import os
import yaml 

from .debug_print import debug_print
from .database import Database, get_upload_id



config_filename = os.environ.get("CONFIG", "config/config.yaml")

debug_print(f"Using {config_filename}")
with open(config_filename, "r") as f:
    g_config = yaml.safe_load(f)

    g_upload_dir = g_config["upload_dir"]

    v_root = g_config.get("volume_root", "/")
    v_map = g_config.get("volume_map", {}).copy()
    for name in v_map:
        v_map[ name ] = os.path.join(v_root,  v_map.get(name, "").strip("/"))
         
    blackout = g_config.get("blackout", [])

    g_database = Database(g_upload_dir, g_config["source"], v_map, blackout)

g_database.regenerate()