<!-- provenance: commit=ab11daaba37f1fca17d057fd087110a663e01deb dirty=false (re-pointed 2026-08-05: the cited 65db97e837e2c876805cac68b9164de3a4ee23dc was a pre-merge #672 branch commit, orphaned by force-push; the domain-first re-solve evidence landed at ab11daaba37f1fca17d057fd087110a663e01deb (#672), which is the cited commit) -->

# Domain-first re-solve for the MAINS_SELV_ISOLATION_BARRIER keepout — keepout NOT landed (issue #518, plan R1)

**Date:** 2026-08-04
**Branch:** `feat/domain-first-resolve-keepout` (worktree `.claude/worktrees/agent-domain-resolve`)
**Issue:** #518 — Board & Netlist Gates: missing `MAINS_SELV_ISOLATION_BARRIER` keepout zone
**Plan:** `docs/plans/2026-08-01-001-feat-mains-selv-isolation-barrier-plan.md` R1 (domain-first floorplan re-solve) + R2 (keepout); the owner-GO'd scope (R1 of `docs/plans/2026-08-02-002-feat-sealed-compartment-plan.md` + #518).
**Board measured:** `pcb/temper.kicad_pcb` on `origin/main` `28dc960de` (board content hash `51e39844…` — **byte-identical** to the #654 falsification measurement; verified via `git diff b8709225c 28dc960de -- pcb/ power_pcb_dataset/ elec/domain_manifest.yaml` = empty).

> **Verdict (step-5 outcome).** After the domain-first re-solve, the keepout is
> **still not constructible — and this session proves it is constructible for
> NO placement**, from two independent directions: (1) the copper-exclusion
> checks (4+5) are **placement-independent-unsatisfiable** (the four big power
> pours leave no zone-free edge-to-edge corridor; NEW finding this session),
> and (2) the far-side check (6) remains unsatisfiable even after freeing the
> alternating-ring refs (45 alternating Delaunay cycles on 78 refs — half the
> board — remain; expanding the free set made the topology *worse*). **No
> keepout was drawn, `pcb/**` is untouched, and the DRC ceiling + production
> baseline are untouched** (measurement provenance PASSED). The gate stays red
> with a documented reason, exactly as the #654 falsification prescribes.

---

## 1. Executive summary

1. **Falsification reproduced** on `origin/main`'s board (hash `51e39844…`,
   unchanged since #654): the 12-pad strictly-alternating bichromatic Delaunay
   cycle (C6.2→R8.2→K1.A2→R8.1→R75.1→C27.2→C9.1→U5.3→Q1.1→U5.1→U10.2→R27.2),
   the convex-hull interleave (137 SELV centers inside the HV hull, 93 reverse),
   and the copper-exclusion failure (12.6 % copper-free space in 99 fragments,
   no edge-to-edge corridor; zone outlines cover 85.7 %).
2. **NEW, decisive this session — the copper-exclusion obstruction is
   placement-independent.** The 96 copper zones (pours) cover 89.7 % of the
   board (raw union). The *zone-only* free space (board minus pour outlines,
   ignoring pads/segments/vias entirely — the best any placement could ever
   achieve) is 14.3 % in just **5 components, none spanning two opposite
   edges** (comp 0 bottom+left 1044 mm², comp 2 right+top 92 mm², comp 3
   left+top 3903 mm² — all corner scraps). The dominant blockers are the four
   big power pours on **F.Cu + B.Cu**: DC_BUS_RTN 24,349 mm², PWR_RTN
   17,546 mm², SW_NODE 14,082 mm², ac_n 2,757 mm², ac_l 1,587 mm² (simple
   5-vertex polygons, no holes). A placement re-solve moves footprints, never
   pours — so **no solve can ever open a barrier corridor**. Checks 4+5
   (partition + no-intrusion) are unsatisfiable for every placement.
3. **The domain-first re-solve** (production recipe: `run_clearance_repair_solve`
   with `fixed_copper` free_refs={C6,R8,K1,R75,C27,C9,U5,Q1,U10,R27} — the #653
   hoist, seed 0, 60 mm cap, min-displacement, full 11,571+530 constraints,
   validator-gated) completes **clean**: REQ-SAFE-01 0/0, hard=0/intra=0/
   gaps=0. It breaks the specific 12-ring (minimal alternating cycle 12→4;
   C6 +33.6 mm, Q1 +20.4 mm, U10 +15.1 mm), but **45 alternating Delaunay
   cycles remain on 78 refs** — the macro-level interleave. Expanding the free
   set to all 78 cycle refs (moves up to 60 mm, total 6530 mm) made the
   topology **worse** (47 cycles; 174 SELV centers inside the HV hull vs 129):
   the min-displacement + clearance-constraint machinery cannot produce the
   domain *clustering* the far-side check requires — that is a floorplan
   topology, not a clearance property.
4. **DRC class of the solved placements (measured, N=5, regenerated DRU):**
   run 1 (ring-freed) **1311–1312** (creepage 262–263 — the ring moves drove
   isolator HV↔SELV pairs closer); run 2 (expanded) **1019–1020** (creepage
   180–181 — a wide scatter improves pairwise DRC while *destroying* the
   far-side topology). Baseline 1261–1263 matches the documented written-board
   class. DRC quality and far-side separability are **not** correlated.
5. **Step-5 verdict: no compliant barrier exists after the best separation
   attempt → do NOT force a keepout.** `pcb/temper.kicad_pcb` is untouched;
   `power_pcb_dataset/drc_ceiling.json` and
   `power_pcb_dataset/baselines/temper_production_baseline.yaml` are untouched
   (no board change → measurement provenance PASSED, no `Ceiling-Approval`
   needed). The keepout gate stays red (the #518 missing-zone violation), with
   this document as the recorded reason — the same honest outcome the #654
   falsification established.

---

## 2. Reproduction — falsification on the current board

`uv run --no-sync python docs/evidence/2026-08-03_mains_selv_barrier_falsification.py`
(unchanged since #654; the board is byte-identical so every number matches):

| criterion | measured (current board) |
|---|---|
| bichromatic Delaunay cycle | **FOUND, 12 vertices, strictly alternating** (C6.2→R8.2→K1.A2→R8.1→R75.1→C27.2→C9.1→U5.3→Q1.1→U5.1→U10.2→R27.2) |
| HV hull contains SELV centers | **137** |
| SELV hull contains HV centers | **93** |
| copper-free fraction | 12.6 % (4481 mm²) in **99** components |
| components touching ≥2 edges | 3 — all corner scraps (166, 92, 1425 mm²) |
| zone-outline coverage | 85.7 % |
| gate | `violation` (1: `missing`) — the #518 red |

---

## 3. NEW — the copper-exclusion obstruction is placement-independent

`docs/evidence/2026-08-04_zone_corridor_analysis.py` — the decisive new
measurement. Zones (pours) do not move under a placement re-solve, so the
*zone-only* free space is the upper bound on any barrier corridor:

| zone-only metric | measured |
|---|---|
| zone count / union coverage | 96 zones / **89.7 %** of board area |
| zone-free fraction | 14.3 % (5098 mm²) in **5** components |
| components spanning two OPPOSITE edges | **0** |
| components touching ≥2 edges | 3 — all adjacent-edge corner scraps (comp 0 bottom+left, comp 2 right+top, comp 3 left+top) |
| largest zone-free inradius | comp 0: 4.2 mm at (24, 118) — a sliver, not a corridor |
| dominant pours (F.Cu + B.Cu) | DC_BUS_RTN 24,349 mm² (bbox (24,15)–(180,253) — nearly the whole board), PWR_RTN 17,546 mm², SW_NODE 14,082 mm², ac_n 2,757 mm², ac_l 1,587 mm² |

**Why this is decisive.** Check 5 (no intrusion, `check_isolation_keepout.py`
L767–780) forbids the barrier from intersecting any non-keepout zone polygon
on a shared layer; the barrier spans all four copper layers (check 1), so
every pour on F.Cu/B.Cu blocks. The four big pours partition the board such
that no zone-free path spans it edge-to-edge — *even with every pad, segment
and via removed*. Since the far-side check (6) can only be satisfied by a
full board-spanning separator (both domains occupy every x-band, so a corner
cap can never separate them), the barrier requires an edge-to-edge corridor —
which cannot exist. **This obstruction is irreversible by any placement
change.**

---

## 4. The domain-first re-solve

### 4a. Recipe (run 1 — the ring-freed candidate)

`docs/evidence/2026-08-04_domain_first_resolve_solve.py` — the PRODUCTION
recipe through the validator-gated caller:

- `run_clearance_repair_solve(pcb_path, full, full_vd, timeout_ms=180000,
  seed=0, max_rounds=4, max_displacement_mm=60.0, chain_exempt_pairs=None,
  fixed_copper={"parse_result": <no zones>, "free_refs": RING,
  "margin_mm": 0.05})` — the #653 hoist makes `fixed_copper` expressible at
  the production caller (the piece Run A of the wave-2 write could not
  express).
- RING = {C6, R8, K1, R75, C27, C9, U5, Q1, U10, R27} (the 12-ring's refs,
  deduped).
- Nothing hard-pinned (min-displacement toward current), every rotation
  pinned, full 11,571 domain-clearance + 530 keepaway, validator_input wired
  (REQ-SAFE-01 exact-copper audit, fail-closed), fixed-copper audit
  fail-closed.

**Why NOT pin-everything-but-the-ring** (documented decision per the
dispatch's "direct solve_placement … if the caller can't express the pin
set"): the written board is infeasible under the current model's
auto-generated netclass cross-class constraints when pinned — 8 cross-class
pairs sit at/under the 6.0 mm bar at the written positions, two strictly
below (C2<->C26, C4<->U6 at 5.995 mm; `docs/evidence/2026-08-03-fixed-
copper-repair-caller.md` §5). A `fixed_positions` pin-everything-but-ring
solve returns `infeasible` (2.8 s, unsat core = `edge_margin_*` + netclass
pins). The production caller's min-displacement form is the feasible class
the current model admits.

### 4b. Run 1 result (ring-freed)

| field | value |
|---|---|
| status | **clean** (1 round) — all inter pairs cleared, 0 intra |
| validator audit | **hard=0, intra=0, gaps=0**, covered 11,571, geometry_trusted=True, clean=True |
| fixed-copper audit | 0 violations (passed) |
| REQ-SAFE-01 | **0/0** |
| total displacement | 5201.3 mm (168 refs moved, most sub-mm — the diffusion class) |
| ring refs moved | C6 (45.99,186.76)→(18.10,192.43) **33.56 mm**; Q1 (2.20,196.17)→(2.20,175.76) **20.41 mm**; U10 (17.69,200.80)→(2.56,200.80) **15.13 mm**; C9 3.74 mm; K1 2.64 mm; C27/R75/R8/R27/U5 ≤0.02 mm |

### 4c. Run 2 result (expanded — all 78 alternating-cycle refs freed)

To honour "plus anything the falsification's ring analysis says is needed",
the free set was expanded to every ref participating in an alternating cycle
at run 1's placement (78 refs, extracted by the verify script):
`docs/evidence/2026-08-04_domain_first_resolve_solve_summary_run2_expanded.json`.
Result: status clean, buckets 0/0/0, **169 refs moved / 6530 mm** (many at the
60 mm cap) — and the far-side topology got **worse** (§5). Reported because it
is the strongest form of the "the machinery cannot cluster domains" finding.

### 4d. DRC class (measured, N=5, regenerated `temper.kicad_dru`, canonical
filename in /tmp so kicad-cli resolves the project rules — the ceiling
protocol's invocation)

`docs/evidence/2026-08-04_domain_first_resolve_drc.py`:

| rule | baseline (committed board) | run 1 (ring-freed) | run 2 (expanded) | ceiling |
|---|---:|---:|---:|---:|
| clearance | 377–378 | 378 | 377 | 379 |
| creepage | 185–187 | **262–263** | 180–181 | 188 |
| shorting_items | 199–200 | 185 | 102 | 201 |
| solder_mask_bridge | 154 | 138 | 69 | 154 |
| hole_clearance | 105 | 110 | 53 | 105 |
| courtyards_overlap | 11 | 11 | 11 | 11 |
| track_width | 199 | 199 | 199 | 199 |
| **total_errors** | **1261–1263** | **1311–1312** | **1019–1020** | 1267 |

Run 1's creepage rise (262–263 vs ceiling 188) is attributed to the ring
moves: C6/Q1/U10's 15–34 mm relocations brought isolator HV↔SELV pad clusters
closer in surface distance (the exact-copper REQ-SAFE-01 validator stays 0/0
at its own 12.6 mm bar; the DRU creepage rule is a different, stricter
instance-level metric). Run 2's wide scatter improves every DRC rule while
worsening the topology — evidence that DRC quality and far-side separability
are independent axes.

---

## 5. Post-solve obstruction table (pre/post)

Re-verified with `docs/evidence/2026-08-04_domain_first_resolve_verify.py`
(pads re-projected by the per-ref solved delta; rotations pinned so pad
geometry does not rotate):

| criterion | pre (falsification) | post run 1 (ring-freed) | post run 2 (expanded) |
|---|---|---:|---:|
| minimal alternating Delaunay cycle | **12 vertices** | **4 vertices** (R25/C17/U7/U2) | 6 vertices (C18/C24/R43/C3/R22/D5) |
| alternating cycle-basis cycles | — | **45** | **47** |
| refs in alternating cycles | 10 | **78** | — |
| SELV centers inside HV hull | 137 | **129** | **174** (worse) |
| HV centers inside SELV hull | 93 | 84 | 93 |
| copper-free fraction / comps | 12.6 % / 99 | 12.7 % / 89 | 12.6 % / 67 |
| edge-to-edge corridor (opposite edges) | **none** | **none** | **none** |
| REQ-SAFE-01 | 0/0 | **0/0** | 0/0 |
| validator hard/intra/gaps | — | **0/0/0** | 0/0/0 |
| DRC total (N=5) | 1261–1263 | 1311–1312 | 1019–1020 |

**Reading the table.** (a) The 12-ring *is* broken (12→4), so freeing the ring
refs is a *necessary* move in the right direction — but the pad centers remain
curve-inseparable: 45 alternating cycles span 78 refs (C1..C37, R4..R77,
U2..U27, the isolators K1/K2/K3/PS1/T1/U3/U7, D2–D4, F1, L2, Q1/Q2, RT1,
TP1/TP3 — the whole board's interleave). (b) Freeing all 78 made the hull
interleave *worse* (129→174), because the min-displacement objective scatters
components without any clustering incentive. (c) The copper corridor remains
absent in every case — the placement-independent obstruction of §3.

---

## 6. Why the keepout is not constructible (step-5 verdict)

Two independent obstructions, each sufficient, both measured:

1. **Copper-exclusion (checks 4+5) — placement-independent, decisive.** The
   four big power pours (DC_BUS_RTN, PWR_RTN, SW_NODE, ac_n/ac_l on
   F.Cu+B.Cu) leave a zone-free space that never spans the board edge-to-edge
   (§3). No barrier polygon can both bisect the board into exactly two regions
   (check 4) and avoid every pour outline (check 5), because no such corridor
   exists and no placement can create one. **This alone makes the keepout
   impossible for ANY placement, even a perfect domain-first floorplan.**
2. **Far-side (check 6) — unsatisfiable at any achievable displacement.** Even
   after freeing the ring refs (and then all 78 cycle refs), the bichromatic
   Delaunay graph of the pad centers stays cyclic (45→47 alternating cycles).
   Eliminating every cycle requires clustering the domains spatially — the
   domain-first *floorplan* — which the hard-barrier CP-SAT constraint already
   proved infeasible (isolators cannot straddle an 8 mm corridor;
   `docs/evidence/2026-07-28-barrier-constrained-placement.md`). The
   pairwise-clearance machinery (REQ-SAFE-01) demonstrably does not produce
   that clustering (run 2).

Per the #518 dispatch's step 5 and the repo's falsification precedent, **no
keepout was drawn** — drawing one now would be "faking a zone" (the
anti-pattern `docs/plans/2026-07-31-002-fix-pr513-red-checks-and-board-debt-
plan.md` names). The gate stays red with this document as the measured reason.

---

## 7. What would make it constructible (follow-ups, not done here)

1. **Re-pour the power planes to open a corridor** — the *necessary* next
   step for checks 4+5: split/shrink the DC_BUS_RTN / PWR_RTN / SW_NODE pour
   outlines so a zone-free, ≥8.0 mm-wide (one-disk) corridor spans the board
   edge-to-edge. This is a board-geometry change (re-pour + re-fill), outside
   this dispatch's placement-only scope, and would itself need a full DRC
   ceiling re-measure + re-route.
2. **Domain-first floorplan** (the plan's R1) — the *necessary* step for
   check 6: cluster HV-only components on one side of the corridor and
   SELV-only on the other, with isolator BOM/footprint work (≥8.0 mm internal
   HV↔SELV separation) per `docs/brainstorms/2026-07-29-mains-selv-barrier-
   requirements.md`. The ring-freed solve here is a partial step in that
   direction (12-ring broken) but not sufficient alone.

---

## 8. DRC ceiling + production baseline — untouched, with rationale

**No board change was made** (`git diff origin/main -- pcb/` = empty), so:

- `power_pcb_dataset/drc_ceiling.json` is **untouched**: the recorded input
  hash `51e39844…` still matches `pcb/temper.kicad_pcb` exactly and
  `scripts/check_measurement_provenance.py` **PASSES** (verified, §9). No
  re-measurement was needed or performed; the 120-sample record from
  `2026-08-02-k3-swap-and-board-write` remains valid. No before/after per-type
  table and no `Ceiling-Approval:` trailer — nothing moved. (The DRC classes
  in §4d are *informational* measurements of solved-but-unwritten placements
  on /tmp copies, never the committed board.)
- `power_pcb_dataset/baselines/temper_production_baseline.yaml` is
  **untouched**: `drc_errors: 1046`, `drc_warnings: 472` remain properties of
  the unchanged committed board.

A future PR that *does* change the board (re-pour or floorplan, §7) must
re-measure the 120-sample ceiling and update both files in the same PR per
AGENTS.md.

---

## 9. Gates

| gate | result |
|---|---|
| `scripts/check_isolation_keepout.py` | violation (1: `missing`) — **unchanged, pre-existing #518** (the step-5 outcome keeps it red with a documented reason; no keepout forced) |
| `scripts/check_measurement_provenance.py` | **PASSED** (board hash `51e39844…` matches the ceiling record; no board change) |
| evidence provenance (`scripts/check_evidence_provenance.py`) | **PASSED for this change's files**; the gate overall reports 1 pre-existing main violation (`docs/evidence/2026-08-02-validation-portfolio-review.md`, no provenance stamp — unrelated, fails identically on `origin/main`) |
| pytest `tests/placer/cp_sat/test_isolation_barrier.py` | **37 passed** |
| pytest `tests/placer/cp_sat/test_regression_drc.py -k "drc_regression and not routing"` | **2 passed** (3 deselected — the routing/golden variants' pre-existing DesignRules parse failure on main, not chased per dispatch) |
| pytest `tests/requirements/safety/` | **112 passed** |
| pytest `scripts/tests/test_check_isolation_keepout.py` | **27 passed** |
| ruff (touched files) | clean |
| import linter (`scripts/import_linter_gate.py`) | **PASSED — 0 new violations** |
| schematics regeneration | not needed — no nets changed (no board write at all) |

## 10. Reproduction

```bash
# 1. falsification (current board, hash 51e39844)
uv run --no-sync python docs/evidence/2026-08-03_mains_selv_barrier_falsification.py
# 2. zone-only corridor analysis (NEW: placement-independent obstruction)
uv run --no-sync python docs/evidence/2026-08-04_zone_corridor_analysis.py
# 3. domain-first re-solve (production caller, fixed_copper free_refs=RING)
uv run --no-sync python docs/evidence/2026-08-04_domain_first_resolve_solve.py
# 4. post-solve verification (ring / hull / corridor at the solved placement)
uv run --no-sync python docs/evidence/2026-08-04_domain_first_resolve_verify.py
# 5. DRC class (baseline + candidate on /tmp copies; regenerated DRU)
export PYTHONPATH="$(pwd)/packages/temper-placer/src:$(pwd)/scripts"
.venv/bin/python docs/evidence/2026-08-04_domain_first_resolve_drc.py
# expected: status=clean; hard=0 intra=0 gaps=0; ring 12->4; 45 cycles on 78
# refs; corridor: 0 opposite-edge components; run1 DRC 1311-1312, run2 1019-1020
```

## 11. Files

- `docs/evidence/2026-08-04_zone_corridor_analysis.py` — zone-only corridor analysis.
- `docs/evidence/2026-08-04_domain_first_resolve_solve.py` +
  `2026-08-04_domain_first_resolve_solve_summary.json` — run 1 (ring-freed).
- `docs/evidence/2026-08-04_domain_first_resolve_solve_summary_run2_expanded.json` — run 2 (expanded free set).
- `docs/evidence/2026-08-04_domain_first_resolve_verify.py` — post-solve obstruction re-check.
- `docs/evidence/2026-08-04_domain_first_resolve_drc.py` — DRC class (baseline + candidates).
