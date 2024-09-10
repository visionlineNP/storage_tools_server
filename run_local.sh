#!/usr/bin/env bash


CONFIG=$PWD/config/config.ssd.yaml gunicorn -k gevent --timeout 120 -w 1 -b "0.0.0.0:8091" "server.app:app"