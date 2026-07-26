# Temper Project Strategy

**Version:** 3.0
**Date:** 2026-07-25
**Supersedes:** v2.0 (same day), v1.0 (2026-06-22) and its "Strategy-Level
Move Set".

How we work lives in [`METHODOLOGY.md`](./METHODOLOGY.md) and should rarely
change. This document holds what we are building and where we honestly are. It
churns by design.

---

## Bottom line

**The critical path is design completion, not tooling. The board cannot be
fabricated, and the router is not what is stopping it.**

This reverses the premise the project has run on for roughly a month. The
evidence, all gathered 2026-07-25 and detailed below:

| | |
|---|---|
| **Protection gates** | Of seven: **3 fixed** (OCP-01, THM-01, THM-02), **OVP-01 fail-open** (senses the half-bus, can never trip), UVL-02 designed but its fault has nowhere to connect, OCP-02 blocked on sensing domain, UVL-01 vendor-internal. **0 validated on hardware** |
| **IGBT desaturation protection** | **Does not exist.** 19 BOM lines cost it; `grep -ni desat elec/src/*.ato` returns nothing |
| **BOM** | Unusable in both directions — 35 lines costed with no circuit, ~75 wired components uncosted |
| **Router** | ~79% path-finding, but its output carries ~120 shorts and 499 clearance violations |
| **Router's own DRC** | Never ran; when enabled, the first check **crashes** on current data |
| **Fixed today** | OCP-01 50.12 A (was 37.6), THM-01 84.91 °C (was 99.5), board outline, 10 dead CI gates |

The router was never the bottleneck. A month went into routing a board whose
overcurrent protection trips 17% low, whose thermal shutdown is 14.5 °C high,
which has no secondary OCP, no coil thermal sensing, and no desaturation
protection — while its BOM bills for a desat circuit that was never designed
and omits the bus discharge that was.

**All of it was found in one day, with tools already in the repository**: four
ngspice runs against models sitting unused since they were committed, and a
grep of the BOM against the source. None of it required the router to work.

### What this changes

1. **Fabrication is not the next milestone.** "Close one loop, fab a board"
   — the model this document carried this morning — assumed a roughly sound
   design. That assumption is falsified. Ordering this board would produce
   hardware missing three protection mechanisms.
2. **Simulation, not place-and-route, is where the pipeline investment pays.**
   Four SPICE runs found more real defects than a month of router work. For the
   long-term goal of building kitchen appliances quickly, a
   simulation-in-the-loop design-verification layer is worth more than
   incremental autorouter quality — and it is far less built.
3. **The verification layer is not trustworthy yet, but it is now honest.**
   Ten dead CI gates, five vacuous production gates, and a DRC oracle with ±11
   noise were found and mostly fixed. That work is done; continuing it advances
   no gate.

### Recommended sequence

1. ~~**Design review of the protection chain**~~ — **done 2026-07-25**
   (`docs/hardware/PROTECTION_CHAIN_REVIEW.md`). OCP-01 and THM-01 are fixed
   and verified in simulation. Still outstanding from it: OVP-01's divider
   reference is a design decision; OCP-02, THM-02 and DESAT need circuits
   designed; `temper:CST3015` footprint must be drawn before fabrication.
2. **Reconcile the BOM against the source**, both directions.
3. **Extend the SPICE harness** to the power stage — a ZVS-margin sweep across
   the pan-load envelope is the highest-value remaining simulation
   (`METHODOLOGY.md` §11) and the models are already present.
4. **Then** return to routing quality: the ~120 shorts, and repairing the
   manufacturing DRC checks so they run against `RoutePath3D`.

Nothing in steps 1–2 is a coding task, and nothing in them should be delegated
to an agent. They are design and procurement decisions.

---

## What we are building

A **domain-specific place-and-route and verification system for mains-connected
kitchen-appliance power electronics.** The Temper induction cooker is instance
#1 and the source of ground truth — not the terminal goal.

Two artifacts compound across future appliances:

1. **The check corpus** — encoded IEC 60335-1 clauses, datasheet-derived part
   rules, corpus-mined invariants, and our own failure history, expressed as
   cost fields the router optimizes against (`METHODOLOGY.md` §6.3).
2. **Calibrated physics models** — SPICE and thermal models validated against
   bench measurement, so later designs need fewer physical iterations.

The router is necessary but is not the moat. The corpus is.

---

## Non-negotiable safety and performance gates

These gate fabrication release. Traceability lives in `docs/TRACEABILITY.md`.
**Measured status is tracked in the honest-state section below — as of this
writing, zero of 22 have been measured.**

### Performance

