---
date: 2026-08-12
topic: placement-model-expressiveness-gaps
focus: What the CP-based placement model (OR-Tools CP-SAT + Pumpkin) cannot say about the mains-voltage cooktop board, and which of those gaps currently matter
status: inventory
---

# Placement Model Expressiveness Audit

## Verdict

The audit found **9 gaps worth ranking** plus one already-owned-elsewhere item
(copper clearance/creepage, noted and not duplicated). Of the 9, **one is a
live, currently-consequential defect on the real board** (#1 below): the
hand-authored PCL config that is supposed to carry this board's thermal and
EMI placement intent (IGBT-to-RTD/MCU heat clearance, commutation/gate-drive
loop-area budgets, HV/LV zone layout) has drifted from the real board's
geometry and component set to the point that it is **infeasible to even run
against the real board**, and the board that actually shipped was placed
without it — meaning nobody has verified that the declared 40mm/25mm thermal
clearances or the loop-area EMI budgets are honored by the current layout.
This is not new (a CI gate already flags the drift), but the audit's
contribution is showing the drift isn't cosmetic (stale zone boxes) — it
silently disconnects *all* of this board's declared thermal/EMI safety intent
from the board that will actually go to fab.

Everything else is either **latent** (a real, structural absence with no
evidence of current consequence — e.g. no layer/side-assignment variable, on
a board that is 100% single-sided today) or **architectural**: a large,
validated, pydantic-typed vocabulary for thermal/noise/loop/group/DFM
constraints exists and is consumed by a *different* placement strategy (the
deterministic/template placer), while the CP-SAT/Pumpkin path this audit
targets can only see 8 low-level geometric primitives. Decoupling-cap-to-pin
proximity — the classic CP placement constraint — is **structurally
inexpressible**: the model has no pad/pin-level geometry at all, only
whole-component bounding boxes. That is a real, foundational absence, but I
found no evidence it is currently biting this board (no failing gate, no
issue), so it is ranked as a note on foundations, not a fire.

I did **not** find the placement model claiming more safety margin than it
has (the one place I checked closely — the HV/SELV isolation-barrier corridor
width — is soundly tied to the SSOT `MIN_BARRIER_WIDTH_MM` and adds a real
0.5mm margin, not a fictitious one). The closer analogue to "optimistic" is
worse than a false number: it's an *absent* number — declared thermal/EMI
margins that were never actually checked against reality. See "Optimistic or
unsafe claims" below.

**Copper clearance/creepage** is a known gap under separate, parallel
investigation (a sibling brainstorm). Noted here once, not re-derived: the
Chebyshev/AABB `SEPARATED` disjunction and the isolation-barrier corridor are
the only clearance-shaped primitives in the CP-SAT/Pumpkin model, and their
precision (rotated-footprint approximation, per-pad vs. per-component
geometry) is that agent's territory.

---

## Method

Top-down: walked thermal, EMI/EMC, mechanical, DFM, signal-integrity, power
delivery, layer-assignment, and orientation concerns against the actual
encoder code and the actual YAML configs used (or not used) for
`pcb/temper.kicad_pcb`. Bottom-up: read every PCL constraint type
(`temper_placer/pcl/constraints.py`), every CP-SAT handler
(`placer/cp_sat/handlers/*.py`), the Pumpkin transcription
(`docs/evidence/2026-08-07-pumpkin-engine/src/main.rs`), and the entire
higher-level pydantic constraint vocabulary (`_constraint_types/*.py`), then
grepped for consumers of each type across `packages/` to establish which
types are wired into the CP-SAT/Pumpkin path versus merely declared.

Everything below separates **what I read** (cited `path:line` + quote) from
**what I inferred**, and names what would confirm an inference cheaply where
I didn't chase it further.

---

## Optimistic or unsafe claims (flagged first, separately from mere gaps)

**Not found**: an explicit numeric margin in the CP-SAT/Pumpkin model that
overclaims safety. The one candidate I checked in depth — the isolation
barrier corridor —is sound:

```
# packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py:139-151
# 0.5mm above the SSOT REINFORCED creepage figure, MIN_BARRIER_WIDTH_MM
...
DEFAULT_CORRIDOR_WIDTH_MM = MIN_BARRIER_WIDTH_MM + 0.5
```

`MIN_BARRIER_WIDTH_MM` is the PD2/8.0mm SSOT figure
(`docs/evidence/2026-08-11-pd2-decision-record.md`, per
`docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md:42-45`,
which confirms the corridor used in the most recent Pumpkin spike is
`[113.0, 121.0]` mm — an 8.0mm span — on the real 152×234mm board). This adds
margin, not fictitious safety.

**What I found instead is arguably a more dangerous failure mode than a
false number: an absent verification.** The hand-authored PCL file carrying
this board's thermal/EMI safety *intent* —
`packages/temper-placer/configs/constraints/thermal_management.yaml` — declares,
in PCL syntax, real numeric clearances derived from real power figures:

```
# packages/temper-placer/configs/constraints/thermal_management.yaml:38-46
  - type: separated
    a: Q1
    b: U_RTD  # RTD (PT1000) interface IC
    min_distance_mm: 40
    tier: 2
    because: "IGBT heat (>30W dissipation) affects RTD measurement accuracy. Need 40mm+ separation for <1°C error."
```

`U_RTD` and `U_MCU` (the two components these thermal separations protect)
**do not exist under those refs on the real board** — confirmed by grepping
`pcb/temper.kicad_pcb`'s `Reference` properties for `rtd|mcu|esp`: zero hits.
And the sibling PCL file with this board's EMI/zone/connector-access intent
(`temper_induction_cooker.yaml`) is independently documented as unusable
against the real board:

```
# packages/temper-placer/tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py:20-34
## Why courtyard + netclass separation, not the full PCL config

``test_golden_board_drc_regression`` solves with the full
``temper_induction_cooker.yaml`` PCL config (zones + named adjacency/enclosing
constraints). Running that same config against the REAL board is infeasible
for BOTH engines -- confirmed independently ... the config's zone/adjacency
assumptions have drifted from the real board's current geometry (e.g.
``enc_HV_ZONE`` assumes a zone box that does not fit the real board's actual
152x234mm extent; the real board's OWN committed, shipped positions already
violate several of the config's own constraints).
```

The practical consequence: the actual solve that produced the currently
committed `pcb/temper.kicad_pcb` did not — could not — use this config
(it's infeasible), so it almost certainly ran on auto-generated netclass +
courtyard `SEPARATED` constraints alone (the same substitute the golden test
itself uses, per its own docstring). **There is today no live check that the
IGBTs are thermally clear of the RTD/MCU by the declared margins, and no
live check on the EMI loop-area budgets**, because the file that encodes
those checks cannot run, and the "production PCL" label
(`docs/evidence/2026-08-11-pumpkin-real-budget-spike.md:161`, calling
`temper_induction_cooker.yaml` "the production PCL" file) is aspirational,
not actual. This already has a CI gate (see "Already tracked," below) but
that gate's own framing ("3 zones outside the real board outline") undersells
the blast radius — it isn't just zones, it's this board's only declared
thermal and EMI margins.

---

## Ranked gap table

| # | Gap | Status | Currently matters? | Impact if fixed |
|---|---|---|---|---|
| 1 | Thermal/EMI/zone PCL intent (`thermal_management.yaml`, `temper_induction_cooker.yaml`) is drifted/infeasible against the real board; the shipped board's placement never ran it | present-but-unwired (config, not code) | **Yes — live, on the current board** | High: restores the only concrete thermal/EMI margin checks this board has |
| 2 | Decoupling-cap-to-pin proximity structurally inexpressible (no pad-level geometry in the CP model at all) | absent | No measured defect found | Medium-high if pursued; foundational, would need a model change (pad vars), not just a new PCL type |
| 3 | Rich domain vocabulary (`ThermalConstraint`, `NoiseIsolationRule`, `CriticalLoop`, `ComponentGroup`, `DifferentialPairRule`, `ManufacturingConstraint`, etc.) has zero consumers in `placer/cp_sat/**`; only the deterministic/template placer reads it | present-but-unwired | No — architectural, explains #1's workaround | Medium: closes the trap where filling in a documented, validated schema field silently does nothing for CP-SAT/Pumpkin |
| 4 | Physics-derived constraint synthesis (`derive_constraints_from_spec`/`apply_derived_constraints`) computes EMI+thermal+SI values but only converts thermal to a PCL constraint, and even that is called only from the offline quality-oracle scorer, never the production solve | present-but-flat (half) + present-but-unwired (all) | No — by its own docstring it isn't meant to constrain the solve | Low-medium: mostly a documentation/consistency fix; EMI/SI derivation being silently dropped is the surprising part |
| 5 | OR-Tools encoder silently **drops** (warn + continue) a PCL constraint of an unregistered type; Pumpkin **aborts** (exit 2) on the same condition | present-but-divergent | No — both back ends currently cover the full 8-type enum | Low now, high if a 9th PCL type is ever added without updating both encoders |
| 6 | No side/layer (top/bottom) assignment variable anywhere in the geometric model | absent | No — board is 100% single-sided today (169/169 footprints on F.Cu) | Low; would matter only if the board goes double-sided |
| 7 | Mounting holes / fiducials: no placement primitive for them, but also none exist as netlist components yet | N/A / moot | No | None until mounting holes/fiducials are added to the netlist — `KEEPOUT` already covers the need |
| 8 | DFM beyond courtyard clearance (pick-and-place access, reflow/wave orientation consistency, silkscreen legibility, testpoint probe access) entirely unexpressed | absent | No measured defect found | Low; no CI gate or issue traces to this today |
| 9 | Component-height / enclosure z-clearance unexpressed | absent / moot | No — no enclosure design committed yet (`docs/brainstorms/2026-07-20-...`: "no case/glass-top tooling committed yet") | None until an enclosure exists |
| — | Copper clearance/creepage precision (AABB approximation, per-pad vs. per-component) | **already tracked, parallel brainstorm in progress** | — | Not re-derived here |

---

## Gap detail

### 1. Thermal/EMI/zone intent is drifted and unenforced on the real board — HIGH, live

**What it is.** `configs/constraints/thermal_management.yaml` and
`configs/constraints/temper_induction_cooker.yaml` are the two hand-authored
PCL files that encode this board's thermal (IGBT-to-sensitive-component
clearance), EMI (commutation/gate-drive loop area), and HV/LV zone/connector
intent, in the model's own native `separated`/`on_side`/`aligned`/`loop_area`
vocabulary — i.e. this is proof the 8-primitive PCL surface *is* expressive
enough to state these requirements. The problem is not expressiveness; it's
that neither file corresponds to the current board.

**Evidence.**
- `thermal_management.yaml:38-46` names `U_RTD`/`U_MCU`; `grep -oP
  '(property "Reference" "\K[^"]+' pcb/temper.kicad_pcb | grep -iE
  "rtd|mcu|esp"` returns nothing — those refs don't exist on the real board.
- `test_golden_board_pumpkin_real_board.py:20-34` (quoted above): running
  `temper_induction_cooker.yaml` against the real board is infeasible for
  both OR-Tools and Pumpkin, and "the real board's OWN committed, shipped
  positions already violate several of the config's own constraints."
- `docs/evidence/2026-08-11-pumpkin-real-budget-spike.md:161` calls
  `temper_induction_cooker.yaml` "the production PCL" file — a label the
  golden test's own comment shows is not actually true of the shipped board.

**Currently matters?** Yes. This is the live board's config, and it can't be
used to verify the live board.

**Already tracked?** Partially — `.github/workflows/python-tests.yml:1927-1941`
("PCL config <-> board correspondence gate (Gate 1)") already runs
`scripts/check_pcl_config_board_correspondence.py` with `continue-on-error:
true`, named as advisory, with its own fix path ("drop/re-target
J_AC_IN/J_COIL/J_DEBUG/Q1/Q2 references, resize the zones to the real
152x234mm board"). Link, don't re-file: this is that gate, not a new one.
What this audit adds is scope — the gate's framing centers on zones; the
audit shows the same drift also orphans every declared thermal clearance and
EMI loop-area budget in `thermal_management.yaml`, which the gate does not
name.

---

### 2. Decoupling-cap-to-pin proximity: absent, structurally — MEDIUM-HIGH (foundational, latent)

**What it is.** The task brief specifically asks whether this is expressible
at all. It is not, and not because of a missing constraint *type* — because
the geometric model has no pin/pad-level variables to attach such a
constraint to.

**Evidence.** Every component's CP variables, in both encoders, are
whole-box only:

```
# docs/evidence/2026-08-07-pumpkin-engine/src/main.rs:117-126
struct CompVars {
    x0: DomainId, y0: DomainId, w: DomainId, h: DomainId,
    cx: DomainId, cy: DomainId, rot: DomainId,
}
```

```
# packages/temper-placer/src/temper_placer/placer/cp_sat/model.py:38-51
class ComponentVars:
    ref: str
    x_center: cp_model.IntVar
    y_center: cp_model.IntVar
    x_size: cp_model.IntVar
    y_size: cp_model.IntVar
    x_start / y_start / x_end / y_end: cp_model.IntVar
    rot_ref: cp_model.IntVar | None = None
```

No pad offsets, no pin index, nothing sub-component. The closest PCL
primitive, `ADJACENT`, is component-center-to-center or edge-to-edge only
(`main.rs:272-312`). `PlacementProximityConstraint` — the type built
specifically for "component output pin close to target input pin"
(`_constraint_types/routing.py:23-37`) — has **zero** references anywhere
under `placer/cp_sat/` (confirmed by grep across the directory).

**Currently matters?** I found no failing gate, open issue, or DRC/ERC
finding attributing a defect to decoupling-cap placement specifically. This
is a note on the model's foundations, not a measured fire — but it is worth
recording plainly because it is the single most textbook CP-PCB-placement
constraint and the model cannot state it at any granularity finer than
"these two whole components are within N mm of each other."

**Cost to fix.** Nontrivial: needs pad-relative coordinates in the model
(both CP-SAT and Pumpkin), not just a new PCL constraint type — the gap is
one level below the constraint layer, in the variable layer.

---

### 3. The rich domain vocabulary is real, validated, and consumed by a different placer — MEDIUM-HIGH (architectural)

**What it is.** `_constraint_types/` defines 34 pydantic models across
`thermal.py`, `noise.py`, `routing.py`, `safety.py`, `groups.py`,
`topology.py`, `clearance.py` — `ThermalConstraint`/`ThermalProperties`,
`NoiseIsolationRule`/`NoiseDomain`, `CriticalLoop`/`CriticalPath`/
`MatchedLengthGroup`/`StarGroundConfig`, `ComponentGroup`/`ProximityRule`/
`GroupSeparation`/`ComponentSpacingRule`/`ManufacturingConstraint`/
`EscapeClearance`, `DifferentialPairRule`/`SignalToHVClearance`,
`SnubberRequirement`/`BleedResistor`/`SkinEffectDerating`. These are real,
schema-validated, and documented (`docs/evidence/2026-08-11-r7-constraint-types-resolution.md`
confirms they're hand-written, load-bearing pydantic contracts, not dead
stubs). All 34 are exposed as fields on `PlacementConstraints`
(`_constraint_types/config.py:240,255,265` for `critical_loops`,
`noise_isolation`, `thermal_constraints`; the container has ~25 more like
them).

**But for the CP-SAT/Pumpkin path this audit targets, none of it exists.**
Grepping every one of the 23 non-`ClearanceRule`/`NetClassRule` type names
against `placer/cp_sat/**` returns **zero hits** for all of them except
`IsolationBarrier` (consumed by `isolation_barrier.py`,
`_encoder_solve.py`). The only reason this isn't "dead code" in a global
sense is that `_constraint_types` **is** wired — into
`ConstraintCompiler`/`temper-constraint-compiler`
(`packages/temper-placer/src/temper_placer/constraints/compiler.py:104-156`,
`builder.py`), which compiles `ThermalConstraint`/`ComponentSpacingRule`/
`ComponentGroup` into slot filter/scorer functions for the **deterministic/
template placer** — a different placement strategy entirely (see
`docs/brainstorms/2026-06-22-placement-routing-pipeline-gap-requirements.md`'s
K1 "strategy pattern"), not the CP-SAT (OR-Tools/Pumpkin) engine that is
`main`'s "sole engine" (`cli/__init__.py:447-449`: `"CP-SAT placer selected
(default)."`).

**Evidence for the wiring gap itself:**

```
# packages/temper-placer/src/temper_placer/pcl/constraints.py:130-161
class ConstraintType(Enum):
    ADJACENT = (...)
    SEPARATED = (...)
    ENCLOSING = (...)
    # (+ KEEPOUT, ALIGNED, ON_SIDE, ANCHORED, LOOP_AREA — 8 total)
```

This is the entire vocabulary the CP-SAT/Pumpkin encoders can see. All 8
have registered handlers on both back ends (see "Solver divergences,"
below) — so there is no *within-PCL* gap. The gap is one layer up: the
YAML schema a designer fills in is much richer than what the running
placer honors.

**Currently matters?** Not directly measurable as a defect (nothing crashes;
a `ThermalConstraint` in YAML that nobody reads just silently has no
effect for CP-SAT/Pumpkin). It is the architectural root of gap #1: the
board's real thermal intent had to be hand-translated into raw
`separated`/`on_side`/`aligned` PCL entries (`thermal_management.yaml`)
specifically *because* there is no path from `ThermalConstraint` to the
CP-SAT encoder.

---

### 4. Physics-derived constraint synthesis is half-dead and decorative — MEDIUM

**What it is.** `derive_constraints_from_spec`
(`packages/temper-placer/src/temper_placer/pipeline/derivation.py:50-106`)
computes real derived placement parameters from `pcb_spec.yaml`'s physical
spec — EMI (`{loop}_max_dist`, `{loop}_max_area_mm2`), thermal
(`{ref}_min_clearance`), signal integrity (`{net}_max_placement_dist`),
safety (`hv_lv_isolation_mm`). `apply_derived_constraints`
(`derivation.py:109-147`) is supposed to feed these back into the PCL
constraint collection as real `SeparatedConstraint`s, but only converts
**thermal**:

```
# packages/temper-placer/src/temper_placer/pipeline/derivation.py:134
extracted = _rs.extract_min_clearance(key, float(value))
```

`extract_min_clearance`'s own name and the surrounding comment ("The
`_min_clearance` suffix test... is the Rust kernel `extract_min_clearance`")
confirm it only matches keys ending in `_min_clearance` — i.e. only the
thermal-derived entries. The EMI (`_max_dist`/`_max_area_mm2`) and SI
(`_max_placement_dist`) derived values, computed two lines above in the same
function, are silently dropped on the floor: `extracted is None` for every
one of them, and the loop just moves on.

**And even the thermal half never reaches the production solve.**
`apply_derived_constraints` is called only from
`temper_placer/regression/physics_oracle.py` (confirmed by grep: every
non-test caller is in that one file) — which says so explicitly:

```
# packages/temper-placer/src/temper_placer/regression/physics_oracle.py:21-23
R1h: this is an ORACLE/comparison kernel, not a physics
gate — it scores a placement, it does not constrain the solve.
```

**Currently matters?** No — this pipeline was never intended to feed the
solve (its own docstring says so for the thermal half too, since the whole
module is an oracle). The finding worth recording is the *inconsistency*:
EMI and SI derivation happening right next to thermal derivation, with only
thermal wired even partway, is exactly the kind of half-finished plumbing
that looks load-bearing and isn't.

---

### 5. Encoder divergence: fail-open vs. fail-closed on an unsupported constraint type — LOW now, HIGH if it fires

**What it is.** Both encoders currently register handlers for the same 8
PCL types (`adjacent`, `aligned`, `anchored`, `enclosing`, `keepout`,
`loop_area`, `on_side`, `separated`) — full 1:1 parity, confirmed by
diffing `handlers/__init__.py:24-31`'s imports against `main.rs`'s `match`
arms. But their behavior on an *unregistered* type diverges completely:

```
# packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_core.py:326-334
handler = HANDLER_REGISTRY.get(c.constraint_type)
if handler is None:
    UNSUPPORTED_TYPES.add(c.constraint_type)
    logger.warning("No CP-SAT handler for constraint type %s (%s)", ...)
    continue
```

```
# docs/evidence/2026-08-07-pumpkin-engine/src/main.rs:535-541
_ => {
    eprintln!("pumpkin_engine: unsupported constraint type {ctype:?}, aborting");
    std::process::exit(2);
}
```

OR-Tools silently **drops** the constraint (model solves as if it were
never declared); Pumpkin **refuses to run at all**. This is exactly the
"gates that pass for unrelated reasons" pattern the task calls out, except
here it would manifest as a solve that silently under-constrains rather
than a gate that passes wrongly.

**Currently matters?** No — both back ends cover the full current 8-member
enum, so `UNSUPPORTED_TYPES` is (as far as I can tell without instrumenting
a live run) always empty today. **What would confirm this cheaply**:
grep/log `UNSUPPORTED_TYPES` after a real board solve, or add a unit test
asserting it's empty post-solve — I did not do this (out of scope: no
solver sources were to be modified, and running a full real-board solve
was not necessary to establish the divergence exists in the code as
written).

---

### 6. No side/layer assignment variable — LOW, latent

**What it is.** `ComponentVars`/`CompVars` in both encoders carry position,
size, and rotation only — no top/bottom flag. `ManufacturingConstraint.side`
(`_constraint_types/groups.py:48-60`) exists in the schema but, per gap #3,
has zero CP-SAT/Pumpkin consumers, so it inherits the same "dead for this
placer" status even if it were populated.

**Currently matters?** No. `grep -oP '\(footprint "[^"]+".*?\(layer
"\K[FB]\.Cu' pcb/temper.kicad_pcb | sort | uniq -c` returns `169 F.Cu` and
zero `B.Cu` — every component on the real board is already single-sided.
Pure latent absence.

---

### 7. Mounting holes / fiducials — N/A today

**What it is.** No placement primitive exists for "avoid this future
mounting-hole/fiducial location" as a distinct concept from a generic
`KEEPOUT` zone.

**Currently matters?** No — `grep -oP 'MountingHole'` and reference-pattern
searches against `pcb/temper.kicad_pcb` return nothing; the board has no
mounting holes or fiducials as netlist entries yet. `KEEPOUT`
(`main.rs:370-393`, `handlers/keepout.py`) already provides exactly the
primitive needed (an arbitrary rectangular exclusion zone) once they're
added — this is not a model gap, it's an unstarted board feature.

---

### 8. DFM beyond courtyard clearance — LOW, latent

**What it is.** Pick-and-place access, reflow/wave-solder orientation
consistency (relevant for polarized THT parts), silkscreen legibility, and
testpoint probe accessibility have no representation in either the schema
or the encoder. `ManufacturingConstraint.allowed_orientations`
(`_constraint_types/groups.py:54`) is the closest schema field and is dead
for CP-SAT per gap #3.

**Currently matters?** No CI gate, issue, or evidence doc traces a defect
to any of these. Genuine absence, unranked urgency.

---

### 9. Component height / enclosure z-clearance — N/A today

**What it is.** No z-axis/height field anywhere in the constraint schema
or CP model (2D-only placement).

**Currently matters?** No — per
`docs/brainstorms/2026-07-20-board-capacity-resolution-and-physical-sequencing-requirements.md`:
"no case/glass-top tooling is committed yet, so Option A (enlarge) is viable
without a blocking mechanical constraint." No enclosure design exists yet
for a height constraint to be checked against.

---

## Solver divergences (CP-SAT vs. Pumpkin) — full inventory

- **PCL primitive coverage: full parity.** All 8 `ConstraintType` members
  (`ADJACENT`, `SEPARATED`, `ENCLOSING`, `KEEPOUT`, `ALIGNED`, `ON_SIDE`,
  `ANCHORED`, `LOOP_AREA`) have registered handlers in both
  `handlers/__init__.py:24-31` and `main.rs`'s `match` (lines 219-534).
  Pumpkin additionally implements `bounded` and `fixed_rotation`
  (`main.rs:420-492`), which are **not** PCL types — they're a
  from-scratch reimplementation of `isolation_barrier.py`'s OR-Tools-
  `CpModel`-coupled HV/SELV barrier logic, needed because that Python
  module can't be called directly from the standalone Rust binary. This is
  already self-documented in the file's own comments (`main.rs:420-441`)
  and is not a capability gap — both ultimately express the same barrier
  constraint via different code paths.
- **Fail-open vs. fail-closed on an unregistered constraint type** — see
  gap #5 above. This is the one real, if currently latent, behavioral
  divergence found.
- **Objectives**: Pumpkin implements both the displacement-repair objective
  (`main.rs:545-563`, mirroring `model.py::add_displacement_objective`) and
  an HPWL wirelength objective (`main.rs:565-603`) that the task brief's
  "established facts" summary didn't mention — worth noting that the
  brief's framing of the current model ("HPWL span + a displacement-repair
  term" as the objective, "only SEPARATED... keepout... margin... rotation
  pinning" as the constraints) underrepresents Pumpkin's actual current
  scope: it already covers the full PCL 8, plus HPWL/displacement
  objectives, plus the isolation-barrier primitives. **Pumpkin is not the
  production engine, however** — `cli/__init__.py:447-449` prints "CP-SAT
  placer selected (default)" with no Pumpkin option, and Pumpkin exists
  only under `docs/evidence/2026-08-*-pumpkin-*` as spike/equivalence-
  harness code, invoked by ad hoc Python scripts that shell out to the
  compiled binary, not from `packages/temper-placer/src/` at all (confirmed
  by grep: zero references to "pumpkin" anywhere under that path except one
  incidental string match in `router_v6/_adapter_convert.py`, unrelated).
  So any Pumpkin-only capability is, by construction, not yet reachable
  from a production board solve.
- **No divergence found** in netclass-aware `SEPARATED` generation: that
  logic runs once in Python
  (`netclass_constraints.generate_netclass_separated_constraints`) and is
  serialized to flat `separated` JSON entries before either engine sees it
  (confirmed by `docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md:33-45`),
  so there's no parallel implementation to diverge.

---

## What I did not chase further

- Whether `UNSUPPORTED_TYPES` (gap #5) is ever actually non-empty on a real
  solve — would need instrumenting a live production run; not done (out of
  the "no solver source changes" boundary and not necessary to establish
  the code-level divergence).
- The exact numeric thermal/EMI violation, if any, on the current board —
  `U_RTD`/`U_MCU` don't exist under those names, so a direct "board violates
  its own declared 40mm clearance by Nmm" measurement isn't possible without
  first re-establishing what the current RTD/MCU-equivalent refs are; the
  stronger, cheaper-to-verify fact (the refs are simply gone) already
  establishes the config is orphaned.
- `_constraint_types/safety.py::IsolationBarrier.clearance_mm` defaults to
  `0.0` ("pure crossing-only semantics" per its own docstring,
  `safety.py:39-49`) — a barrier declared without an explicit `clearance_mm`
  enforces no margin, only a crossing check. This is a distinct object from
  the `isolation_barrier.py` corridor machinery this audit verified sound
  (gap: none found there); whether any *live* `IsolationBarrier` instance on
  this board relies on the `0.0` default is unverified and adjacent to the
  parallel copper-clearance brainstorm's territory — flagged here for that
  agent rather than re-investigated.

---

## Already tracked — linked, not re-reported

- Copper clearance/creepage precision — parallel brainstorm in progress
  (per dispatch instructions), not duplicated.
- PCL config <-> board correspondence drift (zones, component refs) —
  `.github/workflows/python-tests.yml:1927-1941`, Gate 1, advisory
  (`continue-on-error: true`), with its own named fix path. Gap #1 above is
  this same drift, scoped wider (it also orphans the thermal/EMI
  declarations the gate doesn't name).
- `_constraint_types/` migration status (Rust-portability, not
  CP-SAT-wiring) — `docs/evidence/2026-08-11-r7-constraint-types-resolution.md`,
  resolved JUSTIFIED-KEEP. Orthogonal axis to gap #3: that doc answers "can
  this move to Rust," not "does the CP-SAT/Pumpkin placer read it" (it
  doesn't, on either axis).
- Isolator feasibility under the PD2/8.0mm barrier (U6 provably UNSAT
  jointly with 7 others) —
  `docs/evidence/2026-08-12-isolation-barrier-pumpkin-placement.md`; a
  feasibility/BOM finding, not an expressiveness gap, out of this audit's
  scope.
