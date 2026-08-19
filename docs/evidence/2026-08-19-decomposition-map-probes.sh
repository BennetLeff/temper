#!/bin/bash
# Re-runnable execution-evidence probe set for the decomposition map.
set -u
cd /home/bennet/Desktop/temper
D="${DECOMP_WORKDIR:-/tmp/decomp-map}"
rm -f "$D"/cov/.coverage.*
SRC="--source=packages/temper-placer/src,packages/temper-workflow/src,scripts"

echo "=== PROBE 0: extension symbol freshness ==="
uv run --no-sync python "$D/verify_ext_symbols.py" 2>&1 | tail -15

echo "=== PROBE 1: real production route (scripts/route_board.py) ==="
COVERAGE_FILE=$D/cov/.coverage.route timeout 3000 uv run --no-sync coverage run --branch $SRC --concurrency=thread \
  scripts/route_board.py --pcb pcb/temper.kicad_pcb --output "$D/routed.kicad_pcb" > "$D/probe_route.log" 2>&1
echo "route exit=$? ; $(grep -c . "$D/probe_route.log") log lines"; grep -E "^Result" "$D/probe_route.log" | head -4

echo "=== PROBE 2: full-pipeline closure test (metrics-record.yml CI job) ==="
COVERAGE_FILE=$D/cov/.coverage.closure timeout 3000 uv run --no-sync coverage run --branch $SRC --concurrency=thread \
  scripts/ci_closure_test.py --pcb pcb/temper.kicad_pcb --require-all-stages \
  --output "$D/closure-result.json" --metrics-dir "$D/pipeline-metrics" > "$D/probe_closure.log" 2>&1
echo "closure exit=$?"; tail -3 "$D/probe_closure.log"

echo "=== PROBE 3: golden-board regression (golden-check.yml CI gate) ==="
COVERAGE_FILE=$D/cov/.coverage.regression timeout 3000 uv run --no-sync coverage run --branch $SRC --concurrency=thread \
  -m temper_placer.cli regression > "$D/probe_regression.log" 2>&1
echo "regression exit=$?"; grep -cE "\[SKIP\]|\[PASS\]|\[FAIL\]" "$D/probe_regression.log"

echo "=== PROBE 4: temper-workflow test suite ==="
COVERAGE_FILE=$D/cov/.coverage.tests_wf timeout 900 uv run --no-sync python -m pytest packages/temper-workflow/tests \
  -q --no-header --cov=packages/temper-placer/src --cov=packages/temper-workflow/src --cov-report= --cov-branch \
  -p no:cacheprovider > "$D/probe_tests_wf.log" 2>&1
echo "tests_wf exit=$?"; tail -2 "$D/probe_tests_wf.log"

echo "=== PROBE 5: temper-placer + elec/validation test suite (serial reference run) ==="
COVERAGE_FILE=$D/cov/.coverage.tests timeout 14400 uv run --no-sync python -m pytest packages/temper-placer/tests elec/validation \
  -q --no-header --cov=packages/temper-placer/src --cov=packages/temper-workflow/src --cov-report= --cov-branch \
  -p no:cacheprovider > "$D/probe_tests.log" 2>&1
echo "tests exit=$?"; tail -4 "$D/probe_tests.log"

echo "=== ALL PROBES DONE ==="
ls -la "$D/cov/"
sha256sum pcb/temper.kicad_pcb
