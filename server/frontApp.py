
import flask 
import flask_socketio
import os 
from server.debug_print import debug_print
from .WebsocketServer import WebsocketServer


# prepare the app
app = flask.Flask(__name__)
app.config["SECRET_KEY"] = "AirLabKeyKey"


redis_host = os.environ.get("REDIS_HOST", "localhost")
origins = "*"
socketio = flask_socketio.SocketIO(
    app, 
    cors_allowed_origins=origins,
    ping_interval=25, 
    ping_timeout=60, 
    max_http_buffer_size=200000000, 
    logger=False, 
    engineio_logger=False, 
    message_queue=f"redis://{redis_host}:6379/0",  # Redis message queue
    async_mode="threading"
)



server = None 

def create_server():
    global server 
    server = WebsocketServer(socketio)

    app.before_request(server.authenticate)
    app.route("/")(server.index)
    app.route("/show_login_form")(server.show_login_form)
    app.route("/login", methods=["POST"])(server.login)
    app.route("/file/<string:source>/<string:upload_id>", methods=["POST"])(server.handle_file)
    app.route("/download/<string:upload_id>")(server.download_file)
    app.route("/uploadKeys", methods=["POST"])(server.upload_keys)
    app.route('/downloadKeys')(server.download_keys)
    app.route("/static/js/<path:path>")(server.serve_js)
    app.route("/static/css/<path:path>")(server.serve_css)


    socketio.on("join")(server.on_join)
    # socketio.on("leave")(server.on_leave)
    socketio.on("connect")(server.on_connect)
    socketio.on("disconnect")(server.on_disconnect)

    # # send data to ui
    socketio.on("request_new_data")(server.on_request_new_data)
    socketio.on("request_files_exist")(server.on_request_files_exist)
    socketio.on("request_remote_files_exist")(server.on_request_remote_files_exist)

    # config
    socketio.on("request_projects")(server.on_request_projects)
    socketio.on("add_project")(server.on_add_project)
    socketio.on("set_project")(server.on_set_project)
    socketio.on("edit_project")(server.on_edit_project)
    socketio.on("delete_project")(server.on_delete_project)

    socketio.on("request_robots")(server.on_request_robots)
    socketio.on("add_robot")(server.on_add_robot)
    socketio.on("update_entry_robot")(server.on_update_entry_robot)

    socketio.on("request_sites")(server.on_request_sites)
    socketio.on("add_site")(server.on_add_site)
    socketio.on("update_entry_site")(server.on_update_entry_site)

    socketio.on("request_keys")(server.on_request_keys)
    socketio.on("generate_key")(server.on_generate_key)
    socketio.on("insert_key")(server.on_insert_key)
    socketio.on("delete_key")(server.on_delete_key)
    socketio.on("set_api_key_token")(server.on_set_api_key_token)


    # # search
    socketio.on("request_search_filters")(server.on_request_search_filters)
    socketio.on("search")(server.on_search)

    # remote node
    socketio.on("request_node_ymd_data")(server.on_request_node_ymd_data)
    socketio.on("remote_node_data")(server.on_remote_node_data)
    socketio.on("remote_node_data_block")(server.on_remote_node_data_block)
    socketio.on("request_cancel_node_pull_transfer")(server.on_request_remote_cancel_tranfer)
    socketio.on("request_debug_send")(server.on_request_debug_send)

    # # remote connections
    # socketio.on("control_msg")(server.on_control_msg)
    # pull from remote     
    socketio.on("remote_request_files")(server.on_remote_request_files)    
    # from UI, cancel pull
    socketio.on("request_remote_cancel_transfer")(server.on_request_remote_cancel_tranfer)
    # from ui, cancel push
    socketio.on("request_cancel_push_transfer")(server.on_request_cancel_push_transfer)
    # from remote connection 
    socketio.on("remote_cancel_transfer")(server.on_remote_cancel_transfer)
    socketio.on("remote_transfer_files")(server.on_remote_transfer_files)
    # socketio.on("request_node_ymd_data")(server.on_request_node_ymd_data)
    socketio.on("request_remote_ymd_data")(server.on_request_remote_ymd_data)
    socketio.on("server_status_tqdm")(server.on_server_status_tqdm)
    # request from UI to local to transfer files
    socketio.on("server_transfer_files")(server.on_server_transfer_files)
    # request from RemoteWorker to Server to transfer files
    socketio.on("transfer_node_files")(server.on_transfer_node_files)

    # server
    socketio.on("request_server_data")(server.on_request_server_data)
    socketio.on("request_server_ymd_data")(server.on_request_server_ymd_data)
    socketio.on("server_connect")(server.on_server_connect)
    socketio.on("server_disconnect")(server.on_server_disconnect)
    socketio.on("server_refresh")(server.on_server_refresh)

    # # device related messages
    socketio.on("device_status")(server.on_device_status)
    socketio.on("device_status_tqdm")(server.on_device_status_tqdm)
    socketio.on("device_scan")(server.on_device_scan)
    # socketio.on("device_files_items")(server.on_device_files_items)
    # socketio.on("device_files")(server.on_device_files)
    socketio.on("request_device_ymd_data")(server.on_request_device_ymd_data)
    socketio.on("device_remove")(server.on_device_remove)
    socketio.on("device_request_files")(server.on_device_request_files)
    socketio.on("device_cancel_transfer")(server.on_device_cancel_transfer)
    socketio.on("device_data")(server.on_device_data)
    socketio.on("device_data_block")(server.on_device_data_block)
    socketio.on("estimate_runs")(server.on_estimate_runs)

    # # debug 
    # socketio.on("clear_data")(server.on_debug_clear_data)
    socketio.on("scan_server")(server.on_debug_scan_server)
    socketio.on("debug_send")(server.on_debug_send)


create_server()

def main():
    debug_print(" ---- run ----")
    socketio.run(app=app, debug=False, host="0.0.0.0", port=server.m_config["port"])

if __name__ == "__main__":
    main()    