# storage_tools_server

AIRLab storage tool server

## Install

The Storage Tools Server can be run either as a console app, or as a Docker Compose container.

Step 1. Clone this repo

Step 2. Configure

Edit the `config/config.yaml` file to match your configuration.

### REQUIRED UPDATES

* `server name` must be unique.  
* `upload_dir` is the location for uploads.  This must be readable and writeable by the user running the Server.

### Run as Console App

#### Step 1. Create a python virtual env

``` bash
cd storage_tools_server
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

#### Step 2. Run

1. Activate the virtual environment.

    ``` bash
    cd storage_tools_server

    # Activate if not already active
    . venv/bin/activate
    ```

2. Set the environment variables.
    * `HOSTNAME` should be the name or IP address of the server on the same network as the upload devices.  It is ok to set this to `localhost` or `127.0.0.1` when uploading to another server.  
    * `CONFIG` is the full path to the `config.yaml` in use.  By default, the app will use `$PWD/config/config.yaml`

    ``` bash
    export HOSTNAME=127.0.0.1 
    export CONFIG=$PWD/config/config.ssd2.yaml
    ```

3. Run the app

    ``` bash
    gunicorn -k gevent -w 1 -b "0.0.0.0:8092" --timeout 120 "server.app:app"
    ```

#### Step 3. Stopping the server

Control-c in the window, or `kill -hup PID` where PID is the Process ID, found via `ps`.

## Runnning on server

``` bash
ssh airlab-storage.andrew.cmu.edu
cd {dir for server}
sudo -s
HOSTNAME=airlab-storage docker-compose down
HOSTNAME=airlab-storage docker-compose up --build
```
