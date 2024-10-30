# from server.database import Database
from concurrent.futures import ThreadPoolExecutor
import math
import queue
import time

import requests
from server.debug_print import debug_print
from server.utils import SocketIORedirect, build_multipart_data, dashboard_room, get_device_name, get_source_by_mac_address, get_upload_id, get_datatype, pbar_thread, redis_pbar_thread
from server.sqlDatabase import Database

import redis
import yaml
import humanfriendly as hf
from datetime import datetime, timedelta
import json
import os
import shutil
import uuid
from threading import Event, Thread


class ServerWorker:
    def __init__(self, worker_id) -> None:
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=redis_host, port=6379, db=0)
        self.m_sio = SocketIORedirect()

        self.m_id = os.getpid()
        self.m_worker_id = worker_id
        self.m_exit_flag = Event()

        self.m_send_file_flag = Event()

        self.pubsub = self.redis.pubsub()
        self.m_database = None
        self.sources_set_key = 'connected_sources'

        self.m_secret_key = uuid.uuid4()

        self.m_config = {}
        self.m_volume_map_filename = os.environ.get("VOLUME_MAP", "config/volumeMap.yaml")
        self.m_keys_filename = os.environ.get("KEYSFILE", "config/keys.yaml")

        self._load_config()
        self._load_keys()

        debug_print("Soure is "  + self.m_config["source"])
        max_workers = self.m_config["threads"] * 2

        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        self._start_pubsub_listener()
        self._start_work_listener()


    def _load_keys(self):
        debug_print(f"- loading {self.m_keys_filename}")
        if os.path.exists(self.m_keys_filename):
            with open(self.m_keys_filename, "r") as f:
                keys = yaml.safe_load(f)
                self.m_config["API_KEY_TOKEN"] = keys.get("API_KEY_TOKEN", None)


    def emit(self, event:str, msg:any, to=None):
        data = {
            "event": event,
            "msg": msg
            }
        if to is not None:
            data["to"] = to

        self.redis.lpush("emit", json.dumps(data))


    def stop(self):
        self.m_exit_flag.set()

    def should_run(self):
        return not self.m_exit_flag.is_set()

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

        self.m_config["volume_map"] = volume_map.get("volume_map", {})
        self.m_config["source"] = get_source_by_mac_address() + "_" + str(self.m_config["port"])
        debug_print(f"Setting source name to {self.m_config['source']}")

        self.m_config["volume_root"] = os.environ.get("VOLUME_ROOT", "/")

        v_root = self.m_config.get("volume_root", "/")
        v_map = self.m_config.get("volume_map", {}).copy()
        for name in v_map:
            v_map[ name ] = os.path.join(v_root,  v_map.get(name, "").strip("/"))

        blackout = self.m_config.get("blackout", [])
        self.m_database = Database(v_map, blackout)


    # handle the remote entries redis data.
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

    def delete_remote_entry(self, source, upload_id):
        # Delete the entry from Redis
        self.redis.delete(f'remote_entries:{source}:{upload_id}')

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


    def set_node_data_stats(self, source, stats):
        debug_print("enter")
        stats_json = json.dumps(stats)
        self.redis.set(f"node_data_stats:{source}", stats_json)

    def get_node_data_stats(self, source):
        stats_json = self.redis.get(f"node_data_stats:{source}")
        if stats_json:
            return json.loads(stats_json)
        return None

    def clear_node_data_stats(self, source):
        self.redis.delete(f"node_data_stats:{source}")

    def get_sources(self, source_type):
        """Get the list of sources for a type

        Args:
          source_type: which type of source. One of [device, node]
        """
        sources = self.redis.smembers(f"{self.sources_set_key}:{source_type}")
        return [source.decode("utf-8") for source in sources]

    def add_source(self, source, source_type):
        """Add a new source. 

        Args:
          source: Name of source
          source_type: which type of source. One of [device, node]
        """
        self.redis.sadd(f"{self.sources_set_key}:{source_type}", source)

    # process messages that go out to all workers.  
    # these could be requests to update a data source
    # or other similar things. 
    # these are run in the current thread, so make them simple, or 
    # have the run themself in the background!
    def _process_message(self, channel:str, data:dict):
        if channel == "update_volume_map":
            self.update_volume_map()
    
        if channel == "action":
            action = data.get("action")
            if action == "reload_key":
                self._load_keys()
        else:
            debug_print(f"Unhandled message {channel}")
        pass


    def _start_pubsub_listener(self):
        def listen():
            for message in self.pubsub.listen():
                if message['type'] == 'message':
                    channel = message["channel"].decode("utf-8")
                    data = json.loads(message['data'])
                    self._process_message(channel, data)
        self.pubsub.subscribe("action", "upload_volume_map")
        listener_thread = Thread(target=listen)
        listener_thread.daemon = True
        listener_thread.start()

    def _run_action_in_background(self, action, data):
        self.executor.submit(self._run_action, action, data)
        # action_thread = Thread(target=self._run_action, args=(action, data))
        # action_thread.daemon = True
        # action_thread.start()

    def _run_action(self, action, data):
        # debug_print(f"action: {action}, data: {data}")

        if action == "get_server_data_stub":
            self._send_server_data(data)
        elif action == "get_server_data_ymd":
            self._send_server_ymd_data(data)
        elif action == "get_node_data_stub":
            self._send_node_data(data)
        elif action == "server_scan":
            self._scan_server(data)

        # device processing
        elif action == "device_revise_stats":
            self._device_revise_stats(data)
        elif action == "device_add_entry":
            self._device_add_entry(data)
        elif action == "get_device_data_stub":
            self._send_device_data_stub(data)
        elif action == "get_device_data_ymd":
            self._send_device_ymd_data(data)
        elif action == "device_request_files":
            self._device_request_files(data)

        # projects
        elif action == "request_projects_and_desc":
            self._request_projects_and_desc(data)
        elif action == "delete_project":
            self._delete_project(data)
        elif action == "add_project":
            self._add_project(data)
        elif action == "set_project":
            self._set_project(data)
        elif action == "edit_project":
            self._edit_project(data)

        # robot names
        elif action == "request_robot_names":
            self._request_robot_names(data)
        elif action == "add_robot_name":
            self._add_robot_name(data)
        elif action == "remove_robot_name":
            self._remove_robot_name(data)

        # sites
        elif action == "request_sites":
            self._request_sites(data)
        elif action == "add_site":
            self._add_site(data)
        elif action == "remove_site":
            self._remove_site(data)

        # remote entries
        elif action == "request_remote_servers":
            self._request_remote_servers(data)
        elif action == "add_remote_server":
            self._add_remote_server(data)
        elif action == "remove_remote_server":
            self._remove_remote_server(data)

        # entries
        elif action == "add_entry":
            self._add_entry(data)
        elif action == "estimate_runs":
            self._estimate_runs(data)
        elif action == "update_entry_robot":
            self._update_entry_robot(data)
        elif action == "update_entry_site":
            self._update_entry_site(data)

        # node 
        elif action == "remote_transfer_files":
            self._remote_transfer_files(data)
        elif action == "remote_cancel_transfer":
            self._cancel_transfer()

        elif action == "remote_node_data":
            self._remote_node_data(data)
        elif action == "remote_node_data_block":
            self._remote_node_data_block(data)
        elif action == "request_node_ymd_data":
            self._request_node_ymd_data(data)
        elif action == "check_local_ids":
            self._check_local_ids(data)

        # search 
        elif action == "request_search_filters":
            self._request_search_filters(data)
        elif action == "search":
            self._search(data)

        # other
        elif action == "request_localpath":
            self._request_localpath(data)
        elif action == "request_files_exist":
            self._request_files_exist(data)

        elif action == "debug_send":
            self._debug_send(data)


        else:
            debug_print(f"Unhandled action {action}")

    def _start_work_listener(self):
        # only want one thread at a time. 
        def work_listen():
            while not self.m_exit_flag.is_set():
                try:
                    # Wait for a message from the Redis queue
                    _, message = self.redis.brpop("work", timeout=1)
                    if message:
                        msg = json.loads(message.decode('utf-8'))
                        action = msg.get("action")
                        data = msg.get("data")
                        self._run_action_in_background(action, data)

                except TypeError:
                    # Handle timeout (when no message is received within the timeout period)
                    pass
        work_thread = Thread(target=work_listen)
        work_thread.daemon = True
        work_thread.start()



    def _get_fs_info(self):
        # todo: update this to use volume map
        rtn = {}
        for volume in self.m_config["volume_map"].values():
            volume_path = os.path.join(self.m_config["volume_root"], volume.strip("/"))
            if os.path.exists(volume_path):
                # dev = os.stat(volume_path).st_dev
                dev = get_device_name(volume_path)
                total, used, free = shutil.disk_usage(volume_path)
                free_percentage = (free / total) * 100
                rtn[dev] = (dev, f"{free_percentage:0.2f}")

        return rtn


    def get_remote_connection_address(self):
        address = self.redis.get("remote_connection")
        if address:
            return address.decode("utf-8")
        return None 

    # server data
    def _send_server_data(self, msg=None):
        data = self.m_database.get_send_data_ymd_stub()

        stats = self.m_database.get_run_stats()
        fs_info = self._get_fs_info()

        remote_address = self.get_remote_connection_address()
        remote_connected = remote_address != None

        remotes = self.m_database.get_remote_servers()

        server_data = {
            "entries": data,
            "fs_info": fs_info,
            "stats": stats,
            "source": self.m_config["source"],
            "remotes": remotes,
            "remote_connected": remote_connected,
            "remote_address": remote_address,
        }

        if msg:
            room = dashboard_room(msg)
            self.m_sio.emit("server_data", server_data, to=room)
        else:
            debug_print("Sending to all dashboards")
            self.m_sio.emit("server_data", server_data, to="all_dashboards")

    def _send_server_ymd_data(self, data):
        debug_print(data)
        tab = data.get("tab")
        names = tab.split(":")[-2:]
        session_token = data.get("session_token")

        # data_for indicates an intermediatary is getting the data
        data_for = data.get("data_for")
        # debug_print(f"data_for: {data_for}")

        project, ymd = names
        datasets = self.m_database.get_send_data_ymd(project, ymd)
        stats = self.m_database.get_run_stats(project, ymd)
        room = dashboard_room(data)
        total = len(datasets)

        for node in self.get_sources("node"):
            for dataset in datasets:
                for run in dataset:
                    for entries in dataset[run].values():
                        for entry in entries:
                            try:
                                remote_entry = self.fetch_remote_entry(node, entry["upload_id"])
                                entry["on_node"] = remote_entry != None
                            except TypeError as e:
                                debug_print(entry)
                                raise e
                    

        for i, data in enumerate(datasets):
            server_data = {
                "total": total,
                "index": i,
                "runs": data,
                "stats": stats,
                "source": self.m_config["source"],
                "project": project,
                "ymd": ymd,
                "tab": tab,
                "session_token": session_token,
                "data_for": data_for
            }

            self.m_sio.emit("server_ymd_data", server_data, to=room, debug=False)

    # device data 
    def _device_revise_stats(self, data):
        sources = data.get("source")
        stats = {}

        if sources is None:
            return 
        
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

        self.m_sio.emit("device_revise_stats", stats, to="all_dashboards")

    def _device_add_entry(self, data):
        entry = data.get("entry")
        source = data.get("source")

        dirroot = entry.get("dirroot")
        file = entry.get("filename")
        size = entry.get("size")
        start_datetime = entry.get("start_time")
        end_datetime = entry.get("end_time")
        md5 = entry.get("md5")
        robot_name = entry.get("robot_name")
        if robot_name and len(robot_name) > 0:
            if not self.m_database.has_robot_name(robot_name):
                # debug_print("=================== adding " + robot_name)
                self.m_database.add_robot_name(robot_name, "")
                self._request_robot_names({"room":"all_dashboards"})
                
        site = entry.get("site")
        topics = entry.get("topics", {})
        project = self.device_get_project(source)

        upload_id = get_upload_id(source, project, file)

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
            "temp_size": 0
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
        entry["localpath"] = filepath

        # debug_print(f"added {source} {upload_id}")
        self.create_remote_entry(source, upload_id, entry)

    def _get_device_fs_info(self, source):
        fs_info_json = self.redis.get(f'fs_info:{source}')
        if fs_info_json:
            return json.loads(fs_info_json)
        return None


    def _send_device_data_stub(self, msg=None):
        # debug_print("enter")
        device_data = self._get_device_data_stub()
        for source in device_data:

            stats = self._get_device_data_stats(source)
            if stats:
                device_data[source]["stats"] = stats["stats"]

        debug_print(sorted(device_data.keys()))
        self.m_sio.emit("device_data", device_data, to="all_dashboards") 

    def _get_device_data_stats(self, source):
        device_data = {}        
        entries = self.get_all_entries_for_source(source)

        debug_print(f"entries: {len(entries)}")

        for remote_entry in entries.values():
            uid = remote_entry["upload_id"]
            entry = {}
            for key in ["size", "site", "robot_name", "upload_id", "on_device", "on_server", "basename", "datetime", "topics" ]:
                entry[key] = remote_entry[key]

            entry["size"] = hf.format_size(entry["size"])
            date = remote_entry["datetime"].split(" ")[0]

            device_data["stats"] = device_data.get(
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
            device_data["stats"][date] = device_data["stats"].get(
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

            self._update_stat(source, uid, device_data["stats"][date])
            self._update_stat(source, uid, device_data["stats"]["total"])

        return device_data


    def _get_device_data_stub(self, msg=None):
        debug_print("enter")
        device_data = {}
        count = 0

        sources = self.get_sources("device")
        debug_print(sources)
        for source in sources:
            count = 0
            entries = self.get_all_entries_for_source(source)
            if entries is None or len(entries) == 0:
                debug_print("No entries")
                continue

            # project = self.m_projects.get(source)
            project = self.device_get_project(source)
            # debug_print(f" project for {source} is {project}, {self.m_id}")
            device_data[source] = {"fs_info": {}, "entries": {}, "project": project}

            fs_info = self._get_device_fs_info(source)
            if fs_info:
                device_data[source]["fs_info"] = fs_info

            for entry in entries.values():
                count += 1

                date = entry["datetime"].split(" ")[0]
                relpath = entry["relpath"]
                device_data[source]["entries"][date] = device_data[source]["entries"].get(date, {})
                device_data[source]["entries"][date][relpath] = device_data[source]["entries"][date].get(relpath, [])
        
            debug_print(f"count {count} {source}")
        return device_data

    def _send_device_ymd_data(self, data):
        tab = data.get("tab")
        names = tab.split(":")[-2:]

        source, ymd = names
        datasets = self._get_device_data_ymd(source, ymd)
        stats = self._get_device_run_stats(source, ymd)
        room = data.get("room", "all_dashboards")
        total = len(datasets)


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

    def _get_device_data_ymd(self, source, ymd):
        rtnarr = []
        rtn = {}
        # will send up to max count entries per packet
        max_count = 100
        count = 0 
        total = 0
        
        entries = self.get_all_entries_for_source(source)
        if len(entries) == 0:
            debug_print(f"Source: {source} missing")
            return 

        # debug_print(f"ymd: {ymd}, len(entries): {len(entries)}")

        for remote_entry in entries.values():
            if ymd != remote_entry["date"]:
                continue 
            # date = remote_entry["datetime"].split(" ")[0]
            # if date != ymd:
            #     continue

            entry = {}
            for key in ["size", "site", "robot_name", "upload_id", "on_device", "on_server", "basename", "datetime", "topics" ]:
                entry[key] = remote_entry[key]

            entry["hsize"] = hf.format_size(remote_entry["size"])
            relpath = remote_entry["relpath"]

            rtn[relpath] = rtn.get(relpath, [])
            rtn[relpath].append(entry)

            count += 1
            total += 1 
            if count >= max_count:
                rtnarr.append(rtn)
                rtn = {}
                count = 0
        rtnarr.append(rtn)
        # debug_print(f"ymd: {ymd}, total: {total}")
        return rtnarr 

    def _update_stat(self, source, uid, stat):
        entry = self.fetch_remote_entry(source, uid)
        if entry:
            self._update_stat_for_entry(entry, stat)
        else: 
            debug_print(f"Did not find {source} {uid}")

    def _get_device_run_stats(self, source, ymd):
        device_data = {}
        
        sources = self.get_sources("device")
        for source in sources:                
            # project = self.m_projects.get(source)
            project = self.device_get_project(source)
            device_data[source] = {"fs_info": {}, "entries": {}, "project": project}

            fs_info = self._get_device_fs_info(source)
            if fs_info:
                device_data[source]["fs_info"] = fs_info

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

    def _device_request_files(self, data):
        selected_files = data.get("files")
        source = data.get("source")

        filenames = []
        for upload_id in selected_files:
            entry = self.fetch_remote_entry(source, upload_id)
            if not entry:
                debug_print(
                    f"Error! did not find upload id [{upload_id}] in redis remote entries"
                )
                continue

            filepath = self._get_file_path_from_entry(entry)
            if os.path.exists(filepath):
                continue

            dirroot = entry["dirroot"]
            relpath = entry["fullpath"].strip("/")
            tmp = filepath + ".tmp"
            offset = 0
            if os.path.exists(tmp):
                offset = os.path.getsize(tmp)
            size = entry["size"]

            debug_print((filepath, dirroot, relpath, upload_id, offset, size))
            filenames.append((dirroot, relpath, upload_id, offset, size))

        # clear cancel first
        self.redis.delete(f'cancel:{source}')

        msg = {"source": data.get("source"), "files": filenames}
        self.m_sio.emit("device_send", msg, to=source)


    # add / remove database entries
    def _add_entry(self, data):
        entry = data.get("entry")
        self.m_database.add_entry(entry)
        # self.m_database._set_runs()

    def _estimate_runs(self, data):
        self.m_database._set_runs()
        self.m_sio.emit("has_new_data", {"value": True}, to="all_dashboards")

    # remote server:
    def _request_remote_servers(self, data={}):
        room = data.get("room")
        servers = self.m_database.get_remote_servers()
        servers = sorted(servers)
        self.m_sio.emit("remote_server_names", {"data": servers}, to=room)

    def _add_remote_server(self, data):
        server = data.get("server")
        desc = data.get("desc", "")
        self.m_database.add_remote_server(server, desc)
        self._request_remote_servers({"room": "all_dashboards"})

    def _remove_remote_server(self, data):
        server = data.get("server")
        self.m_database.remove_remote_server(server)
        self._request_remote_servers({"room": "all_dashboards"})


    # robots
    def _request_robot_names(self, data={}):
        room = data.get("room")
        robot_names = self.m_database.get_robots()
        robot_names = sorted(robot_names)
        self.m_sio.emit("robot_names", {"data": robot_names}, to=room)
    
    def _add_robot_name(self, data):
        robot_name = data.get("robot")
        desc = data.get("desc", "")
        self.m_database.add_robot_name(robot_name, desc)
        self._request_robot_names({"room": "all_dashboards"})
        # self._request_robot_names()

    def _remove_robot_name(self, data):
        robot_name = data.get("robot_name")
        self.m_database.remove_robot_name(robot_name)
        self._request_robot_names({"room": "all_dashboards"})
        

    def _update_entry_robot(self, data):
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

    # sites 
    def _request_sites(self, data):
        room = data.get("room")
        sites = self.m_database.get_sites()
        sites = sorted(sites)
        self.m_sio.emit("site_names", {"data": sites}, to=room)

    def _add_site(self, data):
        debug_print(data)
        site = data.get("site")
        desc = data.get("desc", "")
        self.m_database.add_site(site, desc)
        self._request_sites({"room": "all_dashboards"})

    def _remove_site(self, data):
        site = data.get("site")
        self.m_database.remove_site(site)
        self._request_sites({"room": "all_dashboards"})

    def _update_site(self, data):
        site = data.get("site")
        desc = data.get("desc", "")
        self.m_database.update_site(site, desc)
        self._request_sites({"room": "all_dashboards"})

    def _update_entry_site(self, data):
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


    # projects 
    def _request_projects_and_desc(self, data):
        room = data.get("room")
        projects = self.m_database.get_projects_and_desc()
        items = [ {"project":i[0], "description":i[1]  }  for i in projects]
        for item in items:
            item["volume"] = self.m_config["volume_map"].get(item["project"], "")
        
        debug_print(items)
        self.m_sio.emit("project_names", {"data": items, "volume_root": self.m_config["volume_root"]}, to=room)

    def _add_project(self, data):
        debug_print(data)
        name = data.get("project")
        desc = data.get("description")
        volume = data.get("volume")
        self.m_database.add_project(name, desc)

        if volume:
            self.m_config["volume_map"][name] = volume

            with open(self.m_volume_map_filename, "w") as f:
                volume_map = {"volume_map":  self.m_config["volume_map"]}
                yaml.dump(volume_map, open(self.m_volume_map_filename, "w"))            
            self.redis.publish("update_volume_map", "{}")
            self.redis.publish("websocket_action", json.dumps({'action': 'reload_volume_map'}))

        self._request_projects_and_desc({"room":"all_dashboards"})

    def _delete_project(self, data):
        name = data.get("project")
        self.m_database.remove_project(name)
        if name in self.m_config["volume_map"]:
            del self.m_config["volume_map"][name]

        with open(self.m_volume_map_filename, "w") as f:
            volume_map = {"volume_map":  self.m_config["volume_map"]}
            yaml.dump(volume_map, open(self.m_volume_map_filename, "w"))            
        self.redis.publish("update_volume_map", "{}")
        self.redis.publish("websocket_action", json.dumps({'action': 'reload_volume_map'}))
        self._request_projects_and_desc({"room":"all_dashboards"})

    def _edit_project(self, data):
        debug_print(data)
        name = data.get("project")
        desc = data.get("description")
        volume = data.get("volume")

        self.m_database.update_project(name, desc)
        
        volume_map_changed = False
        if self.m_config["volume_map"].get(name, "") != volume:
            self.m_config["volume_map"][name] = volume
            volume_map_changed = True

        if volume_map_changed:
            debug_print("v_map changed")
            with open(self.m_volume_map_filename, "w") as f:
                volume_map = {"volume_map":  self.m_config["volume_map"]}
                yaml.dump(volume_map, open(self.m_volume_map_filename, "w"))            
            self.redis.publish("update_volume_map", "{}")
            self.redis.publish("websocket_action", json.dumps({'action': 'reload_volume_map'}))

        self._request_projects_and_desc({"room":"all_dashboards"})

    def _set_project(self, data):
        source = data["source"]
        self.m_sio.emit("set_project", data, to=source)

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


    def update_volume_map(self):  
        debug_print("enter")      
        volume_map = None
        if os.path.exists(self.m_volume_map_filename):
            with open(self.m_volume_map_filename, "r") as f:
                volume_map = yaml.safe_load(f)

        if volume_map is None:
            volume_map = {"volume_map": {"room":"all_dashboards"}}

        self.m_config["volume_map"] = volume_map.get("volume_map", {})
        self.m_database.update_volume_map(self.m_config["volume_map"])

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

    def _request_localpath(self, data:dict):
        upload_id = data["upload_id"]
        response_queue = data["response_queue"]

        localpath = None 
        entry = self.m_database.get_entry(upload_id)
        if entry:
            localpath = entry["localpath"]
        
        self.redis.lpush(response_queue, localpath)

    def _request_files_exist(self, data:dict):
        rtn = []
        room = dashboard_room(data)
        data_for = data.get("data_for", None)
        entries = data["entries"]
        for entry in entries:
            filepath = self._get_file_path_from_entry(entry)
            entry["on_remote"] = os.path.exists(filepath)
            rtn.append(entry)
        msg = {
            "entries": rtn,
            "data_for": data_for,
            "source": self.m_config["source"]
        }
        self.m_sio.emit("request_files_exist_rtn", msg, to=room) 

    def _remote_transfer_files(self, data):
        debug_print(f"{data}")
        url = data["url"]
        files = data["files"]
        source = self.m_config["source"]
        selected = []

        for row in files:
            project, filepath, upload_id, offset, size, remote_id = row 
            entry = self.m_database.get_entry(remote_id)
            # debug_print(entry)
            selected.append( (source, project, filepath, upload_id, offset, size, remote_id, entry))

        self._send_files(selected, url)

    # remote node data
    def _remote_node_data(self, data):
        source = data["source"]
        stats = data["stats"]
        self.add_source(source, "node")

        self.redis.delete(f"node_data_blocks:{source}")
        self.set_node_data_stats(source, stats)

    def _remote_node_data_block(self, data):
        source = data["source"]
        total = data["total"]
        block = data["block"]
        id = data["id"]

        debug_print(f"received {source} {id}/{total}")
        rtn = {}

        for entry in block:
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
            filepath = self._get_file_path_from_entry(entry)

            entry["on_local"] = False 
            entry["on_remote"] = True

            if os.path.exists(filepath):
                entry["on_server"] = True
                entry["on_local"] = True

            if os.path.exists(filepath + ".tmp"):
                entry["temp_size"] = (
                    os.path.getsize(filepath + ".tmp")
                )
            else:
                entry["temp_size"] = 0

            rtn[upload_id] = entry

            # self.m_node_entries[source] = self.m_node_entries.get(source, {"entries": {}, "stats": {}})
            # self.m_node_entries[source]["entries"][project] = self.m_node_entries[source]["entries"].get(project, {})
            # self.m_node_entries[source]["entries"][project][ymd] = self.m_node_entries[source]["entries"][project].get(ymd, {})
            # self.m_node_entries[source]["entries"][project][ymd][run_name] = self.m_node_entries[source]["entries"][project][ymd].get(run_name, {})
            # self.m_node_entries[source]["entries"][project][ymd][run_name][relpath] = self.m_node_entries[source]["entries"][project][ymd][run_name].get(relpath, [])
            # self.m_node_entries[source]["entries"][project][ymd][run_name][relpath].append(entry)

            # debug_print(f"added {upload_id}")
            self.create_remote_entry(source, upload_id, entry)


        # debug_print(f"emit rtn to {source}")
        msg = {"entries": rtn}
        self.m_sio.emit("node_data_block_rtn", msg, to=source)


        self.redis.sadd(f"node_data_blocks:{source}", id)
        arrived = self.redis.smembers(f"node_data_blocks:{source}")

        if len(arrived) == total:
            # all blocks has been processed. 
            self._send_node_data()
            pass 


    def _create_node_data_stub(self):
        rtn = {}

        sources = self.get_sources("node")
        # debug_print(sources)
        for source_name in sources:
            entries = self.get_all_entries_for_source(source_name)
            # debug_print(len(entries))
            rtn[source_name] = {}
            for entry in entries.values():
                project = entry["project"]
                ymd = entry["date"]
                rtn[source_name][project] = rtn[source_name].get(project, {})
                rtn[source_name][project][ymd] = rtn[source_name][project].get(ymd, {})
        return rtn 


    def _send_node_data(self, msg=None):

        stats = {}
        for source in self.get_sources("node"):
            full_stats = self.get_node_data_stats(source)
            stats[source] = {"total": full_stats.get("total", {})}

        node_data = {
            "entries": self._create_node_data_stub(),
            "fs_info": {},
            "stats": stats
            }
        
        if msg:
            room = dashboard_room(msg)
        else:
            room = "all_dashboards"

        # debug_print(f"Sending to {room}")
        self.m_sio.emit("node_data", node_data, to=room, debug=False)

    def _request_node_ymd_data(self, data):
        debug_print(f"enter {data}")

        # request data to go to the node tab
        tab = data.get("tab")
        names = tab.split(":")
        _, source, project, ymd = names

        runs = {}

        entries = self.get_all_entries_for_source(source)
        if entries:
            for entry in entries.values():
                if entry["project"] != project:
                    continue
                if entry["date"] != ymd:
                    continue

                run_name = entry["run_name"]
                rel_path = entry["relpath"]
                # debug_print(f"remote_id: {entry['remote_id']}")
                runs[run_name] = runs.get(run_name, {})
                runs[run_name][rel_path] = runs[run_name].get(rel_path, [])
                runs[run_name][rel_path].append(entry)


        stats = self.get_node_data_stats(source)
        if stats:
            stats_data = stats.get(project, {}).get(ymd, {})
        else:
            stats_data = {}


        msg = {
            "tab": tab,
            "runs": runs,
            "stats": stats_data,
            "source": source,  
            "project": project,
            "ymd": ymd
        }
        self.m_sio.emit("node_ymd_data", msg, to=dashboard_room(data))

        pass 

    def _check_local_ids(self, data):
        names = data.get("names")
        # check each id and see if it is in the data.
        # if it is, update the status to show it is on the remote server.
        existing_ids = self.m_database.find_upload_ids(names)

        # debug_print(existing_ids)
        for upload_id in existing_ids:
            # debug_print(upload_id)
            # send "dashboard_file" for each of the existing itmes
            msg = {
                "div_id": f"server_select_{upload_id}",
                "status": "On Device and Server",
                "source": self.m_config["source"],
                "on_server": True,
                "on_device": True,
                "upload_id": upload_id,
            }
            self.m_sio.emit("dashboard_file", msg, to="all_dashboards")



    def _cancel_transfer(self):
        debug_print("Cancel transfer!")
        self.m_send_file_flag.set()

    def _debug_send(self, data):

        message_queue = queue.Queue()

        total_size = 1000
        chunk_size = 100
        source = self.m_config["source"]
        socket_events = [("local_sio", "server_status_tqdm", "all_dashboards_and_all_nodes")]
        desc = "test"
        max_threads = 2



        thread = Thread(target=redis_pbar_thread, args=(message_queue, total_size, source, socket_events, desc, max_threads))    
        thread.start()

        name = "name" 
        message_queue.put({"child_pbar": name, "desc": "child_" + desc, "size": total_size, "action": "start"})

        for i in range( total_size // chunk_size ):            
            message_queue.put({"main_pbar": chunk_size})
            message_queue.put({"child_pbar": name, "size": chunk_size, "action": "update", "total_size": total_size, "desc": "child_" +desc})
            time.sleep(2)

        message_queue.put({"child_pbar": name, "action": "close"})
        message_queue.put({"close": True})


    # node send file
    def _send_files(self, filelist, base_url):
        self.m_send_file_flag.clear()
        url = f"{base_url}/file"

        source = self.m_config["source"]
        api_key_token = self.m_config["API_KEY_TOKEN"]
        split_size_gb = int(self.m_config.get("split_size_gb", 1))
        chunk_size_mb = int(self.m_config.get("chunk_size_mb", 1))
        read_size_b = chunk_size_mb * 1024 * 1024
        total_size = 0

        socket_events = [("local_sio", "server_status_tqdm", "all_dashboards_and_all_nodes")]


        # debug_print(f"API Key Token is {api_key_token}")
    
        for _, _, _, _, offset_b, file_size, _, _ in filelist:
            offset_b = int(offset_b)
            file_size = int(file_size)
            total_size += file_size - offset_b

        source = self.m_config["source"]
        max_threads = self.m_config["threads"]
        message_queue = queue.Queue()
        desc = "File Transfer"

        def send_worker(args):
            debug_print("Enter")
            message_queue, source, project, file, upload_id, offset_b, file_size, remote_id, idx = args 
            file_size = int(file_size)
            offset_b = int(offset_b)

            entry = self.m_database.get_entry(upload_id)
            if entry is None:
                entry = self.m_database.get_entry(remote_id)

            for key in ["datetime", "start_datetime", "end_datetime"]:
                entry[key] = entry[key].strftime("%Y-%m-%d %H:%M:%S")

            entry["date"] = entry["date"].strftime("%Y-%m-%d")

            dirroot = self.m_config["volume_map"].get(project, "/").strip("/")
            volume_root = self.m_config.get("volume_root", "/") 
            fullpath = os.path.join( volume_root, dirroot, file.strip("/"))

            # fullpath = self._get_file_path_from_entry(entry)
            if not os.path.exists(fullpath):
                fullpath =  os.path.join( volume_root, file.strip("/"))
                if not os.path.exists(fullpath):
                    debug_print(f"File not found {volume_root}, {dirroot}, {file.strip('/')} ")
                    return fullpath, False

            name = f"{upload_id}_{idx}_{os.path.basename(file)}" 

            total_size = os.path.getsize(fullpath)

            with open(fullpath, 'rb') as fp:
                params = {}
                if offset_b > 0:
                    fp.seek(offset_b)
                    params["offset"] = offset_b 
                    total_size -= offset_b 
                
                def read_and_update():
                    while True:
                        # Read the file in chunks of 4096 bytes (or any size you prefer)
                        chunk = fp.read(read_size_b)
                        if not chunk:
                            break
                        yield chunk
                        # Update the progress bars
                        chunck_size = len(chunk)
                        message_queue.put({"main_pbar": chunck_size})
                        message_queue.put({"child_pbar": name, "size": chunck_size, "action": "update", "total_size": file_size, "desc": desc})
                        
                        if self.m_send_file_flag.is_set():
                            break
                    
                multipart_stream, boundary, content_length = build_multipart_data(entry, read_and_update(), total_size)

                # Set headers
                headers = {
                        "Authorization": f"Bearer {api_key_token}",
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                    }

                desc = "Sending " + os.path.basename(file)
                message_queue.put({"child_pbar": name, "desc": desc, "size": file_size, "action": "start"})

                response = requests.post(url + f"/{source}/{upload_id}", data=multipart_stream, headers=headers)
                
                rtn = True
                if response.status_code != 200:
                    debug_print(("Error uploading file:", response.text, response.status_code))
                    rtn = False

                message_queue.put({"child_pbar": name, "action": "close"})
                if rtn:
                    debug_print(remote_id)
                    msg = {
                        "status": "On Device and Server",
                        "source": self.m_config["source"],
                        "on_device": True,
                        "on_server": True,
                        "upload_id": remote_id,
                    }
                    try:
                        self.m_sio.emit("dashboard_file", msg, to="all_dashboards")
                    except TypeError as e:
                        debug_print(msg)
                        raise e

                return fullpath, rtn
            

        pool_queue = [ (message_queue, source, project, file, upload_id, offset_b, total_size, remote_id,  idx ) for idx, (source, project, file, upload_id, offset_b, total_size, remote_id, entry ) in enumerate(filelist) ]

        thread = Thread(target=redis_pbar_thread, args=(message_queue, total_size, source, socket_events, desc, max_threads))    
        thread.start()

        files = []

        try:
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                for filename, status in executor.map(send_worker, pool_queue):
                    debug_print((filename, status))
                    files.append((filename, status))

        finally:
            message_queue.put({"close": True})


        # done 
        self.m_send_threads = None 



    ## search 
    def _request_search_filters(self, data):
        search_filters = self.m_database.get_search_filters()
        room = dashboard_room(data)
        self.m_sio.emit("search_filters", search_filters, to=room)

    def _search(self, data):
        room = data.get("room", None)
        filter = data.get("filter", {})
        sort_key = data.get("sort-key", "datetime")
        reverse = data.get("sort-direction", "forward") == "reverse"
        page_size = data.get("results-per-page", 25)
        offset = data.get("start_index", 0)

        if sort_key == "filename":
            sort_key = "basename"

        # do the search
        results, total = self.m_database.search(filter, sort_key, offset, page_size, reverse)

        # format the search
        total_pages = int(math.ceil(float(total)/float(page_size)))
        current_page = int(offset) // int(page_size)
        msg = {
            "total_pages": total_pages,
            "current_page": current_page,
            "current_index": offset,
            "results": results
        }
        self.m_sio.emit("search_results", msg, to=room)



    ##### debug

    def _scan_server(self, data):
        event = "server_regen_msg"
        debug_print("Scanning server")
        self.m_database.regenerate(event=event)

        self._send_server_data({})
