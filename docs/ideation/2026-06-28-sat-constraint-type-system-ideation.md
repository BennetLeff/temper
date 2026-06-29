---
date: 2026-06-28
topic: sat-constraint-type-system
focus: Encoding real semantic / PCB designer-level constraints into the SAT solver with a type system while managing exponential explosion
mode: repo-grounded
---

# Ideation: SAT Semantic Constraint Encoding with Type System

## Grounding Context

**Codebase context:** Temper induction cooker — temper-placer (JAX placement + router-v6) + temper-rust-router (splr CDCL SAT). The routing SAT model knows only 3 low-level constraint types (Capacity, DiffPair, Layer). PCL defines 7 placement constraints with HARD/STRONG/SOFT tiers — but the two systems are completely separate. `NetClassRules` safety categories (HV/LV/AC/iso) exist in the data model but never reach the SAT encoder. The primary explosion-management lever is `max_sat_nets` (selective routing by pin count).

**Past learnings:** (1) 228K-variable models required selective net construction. (2) Unsound AtMostK needed 3-layer correctness (proof + CDCL + audit). (3) Pydantic `BaseModel(frozen=True)` + `Literal` pattern for type safety. (4) 6mm HV creepage was "known to router but invisible to placement." (5) Per-stage DRC fence auto-discovers invariants.

**External context:** LCG, WPMS, CEGAR all structurally map to PCB routing. Quilter.ai uses RL for constraint literacy (not SAT/SMT). Multi-sorted logic / dependent types exist academically but have no operational PCB routing implementation.

## Topic Axes

1. **Constraint encoding vocabulary** — Type-system abstractions between "designer says keep HV isolated" and SAT variables/clauses
2. **Explosion containment architecture** — Strategies for preventing model blowup when richer constraints are added
3. **Encoding correctness** — Formal verification of constraint encodings
4. **Placement↔Routing constraint flow** — How semantic constraints flow between placement and routing
5. **Constraint composition** — How multiple semantic constraints compose without interaction bugs

## Ranked Ideas

### 1. Constraint Lattice & Multi-Tier Lowering Compiler

**Axis:** Constraint encoding vocabulary
**Description:** Build a compiler pipeline that takes designer-level semantic constraints (using NetClassRules safety categories as types) and mechanically lowers them through successive desugaring passes into the existing low-level SAT constructs (Capacity, DiffPair, Layer). A Hindley-Milner-style type lattice propagates safety-category judgments through the net topology graph.
**Basis:** `direct:` NetClassRules safety categories exist in the core data model. PCL→JAX compilation already proven. `reasoned:` Compiler multi-pass architecture — each pass transforms richer IR into simpler one until reaching the "target ISA."
**Rationale:** Decouples "what designers say" from "what the SAT solver sees." New semantic constraints cost only a tier-appropriate desugaring rule.
**Downsides:** Significant upfront investment. Type lattice propagation requires careful specification.
**Confidence:** 80%
**Complexity:** High
**Status:** Unexplored

### 2. Hierarchical Net Bundling with Type-Gated Lazy Grounding

**Axis:** Explosion containment architecture
**Description:** Pre-partition nets into bundle equivalence classes sharing the same type signature and geometric neighborhood. Encode constraints once per bundle class, then instantiate per-net clauses lazily via homomorphism. Lazy grounding gated by constraint type (safety eager, performance lazy, aesthetic never).
**Basis:** `direct:` max_sat_nets proves selective construction works. `external:` LCG (Ohrimenko et al. 2009) demonstrates deferred grounding reduces model size 10–100×.
**Rationale:** Multiplicative lever on top of max_sat_nets — compresses representation of nets that survive filtering.
**Downsides:** Bundle analysis is graph-isomorphism problem. May require splr API extensions.
**Confidence:** 75%
**Complexity:** High
**Status:** Unexplored

### 3. UNSAT Provenance + Pre-Solve Constraint Tension Detection

**Axes:** Encoding correctness + Constraint composition
**Description:** Pre-solve: detect analytically-incompatible constraint pairs. At solve time: instrument every clause with provenance metadata, reverse-map UNSAT cores to conflicting designer-level constraints.
**Basis:** `direct:` Zero backward traceability from SAT clause space to semantic constraint space currently. `reasoned:` Spatial implications can be partially evaluated without solving.
**Rationale:** Transforms debugging from clause space (thousands) to constraint space (3–10).
**Downsides:** Provenance metadata adds 10–20% memory overhead per clause.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Unexplored

