# Zone/pour does not reduce unconnected items — measured differentially, U4 should not promote

**Date:** 2026-07-28
**Board:** `pcb/temper.kicad_pcb` @ 168 footprints / 2,338 segments / 48 vias / 96 zones
**Tool:** kicad-cli 10.0.4, zones pre-filled with `pcbnew.ZONE_FILLER` (KiCad 10.0.4 bundled Python)
**Measured by:** this branch, locally — **not** taken from CI

## Two separate problems, only one of which was the gate's fault

`test_zone_pour_production_measurement.py` failed with:

```
enable_zone_pours=True did not reduce unconnected_items (395 >= 260 baseline).
```

That message was **not trustworthy**, for the same reason PR #373 documented in
`test_regression_drc.py`: `PRODUCTION_UNCONNECTED_POST_U4_BASELINE = 260` was
measured on 2026-07-21, when the board held 149 footprints and *zero copper*.
Since 556ccf4f (2026-07-27) the board ships 2,338 segments / 48 vias / 96
zones. The gate was comparing zone/pour on **this** board against a number
from **that** board — a bare-board figure reused as a routed-board budget.

So the first question was whether the accusation survives a valid comparison.
It does. The two problems are independent:

1. **The comparison was broken.** Fixed by measuring both arms in the same run.
2. **Zone/pour genuinely does not help.** Confirmed by the fixed comparison.

Re-baselining the constant would have "fixed" #1 by hiding #2.

## The differential measurement

Both arms routed from the same checked-in board, in one run, zones filled,
DRC sampled 3× each (routing is deterministic; only DRC scatters):

| | `enable_zone_pours=False` | `enable_zone_pours=True` |
|---|---|---|
| `(zone )` entries emitted | 96 | 192 |
| completion_rate | 0.3854 | 0.3854 |
| **`unconnected_items`** | **396** (396/396/396) | **396** (396/396/396) |
| total violations (median) | 1687 | 1831 |

`unconnected_items` shows **zero scatter in either arm** across three samples,
so the null result is not hiding inside DRC noise. An independent N=3 run of
the same harness reproduced it exactly (396/395/396 vs 395/396/396).

Per-type deltas (ON − OFF):

| type | delta |
|---|---|
| `zones_intersect` | **+96** |
| `isolated_copper` | +35 |
| `shorting_items` | +16 (inside the documented ±32 scatter) |
| `clearance` | −1 |
| `tracks_crossing` | −1 |
| **`unconnected_items`** | **0** |

## The cause

The board already ships 96 filled zones. `enable_zone_pours=True` adds
**exactly 96 more** — and produces **exactly 96 `zones_intersect`
violations**, one per added zone. The router re-pours nets that the committed
board already pours, on the same layers. The duplicates overlap the originals,
add 35 more isolated copper islands, and connect nothing that was not already
connected.

This also explains why the old 260 figure once looked achievable: it was
measured when the board had *no* zones at all, so pouring had real work to do.
On a board that pours itself, the feature is redundant.

## Verdict

**U4 promotion should not proceed**, and the gate is correctly red. This is not
a stale-number artifact — both arms were routed and DRC'd in the same run
against the checked-in board, and the gate now carries no stored baseline at
all, so it cannot drift again.

The decision of what to do next is a promotion decision, not a test fix:

* improve zone/pour so it contributes on an already-poured board (e.g. pour
  only nets with no existing zone on that layer), or
* retire this gate on the grounds that the board now supplies its own pours.

Moving a threshold to make the gate green is neither, and would re-hide the
finding this measurement exists to surface.

## Test changes

* `PRODUCTION_UNCONNECTED_POST_U4_BASELINE` **deleted** — replaced by a
  differential comparison that cannot go stale. Deliberately no
  `PRODUCTION_BOARD_BASELINE_SHAPE` equivalent: that guard exists in
  `test_regression_drc.py` to protect hardcoded numbers, and there are none
  left here to protect.
* Anti-vacuous-truth guard added: the pours arm must emit strictly more zone
  entries than the no-pours arm, or the two arms are one measurement compared
  against itself.
* The failure message now carries both arms' full samples and the per-type
  deltas, so a red build states the finding instead of two bare numbers.

## Why this was measurable at all

`_fill_zones_via_pcbnew` hardcoded `/usr/bin/python3` as the pcbnew
interpreter. That path **exists** on macOS but has no pcbnew, so the helper's
existence check passed and the import failed — every test in this family
skipped on every developer machine, which is why the 260 constant sat
unverified while the board changed underneath it.

Replaced with `_resolve_pcbnew_python()`, which probes candidates with a real
`import pcbnew` (env override → `/usr/bin/python3` → KiCad.app's bundled
Python), mirroring `gates._resolve_kicad_footprint_dir`. Every number in this
document was produced on macOS through that resolver.

## UNVERIFIED

* Whether pouring *only* nets that lack a committed zone would reduce
  `unconnected_items`. That is the obvious next experiment; it was not run
  here because it is a feature change, not a measurement.
* CI (Linux, KiCad 8.0.9) has not yet re-run the rewritten gate. The failure
  is expected to reproduce — it is a property of the board and the feature,
  not of the DRC version — but the numbers above are macOS/kicad-cli 10.0.4.
