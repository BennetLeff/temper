---
date: 2026-06-28
topic: constraint-lowering-compiler
---

# Constraint Lattice & Multi-Tier Lowering Compiler

## Summary
Build a standalone Rust crate that compiles designer-level PCL constraints (using NetClassRules safety categories as types) through successive desugaring passes into the existing low-level SAT constraint types (Capacity, DiffPair, Layer). A Hindley-Milner-style type lattice infers minimum clearances, layer restrictions, and adjacency requirements from pairwise net-type interactions before any SAT clause is generated.

---

## Problem Frame
The routing SAT model (`packages/temper-rust-router/src/types.rs`) knows only 3 low-level constraint types: Capacity, DiffPair, Layer. PCL (`packages/temper-placer/src/temper_placer/pcl/constraints.py`) defines 7 constraint types (Adjacent, Separated, Enclosing, Aligned, OnSide, Anchored, LoopArea) with HARD/STRONG/SOFT tiers. These two systems are completely separate — PCL constraints drive JAX placement but have zero representation in the SAT routing stage. `NetClassRules.safety_category` (Literal["HV","LV","AC","iso"]) exists on the 9 net classes in `TEMPER_NET_CLASSES` (`design_rules.py:324-431`) but never reaches the SAT encoder. The 228K-variable blowup case proved that selective net construction is essential, but the current approach gives no semantic type-awareness to the selection — it only uses pin count (`max_sat_nets`). Adding a new PCL constraint type today requires modifying the SAT variable schema, the CNF encoder, and every downstream consumer. This compiler eliminates that coupling by defining a lowering pipeline where new constraint types only need desugaring rules at their natural tier.

---

## Actors
- A1. **PCB Designer**: Defines semantic constraints (isolation, thermal, impedance) in PCL, expressed in terms of component references and `NetClassRules` safety categories
- A2. **SAT Solver (splr)**: Consumes CNF clauses built from the 3 existing constraint types (Capacity, DiffPair, Layer) via the existing Sinz-2005 sequential-counter encoding in `encoding.rs`; never sees designer-level concepts
- A3. **Pipeline Orchestrator**: Invokes compilation between the existing `ConstraintGeneration` stage (Stage 3.1 in `constraint_model.py:365`) and the `solve_topology_rust` entry point (`lib.rs:26`), augmenting the constraint model with lowered PCL constraints before the SAT solve

---

## Key Flows
- **F1. Constraint compilation from PCL to SAT**
  - Trigger: Pipeline Stage 2 completes channel analysis (skeletons + channel widths available), Stage 3 begins
  - Actors: A3 (orchestrator), A1 (indirectly via PCL config), A2 (output consumer)
  - Steps:
    1. Orchestrator loads the active PCL constraint set and resolves each constraint's component references to their net classes via `TEMPER_NET_ASSIGNMENTS` → `NetClassRules.safety_category`
    2. Compiler constructs the safety-type lattice over HV/LV/AC/iso with meet/join operators that encode the pairwise clearance values from `NetClassRules.creepage_mm` and required-layers from `NetClassRules.required_layer`
    3. Compiler walks the net topology graph (the `ChannelSkeleton` edges from Stage 2) and, for every net-pair that shares a potential routing channel, computes the inferred constraint set from their safety types using lattice meet/join
    4. The inferred constraint set is lowered through successive desugaring tiers (PCL → geometric IR → constraint ISA) into `InternalConstraint` instances
    5. Lowered constraints are merged into the existing `ConstraintModel` (augmenting, not replacing, the capacity/diff-pair/layer constraints already built by `ModelBuilder`)
    6. The augmented model is passed to `solve_topology_rust` unchanged — no modification to the solver or CNF encoder
  - Outcome: The SAT model contains clauses derived from both structural routing needs (channel capacity, layer restrictions) AND designer-level PCL constraints (separation, adjacency, enclosing)
  - Covered by: R1, R3, R4, R5, R6, R10

- **F2. UNSAT provenance reverse-mapping**
  - Trigger: `solve_topology_rust` returns status `"unsat"`
  - Actors: A3 (orchestrator), A1 (consumes diagnostics)
  - Steps:
    1. The UNSAT core (clause indices) from `TopologyResult.unsat_core` is received
    2. Each conflicting clause is reverse-mapped through the desugaring tier provenance records to its origin PCL constraint(s)
    3. If multiple PCL constraints contributed to the conflict, the compiler reports all of them with their respective tier and rationale
    4. The provenance report is emitted as structured diagnostics the pipeline can surface to the designer
  - Outcome: Designer sees "Constraint conflict: HV isolation (PCL 'iso_main_hv_lv') requires ≥6mm separation, but thermal coupling (PCL 'therm_q1_q2') requires ≤3mm separation" instead of raw clause indices
  - Covered by: R9

