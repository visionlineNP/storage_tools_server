from datetime import datetime, timedelta
import shutil
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory,
    session,
    redirect,
    url_for,
    flash,
    make_response,
)
from flask_socketio import SocketIO, disconnect, join_room, leave_room
import os
import yaml
import json
import humanfriendly
import socket
import fcntl
import struct
from zeroconf import Zeroconf, ServiceInfo
import jwt
from engineio.payload import Payload
import psutil
import hashlib
import secrets

from .debug_print import debug_print
from .speed import FileSpeedEstimate
from .database import Database, get_upload_id
from .remoteConnection import RemoteConnection





# prepare the app
app = Flask(__name__)
app.config["SECRET_KEY"] = "AirLabKeyKey"

# optional for extra security, set the Cross site origins (cors_allowed_origins)
#hostname=os.environ["HOSTNAME"]
#origins = [f"http://{hostname}:8091", f"http://{hostname}.andrew.cmu.edu:8091"]

origins = "*"

Payload.max_decode_packets = 100  # Increase the number of packets allowed in a single request
socketio = SocketIO(app, cors_allowed_origins=origins, ping_interval=25, ping_timeout=60, max_http_buffer_size=200000000, logger=False, engineio_logger=False)


# global variables.
# keeps tracks up uploads
g_uploads = {}

# keeps track of which devices are connected.
g_sources = {"devices": [], "nodes": [], "report_host": [], "report_node": []}

# maps source to upload_id to file entry for files on device
g_remote_entries = {}

# buffer of source to entries.  
g_remote_entries_buffer = {}

# maps source to node data for files on remote nodes (other servers)
g_node_entries = {}


# tracks the remote device and node sockets
# so we can know when they disconnect
# maps source name to sid
g_remote_sockets = {}

# which files to operate on the device
# maps source to list of files on the device
g_selected_files = {}

# flag set to do action
# maps source name to bool
g_selected_files_ready = {}

# which action to do.  [send, delete, cancel]
# maps source name to action
g_selected_action = {}

# how much space is left on each device.
g_fs_info = {}

# maps source to project
g_projects = {}

# report node information
# maps source -> { threads: int, }
g_report_node_info = {}

# Store uploaded files in this directory
g_upload_dir = None

# stub for a real database.
g_database = None


# dashboard clients
# when we need to send something to every dashboard.  
g_dashboard_rooms = []

def get_source_by_mac_address():
    macs = []
    addresses = psutil.net_if_addrs()
    for interface in sorted(addresses):
        if interface == "lo":
            continue
        for addr in sorted(addresses[interface]):
            if addr.family == psutil.AF_LINK:  # Check if it's a MAC address
                # if psutil.net_if_stats()[interface].isup:
                macs.append(addr.address.replace(":",""))

    name = hashlib.sha256("_".join(macs).encode()).hexdigest()[:16]
    rtn = f"SRC-{name}"
    return rtn 

# config_filename = args.config
config_filename = os.environ.get("CONFIG", "config/config.yaml")

def load_config(config_filename):
    debug_print(f"Using {config_filename}")
    with open(config_filename, "r") as f:
        g_config = yaml.safe_load(f)
 
        g_config["source"] = get_source_by_mac_address() + "_" + str(g_config["port"])
        debug_print(f"Setting source name to {g_config['source']}")

        g_upload_dir = g_config["upload_dir"]
        os.makedirs(g_upload_dir, exist_ok=True)

        v_root = g_config.get("volume_root", "/")
        v_map = g_config.get("volume_map", {}).copy()
        for name in v_map:
            v_map[ name ] = os.path.join(v_root,  v_map.get(name, "").strip("/"))
         
        blackout = g_config.get("blackout", [])

        g_database = Database(g_upload_dir, g_config["source"], v_map, blackout)
        g_database.estimate_runs()

    # g_database.regenerate()
    # # this is optional. We can preload projects, sites, and robots
    # # based on the config.
        for project_name in sorted(g_config.get("volume_map", [])):
    # for project_name in g_config.get("projects", []):
            g_database.add_project(project_name, "")

        for robot_name in g_config.get("robots", []):
            g_database.add_robot_name(robot_name, "")

        for site_name in g_config.get("sites", []):
            g_database.add_site(site_name, "")
    return g_upload_dir,g_database,g_config

g_upload_dir, g_database, g_config = load_config(config_filename)

g_keys_filename = os.environ.get("KEYSFILE", "config/keys.yaml")

def load_keys(g_keys_filename):
    global g_config 
    if os.path.exists(g_keys_filename):
        with open(g_keys_filename, "r") as f:
            keys = yaml.safe_load(f)
            g_config["keys"] = keys["keys"]
            g_config["API_KEY_TOKEN"] = keys.get("API_KEY_TOKEN", None)

load_keys(g_keys_filename)

# wrapper for remote connection to another server
g_remote_connection = RemoteConnection(g_config, socketio, g_database)


# set up zero conf for device
zeroconf = Zeroconf()


# grab all the ip address that this server has.
def get_ip_addresses():
    interfaces = os.listdir("/sys/class/net/")
    ip_addresses = []
    for iface in interfaces:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ip_address = fcntl.ioctl(
                sock.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack("256s", iface[:15].encode("utf-8")),
            )[20:24]
            ip_address = socket.inet_ntoa(ip_address)
            ip_addresses.append(ip_address)
        except IOError:
            continue
    return ip_addresses


def setup_zeroconf():
    ip_addresses = get_ip_addresses()
    # ip_addresses = ["127.0.0.1"]
    addresses = [socket.inet_aton(ip) for ip in ip_addresses]

    debug_print(f"using address: {ip_addresses}")
    desc = {}
    info = ServiceInfo(
        "_http._tcp.local.",
        "Airlab_storage._http._tcp.local.",
        addresses=addresses,
        port=g_config["port"],
        properties=desc,
    )

    zeroconf.register_service(info)

## 
# user auth token 
## 
def generate_token(user):
    payload = {
        'user': user,
        'iss': 'storage_tool_server',
    }
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm='HS256')


def dashboard_room():

    username = request.headers.get('X-Authenticated-User')
    if not username:
        username = request.cookies.get("username")
    if not username:
        username = request.args.get("username")

    if not username:
        username = "DEVICE"

    return "dashboard-" + username


###############################################################################
# socket io connectons
###############################################################################


