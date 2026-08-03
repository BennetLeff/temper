<!-- provenance: commit=51df5d86138ca1e807f7f5f8c1046c9d2b0e40eb dirty=false -->

# K3 swap + board write — owner-granted wave-2 (issue #523)

**Date:** 2026-08-02
**Branch:** `feat/k3-swap-and-board-write` (worktree
`.claude/worktrees/agent-board-write`), from `origin/main` at `760252f02`.
**Issue:** #523 — the K3 RT314012 relay swap + validator-gated re-solve +
board write + DRC ceiling re-measurement, the owner-granted wave-2 write
(GO given 2026-08-02). **This is the only change authorized to touch
`pcb/temper.kicad_pcb`, `elec/src`, and `power_pcb_dataset/drc_ceiling.json`
in this session.**

## Headline

**REQ-SAFE-01 on the written board = 0 violations / 0 pairs (0 inter /
0 intra).** The last board blocker — K3's G5LE-1 intra-footprint
coil<->contact gap (3 records / 1 pair, all K3<->K3, 3.558846mm vs the
4.0/6.0/8.0 bars) — is GONE: K3 now carries the TE Schrack RT314012
(12.76mm internal gap) and was re-solved to a position where the whole
board is validator-clean.

## 1. Why the swap (context)

- The G5LE-1's 3.559mm coil-to-contact gap fails **both** the 8.0mm
  reinforced-creepage bar (PD2, currently enforced everywhere) and the
  6.0mm pollution-degree-independent clearance minimum — and would fail
  the 12.6mm PD3 fallback too. The swap is required under either bar
  (docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md §4; plan
  docs/plans/2026-08-02-002-feat-sealed-compartment-plan.md R5).
