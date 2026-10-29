# Rev F before/after: the Rev E circuit on 100 × 100 mm

Rev F is the Rev E circuit (same netlist, same BOM) re-laid from 140 × 105 mm to 100 × 100 mm, so that the enclosure shrinks from about 150 × 115 × 36 mm to about 110 × 110 × 36 mm. The plan and the decisions are in [rev-f-plan.md](rev-f-plan.md).

**Method.** Placement is in `cad/tools/rev_f.py` and the routing is by hand in `cad/tools/rev_f_routes.py`: explicit coordinates and pad references, plus Rev E's own hand routes, carried over by coordinate transform inside five rigid groups. **No autorouter, no path search.** The board is commit `418377699` on `study/lcr-rev-f-100`.

**Verdict.** **Rev F is a viable replacement for Rev E on the evidence below. It is not ordered:** `manufacturing/` is still Rev E on this branch, and the fabrication price is an area-scaled estimate. Every build gate is clean. The extracted node capacitances pass gate G1 (source 11.3 ≤ 13.7 pF, tia 14.0 ≤ 14.7 pF at the high corner). Every loop's worst phase margin over the 360-case matrix is within 0.02° of Rev E or above it (drive +1.04°). The cost is a 5 V trunk three times longer (38 mV at 0.45 A, PASS), and the TIA's C104 loop sits nearer the switcher (+12 dB relative near-field pickup; not a bound). The enclosure footprint shrinks by 30 %.

![Rev E and Rev F at the same scale](../validation/rev-f/before-after.png)

`python3 validation/rev-f/before_after.py` draws this figure from git (Rev E, `48b012771`) and from this tree (Rev F). The KiCad front render of Rev F is `validation/rev-f/pcb-front.svg`; Rev E's is `previews/pcb-front.svg`.

## 1. Build gates

