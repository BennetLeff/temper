# 08 Manufacturing package: native-21 candidate

A **candidate** JLCPCB package for native-21 (stage 6), reviewed independently of KiCad. It
does not release fabrication: `DECISIONS.md` controls that, and its gates are open
([fab/FAB-NOTE.md](fab/FAB-NOTE.md)).

- Board: native-21 stage 7 (stage-6 copper + board-only test pads, fiducials, holes; rebuilt), SHA-256
  `ebdfdb3cd209134498c863c9b914a19da773bf32f931144d51619354e18c6124`.
- Tools: KiCad 10.0.4 `kicad-cli`, gerbv 2.11.1 (independent renderer), Miniforge Python 3.12.
- Scripts: native-17's `bom_cpl_jlc.py` unchanged; `review_fab.py` with one change, below.

## Files (`fab/`)

| File | Content |
| --- | --- |
| `gerbers/` and `native-21-gerbers.zip` | F/In1/In2/B copper, paste, silk (mask subtracted), mask, outline; PTH and NPTH Excellon (mm) with Gerber drill maps |
| `drill-report.txt` | KiCad drill report |
| `bom-jlcpcb.csv` | 92 lines, JLCPCB columns plus manufacturer part number and mount type |
| `cpl-jlcpcb.csv` | 347 placements (34 THT, 313 SMD/other) |
| `positions-kicad.csv` | KiCad's own position export |
| `FAB-NOTE.md` | Order requirements (including filled and capped vias) and deviations |

## Independent review (`scripts/review_fab.py`, `review.json`)

| Check | Result |
| --- | --- |
| Outline | 290 × 190 mm |
| Holes | 852 plated (112 component + 740 via, from each tool's X2 function) and 8 non-plated; the board's census is 112 PTH pads + 740 vias |
| Outer copper around every plated hole, F and B (12 points at drill radius + 0.07 mm) | **852/852 on both sides** |
| Mask opening over every component hole, both sides | 112/112 |
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
python3 validation-results/08-manufacturing-package/native-21/scripts/review_fab.py $O/gerbers validation-results/08-manufacturing-package/native-21/review.json
$KICAD_PY tools/jlc_dfm_check.py $B > validation-results/08-manufacturing-package/native-21/jlc-dfm.json
```

Gerber files embed a creation timestamp, so regenerated files differ in their headers; the zip's
hash is for the committed set.
