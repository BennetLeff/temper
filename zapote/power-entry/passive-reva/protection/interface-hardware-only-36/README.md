# Rev36: HOT MCU necessity decision experiment

## Verdict

**ATmega is not functionally necessary in the modeled fault contract. An
ESP32-only candidate is viable with HOT-side lockout plus a delayed rearm
qualifier. It is not ready to freeze:** the delay must have a guaranteed
minimum longer than the maximum stale-event path, and the compiled circuit
must close the HOT fault / source watchdog paths. No assembled board has been
tested. The new candidate has a plausible bounded-delay source in the already
selected HOT TPS3890 supervisors, but MR wiring, CT capacitor selection, and
the full timing inequality still need schematic-level verification.

The MCU-independent power-stage functions already have hardware owners:
Rev30 source PERMIT latch, Rev29/35 HOT rail/AUX and RUN latches, and external
watchdogs. The extra ATmega in Rev31/33 supplies the HOT state machine,
transport decoding, challenge/ACK, diagnostics, and HOT outputs. Rev13's
epoch/intent protocol logically rejects stale sessions, but it is not a wire
decoder, built firmware, or timing proof. The ATmega itself has not been
implemented or tested here.

## ESP32-only candidate

This is a concrete *topology hypothesis*, not a compiled schematic:

1. Keep the Rev30/34 SELV source latch and TPS3431 watchdog. Firmware never
   services WDI autonomously. After any reset it withholds WDI through the
   full qualified timeout, observes source PERMIT physically low, invalidates
   old start state, and requires a released-then-pressed local start event.
2. Keep the HOT `RUN` latch and fast local gate-disable path. Reassign the
   second half of the existing `SN74HCS74` from `SESSION_QUALIFIED` to
   `HOT_READY`; Q1 remains RUN, Q2 is cleared low by `/CLR2` on HOT faults,
   PERMIT-low, or invalid rails. Q2 sets only on a HOT_REARM clock when its D
   input, delayed `rails_ok`, is high.
3. Use ISO7741F channel D (HOT IND pin 11 to SELV OUTD pin 6) for HOT_HEALTH
   feedback from the delayed TPS3890 `rails_ok`; HOT_HEALTH goes low on HOT
   fault/rail loss and asynchronously clears source PERMIT. It is deliberately
   not Q2/HOT_READY, because HOT_READY is low during normal OFF and would
   deadlock the source PERMIT latch. The candidate gives up the existing
   `HOT_RESPONSE_TX` channel. Reassign forward channel A (`SOURCE_COMMAND_TX`)
   to HOT_REARM; channels B/C remain PERMIT/relay.
4. Reuse the HOT TPS3890 supervisors' delay as a blanking qualifier. Drive
   their active-low MR from a live HOT fault summary; SENSE continues to
   supervise HOT rails. Their shared RESET/`rails_ok` asserts low during
   faults and remains low for the CT delay after MR and SENSE recover. Q2 D
   is delayed `rails_ok`; HOT_REARM is CLK2. A pulse during fault/blank samples
   D low and leaves Q2 low; a held-high input has no later rising edge. A new
   edge after the delay sets HOT_READY.
5. ESP emits exactly one HOT_REARM pulse per fresh local press. Once
   HOT_HEALTH is high, it sets the SELV PERMIT latch while Q2 remains low,
   emits HOT_REARM, waits the specified logic/isolator settling interval, and
   then emits ARM. Q2-low makes a missed rearm fail off. A HOT_HEALTH falling
   edge cancels the pending intent; firmware never replays a queued rearm.
6. Any HOT fault pulls HOT_HEALTH low through the powered SELV side of the
   reverse isolator and asynchronously clears source PERMIT. Q2/HOT_READY
   remains low after the fault disappears until a new HOT_REARM edge. The
   documented ISO7741F
   default-low behavior on input-side power/signal loss supports this direction
   when SELV output-side power remains present; the unpowered output-side case
   is not claimed.

