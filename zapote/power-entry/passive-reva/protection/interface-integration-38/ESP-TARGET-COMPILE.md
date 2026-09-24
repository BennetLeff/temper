# Rev38 ESP32-S3 target compile attempt

Status: **diagnostic lockout and Rev38 source-task test images linked;
production image and target behavior OPEN**. These links are
compiler/interface checks, not timing or reset acceptance.

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
production ESP-IDF link remains **FAIL** and U6 remains OPEN. Neither target compilation
nor a host PASS changes the zero-timing lockout or physical qualification
status.

## Diagnostic lockout image (2026-09-24)

The default `TEMPER_DIAGNOSTIC_LOCKOUT=ON` ESP-IDF configuration selects a
separate entry point and explicitly marked diagnostic cooker hooks. The
normal `main.c` path is selected with `-D TEMPER_DIAGNOSTIC_LOCKOUT=OFF` and
still requires real implementations of the 32 cooker interfaces above. The
diagnostic hooks cannot compile without the diagnostic definition; they are
not a production peripheral implementation or a substitute for the U6
target behavior evidence.

The diagnostic entry point loads the GPIO output latch before enabling each
pin, then drives Rev38 `SOURCE_STOP_N` (GPIO13) low, cooker `RUNAWAY_CUT`
(GPIO15) high, both gate PWM pins (GPIO4/5) low, and the bypass-relay pin
(GPIO16) low. It repeats that sequence and aborts on a GPIO failure. It never
starts the cooker state-machine tasks, the legacy watchdog initialization
(which clears `RUNAWAY_CUT`), the Rev38 source task, either watchdog feed, or
the I²C/UART command owners. Diagnostic power-request hooks reassert the cuts
and abort; all diagnostic self-tests return failure. The image retains a
read-only reference to `state_machine_update()` so the cooker core and its
interfaces must resolve at image link without running that core.

Build reproduction, from the repository root, using the local IDF v5.3.6
image and a temporary SDK configuration/build directory:

```sh
docker run --rm -v "$PWD":/work -w /work/firmware \
  espressif/idf:release-v5.3 bash -lc \
  'cp sdkconfig /tmp/temper-diagnostic-sdkconfig && \
   idf.py -B /tmp/temper-diagnostic-build \
     -D SDKCONFIG=/tmp/temper-diagnostic-sdkconfig build'
```

The host `test_diagnostic_lockout` checks the exact cut sequence and that a
single failed pin drive reports failure while still attempting every other
cut. With `espressif/idf:release-v5.3` (IDF v5.3.6), the full default
diagnostic build completed the `induction_cooker.elf` link and generated an
ESP32-S3 binary of `0x31a40` bytes; the state-machine link anchor is present.
The host lockout test passed. This is software evidence only. No board was
programmed or measured:
power-on pin states before the ESP begins executing, GPIO output readback,
physical gate and relay levels, reset-to-off latency, and Rev38 response
timing remain unqualified. This linked diagnostic image does **not** close U6
or change any Rev38 zero timing bound.

On 2026-09-24 the same Docker command rebuilt the diagnostic image after
`0c3093230` and `bb8be3714`. The updated source authorization, runtime,
ESP adapter and IDF binding objects compiled; `induction_cooker.elf` linked
and the binary remained `0x31a40` bytes. The container lacked `jinja2`, so
the build used the committed generated config and transition-table headers;
the independent `make regen-check` gate passed in the worktree. This is a
compile receipt only: the diagnostic entry point does not run the source
task or exercise GPIO14 on hardware.

After the RTD freshness-status change on 2026-09-24, a diagnostic rebuild was
attempted with the same command. It stopped before IDF startup because the
local Docker daemon socket did not exist. The MAX31865 host tests and all 17
firmware CTest entries pass, but the updated RTD object and diagnostic image
have **no new ESP32-S3 target build receipt**. Repeat the target build when
the IDF container is available; do not transfer the earlier image receipt to
these changed bytes.