# handle updates to the dashboard
# each device will be a socketio room
# and a dashboard can join or leave a room to get updates
# from a dashboard.
@socketio.on("join")
def on_join(data):
    global g_remote_sockets
    room = data["room"]
    client = data.get("type", None)
    join_room(room)
    socketio.emit("dashboard_info", {"data": f"Joined room: {room}", "source": g_config["source"]}, to=room)
    debug_print(f"Joined room {room} from {client}")
    if client != "dashboard":
        g_remote_sockets[room] = request.sid
    else:
        if room not in g_dashboard_rooms:
            g_dashboard_rooms.append(room)

        send_all_data()

    

@socketio.on("leave")
def on_leave(data):
    source = data["room"]
    leave_room(source)
    debug_print(f"left room {source}")


@socketio.on("ping")
def on_ping(data):
    debug_print(f"Got ping {data}")


@socketio.on("connect")
def on_connect():
    # debug_print("Connection")

    username = request.args.get("username")
    if username is None:
        username = request.headers.get('X-Authenticated-User') 
    debug_print(f"username is {username}")

    api_key_token = request.headers.get("X-Api-Key")
    if api_key_token:
        debug_print(f"Api key: {api_key_token}")
        return 

    auth_header = request.headers.get("Authorization")

    if auth_header:
        debug_print(auth_header)
        auth_type, token = auth_header.split()
        if auth_type.lower() == "bearer":
            api_key_token = token
            # debug_print(api_key_token)
            # Validate the API key token here
            if validate_api_key_token(api_key_token):
                debug_print("Valid token")
                session["api_key_token"] = api_key_token
                return "Valid Connection", 200
            else:
                debug_print("Invalid token")
                return "Invalid API key token", 401
        elif auth_type.lower() == "basic":
            user = request.headers.get('X-Authenticated-User')  # Header set by Nginx after LDAP auth
            ## need to pass this to send_all_data.
        else:
            disconnect()

    # debug_print("Client connected")
    # if username:
    #     send_all_data()
    # return "Good", 200
    
def send_all_data():
    send_device_data()
    send_node_data()
    send_server_data()
    send_report_host_data()
    send_report_node_data()
    on_request_projects()
    on_request_robots()
    on_request_sites()
    on_request_keys()
    debug_print("Sent all data")


@socketio.on("disconnect")
def on_disconnect():

    global g_remote_entries
    global g_remote_sockets
    global g_sources
    global g_report_node_info

    remove = None
    for source, sid in g_remote_sockets.items():
        if sid == request.sid:
            remove = source
            break

    if remove:
        # debug_print(f"g_remote_entries: { remove in g_remote_entries} ")
        # debug_print(f"g_remote_sockets: {remove in g_remote_sockets}")
        # for source_type in sorted(g_sources):
        #     debug_print(f"g_sources[\"{source_type}\"]:  {remove in g_sources[source_type]}")

        if remove in g_remote_entries:
            del g_remote_entries[remove]
        if remove in g_remote_sockets:
            del g_remote_sockets[remove]
        if remove in g_node_entries:
            del g_node_entries[remove]
        if remove in g_sources["devices"]:
            g_sources["devices"].pop(g_sources["devices"].index(remove))
            debug_print(g_sources["devices"])            
            send_device_data()
        if remove in g_sources["nodes"]:
            g_sources["nodes"].pop(g_sources["nodes"].index(remove))
            send_node_data()
        if remove in g_sources["report_host"]:
            g_sources["report_host"].pop(g_sources["report_host"].index(remove))
            send_report_host_data()

        if remove in g_sources["report_node"]:
            g_sources["report_node"].pop(g_sources["report_node"].index(remove))
            del g_report_node_info[remove]

            send_report_node_data()

        debug_print(f"Got disconnect: {remove}")
    else:
        room = dashboard_room()
        if room in g_dashboard_rooms:
            g_dashboard_rooms.pop(g_dashboard_rooms.index(room))
        debug_print("client disconnect: " + room )

@socketio.on("keep_alive")
def on_keep_alive():

    source = None
    for _source, sid in g_remote_sockets.items():
        if sid == request.sid:
            source = _source
            break

    # debug_print(source)
    # just keeping aliving.
    socketio.emit("keep_alive_ack")
    # debug_print("alive")
    pass 
        
@socketio.on("control_msg")
def on_control_msg(data):
    source = data.get("source")
    action = data.get("action")
    socketio.emit("control_msg", {"action": action}, to=source)
    if g_remote_connection.connected():
        g_remote_connection._handle_control_msg(data)


@socketio.on("device_remove")
def on_device_remove(data):

    source = data.get("source")
    ids = data.get("files")

    filenames = []
    for upload_id in ids:
        if not upload_id in g_remote_entries[source]:
            debug_print(
                f"Error! did not find upload id [{upload_id}] in {sorted(g_remote_entries[source])}"
            )
            continue

        dirroot = g_remote_entries[source][upload_id]["dirroot"]
        relpath = g_remote_entries[source][upload_id]["fullpath"].strip("/")
        filenames.append((dirroot, relpath, upload_id))

    msg = {"source": source, "files": filenames}
    socketio.emit("device_remove", msg, to=source)


ui_status = {}


@socketio.on("device_status")
def on_device_status(data):
    global ui_status
    # debug_print(data)

    source = data.get("source")

    msg = {"source": source}

    ui_status[source] = None
    if "msg" in data:
        msg["msg"] = data["msg"]

    # socketio.emit("device_status", msg, to=dashboard_room())
    socketio.emit("device_status", msg)


@socketio.on("device_status_tqdm")
def on_device_status_tqdm(data):
    # debug_print(data)
    socketio.emit("device_status_tqdm", data)


@socketio.on("device_scan")
def on_device_scan(data):
    socketio.emit("device_scan", data)

@socketio.on("device_files_items")
def on_device_files_items(data):    
    global g_remote_entries_buffer

    source = data.get("source")
    files = data.get("files")

    g_remote_entries_buffer[source] = g_remote_entries_buffer.get(source, [])
    g_remote_entries_buffer[source].extend(files)


