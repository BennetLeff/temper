# Source and model boundary

The source is `elec/src/power_entry_f2_shutdown.ato:PowerEntryF2Shutdown`.
`source-02` is its authoritative Atopile export; `compiled-bridge.json` is the
transported physical-pin graph. `source-01` predates restoration of the1206
gate resistor and is retained only as failed-attempt evidence.

The compiled graph has32 components. The transient experiment includes the
external boost plant and gate load, which are not additional components in
this32-part detector/latch/driver subcircuit.

| Circuit feature | Model representation and limit |
|---|---|
| Each200k+200k+200k+200k+187k upper divider chain | Lumped987k resistance; no individual resistor voltage coefficient or parasitic capacitance |
|200Ω tap,5.62kΩ return,100pF high-tap filter on each bus | Explicit nominal R/C elements; tolerance/offset considered separately by the conditional static screen |
| LM4040A25 with10k bias from aux | Ideal2.5V reference; no startup, dynamic impedance or temperature error model |
| Four TLV3202 channels | Separate healthy-high behavioral comparator outputs; no push-pull outputs tied together; response delay is an authored approximation using a datasheet fixture value |
| SN74HCS21 first gate | Combines four detector outputs |
| SN74HCS21 second gate | Combines detector health, supplied rails_ok, permit and a tied-high input |
| SN74HCS74 first half | D and active-low CLR receive qualified health; PRE inactive; raw ARM edge sets Q; asynchronous fault clear retains OFF until a later valid edge |
| SN74HCS74 unused half | Held in a defined state by compiled source; contributes no modeled active function |
| UCC27624 | Behavioral delay/output model in the base transient; separate unchanged TI manufacturer model exercised in vendor checks |
|10Ω1206 gate resistor and10kΩ gate-source pulldown | Explicit values; effective gate capacitance is authored from typical charge, not an exact ST transistor model |
|2.2kΩ EN pulldown | Physical source default bias; an idealized driven EN in the behavioral model cannot establish its unpowered behavior |
| Four100nF logic bypasses,100nF+1µF driver bypass | Source connectivity verified; ideal model supplies omit impedance and bypass effectiveness |

All interfaces are HOT-referenced. `logic5` and `aux` are fixed ideal supplies.
`rails_ok` is an externally qualified signal, including startup clear hold;
toggling it tests the logic contract, not actual rail ramp, brownout, reset
supervisor, input-clamp or back-power behavior. The source's direct Q→ENA
connection has an unresolved unpowered-state interface concern documented in
the independent circuit review. No physical default-off qualification follows.

The boost plant uses an ideal opening switch for F2, a lumped inductor, a
19.8µF local reservoir, bulk bank, and authored diode/MOS switch surrogates.
It omits fuse arcing, wiring inductance, layout, saturation curves, exact
MOSFET Miller behavior and failed-short devices. Initial current labels are
conditions at time zero; use measured current at F2 opening and at threshold
in the result table when interpreting the fault event.

The static screen reruns the previous2048-corner Rust calculation with the
same authored±0.35% resistor,±8mV offset and20nA/input bias allowances. Those
are conditional design allowances, not newly established TLV3202 assembly
bounds. TLV3202's specified offset/bias conditions, common-mode and supply
rejection, typical hysteresis, the reference and resistor temperature behavior
still require an applicable combined error budget. A transient run at nominal
threshold does not silently incorporate the worst static corner or guarantee
the20mV overdrive used in the comparator's switching fixture.

Independent TI latch and driver checks are described in `vendor/README.md`.
They strengthen the functional comparison but do not turn the behavioral
plant into a manufacturer-qualified assembly model.