The later GPIO14 open-drain candidate also has no ESP32-S3 build receipt.
`docker info` still cannot find the local daemon socket; launching the
installed Docker Desktop bundle returned macOS `kLSNoExecutableErr`, and its
direct executable exited 134. Host compilation does not establish that the
IDF GPIO mode, release path or pulse delay builds and behaves on the target.
The subsequent source-task request and restart path likewise has host runtime
tests but no new IDF compiler or device receipt; `esp_restart()` reset and
retained-peripheral behavior still require target capture.

The later production cooker RTD-temperature and monotonic-clock hooks, INIT
conversion wait, and diagnostic link-anchor type correction initially had no
ESP32-S3 build receipt. On 2026-09-24, `docker info` failed because
`~/.docker/run/docker.sock` did not yet exist, and no local `idf.py` was found.
The 22 focused MAX31865 tests and all 17 host CTest entries passed. That
Docker outage was subsequently resolved; the refreshed diagnostic and Rev38
test-image receipts below supersede the target-build gap for those images.
Production still has unresolved cooker peripheral/self-test hooks.

### Refreshed diagnostic image

After Docker became available on 2026-09-24, the diagnostic reproduction
command above rebuilt the current sources, including the RTD object and the
corrected state-machine link anchor. `induction_cooker.elf` linked and the
ESP32-S3 binary was `0x31b20` bytes. SHA-256: ELF
`8ddfbea149b14dcf6f232989be5b2aa561738e408646d5207339e1becfe52885`;
binary `e2a4651d9f09e3ce47dcff7dae924beb535398d3dee901c37c353bf164af6382`.
The complete local `firmware/sdkconfig` input SHA-256 was
`88adb4734e78f358e8cbd60dc71eab8bd0052a39700d9443edf43a4e2aaa4861`.
The diagnostic entry remains a lockout image, not a programmed-pin or
source-task run receipt.

## Rev38 source-task test entry (target link PASS, 2026-09-24)

`firmware/main/rev38_source_test_idf.c` is a third, explicitly selected
`TEMPER_REV38_TEST_IMAGE=ON` entry. It establishes direct STOP, runaway cut,
PWM-low and bypass-relay-low outputs, then calls the **real**
`pe_esp32_source_service_start()` task. That task initializes the GPIO,
I²C0/TCA6408A and UART1 ownership path before its zero timing qualifiers
force lockout. The entry treats an armed return as an error and reasserts
the cooker cuts afterward. The test-image CMake source list excludes the
incomplete cooker application and its diagnostic mock hooks; the existing
diagnostic and production image selections remain separate.

Current source SHA-256: entry
`5fb7af8681470ded15ce9ed9099028451bd41a2826e0910af3ae9080ff6231aa`,
`firmware/main/CMakeLists.txt`
`15f9eed25f55086d7616ed579b6134f810e8c50788986497aa72c4569bdd571e`.
The host CMake suite builds and all 17 CTests pass with the worktree venv on
`PATH`. The local Docker daemon became available later on 2026-09-24. The
full ESP-IDF v5.3 target build then compiled the actual source-task entry,
source service, ESP32 adapter, IDF GPIO/I²C/UART binding, authorization
runtime and receiver protocol, linked `induction_cooker.elf`, and generated
the ESP32-S3 binary. Reproduction from the repository root:

```sh
docker run --rm -v "$PWD":/work -w /work/firmware \
  espressif/idf:release-v5.3 bash -lc \
  'cp sdkconfig /tmp/temper-rev38-sdkconfig && \
   idf.py -B /tmp/temper-rev38-build \
     -D SDKCONFIG=/tmp/temper-rev38-sdkconfig \
     -D TEMPER_REV38_TEST_IMAGE=ON build && \
   sha256sum /tmp/temper-rev38-build/induction_cooker.elf \
     /tmp/temper-rev38-build/induction_cooker.bin'
```

