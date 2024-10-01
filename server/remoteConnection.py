import os 
import socket
import socketio 
import queue 
import requests
import gevent 

import socketio.exceptions
from .database import Database, VolumeMapNotFound, get_upload_id
from .SocketIOTQDM import SocketIOTQDM
from .debug_print import debug_print


def count_elements(d):
    count = 0
    if isinstance(d, dict):
        count += len(d)  # Count the keys
        for key, value in d.items():
            if isinstance(value, dict):
                count += count_elements(value)  # Recursively count elements in nested dictionary
            elif isinstance(value, list):
                count += len(value)  # Count elements in the list
                for item in value:
                    if isinstance(item, dict):
                        count += count_elements(item)  # Recursively count elements in nested dictionaries within lists
            else:
                count += 1  # Count the value as an element
    return count


class RemoteConnection:
    """
    Args:
        config: loaded config
        local_sio: The parent processes socket to local server
    """
    def __init__(self, config, local_sio, database:Database) -> None:
        self.m_config = config

        self.m_local_sio = local_sio
        self.m_sio = socketio.Client()
        self.m_server = None 
        self.m_signal = None
        self.m_verbose = config.get("verbose", True)
        self.m_database = database
        self.m_source = config.get("source")
        self.m_username = ""

        # maps remote to local id
        self.m_upload_id_map = {}

        # maps local id to remote 
        self.m_rev_upload_id_map =  {}

        self.m_node_source = None 
        pass

    def connected(self):
        return self.m_sio.connected
    
    def server_name(self):
        if self.m_sio.connected:
            return self.m_server 
        return None 

    def connect(self, server_full, send_to_all_dashboards_fn, get_file_path_from_entry_fn):
        rtn = False

        try:
            self.m_server = None
            server, port = server_full.split(":")
            port = int(port)
            socket.create_connection((server, port))
            debug_print(f"Connected to {server}:{port}")

            if self.m_sio.connected:
                self.m_sio.disconnect()

            api_key_token = self.m_config["API_KEY_TOKEN"]
            headers = {"X-Api-Key": api_key_token}

            self.m_sio.connect(f"http://{server}:{port}/socket.io", headers=headers, transports=['websocket'])
            self.m_sio.on('control_msg')(self._handle_control_msg)    
            self.m_sio.on("dashboard_file")(self._on_dashboard_file)
            # self.m_sio.on("node_data")(self._on_node_data)
            self.m_sio.on("node_data_ymd_rtn")(self._on_node_data_ymd_rtn)
            self.m_sio.on("node_send")(self._on_node_send)
            self.m_sio.on("disconnect")(self._on_disconnect)
            self.m_sio.on("connect")(self._on_connect)
            self.m_sio.on("node_revise_stats")(self._on_node_revise_stats)
            self.m_sio.on("dashboard_info")(self._on_dashboard_info)
            self.m_sio.on("server_data")(self._on_server_data)
            self.m_sio.on("server_ymd_data")(self._on_server_ymd_data)
            # self.m_sio.on("device_remove")(self.removeFiles)

            # self.m_node_source = self.m_config["source"].replace("SRC","NODE")
            self.m_node_source = self.m_config["source"]
            self.m_sio.emit('join', { 'room': self.m_node_source, "type": "node" })
            self.m_server = server_full
            self.m_upload_id_map = {}
            self.m_rev_upload_id_map = {}

            self.send_to_all_dashboards_fn = send_to_all_dashboards_fn
            self.get_file_path_from_entry_fn = get_file_path_from_entry_fn

            self.send_node_data()

            self.m_sio.emit("request_server_data", {"room": self.m_node_source})

            rtn = True

        except socketio.exceptions.ConnectionError as e:
            debug_print("Ah-Ah-Ahh, invalid key")
            self.m_local_sio.emit("server_invalid_key", {"key": api_key_token, "server": server_full})

        except Exception as e:
            if self.m_verbose:
                debug_print(e)
        return rtn

    # def dashboard_room(self):
    #     return "dashboard-" + self.m_username

    def _on_connect(self):
        debug_print("node connected")
        source = self.m_config["source"]
        msg = {"source": source, "address": self.m_server, "connected": True}
        self.send_to_all_dashboards_fn("remote_connection", msg)
        # self.m_local_sio.emit("remote_connection", {"source": source, "address": self.m_server, "connected": True}, to=self.dashboard_room())
        self.m_sio.emit("server_refresh")

    def _on_disconnect(self):
        debug_print("node disconnected")
        source = self.m_config["source"]
        msg = {"source": source, "connected": False}
        self.send_to_all_dashboards_fn("remote_connection", msg)
        # self.m_local_sio.emit("remote_connection", {"source": source, "connected": False}, to=self.dashboard_room())
        

    def _on_dashboard_info(self, data):
        host = data.get("source")
        debug_print(f"connected to [{host}]")

    def _on_dashboard_file(self, data):

        # debug_print(data)

        source = data.get("source")
        # we only want to do updates from external sources.  
        if source == self.m_node_source:
            return 
        # debug_print(data)
        upload_id = data["upload_id"]
        local_id = self.m_upload_id_map.get(upload_id, None)
        if( local_id):
            data["upload_id"] = local_id
            # self.m_local_sio.emit("dashboard_update", data, to=self.dashboard_room())
            self.send_to_all_dashboards_fn("dashboard_update", data)
        else:
            debug_print(f"Didn't get mapping for {upload_id}")
        # self.m_local_sio.emit("dashboard_file_server", data)
        pass 


    def _on_node_data_ymd_rtn(self, data):
        entries = data["entries"]
        project = data["project"]

        for upload_id in entries:
            entry = entries[upload_id]

            on_remote = entry.get("on_local")
            on_local = entry.get("on_remote")
            remote_id = entry.get("upload_id")


            # file = os.path.join(entry["relpath"], entry["basename"]) 

            # upload_id = get_upload_id(self.m_config["source"], project, file)
            self.m_upload_id_map[remote_id] = upload_id
            self.m_rev_upload_id_map[upload_id] = remote_id

            # debug_print(f"Remote: {remote_id} -> {upload_id}")            

            msg = {
                "on_remote": on_local,
                "on_local": on_remote,
                "upload_id": upload_id
            }
            self.send_to_all_dashboards_fn("dashboard_file_server", msg)
            # self.m_local_sio.emit("dashboard_file_server", msg, to=self.dashboard_room())

        
    def _on_server_data(self, data):    
        debug_print("Got server data")    
        self.m_local_sio.emit("remote_data", data)

    def _on_server_ymd_data(self, data):
        debug_print("Got Data")

        msg = {
            "ymd": data.get("ymd", ""),
            "project": data.get("project", ""),
            "source": data.get("source", ""),
            "tab": data.get("tab", ""),
            "runs": {},
            "stats": data.get("stats", {})
        }

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
                    self.m_upload_id_map[upload_id] = local_id 
                    self.m_rev_upload_id_map[local_id] = upload_id
                    # self.m_upload_id_map.get(upload_id, None)
                    item["upload_id"] = local_id
                    item["remote_upload_id"] = upload_id

                    filepath = self.get_file_path_from_entry_fn(item)
                    item["on_remote"] = True 
                    item["on_local"] =  os.path.exists(filepath)

                    tmp = filepath + ".tmp"
                    offset = 0
                    if os.path.exists(tmp):
                        offset = os.path.getsize(tmp)
                    item["offset"] = offset 

                    msg["runs"][run_name][rel_path].append(item)

        self.m_local_sio.emit("remote_ymd_data", msg)


    def server_transfer_files(self, data):
        debug_print(data)

        for uid in data["upload_ids"]:
            debug_print((uid, self.m_rev_upload_id_map.get(uid, "Not found")))

        ids = [ self.m_rev_upload_id_map[uid] for uid in data["upload_ids"] if uid in self.m_rev_upload_id_map ]
        msg = {
            "source": self.m_node_source,
            "upload_ids": ids
        }
        self.m_sio.emit("transfer_node_files", msg)

    def _handle_control_msg(self, data):
        source = data.get("source")
        # if source != self.m_config["source"] :
        if source != self.m_node_source:
            return 
        if data.get("action", "") == "cancel":
            self.m_signal = "cancel"

    def request_remote_ymd_data(self, data):
        if not self.connected():
            return 
        tab = data.get("tab", None)
        if not tab:
            return 
        msg = {"tab": tab, "room": self.m_node_source}

        debug_print(msg)
        self.m_sio.emit("request_server_ymd_data", msg)

    def send_node_data(self):
        if not self.connected():
            return 
        
        debug_print("Sending node data")

        try:
            data = self.m_database.get_send_data()
        except VolumeMapNotFound as e:
            self.m_local_sio.emit("server_error", {"msg": str(e)})
            
            
        source = self.m_node_source
        stats = self.m_database.get_run_stats()

        node_data = {"entries": data, 
                     "stats": stats,
                       "source": source
                        }

        url = f"http://{self.m_server}/nodedata"

        api_key_token = self.m_config["API_KEY_TOKEN"]
        headers = {
            "Authorization": f"Bearer {api_key_token}"
            }

        debug_print("sending node data")
        response = requests.post(url, json=node_data, headers=headers)
        debug_print(response.status_code)


    def _on_node_send(self, data):
        # source = data.get("source").replace("NODE", "SRC")
        source = data.get("source")
        if source != self.m_config["source"]:
            return 
        files = data.get("files")

        self._sendFiles(self.m_server, files)

    def _on_node_revise_stats(self, data):
        debug_print(data)

        # msg = {}
        if self.m_node_source in data:
            pass 


    def _sendFiles(self, server, filelist):
        local_status_event = "server_status_tqdm"
        remote_status_event = "node_status_tqdm"
        self.m_signal = None 

        num_threads = min(self.m_config["threads"], len(filelist))
        url = f"http://{server}/file"

        #  source = self.m_config["source"]
        # debug_print(f"Source: {self.m_node_source}")
        source = self.m_node_source
        api_key_token = self.m_config["API_KEY_TOKEN"]


        total_size = 0
        file_queue = queue.Queue()
        for file_pair in filelist:
            debug_print(f"add to queue {file_pair}")
            offset = file_pair[3]
            size = file_pair[4]
            try:
                total_size += int(size) - int(offset)
            except ValueError as e:
                debug_print(file_pair)
                raise e 
            file_queue.put(file_pair)

    
        with SocketIOTQDM(total=total_size, unit="B", unit_scale=True, desc="File Transfer", position=0, 
                          leave=False, source=self.m_node_source, socket=self.m_local_sio, event=local_status_event) as local_main_pbar,  SocketIOTQDM(total=total_size, unit="B", unit_scale=True, desc="File Transfer", position=0, 
                          leave=False, source=self.m_config["source"], socket=self.m_sio, event=remote_status_event) as remote_main_pbar:

            def worker(index:int):
                with requests.Session() as session:
                    while True:
                        try:                            
                            project, file, upload_id, offset, total_size = file_queue.get(block=False)
                            offset = int(offset)
                            total_size = int(total_size)

                            # debug_print((dirroot, file, upload_id, offset, total_size))
                        except queue.Empty:
                            break 
                        
                        if self.m_signal == "cancel":
                            break

                        dirroot = self.m_config["volume_map"].get(project, "/").strip("/")
                        fullpath = os.path.join( self.m_config["volume_root"], dirroot, file.strip("/"))
                        if not os.path.exists(fullpath):
                            local_main_pbar.update()
                            remote_main_pbar.update()
                            debug_print(f"{fullpath} not found" )
                            continue 

                        # total_size = os.path.getsize(fullpath)

                        with open(fullpath, 'rb') as file:
                            params = {}
                            if offset > 0:
                                file.seek(offset)
                                params["offset"] = offset 
                                total_size -= offset 

                            headers = {
                                'Content-Type': 'application/octet-stream',
                                "Authorization": f"Bearer {api_key_token}"

                                }
                            
                            # debug_print(headers)
                            # Setup the progress bar
                            with SocketIOTQDM(total=total_size, unit="B", unit_scale=True, leave=False, position=1+index, source=self.m_node_source, socket=self.m_sio, event=remote_status_event) as remote_pbar, SocketIOTQDM(total=total_size, unit="B", unit_scale=True, leave=False, position=1+index, source=self.m_config["source"], socket=self.m_local_sio, event=local_status_event) as local_pbar:
                                def read_and_update():
                                    while True:
                                        # Read the file in chunks of 4096 bytes (or any size you prefer)
                                        chunk = file.read(1024*1024)
                                        if not chunk:
                                            break
                                        yield chunk
                                        # Update the progress bar
                                        local_pbar.update(len(chunk))
                                        local_main_pbar.update(len(chunk))

                                        remote_pbar.update(len(chunk))
                                        remote_main_pbar.update(len(chunk))

                                        if self.m_signal:
                                            if self.m_signal == "cancel":
                                                break
                                
                                # Make the POST request with the streaming data
                                response = session.post(url + f"/{source}/{upload_id}", params=params, data=read_and_update(), headers=headers)

                            if response.status_code != 200:
                                debug_print(("Error uploading file:", response.text, response.status_code))

                            # main_pbar.update()
    
            greenlets = []
            for i in range(num_threads):
                greenlet = gevent.spawn(worker, i)  # Spawn a new green thread
                greenlets.append(greenlet)

            # Wait for all green threads to complete
            gevent.joinall(greenlets)

        self.m_signal = None 



    def disconnect(self):
        if self.m_sio.connected:
            self.m_sio.disconnect()

    def pull_files(self, data):
        debug_print("enter")
        if self.m_sio.connected:
            self.m_sio.emit("remote_transfer_files", data)