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
  `_in_zone`/`_find_similar`), NaN/inf placements, exact-boundary cases,
  malformed-placement error paths (lazy raise semantics: a fired rule that
  touches a non-2-sequence placement raises the oracle's exception instead
  of silently not firing; unrelated malformed entries stay inert), dict-
  subclass protocol parity (a `__contains__` override that returns False
  skips the rule on BOTH sides; a raising `__contains__` propagates), and
  the pinned pow-vs-product discriminator (regression-proofs the `py_pow`
  seam).
- `test_reporter_rust_differential.py` — `check()` result lists (status,
  tier, components, message, `actual`/`expected` via `.hex()`, details),
  `to_text()` and `to_json()` byte-identical (including hand-built reports
  with non-empty `details` AND with int/bool `actual`/`expected` leaves —
  the oracle emits the leaf untouched, so `json.dumps` renders `5`/`true`,
  not `5.0`/`1.0`), NaN-coordinate message parity (`nanmm`, not `NaNmm`),
  dict-subclass `__getitem__`-raise propagation from `check()`, and result
  ORDER (rule order + placements dict iteration order).
- `test_builder_rust_differential.py` — `validate()` error strings and
  `to_yaml()` byte-identical.

Floats are compared via `float.hex()` (never tolerance); concrete types are
carried in the comparison keys (`_result_key`); every message string is
compared as-is, which pins `py_float_str`, the `:.1f` rounding on finite
values, and — via `test_nan_placements_messages_byte_identical` — the NaN/inf
rendering of the message float sites (`%.1f` in CPython renders NaN as `nan`;
Rust's `{:.1}` Display would write `NaN` — the sites go through
`py_float_fmt_1`, see below).

### Numerical traps found and handled

- **Neumaier summation.** `_centroid` uses CPython 3.12's `sum()`, which is
  Neumaier-compensated. `src/constraints/mod.rs::neumaier_sum` replicates it
  exactly; the differential's cancellation case
  `[(1e16,0),(1.0,0),(-1e16,0)] -> 1/3` discriminates it from naive
  accumulation (mutant M4 caught).
- **`x ** 2` is libm `pow`, not the IEEE product.** CPython's float `**`
  calls the host runtime's libm `pow`, which is not guaranteed to equal the
  (correctly-rounded) IEEE multiply: measured to differ by 1 ULP on ~0.14%
  of values on macOS arm64 (`pow(96.147…, 2.0)` vs `96.147… * 96.147…`).
  The oracle's `_distance` and GroupSpread diagonal use `** 2`, so Rust
  `distance()` and the GroupSpread diagonal route the square through
  `py_pow` — host libm `pow` resolved via `dlsym` once per process (the
  same class-B1 pattern as temper-thermal's `hostmath.rs`), with a `powf`
  fallback. How the two routes resolve per platform (verified 2026-08-04):
  on **Linux** (Ubuntu CI) `dlsym(RTLD_DEFAULT, "pow")` resolves the
  process-global glibc libm `pow` (primary route; the 200k-sample A/B shows
  zero mismatches); on **macOS** `dlsym(RTLD_DEFAULT, "pow")` returns NULL
  from a Python-loaded extension — `RTLD_DEFAULT` (null handle) only covers
  the main image + `RTLD_GLOBAL` images, and CPython loads extension bundles
  with `RTLD_LOCAL` (the same call succeeds from a standalone C binary, so
  the "invalid handle" claim only reproduces inside Python) — so the `powf`
  fallback runs there and is sound *by accident*: with a runtime exponent
  LLVM cannot fold `f64::powf` to `x * x`, it emits an undefined `_pow`
  resolved to libSystem, the SAME function CPython's `float_pow` calls
  (verified via `nm`: `U _pow` in the built `.so`, plus the
  pow-vs-product discriminator in the compiler differential). The dlsym
  declaration is `#[cfg(not(target_arch = "wasm32"))]`-guarded, which leaves
  it compiled (and unlinked — no `dlsym` in the MSVC CRT) on Windows;
  recorded, not fixed: out of scope for the Ubuntu CI target. Plain
  `f64::powf(2.0)` with a LITERAL exponent is NOT a safe stand-in: the
  extension's release build folds it into `x * x` (verified in the installed
  `.so`; the P3 spacing PBT surfaced the 1-ULP divergence). `sqrt` stays
  `f64::sqrt` — IEEE-754 correctly rounded, bit-identical to `math.sqrt`;
  the PBT reference uses `math.sqrt` (not `** 0.5`, which is libm `pow`
  again).