@socketio.on("device_files")
def on_device_files(data):
    global g_remote_entries
    global g_remote_entries_buffer
    global g_fs_info
    global g_projects
    global g_sources

    source = data.get("source")
    project = data.get("project", None)
    if project is None:
        g_remote_entries[source] = {}
        send_device_data()

    # files = data.get("files")
    files = g_remote_entries_buffer.get( source, data.get("files", []))
    if source in g_remote_entries_buffer: del g_remote_entries_buffer[source]

    g_selected_files_ready[source] = False
    g_selected_action[source] = None
    g_projects[source] = project

    if source not in g_sources["devices"]:
        g_sources["devices"].append(source)

    # note, this could be emitted
    g_fs_info[source] = data.get("fs_info")

    g_remote_entries[source] = {}

    for entry in files:
        dirroot = entry.get("dirroot")
        file = entry.get("filename")
        size = entry.get("size")
        start_datetime = entry.get("start_time")
        end_datetime = entry.get("end_time")
        md5 = entry.get("md5")
        robot_name = entry.get("robot_name")
        if robot_name and len(robot_name) > 0:
            has_robot = g_database.has_robot_name(robot_name)
            if not has_robot:
                g_database.add_robot_name(robot_name, "")
                g_database.commit()

                # send users new robot names
                on_request_robots()
                
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
            "datetime": start_datetime,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "upload_id": upload_id,
            "dirroot": dirroot,
            "status": None,
            "temp_size": 0,
            "on_device": True,
            "on_server": False,
            "md5": md5,
            "topics": topics,
        }

        g_remote_entries[source][upload_id] = entry

        filepath = get_file_path(source, upload_id)
        status = "On Device"
        if os.path.exists(filepath):
            status = "On Device and Server"
            g_remote_entries[source][upload_id]["on_server"] = True
        if os.path.exists(filepath + ".tmp"):
            status = "Interrupted transfer"
            g_remote_entries[source][upload_id]["temp_size"] = os.path.getsize(
                filepath + ".tmp"
            )
        g_remote_entries[source][upload_id]["status"] = status

    send_device_data()


# @socketio.on("request_server_ymd_data")
# def on_request_server_ymd_data(data):
#     global g_database
#     tab = data.get("tab")
#     names = tab.split(":")

#     _, project, ymd = names
#     datasets = g_database.get_send_data_ymd(project, ymd)

#     stats = g_database.get_run_stats(project, ymd)
    
#     for i, data in enumerate(datasets):
#         server_data = {
#             "total": len(datasets),
#             "index": i,
#             "runs": data,
#             "stats": stats,
#             "source": g_config["source"],
#             "project": project,
#             "ymd": ymd,
#             "tab": tab
#         }

#         socketio.emit("server_ymd_data", server_data, to=dashboard_room())


@socketio.on("request_server_ymd_data")
def on_request_server_ymd_data(data):
    global g_database
    tab = data.get("tab")
    names = tab.split(":")

    _, project, ymd = names
    datasets = g_database.get_send_data_ymd(project, ymd)
    stats = g_database.get_run_stats(project, ymd)
    
    room = dashboard_room()

    # Start the long-running task in the background
    socketio.start_background_task(target=emit_server_ymd_data, datasets=datasets, stats=stats, project=project, ymd=ymd, tab=tab, room=room)
    # debug_print(f"sending data! {project} {ymd} {len(datasets)}")


def emit_server_ymd_data(datasets, stats, project, ymd, tab, room):
    """Background task to emit data incrementally."""
    max_rows = 2

    total = min(max_rows, len(datasets))

    for i, data in enumerate(datasets[:max_rows]):
        server_data = {
            "total": total,
            "index": i,
            "runs": data,
            "stats": stats,
            "source": g_config["source"],
            "project": project,
            "ymd": ymd,
            "tab": tab
        }

        # Emit the data to the client
        socketio.emit("server_ymd_data", server_data, to=room)

    # debug_print(f"-- complete {project} {ymd} {len(datasets)}")

@socketio.on("request_node_ymd_data")
def on_request_node_ymd_data(data):
    global g_node_entries

    tab = data.get("tab")
    names = tab.split(":")
    _, source, project, ymd = names

    source_data = g_node_entries.get(source, {})
    # project_data = source_data.get("entries", {}).get(project)
    # ymd_data = project_data.get(ymd, {})
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
    socketio.emit("node_ymd_data", msg, to=dashboard_room())


@socketio.on("request_projects")
def on_request_projects():
    names = [i[1] for i in g_database.get_projects()]
    socketio.emit("project_names", {"data": names})


@socketio.on("add_project")
def on_add_project(data):
    global g_database
    g_database.add_project(data.get("project"), data.get("desc", ""))
    g_database.commit()
    on_request_projects()


@socketio.on("set_project")
def on_set_project(data):
    source = data["source"]
    debug_print(data)
    socketio.emit("set_project", data, to=source)


@socketio.on("server_connect")
def on_server_connect(data):
    global g_remote_connection
    address = data.get("address", None)
    username = request.cookies.get("username")
    if address:
        g_remote_connection.connect(address, username)

    # debug_print(("Connection", g_remote_connection.connected()))
    source = g_config["source"]
    socketio.emit(
        "remote_connection",
        {
            "source": source,
            "address": address,
            "connected": g_remote_connection.connected(),
        },
    )


@socketio.on("server_disconnect")
def on_server_disconnect():
    global g_remote_connection
    g_remote_connection.disconnect()
    # debug_print(("Connection", g_remote_connection.connected()))
    # source = config["source"]
    # socketio.emit("remote_connection", {"source": source, "connected": g_remote_connection.connected()})


# this status can come from either node or server
# file upload, so both will be updated.
@socketio.on("server_status_tqdm")
def on_device_status_tqdm(data):
    socketio.emit("server_status_tqdm", data, to=dashboard_room())
    socketio.emit("node_status_tqdm", data, to=dashboard_room())


# send the updated data to the server.  
@socketio.on("server_refresh")
def on_server_refresh():
    global g_remote_connection
    g_remote_connection.send_node_data()

@socketio.on("request_robots")
def on_request_robots():
    names = [i[1] for i in g_database.get_robots()]
    socketio.emit("robot_names", {"data": names})


@socketio.on("add_robot")
def on_add_robot(data):
    global g_database
    g_database.add_robot_name(data.get("robot"), data.get("desc", ""))
    g_database.commit()
    on_request_robots()


@socketio.on("request_sites")
def on_request_sites():
    names = [i[1] for i in g_database.get_sites()]
    socketio.emit("site_names", {"data": names})

@socketio.on("request_keys")
def on_request_keys():
    keys = g_config["keys"]
    api_token = g_config["API_KEY_TOKEN"]
    socketio.emit("key_values", {"data": keys, "source": g_config["source"], "token": api_token}, to=dashboard_room())

