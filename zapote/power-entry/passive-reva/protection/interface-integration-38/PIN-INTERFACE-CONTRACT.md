# Rev38 pin and interface integration contract

Status: **candidate map joined in Atopile, integration in progress**. This is the integration
owner's single checklist for the source, isolation, receiver, and supply
interfaces. The HOT MCU and isolation endpoints below are selected in the
Rev38 Atopile fixture. The ESP module/GPIO and local expander allocation is
joined as `SourceMcu38` and exact-pin audited. A single source task is now
wired into `app_main`, but remains locked out; CPU-reset behavior and the
ESP-IDF target image are unverified. Rev38 sources compile for ESP32-S3, while
the full image fails link on unresolved production cooker hooks.
The approved plan and `receiver-selection.md` govern behavior; a pin listed
here is not an electrical, boot-state, or timing acceptance.

## Isolation and physical meanings

The listed pin numbers are device pins, not board connector numbers. SELV
ground and HOT0 remain isolated. Every safety-significant receiver input or
isolator output requires its local fail-low network and partial-power check.

| Channel | SELV endpoint | HOT endpoint | Meaning and failure behavior |
| --- | --- | --- | --- |
| ISO7741FDWR A, forward | pin 3 INA, source command TX | pin 14 OUTA, AVR PA1/31 USART0 RX | Frames are identity/sequence input; absent traffic gives no liveness credit. |
| ISO7741FDWR B, forward | pin 4 INB, retained source PERMIT Q | pin 13 OUTB, physical HOT PERMIT | Low clears RUN; loss after a prior high also invalidates SESSION. |
| ISO7741FDWR C, forward | pin 5 INC, source relay request | pin 12 OUTC, AVR PA5/3 input | AVR PA2 alone owns the relay output, and retained HOT RUN Q qualifies its MOSFET gate. |
| ISO7741FDWR D, reverse | pin 6 OUTD, source response RX | pin 11 IND, AVR PA0/30 USART0 TX | Response bytes carry protocol progress only. |
| ISO7742FDWR A, forward | pin 3 INA, source hardware-health Q | pin 14 OUTA, HOT source-health clear input | Loss clears both HOT retained memories independently of UART. |
| ISO7742FDWR B, forward | pin 4 INB, source STOP_N | pin 13 OUTB, HOT STOP clear input | Low asserts the physical abort path, including READY before PERMIT high. |
| ISO7742FDWR C, reverse | pin 5 OUTC, source HOT PERMIT readback | pin 12 INC, physical HOT PERMIT | Source sees the actual isolated conductor and records loss after high. |
| ISO7742FDWR D, reverse | pin 6 OUTD, source HOT SESSION readback | pin 11 IND, retained HOT_SESSION_OK Q | Source permit depends on this distinct feedback. |

Each isolator uses pins 1/2/8 for SELV supply/returns and pins 16/9/15 for
HOT supply/returns. Pin 7 EN1 and pin 10 EN2 are tied to their respective
supplies. The exact-pin Rust audit checks the present Atopile fixture; the
native board must preserve these assignments and domain separation.

## HOT receiver package ownership

Selected part: AVR64DA32-E/PT, 32-pin TQFP. These are the physical package
numbers in `receiver-selection.md` and the current receiver fixture.

| Pin(s) | Signal and sole owner | Required default or check |
| --- | --- | --- |
| 30 PA0 / 31 PA1 | USART0 response TX / command RX | Decoder cannot turn traffic alone into permission. |
| 32 PA2 / 3 PA5 | Relay drive output / isolated relay-request input | PA2 low at boot and lockout; no direct PA5-to-coil path. |
| 4 PA6 / 1 PA3 / 2 PA4 | Attempt-valid output / permit-seen Q input / preparation-abort reset request | PA6 has local low default; PA4 pulse precedes challenge publication. |
| 6 PC0 / 7 PC1 / 8 PC2 / 9 PC3 | Post-trip disarm Q / preparation-abort Q / fault summary inputs; permit-history reset request | PC3 pulse cannot erase a new preparation trip. |
| 10 PD0 / 11 PD1 / 12 PD2 | Physical HOT PERMIT / SESSION Q / RUN Q inputs | Fresh hardware readbacks, not firmware mirrors. |
| 13 PD3 / 14 PD4 / 15 PD5 / 16 PD6 / 17 PD7 | Abort_N / revalidation edge / RUN-set edge / receiver WDI / rail-good | Abort_N externally low on reset or high impedance; request clocks remain raw edges. |
| 20 PF0 / 21 PF1 | Physical SESSION_CLEAR_N readback / post-trip disarm-sample clock | Sample clear after abort release; verify disarm Q after the PF1 edge. |
| 18 AVDD / 19 GND / 28 VDD / 29 GND | HOT logic supply and HOT0 returns | Rail sequencing and brownout behavior remain unqualified. |
| 26 PF6 / 27 UPDI | RESET / programming | Keep reset enabled; record programmed fuse/BOD/clock image. |

