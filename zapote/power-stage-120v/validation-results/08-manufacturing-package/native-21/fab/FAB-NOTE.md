# Fabrication note: power-stage-120v native-21 (CANDIDATE, not released)

Board: native-21 stage 6, rebuilt from `native-21/layout/copper.json` by
`sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR`; SHA-256
`e7b8fe778ed3e8f2d9aa22a49ad4d7b06b58b51b65da9a6106adf9543d5f2c54`.
Gerbers: `native-21-gerbers.zip`, SHA-256
`0b975203805af237e3f2a772e2946727f94916a777a9e1e36d33abbd6b3bae6b`.

**This package isn't released for ordering.** The release gates in `DECISIONS.md` and
`FAB-JLCPCB.md` are still open: insulation and thermal qualification, the laminate CTI
confirmation, and the LCSC sourcing below. Ordering is a purchase and needs the owner.

| Item | Requirement |
| --- | --- |
| Size | 290 × 190 mm L-shaped outline, 4 layers |
| Stackup | JLCPCB **JLC041622-7628**, 1.6 mm |
| Copper | **2 oz outer and 2 oz inner** |
| Laminate | CTI ≥ 175 V (material group IIIa) **required**; confirm on the order (open question to JLCPCB) |
| Surface finish | Lead-free HASL or ENIG |
| Solder mask / silk | Green / white |
| Impedance control | None |
| **Via covering** | **Epoxy-filled and capped (via-in-pad / POFV) for every 0.3 mm via** (730: 501 × 0.6/0.3 and 229 × 0.85/0.3). 42 sit inside SMD pads with no legal spot outside, plus the R5 shunt current-pad arrays. The ten 1.6/0.8 current vias stay tented (JLC fills holes ≤ 0.5 mm only). Select "Confirm production files". |
| Drills | 852 plated (740 vias, 112 component holes), 8 non-plated |

JLC rules applied (`tools/jlc_dfm_check.py`, re-read verbatim 2026-10-08): PTH annular ring
≥ 0.254 mm at 2 oz; via diameter ≥ hole + 0.1 mm (our floor is a 0.15 mm ring); tracks ≥ 0.2 mm
(8 mil at 2 oz); via drill ≥ 0.15 mm. Result: PASS (`../jlc-dfm.json`).

Deviations and notes:
- **No LCSC part numbers yet.** Every BOM line is "LCSC number to be sourced, or
  consigned/hand-assembled". JLCPCB assembly needs a checked LCSC number per line and each CPL
  rotation checked in JLCPCB's preview.
- Plated through-hole pads have lands on both outer layers; unconnected inner rings are removed
  on purpose.
- Accepted DRC warnings: 6 short dangling stubs, 20 silk-over-copper, 2 + 2 PS1/PS2/J3 outline
  silk at the board edge or overlapping; 199 `lib_footprint_issues` come from the project's
  unconfigured stock-library table.
- 75 reference designators that have no clear silk spot are on F.Fab only (assembly drawing).
