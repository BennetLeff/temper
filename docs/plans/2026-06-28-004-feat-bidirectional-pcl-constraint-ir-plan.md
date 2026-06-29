---
plan_id: 2026-06-28-004
plan_type: feat
title: "feat: Bidirectional PCL constraint IR — unified placement/routing/DRC constraint system"
status: draft
origin: docs/brainstorms/2026-06-28-bidirectional-pcl-constraint-ir-requirements.md
tags: [pcl, sat, drc, constraint-ir, bridge, bidirectional, unsat-feedback]
---

# feat: Bidirectional PCL constraint IR

## Summary

PCL becomes the unified Constraint Intermediate Representation for the temper pipeline. Every PCL constraint carries multi-backend compilation targets: downward to JAX placement loss terms (already working via `pcl/loss_bridge.py`), downward to SAT routing clauses (missing), and downward to DRC assertions (post-route). Upward: SAT UNSAT cores compile to new PCL constraints that trigger re-placement.

Three new bridge modules map PCL constraint types to their respective backends:
`pcl/sat_bridge.py` (PCL→SAT), `pcl/drc_bridge.py` (PCL→DRC), and
`pcl/unsat_compiler.py` (UNSAT core→PCL diff). A new `ChannelSeparationConstraint`
SAT type encodes the minimum channel-distance between net groups. The
`ConstraintOrigin` registry tracks PCL-to-SAT mapping for upward compilation.

The Rust `solver.rs` already has `solve_with_cadical_cores()` (selector-literal
approach) that returns clause-index UNSAT cores. The Python side wires these
through `TopologicalSolution.unsat_core` and the upward compiler.

---

## Problem Frame

Two completely separate constraint systems exist with no data path between them:

| System | Types | Downstream consumer | Status |
|---|---|---|---|
| PCL (`pcl/constraints.py`) | 7 | JAX loss terms via `pcl/loss_bridge.py` | Working |
| Routing SAT (`router_v6/constraint_model.py`) | 3 | CaDiCaL CDCL via `temper_rust_router` | Working |

This causes:
- **6mm HV creepage bug**: `SeparatedConstraint(HV_ZONE, MCU_ZONE, 6mm)` respected by placement but invisible to SAT routing
- **10 stuck HV nets**: No shared model of which nets require which channel privileges
- **UNSAT opacity**: `pipeline/derivation.py:65` has an explicit TODO for back-propagation
- **PCL→SAT gap**: `ModelBuilder` has zero awareness of PCL constraints

---

## Requirements Trace

Source: `docs/brainstorms/2026-06-28-bidirectional-pcl-constraint-ir-requirements.md`

| R-ID | Summary | Covered by |
|---|---|---|
| R1 | `BaseConstraint.targets` field (`list[Literal["jax","sat","drc"]]`) default `["jax"]` | U1 |
| R2 | `BaseConstraint.backends` registry (`dict[str, Callable]`) | U1 |
| R3 | `CompilationTarget` enum (`JAX`, `SAT`, `DRC`) | U1 |
| R4 | `ConstraintCollection.compile(target, context)` dispatcher | U1 |
| R5 | Register existing `constraint_to_loss` as JAX backend (no interface change) | U1 |
| R6 | `pcl/sat_bridge.py` maps all 7 PCL types to SAT constraint types | U2 |
| R7 | `SeparatedConstraint` produces `ChannelSeparationConstraint` | U2, U3 |
| R8 | Tier maps to SAT clause hardness (MVP: STRONG/SOFT as hard clauses) | U2 |
| R9 | SAT bridge accepts `Netlist`, `Board`, `ChannelSkeleton`, `ChannelWidths` | U2 |
| R10 | Unresolved component/zones produce warning + skip (not error) | U2 |
| R11 | `pcl/drc_bridge.py` maps all 7 PCL types to DRC assertions | U4 |
| R12 | DRC assertions carry source PCL constraint `id` + `because` | U4 |
| R13 | `TopologicalSolution` gains `unsat_core` field | U5, U6 |
| R14 | `pcl/unsat_compiler.py` maps UNSAT cores to escalated/synthesized constraints | U6 |
| R15 | Configurable escalation limit (`max_escalations=3`) | U6 |
| R16 | Synthesized constraints carry `because` + `unsat_`-prefixed `id` | U6 |
| R17 | `ConstraintType.capabilities` (frozen set of semantic tags) | U1 |
| R18 | SAT/DRC bridges use capabilities for default grounding | U2, U4 |
| R19 | `ConstraintType.supported_targets` — declarative capability negotiation | U1 |
| R20 | All existing PCL constraints remain valid without modification | U1 |
| R21 | `constraint_to_loss` API unchanged, registered transparently | U1 |
| R22 | `ModelBuilder` accepts optional `pcl_constraints` parameter | U2 |
| R23 | SAT model with PCL→SAT is strict superset of current model | U2 |
| R24 | New PCL types auto-gain SAT grounding via capabilities | U2 |
| R25 | SAT bridge `register_handler()` for per-type overrides | U2 |

---

## Key Technical Decisions

1. **KD1.** PCL classes remain mutable dataclass-like (`__init__` not frozen) to support `escalate()`. The `backends` registry is class-level to avoid per-instance overhead.

2. **KD2.** SAT bridge uses existing `ConstraintModel` types (`CapacityConstraint`, `OrderVar`, `LayerConstraint`) plus a new `ChannelSeparationConstraint` — no new intermediate representation. Mirrored in both Python `constraint_model.py` and Rust `types.rs` (`InternalConstraint::ChannelSeparation` variant).

3. **KD3.** UNSAT core extraction via `solve_with_cadical_cores()` already exists in Rust (`solver.rs:123`). It returns clause indices using selector-literal instrumentation. The Python side needs to: (a) pass `ConstraintOrigin` names into the Rust solver as clause-name metadata, and (b) map returned indices back to names.

