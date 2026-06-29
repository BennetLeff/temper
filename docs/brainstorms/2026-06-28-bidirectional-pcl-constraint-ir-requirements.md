---
date: 2026-06-28
topic: bidirectional-pcl-constraint-ir
---

# Bidirectional PCL Constraint IR

## Summary

PCL becomes the unified Constraint Intermediate Representation for the temper pipeline. Every
PCL constraint carries multi-backend compilation targets: downward to JAX placement loss terms
(already working via `pcl/loss_bridge.py`), downward to SAT routing clauses (missing), and
downward to DRC assertions (post-route). Upward: SAT UNSAT cores compile to new PCL
constraints that trigger re-placement. The PCL type system serves as shared vocabulary —
placement and routing never need knowledge of each other's internals.

This replaces two architecturally isolated constraint systems (PCL's 7-type placement
language and the SAT model's 3-type routing language) that currently share no data path,
causing correctness gaps such as the documented 6mm HV creepage bug where the router knew
about creepage but the placer was blind to it.

---

## Problem Frame

### Current state

**Two completely separate constraint systems exist with no data path between them:**

| System | Types | Downstream consumer | Status |
|---|---|---|---|
| PCL (`pcl/constraints.py`) | 7 (Adjacent, Separated, Enclosing, Aligned, OnSide, Anchored, LoopArea) | JAX loss terms via `pcl/loss_bridge.py` | Working |
| Routing SAT (`router_v6/constraint_model.py`) | 3 (Capacity, DiffPair, Layer) | splr CDCL solver via `router_v6/pipeline.py` | Working |

The lack of a data path causes concrete failures:

- **6mm HV creepage bug** (documented in `docs/ideation/2026-06-28-sat-constraint-type-system-ideation.md:14`):
  The 6mm IEC 60335-1 creepage was known to the router (encoded as clearance on obstacle expansion
  and in the DRC oracle) but invisible to placement — the PCL `SeparatedConstraint` for HV/LV
  isolation was never forwarded to the SAT constraint model. Placement could propose positions
  within 6mm of HV components; routing would then fail with no feedback explaining why.

- **10 stuck nets** (documented across multiple brainstorms): The 33% completion wall exists because
  HV nets with 6mm clearance requirements compete for scarce channels after LV nets have already
  consumed them. Neither the placer nor the SAT solver has a shared model of which nets require
  which channel privileges.

- **UNSAT opacity**: When the SAT solver returns UNSAT, the only signal back to the pipeline is a
  boolean `status = "unsat"`. There is no mechanism to extract *why* routing failed and feed that
  back to placement. `pipeline/derivation.py:65` has an explicit TODO: "Implement
  back-propagation to PCL constraints."

- **PCL→SAT gap**: `constraint_model.py`'s `ModelBuilder` builds capacity, diff-pair, and layer
  constraints purely from skeletons, nets, and design rules. It has zero awareness of PCL
  constraints. A `SeparatedConstraint(HV_ZONE, MCU_ZONE, min_distance_mm=6.0)` that the placer
  respects never produces a corresponding SAT channel-ordering or capacity constraint.

### Desired state

PCL becomes the single constraint IR. Each PCL constraint declares its compilation targets
(`jax`, `sat`, `drc`). New constraint types auto-gain SAT grounding through the shared type
system. When routing fails, the UNSAT core is compiled back into new or escalated PCL
constraints, closing the feedback loop.

---

## Actors

- **A1. Designer / Constraint Author** — writes PCL YAML; expects constraints to be respected
  by both placement and routing without duplicate specification.
- **A2. Placer Developer** — adds a new PCL constraint type; expects SAT grounding to be
  derived automatically or with minimal explicit mapping.
- **A3. Router Developer** — works on the SAT solver; consumes constraints through the PCL IR
  without needing to understand placement internals.
- **A4. CI / Verification** — runs deterministic tests asserting that PCL constraints produce
  equivalent SAT constraints and that feedback loops close under known failure cases.

---

## Key Flows

### Flow 1: Downward compilation (PCL → multi-backend)

```
Input: PCL ConstraintCollection (YAML or programmatic)
├── PCL→JAX (existing, loss_bridge.py)
│   └── Produces: LossFunction list for geometric optimization
├── PCL→SAT (new)
│   └── Produces: ConstraintModel entries (CapacityConstraint, OrderConstraint, etc.)
└── PCL→DRC (new)
    └── Produces: DRC assertion list for post-route validation
```

### Flow 2: Upward compilation (SAT UNSAT → PCL)

```
Input: SAT UNSAT core from splr
├── Parse minimal conflict clause set
├── Map SAT variable names → component/zone references
├── Compile to new PCL constraints:
│   ├── SeparatedConstraint if part A logically must be farther from part B
│   ├── Escalated tier on existing constraints that appeared in conflict
│   └── AdjacentConstraint if ordering inversion could resolve a bottleneck
└── Output: PCL ConstraintCollection diff → re-trigger placement loop
```

### Flow 3: Type-system auto-grounding

```
New PCL type registered (e.g., "Creepage" constraint)
├── Type inherits BaseConstraint
├── Default SAT grounding derived from type semantics:
│   ├── "Separation" family → SAT channel ordering + capacity reservation
│   ├── "Adjacency" family → SAT proximity preference (soft clause)
│   └── "Zone" family → SAT layer/region restriction
├── Default DRC assertion derived from type semantics
└── Developer overrides only where semantics differ from defaults
```

---

## Requirements

### IR Design

- **R1.** PCL `BaseConstraint` gains a `targets` field (`list[Literal["jax", "sat", "drc"]]`)
  defaulting to `["jax"]`. Constraints where `"sat"` is absent are invisible to the SAT
  compilation pass.

- **R2.** `BaseConstraint` gains a `backends` registry: a `dict[str, Callable]` mapping
  backend name to a compilation function. Default entries:
  - `"jax"` → `loss_bridge.constraint_to_loss` (existing)
  - `"sat"` → `sat_bridge.constraint_to_clauses` (new)
  - `"drc"` → `drc_bridge.constraint_to_assertions` (new)

- **R3.** A `CompilationTarget` enum (`JAX`, `SAT`, `DRC`) is added to `pcl/constraints.py`
  alongside the existing enums.

- **R4.** PCL `ConstraintCollection` gains `compile(target: CompilationTarget, context)`
  that iterates all constraints, dispatches to the registered backend function, and returns
  the appropriate output type (`list[LossFunction]`, `ConstraintModel`, `DRCAssertionList`).
  `compile()` SHALL pass a `Context` object containing: `constraint` (`BaseConstraint`),
  `netlist` (`Netlist`), `board` (`Board | None`), `skeletons`
  (`dict[str, ChannelSkeleton]`), `channel_widths` (`dict[str, ChannelWidths]`),
  `design_rules` (`DesignRules`). Each backend callable accepts
  `(constraint: BaseConstraint, context: Context)` and returns backend-specific
  output.

- **R5.** The existing `pcl/loss_bridge.py` `constraint_to_loss` dispatcher is registered
  as the JAX backend without changing its interface. All seven types remain supported.

### Downward Compilation: PCL → SAT

- **R6.** A new module `pcl/sat_bridge.py` implements the PCL→SAT compilation backend.
  It maps PCL constraint types to SAT constraint types:

  | PCL type | SAT mapping |
  |---|---|
  | `AdjacentConstraint` | Soft clause preferring net-ordering proximity; no hard capacity reservation |
  | `SeparatedConstraint` | Encode minimum channel-distance between net groups; `AtMostK` on shared channels |
  | `EnclosingConstraint` | Restrict net-channel usage to channels within the enclosing zone's spatial extent |
  | `AlignedConstraint` | No SAT grounding (alignment is a placement-only constraint) |
  | `OnSideConstraint` | Channel usage restricted to edges on the specified board side |
  | `AnchoredConstraint` | Pin net-channel variables on channels that include the anchored position |
  | `LoopAreaConstraint` | Encode loop-area bound as combined ordering + proximity constraints on nets in the loop |

  Each semantic constraint SHALL desugar into instances of the EXISTING
  `Constraint` subclasses (`CapacityConstraint`, `DiffPairConstraint`,
  `LayerConstraint`) plus one new `ChannelSeparationConstraint` (defined in
  this feature). `AtMostK` is encoded via the existing `CapacityConstraint` +
  the Sinz sequential counter; "combined ordering + proximity" desugars to
  `CapacityConstraint` with conjunction of `OrderVar` and `LayerConstraint`.

- **R7.** `SeparatedConstraint` with `min_distance_mm` produces a `ChannelSeparationConstraint`:
  for any channel shared by nets from both groups A and B, enforce that the channel's net ordering
  places at least `ceil(min_distance_mm / channel_spacing)` empty slots between them.

- **R8.** PCL constraint tier maps to SAT clause hardness:
  - `HARD` → hard SAT clause (must be satisfied)
  - `STRONG` → weighted clause with high penalty (soft but expensive to violate)
  - `SOFT` → weighted clause with low penalty

  STRONG and SOFT constraints SHALL be encoded using the indicator-variable
  approach: each soft constraint gets a fresh relaxation literal, and an
  `AtMostK` cardinality constraint limits how many relaxation literals can be
  true (K = 0 for STRONG, K = floor(n_constraints * 0.3) for SOFT). In the
  MVP, STRONG and SOFT both SHALL be encoded as hard clauses (no relaxation).
  Full indicator-variable support is deferred until splr gains weighted-clause
  or MaxSAT capability.

- **R9.** The SAT bridge accepts the same `Netlist` and `Board` context objects used by the
  JAX bridge, plus the `ChannelSkeleton` and `ChannelWidths` from Stage 2 of the routing
  pipeline.

- **R10.** PCL constraints whose referenced components/zones cannot be resolved in the current
  netlist/board produce a warning and are skipped (not an error) — this handles components
  that exist in the PCL YAML but are not yet populated in a particular board variant.
  This check runs BEFORE per-type mapping (R6, R7); skipped constraints produce no SAT
  clauses and no DRC assertions. If a constraint references unresolved components, none
  of its bridges fire.

### Downward Compilation: PCL → DRC

- **R11.** A new module `pcl/drc_bridge.py` implements the PCL→DRC compilation backend.
  Each constraint type maps to one or more DRC assertions with clear pass/fail criteria:

  | PCL type | DRC assertion |
  |---|---|
  | `AdjacentConstraint` | Measured pin-to-pin or edge-to-edge distance ≤ `max_distance_mm` |
  | `SeparatedConstraint` | Measured pin-to-pin or edge-to-edge distance ≥ `min_distance_mm`; includes creepage path |
  | `EnclosingConstraint` | All component centroids within zone polygon |
  | `AlignedConstraint` | Maximum deviation from alignment axis ≤ `tolerance_mm` |
  | `LoopAreaConstraint` | Loop polygon area ≤ `max_area_mm2` |
  | `OnSideConstraint` | Component center is within `max_distance_mm` of the specified board edge; component bounding box does not overhang the board (unless `edge=OVERHANG`) |
  | `AnchoredConstraint` | Component center matches the specified position (if given) or lies within the specified region rectangle |

- **R12.** DRC assertions include the source PCL constraint `id` and `because` string so
  violation reports are traceable to designer intent.

### Upward Compilation: SAT UNSAT → PCL

- **R13.** When the SAT solver returns UNSAT, the `TopologicalSolution` gains an optional
  `unsat_core` field: a list of constraint names that form a minimal unsatisfiable set.

- **R14.** A new module `pcl/unsat_compiler.py` implements the UNSAT→PCL upward compiler:

  1. Parse the UNSAT core constraint names
  2. Identify which PCL constraints map to which SAT constraints (maintained in a
     `ConstraintOrigin` registry during downward compilation)
  3. For each conflict:
     - If a PCL constraint with tier < HARD appears in the core → escalate it one tier
     - If the core implicates two components/groups without an explicit PCL constraint →
       synthesize a new `SeparatedConstraint` with the channel bottleneck distance as
       `min_distance_mm` and tier `STRONG`
     - If the core is empty (trivially UNSAT due to board geometry) → emit an
       `InfeasibleConstraintSet` error with diagnostic
  4. Return a `ConstraintCollection` diff containing new and escalated constraints

- **R15.** The UNSAT→PCL compiler has a configurable escalation limit (`max_escalations: int = 3`)
  to prevent infinite escalation loops. Constraints at HARD tier are never escalated further.

- **R16.** Synthesized constraints carry `because = "Synthesized from SAT UNSAT core: <conflict description>"` and
  `id` with prefix `unsat_` for audit-trail traceability.

### Type-System as Shared Vocabulary

- **R17.** `ConstraintType` enum gains a `capabilities` field: a frozen set of semantic tags
  (`SEPARATION`, `PROXIMITY`, `ORDERING`, `ZONING`, `ALIGNMENT`) that downstream compilers
  use to select appropriate grounding strategies without type-specific dispatch.

  | ConstraintType | Tags |
  |---|---|
  | `ADJACENT` | `{PROXIMITY}` |
  | `SEPARATED` | `{SEPARATION, ORDERING}` |
  | `ENCLOSING` | `{ZONING}` |
  | `ALIGNED` | `{ALIGNMENT}` |
  | `ON_SIDE` | `{ZONING}` |
  | `ANCHORED` | `{ZONING}` |
  | `LOOP_AREA` | `{PROXIMITY, ORDERING}` |

- **R18.** The SAT bridge and DRC bridge use `ConstraintType.capabilities` for default
  grounding. A new `AdjacentConstraint`-derived type automatically inherits `PROXIMITY`
  grounding. A new `SeparatedConstraint`-derived type auto-gains ordering and separation.

- **R19.** Constraint types declare which compilation targets they support via a
  `supported_targets` set on `ConstraintType`. `ALIGNED` sets `{JAX, DRC}` but not `{SAT}` —
  the SAT bridge skips it without error. This replaces ad-hoc isinstance checks with
  declarative capability negotiation.

### Backward Compatibility

- **R20.** All existing PCL constraints remain valid without modification. The `targets`
  field defaults to `["jax"]` — no existing code path changes.

- **R21.** The existing `pcl/loss_bridge.py` API (`constraint_to_loss(constraint, netlist, ...)`)
  is unchanged. It is registered as the JAX backend transparently.

- **R22.** The SAT pipeline's `ModelBuilder` accepts an optional `pcl_constraints:
  ConstraintCollection | None = None` parameter. When `None`, behavior is identical to
  current. When provided, the builder calls `pcl_constraints.compile(SAT)` and merges
  the resulting constraints into the model.

- **R23.** The SAT model generated with PCL→SAT compilation is a strict superset of the
  current SAT model for any board where PCL constraints reference only components that
  exist in the netlist. No existing routes are degraded.

### New PCL Types Auto-Gaining SAT Grounding

- **R24.** When a developer creates a new PCL constraint class inheriting from
  `BaseConstraint`, the type inherits `supported_targets` from its `ConstraintType`.
  No additional code is required for SAT grounding unless the type's semantics differ
  from the capability-based defaults.

- **R25.** The SAT bridge has a `register_handler(constraint_type: ConstraintType,
  handler: Callable)` method allowing developers to override the default grounding for
  a specific type without modifying the bridge.

---

## Acceptance Examples

### AE1: HV/LV Separation flows to SAT

```python
# Input PCL
constraint = SeparatedConstraint(
    a="HV_ZONE", b="MCU_ZONE",
    min_distance_mm=6.0,
    tier=ConstraintTier.HARD,
    because="IEC 60335-1 reinforced isolation requirement"
)

# Downward: SAT compilation
sat_constraints = sat_bridge.constraint_to_clauses(constraint, netlist, board, skeletons)
# Produces: ChannelSeparationConstraint ensuring no shared channel within 6mm
#           between nets in HV_ZONE and nets in MCU_ZONE
```

### AE2: UNSAT core produces placement feedback

```python
# Routing returns UNSAT with core
solution = TopologicalSolution(
    status=SolverStatus.UNSATISFIABLE,
    assignment={},
    solver_time_ms=1234.0,
    unsat_core=["cap_L1_E42_HV_ZONE_MCU_ZONE", "sep_enc_zone_hv_zone_mcu_zone"]
)

# Upward compilation
diff = compile_unsat_to_pcl(solution.unsat_core, pcl_constraints, context)
# Produces: escalated SeparatedConstraint(HV_ZONE, MCU_ZONE, tier=HARD) if not already HARD
#           OR new SeparatedConstraint with channel bottleneck distance if constraint absent

# Re-placement loop consumes the diff
```

### AE3: New PCL type auto-gains SAT grounding

```python
class CreepageConstraint(BaseConstraint):
    """New type: enforce creepage distance between pin A on component X and pin B on component Y."""
    constraint_type = ConstraintType.CREEPAGE  # tagged {SEPARATION, ORDERING}
    # developer defines fields: component_a, pin_a, component_b, pin_b, min_distance_mm

# SAT bridge auto-applies {SEPARATION, ORDERING} grounding:
# → ChannelSeparationConstraint
# → OrderConstraint between associated nets
# No handler registration needed
```

### AE4: Backward compatibility

```python
# Fixture: half-bridge board with 12 PCL constraints
collection = ConstraintCollection()
collection.add(AdjacentConstraint(a="Q1", b="Q2", max_distance_mm=10.0))
collection.add(SeparatedConstraint(a="HV_ZONE", b="LV_ZONE", min_distance_mm=6.0))
collection.add(EnclosingConstraint(zone="HV_ZONE", items=["Q1", "Q2", "D1"]))
collection.add(AlignedConstraint(items=["R1", "R2"], axis=AlignmentAxis.HORIZONTAL))
collection.add(OnSideConstraint(items=["J1"], edge=BoardEdge.TOP))
collection.add(AnchoredConstraint(items=["U1"], position=(50.0, 30.0)))
collection.add(LoopAreaConstraint(nets=["HV_OUT", "HV_RTN"], max_area_mm2=100.0))
collection.add(AdjacentConstraint(a="C1", b="C2", max_distance_mm=5.0))
collection.add(SeparatedConstraint(a="Q3", b="Q4", min_distance_mm=8.0))
collection.add(EnclosingConstraint(zone="PWR_ZONE", items=["L1", "C3"]))
collection.add(AlignedConstraint(items=["D2", "D3"], axis=AlignmentAxis.VERTICAL))
collection.add(AnchoredConstraint(items=["J2"], region=Region(0, 0, 100, 50)))

for c in collection:
    assert "jax" in c.targets  # default preserved

# Existing loss bridge works unchanged
losses = [constraint_to_loss(c, netlist, board) for c in collection]
```

---

## Success Criteria

- **SC1.** The 10 currently-stuck HV nets (documented in `docs/ideation/2026-06-28-sat-constraint-type-system-ideation.md`)
  are no longer blocked by the 6mm placement-routing information gap:
  `SeparatedConstraint(HV_ZONE, MCU_ZONE, min_distance_mm=6.0)` produces SAT constraints that
  prevent LV nets from consuming channels within the HV creepage exclusion zone.

- **SC2.** When the SAT solver returns UNSAT on the canonical Temper PCB, the pipeline
  produces at least one synthesized or escalated PCL constraint that, when applied to
  re-placement, changes component positions. The feedback loop reduces UNSAT probability
  by at least one iteration.

- **SC3.** A new PCL constraint type (e.g., `CreepageConstraint` as in AE3) added by a
  developer produces correct SAT clauses and DRC assertions without modifying the SAT
  bridge or DRC bridge. A test verifies this property for all `ConstraintType` tags.

- **SC4.** Existing regression tests pass: all PCL parser tests, all loss bridge tests,
  all SAT constraint model tests, and the deterministic pipeline test suite.
  The pipeline produces bit-identical placement and routing output for boards with no
  PCL→SAT targets.

- **SC5.** A deterministic test verifies that for the canonical Temper PCB with
  `SeparatedConstraint(HV_ZONE, MCU_ZONE, min_distance_mm=6.0)`, the SAT model contains
  at least one `ChannelSeparationConstraint` that would be absent if the PCL constraint
  were removed.

---

## Testing Strategy

- **TS1. Unit tests per bridge module.** `pcl/sat_bridge.py`, `pcl/drc_bridge.py`,
  and `pcl/unsat_compiler.py` each have a `test/` module covering all supported
  PCL constraint types with at least one positive and one edge-case test.

- **TS2. Integration tests for round-trip PCL → SAT → UNSAT → PCL.** A
  deterministic end-to-end test constructs a known-UNSAT constraint set, runs
  it through `compile(SAT)` → solver → `compile_unsat_to_pcl()`, and asserts
  the output diff contains the expected escalated or synthesized constraints.

- **TS3. Property-based tests for constraint equivalence.** For each PCL
  constraint type, `hypothesis`-style tests verify that a PCL constraint
  compiles to SAT clauses that admit exactly the routing solutions the
  placement constraint was designed to permit — no false positives (clauses too
  permissive) and no false negatives (clauses too restrictive).

- **TS4. CI gate for bridge registration completeness.** A CI test enumerates
  all `ConstraintType` members and asserts that each has a registered handler
  in the SAT bridge, a DRC bridge handler (where `DRC` is in the type's
  `supported_targets`), and that the combined set covers all 7 PCL constraint
  types. This gate prevents regressions when new constraint types are added
  without bridge registration.

---

## Scope Boundaries

### In scope

- Adding `targets`, `backends` registry, and `CompilationTarget` enum to PCL
- `pcl/sat_bridge.py`: PCL→SAT compilation for all 7 existing types
- `pcl/drc_bridge.py`: PCL→DRC compilation for types with DRC semantics
- `pcl/unsat_compiler.py`: UNSAT core → PCL constraint diff
- `ConstraintType.capabilities` semantic tagging
- Integration point at `ModelBuilder` for consuming PCL constraints
- `TopologicalSolution.unsat_core` field and extraction from the Rust solver
- Tests for each bridge direction

### Out of scope

- Rewriting the splr CDCL algorithm or the core SAT encoding in `solver.rs`.
  Exposing existing UNSAT-core data through the PyO3 FFI IS in scope.
- Reimplementing the JAX loss bridge (existing `loss_bridge.py` is registered, not rewritten)
- Full constraint at-most-one (AMO) encoding for all PCL→SAT mappings — MVP encodes
  ordering and separation; advanced cardinality is future work
- Automatic PCL constraint discovery from netlist topology — PCL is authored, not inferred
- DRC assertion *execution* — the DRC bridge produces assertions consumed by existing DRC
  infrastructure; it does not replace the DRC oracle
- Real-time interactive constraint editing in a GUI

---

## Key Decisions

- **KD1.** PCL classes use dataclass-like `__init__` (not frozen) to support the
  `escalate()` method. The `backends` registry is a class-level attribute to avoid
  per-instance overhead.

- **KD2.** The SAT bridge uses the existing `ConstraintModel` types (`CapacityConstraint`,
  `OrderVar`, etc.) plus a new `ChannelSeparationConstraint` rather than inventing a new
  intermediate representation. This ensures the Rust solver receives constraints in its
  existing format.

- **KD3.** UNSAT core extraction requires changes to the Rust CDCL wrapper to expose
  conflict clause names. The Python `unsat_compiler.py` operates on names, not raw
  clause objects, keeping the Rust-Python boundary minimal.

- **KD4.** The `ConstraintType.capabilities` approach (semantic tags) is chosen over
  explicit per-type SAT handler registration because it auto-grounds future types and
  reduces the maintenance burden of the 7-type × 3-backend matrix.

- **KD5.** The `ConstraintOrigin` registry (R14) is a bidirectional map maintained during
  downward compilation: `PCL constraint ID → list[SAT constraint names]`. This survives
  only within a single pipeline run — it is not serialized.

---

## Dependencies / Assumptions

### Dependencies

- **D1.** `pcl/constraints.py` — PCL type hierarchy (7 types, `BaseConstraint`, enums)
- **D2.** `pcl/loss_bridge.py` — existing PCL→JAX compiler to be registered
- **D3.** `router_v6/constraint_model.py` — SAT `ConstraintModel`, `Variable`, `Constraint`
  types to target
- **D4.** `router_v6/sat_model.py` — SAT clause encoding and `populate_sat_from_constraints`
- **D5.** `router_v6/pipeline.py` — Rust CDCL solver wrapper; needs `unsat_core` exposure
- **D6.** `pipeline/derivation.py` — `apply_derived_constraints` TODO to be resolved by
  this feature
- **D7.** `temper_rust_router` (Rust crate) — `solve_topology_rust` must return UNSAT
  core data in the result dict
- **D8.** Cross-document dependency: If the constraint combinator library
  (`2026-06-28-constraint-combinator-library-requirements.md`) adds new
  `InternalConstraint` variants, the SAT bridge in this document MUST be updated
  to emit those variants for the corresponding PCL constraint types.

### Assumptions

- **A1.** splr's conflict clause set is accessible via the Rust FFI and can be mapped
  back to named SAT constraints.
- **A2.** The spatial granularity of PCL zone definitions is sufficient to express
  channel-level routing restrictions. If zones are too coarse, the PCL→SAT mapping may
  produce overly conservative constraints.
- **A3.** The SAT model with PCL-derived constraints remains tractable for the canonical
  Temper PCB (23 nets, 2 signal layers). If PCL→SAT compilation produces too many new
  clauses, selective compilation or clause merging will be needed.
- **A4.** `ChannelSkeleton` and `ChannelWidths` are available at the time of PCL→SAT
  compilation (Stage 2 of the routing pipeline). This is already the case in the
  `ModelBuilder` flow.
- **A5.** The `ConstraintCollection` passed to the SAT bridge is the same object that
  was passed to the JAX bridge — they share the same constraint instances and IDs.

---

## Outstanding Questions

- **Q1.** Should UNSAT core compilation produce *multiple* new PCL constraints
  (one per conflict) or a single composite? Current proposal: one per conflict,
  but run a dedup pass to merge constraints with identical component pairs.

- **Q2.** What is the splr UNSAT core API surface? The Rust crate may need a new
  export to expose conflict clause names. Can splr's `Certificate` module provide
  this, or do we need to instrument the CDCL propagate loop?

- **Q3.** Should the PCL→SAT bridge run before or after the existing
  `ModelBuilder._create_capacity_constraints()`? Current proposal: after, with
  PCL constraints added as additional constraints. Ordering constraints can
  reduce capacity pressure by spreading nets across channels.

- **Q4.** How does `ConstraintType.capabilities` interact with types that have
  overlapping semantics? E.g., `LoopAreaConstraint` has `{PROXIMITY, ORDERING}`
  but is not equivalent to `AdjacentConstraint + OrderConstraint`. Answer:
  the SAT bridge dispatches on the *concrete type* first (R25 handler override),
  falling back to capability-based defaults only for unrecognized types.

- **Q5.** Should `ConstraintType.capabilities` be defined on the enum or on the
  constraint class? Proposal: on `ConstraintType` enum to avoid circular imports
  and to make capability lookups a static map.

- **Q6.** Does an escalated constraint (via `escalate()`) auto-update `targets`?
  Current proposal: no — `targets` is set at construction time. If the pipeline
  wants to re-compile an escalated constraint to SAT, it should call `compile(SAT)`
  explicitly.

- **Q7.** What happens when PCL→SAT compilation produces an empty constraint set
  for a board? This is expected for boards with no PCL YAML or PCL YAML that only
  references absent components. The SAT model is valid (but not enriched).

- **Q8.** Performance budget for PCL→SAT compilation: acceptable latency inline
  in the pipeline (Stage 3.1), or should it be a separate stage? Proposal: inline —
  the constraint count is O(dozens), not O(thousands).

- **Q9.** Are UNSAT cores available for UNSAT derived from cardinality constraints
  (`AtMostK`)? The sequential counter encoding adds auxiliary variables; the splr
  UNSAT core may reference auxiliary variables, not the original PCL-derived
  constraint names. Resolution: the `ConstraintOrigin` registry maps auxiliary SAT
  variable names back to original constraint names.

- **Q10.** Should the pipeline automatically re-trigger placement when the UNSAT
  compiler produces new constraints, or should constraint production be a manual
  decision? Proposal: automatic for tier escalation (existing constraint, just
  stronger), manual for synthesized new constraints (require human review of the
  `because` string).