| Gate | Description | Reference |
|------|-------------|-----------|
| EFF-01 | Efficiency >90% @1000W (Pin/Pout) | `FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| EFF-02 | Efficiency >92% @1800W (ZVS active) | §1.1 |
| EFF-03 | Standby power <1.0W (off state, mains connected) | §1.1 |
| PWR-01 | Power accuracy ±10% @1000W | §1.2 |
| PWR-02 | Power accuracy ±5% @1800W | §1.2 |
| PID-01 | Temperature accuracy ±2°C (steady state @100°C, calibrated ref) | §1.3 |
| PID-02 | Temperature stability ±1°C (30min hold @60°C) | §1.3 |
| PID-03 | Overshoot <5°C peak (step 25°C→100°C) | §1.3 |
| PID-04 | Settling time <5min to within 2°C (step 25°C→100°C) | §1.3 |

### Protection

| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A **peak**, <1µs | `FUNCTIONAL_TEST_CRITERIA.md` §2.1 |
| OCP-02 | Secondary OCP 55-65A **peak**, <5µs | §2.1 |
| OVP-01 | DC Bus OVP 390-410V, hysteresis 10-20V | §2.2 |
| THM-01 | Heatsink NTC 85°C trip / 70°C recovery, shutdown | §2.3 |
| THM-02 | Coil NTC 120°C trip / 100°C recovery, shutdown | §2.3 |
| UVL-01 | Gate Drive UVLO **<12.0V falling** / **>13.0V rising** | §2.4 |
| UVL-02 | Logic UVLO **<2.9V falling** / **>3.0V rising** | §2.4 |

### EMC

| Gate | Description | Reference |
|------|-------------|-----------|
| EMC-01 | CISPR 14-1 Class B 150-500kHz (66→56 dBµV QP / 56→46 dBµV avg, >3dB margin) | `FUNCTIONAL_TEST_CRITERIA.md` §3.1 |
| EMC-02 | CISPR 14-1 Class B 0.5-5MHz (56 dBµV QP / 46 dBµV avg, >3dB margin) | §3.1 |
| EMC-03 | CISPR 14-1 Class B 5-30MHz (60 dBµV QP / 50 dBµV avg, >3dB margin) | §3.1 |

### Mechanical

| Gate | Description | Reference |
|------|-------------|-----------|
| MCH-01 | Button force 2-5N (tactile feedback) | `FUNCTIONAL_TEST_CRITERIA.md` §4 |
| MCH-02 | Knob torque 0.5-2 N·cm (smooth feel) | §4 |
| MCH-03 | Glass load 20kg static, no cracking | §4 |

---

## Honest state (2026-07-25)

All figures measured on this date unless noted. Figures without a reproducible
command are not recorded here.

### Board

- `pcb/temper.kicad_pcb`: **149 footprints, 151 nets**, 4 copper layers.
- **Router scope: 95 nets.** Power/ground/HV nets are excluded from A* by
  `_should_route()` (`router_v6/_astar_reconstruct.py`); they are handled by
  zone pours.
- **`Edge.Cuts` was a placeholder** — a single 100 × 150 mm rectangle at the
  origin, while the placement spans x 31.5–145.9, y 30.7–240.4 mm.
  **113 of 149 footprints (76%) lay outside it.** See `METHODOLOGY.md` §7.
  **Fixed 2026-07-25**: outline is now (20, 20)–(172, 254), **152 × 234 mm**,
  derived from true pad extents (132.2 × 213.6 mm, widest part the MeanWell
  IRM-1 AC/DC module at 41.8 mm radius) plus a 10 mm edge margin.
  **0 of 149 footprints outside.** This is **rung 1** of the tightening ladder
  (`METHODOLOGY.md` §10) — deliberately loose, to be tightened toward the
  teardown enclosure envelope at rungs 3–4. It is not an enclosure decision.
- The committed board carries **no routing**: 0 segments, 0 vias, 0 zones.

### Router

Measured A/B, changing only the board outline. Same commit, netlist, and flags;
`enable_zone_pours=True`, empty placements.

| | Placeholder outline (as committed) | Outline enclosing the parts |
|---|---|---|
| completion_rate | **0.0000** | **0.7857** (66 of 84 attempted) |
| nets routed / failed | 0 / 95 | 66 / 18 |
| segments emitted | 0 | 2,966 |
| unconnected items | 326 | 281 |
| DRC violations (router output) | 625 | 1,289 |
| wall time | 27.3 s | 98.3 s |

**The router is at roughly 79%, not 3.45%.** It had never been given a valid
board. DRC rising from 625 to 1,289 is expected and honest — zero routing
cannot produce routing violations; 2,966 new segments produce new ones.

**79% is not "nearly done."** It is measured with an unvalidated schematic. It
means the infrastructure is far healthier than previously recorded, not that
the board is close.

### Rung 1 — routed against the real outline (2026-07-25)

Re-measured on the committed board after the `Edge.Cuts` fix above. Same
invocation, `enable_zone_pours=True`, empty placements:

| | Value |
|---|---|
| completion_rate | **0.7857** (66 of 84 attempted) |
| segments / vias / zones | 3,265 / 48 / 98 |
| unconnected items | **276** (from 326 unrouted) |
| DRC violations | 1,464 |
| wall time | 141.3 s |

Violation profile of the routed output: **499 `clearance`**, 597 silkscreen
(199 each of `silk_edge_clearance` / `silk_overlap` / `silk_over_copper`),
**113–124 `shorting_items`**, 85 `solder_mask_bridge`.

> **`shorting_items` is not reproducible.** Five `kicad-cli pcb drc` runs on
> the *same* routed file returned 124 / 113 / 119 / 120 / 123 — a spread of 11
> (~9%). The router itself is deterministic (byte-identical geometry across
> runs once `tstamp`/`uuid` are stripped); the instability is in KiCad's DRC.
> `unconnected` (276) and `clearance` (499) are stable.
>
> Any figure gated on `shorting_items` is therefore unreliable at ±11 —
> including `drc_ceiling.json`, the corpus regression baselines, and the
> "381 honest violations" figure recorded below. A shorts fix must be
> validated over N ≥ 5 runs with median and range, never a single before/after.
> Evidence: `docs/evidence/2026-07-25-shorting-items-diagnosis.md`.

**`completion_rate` is itself a blind metric.** It reports 78.57% while the
routes it produced contain 499 clearance violations and 123 shorts. A short is
a fatal defect on a mains-connected board. Completion measures *whether a path
was found*, not *whether the path is manufacturable* — the same class of gap
as `METHODOLOGY.md` §7, one level up.

Consequence: the router's success metric needs a DRC-legality term before any
completion figure is quoted as progress. Recorded here so 78.57% is not
carried forward as a stale headline the way "24/24" and "72/95" were.

### Rung 1b — re-measured after the CST3015 change (2026-07-26)

T1 was swapped to the CST3015-100ED (courtyard 21.0 × 16.2 → 24.86 × 30.5 mm,
3.5× area) and four parts re-placed. Re-routed on the same board, manufacturing
DRC off:

| | Rung 1 | Rung 1b | Δ |
|---|---|---|---|
| completion_rate | 0.7857 | **0.7738** | −1.2 pp |
| segments | 3,265 | **2,878** | −387 |
| vias | 48 | **52** | +4 |
| unconnected | 276 | **283** | +7 |
| `shorting_items` median (range) | 120 (113–124) | **142 (136–148)** | **+22** |
| `clearance` | 499 | 499 | 0 |
| wall time | 141 s | 96 s | — |

**The shorts increase is real, not noise.** Measured as median over five DRC
runs per the protocol in the reconciliation note above; the two ranges
(113–124 and 136–148) do not overlap. This is the first time that protocol has
distinguished a genuine regression from measurement scatter.

**This is an accepted trade, not a defect.** A 3.5× larger part landed in an
already-tight region, so nets that previously routed through it no longer can.
What was bought: OCP-01 moves from failing (37.6 A against a 45–55 A window) to
passing at 50.1 A, and winding isolation goes from 1500 Vrms to 5000 Vrms
reinforced with ≥8 mm creepage. Protection correctness over routability, on a
board that is not fabricable for other reasons anyway.

**Manufacturing DRC could not be included.** With the stage enabled the run did
not finish — 27 min, 98% CPU, 9.2 GB — because `verify_clearance` is O(n²) pure
Python. It is now switchable and off by default; see
`docs/evidence/2026-07-26-manufacturing-drc-scalability.md`.

### DRC — committed board

747 violations, 326 unconnected (`kicad-cli pcb drc`, KiCad 10.0.4):

```
199  silk_overlap          62  shorting_items        7  missing_courtyard
199  silk_over_copper      57  solder_mask_bridge    5  copper_edge_clearance
146  lib_footprint_issues  27  courtyards_overlap    4  hole_clearance
 12  clearance             16  pth_inside_courtyard  3  hole_to_hole
 10  silk_edge_clearance
