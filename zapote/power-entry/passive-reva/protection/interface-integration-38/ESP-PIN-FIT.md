# Rev38 ESP32-S3 source pin-fit screen

Status: **joined Atopile pin fixture plus candidate adapter, not U6 PASS**. The present
source needs 15 logical channels while only GPIO13, 21 and 48 are unclaimed
ordinary pads in both existing authorities. The table below shows one way to
fit the interface while retaining GPIO19/20 native USB and GPIO43/44 UART0
debug. `firmware/main/power_entry_esp32_adapter.c` and
`power_entry_esp32_idf.c` now implement this candidate mapping and boot
sequence. `elec/src/source_mcu.ato` joins the Rev38-side 16-contact port and
expander to the source authority and isolation channels. The module pads in
this table belong to the existing cooker ESP and its unbuilt mating port; the
source runtime is wired into `app_main`, and its application objects compile
with ESP-IDF v5.3. The complete cooker image still fails at link on unresolved
production hooks; no target board check has run. See `ESP-PIN-INVENTORY.md`
for the competing assignments.

## Direct ESP pins in the screened allocation

The exact N8R8 module pad numbers come from [Espressif's WROOM-1 module
datasheet](https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf).
GPIO39–42 are ordinarily external JTAG pins; [Espressif's USB Serial/JTAG
guide](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-guides/jtag-debugging/configure-builtin-jtag.html)
permits USB debugging on GPIO19/20 instead. This choice needs actual USB
recovery and boot-pin verification, including eFuse/strap state.

| Module pad / GPIO | Screened owner | Direction | Required reset/default and displaced use |
| --- | --- | --- | --- |
| 21 / 13 | `SOURCE_STOP_N` | ESP output | External pull-down holds STOP asserted; no other owner. |
| 23 / 21 | `SOURCE_VALIDATED_HEARTBEAT` one-shot request | ESP output | External pull-down; only deliberate rising software edge may feed WDI. |
| 25 / 48 | `SOURCE_PERMIT_SET_REQUEST` | ESP output | External pull-down; synchronous low-high-low request only. |
| 11 / 18 | `SOURCE_PREWATCHDOG_OK` physical sample | ESP input | Replaces the provisional power LED; no safety decision from an LED state. |
| 33 / 40 | Isolated command UART TX | ESP output | External JTAG function relinquished; no ROM UART0 chatter on this pin. |
| 34 / 41 | Isolated response UART RX | ESP input | External JTAG function relinquished. |
| 35 / 42 | Fresh dedicated START button | ESP input | External JTAG function relinquished; GPIO0 remains a download strap, not START. |
| 31 / 38 | I²C SDA to local expander | Bidirectional | Already an optional I²C claim in firmware/source; must not share an unbounded bus owner. |
| 32 / 39 | I²C SCL to local expander | ESP output | Existing I²C/JTAG claims must be reconciled; USB JTAG remains available. |

The START button is normally open to local ground with an external pull-up
to the ESP 3.3 V rail. GPIO42 low means pressed. The adapter does not enable
an internal pull-up. The TCA6408A ADDR pin must be tied low for the adapter's
7-bit address 0x20; RESET_N needs a pull-up to VCCI and is not allocated to an
ESP GPIO. The Atopile fixture joins these exact source nets and module pads;
the 3.3 V producer, source reset-good and interlock producers remain open.

The isolated protocol would use a GPIO-matrix-routed UART, with a single
driver owner and bounded completed-frame transmission. GPIO43/44 stay on
UART0 for boot/debug, and GPIO19/20 stay on USB. GPIO35–37 remain unavailable
on N8R8 because of Octal PSRAM. This allocation consumes every listed direct
pad. A second RTD select, fault/power LEDs, or another source input needs a
new allocation; none is silently assigned to a strapping pin.

## Eight slow channels on a local I²C expander

