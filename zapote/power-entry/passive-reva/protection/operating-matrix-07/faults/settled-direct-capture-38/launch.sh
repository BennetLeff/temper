#!/bin/bash
set -u
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07 || exit 2
run_root="$PWD/faults/settled-direct-capture-38"
set -C
exec 3> "$run_root/launch-start.txt" || exit 2
date -u '+%Y-%m-%dT%H:%M:%SZ' >&3
exec 3>&-
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
/private/tmp/matrix07-fault-runner29-parent \
 "$run_root/F2-CREST" \
 /private/tmp/matrix07-direct-fault37-parent \
 /opt/homebrew/bin/pigz \
 /private/tmp/matrix07-fault-native-decoder-parent \
 /private/tmp/matrix07-fault-adapter-parent \
 /private/tmp/matrix07-fault-validation22-parent \
 .662 f2-crest .6541666666667 .002 .6541666666667 .002 .000002 .000000025 3600 900 \
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
