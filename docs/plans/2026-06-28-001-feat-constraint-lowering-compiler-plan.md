---
date: 2026-06-28
type: feat
origin: docs/brainstorms/2026-06-28-constraint-lowering-compiler-requirements.md
---

# feat: Constraint Lattice & Multi-Tier Lowering Compiler

## Summary
A standalone Rust crate `packages/temper-constraint-compiler/` compiles PCL designer-level constraints through 3 desugaring tiers into the existing low-level SAT constraint types (Capacity, DiffPair, LayerRestriction). A Hindley-Milner-style safety-type lattice over HV/LV/AC/iso infers clearances and layer restrictions from pairwise net-type interactions before any SAT clause is generated.

---

## Problem Frame
The routing SAT model (`types.rs`) knows only 3 low-level constraint types: Capacity, DiffPair, LayerRestriction. PCL (`pcl/constraints.py`) defines 7 constraint types (Adjacent, Separated, Enclosing, Aligned, OnSide, Anchored, LoopArea) with HARD/STRONG/SOFT tiers. These two systems are completely separate -- PCL constraints drive JAX placement but have zero representation in the SAT routing stage. `NetClassRules.safety_category` (Literal["HV","LV","AC","iso"]) exists on the 9 net classes in `TEMPER_NET_CLASSES` (`design_rules.py:324-431`) but never reaches the SAT encoder. The 228K-variable blowup case proved selective net construction is essential, but the current approach gives no semantic type-awareness -- it only uses pin count (`max_sat_nets`). Adding a new PCL constraint type today requires modifying the SAT variable schema, the CNF encoder, and every downstream consumer. This compiler eliminates that coupling by defining a lowering pipeline where new constraint types only need desugaring rules at their natural tier.

---

## Key Technical Decisions

1. **Standalone crate with path dependency on `temper-rust-router`**: The lowering pipeline has its own dependency surface (type lattice, desugaring rules, provenance tracking, property-test frameworks) that should not couple to the solver crate's release cycle. A path dependency on `temper-rust-router` keeps the target ISA (`InternalConstraint`, `InternalConstraintModel` in `types.rs:289-312`) in sync without co-locating compiler internals. **Evidence**: `Cargo.toml` format and edition-2024 from the existing crate; `types.rs:289-312` confirms `InternalConstraintModel` is `pub`.

2. **3 desugaring tiers (exactly per requirements R5-R6)**: Tier 0 (PCL IR with component references), Tier 1 (Net-Class-Aware Geometric IR with resolved net indices and concrete distances), Tier 2 (Constraint ISA producing `InternalConstraint` instances). This decouples PCL syntax/component resolution, geometric constraint semantics, and SAT variable mapping into three separate concerns with clear IR boundaries. Fewer tiers force one module to understand both PCL and SAT details; more tiers add abstraction overhead without demonstrated benefit. **Evidence**: PCL types in `pcl/constraints.py` use component reference strings and zone names; the SAT ISA in `types.rs:290-306` uses net indices and channel IDs.

3. **PyO3 bindings as a stateful compiler object + single-shot entry point**: The pipeline orchestrator in `pipeline.py:594-632` calls `solve_topology_rust` between constraint generation and the SAT solve. The compiler must fit into this same synchronous call pattern without network/subprocess overhead. A stateful `PyCompiler` object supports incremental recompilation (R11) while the single-shot `compile_pcl_to_sat()` function covers the initial compilation. The binding shape mirrors `solve_topology_rust` (dict-lists in, dict out). **Evidence**: `lib.rs:26-102` shows the existing PyO3 entry point pattern with `#[pyfunction]`, `PyDict`, `PyList`; `types_py_bridge.rs:6-87` shows the Python-to-Rust bridge pattern.

4. **Target is existing constraint types only -- no new SAT variable types**: The compiler lowers TO the existing `InternalConstraint` variants, not extending them. The Sinz-2005 correctness proof (`encoding.rs:167-181`), the CaDiCaL solver integration (`solver.rs`), and the audit module (`audit.rs`) validate the augmented model without modification. **Evidence**: `InternalConstraint` enum in `types.rs:290-306` has exactly 3 variants; `encoding.rs:111-151` handles each variant in a match arm; `audit.rs:72-125` audits each variant.

5. **Safety-type lattice with externalized clearance values**: The lattice is a function `(net_type_pair, DesignRules) -> InferredConstraintSet`, not a hardcoded table. Clearance values load from `NetClassRules.clearance` and `NetClassRules.creepage_mm` at invocation time via PyO3 dict. The lattice join produces `iso` as a synthetic category (never a source in `TEMPER_NET_CLASSES`), with clearance = max of the two source clearances. **Evidence**: `design_rules.py:115-141` shows `NetClassRules` fields `clearance` and `creepage_mm`; `TEMPER_NET_CLASSES` at lines 324-431 shows only HV/LV/AC as source `safety_category` values.

6. **Provenance metadata as a separate tracking structure, not embedded in constraints**: Every `InternalConstraint` at Tier 2 carries a back-reference chain via a parallel `ProvenanceMap` (clause origin index → `(pcl_constraint_id, desugaring_rule_id, tier)`). This avoids modifying the `InternalConstraint` enum (R10) and keeps provenance out of the SAT encoding path. **Evidence**: `TopologyResult.unsat_core` in `types.rs:347-355` returns `Vec<usize>` of clause indices; `solve_with_cadical_cores()` in `solver.rs:123-240` maps selector literals back to clause indices.

7. **UNSAT provenance emitted as Python objects matching the `audit.rs` pattern**: The existing audit module returns violations as Python dicts through PyO3 (`lib.rs:151-191`). Provenance diagnostics follow the same `PyDict`-per-violation pattern for consistency. **Evidence**: `lib.rs:154-189` shows `AuditViolation` enum serialized to `PyDict` with type-specific fields.

---

## Implementation Units

### U1. Create crate scaffold and dependency graph

