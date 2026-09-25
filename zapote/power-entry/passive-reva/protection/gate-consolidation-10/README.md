# Gate/restart consolidation: shared supervisor reset

2026-09-22. **One isolated candidate compiles to 128 instances, down from
131.** Both versions pass the same thirteen nominal fault/supply scenarios
and reject the same two negative controls. A separate output-node experiment
checks each supervisor independently. Retain this as a comparison candidate;
the canonical Rev09 source and PCB are unchanged.

This is a three-part simplification of rail aggregation. It does not remove
a protection function or establish that 128 is the finished assembly count.
The [supply/control contract](../../../../../docs/evidence/2026-09-22-power-entry-interface-contract/README.md)
still has open rail, command and physical qualification requirements.

## Circuit change

Both TPS389001 supervisors already use logic5 and have open-drain RESET
outputs. Tie their RESET pins together at rails_ok, retain one 10 kΩ pullup
to **logic5**, and retain the 100 kΩ rails_ok pulldown. Either supervisor
can hold the node low. It rises only when both have released after their
individual qualification delays.

| Instance | Action |
|---|---|
| protection.reset_and | Remove SN74LVC1G08 aggregation gate |
| protection.reset_and_bypass | Remove its 100 nF bypass |
| protection.reset_pull_logic | Remove duplicate 10 kΩ pullup |
| protection.reset_pull_aux | Retain as shared 10 kΩ pullup; p2 moves to rails_ok |
| protection.rail_pd | Retain 100 kΩ to HOT0 |
| sup_logic.RESET, sup_aux.RESET | Both connect directly to rails_ok |

Both supervisor dividers/timers, fast AUX comparator, detector aggregation,
retained latch, ARM/PERMIT buffers, final enable AND, BSS138 disable interface,
driver, gate resistors and two-transistor controller standby remain.
The retained enable AND is a different instance from the removed reset AND.

[Compiled inventory delta](component-delta.json): RevB 79→76, block D 53→50,
integrated candidate 131→128. Exactly the three instances above disappeared;
there are no additions or attribute changes among retained components.
[Candidate source](source-candidate/elec/src/power_entry_f2_shutdown_revb.ato),
[export](source-candidate/resolved-components.json),
[netlist](source-candidate/build/default.net).

The exported rails_ok net contains exactly U33.6 (logic RESET), U34.6 (AUX
RESET), U45.2 (shared pullup), U46.1 (pulldown), and U29.10 (health.B2).
U45.1 connects to logic5 and U46.2 to control_gnd. Part/pin identity was
checked against individual ATO declarations: Atopile's shared library metadata
is not a manufacturing authority.

## Electrical argument and limits

