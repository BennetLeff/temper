#!/bin/bash
# F2-ZERO launch wrapper.  Preparation only: the parent must run this after
# the storage and single-full-solver gates pass in the host environment.
set -u
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07 || exit 2
run_root="$PWD/faults/settled-direct-capture-51"
src="$PWD/faults/settled-compact-prep-24/prepared/F2-ZERO"
out="$run_root/full-F2-ZERO"
required_kib=$((16*1024*1024)) # 10 GiB runtime floor + 6 GiB archive reserve

if [ ! -d "$src" ]; then echo "prepared F2-ZERO source is missing" >&2; exit 77; fi
if [ -e "$out" ]; then echo "refusing existing F2-ZERO output" >&2; exit 77; fi

check_space() {
  local available_kib
  if ! available_kib=$(df -Pk "$PWD" | awk 'NR==2 {print $4}'); then
    echo "unable to read free-space gate" >&2; return 77
  fi
  case "$available_kib" in ''|*[!0-9]*) echo "free-space gate is not numeric" >&2; return 77;; esac
  if [ "$available_kib" -lt "$required_kib" ]; then
    echo "free-space gate failed: ${available_kib} KiB < ${required_kib} KiB (16 GiB)" >&2
    return 77
  fi
  return 0
}

check_solver_inventory() {
  local process_inventory solver_rows
  if ! command -v ps >/dev/null 2>&1 || ! command -v awk >/dev/null 2>&1; then
    echo "ps/awk unavailable; refusing full-solver launch" >&2; return 77
  fi
  if ! process_inventory=$(ps -axo pid=,comm= 2>/dev/null); then
    echo "cannot inspect full-solver process inventory" >&2; return 77
  fi
  if [ -z "$process_inventory" ]; then
    echo "empty full-solver process inventory; refusing launch" >&2; return 77
  fi
  if ! solver_rows=$(printf '%s\n' "$process_inventory" | awk '
    $2 ~ /(^|\/)ngspice$/ ||
    $2 ~ /(^|\/)matrix07-direct-normal37-parent$/ ||
    $2 ~ /(^|\/)matrix07-direct-fault37-parent$/ ||
    $2 ~ /(^|\/)matrix07-fault-native-host-parent$/ ||
    $2 ~ /(^|\/)matrix07-fault-runner45-parent$/ ||
    $2 ~ /(^|\/)matrix07-line-load-native-runner27-parent$/ { print }
  '); then
    echo "cannot filter full-solver process inventory" >&2; return 77
  fi
  if [ -n "$solver_rows" ]; then
    echo "a known full solver/campaign runner is live; refusing F2-ZERO:" >&2
    printf '%s\n' "$solver_rows" >&2
    return 77
  fi
  return 0
}

# Bind the prepared source before materializing a fresh writable output.  These
# are the exact hashes recorded in source-tool-binding.json; no source is edited.
verify_source() {
  local name expected actual
  for name in \
    case.cir manifest.json cold.cir ucc28180-pwm-latch.inc protection.inc \
    standby.inc clamp.inc authored_logic_hysteretic.inc; do
    case "$name" in
      case.cir) expected=b704ebd646dce1da7cf03518478ac1956e3a0bffbae804bd28ff383f4a6fb6c1 ;;
      manifest.json) expected=c569392b818e638c59b4787353803c094ae552cbd1409b08e184da6eacf8c3a6 ;;
      cold.cir) expected=db9d544938b792aac009c1ee4fcf27f52a8283beb167e40262d495d4c098ac94 ;;
      ucc28180-pwm-latch.inc) expected=2e885755aad4d03fb9c06d7c556faf23ad0ae7922f581d56752db78933b97251 ;;
      protection.inc) expected=61385002bc7c55313814b7ea606c1198129da20a1f76cd44fe197de0468a70e8 ;;
      standby.inc) expected=94d995d17a85ef932fe511bb2adbee02a1cd3fd1c88604b16d6b6929b31a50eb ;;
      clamp.inc) expected=96cd8d6bfd3870b22403c39437ef2625f0a930f9e06632adcebbc45b61b9dcde ;;
      authored_logic_hysteretic.inc) expected=95ae31864ffa55bf33833849ee38c4654bbdb769c9c52976e25a5b4afb73445b ;;
    esac
    if ! actual=$(shasum -a 256 "$src/$name" | awk '{print $1}'); then
      echo "cannot hash prepared source $name" >&2; return 77
    fi
    if [ "$actual" != "$expected" ]; then
      echo "prepared source hash mismatch: $name" >&2; return 77
    fi
  done
  return 0
}

# Gate before the copy and once more immediately before any solver spawn.
check_space || exit $?
check_solver_inventory || exit $?
verify_source || exit $?
if ! mkdir "$out"; then echo "cannot create fresh F2-ZERO output" >&2; exit 77; fi
for source_file in case.cir manifest.json cold.cir ucc28180-pwm-latch.inc protection.inc standby.inc clamp.inc authored_logic_hysteretic.inc; do
  if ! cp -p "$src/$source_file" "$out/$source_file"; then
    echo "source materialization failed: $source_file" >&2; exit 77
  fi
done
check_space || exit $?
check_solver_inventory || exit $?
shasum -a 256 -c "$run_root/tools-parent.sha256" || exit 77

# Noclobber makes a second invocation fail rather than overwrite launch evidence.
set -C
exec 3> "$run_root/launch-start.txt" || exit 2
date -u '+%Y-%m-%dT%H:%M:%SZ' >&3 || exit 2
exec 3>&-
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
/private/tmp/matrix07-fault-runner45-parent \
 "$out" \
 /private/tmp/matrix07-direct-fault37-parent \
 /opt/homebrew/bin/pigz \
 /private/tmp/matrix07-fault-native-decoder-parent \
 /private/tmp/matrix07-fault-adapter-parent \
 /private/tmp/matrix07-fault-validation22-parent \
 .682 f2-zero .6583333333333 .010 .6583333333333 .010 .000002 .000000025 3600 900 \
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
