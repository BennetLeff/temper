# D-9: adversarial review of the D-4 follow-up work

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

D-4 (`out-D4/`) found real defects. This reviews the work done in response,
before its results are relied on. Same format and standard as D-4.

## Scope

Commits on `codex/power-stage-120v-build` from `f5a1c8083` through the head
at the time you start (use `git log --oneline f5a1c8083^..HEAD -- round17`
under `zapote/power-stage-120v/validation-results/01-switching-parasitics/`).
In particular:

1. **Grid fixes** (`d2/grid.py`, `d2/test_grid.py`): does the identity
   really cover everything that changes a result (simulator version?
   `common/options.inc`? criteria constants?) Can the ZVS verdict or cause
   labels still mislead?
2. **Identity checks** (`scripts/inductance_matrix.py`, `extrapolate.py`,
   `d2/run_d2.py`, `scripts/margin_correct.py`): construct inputs that pass
   the checks but are wrong.
3. **Campaign provenance** (`scripts/campaign.py` manifest): what changes a
   result without changing a hashed file?
4. **Bulk current mode** (`d2/bulk_mode.py`, `results/bulk-mode/`): is the
   slew comparison meaningful (numerical differentiation at a 0.2 ns step,
   window choice)? Is the "estimate" reasonable? Is the 5-port response
   (`closures-legA5.json`, the A5 crop in `scripts/mesh25d_hybrid.py`,
   `d2/leg_matrix5.cir`, `d2/make_deck5.py`) the right fix — port
   placement, orientation, C5 left on a heuristic path, ESL reuse?
5. **Margin correction** (`scripts/margin_correct.py`,
   `results/matrices/`): the additive transfer from the coarse h = 1 mesh to
   the fine h → 0 matrix — what would make it wrong, and what test would
   show it?
6. **Grid v2 conclusions** (`d2/README.md`, "Grid v2"): are the stated
   conclusions supported by `results/grid-h0-lin12-v2/`?
7. **Signed pair checks** (`scripts/pair_check.sh`) and any results by the
   time you start: is the comparison a real independent check?

## Deliverable

`round17/delegation/out-D9/README.md`: ranked findings (P1/P2/P3) each with
location, concrete failure scenario, and decision/check — as D-4 did — plus
what was checked and found sound. Reproductions as committed scripts.

## Acceptance

Every finding is demonstrated or explicitly labelled as an unverified
concern; no edits outside `out-D9/`.