4. **KD4.** `ConstraintType.capabilities` (semantic tags) chosen over explicit per-type SAT handler registration because it auto-grounds future types and reduces the 7-type × 3-backend maintenance matrix.

5. **KD5.** `ConstraintOrigin` registry is a bidirectional map (`PCL constraint ID → list[SAT constraint names]`) maintained during downward compilation. It survives only within a single pipeline run — not serialized.

6. **KD6.** The `construct_constraints_from_derived()` function resolves the TODO at `derivation.py:65` by calling `ConstraintCollection.compile(JAX)` through the loss bridge (already working) and `compile(SAT)` through the new SAT bridge. The derivation module itself does not need to change — the feedback loop at `pipeline/feedback.py` invokes the new compilation paths.

7. **KD7.** STRONG and SOFT tiers in the SAT bridge MVP are encoded as hard clauses (no relaxation literals). Full indicator-variable/MaxSAT support is deferred. See R8.

---

## Implementation Units

### U1. PCL IR extensions: targets, backends, capabilities, CompilationTarget

**Goal:** Extend `pcl/constraints.py` with the new IR fields and types, wire the existing `loss_bridge.py` as the JAX backend, and add `ConstraintCollection.compile()`.

**Requirements:** R1, R2, R3, R4, R5, R17, R19, R20, R21

**Dependencies:** None (foundational unit — all other units depend on this)

**Files:**
| Action | File |
|---|---|
| Modify | `packages/temper-placer/src/temper_placer/pcl/constraints.py` |
| Modify | `packages/temper-placer/src/temper_placer/pcl/parser.py` |
| Modify | `packages/temper-placer/src/temper_placer/pcl/loss_bridge.py` |

**Approach:**

1. **`CompilationTarget` enum** (`constraints.py`):
   ```python
   class CompilationTarget(Enum):
       JAX = "jax"
       SAT = "sat"
       DRC = "drc"
   ```

2. **`SemanticTag` enum** (`constraints.py`):
   ```python
   class SemanticTag(Enum):
       SEPARATION = "separation"
       PROXIMITY = "proximity"
       ORDERING = "ordering"
       ZONING = "zoning"
       ALIGNMENT = "alignment"
   ```

3. **`ConstraintType` gains `capabilities` and `supported_targets`:**
   Replace the current plain `Enum` values with tuples:
   ```python
   class ConstraintType(Enum):
       ADJACENT = ("adjacent", frozenset({SemanticTag.PROXIMITY}), frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}))
       SEPARATED = ("separated", frozenset({SemanticTag.SEPARATION, SemanticTag.ORDERING}), frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}))
       ENCLOSING = ("enclosing", frozenset({SemanticTag.ZONING}), frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}))
       ALIGNED = ("aligned", frozenset({SemanticTag.ALIGNMENT}), frozenset({CompilationTarget.JAX, CompilationTarget.DRC}))
       ON_SIDE = ("on_side", frozenset({SemanticTag.ZONING}), frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}))
       ANCHORED = ("anchored", frozenset({SemanticTag.ZONING}), frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}))
       LOOP_AREA = ("loop_area", frozenset({SemanticTag.PROXIMITY, SemanticTag.ORDERING}), frozenset({CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC}))
   ```
   Add `value`, `capabilities`, and `supported_targets` as `@property` accessors on the enum.

4. **`BaseConstraint` gains `targets` and `backends`:**
   - `targets: list[str]` — defaults to `["jax"]`; validated against `CompilationTarget` values.
   - `backends` is a **class-level** dict (`dict[str, Callable]`) defaulting to `{"jax": constraint_to_loss}`. The `"sat"` and `"drc"` keys are populated by the respective bridge modules at import time (lazy registration pattern).
   - `__post_init__` validates `targets` members are valid `CompilationTarget` values.

5. **`ConstraintCollection.compile()` method** (`parser.py`):
   ```python
   def compile(self, target: CompilationTarget, context: CompilationContext) -> list:
       """Dispatch all constraints to the target backend."""
       results = []
       backend_fn = BaseConstraint.backends.get(target.value)
       if backend_fn is None:
           raise ValueError(f"No backend registered for target: {target}")
       for constraint in self.constraints:
           if target.value not in constraint.targets:
               continue
           # R10: skip unresolved constraints
           if not _is_resolved(constraint, context):
               warnings.warn(f"Constraint {constraint.id} references unresolved components, skipping")
               continue
           results.append(backend_fn(constraint, context))
       return results
   ```

6. **`CompilationContext` dataclass** (new, in `constraints.py` or a shared location):
   ```python
   @dataclass
   class CompilationContext:
       constraint: BaseConstraint
       netlist: Netlist
       board: Board | None = None
       skeletons: dict[str, ChannelSkeleton] | None = None
       channel_widths: dict[str, ChannelWidths] | None = None
       design_rules: DesignRules | None = None
   ```

7. **Loss bridge registration:** In `loss_bridge.py`, at module level:
   ```python
   # Register as the default JAX backend
   BaseConstraint.backends["jax"] = constraint_to_loss
   ```
   The existing `constraint_to_loss` signature `(constraint, netlist, board, zones, loops)` is wrapped in an adapter that destructures `CompilationContext`. The existing callers (`constraint_to_loss` directly) are not affected.

8. **Backward compatibility:** All existing fields (`constraint_type`, `tier`, `because`, `id`) unchanged. `targets` defaults to `["jax"]` — existing PCL YAML and programmatic construction unchanged. `ConstraintType` enum `.value` accessor still returns the string (e.g., `"adjacent"`) for existing serializer consumers.

