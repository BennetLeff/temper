# Rev37: ESP-only permit-blanking experiment

**Build decision: hold the mains-connected ESP-only board.** This experiment
tests a specific change to Rev36, not a released power-entry circuit.

## Circuit question

Rev36 proposed using the HOT TPS3890 rail supervisors as both a blanking
qualifier and the reverse HOT_HEALTH signal. Holding their MR input low while
HOT PERMIT is low would restart blanking after a PERMIT wire break. It would
also hold HOT_HEALTH low during normal OFF, so a source latch that requires
HOT_HEALTH before raising PERMIT could never start.

Rev37 tests a **separate permit-blanking supervisor**. Its MR is low for as
long as the HOT receiver sees PERMIT low; its RESET holds HOT_READY cleared
until CT completes after PERMIT returns. Reverse HOT_HEALTH is derived from
independent raw HOT rail/fault status and can be high in normal OFF. A second
reverse isolator returns the physical HOT PERMIT level. A SELV latch remembers
that it saw PERMIT high and then holds source authorization clear if the
readback falls. Its seen bit clears only on an explicit session-reset input
or source-health loss. The returned HOT health is now ANDed with external
SOURCE_HEALTH before clearing the source latch. The TPS3890 open-drain RESET
has an explicit pull-up. The Atopile fixture under `elec/` compiles to 30 parts;
`audit.rs` checks the critical pin joins and rejects a PERMIT-return miswire.
This is connectivity evidence, not a power-stage schematic or safety proof.
The separate [portable source-policy prototype](firmware-policy/README.md)
passes 11 host tests for reset lockout, physical readbacks, watchdog service
through the HOT blanking wait, and one-step reset/REARM/ARM requests. It is not
integrated with the fixture or ESP-IDF.

## Counterexample that remains

Independent raw HOT_HEALTH alone does not report a broken HOT PERMIT
conductor. If that conductor opens while RUN is high, the HOT receiver clears
RUN and HOT_READY and starts blanking, but a source latch **without physical
HOT PERMIT readback** can remain high. The wire may reconnect with source
authorization still present. A delayed old HOT_REARM edge arriving **after**
blanking can then set HOT_READY, and a reconnecting ARM edge can restore RUN
without a new local press.

`model.rs` reproduces that **raw-health-only negative control** with an
illustrative 229 ms blanking interval. It also shows why a returned and
latched indication of the wire break blocks the sequence. Rev37 now has that
feedback pin path, but the model assumes it is captured reliably. Neither the
event model nor the compiled netlist proves its minimum pulse width,
power-on state, or response across partial-power and fault corners.
Another negative-control test shows that a HOT fault short enough to miss both
the timer's MR qualification and the source-health capture can allow stale
REARM and ARM edges to restore RUN. The fixture has no retained HOT-fault
inhibit for that case.

```sh
rustc --edition=2021 --test \
  zapote/power-entry/passive-reva/protection/interface-hardware-only-37/model.rs \
  -o /private/tmp/interface-hardware-only-37-tests
/private/tmp/interface-hardware-only-37-tests
```

The Atopile 0.2.69 build generates `build/default.net` from `ato.yaml`.
From this directory, build and run the connectivity audit with:

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache \
UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
/Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 \
  --from atopile==0.2.69 ato --non-interactive build \
  elec/src/esp_only_hot_receiver.ato:EspOnlyHotReceiver
rustc --edition=2021 audit.rs -o /private/tmp/temper37-audit
/private/tmp/temper37-audit
```

The audit reports 30 instances and rejects a deliberately miswired reverse
PERMIT pin. It cannot verify timing, default levels on partial power, or the
external fault and source-health producers.

The 229 ms is conditional on a capacitor with *guaranteed effective* minimum
264 nF: `0.264 µF × 1.17 V / 1.35 µA = 228.8 ms`. No capacitor with that
effective minimum has been selected. TI requires MR low for at least 1 µs to
assert RESET. The source TPS3431's 1 nF watchdog table gives 144.98 ms maximum
**with an ideal capacitor**. These numbers alone do not bound the time at
which ESP firmware can issue an old rearm edge. [TPS3890](https://www.ti.com/lit/ds/symlink/tps3890.pdf),
[TPS3431](https://www.ti.com/lit/ds/symlink/tps3431.pdf).

## Decision gate

The compiled return path is a concrete improvement, but the following remain
open before a mains-connected build:

1. Prove the physical PERMIT-readback low pulse reaches the source HCS74 and
   satisfies its asynchronous-clear timing. Verify power-on reset and every
   partial-power state of the two source latch bits. A retained-low
   SOURCE_SESSION_RESET_N must hold source PERMIT clear, and its driver must
   have a specified reset/default state.
2. Join the fixture to the actual source watchdog, HOT faults and gate-disable
   path. A HOT fault shorter than the TPS3890's 1 µs minimum MR-low pulse can
   clear HOT_READY/RUN without restarting the timer. An old REARM and ARM edge
   could then set them again while source PERMIT remains high. Add a retained
   hardware fault inhibit that requires a fresh start, or prove a guaranteed
   MR-low stretch for every fault. Bound readback propagation, watchdog
   timeout, and current cessation.
3. Select a CT capacitor with guaranteed effective capacitance and calculate
   both minimum and maximum timer delays. Bound all firmware and isolator paths
   that could deliver an old HOT_REARM or ARM edge. Integrate and test the ESP
   GPIO driver, including CPU-only reset and task preemption.
   The source policy's `hot_permit_delay_elapsed` is a local timer input, not
   physical feedback from the HOT TPS3890; its maximum-delay qualification
   is still a driver obligation.
4. Validate the joined low-voltage circuit with fault injection before a
   power-entry PCB or mains test. The 30-part fixture omits the PFC detector,
   AUX clamp, gate driver, source POR and native board implementation.

Until those checks pass, this work neither approves the ESP-only board nor
proves an ATmega is necessary.
