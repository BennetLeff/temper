# Wave-4 Discipline Contract — Per-Migration Gates, Bit-Exactness Catalog, Residual Decision Procedure


The operational specification of the Wave-4 full-migration program's durable
artifact (plan `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`,
R1/R2/R3/R7). This document is the checklist every Wave-4 migration PR is
reviewed against, stage 3 of the per-migration pipeline
(`docs/migration-pipeline.md`) in executable form. It is a reference doc, not a
plan: it holds no scope, schedule, or decisions of its own — it specifies how
migrations are gated and how residuals are decided.

---

## 1. Per-migration gate checklist

Every Wave-4 migration must clear every gate below before merge. A reviewer
runs this list on every Wave-4 PR; a missing gate is a merge blocker, not a
follow-up. "Evidence location" names where in the PR the gate's proof appears.

| # | Gate | Requirement | Evidence location in the PR |
|---|------|-------------|-----------------------------|
| G1 | **TDD differential-oracle-first** — the differential test pinning the pre-migration implementation **verbatim** is written *before* the Rust; red → green | R1f, R1a | `packages/temper-placer/tests/<module>/test_<module>_rust_differential.py` opens with a `_oracle_*` block copied from the module AS COMMITTED before migration, carrying a "do not edit — they are the reference" comment (pattern: `test_bottleneck_geometry_rust_differential.py`). Git history shows the test file's first commit (red) predating the Rust pyfunction's (green), or the combined commit's diff order proves test-before-code. |
| G2 | **Behavioral A/B** — bit-identical parity, old vs new, asserted on identical inputs; **bit-exact `==`, not tolerance** (tolerances are only allowed where the *oracle itself* is non-deterministic, and then only with the oracle's own 1-ulp band pinned) | R1a | The differential suite, green on CI, with `==` assertions covering randomized inputs plus crafted edge cases (NaN/inf semantics, degenerate inputs, insertion order). The suite's name and scope are restated in the home crate's `VERIFICATION.md` "Empirical verification" section. |
| G3 | **Performance A/B** — before/after CI wall-time through the existing comparison workflow | R1b, R2 | The PR's `## Performance Comparison` comment (posted by `.github/workflows/pr-perf-check.yml`), with **no 🔴 REGRESSION row** against the rolling median baseline. Margins from `scripts/pr_perf_compare.py`: `TIMING_MARGIN = 0.20` (any `_ms`/`_seconds` metric >20% over baseline → REGRESSION), `COMPLETION_MARGIN = 0.10` (completion-rate metrics dropping >10% → REGRESSION), `IMPROVEMENT_THRESHOLD = 0.10`, rolling window `DEFAULT_WINDOW = 5`. Phase 0 wiring (R2) makes this a hard gate: the script exits non-zero on regression, the workflow's `continue-on-error: true` (currently stub `temper-N6-U8`) is removed, a required status check is configured, and a missing/empty baseline (`NO_BASELINE`) fails closed. Pure-delegation modules (no compute) use the R2 carve-out: "no regression beyond noise", with the Phase-0-quantified CI noise floor stated in the PR body. |
| G4 | **PBT: >=5 non-vacuous properties per module** — every property is vacuity-guarded by a mutation test proving a degenerate kernel violates it | R1c | `<module>_pbt.py` defines P1..P5+ and, per property, a `test_pN_fails_for_<mutant>` re-running the property against a mutated kernel via `hypothesis.inner_test` and asserting `AssertionError` (pattern: `test_bottleneck_geometry_pbt.py` — `restore_kernels` fixture, constant/position-dependent/absent-edge mutants, and a sanity test proving the input class is genuinely discriminating). Hypothesis conventions: `@given` composite strategies, `@settings(max_examples=..., deadline=...)`, docstring per property naming what a degenerate implementation would satisfy trivially. |
| G5 | **Metamorphic testing: >=3 invariant relations per module** — translation/rotation/permutation/scale, honestly bounded (exactness claimed only where the transform preserves every f64 bit, e.g. power-of-two scales; otherwise a stated tolerance with the oracle's own band) | R1d | `<module>_metamorphic.py`, or a clearly-labelled section of the PBT file, naming each relation and its exactness claim (e.g. "translation invariance (exact for power-of-two cells + dyadic centres)" vs "rotation invariance (tight tolerance)"). |
| G6 | **Induction proof** — base case + induction step in the home crate's `VERIFICATION.md`, per the `packages/temper-geometry/VERIFICATION.md` convention; data-only modules (Phase 2 pyclasses, pure-delegation wrappers) record a structural proof or an explicit non-applicability note instead | R1e | A `## <Module> — Verification by Induction` section in the home crate's `VERIFICATION.md`: named base case with the smallest meaningful input (bit-exact vs the oracle), the induction hypothesis, a step arguing per-element independence / order preservation / no cross-element interaction, and the "Empirical verification" paragraph naming the differential/PBT suites. |
| G7 | **Rust best-practices bar** — no `unwrap` outside tests, `catch_unwind` at pyo3 boundaries, borrow over clone, iterators over indexed loops, doc comments on public items | R1g | `cargo clippy`/`cargo test` green on the touched crates; every exported pyo3 function wrapped in `temper_py_bridge::catch_unwind(...).map_err(panic_to_err)` (pattern: `clearance_geometry.rs`); grep for `unwrap` returns only `#[cfg(test)]` / test-module hits; the crate passes `make extensions-check` post-merge. |
| G8 | **R24 physics discipline** (physics-gated surfaces only): Chebyshev-style soundness proof (conservative bound or classified error), BMC-exhaustive validation on small N against a truthful oracle, post-solve audit recomputing the encoded quantity from coordinates | R1h | `docs/physics-verification-methodology.md` conventions: the soundness argument in the module's PBT/VERIFICATION section (e.g. "for separated boxes `0.0 <= cheb <= euclid + 1e-12`" in `test_audit_pbt.py`), a small-N exhaustive oracle comparison in the differential suite, and the audit recompute wired where the constraint is consumed (e.g. `placer/cp_sat/audit.py`, already Rust-backed). Non-physics surfaces record an explicit N/A. |

**Tie-break rule:** when a gate cannot be satisfied honestly (parity cannot be
pinned bit-exactly, a property is genuinely vacuous, the perf baseline is
absent), the candidate is **reported and recorded, not faked** (pipeline hard
rule) — the PR is paused and the divergence is escalated, per the catalog in
section 2, before any of the remaining gates are claimed.

---

## 2. Bit-exactness catalog (R1a basis)

The known divergence classes between Python/CPython arithmetic and Rust's.
**Check this list before implementing a migration; extend it when a new class
is found.** Every class is either a measured Waves 1–3 pitfall or a standing
class checked on every new kernel — the Rust side must replicate the *Python*
semantics, not its own.

| # | Divergence class | Concrete failure example | Mitigation (what the Rust side must do) | Repo evidence anchors |
|---|------------------|--------------------------|------------------------------------------|-----------------------|
| B1 | **Host-runtime libm via `dlsym`** — CPython's `math.cos`/`sin`/`pow` come from the host Python runtime's libm; a crate's statically-bound `f64::sin`/`cos`/`powf` differs in the last ulp (the uv standalone build's libm measured 1 ulp apart on real inputs) | `f64::sin(theta)` ≠ CPython `math.sin(theta)` by 1 ulp → a rotation coordinate is off by 1 ulp → a bit-exact assertion fails | Resolve `cos`/`sin`/`pow` via `dlsym(RTLD_DEFAULT, ...)` (once per symbol, cached in a `LazyLock<Option<fn>>`), falling back to the std intrinsic only when `dlsym` is unavailable | `packages/temper-geometry/src/pad_geometry.rs` (`dlsym_math`, lines ~27–66); `grid_raster.rs` (`dlsym_unary`/`dlsym_binary` for `pow`/`cos`/`sin`, lines ~37–82); documented in `VERIFICATION.md` (pad geometry §, grid kernels §) |
| B2 | **`math.pi / 2.0` vs `FRAC_PI_2`** — the *division* and the named constant differ by 1 ulp | `axis_radius` computed with `PI / 2.0` (Python) vs `FRAC_PI_2` (Rust) → 1 ulp apart | Preserve the exact constant expression the oracle used — write `std::f64::consts::PI / 2.0`, not `FRAC_PI_2` | `VERIFICATION.md` pad-geometry § ("`axis_radius` uses `PI / 2.0` (the division), not `FRAC_PI_2` — also 1 ulp apart") |
| B3 | **Banker's rounding** — Python `round(x, n)` is round-half-**even**; `f64::round` is round-half-away | `round(0.0045, 3)` → `0.004` (Python) but `(0.0045*1000.0).round()/1000.0` → `0.005` (Rust); `2.5f64.round()` → `3.0` but Python `round(2.5)` → `2` | Use `(x * 10^n).round_ties_even() / 10^n` — never `f64::round` | `packages/temper-placer/temper-constraints/src/ipc.rs` (lines ~112–113, `round_ties_even` with the `0.0045`/`0.0055`/`2.5`/`3.5` pin tests, lines ~178–184); `temper-constraints/VERIFICATION.md` |
| B4 | **CPython Dekker double-double `math.hypot`** — CPython's 2-arg `hypot` is `vector_norm` (two-step Dekker), *not* libm `hypot`; they differ in the last ulp | Any distance computed with `f64::hypot` where the oracle is `math.hypot` → 1 ulp off | Replicate `vector_norm` exactly (a `py_hypot` helper: NaN up-front, ±inf handling, then the Dekker two-step), and use it *only* where CPython `math.hypot` is the oracle | `packages/temper-geometry/src/pad_geometry.rs` (`py_hypot`, lines ~135–147); `creepage_check.rs` (lines 13, 59–69); `clearance_geometry.rs` (imports + reach/centre-gap call sites) |
| B5 | **Python `max`/`min` asymmetric NaN semantics** — `max(NaN, x) == NaN` but `max(x, NaN) == x` (builtins keep the *first* argument); `f64::max`/`min` discard NaN | `chebyshev_gap` using `f64::max` silently drops a NaN arm the Python oracle keeps | Replicate `py_max`/`py_min` argument-order semantics explicitly (position-dependent NaN handling), and preserve the oracle's min-then-max nesting (e.g. the grid segment kernel's `t = max(0.0, min(1.0, t))` — `(1.0_f64.min(t_raw)).max(0.0)`, NOT `t_raw.max(0.0).min(1.0)`, because for `t_raw = NaN` CPython `min` keeps its first argument and clamps to 1.0) | `VERIFICATION.md` placement-audit § (py_max semantics), grid-raster § item 3 (min-then-max NaN clamp); `grid_raster.rs` |
| B6 | **GEOS `sqrt`-not-`hypot` distances** — Shapely/GEOS point distance is `sqrt(dx·dx + dy·dy)`, *not* `hypot`; replicating with `math.hypot` or libm `hypot` fails by 1 ulp on ~12% of random pairs (measured) | Pad-pair distance via `py_hypot` where the oracle is GEOS → 1 ulp off on ~12% of pairs | Use plain `sqrt(dx*dx + dy*dy)` where GEOS is the oracle; keep `py_hypot` only where CPython `math.hypot` is the oracle (reach, centre-gap pruning) — the crate's `py_hypot` is *not* a universal distance function | `packages/temper-geometry/src/clearance_geometry.rs` (lines ~20–28 header note, `geos_point_distance` at ~165, `py_hypot` only for the copper-side call sites) |
| B7 | **f64 operation order** — bit-exactness depends on preserving the oracle's expression shape: left-to-right two-op chains stay two ops, `x ** 2`/`x ** 0.5` are libm `pow` (not `x*x`/`sqrt`), constants stay in the oracle's grouping (`mu_0 = 4 * 3.14159265359e-7` as a three-op chain) | `x * x` where the oracle wrote `pow(x, 2.0)` → 1 ulp off; reassociating `(a*b)*c` into `a*(b*c)` → 1 ulp off | Copy the reference expression verbatim: same op count, same grouping, same evaluation order, no reassociation, no fusing | `VERIFICATION.md` (spice § shoelace/`mu_0` chain, grid-raster § `x**2`/`x**0.5`, copper-coverage § "Arithmetic order is preserved exactly") |
| B8 | **Denormal underflow** — CPython (IEEE, no FTZ) preserves denormal results (~1e-308 for f64, ~1e-45 for f32); compiler fast-math or `-ffast-math`-style flags, SIMD FTZ/DAZ, or `mul_add` fusion can flush them to zero | A denormal-band intermediate flushes to 0.0 under Rust fast-math → downstream `x / tiny` diverges from the Python oracle | Keep default IEEE semantics in the crate (no `fast-math`, no FTZ/DAZ, no automatic `mul_add` fusion where the oracle has separate `*` then `+`), and pin a differential case in the denormal magnitude band per module that touches near-zero arithmetic | No in-repo Rust hit for denormal handling yet (grep 2026-08-01) — recorded as a standing class to check on every new kernel, not a fixed one |
| B9 | **CPython `repr(str)` single-quotes vs Rust `{:?}` double-quotes** — dataclass/`__repr__` strings render with Python's `'name'` but Rust's `{:?}` renders `"name"`; string fields inside reprs therefore diverge even when every value is identical (the net_types/loops migrations never asserted full repr equality in their differential suites, so this went unnoticed until the design-rules differential asserted `repr(...)` byte-for-byte) | `repr(ViaTemplate(name='Via1x1', ...))` (Python) vs `ViaTemplate(name="Via1x1", ...)` (Rust) | Render string fields with a `py_str_repr` helper (single-quoted, backslash/single-quote escaping) whenever a repr string is part of the differential contract | `packages/temper-design-bundle/src/design_rules.rs` (`py_str_repr`, ~line 60; used in `ViaTemplate::__repr__`); pinned by `tests/core/test_design_rules_rust_differential.py::test_design_rules_equality_and_repr_identical` |

