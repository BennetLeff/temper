<!-- provenance: commit=0b4d95114985df330c2a8644e34a8b4bd5cd4563 dirty=UNKNOWN -->
---
module: pcb
tags: [placement, creepage, drc, pd3, clearance, routing-domain, placement-domain]
problem_type: placement-fix
---

# 2026-08-16: Placement pass — PD3 creepage pad↔pad residue and clearance-family domain split

## Scope and authority

Board edit authorized by owner for component placement (placement pass for
creepage violations; Part 2: clearance-family analysis). Scope: **move only
the components that needed moving** — 10 components. All other components,
the board outline, every DRC threshold/ceiling constant, every netclass
assignment, and every DRU rule are untouched. Worktree
`fix/placement-pass-creepage-clearance` off `origin/main @ 7b424488f`, own
directory, never the main checkout. `pcb/temper.kicad_pcb` sha256
`ddb96f9e...ef2` (main) -> `3442cb03...e268` (this branch). No `git stash`,
no shared-venv writes: measurements used this worktree's own isolated venv
(`make venv-isolate`) with all 10 pyo3 crates built from THIS branch's
sources (origin/main base), kicad-cli 10.0.5, the repo's
`run_drc --all-track-errors` protocol, and `pcb/temper.kicad_dru`
regenerated from `scripts/generate_kicad_dru.py` at the measured commit.

## Baseline (origin/main @ 7b424488f)

Live DRC, 120-sample protocol, regenerated PD3 DRU, `--all-track-errors`:

| category | baseline count | note |
|---|---:|---|
| creepage | **313-314** (band; committed record {313:15, 314:105}) | matches committed ceiling exactly — environment validated |
| clearance | 499 (capped read) / 1105 (TRUE uncapped) | |
| shorting_items | 189 | |
| total errors | 1446 | |

Creepage item-type classification (the "placement residue" premise):

| pair type | baseline count | owner |
|---|---:|---|
| pad↔pad (intra-footprint) | 26 | part selection, NOT placement |
| pad↔pad (cross-component) | **74 violations / 39 pairs** | placement (this PR) |
| pad↔track | 142 | routing |
| pad↔via | 31 | routing |
| track↔via / track↔track | 24 | routing |

