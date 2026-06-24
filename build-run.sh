#!/bin/bash
cd /home/ubuntu/_qoder/gs-vercount
# Build inside gs-vercount using local context
podman build -t localhost/gs-vercount:latest -f Containerfile .
podman-compose up -d --force-recreate
