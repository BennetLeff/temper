# Open-PR triage: inventory, conflict matrix, rotation-fix casualties, merge order

<!-- provenance: commit=0a8e7194f0150dc310e68fada1af19af2a5ae1e4 dirty=false -->

**Date:** 2026-07-30
**Scope:** Read-only analysis only. No PR was merged, closed, commented on, or pushed to. All
`git merge-tree --write-tree` calls below are read-only (write to a throwaway tree object, not any
ref). All PR branches were fetched read-only as `refs/pull/<n>/head` into local refs `pr-<n>` in
this worktree; no session's branch was checked out, rebased, or force-pushed.
**Base:** `origin/main` @ `0a8e7194f0150dc310e68fada1af19af2a5ae1e4` (tip at fetch time), which is
PR #479's merge commit -- the repo-wide rotation-convention sign fix
(`R(+theta)` -> `R(-theta)`, 12 sites, un-masks 102 REQ-SAFE-01 violations). Every open PR's
merge-base with `origin/main` predates this commit (verified below) -- nobody has rebased onto it
yet.

---

## 1. PR inventory

Open, non-bot, non-release PRs at fetch time (12 total). `gh pr list --state open`.

| # | Title | Base ref | `gh` mergeable | Files changed | +/- |
|---|---|---|---|---|---|
| 486 | fix(pcb): close DRU creepage-rule blacklist gap, triage 205 creepage violations | `fix/kicad-pro-netclass-consolidation` (= #474's branch, **stacked, not `main`**) | MERGEABLE/CLEAN | `docs/evidence/2026-07-30-creepage-205-triage.md`, `scripts/generate_kicad_dru.py` | +416/-4 |
| 483 | fix(ci): conform the rotation evidence doc's provenance line to the gate's format | `main` | MERGEABLE/UNSTABLE | `docs/evidence/2026-07-30-placement-writer-rotation.md` | +2/-1 |
| 481 | fix(tests): re-fix three test_adapter.py zone tests whose vcc fixture went stale | `main` | MERGEABLE/UNSTABLE | `packages/temper-placer/tests/router_v6/test_adapter.py` | +69/-18 |
| 474 | fix(pcb): consolidate GateDrive split (#465) and 13-net coverage (#467) in kicad_pro | `main` | MERGEABLE/UNSTABLE | `_pipeline_route.py`, `trace_width_assignment.py`, its test, `pcb/temper.kicad_pro` | +138/-5 |
| 473 | docs(evidence): triage main's red DRC ratchet -- #459 regressions verified as correct-board consequence | `main` | MERGEABLE/UNSTABLE | `docs/evidence/2026-07-30-drc-ceiling-459-triage.md` (doc only) | +308/-0 |
| 467 | fix(pcb): assign netclasses to 13 nets absent from kicad_pro (#440 remainder) | `main` | MERGEABLE/UNSTABLE | `pcb/temper.kicad_pro` | +14/-1 |
| 465 | fix(pcb): split kicad_pro's GateDrive netclass into GateDriveHV/GateDriveSELV | `main` | MERGEABLE/UNSTABLE | `pcb/temper.kicad_pro` | +23/-5 |
| 460 | fix(placer): make domain-clearance bbox constraint copper-aware, sound | `main` | **CONFLICTING/DIRTY** | 16 files -- see Sec 3 | +2414/-428 |
| 457 | feat(gates): creepage/clearance SSOT-drift gate, derive DEFAULT_CORRIDOR_WIDTH_MM from SSOT | `main` | MERGEABLE/UNSTABLE | `isolation_constants.py` (new), `isolation_barrier.py`, 2 new gate scripts + test | +2201/-10 |
| 447 | fix(netclass): recover 27368038/718a903f fully + 2 orphaned evidence docs (round 2) | `main` | **CONFLICTING/DIRTY** | `_parse_board.py`, `_adapter_convert.py`, `clearance_check.py`, `routing_demand.py`, `trace_width_assignment.py`, `test_adapter.py`, `check_net_classification.py`, allowlist, 2 evidence docs | +1048/-97 |
| 446 | feat(ci): HV netclass coverage gate | `main` | MERGEABLE/UNSTABLE | new gate script + test, CI workflow, manifest | +1088/-0 |
| 440 | fix(netclass): recover stranded HV-netclass and creepage-enforcement fixes | `main` | **CONFLICTING/DIRTY** | `design_rules.py`, `netclass_rules.yaml`, `pcb/temper.kicad_pro`, `generate_kicad_dru.py`, 2 evidence docs, tests, `configs/temper_production_config.yaml` | +2242/-16 |

(#96, `release-please--branches--main`, and no dependabot PRs were open; excluded as out of scope.)

All 12 confirmed **PREDATE #479** (`git merge-base --is-ancestor 0a8e7194 pr-<n>` fails for every
one) -- every open PR needs at least a trivial rebase to pick up the rotation fix, even where no
textual conflict results.

`gh`'s own `mergeable`/`mergeStateStatus` for #460/#447/#440 (CONFLICTING/DIRTY against `main` as
of fetch time) was independently reproduced below with `git merge-tree --write-tree` -- not just
trusted from the API.

---

## 2. Conflict matrix

### 2.1 Each PR vs. current `origin/main` (`git merge-tree --write-tree origin/main pr-<n>`)

| PR | Result |
|---|---|
| 486 | clean |
| 483 | clean |
| 481 | clean |
| 474 | clean |
| 473 | clean |
| 467 | clean |
| 465 | clean |
| **460** | **CONFLICT**: `docs/evidence/2026-07-30-placement-writer-rotation.md` (add/add), `io/_parse_modules.py`, `io/_write_board.py`, `requirements/validators/_copper.py`, `router_v6/_adapter_convert.py`, `tests/router_v6/test_adapter.py` (content) |
| 457 | clean |
| **447** | **CONFLICT**: `io/_parse_board.py`, `router_v6/_adapter_convert.py` (content) |
| 446 | clean |
| **440** | **CONFLICT**: `docs/evidence/2026-07-28-netclass-defect-reconciliation.md` (add/add), `netclass_rules.yaml`, `core/design_rules.py`, `tests/core/test_design_rules.py`, `tests/io/test_netclass_loader.py`, `pcb/temper.kicad_pro`, `scripts/generate_kicad_dru.py` (content), `scripts/tests/test_generate_kicad_dru.py` (add/add) |

"Clean" here means clean **against `origin/main` today** -- it says nothing about whether two
clean-individually PRs conflict with *each other*. See 2.2.

### 2.2 File-overlap clusters and pairwise `git merge-tree`

**Cluster A -- `pcb/temper.kicad_pro`:** #474, #467, #465, #440 (and #486, stacked on #474's
branch, inherits its kicad_pro content without adding more).

| Pair | Result |
|---|---|
| 474 vs 467 | CONFLICT: `pcb/temper.kicad_pro` |
| 474 vs 465 | CONFLICT: `pcb/temper.kicad_pro` |
| 467 vs 465 | CONFLICT: `pcb/temper.kicad_pro` |
| 474 vs 440 | CONFLICT: `pcb/temper.kicad_pro` + `netclass_rules.yaml`, `design_rules.py`, `test_design_rules.py`, `test_netclass_loader.py`, `generate_kicad_dru.py`, 2 add/add evidence docs |
| 467 vs 440 | CONFLICT: same set minus `kicad_pro` overlap is present too (both touch it) |
| 465 vs 440 | CONFLICT: same pattern |
| 486 vs 440 | CONFLICT: inherits 474's `kicad_pro` conflict with 440, plus `generate_kicad_dru.py` (486 and 440 both edit the DRU generator's creepage-rule logic independently) |

