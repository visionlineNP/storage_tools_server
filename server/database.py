# stub for database.


import json
import os
import pathlib
import threading
from flask_socketio import SocketIO
import humanfriendly
from datetime import datetime, timedelta
import hashlib
from tqdm import tqdm 

from .debug_print import debug_print
from .throttledEmit import ThrottledEmit 


class VolumeMapNotFound(Exception):
    def __init__(self, project_name:str) -> None:
        msg = f"Failed to find volume mapping for {project_name}"
        super().__init__(msg)


def get_upload_id(source: str, project: str, file: str):
    """
    Generates a unique upload ID based on the provided source, project, name, and file information.

    Args:
        source (str): The source of the upload.
        project (str): The project associated with the upload.
        name (str): The name of the upload.
        file (str): The file path or name being uploaded.

    Returns:
        str: A unique upload ID generated from the provided information.
    """
    val = f"{source}_{project}_{file.strip('/')}"
    val = val.replace("/", "_")
    val = val.replace(".", "_")
    # Use 'return val' when debugging issues with id missmatch
    # return val
    hash_object = hashlib.md5(val.encode())
    return hash_object.hexdigest()


class Database:
    def __init__(self, root, source, volume_map, blackout) -> None:
        self.source = source
        self.root = root
        self.filename = pathlib.Path(root) / "database.json"
        debug_print(f"-- Loading {self.filename.as_posix()}")
        self.mutex = threading.Lock()
        self.volume_map = volume_map
        self.blackout = blackout
        self._init_db(self.filename)

    # def filter_db(self):
    #     data = []
    #     debug_print(f"starting with {len(self.database['data'])}")
    #     for entry in self.database["data"]:
    #         basename = entry.get("basename")
    #         if basename.startswith("frame_") and basename.endswith("png"):
    #             continue
    #         data.append(entry)
    #     debug_print(f"end with {len(data)}")
    #     self.database["data"] = data

    def _init_db(self, filename=None):
        if filename and filename.exists():
            self.database = json.load(filename.open("r"))
        else:
            self.database = {
                "projects": [],
                "robots": [
                    ["None", "For entries that are not associated with a robot"]
                ],
                "runs": [],
                "data": [],
                "sites": [
                    [None, "Default for data without a site."],
                ],
            }

    def regenerate(self, sio=None, event=None, room=None):
        # init db without file to create new db.
        self._init_db()

        emit = None 
        if sio and event:
            emit = ThrottledEmit(sio, event, room=room)

        for project in sorted(self.volume_map):
            volume_root = self.volume_map[project]

            debug_print((project, volume_root))
            for root, _, files in os.walk(volume_root):
                skip = False
                for b in self.blackout:
                    if b in root:
                        skip = True 
                if skip:
                    continue

                if emit:
                    msg = f"Scanning {root}"
                    emit.emit(msg)

                # debug_print(root)
                for basename in tqdm(files, desc=f"Processing {root}", leave=False):
                    if basename == "database.json":
                        continue
                    if basename.endswith(".metadata"):
                        base = ".".join(basename.split(".")[:-1])
                        filename = os.path.join(root, base)
                        entry = json.load(open(os.path.join(root, basename), "r"))
                        entry["localpath"] = filename
                        entry["dirroot"] = volume_root
                        # entry["reldir"] = root.replace(volume_root, "").strip()
                        # entry["upload_id"] = str(hex(abs(hash(filename))))
                        self.add_data(entry)

        if emit:
            emit.close()

        self.estimate_runs()
        self.commit()

    def commit(self):
        with self.mutex:
            with self.filename.open("w") as f:
                json.dump(self.database, f, indent=True, sort_keys=True),

    def update_volume_map(self, volume_map:dict):
        self.volume_map = volume_map.copy()

    def _add_name(self, table: str, name: str, description: str):
        with self.mutex:
            name_to_index = {
                name_: i for i, (name_, _) in enumerate(self.database[table])
            }
            if name in name_to_index:
                return name_to_index[name]
            self.database[table].append((name, description))
            return len(self.database[table]) - 1

    def add_project(self, name: str, description: str):
        self._add_name("projects", name, description)

    def edit_project(self, name:str, description:str):
        table = "projects"
        changed = False
        for entry in self.database[table]:
            if entry[0] == name:
                if entry[1] != description:
                    entry[1] = description
                    changed = True 
        return changed

    """
    Returns true if deleted. 
    """
    def delete_project(self, name:str):        
        table = "projects"
        origin_len = len(self.database[table])
        self.database[table] = [entry for entry in self.database[table] if entry[0] != name]
        return len(self.database[table]) != origin_len

    def add_robot_name(self, name: str, description: str):
        if not self._has_name("robots", name):
            self._add_name("robots", name, description)

    def add_site(self, name: str, description: str):
        self._add_name("sites", name, description)

    def _get_names(self, table: str):
        rtn = []
        with self.mutex:
            for i, (name, desc) in enumerate(self.database[table]):
                rtn.append((i, name, desc))
        return rtn

    def _has_name(self, table:str, name:str):
        with self.mutex:
            for name_, _ in self.database[table]:
                if name_ == name:
                    return True 
        return False 

    def has_robot_name(self, name:str)-> bool:
        return self._has_name("robots", name)

    def get_projects(self):
        names =self._get_names("projects")
        names = sorted(list(set(names)))
        return names

    def get_robots(self):
        return self._get_names("robots")

    def get_sites(self):
        return self._get_names("sites")

    def _get_name_id(self, table: str, name: str) -> int:
        with self.mutex:
            name_to_index = {
                name: i for i, (name, _) in enumerate(self.database[table])
            }
            idx = name_to_index.get(name, -1)
        if idx == -1:
            return self._add_name(table, name, "")
        return name_to_index[name]

    def get_project_id(self, name):
        return self._get_name_id("project", name)

    def get_robot_id(self, name):
        return self._get_name_id("robot", name)

    def get_site_id(self, name):
        return self._get_name_id("sites", name)

    def _get_name(self, table, idx):
        with self.mutex:
            if idx > -1 and idx < len(self.database[table]):
                return self.database[table][idx][1]
            return None

    def get_project_name(self, idx):
        return self._get_name("projects", idx)

    def get_robot_name(self, idx):
        return self._get_name("robots", idx)

    def get_site_name(self, idx):
        return self._get_name("sites", idx)

    def add_run(self, project, site, robot_name, run_name, duration, total_size):
        with self.mutex:
            name_to_index = {
                (entry[0], entry[1], entry[2], entry[3]): i
                for i, entry in enumerate(self.database["runs"])
            }
        project_idx = self.get_project_id(project)
        robot_idx = self.get_robot_id(robot_name)
        site_idx = self.get_site_id(site)

        key = (project_idx, site_idx, robot_idx, run_name)
        if key in name_to_index:
            return name_to_index[key]

        with self.mutex:
            self.database["runs"].append(
                (project_idx, site_idx, robot_idx, run_name, duration, total_size)
            )
            return len(self.database["runs"]) - 1

    def get_runs(self):
        rtn = []
        for i, entry in enumerate(self.database["runs"]):
            project = self.get_project_name(entry[0])
            site = self.get_site_name(entry[1])
            name = self.get_robot_name(entry[2])
            row = [i, project, site, name]
            row.extend(entry[2:])

            rtn.append(row)
        return rtn

    def add_data(self, entry: dict):
        # datatype = entry["datatype"]
        # date = entry["datetime"]
        basename = entry["basename"]
        reldir = entry["relpath"]
        # size = entry["size"]
        site = entry["site"]

        project = entry["project"]
        robot = entry["robot_name"]
        # run = entry["run_name"]

        fullpath = f"{reldir}/{basename}"

        with self.mutex:
            name_to_index = {
                f"{item['relpath']}/{item['basename']}": i
                for i, item in enumerate(self.database["data"])
            }
        if fullpath in name_to_index:
            return 
        else:
            self.add_project(project, "")
            self.add_robot_name(robot, "")
            self.add_site(site, "")
            local_entry = entry.copy()

            file = os.path.join(entry["relpath"], entry["basename"])

            local_entry["upload_id"] = get_upload_id(self.source, project, file)
            with self.mutex:
                self.database["data"].append(local_entry)

    def get_data(self):
        rtn = {}
        for entry in self.database["data"]:
            project = entry["project"]
            robot = entry["robot_name"]
            run = entry["run_name"]

            datatype = entry["datatype"]
            date = entry["datetime"]
            ymd = date.split(" ")[0]
            basename = entry["basename"]
            relpath = entry["relpath"]
            size = entry["size"]
            site = entry["site"]

            rtn[project] = rtn.get(project, {})
            rtn[project][robot] = rtn[project].get(robot, {})
            rtn[project][robot][run] = rtn[project][robot].get(run, [])
            rtn[project][robot][run].append(
                {
                    "datetime": date,
                    "relpath": relpath,
                    "basename": basename,
                    "size": size,
                    "site": site,
                    "run_name": run,
                    "datatype": datatype,
                }
            )
        return rtn

    def get_node_data(self):
        rtn = {}
        for entry in self.database["data"]:
            project = entry["project"]
            run = entry["run_name"]
            date = entry["datetime"]
            ymd = date.split(" ")[0]
            relpath = entry["relpath"]

            rtn[project] = rtn.get(project, {})
            rtn[project][ymd] = rtn[project].get(ymd, {})
            rtn[project][ymd][run] = rtn[project][ymd].get(run, {})
            rtn[project][ymd][run][relpath] = rtn[project][ymd][run].get(relpath, [])
            node_entry = {
                "reldir": relpath,
                "on_local": False,
                "on_remote": True,
                "hsize": humanfriendly.format_size(entry["size"]),
                "topics": entry.get("topics", []),
            }
            node_entry.update(entry)
            # node_entry["dirroot"] = self.root

            rtn[project][ymd][run][relpath] = rtn[project][ymd][run].get(relpath, [])
            rtn[project][ymd][run][relpath].append(node_entry)

        return rtn

    def get_send_data_ymd_stub(self):

        rtn = {}
        for entry in self.database["data"]:
            project = entry["project"]
            date = entry["datetime"]
            ymd = date.split(" ")[0]

            rtn[project] = rtn.get(project, {})
            rtn[project][ymd] = rtn[project].get(ymd, {})
        return rtn

    def get_send_data_ymd(self, send_project, send_ymd):
        pass 
        rtnarr = []
        rtn = {}
        max_count = 500
        count = 0
        for entry in self.database["data"]:
            project = entry["project"]
            if project != send_project:
                continue 

            datatype = entry["datatype"]
            date = entry["datetime"]
            ymd = date.split(" ")[0]

            if ymd != send_ymd:
                continue

            robot = entry["robot_name"]
            run = entry["run_name"]

            dirroot = self.root
            
            basename = entry["basename"]
            relpath = entry["relpath"]
            size = entry["size"]
            site = entry["site"]
            topics = entry.get("topics", [])
            upload_id = entry["upload_id"]
            localpath = entry["localpath"]
            fullpath = entry["fullpath"]

            rtn[run] = rtn.get(run, {})
            rtn[run][relpath] = rtn[run].get(relpath, [])
            rtn[run][relpath].append(
                {
                    "datetime": date,
                    "relpath": relpath,
                    "basename": basename,
                    "size": size,
                    "site": site,
                    "run_name": run,
                    "robot_name": robot,
                    "datatype": datatype,
                    "on_local": True,
                    "on_remote": False,
                    "hsize": humanfriendly.format_size(size),
                    "topics": topics,
                    "upload_id": upload_id,
                    "localpath": localpath,
                    "fullpath": fullpath
                }
            )
            count += 1
            if count >= max_count:
                rtnarr.append(rtn)
                rtn = {}
                count = 0

        rtnarr.append(rtn)
        return rtnarr


    def get_localpath(self, upload_id):
        for entry in self.database["data"]:
            if entry["upload_id"] == upload_id:
                return entry["localpath"]
        return None

    def get_entry(self, upload_id):
        for entry in self.database["data"]:
            # debug_print(f"{upload_id} vs {entry['upload_id']}")
            if entry["upload_id"] == upload_id:
                return entry.copy()
        return None

    """
    returns project -> ymd -> run## -> relpath -> list of entries
    """

    def get_send_data(self):
        rtn = {}
        for entry in self.database["data"]:
            project = entry["project"]
            if project not in self.volume_map:
                raise VolumeMapNotFound(project)

            run = entry["run_name"]
            datatype = entry["datatype"]
            date = entry["datetime"]
            ymd = date.split(" ")[0]
            basename = entry["basename"]
            relpath = entry["relpath"]
            size = entry["size"]
            site = entry["site"]
            topics = entry.get("topics", [])
            upload_id = entry["upload_id"]
            robot_name = entry["robot_name"]
            fullpath = entry.get("fullpath", "")

            rtn[project] = rtn.get(project, {})
            rtn[project][ymd] = rtn[project].get(ymd, {})
            rtn[project][ymd][run] = rtn[project][ymd].get(run, {})
            rtn[project][ymd][run][relpath] = rtn[project][ymd][run].get(relpath, [])
            rtn[project][ymd][run][relpath].append(
                {
                    "datetime": date,
                    "relpath": relpath,
                    "fullpath": fullpath,
                    "basename": basename,
                    "size": size,
                    "site": site,
                    "run_name": run,
                    "datatype": datatype,
                    "on_local": True,
                    "on_remote": False,
                    "hsize": humanfriendly.format_size(size),
                    "topics": topics,
                    "upload_id": upload_id,
                    "dirroot": self.volume_map[project],
                    "robot_name": robot_name,
                    "start_datetime" :entry["start_datetime"],
                    "end_datetime" : entry["end_datetime"]

                }
            )

        return rtn

    def get_run_stats(self, send_project=None, send_ymd=None):
        stats = {}

        for entry in self.database["data"]:
            project = entry["project"]
            if send_project and project != send_project:
                continue

            robot = entry["robot_name"]
            run = entry["run_name"]

            datatype = entry["datatype"]
            date = entry["datetime"]
            ymd = date.split(" ")[0]

            if send_ymd and ymd != send_ymd:
                continue

            if not "start_datetime" in entry:
                debug_print(json.dumps(entry, indent=True))

            start_time = entry.get("start_datetime", entry.get("start_time"))
            end_time = entry.get("end_datetime", entry.get("end_time"))
            # basename = entry["basename"]
            # relpath = entry["relpath"]
            size = entry["size"]
            # site = entry["site"]

            stats[project] = stats.get(project, {})
            stats[project][ymd] = stats[project].get(ymd, {})
            stats[project][ymd][run] = stats[project][ymd].get(
                run,
                {
                    "total_size": 0,
                    "count": 0,
                    "start_datetime": None,
                    "end_datetime": None,
                    "datatype": {},
                },
            )

            stat = stats[project][ymd][run]
            stat["total_size"] += size
            stat["htotal_size"] = humanfriendly.format_size(stat["total_size"])
            stat["count"] += 1

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
            stat["hduration"] = humanfriendly.format_timespan(duration.seconds)

            stat["datatype"][datatype] = stat["datatype"].get(
                datatype, {"total_size": 0, "count": 0}
            )
            stat["datatype"][datatype]["total_size"] += size
            stat["datatype"][datatype]["htotal_size"] = humanfriendly.format_size(
                stat["datatype"][datatype]["total_size"]
            )

            stat["datatype"][datatype]["count"] += 1

            stats[project][ymd][run] = stat

        return stats

    # removes all data on the database.  Data can still be reimported.
    def debug_clear_data(self):
        self.database["data"] = []
        self.commit()

    def estimate_runs(self):
        entry_set = [
            i
            for i, entry in enumerate(self.database["data"])
            if (entry["datatype"].lower() == "mcap")
            or (entry["datatype"].lower() == "bag")
        ]

        # debug_print(sorted(self.database["data"][0]))
        runs_by_relpath = {}

        interval_sets = {}
        for i in entry_set:
            entry = self.database["data"][i]
            project = entry["project"]

            interval_sets[project] = interval_sets.get(project, [])
            interval_sets[project].append(entry)

        for project in interval_sets:
            groups = group_overlapping_intervals(interval_sets[project])
            for run_id, group in enumerate(groups):
                start_time = group[0]["start_datetime"]
                end_time = group[-1]["end_datetime"]

                for entry in self.database["data"]:
                    if entry["project"] != project:
                        continue
                    if (
                        start_time <= entry["start_datetime"] <= end_time
                        or start_time <= entry["end_datetime"] <= end_time
                    ):
                        run_name = f"run_{run_id:04d}"
                        entry["run_name"] = run_name
                        relpath = entry["relpath"]

                        # keep track of which relpaths has which runs.
                        runs_by_relpath[relpath] = runs_by_relpath.get(relpath, [])
                        if not run_name in runs_by_relpath[relpath]:
                            runs_by_relpath[relpath].append(run_name)

        # debug_print(json.dumps(runs_by_relpath, indent=True))
        # if there is a file with a missing run name, check the directory
        # to see if it has only one run. If so, set it to that.
        for entry in self.database["data"]:
            relpath = entry["relpath"]
            if relpath in runs_by_relpath and len(runs_by_relpath[relpath]) == 1:
                entry["run_name"] = runs_by_relpath[relpath][0]

        # update all other runs to be default run name
        for entry in self.database["data"]:
            if not entry["run_name"]:
                entry["run_name"] = "run__no_name"


    def passes_filter(self, entry:dict, filters:dict):
        for name, filter in filters.items():
            entry_value = entry.get(name, "None")
            if filter.get("type", "") == "discrete":
                if not entry_value:
                    entry_value = "None"
                                
                keys = filter.get("keys", "")

                if isinstance(entry, dict):
                    found = False 
                    for key in keys:
                        if key in entry_value:
                            found = True
                    if not found:
                        return False 
                    
                elif not entry_value in keys:
                    return False
            if filter.get("type", "") == "range":
                if name == "datetime":
                    start_time = entry.get("start_datetime", None)
                    end_time = entry.get("end_datetime", None)
                    if not start_time or not end_time:
                        return False
                    filter_min = filter.get("min", "")
                    filter_max = filter.get("max", "")

                    if end_time < filter_min or start_time > filter_max:
                        return False
                else:
                    filter_min = int(filter.get("min", "0"))
                    filter_max = int(filter.get("max", "0"))
                    if entry_value < filter_min or entry_value > filter_max:
                        return False
                    
        return True 

    def search(self, filter:dict, sort_key:str, reverse:bool):
        # debug_print(filter)
        keys = ["project", "site", "robot_name", "datetime", "basename", "topics", "size", "upload_id", "datatype"]
        rtn = []
        for entry in self.database["data"]:
            # apply filter.
            if not self.passes_filter(entry, filter):
                continue

            item = {}
            for key in keys:
                item[key] = entry.get(key, None)
            item["hsize"] = humanfriendly.format_size(item["size"])
            rtn.append(item)

        rtn.sort(key=lambda item: item[sort_key], reverse=reverse)
        return rtn 
    
    def get_search_filters(self):
        discrete_keys = ["project", "site", "robot_name", "topics", "datatype"]
        range_keys = ["datetime", "size", "duration"]

        filters = {}

        for entry in self.database["data"]:

            # duration is special cased here. 
            duration = datetime.strptime(
                entry["end_datetime"], "%Y-%m-%d %H:%M:%S"
            ) - datetime.strptime(entry["start_datetime"], "%Y-%m-%d %H:%M:%S")

            entry["duration"] = duration.seconds

            for key in discrete_keys:
                filters[key] = filters.get(key, {"type": "discrete", "keys":set()})

                if isinstance(entry[key], list):
                    for item in entry[key]:
                        if entry[key]:
                            filters[key]["keys"].add(item)
                        else:
                            filters[key]["keys"].add("None")

                elif isinstance(entry[key], dict):
                    for item in sorted(entry[key]):
                        if item:
                            filters[key]["keys"].add(item)
                        else:
                            filters[key]["keys"].add("None")
                else:
                    if entry[key]:
                        filters[key]["keys"].add(entry[key])
                    else:
                        filters[key]["keys"].add("None")                        
                
            for key in range_keys:
                filters[key] = filters.get(key, {"type": "range", "min": entry[key], "max": entry[key]})
                filters[key]["min"] = min(filters[key]["min"], entry[key])
                filters[key]["max"] = max(filters[key]["max"], entry[key])

            

        for key in discrete_keys:
            if key in filters:
                filters[key]["keys"] = sorted(list(filters[key]["keys"]))
        return filters 

def group_overlapping_intervals(intervals):
    if not intervals:
        return []

    # Sort intervals by start_datetime
    intervals.sort(key=lambda x: x["start_datetime"])

    grouped_intervals = []
    current_group = [intervals[0]]

    for i in range(1, len(intervals)):
        current_interval = intervals[i]
        last_interval_in_group = current_group[-1]

        # Check if the current interval overlaps with the last interval in the current group
        if current_interval["start_datetime"] <= last_interval_in_group["end_datetime"]:
            current_group.append(current_interval)
        else:
            grouped_intervals.append(current_group)
            current_group = [current_interval]

    # Append the last group
    if current_group:
        grouped_intervals.append(current_group)

    return grouped_intervals
