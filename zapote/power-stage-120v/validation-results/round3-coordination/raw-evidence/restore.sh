#!/bin/sh
# Restore the round-3 raw evidence (runs, logs, waveform arrays) into
# zapote/power-stage-120v/validation-results from the GitHub release asset,
# then verify every file against manifest.json. Needs gh and python3.
#   sh zapote/power-stage-120v/validation-results/round3-coordination/raw-evidence/restore.sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)                      # validation-results
. "$HERE/asset.env"                                  # TAG, ASSET, ASSET_SHA256
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
gh release download "$TAG" --repo BennetLeff/temper --pattern "$ASSET" --dir "$TMP"
echo "$ASSET_SHA256  $TMP/$ASSET" | shasum -a 256 -c -
tar -xf "$TMP/$ASSET" -C "$ROOT"
python3 "$HERE/verify.py" "$ROOT"
