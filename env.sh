
# Docker Compose ENVS
# run `. env.sh` before running `docker compose` for the first time, or if any of these values change. 

export CONFIG_FILE="/home/norm/src/airlab/storage_tools_server/config/config.small.yaml"
export UPLOAD_DIR="/media/norm/Extreme SSD/uploads_small"

export CUSTOM_UID=$(id -u)
export CUSTOM_GID=$(id -g)
export CUSTOM_USERNAME="devserver"
