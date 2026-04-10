#!/bin/bash
set -euo pipefail

mkdir -p /data
cp /configs/*.yaml /data/ 2>/dev/null || true

echo "Estructura /configs:"
find /configs -type f | sort || true

echo "Estructura /data:"
find /data -type f | sort || true

python3 /app/server.py &
nginx -g "daemon off;"
