#!/usr/bin/env bash
HOSTNAME=airlab-storage docker-compose down 
HOSTNAME=airlab-storage docker-compose up --build --remove-orphans
