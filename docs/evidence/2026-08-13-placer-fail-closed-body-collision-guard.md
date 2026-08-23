<!-- provenance: commit=96db2ccde669efa82d85fb494d5d152d8af8848f dirty=UNKNOWN -->

# A fail-closed F.Fab body-collision guard at the placer's solve chokepoint

Commit `de59c0458` (PR #602, 2026-08-03) moved 12 components in one
automated re-solve and created `C2xC3` -- two 35mm snap-in electrolytic
capacitors whose bodies interpenetrate by 7.73mm. Nothing in the pipeline
rejected it; it has been on the board ever since, visible only as an opaque
`courtyards_overlap: 8` ratchet number. PR #1168 (2026-08-13) reproduced the
defect deliberately: with the isolation barrier relaxed, `solve_placement`
returned `optimal` in 36-43s for placements that live `kicad-cli` DRC showed
carried 14 and 9 `courtyards_overlap` violations, including a new collision
up to 9.47mm -- worse than today's board.

This closes that gap: a post-solve audit that computes true `F.Fab` body
overlap and fails closed on any real interpenetration, wired into the one
place every produced placement passes through.

## 1. The chokepoint

`packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py::solve_placement`
is the single function every placement route funnels through:

- `temper-placer optimize --no-loop` calls it directly
  (`cli/__init__.py:855`).
- `temper-placer optimize --loop` (`PlaceRouteLoop.run`) calls it via
  `_loop_core.py::_LoopCoreMixin._call_solver`, which lazily imports and
  invokes the exact same `encoder.solve_placement` (grep confirms these are
  the only two call sites of `solve_placement(` in production code).

Both paths write the CP-SAT result to a `.kicad_pcb` file only after
`solve_placement` returns. This is where R24's three existing post-solve
audits already live (`audit_fixed_copper`, `audit_domain_clearance_validator`
via `validator_input`) -- the same discipline this guard extends: recompute
the real thing independent of the solver's own claim, and raise on a
feasible/optimal solve that produced a real violation.

## 2. What the guard computes, and why it is not fresh arithmetic

`packages/temper-placer/src/temper_placer/core/fab_body.py` (`FabBody`) and
`packages/temper-placer/src/temper_placer/placer/cp_sat/body_collision.py`
(`audit_body_collisions`).

**Rotation transform**: delegates to the same compiled kernel
`core/courtyard.py`'s `Courtyard.get_global_polygon` already uses --
`temper_geometry.courtyard_global_points_py` -- the KiCad-sanctioned
`R(-theta)` convention. `rotation_idx` is the 0-3 quadrant index
(`CpSatPlacementResult.rotations`' own contract), never degrees -- the exact
confusion PR #1167 documents four independent wrong answers from in one day.

**Extraction**: `io/fab_body_extraction.py::extract_fab_bodies` reads
`F.Fab`/`B.Fab` graphic items via `kiutils` (already a dependency, already
used by this package for `F.Fab` text in
`io/_parse_modules.py::_get_footprint_reference`) and reuses
`kicad_metadata.py::_courtyard_points_from_raw` VERBATIM for the
poly/circle/rect/line/arc hull-and-union merge -- the identical algorithm
`F.CrtYd` courtyard extraction already uses, fed a different layer's shapes.

**Boolean overlap**: `shapely`/GEOS polygon intersection area -- the same
"library boundary, not a kernel" posture `Courtyard.check_overlap` already
uses.

**Cross-validation, not just self-consistency.** This pipeline was checked
against two independent sources before being trusted:

1. PR #1158 (`docs/evidence/2026-08-13-courtyard-collision-characterization-and-remediation-plan.md`),
   an independent from-scratch S-expression parser with no shared code.
   Both reproduce identical world body centers for C2/C3 --
   `(98.48, 64.84)` / `(87.36, 39.94)` -- and identical classification for
   all 8 tracked `courtyards_overlap` pairs (measured here as overlap AREA
   in mm², not linear penetration depth, but zero-vs-nonzero classification
   and relative ranking match exactly):

   | pair | this guard's overlap area (mm²) | PR #1158's linear depth |
   |---|---|---|
   | C2 x C3 | 115.6512 | 7.728mm (worst) |
   | C5 x C7 | 106.8341 | 7.410mm |
   | C5 x L1 | 10.3219 | 1.560mm |
   | C4 x R46 | 5.1200 | 1.600mm |
   | C4 x C22 | 1.2800 | 0.800mm |
   | C4 x R4 | 0.0306 | 0.147mm (marginal) |
   | C3 x K3 | **0.0 (clear)** | clear, gap 0.390mm |
   | C2 x PS1 | **0.0 (clear)** | clear, gap 0.190mm |

2. Live `kicad-cli pcb drc --format json --severity-error pcb/temper.kicad_pcb`
   (`kicad-cli` 10.0.5, matching `drc_ceiling.json`'s recorded tool
   version): exactly these 8 `courtyards_overlap` pairs, no more, no fewer,
   reproduced in this worktree independently of both parsers above.

## 3. Distinguishing body collision from courtyard touch

The audit measures `F.Fab` body polygons only -- never `F.CrtYd`. A pair
whose bodies do not intersect (`intersection area <= 1e-6 mm²`, the
tolerance for floating-point boundary noise) is never a violation,
regardless of how much their courtyards overlap. `C3xK3` and `C2xPS1`
measure exactly `0.0` body-overlap area under this pipeline -- both are
part of the board's 8 tracked `courtyards_overlap` pairs, and neither ever
reaches the allowlist classification step (see
`test_body_collision.py::TestProductionBoardAllowlistCoverage`, which
asserts both are absent from *both* the violations and allowlisted
buckets).

## 4. Handling the existing 6 -- a ratchet, not a pass

The current board already carries 6 real `F.Fab` body collisions. Two
choices were rejected outright per the task brief's own warning ("a guard
that passes today's board unconditionally is the failure mode this repo
keeps hitting"):

- **Fix them here** -- out of scope; PR #1158 owns a live-kicad-cli-verified
  remediation plan (7 of 8 pairs have verified fixes; `C2xC3` needs a
  coordinated 4-body re-place). This PR does not move
  `pcb/temper.kicad_pcb`.
- **A vacuous allowlist** ("skip if the pair is already known") -- rejected
  because it would have let PR #1168's reproduction through: that re-solve
  made an *already-listed* class of collision WORSE (up to 9.47mm, this
  board's own worst case is 7.73mm) while still reporting `optimal`. A
  pass keyed only on pair identity cannot catch that.

**What was built instead**: `packages/temper-placer/configs/body_collision_allowlist.yaml`
pins the 6 pairs with their EXACT measured baseline overlap area (full
double precision, not the rounded mm figures in the table above) plus
provenance (board sha256, commit, `kicad-cli` version, measurement date)
and a `review_by` date pointing back at PR #1158 as the pairs' remediation
owner. `audit_body_collisions` permits a listed pair only **at or below**
its recorded baseline:

- a pair not on the allowlist with real body overlap -> hard failure
  (`kind="new"`);
- a pair on the allowlist whose resolved overlap EXCEEDS its baseline ->
  hard failure (`kind="worsened"`) -- this is what would have caught
  PR #1168's reproduction, not just a brand-new pair appearing;
- a pair on the allowlist at or below baseline -> reported on
  `CpSatPlacementResult.body_collision_audit.allowlisted`, never raised.

This is not free to extend: adding a pair to the allowlist requires a
measured baseline, not a guess, and the file's own header states the
allowlist "must not become a general-purpose escape hatch."

## 5. Proof it bites, and does not false-positive

`packages/temper-placer/tests/placer/cp_sat/test_body_collision.py` (18
tests, all passing), plus `tests/core/test_fab_body.py` (6) and
`tests/io/test_fab_body_extraction.py` (4). Highlights:

- **`TestSolvePlacementBites::test_new_body_collision_rejects_a_solve_the_box_model_missed`**
  -- two components whose declared solver box (`comp.bounds=(0.1,0.1)`) is
  small enough that CP-SAT's own courtyard/no-overlap machinery is fully
  satisfied (status `optimal`/`feasible`) at 1mm center separation, but
  whose TRUE `F.Fab` bodies (radius-3mm circles, independent of
  `comp.bounds`) collide badly -- exactly the class of defect PR #1158
  section 3.3 flags as the open hypothesis for how `C2xC3` happened
  (`comp.bounds` not carrying the real footprint envelope into the
  solver). `solve_placement(..., body_collision_input=...)` raises
  `RuntimeError` naming the pair and "physically unassemblable."

- **`TestSolvePlacementBites::test_benign_courtyard_touch_on_the_real_board_passes`**
  -- `C3`/`K3`, pinned via `fixed_positions` at their EXACT committed board
  coordinates, run through the real `solve_placement` chokepoint with their
  real extracted `F.Fab` geometry. Passes cleanly: `status` is
  optimal/feasible and `body_collision_audit.clean` is `True`.

- **`TestProductionBoardAllowlistCoverage::test_real_board_is_clean_against_the_real_allowlist`**
  -- the real, committed board (`pcb/temper.kicad_pcb`, positions/rotations
  read directly, no solve involved) against the real, checked-in
  `configs/body_collision_allowlist.yaml`: `clean` is `True`, exactly the 6
  allowlisted pairs are reported (matching the allowlist's own key set
  exactly), and `C3xK3`/`C2xPS1` are absent from both buckets.

- **`TestAuditBodyCollisions::test_allowlisted_pair_worse_than_baseline_is_a_violation`**
  -- the #1168 regression class, minimized: a pair on the allowlist with a
  baseline set below what the resolved geometry actually produces still
  fires (`kind="worsened"`).

- **`TestAuditBodyCollisions::test_bodies_clear_is_never_a_violation_even_unallowlisted`**
  and **`test_bbox_broad_phase_does_not_miss_a_real_collision`** -- the
  cheap bounding-box pre-filter used for O(n^2)-pair performance does not
  suppress a real, non-adjacent collision.

## 6. Verification checklist

- [x] `scripts/check_stale_extensions.py` -- 10/10 fresh (`make venv-isolate`
      run in this worktree; every one of the 10 extensions explicitly
      import-checked, not just freshness-checked).
- [x] `make netlist` run in this worktree.
- [x] `uv run --no-sync python scripts/import_linter_gate.py` -- PASSED,
      0 new violations.
- [x] No `scripts/*.py` gate script added -- the guard lives in
      `solve_placement`/the CLI, not a standalone CI script, so
      `gate_input_registry._CI_SCRIPT_SURVEY` (which tracks
      `.github/workflows/python-tests.yml` script invocations) does not
      apply; confirmed no new files under `scripts/`.
- [x] `pcb/temper.kicad_pcb` sha256 unchanged throughout
      (`b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6`).
- [x] No clearance/creepage/safety value or ratchet ceiling changed.
- [x] `git status --porcelain` / `git grep -l "^<<<<<<< "` clean before
      every commit.
- [x] Pre-existing test failures (`tests/cli/test_optimize_no_loop.py`'s 4
      round-trip-oracle failures, `tests/placer/cp_sat/test_validator_audit.py::TestProductionBoardSolve::test_free_k3_solve_is_inter_clean_and_k3_intra_surfaces`,
      `tests/placer/cp_sat/test_erc_gate.py::TestErcGateCheck::test_erc_clean`)
      reproduced identically against the unmodified base commit
      (`a3fbaff37`, verified via a throwaway `git worktree` + `PYTHONPATH`
      override) -- unrelated to this change, not newly introduced by it.