**Test scenarios:**
- `ConstraintType.ADJACENT.capabilities` returns `{SemanticTag.PROXIMITY}`
- `ConstraintType.ALIGNED.supported_targets` returns `{CompilationTarget.JAX, CompilationTarget.DRC}` (no SAT)
- `BaseConstraint()` defaults to `targets=["jax"]`
- `BaseConstraint(targets=["jax"])` validates; `BaseConstraint(targets=["invalid"])` raises `ValueError`
- `ConstraintCollection.compile(CompilationTarget.JAX, ctx)` dispatches all 7 types
- `ConstraintCollection.compile(CompilationTarget.SAT, ctx)` raises `ValueError` before U2 registers the SAT backend
- Existing `ConstraintType.SEPARATED.value` still returns `"separated"` (string form preserved)
- Existing `constraint_to_loss(c, netlist, board)` calls still work unchanged

**Verification:** All existing PCL parser tests, loss bridge tests pass. `ConstraintCollection.compile(JAX)` produces identical loss functions to the current direct `constraint_to_loss` calls.

---

### U2. PCL→SAT downward bridge (`pcl/sat_bridge.py`)

**Goal:** Create the SAT compilation backend that maps all 7 PCL constraint types into `ConstraintModel` entries (`CapacityConstraint`, `LayerConstraint`, `DiffPairConstraint`, `OrderVar`, plus the new `ChannelSeparationConstraint`).

**Requirements:** R6, R7, R8, R9, R10, R18, R22, R23, R24, R25

**Dependencies:** U1 (PCL IR extensions), U3 (`ChannelSeparationConstraint` type definition)

**Files:**
| Action | File |
|---|---|
| New | `packages/temper-placer/src/temper_placer/pcl/sat_bridge.py` |
| New | `packages/temper-placer/tests/pcl/test_sat_bridge.py` |
| Modify | `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` |
| Modify | `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` |

**Approach:**

1. **`sat_bridge.py` module structure:**

   ```
   pcl/sat_bridge.py
   ├── class ConstraintOrigin  — bidirectional PCL-ID ↔ SAT-constraint-name registry
   ├── class SATBridgeContext   — wraps ChannelSkeleton, ChannelWidths, nets, net_to_idx
   ├── def _resolve_components(constraint, netlist, board) → list[int]  — shared with loss_bridge
   ├── Per-type handlers:
   │   ├── _adjacent_to_sat(constraint, ctx) → list[Constraint]
   │   ├── _separated_to_sat(constraint, ctx) → list[Constraint]
   │   ├── _enclosing_to_sat(constraint, ctx) → list[Constraint]
   │   ├── _onside_to_sat(constraint, ctx) → list[Constraint]
   │   ├── _anchored_to_sat(constraint, ctx) → list[Constraint]
   │   ├── _loop_area_to_sat(constraint, ctx) → list[Constraint]
   │   └── _aligned_to_sat(constraint, ctx) → None  # SKIP — no SAT grounding
   ├── CAPABILITY_HANDLERS: dict[SemanticTag, Callable]  — default grounding by tag
   ├── TYPE_HANDLERS: dict[ConstraintType, Callable]     — per-type dispatch (R25)
   ├── def register_handler(constraint_type, handler)    — R25 public API
   └── def constraint_to_clauses(constraint, context) → list[Constraint]  — main entry
   ```

2. **Per-type mapping logic (reference `constraints.py:161-661` for field names):**

   | PCL type | Field access | SAT output |
   |---|---|---|
   | `AdjacentConstraint` | `c.a`, `c.b` → resolve to net indices | Weighted soft clause preferring same-channel usage. `OrderVar` between nets a,b set to prefer proximity. No hard capacity reservation. |
   | `SeparatedConstraint` | `c.a`, `c.b`, `c.min_distance_mm` | `ChannelSeparationConstraint` between net groups A and B. `AtMostK` (`CapacityConstraint` + Sinz counter) on shared channels. `OrderVar` at least k slots apart. |
   | `EnclosingConstraint` | `c.outer` (zone), `c.inner` (components) | `LayerConstraint` restricting inner-component nets to channels within zone's spatial extent. Computed by checking channel endpoints against zone bounds. |
   | `AlignedConstraint` | `c.components` | **No SAT grounding.** `supported_targets` excludes `SAT`. Handler returns `[]`. |
   | `OnSideConstraint` | `c.components`, `c.side` | `LayerConstraint` restricting net usage to channels on the specified board side. Channel direction vectors used to identify edge-adjacent channels. |
   | `AnchoredConstraint` | `c.component`, `c.position` or `c.region` | Pin `NetChannelVar` to channels that include the anchored position/region. If `position` is set, find channels whose endpoints bracket the position. |
   | `LoopAreaConstraint` | `c.loop_name`, `c.max_area_mm2` | Combined `OrderConstraint` + `CapacityConstraint` (`AtMostK`) on nets in the loop. Restrict shared-channel count to enforce loop area bound. |

3. **`ConstraintOrigin` registry:**
   - Internal dict: `{pcl_id: [sat_constraint_name, ...]}` populated during compilation.
   - Provides `lookup_pcl_id(sat_name: str) → str | None` for upward compilation.
   - Lifecycle: constructed fresh per `constraint_to_clauses()` call; stored on return value or context.

4. **Tier mapping (R8):**
   ```python
   TIER_TO_HARDNESS = {
       ConstraintTier.HARD: "hard",
       ConstraintTier.STRONG: "hard",   # MVP: encode as hard
       ConstraintTier.SOFT: "hard",     # MVP: encode as hard
   }
   ```
   All constraints produce hard SAT clauses in MVP. STRONG/SOFT relaxation deferred.

5. **`ModelBuilder` integration (R22):**
   - Add `pcl_constraints: ConstraintCollection | None = None` parameter to `ModelBuilder.__init__`.
   - After `_create_layer_constraints()`, call a new `_apply_pcl_constraints()` method:
     ```python
     def _apply_pcl_constraints(self):
         if self.pcl_constraints is None:
             return
         from temper_placer.pcl.sat_bridge import constraint_to_clauses
         from temper_placer.pcl.constraints import CompilationTarget
         ctx = CompilationContext(...)
         sat_constraints = self.pcl_constraints.compile(CompilationTarget.SAT, ctx)
         for c_list in sat_constraints:
             for c in c_list:
                 self.model.add_constraint(c)
     ```

