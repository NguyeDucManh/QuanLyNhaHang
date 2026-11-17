#!/usr/bin/env bash
set -euo pipefail
# Check actual runtime libraries; never migrate, seed or update the database.
python scripts/check_face_native.py
exec daphne -b 0.0.0.0 -p "${PORT:-10000}" restaurant_system.asgi:application