The sequence avoids the PERMIT-low deadlock because the reverse line reports
HOT_HEALTH, not Q2/HOT_READY: when healthy, it can be high during normal OFF.
Start raises PERMIT first while Q2 remains low, then HOT_REARM sets Q2, and ARM
is sent last. PERMIT-high alone cannot energize RUN. If PERMIT opens while
running, its falling level clears Q1 and Q2; reconnecting PERMIT and ARM cannot
restore Q2. HOT_REARM must be newly issued after the blanking delay. The guard
works only if its minimum reset delay exceeds the complete stale-event and
logic timing bound.

## Decision-critical counterexample

The model intentionally separates events that an idealized single-step
simulation would collapse:

| Relative time | Event | State |
|---:|---|---|
| 399.9 µs | After an earlier lockout, the user presses start; ESP emits HOT_REARM | Source PERMIT and HOT_READY are low; pulse is in flight |
| 400.0 µs | A new HOT fault asserts local lockout | HOT_READY was already low, so the source sees no new falling edge |
| 400.02 µs | HOT health recovers | HOT lockout remains set |
| 400.03 µs | The pre-fault HOT_REARM pulse arrives | One-bit HOT logic accepts it and raises HOT_READY |
| 400.04 µs | ESP continues the pre-fault start sequence | It sets PERMIT and pulses ARM; RUN sets without a post-fault press |

`pre_fault_rearm_pulse_can_authorize_post_fault_start` asserts this case for
the unguarded receiver. The new delayed-qualifier tests exercise the candidate
fix. The simultaneous PERMIT+ARM open/reconnect remains blocked by retained
lockout. These are event-model results under a supplied delay bound, not
analog or board evidence.

### Candidate blanking bound and challenge alternative

The selected TPS3890 already provides the most promising discrete guard: its
RESET output asserts on SENSE undervoltage or active-low MR, then remains low
for the programmed CT delay after both recover. The datasheet specifies
`ICT=0.90..1.35 µA` and `VCT=1.17..1.29 V`; TI's worked example calculates
that a 1.5-nF ±20% CT capacitor guarantees at least 1 ms over -40..125°C.
The Rev29/35 source currently uses 100-pF CTs and ties MR high, so it does not
yet implement this candidate. A provisional 0.33-µF ±20% effective C gives a
conservative CT ramp lower bound of `0.264 µF × 1.17 V / 1.35 µA = 229 ms`
(ignoring the positive nominal offset). This exceeds the selected 1-nF
TPS3431's ideal-capacitance maximum of 145 ms, but only if CT effective
capacitance, MR pulse capture, and the source's maximum stale command latency
are verified. MR must be low for at least 1 µs; direct fault-summary wiring
must guarantee that minimum or add a pulse stretcher. The selected capacitor
also needs a voltage/temperature derating check. See the TPS3890 and TPS3431
datasheets below.

I also assessed a new `SN74LVC1G123` retriggerable monostable. It could stretch
each HOT fault into a blanking interval, but TI's duration-versus-RC curves and
application example are typical; there is no usable guaranteed minimum for the
proposed long RC interval. It is weaker evidence than the TPS3890 CT timing
limits, so Rev36 uses TPS3890 as the candidate and keeps 1G123 as an unqualified
fallback.

Required inequality: `Tblank_min > Tstale_max + Tsetup_margin`. `Tstale_max`
includes the ESP task's worst scheduling delay before HOT_REARM is emitted,
the isolator and input path, and any delayed edge after a source CPU-only
reset. Bound it by the source watchdog maximum plus a verified boot/output
contract; a typical WDI period or an assumed task latency is not enough.
`Tsetup_margin` includes HCS74 clock/D setup, asynchronous preset recovery,
fault propagation, and board-level delay. At 2.5 V the ISO7741 data table
lists max propagation as 21 ns, only one part of this full bound. An MR-low
event must be visible to the TPS3890 and HOT lockout must be asynchronously
preset for every fault class. Every fault must restart the delay. A firmware
delay after seeing HOT_READY low is insufficient when HOT_READY was already
low before the fault.