---

## Requirements

### Package structure
- **R1.** The compiler SHALL be a standalone Rust crate `temper-constraint-compiler` in `packages/temper-constraint-compiler/` with its own `Cargo.toml`, depending on `temper-rust-router` (via path dependency) for access to `InternalConstraint`, `InternalConstraintModel`, and related types
- **R2.** The compiler SHALL expose PyO3 bindings so the Python pipeline can invoke compilation from Stage 3.1–3.6 (between `ConstraintGeneration` and the SAT solve). The binding receives PCL constraint data as Python dicts and returns an augmented constraint model in the same dict-list format that `solve_topology_rust` already consumes

### Type lattice
- **R3.** The compiler SHALL define a safety-type lattice over `NetClass` values — the four concrete types from `NetClassRules.safety_category`: `HV`, `LV`, `AC`, `iso` — with meet/join operations that determine the minimum required clearance, layer restrictions, and adjacency requirements for any pair of net types. The lattice MUST encode the real clearance values: HV-HV = 3mm (safe within same domain), HV-LV = 6mm (IEC 60335-1 reinforced), HV-AC = 6mm, LV-LV = 0.25mm (standard signal), iso-isolates both sides. The join of two types is the most restrictive interaction category; the meet is the most permissive
- **R4.** The lattice SHALL propagate type judgments through the net topology graph: for each pair of nets that share at least one channel edge in the routing skeleton, the lattice computes the inferred constraint set (`InferredConstraint`) containing the clearance floor, layer restriction, and whether separation is required. The inference is mechanical — no heuristic choices, no tuning knobs — given the net types and a clearance table, the output is deterministic

### Desugaring pipeline
- **R5.** The compiler SHALL implement a multi-tier desugaring pipeline where each tier transforms a richer constraint IR into a simpler one. The final tier MUST produce only `InternalConstraint` instances of the 3 existing variants (Capacity, DiffPair, Layer) — no new SAT variable types are created
- **R6.** The pipeline SHALL support at minimum 3 desugaring tiers:
  - **Tier 0 (PCL Constraint IR)**: The raw PCL constraint types (Adjacent, Separated, Enclosing, Aligned, OnSide, Anchored, LoopArea) PLUS the lattice-inferred constraints for each net-pair. This tier understands component references and zone names
  - **Tier 1 (Net-Class-Aware Geometric IR)**: Constraints resolved to net indices and geometric parameters (min/max distance in mm, layer preference, region bounds). Component references and zone names are fully resolved. Separation values are concrete floats, not type-category lookups. This tier is the desugaring target for Tier 0 rules
  - **Tier 2 (Constraint ISA)**: Pure `InternalConstraint` instances (Capacity, DiffPair, Layer), parameterized by channel IDs, variable names, and net indices. This is the "machine code" the existing SAT encoder in `encoding.rs` consumes. Each Tier 1 constraint may expand into one or more Tier 2 constraints across multiple channels
- **R7.** Each desugaring rule SHALL be registered in a rule table (per-tier). Adding a new constraint type (e.g., a future `ImpedanceMatched` constraint) SHALL require only adding its desugaring rules at the appropriate tier(s) — no changes to the SAT variable schema (`InternalVariable`), the constraint ISA (`InternalConstraint`), or the CNF encoder (`encoding.rs`)

### Correctness
- **R8.** Each desugaring tier SHALL carry its own property-test suite (Rust `proptest`) proving that the tier's output is semantically equivalent to its input for all small-n topologies (up to exhaustion limits, e.g., all 4-net topologies on all 3-channel skeletons). Each tier's property test encodes "the lowered constraints admit exactly the same routing solutions as the original constraints, modulo the geometric abstractions gained/lost at each tier"
- **R9.** The compiler SHALL preserve provenance metadata through the desugaring pipeline. Every `InternalConstraint` emitted at Tier 2 carries a back-reference chain (PCL constraint ID → desugaring rule applied) so that when the SAT solver returns UNSAT, the compiler can reverse-map the conflicting clause IDs back to the originating PCL constraints and their rationales

