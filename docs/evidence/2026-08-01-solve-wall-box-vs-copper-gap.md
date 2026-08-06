<!-- provenance: commit=b3638473af4b25dc44fc4ea446568f39c58dc407 dirty=false -->

# The #523 "gap 2" premise — solver box-bar vs REQ-SAFE-01 exact-copper bar (2026-08-01/02)

**Date:** 2026-08-01 (measurement); doc finalized 2026-08-02
**Branch:** `spike/gap2-wall-box-vs-copper` (worktree `.claude/worktrees/agent-gap2-wall`),
from `origin/main` `f204007097e76f96827c76257afb3f72c35f1fb9` (Merge PR #566; ancestry
includes #567 zone-polygon encoding and #568/#579 edge-hanging-refs fix).
**Scope:** READ-ONLY. No `src/` change, no `pcb/` change, no `elec/` change. Every
figure in this doc was measured on a clean tree at `f20400709` against the committed
`pcb/temper.kicad_pcb`. Measurement scripts + data live alongside this doc:
`gap2_wall_measure.py` (solve variants + unsat cores),
`gap2_wall_pairs.py`/`gap2_wall_pairs.csv` (per-pair table),
`gap2_wall_solve_cores.json`, `gap2_wall_summary.json`.

## TL;DR — verdict: gap 2 is real for the pinned-pair class, but it does NOT unlock the wall

The handoff (§4) asked whether the REQ-SAFE-01 validator's exact-copper bar
(pad-to-pad) is LOOSER than the solver's box bar (component bbox), such that a
validator-clean placement exists where the box-bar solve proves none does.

**Measured: for every pair where the box bar is violated at the current pinned
positions — all 45 of them on the canonical domain/keepaway basis — the copper
bar is satisfied.** `box_dist < margin` AND `copper_dist >= margin` on 45/45
pairs; zero genuine copper violations among the pinned-pair violations (a
full-model float cross-check adds 2 netclass + 5 courtyard pairs — same verdict;
`gap2_wall_summary.json` = 45 box-violated / 0 copper-violated / 45 gap2-holds).
The box bar is strictly stricter than the copper bar on every single pair that
makes the pinned formulation infeasible. **Gap 2 HOLDS for that class.**

**But gap 2 does not unlock the wall.** Three reasons, measured:

1. **The handoff's stated mechanism is stale on this base.** The unsat core does
   NOT name `edge_margin_C1..C21`; the deterministic edge-margin violation set at
   the pinned positions is exactly `{C27}` (free). The edge-hanging-refs fix
   (#568/#579, merged into this base's ancestry) already paid that wall down. The
   remaining pinned-pair wall is the 45 marginal box-bar violations (all
   copper-clean, all 0.01–2.0mm under the bar — the even-parity quantization
   class plus a few genuine box-vs-copper slacks).
2. **The free-ref wall is not a box-vs-copper over-constraint in the pinned
   sense.** K3 is already box-feasible and copper-clean at its current position
   (168 domain pairs, zero violations in either bar). C27 cannot be placed
   on-board with everything else pinned even in a **pure-geometry** solve with
   ZERO domain constraints (infeasible in 1.6s): its 43.1×23mm box does not fit
   the packed board. A copper-accurate SEPARATED bar does not remove the
   NoOverlap2D/courtyard box-fit wall.
3. **The practical wall is already mostly open.** The production repair recipe
   (nothing pinned, ≤60mm displacement) IS feasible and — on this base — its
   solved placement is **validator-clean** for every inter-component pair: C27
   lands ON-BOARD at (28.62, 222.0), all 271 K3/C27 domain pairs clear the 8.0mm
   copper bar, and `verify_iec60335_compliance` reports the same 3 K3-intra
   violations as current main. This is a materially different outcome from the
   run-B doc's 12-violation finding on the pre-#568 board. The remaining
   engineering walls are: the zone-inclusive fixed-copper solve (run C, still
   infeasible even with #567), the pinned formulation's 45 marginal box-bar
   violations (fixed by making the constraint copper-accurate — the gap-2 work
   item), and K3's RT314012 physical short (#523).

**Consequence for the §4 fallbacks**: a copper-accurate domain constraint
(validator semantics: exact pad-to-pad + aligned pair set) is worth building — it
would accept the current board's pinned positions (45 marginal violations
disappear) and shrink required displacement — but it does NOT by itself place
C27 on-board in the pinned formulation. The real paths are: (a) land the
run-B-style repair placement (validator-clean on this base) with the
zone-inclusive fixed-copper pass (run C) made feasible — the zone work item from
the run-B doc's gap 1; and/or (b) full re-layout with C27 **included** in the
model (the #517 re-solve excluded it). The isolation-slot/reconciliation options
from §4 remain relevant for K3-intra and any genuine copper pairs the validator
still reports at the landing placement.

## 1. Context and the exact question

The full scoped solve for K3/tank3 — FREE {K3, C27} + 12,022 domain-clearance +
530 keepaway + fixed-copper constraints, everything else pinned — is infeasible
on `origin/main` (reproduced below). The handoff hypothesis (issue #523 gap 2):
the solver's box bar (component-bbox Chebyshev separation, `handlers/separated.py`)
is stricter than the validator's copper bar (exact pad-to-pad,
`requirements/validators/clearance.py`), so a validator-clean placement may exist
where the box-bar solve proves none does. This doc measures that premise for the
specific pairs involved.

## 2. Methodology — exact geometry used

All geometry mirrors the production code paths, not re-derived approximations.

**(a) Solver box-bar distance.** `handlers/separated.py::encode_separated`
enforces, per pair, a Chebyshev (L∞) gap between the two components' bounding
boxes: at least one axis must satisfy `a.edge + margin <= b.edge`. The boxes are
`Component.bounds` (computed by `io/_parse_modules.py::_calculate_footprint_bounds`
symmetric around the placement centre `initial_position` — the 2026-07-30
frame fix), placed at `initial_position` with rotation-aware effective sizes
(`model.py::add_rotation`: rot 1/3 swap w/h; sizes and centres quantized on the
solver's even-rounded integer grid, `mm_to_units` round-half-even, 100 units/mm).
`gap2_wall_pairs.py` computes `box_dist_mm = max(|dx| − (hw_a + hw_b),
|dy| − (hh_a + hh_b)) * 0.01` on that exact grid. A float-mm cross-check on the
unquantized geometry agrees on every verdict.

**(b) Required margin.** The constraint's `min_distance_mm`: domain-clearance
pairs carry `max(min_clearance_mm, min_creepage_mm)` over the applicable
IEC60335_REQUIREMENTS rows (= creepage, 8.0mm for HV↔LV, 1.0mm for the
LV_CONTROL↔LV_CONTROL FUNCTIONAL row); keepaway carries `MAX_IEC_MARGIN_MM`
(8.0mm); courtyard τ = 0.4mm; netclass cross-class = 6.0mm.

**(c) Exact-copper distance.** The REQ-SAFE-01 validator's own
`clearance._CopperModel.copper_distance(ref_a, domain_a, ref_b, domain_b,
nets_domain)` — exact pad-polygon distance on rotation-aware pad geometry, with
the same per-domain pad restriction the validator applies (a pad counts for a
domain only if its own net maps to that domain). For domain pairs the reported
figure is the minimum over every applicable boundary (the binding one), matching
`verify_iec60335_compliance`'s per-row walk. Verified against the validator's own
output on the current board (3 violations / 1 pair, all K3-intra) and
spot-checked per-pair (e.g. K2/R6 = 9.002mm, C27/U9 = 24.127mm — identical
through both paths).

**Verdict per pair**: `box_dist < margin AND copper_dist >= margin` → gap-2
premise HOLDS for this pair (the box bar is the sole blocker; copper is satisfied
at the pinned position). `copper_dist < margin` → genuine copper violation (no
placement fixes it without moving something, or a slot / the validator
reconciliation).

## 3. Unsat-core reproduction

The scoped solve was reproduced on the committed board:

```
FREE = {K3, C27}; every other ref pinned at its current position+rotation
12,022 domain-clearance + 530 keepaway constraints (full 47-net manifest
classification, no chain-sibling exemption — matches the handoff's "530")
fixed_copper = {parse_result, free_refs={K3,C27}, margin_mm=0.05} (zones included)
timeout 60–120s, seed 0, hint_positions = current, minimize_displacement for the free pair
```

Result: **`status=infeasible` in ~1.4–1.7s** (reproduced independently in this
session and in the previous dispatch; cores in `gap2_wall_solve_cores.json`).

**The sufficient core is NOT a reliable diagnostic.** CP-SAT's
`SufficientAssumptionsForInfeasibility` is non-minimal and search-order-dependent;
the same formulation produced a 1-entry core (`edge_margin_C27`) in one run, a
15,736-entry core (169 edge_margin + all sep pairs + no_overlap_2d + 2
fixed_copper) in another, and an empty core in a third. The handoff's claim that
"the unsat core names `edge_margin_C1..C21`" does not reproduce: the core names
refs non-deterministically, and the *deterministic* edge-margin violation set is
different (below).

The deterministic diagnostics (computed from the pinned positions, not from the
core):

| wall | deterministic violation set at current positions |
|---|---|
| edge margin (0.5mm) | `{C27}` only — and C27 is FREE. R17's box sits at exactly 0.50mm (float 0.4999…); in model units its x_start = 50 = margin, so it is model-valid. **The `edge_margin_C1..C21` wall from the handoff was paid down by #568/#579** (edge-hanging refs fix, merged into this base's ancestry); on the pre-#568 board those refs hung off the edge and pinning them was infeasible. |
| box-bar (domain 8.0/1.0, keepaway 8.0, netclass 6.0, courtyard 0.4) | **45 pairs on the canonical deduplicated domain/keepaway basis** (44 domain + 1 keepaway R69/C26); a full-model float cross-check adds 2 netclass + 5 courtyard pairs — **all of them GAP2-HOLDS, zero copper violations** |
| no_overlap_2d / courtyard box fit | structural for the *pinned* formulation: C27's box has no on-board spot while every other ref stays put (§5); the repair formulation places it (§6) |

## 4. Per-pair table — every box-bar violation is copper-clean

Full table: `gap2_wall_pairs.csv` (12,101 unique domain+keepaway pairs; 45
non-CLEAN). Condensed (all 45 GAP2-HOLDS; box/copper in mm; copper = min over
applicable boundaries, the validator-binding figure):

| pair | kind | margin | box_dist | copper_dist |
|---|---:|---:|---:|---:|
| C1/C38 | domain | 8.0 | 7.98 | 10.817 |
| C2/J1 | domain | 8.0 | 7.99 | 16.370 |
| C14/K2 | domain | 8.0 | 7.25 | 12.625 |
| C23/R17 | domain | 8.0 | 7.99 | 8.604 |
| C23/R65 | domain | 8.0 | 7.99 | 10.199 |
| C27/U21 | domain | 8.0 | 7.74 | 21.550 |
| C27/U9 | domain | 8.0 | 7.85 | 24.127 |
| C3/U27 | domain | 8.0 | 7.99 | 17.273 |
| C8/L2 | domain | 8.0 | 7.99 | 25.387 |
| F1/SW2 | domain | 8.0 | 7.99 | 9.007 |
| K1/TP1 | domain | 8.0 | 7.99 | 19.293 |
| K2/PS1 | domain | 8.0 | 7.21 | 11.704 |
| L1/R2 | domain | 8.0 | 7.99 | 24.108 |
| L1/R59 | domain | 8.0 | 7.99 | 19.370 |
| L1/R75 | domain | 8.0 | 7.99 | 22.348 |
| R14/C32 | domain | 8.0 | 7.99 | 9.766 |
| R14/C40 | domain | 8.0 | 7.99 | 13.159 |
| R14/R21 | domain | 8.0 | 7.98 | 11.903 |
| R14/R31 | domain | 8.0 | 7.99 | 17.127 |
| R14/U12 | domain | 8.0 | 7.99 | 13.476 |
| R24/C32 | domain | 8.0 | 7.99 | 8.500 |
| R6/K2 | domain | 8.0 | 6.00 | 9.002 |
| R56/R37 | domain | 8.0 | 7.99 | 12.231 |
| R56/R76 | domain | 8.0 | 7.99 | 11.997 |
| T1/D3 | domain | 8.0 | 7.99 | 14.950 |
| U8/R76 | domain | 8.0 | 7.99 | 12.342 |
| R69/C26 | keepaway | 8.0 | 7.99 | 18.480 |
| C13/R36 | domain | 1.0 | 0.99 | 1.546 |
| C18/C39 | domain | 1.0 | 0.99 | 1.500 |
| C19/C39 | domain | 1.0 | 0.99 | 2.029 |
| C19/R43 | domain | 1.0 | 0.99 | 3.060 |
| C28/C37 | domain | 1.0 | 0.99 | 3.063 |
| C36/C37 | domain | 1.0 | 0.99 | 1.936 |
| C9/R70 | domain | 1.0 | 0.99 | 1.505 |
| D1/R35 | domain | 1.0 | 0.99 | 3.253 |
| Q2/U19 | domain | 1.0 | 0.99 | 2.130 |
| R1/U18 | domain | 1.0 | 0.99 | 1.701 |
| R15/U14 | domain | 1.0 | 0.99 | 1.505 |
| R3/U23 | domain | 1.0 | 0.99 | 1.490 |
| R31/U12 | domain | 1.0 | 0.98 | 4.059 |
| R38/R54 | domain | 1.0 | 0.99 | 1.738 |
| R47/R67 | domain | 1.0 | 0.99 | 1.510 |
| R48/U18 | domain | 1.0 | 0.99 | 2.746 |
| R58/U19 | domain | 1.0 | 0.99 | 2.670 |
| R68/U18 | domain | 1.0 | 0.98 | 1.513 |

(Plus, on the float basis, 2 netclass pairs C5/L1 (6.0 bar, box 5.995, copper
16.363) and C1/R4 (6.0, box 6.000, copper 10.598), and 5 courtyard-τ pairs
C4/R8, R12/R13, R4/R51, R57/U20, C10/C37 (0.4 bar, box 0.395–0.400, copper
0.910–10.540) — same verdict, all GAP2-HOLDS. Every box-bar violation, on either
basis, is copper-satisfied: **zero copper violations**.)

**Reading**: the dominant class is the 8.0mm domain pairs sitting 0.01–0.02mm
under the bar (the even-parity quantization class #568 documented) plus a few
with real box-vs-copper slack (K2/R6 box 6.00 vs copper 9.00 — K2's big relay
box over-approximates its pads by 3mm; L1 pairs box 7.99 vs copper ~20-24mm —
L1's courtyard dominates). In every case the copper is satisfied **at the pinned
positions** — i.e. a copper-accurate constraint would accept the current board
without moving any pinned ref.

## 5. The free-ref probe — K3 is already fine; C27 cannot fit with everything pinned

**K3 at its current position (56.82, 9.0, rot 1):** all 168 domain-clearance
pairs are box-clean (≥ 8.0mm) AND copper-clean (≥ 8.0mm). K3 does not need to
move; a scoped solve could leave it exactly where it is. (The 2026-07-31
infeasibility doc's Wall 4 — K3 pushed 30–280mm — was about the *12.6mm PD3* bar
on the pre-#517 board; at the current PD2/8.0mm state K3's position is fine.)

**C27 at its staged position (20, 252.75 — off-board):** 114 domain pairs; two
marginal box violations (C27/U21 7.74mm, C27/U9 7.85mm vs 8.0), both copper-clean
(21.55, 24.13). Trivially copper-clean because C27 is 20mm off the board — the
staged position is not the interesting question.

**C27 ON-board, everything else pinned:**
```
FREE={C27}, every other ref pinned, NO domain/keepaway/fixed-copper
    -> status=infeasible in 1.6s (pure geometry: NoOverlap2D + courtyard τ +
       netclass 6.0 + edge margins)
FREE={C27}, + 12,022 domain constraints      -> infeasible
FREE={C27}, + domain + 530 keepaway          -> infeasible
```
C27's 43.1×23mm box cannot be placed on-board with all 168 other refs pinned even
with ZERO domain constraints. This is the documented consequence of the #517
re-solve having **excluded C27 from the model** (the board was packed without
room for it; see `docs/evidence/2026-07-30-safety-closure-evidence.md` §4 and the
PD2 resolve doc §2.1). A copper-accurate SEPARATED bar does not address this
pinned wall by itself: NoOverlap2D and the courtyard-τ constraints are box
constraints too, and C27's box has no empty spot *while every other ref stays
put*. But §6 shows the *repair* formulation (nothing pinned, ≤60mm displacement)
finds C27 an on-board spot — the pinned non-fit is a property of the pinned
formulation, not of the board.

## 6. The repair recipe's run-B placement — box-feasible AND validator-clean on this base

The production repair recipe (nothing pinned, min-displacement, max 60mm,
fixed-rotations, fixed-copper without zone items) IS feasible on this base
(`B_repair_no_zones`: status=feasible — reproduced in both dispatches). The
solver's actual solved placement on this base (169/169 refs):

```
K3  -> (58.08, 11.18) rot 90   (moved ~2.6mm from (56.82, 9.0))
C27 -> (28.62, 222.0)  rot 0   (ON-BOARD; moved ~34mm from the staged (20, 252.75))
```

Measuring the **full** solved placement (all 169 refs at their solver positions,
not a K3/C27-only reconstruction) with the validator's own model:

| check | result |
|---|---|
| K3/C27 domain-clearance pairs (271 unique) | **0 copper violations** — worst pair C27/U10 8.66mm (≥ 8.0 bar); all K3 pairs ≥ 12mm |
| full REQ-SAFE-01 `verify_iec60335_compliance` | **3 violations / 1 pair** — all K3-intra (G5LE-1's internal 3.559mm gap), IDENTICAL to current main |
| C27 on-board | yes — (28.62, 222.0), inside the 0.5mm edge margin |

**This is a materially different outcome from the run-B doc's finding (12
violations / 9 pairs on the pre-#568 board).** The earlier session's "run-B is
not validator-clean" was measured on a board before the edge-hanging refs fix
(#568) and the zone-polygon encoding (#567), and its written C27 position
(44.44, 236.56) sat effectively on top of U24 (the run-B doc reports C27↔U24 at
0.32mm — a placement no constraint in that session's recipe protected, since U24
is unclassified and that recipe's keepaway did not bind it). On THIS base the
full recipe (12,022 domain + 530 keepaway, keepaway now protecting every
unclassified ref incl. U24) produces a placement that is **box-feasible,
copper-clean for every K3/C27 domain pair, and validator-clean for every
inter-component pair** — C27 lands on-board and the only remaining REQ-SAFE-01
violations are the K3-intra footprint ones that no placement can fix.

Caveats (why this is not yet a landable placement):
- The recipe used fixed-copper **without zone items** (the run-B convention).
  The zone-inclusive variant C (`C_repair_with_zones`) is still `infeasible`
  even with the #567 polygon-exact zone encoding — the zone obstacles
  (whole-board pours SW_NODE/PWR_RTN/ac_n) plus C27's on-board target still have
  no feasible spot. Zone handling remains the open work item (the run-B doc's
  gap 1).
- The R24 fixed-copper post-solve audit, the DRC gates (courtyards_overlap,
  shorting_items) and the drc_ceiling re-measurement must all pass for any
  written placement — not done here (READ-ONLY task; no board write).
- K3's RT314012 swap (#523) still physically shorts at every rotation of its
  current origin — the fixed-copper constraint is what will gate that, and it
  needs a feasible zone-inclusive solve first.

## 7. Premise verdict

**PARTIAL — HOLDS for the pinned-pair class (45/45 pairs on the canonical basis,
zero exceptions); does NOT by itself unlock the wall — but the wall is already
mostly open via the repair recipe.**

- The 45 box-bar violations that make the pinned formulation infeasible are all
  copper-clean: a copper-accurate (pad-level, validator-semantics) domain
  constraint would accept the current board's pinned positions. Box and copper
  **disagree** (box strictly stricter) on every single violating pair. This is
  the strongest gap-2 evidence and it is unambiguous.
- The free-ref wall is NOT a box-vs-copper over-constraint in the pinned sense:
  K3 is already fine, and C27 cannot fit on-board with everything else pinned
  (pure-geometry infeasible, §5). But §6 shows that when the formulation is the
  repair recipe (nothing pinned, ≤60mm), the solver finds C27 an on-board spot
  that is **validator-clean** for every inter-component pair. So the *practical*
  wall is not "box blocks a copper-clean placement" — the solver already
  produces one — it is the remaining engineering: the pinned formulation's 45
  marginal box-bar violations (fixed by a copper-accurate constraint), the
  zone-inclusive infeasibility (run C), and K3's RT314012 physical short.

## 8. What this implies for the §4 fallback options

1. **Full re-layout** — the real path, and the honest one. C27 cannot fit with
   everything else pinned (pure-geometry infeasible, §5), but the repair recipe
   (§6) already demonstrates a validator-clean C27-on-board placement. The
   natural next step is to make the **zone-inclusive** repair solve feasible (run
   C) and land that placement with the K3 swap, re-measuring DRC + drc_ceiling in
   the same PR per AGENTS.md. A copper-accurate constraint from §7 would drop the
   45 marginal pinned-pair violations (smaller required displacement) on top.
2. **Isolation slot / footprint change** — still needed for the genuine copper
   pairs no placement can fix: K3-intra (G5LE-1's 3.559mm internal gap, the only
   current REQ-SAFE-01 violation), and the RT314012's own geometry at K3's
   origin (#523). Gap 2 does not convert any of these into placement-fixable
   pairs.
3. **PD2 validator reconciliation** — the gap-2 work item, and worth doing: the
   measured 45/45 box-vs-copper disagreement is exactly the "solver-validator
   semantics alignment" the run-B doc already named. Replacing the SEPARATED
   box bar with the validator's exact-copper measurement (plus the aligned pair
   set, including unclassified-ref keepaway — which is what makes the §6
   placement validator-clean) makes "solver audit clean" imply "REQ-SAFE-01
   clean". It unblocks the pinned formulation and shrinks displacement; it is
   the enabler, not the stand-alone unlock.

**Bottom line for the owner**: the gap-2 premise is TRUE (box stricter than
copper, 45/45, zero exceptions), but the wall is not the box-vs-copper gap. The
wall is (a) the pinned formulation's marginal box-bar violations — fixed by the
copper-accurate constraint (gap-2 implementation), (b) the zone-inclusive
fixed-copper infeasibility (run C — the run-B doc's gap 1, still open even with
#567), and (c) K3's RT314012 physical short. On this base the solver can already
produce a validator-clean C27-on-board placement via the repair recipe; the 
decision-relevant finding for the handoff is that **gap 2 holds and is
measurable, but the §4 fallbacks (full re-layout / zone work / slot) are the real
path**, exactly as the handoff's "if box and copper agree" branch anticipated —
except box and copper do NOT agree, and that disagreement is what makes the
copper-accurate constraint worth building as the primary enabler.

## Files

- `docs/evidence/2026-08-01-solve-wall-box-vs-copper-gap.md` — this document
- `docs/evidence/gap2_wall_measure.py` — solve variants A/A0/B/C + unsat cores
- `docs/evidence/gap2_wall_solve_cores.json` — the solve cores (with provenance)
- `docs/evidence/gap2_wall_pairs.py` — per-pair box-vs-copper measurement
- `docs/evidence/gap2_wall_pairs.csv` — the 12,101-row table (45 non-CLEAN)
- `docs/evidence/gap2_wall_summary.json` — headline counts

## Reproduction

```bash
cd .claude/worktrees/agent-gap2-wall
make netlist && make extensions
uv run --no-sync python docs/evidence/gap2_wall_measure.py   # solves A/A0/B/C
uv run --no-sync python docs/evidence/gap2_wall_pairs.py     # per-pair table
# expected: 12,101 unique pairs; 45 box-violated; 0 copper-violated; 45 gap2-holds
```
