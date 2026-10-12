# Controller prototype-lot release (C36)

Branch `controller-release` (from `controller-layout` 1f2dbdb7e). Nothing was ordered, uploaded, logged into or sent. The block validators (Rust) were **not re-run**: the workspace was not built; their expected exact-MPN findings are pre-waived in `../block-validators/WAIVERS.md` (W2 note, W6).

## BOM diff (before = C34 `fab/bom-jlcpcb.csv`, after = this branch): only these 6 lines

```diff
22c22
< B2P-VH(LF)(SN),J13,JST_VH_B2P-VH_1x02_P3.96mm_Vertical,C20571196,B2P-VH(LF)(SN),THT,
---
> B2P-VH(LF)(SN),J13,JST_VH_B2P-VH_1x02_P3.96mm_Vertical,C160315,B2P-VH(LF)(SN),THT,283039
39c39
< RC0603FR-078K06L,R31,R_0603_1608Metric,C131052,RC0603FR-078K06L,SMD,163
---
> RT0603BRD078K06L,R31,R_0603_1608Metric,C861587,RT0603BRD078K06L,SMD,2718
43c43
< RG2012V-431-W-T1,R39,R_0805_2012Metric,C4260028,RG2012V-431-W-T1,SMD,0
---
> RT0805BRD07430RL,R39,R_0805_2012Metric,C865488,RT0805BRD07430RL,SMD,656
49c49
< ERA-3AEB1652V,R53,R_0603_1608Metric,C2074586,ERA-3AEB1652V,SMD,0
---
> RT0603BRD0716K5L,R53,R_0603_1608Metric,C728584,RT0603BRD0716K5L,SMD,18103
70c70
< AD8436BRQZ,U14,QSOP-20_3.9x8.7mm_P0.635mm,C652840,AD8436BRQZ,SMD,0
---
> AD8436ARQZ-R7,U14,QSOP-20_3.9x8.7mm_P0.635mm,C495329,AD8436ARQZ-R7,SMD,106
76c76
< CD74HC30PWR,U22,TSSOP-14_4.4x5mm_P0.65mm,C2866074,CD74HC30PWR,SMD,7
---
> "74HC30PW,118",U22,TSSOP-14_4.4x5mm_P0.65mm,C546857,"74HC30PW,118",SMD,144
```

The last column is JLC stock (2026-10-12 for the swapped lines, from `bom/controller-parts.json`). No other line changed.

## Copper and placement unchanged

`geom_hash.py` (KiCad Python) hashes footprints (ref, layer, position, rotation, library item), pads (position, size, net, layers), tracks, vias, zones (outline and filled polygons) and board drawings, and ignores Value/MPN text. Run on `git show HEAD:pcb/controller.kicad_pcb` (`geom-before.json`) and on the board after `layout/refresh_parts.py`, `build_schematic.py`, a `--refill-zones --save-board` DRC and `fab.py` (`geom-after.json`):

| Class | Count | sha256 (identical before and after) |
|---|---|---|
| footprints | 248 | 50df16bd... |
| pads | 820 | 493e62e9... |
| tracks | 3366 | a189cc59... |
| vias | 901 | 4fce4761... |
| zones (with fills) | 18 | f26e531f... |
| drawings | 26 | eda652a9... |
| **total** | | **971de7e3e867bd735ed15ac364f76d6f8c98cf1e54d41a7cf96089e2244c9bed** |

