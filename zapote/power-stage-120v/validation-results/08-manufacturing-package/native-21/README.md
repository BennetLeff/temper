# 08 Manufacturing package: native-21 candidate

A **candidate** JLCPCB package for native-21 (stage 19b), reviewed independently of KiCad. It
does not release fabrication: `DECISIONS.md` controls that, and its gates are open
([fab/FAB-NOTE.md](fab/FAB-NOTE.md)).

- Board: native-21 stage 19b (stage 19 + transfer caps C153-C156 at pwm_hb, item 19b; stage 19 was stage 18 + converter-local caps at U41 / U42 / U26, bus_fault_hot along its Kelvin return, ct_zc / pwm_hb re-laid, comparator / monitor bypass caps beside their ICs; DECISIONS item 19, `stage19-pi-si/`; stage 18 was stage 17b + the SELV LINE_ZC_RAW / V15_SELV B.Cu runs re-laid ≥ 12.6 mm from RES_A, DECISIONS item 18, `stage18-res-a-creepage/`; 17b was stage 16 + R5 = Bourns CSS2H-2512R-1L00F on a Kelvin land + declared pour priorities, item 17 / 17b), SHA-256
  `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662`; Gerber ZIP `c9eaf0d96091662cd25d0ef5a2d78e972f6123e1a1b4cb1c6d85804922e80ea3`.
- Tools: KiCad 10.0.4 `kicad-cli`, gerbv 2.11.1 (independent renderer), Miniforge Python 3.12.
- Scripts: native-17's `bom_cpl_jlc.py` (stage 17: an SMD part with paste-free pads takes its centroid from the pasted pads, so R5's sense fingers do not shift it; no other placement moved); `review_fab.py` with one change, below.

## Files (`fab/`)

| File | Content |
| --- | --- |
| `gerbers/` and `native-21-gerbers.zip` | F/In1/In2/B copper, paste, silk (mask subtracted), mask, outline; PTH and NPTH Excellon (mm) with Gerber drill maps |
| `drill-report.txt` | KiCad drill report |
| `bom-jlcpcb.csv` | 92 source lines plus the F1 clip line, JLCPCB columns plus manufacturer part number, mount type and assembly route (`scripts/apply_lcsc.py`) |
| `cpl-jlcpcb.csv` | 357 placements (38 THT, 319 SMD/other); pad-centre centroids |
| `assembly-drawing.pdf` | F.Fab (every designator), silk and outline, A4 fit (review M12) |
| `positions-kicad.csv` | KiCad's own position export |
| `FAB-NOTE.md` | Order requirements (including filled and capped vias) and deviations |

## Independent review (`scripts/review_fab.py`, `review.json`)

| Check | Result |
| --- | --- |
| Outline | 290 × 190 mm |
| Holes | 873 plated (120 component incl. 4 F1 slots + 753 via) and 15 non-plated; the board's census is 120 PTH pads + 753 vias |
| Outer copper around every plated hole, F and B (12 points at drill radius + 0.07 mm) | **869/869 round holes on both sides.** The 4 F1 slots (G85) are outside the script's parser and were checked in the drill file |
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
