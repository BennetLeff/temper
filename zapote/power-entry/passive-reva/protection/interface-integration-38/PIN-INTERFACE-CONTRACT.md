# Rev38 pin and interface integration contract

Status: **candidate map, integration in progress**. This is the integration
owner's single checklist for the source, isolation, receiver, and supply
interfaces. The HOT MCU and isolation endpoints below are selected in the
Rev38 Atopile fixture. The ESP module/GPIO and local expander allocation is
screened but is **not yet joined** to that fixture or proven at CPU reset.
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
| 35 / GPIO42 | Fresh START button | Direct input; a prior held press is not a fresh intent. |
| 31 / GPIO38, 32 / GPIO39 | Local I²C SDA / SCL | One bounded bus owner; timeout or stale read must assert direct STOP. |
| TCA6408A-Q1 P0 / P1 / P2 | CHALLENGE_ACTIVE / SEEN_RESET_REQUEST / isolated relay request | Outputs; write low output latches and read back before enabling directions. Retained outputs during CPU-only reset need fault analysis. |
| TCA6408A-Q1 P3 / P4 / P5 / P6 / P7 | RAIL_RESET_N / local PERMIT Q / physical HOT PERMIT feedback / HOT SESSION feedback / PERMIT_SEEN Q | Inputs; one complete fresh snapshot with bounded age before START, WDI, or a control edge. |

The source physical read maps `safety_ok` to SOURCE_PREWATCHDOG_OK, never to
WDO-qualified SOURCE_HEALTH_Q. The direct STOP and independent source
watchdog own unexpected execution-loss shutdown. Expander reset, ESP reboot,
or an I²C ACK cannot be counted as immediate CPU-reset detection. The relay
request cannot bypass the AVR decision and retained HOT RUN gate.

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
| SELV3V3/SELV_GND | Source authority and isolation joined; ESP module producer absent | Join module supply, reset-good and interlock producers; qualify defaults during partial power. |
| HOT_LOGIC5/HOT0 | Receiver, isolators, watchdog and logic consumers joined; producer absent | Select/join 5 V producer with startup and rail-order evidence. |
| AUX_PROTECTED/HOT0 | Driver, PFC control, detectors and relay consumer joined; producer absent | Select/join 15 V protected chain and load budget; verify OVP/UVLO, fast-fault peak and startup. |
| FUSED_L/N/PE | Board terminal 1714984 pins 1/2/3 and AC path joined | Off-board F1/inlet harness is a separate assembly interface. No fuse installation or interruption PASS is implied. |

## Integration gate

Before promoting this map, update the joined Atopile entry, receiver and ESP
adapters, exact-pin audit, and native KiCad symbols/footprints together.
Check every physical pad, pull/default, supply return, isolator direction,
UART ownership and expander retained-output case. Capture boot/CPU-only reset
and partial-power behavior on the selected hardware. Until then this is the
candidate **interface contract**, with ESP and supply joins OPEN.
