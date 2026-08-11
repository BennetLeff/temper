#!/usr/bin/env bash
# U6 sustained-agreement campaign, for any tier.
#
#   tools/wasm/u6_campaign.sh <crate> [commits] [outdir]
#
# Protocol: docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md §U6, and the
# temper-drc-rs precedent in docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md.
# N consecutive origin/main commits; each built for wasm32 AND run natively; the
# per-test verdicts compared. 100% agreement across all N is the R19 bar that
# R24 licenses a crate's `cargo test` step leaving GitHub Actions on.
#
# Everything crate-specific -- cargo features, native args, the expected-failure
# manifest -- is READ FROM tools/wasm/wasm_tier_topology.json. Nothing here is
# per-crate, so adding a tier to the topology makes it runnable here for free,
# the same property #940/#943/#956 gave the other four consumers.
#
# READ THE SCOPE LINE, NOT ONLY THE AGREEMENT LINE. `agreement_rate: 1.0` means
# every test present on BOTH sides agreed. `native_only` counts tests with no
# wasm32 counterpart -- they cannot disagree because they are not there. A crate
# at 1.0 with a large native_only has NOT proved its native `cargo test` step is
# redundant; it has proved the intersection agrees. That distinction is the
# whole difference between "narrow the step" and "delete the step".
set -uo pipefail

CRATE="${1:?usage: u6_campaign.sh <crate> [commits] [outdir]}"
NCOMMITS="${2:-10}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${3:-/tmp/u6-$CRATE}"
WT="$REPO/.claude/worktrees/u6-$CRATE"

# r19_compare.py imports datetime.UTC -> needs CPython >= 3.11. A conda python3
# on PATH is often 3.9 and fails at import, so resolve an interpreter that works
# rather than trusting `python3`.
PY=""
for cand in /usr/bin/python3 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'from datetime import UTC' 2>/dev/null; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "no CPython >= 3.11 found (r19_compare.py needs datetime.UTC)"; exit 2; }

# One target dir per crate: parallel campaigns must not share one, or they
# serialize on cargo's build lock and lose the parallelism they were fanned out for.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/tmp/u6-target-$CRATE}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:/home/bennet/miniconda3/lib"

read -r FEATURE EXPECTED NATIVE_ARGS < <("$PY" - "$CRATE" <<'PY'
import json, sys
crate = sys.argv[1]
topo = json.load(open('tools/wasm/wasm_tier_topology.json'))
tier = next((t for t in topo['tiers'] if t['crate'] == crate), None)
if tier is None:
    sys.exit(f"{crate} is not a tier in wasm_tier_topology.json")
# The full-corpus feature for this tier is its single shard's, or the tier's own.
feat = tier.get('cargo_features') or tier['shards'][0]['cargo_features']
print(feat, tier['expected_failures'], ' '.join(tier['native_test_args']))
PY
) || exit 2

mkdir -p "$OUT"
cd "$REPO"
cp tools/wasm/r19_compare.py "$OUT/r19_compare.py"
cp "$EXPECTED" "$OUT/expected.json"
RUNNER="$REPO/tools/wasm/run_wasm_tests.mjs"   # run IN PLACE: it resolves its
# default expected-failures manifest relative to its own path, so a copy
# elsewhere looks for a sibling that is not there and exits 2.

echo "crate=$CRATE feature=$FEATURE expected=$EXPECTED"
echo "native args: $NATIVE_ARGS"
mapfile -t COMMITS < <(git rev-list origin/main -"$NCOMMITS")
git worktree add -f --detach "$WT" "${COMMITS[0]}" >/dev/null 2>&1

pass=0; fail=0
for c in "${COMMITS[@]}"; do
  cd "$WT" || exit 1
  git checkout -q --detach "$c" 2>/dev/null || { echo "$c  CHECKOUT-FAILED"; fail=$((fail+1)); continue; }

  # --manifest-path, NOT `-p`: this repo has NO root Cargo.toml (it is not a
  # cargo workspace), so `-p temper-wasm-test-runner` fails from the repo root
  # with "could not find Cargo.toml in <root> or any parent directory".
  if ! cargo build -q --release --target wasm32-unknown-unknown \
        --manifest-path packages/temper-wasm-test-runner/Cargo.toml \
        --no-default-features --features "$FEATURE" >"$OUT/build_$c.log" 2>&1; then
    echo "$c  WASM-BUILD-FAILED ($OUT/build_$c.log)"; fail=$((fail+1)); continue
  fi
  WASM="$CARGO_TARGET_DIR/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm"
  if ! node "$RUNNER" "$WASM" --json "$OUT/wasm_$c.json" \
        --expected-failures "$OUT/expected.json" >"$OUT/wasmrun_$c.log" 2>&1; then
    echo "$c  WASM-RUN-FAILED ($OUT/wasmrun_$c.log)"; fail=$((fail+1)); continue
  fi

  # shellcheck disable=SC2086  # NATIVE_ARGS is a deliberate word-split arg list
  cargo test $NATIVE_ARGS >"$OUT/native_$c.txt" 2>&1

  if "$PY" "$OUT/r19_compare.py" --native-file "$OUT/native_$c.txt" \
        --wasm-json "$OUT/wasm_$c.json" --expected-failures "$OUT/expected.json" \
        --commit "$c" --output "$OUT/r19_$c.json" --fail-on-disagree \
        >"$OUT/cmp_$c.log" 2>&1; then
    echo "$c  AGREE   $("$PY" -c "
import json;c=json.load(open('$OUT/r19_$c.json')).get('comparison',{})
print('rate=%s in_both=%s native_only=%s wasm32_only=%s' % (c.get('agreement_rate'),c.get('total_in_both'),c.get('native_only'),c.get('wasm32_only')))")"
    pass=$((pass+1))
  else
    echo "$c  DISAGREE ($OUT/cmp_$c.log)"; sed -n '/DISAGREEMENTS/,$p' "$OUT/cmp_$c.log" | head -12
    fail=$((fail+1))
  fi
done

echo "============================================="
echo "U6 $CRATE: $pass/$NCOMMITS at full agreement, $fail failed"
if [ "$pass" -eq "$NCOMMITS" ]; then
  echo "VERDICT: R19 sustained agreement MET ($pass/$NCOMMITS) -- for the INTERSECTION."
  "$PY" -c "
import json;c=json.load(open('$OUT/r19_${COMMITS[0]}.json')).get('comparison',{})
n=c.get('native_only',0)
print('  in both: %s | native-only: %s  <- these are NOT covered by the tier' % (c.get('total_in_both'),n))
print('  ' + ('native_only is 0: the tier covers this crate.' if n==0 else
      'native_only is %d: triage each before claiming the native step is redundant.' % n))"
else
  echo "VERDICT: NOT MET"
fi
