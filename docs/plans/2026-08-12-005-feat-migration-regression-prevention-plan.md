---
title: Migration regression prevention — closing the scipy reversal and arming the class
type: feat
date: 2026-08-12
topic: migration-regression-prevention
artifact_contract: ce-unified-plan/v1
artifact_readiness: design-and-prototype
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# Migration Regression Prevention

> **CORRECTION (2026-08-12), added by the void-board-baseline purge task.** §1.4 below
> cites `docs/evidence/2026-08-12-board-recipe-reproducibility.md`'s "168 footprints,
> 3,349 segments, 56 vias, 70 zones, 80/105 nets" as "the current reproducible full-recipe
> baseline." That figure is **VOID** -- see the correction notice at the top of that
> document itself (measured on an unpinned `pumpkin_engine` binary, not reproducible from
> an identifiable program). The true baseline is **2,514 segments / 22 vias / 76 zones /
> 168 footprints** (`scripts/board_shape_baseline.json`). §1.3-1.4's own conclusion --
> that this plan's fix does not change `_corridor_backbone.py`'s output and so does not
> itself owe a baseline re-measurement -- is not affected by which baseline number is
> current; only the specific figure cited in §1.4 is void.

## Goal Capsule

**Objective:** Fix the scipy regression #1052 (`d8e6efd48`) reintroduced into
`_corridor_backbone.py`, verify it does not change the board, measure how
widespread this failure class actually is, and arm a proportionate,
non-vacuous CI gate against recurrence.