- **CPython float repr.** `py_float_str` reproduces `str(float)`: decimal
  notation for `1e-4 <= |x| < 1e16` with a `.0` suffix on integrals, signed
  zero-padded exponents otherwise (`1e+16`, `1e-05`, `nan`, `inf`, `-0.0`).
  Rust `{}` would write `1e16`/`1e-5`/`1`. The `:.1f` message precision uses
  `py_float_fmt_1`, which is Rust `{x:.1}` (round-half-even, byte-identical
  to CPython's `%.1f` on every finite value — verified on the tie/edge set;
  pinned by every message comparison) with NaN/inf special-cased: CPython's
  `f"{float('nan'):.1f}"` is `nan`, while Rust's `{:.1}` Display writes `NaN`
  — a byte-parity break demonstrated by the adversarial re-review and closed
  by the shared helper. NaN reaches the messages only through the placements
  dict (every constraint-side float is pydantic-bounded `ge`/`gt` 0, so NaN
  cannot ride a rule field): spacing/proximity distance, the thermal edge
  distance, and the group-spread diagonal all render `nanmm` identically
  (pinned by `test_nan_placements_messages_byte_identical`). The escape/
  corridor DISTANCE sites are unreachable with NaN through `check()` (`NaN <
  x` is False, so no violation ever carries a NaN distance) — the helper
  covers them anyway.
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

