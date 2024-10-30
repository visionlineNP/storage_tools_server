#!/usr/bin/env bash

docker compose -f docker-compose-redis.yaml down
docker compose -f docker-compose-redis.yaml up --build --remove-orphans