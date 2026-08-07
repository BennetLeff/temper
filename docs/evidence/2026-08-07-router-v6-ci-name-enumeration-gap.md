# `tests/router_v6/` name-enumeration gap: ground truth, triage, and the drift test

<!-- provenance: worktree branched from main 7e1194b7 (2026-08-07); adds one
     new test file (packages/temper-placer/tests/validation/test_ci_test_file_registration.py)
     and this document. No workflow file, production source, pcb/temper.kicad_pcb,
     or power_pcb_dataset/drc_ceiling.json was touched. -->

## Why this doc exists

A CI-mask triage flagged that 47 files in `packages/temper-placer/tests/router_v6/`
looked unreferenced by any CI job, and speculated it might be a second instance
of the "CI enumerates test files by name, so a forgotten file silently never
runs" defect shape already confirmed twice this session (a deleted file in
router_v6 group 2 zeroing that whole group; 9 of 20 firmware test binaries
never registered with `add_test()`). This doc re-derives that finding from
scratch against the current worktree (`main` 7e1194b7), fixes the count, runs
every unreferenced file to find out what it actually does, and lands the
structural fix: a drift test.

## 1. Ground truth

Enumerated every `.py` file under `packages/temper-placer/tests/` (989 files,
754 matching the `test_*.py` pytest-collection convention) and every file/dir
argument any `.github/workflows/*.yml` step passes to `pytest`, resolved
per-step against that step's `working-directory` (a step's bare `tests/...`
argument only means `packages/temper-placer/tests/...` when the step actually
`cd`s or sets `working-directory: packages/temper-placer` — two raw regex
hits for `tests/test_route_and_measure_{pbt,rust_differential}.py` turned out
to belong to `packages/temper-workflow`'s own test tree, a step with
`working-directory: packages/temper-workflow`, and were excluded once that
was checked).

- **754** files under `packages/temper-placer/tests/` match the `test_*.py`
  pytest-collection convention (989 `.py` files total, including helpers,
  oracles, `conftest.py`, and property strategy modules that don't match that
  convention and were never going to run under any name).
- Workflow steps reference **209 individual filenames** plus **13 whole
  directories** (`core/`, `deterministic/`, `fields/`, `io/`, `metrics/`,
  `physics/`, `placer/cp_sat/`, `requirements/{dfm,emc,review,safety}/`,
  `rust_integration/`, `validation/`) — resolved per-step against that step's
  actual `working-directory` (or an inline `cd packages/temper-placer &&`,
  one step uses that form instead), not assumed from a flat regex sweep. An
  early pass of this same sweep skipped the whole-directory case, which wrongly
  flagged everything under `tests/validation/` (including
  `test_gate_input_registry.py` itself, which plainly does run) as
  "unreferenced"; corrected before any number below was finalized.
- Combining named files with directory membership: **536 of 754** `test_*.py`
  files are covered by at least one job. **218 are covered by none.**
- Exactly **1** individually-named reference resolves to nothing on disk:
  `tests/router_v6/test_wave4_numba_astar.py`, named in the *Invariant tests
  (router_v6 group 2)* step (`.github/workflows/python-tests.yml:2710`). The
  file was deleted in `37793e5c` (post-Numba-migration cleanup, predates this
  session). `pytest` exits 4 (usage error, "file or directory not found")
  before collecting anything from that invocation, so `pytest_guard.py`'s
  `--min-tests 500` floor never even gets a JUnit report to read —
  **confirmed by directly running `pytest --collect-only -q` with group 2's
  exact 50-file argument list: `collected 0 items`, rc=4.** This is the same
  defect class the "invariant tests router_v6 group 2" masking comment already
  names, re-confirmed against current `main` rather than assumed.
  - **This is the only dangling reference anywhere in the file.** All 12 other
    `pytest_guard.py`-wrapped invocations in `python-tests.yml` (groups 1/3/4,
    the two Phase-5 anti-vacuity gates, the cli/report/explainability/clearance
    differentials, the requirements suite, both cp-sat suites, and both
    `invariant-rest` steps) were each re-run locally with the *exact* file/dir
    arguments the workflow passes, using `pytest --collect-only -q`. Every one
    of them collects a nonzero count comfortably above its declared
    `--min-tests` floor (e.g. group 1: 693 collected vs. floor 500; group 3:
    722 vs. 500; `invariant-rest`: 4423 vs. 2350; the validation hard gate:
    1528/1530 vs. 590). **Group 2 is the only zeroed group in the file.**
