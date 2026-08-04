# Verification: Wave-4 Phase 2 core contract layer

Scope: `src/placer_core/` — the Rust port of the placer's `core/`
CONTRACT layer (`Rect`, `PinInfo`, `PlacementViolation`, `FabPreset`,
plus the pure kernels of `units`, `net_classification`, `manufacturing`,
`placement_drc`, and `netlist.build_adjacency_matrix`).

This file carries the **R1e** obligation: a structural/inductive
soundness argument for each ported kernel, stating what is proved,
under what assumption, and where the assumption is checked. R1a (the
differential), R1b (perf), R1c (properties), R1d (metamorphic
relations) and the mutation corpus live in
`packages/temper-placer/tests/wave4_phase2/`.

---

## R1e-1 `net_classification`: the regex rewrite is a *language* identity

**Claim.** For every string `s` and every pattern `p` in the seven
declared sets, the Rust matcher accepts `s` iff CPython's
`re.search(rf"(?:^|_){re.escape(p)}(?:$|[\d_])", s.upper())` does.

**Proof (structural, on the position of a candidate match).**

Two rewrites separate the claim from the reference text.

1. `^` → `\A`. Without `re.MULTILINE`, CPython's `^` matches only at
   offset 0, which is `\A`'s definition. Identical, no assumption.

2. `$` → `\z`, with one trailing `\n` deleted from the haystack.
   CPython's `$` matches at exactly two positions: `len(s)`, and
   `len(s) - 1` when `s[-1] == '\n'`. Let `s'` be `s` with a single
   trailing `\n` removed if present.
   * If `s` has no trailing newline, `s' = s` and the two `$` positions
     collapse to one, `len(s) = len(s')`, which is `\z`. ∎
   * If `s` ends in `\n`, then `len(s') = len(s) - 1`, so `\z` on `s'`
     sits at the first `$` position; the second (`len(s)`) is
     unreachable for any pattern, because the character immediately
     before it is `\n`, and the only two things that can precede the
     tail alternation are the pattern's own final character (never `\n`
     — every pattern is ASCII alphanumeric, `+` or `-`) or a `[\d_]`
     match (`\n` is in neither class). ∎

   The deletion cannot destroy a match either: the only characters it
   removes is the final `\n`, which no pattern contains and no `[\d_]`
   accepts.

**Assumptions, and where they are checked.**
* *Every pattern is non-empty and ASCII* — checked by
  `netclass::tests::patterns_are_ascii_and_non_empty`, which fails at
  build time if a future pattern breaks it. (The emptiness case matters:
  the reference's guard is `if p and not p[-1].isalnum()`, so an empty
  pattern takes the *trailing-boundary* branch, not the leading-anchor
  one, and the two branches are **not** equivalent there. `pattern_source`
  reproduces that.)
* *`regex::escape` and `re.escape` describe the same language* — both
  escape a superset of the regex metacharacters and neither changes what
  the pattern matches. Only six patterns contain a metacharacter
  (`+3V3`, `+5V`, `+12V`, `+15V`, `DC_BUS+`, `DC_BUS-`), and all six are
  in the differential corpus.
* *`str.upper()` agrees between CPython and Rust* — both implement the
  full Unicode uppercase mapping including the length-changing cases.
  Checked on `ß` (→ `SS`) and `ı` (→ `I`) in
  `netclass::tests::unicode_case_folding` and across the differential's
  Unicode corpus. **Not proved in general**: see "Not verified" below.

**Order invariance.** `matches_any` is `Iterator::any` over the pattern
list, i.e. a disjunction with early exit. The value of a disjunction is
independent of evaluation order, so the reference's `frozenset`
iteration — whose order is `PYTHONHASHSEED`-dependent for `str` — cannot
change the answer. Not asserted, *measured*:
`test_witness_frozenset_iteration_order_is_hash_seed_dependent` runs the
reference under eight hash seeds, asserts the observed order really does
move (otherwise the test proves nothing) and that the classification
does not. The order is left alone; it is deliberately **not** sorted.

---

## R1e-2 `build_adjacency_matrix`: the update multiset is a permutation invariant

**Claim.** The matrix is independent of the order of each net's pin
list, so the reference's `list(set(...))` — a hash-ordered sequence —
is deterministic despite appearances, and the Rust port's
first-occurrence order produces the same bits.

