# Isolated running-fault and supply tests

The authoritative controller is `controller.inc`, bound to the final79-part
revision-B source and its `source-07` export. The fixture independently drives
VD and VB, so a closed F2 cannot erase the fault stimulus. These are loaded-gate
logic tests; the separate plant tests measure power-switch current and energy.

Fifteen cases execute:13 positive cases pass, while bypassing the detector and
slowing its response fail the same assertions as ordinary cases. The extractor
requires exactly the expected case set, a 0–650 us trace span, no sampling gap
over 100 ns, valid columns and finite values, and the expected control events.
Negative-control names do not force a FAIL result.

Each of the four detector tests first arms a14.98V loaded gate, asserts only the
intended channel, restores healthy voltages while ARM remains high, checks
continued shutdown with healthy rails, then requires a new ARM edge to restore
the gate. Measured **unfiltered bus-voltage threshold to gate below4V**, including
the divider/input filters, is0.748899µs for either absolute OV channel and
1.535580µs for either mismatch channel. These are nominal model observations,
not guaranteed hardware delays at tiny comparator overdrive.

The other positive cases cover both supply orders, either supply continuously
absent,60µs supply ramps, separate logic/aux dropout and return, a1µs aux loss
that clears the latch through the fast comparator, and startup with ARM/PWM
already held high. The final case must remain off even after rails become valid.
The fresh-edge rearm cases demonstrate that the tests can also enable the gate.

The physical resistor/filter networks are explicit, including47pF bus filters,
22kΩ comparator isolation and assumed2pF comparator input capacitances. The
reference is powered by logic5. The supervisor model uses actual294k/100k and
1.03M/100k dividers,47k SENSE resistors, nominal1.157V release threshold,
8µs falling propagation and a **retriggerable132µs** release timer representing
100pF CT plus the internal delay. Hysteresis and timing tolerance are omitted;
this is an authored nominal model, not an exact TPS3890 manufacturer model.
The fast auxiliary comparator uses430k/100k and the independent2.5V reference.

The latch is genuinely edge-triggered; the active-low hardware CLR is inverted
to XSPICE's active-high reset. Enable is RUN AND clear_ok, followed by the small
MOSFET,1kΩ disable pullup, driver surrogate and10Ω loaded-gate path. The unchanged
TI driver model is checked independently under `../vendor/`.

The LVC and latch behavior below their specified operating supplies is modeled
as off/reset. **That assumption is not a datasheet guarantee through brownout.**
The absent-power default, input-current budget and supply sequencing are tested
under the documented models; arbitrary partial-power analog behavior still
needs device characterization before a hardware protection claim.

`attempt-100p/` retains the prior controller and trace: its mismatch filter
response alone exceeded2µs. The accepted source reduces the filter to47pF.
This increases bandwidth and does not establish hardware noise immunity.
`raw/*.debug.tsv` retains actual rails, supervisor timers, divider nodes and
IN−; the extracted trace retains every detector, Q, enable and loaded gate.

Reproduce from the repository root:

```sh
sh zapote/power-entry/passive-reva/protection/f2-shutdown-04/fault-tests/run_cases.sh
```
