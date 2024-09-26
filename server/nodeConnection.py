import json
import os 
import queue 
import requests
import gevent 


from .SocketIOTQDM import SocketIOTQDM
from .debug_print import debug_print


def build_multipart_data(entry, generator, total_size):
    boundary = "----WebKitFormBoundary" + os.urandom(16).hex()  # Example boundary
    boundary_bytes = boundary.encode('utf-8')

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


class NodeConnection:
    def __init__(self, config, sio) -> None:
        self.m_signal = None 

        self.m_config = config 
        self.m_sio = sio    
        self.m_node_source = config["source"]     


        pass

    def cancel(self):
        self.m_signal = "cancel"

    def sendFiles(self, filelist, base_url):
        # debug_print((base_url, filelist))
        local_status_event = "server_status_tqdm"
        self.m_signal = None 

        num_threads = min(self.m_config["threads"], len(filelist))
        url = f"{base_url}/file"

        #  source = self.m_config["source"]
        # debug_print(f"Source: {self.m_node_source}")
        source = self.m_node_source
        api_key_token = self.m_config["API_KEY_TOKEN"]


        total_size = 0
        file_queue = queue.Queue()
        for file_pair in filelist:
            # debug_print(f"add to queue {file_pair}")
            offset = file_pair[3]
            size = file_pair[4]
            try:
                total_size += int(size) - int(offset)
            except ValueError as e:
                debug_print(file_pair)
                raise e 
            
            # debug_print(file_pair)
            file_queue.put(file_pair)

    
        with SocketIOTQDM(total=total_size, unit="B", unit_scale=True, desc="File Transfer", position=0, 
                          leave=False, source=self.m_node_source, socket=self.m_sio, event=local_status_event) as local_main_pbar:

            def worker(index:int):
                # debug_print("Enter")
                with requests.Session() as session:
                    while True:
                        try:                            
                            project, file, upload_id, offset, total_size, entry = file_queue.get(block=False)
                            offset = int(offset)
                            total_size = int(total_size)

                            # debug_print((dirroot, file, upload_id, offset, total_size))
                        except queue.Empty:
                            break 
                        
                        if self.m_signal == "cancel":
                            break

                        dirroot = self.m_config["volume_map"].get(project, "/").strip("/")
                        fullpath = os.path.join( self.m_config["volume_root"], dirroot, file.strip("/"))
                        if not os.path.exists(fullpath):
                            local_main_pbar.update()
                            debug_print(f"{fullpath} not found" )
                            continue 

                        # total_size = os.path.getsize(fullpath)

                        with open(fullpath, 'rb') as file:
                            params = {}
                            if offset > 0:
                                file.seek(offset)
                                params["offset"] = offset 
                                total_size -= offset 
                            
                            # debug_print(headers)
                            # Setup the progress bar
                            with SocketIOTQDM(total=total_size, unit="B", unit_scale=True, leave=False, position=1+index, source=self.m_config["source"], socket=self.m_sio, event=local_status_event) as local_pbar:
                                def read_and_update():
                                    while True:
                                        # Read the file in chunks of 4096 bytes (or any size you prefer)
                                        chunk = file.read(1024*1024)
                                        if not chunk:
                                            break
                                        yield chunk
                                        # Update the progress bar
                                        local_pbar.update(len(chunk))
                                        local_main_pbar.update(len(chunk))
                                        
                                        if self.m_signal:
                                            if self.m_signal == "cancel":
                                                break
                                
                                multipart_stream, boundary, content_length = build_multipart_data(entry, read_and_update(), total_size)

                            # Set headers
                                headers = {
                                    "Authorization": f"Bearer {api_key_token}",
                                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                                }


                                response = session.post(url + f"/{source}/{upload_id}", data=multipart_stream, headers=headers)
                                
                                # debug_print(f"{url} {source} {upload_id} {params} {headers}")
                                # Make the POST request with the streaming data
                                # response = session.post(url + f"/{source}/{upload_id}", params=params, data=read_and_update(), headers=headers)                                

                                if response.status_code != 200:
                                    debug_print(("Error uploading file:", response.text, response.status_code))
    
            greenlets = []
            for i in range(num_threads):
                greenlet = gevent.spawn(worker, i)  # Spawn a new green thread
                greenlets.append(greenlet)

            # Wait for all green threads to complete
            gevent.joinall(greenlets)

            debug_print("pull complete")

        self.m_signal = None 

    