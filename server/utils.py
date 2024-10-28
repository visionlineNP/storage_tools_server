
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

from server.SocketIOTQDM import MultiTargetSocketIOTQDM 


from .debug_print import debug_print 

def get_source_by_mac_address():
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

    debug_print(os.environ.get("SERVERNAME"))
    if "SERVERNAME" in os.environ:
        rtn = f"SRC-{os.environ['SERVERNAME']}-{name}"
    else:
        rtn = f"SRC-{name}"
    debug_print(rtn)
    return rtn 

def is_interface_up(interface):
    path = f"/sys/class/net/{interface}/operstate"
    try:
        with open(path, "r") as fid:
            state = fid.read()
    except NotADirectoryError:
        state = "down"

    state = state.strip()
    return state == "up"


# grab all the ip address that this server has.
def get_ip_addresses():
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



def dashboard_room(data=None):
    room = None 
    if data:
        room = data.get("room", None)
        if not room and "session_token" in data:
            room = "dashboard-" + data["session_token"]
    if not room:
        room = "dashboard-DEVICE"

    return room


def get_datatype(file: str):
    _, ext = os.path.splitext(file)
    ext.replace(".", "")
    return ext


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


class SocketIORedirect:
    def __init__(self) -> None:
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis = redis.StrictRedis(host=redis_host, port=6379, db=0)

    def emit(self, event:str, msg:any, to=None, debug=False):
        data = {
            "event": event,
            "msg": msg,
            "debug": debug
            }
        if to is not None:
            data["to"] = to

        if debug: debug_print(data)
        self.redis.lpush("emit", json.dumps(data))


def build_multipart_data(entry, generator, total_size):
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


def pbar_thread(messages:queue.Queue, total_size, source, socket_events, desc, max_threads, debug=False):
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