def save_keys():
    global g_keys_filename 
    global g_config 

    write_data = {
        "keys": g_config["keys"],
        "API_KEY_TOKEN": g_config["API_KEY_TOKEN"]
        }
    yaml.dump(write_data, open(g_keys_filename, "w"))


@socketio.on("generate_key")
def on_generate_key(data):
    source = data.get("source")
    name = data.get("name")

    # add some spice to the key
    salt = secrets.token_bytes(16)

    values = [source, name, f"{salt}"]

    key = hashlib.sha256("_".join(values).encode()).hexdigest()[:16]
    if key in g_config["keys"]:
        socketio.emit("server_status", {"msg": "failed to create key", "rtn": False})
        return 
    g_config["keys"][key] = name

    save_keys()
    socketio.emit("server_status", {"msg": "Created key", "rtn": True})
    on_request_keys()

@socketio.on("insert_key")
def on_insert_key(data):
    name = data.get("name")
    key = data.get("key")

    if key in g_config["keys"]: 
        return 
    
    if name in g_config["keys"].values():
        return 
    g_config["keys"][key] = name 

    save_keys()
    socketio.emit("server_status", {"msg": "Inserted key", "rtn": True})

    on_request_keys()

@socketio.on("delete_key")
def on_delete_key(data):
    source = data.get("source")
    key = data.get("key")
    name = data.get("name")

    debug_print(f"deleting {key} for {name} via {source}")

    if key in g_config["keys"]:
        del g_config["keys"][key]
    else:
        debug_print(f"Did not find {key}")

    save_keys()

    on_request_keys()

@socketio.on("set_api_key_token")
def on_set_api_key_token(data):
    source = data.get("source")
    key = data.get("key")

    g_config["API_KEY_TOKEN"] = key 
    save_keys()


@socketio.on("add_site")
def on_add_site(data):
    global g_database
    g_database.add_site(data.get("site"), data.get("desc", ""))
    g_database.commit()
    on_request_sites()


@socketio.on("update_entry_site")
def on_update_entry_site(data):
    global g_remote_entries
    source = data.get("source")
    upload_id = data.get("upload_id")
    site = data.get("site")
    if source not in g_remote_entries:
        return
    if upload_id not in g_remote_entries[source]:
        return
    g_remote_entries[source][upload_id]["site"] = site

    update = {
        "source": source,
        "relpath": g_remote_entries[source][upload_id]["relpath"],
        "basename": g_remote_entries[source][upload_id]["basename"],
        "update": {"site": site},
    }
    socketio.emit("update_entry", update)


@socketio.on("update_entry_robot")
def on_update_entry_robot(data):
    global g_remote_entries
    # debug_print(data)
    source = data.get("source")
    upload_id = data.get("upload_id")
    robot = data.get("robot")
    if source not in g_remote_entries:
        return
    if upload_id not in g_remote_entries[source]:
        return
    g_remote_entries[source][upload_id]["robot_name"] = robot

    update = {
        "source": source,
        "relpath": g_remote_entries[source][upload_id]["relpath"],
        "basename": g_remote_entries[source][upload_id]["basename"],
        "update": {"robot_name": robot},
    }

    socketio.emit("update_entry", update)


@socketio.on("remote_node_data_ymd")
def on_remote_node_data_ymd(data):
    global g_node_entries
    global g_remote_entries
    global g_selected_action

    source = data.get("source")

    if source not in g_sources["nodes"]:
        g_sources["nodes"].append(source)

    g_selected_action[source] = None

    rtn = {}

    project = data["project"]
    ymd = data["ymd"]
    runs = data["runs"]    


    for run_name, relpaths in runs.items():
        for relpath, entries in relpaths.items():
            for entry in entries:
                orig_id = entry["upload_id"]
                file = os.path.join(relpath, entry["basename"])
                upload_id = get_upload_id(g_config["source"], project, file)
                debug_print((orig_id, upload_id))
                entry["upload_id"] = upload_id
                entry["project"] = project
                g_remote_entries[source][upload_id] = entry

                filepath = get_file_path(source, upload_id)

                if os.path.exists(filepath):
                    g_remote_entries[source][upload_id]["on_server"] = True
                    entry["on_local"] = True

                if os.path.exists(filepath + ".tmp"):
                    g_remote_entries[source][upload_id]["temp_size"] = (
                        os.path.getsize(filepath + ".tmp")
                    )
                else:
                    g_remote_entries[source][upload_id]["temp_size"] = 0

                rtn[upload_id] = entry

    msg = {"entries": rtn,
           "project": project}

    debug_print(f"emit rtn to {source}")
    socketio.emit("node_data_ymd_rtn", msg, to=source)

    pass

@socketio.on("remote_node_data")
def on_remote_node_data(data):
    global g_node_entries
    global g_remote_entries
    global g_selected_action

    source = data.get("source")

    if source not in g_sources["nodes"]:
        g_sources["nodes"].append(source)

    g_selected_action[source] = None

    g_remote_entries[source] = {}

    for project, ymds in data["entries"].items():
        rtn = {}
        for ymd, runs in ymds.items():
            for run_name, relpaths in runs.items():
                for relpath, entries in relpaths.items():
                    for entry in entries:

                        node_upload_id = entry["upload_id"]
                    
                        file = os.path.join(relpath, entry["basename"])
                        upload_id = get_upload_id(g_config["source"], project, file)

                        entry["upload_id"] = upload_id
                        entry["local_id"] = node_upload_id
                        entry["project"] = project
                        entry["on_local"] = True

                        g_remote_entries[source][upload_id] = entry

                        filepath = get_file_path_from_entry(entry)

                        if os.path.exists(filepath):
                            entry["on_remote"] = True
                                            
                        if os.path.exists(filepath + ".tmp"):
                            g_remote_entries[source][upload_id]["temp_size"] = (
                                os.path.getsize(filepath + ".tmp")
                            )
                        else:
                            g_remote_entries[source][upload_id]["temp_size"] = 0

                        # rtn_entries_items = ["on_local","on_remote","upload_id","relpath","basename" ]
                        rtn_entries_items = ["on_local","on_remote","upload_id" ]
                        rtn_entry = {
                            name: entry[name] for name in rtn_entries_items
                        }
                        rtn[node_upload_id] = rtn_entry


        msg = {"entries": rtn,
               "project": project}

        debug_print(f"emit rtn to {source}")
        socketio.emit("node_data_ymd_rtn", msg, to=source)


    # debug_print(data)

    # g_node_entries[source] = data
    # if not source in g_sources["nodes"]:
    #     g_sources["nodes"].append(source)
    #     debug_print(f"added {source} to 'nodes'")

    # msg = {"entries": g_node_entries}

    # socketio.emit("node_data", msg, to=source)
    # socketio.emit("node_data", msg, to=dashboard_room())


