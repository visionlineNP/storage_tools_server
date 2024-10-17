
import os 
import psutil
import hashlib 
import socket 
import fcntl
import struct


from .debug_print import debug_print 

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
        
        debug_print(f"{iface} up is {is_interface_up(iface)}")
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
    return ext
