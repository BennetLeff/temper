#!/bin/zsh
# Licensed models stay in this folder's ignored vendor cache.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p vendor
curl -fsSL -A 'Mozilla/5.0' -o vendor/cfd7-650.zip https://www.infineon.com/assets/row/public/documents/24/50/infineon-power-coolmos-cfd7-mosfet-650v-spice-simulationmodels-en.zip
echo '5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d  vendor/cfd7-650.zip' | shasum -a 256 -c -
unzip -p vendor/cfd7-650.zip IFX_CFD7_650V.lib > vendor/IFX_CFD7_650V.lib
echo '02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b  vendor/IFX_CFD7_650V.lib' | shasum -a 256 -c -