### Integration
- **R10.** The compiler SHALL integrate with the existing `solve_topology_rust` entry point without modification to that function's signature. After compilation, the augmented `InternalConstraintModel` is passed to the existing `encoding::encode_to_cnf` + `solver::solve_with_splr` pipeline unchanged. The compiler emits to the same `InternalConstraint` types the encoder already handles
- **R11.** The compiler SHALL support incremental recompilation: when only a subset of nets change placement (identified by `net_idx`), only lattice inferences and desugaring rules involving affected net-pairs SHALL be re-evaluated. Unaffected net-pair constraints are retained from the previous compilation pass. The incremental API is exposed via PyO3 as a stateful compiler object that accepts delta net indices

---

## Acceptance Examples
- **AE1. Covers R3–R6.** Given a board with 2 HV nets (Q1, D1) and 3 LV nets (MCU, SENSOR, DEBUG) sharing channels in the routing skeleton:
  - The lattice infers: (a) HV-HV pairs require ≥3mm clearance (lattice join of HV∨HV = HV with 3mm floor), (b) HV-LV pairs require ≥6mm clearance (lattice join of HV∨LV = `isolated` with 6mm floor), (c) LV-LV pairs require ≥0.25mm clearance (join of LV∨LV = LV with 0.25mm floor)
  - Tier 1 desugaring produces geometric separation constraints (min_distance_mm = 6.0) for each HV-LV pair sharing a channel
  - Tier 2 desugaring expands each geometric separation into LayerConstraint instances (forbidding shared channels that cannot accommodate 6mm) and CapacityConstraint refinements (reserving width budget for creepage)
  - The resulting model augments — but does not replace — the existing capacity limits from `ModelBuilder._create_capacity_constraints`

- **AE2. Covers R9.** Given a board where HV clearance (6mm) conflicts with a thermal adjacency requirement (3mm max distance in `AdjacentConstraint`):
  - Tier 0 identifies the conflict: `SeparatedConstraint("iso_main_hv_lv", min_distance_mm=6.0)` from lattice inference contradicts `AdjacentConstraint("therm_q1_q2", max_distance_mm=3.0)` for the same net-pair
  - The conflict is detected at Tier 0 (pre-SAT) if it is structurally impossible (both constraints involve the same pair and the distance bounds overlap). If channel geometry allows a partial routing that drives UNSAT, the conflict surfaces post-solve via provenance
  - The provenance system reports: "Constraint conflict: HV isolation (PCL constraint 'iso_main_hv_lv') requires ≥6mm separation between Q1_HV and Q2_HV, but thermal coupling (PCL constraint 'therm_q1_q2') requires ≤3mm adjacency between Q1 and Q2"

---

## Success Criteria
- A PCL constraint type not previously supported by the SAT solver (e.g., `Enclosing` with a zone) produces correct routing assignments — nets inside/outside the zone are placed on appropriate channels — when lowered through the compiler
- Adding a new PCL constraint type to the compiler requires only a new desugaring rule entry in the rule table plus a property test for the relevant tier — no changes to `InternalConstraint`, `InternalVariable`, `encoding.rs`, or the `splr` integration
- The 228K-variable blowup case (from past learnings in `docs/ideation/2026-06-28-sat-constraint-type-system-ideation.md`) does NOT materially increase in model size when semantic constraints are added through the compiler. The compiler lowers to the same target ISA, and the existing selective construction (`max_sat_nets`) gates which nets receive SAT variables — the compiler only adds clauses for nets that are already in the model

---

