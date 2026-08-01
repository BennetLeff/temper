<!-- provenance: commit=b11c903889a9066257bc18fcc13b74a804fc6f60 dirty=false -->

# Pad-vs-fixed-copper NoOverlap CP-SAT constraint (issue #523 Option 3)

**Date:** 2026-08-01
**Scope:** `pcb/**` read-only (only parsed, never written). `elec/**` untouched. All
solve results in this doc are candidate placements measured in memory / scratch
(`/tmp/opt3_*`), never committed to the tracked board. Writing K3's placement to
`pcb/temper.kicad_pcb` is explicitly **NOT done here** — that write awaits human
approval (see GO/NO-GO, §7).

**Base:** worktree `.claude/worktrees/agent-opt3-fixed-copper`, branch
`feat/fixed-copper-constraint-opt3` from `origin/main` `7c474b820`
(`scripts/assert-base.sh origin/main` OK). `uv sync --all-packages --inexact`,
`make netlist`, `make extensions` (11/11 fresh). HEAD at measurement time:
`b11c903889a9066257bc18fcc13b74a804fc6f60` (branch rebased onto origin/main
`37a4251e0` after main moved 9 commits mid-session; none touched the files in
this change), tree clean.

---

## 1. The gap this closes

The placer's constraint vocabulary separated components from fixed geometry only
at whole-component level: `SeparatedConstraint` (courtyard boxes),
`KeepoutConstraint` (named zones), `NoOverlap2D` (components off each other).
Nothing constrained a *pad* of a placed component against the board's
*pre-existing routed copper* (traces, vias, pours, other components' pads). The
K3 blocker (TE Schrack RT314012) was exactly that hole: its NO pad lands on a
pre-existing B.Cu track (`hb.gate_hs.driver-p2`, segment (48.85,45.25)→(48.85,45.15))
— a measured physical short (5 `shorting_items`) that no clearance/domain
mechanism addressed (the net is not domain-declared; the 12.6mm pairs are
component-component only).

Delivered: `packages/temper-placer/src/temper_placer/placer/cp_sat/fixed_copper.py`
— a new constraint generator + CP-SAT encoder + exact oracle + R24 post-solve
audit, wired into `solve_placement(fixed_copper=...)` (`_encoder_solve.py`).
Existing behaviour is unchanged when the parameter is absent (all pre-existing
cp_sat tests stay green).

## 2. Constraint semantics

For every FREE (being-placed) component, every pad's copper rectangle (pad local
geometry + component quadrant rotation, in the solver's placement frame) must
NOT overlap any fixed-copper item of a **different net** on any **shared copper
layer**, with a 0.05 mm margin (matching the verified issue-#523 grid search).
Fixed-copper items come from `ParseResult.traces`/`.vias`/`.board.zones` (dead in
the solver path before this change) plus every pinned component's pads.

## 3. Encoding choices + conservatism bounds (v1, conservative boxes)

| item | exact copper | encoded obstacle | conservatism bound (worst case) |
|---|---|---|---|
| trace segment | thick segment (stadium, radius w/2) | `bbox(segment) ⊕ (w/2 + margin + headroom)` | computed **per segment** as the exact max corner overhang, `segment_slack_mm` = max over the 4 bbox corners of `dist(corner, centerline) − w/2 − margin`; a diagonal segment's corner can be ~L/2 from the track (NOT the axis-aligned `(√2−1)(w/2+m)` closed form, which under-reports diagonals — see §5.1) |
| via | disc (radius d/2) | bounding square ⊕ (d/2 + margin + headroom) | `(√2−1)(d/2 + margin + headroom)` |
| zone (pour) | fill region (parser sees only the outline polygon) | outline-polygon **bbox** ⊕ (margin + headroom) | unbounded by construction for a large/diagonal pour (bbox can span the board while the fill is carved into islands). **Documented future tightening: polygon-exact zone encoding.** |
| other component's pad | pad's own rect (rotated) | rect ⊕ (margin + headroom) | `(√2−1)(margin + headroom)` (square expansion of a rect) |

Per (pad, item) pair whose layers intersect and nets differ, one `BoolOr` over
four linear literals (pad left/right/below/above the item's expanded box), gated
on a per-component assumption literal `fixed_copper_<ref>` for unsat-core
attribution. Pad world rect is affine in `x_center`/`y_center` with rotation
tables over the model's 4 quadrant indices (rot 1/3 swap local half-extents,
matching the model's own size tables and the repo's sanctioned R(−θ)
convention). Degenerate pads clamp to a 0.01 mm half-extent (CP-SAT requires
positive intervals; the clamp makes the encoding strictly more conservative).

**Net/layer filtering:** an item is an obstacle only if (a) the item's copper
layers intersect the pad's layers (THT pads are on all four copper layers), and
(b) the item's net is not one of the free component's own nets (own-net copper
is the future connection, not a short). `include_other_pads` flag (default on)
turns pinned components' pads into obstacles; the flag exists for A/B runs.

## 4. Soundness proof (R24 item 1 — Chebyshev-style)

Let E be the encoded obstacle and S the exact copper shape. For every item kind,
`E ⊇ S ⊕ margin` (a shape is contained in its own bbox; the pad square expansion
contains the disc expansion). If CP-SAT declares feasibility, every pad rect
avoids every E, hence avoids every `S ⊕ margin` on every shared layer — so
**the encoded predicate implies the exact geometric predicate: no false
negatives.** The encoding can only reject placements that are exactly clear
(conservatism, bounded per kind in the table above).

**Integer-grid term the containment alone does not cover (measured, fixed).**
The encoding then quantizes to the 0.01 mm integer grid: `mm_to_units` is
round-half-even, and a pad edge carries two such terms (offset + half-extent)
while an item edge carries one. Worst case the encoded predicate could accept a
placement whose exact clearance is `margin − 0.015 mm`. **Measured on the real
board**: a feasible repair solve placed K3 pad 3 at 0.040 mm from a PWR_RTN pad
with margin 0.05 mm, and the R24 post-solve audit (exact oracle, independent of
the solver) caught it as a hard failure. **Fix landed in
`caa301cc0`**: every item's encoded box embeds `_GRID_HEADROOM_MM = 0.02 mm`
(2 units) beyond the margin, so the effective containment is `E ⊇ S ⊕
(margin + headroom)` and the 1.5-unit worst-case erosion can never push the
guaranteed clearance below the physical margin (0.5 unit stays unspent). The
audit and BMC oracle still compare against the physical `margin`, so a
feasible solve necessarily clears every item by at least `margin`.

## 5. BMC-exhaustive validation (R24 item 2)

`tests/placer/cp_sat/test_fixed_copper.py::TestFixedCopperSoundnessBMC` sweeps
the **encoded** predicate (`encoded_pad_world_rect`, which mirrors the
encoder's half-extent clamp, vs `encoded_overlap`) against the **exact** oracle
(`exact_clearance_mm`, the same function the post-solve audit uses) over:

- pad sizes: degenerate (0,0), square (1,1), elongated (3,2) — all ×4 rotations;
- item shapes: horizontal/vertical/diagonal/degenerate segments, via, pad rect,
  L-shaped zone;
- a 121×121 offset grid (0.05 mm steps, −3..+3 mm) per case, covering
  touching / overlapping / clear at 0.9× / 1.0× / 1.1× margin and beyond.

Two assertions, both directions:
1. **Soundness**: `encoded_overlap == False ⇒ exact_clearance ≥ margin − 1e-9`.
   Zero counterexamples over **>100k checked cases** (`checked > 100_000` guard
   against sweep collapse; float-eps tolerance at the exact-margin boundary).
2. **Conservatism**: encoded-overlap cases whose exact clearance is still ≥
   margin must not exceed the per-item documented slack (`excess ≤ slack_mm +
   1e-9`), and the sweep must actually exercise a corner (excess > 0) so the
   bound check is not vacuous.

17/17 tests in `test_fixed_copper.py` pass (generator-not-vacuous on the real
board, item-building/frame-normalization, BMC sweep, post-solve audit, and
solve-level fail-capable tests). The sweep **falsified the first
implementation twice**, each a real defect (see §5.1, §5.2) — the tests earn
their keep.

### 5.1 Defect found: segment slack closed form is diagonal-unsound

The initial `slack_mm = (√2−1)(w/2+m)` is exact only for axis-aligned segments;
a diagonal segment's bbox corner can be ~L/2 from the actual thin track
(measured 2.52 mm excess on a 5 mm diagonal segment vs the 0.124 mm documented
bound). Fixed: `segment_slack_mm` computes the exact worst-case corner overhang
per segment (convexity: distance to the stadium is convex, so the max over the
box is at a corner).

### 5.2 Defect found: degenerate-pad clamp invisible to the sweep

Evaluating the encoded predicate against the raw (unclamped) pad rect let a
degenerate point pad sit at exactly the margin distance and report a
counterexample the real encoder (which clamps to a 0.02 mm box) rejects. Fixed:
`encoded_pad_world_rect` applies the same `_MIN_HALF_MM` clamp as the encoder,
so the sweep and the encoder cannot drift.

### 5.3 Defect found by the post-solve audit (not the sweep): grid headroom

See §4 — only a full-board solve with the exact oracle surfaced the 1-unit
quantization erosion at the margin boundary. This is the reason the audit is a
hard failure, not a warning.

## 6. Post-solve audit (R24 item 3)

`audit_fixed_copper(pads, items, resolved_positions_mm, resolved_rotations)`
recomputes the **exact** pad-to-copper clearance from the resolved coordinates
and rotation indices, independent of whatever the solver claims, using the same
oracle the BMC sweep uses (`exact_clearance_mm`). A violation (clearance below
the physical margin for a different-net, shared-layer pair) means the soundness
proof failed for this solve — an encoding bug — and `solve_placement` **raises**
when `fixed_copper=` was given and a feasible solve produces violations
(hard failure, not a reportable warning). `audit_domain_clearance` continues to
run as before. The audit is what caught §5.3 in production-grade conditions.

## 7. Scoped solve on the real board (READ-ONLY) — result

Driver `/tmp/opt3_final.py` (scratch, not committed), board
`pcb/temper.kicad_pcb` (origin (20,20), 152×234 mm), FREE = {K2, K3, C27},
domain-clearance (12.6 mm bar, full 47-net classification) + keep-away
constraints, fixed-copper at 0.05 mm margin with other-pads on, timeout 180 s,
seed 0, hints = current positions.

| run | formulation | status | K3 result | audits |
|---|---|---|---|---|
| A | FREE + everything else **pinned** (task-brief scoped solve), FC with zones | **infeasible** (1.95 s) | — | unsat core 15737: edge_margin 169 + sep 15564 + fixed_copper 3 |
| A0 | everything pinned, **no** extra constraints, no FC | **infeasible** (<1 s) | — | 6 pre-existing bounds-box overlap walls on the current board: C1/R7, C14/C5, C25/K3, C3/C4, D2/F1, K3/R12 (see §8) |
| B | production repair recipe (nothing hard-pinned, min-displacement to current), FC **without** zone items | **feasible** (121.7 s) | **K3 → (126.0, 50.78) rot 1** (moved 91 mm in x); K2 → (131.7, 90.6); C27 → (24.54, 222.0) | **fixed-copper 0 violations, domain-clearance 0 violations** |
| C | same as B, FC **with** zones | **infeasible** (2.3 s) | — | unsat core 15737, fixed_copper_* present for all 3 free refs |

**Attribution (which class binds).** Run C's infeasibility is the **fixed-copper
zone items**, not the segment/via/pad encoding and not the domain/overlap
constraints: run B proves the identical recipe is feasible (and audit-clean)
once the 96 zone items are dropped, and the issue-#523 spike's *exact*
zone-polygon check found 945 viable K3 origins on the same board — the zone
items are genuine whole-board pours (SW_NODE bbox 135×229 mm, PWR_RTN 126×210
mm, ac_n 102×196 mm) whose **bbox** encoding blocks every candidate the exact
polygon permits. This is precisely the documented zone-bbox conservatism of §3;
a polygon-exact zone encoding (the documented future tightening) is what would
make run C feasible.

Run A's infeasibility is **not** a fixed-copper problem at all: run A0 shows the
base model (NoOverlap2D + edge margins) is already unsatisfiable with everything
pinned, because the *current* board carries 6 genuine bounds-box overlaps among
refs that must stay pinned — the tracked `courtyards_overlap` DRC debt
(14-16 records; a prior session's evidence
`2026-07-31-k3-rtsolve-infeasible-board.md` measured the same wall class on the
then-current board with 31 overlap pairs). A scoped pin solve on this board is
structurally infeasible before the fixed-copper constraint is even added; walls
1-3 (edge-quantization pins, NoOverlap2D overlaps, τ/netclass cross-class
violations at pinned positions) must be paid down by a geometry-repair pre-pass
first.

**The fixed-copper constraint itself works.** Run B is a genuine end-to-end
demonstration: with the documented zone conservatism removed, the solver finds a
placement of K2/K3/C27 whose pads clear every one of the 2,895 segment/via/pad
obstacles at ≥ 0.05 mm, and the post-solve audit (exact oracle, hard failure on
any mismatch) confirms zero violations — including for K3's THT pads on all four
copper layers. The fail-capable solve-level tests prove both directions: a pad
deliberately on a different-net track is rejected (infeasible, unsat core names
`fixed_copper_*`), a clear placement is accepted.

## 8. Why the K3 blocker measurement differs from the spike

The current board's K3 is still the G5LE-1 footprint at (34.9, 50.78) rot 1 — the
RT314012 swap has not landed on main (prior sessions reverted it; see
`docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md`). The blocker track
`hb.gate_hs.driver-p2` is present at normalized (28.85, 25.25)-(28.85, 25.15).
The exact fixed-copper oracle reports **10 zone violations** at K3's current
position (SW_NODE/PWR_RTN pours) — consistent with the shorting regression the
prior session measured when the RT314012 was embedded at its origin. K3's
current position does not overlap the gate-driver track in the *segment* oracle;
the pours are what it sits on, which is exactly what run C's zone items forbid.

## 9. Gate verification

- `uv run --no-sync pytest packages/temper-placer/tests/placer/cp_sat/ -q -p no:cacheprovider`:
  **578 passed, 4 skipped, 1 xfailed, 2 failed → 0 failed after `make netlist`**
  (the 2 failures are `TestRealBoardClearanceRepair`, which require
  `elec/build/default.net`; with the netlist built both pass). All pre-existing
  tests stay green; the known pre-existing production-board DRC regression
  (unconnected 393) is already fixed on main by PR #540.
- `ruff check` on all touched files: clean.
- `uv run --no-sync python scripts/import_linter_gate.py`: 0 new violations
  (fixed_copper.py imports only from `temper_placer.pcl.constraints`-adjacent
  public modules, consistent with the cp_sat package's existing boundaries).

## 10. GO / NO-GO on writing K3's placement to the board

**NO-GO.** The fixed-copper constraint is sound, audit-protected, and
BMC-validated, and run B proves the encoder can find a placement with zero
exact-oracle violations when zones are excluded — but run C shows the v1
zone-bbox encoding blocks every candidate on this board (whole-board pours), so
a solve with zones enabled cannot yet produce a placement for K3 to write. And
run A shows the scoped pin formulation is structurally infeasible on the current
board's geometry debt regardless of this constraint. Writing K3 to the board now
would either use run B's zone-blind result (which sits on SW_NODE/PWR_RTN pours
— a real short) or skip the solve entirely (the current shorting state). Neither
is acceptable.

**Before a human approves the write**, in order:
1. Implement the documented zone tightening (polygon-exact zone encoding, or
   zone items filtered to their actual fill islands) — expected to make run C
   feasible while keeping soundness (the spike's 945 exact-polygon-viable
   positions remain reachable).
2. Pay down walls 1-3 (geometry-repair pre-pass nudging the ~6-40 overlapping /
   edge-quantized pinned refs) so run A's pin formulation becomes feasible — or
   accept a full re-layout under the repair recipe.
3. Re-run the scoped solve (run C) to `feasible`, confirm the R24 post-solve
   audit reports 0 violations, verify against the independent REQ-SAFE-01
   validator and a DRC measurement, THEN write K3's placement in a separate
   board-changing PR with the DRC-ceiling re-measurement that PR requires.