**The defect, stated precisely.** `_corridor_backbone.py:549` (as merged in
#1052) does `from scipy.ndimage import label` for 8-connected
component-labelling of a corridor mask. This repo closed this exact
migration twice: `1efa1cb33` (EDT call sites) and `3ba16bfbd` ("migrate
routability_check.py and channel_skeleton radius kernel off scipy" —
`connected_components.rs`, exposed as
`temper_geometry.connected_components_8_transform`, already used by
`routability_check.py`'s own `_connected_components_8` wrapper). #1052 did
not add a genuinely new capability; it re-solved an already-solved problem
with the already-deprecated tool, and no gate objected.

**Why this matters beyond one file.** A completed, twice-verified migration
was silently reversed by a PR whose own CI ran green. The general failure
is: nothing in this repo, before this plan, prevented reintroducing a
dependency the repo has deliberately migrated away from. Whether that's a
one-off or a pattern determines how much infrastructure is proportionate —
measured in Part 2 below, not assumed.

---

## Part 1 — the fix (landed on this branch)

### 1.1 What changed

`packages/temper-placer/src/temper_placer/router_v6/_corridor_backbone.py`:
added a local `_connected_components_8(mask) -> np.ndarray` wrapper
(mirrors `routability_check.py`'s own, same name, same delegation target:
`temper_geometry.connected_components_8_transform`), and replaced the
`scipy.ndimage.label` call site with it. No other production file imports
`_corridor_backbone.py`'s internals besides `_ground_plane.py` and
`_power_islands.py` (both verified, §1.3).

**No partial replacement was needed** — an exact Rust equivalent already
existed, already proven (`docs/evidence/2026-08-07-rust-connected-components-spike.md`:
~8.9M cells, 33 curated + 300 random trials, 0 partition mismatches, 0
numeric-label mismatches against scipy), and already used in production
elsewhere (`routability_check.check_routability_cc`). This was a pure
delegation swap, not new engineering.

### 1.2 Why label *ordering* — the risk the task specifically flagged — doesn't apply here

`_corridor_backbone.py` uses the label array in exactly two ways
(`corridor_aware_spanning_edges`'s `groups.setdefault(comp_id, ...)`
grouping and `_nearest_label`'s "first nonzero label in this window"
lookup) — both are partition/equality operations, never a numeric
comparison or an ordering assumption. Even though the Rust kernel is not
*contractually* required to reproduce scipy's exact numbering (only the
partition), it measurably does, on every case tested. The risk is real in
the abstract; it is structurally inert at this specific call site. Full
argument: `docs/evidence/2026-08-12-corridor-backbone-scipy-to-rust-board-neutrality.md` §1.

### 1.3 Board-neutrality: verified, not assumed

**Verdict: board-neutral, directly measured.** Both of
`_corridor_backbone.py`'s only two production callers
(`_ground_plane.generate_ground_plane_content`,
`_power_islands.generate_power_islands_content`) were run twice against the
real, untouched `pcb/temper.kicad_pcb`
(sha256 `6928b7c8...0544b64`, unchanged throughout — `git status --short
pcb/` empty before/after) — once with the fix, once with the pre-fix scipy
code restored via an uncommitted scratch patch — and their returned board
content matched **SHA256-identical** in both cases:

```
gnd_after_fix.txt      a72d25032635...80913ec
gnd_before_fix_scipy   a72d25032635...80913ec   (identical)
pwr_after_fix.txt      bee24d088317...a75613
pwr_before_fix_scipy   bee24d088317...a75613   (identical)
```

Both runs exercised the changed code path non-vacuously
(`mst_edges_astar_routed=15` for `gnd`, `=7` for `+3V3` — nonzero, so the
corridor-mask/connected-components branch actually ran, not merely
short-circuited).

**A full `route_board.py` end-to-end re-route was attempted, not
completed** — it was OOM-killed twice in this environment (~59.5GB RSS on a
62GB host under heavy concurrent multi-agent load; `dmesg` confirms `Out of
memory: Killed process ... (python3)` both times, unrelated to this fix).
Full detail and the reasoning for why the narrower per-caller test is
sufficient (and in one respect *more* precise, since it isolates this
change from Stage 0-4 net-batching's own independently-documented
nondeterminism) is in
`docs/evidence/2026-08-12-corridor-backbone-scipy-to-rust-board-neutrality.md`
§3. This is reported as a resource constraint, not a shortfall in the
verification's rigor — the evidence obtained is SHA256-exact on the real
production code path, which is a stronger result than a full-board segment/
via/zone count match would have been on its own.

### 1.4 Baseline reconciliation

`docs/evidence/2026-08-12-board-recipe-reproducibility.md` (from a sibling
worktree, `agent-a374c69e35366ad12`) established the current reproducible
full-recipe baseline: 168 footprints, 3,349 segments, 56 vias, 70 zones,
80/105 nets routed — measured on `origin/main` **including** #1052 (i.e.
including the scipy regression this plan fixes). Since §1.3 proves the fix
changes nothing about `_corridor_backbone.py`'s output, that baseline
remains valid and unaffected by this fix; no re-measurement of the full
baseline is owed by this change.

---

## Part 2 — how widespread is this failure class?

**Measured (`docs/evidence/2026-08-12-migration-reversal-sweep.md`): 1
reversal, not many.** Full-tree sweep of production imports (`packages/`,
`scripts/`, `tools/`, excluding tests/oracles/spikes/benchmarks) for scipy,
networkx, shapely, and ortools:

