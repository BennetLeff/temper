# Failure mechanism taxonomy: eight recurring shapes, verified instances

<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** repo-wide survey of one day's worth of fixes (2026-07-26 through
2026-07-27 on `main`), grouped by mechanism rather than by symptom. Every
claim below was checked directly against `git log`/`git show`, the current
tree, or `gh run list` — see "Verification method" and the closing count.

## Why this taxonomy, not a list of bugs

`docs/METHODOLOGY.md` §4 already names six failure classes for a
*validation layer* (Missing, Wrong, Unwired, Vacuous, Wrong threshold,
Silently skipped). Several of the mechanisms below map onto that table
cleanly; several don't, because they aren't about a validator computing the
wrong answer — they're about repo state (a `.gitignore` rule, an allowlist,
a CI concurrency key) drifting from what a person believes it says. That
gap is itself worth naming, and the closing section proposes how.

## Verification method

Every SHA below was checked with `git cat-file -e <sha>^{commit}`; every
file path and line number was checked against the current tree (`afaf9000`,
`origin/main`) and corrected or dropped where it had moved or couldn't be
confirmed, per the brief for this document. Live CI state (mechanism 8) was
checked with `gh run list --workflow=python-tests.yml --branch main`, not
transcribed from a summary. Where a number in the brief this document was
commissioned from didn't match measurement, the measurement is reported and
the discrepancy is called out explicitly rather than silently corrected.

---

## 1. Ignore rule added, files never untracked

**Mechanism:** `.gitignore` rules only affect untracked paths; adding a
rule for a path that's already committed changes nothing; there is no
prompt, warning, or diff that surfaces the mismatch.

**Why it evades detection:** the rule *reads* as fixed the moment it's
committed — `git status` goes quiet for anything not yet tracked, and
nobody diffs the tracked-file list against the ignore patterns to check
whether the rule actually did anything to files it was written to cover.

**Verified instances:**

- **`.DS_Store`** (rule at `.gitignore:64`, confirmed current). **Six**
  files were untracked across two commits on 2026-07-26, not five as
  briefed: `2a525d92` ("repair five more keyword APIs...") drops the root
  `.DS_Store` as an incidental part of an unrelated diff; `27ea74f3`
  ("chore: untrack the remaining four .DS_Store files") drops the other
  five (`components/.DS_Store`, `components/LMR51420/.DS_Store`,
  `components/LMR51420/test_files/.DS_Store`,
  `packages/temper-placer/.DS_Store`,
  `packages/temper-placer/tests/.DS_Store`). **`27ea74f3`'s own title
  undercounts by one** — "four" in the subject line, five files in the
  diff and in the commit body's own list, which explicitly says "five of
  them rode along in the index... the root one went in an earlier
  commit." A live instance of mechanism 2 nested inside a fix for
  mechanism 1.
- **`.hypothesis/`** (rule at `.gitignore:89`, confirmed current). **81
  entries**, all removed in `2a525d92` — verified by exact count
  (`git show 2a525d92 --name-status | grep -c '\.hypothesis'` → 81).