The complete local `firmware/sdkconfig` input SHA-256 was
`88adb4734e78f358e8cbd60dc71eab8bd0052a39700d9443edf43a4e2aaa4861`;
the committed `sdkconfig.defaults` SHA-256 was
`31d786e2cd3c4cbf3b8228bcd123d58dacc6f3b80d95821d3fc4ad3242140405`.
The linked ELF SHA-256 was
`f6b5e305203cb5aa817254b5b4bf7f1cddeb4cc933b75ca7d7431904ab734613`;
the binary SHA-256 was
`635ebf3527ec84f7adfaad95728baee65452d780f518500c3067bfdef079279b`,
size `0x376f0` bytes. This passes the **source-task target-build** check.
The container lacked `jinja2`, so it used the committed generated config
and transition-table headers. The build emitted non-fatal existing HAL/ADC
warnings. The local `sdkconfig` is generated and untracked; its hash pins
this receipt's exact configuration rather than asserting that a fresh
checkout automatically reproduces it.

A separate fresh build **from committed `sdkconfig.defaults` alone** also
linked on 2026-09-24. It used `-B /tmp/temper-rev38-repro-build`,
`-D SDKCONFIG=/tmp/temper-rev38-repro-sdkconfig`,
`-D IDF_TARGET=esp32s3` and `-D TEMPER_REV38_TEST_IMAGE=ON`, with no copy of
the local config. IDF generated a config with the **same** SHA-256
`88adb4734e78f358e8cbd60dc71eab8bd0052a39700d9443edf43a4e2aaa4861`.
That second ELF was
`a69de5cfd7ba6aa14a6155414b0cc8aff2fa174c362951c7c97ba4fdbf255c64`
and the binary was
`dea7ab8bbc0491b792c80c80ff6797f2be43da00e6264a2179b65661c60aca9a`
SHA-256, again `0x376f0` bytes. The two output hashes differ despite the
matching generated config and source bytes; this record claims two
successful target links, not byte-for-byte reproducible IDF output. The
fresh build establishes that the test image does not depend on the untracked
local `sdkconfig` file.

### Monitor-fault source task refresh (2026-09-24)

After the source-owner monitor-fault latch was added, all 17 firmware host
CTest entries passed. A fresh read-only-source Docker build with
`espressif/idf:release-v5.3`, `-D IDF_TARGET=esp32s3` and
`-D TEMPER_REV38_TEST_IMAGE=ON` compiled the updated service/runtime and
linked the test image. The ELF SHA-256 is
`f11480013851254d0007edc6f288a8cf39d0acd72b9af9e90383bdbffb6a7957`;
the binary SHA-256 is
`60a6d4e6dc2b2b9245dcd2e1719129320db6723e23bf7d330356da450919df83`
and size is `0x37900`. The container again used the committed generated
headers because `jinja2` is absent. This is a target **link** receipt, not
programmed-pin or response-time evidence. The monitor producer has no
qualified cooker safety check yet, and zero timing qualifiers keep the
source service locked out.

No board has been programmed or captured. GPIO13/21/48/14, UART final-bit,
I²C age, WDI/PERMIT, gate and relay levels, reset feed tail and fault timing
remain unmeasured. Zero target timing bounds keep the service locked out.
The cooker production image still lacks peripheral/self-test hooks, and its
target link remains OPEN. The earlier Docker-unavailable observations above
are historical and superseded for this Rev38 test-image build.

## Normal cooker production image retry (target link FAIL, 2026-09-24)

With Docker available, the normal `main.c` entry was selected explicitly by
`-D TEMPER_DIAGNOSTIC_LOCKOUT=OFF -D TEMPER_REV38_TEST_IMAGE=OFF` using the
same pinned local `sdkconfig` hash above. ESP-IDF compiled the registered
production sources and reached the final ELF link, which failed on genuine
missing cooker peripheral and self-test definitions. The unresolved set
includes power/PWM, heatsink/DC-current sensing, buttons/UI/fan/buzzer,
EEPROM logging and seven POST `test_*` hooks. The production source now
defines `get_time_ms` and `read_pan_temperature`; they no longer require
stubs. Diagnostic hooks are intentionally excluded from this image.

This retry separates a real production integration gap from a missing Docker
toolchain. `main.c` already starts the Rev38 source task, but its zero timing
qualifiers and absent independent monitor progress keep authorization in
lockout. A production link requires actual board implementations and source
registration for the remaining hooks. Even a successful link would still
need programmed-pin, rail, reset and timing captures before physical credit.
