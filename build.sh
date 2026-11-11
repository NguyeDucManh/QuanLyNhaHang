#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

python -m pip install -r requirements-production.txt
python manage.py check
python manage.py download_ai_models --face-only
python manage.py collectstatic --noinput
# Migrations, seeds and training deliberately require separate operator actions.
