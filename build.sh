#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

bash scripts/install_production.sh
python scripts/check_face_native.py
python manage.py check
python manage.py download_ai_models --face-only
python manage.py collectstatic --noinput
# Migrations, seeds and training deliberately require separate operator actions.