- The RT314012 (same part K2 got in PR #524) has a 12.76mm internal
  coil<->nearest-contact gap — clears 8.0mm at 1.6x, 6.0mm at 2.1x, and
  the 12.6mm PD3 bar.
- The swap was previously **BLOCKED on placement** (2026-07-31): at the
  pre-re-solve origin every rotation shorted copper. The re-solve (#523)
  unblocks it.

## 2. Swap procedure (mirrors the K2 swap, PR #524)

1. **elec/src/modules.ato** — `k_dis2` declared as RT314012: `mpn =
   "RT314012"`, `footprint = "temper:Relay_SPDT_Schrack-RT314012"`, with
   the BLOCKED comment replaced by a SWAPPED note (the exact substitution
   pattern #524 used for `k_dis1`).
2. **elec/domain_manifest.yaml** — `discharge.k_dis2` isolator
   declaration's `component:` string updated to "TE Connectivity / Schrack
   RT314012 (Relay_SPDT), discharge relay 2". Pin convention unchanged
   (groups `coil: ["2","5"]`, `contacts: ["1","3","4"]` match both parts'
   1..5 pads), so nothing else in the manifest moved.
3. **`make netlist`** — regenerated `elec/build/default.net` (build
   artifact, not tracked); K3's footprint resolves to
   `temper:Relay_SPDT_Schrack-RT314012`.
4. **pcb/temper.kicad_pcb** — K3's embedded G5LE-1 block replaced with
   the RT314012 geometry (the canonical in-repo copy: K2's embedded block
   in the same file, byte-identical geometry to the project
   `temper.pretty` library footprint), keeping K3's tstamp and
   sheetpath, at K3's current board position. Pad nets by number from the
   regenerated netlist: 1=COM/DC_BUS_RTN, 2=coil1, 3=NO, 4=NC, 5=coil2
   (shares the `discharge.k_dis1-coil2` node — the two relay coils are
   wired in series; there is no separate `k_dis2-coil2` net record).
   Mechanized by `docs/evidence/k3_swap_embed_footprint.py`.

Consistency gates after the swap: copper_net_consistency 0 violations /
footprint_drift 0 / domain_partition 0 crossings / pad_orientation PASS.

## 3. Re-solve (validator-gated)

### 3a. Run A — production caller (run_clearance_repair_solve) — reported, NOT written

Ran the production repair recipe through the validator-gated caller on the
swapped board (nothing hard-pinned, min-displacement to current,
≤60mm cap, fixed rotations, full domain-clearance 11,571 + 530 keepaway,
seed 0, 180s/round, max 4 rounds). Result: **status=clean**, hard=0,
intra=0, gaps=0, REQ-SAFE-01 0/0 — but the caller **cannot express
`fixed_copper`**, so its solve moved 166 refs (total displacement
5763.6mm), and the resulting written board **REGRESSED on DRC**:
total_errors 1428-1437 vs the 1356 ceiling (clearance 458, creepage 211,
solder_mask_bridge 206, silk_over_copper 199; 120 samples, DRU
regenerated, `--all-track-errors`). That regression is a **finding, not a
bump**: it is an artifact of the caller's interface limitation, and the
evidence-validated candidate that the re-solve evidence measured
(1043→838) is the Run-B recipe below. Run A is recorded in
`docs/evidence/k3_swap_board_write_solve_summary.json`; its placement was
reverted and is NOT the written board.

### 3b. Run B — the evidence-validated candidate — THE WRITTEN PLACEMENT

Re-ran the wall-spike variant-B recipe exactly
(docs/evidence/2026-08-01-k3-resolve-validator-gated.md §4 Run B): direct
`solve_placement` with `fixed_copper` WITHOUT zone items
(`free_refs={K3,C27}`, margin 0.05), nothing pinned, min-displacement to
current, ≤60mm cap, every rotation pinned, full 11,571 + 530 constraint
set, no chain exemption, seed 0, 180s, hints = current positions, plus
`validator_input` wired.

| field | value |
|---|---|
| status | feasible |
| K3 | (43.12, 17.92) rot 90 (from swap-only (45.97, -3.67) local frame) |
| C27 | (28.62, 222.0) rot 0 — **ON-BOARD**, exactly the spike-predicted position |
| total displacement | 6484.2mm (167 refs >0.02mm; most sub-mm — the fixed_copper recipe anchors every other ref as an obstacle) |
| validator audit | hard=0, intra=0 (RT314012 bucket EMPTY as predicted), gaps=0, covered 11,571, geometry_trusted=True, clean=True |

### 3c. Written placement (board-file absolute frame)

| ref | pre-write (swap-only, 271c33f20) | written (3410ee4e1) | Δ |
|---|---|---|---|
| K3 | (69.72, 29) rot 90 | (66.87, 50.59) rot 90 | (−2.85, +21.59) |
| C27 | (20, 272.75) rot 0 (staged off-board) | (28.62, 242.0) rot 0 — **ON-BOARD** | (+8.62, −30.75) |

Write mechanism: `write_placements_to_pcb` with CP-SAT local frame →
absolute (add board origin (20,20)), components list for bbox-center →
footprint-origin conversion (rotation-aware center-offset subtraction) —
the same mechanism the re-solve evidence used. Round-trip re-parse: 0
mismatches; REQ-SAFE-01 on the written board = **0/0**.

## 4. DRC ceiling re-measurement (120 samples)

Full ceiling protocol: `temper_placer.validation._drc_api.run_drc`
(kicad-cli **10.0.4**, `--all-track-errors`), `pcb/temper.kicad_dru`
regenerated from `scripts/generate_kicad_dru.py` first (the CI gate's
exact invocation), 120 samples on the committed written board (hash
`51e39844`). **The candidate was measured under its canonical filename so
kicad-cli resolves the DRU rules** — an earlier 842 reading was a
measurement artifact (candidate named `candidate.kicad_pcb` in /tmp had
no DRU beside it, so the custom creepage/track_width categories were
silently absent; the apples-to-apples figure is 1261-1263).

| category | prior ceiling (cf161bee) | written board observed (120 samples) | new ceiling | attribution |
|---|---:|---:|---:|---|
| clearance | 415 | 377-378 | 379 (+1 headroom) | Run-B re-solve separates HV<->SELV pairs |
| creepage | 201 | 185-187 | 188 (+1 CI band) | same |
| hole_clearance | 129 | 105 | 105 | K3/C27 moved clear of via clusters |
| shorting_items | 202 | 199-200 | 201 (+1 headroom) | same |
| solder_mask_bridge | 169 | 154 | 154 | same |
| track_width | 199 | 199 | 199 | unchanged |
| annular_width | 4 | 4 | 4 | unchanged |
| courtyards_overlap | 11 | 11 | 11 | unchanged |
| copper_edge_clearance | 12 | 12 | 12 | unchanged |
| hole_to_hole | 3 | 3 | 3 | unchanged |
| tracks_crossing | 3 | 3 | 3 | unchanged |
| via_diameter | 4 | 4 | 4 | unchanged |
| **error_ceiling** | **1356** | — | **1267** | all error categories improved or held |

| warning category | prior ceiling | written observed | new ceiling | attribution |
|---|---:|---:|---:|---|
| silk_over_copper | 122 | 172 | 172 | Run-B re-solve moved 167 refs (min-displacement within 60mm); moved footprints' silk now crosses copper it did not before — same placement-class mechanism the #517 solve documented; deliberate wave-2 write |
| track_dangling | 44 | 45 | 45 | one track endpoint whose pad moved now dangles (placement-class) |
| lib_footprint_issues | 10 | 11 | 11 | K3's RT314012 references the project `temper` library (same class the K2 swap documented) |
| lib_footprint_mismatch | 24 | 23 | 23 | K3's embedded copy now matches its library footprint |
| pth_inside_courtyard | 4 | 1 | 1 | K3/C27 moved out of other parts' courtyards |
| silk_edge_clearance | 2 | 1 | 1 | moved silk no longer crosses the board edge |
| missing_courtyard | 5 | 5 | 5 | unchanged |
| silk_overlap | 199 | 199 | 199 | unchanged |
| via_dangling | 15 | 15 | 15 | unchanged |
| **warning_ceiling** | **425** | — | **472** | three per-type rises, all attributed |

**Ceiling verdict:** error_ceiling **decreases** 1356→1267 (every error
category improved or held — no error raise). warning_ceiling **rises**
425→472 with three per-type rises, each attributed to a named commit
(271c33f20 swap: lib_footprint_issues; 3410ee4e1 re-solve:
silk_over_copper, track_dangling) — the deliberate wave-2 board change,
not an unexplained regression. Per the standing convention (a per-type
increase is commit-trailer-gated regardless of direction), the landing
commit carries the `Ceiling-Approval:` trailer.

Nondeterministic categories on this board (recorded in the ceiling):
clearance 377-378, creepage 185-187, shorting_items 199-200.

## 5. Test re-baseline (board-dependent-test rule applied to itself)

The #588/#591 re-baselined assertions encoded the pre-write K3-intra
reality and went stale in THIS PR (the board changed under them). All
updated fail-closed, with measured numbers and this evidence cited:

- `test_clearance.py::test_temper_board_clearance_compliance`: K3-intra
  pin (3 records / 1 pair at 3.558846mm) → **0 inter + 0 intra**; any new
  violation of either kind fails, naming the pairs.
- `test_clearance_copper.py::test_the_seven_known_intra_footprint_
  blockers_are_now_visible`: blocker set `{"K3"}` → **set()** — K3 cleared
  by its own RT314012 swap; K2/C6/K1/T1/U3/U7 still asserted absent.
- `test_clearance_repair.py::test_repair_solve_drives_inter_component_
  violations_to_zero`: `intra_blocker_refs` now **empty**.
- `test_clearance_repair.py::test_checker_copper_distance_is_lower_bound_
  on_origin_distance`: intra floor `{"K3"}` → **empty**.
- `test_validator_audit.py::TestProductionBoardSolve::test_free_k3_solve_
  is_inter_clean_and_k3_intra_surfaces`: re-based from the pre-write
  pure-geometry recipe (FREE={K3}, everything pinned — infeasible on the
  written board because its box no-overlap is stricter than KiCad's actual
  courtyards) to the **Run-B production recipe** the board was written
  with (fixed_copper free_refs={K3,C27}, min-displacement, full
  domain-clearance + keepaway, ≤60mm cap); asserts hard=0, intra=0,
  gaps=0, and the ≤60mm displacement contract.

## 6. Gates

- 4 consistency gates (written board): copper_net_consistency 0 /
  footprint_drift 0 / domain_partition 0 crossings / pad_orientation PASS.
- `scripts/check_measurement_provenance.py`: **PASSED** (board hash
  51e39844 matches the ceiling's recorded hash).
- pytest: `tests/requirements/safety/` 56 passed;
  `test_clearance_repair.py` + `test_validator_audit.py` 43 passed — all
  green on the written board.

## 7. Files

- `docs/evidence/k3_swap_embed_footprint.py` — K3 footprint embed-swap.
- `docs/evidence/k3_swap_board_write_solve.py` /
  `k3_swap_board_write_solve_summary.json` — Run A (production caller),
  reported not written.
- `docs/evidence/k3_swap_board_write_variantB.py` /
  `k3_swap_board_write_variantB_summary.json` — Run B (the written
  candidate).
- `docs/evidence/k3_swap_board_write_apply.py` — board write + round-trip
  + REQ-SAFE-01 verification.
- `docs/evidence/k3_swap_board_write_drc.py` /
  `k3_swap_board_write_drc_summary.json` — 120-sample ceiling protocol.

## 8. Reproduction

```bash
make netlist && make extensions
uv run --no-sync python docs/evidence/k3_swap_board_write_variantB.py   # Run B solve
uv run --no-sync python docs/evidence/k3_swap_board_write_apply.py     # write + verify
export PYTHONPATH="$(pwd)/packages/temper-placer/src:$(pwd)/scripts"
.venv/bin/python docs/evidence/k3_swap_board_write_drc.py              # 120-sample ceiling
# expected: status=feasible; C27 -> (28.62, 222.0) ON-BOARD; K3 ->
# (43.12, 17.92) rot 90; hard=0 intra=0 gaps=0; REQ-SAFE-01 = 0/0;
# error_ceiling 1356 -> 1267; warning_ceiling 425 -> 472 (Ceiling-Approval)
```
