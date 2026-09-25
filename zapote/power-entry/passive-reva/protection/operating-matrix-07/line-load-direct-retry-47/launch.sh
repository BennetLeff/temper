#!/bin/bash
set -u
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07 || exit 2
run_root="$PWD/line-load-direct-retry-47"
out="$run_root/full-LL09"
test ! -e "$out" || { echo "refusing existing LL09 output" >&2; exit 77; }
# 2.2 GiB prospective archive + 10 GiB floor, rounded up in KiB. Existing
# archives are already reflected in df and must not be subtracted twice.
required_kib=$((122*1024*1024/10+1))
available_kib=$(df -Pk "$PWD" | awk 'NR==2 {print $4}')
case "$available_kib" in ''|*[!0-9]*) echo "unable to read free-space gate" >&2; exit 77;; esac
if [ "$available_kib" -lt "$required_kib" ]; then
  echo "free-space gate failed: ${available_kib} KiB < ${required_kib} KiB" >&2
  exit 77
fi
# Rust hosts may link libngspice while their process name is the host binary,
# so pgrep -x ngspice is insufficient. The approved host must provide a
# command-name inventory. This bounded guard knows only the full-solver names;
# read-only analyzers and this launch wrapper are intentionally not blocked.
if ! command -v ps >/dev/null 2>&1 || ! command -v awk >/dev/null 2>&1; then echo "ps/awk unavailable; refusing solver launch" >&2; exit 77; fi
if ! process_inventory=$(ps -axo pid=,comm= 2>/dev/null); then
  echo "cannot inspect full-solver process inventory" >&2
  exit 77
fi
if [ -z "$process_inventory" ]; then echo "empty process inventory; refusing launch" >&2; exit 77; fi
if ! solver_rows=$(printf '%s\n' "$process_inventory" | awk '$2 ~ /(^|\/)ngspice$/ || $2 ~ /(^|\/)matrix07-direct-normal37-parent$/ || $2 ~ /(^|\/)matrix07-direct-fault37-parent$/ {print}'); then echo "cannot filter solver process inventory" >&2; exit 77; fi
if [ -n "$solver_rows" ]; then
  echo "full solver already live; refusing launch:" >&2
  printf '%s\n' "$solver_rows" >&2
  exit 77
fi
set -C
exec 3> "$run_root/launch-start.txt" || exit 2
date -u '+%Y-%m-%dT%H:%M:%SZ' >&3 || exit 2
exec 3>&-
/private/tmp/matrix07-line-load-native-runner27-parent \
 --source "$PWD/accepted-baseline-11" \
 --baseline "$PWD/accepted-baseline-11/acceptance.json" \
 --manifest "$PWD/line-load-prep/manifest.json" \
 --output "$run_root/full-LL09" \
 --tracked /private/tmp/matrix07-direct-normal37-parent \
 --normalize /private/tmp/matrix07-normalize \
 --checker /private/tmp/matrix07-checker \
 --decoder /private/tmp/matrix07-native-stream-host \
 --event-metrics /private/tmp/matrix07-event-metrics-host \
 --event-audit /private/tmp/matrix07-normal15-event-audit-host \
 --spice-scripts /opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
 --pigz /opt/homebrew/bin/pigz \
 --workers 1 --wall-limit 3600 --end-s .65 \
 --first-invalid-snapshot --cases LL09 \
 > "$run_root/runner.stdout" 2> "$run_root/runner.stderr" &
runner_pid=$!
printf '%s\n' "$runner_pid" > "$run_root/runner.pid"
bash host/resource-monitor-37.sh "$runner_pid" "$run_root/resource-samples.txt" 6000 &
monitor_pid=$!
printf '%s\n' "$monitor_pid" > "$run_root/monitor.pid"
printf 'runner_pid=%s monitor_pid=%s\n' "$runner_pid" "$monitor_pid"
wait "$runner_pid"
runner_rc=$?
printf '%s\n' "$runner_rc" > "$run_root/runner.exit"
wait "$monitor_pid"
monitor_rc=$?
printf '%s\n' "$monitor_rc" > "$run_root/monitor.exit"
printf 'runner_rc=%s monitor_rc=%s\n' "$runner_rc" "$monitor_rc"
exit "$runner_rc"
