# Fabrication note: power-stage-120v native-21 (CANDIDATE, not released)

Board: native-21 stage 32 (via cleanup: 120 of the 124 legacy 0.85/0.3 signal vias are the standard 0.6/0.3, same drill, the 4 on the mains nets ac_n_in / l_filt / n_filt keep 0.85; HSB_GOOD, BUS_FAULT_ISO and BIAS_GOOD's U40 branch hop on In2 instead of B.Cu; BOM unchanged; DECISIONS.md item 35; stage 31: BOM only on the stage-30 copper: U9 / U32 Chipanalog CA-IS3720HW and U44 CA-IS3720LW in place of the ISO7710DWR / ISO7710FDWR, same land pattern, spare-channel pins 5 / 12 left open; the 24 × 1210 10 µF are Samsung CL32B106KBJNNNE; DECISIONS.md item 34; stage 30: bias-monitor heartbeat: HS-A ISO6721FB link U43, HS-B default-LOW verdict U44, LS oscillator U45 / heartbeat U32 / SELV NAND U46 / pump D19 into U40; U9 BUS_FAULT RC R134 / C167; the per-rail notice stages, U33 / U34 and the OR U25 are gone; DECISIONS.md item 33; stage 29: U1/U2 Infineon 2EDR8259X with 8.2 ohm gates, DECISIONS.md item 31; stage 28: F2 Schurter UMT-H 1.5 kA + R130 0.15 ohm limiter, DECISIONS.md item 30; stage 27: J1 Phoenix 1714971 MKDS 5/2-9,5, UL/CSA group B 30 A; F1 5.65 mm left; DECISIONS.md item 29; stage 26: C126–C129 6SVPC220MV, BOM only, DECISIONS.md item 28; stage 22: DIS = NAND(PERMIT, BIAS_GOOD): Q1 / Q4 and R8 / R16 deleted, DECISIONS.md item 27; stage 21b: stage 21 plus the OCP Kelvin return run under its pour and C30 / C31 beside U6, DECISIONS.md item 26; stage 21: BR1 feeds the bus directly, the J7–J10 rail-link studs are gone, R5.4 via field 0.8/0.5 mm; DECISIONS.md item 25; it includes stage 20's four part swaps, DECISIONS.md item 23: T1 CST3015-200ED + R39 3.0 ohm, U36 VOL628A-2X001T, resonant bank B32654A1104J000; 19c is the benchmark: stage 19b with leg A's VCCI cap C7 moved under U1, DECISIONS.md item 19c; stage 19b was stage 19 plus four 100 nF v3v3-selv_gnd reference-transfer caps C153-C156 beside pwm_hb's J4-side layer changes, DECISIONS.md 2026-10-12 item 19b; stage 19 was stage 18 with the converter-local capacitors at the RECOM U41 / U42 output pins and the TPS7A47 U26 pins, bus_fault_hot routed along its Kelvin return, ct_zc / pwm_hb / pwm_lb re-laid on continuous references, and the comparator / monitor bypass caps beside their ICs, DECISIONS.md 2026-10-12 item 19; stage 18 was stage 17b with the SELV LINE_ZC_RAW / V15_SELV B.Cu runs re-laid ≥ 12.6 mm from RES_A, DECISIONS.md 2026-10-12 item 18; stage 17b was stage 16 with R5 = Bourns CSS2H-2512R-1L00F on its Kelvin land and declared pour priorities so the fill no longer depends on KiCad's fill order, DECISIONS.md 2026-10-12 item 17 / 17b; stage 16 was stage 15b plus the F2 / J11 blower-supply mains tap, item 16; stage 15b was stage 14 plus the 28 A tank hardware: R34 12.6 k, R43/R46 2.21 k and SW_A / SW_B copper widening, DECISIONS.md 2026-10-10 items 13-14; stage 14 added one RECOM R24C2T25/R-R isolated bias module per high side, U41/U42, the 9 µF C5/C6 bus film and the 2 × 30KPA150CA series bus clamp D3/D17, DECISIONS.md 2026-10-09 stage 14; stage 13b added the BOM simplification, the 5 × TDK B32654 resonant bank and the C1/C2 X2 swap; stage 12 carried the independent-review fixes, `../REVIEW-TRIAGE.md`), rebuilt from
`native-21/layout/copper.json` by `sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR`;
SHA-256
`2fb346dc8277e4295d8ef88effabdcc71dcd363fcaa93604800ddc2872fbfa4e`.
Gerbers: `native-21-gerbers.zip`, SHA-256
`b9b25cb5ead3e32a442bd564fbf60108d4f28cd70691fa8cd134089075774043`.

**This package isn't released for ordering.** The gates come in two tiers (decision 2026-10-08; PROTOTYPE-LOT.md agrees).

**Before ordering the bench prototype lot** (run on an isolated, current-limited supply):
- the native-21 FEM correction matrices (leg A/B `a21corr` / `b21corr`) land and F6 re-runs on them. A failure would mean a copper change;
- M11 (heatsink HOT↔PE stack) is approved (DECISIONS.md 2026-10-08). Its parts still need sourcing: AlN tiles (quote), non-conductive compound, gap pad, spreader bar, comb spring, FR-4 strip (`../owner-items/m11/`);
- procurement of the no-stock parts in `../owner-items/order/ORDER-PACKAGE.md`, incl. T1, the RECOM R24C2T25/R-R bias modules U41/U42, the 30KPA150CA clamp pair D3/D17, C5/C6 and the 5 × TDK B32654A1104K000 resonant caps.

**Before mains-connected or unattended operation, and before product release:**
- insulation and thermal qualification (PD3, IEC 60664-4, hipot, partial discharge);
- the laminate CTI: settled from Kingboard / UL records by naming KB-6164 on the order (`../sourcing/inquiries/CTI-RESEARCH-2026-10-14.md`, DECISIONS 41); the certifier accepts PLC 3 as group IIIa (CERTIFIER-PACKET A3);
- F1 (Littelfuse KLDR025.TXP, UL Class CC, 600 Vac / 200 kA): the open-clip (01250003H) acceptance and the clip's voltage rating and agency file (`../owner-items/f1cc/`). The nameplate is 120–127 V~ 60 Hz, and there is no inlet fuse (DECISIONS.md 2026-10-09);
- the certification lab's answer on the tank-voltage RMS convention (M6 reversal condition);
- RES_A (297 V rms at 28 A) is held at 12.6 mm reinforced creepage to SELV/PE on the outer layers (item 18); the lab confirms that same-layer inner paths count as solid insulation (C152's inner rings are 9.694 mm from the SELV inner islands).

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
| **Via covering** | **Epoxy-filled and capped (POFV) for all 695 × 0.3 mm vias, no exceptions.** 61 sit fully inside SMD pads and 78 more overlap a pad edge (`native-21/verification/via_in_pad.py`), including the R5 shunt current-pad arrays and the exposed-pad thermal fields (U26–U28 3 × 3, U35 2 × 2). The ten 1.6/0.8 current vias stay tented (JLC fills holes ≤ 0.5 mm only). Via sizes (stage 32, `via_in_pad.py` census): 691 × 0.6/0.3 and 4 × 0.85/0.3 (the 695 POFV vias), 5 × 0.8/0.5 (R5.4, in or at the pad), 10 × 1.6/0.8 (tented). The KiCad file says `filling/capping no`; this note is the requirement. Select "Confirm production files" |
| Drills | 816 plated (710 vias, 106 component holes, 4 of them **plated slots 1.2 × 2.5 mm** for F1's 10 × 38 clips: routed slots, G85 in the PTH drill file), 15 non-plated (8 connector holes, 7 M3 fixings) |
| Board-only parts | 39 bring-up test pads (bare copper), 3 fiducials (1 mm, 3 mm mask opening), 7 M3 holes at the positions the enclosure adopted; none in BOM/CPL. **H2–H7: the whole fixing chain is insulating** (nylon screw, washer and standoff; no metal screw, nut or insert within 10 mm of the board), with outer copper clear under the 7 mm washer. H1 may take metal hardware (native-21/BRINGUP-PROBES.md). Enclosure R30: male-female standoffs threaded into the tapped base (nylon at H2–H7 with a nylon top screw and washer, ≥ 10 mm; brass at H1). H1 is a bare NPTH, so its metal hardware bonds the chassis only; the board's PE comes in at J6 |

JLC rules (`tools/jlc_dfm_check.py`, capabilities page re-read verbatim 2026-10-08):
- PTH annular ring ≥ 0.254 mm at 2 oz.
- Via diameter ≥ hole + 0.1 mm; our floor is a 0.15 mm ring.
- Track/space at 2 oz multilayer: JLC allows 0.15/0.15 mm. Our floor is 0.2/0.2 mm, and the tightest gap is the U41/U42 modules' 0.20 mm pad-to-pad (0.45 mm pads at 0.65 mm pitch).
- Via drill ≥ 0.15 mm.
- Result: **PASS**. 710 vias, 106 plated pads (slot rings checked per axis: 0.60 mm), minimum track 0.2 mm, 0 failures (`../jlc-dfm.json`).

Assembly:
- **LCSC numbers:** 84 of 94 source lines map to a checked LCSC part (48 exact from the survey, 35 changed or added since, most of them the 2026-10-09 Basic swaps, the stage-14 bias parts, stage 17's R5 CSS2H-2512R-1L00F (C4175647, JLC Extended) and the stage-30 heartbeat parts, 1 accepted substitute; `../sourcing/`, `../bom-simplification/`). Ten are consigned or hand-assembled: F1 fuse, F2 (Schurter UMT-H 3403.0279.23, 1.5 kA, blower-supply tap; LCSC C3163739 carries no stock, so consign it from Digi-Key), C1/C2 (KEMET R463N410050N1K, Digi-Key), C5/C6 (TDK B32676G1905K000), T1, the resonant bank C21–C23/C151/C152 (TDK B32654A1104K000), J3, D3/D17 (Good-Ark 30KPA150CA, P600 axial) and U41/U42 (RECOM R24C2T25/R-R). Check stock again before ordering. U9 / U32 / U44 (Chipanalog CA-IS3720HW C428883 / CA-IS3720LW C2890049, stage 31): JLC had 1,640 / 2,542 on 2026-10-14. U1/U2 (Infineon 2EDR8259XXUMA1, LCSC C17455725, stage 29) are now JLC-assembled; Digi-Key holds the volume stock. R130 (Vishay AC05 0.15 ohm, LCSC C1382388, stage 28) is THT and mounted upright: body seated on pad 1 (square), the top lead bent down into pad 2.
- **Lead trim (insulation):** trim every THT lead to ≤ 2.5 mm below the board bottom after soldering (ASSEMBLY.md); trim C1/C2's 25 mm leads to 4 mm before insertion.
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
