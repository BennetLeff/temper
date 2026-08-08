---
title: Wave-C Core Contracts Migration — net_graph + differential_pair → temper-design-bundle pyclasses
type: feat
date: 2026-08-08
topic: wavec-core-contracts-migration
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: ce-brainstorm
status: active
swept: 2026-08-08
swept_basis: "doc-review passed — P1s fixed (container-type overclaim corrected, R8 count 3->2); no units landed yet"
---

# Wave-C Core Contracts Migration — Plan

## Goal Capsule

**Objective:** Migrate the two remaining Wave-C pure-Python data-contract modules
(`temper_placer/core/net_graph.py`, 62 LOC, and
`temper_placer/core/differential_pair.py`, 47 LOC) to pyo3 pyclasses in
`temper-design-bundle`, following the established Phase-2 contracts-as-pyclasses
pattern (`netlist_contracts.rs`, `priority.rs`, `design_rules.rs`). Each source
module becomes a pure-delegation shim re-exporting the pyclass.

**Root cause / blocker addressed:** Per
`docs/evidence/2026-08-06-pyany-surface-audit-2.md` §2.1 Wave C, `DesignRules`
holds containers whose *element types* are cross-module objects: seven
containers store `SubNetEdge`/`NetGraph`/`DifferentialPairConstraint`
instances (`differential_pairs` is `Py<PyList>`, `net_topologies` is
`Py<PyDict>`, etc. — the containers themselves are already typed
`Py<PyList>`/`Py<PyDict>`; only their elements are opaque). These containers
are STILL-NEEDED only because the types they hold (`SubNetEdge`, `NetGraph`,
`DifferentialPairConstraint`) are still pure Python. Migrating those types
makes them same-crate pyclasses, allowing `DesignRules`' containers to hold
typed pyclass elements (`Py<PyList>` of `Py<DifferentialPairConstraint>`,
`Py<PyDict>` of `Py<NetGraph>`) — removing the justification for the opaque
classification and closing two §3 watch-items (`config_loader.rs:1174/1208` —
`core.net_graph`; `config_loader.rs:2004` — `core.differential_pair`). The
container *types* do not change (they are already `Py<PyList>`/`Py<PyDict>`);
the migration documents the element types and reclassifies the fields
(STILL-NEEDED → INTENTIONAL).

**Product authority:** temper-design-bundle + temper-placer maintainers.

**Open blockers:** none. Both modules are pure-stdlib dataclasses with no
third-party deps, no numpy, no IO, and no compute kernels. The `config_loader`
watch-items are import-call-only (constructors + field assignment); the
resolution pattern (use the crate's own type object) is already proven on
`DesignRules` at `config_loader.rs:1968`.

---

## Product Contract

### Summary

Both modules are `@dataclass` data contracts with immutable scalar fields
(strings, floats, ints, optionals) plus identity-mutable container fields
(`list`, `set`) on `NetGraph`. Migration follows the fully-opaque storage
pattern established in `netlist_contracts.rs` § "Why every field is an opaque
`Py<PyAny>`": every scalar field stores the exact Python object the caller
passed, preserving int-vs-float type identity, `None`-vs-`0.0` distinction, and
dataclass `repr`/`eq`/`hash` semantics by construction.

`__repr__` delegates to CPython's own `repr()` on each stored field object
(the `repr_of` helper from `netlist_contracts.rs`), avoiding both B9
(single-vs-double-quotes) and B10 (float exponent rendering) divergence classes
entirely. `__eq__` builds the compare-tuple and defers to Python `tuple.__eq__`,
identical to a generated dataclass `__eq__`. `__hash__` raises
`TypeError: unhashable type` (both dataclasses are `frozen=False, eq=True`,
so Python sets `__hash__ = None`).

`DifferentialPairConstraint.__post_init__` validation is replicated in the
pyclass `#[new]` constructor with bit-exact `ValueError` message text and the
exact same check **order** (spacing → coupling_tolerance → max_skew →
impedance_ohm). The first failing check raises; subsequent checks are not
reached.

`NetGraph`'s mutable containers (`edges: list[SubNetEdge]`,
`star_nodes: set[str]`) follow the established `Py<PyList>` / `Py<PySet>`
identity-preserving pattern: the getter returns the **same** Python object
(not a copy), in-place mutation (`append`/`add`) persists, and the default
factories (`field(default_factory=list)` / `field(default_factory=set)`)
produce a fresh empty container per instance. The three lookup methods
(`get_edge`, `get_outgoing_edges`, `get_incoming_edges`) are reimplemented
as Rust methods on the pyclass, iterating the stored `PyList` and comparing
`source_pin`/`sink_pin` fields via Python attribute access (not stringified
comparison, preserving type identity).

### Key Decisions

