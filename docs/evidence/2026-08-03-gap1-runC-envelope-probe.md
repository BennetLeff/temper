<!-- provenance: commit=f6933d0a241ea1bc04f8395cf2ee4fe7d87c459e dirty=false (re-pointed from a dangling SHA to the base commit this document's own Sec "Base" line already names -- see below) -->

# Gap-1 run-C envelope probe — does relaxing the displacement cap unblock the zone-inclusive solve? (issue #618)

**Date:** 2026-08-03. **Base:** origin/main at measurement time
(`f6933d0a241ea1bc04f8395cf2ee4fe7d87c459e`, post-#602 board write: K3 is the
RT314012 swap, C27 at (28.62, 222.0) normalized — the written board IS the
best-known placement). **Measurement tree:** clean at the artifact commit
(see header).

## Question

The run-C verdict (`docs/evidence/2026-08-01-gap1-runC-unsat-core.md`, #598)
left one open probe: *"If run-C is to be retried, giving C27 a wider envelope
(or relaxing the 60mm cap for it specifically) is the highest-leverage
probe."* This spike runs that probe against the CURRENT board (the old
measurement predates the #602 board write) and asks the deterministic
question the unsat core cannot answer: **does ANY zone-inclusive solve
terminate feasible as the displacement envelope is relaxed, and if not, which
zone items are unsatisfiable at ANY reachable placement?**

## Reproduction on the current board

Formulation (identical to the run-B/C recipe): nothing pinned, rotations
fixed, hard Manhattan displacement cap, domain-clearance + keepaway
SeparatedConstraints (12,101 total for 169 refs), fixed-copper vs
traces/vias/zones/other pads for FREE={K3,C27} at margin 0.05mm.

| variant | cap | seed | C27 in disp. obj. | status | solve time | core |
|---|---|---|---|---|---|---|
| `B_60_s0` (no zones) | 60 | 0 | yes | **feasible** | 181.6s | 0 |
| `C_60_s0` (zones) | 60 | 0 | yes | infeasible | 2.15s | 15,285 |
| `C_120_s0` (zones) | 120 | 0 | yes | infeasible | 1.97s | 15,285 |
| `C_120_s1` (zones) | 120 | 1 | yes | infeasible | 1.81s | 15,285 |
| `C_c27x_s0` (zones) | 60 | 0 | **no (C27 unbounded)** | infeasible | 1.94s | 15,285 |
| `C_240_s0` (zones) | 240 | 0 | yes | infeasible | 2.06s | 15,285 |
| `C_nobigpours_s0` (zones, big pours dropped) | 60 | 0 | yes | infeasible | 1.72s | 15,285 |

Findings:

1. **The no-zones reproduction holds**: `B_60_s0` is feasible (181.6s) and
   its placement is validator-clean — the exact fixed-copper audit at the
   best-known placement (the current board) reports **0 violations**.
2. **Every zone-inclusive variant is infeasible in ~2s** — cap 60→120→240,
   seed 0→1, and C27 fully excluded from the displacement objective
   (unbounded) change nothing. **The displacement envelope is not the
   lever.** The 2s solve time and byte-identical core size (15,285) across
   all six variants indicate a structural (encoding-level) unsatisfiability,
   not search-order noise and not a displacement-bound conflict.
3. **Even dropping the three board-spanning pour nets
   (DC_BUS_RTN/SW_NODE/+15V_LS) from the fixed-copper parse_result leaves
   the solve infeasible** in 1.7s — the blocker is not unique to those three
   pours.

## Deterministic zone-conflict analysis at the best-known placement

Cores are non-minimal and search-order-dependent (documented in
`docs/solutions/best-practices/infeasibility-claims-bar-class-and-unsat-core-nondeterminism-2026-08-02.md`),
so the deterministic measurement is direct constraint evaluation at the
best-known placement (the current board), exactly as
`gap1_runc_pairs_corrected.py` does.

### Pair side (unchanged character from the old board)

15,113 pairs named in the run-C core: **38 box-bar blockers, 0 exact-copper
violations, 15,075 clean** at the best placement — the pair side remains
bar-approximation-strict (copper-clean), the reconciliation-able class
identified in #598 (the 42→38 delta is the K3 swap's geometry).

### Exact zone side (20 violations on the current board, not 12)

The exact fixed-copper audit at the best placement reports **20 zone-item
violations** (the old doc's 12 were measured pre-#602, on the G5LE-1 K3;
the RT314012 swap changed K3's pad field):

| free ref | pad(s) | zone net | count | clearance at best | required |
|---|---|---|---|---|---|
| K3 | 1,2,3,4,5 (8 physical pads) | SW_NODE | 16 (×2 layers) | 0.0 mm | 0.05 mm |
| C27 | 2 | DC_BUS_RTN | 2 (×2 layers) | 0.0 mm | 0.05 mm |
| K3 | 3 | +15V_LS | 2 (×2 layers) | 0.0 mm | 0.05 mm |

C27 pad 2 straddles the DC_BUS_RTN pour's top edge at the board's top edge
(the 0.5mm edge bar region); K3 sits inside the SW_NODE pour with pad 3
clipping the +15V_LS bottom strip.

### Is each zone's demand met anywhere the component can actually go?

Per-pair exact-oracle reachability over the Manhattan displacement envelope
(gated by the same edge_margin ≥0.5mm the solver enforces), holding
rotations fixed, using the R24 audit's own exact oracle
(`exact_clearance_mm`):

| (ref, pad) vs zone | min displacement to clear | exact-clear cells / 231,361 |
|---|---|---|
| C27 pad 2 vs DC_BUS_RTN | **1.0 mm** → (29.62, 222.0) | 14,973 |
| K3 pad 1 vs SW_NODE | 11.0 mm | 23,793 |
| K3 pad 2 vs SW_NODE | 26.0 mm | 19,709 |
| K3 pad 3 vs SW_NODE | 7.5 mm | 24,834 |
| K3 pad 3 vs +15V_LS | 0.5 mm | 42,871 |
| K3 pad 4 vs SW_NODE | 14.0 mm | 22,936 |
| K3 pad 5 vs SW_NODE | 18.5 mm | 21,496 |

**Jointly (all of a ref's conflicting zones at once), within the cap:**
C27 clears every zone at (29.62, 222.0) — 1.0 mm displacement; K3 clears
every zone at (16.12, 7.42) — 37.5 mm displacement. Both remain satisfiable
within the **60mm** cap (C27: 3,918 cells; K3: 1,030 cells of 58,081).

**So the exact zone geometry is NOT inherently unsatisfiable**: every
conflicting zone's demand is met somewhere within the current 60mm envelope,
per the same exact oracle the audit and BMC test use.

### Why the solver still cannot reach any of those positions — the encoding

The fixed-copper zone encoder (`fixed_copper.py::_zone_item`) applies the
polygon-exact half-plane encoding (#567) only to **convex rectilinear**
zones; any zone with a diagonal edge (or non-convex outline) falls back to
its axis-aligned bounding box. Of the 96 zone items on the current board,
**54 are bbox-fallback** — including the board-spanning pours
(DC_BUS_RTN, SW_NODE, +15V_LS, GATE_HS, PWM_HS, PWM_LS, PWR_RTN, ac_l,
ac_n; each ×2 layers), all convex polygons with diagonal edges.

Measured at the same envelope grid, the solver's *encoded* predicate accepts
almost none of the exact-clear positions:

| (ref, pad) vs zone | encoding | exact-clear cells | **encoded-clear cells** |
|---|---|---|---|
| C27 pad 2 vs DC_BUS_RTN | BBOX | 14,973 | **0** |
| K3 pad 1 vs SW_NODE | BBOX | 23,793 | 3,225 |
| K3 pad 2 vs SW_NODE | BBOX | 19,709 | 208 |
| K3 pad 3 vs SW_NODE | BBOX | 24,834 | 4,575 |
| K3 pad 3 vs +15V_LS | BBOX | 42,871 | 39,630 |
| K3 pad 4 vs SW_NODE | BBOX | 22,936 | 3,225 |
| K3 pad 5 vs SW_NODE | BBOX | 21,496 | 3,448 |

**C27 pad 2 vs DC_BUS_RTN is the smoking gun**: the DC_BUS_RTN pour's AABB
(4.26, −5.25)–(160.15, 232.98) contains the *entire* 152×234 board, so the
encoded constraint "pad outside the bbox" is unsatisfiable for any on-board
placement — 0 encoded-clear cells vs 14,973 exact-clear cells. This is why
the solve dies in ~2s regardless of cap, seed, or C27's displacement bound:
**the infeasibility is the encoding, not the envelope and not the zone
geometry.** The other big bbox pours shrink K3's encoded zone-clear region
to a sliver (208–4,575 of 231k cells) and force it toward the crowded top
edge, compounding the same effect.

### Compound sanity check at the per-ref zone-clear candidate

Moving both free refs to their joint first-clearing positions
(C27 → (29.62, 222.0), K3 → (16.12, 7.42)) produces **14 new exact
fixed-copper violations** (K3 pad 2/4 vs GATE_HS zone at 0.035/0.000mm, K3
pads vs the ESP32 module's pads io41/io42/gpio35/gpio36, K3 pad 4 vs two
segments). The naive per-ref zone-clear candidate is not compound-clean —
run-C feasibility under an exact encoding is a genuine (still unsolved)
placement search, not a foregone conclusion. What this probe establishes is
that the current infeasibility is *structural and encoding-level*: the
solver is blocked by construction before any placement search can reach the
exact zone-clear region.

## Verdict: run-C is unblockable by envelope alone — the blocker is the zone encoding's AABB fallback

1. **Envelope-only is not a lever (answered).** Cap 60→120→240 mm, seed
   variation, and C27-unbounded displacement all leave the zone-inclusive
   solve infeasible in ~2s with an identical 15,285-constraint core. The
   #598 "relax the 60mm cap for C27" probe is closed: **no envelope change
   unblocks run-C.**
2. **The exact zone geometry is not the blocker (answered).** Every one of
   the 20 zone-item violations is individually satisfiable within the 60mm
   envelope per the exact oracle, and jointly per ref (C27: 1.0mm; K3:
   37.5mm). The zones' demands are met "anywhere C27 can actually go" — the
   old doc's open question about "different displacement envelope, seed, or
   repair rounds" is answered in the affirmative for the *geometry*.
3. **The blocker is the fixed-copper zone encoding.** 54/96 zone items
   (incl. every board-spanning pour) fall back to axis-aligned bounding
   boxes because they have diagonal edges; the DC_BUS_RTN AABB contains the
   whole board, making C27's encoded zone constraint unsatisfiable on-board
   (0 encoded-clear cells vs 14,973 exact). The fix is a **placer src/
   change**: extend the #567 polygon-exact half-plane encoding to general
   convex zones with diagonal edges. This is expressible in CP-SAT — for
   fixed rotations the pad's four corner coordinates are linear in the
   component center, so each diagonal edge yields one BoolOr over four
   corner half-plane literals (the rectilinear path's exact analogue).
4. **Neither a zone-geometry (board/mech) change nor the isolation slot is
   demonstrated as necessary.** Zone-geometry change (making the pours
   rectilinear so the existing exact encoding engages) is an alternative
   board-side workaround; the isolation slot / footprint change remains
   needed only for what placement cannot fix — and this probe does not show
   any placement-irreducible zone conflict (all are exact-clearable within
   the envelope). If, after the encoding fix, the exact compound problem is
   still infeasible (the candidate compound audit shows 14 new non-zone
   conflicts at the naive candidate), that residual would then justify a
   zone-geometry / slot decision — tracked as a follow-up, not answered
   here.
5. **R2 keepout tie-in (`docs/plans/2026-08-02-002`).** The
   MAINS_SELV_ISOLATION_BARRIER keepout is currently absent from the board,
   so it cannot be a cause of the measured infeasibility; when it lands it
   adds a *new* hard constraint run-C must satisfy and does not address the
   zone-encoding blocker — it is orthogonal to this probe, and the plan's
   own sequencing (R5 board write → R2 keepout) is unaffected.

## Artifacts

- `gap1_runc_envelope_probe.py` — variant matrix runner (cap × seed ×
  C27-exclusion × big-pours-dropped) + deterministic analysis (pairs,
  exact fixed-copper audit, per-pair/joint exact reachability, encoded
  reachability, candidate compound audit). No src/ or pcb/ changes.
- `gap1_runc_envelope_matrix.json` — per-variant status/time/core.
- `gap1_runc_envelope_zones.json` / `.csv` — zone-conflict reachability.
- `gap1_runc_envelope_joint.csv` — joint (per-ref all-zones) reachability.
- `gap1_runc_envelope_pairs.csv` — pair verdicts at the best placement.

## Provenance

Measured on the clean tree at the artifact commit (see header). The
measurement scripts re-derive the run-C formulation from the committed
board (`pcb/temper.kicad_pcb` at origin/main) and the committed test
fixture; `pcb/`, `src/`, and `elec/` were untouched.