# comes from local gui
@socketio.on("server_transfer_files")
def on_server_transer_files(data):
    if g_remote_connection.connected():
        g_remote_connection.server_transfer_files(data)


# comes from remote gui
@socketio.on("transfer_node_files")
def on_transfer_node_files(data):
    debug_print(data)
    source = data.get("source")
    selected_files = data.get("upload_ids")

    filenames = []
    for upload_id in selected_files:
        if not upload_id in g_remote_entries[source]:
            debug_print(
                f"Error! did not find upload id [{upload_id}] in {sorted(g_remote_entries[source])}"
            )
            continue

        filepath = get_file_path(source, upload_id)
        if os.path.exists(filepath):
            continue

        entry = g_remote_entries[source][upload_id]

        # debug_print(entry)

        dirroot = entry["dirroot"]
        reldir = entry["relpath"]
        basename = entry["basename"]
        offset = entry["temp_size"]
        size = entry["size"]
        file = os.path.join(reldir, basename)

        filenames.append((dirroot, file, upload_id, offset, size))

    msg = {"source": data.get("source"), "files": filenames}

    socketio.emit("node_send", msg)


@socketio.on("set_md5")
def on_set_md5(data):
    socketio.emit("set_md5", data)


###########################################
# Redirect message from clients to clients
###########################################
@socketio.on("node_action")
def on_node_action(msg):
    # debug_print(msg)
    socketio.emit("node_action", msg)


@socketio.on("node_status_tqdm")
def on_node_status_tqdm(msg):
    socketio.emit("node_status_tqdm", msg)


@socketio.on("report_node_task_status")
def on_report_node_task_status(msg):
    socketio.emit("report_node_task_status", msg)


@socketio.on("report_node_status")
def on_report_node_status(msg):
    socketio.emit("report_node_status", msg)


@socketio.on("task_reindex_all")
def on_task_reindex_all(data):
    source = data.get("source")
    event = "task_reindex"

    files = []
    all_data = g_database.get_data()
    for project in all_data:
        for robot in all_data[project]:
            for run in all_data[project][robot]:
                for entry in all_data[project][robot][run]:
                    # this assumes that the files are on the same filesystem
                    if entry["datatype"] != ".mcap" and entry["datatype"] != ".bag":
                        continue
                    date = entry["datetime"].split()[0]
                    fullpath = os.path.join(
                        project, date, entry["relpath"], entry["basename"]
                    )
                    files.append(fullpath)

    if len(files) == 0:
        return

    msg = {"source": source, "upload_dir": g_upload_dir, "files": files}

    socketio.emit(event, msg)


# @socketio.on_error_default  # This will catch any event that doesn't have a specific handler
# def catch_all_event_error_handler(e):
#     debug_print(f"An error occurred: {str(e)}")


###########################################
# debug code. Disable for production
###########################################
@socketio.on("debug_clear_data")
def on_debug_clear_data():
    global g_database
    g_database.debug_clear_data()
    send_server_data()


@socketio.on("debug_count_to")
def on_debug_count_to(data):
    debug_print(data)
    source = data.get("source")
    count_to = data.get("count_to")
    event = "count_to"
    msg = {"count_to": count_to, "source": source}

    # socketio.emit(event, msg, to=source)
    socketio.emit(event, msg)


@socketio.on("debug_count_to_next_task")
def on_debug_count_to_next_task(data):
    debug_print(data)
    source = data.get("source")
    count_to = data.get("count_to")
    event = "count_to_next_task"
    msg = {"count_to": count_to, "source": source}

    # socketio.emit(event, msg, to=source)
    socketio.emit(event, msg)


###########################################
# debug code. Disable for production
###########################################
@socketio.on("scan_server")
def on_debug_scan_server():

    debug_print("Scan Server")

    g_database.regenerate()

    for project_name in g_config.get("projects", []):
        g_database.add_project(project_name, "")

    for robot_name in g_config.get("robots", []):
        g_database.add_robot_name(robot_name, "")

    for site_name in g_config.get("sites", []):
        g_database.add_site(site_name, "")

    send_server_data()


##
# authenticate
@app.before_request
def authenticate():
    # debug_print(request)
    
    # Check if the current request is for the login page
    if request.endpoint == "show_login_form" or request.endpoint == "login":
        debug_print(request.endpoint)
        return  # Skip authentication for login page to avoid loop

    api_key = request.headers.get('X-Api-Key')
    if api_key:
        if validate_api_key_token(api_key):
            return
        else:
            return "Invalid API Key", 402

    auth_header = request.headers.get("Authorization")
    if auth_header:
        # debug_print(auth_header)
        auth_type, token = auth_header.split()
        if auth_type.lower() == "bearer":
            api_key_token = token
            # debug_print(api_key_token)
            # Validate the API key token here
            if validate_api_key_token(api_key_token):
                session["api_key_token"] = api_key_token
            else:
                return "Invalid API key token", 402
        elif auth_type.lower() == "basic":

            user = request.headers.get('X-Authenticated-User')  # Header set by Nginx after LDAP auth
            debug_print(user)
            if not user:
                return jsonify({'error': 'Unauthorized-v1'}), 401

            # Generate a token for the authenticated user
            token = generate_token(user)


            response = make_response()
            response.set_cookie(
                "username", user
            )  
            response.set_cookie(
                "token", token, 
            )  

        else:
            return jsonify({'error': 'Unauthorized-v2'}), 401

    else:
        if g_config.get("use_ldap", True):
            return jsonify({'error': 'Unauthorized-v3'}), 401

        username = request.cookies.get("username")
        password = request.cookies.get("password")
        if username and password and validate_user_credentials(username, password):
            # debug_print("Valid")
            session["user"] = (
                username  # You can customize what you store in the session
            )
            return  # continue the request

        return redirect(
            url_for("show_login_form")
        )  # Redirect to login if no valid session or cookies