6. **`_resolve_components` shared logic (R10):**
   Reuse pattern from `loss_bridge._resolve_to_indices` (`loss_bridge.py:60-97`). If a component ref or zone name cannot be resolved, emit `warnings.warn()` and return `[]`. The compile loop in `ConstraintCollection.compile()` checks for this and skips.

7. **Registration (R5, R24, R25):**
   At module level in `sat_bridge.py`:
   ```python
   from temper_placer.pcl.constraints import BaseConstraint
   BaseConstraint.backends["sat"] = _backend_adapter
   ```
   The `_backend_adapter` destructures `CompilationContext` and calls `constraint_to_clauses`.

   Default capability handlers registered at import:
   ```python
   CAPABILITY_HANDLERS = {
       SemanticTag.SEPARATION: _separation_default,
       SemanticTag.PROXIMITY: _proximity_default,
       SemanticTag.ORDERING: _ordering_default,
       SemanticTag.ZONING: _zoning_default,
       SemanticTag.ALIGNMENT: _alignment_default,  # returns []
   }
   ```
   For unrecognized types, dispatch on capabilities (R24).

8. **Pipeline integration (`pipeline.py:603`):**
   In `_run_stage3()`, after `ModelBuilder(...)`, pass PCL constraints:
   ```python
   model_builder = ModelBuilder(
       ...,
       pcl_constraints=state.pcl_constraints,  # from BoardState or pipeline state
   )
   ```

**Test scenarios:**
- `SeparatedConstraint(HV_ZONE, MCU_ZONE, 6mm)` → produces at least one `ChannelSeparationConstraint`
- `AlignedConstraint([...])` → produces empty list (no SAT grounding)
- `AdjacentConstraint(Q1, Q2, 10mm)` → produces soft `OrderVar` proximity clause
- `EnclosingConstraint(HV_ZONE, ...)` → produces `LayerConstraint` on channels outside zone
- Component ref "NONEXISTENT" in any constraint → warning emitted, skipped
- `ConstraintOrigin` correctly maps PCL IDs to SAT constraint names
- `ModelBuilder(pcl_constraints=collection)` merges PCL→SAT constraints with existing model
- SAT model without `pcl_constraints` is identical to current behavior (R23)
- `register_handler(ConstraintType.SEPARATED, custom_handler)` overrides default
- New type inheriting `{SEPARATION, ORDERING}` auto-grounds via capabilities
- `constraint_to_clauses()` called with tier=STRONG → produces hard clause (MVP behavior)

**Verification:**
- Unit tests in `test_sat_bridge.py` cover all 7 types + edge cases.
- Integration test: `ModelBuilder` with PCL constraints produces superset of current model.
- CI gate: enumeration test asserts all `ConstraintType` members with `SAT in supported_targets` have a handler.

---

### U3. `ChannelSeparationConstraint` — new SAT constraint type

**Goal:** Add a `ChannelSeparationConstraint` to both Python `constraint_model.py` and Rust `types.rs` that enforces minimum channel-distance between two net groups.

**Requirements:** R7 (encoding for `SeparatedConstraint`), KD2

**Dependencies:** U1 (SAT bridge needs this type to exist)

**Files:**
| Action | File |
|---|---|
| Modify | `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` |
| Modify | `packages/temper-rust-router/src/types.rs` |
| Modify | `packages/temper-rust-router/src/encoding.rs` |
| Modify | `packages/temper-rust-router/src/types_py_bridge.rs` |

**Approach:**

1. **Python `constraint_model.py`** — add after `LayerConstraint` (line 121):
   ```python
   @dataclass(kw_only=True)
   class ChannelSeparationConstraint(Constraint):
       """
       Constraint: nets from group A and group B must not share channels
       within `min_slots` slots of each other.
       """
       group_a_indices: list[int]
       group_b_indices: list[int]
       min_slots: int  # ceil(min_distance_mm / channel_spacing)
       channel_id: str
   ```

2. **Rust `types.rs`** — add variant to `InternalConstraint` (line 290):
   ```rust
   pub enum InternalConstraint {
       Capacity { ... },
       DiffPair { ... },
       LayerRestriction { ... },
       ChannelSeparation {
           group_a: Vec<usize>,
           group_b: Vec<usize>,
           min_slots: usize,
           channel_id: String,
       },
   }
   ```

3. **Rust `types_py_bridge.rs`** — add conversion from Python `ChannelSeparationConstraint` pyclass to `InternalConstraint::ChannelSeparation`. The existing `ChannelSeparationConstraint` pyclass (at `constraint_model.py`) is registered with PyO3 for FFI passage.

4. **Rust `encoding.rs`** — encode `ChannelSeparationConstraint` to CNF clauses:
   - For a channel `C`, all nets in group A and all nets in group B that _could_ use `C`:
   - Create `OrderVar` pairs between each (a∈A, b∈B) for channel `C`.
   - Add an `AtMostK` cardinality constraint: at most `min_slots` nets from A∪B share the same channel slot ordering.
   - The encoding uses the existing sequential-counter pattern from `sat_model.py:_encode_at_most_k()`.

5. **`constraint_model.py`**: Register `ChannelSeparationConstraint` in `ConstraintModel.add_constraint()` (similar to existing dispatch at line 141).

**Test scenarios:**
- `ChannelSeparationConstraint(group_a=[0,1], group_b=[2,3], min_slots=2, channel_id="L1_E5")` round-trips through Python→Rust→Python
- Two groups with 0 `min_slots` → constraint is a no-op (trivially satisfied)
- All nets in one group → constraint only restricts cross-group channel sharing
- `ChannelSeparationConstraint` appears in `ConstraintModel.constraints` list
- Rust solver with `ChannelSeparationConstraint` returns SAT when separation is feasible

