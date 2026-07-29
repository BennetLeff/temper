---
title: "A baseline judges the board it was measured against, not the one committed today — four absolute thresholds, one still red on main, that outlived the bare board that produced them"
date: "2026-07-29"
category: best-practices
module: temper_placer
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "hardcoding a numeric threshold (violation count, footprint count, unconnected-item budget) measured against a specific artifact revision"
  - "a PCB, netlist, or other generated/committed artifact is about to be regenerated, re-placed, or re-routed"
  - "a doc or test comment cites a measurement date without also citing the commit or artifact state it was measured against"
  - "a gate compares today's artifact against a constant instead of against a second measurement of today's artifact"
  - "considering a hand edit to a stale baseline/golden file to make a CI gate green again"
tags:
  - stale-baseline
  - mutable-artifact
  - differential-gate
  - board-shape-guard
  - drc-thresholds
  - category-error
  - anti-vacuous-truth
  - golden-regression
  - manual-rebaseline-resets-the-clock
---

# A baseline judges the board it was measured against, not the one committed today

## Context

`pcb/temper.kicad_pcb` was bare — 149 footprints, zero copper (no segments,
no vias, no zones) — through 2026-07-21. On 2026-07-27 (`556ccf4f`) it was
routed for the first time (2,338 segments, 48 vias, 96 zones), then resynced
to the netlist (`65bd0159`, 170→168 footprints, 165→164 nets). Four
independent absolute thresholds, each written against an earlier board
shape, kept being compared to a later one for as long as six days after the
board changed underneath them:

1. **`docs/STRATEGY.md`** asserted "The committed board carries no routing:
   0 segments, 0 vias, 0 zones" and "149 footprints, 151 nets" — both true
   on 2026-07-25, both false by the time anyone read them after
   `556ccf4f`/`65bd0159`. Fixed in PR #371 (`df5e1db5`).
