# quality-oracle marshalers: JUSTIFIED-KEEP (2026-08-09)

**Module**: `packages/temper-placer/src/temper_placer/validation/human_reference_extractor.py`
**Marshalers**: `_netlist_to_oracle_dict` (L382–401), `_placement_to_oracle_dict` (L404–417)
**Classification**: product-runtime → **JUSTIFIED-KEEP**
**LOC**: 32
**Consumers**:
- `human_reference_extractor.py:462–467` — `prepare_quality_py` + `evaluate_prepared_py` (primary)
- `io/reference_loader.py:22–35` — imports + same two-step pipeline (secondary)

**Dependency surface** (Python only): `temper_placer.core.netlist` (pyclasses from `temper-design-bundle`), `temper_placer.core.state` (dataclass), `temper_placer.core.board` (pyclass from `temper-design-bundle`), `numpy` (for `asarray(…, float64)`).

## What they do

Two thin adapters between the placer's typed Python objects and the quality oracle's dict-based API:

| Marshaler | Input | Output dict shape | Rust consumer |
|---|---|---|---|
| `_netlist_to_oracle_dict` | `Netlist` (pyclass) | `{nets: [{name, pins}], components: [{ref, footprint, width, height}]}` | `extract_netlist()` in `temper-quality-oracle/src/lib.rs:46` |
| `_placement_to_oracle_dict` | `PlacementState` (dataclass) + `Netlist` + `Board` | `{positions: [f64, …], component_refs: [str, …], board_width_mm, board_height_mm}` | `extract_placement()` in `temper-quality-oracle/src/lib.rs:239` |

## Why JUSTIFIED-KEEP (concrete blocker)

**The dict IS the pinned API.** `temper_quality_oracle`'s three public pyfunctions — `evaluate_quality_py`, `prepare_quality_py`, `evaluate_prepared_py` — all accept `&PyDict` for their netlist and placement arguments. These are the crate's documented, multi-consumer interface (3 Python files × 5 call sites, plus 7 test sites in `test_quality_oracle.py`). The dict shape documented above is the contract.

**The placer types are not simple data containers.** `Netlist` is a pyo3 pyclass from `temper-design-bundle` with computed index fields (`_component_index`, `_net_index`, `_component_nets`) and `dataclasses.replace` compatibility. `PlacementState` is a Python `@dataclass` with `numpy.ndarray` fields. Converting these to the quality oracle's Rust types (`types.rs::Netlist { nets: Vec<NetInfo>, components: Vec<ComponentInfo> }`) is not a zero-cost cast — it is a semantic transformation that the 32-line marshaler already performs.

**Migrating would duplicate the type hierarchy.** Adding pyclass versions of `Netlist`/`PlacementState` to `temper-quality-oracle` would create a second, parallel representation of the same concepts in a different crate — with its own maintenance burden, its own `FromPyObject` extractors, and a coupling contract between the two representations. The netlist/board pyclass migration (Wave 4 Phase 3 candidate 1, `temper-design-bundle`) already established the canonical pyclass location; duplicating a subset of those types in `temper-quality-oracle` breaks that consolidation.

**Cost/benefit: negative.** The two marshalers total 32 lines. Migrating them to Rust requires:
1. New `#[pyclass]` types in `temper-quality-oracle/src/types.rs` (Netlist, NetInfo, ComponentInfo, PlacementState) — the existing plain structs are already those types; making them pyclasses adds pyo3 boilerplate (~100+ LOC)
2. New `#[pyfunction]` overloads (or `FromPyObject` impls) for `prepare_quality_py` / `evaluate_prepared_py` / `evaluate_quality_py`
3. Consumer updates in `reference_loader.py` and `test_quality_oracle.py`
4. Backward-compatibility bridge for the existing dict-based callers (or a hard cutover)

The migration saves at most 32 LOC of Python at a cost of 100+ LOC of Rust boilerplate + 3-file consumer churn. This is not a marshalling-boundary migration where the Rust side already has the types and the Python side is doing redundant work — the Rust side *is* the dict API, and the Python side is the thinnest possible adapter.

## Re-decidable trigger

When one of the following becomes true, this verdict should be re-reviewed:
1. `temper-quality-oracle`'s types (`Netlist`, `PlacementState`) are already pyclasses for another reason (e.g., the crate exposes them for direct use by other Rust consumers)
2. The placer's `Netlist`/`PlacementState` types are themselves replaced by `temper-quality-oracle` pyclasses (i.e., the type hierarchy is unified rather than duplicated)
3. The dict-based API is deprecated in favor of a typed interface

## Recorded evidence

- **Oracle test**: `tests/validation/test_marshaler_dict_shapes.py` — 15 assertions pinning every key, value type, and edge case (empty, int→float cast, pin-ref stripping, float32→float64 upcast, component ordering). Green on commit.
- **This document**: follows the residual decision procedure (`docs/wave4-discipline-contract.md` §3), step 3 recording template: LOC, consumers, dependency surface, concrete blocker, re-decidable trigger.
- **Date**: 2026-08-09 · **Branch**: `fanout2/marshal-2` · **Commit**: (to be recorded)
