# Validation DRC-check kernels — Verification

## PyAny-removal wave 2 (2026-08-06) — typed-handle tightenings

Record per plan R1e, as part of the Wave-4 PyAny-removal wave 2
(`docs/evidence/2026-08-06-pyany-surface-audit-2.md`, Wave A). Four stored
fields in `drc_contracts.rs` are tightened from opaque `Py<PyAny>` to typed
handles. Each wrapped value IS the same-crate pyclass on every verified
production construction path, so the tightening changes nothing observable:
the getter/setter/`__eq__`/`__repr__`/`to_dict` surfaces are unchanged, and
the differential suites stayed green unchanged. A non-pyclass payload that
was previously stored opaquely now raises `TypeError` — the pinned suites
never pass one.

| Struct | Field | Change | Evidence |
|---|---|---|---|
| `Issue` | `severity` | `Py<PyAny>` → `Py<Severity>` | Production (`drc_runner.py:225`, `drc_oracle.py:575`) and every differential corpus case pass the `Severity` pyclass members (`_SEVERITY_MAP[...]`, `_RS_SEV[...]`). |
| `Issue` | `location` | `Py<PyAny>` → `Option<Py<Location>>` | Production passes `_Location(...)` or `None`; differential cases resolve `$loc` → the `Location` pyclass or default `None`. |
| `Placement` | `via_placement` | `Py<PyAny>` → `Option<Py<ViaPlacement>>` | `_pipeline_verify.py:98` assigns `DRCViaPlacement(...)` (the pyclass re-export) after default construction; `from_dict` emits `None`. |
| `Placement` | `trace_placement` | `Py<PyAny>` → `Option<Py<TracePlacement>>` | `_pipeline_verify.py:124` assigns `DRCTracePlacement(...)`; `from_dict` emits `None`. |

The remaining 81 stored fields stay `Py<PyAny>` (INTENTIONAL int-vs-float
type preservation or STILL-NEEDED Python-built identity-mutable containers,
per the audit).

**Pins:** the differential suites
(`test_drc_contracts_rust_differential.py`, the #717/#761 consumer
differentials, the report differentials) pass unchanged, and three anti-
vacuity identity pins were added: `test_issue_severity_typed_identity_and_type`,
`test_issue_location_typed_none_and_identity`,
`test_placement_via_trace_typed_identity_and_none` (each asserts `is`
identity for the pyclass cases, `None` for the empty cases, and `TypeError`
for a non-pyclass payload).

---

The validation DRC-check slice (`src/validation.rs`) is the FIRST Wave 4
Phase 4 migration, porting the pure compute kernels of
`temper_placer/validation/` into `temper_drc_rs`. The Python modules
(`drc_oracle.py`, `geometric.py`, `drc.py`, `drc_runner.py`, `drc_fence.py`,
`trace_analyzer.py`, `tht_check.py`) are now delegation shims over these
kernels; the pre-migration implementations are pinned verbatim as the
differential oracles.

## Candidate scorecard (why this slice, what stays Python)

The Phase 4 verdict ledger (`docs/wave4-verdicts.yaml`) assigns the whole
`validation/` surface to Phase 4. This slice takes the seven modules whose
compute is pure and self-contained; the boundaries kept Python are all
argued in-source in the modules and below:

| Kernel | Python origin | Verdict |
|---|---|---|
| `infer_package_type` | `drc_oracle._infer_package_type` | migrated |
| `tht_hole_collisions` | `tht_check.validate_hole_clearance` (pairwise half) | migrated |
| `trace_length` / `min_hv_lv_trace_clearance` | `trace_analyzer` length / HV-LV kernels | migrated |
| `geometric_validate` | `geometric.GeometricValidator` decision logic | migrated |
| `parse_drc_violation` / `compute_drc_penalty` | `drc.KiCadDRCValidator` | migrated |
| `group_violations` | `drc_runner` / `drc_oracle._violations_to_run_result` | migrated |
| `issue_fingerprint` / `metrics_summary` | `drc_fence` | migrated |
| kicad-cli subprocess (`run_drc`) | `drc` / `_drc_api` | **stays Python** — I/O boundary, nothing to migrate |
| GEOS / `scipy.spatial.ConvexHull` (Qhull) | `geometric` zone predicate is already Rust (temper-geometry); `trace_analyzer.calculate_actual_loop_area` ConvexHull | **stays Python** — Qhull is not bit-reproducible outside scipy (the guide's "library semantics are not reimplementable", GEOS-buffer precedent) |
| `str(float)` no-format message formatting | messages built from Rust-returned numeric fields | **stays Python** — shortest-repr with `.0` suffix/exponent thresholds is a Python library semantic Rust `Display` does not reproduce (`10.0` vs `10`) |
| Phase-2 contract objects (`drc_types`, `drc_result`) | consumed by `drc.py`, `drc_runner.py`, `drc_fence.py` | **untouched** — Phase 2 CONTRACT surfaces, decided at their own pull |
| K1-schema dict builders (`_build_board_dict`, `_placement_to_board_dict`, `_constraints_to_dict`) | `drc_oracle` / `drc_runner` | **stays Python** — marshalling over Phase-2 contracts; `_build_board_dict`'s net ref lists come from a set comprehension whose iteration order is hash-randomized per process (the guide's "iteration order over sets" trap — sorting to stabilise would be a behaviour change no differential could catch) |
| `DRCFence.check` orchestration, `CheckRunner.run` glue | `drc_fence` / `drc_runner` | **stays Python** — wall-clock timing, logging, budget/failure raising |
| `_check_zones` | `geometric` | **stays Python** — the zone predicate (`point_in_zone`) is already Rust (temper-geometry); the remainder is Board contract lookup plus message building |

## Induction applicability

**Mathematical induction is not applicable to this module.** None of the
kernels is recursive, and none iterates over a dimension whose correctness
depends on a size parameter:

- `infer_package_type` is a fixed sequence of disjoint substring tests.
- `tht_hole_collisions` / `trace_length` / `min_hv_lv_trace_clearance` /
  `geometric_validate` / `compute_drc_penalty` / `metrics_summary` iterate
  over caller-provided collections, but each per-element operation is
  independent of the collection's size; `group_violations`' per-group loop
  is likewise size-independent, and its sorted-group order is a fixed
  lexicographic sort.
- `parse_drc_violation` is a fixed transcription of the kicad-cli JSON →
  record classification.

Per the plan's R1e, a **structural proof** is recorded instead (the
bit-exactness claim is verified by the differential suites and the mutation
campaign rather than by induction).

## Structural proof

**Claim (bit-identical parity).** For every kernel, the Rust behaviour is
bit-identical to the pinned pre-migration Python implementation for every
input in the differential suites' domains, with the documented deviations
below.

*Proof by structural cases.* Each kernel is a direct transcription of the
oracle body with the following load-bearing equivalences, each pinned by
measurement or by construction:

1. **Arithmetic equivalence.** CPython's `x ** y` on floats is libm `pow`
   — NOT repeated multiplication and NOT `sqrt`: measured 262/200000
   mismatches of `x*x` vs `x**2` and 274/200000 of `sqrt` vs `x**0.5` on
   this platform. Every `**2`/`**0.5` site (`trace_length`,
   `tht_hole_collisions`, the mounting-hole distance) calls
   `host_math::pow`, resolved via `dlsym` to the exact libm `pow` the host
   CPython calls (the `temper-thermal` hostmath B1 precedent).
   `f64::powf` was considered and rejected as a proxy: with a constant
   exponent LLVM folds the `llvm.pow.f64` intrinsic (`powf(2.0)` →
   `x*x`, `powf(0.5)` → `sqrt`; verified in this crate's release
   disassembly), both of which disagree with libm `pow`. `math.sqrt` is
   the correctly-rounded IEEE sqrt → `f64::sqrt` (measured 0/200000
   mismatches for the HV-LV kernel; `sqrt` is deliberately NOT routed
   through `dlsym` — IEEE-754 requires correct rounding, so the hardware
   instruction matches every conforming libm).
2. **Accumulation order.** `compute_drc_penalty`, `trace_length` and
   `metrics_summary`'s custom-metric accumulation preserve the oracle's
   in-order `+=` strategy — not CPython's Neumaier-compensated `sum()`
   (which disagrees at the last bit, e.g. `0x1.6666666666667p+4` vs
   `0x1.6666666666666p+4` for 4×0.1+1.0+1.0+20.0). Pinned by the
   differential; a PBT that used `sum()` as its "independent" arm was
   corrected to the `+=` strategy after the disagreement was measured.
3. **Fixed-point message formatting** (`:.2f`/`:.3f`/`.1f`) matches CPython
   bit-for-bit (measured 100k/100k on random values) — this is why
   `tht_hole_collisions` builds its `:.3f` messages Rust-side, while
   no-format `str(float)` messages are built Python-side from the numeric
   fields (see scorecard).
4. **Enum/severity semantics.** `parse_drc_violation` resolves the type
   against the verbatim `DRC_VIOLATION_TYPE_VALUES` catalog (pinned against
   the live `DRCViolationType` enum by
   `test_parse_differential_all_enum_members`); severity normalizes to
   `ERROR`/`WARNING` with the oracle's exact default and non-string →
   `None` paths. `group_violations` normalizes unknown severities to
   `ERROR` (the oracle's `_SEVERITY_MAP.get(..., ERROR)` fallback). The
   record does NOT carry `has_failure`: both delegation modules recompute it
   from the normalized severity (dead-output removal, pass 2 — the kernel
   emits only the single source, the wrapper re-derivation is pinned by
   `test_prop5_group_failure_flags`).
5. **Order semantics.** `group_violations` sorts group names with Rust's
   `String` sort (= CPython lexicographic str sort for UTF-8, byte order ==
   code-point order), preserving input order within each group;
   `issue_fingerprint` sorts the item segment identically.
   `metrics_summary` keeps first-seen key position with last-value-wins for
   `check_timings` (Python dict assignment semantics), implemented as an
   order-preserving `Vec<(String, Py<PyAny>)>` scan — not a `HashMap`. The
   raw Python objects pass through: the oracle assigns/accumulates the
   caller's values verbatim (`check_timings[name] = elapsed_ms`;
   `custom_metrics[key] += value`), so an `int` stays `int` (exact beyond
   2^53) and int+float `+=` promotes to `float` via Python `__add__`.
6. **Boundary edge math.** `geometric_validate` consumes the pairwise signed
   box distances, rotated AABB half-sizes and boundary-predicate outputs
   from the existing temper-geometry Rust kernels (single source of truth —
   both arms call the same primitives), and only re-implements the decision
   thresholds (`> overlap_threshold`, `> 5.0`/`> 1.0` severity ladder,
   `> 10.0` boundary severity, HV-LV pair detection, keepout
   intersection, `max(half_w, half_h) + keepout_radius`) verbatim.
