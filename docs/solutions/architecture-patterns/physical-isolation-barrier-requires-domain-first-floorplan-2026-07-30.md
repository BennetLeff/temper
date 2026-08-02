---
title: "A physical mains-SELV barrier is a floorplan topology, not a keepout annotation"
date: "2026-07-30"
category: architecture-patterns
module: pcb-hardware-design
problem_type: architecture
component: isolation-barrier
severity: critical
applies_when:
  - "a PCB claims a mains-to-SELV isolation boundary"
  - "a keepout must partition two electrical domains across every copper layer"
  - "the existing board already contains mixed-domain components and interleaved placement"
  - "a safety gate requires an edge-to-edge barrier rather than pairwise distance checks"
tags:
  - mains-selv-isolation
  - pcb-floorplan
  - keepout
  - pd2
  - creepage
  - cp-sat
  - compound-engineering
  - falsifiable-design
---

# A physical mains-SELV barrier is a floorplan topology, not a keepout annotation

## Executive decision

The production target is Pollution Degree 2 (PD2), with 8.0 mm reinforced
creepage for the mains-to-SELV board barrier. PD2 is conditional on a covered,
gasketed PCB compartment that is separate from the coil/heatsink forced-air
path. If that mechanical exception is not implemented and verified, the
fallback is PD3 and 12.6 mm reinforced creepage.

The current PCB cannot be closed by drawing the named
`MAINS_SELV_ISOLATION_BARRIER` zone onto the existing placement. The HV and
SELV components are interleaved across the board, so an arbitrary strip would
cut through real pads, footprints, vias, and traces. The barrier must be
created by a domain-first floorplan redesign, followed by routing and then the
keepout annotation. The keepout is the final machine-checkable expression of
the topology, not the topology itself.

This document records the diagnosis, the design alternatives, the recommended
implementation sequence, and the gates that define completion. It deliberately
does not claim the current board is fabrication-ready.

## The failure pattern

The project had several correct declarations:

- `elec/domain_manifest.yaml` identifies HV and SELV nets;
- the requirements validator derives a reinforced creepage requirement;
- the KiCad generator emits a real `creepage` constraint;
- `scripts/check_isolation_keepout.py` exists as a fail-closed physical gate;
- the netlist domain-partition gate verifies galvanic connectivity.

Those facts did not imply that a physical board barrier existed. The current
board measurement examined 169 footprints, 521 pads, 2,482 copper items, and
four copper layers. It found 99 HV pads and 221 SELV pads, but no named
`MAINS_SELV_ISOLATION_BARRIER` zone. A candidate full-height strip at an
arbitrary x-coordinate produced both far-side domain crossings and copper
intrusions; it was correctly discarded.

The earlier placement analysis explains why. The board contains:

| Placement class | Meaning | Current count |
|---|---|---:|
| HV-only | Pads touch HV nets only | 44 historical baseline |
| SELV-only | Pads touch SELV nets only | 106 historical baseline |
| Mixed-domain | The component itself straddles the isolation boundary | 8 |
| Unclassified | Neither declared domain | 10 |

The historical counts differ by a few pads from the current worktree because
the board has moved since the first audit. The structural result is unchanged:
both domains span the board envelope and no simple contiguous corridor exists.
See [`2026-07-28-isolation-keepout.md`](../../evidence/2026-07-28-isolation-keepout.md).

## Why the obvious fixes are wrong

### Drawing the zone first

A zone drawn across the existing board is not a repair. It either:

- crosses pads or footprints belonging to one domain;
- leaves HV or SELV copper on both sides of the partition;
- allows routing around an end if it does not reach both board edges; or
- creates a red DRC/keepout result that someone is tempted to exempt.

The gate's red result is useful evidence. It tells us the board topology is
wrong for the requested invariant.

### Lowering the barrier width

PD2 changes the target from 12.6 mm to 8.0 mm; it does not make an arbitrary
interleaved floorplan partitionable. Lowering the target below 8.0 mm would
change the safety requirement to fit the board and would be an invalid gate
neutering mechanism.

### Exempting mixed-domain footprints

Mixed-domain footprints are expected only at the boundary, and their pads must
land on their respective sides. Exempting them globally would allow the
barrier to pass through an isolator body or a relay's coil/contact geometry.
The correct response is to select a part and land pattern whose physical
primary-to-secondary geometry can straddle the corridor.

### Treating IP20 as proof of PD2

IP20 does not prove that the PCB insulation is protected from conductive
pollution. The PD2 selection requires a separate covered PCB compartment,
isolated from the coil/heatsink airflow path, with assembly and inspection
criteria. The electrical and mechanical decisions are coupled, but neither
substitutes for the other.