## SELV ESP allocation proposed for the separate Rev38 candidate

Part assumption: ESP32-S3-WROOM-1-N8R8. This allocation preserves native USB
on GPIO19/20 and UART0 boot/debug on GPIO43/44. GPIO35–37 are unavailable
with its Octal PSRAM. It uses GPIO39–42 only after the JTAG/debug tradeoff in
`ESP-PIN-FIT.md` is accepted. Neither a bare firmware constant nor this table
is evidence of a joined module pad.

| Module pad / GPIO or expander bit | Runtime meaning | Direction and startup condition |
| --- | --- | --- |
| 21 / GPIO13 | SOURCE_STOP_N | Direct ESP output; external pull-down asserts STOP until deliberately released. |
| 23 / GPIO21 | Source TPS3431 heartbeat *request* | Direct ESP output; external pull-down; a deliberate rising edge triggers a one-shot whose active-low output feeds WDI. Do not write the retained pad during boot before disarm. |
| 25 / GPIO48 | SOURCE_PERMIT_SET_REQUEST | Direct ESP output; external pull-down; one synchronous low-high-low request. |
| 11 / GPIO18 | SOURCE_PREWATCHDOG_OK | Direct physical input; reset-good, interlock and rail-good combination excludes WDO. |
| 33 / GPIO40, 34 / GPIO41 | Isolated command UART TX / response UART RX | One synchronous protocol owner; UART0 remains on GPIO43/44. |
| 35 / GPIO42 | Fresh START button | Direct active-low input with normally open switch to ground and external pull-up; a prior held press is not a fresh intent. |
| 31 / GPIO38, 32 / GPIO39 | Local I²C SDA / SCL | One bounded bus owner; timeout or stale read must assert direct STOP. |
| TCA6408A-Q1 P0 / P1 / P2 | CHALLENGE_ACTIVE / SEEN_RESET_REQUEST / isolated relay request | Outputs; write low output latches and read back before enabling directions. Retained outputs during CPU-only reset need fault analysis. |
| TCA6408A-Q1 P3 / P4 / P5 / P6 / P7 | RAIL_RESET_N / local PERMIT Q / physical HOT PERMIT feedback / HOT SESSION feedback / PERMIT_SEEN Q | Inputs; one complete fresh snapshot with bounded age before START, WDI, or a control edge. |

The source physical read maps `safety_ok` to SOURCE_PREWATCHDOG_OK, never to
WDO-qualified SOURCE_HEALTH_Q. The direct STOP and independent source
watchdog own unexpected execution-loss shutdown. Expander reset, ESP reboot,
or an I²C ACK cannot be counted as immediate CPU-reset detection. The relay
request cannot bypass the AVR decision and retained HOT RUN gate.

`SOURCE_RESET_GOOD` and `SOURCE_INTERLOCK_N` currently have 10 kΩ local
pull-downs and no driving components, so the pre-watchdog sample stays low
on the compiled candidate. ESP EN is pulled high and does not report an
internal CPU-only reset. The source watchdog WDO clears source health, but
using that WDO as the pre-feed sample would make the first feed dependent on
the watchdog already being healthy. Choose and join independent reset and
interlock producers, then test CPU-only reset with retained expander and
GPIO state before enabling the source task. A pin assignment or a boot log
cannot close that physical producer gap.

