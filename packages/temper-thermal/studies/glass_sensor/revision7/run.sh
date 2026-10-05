#!/bin/sh
set -eu
cd "$(dirname "$0")"
rm -f source-provenance.json
case "${1:-}" in
    --rebuild-cad) ./mechanical/run.sh; ./fixture/build.sh ;;
    '') (cd mechanical && shasum -a 256 -c inputs.sha256)
        (cd fixture && shasum -a 256 -c results/cad-inputs.sha256) ;;
    *) echo 'usage: ./run.sh [--rebuild-cad]' >&2; exit 1 ;;
esac
./fixture/integrate.sh
./thermal/run.sh
./thermal/check_runner.sh
./fixture/run.sh
./fixture/check.sh
./calibration/run.sh
python3 build_report.py
python3 provenance.py write
python3 provenance.py verify