2. **`test_regression_drc.py`**'s `PRODUCTION_PLACEMENT_ONLY_DVIOLATIONS =
   800` (measured 747) and `PRODUCTION_ROUTING_DVIOLATIONS = 1200`
   (measured 953) were both measured on the 149-footprint, zero-copper
   board. Fixed in PR #373 (`5b9c05db`), which proved the point by
   re-running `kicad-cli pcb drc` against `git show be14c878:pcb/temper.kicad_pcb`
   (the historical bare board) and reproducing 747 class-for-class — 62
   `shorting_items`, 57 `solder_mask_bridge`, 27 `courtyards_overlap`, 12
   `clearance`, zero track/via/zone violations of any kind. Decomposing the
   growth from 2026-07-18 to the routed HEAD: of the total +849 violations,
   ~247 came from the board silently growing 149→170 footprints while still
   bare, and ~591 came from actually routing it.
3. **`test_zone_pour_production_measurement.py`**'s
   `PRODUCTION_UNCONNECTED_POST_U4_BASELINE = 260` was measured 2026-07-21,
   also on the bare board. PR #373 flagged it in a comment but did not
   re-measure it — that test was silently skipping on every macOS dev
   machine (see below), so nobody could. PR #386 (`b39b382d`) finally
   measured it: on the routed board, `enable_zone_pours=True` produces
   `unconnected_items` **identical** to `False` (396 vs 396, zero scatter
   across three DRC samples), because the board already ships 96 filled
   zones and the flag pours 96 more on top of them — exactly duplicating
   existing copper rather than connecting anything new.
4. **`power_pcb_dataset/baselines/temper_production_baseline.yaml`**'s
   `component_count: 170` — a different artifact from either of the above:
   a hand-maintained YAML golden baseline consumed by the *Golden
   Regression Check* workflow's `golden-check` job, not the DRC thresholds
   or board-shape guard in `test_regression_drc.py`, and not something PR
   #373 touched. Both track "how many footprints does the board have," but
   they are two independent numbers in two independent files, chased by
   two independent mechanisms. `pcb/temper.kicad_pcb` measures **168**
   footprints (`grep -c '(footprint ' pcb/temper.kicad_pcb`); the golden
   baseline still says 170. **This one is not historical — it is red on
   `main` right now:**

   ```
   REGRESSION: component_count: 168.0 vs baseline 170.0 (-2.0)
   ERROR: Regression detected for temper_production: component_count: 168.0 vs baseline 170.0 (-2.0)
   ```

   (`gh run list --workflow "Golden Regression Check" --branch main --limit 3`,
   confirmed failing on the run for `b39b382d`, the same commit PR #386
   landed as, 2026-07-29T06:07:59Z.)

   This instance is the strongest evidence in the set, because the file's
   own header comments show the baseline already being hand-chased twice
   in one day and failing a third time regardless:

   ```
   # 2026-07-27: component_count 149 -> 169, net_count 95 -> 106.
   ...
   # 2026-07-27 (second update): component_count 169 -> 170, net_count 106 -> 108.
   ...
   # This file has now gone stale twice in one day. It has no bless script and
   # no Ceiling-Approval gate -- scripts/bless_baselines.py governs only
   # power_pcb_dataset/corpus/<id>/baseline.json and errors with "not found in
   # manifest" for temper_production. Every legitimate board change therefore
   # requires a hand edit, which is precisely the drift-prone arrangement the
   # corpus baselines have machinery to prevent.
   ```

   The file's own comments already diagnose the mechanism correctly
   (`scripts/bless_baselines.py` doesn't reach `golden_manifest.yaml`
   boards, so `temper_production`'s baseline has no automated re-bless
   path and every legitimate board change requires a manual number edit).
   What they demonstrate, that the other three instances don't, is the
   *outcome* of trying to fix an absolute baseline by hand: two same-day
   manual corrections (149→169, then 169→170) each made the gate pass
   again, briefly, and neither addressed why the number would go stale
   again the next time the board changed shape — which it did, a third
   time, before this document was written. Chasing the number is not a
   fix; it resets the clock.

   **Not fixed here.** Per the discipline this document argues for
   (guidance item 2, below), the correct repair is the differential
   pattern PR #386 already demonstrated for the zone/pour baseline, or
   wiring `bless_baselines.py`/an equivalent shape guard to
   `golden_manifest.yaml` boards — not a fifth hand edit to the number.
   Hand-editing `component_count` to `168` would make this specific gate
   green again for exactly as long as the board's footprint count doesn't
   change, which is the anti-pattern this whole document is about.

All four are the same shape: **a number was recorded against one revision
of a mutable, regenerable artifact, and nothing re-checked whether the
artifact was still the one the number described.** None of the four
constants were wrong when written. All four were wrong by the time they
gated anything (three now fixed, one still red), and none of them said so
on its own.

A further mechanism compounded instance 3 specifically:
`_fill_zones_via_pcbnew` hardcoded `/usr/bin/python3` as the pcbnew
interpreter. That path **exists** on macOS but has no `pcbnew` module, so
the helper's own existence check passed and the import failed silently —
the entire zone/pour DRC test family skipped on every developer machine for
the six days between the bare-board measurement and the routed board,
which is exactly the window in which nobody could have caught the drift by
just running the test. PR #386 replaced it with `_resolve_pcbnew_python()`,
which probes candidates with a real `import pcbnew` (env override →
`/usr/bin/python3` → KiCad.app's bundled Python) rather than trusting a
path's existence to imply the capability behind it.

## Guidance

1. **An absolute threshold measured against a generated artifact needs a
   shape guard, not just a value.** PR #373's fix is not "raise the
   number" — it adds `_assert_baseline_board_shape()`, which asserts the
   board's footprint/segment/via/zone counts still match what the baseline
   was measured against *before* comparing violation counts, and fails
   with "re-measure" rather than silently judging a different board.
   Verified to fire: swapping in the pre-route board trips the shape
   assertion, not the violation-count assertion.
2. **Where possible, delete the stored number and measure both arms in the
   same run instead.** This is the strictly stronger fix, demonstrated by
   PR #386 on the zone/pour gate: `PRODUCTION_UNCONNECTED_POST_U4_BASELINE`
   is gone entirely, replaced by routing the same checked-in board twice
   (`enable_zone_pours=True` and `False`) in one test run and asserting the
   *relationship* between the two arms. This gate cannot go stale, because
   it never stores a fact about a specific past board — it only ever
   compares the board that exists right now to itself.
3. **A differential gate needs its own anti-vacuous-truth guard.** PR #386
   asserts the pours-on arm emits strictly more `(zone )` entries than the
   pours-off arm — otherwise a future refactor that made the flag a no-op
   would make both arms identically 396/396 for the wrong reason (the flag
   doing nothing) rather than the right one (the flag being redundant on
   this board), and nothing would distinguish the two.
4. **Decompose a growing violation count before treating a delta as a
   regression.** PR #373's breakdown (149→170 footprints while bare,
   +247; routing itself, +591; the remainder library-table drift) is what
   turned "the board got 849 violations worse" from an alarming headline
   into three separately-understood, separately-actionable causes — one of
   which (footprint growth) wasn't a defect at all.
5. **An existence check on a path is not a capability check.**
   `/usr/bin/python3` existing is not evidence it can `import pcbnew`. Any
   gate that decides whether to run based on `Path.exists()` for an
   interpreter, tool, or binary should instead attempt the real capability
   and treat "exists but can't do the thing" as a distinct, loud failure —
   not a silent skip that leaves a stale baseline unverified indefinitely.
6. **Hand-editing a stale absolute baseline to match today's artifact does
   not fix the staleness — it resets the clock on the same failure.**
   `power_pcb_dataset/baselines/temper_production_baseline.yaml`'s own
   header comments record two same-day manual corrections
   (`component_count` 149→169, then 169→170 the same day, 2026-07-27), and
   the gate is red again regardless (168 vs. 170) as of this writing. Each
   hand edit bought exactly as much time as it took for the next
   legitimate board change to land. A baseline with no automated re-bless
   path (`scripts/bless_baselines.py` reaches
   `power_pcb_dataset/corpus/<id>/baseline.json` but errors "not found in
   manifest" for `golden_manifest.yaml` boards like `temper_production`)
   will keep needing this same manual correction on every board change,
   forever — the fix is a shape guard or a differential gate, per items 1
   and 2, not a fourth or fifth hand edit.

## Why This Matters

None of these four thresholds were negligence at the time they were
written — 800, 1200, 260, and 170 were all real, correct measurements of
the board that existed when each was recorded. The failure was structural:
an absolute number has no way to say "this was true of a board that no
longer exists." `pcb/temper.kicad_pcb` moved at least four times in twelve
days (149 footprints bare → 169 → 170 → routed at 170 → resynced to 168)
and four independent gates, across three files plus a prose document, all
kept judging the current board by an earlier one's numbers. The
`/usr/bin/python3` bug compounded this specifically for the zone/pour
constant: not only did nobody re-measure it, nobody *could*, because the
test that would have caught the drift was silently not running at all on
the machine most likely to be used to check it. The golden-baseline
instance adds a fourth angle no code diff shows: **it is only visible by
running the gate, not by reading a diff.** `git show`/`git log` on the
five PRs this document otherwise draws from surface every other instance
directly in a commit message or code change; this one required running
`gh run list --workflow "Golden Regression Check"` and reading a live CI
log, because the failure is a data file disagreeing with a board file,
with no code change connecting them at all. Auditing "are our baselines
stale" by scanning recent diffs would miss this instance entirely — it
has to be asked of the gates themselves. The fix that generalizes is the
one PR #386 landed for zone/pour: a gate that measures the relationship
between two things computed *now* cannot drift, because it never
remembers a fact about *then* — and the golden-baseline instance is the
concrete proof that the manual alternative (re-chase the number by hand)
was tried, twice, on the same day, and failed both times.

## When to Apply

- Before hardcoding any DRC/quality/count threshold against a PCB,
  generated netlist, or other artifact that gets regenerated or re-placed —
  ask what happens to the gate the next time that artifact changes shape,
  and prefer recording the artifact's shape alongside the threshold so
  drift fails loudly instead of silently judging the wrong thing.
- When a fix to a stale baseline is available: prefer deleting the stored
  number for a differential (both-arms-same-run) comparison over simply
  updating it to today's value — an updated absolute number is exactly as
  stale-prone as the one it replaced.
- When a gate depends on a specific interpreter/tool/binary being present:
  verify the actual capability (`import <module>`, `<tool> --version`),
  not just that a candidate path exists on disk.
- When a violation/defect count grows across a change: decompose it by
  category and by known causes (artifact growth vs. the change under test)
  before reporting the raw delta as a regression.
- When a stale-baseline hunt relies on `git show`/`git log`/reading diffs:
  also check whether any CI workflow is currently red on `main` for a
  reason a diff wouldn't show — a hand-maintained baseline file compared
  against a generated artifact by a scheduled or push-triggered gate can
  drift with zero corresponding code change to find.
- Before hand-editing any baseline/golden file to make a red gate green
  again: check whether its own history (comments, prior commits) shows
  this has been done before. A second or third manual correction to the
  same number is itself the signal that the gate needs a shape guard or a
  differential rewrite, not another edit.

## Examples

```python
# test_regression_drc.py -- shape guard added by PR #373, checked before
# the violation-count assertions ever run
PRODUCTION_BOARD_BASELINE_SHAPE = {
    "footprints": 168,
    "segments": 2338,
    "vias": 48,
    "zones": 96,
}