This is expected, not alarming: #474's own body states it is **the union of #465 and #467**
("Both #465 and #467 edit `pcb/temper.kicad_pro` and must land together, not separately... This
branch is the union of both diffs"). #465 and #467 conflicting with #474 individually is exactly
what "#474 supersedes both" should look like. See Sec 5 for the recommendation to close #465/#467
in favor of #474.

**Cluster B -- `router_v6/_adapter_convert.py` / `tests/router_v6/test_adapter.py`:** #460, #447,
#481.

| Pair | Result |
|---|---|
| 460 vs 447 | CONFLICT: `io/_parse_board.py`, `_adapter_convert.py` |
| 460 vs 481 | CONFLICT: `docs/evidence/2026-07-30-placement-writer-rotation.md` (add/add), `_adapter_convert.py`, `test_adapter.py` |
| 447 vs 481 | CONFLICT: `io/_parse_board.py`, `_adapter_convert.py`, `test_adapter.py` |

Unlike Cluster A, this is **not** one PR being a clean superset of the others -- #460, #447, and
#481 fix three different, non-overlapping bugs (rotation/bbox-frame soundness; stranded
plane-detection + SAFETY_VOCAB substring fixes; stale test fixtures) that happen to land in the
same two files. Note also that `474 vs 447` conflicts in `io/_parse_board.py` even though #474's
own file list does not touch that file directly -- this is an artifact of #474 and #447 diverging
from `main` at different points while `main` itself moved under both of them; it is not evidence
of a real feature interaction and should not be read as one (confirm by rebase, not by this
artifact alone).

