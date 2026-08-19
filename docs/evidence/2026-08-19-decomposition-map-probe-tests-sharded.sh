#!/bin/bash
# Serial pytest per top-level test directory, shards in parallel, one coverage
# file each, combined afterwards. Avoids the pytest-xdist collection race
# ("Different tests were collected between gw0 and gwN") seen on this tree,
# without deselecting a single test.
cd /home/bennet/Desktop/temper
D="${DECOMP_WORKDIR:-/tmp/decomp-map}"
mkdir -p "$D/shards"; rm -f "$D/shards"/* "$D"/cov/.coverage.tests*
J=6
run_shard () {
  local name=$1; shift
  COVERAGE_FILE="$D/shards/.coverage.$name" timeout 10800 \
    uv run --no-sync python -m pytest "$@" -q --no-header -p no:randomly \
    --cov=packages/temper-placer/src --cov=packages/temper-workflow/src \
    --cov-report= --cov-branch > "$D/shards/$name.log" 2>&1
  echo "$name exit=$? :: $(grep -oE '[0-9]+ (passed|failed|error)[^,]*' "$D/shards/$name.log" | tr '\n' ' ')"
}
export -f run_shard; export D
SHARDS=""
for d in packages/temper-placer/tests/*/; do
  n=$(basename "$d"); SHARDS="$SHARDS $n:$d"
done
SHARDS="$SHARDS toplevel:@TOP elec:elec/validation wf:packages/temper-workflow/tests"
i=0
for s in $SHARDS; do
  name=${s%%:*}; path=${s#*:}
  if [ "$path" = "@TOP" ]; then
    files=$(ls packages/temper-placer/tests/*.py 2>/dev/null | tr '\n' ' ')
    [ -z "$files" ] && continue
    run_shard "$name" $files &
  else
    run_shard "$name" "$path" &
  fi
  i=$((i+1))
  if [ $((i % J)) -eq 0 ]; then wait; fi
done
wait
echo "=== combining ==="
cd "$D/shards" && COVERAGE_FILE="$D/cov/.coverage.tests" /home/bennet/Desktop/temper/.venv/bin/python -m coverage combine --keep $(ls .coverage.* | tr '\n' ' ')
echo "combined -> $(ls -la $D/cov/.coverage.tests 2>&1)"
echo "=== shard results ==="
for f in "$D/shards"/*.log; do echo "$(basename $f .log): $(tail -3 $f | grep -oE '[0-9]+ (passed|failed|error|skipped)[^,]*' | tr '\n' ' ')"; done