**Proof (induction on the number of nets).**

*Base.* Zero nets: both produce the all-zero `(n, n)` matrix.

*Step.* Assume the matrices agree after `k` nets. Net `k+1` contributes,
in both implementations, the set `S` of distinct in-range component
indices on that net (the reference by `set()`, the port by a `seen`
bitmap; both compute the same set, since both keep exactly the indices
that occur at least once). Both then enumerate ordered pairs `(a, b)`
with `a` before `b` in *their own* sequence order, and for each perform
two updates: `+= 1` at `(a, b)` and `+= 1` at `(b, a)`.

For any linear order on `S`, the enumeration `a < b` visits each
*unordered* pair `{i, j} ⊆ S, i ≠ j` exactly once. The two updates it
performs are `(i, j)` and `(j, i)` — a set that does not depend on which
of `i`, `j` came first. So the **multiset** of `(cell, +1)` updates
contributed by net `k+1` is `{ (i,j), (j,i) : {i,j} ⊆ S }`, identical
under any order. Distinct cells accumulate independently, and `f32`
addition on a single cell is applied the same number of times, so the
final bits agree. ∎

**Why `f32` and not a `u32` count.** The proof gives equality of the
*number* of `+= 1` applications, not of the value; `f32 += 1.0` stops
advancing at 2^24, so a `u32` count converted once would diverge above
that. Accumulating in `f32`, as the reference's `np.float32` array does,
makes the values agree by construction. Pinned by
`adjacency::tests::f32_accumulation_saturates_exactly_like_numpy`.

**Last-wins on duplicate refs.** `ref_to_idx` is a dict comprehension,
so a repeated `ref` maps to its final index. `HashMap::insert` in
enumeration order reproduces this. Pinned by
`duplicate_component_refs_resolve_to_the_last_index`.

**Empty netlist.** Deliberately *not* in Rust: `np.array([]).reshape(0, 0)`
is **float64**, unlike the float32 the populated branch returns. The
shim keeps that branch so the dtype contract survives; the differential
asserts it (`test_empty_netlist_dtype_is_float64_not_float32`).

---

## R1e-3 `validate_placement_drc`: the scan is a total function of unordered pairs

**Claim.** The port emits the same violations, in the same order, with
the same messages, and re-attaches the caller's own pin objects.

**Argument (structural).** The reference is a double loop over
`i < j` with no state carried between iterations other than the append
order. The port keeps the identical loop bounds and the identical
`continue` structure, so the emitted sequence is the same subsequence of
the same enumeration. Three float facts make the values bit-exact:

* `radius = diameter_mm / 2.0` — division by a power of two is exact for
  every finite input, and for infinities and NaN it is the identity/NaN.
  Never a rounding, so no libm involvement.
* `dist = sqrt(dx*dx + dy*dy)` — `sqrt` is required by IEEE-754 to be
  correctly rounded, so it is bit-identical to `math.sqrt` on any
  conforming libm; the two multiplies and the add are each single
  correctly-rounded operations in the same order. This is why `sqrt`
  does *not* need `temper-thermal`'s `dlsym` treatment while `exp`/`pow`
  do. Note the reference writes `dx * dx`, not `dx ** 2` — the latter is
  libm `pow` and is *not* reproducible by a multiply.
* the comparisons are `<` on raw `f64`, so a NaN operand makes every
  branch false and the pair yields nothing. Pinned as a witness
  (`nan_coordinate_yields_no_violation_witness`), not "fixed".

**Message formatting.** `f"{x:.3f}"` is `format_fixed`, not Rust's
`{:.3}`: they agree on the digits (both correctly rounded, ties to even)
but disagree on the non-finites (`nan`/`inf` vs `NaN`/`inf`). The
differential includes NaN and infinite coordinates, diameters and
clearances for exactly this reason.

**Object identity.** The pure kernel returns *indices*; the pyo3
boundary re-attaches `pins[i]`, so `violation.item_a is pins[i]` holds
as it did when the reference stored the objects directly. Checked by
`test_placement_drc_returns_the_callers_own_pin_objects`.

---

## R1e-4 `Rect`: the invariant is established at construction and never re-broken

**Claim.** Every reachable `Rect` satisfies `x_max > x_min` and
`y_max > y_min`, and every Python-visible operation reproduces the
frozen dataclass exactly.

