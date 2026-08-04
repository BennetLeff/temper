# Write/export engine — Verification

The write/export engine kernels (`src/kicad_write.rs`) are Wave 4 Phase 3
candidate 4 of
`docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`, ported from
`temper_placer/io/kicad_exporter.py` (779 LOC), `_write_board.py` (532),
`_write_tracks.py` (340), `_write_modules.py` (271), `placement_exporter.py`
(281), `_write_zones.py` (106), `kicad_writer.py` (93) and `_write_types.py`
(90) — 2,492 LOC of the candidate's measured 2,493 (the residual line is the
`validate_output_pcb` kiutils-read helper, kept across the boundary; see
"Boundaries kept on the Python side"). All eight Python modules are now
delegation shims; the pre-migration implementations are pinned VERBATIM as
`packages/temper-placer/tests/io/_*_py_oracle.py`.

## Candidate scorecard (home-crate decision, why this scope)

The plan's Q3 leaves the home crate per-candidate. **temper-io-types** is the
home crate, not temper-design-bundle: the write engine is an IO surface (the
DSN write precedent lives here), the plan's D3 names "a Rust KiCad
s-expression engine in temper-io-types" as the target, and the kernels hold
no contract pyclasses — the four result pyclasses (`PlacementUpdate`,
`WriteResult`, `StrippingResult`, `IsolationSlotResult`) are IO result types,
not domain contracts.

The honest scope is the plan's D5/Q1 shape: **every transformation and
decision of the write path is Rust, reading its unmigrated inputs
(kiutils `Board`, router_v6 `RoutePath`, `PlacementState`, `BoardState`,
numpy arrays) duck-typed across the pyo3 boundary; the kiutils object I/O
and item construction stay in the shims.** The alternative — a byte-identical
full-board serializer replacing kiutils' `board.to_file` — is not reachable
without the shared sexpr board model the parse candidate (candidate 3) owns;
that is the R4 phase-closing condition's second half and is joint with
candidate 3, recorded below rather than silently absorbed.

## R1h — state applicability

**N/A.** This is a write/serialization surface, not a physics-gated one: no
clearance, creepage, thermal, or current-density margin is computed, asserted,
or relied upon anywhere in the module (the isolation-slot geometry is
mechanical cutout placement, not a margin), so the R24 state gate has nothing
to attach to.

## Induction applicability

**Mathematical induction is not applicable to this module.** Nothing here is
recursive over a size parameter whose correctness depends on that parameter:

- `path_to_segments` / `path_to_vias` iterate caller-provided coordinates;
  each pair's rendering is independent of the path's length (the only
  size-coupled behavior, `simplify_path`, removes collinear waypoints by a
  fixed local rule — an induction on the "keep/keep-or-drop" decisions would
  restate the loop).
- `extract_pad_centers`, `generate_connector_segments`,
  `state_to_placements`, `write_placements_plan`, `strip_routing_plan`, and
  the remaining plans iterate collections with per-element operations
  independent of collection size.
- The dedup passes (via dedup, connector endpoints) are keyed by fixed
  rounding functions with first-wins semantics — no size-parameterized
  invariant.

Per the plan's R1e, a **structural proof** is recorded instead.

## Structural proof

**Claim (bit-identical parity).** For every migrated entry point, the Rust
kernel's output — or the output file of the shim that applies the kernel's
plan — is bit-identical to the pinned pre-migration Python implementation
(`packages/temper-placer/tests/io/test_kicad_write_rust_differential.py`).

*Proof by structural cases.*

1. **Rounding.** `py_round_ndigits` reproduces CPython's decimal-aware
   `round(x, ndigits)` by rounding the EXACT rational `x * 10^ndigits` in
   integer arithmetic (mantissa/exponent decomposition, `5^ndigits` scaling,
   exact half-to-even shift). The multiply-then-round shortcut is provably
   wrong: `2.675 * 100.0 == 267.5` exactly while `round(2.675, 2) == 2.67`
   (the exact binary value sits just below the tie). A naive port silently
   shifts every `.5`-tick via-dedup key by one 1e-3 mm unit. Bounded: exact
   for `|x * 10^ndigits| < 2^53` (all real board coordinates; beyond that the
   correctly-rounded f64 of the exact rounded rational may differ from
   CPython's parse-back in double-rounding edge cases — unreachable from
   mm-scale geometry). `py_round_ties_even` (round-to-int) is exact: for the
   integer case the f64 value IS the value being rounded.

