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
unresolved cooker functions. Examples include `peripherals_init`,
`get_time_ms`, `display_show_message`, `test_adc_calibration` and other
self-test callbacks, `read_pan_temperature`, and hardware watchdog/shutdown
hooks. Some functions have production source that the app's CMake target does
not include (for example `firmware/config.c` and `components/safety/safety.c`);
others are currently found only in `firmware/test/state_machine_stubs.c`.
Those test implementations must not be linked into an operational image.
The remaining linker set needs real production implementations and an
explicit component/source inventory. The ESP-IDF build remains **FAIL** and
U6 remains OPEN. Neither target compilation nor a host PASS changes the
zero-timing lockout or physical qualification status.
