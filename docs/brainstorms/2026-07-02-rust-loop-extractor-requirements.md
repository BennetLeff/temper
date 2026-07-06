---
date: 2026-07-02
topic: rust-loop-extractor
---

# Rust Loop Extractor Crate

## Summary

A new Rust crate `temper-loop-extractor-rs` ports the half-bridge loop extraction algorithm — replacing silent `None` failures with `Result<T, ExtractionError>`, adding compile-time pin-mapping tables, and verifying correctness through proptest PBT and BMC induction ladders proving topological invariants. Exposed to Python via PyO3/maturin, sibling to `temper-rust-router` and `temper-drc-rs`.

---

## Problem Frame

The Python loop extractor (`packages/temper-placer/src/temper_placer/core/loop_extractor.py`) has four known failure modes on the Temper board that are unfixable without structural changes to how the extractor handles types and errors:

1. **Numeric pin names** (TO-247): Q1/Q2 use pin `"2"` = collector/drain. The extractor only matches string names `"DRAIN"`, `"COLLECTOR"` — no pin-map for TO-247. DC+ bus rail not found, commutation loop extraction fails.
2. **Split-capacitor topology**: C_BUS1 spans DC_BUS+/PGND, C_BUS2 spans PGND/DC_BUS-. The extractor's `find_capacitors_between` checks for a single capacitor connected to both rails directly. No bus capacitor found, extraction fails.
3. **Missing MPN values**: The parser doesn't populate `attributes["MPN"]`, so heuristic MPN-based IGBT/MOSFET detection falls through. Components are detected only by footprint name (TO-247), with confidence 0.7 and no subcategory.
4. **Silent failures**: Every extraction step returns `None` on failure with zero error information. `auto_extract_loops` silently skips failed extractions — the caller has no way to distinguish "no topology present" from "topology present but extraction bug."

Beyond these fixes, the Rust port delivers guarantees Python cannot express: `match` exhaustiveness on pin-mapping tables catches missing package types at compile time; `Result<T, ExtractionError>` forces explicit error handling; and type-safe graph types prevent string-keying bugs. The extraction algorithm is fundamentally a graph reachability problem — these invariants are provable through BMC induction.

---

## Actors

- A1. **Placer Pipeline** — the Python `quality_orchestrator` at `packages/temper-placer/src/temper_placer/quality/orchestrator.py` that invokes `auto_extract_loops` to produce a `LoopCollection` for constraint generation
- A2. **Developer** — the person debugging a failed extraction or adding support for a new component package, who needs actionable error messages and pin-mapping guidance
- A3. **CI Gate** — the test suite that runs PBT and BMC induction tests per PR, verifying that extraction invariants hold for all generated netlists

---

## Key Flows

- F1. **Extract loops for a known half-bridge (Python caller)**
  - **Trigger:** Placer pipeline invokes `auto_extract_loops(netlist)` with a Temper board netlist
  - **Actors:** A1
  - **Steps:** Python passes `Netlist` across PyO3 boundary → Rust classifies components via pin-mapping + footprint → Rust detects half-bridge topology → Rust traces commutation, gate drive, and bootstrap loops → Rust returns `Result<LoopCollection, ExtractionError>` → Python caller processes result or handles error
  - **Outcome:** A `LoopCollection` with 3-4 loops, or a structured error identifying the missing net/pin/component
  - **Covered by:** R1, R2, R3, R4, R5, R8

- F2. **Extraction fails with an actionable error**
  - **Trigger:** Netlist has a TO-247 IGBT but no pin-mapping for pin `"2"`
  - **Actors:** A1, A2
  - **Steps:** Rust pin-mapping lookup for `TO-247-3` → pin `"2"` not in the compile-time mapping → Rust returns `ExtractionError::UnmappedPin { component_ref, footprint, pin_number, known_names }`
  - **Outcome:** Python caller receives an error with component ref, footprint, the unmapped pin number, and the list of known pin names for that package — developer can fix the pin-mapping table
  - **Covered by:** R2, R6

- F3. **CI verifies extraction invariants on every PR**
  - **Trigger:** `cargo test --lib` or `cargo test --test proptest_*`
  - **Actors:** A3
  - **Steps:** proptest generates random half-bridge netlists → extraction runs on each → soundness invariant (every component in loop is reachable via claimed net path) is checked → BMC base-case (minimal 2-switch + 1-cap netlist) is verified → BMC inductive step (add one unrelated component to a valid netlist, loop still found) is verified
  - **Outcome:** No invariant violations across the generated space; induction ladder passes for bounded component count
  - **Covered by:** R9, R10, R11, R12, R13