```

**53% is silkscreen cosmetics burying 62 `shorting_items`** — real electrical
defects on an HV board. This is the alarm-fatigue failure mode
(`METHODOLOGY.md` §6.2), already active.

### Retracted figures

- **"72/95 routed"** (v1.0, attributed to `f53aa042`) — does not reproduce.
  Default flags on the committed board give 0/95. The number came from an
  unidentified configuration.
- **"24/24 routed"** — the piantor benchmark board, never the temper board.
- **"3.45% completion"** (`docs/evidence/2026-07-24-r14-…json`) — accurate for
  its configuration, but measured against an invalid board outline; it says
  nothing about router capability.

### Schematic

**Not validated on any axis.** No clean ERC run (no ERC has ever been run), no
power-stage simulation, no verified component values against computed stress, no
review by an experienced power-electronics engineer.

### ERC

**First run 2026-07-25** (`kicad-cli sch erc`, KiCad 10.0.4, `pcb/temper.kicad_sch`).

**438 violations, all severity `warning`. Zero errors.**

```
149  lib_symbol_issues       symbol/library drift
146  footprint_link_issues   footprint assignment
143  endpoint_off_grid       wire endpoints off grid
```

`pcb/mcu.kicad_sch` separately: 64 violations.

**What this does and does not tell us.** No connectivity errors were reported —
no undriven power pins, no conflicting outputs, no duplicate references. That
is genuinely reassuring about gross wiring.

But **ERC validates schematic hygiene, not circuit correctness**, so "ERC
clean" must never be read as "schematic trustworthy." The design loop's real
questions — are the component values right, does the resonant tank hold ZVS
across the pan-load range, do the protection thresholds land inside
OCP-01/OVP-01 — are untouched by ERC and need simulation plus expert review.

One warning class deserves follow-up rather than bulk suppression:
**143 `endpoint_off_grid`**. Off-grid endpoints are the condition under which
two wires appear visually connected but are electrically separate. KiCad grades
it a warning; on a mains-connected board it is worth confirming that none of
the 143 sit on a net that matters.

### Simulation

`simulation/models/` holds **13 vendor model files and no harness**:
`IKW40N120H3.lib` + `IKW40N120H3_thermal.sub` (IGBT), `pan_load.sub` and
`current_transformer.sub` (tank and sensing), `UCC14140_behavioral.sub`
(isolated gate drive), `TLV3201` + `TPS3700` + `REF2025` (protection
comparators and reference), `LMR51430_avg.lib` + `XC6220_3V3` + `LDO_3V3`
(rails), `SN74LVC1G08` + `SN74LVC1G38` (logic). This is a nearly complete kit
for the power stage and protection chain, with nothing to run it.

### Gates

**0 of 22 measured on hardware.** No board has been fabricated. No protection
has tripped. No performance has been observed. Every gate's *acceptance*
requires physical hardware.

**1 of 22 measured in simulation — and it FAILS.**

#### OCP-01 — simulated 37.61 A against a 45–55 A requirement

First simulated protection measurement in the project (2026-07-25,
`simulation/harness/run_ocp01_sim.py`, evidence
`docs/evidence/2026-07-25-ocp01-trip-point-sim.json`). Independently
re-derived by hand:

| | |
|---|---|
| Reference divider | 3200 Ω / 10000 Ω on +3V3 → **V_ref = 2.500 V** |
| CT + burden | 1:100, 6.65 Ω |
| Trip current | 2.5 / 6.65 × 100 = **37.6 A** |
| Simulation | **37.611 A** |
| **OCP-01 requirement** | **45–55 A** |

The design as committed trips **7.4 A below the specified minimum.**

The source contains both figures and contradicts itself:

- `elec/src/modules.ato:1188` — *"6.65R keeps the OCP trip at
  2.5V/6.65R\*100 = 37.6A"*
- `elec/src/modules.ato:1493` — *"Over-current protection comparator, 50A
  threshold."*

**A 50 A trip is not merely unimplemented, it is unreachable.** It would
require V_ref = 50 × 6.65 / 100 = **3.325 V from a 3.3 V rail**. No choice of
divider on this rail can reach the OCP-01 window with a 6.65 Ω burden; the
burden resistor or the CT ratio has to change.

Caveats, stated rather than buried:

- **Uncalibrated.** No bench data exists; all models carry
  `calibrated: false`.
- **OCP-01's <1 µs propagation budget remains UNMEASURED.** The `TLV3201`
  behavioral model declares no timing model. Reporting a delay figure from it
  would be a fabricated number.
- Whether 37.6 A is *dangerous* or merely *non-compliant* depends on real
  operating current at 1800 W, which is unmeasured. It is a spec violation
  either way.

This is the first finding in this work that advances an actual gate rather
than the verification layer around it.

#### Full protection-gate audit (2026-07-25)

All seven protection gates examined against the committed `elec/src/modules.ato`
values. Simulated results hand-verified against divider arithmetic. Every model
`calibrated: false`; ngspice confirmed deterministic (5 identical runs per gate).

| Gate | Requirement | Measured | Verdict |
|---|---|---|---|
| OCP-01 | 45–55 A | **50.12 A** | **FIXED** 2026-07-25 — needed a new CT (CST3015-100ED, 88 A) |
| THM-01 | 85 °C | **84.91 °C** | **FIXED** 2026-07-25 — divider re-proportioned |
| OVP-01 | 390–410 V | **399.88 V at a node that never exceeds ~170 V** | **FAIL-OPEN** — see "OVP-01 senses the half-bus" below. The 2026-07-26 "fix" broke a working circuit |
| OCP-02 | 55–65 A | 60.0 A designed | **DESIGNED, not implemented** — INA240 pinout unverified |
| THM-02 | coil NTC 120 °C | **120.3 °C** | **DESIGNED & WIRED** 2026-07-26 |
| UVL-01 | <12.0 V | — | **UNMEASURABLE** — internal to UCC21550B silicon |
| UVL-02 | <2.9 V | 2.825 V (candidate circuit) | **UNCONFIRMED** — see below |

**Two gates have no implementing circuit.** Verified by inspection, not
inference:

- **OCP-02**: zero references to a secondary OCP anywhere in `elec/src/*.ato`;
  exactly one `OCPComparator` instance exists. Yet `docs/hardware/BOM.md:111`
  lists `U_COMP2 | LM393DR | Secondary OCP` — a part costed for a circuit that
  was never wired.
- **THM-02**: exactly one `ThermalComparator` instance (`modules.ato:1790`),
  wired to the heatsink NTC. No coil-temperature circuit exists.

**THM-01 contradicts its own docstring** (*"Thermal protection, 85C threshold
with hysteresis"*) by ~14.5 °C — the same self-contradiction species as OCP-01.

**BOM and schematic specify different thermistors.** `BOM.md:176` lists
`NCU18XH103F6SRB` (10 kΩ @ 25 °C, B=3950); `modules.ato:1648` uses
`NTCALUG01A104GA` (R25 = 100 kΩ, B = 4190 K), annotated "VERIFIED 2026-07-16".
Different R25 *and* different B — the divider behaviour is not comparable.

**OVP-01 is resolved, and it was failing hard.** The ambiguity is settled by
`modules.ato`: `ovp.v_bus.line ~ dc_bus.line` — the divider senses the **full
bus**, which `main.ato:94` declares as `+340V_BUS` with `v_bus_max = 340 V`.
There is no half-bus interpretation.

With the 130:1 divider (3 × 430 kΩ over 10 kΩ) and the original 1.50 V
reference, the trip was 195 V. At the 340 V nominal bus the sense node sits at
**2.615 V against a 1.50 V reference — the OVP fault asserted permanently and
the cooker could not have run at all.**

`main.ato:195` had already stated the intent (`v_ovp_trip: voltage = 390V`,
with `assert v_ovp_trip > v_bus_max`); the reference divider simply never
matched it. Fixed by `r_ref_top` 12 kΩ → 732 Ω, giving V_ref = 3.075 V and a
**399.88 V** simulated trip (hand-derived 399.7 V), worst case 391–408 V over
±1% parts — inside the 390–410 V window at both ends.

**UVL-02's candidate** (TPS3700 monitoring RTD_AVDD) trips at 2.825 V,
conservatively under the 2.9 V ceiling, but it monitors the RTD subsystem. The
more literal candidate — the TPS3823-33 watchdog supervisor, 2.93 V typ — is
fixed silicon with no model.

**Summary: of seven protection gates, two fail measurably, two have no
circuit, one is ambiguous, and two are unmeasurable in simulation.** None has
been validated on hardware. These are the gates the safety case rests on.

### Recovered gate qualifiers invalidate three of today's fixes (2026-07-26)

The gate tables above previously dropped qualifiers that
`FUNCTIONAL_TEST_CRITERIA.md` states explicitly — peak/RMS basis, rising/falling
direction, and **entire recovery and hysteresis columns**. Restoring them
immediately falsified part of three fixes landed earlier the same day:

| Gate | Spec (recovered) | As designed today | Verdict |
|---|---|---|---|
| THM-01 | trip 85 °C, **recovery 70 °C** → 15 °C hysteresis | trip 84.9 °C, release 79.2 °C → **5.6 °C** | **insufficient hysteresis** |
| THM-02 | trip 120 °C, **recovery 100 °C** → 20 °C hysteresis | trip 120.3 °C, release 113.7 °C → **6.6 °C** | **insufficient hysteresis** |
| OVP-01 | 390–410 V trip, **hysteresis 10–20 V** | no hysteresis — comparator has no feedback resistor | **hysteresis absent entirely** |

The trip points are correct in all three cases; the release behaviour is not.
Required sense-node swings, computed from the NTC beta curve:

- THM-01 needs **0.4154 V** between the 85 °C and 70 °C sense levels; the
  present divider delivers 0.1535 V.
- THM-02 needs **0.4582 V** between 120 °C and 100 °C.

These are `r_hyst` value changes, not topology changes. OVP-01 needs a
hysteresis resistor added, which it currently lacks.

**This is the cost of reasoning from a lossy summary.** The information was in
the source document throughout; three designs were derived against a table that
had silently dropped the columns that constrain them. Two earlier analyses this
week — OCP peak-versus-RMS and UVL-02 threshold direction — had already been
corrected for the same reason before the cause was identified.

Also surfaced: **`FUNCTIONAL_TEST_CRITERIA.md` §1.2 specifies a 200 W ±25%
power tier that has no corresponding gate** in this document. That is an
omitted requirement, not a lost qualifier.

### Manufacturing DRC is no longer the bottleneck (2026-07-26)

Full detail: `docs/evidence/2026-07-26-clearance-rust-port.md`. `verify_clearance`
is ported to Rust in `temper-drc-rs`. **Stage 5 now adds ~0.7 s to a ~124 s
route, down from 25+ minutes or non-terminating.** 9.7×–124× faster than the
Python path, the gap widening with n.

**Scope correction to a figure this document previously carried.** The
"27 min / 9.2 GB" was **Stage 5 as a whole** — all seven DFM checks — not
`verify_clearance` alone. Measured in isolation the function is O(n²) in time
(180.9 s at 3,200 routes, clean 4×-per-doubling) but modest in memory, under
5 MB. The 9.2 GB belonged elsewhere in the stage.

**Both falsifiers were stated before implementing and neither fired:** distinct
required-clearance values on the real board number **3** (0.127 / 4.2 / 14.0 mm)
and do not grow with n; HV-gated nets are **1.16%** (7 of 603). That is what
makes a two-tier structure safe here — a uniform grid for the ~99% fine-vs-fine
majority, brute force for HV-touching pairs and all via checks. An explicit
100%-HV differential test proves it degrades *gracefully* rather than
*incorrectly* if that ratio ever changed.

**Equivalence was proved, not assumed.** The port preserves CPython's positional
`max()`/`min()` NaN semantics, NaN poisoning of per-layer minima, two
*different* HV-keyword lists, and an existing `via_diameter_default` quirk —
**preserved deliberately, not fixed**, so the port is a port. Evidence: a
40-seed Rust property test against a brute-force oracle, a Python-vs-Rust
differential test asserting **set equality of violations, not counts**
(`test_clearance_rust_differential.py:131`), and the full suite at **551 passed,
18 pre-existing xfail, 0 failed** now running against the Rust backend.

The existing Hypothesis idempotency test earned its keep: it caught **`HashMap`
iteration-order nondeterminism** in the new grid, fixed with `BTreeMap` and
locked in by a regression test.

**The port is NOT active in the primary checkout, and its proof skips silently.**
Measured at HEAD:

```
pytest test_clearance_rust_differential.py -q  ->  38 skipped in 0.07s  (exit 0)
```

The port's author reported "38/38 pass", true in their own worktree where the
wheel was built. Here, `test_clearance_rust_differential.py:33-35` guards on
`skipif(not _HAS_RUST_CLEARANCE)`, and the installed `temper_drc_rs` exposes
only `run_drc` — a stale wheel predating `verify_route_clearance`.

**So both guarantees are absent wherever the wheel is stale**: the speedup (the
Python fallback runs) and the equivalence proof (the differential test never
executes). Both silent; the suite exits 0.

This is the **silently-skipped** entry in `METHODOLOGY.md` §4's own taxonomy —
after ten dead CI gates and five vacuous ones, it would be the eleventh. Note
the ambiguity that makes it invisible: **"38 passed" and "38 skipped" are both
exit 0.** Reporting run counts rather than exit codes is the whole fix.

The wheel was *importable and wrong-versioned*, not missing, so an import check
would not have caught it. A build-freshness check comparing installed extension
to crate source is the mechanism that would.

**`enable_manufacturing_drc` still defaults False, deliberately.** Performance
no longer blocks it, but two things do: 14 of 16 router-instantiating test files
implicitly assume it is off, and **the committed board has 616 critical
violations** — genuine overlapping copper from routing that is 76.2% complete —
which would immediately trip the existing `dfm_fail_on="critical"` gate. Flipping
the default is a follow-up decision, not a side effect.

### SELV domain floated — barrier real, but one resistive crossing remains (2026-07-26)

Full detail: `docs/hardware/SELV_ISOLATION_REDESIGN.md`. **Landed.** The star
join is gone; `main.ato:341` now reads `gnd ~ pe`, bonding SELV ground to
protective earth instead of to the doubler midpoint. The ZCD signal crosses
through a new **H11L1 optocoupler** (`U3`, datasheet-verified, 5000 Vrms), and
`+340V_BUS` is renamed `+170V_BUS`.

**Verified by hand on a freshly built netlist at HEAD**, not taken on report:

| Net | Code | Pins | Refs |
|---|---|---|---|
| `gnd` | 1 | 80 | 71 |
| `PWR_RTN` | 6 | 17 | 17 |

Straddling designators: **`C6`, `PS1`, `T1`, `U3`** — the Y-cap, the IRM-10-15,
the CST3015 current transformer, and the new optocoupler. Every one crosses by
design.

**The barrier is not yet complete, and the gap evades the obvious test.**

```
main.ato:434   safety.dc_bus.line      ~ dc_bus_plus   # +170 V, HV domain
main.ato:435   safety.dc_bus.reference ~ gnd           # SELV domain
```

The OVP divider is **1.30 MΩ (3 × 430 kΩ + 10 kΩ) joining the HV bus to SELV
ground.** Those are two *different* nets, so a partition check asking "are the
declared domains disjoint?" returns **PASS while a galvanic path exists**.
The lesson generalises: **passive two-terminal parts are wires.** Only declared
isolators may break connectivity, and capacitors need an explicit, defended
policy because they block DC and pass AC.

**The steady 131 µA of leakage is not the hazard.** If the 10 kΩ bottom
resistor opens, **the full +170 V appears on the SELV-side node** — which feeds
a comparator input and an MCU ADC pin. A single passive failure puts
mains-derived HV onto the control domain. Crossings should be reported with
their single-fault behaviour, not merely their existence.

Also found, and separate from isolation: **THM-02's MCU analog tap
(`coil_ntc_sense`) is never wired at Top** — a completeness gap in a
protection circuit that is otherwise live. `SecondaryOCPComparator` remains
deliberately un-instantiated. `LogicUVLOComparator` is entirely SELV-internal
and is not a crossing at all.

ERC after the change: **492 warnings, 0 errors**, in the same three pre-existing
generic categories — no new violation class.

### The bus capacitance rests on a simulation that does not exist (2026-07-26)

Full review: `docs/evidence/2026-07-26-bus-capacitor-architecture-review.md`.
The earlier reselection is **withdrawn**: six 66 mm cans are 57.7% of the
152 × 234 mm board as raw circles and **82.7% at a realistic 70 mm pitch**, and
the small-can route is worse — 20–24 D35 cans at **90–108%** of the board. The
source edits were reverted; `EKMQ251VSN182MA50S` stands, still failing ripple.

When every route is physically impossible, the architecture is the defect.
Three findings follow, and the third is the load-bearing one.

**1. The HF bypass is across the wrong node pair.** `c_dc_hf` (470 nF) is wired
`hv_plus ↔ hv_minus` (`modules.ato:322-331`). In this doubler the ripple never
flows through that pair — it flows `hv_plus ↔ gnd_ref` and `gnd_ref ↔ hv_minus`,
one half at a time. The part is in the circuit and out of the current path.
Sizing it correctly would need **~819 µF per half**, ~1740× the present value,
at or beyond commercial DC-link film range — and still insufficient, since the
line-frequency term fails on its own.

**2. The bank is ESR-dominated at 35 kHz.** Xc is 2.3% of ESR, so the
electrolytics absorb the HF term regardless of what the film cap does.

**3. There is no derivation for 3600 µF per half, and the evidence cited for it
does not exist.** `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md:70` reports results
"(sim_33_voltage_doubler.cir)" and cites two explicit paths at `:291-292`.
**Neither file exists anywhere in the repository** — confirmed by `find`. A
"Results" section reports numbers from a simulation with no artifact.

Worse, the "≥5 A RMS ripple current" spec that sizing rests on appears to be
**the average DC diode current relabelled as RMS ripple**, corroborated by that
same document's capacitor-loss estimate being ~10× low against real ripple.

**So the ripple failure is substantially self-inflicted.** A stiff bus was
chosen on absent evidence against a mis-derived requirement. Published work on
this topology class (Hsieh 2023, IET Power Electronics) deliberately uses
*reduced* DC filtering for high power factor — the opposite direction.

**Next step is to re-derive bulk capacitance from a real model**, checked
against the tank's already-tight ZVS margin, before any further part selection.

**Superseded by the derivation below — at real part tolerance, `BusDischarge`
FAILS.** `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` computes **65.4 s at the
capacitor's +20% tolerance** against the <60 s target, verified against the
distributor-published tolerance. The 54 s figure is nominal-only. So the
sequence here went: reported failing at 213 s (wrong — that was a withdrawn
proposal), corrected to passing at 54 s (right, but nominal-only), and now
**failing at 65.4 s once tolerance is applied.** The margin never existed.

Two fixes, either sufficient: reduce C to **~3000 µF/half**, or resize the
discharge strings from **9.4 kΩ to ~8.6 kΩ** and leave C alone. The latter is
arguably lower-risk since it touches one passive value rather than the bus.

**The derivation's load-bearing result: capacitance is a weak lever on the
ripple failure.** The 35 kHz term is structurally independent of bulk C, so
driving C toward zero buys back at most ~27% of the combined ripple current. At
the recommended 3000 µF the margin moves only from **4.26× to 4.16×** over
rated. **Re-sizing the bus does not fix ripple** — that needs the film-bypass
and parallel-capacity levers from the architecture review.

The ripple-voltage budget lands at ~15–16%, justified *not* by ZVS or voltage
headroom (neither is tight) but by there being no reward for pushing further.

**The falsifier partially fired**, which is the honest part. ZVS Coss-timing and
voltage ratings are derivable from real datasheet numbers and are non-binding.
But whether the tank still delivers 1800 W through the bottom of the ripple sag
(`PWR-02`/`EFF-02`) needs the tank's `P(V_bus, f_sw)` transfer function — which
needs the coil/pan coupling calibration that `TANK_COIL_SPECIFICATION.md`
already flags as missing. **That is the named blocker: bench-measure the real
coil-and-pan coupling and reflected resistance.** It is the same measurement
three separate open questions now depend on.

**Prior text, retained for the record:**
The 213 s figure quoted previously was the consequence of the *withdrawn*
14,100 µF proposal, not the committed design. `modules.ato:772-773` derives the
real number — `tau = 9.4k × 3600 µF = 33.8 s`, reaching <34 V in 1.61 tau
≈ **54 s against the <60 s target**. It passes, on about 10% margin.

That reframes the coupling rather than removing it: discharge time scales
linearly with capacitance, so **anything above ~4000 µF per half breaks the
target** with the present 9.4 kΩ strings. It is a ceiling on C, not a failure to
repair. Two caveats: the 10% margin is nominal only, and electrolytic tolerance
plus ageing could plausibly consume it; and the discharge resistors are
themselves resizable, which is a real option rather than a fixed constraint.

**Separately: the `<60 s` requirement is not in `FUNCTIONAL_TEST_CRITERIA.md`.**
It exists only as comments in `elec/src/modules.ato` (lines 445, 636, 773). A
safety-relevant timing requirement — bus discharge for servicing, IEC 60335-1
territory — never made it into the requirements document at all. That is the
inverse of the derived-document drift class: not a qualifier lost on the way
down, but a requirement that never went up.

This is a new species for the failure taxonomy — not a wrong value, not a
vacuous check, but **a citation to evidence that was never produced.** Nothing
in the repo could have caught it, because nothing verifies that referenced
artifacts exist.

### `default.net` aliases part identity by footprint — use `default.csv` (2026-07-26)

Detail: `docs/evidence/2026-07-26-ato-build-state.md`.

**atopile's netlist exporter collapses the `libsource`/MPN identity of
components that share an identical KiCad footprint.** Every SOT-23-5 five-pin
IC — ten components spanning `REF2025`, six `TLV3201` instances, `SN74LVC1G08`,
`SN74LVC1G38` and `TPS3823` — is labelled `REF2025AIDDCR` in `elec/build/default.net`.
**85 distinct BOM parts collapse to 40 `libpart` entries.**

`default.csv`, the BOM and the designator map all identify each part
correctly. Only the `.net` file's part-identity fields are affected.

**Blast radius, checked rather than assumed:** the `(nets ...)` section keys on
`(ref, pin)` and not on `libsource`, confirmed directly for U19. So
connectivity-based checks — net topology, the SELV isolation survey, the
domain-partition gate — read the right thing. **Anything trusting `.net` for
*which part* a designator is will be wrong for every footprint-duplicate
group.**

This bit immediately: grepping `.net` for MPNs to test whether the artifact was
stale produced counts inflated by aliasing — 22 apparent instances of one
capacitor MPN across all 0603 parts. The clean test is `default.csv`.

**Two related facts, neither of which is the other:**

1. `ato build` was never broken. The bare invocation crashed because
   `elec/ato.yaml`'s `builds.default.entry` lacked the `:Top` root-instance
   suffix — pre-existing since the file was created, and never hit by the
   Makefile, which always passed the entry explicitly. One-line fix. This was
   the **fourth** stale-base false alarm of the day.
2. The build artifacts in the working checkout **are** currently stale — they
   predate the BOM blocker replacements. `default.csv` still lists
   `GRM188R71E104KA01D` and `DE2E3KH221MA3B`, neither of which is in source any
   more. They were current when measured a few commits earlier; `HEAD` moved
   underneath them. Since `elec/build/` is gitignored and has never been
   tracked, **there is no committed netlist and never has been** — every claim
   in this project citing `default.net`, including "the BOM reconciles 155/155",
   read a local artifact of unrecorded provenance.

### OVP-01 senses the half-bus and is now fail-open (2026-07-26)

**The 2026-07-26 OVP-01 "fix" recorded above disabled a working protection
circuit.** It reasoned from a net name instead of the topology.

`dc_bus_plus` is the **+170 V half-bus**, not 340 V. The proof needs no
comment and no datasheet — it is already machine-checked in the source:

```
modules.ato:614-615   c_bus1.plus ~ dc_bus.hv_plus ; c_bus1.minus ~ dc_bus.gnd_ref
modules.ato:579       assert c_bus1.voltage_rating >= v_bus_half * 1.25
```

The design sizes that exact capacitor — the one bridging `hv_plus` to the
midpoint — against `v_bus_half`. Rated 250 V: `250 >= 212.5` passes against
170 V; `250 >= 425` would fail against 340 V. 340 V is the differential from
`hv_plus` to `hv_minus`, not the potential at either node.

Meanwhile `main.ato:94-95` names that node `+340V_BUS` with the comment
`# +340V`, while `main.ato:270` calls the *same node* "Half-bus input
(~170VDC)". The file contradicts itself.

**Consequence.** The 1/130 divider with `V_ref = 2.973 V` trips at ~400 V *at
the sense node*, which sits at 170 V nominal. The comparator can never fire.

**The original 12 kΩ / 1.50 V value was correct**: `1.50 × 130 = 195 V`, exactly
half of the spec's 390 V — the right threshold for a half-bus sense. The
premise that the OVP "asserted permanently and the cooker could not have run"
was false; at 170 V the sense node sits at 1.31 V, *below* the 1.50 V
reference. The bug being fixed did not exist.

The false reasoning is recorded verbatim in `modules.ato:1590-1599` and is
being corrected alongside the SELV work, together with the lying net name.

**Resolution is deferred deliberately**, because it is entangled with the SELV
float: sensing the full bus differentially requires a reference at `hv_minus`
(−170 V), a second domain problem. Sensing the half-bus at half the threshold
is simpler but misses fault modes where the two halves diverge.

This is the third gate this session that went green while measuring the wrong
thing, and the only one where the error was introduced rather than inherited.
It is the seed defect for the net-name assertion gate in
`docs/evidence/2026-07-26-three-consistency-gates.md`.

### The fault tree is full — two designed circuits cannot reach the latch (2026-07-26)

Detail: `docs/hardware/UVL02_DESIGN.md` §7.1.

**UVL-02 now exists.** It had no implementing circuit; the two candidates were
both rejected on identity, not on which number looked better. `TPS3823-33` is
the literal logic supervisor but fixed silicon — verified against TI's
datasheet at **2.93 V falling / 2.96 V rising**, failing the `<2.9 V` / `>3.0 V`
window in *both* directions. `RTDSensing.rail_monitor` is the right IC family
but monitors `RTD_AVDD`, a downstream rail, not the logic supply.

The stated falsifier — *"the spec is achievable with a fixed-threshold
supervisor"* — **fired**. The window needs >3.4% hysteresis; that device class
tops out near 1–3%. It is only reachable with external positive feedback around
a window comparator, which is what `LogicUVLOComparator` now does: nominal trip
**2.716 V** / recovery **3.222 V**, worst case over ±1% E96 and the full
datasheet VIT_A range **2.800 V / 3.106 V** — inside both limits with 100 mV
and 106 mV to spare.

**But its fault is not wired, and cannot be.** Surveyed against the current
tree: `fault_or` gate 3's `Y3` drives nothing; `fault_any_or` gate 3 is
entirely unreferenced with no path into the SET aggregation; `fault_any_or.C2`
sits on the reset-qualifier path, so using it would block reset without ever
tripping the latch. `fault_any_or.C1` — which an earlier survey found free —
was claimed by THM-02 in `d99c88e2`.

**Two fully-designed protection circuits, OCP-02 and UVL-02, now have nowhere
to connect.** This is a fault-tree *capacity* problem, not a per-gate search.
Remediation is either reworking the two `SN74HC4075`s into a wider cascade or
adding a third OR package — a real part decision, deliberately not taken here.
UVL-02's fault currently lands on a test point so the circuit is provable on a
bench even while unwired.

Also corrected: `components.ato` carried a stale `v_threshold = 3.08V` for the
TPS3823, against the datasheet's 2.93 V.

### The isolation barrier is shorted by the star-point join (2026-07-26)

Full audit: `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md`. **This is the
highest-severity finding in the project to date.** Verified by direct reading
of the committed source, not inferred.

The design believes it has an isolated SELV control domain. Three lines defeat
it:

```
main.ato:271  aux_supply.power_in.gnd  ~ power_return   # HV side of the barrier
main.ato:273  aux_supply.power_out.gnd ~ gnd            # SELV side of the barrier
main.ato:299  power_return ~ gnd                        # "single-point star join"
```

`power_in.gnd` and `power_out.gnd` are therefore **the same net**. The
IRM-10-15's 4.2 kVAC isolation barrier is shorted across. A single-point star
join is a technique for joining grounds *within* one domain; applied *across*
an isolation barrier it is simply a short, and the comment block at
`main.ato:288-297` asserts both things at once.

That node is also mains-referenced. `modules.ato:620-621` ties AC Neutral
through the common-mode choke winding to `dc_bus.gnd_ref`, which is the same
net again. And `modules.ato:683-689` runs a 450 kΩ divider from **AC_L**
directly to that node with its tap going to an MCU ADC pin — carrying a `TODO`
that already admits *"ZCD signal crosses isolation barrier (HV -> SELV) …
For now, ZCD is on HV side."*

So the entire control domain — MCU, safety interlock, and the **user-touchable
RTD food probe** — sits at AC Neutral in normal operation, and at AC Line under
a reversed-plug fault. `RTDSensing`'s own docstring (`modules.ato:1259-1265`)
claims the opposite: *"The user-touchable RTD food probe is therefore separated
from AC mains potential."* It is not.

**This is a topology decision, not a value fix, and it is the user's call:**

| Option | Consequence |
|---|---|
| **Remove the star join**, float the SELV domain properly | Requires isolating every crossing — the ZCD optocoupler its own TODO already names, plus a full survey of the others. Preserves the SELV claim and the touchable probe |
| **Accept a mains-referenced design** and re-classify | Legitimate and common for induction hobs, but the SELV claim must be deleted everywhere, and the RTD probe needs reinforced insulation or must stop being user-touchable. Changes the certification approach wholesale |

Nothing else in the safety case should be treated as settled until this is
resolved, because the insulation coordination for every other part depends on
which domain it is actually in.

Second finding from the same audit: the **G5LE-1 discharge relays are approved
only to 30 VDC under UL/CSA** (125 VDC in the bare catalogue) while breaking up
to **170 VDC**. `modules.ato:700-724` already documents the out-of-catalogue
break and adds an RC snubber for it — but the *approval* still does not extend
there, so the mitigation solves the engineering and not the certification.

### Bus capacitors fail on ripple current by ~5× (2026-07-26)

Full derivation: `docs/evidence/2026-07-26-bus-capacitor-ripple.md`.

`EKMQ251VSN182MA50S` is rated **2.70 A rms at 105 °C, 120 Hz** (United
Chemi-Con CAT. No. E1001E, KMQ series, part listed explicitly). Four of them,
two per half-bus, give the bank **10.8 A** of ripple capability.

| Component | Per capacitor, 120 Hz-equivalent |
|---|---|
| Line-frequency recharge | **7.7 – 12.3 A** |
| ~35 kHz inverter draw | 8.4 – 9.5 A |
| **Combined (quadrature)** | **4.2 – 5.8 × rated**, central **4.8×** |

**Verdict: FAILS**, under every assumption combination checked including the
one most favourable to the design.

**The conclusion does not depend on the undefined tank inductance.** The
falsifier was stated before deriving — *"this fails if the line-frequency term
alone does not already exceed rating"* — and it did not fire: the
line-frequency term **alone** clears the rating by 2.8–4.6×. The switching-term
estimate was taken from this repo's own committed-values bound rather than
fabricated, and the verdict survives without it.

The analysis also corrected the topology framing: this is a Delon/cascade
doubler, so each bank recharges once per full 60 Hz cycle, not twice.

**Life estimation is not meaningful here.** The datasheet's 2000 h at 105 °C
endurance assumes operation *within* rated ripple. At ~4.8× rated the
dissipation is roughly 23× higher, and the case thermal resistance is not
published, so the hotspot rise is UNVERIFIED. Quoting a life figure would
imply a validity the operating point does not have.

This is the failure mode predicted as most likely for this design, and it is
failing structurally rather than marginally — the fix is more capacitance,
more parts in parallel, or a higher-ripple series, not a tweak.

### The BOM matches source but cannot be ordered (2026-07-26)

Full detail: `docs/evidence/2026-07-26-bom-availability-sweep.md`. ~38 of ~182
distinct MPNs checked (~21%), weighted by consequence; coverage stated
explicitly rather than implied.

Reconciling the BOM to source established **consistency, not procurability**.
Three blockers:

| Part | Problem |
|---|---|
| `GRM188R71E104KA01D` 100 nF 0603 | **Obsolete, zero stock** — and used in **22 netlist instances** across gate drive, buck, aux supply, MCU, RTD, watchdog and OVP |
| `DE2E3KH221MA3B` X2 EMI cap | Not found at any distributor. Murata's DE2-series coding decodes "221" as **220 pF, not the 220 nF the BOM states** — a 1000× mismatch, and the family tops out near 10 nF |
| `0034.3129` mains fuse | Real and stocked, but appears to be a bare fuse *link*, not the holder+fuse assembly the BOM describes |

The X2 capacitor is the more serious of the three: it is a **mains-facing
safety-critical part**, it carries a 1000× value discrepancy, and it may not
exist. It shares the exact signature of the already-corrected fictional
`EKZE251ELL332MM40S` bus capacitor — a plausible-looking MPN that survives
review because nobody looks it up.

**Risks** (not blockers): `G4A-1A-E` bypass relay is EOL with finite stock;
`V150LA10AP` MOV has conflicting EOL signals, left UNVERIFIED rather than
guessed; bus caps show only ~200 units at ~28-week lead; and `CST3015-100ED`,
`SN74HC4075DR` and the WIMA film cap could not be confirmed at a distributor
at all — notable because the CST3015 was selected only today.

**Two MPN discrepancies resolved** by tracing to the netlist rather than the
prose: only `MAX31865AAP+` (SSOP-20) is ever instantiated — `ATP+` exists only
in BOM text; and only `UCC21550BDW` is ordered, though the atopile class is
still misleadingly *named* `UCC21550BDWK`.

### OCP-01 versus full-power tank current (2026-07-26)

Analytical, from committed values only — no pan model. Full working:
`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`.

**OCP-01 trips on instantaneous current.** There is no rectifier in the sense
path (the BOM's "Precision Rectifier (OCP)" is class A — costed, never wired),
and the 100 nF across the burden has a 319 kHz corner, so at the 35 kHz
fundamental it filters noise rather than averaging. Trip is **50.1 A peak =
35.4 A RMS**.

**That is in tension with EFF-02/PWR-02.** Power is `I_rms² × R_eff`, so
reaching 1800 W without tripping requires:

| Trip (peak) | = RMS | `R_eff` needed for 1800 W |
|---|---|---|
| 45.0 A (spec min) | 31.8 A | 1.78 Ω |
| **50.1 A (as built)** | **35.4 A** | **1.43 Ω** |
| 55.0 A (spec max) | 38.9 A | 1.19 Ω |

A typical 1.8 kW hob runs ~40 A RMS, implying `R_eff ≈ 1.12 Ω` — which needs
56.6 A peak and **trips**. Even at the top of the OCP-01 window the design
needs better-than-typical coupling. The failure mode is nuisance trips on
low-resistivity, undersized or off-centre cookware.

The conflict is **conditional on `R_eff`, which is unknown** because the coil is
unspecified. That makes measuring `R_eff` for the intended coil and a reference
pan set the single highest-value bench measurement available — it also unblocks
the coil specification.

**Spec ambiguity, again.** `OCP-01: 45-55A` does not say peak or RMS. Read as
peak the implementation is compliant; read as RMS it trips at 35.4 A, below the
45 A minimum. Peak is almost certainly intended — OCP-02's 55–65 A read as RMS
would be 78–92 A peak against a 40 A IGBT, which is incoherent. This is the
same ambiguity as UVL-02 and should be written into
`FUNCTIONAL_TEST_CRITERIA.md` rather than inferred a third time.

### ZVS margin — the coil inductance is undefined (2026-07-26)

First power-stage simulation. Full evidence:
`docs/evidence/2026-07-26-zvs-margin-sweep.json`, harness
`simulation/harness/run_zvs_sweep.py`.

**The tank's defining component has no value in the design.** `grep` across
`elec/src/*.ato` finds **no inductance anywhere** for the coil
(`inductor_conn` is an unplaced Litz placeholder). Resonant frequency is
therefore undetermined by the committed design. The sweep used
`pan_load.sub`'s own 80 µH default, which is a *model* assumption, not a
design choice.

With the committed 300 nF (`c_tank1` + `c_tank2`, 150 nF each **in parallel**)
and that 80 µH:

| | |
|---|---|
| Actual resonance | **~32.5 kHz** |
| Declared `f_resonant_nominal` (`main.ato:74`) | **25 kHz** |
| Operating `f_switching` (`main.ato:71`) | **35 kHz** |
| ZVS collapse, measured | between **32 kHz (lost)** and **33 kHz (held)** |

**The design believes it has ~10 kHz of margin above resonance. Under the
model's assumption it has ~2.5 kHz — four times less.** Losing ZVS means hard
switching, which is the primary way an IGBT dies in this topology.

To make the declared 25 kHz true, the coil would have to be **135 µH**. At
80 µH resonance is 32.5 kHz; at 68.9 µH it would sit exactly on the 35 kHz
operating point, i.e. fully capacitive and no ZVS at all. **Nothing in the
design distinguishes these cases**, which is the actual defect — the margin
number is a consequence, not the root.

Also found: `pan_load.sub`'s `PANLOAD_SIMPLE` / `PANLOAD_VARIABLE` subcircuits
declare an `RPAN` parameter that is **never referenced in the subcircuit
body** — a dead knob, the same unwired-parameter class as the CLI flags and
the manufacturing DRC stage. `PANLOAD_TRANSFORMER` was used instead.

Sweep covered 4 pan presets × 9 frequencies (28–45 kHz); 34 of 36 points
converged, 2 reported `UNMEASURED` rather than guessed. Collapse is driven
almost entirely by frequency versus tank resonance, not by pan coupling —
which is why the coil value matters more than the pan model.

**Fidelity bound, stated rather than buried:** the IGBT model is behavioural
with fixed capacitances, so margins are ordinal, not calibrated
switching-loss figures. All models remain `calibrated: false`.

### BOM vs. source audit (2026-07-25)

Full detail: `docs/evidence/2026-07-25-bom-source-audit.md`.

The two BOM contradictions found incidentally above prompted a systematic
audit. The BOM and the design source disagree extensively **in both
directions**:

| Class | Count | Meaning |
|---|---|---|
| **A — costed, no circuit** | **35 BOM lines** | Parts ordered for circuits that do not exist |
| **B — wired, uncosted** | **~75 source components** | Designed circuits whose parts will not be ordered |
| **C — values disagree** | **16 items** | Same part, different value or MPN |

**Two safety systems are mirror images of each other**, both spot-verified by
the reviewer:

- **IGBT desaturation protection is costed but never designed.**
  `docs/hardware/BOM.md:145–163` lists 19 line items — DESAT diodes
  (STTH1R06, 1200 V), 1 MΩ current-limit resistors, blanking capacitors — and
  `grep -ni "desat" elec/src/*.ato` returns **nothing**. There is even a
  `docs/hardware/IGBT_DESATURATION_PROTECTION.md`. DESAT is the mechanism that
  detects an IGBT short-circuit and shuts the stage down.
- **Active bus discharge is designed but never costed.** 14 references in
  `modules.ato` (the router routes `discharge.k_dis1`, `discharge.r_dis1a` and
  siblings); **zero** BOM entries. This is what makes the 340 V bus safe to
  touch after power-off.

Also absent from the BOM while present in source: the **isolated auxiliary
15 V supply** — the actual isolation barrier — and the RTD hardware-window
fault chain (~25 parts, including the UVL-02 candidate circuit cited above).

Also class A: the secondary-OCP shunt/diff-amp/comparator chain
(`BOM:109–111`), the precision rectifier (`BOM:185–186`), the ADUM1250 I²C
isolator (`BOM:95`, explicitly superseded per `components.ato:51–54`), five
fault LEDs (`BOM:196–201`, whose source comment at `modules.ato:1863` says they
"remain unassigned"), and 74HC08D/74HC04D logic ICs (`BOM:131–132`) with zero
references anywhere.

Class C includes the **OCP-01 current-sense pair** (CT + burden,
`BOM:102–103`) and the **OVP divider** (`BOM:169–170`) — the components that
set the trip points already recorded as failing and ambiguous above. The
BOM-vs-source gap on them was previously unnoticed.

**Consequence: the BOM cannot currently be used to order this board.** It bills
for circuits that were never designed and omits circuits that were. Reconciling
it is a procurement and design decision, deliberately not made here.

Counts are the audit's; the two safety-system findings and the OCP/OVP value
gaps were independently spot-verified. Coverage limits and UNRESOLVED items are
recorded in the evidence document.

---

## Architecture decisions

### Two boards

Split HV from LV. **U6, the SOIC16W isolated gate driver, is the boundary.**

- **HV board** — AC inlet, EMI CMC, bridge, bus capacitors, IGBT (U5),
  resonant tank, current transformer, active bus discharge, U6 primary side.
  Thick copper, wide clearances, few nets.
- **LV board** — ESP32-S3, LMR51430 buck, MAX31865, sensing frontends, UI,
  U6 secondary side. Dense, low voltage, 2-layer, cheap to respin.

Rationale: creepage/clearance becomes a board-edge problem rather than an
intra-board one; the LV board becomes cheap enough to iterate freely; routing
difficulty drops on both; loops shrink and parallelize.

**Cost to carry forward:** gate drive now crosses a connector, and gate drive is
inductance-sensitive. This is a design constraint, not a blocker.

### Semantic netlist as router input

Atopile emits a hierarchical semantic partition — `hb.*`, `tank.*`,
`safety.ovp.*`, `discharge.*`, `power_in.*`, `thermal.*`, `rtd_pan.*` — that the
router currently treats as opaque strings. Carrying that intent into router
objectives is likely a larger win than any A* improvement and is mostly plumbing
on information already present.

### Physics branches are the live line of work

`feat/physics-routing-constraints`, `feat/physics-informed-placement-routing`,
`feat/physics-thermal-field`, and `feat/physics-verification-rigor` (last
touched 2026-07-09) implement checks-as-cost-fields, the pattern
`METHODOLOGY.md` §6.3 depends on. They were parked for router hygiene. They are
the highest-value existing work in the repository.

---

## Pipeline architecture

### Today

```
elec/*.ato ──► netlist ──► placement ──► routing ──► kicad-cli drc ──► gerbers
                                                       ▲
                                            one terminal metric,
                                            geometric only, no oracle
```

Each stage trusts its input. Checks live at the end and are purely geometric.
The router optimizes connectivity and wirelength; physics is an optional
bolt-on. Atopile's semantic hierarchy is flattened to strings. Everything is
learned at the end, or not at all.

### Target

```
                    ┌──────────── CHECK CORPUS ─────────────┐
                    │ provenance-tiered · emits cost fields  │
                    └─┬──────┬────────────┬───────────┬──────┘
      verdicts (gate) │      │            │           │
                      ▼      ▼            ▼           ▼
 .ato ──► netlist ──► ✓ ──► placement ──► ✓ ──► routing ──► ✓ ──► DFM ──► gerbers
   │        │                  ▲                    ▲
   │   semantic                └──── cost fields ───┘
   │   hierarchy                     (steer)
   │   preserved ─────────────────────────────────►
   │
   └──► ERC ──► SPICE / thermal ──► calibrated? ──► verdicts + cost fields
             (design loop, independent clock)


  ┌─ VALIDATOR PIPELINE (own clock: runs when checks change) ─┐
  │  check corpus ──► fault injection  → sensitivity          │
  │              └──► known-good corpus → specificity         │
  │                        ↓                                  │
  │                  coverage number                          │
  └───────────────────────────────────────────────────────────┘
```

### Five structural changes

1. **Checks shift left.** Each check declares the earliest stage at which it is
   computable, and runs there.
2. **The check layer gains a feedback edge.** The same corpus flows both
   directions: verdicts out (gate), cost fields in (steer), under threshold
   subordination (`METHODOLOGY.md` §6.3).
3. **Seams become contracts** (`METHODOLOGY.md` §3.1). Failures localize to a
   stage instead of surfacing as a symptom several stages downstream.
4. **A validator pipeline appears** that has no analogue today, running on its
   own clock and producing the coverage number that replaces "DRC = 0".
5. **Design and pipeline are parallel branches**, converging only at
   "order boards".

### Checks by stage

| Stage | Checks | Cost |
|-------|--------|------|
| Netlist | isolation-domain reachability, voltage-domain compatibility, single-pin nets, unconnected power pins, part stress vs. abs-max | ms |
| Placement | inside-outline, courtyard, decoupling proximity, HV keepout, congestion estimate | ~1 s |
| Routing | clearance, ampacity, loop area, return-path continuity | ~100 s |
| Manufacturing | DFM, fab-house rule set | s |

### Loop cadence

| Loop | Runs | Wall time |
|------|------|-----------|
| Netlist | every schematic edit | ms |
| Placement | every placement iteration | ~1 s |
| Route | when placement stabilizes | ~100 s |
| Validator | when checks change | minutes |
| Simulation | batch, not a loop (`METHODOLOGY.md` §3.2) | hours |

Today only the ~100 s route loop exists.

### Code impact

- **New**: netlist-stage checks, seam preconditions, fault-injection harness,
  corpus specificity run, ERC, SPICE harness, congestion predictor
- **Modified**: `route_pcb()` gains semantic net metadata; checks return cost +
  threshold rather than bool; the ledger's `IMBALANCED` gates instead of prints;
  DRC output gains severity tiers
- **Unchanged**: A* kernel, CP-SAT placer core, zone pours, KiCad I/O

The router barely changes. What changes is what it is told to optimize and what
is asserted around it.

### Risk

This adds stages, and stages are where the reference failure lived. Per
`METHODOLOGY.md` §3.3, contracts and the validator pipeline land **before** the
check corpus grows. A pipeline with more stages and no seam assertions is
strictly worse than what exists today.

---

## Build order

Steps 1–4 build the validator for the validators before scaling check count —
principle 2 gating principle 4, applied to the plan itself.

| # | Work | Rationale |
|---|------|-----------|
| 1 | `kicad-cli sch erc` | Free, today, largest unexplored surface |
| 2 | Seam contracts + footprints-inside-outline precondition | Eliminates the §7 bug class; prerequisite to all decomposition (`METHODOLOGY.md` §3.3) |
| 3 | Make existing detectors gate; anti-vacuous-truth guards; the 9 metamorphic relations | Targets failure classes 3/4/6 using machinery already present |
| 4 | Fault-injection harness, ~10 defect classes, **with injector self-verification** | Coverage number exists from check #1; an unverified injector yields false confidence (`METHODOLOGY.md` §5) |
| 5 | Corpus specificity run | False-positive oracle; corpus already exists |
| 6 | Netlist isolation-domain + voltage-domain checks | Safety-critical, milliseconds, currently absent; the most validatable loop we have (§3.2) |
| 7 | Datasheet → check extraction, provenance-tiered | Scales with part count |
| 8 | Block decomposition of routing on the atopile hierarchy | Only after step 2. Subdivides the one loop that is still monolithic (`METHODOLOGY.md` §3.4) |
| 9 | ngspice harness; ZVS sweep first; models tagged uncalibrated | Highest simulation return |
| 10 | Revive physics branches — **thresholds first, cost fields second** | Router objective function, under threshold subordination (`METHODOLOGY.md` §6.3) |
| 11 | Convert `docs/solutions/` prose to checks + injections | Turns on the flywheel |

Rungs of constraint tightening (`METHODOLOGY.md` §10) run alongside, starting at
rung 1.

---

## Track status

WIP limit: **one track.** Tracks are independently plannable, not independently
shippable.

| Track | State | Gate advanced |
|-------|-------|---------------|
| Verification correctness | **ACTIVE** | prerequisite to all |
| Pipeline (place & route) | paused pending track 1 | none directly |
| Design validation (ERC, sim, review) | runs in parallel — independent loop | prerequisite to all |
| Fabrication + bench | blocked on design validation | all 22 |
| Router/placer hygiene | **HALTED** | none |

Reopening the hygiene track requires a stated reason logged against this
section.

---

## Superseded

- Strategy v1.0's "Strategy-Level Move Set" (moves 1–4, 2026-07-24) — moves 1
  and 2 were premised on the router-capacity reading of the §7 failure.
- `docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md` — the fix
  was correct; the framing was not. The gate was reporting an invalid board.
- `docs/plans/2026-07-24-002-feat-pivot-to-fab-ready-board-verdict-plan.md` —
  its verdict layer is superseded by the check corpus with provenance tiers.
- Any recorded router completion figure predating 2026-07-25.

A sweep of the remaining 143 plans for superseded status is outstanding.
