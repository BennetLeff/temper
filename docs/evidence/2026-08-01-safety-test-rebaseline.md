<!-- provenance: commit=611b0c349563d5ecfe9c8788f9d3cf75a674da83 dirty=false -->

# Safety-suite re-baseline: REQ-SAFE-01 board-clearance and intra-footprint-blocker assertions

**Date:** 2026-08-02
**Branch:** `fix/safety-test-rebaseline-2` (worktree `.claude/worktrees/agent-test-rebaseline-r2`)
**Base:** origin/main `e5bd461e276b65d0499f0ecd4a9ff29309f2c1bd` (verified via `scripts/assert-base.sh origin/main`).
**Measurements at:** branch tip `611b0c349` (clean tree, full `tests/requirements/safety/` suite green: 108 passed).
**Issue:** #523 (K3 G5LE-1 gap / RT314012 swap blocked), plus the board changes under the tests: #517 (PD2/8.0mm re-solve), #524 (K2 -> TE Schrack RT314012), #568/#579 (edge-hanging refs nudge).

## Why this re-baseline is not a ratchet-loosening

Two safety-suite tests on `main` asserted board states that no longer exist.
The board changed under them; the assertions did not. Each change is
attributable to a specific, merged, documented PR -- not to an unexplained
regression -- and each re-baselined assertion encodes the CURRENT measured
state while remaining fail-closed for any NEW violation. The 0-violation
state test 1 asserted was the pre-#517/pre-#524 board; test 2's
`{"K2","K3"}` blocker set was the 2026-07-30 PD2-adoption set, written
before #524's relay swap landed the next day.

This follows the discipline of
`docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md`:
an absolute baseline that judged a past board is re-anchored to measured
reality and -- where possible -- to a *structural* assertion (inter == 0,
intra pinned to exactly the documented pair) rather than a bare number that
can silently absorb the next board change.

## Board changes under the two tests (each commit is on origin/main)

| commit | PR | what changed | effect on the two tests |
|---|---|---|---|
| `55226f8ad` | #517 | re-solve placement to clear all 23 placement-fixable REQ-SAFE-01 pairs at PD2/8.0mm | test 1: 56 records / 24 pairs (copper-to-copper, 2026-07-28 measurement) -> 3 records / 1 pair |
| `0f0a13412` / `27ea686c5` | #524 | swap K2's footprint to TE Schrack RT314012 (internal coil<->contact 12.76mm vs G5LE-1's 3.559mm); K3's swap blocked | test 2: K2 leaves the intra-footprint blocker set |
| `a2fdfd1bb` | #568/#579 | nudge edge-hanging refs inward (K2 +18.2mm y; 29 refs by 0.01-0.03mm); REQ-SAFE-01 unchanged at 3/1 K3-intra | positions move; violation set unchanged |
| `da902db9f` | #582 | DRC ceiling re-measure for #568 | no effect on REQ-SAFE-01 |

The K3 RT314012 swap remains blocked on placement (issue #523;
`docs/evidence/2026-07-31-k2k3-relay-swap-placement.md`), so K3 stays on
the G5LE-1 -- the remaining genuine intra-footprint blocker.

## Test 1: `TestClearanceIntegration::test_temper_board_clearance_compliance`

**Before (on origin/main e5bd461e2):** FAILED. The test asserted
`assert not failures` with an unconditional 0-violation expectation. Actual
result: `3 REQ-SAFE-01 clearance/creepage violations across 1 pair(s)
(3 of the records are intra-footprint)`.

**After (re-baselined, this change):** PASSED, asserting the measured state:

- **0 inter-component violations** (`assert not inter`) -- the documented
  current state has none; ANY new inter-component violation fails the test.
- **Exactly 3 intra-footprint records**, all `ref_a == ref_b == "K3"`,
  all measured **3.558846mm** copper-to-copper, with the (metric,
  insulation, required-bar) rows pinned to exactly:
  - (`creepage`, `basic`, 4.0)
  - (`clearance`, `reinforced`, 6.0)
  - (`creepage`, `reinforced`, 8.0)
- The geometry model is asserted `== "copper"` (never the optimistic
  origin-to-origin proxy).

**Measured numbers (2026-08-02, origin/main e5bd461e2 board):**