- **D1. Fully-opaque storage — every field is `Py<PyAny>`** (plan-settled).
  The established pattern from `netlist_contracts.rs` and `design_rules.rs`:
  storing the caller's exact Python object makes int-vs-float preservation
  true by construction, avoids the B9/B10 repr divergence classes by delegating
  `repr()` to CPython, and simplifies `__eq__` (build tuple, compare via
  Python). The alternative — typed fields (`String`, `f64`, `Option<f64>`) —
  requires manually replicating CPython repr rules (the `py_float_str` /
  `py_str_repr` helpers) and `__eq__` semantics, and silently widens `int 0`
  to `float 0.0` on any repr/eq path that touches the widened value. Both
  modules are small enough (109 LOC total) that the opaque overhead is
  negligible; the pattern's correctness is already verified on `Pin` (12
  fields), `Component` (13 fields), and `ViaTemplate` (5 fields + 1 typed).

- **D2. `__repr__` and `__eq__` delegate to CPython — not reimplemented**
  (plan-settled). The `repr_of` helper from `netlist_contracts.rs`
  (`obj.bind(py).repr()?.extract()`) renders every field via CPython's own
  `repr()`, and `dataclass_repr` assembles the final string. This sidesteps
  B9 (`'name'` vs `"name"`) and B10 (`1e-05` vs `1e-5`, `nan` vs `NaN`)
  entirely — CPython is the authority for both. `dataclass_eq` builds
  `tuple(fields)` on both sides and calls `tuple.__eq__`, the exact operation
  a generated dataclass `__eq__` performs. No manual comparison logic, no
  divergence surface.

- **D3. `DifferentialPairConstraint.__post_init__` is replicated in `#[new]`**
  (plan-settled). pyo3 `#[new]` is the constructor; `__post_init__` logic
  runs there because dataclass `__post_init__` is invoked by `__init__`
  (generated) after field assignment. The four checks are in declaration order
  (the same order `__post_init__` writes them — Python top-to-bottom),
  and each raises `PyValueError` with the exact f-string message text. The
  `impedance_ohm` check is gated on `is not None` (Python identity test)
  before the `<= 0` inequality.

- **D4. `NetGraph` mutable containers are identity-preserving**
  (plan-settled). `edges` is stored as `Py<PyList>` and the getter returns
  `self.edges.clone_ref(py)`. The config_loader (`config_loader.rs:1199`)
  does `graph.edges.append(edge)` — this mutates the SAME list object, and
  the getter must return that identity. Same for `star_nodes` as `Py<PySet>`.
  The defaults (`field(default_factory=list)` / `field(default_factory=set)`)
  create a fresh empty list/set per instance in `#[new]` when the argument is
  `None`. The `list_or_new` / `dict_or_new` helpers from `netlist_contracts.rs`
  are reused for the list fields; a new `set_or_new` helper (mirroring
  `list_or_new`, building a `PySet`) is needed for `star_nodes` since
  `netlist_contracts.rs` has no set variant.

