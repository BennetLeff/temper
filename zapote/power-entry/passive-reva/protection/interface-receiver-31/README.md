# Rev31 HOT receiver hardware candidate

Status: **pin-level candidate and interface contract; firmware and native electrical fixture remain open.** This directory adds no product schematic or PCB and changes no existing source. The candidate supplies the three HOT-side receiver outputs Rev29 leaves open, plus the retained ARM edge, while preserving the Rev13 fresh-session contract.

## Selected MCU

| Item | Candidate |
|---|---|
| Manufacturer / MPN | Microchip `ATMEGA328P-AU` |
| Package | 32-lead TQFP, 7 × 7 mm |
| HOT supply | `logic5`; at 5 V, the 16 MHz crystal speed is within the datasheet's operating limits |
| Nonvolatile memory | 32 KiB ISP Flash, 1 KiB EEPROM |
| Serial peripheral | One hardware USART for command receive and response transmit |
| PCBParts local catalog | JLC search returned LCSC `C14877`, `ATMEGA328P-AU`, TQFP-32 (7×7), preferred catalog, stock 40,553 at query time (2026-09-22). This is catalog evidence, not live stock or assembly commitment. |

Microchip documents the supply/speed limits, 32 KiB Flash, EEPROM, USART, reset, brown-out, and TQFP pin map in the [ATmega328P datasheet](https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf). A production design still needs package-footprint review, lifecycle and supplier review, and assembly confirmation.

## Pin-level connection proposal

The three forward channels keep their Rev16 meanings: a framed command stream, an independently maintained PERMIT level, and a RELAY_CMD digital input. Only command and response need asynchronous serial; no UART framing is imposed on PERMIT or RELAY_CMD. ISO7741F's HOT outputs are powered from HOT logic5 and directly meet the MCU's HOT-domain input levels.

| MCU signal | TQFP pin | Candidate connection |
|---|---:|---|
| PD0 / RXD | 30 | `HOT_COMMAND_RX` from ISO7741F pin 14; framed command input |
| PD1 / TXD | 31 | `HOT_RESPONSE_TX` to ISO7741F pin 11; challenge/ACK response stream |
| PD2 | 32 | `HOT_PERMIT_RX` from ISO7741F pin 13; maintained active-high permit; any low invalidates before frame processing |
| PD3 | 1 | `HOT_RELAY_CMD` from ISO7741F pin 12; digital relay command input |
| PC0 | 23 | `RECEIVER_SESSION_ACTIVE` to Rev29 watchdog EN; 10 kΩ external pulldown |
| PC1 | 24 | `VALIDATED_HEARTBEAT_5V` to Rev29 TPS3431 WDI; 10 kΩ external pulldown |
| PC2 | 25 | `SESSION_QUALIFIED_PULSE_5V` to Rev29 HCS74 CLK2; 10 kΩ external pulldown |
| PC3 | 26 | `ARM` to retained HOT ARM input buffer; 10 kΩ external pulldown |
| PC4 | 27 | `HOT_LINK_GOOD_OBSERVED` from Rev29 retained HCS74 Q2 `qualified_link_good`; low is persistent evidence that watchdog/async clear removed the latch state |
| PC6 / RESET | 29 | `/RESET`; active-low HOT `rails_ok` supervisor node and ISP header, with the pull-up change and limits below |
| PB6 / XTAL1 | 7 | 16 MHz crystal |
| PB7 / XTAL2 | 8 | 16 MHz crystal |
| VCC | 4, 6 | Both pins to HOT `logic5` |
| GND | 3, 5 | Both pins to HOT ground |
| AVCC | 18 | To `logic5`, locally bypassed; don't leave unpowered even if ADC is unused |
| AREF | 20 | 100 nF to HOT ground if ADC reference is unused; do not drive externally |
| PB3 / MOSI, PB4 / MISO, PB5 / SCK | 15 / 16 / 17 | 6-pin ISP programming header |