- **Goal:** Create `packages/temper-constraint-compiler/` with Cargo.toml, pyproject.toml (maturin), module stubs, and a path dependency on `temper-rust-router` for `InternalConstraintModel` and `InternalConstraint`.
- **Requirements:** R1
- **Dependencies:** None
- **Files:**
  - Create: `packages/temper-constraint-compiler/Cargo.toml`
  - Create: `packages/temper-constraint-compiler/pyproject.toml`
  - Create: `packages/temper-constraint-compiler/src/lib.rs` (PyO3 module entry, `#[pymodule]`, `pub mod` declarations)
  - Create: `packages/temper-constraint-compiler/src/type_lattice.rs` (module stub)
  - Create: `packages/temper-constraint-compiler/src/ir_tier0.rs` (PCL Constraint IR types, module stub)
  - Create: `packages/temper-constraint-compiler/src/ir_tier1.rs` (Geometric IR types, module stub)
  - Create: `packages/temper-constraint-compiler/src/desugar_tier0.rs` (Tier 0 → Tier 1 desugaring, module stub)
  - Create: `packages/temper-constraint-compiler/src/desugar_tier1.rs` (Tier 1 → Tier 2 desugaring, module stub)
  - Create: `packages/temper-constraint-compiler/src/provenance.rs` (provenance tracking, module stub)
  - Create: `packages/temper-constraint-compiler/src/pyo3_bridge.rs` (Python binding layer, module stub)
  - Create: `packages/temper-constraint-compiler/tests/test_type_lattice.rs`
  - Create: `packages/temper-constraint-compiler/tests/test_tier0_to_tier1.rs`
  - Create: `packages/temper-constraint-compiler/tests/test_tier1_to_tier2.rs`
  - Create: `packages/temper-constraint-compiler/tests/test_provenance.rs`
  - Create: `packages/temper-constraint-compiler/tests/test_incremental.rs`
