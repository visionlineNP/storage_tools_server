"""
Common or static functions for the Storage Tools Server
"""

import os
import queue
import time 
import psutil
import hashlib 
import socket 
import fcntl
import struct
import redis 
import json

from typing import Generator, List, Tuple

from server.SocketIOTQDM import MultiTargetSocketIOTQDM 
from .debug_print import debug_print 


def get_source_by_mac_address() -> str:
    """Generates a unique source name based on the active interfaces

    Names will be formatted as "SRC-" + name + hash string. 

    Env:
       SERVERNAME: Defaults to "Server"

    Returns:
        str: formated server name 
    """
    macs = []
    addresses = psutil.net_if_addrs()
    for interface in sorted(addresses):
        if interface == "lo":
            continue
        if not is_interface_up(interface):
            continue

        for addr in sorted(addresses[interface]):
            if addr.family == psutil.AF_LINK:  # Check if it's a MAC address
                # if psutil.net_if_stats()[interface].isup:
                macs.append(addr.address.replace(":",""))

    name = hashlib.sha256("_".join(macs).encode()).hexdigest()[:8]

    # debug_print(os.environ.get("SERVERNAME"))
    if "SERVERNAME" in os.environ:
        rtn = f"SRC-{os.environ['SERVERNAME']}-{name}"
    else:
        rtn = f"SRC-{name}"
    # debug_print(rtn)
    return rtn 

def is_interface_up(interface:str) -> bool:
    """Checks if a given interface is up or down

    Args:
        interface (str): Name of an interface from psutils.net_if_address()

    Returns:
        bool: True if interface is currently up, false if not
    """
    path = f"/sys/class/net/{interface}/operstate"
    try:
        with open(path, "r") as fid:
            state = fid.read()
    except NotADirectoryError:
        state = "down"

    state = state.strip()
    return state == "up"


def get_ip_addresses() -> List[str]:
    """Create a list of all ip address for active interfaces

    Returns:
        List[str]: List of ip address as strings
    """
    interfaces = os.listdir("/sys/class/net/")
    ip_addresses = []
    for iface in interfaces:
        
        # debug_print(f"{iface} up is {is_interface_up(iface)}")
        if not is_interface_up(iface):
            continue

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ip_address = fcntl.ioctl(
                sock.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack("256s", iface[:15].encode("utf-8")),
            )[20:24]
            ip_address = socket.inet_ntoa(ip_address)

            if ip_address == "127.0.0.1":
                continue

            ip_addresses.append(ip_address)
        except IOError:
            continue
    return ip_addresses



def dashboard_room(data:dict=None) -> str:
    """Gets the dashboard room for the message

    Reads "room" from message. If "room" is not present, uses "session_token"
    If that isn't present, defaults to "dashboard-DEVICE

    Args:
        data (dict, optional): A data message. Defaults to None.

    Returns:
        str: Room name, dashboard or "dashboard-DEVICE"
    """
    room = None 
    if data:
        room = data.get("room", None)
        if not room and "session_token" in data:
            room = "dashboard-" + data["session_token"]
    if not room:
        room = "dashboard-DEVICE"

    return room


def get_datatype(file: str) -> str:
    """Get the extension for a filename

    Args:
        file (str): filepath

    Returns:
        str: extension
    """
    _, ext = os.path.splitext(file)
    ext.replace(".", "")
    return ext


def get_upload_id(source: str, project: str, file: str) -> str:
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


class EmitRedirect:
    """
    An interface to emulate the SocketIO "emit" function.
    """ 
    def emit(self, event:str, msg:any, to:str=None, debug=False):
        """Emulate the socketio.emit message, with added features

        Args:
            event (str): Name of the event
            msg (any): Message to send, must be JSON-able
            to (str, optional): Where to send the message. Can be None (for all), a source, "all_dashboards", "all_nodes", "add_dashboards_and_all_nodes". Defaults to None.
            debug (bool, optional): Echo this message to stderr. Defaults to False.
        """
        pass 

