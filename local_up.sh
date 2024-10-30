#!/usr/bin/env bash

docker compose -f docker-compose-local.yaml --env-file config.local.env down
docker compose -f docker-compose-local.yaml  --env-file config.local.env up --build --remove-orphans