7. **Empty-input semantics.** `min_hv_lv_trace_clearance` returns `+inf`
   for an empty HV or LV arm (the oracle's `float("inf")`);
   `compute_drc_penalty([])` returns `0.0`; `group_violations([])` returns
   `[]`; `metrics_summary([])` returns empty lists/dicts and zero counts;
   the empty-netlist geometric path raises the same `IndexError` in both
   arms (asserted by `test_empty_netlist_both_arms_raise`). `trace_length`
   skips None-net traces exactly as the oracle's `if trace.net ==
   net_name` (the Trace contract is `net: str | None`, and `None` never
   equals a str `net_name`) — pinned by
   `test_trace_length_none_net_trace_skipped` and the `None` entries in
   `test_differential_random_stress`.

## Documented deviations (per R1, recorded here)

- **`affected_items` typing in `group_violations`.** The oracle passes
  `affected_items` through opaquely; the kernel requires a list of strings
  and raises `PyValueError` otherwise. Realistic `temper_drc_rs.run_drc()`
  output is always a string list, and both arms raise on the pathological
  cases (the oracle fails later, in the `Issue` contract). Narrower and
  documented in `validation.rs`.
- **`group_violations` `check_name` key must be a string.** The oracle
  groups by `v.get('check_name', 'unknown')` — any hashable key works (an
  int key flows through into the str-typed `Issue`/`CheckResult` contract
  unenforced at runtime); the kernel's `get_str_or` raises `PyValueError`
  on a non-string key. **Chosen to RECORD rather than match**: faithful
  matching would require grouping by arbitrary hashable PyAny keys with
  Python-side `hash`/equality/`<` for the sorted group order — a change to
  the kernel's public marshalling contract (`Vec<(String, ...)>` → PyAny
  keys) for inputs that cannot arise from `temper_drc_rs.run_drc()`
  (`check_name` is always a string there). Pinned by
  `test_group_violations_non_string_check_name_narrowing`.
- **`parse_drc_violation` non-string `type`/`severity`.** Both arms return
  `None` (the oracle via `except Exception`), the kernel via an explicit
  extraction-failure path — same observable result.
- **`parse_drc_violation` `pos` — matched, not narrowed.** The value is
  read with `.get("x"/"y", 0)` (the oracle's `Mapping.get`) in both arms,
  so any truthy Mapping parses — plain dict, dict subclass, `UserDict`,
  `MappingProxyType` (pinned by
  `test_parse_differential_mapping_pos_and_dict_subclass_items`). A truthy
  non-Mapping `pos` fails closed in both arms (oracle `AttributeError` →
  `except Exception` → `None`; kernel extraction-failure → `None`).
- **`parse_drc_violation` `items` — no narrowing exists.** The review
  flagged dict-subclass entries as skipped by the kernel's
  `cast::<PyDict>`; that does not hold on this pyo3 (0.29): `cast` uses
  `PyDict_Check`, which is isinstance-based, so dict subclasses are
  accepted exactly like the oracle's `isinstance(affected, dict)`.
  Verified live and pinned by the same test above.
- **`compute_drc_penalty` non-float values.** The kernel raises
  `PyValueError`; the oracle raises `TypeError` at the `+=`. Both fail
  closed; realistic inputs are floats. (`metrics_summary` carried the same
  deviation before this review round; it now passes the caller's numeric
  values through raw and accumulates via Python `__add__`, so no narrowing
  remains there — pinned by
  `test_metrics_summary_int_values_type_preserved`.)
- **`infer_package_type(None)`.** The kernel's `Option<String>` handles
  `None` as the oracle's `footprint.lower() if footprint else ""` path —
  identical result (`"smd"`), pinned by the differential.

## Pass 2 (adversarial review) — dead-output removal, order pinning, fallback restoration

Structural findings from the adversarial review were resolved as follows
(recorded per field, as required by the review):

**Dead decision fields deleted from the kernels** — each was an
unobservable mutation region (a mutant flipping it passes every differential
and every documented sweep mutant, because no production consumer reads it).
Deleting removes the region entirely; the kernel contract stays minimal.

| Field | Kernel site | Why dead | Resolution |
|---|---|---|---|
| clearance finding `severity` | `geometric_validate` | `_wrap_clearances` re-derives it from `is_hv_lv`/`dist` | **deleted** (with the `(severity, code)` derivation) |
| clearance finding `code` | `geometric_validate` | `_wrap_clearances` re-derives `GEO_HV_LV_CLEARANCE`/`GEO_CLEARANCE` from `is_hv_lv` | **deleted** |
| keepout finding `severity` | `geometric_validate` | `_wrap_keepouts` hardcodes `ValidationSeverity.ERROR` | **deleted** (`code` kept — the wrapper reads it) |
| mounting-hole finding `severity` | `geometric_validate` | `_wrap_keepouts` hardcodes `ValidationSeverity.ERROR` | **deleted** (`code` kept — the wrapper reads it) |
| metrics `overlap_count` | `geometric_validate` | `_wrap_overlaps` recomputes it from findings | **deleted** |
| metrics `total_overlap_area` | `geometric_validate` | `_wrap_overlaps` recomputes it from findings | **deleted** |
| metrics `clearance_violations` | `geometric_validate` | `_wrap_clearances` recomputes it from findings | **deleted** |
| record `has_failure` | `group_violations`/`normalize_violation` | both `drc_oracle` and `drc_runner._violations_to_run_result` recompute it from normalized severity | **deleted**; the wrapper re-derivation pinned by the rewritten `test_prop5_group_failure_flags` (asserts `CheckResult.passed` through the shim AND asserts `has_failure` is not re-emitted) |

**Load-bearing fields kept** (consumers read them; already pinned by the
differentials and sweep mutants M6/M7): overlap finding `severity`/`code`,
boundary finding `severity`/`code`, metrics `boundary_violations`,
metrics `keepout_violations`.

**custom_metrics key order pinned by the differential.** The fence
differential previously compared `custom_metrics` order-insensitively
(`tuple(sorted(...))`) while `check_timings` was compared in insertion
order — so the kernel's first-seen-key-position contract (an
order-preserving `Vec` scan, not a `HashMap`) was pinned only by the single
hand-built `test_prop5_metrics_custom_accumulation`. The differential now
compares `custom_metrics` in insertion order too (mirroring
`check_timings`), so a HashMap-backed mutation fails the random
differential deterministically instead of passing it ~50% of the time.

**`drc_oracle._infer_package_type` Python fallback restored.** Pass 1 had
narrowed the module's graceful-degradation contract: `_infer_package_type`
called `_rs()` unconditionally, so the parsed-PCB dict-builder path
(`ci_closure_test.py`) broke at call time without the extension while the
module still advertised `_HAS_RUST_DRC=False` machinery. The verbatim
pre-migration pure-Python body (from `_drc_oracle_py_oracle.py`) is now
behind the `_HAS_RUST_DRC` guard; with the extension present the shim still
delegates to the kernel (the differential keeps pinning the Rust path). The
scorecard's "dict builders stay Python" claim is accurate again.

## Evidence

- Differential (R1a/R1f, TDD red→green): the RED commit
  `25fb09ae3` ("test(validation): Wave-4 Phase-4 TDD RED — oracles +
  differential/PBT suites") pins the pre-migration implementations verbatim
  (`_tht_check_py_oracle.py`, `_geometric_py_oracle.py`,
  `_drc_oracle_py_oracle.py`, `_drc_fence_py_oracle.py` at commit
  `aece7c372`, plus the migrated-function bodies of `trace_analyzer`,
  `drc` and `drc_runner` pinned inside their differential files). The
  differentials fail to collect until the `temper_drc_rs` kernels exist
  (module-level `= _tdrc.<symbol>` bindings), which is the demonstrated
  RED. GREEN: 94 differential/PBT tests pass (7 files).
- Properties (R1c): ≥5 non-vacuous properties per module (35 PBT — 5 each
  across the 7 modules), each asserting a concrete observable (severity
  classification, message format shape, sorted/partitioned grouping,
  failure flags, count/metric reconstruction, custom-metric accumulation,
  empty-input behaviour) — see the `test_*_rust_differential.py` suites.
- Metamorphic (R1d): ≥3 honestly-bounded relations per module (23 MRs
  total: 3+3+3+3+3+3+5) — e.g. overlap-threshold monotonicity, reflection
  invariance of geometric findings, permutation invariance of HV-LV
  clearance (min is associative, unlike a sum), penalty doubling with one
  weight dict scaled (bounded to known keys: defaults are not scaled),
  group-partition invariance under input permutation.
- Anti-vacuity mutation campaign (see
  `docs/evidence/2026-08-04-wave4-phase4-validation-mutation-sweep.md`):
  **12 mutants across all 10 kernels, every one caught by the
  differentials** (1–8 failures each). Mutants covered severity
  thresholds, boundary predicates, keyword catalogs, message formats,
  net filters, min→max, sort removal, join separators, category arms and
  weight defaults. No surviving mutants; no discriminating-case additions
  were required.
- Performance A/B (R1b): delegation shims with per-call marshalling; the
  no-regression-beyond-noise comparison in `scripts/pr_perf_compare.py`
  applies (pure-delegation surface — no speedup claim is manufactured; a
  measured warning from the phase guide: a Rust kernel behind a per-call
  marshalling boundary can be net-negative, and the DRC-check kernels are
  small relative to their marshalling).
- Rust practice (R1g): borrow over clone throughout; no `unwrap` outside
  tests; every `#[pyfunction]` boundary relies on pyo3's default
  `catch_unwind` (panics surface as `PanicException`, never as UB across
  the boundary).
- Physics gating (R1h): **not applicable** — the DRC-check slice is not a
  physics-gated surface (no CP-SAT constraint gates on a physics
  quantity), so the R24 discipline (Chebyshev-style soundness proof,
  BMC-exhaustive validation, post-solve audit) does not apply. State
  recorded explicitly because the ledger requires it.

---

# drc_types / drc_result contracts — Verification (Wave 4 Phase 2)

The Wave 4 Phase 2 contract slice (`src/drc_contracts.rs`) migrates the
CONTRACT TYPES of `temper_placer/validation/drc_types.py` and
`temper_placer/validation/drc_result.py` to pyo3 pyclasses. Both Python
modules are now pure-delegation re-exports of those pyclasses (the pattern
established by `core/board.py` and `core/netlist.py`), with the dataclass
protocol (`__dataclass_fields__` / `dataclasses.fields` /
`dataclasses.replace`) restored by `core/_contract_dataclass_compat`. The
pre-migration implementations are pinned VERBATIM as the oracles
(`tests/validation/_drc_types_py_oracle.py` /
`_drc_result_py_oracle.py`, commit `17553437d`). TDD-RED commit
`b7af1384b` (the differential fails to collect without the pyclasses — see
below); GREEN is this slice.

## Candidate scorecard (what is a contract vs what stays Python)

| Class | Python origin | Verdict |
|---|---|---|
| `ComponentPlacement`, `Placement`, `ClearanceRule`, `ZoneDefinition`, `LoopConstraint`, `ThermalConstraint`, `GroupConstraint`, `ConstraintSet`, `Via`, `ViaPlacement`, `TraceSegment`, `TracePlacement` | `drc_types.py` | migrated to pyclasses |
| `Severity`, `Location`, `Issue`, `CheckResult`, `RunResult` | `drc_result.py` | migrated to pyclasses |
| `Check` ABC, `CompositeCheck`, the 15 check stub classes (`ClearanceCheck`, `ComponentOverlapCheck`, …) | `drc_result.py` | **stays Python** — execution placeholders (delegating actual checking to the Rust engine), not data contracts; only their `CheckResult(...)` construction crosses to the pyclass |
| K1-schema dict builders (`_placement_to_board_dict`, `_constraints_to_dict`, `_build_board_dict`), fence/runner orchestration, CLI | `drc_runner.py` / `drc_oracle.py` / `drc_fence.py` | **stays Python** — marshalling over the contracts (already ruled Phase-4 surfaces) |

## Induction applicability

Not applicable — none of the classes is recursive or iterates over a
dimension whose correctness depends on a size parameter. A **structural
proof** is recorded instead (per the plan's R1e).

## Structural proof

**Claim (bit-identical parity).** For every construction/access pattern in
the differential suites' domains, the pyclasses reproduce the pinned
pre-migration dataclasses bit-identically, with the documented narrowing
below.

*Proof by structural cases.*

1. **Construction and field parity by construction.** Every field is
   stored as the exact Python object the caller passed (each struct field
   is an opaque `Py<PyAny>`), so the dataclass's *no-coercion* `__init__`
   is reproduced by construction: `Location(1, 2)` stores int coordinates
   and `.x` returns int `1`, never `1.0`. None-vs-empty follows the same
   rule (`opt_or` stores an explicit `None` verbatim; `list_or_new` /
   `dict_or_new` produce a fresh empty container for `default_factory`
   fields). Literal defaults (`net_class="Signal"`, `board_width=100.0`,
   `weight=1.0`, …) are injected only when the argument is omitted, so
   `Placement(board_width=None)` stores `None` exactly as the dataclass
   does. The one narrowing is recorded below.
2. **`__eq__`.** A generated dataclass `__eq__` returns `NotImplemented`
   unless `other.__class__ is self.__class__` (the `is` test, so a subclass
   instance compares unequal), then defers to tuple equality on the
   `compare=True` fields in declaration order. `dataclass_eq` reproduces
   both — including the `NotImplemented` return that makes `x == 1` raise
   `TypeError` — by delegating the field comparison to Python's own tuple
   `==`. `eq=True, frozen=False` dataclasses set `__hash__ = None`;
   `unhashable()` raises CPython's exact message
   (`TypeError: unhashable type: 'Location'`).
3. **`__repr__` / `__str__` byte-parity.** `__repr__` splices CPython's own
   `repr()` of each stored field into the generated layout
   `Cls(f1=r1, f2=r2, …)` (`dataclass_repr`). The custom `__str__`s
   (`Location.__str__` `"(x, y) on layer"`, `Issue.__str__`
   `"[code] message (items)"` with the 3-item truncation, `Severity`'s
   `<Severity.ERROR: 3>` / `Severity.ERROR`) route every formatting through
   Python's own `format()`/`str()` (the `py_float_fmt_2` / `str()`
   helpers), so fixed-point rounding and int-vs-float rendering agree
   bit-for-bit with the oracle.
4. **`Severity` surface.** pyo3 cannot subclass `enum.Enum`, so `Severity`
   is a pyclass whose four members are `#[classattr]` singletons
   (`Severity.INFO` …) reproducing the member surface the consumers use:
   `.name`, `.value` (int), `.weight` (the documented 0/1/10/100 table),
   `.is_failure` (exactly ERROR/CRITICAL), `repr` `<Severity.ERROR: 3>`,
   `str` `Severity.ERROR`, value+name equality, hashability, and
   value-based `__lt__`/`__le__` that return `NotImplemented` for a
   non-member (the oracle's `isinstance` guard — pinned by
   `test_severity_surface_identical`, including the `obj < 1` TypeError).
5. **Mutation vs frozen.** Every contract is a plain (non-frozen)
   dataclass: fields are `#[pyo3(get, set)]`, instances carry a `__dict__`
   (the `dict` pyclass flag), so attribute assignment/injection works and
   stores the raw object. `CheckResult.merge` returns a *new* object with
   fresh list/dict containers exactly as the dataclass's
   `self.issues + other.issues` / `{**a, **b}` do (later keys win,
   first-seen position kept — MR1 pins it).
6. **Computed properties are recomputed, not stored.** `info_count` …
   `critical_count`, `total_issues`, `penalty`, `RunResult.passed` /
   `all_issues` / counts / `total_penalty`, `bounds`, `center`,
   `distance_to`, `edge_distance_to`, `overlaps`, `overlap_area`, via
   `radius`, trace `length` / `bounding_box`, `by_category`,
   `by_severity`, `issues_for_component` each re-derive from the fields
   through Python's own operators (`PyAnyMethods::sub`/`div`/`pow`, the
   `math.sqrt`/`min`/`max` callbacks), so arithmetic — including int-widening
   in `bounds`'s `width / 2` and the `** 2` float-pow semantics in
   `TraceSegment.length` — is bit-exact by delegation.