- Of the **218** uncovered `test_*.py` files, **49** are under
  `tests/router_v6/` specifically (the flagged directory, and the only
  subtree with zero directory-level coverage anywhere — see below); the
  remaining **169** are spread across the rest of the test tree (`tests/pcl/`,
  `tests/scripts/`, `tests/manufacturing/`, `tests/core/`'s uncovered
  siblings, etc.) and are **out of scope for this pull** — the assignment was
  router_v6 plus a general ground-truth count, and the structural fix below
  (§4) applies uniformly to all of them, not just router_v6, without this
  pull re-triaging every one individually.
  - This corrects the originally-flagged **47** to **49**, fully explained by
    drift on `main` between the original triage's read and this one (not a
    methodology disagreement), plus restricting the count to actual
    `test_*.py` pytest-collection modules rather than also counting
    helper/oracle files (`_*.py`, `conftest.py`, strategy modules) that don't
    match that convention and were never going to run under any name anyway.

**`tests/router_v6/` as a *directory* is never passed to pytest anywhere.**
153 of the 209 individually-named files are under `router_v6/` (153 + 49
uncovered = 202, the full `test_*.py` count for that directory) — every one
an individual filename; the apparent directory-looking matches in a naive
regex sweep are just the `tests/router_v6/` prefix shared by those 153
individually-named files, not a `pytest tests/router_v6/` argument. Confirmed
by direct grep of every `router_v6` occurrence across all workflow files.

## 2. The 49 unreferenced `router_v6/test_*.py` files: what they actually do

All 49 were built and run together, from a fresh worktree checkout, with the
same four Rust extensions the CI container prebuilds
(`temper-rust-router`, `temper-drc-rs`, `temper-constraints`,
`temper-geometry`, plus — not built by any `python-tests.yml` step, evidently
baked into `ghcr.io/bennetleff/temper-ci:latest` directly —
`temper-design-bundle`, `temper-ipc`, `temper-constraint-compiler`,
`temper-quality-oracle`, `temper-placement-topology`, `temper-io-types`,
`temper-thermal`, `temper-orchestration`, `temper-dsn`), using the same
`-m "not slow"` marker filter groups 1-4 use:

```
2691 collected, 3 skipped
2688 passed, 3 failed
```

**22 of the 49 are `*_rust_differential.py` files** — the R19 pinned-oracle
differentials that pin a Rust port bit-exact against its pre-migration Python
oracle. Combined with the ground-truth pass: `router_v6/` has **23**
`test_*rust_differential.py` files on disk total, and **only one**
(`test_clearance_rust_differential.py`) is named anywhere in
`python-tests.yml` — inside group 2's list, the group that currently
collects zero tests (§1). **Net effect: 100% of router_v6's Rust-migration
differential oracles are currently unverified by CI** — 22 by pure omission,
the 23rd by omission-via-poisoned-group. This is exactly the risk the task
brief named: the migration evidence these files exist to provide is not being
re-checked on any PR or trunk run.

### Triage

**46 of 49 files: fully green.** No `kicad-cli`/`ngspice`/`mfem`-style
environmental blocker anywhere in the 49 — these are pure Python/Rust
differential and property-based tests with no external tool dependency. Three
`*_rust_differential.py` files (`test_channel_skeleton_...`,
`test_layer_assignment_...` group) plus a few others carry a conditional
`pytest.skip(f"pinned commit {sha} not present in this clone")` guard for
shallow-clone environments; this worktree is a full checkout so those ran
rather than skipped. Three test *functions* skip for an unrelated,
pre-existing reason: `test_stage2_golden_parity.py` and
`test_stage4_golden_parity.py`/`test_stage4_monolith_parity.py` module-skip
when their `tests/fixtures/stage{2,4}_goldens/` fixture data isn't present in
the expected per-board layout (`stage2_goldens/` doesn't exist on disk at
all; `stage4_goldens/` exists but its subdirectories are stage names, not the
per-board layout the loader expects). That is a pre-existing fixture-generation
gap (`generate_stage2_goldens.py`/`generate_stage4_goldens.py` exist in the
same directory and were evidently never run to populate `stage2_goldens/`),
unrelated to CI wiring, and out of scope here — flagged, not fixed.

**3 of 49 files: genuinely fail** — real content bugs, not environment noise,
each independently reproducible and unrelated to platform quirks a CI
container wouldn't also hit:

1. `test_congestion_rust_differential.py::test_total_movement_bit_exact[moves6]`
   and `test_escape_via_rust_differential.py::test_is_position_valid_bit_exact[overflow_square]`
   — same root cause: on an intentional-overflow input, the Python oracle
   raises `OverflowError(34, 'Numerical result out of range')` (glibc's
   `strerror(ERANGE)` text) while the Rust binding raises
   `OverflowError(34, 'Result too large')` (a string PyO3/the Rust crate
   hardcodes). The differential asserts the oracle and Rust exception
   *messages* match verbatim and they don't. Real, reproducible parity gap
   between the pinned oracle and the Rust port's error surface — not a
   flaky/local-only failure, though it was measured on this machine's glibc,
   not inside `ghcr.io/bennetleff/temper-ci:latest`, so it should be
   re-confirmed in-container before being treated as certain to reproduce
   there too.
