# K3 RT314012 relay swap at the #517-re-solved position — placement measurement, 2026-08-01

<!-- provenance: commit=6af87796f727ba385a043ef587d12efff04bc90e dirty=false -->

## Summary

K3 (discharge.k_dis2), the last REQ-SAFE-01 board blocker, is swapped from
the Omron G5LE-1 to the TE Schrack RT314012 at its **#517-re-solved
position (69.72, 29.0)**, rotation **90.0** — the orientation measured to
clear REQ-SAFE-01 **completely** (0 violations, down from 3, all K3
intra-footprint 3.559mm) with **zero new cross-net shorts** (all five
pre-existing K3-attributed shorting_items records are removed), **zero
courtyard regression** (courtyards_overlap stays 11), and an error total
that **falls** (1329 → 1309, DRU-regenerated measurement; 1037 → 1030,
bare run_drc).

The prior K3 swap (2026-07-31, reverted as 334d34fe9) failed at the
**pre-re-solve** origin (47.8, 70.78): every rotation shorted copper there.
The #517 placement re-solve moved K3 clear of that copper; this change
re-evaluates the swap at the **new** position, mirroring how K2's swap
failed at its old position but landed at the re-solved one.

## 1. Board state

- K3 at (69.72, 29.0) rot 90.0 on the G5LE-1 (current main) →
  K3 at (69.72, 29.0) rot **90.0** on the RT314012 (this change).
