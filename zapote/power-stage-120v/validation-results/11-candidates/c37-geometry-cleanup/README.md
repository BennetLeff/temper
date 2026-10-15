# Candidate 37: post-route track-geometry cleanup (stage 37)

DECISIONS 43 measured native-21's track geometry and planned a fix: "a deterministic post-route cleanup pass (remove
fold-backs, mitre right angles, open acute corners, snap any-angle runs where clearance allows) … applied as a final
global pass after the island lanes merge". This candidate builds that pass and proves it on the board of record, s35.

**Verdict: ACCEPT** (draft decision in `DECISIONS-DRAFT.md`; the number is assigned at merge).
- Chain `native21s37` reached CHAIN_DONE on board `1900b038…`. DRC: 0 errors, 0 unconnected, and the same warning
  set as s35.
- The scorecard compare is ACCEPT against s35, s32 and 19c. Against 19c it was REJECT before, only on item 43's
  geometry ratchets.
- Track geometry, s35 → s37:

| Metric | s35 | s37 |
|---|---|---|
| Right-angle corners | 104 | **50** |
| Acute corners | 206 | **23** |
| Fold-backs (part of the acute count) | 44 | **3** |
| Any-angle track | 704.4 mm | **308.4 mm** |

- No electrical metric got worse (section 4).
- A second run of the pass on its own output changes nothing (section 5).

**Basis:**
- Stage 35: copper.json `085c80be…`, board `fba59ef3…`, export `native-21/verification/native21s35-all-copper.json.gz`.
- Branch `claude/native21-geometry-cleanup` from `codex/power-stage-integration` at `8bf12675c`, 2026-10-15.
- Stage tag `native21s37`.

**This pass touches every island.** It must run last: after the other lanes merge, re-run it on the merged copper and
then run the chain again. It is safe to re-run on any later board:
- it reads the board's own export;
- it refuses an export whose tracks are not that copper's segments;
- a converged board gives 0 edits.

## 1. The tool

`native-21/layout/track_cleanup21.py COPPER.json BOARD-all-copper.json.gz [--out OUT.json] [--report R.json]`

It is a post-route transform of a finished copper.json, like `gates/trim_tails.py`. It is not an `add_stageNN` patch:
it needs the built board as its obstacle model (pad shapes per layer, zone fills as KiCad filled them, the outline),
and it has to see the final copper of every lane. `patches21.py` and `gates/README.md` say so.

The four steps, in order. Each step repeats until it accepts nothing more. Then the whole sequence runs again,
retrying every skipped item, until a full round changes nothing.

1. **Fold-backs.**
   - Free tip (nothing at the tip): the tip is dead copper. The track runs straight between its two neighbours, on the
     polyline whose copper already covers that run.
   - Tip on a pad or via: the shorter arm lies on the longer one, so it is a duplicated segment. The copy goes, and the
     shorter track starts where the overlap ends. That leaves a T junction; the copper is unchanged apart from the
     duplicate.
2. **Acute corners.**
   - Free tip: the corner becomes the octilinear tangent polygon of a circle tangent to both arms, with turns of at most
     45°. A 45° corner becomes 3 × 135°.
   - If the arms are too short for that, the shorter arm leaves the longer one square, at the foot of its far end. The
     tip beyond the foot is redundant copper. This trades the acute corner for a right angle.
   - Tip on a pad or via: the shorter arm leaves the longer one square, at the foot of its far end. The result is a T
     with two 90° angles, and the longer arm keeps the tip.
   - An arm that lies wholly inside the tip's pad or via copper is dropped.
3. **Right angles.** Free tips are mitred with the same tangent polygon, giving 2 × 135°.
   - The radius starts at 5.1 × the track width. That is a mitre leg of 3 × the width, and at least 0.5 mm; on a
     0.25 mm track the leg is 0.75 mm.
   - The radius steps down to the track width. Below that, the inner edge of the copper would keep its sharp corner,
     so a smaller mitre would be cosmetic only.
   - A leg uses at most half an arm when the arm's far end is another corner.
   - A mitre between two widths goes on the wider polyline, so nothing narrows.
