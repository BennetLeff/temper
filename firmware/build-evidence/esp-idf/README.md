# ESP-IDF build evidence (firmware/, ESP32-S3)

Date: 2026-10-12. Branch `build/esp-idf`. Reproduce with `./build.sh` (needs the IDF install below).

## Toolchain

| Item | Value |
|---|---|
| ESP-IDF | **v5.3.6**, tag commit `79e3454c68248bd7d881721c9b2e94561378a8ce` (`~/esp/esp-idf-v5.3.6`, outside the repo) |
| Why 5.3 | `.github/workflows/release-artifacts.yml` builds with `espressif/idf:release-v5.3`; README says "v5.0+". No `idf_component.yml`, `dependencies.lock` or committed `sdkconfig` exist. 5.3.6 is the newest 5.3.x tag. |
| Target | esp32s3 (`idf.py set-target esp32s3`) |
| Compiler | xtensa-esp-elf GCC 13.2.0 (`esp-13.2.0_20250707`), installed by `install.sh esp32s3` |
| Kconfig | `sdkconfig.defaults` + `sdkconfig.evidence` (one line: `CONFIG_TEMPER_POWER_HW_BINDING=y`, so the opt-in `n21_hw_esp32.c` is also compiled; it defaults to `n`) |

## Pass criterion

Clean build: every esp32 glue file compiled AND linked, `idf.py build` exit 0.

## Result

| Stage | Result |
|---|---|
| Configure (`set-target`) | PASS |
| Compile, all 12 glue files + all other firmware sources | **PASS** (0 errors; see `compiled-glue-files.txt`) |
| Link, strict (`build-strict.trimmed.log`) | **FAIL: 26 undefined references**, all to functions with no production implementation (`undefined-symbols.txt`) |
| Link, diagnostic (`build-diag-link.trimmed.log`) | PASS only with `diag_stubs/` (abort() stubs for those 26 symbols). NOT flashable, NOT a pass. |

**Verdict: PARTIAL. All glue compiles; the firmware image does not link.** The strict build fails at
link for a reason that is not a glue bug: `main/state_machine.c`, `main/state_handlers.c` and `main/main.c` call
26 platform functions that exist only as host test doubles in `firmware/test/state_machine_stubs.c`:

`button_is_pressed button_set_enabled buzzer_beep buzzer_beep_continuous buzzer_stop display_show_fault display_show_message display_update_countdown display_update_temperature eeprom_log_fault fan_set_auto_mode fan_set_speed get_time_ms led_set_pattern peripherals_enter_low_power peripherals_exit_low_power peripherals_init read_dc_bus_current read_pan_temperature read_rtd_resistance test_adc_calibration test_display_communication test_eeprom_read test_fan_operation test_hardware_comparators test_rtd_sensor`

Inventing these would mean choosing hardware behaviour (thermistor read path, fan, display, EEPROM, self-tests),
which this task excludes, so they are reported, not fixed. `read_pan_temperature`, `read_rtd_resistance` and
`read_dc_bus_current` feed the safety interlocks in `state_machine.c`, so they matter most for review.

### Size (diagnostic image, `size.txt`, `size-components.txt`)

`induction_cooker.bin` = 380448 bytes (0x5ce20), 82 % of the 2 MB app partition free. Flash code 203264, flash
data 87096, DIRAM 79163 (23 %), IRAM 16383 / 16384 (this is the IDF-reserved non-cache IRAM bank; normal for
esp32s3). Per-archive sizes are in `size-components.txt` (project archives: libpower 23981, libmain 15880
[main + control + safety + config + sensors], libtemper_hal 11083). `libdiag_stubs.a` (234 B) is the diagnostic stubs.
The figures include the 234 B of stubs.

### Proof the glue compiled and linked

- `compiled-glue-files.txt`: entries from `build/compile_commands.json` for every file under `components/*/esp32/`, `main/`
  and `components/power/n21_hw_esp32.c` (12 files, with object paths).
- `linked-glue-objects.txt`: the same 12 objects with their non-zero input-section sizes in the final link map
  (diagnostic image), so they are linked in, not just compiled.

### Warnings from project code (clean full build; IDF's own code produced none that matter)

| File:line | Warning | Action |
|---|---|---|
| components/control/pll_control.c:193, 203 | `pwm_edge_cb`, `zcd_edge_cb` defined but not used | listed: the capture-callback wiring is unfinished, removing it is a control change |
| components/control/pll_control.c:357 | unused variable `abs_error` | listed: in the lock-detection logic, not touched |
| components/hal/esp32/hal_adc_esp32.c:57 | `ADC_ATTEN_DB_11` deprecated in IDF 5.3 (alias of `ADC_ATTEN_DB_12`, same value) | listed: swap is behaviour-neutral but sits in ADC range mapping, left for the owner |
| components/hal/esp32/hal_timer_esp32.c:41 | `s_capture_contexts` unused | listed |
| main/state_handlers.c:21 | `TAG` unused | listed |
| main/state_handlers.c:282 | unused variable `estimation_complete` | listed: thermal-mass estimation result is discarded, possible logic gap |