`diff geom-before.json geom-after.json` is empty. The `.kicad_pcb` text diff is 20 lines (the five footprints' Value/MPN). Every Gerber differs from C34 in its two creation-date lines only. The router was not run.

## CPL rotation audit (`../fab-loose-ends/cpl-rotation/`, DB sha256 fce26b89...3542698)

| Stage | OK | CORRECTED | NEEDS-PREVIEW | Note |
|---|---|---|---|---|
| C35 audit (old board and BOM) | 196 | 15 | 37 | before C34 moves; J13 had no footprint data |
| Re-audit on the C34 board, new BOM, before folding | 197 | 15 | 36 | C31, C18, C51, R43, R44, R45 moved by C34: symmetric passives, class OK; J13 OK with C160315; new EasyEDA footprints fetched for C861587, C728584, C865488, C546857, C495329, C160315 |
| After folding (`fab/cpl-jlcpcb.csv`) | 197 | 15 applied | 36 | `fab/cpl-jlcpcb.csv` is byte-equal (modulo CRLF) to the audit's proposed CPL; the audit now reads KiCad rotation from the board, so re-running it after the fold gives the same counts and `cpl_lines_equal_to_proposed` = 248 |

The fold is `CPL_ROTATION_OFFSET` in `layout/fab.py` (keyed by LCSC code): U5, U6, U7, U15 (+270), U8, U9, U21, U22, U23, U24, U30, U36, U38, U39 (+270), U20 (+180). U22's offset now comes from the Nexperia C546857 footprint (geometry and DB agree, 270). The 36 NEEDS-PREVIEW lines (22 LCSC codes) are listed in `fab/fab-notes.md` for the owner's JLC placement preview; they keep KiCad's rotation. U14 (AD8436ARQZ-R7, QSOP-20) is one of them: geometry says 270, no DB rule.

## Gates

| Gate | Result |
|---|---|
| `tools/verify_controller.py` | VERIFY: PASS (13 sections; frozen netlist sha256 2f5c40d238bed1f67dfe88a3701d25ba4480784209620a033c7ddc5614d98d1f) |
| `tests/test_verify_mutations.py` | 33 passed |
| `tools/freeze.py` | rebuilt with atopile 0.2.69; only the six part names differ in `default.net` |
| `layout/check_layout.py` (KiCad Python) | 12/12 PASS |
| KiCad DRC `--refill-zones --schematic-parity` | 0 errors, 29 warnings (29 at C34), 0 unconnected, parity 0 |
| `layout/jlc_dfm_check.py` | PASS, no failures |
| `layout/review_fab.py` | PASS (no_outer_copper 0, no_mask_opening 0, silk_on_land 0) |
| Block validators | not re-run |

## Fab package

`fab/controller-gerbers.zip` sha256 `9331ee6de5c5e192f582c8d0f38cbce5e7a00d2b60313f38b4fb09085d61938d`; `fab/bom-jlcpcb.csv` `ca5aa070b726eea8fd0aff7f78ce1460217db377ec18631c7243fc0874230b79`; `fab/cpl-jlcpcb.csv` `b575b4d57ce9aa7fe81891a916c1e27e99a576b012b4db2be91a0bc2819f354a`.

## R31 datasheet check (C861587, RT0603BRD078K06L)

Downloaded to the session scratchpad (not committed): Yageo RT series datasheet (the DigiKey-hosted 2004 issue; yageo.com and datasheet.lcsc.com returned 404 or HTML from this network). Its ordering-code table decodes RT0603 B R D 07 8K06 L as 0603, 0.1 % (B), D = +/-25 ppm/C, 8.06 kOhm (E96 code 8K06); the LCSC/JLC description of C861587 reads "8.06k 100mW 75V Thin Film +/-25ppm +/-0.1% 0603". That meets 8.06 kOhm, 1 % or better, 0603, TCR <= 100 ppm. Caveat: the per-part datasheet itself was not retrievable; the match rests on the series ordering-code table plus the distributor listing. Better than the RC part it replaces (1 %, 100 ppm).

## Reproduce

```sh
python3 tools/freeze.py                                   # ato build -> frozen/
KPY layout/refresh_parts.py && python3 layout/build_schematic.py   # fields only; no router
# DRC (make.py step 4), then KPY layout/jlc_dfm_check.py, check_layout.py, fab.py, python3 layout/review_fab.py
KPY evidence/release-proto/geom_hash.py pcb/controller.kicad_pcb   # compare with geom-before.json
```
