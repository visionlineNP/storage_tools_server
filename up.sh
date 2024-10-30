#!/usr/bin/env bash

docker-compose --env-file config.prod.env down
docker-compose --env-file config.prod.env up --build --remove-orphans
