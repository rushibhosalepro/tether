# One command from nothing to a blocked PR check. ~6 minutes, most of it Docker.
$ErrorActionPreference = "Stop"

python -m pip install --quiet acryl-datahub
datahub docker quickstart
datahub datapack load showcase-ecommerce

python -m pip install --quiet -e .
python -m seed.emit_ml_layer

Write-Host ""
Write-Host "DataHub:  http://localhost:9002"
Write-Host "Now run:  tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch --pr-url local"