2. `test_zone_pour_geometry_rust_differential.py::test_tie_break_class_exists_direct_cKDTree_comparison`
   — fails with the test's own diagnostic message: *"the forcing coordinates
   no longer reproduce a scipy/first-wins disagreement -- this test no longer
   demonstrates the documented divergence and should be re-derived."* The test
   was written to force a specific SciPy `cKDTree` tie-break disagreement with
   fixed coordinates; the installed SciPy version no longer produces that
   disagreement at those coordinates. Self-documented maintenance debt, not a
   Rust-port regression — but also not passing, so it can't be wired in
   as-is.

None of the three are `kicad-cli`/`ngspice`/`mfem`-shaped environmental
failures. They are the reason "just turn the directory on" is not the
recommended fix (see §3) — doing that today would turn any gate it's wired
into red on day one.

## 3. Workflow changes this pull is leaving unapplied

**Not applied — another agent is concurrently wiring gates into
`.github/workflows/*.yml`, and this pull was instructed not to touch that
directory.** Documented precisely here so that work can act on it directly:

1. **Fix the deleted-path defect in group 2** (`python-tests.yml:2710`):
   remove `tests/router_v6/test_wave4_numba_astar.py` from the group 2
   argument list (the Numba backend it tested was removed in `365eb259`, the
   test file itself in `37793e5c`; there is no successor file to point at
   instead — the Rust A* kernel's own coverage lives in
   `test_astar_kernel_rust_differential.py`, already one of the 49). This
   alone changes group 2 from 0 collected to ~700+, including reinstating the
   one `rust_differential` file already on its list
   (`test_clearance_rust_differential.py`). Group 2 is currently
   `if: github.event_name != 'pull_request'` and `continue-on-error: true`
   (trunk-only, masked, comment says "one live failure" was the reason for the
   mask on 2026-07-28) — worth re-measuring once the path is fixed, since the
   mask predates this fix and may have been hiding the zero-collection outcome
   rather than (or in addition to) a real failure.
2. **Add the 46 currently-green `router_v6/` files** to CI. Two ways to do
   it, in order of preference:
   - **Preferred — switch the four `invariant-router-v6-*` steps from
     per-file enumeration to `tests/router_v6/` as a directory**, with
     `--deselect` for the 3 known-failing test IDs from §2 (mirroring the
     pattern the validation hard gate already uses for
     `test_mfem_runner.py::test_check_mfem_binary_present` and
     `test_ucc21550_contract_pbt.py::...`). This is the structural fix (§4)
     applied to the workflow side too — it is what makes "add a new
     `router_v6/test_*.py` file" not require a workflow edit at all going
     forward, closing the hole this whole investigation is about, not just
     patching today's instance of it.
   - Fallback if a directory switch is judged too large a change for this
     round: append the 46 filenames to whichever of groups 1/3/4 (or a new
     group) keeps runtime balanced, and the 3 failing-file names to an
     explicit backlog for later, with `--deselect` on the specific failing
     node IDs if the surrounding file's other tests are worth having now.
3. **Do not add the 3 failing tests un-deselected.** Either `--deselect` the
   3 specific node IDs (letting the rest of those 3 files run) or exclude the
   3 files outright pending a fix, with a tracked reason each:
   - `test_total_movement_bit_exact[moves6]` / `test_is_position_valid_bit_exact[overflow_square]`
     — Rust-vs-oracle `OverflowError` message text mismatch (temper-NNN,
     needs the Rust side's message updated to match the oracle's
     `strerror`-based text, or the oracle relaxed to compare error *type*
     only).
   - `test_tie_break_class_exists_direct_cKDTree_comparison` — needs
     re-derived forcing coordinates for the current SciPy version
     (temper-NNN).
4. Re-verify all three findings inside `ghcr.io/bennetleff/temper-ci:latest`
   itself before wiring — this doc's runs were local (full checkout, locally
   built Rust extensions), not inside the actual CI container.

No file under `.github/` was modified to produce this doc; the above is
description only.

## 4. Structural fix: a drift test, not a one-time patch

A name-enumerated list drifts again the next time someone adds a
`router_v6/test_*.py` file and forgets to add it to a job — the mechanism that
produced both the 49-file gap here and the two independently-confirmed
instances this session (the deleted group-2 file; 9/20 unregistered firmware
`add_test()` binaries). Two structural options:

