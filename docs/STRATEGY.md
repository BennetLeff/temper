# Temper Project Strategy

**Version:** 2.0
**Date:** 2026-07-25
**Supersedes:** Strategy v1.0 (2026-06-22) and its "Strategy-Level Move Set"
added 2026-07-24.

How we work lives in [`METHODOLOGY.md`](./METHODOLOGY.md) and should rarely
change. This document holds what we are building and where we honestly are. It
churns by design.

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
- **`Edge.Cuts` is a placeholder** — a single 100 × 150 mm rectangle at the
  origin, while the placement spans x 31.5–145.9, y 30.7–240.4 mm.
  **113 of 149 footprints (76%) lie outside it.** See `METHODOLOGY.md` §7.
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

**79% is not "nearly done."** It is measured on an arbitrary outline with an
unvalidated schematic. It means the infrastructure is far healthier than
previously recorded, not that the board is close.

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

**No ERC has ever been run.** `kicad-cli sch erc` exists and is unused. This is
the largest unexplored validation surface in the project.

### Simulation

`simulation/models/` holds **13 vendor model files and no harness**:
`IKW40N120H3.lib` + `IKW40N120H3_thermal.sub` (IGBT), `pan_load.sub` and
`current_transformer.sub` (tank and sensing), `UCC14140_behavioral.sub`
(isolated gate drive), `TLV3201` + `TPS3700` + `REF2025` (protection
comparators and reference), `LMR51430_avg.lib` + `XC6220_3V3` + `LDO_3V3`
(rails), `SN74LVC1G08` + `SN74LVC1G38` (logic). This is a nearly complete kit
for the power stage and protection chain, with nothing to run it.

### Gates

**0 of 22 measured.** No board has been fabricated. No protection has tripped.
No performance has been observed. Every remaining gate requires physical
hardware.

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
