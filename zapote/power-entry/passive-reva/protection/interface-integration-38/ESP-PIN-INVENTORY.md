# Rev38 ESP32-S3 source pin inventory

Status: **inventory only; pin contract OPEN**. The joined Rev38 Atopile
candidate still has no ESP component or GPIO producer. Do not assign the
firmware runtime callbacks to numbered GPIOs from this inventory alone.
`ESP-PIN-FIT.md` records one unadopted GPIO/I²C-expander allocation and its
reset-time failure cases; it does not change this status.

## Module limits

The existing cooker source names `ESP32-S3-WROOM-1-N8R8` in
`elec/src/components.ato`. Espressif's [module datasheet, Table 3-1](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
shows that GPIO35, GPIO36, and GPIO37 are internally used by the Octal PSRAM
on this variant and are unavailable externally. The same table maps module
pads 21/23/24/25/31/32/33/34/35 to GPIO13/21/47/48/38/39/40/41/42.
The [ESP32-S3 chip datasheet, Sections 2.3.4–2.3.5](https://documentation.espressif.com/esp32_s3_datasheet_en.pdf)
identifies GPIO0/3/45/46 as strapping pins, GPIO19/20 as USB, GPIO39–42 as
JTAG, and GPIO43/44 as UART0. These functions constrain boot, debugging,
and recovery; a GPIO being exposed on the module does not make it free.

## Existing cooker claims to reconcile

| GPIO | `firmware/components/hal/include/temper_pins.h` | `elec/src/modules.ato` MCU module |
| --- | --- | --- |
| 0 | Reset button | BOOT/download button and pull-up |
| 1–3 | ADC current, bus, NTC | ADC current, bus, NTC |
| 4–5 | PWM high/low | PWM high/low |
| 6–7 | TPS3823 reset input/feed output | TPS3823 reset input/feed output |
| 8–12 | MAX31865 SPI, DRDY, chip select | MAX31865 SPI, DRDY, chip select |
| 14–15 | Reset request, runaway cut | Reset request, runaway cut |
| 16 | Future second RTD select | Bypass relay control |
| 17 | Fault LED | Fault status input |
| 18 | Power LED | No MCU connection shown in the cited block |
| 19–20 | Bypass relay, fault status | Native USB D−/D+ |
| 38–39 | Optional I²C | I²C pull-ups and bus |
| 43–44 | Debug UART0 | UART0 |
| 47 | No definition | Bus-discharge relay control |

The firmware and electrical source conflict on GPIO16/17/19/20. The baseline
symbol also declares GPIO35–37 despite its N8R8 MPN. Neither side is a valid
Rev38 pin authority until these conflicts are resolved in the separate
candidate and firmware together. The canonical board stays unchanged.

Without reassignment, GPIO13, GPIO21, and GPIO48 are the only exposed
non-strap, non-debug, non-USB pins with no claim in either cited source.
GPIO18 has only a firmware LED claim. GPIO38 is optional I²C in firmware but
is connected in the electrical source. GPIO39–42 have JTAG or I²C claims.

## Rev38 logical I/O demand before sharing or reassignment

| Direction | Signals needing an assigned producer or physical sample |
| --- | --- |
| Outputs (7) | Runtime STOP_N, CHALLENGE_ACTIVE, SEEN_RESET_REQUEST, PERMIT_SET_REQUEST, validated WDI heartbeat; isolated command TX and relay request |
| Inputs (8) | Protocol RX; local permit Q, physical HOT permit, retained HOT session, permit-seen Q, rail-good, external safety aggregate, fresh START button |

This is a **logical-channel count**, not a final GPIO count. `SOURCE_RESET_GOOD`
and `SOURCE_INTERLOCK_N` also need real hardware producers; an ESP output may
not impersonate either independent condition. The eventual design may combine
or move signals only after preserving the asynchronous STOP/clear path,
independent readbacks, reset boot defaults, and WDI one-owner rule. Any GPIO
expander, multiplexing, USB/JTAG repurpose, or change to existing cooker pin
functions needs a reviewed timing and failure analysis. The STOP, WDI, and
permit-set paths especially require direct pin/edge ownership evidence.

The source circuit now generates `SOURCE_PREWATCHDOG_OK` from reset-good,
interlock, and rail-good without WDO. It is a candidate `safety_ok` sample
before the first watchdog feed, not a reserved ESP pin. The logical input
count above is unchanged; the final contract must say whether `rail_good`
also gets its own GPIO or shares this composite with a justified loss of
diagnostic detail.

The next pin contract must enumerate every module pad, exact GPIO, net,
direction, boot state, pull/default, sole firmware owner, competing cooker
function, and test point. It must be checked against the compiled Rev38
netlist and target boot capture before U4/U6 pin acceptance.