7. **`RunResult.passed` fails closed** (the anti-vacuity rule): an empty
   run reports `False`, not Python's vacuously-True `all([])` — pinned by
   P2 and M3.
8. **`from_dict` / `to_dict` marshalling.** The dicts are reproduced with
   the oracle's `Mapping.get` semantics (so dict subclasses behave
   identically), the oracle's defaults, `tuple(bounds)` / `list(bounds)`
   conversions, `float()` for dict-form clearances, and the oracle's exact
   key sets — `ConstraintSet.to_dict` emits only
   clearances/zones/critical_loops/net_classes/voltage_domains/
   hv_clearance_mm/board (thermal/groups are NOT emitted, verbatim). The
   round-trips are pinned by P5 and `test_consumer_from_dict_to_dict_roundtrip_identical`.
9. **`from_yaml`.** Delegates to Python's own `yaml.safe_load(open(path))`
   then `from_dict`, so YAML parsing parity is inherited, not re-derived.
10. **Dataclass protocol restoration.** `_contract_dataclass_compat`
    installs genuine `__dataclass_fields__` / `__annotations__` / the
    public `__module__` on each pyclass, so `dataclasses.is_dataclass`,
    `dataclasses.fields` and `dataclasses.replace` behave as they did on
    the oracle (the FieldSpecs mirror the oracle field-for-field, including
    `default_factory=list/dict` and literal defaults).

## Documented narrowing (per R1)

- **Explicit `None` to a `default_factory` field.** pyo3's
  `Option<&Bound>` collapses "argument omitted" and "argument `None`" into
  one `None`; the literal-default fields resolve that with *signature
  defaults* (injected only when omitted, so `Placement(board_width=None)`
  stores `None` verbatim), but a `default_factory` field given an explicit
  `None` collapses to a fresh empty list/dict where the dataclass would
  store `None`. No consumer passes `None` to a factory field (audited:
  `drc_runner`/`drc_oracle`/`drc_fence` pass lists/dicts or omit the
  argument), and the narrowing is recorded here rather than silently
  matching.
- **No pickling guarantee.** The pyclasses do not implement
  `__reduce__`/`__getnewargs__`; pickling a contract object raises
  `PicklingError`. The pre-migration dataclasses were picklable. No
  production consumer pickles these objects (audited), and the differential
  does not pin pickle, so this is recorded rather than implemented (the
  Phase-2 core contracts' `__reduce__` was added because the board/netlist
  consumers genuinely pickle — not the case here). `copy.deepcopy` of a
  *field container* (a list/dict inside a pyclass) works as before; deep
  copy of a pyclass instance itself is not part of the pinned surface.