4. **Any-angle segments** become an octilinear dogleg: one diagonal piece and one orthogonal piece, with a 135° bend.
   Both variants are tried. Pieces must be at least 0.05 mm long, and at least 1 mm at a track end that joins only by
   overlap (otherwise KiCad reports the short end piece as dangling).

An edit is kept only if every check below holds. Otherwise the next smaller candidate is tried, and if none passes the
item is left with its reason (section 6). The checks:

- **net:** res_a (RES_A creepage copper) and the OCP sense nets are never edited. The OCP sense nets are ocp_kelvin_p /
  ocp_kelvin_n / ocp_node / ocp_thresh, which carry the Kelvin and pickup budgets.
- **spine:** no removed or added segment touches the SELV-spine lock region, and no fill inside that region can change.
- **clearance:** the added copper (new minus old) keeps clear of every other-net item on its layer by
  `rules21.clearance_on` + 0.02 mm. That covers tracks, vias, pads and fills; because fills count, no fill has to
  retreat. The added copper also keeps:
  - 0.3 mm from holes and 1.0 mm from fiducials;
  - 0.5 mm from the edge;
  - the 8.0 mm plan-view barrier on every layer;
  - out of the protected pours.
- **barrier:** the added copper is no closer to the other side of the barrier, or (on F / B) to the RES_A 12.6 mm
  counterpart, than the copper it replaces. The exception is copper at least 25 mm away. So the barrier, D5 and RES_A
  outer minima can only stay equal or improve.
- **fill:** where removed copper lets another net's fill grow, the growth area must be:
  - at least 11 mm from the other side of that fill's barrier (the gate minima are 8.05 mm);
  - at least 25 mm from a RES_A pair;
  - outside the spine region.
- **connect:** the net's connectivity uses KiCad's anchor rule: a track end inside another item; pads and vias join a
  fill they touch. It must split the pads, vias and fills into exactly the same groups as before, with no new floating
  group or dangling end.
- **metric:** on the net and layer, the counts must not get worse in severity order (fold-backs, acute, right angles),
  the step's target must improve, and at most 2 mm of any-angle track may be added.

Pads, vias, zones, widths and parts never move. KiCad DRC in the chain stays the authority.

**Controls.** `native-21/layout/test_track_cleanup21.py` has 45 checks, all passing
(`results/test_track_cleanup21.txt`):
- each fix: a free fold-back, a fold-back at a via, a 45° acute corner (→ 135°), a right angle (→ 2 × 135°), an
  any-angle segment;
- a dogleg blocked by other-net pads on both sides, skipped for clearance;
- a corner whose tip a third track joins by overlap, skipped for connectivity;
- res_a left alone;
- a mitre beside a pad that falls back to a smaller legal one;
- a SELV dogleg 8.5 mm from HOT copper that bends away from it;
- every case: connectivity unchanged, and a second run applies nothing.

`gates/test_track_geometry.py` still passes (7 / 7).

## 2. The run on s35

The pass is reproducible from committed files and deterministic: re-running it on the same inputs gives a
byte-identical copper.json, `f24e4bf8…`. The run:

```sh
git show 8bf12675c:zapote/power-stage-120v/native-21/layout/copper.json > s35-copper.json          # 085c80be…
sh validation-results/11-candidates/c37-geometry-cleanup/passes37.sh s35-copper.json \
   native-21/verification/native21s35-all-copper.json.gz $RUNS/p1      # cleanup + one build
sh native-21/layout/gates/chain.sh native21s37 $RUNS/p1/b $RUNS/c2
```

There were 625 edits (`results/cleanup-s35-to-s37.json`; its `log` lists each one):

