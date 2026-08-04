# DSN emitter — Verification

The SPECCTRA DSN emitter (`src/dsn_exporter.rs`, with the primitives in
`src/dsn_types.rs`) is Wave 4 Phase 3 candidate 6 of
`docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`, ported from
`temper_placer/io/dsn_exporter.py` (559 LOC) and `temper_placer/io/dsn.py`
(131 LOC). Both Python modules are now pure-delegation shims; decision D6
("the DSN surface migrates onto the landed `temper-io-types` primitives and
`io/dsn.py`'s Python types retire") is what this entry closes.

Scope note on the candidate's measured 795 LOC: `io/dsn_schema.py` (39),
`io/dsn_validator.py` (49) and `io/dsn_normalizer.py` (17) were **already**
Rust delegation shims over the `temper-dsn` crate at `origin/main ebf9326ff`
— verified by reading the modules, not inferred. The remaining 690 LOC is what
moved here.

## R1h — state applicability

**N/A.** This is a serialization surface, not a physics-gated one: it reads a
`Board`/`Netlist` and emits text. No clearance, creepage, thermal, or
current-density margin is computed, asserted, or relied upon anywhere in the
module, so the R24 state gate has nothing to attach to.

## Induction applicability

**Mathematical induction is not applicable to this module.** Nothing here is
recursive over a size parameter whose correctness depends on that parameter:

- `dsn_expression_to_string` recurses over the expression *tree*, but the
  per-node rendering is a fixed concatenation independent of subtree depth and
  of sibling count; there is no size-parameterized invariant.
- `export_structure` / `export_library` / `export_placement` /
  `export_network` / `export_wiring` iterate caller-provided collections
  (layers, components, pins, nets, keepouts, traces). The per-element operation
  is independent of the collection's size. It is **not** independent of order
  — the emitter's whole determinism contract is an ordering contract — so
  order-independence is asserted where it holds (deterministic mode, distinct
  sort keys: E4/MR-family in `test_dsn_pbt.py`) and asserted against the oracle
  where it does not (non-deterministic mode, tied sort keys).
- `natural_sort_key` and `compute_center_offsets` are single linear passes.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (byte-identical parity).** For every public entry point, the Rust
emitter's output is byte-identical to the pinned pre-migration Python
implementation (`packages/temper-placer/tests/io/_dsn_exporter_py_oracle.py`
and `_dsn_py_oracle.py`, both pinned VERBATIM at `origin/main ebf9326ff`).

The claim is on **bytes**, not on structure. DSN output is a serialized
artifact: `io/dsn_schema.py` hashes the design into a `;schema-version:` header
that `io/dsn_validator.py` fails closed on, and `tests/io/test_dsn_kicad.py`
pins the emitted file as importable by KiCad's SPECCTRA importer. The
differential therefore asserts `str(rust) == str(python)` with no
normalization, and pairs it with a leaf-for-leaf structural assertion (floats
as `float.hex()`, every non-float leaf carrying its concrete `type`) so that an
int-vs-float drift cannot hide behind a rendering that trims `.0`.

*Proof by structural cases.*

1. **Numeric rendering.** Every coordinate reaches the output through one of
   two paths. Scaled-and-rounded coordinates go through `py_round_half_even`,
   which is CPython's `round(float)` — round-half-to-**even**, implemented as
   `f64::round_ties_even`. `f64::round` breaks ties **away from zero** and is
   therefore not a substitute; on a 5um design grid, exact `.5` ticks are
   common, so the naive port shifts geometry by one 10um unit routinely.
   Unrounded coordinates go through `format_dsn_arg`'s `{:.6}`-then-trim, which
   matches `f"{v:.6f}".rstrip("0").rstrip(".")`; both are correctly-rounded
   decimal conversions of the exact binary value.

2. **Float operation order.** The port preserves CPython's evaluation order
   where reassociation is observable: `-pad_width / 2 * S` is
   `((-pad_width) / 2) * S`, and `(min + max) / 2` is taken on the
   pad-inclusive bounding box after the half-extents. Reassociating the pad
   half-extent is bit-neutral for every *normal* f64 (verified numerically over
   2e5 samples) and differs only at subnormals — which is why the differential
   carries a subnormal pad width (`5e-324`), so the association order is pinned
   rather than merely believed.

3. **Ordering — the determinism contract.** Every sort is reproduced with its
   exact key and with `list.sort`'s **stability**:
   - keepouts sort on `str(k.args[0])`, a plain **string** sort, so `KO_10`
     precedes `KO_2`;
   - image pins sort **twice** — first on the natural key of the scaled X
     coordinate (`args[2]`), then, stably, on the natural key of the pin number
     (`args[1]`), so the X order survives as the tie-break;
   - `_natural_sort_key` splits on `(\d+)` and compares digit runs the way
     CPython compares `int()` of them: leading zeros insignificant, then
     numerically, and **unbounded** (Python's `int` has no width limit, so the
     port compares normalized digit strings by length-then-lexicographic rather
     than parsing into a fixed-width integer);
   - image/padstack/footprint-id sorts key on `py_lower`, a per-character
     lowercase. `str::to_lowercase` is NOT used: it applies the Greek
     final-sigma rule, which CPython's `str.lower()` does not, and the result
     is a sort key.

4. **Insertion order is pinned, not inherited.** `padstacks` and
   `components_by_fp` are Python `dict`s whose iteration order is insertion
   order by language guarantee, and the non-deterministic export path emits
   them in that order. `InsertionMap` reproduces it explicitly. A `HashMap`
   here would be the classic "ordering that happens to be stable today".

5. **Net classification.** The prefix list is transcribed verbatim. The
   voltage regex is `(?i)(_PLUS|VCC|VDD)\d+V?\d*\n?\z` — the `\n?\z` replaces
   Python's `$`, which (without `re.MULTILINE`) also matches immediately before
   a trailing newline whereas the `regex` crate's `$` is end-of-haystack only.
   `\d` is Unicode `Nd` on both sides.

6. **Truthiness.** Python truthiness is reproduced where it is load-bearing:
   an empty comment string emits **no** comment line (`if self.comment:`), an
   empty trace list emits **no** `(wiring)` section (`if traces:`), a falsy
   `layer_stackup` takes the two-layer fallback, and `pin.shape` being `""`
   falls through to `"rect"`.

7. **`bool` is not `int`.** At the pyo3 boundary a `PyBool` arm precedes the
   `PyInt` arm, because CPython's `bool` is an `int` subclass that
   `is_instance_of::<PyInt>()` accepts — the pinned Python falls through to
   `str(v)` and renders `True`, not `1`.

## Boundaries kept on the Python side (and why)

Applying PR #688's `yaml.safe_load` judgement: a kernel is kept across the
boundary when reimplementing it would be a *behaviour change* rather than a
port.

- **`np.argmax`** still derives rotation indices from a 2-D logits/one-hot
  array. Reimplementing it means re-deciding numpy's dtype promotion and
  tie-break on an array this crate cannot see without a numpy-interop
  dependency the phase plan explicitly declines to assume.
- **`pin_world_position`** still computes pad world geometry for the
  non-deterministic net ordering. It is the repo's SSOT for
  rotation-and-side-aware pad placement and it is `sin`/`cos` on `math.pi`;
  libm and Rust's intrinsics are not bit-identical across platforms for
  transcendentals, so porting it would inject a divergence into a *sort key*,
  where fixture differentials are least likely to catch it. The ordering logic
  built on those coordinates IS ported.
- **`compute_dsn_schema_hash`** is called, not reimplemented. It was already a
  Rust delegation shim (`temper-dsn`) before this migration, and
  `io/dsn_validator.py` fails closed on that hash — a second implementation
  would be exactly the drift the validator exists to catch.

## Documented deviations and bounds (per R1, recorded here)

1. **`DSNRect`/`DSNCircle`/`DSNPath` are pyclasses, not frozen dataclasses.**
   They are mutable, unhashable, compare by identity, no longer subclass
   `DSNShape`, and their `__repr__` differs. Measured consumers outside
   `io/dsn.py`: one test, which uses only `to_dsn()`.
2. **`DSNExpression.args` returns a fresh list** on each access rather than the
   stored sequence, so mutating the returned list does not mutate the
   expression.
3. **`DSNPoint` / `DSNShape` / `DSNPolygon` stay Python.** No Rust twin, and
   zero consumers repo-wide. Retiring them is an R8 residual decision.
4. **A short `positions` array now raises `IndexError` at construction**
   rather than at `export_placement`, because the shim materializes the array
   once. Same exception type and message (numpy's).
5. **`i64` coordinate bound.** `py_round_half_even` saturates where CPython's
   arbitrary-precision `int` would widen. A DSN coordinate is a board dimension
   in 10um units (reachable range ~1e6), so the bound is unreachable in
   practice; it is recorded rather than defended in code.
6. **Non-ASCII decimal digits in a natural-sort key.** Digit runs are compared
   as normalized digit strings, which is exact for ASCII. A run mixing scripts
   (e.g. Arabic-Indic digits) would compare by code point where CPython's
   `int()` compares by numeric value. Also unreached: CPython itself *raises*
   `ValueError` on a `str.isdigit()`-true-but-`\d`-false character such as `²`,
   which the port does not reproduce. Both are outside the generated input
   space by construction and named here rather than silently assumed away.
7. **NaN ordering** in the non-deterministic span sort falls back to
   `Ordering::Equal`; CPython's sort with NaN keys is itself
   implementation-defined. Not reachable from finite pad geometry.

## Evidence

- **R1a behavioral A/B** — `packages/temper-placer/tests/io/test_dsn_rust_differential.py`,
  42 tests: every section byte-compared against the pinned oracle plus a
  leaf-for-leaf structural compare; the shipped corpus (`power_pcb_dataset/corpus/`,
  both determinism modes) exported end to end; rounding-mode, natural-sort,
  lowercase-tie, quoting, shape/layer, footprint-separator, duplicate-ref,
  positions/rotations, and exclusion fixtures.
- **R1b performance A/B** — `benchmarks/perf_ab.py`, entry
  `("dsn-exporter", "export_pcb")`, wired to `scripts/pr_perf_compare.py`'s
  record shape and carrying an in-harness **byte**-parity assertion. Per R2
  this is the no-regression-beyond-noise arm; no speedup is claimed as the
  gate. The baseline row must be captured from CI (see the harness docstring on
  the measured ~11% darwin/linux platform bias), so the gate reports
  `NO_BASELINE` until it is.
- **R1c properties** — `packages/temper-placer/tests/io/test_dsn_pbt.py`:
  6 properties for `dsn_exporter` (E1-E6) and 6 for `dsn` (P1-P6), each with a
  G4 vacuity mutant asserting the property fails against a degenerate kernel.
- **R1d metamorphic relations** — MR1 (uniform pad translation absorbed by
  image self-centering, bounded to dyadic offsets), MR2 (sanitization
  idempotence, bounded to the emitted name), MR3 (keepout count monotonicity,
  bounded away from restating the sort), plus M1-M4 in the differential; a
  discriminating-check test proves the relations are breakable.
- **R1f TDD** — the differential was run before the extension carried the new
  class and failed to collect (`ImportError: cannot import name
  'DSNExporterCore' from 'temper_io_types'`); GREEN after the build.
- **R1g Rust practices** — no `unwrap`/`expect` outside tests and the two
  `#[expect]`-annotated literal-regex constructions; borrows preferred over
  clones on the hot path; every `#[pymethods]` body wrapped in `catch_unwind`
  at the boundary. `cargo clippy --all-features --all-targets -- -D warnings`
  clean.
- **Anti-vacuity** — 11 mutations applied to the Rust, rebuilt, and re-run;
  all 11 caught. Two initially survived (`(?i)` dropped from the voltage regex;
  the pad half-extent reassociated) and both were closed by *tightening the
  differential*, not by weakening the claim — the first needed a lower-case
  net name that no prefix rule already classifies, the second needed a
  subnormal pad width. See the PR body for the table.