- **D5. The two modules are ONE G4 verification unit** (plan-settled, per the
  G4 cluster rule in `docs/wave4-discipline-contract.md` §1 — "where several
  modules are migrated together behind ONE pinned oracle and ONE shared
  corpus"). Both are migrated in a single PR behind one differential test
  file, one PBT file, and one corpus. The >=5 properties are counted across
  the unit; every module must be reached by >=1 property (module-to-property
  map in the PBT file's docstring). At 109 LOC total across two modules,
  splitting them into separate units with separate gate suites would add
  ceremony disproportionate to the behavior being verified.

  **Module-to-property map (minimum reachability):**
  - `SubNetEdge`/`NetGraph`: P1 (edge lookup consistency), P2 (mutable edges
    identity), P3 (mutable star_nodes identity), P4 (repr round-trip for
    `float | None` fields)
  - `DifferentialPairConstraint`: P5 (validation order and message text), P6
    (repr round-trip with impedance_ohm=None vs float), P7 (eq with different
    field subsets)

- **D6. `config_loader.rs` watch-item resolution uses crate's own type**
  (plan-settled). After migration, the three `config_loader.rs` call sites
  that currently do `PyModule::import(py, "temper_placer.core.net_graph")`
  (lines 1174, 1208) and `py_callable(py, "temper_placer.core.differential_pair", "DifferentialPairConstraint")`
  (line 2004) switch to `py.get_type::<SubNetEdge>()` /
  `py.get_type::<NetGraph>()` / `py.get_type::<DifferentialPairConstraint>()`
  — the same pattern that already resolved the `DesignRules` circles at
  `config_loader.rs:1968` and `loaders.rs:326`. This is a Rust→Rust call
  (no shim hop), not circular. The Python shim (`core/net_graph.py`,
  `core/differential_pair.py`) re-exports the pyclasses for Python consumers;
  Rust code uses the crate's own types. See the audit §3 "two wave-1
  DesignRules circles are already closed" precedent.

### Requirements

- **R1.** The migrated pyclasses must be behaviorally bit-exact with the
  pre-migration Python dataclasses — identical `repr()`, `==`, `!=`, hash
  unavailability (`TypeError`), constructor defaults, field types (int stays
  int, `float | None` preserves `None`-vs-`0.0`), mutable container identity,
  and `__post_init__` validation (message text + order) — as validated by the
  differential oracle (U1).

- **R2.** The behavioral A/B gate must pass: bit-identical `repr()` on
  randomized inputs, identical `==`/`!=` outcomes, identical `ValueError`
  messages for invalid differential-pair parameters, and identical container
  mutation behavior (U4).

- **R3.** The performance A/B gate must pass — "no regression beyond noise"
  (these are pure-delegation data contracts with no compute; the R2 carve-out
  for pure-delegation modules applies, with the CI noise floor stated in the
  PR body per Phase 0). The migration replaces dataclass construction with
  pyclass construction; both are Python-object operations with no algorithmic
  work (U4).

- **R4.** PBT: >=5 non-vacuous properties across the verification unit, each
  vacuity-guarded by a mutation test proving a degenerate implementation
  violates it. Every module must be reached by >=1 property (U4).

- **R5.** Metamorphic testing: >=3 invariant relations per module, honestly
  bounded (U4).

- **R6.** Induction proof: structural proof or explicit non-applicability
  note in `packages/temper-design-bundle/VERIFICATION.md` — these are data-
  only modules, so the structural-proof pattern from `priority.rs` /
  `design_rules.rs` applies (named base case with the smallest meaningful
  input, argument for per-field independence, no recursive or iterative
  computation) (U4).

- **R7.** Rust best-practices bar: no `unwrap` outside tests, `catch_unwind`
  at pyo3 boundaries, borrow over clone, iterators, doc comments on public
  items. The pyclass `#[new]` constructors and the `__repr__`/`__eq__`/
  `__hash__` methods are pyo3 boundaries and must be guarded (U4).

- **R8.** `DesignRules` container tightening: after both modules are migrated,
  `DesignRules.differential_pairs` holds `Py<DifferentialPairConstraint>`
  elements (the list stays `Py<PyList>`, identity-mutable); `DesignRules.net_topologies`
  holds `Py<NetGraph>` values keyed by net-name string (the dict stays
  `Py<PyDict>`). The container *types* are unchanged (already `Py<PyList>`/
  `Py<PyDict>`); this unit types the elements and reclassifies the two fields
  STILL-NEEDED → INTENTIONAL in the next audit. The audit §2.1 Wave C
  `Py<PyAny>` count drops by **2** (`differential_pairs`, `net_topologies`);
  `bus_cohorts` is explicitly out of scope (requires `BusCohortConstraint`
  migration, tracked separately) and does not count here (U5).

- **R9.** The two §3 watch-items must be resolved — `config_loader.rs` uses
  the crate's own type objects instead of `temper_placer.core.*` Python imports.
  The audit re-scan must confirm zero new circular call-backs (U5).

---

## Unit Breakdown with Gates

### U1. Differential Oracle + TDD Scaffolding

**Scope:** Write the differential test pinning the pre-migration implementation
**verbatim** as oracle, BEFORE any Rust code is written. This is the TDD red→green
gate (G1). The test file covers both modules (one verification unit per D5).

**Oracle blocks:**
- `_py_oracle_net_graph.py` — a verbatim copy of `net_graph.py`'s `SubNetEdge`
  and `NetGraph` classes (including `get_edge`/`get_outgoing_edges`/
  `get_incoming_edges`), carrying the "do not edit — they are the reference"
  comment.
- `_py_oracle_differential_pair.py` — verbatim `DifferentialPairConstraint`
  with `__post_init__`.

**Differential test file:**
`packages/temper-placer/tests/core/test_net_graph_and_diff_pair_rust_differential.py`

**Test coverage:**
- Construction with all field combinations (required-only, all-defaults,
  keyword-mixed, positional)
- `repr()` identity for every field type combination (`float | None` → `None`
  renders as `None`, not `'None'`; int `0` renders as `0`, not `0.0`)
- `==` / `!=` between identical and differing instances
- `hash()` raises `TypeError: unhashable type: 'SubNetEdge'` /
  `'NetGraph'` / `'DifferentialPairConstraint'`
- `NetGraph.edges.append(...)` mutates in-place and the getter returns the
  same object
- `NetGraph.star_nodes.add(...)` mutates in-place
- `NetGraph.get_edge()` / `get_outgoing_edges()` / `get_incoming_edges()` —
  linear scan, correct on empty, single-edge, duplicate source, duplicate sink
- `DifferentialPairConstraint` validation: each of the four error conditions
  produces the exact `ValueError` text, in the correct order (only first error
  raised)
- Default values: `edges=[]` per instance (not shared), `star_nodes=set()`
  per instance, `priority=0`, `max_skew_mm=0.5`, etc.

**Evidence that closes U1:**
- The differential test file exists and is committed.
- The oracle blocks are verbatim copies of the `origin/main` source files
  (git history shows the test file predates any Rust code).
- The test passes against the Python oracle (identity mode — oracle vs oracle,
  trivially green).

**Gate:** U2 must not begin until the differential test is committed and
passing (identity mode). The test file's first commit must predate the
first Rust commit (G1 TDD).

---

### U2. SubNetEdge + NetGraph Pyclass Implementation

**Scope:** Implement `SubNetEdge` and `NetGraph` as `#[pyclass]`es in a new
file `packages/temper-design-bundle/src/net_graph_contracts.rs`, following
the `netlist_contracts.rs` pattern:
- `#[pyclass(dict, module = "temper_design_bundle_python.net_graph_contracts")]`
- Every field is `Py<PyAny>` (D1)
- `#[new]` with `Option<&Bound<'_, PyAny>>` for each field, defaulting to the
  dataclass default where applicable
- `__repr__` via `repr_of` + `dataclass_repr`
- `__eq__` via `dataclass_eq`
- `__hash__` raises `unhashable("SubNetEdge")` / `unhashable("NetGraph")`
- `NetGraph.edges` getter returns `self.edges.clone_ref(py)` (identity-preserving)
- `NetGraph.star_nodes` getter same pattern (as `Py<PySet>`)
- `NetGraph.get_edge` / `get_outgoing_edges` / `get_incoming_edges` — Rust
  methods iterating the stored `PyList` and accessing `source_pin`/`sink_pin`
  via `py.getattr()`
- `register(module)` function registered in `lib.rs`

**Delegation shim:** `temper_placer/core/net_graph.py` becomes:
```python
from temper_design_bundle_python.net_graph_contracts import NetGraph, SubNetEdge
__all__ = ["NetGraph", "SubNetEdge"]
```

**Home crate placement:** `net_graph_contracts.rs` (new file), registered
alongside the existing contracts modules in `lib.rs` (after `board_contracts`
registration, before `config_loader`).

**Evidence that closes U2:**
- The differential test (U1) passes against the Rust implementation (green).
- `cargo test -p temper-design-bundle` passes.
- `make extensions && make extensions-check` reports 0 STALE.

---

### U3. DifferentialPairConstraint Pyclass Implementation

**Scope:** Implement `DifferentialPairConstraint` as a `#[pyclass]` in a new
file `packages/temper-design-bundle/src/differential_pair_contracts.rs`,
following the same pattern as U2, plus `__post_init__` validation in `#[new]`:
- Check `spacing_mm <= 0` → `ValueError("spacing_mm must be positive, got {v}")`
- Check `coupling_tolerance_mm < 0` → `ValueError("coupling_tolerance_mm must be non-negative, got {v}")`
- Check `max_skew_mm < 0` → `ValueError("max_skew_mm must be non-negative, got {v}")`
- Check `impedance_ohm is not None and impedance_ohm <= 0` →
  `ValueError("impedance_ohm must be positive if specified, got {v}")`
- The checks are in this exact order; the first failing check raises
- `impedance_ohm` None-check uses Python identity (`obj.is_none()`), not
  truthiness

**Delegation shim:** `temper_placer/core/differential_pair.py` becomes:
```python
from temper_design_bundle_python.differential_pair_contracts import DifferentialPairConstraint
__all__ = ["DifferentialPairConstraint"]
```

**Home crate placement:** `differential_pair_contracts.rs` (new file),
registered alongside U2's module in `lib.rs`.

**Evidence that closes U3:**
- The differential test passes (both U2 and U3 pyclasses green).
- `__post_init__` validation produces bit-exact `ValueError` text for all
  four error conditions.
- `cargo test -p temper-design-bundle` passes.

---

### U4. Full Gate Suite (Behavioral A/B, Performance A/B, PBT, Metamorphic, Induction)

**Scope:** Run the complete Wave-4 discipline gate set (G1–G8) on the combined
verification unit. This is the heaviest gate unit.

**Gate checklist:**

| Gate | Instrument | Pass criterion | Evidence location |
|---|---|---|---|
| **G1 TDD** | Differential test (U1) committed before Rust | Git history: test predates pyclass | `test_net_graph_and_diff_pair_rust_differential.py` first commit |
| **G2 Behavioral A/B** | U1 differential suite, green on CI | Bit-identical `repr()`, `==`, `ValueError` text on randomized + edge-case inputs | Same differential file, CI log |
| **G3 Performance A/B** | CI perf comparison workflow | No REGRESSION (pure-delegation carve-out: "no regression beyond noise") | PR perf-check comment |
| **G4 PBT** | `test_net_graph_diff_pair_pbt.py` | >=5 non-vacuous properties, every module reached >=1, each vacuity-guarded | PBT file |
| **G5 Metamorphic** | In PBT file or separate `_metamorphic.py` | >=3 invariant relations per module | PBT/metamorphic file |
| **G6 Induction proof** | `VERIFICATION.md` § "NetGraph + DifferentialPair — Verification" | Structural proof (base case + per-field independence) or explicit N/A note | VERIFICATION.md |
| **G7 Rust bar** | `cargo clippy`, `cargo test` | No `unwrap` outside tests, `catch_unwind` at pyo3 boundaries, borrow over clone | CI log |
| **G8 R24 physics** | N/A — data contracts, no physics | Explicit N/A recorded | VERIFICATION.md |

**PBT properties (minimum 7, covering both modules):**

| Property | Module | Description | Vacuity mutant |
|---|---|---|---|
| P1 | NetGraph | `get_edge` returns correct edge for matching source/sink | Always-return-None kernel |
| P2 | NetGraph | `get_outgoing_edges` returns all and only edges with matching source | Always-empty-list kernel |
| P3 | NetGraph | Mutable `edges` identity: after `append`, the list is longer and the getter returns the same object | Getter-returns-copy kernel |
| P4 | NetGraph | Mutable `star_nodes` identity: after `add`, the set contains the new element | Getter-returns-copy kernel |
| P5 | SubNetEdge | `repr` round-trip: all field types render correctly (`None`, `int`, `float`) | Float-always-rendered-as-int kernel |
| P6 | DifferentialPairConstraint | Validation order: `spacing_mm=0` raises before `max_skew_mm=-1` (order test) | Swapped-check-order kernel |
| P7 | DifferentialPairConstraint | `repr` with `impedance_ohm=None` renders `None`, not `0.0` or omitted | None-rendered-as-0.0 kernel |

**Metamorphic relations (minimum 3 per module):**

For `SubNetEdge`/`NetGraph`:
- MR1: **Field-permutation invariance** — swapping two edges in the `edges`
  list does not change `get_edge(source, sink)` result (list position
  independent of lookup)
- MR2: **Edge-addition monotonicity** — adding an edge never makes a
  previously-returned edge disappear (`get_edge` result stable under append)
- MR3: **Default identity** — default-constructed `SubNetEdge` (with only
  `source_pin`/`sink_pin`) equals another identically-constructed one

For `DifferentialPairConstraint`:
- MR4: **Field-subset equality** — two instances with identical fields
  compare equal regardless of construction order (positional vs keyword)
- MR5: **Spacing-monotonic error** — for any negative spacing `s1 < s2 < 0`,
  `DifferentialPairConstraint(..., spacing_mm=s1)` and
  `DifferentialPairConstraint(..., spacing_mm=s2)` both raise `ValueError`
  mentioning `spacing_mm`
- MR6: **Default preservation** — `DifferentialPairConstraint(net_pos='A',
  net_neg='B')` has `max_skew_mm=0.5` (the dataclass default), and the field
  renders in `repr()`

**Evidence that closes U4:**
- All eight gates pass. Results recorded in the gate table (this plan, updated
  in the implementation commit).
- The PBT anti-vacuity mutation tests each demonstrate that a degenerate kernel
  would be caught.

---

### U5. DesignRules Container Tightening + Config-Loader Resolution

**Scope:** After U2–U4 green, tighten the `DesignRules` containers and resolve
the `config_loader.rs` watch-items.

**DesignRules changes (`design_rules.rs`):**
- `differential_pairs: Py<PyList>` — the LIST type stays `Py<PyList>`
  (identity-mutable), but its elements are now guaranteed to be
  `DifferentialPairConstraint` pyclasses. The field docstring is updated to
  note the element type.
- `net_topologies: Py<PyDict>` — the DICT type stays `Py<PyDict>`, values are
  `NetGraph` pyclasses.
- The audit §2.1 Wave C STILL-NEEDED classification for these two containers
  is downgraded to INTENTIONAL (container identity-preserving; element types
  are now same-crate pyclasses, not opaque `Py<PyAny>`).

**Config-loader resolution (`config_loader.rs`):**
- Line 1174: `PyModule::import(py, "temper_placer.core.net_graph")` →
  `py.get_type::<NetGraph>()` for `NetGraph` construction, and
  `py.get_type::<SubNetEdge>()` for `SubNetEdge` construction at lines
  1179/1185/1208/1209/1214.
- Line 2004: `py_callable(py, "temper_placer.core.differential_pair", "DifferentialPairConstraint")`
  → `py.get_type::<DifferentialPairConstraint>()`.
- Both watch-items are recorded as RESOLVED in the audit re-scan.

**Evidence that closes U5:**
- `DesignRules` containers are typed (element types documented).
- `config_loader.rs` imports resolved; no `temper_placer.core.*` Python import
  for these types.
- `cargo test -p temper-design-bundle` passes.
- `make extensions && make extensions-check` reports 0 STALE.
- Audit re-scan (`grep` for net_graph/differential_pair in config_loader.rs)
  confirms zero remaining Python-module imports for these types.

---

### U6. Verdict — Wave C Complete

**Scope:** Confirm that the two modules are migrated, the delegation shims are
in place, the DesignRules containers are tightened, and the audit watch-items
are closed. Record the residual-verdict transition.

**What U6 confirms:**
1. `net_graph.py` (62 LOC) → MIGRATED as `net_graph_contracts.rs` +
   delegation shim
2. `differential_pair.py` (47 LOC) → MIGRATED as `differential_pair_contracts.rs`
   + delegation shim
3. `DesignRules`' two Wave C containers are no longer STILL-NEEDED (container
   identity stays `Py<PyList>`/`Py<PyDict>`; element types are now same-crate)
4. `config_loader.rs` watch-items (lines 1174, 1208, 2004) are RESOLVED
5. The audit's §3 watch-list shortens from 4 items to 2:
   - ~~`config_loader.rs:1174/1208` (core.net_graph)~~ **RESOLVED**
   - ~~`config_loader.rs:2004` (core.differential_pair)~~ **RESOLVED**
   - `config_loader.rs:1680` (pcl.constraints) — still pending
   - `config_loader.rs:1904` (_constraint_types) — still pending

**Evidence that closes U6:**
- Both delegation shims are in place and importable.
- The differential test passes (both modules).
- The full gate suite (U4) passed.
- `DesignRules` container docstrings updated.
- The commit message references this plan and the audit §2.1 Wave C.
- The `Ceiling-Approval:` trailer is not required (no board change).

---

## Risks + Mitigations

### R-A. Mutable container identity preservation (P1 risk — scrutinize hardest)

**Risk:** `NetGraph.edges` is a Python list that consumers mutate in-place
(`graph.edges.append(edge)` at `config_loader.rs:1199`). If the pyclass getter
returns a copy, the append silently disappears and the differential test
*will* catch it (the oracle does the same append and then reads back) — but
only if the test covers in-place mutation. The PBT property P3 specifically
tests identity: append through getter, read back through getter, assert the
element is present AND the list reference is the same Python object.

**Mitigation:** The established `clone_ref(py)` pattern from `netlist_contracts.rs`
is used for both `edges` (as `Py<PyList>`) and `star_nodes` (as `Py<PySet>`).
The default factory creates a fresh empty container per instance in `#[new]`,
preventing the shared-default footgun (where two default-constructed instances
share the same list).

### R-B. `__post_init__` ValueError message parity (medium risk)

**Risk:** The four validation checks in `DifferentialPairConstraint.__post_init__`
must produce bit-exact error messages including the `{self.spacing_mm}` f-string
interpolation. If CPython's `str(float)` and Rust's `format!("{v}")` disagree
on a trailing zero (`0.0` vs `0`), the message diverges.

**Mitigation:** The checks access `self.spacing_mm` etc. as `Py<PyAny>` objects
and call `obj.bind(py).str()?.to_string()` — CPython's own `str()` — to produce
the message body. This is the same technique `dataclass_repr` uses for
`repr()`: delegate to CPython rather than reimplement. The error messages are
pinned in the differential test (U1) with exact string assertions, so any
divergence is caught immediately.

### R-C. G4 cluster-vs-module unit decision (low risk)

**Risk:** A reviewer may challenge that two semantically distinct modules
(graph model vs constraint model) are one verification unit. The G4 cluster
rule permits this when they share one oracle and one corpus. If a reviewer
objects, plan B is to split into two units with 5 properties each — at a cost
of ~doubled test ceremony for modules that together are only 109 LOC.

**Mitigation:** The G4 conditions are satisfied: (1) every module is reached
by >=1 property (P1–P4 for net_graph, P5–P7 for differential_pair), (2) the
module-to-property map is stated in the PBT file's docstring, and (3)
reachability is measured per property (vacuous constants are caught by the
mutation companions). The cluster is justified in the plan (D5) and the PBT
file's header.

### R-D. Config-loader call-back after migration (low risk)

**Risk:** The audit §3 says "each migration converts a §3 watch-item into a
circular call-back." If `config_loader.rs` switches to `py.get_type::<NetGraph>()`,
this is Rust→Rust (same crate), not circular. If it accidentally keeps the
`PyModule::import` path and the delegation shim re-exports, that IS a
Rust→Python→Rust circle — but the plan explicitly switches to the crate's
own type (D6), following the already-proven `DesignRules` precedent.

**Mitigation:** The U5 evidence check explicitly greps `config_loader.rs` for
remaining `temper_placer.core.net_graph` / `temper_placer.core.differential_pair`
Python imports and fails the unit if any remain.

### R-E. `_constraint_types/config.py` type annotation compatibility (low risk)

**Risk:** `_constraint_types/config.py` is a pydantic model with
`net_topologies: list[NetGraph]`. After migration, `NetGraph` is a pyclass
from `temper_design_bundle_python`, re-exported by the `core/net_graph.py`
delegation shim. Pydantic's type resolver must see the same class. The
delegation shim `from temper_design_bundle_python.net_graph_contracts import NetGraph`
preserves the import path; `from temper_placer.core.net_graph import NetGraph`
still resolves to the same object.

**Mitigation:** Verify that `from temper_placer.core.net_graph import NetGraph`
returns the pyclass (the delegation shim's re-export) by importing it in the
differential test's conftest or a targeted unit test. If pydantic's
`typing.get_type_hints` resolves differently (unlikely — it follows the module's
`__dict__`), the delegation shim uses the standard import pattern.

---

## Sequencing + Worktree Plan

### Branch strategy

All work lands on one branch (`feat/wavec-core-contracts`), cut from
`origin/main`. Per the pipeline hard rule: create the branch in a clean
worktree off `origin/main`, never from a dirty checkout.

### Worktree isolation

```bash
git worktree add ../wt-wavec -b feat/wavec-core-contracts
cd ../wt-wavec
make venv-isolate  # isolated .venv, ~700 MB, immune to other sessions
source scripts/cargo_shared_env.sh  # shared CARGO_TARGET_DIR
```

### Unit sequencing

| Unit | Depends on | Estimated effort | Risk |
|---|---|---|---|
| **U1** (differential oracle + TDD) | None | 1–2 days | Low — test-only, no Rust |
| **U2** (SubNetEdge + NetGraph pyclass) | U1 green (identity mode) | 1–2 days | Medium — first new pyclass in this wave; establishes the pattern |
| **U3** (DifferentialPairConstraint pyclass) | U2 (shared helpers, register pattern) | 0.5–1 day | Low — simpler than U2 (no mutable containers, no methods) |
| **U4** (full gate suite) | U2 + U3 green | 2–3 days | Medium — PBT properties, metamorphic relations, induction proof |
| **U5** (DesignRules tightening + config-loader resolution) | U4 green | 0.5–1 day | Low — touch two fields, two import lines |
| **U6** (verdict) | U5 green | 0.5 day | Low — doc artifact |

**Total estimated effort:** 6–10 days.

**Parallelism:** U1 (differential test) is the only unit that can run before
any Rust code. U2 and U3 are sequential only because U3 depends on the helpers
and registration pattern established in U2 (though they could be parallel with
a shared scaffolding commit). U4 requires both pyclasses green. U5 requires U4.
U6 requires U5.

---

## Non-Goals

- **No BusCohortConstraint migration.** `DesignRules.bus_cohorts` is the
  third Wave C container and requires `BusCohortConstraint` migration; that
  module is not in this plan's scope. The `bus_cohorts` field stays
  `Py<PyList>` of `Py<PyAny>` until that migration.
- **No pcl.constraints migration.** `config_loader.rs:1680` (pcl.constraints
  watch-item) is outside this plan's scope.
- **No `_constraint_types` migration.** `config_loader.rs:1904` (pydantic
  `PlacementConstraints` watch-item) is outside this plan's scope.
- **No config_loader.rs rewrite beyond the three import sites.** The two
  `net_topology` / `kelvin_sensing` processing blocks (lines 1172–1248) and
  the `differential_pairs` construction loop (lines 2004–2026) keep their
  current logic; only the class-resolution mechanism changes (module import →
  crate type object).
- **No DesignRules repr/eq/hash change.** The `DesignRules` pyclass already
  delegates `__repr__`/`__eq__` to Python via its stored fields; changing
  the element type of `differential_pairs` from `Py<PyAny>` to a known pyclass
  does not change the delegation path.
- **No change to `core/__init__.py`'s `__all__`.** The re-exports keep the
  same names; no consumer sees a difference.
- **No change to `_constraint_types/config.py` beyond the import resolution**
  (which the delegation shim handles transparently).
- **No numpy, no math, no IO.** Both modules are pure-stdlib dataclasses;
  none of the B1–B8, B11–B13 divergence classes apply.

---

## Open Questions

- **E.1. Should `NetGraph.get_edge` / `get_outgoing_edges` / `get_incoming_edges`
  be Rust methods or delegate to Python iteration?** The plan assumes Rust
  methods (linear scan over the stored list, accessing `source_pin`/`sink_pin`
  via Python attribute access). This avoids the boundary crossing of calling
  Python list comprehensions, and the methods are O(n) with n typically ≤ 5
  edges per graph. If a reviewer prefers Python delegation for fidelity, the
  methods can call the equivalent Python list comprehensions through
  `py.eval()` or a helper — but this adds a Python boundary crossing for no
  correctness gain (the linear-scan logic is already identical to the oracle).
  **Deferred to implementation — the differential test catches any divergence
  either way.**

- **E.2. Are the `edges` and `star_nodes` fields typed as `Py<PyList>` /
  `Py<PySet>` from the start, or initially as `Py<PyAny>` and tightened
  later?** The plan types them directly as `Py<PyList>` / `Py<PySet>`. The
  dataclass annotations are `list[SubNetEdge]` and `set[str]` — the container
  types are known. If a consumer pushes a non-list/non-set object through
  the constructor, the pyo3 `extract` will raise `TypeError` with a message
  that differs from CPython's field-assignment error — but this is a
  contract violation (the annotation is `list`/`set`), and the differential
  test exercises only valid inputs. The same risk exists for every typed
  container in the existing pyclasses. **Plan-settled: typed from the start.**

- **E.3. Does the `repr_of` approach (calling CPython's `repr()`) have a
  performance impact vs `py_float_str`/`py_str_repr`?** Yes — one Python
  call per field per `repr()`. For these data contracts (constructed once
  per config load, not in hot loops), the overhead is negligible. The
  `netlist_contracts.rs` `Pin.__repr__` (12 fields × 1 `repr()` call each)
  already uses this pattern and the Phase-2 migrations' performance A/B
  passed. **Plan-settled: `repr_of` for both modules.**

- **E.4. Should the `config_loader.rs` net_topology/kelvin_sensing processing
  blocks also be tightened to use the typed container elements?** The blocks
  at lines 1172–1248 construct `NetGraph` and `SubNetEdge` instances and
  append them to a `PyList`. After migration, they construct the pyclasses
  directly via `py.get_type::<NetGraph>()` — the list itself is still
  `Py<PyList>` (identity-mutable), and the element types are naturally the
  pyclass constructors. No additional tightening is needed. **Plan-settled:
  the import resolution is the only change.**

---

## Sources

- Wave C context + audit: `docs/evidence/2026-08-06-pyany-surface-audit-2.md`
  §2.1 (DesignRules container classification), §3 (config_loader watch-items),
  §4 (Wave C removal plan)
- Wave-4 program plan: `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`
  (Phase 2 contracts-as-pyclasses, D5 pivot, R1–R8)
- Discipline contract: `docs/wave4-discipline-contract.md` §1 (G1–G8 gates),
  §2 (B1–B13 bit-exactness catalog), §3 (residual decision procedure)
- Migration pipeline: `docs/migration-pipeline.md` (stages 1–6, hard rules)
- Established pyclass pattern: `packages/temper-design-bundle/src/netlist_contracts.rs`
  (opaque storage, `repr_of`, `dataclass_repr`, `dataclass_eq`, `unhashable`,
  `list_or_new`, `clone_ref` identity preservation)
- Established pyclass pattern (simpler): `packages/temper-design-bundle/src/priority.rs`
  (module docstring conventions, `py_str_repr`/`py_float_str` helpers, B9/B10
  notes, `register()` convention)
- DesignRules container: `packages/temper-design-bundle/src/design_rules.rs`
  lines 326–358 (`DesignRules` struct with `differential_pairs: Py<PyList>`,
  `net_topologies: Py<PyDict>`)
- Config-loader watch-items: `packages/temper-design-bundle/src/config_loader.rs`
  lines 1172–1248 (net_graph construction), lines 1955–2026
  (constraints_to_design_rules with differential_pair construction)
- Source modules: `packages/temper-placer/src/temper_placer/core/net_graph.py`
  (62 LOC), `packages/temper-placer/src/temper_placer/core/differential_pair.py`
  (47 LOC)
- Consumers: `packages/temper-placer/src/temper_placer/_constraint_types/config.py`
  line 8 (NetGraph type annotation), `packages/temper-placer/src/temper_placer/core/__init__.py`
  lines 34/63 (re-exports), `packages/temper-placer/src/temper_placer/io/config_loader.py`
  lines 68–69 (imports for loading)
