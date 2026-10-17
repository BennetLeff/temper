#!/bin/zsh
# Download and verify the vendor SPICE models into models/vendor/ (not committed:
# vendor licence terms). Re-run is safe. Stops on any hash mismatch.
set -e
cd "$(dirname "$0")"
mkdir -p vendor
URL=https://www.infineon.com/assets/row/public/documents/24/50/infineon-power-coolmos-cfd7-mosfet-650v-spice-simulationmodels-en.zip
ZIP_SHA=5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d
LIB_SHA=02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b
curl -sL -A "Mozilla/5.0" -o vendor/cfd7-650.zip "$URL"
echo "$ZIP_SHA  vendor/cfd7-650.zip" | shasum -a 256 -c -
(cd vendor && unzip -o -q cfd7-650.zip)
echo "$LIB_SHA  vendor/IFX_CFD7_650V.lib" | shasum -a 256 -c -
echo "OK: vendor/IFX_CFD7_650V.lib (subcircuits IPW65R018CFD7_L0/L1/L3; pin order drain gate source)"
