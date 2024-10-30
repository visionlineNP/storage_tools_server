# Developer Tips

The Storage Tools Server is split up into three parts, the Front End, the Back End, and the Database/Redis. It can be helpful to restart only the Front End or the Back End without having to create a new docker image.  

Create three terminals, starting in the `storage_tools_server` directory.

The Database/Redis must always be started before the Back End. The Front End and Back End can be restarted without consequences.

This example will create a server named "LocalServer" on port 8091.

> Notice!
> Make sure to set `VOLUME_ROOT` to the same value in your `config.local.env`

## Terminal 1. Database / Redis

```bash
cd ~/src/storage_tools_server/
./redis_up.sh
```

The `redis_up.sh` script:

```bash
#!/usr/bin/env bash
docker compose -f docker-compose-redis.yaml down
docker compose -f docker-compose-redis.yaml up --build --remove-orphans
```

## Terminal 2. Back End

```bash
cd ~/src/storage_tools_server/
VOLUME_ROOT="/media/norm/Extreme SSD1/uploads/" SERVERNAME="LocalServer" REDIS_URL="http://localhost:6397" CONFIG="config/config.local.yaml" python -m server.backApp
```

## Terminal 3. Front End

```bash
gunicorn -k gthread -w 4 --threads 8 -b 0.0.0.0:8091 --timeout 30 server.frontApp:app --env SERVERNAME="LocalServer" --env CONFIG="config/config.local.yaml" --env VOLUME_ROOT="/media/norm/Extreme SSD1/uploads/"
```