class SocketIORedirect(EmitRedirect):
    """
    A class to emulate the SocketIO "emit" function.

    Messages are pushed into a Redis "emit" queue, to be 
    processed by the WebscocketServer.

    Envs:
    - REDIS_HOST. Defaults: "localhost"
    """
    def __init__(self) -> None:
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=redis_host, port=6379, db=0)

    def emit(self, event:str, msg:any, to:str=None, debug=False):
        """Emulate the socketio.emit message, with added features

        Args:
            event (str): Name of the event
            msg (any): Message to send, must be JSON-able
            to (str, optional): Where to send the message. Can be None (for all), a source, "all_dashboards", "all_nodes", "add_dashboards_and_all_nodes". Defaults to None.
            debug (bool, optional): Echo this message to stderr. Defaults to False.
        """
        data = {
            "event": event,
            "msg": msg,
            "debug": debug
            }
        if to is not None:
            data["to"] = to

        if debug: debug_print(data)
        self.redis.lpush("emit", json.dumps(data))

class RemoteIORedirect(EmitRedirect):
    """Class to emulate the socketio.emit() function, for remote connections.

    This class will push emit actions into the RemoteWorker "remote_work" queue.

    Envs:
    - REDIS_HOST. Defaults: "localhost"
    """
    def __init__(self) -> None:
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=redis_host, port=6379, db=0)

    def emit(self, event:str, msg:any, to:str=None, debug=False):
        """Emulate the socketio.emit message, with added features

        Args:
            event (str): Name of the event
            msg (any): Message to send, must be JSON-able
            to (str, optional): Where to send the message. Can be None (for all), a source, "all_dashboards", "all_nodes", "add_dashboards_and_all_nodes". Defaults to None.
            debug (bool, optional): Echo this message to stderr. Defaults to False.
        """
        data = {
            "event": event,
            "msg": msg,
            "debug": debug
            }
        if to is not None:
            data["to"] = to

        msg = {
            "action": "remote_emit",
            "data": data
        }

        if debug: debug_print(data)
        self.redis.lpush("remote_work", json.dumps(data))