**Verification:**
- Unit test: Python `ChannelSeparationConstraint` construction and attribute access.
- Unit test: Rust `InternalConstraint::ChannelSeparation` is created from Python bridge.
- Integration test: Rust solver encodes and respects `ChannelSeparationConstraint`.

---

### U4. PCL→DRC downward bridge (`pcl/drc_bridge.py`)

**Goal:** Create the DRC compilation backend that maps all PCL constraint types to DRC assertion specifications.

**Requirements:** R11, R12, R18

**Dependencies:** U1 (PCL IR extensions)

**Files:**
| Action | File |
|---|---|
| New | `packages/temper-placer/src/temper_placer/pcl/drc_bridge.py` |
| New | `packages/temper-placer/tests/pcl/test_drc_bridge.py` |

**Approach:**

1. **`DRCAssertion` dataclass** (in `drc_bridge.py`):
   ```python
   @dataclass
   class DRCAssertion:
       source_id: str       # PCL constraint id (R12)
       source_because: str  # PCL constraint because (R12)
       check_type: str      # "distance", "containment", "alignment", "area"
       subjects: list[str]  # Component refs
       threshold: float     # min/max distance, max area, tolerance
       metric: str          # "edge_to_edge", "center_to_center", etc.
       pass_criteria: str   # Human-readable pass condition
   ```

2. **Per-type mapping logic:**

   | PCL type | `check_type` | Threshold source | Pass criteria |
   |---|---|---|---|
   | `AdjacentConstraint` | `distance_max` | `c.max_distance_mm` | Measured edge-to-edge distance ≤ threshold |
   | `SeparatedConstraint` | `distance_min` | `c.min_distance_mm` | Measured edge-to-edge distance ≥ threshold; includes creepage path |
   | `EnclosingConstraint` | `containment` | `c.margin_mm` | All component centroids within zone polygon (±margin) |
   | `AlignedConstraint` | `alignment` | `c.tolerance_mm` | Maximum deviation from alignment axis ≤ tolerance |
   | `OnSideConstraint` | `edge_proximity` | `c.max_distance_mm` | Component center within threshold of board edge; bounding box does not overhang (unless `edge=OVERHANG`) |
   | `AnchoredConstraint` | `position` | N/A | Component center matches `position` or lies within `region` rectangle |
   | `LoopAreaConstraint` | `area_max` | `c.max_area_mm2` | Loop polygon area ≤ threshold |

3. **`constraint_to_assertions(constraint, context) -> list[DRCAssertion]`** — main entry point, dispatched by `ConstraintCollection.compile(DRC, ctx)`.

4. **Registration:** At module level:
   ```python
   BaseConstraint.backends["drc"] = _backend_adapter
   ```

**Test scenarios:**
- All 7 types produce correct `DRCAssertion` with `source_id` and `source_because` set
- `SeparatedConstraint(a="HV", b="LV", min_distance_mm=6.0)` → `check_type="distance_min"`, `threshold=6.0`
- `AlignedConstraint(components=["R1","R2"], tolerance_mm=0.5)` → `check_type="alignment"`, `threshold=0.5`
- `OnSideConstraint(edge=OVERHANG)` → pass criteria mentions overhang exemption
- `LoopAreaConstraint(max_area_mm2=100.0)` → `check_type="area_max"`, `threshold=100.0`
- Backend registration: `BaseConstraint.backends["drc"]` resolves after import

**Verification:**
- Unit tests cover all 7 types.
- CI gate: enumeration test asserts each `ConstraintType` with `DRC in supported_targets` has assertions.

---

### U5. `TopologicalSolution.unsat_core` — wire Rust UNSAT core to Python

**Goal:** Expose the existing `solve_with_cadical_cores()` UNSAT core through the Python pipeline so the upward compiler can consume it.

**Requirements:** R13, KD3

**Dependencies:** U3 (`ChannelSeparationConstraint` in Rust types, needed for full constraint model passing)

**Files:**
| Action | File |
|---|---|
| Modify | `packages/temper-placer/src/temper_placer/router_v6/topology_solver.py` |
| Modify | `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` |
| Modify | `packages/temper-rust-router/src/lib.rs` |
| Modify | `packages/temper-rust-router/src/solver.rs` (minor — expose clause-name metadata) |

**Approach:**

1. **`TopologicalSolution.unsat_core` field** (`topology_solver.py:25`):
   ```python
   @dataclass
   class TopologicalSolution:
       status: SolverStatus
       assignment: dict[str, bool]
       solver_time_ms: float
       unsat_core: list[str] = field(default_factory=list)  # NEW: constraint names in UNSAT core
   ```

2. **Rust `solve_topology_rust` — already returns `unsat_core`** in the result dict (`lib.rs:95-99`). Currently it returns clause **indices** (`Vec<usize>`). The Python side currently does not read `unsat_core` from the result dict. We need to:
   - In `pipeline.py:_run_stage3()`, read `rust_result.get("unsat_core", [])`.
   - The indices are clause indices in the encoded CNF. We need a mapping from clause index → constraint name.
   - Pass constraint names alongside to the Rust solver (or maintain a Python-side clause-name registry).

3. **Clause-name registry approach:**
   - Before calling `solve_topology_rust()`, build a list `clause_names: list[str]` parallel to the constraints + clauses derived from them.
   - Since `solve_with_cadical_cores()` adds one selector per **clause**, and each Python `Constraint` may produce multiple CNF clauses (e.g., `AtMostK` produces O(n·k) clauses), the registry must map clause index → constraint name.
   - Simplest MVP: track the constraint name that "owned" each clause. The `ConstraintModel.build()` step already has a linear constraint list. After encoding, the number of CNF clauses is known (`num_clauses` in Rust result). We maintain a Python-side array `clause_origin: list[str]` of length `num_clauses`, where each entry is the constraint name.
   - On UNSAT, `rust_result["unsat_core"]` contains clause indices. Map through `clause_origin` to get constraint names.