RESET is low-impedance while asserted and high-impedance after recovery and
delay. TI specifies 10 kΩ–1 MΩ pullups, output leakage and load-dependent VOL.
The selected topology uses compatible open-drain outputs; it must not be
generalized to the push-pull comparator outputs. At VDD≥4.5 V, TPS3890 lists
VOL≤0.3 V at 3 mA. Our nominal pullup draws about 0.5 mA when asserted at 5 V.
RESET behavior is undefined below the device's power-on-reset voltage.
[TPS3890 datasheet](https://www.ti.com/lit/ds/symlink/tps3890.pdf), §§6.5, 8.3.3, 8.4.

At nominal 5 V with both outputs released, rails_ok is 5×100/110 = 4.545 V
before leakage. At the HCS21's specified 4.5 V supply test point, the same
divider gives 4.091 V versus its 3.15 V maximum rising threshold; asserted
VOL≤0.3 V is below its 0.9 V minimum falling threshold. Those are point
checks, not a guaranteed threshold interpolation across the unfinished RUN
envelope. Include resistor tolerance, leakage, node capacitance and actual
supply corners in final selection. The HCS input is Schmitt-triggered.
[SN74HCS21 datasheet](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf), §§6.3–6.5.

The original rails_ok was a driven gate output, not two parallel pullups.
The candidate changes its source impedance to approximately 10 kΩ || 100 kΩ
and adds an RC-dependent release edge. It also removes the aggregation gate's
Ioff boundary. Its pullup introduces no independent powered rail, but that
does not prove the complete injection/brownout behavior benign. Both versions
still require supply-order and intermediate-voltage qualification.

## Comparison evidence

The baseline copies the existing shutdown-04 controller and Rust extractor
without changing their behavior. The candidate replaces only its abstract
rails_ok generator with two open-drain switches, the shared pullup/pulldown,
and node capacitance. Assumptions are Ron=100 Ω, Roff=1 TΩ, total C=10 pF.
These are authored model values, not a vendor transistor model or maximum
capacitance bound. The model retains inherited supervisor timing and
below-supply reset assumptions.

| Check | Result |
|---|---|
| Atopile 0.2.69 build and resolved export | Completed; 128 instances |
| Baseline loaded-gate suite | 13 PASS; detector-bypass and slow-detector negative controls FAIL as expected |
| Candidate loaded-gate suite | Same verdicts using unchanged Rust acceptance function |
| Rust extractor self-tests | 4 passed, including invalid/truncated traces and re-arm-before-edge rejection |
| Added PERMIT loss/return observation, both versions | Gate falls; Q stays low after PERMIT returns with ARM held high; fresh ARM restores gate |
| Shared RESET node bench | Both outputs can independently hold rails_ok low |
| Deliberately disconnected AUX RESET | rails_ok rises incorrectly while AUX reset is asserted; direct bench exposes the defect |

The fifteen-case suite covers four separate detector channels, both rail
orders, either rail absent, ramps, each rail loss/return, a short AUX loss,
startup ARM held high, fresh re-arm and the two negative controls. Full trace
span and ≤100 ns sample-gap checks remain enabled; runs use the inherited
10 ns requested step and 650 µs duration.
[Baseline results](baseline/traces/summary.csv),
[candidate results](candidate/traces/summary.csv),
[extractor tests](extractor-tests.txt).

Absolute-OV and mismatch threshold-to-loaded-gate observations remain
0.748899 µs and 1.535580 µs respectively. One logic-dropout fault timestamp
differs by 0.000013 µs, without changing the verdict; do not infer a meaningful
speed difference from it. The inherited 2 µs screen is a nominal experiment
criterion, not a newly justified hardware timing limit.

The additional PERMIT stimulus drops at 240 µs and returns at 300 µs while
ARM stays high until 550 µs; the fresh edge is at 560 µs. Both versions show
14.982 V gate before loss, ≤34.49 µV in the 242–299 µs fault window, Q=0
through the 302–550 µs recovery window, and 14.982 V after fresh ARM.
These are ngspice measurements inspected by the parent, not additional cases
silently inserted into the fifteen-case Rust verdict set.
[Baseline log](baseline/permit-loss/run.log),
[candidate log](candidate/permit-loss/run.log).

The isolated RESET bench gives 24.86 mV with both outputs asserted, 49.46 mV
with either alone, and 4.545 V with both released. With the AUX output wire
deliberately removed, AUX-only assertion instead reads 4.545 V. This matters
because fast AUX protection or the fixture's explicit logic-rail gate could
mask a faulty aggregation connection in a full scenario.
[Bench circuit](reset-bench/shared-reset.cir),
[measurements](reset-bench/shared-reset.log),
[negative control](reset-bench/open-aux-negative.log).

## Remaining work and decision

**Keep this candidate; do not adopt it as qualified protection yet.** The
count reduction and nominal behavior comparison are complete for this bounded
unit. Larger reductions need their own comparison, not inference from this one.

- Raw ARM/PERMIT disconnect defaults and AUX overvoltage handling remain
  shared baseline gaps. The candidate does not claim to fix them; adding their
  eventual implementation can increase the count.
- The loaded-gate fixture does not include the UCC28180 VSENSE standby
  network, actual system command crossing, thermal behavior or power plant.
  Standby wiring is retained, but dynamic standby/restart was not verified here.
- Intermediate logic voltage, output leakage at partial power, true output
  capacitance, tolerance, noise, rail-dip requirements and loaded silicon
  behavior remain unqualified. No powered hardware work occurred.
- Build warnings for existing generic passives/missing MPNs remain. The
  source export is a topology experiment, not a purchase-ready BOM.

Next resolve the raw command receiver defaults and upper AUX fault response
in one interface revision, then compare it with this 128-instance candidate.
Keep the full-converter and PCB adoption work downstream of those decisions.

## Reproduction and provenance

[Input identity](input-identity.json), [commands](commands.md) and
[run receipt](receipt.json) bind the baseline source, fixture, tools and new
artifacts. Raw traces and simulator logs are retained under each variant;
the parent owns final interpretation. Luna proposed the topology and reviewed
the resulting experiment. The canonical source and the two pre-existing
tracked document edits were preserved. No commit, push or publication occurred.