---

## 3. Residual decision procedure (R3)

Every repo-Python surface not assigned to a migration phase is a **residual**
and must receive a recorded verdict. The procedure: **classify → decide →
record evidence**. Nothing is pre-excluded (R7) — visualization, `scripts/`,
the test suite, the solver boundary, and every library boundary are decisions,
not kept-by-default.

### Step 1 — Classify

| Class | What it is | Examples |
|-------|-----------|----------|
| **product runtime** | imported by the measured product surface (`temper_placer` minus `_constraint_types`/`profiling`) | `visualization/`, `io/` kiutils boundary, `placer/cp_sat/` solver boundary |
| **tooling** | dev/CI tooling, not shipped product | top-level `scripts/`, `benchmarks/`, `packages/temper-placer/{scripts,experiments,spikes}` |
| **test** | test-suite code | `packages/temper-placer/tests` (155,455 LOC) |
| **non-runtime artifact** | docs, data, fixtures with no execution path | `docs/`, `power_pcb_dataset/` |

### Step 2 — Decide

- **MIGRATE** — assigned to a phase in the Wave-4 plan (or a pulled-phase re-plan).
- **RETIRE** — dead or obsolete; deleted with a written retire rationale (what it did, why it is dead, what replaces it).
- **JUSTIFIED-KEEP** — stays Python with a written reason naming a concrete blocker or a measured verdict (see bar below).