| record | boundary | metric | insulation | measured | required | shortfall |
|---|---|---|---|---|---|---|
| 1 | DC_BUS<->LV_CONTROL | creepage | reinforced | 3.558846 | 8.0 | 4.441154 |
| 2 | DC_BUS<->LV_CONTROL | clearance | reinforced | 3.558846 | 6.0 | 2.441154 |
| 3 | DC_BUS<->LV_CONTROL | creepage | basic | 3.558846 | 4.0 | 0.441154 |

Closest copper: `K3.1(DC_BUS_RTN) <-> K3.2(discharge.k_dis2-coil1)`.
K3 is the G5LE-1 discharge relay 2 at board-file `(at 69.72 29 90)`.
The BASIC *clearance* 3.0mm bar passes (3.559 > 3.0); the three bars
4.0/6.0/8.0 fail. This matches the documented state verified in
`docs/evidence/2026-08-01-runb-audit-lie-reproduction.md` sec 4
("REQ-SAFE-01 = 3 records / 1 pair / 3 intra, all K3<->K3 intra",
measured 3.5588mm) and the earlier
`docs/evidence/2026-07-31-k2k3-relay-swap-placement.md`.

**Fail-closed check (verified directly, not assumed):** injecting an
inter-component pair (parking an LV ref 0.05mm from K3's HV pad) produces
inter violations that the new `assert not inter` catches.

## Test 2: `TestRealBoardIsolatorFigures::test_the_seven_known_intra_footprint_blockers_are_now_visible`

**Before (on origin/main e5bd461e2):** FAILED.
`assert {"K2", "K3"} <= intra` -- measured `intra={'K3'}`. K2 was asserted
present in the blocker set but #524's relay swap cleared it.

**After (re-baselined, this change):** PASSED, asserting the measured set:

- `"K3" in intra` (still the genuine blocker; 3.558846mm measured, ~4.4mm
  short of the 8.0mm REINFORCED bar and below the PD-independent 6.0mm
  clearance minimum).
- `"K2" not in intra` (cleared by #524's RT314012 swap; asserted absent so
  a reversion of the swap is caught).
- `"C6" not in intra`, `"K1" not in intra`, `"T1" not in intra`,
  `"U3" not in intra`, `"U7" not in intra` (cleared by the PD2/8.0mm
  target; unchanged from the prior version of the test).
- `intra == {"K3"}` -- the measured current blocker set, exactly.

**Measured blocker set (2026-08-02, origin/main e5bd461e2 board):**
`intra = {"K3"}` -- confirmed by re-measurement, not assumed. K2 (now
RT314012) is absent; the five PD2-cleared refs (C6, K1, T1, U3, U7) are
absent; K3 is present.

## Full-suite result (this branch)

```
uv run --no-sync pytest tests/requirements/safety/ -q
108 passed in 37.00s
```

All 108 tests in `packages/temper-placer/tests/requirements/safety/` pass
on this branch. No remaining failures; nothing hidden. (Two additional
real-board tests in the suite -- `test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`
and `test_isolator_pad_gap` -- were already green on main and remain green.)

## Files changed

- `packages/temper-placer/tests/requirements/safety/test_clearance.py` --
  re-baselined `test_temper_board_clearance_compliance` (commit `8df1ea261`).
- `packages/temper-placer/tests/requirements/safety/test_clearance_copper.py`
  -- re-baselined `test_the_seven_known_intra_footprint_blockers_are_now_visible`
  (commit `611b0c349`).
- `docs/evidence/2026-08-01-safety-test-rebaseline.md` -- this document.

No changes under `packages/temper-placer/src/` and no changes under
`pcb/` -- validation-only, per the task's standing constraints. The board
file itself was not touched; the assertions were re-measured against it.

## Gates

- ruff: clean on both touched test files (checked before commit).
- Import linter: no new violations (no imports changed).
- Full `tests/requirements/safety/` suite: 108 passed.
- Evidence provenance: this file's first line declares
  `provenance: commit=611b0c349 dirty=false` (full 40-char SHA; the branch
  tip at which the full suite was verified green on a clean tree).

## Honest limits

- The re-baselined numbers describe the board as committed at
  `e5bd461e2` (origin/main at dispatch time). If a later board change
  moves K3 (or re-swaps its footprint), these assertions will fail closed
  with a clear "measured X, expected 3.558846mm" / "got intra=..." message
  -- that is the intended fail-closed behavior, not a need to re-ratchet.
- K3's 3.558846mm figure is the G5LE-1's fixed terminal topology; it will
  only disappear when the #523-blocked RT314012 swap lands. Until then the
  test asserts the documented reality rather than a fictional pass.