def _assert_baseline_board_shape() -> None:
    ...  # compares the live board's counts to the recorded shape;
         # mismatch -> "re-measure", never a silent pass against stale numbers
```

```python
# test_zone_pour_production_measurement.py -- PR #386's replacement for the
# stale PRODUCTION_UNCONNECTED_POST_U4_BASELINE = 260 constant: both arms
# measured in the same run, against whatever board is checked in today
unconnected_off = route_and_drc(enable_zone_pours=False)  # 396, 396, 396
unconnected_on  = route_and_drc(enable_zone_pours=True)   # 396, 396, 396
assert zones_emitted(on=True) > zones_emitted(on=False)   # anti-vacuous-truth
# no stored baseline to compare against -- the relationship IS the gate
```

```
# power_pcb_dataset/baselines/temper_production_baseline.yaml -- hand-chased
# twice in one day (2026-07-27), stale again by the time this doc was
# written. Not fixed here: editing the "170" is the anti-pattern this
# document argues against, not a resolution of it.
# 2026-07-27: component_count 149 -> 169, net_count 95 -> 106.
# 2026-07-27 (second update): component_count 169 -> 170, net_count 106 -> 108.
# This file has now gone stale twice in one day. It has no bless script and
# no Ceiling-Approval gate ...
component_count: 170     # live board (pcb/temper.kicad_pcb): 168

