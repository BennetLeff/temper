# 08 Manufacturing package: native-21 candidate

A **candidate** JLCPCB package for native-21 (stage 15b), reviewed independently of KiCad. It
does not release fabrication: `DECISIONS.md` controls that, and its gates are open
([fab/FAB-NOTE.md](fab/FAB-NOTE.md)).

- Board: native-21 stage 15b (stage 14 + 28 A protection values R34 / R43 / R46 and SW_A / SW_B widening, DECISIONS items 13-14), SHA-256
  `9a9c43c63f63d383c89b9dc1d4d03a34d4390cfa1c26bbe802d71e169c6ddf94`.
- Tools: KiCad 10.0.4 `kicad-cli`, gerbv 2.11.1 (independent renderer), Miniforge Python 3.12.
- Scripts: native-17's `bom_cpl_jlc.py` unchanged; `review_fab.py` with one change, below.

## Files (`fab/`)

| File | Content |
| --- | --- |
| `gerbers/` and `native-21-gerbers.zip` | F/In1/In2/B copper, paste, silk (mask subtracted), mask, outline; PTH and NPTH Excellon (mm) with Gerber drill maps |
| `drill-report.txt` | KiCad drill report |
| `bom-jlcpcb.csv` | 91 source lines plus the F1 clip line, JLCPCB columns plus manufacturer part number, mount type and assembly route (`scripts/apply_lcsc.py`) |
| `cpl-jlcpcb.csv` | 351 placements (37 THT, 314 SMD/other); pad-centre centroids |
| `assembly-drawing.pdf` | F.Fab (every designator), silk and outline, A4 fit (review M12) |
| `positions-kicad.csv` | KiCad's own position export |
| `FAB-NOTE.md` | Order requirements (including filled and capped vias) and deviations |

## Independent review (`scripts/review_fab.py`, `review.json`)

| Check | Result |
| --- | --- |
| Outline | 290 × 190 mm |
| Holes | 881 plated (118 component incl. 4 F1 slots + 763 via) and 15 non-plated; the board's census is 118 PTH pads + 763 vias |
| Outer copper around every plated hole, F and B (12 points at drill radius + 0.07 mm) | **877/877 round holes on both sides.** The 4 F1 slots (G85) are outside the script's parser and were checked in the drill file |
| Mask opening over every component hole, both sides | 112/112 round (+ 4 slots) |
| Silk over a component land | 0 |
| JLCPCB rules (`tools/jlc_dfm_check.py`, `jlc-dfm.json`) | PASS |

**Probe radius changed from 0.12 to 0.07 mm** beyond the drill edge. Native-21's 0.6/0.3 vias have
a 0.15 mm ring, so 0.12 mm sampled 0.03 mm (about one 1000 dpi pixel) inside the copper edge.
It reported 179 false misses, although KiCad's `FlashLayer` showed copper on both outer layers of
every via. **Negative control** at 0.07 mm, native-15's Gerbers
(`negative-control-native15-review.json`): it still fails with exactly 37 front and 74 back holes
without outer copper, the same as native-17's control at 0.12 mm. So the tighter probe still
catches the defect class.

## Reproduce (unit root)

```sh
B=<rebuilt native-21 board>   # sh native-21/layout/incr_iter.sh native-21/layout/copper.json - OUTDIR
O=validation-results/08-manufacturing-package/native-21/fab
kicad-cli pcb export gerbers --output $O/gerbers/ --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts --subtract-soldermask $B
kicad-cli pcb export drill --output $O/gerbers/ --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 --generate-report --report-path $O/drill-report.txt $B
kicad-cli pcb export pos --output $O/positions-kicad.csv --format csv --units mm --side both $B
$KICAD_PY validation-results/08-manufacturing-package/native-21/scripts/bom_cpl_jlc.py $B native-21/frozen/default.csv $O
python3 validation-results/08-manufacturing-package/native-21/scripts/apply_lcsc.py
kicad-cli pcb export pdf --mode-multipage --scale 0 --output $O/assembly-drawing.pdf --layers F.Fab,F.Silkscreen,Edge.Cuts --cl Edge.Cuts --sketch-pads-on-fab-layers --black-and-white $B
python3 validation-results/08-manufacturing-package/native-21/scripts/review_fab.py $O/gerbers validation-results/08-manufacturing-package/native-21/review.json
$KICAD_PY tools/jlc_dfm_check.py $B > validation-results/08-manufacturing-package/native-21/jlc-dfm.json
```

Gerber files embed a creation timestamp, so regenerated files differ in their headers; the zip's
hash is for the committed set.
