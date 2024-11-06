from datetime import datetime, timedelta
import json
import os
import pathlib
from typing import List, Tuple
import humanfriendly
import psycopg2
from psycopg2.extras import RealDictCursor

from server.debug_print import debug_print
from server.throttledEmit import RedisThrottledEmit


def build_paginated_query(
    filters: dict, order_by: str, offset: int, page_size: int, reverse: bool) -> str:
    """
    Builds a paginated SQL query based on the provided filters, ordering, and pagination settings.

    Args:
        filters (dict): A dictionary specifying filter conditions for the query.
        order_by (str): Column name to sort the results by.
        offset (int): Number of rows to skip before starting to collect the result set.
        page_size (int): Maximum number of entries to retrieve.
        reverse (bool): Whether to sort the results in descending order.

    Returns:
        str: A SQL query string with the specified filters, ordering, and pagination settings.
    """
    query = "SELECT * FROM data WHERE "
    conditions = []

    # Add conditions based on filters
    for name, filter in filters.items():
        if filter["type"] == "discrete":
            # For discrete filters, match any of the specified keys
            keys = "', '".join(filter["keys"])
            conditions.append(f"{name} IN ('{keys}')")
        elif filter["type"] == "range":
            # For range filters, match values between min and max
            min_val = filter["min"]
            max_val = filter["max"]
            if name == "datetime":
                conditions.append(f"{name} BETWEEN '{min_val}' AND '{max_val}'")
            else:
                conditions.append(f"{name} BETWEEN {min_val} AND {max_val}")

    # Add conditions for JSON if needed
    if "topics" in filters:
        for key, val in filters["topics"]["keys"].items():
            # For JSON fields, use the @> operator to check if key-value pairs match
            conditions.append(f'topics @> \'{{"{key}": "{val}"}}\'')

    # Combine all conditions using AND
    query += " AND ".join(conditions)
    order_direction = "DESC" if reverse else "ASC"
    # Add ordering, limit, and offset to the query
    query += (
        f" ORDER BY {order_by} {order_direction} LIMIT {page_size} OFFSET {offset};"
    )
    return query


def build_count_query(filters: dict) -> str:
    """
    Builds a SQL query to count the number of entries that match the provided filters.

    Args:
        filters (dict): A dictionary specifying filter conditions for the query.

    Returns:
        str: A SQL query string to count the number of matching entries.
    """
    query = "SELECT COUNT(*) FROM data WHERE "
    conditions = []

    # Add conditions based on filters
    for name, filter in filters.items():
        if filter["type"] == "discrete":
            # For discrete filters, match any of the specified keys
            keys = "', '".join(filter["keys"])
            conditions.append(f"{name} IN ('{keys}')")
        elif filter["type"] == "range":
            # For range filters, match values between min and max
            min_val = filter["min"]
            max_val = filter["max"]
            if name == "datetime":
                conditions.append(f"{name} BETWEEN '{min_val}' AND '{max_val}'")
            else:
                conditions.append(f"{name} BETWEEN {min_val} AND {max_val}")

    # Add conditions for JSON if needed
    if "topics" in filters:
        for key, val in filters["topics"]["keys"].items():
            # For JSON fields, use the @> operator to check if key-value pairs match
            conditions.append(f'topics @> \'{{"{key}": "{val}"}}\'')

    # Combine all conditions with AND
    query += " AND ".join(conditions) + ";"
    return query


