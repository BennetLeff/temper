# Rev38 ESP32-S3 source pin-fit screen

Status: **allocation screen, not a pin contract or U6 PASS**. The present
source needs 15 logical channels while only GPIO13, 21 and 48 are unclaimed
ordinary pads in both existing authorities. The table below shows one way to
fit the interface while retaining GPIO19/20 native USB and GPIO43/44 UART0
debug. It has not been joined to `source_authority.ato`, built with ESP-IDF,
or checked on a board. See `ESP-PIN-INVENTORY.md` for the competing assignments.

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
| P2 | Isolated relay request | Output | A retained high needs independent HOT relay gating by session/health; the receiver relay policy is not implemented. |
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
reload a cleared memory, or keep the relay energized after permission loss.

The proposed adapter would treat I²C timeout, missing ACK, bad configuration
readback, or an incomplete input read as an unsafe physical sample and drive
direct STOP low. Its timeout, bus recovery, snapshot age, and sample-to-START
latency belong in the U1 bound. The source runtime's physical-sample
callback now returns a validity flag and asserts STOP on failure; a host
test covers a failed read. The relay-request pin and actual I²C target
adapter still need a fail-closed design before this allocation can be adopted. The
expander reset cannot simply be tied to WDO: WDO low would hold the I²C
readbacks unavailable while boot needs them to establish physical disarm
before the first recovery feed.

## Reconciliation and acceptance work

The existing cooker firmware uses GPIO19/20 for bypass relay/fault status,
while `elec/src/modules.ato` uses them for USB and places those functions on
GPIO16/17. This screen assumes the **new Rev38 variant** keeps USB and
reconciles the cooker functions to the actual candidate netlist. GPIO16's
future second RTD-select claim and GPIO17's fault-LED claim must be moved or
retired explicitly; the canonical board/firmware mapping is not changed by
this screen. The optional I²C bus must have one owner and a qualified load,
pull-up and stuck-bus behavior.

Before adoption: join the ESP/module, expander, source authority, isolators,
and physical button into one Atopile candidate; audit every numbered pad,
output default and isolation crossing; implement the synchronous ESP driver;
prove no autonomous/boot WDI edge; test expander retention and interrupted
I²C writes on CPU-only reset; and capture actual reset-to-off behavior. If
the three expander outputs cannot meet those failure cases, this allocation
fails and the source interface or MCU architecture needs revision.
