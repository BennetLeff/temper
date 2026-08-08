---
title: BusCohortConstraint Pyclass Migration — closes DesignRules.bus_cohorts opacity
type: feat
date: 2026-08-08
topic: buscohort-pyclass-migration
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: ce-brainstorm
status: proposed
swept: 2026-08-08
---

# BusCohortConstraint Pyclass Migration

## Goal Capsule

**Objective:** Migrate `temper_placer/core/bus_cohort.py`'s `BusCohortConstraint`
(191 LOC, dataclass) to a pyo3 pyclass in `temper-design-bundle`, following the
Wave-C core-contracts pattern (`net_graph_contracts.rs`,
`differential_pair_contracts.rs`). The module becomes a pure-delegation shim
re-exporting the pyclass. `BusRegistry` stays Python (it is registry state:
`dict[str, ...]` + a reverse map, no compute worth crossing the boundary).

**Root cause / blocker addressed:** Per
`docs/evidence/2026-08-06-pyany-surface-audit-2.md` §4 Wave C, `DesignRules.bus_cohorts`
(`design_rules.rs:354`, `Py<PyList>`) was explicitly excluded from the Wave-C
migration because its element type (`BusCohortConstraint`) is still pure Python.
Migrating the type makes `bus_cohorts`' elements same-crate pyclasses and lets
`DesignRules.get_bus_cohort_for_net` (`design_rules.rs:789`, currently duck-typed)
be typed. The container *type* does not change (`Py<PyList>`, identity-mutable).

**Product authority:** temper-design-bundle + temper-placer maintainers.

**Open blockers:** none. The module is a pure-stdlib dataclass (list container,
three `__post_init__` checks, one property). No numpy, no IO, no compute kernels.

---

## Product Contract

### Summary

`BusCohortConstraint` is `@dataclass` with scalar fields (`name: str`,
`pitch_mm: float`, `max_skew_mm: float`, `allow_swapping: bool`) plus one
container (`nets: list[str]`). `__post_init__` runs three checks in order:
empty-nets → `ValueError`, `pitch_mm <= 0` → `ValueError`, `max_skew_mm < 0` →
`ValueError`. `signal_count` is a read-only property (`len(nets)`).

Migration follows the fully-opaque storage pattern from `netlist_contracts.rs`
and `differential_pair_contracts.rs` (D1): every scalar field stores the exact
Python object passed (preserving int-vs-float identity, e.g. `pitch_mm=1`
stays an int), `__repr__`/`__eq__` delegate to CPython via `repr_of` /
`dataclass_eq`, `__hash__` raises `unhashable` (dataclass is `eq=True`,
`frozen=False`). `nets` is `Py<PyList>` (identity-preserving getter via
`clone_ref`, matching the Wave-C `edges` pattern). The three `__post_init__`
checks replicate in `#[new]` with bit-exact `ValueError` message text and the
same order.

### Key Decisions

- **D1. Fully-opaque storage for scalars, typed `Py<PyList>` for `nets`**
  (plan-settled, Wave-C precedent). `name` could be `String` (str is
  coercible), but opaque keeps dataclass semantics by construction and matches
  the established pattern; `nets` is typed `Py<PyList>` because the annotation
  is `list[str]` and the container is identity-mutated in-place by consumers
  (`config_loader` builds the list then passes it; `get_bus_cohort_for_net`
  reads it back). Typed `Py<PyList>` from the start (E.2 in Wave-C, settled the
  same way).

- **D2. `__repr__`/`__eq__` delegate to CPython** (plan-settled, Wave-C). The
  `repr_of` / `dataclass_repr` / `dataclass_eq` helpers from `netlist_contracts.rs`
  are reused; no manual float/str rendering (avoids B9/B10 divergence classes).

- **D3. `__post_init__` validation replicated in `#[new]` in declaration
  order** (plan-settled, Wave-C). Check 1: `not self.nets` →
  `ValueError("Bus cohort must contain at least one net.")`. Check 2:
  `pitch_mm <= 0` → `ValueError(f"pitch_mm must be positive, got {self.pitch_mm}")`
  with the interpolated value rendered via CPython `str()` (the R-B mitigation
  from Wave-C: `obj.bind(py).str()?.to_string()`, not Rust `format!`). Check 3:
  `max_skew_mm < 0` → `ValueError(f"max_skew_mm must be non-negative, got {self.max_skew_mm}")`.
  The empty-nets check runs first; a caller passing `nets=[]` gets the empty-net
  error, not the pitch error.

