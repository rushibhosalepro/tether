#!/usr/bin/env bash
# One command from nothing to a blocked PR check. ~6 minutes, most of it Docker.
set -euo pipefail

python -m pip install --quiet acryl-datahub
datahub docker quickstart
datahub datapack load showcase-ecommerce

python -m pip install --quiet -e .
python -m seed.emit_ml_layer

echo
echo "DataHub:  http://localhost:9002"
echo "Now run:  tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch --pr-url local"
