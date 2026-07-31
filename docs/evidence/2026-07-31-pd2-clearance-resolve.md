# PD2/8.0mm clearance re-solve: 53 -> 6 REQ-SAFE-01 violations (provable floor)

<!-- provenance: commit=55226f8adc66378789f89b27a82593600748a4c7 dirty=false -->

**Date:** 2026-07-31
**Scope:** `pcb/temper.kicad_pcb` re-solved and rewritten (placement-only; routing data preserved
byte-identically). No `elec/src/*.ato` changes, no validator/gate script changes. Driver script
and candidate board live under `/private/tmp/w517-scratch/` (scratch, not committed) -- this doc
reports their exact invocations and output.
**Base:** worktree `w-517`, branch `fix/board-clearance-resolve-pd2`, tip `10f3e20df` (carries PR
#515's PD2/8.0mm validator change; 2 ahead of origin/main, verified `git rev-list --left-right
--count origin/main...HEAD` = 0 2). `make netlist` run fresh (digest `736b01f0e07e…`).

## 0. Task

Issue #517: even at the selected PD2/8.0mm architecture, `test_temper_board_clearance_compliance`
reports 53 REQ-SAFE-01 clearance/creepage violations across 25 pairs (copper-to-copper). Mission:
determine empirically whether 0 violations is reachable for the placement-fixable pairs; land the
best achievable board; follow the AGENTS.md DRC-ceiling re-measurement protocol (120 `run_drc()`
samples, every per-type delta attributed).

## 1. Baseline (reproduced fresh, this branch, before any change)

```
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s
```

**53 REQ-SAFE-01 violations across 25 pairs** (159 components matched, 94.1% coverage),
**6 unclassified-proximity findings = 0**. The 25 pairs split into:

- **23 inter-component pairs** (placement-fixable): C17-R32, R30-R32, R30-R1, C17-R26, R30-R54,
  R30-U13, R12-K3, C17-U13, C22-U15, R30-R73, C22-C16, R30-R46, R30-L2, R30-R26, R30-C31,
  U6-R18, C17-R73, C17-R54, C22-R77, C22-C12, C22-C38, F1-R70, T1-U27.
- **2 intra-footprint pairs** (provably unfixable by placement): `K2`, `K3` (discharge relays;
  HV contact pad ↔ SELV coil pad at 3.559mm inside the footprint — below even the
  pollution-degree-independent 6.0mm clearance minimum, so no pollution-degree change or
  placement could ever clear them; they need a footprint/part change, tracked with #518).

## 2. Solve

### 2.1 Method (mirrors `docs/evidence/2026-07-30-copper-aware-domain-resolve.md`)

- `load_real_board_placement()` (the fixture the gate test itself calls) for the full 54-net
  manifest classification → `generate_domain_clearance_constraints(full_placement,
  full_voltage_domains, component_refs=<all 168 model refs>)`: **11,908 constraints**.
- **Keep-away group** (the 2026-07-27 evidence doc's remedy for the free-reshuffle regression):
  one HARD `SeparatedConstraint` per (unclassified, HV-classified) pair at `MAX_IEC_MARGIN_MM`
  (8.0), minus `_chain_sibling_exempt_pairs`: **518 constraints** (10 unclassified × 53 HV refs).
  Without this group the first solve attempt regressed 6 unclassified-proximity findings
  (R72/R57/R64 at 0.910mm from R9) — same failure mode as 2026-07-27 Sec 3. The second attempt
  (with the group) produces 0 findings.
- `solve_placement(netlist=<PCB parse minus C27>, board=<PCB parse>, extra_constraints=<12,428>,
  timeout_ms=180_000, seed=0, hint_positions=<current local positions>)`.
- **REQ-EMC-03 anchors (added after the first solve attempt regressed the EMI test)**: the
  first full solve moved F1 (fuse) and RV1 (MOV) such that RV1.x < F1.x, regressing
  `test_temper_board_emi_filter_compliance` (MOV-001, "MOV before the fuse"). The final solve
  adds two `AnchoredConstraint`s: **RV1 pinned at its original bbox-center (105.47, 168.92
  local)** (feasible — its 16x5.7mm bbox is inside the model's 0.5mm edge margin) and **F1
  region-constrained so its 25x2.5mm bbox stays strictly left of RV1's bbox** (x_end <= 97.47).
  F1 could NOT be pinned at its original spot: its courtyard bbox spans x∈[-10.75, 14.25]
  local — it hangs off the board edge — so the model's edge-margin constraint makes that
  position infeasible (verified: `status=infeasible`, unsat core `edge_margin_F1` +
  `anchor_anchor_F1_emc` on the first anchoring attempt). Result: RV1.x (129.21) >= F1.x
  (60.35) on the solved board; the EMI test PASSES.
- **C27 (tank.c_tank3) excluded** from the model, constraints, and write: staged at (20.0, 272.75)
  outside the board outline per the documented human placement decision
  (`docs/evidence/2026-07-30-safety-closure-evidence.md` Sec 4). Verified untouched after the
  write.
- Write: `write_placements_to_pcb` with `board.origin` (20, 20) added (CP-SAT local frame →
  absolute) and `components=` passed (bbox-center → footprint-origin conversion). Scratch driver:
  `/private/tmp/w517-scratch/resolve_pd2.py`.

### 2.2 Result

```
solver status: optimal  solve_time_ms=33882  placed=168/168  unplaced=[]
domain-clearance constraints: 11908   keep-away constraints: 518   anchor constraints: 2
R24 audit mismatches (domain_clearance): 0
R24 audit mismatches (keep_away): 0
write: updated=168 skipped=1 (C27)
```

### 2.3 Board-content verification (netlist gates as oracle)

- Footprint refs: 169 identical (sorted diff, empty). Nets: identical (sorted diff, empty).
- Routing data preserved exactly: 2338 segments / 48 vias / 96 zones, counts byte-identical.
- Diff is placement-only: 169 footprint `(at …)` lines + per-pad body re-orientation
  (`_reorient_pads`, required when footprint rotation changes) + 2 kiutils `tedit` formatting
  lines + 1 non-copper `(point` (F.Fab) fab-marker line dropped by kiutils serialization
  (no copper/netlist/clearance impact).
- Positions: 168/169 footprints moved (all but C27), median displacement 112.77mm, max 255.35mm
  (R34) — a full-board reshuffle, the documented characteristic of the free solve
  (`2026-07-30-copper-aware-domain-resolve.md` Sec 4 measured ~100-116mm). 110 rotations changed.
- Only C27 remains outside the board outline.

## 3. Gate measurements on the solved board (real pytest, candidate swapped in, restored after)

```
test_temper_board_clearance_compliance:
  REQ-SAFE-01: 53 -> 6 violations across 2 pair(s) (6 records intra-footprint, K2/K3 only).
  Unclassified-proximity findings: 0 (was 0; first solve attempt regressed to 6, fixed by keep-away).
  FULL-COVERAGE CROSS-CHECK: 6 violations over the full 54-net manifest (159 components).
  Components matched: 159 (unchanged coverage).
  Assertion still fails (deliberately — the gate reports the true state; K2/K3 are the
  provable floor, not a pass).
tests/requirements/safety/ (full dir): 107 passed, 1 failed (the same integration test).
test_clearance_copper.py: 33 passed.  test_isolation.py: 31 passed.
tests/placer/cp_sat/test_domain_clearance.py: 21 passed.
test_emi_filter.py::TestEMIFilterIntegration::test_temper_board_emi_filter_compliance:
  PASSED (was FAILED on the first solve attempt -- MOV-001 -- fixed by the REQ-EMC-03 anchors).
tests/requirements/emc/: 57 passed, 4 skipped.
scripts/check_domain_partition.py: PASSED — 0 domain crossings, 0 isolator breaches, 0 chain defects.
scripts/check_isolation_keepout.py: FAILED — pre-existing #518 (no MAINS_SELV_ISOLATION_BARRIER
  zone on the board; unchanged by this re-solve, verified 0 zones before and after).
Router: scripts/route_board.py (router_v6 route_pcb) attempted on the solved board — exceeded
  15 min without completing; abandoned. Not blocking per orchestrator policy (regression Check
  failures reported, not blocking); the DRC ceiling re-measurement quantifies the routing impact
  instead (Sec 5).
```

## 4. Before/after REQ-SAFE-01 (PD2/8.0mm validator)

| Measurement | Before | After |
|---|---:|---:|
| `verify_iec60335_compliance` violations | 53 | **6** |
| Violating pairs | 25 (23 inter + 2 intra) | **2 (K2, K3 intra only)** |
| Unclassified-near-HV findings | 0 | **0** |
| Components matched | 159 | 159 (unchanged) |
| 12.6mm (PD3) counterfactual | 123 (per #515) | not re-measured on the solved board (PD3 superseded by decision) |

**0 total is NOT reachable by placement**: K2/K3 are single-part intra-footprint pairs at
3.559mm — placement cannot separate a part's own pads, and 3.559 < 6.0mm means even downgrading
the boundary tier or pollution degree cannot clear them. 6 records / 2 pairs is the provable
floor; eliminating it requires a different relay footprint or part (see #518's blocker comment:
K2/K3 are "infeasible even at 1.0 mm corridor width" for the barrier gate too).

## 5. DRC ceiling re-measurement (companion commit, `Ceiling-Approval:` trailer)

Per AGENTS.md: 120 samples of `temper_placer.validation._drc_api.run_drc` (kicad-cli 10.0.4,
`--all-track-errors`, zone fill) against the committed board
(`pcb/temper.kicad_pcb` @ `55226f8ad`, sha256 `e3817782…`); creepage re-measured via the
DRU-regenerating path (4 samples, stable at 32 — unchanged from the prior record). Full
per-category observed ranges, delta attribution, and the resulting
`power_pcb_dataset/drc_ceiling.json` update are in the companion commit's `_march` entry —
the short version: the re-solve is a placement-only reshuffle on a routed board with no
re-route pass, which is the exact, pre-investigated mechanism
(`2026-07-30-copper-aware-domain-resolve.md` Sec 4) that raises `shorting_items` (118→202),
`solder_mask_bridge` (69→163), `hole_clearance` (109→132), `hole_to_hole` (1→3),
`track_dangling` (29→44), `via_dangling` (4→15) while lowering `clearance` (502→440),
`copper_edge_clearance` (15→12), `courtyards_overlap` (14→11), `pth_inside_courtyard` (9→4),
`holes_co_located` (2→0), `silk_edge_clearance` (199→2) and `silk_over_copper` (199→124).
Error aggregate fully deterministic 974/974; clearance 437-439 and shorting_items 199-201 are
the only nondeterministic categories (ceilings 440 / 202 = observed max + 1, the standing
convention). `error_ceiling` 875→1010 (+135), `warning_ceiling` 680→427 (−253). Every rise is
attributed to that mechanism; no un-attributable or unexplained category movement was observed.
The six per-type rises carry the `Ceiling-Approval:` trailer on the ceiling commit
(`e8773d2d5`). A route-aware re-layout that avoids this trade-off is the sibling workstream #504.

## 6. Reproduction

```bash
cd /Users/bennet/Desktop/w-517          # branch fix/board-clearance-resolve-pd2
make netlist
# baseline:
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -rA -s
# solve (scratch driver): /private/tmp/w517-scratch/resolve_pd2.py
# verify solved board (swap candidate over pcb/, run pytest, restore):
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/ -q
```
