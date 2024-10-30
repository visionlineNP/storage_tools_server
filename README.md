# storage_tools_server

AIRLab storage tool server

## Install

The Storage Tools Server can be run either as a console app, or as a Docker Compose container.

### Step 1. Clone this repo

```bash
mkdir -p  ~/src/castacks
cd ~/src/castacks
git clone https://github.com/castacks/storage_tools_server`
cd storage_tools_server
```

### Step 2. Configure

Edit `config.local.env` to match your configuration.

Example config:

```bash
# ########################################################
#                          Localize
# ########################################################

# Display name of your local server 
# The app will add a machine based hash and port to the name. 
SERVERNAME=LocalServer

# Change this to the top level of where you are storing local files
VOLUME_ROOT="/media/norm/Extreme SSD1/uploads/"

# ########################################################
#                     Do not change
# ########################################################

# These do not need to change. 
CONFIG=/app/config/config.local.yaml
PORT=8091
REDIS_HOST=localhost
REDIS_URL=redis://127.0.0.1:6379/0
```

### Run The Server Locally

#### Launching the Server

```bash
cd ~/src
cd storage_tools_server
./local_up.sh
```

Point your favorite web browser at `http://localhost:${PORT}`. The default user is `admin` and the default password is `NodeNodeDevices`.

#### Stopping the server

Control-c in the window, or `./local_down.sh`

## Runnning on the NAS

``` bash
ssh airlab-storage.andrew.cmu.edu
cd {dir for server}
sudo -s
./up.sh
```

## Guides

* [How the Data Flows in the System](docs/DataFlow.md)
* [Using the Dashboard](docs/Dashboard.md)
* [Troubleshooting](docs/Troubleshooting.md)
* [API Keys, Adding New Device](docs/KeyManagement.md)

## Known bugs

[Known bugs](docs/KnownBugs.md)
