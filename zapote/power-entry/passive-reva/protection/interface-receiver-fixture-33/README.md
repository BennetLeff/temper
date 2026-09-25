# Rev33 HOT receiver hardware fixture

Status: **offline-compiled connectivity fixture; no receiver firmware, PCB,
protocol implementation, or bench qualification.** This directory implements
the Rev31 ATmega328P-AU and ISO7741F pin plan as a standalone Atopile source
fixture. It adds no changes to the product PCB or earlier revision folders.

## Compiled interfaces

The fixture maps the Rev16 forward channels to HOT ATmega inputs: ISO7741F
OUTA pin 14 to PD0/RXD pin 30 for command, OUTB pin 13 to PD2 pin 32 for
maintained PERMIT, and OUTC pin 12 to PD3 pin 1 for RELAY_CMD. Reverse channel
D maps ATmega PD1/TXD pin 31 to ISO7741F IND pin 11 and SELV OUTD pin 6 to
`SOURCE_RESPONSE_RX`. USART is used only for command and response. PERMIT and
RELAY_CMD stay separate digital inputs.

Four HOT-powered SN74LVC1G17 buffers separate the MCU outputs from Rev29's
`RECEIVER_SESSION_ACTIVE`, `VALIDATED_HEARTBEAT_5V`,
`SESSION_QUALIFIED_PULSE_5V`, and `ARM` nets. Each MCU-side input has a 100 kΩ
pulldown; the fixture models Rev29's existing 10 kΩ pulldown on each buffered
output. This avoids shorts between each MCU output and its buffer while
matching the downstream load. Rev29 therefore sees approximately 0.5 mA at
5 V per asserted output.

PC4 pin 27 observes the persistent Rev29 `qualified_link_good` signal. The
ATmega VCC pins 4 and 6 and AVCC pin 18 are tied to HOT `logic5`, each VCC
branch and AVCC have a local 100 nF bypass, and a 1 µF branch capacitor is
included. AREF has 100 nF to HOT ground. A 16 MHz crystal and 18 pF load
capacitors are included as placeholders; the crystal part, load requirement,
and layout parasitics have not been selected. Unused GPIOs have weak 100 kΩ
pulldowns rather than hard shorts. ADC6/ADC7 are tied to HOT ground.

## Reset circuit and limits

A local `TPS389001DSER` supervisor uses HOT `logic5` at SENSE and existing
Rev29 active-low `rails_ok` at MR. Its open-drain RESET output joins the
ATmega RESET pin and the HOT-side ISP header. A 10 kΩ pullup and 1 MΩ weak
pulldown bias the shared node. The ISP programmer only pulls RESET low, so
there is no push-pull contention.

At the 5.5 V upper rail corner, using the ATmega's minimum 30 kΩ internal
RESET pullup and 1% external resistor corners, the supervisor sinks less
than 0.75 mA: 5.5 V / 9.9 kΩ + 5.5 V / 30 kΩ + 5.5 V / 0.99 MΩ. TI specifies
TPS3890 RESET VOL ≤0.30 V at VDD ≥4.5 V and 3 mA. ATmega RESET VIL is ≤0.1×VCC,
or 0.45 V at VCC=4.5 V, leaving at least 0.15 V low-level margin in the
ATmega's 16 MHz supply range. At VCC=2.7 V, the calculated sink load is below
0.37 mA; TI specifies VOL ≤0.25 V at VDD ≥2.7 V and 2 mA, while ATmega RESET
VIL is ≤0.27 V. That 20 mV margin is narrow. The open-drain path is not
claimed as a valid ATmega reset level below 2.7 V.

For RESET high, the 10 kΩ pullup and 1 MΩ pulldown alone give at least
0.989×VCC at 1% resistor corners, above ATmega RESET VIH=0.9×VCC. The internal
RESET pullup increases this high level. `rails_ok` is an existing Rev29
shared supervisor net; its release threshold, resistor corners, delay, and
interaction with the complete HOT supply ramp must still be verified in the
combined candidate. Keep the MCU BOD fuse enabled and select a threshold
compatible with the actual clock and minimum supply. Fuse programming and
startup behavior below 2.7 V have not been tested.

## Logic-level boundary

The 100 kΩ MCU-side pulldown plus LVC1G17 input leakage load each MCU output
by at most about 60 µA at 5.5 V. Microchip's guaranteed ATmega output-high
point is 4.1 V at VCC=5 V and 20 mA, while the TI Schmitt buffer's maximum
positive-going threshold is 3.33 V at VCC=5.5 V. Those are useful nominal
cross-checks, but the MCU output-high guarantee and buffer threshold do not
share a single specified rail/load corner, so complete input margin still
needs verification.

The four LVC1G17 outputs see the Rev29 10 kΩ pulldown (about 0.55 mA at
5.5 V). TI specifies VOH ≥3.8 V at VCC=4.5 V under a much heavier 32 mA load;
at that operating point the minimum VOH exceeds TPS3431 WDI VIH=0.8×VDD by
0.2 V and exceeds the HCS74 clock input threshold. The datasheet does not
provide a matching guaranteed VOH point for the 10 kΩ load at the maximum
5.5 V rail, where TPS3431 WDI requires 4.4 V. **Thus heartbeat/session-pulse
high-level margin at the full HOT rail range remains open.** ARM output high
margin at the full rail/load corners also needs the downstream receiver's
guaranteed threshold. Do not promote these buffered outputs as full-corner
qualified without those checks.

## What remains outside this fixture

- ATmega firmware, on-wire frame definition, USART baud rate, CRC, EEPROM
  journal, validated-frame heartbeat policy, and fresh-session state machine.
- Producer of a physical source reset/abort signal; existing Rev16 isolation
  allocation has no spare direct channel.
- Complete reset/supply ramp analysis with Rev29 and the actual 5 V source.
- Verified footprints for the ATmega and TPS3890, selected crystal, sourced
  assembly BOM, and KiCad library registration.
- Output VOH/VIH margin closure across all rail and temperature corners.
- Oscillator start-up, external watchdog timeout, total disable latency, and
  any prototype or bench capture. No assembled board was available here.

## Reproduce

From this directory, using the cached offline Atopile environment documented
in [Rev26 build environment](../interface-integration-26/build-environment.md):

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/hot_receiver_fixture.ato:HotReceiverFixture
mkdir -p compiled
cp build/default.net build/default.csv compiled/
python3 audit_netlist.py
```

The build compiles 41 named nets and 41 component instances. The compiled
graph audit checks all ATmega package pins, the four distinct MCU/buffer
boundaries, ISO channel directions, power and ground pins, ISP reset sharing,
and the compiled MPN identity for every IC. Results and hashes are in
[`receipt.json`](receipt.json).

## Primary references

- [Microchip ATmega328P datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf),
  TQFP pinout, DC thresholds, RESET pullup range, reset/BOD.
- [TI TPS3890 datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf),
  SENSE/MR behavior, open-drain RESET VOL, POR, and CT timing.
- [TI SN74LVC1G17 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf),
  Schmitt thresholds, leakage, and output VOH limits.
- [TI ISO7741 datasheet](https://www.ti.com/lit/ds/symlink/iso7741.pdf),
  channel direction and package pinout.
