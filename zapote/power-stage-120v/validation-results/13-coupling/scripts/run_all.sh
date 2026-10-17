#!/bin/sh
# Rerun the coupling audit end to end for one stage (read-only on every input; writes the results directory, and the
# regenerated B3 maps under 13-coupling/cache/), then rerun it and check that every results *.json is byte-identical
# (determinism control; exit 1 otherwise).
#   sh validation-results/13-coupling/scripts/run_all.sh                       # the board of record (stages.LATEST)
#   sh validation-results/13-coupling/scripts/run_all.sh --stage native21s32 --root /tmp/s32/zapote/power-stage-120v
#        (an older stage: export its inputs first with export_stage.sh; results go to results-s32/)
# Stage options (common.init): --stage TAG --root DIR --out DIR --repo DIR --build DIR --b3-dir DIR
# Each step returns from run() on failure: set -e does not act inside a function called on the left of ||.
set -e
set -o pipefail
S=$(cd "$(dirname "$0")" && pwd)
R=$(python3 -I "$S/common.py" "$@")
mkdir -p "$R"
run() {
  python3 -I $S/b3_maps.py "$@" || return 1
  python3 -I $S/assign.py "$@" || return 1
  python3 -I $S/electrical.py "$@" || return 1
  python3 -I $S/physical.py "$@" || return 1
  python3 -I $S/physics.py "$@" || return 1
  python3 -I $S/verification.py "$@" || return 1
  python3 -I $S/history.py "$@" || return 1
  python3 -I $S/combine.py "$@" || return 1
  python3 -I $S/contracts.py "$@" || return 1
  python3 -I $S/regroup.py make "$@" || return 1
  for a in islands islands_selv; do
    python3 -I $S/electrical.py --alt $a "$@" || return 1
    python3 -I $S/physical.py --alt $a "$@" || return 1
  done
  python3 -I $S/regroup.py compare "$@" || return 1
  python3 -I $S/spine.py "$@" || return 1   # skips a stage whose root has no SELV-spine lock (stage 32)
  python3 -I $S/oos.py "$@" || return 1   # skips the stage the frozen model was written on (stage 32)
}
run "$@" > "$R/run1.log" 2>&1 || { cat "$R/run1.log"; exit 1; }
H1=$(cd "$R" && shasum -a 256 *.json)
run "$@" > "$R/run2.log" 2>&1 || { cat "$R/run2.log"; exit 1; }
H2=$(cd "$R" && shasum -a 256 *.json)
rm -f "$R/run2.log"
if [ "$H1" != "$H2" ]; then
  echo "DETERMINISM FAILED"; echo "$H1" > "$R/.h1"; echo "$H2" > "$R/.h2"; diff "$R/.h1" "$R/.h2" || true; rm -f "$R/.h1" "$R/.h2"; exit 1
fi
grep -c "^PASS" "$R/run1.log" | sed 's/^/controls passed: /'
if grep -q "^FAIL" "$R/run1.log"; then echo "CONTROL FAILED"; exit 1; fi
echo "$H1" > "$R/SHA256SUMS"
echo "deterministic: $(echo "$H1" | wc -l | tr -d ' ') result files identical over two runs"
