#!/bin/bash

while true; do
    python bot.py >> /dev/stdout 2>> /dev/stderr &
    pid=$!
    sleep $((($(date -d '04:00' +%s) - $(date +%s) + 86400) % 86400))
    kill $pid
done
