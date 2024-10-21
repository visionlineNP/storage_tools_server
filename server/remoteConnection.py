from concurrent.futures import ThreadPoolExecutor
import os 
import socket
from threading import Thread
import uuid
import socketio 
import queue 
import requests
import time 
# import gevent 

import socketio.exceptions
from .database import Database, VolumeMapNotFound, get_upload_id
from .SocketIOTQDM import SocketIOTQDM, MultiTargetSocketIOTQDM
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


class PosMaker:
    def __init__(self, max_pos) -> None:
        self.m_pos = {i: False for i in range(max_pos)}
        self.m_max = max_pos
    
    def get_next_pos(self) -> int:
        for i in sorted(self.m_pos):
            if not self.m_pos[i]:
                self.m_pos[i] = True 
                return i
            
        # just in case things get messed up, always return a valid position
        i = self.m_max 
        self.m_max += 1
        self.m_pos[i] = True
        return i 
    
    def release_pos(self, i):
        self.m_pos[i] = False


def pbar_thread(messages:queue.Queue, total_size, source, socket_events, desc, max_threads):
    pos_maker = PosMaker(max_threads)

    positions = {}

    pbars = {}
    pbars["main_pbar"] = MultiTargetSocketIOTQDM(total=total_size, unit="B", unit_scale=True, leave=False, position=0, delay=1, desc=desc, source=source,socket_events=socket_events)

    while True:
        try:
            action_msg = messages.get(block=True)

        except queue.Empty:
            time.sleep(0.001)
            continue
        except ValueError:
            time.sleep(0.001)
            continue
        
        if "close" in action_msg:
            # debug_print("close")
            break

        if "main_pbar" in action_msg:
            pbars["main_pbar"].update(action_msg["main_pbar"])
            continue

        if "child_pbar" in action_msg:
            name = action_msg["child_pbar"]
            action = action_msg["action"] 
            if action == "start":
                desc = action_msg["desc"]
                position = pos_maker.get_next_pos()
                positions[name] = position
                size = action_msg["size"]
                if position in pbars:
                    pbars[position].close()
                    del pbars[position]
                # debug_print(f"creating {name}")
                pbars[position] = MultiTargetSocketIOTQDM(total=size, unit="B", unit_scale=True, leave=False, position=position+1, delay=1, desc=desc, source=source,socket_events=socket_events)
                continue
            if action == "update":     
                # debug_print(f"updating {name}")           
                position = positions.get(name, None)
                if position == None:
                    debug_print(f"Do not have pbar for {name}")
                    for pname in positions:
                        debug_print(f"{pname} {positions[pname]}")
                    continue
                size = action_msg["size"]
                if position in pbars:
                    # debug_print(f"{position} : {size}")
                    pbars[position].update(size)
                else:
                    debug_print(f"do not have pbar for {position}")
                continue
            if action == "close":
                position = positions.get(name, None)
                if position == None:
                    continue

                if position in pbars:
                    pbars[position].close()
                    del pbars[position]
                pos_maker.release_pos(position)

                # debug_print(f"removing {name}")
                del positions[name]
                continue
            continue 


    positions = pbars.keys()
    for position in positions:
        pbars[position].close()


