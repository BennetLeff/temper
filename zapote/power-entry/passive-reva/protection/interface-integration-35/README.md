# Revision 35: one compiled source-to-PFC control candidate

Status: **compiled connectivity review candidate, not a released schematic or
qualified power entry.** This source copies the Rev29 AUX/PFC protection graph,
the Rev33 HOT receiver, and the Rev34 SELV source-health circuit into one
Atopile build. It changes no product PCB or earlier revision directory.

## What is joined

`source.source_latch.Q1/PERMIT_TX` drives the single `receiver.iso.INB`; its
`OUTB` reaches the Rev29 HOT permit buffer and retained hardware clear path.
The HOT ATmega's four buffered outputs reach Rev29 session-active, watchdog
WDI, qualified-session clock, and ARM inputs. Rev29's `rails_ok` reaches the
HOT receiver's dedicated open-drain reset supervisor MR, while Q2 link-good
returns to the ATmega's PC4 observation input. SELV and HOT isolator supplies
and grounds remain separate.

The join retains **one ISO7741F** in the HOT receiver core. Rev34's fixture
isolator and its unused-channel loads are removed. Rev33's four 10 kOhm
*modeled* loads are removed because Rev29 already has the actual input
pulldowns. The Rev34 correction remains: watchdog WDO/ENOUT share one 10 kOhm
pullup, with no competing watchdog-good pulldown.
The Rev29 external permit connector is removed in this copy so it cannot
drive around the isolator; the isolated permit net has the ISO output, HOT
permit-buffer input, one pulldown, and the HOT MCU sense input.
HOT firmware must leave that sense pin as an input through reset and normal
operation; the compiled netlist cannot enforce MCU pin direction.

The HOT receiver's unspecified crystal placeholder is changed from 16 MHz to
8 MHz. Microchip specifies 8 MHz operation from 2.7 V, while 16 MHz requires
at least 4.5 V. The existing Rev29 logic5 supervisor's 294 kOhm/100 kOhm
divider can release around 4.45 V at its low threshold corner, so retaining a
16 MHz clock would leave a specified-speed violation. This clock choice does
not select a real crystal, load capacitors, fuse image, or UART baud rate.

## What the build establishes

The offline Atopile 0.2.69 build emits 226 component instances and 164 named
nets. `audit.rs` parses the compiled netlist, checks critical pin membership
across the source latch, shared isolator, HOT receiver, watchdog, reset and
Rev29 protection, verifies one isolator and no duplicated fixture loads, and
rejects deliberate permit-miswire, external-bypass, and extra-isolator
mutations. The audit is
not an electrical simulation and does not establish firmware behavior.

Reproduce from this directory:

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/power_entry_integrated_35.ato:PowerEntryIntegrated35
rustc --edition=2021 audit.rs -o /tmp/temper35-audit
/tmp/temper35-audit
```

`receipt.sha256` pins the Atopile source, compiled netlist/BOM, audit, policy,
tests, and this note. Run `shasum -a 256 -c receipt.sha256` here to check
those artifact bytes.

## Required reset and firmware behavior

An ESP32-S3 CPU-only reset can leave the `SOURCE_RESET_GOOD` GPIO high. The
source latch therefore cannot treat that GPIO as an all-reset detector. On
every source boot or restart, firmware must inhibit any autonomous WDI service,
invalidate the old session, and keep re-arm low. Before a new re-arm it must
observe the *physical* source latch Q1/PERMIT_TX low after reset; when a prior
permit was high, withholding accepted-frame WDI edges lets TPS3431 timeout
clear that latch even if the GPIO remains high. A fresh validated peer
session may then generate accepted-frame WDI edges while the physical latch
remains low; this restores watchdog-good so the latch can accept a later
re-arm pulse. That pulse requires a new local start edge. A held start button
or restored software state cannot produce it.
The existing cooker firmware's unconditional TPS3823 feed is a separate
function and must not be used as this TPS3431 heartbeat.

The [host-tested source policy prototype](firmware-policy/README.md) implements
this lockout/re-arm state machine in portable C; six focused tests pass. It
is not linked into ESP-IDF and contains no frame decoder or WDI pin driver.
The policy still needs an ESP32 input bound to the source latch Q1/PERMIT_TX
readback, a qualified path to `SOURCE_REARM_PULSE`, and software integration.
They are external ports in this fixture. Product firmware must
test CPU-only reset with retained GPIO, reset immediately after a legal WDI
edge, boot transitions that themselves create one WDI falling edge, stale
session replay, a held start button, and an attempted early re-arm. It must
also prove that timer/DMA/peripheral activity cannot create WDI edges without
accepted frames. The policy permits watchdog-bounded shutdown; it does not
provide instantaneous internal-reset detection.

## Electrical and physical work still open

- The SN74LVC1G17 output-high guarantee at full HOT rail is not matched to
  Rev29's 10 kOhm loads. Reducing pulldowns to 100 kOhm would fit TI's 100 µA
  output test point, but default-low behavior with leakage and partial power
  must be checked before changing those safety biases. Similar loaded-high
  checks remain for the source and HOT AND outputs.
- The exact HOT and SELV rail minima, TPS3890 threshold and CT corners,
  oscillator part/load, BOD fuses, HCS74 pulse widths, and supply ramps are
  unqualified. The 8 MHz choice removes the specific 16 MHz/4.5 V cliff; it
  does not qualify the complete ramp.
- TPS3431's 1 nF CWD and the source latch define no measured maximum
  fault-to-gate/relay turn-off time. Capacitor tolerance, watchdog reset pulse,
  logic and isolation propagation, gate discharge, relay release, and current
  cessation must be bounded together.
- The real AUX source impedance/surge envelope, converter VIN current during
  startup, LT4363/FET SOA and fault recovery, fuse choice, footprints,
  manufacturing MPN export, native KiCad/ERC/DRC, and low-voltage bench capture
  remain open. No assembled prototype is available.

Primary data: [ATmega328P](https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf),
[TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf),
[TPS3431](https://www.ti.com/lit/ds/symlink/tps3431.pdf),
[SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf),
[ESP32-S3](https://documentation.espressif.com/esp32-s3_datasheet_en.pdf).
