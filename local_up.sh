#!/usr/bin/env bash

if [[ ! -e config/keys.yaml ]]; then
    cp config/keys_placeholder.yaml config/keys.yaml
fi

docker compose -f docker-compose-local.yaml --env-file config.local.env down
docker compose -f docker-compose-local.yaml  --env-file config.local.env up --build --remove-orphans