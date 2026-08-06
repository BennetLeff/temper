# Validation DRC-check kernels — Verification

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
