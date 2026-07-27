# OVP-01 half-bus retune: derivation, worst-case tolerance, simulation

<!-- provenance: commit=9a4ad578f895dc34a866fd4af4bcc030094e3ec6 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** `elec/src/modules.ato::OVPComparator` (`r_ref_top`, `r_hyst`),
`simulation/harness/run_ovp01_sim.py`,
`simulation/harness/nets/ovp01_trip_point.cir`.

## Falsifier (stated before implementing)

**"195-205V trip with 5-10V hysteresis is unachievable with E96 1%
resistors, given the existing 3x430k/10k sense divider's own tolerance."**

**Partially fired.** Nominal values land comfortably centred in both
windows and the simulated result passes. The **worst-case corner
analysis does NOT fully clear the trip window** (exceeds by ~1.1-1.2V at
each end) for any E96 combination tried, including an exhaustive search
over `r_ref_top`/`r_ref_bot`/`r_hyst`. Hysteresis clears its window with
margin in all cases. See "Worst case" below for the arithmetic. Per the
task's explicit instruction, this is reported rather than hidden or used
to justify weakening the spec.

## Background

`dc_bus_plus` is the +170V half-bus, not 340V, proven independent of any
comment by `modules.ato:579`: `assert c_bus1.voltage_rating >= v_bus_half
* 1.25` (250V >= 212.5V passes against 170V; 250V >= 425V would not
against 340V). The prior `r_ref_top = 1.1k` (`V_ref = 2.973V`) assumed
full-bus sensing and set a ~400V trip at a node that never exceeds
~170V -- fail-open, per `docs/STRATEGY.md` "OVP-01 senses the half-bus and
is now fail-open."

`FUNCTIONAL_TEST_CRITERIA.md` SS2.2 specifies OVP-01 as **390-410V trip,
10-20V hysteresis** on the full bus. Sensing the half-bus at half the
threshold halves both: **195-205V trip, 5-10V hysteresis** at
`dc_bus_plus`.

## Circuit model

```
v_bus --Rtop(=R1+R2+R3=3x430k)-- INP --Rbot(=10k)-- gnd
                                  |
                          Rhyst (to comp.OUT)
VCC(3.3V) --Rreftop-- INN --Rrefbot(=10k)-- gnd
```

Exact closed-form (node equation at INP, solved for V_bus at the instant
`comp.OUT` transitions between 0V and VCC):

```
N          = (Rtop + Rbot) / Rbot                    (divider gain, =130 nominal)
Vref       = VCC * Rrefbot / (Rreftop + Rrefbot)
V_trip     = Vref * (N + Rtop/Rhyst)          [comp.OUT = 0V just before trip]
V_release  = V_trip - VCC * Rtop / Rhyst      [comp.OUT = VCC just before release]
hysteresis = VCC * Rtop / Rhyst               (Rbot cancels exactly)
```

This closed form was cross-checked against the OLD fail-open values
(`Rreftop=1100`, `Rhyst=287000`): predicts trip=399.85V, release=385.02V,
matching the module's own prior inline derivation (399.8V/385.0V)
exactly, confirming the formula before using it for the new values.

## Derivation

Target: trip centred at 200V (mid of 195-205), hysteresis centred at
7.5V (mid of 5-10), with `Rtop = 1,290,000`, `Rbot = 10,000` fixed
(existing sense divider, not retuned here).

```
Rhyst = VCC * Rtop / hyst_target = 3.3 * 1,290,000 / 7.5 = 567,600 -> nearest E96: 562k or 549k
Vref  = V_trip_target / (N + Rtop/Rhyst) = 200 / (130 + 1290000/562000) = 200/132.295 = 1.5117V
Rreftop = VCC*Rrefbot/Vref - Rrefbot = 3.3*10000/1.5117 - 10000 = 11,831.6 -> nearest E96: 11.8k (exact E96 value)
```

With `Rreftop=11.8k`, `Rrefbot=10k`, `Rhyst=619k` (see "Worst case" below
for why 619k over 562k):

```
Vref  = 3.3*10000/(11800+10000) = 1.51376 V
V_trip     = 1.51376 * (130 + 1290000/619000) = 1.51376*132.084 = 199.94 V
hysteresis = 3.3*1290000/619000 = 6.877 V
V_release  = 199.94 - 6.877 = 193.06 V
```

Both centred in their windows (trip: 199.94 of [195,205]; hysteresis:
6.88 of [5,10]).

## Worst case (every resistor independently at +/-1%, all 32 corners)

Resistors in the path: `r_div_top1/2/3` (430k each), `r_div_bot` (10k),
`r_ref_top` (11.8k), `r_ref_bot` (10k), `r_hyst` (619k) -- 5 independent
tolerances, 2^5 = 32 corner combinations swept exhaustively (script in
`/tmp` during this session; reproducible by evaluating the closed form
above at all 32 sign combinations of +/-1%).

