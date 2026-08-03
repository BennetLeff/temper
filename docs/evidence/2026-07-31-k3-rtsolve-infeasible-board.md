<!-- provenance: commit=ba02616f140f69092784651f2a60a49bbfccb428 dirty=false (branch fix/k3-relay-placement, board restored byte-identical to origin/main 251841703a...; every solve measurement in this doc ran in a clean tree at HEAD 733aa0861 against the restored board) -->

# K3 RT314012 re-solve attempt — the scoped CP-SAT solve is infeasible on the current board

**Date:** 2026-07-31
**Branch:** `fix/k3-relay-placement` (worktree `.claude/worktrees/agent-k3resolve`),
from `origin/main` `becaf34a9` (PR #524, K2 relay swap, merged).
**Scope:** attempt to land the K3 (discharge.k_dis2) RT314012 swap together with a
placer re-solve (FREE set {K2, K3, C27}) per the scoped K3+tank3 plan. **Outcome:
the scoped solve is genuinely infeasible; the board is restored to main's exact
state; the placer machinery (PR #504) is delivered on this branch instead.**

## TL;DR

The plan's T4 formulation — pin every ref except {K2, K3, C27} at its current
position and satisfy the 12.6mm domain-clearance constraints for the free set —
is **provably infeasible on the merged board**, for four independent, each
sufficiently-fatal reasons. None of them is a solver bug; all are the board's
pre-existing distance to the placer's own model (the debt #504/#517 already
documented), plus one genuine model-quantization interaction. The plan's
relaxation ladder (free D4/R18/U6, widen K3 region, drop C27) does not address
any of them. Per the plan's own rule ("if genuinely infeasible, STOP and report
with the unsat evidence"), the solve is stopped and reported here.

T2 (elec unblock) and T3 (K3 board embed-swap) were landed, verified green
against every non-DRC gate, and then **reverted** because the T3 intermediate
board (K3's RT314012 at its current origin, pre-placement) is a measurable DRC
regression (shorting_items 118 -> 137) — leaving it in the branch would have been
worse than main. The branch now carries main's board byte-identical plus the PR
#504 clearance-repair machinery (cherry-picked, tests green), which is the
dependency the future board solve will need.

## 1. T1 — the re-solve machinery is now on the branch

`origin/main` did **not** have the fixed-rotations / min-displacement /
clearance-repair machinery (grep for `fixed_rotations`/`clearance_repair`/
`AnchoredConstraint` in `packages/temper-placer/src` returned nothing). The two
PR #504 commits (`2677ae087`, `150f495a9`, branch `fix/clearance-resolve-
reroute-loop`) were cherry-picked. Two mechanical conflicts in `_encoder_solve.py`
(HEAD's `fixed_positions` feature vs the cherry-pick's `minimize_displacement_to`
/`fixed_rotations`/`max_displacement_mm`) were resolved additively (both features
kept); `docs/plans/README.md` was regenerated. Full `tests/placer/cp_sat/` suite:
**461 passed, 1 skipped, 1 xfailed** (13m49s).

## 2. T2/T3 — landed, verified, then reverted

- **T2 (elec):** `k_dis2` pointed at `RT314012` / `temper:Relay_SPDT_Schrack-RT314012`,
  BLOCKED notes replaced with history-preserving comments. `make netlist`: build
  complete, all assertions PASSED; BOM shows `RT314012,"K2,K3"`.
- **T3 (board):** K3's embedded G5LE-1 block replaced in-place with the RT314012
  geometry at its origin (47.8, 70.78) rot 0, pads carrying nets BY NUMBER
  (pad 1=COM/`DC_BUS_RTN`, 2=`discharge.k_dis2-coil1`, 3=NO, 4=NC, 5=coil2 —
  shared coil2 net `discharge.k_dis1-coil2`, matching K2's convention), K3's
  tstamp/properties kept, unique uuids (`c4a1e2xx`). Verified green:
  `check_copper_net_consistency` PASSED (518 pads), `check_footprint_drift`
  PASSED (169/169), `check_pad_orientation` PASS, `check_domain_partition`
  PASSED. Immediate REQ-SAFE-01 effect at the unchanged origin: **122 -> 117
  errors, 87 -> 86 pairs, intra 8 -> 5** (K3's own 3.559mm coil-to-contact
  records cleared — the RT314012's 12.76mm internal gap passes the 12.6mm bar).
- **Why reverted:** the T3 board at the current origin shorts copper (that is the
  #523 blocker). Measured DRC (3 samples, deterministic): shorting_items 118 ->
  **137**, courtyards_overlap 14 -> 16, hole_clearance 109 -> 123, solder_mask_bridge
  69 -> 88, errors 840 -> 895, warnings 678 -> 685. A branch carrying a known new
  shorting regression is worse than main; both commits were reverted (the elec
  unblock and the board swap must land together or not at all, or the
  netlist/board footprint drift gate fails).

## 3. T4 — the scoped solve: why it is infeasible (four independent walls)

All measurements below were taken on the **restored** board (identical to
main). Constraint generation and solving used `temper_placer.placer.cp_sat`
with `generate_domain_clearance_constraints` (12.6mm bar, PD3 — #515 not
merged), `generate_unclassified_hv_keepaway_constraints`, `solve_placement`
with `hint_positions`, `fixed_positions`, `fixed_rotations`,
`minimize_displacement_to`, `max_displacement_mm`, seed 0.

### 3.1 Wall 1 — exact-position pins are impossible for edge refs (model quantization)

`CpSatModel.mm_to_units` rounds to the nearest **even** integer (required by the
midpoint identity `x_start + x_end == 2*x_center`). A ref whose box edge sits at
exactly the 0.5mm board margin has an even-rounded center that pushes the edge
*below* the margin:

- C23 (0603, bounds 2.96 x 1.46) at local (149.40, 1.23): `mm_to_units(1.23)` =
  123 -> even-rounded to **122**; y_start = 122 - 73 = 49 units < the 50-unit
  margin. Pinning C23 at its exact board position is UNSAT (minimal unsat core:
  exactly one entry, `edge_margin_C23`). The same class hits R25, U19, and every
  ref parked within 0.01mm of an edge margin (~11 refs measured).
- The plan's pin primitive (fixed_positions/AnchoredConstraint) therefore cannot
  pin the board as built. A <=0.02mm nudge to the nearest even-safe center fixes
  the *class*, but then Wall 2/3/4 below still apply.

### 3.2 Wall 2 — NoOverlap2D: 31 pre-existing box overlaps among pinned refs

The encoder wires `NoOverlap2D` unconditionally over all 169 refs. The current
board has **31 bounding-box overlaps** between refs that must stay pinned
(measured with the model's own effective sizes, rotation-swapped):
C1/R7, C3/C4 (two 35mm bus electrolytics at 17.0mm center distance — genuinely
touching), C14/C5, C24/R8+R9, C8/R12+R4, D4/R2, ... This is the tracked
`courtyards_overlap` 14-16 DRC debt; the placer's box model sees it too and
cannot have both refs pinned. Even with *no* extra constraints and *no* free
set beyond {K2,K3,C27}, the solve is UNSAT (`git`-verified, `status=infeasible`
in <1s). Freeing the 26-40 involved refs moves the solve to Wall 3/4.

### 3.3 Wall 3 — SEPARATED-tau and netclass cross-class constraints are violated at pinned positions

- The courtyard-clearance τ (0.4mm = 0.2 default + 2x0.1 mask expansion) is also
  subject to the even-rounding boundary class: e.g. C2/R13 have float separation
  0.40mm exactly, but model-integer separation 39 < 40 units — a pinned pair the
  τ constraint rejects.
- `configs/netclass_rules.yaml` adds cross-class SEPARATED constraints at 6.0mm
  for HV<->LV pairs (HighVoltageIsolated/HighVoltage/ACMains vs Signal/Power).
  The current board violates 6mm box-separation for many of these pinned pairs —
  the same debt the REQ-SAFE-01 copper checker reports (122 records on main).
  These constraints are generated by the encoder itself, not by the caller's
  constraint list, so a scoped caller cannot exclude them.

### 3.4 Wall 4 — the 12.6mm domain bar, even scoped to the free set, forces a full re-layout

With the free set {K2,K3,C27} (plus the refs Walls 1-3 force free), the scoped
domain constraints (K2/K3/C27 vs ~150 cross-domain refs each, 12.6mm box-edge
separation) have **no feasible region that keeps the rest of the board in
place**:

- Soft-pinning via `minimize_displacement_to` does not help: on this 169-ref
  model CP-SAT returns `feasible` (not `optimal`) with a poor objective — 105
  refs fly 200mm+ even in a *pure-geometry* solve with *no* extra constraints
  (objective 423408 units ≈ 4234mm), because refs absent from the objective have
  no incentive to stay and hints are non-binding. A 240-600s budget does not
  materially improve the objective (verified at 120s/240s/300s/600s).
- Any solve that satisfies the 12.6mm bar moves the free refs 30-280mm (K2 from
  y=95.5 to y=37.1; C27 from off-board y=252.75 to y≈73) and the independent
  copper-level checker **worsens** (REQ-SAFE-01 117 -> 183 errors) because the
  scatter creates new violations. This reproduces, for the scoped 3-ref case,
  the exact #504/#517 finding: "a placement that clears REQ-SAFE-01 at 12.6mm
  is necessarily a full re-layout" (their measured 22,686mm displacement).

### 3.5 Why the plan's relaxation ladder does not apply

- "free D4/R18/U6" — those refs are *not* the infeasibility cause; the causes
  are the edge/overlap/τ/netclass violations spread across 40+ pinned refs and
  the 12.6mm bar itself.
- "widen K3 region" (zones) — does not touch any of Walls 1-3 (pinned refs).
- "drop C27 to a secondary solve" — C27 is not the blocker; single-ref solves
  (K3 alone, K2 alone, C27 alone) are each infeasible at 12.6mm box level with
  all other refs pinned (measured: `status=infeasible` for every single-ref
  scoped solve).

The plan's rule is explicit: *NEVER weaken a constraint to pass; if genuinely
infeasible, STOP and report with the unsat evidence.* No constraint was
weakened; the solve is stopped. Unsat evidence: minimal core `edge_margin_C23`
(1 entry) for the quantization class; `status=infeasible` cores of 19-22k
assumptions for the combined runs (the hard SEPARATED constraints are not
assumption-decorated, so the "sufficient" core is uninformative — the wall-by-
wall isolation above is the evidence).

## 4. Board state left behind

- `pcb/temper.kicad_pcb`: **byte-identical to origin/main** (sha256
  `251841703a...51c0`).
- `elec/src/modules.ato`, `elec/domain_manifest.yaml`: **identical to
  origin/main** (k_dis2 back on G5LE-1 with the BLOCKED note).
- Gates on the branch: `check_copper_net_consistency` PASSED (515 pads),
  `check_footprint_drift` PASSED (169/169), `check_domain_partition` PASSED,
  `check_pad_orientation` PASS, `mpn_fabrication_gate` PASSED,
  `check_measurement_provenance` matches the recorded hash (board unchanged).
- Added to the branch: the PR #504 clearance-repair machinery (2 commits) with
  its full test suite green.

## 5. What unblocks the K3 swap (recommendations, in order)

1. **The board's geometry debt must be paid before any scoped pin solve is
   possible.** Walls 1-3 all stem from refs sitting at model-boundary positions
   or in genuine overlaps. A future solve must either (a) accept a
   geometry-repair pre-pass that nudges the ~40 conflicting refs (up to ~20mm
   for C3/C4, C14/C5 — real overlaps) and write those positions, or (b) land
   the #517 full re-layout that the 12.6mm bar demands (the project's
   documented, deferred decision).
2. **Or reduce the bar**: the 12.6mm box-separation constraint is far stricter
   than the copper-level requirement the REQ-SAFE-01 checker actually gates on
   (#504 §conclusion). A copper-accurate constraint (per-pad domain copper
   boxes) is the follow-up constraint-model change that would shrink the
   required displacement; it is out of scope here.
3. K3's physical blocker (#523: RT314012 pads short copper at every rotation of
   its current origin) is a geometry problem that a DRC-verified positional
   search could solve today; the repo's precedent says placement is the
   placer's job, and the placer is infeasible until (1) or (2) lands — so the
   blocker stands, tracked.

## 6. Commits on the branch

- `84c263a98` feat(placer): minimum-displacement clearance repair machinery (#504) [cherry-picked]
- `742a6fdcd` fix(placer): type-check and vulture-gate cleanliness for repair machinery (#504) [cherry-picked]
- `6f49254d2` feat(elec): unblock K3 discharge relay (k_dis2) onto TE Schrack RT314012 [reverted by 733aa0861]
- `334d34fe9` feat(pcb): embed-swap K3 discharge relay footprint to temper:Relay_SPDT_Schrack-RT314012 [reverted by e56b1d841]
- `e56b1d841` Revert "feat(pcb): embed-swap K3 discharge relay footprint..."
- `733aa0861` Revert "feat(elec): unblock K3 discharge relay (k_dis2) onto TE Schrack RT314012"

## Reproduction

```bash
git fetch origin main
git worktree add .claude/worktrees/agent-k3resolve -b fix/k3-relay-placement origin/main
cd .claude/worktrees/agent-k3resolve
make netlist
# T1 machinery tests:
UV_PROJECT_ENVIRONMENT=/Users/bennet/Desktop/temper/.venv \
  uv run --no-sync pytest packages/temper-placer/tests/placer/cp_sat/ -q
# Wall 1 (minimal unsat core, pin C23 at its exact board position):
UV_PROJECT_ENVIRONMENT=/Users/bennet/Desktop/temper/.venv \
  uv run --no-sync python - <<'PY'
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat import solve_placement
r = parse_kicad_pcb("pcb/temper.kicad_pcb")
pos = {c.ref: c.initial_position for c in r.netlist.components if c.initial_position}
rot = {c.ref: int(c.initial_rotation or 0) for c in r.netlist.components if c.initial_position}
hints = {ref: (x, y, rot[ref]) for ref, (x, y) in pos.items()}
res = solve_placement(netlist=r.netlist, board=r.board, extra_constraints=None,
                      timeout_ms=45000, seed=0, hint_positions=hints,
                      fixed_positions={"C23": (*pos["C23"], rot["C23"])},
                      fixed_rotations=rot)
print(res.status, [u["name"] for u in res.unsat_core])  # infeasible [edge_margin_C23]
PY
```
