# storage_tools_server

AIRLab storage tool server

## Install

The Storage Tools Server can be run either as a console app, or as a Docker Compose container.

Step 1. Clone this repo

Step 2. Configure

Edit the `config/config.yaml` file to match your configuration.

### REQUIRED UPDATES

* `upload_dir` is the location for uploads.  This must be readable and writeable by the user running the Server.
* `volume_root` sets the prefix for all entries in the `volume_map`.  This must be readable and writeable by the user running the Server. If you want to organize your data as `/mnt/data/first` and `/mnt/data/second`, you would set the `volume_root` to `/mnt/data`
* `volume_map` is a mapping from project name to `volume_root/{path}`.  All projects must have a mapping. If you want to organize your data as `/mnt/data/first/datasets/experiments` and `/mnt/data/second/datasets/experiments`, you would set the `volume_root` to `/mnt/data`. Then set `volume_map` to

    ```yaml
    volume_root:
      - first: /first/datasets/experiments
      - second: /second/datasets/experiments
    ```

    All uploaded data to `first` will be under `/mnt/data/first/datasets/experiments`.  

### Optional updates

* `port`.  The TCP port that the server runs on.  Defaults to 8091.  If you change this, make sure to change this in the run step.  
* `remote`. List of remote servers for pushing data.  

### Run as Console App

#### Step 1. Create a python virtual env

``` bash
cd ~/src
git clone https://github.com/castacks/storage_tools_server
cd storage_tools_server
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

#### Step 2. Run

1. Activate the virtual environment.

    ``` bash
    cd ~/src/storage_tools_server

    # Activate if not already active
    . venv/bin/activate
    ```

2. Set the environment variables.
    * `CONFIG` is the full path to the `config.yaml` in use.  By default, the app will use `$PWD/config/config.yaml`
    * `PORT` is the same port as define in the optional setup. The default is 8091.

    ``` bash
    export CONFIG=$PWD/config/config.yaml
    export PORT=8091
    ```

3. Run the app

    ``` bash
    gunicorn -k gevent -w 1 -b "0.0.0.0:${PORT}" --timeout 120 "server.app:app"
    ```

    Point your favorite web browser at `http://localhost:${PORT}`. The default user is `admin` and the default password is `NodeNodeDevices`.

#### Step 3. Stopping the server

Control-c in the window, or `kill -hup PID` where PID is the Process ID, found via `ps`.

## Runnning on server

``` bash
ssh airlab-storage.andrew.cmu.edu
cd {dir for server}
sudo -s
docker-compose down
docker-compose up --build
```

## Guides

* [Troubleshooting](docs/Troubleshooting.md)
* [API Keys, Adding New Device](docs/KeyManagement.md)