| | Nominal | Worst case | Window |
|---|---|---|---|
| Trip | 199.94 V | **193.9 - 206.2 V** | 195-205 V |
| Hysteresis | 6.88 V | **6.74 - 7.02 V** | 5-10 V |

**Hysteresis clears its window comfortably at both corners.** Trip does
**not**: worst case undershoots the 195V floor by ~1.1V and overshoots
the 205V ceiling by ~1.2V.

### Is this fixable by choosing different E96 values?

An exhaustive search over E96 `r_ref_top` (9-15k range), E96 `r_ref_bot`
(8-12k range) and E96 `r_hyst` (300-900k range) -- 17,204 combinations --
found the best achievable worst-case trip excursion is **~1.14V beyond
the window at the tightest fit** (`Rreftop=10.7k, Rrefbot=9.09k,
Rhyst=681k`: trip range 193.87-206.14V). Holding `r_ref_bot=10k` fixed
(matching the existing design convention -- all other bottom resistors in
this divider chain are 10k) and searching only `r_ref_top`/`r_hyst`, the
best fit is the chosen `11.8k`/`619k` pair: worst case
**193.89-206.16V**, excursion +1.16V / -1.11V, both smaller than at the
first-pass `562k` hysteresis value (+1.49V/-0.80V, worse balance).

**Root cause: the irreducible term is the EXISTING sense divider's own
tolerance.** Decomposing the worst-case spread: holding `r_ref_top` and
`r_hyst` at nominal and sweeping only `r_div_top1-3`/`r_div_bot` at
+/-1% already produces ~+/-2% of trip-point spread (from the divider
ratio `N` alone), before the reference divider's own ~+/-1% ratio
tolerance is added. Neither is something this task's scope (`r_ref_top`,
`r_hyst`) can reduce -- the sense divider is fixed elsewhere in the design
and its own 1% parts, cascaded through a ~130x gain, already consume
more of the 10V window's relative tolerance budget (~10/200 = 5%) than
is available once the reference divider's own tolerance is added on top.

**Conclusion: 195-205V trip in full worst-case corner analysis is NOT
achievable with E96 1% resistors given the existing sense-divider
topology.** This is reported per instruction rather than used to justify
picking wider spec windows or looser resistor tolerances not asked for.
The values chosen (`r_ref_top=11.8k`, `r_hyst=619k`) are the E96 pair
that minimizes the worst-case excursion (the best achievable), not a
value picked to make a nominal-only check pass -- and they are a large
improvement over the fail-open prior state (which never trips at all
under any tolerance).

## Simulation

`simulation/harness/run_ovp01_sim.py` (ngspice, `TLV3201_ngspice.lib`,
`calibrated: false`), nominal component values, up-then-down 0-350V ramp
capturing both trip (rising) and release (falling) in one transient:

| | Hand-derived | Simulated |
|---|---|---|
| Trip | 199.94 V | 200.03 V (agreement 0.09 V) |
| Release | 193.06 V | 193.20 V (agreement 0.14 V) |
| Hysteresis | 6.88 V | 6.83 V |

**Deterministic across 5 identical ngspice runs** (byte-identical
stdout). Both trip and release are within the half-bus-equivalent
195-205V / 5-10V windows. Evidence:
`docs/evidence/2026-07-27-ovp01-trip-point-sim.json`.

The simulation uses **nominal** component values only (ngspice does not
sweep tolerance in this harness); the worst-case analysis above is a
separate closed-form/corner calculation, not a SPICE Monte Carlo run.

## Known limitation (stated, not fixed)

Sensing only `dc_bus_plus` (the +170V half relative to the doubler
midpoint) is **blind to bus imbalance**: a fault mode where one half-bus
over-volts while the other under-volts such that `dc_bus_plus` alone
never crosses the trip point even though the plus-to-minus differential
is abnormal. Detecting that requires a reference at `dc_bus_minus`
(-170V), a second SELV/HV domain-crossing problem not taken on here.

## UNVERIFIED

- `r_ref_top` (`RC0603FR-0711K8L`, 11.8k) and `r_hyst`
  (`RC0603FR-07619KL`, 619k) MPNs confirmed as real, active, orderable
  parts via DigiKey product search (exact match, both Yageo RC0603 1%
  0603 parts) -- not fabricated.
- TLV3201's actual comparator output swing (assumed rail-to-rail 0-VCC in
  the closed-form derivation, matching the pre-existing convention this
  module's own prior comment already used) is not independently verified
  against the datasheet's actual VOL/VOH at 3.3V -- carried over from the
  existing design's own assumption, not newly introduced here.
- Propagation delay remains unmeasured (`TLV3201_ngspice.lib` declares no
  timing model), unchanged from the pre-existing state.
