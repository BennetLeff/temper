#!/usr/bin/env bash
# Pre-mortem: compile+link the frozen firmware copy (scratch) with the n21 hardware binding on. Does not touch the export.
set -uo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
. "$HOME/esp/esp-idf-v5.3.6/export.sh" >/dev/null 2>&1
cd "$S/fw"
printf '# Evidence build only\nCONFIG_TEMPER_POWER_HW_BINDING=y\n' > "$S/sdkconfig.premortem"
export SDKCONFIG_DEFAULTS="sdkconfig.defaults;$S/sdkconfig.premortem"
B="$S/fwbuild"; rm -rf "$B"; mkdir -p "$B"
idf.py -B "$B" -DSDKCONFIG="$B/sdkconfig" set-target esp32s3 > "$S/idf-set-target.log" 2>&1; echo "set-target rc $?"
idf.py -B "$B" -DSDKCONFIG="$B/sdkconfig" build > "$S/idf-build.log" 2>&1; RC=$?
echo "build rc $RC"
ls -l "$B"/*.bin 2>/dev/null | awk '{print $5, $9}'
grep -E "^CONFIG_(ESP_CONSOLE|ESPTOOLPY_FLASH|TEMPER_POWER|ESP_BROWNOUT_DET_LVL|PARTITION_TABLE_CUSTOM|ESP_TASK_WDT|SPIRAM|ESP_CONSOLE_UART)" "$B/sdkconfig" | head -40 > "$S/idf-sdkconfig-excerpt.txt"
grep -cE "warning:" "$S/idf-build.log" | sed 's/^/warnings: /'
grep -E "error|Error" "$S/idf-build.log" | head -20
rm -rf "$B"
echo done