## Component consequences at the PD2 target

The current mixed-domain set is `C6`, `K1`, `K2`, `K3`, `PS1`, `T1`, `U3`, and
`U7`. The existing barrier-constrained placement experiment used an 8.5 mm
working corridor (8.0 mm requirement plus 0.5 mm solver/gate margin) and
returned infeasible before the domain-only packing problem was reached. Its
individually blocking set was `C6`, `K1`, `K2`, `K3`, `T1`, `U3`, and `U7`; only
`PS1` cleared that conservative model. The exact 8.0 mm pairwise audit is less
strict for some elongated pads, but still identifies `K2` and `K3` as real
body-crossing failures and several other parts as marginal.

| Ref | Current issue | Required resolution |
|---|---|---|
| C6 | Placeholder Y-cap footprint, not a sourced production part | Select a real safety-rated Y capacitor and land pattern with sufficient lead pitch |
| K1 | General-purpose relay geometry is too close for the conservative barrier model | Select a safety relay with rated coil/contact separation and a verified footprint |
| K2, K3 | G5LE-1 coil/contact pin geometry crosses the barrier | Replace with a relay family designed for reinforced isolation |
| T1 | Current land pattern is marginal under the conservative pad model | Validate a wider land pattern or alternate CT against the physical creepage path |
| U3 | Standard DIP-6 row spacing is too narrow for the solver's corridor | Select a wider reinforced-isolation optocoupler package/land pattern |
| U7 | Current DWK package is marginal under the conservative corridor model | Validate a wider certified package or land pattern; do not infer isolation from omitted pins alone |
| PS1 | Large primary/secondary separation; not the current intrinsic blocker | Retain only after datasheet, footprint, and creepage path are verified |

The part changes are not optional cleanup after placement. Until the boundary
components can physically straddle the corridor, a hard placement solver is
correctly unsatisfiable regardless of board expansion. See
[`barrier-constrained-placement.md`](../../evidence/2026-07-28-barrier-constrained-placement.md)
and [`2026-07-28-isolator-sourcing-brief.md`](../../evidence/2026-07-28-isolator-sourcing-brief.md).

## Architecture alternatives

### Alternative A: single-board domain-first redesign

Rebuild the floorplan around one edge-to-edge barrier:

```text
HV island                 8.0 mm barrier                 SELV island
AC/DC bus ─ IGBT ─ tank    | full-layer keepout |          MCU ─ UI ─ sensors
                           | isolators straddle |
```

Advantages:

- one PCB and one assembly;
- preserves the current external wiring concept;
- directly matches the existing keepout gate and CP-SAT barrier model.

Costs:

- requires the mixed-domain BOM/footprint work above;
- requires a complete placement and routing regeneration;
- may require board-outline or connector changes;
- does not make the current board salvageable by local moves.

### Alternative B: split power and control boards

Put the mains/DC-bus/IGBT/tank circuitry on a power board and the MCU/UI/
sensor circuitry on a SELV control board. Cross-board interfaces must use
certified isolation components and connectors with their own creepage,
clearance, mounting, and contamination assumptions. The isolated auxiliary
supply can remain on the power board if its isolated output is the only
electrical interface to the control board.

Advantages:

- converts a dense two-dimensional interleaving problem into a board-to-board
  interface problem;
- makes the pollution boundary and service partition easier to inspect;
- reduces the amount of existing placement that must be re-solved at once.

Costs:

- adds a board-to-board connector/harness and mechanical retention;
- requires a new interface safety analysis and EMC/return-current analysis;
- does not remove the need for certified isolators or a protected control-board
  compartment.

**Recommendation:** choose Alternative B if production schedule and enclosure
space permit it. Choose Alternative A only if the single-board constraint is
real and the BOM owner accepts the required isolator substitutions. In either
case, start a new board-topology workstream; do not keep editing the current
interleaved board incrementally.

The approved Alternative B contract is now recorded in
`elec/domain_manifest.yaml` as `POWER_CONTROL_SELV_INTERFACE`. The existing
netlist domain gate validates that every enumerated board-to-board net exists
in the compiled design and belongs to the explicitly allowed `SELV` domain;
an HV or unclassified connector net is a gate violation. This closes the
source-level regression hole while the physical power/control PCB artifacts,
connector selection, and mechanical partition remain implementation work.

## Implementation sequence

### Phase 1 — freeze the boundary contract

1. Keep PD2 at 8.0 mm in the KiCad generator and shared isolation constant.
2. Freeze the exact HV/SELV/isolator net manifest.
3. Record the mechanical PD2 enclosure requirements in the assembly drawing.
4. Create a decision record for single-board versus split-board topology.

