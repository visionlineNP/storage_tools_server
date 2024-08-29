# stub for database.


import json
import os
import pathlib
import threading
import humanfriendly
from datetime import datetime, timedelta
import hashlib
from .debug_print import debug_print


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

    def regenerate(self):
        # init db without file to create new db.
        self._init_db()

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

                debug_print(root)
                for basename in files:
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

        self.estimate_runs()
        self.commit()

    def commit(self):
        with self.mutex:
            with self.filename.open("w") as f:
                json.dump(self.database, f, indent=True, sort_keys=True),

    def _add_name(self, table: str, name: str, description: str):
        with self.mutex:
            name_to_index = {
                name: i for i, (name, _) in enumerate(self.database[table])
            }
            if name in name_to_index:
                return name_to_index[name]
            self.database[table].append((name, description))
            return len(self.database[table]) - 1

    def add_project(self, name: str, description: str):
        self._add_name("projects", name, description)

    def add_robot_name(self, name: str, description: str):
        self._add_name("robots", name, description)

    def add_site(self, name: str, description: str):
        self._add_name("sites", name, description)

    def _get_names(self, table: str):
        rtn = []
        with self.mutex:
            for i, (name, desc) in enumerate(self.database[table]):
                rtn.append((i, name, desc))
        return rtn

    def get_projects(self):
        return self._get_names("projects")

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
            return name_to_index[fullpath]
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
        rtn = {}
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
                    "datatype": datatype,
                    "on_local": True,
                    "on_remote": False,
                    "hsize": humanfriendly.format_size(size),
                    "topics": topics,
                    "upload_id": upload_id,
                }
            )

        return rtn


    """
    returns project -> ymd -> run## -> relpath -> list of entries
    """

    def get_send_data(self):
        rtn = {}
        for entry in self.database["data"]:
            project = entry["project"]
            robot = entry["robot_name"]
            run = entry["run_name"]

            dirroot = self.root
            datatype = entry["datatype"]
            date = entry["datetime"]
            ymd = date.split(" ")[0]
            basename = entry["basename"]
            relpath = entry["relpath"]
            size = entry["size"]
            site = entry["site"]
            topics = entry.get("topics", [])
            upload_id = entry["upload_id"]

            rtn[project] = rtn.get(project, {})
            rtn[project][ymd] = rtn[project].get(ymd, {})
            rtn[project][ymd][run] = rtn[project][ymd].get(run, {})
            rtn[project][ymd][run][relpath] = rtn[project][ymd][run].get(relpath, [])
            rtn[project][ymd][run][relpath].append(
                {
                    "datetime": date,
                    "relpath": relpath,
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

            start_time = entry["start_datetime"]
            end_time = entry["end_datetime"]
            basename = entry["basename"]
            relpath = entry["relpath"]
            size = entry["size"]
            site = entry["site"]

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
            if entry["datatype"].lower() == ".mcap"
            or entry["datatype"].lower() == ".bag"
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