A toggled one-bit challenge is not a drop-in replacement: one reverse channel
must provide fail-low HOT_READY, and parity can change without guaranteeing an
observable fault-low transition (for example when parity was already low).
Robust challenge echo requires an extra reverse status channel or temporal
encoding, plus an ESP echo and HOT decoder/strobe. The existing three forward
channels are command, PERMIT, relay; the command channel can be reassigned to
HOT_REARM, but a challenge decoder would need additional state/logic. That
approaches the ATmega receiver's complexity. The timer/latch candidate uses
one bit and existing isolation, with a conditional timing proof instead.

## Reset and protocol boundaries

- A static GPIO retained high through an ESP32-S3 CPU-only reset produces no
  continuing WDI falling edges; the SELV/source TPS3431 then clears source
  PERMIT after its maximum timeout. WDI must be a software-only GPIO, not a
  peripheral output. The model's 130-ms value is illustrative.
- If a timer/peripheral continues to generate WDI edges through the CPU-only
  reset, the external watchdog cannot identify the reset and permit stays set.
  Rev32/35 document this counterexample. The ESP-only candidate relies on
  software-only WDI, withheld after reset. It removes the HOT TPS3431's
  validated-peer-frame heartbeat and HOT session diagnostics; if those are
  required, retain a HOT stateful receiver.
- A one-bit ARM waveform cannot distinguish a fresh edge from a replayed
  waveform while the system is armed. Reconnect safety comes from PERMIT-low
  clearing Q2 and the HOT-local delayed rearm qualifier, not from ARM edge
  semantics. The ESP-only candidate drops HOT peer-frame validation and its
  diagnostics; if Rev13 challenge/ACK or validated HOT link health is a
  product requirement, a HOT stateful receiver is required.
- The model has no voltage thresholds, analog ramps, propagation delays,
  minimum latch pulse widths, metastability, or gate/current cessation.
  None of its passes are board-safety evidence.

## Comparison

| | ESP32 + discrete HOT logic | ESP32 + HOT ATmega candidate |
|---|---|---|
| Fault shutdown | Existing source/HOT hardware latches and watchdogs can own it | Same hardware latches remain necessary; MCU does not replace them |
| Fresh start | Wait HOT_HEALTH, raise PERMIT while Q2 low, issue one HOT_REARM, then ARM | Rev13 source/HOT session and fresh intent model; transport and firmware remain unbuilt |
| Reconnect handling | PERMIT-low clears Q1/Q2; reconnect cannot restart RUN until new HOT_REARM; guard blocks in-flight pulse if timing bound holds | Logical stale epoch/intent rejected; physical decoder, pulse timing, reset path and board still unverified |
| Firmware | ESP32 only, with stricter boot/heartbeat/rearm contract | ESP32 plus new HOT MCU firmware, bootloader/fuses, EEPROM session journal and protocol decoder |
| Hardware | Reuses TPS3890/HCS74, changes CT/MR/fault wiring, reassigns command channel to HOT_REARM; removes HOT MCU, HOT TPS3431, crystal, ISP | Adds ATmega, clock/reset/ISP/BOD and uses existing reverse response channel |
| Diagnostics | HOT_HEALTH/HOT_READY only; no HOT frame validation or session diagnostics | HOT can return protocol status, faults, and ACKs |
| Evidence | 20 executable event-contract tests; no compiled no-MCU circuit, source timing bound, or prototype | Rev13 logical tests 21/21; Rev33/35 connectivity only; no product firmware/prototype |

## Reproduction

From the worktree root:

```sh
rustc --edition=2021 --test \
  zapote/power-entry/passive-reva/protection/interface-hardware-only-36/model.rs \
  -o /private/tmp/interface-hardware-only-36-tests
/private/tmp/interface-hardware-only-36-tests
```

