import json
import socket
from threading import Event, Thread
import time
import redis.exceptions
import socketio
import os 
import redis 
import yaml

from server.ServerWorker import get_source_by_mac_address
from server.debug_print import debug_print
from server.sqlDatabase import Database
from server.utils import SocketIORedirect, dashboard_room, get_ip_addresses, get_upload_id, pbar_thread

class RemoteWorker:
    """
    The RemoteWorker class encapsulates the connection between this server 
    and a remote server. It is intended to be run as a single process
    from the bacpApp.py script.  

    It uses the same config file as WebsocketServer and ServerWorker.

    It can submit actions to the "work" queue.
    It receives actions from the "remote_work" queue. 

    Actions:
        - "remote_connect": Establish a connection to a remote service.
        - "remote_disconnect": Disconnect from a remote service.
        - "request_remote_ymd_data": Request year-month-day-specific data from the remote service.
        - "remote_refresh": Refresh remote service data.
        - "request_files_exist": Check if specified files exist on the remote.
        - "remote_request_files": Initiate file transfer request from remote to local.
        - "remote_cancel_transfer": Cancel an ongoing file transfer from the remote.
        - "server_transfer_files": Push specified files to the remote server.
        - "remote_emit": Emits a debug message for logging.
        - "reload_keys": Reload authentication or API keys for remote access.

    Env Variables:
    - REDIS_HOST. Default: "localhost". 
    - VOLUME_MAP. Default: "config/volumeMap.yaml"
    - KEYSFILE. Default: "config/keys.yaml"
    - CONFIG. Default: "config/config.yaml"
    - SERVERNAME. Defaults: "Server"

    The RemoteConnection implements the connection to the remote server.
    It handles all of the websocket functions. 
    """
    def __init__(self) -> None:

        self.m_redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=self.m_redis_host, port=6379, db=0)
        self.m_exit_flag = Event()
        self.m_volume_map_filename = os.environ.get("VOLUME_MAP", "config/volumeMap.yaml")
        self.m_keys_filename = os.environ.get("KEYSFILE", "config/keys.yaml")
        self.m_sio = SocketIORedirect()
        self.m_database = None 
        self.sources_set_key = 'connected_sources'  

        self._load_config()
        self._load_keys()
        self._start_work_listener()

        self.m_remote_connection = RemoteConnection(self.m_config, self)
        debug_print("--  RemoteWorker is ready -- ")

    def _load_keys(self):
        debug_print(f"- loading {self.m_keys_filename}")
        if os.path.exists(self.m_keys_filename):
            with open(self.m_keys_filename, "r") as f:
                keys = yaml.safe_load(f)
                self.m_config["API_KEY_TOKEN"] = keys.get("API_KEY_TOKEN", None)

    def stop(self):
        self.m_exit_flag.set()

    def should_run(self):
        return not self.m_exit_flag.is_set()

    def set_remote_connection_address(self, address):
        self.redis.set("remote_connection", address)
    
    def get_remote_connection_address(self):
        address = self.redis.get("remote_connection")
        if address:
            return address.decode("utf-8")
        return None 
    
    def clear_remote_connection_address(self):
        keys = self.redis.keys("remote_connection") 
        if keys:
            self.redis.delete(*keys)

    def create_remote_entry(self, source, upload_id, entry):
        entry_json = json.dumps(entry)
        self.redis.set(f'remote_entries:{source}:{upload_id}', entry_json)

    def delete_remote_entries_for_source(self, source):
        cursor = '0'
        while cursor != 0:
            cursor, keys = self.redis.scan(cursor=cursor, match=f'remote_entries:{source}:*')
            if keys:
                # Delete the matching keys
                self.redis.delete(*keys)    

    def get_file_path_from_entry(self, entry:dict) -> str:
        project = entry.get("project")

        root = self.m_config.get("volume_root", "/")
        volume = self.m_config["volume_map"].get(project, "").strip("/")

        relpath = entry["relpath"]
        filename = entry["basename"]
        if "date" in entry:
            date = entry["date"]
        else:
            date = entry["datetime"]

        if " " in date:
            date = date.split(" ")[0]
    
        site = entry.get("site", "default")
        if not site:
            site = "default"

        robot_name = entry.get("robot_name", "default")
        if not robot_name: 
            robot_name = "default"
        if robot_name.lower() == "none":
            robot_name = "default"


        try:
            filedir = os.path.join(root, volume, date, site, robot_name, relpath)
        except TypeError as e:
            debug_print((root, volume, date,relpath))
            raise e

        filepath = os.path.join(filedir, filename)

        return filepath


    def _load_config(self):
        config_filename = os.environ.get("CONFIG", "config/config.yaml")

        volume_map = None
        if os.path.exists(self.m_volume_map_filename):
            with open(self.m_volume_map_filename, "r") as f:
                volume_map = yaml.safe_load(f)

        if volume_map is None:
            volume_map = {"volume_map": {}}


        debug_print(f"Using {config_filename}")
        with open(config_filename, "r") as f:
            self.m_config = yaml.safe_load(f)
            self.m_config["source"] = get_source_by_mac_address() + "_" + str(self.m_config["port"])
            self.m_config["volume_map"] = volume_map.get("volume_map", {})
            self.m_config["volume_root"] = os.environ.get("VOLUME_ROOT", "/")


        v_root = self.m_config.get("volume_root", "/")
        v_map = self.m_config.get("volume_map", {}).copy()
        for name in v_map:
            v_map[ name ] = os.path.join(v_root,  v_map.get(name, "").strip("/"))

        blackout = self.m_config.get("blackout", [])
        self.m_database = Database(v_map, blackout)

    # submit an action for one of the worker threads
    def _submit_action(self, action:str, data:dict):
        msg = {
            "action": action,
            "data": data
        }
        self.redis.lpush("work", json.dumps(msg))

    def _start_work_listener(self):
        # only want one thread at a time. 
        def work_listen():
            while not self.m_exit_flag.is_set():
                try:
                    # Wait for a message from the Redis queue
                    _, message = self.redis.brpop("remote_work", timeout=1)
                    if message:
                        msg = json.loads(message.decode('utf-8'))
                        action = msg.get("action")
                        data = msg.get("data")
                        self._run_action(action, data)

                except TypeError:
                    # Handle timeout (when no message is received within the timeout period)
                    pass
                except redis.exceptions.ConnectionError as e:
                    debug_print(f"Error reading from {self.m_redis_host}")
                    raise e
                
        work_thread = Thread(target=work_listen)
        work_thread.daemon = True
        work_thread.start()

    def _run_action(self, action:str, data:dict):
        """
        Executes a specified action based on the provided action identifier and data.

        Args:
            action (str): The action to perform. Supported actions are listed below.
            data (dict): Data required to execute the specified action.

        Actions:
            - "remote_connect": Establish a connection to a remote service.
            - "remote_disconnect": Disconnect from a remote service.
            - "request_remote_ymd_data": Request year-month-day-specific data from the remote service.
            - "remote_refresh": Refresh remote service data.
            - "request_files_exist": Check if specified files exist on the remote.
            - "remote_request_files": Initiate file transfer request from remote to local.
            - "remote_cancel_transfer": Cancel an ongoing file transfer from the remote.
            - "server_transfer_files": Push specified files to the remote server.
            - "remote_emit": Emits a debug message for logging.
            - "reload_keys": Reload authentication or API keys for remote access.
        """

        if action == "remote_connect":
            self._remote_connect(data)
        elif action == "remote_disconnect":
            self._remote_disconnect(data)
        elif action == "request_remote_ymd_data":
            self._request_remote_ymd_data(data)
        elif action == "remote_refresh":
            self._remote_refresh(data)
        elif action == "request_files_exist":
            self._request_files_exist(data)

        # pull from remote 
        elif action == "remote_request_files":
            self._remote_request_files(data)
        elif action == "remote_cancel_transfer":
            self._remote_cancel_transfer(data)

        # push to remote
        elif action == "server_transfer_files":
            self._server_transfer_files(data)

        elif action == "remote_emit":
            debug_print(data)

        # update keys
        elif action == "reload_keys":
            ## note! we are assuming there is only one 
            ## remote connection server right now. so reload keys is a 
            ## consumed action, not a process!
            self._load_keys()
        else:
            debug_print(f"unhandled action {action}")


    def _remote_connect(self, data):
        address = data.get("address")
        self.m_remote_connection.disconnect()
        self.m_remote_connection.connect(address)

    def _remote_disconnect(self, data):
        self.m_remote_connection.disconnect()        

    def _request_remote_ymd_data(self, data):
        self.m_remote_connection.request_remote_ymd_data(data)

    def _request_files_exist(self, data):
        self.m_remote_connection.request_files_exist(data)

    def _remote_refresh(self, data):
        self.m_remote_connection.remote_refresh(data)

    def _remote_request_files(self, data):
        debug_print(data)

        selected_files = data.get("selected_files")
        url = data.get("url")
        source = self.m_config["source"]

        # this case should only come up when running on a local server
        # and using localhost
        if "localhost" in url.lower() or "127.0.0.1" in url:
            protocol, _, port = url.split(":")
            addresses = get_ip_addresses()
            if len(addresses) > 0:
                address = addresses[0]
                url = f"{protocol}://{address}:{port}"
            else:
                debug_print("Could not get ip address")
                return 


        if self.m_remote_connection.connected():
            msg = {
                "files": selected_files,
                "url": url,
                "source": source
            }

            debug_print(msg)
            self.m_remote_connection.remote_emit("remote_transfer_files", msg)

    def _remote_cancel_transfer(self, data):
        debug_print("enter")
        self.m_remote_connection.remote_emit("remote_cancel_transfer", {"source": self.m_config["source"]})
        pass

    def _server_transfer_files(self, data):
        debug_print("enter")
        self.m_remote_connection.server_transfer_files(data)

    ## actions 
    def send_node_data(self):        
        blocks = self.m_database.get_node_data_blocks()
        stats = self.m_database.get_run_stats()
        blocks_count = len(blocks)

        server_data = {
            "source": self.m_config["source"],
            "room": self.m_config["source"],
            "total": blocks_count,
            "stats": stats
        }

        if self.m_remote_connection.connected():
            try:
                self.m_remote_connection.remote_emit("remote_node_data", server_data)

                blocks_count = len(blocks)
                for i, block in enumerate(blocks):
                    msg = {
                        "source": self.m_config["source"],
                        "room": self.m_config["source"],
                        "total": blocks_count,
                        "block": block,
                        "id": i
                    }
                    debug_print(f"Sending block {i}")
                    self.m_remote_connection.remote_emit("remote_node_data_block", msg)
                    time.sleep(0.05)



            except socketio.exceptions.BadNamespaceError as e:
                debug_print("Bad namespace error")




