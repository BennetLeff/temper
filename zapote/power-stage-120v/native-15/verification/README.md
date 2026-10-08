# Native-15 verification, 2026-09-27: C1/C2 X2 capacitor correction

Native-15 is native-13 with one owner-approved part correction from
[validation task 07](../../validation-results/07-conducted-emi/round2/C1-C2-PROPOSAL.md):

- C1/C2: KEMET R463R410000M1M → **R463N410000N1M** (1 µF X2 310 VAC). The old
  part has a 27.5 mm lead pitch and didn't fit the 22.5 mm footprint. The new
  part has 22.5 mm pitch, 26.5 × 11.0 × 20.0 mm nominal and 26.8 × 11.2 ×
  20.1 mm maximum body (KEMET R46 datasheet, SHA-256 `5a3131ce…`, p.10 row,
  p.3 tolerances).
- New footprint `temper:KEMET_R463N410000N1M_P22.50_ReviewOnly`
  ([spec](../../libraries/footprint-specs/KEMET_R463N410000N1M_P22.50_ReviewOnly.yaml)),
  derived from the stock 22.5 mm pattern. Pads and drills are unchanged
  (2.4 mm pad, 1.2 mm drill). The fab outline is at the 11.0 mm nominal
  width. The courtyard is the maximum body plus 0.25 mm across and 0.10 mm
  at the length ends, so it grows only in width (11.0 → 11.7 mm); its length
  equals the stock pattern's.
- New 3D envelope `models3d/capacitors/KEMET_R463N410000N1M.step`, at the
  maximum body, not nominal.

Native-14 is the placement. Against native-12, only C1/C2's footprint
(identity, silk, fab, courtyard, 3D model) and MPN/Value differ; every pose
and pad is identical, and the placement metrics are identical.

Electrical board SHA-256: `bec1df670d5965bff852b5c0e674dbfa2a6396767c78f213f88b58eddad9ab5f`.
The active board is the presentation revision (labels and 3D models),
`a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`, and its
copper is identical to the electrical board.

| Check | Result |
| --- | --- |
| Full DRC, fill + three repeats | 0 copper findings, 0 schematic mismatch; 28 library + 3 L1/J3 silk overlaps (same as native-13); board stable |
| Opens | Only the intended R5 Kelvin split; pad clusters identical to native-13 |
| Copper vs native-13 | Pads, tracks and vias identical; three refilled zone polygons differ only in vertex order (symmetric-difference area 0.0 mm²); power screens unchanged (0.886 / 0.457) |
| Barrier | 0 (Rust) and 0 (pinned oracle) |
| Parity / copper identity / stackup / JLCPCB / hardware surface | PASS / PASS / pass / PASS / 0 hits |
| Presentation board | Copper identical; the same DRC counts and gates; 24 models attached including C1/C2; 135 references labeled |
| Source audit | 53/53 with C1/C2 added to the safety identity table; board tests 44/44 (retargeted to native-14/15) |

## C1/C2 mechanical clearances (courtyard to courtyard)

| Part | Nearest | native-13 | native-15 |
| --- | --- | --- | --- |
| C1 | RV1 | 1.91 mm | 1.56 mm |
| C1 | PS1 | 2.26 mm | 1.91 mm |
| C2 | C5 | 0.16 mm | 0.16 mm |
| C2 | BR1 | 2.91 mm | 2.91 mm |

C2's worst-case (maximum) body is 0.60 mm from C5's body, and its top edge is
at y = 10.20 mm, outside the 10 mm heat-sink zone. A 0.25 mm allowance at the
length ends would have put C2's courtyard 0.01 mm from C5's and 0.1 mm inside
the heat-sink zone, so the length ends use the IPC-7351 least allowance
(0.10 mm), which still encloses the maximum body.

Lead fit: the 1.2 mm drill against the 0.85 mm maximum lead leaves 0.35 mm of
total pitch accommodation, against a ±0.4 mm pitch tolerance. At the extreme,
the leads need about 0.05 mm of forming; confirm on the first article.

Not a fabrication or powered-operation release. The EMI task 07 still needs
C1/C2 ESR/ESL (the R46 datasheet's impedance data now applies to the fitted
part).