### Step 3 — Record evidence (required per decision)

Every verdict records, at minimum: **LOC** (measured), **consumers** (import
graph / call sites — who breaks if it moves), **dependency surface** (third-party
libraries bound to it: ortools, kiutils, shapely, networkx, scipy, plotly),
**churn rate** (git-history signal for `scripts/`-style CI tooling).

### The justification bar

- **"Consolidation" alone never suffices** (R3, D6). A JUSTIFIED-KEEP must name
  a concrete blocker — no mature Rust drop-in (ortools CP-SAT, Phase 1 spike
  pending), format churn (kiutils KiCad), a library boundary (networkx
  min-cut partition order — `nx.minimum_cut`'s reachable partition is
  algorithm-order-dependent, recorded in `temper-geometry/VERIFICATION.md`), or
  a recorded solver-kept verdict in the style of **KTD8** (scipy EDT — `edt`
  crate measured max diff 2.0–2.236, rejected) / **KTD9** (scipy spsolve —
  deliberately kept, measured ~5e-13 K parity) — or a written cost-benefit
  analysis showing migration net-negative.
- **Re-decidable rule:** a JUSTIFIED-KEEP is never permanent — a spike can
  overturn it (a spike *produced* KTD8/KTD9; the Phase 1 ortools spike exists
  precisely to re-open the solver boundary). A verdict is re-reviewed when
  evidence changes: a new crate, a measured parity result, a consumer
  disappearing.

### One-line recording template

```
- <module/path>: <CLASS> → <DECISION> — <blocker or measured verdict> (LOC: <n>; consumers: <n>; deps: <list>; churn: <signal>)
```

Example (matching the recorded verdicts):

```
- scipy EDT (router_v6/channel_widths.py): product-runtime → JUSTIFIED-KEEP — KTD8: edt crate diverges (max diff 2.0–2.236); Rust-native exact EDT recorded fallback (LOC: ~200; consumers: 2 — channel_widths.py:208, _astar_heuristics.py:101; deps: scipy.ndimage; churn: low)
```

---

*This contract supersedes nothing; it operationalizes the Wave-4 plan's R1/R2/R3/R7
and the pipeline's stage 3. Changes to the gates, catalog, or procedure belong
in a plan, not silently in this file.*