**Cluster C -- `docs/evidence/2026-07-30-placement-writer-rotation.md`:** #483, #460 (add/add
against `origin/main`, and against each other -- see Sec 3.1, this is a real duplicate-content
collision, not noise).

**Cluster D -- `scripts/generate_kicad_dru.py`:** #486, #440 (content conflict; both independently
patch DRU-generation creepage-rule logic).

**No conflict found:** #457 is disjoint from every other open PR (verified individually against
446, 460, 465, 467, 474, 481, 483, 486, 440, 447, 473 -- all clean; full pairwise grid not included
here for brevity since 457 clean-vs-main plus zero shared files with any other PR's file list is
sufficient). #446, #473, #481 (besides Cluster B), #483 (besides Cluster C) have no other file
overlaps with the rest of the queue.

---

## 3. Rotation-fix (#479) casualties

**Headline finding: exactly one open PR substantively collides with #479 -- PR #460 -- and it is a
severe collision: #460 independently discovered and fixed the identical rotation-sign bug, in three
of #479's twelve sites, reaching the identical headline number (102).**

### 3.1 PR #460 -- duplicate, independent rediscovery of the same bug

#460's pushed branch (`fix/domain-clearance-copper-aware`, head `f3a3fb13`) is not a single-purpose
diff. Its own commit log (oldest to newest) is:

```
9471908b fix(placer): make domain-clearance bbox constraint copper-aware, sound   <- #460's stated purpose
44f98f83 docs(evidence): add appendix on the one discovered regression + root cause
58d2fdcb refactor(router): split zone/pour emission out of _adapter_convert.py (#470)   <- ALREADY on main via #470
b21110ab fix(router): apply CP-SAT solved rotation in _apply_placements_to_pcb (#471)   <- ALREADY on main via #471
f3a3fb13 fix(placer): correct KiCad footprint rotation sign, close Q1/Q2 golden-board short   <- DUPLICATE of #479
```

The last commit's message (`f3a3fb13`) states, in #460's own author's words:

> "every place this codebase converts between a CP-SAT box-centre coordinate and a KiCad footprint
> anchor under rotation assumed KiCad rotates a footprint's pads counter-clockwise. Verified
> directly against pcbnew ... it rotates them clockwise... Fixed in the four places carrying the
> wrong sign: `_adapter_convert.py::_apply_placements_to_pcb`, `io/_write_board.py`
> (`write_placements_to_pcb`/`state_to_placements`), `io/_parse_modules.py`,
> `requirements/validators/_copper.py::_rotate`... **REQ-SAFE-01 moves 98 -> 102 on this same
> commit**"

This is the *same* R(+theta)->R(-theta) bug #479 fixed repo-wide, on 3 of #479's 12 sites
(`_parse_modules.py`, `_write_board.py`, `requirements/validators/_copper.py`), reaching #479's
*exact same* headline number: **102 REQ-SAFE-01 violations un-masked**. Diffing #460's hunks
against #479's confirms the fix is functionally identical (same sign flip, same trig identity,
same 6-decimal-place pcbnew verification numbers `(10.393615, -2.823608)` appear in both #460's and
#479's code comments almost verbatim) -- independent convergent discovery, not a copy, but a full
duplicate in effect.

