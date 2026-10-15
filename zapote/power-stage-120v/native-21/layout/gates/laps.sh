# Step timing for the native-21 loop scripts (sourced, POSIX sh). Summarise with gates/laps.py.
#   . "$G/laps.sh"; laps_init SCRIPT LOGFILE
#   some step; lap NAME          # NAME's wall time = since the previous lap (or laps_init)
# Each lap appends one JSON line to LOGFILE: {"script", "run", "root", "step", "s", "end"}. A `( ... ) &` block
# inherits the clock at its fork; set LAPS_SCRIPT=chain/fit inside it so its laps sum to the block's own wall time.
# root is the outermost run (chain or passes), exported so incr_iter / regate laps group under it.
# Laps never wrap a command and never fail the caller (set -e / pipefail behave as without them). LAPS=0 disables.
laps_clock() { perl -MTime::HiRes=time -e 'printf "%.3f %.3f\n", time, time - $ARGV[0]' "${1:-0}" 2>/dev/null || echo "$(date +%s) 0"; }
laps_init() {
  [ "${LAPS:-}" = 0 ] && return 0
  LAPS_SCRIPT=$1; LAPS=$2
  case $LAPS in /*) ;; *) LAPS=$PWD/$LAPS;; esac
  mkdir -p "$(dirname "$LAPS")" 2>/dev/null || true
  # shellcheck disable=SC2046  # split "now delta" on purpose
  set -- $(laps_clock); LAPS_T=$1
  LAPS_RUN=$LAPS_SCRIPT-$$-${1%.*}; LAPS_ROOT=${LAPS_ROOT:-$LAPS_RUN}; export LAPS_ROOT
}
lap() {
  [ -n "${LAPS_T:-}" ] || return 0
  # shellcheck disable=SC2046
  set -- "$1" $(laps_clock "$LAPS_T")
  printf '{"script": "%s", "run": "%s", "root": "%s", "step": "%s", "s": %s, "end": %s}\n' \
    "$LAPS_SCRIPT" "$LAPS_RUN" "$LAPS_ROOT" "$1" "$3" "$2" >> "$LAPS" 2>/dev/null || true
  LAPS_T=$2
}