- **D4. `signal_count` is a getter returning `self.nets.bind(py).len()`**
  (plan-settled). The property is `len(nets)`; the stored `Py<PyList>`'s length
  is the value, read live so in-place list mutation is reflected.

- **D5. `BusRegistry` stays Python** (plan-settled). It is `dict[str,
  BusCohortConstraint]` + `dict[str, str]` reverse-map state with
  register/lookup/inference methods. The inference (`infer_buses_from_nets`)
  is string-prefix classification over net names — genuinely Python glue with
  no numeric kernel; a pyclass version would be a container-over-pyclass
  (net-negative per the routing_results.py precedent). Only `BusCohortConstraint`
  migrates.

- **D6. Single G4 verification unit** (plan-settled, Wave-C D5). One module,
  one differential file, one PBT file.

### Requirements

- **R1.** Bit-exact parity with the pre-migration dataclass: identical
  `repr()`, `==`/`!=`, `hash` unavailability, constructor defaults
  (`pitch_mm=0.5`, `max_skew_mm=2.0`, `allow_swapping=False`), field type
  identity (int stays int), `nets` list identity under in-place mutation, and
  the three `ValueError` messages in order (U1, U4).
- **R2.** Behavioral A/B: bit-identical `repr()` on randomized inputs,
  identical `ValueError` text, identical `==` outcomes (U4).
- **R3.** Performance A/B: "no regression beyond noise" (pure-delegation data
  contract; the R2 carve-out applies) (U4).
- **R4.** PBT: >=5 non-vacuous properties, each vacuity-guarded by a mutation
  test (U4).
- **R5.** Metamorphic: >=3 invariant relations per module, honestly bounded
  (U4).
- **R6.** Induction proof: structural (base case + per-field independence) in
  `packages/temper-design-bundle/VERIFICATION.md` (U4).
- **R7.** Rust best-practices bar: no `unwrap` outside tests, `catch_unwind`
  at pyo3 boundaries, borrow over clone (U4).
- **R8.** `DesignRules.bus_cohorts` element typing + `get_bus_cohort_for_net`
  typed: the list stays `Py<PyList>`, elements are now `BusCohortConstraint`
  pyclasses; `get_bus_cohort_for_net` compares `bus.nets` membership via Python
  attribute access on the typed element. The audit's stored-`Py<PyAny>` count
  drops by **1** (`bus_cohorts`); `bus_cohorts` is reclassified STILL-NEEDED →
  INTENTIONAL in the next audit. `__eq__`/`__repr__`/`__hash__` of `DesignRules`
  are unchanged (they delegate via the stored list) (U3, U5).
- **R9.** The `config_loader.rs` construction sites for `bus_cohorts` use the
  crate's own type (`py.get_type::<BusCohortConstraint>()`) instead of a
  `temper_placer.core.bus_cohort` Python import, following the Wave-C D6
  resolution pattern (U3).

---

## Unit Breakdown with Gates

### U1. Differential Oracle + TDD Scaffolding

- Verbatim oracle: `tests/core/_bus_cohort_py_oracle.py` — a copy of
  `core/bus_cohort.py`'s `BusCohortConstraint` (dataclass + `__post_init__` +
  `signal_count`), "do not edit — they are the reference".
- Differential: `tests/core/test_bus_cohort_rust_differential.py` — construction
  (required-only / all-defaults / keyword / positional), `repr()` for every
  field-type combination, `==`/`!=`, `hash()` → `TypeError: unhashable type`,
  `nets.append(...)` identity, `signal_count`, and each `ValueError` text+order.
- Red first: the test file's first commit predates the pyclass (G1 TDD).

### U2. BusCohortConstraint Pyclass Implementation

- New file `packages/temper-design-bundle/src/bus_cohort_contracts.rs`
  (register in `lib.rs` alongside the Wave-C contracts).