class Database:
    """An interface to the SQL database.  

    Environment:
        REDIS_HOST: default "localhost"

    """
    def __init__(self, volume_map: dict, blackout: list) -> None:
        """Create an instance of the database interface

        Args:
            volume_map (dict): Mapping of project name to complete volume path
            blackout (list): List of directories to avoid scanning. Can be a part of a directory, and will still match
        """
        self.m_username = "sts"
        self.m_password = "mypassword"
        self.m_db_name = "stsdb"
        self.m_volume_map = volume_map
        self.m_blackout = blackout
        self.m_cache = {}

        self.m_time_format = {
            "date": "%Y-%m-%d",
            "datetime": "%Y-%m-%d %H:%M:%S",
            "start_datetime": "%Y-%m-%d %H:%M:%S",
            "end_datetime": "%Y-%m-%d %H:%M:%S",
        }

        self.init_db()
        self._set_runs()

    def connect(self):
        db_host = os.environ.get("DB_HOST", "localhost")
        db_port = os.environ.get("DB_PORT", 5432)
        conn = psycopg2.connect(
            dbname=self.m_db_name,
            user=self.m_username,
            password=self.m_password,
            host=db_host,
            port=db_port
        )
        return conn

    def init_db(self):
        conn = self.connect()
        cur = conn.cursor()

        with self.connect() as conn:
            with conn.cursor() as cur:
                # Create the table if it doesn't exist
                create_data_table_query = """
                CREATE TABLE IF NOT EXISTS data (
                    upload_id VARCHAR(255) PRIMARY KEY,
                    project VARCHAR(255),
                    robot_name VARCHAR(255),
                    run_name VARCHAR(255),
                    datatype VARCHAR(10),
                    relpath TEXT,
                    basename TEXT,
                    fullpath TEXT,
                    size BIGINT,
                    site VARCHAR(255),
                    date DATE,
                    datetime TIMESTAMP,
                    start_datetime TIMESTAMP,
                    end_datetime TIMESTAMP,
                    dirroot TEXT,
                    remote_dirroot TEXT,
                    status VARCHAR(255),
                    temp_size BIGINT,
                    md5 CHAR(32),
                    topics JSONB,
                    localpath TEXT,
                    duration INTEGER
                );
                """
                cur.execute(create_data_table_query)

                table_names = ["sites", "projects", "robot_names", "remote_servers"]
                for table_name in table_names:
                    create_table_query = f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                    name VARCHAR(255) PRIMARY KEY,
                    description VARCHAR(255)
                    );
                    """
                    cur.execute(create_table_query)

            conn.commit()

    def load_from_json(self, root):
        filename = pathlib.Path(root) / "database.json"
        if filename.exists():
            with filename.open("r") as fid:
                database = json.load(fid)
            for entry in database["data"]:
                self.add_entry(entry)

        for name in self.m_volume_map:
            self.add_project(name, "")
        self._set_runs()

    def _drop_data_table(self):
        with self.connect() as conn:
            with conn.cursor() as cur:
                query = "DROP TABLE IF EXISTS data"
                cur.execute(query)
                conn.commit()

    def regenerate(self, event:str=None, room:str=None):
        """Regenerate the database, send messages to a Redis redirection. 

        Args:
            event (str, optional): Websocket Event for ui. Defaults to None.
            room (str, optional): room to send events, None for all. Defaults to None.
        """
        # init db without file to create new db.
        self._drop_data_table()
        self.init_db()

        emit = None
        if event:
            emit = RedisThrottledEmit(event, room=room)

        for project in sorted(self.m_volume_map):
            volume_root = self.m_volume_map[project]

            debug_print((project, volume_root))
            for root, _, files in os.walk(volume_root):
                skip = None
                for b in self.m_blackout:
                    if b in root:
                        skip = b
                if skip:
                    # debug_print(f"Skipping because {root} matches {skip}")
                    if emit:
                        emit.emit(f"Skipping because {root} matches {skip}")

                    continue

                debug_print(root)

                if emit:
                    emit.emit(f"Scanning {root}")
                
                for basename in files:
                    if basename == "database.json":
                        continue
                    if basename.endswith(".metadata"):
                        base = ".".join(basename.split(".")[:-1])
                        filename = os.path.join(root, base)
                        if not os.path.exists(filename):
                            continue

                        entry = json.load(open(os.path.join(root, basename), "r"))
                        entry["localpath"] = filename
                        entry["dirroot"] = volume_root
                        entry["date"] = entry.get(
                            "date", entry["datetime"].split(" ")[0]
                        )
                        entry["md5"] = entry.get("md5", "0")
                        self.add_entry(entry)
        if emit:
            emit.close()

        self._set_runs()

    def update_volume_map(self, volume_map:dict):
        self.m_volume_map = volume_map

    def update_blackout_list(self, blackout:list):
        self.m_blackout = blackout

    def check_upload_id(self, upload_id: str) -> bool:
        """Check if this upload_id exists in the database

        Args:
            upload_id (str): an upload id

        Returns:
            bool: True if it does, false if not
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                query = "SELECT EXISTS(SELECT 1 FROM data WHERE upload_id = %s)"
                cur.execute(query, (upload_id,))

                # Fetch the result (True if exists, False if not)
                exists = cur.fetchone()[0]
        return exists

    def find_existing_ids(self, upload_ids: List[str]) -> List[str]:
        with self.connect() as conn:
            with conn.cursor() as cur:
                # Use the SQL IN clause with a tuple of upload_ids
                query = "SELECT upload_id FROM data WHERE upload_id = ANY(%s)"
                cur.execute(query, (upload_ids,))

                # Fetch all found upload_ids
                existing_ids = cur.fetchall()

        existing_ids_list = [row[0] for row in existing_ids]
        return existing_ids_list

    def find_upload_ids(self, names: List[Tuple[str, str]]) -> List[str]:
        """Find the 

        Args:
            names (List[Tuple[str, str]]): _description_

        Returns:
            List[str]: _description_
        """
        ids = []
        with self.connect() as conn:
            with conn.cursor() as cur:
                for project, filename in names:
                    filename = filename.strip("/")
                    query = "SELECT upload_id FROM data WHERE project = %s AND fullpath = %s"
                    cur.execute(query, (project, filename))
                    results = cur.fetchall()
                    if len(results) > 0:
                        ids.extend(results[0])
        return ids

    def add_entry(self, entry:dict):
        if entry.get("upload_id") is None or entry["upload_id"] == "None":
            return

        debug_print(f"Add {entry['upload_id']}")
        # skip if entry already exists.
        if self.check_upload_id(entry["upload_id"]):
            return

        self.add_robot_name(entry["robot_name"], "")
        self.add_project(entry["project"], "")

        if entry["site"] and len(entry["site"]) > 0:
            self.add_site(entry["site"], "")

        entry["datatype"] = entry.get("datatype").replace(".", "")
        if entry["run_name"] is None or len(entry["run_name"]) < 1:
            entry["run_name"] = "run_no_name"

        if "date" not in entry:
            entry["date"] = entry["datetime"].split(" ")[0]

        if "md5" not in entry:
            entry["md5"] = "0"

        duration = datetime.strptime(
            entry["end_datetime"], "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(entry["start_datetime"], "%Y-%m-%d %H:%M:%S")
        entry["duration"] = duration.seconds

        with self.connect() as conn:
            with conn.cursor() as cur:
                query = """
                    INSERT INTO data (
                        project, robot_name, run_name, datatype, relpath, basename, fullpath,
                        size, site, date, datetime, start_datetime, end_datetime, upload_id,
                        dirroot, md5, topics, localpath, duration
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                cur.execute(
                    query,
                    (
                        entry["project"],
                        entry["robot_name"],
                        entry["run_name"],
                        entry["datatype"],
                        entry["relpath"],
                        entry["basename"],
                        entry.get("fullpath", ""),
                        entry["size"],
                        entry["site"],
                        entry["date"],
                        entry["datetime"],
                        entry["start_datetime"],
                        entry["end_datetime"],
                        entry["upload_id"],
                        entry["dirroot"],
                        entry["md5"],
                        json.dumps(entry["topics"]),
                        entry["localpath"],
                        entry["duration"],
                    ),
                )

                conn.commit()

    def get_entry(self, upload_id:str) -> dict:
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM data WHERE upload_id = %s"
                cur.execute(query, (upload_id,))
                result = cur.fetchone()
        return result

    def get_all_entries(self) -> List[dict]:
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM data"
                cur.execute(query)
                result = cur.fetchall()  # Fetch all entries as a list of dictionaries
        return result

    def _add_name(self, table:str, name:str, description:str):
        if self._has_name(table, name):
            return

        self.m_cache[table] = self.m_cache.get(table, {})
        self.m_cache[table][name] = description

        try:
            with self.connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = (
                        "INSERT INTO "
                        + f"{table}"
                        + "(name, description) VALUES (%s, %s)"
                    )
                    cur.execute(query, (name, description))
                    conn.commit()
        except psycopg2.errors.UniqueViolation:
            pass

    def _get_names(self, table:str) -> List[str]:
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"SELECT name FROM {table} ORDER BY name"
                cur.execute(query)
                result = cur.fetchall()  # Fetch all entries as a list of dictionaries
        rtn = [(item["name"]) for item in result if item["name"] is not None]
        return rtn

    def _remove_name(self, table:str, name:str):
        debug_print(f"delete from {table} {name}")
        if table in self.m_cache and name in self.m_cache[table]:
            del self.m_cache[table][name]

        with self.connect() as conn:
            with conn.cursor() as cur:
                query = f"DELETE from {table} WHERE name = %s"
                cur.execute(query, (name,))
            conn.commit()

    def _has_name(self, table:str, name:str) -> bool:
        if table in self.m_cache and name in self.m_cache[table]:
            return True

        exists = False
        try:
            conn = self.connect()
            with conn.cursor() as cur:
                query = f"SELECT EXISTS(SELECT 1 FROM {table} WHERE name = %s)"
                cur.execute(query, (name,))

                # Fetch the result (True if exists, False if not)
                fetch = cur.fetchall()
                if fetch and len(fetch) > 0:
                    exists = fetch[0][0]
            conn.close()
            if exists:
                self.m_cache[table] = self.m_cache.get(table, {})
                self.m_cache[table][name] = ""
        except psycopg2.OperationalError as e:
            debug_print(f"error with {table} {name}: {e}")
            exists = False
        return exists

    def _replace_name(self, table:str, name:str, description:str):
        if self._has_name(table, name):
            self._remove_name(table, name)
        self._add_name(table, name, description)

    def _get_names_and_desc(self, table:str) -> List[Tuple[str,str]]:
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"SELECT * FROM {table} ORDER BY name"
                cur.execute(query)
                result = cur.fetchall()  # Fetch all entries as a list of dictionaries
        cur.close()
        conn.close()

        rtn = [(item["name"], item["description"]) for item in result]
        return rtn

    # projects
    def add_project(self, name:str, description:str):
        self._add_name("projects", name, description)

    def remove_project(self, name:str):
        self._remove_name("projects", name)

    def update_project(self, name:str, description:str):
        self._replace_name("projects", name, description)

    def get_projects(self) -> List[str]:
        return self._get_names("projects")

    def get_projects_and_desc(self):
        return self._get_names_and_desc("projects")

    # sites
    def add_site(self, name, description):
        self._add_name("sites", name, description)

    def get_sites(self):
        return self._get_names("sites")

    def update_site(self, name, description):
        self._replace_name("sites", name, description)

    def remove_site(self, name):
        self._remove_name("sites", name)

    # robots
    def add_robot_name(self, name, description):
        self._add_name("robot_names", name, description)

    def get_robots(self):
        return self._get_names("robot_names")

    def update_robot_name(self, name, description):
        self._replace_name("robot_names", name, description)

    def has_robot_name(self, name):
        return self._has_name("robot_names", name)

    def remove_robot_name(self, name):
        self._remove_name("robot_names", name)

    # remote servers
    def add_remote_server(self, name, description):
        self._add_name("remote_servers", name, description)

    def get_remote_servers(self):
        return self._get_names("remote_servers")

    def remove_remote_server(self, name):
        self._remove_name("remote_servers", name)

    # runs
    def _set_runs(self):
        query = """
        SELECT site, date, robot_name, start_datetime, end_datetime 
        FROM data 
        WHERE (datatype = 'mcap' or datatype = 'bag') 
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query)

                # Execute the query to fetch entries
                cur.execute(query)
                results = cur.fetchall()

        times = {}
        for item in results:
            site = item["site"]
            date = item["date"].strftime("%Y-%m-%d")
            robot_name = item["robot_name"]
            key = (site, date, robot_name)
            start_time = item["start_datetime"]
            end_time = item["end_datetime"]
            times[key] = times.get(key, [])
            times[key].append((start_time, end_time))

        merged = {}
        for key in times:
            sorted_times = sorted(times[key])
            merged[key] = []
            for current in sorted_times:
                if not merged[key] or merged[key][-1][1] < current[0]:
                    merged[key].append(current)
                else:
                    merged[key][-1] = (
                        merged[key][-1][0],
                        max(merged[key][-1][1], current[1]),
                    )

        with self.connect() as conn:
            with conn.cursor() as cur:
                for (site, date, robot_name), runs in merged.items():
                    for i, (start_time, end_time) in enumerate(runs):
                        idx = i + 1
                        run_name = f"run_{idx:03d}"
                        query = "UPDATE data set run_name = %s WHERE start_datetime >= %s AND end_datetime <= %s"
                        cur.execute(query, (run_name, start_time, end_time))
            conn.commit()

    # server data
    def get_send_data_ymd_stub(self):
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"SELECT DISTINCT project, date FROM data"
                cur.execute(query)
                results = cur.fetchall()

        rtn = {}
        for item in results:
            project = item["project"]
            ymd = item.get("date").strftime("%Y-%m-%d")
            rtn[project] = rtn.get(project, {})
            rtn[project][ymd] = rtn[project].get(ymd, {})
        return rtn

    def get_run_stats(self, send_project=None, send_ymd=None):
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if send_project:
                    if send_ymd:
                        query = "SELECT * from data where project = %s and date = %s"
                        cur.execute(query, (send_project, send_ymd))
                    else:
                        query = "SELECT * from data where project = %s"
                        cur.execute(query, (send_project,))
                else:
                    query = "SELECT * from data"
                    cur.execute(query)
                results = cur.fetchall()

        stats = {
            "total": {
                "total_size": 0,
                "count": 0,
                "start_datetime": None,
                "end_datetime": None,
                "datatype": {}
            }
        }
        for entry in results:
            project = entry.get("project")
            ymd = entry.get("date").strftime("%Y-%m-%d")
            run = entry["run_name"]


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

            self._update_stats_for_entry(entry, stats[project][ymd][run])
            self._update_stats_for_entry(entry, stats["total"])

        return stats

    def _update_stats_for_entry(self, entry:dict, stat:dict):
        """
        Updates cumulative statistics for a data entry, including total size, count, 
        date range, and breakdown by datatype.

        Args:
            entry (dict): A dictionary representing a data entry with keys:
                - "size" (int): Size of the entry in bytes.
                - "start_datetime" (datetime, optional): Start timestamp.
                - "end_datetime" (datetime, optional): End timestamp.
                - "datatype" (str): The data type of the entry.
            stat (dict): The cumulative statistics dictionary to update, including:
                - "total_size" (int): Total size of entries.
                - "htotal_size" (str): Human-readable format of total size.
                - "count" (int): Number of entries processed.
                - "start_datetime" (str): Earliest start time.
                - "end_datetime" (str): Latest end time.
                - "duration" (int): Duration in seconds between the earliest start 
                and latest end times.
                - "hduration" (str): Human-readable format of the duration.
                - "datatype" (dict): Breakdown by datatype, with each datatype 
                containing its own total size and count.

        Updates:
            - Updates `stat` to include the new `entry` data, adjusting cumulative
            size, count, start/end times, and duration, formatted for readability.

        Raises:
            AssertionError: If duration calculation results in a non-timedelta value.
        """
        size = entry["size"]
        start_time = entry.get("start_datetime")
        end_time = entry.get("end_datetime")
        datatype = entry["datatype"]

        if start_time:
            start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
        if end_time:
            end_time = end_time.strftime("%Y-%m-%d %H:%M:%S")

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

    def get_send_data_ymd(self, send_project:str=None, send_ymd:str=None):
        """
        Retrieves and structures data entries from the database by project and date, 
        grouping them in batches and including relevant metadata.

        Args:
            send_project (str, optional): Project name to filter data by. If None, data for all projects is fetched.
            send_ymd (str, optional): Specific date (in "YYYY-MM-DD" format) to filter data by. Ignored if None.

        Returns:
            list: A list of dictionaries, where each dictionary contains up to 500 entries with metadata fields,
                grouped by `run_name` and `relpath`. Each entry includes:
                - "basename" (str): Base file name.
                - "datatype" (str): Data type (e.g., file type).
                - "datetime" (str): Timestamp for the entry.
                - "end_datetime" (str): End datetime.
                - "fullpath" (str): Full path to the file.
                - "complete_relpath" (str): Complete relative path combining date, site, robot, and relpath.
                - "hsize" (str): Human-readable file size.
                - "localpath" (str): Local path to the file.
                - "on_local" (bool): Flag indicating if data is available locally.
                - "on_remote" (bool): Flag indicating if data is available remotely.
                - "relpath" (str): Relative path within the project.
                - "robot_name" (str): Robot associated with the entry.
                - "run_name" (str): Run identifier.
                - "site" (str): Site location, defaulting to "default" if None.
                - "size" (int): File size in bytes.
                - "start_datetime" (str): Start datetime.
                - "topics" (list): Topics associated with the data.
                - "upload_id" (str): Unique identifier for the upload.

        Notes:
            - Batches entries in groups of 500 to avoid large payloads.
            - Formats date-related fields for consistency.
            - Groups data by `run_name` and `relpath`.
        """
        rtnarr = []
        rtn = {}
        max_count = 500
        count = 0

        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if send_project:
                    if send_ymd:
                        query = "SELECT * from data where project = %s and date = %s"
                        cur.execute(query, (send_project, send_ymd))
                    else:
                        query = "SELECT * from data where project = %s"
                        cur.execute(query, (send_project,))
                else:
                    query = "SELECT * from data"
                    cur.execute(query)
                results = cur.fetchall()

        for entry in results:
            robot = entry["robot_name"]
            run = entry["run_name"]
            basename = entry["basename"]
            relpath = entry["relpath"]
            size = entry["size"]
            site = entry["site"]
            topics = entry.get("topics", [])
            upload_id = entry["upload_id"]
            localpath = entry["localpath"]
            fullpath = entry.get("fullpath", "")
            datatype = entry["datatype"]
            date = entry["datetime"].strftime("%Y-%m-%d %H:%M:%S")
            ymd = entry["date"].strftime("%Y-%m-%d")

            if site is None:
                site = "default"
            complete_relpath = os.path.join(ymd, site, robot, relpath, basename)

            rtn[run] = rtn.get(run, {})
            rtn[run][relpath] = rtn[run].get(relpath, [])
            rtn[run][relpath].append(
                {
                    "basename": basename,
                    "datatype": datatype,
                    "datetime": date,
                    "end_datetime": entry["end_datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                    "fullpath": fullpath,
                    "complete_relpath": complete_relpath,
                    "hsize": humanfriendly.format_size(size),
                    "localpath": localpath,
                    "on_local": True,
                    "on_remote": False,
                    "relpath": relpath,
                    "robot_name": robot,
                    "run_name": run,
                    "site": site,
                    "size": size,
                    "start_datetime": entry["start_datetime"].strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "topics": topics,
                    "upload_id": upload_id,
                }
            )
            count += 1
            if count >= max_count:
                rtnarr.append(rtn)
                rtn = {}
                count = 0

        rtnarr.append(rtn)
        return rtnarr

    # node data format:
    def get_node_data_blocks(self):
        blocks = []

        block_size = 100
        block = []
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM data"
                cur.execute(query)

                for entry in cur:
                    for key, format in self.m_time_format.items():
                        if key in entry:
                            entry[key] = entry[key].strftime(format)

                    block.append(entry)
                    if len(block) >= block_size:
                        blocks.append(block)
                        block = []
        if len(block) > 0:
            blocks.append(block)
        return blocks

    # search
    def get_search_filters(self):
        """
        Generates a set of filter options for search functionality based on 
        entries in the `data` table, categorizing columns as discrete or range types.

        Returns:
            dict: A dictionary of filter options for each key, structured as:
                - For discrete keys (e.g., "project", "site"):
                    {
                        "type": "discrete",
                        "keys": list of unique values for the key
                    }
                - For range keys (e.g., "datetime", "size"):
                    {
                        "type": "range",
                        "min": minimum value for the key,
                        "max": maximum value for the key
                    }

        Notes:
            - The `discrete_keys` list contains columns categorized as discrete filters.
            - The `range_keys` list contains columns categorized as range filters.
            - `datetime` values are formatted as strings for consistency.
            - Filters are constructed from database values, with lists and dictionaries
            expanded to unique values in `discrete` filters.
        """

        discrete_keys = ["project", "site", "robot_name", "topics", "datatype"]
        range_keys = ["datetime", "size", "duration"]
        filters = {}

        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM data"
                cur.execute(query)

                for entry in cur:
                    duration = entry["end_datetime"] - entry["start_datetime"]
                    entry["duration"] = duration.seconds

                    for key in discrete_keys:
                        filters[key] = filters.get(
                            key, {"type": "discrete", "keys": set()}
                        )

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
                        filters[key] = filters.get(
                            key, {"type": "range", "min": entry[key], "max": entry[key]}
                        )
                        filters[key]["min"] = min(filters[key]["min"], entry[key])
                        filters[key]["max"] = max(filters[key]["max"], entry[key])

        for key in filters:
            if key == "datetime":
                filters[key]["min"] = filters[key]["min"].strftime("%Y-%m-%d %H:%M:%S")
                filters[key]["max"] = filters[key]["max"].strftime("%Y-%m-%d %H:%M:%S")
            elif filters[key]["type"] == "discrete":
                filters[key]["keys"] = list(filters[key]["keys"])

        return filters

    def search(
        self, filters: dict, order_by: str, offset: int, page_size: int, reverse: bool
    ):
        
        """
        Executes a paginated search query based on provided filters, ordering, 
        and pagination settings, and returns the results along with the total count.

        Args:
            filters (dict): A dictionary specifying search filters for the query.
            order_by (str): Column name to sort the results by.
            offset (int): Number of rows to skip before starting to collect the result set.
            page_size (int): Maximum number of entries to retrieve.
            reverse (bool): Whether to sort the results in descending order.

        Returns:
            tuple: 
                - List[dict]: Each dictionary represents an entry with formatted 
                size (`hsize`) and datetime fields.
                - int: Total count of entries that match the filters without pagination.
        Notes:
            - Formats size and datetime fields in each entry before returning.
        """
        search_query = build_paginated_query(
            filters, order_by, offset, page_size, reverse
        )
        count_query = build_count_query(filters)

        rtn = []
        with self.connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(search_query)
                entries = cur.fetchall()

                cur.execute(count_query)
                count = cur.fetchall()[0]["count"]

        for entry in entries:
            entry["hsize"] = humanfriendly.format_size(entry["size"])

            for key, format in self.m_time_format.items():
                if key in entry:
                    entry[key] = entry[key].strftime(format)

            rtn.append(entry)
        return rtn, count