def validate_api_key_token(api_key_token):
    # this should be more secure
    # for now we will just look up the key
    # debug_print( (api_key_token,  api_key_token in config["keys"]))

    return api_key_token in g_config["keys"]


@app.route("/login", methods=["GET"])
def show_login_form():
    return render_template("login.html")

# Only used for local server. Not used when running LDAP
@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    if validate_user_credentials(username, password):
        response = make_response(redirect(url_for("serve_index")))
        response.set_cookie(
            "username", username, max_age=3600 * 24
        )  # Expires in 24 hour
        response.set_cookie(
            "password", password, max_age=3600 * 24
        )  # Not recommended to store password directly

        api_key_token = None
        for key in g_config["keys"]:
            if g_config["keys"][key].lower() == username.lower():
                api_key_token = key
                break
        if api_key_token is not None:
            response.set_cookie("api_key_token", api_key_token, max_age=3600 * 24)
        else:
            debug_print(f"Failed to find api_key for [{username}]")

        # debug_print(f"----- {username} {api_key_token} -------")

        return response
    else:
        flash("Invalid username or password")
        return redirect(url_for("show_login_form"))


def validate_user_credentials(username, password):
    # debug_print((username, password))
    # Placeholder function to validate credentials
    return username == "admin" and password == "NodeNodeDevices"


# send javascript files
@app.route("/js/<path:path>")
def serve_js(path):
    return send_from_directory("js", path)


@app.route("/css/<path:path>")
def serve_css(path):
    return send_from_directory("css", path)


@app.route("/")
def serve_index():

    response = make_response(send_from_directory("static", "index.html"))
    user = request.headers.get('X-Authenticated-User')  
    if user:
        response.set_cookie("username", user)  

    return response


@app.route("/debug")
def serve_scratch():
    debug_print("Yo")
    return send_from_directory("static", "stratch.html")

@app.route("/node-data", methods=["POST"])
def handle_node_data():
    data = request.get_json()
    source = data.get("source")

    debug_print(f"Got data from node {source}")

    on_remote_node_data(data)

    return jsonify("Received")


@app.route("/transfer-selected", methods=["POST"])
def transfer_selected():
    data = request.get_json()
    selected_files = data.get("files")
    source = data.get("source")

    filenames = []
    for upload_id in selected_files:
        if not upload_id in g_remote_entries[source]:
            debug_print(
                f"Error! did not find upload id [{upload_id}] in {sorted(g_remote_entries[source])}"
            )
            continue

        filepath = get_file_path(source, upload_id)
        if os.path.exists(filepath):
            continue

        dirroot = g_remote_entries[source][upload_id]["dirroot"]
        relpath = g_remote_entries[source][upload_id]["fullpath"].strip("/")
        offset = g_remote_entries[source][upload_id]["temp_size"]
        size = g_remote_entries[source][upload_id]["size"]
        filenames.append((dirroot, relpath, upload_id, offset, size))

    msg = {"source": data.get("source"), "files": filenames}

    socketio.emit("device_send", msg)

    # # debug_print(data)
    return jsonify("Received")


def update_fs_info():
    global g_fs_info
    source = g_config["source"]
    dev = os.stat(g_upload_dir).st_dev
    total, used, free = shutil.disk_usage(g_upload_dir)
    free_percentage = (free / total) * 100
    g_fs_info[source] = {dev: (g_upload_dir, f"{free_percentage:0.2f}")}


def get_datatype(file: str):
    _, ext = os.path.splitext(file)
    return ext


# def get_upload_id(source: str, project: str, file: str):
#     """
#     Generates a unique upload ID based on the provided source, project, name, and file information.

#     Args:
#         source (str): The source of the upload.
#         project (str): The project associated with the upload.
#         name (str): The name of the upload.
#         file (str): The file path or name being uploaded.

#     Returns:
#         str: A unique upload ID generated from the provided information.
#     """
#     val  = f"{source}_{project}_{file.strip('/')}"
#     val  = val.replace("/", "_")
#     val  = val.replace(".", "_")
#     return str(hex(abs(hash(val))))


# set the date of an entry from the input type="datetime-local" field.
@app.route("/update-datetime", methods=["POST"])
def update_datetime():
    global g_remote_entries
    data = request.get_json()

    source = data.get("source")
    upload_id = data.get("upload_id")
    new_datetime = data.get("datetime")

    date, time = new_datetime.split("T")
    formatted_date = f"{date} {time}:00"

    if source in g_remote_entries and upload_id in g_remote_entries[source]:
        g_remote_entries[source][upload_id]["datetime"] = formatted_date

    debug_print(f"set {source} {upload_id} to {new_datetime}")

    return jsonify({"message": "set"})


@app.template_filter()
def dateformat(value):
    date, time = value.split(" ")
    hh, mm, _ = time.split(":")
    return f"{date}T{hh}:{mm}"


@app.route("/report_host", methods=["POST"])
def handle_report_host():
    global g_remote_entries
    global g_fs_info

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    source = data.get("source")

    # note, this could be emitted
    # fs_info[source] = data.get("fs_info")

    if source not in g_sources["report_host"]:
        g_sources["report_host"].append(source)

    send_report_host_data()

    return jsonify({"message": "Connection accepted"}), 200


@app.route("/report_node", methods=["POST"])
def handle_report_node():
    global g_remote_entries
    global g_fs_info

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    source = data.get("source")
    threads = data.get("processors")

    if source not in g_sources["report_node"]:
        g_sources["report_node"].append(source)

    g_report_node_info[source] = {"threads": threads}

    send_report_node_data()

    return jsonify({"message": "Connection accepted"}), 200

def get_dirroot(project:str) -> str:
    root = g_config.get("volume_root", "/")
    volume = g_config["volume_map"].get(project, "").strip("/")
    # debug_print((root, project, volume))
    return os.path.join(root, volume)

def get_file_path_from_entry(entry:dict) -> str:
    project = entry.get("project")

    root = g_config.get("volume_root", "/")
    volume = g_config["volume_map"].get(project, "").strip("/")

    relpath = entry["relpath"]
    filename = entry["basename"]
    try:
        filedir = os.path.join(root, volume, relpath)
    except TypeError as e:
        debug_print((root, volume, relpath))
        raise e

    filepath = os.path.join(filedir, filename)

    return filepath


