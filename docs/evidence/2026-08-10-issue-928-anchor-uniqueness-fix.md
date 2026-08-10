# Issue #928 fix — R13 anchor uniqueness: re-scanned fixpoint replaces the x_max clamp (2026-08-10)

<!-- provenance: commit=9d1777705cb3656f5c941596b56f3f6f99a7d227 dirty=false (fix recorded at this commit; measured after the rebuilt extension and full physics sweep) -->
<!-- provenance: worktree=<wt-anchor>, branch=fix/anchor-uniqueness-928 -->

**What this is.** The root-cause record and behavioural change note for
the `test_p6_anchors_are_unique` flake (two devices coinciding at
(40.0, 21.0)) and the fix in
`packages/temper-thermal/src/thermal_potential.rs` +
`packages/temper-placer/tests/physics/_thermal_potential_py_oracle.py`.

## Symptom

`test_thermal_potential_rust_pbt.py::test_p6_anchors_are_unique` (R13:
no two anchors within 0.1 mm) flaked on `board=(0, 0, 40, 21)` with
`devices=[('Q0',0.0),('Q1',0.0),('Q2',1.0),('Q3',0.0),('Q4',1.0)]`:
Q0 and Q3 both landed at `(40.0, 21.0)` — the top-right corner.
Confirmed pre-existing (recorded in the #927 triage note) and reproduced
byte-identically on `main` before this fix through both the Rust-backed
module and the pinned pure-Python oracle.

## Root cause

`enforce_unique_positions_with` (`_enforce_unique_positions`) was a
single pass over every pair (i < j): when `dist < tolerance_mm` it moved
`anchors[j]` to `min(xj + offset_mm, x_max)`.

1. **The x_max clamp merges anchors.** When `xj` sat at `x_max`, the
   clamp put the nudged anchor back exactly on top of an anchor already
   at `x_max` — `min(40.0 + 0.5, 40.0) == 40.0` — and the pair was never
   re-checked.  That is the (40.0, 21.0) coincidence.
2. **Single-pass blindness.** The scan visited each pair once, so a
   nudge that landed on a third anchor was never revisited.

## The fix (both arms, bit-identical)

Re-scan every pair until a full pass makes no move.  Each move places the
later anchor on the first x-position on its row — `+offset_mm` outward,
then `-offset_mm` inward, never beyond the board — that is at least
`tolerance_mm` from EVERY other anchor (`search_free_x` in Rust /
`_find_free_x` in the oracle).  Because every move lands clear of all
anchors, a move never re-creates a violation, so termination is
guaranteed without an iteration budget; a pair whose row is saturated is
left as-is rather than clamped onto an anchor.  The old `py_min` helper
(only used by the old nudge) was deleted.

For the flake input the second coincident device now lands at
`(39.5, 21.0)` — the inward step that the old clamp made impossible.

## Why the differential oracle was re-pinned, not left alone

The R1a differential's contract is bit-parity between the Rust kernel and
the pinned pre-migration oracle.  The old coincident-anchor behaviour was
shared bit-for-bit by both arms — a migration-drift differential cannot
catch a bug both arms got right together.  This is the documented
exception to `_thermal_potential_py_oracle.py`'s "verbatim" header: the
oracle was updated in lock-step with the Rust kernel and the differential
now asserts the two arms agree on the NEW behaviour (110 tests, including
the two BMC-exhaustive sweeps).  The behavioural change is documented in
the differential test's module docstring and in
`packages/temper-thermal/VERIFICATION.md`.

## Verification

- `cargo test -p temper-thermal` — 191 passed (3 new uniqueness
  regressions: x_max merge, third-anchor collision, two-sided nudge).
- `cargo clippy --all-features --all-targets -- -D warnings` — clean.
- Differential: `test_thermal_potential_rust_differential.py` — 110 passed.
- PBT: `test_thermal_potential_rust_pbt.py` — 34 passed;
  `test_p6_anchors_are_unique` at `max_examples=500` (committed) —
  500 passing examples, 0 failing, run 3× green (0.67–0.70 s each).
- Regression: the exact flake input end-to-end is unique; the
  constructed x_max-clamp and third-anchor cases resolve to distinct
  anchors; P7's nudge clause generalized to whole multiples of
  `offset_mm` (plus a new vacuity guard that a non-multiple off-grid
  anchor is still rejected).

Refs #928
