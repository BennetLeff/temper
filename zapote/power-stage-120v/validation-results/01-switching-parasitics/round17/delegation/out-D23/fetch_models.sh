#!/bin/zsh
# Licensed models stay in this folder's ignored vendor cache.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p vendor
curl -fsSL -o vendor/slum881.zip https://www.ti.com/lit/zip/slum881
echo 'a78cde1efc300da2758bb2e2ff8ce9d6a115acea7b2d5336e1b32a2152a2ab5e  vendor/slum881.zip' | shasum -a 256 -c -
unzip -p vendor/slum881.zip ucc21550-q1.lib > vendor/ucc21550-q1.lib
echo '4355b47c5ee17cd416075f86f3b80e76b013125f9539fe9ac04b077136ea2b22  vendor/ucc21550-q1.lib' | shasum -a 256 -c -
curl -fsSL -A 'Mozilla/5.0' -o vendor/cfd7-650.zip https://www.infineon.com/assets/row/public/documents/24/50/infineon-power-coolmos-cfd7-mosfet-650v-spice-simulationmodels-en.zip
echo '5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d  vendor/cfd7-650.zip' | shasum -a 256 -c -
unzip -p vendor/cfd7-650.zip IFX_CFD7_650V.lib > vendor/IFX_CFD7_650V.lib
echo '02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b  vendor/IFX_CFD7_650V.lib' | shasum -a 256 -c -