| Step | Edits | F.Cu | In1.Cu | In2.Cu | B.Cu | How |
|---|---|---|---|---|---|---|
| Fold-backs | 39 | 28 | 2 | 4 | 5 | 5 free tips removed; 34 duplicate overlaps at pad / via tips |
| Acute corners | 136 | 97 | 9 | 13 | 17 | 32 free (tangent mitre or square merge); 104 at pad / via tips (square T) |
| Right angles | 69 | 49 | 12 | 3 | 5 | 52 mitred; 17 arms inside pad / via copper dropped |
| Any-angle | 381 | 293 | 16 | 29 | 43 | octilinear doglegs |

Board-wide effects:
- Track length went from 10,377.4 to 10,275.5 mm (−101.9 mm).
- Segments went from 3,936 to 4,306.
- 100 nets were touched. The most edits were on n_ls (81), v15_ls (46), v3v3 (35), selv_gnd (28) and leg_ret (26).

Per layer:

| Layer | Right s35 → s37 | Acute | Fold-backs | Any-angle mm |
|---|---|---|---|---|
| F.Cu | 70 → 29 | 141 → 13 | 32 → 2 | 501.0 → 202.5 |
| In1.Cu | 20 → 8 | 15 → 3 | 3 → 1 | 64.3 → 45.5 |
| In2.Cu | 5 → 3 | 23 → 4 | 4 → 0 | 59.3 → 31.9 |
| B.Cu | 9 → **10** | 27 → 3 | 5 → 0 | 79.7 → 28.5 |

B.Cu gains one right angle. That is an acute corner (on a short arm) traded for a right angle by the square merge.

Visual record: `results/panels-{fold,acute,right,any}.png`. Each shows 24 random edits per step, with s35 copper in
grey and s37 in blue (`scripts/panels.py`).

## 3. Chain `native21s37`

**CHAIN_DONE**, board `1900b038f54a9b0b1effac574c0cb4aa733dc6a2a186ef6371fe360840ff7ae5`, Gerber ZIP `f6756eba…`.

| Gate | s35 | s37 |
|---|---|---|
| DRC errors / unconnected / plane splits | 0 / 0 / 0 | 0 / 0 / 0 |
| DRC warnings | lib 199, silk 199 + 199 + 21 | identical |
| Barrier (plan view 8 mm), Rust gate | 0 violations | 0 violations |
| RES_A outer 12.6 mm | 0; min F 20.393 / B 13.375 | 0; min F 20.393 / B 13.375 |
| D5 HOT–SELV / HOT–PE | 8.047 / 8.507 | 8.047 / 8.507 |
| DFM | PASS, 750 vias, min track 0.2 | PASS, 750 vias, min track 0.2 |
| SPINE_LOCK (owner none) | PASS | PASS |
| FIT | 401 / 0 / 0 / 403 / 0 | 401 / 0 / 0 / 403 / 0 |
| Bypass / return path / PI / RES_A creepage 18 | PASS | PASS |
| CPL audit, BOM / CPL designators | 349 / 349, PASS | 349 / 349, PASS |

- The Rust gate's census rises from 5,783 to 6,153 items (RES_A outer F 972 → 1,036, B 522 → 533). This is the item
  count, which tracks the larger segment count, not a distance.
- **Chain fix (separate commit `ea9093c49`).** The first s37 chain stopped with `BLOCK FAILED: thermal`, although
  every gate had run. The cause: `run_basis.py` exits 1 on a FAIL verdict, and the thermal block runs under `set -e`.
  The B3 ratings release gate FAILs on every board today (DECISIONS 46), so every lane's chain would stop there.
  - The verdict is the scorecard's to read; the comment in chain.sh already said so. The exit status is now ignored.
  - The existing check that `margins.json` was solved on this board still fails the block if the basis did not run.
  - The re-run reached CHAIN_DONE.