**Argument (by construction + immutability).** There is exactly one
constructor path (`#[new]`), and it performs the two `__post_init__`
checks *before* the struct is built, at **Python** comparison level, so
the check is exact for large integers and honours any operand's own
`__gt__`. `from_xyxy`, `from_xywh` and `coerce` all funnel through
`cls(...)` (`coerce` via `cls.from_xyxy`, so a subclass override is
honoured as in the reference). The four fields have no setter and
`__setattr__`/`__delattr__` raise `dataclasses.FrozenInstanceError`, so
no reachable operation can invalidate the invariant afterwards. ∎

**Why the fields hold Python objects.** The reference does **no**
coercion in `__init__` — only `from_xyxy`/`from_xywh` call `float()`. So
`Rect(1, 2, 3, 4).x_min` is the `int` `1` and `.width` is the `int` `2`.
Storing `f64` would change both the value's type and the `repr`. The
struct therefore carries the four originals plus an `f64` view
(`PyRect::data`) for Rust consumers; the `f64` view is lossy above 2^53
and no Python-visible path reads it.

**Pickling — a regression this file initially missed.** A pyclass is
unpicklable by default and the dataclass was not, so `pickle.dumps(board)`
and `copy.deepcopy(zone)` both failed with `TypeError: cannot pickle
'temper_io_types.Rect' object` — reached through `Zone.bounds`. All four
contract types now implement `__reduce__` as `(type(self), (fields…))`,
which reconstructs through `type(self)` so a subclass stays a subclass,
re-runs the invariant check, and preserves field types exactly (an `int`
`Rect` round-trips as `int`). Covered by
`test_rect_survives_pickle_copy_and_deepcopy`,
`test_zone_and_board_survive_pickle_and_deepcopy`,
`test_contract_objects_survive_pickle_and_deepcopy` and
`test_rect_subclassing_still_works`, and by mutants M36–M39.

This is worth recording as a process point, not just a bug: the first
differential was green across 941 assertions while `pickle` was broken,
because nothing in it pickled anything. Behavioural coverage is only as
wide as the operations you think to perform.

**The one measured API delta.** `dataclasses.is_dataclass(Rect)` was
`True`, is now `False`. The visible consequence is that `asdict()` on a
dataclass *containing* a `Rect` no longer recurses into it — it
deep-copies the `Rect` instead of flattening it:

```text
before:  {'bounds': {'x_min': 0.0, 'y_min': 0.0, 'x_max': 1.0, 'y_max': 1.0}}
after:   {'bounds': Rect(x_min=0.0, y_min=0.0, x_max=1.0, y_max=1.0)}
```

Grepped: the repo has four `asdict` call sites (`metrics/physics.py`,
`pipeline/dag_observability.py`, `testing/quarantine.py`,
`validation/results/battery_run.py`) and none is reachable from a
`Rect`. Both shapes are pinned by
`test_rect_is_no_longer_a_dataclass_and_asdict_changes_shape`.

---

## R1e-5 `units`: R24 physical-quantity discipline

Every function here converts or compares a **physical quantity**
(degrees, radians, millimetres, grid cells), so R24 applies.

**Conservative-bound classification.** None of these is an
approximation of a physical model; each is an exact unit conversion, so
the R24 requirement is not "the bound is conservative" but "the
conversion is the *same* conversion". The soundness statement is
therefore an identity, not an inequality, and it is discharged by
bit-exact agreement rather than by an error bound.

**Associativity is the whole content of the claim.** `deg_to_rad` is
`(x * π) / 180`, **not** `x * (π/180)`. Measured on this repo's
interpreter over 200 007 samples: the two disagree on **59 113**
(29.6 %), and `np.radians`/`math.radians` disagree with the reference on
the same 59 113. `rad_to_deg` = `(x * 180) / π` disagrees with
`np.degrees`/`to_degrees` on 51 688 / 200 000 (25.8 %). `to_radians()`
would have been a silent 1-ulp regression on a third of all inputs.
`std::f64::consts::PI` is bit-identical to `np.pi` (`0x1.921fb54442d18p+1`),
asserted in `units::tests::pi_constant_matches_numpy`.