- **Approach:**
  - `Cargo.toml` uses `edition = "2024"`, `crate-type = ["cdylib"]`, dependencies: `pyo3` (mirroring `temper-rust-router`'s version 0.23 with `extension-module`), `temper-rust-router = { path = "../temper-rust-router" }`, `serde = { version = "1", features = ["derive"] }` for IR serialization. Dev-dependencies: `proptest = "1"`.
  - `pyproject.toml` uses `maturin` as build backend matching the `temper-rust-router` pattern.
  - `lib.rs` declares `pub mod` for each source file (8 modules) and registers the PyO3 module with `#[pymodule]`, adding placeholder functions for the two PyO3 entry points: `compile_pcl_constraints()` (single-shot) and `PyCompiler` (stateful).
  - The crate links `InternalConstraintModel`, `InternalConstraint`, `InternalVariable` from `temper-rust-router`'s public `types` module (`temper_rust_router::types::{}`).
- **Patterns to follow:**
  - `packages/temper-rust-router/Cargo.toml` -- edition, crate-type, dependency style
  - `packages/temper-rust-router/pyproject.toml` -- maturin config
  - `packages/temper-rust-router/src/lib.rs:1-211` -- PyO3 module entry, `#[pymodule]`, `#[pyfunction]`
- **Test scenarios:**
  - Crate compiles: `cargo build` in `packages/temper-constraint-compiler/` succeeds
  - Module importable: `import temper_constraint_compiler; dir(temper_constraint_compiler)` shows `compile_pcl_constraints` and `PyCompiler`
  - Path dependency resolves: accessing `temper_rust_router::types::InternalConstraint::Capacity { .. }` compiles
  - `cargo test` runs the placeholder test stubs
- **Verification:**
  - `cargo build` exits 0
  - `python -c "import temper_constraint_compiler"` exits 0
  - `cargo test` reports placeholder tests found (0 pass, 0 fail for stubs)

---

### U2. Safety-type lattice with Hindley-Milner meet/join

- **Goal:** Implement the type lattice over `NetClass` safety categories (HV, LV, AC, iso) with meet/join operations that determine minimum clearance, layer restriction, and separation requirement for any pair of net types. Load clearance values from NetClassRules data at invocation time.
- **Requirements:** R3, R4, R12
- **Dependencies:** U1 (crate scaffold, `type_lattice.rs` module)
- **Files:**
  - Create: `packages/temper-constraint-compiler/src/type_lattice.rs`
  - Modify: `packages/temper-constraint-compiler/src/lib.rs` (register module)
- **Approach:**
  - Define `SafetyCategory` enum: `HV`, `LV`, `AC`, `Iso` where `Iso` is only produced by join, never a source.
  - Define `LatticePair { a: SafetyCategory, b: SafetyCategory }` with precomputed join/meet tables.
  - Join table (commutative, upper-right shown): `HV∨LV = Iso`, `HV∨AC = Iso`, `AC∨LV = Iso`, `HV∨HV = HV`, `LV∨LV = LV`, `AC∨AC = AC`, `iso∨X = iso`. Meet table (most-permissive): `HV∧LV = LV`, `HV∧AC = AC`, `AC∧LV = LV`, `HV∧HV = HV`, `LV∧LV = LV`, `AC∧AC = AC`, `iso∧X = X`.
  - Define `TypeLattice` struct storing a `HashMap<String, NetClassMetadata>` loaded from Python: `{ class_name: { safety_category, clearance, creepage_mm, required_layer } }`.
  - Key method: `infer(net_class_a: &str, net_class_b: &str) -> Option<InferredConstraint>` where the result contains `clearance_floor_mm`, `layer_restriction: Option<String>`, `separation_required: bool`.
  - Clearance floor = `max(creepage_a, creepage_b)` when join yields a category with creepage > 0; `max(clearance_a, clearance_b)` otherwise. For `iso` join: `max(creepage(a), creepage(b))` with a minimum floor of the larger component's creepage.
  - `layer_restriction` is the `required_layer` of the higher-voltage net class (or the HV one if both are HV). If one net has `required_layer = "B.Cu"` and the other has `None`, the pair is layer-restricted for the first net's channels.
  - `separation_required = true` when the join yields `Iso` (different voltage domains must be separated) or `HV` (HV-HV pairs maintain creepage distance).
  - Implement `propagate_through_topology(skeleton_edges: Vec<(usize, usize, String)>, net_class_map: HashMap<usize, String>, lattice: &TypeLattice) -> Vec<InferredNetPairConstraint>` that walks the routing skeleton and produces constraints for every net-pair sharing a channel edge.
  - Filter: only emit constraints where both nets have variables present in the existing `InternalConstraintModel` (respecting `max_sat_nets` selective construction).
  - For `safety_category=None`: warn and exclude from lattice inference; treat as 'unclassified'.
  - `NetClassMetadata` includes `dru_priority: Option<u32>` to inform ordering when multiple `required_layer` constraints conflict.
- **Patterns to follow:**
  - `design_rules.py:337-429` -- the 9 `TEMPER_NET_CLASSES` entries with their `safety_category`, `clearance`, `creepage_mm`, `required_layer` values
  - `_safety_keywords.py:25-31` -- `resolve_safety_category()` pattern for extracting `safety_category` from `NetClassRules`
  - `bottleneck_geometry.py:276-318` -- numeric ranking of safety categories for constraint ordering
- **Test scenarios:**
  - HV-HV pair: lattice infers HV join, clearance_floor = max(clearance_a, clearance_b) (e.g., 6.0 for HighVoltage-HighCurrent), separation_required = true (maintain creepage within HV)
  - HV-LV pair: lattice infers Iso join, clearance_floor = max(6.0, 0.25) = 6.0, separation_required = true
  - LV-LV pair: lattice infers LV join, clearance_floor = max(0.25, 0.15) = 0.25, separation_required = false
  - AC-LV pair: lattice infers Iso join, clearance_floor = max(6.0, 0.25) = 6.0, separation_required = true
  - Iso-X pair: lattice infers Iso join, clearance_floor = max(creepage of both), separation_required = true
  - Layer restriction: HV net with `required_layer = "B.Cu"` paired with LV net with `required_layer = None` → constraint emitted for HV net's channels
  - All 10 unordered pairs of the 4 safety categories exhaustively verified for deterministic join/meet
  - Skeleton walk: 5 nets on 3 channels produce correct per-channel-pair inference vector
  - `safety_category=None` net: excluded from inference with warning logged (does not panic)
  - `net_class_map` miss for a net index: `infer()` returns `None` with warning logged (R12)
- **Verification:**
  - `cargo test --lib type_lattice` -- all unit tests pass
  - Property test: for all 16 combinations of (HV, LV, AC, iso) × (HV, LV, AC, iso), join and meet are commutative, associative, and idempotent
  - Integration: lattice inference on `TEMPER_NET_CLASSES` fixture data produces deterministic, identical results for repeated calls with same inputs

---

### U3. Tier 0 PCL Constraint IR types

- **Goal:** Define the Tier 0 IR representing raw PCL constraint types (Adjacent, Separated, Enclosing, Aligned, OnSide, Anchored, LoopArea) plus lattice-inferred constraints, using component references and zone names.
- **Requirements:** R5, R6
- **Dependencies:** U1 (crate scaffold)
- **Files:**
  - Create: `packages/temper-constraint-compiler/src/ir_tier0.rs`
  - Modify: `packages/temper-constraint-compiler/src/lib.rs` (register module)
- **Approach:**
  - Define `PclConstraint` enum with 8 variants: `Adjacent { id, a: String, b: String, max_distance_mm: f64, tier, because, metric }`, `Separated { id, a: String, b: String, min_distance_mm: f64, tier, because, metric }`, `Enclosing { id, outer: String, inner: Vec<String>, margin_mm: f64, tier, because }`, `Aligned { id, components: Vec<String>, axis, tolerance_mm: f64, tier, because }`, `OnSide { id, components: Vec<String>, side, edge, max_distance_mm: f64, tier, because }`, `Anchored { id, component: String, region: Option<Rect>, position: Option<Point>, tier, because }`, `LoopArea { id, loop_name: String, max_area_mm2: f64, tier, because }`, `InferredSeparation { source_pair: (String, String), clearance_floor_mm: f64, layer_restriction: Option<String>, tier }`.
  - Each variant carries a `ConstraintId(String)`, `tier: ConstraintTier` (Hard/Strong/Soft), and `because: String`.
  - Define `ConstraintTier` enum: `Hard`, `Strong`, `Soft` matching `pcl/constraints.py:45-57`.
  - Define `PclConstraintModel { pcl_constraints: Vec<PclConstraint>, inferred_constraints: Vec<PclConstraint> }` as the entry type from Python.
  - Implement `PclConstraintModel::from_python_dicts(pcl_dicts: Vec<PyDict>, inferred_dicts: Vec<PyDict>) -> PyResult<Self>` in the PyO3 bridge layer (U8), not here -- but the IR types must be ready.
  - Include `Display` impl for each variant producing the `id` + type + component references for diagnostic messages.
- **Patterns to follow:**
  - `pcl/constraints.py:106-661` -- all 7 constraint classes with their field sets, `to_dict()` methods, `ConstraintType` enum, `ConstraintTier` enum
  - `types.rs:264-306` -- `InternalConstraint`, `InternalVariable` enum patterns with named fields
- **Test scenarios:**
  - Round-trip: `PclConstraint::to_dict()` → `PclConstraintModel::from_python_dicts()` produces identical constraint
  - All 7 PCL types parse correctly from Python dict with all optional fields present
  - All 7 PCL types parse correctly with only required fields
  - `InferredSeparation` variant constructed from lattice output (pair of net class names, clearance, optional layer) matches `InferredNetPairConstraint` from U2
  - Invalid tier value raises `PyTypeError` with descriptive message
  - Missing required field raises `PyTypeError` with field name
  - `ConstraintTier` ordering: Hard < Strong < Soft (for priority comparisons)
- **Verification:**
  - `cargo test --lib ir_tier0` -- all unit tests pass
  - Python round-trip test via PyO3: load a real `constraints.py` dict, round-trip through Rust, verify identical fields

---

### U4. Tier 1 Net-Class-Aware Geometric IR types

- **Goal:** Define the Tier 1 IR where component references and zone names are fully resolved to net indices, and constraints carry concrete geometric parameters (min/max distance in mm, layer preference, region bounds).
- **Requirements:** R5, R6
- **Dependencies:** U2 (type lattice for geometric inference), U3 (Tier 0 IR as desugaring source)
- **Files:**
  - Create: `packages/temper-constraint-compiler/src/ir_tier1.rs`
  - Modify: `packages/temper-constraint-compiler/src/lib.rs` (register module)
- **Approach:**
  - Define `ResolvedConstraint` enum: `Separation { id, net_a: usize, net_b: usize, min_distance_mm: f64, tier, provenance: ProvenanceRef }`, `Adjacency { id, net_a: usize, net_b: usize, max_distance_mm: f64, tier, provenance }`, `ZoneEnclosing { id, nets: Vec<usize>, zone_bounds: Rect, margin_mm: f64, tier, provenance }`, `LayerPreference { id, net: usize, layer: String, tier, provenance }`, `Alignment { id, nets: Vec<usize>, axis: AlignmentAxis, tolerance_mm: f64, tier, provenance }`, `EdgePlacement { id, nets: Vec<usize>, side: BoardEdge, max_distance_mm: f64, tier, provenance }`, `Anchored { id, net: usize, region: Option<Rect>, position: Option<Point>, tier, provenance }`, `LoopArea { id, loop_name: String, nets: Vec<usize>, max_area_mm2: f64, tier, provenance }`.
  - `ProvenanceRef` is an opaque index into the `ProvenanceMap` (U7), tracking the origin PCL constraint ID + desugaring rule.
  - `Rect = { x_min, y_min, x_max, y_max }`; `Point = { x, y }`; `AlignmentAxis` enum; `BoardEdge` enum.
  - `ResolvedConstraintModel { constraints: Vec<ResolvedConstraint>, net_class_map: HashMap<usize, NetClassMetadata> }` -- the fully resolved intermediate representation.
  - Net indices are resolved from component references via a `ComponentResolver` passed from Python (component name → net index map constructed from PCB data).
  - Zone names resolve to bounding rectangles passed from Python as dicts.
- **Patterns to follow:**
  - `pcl/constraints.py:106-661` -- PCL constraint field semantics; component reference strings map to net indices; zone names map to bounding regions
  - `stage0_data.py:41-60` -- `StackupInfo` and `LayerInfo` for layer naming convention
  - `types.rs:264-306` -- net-index-based addressing in `InternalVariable` and `InternalConstraint`
- **Test scenarios:**
  - Separation constraint: `a="Q1"`, `b="Q2"` → resolved to `net_a=3, net_b=7` via component-to-net resolver
  - Enclosing constraint: `outer="HV_ZONE"` → resolved to `zone_bounds=Rect{...}`; `inner=["Q1", "D1"]` → resolved to `nets=[3, 5]`
  - Missing component resolver entry for a reference: returns `Err(CompileError::UnresolvedComponent("Q1"))` (R12)
  - Missing zone entry: returns `Err(CompileError::UnresolvedZone("HV_ZONE"))` (R12)
  - Loop area constraint with 4 nets resolved correctly
  - All constraints carry `ProvenanceRef` pointing to valid provenance entries
  - Multiple constraints on the same net-pair (separation + adjacency) coexist in the model
- **Verification:**
  - `cargo test --lib ir_tier1` -- all unit tests pass
  - Integration: resolve a full 7-constraint PCL model with known component→net mapping, verify all `ResolvedConstraint` net indices match expected

---

### U5. Tier 0 → Tier 1 desugaring (PCL IR → Geometric IR)

- **Goal:** Implement the desugaring rules that transform PCL constraint types and lattice-inferred constraints into resolved geometric constraints with net indices and concrete parameters.
- **Requirements:** R5, R6, R7, R8, R12
- **Dependencies:** U2 (type lattice), U3 (Tier 0 IR), U4 (Tier 1 IR)
- **Files:**
  - Create: `packages/temper-constraint-compiler/src/desugar_tier0.rs`
  - Modify: `packages/temper-constraint-compiler/src/lib.rs` (register module)
- **Approach:**
  - Define `DesugarRuleTier0` as a function pointer or closure type: `fn(&PclConstraint, &ComponentResolver, &ZoneResolver, &mut ProvenanceMap) -> Result<Vec<ResolvedConstraint>, CompileError>`.
  - Define a static `RULES_TIER0: &[(&str, DesugarRuleTier0)]` table mapping PCL constraint variant names → desugaring functions.
  - For each PCL type, one rule:
    - `desugar_adjacent`: resolve component refs `a`/`b` → net indices via `ComponentResolver`. Emit `ResolvedConstraint::Adjacency` with `max_distance_mm`, `tier`, provenance. If `pin_a`/`pin_b` specified, store pin metadata in constraint.
    - `desugar_separated`: resolve `a`/`b` → net indices. Emit `ResolvedConstraint::Separation` with `min_distance_mm`.
    - `desugar_enclosing`: resolve `outer` → zone bounds via `ZoneResolver`, `inner` → net indices list. Emit `ResolvedConstraint::ZoneEnclosing`.
    - `desugar_aligned`: resolve `components` list → net indices. Emit `ResolvedConstraint::Alignment` with axis.
    - `desugar_on_side`: resolve `components` → net indices. Emit `ResolvedConstraint::EdgePlacement`.
    - `desugar_anchored`: resolve `component` → net index. Emit `ResolvedConstraint::Anchored` with region/position.
    - `desugar_loop_area`: resolve loop components → net indices. Emit `ResolvedConstraint::LoopArea`.
    - `desugar_inferred_separation`: `InferredSeparation` from lattice → resolve both net class names to the actual net indices sharing channels. Emit `ResolvedConstraint::Separation` with `clearance_floor_mm` as `min_distance_mm`, layer restriction as `ResolvedConstraint::LayerPreference`. One `InferredSeparation` may expand to multiple `ResolvedConstraint` instances (one per net-pair sharing a channel).
  - The rule table is `&'static` for each tier; new constraint types register their desugaring function at the appropriate tier (R7).
  - `ComponentResolver` and `ZoneResolver` are traits (or closures) injected from Python via PyO3 -- the compiler does not own the PCB data.
  - On component/zone resolution failure, return `CompileError` with structured message (R12).
- **Patterns to follow:**
  - `pcl/constraints.py:106-661` -- constraint field semantics and resolution logic
  - `pipeline.py:594-612` -- the `ModelBuilder` pattern for resolving per-PCB data (nets, channel widths, design rules)
  - `types.rs:264-306` -- net-index-based addressing
- **Test scenarios:**
  - Desugar AdjacentConstraint with component refs → single `ResolvedConstraint::Adjacency`
  - Desugar SeparatedConstraint with zone refs → single `ResolvedConstraint::Separation`
  - Desugar EnclosingConstraint with 3 inner components → `ResolvedConstraint::ZoneEnclosing` with 3 net indices
  - Desugar InferredSeparation for HV-LV pair across 2 channels → 2 `ResolvedConstraint::Separation` instances + 1 `ResolvedConstraint::LayerPreference`
  - Unresolved component ref: returns `CompileError` not panic
  - Unresolved zone ref: returns `CompileError` not panic
  - Empty constraint model (0 PCL constraints, 0 inferred) → produces empty `ResolvedConstraintModel`
  - Provenance: each emitted `ResolvedConstraint` has a valid `ProvenanceRef` linking back to the source `PclConstraint.id`
- **Verification:**
  - `cargo test --lib desugar_tier0` -- all unit tests pass
  - Property test (R8): for all valid PCL constraint inputs, desugaring is deterministic (same input → same output), total function (no panics on valid inputs), and produces at least 1 `ResolvedConstraint` per PCL constraint
  - Rule registration test: verify `RULES_TIER0` has exactly one entry per PCL constraint variant + one for `InferredSeparation` (8 entries)

---

### U6. Tier 1 → Tier 2 desugaring (Geometric IR → Constraint ISA)

- **Goal:** Implement the desugaring rules that transform resolved geometric constraints into `InternalConstraint` instances (Capacity, DiffPair, LayerRestriction) consumable by the SAT encoder. This is the final lowering tier.
- **Requirements:** R5, R6, R7, R8, R10
- **Dependencies:** U1 (crate + types access), U4 (Tier 1 IR), U5 (Tier 1 as input)
- **Files:**
  - Create: `packages/temper-constraint-compiler/src/desugar_tier1.rs`
  - Modify: `packages/temper-constraint-compiler/src/lib.rs` (register module)
- **Approach:**
  - Define `DesugarRuleTier1` type: `fn(&ResolvedConstraint, &ChannelTopology, &mut ProvenanceMap) -> Result<Vec<InternalConstraint>, CompileError>`.
  - Define static `RULES_TIER1` table mapping `ResolvedConstraint` variant names → desugaring functions.
  - Each geometric constraint type expands:
    - `Separation(net_a, net_b, min_distance_mm)`: For each channel shared by both nets in the skeleton, if the channel width < `min_distance_mm`, emit `LayerRestriction { var_name: "uses_N{net_a}_{ch}", allowed: false }` for one net (prevents co-channel placement). If channel width can accommodate spacing via capacity budget, add a `CapacityConstraint` refinement: increase the effective `capacity` term by a `creepage_width_budget` = `min_distance_mm - trace_width`. This is conservative -- if the channel can't fit both nets with the required clearance, the `LayerRestriction` makes it infeasible for them to coexist.
    - `Adjacency(net_a, net_b, max_distance_mm)`: For channels reachable by both nets, emit constraints that force co-routing (if both nets have the same `required_layer` or no layer restriction). This maps to paired `LayerRestriction` constraints ensuring both nets are assigned to the same channel. For channels where co-routing is geometrically possible, emit an `AssignmentHint` (stored in Tier 1 but not lowered to ISA -- adjacency is advisory, not a hard SAT constraint, unless tier=HARD in which case it becomes a DiffPair-style equality).
    - `ZoneEnclosing { nets, zone_bounds }`: For each net in `nets`, determine which channels intersect the zone. Emit `LayerRestriction { allowed: true }` for channels inside the zone and `LayerRestriction { allowed: false }` for channels outside (if zone-enclosed is HARD tier). If SOFT/STRONG, emit as removable soft constraints.
    - `LayerPreference { net, layer }`: Emit `LayerRestriction { var_name: "uses_N{net}_{ch}", allowed }` for each channel on/off `layer`. For multi-layer channels, prefer the requested layer.
    - `Alignment`, `EdgePlacement`, `Anchored`, `LoopArea`: For initial implementation, these are advisory-only at Tier 2 (store provenance but emit zero `InternalConstraint` -- they inform routing heuristics, not SAT hard constraints). Future desugaring rules can add Capacity/LayerRestriction emissions without changing the desugaring framework or SAT types (R7).
  - The `ChannelTopology` struct represents the routing skeleton: `{ channels: Vec<Channel { id: String, width_mm: f64, nets: Vec<usize>, layer: String }> }`.
  - Each desugaring function accesses `ChannelTopology` to determine which channels are relevant, compute width budgets, and check layer compatibility.
  - When a geometric constraint cannot map to any reachable channel (e.g., zone has no channels), return `CompileError::UnreachableConstraint` (R12).
  - Output is a flat `Vec<InternalConstraint>` ready to be merged into the existing `InternalConstraintModel`.
  - The constraints map to variables already in the model: `uses_N{net_idx}_{channel_id}` for `InternalVariable::NetChannel`.
- **Patterns to follow:**
  - `types.rs:290-306` -- `InternalConstraint::Capacity { channel_id, capacity, slack_factor, terms }`, `DiffPair { channel_id, p_var_name, n_var_name }`, `LayerRestriction { var_name, allowed }`
  - `types_py_bridge.rs:67-83` -- how `LayerRestriction` constructs `var_name` from `net_idx` + `channel_id` (`"uses_N{}_{}"`)
  - `encoding.rs:111-151` -- how each `InternalConstraint` maps to CNF clauses (the target ISA)
- **Test scenarios:**
  - Separation 6mm on a 3mm channel → emits `LayerRestriction(allowed=false)` for one net on that channel
  - Separation 0.25mm on a 2mm channel with 0.2mm traces → emits `CapacityConstraint` refinement, no `LayerRestriction`
  - ZoneEnclosing (HARD): 3 nets inside a zone with 2 channels → emits `LayerRestriction(allowed=true)` for channels inside zone, `LayerRestriction(allowed=false)` for channels outside
  - LayerPreference: `net=5, layer="B.Cu"` with 2 channels on B.Cu, 1 on F.Cu → emits 2 `LayerRestriction(allowed=true)`, 1 `LayerRestriction(allowed=false)`
  - Adjacency HARD tier: `net_a=1, net_b=2` sharing channel CH1 → emits `DiffPairConstraint` for CH1
  - Adjacency SOFT tier: emits zero `InternalConstraint` (advisory, provenance logged)
  - Alignment, Anchored, LoopArea: emit zero `InternalConstraint` for initial impl
  - Empty channel topology: `ResolvedConstraint::Separation` returns `Err(CompileError::UnreachableConstraint)` (R12)
  - Multiple channels: separation constraint emits one `InternalConstraint` per shared channel
- **Verification:**
  - `cargo test --lib desugar_tier1` -- all unit tests pass
  - Property test (R8): for exhaustive small-n topologies (n≤4 nets, ≤3 channels), verify that all SAT assignments satisfying the Tier 2 constraints also satisfy the Tier 1 geometric constraints (conservative approximation holds). Verify no false UNSAT is introduced (the augmented model is UNSAT only when the original model + geometric constraints are infeasible).
  - Rule registration: `RULES_TIER1` has one entry per `ResolvedConstraint` variant (8 entries)

---

### U7. Provenance metadata tracking

- **Goal:** Implement provenance tracking through the desugaring pipeline so that every `InternalConstraint` at Tier 2 carries a back-reference chain to its origin PCL constraint(s) and desugaring rule(s), enabling UNSAT core reverse-mapping.
- **Requirements:** R9
- **Dependencies:** U5 (Tier 0→1), U6 (Tier 1→2)
- **Files:**
  - Create: `packages/temper-constraint-compiler/src/provenance.rs`
  - Modify: `packages/temper-constraint-compiler/src/lib.rs` (register module)
- **Approach:**
  - Define `ProvenanceMap` structure:
    - `entries: Vec<ProvenanceEntry>` indexed by `ProvenanceRef(usize)`.
    - `clause_to_provenance: HashMap<usize, Vec<ProvenanceRef>>` mapping clause indices to origin entries.
    - `ProvenanceEntry { pcl_constraint_id: String, tier0_type: String, desugar_rule_t0: String, desugar_rule_t1: String, rationale: String, tier: ConstraintTier }`.
  - Each desugaring function in U5 and U6 calls `prov.push(pcl_id, rule_name, tier, rationale)` when emitting a constraint, and `prov.link_clause(clause_idx, prov_ref)` when the constraint becomes a SAT clause.
  - Define `reverse_map_unsat_core(core: &[usize], prov: &ProvenanceMap) -> Vec<ProvenanceDiagnostic>`:
    - For each clause index in the UNSAT core, look up all `ProvenanceRef`s.
    - Group by `pcl_constraint_id`, deduplicate.
    - Produce `ProvenanceDiagnostic { pcl_constraint_id, tier, rationale, conflict_with: Vec<String> }` if multiple PCL constraints contributed.
  - Define `detect_conflicts(model: &ResolvedConstraintModel) -> Vec<ConflictReport>` for pre-solve conflict detection:
    - For each `ResolvedConstraint::Separation(na, nb, min_d)` and `ResolvedConstraint::Adjacency(na', nb', max_d)` where `na==na' && nb==nb'`, if `min_d > max_d`, report a conflict.
    - Detect zone-enclosure vs. separation contradictions.
    - Detect layer preference conflicts (net required on different layers).
  - `ProvenanceDiagnostic` has a human-readable `Display` impl producing messages like: _"Constraint conflict: HV isolation (PCL constraint 'iso_main_hv_lv') requires >=6mm separation between Q1_HV and Q2_HV, but thermal coupling (PCL constraint 'therm_q1_q2') requires <=3mm adjacency between Q1 and Q2"_ (AE2).
- **Patterns to follow:**
  - `solver.rs:208-229` -- UNSAT core extraction from `core()` returns clause indices, then `core_clause_indices` maps selector vars back
  - `audit.rs:44-128` -- structured violations returned as data, not panics
  - `lib.rs:94-99` -- `unsat_core` serialized as `PyList` of clause indices
- **Test scenarios:**
  - Single PCL constraint → Tier 2: 1 `ProvenanceEntry` linked to 1 clause index
  - Inferred separation expands to 3 channels: 3 `ProvenanceEntry`s, each linked to their channel's clause
  - UNSAT core reverse-map: 3 clause indices in core → 2 distinct PCL constraint IDs returned
  - Conflict detection: `Separation(min=6mm)` + `Adjacency(max=3mm)` on same net-pair → pre-solve `ConflictReport`
  - Conflict detection: `Separation` + `Adjacency` with `min_d <= max_d` → no conflict
  - Conflict detection: `LayerPreference("B.Cu")` + `LayerPreference("F.Cu")` on same net → conflict
  - Empty UNSAT core → empty diagnostic list
  - Provenance serialization: `ProvenanceDiagnostic` → Python dict preserves all fields
- **Verification:**
  - `cargo test --lib provenance` -- all unit tests pass
  - Integration: compile a PCL model with known conflict, verify pre-solve detection catches it; compile a satisfiable model, run `solve_with_cadical_cores`, verify reverse-map produces correct origin IDs

---

### U8. PyO3 bindings and pipeline integration

- **Goal:** Expose the compiler as PyO3 bindings matching the `solve_topology_rust` pattern, with a stateful `PyCompiler` object supporting incremental recompilation (R11), and integrate into the existing pipeline between Stage 3.1-3.6 constraint generation and the SAT solve.
- **Requirements:** R2, R10, R11, R12
- **Dependencies:** U1-U7 (all compiler internals), U5 (Tier 0→1 desugaring), U6 (Tier 1→2 desugaring)
- **Files:**
  - Create: `packages/temper-constraint-compiler/src/pyo3_bridge.rs`
  - Modify: `packages/temper-constraint-compiler/src/lib.rs` (register PyO3 functions/classes)
  - Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (integration point after constraint model building, before SAT solve)
- **Approach:**
  - **Stateful `PyCompiler` class** (`#[pyclass]`):
    - Fields: `lattice: TypeLattice`, `resolver: Option<ComponentResolver>`, `zone_resolver: Option<ZoneResolver>`, `topology: Option<ChannelTopology>`, `last_model: Option<ResolvedConstraintModel>`, `prov: ProvenanceMap`.
    - Constructor: `__init__(self, net_class_dicts: dict, component_map: dict, zone_map: dict, skeleton_edges, channel_widths)` -- initializes the lattice from `NetClassRules`-shaped dicts, the component and zone resolvers, and the channel topology.
    - `compile(self, pcl_dicts: list[dict], net_names: list[str]) -> dict`: runs the full pipeline Tier 0 → Tier 1 → Tier 2, returns `{ "constraints": [...dict...], "provenance": [...dict...], "warnings": [...str...], "conflicts": [...dict...] }`. The returned constraint dicts match existing `ConstraintModel` shape for direct merge into the `py_cons` list passed to `solve_topology_rust`.
    - `recompile_delta(self, changed_net_indices: list[int]) -> dict`: re-evaluates only lattice inferences and desugaring rules involving the changed net indices. Unaffected net-pair constraints are retained from the previous compilation (R11).
    - `reverse_map_unsat_core(self, unsat_core_indices: list[int]) -> list[dict]`: returns provenance diagnostics for the UNSAT core.
  - **Single-shot function** `compile_pcl_constraints(pcl_dicts, net_class_dicts, component_map, zone_map, skeletons, channel_widths, existing_vars, existing_cons, net_names) -> PyResult<PyObject>`:
    - Wraps the stateful compiler for one-shot use.
    - Returns a `PyDict` with `"augmented_variables"` and `"augmented_constraints"` keys -- the merged model ready to pass to `solve_topology_rust`.
    - The augmented model = existing `InternalConstraintModel` + lowered PCL constraints (R10).
  - **Pipeline integration** in `pipeline.py:_run_stage3()`:
    - After `constraint_model = model_builder.build()` (line 612), insert: `constraint_model = self._augment_with_pcl_constraints(constraint_model, net_names, pcb)`.
    - `_augment_with_pcl_constraints` loads PCL data from `pcb.constraints` (if available), invokes the compiler, and appends the lowered constraints to `constraint_model.constraints`.
    - The augmented `py_vars` and `py_cons` are then passed to `solve_topology_rust` as before.
    - On UNSAT, call `compiler.reverse_map_unsat_core(rust_result["unsat_core"])` and surface diagnostics.
    - Feature-gate: if `TEMPER_PCL_CONSTRAINTS=1` env var is set.
  - **Error surfacing**: Python exceptions raised via `PyErr` subtypes: `PyConstraintCompileError` (unresolved component/zone), `PyConstraintConflictError` (pre-solve conflict detected).
- **Patterns to follow:**
  - `lib.rs:26-102` -- `solve_topology_rust` `#[pyfunction]` pattern with `PyList`, `PyDict`, `PyResult<PyObject>`
  - `lib.rs:194-211` -- `#[pymodule]` with `add_class`, `add_function`
  - `types.rs:16-257` -- `#[pyclass(subclass, get_all)]` pattern for Python-visible types
  - `pipeline.py:594-632` -- Stage 3 integration point, `from temper_rust_router import solve_topology_rust`
  - `_safety_keywords.py:25-31` -- `resolve_safety_category()` pattern for extracting safety category data from `NetClassRules`
- **Test scenarios:**
  - Single-shot: `compile_pcl_constraints([adj_dict, sep_dict], net_classes, ..., [], [], net_names)` returns dict with `augmented_constraints` list
  - Stateful: `compiler = PyCompiler(...); result = compiler.compile(pcl_dicts, net_names)` returns constraints + provenance + warnings
  - Incremental: `compiler.compile(model1); compiler.recompile_delta([2, 5])` returns only constraints affected by nets 2 and 5, retaining others
  - UNSAT core reverse-map: `compiler.reverse_map_unsat_core([17, 23])` returns diagnostics for clause indices 17 and 23
  - Empty PCL: `compiler.compile([], net_names)` returns empty constraints, zero warnings, zero conflicts
  - Missing safety_category: net with `safety_category=None` produces a warning in the result dict, not an error
  - Unresolved component: `pcl_dict` with ref "UNKNOWN" raises `PyConstraintCompileError`
  - Pre-solve conflict: separable + adjacent constraints on same net-pair with incompatible distances returns `conflicts` list
  - Pipeline integration: full `RouterV6Pipeline._run_stage3()` with `TEMPER_PCL_CONSTRAINTS=1` produces augmented constraint model with zero regressions on existing tests
- **Verification:**
  - `cargo test --lib pyo3_bridge` -- Rust-side unit tests pass
  - `python -c "from temper_constraint_compiler import compile_pcl_constraints, PyCompiler; ..."` -- import and basic invocation succeed
  - `python -m pytest packages/temper-placer/tests/router_v6/` -- existing router V6 tests pass unchanged (no regression)
  - Pipeline integration test with real PCL constraints from `pcb/temper.kicad_pcb` produces non-empty lowered constraints

---

### U9. Property-test suite for desugaring correctness

- **Goal:** Implement Rust `proptest` suites for Tier 0→1 and Tier 1→2 desugaring, verifying conservative approximation and no-false-UNSAT properties per R8.
- **Requirements:** R8
- **Dependencies:** U5 (Tier 0→1 desugaring), U6 (Tier 1→2 desugaring), U7 (provenance)
- **Files:**
  - Create: `packages/temper-constraint-compiler/tests/proptest_tier0_to_tier1.rs`
  - Create: `packages/temper-constraint-compiler/tests/proptest_tier1_to_tier2.rs`
  - Modify: `packages/temper-constraint-compiler/Cargo.toml` (add `proptest` to dev-dependencies)
- **Approach:**
  - **Tier 0→1 property tests**: Generate valid `PclConstraint` instances via `proptest::prelude::any` with strategies for each variant. Assert: desugaring is deterministic (same input → same output), produces at least 1 `ResolvedConstraint`, all emitted constraints have valid `ProvenanceRef`s, component and zone refs resolve to valid indices, no panics on valid inputs.
  - **Tier 1→2 property tests**: Generate small-n topologies (n≤4 nets, ≤3 channels) with random channel widths and net assignments. Generate `ResolvedConstraint` instances. Assert: (a) **conservative approximation** -- all SAT assignments satisfying Tier 2 constraints also satisfy Tier 1 geometric semantics (verify with an exhaustive SAT-enumeration of the small CNF and constraint checker); (b) **no false UNSAT** -- if the Tier 1 constraints are geometrically satisfiable, then the Tier 2 CNF is SAT; (c) **deterministic** -- same input produces same `InternalConstraint` vector.
  - Use the mini-DPLL solver from `encoding.rs:189-261` (or an extracted `dpll_sat` utility function) to exhaustively check SAT assignments for small-n topologies.
  - **Channel topology generators**: `proptest` strategies for `ChannelTopology` with:
    - 1-4 channels, each with width ∈ [0.5, 10.0]mm
    - 1-4 nets assigned per channel
    - Random layers from {F.Cu, In1.Cu, In2.Cu, B.Cu}
  - **Constraint generators**: strategies for each `ResolvedConstraint` variant with net indices within topology bounds.
- **Patterns to follow:**
  - `encoding.rs:264-305` -- exhaustive AtMostK verification pattern with DPLL for n≤8
  - `audit.rs:276-322` -- brute-force constraint checker pattern for all assignments of small-n model
- **Test scenarios:**
  - Tier 0→1: 1000 randomly generated `PclConstraintModel` instances, all pass deterministic + provenance checks
  - Tier 1→2: exhaustive 4-net 3-channel topology, all 16 assignment combinations verified for separation constraints
  - Tier 1→2: 100 random small topologies, conservative approximation verified via brute-force SAT enumeration
  - Tier 1→2: adversarially chosen topology where separation exceeds channel width → UNSAT correctly detected (not false SAT)
  - Tier 1→2: topology where constraints are satisfiable → SAT result (no false UNSAT)
- **Verification:**
  - `cargo test --test proptest_tier0_to_tier1` -- all property tests pass
  - `cargo test --test proptest_tier1_to_tier2` -- all property tests pass

---

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `InternalConstraintModel` is `pub` in `types.rs` but the `model_from_python` path is the only bridge today -- the compiler needs direct construction of `InternalConstraint` instances from Rust | Low | Medium | `InternalConstraint` and `InternalConstraintModel` are `pub` enum/struct in `types.rs:289-312`; the compiler directly constructs them without going through PyO3 |
| `NetClassRules` data is Python-only (Pydantic); the compiler needs structured net-class metadata | High | Medium | Resolved by U8: net class data flows into the compiler as `PyDict` via PyO3 bridge, converted to Rust `NetClassMetadata` struct in `type_lattice.rs`. No Rust-side `NetClassRules` dependency |
| `ChannelSkeleton` edges from Stage 2 are NetworkX Python objects; topology data must cross into Rust | High | Low | Resolved by U8: skeleton edges + channel widths passed as `Vec<dict>` (list of {net_a, net_b, channel_id} dicts) matching the existing `solve_topology_rust` pattern |
| CaDiCaL UNSAT core returns clause indices relative to the instrumented CNF (with selectors), not the original CNF | Medium | Low | `solve_with_cadical_cores()` at `solver.rs:216-228` already maps selector vars back to original clause indices. Provenance tracking in U7 operates on these corrected indices |
| Lattice may produce redundant constraints (same LayerRestriction emitted from multiple PCL constraints) | Medium | Low | Desugaring functions in U6 deduplicate by channel+var_name key before emitting. Provenance entries accumulate all origin references for deduplicated constraints |
| Adding the compiler to the Rust build may increase compile times | Low | Low | Standalone crate with path dependency -- only recompiled when its own sources or `temper-rust-router`'s public API changes |

**Dependencies on external changes:**
- None. The compiler is additive -- it augments the constraint model without modifying `temper-rust-router`'s `types.rs`, `encoding.rs`, `solver.rs`, or `audit.rs`.
- `InternalConstraintModel`, `InternalConstraint`, and `InternalVariable` are already `pub` in `types.rs:264-312` with `pub` visibility on all fields.

---

## Deferred to Follow-Up Work

1. **PCL constraint authoring UI (ce-polish-beta)**: A browser-based interface for designers to author and validate PCL constraints with live feedback from the lattice inference. Not in scope for the initial compiler implementation.

2. **Lazy grounding (ideation #2)**: Hierarchical net bundling with type-gated lazy grounding for explosion containment beyond `max_sat_nets`. Deferred until the lowering compiler proves that semantic constraints don't increase model size (success criteria measurement).

3. **Bidirectional PCL constraint IR (ideation #4)**: SAT UNSAT cores compiling upward to new PCL constraints triggering re-placement. Requires the compiler to be stable and the UNSAT provenance to be operational first.

4. **Constraint combinator library (ideation #5)**: ~6 primitive constraint encodings with inductive proofs, all designer constraints as compositions. Deferred until the full PCL vocabulary is lowered and the rule table pattern (R7) is validated with real constraints.

5. **Railway-style Bounded Model Checking (ideation #6)**: An Encoder Specification Language with BMC to prove equivalence for bounded topologies. The proptest suite in U9 provides lightweight correctness; formal BMC is a separate engineering investment.

6. **ESLint/CI rule for PCL rule table completeness**: A static check ensuring every `PclConstraint` variant has a corresponding entry in `RULES_TIER0` and `RULES_TIER1`. This is a quality-of-life improvement for developers adding new constraint types.

7. **Alignment/Anchored/EdgePlacement/LoopArea Tier 2 encodings**: The initial implementation treats these 4 constraint types as advisory (provenance-logged but emitting zero `InternalConstraint`). Full Tier 2 desugaring rules require mapping these geometric semantics to Capacity/LayerRestriction clauses with per-channel spatial awareness -- deferred until a concrete design requires them.

8. **`iso` as a source category**: The current lattice treats `iso` as synthetic (join-only). If future designs require explicit `iso` net class assignments, the lattice needs a direct `iso` node with self-join semantics (iso∨iso = iso with creepage=max). Deferred until needed.