| Check | Rev E | Rev F |
|---|---|---|
| Outline | 140 × 105 mm (147 cm²) | **100 × 100 mm (100 cm²), −32 %** |
| ERC / DRC / unconnected / parity | 0 / 0 / 0 / 0 | **0 / 0 / 0 / 0** (`validation/rev-f/erc.json`, `drc.json`) |
| Vias in SMT lands | 33 exposed-pad thermal vias, tented | the same 33, tented; every via 0.3 mm drill, ≥ 0.45 mm pad (`audit_dfm.py`, `validation/rev-f/via-in-pad-process.json`) |
| Independent check (`independent_check.py`) | 0 findings | **632 pins, 0 findings** |
| OPA2810 bypass, pin to cap pad (U6 C50 / C51, U7 C52 / C53) | 2.05 / 2.03, 2.05 / 2.03 mm | **1.85 / 1.65, 1.80 / 1.77 mm** |
| Codec decoupling; LDO CIN / COUT; CONV_FBP / CONV_FBN | 1.27–3.87 mm; 5.58 / 6.13 mm; 9.1 / 16.1 mm | identical (rigid groups) |
| Switcher to nearest analog IC (centres) | 64.6 mm (D3–U14) | 63.6 mm (D3–U7) |
| U15 → C103 (codec 5VA filter) | about 37 mm | **2.08 mm** |
| C80 (switcher input bulk) → U13 | 16.4 mm | 14.3 mm (plan gate said ≤ 10 mm; amended, see the plan's Decisions) |

Layout audit numbers: `validation/layout-audit-rev-f.json` (`LCR_REV=f <kicad-python> cad/tools/audit_layout.py`).

## 2. Extracted parasitics (gate G1)

`sh validation/layout-parasitics/run_reve.sh revf` exports the board of commit `418377699` (SHA-256 `b583100c…8af7`). It runs 30 FD solves, two at a time: about 18 min wall on this Mac (1085 s, peak about 5 GB per solve). It then writes `extracted_revf.json` and `stability-full-chain/revf_extracted.rs`. The method is the same as Rev E's `reve_bnc`:

- a whole-board solve at 0.2 mm (`revf` window 72 × 51 mm, a plain box, smaller than Rev E's L-domain);
- a thin-prepreg 1080 solve for the high corner;
- grid-convergence zooms on the Rev F features (`fd3d.WINDOWS` `revf_*`: U7, the K1 relay flanks, the DUT_HI/SOURCE_BUF pair, the BNC band, the LCUR corner, the LPOT/LCUR verticals).

Values are in pF to ground, nominal / high, worst range. "Rev F forecast" is phase 1's closed-form estimate.

| Node | Rev E (`reve_bnc`) | Rev F forecast | **Rev F extracted** |
|---|---|---|---|
| source (SOURCE_BUF + selected RG) | 9.38 / 13.72 | 6.69 / 10.05 | **6.07 / 11.29** (G1 ≤ 13.7: PASS) |
| tia (TIA_OUT + selected RF) | 10.21 / 14.70 | 7.35 / 10.59 | **8.03 / 14.01** (G1 ≤ 14.7: PASS) |
| sum (TIA_SUM) | 0.94 / 1.09 | 0.69 / 0.80 | 0.75 / 0.94 |
| sum ↔ tia | 0.225 / 0.345 | | 0.167 / 0.282 |
| low (DUT_LO, LCUR jack included) | 7.45 / 10.89 | 6.08 / 8.88 | **7.74 / 13.71** |
| hi (DUT_HI, HCUR jack included) | 12.93 / 16.49 | 12.21 / 15.58 | 11.81 / **19.09** |
| hpot / lpot | 8.87 / 10.86 nom | 5.83 / 7.25 nom | 4.42 / 5.12 nom |
| tia ↔ unselected RF | 0.90 / 1.11 | | 0.11 / 0.15 |
| srcdrv | 1.28 / 1.55 | 1.03 nom | 0.51 / 0.91 |

**Loop inductance** (free-space "high" value including the OPA2810 package, the value the harness uses):

| Loop | Rev E | Rev F |
|---|---|---|
| RF branch, 100 Ω / 5 kΩ / 100 kΩ | 64.9 / 64.4 / 92.4 nH | **25.5 / 28.2 / 53.3 nH** |
| C104 | 5.04 nH | 3.86 nH |

**Reading the high corner.** The high corner scales the nominal by (1 + U), where U is the grid uncertainty. For Rev F, U is 0.21; Rev E's was 0.12. It is set by the spread of the zoom ratios. The widest ratio is the TIA_OUT–RF100K mutual in the relay zoom: the two In2 buses overlap only about 3 mm inside that window, so their ratio is poorly resolved. Rev F's high corner is therefore more pessimistic than Rev E's in proportion.

- This is largely why DUT_LO and DUT_HI come out above Rev E at the high corner (13.7 vs 10.9 pF and 19.1 vs 16.5 pF), while their nominal values are +4 % and −9 %.
- Both nodes are on the Kelvin current side, and the stability matrix below carries their high values.
- The forecast under-called DUT_LO (8.9 pF high). The routed LCUR path runs from J9 past R106, 17 mm down x 122.6 and 8 mm across to R94, and its zoom grid factor is 1.20 (Rev E 0.93).

## 3. Stability: 360-case matrix on the extracted board

`sh validation/rev-f-floorplan/run_matrix.sh revfcng100 8` (78 s) runs the `kelvincng100` grid on `revf_extracted.rs`: no cable, four 1 m coax, 100–1000 pF lumped, K4 closed, nominal and stress relay sets, three ranges. The tables are `stability-full-chain/matrix-final_revfcng100.md` and `summary-revfcng100.md`. The per-case decks are committed, as Rev E's are.

| Loop, worst of 90 cases | Rev E as built (`kelvincng100`) | Rev F forecast (`revfestcng100`) | **Rev F extracted (`revfcng100`)** |
|---|---|---|---|
| drive (source driver) | 46.83° | 47.87° | **47.87°** |
| TIA | 57.21° | 57.44° | **57.19°** (−0.02°) |
| HIGH follower | 57.05° | 57.33° | **57.56°** |
| LOW follower | 55.89° | 56.92° | **56.71°** |
| min abs(1+T): drive / TIA / LOW | 0.588 / 0.491 / 0.643 | 0.593 / 0.512 / 0.660 | 0.594 / 0.493 / 0.651 |
| Negative-real-axis crossings left of −1 | 0 | 0 | 0 |

- **The TIA is equal, not better.** The forecast gave +0.23°; the extracted board gives −0.02°. The C104 loop inductance fell (5.04 → 3.86 nH), but TIA_OUT's high corner (14.0 pF) is close to Rev E's 14.7 pF, so the TIA loop is unchanged.
- **The drive loop gains 1.04°**, from SOURCE_BUF copper and RF lead inductance, as forecast. The stress relay-contact estimates still set the floor.

**HIGH-follower min abs(1+T): a sampling effect, not a Rev F regression.** The matrix reports 0.221 for Rev F (r5k/r100k, open or matched DUT, 1 m coax, nominal set) against 0.610 for Rev E. The cause is a single-sample dip at 89.13 MHz: the angle of T jumps from −134° to −176° and back. It is a lossless-line resonance of the 1 m HPOT coax, narrower than the matrix's 120-points-per-decade grid (1.9 % steps). `validation/rev-f/resonance_zoom.py` reruns the same deck on a 10 kHz linear grid from 60 to 120 MHz (`validation/rev-f/resonance-zoom.txt`):

| Case (r5k, open, 1 m coax, nominal set), HIGH loop | min abs(1+T) | at |
|---|---|---|
| Rev E as built | **0.189** | 86.97 MHz |
| Rev F extracted | **0.197** | 89.08 MHz |

Resolved, Rev F is slightly better than Rev E. **Rev E's committed 0.610 for this loop was an under-sampled figure:** its dip fell between grid points. The same re-sweep on the drive, TIA and LOW loops (both revisions, the nominal and the worst stress coax case) moves no minimum by more than 0.01, and the TIA's 0.49 is resolved. It is a property of the lossless coax model and the HIGH follower, present on both boards. Real coax loss damps it. It is listed under residual risks.


## 4. Power: 5 V trunk, USB budget

`validation/power-spurs/regulator_check.py`, Rev E from the Rev E tree (`regulator_check.json`), Rev F with `LCR_CPL=../rev-f/cpl-jlcpcb.csv` (`regulator_check-rev-f.json`). Both: **48 PASS, 2 FLAG, 0 FAIL**, the same two FLAGs.

| Row | Rev E | Rev F |
|---|---|---|
| 5 V trunk U16.6 → U13.5/6, least-resistance copper path at 60 °C | 43.1 mΩ over 33.5 mm, 19.4 mV at 0.45 A | **84.2 mΩ over 110.5 mm, 37.9 mV at 0.45 A** |
| TPS65131 VIN minimum (USB 4.75 V worst case, after entry and trunk) | 4.300 V | 4.281 V |
| TPS65131 duty cycle, all corners at 2× load | 0.612–0.780 | 0.612–0.781 (limit 0.875) |
| Inductor current at 2× load | 0.379–0.548 A | 0.381–0.550 A (limit 1.8 A) |
| TPS2553 current limit (R110 24 k ± 1 %) | 0.989 / 1.074 / 1.170 A | unchanged |
| USB input budget | 0.45 A estimate vs 0.5 A Default USB Power | unchanged |
| FLAG: USB unconfigured draw | 0.45 A from attach vs 100 mA (USB 2.0 §7.2.1); firmware declares self-powered | unchanged; layout-independent |
| FLAG: R95/R96 headroom with divider TCR | 0.97 V at the worst corner (≥ 0.6 V dropout, < 1 V PSRR condition) | unchanged |

The trunk is longer than the plan's 99 mm Manhattan estimate (the 1.0 mm B.Cu run follows the bottom edge to clear the digital block), and the plan's 22 mV was at 25 °C on width alone. The check's figure is the least-resistance single path, an upper estimate for the strip model. The 19 mV extra drop moves the converter corner by 0.001 in duty cycle.

## 5. Switcher pickup (relative, not a bound)

`python3 validation/power-spurs/switcher_pickup.py --rev-f ../..` → `switcher_pickup-rev-f.json`. It compares the mutual inductance from the TPS65131 switch loops and L1/L2 into each victim loop, Rev F against Rev E, routed copper on both. **It is a RELATIVE estimate and not a bound**: the absolute leakage of the switcher is unknown, and the In1 plane's shielding, conducted and capacitive paths and the enclosure are not modelled (the same plane on both boards is taken to cancel in the ratio).

| Victim loop | Area Rev E / Rev F (mm²) | Sum of switch loops | L1 / L2 dipole |
|---|---|---|---|
| TIA C104 loop (U7.1–C104–U7.2) | 1.85 / 3.33 | **+12.2 dB** | +12.3 / +12.1 dB |
| TIA RF100K loop (U7.1–K3–R45–U7.2) | 149.6 / 75.4 | +4.3 dB | +4.5 / +2.6 dB |
| Codec ch1 / ch2 input legs | 15.1 / 15.6 (unchanged) | −3.2 / −3.8 dB | −1.7…−5.4 dB |
| U6 EXCITE input | 572 / 2.1 | −42.1 dB | −41.9 / −41.2 dB |
| HPOT input | 588 / 19.9 | −28.8 dB | −28.3 / −28.0 dB |
| LPOT input | 457 / 8.7 | −23.3 dB | −23.5 / −22.2 dB |

The per-source "worst" column in the JSON reaches +33 / +36 dB for the boost on-phase loop into the TIA loops. That source's coupling into these victims is near zero on Rev E (its contributions cancel), so the ratio is large but the absolute term stays small beside the other loops; the summed figure above is the one to read.

What moved: the TIA is about 22 mm nearer the switcher (85 → 63 mm from the boost hot loop), and the C104 loop is larger: U7 is turned 90° from its Rev E pose, and the loop perimeter grows from 6.4 to 8.3 mm (`rev_e_geometry` / `rev_f_geometry` in the JSON). By 1/r³ and area alone that would be about +8 dB (distance) and +5 dB (area). The Kelvin input loops collapse because the jacks now drop straight onto the followers.

**Harmonic collisions** are a property of the frequency plan, not the layout, and are unchanged: with fsw free-running in 1.25–1.50 MHz, a switcher harmonic lands on a test tone with probability 9.1e-4 (8 fs modulator) down to 9.6e-5 (64 fs) per frequency, about twice that at 85 kHz (transition-band image). The near-field ratios above scale the error **if** a collision happens; the source-off check (R-E2) sees a collided line, so it fails a capture rather than biasing it.

## 6. Cost

`<kicad-python> manufacturing/order_estimate.py N` on the Rev F tree reproduces Rev E's committed `order-estimate-2.json` and `order-estimate-5.json` byte for byte: same parts, same lines (23 extended, 39 basic/preferred), same joints. Assembly is unchanged.

| | 2 boards | 5 boards |
|---|---|---|
| JLC standard assembly incl. Rev E fabrication quote ($51.90) | $341.06 | $454.70 |
| JLC hand fit (BNCs) | $16.71 | $31.10 |
| **Rev E total** | **$357.77** | **$485.80** |
| Fabrication, Rev F ESTIMATE (board line × 100/140; ENIG kept or also scaled) | $44.21–49.41 | $44.21–49.41 |
| **Rev F total, ESTIMATE** | **$350.08–355.28** | **$478.11–483.31** |

JLC fabricates at least five boards, so the fabrication line is the same for two. The Rev F fabrication figure is an area scaling of the 140 × 100 mm quote, not a quote: JLC's pricing is tiered. Re-quote at upload. The saving on the board is $2.5–7.7 per order; the real saving is the enclosure.

## 7. Enclosure

| | Rev E | Rev F |
|---|---|---|
| Board | 140 × 105 mm | 100 × 100 mm |
| Enclosure (outside, about) | 150 × 115 × 36 mm | **110 × 110 × 36 mm, −30 % footprint** |
| Mounting holes (M3) | 132 × 92 mm pattern | 92 × 87 mm pattern, same insets |
| BNC centres from the left board edge | 58 / 80 / 102 / 124 mm | 17 / 39 / 61 / 83 mm (same 22 mm pitch and order) |
| USB-C cut-out, centre behind the front (jack) edge | 32 mm, left wall | 77 mm, left wall |

The jacks' 12 mm overhang of the front edge, the panel order (HCUR, HPOT, LPOT, LCUR), the leads and the cal kit do not change.

## 8. Residual risks

1. **HIGH follower near a 1 m coax resonance (both revisions).** With the lossless 1 m HPOT lead model, |1+T| dips to about 0.19–0.20 near 87–89 MHz (T at −172°). Phase margin at the unity crossing is still 57.6°, and nothing encircles −1. The matrix's 120-points-per-decade grid hides the dip on Rev E. Before hardware, rerun the HIGH loop with a lossy coax model, or add a resonance-resolving sweep to `loop_matrix.rs`. This is not caused by Rev F.
2. **Switcher near-field pickup into the TIA** is up by +12.2 dB (C104 loop) and +4.3 dB (RF100K loop), relative to an unknown absolute level. It matters only when a switcher harmonic collides with a test tone (≤ 9.1e-4 per frequency, unchanged). The source-off check catches a collision. If bench spurs show up, the first lever is to shrink the C104 loop (3.3 → about 1.9 mm², as on Rev E) by moving C104 against U7.1/U7.2.
3. **The high-corner parasitics carry a wider grid uncertainty** (U 0.21 vs 0.12; see §2). The matrix is run at that pessimistic corner and passes, so this makes the result conservative, not optimistic.
4. **5 V trunk 110 mm** (84 mΩ at 60 °C, 38 mV at 0.45 A). It passes, with VIN ≥ 4.28 V and duty ≤ 0.781 of 0.875. A 1.5 mm trunk would recover about a third of the drop, if a later revision needs it.
5. **Thermal**: the same 2.3 W in a 30 % smaller box runs warmer. Not evaluated. Calibration-to-use drift and the K4 reference check are the controls, as in the plan.
6. **Not rerun for Rev F** (layout-independent or assumed-strays inputs): `source_stage.py` (U5 strays are assumed values, not extracted), `rev_e_spurs.py`, `rail_monitor_window.py` (same dividers), the accuracy map, and the visual-review receipt.
7. **Fabrication price** is an area scaling. Re-quote at upload. The Rev F Gerbers are not packaged on this branch: run `rebuild.sh` without restoring `manufacturing/` to produce them.

## Reproduce

```sh
cd instruments/lcr-meter
python3 cad/tools/rev_f.py                       # placement + routes -> cad/design.json, cad/routing.json (pre-DRC printed)
LCR_SKIP_ARCHIVE=1 RENDER_PYTHON=true sh cad/rebuild.sh   # ERC/DRC/DFM; then copy evidence to validation/rev-f/ and
git checkout -- manufacturing previews validation/drc.json validation/erc.json validation/via-in-pad-process.json
<kicad-python> validation/independent_check.py f
LCR_REV=f <kicad-python> cad/tools/audit_layout.py
sh validation/layout-parasitics/run_reve.sh revf  # FD extraction -> extracted_revf.json, stability-full-chain/revf_extracted.rs
sh validation/rev-f-floorplan/run_matrix.sh revfcng100 8
cd validation/stability-full-chain && python3 kelvin_summary.py matrix-final_revfcng100.md > summary-revfcng100.md; cd ../..
cd validation/power-spurs && python3 switcher_pickup.py --rev-f ../.. --out switcher_pickup-rev-f.json
LCR_CPL=../rev-f/cpl-jlcpcb.csv LCR_OUT=regulator_check-rev-f.json python3 regulator_check.py; cd ../..
python3 validation/rev-f/before_after.py
```