- `catch_panic` (`temper-py-bridge`) wraps every pyo3 entry point — the two
  `#[new]` pyclass constructors, both `__call__`s and all 12 pyfunctions;
  panics surface as `PyRuntimeError`. Non-panic errors pass through as their
  native Python exception: the compiled filter/scorer `__call__`s propagate
  placement-lookup/extraction failures (TypeError/IndexError — matching the
  oracle's eager `placements[other]` + tuple-unpack raise) instead of
  converting them to `RuntimeError` or silently letting the rule not fire.
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
| M5 | message threshold `py_float_str` → `{:.1}` | multi-decimal threshold in messages: `10.25mm` → `10.25` vs `10.2` (an integral `10.0mm` threshold cannot discriminate — both render `10.0`; pinned deterministically by `test_spacing_message_multi_decimal_threshold`) |
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

## Adversarial re-review (2026-08-04) — three byte-parity breaks closed

An adversarial pass on the merged Phase-4 branch returned HOLD with three
demonstrated byte-parity breaks and two residual risks; all were closed:

1. **NaN message rendering.** `{:.1}` Display writes `NaN` where CPython's
   `%.1f` writes `nan` — six message sites in `report.rs`, diverging in
   `check()` messages and propagating into `to_text()`/`to_json()`.
   Closed by `py_float_fmt_1` (finite values unchanged; NaN/inf mapped to
   `nan`/`inf`/`-inf`) + `test_nan_placements_messages_byte_identical`
   (NaN driven through the placements dict, which is the only NaN channel —
   constraint-side floats are pydantic-bounded).
2. **Dict-subclass protocol.** (a) The compiled filter/scorer used
   `PyDict_Contains`, bypassing a Python-level `__contains__` override —
   an always-False `__contains__` flipped filter decisions (oracle skips
   the rule, shim fired it) and a raising `__contains__` was swallowed.
   Closed by routing `placements_lookup` through `PySequence_Contains`
   (`as_any().contains`). (b) The reporter extracted placements into a
   C-level list, so a dict subclass whose `__getitem__` raises made the
   oracle's `check()` raise while the shim returned a normal report.
   Closed by routing the reporter's per-ref lookups through the same
   Python-level lookup closure (the escape/corridor item iteration stays
   C-level, matching `placements.items()` on non-overriding subclasses).
3. **Hand-built `to_json` with int/bool leaves.** `result_from_dict` coerced
   leaves to f64, so `actual_value=5` re-emitted as `5.0`. Closed by
   marshalling the RAW Python leaf through the JSON builder (`ParsedResults`
   carries the untouched leaves; the f64 coercion on `CheckResult` is now
   best-effort since no consumer of the to_text/to_json path reads it).
4. **py_pow seam docs** were inaccurate on macOS (`dlsym(RTLD_DEFAULT,
   "pow")` returns NULL inside a Python-loaded extension, so the `powf`
   fallback runs and is sound by accident — see the `** 2` bullet above).
   Corrected in-source and in this file, and `test_distance_pow_vs_product_
   discriminator` pins the found input where `pow` differs from the IEEE
   product through `_distance`. The Windows link gap (the `not(wasm32)`
   guard leaves the `dlsym` declaration unlinked on Windows) is recorded,
   not fixed.

The RED fixtures were committed first (commit `9624bb1fd`): 5 of the 6
failed against the built extension; the fixes commit turns them green.

## `Py<PyAny>` decision

The seed crate carries 11 `Py<PyAny>` handles — all in the PCL pipeline's
return positions (`pyo3_bridge.rs`, `lib.rs`), untouched by this migration.
The new constraints surface adds **zero new stored** `Py<PyAny>` handles:
the shim marshals the pydantic constraint objects into a plain-dict payload
once, Rust parses it into typed `ConstraintData` structs, and the per-call
filter/scorer/reporter evaluate entirely on those structs (the "data moves
into Rust" form the phase guide prefers over the handle form). The only
runtime Python access in the hot path is exact-ref lookup into the caller's
placements dict. (Return-position `Py<PyAny>` values are transient
marshalling — e.g. `yaml_value_to_py` builds the YAML dict, and the
validate/check/report entry points return freshly-built Python objects;
none are stored past the call.)

## Known, documented deviations

- **`py_lower` is ASCII-only** (used by `_find_similar`'s prefix match).
  Rust's full `to_lowercase` applies the Greek final-sigma rule CPython's
  `lower()` does not; component refs in every fixture and the differential
  are ASCII, so the ASCII fold matches CPython exactly on the tested domain.
  Non-ASCII component refs are outside the tested domain (the oracle's
  `str.lower` would fold them differently).
- **Compiled filter/scorer entry-point narrowing.** The pyclass `__call__`
  signatures require `component: str` and a real `dict` for `placements`
  (pyo3 extraction). The oracle's `filter_slot`/`score_slot` accept any
  hashable component (e.g. `int 5`) and any object with `__contains__`/
  `__getitem__` (a `collections.abc.Mapping`): oracle `True`/`False` vs shim
  `TypeError` (`'int' object is not an instance of 'str'`, `'...' object is
  not an instance of 'dict'`). Realistic usage is str components and dict
  placements (the shim's own type aliases and every consumer), and the
  dict-subclass PROTOCOL (Python-level `__contains__`/`__getitem__`) IS
  honored on the values that pass extraction — so this is recorded as a
  documented deviation, not widened.
- **Dict-subclass protocol.** The shim's placement lookups use the
  Python-level membership/subscript protocol (`PySequence_Contains` /
  `__getitem__` via `as_any()`), NOT the dict C-API fast paths, so a dict
  subclass's `__contains__`/`__getitem__` overrides behave identically to
  the oracle's `other in placements` / `placements[other]`: an override
  returning False skips the rule (filter accepts), and a raising override
  propagates (compiler differential's `TestDictSubclassProtocolDifferential`
  and the reporter's `__getitem__`-raise case).
- **Malformed-placement error wording.** When a fired rule touches a
  placement value that is not a 2-sequence of numbers, both the oracle and
  the Rust raise — same exception type, and byte-identical message for the
  non-sequence and too-short cases (`'float' object is not subscriptable`,
  `tuple index out of range`) and for a dict subclass whose `__getitem__`
  raises (propagated verbatim). Only the *non-numeric element* case differs
  in wording: the oracle's `_distance` fails inside the arithmetic
  (`unsupported operand type(s) for -: 'float' and 'str'`), the Rust fails
  inside pyo3's f64 extraction (`must be real number, not str`) — both
  `TypeError`. The differential pins the exception type for that case
  (`test_non_numeric_value_raises_type_error`) and pins byte-identical
  messages for the other three.
- **Malformed-placement scope.** The error propagation covers the compiled
  filter/scorer `__call__`s (the per-call hot path the oracle reaches via
  `placements[other]`) and the reporter's `check()`, whose per-ref placement
  lookups go through the same Python-level protocol — a dict subclass whose
  `__getitem__` raises propagates natively from `check()` exactly like the
  oracle (`test_dict_subclass_raising_getitem_raises_in_check`). The
  reporter's EAGER `placements_vec` extraction of the item list (non-tuple /
  non-numeric placement VALUES, reached through the escape/corridor
  iteration which the oracle reads from `placements.items()`) still raises
  inside the uniform entry-point mapping and is wrapped in `PyRuntimeError`
  rather than passed through as the native type; no differential exercises
  that path.
- **Reporter iterates `placements.items()` at the C level.** The escape/
  corridor full-iteration extracts the ordered item list with the dict
  C-API fast path, matching `placements.items()` on any dict subclass that
  does NOT override `items()`. A subclass that overrides `items()` is
  outside the tested domain (recorded, not closed).
- **PyYAML `yaml.dump` and `json.dumps` stay Python stdlib.** The
  `to_yaml` data-shape logic (conditional keys, insertion order) is Rust;
  the serialization call itself stays Python per the Wave-4 guide's PyYAML
  ruling (PyYAML is YAML 1.1 and not bit-reimplementable). The
  byte-identical `to_yaml()` pin is therefore a pin to the **CI's PyYAML
  version** (the same interpreter+PyYAML both sides run under), not a
  statement about YAML semantics across versions. `json.dumps` stays Python
  for the same reason (stdlib, deterministic given the Rust-built dict).
- **`ConstraintStatus` stays a Python enum.** Consumers use member identity
  (`r.status == ConstraintStatus.VIOLATED`); pyo3 cannot replicate
  class-level iteration or identity semantics, so the enum remains Python
  and the Rust side speaks its canonical string values.
- **Fluent `add_*` builder methods stay Python.** They construct pydantic
  `_constraint_types` objects — orchestration over Python data, not compute;
  the migrated builder compute is `validate()` and the `to_yaml()` shape.
- **`_find_or_create_group` stays Python** (stateful mutation of the
  pydantic object graph).

## Residual guard limitations (recorded, not closed)

- **`_centroid` pins CPython ≥ 3.12 `sum()`.** The oracle's `_centroid` uses
  the built-in `sum()`, which is Neumaier-compensated since 3.12. The
  differential compares the Rust `neumaier_sum` against it; CI pins CPython
  3.12, and on 3.11 the differential fails loudly (mismatched centroid for
  the cancellation case) rather than silently passing — it is not a
  version-tolerant pin.
- **`_f()` comparison-key coercion hides int-vs-float leaf divergence.**
  The differentials' shared comparison key `_f(value) = float(value).hex()`
  coerces int leaves to float, so a migrated function returning `1` where
  the oracle returns `1.0` would compare equal (both `0x1.0p+0`). The
  helper is duplicated per-suite rather than shared, so the coercion was
  recorded rather than churned: every migrated surface returns typed values
  (`f64` in Rust, float in Python), the check()-produced reporter
  `actual`/`expected` leaves are floats by construction on both sides, and
  the hand-built-report `to_json` path is pinned on the LEAF TYPE directly
  (`test_hand_built_report_int_and_bool_leaves_json` asserts
  `json.loads(...)` yields `int`/`bool`/`float`/`None` exactly as the
  oracle renders); the PBT suites additionally assert concrete Python types
  on the shim outputs.

## Scorecard

| Gate | Status |
|---|---|
| R1a bit-identical A/B | ✓ 54 differential test methods across the three suites (randomized + boundary + protocol + NaN + int/bool-leaf cases) |
| R1b perf A/B | ✓ no benchmarked surface (baseline covers bottleneck-geometry); not a speedup candidate — stated, not manufactured |
| R1c ≥5 properties/module | ✓ 5 + 5 + 5 (all non-vacuous, each has a witness/guard) |
| R1d ≥3 metamorphic/module | ✓ 4 + 4 + 4 (bounds stated in-test) |
| R1e verification entry | ✓ induction over rule-list structure (base case asserted, step per-rule) |
| R1f TDD RED-first | ✓ differentials committed RED, went green with the Rust |
| R1g Rust practice | ✓ catch_panic at every pyo3 boundary (12 pyfunctions + 2 `__call__`s + 2 `#[new]` constructors), no `unwrap`/`expect` outside tests, borrow over clone |
| R1h physics gating | ✓ N/A — not physics-gated (CP-SAT boundary is Phase-1 KEEP) |
| Anti-vacuity | ✓ 11 mutants, 10 caught, 1 provably equivalent; 0 survivors |

## Environment notes

`cargo test` on this crate's lib aborts at dyld load on macOS only when the
extension-module feature links a Python interpreter; the pure-Rust
`constraints` unit tests (67 total incl. 15 new) run under
`cargo test --lib` without linking Python and are validated through the
pytest differential against the built wheel.

## PCL contract objects — Wave 4, Phase 2/6 (`src/pcl_contracts.rs`)

A second surface migrates into this crate: the pure-data contracts of
`temper_placer/pcl/constraints.py` (872 LOC pre-migration) — the eight PCL
constraint classes' data surface and `CompilationContext`. They become pyo3
`#[pyclass]` objects: construction validation (`because` ≥10 chars, `targets`
membership, `AlignedConstraint` ≥2 components, `AnchoredConstraint`
region/position exclusivity), id generation, `involves_component`,
`to_dict`, `escalate`, and the deterministic dataclass-style
`__repr__`/`__eq__`/`__hash__` surface run in Rust. `pcl/constraints.py` is
now a delegation shim.

**Why this slice and not more.** The module carried an ortools-encoder
entanglement: `BaseConstraint` (an ABC the tagged-constraint classes
subclass) holds the class-level `backends` registry that
`sat_bridge.py`/`drc_bridge.py` populate and `parser.py` dispatches through,
and the tagged classes call `super().__init__` into it. That slice — and the
value enums, which must stay Python `enum.Enum` for `for t in ConstraintType`
and `ConstraintType(value)` — stays in Python per the Phase-1 ortools-encoder
KEEP. The migrated classes are registered as **virtual subclasses** of
`BaseConstraint` (`ABC.register`), so `isinstance(c, BaseConstraint)` — which
`test_feedback` asserts on every feedback delta — keeps holding.

## R1a — behavioural A/B, bit-identical

`tests/pcl/test_constraints_rust_differential.py` (169 methods) drives
identical inputs through the shim and the oracle block pinned in the same
file. The oracle is the pre-migration `constraints.py` with one documented
mechanical transformation: the eight concrete classes were *plain* classes
whose `repr()` was the address-dependent `object at 0x...` form — not a
pin-able contract — so the oracle re-declares them as
`@dataclass(unsafe_hash=True)` (fields in the same order, `__init__` and
method bodies verbatim; `BaseConstraint` as a plain ABC with a manual
`__init__` so the dataclass subclasses can carry non-default fields;
`CompilationContext` was already a dataclass and is copied as-is). The
differential pins, per class: `repr()` byte-identical, structural `==`
agreement, `__hash__`-agrees-with-equality, `to_dict()` (via the type-carrying
`_pclsig` comparator), `involves_component`, id generation, the escalation
ladder, the `ValueError` messages (`must be ≥10 chars`, `at least 2
components`, `requires either region or position`, `cannot have both`),
default values (`metric`/`margin_mm`/`tolerance_mm`/`max_distance_mm`),
deepcopy and pickle round-trips (`__reduce__`), and enum **identity** — the
getters hand back the very live `ConstraintTier`/`ConstraintType`/... 
singletons the rest of the tree binds against.

## R1c / R1d — properties and metamorphic relations

`tests/pcl/test_constraints_pbt.py` (hypothesis, 200 examples each; all
non-vacuously guarded):

| # | Kind | Property |
|---|---|---|
| P1 | R1c | id is deterministic over identical inputs and non-empty |
| P2 | R1c | a caller-supplied `id` wins over auto-generation |
| P3 | R1c | `to_dict` serializes enum fields to `.value` and round-trips string fields |
| P4 | R1c | `involves_component` is True for every named ref, False otherwise |
| P5 | R1c | `escalate` is monotone, reaches HARD in ≤2 steps, HARD is a fixed point |
| P6 | R1c | `deepcopy` is an exact clone (eq/repr/to_dict/id) |
| MR1 | R1d | id is invariant under escalation |
| MR2 | R1d | `to_dict` is invariant under deepcopy |
| MR3 | R1d | escalate commutes with deepcopy |
| MR4 | R1d | involvement answers are invariant under escalation |

## R1e — induction applicability

The migrated surface is finite flat data: each constraint object is a fixed
set of fields whose derived behaviour (`id`, `to_dict`, `involves_component`,
`escalate`, repr/eq/hash) is a pure function of those fields. Correctness
lifts componentwise: every field is stored exactly as passed (no coercion)
and every derived value is computed from the stored fields alone, so two
objects that agree on all fields agree on all derived values — which is what
the structural `__eq__` and the deterministic `repr` assert. The only
recursion-like structure, the list fields (`inner`, `components`, `targets`),
appears only in membership checks and serialization pass-through; the oracle
and shim iterate them in the same order.

## R1f — TDD

RED first (commit `07e8ead6`): the differential was committed against the
pre-migration module with 24 expected failures — the object-`repr` (11),
identity-`hash` (11) and the `targets=` constructor rejection (2) — pinning
exactly the delta the migration introduces. The Rust surface + shim landed in
the following commit (`fe9e6fb5`) and turned all 165 differential methods
green.

## R1g — Rust practice

- No `unwrap`/`expect` anywhere (the crate's clippy `unwrap_used`/
  `expect_used` deny is satisfied); `cargo clippy --all-features
  --all-targets -- -D warnings` is clean.
- The constructors and `to_dict` entry points are wrapped in
  `temper_py_bridge::catch_panic` (R1g catch_unwind at the boundary); panics
  surface as `PyRuntimeError`, while non-panic errors (the `ValueError`
  validations, pyo3 extraction `TypeError`s) pass through as their native
  Python exception — the differential pins the `ValueError` messages
  byte-for-byte.
- Live Python enum singletons are cached once in a `PyOnceLock` and handed
  back through the getters (no re-import per call).
- `hash` is CPython's own tuple hash (`hash(tuple(...))`), not a replica.

## R1h — physics gating

**Not applicable** — PCL contract objects are declarative data, not
physics-gated compute (no solver, no field quantities, no conservative-bound
constraint). Stated explicitly per the gate.

## Known, documented deviations

- **`repr`/`==`/`hash` are a defined contract, not the pre-migration
  behaviour.** The pre-migration classes were plain classes with
  address-dependent `repr` and identity `==`/`hash`. The migration defines the
  deterministic dataclass-style surface (the "contracts-as-pyo3-pyclasses"
  pivot) and pins it against the re-declared oracle. No in-repo consumer
  relied on the old repr/identity equality (grep-verified).
- **`targets=` is accepted at construction (widening).** The pre-migration
  concrete `__init__` signatures rejected it (`TypeError: unexpected keyword
  argument 'targets'`); the migrated constructors accept the `BaseConstraint`
  dataclass field and run its validation. No in-repo caller passes `targets=`
  (grep-verified), and the oracle dataclass accepts it, so the differential
  stays shim==oracle on every exercised path. The differential pins the exact
  `ValueError` literal for an invalid target instead.
- **`__hash__` covers the hashable field surface.** List/dict fields cannot
  sit in a Python tuple, so the oracle dataclass's `unsafe_hash` is
  *unhashable* for list-bearing classes. The shim keeps objects hashable (as
  the pre-migration plain classes were) by hashing only the scalar fields —
  equal objects share equal scalars, which is all the
  equal-implies-equal-hash invariant needs.
- **The value enums stay Python `enum.Enum`** (`ConstraintTier`,
  `ConstraintType`, `DistanceMetric`, `Axis`, `BoardSide`, `EdgeType`,
  `CompilationTarget`): production does `for t in
  ConstraintType` and `ConstraintType(value)`, which a `#[pyclass]` enum
  cannot provide (the tag_dispatch precedent). Rust holds the members the
  objects were constructed with and hands back the same singletons.
- **`BaseConstraint` stays Python** (the tagged-constraint subclasses and the
  sat/drc/rust bridge registration are the Phase-1 ortools-encoder KEEP);
  the migrated pyclasses are virtual subclasses, so `isinstance` checks hold
  but `super()`/`__mro__` traversal from a migrated instance is not the
  Python-class path (no in-repo consumer does that).
- **Non-str constructor fields.** The `because` field is extracted to `str`
  for validation, so a non-str `because` raises pyo3's
  `TypeError: argument 'because' must be str` instead of Python's
  `TypeError: object of type '...' has no len()`. Realistic callers always
  pass strings (the parser and every fixture do); recorded, not closed.
- **`__reduce__` reconstructs via the constructor.** Pickle/deepcopy rebuild
  from the constructor args (id included), which is byte-identical for
  already-constructed objects.

## Scorecard (PCL contract objects)

| Gate | Status |
|---|---|
| R1a bit-identical A/B | ✓ 169 differential methods (repr/eq/hash/to_dict/involves/id/escalate/validation/defaults/deepcopy/pickle/enum identity/BaseConstraint compat) |
| R1b perf A/B | ✓ not a benchmarked surface; contract objects are not a speedup candidate — stated, not manufactured |
| R1c ≥5 properties | ✓ 6 (P1–P6, all non-vacuously guarded) |
| R1d ≥3 metamorphic | ✓ 4 (MR1–MR4, bounds stated in-test) |
| R1e verification entry | ✓ componentwise field-data induction (base asserted: empty/edge inputs in the differential) |
| R1f TDD RED-first | ✓ differential committed RED (24 expected failures), went green with the Rust |
| R1g Rust practice | ✓ catch_panic at every constructor/to_dict boundary, no unwrap/expect, clippy `-D warnings` clean |
| R1h physics gating | ✓ N/A — declarative data, not physics-gated |