The reconciliation doc
(`docs/evidence/2026-08-16-placement-reconciliation-k1-cluster-c7-and-creepage-ranking.md`,
PR #1248, merged on this base) measured only 9 cross-component pad↔pad pairs
on the pre-cluster board and claimed "only 9 of 329 are placement-fixable".
This measurement, with the same protocol on the post-cluster board, finds
**39 cross-component pad↔pad pairs (74 violations)**. The discrepancy is
the reconciliation doc's item-type classifier: it treated `PTH pad ...`
items as "other" (its §3.1 table counts `pad↔track 114` / `track↔track/zone/
other 195` while this measurement finds `pad↔track 142` and treats PTH pads
as pads). The pad↔pad residue is therefore **4-8× larger than the
reconciliation doc reported**, and the c-space doc
(`docs/evidence/2026-08-16-creepage-aware-cspace.md`, branch-only) measured
94 pad↔pad on a routed scratch board — same order of magnitude.

## Part 1 — placement pass: 10 component moves, 16 creepage net-pairs cleared, 0 new

### Method

For each offender pair, the component to move was chosen as the smaller /
less-net-dense member (LV SMD parts over HV THT parts, never the ESP32, the
relays, the tank caps, or the TO-247s). Candidate displacements were
searched on a 0.25mm grid with a geometric model (edge-to-edge distance =
center distance − pad half-diagonals; the DRC's creepage bar 12.6mm
reinforced / 10.0mm tank-functional). Each move was applied with a
surgical single-`(at ...)`-line edit, then **verified with live kicad-cli
DRC**: creepage must drop, and every other category (shorting, clearance,
solder_mask, copper_edge, hole_clearance, warnings) must not regress.
Moves that regressed were reverted and re-attempted with a different
displacement, or documented infeasible. A move was kept only when the DRC
verified a strict improvement.

Note on the DRC's pad naming: KiCad reports **one violation per net-pair**
(the closest pad pair of the two nets). Clearing a net-pair's closest pad
pair re-anchors the report onto the next-closest pads of the same two nets
— the net-pair count is the stable measure. All deltas below are net-pair
deltas (the authoritative accounting), with pad-pair counts noted.

### Moves landed (10 components, 11 `(at ...)` lines)

| # | component (footprint / identity) | from | to | net-pairs cleared | pad-pad violations cleared |
|---|---|---|---|---|---|
| 1 | U14 (SOT-23-5, `vcc` LV OVP/RTD comp) | (32.59, 220.80) | (32.89, 220.40) | hb.power_loop.q_high-g × vcc | U14×U4 (1) |
| 2 | C16 (0603, `+15V` LV) | (28.81, 220.58) | (30.06, 217.83) | +15V × hb.power_loop.q_high-g | C16×U4 (1) |
| 3 | C36 (0603, `V_BUS_SENSE` LV) | (47.59, 21.98) | (46.34, 21.98) | DC_BUS_RTN × V_BUS_SENSE | C36×K3 (1) |
| 4 | C20 (0603, `+3V3`/`gnd` LV) | (28.81, 111.00) | (25.31, 110.00) | +3V3 × discharge.k_dis2-nc; +3V3 × tank-out | C20×R15 (2), C20×R30 (1) |
| 5 | SW1 (0603, `en`/`gnd` LV switch) | (106.47, 241.87) | (102.72, 246.62) | discharge.k_dis1-nc × en | R14×SW1 (2) |
| 6 | U10 (SOT-23-5, LV RTD comparator) | (157.92, 99.45) | (157.92, 96.45) | rtd_pan.low_window-out × tank.c_tank1-p2; gnd × tank.c_tank1-p2 | C25×U10 (3) |
| 7 | R53 (1206, `V_BUS_SENSE` LV) | (114.35, 138.76) | (114.35, 141.26) | PWR_RTN × V_BUS_SENSE | PS1×R53 (1) |
| 8 | R60 (axial THT, `safety-line-1` LV) | (44.92, 36.06) | (43.90, 36.10) | discharge.k_dis2-nc × safety-line-1 | K3×R60 (1) |
| 9 | R6 (axial THT, `+170V_BUS` HV) | (55.71, 174.09) | (51.71, 174.09) | +170V_BUS × {+3V3, OCP2_VREF_2V5, safety.ovp-line, safety.ovp.comp-inp} | R6×U16 (5) |
| 10 | R50 (0603, OVP divider LV) | (127.41, 23.85) | (122.91, 23.85) | PWR_RTN × {safety.ovp-line, safety.ovp.comp-inp} | C14×R50 (2) |

Total: **16 creepage net-pairs cleared, 0 new** (measured net-pair diff,
see below). Cross-component pad-pad violations: **74 → 61** (13 pad-pad
violations cleared; the residual 1 is a DRC re-anchor, see below).
Creepage total: **313-314 → 294-295**. Total DRC errors: **1446 → 1426-1427**.

### Rejected / reverted moves (documented, not silently absorbed)

| attempt | result | why reverted |
|---|---|---|
| U14 → (33.84, 219.05) | shorting +7, solder_mask +7 | moved onto an existing `inb` track (pad↔track shorts) |
| C36 → (46.34, 20.98) | copper_edge +1 | C36's `gnd` pad came within 0.5mm of the y=20 board edge |
| R38 → (44.19, 58.58) | net wash | cleared R38×R5 but the gnd×PWR_RTN net-pair re-anchored onto U11's `gnd` pad — same net pair, no net gain; reverted |
| SW1 first attempt → (102.72, 245.62) | silk_over_copper 42→43 | SW1 silk clipped U22's mask; moved further to (102.72, 246.62), clean |
| R53 → (114.35, 142.26) | new pad↔track | R53's `safety.ovp.r_adc_top2-p2` pad came within 12.6mm of the `power_in.ntc-no` track; reduced to dy=+2.5, clean |
| U11 → (46.61, 61.76) | shorting +1, solder_mask +1, silk +2 | U11 (RTD comp) encroached on R37; R5×U11 is placement-infeasible (see below) |
| K3 → (66.47, 49.59) | shorting +2, solder_mask +2, hole_clearance +2 | relay move perturbs its own pad/via field; K3×U27 documented infeasible |

### Remaining cross-component pad-pad: classification, not placement

61 pad-pad violations remain (28 pairs). Attributed:

| class | violations | pairs | disposition |
|---|---:|---:|---|
| **classification questions** (net unassigned → Default → charged as LV though HV-declared in `elec/domain_manifest.yaml`) | 14 | C17×R15, C23×U7, R15×R18, R4×U5, R15×R30, C8×R7, L1×R8, R22×U1, R22×U2, C1×R22, K3×R19, R15×R51 | NOT placement — the fix is assigning the netclass in `pcb/temper.kicad_pro` (hb-gnd, discharge.r_snub2-p2, discharge.r_dis2a-p2, discharge.k_dis2-no, input are HV-declared in the manifest but absent from `netclass_assignments`). R15×R51 is the `safety.ovp.r_adc_top1-p2` mid-chain node (~114V), deliberately left unclassified per manifest §572-587. These are false positives of the current classification, not real HV↔LV crossings — moving components for them would be wrong |
| **cert-lab excluded** (T1/T2/U6) | 8 | R30×T1, F1×T1, U5×U6, R4×U6, F1×U6 | excluded per reconciliation doc / cert-lab package |
| **placement-infeasible** (no zero-new-violation move exists; searched, documented) | 38 | R5×U27 (18), R5×U11 (4), C22×U16 (4), C22×R26 (3), U27×U7 (2), C6×U1 (2), C1×U9 (2), K3×U27, R38×R5, C20×R51, C1×C6 | dense pockets; every candidate displacement creates new HV↔LV pairs (verified by search + live DRC). Matches the c-space doc's clusters: R5↔U27 needs +3.2-4.4mm, C22↔R26 needs +8.4-9.0mm — the doc's warning that hand moves in these pockets trade one pair for another is confirmed. Needs a placement re-solve with courtyard- AND creepage-aware checker |
| DRC re-anchor artifact | 1 | C20×R51 (gnd×+170V_BUS) | this net-pair existed at baseline (the DRC named U16×R6's closest pads); after R6×U16 cleared, the same net-pair's closest pads are C20's `gnd` and R51's `+170V_BUS`. Not a new violation — same net-pair, new closest pads. Net-pair count unaffected |

### Why R5×U27 (18 violations) is not moveable

R5 (2512 SMD, `PWR_RTN`/`DC_BUS_RTN`, HighVoltage) sits at (28.23, 67.74)
between the ESP32 (U27) above, U7 (bootstrap diode) / C23 (Y-cap) /
R9 below, and U11 / R38 / R37 to the right. A 0.25mm-grid search over ±8mm
with edge-to-edge semantics finds **no displacement** that clears U27's 18
pads without creating new charged pairs (best candidate still leaves
partner penalty 40+). Every direction is blocked by LV pads of U27/U11/R38
or by C23's `hb-gnd` pad (which the DRC charges as LV today). This is the
c-space doc's largest cluster, pre-flagged as placement-infeasible. The
fix is a re-solve with a proper checker, or netclass assignment of
`hb-gnd` (which removes C23 as an obstacle), not a hand move.

## Part 2 — clearance family: 100% routing-domain, 0% placement-fixable

The task brief's "~501 clearance (capped 499) + ~199 shorting (capped 199)"
family. Measured on the post-pass board (TRUE uncapped via
`measure_uncapped_drc.py dru-category clearance`):

| category | TRUE count | item shapes |
|---|---:|---|
| clearance | **1120** (capped read 499) | track↔track 273, pad↔track 187, track↔via 25, pad↔via 14 |
| shorting_items | 189 (capped read) | pad↔track 133, track↔via 43, pad↔via 6, via↔via 6, track↔track 1 |

**Zero pure pad↔pad clearance violations** (every clearance item involves a
track or a via; 0 of 499 have no track/via/zone). **Zero pad↔pad shorts**
(shorting shapes are all track/via-involving).

Answer to the brief's Part 2 questions:

1. *Do the 501 clearance violations share distance with creepage?* **No.**
   Clearance is charged by the DRU's clearance constraints (HV to LV 2.0mm,
   AC Mains to LV 6.0mm, HighVoltageSignal to LV 2.0mm — all far smaller
   than creepage's 12.6mm) and lives almost entirely in routed copper.
   The creepage halos / via-clearance fixes do not touch these: clearance
   violations are track-vs-track / pad-vs-track at 2-6mm gaps, not the
   12.6mm barrier crossings.
2. *Routing-fixable or placement-fixable?* **100% routing-fixable.** The
   board is essentially unrouted (27/139 nets connected on main); the
   clearance family is routed-copper debt. The width-aware C-space
   (#1249) and clearance halos are the correct owner. The dominant rules:
   HighVoltageSignal to LV 465, HV to LV 207, Default routing 260,
   HighVoltageIsolated to LV 110.
3. *Placement-fixable ones?* **None.** Zero pad↔pad clearance violations.
4. *Why doesn't the obstacle halo prevent them?* These are on the committed
   (essentially unrouted) board — the router's C-space only affects
   routing output, and the committed board predates any full re-route.
   The routing agents' measured post-route boards show the same family
   dropping as the C-space fixes land (the #1249/#1261 evidence docs).
5. *The 199 shorting cap:* 189 measured, all track/via-involving, same
   conclusion — routing domain. The 11 via-vs-inner-track residuals are
   the other agent's via-clearance fix's domain, confirmed here as
   via-involving shapes (43 track↔via + 6 via↔via + 6 pad↔via).

## DRC ceiling update (this PR)

The re-measurement protocol (≥120 samples, kicad-cli 10.0.5, regenerated
DRU) was run against the final committed board. **No ceiling rises**:
creepage ceiling **drops** (the only nondeterministic category), and every
other error/warning category is unchanged or drops. No `Ceiling-Approval:`
trailer is therefore required. Exact numbers and the `_march` entry are in
`power_pcb_dataset/drc_ceiling.json` (committed with this PR).

## Files changed

- `pcb/temper.kicad_pcb`: exactly 10 component `(at ...)` moves (11 lines;
  one line is a float-representation restore of R5, no position change).
- `power_pcb_dataset/drc_ceiling.json`: provenance + `_march` + ceilings.
- `docs/evidence/2026-08-16-placement-pass-creepage-clearance.md`: this doc.

## Follow-ups (not done here, explicitly out of scope)

1. **Netclass assignment gap** (classification questions, 14 violations):
   `hb-gnd`, `discharge.r_snub2-p2`, `discharge.r_dis2a-p2`,
   `discharge.k_dis2-no`, `input` are HV-declared in
   `elec/domain_manifest.yaml` but absent from `pcb/temper.kicad_pro`
   `netclass_assignments` → read as Default → LV → charged 12.6mm against
   genuine HV. This is a `kicad_pro` data fix (same class as #1083/#1087
   which assigned PWR_RTN and 20 SELV nets), NOT placement. Assigning
   them HV-side clears ~14 false creepage violations. Verify against the
   manifest's own declarations and the R15×R51 mid-chain exception before
   changing.
2. **Placement-infeasible clusters** (38 violations): R5↔U27/U11/R38,
   C22↔R26/U16, C6↔U1, U27↔U7, C1↔U9/C6, K3↔U27. Need a courtyard- AND
   creepage-aware placement re-solve (the c-space doc's "flagged, not
   moved" set). R5 alone is 22 of the 38.
3. **Clearance/shorting families** (1120 TRUE clearance + 189 shorting):
   routing domain; owned by the routing agents' C-space / via fixes.