2. **Float operation order.** Rotation is R(-theta) with the Python
   operation order preserved (`x * c + y * s`, `-x * s + y * c`); `radians`
   is `x * (PI / 180.0)` with `PI` the same double as `math.pi`, so the
   compile-time constant equals Python's runtime division and the multiply is
   the same IEEE op. `grid_to_world` preserves `((origin + cx*cs) + cs/2)`.
   `py_mod` reproduces float `%` (C `fmod` then adjust to the divisor's
   sign): a negative `(rotation_deg + offset)` would otherwise land in the
   wrong quadrant.

3. **Dedup keys.** `export_route_plan` dedups vias on
   `(round(x,3), round(y,3), sorted(layers))` — first wins, insertion order
   preserved, keys compared by f64 equality (so `-0.0` and `0.0` are the same
   key, matching Python tuple equality/hash). `export_board_state_plan` uses
   `via_dedup`'s `round(x/0.001) * 0.001` — the DIVISION then multiply is
   preserved (not `* 1000.0`, a different IEEE rounding).

4. **Ordering is pinned, not inherited.** Pad centers, net maps, placements,
   connectors and warnings all preserve the Python dict/list iteration order
   of the object being read; iteration always walks the Python object's own
   order (PyDict insertion order), never a `HashMap`. The connector-endpoint
   set in `generate_connector_segments` is a REAL Python set (built in the
   same interpreter, in the same insertion order as the verbatim oracle), so
   its iteration order IS CPython's hash-table slot order — bit-exact by
   construction; the exact-distance tie-break differentials pin the case
   where a first-appearance Vec would pick the other endpoint.

5. **Truthiness and absence.** Python truthiness is reproduced where
   load-bearing: `path.cells`/`segments`/`coordinates` falsy fall through,
   `net_name`/`net` falsy resolve to `"unknown"`, `trace_widths` falsy takes
   the default, `explicit_vias` falsy falls back to inferred vias,
   `attributes` falsy skips center-offset extraction, an empty string
   `Reference` falls through the reference lookup. A `None` pad `position`
   (pads without an `at` token) is the one documented divergence: the pinned
   Python raises `AttributeError`, the kernel reads `(0, 0)` — out of the
   input space of every real board (see Documented deviations).

6. **`bool`-vs-`int`.** `placements_to_json` passes each `x`/`y`/`rotation`
   value through as the SAME Python object (no float coercion), so an int
   stays an int in the JSON dict — type parity with the pinned Python.

## Boundaries kept on the Python side (and why)

Applying PR #688's `yaml.safe_load` judgement: a kernel is kept across the
boundary when reimplementing it would be a *behaviour change* rather than a
port.

- **kiutils board I/O and item construction** — `KiBoard.from_file` /
  `board.to_file` and the `Segment`/`Via`/`Zone`/`GrLine`/`GrRect`/`GrText`/
  `Position` constructors stay in the shims, along with the per-item
  try/except that reports kiutils construction failures (zone/slot/trace
  warnings). A byte-identical full-board serializer replacing
  `board.to_file` requires the shared sexpr board model the parse candidate
  owns; the R4 "kiutils leaves product code" condition is joint with
  candidate 3 and not closed by this candidate alone.
