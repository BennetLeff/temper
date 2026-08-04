# Placement-constraints surface — Verification (Wave 4, Phase 4)

The placement-constraints compute (`temper_placer/constraints/compiler.py`
530 LOC, `builder.py` 441, `reporter.py` 599) is migrated to Rust in this
crate (`src/constraints/`). The Python modules are delegation shims; the
pre-migration implementations are pinned verbatim as the differential oracles
(`packages/temper-placer/tests/constraints/_*_py_oracle.py`, commit
`aece7c372`).

The verdict (`docs/wave4-verdicts.yaml`) assigns `constraints/**` to Phase 4
with "temper-constraint-compiler is the Rust seed". The crate's existing PCL
pipeline (tier0/1/2 desugaring, type lattice, provenance) is untouched.

## R1a — behavioural A/B, bit-identical

Three differential suites drive IDENTICAL inputs through the pinned oracle and
the delegation shim:

- `test_compiler_rust_differential.py` — compiled filter/scorer over 120
  randomized constraint sets per surface (bool / `float.hex()`), `validate()`
  error tuples (all four fields + `__str__`), the helper methods
  (`_distance`/`_centroid`/`_min_edge_distance`/`_point_to_segment_distance`/
  `_in_zone`/`_find_similar`), NaN/inf placements, plus exact-boundary cases.
- `test_reporter_rust_differential.py` — `check()` result lists (status,
  tier, components, message, `actual`/`expected` via `.hex()`, details),
  `to_text()` and `to_json()` byte-identical (including hand-built reports
  with non-empty `details`), result ORDER (rule order + placements dict
  iteration order).
- `test_builder_rust_differential.py` — `validate()` error strings and
  `to_yaml()` byte-identical.

Floats are compared via `float.hex()` (never tolerance); concrete types are
carried in the comparison keys (`_result_key`); every message string is
compared as-is, which pins `py_float_str` and the `:.1f` rounding
transitively.

### Numerical traps found and handled

- **Neumaier summation.** `_centroid` uses CPython 3.12's `sum()`, which is
  Neumaier-compensated. `src/constraints/mod.rs::neumaier_sum` replicates it
  exactly; the differential's cancellation case
  `[(1e16,0),(1.0,0),(-1e16,0)] -> 1/3` discriminates it from naive
  accumulation (mutant M4 caught).
- **CPython float repr.** `py_float_str` reproduces `str(float)`: decimal
  notation for `1e-4 <= |x| < 1e16` with a `.0` suffix on integrals, signed
  zero-padded exponents otherwise (`1e+16`, `1e-05`, `nan`, `inf`, `-0.0`).
  Rust `{}` would write `1e16`/`1e-5`/`1`. The `:.1f` message precision uses
  Rust `{:.1}`, which matches CPython's round-half-even on the exact value
  (verified on the tie/edge set; pinned by every message comparison).
- **NaN semantics.** CPython's `min`/`max` keep the running first element
  (replace only on strict `<`/`>`), so `min(1, NaN) == 1`, `max(0, NaN) == 0`
  and a NaN in position 0 of `_min_edge_distance`'s four distances survives.
  `py_min`/`py_max`/`py_min_1`/`py_max_0` replicate this; Rust `f64::min`/
  `clamp` would discard NaN. A `clamp`-style mutation is provably equivalent
  (when the projection parameter is NaN the final distance is NaN either way)
  — recorded, not closed.
- **Iteration order.** The `_find_similar` first-match and the
  `"Available zones: ..."` join iterate Python SETS (hash order varies per
  process). The shims pass the exact set-iteration order through
  (`list(component_refs)`, `list(zone_names)`), so Rust matches the oracle
  for every permutation — both sides see the same order in the same process
  (asserted in `test_validate_differential` and
  `test_find_similar_set_order`). Placements dict insertion order flows
  through `check_constraints` (multi-violation result order) the same way.
- **Empty inputs.** Compiling empty constraints: filter always `True`, scorer
  `0.0`, `check()` yields `[]`, `to_text()` yields the header + blank line +
  bare `SUMMARY:` (pinned byte-exactly), `to_json()` yields the all-zero
  summary, `builder.validate([])`/`to_yaml()` yield `[]`/`"{}\n"`.
- **Tier as raw string.** `tier` is carried as the raw string because
  consumers read it back verbatim (`ConstraintResult.tier`,
  `to_yaml` emits `"tier": r.tier`); `is_hard()` is `tier == "hard"`.
- **Error strings.** Every `ValidationError`/builder-error message is built
  with the source's exact f-string content; `ValidationError.__str__` stays on
  the Python dataclass (the differential pins it).

## R1b — performance

