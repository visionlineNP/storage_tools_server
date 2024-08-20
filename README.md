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

Step 1. Create a python virtual env

``` bash
cd storage_tools_server
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

Step 2. Run

``` bash
cd storage_tools_server

# Activate if not already active
. venv/bin/activate
python ./server/app.py -c config/config.yaml
```

Step 3. Stopping the server

Control-c in the window, or `kill -hup PID` where PID is the Process ID, found via `ps`. 

### Run as Docker Compose

Step 1. Install Docker Compose

Step 2. Clone this repo

Step 3.  Build the Docker Compose image

``` bash
cd storage_tools_server
. env.sh 
docker compose build
```

Step 4. Run the Docker Compose Image

``` bash
cd storage_tools_server
. env.sh
docker compose up
```

Step 5. Stop the server

Control-c in the running console, or `docker compose stop`