- **Enum class-level iteration.** pyo3 has no metaclass hook, so
  `list(Severity)` / `set(Severity)` (the Enum's `EnumType.__iter__`)
  cannot be wired. The pyclass exposes `Severity.members()` instead — the
  documented `gates.py` substitute for exactly this limitation — yielding
  the four members in definition order, pinned against the oracle's
  `list(Severity)` by `test_severity_surface_identical`. The one consumer
  (`tests/report/test_report_pbt.py`, which selected random severities via
  `rng.choice(list(Severity))`) was adapted to `Severity.members()`.

## Stub surface (mypy) — no `.pyi` added

No `.pyi` stub is added for the `temper_drc_rs` contracts, matching the
earlier `temper_drc_rs` kernel slices (validation/regression/req_safe) that
also added none. The extension is consumed through the typed Python shims
(`drc_types.py` / `drc_result.py`); under the repo's mypy config
(`ignore_missing_imports = true`, `disable_error_code = ["import-untyped"]`)
their re-export names resolve to `Any`, and no typed consumer calls
`dataclasses.replace` / `dataclasses.fields` on a contract pyclass — the
board/netlist stubs exist precisely because their consumers import
`temper_design_bundle_python` directly and call `replace()` on the
pyclasses (the `_contract_dataclass_compat` docstring's load-bearing case).
The type-check gate is unchanged by this slice, verified byte-for-byte
against origin/main under an identical environment (identical NEW/STALE
violation lists): `drc_result.py` stays at its allowlisted 1-error baseline
(the `TypeAlias` marker on the re-exports) and `drc_types.py` stays at 0.
Direct `temper_drc_rs` imports in `drc_runner` / `drc_fence` / `tht_check`
/ `geometric` / the regression modules keep their existing
`# type: ignore[import-untyped]` (the pre-slice pattern), unchanged.

## R1 status

- R1a: **bit-identical differential** — `test_drc_contracts_rust_differential.py`
  (52 tests): construction with identical kwargs (positional AND keyword),
  field round-trip with type-carrying canonicalization (`canon` tags every
  leaf with its concrete type and floats by `float.hex()`), repr/str
  byte-parity, the whole-corpus equality matrix (including `x == object()`
  → `False`), mutation semantics, `Severity` surface, `from_dict`/`to_dict`
  round-trips, and the #717/#761 consumer access patterns pinned directly
  (violations→RunResult, counts/penalty/fail-closed, to_dict+json,
  `__str__` surfaces, `metrics_summary` input reads, drc_runner
  marshalling reads, `ConstraintSet` lookup methods, geometry accessors).
- R1b: **no-regression arm not registered** — pure-delegation contract
  surface; the objects are constructed/marshalled per call behind a pyo3
  boundary and the slice makes no speedup claim (the #775 carve-out's
  "only register measurable compute" argument; the validation-slice
  precedent applies verbatim).
- R1c: **5 non-vacuous properties** (P1 severity weight table, P2
  fail-closed passed, P3 counts/penalty recomputed from severities, P4
  total_penalty is the severity-weighted sum, P5 from_dict↔to_dict
  leaf-preserving round-trip).
- R1d: **3 metamorphic relations** (MR1 merge order-preserving
  concatenation + ANDed passed + later-metrics-wins, MR2 permutation
  invariance of the aggregate counts/penalty, MR3 by_category partition +
  empty-check-in-every-group semantics).
- R1e: this file (structural proof; induction N/A).
- R1f: **TDD** — RED `b7af1384b` verified against a real build of the RED
  commit: the differential fails to collect with
  `AttributeError: module 'temper_drc_rs' has no attribute 'Severity'`
  (re-verified 2026-08-06 by building `lib.rs` at `b7af1384b` into the
  shared target dir and running the RED test against that module). GREEN is
  this slice.
- R1g: borrow over clone (fields are cloned `Py<PyAny>` handles — a borrow
  cannot be stored); no `unwrap`/`expect` outside tests (clippy
  `unwrap_used`/`expect_used` are denied in `Cargo.toml`); every
  `#[pymethods]` boundary relies on pyo3's default `catch_unwind` (panics
  surface as `pyo3_runtime.PanicException`, never as UB across the
  boundary).
- R1h: **not physics-gated** — the contracts are pure data objects with
  geometry helpers; no CP-SAT constraint gates on a physics quantity, so
  the R24 discipline (soundness proof, BMC-exhaustive validation,
  post-solve audit) does not apply. Stated explicitly because the ledger
  requires it.

## Consumer-semantics audit (the #717/#761 construction sites)

Every production construction site is enumerated and stays working through
the delegation shims (all pinned by the #717/#761 suites, which drive the
objects end-to-end and stayed green unchanged):

- `drc_oracle.DRCOracle._violations_to_run_result` — builds
  `Location`/`Issue`/`CheckResult`/`RunResult` by keyword, compares
  `severity in (Severity.ERROR, Severity.CRITICAL)`, reads
  `v["affected_items"]`/`v["details"]` verbatim.
- `drc_runner._violations_to_run_result` — identical construction pattern.
- `drc_fence` — reads `.check_results`/`.passed`/`.issues`, `Severity.*.weight`,
  feeds `issue_fingerprint(issue.code, issue.message, list(issue.affected_items))`
  and `metrics_summary(...)` (the Rust kernel reads `c.elapsed_ms`,
  `i.category`, `c.metrics` back off the pyclass objects).
- `drc_runner._placement_to_board_dict` / `_constraints_to_dict`,
  `drc_oracle._build_board_dict` — read `comp.layer/x/y/rotation/width/…`,
  `zone.bounds`, rule fields off the drc_types pyclasses.
- `drc_cli` — `Placement.from_yaml` / `ConstraintSet.from_yaml` (the
  kicad-cli path), `result.passed`.
- `Check`/`CompositeCheck`/the 15 stub classes — construct
  `CheckResult(check_name=…, passed=True)` and call `.merge(...)`.

## Mutation campaign (anti-vacuity)

**11 mutants, all caught, no survivors** — see
`docs/evidence/2026-08-06-wave4-phase2-drc-contracts-mutation-sweep.md`:
severity weight table, INFO-vs-ERROR count, fail-open `passed`, merge
later-wins, repr field omission, `__str__` truncation index, bounds sign
flip, clearance rule matching disabled, `from_dict` default, doubled
penalty, and the mid-sweep `Severity.members()` order swap (M11) — the
class-level-enumeration surface added for the report formatter's severity
enumeration, pinned directly against the oracle's `list(Severity)`.
Pristine rebuild after the sweep: 52/52 green.

---

# REQ-SAFE-01 clearance validator — Verification (Phase 5)

The `requirements/validators/{clearance,_copper}.py` compute
(`src/req_safe_01.rs`) is the Phase 5 migration into this crate. The
Python modules are delegation shims; the pre-migration implementations are
pinned verbatim as the differential oracle package
(`tests/requirements/clearance_oracle/`). TDD-RED commit: `ba3d857dd`
(fails to collect until `temper_drc_rs.req_safe_01_*` exists); GREEN: 25
differential+PBT tests, full requirements suite 475 passed.

## Scorecard

| Kernel | Python origin | Verdict |
|---|---|---|
| nets-domain map, domain pairing (same-domain + raw-ref pair-skip), intra-footprint boundary components | `clearance.py` | migrated |
| copper model: pad parsing, reach, memoized `copper_distance`, domain restriction | `_copper.py` | migrated — **the `temper-geometry` kernels stay the authority**: `tg_rotate` / `tg_origin_distance` / `tg_component_reach` / `tg_copper_scan` are called back across the boundary, exactly as the Wave-3 `_copper` facade calls them (both differential arms run the same kernels — the Rust memoizes the results) |
| check core with pruning/origin/unrestricted counters + WARNING records | `clearance.py` | migrated (records computed in Rust, emitted by the shim through the logging framework) |
| `verify_iec60335_compliance` 6-row matrix walk over a shared model | `clearance.py` | migrated |
| `format_clearance_report` worst-first table | `clearance.py` | migrated |
| string-keyed requirement matrix | `clearance.py` | migrated; the `IEC60335_REQUIREMENTS` tuple-keyed data stays Python |
| enums/dataclasses (`VoltageDomain`, `ClearanceViolation`, `ClearanceResult`), `str`-mixin Enum identity | `clearance.py` | stays Python — construction and identity are Python runtime semantics |
| `_copper` facade attribute surface (`_Pad`/`_component_pads`/`_CopperModel`) | `_copper.py` | stays Python — the Wave-3-pinned facade, populated from Rust payloads; distance methods call the temper-geometry kernels directly |

## Induction applicability

Not applicable — structural proof recorded instead (per R1e): every kernel
is a fixed transcription over caller-provided collections (pair loops,
memoized pairwise lookup, a fixed 6-row matrix, a worst-first sort) with
no size-parameterized invariant.

## Structural proof

**Claim (bit-identical parity).** The Rust behaviour is bit-identical to
the pinned oracle for every input in the differential suites' domains,
with the Python-side seams in the scorecard.

1. **Pairing.** `domain_boundary_pairs_vec` reproduces the oracle's
   semantics exactly: same-domain mode pairs every unique unordered pair;
   cross-domain mode pairs every `(a, b)` except raw-`.get("ref")`
   equality (two missing refs skip, `None == None`, exactly like Python).
   M9 (same-domain pairing killed) was caught by the differential.
2. **Memoized copper distance.** `copper_distance` caches by the
   `(ref_a, domain_a, ref_b, domain_b)` key and returns the cached
   payload — the memoization preserves bit-exactness because the cached
   value is the identical computed value (M10, a `+1e-9` bias on the
   computed distance, was caught by the `measured_mm` bit pins).
3. **Counters.** `pairs_checked == pairs_inter + pairs_intra` and the
   pruned/origin/unrestricted breakdowns are pinned both by the PBT
   (invariant property) and by the differential stats comparisons.
4. **WARNING records.** The origin-modelled WARNING message text is
   computed in Rust and emitted by the shim; the differential compares the
   full record sequences (M13, a dropped clause, was caught).
5. **Matrix walk.** `verify_iec60335_compliance` walks the 6 fixed
   `(domain_a, domain_b, insulation, min_clearance, min_creepage, design)`
   rows twice (clearance + creepage) over one shared `CopperModel`,
   producing 12 stat rows tagged with the insulation class — pinned by the
   PBT (`len(rows) == 12`, both metrics, all three insulation classes) and
   by the differential. M12 (halved `min_clr`, violations silently
   forgiven) was caught.
6. **Worst-first report.** `format_clearance_report` sorts by
   `(-shortfall, ref_a)` — the PBT and differential pin the worst-first
   header, the sorted table, and the closest-pads tail (M11, ascending
   sort, was caught).
7. **Temper-geometry authority.** Both differential arms route every
   distance through the same `temper_geometry` kernels; the Rust adds only
   memoization and record shaping, so geometry parity is inherited from
   the kernels rather than re-derived.

## R1 status

- R1a: bit-identical differential (16 tests; floats via `float.hex()`;
  WARNING-record sequences compared element-wise).
- R1b: not registered — per-call marshalling surface, same argument as the
  validation slice above; no speedup claim.
- R1c/R1d: 9 PBT properties (violation fields, actual-gap value,
  creepage==clearance on unbroken board, passed==(violations empty),
  counter invariants, pruning, matrix rows, worst-first report,
  intra-pair shape) + 4 MRs (far-pair pruning relation, passed↔violations,
  unbroken-board creepage==clearance, intra-pair `ref_a == ref_b`).
- R1e: this file (structural proof; induction N/A).
- R1f: TDD — RED `ba3d857dd`, GREEN in `3ddf6fd14` (rebased).
- R1g: `catch_unwind` at every `#[pyfunction]`; no `unwrap` outside tests;
  the 3 `expect`s are guarded by immediately-preceding branch construction
  (see the io-types VERIFICATION.md for the full list).
- R1h: **not physics-gated** — `clearance.py`/`_copper.py` reference no
  physics module (verified against the oracle pins) and the
  physics-soundness register's scan set covers only `placer/cp_sat/*` and
  `router_v6/constraint_model.py`; the register gate exits 0.

## Mutation campaign

13 mutants ran across both Phase-5 home crates (see
`docs/evidence/2026-08-05-wave4-phase5-mutation-sweep.md`); M9–M13 target
this crate and were all caught by the clearance differential/PBT suites.


## Phase 4 — the validation-remainder RDL kernel (`rdl_sum`)

Wave-4 Phase-4 moved the ONE in-module numeric compute of
`temper_placer/validation/human_reference_extractor.py`'s
`_compute_routing_metrics` here: the routed-length loop
`rdl += math.hypot(end.x - start.x, end.y - start.y)` in segment order.
Home-crate decision: temper-drc-rs, because the kernel is a trace-kernel —
the same family as this crate's already-landed `trace_length` — and the
crate already owns the hostmath machinery.

**The `math.hypot` boundary — why it is a callback, not a dlsym.**
The first transcription dlsym'd the system libm `hypot` (the B1 hostmath
precedent that works for `pow`). It diverges from CPython's `math.hypot`
by 1 ulp on non-correctly-rounded inputs: `math.hypot(0.1, 0.1)` is
`0x1.21a1851ff630ap-3` while libm `hypot` (and `sqrt(x*x + y*y)`, and
`sqrt(fma(...))`, all verified by C probe) is `…b-3`. CPython 3.12 inlines
its own fdlibm-style hypot into `mathmodule.c` (bpo-33083), so no dlsym
target reproduces it. `rdl_sum` therefore takes `math.hypot` as a
per-segment callback: the host runtime's own function, so bit-parity holds
by construction, while the in-order `+=` accumulation stays Rust. The
delegation module and the differential pass `math.hypot` explicitly. The
1-ulp divergence was caught by the differential on first run and is
recorded in `docs/evidence/2026-08-05-wave4-phase4-validation-remainder-
mutation-sweep.md`; the M11 mutant (manhattan substitute) is caught.

R1 coverage (shared with the design-bundle Phase-4 section): R1a via
`test_human_reference_extractor_rust_differential.py` (floats via
`.hex()`); R1c 5 properties (non-negativity, per-segment lower bound,
single-segment = hypot, zero-length invariance, empty = 0.0); R1d 3 MRs
(scaling homogeneity, negation identity, midpoint splitting); R1f RED
commit `28d712e75` (the file fails to collect without `temper_drc_rs.
rdl_sum`); R1g no `unwrap`/`expect` outside tests, pyo3 `catch_unwind`
default; R1b no-regression arm not registered — a per-segment callback
loop is marshalling-bound and the slice makes no speedup claim (recorded
reason); R1h **not applicable** (no physics-gated quantity).
---

# Regression-slice kernels — Verification (Wave 4 Phase 4)

The regression slice ported the portable compute of seven
`temper_placer/regression/` modules. Three land in this crate (drc_ratchet,
closure_test, physics_oracle — validation-adjacent, the #717/#761 precedent
of hosting validation kernels here); four land in `temper-design-bundle`
(cp_sat_comparison, measure_closure, fingerprint, schema_validator — compute
plus the netlist/board contracts that live there). The pre-migration modules
are pinned verbatim as the differential oracles
(`packages/temper-placer/tests/regression/_*_py_oracle.py`, commit
`0a29f15e3`). TDD-RED commit `de1f6ac9d` (the differentials fail to collect
until the kernels exist); GREEN `dc603230b`.

## Candidate scorecard — home-crate decisions

| Kernel | Python origin | Home crate | Verdict |
|---|---|---|---|
| `ratchet_check` / `detect_ceiling_raise` | `drc_ratchet.py` | temper-drc-rs | migrated |
| `closure_validate` / `closure_summary` | `closure_test.py` | temper-drc-rs | migrated |
| `compute_oracle_margins` / `overall_score` / `clearance_passed` | `physics_oracle.py` | temper-drc-rs | migrated |
| `compare_metric_dicts` | `cp_sat_comparison.py` | temper-design-bundle | migrated |
| `compute_drc_clearance_pass_pct` | `measure_closure.py` | temper-design-bundle | migrated |
| `input_fingerprint` / `source_fingerprint` / `should_skip` | `fingerprint.py` | temper-design-bundle | migrated |
| `validate_schema` | `schema_validator.py` | temper-design-bundle | migrated |
| DRC backends (kicad-cli subprocess, board-dict build), ceiling JSON I/O | `drc_ratchet.py` | — | **stays Python** — I/O/marshalling; the #575 ratchet constants stay where they are |
| `ClosureTest.run()` orchestration, sidecar writer, routing-failure extraction | `closure_test.py` | — | **stays Python** — consumes pipeline/router surfaces outside this slice |
| physics metric functions (`thermal_score`, `dual_rail_clearance_report`, `zone_compliance_score`, `loop_area_score`, `compactness_score`, `derive_constraints_from_spec`, parser, `infer_quality_config`) | `physics_oracle.py` | — | **stays Python** — other surfaces, called back across the boundary unchanged |
| fingerprint file I/O / cache JSON, schema YAML loading, measure_closure payload assembly | fingerprint / schema_validator / measure_closure | — | **stays Python** — I/O + marshalling; messages type-carry int-vs-float via Python `str()` |

The six harness modules (runner, reporter, corpus_runner, metrics_recorder,
cli, manifest) are JUSTIFIED-KEEP with a D6 harness-independence blocker
(recorded in `docs/wave4-verdicts.yaml`); they are NOT migrated and were not
modified beyond what the shims require.

## drc_ratchet

### Induction applicability
Not applicable — no recursion; every loop iterates over caller-provided
collections with size-independent per-element operations. A **structural
proof** is recorded instead.

### Structural proof
**Claim (bit-identical parity).** For every input in the differential
suite's domain, `ratchet_check`/`detect_ceiling_raise` reproduce the pinned
pre-migration `_check_board` comparison + message composition and
`detect_ceiling_raise` bit-for-bit.

*Proof by structural cases:*

1. **Comparison semantics.** The per-type category loop sorts the current
   rules (`sorted(current_by_type.items())`), looks up the allowed count with
   a 0 default (implicit-zero ceiling), flags `is_new` for rules absent from
   the allowed record, and fires only when the allowed record is non-empty
   AND the backend supplied a breakdown (the oracle's `and` guard — an empty
   record suppresses the per-type dimension entirely). `count > allowed` is
   strict (the boundary pinned by M2).
2. **Aggregate deltas.** `error_delta = current - ceiling`, failing when
   `> 0`, with `aggregate_*_delta = max(delta, 0)`.
3. **Message composition.** All interpolations are int/str/bool (no-format
   `str(float)` never appears in this module), so `format!` matches CPython
   f-strings bit-for-bit. The failing-run message keeps the version note's
   two-space indent verbatim; the passing run `.strip()`s it (Python
   `str.strip` == Rust `str::trim` for the ASCII note). The category block
   renders `new_failures + regressed_failures` (NEW first), matching the
   oracle's list concatenation, and reports `source` once per block.
   `violation_deltas` and `category_failures` are in the oracle's order
   (errors loop then warnings loop, each sorted).
