#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail

# Render uses CPU inference. Install the official CPU build before resolving
# requirements.txt, whose torch==2.14.1 also accepts the 2.14.1+cpu local version.
# Keep this pin aligned with requirements.txt; never fall back silently to CUDA.
if [[ "$(uname -s)" == "Linux" ]]; then
  python -m pip install 'torch==2.14.1+cpu' --index-url https://download.pytorch.org/whl/cpu
fi
python -m pip install -r requirements-production.txt
