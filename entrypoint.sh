#!/usr/bin/bash

gunicorn -k gthread -w 4 --threads 8 -b 0.0.0.0:${PORT} --timeout 30 server.frontApp:app
