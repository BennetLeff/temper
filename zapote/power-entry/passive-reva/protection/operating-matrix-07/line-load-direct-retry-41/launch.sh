#!/bin/bash
set -u
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07 || exit 2
run_root="$PWD/line-load-direct-retry-41"
set -C
exec 3> "$run_root/launch-start.txt" || exit 2
date -u '+%Y-%m-%dT%H:%M:%SZ' >&3
exec 3>&-
/private/tmp/matrix07-line-load-native-runner27-parent \
 --source "$PWD/accepted-baseline-11" \
 --baseline "$PWD/accepted-baseline-11/acceptance.json" \
 --manifest "$PWD/line-load-prep/manifest.json" \
 --output "$run_root/full-LL08" \
 --tracked /private/tmp/matrix07-direct-normal37-parent \
 --normalize /private/tmp/matrix07-normalize \
 --checker /private/tmp/matrix07-checker \
 --decoder /private/tmp/matrix07-native-stream-host \
 --event-metrics /private/tmp/matrix07-event-metrics-host \
 --event-audit /private/tmp/matrix07-normal15-event-audit-host \
 --spice-scripts /opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
 --pigz /opt/homebrew/bin/pigz \
 --workers 1 --wall-limit 3600 --end-s .65 \
 --first-invalid-snapshot --cases LL08 \
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
