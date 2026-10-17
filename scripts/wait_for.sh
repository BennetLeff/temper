#!/bin/sh
# Wait for another process to finish without matching yourself.
#   sh scripts/wait_for.sh [--timeout S] [--interval S] pid PID
#   sh scripts/wait_for.sh [--timeout S] [--interval S] pattern 'chain.sh native21s43'
# Exit 0 once PID is gone / no other process matches PATTERN (pgrep -f), 124 on timeout (the matches left go to
# stderr), 2 on bad usage. --timeout 0 (the default) waits without limit; --interval defaults to 10 s.
#
# Why: `until ! pgrep -f PAT; do sleep N; done` runs as one `sh -c '...'` whose own argv holds PAT. Linux pgrep
# (procps) skips only itself, so the loop finds its own shell and never ends. macOS pgrep skips its ancestors, but two
# such loops on one job (a wait the tool timeout moved to the background, then the agent's retry) each find the other
# and wait forever after the job ends (reproduced 2026-10-15). Agent transcripts held 175 `pgrep -f` poll loops, 15
# agent-hours. This script skips its own PID, every ancestor's (the agent's shell), and any other wait_for.sh.
set -u
timeout=0 interval=10
while [ $# -gt 0 ]; do
  case $1 in
    --timeout) timeout=$2; shift 2 ;;
    --interval) interval=$2; shift 2 ;;
    *) break ;;
  esac
done
mode=${1:-} target=${2:-}
if [ -z "$mode" ] || [ -z "$target" ]; then
  echo "usage: sh scripts/wait_for.sh [--timeout S] [--interval S] pid PID | pattern PATTERN" >&2
  exit 2
fi
skip=" "
p=$$
while [ -n "$p" ] && [ "$p" -gt 1 ] 2>/dev/null; do
  skip="$skip$p "
  p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
done
others() {
  for q in $(pgrep -f -- "$target" 2>/dev/null); do
    case $skip in *" $q "*) continue ;; esac
    cmd=$(ps -o command= -p "$q" 2>/dev/null) || continue
    case $cmd in *wait_for.sh*) continue ;; esac
    echo "$q $cmd"
  done
}
start=$(date +%s)
while :; do
  case $mode in
    pid) # an exited child its parent has not reaped yet (a zombie) still answers kill -0
         kill -0 "$target" 2>/dev/null || exit 0
         case $(ps -o stat= -p "$target" 2>/dev/null) in *Z*) exit 0 ;; esac ;;
    pattern) [ -z "$(others)" ] && exit 0 ;;
    *) echo "wait_for: mode must be pid or pattern, not '$mode'" >&2; exit 2 ;;
  esac
  if [ "$timeout" -gt 0 ] && [ $(( $(date +%s) - start )) -ge "$timeout" ]; then
    echo "wait_for: still running after ${timeout} s:" >&2
    if [ "$mode" = pid ]; then echo "pid $target" >&2; else others >&2; fi
    exit 124
  fi
  sleep "$interval"
done
