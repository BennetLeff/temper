# 2026-07-28: origin/main <-> docs/methodology-loop-discipline reconciliation

## Context

`origin/main` and the canonical methodology base commit `0cf203af` (branch
`docs/methodology-loop-discipline`, per task instruction -- see "Base commit
resolution" below) had diverged: **24 commits behind / 79 commits ahead**
(exact counts, verified by `git rev-list --count`):

```
git rev-list --count 0cf203af..origin/main   -> 24
git rev-list --count origin/main..0cf203af   -> 79
git merge-base 0cf203af origin/main          -> 706dc346b310d6b4cd3a235e4aadcf7083b62392
```

This matches the task's stated 24/79 split exactly, confirming `0cf203af` is
the correct base commit.

### Base commit resolution (a real hazard, caught before merging)

The **local** branch ref `docs/methodology-loop-discipline` in this worktree's
shared object store was NOT at `0cf203af` -- it was at `f8b5f43c`, a commit
that is an *ancestor* of `0cf203af` (64 commits behind it), carrying five
unrelated `docs(solutions):` commits on top of an older point in the same
line of history. `git merge-base --is-ancestor 0cf203af
docs/methodology-loop-discipline` returned false. The local branch ref had
gone stale relative to `origin/docs/methodology-loop-discipline` (which
correctly points at `0cf203af`) -- exactly the kind of shared-checkout drift
the task warned about. **The local branch name was not trusted; the pinned
commit hash `0cf203af` was used as the merge base**, per explicit task
instruction.

## Work location

All work was done in worktree
`/Users/bennet/Desktop/temper/.claude/worktrees/agent-ae6c3371e77830d8d`, on a
new branch `merge/main-into-methodology-loop-discipline` created from
`0cf203af` (not from the stale local `docs/methodology-loop-discipline` ref,
and not by mutating that ref -- other concurrent sessions may depend on it).
`origin/main` was merged into this new branch. **Nothing was pushed.**

## Survey: the 24 incoming commits (origin/main, not in 0cf203af)

```
c59589b0 feat(gates): decide netlist freshness by content hash, not mtime
985073af Merge #372: content-hash freshness for the netlist gate
5b9c05db fix(tests): re-baseline production DRC gates -- bare-board budgets were judging a routed board (#373)
1f9d13d9 fix(tests): pin the retired --placer CLI contract instead of the removed one (#380)
e4e5e976 fix(encoder): read unresolved-ref policy live; unmask the golden-board gate (#379)
3ba5cf81 perf(ci): split Core Tests so one red gate stops hiding 33 others
2cff1705 Merge pull request #378 from BennetLeff/perf/split-core-tests-gates
0a94206e chore(build): add `make extensions` to rebuild all pyo3 crates in one command
05aa69e7 Merge pull request #376 from BennetLeff/chore/make-extensions-target
f9c043a6 feat(gates): decide extension freshness by content hash, not mtime
e0af5e46 Merge pull request #377 from BennetLeff/feat/content-hash-extensions
f23e0e70 fix(evidence): stamp pour-strategy-audit.md with real provenance
7aeab150 fix(tests): re-characterize the stale real-tree MPN gate test as clean, not failing
21fd2530 fix(docs): reconcile UVL-02 Sec7.1's zero-capacity invariant with the tree that superseded it
3733f25c fix(hygiene): remove genuinely-dead GateError import and unreachable else block
e799183c fix(safety): replace circle-only pad model with exact shape-aware geometry (gate + CP-SAT)
b99f6ced fix(router): consolidate router pad-radius model onto the shared exact geometry
cd7704a6 docs(evidence): pad geometry model fix -- derivation, re-derived tables, verification
8b64f975 Merge pull request #383 from BennetLeff/fix/evidence-provenance-pour-audit
6896de97 Merge pull request #384 from BennetLeff/fix/mpn-gate-stale-test
76f14845 Merge pull request #385 from BennetLeff/fix/capacity-budget-invariant
83415083 Merge pull request #387 from BennetLeff/fix/vulture-dead-code
320e3c81 Merge pull request #388 from BennetLeff/fix/pad-geometry-model
65fc5df7 chore: regenerate ARCHITECTURE.svg [skip ci]
```

Files touched: 44 files, +4770/-542. Themes: (1) exact shape-aware pad
bounding-radius model (`core/pad_geometry.py`, new) replacing the isotropic
`max(size.X, size.Y)/2` circle approximation everywhere it was used
(`check_isolation_keepout.py`, `isolation_barrier.py`, router obstacle map,
escape-via generator); (2) CI robustness (content-hash freshness for netlist
and extension gates, `make extensions` target, splitting the monolithic
"Core Tests" CI job so one red Rust-lint step stops masking ~33 downstream
gates); (3) several test/gate re-baselines and dead-code/evidence cleanups.

## Survey: the 79 outgoing commits (0cf203af, not in origin/main)

79 commits, 79 files, +17268/-1225. Themes: the day's safety/DRC work --
creepage/clearance re-derivation (PD2->PD3 retarget, 8.0mm -> 12.6mm
reinforced creepage), `generate_kicad_dru.py` DRC-rule condition fixes (KiCad
condition-language matches-nothing traps), K2/K3 discharge-relay
replacement-then-revert (Finder DPDT tried, found to fail creepage, reverted
to Omron G5LE-1 `Relay_SPDT`), net-classification and net-assignment fixes
(`+170V_BUS` rename propagation), the router A* decomposition/reconstruction
rewrite, and ~20 `docs/solutions/` lessons-learned entries.

## Overlap: files touched by both sides

Exact-name overlap (`git diff --name-only` on each side, `comm -12`):

```
.github/workflows/python-tests.yml
packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py
scripts/check_isolation_keepout.py
```

No other file -- including every file named in the task's watch list
(`elec/domain_manifest.yaml`'s `TEMPER_NET_ASSIGNMENTS`-equivalent,
`pcb/temper.kicad_pro`, `scripts/generate_kicad_dru.py`, `elec/src/*.ato`) --
was touched by both histories. This was verified by grepping the 24-side's
changed-file list for `kicad_pro|generate_kicad_dru|elec/src|net_assignment
|TEMPER_NET` -- zero matches. Those files therefore carried over from the
79-side (0cf203af) completely unchanged, with no merge decision to make.

### Per-overlap-file hunk-range analysis (done before merging, to predict conflicts)

- **`scripts/check_isolation_keepout.py`**: 24-side hunks at original lines
  151 (import), 249-260 (`PadInstance.radius` docstring), 378-400
  (`load_board`, pad-radius computation switched to
  `pad_bounding_radius()`). 79-side hunks at original lines 27-34, 47-74
  (docstring "Which clearance figure" section, PD2->PD3 rederivation),
  164-174 (`MIN_BARRIER_WIDTH_MM` 8.0 -> 12.6). Disjoint ranges ->
  **auto-merged cleanly**, confirmed by `git merge`.
- **`isolation_barrier.py`**: 24-side hunks at 51-63, 103-109, 225-291,
  348-361, 548-558 (Pad tuple -> dataclass with shape-aware
  `axis_radius()`). 79-side hunk at 125-137 only (`DEFAULT_CORRIDOR_WIDTH_MM`
  8.5 -> 13.1, tracking the keepout gate's 12.6mm retarget +0.5mm margin).
  Disjoint -> **auto-merged cleanly**.
- **`.github/workflows/python-tests.yml`**: 79-side's single hunk (renaming
  the "Derived-document drift gate" step and its comment to describe all
  four arms it now covers: STRATEGY.md, PROTECTION_CHAIN_REVIEW.md, and
  board facts vs `pcb/temper.kicad_pcb`) sat inside the 24-side's giant
  CI-restructuring hunk (splitting the ~1300-line monolithic "Core Tests" job
  into `rust-checks`, `board-gates`, and other jobs). **This is the one
  actual conflict** -- resolved manually (see below).

## Conflict resolution (the only one)

`.github/workflows/python-tests.yml`: git produced a diff3 conflict where
HEAD (0cf203af) had the old monolithic job body (ending in "Rebuild script
invocation graph"), the merge base had the same body pre-rename, and
`origin/main` had deleted the entire block (it was split into several new
jobs earlier in the same file: `rust-checks`, `board-gates`, etc.).

**What each side intended:**
- 79-side (0cf203af): rename one step and its comment so the description
  matches what `check_derived_doc_drift.py` now actually checks (it grew a
  fourth arm, `PROTECTION_CHAIN_REVIEW.md`, plus a `pcb/temper.kicad_pcb`
  board-facts check). Purely descriptive; the `run:` command
  (`uv run python scripts/check_derived_doc_drift.py`) is byte-identical
  before and after.
- 24-side (origin/main): fix a real incident where one Rust clippy failure in
  the old monolithic job masked 43 downstream steps (including two safety
  gates) for hours. Split the job into independently-reporting jobs. The
  same "Derived-document drift gate" step (unrenamed, still the pre-79-side
  wording) already exists intact in the new `board-gates` job, at what is now
  line 768 of the merged file -- verified by grep before resolving.

**Resolution:** took `origin/main`'s restructured job layout (deleting the
old monolithic block entirely -- keeping it would resurrect the exact
"one red gate hides 33 others" defect the 24-side commit fixed, and would
duplicate every step name in the file), then manually re-applied the
79-side's step-rename and comment to the step's new location in
`board-gates` (now lines 765-774). Verified both `docs/STRATEGY.md` and
`pcb/temper.kicad_pcb` are already in that job's `paths:` trigger filters
(lines 77, 82, 150, 155), matching the re-applied comment's claim. No
functional behavior changed by this resolution -- only which job runs an
unchanged command, and what its name/comment say it covers.

This is a **minimal, well-documented resolution** per the task's note that
two sibling agents are working `scripts/generate_kicad_dru.py` /
`netclass_rules.yaml` and worktree `.venv` isolation and will land after this
merge -- their changes do not touch this file.

## FALSIFIER check

*"The two histories merge cleanly on the merits, with no safety-relevant
correction lost. If any conflict cannot be resolved without choosing between
two defensible intents, stop and report it rather than picking one."*

**Did not fire.** Both sides' intents in the one real conflict were fully
compatible (a cosmetic rename vs. a structural CI split) and both survive
intact in the resolution -- nothing was silently dropped, and no defensible
intent was overridden by the other.

## Watch-list verification (all five items, all confirmed present post-merge)

| Item | Verified as |
|---|---|
| `TEMPER_NET_ASSIGNMENTS`-equivalent map (`design_rules.py`) keeps `+170V_BUS` -> `HighVoltage` | `packages/temper-placer/src/temper_placer/core/design_rules.py:444` `"+170V_BUS": "HighVoltage"` (legacy `"+340V_BUS"` key also retained at line 445, not removed) |
| `pcb/temper.kicad_pro` net-class assignments | line 336-337 `"ac_l"/"ac_n": "ACMains"`, line 343 `"+170V_BUS": "HighVoltage"` |
| `generate_kicad_dru.py` conditions | `A.Reference == B.Reference`, `A.NetClass == B.NetClass`, `A.Pad_Type == 'SMD'` all present; `A.Footprint`, `A.insideCourtyard(B.Reference)`, `A.Attribute` forms only appear in comments documenting why they were replaced (grep confirmed, no live occurrences as conditions) |
| `check_isolation_keepout.py` 12.6mm PD3 figure | `MIN_BARRIER_WIDTH_MM = 12.6` at line 257; live gate run (see below) prints "Required minimum barrier width: 12.6mm" |
| `elec/src/` K2/K3 relay | `elec/src/modules.ato` instantiates `k_dis1 = new Relay_SPDT` / `k_dis2 = new Relay_SPDT` (Omron G5LE-1); `Relay_DPDT` (Finder) component exists in `components.ato` only as an explicitly-quarantined, never-instantiated definition with a "DO NOT re-instantiate this component for K2/K3" docstring |

No conflict markers remain anywhere in the tree (checked: `grep -rn
'^<<<<<<<\|^=======$\|^>>>>>>>'` across `.py`/`.yml`/`.yaml`/`.md` -> 0
matches).

## Verification run (after `uv sync --all-packages --inexact` and `make
extensions`, both required since this worktree had no prior venv; 10/10
pyo3 extensions rebuilt and confirmed fresh by `check_stale_extensions.py`
before running any gate)

`make netlist`: **Build complete** (no assertion failures).

Ten gates required green -- **10/10 green**:

| Gate | Result |
|---|---|
| `check_domain_partition.py` | PASSED -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects (54 nets, 2 domains, 10 isolators, over 164 compiled nets/168 components) |
| `capacity_budget_gate.py` | PASSED -- 0 defects |
| `mpn_fabrication_gate.py` | PASSED -- 0 new violations |
| `check_derived_doc_drift.py` | passed -- 3 documents, 47 tables, 52 gate rows matched, 136 fields checked, 6 board facts checked (confirms the merged CI step's new "four arms" description is accurate) |
| `check_copper_net_consistency.py` | PASSED -- 0 violations across 2482 copper items, 510 pads |
| `check_rust_drc_presence.py` | OK -- temper_drc_rs present and fresh |
| `check_undeclared_imports.py` | passed -- 3273 imports checked across 657 files |
| `check_stale_extensions.py` | PASSED -- 10/10 extension modules fresh |
| `check_net_classification.py` | passed -- 0 violations (65 UNRESOLVED call sites reported informationally, not counted as violations -- expected/pre-existing behavior) |
| `check_pll_range_consistency.py` | PASSED -- 4/4 checks agree |

Expected non-green gates, confirmed still at their documented expected exit
codes (not "fixed", per task instruction):

- `check_isolation_keepout.py`: **exit 3**, 1 violation (missing physical
  keepout zone -- a real, known, unresolved hardware gap), using the merged
  **12.6mm** figure throughout its own output.
- `check_measurement_provenance.py`: **exit 5**, 1 problem (malformed
  `source` field in `power_pcb_dataset/drc_ceiling.json`, pre-existing).

Test suites required green -- **all green**:

- `uv run --no-sync python -m pytest elec/validation -q`: **30/30 passed**.
- `scripts/tests/test_generate_kicad_dru.py`: **21/21 passed**.

Additional targeted tests run as extra diligence on the two auto-merged,
safety-adjacent files (not explicitly required by the task, but touched by
both histories):

- `packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier.py` +
  `scripts/tests/test_check_isolation_keepout.py`: **40/40 passed**.
- `packages/temper-placer/tests/core/test_pad_geometry.py` +
  `scripts/tests/test_check_stale_extensions.py`: **102 passed, 6 skipped**
  (skips pre-existing/unrelated, not caused by this merge).

## UNVERIFIED

- The full repo-wide test suites (`packages/temper-placer/tests/` in full,
  `packages/temper-workflow/tests/`, the multi-hour INVARIANT suite, the
  Rust crates' `cargo test`/`cargo clippy`) were **not** run in full --
  out of scope for the task's explicit verification list and multi-hour on
  this machine. Only the gates, tests, and suites the task explicitly named
  as required, plus a few extra targeted tests on the two non-conflicting
  overlap files, were run.
- The two sibling agents' claimed in-flight work on
  `scripts/generate_kicad_dru.py` / `netclass_rules.yaml` and worktree
  `.venv` isolation was not independently observed (no such uncommitted
  changes were visible from this worktree at merge time) -- this merge does
  not touch either area, so no interaction is expected, but their eventual
  landing was not verified against this branch.
- Disk headroom was monitored before/after the extension build (21GB ->
  19GB free); not monitored continuously throughout every step.

## Result

Branch `merge/main-into-methodology-loop-discipline` (worktree
`/Users/bennet/Desktop/temper/.claude/worktrees/agent-ae6c3371e77830d8d`),
commit `1ae67f41`, contains `origin/main` merged into `0cf203af` with one
manually-resolved conflict (documented above), zero safety-relevant
corrections reverted, and all required gates/tests green or at their
documented expected non-zero exit codes. **Not pushed anywhere**, per task
instructions.
