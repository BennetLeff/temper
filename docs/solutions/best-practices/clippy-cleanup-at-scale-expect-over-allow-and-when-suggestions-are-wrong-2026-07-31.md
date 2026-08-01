---
module: temper-placer
tags: [clippy, rust, lint-hygiene, expect-over-allow, bit-identical, pyo3]
problem_type: best_practice
date: 2026-07-31
severity: medium
---

# Clippy cleanup at scale: expect-over-allow, when clippy's suggestion is wrong, and validating the exact gate

## Problem

~60 crates carried `[lints.clippy] unwrap_used/expect_used = "deny"` configs
with a CI gate, but the landed wave-era code was not `-D warnings` clean.
A full hygiene pass had to fix ~150 lint errors across the crates **without
changing any computed value** — several crates have differential/property
tests asserting bit-identical results against Python oracles.

## The conventions that emerged

1. **`#[expect(clippy::lint)]` with an honest `reason` beats `#[allow]`.**
   Unfulfilled expects fail under `-D warnings`, so stale allows get caught;
   the reason string documents *why* the lint is acceptable. Used for
   `too_many_arguments` on pyo3-boundary signatures (mirror the Python
   signature 1:1), infallible invariants (`NormalizedScore::new(0.0)`), and
   proc-macro misuse panics (rustc reports them as compile errors at the
   derive site).
2. **Test-code unwraps/expects get `#[allow(clippy::unwrap_used)]` on the
   `mod tests`** (and `clippy::expect_used` where expects appear) — the
   repo convention, matching router-core's pre-existing style. Integration
   test files get a file-level `#![allow]`.
3. **Byte-parsing `try_into().unwrap()` on `chunks_exact` → `copy_from_slice`
   into a stack array** — infallible, no panic path, and removes the lint
   rather than suppressing it.

## When clippy's suggestion is wrong

Two suggestions were rejected because they would have changed behavior, and
the rejection was justified with `#[expect]` + reason:

- `clippy::manual_range_contains` (`!(0.0..=1.0).contains(&r)` → `r < 0.0 ||
  r > 1.0`): **not equivalent for NaN.** NaN comparisons are all-false
  (original returns `false`), `!contains` returns `true`. The module is a
  bit-exact port of GEOS `segmentToSegment` whose NaN semantics are
  oracle-required.
- `clippy::is_digit_ascii_radix` (`to_digit(10).is_some()` →
  `is_ascii_digit()`): drops Unicode decimal digits (Nd) that the pinned
  Python oracle (`re`'s `\d`, Unicode-aware) matches.

Rule: **a clippy suggestion is a candidate, not a verdict — when the crate
has differential/oracle tests, verify the suggestion is semantics-preserving
before applying it.**

## The "operation will always return zero" investigations

Four findings of this shape (3 in geometry test code, 1 in astar.rs test
code) were all the same pattern: the documented row-major index formula
`row * cols + col` written with `row = 0` (e.g. `validity[0 * 8 + d]`,
`g[0 * 5 + 0]`). None were algorithmic bugs. Rule: **investigate
clippy's "likely not the intended outcome" before assuming it is a bug** —
constant-zero sub-expressions in deliberate index math are common.

## A hidden Rust limitation: you cannot borrow-lookup a tuple-String key

The hot DRC clearance loop allocated `layer.to_string()` per candidate pair
with `layer` loop-invariant. The textbook "look up with a borrowed key"
fix — `HashMap<(usize, usize, String), _>::get(&(i, j, layer))` where
`layer: &str` — **does not compile**: Rust does not provide
`(A, B, String): Borrow<(A, B, str)>` (the tuple `Borrow` impls require
`String: Borrow<&str>`, which does not exist). The safe fix was a
**per-phase accumulator** keyed only by `(usize, usize)` (allocation-free,
same min/first-seen/NaN semantics), merged into the outer
`(usize, usize, String)` map once per distinct pair. Rule: **when a
loop-invariant `String` key is the allocation, restructure the key shape
rather than fighting `Borrow`.**

## Validating the gate before gating

The CI clippy step was extended from 3 crates to all 14 with `--all-targets`.
A spot-check that "looked clean" (message-format grep without `-D warnings`)
missed 55 errors in the four wave-era crates. Rule: **the validation must be
the exact gate command** — `cargo clippy --all-targets --no-deps -- -D
warnings` with zero tolerance — before extending a gate to a crate.

## Related

- `docs/solutions/best-practices/per-workstream-worktree-2026-07-31.md`
- The pyo3 migration itself: `(Self, Base)` tuple returns →
  `PyClassInitializer::from(base).add_subclass(self)`, and
  `#[pyclass(from_py_object)]` opt-in. pyo3's own
  `From<(S, B)> for PyClassInitializer<S>` is literally
  `from(base).add_subclass(sub)`, so the migration is bit-identical by
  construction.