Result: **21 passed, 0 failed.** The unguarded test asserts the unsafe
counterexample. Guarded tests pass under an injected blanking minimum; a
negative-control test confirms an edge after the assumed bound is accepted.
This is an event model, not analog simulation.

Relevant source evidence:

- Rev11 one-bit reconnect case: `interface-defaults-11/after/arm_reconnect_high/case.cir`;
  PERMIT and ARM conductors reconnect at 400.001 µs, before the deliberate
  ARM event at 560 µs.
- Rev13 logical session model: `interface-handshake-13/command/design.md` and
  `interface-handshake-13/command/handshake.rs`.
- Rev29 HOT retained-latch/watchdog wiring and limits:
  `interface-integration-29/README.md`.
- Rev30 SELV source latch, Rev32 reset contract, Rev33 HOT MCU interface,
  Rev34 joined source watchdog, Rev35 source-to-HOT compiled join:
  their respective `README.md` files.
- TI ISO7741F datasheet: https://www.ti.com/lit/ds/symlink/iso7741.pdf
- TI TPS3890 datasheet: https://www.ti.com/lit/ds/symlink/tps3890.pdf
- TI TPS3431 datasheet: https://www.ti.com/lit/ds/symlink/tps3431.pdf
- ESP32-S3 datasheet: https://documentation.espressif.com/esp32-s3_datasheet_en.pdf

## Remaining physical blockers

The compiled Rev35 HOT fault signals and MR pins have not been joined into a
non-recursive `HOT_FAULT_EVENT`; the existing MR pins are tied high and do not
currently trigger on every required fault. The model does not instantiate
TPS3890, HCS74, or analog timing. The provisional CT capacitor has no selected
MPN/effective capacitance over bias and temperature. The ESP maximum time from
accepting a button press to producing or abandoning any queued HOT_REARM has
not been bounded against source watchdog maximum timeout. No no-ATmega compiled
schematic or board verifies Q2 reuse, feedback direction, MR pulse capture, or
rail ramp. In particular, a PERMIT conductor opening at HOT clears Q2, but
HOT_HEALTH/`rails_ok` remains high unless that falling edge also creates an
MR fault-event pulse. A stale HOT_REARM could otherwise set Q2 before PERMIT
and ARM reconnect, restoring RUN. PERMIT-low must create an MR pulse of at
least 1 µs and restart the blank interval, while normal OFF must not hold MR
low. No pulse generator or net implementing this behavior exists in the
candidate. This is a concrete reopen race, not a timing detail. The topology
also removes the HOT validated-peer-frame watchdog and diagnostics. More
logical tests cannot resolve these.

Thus the verdict is **unresolved: ATmega is not shown necessary, but it is not
yet safe to drop it.** The candidate has a coherent PERMIT/HOT_HEALTH/Q2
sequence if the circuit matches the topology above. Resolve fault wiring,
timer and source-output bounds, plus whether HOT link supervision is required;
then compile and test the circuit. If a source-approved edge can arrive after
the HOT delay or some required fault cannot assert MR for at least 1 µs, retain
a HOT stateful receiver or add a challenge interface.

## Exact next decision experiment

Compile the HOT fault-summary -> TPS3890 MR -> `rails_ok` delay -> HCS74 lockout
gate, changing CT from 100 pF to a selected low-leakage capacitor with
guaranteed minimum effective C. Prove the MR pulse-width requirement for every
fault class and compute `Tblank_min > Tstale_max + Tsetup_margin` using the
datasheet min/max limits, source watchdog max, ESP task bound, isolator, and
latch setup/recovery timings. Sweep HOT fault and rail brownout across the
entire rearm pulse and both PERMIT/ARM conductor reconnect orders. If that
inequality is proven and the compiled connectivity passes, the ATmega can be
removed from the candidate. If any stale output can occur after blanking or
the HOT fault cannot trigger MR, use a HOT stateful receiver or add a challenge
interface. This is the remaining decision gate.