The constraint compiler/reporter is **not a speedup candidate** (the
per-call boundary is a marshalling-light pyclass call; the phase guide warns
against manufacturing speed claims). The perf A/B baseline
(`power_pcb_dataset/metrics/perf_ab_baseline.jsonl`) covers
`bottleneck-geometry` only — no benchmarked stage touches this surface, so
the no-regression arm is trivially satisfied and is stated as such rather
than gated. Design choice for the hot path: the compiled
`CompiledSlotFilter`/`CompiledSlotScorer` hold pre-parsed `ConstraintData`
and look placements up directly in the Python dict (no per-call
marshalling). A local micro-benchmark (2000 randomized filter+scorer calls
over a 6-rule constraint set, parity-verified first) measured the shim at
0.34× (filter) / 0.40× (scorer) of the oracle's wall time — reported as a
measurement, not a claim; the perf gate itself does not cover this surface.

## R1c / R1d — properties and metamorphic relations

Per module (all non-vacuously guarded; each fails if the function under test
returns a constant):

| Module | Properties (R1c) | Metamorphic (R1d) |
|---|---|---|
| compiler | P1 totality + empty semantics; P2 hard-spacing ray monotonicity (with a guaranteed-inside guard); P3 scorer non-negativity + positive witness; P4 rejection is rule-witnessed (independent re-evaluation); P5 soft rules never filter | MR1 translation invariance (bounded to integer coordinates where every f64 op is exact); MR2 unrelated placement inert; MR3 scorer additivity over disjoint universes; MR4 power-of-two scale homogeneity |
| reporter | P1 result-count decomposition in rule order; P2 status domain; P3 spacing SATISFIED ⟺ dist ≥ threshold (bit-exact actual); P4 is_violation ⟺ hard&violated; P5 JSON summary matches the report | MR1 crossing a threshold flips status; MR2 removing an unplaced entry is inert; MR3 placements-dict order independence (bounded: no escape/corridor violations); MR4 placing a skipped component activates the check |
| builder | P1 valid build validates clean / missing ref is caught; P2 one error per missing reference; P3 determinism; P4 YAML shape present/absent; P5 YAML numeric round-trip | MR1 available-components order independence; MR2 zone gate on `available_zones is not None`; MR3 serialization conditional-key monotonicity; MR4 `build() is base` identity |

## R1e — induction applicability

**An inductive proof applies to the iterative (non-recursive) rule-list
structure.** No function in the migrated surface is recursive, but the
filter/scorer/reporter all reduce over rule lists, so correctness lifts by
induction on the list length: each rule's contribution is a pure function of
its own fields and the placements (a spacing rule never reads another rule's
state; the scorer accumulates independent non-negative terms; the reporter
emits results per rule in a fixed order). The base case (zero rules:
filter accepts, scorer 0.0, empty report) is asserted in the differential
and PBT suites; the inductive step is that appending one rule adds exactly
its own term/result, which the randomized differential exercises across list
lengths 0–6 per category. The per-element arithmetic order is preserved
verbatim (each `+=` is one f64 add in the source's sequence; the 
Neumaier-summed centroid is the only multi-element reduction and is pinned
exactly).

## R1f — TDD

The oracle + differential + PBT suites were committed first (commit
`873b2f412`) and demonstrated RED: the differentials failed to collect
(`AttributeError` on the missing `CompiledSlotFilter`/
`CompiledSlotScorer`/`check_constraints`/`builder_validate` symbols) until
the Rust surface landed (`8b847ec09`).

## R1g — Rust practice

- `catch_panic` (`temper-py-bridge`) wraps every pyo3 entry point — pyclass
  `__call__`s and all 12 pyfunctions; panics surface as `PyRuntimeError`.
- No `unwrap`/`expect` outside `#[cfg(test)]` (clippy `unwrap_used`/
  `expect_used` deny is satisfied; the two unreachable-`expect` sites in
  `py_float_str` were rewritten as non-panicking `match` fallbacks).
- Borrow over clone throughout; the per-call filter lookup is a `&dyn Fn`
  closure over the Python dict, not a cloned `Vec`.

## R1h — physics gating

**Not applicable — the constraints surface is not physics-gated.** It is pure
compute over declarative rules (no solver, no field quantities, no
conservative-bound constraint). The CP-SAT solver boundary is the Phase-1
JUSTIFIED-KEEP and is untouched; the migrated surface never crosses it. The
R24 discipline therefore does not apply; this is stated explicitly per the
gate's requirement.

## Anti-vacuity — the mutation campaign

11 mutants, 10 caught by the differentials, 1 provably equivalent. Six
survivors were closed by adding exact-boundary discriminating cases to the
differential (the random differential almost never lands exactly on a
threshold):