- **`temp_routing_test/`** — **7 files**, confirmed exactly (7 unique
  paths across `2a525d92` and its squash-merge duplicate `866de677`).
  No rule existed before `dd597755` ("chore(gitignore): ignore
  `mfem_mesh/` and `temp_routing_test/` scratch output"), whose own
  comment states the count: "held 7 stale routing logs."
- **Cargo `target/` build output** — **472 files, 131.4 MB**, across
  `temper-dsn-core`, `temper-ipc-core`, `temper-py-bridge`,
  `temper-py-bridge-derive`, confirmed exactly by commit `efd78c0d`
  ("chore: untrack 472 committed Rust build artifacts (131 MB)
  (#357)") and independently re-measured here by summing blob sizes of
  every deleted object in that commit's diff (131.35 MB). **Line number
  corrected**: the commit message cites `.gitignore:114` (true at the
  time it was written); the rule (`packages/*/target/`) is at
  **line 106** in the current tree.

**What mechanically prevents recurrence:** nothing repo-wide.
`scripts/test_root_hygiene.py` exists but only checks a fixed, small set
of root-level filename suffixes (`*.py`, `*.kicad_pcb`, `*.json`, etc.)
against a per-category allowlist — it would not have caught any of the
four instances above, all of which are nested paths outside its scope. No
CI step diffs `git ls-files` against `git check-ignore` output.

---

## 2. Debt paid, ledger never updated

**Mechanism:** a monotonic-shrink allowlist/baseline is supposed to track
outstanding debt, but nothing forces it to shrink when the debt is
actually paid off — an entry stays on the books until a human notices and
removes it.

**Why it evades detection:** the gate that reads the ledger only checks
"is current state ≤ the recorded baseline," which stays true forever once
the underlying code has *improved* past the baseline. Improvement doesn't
trip anything.

**Verified instances:**

- **`scripts/vulture_gate.py` / `deadcode-baseline.py`**: commit
  `be5ddcfc` ("chore(deadcode): burn down 25 stale baseline entries, 82 ->
  57") removed exactly 25 lines from `deadcode-baseline.py` (confirmed via
  `git show --stat`). All 25 belonged to two EMC validator files
  (`emi_filter.py`, `ground_plane.py`) baselined while they still raised
  `NotImplementedError`; commits `7ab70a65`/`eb3b38fb` implemented them,
  making the parameters genuinely used and the suppressions stale.
- **LOC allowlist / `tools/loc_cap_check.py`**: commit `529df2d9`
  ("chore(loc-cap): record 13 earned paydowns, allowlist 17 -> 6")
  confirms 13 of 17 entries were for files long since decomposed under
  cap, including exactly the two cited in the brief:
  `cli/__init__.py` 3946 → 706 lines, `astar_pathfinding.py` 1797 → 68
  lines. Allowlist entry count went 17 → 6, confirmed.
- **Plan ledger**: `docs/plans/2026-07-25-001-fix-test-skip-accounting-plan.md`'s
  R1 (four unguarded `all()` sites) was implemented in `3c6c19b2`
  (2026-07-25 16:33:45) but the plan wasn't updated to mark it done until
  `dd8226da` (2026-07-27 15:10:40) — **~46.6 hours**, "roughly two days"
  is a fair characterization, not "exactly two days."
- **The asymmetry, confirmed structurally**: `vulture_gate.py` already
  exits 4 on stale baseline entries — that's the only reason the 25
  vulture entries were ever found. The LOC gate had no equivalent check
  until today: `0351345a` / `04457e16` ("feat(loc-cap): fail on stale
  allowlist entries, matching the vulture gate") added a `STALE_ENTRY`
  check to `tools/loc_cap_check.py`, confirmed present at that path,
  exiting 2 (distinguishable from a real violation's exit 1) when an
  allowlisted file is now under cap.

**What mechanically prevents recurrence:** `scripts/vulture_gate.py`
(pre-existing) and `tools/loc_cap_check.py`'s new `STALE_ENTRY` check
(commit `0351345a`), both wired as blocking CI steps (`python-tests.yml:415`,
`:614`, neither has `continue-on-error`). No equivalent exists for plan
documents — a plan's requirement status is still only corrected when
someone re-reads the file, which is how the R1 lag above was found.

---

## 3. Mechanical autofix broke a live caller

**Mechanism:** a ruff/mypy autofix renames or removes a symbol based on
static usage analysis *within the file it's editing*; it doesn't check
callers in other files, so a caller that still uses the old name breaks at
runtime (or at test-collection time) with no compile-time signal in the
file that was actually wrong.

**Why it evades detection:** the fix looks purely mechanical and
behavior-preserving (removing an "unused" argument, dropping an "unused"
import) from the vantage point of the file being edited. mypy does catch
some of these — but the fix landed the same day as an unrelated,
routine allowlist-sync commit that absorbed the new error as accepted
debt within about ten hours, discussed in
`docs/evidence/2026-07-26-api-signature-drift-gate.md`.

**Verified instances**, all traced to specific commits:

- **`check_routability`** (`ce882acf`, "fix 99 more ruff violations
  (ARG001/ARG002 + auto-fixes)", 2026-07-22) renamed the function's
  `net_name` parameter to `_net_name`; `check_routability_direct` in the
  same file kept calling it with the old keyword. Full investigation and
  fix in `docs/evidence/2026-07-26-api-signature-drift-gate.md`; restored
  in `1c6dd6d3`. This is the one instance a mechanical gate now catches
  (below).
- **Five keyword APIs**, repaired together in `2a525d92` ("repair five
  more keyword APIs broken by ARG001/ARG002 autofixes"):
  `drc_runner.CheckRunner.run`'s `modified_regions`,
  `mfem_compare.compare_fields`'s
  `cell_size_mm`, `copper_coverage.check_thermal_plausibility`'s
  `ambient_C`, `battery_run._ensure_field_diverges`'s `netlist`, and
  `geometry/drc_inflate.py`'s `smooth_relu(beta=)` → the correct
  parameter name is `alpha` (`smooth.py:114`); `drc_inflate.py:197`
  currently reads `smooth_relu(clearance_mm - distances, alpha=beta)`
  with an explanatory comment. This is the fifth of the "five," not a
  sixth separate instance.
- **`import time` removed from `cp_sat/loop.py`** by `5a17025b` ("batch CI
  fixes — ruff, codegen, Docker pre-compile", 2026-07-23), as part of
  splitting the module into mixins. This broke
  `test_solve_time_trend_warning`'s
  `mock.patch("...cp_sat.loop.time.monotonic")` target (`AttributeError`,
  test errored rather than asserted). The test file itself now documents this
  (`test_loop_field_feedback.py:596-600`); fixed in `9f03990f`
  ("repoint solve-time monkeypatch at `_loop_core` after the mixin
  split").
- **Fixture params in
  `packages/temper-placer/tests/requirements/dfm/test_placement_rules.py`**
  — `_esp32_placement`, `_esp32_antenna_violation`, and a module-level
  test's `_self` parameter.
  **Correction to the brief**: the root cause is **not** `ce882acf` or
  `5a17025b`. It's a separate commit, `cf2aad24` ("fix(types): batch-fix
  154 mypy errors across 8 seams — 358 -> 204"), which underscore-prefixed
  the parameters as an "unused argument" mypy autofix; pytest resolves
  fixtures by parameter name, so `_esp32_placement` stopped matching the
  still-live `esp32_placement` fixture at line 216. Fixed in `8a65b3f6`
  ("repair enum mixin and pytest fixture params broken by autofixes"),
  which frames this explicitly as "the third manifestation of the
  underscore-rename class today."

**What mechanically prevents recurrence:** `scripts/check_typecheck_gate.py`
gained a hard, additive-only call-arg gate (`.call-arg-allowlist`,
commits `0a5ffe07`/`f584d556`) independent of the shrinkable
`.typecheck-allowlist` — this catches the `check_routability` class
(a `call-arg` mypy error) unconditionally, wired at `python-tests.yml:685`.
**It does not and cannot catch the other two shapes**: the monkeypatch
target and the fixture-name mismatches are pytest-resolution failures, not
type errors, and the fixing commits say so directly ("pytest fixture
resolution is not a type-checker concern"). No gate exists for those; both
were found by running the affected test files and reading the failures.

---

## 4. Stale build artifact read as truth

**Mechanism:** a locally-built PyO3 extension (`maturin develop`, not
`uv sync`-managed) imports successfully even when it predates the Rust
source it's supposed to reflect. A bare `import` check treats "imports"
and "current" as the same fact; they aren't.

**Why it evades detection:** the same class of check —
`python -c "import <module>"` succeeding — is used both to prove the
extension is buildable at all and to imply it's fresh. pyo3 only
guarantees a registered symbol appears on *that build*, never that the
build was taken from HEAD.

**Verified instances:**

- **`temper_drc_rs`**: a stale wheel made
  `test_clearance_rust_differential.py` report **38 skipped, 0 run**
  while CI stayed green — full before/after measurement in
  `docs/evidence/2026-07-26-rust-backend-presence-gate.md` (38 skipped →
  38 passed after rebuild). Explicitly filed under METHODOLOGY §4 class 6
  ("Silently skipped") in that doc's own scope line.
- **`uv sync` reusing a cached build keyed on version, not content**:
  confirmed directly in commit `17eecbd6`'s body — restoring
  `ConfigBoardMismatchError` etc. to `temper-io-types` was "verified
  against a freshly built wheel rather than a cached one (a `uv sync`
  reused a stale build keyed on version rather than content, which
  briefly hid this)." No dedicated gate; caught by forcing a rebuild by
  hand.
- **Dropped as UNVERIFIED**: the brief's claim of "a local checkout had 4
  of 6 PyO3 extensions stale, `temper_rust_router` by 24 days, which
  produced a bogus 49-failure measurement that was retracted" — no commit,
  evidence doc, or `STRATEGY.md` passage corroborates these specific
  numbers. What **is** verified and kept instead: `STRATEGY.md` (line
  774) and `docs/evidence/2026-07-26-rust-backend-presence-gate.md` §4
  both state the structural gap is real and *unfixed* for
  `temper_rust_router` and `temper_constraints` — but that document's own
  §6 explicitly marks staleness for those two crates as **not
  independently reproduced**, unlike `temper_drc_rs`'s incident. The
  4-of-6/24-day/49-failure figures appear to be from a session not
  reflected in this repository's history.

**What mechanically prevents recurrence:** `scripts/check_rust_drc_presence.py`
+ `TEMPER_REQUIRE_RUST_DRC=1` (job-level env var), parses `lib.rs`'s
`#[pymodule]` registration and asserts every symbol is present on the
installed module — wired as a non-`continue-on-error` step at
`python-tests.yml:213-216`, scoped **only to `temper-drc-rs`**. Confirmed
still unfixed for the siblings: `python-tests.yml:182` (`temper_rust_router`)
and `:233` (`temper_constraints`) are both still bare `import` checks with
no freshness gate — the exact structural gap that caused the fixed
incident. No gate exists for the `uv sync` cache-key issue.

---

## 5. A path that does not exist zeroing an entire suite

**Mechanism:** `pytest <path-a> <path-b> ...` aborts entirely if any one
path doesn't exist — it does not skip the bad path and run the rest. If
the step's exit code is discarded (`continue-on-error: true`), this
produces a green check with zero tests run and no visible signal.

**Why it evades detection:** the failure mode looks like "0 tests
collected, exit code non-zero" for a fraction of a second in the log, then
`continue-on-error` converts that into a green step — nobody reads step
logs on a passing job.

**Verified instances:**

- `.github/workflows/python-tests.yml` invoked `pytest tests/router_v6/
  tests/io/ tests/deterministic/ tests/losses/ tests/physics/
  tests/fields/ tests/validation/ tests/placer/cp_sat/`. `tests/losses/`
  does not exist. Confirmed by commit `dd8226da` ("fix(ci): the extended
  test suite has been running zero tests (#354)"): pytest aborts on the
  missing path, so **none of the seven sibling directories ran either —
  3,526 collectible tests, executing zero times**, with the non-zero exit
  discarded by `continue-on-error`. The path is now removed from the
  invocation (confirmed current: `python-tests.yml:364-365`).
- **`packages/temper-workflow`** runs `pytest tests/` and collects 0
  items — confirmed directly: `packages/temper-workflow/tests/` contains
  only `__init__.py`, no test files. Still true in the current tree;
  `dd8226da`'s commit body flags this explicitly as "found and NOT fixed
  here."

**What mechanically prevents recurrence:** `scripts/pytest_guard.py
--min-tests N`, wired at `python-tests.yml:364` (`--min-tests 2500`) and
`:467` (`--min-tests 130`) for the two invocations that were fixed —
asserts a floor on tests *actually executed* from JUnit XML, excludes
skips. **Not extended** to the `packages/temper-workflow` invocation
(`python-tests.yml:377`), which still has no guard and still collects 0
items every run.

---

## 6. A merge deleting production code

**Mechanism:** a merge commit that resolves without a textual conflict can
still silently discard one side's changes if the merge tool (or a human
resolving it) picks the wrong hunk — nothing distinguishes that from a
legitimate merge, and if the discarded code has no test coverage, nothing
downstream notices either.

**Why it evades detection:** the merge completes cleanly — no conflict
markers, no CI failure at merge time if the surviving Python shim still
parses. The break only surfaces the first time something actually calls
the now-missing symbol, which for an untested module can be arbitrarily
later.

**Verified instances:**

- `67e4d4ab` ("feat(io): port zone_filler, config_board_binding,
  design_bundle_preflight to temper-io-types") added 309 lines to
  `packages/temper-io-types/src/lib.rs`: `ConfigBoardMismatchError`,
  `extract_config_refs`, `verify_config_matches_netlist`,
  `fill_zones_pcbnew`, `fill_zones_if_present`.
- The very next commit, `cd4e896a` ("merge main"), resolved the merge by
  discarding that work from the Rust side: `git diff cd4e896a^1 cd4e896a
  -- lib.rs` shows 307 deletions against 2 insertions (net ~309 lines
  removed, matching the fix commit's own count), while keeping every
  Python shim that imports those five names.
- `io/zone_filler.py:7` — confirmed current: `from temper_io_types import
  fill_zones_if_present, fill_zones_pcbnew` — raised `ImportError` at
  module load from `cd4e896a` (2026-07-22) onward. **No test in the repo
  imports `temper_placer.io.zone_filler`**, confirmed by grep, so this
  surfaced nowhere until manually found.
- Already fixed on `main`: commit `17eecbd6` ("fix: all four collection
  errors, including production code a merge deleted (#358)") restored the
  first three symbols in an earlier sibling commit and the remaining two
  (`fill_zones_pcbnew`, `fill_zones_if_present`) in this one, verbatim
  from `67e4d4ab`.

**What mechanically prevents recurrence:** nothing. The fix restored the
dropped Rust code; **no test was added** that imports
`temper_placer.io.zone_filler` or exercises `fill_zones_pcbnew`/
`fill_zones_if_present`, so an identical future merge-resolution mistake
on this file would again go undetected until a real caller hit it.

---

## 7. A mock patching a re-export, silently doing nothing

**Mechanism:** `mock.patch`/`monkeypatch.setattr` intercepts attribute
lookups on the *object you patch*, not all references to the underlying
function. If a module re-exports a name but the production code path
calls the name from inside the module where it's actually defined (not
through the re-export), patching the re-export changes nothing that
production code sees — the mock never fires, and the test can pass
regardless of what the real implementation does.

**Why it evades detection:** the test still runs, still makes assertions,
and those assertions still pass — a passing test whose mock is silently
inert is indistinguishable from a passing test with a working mock,
until someone reads the production call graph.

**Verified instances**, both found and fixed together in `e351f479`
("fix(test): patch `_route_segment_3d` where it resolves, not where it
used to live (#356)"):

- **`_segment_search`** (the silent half): `astar_pathfinding.py` does
  re-export `_segment_search`, so `monkeypatch.setattr(pathfinding,
  "_segment_search", ...)` raised no error — but production calls it from
  inside `_astar_reconstruct.py` (confirmed: `_astar_reconstruct.py:800,
  928, 955`), which never consults the re-export. The fix commit's own
  words: "That mock has been silently ineffective rather than loudly
  broken."
- **`_route_segment_3d`** (its loud sibling, same root cause): not
  re-exported by `astar_pathfinding.py` at all after the module split
  (1,797 → 68 lines). Patching it there raised `AttributeError` in six
  tests across `test_astar_route_multilayer_via_fallback.py` and
  `test_all_pad_tree_routing.py` — loud, not silent, because there was no
  stale re-export to catch the patch.
- Both patch targets are now retargeted to `_astar_reconstruct`, where
  the lookups actually happen. Confirmed current:
  `test_all_pad_tree_routing.py:192, 228` patch
  `reconstruct._segment_search`, not `astar_pathfinding._segment_search`.

**What mechanically prevents recurrence:** nothing. Both patches were
manually retargeted; no lint/AST check exists (and this task did not add
one) that would flag a `mock.patch`/`monkeypatch.setattr` target whose
module doesn't match where the production code actually performs the
attribute lookup.

---

## 8. CI cancelling its own trunk signal

**Mechanism:** `python-tests.yml`'s `concurrency` block groups runs by
`${{ github.workflow }}-${{ github.ref }}`, which collapses to a single
value for every push to `main`. When merges land faster than the suite
finishes, each new push cancels whatever was still running from the
previous one — no run ever reaches a real pass/fail verdict.

**Why it evades detection:** a `cancelled` run isn't a `failed` run;
individually each cancellation looks like unremarkable churn on a
fast-merging day, not the emergent effect of a shared concurrency key
silently discarding every trunk signal.

**Verified, live, via `gh run list --workflow=python-tests.yml --branch
main --json ...`** (not transcribed — queried directly):

- Confirmed: `python-tests.yml:3-5` — `concurrency: group:
  ${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: true`.
- **Eight consecutive `cancelled` runs, confirmed exactly**, most recent
  first: `afaf9000` (workflow_dispatch), `f2f3060e` (workflow_dispatch),
  `f2f3060e` (#360), `45ad8825` (#359), `dd8226da` (#354), `17eecbd6`
  (#358), `e351f479` (#356), `efd78c0d` (#357) — spanning
  2026-07-27T21:09:48Z to 23:27:40Z.
- **Correction to the brief**: "the last completed run predating eight
  merges" is imprecise in two ways. The last non-cancelled run before the
  streak was `b23d9115` (#352, 19:03:21Z) — its conclusion was
  **`failure`**, not a passing "completed" run. And the interval between
  it and the current tip contains **seven** PR merges (#360, #359, #354,
  #358, #356, #357, #353), not eight; the eighth commit in that range is
  `afaf9000`, `architecture-poster.yml`'s own auto-generated
  `ARCHITECTURE.svg` commit, not a PR merge.
- **Correction to the brief on `architecture-poster.yml`'s role**: its
  auto-commit is tagged `[skip ci]` (`architecture-poster.yml:70`) and the
  workflow has no `concurrency` block of its own — confirmed it does
  **not** itself trigger or get cancelled by `python-tests.yml` runs (no
  `push`-triggered `python-tests.yml` run exists for `afaf9000` in the
  list above, only two manual `workflow_dispatch` entries). Its actual
  contribution is softer than "pushes that cancel CI": it's one more
  automated committer landing on `main` in the same fast-merge window,
  compounding how quickly the branch moves, not a second, independent
  source of cancellations against `python-tests.yml`.

**What mechanically prevents recurrence:** none currently.
`concurrency.cancel-in-progress: true` keyed on `github.ref` remains in
`python-tests.yml` as of this measurement. Per this task's brief, a
sibling session is addressing this concurrently — not fixed here, and
`.github/workflows/` was not edited to produce the measurements above.

---

## Related: a workaround outliving the constraint that justified it

Distinct in kind from the eight above — not a defect evading detection,
but a *correct* decision whose precondition silently expired. Verified in
commit `f2f3060e` ("refactor: collapse the three vestigial -core crates,
18 packages → 15 (#360)"):

- **`temper-dsn-core`** and **`temper-ipc-core`** were split out solely
  because pyo3's extension-module `cdylib` couldn't be linked for
  `cargo test` under **pyo3 0.23** (dyld abort). Confirmed in the commit
  body: with pyo3 upgraded to **0.29** elsewhere in the repo, `cargo test
  --lib` links and runs cleanly with no dyld abort — "confirmed with a
  `cargo clean` rebuild, not just an incremental one." Both crates were
  folded back into their parents (`temper-dsn`, `temper-ipc`), verified
  with an unchanged Python symbol set before/after a forced reinstall.
- **`temper-geometry-core`** was split to "break geometry->core import
  cycle" — but the commit confirms that cycle was **at the Python layer**
  (`temper_placer.geometry` importing `temper_placer.core.geometry_types`),
  severed once geometry was ported to Rust wholesale. The two Rust crates
  themselves only ever had a one-way dependency edge; there was never a
  crate-level cycle to break. Verified: `cargo clippy` clean, exported
  Python symbol set byte-for-byte identical (124 names), and the
  `geometry`/`clearance` test suite produces the exact same pass/fail
  counts as unmodified `origin/main`.
- Net: 18 packages → 15, confirmed by the commit's own title and
  arithmetically consistent with three crates removed.

**Why it evades detection:** nothing re-checks whether a workaround's
justifying precondition still holds when the thing that removed the
precondition (here, the pyo3 0.23→0.29 migration) lands as an unrelated,
separately-motivated change. The workaround doesn't announce its own
obsolescence.

**What mechanically prevents recurrence:** none. This instance was found
by an agent manually re-deriving each crate's original split rationale
(`docs/plans/2026-07-25-003-refactor-package-consolidation-plan.md`) and
testing whether it still held. No periodic or CI-driven re-validation of
workaround preconditions exists.

Given the clean-instance count and the distinct shape (precondition
drift, not detection drift), this is a reasonable candidate for a ninth
mechanism, but it doesn't share the "something reports false" character
of 1–8, so it's presented here as related rather than folded into the
same list.

---

## Cross-reference to `docs/METHODOLOGY.md` §4

**Correction to this task's framing**: the brief describing this document
paraphrased METHODOLOGY §4 as "silently-skipped, vacuous, unwired,
dead-wired classes." The actual table has **six** classes — Missing,
Wrong, Unwired, Vacuous, Wrong threshold, Silently skipped — and
**"dead-wired" does not appear anywhere in `docs/METHODOLOGY.md`**
(confirmed by grep). Mapping the eight mechanisms above onto the real
table:

| Mechanism | §4 class | Fit |
|---|---|---|
| 1. Ignore rule never applied | — | Doesn't fit. §4 is scoped to validation-layer checks; a `.gitignore` rule isn't a check. |
| 2. Ledger never updated | — | Doesn't fit, same reason — a debt ledger isn't a validator's verdict. |
| 3. Autofix broke a caller | *(closest: 2, Wrong)* | Partial. The symptom (`TypeError`/`AttributeError`) resembles "computes the wrong function," but the cause is an interface contract broken by tooling, not a validator's logic being wrong. |
| 4. Stale build artifact | 6, Silently skipped | Direct — the source evidence doc files it under class 6 explicitly. |
| 5. Missing path zeros a suite | 4 (Vacuous) + 6 (Silently skipped) | Direct — zero collected items is vacuity; `continue-on-error` is the skip. |
| 6. Merge deletes production code | 1, Missing | Loose — the merge itself isn't a §4 class, but the reason it went unnoticed (`zone_filler.py` has no test) is a textbook class-1 gap. |
| 7. Mock patches a re-export | 4, Vacuous | Direct — a mock that can't fire makes the assertion trivially pass regardless of the code under test, same shape as `all([])`. |
| 8. CI cancels its own signal | 6, Silently skipped | Direct — no completed run means the suite's true verdict is permanently unknown, functionally the same as a skip even though pytest never reports one. |

Three of eight (1, 2, and half of 3) sit outside the taxonomy's current
scope entirely.

## Proposed additions

Not applied — `METHODOLOGY.md`/`STRATEGY.md` were not edited, per the
brief for this task.

- **`METHODOLOGY.md` §4**: add a scope note that the six-class table
  covers validation-layer checks specifically, and a candidate seventh
  class — *"Stale record — ground truth changed and the record that
  claims to track it didn't"* — covering mechanisms 1 and 2 here
  (ignore rules against tracked files, debt ledgers, and the "related"
  workaround-precondition case). This is a repo-hygiene/bookkeeping
  failure shape, not a validator-correctness one, and deserves its own
  bucket rather than being force-fit into the existing six.
- **`STRATEGY.md`**: no edit proposed to its content; a future entry
  documenting mechanism 8's resolution (once the concurrently-running
  sibling fix lands) would be the natural place to close the loop, same
  pattern as the existing dated entries for the other CI-gate fixes
  landed this week.

## Verification summary

Counting each distinct factual claim in the brief this document was
built from (a number, a SHA, a file:line, or a named behavior):
**~29 claims checked. 23 verified as stated (some with corrected line
numbers folded in where the underlying fact was still right); 5 corrected**
(§1's DS_Store count 5→6 and its stale `.gitignore` line number;
§3's fixture-param root-cause commit; §8's "eight merges" → seven PR
merges plus one non-PR auto-commit, and `architecture-poster.yml`'s
mechanical role); **1 dropped as UNVERIFIED** (§4's "4 of 6 PyO3
extensions stale / 24 days / bogus 49-failure measurement," which no
commit, evidence doc, or `STRATEGY.md` passage corroborates).