For the screened [TCA6408A-Q1](https://www.ti.com/lit/ds/symlink/tca6408a-q1.pdf),
the output latch register `0x01` and
configuration register `0x03` both power up to `0xFF`. The adapter must hold
direct STOP low, write `0x00` to the output latch and read it back, then
write/read `0xF8` at the configuration register so P0–P2 become low outputs
and P3–P7 remain inputs. It must not enable output direction before the low
latch is verified. A CPU-only ESP reset can leave P0–P2 actively driven from
the old transaction until those writes occur; software boot ordering alone
does not bound that interval. No expander RESET conductor is assigned yet.

## Supply and assembly boundaries

| Interface | Current joined status | Required producer/acceptance |
| --- | --- | --- |
| SELV3V3/SELV_GND | Source authority, isolation, ESP module and expander loads joined; 3.3 V producer absent | Join supply, reset-good and interlock producers; qualify defaults during partial power. |
| HOT_LOGIC5/HOT0 | TPS54202 candidate joined after protected AUX; exact pads/net paths audited | Qualify complete load, feedback/output effective capacitance, startup, thermal, reset and rail-order behavior. |
| AUX_PROTECTED/HOT0 | LTC4368-2/FDS3992/shunt candidate joined as sole pre-cutoff-to-protected path; exact pads/net paths audited | Qualify load budget, divider procurement, FET SOA, OVP/UVLO, fast-fault output peak, startup and latch reset. |
| RAW_AUX24/HOT0 | IRM-20-24 pads 4/3 joined through the post-CMC AUX branch terminal to LMR36015BRNXT VIN/EN | Physical module orientation, branch cartridge and harness, raw peak, startup and thermal behavior remain unverified. The raw rail is HOT and feeds only the joined 15 V converter. |
| AUX15_PRECUT/HOT0 | LMR36015BRNXT SW → 18 µH → 44 µF nominal output bank and feedback divider, feeding only LTC4368 VIN/SHDN, upstream FET drain and UV/OV dividers | Effective capacitance, loop stability, startup, output window, fault peak and thermal behavior remain unverified. |
| FUSED_L/N/PE | Board terminal 1714984 pins 1/2/3 and AC path joined | Off-board F1/inlet harness is a separate assembly interface. No fuse installation or interruption PASS is implied. |

For the proposed IRM-20 AUX source, the installed KiCad 10 symbol and THT
footprint provide a candidate 1=AC/L, 2=AC/N, 3=−V, 4=+V mapping for both
15 V and 24 V versions; [the source decision record](AUX-SOURCE-CANDIDATE.md)
gives pad centers and provenance. The manufacturer drawing is a bottom view
with terminal names but no numeric pin table, so confirm orientation on a
physical module and a 1:1 native print before using that mapping to release
a board. The AUX branch now has Phoenix `1714971` position 1 as the
post-CMC line send to an off-board `LP-CC-2`/`BCM603-1P` assembly and
position 2 as the fused `AUX_FUSED_L` return to IRM AC/L. IRM AC/N takes
post-CMC `AC_RECT_N`. The two L terminal pads must stay electrically
separate on the PCB, with the fuse the only intended connection. The
terminal and IRM raw-source pins now compile, and the audit rejects a
copper bypass or direct pre-fuse feed; the off-board fuse and wiring remain
unbuilt. Inrush, fault and F1
coordination remain open.

The existing cooker `elec/src/main.ato` connects its `AuxSupply`
IRM-10-15 output to a **SELV** 15 V rail and a `PowerManagement`
LMR51430 3.3 V buck, with SELV ground bonded to PE separately from the HOT
return. That is a possible upstream source if Rev38 is integrated with that
assembly, but the existing 3.3 V load and new ESP/expander/isolation startup
load must be budgeted together. `SELV-SUPPLY-LOAD.md` inventories the joined
Rev38 loads and direct startup capacitance: Espressif requires at least 0.5 A
of source capability for the ESP alone, before the isolators and other logic.
The record does not establish spare power on the existing IRM-10-15 or its
3.3 V buck. Resolve whether the production and Rev38 ESP instances are one
physical device or two, and define the physical connector, rail limits,
reset-good and interlock producers. If Rev38 is a separate
board, its SELV source must instead be part of that board or a specified
external supply interface. Neither choice permits bonding `SELV_GND` to
`HOT0`; no 3.3 V source is credited in the current joined netlist.

The production `SafetyInterlock.shutdown` is an active-high latched **fault**
that drives the UCC21550 `DIS` input (`elec/src/main.ato`), while Rev38
`SOURCE_INTERLOCK_N` needs a high-to-allow, fail-low producer. The inspected
production source cross-couples a NAND latch and gives its reset request to
MCU GPIO14; it does not establish a power-up healthy state for a Rev38
interlock feed. Directly tying these signals would have the wrong polarity.
Inversion alone would not prove startup state, missing-wire default, retained
fault priority, or ownership if the two ESP instances are combined. Keep the
Rev38 interlock pull-down and treat any producer selection as OPEN until those
cases are represented in the joined circuit and tested at the physical pins.

## Integration gate

The Atopile candidate now joins source MCU, expander, button, source authority
and both isolation channels. The ESP adapter is host-tested and wired to one
`app_main` task, but is not target-built or measured. Zero target timing
bounds and unqualified UART final-bit, reset feed-tail, and monitor progress
conditions keep the task locked out. The expander P1 history-reset pulse
uses a candidate 5 ms I²C transaction timeout. Runtime now reserves its
configured sample-to-edge bound before requesting P1 or permit-set; the
bound still needs target capture. `uart_wait_tx_done()` is only
documented as waiting for the TX FIFO to empty; a final START-bit completion
claim also needs target capture. Before promoting this map, update the native
KiCad symbols/footprints and obtain the physical evidence.
Check every physical pad, pull/default, supply return, isolator direction,
UART ownership and expander retained-output case. The legacy cooker pin
header still names GPIO18 as a power LED and GPIO38/39 as optional I²C;
the current firmware has no callers of those aliases, but the native pin
ownership review must remove or reconcile them. Capture boot/CPU-only reset
and partial-power behavior on the selected hardware. Until then this is the
candidate **interface contract**, with ESP and supply joins OPEN.
