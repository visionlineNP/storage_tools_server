from datetime import datetime, timedelta
import hashlib
import json
import math
import secrets
import shutil
from threading import Lock, Thread
import time
from flask import flash, g, jsonify, make_response, redirect, render_template, request, send_from_directory, session, url_for 
from flask_socketio import disconnect, join_room, SocketIO
from zeroconf import NonUniqueNameException, ServiceInfo, Zeroconf 
import jwt 
import os
import socket 
import urllib
import uuid
import yaml
import humanfriendly as hf 
import redis


from .debug_print import debug_print
from .utils import dashboard_room, get_datatype, get_ip_addresses, get_source_by_mac_address
from .database import Database, get_upload_id
from .remoteConnection import RemoteConnection
from .nodeConnection import NodeConnection


class Server:
    def __init__(self, socketio:SocketIO) -> None:
        self.m_sio = socketio
        self.m_id = os.getpid()

        self.redis = redis.StrictRedis(host='redis', port=6379, db=0)
        # always start with a clean slate
        self.redis.flushall()
        self.pubsub = self.redis.pubsub()
        self._start_pubsub_listener()


        self.m_secret_key = uuid.uuid4()

        self.m_config = {}

        # keeps track of which devices are connected.
        self.m_sources = {"devices": [], "nodes": [], "report_host": [], "report_node": []}
        self.sources_set_key = 'connected_sources'  

        # maps source to upload_id to file entry for files on device
        self.m_remote_entries = {}

        # to lock the entries
        self.m_remote_entries_lock = {}

        # buffer of source to entries.  
        self.m_remote_entries_buffer = {}

        # maps source to node data for files on remote nodes (other servers)
        self.m_node_entries = {}

        # used to pull data from a node
        self.m_node_connections = {}

        # tracks the remote device and node sockets
        # so we can know when they disconnect
        # maps source name to sid
        self.m_remote_sockets = {}

        # which files to operate on the device
        # maps source to list of files on the device
        self.m_selected_files = {}

        # flag set to do action
        # maps source name to bool
        self.m_selected_files_ready = {}

        # which action to do.  [send, delete, cancel]
        # maps source name to action
        self.m_selected_action = {}

        # how much space is left on each device.
        self.m_fs_info = {}

        # maps source to project
        self.m_projects = {}

        # report node information
        # maps source -> { threads: int, }
        self.m_report_node_info = {}

        # Store uploaded files in this directory
        self.m_upload_dir = None

        # stub for a real database.
        self.m_database = None

        # associate a session_token with dict of state
        # if a source has been updated since last send, set state to true
        # otherwise is set to false. 
        self.m_has_updates = {}

        # connects a room to a session token. 
        self.m_session_tokens = {}

        # dashboard clients
        # when we need to send something to every dashboard.  
        self.m_dashboard_rooms = []

        # used by on_device_status to keep track of source -> msg
        self.m_ui_status = {}

        # search results
        self.m_search_results = {}

        self.m_volume_map_filename = os.environ.get("VOLUME_MAP", "config/volumeMap.yaml")
        self.m_keys_filename = os.environ.get("KEYSFILE", "config/keys.yaml")


        self._load_config()
        self._load_keys()

        self.m_remote_connection = RemoteConnection(self.m_config, socketio, self.m_database, self)

        self.m_zeroconf = Zeroconf()
        self._setup_zeroconf()

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
    
            self.m_config["volume_map"] = volume_map.get("volume_map", [])
            self.m_config["source"] = get_source_by_mac_address() + "_" + str(self.m_config["port"])
            debug_print(f"Setting source name to {self.m_config['source']}")

            self.m_upload_dir = self.m_config["upload_dir"]
            os.makedirs(self.m_upload_dir, exist_ok=True)

            v_root = self.m_config.get("volume_root", "/")
            v_map = self.m_config.get("volume_map", {}).copy()
            for name in v_map:
                v_map[ name ] = os.path.join(v_root,  v_map.get(name, "").strip("/"))
            
            blackout = self.m_config.get("blackout", [])

            self.m_database = Database(self.m_upload_dir, self.m_config["source"], v_map, blackout)
            self.m_database.estimate_runs()

        # self.m_database.regenerate()
        # # this is optional. We can preload projects, sites, and robots
        # # based on the config.
            for project_name in sorted(self.m_config.get("volume_map", [])):
                self.m_database.add_project(project_name, "")

            for robot_name in self.m_config.get("robots", []):
                self.m_database.add_robot_name(robot_name, "")

            for site_name in self.m_config.get("sites", []):
                self.m_database.add_site(site_name, "")

    def _load_keys(self):
        if os.path.exists(self.m_keys_filename):
            with open(self.m_keys_filename, "r") as f:
                keys = yaml.safe_load(f)
                self.m_config["keys"] = keys["keys"]
                self.m_config["API_KEY_TOKEN"] = keys.get("API_KEY_TOKEN", None)

    def _setup_zeroconf(self):
        this_claimed = self.redis.set("zero_conf", "claimed",  nx=True, ex=5)
        if not this_claimed:
            debug_print(f"{self.m_id}:  zero conf already claimed")
            return 

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

    def _get_dirroot(self, project:str) -> str:
        root = self.m_config.get("volume_root", "/")
        volume = self.m_config["volume_map"].get(project, "").strip("/")
        # debug_print((root, project, volume))
        return os.path.join(root, volume)

    def _get_file_path_from_entry(self, entry:dict) -> str:
        project = entry.get("project")

        root = self.m_config.get("volume_root", "/")
        volume = self.m_config["volume_map"].get(project, "").strip("/")

        relpath = entry["relpath"]
        filename = entry["basename"]
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


        try:
            filedir = os.path.join(root, volume, date, site, robot_name, relpath)
        except TypeError as e:
            debug_print((root, volume, date,relpath))
            raise e

        filepath = os.path.join(filedir, filename)

        return filepath

    def _get_file_path(self, source: str, upload_id: str) -> str:
        """
        Returns the full path of a file based on the source and upload_id.

        Parameters:
        source (str): The source of the file.
        upload_id (str): The unique identifier for the file.

        Returns:
        str: The full path of the file.
        """
        # entry = self.m_remote_entries[source][upload_id]
        entry = self.fetch_remote_entry(source, upload_id)
        return self._get_file_path_from_entry(entry)

    def _get_rel_dir(self, source: str, upload_id: str) -> str:
        entry = self.fetch_remote_entry(source, upload_id)

        project = entry.get("project", None)
        project = project if project else "None"
        date = entry["datetime"].split()[0]

        relpath = entry["relpath"]
        filename = entry["basename"]
        try:
            reldir = os.path.join(project, date, relpath)
        except TypeError as e:
            debug_print((project, date, relpath))
            raise e

        reldir = os.path.join(reldir, filename)

        return reldir

    def _start_pubsub_listener(self):
        # Start a thread to listen for changes on the resync channel
        def listen():
            for message in self.pubsub.listen():
                if message['type'] == 'message':
                    channel = message["channel"].decode("utf-8")
                    debug_print(channel)

                    data = json.loads(message['data'])
                    if channel == "resync_remote_entries":
                        source = data['source']
                        upload_id = data['upload_id']
                        self.sync_remote_entry(source, upload_id)
                    elif channel == "node_data":
                        self._process_node_data(data)
                    elif channel == "node_data_block":
                        self._process_node_data_block(data)

        self.pubsub.subscribe('resync_remote_entries', 
                              'node_data', 
                              "node_data_block"
                              ) 
        listener_thread = Thread(target=listen)
        listener_thread.daemon = True
        listener_thread.start()

    def create_remote_entry(self, source, upload_id, entry):
        # debug_print((source, upload_id))
            
        # Serialize the entry as a JSON string and store it in Redis
        entry_json = json.dumps(entry)
        self.redis.set(f'remote_entries:{source}:{upload_id}', entry_json)
        # debug_print(f"added remote_entries:{source}:{upload_id}")

        # # Publish a message to other workers that this entry has been created
        # self.redis.publish('resync_remote_entries', json.dumps({'source': source, 'upload_id': upload_id}))

    def fetch_remote_entry(self, source, upload_id):
        # Fetch the entry from Redis
        entry_json = self.redis.get(f'remote_entries:{source}:{upload_id}')
        if entry_json:
            return json.loads(entry_json)
        return None

    def update_remote_entry(self, source, upload_id, updated_entry):
        # Fetch and update the entry in Redis

        if not "start_datetime" in updated_entry:
            debug_print(f"Skipping {updated_entry}")

        entry_json = json.dumps(updated_entry)
        self.redis.set(f'remote_entries:{source}:{upload_id}', entry_json)

        # Publish a message to notify other workers about the update
        self.redis.publish('resync_remote_entries', json.dumps({'source': source, 'upload_id': upload_id}))

    def sync_remote_entry(self, source, upload_id):
        pass 
        # # Fetch the updated entry from Redis and sync the local cache if needed
        # entry_json = self.redis.get(f'remote_entries:{source}:{upload_id}')
        # if entry_json:
        #     print(f"Synced entry from Redis: {source}, {upload_id}")
        #     # Here you can add logic to sync the local cache if you maintain one

    def delete_remote_entry(self, source, upload_id):
        # Delete the entry from Redis
        self.redis.delete(f'remote_entries:{source}:{upload_id}')

        # Publish a message to notify other workers about the deletion
        self.redis.publish('resync_remote_entries', json.dumps({'source': source, 'upload_id': upload_id}))

    def get_all_entries_for_source(self, source):
        # debug_print(f"enter {source}")
        # Fetch all entries for a specific source
        keys = self.redis.keys(f'remote_entries:{source}:*')
        entries = {}
        for key in keys:
            upload_id = key.decode('utf-8').split(':')[-1]
            entry_json = self.redis.get(key)
            if entry_json:
                entries[upload_id] = json.loads(entry_json)
        return entries
    
    def delete_remote_entries_for_source(self, source):
        cursor = '0'
        while cursor != 0:
            cursor, keys = self.redis.scan(cursor=cursor, match=f'remote_entries:{source}:*')
            if keys:
                # Delete the matching keys
                self.redis.delete(*keys)    

    def dashboard_add_room(self, room):
        debug_print(f"added {room}")
        self.redis.sadd("dashboard_rooms", room)

    def dashboard_remove_room(self, room):
        self.redis.srem("dashboard_rooms", room)

    def dashboard_get_rooms(self):
        rooms = self.redis.smembers("dashboard_rooms")
        return [room.decode("utf-8") for room in rooms]

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
          source_type: which type of source. One of [devices, nodes]
        """
        sources = self.redis.smembers(f"{self.sources_set_key}:{source_type}")
        return [source.decode("utf-8") for source in sources]

    def device_set_project(self, source, project):
        self.redis.set(f'device_project:{source}', project)

    def device_get_project(self, source):
        project = self.redis.get(f'device_project:{source}')
        if project:
            return project.decode("utf-8")
        return None

    def device_remove_project(self, source):
        keys = self.redis.keys(f'device_project:{source}') 
        if keys:
            self.redis.delete(*keys)

    def _device_revise_stats(self):
        stats = {}
        sources = self.get_sources("devices")

        for source in sources:

            stats[source] = {
                "total_size": 0,
                "count": 0,
                "start_datetime": None,
                "end_datetime": None,
                "datatype": {},
                "on_server_size": 0,
                "on_server_count": 0,
            }

            entries = self.get_all_entries_for_source(source)
            for entry in entries.values():
                self._update_stat_for_entry(entry, stats[source])

    def _update_stat_for_entry(self, entry, stat):
        filename = self._get_file_path_from_entry(entry)
        on_server = os.path.exists(filename)

        size = entry["size"]
        start_time = entry["start_datetime"]
        end_time = entry["end_datetime"]
        datatype = entry["datatype"]


        stat["total_size"] += size
        stat["htotal_size"] = hf.format_size(stat["total_size"])
        stat["count"] += 1

        if on_server:
            stat["on_server_size"] += size
            stat["on_server_count"] += 1

        stat["on_server_hsize"] = hf.format_size(stat["on_server_size"])

        if stat["start_datetime"]:
            stat["start_datetime"] = min(start_time, stat["start_datetime"])
        else:
            stat["start_datetime"] = start_time

        if stat["end_datetime"]:
            stat["end_datetime"] = max(end_time, stat["end_datetime"])
        else:
            stat["end_datetime"] = end_time

        duration = datetime.strptime(
            stat["end_datetime"], "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(stat["start_datetime"], "%Y-%m-%d %H:%M:%S")
        assert isinstance(duration, timedelta)
        stat["duration"] = duration.seconds
        stat["hduration"] = hf.format_timespan(duration.seconds)

        stat["datatype"][datatype] = stat["datatype"].get(
            datatype,
            {"total_size": 0, "count": 0, "on_server_size": 0, "on_server_count": 0},
        )
        stat["datatype"][datatype]["total_size"] += size
        stat["datatype"][datatype]["htotal_size"] = hf.format_size(
            stat["datatype"][datatype]["total_size"]
        )
        stat["datatype"][datatype]["count"] += 1

        if on_server:
            stat["datatype"][datatype]["on_server_size"] += size
            stat["datatype"][datatype]["on_server_count"] += 1
        stat["datatype"][datatype]["on_server_hsize"] = hf.format_size(
            stat["datatype"][datatype]["on_server_size"]
        )

    def _update_stat(self, source, uid, stat):
        entry = self.fetch_remote_entry(source, uid)
        if entry:
            self._update_stat_for_entry(entry, stat)
        else: 
            debug_print(f"Did not find {source} {uid}")

    def _emit_server_ymd_data(self, datasets, stats, project, ymd, tab, room):
        """Background task to emit data incrementally."""
        total = len(datasets)

        for i, data in enumerate(datasets):
            server_data = {
                "total": total,
                "index": i,
                "runs": data,
                "stats": stats,
                "source": self.m_config["source"],
                "project": project,
                "ymd": ymd,
                "tab": tab
            }

            # Emit the data to the client
            debug_print(f"Sending {project} {ymd} {room}")
            self.m_sio.emit("server_ymd_data", server_data, to=room)
        # debug_print("Done")

    def _emit_device_ymd_data(self, datasets, stats, source, ymd, tab, room):
        if datasets is None:
            return 
        
        total = len(datasets)
        for i, data in enumerate(datasets):
            device_data = {
                "total": total,
                "index": i,
                "reldir": data,
                "stats": stats,
                "source": self.m_config["source"],
                "device_source": source,
                "ymd": ymd,
                "tab": tab
            }
            self.m_sio.emit("device_ymd_data", device_data, to=room)



    def _send_dashboard_file(self, msg):
        self._send_to_all_dashboards("dashboard_file", msg, with_nodes=True)

    def _send_to_all_dashboards(self, event, msg, with_nodes:bool=False):
        rooms = []
        # rooms.extend(self.m_dashboard_rooms)
        rooms.extend(self.dashboard_get_rooms())
        if with_nodes:
            nodes = self.get_sources("nodes")
            rooms.extend(nodes)

        debug_print(f"rooms: {rooms}")

        for room in rooms:
            self.m_sio.emit(event, msg, to=room)

    def _update_fs_info(self):
        source = self.m_config["source"]

        # todo: update this to use volume map

        dev = os.stat(self.m_upload_dir).st_dev
        total, used, free = shutil.disk_usage(self.m_upload_dir)
        free_percentage = (free / total) * 100
        self.m_fs_info[source] = {dev: (self.m_upload_dir, f"{free_percentage:0.2f}")}

    def _validate_api_key_token(self, api_key_token):
        # this should be more secure
        # for now we will just look up the key
        return api_key_token in self.m_config["keys"]

    def _validate_user_credentials(self, username, password):
        # debug_print((username, password))
        # Placeholder function to validate credentials
        return username == "admin" and password == "NodeNodeDevices"

    def on_connect(self):
        """
        Handles a new client connection to the server.

        This function is called when a new WebSocket connection is established. It checks the connection request
        for session tokens, username, API key, or authorization headers and validates the credentials.
        If the credentials are invalid, it raises a `ConnectionRefusedError` to reject the connection.

        Steps:
        1. Retrieves the `session_token` from the query arguments and assigns it to the `g` object for global access.
        2. Retrieves the `username` from the query arguments. If not provided, it checks for the `X-Authenticated-User` 
        header (e.g., if an external authentication system is in place).
        3. Logs the `username` for debugging purposes.
        4. Checks for an API key in the `X-Api-Key` header:
        - If an API key is provided, the function validates it using the `_validate_api_key_token` method.
        - If the key is valid, the connection proceeds.
        - If the key is invalid, the connection is rejected with a `ConnectionRefusedError`.
        5. If no API key is present, it checks for an `Authorization` header:
        - If the authorization type is "Bearer", it extracts the token and validates it.
            - If the token is valid, the connection proceeds, and the token is stored in the session.
            - If invalid, the connection is rejected with a `ConnectionRefusedError`.
        - If the authorization type is "Basic", it extracts the username from the `X-Authenticated-User` header 
            (for Basic authentication, typically handled by Nginx with LDAP authentication).
        - For other unsupported authorization types, the connection is disconnected.
        
        Raises:
            ConnectionRefusedError: If the API key or token is invalid, the connection is refused.

        """
        debug_print(f"session id: {request.sid}")

        g.session_token = request.args.get("session_token")

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

    def on_disconnect(self):
        """
        Handles the disconnection of a client from the server.

        This function is called when a WebSocket client disconnects. It identifies the source associated with
        the disconnected session ID, cleans up any data structures related to the source, and removes the source 
        from various internal tracking dictionaries and lists.

        Steps:
        1. Logs the session ID of the disconnecting client for debugging purposes.
        2. Iterates through the `m_remote_sockets` dictionary, which maps sources to session IDs, to find 
        the source that matches the current session ID.
        3. If a source is found (i.e., `remove` is set), the following cleanup actions are performed:
        - Removes the source from `m_remote_entries`, `m_remote_sockets`, and `m_node_entries` if it exists in them.
        - If the source is present in `m_sources["devices"]`, it is removed, and the device data is updated by calling `_send_device_data()`.
        - If the source is present in `m_sources["nodes"]`, it is removed, and the node data is updated by calling `_send_node_data()`.
        - Removes the source from `m_dashboard_rooms` if it exists.
        - If the source has a session token in `m_session_tokens`, the token and any associated updates in `m_has_updates` 
            are deleted, along with the source's session token entry.
        - Removes the source from `m_search_results` and `m_node_connections` if present.
        4. After completing the cleanup, logs that the disconnect has been processed for the given source.

        Note:
        - The method primarily cleans up references to the disconnected source to free up resources and maintain 
        consistency across the server's internal data structures.
        - If any data structure or connection is missed during cleanup, it could lead to memory leaks or stale state.

        Args:
            None. This method works with the current request context (i.e., `request.sid`).

        Debugging:
        - Logs key actions and the session ID to assist with troubleshooting disconnection issues.
        """

        debug_print(f"session id: {request.sid}")

        remove = None
        for source, sid in self.m_remote_sockets.items():
            if sid == request.sid:
                remove = source
                break

        if remove:
            debug_print(f"--- remove {remove}")

            if remove in self.m_remote_entries:
                del self.m_remote_entries[remove]
            if remove in self.m_remote_sockets:
                del self.m_remote_sockets[remove]
            if remove in self.m_node_entries:
                del self.m_node_entries[remove]
            if remove in self.m_sources["devices"]:
                self.m_sources["devices"].pop(self.m_sources["devices"].index(remove))
                self.delete_source(remove, "devices")
                self.device_remove_project(remove)
                self._send_device_data()

            if remove in self.m_sources["nodes"]:
                self.m_sources["nodes"].pop(self.m_sources["nodes"].index(remove))
                self._send_node_data()

            if remove in self.m_dashboard_rooms:
                self.m_dashboard_rooms.pop(self.m_dashboard_rooms.index(remove))
            self.dashboard_remove_room(remove)

            if remove in self.m_session_tokens:
                session_token = self.m_session_tokens[remove]
                if session_token in self.m_has_updates:
                    del self.m_has_updates[session_token]
                del self.m_session_tokens[remove]

            if remove in self.m_search_results:
                del self.m_search_results[remove]

            if remove in self.m_node_connections:
                del self.m_node_connections[remove]

            self.delete_remote_entries_for_source(remove)


            debug_print(f"Got disconnect: {remove}")

    def on_join(self, data: dict):
        """
        Handles a client joining a room.

        This function is called when a client sends a request to join a specific room. It handles various client types
        (e.g., "device", "dashboard", "node") and performs specific actions based on the type of client that is joining.
        Additionally, it ensures that duplicate device connections are rejected and broadcasts a message to the room
        upon a successful join.

        Args:
            data (dict): A dictionary containing the room to join and an optional 'type' key that defines the type
                        of client ("device", "dashboard", or "node"). Other optional fields like 'session_token'
                        may also be present for specific client types.

        Steps:
        1. Extracts the `room` from the `data` dictionary, which defines which room the client is trying to join.
        2. Extracts the `type` of client (e.g., "device", "dashboard", or "node"). If `type` is not provided, it defaults to `None`.
        
        3. **Device Connection**:
            - If the client is a "device" and there is already a device connected to the same room (tracked in `m_remote_sockets`), 
            the new connection is rejected by calling `disconnect()` with the current session ID (`request.sid`).
            - This ensures that only one device can connect to a room at a time.
        
        4. **Joining the Room**:
            - If there is no conflict or if the client is not a device, the client is allowed to join the room by calling `join_room(room)`.
            - The server sends a message to the room broadcasting that the client has successfully joined, using `self.m_sio.emit()`.
            - The current session ID (`request.sid`) is stored in `m_remote_sockets` for tracking purposes.
        
        5. **Dashboard Connection**:
            - If the client is a "dashboard", the room is added to `m_dashboard_rooms` if it's not already present.
            - A session token is extracted from the `data`, and the session token is associated with the room in `m_session_tokens`.
            - The `m_has_updates` dictionary is updated to track any updates that the dashboard has received for the session.
            - Finally, the server sends all relevant data to the dashboard by calling `self._send_all_data()`.
        
        6. **Node Connection**:
            - If the client is a "node", a new `NodeConnection` instance is created for the room, using the server's configuration (`self.m_config`)
            and the SocketIO instance (`self.m_sio`), and it is stored in `m_node_connections`.

        Debugging:
        - Logs the room and the type of client joining for debugging purposes.
        - Logs rejection of duplicate device connections to help troubleshoot device connection issues.
        
        Raises:
            None. The function handles disconnections and emits messages within the WebSocket context.

        Note:
        - The function differentiates between client types to handle rooms appropriately. Each type of client has different
        responsibilities (e.g., devices are tracked uniquely, dashboards receive full data, nodes manage connections).
        - The function manages the data structure `m_remote_sockets` to ensure that rooms and their connections are tracked efficiently.
        """

        debug_print((data, self.m_id))

        room = data["room"]    
        client = data.get("type", None)

        if client == "device" and room in self.m_remote_sockets:
            # we have a duplicate connection. reject this and hold on to the current
            debug_print("found duplicate socket for device!")
            # disconnect(request.sid)
            return 

        join_room(room)
        self.m_sio.emit("dashboard_info", {"data": f"Joined room: {room}", "source": self.m_config["source"]}, to=room)
        debug_print(f"Joined room {room} from {client}")
        self.m_remote_sockets[room] = request.sid

        if client == "dashboard":
            if room not in self.m_dashboard_rooms:
                self.m_dashboard_rooms.append(room)
            self.dashboard_add_room(room)

            session_token = data.get("session_token")

            self.m_session_tokens[room] = session_token
            # used to keep track of updated sources, and who knows what. 
            self.m_has_updates[session_token] = {}

            self._send_all_data({"session_token": session_token})

        if client == "node":
            self.m_node_connections[room] = NodeConnection(self.m_config, self.m_sio, self.m_database)

        if client == "device":
            self.add_source(room, "devices")

    def on_leave(self, data:dict):
        debug_print(data)
        pass 



    def on_remote_node_data(self, data):
        debug_print("enter --- ")
        self.redis.publish("node_data", json.dumps(data))

    def on_remote_node_data_block(self, data):
        debug_print("enter ------")
        self.redis.publish("node_data_block", json.dumps(data))

    def _process_node_data(self, data):
        source= data.get("source")
        stats = data.get("stats")

        # self.m_remote_node_expect[source] = total
        self.m_remote_entries[source] = {}
        self.m_node_entries[source] = {
            "stats": stats,
            "entries": {}
        }

    def _process_node_data_block(self, data):
        """ Recevie node data from remote source.  """
        source = data.get("source")
        entries = data.get("block")
        id = data.get("id")
        total = data.get("total")

        rtn = {}

        for entry in entries:
            relpath = entry["relpath"]
            orig_id = entry["upload_id"] 
            entry["remote_id"] = orig_id
            project = entry["project"]
            run_name = entry["run_name"]
            ymd = entry["datetime"].split(" ")[0]

            entry["hsize"] = hf.format_size(entry["size"])
            
            file = os.path.join(relpath, entry["basename"])
            upload_id = get_upload_id(self.m_config["source"], project, file)
            entry["upload_id"] = upload_id
            self.m_remote_entries[source][upload_id] = entry

            filepath = self._get_file_path_from_entry(entry)

            entry["on_local"] = False 
            entry["on_remote"] = True

            if os.path.exists(filepath):
                self.m_remote_entries[source][upload_id]["on_server"] = True
                entry["on_local"] = True

            if os.path.exists(filepath + ".tmp"):
                self.m_remote_entries[source][upload_id]["temp_size"] = (
                    os.path.getsize(filepath + ".tmp")
                )
            else:
                self.m_remote_entries[source][upload_id]["temp_size"] = 0

            rtn[upload_id] = entry

            self.m_node_entries[source]["entries"][project] = self.m_node_entries[source]["entries"].get(project, {})
            self.m_node_entries[source]["entries"][project][ymd] = self.m_node_entries[source]["entries"][project].get(ymd, {})
            self.m_node_entries[source]["entries"][project][ymd][run_name] = self.m_node_entries[source]["entries"][project][ymd].get(run_name, {})
            self.m_node_entries[source]["entries"][project][ymd][run_name][relpath] = self.m_node_entries[source]["entries"][project][ymd][run_name].get(relpath, [])
            self.m_node_entries[source]["entries"][project][ymd][run_name][relpath].append(entry)

            self.create_remote_entry(source, upload_id, entry)

        msg = {"entries": rtn}

        # debug_print(f"emit rtn to {source}")
        self.m_sio.emit("node_data_block_rtn", msg, to=source)

        if id == (total-1):
            self._send_node_data()

    def _send_all_data(self, data):
        self._send_device_data(data)
        self._send_node_data(data)
        self._send_server_data(data)
        self.on_request_projects(data)
        self.on_request_robots(data)
        self.on_request_sites(data)
        self.on_request_keys(data)
        self.on_request_search_filters(data)
        debug_print("Sent all data")

        # after this, there should be no new data!
        room = dashboard_room(data)
        self.m_sio.emit("has_new_data", {"value": False}, to=room)

    def on_request_new_data(self, data):
        session_token = data.get("session_token","")
        if session_token in self.m_has_updates:
            # we can be more fine tuned later. now just push everything
            self._send_all_data(data)

    def _create_node_data_stub(self):
        rtn = {}

        for source_name, source_items in self.m_node_entries.items():
            rtn[source_name] = {}
            for project_name, project_items in source_items.get("entries", {}).items():
                rtn[source_name][project_name] = {}
                for ymd in sorted(project_items):
                    rtn[source_name][project_name][ymd] = {}
        # debug_print(rtn)
        return rtn 

    def _send_node_data(self, msg=None):
        node_data = {
            "entries": self._create_node_data_stub(),
            "fs_info": {}
            }

        if msg:
            room = dashboard_room(msg)

            if room in self.m_session_tokens:
                session_token = self.m_session_tokens[room]
                for source in node_data:
                    self.m_has_updates[session_token][source] = False

            self.m_sio.emit("node_data", node_data, to=room)
        else:
            for session_token in self.m_has_updates:
                for source in node_data:
                    self.m_has_updates[session_token][source] = False

            self._send_to_all_dashboards("node_data", node_data, with_nodes=False)



    def on_request_node_ymd_data(self, data):
        tab = data.get("tab")
        names = tab.split(":")
        _, source, project, ymd = names

        source_data = self.m_node_entries.get(source, {})
        runs= source_data.get("entries", {}).get(project, {}).get(ymd, [])
        stats_data = source_data.get("stats", {}).get(project).get(ymd, {})

        msg = {
            "tab": tab,
            "runs": runs,
            "stats": stats_data,
            "source": source,  
            "project": project,
            "ymd": ymd
        }
        self.m_sio.emit("node_ymd_data", msg, to=dashboard_room(data))

    def _get_device_data_stats(self):
        device_data = {}
        
        sources = self.get_sources("devices")
        for source in sources:                
            # project = self.m_projects.get(source)
            project = self.device_get_project(source)
            device_data[source] = {"fs_info": {}, "entries": {}, "project": project}

            if source in self.m_fs_info:
                device_data[source]["fs_info"] = self.m_fs_info[source]
            entries = self.get_all_entries_for_source(source)
            for remote_entry in entries.values():
                uid = remote_entry["upload_id"]
                entry = {}
                for key in ["size", "site", "robot_name", "upload_id", "on_device", "on_server", "basename", "datetime", "topics" ]:
                    entry[key] = remote_entry[key]

                entry["size"] = hf.format_size(entry["size"])
                date = remote_entry["datetime"].split(" ")[0]

                device_data[source]["stats"] = device_data[source].get(
                    "stats",
                    {
                        "total": {
                            "total_size": 0,
                            "count": 0,
                            "start_datetime": None,
                            "end_datetime": None,
                            "datatype": {},
                            "on_server_size": 0,
                            "on_server_count": 0,
                        }
                    },
                )
                device_data[source]["stats"][date] = device_data[source]["stats"].get(
                    date,
                    {
                        "total_size": 0,
                        "count": 0,
                        "start_datetime": None,
                        "end_datetime": None,
                        "datatype": {},
                        "on_server_size": 0,
                        "on_server_count": 0,
                    },
                )

                self._update_stat(source, uid, device_data[source]["stats"][date])
                self._update_stat(source, uid, device_data[source]["stats"]["total"])

        return device_data
    
    def _get_device_data_stats_by_source_ymd(self, source, ymd):
        device_data = {}
        
        sources = self.get_sources("devices")
        for source in sources:                
            # project = self.m_projects.get(source)
            project = self.device_get_project(source)
            device_data[source] = {"fs_info": {}, "entries": {}, "project": project}

            if source in self.m_fs_info:
                device_data[source]["fs_info"] = self.m_fs_info[source]
            entries = self.get_all_entries_for_source(source)
            for remote_entry in entries.values():
                uid = remote_entry["upload_id"]
                date = remote_entry["datetime"].split(" ")[0]
                if date != ymd:
                    continue
                entry = {}
                for key in ["size", "site", "robot_name", "upload_id", "on_device", "on_server", "basename", "datetime", "topics" ]:
                    entry[key] = remote_entry[key]

                entry["size"] = hf.format_size(entry["size"])

                device_data[source]["stats"] = device_data[source].get(
                    "stats",
                    {
                        "total": {
                            "total_size": 0,
                            "count": 0,
                            "start_datetime": None,
                            "end_datetime": None,
                            "datatype": {},
                            "on_server_size": 0,
                            "on_server_count": 0,
                        }
                    },
                )
                device_data[source]["stats"][date] = device_data[source]["stats"].get(
                    date,
                    {
                        "total_size": 0,
                        "count": 0,
                        "start_datetime": None,
                        "end_datetime": None,
                        "datatype": {},
                        "on_server_size": 0,
                        "on_server_count": 0,
                    },
                )

                self._update_stat(source, uid, device_data[source]["stats"][date])
                self._update_stat(source, uid, device_data[source]["stats"]["total"])

        return device_data



    def _get_device_data_ymd_stub(self):
        # debug_print("enter")
        device_data = {}
        count = 0

        sources = self.get_sources("devices")
        for source in sources:
            # project = self.m_projects.get(source)
            project = self.device_get_project(source)
            # debug_print(f" project for {source} is {project}, {self.m_id}")
            device_data[source] = {"fs_info": {}, "entries": {}, "project": project}
            if source in self.m_fs_info:
                device_data[source]["fs_info"] = self.m_fs_info[source]

            entries = self.get_all_entries_for_source(source)
            for entry in entries.values():
                count += 1

                data_entry = {}
                for key in ["size", "site", "robot_name", "upload_id", "on_device", "on_server", "basename", "datetime", "topics" ]:
                    data_entry[key] = entry[key]

                    data_entry["size"] = hf.format_size(entry["size"])
                    date = entry["datetime"].split(" ")[0]
                    relpath = entry["relpath"]
                    device_data[source]["entries"][date] = device_data[source]["entries"].get(date, {})
                    device_data[source]["entries"][date][relpath] = device_data[source]["entries"][date].get(relpath, [])
        
        # debug_print(f"count {count}")
        return device_data

    def _get_send_device_data_ymd_data(self, source:str, ymd:str):
        rtnarr = []
        rtn = {}
        # will send up to max count entries per packet
        max_count = 50
        count = 0 
        
        entries = self.get_all_entries_for_source(source)
        if len(entries) == 0:
            debug_print(f"Source: {source} missing")
            return 

        for remote_entry in entries.values():
            date = remote_entry["datetime"].split(" ")[0]
            if date != ymd:
                continue

            entry = {}
            for key in ["size", "site", "robot_name", "upload_id", "on_device", "on_server", "basename", "datetime", "topics" ]:
                entry[key] = remote_entry[key]

            entry["size"] = hf.format_size(remote_entry["size"])
            relpath = remote_entry["relpath"]

            rtn[relpath] = rtn.get(relpath, [])
            rtn[relpath].append(entry)

            count += 1
            if count >= max_count:
                rtnarr.append(rtn)
                rtn = {}
                count = 0

        rtnarr.append(rtn)

        return rtnarr 


    def _send_device_data(self, data=None):
        # debug_print("enter")
        device_data = self._get_device_data_ymd_stub()    

        stats = self._get_device_data_stats()
        for source in device_data:
            if "stats" in stats[source]:
                device_data[source]["stats"] = stats[source]["stats"]

            # revise the has_updates  
            for session_token in self.m_has_updates:
                self.m_has_updates[session_token][source] = False

        # debug_print(device_data)
        self._send_to_all_dashboards("device_data", device_data)    
        # debug_print("exit")



    def _send_server_data(self, msg=None):
        data = self.m_database.get_send_data_ymd_stub()

        stats = self.m_database.get_run_stats()
        self._update_fs_info()

        server_data = {
            "entries": data,
            "fs_info": self.m_fs_info[self.m_config["source"]],
            "stats": stats,
            "source": self.m_config["source"],
            "remotes": self.m_config.get("remote", []),
            "remote_connected": self.m_remote_connection.connected(),
            "remote_address": self.m_remote_connection.server_name()
        }

        if msg:
            room = dashboard_room(msg)

            if room in self.m_session_tokens:
                session_token = self.m_session_tokens[room]
                self.m_has_updates[session_token][self.m_config["source"]] = False

            debug_print(f"sending to {room}")   
            # debug_print(server_data)     
            self.m_sio.emit("server_data", server_data, to=room)
        else:
            debug_print("Sending to all dashboards")

            for session_token in self.m_has_updates:
                self.m_has_updates[session_token][self.m_config["source"]] = False

            self._send_to_all_dashboards("server_data", server_data, with_nodes=False)

    # process project
    def on_request_projects(self, data: dict):
        """
        Handles the request for project data from a client.

        This function is triggered when a client (typically a dashboard) requests the list of projects. It retrieves
        the project data from the database, processes it to include the volume information from the server configuration,
        and then emits the project list back to the requesting client.

        Args:
            data (dict): A dictionary containing the data related to the request. It is expected to contain enough
                        information to determine which room the client belongs to.

        Steps:
        1. Determines the room associated with the request using the `dashboard_room()` helper function. This identifies 
        which dashboard room to send the response to.
        2. Retrieves the list of projects from the database by calling `self.m_database.get_projects()`. Each project is 
        assumed to be a tuple where:
        - `i[1]`: Represents the project name.
        - `i[2]`: Represents the project description.
        3. Constructs a list of dictionaries (`items`), where each dictionary contains:
        - `project`: The name of the project.
        - `description`: The description of the project.
        4. For each project, the function adds a `volume` field to the dictionary, which is populated from the server's 
        configuration (`self.m_config["volume_map"]`). If no volume is mapped for a project, the volume is set to an empty string.
        5. Emits the `project_names` event via SocketIO, sending the `items` list (containing project names, descriptions, and volumes)
        back to the client in the corresponding room.

        Emits:
            "project_names": Sends the project data as a dictionary to the specified room. The dictionary has the format:
            {
                "data": [
                    {
                        "project": <project_name>,
                        "description": <project_description>,
                        "volume": <project_volume>
                    },
                    ...
                ]
            }

        Debugging:
        - Not directly logged here, but if `debug_print` or similar logging is available, it may be beneficial to log the 
        room and the items being sent for troubleshooting.

        Notes:
        - This function ensures that the client receives the project list along with the volume information. The `volume_map`
        is used to provide additional context for each project.
        - The client is typically a dashboard, and this response allows the dashboard to display a list of projects with
        their descriptions and mapped volumes.

        Raises:
            None. The function handles the request and emits the data back to the client via SocketIO.
        """
        room = dashboard_room(data)
        items = [ {"project":i[1], "description":i[2]  }  for i in self.m_database.get_projects()]
        for item in items:
            item["volume"] = self.m_config["volume_map"].get(item["project"], "")

        self.m_sio.emit("project_names", {"data": items}, to=room)

    def on_add_project(self, data: dict):
        """
        Handles the addition of a new project to the database and updates the volume map configuration.

        This function processes a request to add a new project. It retrieves the project name, description, and volume
        from the incoming `data`, adds the project to the database, updates the volume map in memory and on disk,
        and then refreshes the project list for clients by triggering a project data request.

        Args:
            data (dict): A dictionary containing the following keys:
                - "project" (str): The name of the new project (required).
                - "description" (str): The description of the project (optional, defaults to an empty string).
                - "volume" (str): The volume associated with the project (optional).

        Steps:
        1. Retrieves the project name, description, and volume from the `data` dictionary.
        - If the description is not provided, it defaults to an empty string.
        2. Adds the project to the database by calling `self.m_database.add_project(name, desc)`.
        3. Commits the changes to the database using `self.m_database.commit()`.
        4. Checks if the volume for the project in the configuration (`self.m_config["volume_map"]`) differs from the provided volume:
        - If the volume has changed or doesn't exist, it updates the volume map in the configuration.
        5. Writes the updated volume map to a file (`self.m_volume_map_filename`) using YAML format.
        6. Calls `self.m_database.update_volume_map()` to update the volume map in the database.
        7. Refreshes the project list for clients by invoking the `_on_request_projects()` function to send the updated list of projects.

        File I/O:
        - Opens the `self.m_volume_map_filename` file in write mode to persist the updated volume map.
        - Writes the volume map in YAML format to ensure that the configuration file is kept in sync with the in-memory map.

        Notes:
        - The volume map is a configuration that associates projects with specific volumes. This function ensures
        that the volume map is updated both in memory and on disk whenever a new project is added or when the volume
        for a project changes.
        - The function commits all changes to the database and updates the clients with the new project list.

        Example:
            If the following `data` is passed:
            {
                "project": "NewProject",
                "description": "A new project for testing",
                "volume": "/mnt/data"
            }

            The function will:
            1. Add "NewProject" to the database with the description "A new project for testing".
            2. Associate "NewProject" with the volume "/mnt/data" in the volume map and persist the map to disk.
            3. Update the database with the new volume map.
            4. Trigger the update of project data for all clients.

        Raises:
            None. The function safely processes the project addition and updates the database and configuration as needed.
        """

        name = data.get("project")
        desc = data.get("description", "")
        volume = data.get("volume")

        self.m_database.add_project(name, desc)
        self.m_database.commit()

        volume = data.get("volume")
        if self.m_config["volume_map"].get(name, "") != volume:
            self.m_config["volume_map"][name] = volume

        with open(self.m_volume_map_filename, "w") as f:
            volume_map = {"volume_map":  self.m_config["volume_map"]}
            yaml.dump(volume_map, open(self.m_volume_map_filename, "w"))            

        self.m_database.update_volume_map(self.m_config["volume_map"])
        self.on_request_projects(data)

    def on_set_project(self, data: dict):
        source = data["source"]
        self.m_sio.emit("set_project", data, to=source)

    def on_edit_project(self, data: dict):
        name = data.get("project")
        desc = data.get("description")
        volume = data.get("volume")
        if self.m_database.edit_project(name, desc):
            self.m_database.commit()
        
        volume_map_changed = False
        if self.m_config["volume_map"].get(name, "") != volume:
            self.m_config["volume_map"][name] = volume
            volume_map_changed = True

        if volume_map_changed:
            with open(self.m_volume_map_filename, "w") as f:
                volume_map = {"volume_map":  self.m_config["volume_map"]}
                yaml.dump(volume_map, open(self.m_volume_map_filename, "w"))            

        self.on_request_projects(data)

    def on_delete_project(self, data):
        name = data.get("project")
        
        if self.m_database.delete_project(name):
            self.m_database.commit()

            self.on_request_projects(data)

        if name in self.m_config["volume_map"]:
            del self.m_config["volume_map"][name]

        with open(self.m_volume_map_filename, "w") as f:
            volume_map = {"volume_map":  self.m_config["volume_map"]}
            yaml.dump(volume_map, open(self.m_volume_map_filename, "w"))            

        self.m_database.update_volume_map(self.m_config["volume_map"])

    # process robot 
    def on_request_robots(self, data: dict = None):
        names = [i[1] for i in self.m_database.get_robots()]
        self.m_sio.emit("robot_names", {"data": names})

    def on_add_robot(self, data: dict):
        self.m_database.add_robot_name(data.get("robot"), data.get("desc", ""))
        self.m_database.commit()
        self.on_request_robots()

    def on_update_entry_robot(self, data):
        # debug_print(data)
        source = data.get("source")
        upload_id = data.get("upload_id")
        robot = data.get("robot")

        entry = self.fetch_remote_entry(source, upload_id)
        if not entry:
            return 
        entry["robot_name"] = robot 

        self.update_remote_entry(source, upload_id, entry)

        update = {
            "source": source,
            "relpath": entry["relpath"],
            "basename": entry["basename"],
            "update": {"robot_name": robot},
        }

        self.m_sio.emit("update_entry", update)

    # process site
    def on_request_sites(self, data: dict =None):
        names = [i[1] for i in self.m_database.get_sites()]
        self.m_sio.emit("site_names", {"data": names})

    def on_add_site(self, data):
        self.m_database.add_site(data.get("site"), data.get("desc", ""))
        self.m_database.commit()
        self.on_request_sites()

    def on_update_entry_site(self, data):
        source = data.get("source")
        upload_id = data.get("upload_id")
        site = data.get("site")

        entry = self.fetch_remote_entry(source, upload_id)
        if not entry:
            return 

        entry["site"] = site
        self.update_remote_entry(source, upload_id, entry)


        update = {
            "source": source,
            "relpath": entry["relpath"],
            "basename": entry["basename"],
            "update": {"site": site},
        }
        self.m_sio.emit("update_entry", update)

    ## process keys
    def _save_keys(self):
        write_data = {
            "keys": self.m_config["keys"],
            "API_KEY_TOKEN": self.m_config.get("API_KEY_TOKEN", "")
            }
        yaml.dump(write_data, open(self.m_keys_filename, "w"))

    def on_request_keys(self, data=None):
        keys = self.m_config["keys"]
        api_token = self.m_config.get("API_KEY_TOKEN", "")
        self.m_sio.emit("key_values", {"data": keys, "source": self.m_config["source"], "token": api_token})

    def on_generate_key(self, data):
        source = data.get("source")
        name = data.get("name")
        
        # add some spice to the key
        salt = secrets.token_bytes(16)

        values = [source, name, f"{salt}"]

        key = hashlib.sha256("_".join(values).encode()).hexdigest()[:16]
        if key in self.m_config["keys"]:
            self.m_sio.emit("server_status", {"msg": "failed to create key", "rtn": False})
            return 
        self.m_config["keys"][key] = name

        self._save_keys()
        self.m_sio.emit("server_status", {"msg": "Created key", "rtn": True})
        self.m_sio.emit("generated_key", {"key": key})
        self.on_request_keys(data)

    def on_insert_key(self, data):
        name = data.get("name")
        key = data.get("key")

        if key in self.m_config["keys"]: 
            return 
        
        if name in self.m_config["keys"].values():
            return 
        self.m_config["keys"][key] = name 

        self._save_keys()
        self.m_sio.emit("server_status", {"msg": "Inserted key", "rtn": True})

        self.on_request_keys(data)

    def on_delete_key(self, data):
        source = data.get("source")
        key = data.get("key")
        name = data.get("name")

        debug_print(f"deleting {key} for {name} via {source}")

        if key in self.m_config["keys"]:
            del self.m_config["keys"][key]
        else:
            debug_print(f"Did not find {key}")

        self._save_keys()
        self.on_request_keys()

    def on_set_api_key_token(self, data):
        key = data.get("key")
        self.m_config["API_KEY_TOKEN"] = key 
        self._save_keys()
        self.on_request_keys()

    # process search
    def on_request_search_filters(self, data:dict):
        room = dashboard_room(data)
        msg = self.m_database.get_search_filters()
        self.m_sio.emit("search_filters", msg, to=room)

    def on_search(self, data):
        room = data.get("room", None)
        filter = data.get("filter", {})
        sort_key = data.get("sort-key", "datetime")
        reverse = data.get("sort-direction", "forward") == "reverse"
        page_size = data.get("results-per-page", 25)

        if room is None:
            debug_print("No room!")
            return 
        self.m_search_results[room] = self.m_database.search(filter, sort_key, reverse=reverse)

        query = {
            "room": room,
            "count": page_size,
            "start_index": 0
        }

        return self.on_search_fetch(query)

    def on_search_fetch(self, query):
        room = query.get("room", None)
        page_size = int(query.get("count"))
        start_index = int(query.get("start_index", 0))

        results = []
        if room in self.m_search_results:
            results = self.m_search_results[room][start_index: (page_size+start_index)]

        total = len(self.m_search_results[room])
        total_pages = int(math.ceil(float(total)/float(page_size)))
        current_page = int(start_index) // int(page_size)

        msg = {
            "total_pages": total_pages,
            "current_page": current_page,
            "current_index": start_index,
            "results": results
        }
        self.m_sio.emit("search_results", msg, to=room)

    ## device data
    def on_device_status(self, data):
        source = data.get("source")
        msg = {"source": source}
        self.m_ui_status[source] = None
        if "msg" in data:
            msg["msg"] = data["msg"]
        self.m_sio.emit("device_status", msg)

    def on_device_status_tqdm(self, data):
        self.m_sio.emit("device_status_tqdm", data)

    def on_device_scan(self, data):
        self.m_sio.emit("device_scan", data)

    def on_device_files_items(self, data):
        source = data.get("source")
        files = data.get("files")

        self.m_remote_entries_buffer[source] = self.m_remote_entries_buffer.get(source, [])
        self.m_remote_entries_buffer[source].extend(files)

    def on_device_files(self, data):
        source = data.get("source")
        project = data.get("project", None)
        # debug_print(f"project is [{project}]")
        if project is None:
            debug_print(f"clearing {source}")
            self.delete_remote_entries_for_source(source)
            

        if project and project not in self.m_config["volume_map"]:
            self.m_sio.emit("server_error", {"msg": f"Project: {project} does not have a volume mapping"})
            debug_print("Error")


        # files = data.get("files")
        files = self.m_remote_entries_buffer.get( source, data.get("files", []))
        if source in self.m_remote_entries_buffer: del self.m_remote_entries_buffer[source]

        self.m_selected_files_ready[source] = False
        self.m_selected_action[source] = None
        # self.m_projects[source] = project
        self.device_set_project(source, project)

        if source not in self.m_sources["devices"]:
            self.m_sources["devices"].append(source)
        self.add_source( source, "devices")

        # note, this could be emitted
        self.m_fs_info[source] = data.get("fs_info")

        # debug_print(f"Clearing {source} with {len(files)}")
        self.delete_remote_entries_for_source(source)

        for entry in files:
            dirroot = entry.get("dirroot")
            file = entry.get("filename")
            size = entry.get("size")
            start_datetime = entry.get("start_time")
            end_datetime = entry.get("end_time")
            md5 = entry.get("md5")
            robot_name = entry.get("robot_name")
            if robot_name and len(robot_name) > 0:
                has_robot = self.m_database.has_robot_name(robot_name)
                if not has_robot:
                    self.m_database.add_robot_name(robot_name, "")
                    self.m_database.commit()

                    # send users new robot names
                    self.on_request_robots()
                    
            site = entry.get("site")
            topics = entry.get("topics", {})

            # for dirroot, file, size, start_datetime, end_datetime, md5 in files:
            upload_id = get_upload_id(source, project, file)

            project = project if project else "None"
    
            entry = {
                "project": project,
                "robot_name": robot_name,
                "run_name": None,
                "datatype": get_datatype(file),
                "relpath": os.path.dirname(file),
                "basename": os.path.basename(file),
                "fullpath": file,
                "size": size,
                "site": site,
                "date": start_datetime.split(" ")[0],
                "datetime": start_datetime,
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
                "upload_id": upload_id,
                "dirroot": dirroot,
                "remote_dirroot": dirroot,
                "status": None,
                "temp_size": 0,
                "on_device": True,
                "on_server": False,
                "md5": md5,
                "topics": topics,
            }


            filepath = self._get_file_path_from_entry(entry)
            status = "On Device"
            if os.path.exists(filepath):
                status = "On Device and Server"
                entry["on_server"] = True
            if os.path.exists(filepath + ".tmp"):
                status = "Interrupted transfer"
                entry["temp_size"] = os.path.getsize(
                    filepath + ".tmp"
                )
            entry["status"] = status

            self.create_remote_entry(source, upload_id, entry)
            self.sync_remote_entry(source, upload_id)

        # debug_print("data complete")
        self._send_device_data()

    def on_request_device_ymd_data(self, data):
        tab = data.get("tab")
        names = tab.split(":")
        _, source, ymd = names

        datasets = self._get_send_device_data_ymd_data(source, ymd)
        room = dashboard_room(data)
        stats = self._get_device_data_stats_by_source_ymd(source, ymd)

        # Start the long-running task in the background
        self.m_sio.start_background_task(target=self._emit_device_ymd_data, datasets=datasets, stats=stats, source=source, ymd=ymd, tab=tab, room=room)

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


    ### server data 
    def on_request_server_ymd_data(self, data):
        # debug_print(data)
        tab = data.get("tab")
        names = tab.split(":")[-2:]

        project, ymd = names
        datasets = self.m_database.get_send_data_ymd(project, ymd)
        stats = self.m_database.get_run_stats(project, ymd)        
        room = dashboard_room(data)

        # Start the long-running task in the background
        self.m_sio.start_background_task(target=self._emit_server_ymd_data, datasets=datasets, stats=stats, project=project, ymd=ymd, tab=tab, room=room)

    ## remote connections     
    def on_control_msg(self, data):
        source = data.get("source")
        action = data.get("action")
        self.m_sio.emit("control_msg", {"action": action}, to=source)
        if self.m_remote_connection.connected():
            self.m_remote_connection._handle_control_msg(data)

    def on_remote_transfer_files(self, data):
        debug_print(f"{data}")
        url = data["url"]
        files = data["files"]
        source = data["source"]
        selected = []

        for row in files:
            project, filepath, upload_id, offset, size, remote_id = row 
            entry = self.m_database.get_entry(remote_id)
            debug_print(entry)
            selected.append( (project, filepath, upload_id, offset, size, entry))

        nodeConnection = self.m_node_connections.get(source, None)
        if not nodeConnection:
            debug_print("No connection") 
            return 

        self.m_sio.start_background_task(nodeConnection.sendFiles, selected, url)

    def on_request_server_data(self,data):
        debug_print(data)
        self._send_server_data(data)

    def on_server_connect(self, data):
        global g_remote_connection
        address = data.get("address", None)
        # username = request.cookies.get("username")
        if address:
            self.m_remote_connection.connect(address, self._send_to_all_dashboards, get_file_path_from_entry_fn=self._get_file_path_from_entry)

        # debug_print(("Connection", g_remote_connection.connected()))
        source = self.m_config["source"]
        self.m_sio.emit(
            "remote_connection",
            {
                "source": source,
                "address": address,
                "connected": self.m_remote_connection.connected(),
            },
        )

    def on_server_disconnect(self, data):
        self.m_remote_connection.disconnect()

    def on_server_status_tqdm(self, data):
        # this status can come from either node or server
        # file upload, so both will be updated.
        self._send_to_all_dashboards("server_status_tqdm", data, with_nodes=True)
        self._send_to_all_dashboards("node_status_tqdm", data, with_nodes=True)

    def on_server_refresh(self, msg=None):
        # send the updated data to the server.  
        self.m_remote_connection.server_refresh()

    def on_server_transfer_files(self, data):
        if self.m_remote_connection.connected():
            self.m_remote_connection.server_transfer_files(data)

    def on_transfer_node_files(self, data):
        debug_print(data)
        source = data.get("source")
        selected_files = data.get("upload_ids")

        filenames = []
        for upload_id in selected_files:
            entry = self.fetch_remote_entry(source, upload_id)
            if not entry:
                debug_print(
                    f"Error! did not find upload id [{upload_id}] for {source}"
                )
                continue

            filepath = self._get_file_path_from_entry(entry)
            if os.path.exists(filepath):
                continue

            project = entry["project"]
            offset = entry["temp_size"]
            size = entry["size"]
            file = entry["fullpath"]
            filenames.append((project, file, upload_id, offset, size))

        msg = {"source": data.get("source"), "files": filenames}

        self.m_sio.emit("node_send", msg)

    def on_request_remote_ymd_data(self, data):
        self.m_remote_connection.request_remote_ymd_data(data)

    def on_remote_request_files(self, data):
        debug_print(data)

        selected_files = data.get("selected_files")
        url = data.get("url")
        source = self.m_config["source"]

        if self.m_remote_connection.connected():
            msg = {
                "files": selected_files,
                "url": url,
                "source": source
            }
            self.m_remote_connection.pull_files(msg)


    ### http commands 
    def authenticate(self):    
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

    def index(self):
        session_token = str(uuid.uuid4())
        response = make_response(render_template("index.html", session={"token": session_token}))

        # response = make_response(send_from_directory("static", "index.html"))
        user = request.headers.get('X-Authenticated-User')  
        if user:
            response.set_cookie("username", user)  

        return response

    def serve_js(self, path):
        return send_from_directory("js", path)

    def serve_css(self, path):
        return send_from_directory("css", path)

    def show_login_form(self):
        return render_template("login.html")

    def handle_file(self, source: str, upload_id: str):
        debug_print(f"{source} {upload_id}")

        entry = self.fetch_remote_entry(source, upload_id)
        if entry is None:
            json_data = request.form.get('json')
            if json_data:
                entry = json.loads(json_data)
            else:
                return f"Invalid ID {upload_id} for {source}", 503


                sources = self.get_sources("devices")
                if not source in sources:
                    debug_print(f"Invalid Source {source}")
                    return f"Invalid Source {source}",  503

                else:
                    debug_print(f"Invalid ID {upload_id} for {source}")
                    return f"Invalid ID {upload_id} for {source}", 503

        # debug_print(entry)

        offset = request.args.get("offset", 0)
        if offset == 0:
            open_mode = "wb"
        else:
            open_mode = "ab"

        cid = request.args.get("cid")
        splits = request.args.get("splits")
        is_last = cid == splits

        filep = request.files.get('file', request.stream)
        filename = entry["basename"]

        filepath = self._get_file_path_from_entry(entry)
        tmp_path = filepath + ".tmp"

        # debug_print(filepath)

        if os.path.exists(filepath):
            return jsonify({"message": f"File {filename} alredy uploaded"}), 409

        if self.m_selected_action.get(source, "") == "cancel":
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

        # Start uploading the file in chunks
        chunk_size = 10 * 1024 * 1024  # 1MB chunks
        with open(tmp_path, open_mode) as fid:
            while True:

                if self.m_selected_action.get(source,"") == "cancel":
                    self._send_dashboard_file(cancel_msg)

                    return jsonify({"message": f"File {filename} upload canceled"})

                try:
                    chunk = filep.read(chunk_size)

                except OSError:
                    # we lost the connection on the client side.
                    self._send_dashboard_file(cancel_msg)
                    return jsonify({"message": f"File {filename} upload canceled"})

                if not chunk:
                    break
                fid.write(chunk)

        os.chmod(tmp_path, 0o777 )

        if os.path.exists(tmp_path) and is_last:
            current_size = os.path.getsize(tmp_path)
            if current_size != expected:
                # transfer canceled politely on the client side, or
                # some other issue. Either way, data isn't what we expected.
                cancel_msg["status"] = (
                    "Size mismatch. " + str(current_size) + " != " + str(expected)
                )
                self._send_dashboard_file(cancel_msg)

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

            self._send_dashboard_file(data)

        entry["localpath"] = filepath
        entry["on_server"] = True
        entry["dirroot"] = self._get_dirroot(entry["project"])
        entry["fullpath"] = filepath.replace(entry["dirroot"], "").strip("/")


        metadata_filename = filepath + ".metadata"
        with open(metadata_filename, "w") as fid:
            json.dump(entry, fid, indent=True)

        os.chmod(metadata_filename, 0o777)

        self.m_database.add_data(entry)
        self.m_database.estimate_runs()
        self.m_database.commit()


        # signal to the dashboards that this source has updates.  
        for session_token in self.m_has_updates:
            self.m_has_updates[session_token][self.m_config["source"]] = True

            room = "dashboard-" + session_token
            self.m_sio.emit("has_new_data", {"value": True}, to=room)

        # # TODO: replace send_server_data with "update_server_data"
        # # send_server_data()

        # ymd = entry["date"]
        # project = entry["project"]
        # tab = f"server:{project}:{ymd}"

        # on_request_server_ymd_data({"tab": tab})

        self._device_revise_stats()

        return jsonify({"message": f"File {filename} chunk uploaded successfully"})

    def transfer_selected(self):
        data = request.get_json()
        selected_files = data.get("files")
        source = data.get("source")

        filenames = []
        for upload_id in selected_files:
            entry = self.fetch_remote_entry(source, upload_id)
            if not entry:
                debug_print(
                    f"Error! did not find upload id [{upload_id}] in {sorted(self.m_remote_entries[source])}"
                )
                continue

            filepath = self._get_file_path_from_entry(entry)
            if os.path.exists(filepath):
                continue

            dirroot = entry["dirroot"]
            relpath = entry["fullpath"].strip("/")
            offset = entry["temp_size"]
            size = entry["size"]
            filenames.append((dirroot, relpath, upload_id, offset, size))

        msg = {"source": data.get("source"), "files": filenames}

        self.m_sio.emit("device_send", msg)

        # # debug_print(data)
        return jsonify("Received")

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
                if self.m_config["keys"][key].lower() == username.lower():
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

    def download_file(self,upload_id):
        localpath = self.m_database.get_localpath(upload_id)
        debug_print((upload_id, localpath))        
        if localpath:

            directory = os.path.dirname(localpath)
            filename = os.path.basename(localpath)
            
            debug_print(f"Download {localpath} {os.path.exists(localpath)}")
            return send_from_directory(directory=directory, path=filename, as_attachment=True)
        
        return "File Not Found", 404

    
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
                self.m_config["keys"] = keys
                self._save_keys()
                self.on_request_keys(None)

                return jsonify({'message': 'Keys updated.'}), 200
            
            except yaml.YAMLError as e:
                return jsonify({'message': f'Error parsing YAML file: {str(e)}'}), 400
            except Exception as e:
                return jsonify({'message': f'Error saving file: {str(e)}'}), 500            




    # debug. disable for production

    def on_debug_clear_data(self, data=None):
        self.m_database.debug_clear_data()
        self._send_server_data(data)

    def on_debug_scan_server(self, data=None):
        debug_print("enter")
        self.m_sio.start_background_task(self._scan_server_background, data)

    def _scan_server_background(self, data=None):
        debug_print("Scanning server")
        self.m_database.regenerate(self.m_sio, event="server_regen_msg")

        for project_name in self.m_config.get("projects", []):
            self.m_database.add_project(project_name, "")

        for robot_name in self.m_config.get("robots", []):
            self.m_database.add_robot_name(robot_name, "")

        for site_name in self.m_config.get("sites", []):
            self.m_database.add_site(site_name, "")

        self._send_server_data(data)