4. **Pipeline wiring** (`pipeline.py:632`):
   ```python
   rust_result = solve_topology_rust(py_vars, py_cons, net_names)
   # ...
   unsat_core_names = []
   if rust_result["status"] == "unsat":
       core_indices = rust_result.get("unsat_core", [])
       for idx in core_indices:
           if 0 <= idx < len(clause_origin):
               unsat_core_names.append(clause_origin[idx])
   solution = TopologicalSolution(
       status=status,
       assignment=...,
       solver_time_ms=...,
       unsat_core=unsat_core_names,
   )
   ```

5. **Rust side — pass constraint metadata for clause naming:**
   Option A (MVP): Python maintains clause_origin. The Rust solver doesn't need to know names.
   Option B: Pass constraint names as metadata alongside constraints, Rust returns names directly.
   **Choose Option A** for MVP — minimizes Rust changes. The clause index → name mapping is maintained in `pipeline.py`.

**Test scenarios:**
- SAT result: `solution.unsat_core` is empty list
- UNSAT result: `solution.unsat_core` contains constraint names from the conflicting clauses
- `solve_with_cadical_cores()` path exercised (currently pipeline uses `solve_with_cadical` without cores)
- Clause origin array length matches `num_clauses` from Rust result
- Constraint names in unsat_core correspond to actual constraints in the model

**Verification:**
- Unit test: Construct a known-UNSAT constraint model, solve, assert `unsat_core` is non-empty.
- Integration test: Pipeline with conflicting capacity + separation produces UNSAT with named core.

---

### U6. UNSAT→PCL upward compiler (`pcl/unsat_compiler.py`)

**Goal:** Compile SAT UNSAT cores back into new or escalated PCL constraints.

**Requirements:** R14, R15, R16

**Dependencies:** U5 (`TopologicalSolution.unsat_core`), U1 (PCL IR), `ConstraintOrigin` from U2

**Files:**
| Action | File |
|---|---|
| New | `packages/temper-placer/src/temper_placer/pcl/unsat_compiler.py` |
| New | `packages/temper-placer/tests/pcl/test_unsat_compiler.py` |

**Approach:**

1. **`compile_unsat_to_pcl()` function:**
   ```python
   def compile_unsat_to_pcl(
       unsat_core: list[str],
       pcl_constraints: ConstraintCollection,
       origin: ConstraintOrigin,
       context: CompilationContext,
       max_escalations: int = 3,
   ) -> ConstraintCollection:
   ```

2. **Algorithm:**
   For each constraint name in `unsat_core`:
   1. Look up the PCL constraint ID via `origin.lookup_pcl_id(name)`.
   2. If found: find the PCL constraint in `pcl_constraints` by ID.
      - If tier < HARD and `_count_prior_escalations(constraint.id) < max_escalations`:
        escalate the constraint (call `c.escalate()`), add to diff.
   3. If not found: the conflicting SAT constraint has no PCL origin.
      - Identify which components/nets are involved (from SAT variable names in the core).
      - Synthesize a new `SeparatedConstraint` with `min_distance_mm` derived from the channel bottleneck geometry.
      - Set `tier=STRONG`, `because="Synthesized from SAT UNSAT core: <description>"`, `id=f"unsat_{description_hash}"` (R16).
   4. If core is empty: emit `InfeasibleConstraintSet` error.

3. **`_derive_bottleneck_distance()` helper:**
   - Given the channel IDs and net indices in the unsat core, compute the minimum feasible separation distance from channel spacing metadata in `context.channel_widths`.
   - `min_distance_mm = min_slots * channel_spacing_mm + safety_margin`.

4. **Deduplication:** Before returning, merge constraints with identical `(a, b)` component pairs at the same tier. Take the maximum `min_distance_mm`.

5. **Escalation tracking (R15):**
   - `_escalation_counts: dict[str, int]` — keyed by constraint ID, maintained within a pipeline run.
   - `max_escalations` default 3. Constraints at HARD tier are never escalated further.

6. **Integration with feedback loop:**
   - In `pipeline/feedback.py` or `pipeline/derivation.py`, when `solution.status == UNSATISFIABLE`:
     - Call `compile_unsat_to_pcl(solution.unsat_core, pcl_constraints, origin, ctx)`.
     - Merge the diff into `pcl_constraints`.
     - Re-trigger placement loop with the augmented constraints.

**Test scenarios:**
- Core with known PCL constraint at STRONG tier → escalated to HARD
- Core with known PCL constraint at HARD tier → NOT escalated (already max)
- Core with unknown constraint name → new `SeparatedConstraint` synthesized with `unsat_` prefix
- Empty core → `InfeasibleConstraintSet` raised
- Multiple conflicts with same component pair → deduplicated to single constraint with max distance
- Escalation counter prevents infinite loops: 4th escalation of same constraint → skipped
- Synthesized constraint carries `because` string referencing the conflict description
- `ConstraintCollection` diff is a valid `ConstraintCollection` that passes PCL validation

**Verification:**
- Unit tests cover all branches: escalation, synthesis, dedup, empty core, max escalation limit.
- Integration test: UNSAT core from known Temper PCB failure case → produces expected PCL diff.

---

### U7. Integration: pipeline end-to-end feedback loop

**Goal:** Wire the bidirectional compilation pipeline into `pipeline/feedback.py` and `pipeline/derivation.py`, enabling automatic placement-routing iteration.

**Requirements:** R14 (integration point), resolves TODO at `derivation.py:65`

**Dependencies:** U1–U6 (all preceding units)