The table's TQFP pin numbers follow Microchip's datasheet figure. Use an ISP header carrying RESET, MOSI, MISO, SCK, `logic5`, and HOT ground. The programmer must use the HOT domain and must not bridge SELV and HOT grounds. Configure the internal watchdog and brown-out fuse for the valid 5 V domain. **Do not treat the existing Rev29 10 kΩ pull-up plus 100 kΩ pull-down as a proven AVR reset release:** nominal `RESET=0.909×logic5` is barely above the ATmega328P's `VIH(min)=0.9×VCC` and has no guaranteed tolerance/leakage margin. A candidate improvement is an additional 20 kΩ pull-up from `/RESET` to `logic5` (effective pull-up ≈6.67 kΩ with the existing 10 kΩ); with 5% pull-up and pull-down corners, the high ratio is approximately 0.931×logic5. This keeps reset wired-low and ISP compatible. However, it is **not yet approved**: prove total sink current from every load on shared `rails_ok` at supervisor valid-rail corners, including the AVR internal RESET pull-up and all other shared branches, against TPS3890 VOL/current limits; prove leakage and actual reset threshold corners. If those checks fail, redesign the reset node with a qualified open-drain reset stage/supervisor; do not add a push-pull buffer directly across the ISP RESET line. Until that proof is done, guaranteed startup/reset release is open. Keep all four safety outputs externally pulled low with local 10 kΩ resistors; AVR GPIOs are high impedance during reset. Keep RESET accessible to programming and bench reset.

Rev29 has a direct hardware PERMIT path independent of MCU parsing: the isolated PERMIT signal feeds the HOT health/clear logic and `clear_ok`, which clears the retained RUN latch and gates final enable. A low PERMIT therefore removes authorization even with a stalled receiver. The MCU's PD2 `HOT_PERMIT_RX` observation is additional protocol/session invalidation, not the safety clear path. Route the retained HCS74 Q2 `qualified_link_good` state to PC4. It goes low on watchdog/async clear and stays low until a fresh session-qualified edge, so the MCU can observe a missed short clear pulse after recovering from a halt. Firmware must see Q2 low, then a newly qualified session before it emits the next pulse; high means only that the hardware latch currently records qualified link. A short `watchdog_clear_qualified` pulse alone is not sufficient feedback because firmware may miss it while halted.

Use a 16 MHz crystal and load capacitors selected from the crystal manufacturer's specified load capacitance and the final board parasitics. The source tree has not selected or laid out a crystal. Place a 100 nF ceramic at each VCC/GND pair and AVCC, with short local returns, and a nearby 1 µF bulk capacitor on this MCU supply branch. Validate oscillator start-up and command baud error across voltage and temperature before freezing the wire protocol.

## Rev13 behavior required of firmware

This is a hardware capacity proposal, not a firmware implementation. The receiver firmware must retain the Rev13 behavior in [`interface-handshake-13/command/design.md`](../interface-handshake-13/command/design.md):

1. Restore and advance a persistent monotonic session counter. Commit the new session identity before transmitting its `Challenge`; use a wear-levelled, CRC-protected, power-loss-safe EEPROM journal. Counter exhaustion or invalid journal state fails offline.
2. Require the source's challenge to be newer than its persisted last session and wait for a new local start intent. A held ARM level or replayed request is not fresh intent.
3. Require matching `(session, intent)` across `Request`, `Ack`, and `Start`. Reject stale, mismatched, reordered, or out-of-deadline frames. Duplicate `Request` can repeat the matching `Ack` without extending the fixed deadline.
4. Treat low PERMIT, receiver reset, framing/CRC failure, session mismatch, local health loss, or protocol timeout as offline: immediately deassert `RECEIVER_SESSION_ACTIVE`, heartbeat, session-qualified pulse, and ARM; no automatic session recovery.
5. Generate watchdog WDI edges only when a complete command frame passes framing, integrity, session/sequence, and state-context validation. Replayed/stale frames and periodic timer activity must not feed the watchdog. The heartbeat policy must require continuing safety-relevant peer traffic rather than arbitrary valid noise.
6. Generate one fresh session-qualified rising edge only after a newer session is established, Rev13 idle qualification is complete, and `HOT_LINK_GOOD_OBSERVED` has been observed low since the last fault/reset. Q2 can go high only *after* that edge; require the Q2 feedback to read high before issuing a separate ARM rising edge for the exact matching START. If Q2 remains low, stay offline. Drive both pulse outputs low before a reset/fault and keep them low across reconnect until a new handshake.