def get_file_path(source: str, upload_id: str) -> str:
    """
    Returns the full path of a file based on the source and upload_id.

    Parameters:
    source (str): The source of the file.
    upload_id (str): The unique identifier for the file.

    Returns:
    str: The full path of the file.
    """
    entry = g_remote_entries[source][upload_id]
    return get_file_path_from_entry(entry)
    
    # project = g_remote_entries[source][upload_id].get("project")
    # root = g_config.get("volume_root", "/")
    # volume = g_config["volume_map"].get(project, "").strip("/")

    # relpath = g_remote_entries[source][upload_id]["relpath"]
    # filename = g_remote_entries[source][upload_id]["basename"]
    # try:
    #     filedir = os.path.join(root, volume, relpath)
    # except TypeError as e:
    #     debug_print((root, volume, relpath))
    #     raise e

    # filepath = os.path.join(filedir, filename)

    # return filepath


def get_rel_dir(source: str, upload_id: str) -> str:
    project = g_remote_entries[source][upload_id].get("project", None)
    project = project if project else "None"
    date = g_remote_entries[source][upload_id]["datetime"].split()[0]

    relpath = g_remote_entries[source][upload_id]["relpath"]
    filename = g_remote_entries[source][upload_id]["basename"]
    try:
        reldir = os.path.join(project, date, relpath)
    except TypeError as e:
        debug_print((project, date, relpath))
        raise e

    reldir = os.path.join(reldir, filename)

    return reldir


@app.route("/cancel/<string:source>", methods=["GET"])
def handle_cancel(source: str):
    if source in g_selected_action:
        g_selected_action[source] = "cancel"
        socketio.emit("control_msg", {"action": "cancel"}, to=source)
        return jsonify({"message": f"Cancelling transfers for {source}"})
    else:
        return jsonify({"message": f"{source} not found on this server."}), 404


@app.route("/rescan/<string:source>", methods=["GET"])
def handle_rescan(source: str):
    if source in g_selected_action:
        g_selected_action[source] = "rescan"
        g_selected_files_ready[source] = True

        return jsonify({"message": f"Rescanning {source}"})
    else:
        return jsonify({"message": f"{source} not found on this server."}), 404


def send_dashboard_file(msg):
    send_to_all_dashboards("dashboard_file", msg, with_nodes=True)


def send_to_all_dashboards(event, msg, with_nodes:bool=False):
    rooms = []
    rooms.extend(g_dashboard_rooms)
    if with_nodes:
        rooms.extend(g_sources["nodes"])

    for room in rooms:
        socketio.emit(event, msg, to=room)


@app.route("/file/<string:source>/<string:upload_id>", methods=["POST"])
def handle_file(source: str, upload_id: str):

    if source not in g_remote_entries:
        return f"Invalid Source {source}",  503

    if upload_id not in g_remote_entries[source]:
        return f"Invalid ID {upload_id} for {source}", 503

    g_uploads[upload_id] = {
        "display_filename": g_remote_entries[source][upload_id]["basename"],
        "filepath": g_remote_entries[source][upload_id]["relpath"],
        "project": g_remote_entries[source][upload_id]["project"],
        "robot_name": g_remote_entries[source][upload_id]["robot_name"],
        "datetime": g_remote_entries[source][upload_id]["datetime"],
        "date": g_remote_entries[source][upload_id]["datetime"].split()[0],
        "source": source,
        "progress": FileSpeedEstimate(g_remote_entries[source][upload_id]["size"]),
        "status": "uploading",
    }

    offset = request.args.get("offset", 0)
    if offset == 0:
        open_mode = "wb"
        g_uploads[upload_id]["progress"].update_existing(offset)
    else:
        open_mode = "ab"

    cid = request.args.get("cid")
    splits = request.args.get("splits")
    is_last = cid == splits

    filep = request.stream
    filename = g_remote_entries[source][upload_id]["basename"]

    filepath = get_file_path(source, upload_id)
    tmp_path = filepath + ".tmp"

    if os.path.exists(filepath):
        return jsonify({"message": f"File {filename} alredy uploaded"})

    if g_selected_action[source] == "cancel":
        return jsonify({"message": f"File {filename} upload canceled"})

    # keep track of expected size. If remote canceled, we won't know.
    expected = g_remote_entries[source][upload_id]["size"]

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # we use this in multiple location, better to define it.
    cancel_msg = {
        "div_id": f"status_{upload_id}",
        "source": g_config["source"],
        "status": "<B>Canceled</B>",
        "on_device": True,
        "on_server": False,
        "upload_id": upload_id,
    }

    # Start uploading the file in chunks
    chunk_size = 10 * 1024 * 1024  # 1MB chunks
    with open(tmp_path, open_mode) as fid:
        while True:

            if g_selected_action[source] == "cancel":
                send_dashboard_file(cancel_msg)
                # socketio.emit("dashboard_file", cancel_msg, to=dashboard_room())
                # if source in g_sources["nodes"]: 
                #     socketio.emit("dashboard_file", cancel_msg, to=source)

                return jsonify({"message": f"File {filename} upload canceled"})

            try:
                chunk = filep.read(chunk_size)
            except OSError:
                # we lost the connection on the client side.
                send_dashboard_file(cancel_msg)
                # socketio.emit("dashboard_file", cancel_msg, to=dashboard_room())
                # if source in g_sources["nodes"]: 
                #    socketio.emit("dashboard_file", cancel_msg, to=source)

                return jsonify({"message": f"File {filename} upload canceled"})

            if not chunk:
                break
            fid.write(chunk)
            g_uploads[upload_id]["progress"].update(len(chunk))

    os.chmod(tmp_path, 0o777 )

    if os.path.exists(tmp_path) and is_last:
        current_size = os.path.getsize(tmp_path)
        if current_size != expected:
            # transfer canceled politely on the client side, or
            # some other issue. Either way, data isn't what we expected.
            cancel_msg["status"] = (
                "Size mismatch. " + str(current_size) + " != " + str(expected)
            )
            send_dashboard_file(cancel_msg)
            # socketio.emit("dashboard_file", cancel_msg, to=dashboard_room())
            # if source in g_sources["nodes"]: 
            #     socketio.emit("dashboard_file", cancel_msg, to=source)

            return jsonify({"message": f"File {filename} upload canceled"})

        os.rename(tmp_path, filepath)
        g_uploads[upload_id]["status"] = "complete"

        data = {
            "div_id": f"status_{upload_id}",
            "status": "On Device and Server",
            "source": g_config["source"],
            "on_device": True,
            "on_server": True,
            "upload_id": upload_id,
        }
        # socketio.emit("dashboard_file", data, to="client-" + source)
        send_dashboard_file(data)
        # socketio.emit("dashboard_file", data, to=dashboard_room())
        # if source in g_sources["nodes"]: 
        #     socketio.emit("dashboard_file", data, to=source)

    g_remote_entries[source][upload_id]["localpath"] = filepath
    g_remote_entries[source][upload_id]["on_server"] = True
    g_remote_entries[source][upload_id]["dirroot"] = get_dirroot(g_remote_entries[source][upload_id]["project"])

    metadata_filename = filepath + ".metadata"
    with open(metadata_filename, "w") as fid:
        json.dump(g_remote_entries[source][upload_id], fid, indent=True)

    os.chmod(metadata_filename, 0o777)

    g_database.add_data(g_remote_entries[source][upload_id])
    g_database.estimate_runs()
    g_database.commit()
    send_server_data()
    device_revise_stats()

    return jsonify({"message": f"File {filename} chunk uploaded successfully"})