**BMC-exhaustive validation on small N.** `is_valid_layer` and
`is_valid_net_id` are total predicates over a small integer domain; the
differential enumerates `layer ∈ {-2, -1, 0, 1, 2, 3, 4, 5, 7, ±2^31,
2^53, 2^63}` against `max_layers ∈ {0, 1, 4, 8}` — every branch, both
outcomes, plus the unbounded-integer case that an `i64` extraction
cannot represent.

**Post-conversion audit.** `test_p7_mm_to_cell_agrees_and_truncates_toward_zero`
recomputes the quotient in Python and asserts the returned cell index
satisfies `|cell| <= |mm / size|` and `cell == int(mm / size)` — the
audit-after-the-fact that R24 asks for.

**Scope caveat (measured, not assumed).** Only the scalar path is in
Rust. `deg_to_rad`/`rad_to_deg` are annotated `float | Array`, and NEP 50
makes the array result dtype depend on the input dtype — a float32 array
stays float32 and is *computed* in float32 (measured:
`int32 -> float64`, `int64 -> float64`, `float32 -> float32`,
`float64 -> float64`). The shim routes non-scalars to the original,
untouched numpy expression. The scalar test is exact type identity, not
`isinstance`: `np.float64` **is** a subclass of `float`, and using
`isinstance` silently downgraded `np.float64` results to plain `float`
until the differential caught it.

---

## R1e-6 `manufacturing`: CPython's `max` is not `f64::max`

`inflated_clearance` is `max(0.0, nominal - tolerance)` with CPython's
*builtin* two-argument `max`, which keeps its left operand unless the
right compares strictly greater. Measured:

| call | CPython builtin | `f64::max` |
|------|-----------------|------------|
| `max(0.0, nan)`  | `0.0`  | `0.0`  |
| `max(nan, 0.0)`  | `nan`  | `0.0`  |
| `max(0.0, -0.0)` | `0.0`  | `0.0`  |
| `max(-0.0, 0.0)` | `-0.0` | `0.0`  |

With the constant `0.0` on the left the two agree *today*, so writing
`f64::max` would have passed the differential and left a landmine for the
first refactor that swaps the operands. `cpython_max2` spells the
semantics out instead, and `cpython_max_nan_is_left_biased` pins the
disagreement so the distinction cannot be optimised away later.

---

## Anti-vacuity: the mutation corpus

36 source mutants were applied to `src/placer_core/`, one at a time,
each followed by a full rebuild and a full gate run
(`cargo test --lib` + `pytest tests/wave4_phase2/`), then reverted. The
driver was a throwaway script (apply literal `(file, old, new)` edits;
rebuild; gate; revert) run outside the repo, so the durable record is
this section: every mutant is listed below by the exact behaviour it
reverts, which is enough to reconstruct the corpus.

**37 / 40 killed** (36 in the main corpus + 4 added for the `__reduce__`
path once pickling was fixed). The 3 survivors are each accounted for
below; none was closed by weakening a claim.

The four `__reduce__` mutants (M36–M39) all started as survivors and all
four were closed by new discriminating tests: reconstructing through the
concrete class instead of `type(self)` (needed a subclass `copy` test);
coercing the fields to `float`; swapping `PinInfo.x`/`.y`; and dropping
`FabPreset.drill_tolerance_mm` — the last of which survived because all
three named presets leave that field at its default, so the corpus now
includes a preset with every field non-default.

