# Fabrication note: power-stage-120v native-21 (CANDIDATE, not released)

Board: native-21 stage 53, the board of record (DECISIONS.md item 75: the S10 ovp_ok_hot In1 run moves to In2, the R43 real-pose fit gate and the 3D-model gate; item 74: the prototype bank C21–C23 / C151 / C152 is TDK
B32643H8104J000 (24 A strict ladder; DigiKey 306 on the 2026-10-16 read), consigned into the 22.5 mm holes; L1 is
B82726S2243A020, consigned / hand-assembled (JLC C7084710 holds 0); C3 / C4 are Murata DE1E3RA222MJ4BH01F. Item 73:
the dual-pitch footprint
`temper:Bank_Film_DualPitch_P22.5_P27.5_Radial` (pad 1 at x 163.0; pad-2 holes at x 185.5 for the TDK B32643H / B32643B parts and x 190.5 for the KNSCHA fallback,
both on sw_b; 1.2 mm drills, 0.6 mm rings); a sourcing override: the H bank caps the commissioned ladder at 24 A
strict (B32643B8104J000, 28 A, fits the same holes later; KNSCHA stops at 22 A); item 71: U46.A (hsb_good) driven from PERMIT
through R135 100 k, so BIAS_GOOD = bias_ok AND PERMIT and TP19 reads low while PERMIT is low; item 70: S23's B′-1.02 V
OCP divider, R33 7.5 k / R34 16 k / R35 11 k, and the bank-area re-cut for a 2000 V bank; item 67: the four TPS70950
ENs on 100 k / 27 k dividers and on the 125 °C TPS70950QDBVRQ1, the REF25 watchdog on U14's second channel, BIAS_GOOD
read back on J4.1 through R146, end-of-line test pads; item 63: U5 (REF25) on the 125 °C LM4050AEM3-2.5/NOPB; item 62:
the rail-monitor ICs on their 125 °C grades; item 60: the S16 rail-monitor values; the stage history is DECISIONS.md
items 12–75). Built by `sh native-21/layout/gates/chain.sh native21s53 …`; SHA-256
`82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27` (the integration build; copper key b7a0bc5790b9; the s52 copper key was 3a4c616e7870). Plated holes 876: the
bank is consigned into the 22.5 mm holes (pad 2 at x 185.5); the five x 190.5 holes are plated and stay open at assembly.
The silk bank-variant fit mark ("BANK FIT, TICK ONE") carries H = B32643H8104J000 24 A MAX and B = B32643B8104J000
28 A: tick H on the prototype boards. U5 is sourced and consigned (JLC stock 50 against 500; owner pre-order,
OPEN-ITEMS owner action 7); U3 / U37–U39 TPS70950QDBVRQ1 (C485909) are JLC Extended, 11,607 in stock.
Gerbers: `native-21-gerbers.zip`, SHA-256
`a6afd37a4f4e0039de8de7fd86755ff65328f21e43501a23d0904e78ffbd4ddc`. Thermal basis: hot-copper B3, tank ceiling 17.5 A
(DECISIONS.md item 61).

**This package isn't released for ordering.** The gates come in two tiers (decision 2026-10-08; PROTOTYPE-LOT.md agrees).

**Before ordering the bench prototype lot** (run on an isolated, current-limited supply):
- the native-21 FEM correction matrices (leg A/B `a21corr` / `b21corr`) land and F6 re-runs on them. A failure would mean a copper change;
- M11 (heatsink HOT↔PE stack) is approved (DECISIONS.md 2026-10-08). Its parts still need sourcing: AlN tiles (quote), non-conductive compound, gap pad, spreader bar, comb spring, FR-4 strip (`../owner-items/m11/`);
- procurement of the no-stock parts in `../owner-items/order/ORDER-PACKAGE.md`, incl. T1, the RECOM R24C2T25/R-R bias modules U41/U42, the 30KPA150CA clamp pair D3/D17, C5/C6. The prototype resonant bank (TDK B32643H8104J000, DigiKey) and L1 (B82726S2243A020, Mouser / DigiKey) are consigned; TDK B32643B8104J000 is ordered only for the 28 A route (DECISIONS.md items 73 and 74, OPEN-ITEMS S28).

