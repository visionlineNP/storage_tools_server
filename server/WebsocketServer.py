import hashlib
import secrets
import socket
import time
import json
import os
import urllib
import uuid
import redis
import yaml

from flask import flash, jsonify, make_response, redirect, render_template, request, send_from_directory, session, url_for
from flask_socketio import SocketIO, disconnect, join_room
from threading import Event, Thread
from zeroconf import NonUniqueNameException, ServiceInfo, Zeroconf

from server.ServerWorker import get_source_by_mac_address
from server.debug_print import debug_print
from server.utils import dashboard_room, get_ip_addresses
from server.__version__ import __version__



class WebsocketServer:
    def __init__(self, socketio:SocketIO) -> None:
        self.m_sio = socketio
        self.m_id = os.getpid()

        redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=redis_host, port=6379, db=0)

        # maps sources to sockets
        self.m_connections = {}
        self.m_keys = {}
        self.sources_set_key = 'connected_sources'
        self.m_keys_filename = os.environ.get("KEYSFILE", "config/keys.yaml")
        self.m_volume_map_filename = os.environ.get("VOLUME_MAP", "config/volumeMap.yaml")
        self.m_exit_flag = Event()
        self.m_thread = None
        self.m_config = None

        self.m_zeroconf = None
        self.m_device_files_buffer = {}

        self.pubsub = self.redis.pubsub()
        self._load_config()    
        self._setup_zeroconf()    
        self._load_keys()
        self._load_volume_map()
        self._emit_listener()
        self._action_listener()

    def _load_config(self):
        config_filename = os.environ.get("CONFIG", "config/config.yaml")

        debug_print(f"Using {config_filename}")
        with open(config_filename, "r") as f:
            self.m_config = yaml.safe_load(f)

            self.m_config["source"] = get_source_by_mac_address() + "_" + str(self.m_config["port"])
            self.m_config["volume_root"] = os.environ.get("VOLUME_ROOT", "/")

    def _submit_remote_action(self, action, data):
        msg = {
            "action": action,
            "data": data
        }
        self.redis.lpush("remote_work", json.dumps(msg))

    def _setup_zeroconf(self):
        if not self.m_config.get("provide_zeroconf", False):
            return 
        
        this_claimed = self.redis.set("zero_conf", "claimed",  nx=True, ex=5)
        if not this_claimed:
            debug_print(f"{self.m_id}:  zero conf already claimed")
            return 

        self.m_zeroconf = Zeroconf()
        debug_print("enter")

        ip_addresses = get_ip_addresses()
        addresses = [socket.inet_aton(ip) for ip in ip_addresses]

        debug_print(f"using address: {ip_addresses}")
        desc = {"source": self.m_config["source"].encode("utf-8")}

        info = ServiceInfo(
            "_http._tcp.local.",
            "Airlab_storage._http._tcp.local.",
            addresses=addresses,
            port=self.m_config["port"],
            properties=desc,
        )

        try:
            self.m_zeroconf.unregister_service(info)
            self.m_zeroconf.register_service(info)
        except NonUniqueNameException as e:
            debug_print("Zeroconf already set up? Is there a dupilcate process?")


    def everyone_reload_keys(self):
        self.redis.publish("websocket_action", json.dumps({'action': 'reload_keys'}))
        self._submit_remote_action("reload_keys", {})
        self.redis.publish("broadcast", json.dumps({'action': 'reload_keys'}))
        self._load_keys()
        self.on_request_keys()
        pass 

    # all remote entries are in the form of "remote_entries:{source}:{upload_id}"
    def create_remote_entry(self, source, upload_id, entry):
        entry_json = json.dumps(entry)
        self.redis.set(f'remote_entries:{source}:{upload_id}', entry_json)

    def fetch_remote_entry(self, source, upload_id):
        entry_json = self.redis.get(f'remote_entries:{source}:{upload_id}')
        if entry_json:
            return json.loads(entry_json)
        return None

    def update_remote_entry(self, source, upload_id, updated_entry):
        if not "start_datetime" in updated_entry:
            debug_print(f"Skipping {updated_entry}")

        entry_json = json.dumps(updated_entry)
        self.redis.set(f'remote_entries:{source}:{upload_id}', entry_json)

    def delete_remote_entries_for_source(self, source):
        cursor = '0'
        while cursor != 0:
            cursor, keys = self.redis.scan(cursor=cursor, match=f'remote_entries:{source}:*')
            if keys:
                # Delete the matching keys
                self.redis.delete(*keys)    

    def set_device_fs_info(self, source, fs_info):
        fs_info_json = json.dumps(fs_info)
        self.redis.set(f'fs_info:{source}', fs_info_json)

    def remove_device_fs_info(self, source):
        cursor = '0'
        while cursor != 0:
            cursor, keys = self.redis.scan(cursor=cursor, match=f'fs_info:{source}:*')
            if keys:
                # Delete the matching keys
                self.redis.delete(*keys)    

    def device_remove_project(self, source):
        keys = self.redis.keys(f'device_project:{source}') 
        if keys:
            self.redis.delete(*keys)

    def add_source(self, source, source_type):
        """Add a new source. 

        Args:
          source: Name of source
          source_type: which type of source. One of [device, node]
        """
        self.redis.sadd(f"{self.sources_set_key}:{source_type}", source)

    def delete_source(self, source, source_type):
        """remove an existing source. 

        Args:
          source: Name of source
          source_type: which type of source. One of [device, node]    
        """
        self.redis.srem(f"{self.sources_set_key}:{source_type}", source)

    def get_sources(self, source_type):
        """Get the list of sources for a type

        Args:
          source_type: which type of source. One of [device, node]
        """
        sources = self.redis.smembers(f"{self.sources_set_key}:{source_type}")
        return [source.decode("utf-8") for source in sources]



    # message queues 

    def _process_message(self, channel, data):
        if channel == "websocket_action":
            action = data.get("action")
            if action == "reload_keys":
                self._load_keys() 
            elif action == "reload_volume_map":
                self._load_volume_map()
            else:
                debug_print(f"unprocessed action {action}")

    def _action_listener(self):
        def listen():
            for message in self.pubsub.listen():
                if message['type'] == 'message':
                    channel = message["channel"].decode("utf-8")
                    data = json.loads(message['data'])
                    self._process_message(channel, data)
        self.pubsub.subscribe("websocket_action")
        listener_thread = Thread(target=listen)
        listener_thread.daemon = True
        listener_thread.start()


    def _emit_listener(self):
        # only want one thread at a time. 
        if self.m_thread is not None:
            return
        # debug_print(f"{os.environ['REDIS_URL']}")
        def listen():
            while not self.m_exit_flag.is_set():
                try:
                    # Wait for a message from the Redis queue
                    _, message = self.redis.brpop("emit", timeout=1)
                    if message:
                        # debug_print(message)
                        msg = json.loads(message.decode('utf-8'))
                        event = msg.get("event")
                        data = msg.get("msg")
                        room = msg.get("to", None)
                        debug = msg.get("debug", False)
                        with_nodes = "all_node" in room  or msg.get("with_nodes", False)

                        if "all_dash" in room:                            
                            self._send_to_all_dashboards(event, data, with_nodes, debug)
                        else:
                            if debug:
                                debug_print(f"{event} to={room}")
                            self.m_sio.emit(event, data, to=room)


                except TypeError:
                    # Handle timeout (when no message is received within the timeout period)
                    pass
        listener_thread = Thread(target=listen)
        listener_thread.daemon = True
        listener_thread.start()
        self.m_thread = listener_thread

    def _send_to_all_dashboards(self, event, data, with_nodes=False, debug=False):
        dashboards = self.get_sources("dashboard")
        for dashboard in dashboards:
            if debug: debug_print(f"sending {event}  to {dashboard}")
            self.m_sio.emit(event, data, to=dashboard)        
        
        if with_nodes:
            nodes = self.get_sources("node")
            for node in nodes:
                if debug: debug_print(f"sending {event}  to {dashboard}")
                self.m_sio.emit(event, data, to=node)

    def _update_dashboard_status(self, source:str, upload_id:str) -> None:
        # update server remote tab
        msg = {
            "on_remote": True,
            "on_local": True,
            "upload_id": upload_id
        }
        self._send_to_all_dashboards("dashboard_file_server", msg)


    def stop(self):
        self.m_exit_flag.set()
        if self.m_thread:
            self.m_thread.join()
            self.m_thread = None

    def _load_keys(self):
        debug_print(f"- loading {self.m_keys_filename} {self.m_id}")
        if os.path.exists(self.m_keys_filename):
            with open(self.m_keys_filename, "r") as f:
                keys = yaml.safe_load(f)
                self.m_keys = keys["keys"]
                self.m_config["API_KEY_TOKEN"] = keys.get("API_KEY_TOKEN", None)

    def _load_volume_map(self):
        volume_map = None
        if os.path.exists(self.m_volume_map_filename):
            with open(self.m_volume_map_filename, "r") as f:
                volume_map = yaml.safe_load(f)

        if volume_map is None:
            volume_map = {"volume_map": {"room":"all_dashboards"}}

        self.m_config["volume_map"] = volume_map.get("volume_map", {})


    def _validate_api_key_token(self, api_key_token):
        # this should be more secure
        # for now we will just look up the key
        return api_key_token in self.m_keys

    def _validate_user_credentials(self, username, password):
        # debug_print((username, password))
        # Placeholder function to validate credentials
        return username == "admin" and password == "NodeNodeDevices"



    # commands 
    def _submit_action(self, action:str, data:dict):
        msg = {
            "action": action,
            "data": data
        }
        self.redis.lpush("work", json.dumps(msg))

    def _send_all_data(self, data):
        self._send_device_data(data)
        self._send_node_data(data)
        self._send_server_data(data)
        self.on_request_projects(data)
        self.on_request_robots(data)
        self.on_request_sites(data)
        self.on_request_keys(data)
        self.on_request_search_filters(data)
        self.on_request_remote_servers(data)
        debug_print("Sent all data")

        # after this, there should be no new data!
        room = dashboard_room(data)
        self.m_sio.emit("has_new_data", {"value": False}, to=room)

    def on_request_new_data(self, data):
        self._send_server_data(data)

    def on_request_files_exist(self, data):
        self._submit_action("request_files_exist", data)

    def on_request_remote_files_exist(self, data):
        self._submit_remote_action("request_files_exist", data)

    def _send_server_data(self, data):
        self._submit_action("get_server_data_stub", data)
        room = dashboard_room(data)
        self.m_sio.emit("has_new_data", {"value": False}, to=room)

    def _send_node_data(self, data=None):
        if data is None:
            data = {"room": "all_dashboards"}
        self._submit_action("get_node_data_stub", data)

    def _send_device_data(self, data=None):
        if data is None:
            data = {"room": "all_dashboards"}
        self._submit_action("get_device_data_stub", data)

    # projects
    def on_request_projects(self, data):
        self._submit_action("request_projects_and_desc", data)

    def on_add_project(self, data):
        self._submit_action("add_project", data)

    def on_set_project(self, data):
        self._submit_action("set_project", data)

    def on_edit_project(self, data):
        self._submit_action("edit_project", data)

    def on_delete_project(self, data):
        self._submit_action("delete_project", data)

    # robot names
    def on_request_robots(self, data):
        self._submit_action("request_robot_names", data)

    def on_add_robot(self, data):
        self._submit_action("add_robot_name", data)

    def on_remove_robot(self, data):
        debug_print(data)
        self._submit_action("remove_robot_name", data)

    def on_update_entry_robot(self, data):
        self._submit_action("update_entry_robot", data)

    # site names
    def on_request_sites(self, data):
        self._submit_action("request_sites", data)

    def on_add_site(self, data):
        self._submit_action("add_site", data)

    def on_remove_site(self, data):
        self._submit_action("remove_site", data)

    def on_update_entry_site(self, data):
        self._submit_action("update_entry_site", data)

    # remote servers
    def on_request_remote_servers(self, data):
        self._submit_action("request_remote_servers", data)

    def on_add_remote_server(self, data):
        self._submit_action("add_remote_server", data)

    def on_remove_remote_server(self, data):
        self._submit_action("remove_remote_server", data)


    # key master
    def on_request_keys(self, data=None):
        keys = self.m_keys
        api_token = self.m_config.get("API_KEY_TOKEN", "")
        self.m_sio.emit("key_values", {"data": keys, "source": self.m_config["source"], "token": api_token})

    def _save_keys(self):
        write_data = {
            "keys": self.m_keys,
            "API_KEY_TOKEN": self.m_config.get("API_KEY_TOKEN", "")
            }
        yaml.dump(write_data, open(self.m_keys_filename, "w"))

    def on_generate_key(self, data):
        source = data.get("source")
        name = data.get("name")        
        # add some spice to the key
        salt = secrets.token_bytes(16)

        values = [source, name, f"{salt}"]
        key = hashlib.sha256("_".join(values).encode()).hexdigest()[:16]
        if key in self.m_keys:
            self.m_sio.emit("server_status", {"msg": "failed to create key", "rtn": False})
            return 
        self.m_keys[key] = name

        self._save_keys()
        self.m_sio.emit("server_status", {"msg": "Created key", "rtn": True})
        self.m_sio.emit("generated_key", {"key": key})
        self.on_request_keys({"room": "all_dashboards"})
        self.everyone_reload_keys()
    

    def on_insert_key(self, data):
        name = data.get("name")
        key = data.get("key")

        if key in self.m_keys: 
            debug_print("Key name exists")
            return 
        if name in self.m_keys.values():
            debug_print("Key value exists")
            return 
        self.m_keys[key] = name 
        self._save_keys()
        self.m_sio.emit("server_status", {"msg": "Inserted key", "rtn": True})
        self.on_request_keys({"room": "all_dashboards"})
        self.everyone_reload_keys()


    def on_delete_key(self, data):
        source = data.get("source")
        key = data.get("key")
        name = data.get("name")

        debug_print(f"deleting {key} for {name} via {source}")

        if key in self.m_keys:
            del self.m_keys[key]
        else:
            debug_print(f"Did not find {key}")
            return 

        self._save_keys()
        self.everyone_reload_keys()


    def on_set_api_key_token(self, data):
        key = data.get("key")
        self.m_config["API_KEY_TOKEN"] = key 
        self._save_keys()
        self.on_request_keys({"room": "all_dashboards"})
        self.everyone_reload_keys()


    def download_keys(self):
        fullpath = self.m_keys_filename
        if not fullpath.startswith("/"):
            if "PWD" in os.environ:
                fullpath = os.path.join(os.environ["PWD"], fullpath)
            else:
                fullpath = os.path.join("/app", fullpath)

        debug_print(f"Download {fullpath}")
        directory = os.path.dirname(fullpath)
        filename = os.path.basename(fullpath)
        return send_from_directory(directory=directory, path=filename, as_attachment=True)


    def upload_keys(self):
        if 'file' not in request.files:
            return jsonify({'message': 'No file part'}), 400
        
        file = request.files['file']

        if file.filename == '':
            return jsonify({'message': 'No selected file'}), 400

        if file:
            try: 
                yaml_content = yaml.safe_load(file.read())
                keys = yaml_content.get("keys", None)
                if not keys:
                    return jsonify({'message': f"Error. {file.filename} did not contain any keys"}), 400
                self.m_keys = keys
                self._save_keys()
                self.on_request_keys(None)
                self.everyone_reload_keys()


                return jsonify({'message': 'Keys updated.'}), 200
            
            except yaml.YAMLError as e:
                return jsonify({'message': f'Error parsing YAML file: {str(e)}'}), 400
            except Exception as e:
                return jsonify({'message': f'Error saving file: {str(e)}'}), 500            

    # zero config

    # get the list of addresses that could be used, plus
    # the manually selected one. 
    def on_request_zeroconf_address(self, data):
        pass 

    def on_select_zeroconf_address(self, data):
        pass 

    # toggle on and off
    def on_set_zeroconf(self, data):
        pass

    # searching 
    def on_request_search_filters(self, data):
        self._submit_action("request_search_filters", data)

    def on_search(self, data):
        self._submit_action("search", data)

    # device 
    ## device data
    def on_device_status(self, data):
        source = data.get("source")
        msg = {"source": source}
        # self.m_ui_status[source] = None
        if "msg" in data:
            msg["msg"] = data["msg"]
        self._send_to_all_dashboards("device_status", msg)

    def on_device_status_tqdm(self, data):
        self._send_to_all_dashboards("device_status_tqdm", data)

    def on_device_scan(self, data):
        self.m_sio.emit("device_scan", data)

    # def on_device_files_items(self, data):
    #     # debug_print(f"enter {self.m_id}")
    #     source = data.get("source")
    #     files = data.get("files")

    #     # debug_print(files[0])

    #     self.m_device_files_buffer[source] = self.m_device_files_buffer.get(source, [])
    #     self.m_device_files_buffer[source].extend(files)

    def device_set_project(self, source, project):
        self.redis.set(f'device_project:{source}', project)

    # deprecated
    # def on_device_files(self, data):
    #     debug_print(f"enter {self.m_id}")

    #     source = data.get("source")
    #     project = data.get("project", None)
    #     # debug_print(f"project is [{project}]")
    #     if project is None:
    #         debug_print(f"clearing {source}")
    #         self.delete_remote_entries_for_source(source)
            
    #     if project and project not in self.m_config["volume_map"]:
    #         self.m_sio.emit("server_error", {"msg": f"Project: {project} does not have a volume mapping"})
    #         debug_print("Error")

    #     # files = data.get("files")
    #     files = self.m_device_files_buffer.get( source, data.get("files", []))
    #     if source in self.m_device_files_buffer: del self.m_device_files_buffer[source]

    #     debug_print(f"Files has: {len(files)}")

    #     self.clear_cancel(source)
    #     # self.m_selected_files_ready[source] = False
    #     # self.m_projects[source] = project
    #     self.device_set_project(source, project)
    #     self.add_source( source, "device")

    #     # note, this could be emitted
    #     self.set_device_fs_info(source, data.get("fs_info"))
    #     # self.m_fs_info[source] = data.get("fs_info")

    #     # debug_print(f"Clearing {source} with {len(files)}")
    #     self.delete_remote_entries_for_source(source)

    #     debug_once = True

    #     for entry in files:
    #         if entry is None:
    #             if debug_once:
    #                 debug_print("Empty entry!")
    #                 debug_once = not debug_once
    #             continue

    #         if not "dirroot" in entry:
    #             debug_print(entry)
    #             continue

    #         self._submit_action("device_add_entry", {"source": source, "entry": entry})


    #     # debug_print("data complete")
    #     # Do we really need to resend the device data?
    #     # Yes, we do. 
    #     time.sleep(0.5)
    #     self._send_device_data()
    #     debug_print("sent")

    def on_device_data(self, data):
        debug_print("enter")
        source = data.get("source")
        project = data.get("project")
        # robot_name = data.get("robot_name")
        # total = data.get("total")
        fs_info = data.get("fs_info")

        if project and project not in self.m_config["volume_map"]:
            self.m_sio.emit("server_error", {"msg": f"Project: {project} does not have a volume mapping"})
            debug_print(f"Project: {project} does not have a volume mapping")
            return 
        
        self.clear_cancel(source)
        self.device_set_project(source, project)
        self.add_source( source, "device")
        self.set_device_fs_info(source, fs_info)

        self.redis.delete(f"device_data_blocks:{source}")

    def on_estimate_runs(self, data):
        debug_print(data)
        self._submit_action("estimate_runs", data)

    def on_device_data_block(self, data):
        source = data.get("source")
        total = data.get("total")
        id = data.get("id")
        block = data.get("block")

        for entry in block:
            self._submit_action("device_add_entry", {"source": source, "entry": entry})            

        self.redis.sadd(f"device_data_blocks:{source}", id)
        arrived = self.redis.smembers(f"device_data_blocks:{source}")
        
        # debug_print(f"{len(arrived)} / {total}")

        if len(arrived) == total:
            debug_print("Send")
            time.sleep(0.25)
            self._send_device_data()

    def on_device_remove(self, data):

        debug_print(data)

        source = data.get("source")
        ids = data.get("files")

        filenames = []
        for upload_id in ids:

            entry = self.fetch_remote_entry(source, upload_id)
            if not entry:
                debug_print(f"did not find [{upload_id}] in {source}")
                continue

            dirroot = entry["remote_dirroot"]
            relpath = entry["fullpath"].strip("/")
            filenames.append((dirroot, relpath, upload_id))

        msg = {"source": source, "files": filenames}
        debug_print(msg)
        self.m_sio.emit("device_remove", msg, to=source)

    def on_device_request_files(self, data):
        self._submit_action("device_request_files", data)

    def on_device_cancel_transfer(self, data):
        source = data.get("source")
        self.set_cancel(source)
        self.m_sio.emit("device_cancel_transfer", data, to=source)

    # handle socket connections 
    def on_connect(self, con=None):
        if con is not None:
            debug_print(f"passed {con}")

        username = request.args.get("username")
        if username is None:
            username = request.headers.get('X-Authenticated-User')
        debug_print(f"username is {username}")

        api_key_token = request.headers.get("X-Api-Key")
        if api_key_token:
            debug_print(f"Api key: {api_key_token}")
            if self._validate_api_key_token(api_key_token):
                debug_print("Valid key")
                return

            # disconnect()
            raise ConnectionRefusedError(f"Invalid API key token {api_key_token}")

        auth_header = request.headers.get("Authorization")

        if auth_header:
            debug_print(auth_header)
            auth_type, token = auth_header.split()
            if auth_type.lower() == "bearer":
                api_key_token = token
                # debug_print(api_key_token)
                # Validate the API key token here
                if self._validate_api_key_token(api_key_token):
                    debug_print("Valid token")
                    session["api_key_token"] = api_key_token
                    return "Valid Connection", 200
                else:
                    debug_print("Invalid token")
                    raise ConnectionRefusedError(f"Invalid API key token {api_key_token}")

            elif auth_type.lower() == "basic":
                user = request.headers.get('X-Authenticated-User')  # Header set by Nginx after LDAP auth
                ## need to pass this to send_all_data.
            else:
                debug_print("Disconnect")
                disconnect()


    def on_join(self, data:dict):
        debug_print(f"source: {self.m_config['source']} {data}")
        # source type is one of "node", "device", "dashboard"
        source = data["room"]
        source_type = data.get("type", None)

        if source_type == "node":
            # self._clear_node_data(source)
            # add a node connection worker
            pass

        self.add_source(source, source_type)
        join_room(source)
        self.m_sio.emit("dashboard_info", {"data": f"Joined room: {source}", "source": self.m_config["source"]}, to=source)


        if source_type == "dashboard":
            self._send_all_data({"room": source})
            self._send_to_all_dashboards("version", __version__)

        if source_type == "device":
            self.clear_all_locks(source)

        self.m_connections[source] = {
            "source_type": source_type,
            "sid": request.sid
        }

    def on_disconnect(self):
        remove = None

        for source, con in self.m_connections.copy().items():
            debug_print(f"request.sid: {request.sid} / con['sid']: {con['sid']}")
            if con["sid"] == request.sid:
                remove = source
                break

        if remove:
            source_type = self.m_connections[remove]["source_type"]
            del self.m_connections[remove]

            self.delete_source(remove, source_type)

            # device related
            if remove in self.m_device_files_buffer: del self.m_device_files_buffer[remove]
            self.remove_device_fs_info(remove)
            self.delete_remote_entries_for_source(remove)
            self.device_remove_project(remove)
            self._clear_node_data(remove)

            if source_type == "node":
                self._send_node_data()
            elif source_type == "device":
                self._send_device_data()

        debug_print(f"Got disconnect: {remove}")

    def on_request_server_data(self, data=None):
        self._send_server_data(data)

    def on_request_server_ymd_data(self, data=None):
        self._submit_action("get_server_data_ymd", data)

    def on_request_device_ymd_data(self, data=None):
        self._submit_action("get_device_data_ymd", data)

    def on_request_remote_ymd_data(self, data=None):
        self._submit_remote_action("request_remote_ymd_data", data)

    def on_remote_request_files(self, data=None):
        self._submit_remote_action("remote_request_files", data)

    def on_request_remote_cancel_tranfer(self, data):
        debug_print(f"enter {data}")
        room = data.get("source")
        self.m_sio.emit("remote_cancel_transfer", data, to=room)

    def on_request_debug_send(self, data):
        debug_print(f"enter {data}")
        room = data.get("source")
        self.m_sio.emit("debug_send", data, to=room)

    def on_request_cancel_push_transfer(self, data):
        source = data["source"]
        debug_print(f"enter {data}")
        self.set_cancel(source)

    def on_remote_cancel_transfer(self, data=None):
        debug_print(f"enter {data}")
        # self._submit_remote_action("remote_cancel_transfer", data)
        self._submit_action("remote_cancel_transfer", data)

    # run on local, pushed data to remote. 
    def on_remote_transfer_files(self, data):
        self._submit_action("remote_transfer_files", data)

    # received node data
    def on_remote_node_data(self, data):
        self._submit_action("remote_node_data", data)

    def on_remote_node_data_block(self, data):
        self._submit_action("remote_node_data_block", data)

    def on_request_node_ymd_data(self, data):
        self._submit_action("request_node_ymd_data", data)

    

    # handle http
    ### http commands 
    def authenticate(self):
        # debug_print(request.endpoint)

        # note, the we are not geting the "Authoerizion" header for download link!
        if request.endpoint == "download_file":
            return

        # Check if the current request is for the login page
        if request.endpoint == "show_login_form" or request.endpoint == "login":
            debug_print(request.endpoint)
            return  # Skip authentication for login page to avoid loop

        api_key = request.headers.get('X-Api-Key')
        if api_key:
            if self._validate_api_key_token(api_key):
                return
            else:
                return "Invalid API Key " + api_key, 402

        auth_header = request.headers.get("Authorization")
        if auth_header:
            # debug_print(auth_header)
            auth_type, token = auth_header.split()
            if auth_type.lower() == "bearer":
                api_key_token = token
                # Validate the API key token here
                if self._validate_api_key_token(api_key_token):
                    session["api_key_token"] = api_key_token
                else:
                    return "Invalid API key token", 402
            elif auth_type.lower() == "basic":

                user = request.headers.get('X-Authenticated-User')  # Header set by Nginx after LDAP auth
                # debug_print(user)
                if not user:
                    return jsonify({'error': 'Unauthorized-v1'}), 401

                # Generate a token for the authenticated user
                # token = self.generate_token(user)

                response = make_response()
                response.set_cookie(
                    "username", user
                )
            else:
                return jsonify({'error': 'Unauthorized-v2'}), 401

        else:
            if self.m_config.get("use_ldap", True):
                return jsonify({'error': 'Unauthorized-v3. Config is set to use LDAP and non-ldap auth path was triggered'}), 401

            username = request.cookies.get("username")
            password = request.cookies.get("password")
            if username and password and self._validate_user_credentials(username, password):
                # debug_print("Valid")
                session["user"] = (
                    username  # You can customize what you store in the session
                )

                return  # continue the request

            return redirect( url_for("show_login_form"))  # Redirect to login if no valid session or cookies

    # Only used for local server. Not used when running LDAP
    def login(self):
        debug_print("enter")
        username = request.form["username"]
        password = request.form["password"]

        if self._validate_user_credentials(username, password):
            response = make_response(redirect("/"))
            response.set_cookie(
                "username", username, max_age=3600 * 24
            )  # Expires in 24 hour
            response.set_cookie(
                "password", urllib.parse.quote(password), max_age=3600 * 24
            )  # Not recommended to store password directly

            api_key_token = None
            for key in self.m_config.get("keys", {}):
                if self.m_keys[key].lower() == username.lower():
                    api_key_token = key
                    break
            if api_key_token is not None:
                response.set_cookie("api_key_token", urllib.parse.quote(api_key_token), max_age=3600 * 24)
            else:
                debug_print(f"Failed to find api_key for [{username}]")

            # debug_print(f"----- {username} {api_key_token} -------")

            return response
        else:
            flash("Invalid username or password")
            return redirect(url_for("show_login_form"))


    def index(self):
        session_token = str(uuid.uuid4())
        response = make_response(render_template("index.html", session={"token": session_token}))

        # response = make_response(send_from_directory("static", "index.html"))
        user = request.headers.get('X-Authenticated-User')
        if user:
            response.set_cookie("username", user)

        return response
    
    def get_name(self):
        msg = {"source": self.m_config["source"]}
        return jsonify(msg)

    def serve_js(self, path):
        return send_from_directory("js", path)

    def serve_css(self, path):
        return send_from_directory("css", path)

    def show_login_form(self):
        return render_template("login.html")

    def set_lock(self, source, id):
        """Set a lock for the given source and id if it doesn't already exist."""
        lock_key = f"lock:{source}:{id}"
        # Set the lock if it doesn't exist (SETNX)
        # This returns 1 if the lock is set, 0 if it already exists
        lock_set = self.redis.setnx(lock_key, "locked")
        return bool(lock_set)  # True if lock was set, False if it already existed

    def remove_lock(self, source, id):
        """Remove the lock for the given source and id."""
        lock_key = f"lock:{source}:{id}"
        # Remove the lock key
        self.redis.delete(lock_key)

    def clear_all_locks(self, source):
        lock_keys = self.redis.keys(f"lock:{source}:*")
        if lock_keys:
            self.redis.delete(*lock_keys)

    def set_cancel(self, source):
        """Set the cancel flag for a given source."""
        self.redis.set(f'cancel:{source}', '1')

    def clear_cancel(self, source):
        """Clear the cancel flag for a given source."""
        self.redis.delete(f'cancel:{source}')

    def is_canceled(self, source):
        """Check if the cancel flag is set for a given source."""
        return self.redis.get(f'cancel:{source}') == b'1'  # Return True if '1', else False
    

    def _clear_node_data(self, source):
        # remove all data for this source.
        self.delete_remote_entries_for_source(source)
        self.redis.delete(f"node_data_blocks:{source}")
        self.redis.delete(f"node_data_stats:{source}")

        pass 

    def handle_file(self, source: str, upload_id: str):
        debug_print(f"{source} {upload_id} {self.m_id}")

        entry = self.fetch_remote_entry(source, upload_id)
        if entry is None:
            json_data = request.form.get('json')

            debug_print(json_data)
            if json_data:
                entry = json.loads(json_data)
                self.create_remote_entry(source, upload_id, entry)
            else:
                return f"Invalid ID {upload_id} for {source}", 503

        if entry is None:
            debug_print(f"Failed to find entry for {upload_id}")
            return f"Upload ID {upload_id} not found", 503
        
        
        debug_print(f"{entry.get('upload_id')}, {entry.get('basename')}")
        offset = int(request.args.get("offset", 0))
        if offset == 0:
            open_mode = "wb"
        else:
            open_mode = "ab"

        # debug_print(f"{source} {upload_id} {self.m_id}, offset: {offset} ")

        cid = request.args.get("cid")
        splits = request.args.get("splits")
        debug_print(("cid", cid, splits))
        is_last = cid == splits

        filep = request.files.get('file', request.stream)
        # if not "filename" in entry:
        #     debug_print(entry)
        filename = entry["basename"]

        filepath = self._get_file_path_from_entry(entry)
        # filepath = entry.get("localpath", self._get_file_path_from_entry(entry))
        tmp_path = filepath + ".tmp"

        debug_print(filepath)

        if os.path.exists(filepath):
            debug_print(f"{filepath} already exists")
            return jsonify({"message": f"File {filename} alredy uploaded"}), 409

        if self.is_canceled(source):
            debug_print("received cancel")
            return jsonify({"message": f"File {filename} upload canceled"}), 400

        # keep track of expected size. If remote canceled, we won't know.
        expected = entry["size"]

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # we use this in multiple location, better to define it.
        cancel_msg = {
            "div_id": f"status_{upload_id}",
            "source": self.m_config["source"],
            "status": "<B>Canceled</B>",
            "on_device": True,
            "on_server": False,
            "upload_id": upload_id,
        }

        # debug_print(f"opening {tmp_path}")

        if not self.set_lock(source, upload_id):
            debug_print("Duplicated send!")
            return jsonify({"message": f"File {filename} duplicated send!"}), 400

        # Start uploading the file in chunks
        chunk_size = 10 * 1024 * 1024  # 1MB chunks
        with open(tmp_path, open_mode) as fid:
            os.chmod(tmp_path, 0o777 )
            debug_print(f"writing to {tmp_path}")
            while True:

                # todo: add a "set_cancel(source)" and "clear_cancel(source)", and "get_cancel(source)"
                if self.is_canceled(source):
                    self._send_to_all_dashboards("dashboard_file", cancel_msg, with_nodes=True)
                    debug_print(f"cancel {filename}")
                    self.remove_lock(source, upload_id)
                    return jsonify({"message": f"File {filename} upload canceled"}), 520

                try:
                    chunk = filep.read(chunk_size)

                except OSError:
                    # we lost the connection on the client side.
                    debug_print(f"lost connection {filename}")
                    self._send_to_all_dashboards("dashboard_file", cancel_msg, with_nodes=True)
                    self.remove_lock(source, upload_id)
                    return jsonify({"message": f"File {filename} upload canceled"}), 520

                if not chunk:
                    break
                fid.write(chunk)

        

        if os.path.exists(tmp_path) and is_last:
            current_size = os.path.getsize(tmp_path)
            if current_size != expected:
                # transfer canceled politely on the client side, or
                # some other issue. Either way, data isn't what we expected.
                cancel_msg["status"] = (
                    "Size mismatch. " + str(current_size) + " != " + str(expected)
                )
                self._send_to_all_dashboards("dashboard_file", cancel_msg, with_nodes=True)

                debug_print(f"file size missmatch {filename}")
                self.remove_lock(source, upload_id)

                return jsonify({"message": f"File {filename} upload canceled"})

            os.rename(tmp_path, filepath)

            data = {
                "div_id": f"status_{upload_id}",
                "status": "On Device and Server",
                "source": self.m_config["source"],
                "on_device": True,
                "on_server": True,
                "upload_id": upload_id,
            }

            self._send_to_all_dashboards("dashboard_file", data, with_nodes=True)

        self.remove_lock(source, upload_id)


        entry["localpath"] = filepath
        entry["on_server"] = True
        entry["dirroot"] = self._get_dirroot(entry["project"])
        entry["fullpath"] = filepath.replace(entry["dirroot"], "").strip("/")

        # debug_print(f"received {filename}")

        metadata_filename = filepath + ".metadata"
        with open(metadata_filename, "w") as fid:
            json.dump(entry, fid, indent=True)

        os.chmod(metadata_filename, 0o777)

        # todo: replace this with a request to ServerWorker to add the entry and update the runs
        self._submit_action("add_entry", {"entry": entry})


        self._send_to_all_dashboards("has_new_data", {"value": True})

        self._update_dashboard_status(source, upload_id)

        # # TODO: replace send_server_data with "update_server_data"
        # # send_server_data()

        # ymd = entry["date"]
        # project = entry["project"]
        # tab = f"server:{project}:{ymd}"

        # on_request_server_ymd_data({"tab": tab})

        self._submit_action("device_revise_stats", {"sources": self.get_sources("device")})

        return jsonify({"message": f"File {filename} chunk uploaded successfully"})

    def _get_localpath(self, upload_id):
        response_queue = f'response:{uuid.uuid4()}'
        self._submit_action("request_localpath", {"upload_id": upload_id, "response_queue": response_queue})
        response = self.redis.blpop(response_queue, timeout=10)
        if response_queue:
            return response[1].decode("utf-8")
        return None

    def download_file(self, upload_id):
        localpath = self._get_localpath(upload_id)

        debug_print((upload_id, localpath))        
        if localpath:

            directory = os.path.dirname(localpath)
            filename = os.path.basename(localpath)
            
            debug_print(f"Download {localpath} {os.path.exists(localpath)}")
            return send_from_directory(directory=directory, path=filename, as_attachment=True)
        
        return "File Not Found", 404


    ### remote connection
    def on_server_connect(self, data):
        address = data.get("address", None)
        if address:
            self._submit_remote_action("remote_connect", {"address": address})
            
    def on_server_disconnect(self, data):
        self._submit_remote_action("remote_disconnect", {})

    def on_server_refresh(self, data=None):
        msg = {}
        if data:
            address = data.get("address", None)
            if address:
                msg["address"] = address
        self._submit_remote_action("remote_refresh", msg)

    def on_server_status_tqdm(self, data):
        # this status can come from either node or server
        # file upload, so both will be updated.
        self._send_to_all_dashboards("server_status_tqdm", data, with_nodes=True, debug=True)
        self._send_to_all_dashboards("node_status_tqdm", data, with_nodes=True)

    # request from UI to local to transfer files
    def on_server_transfer_files(self, data):
        self._submit_remote_action("server_transfer_files", data)

    # request from RemoteWorker to Server to transfer files
    def on_transfer_node_files(self, data):
        debug_print(data)
        source = data.get("source")
        selected_files = data.get("upload_ids")

        filenames = []
        for upload_id, remote_id in selected_files:
            entry = self.fetch_remote_entry(source, upload_id)
            if not entry:
                debug_print(
                    f"Error! did not find upload id [{upload_id}] for {source}"
                )
                continue

            filepath = self._get_file_path_from_entry(entry)
            if os.path.exists(filepath):
                debug_print(f"File [{filepath}] already exists")
                continue

            complete_relpath = self._get_complete_relpath_from_entry(entry)

            project = entry["project"]
            offset = entry.get("temp_size", 0)
            size = entry["size"]
            # file = entry["fullpath"]
            filenames.append((project, complete_relpath, upload_id, offset, size, remote_id))

        msg = {"source": data.get("source"), "files": filenames, "receiver": self.m_config["source"]}

        self.m_sio.emit("node_send", msg)



    # utils

    def _get_complete_relpath_from_entry(self, entry:dict) -> str:
        relpath = entry["relpath"].strip("/")
        filename = entry["basename"].strip("/")
        if "date" in entry:
            date = entry["date"]
        else:
            date = entry["datetime"].split(" ")[0]
    
        site = entry.get("site", "default")
        if not site:
            site = "default"

        robot_name = entry.get("robot_name", "default")
        if not robot_name: 
            robot_name = "default"
        if robot_name.lower() == "none":
            robot_name = "default"

        debug_print((date, site, robot_name, relpath, filename))
        filedir = os.path.join(date, site, robot_name, relpath, filename)

        return filedir


    def _get_file_path_from_entry(self, entry:dict) -> str:
        project = entry.get("project")

        root = self.m_config.get("volume_root", "/")
        volume = self.m_config["volume_map"].get(project, "").strip("/")

        relpath = entry["relpath"].strip("/")
        filename = entry["basename"].strip("/")
        if "date" in entry:
            date = entry["date"]
        else:
            date = entry["datetime"].split(" ")[0]
    
        site = entry.get("site", "default")
        if not site:
            site = "default"

        robot_name = entry.get("robot_name", "default")
        if not robot_name: 
            robot_name = "default"
        if robot_name.lower() == "none":
            robot_name = "default"

        debug_print((root, volume, date, site, robot_name, relpath))
        filedir = os.path.join(root, volume, date, site, robot_name, relpath)
        filepath = os.path.join(filedir, filename)

        return filepath

    def _get_dirroot(self, project:str) -> str:
        root = self.m_config.get("volume_root", "/")
        volume = self.m_config["volume_map"].get(project, "").strip("/")
        # debug_print((root, project, volume))
        return os.path.join(root, volume)

    ### debug

    def on_debug_scan_server(self, data=None):
        self._submit_action("server_scan", {})

    def on_debug_send(self, data):
        debug_print(data)
        self._submit_action("debug_send", data)
