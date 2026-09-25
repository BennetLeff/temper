#!/bin/bash
# Read-only samples of a campaign runner and its descendants. No process control.
# Run with the same process-inspection permission as the authorized runner.
set -u
if [ "$#" -ne 3 ]; then
  echo 'usage: resource-monitor-37.sh RUNNER_PID NEW_LOG MAX_SECONDS' >&2
  exit 2
fi
runner_pid=$1
monitor_log=$2
monitor_limit=$3
case "$runner_pid:$monitor_limit" in
  *[!0-9:]*|:*|*:) echo 'PID and deadline must be positive integers' >&2; exit 2;;
esac
if [ "$runner_pid" -le 0 ] || [ "$monitor_limit" -le 0 ]; then exit 2; fi
set -C
exec 3> "$monitor_log" || exit 2
monitor_started=$SECONDS
while :; do
  printf 'sample_utc=%s elapsed_s=%s runner_pid=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$((SECONDS-monitor_started))" "$runner_pid" >&3
  df -k . >&3 2>&3 || { echo 'monitor_error=df' >&3; exit 1; }
  /usr/sbin/sysctl vm.swapusage >&3 2>&3 || { echo 'monitor_error=swap' >&3; exit 1; }
  process_rows=$(/bin/ps -axo pid=,ppid=,rss=,pcpu=) || { echo 'monitor_error=ps' >&3; exit 1; }
  printf '%s\n' "$process_rows" | awk -v root="$runner_pid" '
    { p[NR]=$1; parent[NR]=$2; row[NR]=$0 }
    END {
      owned[root]=1
      for (pass=1; pass<=NR; pass++) {
        added=0
        for (i=1; i<=NR; i++) if (owned[parent[i]] && !owned[p[i]]) { owned[p[i]]=1; added=1 }
        if (!added) break
      }
      print "owned_process_columns=pid,ppid,rss_kib,pcpu"
      total=0; alive=0
      for (i=1; i<=NR; i++) if (owned[p[i]]) { print row[i]; split(row[i], f); total+=f[3]; if (p[i]==root) alive=1 }
      print "owned_rss_sum_kib=" total " runner_present=" alive
    }' >&3 || { echo 'monitor_error=filter' >&3; exit 1; }
  # PID existence is observation only; the runner exit status remains authoritative.
  if ! kill -0 "$runner_pid" 2>/dev/null; then echo 'monitor_stop=runner_absent' >&3; exit 0; fi
  if [ "$((SECONDS-monitor_started))" -ge "$monitor_limit" ]; then
    echo 'monitor_stop=observation_deadline_no_process_action' >&3
    exit 0
  fi
  sleep 5
done