| Mutant | What it changed | Caught by |
|---|---|---|
| M1 | filter spacing `dist < min` → `dist <= min` | exact 10.0mm threshold case (accepted) |
| M2 | filter proximity `dist > max` → `dist >= max` | exact 10.0mm threshold case (accepted) |
| M3 | escape None-clearance default 3.0 → 0.0 | 2.0mm-inside filter reject + scorer +50.0 |
| M4 | Neumaier → naive sum | centroid cancellation case `(1e16+1-1e16)/3` |
| M5 | message threshold `py_float_str` → `{:.1}` | every `10.0mm` message (`.0` suffix) |
| M6 | corridor `d < half` → `d <= half` | component at exactly half-width (clear) |
| M7 | `_find_similar` min-length-2 guard dropped | `"C"`/`"1"`/`""` return `None` |
| M8 | builder zone empty-string gate dropped | `zone=""` yields no error |
| M9 | `to_text` annotation drops `tier=="hard"` | **provably equivalent** — the annotation is only computed inside the hard-results loop, where `tier=="hard"` always holds |
| M10 | proximity penalty multiplier 10.0 → 5.0 | random scorer differential |
| M11 | spacing check `dist >= min` → `dist > min` | exact 10.0mm threshold case (satisfied) |

Every mutation was applied to the Rust, the extension rebuilt, the three
differential suites run, and the source reverted. A differential that was
green under a mutation is a survivor; the survivors above were each closed
with a discriminating case (committed with the campaign record), and all 11
now fail the differential.

## `Py<PyAny>` decision

The seed crate carries 11 `Py<PyAny>` handles — all in the PCL pipeline's
return positions (`pyo3_bridge.rs`, `lib.rs`), untouched by this migration.
The new constraints surface adds **zero** handles: the shim marshals the
pydantic constraint objects into a plain-dict payload once, Rust parses it
into typed `ConstraintData` structs, and the per-call filter/scorer/reporter
evaluate entirely on those structs (the "data moves into Rust" form the
phase guide prefers over the handle form). The only runtime Python access in
the hot path is exact-ref lookup into the caller's placements dict.

## Known, documented deviations

- **`py_lower` is ASCII-only** (used by `_find_similar`'s prefix match).
  Rust's full `to_lowercase` applies the Greek final-sigma rule CPython's
  `lower()` does not; component refs in every fixture and the differential
  are ASCII, so the ASCII fold matches CPython exactly on the tested domain.
  Non-ASCII component refs are outside the tested domain (the oracle's
  `str.lower` would fold them differently).
- **PyYAML `yaml.dump` and `json.dumps` stay Python stdlib.** The
  `to_yaml` data-shape logic (conditional keys, insertion order) is Rust;
  the serialization call itself stays Python per the Wave-4 guide's PyYAML
  ruling (PyYAML is YAML 1.1 and not bit-reimplementable). `json.dumps`
  stays Python for the same reason (stdlib, deterministic given the
  Rust-built dict).
- **`ConstraintStatus` stays a Python enum.** Consumers use member identity
  (`r.status == ConstraintStatus.VIOLATED`); pyo3 cannot replicate
  class-level iteration or identity semantics, so the enum remains Python
  and the Rust side speaks its canonical string values.
- **Fluent `add_*` builder methods stay Python.** They construct pydantic
  `_constraint_types` objects — orchestration over Python data, not compute;
  the migrated builder compute is `validate()` and the `to_yaml()` shape.
- **`_find_or_create_group` stays Python** (stateful mutation of the
  pydantic object graph).

## Scorecard

| Gate | Status |
|---|---|
| R1a bit-identical A/B | ✓ 40 differential assertions across the three suites (randomized + boundary) |
| R1b perf A/B | ✓ no benchmarked surface (baseline covers bottleneck-geometry); not a speedup candidate — stated, not manufactured |
| R1c ≥5 properties/module | ✓ 5 + 5 + 5 (all non-vacuous, each has a witness/guard) |
| R1d ≥3 metamorphic/module | ✓ 4 + 4 + 4 (bounds stated in-test) |
| R1e verification entry | ✓ induction over rule-list structure (base case asserted, step per-rule) |
| R1f TDD RED-first | ✓ differentials committed RED, went green with the Rust |
| R1g Rust practice | ✓ catch_panic everywhere, no unwrap/expect outside tests, borrow over clone |
| R1h physics gating | ✓ N/A — not physics-gated (CP-SAT boundary is Phase-1 KEEP) |
| Anti-vacuity | ✓ 11 mutants, 10 caught, 1 provably equivalent; 0 survivors |

## Environment notes

`cargo test` on this crate's lib aborts at dyld load on macOS only when the
extension-module feature links a Python interpreter; the pure-Rust
`constraints` unit tests (67 total incl. 15 new) run under
`cargo test --lib` without linking Python and are validated through the
pytest differential against the built wheel.