- **numpy extraction** — `state.positions[i]` indexing, `state.to_discrete()`
  and `np.argmax` stay in the shims (the phase plan declines to assume a
  numpy-interop dependency; the DSN candidate's boundary note). The
  per-component math on the extracted values is Rust.
- **`validate_output_pcb`** — a kiutils-read validation helper whose entire
  purpose is exercising `KiBoard.from_file`; kept whole in the shim.
- **`strip_routing_preserve_nets`** — composition + net-assignment
  verification over kiutils pad objects; kept in the shim (the
  classification kernel it wraps is Rust).

## Documented deviations and bounds (per R1, recorded here)

1. **A `None` pad `position` in `extract_pad_centers`** reads as `(0, 0)`
   where the pinned Python raises `AttributeError`. Pads without an `at`
   token are outside the input space of every real board; recorded rather
   than defended.
2. **`round(x, ndigits)` bound** — see the rounding proof (item 1).
3. **`PlacementUpdate.x/y/rotation` are f64** — a constructor call with an
   int coerces to float. All production construction sites produce floats
   (`float(positions[i]) + origin`, `float(indices[i]) * 90`), and
   `placements_to_json` passes the stored value through without re-coercion.
4. **`__module__`/repr of the result pyclasses** differ from the dataclasses
   (`temper_io_types` vs `temper_placer.io._write_types`). The repr DIGITS
   match — Rust's `{:?}` for f64 uses the same shortest round-trip algorithm
   as Python's `repr(float)` — but the FORMAT diverges at three boundaries
   (verified 2026-08-04, Rust 1.92 `{:?}` vs CPython `repr`):
   `|x| >= 1e16` renders `1e16` where Python renders `1e+16` (no exponent
   sign); `|x| <= 1e-5` renders `1e-5` where Python renders `1e-05`
   (exponent not zero-padded); NaN renders `NaN` where Python renders `nan`.
   `-0.0` is NOT a divergence: Debug prints `-0.0` (the `-0` form belongs to
   Display, which the repr never uses), so it matches Python. It is reachable
   in principle, though: `py_mod(-360.0, 360.0)` returns `-0.0` (kernel unit
   test `py_mod_takes_divisor_sign`), so `state_to_placements` can emit a
   `-0.0` rotation — placement coordinates are mm-scale and rotations are
   multiples of 90 from quantized indices, so practical exposure is nil.
   None of the four pyclasses' reprs is asserted anywhere in the
   differential (`_leaf` canonicalizes floats via `float.hex()` and
   `_canon_result` reads result fields, never `repr`).
5. **`float(str)`** parses via Rust `str::parse::<f64>()` (IEEE-correctly
   rounded like CPython; the plan's Q2 assumption). Python's underscore
   literals (`float("1_000")`) are not accepted — unreachable from JSON
   round-trip data.
6. **An object without `.width` passed as a write-path via** (e.g. an
   `export_types.TraceVia` where a `core.board.Via` belongs) is read as
<<<<<<< HEAD
   `0.0` by the kernel (emitting a size-0 via) — but the pinned Python's two
   via-reading paths diverge, so the divergence is path-dependent:
   - **`write_routes_to_pcb`** (`_write_tracks_py_oracle.py`) accesses
     `via.width` inside its per-via `try/except` (the `Via(... size=via.width
     ...)` construction is in `try`), so a missing `.width` is caught,
     warned (`"Failed to add via at ..."`) and the via is **skipped**. The
     kernel (`write_routes_plan`) reads `get_attr_f64(.., "width", 0.0)` and
     emits the size-0 via instead.
   - **`export_board_state`** (`_kicad_exporter_py_oracle.py`) accesses
     `v.width` in a bare list comprehension
     (`TraceVia(net=v.net, position=v.position, size=v.width, ...) for v in
     all_vias`) with no `try/except`, so the `AttributeError` **propagates
     and aborts the whole export**. The kernel (`export_board_state_plan`)
     reads `0.0` and emits the size-0 via.
   The write path's real input type always carries `.width`; both
   divergences are confined to out-of-domain inputs.
7. **`get_footprint_reference` str-coerces a non-string
   `properties["Reference"]`** (`ref_.str()` at the dict path) where the
   verbatim oracle returns the raw value, changing dict-key matching
   downstream. The kernel's return type is `Option<String>` — the reference
   feeds `format!` warnings and the plan-tuple refs at three call sites — so
   raw pass-through would restructure the pinned plan contract. No kiutils
   footprint produces a non-string Reference; recorded rather than defended.
8. **`write_routes_plan` / `export_board_state_plan` coerce route/via
   coordinates and widths to f64** where the oracle forwards the raw values
   into `Position(...)`: an int coordinate renders "3" in the oracle's
   kiutils sexpr and "3.0" here. `write_zones_plan`'s pts pass through raw
   (fixed — the int-coordinate zone differential pins it), but the
   routes/board-state specs carry f64s via `get_xy`/`get_attr_f64` and the
   `PyTraceSegment`/`PyTraceVia` pyclasses have f64 fields shared with the
   Python `export_types` surface — raw pass-through would change the pyclass
   schema. All production inputs (BoardState routes/vias) are floats;
   int coordinates only arise from hand-built out-of-domain inputs.
9. **`add_isolation_slots_to_pcb` warning interleaving**: the oracle emits
   per-slot warnings in slot order, interleaving not-found and kiutils
   construction failures; the migration emits all plan (not-found) warnings
   first, then the shim's construction warnings. A GrLine construction
   failure is unreachable for any slot the plan accepted (the plan already
   read and rotated the slot's geometry, so the shim only constructs
   well-formed lines), hence no fixture can reach the mixed case — aligning
   the order would change the pinned plan contract for an untestable path.
   Recorded rather than restructured.
10. **`export_route_plan` requires `explicit_vias` to be a Python `list`** —
   `ev.cast::<PyList>()` raises `ValueError("explicit_vias must be a list")`
   for any other iterable. The pinned Python accepted any iterable
   (`all_vias.extend(vias)` — a tuple works). Unreachable from real routes
   (the router produces lists); recorded rather than defended.
11. **`py_round_ndigits` shift-overflow panic on tiny inputs** — for
   `|x|` small enough that `e + ndigits <= -128` (a subnormal always, or any
   normal `|x| < 2^-78` with the production `ndigits=3`),
   `round_half_even_shift` shifts `1i128` by >= 128 bits, which panics;
   `guarded()` converts the panic to a `PyRuntimeError` (not an abort), where
   CPython returns `0.0`. Unreachable from mm-scale coordinates (via-dedup
   keys are ~1e-3), and inside the documented `|x * 10^n| < 2^53` bound —
   that bound only excludes the TOP end, so it does not cover this tail.

## Review notes (2026-08-04 adversarial review, PR #718)

Recorded, not fixed — each is a thinness or an out-of-domain error-path
change, with the reasoning:

- **Corpus end-to-end thinness**: the corpus A/Bs never exercise
  `generate_connector_segments` on realistic production geometry — the F1
  exact-distance tie lives exactly there (a skeleton-router gap near a pad,
  both endpoints equidistant). The tie-break differentials close the
  determinism gap synthetically, but a production-board connector-generation
  A/B against the oracle remains uncovered and is the natural follow-up.
- **`path_coords` truthiness swallow**: a numpy-array `path.cells` raises
  `ValueError` (ambiguous truth value) in the pinned Python;
  `is_truthy(...).unwrap_or(false)` in the kernel swallows that into falsy
  and silently falls through to the segments/coordinates branch. Real paths
  carry plain cell lists, so the swallow is confined to out-of-domain
  inputs, but it is a genuine error-path change and is recorded here rather
  than claimed as parity.
||||||| parent of 3fbcb673a (fix(wave4): pass-2 review fixes — perf harness oracle import, MR3 vacuity, VERIFICATION deviations)
   `0.0` by the kernel where the pinned Python catches the `AttributeError`
   and skips the via with a warning. The write path's real input type always
   carries `.width`; the divergence is confined to out-of-domain inputs.
=======
   `0.0` by the kernel (emitting a size-0 via) — but the pinned Python's two
   via-reading paths diverge, so the divergence is path-dependent:
   - **`write_routes_to_pcb`** (`_write_tracks_py_oracle.py`) accesses
     `via.width` inside its per-via `try/except` (the `Via(... size=via.width
     ...)` construction is in `try`), so a missing `.width` is caught,
     warned (`"Failed to add via at ..."`) and the via is **skipped**. The
     kernel (`write_routes_plan`) reads `get_attr_f64(.., "width", 0.0)` and
     emits the size-0 via instead.
   - **`export_board_state`** (`_kicad_exporter_py_oracle.py`) accesses
     `v.width` in a bare list comprehension
     (`TraceVia(net=v.net, position=v.position, size=v.width, ...) for v in
     all_vias`) with no `try/except`, so the `AttributeError` **propagates
     and aborts the whole export**. The kernel (`export_board_state_plan`)
     reads `0.0` and emits the size-0 via.
   The write path's real input type always carries `.width`; both
   divergences are confined to out-of-domain inputs.
7. **`export_route_plan` requires `explicit_vias` to be a Python `list`** —
   `ev.cast::<PyList>()` raises `ValueError("explicit_vias must be a list")`
   for any other iterable. The pinned Python accepted any iterable
   (`all_vias.extend(vias)` — a tuple works). Unreachable from real routes
   (the router produces lists); recorded rather than defended.
8. **`py_round_ndigits` shift-overflow panic on tiny inputs** — for
   `|x|` small enough that `e + ndigits <= -128` (a subnormal always, or any
   normal `|x| < 2^-78` with the production `ndigits=3`),
   `round_half_even_shift` shifts `1i128` by >= 128 bits, which panics;
   `guarded()` converts the panic to a `PyRuntimeError` (not an abort), where
   CPython returns `0.0`. Unreachable from mm-scale coordinates (via-dedup
   keys are ~1e-3), and inside the documented `|x * 10^n| < 2^53` bound —
   that bound only excludes the TOP end, so it does not cover this tail.
>>>>>>> 3fbcb673a (fix(wave4): pass-2 review fixes — perf harness oracle import, MR3 vacuity, VERIFICATION deviations)

## Evidence

- **R1a behavioral A/B** — `packages/temper-placer/tests/io/test_kicad_write_rust_differential.py`,
  100 tests: kernel differentials canonicalized leaf-by-leaf (floats as
  `float.hex()`, non-float leaves carrying concrete `type`, numpy arrays as
  `(dtype, shape, tobytes())`), plus full-function A/Bs where both arms write
  through kiutils' `to_file` so byte-identical outputs are equivalent to
  identical board mutations (uuid4 patched deterministically for
  item-creating paths). Covers the R(-theta) rotation convention, the
  decimal-aware round-half-to-even via-dedup discriminator, the pad-body
  reorientation class (#374), preserve-unmatched warnings, zone fill
  clearing, the connector exact-distance tie-break (both insertion orders),
  the duplicate-ref last-wins center-offset dedup (with cross-kernel
  consistency), the explicit-empty-net-map no-rebuild rule, the
  `validate_4_layer_output` exact decision strings (warn/raise/no-layers/ok),
  the placements_from_json error paths (KeyError / ValueError message), the
  int-coordinate zone pass-through, and corpus end-to-end strip/placement
  A/Bs.
- **R1b performance A/B** — `benchmarks/perf_ab.py`, entry
  `("kicad-write", "state_to_placements")`, wired to
  `scripts/pr_perf_compare.py`'s record shape with an in-harness parity
  assertion. I/O-shaped no-regression arm; no speedup claimed (measured
  locally 0.85×; the baseline row must come from CI given the ~11%
  darwin/linux platform bias).
- **R1c properties** — `packages/temper-placer/tests/io/test_kicad_write_pbt.py`:
  6 properties (P1-P6), each with a vacuity guard / discriminator test.
- **R1d metamorphic relations** — MR1 (snap translation invariance, integer
  coords keep distance comparisons exact), MR2 (simplify_path index-set
  invariance under integer scaling — the cell-center affine map is asserted,
  not just the count), MR3 (rotation wraparound mod 360, multiples of 90 are
  exact), MR4 (unmatched->matched monotonicity of write_placements_plan),
  MR5 (zone-removal monotonicity); each paired with a discriminating-check
  test proving it breakable.
- **R1f TDD** — the differential was demonstrated RED twice: before the
  kernels were registered (the shim's import of a not-yet-registered
  `temper_io_types` name failed collection with `ImportError`) and eight
  times during the mutation campaign.
- **R1g Rust practices** — no `unwrap`/`expect` outside tests;
  `catch_unwind` at every pyo3 boundary (`guarded()`); borrows preferred on
  the hot path; `cargo clippy --all-features --all-targets -- -D warnings`
  clean.
- **Anti-vacuity** — 8 mutations applied to the Rust, rebuilt, and re-run;
  all 8 caught. One initially SURVIVED (via-dedup removal: the first test's
  vias sat at distinct positions, so dedup was vacuous) and was closed by
  tightening the differential — a route flipping F.Cu→In1.Cu→F.Cu at the
  same grid cell, whose two transitions collide on the dedup key. See the PR
  body for the table.