def device_revise_stats():
    stats = {}

    for source in g_remote_entries:
        if source in g_sources["devices"]:
            stats[source] = {
                "total_size": 0,
                "count": 0,
                "start_datetime": None,
                "end_datetime": None,
                "datatype": {},
                "on_server_size": 0,
                "on_server_count": 0,
            }
            for uid in g_remote_entries[source]:
                update_stat(source, uid, stats[source])

    send_to_all_dashboards("device_revise_stats", stats)
    # socketio.emit( "device_revise_stats", stats, to=dashboard_room() )
    # for node in g_sources["nodes"]:
    #     socketio.emit("node_revise_stats", stats, to=node)


def send_device_data():
    global g_remote_entries
    global g_fs_info
    global g_projects

    device_data = {}

    for source in g_remote_entries:
        if source in g_sources["devices"]:
            project = g_projects.get(source)
            device_data[source] = {"fs_info": {}, "entries": {}, "project": project}
            if source in g_fs_info:
                device_data[source]["fs_info"] = g_fs_info[source]
            for uid in g_remote_entries[source]:
                entry = {}
                # entry.update(g_remote_entries[source][uid])
                # debug_print(g_remote_entries[source][uid]["robot_name"])
                for key in ["size", "site", "robot_name", "upload_id", "on_device", "on_server", "basename", "datetime", "topics" ]:
                    entry[key] = g_remote_entries[source][uid][key]

                entry["size"] = humanfriendly.format_size(entry["size"])
                date = g_remote_entries[source][uid]["datetime"].split(" ")[0]
                relpath = g_remote_entries[source][uid]["relpath"]
                device_data[source]["entries"][date] = device_data[source]["entries"].get(date, {})
                device_data[source]["entries"][date][relpath] = device_data[source]["entries"][date].get(relpath, [])
                device_data[source]["entries"][date][relpath].append(entry)

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

                update_stat(source, uid, device_data[source]["stats"][date])
                update_stat(source, uid, device_data[source]["stats"]["total"])

    for room in g_dashboard_rooms:
        debug_print(f"send_device_data to [{room}]")
        # debug_print(json.dumps(device_data, indent=True))
        socketio.emit("device_data", device_data, to=room)


def update_stat(source, uid, stat):
    filename = get_file_path(source, uid)
    on_server = os.path.exists(filename)

    size = g_remote_entries[source][uid]["size"]
    start_time = g_remote_entries[source][uid]["start_datetime"]
    end_time = g_remote_entries[source][uid]["end_datetime"]
    datatype = g_remote_entries[source][uid]["datatype"]

    stat["total_size"] += size
    stat["htotal_size"] = humanfriendly.format_size(stat["total_size"])
    stat["count"] += 1

    if on_server:
        stat["on_server_size"] += size
        stat["on_server_count"] += 1

    stat["on_server_hsize"] = humanfriendly.format_size(stat["on_server_size"])

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
        datatype,
        {"total_size": 0, "count": 0, "on_server_size": 0, "on_server_count": 0},
    )
    stat["datatype"][datatype]["total_size"] += size
    stat["datatype"][datatype]["htotal_size"] = humanfriendly.format_size(
        stat["datatype"][datatype]["total_size"]
    )
    stat["datatype"][datatype]["count"] += 1

    if on_server:
        stat["datatype"][datatype]["on_server_size"] += size
        stat["datatype"][datatype]["on_server_count"] += 1
    stat["datatype"][datatype]["on_server_hsize"] = humanfriendly.format_size(
        stat["datatype"][datatype]["on_server_size"]
    )

    # on_device_status({"source": source})


def send_node_data():
    pass 

    # debug_print("send")
    # msg = {"entries": g_node_entries}

    # socketio.emit("node_data", msg, to=dashboard_room())


def send_server_data():
    # data = g_database.get_send_data()
    data = g_database.get_send_data_ymd_stub()

    stats = g_database.get_run_stats()
    update_fs_info()

    server_data = {
        "entries": data,
        "fs_info": g_fs_info[g_config["source"]],
        "stats": stats,
        "source": g_config["source"],
        "remotes": g_config.get("remote", []),
        "remote_connected": g_remote_connection.connected(),
    }

    send_to_all_dashboards("server_data", server_data, with_nodes=False)
    # socketio.emit("server_data", server_data, to=dashboard_room())


def send_report_host_data():
    msg = {"hosts": []}

    for report_host in g_sources["report_host"]:
        msg["hosts"].append(report_host)

    socketio.emit("report_host_data", msg, to=dashboard_room())
    send_report_node_data()


def send_report_node_data():
    msg = {"nodes": {}}

    for report_node in g_report_node_info:
        if report_node in g_sources["report_node"]:
            msg["nodes"][report_node] = g_report_node_info[report_node]

    socketio.emit("report_node_data", msg, to=dashboard_room())

try:
    setup_zeroconf()
except Exception as e:
    debug_print("Error setting up zero conf. Maybe duplicate process?")
    pass 


# run with CONFIG=$PWD/config/config.ssd.yaml gunicorn -k gevent -w 1 -b "0.0.0.0:8091" "server.app:app"

def main():
    debug_print("enter")
    socketio.run(debug=False, host="0.0.0.0", port=g_config["port"])


if __name__ == "__main__":
    main()