- Swap template: K2's serialized RT314012 block (same geometry, same
  `temper:Relay_SPDT_Schrack-RT314012` footprint, pad numbers renumbered
  1..5 per the project's Relay_SPDT convention). K3's tstamp preserved
  (3b259aaf-...), Reference → K3, Sheetpath → discharge.k_dis2, fresh
  uuid range `c4a1e2xx` (the range the reverted prior swap used, verified
  free). Nets carried **by pad number** from the old G5LE-1 block:
  pad 1=COM/`DC_BUS_RTN`, 2=coil1, 3=NO, 4=NC, 5=coil2 (shared coil2 net
  `discharge.k_dis1-coil2`, matching K2's convention).
- Pad absolute angles set to the footprint rotation (the .kicad_pcb
  convention documented in scripts/check_pad_orientation.py; a library
  pad at local 0 placed at rotation R serializes with angle R).

## 2. Rotation sweep at the re-solved position (N=5 DRC + REQ-SAFE-01 each)

Measured with `temper_placer.validation._drc_api.run_drc` (kicad-cli
10.0.4, `--all-track-errors`), bare (no DRU regenerated — the standing
measurement contract; the CI-exact DRU-regenerated numbers are in §4).

| rotation | error total | courtyards | K3-attributed shorts | REQ-SAFE-01 |
|---|---|---|---|---|
| base (G5LE-1) | 1031-1036 | 11 | 5 distinct (discharge.k_dis1-coil2 × nc, × safety.coil_thermal.comp-inp; k_dis2-nc × k_dis1-nc, × comp-inp) | **3** (K3 intra 3.559 ×3) |
| **0** | 1026-1032 | 11 | 3 (DC_BUS_RTN × k_dis1-nc; k_dis2-nc × k_dis1-nc; k_dis2-no × k_dis1-nc) | 2 inter (K3<->C37 7.656, K3<->C28 7.755) + 1 unclassified proximity (C10 2.324) — **worse** |
| **90** | 1022-1027 | 11 | **0** | **0 — PASSES** |
| 180 | 1026-1031 | **14** (K3 courtyards 15 records) | 0 | 0 (but courtyard regression) |
| 270 | 1028-1033 | **14** (K3 courtyards 15 records) | 1 (RTD_SDI × k_dis2-no) | 7 (K3<->R74 0.063!, K3<->R60 3.582) — **much worse** |

**Chosen: rotation 90** — the only orientation that simultaneously (a)
clears REQ-SAFE-01 entirely (the mission's primary goal), (b) removes
every pre-existing K3-attributed cross-net short (0 remaining), (c) keeps
courtyards_overlap at the base count 11 (no regression), and (d) lowers
the error total below base. Rot 0 fails REQ-SAFE-01 (2 inter + 1
unclassified proximity finding — C10 at 2.324mm from K3). Rot 180 passes
REQ-SAFE-01 but regresses courtyards_overlap 11 → 14 (15 K3-attributed
overlap records) and pth_inside_courtyard 4 → 8. Rot 270 is a REQ-SAFE-01
catastrophe (K3<->R74 at 0.063mm). Rot 90 mirrors K2, which also landed at
rot 90 at its re-solved position — the footprint's narrow axis fits the
solved neighbourhood.

## 3. REQ-SAFE-01 before/after (copper-to-copper, real-board fixture)

`test_temper_board_clearance_compliance`:

| | before | after |
|---|---|---|
| violations / pairs | 3 / 1 (all K3 intra, 3.559mm) | **0 / 0** |
| intra-footprint | 3 | 0 |
| full-coverage cross-check | 3 | 0 |
| unclassified proximity findings | 0 | 0 |

The K3 G5LE-1 coil-to-contact 3.559mm records are **cleared**: the
RT314012's 12.760mm internal gap (independently recomputed from the
footprint geometry: pad 2 coil1 edge to pad 4 NC edge = 15.26 − 1.5 − 1.0
= 12.760mm) passes the 8.0mm reinforced bar (1.6x) and the 6.0mm
pollution-degree-independent minimum (2.1x). The companion test
`test_the_seven_known_intra_footprint_blockers_are_now_visible` was
updated (it had been red on main since the K2 swap cleared K2): it now
asserts K2 and K3 are absent from `intra` and that `intra == set()` —
recording the fix, not weakening it (a regression that re-adds any
intra-footprint blocker is still caught).

## 4. DRC ceiling re-measurement (the CI-exact invocation)

Per the 2026-08-01 precedent (commit aac25dde5): the standing measurement
contract for the ceiling file is **120 samples of run_drc with
pcb/temper.kicad_dru FIRST regenerated from scripts/generate_kicad_dru.py**
— exactly what ci_check_drc.py does. Bare run_drc never reports the DRU's
`creepage`/`track_width` categories, so the CI-exact invocation is the one
the gate enforces. Measured on the committed board (kicad-cli 10.0.4,
`--all-track-errors`, 120 samples, N=120 deterministic):

| category | base (G5LE-1) | **after (K3 RT314012 rot 90)** | ceiling | Δ vs recorded |
|---|---|---|---|---|
| annular_width | 4 | 4 | 4 | 0 |
| clearance | 406-407 | **400-401** | 402 | 440 → 402 (**−38**) |
| copper_edge_clearance | 12 | 12 | 12 | 0 |
| courtyards_overlap | 11 | 11 | 11 | 0 |
| creepage | 196 | **193** | 194 | (NEW; 32 recorded → 194) |
| drill_out_of_range | 4 | 4 | 4 | 0 |
| hole_clearance | 124 | **118** | 118 | 132 → 118 (**−14**) |
| hole_to_hole | 3 | 3 | 3 | 0 |
| shorting_items | 199-200 | 199-200 | 201 | 202 → 201 (**−1**) |
| solder_mask_bridge | 163 | **158** | 158 | 163 → 158 (**−5**) |
| track_width | 199 | 199 | 199 | (NEW; 0 recorded → 199) |
| tracks_crossing | 3 | 3 | 3 | 0 |
| via_diameter | 4 | 4 | 4 | 0 |
| **error total** | **1329** | **1309** | **1313** | 1010 → 1313 |

Warnings: lib_footprint_issues 10 → 11 (K3 now references the project
`temper` library, reported "not enabled" — same class as T1/C6/U7/K2),
lib_footprint_mismatch 24 → 23 (K3's embedded copy now matches its library
footprint), silk_edge_clearance 4 → 6 (RT314012 silk at rot 90), all else
unchanged. warning total 428 → 430.

**Every delta attributed:**

- **clearance −38** (440→402): the #517 solve's PD2/8.0mm separation
  win, extended by the K3 swap (the RT314012's pads sit clear of LV
  copper at rot 90). Placement-class, all decrease.
- **creepage 32→194**: NEW category in the CI-exact (DRU-regenerated)
  measurement — the recorded 32 came from the old DRU path; the current
  DRU rules (regenerated identically for base and swapped board) report
  196 base / 193 after. The **−3** base→after is the K3 swap's doing
  (contacts clear of LV copper); the 32→196 baseline shift is the
  pre-existing DRU-rules/design-rules state, unchanged by this swap,
  already recorded by aac25dde5's measurement of the K2 board.
- **track_width 0→199**: NEW category from the DRU's custom track-width
  rule (the same 199 aac25dde5 recorded — pre-existing, unchanged by the
  K3 swap).
- **hole_clearance −14** (132→118): RT314012's THT holes at rot 90 clear
  the neighbourhood better than the G5LE-1's — the swap doing its job.
- **solder_mask_bridge −5** (163→158): RT314012 pad apertures bridge
  less copper — the swap doing its job.
- **shorting_items −1** (202→201): K3's five pre-existing shorting
  records removed (see §2); the 118→202 rise was the #517 solve's
  documented mechanism, not this swap.
- **warnings +2**: lib_footprint_issues +1 (K3's temper-library
  reference, same class as K2's), lib_footprint_mismatch −1 (K3 copy now
  matches library), silk_edge_clearance +2 (RT314012 silk at rot 90) —
  all three the direct, measured consequence of the footprint swap.

Rises requiring the Ceiling-Approval trailer on the landing commit:
creepage (NEW), track_width (NEW), error_ceiling 1010 → 1313,
warning_ceiling 428 → 430, lib_footprint_issues 10 → 11,
silk_edge_clearance 4 → 6. Every rise is attributable (above); no
unattributable or unexplained movement.

## 5. What was verified

- REQ-SAFE-01 test PASSES (0 violations; full-coverage cross-check 0).
- Full `tests/requirements/safety/` suite: **108 passed** (incl. the
  updated seven-known-blockers test).
- `tests/requirements/`: 455 passed, 5 skipped. `tests/regression/`:
  129 passed, 1 skipped.
- check_pad_orientation: PASS (169 footprints, 527 pads, 0 overlaps).
- check_copper_net_consistency: PASSED (2482 copper items, 518 pads).
- check_footprint_drift: PASSED (169/169 matched, K3 now RT314012).
- check_domain_partition: PASSED (0 crossings).
- mpn_fabrication_gate: PASSED.
- Reproducibility: 30 fresh samples on the swapped board reproduced the
  1309 error total exactly (deterministic).

## Reproduction

```bash
make netlist
export PYTHONPATH="$(pwd)/packages/temper-placer/src"
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s
# CI-exact 120-sample DRC:
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import generate_kicad_dru
generate_kicad_dru.OUTPUT_PATH.write_text(generate_kicad_dru.generate_dru())
from pathlib import Path
from temper_placer.validation._drc_api import run_drc
for _ in range(120):
    run_drc(Path('pcb/temper.kicad_pcb'))
"
```