def build_multipart_data(entry:dict, generator:Generator, total_size:int):
    boundary = "----WebKitFormBoundary" + os.urandom(16).hex()  # Example boundary

    # Build the preamble for JSON data
    json_data = json.dumps(entry).encode('utf-8')
    json_preamble = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"json\"\r\n"
        f"Content-Type: application/json\r\n\r\n"
    ).encode('utf-8')

    # Build the file preamble
    file_preamble = (
        f"\r\n--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"file.bin\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode('utf-8')

    # Build the ending boundary
    end_boundary = f"\r\n--{boundary}--\r\n".encode('utf-8')

    # Define a generator that yields the complete multipart data
    def multipart_stream():
        # Yield JSON preamble and data
        yield json_preamble
        yield json_data

        # Yield file preamble
        yield file_preamble

        # Yield the actual file data in chunks from the generator
        for chunk in generator:
            yield chunk

        # Yield the end boundary
        yield end_boundary

    # Calculate the complete content-length
    content_length = len(json_preamble) + len(json_data) + len(file_preamble) + total_size + len(end_boundary)

    return multipart_stream(), boundary, content_length


class PosMaker:
    """
    Manages positions with a maximum limit, providing the next available position and releasing positions when no longer in use.
    """

    def __init__(self, max_pos) -> None:
        """
        Initializes the PosMaker with a maximum number of positions.
        
        Args:
            max_pos (int): The maximum number of positions available initially.
        """
        self.m_pos = {i: False for i in range(max_pos)}
        self.m_max = max_pos

    def get_next_pos(self) -> int:
        """
        Retrieves the next available position. If all initial positions are in use, it extends the range by one.

        Returns:
            int: The next available position.
        """
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
        """
        Releases a position, making it available again.
        
        Args:
            i (int): The position to release.
        """
        self.m_pos[i] = False


def redis_pbar_thread(messages:queue.Queue, total_size:int, source:str, 
                      socket_events:List[Tuple[str,str,str]], 
                      desc:str, max_threads:int, debug:bool=False):
    """
    A helper function to manage progress bar updates with Socket.IO events routed through Redis interfaces.

    Args:
        messages (queue.Queue): Queue to receive progress bar actions and updates.
        total_size (int): Total size for the main progress bar to track, in bytes.
        source (str): Identifier for the source emitting progress updates.
        socket_events (List[Tuple[str, str, str]]): List of Socket.IO events with structure (location, event_name, room).
            - `location` can be "local_sio" or "remote_sio" to determine where the event should be emitted.
            - `event_name` is the name of the event to be emitted.
            - `room` specifies the room for the event.
        desc (str): Description for the main progress bar.
        max_threads (int): Maximum number of child progress bars (each associated with a thread).
        debug (bool, optional): Flag for enabling debug mode, which echoes messages to stderr. Defaults to False.

    Workflow:
        - Initializes `local_sio` and `remote_sio` interfaces based on `socket_events`:
            - If `sio_location` is "local_sio", a `SocketIORedirect` instance (implements `EmitRedirect`) is used.
            - If `sio_location` is "remote_sio", a `RemoteIORedirect` instance (implements `EmitRedirect`) is used.
        - Transforms `socket_events` to `redis_events`, each using the correct `EmitRedirect`-compliant instance.
        - Calls `pbar_thread` to handle progress bar management with the updated `redis_events`.

    Notes:
        This function prepares `socket_events` for Redis-based communication by categorizing events 
        according to their required Socket.IO redirect interface before passing them to `pbar_thread`.
        Both `SocketIORedirect` and `RemoteIORedirect` classes implement the `EmitRedirect` interface, 
        ensuring compatibility with the event emission requirements.
    """

    local_sio = None
    remote_sio = None 

    redis_events = []
    for (sio_location, event, room) in socket_events:
        if sio_location == "local_sio":
            if not local_sio: local_sio = SocketIORedirect()
            redis_events.append((local_sio, event, room))
        elif sio_location == "remote_sio":
            if not remote_sio: remote_sio = RemoteIORedirect()
            redis_events.append((remote_sio, event, room))

    pbar_thread(messages, total_size, source, redis_events, desc, max_threads, debug=debug)
       

def pbar_thread(messages:queue.Queue, total_size:int, source:str, 
                socket_events:List[Tuple[EmitRedirect,str,str]], 
                desc:str, max_threads:int, debug:bool=False):
    
    """
    A thread function to manage multiple progress bars for tracking data processing progress and emitting updates.

    Args:
        messages (queue.Queue): Queue to receive progress bar actions and updates.
        total_size (int): Total size for the main progress bar to track, in bytes.
        source (str): Identifier for the source emitting progress updates.
        socket_events (List[Tuple[EmitRedirect, str, str]]): List of Socket.IO events as (emit_interface, event_name, room).
        desc (str): Description for the main progress bar.
        max_threads (int): Maximum number of child progress bars (each associated with a thread).
        debug (bool, optional): Flag for enabling debug mode, which echoes messages to stderr. Defaults to False.

    Workflow:
        - Initializes a main progress bar for tracking the `total_size`.
        - Processes messages from `messages` queue to manage child progress bars:
            - "main_pbar": Updates the main progress bar.
            - "child_pbar": Manages child progress bars by creating, updating, or closing them based on actions.
            - "close": Terminates the thread and closes all active progress bars.        
    """

    pos_maker = PosMaker(max_threads)
    positions = {}
    pbars = {}
    pbars["main_pbar"] = MultiTargetSocketIOTQDM(total=total_size, unit="B", unit_scale=True, leave=False, position=0, delay=1, desc=desc, source=source,socket_events=socket_events, debug=debug)

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
                pbars[position] = MultiTargetSocketIOTQDM(total=size, unit="B", unit_scale=True, leave=False, position=position+1, delay=1, desc=desc, source=source,socket_events=socket_events)
                continue
            if action == "update":
                position = positions.get(name, None)
                if position == None:
                    debug_print(f"Do not have pbar for {name}")
                    for pname in positions:
                        debug_print(f"{pname} {positions[pname]}")
                    continue
                size = action_msg["size"]
                if position in pbars:
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
                del positions[name]

    positions = pbars.keys()
    for position in positions:
        pbars[position].close()


def get_device_name(path:str) -> str:
    """
    Returns the device name for the given path by comparing the path's device ID
    with device IDs of mounted partitions. Returns None if no match is found.

    Args:
        path (str): File system path to check.

    Returns:
        str: Device name associated with the path, or None if not found.
    """
    device_id = os.stat(path).st_dev
    for partition in psutil.disk_partitions(all=True):
        try:
            if os.stat(partition.mountpoint).st_dev == device_id:
                return partition.device
        except PermissionError:
            pass 
    return None