**Before mains-connected or unattended operation, and before product release:**
- insulation and thermal qualification (PD3, IEC 60664-4, hipot, partial discharge);
- the laminate CTI: settled from Kingboard / UL records by naming KB-6164 on the order (`../sourcing/inquiries/CTI-RESEARCH-2026-10-14.md`, DECISIONS 41); the certifier accepts PLC 3 as group IIIa (CERTIFIER-PACKET A3);
- F1 (Littelfuse KLDR025.TXP, UL Class CC, 600 Vac / 200 kA): the open-clip (01250003H) acceptance and the clip's voltage rating and agency file (`../owner-items/f1cc/`). The nameplate is 120–127 V~ 60 Hz, and there is no inlet fuse (DECISIONS.md 2026-10-09);
- the certification lab's answer on the tank-voltage RMS convention (M6 reversal condition);
- RES_A (297 V rms at 28 A) is held at 12.6 mm reinforced creepage to SELV/PE on the outer layers (item 18); the lab confirms that same-layer inner paths count as solid insulation (on s51 the closest is C152.1, RES_A at (163.0, 113.2): its In1 / In2 rings are 8.328 mm from the SELV v3v3 plane, unchanged since s49; the s51 x 190.5 holes are sw_b and ≥ 14.8 mm from it, `c51-bank-source/stage51/results/hole-clearance-s51.md`).

M6, M10 and M11 are decided (DECISIONS.md 2026-10-08).

Ordering is a purchase and needs the owner.