class RemoteConnection:
    """
    Args:
        config: loaded config
        local_sio: The parent processes socket to local server
    """
    def __init__(self, config, local_sio, database:Database, parent) -> None:
        self.m_config = config
        self.m_parent = parent 

        self.m_local_sio = local_sio
        self.m_remote_sio = socketio.Client()
        self.m_server = None 
        self.m_signal = None
        self.m_send_threads = False 
        self.m_verbose = config.get("verbose", True)
        self.m_database = database
        self.m_source = config.get("source")
        self.m_username = ""
        self.m_session_token = None 
        self.m_send_lock = {}

        self.m_send_offsets = {}
        # maps remote to local id
        self.m_upload_id_map = {}

        # maps local id to remote 
        self.m_rev_upload_id_map =  {}

        self.m_node_source = None 
        self.m_remote_source = None 

        self.send_to_al_local_dashboards_fn = None 
        self.get_file_path_from_entry_fn = None
        pass

    def connected(self):
        return self.m_remote_sio.connected
    
    def server_name(self):
        if self.m_remote_sio.connected:
            return self.m_server 
        return None 

    def connect(self, server_full, send_to_all_dashboards_fn, get_file_path_from_entry_fn):
        rtn = False

        self.send_to_al_local_dashboards_fn = send_to_all_dashboards_fn
        self.get_file_path_from_entry_fn = get_file_path_from_entry_fn
        self.m_session_token = str(uuid.uuid4())

        try:
            self.m_server = None
            self.m_remote_source = None 
            server, port = server_full.split(":")
            port = int(port)

            self.send_to_al_local_dashboards_fn("server_link_status", {"server": server_full, "msg": f"Testing <b>{server_full}</b>"})

            socket.create_connection((server, port))
            debug_print(f"Connected to {server}:{port}")

            self.send_to_al_local_dashboards_fn("server_link_status", {"server": server_full, "msg":""})

            if self.m_remote_sio.connected:
                self.m_remote_sio.disconnect()

            api_key_token = self.m_config["API_KEY_TOKEN"]
            headers = {"X-Api-Key": api_key_token}

            self.m_remote_sio.connect(f"http://{server}:{port}/socket.io", headers=headers, transports=['websocket'])
            self.m_remote_sio.on('control_msg')(self._handle_control_msg)    
            self.m_remote_sio.on("dashboard_file")(self._on_dashboard_file)
            self.m_remote_sio.on("node_data_ymd_rtn")(self._on_node_data_ymd_rtn)
            self.m_remote_sio.on("node_data_block_rtn")(self.on_node_data_block_rtn)
            self.m_remote_sio.on("node_send")(self._on_node_send)
            self.m_remote_sio.on("disconnect")(self._on_disconnect)
            self.m_remote_sio.on("connect")(self._on_connect)
            self.m_remote_sio.on("node_revise_stats")(self._on_node_revise_stats)
            self.m_remote_sio.on("dashboard_info")(self._on_dashboard_info)
            self.m_remote_sio.on("server_data")(self._on_server_data)
            self.m_remote_sio.on("server_ymd_data")(self._on_server_ymd_data)

            self.m_node_source = self.m_config["source"]
            self.m_remote_sio.emit('join', { 'room': self.m_node_source, "type": "node" })
            self.m_server = server_full
            self.m_upload_id_map = {}
            self.m_rev_upload_id_map = {}
            self.m_send_lock = {}

            self.send_node_data()

            self.m_remote_sio.emit("request_server_data", {"room": self.m_node_source})

            rtn = True

        except socketio.exceptions.ConnectionError as e:
            debug_print("Ah-Ah-Ahh, invalid key")
            self.send_to_al_local_dashboards_fn("server_invalid_key", {"key": api_key_token, "server": server_full})

        except Exception as e:
            if self.m_verbose:
                debug_print(e)
            self.send_to_al_local_dashboards_fn("server_link_status", {"server": server_full, "msg": f"Failed to connect to <b>{server_full}</b>: <i>{e}</i>", "timeout": 2.5})
        return rtn


    def server_refresh(self):
        # Send the contents of our server to the remote
        # request the remote sends their data to us. 
        self.send_node_data()

        try:
            self.m_remote_sio.emit("request_server_data", {"room": self.m_node_source})
        except socketio.exceptions.BadNamespaceError:
            pass 

    def _on_connect(self):
        # when we connect to a remote server,
        # 
        debug_print("node connected")
        source = self.m_config["source"]

        msg = {"source": source, "address": self.m_server, "connected": True}
        self.send_to_al_local_dashboards_fn("remote_connection", msg)
        self.m_remote_sio.emit("server_refresh")

    def _on_disconnect(self):
        debug_print("node disconnected")
        source = self.m_config["source"]
        msg = {"source": source, "connected": False}
        self.send_to_al_local_dashboards_fn("remote_connection", msg)
        # self.m_local_sio.emit("remote_connection", {"source": source, "connected": False}, to=self.dashboard_room())
        

    def _on_dashboard_info(self, data):
        host = data.get("source")
        debug_print(f"connected to [{host}]")
        self.m_remote_source = host

    def _on_dashboard_file(self, data):
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
            self.send_to_al_local_dashboards_fn("dashboard_update", data)
        else:
            debug_print(f"Didn't get mapping for {upload_id}")
        # self.m_local_sio.emit("dashboard_file_server", data)
        pass 


    def on_node_data_block_rtn(self, data):
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
            self.send_to_al_local_dashboards_fn("dashboard_file_server", msg)



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
            self.send_to_al_local_dashboards_fn("dashboard_file_server", msg)
            # self.m_local_sio.emit("dashboard_file_server", msg, to=self.dashboard_room())

        
    def _on_server_data(self, data):    
        debug_print("Got server data")    
        self.m_local_sio.emit("remote_data", data)

    def _on_server_ymd_data(self, data):
        # debug_print("Got Data")

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

                    self.m_parent.create_remote_entry(self.m_remote_source, local_id, item )


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
        # tell remote server to request these files from us. 
        debug_print(data)

        for uid in data["upload_ids"]:
            debug_print((uid, self.m_rev_upload_id_map.get(uid, "Not found")))

        ids = [ self.m_rev_upload_id_map[uid] for uid in data["upload_ids"] if uid in self.m_rev_upload_id_map ]

        msg = {
            "source": self.m_node_source,
            "upload_ids": ids
        }
        self.m_remote_sio.emit("transfer_node_files", msg)

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

        # debug_print(msg)
        self.m_remote_sio.emit("request_server_ymd_data", msg)


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

        if self.m_remote_sio.connected:
            try:
                self.m_remote_sio.emit("remote_node_data", server_data)
                self.m_remote_sio.start_background_task(self.background_send_remote_node_data, blocks)
            except socketio.exceptions.BadNamespaceError as e:
                debug_print("Bad namespace error")



    def background_send_remote_node_data(self, blocks):
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
            self.m_remote_sio.emit("remote_node_data_block", msg)
            time.sleep(0.05)


    def _on_node_send(self, data):
        debug_print(data)
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


    def _background_send_files(self, server:str, filelist:list):
        local_status_event = "server_status_tqdm"
        remote_status_event = "node_status_tqdm"


        debug_print("enter")
        if self.m_send_threads:
            debug_print(f"Already getting file for {server} {self.m_send_threads}")
            return 

        self.m_send_threads = True

        self.m_signal = None

        url = f"http://{server}/file"

        source = self.m_config["source"]
        api_key_token = self.m_config["API_KEY_TOKEN"]
        split_size_gb = int(self.m_config.get("split_size_gb", 1))
        chunk_size_mb = int(self.m_config.get("chunk_size_mb", 1))
        read_size_b = chunk_size_mb * 1024 * 1024


        socket_events = [(self.m_local_sio, local_status_event, None),
                         (self.m_remote_sio, remote_status_event, None)]
        total_size = 0

        for  _, _, _, offset_b, file_size in filelist:
            total_size += file_size - offset_b

        source = self.m_config["source"]
        max_threads = self.m_config["threads"]
        message_queue = queue.Queue()
        desc = "File Transfer"


        def send_worker(args):
            debug_print("Enter")
            message_queue, project, relative_path, upload_id, offset_b, file_size, idx = args 

            dirroot = self.m_config["volume_map"].get(project, "/").strip("/")
            fullpath = os.path.join( self.m_config["volume_root"], dirroot, relative_path.strip("/"))

            name = f"{upload_id}_{idx}_{os.path.basename(relative_path)}" 
            # fullpath = os.path.join(dirroot, relative_path)

            if self.m_signal and self.m_signal == "cancel":
                return fullpath, False
            
            if not os.path.exists(fullpath):
                return fullpath, False  
            
            with open(fullpath, 'rb') as file:
                params = {}
                if offset_b > 0:
                    file.seek(offset_b)
                    params["offset"] = offset_b
                    file_size -= offset_b

                self.m_send_offsets[upload_id] = offset_b

                split_size_b = 1024*1024*1024*split_size_gb
                splits = file_size // split_size_b

                params["splits"] = splits

                headers = {
                    'Content-Type': 'application/octet-stream',
                    "X-Api-Key": api_key_token
                    }

                def read_and_update(upload_id, parent:RemoteConnection):
                    read_count = 0
                    while parent.connected():
                        if self.m_signal and self.m_signal == "cancel":
                            break

                        chunk = file.read(read_size_b)
                        if not chunk:
                            break
                        yield chunk

                        # Update the progress bars
                        chunck_size = len(chunk)
                        message_queue.put({"main_pbar": chunck_size})
                        message_queue.put({"child_pbar": name, "size": chunck_size, "action": "update", "total_size": file_size, "desc": desc})

                        parent.m_send_offsets[upload_id] += chunck_size
                        read_count += chunck_size

                        if read_count >= split_size_b:
                            break

                desc = "Sending " + os.path.basename(relative_path)
                message_queue.put({"child_pbar": name, "desc": desc, "size": file_size, "action": "start"})

                # with requests.Session() as session:
                for cid in range(1+splits):

                    if self.m_signal and self.m_signal == "cancel":
                        break

                    params["offset"] = self.m_send_offsets[upload_id]
                    params["cid"] = cid
                    response = requests.post(url + f"/{source}/{upload_id}", params=params, data=read_and_update(upload_id, self), headers=headers)
                    if response.status_code != 200:
                        debug_print(f"Error! {response.status_code} {response.content.decode()}")
                        break 

                message_queue.put({"child_pbar": name, "action": "close"})

                return fullpath, upload_id, True 

        pool_queue = [ (message_queue, dirroot, relative_path, upload_id, offset_b, file_size, idx) for idx, (dirroot, relative_path, upload_id, offset_b, file_size) in enumerate(filelist) ]

        thread = Thread(target=pbar_thread, args=(message_queue, total_size, source, socket_events, desc, max_threads))    
        thread.start()

        files = []

        try:
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                for filename, upload_id, status in executor.map(send_worker, pool_queue):
                    ## 
                    # update file entry 
                    msg = {
                        "div_id": f"status_{upload_id}",
                        "status": "On Device and Server",
                        "source": self.m_config["source"],
                        "on_device": True,
                        "on_server": True,
                        "upload_id": upload_id,
                    }
                    self.m_parent._send_dashboard_file(msg)

                    debug_print((filename, status))
                    files.append((filename, status))

        finally:
            message_queue.put({"close": True})


        # done 
        self.m_send_threads = None 

        pass 

    def _sendFiles(self, server, filelist):
        if self.m_send_threads:
            return 
        # self.m_send_threads = True
        self.m_local_sio.start_background_task(target=self._background_send_files, server=server, filelist=filelist)




    def disconnect(self):
        debug_print("Disconnect remote...")
        if self.m_remote_sio.connected:
            self.m_remote_sio.disconnect()
        if self.m_remote_source:
            self.m_parent.delete_remote_entries_for_source(self.m_remote_source)
            self.m_parent._send_server_data()

    def pull_files(self, data):
        debug_print("enter")
        if self.m_remote_sio.connected:
            self.m_remote_sio.emit("remote_transfer_files", data)