| Library | Closed migration? | Production imports | Reversals |
|---|---|---:|---:|
| scipy | Yes | 1 (pre-fix) -> 0 (post-fix) | **1** (this PR's own fix) |
| networkx | Yes | 0 | 0 |
| shapely | No — documented, deliberate GEOS boundary KEEP | 26 | N/A |
| ortools | No — documented architectural blocker (no Rust CP-SAT) | 4 | N/A |

This is the number that calibrates Part 3: a narrow, near-zero-cost gate is
proportionate; a large new subsystem is not justified by the evidence.

---

## Part 3 — prevention: design, cost, and wiring proof

Full option comparison (4 options, costed):
`docs/brainstorms/2026-08-12-migration-regression-prevention-options.md`.
**Chosen: extend the existing import-boundary check** (`AGENTS.md` §
"Import Boundary Check"), per the task's own stated preference and because
it fits: `scripts/import_linter_gate.py` + `.importlinter` is already
wired, already required, already blocking.

### 3.1 What was added

`.importlinter`: `include_external_packages = True` (required for a
`forbidden` contract to reference a module outside `root_packages`) plus
two new contracts:

```ini
[importlinter:contract:no-scipy-in-temper-placer]
type = forbidden
source_modules = temper_placer
forbidden_modules = scipy

[importlinter:contract:no-networkx-in-temper-placer]
type = forbidden
source_modules = temper_placer
forbidden_modules = networkx
```

**This is a ratchet-at-zero, not a registry.** Because Part 2 proves scipy
and networkx are *already* at zero production imports, there is no
per-symbol mapping to build or keep synchronized — the two contracts are
maximally strict from the moment they land. This sidesteps the central
design problem of a "closed migrations registry" option (how does the
registry learn about a new closure without a human/agent remembering to
update it?) by not needing one for the two libraries with actual reversal
history/risk today.

### 3.2 Why this is not another instance of the pattern this session was warned about

The task named three concrete failure modes found elsewhere in this repo
this week (`docs/evidence/2026-08-12-gate-vacuity-structural-prevention.md`,
`docs/evidence/2026-08-11-gate-vacuity-audit.md`): a purpose-built gate
commented out of CI for four days, a sync script whose docstring claimed CI
wiring it never had, and a reachability heuristic that credited "a test
file exists" as "runs in CI." Checked against each:

- **Wired, not advisory:** `.github/workflows/python-tests.yml`'s
  `hygiene-gates` job runs "Import boundary enforcement"
  (`uv run python scripts/import_linter_gate.py`) with **no**
  `continue-on-error`. `.github/required-checks.json`'s
  `required_contexts` includes `"Repo Hygiene & Import Gates"` — confirmed
  by direct read of both files, not inferred from a docstring claim.
- **Blocking, not soft-launch:** `import_linter_gate.py`'s
  `CUTOVER_DATE = 2026-07-06` has already passed (today: 2026-08-12); a
  violation exits non-zero and blocks merge, not merely warns.
- **Not a frozen/hand-maintained list that can silently drift:** the two
  new contracts assert "zero of this library, ever" — there is no list of
  symbols to keep in sync as migrations complete. The
  `import-linter-allowlist.yaml` escape hatch (frozen since 2026-07-06,
  requires a ticket reference in the justification comment) already exists
  and needs no changes; any future legitimate exception is visible in
  `git diff` with a reason attached, not silent.
- **Demonstrated to fail on the real violation, not merely inspected:**

  ```
  $ # exact reintroduced line restored: from scipy.ndimage import label
  $ uv run python scripts/import_linter_gate.py
  temper_placer imports scipy
  Boundary rule: no-scipy-in-temper-placer
  Option B: Add an allowlist entry to 'import-linter-allowlist.yaml' ...
  $ echo $?
  3

  $ # fix restored
  $ uv run python scripts/import_linter_gate.py
  Import boundary gate PASSED — 0 new violations
  $ echo $?
  0
  ```

  This reproduces PR #1052's exact defect against the new gate and shows it
  is caught — not a synthetic example, the actual historical regression.

### 3.3 R42 mutation coverage (`scripts/gate_mutate.py`) — evaluated, not extended, with reasons

The task asked whether R42 applies. `import_linter_gate.py` is **not**
currently in `ci-corpus/mutations.yaml`'s corpus. Per
`docs/evidence/2026-08-12-gate-vacuity-structural-prevention.md`'s own
measured cost model (its Part 2, "Cost, coverage, and what it structurally
cannot catch"): a gate that already exposes an injectable `run()` (like
`check_hv_netclass_coverage.py`) costs ~1 hour to add a canary + 2-3
mutation triples; a gate that shells out to a real subprocess against the
real repo tree (like `import_linter_gate.py`, which invokes `lint-imports`
as a subprocess) is explicitly named in that same document as the *higher*
cost case, needing either a retrofit of injection points or a heavier
tempdir/subprocess canary. Given Part 2's measured count (1 reversal) does
not justify a large new investment, and §3.2 already provides direct,
non-synthetic proof the gate fires on the real historical defect (which is
what R42 would mechanize for hypothetical future gate-logic regressions,
not what's at risk today), this plan does **not** extend R42 in this PR.

**Named as follow-up, honestly costed:** wrap `import_linter_gate.py`'s
`lint-imports` subprocess call in a tempdir-fixture canary (a scratch
package tree with one `import scipy` line, asserted to fail; one without,
asserted to pass), then add `guard-strip`/`condition-invert`/`return-stub`
mutation triples against `classify_lint_report` and `run_lint_imports`'s
violation-parsing logic. Estimated cost: half a day (subprocess-based
canary, per the cited cost model, not the ~1 hour injectable case). Not
done here because Part 2's proportionality argument (1 reversal, not 20)
argues against front-loading it, and §3.2's direct historical-regression
reproduction already answers "does this specific gate catch this specific,
real defect" — which is the higher-value question R42 would otherwise be
approximating.

### 3.4 Named, non-hidden scope limits

- Covers `temper_placer` (import-linter's `root_packages`) only — a
  regression in `scripts/`, `tools/`, or a sibling package (e.g.
  `temper-workflow`) is not caught by this mechanism. Part 2's sweep found
  zero such regressions today, so this is a scope boundary, not a
  currently-open hole; if the sweep is re-run later and finds one, the fix
  is a second `.importlinter` (or a shared one, if those packages are ever
  brought under the same root) — same low-cost shape as this PR's own.
- Only guards scipy and networkx — the two libraries with an actually
  closed migration today. A future closed migration for a different
  library needs its own contract added by hand at that time; this is not
  automatic, and no mechanism in this repo makes it automatic without the
  registry-and-population problem Option A (in the brainstorm doc) was
  rejected for solving at a cost disproportionate to the measured count.

---

## Verification checklist

- [x] Fix applied, `_corridor_backbone.py` scipy-free (`cff390182`).
- [x] Board-neutrality measured directly on the real board, both callers,
      SHA256-identical (`docs/evidence/2026-08-12-corridor-backbone-scipy-to-rust-board-neutrality.md`).
- [x] Label-ordering risk addressed structurally (code reading) and
      empirically (real-board byte-identical output).
- [x] Full-tree sweep for other reversals, real counts
      (`docs/evidence/2026-08-12-migration-reversal-sweep.md`).
- [x] Gate designed, implemented, wired into an already-required CI check.
- [x] Gate demonstrated non-vacuous against the real historical defect
      (exit 3 on the regression, exit 0 on the fix).
- [x] R42 applicability evaluated and honestly costed as a named follow-up,
      not silently skipped.
- [ ] Full `route_board.py` end-to-end re-route — attempted, OOM-killed
      twice by environment resource contention, not completed. Not treated
      as a blocking gap given §1.3's stronger, targeted evidence; named
      here for transparency per the task's "stop and report" instruction
      for anything not fully verified.

## Follow-ups (not done in this PR, scoped and costed)

1. R42 extension for `import_linter_gate.py` (§3.3): ~half a day,
   subprocess-canary shape.
2. Full `route_board.py` baseline re-confirmation, opportunistic, whenever
   this environment's concurrent-agent memory pressure allows a ~60GB
   single-process run to complete without OOM (not urgent: §1.3's
   per-caller evidence already establishes board-neutrality independently).
3. If a future sweep finds a reversal outside `temper_placer` (`scripts/`,
   `tools/`, a sibling package), extend with a second `.importlinter`-style
   gate scoped to that root, mirroring this PR's shape.