- **Test points.** The chain's board-only planner (`plan_board_only21.py`) re-plans the bring-up test pads from the
  copper on every run. It samples each track every 0.5 mm from its start. Where a track was re-shaped, three test points
  and one reference point moved along their own net's copper:

| Test point | Net | s35 | s37 | Moved |
|---|---|---|---|---|
| TP3 | v15_ls | 113.05, 98.595 | 113.95, 98.595 | 0.90 mm |
| TP4 | v24_raw | 118.2, 79.6 | 118.6, 80.55 | 1.03 mm |
| TP7 | bus_fault_hot | 101.6, 74.9 | 101.1, 74.9 | 0.50 mm |
| TP30 (TP7's reference) | ocp_kelvin_p | 103.75, 74.095 | 103.396, 74.449 | 0.50 mm |

  `BRINGUP-PROBES.md` and the labels follow. No schematic part, pad or via moved.

## 4. Scorecard

`validation-results/10-benchmark/scorecard-native21s37.json`, compared in `results/compare.txt`:

- `ACCEPT native21s37 vs s35`: better on b3_laminate_margin_K, b3_rated_part_margin_K and all four track-geometry
  metrics; nothing worse.
- `ACCEPT vs s32`: also cheaper on parts_usd_at_500 and hand_or_consign_lines, which come from stage 35.
- `ACCEPT vs 19c`. This was REJECT for s35, only on item 43's strict acute and fold-back ratchets: 206 vs 198 acute,
  44 vs 35 fold-backs.

Every card field that moved, s35 → s37:

| Field | s35 | s37 | Why |
|---|---|---|---|
| track_right_angle_corners | 104 | 50 | the pass |
| track_acute_corners | 206 | 23 | the pass |
| track_fold_backs | 44 | 3 | the pass |
| track_any_angle_mm | 704.4 | 308.4 | the pass |
| b3_laminate_margin_K | −56.4 | −56.3 | body-model laminate peak 0.1 K lower |
| b3_rated_part_margin_K | −38.9 | −38.8 | rated-part peak 0.1 K lower |
| b3_c28_h25_peak_C (reference only, not compared) | 135.0 | 135.3 | legacy single-cell peak, a mesh artefact (DECISIONS 46) |

The other electrical results are unchanged or better:
- **Task 04:** 39 scenarios, 0 failed; bus_p span 2.835 % (unchanged). The only change above 0.01 % is hv_dc: R and
  loss are 0.011 % lower (shorter copper). Everything else moved by less than 1e-4 relative, or is numerical noise
  below 1e-10 W.
- **Kelvin:** band 67.77–116.44 A, R_eff R35.2 152.9 mΩ (unchanged).
- **Return path:** 18 open changes, worst asserted 2.72 mm (unchanged).
- **Necks** (`shoot-through-f1/s37_necks.json`): every segment identical; min ratio 0.993.
- **OCP pickup** (`coil-pickup/s21b/result-s37.json`): pan-60 stack 4.1729 against 4.1730 A, so 4.17 A on the card.
  ref25 was edited and the OCP sense nets were not.
- **Legacy B3 peaks** (reference): c28_h10 192.3 → 192.6, extreme_h10 247.1 → 241.5 °C. They are not compared; these
  single-cell peaks move 40–50 K with the mesh.

## 5. Idempotence

`track_cleanup21.py native-21/layout/copper.json native-21/verification/native21s37-all-copper.json.gz` gives
**0 edits** (`results/cleanup-s37-second-run.json`). That is the s37 copper against its own rebuilt and refilled
board. The export check passes, so the export is that copper's build.

The first version of the tool did not converge: it skipped an item for the rest of the run once it failed. On s35's
output a second run then made 5 more edits. Every round now retries every skipped item, and the pass stops when a
whole round applies nothing (commit `f86dc8ae8`). The unit tests check a second run on every case.

## 6. What the pass could not fix, and why

These are the items left on s37, with the reason from the last round (`results/cleanup-s37-second-run.json`, `left`).
The counts are corners; fold-backs are also counted among the acute corners.

**Right angles (50):**

| Reason | F.Cu | In1.Cu | In2.Cu | B.Cu |
|---|---|---|---|---|
| Square exit from a pad: both tracks leave the pad, and the inner corner lies inside the pad copper (no copper corner) | 15 | | | |
| Square exit from a via: the same, inside the via ring | 4 | | 1 | 1 |
| Corner tip on a pad (not covered) | 1 | | | |
| Arms too short for a mitre of radius ≥ the track width | 9 | | 2 | 8 |
| Locked OCP sense nets (ocp_kelvin_p In1 Kelvin run) | | 7 | | |
| Clearance: inside the protected ocp_kelvin_p pour | | 1 | | |
| SELV-spine lock region | | | | 1 |

**Acute corners (20, plus the 3 fold-backs):**

| Reason | F.Cu | In1.Cu | In2.Cu | B.Cu |
|---|---|---|---|---|
| SELV-spine lock region | 5 | | 1 | 1 |
| Locked OCP sense nets | 3 | 1 | | |
| Metric: no improvement, or the fix would add a fold-back or right angle | 2 | | 2 | 2 |
| Clearance: v3v3 fill | | 1 | | |
| Fill growth near the barrier | | | 1 | |
| Pad tip with no trunk to merge onto | 1 | | | |

**Fold-backs (3):** 2 on F.Cu where the arm widths or the polyline shape (a fold inside one polyline, with nothing at
the tip) are not handled, and 1 on In1.Cu where fill growth near the barrier stopped the fix.

**Any-angle (308.4 mm in 286 segments):**

| Reason | Segments | mm | Layers |
|---|---|---|---|
| Clearance (other-net fills, pads, tracks, protected pours, H1) | 40 | 117.5 | F 73.0, In1 24.4, In2 18.5, B 1.6 |
| Room: dogleg pieces under 0.05 mm (near-octilinear short escapes), or under 1 mm at an overlap-joined end | 182 | 64.8 | F 42.6, B 9.1, In2 8.3, In1 4.8 |
| Barrier: the dogleg would come closer to the other side | 7 | 47.8 | F 46.0, B 1.8 |
| Metric: the dogleg would add a right or acute corner at an end | 13 | 32.6 | In1 16.3, F 10.7, In2 2.9, B 2.6 |
| SELV-spine lock region | 27 | 25.3 | B 13.4, F 11.9 |
| Locked nets (res_a / OCP sense) | 17 | 20.4 | F 18.3, In2 2.1 |

What would fix more:
- **Spine items:** the SELV lane can run the same tool with the region unlocked, then re-issue the lock (its own
  DECISIONS item).
- **Locked nets:** each needs its own owner with the Kelvin, pickup and RES_A budgets re-run.
- **Long any-angle runs** blocked by clearance or the barrier: these need re-routing, not a dogleg.

## 7. Open items

1. Re-run the pass after the island lanes merge, then the chain. The pass is the final global step (DECISIONS 43).
2. If test points should stay put across copper edits, `plan_board_only21.py` could keep a still-legal previous spot.
   It is not changed here.

## Files

- `native-21/layout/track_cleanup21.py`, `test_track_cleanup21.py`; `patches21.py` note; `gates/README.md`.
- `passes37.sh`: the pass on stage 35's copper and one build.
- `results/`:
  - `cleanup-s35-to-s37.json`: the edit report with every edit and the skip reasons;
  - `cleanup-s37-second-run.json`: the idempotence run;
  - `track-geometry-s3{5,7}.json`;
  - `compare.txt`;
  - `test_track_cleanup21.txt`;
  - `panels-*.png`.
- `scripts/panels.py`: before / after panels.
- **Runs** (`worktrees/runs-native21/geo`, outside the repo): `p1` (the pass and its build) and `c2` (the accepted
  chain build).
