# Fabrication note: power-stage-120v native-21 (CANDIDATE, not released)

Board: native-21 stage 57, the board of record (DECISIONS.md item 87: the Q2 / Q3 / Q5 / Q6 TO-247 holes go from 1.5 to 1.8 mm, footprint `temper:TO-247-3_Vertical_D1.8`; stage 56 was item 85: the R24C2T25 CTRL dividers R127 / R129 27 k → 16 k RT0603BRD0716KL, BOM only, copper unchanged from stage 55; stage 55 was item 82: U47 SN74LVC1G17 Schmitt buffer + C179 100 nF between the R134 / C167 CMTI filter and U13.A, C167 moved 3.25 mm south, one new v3v3 via, the SELV-spine lock reissued; stage 54 was item 81: the c54 remediation, R_on on UniRoyal PS12 2 W, the split bleed on Panasonic ERJ-PA3, R44 / R45 11 k, an ac_n_in F.Cu strip with 8 stitch vias at J1.2 and 9 track-cleanup edits; stage 53 was DECISIONS.md item 75: the S10 ovp_ok_hot In1 run moves to In2, the R43 real-pose fit gate and the 3D-model gate; item 74: the prototype bank C21–C23 / C151 / C152 is TDK
B32643H8104J000 (24 A strict ladder; Mouser 1,736 / DigiKey 306 on the 2026-10-18 read), bought by JLC Global Sourcing and
hand-soldered by JLC into the 22.5 mm holes; L1 is B82726S2243A020, JLC Global Sourcing (C7084710 holds 0), JLC
hand-solders it (consign-r1, owner 2026-10-18); C3 / C4 are Murata DE1E3RA222MJ4BH01F. Item 73:
the dual-pitch footprint
`temper:Bank_Film_DualPitch_P22.5_P27.5_Radial` (pad 1 at x 163.0; pad-2 holes at x 185.5 for the TDK B32643H / B32643B parts and x 190.5 for the KNSCHA fallback,
both on sw_b; 1.2 mm drills, 0.6 mm rings); a sourcing override: the H bank caps the commissioned ladder at 24 A
strict (B32643B8104J000, 28 A, fits the same holes later; KNSCHA stops at 22 A); item 71: U46.A (hsb_good) driven from PERMIT
through R135 100 k, so BIAS_GOOD = bias_ok AND PERMIT and TP19 reads low while PERMIT is low; item 70: S23's B′-1.02 V
OCP divider, R33 7.5 k / R34 16 k / R35 11 k, and the bank-area re-cut for a 2000 V bank; item 67: the four TPS70950
ENs on 100 k / 27 k dividers and on the 125 °C TPS70950QDBVRQ1, the REF25 watchdog on U14's second channel, BIAS_GOOD
read back on J4.1 through R146, end-of-line test pads; item 63: U5 (REF25) on the 125 °C LM4050AEM3-2.5/NOPB; item 62:
the rail-monitor ICs on their 125 °C grades; item 60: the S16 rail-monitor values; the stage history is DECISIONS.md
items 12–75). Built by `sh native-21/layout/gates/chain.sh native21s57 …`; SHA-256
`25596d8eff460eabab3c538c83daea0d88eb1135fd7ae1519d8cc30a4f32421a` (the c57b build; copper key a4a2e176134f; s56's was cf4d7c896672). Plated holes 885: the
bank goes into the 22.5 mm holes (pad 2 at x 185.5); the five x 190.5 holes are plated and stay open at assembly.
The silk bank-variant fit mark ("BANK FIT, TICK ONE") carries H = B32643H8104J000 24 A MAX and B = B32643B8104J000
28 A: tick H on the prototype boards. U5 is JLC stock reserved by pre-order (JLC 50 against 20 on the 20-board lot;
OPEN-ITEMS owner action 7 for volume); U3 / U37–U39 TPS70950QDBVRQ1 (C485909) are JLC Extended, 11,607 in stock.
Gerbers: `native-21-gerbers.zip`, SHA-256
`f91513c5ce1163b758912ec1e4899f406645d0471d9a5bce69a232e08157cea9`. Thermal basis: hot-copper B3, tank ceiling 17.5 A
(DECISIONS.md item 61).

**This package isn't released for ordering.** The gates come in two tiers (decision 2026-10-08; PROTOTYPE-LOT.md agrees).

**Before ordering the bench prototype lot** (run on an isolated, current-limited supply):
- the native-21 FEM correction matrices (leg A/B `a21corr` / `b21corr`) land and F6 re-runs on them. A failure would mean a copper change;
- M11 (heatsink HOT↔PE stack) is approved (DECISIONS.md 2026-10-08). Its parts still need sourcing: AlN tiles (quote), non-conductive compound, gap pad, spreader bar, comb spring, FR-4 strip (`../owner-items/m11/`);
- procurement per `../owner-items/order/ORDER-PACKAGE.md` (consign-r1 package, owner 2026-10-18): the JLC Global Sourcing lines (U41/U42 RECOM R24C2T25/R-R, the bank, C5/C6, L1, D3/D17 Good-Ark 30KPA150CA, F2, J2/J5, J6 if offered) must reach JLC's parts warehouse, the consigned FET lot (Q2/Q3/Q5/Q6) must arrive, and the C1/C2, T1 and U5 pre-orders must be placed, all before the PCBA order. TDK B32643B8104J000 is ordered only for the 28 A route (DECISIONS.md items 73 and 74, OPEN-ITEMS S28).

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
| **Via covering** | **Epoxy-filled and capped (POFV) for all 771 × 0.3 mm vias (726 × 0.6/0.3, 45 × 0.85/0.3; stage 55), no exceptions.** 73 sit fully inside SMD pads and 73 more overlap a pad edge (stage 55, as at s54; earlier text said 60 / 75) (`native-21/verification/via_in_pad.py`), including the R5 shunt current-pad arrays and the exposed-pad thermal fields (U26–U28 3 × 3, U35 2 × 2). The ten 1.6/0.8 current vias stay tented (JLC fills holes ≤ 0.5 mm only). Via sizes (stage 32, `via_in_pad.py` census): 691 × 0.6/0.3 and 4 × 0.85/0.3 (the 695 POFV vias), 5 × 0.8/0.5 (R5.4, in or at the pad), 10 × 1.6/0.8 (tented). The KiCad file says `filling/capping no`; this note is the requirement. Select "Confirm production files" |
| Drills | 885 plated (786 vias, 99 component holes, 4 of them **plated slots 1.2 × 2.5 mm** for F1's 10 × 38 clips: routed slots, G85 in the PTH drill file), 14 non-plated (drill report, stage 44: 2 × 1.02, 10 × 3.2, 2 × 5.2 mm) |
| Board-only parts | 39 bring-up test pads (bare copper), 3 fiducials (1 mm, 3 mm mask opening), 10 M3 holes (board_only21.json: H1 and H2 may take metal, H3–H10 nylon only); the R43 enclosure supports seven of them: H1 and H3–H8 (R43 calls them H1–H7, so its "H2–H7" are the board's H3–H8); **H2, H9 and H10 are left empty: fit no hardware in them** (DECISIONS 76); none in BOM/CPL. **At the supported nylon holes (board H3–H8): the whole fixing chain is insulating** (nylon screw, washer and standoff; no metal screw, nut or insert within 10 mm of the board), with outer copper clear under the 7 mm washer. H1 may take metal hardware (native-21/BRINGUP-PROBES.md). Enclosure R30: male-female standoffs threaded into the tapped base (nylon at the board's H3–H8 with a nylon top screw and washer, ≥ 10 mm; brass at H1). H1 is a bare NPTH, so its metal hardware bonds the chassis only; the board's PE comes in at J6 |

JLC rules (`tools/jlc_dfm_check.py`, capabilities page re-read verbatim 2026-10-08):
- PTH annular ring ≥ 0.254 mm at 2 oz.
- Via diameter ≥ hole + 0.1 mm; our floor is a 0.15 mm ring.
- Track/space at 2 oz multilayer: JLC allows 0.15/0.15 mm. Our floor is 0.2/0.2 mm, and the tightest gap is the U41/U42 modules' 0.20 mm pad-to-pad (0.45 mm pads at 0.65 mm pitch).
- Via drill ≥ 0.15 mm.
- Result: **PASS**. 786 vias (stage 55), 99 plated pads (slot rings checked per axis: 0.60 mm), minimum track 0.2 mm, 0 failures (`../jlc-dfm.json`).

Assembly:
- **LCSC numbers and assembly routes (consign-r1 package, owner 2026-10-18, restored by DECISIONS 91: JLC does as much as possible; through-hole hand work only where it can't be avoided):** `bom-jlcpcb.csv` has 95 lines: 92 assembled by JLC (18 Basic, 74 Extended; stage 54 moved the 4.99 k line from Basic 0603WAF4991T5E to Extended ERJ-PA3F4991V) and 3 left to the owner (BR1, RV1, the F1 cartridge), plus the F1 clips in `hand-assembly-extras.csv`. The route of each non-catalogue line is in its Assembly column, written by `../scripts/apply_lcsc.py` (ORDER_PLAN). Check stock again before ordering.
  - **JLC Global Sourcing** (JLC buys from the named distributor; the part must be in JLC's warehouse before the PCBA order; JLC promises no batch and may cancel a part it can't assemble): U41/U42 RECOM R24C2T25/R-R (C9900245652; **reject the auto-match C22466894 "R24C2T25-R"**, a different, non-/R product; MSL 3, have JLC bake it), the bank C21–C23/C151/C152 TDK B32643H8104J000 (no public LCSC number: select the private-library stock at the BOM step), C5/C6 TDK B32676G1905K000 (C3802167), L1 TDK B82726S2243A020 (C7084710), D3/D17 **Good-Ark** 30KPA150CA (no LCSC number on purpose: JLC's C19111562 is the Littelfuse-branded part; select the private-library Good-Ark stock), F2 Schurter 3403.0279.23 (C3163739), J2/J5 Würth 7466004R (C6708126), and J6 Phoenix 1704004 (C5481600) if JLC lists a supplier; if not, J6 is Do Not Place and the owner hand-solders it.
  - **Consigned (DECISIONS 91, reversing DECISIONS 86):** Q2/Q3/Q5/Q6 Infineon IPW65R018CFD7 (C3289047), from one recorded DigiKey lot sized to the assembled board count: ship 4 per assembled board plus 4 spare (e.g. 24 for 5 boards, 44 for 10, or 84 of a 120-piece lot for 20); all placements come from the consigned stock, none from JLC's own (JLC does not mix sources for one MPN in an order). JLC hand-solders them.
  - **Reserved by pre-order** (JLC's own stock, no custom lot numbers): C1/C2 KEMET R463N410050N1K (C3299886, JLC 46 against 40 on 2026-10-18), T1 CST3015-200ED (C50132500, 64 against 20), U5 LM4050AEM3-2.5/NOPB (C2156518, 50 against 20).
  - **Order-file variant:** J3/J11 are ordered as the grey JST B2P3-VH-H(LF)(SN), C160900 (JLC 5,610), the same header in a grey housing (eVH.pdf colour suffix H); the source and frozen netlist keep B2P3-VH(LF)(SN) (`apply_lcsc.py` ORDER_VARIANT; ledger `alternates`).
  - **JLC hand-solders every fitted THT part**, including J1, J3/J11, J4, J6 (if sourced), C1–C6, C38–C41, L1, PS2, R130, D3/D17, the bank and the FETs. R130 (Vishay AC05 0.15 ohm, C1382388) is mounted upright: body seated on pad 1 (square), the top lead bent down into pad 2. U9 / U32 (CA-IS3720HW C428883), U43 / U44 (ISO6721FBDR, since stage 40) and U1/U2 (2EDR8259XXUMA1, C17455725) are JLC-assembled from JLC stock.
- **Order remarks** (paste into the PCBA order's remark field): "Q2, Q3, Q5, Q6 (TO-247, consigned): seat each upright on its center drain shoulder (not flush on the board), pushed toward the rear edge with tab faces coplanar within 0.2 mm and perpendicular within 1 deg. BR1 is Do Not Place: leave its holes open and unsoldered. Trim every through-hole lead to 2.5 mm or less below the board bottom after soldering. The bank C21–C23/C151/C152 goes in the 22.5 mm holes (pad 2 at x 185.5); leave the five x 190.5 holes open and unsoldered. Leave RV1 and the F1 clips unfitted. Tick H on the bank-fit silk mark."
- **Lead trim (insulation):** trim every THT lead to ≤ 2.5 mm below the board bottom after soldering (ASSEMBLY.md); the bank's leads protrude 3.35–4.35 mm and are trimmed to this rule too; trim C1/C2's 25 mm leads to 4 mm before insertion.
- **Owner hand assembly** (through-hole only, on a bottom-preheated board ≥ 100 °C):
  - BR1 (GBJ2510-F), Do Not Place at JLC; the owner fits it before mains. It is the only mains-to-bus path: with it out, PS2 runs from mains while the bus is fed from a bench DC supply, so nothing back-feeds PS2's output (bring-up with BR1 not fitted: `firmware/components/power/COMMISSIONING.md`, commission-s53 2026-10-18);
  - RV1 (TMOV20RP175E), Do Not Place at JLC (form lead 2 in line, FOOTPRINTS F4);
  - F1-CLIP (2 × Littelfuse 01250003H, 10 × 38 / Class CC clips, 30 A), soldered into the plated slots. Listed in `hand-assembly-extras.csv`, not in the JLC BOM: it has no CPL row, and JLC rejects a BOM designator without one (splitting the clips into BOM components is deferred, consign-r1 candidate (c));
  - the F1 cartridge, inserted after cleaning;
  - J6, only if JLC Global Sourcing offers no supplier.
- **First-article inspection (closure review S10-3):** the 0.3 mm driver output necks run under the 0805 VDD–VSS stacks with 0.30 mm to the pads. Inspect for solder bridges under C10/C145/C11, C8/C146, C17/C147/C18 and C15/C148. IR-check U26 (TPS7A4700) at first power-up: its In1 n_ls spreading plane has thinned over stages 8–11 (DECISIONS stage 11).
- **Through-hole reflow:** the REDCUBE studs (J2, J5; J7–J10 were removed in stage 21) are THR parts, soldered by reflow (paste in hole), not wave. Low-current THT pads in the 2 oz pours have 0.5 mm × 4 thermal spokes (review M3). Power pins stay solid: hand rework of them only on a bottom-preheated board (≥ 100 °C).
- **Upload `cpl-jlcpcb-order.csv` (rotation-corrected, Y negated) with `bom-jlcpcb.csv`: `cpl-jlcpcb.csv` is the uncorrected positive-Y source and previews mirrored off the board (JLC viewer, 2026-10-17).** Check each CPL rotation in JLCPCB's preview; centroids are pad centres (review M9). R5 (CSS2H-2512R-1L00F, stage 17): its centroid is the centre of the two pasted current pads (38.5, 12.6), not of the land, whose two sense fingers run 1.5 mm west of the body (`scripts/bom_cpl_jlc.py`); the land is a project footprint, so check R5's position and rotation against JLC's own C4175647 footprint in the preview. The sense fingers are mask-open copper with no paste.
- `assembly-drawing.pdf`: F.Fab (all designators, including the 115 with no clear silk spot (hole and fiducial designators are there by design)), silk and outline, scaled to A4.

Deviations and notes:
- Plated through-hole pads have lands on both outer layers. Unconnected inner rings are removed on purpose.
- Accepted DRC warnings, against 0 errors and 0 unconnected:
  - 11 short dangling stubs (≤ 1.1 mm);
  - 20 silk-over-copper, 1 silk overlap (Q2's designator on the BR1 outline) and 2 silk-to-edge (PS1/PS2 outlines);
  - 199 `lib_footprint_issues`, from the project's unconfigured stock-library table.
