# Fabrication note: power-stage-120v native-21 (CANDIDATE, not released)

Board: native-21 stage 15b (stage 14 plus the 28 A tank hardware: R34 12.6 k, R43/R46 2.21 k and SW_A / SW_B copper widening, DECISIONS.md 2026-10-10 items 13-14; stage 14 added one RECOM R24C2T25/R-R isolated bias module per high side, U41/U42, the 9 µF C5/C6 bus film and the 2 × 30KPA150CA series bus clamp D3/D17, DECISIONS.md 2026-10-09 stage 14; stage 13b added the BOM simplification, the 5 × TDK B32654 resonant bank and the C1/C2 X2 swap; stage 12 carried the independent-review fixes, `../REVIEW-TRIAGE.md`), rebuilt from
`native-21/layout/copper.json` by `sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR`;
SHA-256
`9a9c43c63f63d383c89b9dc1d4d03a34d4390cfa1c26bbe802d71e169c6ddf94`.
Gerbers: `native-21-gerbers.zip`, SHA-256
`c7d1354598cf1a75e03e6faa8c7e08f87273718a092660751fde3a6f0225d6b7`.

**This package isn't released for ordering.** The gates come in two tiers (decision 2026-10-08; PROTOTYPE-LOT.md agrees).

**Before ordering the bench prototype lot** (run on an isolated, current-limited supply):
- the native-21 FEM correction matrices (leg A/B `a21corr` / `b21corr`) land and F6 re-runs on them. A failure would mean a copper change;
- M11 (heatsink HOT↔PE stack) is approved (DECISIONS.md 2026-10-08). Its parts still need sourcing: AlN tiles (quote), non-conductive compound, gap pad, spreader bar, comb spring, FR-4 strip (`../owner-items/m11/`);
- procurement of the no-stock parts in `../owner-items/order/ORDER-PACKAGE.md`, incl. UCC21550, ISO7710, T1, the RECOM R24C2T25/R-R bias modules U41/U42, the 30KPA150CA clamp pair D3/D17, C5/C6 and the 5 × TDK B32654A1104K000 resonant caps.

**Before mains-connected or unattended operation, and before product release:**
- insulation and thermal qualification (PD3, IEC 60664-4, hipot, partial discharge);
- the laminate CTI written confirmation (`../sourcing/inquiries/CTI-JLC.md`; send it with the order);
- F1 (Littelfuse KLDR025.TXP, UL Class CC, 600 Vac / 200 kA): the open-clip (01250003H) acceptance and the clip's voltage rating and agency file (`../owner-items/f1cc/`). The nameplate is 120–127 V~ 60 Hz, and there is no inlet fuse (DECISIONS.md 2026-10-09);
- the certification lab's answer on the tank-voltage RMS convention (M6 reversal condition).

M6, M10 and M11 are decided (DECISIONS.md 2026-10-08).

Ordering is a purchase and needs the owner.

