# Triage of the independent pre-fab review (REVIEW-2026-10-08.md)

Each BLOCKER and MAJOR was verified against the board before acting. Status: **fixed** (evidence
named), **decision** (recorded in DECISIONS.md), **owner** (needs the owner or the enclosure design),
**open**.

| Id | Finding | Verified | Status / action |
| --- | --- | --- | --- |
| B1 | UCC21550 VDD decoupling not local | Yes. High-side VDDA–VSSA: no capacitor in the source at all (BiasReservoir's `p` is unused); nearest 48–53 mm. Low-side c_ls / c_ls_bulk exist but sat 14–16 mm away | **Stage 8:** source adds c_hs 100 nF + c_hs_bulk 10 µF per leg (C10/C11, C17/C18); caps placed beside the pins (HS 100 nF 4.3 mm, 10 µF 7.9–8.6 mm from VDDA; was 48–53; LS 100 nF at VDDB, the LS 10 µF keeps its block spot ~16 mm away, DECISIONS.md). **Fixed** on board `d4468ffd` |
| B2 | No thermal vias in TPS7A4700 / SN6507 exposed pads | Yes: 0 vias in U26/U27/U28 pads, 1 in U35 | **Fixed:** 3 × 3 filled vias per TPS7A4700 pad, 2 × 2 in U35 (`layout/patches21.py` EP_VIAS). B3: U26's pad cell 176 → 162 °C (task 04 README, stage 8) |
| M1 | AMC1311 / ISO7710 supply decoupling not local | Yes, but the caps exist (c_vs1/2, c_iso1/2, civcc1/2); the block packs put them 12–47 mm away | **Fixed:** placed beside each supply pin, on the pin's side of the barrier (D5 PASS, barrier gates 0) |
| M2 | Long gate loops, return through the switch-node pour | Yes (geometry) | **Covered:** the FEM gate ports run from the driver pins (P3 U.15→U.14, P4 U.10→U.9), so this copper is in the extracted gate loops; F6 passes 252/252 on both legs (FINDINGS M11). Bring-up D4 condition 3 measures the ringing |
| M3 | No thermal relief on THT pads in 2 oz planes; REDCUBE studs are reflow-only (THR) | Yes | **Fixed:** 0.5 mm × 4 spokes on 30 low-current THT pads (`layout/pad_reliefs21.py`, now a hard build step); power pins solid. THR process in FAB-NOTE |
| M4 | Copper under nylon fixings; only screws specified; NYLON not on silk | Yes | **Fixed:** 7 holes re-planned, washer face copper-free on F and B; H2–H7 nylon (silk + F.Fab), H4–H6 need ≥ 10 mm nylon standoffs (HOT copper near the wall; D5-AUDIT). Two new holes at the SELV tongue's corners |
| M5 | 8.0 mm barrier has no tolerance margin (minimum 8.047 mm) | Yes | **Decision:** 8.0 mm is the owner-approved provisional floor (D5-BASIS); etch undercut widens copper gaps; the certification lab sets the final distance. Not re-routed |
| M6 | Coil studs J2/J5 at 15 mm against ASSEMBLY.md's 30 mm target (~540 V peak) | Yes | **Decision (owner, 2026-10-08):** J2/J5 stay at 15 mm, with insulated M4 ring lugs. The 30 mm target is withdrawn (`owner-items/m6m10/`) |
| M7 | J3 TCO loop pins 1.26 mm apart | Yes | **Stage 8:** JST B2P3-VH(LF)(SN), VH with post 2 omitted: 7.92 mm pitch, 5.22 mm copper gap, 250 V 10 A; unshrouded (shrouded doesn't fit); hand-soldered (`sourcing/F1-J3-PARTS.md`) |
| M8 | F1 clips missing from the BOM and under-rated | Yes | **Stage 8:** 2 × Littelfuse 01220088Z (30 A) on the 34.21 × 7.62 mm pattern; own BOM line (`scripts/apply_lcsc.py`). The fuse was undersized as well (≈ 14.5 A continuous after Littelfuse's 25 % derating): now Eaton MDA-25-R, 25 A, 10 kA @ 125 Vac (Eaton TD 2002, owner-read) |
| M9 | CPL uses footprint origins; T1 has no mount type | Yes | **Fixed:** pad-centre centroids, mount type from pads (`scripts/bom_cpl_jlc.py`); rotations checked in JLC's preview (now meaningful) |
| M10 | Outline is 290 × 190 (L) against D-36's 290 × 140; J4 on the front of the tongue | Yes; the tongue appeared during routing without a recorded decision | **Decision (owner, 2026-10-08):** L outline recorded, with J4 on the tongue (R4 fit 417 / 0 hits; J4 lead 74 mm, SELV side) |
| M11 | Tabs 1.8–2.3 mm inside the edge; HOT↔PE at the heatsink not evaluated | Yes, and worse: as modelled in R25 the sink sat on the board edge, 0.6 mm from HOT copper | **Decision (owner, 2026-10-08):** sink set back 8 mm with an Al spreader bar, 2 mm AlN tiles (reinforced), comb-spring clamp through FR-4 (`owner-items/m11/`). No board change |
| M12 | No board ID, HV warning, PE mark or BR1 silk; assembly drawing not in the package | Yes | **Fixed:** board ID, HV warning, nylon legend, PE at J6, BR1 outline and pin marks on silk; `fab/assembly-drawing.pdf` |
| M13 | Not orderable as defined (stock) | Yes | Covered by PROTOTYPE-LOT.md buy plan |
| M14 | PE / Y-cap net long and thin; R38 not near J6 | Yes (R38 at (25.4, 132.9), J6 at (150.6, 134.5)) | **Decision:** the J6 branch is functional only (D5-BASIS: cord PE bonds to the chassis directly; R38 is the single functional bond), so its current is Y-cap leakage; thin track is adequate. R38 placement deviates from "near J6": recorded for the owner |

MINOR items closed in stage 8:
- **m2:** counted on the stage-8 board: 77 drills fully in pads and 64 overlapping. FAB-NOTE says all 770 POFV, no exceptions.
- **m7:** ENIG; thickness 1.6–1.76 mm; CTI as a hard order condition; order number removed.
- **m8:** FLOORPLAN outline; one H1 figure set (centre / hole edge / washer edge); FAB-JLCPCB track rule; ASSEMBLY's supplies.
- **m10:** T1 gets the SMD attribute.
- **m14:** JLC's 2 oz rule is 0.15/0.15 and the tightest gap is 0.20.

New in stage 8, not from the review:
- **F1 was undersized.** It's now Eaton MDA-25-R (25 A, 10 kA @ 125 Vac). Open: the fault-current bound above 125 Vac (1.5 kA) and Recognized-component acceptance.
- The thermal-relief step had been failing silently.

**Gates on stage 8** (`d4468ffd`):
- DRC 0 errors / 0 unconnected / parity 0;
- barrier21 and the Rust gate 0;
- DFM PASS;
- Gerber review 892/892;
- D5 PASS;
- Kelvin band 47.52–97.98 A;
- body collisions 0; R4 fit 0 hits;
- task 04 tank paths unchanged;
- source verify PASS; audit 74/74.

## Closure review of stage 8 (`REVIEW-STAGE8.md` in this folder) and stage 9

Board `d4468ffd` was re-reviewed independently. It confirmed B2, M7, M9 and M12 closed, and M3 and M8 closed with release gates. It found B1 partial and a new MAJOR, N1. Stage 9 (board `e9d1cc4f`, DECISIONS.md 2026-10-08 "stage 9") answers:

| Id | Status after stage 9 |
| --- | --- |
| B1 | **Fixed.** 0805 stacks (100 nF + 1 µF, + 10 µF high side) straddle each output pin. Every VDD–VSS loop is 2.07–2.2 mm with no vias, on all four channels, measured with the reviewer's `path.py` |
| N1 | **Fixed.** The sw_a link from Q2's source to C50 is 24.1 mm, identical to stage 7. Gate loops: +2 nH on every gate diagonal still passes F6 252/252 per leg (`round17/d2/compose_stage9_bound.py`) |
| M1 | **Fixed, with a placement compromise (stage 10).** TI SBAS786C §10 confirms 100 nF ∥ 1 µF on each supply. C149 (VDD1) and C150 (VDD2), 1 µF 0805, are added. VDD2's sits 4.9 mm from its pin. VDD1's is 13.8 mm by copper through 2 vias (no closer free spot on U4's HOT side); C28's 100 nF stays the HF cap |
| M2 | Unchanged from the FEM record; the gate loops are bounded as above |
| M4 | **Requirement stated.** The whole fixing chain at H2–H7 is insulating (BRINGUP-PROBES.md, FAB-NOTE). Holes are frozen at the positions the enclosure adopted |
| N2 | **Fixed.** The legend reads H2–H7 |
| N3 | **Fixed.** Dead leg_ret stub removed; 9 dangling-track warnings remain, all ≤ 3 mm |
| N5 | **Fixed.** The board and position file now carry MDA-25-R |
| N6 | **Fixed.** `d5_audit.py` built zones without their cut-outs and measured from the drill's square box. With the zone holes and the round drill it reports H4 1.20 / H5 7.92 mm, the reviewer's figures. Barrier minima unchanged |

## Re-review of stage 10 (`REVIEW-STAGE10.md`) and stage 11

The independent reviewer re-measured board `ef993141` against stages 7 and 8.
- **No new BLOCKER or MAJOR.**
- B1, N1, N3 and N5 are **closed**, and M4 is closed with a residual hardware-error risk.
- The +2 nH gate-loop bound is **sound**: the neck rise is 0.53–0.92 nH by the reviewer's own estimate.
- **Reviewer correction:** the y = 40 leg_ret In1 run is live; only its duplicate segment was dead. Stage 9 removed just that.

Minor items, answered in stage 11:

| Id | Finding | Stage 11 |
| --- | --- | --- |
| M1 / S10-1 | Moving C29 lengthened the AMC1311 VDD2 100 nF loop from 1.8 to 3.85 mm. C149's 1 µF loop is long (~27 mm, 4 vias) | Placement order fixed: the 100 nF goes first and is back at the pin. C149 stays a recorded compromise (no closer free spot on U4's HOT side) |
| N2 | NYLON per hole only on F.Fab; board-ID text breaks silk-to-edge; hole designators overlap their washer rings | Hole and fiducial designators on F.Fab (the rings and the H2–H7 legend mark the holes on silk); text placement uses the real stroke-font width and a 1.5 mm edge margin |
| S10-2 | BRINGUP-PROBES.md stale against the stage-10 plan | Regenerated after the re-plan |
| S10-3 | 0.3 mm output necks run under the 0805 bodies (0.30 mm to the pads) | First-article inspection item: check for solder bridges under C10/C145/C11, C8/C146, C17/C147/C18, C15/C148 |
