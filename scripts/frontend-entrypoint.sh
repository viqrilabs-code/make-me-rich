#!/usr/bin/env sh
set -eu

cd /app/frontend
exec npm run start -- --hostname 0.0.0.0 --port 3000

