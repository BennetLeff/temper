# Protection chain closeout: OVP-01 retune, BusDischarge resize, fault-tree capacity

**Date:** 2026-07-27
**Commits:** `8fe11824` (OVP-01 retune), `26329b4a` (OVP-01 simulation),
`5484a1fd` (BusDischarge resize), `7826a5d7` (fault-tree third package).

Closes the three open items in `docs/STRATEGY.md`'s protection chain
review. Each item's falsifier, derivation, worst-case analysis, and
UNVERIFIED list are detailed in their own evidence document; this file
summarizes and cross-references them, plus the shared verification run.

---

## 1. OVP-01 fail-open -> re-tuned for half-bus sensing

**Falsifier**: *"195-205V trip with 5-10V hysteresis is unachievable
with E96 1% resistors, given the existing 3x430k/10k sense divider's own
tolerance."* **Partially fired** -- nominal values and the simulation
both pass; the full worst-case corner analysis does NOT fully clear the
trip window (exceeds by ~1.1-1.2V at each end), confirmed by an
exhaustive E96 search finding no combination that closes the gap. Full
detail: `docs/evidence/2026-07-27-ovp01-half-bus-retune.md`.

**Derivation**: `r_ref_top` 1.1k -> **11.8k**, `r_hyst` 287k -> **619k**
(both real, DigiKey-verified Yageo RC0603 1% parts:
`RC0603FR-0711K8L`, `RC0603FR-07619KL`). Closed form:
`V_trip = Vref*(N + Rtop/Rhyst)`, `hysteresis = VCC*Rtop/Rhyst`
(`Rbot` cancels exactly) -- cross-checked against the OLD fail-open
values before use (reproduced 399.85V/385.02V exactly).

**Worst case** (32 corners, every resistor in the path at +/-1%):

| | Nominal | Simulated | Worst case | Window |
|---|---|---|---|---|
| Trip | 199.94 V | 200.03 V | **193.9 - 206.2 V** | 195-205 V |
| Hysteresis | 6.88 V | 6.83 V | **6.74 - 7.02 V** | 5-10 V |

Hysteresis clears with margin; trip does not fully clear (reported, not
hidden -- the chosen E96 pair minimizes the worst-case excursion, the
best achievable, not a value picked to pass a nominal-only check).

**Simulation**: `simulation/harness/run_ovp01_sim.py` (ngspice,
`TLV3201_ngspice.lib`, `calibrated: false`), deterministic across 5
identical runs. Evidence: `docs/evidence/2026-07-27-ovp01-trip-point-sim.json`.

**Known limitation** (stated, not fixed): sensing only `dc_bus_plus` is
blind to bus *imbalance* -- one half over-volting while the other
under-volts such that `dc_bus_plus` alone never crosses the trip point.
Fixing this needs a `dc_bus_minus`-referenced sense, a second SELV/HV
domain-crossing problem not taken on here.

**Module docstring**: the false "senses the full bus" reasoning is kept
verbatim, marked SUPERSEDED, not deleted.

---

## 2. BusDischarge fails at capacitor tolerance -> resized

**Falsifier**: *"No E-series 5W wirewound resistor value clears BOTH the
capacitor's +20% tolerance AND the resistor's own tolerance
simultaneously, while keeping dissipation under the 5W rating."* **Did
not fire.** Full detail:
`docs/evidence/2026-07-27-busdischarge-tolerance-retune.md`.

**Derivation**: `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` SS5.1's own
capacitor-tolerance-only answer (~8.6k/string, 2x 4.3k) was evaluated and
**rejected**: stacked with the resistor's own +/-5% tolerance, it gives
62.8s -- failing the <60s target the same way the original 9.4k design
did. **3.9k/string (7.8k total) clears both stacked** (56.9s, ~3.1s
margin).

| R per string | t at C+20% only | t at C+20% AND R+5% (stacked) | Verdict |
|---|---|---|---|
| 9.4k (2x 4.7k, prior) | 65.35s | -- | FAILS |
| 8.6k (2x 4.3k) | 59.79s | 62.78s | FAILS once stacked |
| **7.8k (2x 3.9k, chosen)** | 54.23s | **56.94s** | **PASSES** |

**Dissipation**: 1.54W -> 1.85W per resistor (37% of the 5W rating,
comfortable margin retained; this figure is the peak, since dissipation
only falls as the bus discharges). **Relay contact stress**: break
current 18mA -> 21.8mA, still ~5% of the Ag arc-sustain threshold; the
out-of-catalog 170VDC break conclusion and RC snubber sizing are
unchanged (both independent of string resistance).

**Real MPN**: `AC05000003901JAC00` (Vishay AC05, 3.9k, +/-5%, 5W) --
confirmed exact-match, active/orderable via a live DigiKey product
search fetch. Same family/footprint as the prior 4.7k part.

