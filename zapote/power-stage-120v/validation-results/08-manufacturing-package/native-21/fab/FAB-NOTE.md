# Fabrication note: power-stage-120v native-21 (CANDIDATE, not released)

Board: native-21 stage 10 (the independent-review fixes and their closure-review rework, `../REVIEW-TRIAGE.md`), rebuilt from
`native-21/layout/copper.json` by `sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR`;
SHA-256
`ef993141572fa93ad593c1d0d7fb07424c6e90af78b8bb277e57a48e1887b6df`.
Gerbers: `native-21-gerbers.zip`, SHA-256
`a0f8fa40af9d0c142dd6c8714d763c31b09ecc694351074e54139d2f49319eb2`.

**This package isn't released for ordering.** These gates are still open:
- insulation and thermal qualification;
- the laminate CTI confirmation;
- F1 (MDA-25-R): the certifier's confirmation that the 10 kA @ 125 Vac rating covers the 127 V (+6 %) corner (nominal-voltage rule), and Recognized-component / clip acceptance (`../sourcing/F1-J3-PARTS.md`);
- the owner items in `../REVIEW-TRIAGE.md` (M6, M10, M11).

Ordering is a purchase and needs the owner.

| Item | Requirement |
| --- | --- |
| Size | 290 × 190 mm L-shaped outline, 4 layers |
| Stackup | JLCPCB **JLC041622-7628**, 1.6 mm nominal. **Finished thickness 1.6–1.76 mm** (+10 / −0 %): the REDCUBE THR studs need 1.6–2.0 mm (review m7), and JLC's ±10 % allows 1.44 mm. Ask JLC to confirm; if it can't hold the minimum, re-stack at 1.8 mm |
| Copper | **2 oz outer and 2 oz inner** |
| Laminate | **CTI ≥ 175 V (material group IIIa), a hard order condition.** Don't place the order until JLC confirms it in writing |
| Surface finish | **ENIG**: 0.5 mm HVSSOP (U35), 0.65 mm VQFN with exposed pads (U26–U28), capped via-in-pad |
| Solder mask / silk | Green / white |
| Impedance control | None |
| Order number | **Remove** (JLC's "remove order number" option); the silk carries the board ID instead |
| **Via covering** | **Epoxy-filled and capped (POFV) for all 766 × 0.3 mm vias, no exceptions.** 79 sit fully inside SMD pads and 62 more overlap a pad edge, including the R5 shunt current-pad arrays and the exposed-pad thermal fields (U26–U28 3 × 3, U35 2 × 2). The ten 1.6/0.8 current vias stay tented (JLC fills holes ≤ 0.5 mm only). The KiCad file says `filling/capping no`; this note is the requirement. Select "Confirm production files" |
| Drills | 888 plated (776 vias, 112 component holes), 15 non-plated (8 connector holes, 7 M3 fixings) |
| Board-only parts | 36 bring-up test pads (bare copper), 3 fiducials (1 mm, 3 mm mask opening), 7 M3 holes at the positions the enclosure adopted; none in BOM/CPL. **H2–H7: the whole fixing chain is insulating** (nylon screw, washer and standoff; no metal screw, nut or insert within 10 mm of the board), with outer copper clear under the 7 mm washer. H1 may take metal hardware (native-21/BRINGUP-PROBES.md) |

JLC rules (`tools/jlc_dfm_check.py`, capabilities page re-read verbatim 2026-10-08):
- PTH annular ring ≥ 0.254 mm at 2 oz.
- Via diameter ≥ hole + 0.1 mm; our floor is a 0.15 mm ring.
- Track/space at 2 oz multilayer: JLC allows 0.15/0.15 mm. Our floor is 0.2/0.2 mm, and the tightest gap is U35's 0.20 mm pad-to-pad.
- Via drill ≥ 0.15 mm.
- Result: **PASS**. 776 vias, 112 plated pads, minimum track 0.2 mm, 0 failures (`../jlc-dfm.json`).

Assembly:
- **LCSC numbers:** 88 of 95 source lines map to a checked LCSC part (82 exact, 5 changed or added after the survey, 1 accepted substitute; `../sourcing/`). Seven are consigned or hand-assembled: F1 fuse, C5/C6, U1/U2, T1, J3, R34, T2/T3. Check stock again before ordering.
- **Hand assembly:**
  - F1-CLIP (2 × Littelfuse 01220088Z, 30 A), soldered;
  - the F1 cartridge, inserted after cleaning;
  - J3 (JST B2P3-VH, 7.92 mm pitch, unshrouded).
- **Through-hole reflow:** the REDCUBE studs (J2, J5, J7–J10) are THR parts, soldered by reflow (paste in hole), not wave. Low-current THT pads in the 2 oz pours have 0.5 mm × 4 thermal spokes (review M3). Power pins stay solid: hand rework of them only on a bottom-preheated board (≥ 100 °C).
- Check each CPL rotation in JLCPCB's preview; centroids are pad centres (review M9).
- `assembly-drawing.pdf`: F.Fab (all designators, including the 114 with no clear silk spot), silk and outline, scaled to A4.

Deviations and notes:
- Plated through-hole pads have lands on both outer layers. Unconnected inner rings are removed on purpose.
- Accepted DRC warnings, against 0 errors and 0 unconnected:
  - 11 short dangling stubs (≤ 1.1 mm);
  - 20 silk-over-copper, 9 silk-overlap and 4 silk-to-edge;
  - 199 `lib_footprint_issues`, from the project's unconfigured stock-library table.