4. **Raise detection.** Iterates the new boards in JSON order, skips boards
   absent from the old record, and accumulates reasons in the oracle's
   order (aggregates, then sorted `violations_by_type`, then sorted
   `warnings_by_type`), including a rule absent from the old record (a raise
   from its implicit 0). Requires `"Ceiling-Approval:"` in the commit
   message; returns `exit_code=2` on an unapproved raise, `None` otherwise.

### Documented deviations
- **Float-valued ceilings/counts fail LOUDLY at the shim marshal boundary
  (pass 2, P1-1).** Pass 1 recorded the delegation shim's `int()` coercion
  in `detect_ceiling_raise`'s Python-side `_marshal` as a truncation to
  match the kernel's `i64` marshal, with the same coercion at the
  `ratchet_check` boundary. The adversarial review demonstrated this fails
  the #575 approval gate OPEN: a float-valued ceiling raise (`100 ->
  100.5`) marshals to `100 -> 100` (truncated), so the kernel sees no raise,
  the shim returns None, and the gate PASSES where it must block merge --
  the oracle's raw compare would report `exit_code=2`. Fixed by validating
  int-ness at the marshal boundary: any value that is not a genuine `int`
  (bool excluded) raises `CeilingMarshalError` (a `ValueError` subclass,
  `temper_placer/regression/drc_ratchet.py`) naming the field, board and
  value BEFORE the kernel runs. This is a documented deviation FROM the
  oracle's raw compare but SAFER: fail-loud where the old shim silently
  passed. The i64 kernel boundary is unchanged (no f64 message-rendering
  churn). The oracle keeps its raw-compare behavior; the differential pins
  BOTH arms' loud behavior (`test_differential_float_ceiling_fails_loudly`,
  `test_differential_float_per_type_count_fails_loudly`). Pinned int-valued
  inputs are unaffected (the real `drc_ceiling.json` is all ints).

### Pass 2 (adversarial review) — fail-loud marshal, graceful degradation, marshalling-scope disclosure

**Fail-loudly float marshal (P1-1).** See the deviation record above. The
gate's entire purpose is fail-closed on any raise; pass 1's int-only
"record, don't change" response was the wrong response for a safety gate,
because the truncation is exactly the failure mode the gate exists to
prevent. Resolved by validating int-ness at the shim marshal boundary.

**Kernel-missing graceful degradation restored (P1-2b).** During the
migration the `ratchet_check` kernel call moved OUTSIDE `_check_board`'s
`try/except`, so a missing `temper_drc_rs` raised an unhandled
`ImportError: No module named 'temper_drc_rs'` traceback on the
kicad-cli backend (the `ci_check_drc.py --backend kicad-cli` /
`ci_closure_test.py` crash class) instead of the pre-migration clean
`DRC (rust) failed` FAIL. The kernel call is back inside the `try/except`
(pinned by `test_missing_kernel_fails_cleanly_not_traceback`). CI now also
builds `temper-drc-rs` explicitly in every workflow that consumes it
(regression.yml, metrics-record.yml, pr-pipeline-scorecard.yml -- see the
workflow changes in the same PR), so the missing-extension state is a
defensive path, not a normal one.

**Mutation-sweep scope (kernel-only) disclosed (P2).** The anti-vacuity
sweep (45 mutants) mutated ONLY the Rust kernels. The Python-side shim
marshalling layer (`_marshal`, the `int()` coercion boundary, the
cache-entry lookup, the import/lazy-load boundaries) was NOT
mutant-tested -- and the P1-1 finding is the concrete proof of why that
matters: a kernel-only sweep cannot see a fail-open in the marshalling
boundary. Since this review round, the marshal validates int-ness and the
`should_skip` kernel handles the null/non-dict entry class (see
temper-design-bundle's VERIFICATION.md), closing the demonstrated classes.

### R1 status
- R1a: bit-exact differential `test_drc_ratchet_rust_differential.py` —
  full `DrcRatchetResult` (incl. message strings) vs the oracle, both
  backends, deterministic + 120-case randomized stress; pass 2 added the
  fail-loud float-marshal cases, the exact `'; '`-separator pin, and the
  kernel-missing graceful-degradation pin.
- R1b: no-regression arm **not registered** — the ratchet comparison runs
  once per gate invocation behind a per-call marshalling boundary; the slice
  makes no speedup claim (the recorded reason, per the #775 precedent's
  "only register measurable compute" carve-out).
- R1c: 9 non-vacuous properties.
- R1d: 4 honestly-bounded metamorphic relations.
- R1e: structural proof above (no recursion; induction N/A).
- R1f: RED `de1f6ac9d` (fails to collect without `ratchet_check`/
  `detect_ceiling_raise`), GREEN `dc603230b`.
- R1g: no `unwrap`/`expect` outside tests; pyo3 `catch_unwind` default at
  every `#[pyfunction]` boundary.
- R1h: **not applicable** — the ratchet enforces committed ceilings; no
  CP-SAT constraint gates on a physics quantity.

## closure_test

### Induction applicability
The `closure_summary` loop is a fixed-order line accumulation (structural,
no induction). `closure_validate` is a conjunction of four independent
predicates — no recursion and no size-parameterized correctness claim, so
a **structural proof** is recorded (induction N/A).

### Structural proof
**Claim.** `closure_validate` emits exactly the oracle's failure messages in
the oracle's order, and `closure_summary` renders the report string
byte-identically.

*Proof by structural cases:*
1. Each predicate maps one-for-one from `ClosureResult.validate`'s `if`
   chain, in order, with the exact message text; the conjunctive
   zero-results line is present iff both placement and routing produced
   nothing.
2. `closure_summary` joins the fixed header block (with `:.1f` formatting
   for the completion pct and wall clock — measured CPython-parity,
   round-half-even) then appends the error/warning lines in list order.
   `:.1f` renders `94.25` → `94.2` and `123.456` → `123.5` identically in
   both arms (pinned by the differential).

### R1 status
- R1a: `test_closure_test_rust_differential.py` (300 randomized + edge
  cases).
- R1b: not registered (harness report rendering; no speedup claim).
- R1c: 7 non-vacuous properties. R1d: 3 MRs. R1e: structural proof above.
- R1f: RED `de1f6ac9d`, GREEN `dc603230b`. R1g: no `unwrap`/`expect`
  outside tests; pyo3 `catch_unwind` default.
- R1h: **not applicable** (no physics-gated quantity).

## physics_oracle

### R1h — the physics-gating question (recorded explicitly per the ledger)
**This is an ORACLE/comparison kernel, not a physics gate.** The module
scores a CP-SAT placement against physics metrics (thermal, clearance,
dual-rail) to produce a pass/fail *observation*; it does not constrain any
solve, and no CP-SAT constraint gates on a physics quantity here. The R24
discipline (Chebyshev-style soundness proof, BMC-exhaustive validation,
post-solve audit) therefore does **not** apply; the kernels are pinned
against the oracle by the differential instead.

### Induction applicability
Not applicable — no recursion; the margin math is three independent
multiplications and `overall_score` is a fixed accumulation over
caller-provided scores. **Structural proof** recorded.

### Structural proof
**Claim.** `compute_oracle_margins`, `overall_score` and `clearance_passed`
reproduce the pinned oracle bit-for-bit.

*Proof by structural cases:*
1. **Margins.** Each margin is one IEEE-754 multiply of the score (with the
   oracle's `dict.get(key, 1.0)` missing-key default, preserved in-kernel)
   by the caller's engineering-unit parameter — identical to the oracle's
   expression. `clearance_margin_mm = (score - 1.0) * threshold` is signed
   headroom (negative below 1.0).
2. **Overall score.** CPython 3.12's builtin `sum()` uses Neumaier-
   compensated summation for floats (measured on this platform: a plain
   `+=` accumulation diverges from `sum()` on 4640/20000 random inputs and
   `sum([1e16, 1.0, -1e16])` is 1.0, not 0.0). The kernel transcribes that
   loop exactly (`t = s + x`; `c += (s - t) + x` when `|s| >= |x|`, else
   `c += (x - t) + s`; `s = t`; result `s + c`), then divides by the count —
   the oracle's `sum(...) / len(...)`. Empty input → `0.0` (the oracle's
   `else 0.0` branch). The M3 mutant (plain accumulation) is caught by the
   differential.
3. **Pass decision.** `clearance_passed` is `clearance >= threshold` — the
   oracle's `passed = clearance >= _CLEARANCE_PASS_THRESHOLD` (threshold
   default 0.95 stays in the delegation module).
4. **Cross-boundary call-backs.** `score_placement`, `run_physics_oracle`
   and `score_human_baseline` keep calling the metric functions
   (`thermal_score`, `dual_rail_clearance_report`, `zone_compliance_score`,
   `loop_area_score`, `compactness_score`) and the spec/parse/derivation
   pipeline across the boundary unchanged — only the three pure kernels
   moved.

### R1 status
- R1a: `test_physics_oracle_rust_differential.py` (margins 400 randomized,
   overall 400 randomized + the Neumaier boundary case, clearance_passed
   boundary sweep).
- R1b: not registered (score aggregation behind a marshalling boundary; no
   speedup claim).
- R1c: 7 non-vacuous properties. R1d: 4 MRs. R1e: structural proof above.
- R1f: RED `de1f6ac9d`, GREEN `dc603230b`. R1g: no `unwrap`/`expect`
   outside tests; pyo3 `catch_unwind` default.
- R1h: stated above — not a physics gate.

## Mutation campaign

See `docs/evidence/2026-08-05-wave4-phase4-regression-mutation-sweep.md`
for the full per-mutant record: **45 mutants across all seven kernels, every
one caught by the differentials** (no surviving mutants, no infra failures
counted as kills, pristine rebuild at the end).

**Scope disclosure (pass 2): the sweep is kernel-only.** It mutated only the
Rust kernels; the Python-side shim marshalling layer (the `_marshal` int
coercion, the lazy `temper_drc_rs` import boundaries, the cache-entry
lookup) was NOT mutant-tested. The pass-2 review's P1-1 (a float-valued
ceiling silently truncated by `int()` fails the #575 approval gate OPEN) is
the concrete proof of why that scope matters -- a kernel-only sweep cannot
see a fail-open in the marshalling boundary. That class is now closed by
fail-loudly int-validation at the marshal boundary (above), and the
`should_skip` null/non-dict entry class by the kernel fix in
temper-design-bundle.
reason); R1h **not applicable** (no physics-gated quantity).

reason); R1h **not applicable** (no physics-gated quantity).

## Violation-Report Kernels (`violation_report.rs`) — Verification (Wave 4 Phase 4, 2026-08-04)

The Wave 4 Phase 4 analysis-surface migration moved the report-building/
shape logic of `temper_placer/analysis/_violation_report.py` (191 LOC)
into this crate.  The Python module is now a delegation shim; its
pre-migration implementation is pinned verbatim as the differential
oracle (`packages/temper-placer/tests/analysis/_violation_report_py_oracle.py`,
commit `c5875adad`).

**Home-crate decision (why temper-drc-rs).** The report consumes DRC
items (`rule`, `components`, `location`, `message` from
`validation/_drc_api.py`) and produces a violation report; the crate that
owns DRC-domain kernels is temper-drc-rs, which already hosts the
report-adjacent `group_violations` and `metrics_summary` kernels
(validation.rs).  temper-design-bundle (Phase-2 contracts) and
temper-rust-router (Phase-5 orchestration) were rejected: neither owns
DRC item shaping or Markdown rendering.

**Boundary — what stays Python and why (the kiutils ruling).** The
module constructs kiutils objects (`KiBoard.from_file`,
`_extract_component_positions` footprint reads) and computes shapely/GEOS
intersections (`_compute_overlap_area_mm2`) for report rendering — both
stay Python-side per the established rulings: kiutils object construction
and GEOS intersection are library semantics that cannot be crossed
bit-exactly (the guide's "library semantics are not reimplementable"
precedent).  This module therefore remains one of the runtime-kiutils
importers (the program's six resolve as their surfaces migrate; #718's
write-engine migration removed one — the resolution here is the compute
that *can* cross, not the kiutils read itself).  `run_drc` (the
kicad-cli subprocess) also stays Python (I/O boundary).  The Rust side
owns everything downstream: target-rule filtering, ref shaping, row
construction, the overlap-callback dispatch, the stable
overlap-descending sort, and the Markdown renderer.

