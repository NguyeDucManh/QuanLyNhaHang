#!/usr/bin/env bash
set -euo pipefail
python scripts/render512_fixture.py
exec daphne -b 127.0.0.1 -p 8100 scripts.render512_app:application
