<!-- provenance: commit=<fill-after-artifact-commit> dirty=<bool> -->

# Run-C (zone-inclusive fixed-copper) unsat-core analysis — issue #523 "gap 1"

**Date:** 2026-08-02. **Base:** origin/main at measurement time (pre-#584 merge, containing #567 polygon-exact zones, #568/#579 edge-hanging fix, #521 PD2 re-solve).

## Question

The production repair recipe (nothing pinned, ≤60mm displacement — variant B of
`docs/evidence/2026-08-01-solve-wall-box-vs-copper-gap.md`) is feasible and its
placement is validator-clean (C27 on-board at (28.62, 222.0), REQ-SAFE-01 3/1
K3-intra only — see `docs/evidence/2026-08-01-k3-resolve-validator-gated.md`).
The zone-inclusive fixed-copper variant (run-C, same envelope + zone items) is
infeasible. This analysis answers: **why, and can a copper-accurate
reconciliation unlock it?**

## Reproduction

| variant | formulation | status | notes |
|---|---|---|---|
| B | repair recipe, no zones, ≤60mm, seed 0, 180s | **feasible** (184s) | core empty; C27 (28.62, 222.0), K3 (58.08, 11.18) rot 90 |
| C | B + polygon-exact zone items (fixed-copper, #567 encoding) | **infeasible** | unsat core contents non-deterministic across runs (edge_margin_C1..C18+ in one run, empty in another) — consistent with the unsat-core non-determinism documented in `docs/solutions/best-practices/infeasibility-claims-bar-class-and-unsat-core-nondeterminism-2026-08-02.md` |

The core is not a reliable wall inventory; the deterministic measurement below
is (direct constraint evaluation at the best-known placement).

## Deterministic findings at the best-known (run-B) placement

Full per-pair table: `gap1_runc_pairs_corrected.csv` (15,113 rows), verdict
script `gap1_runc_pairs_corrected.py`, summary `gap1_runc_pairs_corrected_summary.json`;
edge-slack + exact fixed-copper audit: `gap1_runc_summary.json`.

| metric | value |
|---|---|
| pair constraints in run-C core (corrected parse) | 15,113 |
| ... box-bar blockers (`box_dist < margin`) | **42** |
| ... exact-copper violations (`copper_dist < margin`) | **0** |
| ... clean | 15,071 |
| edge-margin slack at best-known placement | all 169 refs ≥ 0.5mm (C27, C3, K2, R74, R78, SW1, U22, C40, … exactly at 0.5) |
| exact fixed-copper violations at best-known placement | **12, all `zone` kind** (0 segment/via/pad-item) |

## Verdict: PARTIAL — the two blocker classes need different treatments

1. **The pair side is bar-approximation-strict (reconciliation-able).** All 42
   box-bar-blocker pairs are **copper-clean** at the best-known placement — the
   same 45/45-style divergence measured for the pinned formulation. A
   copper-accurate separation constraint (validator-aligned, per gap 2's
   machinery) would accept all 42. This is the 8.0/PD2-valid "enabler" —
   provided the PD2 bar is legitimate (option a, sealed compartment,
   `docs/plans/2026-08-02-002-feat-sealed-compartment-plan.md`).

2. **The zone side is real geometry, not approximation.** The 12 zone-item
   fixed-copper violations are measured with the polygon-exact (#567,
   BMC-validated) zone encoding — exact copper-vs-zone polygons, not boxes.
   No copper-accurate reformulation can accept them; a run-C-feasible placement
   must actually clear the zones (different displacement envelope, seed, or
   repair rounds), or the zone geometry itself must change (board/mech change —
   out of scope for the placer). This is why run-C stays infeasible while the
   no-zones repair lands validator-clean.

3. **Edge interplay.** Several refs sit exactly at the 0.5mm edge bar (C27
   included — it is at the board edge at (28.62, 222.0)); the zone-inclusive
   formulation's demands on those refs compound the conflict. If run-C is to be
   retried, giving C27 a wider envelope (or relaxing the 60mm cap for it
   specifically) is the highest-leverage probe.

## Implication for the §4 fallback options

- The isolation slot / footprint change remains needed only for what placement
  cannot fix: K3's intra gap (being resolved by the RT314012 swap) and any
  residual zone-geometry conflict.
- PD2/8.0mm reconciliation is a **partial** unlock: it clears the 42-pair box
  side, not the 12-zone side. Full run-C feasibility is a placer-envelope
  problem, not a bar problem.
- The shipped validator-gated repair solve (no zones) already produces the
  gate-accepted candidate; run-C remains the open item for a zone-guaranteed
  candidate, tracked in issue #523.

## Artifacts

- `gap1_runc_measure.py` — B/C variant runner + core extraction
- `gap1_runc_solve_cores.json` — raw cores per variant (non-deterministic; see above)
- `gap1_runc_core_table.csv` — per-constraint core table
- `gap1_runc_pairs_corrected.csv` / `.py` / `_summary.json` — corrected pair verdicts
- `gap1_runc_summary.json` — edge slack, exact fixed-copper audit, verdict counts

## Provenance

Measured on the clean tree at the artifact commit (see header); the two
independent measurement scripts agree on the headline numbers (42 box-bar
blockers / 0 copper violations; 12 zone-item fixed-copper violations).