**Induction applicability.** Mathematical induction is not applicable:
both kernels are fixed loops over caller-provided collections whose
per-element operations are size-independent.  Per the plan's R1e a
**structural proof** is recorded instead.

**Structural proof (bit-identical parity).** Claim: for every input in
the differential/PBT domains, `build_report_rows` and `render_report`
reproduce the oracle's `_generate_report_rows`/`_render_report`
bit-identically, with the documented deviation below.
*Proof by structural cases.*
- `build_report_rows` mirrors the oracle loop-for-loop: `rule` `None`
  (the shim's `getattr(err, "rule", None)`) and non-target rules are
  dropped; `refs_sorted` is `sorted(components)` for `len >= 2` (UTF-8
  byte order == code-point order) and an in-order copy otherwise; row
  dicts carry exactly the oracle's eight keys with the oracle's value
  types (`overlap_area_mm2` starts as `0.0`); the overlap callback is
  invoked exactly where the oracle calls `_compute_overlap_area_mm2`
  (`courtyards_overlap` with exactly two refs — its exceptions are
  swallowed Python-side and return `0.0`, so the callback contract
  matches); the final sort is the oracle's stable descending sort by
  overlap (`sort_by` with the comparator reversed; ties keep input
  order, and the differential's tie fixture pins it).
- `render_report` is a line-for-line port: first-appearance rule-section
  order (dict insertion order — implemented as an ordered Vec, not a
  HashMap), the two header lines (including the double space after
  `` `kicad-cli pcb drc`. `` — mutant-class-checked by byte-identical
  render assertions), the `| # | Components | ...` table header and
  separator rows, the em-dash (`U+2014`) intro line, per-row cells with
  CPython fixed-format floats (`py_float_fixed`: correctly rounded, so
  it agrees with CPython's dtoa on every finite double; `nan`/`inf`
  spellings special-cased), the `overlap > 0.0` em-dash gate (NaN and
  `-0.0` both render the em-dash — `NaN > 0` and `-0.0 > 0` are False),
  the pipe-escape-then-truncate message transform
  (`replace("|", "\\|")` then 120 *characters*, not bytes), and the
  Summary section with the oracle's two-rule tallies (non-target rules
  count in neither) and `Total: <len(rows)>`.
- Missing dict keys raise `KeyError` with the same argument as Python's
  subscript (`PyKeyError::new_err("rule")` — `str(exc)` matches).

**Documented deviations (per R1, recorded here).**
- D1 (NaN sort keys): Python's `list.sort` with a NaN key is not a
  strict weak order — TimSort's merge moves NaN-keyed elements
  order-dependently (measured: all 6 orders over 3 elements).  The Rust
  stable sort treats NaN keys as Equal, which is deterministic and
  stable.  The overlap key is never NaN in production (shapely polygon
  area or `0.0`), so the domains agree on every reachable input; the
  differential asserts the non-NaN domain and P3 bounds its generator to
  non-NaN overlaps.

**Evidence.**
- Differential (R1a/R1f, TDD red→green): `test_violation_report_rust_differential.py`
  — oracle `_generate_report_rows`/`_render_report` vs the shim on
  synthetic `DrcError` lists with real shapely fake courtyards (row keys
  canonicalised with floats via `float.hex()` + concrete type tags),
  empty/missing-meta/missing-positions inputs, stable-tie fixtures, the
  rule-attribute-absent case, pipe-escape and 200-char truncation
  renders, first-appearance section order, a 139-value float-formatting
  corpus (location/area cells byte-identical), NaN/negative area em-dash
  cells, missing-key `KeyError` parity, and a build→render round trip.
  RED before the Rust landed (fails to collect).
- PBT (R1c): `test_violation_report_pbt.py` — 6 hypothesis properties
  (P1 rule filtering, P2 ref shaping, P3 sort contract with a
  deterministic synthetic overlap callback, P4 row field fidelity,
  P5 render summary arithmetic, P6 render table structure),
  non-vacuously guarded.
- Metamorphic (R1d): `test_violation_report_pbt.py` — MR1 summary
  permutation invariance, MR2 filtering monotonicity (subset rows ⊆
  superset rows), MR3 ref-order symmetry (canonical `refs_sorted` and
  overlap are invariant under a component-pair swap; the `components`
  field deliberately preserves input order — the honest bound), MR4
  append-stability (appending zero-overlap rows keeps pre-existing rows
  in their relative order).
- Anti-vacuity mutation campaign: **6 mutants, all caught by the
  differential/PBT** — M6 dropped target-rule filter, M7 dropped ref
  sort, M8 ascending instead of descending sort, M9 `>= 0` instead of
  `> 0` area gate, M10 truncation at 121 instead of 120 chars, M13
  dropped pipe escaping.  No survivors.  (The render-literal fidelity
  class — the double space after `` `kicad-cli pcb drc`. `` — is
  exercised by every byte-identical render assertion.)
- Performance A/B (R1b): **no perf arm registered — recorded why.**  The
  migrated compute (row shaping + Markdown rendering of a handful of
  violation rows) is a small fraction of a wall-time budget dominated by
  the kicad-cli DRC subprocess and the kiutils board parse, both of which
  stay Python-side.  A pr_perf_compare arm would measure marshalling
  noise, not compute; the pure-delegation no-regression-beyond-noise
  statement applies.
- Rust practice (R1g): borrow over clone (rows are grouped by ref; refs
  are cloned only where the callback needs owned strings); no `unwrap`
  outside tests; every `#[pyfunction]` boundary relies on pyo3's default
  `catch_unwind` (panics surface as `PanicException` — the validation.rs
  precedent; an explicit `temper_py_bridge::catch_unwind` is impossible
  on a `Py<PyAny>`/`Py<PyList>` return, which is not `UnwindSafe`).
- Physics gating (R1h): **not applicable** — the violation report is not
  a physics-gated surface (no CP-SAT constraint gates on a physics
  quantity; the report summarises kicad-cli DRC output), so the R24
  discipline does not apply.  Stated explicitly because the ledger
  requires the determination.
# Deterministic leaf DRC-check kernels — Verification (Wave 4 Phase 5, batch 2)

## Candidate scorecard — home-crate decision

The DRC-check leaf stages (`drc_validation.py`, `drc_sweep.py`
TrackDeduplicationStage, `placement_validation.py`, `courtyard_check.py`)
and the connectivity-validation kernel (`connectivity_validation.py`) are
validation/DRC-check compute, so they live in **temper-drc-rs**
(`deterministic_leaf_drc.rs`, `deterministic_connectivity.rs`), not
temper-design-bundle (placements/component math) or temper-geometry (pure
geometry primitives). The pad-touch predicate inside
`deterministic_connectivity.rs` calls temper-geometry's single-source-of-
truth `point_to_rotated_rect_distance` via a new rlib dependency — the same
function the Python arm delegates to, so the `<= 1e-4` boundary is one
function, not two.

What stays Python (the shims keep their `run()` orchestration):
kicad-cli subprocess, drc-oracle geometry extraction, per-net grouping,
plane-net/NoNet skipping, violation-object construction, summary logging,
the `DRCValidationError` raise, and the message-formatting delegation to
CPython's `__format__` (`fmt_1f`). The `fail_on_violations` /
`max_violations` threshold *decision* (should-raise + message) is delegated
to the migrated `threshold_decision` kernel so it cannot drift from the
pinned oracle. `_validate_signal_hv` receives the violation kind
(`missing_component` / `path_too_long` / `hv_clearance`) as the kernel
return tuple's final element — the shim no longer infers the kind from
message text.

## R1 status

- **R1a bit-identical vs verbatim oracles.** `test_drc_leaf_rust_differential.py`
  (22 tests) and `test_connectivity_validation_rust_differential.py` (14 tests)
  drive identical inputs through the oracle and the kernel; floats are compared
  bit-exactly. For connectivity the violation *locations* are input coordinates
  (never recomputed) and the descriptions are plain string interpolation, so the
  comparison is exact by construction.
- **R1b no-regression arm.** The stage-level `test_connectivity_validation.py`
  suite (7 tests) runs the delegation shim end-to-end and stays green. No
  perf arm registered: the migrated compute is O(n^2) geometric scans that are
  a small fraction of wall time; a pr_perf_compare arm would measure
  marshalling noise.
- **R1c >=5 non-vacuous properties.** `test_drc_leaf_pbt.py` (8 PBT) and
  `test_connectivity_validation_pbt.py` (6 properties) assert structural
  models: for connectivity, well-separated nets admit an exact prediction
  (unconnected == pad-components - 1, orphan == copper islands,
  dangling == lone tracks) which the properties verify over 100 draws each.
- **R1d >=3 MRs/module.** drc-leaf: dedup net-sensitivity, orientation,
  segment-collapse. Connectivity: translation, net-rename, bridging, order
  permutation (MR4 asserts only the order-invariant facts — the
  unconnected-pad *identity* is root-pinned by the largest-root-primary rule,
  which legitimately changes under registration-order permutation).
- **R1e VERIFICATION.md.** This section. No induction applies (single-pass /
  bounded loops, no recursion beyond the path-compressed UnionFind `find`,
  which terminates by construction); the differentials are the structural
  proof of observational equivalence.
- **R1f TDD.** The RED commits fail to collect with
  `AttributeError: module 'temper_drc_rs' has no attribute ...` before the
  kernels land (demonstrated live), and the PBT suites fail likewise.
- **R1g Rust practice.** borrow-over-clone (the connectivity kernel borrows
  `&[PadRec]`/`&[TrackRec]`/`&[ViaRec]` throughout); no `unwrap` outside
  tests (the four guarded `.unwrap()` calls in the committed DRC kernels were
  replaced with pattern matching in the clippy-cleanup commit); every
  `#[pyfunction]` boundary is wrapped in the `guard` catch_unwind helper so a
  Rust panic surfaces as a Python `RuntimeError`.
- **R1h physics gating.** Not applicable — none of these stages gate a CP-SAT
  constraint on a physics quantity; they summarise/validate DRC geometry.
  Stated explicitly per the ledger.

## Anti-vacuity (mutation campaign)

The 26-mutant reproducible campaign (`scripts/phase5_batch2_mutations.py`)
covers all batch-2 kernels: every mutant rebuilds the crate, must kill at
least one differential/PBT test, then reverts and verifies the source is
pristine before the next. The campaign ends with a pristine rebuild + the
full differential set green. Two candidate mutants were proven observably
vacuous (the differential staying green is correct) and removed with
in-driver notes: layer_assignment empty-net-class (maps identically to
"Signal") and the single pad-component flag (sorted roots[1:] is empty).
The third originally-claimed vacuous mutant — the slot-grid ceil/floor
window — was RE-ADDED after review: the naive "|cell| > radius/spacing
implies distance > radius" argument is false for round-to-nearest cells
(center (0,0), radius 8.5, spacing 5, slot (7.6, 0) sits in cell (2, 0) at
distance 7.6 <= 8.5, reachable only through the ceil window). It is killed
by `test_within_radius_ceil_only_zone`. See the evidence doc
`docs/evidence/2026-08-06-wave4-phase5-batch2-mutation-sweep.md`.

# Wave 4 Phase 5 — via_validation kernels (`deterministic_leaf_drc.rs`)

The final unowned deterministic helper/stage slice (2026-08-06). The two
via-validation kernels moved here (`count_connected_layers` and
`dedup_via_positions`, registered top-level on `temper_drc_rs` as
`count_connected_layers_py` / `dedup_via_positions_py`):

| Kernel | Python origin | Rust function |
|---|---|---|
| via layer-connectivity count | `deterministic/stages/via_validation.py` → `ViaValidationStage._count_connected_layers` | `count_connected_layers` |
| via position dedup | same → `ViaDeduplicationStage.run`'s sweep | `dedup_via_positions` |

The Python stage is a delegation shim; the trace/pin endpoint-index building,
the plane-net predicate (`_is_plane_net`), and the `frozenset` wraps stay
Python. The pre-migration implementations are pinned VERBATIM as the oracle
(`tests/deterministic/stages/_via_validation_py_oracle.py`).

## Home-crate decision

`temper-drc-rs` hosts the DRC-check stage kernels (courtyard_check /
drc_sweep / drc_validation / placement_validation, batch 2). Dangling-via
removal and via dedup are DRC-cleanup validation compute — the same home-crate
line. The `** 2` distance terms resolve libm `pow` via `crate::pymath`.

## Induction applicability

Mathematical induction is not applicable: neither kernel is recursive. Per
R1e, a **structural proof** is recorded instead.

## Structural proof (bit-identical parity)

1. **The `tol * tol` vs `tolerance ** 2` split is pinned.** `count_connected_layers`
   computes `tol_sq = tol * tol` (PLAIN MULTIPLY — the oracle does not use
   `**` there), while `dedup_via_positions` computes `tol_sq = tolerance ** 2`
   (libm `pow`). The two kernels deliberately differ; the differential drives
   both against the verbatim oracle so a `**`↔`*` swap in either fails.
2. **`** 2` distance terms.** Every distance is `(vx - tx) ** 2` via
   `crate::pymath::pow`; the boundary is `<= tol_sq` with a first-hit `break`
   (`test_count_trace_exactly_on_boundary`, `test_dedup_boundary`; mutants
   M12/M13 flip `<=` to `<` and are killed). The `break` is load-bearing for
   the `duplicates` COUNT, not just the boundary: without it, one rejected
   position within tolerance of two KEPT positions fires `duplicates += 1`
   twice (`test_dedup_multi_match_chain_counts_rejected_once`; mutant M14
   removes the `break` and is killed).
3. **Plane-layer auto-connect is gated on `is_plane`.** A signal net on a
   plane layer still needs a trace/pin (`test_count_non_plane_net_plane_layer_needs_trace`;
   mutant M11 drops the gate and is killed). Layers in `via.layers` are
   unique, so the oracle's `connected_layers` set semantics collapse to a
   per-layer `insert` (the trace sweep and the pin sweep are mutually
   exclusive per layer via the `!connected_layers.contains(layer)` check).
4. **Dedup is first-seen-wins in input order and returns kept INDICES** so
   the shim recovers the original `Via` objects by index — object identity
   matters when two vias share an exact position (the oracle keeps the FIRST
   via object; an index-free position map could return the wrong one).
5. **Non-string via layers flow through silently (tolerant extraction).** The
   oracle compares each `via.layers` element against the string trace/pin/
   plane keys, and a non-string layer simply matches nothing (`layer in
   trace_index` on a `{str: ...}` dict misses without raising). The marshaler
   therefore DROPS non-string elements instead of propagating
   `extract::<String>()`'s TypeError, reproducing the oracle exactly — a
   hashable non-string layer contributes nothing to the count on either arm.
   Reachability: only an externally-constructed `BoardState(vias=...)` whose
   `Via.layers` carries a non-string layer (the stage's `Via` is
   contract-typed `tuple[str, ...]`; all production construction sites pass
   layer-name strings). Pinned by `test_count_non_string_layer_ignored`.

## Evidence

- Differential (R1a): `test_via_validation_rust_differential.py` — 26 test
  functions (36 oracle-vs-Rust comparisons), bit-exact against the verbatim
  oracle.
- PBT (R1c/R1d): `test_via_validation_pbt.py` — 5 properties + 3 MRs,
  including an independent dedup coverage/separation cross-check.
- Rust unit tests: existing `deterministic_leaf_drc.rs::tests` plus the
  shared pymath pins.
- Anti-vacuity: mutants M11–M14 in `scripts/phase5_final_leaves_mutations.py`,
  all killed (see `docs/evidence/2026-08-06-wave4-phase5-final-leaves-mutation-sweep.md`).
  M14 (the dedup inner-`break` removal) is killed by
  `test_dedup_multi_match_chain_counts_rejected_once` — a multi-match chain
  where one rejected position sits within tolerance of two KEPT positions
  over-counts `duplicates` without the `break` (the oracle counts once per
  REJECTED position).
- R1b: the stage shims keep their public signatures; the full
  `tests/deterministic/` suite (963 cases) is green. Pure-delegation carve-out:
  no regression beyond CI noise expected.
- R1f: the differential's first commit failed at collection (missing
  `count_connected_layers_py` / `dedup_via_positions_py`) before the kernels
  landed.
