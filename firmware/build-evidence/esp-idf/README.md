# ESP-IDF build evidence (firmware/, ESP32-S3)

Date: 2026-10-12. Branches `build/esp-idf` (first compile) and `fw/platform` (platform layer, strict link). Reproduce with `./build.sh` (needs the IDF install below).

## Toolchain

| Item | Value |
|---|---|
| ESP-IDF | **v5.3.6**, tag commit `79e3454c68248bd7d881721c9b2e94561378a8ce` (`~/esp/esp-idf-v5.3.6`, outside the repo) |
| Why 5.3 | `.github/workflows/release-artifacts.yml` builds with `espressif/idf:release-v5.3`; README says "v5.0+". No `idf_component.yml`, `dependencies.lock` or committed `sdkconfig` exist. 5.3.6 is the newest 5.3.x tag. |
| Target | esp32s3 (`idf.py set-target esp32s3`) |
| Compiler | xtensa-esp-elf GCC 13.2.0 (`esp-13.2.0_20250707`), installed by `install.sh esp32s3` |
| Kconfig | `sdkconfig.defaults` + `sdkconfig.evidence` (one line: `CONFIG_TEMPER_POWER_HW_BINDING=y`, so the opt-in `n21_hw_esp32.c` is also compiled; it defaults to `n`) |

## Pass criterion

Clean build: every esp32 glue file compiled AND linked, `idf.py build` exit 0, with no diagnostic stubs.

## Result (2026-10-12, branch `fw/platform`)

| Stage | Result |
|---|---|
| Configure (`set-target`) | PASS |
| Compile, all glue files + all other firmware sources | **PASS** (0 errors, no new warnings; `compiled-glue-files.txt`, now 14 files incl. `main/platform/`) |
| Link, strict (`build-strict.trimmed.log`) | **PASS, exit 0** (`build.sh` prints `STRICT build exit code: 0`; the DIAG step did not run) |
| The 26 formerly undefined symbols (`undefined-symbols.txt`) | all `DEFINED` (type `T`) in `induction_cooker.elf`, each from `platform_esp32.c.obj` or `ui_esp32.c.obj`; 0 `diag_stubs` references in the link map (`platform-symbols-nm.txt`) |
| Host tests (`ctest-summary.txt`) | **29/29** (was 28; new `platform_logic_tests`, plus 3 new cases in `max31865_tests`) |

**Verdict: PASS.** The 26 platform functions now have production implementations for the integrated controller
(`main/platform/`, decisions in `components/platform/platform_logic.c`). Per-function hardware path, mapping source and
failure behaviour: **[PLATFORM.md](PLATFORM.md)**. Four are documented unsupported-safe (no hardware):
`read_dc_bus_current` (always `+INFINITY`, so PREHEAT latches FAULT_IGBT_SHORT: this image cannot heat until the owner
re-points that interlock, PLATFORM.md P1), `peripherals_enter_low_power`, `peripherals_exit_low_power`, `led_set_pattern`.
Bench-level open items (RTD conversions not commanded, provisional UI-board bit map) are listed there too.

History: at 4168c046a (branch `build/esp-idf`) the strict link failed with these 26 undefined references and a
non-flashable image was linked only with `diag_stubs/` (abort() stubs). That diagnostic path is still in `build.sh` for a
future link failure; it is not used now.

### Size (strict image, `size.txt`, `size-components.txt`, `bin-size.txt`)

`induction_cooker.bin` = **409312 bytes** (0x63ee0), 80 % of the 2 MB app partition free. Flash code 229404, flash data
89736, DIRAM 87699 (25.66 %), IRAM 16383 / 16384 (the IDF-reserved non-cache IRAM bank; normal for esp32s3). Project
archives: libmain 30812 (incl. the platform layer and its 8 KB OLED framebuffer in .bss), libpower 23965, libtemper_hal 11083.

### Proof the glue compiled and linked

- `compiled-glue-files.txt`: entries from `build/compile_commands.json` for every file under `components/*/esp32/`, `main/`
  and `components/power/n21_hw_esp32.c` (12 files, with object paths).
- `linked-glue-objects.txt`: the glue objects plus the platform layer (`platform_esp32`, `ui_esp32`, `platform_logic`,
  `rtd_service`, `max31865`) with their non-zero input-section sizes in the strict image's link map, so they are linked in,
  not just compiled.

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

### Platform layer (branch `fw/platform`)

| File | Change |
|---|---|
| `main/platform/platform_esp32.{c,h}`, `main/platform/ui_esp32.c`, `main/platform/ui_board_map.h` (new) | production implementations of the 26 functions (PLATFORM.md) |
| `components/platform/platform_logic.c`, `include/platform_logic.h` (new) | pure logic, host-tested by `test/test_platform_logic.c` |
| `components/sensors/max31865.{c,h}` | `MAX31865_RREF_OHM` (430 ohm, board r_ref), `max31865_read_rtd_word()`, `max31865_rtd_word_to_ohm()` |
| `components/sensors/rtd_service.{c,h}` | reads the RTD data word on each DRDY completion (before the unchanged fault-cycle service); `rtd_service_latest_word()` |
| `main/thermal_io.c` | the state machine's FAN_SPEED_MAX request is a full-speed floor on the fan law's command (one call, line 186) |
| `main/CMakeLists.txt` | the platform sources and include dirs |
| `test/CMakeLists.txt`, `test/test_platform_logic.c`, `test/test_max31865.c` | new ctest + 3 new cases; `test/state_machine_stubs.c` (host doubles) unchanged |
| `build.sh`, `mapsum.py` | nm proof + bin size on a strict pass; build-dir paths normalised to `<BUILD>`; map summary includes the platform objects |

## Control: host tests after the changes

Fresh dir `firmware/build-host-ctest` (`cmake -S firmware/test`):

At 4168c046a: `100% tests passed, 0 tests failed out of 28`. After the platform layer (`ctest-summary.txt`, fresh build
dir outside the repo):

```
100% tests passed out of 29
Total Test time (real) =   5.11 sec
```

## Files here

`build.sh` (reproduce; `BUILD_DIR=... ./build.sh`), `PLATFORM.md` (per-function mapping), `build-strict.trimmed.log`,
`platform-symbols-nm.txt`, `bin-size.txt`, `ctest-summary.txt`, `undefined-symbols.txt` (the 26 symbols missing at
4168c046a; input of the nm proof), `size.txt`, `size-components.txt`, `compiled-glue-files.txt`, `linked-glue-objects.txt`,
`mapsum.py`, `sdkconfig.evidence`, `diag_stubs/` (diagnostic fallback only, unused by a passing build). Not committed: the
build directory, ESP-IDF. `ui.c` is still not built (it needs `hal_encoder`/`hal_led`, which only have mock
implementations; the UI board is driven by `main/platform/ui_esp32.c` instead).
