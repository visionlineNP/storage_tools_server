#!/usr/bin/env bash


HOSTNAME=127.0.0.1 CONFIG=$PWD/config/config.ssd.yaml gunicorn -k gevent -w 1 -b "0.0.0.0:8091" "server.app:app"