---

## Requirements

**Error handling and failure modes**

- R1. Every extraction step that can fail must return `Result<T, ExtractionError>` — no silent `None` on failure. The error variant must carry enough context for the caller to diagnose the failure without inspecting source code.

- R2. `ExtractionError` must include variants for each distinct failure mode: `UnmappedPin` (missing pin in pin-mapping table), `MissingNet` (expected net not found on a component), `NoBusCapacitor` (no capacitor path between DC+ and DC-), `NoTopology` (no half-bridge detected), and `NoSwitchNode` (switches don't share a common net). Each variant must carry component ref, footprint, pin/net names, and any known alternatives as structured fields — not format strings.

- R3. Error messages must be actionable: an `UnmappedPin` error for TO-247 pin `"2"` must include the list of known pin names for TO-247 (`["GATE", "COLLECTOR", "EMITTER"]`) so the developer knows what to add to the mapping.

**Pin-mapping tables**

- R4. The crate must define a compile-time pin-mapping table mapping `(footprint_name, pin_number)` to canonical pin name. The mapping must be exhaustive for all supported packages — adding a new package without adding its pin mapping is a compile error (match exhaustiveness or equivalent).

- R5. Pin lookup must try both the canonical pin name and the numeric pin number. When a component uses numeric pin names (e.g., TO-247 pin `"2"`), the mapping resolves it to the canonical name (`"COLLECTOR"`) for downstream graph traversal. A missing numeric pin in the table is an `UnmappedPin` error.

- R6. The pin-mapping table must cover at minimum: TO-247-3 (IGBT), TO-220-3 (MOSFET), TO-263-3 (MOSFET), SOIC-8 (gate driver), and generic 2-pin THT/SMD capacitor footprints.

**Component classification**

- R7. Component classification must use three tiers in priority order: (a) MPN-based heuristics (highest confidence, 0.9), (b) footprint-pattern matching (confidence 0.7), (c) ref-prefix fallback (lowest confidence). Classification must not require MPN to be present — the fallback chain must always produce a classification for any component.

- R8. Classification must distinguish `power_switch` (with subcategory `igbt` or `mosfet`), `gate_driver`, `capacitor` (with subcategory `bus`, `bootstrap`, or `decoupling`), `diode` (with subcategory `bootstrap` or `generic`), `resistor` (with subcategory `gate` or `generic`), and `other`.

**Topology detection and loop extraction**

- R9. Topology detection must find half-bridge pairs (two switches sharing a common net) and determine high-side vs low-side. High-side is the switch whose collector/drain connects to the higher-voltage rail.

- R10. Commutation loop extraction must support split-capacitor topologies: if no single capacitor spans DC+ and DC- directly, the extractor must search for a capacitor chain through intermediate nets (e.g., C_BUS1 on DC_BUS+/PGND and C_BUS2 on PGND/DC_BUS-). The result must include all capacitors in the path.

- R11. Gate drive loop extraction must find the gate resistor (if present) on the gate net and include it in the loop component list. Extraction succeeds even when no gate driver is found (loop includes switch + resistor only).

- R12. Bootstrap loop extraction must detect bootstrap circuits by: finding a capacitor with "BOOT" in its ref, finding a diode that shares a net with that capacitor, and including both in the loop.

- R13. Merge behavior: when merging auto-extracted loops with manual loop definitions, manual definitions take precedence. An auto-extracted loop named `auto_foo` is overridden by a manual loop named `foo` or `auto_foo`. Manual loops not present in auto-extraction are retained unchanged.

**Correctness verification**

- R14. **Soundness invariant**: For every component in an extracted loop, there must exist a path through the nets in the loop's net list connecting that component to every other component in the loop. Verified by proptest: for all generated netlists, the invariant holds for every extracted loop.

- R15. **Completeness invariant (half-bridge)**: If the netlist contains exactly two `power_switch` components sharing a common net and a bus capacitor (or capacitor chain) connecting their rail nets, the commutation loop extraction must succeed. Verified by BMC base case + inductive step.

- R16. **Uniqueness invariant**: For the same netlist input, the extracted loop set must be deterministic — same components in same order every run. Verified by proptest: extracting twice on the same generated netlist produces identical `LoopCollection`.

- R17. **Termination invariant**: Extraction must terminate for any netlist size. Verified by induction: base case (empty netlist terminates in O(1)), inductive step (adding one component does not introduce unbounded iteration).

**BMC induction ladder**

- R18. Base case: extraction on a minimal valid half-bridge (2 switches + 1 bus cap, 3 nets, 2 components) must produce exactly one commutation loop and must not panic or timeout.

- R19. Inductive step (add): given a netlist with a successfully extracted half-bridge, adding one unrelated component (resistor, capacitor, IC) must not cause extraction to fail — the same loops must still be found, unchanged. Verified up to a bounded component count N=20.

- R20. Inductive step (modify): changing the footprint of a non-switch component (e.g., R_0805 → R_0603) must not change the extracted loop set. Verified by proptest with component-modify strategies.

- R21. Inductive step (remove): removing an unrelated component from a netlist with successfully extracted loops must not cause extraction to fail — loops must stay the same. Verified up to N=20.

**Python bindings**

- R22. The crate must expose a single PyO3 entry function `auto_extract_loops_rust(netlist_dict, topology_hints: Optional[dict]) -> dict` that accepts a Python `Netlist` serialized as a dict and returns either a `LoopCollection` serialized as a dict (on success) or raises a Python exception with the `ExtractionError` details (on failure).

- R23. The Python integration module must provide a `auto_extract_loops` wrapper that delegates to Rust when the crate is importable and falls back to the existing Python extractor when unavailable. The fallback must emit a warning when used.

- R24. Loop, LoopCollection, LoopEvent, and LoopPin remain Python dataclasses — the Rust crate produces dict representations that the Python wrapper converts to these dataclass instances.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R6.** Given a netlist with a TO-247 IGBT where pin `"2"` has no mapping entry, when commutation loop extraction runs, the result is `Err(ExtractionError::UnmappedPin { component_ref: "Q1", footprint: "TO-247-3", pin_number: "2", known_names: ["GATE", "COLLECTOR", "EMITTER"] })`.

- AE2. **Covers R10.** Given a netlist with C_BUS1 on DC_BUS+/PGND and C_BUS2 on PGND/DC_BUS-, when commutation loop extraction runs, the bus capacitor is found via capacitor chain search and the loop includes `["C_BUS1", "C_BUS2", "Q1", "Q2"]` in its component list.

- AE3. **Covers R7, R8.** Given a netlist with a power switch whose `attributes["MPN"]` is missing but whose footprint is `TO-247-3` and ref is `Q1`, when classification runs, the result is `ComponentClassification::PowerSwitch { subcategory: Some(Subcategory::Igbt), confidence: Confidence(0.7) }` — not `Other` and not a panic.

- AE4. **Covers R14, R18.** BMC base case: `auto_extract_loops(half_bridge_minimal_netlist())` returns a `LoopCollection` with exactly one commutation loop. Running the soundness check verifies every component in that loop has a valid net path to every other component.

- AE5. **Covers R15, R19.** Proptest: for any generated netlist with two power switches sharing a net and a capacitor chain between their rails, `auto_extract_loops()` must return `Ok`. Adding 18 unrelated components (up to N=20) does not change this outcome.

- AE6. **Covers R13.** Given auto-extracted loops `["auto_commutation", "auto_gate_drive_Q1"]` and a manual loop named `"commutation"` with `max_area_mm2=300`, when merged, the result contains `"commutation"` with `max_area_mm2=300`, `"auto_gate_drive_Q1"`, and zero duplicates.

- AE7. **Covers R23.** On a system where `temper-loop-extractor-rs` is installed, `auto_extract_loops(netlist)` delegates to Rust. On a system without it, the call falls back to the Python extractor and emits a warning — no `ImportError`, no crash.

---

## Success Criteria

- SC1. All four concrete Temper board failures are resolved: numeric TO-247 pins are mapped, split-capacitor topology is detected, missing MPN values don't block classification, and every failure produces an actionable error instead of silent `None`.
- SC2. The existing Python test suite (`tests/core/test_loop_extractor.py`, 25 tests, 525 lines) passes against the Rust backend when wired through the Python wrapper — same inputs produce same loop sets.
- SC3. Proptest finds zero invariant violations across 10,000 generated half-bridge netlists of 2-20 components (soundness, completeness, uniqueness, termination).
- SC4. The BMC induction ladder passes for all base-case and inductive-step tests up to N=20 components.
- SC5. CI can run `cargo test --lib` and `cargo test --test proptest_*` as part of every PR — no out-of-band setup required.

---

## Scope Boundaries

- Topologies beyond half-bridge (H-bridge, buck, boost, flyback) are deferred — the crate supports only half-bridge detection and extraction
- Loop, LoopCollection, LoopEvent, and LoopPin types remain Python dataclasses — the Rust crate produces dict representations, not `#[pyclass]` mirrors
- Manual loop definition loading (YAML parsing) stays in Python — the Rust crate handles extraction only
- The `loop_area` DRC check in `temper-drc-rs` is separate work — this crate produces loops but does not verify their areas
- Performance benchmarking is deferred — correctness guarantees ship first; profiling-guided optimization follows
- The remainder of the physics oracle chain (quality config, optimizer, `compute_quality_report`) stays in Python

---

## Key Decisions

- **Compile-time pin-mapping over runtime config**: A compile-time table (`match`-exhaustive) catches missing packages at build time, consistent with the repo's existing Rust type-level invariant pattern in `temper-drc-rs/src/types/`. Adding a new package is a code change + `cargo check`, not a config update that silently doesn't apply.
- **Dict-based PyO3 bridge over `#[pyclass]` mirrors**: The existing Rust crates use a pattern of accepting Python dicts and returning Python dicts (e.g., `temper-drc-rs` accepts `board_dict` and returns violation dicts). Following this avoids duplicating the Loop/LoopCollection type hierarchy in Rust and keeps the Python dataclasses as the single source of truth.
- **`thiserror` for error types**: Matches `temper-drc-rs` convention and enables `?` propagation through the extraction pipeline. Each error variant is a struct with named fields, not a format-string Enum.
- **Split-capacitor support as graph path-finding**: Rather than adding ad-hoc heuristics, the fix generalizes `find_capacitors_between` to find a capacitor chain through intermediate nets — treat the component-net graph as undirected, find paths from DC+ to DC- that traverse only capacitor nodes. This is correct for arbitrary capacitor networks, not just the 2-cap split case.

---

## Dependencies / Assumptions

- **Existing Rust infrastructure**: `temper-rust-router` and `temper-drc-rs` prove that PyO3 0.23 + maturin + edition 2024 + `cargo test` work in this repo's CI. The new crate follows the same conventions.
- **`proptest` dev-dependency**: `temper-rust-router` already depends on `proptest = "1"` as a dev-dependency. The new crate adds `proptest` with `#[test]` functions, no new CI infrastructure needed.
- **Netlist dict schema**: The Python `Netlist` dataclass is serialized to a dict conforming to a stable schema before crossing the PyO3 boundary. The schema must be documented and versioned so the Rust side can deserialize without depending on Python internals.
- **Capacitor chain length**: The split-capacitor path search assumes capacitor chains of length ≤ 5 nodes. An unbounded BFS is computationally safe (netlist size is small, typically < 200 components), but the induction proof is only valid for bounded chains.
- **Component refs and net names are unique**: The netlist validation in `Netlist.validate()` already enforces this — the Rust crate can assume uniqueness without re-checking.

---

## Outstanding Questions

### Resolve Before Planning

- [Affects R10][Design] Should the capacitor chain search for split-capacitor topologies be limited to capacitors (series chain), or should it also consider inductors and ferrite beads that could form part of the DC bus path? The current scope assumes capacitors only.

### Deferred to Planning

- [Affects R22][Technical] What is the exact dict schema for `Netlist` crossing the PyO3 boundary? The schema must include components, nets, pins, and attributes — define in planning.
- [Affects R24][Technical] How are `Loop` and `LoopCollection` dicts constructed on the Rust side and deserialized to Python dataclasses? The deserialization layer (a thin Python shim) is a planning detail.
- [Affects R9][Needs research] How is high-side vs low-side determined when both switches have identical footprints and no MPN values? The current heuristic (Q1 = high) may not generalize — the BMC induction ladder must handle ambiguous ordering.
- [Affects R19][Needs research] The inductive-step "add one unrelated component" needs a formal definition of "unrelated" in the component-net graph. A component that creates a new capacitor path between the rails is related — this must be excluded from the proptest strategy.