- R1g: borrow-over-clone; no `unwrap` outside tests; pyo3 default
  `catch_unwind` at the boundary (per the crate's documented convention).
- R1h: not applicable — no physics-gated quantity (recorded N/A).

# DRCOracle decision kernels (`drc_oracle.rs`) — Verification (Wave 4)

The `router_v6/constraints_drc_oracle.py::DRCOracle` numeric/decision bodies
(2026-08-09). The oracle is the verbatim pre-migration module pinned in
`tests/router_v6/test_constraints_drc_oracle_rust_differential.py`'s
`_oracle_*` block (commit `2e205228`); the shipped module is a delegation
shim.

## Candidate scorecard — home-crate decision

The DRCOracle is DRC-check compute, so it lives in **temper-drc-rs**
(`drc_oracle.rs`). The object itself stays Python (a pickled `BoardState`
field, geometry held in the Python-visible `PCBGeometry`/`RadiusIndex`
R-tree); the spatial queries stay Python (their result order *is* the
oracle's iteration order) and the per-element numeric/decision bodies are
the Rust kernels. Ported: `Violation.severity`, the `@req(2026-06-23-007,
R3)` clearance-credit spatial scoping (`get_pad_credit` /
`get_effective_clearance`), `can_place_via`, `can_place_track_segment`
(neckdown, companion-net skip, R3 credit stack, EXP-13 internal-layer
creepage factor), and `validate_all`'s four pairwise checks. Not ported
(recorded in the differential's docstring): registration glue,
`add_clearance_credit` (axis validation + dict insert), `_resolve_owner`
(`pin_owner` may be a callable), `get_valid_via_sites` (grid loop + Python
sort), and the `{actual:.3f}` reason strings (CPython `__format__`
rendering stays in the shim, which builds them from the kernel's structured
`(kind, id, actual, effective)` return).

## Induction applicability

Mathematical induction is **not applicable** to any kernel: none is
recursive, and none iterates over a dimension whose correctness depends on
a size parameter — every loop over a caller-provided collection is a
bounded, per-element-independent scan (the `can_place_*` loops short-circuit
on the first violation but each element's arithmetic is independent of the
collection size; `validate_all`'s four pairwise loops are likewise
size-independent and emission-ordered). Per R1e, a **structural proof** is
recorded instead.

## Structural proof (bit-identical parity)

1. **Distance primitives are the same functions by construction.** The four
   distances (`point_to_segment_distance`,
   `segment_to_segment_distance`, `point_to_rotated_rect_distance`,
   `segment_to_rotated_rect_distance`, and `Via`-center distance via
   `math.hypot` → `py_hypot`) are the exact kernels the Python arm
   delegates to — the Python oracle and the Rust kernel call one function,
   not two copies. The differential corpus therefore exercises the oracle's
   own boundary behaviour (1-ulp edges, degenerate segments) and both arms
   agree by construction.
2. **`min(required, 0.08)` under `neckdown` is CPython builtin `min`**
   (first-argument survives a NaN — B5), replicated via `crate::pymath::py_min`,
   never `f64::min`. Pinned by `test_can_place_neckdown_keeps_nan`, whose
   geometry (via 0.2mm from a track, 0.08-based effective 0.48) is
   constructed so an `f64::min` kernel would flag a violation the oracle
   does not.
3. **Arithmetic grouping preserved verbatim (B7).** `effective = required +
   via_radius + (width/2)` evaluates as `(required + via_radius) +
   (width/2)`; the EXP-13 factor is one `* 0.30` multiply; the tolerances
   are the oracle's exact `effective - 0.001` / `effective - 0.010`
   subtractions. The differential pins the 1µm and 10µm boundary bands
   (`test_can_place_track_segment_1um_tolerance_boundary`,
   `test_validate_all_track_track_10um_tolerance_boundary`).
4. **The R3 credit kernels preserve dict iteration order.** The shim
   marshals `clearance_credits.items()` in insertion order (first match
   wins); the kernel iterates the wire list in that order. The axis-gated
   AABB band test is a verbatim transcription (chained-comparison `&&`
   semantics, `half_w_band = hw + 0.5`), and the pin-pair test is genuine
   Python 2-element-set equality (`set2_eq`, singleton collapse included).
5. **`validate_all` emission order is the oracle's.** The shim enumerates
   the pairs in `geometry.tracks`/`vias`/`pads` list order and spatial-index
   query order (applying the `id_a >= id_b` / net / diff-pair filters), and
   the kernel emits in the four-loop order (track-track, via-via, track-pad,
   via-pad). `test_validate_all_violation_order_preserved` crafts a board
   where each of the four check types fires exactly once and pins the exact
   order plus location fields.
6. **The can_place short-circuit is order-faithful.** The kernels return the
   first violation in the marshalled (index-query) order; the oracle returns
   on the first violation in the same loop order. `test_can_place_via_reports_first_violation_in_query_order`
   pins the order-sensitive choice.
7. **`LayerIndex` / callable-owner glue stays Python.** `LayerIndex(layer)
   in INTERNAL_LAYERS` (an IntEnum that is deliberately not migrated) is
   evaluated by the shim and passed as `apply_internal_creepage`;
   `_resolve_owner` (callable or dict) stays Python, so only the resolved
   `owner`/`pin` cross the boundary. The `required > 0.5` creepage gate and
   the `credit < required` stack order are inside the kernel, exactly where
   the oracle applied them.

## Empirical verification

- **Differential (R1a).** `tests/router_v6/test_constraints_drc_oracle_rust_differential.py`
  — 65 tests driving identical boards through the verbatim oracle and the
  shim; every comparison via `sig()` (`float.hex()`-exact, type-carrying,
  no tolerance). Includes NaN/inf severity cases, the neckdown-NaN trap, the
  rotated-pad distance, the credit axis gate / either-orientation `None` /
  cross-component rejection / callable owner, the first-violation order, the
  companion skip, internal-layer creepage and credit stacking, `get_valid_via_sites`,
  `validate_all` (order + all four types), and the per-kernel wiring proof.
- **PBT (R1c/R1d).** `tests/router_v6/test_constraints_drc_oracle_pbt.py` —
  P1..P6 (6 non-vacuous properties, each with a `test_pN_fails_for_<mutant>`
  vacuity guard that re-runs the full property under a degenerate compiled
  kernel and requires an `AssertionError`, and each with measured
  reachability `calls >= 50` / `outcomes >= 2` at the Rust boundary) plus
  four metamorphic relations (M1 dyadic translation, M2 x-reflection,
  M3 180° rotation — each exact, since every distance is a difference of f64
  coordinates and dyadic translation / sign flips preserve every f64 bit —
  and M4 registration-order permutation, which preserves the *existence* of
  a violation), with anti-vacuity sanity tests proving the transforms are
  not identity and the M4 board genuinely violates.
- **Regression (R1b).** `tests/deterministic/test_isolation_slots_in_slot_generation.py`,
  `tests/deterministic/stages/test_setup.py`,
  `tests/deterministic/stages/test_drc_validation.py`, and
  `tests/router_v6/test_constraints_spatial_index_rust_differential.py` stay
  green (31 passed, 1 skipped). Pure-delegation carve-out: no regression
  beyond CI noise expected.
- **R1f TDD.** The differential's first commit (`8f795bfa`) failed
  `test_required_rust_symbols_present` (the `drc_oracle_*` symbols did not
  exist) before the kernels landed.
- **R1g.** Borrow-over-clone throughout; no `unwrap`/`expect` outside
  `#[cfg(test)]` (crate clippy lint); pyo3 default `catch_unwind` at every
  `#[pyfunction]` boundary (the crate's documented convention); `cargo
  clippy --all-features --all-targets -- -D warnings` and
  `--no-default-features` `cargo test` clean.
- **R1h.** Not applicable — none of these kernels gate a CP-SAT constraint
  on a physics quantity (recorded N/A).

# IPC standard calculations (`ipc.rs`) — Verification

The IPC-2221/2152 current-capacity and trace-width scalar slice
(`src/ipc.rs`) was consolidated from the deleted `temper-ipc` crate
(2026-08-09, third crate-fold of the consolidation program; precedents:
`placement-topology` → `geometry`, `dsn` → `io-types`). `ipc.rs` carries the
pure kernels and their unit/property tests verbatim from
`temper-ipc/src/core.rs`; `ipc_pyo3.rs` is the wholly-pyo3 surface that
exposes them on `temper_drc_rs`, exactly as the old crate's inline bridge did
for `temper_ipc`. The Python consumers (`temper_placer/core/ipc2221.py`,
`ipc2152.py`) were repointed import-only, bodies unchanged. The `temper-ipc`
crate had no `VERIFICATION.md` to carry over, so this section records the
kernels' verification state from first principles.

## Induction applicability

**Mathematical induction is not applicable to this module.** No kernel is
recursive, and none iterates over a dimension whose correctness depends on a
size parameter:

- `estimate_trace_current` / `estimate_current_from_net_class` /
  `calculate_min_trace_width` are closed-form evaluations of the IPC-2221 /
  IPC-2152 power law (`I = k·ΔT^0.44·A^0.725`) on a fixed number of scalar
  inputs.
- `get_net_current` / `net_currents` perform a bounded substring lookup over
  the fixed 9-entry W2 current table; the lookup result is order-dependent
  only when a net name matches more than one key (a documented, pinned
  divergence — see the differential test), never size-dependent.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every ported symbol, the Rust behaviour
is bit-identical to the pre-migration Rust behaviour — these kernels moved
between crates verbatim, so the claim is trivially carried: the fold commit
kept the body of every function and every test byte-for-byte (only the module
doc block was rewritten), and the pyo3 wrappers delegate to the same
functions with the same argument order, defaults, and `PyResult` plumbing.

*Proof by structural cases.*

1. **Forward ampacity.** `estimate_trace_current` applies the IPC-2221 power
   law with `k = 0.024` (internal) / `0.048` (external); the unit tests pin
   the known reference values (external 0.25 mm / 1 oz / 10 °C → ~0.87 A,
   internal → ~0.44 A).
2. **Inverse width.** `calculate_min_trace_width` is the algebraic inverse of
   the forward law (same `k`, same exponent, thickness carried through);
   unit tests pin the round-trip and the documented doctest values
   (external 0.5 A → 0.1160 mm, internal 0.5 A → 0.3019 mm, external 2 A →
   0.784 mm).
3. **Net-current resolution.** `get_net_current` uppercases the input and
   scans `net_currents()` for the first containing key, falling back to
   `DEFAULT_SIGNAL_CURRENT` (0.1 A). The W2 table's 9 keys and the 0.1 A
   default are unchanged from the source crate.
4. **Module constants.** `NET_CURRENTS` and `DEFAULT_SIGNAL_CURRENT` are
   re-exported by `ipc_pyo3::register` exactly as `temper_ipc` exposed them,
   so `core/ipc2152.py`'s `from temper_drc_rs import (...)` re-export line
   keeps its shape.

## R24 physics-gate state applicability

**N/A.** These kernels compute a current-carrying-capacity *scalar* from a
trace width (and its inverse); they do not gate any CP-SAT constraint on a
physics quantity, and the differential/PBT suite carries the verification
evidence below. The pre-existing P1–P9 property suite (non-negativity,
monotonicity in width/temp-rise/current, internal-vs-external ordering, and
the round-trip identity within 1% relative tolerance) was ported along with
the kernels.

## Evidence

- **Unit tests** — 11 tests carried verbatim in `ipc.rs`'s `#[cfg(test)]`
  module (`test_estimate_external_1oz_10c`, `test_estimate_internal_conservative`,
  `test_estimate_from_net_class`, `test_min_trace_width_roundtrip`,
  `test_ipc2152_min_width_basic`, `test_ipc2152_current_capacity_roundtrip`,
  `test_get_net_current_*` ×4, `test_get_net_current_zero_current`).
- **Proptests** — 9 properties (P1–P9) carried verbatim: non-negativity,
  monotonicity in width/temp-rise/current, external-carries-more /
  internal-needs-wider, the ≤1% round-trip identity, and the always-non-
  negative net-current lookup.
- **Python coverage** — `tests/core/test_ipc2221.py` +
  `tests/core/test_ipc2152.py` exercise the shims through the repointed
  module; `tests/placer/cp_sat/test_net_currents_rust_differential.py`
  pins the exact-vs-substring divergence against the StackupGate Python
  authority; `tests/placer/cp_sat/test_ipc2152_pbt.py` /
  `test_ipc2152_rust_differential.py` pin the placer gate consumers.
- **R1g Rust practices** — `cargo check -p temper-drc-rs` clean with and
  without the `python` feature; no `unwrap`/`expect` outside `#[cfg(test)]`
  (crate clippy lint).

---

# Phase-A U5 — DRC marshalling types (`drc_marshal.rs`) — Verification

Rust-orchestration-engine plan (2026-08-09-001), Phase A unit U5: the typed
marshalling boundary replacing the flat K1 dicts the Python marshalers
(`validation/drc_oracle.py`, `validation/drc_runner.py`) used to shuttle into
the DRC kernels.

## What was migrated

| Python marshaler | Rust type (this crate) | Python name |
|---|---|---|
| `_placement_to_board_dict` | `drc_marshal::DrcBoardSnapshot` | `DrcBoardSnapshot` |
| `_constraints_to_dict` / `_build_constraints_dict` | `drc_marshal::ConstraintSet` | `TypedConstraintSet` |
| `_constraint_value_to_plain` | `drc_marshal::ConstraintValue` | `ConstraintValue` |
| `CheckRunner` dataclass data surface | `drc_marshal::CheckRunner` | `CheckRunner` |

Naming deviation (recorded in the module doc): the plan names the constraints
type `ConstraintSet`, but that Python name is occupied by the Phase-2
*contract* pyclass (`drc_contracts::ConstraintSet`, re-exported by
`drc_types.py`; ~90 tests construct `_tdrc.ConstraintSet(...)`), so the
marshalling pyclass registers as `TypedConstraintSet`.

## Empirical verification

- **G1/G2 differential** — `tests/validation/test_drc_marshal_rust_differential.py`
  (committed RED before the Rust implementation, then GREEN): the
  pre-migration marshaler bodies are pinned verbatim as `_oracle_*` blocks;
  the typed `to_dict()` reproduces the pinned K1 dicts bit-exactly
  (float-hex canonicalization). The placer/parsed-PCB constructors chain
  against the already-oracle-validated dict kernels. Kernel-path equivalence:
  `run_drc(DrcBoardSnapshot, TypedConstraintSet)` ==
  `run_drc(K1 dicts, K1 dicts)` (affected_items sorted — the rules build it
  from a `HashSet` whose order is a per-instance `RandomState` artifact; the
  set is what the rules guarantee).
- **G4 PBT** — `tests/validation/test_drc_marshal_pbt.py`: 6 properties
  (P1 ConstraintValue plain round-trip, P2 pydantic `model_dump` unwrap,
  P3 typed-vs-oracle-dict kernel equivalence on a tight board, P4 CheckRunner
  data surface, P5 from_netlist input honouring, P6 from_state shape
  invariants), each with a `test_pN_fails_for_<mutant>` vacuity guard and a
  module→property map in the file docstring.
- **G5 metamorphic** — 4 relations in the same file: order preservation,
  structural recursion, all-`None`-config ≡ no-config, and power-of-two scale.
- **G6 induction** — N/A for the marshalling boundary: the types are
  data-only (no recursive computation); the only recursion is
  `ConstraintValue`'s structural value-tree recursion, whose base case
  (scalar pass-through) and step (element-wise list/dict conversion) are
  pinned by the P1/P2 differential and the MR2 structural-recursion relation.
- **G8 physics discipline** — N/A: pure marshalling, no physics quantity.

## R1g Rust bar

- `cargo clippy --all-features --all-targets -D warnings` clean.
- `cargo test --features python` (with libpython linked for the test binary):
  1792 tests green, including `drc_marshal::tests` (package-type/rule
  defaults, trace-segment engine shape, constraint-value kind labels).
- Every pyo3 entry point is wrapped in `guard()` (`catch_unwind`); no
  `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

---

# Phase-A U6 — oracle marshalers (`oracle_marshal.rs`) — Verification

Rust-orchestration-engine plan (2026-08-09-001), Phase A unit U6: the typed
marshalling boundary for `validation/human_reference_extractor.py`'s
quality-oracle marshalers.

## What was migrated

| Python marshaler | Rust type (this crate) | Python name |
|---|---|---|
| `_netlist_to_oracle_dict` | `oracle_marshal::OracleInput` | `OracleInput` |
| `_placement_to_oracle_dict` | `oracle_marshal::OracleOutput` | `OracleOutput` |

Both pyclasses register under the plan's names without deviation (no
`TypedConstraintSet`-style rename was needed — no `OracleInput`/`OracleOutput`
name existed in `temper_drc_rs`). The Python shims collapse to
`_tdrc.OracleInput.from_netlist(netlist).to_dict()` /
`_tdrc.OracleOutput.from_state(state, netlist, board).to_dict()` — the
dict-building tax moves to Rust. The consuming kernel
(`temper_quality_oracle.prepare_quality_py` / `evaluate_prepared_py`) still
takes the flat dict (a separate crate, outside this unit's file ownership);
the kernel-signature tightening is a later phase, and the shim round-trips
through `to_dict()` in the meantime. The JUSTIFIED-KEEP record
(`docs/solutions/architecture-patterns/quality-oracle-marshalers-justified-keep-2026-08-09.md`)
predated the rust-orchestration-engine plan; this unit is its re-decidable
trigger firing.

## Empirical verification

- **G1/G2 differential** —
  `tests/validation/test_oracle_marshal_rust_differential.py` (committed RED
  before the Rust implementation, then GREEN): the pre-migration marshaler
  bodies are pinned verbatim as `_oracle_*` blocks (from
  `human_reference_extractor.py` lines 382–417 at `edc19ffa`); the typed
  `to_dict()` reproduces the pinned dicts bit-exactly (float-hex
  canonicalization). Hand-built cases cover empty netlist/positions, no-pin
  nets, duplicate pin refs (no dedup), float32→float64 upcast exactness,
  float64 pass-through, and component-order preservation.
- **G4 PBT** — `tests/validation/test_oracle_marshal_pbt.py`: 6 properties
  (P1 netlist dict ≡ pinned oracle, P2 placement dict ≡ pinned oracle, P3
  per-net pins ref-only/in-order, P4 component bounds→float shape, P5
  cross-marshaler 1:1 ref alignment with positions, P6 board dims), each with
  a `test_pN_fails_for_<mutant>` vacuity guard and a module→property map in
  the file docstring. The position-flattening property (P2/P5) exercises the
  `np.asarray(..., dtype=np.float64).reshape(-1).tolist()` path through both
  float32 and float64 inputs.
- **G5 metamorphic** — 4 relations in the same file: MR1 component-order
  preservation (front insertion), MR2 input↔output ref consistency, MR3
  power-of-two scale (bit-exact by construction), MR4 duplicate-pin-ref
  preservation.
- **G6 induction** — N/A for the marshalling boundary: the types are
  data-only, with no recursive computation.
- **G8 physics discipline** — N/A: pure marshalling, no physics quantity.

## R1g Rust bar

- `cargo clippy --all-features --all-targets -- -D warnings` clean (module
  compiles under the `python` feature; default-features build unaffected).
- `cargo test -p temper-drc-rs` (default features): 1750 tests green.
  `oracle_marshal::tests` (pure-data field-shape tests) compile under
  `--all-features --all-targets`; like the rest of the crate's pyo3-gated
  test modules they need a libpython-linked binary to execute, which CI does
  not provide (the `extension-module` feature leaves libpython unlinked in
  test binaries — the same pre-existing constraint as `drc_marshal::tests`).
- Every pyo3 entry point is wrapped in `guard()` (`catch_unwind`); no
  `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).