Outputs are intended as HOT logic5 levels and drive HOT-side consumers only. Do not connect them directly to Rev13 3.3 V SELV logic. External pulldowns keep them low during MCU reset/high-impedance startup. Their VIH margins are **not yet proven across the complete rail/load corners**: Rev29 TPS3431 WDI requires 0.8×VDD, while the AVR datasheet's quoted VOH test point is at a different rail/load condition; compare guaranteed VOH at the final pull-down load against WDI VIH at maximum VDD before release. Likewise check the HCS74 clock input VIH and ARM receiver thresholds at their worst rail corners. A stuck-high output, corrupted firmware, or permissive parser is not made safe by pulldowns. Rev29's independent external watchdog catches a missing falling WDI edge, but does not prove semantic correctness of firmware-generated frames.

## Failure matrix

| Event / fault | Required observable response | Coverage / open point |
|---|---|---|
| HOT `logic5` absent or below supervisor threshold | `rails_ok` asserts low, MCU `/RESET` asserted; outputs remain low through pulldowns | Reset release ratio and shared-node sink current are unresolved; below-threshold partial-power region also needs review |
| MCU power-on, brown-out, external reset, or internal watchdog reset | Session invalidated; outputs remain externally low until protocol state is reinitialized | Firmware startup and fuse settings unimplemented |
| PERMIT low | Rev29 direct hardware path clears retained RUN/final enable; firmware also invalidates session and outputs | Hardware path is MCU-independent; propagation and input threshold still need integration/bench verification |
| Open/shorted command serial input, bad framing/CRC, stale or replayed message | No qualified pulse, no ARM, no heartbeat feed; deassert session active | Exact serial framing, baud, CRC, and response rules are not specified by Rev13 |
| RELAY_CMD changes unexpectedly | Do not infer a valid frame or feed heartbeat from the digital level; reject action under protocol policy | Relay semantics and timing are outside the Rev13 model |
| Peer traffic stops or receiver CPU hangs | Last heartbeat edge stops; Rev29 TPS3431 times out and clears the HOT latch | Shutdown latency is not selected or qualified; no maximum system latency is specified |
| Firmware free-runs a heartbeat without validated traffic | Forbidden; external watchdog cannot be fed by a periodic background task | Requires code review, tests, and actual firmware fault-injection |
| Heartbeat GPIO stuck high or low | TPS3431 receives no continuing required falling edges; timeout clears latch | Depends on Rev29 watchdog wiring, unresolved output VOH/VIH corner, and timeout choice |
| EEPROM journal torn, CRC-invalid, or counter exhausted | Stay offline; never reuse a session identifier | Journal code and endurance analysis are open |
| Source MCU resets while HOT PERMIT remains electrically stuck high | No independent direct reset indication exists in current 3-forward/1-reverse allocation | Separate source-reset/abort design remains an integration requirement |
| ARM output sticks high or reappears across reconnect | Must not create a new session or fresh edge; require independent latch clear and new protocol authorization | A single MCU output fault is not contained by this receiver candidate |

## Explicitly open

- Rev13 specifies already-decoded logical frames only. On-wire framing, baud, command field encoding, CRC, retry timing, response formatting, and transport settling still need a reviewed specification.
- No AVR firmware, EEPROM journal, native Atopile receiver module, compiler build, or hardware test is included. This MCU is not safety-certified, and this candidate is not a safety case.
- RESET deassertion with the shared supervisor net needs a complete sink-current/tolerance/leakage proof. Direct MCU output VOH against WDI/HCS74/ARM VIH across supply and load corners also remains open; do not release this as a guaranteed electrical interface until closed.
- Output timing, pulse width, supervisor sequencing, power-ramp behavior below valid `logic5`, external watchdog timeout, and total power-stage disable latency remain unqualified. No prototype or bench capture exists.
- The direct source-reset/abort path is not solved here. Sampling ESP32 EN alone misses internal resets while EN remains high; the current isolator allocation has no spare reverse channel.
- JLC catalog results are a dated database snapshot, not a purchase commitment, current-stock guarantee, manufacturability proof, or approved BOM.
