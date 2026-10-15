#!/bin/sh
# Rerun the coupling audit end to end (read-only on every input; writes results/ only), then rerun it and check
# that every results/*.json is byte-identical (determinism control; exit 1 otherwise).
#   sh validation-results/13-coupling/scripts/run_all.sh
set -e
set -o pipefail
S=$(cd "$(dirname "$0")" && pwd)
R=$S/../results
run() {
  python3 -I $S/assign32.py
  python3 -I $S/electrical.py
  python3 -I $S/physical.py
  python3 -I $S/physics.py
  python3 -I $S/verification.py
  python3 -I $S/history.py
  python3 -I $S/combine.py
  python3 -I $S/contracts.py
  python3 -I $S/regroup.py make
  for a in islands islands_selv; do
    python3 -I $S/electrical.py --alt $a
    python3 -I $S/physical.py --alt $a
  done
  python3 -I $S/regroup.py compare
}
run > "$R/run1.log" 2>&1 || { cat "$R/run1.log"; exit 1; }
H1=$(cd "$R" && shasum -a 256 *.json)
run > "$R/run2.log" 2>&1 || { cat "$R/run2.log"; exit 1; }
H2=$(cd "$R" && shasum -a 256 *.json)
rm -f "$R/run2.log"
if [ "$H1" != "$H2" ]; then
  echo "DETERMINISM FAILED"; echo "$H1" > "$R/.h1"; echo "$H2" > "$R/.h2"; diff "$R/.h1" "$R/.h2" || true; rm -f "$R/.h1" "$R/.h2"; exit 1
fi
grep -c "^PASS" "$R/run1.log" | sed 's/^/controls passed: /'
if grep -q "^FAIL" "$R/run1.log"; then echo "CONTROL FAILED"; exit 1; fi
echo "$H1" > "$R/SHA256SUMS"
echo "deterministic: $(echo "$H1" | wc -l | tr -d ' ') result files identical over two runs"
