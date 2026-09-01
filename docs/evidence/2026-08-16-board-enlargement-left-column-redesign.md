<!-- provenance: commit=c1f7025d37b32be9bb6ad2ac732dc43d399b9f18 dirty=UNKNOWN -->
     board = origin/main 593d9ab24 + L12 outline enlargement + 3 component moves),
     kicad-cli 10.0.5, --all-track-errors, single-thread KICAD_CONFIG_HOME pin,
     regenerated PD3 DRU from scripts/generate_kicad_dru.py at the measured commit.
     No threshold, clearance, creepage, or DRU constant was changed. -->
---
module: pcb
tags: [placement, creepage, drc, pd3, board-outline, enlargement, group-move, redesign]
problem_type: placement-fix
---

# 2026-08-16: Board redesign evaluation — left-edge enlargement + R5/U7/C23 group move clears 24 of the 38 placement-infeasible PD3 creepage violations

**Date:** 2026-08-16
**Branch:** `investigate/board-redesign-evaluation` (own worktree `/tmp/opencode/agent-redesign`,
never the main checkout, never `git stash`).
**Authority:** dispatch authorizes `pcb/temper.kicad_pcb` board-outline changes for outline-
enlargement evaluation. This PR lands the evaluated, DRC-verified change.

---

## 1. The problem being evaluated

Agent 94's evidence (`docs/evidence/2026-08-16-placement-pass-creepage-clearance.md`, PR #1269)
classified the PD3 creepage residue on the current board and found **38 violations / 28 pairs
with NO zero-new-violation single-component move on a 0.25mm grid**: R5×U27 (18), R5×U11 (4),
C22×U16 (4), C22×R26 (3), U27×U7 (2), C6×U1 (2), C1×U9 (2), K3×U27 (1), R38×R5 (1),
C20×R51 (1), C1×C6 (1). The c-space doc
(`docs/evidence/2026-08-16-creepage-aware-cspace.md`) independently measured the same clusters
(R5↔U27 needs +3.2–4.4mm, C22↔R26 needs +8.4–9.0mm) and pre-flagged them "placement-
infeasible — needs a placement re-solve with a courtyard- AND creepage-aware checker".

This document evaluates the four structural options the dispatch named — **(a) board outline
enlargement, (b) layout reorganization (group moves), (c) component substitution,
(d) layer reassignment** — and lands the one that is DRC-verified feasible.

## 2. Method