## Scope Boundaries
- The compiler lowers TO the existing constraint types (Capacity, DiffPair, Layer) — it does NOT create new SAT variable types or new `InternalConstraint` variants
- The compiler does NOT modify the `splr` solver, the CNF encoding logic in `encoding.rs`, or the Sinz sequential counter
- The compiler does NOT handle runtime constraint modification during CDCL search (lazy grounding is a separate idea #2 from the ideation doc)
- Post-solve audit of constraint satisfaction remains the responsibility of the existing `audit.rs` / DRC fence module
- The compiler does NOT replace the Python `ModelBuilder` class (`constraint_model.py:153`); it compiles PCL constraints INTO additional constraint model entries that `ModelBuilder.build()` would not otherwise emit. The existing `ConstraintModel` is augmented, not replaced

---

## Key Decisions
- **Standalone crate**: Chosen because the lowering pipeline has its own dependency surface (type lattice, desugaring rules, provenance tracking, property-test frameworks) that should not be coupled to the solver crate's release cycle. A path dependency on `temper-rust-router` keeps the target ISA in sync without co-locating the compiler's internals
- **PyO3 bindings**: Chosen because the pipeline orchestrator and PCL constraint sources are in Python; the compiler must be callable from Stage 3 without a network or subprocess boundary. The binding shape mirrors the existing `solve_topology_rust` pattern (dict-lists in, dict out)
- **Target is existing constraint types**: Chosen because it minimizes blast radius — no SAT encoding changes are needed, the Sinz-2005 correctness proof (`encoding.rs:167-181`) is unaffected, and the existing audit module (`audit.rs`) validates the augmented model without modification
- **3 desugaring tiers (minimum)**: Chosen to decouple three concerns that would otherwise entangle: (a) PCL syntax and component resolution, (b) geometric constraint semantics, (c) SAT variable mapping. Fewer tiers would force one module to understand both PCL and SAT details; more tiers add abstraction overhead without demonstrated benefit

---

## Dependencies / Assumptions
- `temper-rust-router` exposes `InternalConstraintModel`, `InternalConstraint`, and `InternalVariable` as public API. **Current state**: these are `pub` within the `types` module but the module itself is not fully publicly re-exported (`lib.rs:9` declares `pub mod types;`, but the trait `IntoInternal` at `types.rs:385` is the only public conversion path). The compiler will need either `pub` re-exports of these internal types or a companion serialization path added to `temper-rust-router`
- `NetClassRules` data is accessible from the Rust side. **Current state**: Python-only (Pydantic `BaseModel`). The compiler will receive net-class metadata via PyO3 as dicts/serdes, or through a conversion layer that maps Python `NetClassRules` fields to a Rust representation
- The Sinz sequential counter encoding (`encoding.rs:20-75`) handles the cardinality constraints the compiler emits. **Confirmed**: the existing encoder produces AtMostK CNF for Capacity constraints. The compiler's Tier 2 output will produce additional Capacity constraints for separation-derived width budgets, which use the same encoding path
- PCL constraints are available as Python objects at pipeline Stage 3 invocation time. **Confirmed**: `ConstraintGenerationStage.run()` (`constraint_model.py:372`) has access to `BoardState` which carries the full constraint set
- The 9 net classes in `TEMPER_NET_CLASSES` (`design_rules.py:324-431`) constitute the complete type universe for the initial lattice; new classes added to this dict automatically participate in lattice inference if they carry a `safety_category` value

---

## Outstanding Questions

### Resolve Before Planning
- **[Affects R9]** Should UNSAT provenance be emitted as a Python object (rich diagnostics consumable by the Stage 3 pipeline) or logged as structured text in the Rust crate? The existing `audit.rs` returns violations as Python dicts through PyO3 — a similar pattern is likely correct
- **[Affects R3]** What are the exact clearance values for each safety-type pair in the type lattice? The current codebase has: HV-HV → implicitly 3mm (same safety domain, only intra-class clearance applies from `NetClassRules.clearance`), HV-LV → 6mm (`creepage_mm` from the HV class), AC-LV → 6mm (`creepage_mm` from ACMains). Are these configurable per-board (loaded from the active `DesignRules` at invocation time) or hard-coded in the compiler? The former matches the SSOT principle (N2) but adds a config surface; the latter is simpler but duplicates the values
- **[Affects R4]** Does the lattice need a concept of `iso` as a full category, or is `iso` semantically "neither HV nor LV" (a barrier)? The `iso` value is declared in the `safety_category` Literal but no net class currently uses it in `TEMPER_NET_CLASSES`. How does `iso` participate in meet/join?

### Deferred to Planning
- **[Technical, affects R5]** How many desugaring tiers, and what intermediate IR structures between them? The requirement says "at minimum 3" but the exact number and the IR data structures are design decisions for the planning phase
- **[Technical, affects R2]** PyO3 binding shape — expose a single `compile_pcl_to_sat(pcl_dicts, net_classes, skeletons, channel_widths) -> (augmented_variables, augmented_constraints)` function, or expose a stateful compiler object with an incremental recompilation API (`Compiler::compile()`, `Compiler::recompile_delta(changed_net_indices)`)
- **[Needs research, affects R3/R7]** Can the type lattice be proven complete — covering all PCB constraint interactions that emerge from the 4 safety categories — or is the lattice inherently extendable (new categories require new meet/join rules)? The ideation doc suggests confidence is 80% that the lattice adequately covers the induction cooker design; proving completeness for the general PCB case may require a formal specification of what "complete" means in this context
- **[Needs research]** Should the Tier 1 geometric IR reuse or mirror the existing `PlacementConstraints` representation from the Python pipeline, or define an independent geometric constraint vocabulary? A shared representation would simplify round-tripping but couples the compiler to Python-side types