# gh run list --workflow "Golden Regression Check" --branch main --limit 3
# REGRESSION: component_count: 168.0 vs baseline 170.0 (-2.0)
# ERROR: Regression detected for temper_production: component_count: 168.0 vs baseline 170.0 (-2.0)
```

## Related

- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — the sibling failure one layer out: a clean measurement from a stale
  *checkout*, rather than a clean threshold judging a stale *artifact*.
  Same root discipline (record what state produced a number), different
  surface (git history vs. a regenerable board file).
- `docs/solutions/best-practices/derived-documents-lose-qualifiers-2026-07-26.md`
  — a different STRATEGY.md failure mode (lossy summarization) found the
  same week as PR #371's stale board-fact fix in the same document.
- `docs/solutions/architecture-patterns/zone-pour-bounding-box-shorting-regression-2026-07-21.md`
  — the original 2026-07-21 measurement that produced the 260 baseline,
  on the board state this document's PR #386 instance found stale.
- `docs/solutions/logic-errors/tree-router-layer-selection-must-intersect-grids-2026-07-29.md`
  — the same PR #386 branch: fixing an unrelated `KeyError` un-masked this
  stale zone/pour baseline by letting the gate run for the first time in
  CI in a while.
- PR #371 (`df5e1db5`), PR #373 (`5b9c05db`), PR #386 (`b39b382d`) —
  three of the four fixes this document generalizes from. The fourth
  instance (the golden-regression baseline) is not tied to any of these
  PRs — it is an independently discovered, still-open failure in a
  separate file, included here for its own sake, not fixed as part of
  this documentation pass.
- `docs/evidence/2026-07-28-zone-pour-differential-verdict.md` — full
  measurement detail for the zone/pour instance, including the per-type
  violation deltas and the `/usr/bin/python3` root cause.
- `power_pcb_dataset/baselines/temper_production_baseline.yaml` — the
  live, still-red golden-regression baseline, including its own header
  comments recording two same-day manual corrections that didn't hold.
- `.github/workflows/golden-check.yml` (the *Golden Regression Check*
  workflow) and `scripts/bless_baselines.py` — the gate this instance
  fails in, and the re-bless mechanism that exists for corpus boards but
  doesn't reach `golden_manifest.yaml` boards like `temper_production`.