- **Point CI at directories with explicit exclusions** (§3.2's preferred
  option) — removes the enumeration step for the common case (a new file in
  an already-covered directory just runs), leaving only genuine
  exclusions (known-failing/environment-gated tests) as an explicit,
  reviewable list. This is a workflow change, left for the CI agent per
  the constraint above.
- **A drift test** that fails when a `test_*.py` file exists but is
  referenced by no job — same shape as the pre-existing
  `test_every_invoked_ci_gate_script_is_registered` in
  `packages/temper-placer/tests/validation/test_gate_input_registry.py`,
  which already does exactly this for gate *scripts* (`scripts/*.py` invoked
  from `python-tests.yml`) and has worked in this repo since U4.

**This pull adds the second one**, in
`packages/temper-placer/tests/validation/test_ci_test_file_registration.py`,
for two reasons beyond "belt and suspenders": (1) it is the only fix this
pull is actually allowed to apply — the workflow-side directory switch is
explicitly out of bounds here; (2) even after the directory switch lands,
files under still-enumerated jobs elsewhere in the repo (there are 169
outside router_v6 — see §1) stay exposed to the exact same defect, and a
drift test protects all of them uniformly without requiring every job to be
converted to directory-style first.

The test re-derives the same coverage computation as §1 (test files vs.
workflow-referenced files/dirs, per-step `working-directory`-scoped) and
requires an exact match against two explicit, reasoned registries:

- `_KNOWN_UNCOVERED_ROUTER_V6_FILES`: the 49 files this doc actually
  triaged in §2, each with a specific, individual reason (the 46 that pass,
  citing the file; the 3 that fail, citing the exact assertion and a
  `temper-NNN` placeholder per §3.3). This is the set worth reading
  file-by-file, because it's the one this pull has real information about.
- `_KNOWN_UNCOVERED_BASELINE`: the other 169 files, untriaged and out of
  scope for this pull, loaded from a checked-in snapshot
  (`ci_test_file_registration_baseline.txt`, one path per line, header
  pointing at this doc) rather than hand-written per-file reasons — 169
  individually-fabricated justifications this pull has no actual basis for
  would be worse than none. The snapshot **is** the reason: "present in the
  baseline" means "known, pre-existing, not re-triaged here."
  
  Together the two registries make the test **green today** — a drift
  detector, not a demand that this pull fix 218 pre-existing gaps it wasn't
  scoped to fix. A **new** unreferenced file outside both registries fails
  the test immediately, by name, forcing a deliberate choice (wire it in, add
  it to the router_v6 registry with a real reason, or add it to the baseline
  snapshot) instead of silent omission. Shrinking either registry without
  actually wiring the file into a job is impossible to do by accident: the
  test also asserts every registry entry is *still* actually uncovered, so
  deleting an entry while the file remains unreferenced just makes the test
  fail the other way.
- `_KNOWN_DANGLING_WORKFLOW_REFERENCES`: paths named in a workflow step that
  don't exist on disk. Currently seeded with the one instance from §1
  (`router_v6/test_wave4_numba_astar.py`, with the `python-tests.yml:2710`
  citation and the removal-commit trail from §3.1). A **new** dangling
  reference — the group-2 defect's shape — fails immediately. Because this
  pull cannot edit the workflow, the existing instance stays registered
  (tracked, not silently accepted) until the CI agent applies §3.1; the CI
  agent's fix will make this test fail with "registry entry stale, remove
  it," which is the intended nudge to keep the two in sync.

`_KNOWN_UNCOVERED_ROUTER_V6_FILES` requires a non-empty reason per entry
(checked by a dedicated test), matching the `non_covered` / `ci_scripts`
reason requirement already enforced in `test_gate_input_registry.py`.
`_KNOWN_DANGLING_WORKFLOW_REFERENCES` likewise. The baseline snapshot's
"reason" is uniform by construction (this doc), so it isn't repeated 169
times in code.

This new test module lives under `tests/validation/`, which
`invariant-rest`'s *"Run validation invariant tests (hard gate)"* step
(`python-tests.yml:2988-2996`) already sweeps as a whole directory
(`tests/validation/`) with **no** `continue-on-error` mask — so, unlike every
`router_v6/` file this doc is about, this new test actually executes on
trunk without requiring any workflow edit at all, and is a real (unmasked)
gate. It does not run on PRs today because `invariant-rest` is
`if: github.event_name != 'pull_request'` — the same trunk-only condition
`router_v6` groups 1/2/4 have; whether to promote `invariant-rest` (or just
this file) to PR-time is a call for whoever owns that job's scope, not
applied here.