[TI TCA6408A-Q1](https://www.ti.com/lit/ds/symlink/tca6408a-q1.pdf)
(`TCA6408AQPWRQ1`) is a *screened* 8-bit, 1.65–3.6 V, −40 to +125 °C part
with an active-low reset input. It is not a BOM selection. On POR or reset,
all P pins are inputs; its output-port register defaults to **0xFF**. An
adapter must write the output-port register low and read it back **before**
enabling any output direction, or the external pull-downs would momentarily
lose control to a high driver.

| Expander bit | Screened owner | Direction | Failure meaning |
| --- | --- | --- | --- |
| P0 | `SOURCE_CHALLENGE_ACTIVE` | Output | Low/high-Z cancels preparation; high retained through CPU-only reset needs a stale-challenge proof. |
| P1 | `SOURCE_SEEN_RESET_REQUEST` | Output | Positive-edge one-shot request; no replay after I²C recovery or CPU reset. |
| P2 | Isolated relay request | Output | A retained high reaches AVR PA5. The joined HOT HCS21 now also requires retained RUN Q before the relay MOSFET gate can rise; receiver timing and contact release remain open. |
| P3 | `SOURCE_RAIL_RESET_N` | Input | Missing/low is unsafe. |
| P4 | `SOURCE_PERMIT_Q` | Input | Fresh physical local-latch readback, never a cached output command. |
| P5 | `SOURCE_HOT_PERMIT_FB` | Input | Fresh reverse-isolator readback. |
| P6 | `SOURCE_HOT_SESSION_FB` | Input | Fresh reverse-isolator readback. |
| P7 | `SOURCE_PERMIT_SEEN_Q` | Input | Fresh local history readback. |

The expander output default is high impedance only after *its own* reset. An
ESP CPU-only reset can leave the expander powered and its output registers
unchanged. Therefore software boot writes, the expander RESET pin, and a
successful I²C ACK are **not** credited as immediate source-reset detection.
The direct STOP and watchdog circuit still own the bounded-reset path. A
held expander output must be proved unable to extend the watchdog deadline,
reload a cleared memory, or keep the relay energized after retained RUN
clears. The new HOT relay gate establishes connectivity, not release time.

The candidate adapter treats I²C timeout, missing ACK, bad configuration
readback, or an incomplete input read as an unsafe physical sample and drives
direct STOP low. It sets the TCA6408A output latch to 0x00, verifies the
readback, clears polarity inversion, and only then enables P0–P2 as outputs
with configuration 0xF8. Every physical sample checks those registers again
and reads P3–P7 and the direct GPIO inputs. Host tests cover retained-high
expander state at CPU-only reset, ordering, and failed readback. The ESP-IDF
binding uses I²C0 at 100 kHz and UART1 at 115200 8N1, with a TX-FIFO drain
call; final shift-register completion is not proven and needs target capture.
The binding uses the I²C master API available in the tested ESP-IDF v5.3
toolchain and is registered in `firmware/main/CMakeLists.txt`. The binding
has compiled for ESP32-S3, but full-image linking and physical timing remain
open. The relay-request P2 remains held low by this adapter until a
separate RUN-qualified owner is joined and tested. Its timeout, bus recovery,
snapshot age, and sample-to-START latency belong in the U1 bound. The
expander reset cannot simply be tied to WDO: WDO low would hold the I²C
readbacks unavailable while boot needs them to establish physical disarm
before the first recovery feed. P1's positive edge can occur after two I²C
transactions. The runtime now reserves the full configured sample-to-edge
bound before requesting P1 or permit-set and the sample-to-WDI bound before
feeding in timed states. Host tests reject a request with less than that
reserve remaining; the configured bounds still need worst-case target
measurement, including I²C retries/timeouts and clock resolution, before
crediting U1.

## Reconciliation and acceptance work

The cooker pin header now assigns the relay and fault inputs to GPIO16/17,
matching `elec/src/modules.ato`, and reserves GPIO19/20 for USB. GPIO18 is
assigned to the Rev38 pre-watchdog input. The optional UI I²C header remains
electrically shared with Rev38 on GPIO38/39. That bus must have one owner
and qualified load, pull-up and stuck-bus behavior.

Before adoption: resolve native footprints and supply producers, define a
state-aware independent monitor progress check and prove no
autonomous/boot WDI edge; test expander retention and interrupted I²C writes
on CPU-only reset; and capture actual reset-to-off behavior. If
the three expander outputs cannot meet those failure cases, this allocation
fails and the source interface or MCU architecture needs revision.
