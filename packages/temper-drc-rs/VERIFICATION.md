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

1. **Arithmetic equivalence.** `dx**2` in CPython is exact repeated
   multiplication → `dx * dx`; `math.sqrt` is the correctly-rounded IEEE
   sqrt → `f64::sqrt` (measured 0/200000 mismatches for the HV-LV kernel).
   `((x-hx)**2 + (y-hy)**2)**0.5` in the oracle is libm `pow` (measured
   274/200000 random mismatches against `sqrt`), so the mounting-hole
   distance uses `powf(0.5)`, which resolves to the same system libm `pow`.
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
   `ERROR` (the oracle's `_SEVERITY_MAP.get(..., ERROR)` fallback) and
   flags `has_failure` iff severity ∈ {ERROR, CRITICAL}.
5. **Order semantics.** `group_violations` sorts group names with Rust's
   `String` sort (= CPython lexicographic str sort for UTF-8, byte order ==
   code-point order), preserving input order within each group;
   `issue_fingerprint` sorts the item segment identically.
   `metrics_summary` keeps first-seen key position with last-value-wins for
   `check_timings` (Python dict assignment semantics), implemented as an
   order-preserving `Vec<(String, f64)>` scan — not a `HashMap`.
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
   arms (asserted by `test_empty_netlist_both_arms_raise`).

## Documented deviations (per R1, recorded here)

- **`affected_items` typing in `group_violations`.** The oracle passes
  `affected_items` through opaquely; the kernel requires a list of strings
  and raises `PyValueError` otherwise. Realistic `temper_drc_rs.run_drc()`
  output is always a string list, and both arms raise on the pathological
  cases (the oracle fails later, in the `Issue` contract). Narrower and
  documented in `validation.rs`.
- **`parse_drc_violation` non-string `type`/`severity`/`pos`.** Both arms
  return `None` (the oracle via `except Exception`), the kernel via an
  explicit extraction-failure path — same observable result.
- **`metrics_summary` / `compute_drc_penalty` non-float values.** The
  kernel raises `PyValueError`; the oracle raises `TypeError` at the `+=`.
  Both fail closed; realistic inputs are floats.
- **`infer_package_type(None)`.** The kernel's `Option<String>` handles
  `None` as the oracle's `footprint.lower() if footprint else ""` path —
  identical result (`"smd"`), pinned by the differential.

## Evidence

- Differential (R1a/R1f, TDD red→green): the RED commit
  `2893a88fe` ("test(validation): Wave-4 Phase-4 TDD RED — oracles +
  differential/PBT suites") pins the pre-migration implementations verbatim
  (`_tht_check_py_oracle.py`, `_geometric_py_oracle.py`,
  `_drc_oracle_py_oracle.py`, `_drc_fence_py_oracle.py` at commit
  `aece7c372`, plus the migrated-function bodies of `trace_analyzer`,
  `drc` and `drc_runner` pinned inside their differential files). The
  differentials fail to collect until the `temper_drc_rs` kernels exist
  (module-level `= _tdrc.<symbol>` bindings), which is the demonstrated
  RED. GREEN: 89 differential/PBT tests pass (7 files).
- Properties (R1c): ≥5 non-vacuous properties per module (24 PBT across
  the 7 modules), each asserting a concrete observable (severity
  classification, message format shape, sorted/partitioned grouping,
  failure flags, count/metric reconstruction, custom-metric accumulation,
  empty-input behaviour) — see the `test_*_rust_differential.py` suites.
- Metamorphic (R1d): ≥3 honestly-bounded relations per module (25 MRs
  total) — e.g. overlap-threshold monotonicity, reflection invariance of
  geometric findings, permutation invariance of HV-LV clearance (min is
  associative, unlike a sum), penalty doubling with one weight dict scaled
  (bounded to known keys: defaults are not scaled), group-partition
  invariance under input permutation.
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