| Item | Requirement |
| --- | --- |
| Size | 290 × 190 mm L-shaped outline, 4 layers |
| Stackup | JLCPCB **JLC041622-7628**, 1.6 mm nominal (JLC ±10 %). No part limits the board thickness since the SMT coil terminals (DECISIONS 44, which drops the 1.60–1.76 mm remark of DECISIONS 42) |
| Copper | **2 oz outer and 2 oz inner** |
| Laminate | **CTI ≥ 175 V (material group IIIa), a hard order condition, met by naming the laminate:** Material Type **"KB6164 - TG135"** (Kingboard KB-6164: UL E123995 CTI PLC 3 at 1.40 mm, Kingboard TDS ≥ 175 V per IEC 60112; `../sourcing/inquiries/CTI-RESEARCH-2026-10-14.md`; +$0.28 per board at 500). Never order the unnamed "FR4 TG135". Order remark: "Material KB-6164 core with KB-6064 prepreg throughout; please state the laminate on the shipment documents" |
| Surface finish | **ENIG**: 0.65 mm SSOP-36 bias modules (U41/U42), 0.65 mm VQFN with exposed pad (U26), capped via-in-pad |
| Solder mask / silk | Green / white |
| Impedance control | None |
| Order number | **Remove** (JLC's "remove order number" option); the silk carries the board ID instead |
| **Via covering** | **Epoxy-filled and capped (POFV) for all 750 × 0.3 mm vias (705 × 0.6/0.3, 45 × 0.85/0.3; stage 44), no exceptions.** 60 sit fully inside SMD pads and 75 more overlap a pad edge (`native-21/verification/via_in_pad.py`), including the R5 shunt current-pad arrays and the exposed-pad thermal fields (U26–U28 3 × 3, U35 2 × 2). The ten 1.6/0.8 current vias stay tented (JLC fills holes ≤ 0.5 mm only). Via sizes (stage 32, `via_in_pad.py` census): 691 × 0.6/0.3 and 4 × 0.85/0.3 (the 695 POFV vias), 5 × 0.8/0.5 (R5.4, in or at the pad), 10 × 1.6/0.8 (tented). The KiCad file says `filling/capping no`; this note is the requirement. Select "Confirm production files" |
| Drills | 859 plated (765 vias, 94 component holes, 4 of them **plated slots 1.2 × 2.5 mm** for F1's 10 × 38 clips: routed slots, G85 in the PTH drill file), 14 non-plated (drill report, stage 44: 2 × 1.02, 10 × 3.2, 2 × 5.2 mm) |
| Board-only parts | 39 bring-up test pads (bare copper), 3 fiducials (1 mm, 3 mm mask opening), 7 M3 holes at the positions the enclosure adopted; none in BOM/CPL. **H2–H7: the whole fixing chain is insulating** (nylon screw, washer and standoff; no metal screw, nut or insert within 10 mm of the board), with outer copper clear under the 7 mm washer. H1 may take metal hardware (native-21/BRINGUP-PROBES.md). Enclosure R30: male-female standoffs threaded into the tapped base (nylon at H2–H7 with a nylon top screw and washer, ≥ 10 mm; brass at H1). H1 is a bare NPTH, so its metal hardware bonds the chassis only; the board's PE comes in at J6 |

JLC rules (`tools/jlc_dfm_check.py`, capabilities page re-read verbatim 2026-10-08):
- PTH annular ring ≥ 0.254 mm at 2 oz.
- Via diameter ≥ hole + 0.1 mm; our floor is a 0.15 mm ring.
- Track/space at 2 oz multilayer: JLC allows 0.15/0.15 mm. Our floor is 0.2/0.2 mm, and the tightest gap is the U41/U42 modules' 0.20 mm pad-to-pad (0.45 mm pads at 0.65 mm pitch).
- Via drill ≥ 0.15 mm.
- Result: **PASS**. 765 vias (stage 44), 94 plated pads (slot rings checked per axis: 0.60 mm), minimum track 0.2 mm, 0 failures (`../jlc-dfm.json`).

Assembly:
- **LCSC numbers:** stage 43: 93 BOM lines, 87 JLC-assembled (19 Basic, 68 Extended) and 6 consigned or hand-assembled (`../PROTOTYPE-LOT.md`); the earlier census: 84 of 94 source lines map to a checked LCSC part (48 exact from the survey, 35 changed or added since, most of them the 2026-10-09 Basic swaps, the stage-14 bias parts, stage 17's R5 CSS2H-2512R-1L00F (C4175647, JLC Extended) and the stage-30 heartbeat parts, 1 accepted substitute; `../sourcing/`, `../bom-simplification/`). Ten are consigned or hand-assembled: F1 fuse, F2 (Schurter UMT-H 3403.0279.23, 1.5 kA, blower-supply tap; LCSC C3163739 carries no stock, so consign it from Digi-Key), C1/C2 (KEMET R463N410050N1K, Digi-Key), C5/C6 (TDK B32676G1905K000), T1, the resonant bank C21–C23/C151/C152 (TDK B32643H8104J000, tick H on the fit mark), L1 (TDK B82726S2243A020), J3, D3/D17 (Good-Ark 30KPA150CA, P600 axial) and U41/U42 (RECOM R24C2T25/R-R). Check stock again before ordering. U9 / U32 / U44 (Chipanalog CA-IS3720HW C428883 / CA-IS3720LW C2890049, stage 31): JLC had 1,640 / 2,542 on 2026-10-14. U1/U2 (Infineon 2EDR8259XXUMA1, LCSC C17455725, stage 29) are now JLC-assembled; Digi-Key holds the volume stock. R130 (Vishay AC05 0.15 ohm, LCSC C1382388, stage 28) is THT and mounted upright: body seated on pad 1 (square), the top lead bent down into pad 2.
- **Lead trim (insulation):** trim every THT lead to ≤ 2.5 mm below the board bottom after soldering (ASSEMBLY.md); the bank's leads protrude 3.35–4.35 mm and are trimmed to this rule too; trim C1/C2's 25 mm leads to 4 mm before insertion.
- **Hand assembly:**
  - F1-CLIP (2 × Littelfuse 01250003H, 10 × 38 / Class CC clips, 30 A), soldered into the plated slots. Listed in `hand-assembly-extras.csv`, not in the JLC BOM: it has no CPL row, and JLC rejects a BOM designator without one;
  - the F1 cartridge, inserted after cleaning;
  - J3 (JST B2P3-VH, 7.92 mm pitch, unshrouded).
- **First-article inspection (closure review S10-3):** the 0.3 mm driver output necks run under the 0805 VDD–VSS stacks with 0.30 mm to the pads. Inspect for solder bridges under C10/C145/C11, C8/C146, C17/C147/C18 and C15/C148. IR-check U26 (TPS7A4700) at first power-up: its In1 n_ls spreading plane has thinned over stages 8–11 (DECISIONS stage 11).
- **Through-hole reflow:** the REDCUBE studs (J2, J5; J7–J10 were removed in stage 21) are THR parts, soldered by reflow (paste in hole), not wave. Low-current THT pads in the 2 oz pours have 0.5 mm × 4 thermal spokes (review M3). Power pins stay solid: hand rework of them only on a bottom-preheated board (≥ 100 °C).
- Check each CPL rotation in JLCPCB's preview; centroids are pad centres (review M9). R5 (CSS2H-2512R-1L00F, stage 17): its centroid is the centre of the two pasted current pads (38.5, 12.6), not of the land, whose two sense fingers run 1.5 mm west of the body (`scripts/bom_cpl_jlc.py`); the land is a project footprint, so check R5's position and rotation against JLC's own C4175647 footprint in the preview. The sense fingers are mask-open copper with no paste.
- `assembly-drawing.pdf`: F.Fab (all designators, including the 115 with no clear silk spot (hole and fiducial designators are there by design)), silk and outline, scaled to A4.

Deviations and notes:
- Plated through-hole pads have lands on both outer layers. Unconnected inner rings are removed on purpose.
- Accepted DRC warnings, against 0 errors and 0 unconnected:
  - 11 short dangling stubs (≤ 1.1 mm);
  - 20 silk-over-copper, 1 silk overlap (Q2's designator on the BR1 outline) and 2 silk-to-edge (PS1/PS2 outlines);
  - 199 `lib_footprint_issues`, from the project's unconfigured stock-library table.