| Item | Requirement |
| --- | --- |
| Size | 290 × 190 mm L-shaped outline, 4 layers |
| Stackup | JLCPCB **JLC041622-7628**, 1.6 mm nominal. **Finished thickness 1.6–1.76 mm** (+10 / −0 %): the REDCUBE THR studs need 1.6–2.0 mm (review m7), and JLC's ±10 % allows 1.44 mm. Ask JLC to confirm; if it can't hold the minimum, re-stack at 1.8 mm |
| Copper | **2 oz outer and 2 oz inner** |
| Laminate | **CTI ≥ 175 V (material group IIIa), a hard order condition.** Don't place the order until JLC confirms it in writing |
| Surface finish | **ENIG**: 0.65 mm SSOP-36 bias modules (U41/U42), 0.65 mm VQFN with exposed pad (U26), capped via-in-pad |
| Solder mask / silk | Green / white |
| Impedance control | None |
| Order number | **Remove** (JLC's "remove order number" option); the silk carries the board ID instead |
| **Via covering** | **Epoxy-filled and capped (POFV) for all 753 × 0.3 mm vias, no exceptions.** 72 sit fully inside SMD pads and 67 more overlap a pad edge (`native-21/verification/via_in_pad.py`), including the R5 shunt current-pad arrays and the exposed-pad thermal fields (U26–U28 3 × 3, U35 2 × 2). The ten 1.6/0.8 current vias stay tented (JLC fills holes ≤ 0.5 mm only). The KiCad file says `filling/capping no`; this note is the requirement. Select "Confirm production files" |
| Drills | 881 plated (763 vias, 118 component holes, 4 of them **plated slots 1.2 × 2.5 mm** for F1's 10 × 38 clips: routed slots, G85 in the PTH drill file), 15 non-plated (8 connector holes, 7 M3 fixings) |
| Board-only parts | 36 bring-up test pads (bare copper), 3 fiducials (1 mm, 3 mm mask opening), 7 M3 holes at the positions the enclosure adopted; none in BOM/CPL. **H2–H7: the whole fixing chain is insulating** (nylon screw, washer and standoff; no metal screw, nut or insert within 10 mm of the board), with outer copper clear under the 7 mm washer. H1 may take metal hardware (native-21/BRINGUP-PROBES.md). Enclosure R30: male-female standoffs threaded into the tapped base (nylon at H2–H7 with a nylon top screw and washer, ≥ 10 mm; brass at H1). H1 is a bare NPTH, so its metal hardware bonds the chassis only; the board's PE comes in at J6 |

JLC rules (`tools/jlc_dfm_check.py`, capabilities page re-read verbatim 2026-10-08):
- PTH annular ring ≥ 0.254 mm at 2 oz.
- Via diameter ≥ hole + 0.1 mm; our floor is a 0.15 mm ring.
- Track/space at 2 oz multilayer: JLC allows 0.15/0.15 mm. Our floor is 0.2/0.2 mm, and the tightest gap is the U41/U42 modules' 0.20 mm pad-to-pad (0.45 mm pads at 0.65 mm pitch).
- Via drill ≥ 0.15 mm.
- Result: **PASS**. 763 vias, 118 plated pads (slot rings checked per axis: 0.60 mm), minimum track 0.2 mm, 0 failures (`../jlc-dfm.json`).

Assembly:
- **LCSC numbers:** 82 of 91 source lines map to a checked LCSC part (49 exact from the survey, 32 changed or added since, most of them the 2026-10-09 Basic swaps and the stage-14 bias parts, 1 accepted substitute; `../sourcing/`, `../bom-simplification/`). Nine are consigned or hand-assembled: F1 fuse, C1/C2 (KEMET R463N410050N1K, Digi-Key), C5/C6 (TDK B32676G1905K000), U1/U2, T1, the resonant bank C21–C23/C151/C152 (TDK B32654A1104K000), J3, D3/D17 (Good-Ark 30KPA150CA, P600 axial) and U41/U42 (RECOM R24C2T25/R-R). Check stock again before ordering.
- **Lead trim (insulation):** trim every THT lead to ≤ 2.5 mm below the board bottom after soldering (ASSEMBLY.md); trim C1/C2's 25 mm leads to 4 mm before insertion.
- **Hand assembly:**
  - F1-CLIP (2 × Littelfuse 01250003H, 10 × 38 / Class CC clips, 30 A), soldered into the plated slots;
  - the F1 cartridge, inserted after cleaning;
  - J3 (JST B2P3-VH, 7.92 mm pitch, unshrouded).
- **First-article inspection (closure review S10-3):** the 0.3 mm driver output necks run under the 0805 VDD–VSS stacks with 0.30 mm to the pads. Inspect for solder bridges under C10/C145/C11, C8/C146, C17/C147/C18 and C15/C148. IR-check U26 (TPS7A4700) at first power-up: its In1 n_ls spreading plane has thinned over stages 8–11 (DECISIONS stage 11).
- **Through-hole reflow:** the REDCUBE studs (J2, J5, J7–J10) are THR parts, soldered by reflow (paste in hole), not wave. Low-current THT pads in the 2 oz pours have 0.5 mm × 4 thermal spokes (review M3). Power pins stay solid: hand rework of them only on a bottom-preheated board (≥ 100 °C).
- Check each CPL rotation in JLCPCB's preview; centroids are pad centres (review M9).
- `assembly-drawing.pdf`: F.Fab (all designators, including the 115 with no clear silk spot (hole and fiducial designators are there by design)), silk and outline, scaled to A4.

Deviations and notes:
- Plated through-hole pads have lands on both outer layers. Unconnected inner rings are removed on purpose.
- Accepted DRC warnings, against 0 errors and 0 unconnected:
  - 11 short dangling stubs (≤ 1.1 mm);
  - 20 silk-over-copper, 1 silk overlap (Q2's designator on the BR1 outline) and 2 silk-to-edge (PS1/PS2 outlines);
  - 199 `lib_footprint_issues`, from the project's unconfigured stock-library table.