The first run used a pytest-only gate and reported 5 survivors. Two of
them (`M12` "cpython_max2 becomes f64::max" and `M11` "precedence: power
before ground") revealed real gaps rather than real equivalences:

* **M12** was killed by a Rust unit test that the pytest-only gate never
  ran. The gate was wrong, not the mutant — `cargo test --lib` is part
  of the R1 gate set and is now part of the mutation gate too.
* **M11** was a genuine coverage hole: the differential's name corpus
  contained no net name matching *two* pattern sets, so the precedence
  order (ground > power > hv) was never exercised. Ten such names
  (`GND_VCC`, `VCC_AC_L`, `AGND_VDD`, …) were added, plus
  `test_net_classification_corpus_is_not_degenerate`, which now fails if
  the corpus ever loses that property again. M11 is killed.
* **M24** (repr exponent threshold 16 → 17) was a second coverage hole:
  `pyrepr::repr_f64` is reached only through the Rust-built
  `__repr__`s, and no test had put a large-magnitude float into one.
  `test_contract_object_reprs_render_floats_exactly_like_cpython` now
  pushes every `EDGE_FLOAT` through `PinInfo` and `FabPreset`, and
  `test_placement_violation_repr_renders_extreme_floats` through
  `PlacementViolation`. M24 is killed.

### Survivors, with proofs

| mutant | verdict | evidence |
|--------|---------|----------|
| **M18** `radius`: `d / 2.0` → `d * 0.5` | **proved equivalent** | `2.0` and `0.5` are exact powers of two, so both spellings request the correctly-rounded `f64` nearest to the same exact real `d/2` — one rounding each, same result, including subnormals and non-finites. `placement_drc::tests::halving_is_exact_either_way` checks bit equality over every binade (`2^-1074 … 2^1023`, ±, ×1.5) plus 40 000 pseudo-random probes. |
| **M23b** `data[i] += 1.0` → `(data[i] as f64 + 1.0) as f32` | **proved equivalent** | For `x < 2^24` the `f64` sum is exact and the single `as f32` rounding is exactly what `f32` addition does. For `x >= 2^24` both yield `x`. No double-rounding window exists because the addend is exactly 1 and `f64` carries 53 bits against `f32`'s 24. |
| **M23c** count in `u32`, convert once at the end | **proved equivalent over the reachable domain** | The two agree for every cell whose final count is `< 2^24`; the first divergent count is `2^24 + 2 = 16 777 218` (`2^24 + 1` is a tie that `u32 as f32` also resolves down). Reaching it needs one *component pair* to co-occur on 16.7 M nets. The Temper board has **684 nets and 169 footprints** (measured from `pcb/temper.kicad_pcb`), ~4.5 orders of magnitude short, and a differential cannot construct the input — 16.7 M pin lists do not fit in memory. Boundary pinned in `adjacency::tests::f32_accumulation_saturates_exactly_like_numpy`. **This is a bounded claim, not an unconditional one.** |

Two mutants from the first run were withdrawn as invalid rather than
counted: an early `M23` added an unused `counts` vector (a no-op edit,
so "surviving" meant nothing) and was replaced by M23b/M23c above.

### What the corpus covers

Every trap this port is built around has a mutant that reverts it:
the `(x*π)/180` associativity (M01/M02), the fused multiply-add (M03),
Python's `$` before a trailing newline (M06), the leading/trailing regex
anchors (M07/M08/M09), case folding (M10), classifier precedence (M11),
CPython's left-biased `max` (M12/M13), the `<` vs `<=` DRC thresholds
(M15), `.3f` formatting (M16/M27), the SHORT-shadows-CLEARANCE control
flow (M17/M19), adjacency symmetry (M20), per-net dedup (M21), dict
last-wins (M22), the `repr` fixed/exponential threshold (M24/M28), the
`nan` spelling (M25), signed zero (M26), the `Rect` invariant (M29),
`coerce`-by-identity (M30), `isinstance`-vs-exact-type on `np.float64`
(M31), unhashability (M32), division by zero (M33), `float()`-vs-pyo3
coercion (M34), and `Rect` storing `f64` instead of the original objects
(M35).

---

## Not verified — read this before trusting anything above

* **Linux.** Every measurement in this file and in the test suite was
  taken on macOS/arm64 (Darwin 25.5.0, CPython 3.12.13, numpy 2.3.5).
  Nothing here was run on Linux. The kernels avoid the libm-sensitive
  operations (`exp`, `pow`, transcendentals) — only `sqrt` is used, and
  it is IEEE-mandated correctly-rounded — so there is no *known* source
  of cross-platform divergence, but that is an argument, not a
  measurement. Treat CI as the first Linux data point.
* **`str.upper()` in general.** Agreement between CPython's and Rust's
  full Unicode uppercase mappings is checked on a corpus, not proved.
  A locale-independent full mapping is specified by Unicode and both
  claim to implement it, but the two may track different Unicode
  versions.
* **`repr()` of a float across CPython versions.** `pyrepr::repr_f64`
  reimplements `format_float_short`'s decpt thresholds; those are stable
  CPython behaviour but are not a language guarantee.
* **`np.linalg.eigh`** (`compute_eigenvector_centrality`) is *not*
  ported and no parity is claimed for it — it is the host LAPACK, and
  bit-exactness would require linking the same LAPACK build.