class RemoteConnection:
    def __init__(self, config, parent:RemoteWorker) -> None:
        self.m_config = config 
        self.m_parent = parent
        self.m_node_source = config.get("source")
        self.m_server_address = None
        self.m_remote_source = None 

        self.m_send_offsets = {}
        # maps remote to local id
        self.m_upload_id_map = {}

        # maps local id to remote 
        self.m_rev_upload_id_map =  {}

        sio = self._create_client()
        self.m_remote_sio = sio

        @sio.event
        def connect():
            self._on_connect()

        @sio.event
        def disconnect():
            self._on_disconnect()

        @sio.event
        def dashboard_info(data):
            self._on_dashboard_info(data)

        @sio.event
        def server_data(data):
            self._on_server_data(data)

        @sio.event
        def server_ymd_data(data):
            self._on_server_ymd_data(data)

        @sio.event
        def node_data_block_rtn(data):
            self._on_node_data_block_rtn(data) 

        @sio.event
        def server_status_tqdm(data):
            self._on_server_status_tqdm(data)

        @sio.event
        def node_send(data):
            self._on_node_send(data)

        @sio.event
        def request_files_exist_rtn(data):
            self._on_request_files_exist_rtn(data)

        @sio.event
        def remote_cancel_transfer(data):
            debug_print(data)
            self._on_remote_cancel_transfer(data)

    def _on_connect(self):
        self.m_remote_sio.emit('join', { 'room': self.m_node_source, "type": "node" })
        self.m_upload_id_map = {}
        self.m_rev_upload_id_map = {}

    def _on_disconnect(self):
        msg = {"source": self.m_node_source, "address": self.m_server_address, "connected": False}
        self.send_to_all_local_dashboard("remote_connection", msg)
        self.m_parent.clear_remote_connection_address()
        self.send_to_all_local_dashboard("remote_data", {})
        self.m_parent.delete_remote_entries_for_source(self.m_remote_source)
        # self.m_parent.delete_remote_source(self.m_remote_source)
        pass 

    def _on_dashboard_info(self, data):
        self.m_remote_source = data.get("source")
        # self.m_parent.add_remote_source(self.m_remote_source)

        msg = {"source": self.m_node_source, "address": self.m_server_address, "connected": True}
        self.send_to_all_local_dashboard("remote_connection", msg)
        self.m_parent.set_remote_connection_address(self.m_server_address)

        # send our data as node information
        self.m_parent.send_node_data()

        # request data from server. 
        self.m_remote_sio.emit("request_server_data", {"room": self.m_node_source})
        pass 

    def _on_server_status_tqdm(self, data):
        debug_print(data)
        self.send_to_all_local_dashboard("server_status_tqdm", data)

    def _on_server_data(self, data):
        debug_print(f"Got server data")   
        room = "all_dashboards"
        self.m_parent.m_sio.emit("remote_data", data, to=room, debug=False) 

    def _on_server_ymd_data(self, data):
        # debug_print(data)
        room = data.get("for", "all_dashboards")

        msg = {
            "ymd": data.get("ymd", ""),
            "project": data.get("project", ""),
            "source": data.get("source", ""),
            "tab": data.get("tab", ""),
            "runs": {},
            "stats": data.get("stats", {})
        }

        names = []

        for run_name, run_entries in data.get("runs", {}).items():
            msg["runs"][run_name] = {}
            for rel_path, items in run_entries.items():
                msg["runs"][run_name][rel_path] = []
                for item in items:
                    assert(isinstance(item, dict))
                    upload_id = item["upload_id"]
                    item["project"] = data.get("project", "")

                    file = os.path.join(item["relpath"], item["basename"])
                    local_id =  get_upload_id(self.m_config["source"], data.get("project"), file) 
                    filepath = self.m_parent.get_file_path_from_entry(item)
                    item["localpath"] = filepath

                    self.m_parent.create_remote_entry(self.m_remote_source, local_id, item )
                    date = item["datetime"].split(" ")[0]

                    
                    self.m_upload_id_map[upload_id] = local_id 
                    self.m_rev_upload_id_map[local_id] = upload_id
                    # self.m_upload_id_map.get(upload_id, None)
                    item["upload_id"] = local_id
                    item["remote_upload_id"] = upload_id

                    # debug_print(f"adding  local_id: {self.m_remote_source} {local_id} -> {upload_id}")

                    filepath = self.m_parent.get_file_path_from_entry(item)
                    item["on_remote"] = True 
                    item["on_local"] =  os.path.exists(filepath)
                    if item["on_local"]:
                        try:
                            site = item.get("site")
                            if not site:
                                site = "default"
                            names.append((data.get("project"), os.path.join(date, site, item["robot_name"], file)))
                        except TypeError as e:
                            debug_print(item)
                            raise e 

                    tmp = filepath + ".tmp"
                    offset = 0
                    if os.path.exists(tmp):
                        offset = os.path.getsize(tmp)
                    item["offset"] = offset 

                    msg["runs"][run_name][rel_path].append(item)
                        


        self.m_parent.m_sio.emit("remote_ymd_data", data, to=room, debug=False)

        if len(names) >0:
            self.m_parent._submit_action("check_local_ids", {"names": names})

    def _on_node_data_block_rtn(self, data):
        debug_print("enter")
        entries = data["entries"]
        for entry in entries.values():
            upload_id = entry.get("remote_id")
            on_remote = entry.get("on_local")
            on_local = entry.get("on_remote")
            remote_id = entry.get("upload_id")

            self.m_upload_id_map[remote_id] = upload_id
            self.m_rev_upload_id_map[upload_id] = remote_id

            msg = {
                "on_local": on_local,
                "on_remote": on_remote,
                "upload_id": upload_id,
                "remote_id": remote_id,
                "fullpath": entry.get("fullpath")
            }
            self.m_parent.m_sio.emit("dashboard_file_server", msg)

    def server_transfer_files(self, data):
        # tell remote server to request these files from us. 
        debug_print(data)

        for uid in data["upload_ids"]:
            debug_print((uid, self.m_rev_upload_id_map.get(uid, "Not found")))

        ids = [ (self.m_rev_upload_id_map[uid], uid) for uid in data["upload_ids"] if uid in self.m_rev_upload_id_map ]

        msg = {
            "source": self.m_node_source,
            "upload_ids": ids
        }
        self.m_remote_sio.emit("transfer_node_files", msg)

    def _on_node_send(self, data):
        debug_print(data)
        # source = data.get("source").replace("NODE", "SRC")
        source = data.get("source")
        if source != self.m_config["source"]:
            return 
        files = data.get("files")

        url = "http://" + self.m_server_address
        msg = {
            "source": source,
            "files": files,
            "url": url
        }
        action = "remote_transfer_files"

        self.m_parent._submit_action(action, msg)


    def request_remote_ymd_data(self, data):        
        if self.connected():
            data["room"] = self.m_node_source
            data["data_for"] = dashboard_room(data)
            debug_print(f"room: {data['data_for']}")
            self.remote_emit("request_server_ymd_data", data)

    def request_files_exist(self, data):
        # debug_print(data)
        if self.connected():
            data["room"] = self.m_node_source
            data["data_for"] = dashboard_room(data)
            self.remote_emit("request_files_exist", data)

    def _on_request_files_exist_rtn(self, data):
        room = data.get("data_for")
        self.m_parent.m_sio.emit("request_files_exist_rtn", data, to=room)

    def _on_remote_cancel_transfer(self, data):
        source = data["source"]
        self.m_parent._submit_action("remote_cancel_transfer", data)

    def remote_refresh(self, data):
        if self.connected():
            self.m_remote_sio.emit("request_server_data", {"room": self.m_node_source})

    def _create_client(self):
        sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,  # Infinite attempts
            reconnection_delay=1,  # Start with 1 second delay
            reconnection_delay_max=5,  # Maximum 5 seconds delay
            randomization_factor=0.5,  # Randomize delays by +/- 50%
            logger=False,  # Enable logging for debugging
            engineio_logger=False  # Enable Engine.IO logging
        )
        return sio 

    def remote_emit(self, event, data=None):
        self.m_remote_sio.emit(event=event, data=data)

    def send_to_all_local_dashboard(self, event, data=None):
        self.m_parent.m_sio.emit(event, data, to="all_dashboards", debug=False)

    def connected(self) -> bool:
        return self.m_remote_sio.connected
    
    def disconnect(self):
        if self.m_remote_sio.connected:
            self.m_remote_sio.disconnect()

    def connect(self, server_address):
        api_key_token = self.m_config["API_KEY_TOKEN"]
        headers = {"X-Api-Key": api_key_token }

        self.m_server_address = None
        try:
            self.send_to_all_local_dashboard("server_link_status", {"server": server_address, "msg": f"Testing <b>{server_address}</b>"})

            server, port = server_address.split(":")
            port = int(port)
            debug_print(f"Testing to {server}:{port}")
            socket.create_connection((server, port))

            self.m_remote_sio.connect(f"http://{server}:{port}/socket.io", headers=headers, transports=['websocket'])
            self.m_server_address = server_address
            self.send_to_all_local_dashboard("server_link_status", {"server": server_address, "msg":""})

        except socket.error as e:
            debug_print(f"Got socket error: {e}")
            

        except socketio.exceptions.ConnectionError as e:
            debug_print(f"Ah-Ah-Ahh, invalid key. {e}")

            self.send_to_all_local_dashboard("server_invalid_key", {"key": api_key_token, "server": server_address})

        except Exception as e:
            if self.m_verbose:
                debug_print(e)
            self.send_to_all_local_dashboard("server_link_status", {"server": server_address, "msg": f"Failed to connect to <b>{server_address}</b>: <i>{e}</i>", "timeout": 2.5})