**Files:**
| Action | File |
|---|---|
| Modify | `packages/temper-placer/src/temper_placer/pipeline/derivation.py` |
| Modify | `packages/temper-placer/src/temper_placer/pipeline/feedback.py` |
| Modify | `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` |
| New | `packages/temper-placer/tests/pipeline/test_bidirectional_feedback.py` |

**Approach:**

1. **Resolve `derivation.py:65` TODO:**
   ```python
   def apply_derived_constraints(
       netlist: Netlist,
       derived: dict[str, Any],
       pcl_constraints: ConstraintCollection | None = None,
   ) -> ConstraintCollection | None:
       """Apply derived constraints back to PCL.
       
       When pcl_constraints is provided, synthesized constraints from
       derivation are added to it. Returns the modified collection.
       """
       if pcl_constraints is None:
           return None
       # Synthesize constraints from derived dict
       for key, value in derived.items():
           if key.endswith("_min_clearance"):
               ref = key.replace("_min_clearance", "")
               pcl_constraints.add(SeparatedConstraint(
                   a=ref, b="*",
                   min_distance_mm=value,
                   tier=ConstraintTier.STRONG,
                   because=f"Derived from thermal spec: {ref} power={...}"
               ))
       return pcl_constraints
   ```

2. **Feedback loop augmentation** (`feedback.py`):
   - After routing returns UNSAT, call `compile_unsat_to_pcl()`.
   - Merge diff into the active `ConstraintCollection`.
   - The existing `run_feedback_loop()` function (`feedback.py:211`) gains a new path: when `status == UNSAT`, generate PCL adjustments via unsat compiler.

3. **Pipeline `_run_stage3()` modification** (`pipeline.py:594`):
   - Build `clause_origin` list during `ModelBuilder.build()`.
   - Extract `unsat_core` from Rust result.
   - Populate `TopologicalSolution.unsat_core`.
   - On UNSAT, store the `unsat_core` on `BoardState` or `PipelineState` for the feedback loop to consume.

4. **`BoardState.pcl_constraints` field:**
   The `BoardState` dataclass (deterministic pipeline) gains an optional `pcl_constraints: ConstraintCollection | None = None` field. This carries the PCL context through stages.

**Test scenarios:**
- Pipeline with `SeparatedConstraint(HV_ZONE, MCU_ZONE, 6mm)` → SAT model contains `ChannelSeparationConstraint`
- Pipeline with intentionally conflicting constraints → SAT returns UNSAT with named core
- UNSAT → `compile_unsat_to_pcl()` produces at least one new/escalated constraint
- Re-placement with escalated constraint → different positions
- Full round-trip: PCL → JAX placement → SAT routing → (UNSAT) → PCL diff → re-placement
- Existing deterministic pipeline tests pass with no PCL→SAT targets (backward compatibility SC4)
- Canonical Temper PCB with PCL constraint → SAT model contains expected `ChannelSeparationConstraint` (SC5)

**Verification:**
- Integration test: end-to-end feedback loop with a known-UNSAT constraint set.
- Regression: all existing router-v6 tests, loss bridge tests, PCL parser tests pass.

---

### U8. Test suite: unit + integration + property + CI gates

**Goal:** Comprehensive test coverage for all new modules and the bidirectional flow.

**Requirements:** TS1, TS2, TS3, TS4 (from requirements doc testing strategy)

**Dependencies:** U1–U7

**Files:**
| Action | File |
|---|---|
| New | `packages/temper-placer/tests/pcl/test_sat_bridge.py` |
| New | `packages/temper-placer/tests/pcl/test_drc_bridge.py` |
| New | `packages/temper-placer/tests/pcl/test_unsat_compiler.py` |
| New | `packages/temper-placer/tests/pipeline/test_bidirectional_feedback.py` |
| New | `packages/temper-placer/tests/pcl/test_bridge_registration.py` |
| New | `packages/temper-placer/tests/pcl/test_constraint_type_capabilities.py` |

**Approach:**

1. **TS1 — Unit tests per bridge module:**
   - `test_sat_bridge.py`: Test all 7 PCL types map to expected SAT constraints. Test edge cases (empty zones, unresolved components, zero min_distance). Test tier mapping.
   - `test_drc_bridge.py`: Test all 7 PCL types produce correct `DRCAssertion` objects.
   - `test_unsat_compiler.py`: Test escalation, synthesis, dedup, empty core, max escalation limit.

2. **TS2 — Integration tests for round-trip:**
   - Construct known-UNSAT constraint set.
   - Run through `compile(SAT)` → solver → `compile_unsat_to_pcl()`.
   - Assert output diff contains expected escalated/synthesized constraints.

3. **TS3 — Property-based tests:**
   - For each PCL type with SAT grounding: Hypothesis test that the compiled SAT clauses admit exactly the routing solutions the placement constraint permits.
   - Strategy: generate random component/zones, compile both JAX and SAT, assert constraint equivalence (both accept or both reject a given placement/routing configuration).

4. **TS4 — CI gate for bridge registration completeness:**
   - `test_bridge_registration.py`: Enumerate all `ConstraintType` members. Assert:
     - Each with `SAT in supported_targets` has a SAT handler (via `TYPE_HANDLERS` or `CAPABILITY_HANDLERS`).
     - Each with `DRC in supported_targets` has a DRC handler.
     - `BaseConstraint.backends` contains entries for `"jax"`, `"sat"`, `"drc"`.
   - `test_constraint_type_capabilities.py`: Assert correct capabilities for each type.

5. **Existing regression tests:**
   - All PCL parser tests pass (unchanged API surface).
   - All loss bridge tests pass (unchanged dispatch).
   - All SAT constraint model tests pass (new `ChannelSeparationConstraint` added but existing types unchanged).
   - All deterministic pipeline tests pass (no SAT targets in default PCL YAML).

