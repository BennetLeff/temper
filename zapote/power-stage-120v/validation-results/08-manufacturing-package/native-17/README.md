# 08 Manufacturing package: native-17 candidate

A **candidate** JLCPCB package for native-17, reviewed independently of
KiCad. It doesn't release fabrication: `DECISIONS.md` controls that, and its
gates are open.

- Board: `native-17/section.kicad_pcb` (presentation revision), SHA-256
  `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
- Tools: KiCad 10.0.4 `kicad-cli`, gerbv 2.11.1 (independent renderer),
  Miniforge Python 3.12.
- Evidence class: exact structural for file content.

The silkscreen step of task 08 was done earlier (designators 1.0/0.15 mm
since native-11).

## Files (`fab/`)

| File | Content |
| --- | --- |
| `gerbers/` and `native-17-gerbers.zip` | F/In1/In2/B copper, paste, silk (with mask subtracted), mask, outline; PTH and NPTH Excellon (mm) with Gerber drill maps |
| `drill-report.txt` | KiCad drill report |
| `bom-jlcpcb.csv` | 57 lines, JLCPCB columns plus manufacturer part number and mount type |
| `cpl-jlcpcb.csv` | 135 placements (36 THT, 99 SMD/other) |
| `positions-kicad.csv` | KiCad's own position export |
| `FAB-NOTE.md` | Order requirements and deviations |

**No LCSC numbers exist yet.** `frozen/default.csv` carries manufacturer part
numbers in its LCSC column. Every BOM line is marked "LCSC number to be
sourced, or consigned/hand-assembled"; JLCPCB assembly needs a checked LCSC
number per line, and each CPL rotation checked in JLCPCB's preview.

## Independent review (`scripts/review_fab.py`, `review.json`)

The review reads the Excellon files and the outline Gerber as text, renders
every Gerber with gerbv on one fixed 1000 dpi grid (no border), and checks
each drill hit. It doesn't use KiCad.

| Check | Result |
| --- | --- |
| Outline | 240.000 × 160.000 mm |
| Holes | 293 plated (116 component + 177 via, from each tool's X2 function) and 8 non-plated; the board's census is 116 pads + 177 vias |
| Outer copper around every plated hole, F and B (12 points at drill radius + 0.12 mm) | **293/293 on both sides** |
| Mask opening over every component hole, both sides | 116/116 |
| Vias | 353 of 354 via sides tented |
| Silk over a component land | 0: every land with silk under it is cleared by a flash in the silk file's clear-polarity section |
| JLCPCB rules (`tools/jlc_dfm_check.py`, including the new outer-land gate) | PASS |

**Negative control:** the same review on native-15's Gerbers
(`negative-control-native15-review.json`) fails with 37 front and 74 back
holes without outer copper. That is exactly KiCad's census for native-15:
23 pads with neither land, plus 14 top-missing and 51 bottom-missing. So the
review catches this defect class independently.

Renderer note: gerbv doesn't clear KiCad's RoundRect aperture macro in
clear-polarity mode, so six roundrect pin-1 pads (J4.1, D1.1, D2.1, J3.1
and F1's two pin-1 clip pads) *render* with silk on them. The Gerber does clear them, so the silk
check uses the clear-polarity flashes, not the render.

## Reproduce (unit root)

```sh
B=native-17/section.kicad_pcb
O=validation-results/08-manufacturing-package/native-17/fab
kicad-cli pcb export gerbers --output $O/gerbers/ --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask $B
kicad-cli pcb export drill --output $O/gerbers/ --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 --generate-report --report-path $O/drill-report.txt $B
kicad-cli pcb export pos --output $O/positions-kicad.csv --format csv --units mm --side both $B
$KICAD_PY validation-results/08-manufacturing-package/native-17/scripts/bom_cpl_jlc.py $B frozen/default.csv $O
python3 validation-results/08-manufacturing-package/native-17/scripts/review_fab.py $O/gerbers validation-results/08-manufacturing-package/native-17/review.json
```

Gerber files embed a creation timestamp, so regenerated files differ in
their headers; the zip's hash is for the committed set.
