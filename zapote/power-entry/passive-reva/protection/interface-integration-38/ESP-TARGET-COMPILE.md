# Rev38 ESP32-S3 target compile attempt

Status: **seven application translation units compiled for ESP32-S3; full
image, link and target behavior OPEN**. This is a compiler compatibility
check, not a timing or reset acceptance.

On 2026-09-23, the `espressif/idf:release-v5.3` Docker image reported
ESP-IDF `v5.3.6-23-gc54ee794c20` and Xtensa GCC 13.2.0. From the worktree's
`firmware` directory, the normal `idf.py build` configuration stopped before
Rev38 compilation because `components/webui/CMakeLists.txt` requires
`esp_vfs_fat`, unavailable in that IDF image. A main-only configure with
`idf.py -D COMPONENTS=main build` then stopped on the missing configured
`firmware/partitions.csv`. Using a temporary single-app partition setting
passed that point, but the project's local `components/hal` name shadowed
IDF's own `hal`, leaving Mbed TLS unable to find `hal/aes_types.h`.

For a **compile-only** check, generated `compile_commands.json` commands
were invoked with temporary include paths for IDF's `hal/include`,
`hal/esp32s3/include` and `hal/platform_port/include`. The Xtensa compiler
successfully produced objects for:

- `firmware/main/main.c`
- `firmware/main/power_entry_authorization.c`
- `firmware/main/power_entry_source_runtime.c`
- `firmware/main/power_entry_esp32_adapter.c`
- `firmware/main/power_entry_esp32_idf.c`
- `firmware/main/power_entry_esp32_service.c`
- `zapote/power-entry/passive-reva/protection/interface-integration-38/receiver-firmware/protocol.c`

The temporary generated build, configuration and objects were removed.
This first check did not establish a linked application, bootable image,
single-owner peripheral behavior, final UART-bit completion, watchdog feed
tail, I²C age, or physical reset-to-off time. The Rev38 source task retains
zero target timing bounds and stays in lockout. A full target build must
first resolve the project configuration/component issues without bypassing
the actual firmware dependency graph, then program and capture the selected
ESP32-S3 hardware.

## Full-image build progression

A subsequent build in the same IDF v5.3 image used the configured custom
partition table and compiled the project's renamed `temper_hal` alongside
IDF's own `hal`. The web UI dependency was corrected to IDF's `fatfs` name.
The production HAL now declares its driver dependencies during IDF's early
component scan, and its target C files compile with the IDF warnings-as-errors
flags. The firmware host CMake build and all 16 CTest entries also pass after
the component rename.

The full target build reaches `induction_cooker.elf` but **fails to link** on
unresolved cooker functions. Production `config.c`, six control sources, and
`safety.c` are now registered and compile under IDF v5.3; the build also
exposed and resolved six invalid `strtof` calls, a target format mismatch,
and missing IDF declarations in those files. The remaining 32 unique linker
symbols are cooker integration work, not Rev38 authorization evidence:

| Owner still needed | Unresolved symbols |
| --- | --- |
| Boot/time/power and sensing | `peripherals_init`, `peripherals_enter_low_power`, `peripherals_exit_low_power`, `get_time_ms`, `read_pan_temperature`, `read_heatsink_temperature`, `read_dc_bus_current`, `power_enable`, `power_set_level`, `pwm_disable_all`, `pwm_set_duty_cycle` |
| Local input/output | `button_is_pressed`, `button_set_enabled`, `buzzer_beep`, `buzzer_beep_continuous`, `buzzer_stop`, `display_show_fault`, `display_show_message`, `display_update_countdown`, `display_update_temperature`, `fan_set_auto_mode`, `fan_set_speed`, `is_fan_running`, `led_set_pattern`, `eeprom_log_fault` |
| Startup self-test | `test_adc_calibration`, `test_pwm_generation`, `test_fan_operation`, `test_hardware_comparators`, `test_rtd_sensor`, `test_display_communication`, `test_eeprom_read` |

The same names have definitions in `firmware/test/state_machine_stubs.c` but
those are mock implementations and cannot fill a production image. The
ESP-IDF build remains **FAIL** and U6 remains OPEN. Neither target compilation
nor a host PASS changes the zero-timing lockout or physical qualification
status.
