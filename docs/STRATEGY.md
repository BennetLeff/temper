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
| **Protection gates** | Of seven: **2 now fixed** (OCP-01, THM-01), **2 have no circuit at all**, 1 is ambiguous, 2 are unmeasurable in simulation, 0 validated on hardware |
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
| EFF-01 | Efficiency >90% @1000W | `FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| EFF-02 | Efficiency >92% @1800W | §1.1 |
| EFF-03 | Standby power <1.0W | §1.1 |
| PWR-01 | Power accuracy ±10% @1000W | §1.2 |
| PWR-02 | Power accuracy ±5% @1800W | §1.2 |
| PID-01 | Temperature accuracy ±2°C | §1.3 |
| PID-02 | Temperature stability ±1°C (30min) | §1.3 |
| PID-03 | Overshoot <5°C | §1.3 |
| PID-04 | Settling time <5min | §1.3 |

### Protection

| Gate | Description | Reference |
|------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A, <1µs | `FUNCTIONAL_TEST_CRITERIA.md` §2.1 |
| OCP-02 | Secondary OCP 55-65A, <5µs | §2.1 |
| OVP-01 | DC Bus OVP 390-410V | §2.2 |
| THM-01 | Heatsink NTC 85°C shutdown | §2.3 |
| THM-02 | Coil NTC 120°C shutdown | §2.3 |
| UVL-01 | Gate Drive UVLO <12.0V | §2.4 |
| UVL-02 | Logic UVLO <2.9V | §2.4 |

### EMC

| Gate | Description | Reference |
|------|-------------|-----------|
| EMC-01 | CISPR 14-1 Class B 150-500kHz | `FUNCTIONAL_TEST_CRITERIA.md` §3.1 |
| EMC-02 | CISPR 14-1 Class B 0.5-5MHz | §3.1 |
| EMC-03 | CISPR 14-1 Class B 5-30MHz | §3.1 |

### Mechanical

| Gate | Description | Reference |
|------|-------------|-----------|
| MCH-01 | Button force 2-5N | `FUNCTIONAL_TEST_CRITERIA.md` §4 |
| MCH-02 | Knob torque 0.5-2 N·cm | §4 |
| MCH-03 | Glass load 20kg | §4 |

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
| OVP-01 | 390–410 V | 195.18 V at `v_bus.line` | **AMBIGUOUS** — see below |
| OCP-02 | 55–65 A | — | **NO CIRCUIT EXISTS** |
| THM-02 | coil NTC 120 °C | — | **NO CIRCUIT EXISTS** |
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

**OVP-01 is ambiguous, not failed.** The circuit as wired trips at 195 V
measured at `v_bus.line`. The module's own comment doubles this to 390.4 V by
assuming symmetric bus halves, which this single-ended divider does not verify.
Compounding it, `main.ato` declares `signal dc_bus_plus # +340V` while every
actual use treats it as a 170 V half-bus rail. Resolving OVP-01 requires
deciding what the divider actually senses — a design question, not a
measurement one.

**UVL-02's candidate** (TPS3700 monitoring RTD_AVDD) trips at 2.825 V,
conservatively under the 2.9 V ceiling, but it monitors the RTD subsystem. The
more literal candidate — the TPS3823-33 watchdog supervisor, 2.93 V typ — is
fixed silicon with no model.

**Summary: of seven protection gates, two fail measurably, two have no
circuit, one is ambiguous, and two are unmeasurable in simulation.** None has
been validated on hardware. These are the gates the safety case rests on.

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