### Phase 2 — close the component geometry

1. Replace the C6 placeholder with a sourced Y-capacitor footprint.
2. Source compliant replacements for K1–K3.
3. Validate T1, U3, and U7 against primary datasheet land patterns and the
   gate's actual pad-geometry model.
4. Update the schematic, BOM, footprints, and netlist together.
5. Run the component-level creepage audit before invoking placement.

### Phase 3 — solve the floorplan

1. Add a hard 8.5 mm working corridor to the placement model for 0.5 mm
   execution margin above the 8.0 mm requirement.
2. Constrain every HV-only component to the HV side and every SELV-only
   component to the SELV side.
3. Constrain every approved mixed-domain component to straddle the corridor
   with its HV and SELV pads on the correct sides.
4. Require a feasible solver result in both candidate corridor orientations
   before selecting the final axis.
5. Inspect the resulting floorplan visually and against connector, heatsink,
   enclosure, and service constraints.

### Phase 4 — express and route the barrier

1. Import the accepted placement into KiCad.
2. Add `MAINS_SELV_ISOLATION_BARRIER` as a full-copper-layer keepout spanning
   the board edge-to-edge.
3. Add slots or approved creepage geometry under boundary components where the
   validated footprint requires it.
4. Route only after the keepout exists; prohibit traces, vias, pads, and pours
   in the corridor.
5. Run the physical gate and KiCad DRC against the real board.

### Phase 5 — prove the result

The board change is not complete until all of these are true:

| Gate | Required result |
|---|---|
| Domain manifest/netlist partition | No unauthorized galvanic HV/SELV connection |
| Isolation keepout gate | Exit 0; named zone, four copper layers, ≥8.0 mm, two regions, no intrusion/crossing |
| Component creepage audit | No unresolved cross-domain pair below the selected requirement |
| KiCad DRC | No new unexplained errors; creepage rules are actually emitted and run |
| Provenance | Board hash, DRC ceiling, tool version, and measurement commit agree |
| DRC ceiling | Re-measured in the same PR; any rise attributed and approved |
| Mechanical PD2 review | Compartment, gasket, airflow separation, cable penetrations, and inspection points verified |

Any board-changing PR must update `power_pcb_dataset/drc_ceiling.json` in the
same PR. A red keepout gate is a release blocker, not a baseline to ratchet.

## What PR #506 closes

PR #506 selects the conditional PD2 architecture and aligns the 8.0 mm
enforcement points:

- `scripts/generate_kicad_dru.py` emits 8.0 mm reinforced creepage;
- `temper_placer.core.isolation_constants.MIN_BARRIER_WIDTH_MM` is 8.0 mm;
- the regression tests assert the selected PD2 target and retain 12.6 mm as
  the explicit fallback;
- the environmental, airflow, assembly, and high-voltage specification docs
  state the protected-compartment release prerequisite.

PR #506 does **not** modify `pcb/temper.kicad_pcb`, so it does not claim a
fabrication-ready board and does not trigger the board-change DRC-ceiling
remeasurement rule. The current keepout gate remains red because the physical
barrier has not yet been designed.

## Durable lesson

The machine-checkable artifact must be downstream of the physical decision:

```text
environment + enclosure
        ↓
PD2 requirement (8.0 mm)
        ↓
domain-first floorplan + boundary-part BOM
        ↓
edge-to-edge KiCad keepout
        ↓
routing + DRC + provenance
```

Reversing this order produces a familiar failure pattern: a threshold is
corrected, a zone is drawn, a gate is made green by exemptions, and the board
still does not implement the claimed safety boundary. The right response to an
infeasible barrier is to expose the component and topology decisions that make
it infeasible, then solve those decisions in the order the physical design
depends on them.

## Related evidence

- [`2026-07-30-pd2-enclosure-decision.md`](../../evidence/2026-07-30-pd2-enclosure-decision.md)
- [`2026-07-28-isolation-keepout.md`](../../evidence/2026-07-28-isolation-keepout.md)
- [`barrier-constrained-placement.md`](../../evidence/2026-07-28-barrier-constrained-placement.md)
- [`2026-07-29-cross-domain-creepage-pd2-vs-pd3.md`](../../evidence/2026-07-29-cross-domain-creepage-pd2-vs-pd3.md)
- [`2026-07-30-pd3-board-expansion-measurement.md`](../../evidence/2026-07-30-pd3-board-expansion-measurement.md)
- [`2026-07-28-isolator-sourcing-brief.md`](../../evidence/2026-07-28-isolator-sourcing-brief.md)
