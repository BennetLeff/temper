<!-- provenance: commit=79860da9d8abfed78e6c7344836c4bc9db55a356 dirty=false -->

# Re-baseline: `test_checker_copper_distance_is_lower_bound_on_origin_distance` (stale board-state expectation, invariant verified sound)

**Date:** 2026-08-02
**Branch:** `triage/checker-lower-bound-2` (worktree `.claude/worktrees/agent-checker-triage-r2`)
**Base:** origin/main `e5bd461e276b65d0499f0ecd4a9ff29309f2c1bd` (verified via `scripts/assert-base.sh origin/main`).
**Issue:** R22 triage of a persistently failing invariant test, dispatched against
`tests/placer/cp_sat/test_clearance_repair.py::TestRealBoardClearanceRepair::test_checker_copper_distance_is_lower_bound_on_origin_distance`.

## Verdict: stale board-state expectation (category a), NOT a broken invariant (category b)

The test asserts a metamorphic, provable relation: the copper-to-copper
checker's reported distance must never fall below the sound origin-based
lower bound `origin_dist - reach_A - reach_B`. On the current board that
**relation holds everywhere**; the test fails because its *baseline*
assertion (`assert inter`, expecting inter-component REQ-SAFE-01
violations to exist) encodes a board that no longer exists.

## Distinguishing numbers (measured 2026-08-02 on origin/main e5bd461e2)

| measurement | value |
|---|---|
| `verify_iec60335_compliance` total records | 3 |
| inter-component violations (`pair_kind != "intra"`) | **0** |
| intra-footprint records | 3, all K3 (ref_a == ref_b == "K3") |
| K3 measured copper-to-copper | 3.558846 mm (below 4.0/6.0/8.0 bars) |
| distinct inter pairs the checker's sound-origin prune lets through (measured set) | 114 |
| of those, measured with the `copper` geometry model | 114 (0 via origin proxy) |
| of those, below the sound bound `copper >= origin - reach_A - reach_B` | **0** |
| of those, "optimistic" (copper < origin) | 93 (81.6%) |
| all distinct inter pairs across every IEC boundary row | 11,571 |
| of those, below the sound bound | **0** |
| `_reach` parity: test-side reach vs checker's internal reach | 0 diffs (bit-identical) |

The checker's own prune (`clearance._check_distance` line 510:
`model.lower_bound(ref_a, ref_b) >= min_mm -> pruned`) is exactly the
relation under test, and it is sound: 0 of 11,571 pairs on the board
violate `copper >= origin - reach_A - reach_B`. The 114 pairs the checker
does measure are all copper-model and all above their sound bound. The
optimistic majority (93/114, copper < origin) reproduces the historical
relation the 2026-07-28 doc measured ("the old origin-only checker was
optimistic on a large majority of flagged pairs").

## Root cause: the board changed under the test, in the direction of *fewer* violations

The test was added by #504 (`2677ae087`, merged 2026-07-31 via PR #522)
against a board carrying **123 inter-component violations** under the
PD3/12.6 mm counterfactual. That same week the board was re-solved:

| commit | PR | change | effect on inter violations |
|---|---|---|---|
| `55226f8ad` | #517 (merged #521, 2026-08-01) | PD2/8.0 mm placement re-solve with the full 54-net manifest classification, 11,908 domain-clearance + 518 keep-away constraints | 23 placement-fixable inter pairs -> 0 |
| `0f0a13412` / `27ea686c5` | #524 | K2 relay -> TE Schrack RT314012 | K2 leaves the intra blocker set |
| `a2fdfd1bb` | #568/#579 (merged #579, 2026-08-02) | nudge edge-hanging refs inward (K2 +18.2 mm; 29 refs 0.01-0.03 mm) | REQ-SAFE-01 unchanged at 3/1 K3-intra |

Documented in `docs/evidence/2026-07-31-pd2-clearance-resolve.md`
("53 -> 6 violations across 2 pair(s)... K2/K3 intra only"; "0 total is
NOT reachable by placement... K2/K3 are the provable floor") and in the
sibling re-baseline `docs/evidence/2026-08-01-safety-test-rebaseline.md`
(branch `fix/safety-test-rebaseline-2`, same base). The lower-bound test
was *not* included in that sibling re-baseline; this commit completes it.

The edge-hanging evidence doc already listed this test as a pre-existing
failure on origin/main ("fail[s] identically on origin/main" — `2026-08-01-edge-hanging-refs-fix.md` line 120), consistent with the root
cause being #517's re-solve, not #568.

## The re-baselined test (fail-closed, non-vacuous)

The original test checked the sound bound only on *violating* inter pairs
and required at least one to exist. On a board with 0 inter violations
that is vacuous-failing. The re-baselined test:

1. **Asserts the documented baseline**: `assert not inter` (0
   inter-component violations — if the board ever regresses to any, this
   fails) and pins the intra floor to exactly `{"K3"}` (the documented,
   #518/#523-tracked blocker). Fail-closed: any NEW inter violation or a
   change to the intra floor fails loudly instead of passing silently.
2. **Keeps the invariant non-vacuous and strictly stronger**: the sound
   bound `copper >= origin - reach_A - reach_B` is now asserted on **every
   inter pair the checker actually measures** (the 114 survivors of its own
   sound-origin prune across all IEC rows), not just the violating subset.
   This is the exact set whose numbers the prune trusts, so it is the
   decision-relevant set for the safety property.
3. **Asserts every measured pair used the `copper` geometry model** (never
   the optimistic origin proxy) and keeps the optimistic-majority count
   over the measured set.

No production code is touched. The checker is unchanged and verified
sound; this is a test-side re-baseline of a stale board-state expectation,
following the `fix/safety-test-rebaseline-2` convention.

## Gates

- ruff: clean on the touched test file (checked before commit).
- Import linter: 0 new violations (imports added match existing precedent
  in this suite — `IEC60335_REQUIREMENTS`, `_nets_domain_map`,
  `_domain_boundary_pairs`, `_CopperModel`).
- The re-baselined test passes; the full `tests/placer/cp_sat/` suite has
  only the documented pre-existing failures (see evidence provenance in
  the landing commit).
- Evidence provenance: this file's first line declares
  `provenance: commit=79860da9d8abfed78e6c7344836c4bc9db55a356 dirty=false`
  (the landing branch-tip SHA).

## Honest limits

- The numbers describe the board as committed at `e5bd461e2`. Any later
  board change that moves K3, re-swaps its footprint, or reintroduces an
  inter-component violation fails these assertions with a clear measured
  vs expected message — that is the intended fail-closed behavior.
- The exhaustive 11,571-pair invariant check is O(pairs) and ~0.1 s, but
  the committed test checks the checker's measured set (114 pairs, the
  decision-relevant set) to keep runtime in the tens of milliseconds;
  the full-board number is recorded here as the stronger evidence that the
  bound is a geometric law, not a property of the prune threshold.