**Verification:**
- `pytest tests/pcl/` passes all new tests
- `pytest tests/router_v6/` passes all existing + new tests
- `pytest tests/pipeline/` passes
- CI gate test catches unregistered constraint types (prevents future regressions)

---

## Scope Boundaries

### In scope
- `CompilationTarget` enum, `targets`/`backends` on `BaseConstraint`, `ConstraintCollection.compile()`
- `ConstraintType.capabilities` and `supported_targets`
- `pcl/sat_bridge.py` — PCL→SAT for all 7 existing types
- `ChannelSeparationConstraint` — Python + Rust type, encoding in Rust solver
- `pcl/drc_bridge.py` — PCL→DRC assertions
- `pcl/unsat_compiler.py` — UNSAT core → PCL constraint diff
- `TopologicalSolution.unsat_core` field and pipeline wiring
- `ConstraintOrigin` registry
- `ModelBuilder` PCL integration
- All tests (unit, integration, property, CI gate)
- Resolving `derivation.py:65` TODO

### Out of scope
- Rewriting the CaDiCaL CDCL solver or core SAT encoding
- Reimplementing the JAX loss bridge (registered, not rewritten)
- Full At-Most-One cardinality encoding for all SAT mappings — MVP uses `AtMostK` where needed
- Automatic PCL constraint discovery from netlist topology
- DRC assertion **execution** — bridge produces assertions; existing DRC infrastructure consumes them
- STRONG/SOFT tier indicator-variable relaxation — MVP encodes all tiers as hard clauses
- Serialization of `ConstraintOrigin` across pipeline runs

---

## Dependencies / Assumptions

### Dependencies
- **D1.** `pcl/constraints.py` — 7 PCL types, `BaseConstraint`, enums (ready, no changes needed to existing types)
- **D2.** `pcl/loss_bridge.py` — existing `constraint_to_loss` dispatcher (ready for registration)
- **D3.** `router_v6/constraint_model.py` — `ConstraintModel`, `Variable`, `Constraint` types (ready; needs `ChannelSeparationConstraint` added)
- **D4.** `router_v6/sat_model.py` — `_encode_at_most_k` sequential counter (reused by SAT bridge)
- **D5.** `router_v6/pipeline.py` — Rust CDCL solver wrapper; `unsat_core` already returned but not consumed (ready for wiring)
- **D6.** `pipeline/derivation.py` — TODO to be resolved (target file)
- **D7.** `temper_rust_router` — Rust crate with `solve_with_cadical_cores()` already present; needs `ChannelSeparationConstraint` encoding
- **D8.** Cross-dependency: If `2026-06-28-constraint-combinator-library-requirements.md` adds new `InternalConstraint` variants, SAT bridge must emit them.

### Assumptions
- **A1.** `solve_with_cadical_cores()` (already in `solver.rs:123`) correctly returns minimal UNSAT cores via selector-literal instrumentation.
- **A2.** Spatial granularity of PCL zone definitions is sufficient for channel-level routing restrictions.
- **A3.** SAT model with PCL-derived constraints remains tractable for the canonical Temper PCB (23 nets, 2 signal layers).
- **A4.** `ChannelSkeleton` and `ChannelWidths` available at SAT compilation time (Stage 2 output, already the case in `ModelBuilder` flow).
- **A5.** `ConstraintCollection` passed to SAT bridge is the same object passed to JAX bridge — shared instances and IDs.
- **A6.** `hypothesis` and `pytest` are available (already dev dependencies).

---

## Outstanding Questions (from requirements doc, with resolution proposals)

| Q | Question | Proposed resolution for implementation |
|---|---|---|
| Q1 | One composite vs. multiple per-conflict constraints? | One per conflict, with dedup pass merging identical component pairs. |
| Q2 | UNSAT core API surface? | `solve_with_cadical_cores()` already exists. Clause index → name mapping via Python-side `clause_origin` array. |
| Q3 | PCL→SAT before or after `_create_capacity_constraints()`? | After, with PCL constraints added as additional constraints. |
| Q4 | Capabilities vs. concrete type dispatch? | Concrete type first (TYPE_HANDLERS), fallback to capabilities for unrecognized types. |
| Q5 | Capabilities on enum or class? | On `ConstraintType` enum — static map, no circular imports. |
| Q6 | Escalated constraint auto-update targets? | No — `targets` set at construction. Pipeline calls `compile(SAT)` explicitly. |
| Q7 | Empty PCL→SAT constraint set? | Expected for boards with no PCL YAML. SAT model valid but not enriched. |
| Q8 | Performance budget? | Inline in Stage 3.1 — O(dozens) constraints, not O(thousands). |
| Q9 | Auxiliary variables in UNSAT core? | `ConstraintOrigin` maps auxiliary SAT variable names to original constraint names. |
| Q10 | Auto vs. manual re-placement trigger? | Auto for tier escalation. Manual for synthesized new constraints (human review of `because` string). |

---

## Success Criteria Trace

| SC | Description | Verified by |
|---|---|---|
| SC1 | 10 stuck HV nets unblocked: `SeparatedConstraint(6mm)` produces SAT `ChannelSeparationConstraint` preventing LV nets from consuming HV channels | U2 test scenarios + U7 integration test |
| SC2 | UNSAT pipeline produces ≥1 synthesized/escalated constraint that changes re-placement | U6 test scenarios + U7 round-trip test |
| SC3 | New PCL type (e.g., `CreepageConstraint` with `{SEPARATION, ORDERING}`) auto-gains SAT grounding without modifying bridge | U2 capability dispatch test |
| SC4 | Existing regression tests pass; pipeline produces bit-identical output for boards with no PCL→SAT targets | U8 regression suite |
| SC5 | Deterministic test: canonical Temper PCB with PCL constraint → SAT model contains expected `ChannelSeparationConstraint` | U7 integration test |