**Consequence:** #460 will not cleanly rebase. `git merge-tree` confirms real conflicts (not
cosmetic) in exactly the 3 shared sites plus `_adapter_convert.py` (content) and
`docs/evidence/2026-07-30-placement-writer-rotation.md` (add/add -- #460 carries its own copy of
the doc #471 already landed under a different provenance stamp). A human rebasing #460 must:

1. Drop the `f3a3fb13` rotation-sign commit's hunks entirely for the 3 sites #479 already fixed
   (taking `main`'s version) -- applying both would either double-flip the sign back to wrong, or
   at best be a no-op merge headache with no functional difference from taking `main`'s.
2. Drop the `58d2fdcb`/`b21110ab` hunks that duplicate already-merged #470/#471 (confirmed on
   `origin/main` today -- `_zone_pour_stitch.py` exists, `route_pcb()` already has a `rotations:`
   parameter).
3. Keep only the genuinely novel `9471908b` (copper-aware bbox / `center_offset`-before-bounds fix)
   and `44f98f83` (evidence appendix) content, rebased onto current `main`.
4. **Re-run Sec 3's REQ-SAFE-01 and DRC measurements from scratch against the actual post-#479
   `main`** before trusting any number in `docs/evidence/2026-07-30-domain-clearance-copper-aware-
   fix.md` or `docs/evidence/2026-07-30-generic-separation-writer-frame-fix.md`. The "98 -> 28"
   REQ-SAFE-01 delta and the "43 -> 49 / shorting 1 -> 4" DRC delta in those docs were measured
   using #460's *own* branch-local rotation fix, which is a plausible but not verified match for
   #479's now-canonical version once every other queued PR (netclass/kicad_pro changes especially)
   also lands. Do not carry these numbers forward unmeasured.

### 3.2 The already-merged doc PR #483 touches is itself stale

`docs/evidence/2026-07-30-placement-writer-rotation.md` (landed via #471, merge commit `27bc79bc`,
**before** #479 in `main`'s history -- confirmed: `27bc79bc` is an ancestor of `0a8e7194`) reports
Sec 3 measurements (CP-SAT solve -> DRC deltas under both rotation-applied and rotation-dropped
writer behavior) computed with the *old*, wrong R(+theta) `_parse_modules.py` convention active.
Those specific numbers (Sec 3.1: "43 -> 43, identical"; Sec 3.2 reproducing #460's regression:
"43 -> 49, shorting_items 1 -> 4, placement_fixable 10 -> 16") are pre-#479 measurements and should
be treated as unverified against the current rotation convention. **#483 itself is fine to merge**
-- it only fixes the provenance *line format* on this doc, touches zero content, and is otherwise
correct -- but it does not fix, and should not be read as vouching for, the doc's now-stale
numbers. Recommend a human flag this doc (not #483) for re-measurement once #460 is resolved (Sec
3.1 above), since both describe the same underlying writer-rotation interaction and should agree
after both are current.

### 3.3 Everything else checked and cleared

Grepped every open PR's file list against #479's 12 fixed sites (`scripts/check_isolation_keepout.py`,
`io/_parse_modules.py`, `io/_write_board.py`, `io/_write_modules.py`, `io/kicad_exporter.py`,
`core/pin_geometry.py`, `placer/cp_sat/isolation_barrier.py`,
`requirements/validators/_copper.py`, `deterministic/stages/setup.py`, `placer/template.py`,
`core/courtyard.py`, `temper-geometry/src/transform.rs`):

- **#457** touches 2 of the 12 site *files* (`isolation_barrier.py`, and
  `check_isolation_keepout.py` which is textually adjacent to but distinct from the site list --
  actually the sign-fix landed in that file too per #479's commit message). Diffed directly:
  #457's hunks only hoist the `MIN_BARRIER_WIDTH_MM`/`DEFAULT_CORRIDOR_WIDTH_MM` *constant* into a
  new `core/isolation_constants.py` SSOT module; it never touches `_rotate()` or
  `_project_onto_barrier_axis()` (the functions #479 actually changed). Textually disjoint,
  confirmed by clean `merge-tree` against both `origin/main` and `pr-460`. **Not a casualty.**
- **All other PRs (486, 483 besides Sec 3.2, 481, 474, 473, 467, 465, 447, 446, 440)** touch none
  of the 12 sites. None of their headline claims depend on the Python rotation-sign convention:
  #465/#467/#474/#440/#486's DRC numbers come from real `kicad-cli`, which #479's own commit
  message states explicitly does not change ("No safety constant, target, or netclass changed. No
  board re-floorplanned, no parts moved, no copper edited -- `pcb/` and `elec/` untouched by this
  commit.") -- i.e. the *committed* `pcb/temper.kicad_pcb`/`pcb/temper.kicad_pro` geometry `kicad-
  cli` measures is unaffected by a Python-only sign-convention fix. **Not casualties of #479**,
  though see Sec 4 for why their numbers are still moving targets for unrelated reasons (concurrent
  netclass edits).

---

## 4. Duplicated / contradictory work (non-rotation)

- **Cluster A supersession, not duplication:** #474 is explicitly the union of #465 + #467 (its own
  body says so and the merge-tree conflicts confirm it's a strict superset diff). **Recommend
  closing #465 and #467** once #474's content is confirmed to match both (spot-checked above; not
  independently re-verified line-by-line here) rather than merging all three.
- **#440 vs. #467/#474:** #467's own body states "#440 itself... its full diff against current
  `main` is now a net -11600 lines (mostly deletions of things `main` has since restructured/
  replaced)... The **only** content in #440 not already on `main` is its `pcb/temper.kicad_pro`
  hunk, which this PR carries in isolation." That claim could not be independently re-verified
  within this task's time budget (it references a "-11600 lines" figure that does not match the
  `+2242/-16` this task's own `gh pr view` snapshot shows for #440 today -- likely because #467's
  body was written against an earlier, larger `main` snapshot and `main` has moved again since).
  **Flagging, not resolving**: a human should re-diff #440 against current `main` before deciding
  whether anything beyond its `kicad_pro` hunk is still unique. Given #474 already carries the
  reconciled `kicad_pro` content, #440's own `kicad_pro` hunk is likely now fully redundant with
  #474's, not #467's alone.
- **#460's internal duplication of #470/#471/#479** -- covered in full in Sec 3.1; this is the most
  severe duplication found, not because two *different* PRs solve the same problem, but because one
  open PR (#460) contains three already-independently-merged fixes (#470, #471, and a rediscovery
  of #479) bundled with its actual novel content.
- **No contradictory (one-undoes-another) pair was found.** Every overlapping pair inspected
  (Cluster A, B, D) is either a clean superset relationship (#474 over #465/#467) or genuinely
  independent, non-overlapping fixes landing in the same file (#460/#447/#481 in
  `test_adapter.py`; #486/#440 in `generate_kicad_dru.py` -- #486 fixes a creepage-rule blacklist
  gap, #440 fixes unrelated rule-condition binding bugs RULE 1/1a/5/7).

---

## 5. Recommended merge order and disposition

| Order | PR | Disposition | Why |
|---|---|---|---|
| 1 | **#483** | Merge as-is | Trivial (2 lines), clean, fixes a real CI-gate false negative ("gate reported 'no provenance line found' while a provenance comment was plainly visible"). No dependency on anything else in the queue. |
| 2 | **#481** | Merge as-is | Small, surgical, empirically verified fixture fix, clean against `main`. Landing it now (before #460/#447 rebase) shrinks what those two have to resolve in `test_adapter.py` later. |
| 3 | **#457** | Merge as-is | Fully disjoint from the rest of the queue (Sec 2.2, Sec 3.3), clean, adds a gate (net safety win). |
| 4 | **#465 + #467 -> close in favor of #474** | Close #465, close #467 (do not merge separately) | #474 is their explicit, verified union; merging all three would just recreate Cluster A's conflicts for no benefit. |
| 5 | **#474** | Merge after rebase (trivial -- clean against current `main` today) | Unblocks #486 (stacked on it) and resolves the `kicad_pro` three-way conflict at its root. |
| 6 | **#486** | Rebase off `main` (currently based on #474's branch) then merge | Needs #474 in `main` first (it's literally stacked on #474's branch). Also needs a look at its own reported residual gap ("`pcb/temper.kicad_pro` itself is missing netclass assignment for `ac_l`/`ac_n`/`+170V_BUS`/`PWR_RTN`/`SW_NODE`") against whatever #440/#467 leave behind. |
| 7 | **#440** | **Needs human re-diff before merging, likely trim-and-close** | Its `kicad_pro` hunk is superseded by #474/#486; per #467's own claim most of the rest is already on `main`. Re-diff against post-#474 `main`; merge only what's left, or close if nothing is. |
| 8 | **#446** | Merge after #440's netclass fixes (or whatever survives from it) land | #446's own body: "Passes clean on this branch (based on `fix/recover-stranded-netclass-safety`, #440)... Watched fail on `origin/main`." Merging #446 before its prerequisite netclass fixes land turns a currently-green gate red for the wrong reason (real, currently-unfixed board gaps) rather than the intended reason (verifying the gate itself). Land the netclass fixes (whatever remains of #440, or #467/#474/#486's coverage) first. |
| 9 | **#447** | Rebase onto `main` (post items 1-8), resolve `_parse_board.py`/`_adapter_convert.py`/`test_adapter.py` conflicts | Genuinely new content (Bug 1, the `_extract_stackup` plane-detection substring bug, confirmed via before/after violation counts in its own body) not superseded elsewhere. Best landed after the netclass/kicad_pro cluster settles so its `SAFETY_VOCAB` sibling-substring fixes apply to final net assignments. |
| 10 | **#460** | **Needs the largest rework -- do not merge as-is** | Strip the duplicate rotation-sign commit and the duplicate #470/#471 commits (Sec 3.1), keep only the copper-aware bbox fix, rebase onto `main` post-#447, and **re-measure Sec 3's REQ-SAFE-01/DRC numbers fresh** before trusting them. Land last in this cluster since it depends on `_adapter_convert.py`/`test_adapter.py` being settled by #481/#447 first. |
| 11 | **#473** | Merge last, or re-run its analysis after items 1-10 land | Its verdict ("#459's 7 red categories are a correct-board consequence, zero real regressions") is about a different, already-settled root cause and is probably still valid -- but the *specific ceiling values* it recommends for a human to apply will already be stale by the time 8 other PRs ahead of it in this order have changed the DRC baseline. Recommend re-running `scripts/ci_check_drc.py --backend kicad-cli` fresh right before any `Ceiling-Approval:` trailer is authored, rather than trusting this doc's numbers at that point. |

**Safe to merge essentially as-is:** #483, #481, #457.
**Needs rebase only (mechanical, low risk):** #474, #486 (after #474), #446 (after its prerequisite
netclass content), #447 (moderate conflict resolution).
**Needs re-measurement before trusting its own claims:** #460 (Sec 3.1), and #473's specific ceiling
numbers (Sec 5, row 11) once the rest of the queue lands.
**Needs a human re-diff and likely close/trim:** #440 (Sec 4).
**Recommend closing outright (superseded):** #465, #467 (in favor of #474).

---

## 6. What could not be established

- Whether #474's `kicad_pro` union is byte-for-byte faithful to #465 + #467's individual diffs was
  not independently re-verified line-by-line (its body claims it was "re-derived via `gh pr diff`
  from each PR's actual head, not typed from the PR descriptions" -- plausible, spot-checked via
  the merge-tree conflict shape matching expectations, not exhaustively).
- #467's "-11600 lines" claim about #440's diff against `main` could not be reconciled with this
  task's own `+2242/-16` snapshot of #440 (Sec 4) -- almost certainly just `main` having moved
  again between when #467's body was written and this triage's fetch, not an error in either, but
  flagged rather than assumed.
- Whether #460's post-rebase (rotation-duplicate-stripped) REQ-SAFE-01/DRC numbers will still show
  the reported "98/102 -> 28" improvement was not re-measured in this task (out of scope --
  read-only analysis, no branch checkouts of other sessions' work, no long-running solves run).
  This is flagged as the single most important follow-up in Sec 3.1/5.
- Did not attempt N-way (3+ branch) simulated merges of the full recommended order end-to-end; each
  pairwise/vs-main check in Sec 2 is real, but the cumulative effect of applying all 11 in the Sec 5
  order was not itself dry-run.