### 4. Bidirectional PCL Constraint IR — Single Language, Multiple Backends

**Axis:** Placement↔Routing constraint flow
**Description:** PCL becomes unified constraint IR. Each PCL constraint carries multi-backend compilation targets (JAX placement, SAT routing, DRC assertions). SAT UNSAT cores compile upward to new PCL constraints triggering re-placement.
**Basis:** `direct:` PCL defines 7 constraint types feeding JAX placement; routing SAT has zero awareness. Creepage lesson documents the cost of this gap.
**Rationale:** Every new PCL constraint type automatically gains SAT grounding with no per-stage translation tax.
**Downsides:** Requires PCL refactoring. Bidirectional flow needs guardrails against runaway constraint generation.
**Confidence:** 85%
**Complexity:** High
**Status:** Unexplored

### 5. Constraint Combinator Library with Soundness-Preserving Composition

**Axis:** Constraint composition
**Description:** Identify ~6 primitive constraint encodings with inductive correctness proofs. All designer-level constraints are compositions of primitives. Composition rules are machine-verified once. Library doubles as rewrite engine for pre-CNF simplification.
**Basis:** `reasoned:` Combinator-library pattern from functional programming. Small set of proven primitives compose to express complex behavior.
**Rationale:** Maximal leverage — prove ~6 primitives once, every future constraint is free.
**Downsides:** Requires formal specification of all primitives and composition rules.
**Confidence:** 70%
**Complexity:** High
**Status:** Unexplored

### 6. Railway-Style Bounded Model Checking for Encoding Correctness

**Axis:** Encoding correctness
**Description:** Define Encoder Specification Language declaring what each constraint means in SAT terms. BMC-verify that CNF output is equivalent to spec for all bounded topologies (e.g., all 4-net topologies). Existing Hypothesis PBT infra provides exhaustive base-case enumeration.
**Basis:** `external:` Railway interlocking formal verification (CENELEC EN 50128) uses SAT-based BMC for safety-critical routing. `direct:` Sinz encoding already exhaustively verified for small-n.
**Rationale:** Catches unsound encodings before any solve runs — not discovered at runtime like the AtMostK bug.
**Downsides:** BMC only proves correctness up to bound. ESL is additional engineering surface.
**Confidence:** 80%
**Complexity:** Medium
**Status:** Unexplored

### 7. Routability Gradient Signal for Differentiable Placement↔SAT Co-Optimization

**Axis:** Placement↔Routing constraint flow
**Description:** Extract solver-internal statistics (backtrack count, clause-learning activity, UNSAT core size) as continuous routability signal. Feed back to JAX placement via straight-through estimator as differentiable penalty term.
**Basis:** `direct:` JAX placement already optimizes multi-term differentiable loss. `reasoned:` Solver statistics can be surrogate-gradiented via STE. `external:` CEGAR demonstrates abstract-and-refine loop.
**Rationale:** Placement learns to produce easy-to-route layouts, not just short-wire-length layouts.
**Downsides:** Surrogate gradient introduces noise. Requires splr instrumentation for internal statistics exposure.
**Confidence:** 65%
**Complexity:** High
**Status:** Unexplored

## Rejection Summary

| # | Idea | Reason |
|---|------|--------|
| 1 | Eager Cathedral (full pre-encoding) | Too extreme — not practically actionable |
| 2 | Type-Check Router (no SAT solver) | Subject-replacement — replaces SAT, not encodes in it |
| 3 | Proof-Carrying Trace (zero SAT variables) | Subject-replacement |
| 4 | Native-Type SAT (solver understands Pydantic) | Too speculative; better as brainstorm variant |
| 5 | Semantic Compressor (100-var cap) | Loses too much routing expressiveness |
| 6 | Per-Family Solver Strategy Dispatch | Merged into Lazy Grounding (#2) |
| 7 | SMT Theory Encoding (skip CNF) | Merged into Lowering Compiler (#1) |
| 8 | Fuzzed Invariant Guard (proptest) | Subsumed by Railway BMC (#6) |
| 9–40 | 32 additional ideas | Duplicates, insufficient basis, below ambition floor, or already covered |