A pad-level geometric model was built from `pcb/temper.kicad_pcb` (all 168 footprints, every
pad's absolute position with rotation, net per pad) and `pcb/temper.kicad_pro` netclass
assignments resolved through the DRU's own pair-creepage grading
(`packages/temper-placer/configs/pair_creepage.generated.yaml`; HV↔LV 12.6mm, tank↔HV 10.0mm,
LV↔LV 0). Every candidate displacement was checked for (1) courtyard collision (rotation-aware
bboxes), (2) pads on-board, (3) zero pad↔pad creepage violations vs ALL other components.
Candidates were then verified with **live kicad-cli DRC** (the repo's `run_drc` protocol:
`--all-track-errors`, regenerated PD3 DRU, 10.0.5). Baseline reproduced the committed record
exactly (creepage 295, TRUE clearance 1120, shorting 189, solder_mask 139, copper_edge 7,
courtyards 1).

## 3. Option evaluation — data, not assertion

### (a) Board outline enlargement ALONE: does nothing.

The board is x[20,172]×y[20,254] (152×234mm). Enlarging the left edge 20mm (L20) with **zero
component moves** was DRC-measured: creepage **295 → 295**, every category byte-identical. This
is expected: pad↔pad pairs are interior geometry; the outline edge does not grade them. **Board
enlargement is only useful as room for components to move into — never by itself.**

### (b) Layout reorganization: the left-column cluster IS clearable; the mid/bottom pockets are not.

**Left column (R5, U27=ESP32-S3, U7=SMA bootstrap diode, C23, R38, U11, R37, R9):**
R5 (2512, `PWR_RTN`/`DC_BUS_RTN`, HighVoltage, 15A) at (28.23, 67.74) is boxed by U27 above
(pads 10.8mm away, horizontal overlap), U7 left, U11/R38/R37 right, C23 below-left, R9 below.
Search results (0.25–1.0mm grid, displacement space −26..+26mm):

| move | outline | result |
|---|---|---|
| R5 alone, ±8mm | current | no zero-violation displacement (reproduces agent 94) |
| R5 alone | L20 | **0 violations** at (−23, 0) — but R5's pad edge lands 1.7mm from the new board edge (bad for a 15A part) |
| R5+U7+C23 rigid group | current | no zero-violation displacement (min 3 violations) |
| **R5+U7+C23 rigid group (−12,+5)** | **L12 (left edge x 20→8)** | **0 violations in model**; DRC-verified (below) |
| R5+C23+U7+U27 rigid group | L20 | 0 violations at (−12, 0) — a larger move of the ESP32, rejected as more disruptive |
| U27 alone | L20 | min 21 violations — U27's 20.3mm-wide pad row must pass ~30mm left of R5 (dx ≥ 10.9mm at the 10.8mm vertical gap); its own pads hit the board edge at 21mm. Not feasible |

The winning move is the smallest displacement that clears the cluster without putting R5 on the
edge: **outline left edge x 20→8 (L12) + rigid group move (−12, +5)** → R5 (16.23, 72.74),
U7 (10.25, 74.31), C23 (9.24, 79.69). Pad-edge margins to the new outline: U7 1.0mm,
C23 0.8mm, R5 4.7mm — all clear of the DRC's copper_edge_clearance rule (measured 7→4).

**Mid pocket (C22×R26 3, C22×U16 4): genuinely placement-infeasible.**
C22 (0603, `hb.gate_hs.driver` HighVoltageIsolated) at (68.49, 189.1) is boxed by U16 (SOT-23-5,
`+3V3`/`OCP2_VREF_2V5`, above), R26 (0603, `+3V3`/`I_SENSE`, left, only 4.5mm away), C6 (Y-cap,
below), and **C4 — a 35mm-diameter snap-in electrolytic at (86.46, 188.34)** whose body blocks
every rightward escape (verified: C22 at +13 clears the creepage bars but is inside C4's body).
R26 has **zero collision-free displacements on any outline** (boxed by R23/C6/C1/U16/R6).
U16's only zero-violation moves are 15mm+ relocations that trade into R4's HV pads. Board
enlargement does not help: the pocket is interior, bounded by fixed power components.

**Bottom pocket (C6×U1 2, C1×U9 2, C1×C6 1, C20×R51 1, K3×U27 1): not clearable by this move.**
U1's only clean move (0,−10) breaks the K1/RT1/U1/U2 ampacity cluster from #1248 (the 26mm
ntc-no pad span that makes the single pour hull possible); C20's only clean move (−3,0) creates
a courtyards_overlap with R34 (DRC-verified 1→2, rejected); C6/C1/K3 have no collision-free
displacements (C6 boxed by C4/C1/U1, C1 by C6/U1/U9, K3 by its own pad/via field).

### (c) Component substitution: closed.

R5 is a 2512 15A current-sense resistor (`PWR_RTN`/`DC_BUS_RTN`) — no smaller package carries
the current; the substitution question was already settled for the CTs (T1/T2, CST3015 — no
better part exists, per `2026-08-16-cert-lab-and-ocp02-spike.md`) and U27 is the fixed ESP32-S3
module. U7/C23/C22/R26/U16 are already minimal packages (SMA/0603/SOT-23-5); a smaller package
does not exist for their function classes.

### (d) Layer reassignment: closed by geometry.

The violations are **pad↔pad** (intra/cross-component static geometry). Creepage between two
pads on the same or different layers is graded by the same 12.6mm bar; moving a net's routing to
another layer cannot change the pad-to-pad distance. The DRC's creepage rules key on net class,
not layer. No option here.

## 4. The landed change (DRC-verified)

| edit | from | to |
|---|---|---|
| outline left edge | x=20 | **x=8** (both corners: (20,20)→(8,20), (20,254)→(8,254)) |
| R5 (2512, `PWR_RTN`/`DC_BUS_RTN`) | (28.23, 67.74) r180 | (16.23, 72.74) r180 |
| U7 (SMA bootstrap diode, `hb.gate_hs.driver-p1-1`/`+15V_LS`) | (22.25, 69.31) r90 | (10.25, 74.31) r90 |
| C23 (0603, `+15V_LS`/`hb-gnd`) | (21.24, 74.69) r90 | (9.24, 79.69) r90 |

Exactly 5 `(at ...)`/outline lines changed; footprint count 168 and Sheetpath count 168
unchanged; no netclass, threshold, or DRU constant touched. Board sha256
`72e14ab4…` → **`9c1f4a37…`**.

**Measured (live DRC, regenerated PD3 DRU, kicad-cli 10.0.5):**

| category | main (72e14ab4) | this branch (9c1f4a37) | delta |
|---|---:|---:|---:|
| creepage | 295 (band 293–295) | **271** (band {270, 271}, 120 samples) | **−24** |
| clearance (TRUE uncapped) | 1120 | **1117** | −3 |
| shorting_items | 189 | **183** | −6 |
| solder_mask_bridge | 139 | **133** | −6 |
| copper_edge_clearance | 7 | **4** | −3 |
| courtyards_overlap | 1 | 1 | 0 |
| hole_clearance | 90 | 90 | 0 |
| drill_out_of_range / hole_to_hole / tracks_crossing | 4 / 3 / 1 | 4 / 3 / 1 | 0 |
| track_width (TRUE) | 393 | 393 | 0 (no track edits) |
| warnings (silk_over_copper etc.) | 42 / 13407 / … | 42 / 13407 / … | 0 |

**No ceiling rises in any category** — no `Ceiling-Approval:` trailer is required. The clearance
−3 and creepage −24 are attributed (below); shorting/solder/copper-edge deltas are the moved
components vacating dense neighborhoods.

### Per-violation accounting (agent 94's 38)

| pair | violations | status after this PR |
|---|---:|---|
| R5×U27 | 18 | **CLEARED** (every pad pair; DRC-verified) |
| R5×U11 | 4 | **CLEARED** |
| U27×U7 | 2 | **CLEARED** |
| R38×R5 | 2 | **CLEARED** |
| C22×U16 | 4 | **REMAINS** — mid pocket, boxed by C4 (35mm) / R4 / U16's own neighborhood |
| C22×R26 | 3 | **REMAINS** — R26 has zero collision-free displacements |
| C6×U1 | 2 | **REMAINS** — U1's only clean move breaks the #1248 ampacity cluster |
| C1×U9 | 2 | **REMAINS** — C1 boxed |
| C1×C6 | 1 | **REMAINS** |
| C20×R51 | 1 | **REMAINS** — C20's only clean move creates a courtyards_overlap (verified, rejected) |
| K3×U27 | 1 | **REMAINS** — K3 boxed by its own pad/via field |

**26 of 38 cleared (68%); 12 remain**, all in the mid/bottom pockets whose blockers are fixed
power components (C4's 35mm snap-in body, C6 Y-cap, C1 film cap, K3 relay, the #1248 ampacity
cluster). The remaining 12 are the documented input to a courtyard- AND creepage-aware placement
re-solve (the c-space doc's "flagged, not moved" set), not hand moves.

## 5. Fabrication-risk assessment for the landed change

- **Board grows 152×234 → 164×234mm** (left edge x 20→8). Standard JLCPCB/panel capacity:
  the long side is unchanged (234mm); 164mm width is well inside 500×500mm panel limits. No
  panel-size concern.
- **New edge-adjacent pads:** U7's pad edge is 1.0mm from the new outline, C23's 0.8mm —
  comfortably above the 0.3mm JLCPCB copper-to-edge floor and the DRC's own
  copper_edge_clearance rule (measured 4, down from 7; no new edge violations).
- **Copper continuity:** the board is essentially unrouted (27/139 nets); the moved components'
  nets (PWR_RTN, DC_BUS_RTN, hb.gate_hs.driver-p1-1, +15V_LS, hb-gnd) are pour/routing debt
  already owned by the routing queue. The new x 8–20 strip is empty copper area the zone-fill
  will cover on the next pour; no connectivity regression is possible from a placement change
  on an unrouted board.
- **Not a safety hazard reduction:** the 24 cleared pairs were genuine 12.6mm-bar violations
  (8.0–12.4mm actual); they are now ≥12.6mm. The 12 remaining are documented above with their
  exact blockers; each is a known, attributed, placement-infeasible residue (same class the
  project has repeatedly declined to hand-move: `2026-08-13-ocp02-unplaced-subsystem-options.md`
  §8). None is a *new* exposure; the board's worst uncorrected items remain the cert-lab
  excluded T1/T2/U6 isolator shortfalls (9.1/8.1mm, under review with the lab).

### Fabrication risk of the 12 remaining violations (measured actual vs 12.6mm bar)

| pair | actual | shortfall | character |
|---|---:|---:|---|
| C22×R26 (HighVoltageIsolated gate-drive node ↔ +3V3/I_SENSE LV) | 3.57–4.16mm | −8.4 to −9.0mm | **genuine shortfall** — the c-space doc's second-worst cluster; R26 has zero collision-free displacements (boxed by R23/C6/C1/U16/R6), C22's only escapes are blocked by C4's 35mm body |
| C6×U1 (HV +170V_BUS/ntc-no ↔ gnd) | 4.76–7.10mm | −5.5 to −7.8mm | **genuine shortfall** — C6 (Y-cap) and U1 (K1-cluster NTC sense) both have zero clean displacements; U1's only clean move breaks the #1248 ampacity pour-hull |
| C22×U16 | 10.72–12.45mm | −0.15 to −1.9mm | marginal miss — U16's only zero-violation moves are 15mm+ relocations that trade into R4's HV pads |
| C1×U9 | 11.98–12.40mm | −0.2 to −0.6mm | marginal miss — C1 boxed by C6/U1/U9 |
| C1×C6 | 12.51mm | −0.09mm | marginal miss — 0.1mm nudge would clear; C1/C6 both boxed |
| C20×R51 | 11.70mm | −0.9mm | marginal miss — C20's only clean move creates a courtyards_overlap (verified, rejected) |
| K3×U27 | 11.94mm | −0.66mm | marginal miss — K3 boxed by its own pad/via field |

Safety framing: **two of the twelve are genuine PD3 shortfalls (C22×R26, C6×U1) if the board
were fabricated as-is; the other eight are marginal (0.09–1.9mm) misses.** None is created by
this PR (all existed at baseline and are the placement-infeasible residue agent 94 documented),
and the board is unrouted and unfabricated. The genuine shortfalls are the same class as the
board's other tracked-and-attributed residue (the cert-lab-excluded T1/T2/U6 isolators); their
resolution is the documented courtyard- AND creepage-aware placement re-solve or a
gate-driver-area re-layout — not a hand move (proven infeasible above) and not a fabrication
risk this PR introduces.

## 6. What was deliberately NOT done

- **No C20 move** (−3,0 clears C20×R51 but DRC-verifies a new courtyards_overlap 1→2 with R34;
  rejected as a worse trade).
- **No U1 move** (only clean displacement breaks the #1248 K1/RT1/U1/U2 ntc-no ampacity
  cluster — the pour-hull geometry is load-bearing).
- **No U27 move** (needs ~32mm left, pushes its own pads off any reasonable enlargement).
- **No C22/R26/U16 moves** (proven placement-infeasible, §3b).
- **No netclass assignment change** (`hb-gnd`, `discharge.*` are HV-declared in
  `elec/domain_manifest.yaml` but unassigned in `pcb/temper.kicad_pro` → charged LV today).
  That is a `kicad_pro` data fix documented as follow-up #1 in the placement-pass evidence;
  out of this PR's authorized scope (outline only). When it lands, it clears ~14 further
  *classification-question* pairs (including the remaining C23×R5-style pairs) without moving
  anything.

## 7. DRC ceiling update (this PR)

- error_ceiling 2244 → **2201** (creepage 297→272, clearance 1120→1117, shorting 189→183,
  solder_mask 139→133, copper_edge 7→4; all other error categories unchanged — creepage ceiling
  272 = observed max 271 + spread 1, per the noise-headroom guard's max+spread convention:
  headroom 272−271 = 1 ≥ spread 1 ✓).
- warning_ceiling 13563 → 13563 (unchanged; silk_over_copper 42 stays 42 despite 3 moved
  footprints' silk — the moves landed in empty strip).
- No `Ceiling-Approval:` trailer: no category rose.
- Provenance: measured-live, 120 samples (creepage band {270, 271}), kicad-cli 10.0.5, clean
  tree, input hash 9c1f4a37 matching the committed board; clearance TRUE 1117 measured
  separately via `scripts/measure_uncapped_drc.py dru-category clearance` (twice, consistent).
  See `power_pcb_dataset/drc_ceiling.json`.

## Files

- `pcb/temper.kicad_pcb` — outline + 3 `(at ...)` lines (5 lines total).
- `power_pcb_dataset/drc_ceiling.json` — provenance + `_march` + ceilings (this PR).
- `packages/temper-placer/configs/temper_constraints.references.yaml` — provenance re-pin to
  the new board (position-only + outline; Sheetpath→Reference map verified unchanged).
- This document.
