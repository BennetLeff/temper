#!/bin/bash
# SW-SHORT launch packet. Preparation only; parent must explicitly launch.
set -u
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07 || exit 2
run_root="$PWD/faults/settled-sw-short-59"
src="$PWD/faults/settled-compact-prep-24/prepared/SW-SHORT"
out="$run_root/full-SW-SHORT"
required_kib=$((16*1024*1024)) # 10 GiB runtime floor + 6 GiB archive reserve

[ -d "$src" ] || { echo "prepared SW-SHORT source is missing" >&2; exit 77; }
[ ! -e "$out" ] || { echo "refusing existing SW-SHORT output" >&2; exit 77; }

check_space() {
  local available_kib
  available_kib=$(df -Pk "$PWD" | awk 'NR==2 {print $4}') || return 77
  case "$available_kib" in ''|*[!0-9]*) echo "free-space gate is not numeric" >&2; return 77;; esac
  if [ "$available_kib" -lt "$required_kib" ]; then
    echo "free-space gate failed: ${available_kib} KiB < ${required_kib} KiB (16 GiB)" >&2
    return 77
  fi
}

check_solver_inventory() {
  local rows inventory
  command -v ps >/dev/null 2>&1 && command -v awk >/dev/null 2>&1 || return 77
  inventory=$(ps -axo pid=,comm= 2>/dev/null) || return 77
  [ -n "$inventory" ] || { echo "empty full-solver inventory" >&2; return 77; }
  rows=$(printf '%s\n' "$inventory" | awk '
    $2 ~ /(^|\/)ngspice$/ ||
    $2 ~ /(^|\/)matrix07-direct-normal37-parent$/ ||
    $2 ~ /(^|\/)matrix07-direct-fault37-parent$/ ||
    $2 ~ /(^|\/)matrix07-fault-native-host-parent$/ ||
    $2 ~ /(^|\/)matrix07-fault-runner45-parent$/ ||
    $2 ~ /(^|\/)matrix07-line-load-native-runner27-parent$/ { print }')
  if [ -n "$rows" ]; then echo "known full solver/campaign runner is live" >&2; printf '%s\n' "$rows" >&2; return 77; fi
}

verify_source() {
  local name expected actual
  for name in case.cir manifest.json cold.cir ucc28180-pwm-latch.inc protection.inc standby.inc clamp.inc authored_logic_hysteretic.inc; do
    case "$name" in
      case.cir) expected=3ba13389962a9550edcc7ca5486109f4793c6082e94a50fe18f0bc1f6f889ace;;
      manifest.json) expected=840b9fbbf83bc91a8138bfd18101b55306146e21445968ccbbaa3864068679ad;;
      cold.cir) expected=db9d544938b792aac009c1ee4fcf27f52a8283beb167e40262d495d4c098ac94;;
      ucc28180-pwm-latch.inc) expected=2e885755aad4d03fb9c06d7c556faf23ad0ae7922f581d56752db78933b97251;;
      protection.inc) expected=61385002bc7c55313814b7ea606c1198129da20a1f76cd44fe197de0468a70e8;;
      standby.inc) expected=94d995d17a85ef932fe511bb2adbee02a1cd3fd1c88604b16d6b6929b31a50eb;;
      clamp.inc) expected=96cd8d6bfd3870b22403c39437ef2625f0a930f9e06632adcebbc45b61b9dcde;;
      authored_logic_hysteretic.inc) expected=95ae31864ffa55bf33833849ee38c4654bbdb769c9c52976e25a5b4afb73445b;;
    esac
    actual=$(shasum -a 256 "$src/$name" | awk '{print $1}') || return 77
    [ "$actual" = "$expected" ] || { echo "prepared source hash mismatch: $name" >&2; return 77; }
  done
}

check_space || exit $?
check_solver_inventory || exit $?
verify_source || exit $?
mkdir "$out" || { echo "cannot create fresh SW-SHORT output" >&2; exit 77; }
for f in case.cir manifest.json cold.cir ucc28180-pwm-latch.inc protection.inc standby.inc clamp.inc authored_logic_hysteretic.inc; do
  cp -p "$src/$f" "$out/$f" || exit 77
done
# Recheck the materialized copy before any solver spawn.
for f in case.cir manifest.json cold.cir ucc28180-pwm-latch.inc protection.inc standby.inc clamp.inc authored_logic_hysteretic.inc; do
  shasum -a 256 "$out/$f" | awk '{print $1}' | grep -Fxq "$(shasum -a 256 "$src/$f" | awk '{print $1}')" || exit 77
done
check_space || exit $?
check_solver_inventory || exit $?
shasum -a 256 -c "$run_root/tools-parent.sha256" || exit 77

set -C
exec 3> "$run_root/launch-start.txt" || exit 2
date -u '+%Y-%m-%dT%H:%M:%SZ' >&3
exec 3>&-
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
/private/tmp/matrix07-fault-runner45-parent \
 "$out" /private/tmp/matrix07-direct-fault37-parent /opt/homebrew/bin/pigz \
 /private/tmp/matrix07-fault-native-decoder-parent /private/tmp/matrix07-fault-adapter-parent \
 /private/tmp/matrix07-fault-validation22-parent .662 switch-short .6541666666667 .002 \
 .6541666666667 .002 .000002 .000000025 3600 900 \
 > "$run_root/runner.stdout" 2> "$run_root/runner.stderr" &
runner_pid=$!
printf '%s\n' "$runner_pid" > "$run_root/runner.pid"
bash host/resource-monitor-37.sh "$runner_pid" "$run_root/resource-samples.txt" 6000 &
monitor_pid=$!
printf '%s\n' "$monitor_pid" > "$run_root/monitor.pid"
wait "$runner_pid"; runner_rc=$?
printf '%s\n' "$runner_rc" > "$run_root/runner.exit"
wait "$monitor_pid"; monitor_rc=$?
printf 'runner_rc=%s monitor_rc=%s\n' "$runner_rc" "$monitor_rc"
exit "$runner_rc"