**Side fix**: `p_dis_resistor`'s sizing assertion previously hardcoded
`9.4kohm`; rewritten to reference `r_dis1a.value + r_dis1b.value`
directly so it cannot go stale across a future resistor-value change --
the same class of bug found and fixed in OVPComparator's trip-point
assert (see item 1).

---

## 3. Fault tree had no capacity -> third OR package added

**Falsifier**: *"Adding a third SN74HC4075 package as a single merge
point does not create reachable SET-path capacity, because
capacity_budget_gate.py's reachability model requires a gate's own
output to lead to the SET pin."* **Did not fire.** Full detail:
`docs/evidence/2026-07-27-fault-tree-capacity-expansion.md`.

**What changed**: added `fault_or3` (third `SN74HC4075DR`, same
already-used real MPN). gate1 aggregates new sources (UVL-02 wired;
one input reserved-but-unwired for OCP-02; one spare); gate2 merges that
with the existing 7-source SET bus and now drives `latch.A1`. gate3 is
unused headroom. **UVL-02's fault is wired** (was on a test point only;
the test point is retained alongside the functional connection).
**OCP-02 is NOT wired** -- `SecondaryOCPComparator` stays
un-instantiated; its INA240 shunt in `DC_BUS_RTN` sits at ~170V common
mode against the part's -4V to +80V input range, an unresolved sensing-
domain problem this change does not fix.

**Capacity, before/after** (`scripts/capacity_budget_gate.py`):

| | Before | After |
|---|---|---|
| Packages inspected | 2 | 3 |
| SET-path inputs evaluated | 18 | 27 |
| **AVAILABLE** | **0** | **3** |
| UNUSABLE | 18 | 24 |
| OCCUPIED (groups) | 11 | 14 |
| Gate exit code | 0 | 0 |

The gate's exit code was 0 both before and after (it only fails on a
wired-to-a-dead-gate defect, never present here) -- the load-bearing
number is `AVAILABLE`: 0 -> 3.

**Propagation delay vs. OCP-01's <1us budget** (real SN74HC4075/SN74HC00
datasheet worst-case delays, commercial temp range, 2V column used as a
conservative bound since neither part is characterized at 3.3V):

| | Gates (OR/NAND) | Worst-case logic delay | Total (+detection+UCC21550) | Margin to 1us |
|---|---|---|---|---|
| Before | 3 OR + 2 NAND | 605 ns | 686 ns | 314 ns (31.4%) |
| **After** | 4 OR + 2 NAND | 730 ns | **811 ns** | **189 ns (18.9%)** |

Margin shrinks from 31.4% to 18.9% but stays comfortably positive. Also
found: `SAFETY_INTERLOCK_DESIGN.md`'s existing lumped 50ns logic budget
undercounts the real gate depth (5 gates already existed before this
change, not the ~2 the lumped model assumes) -- a pre-existing
documentation gap, noted but out of scope to fix here.

---

## Shared verification (all three items, run at final HEAD)

```
make netlist                        -> 76 assertions PASSED, 0 FAILED
scripts/check_domain_partition.py   -> exit 0: 0 domain crossings,
                                        0 isolator-barrier breaches,
                                        0 protective-impedance chain
                                        defects (162->165 nets,
                                        169->170 components)
scripts/capacity_budget_gate.py     -> exit 0: AVAILABLE SET-path
                                        inputs 0 -> 3 (0 defects,
                                        both before and after)
```

**No new part introduced a domain crossing**: `fault_or3` is a 3.3V,
`power_3v3`-only logic package with no HV-side connection; the
domain-partition gate's crossing count is unchanged (0 both before and
after) and its net/component counts moved only by the amount this one
part and its wiring add.

## UNVERIFIED (consolidated from all three items)

- `RC0603FR-0711K8L` (11.8k), `RC0603FR-07619KL` (619k),
  `AC05000003901JAC00` (3.9k) -- all confirmed real, active, exact-match
  parts via live DigiKey product searches during this session. Stock
  levels and lead times observed at fetch time may change.
- TLV3201's comparator output swing is assumed rail-to-rail 0-VCC in the
  OVP-01 closed-form derivation (carried over from the module's own
  pre-existing convention, not independently re-verified against the
  datasheet's VOL/VOH at 3.3V).
- Neither SN74HC4075 nor SN74HC00 is characterized at exactly VCC=3.3V;
  the propagation-delay margin uses the 2V datasheet column as a
  conservative upper bound, not a measured or interpolated 3.3V value.
- Propagation delay for OCP-01's comparator stage (TLV3201) remains
  unmeasured (no timing model in the ngspice library) -- unchanged from
  the pre-existing state, outside this task's scope.
- `SAFETY_INTERLOCK_DESIGN.md`'s lumped timing model was found stale
  (undercounts real gate depth) but not corrected -- flagged, not fixed,
  consistent with this task's `elec/src/*.ato`-only scope.
- Aging/endurance drift of the bus electrolytic capacitor is not modeled
  in the BusDischarge analysis (same pre-existing caveat the capacitance
  derivation document already carries).