- `#[pyclass(dict, module = "temper_design_bundle_python.bus_cohort_contracts")]`,
  `#[new]` with `Option<&Bound<'_, PyAny>>` scalars + `Option<&Bound<'_, PyList>>`
  for `nets` (default fresh empty list via `list_or_new`; note the dataclass
  requires non-empty at construction, so a default empty list + the empty-nets
  check means `nets` has no working default — construct with `nets` required,
  matching `BusCohortConstraint(name, nets, ...)`).
- `signal_count` getter, `repr_of`/`dataclass_eq`/`unhashable` helpers.
- Delegation shim: `core/bus_cohort.py` re-exports the pyclass.

### U3. DesignRules Tightening + Config-Loader Resolution

- `design_rules.rs:354` docstring: elements are now `BusCohortConstraint`
  pyclasses; field type unchanged (`Py<PyList>`).
- `get_bus_cohort_for_net` (`:789`): resolve `bus.nets` via `py.getattr` on the
  element; the element is a known pyclass so the lookup can be typed.
- `config_loader.rs`: replace `temper_placer.core.bus_cohort` imports with
  `py.get_type::<BusCohortConstraint>()`.
- Audit re-scan: confirm zero remaining `temper_placer.core.bus_cohort` imports
  in Rust; reclassify `bus_cohorts` in the next PyAny audit.

### U4. Full Gate Suite

G1 TDD / G2 behavioral A/B / G3 perf A/B (no-regression) / G4 PBT / G5
metamorphic / G6 induction / G7 rust bar / G8 R24 N/A (data contract).

PBT properties (>=5):
- P1: `signal_count == len(nets)` always.
- P2: `repr` round-trip renders `nets` as a list and `allow_swapping` as a bool.
- P3: empty-`nets` construction raises the empty-net `ValueError` first.
- P4: negative `pitch_mm` raises before negative `max_skew_mm` (order).
- P5: `nets` identity: `append` through the getter persists.

Metamorphic (>=3):
- MR1: net-list permutation does not change `signal_count` or `repr` modulo list order.
- MR2: default preservation: `pitch_mm=0.5`, `max_skew_mm=2.0`, `allow_swapping=False`.
- MR3: construction-order invariance (positional vs keyword equality).

### U5. Verdict

Module MIGRATED, shim in place, `DesignRules.bus_cohorts` typed,
`get_bus_cohort_for_net` typed, config_loader resolved, audit reclassifies
`bus_cohorts` INTENTIONAL. No `Ceiling-Approval:` trailer needed (no board change).

---

## Risks + Mitigations

- **R-A. Empty-nets default interaction** — the dataclass default factory
  (`field(default_factory=list)`) produces an empty list, but `__post_init__`
  rejects it. Mirror exactly: `#[new]` takes `Option<PyList>`, defaults to a
  fresh empty list, then the empty-nets check raises. The differential pins
  both the `nets=[]` error and the no-arg behavior.
- **R-B. `ValueError` message float rendering** — use CPython `str()` on the
  stored object (Wave-C R-B mitigation), never Rust `format!`.
- **R-C. Registry stays Python** — reviewers may ask why `BusRegistry` isn't
  migrated; the D5 rationale (registry state, no compute) is the answer, same
  class as `router_v6/routing_results.py`'s keep.

## Sequencing

Branch `feat/buscohort-pyclass`, cut from `origin/main` in an isolated worktree
(`make venv-isolate`). U1 → U2 → U3 → U4 → U5. Estimated 3–5 days.

## Non-Goals

- No `BusRegistry` migration (D5).
- No `DesignRules` `__repr__`/`__eq__`/`__hash__` change.
- No change to `core/__init__.py` `__all__` (re-export keeps the name).
- No `_constraint_types` / pcl migration (out of scope).

## Sources

- Audit: `docs/evidence/2026-08-06-pyany-surface-audit-2.md` §2.1/§4 Wave C.
- Precedent: `docs/plans/2026-08-08-001-feat-wavec-core-contracts-migration-plan.md`.
- Source module: `packages/temper-placer/src/temper_placer/core/bus_cohort.py`
  (191 LOC). Consumers: `tests/core/test_bus_cohort.py`, `DesignRules`
  (`design_rules.rs:354,789`) and `config_loader.rs` construction sites.
- Discipline: `docs/wave4-discipline-contract.md` (G1–G8, B1–B13).