Configure-time notes (not code warnings): `jinja2` is not in the system Python, so `tools/gen_config.py` and
`tools/gen_transition_table.py` fail and the root CMakeLists falls back to the committed `config.h` /
`transition_table.h` (by design; install jinja2 to exercise the generators). `sdkconfig.defaults:16`
`CONFIG_ESP_TASK_WDT` was renamed in IDF 5.x (`CONFIG_ESP_TASK_WDT_INIT`); IDF maps it, but the file should be updated.

## Source changes (all build/glue; no control logic or thresholds)

| File | Change | Justification |
|---|---|---|
| `components/hal/CMakeLists.txt` -> `components/temper_hal/CMakeLists.txt` (git mv) | Component renamed `hal` -> `temper_hal`; sources/includes still point at `components/hal/` via `../hal`; `components/hal/` now has no CMakeLists.txt | **Root cause of the first failure.** ESP-IDF names components after their directory, so the project `hal` silently replaced IDF's own `hal` component and mbedtls failed with `hal/sha_types.h: No such file`. A directory move was rejected: many hash-pinned evidence files and validators reference `components/hal/...`. |
| same file | `if(CONFIG_IDF_TARGET)` -> `if(ESP_PLATFORM)` (2 places), `HAL_REQUIRES` gains `esp_adc` | `CONFIG_*` is undefined during IDF's early requirement-expansion pass, so REQUIRES came out empty (`driver/gpio.h` not found); `hal_adc_esp32.c` includes `esp_adc/*` |
| `main/CMakeLists.txt` | REQUIRES `hal` -> `temper_hal`; SRCS += `../config.c`, `control/{cascade_pid,low_temp_control,pan_detect,pid_control,pll_control,profiles,thermal_mass,zvs_monitor}.c`, `safety/{safety,adc_guard,coil_guard,fan_guard,ntc_guard,pwm_guard}.c`; INCLUDE_DIRS += `../components/safety/include` | Missing sources: main references `g_config`, `pid_*`, `pll_*`, `profile_*`, `thermal_mass_*`, `watchdog_*`, `trigger_hardware_shutdown` etc. (main.c: "These will be included when components are built") |
| `components/power/CMakeLists.txt` | REQUIRES `hal` -> `temper_hal` | follows the rename |
| `components/webui/CMakeLists.txt` | PRIV_REQUIRES `esp_vfs_fat` -> `fatfs` | `esp_vfs_fat` is not an IDF 5.3 component name (it is `fatfs`); configure error |
| `partitions.csv` (new) | nvs 24K, phy_init 4K, factory 2M, storage 1M @ 4 MB flash | `sdkconfig.defaults` sets `CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"` but the file did not exist (build aborts). Layout is the IDF standard single-app one; no OTA layout was specified anywhere. |
| `components/hal/esp32/hal_gpio_esp32.c` | `#include "esp_attr.h"` | `IRAM_ATTR` undeclared |
| `components/control/pll_control.c` | `#include "esp_attr.h"` (in the existing `ESP_PLATFORM` block) | `IRAM_ATTR` undeclared |
| `components/control/thermal_mass.c` | `#ifdef ESP_PLATFORM #include "esp_log.h"` | `ESP_LOGI/W` implicit declaration; host build unaffected |
| `components/hal/esp32/hal_{adc,spi,timer}_esp32.c` | `(int)` casts on `%d` log arguments (`int32_t` is `long` on xtensa) | `-Werror=format`; log text only |
| `config.c` | `strtof(s, NULL, 10)` -> `strtof(s, NULL)` (6x), `#include <stdio.h>`, `(unsigned)` cast on one `%u` | `strtof` takes 2 arguments (the radix was invalid C); `printf` undeclared; format mismatch |

## Control: host tests after the changes

Fresh dir `firmware/build-host-ctest` (`cmake -S firmware/test`):

```
100% tests passed, 0 tests failed out of 28
Total Test time (real) = 5.00 sec
```

## Files here

`build.sh` (reproduce), `build-strict.trimmed.log`, `build-diag-link.trimmed.log`, `undefined-symbols.txt`,
`size.txt`, `size-components.txt`, `compiled-glue-files.txt`, `linked-glue-objects.txt`, `mapsum.py`, `sdkconfig.evidence`,
`diag_stubs/` (diagnostic only). Not committed: `firmware/build/`, ESP-IDF, `ui.c` is not built (it needs
`hal_encoder`/`hal_led`, which only have mock implementations; `main.c` has its `ui_update()` call commented out).
