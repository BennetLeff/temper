<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 dirty=true (all measurements in this document were taken against a worktree built on top of this commit -- fix/board-schematic-resync's tip when this branch was cut -- with this PR's own diff applied on top, prior to that diff itself being committed) -->

---
title: "kw_boundary_match_py: duplicate pyo3 registration, empirically resolved"
date: 2026-08-13
status: fixed
---

# `kw_boundary_match_py` was registered twice in `temper-geometry` — here is what Python actually got

## 1. The headline answer, measured

**`via_clearance.rs`'s implementation wins today, on `origin/fix/board-schematic-resync`
(base `a3fbaff37`).** Not inferred from `lib.rs`'s call order (though that
order — `via_clearance::register(m)` runs *after*
`trace_width_assignment::register(m)`, lines 343/346 — predicts exactly this)
but **empirically confirmed** by importing the built extension and probing a
case where the two implementations provably diverge:

```
$ .venv/bin/python -c "
import temper_geometry as tg
print(tg.kw_boundary_match_py('_X', ['_']))
"
True
```

Why this probe distinguishes them: the keyword `"_"` strips (via
`strip_suffix('_')`) to the empty string. `trace_width_assignment.rs`'s
(now-deleted) `kw_boundary_match_impl` had an explicit `if k == 0 { continue }`
guard — an empty keyword never matched, always contributing `false`.
`via_clearance.rs`'s `word_bounded` has no such guard: `"".starts_with("")` is
always `true`, so it matches whenever the char immediately following a
candidate boundary position is itself `_` or a digit. `"_X"` against `["_"]`
returns `True` under `via_clearance`'s algorithm and `False` under
`trace_width_assignment`'s. The built extension returned `True`:
**`via_clearance`'s implementation was live; `trace_width_assignment`'s own
`kw_boundary_match_py` registration, its own `kw_boundary_match_impl`, and
its own passing Rust unit tests for that function were all dead code**,
never reachable through the shared pyo3 name from the moment both
`register()` calls landed in the same `#[pymodule]`.

## 2. Blast radius — narrower than the shadowing alone suggested

Two things are true simultaneously, and both matter:

**(a) The double registration is a real, confirmed defect independent of any
hyphen question.** pyo3's `PyModule::add_function` is a plain `setattr`; it
does not warn, error, or print on a name collision. This class is invisible
to `cargo build`, `cargo test`, `maturin develop`, and
`scripts/check_stale_extensions.py` (certifies the `.so` is *fresh*, not that
each exported name is backed by exactly one implementation). It is
specifically invisible to `scripts/check_unwired_kernels.py` — a different,
complementary gate — because that gate's `registered_symbols()` scan calls
`dict.setdefault()` when recording `python name -> defining file`: it keeps
whichever registration it happens to see first and never notices a second
one exists. Every differential/unit test for either implementation kept
passing, because each test calls the *same* shadowed name and gets whichever
implementation currently wins.

**(b) But the shadowed symbol itself carries near-zero live blast radius.**
Grepping every non-test Python caller of `temper_geometry.kw_boundary_match_py`
finds exactly two:

- `clearance_engine.py::_kw_boundary_match` (line 125) — **not called by
  anything in production.** `clearance_engine._net_class_to_voltage_class`
  (the function whose docstring literally frames it as "the reference this
  kernel consolidates") calls `net_class_to_voltage_class_py` directly, a
  *separate* pyo3 export that internally uses `via_clearance::kw_boundary_match`
  as a plain Rust function call — never through the pyo3 dispatch table. This
  wrapper is vestigial.
- `trace_width_assignment.py::_kw_boundary_match` (line 41) — also not called
  by production code. `trace_width_assignment._determine_trace_width` calls
  `determine_trace_width_py` directly, which (pre-fix) used its own private
  `kw_boundary_match_impl` — again, never through the shadowed pyo3 name.
  This wrapper is exercised only by
  `test_spatial_drc_cluster_rust_differential.py`'s direct differential test.

**Neither of the two real, live, net-name-driven classification paths in this
codebase —`net_class_to_voltage_class_py` (feeds IEC 60335-1 creepage/
clearance classification) or `determine_trace_width_py` (feeds trace-width
assignment) — was ever reached through the shadowed `kw_boundary_match_py`
symbol.** Each calls its own crate-private matcher function directly. This
means: **fixing the double registration, by itself, changes 0 of the 162
real net names' classification or trace-width outcomes.** That is a
measured fact, not an assumption — verified before and after the fix (§4).

This does **not** make the double registration a non-issue. It is still a
real defect (two implementations under one name is inherently unsafe: the
next person to add a *third* caller of `kw_boundary_match_py` gets whichever
one wins by registration order, with no signal that a choice was even made),
and per PR #319f564f5's own defect-multiplier audit (finding #4, "flagged,
not fixed... needs its own Rust rebuild+test cycle") it was already
identified and explicitly deferred pending exactly this work.

## 3. Board-wide simulation: what changes, what doesn't

All 162 real net names from `elec/build/default.net` (`make netlist`,
digest `8cfd715e60a3…`); 85 of 162 contain a hyphen (52.5%, matches the
originating report).

**`net_class_to_voltage_class_py` (the IEC 60335-1 creepage/clearance path)
— 0 of 162 nets change, hyphen-widened or not, before or after this fix.**
Even simulating what a hyphen-as-boundary widening would do (`s/-/_/g` on
every net name, re-classify, diff) finds **zero** net names where it would
matter — none of the 8 keywords this function's callers use
(`HIGH_VOLTAGE`/`HV`/`MAINS_240V`/`MAINS`/`AC`/`MAINS_120V`/`LOW_VOLTAGE`/
`LV`/`POWER`) happen to sit adjacent to a hyphen in any of this board's real
net names in a boundary-relevant position. This corroborates PR #1174's own
independent finding (`clearance_engine.py`/`via_clearance.rs` audited "zero
live net-name exposure") — re-verified here from scratch, not assumed,
because `_net_class_to_voltage_class`'s only production caller
(`clearance_check._classify_net_class` → `get_clearance`) passes one of the
four fixed labels `HV`/`GND`/`POWER`/`SIGNAL`, never a raw net name, so this
0-of-162 result was never going to surface a live DRC/creepage change no
matter how the boundary is drawn.

**`determine_trace_width_py` (trace-width assignment) — 3 of 162 nets DO
change under a hyphen-widened boundary, and this path IS live (called with
real net names for every routed net):**

| net | narrow (today, unchanged by this PR) | widened (`-` == `_`) |
|---|---|---|
| `hb-gnd` | 0.127 mm, "Standard signal trace" | 0.508 mm, "Power net requires wider trace for current capacity" |
| `hb.gate_hs-vdd` | 0.127 mm, "Standard signal trace" | 0.508 mm, "Power net requires wider trace for current capacity" |
| `hb.gate_ls-vdd` | 0.127 mm, "Standard signal trace" | 0.508 mm, "Power net requires wider trace for current capacity" |

`hb-gnd` is the same half-bridge low-side return net PR #1145's evidence
flags as a creepage miss under a *different* matcher family
(`temper_io_types::placer_core::netclass`) — here, under
`trace_width_assignment.rs`'s own boundary logic, it is independently
under-provisioned for current capacity: assigned the thinnest (default
signal) trace width instead of the power width its current-carrying return
path needs.

**This PR does not widen this boundary, and does not touch this 3-net
result**, for two reasons, both dispositive on their own:

1. **Scope discipline matching #1174's own precedent.** #1174's evidence
   doc explicitly audited `trace_width_assignment.rs` and declined to widen
   it: *"this function assigns trace width, not clearance/creepage — it
   does not decide whether a violation is reported, which is this task's
   explicit scope. Not fixed here."* This task's hard constraint is "do not
   duplicate or revert #1162/#1174" — the substance of that constraint is
   staying inside the reasoning those PRs already established, not just
   avoiding their literal diffs. Widening trace-width's boundary is a
   real, worthwhile, SEPARATE follow-up; bundling it into a duplicate-
   registration fix would conflate two different defect classes in one PR.
2. **`via_clearance.rs`'s own boundary is frozen by a byte-exact oracle
   pin** (`test_via_clearance_tier2_rust_differential.py`'s
   `_ORACLE_PIN_SHA = "f1ffc013"`, mechanically enforced by
   `test_oracle_is_verbatim_copy`). Since this PR consolidates the pyo3
   export onto `via_clearance`'s implementation (§5), widening it here would
   both violate that pin AND reintroduce the exact "-line" SELV/"COIL"
   relay-drive over-match risk #1162/#1174 already fought off elsewhere —
   with (per §3) zero DRC/creepage benefit to show for it.

**Flagged, not fixed: the live 3-net trace-width defect above is real and
independent of this PR's scope** (current-carrying-capacity risk on a
half-bridge return path, not a creepage/clearance violation) — reported
here per this task's own instruction to report every classification
delta honestly, exactly as #1174 flagged its own out-of-scope findings
rather than silently absorbing or hiding them.

## 4. Verification that the fix is a pure consolidation (no behavior change)

Differential test written and run against the ACTUAL built extension,
comparing `via_clearance::kw_boundary_match` (the pyo3-exported winner)
against a faithful line-by-line port of `trace_width_assignment::
kw_boundary_match_impl` (the shadowed loser), across:

- 972 (real net name × real production keyword set) pairs — **0 mismatches**
- 2028 synthetic hyphen/underscore-substituted variants — **0 mismatches**

Only a *synthetic* edge case (a keyword that strips to the empty string,
`"_"`) diverges — confirmed to never occur in any real caller's keyword
list. Consolidation is therefore provably behavior-preserving for every
input either implementation was ever actually invoked with.

Post-fix, re-run against the rebuilt extension: `determine_trace_width_py`'s
3-net hyphen delta (§3) is **byte-identical** before and after this PR — as
expected, since `determine_trace_width` now calls
`via_clearance::kw_boundary_match` (behaviorally identical to the deleted
`kw_boundary_match_impl`) instead of a second, independent implementation.

## 5. The fix

**Consolidated to one Rust implementation and one pyo3 export**, per this
task's stated preference ("prefer consolidating to one, unless they
genuinely differ in intent" — they don't; they're independent
reimplementations of the identical predicate, exactly the copy-paste
pattern PR #319f564f5's audit named this incident as an instance of):

- `via_clearance.rs::kw_boundary_match`/`word_bounded` is now the sole
  implementation. Unwidened — see §3.
- `trace_width_assignment.rs`'s private `kw_boundary_match_impl` is deleted.
  `determine_trace_width` now calls `crate::via_clearance::kw_boundary_match`
  directly (same-crate, `pub fn`, zero new coupling across the pyo3
  boundary).
- `trace_width_assignment.rs`'s `#[pyfunction] kw_boundary_match_py` and its
  `wrap_pyfunction!` registration are deleted outright. The sole
  `kw_boundary_match_py` now registered is `via_clearance.rs`'s.
- Zero Python changes. `clearance_engine.py`/`trace_width_assignment.py`
  both already called `_tg.kw_boundary_match_py(...)` — a name, not a
  module path — so consolidating which Rust file answers for that name
  needed no change on the Python side at all.
- Rust unit tests that exercised `kw_boundary_match_impl` now exercise
  `via_clearance::kw_boundary_match` at the same call sites, proving the
  delegation preserved every pinned case.

## 6. The gate

`scripts/check_pyo3_duplicate_registration.py`: per crate, BFS from every
`#[pymodule]` entry point through every `<path>::register(m)` call
(transitively), collecting every `wrap_pyfunction!`/`add_class::<>` site,
resolving `#[pyo3(name=...)]`/`#[pyclass(name=...)]`/`#[pyfunction(name=...)]`
renames PER DECLARING FILE (not merged crate-wide by bare identifier — see
below), and failing on any Python-visible name registered from more than one
distinct site within the same pymodule. Reused
`check_stale_extensions.discover_crates` for crate enumeration rather than
writing a second one (would have been exactly this incident's own shape, one
level up).

**Caught its own would-be false positive during development**, and stayed
that shape until fixed rather than being weakened: an early version merged
`#[pyclass(name=...)]` renames by bare Rust identifier across an entire
crate (mirroring `check_unwired_kernels.py`'s own documented, deliberate
choice for a *different* reason). Run against the real repo, it flagged
`temper-drc-rs`'s `TypedConstraintSet` as a duplicate — but
`drc_marshal.rs::ConstraintSet` (renamed to `TypedConstraintSet`) and
`drc_contracts.rs::ConstraintSet` (not renamed, its own real Python name is
the bare `ConstraintSet`) are two unrelated types that merely share a local
Rust identifier in different modules. Fixed by resolving renames per
declaring file, falling back to an unambiguous cross-file match only when
the current file does not itself declare the identifier (the legitimate
`#[pyclass(name=...)]`-declared-in-one-file / `add_class` invoked from
another shape, e.g. `PyDsnCircle`/`DSNCircle`). Regression test:
`TestRenameResolution::test_same_bare_name_different_files_one_renamed_is_not_a_false_positive`.

Verified before AND after the fix:

```
$ .venv/bin/python scripts/check_pyo3_duplicate_registration.py     # BEFORE (trace_width_assignment.rs swapped back to its pre-fix content)
FAIL: duplicate pyo3 function/class registration
DUPLICATE_REGISTRATION  temper-geometry::temper_geometry::kw_boundary_match_py
    .../via_clearance.rs:485  fn kw_boundary_match_py
    .../trace_width_assignment.rs:113  fn kw_boundary_match_py
EXIT=3

$ .venv/bin/python scripts/check_pyo3_duplicate_registration.py     # AFTER (this PR's tree)
OK: 10 #[pymodule] unit(s) across 10 crate(s), 666 registration(s) total, 0 duplicate(s).
EXIT=0
```

Registered in `gate_input_registry._CI_SCRIPT_SURVEY` and wired into
`.github/workflows/python-tests.yml` alongside `check_unwired_kernels.py`
(same job, unconditional — parses `.rs` source text only, no built
extensions needed). 13 tests in
`scripts/tests/test_check_pyo3_duplicate_registration.py`: clean single-file
and multi-file (transitive `register()` delegation chain) trees pass; the
exact `kw_boundary_match_py` incident shape (two files, same fn name, same
pymodule) is caught and named with both sites; a duplicate `add_class` is
caught the same way; the same Python name reused across two DIFFERENT
crates is explicitly proven NOT a violation; the `ConstraintSet` false
positive (above) has a dedicated regression test; anti-vacuity (zero crates,
zero registrations) fails closed; the real repo, post-fix, is clean.

## 7. Verification summary

- `cargo test --manifest-path packages/temper-geometry/Cargo.toml --lib`:
  8389/8389 pass (0 regression from the pre-fix 8389/8389 baseline count —
  same total, `kw_boundary_match_cases` now exercises
  `via_clearance::kw_boundary_match` at the same call site).
- `cargo test` for `temper-design-bundle` and `temper-drc-rs` (both have a
  real path dependency on `temper-geometry`): 33/33 and 3312/3312 pass.
- `cargo clippy --lib --features python -- -D warnings`: clean for
  `temper-geometry`, `temper-design-bundle`, `temper-drc-rs`.
- `make venv-isolate` → `scripts/check_stale_extensions.py`: **PASSED,
  10/10 fresh**, before this branch's edits and after every rebuild in this
  session (`Compiling temper-geometry`/`temper-design-bundle`/`temper-drc-rs`
  lines confirmed present each time, per AGENTS.md's "test the actually-
  built extension" requirement).
- `scripts/check_venv_integrity.py`: PASSED, 18/18, throughout.
- `pytest packages/temper-placer/tests/router_v6/test_via_clearance_tier2_rust_differential.py
  packages/temper-placer/tests/router_v6/test_spatial_drc_cluster_rust_differential.py`:
  67/67 pass.
- `pytest packages/temper-placer/tests/router_v6/ -k "clearance or trace_width or creepage"`:
  796 passed, 3 skipped, 15 xfailed (pre-existing, unrelated).
- `scripts/gen_wasm_test_registry.py --crate temper-geometry --check`: up to
  date, no regen needed (test function names unchanged, only their bodies'
  delegate call target changed).
- `packages/temper-placer/tests/validation/test_gate_input_registry.py`:
  19/20 pass; the one failure
  (`test_every_invoked_ci_gate_script_is_registered`, missing
  `check_router_clearance_floor.py`/`check_wasm_covered.py`) is **confirmed
  pre-existing** on the unmodified base commit (`a3fbaff37`) — the workflow
  already referenced both scripts without a survey entry before this branch
  touched anything; not caused by, and not fixed by, this change.
- `git status --porcelain` / `git grep -l "^<<<<<<< "`: clean throughout.

## 8. What this PR does NOT do

- Does not widen any hyphen boundary anywhere (§3's reasoning).
- Does not touch `pcb/temper.kicad_pcb`, any clearance/creepage/DRU
  threshold, or any ratchet ceiling.
- Does not rename any net in `elec/src/**`.
- Does not duplicate or revert #1162, #1174, #1145, #1164, or #1165 — none
  of those commits are in this branch's ancestry (`origin/fix/board-
  schematic-resync`); this PR stays inside the narrow surface those PRs'
  own reasoning already settled for `kw_boundary_match_py` specifically.
- Does not fix the live, real, flagged `determine_trace_width_py` 3-net
  trace-width defect (§3) — reported, not silently absorbed, matching
  #1174's own pattern for genuinely out-of-scope findings.
