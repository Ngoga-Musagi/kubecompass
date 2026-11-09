#!/bin/bash
# Starts the API (internal, 127.0.0.1:8000) and the web server (public, $PORT); exits if either dies.
set -euo pipefail
cd /app
kubecompass ensure || echo "WARNING: ensure failed; API will report 503 until data is indexed"
uvicorn app.main:app --app-dir /app/backend --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips='*' &
cd /app/web && HOSTNAME=0.0.0.0 node server.js &
wait -n
exit $?
