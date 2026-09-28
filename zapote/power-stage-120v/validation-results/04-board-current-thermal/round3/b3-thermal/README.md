# B3 thermal experiment — native-15, round 3

**Status: numerical pipeline validated; operating board temperature and part-rating verdict blocked by missing operating heat inputs.** Evidence class: conditional simulation. The A4 current paths are independent imposed-current experiments, and A6's map explicitly labels itself partial. No path losses were summed and no 15+19 A coherent case was treated as RMS heating. The historical [round-3 correction](../README.md) and the frozen [A4 copper packet](../a4-copper/README.md) remain separate.

## Source and model

The saved board is `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`, at source revision `44417ae1489fd00e2d652fd3b2c1582b76d17630`. [Native KiCad extraction](extract_geometry.py) used KiCad 10.0.4 and its effective pad polygons, so footprint rotation is not reimplemented. The [frozen geometry](inputs/native15-all-copper.json.gz), SHA-256 `2c78992e8f8be58837bb76fa979e549c9a9f7391084c05b30de3ff4f5c86666e`, has one closed board outline without cutouts and 2,149 primitives across 84 net names, including the unconnected net. It includes **all** board copper nets, not only A4's seven power nets. Filled-zone holes are preserved in the native polygon export.

The [solver](thermal.py) uses seven cell-centred finite-volume sheets: four copper levels and three FR-4 levels. Its thicknesses come from `native-15/stackup.json` (SHA-256 `4022df3f3b96530ece8727e96e523691352234c4ed0de00f0cb93227cc89a37d`): 0.070 / 0.4355 / 0.061 / 0.500 / 0.061 / 0.4355 / 0.070 mm. The solid sum is 1.633 mm; the nominal 1.653 mm board also includes 0.010 mm solder mask on each face. The mask is excluded because its thermal conductivity is unspecified, and convection acts directly on the outer thermal sheet. Copper is 390 W/m·K; FR-4 is 0.3 W/m·K in-plane and through-plane. Copper masks use actual zones, tracks, pads, and via lands; non-copper cells in a copper-level sheet use FR-4. Through-plane conductance uses the two adjacent half-slab resistances in series. The solver also adds 903 axial plated-barrel thermal links from the native pad and via drill census, using the A4 18 µm plating assumption; lead and solder cores are excluded. Drill voids and barrel wall temperature are **not** spatially resolved at these pitches, so these links and copper masks are a coarse thermal representation of the holes.

Both faces convect to a stipulated 50 °C air reservoir at either 10 or 25 W/m²K; edges are insulated. These are boundary assumptions, not measured enclosure airflow or heatsink contact. The 0.5 mm run has 153,600 cells per sheet and 1,075,200 layer nodes; it uses iterative conjugate gradient with a diagonal preconditioner, avoiding a direct factorization. Each receipt records material node counts and heat by layer, all input hashes, runtime versions, peak coordinates, solver residual, and integrated convection balance. The saved Python runtime was 3.12.12 with NumPy 2.4.6, SciPy 1.18.0, and Shapely 2.1.2.

## Independent numerical checks

The [self-test receipt](outputs/selftest.json) precedes the board solve. A uniformly heated 10 × 50 mm, 70 µm one-layer copper strip with 1 W, two-face convection and fixed-temperature ends has an analytic peak rise of 19.211998 K. The solver gives 19.211015 K at 1.0 mm (0.00512% error) and 19.211752 K at 0.5 mm (0.00128% error). A separate seven-layer, one-column test drives 1 W through the native stack with its bottom face fixed: numerical and series-resistance peaks both equal 45.705820513 K to machine precision. Both tests conserve energy; the board runs below close source and integrated convection within 4.7 × 10⁻⁹ W. These checks validate the discretization and energy bookkeeping, not the physical cooling or the unresolved board hotspot.

## Conditional A4 Joule-only result

The selected frozen [A4 BUS_P case](../a4-copper/outputs/bus_dc_q2-p0125-pl18.json) imposes 15 A from J8.1 to Q2.2 and dissipates 1.782612 W in the sheet and barrels together. Each `*_joule_w` array was summed **once** with `barrel_heat_by_layer[*].layer_joule_w`; `sheet_joule_w` and `barrel_network_joule_w` are an audit of the same energy and were not added again. The [0.5 mm receipt](outputs/bus_dc_q2_h10_p0p5.json) verifies the remap against the case's `loss_w` within 1.6 × 10⁻¹⁰ W.

| Face convection | Mesh | Peak at 50 °C ambient | Exact peak location and sheet |
| --- | ---: | ---: | --- |
| 10 W/m²K | 2.0 mm | 79.618 °C | (55.0, 21.0) mm, In2.Cu |
| 10 W/m²K | 1.0 mm | 85.825 °C | (55.5, 22.5) mm, In2.Cu |
| 10 W/m²K | 0.5 mm | 78.170 °C | (54.75, 21.75) mm, In2.Cu |
| 25 W/m²K | 2.0 mm | 70.808 °C | (55.0, 21.0) mm, In2.Cu |
| 25 W/m²K | 1.0 mm | 77.221 °C | (55.5, 22.5) mm, In2.Cu |

The natural-convection local peak spans **7.655 K** over the three meshes and is nonmonotonic. The 0.5 mm [temperature map](outputs/bus_dc_q2_h10_p0p5.png) and [raw fields](outputs/bus_dc_q2_h10_p0p5.npz) therefore document a conditional observation, not a mesh-converged temperature or a 20 °C criterion verdict. At that finest mesh, the largest copper-sheet-centre minus adjacent FR-4-sheet-centre rise is 3.284 K at (54.25, 21.75) mm on In2.Cu. This is a **local board proxy** distinct from the 28.170 K air-relative peak; it does not establish the prescribed copper-above-local-board limit for an operating waveform.

The selected case's largest empty-via hop is 8.133 A at (67.2, 34.0) mm, as A4 already flagged above the 3 A review threshold. At 0.5 mm its nearest thermal board cell reaches 69.424 °C (19.424 K above the assumed air). That is **not** a calculated barrel-wall rise or a rated-via verdict; the barrel links have no independent temperature nodes. The per-via proxies, currents and coordinates are in each A4 thermal receipt.

## Conditional A6 known-component subset

The [frozen A6 input](inputs/a6-board-heat-sources.json), SHA-256 `51b6a94102c1896a9108e6936e245dcb9415623f44a045486f56da2ca3305cd1`, is the named `cast_iron-high-120v-1710w` nominal component scenario. It has 42 positioned parts, but only **11** have quantified nonzero board heat under its assumed fractions; 31 are omitted because their loss, board fraction, or heatsink lead path remains unknown. Its own `use_as_complete_b3_heat_source` flags are false. The [component-only run](outputs/a6_partial_nominal_h10_p1.json) deposits the known 3.628850 W uniformly over each named part's actual native KiCad pad-polygon cells, preferring top copper, and keeps this experiment separate from the A4 BUS_P path. A sub-cell U3 pad uses a disclosed nearest-cell fallback at 2 mm.

| Face convection | Mesh | Conditional peak | Peak location |
| --- | ---: | ---: | --- |
| 10 W/m²K | 2.0 mm | 153.227 °C | (19.0, 109.0) mm, L1 pad region, F.Cu |
| 10 W/m²K | 1.0 mm | 131.863 °C | (27.5, 134.5) mm, L1 pad region, F.Cu |
| 25 W/m²K | 2.0 mm | 128.706 °C | (19.0, 109.0) mm, L1 pad region, F.Cu |

The 10 W/m²K component-subset peak changes **21.364 K** with mesh and even shifts between L1 pad regions. L1's 2.025 W is treated as entirely entering board pads by the A6 assumption; winding/body-to-air conduction and contact resistance have not been established. The [map](outputs/a6_partial_nominal_h10_p1.png) and receipt give each applied wattage and local pad-cell temperature. No capacitor, shunt, driver, isolator, choke, or other **part rating** is evaluated from those pad cells, because package/body and missing heat paths make that comparison unsound.

## Remaining input for an operating verdict

The board needs signed, time-resolved pad currents or an equivalent covariance of the spatial current-field basis over the line and switching cycles. In particular, local versus bulk DC-link capacitor sharing, bridge and mains terminal sharing, both leg-return paths, and resonant capacitor/transformer branches must be tied to the **same** operating state. A5's tank RMS of 26.43676 A at an ordinary 1710 W cast-iron case does not determine these pad-current covariances; rescaling or summing separate A4 paths would fabricate heat. The A6 board source also needs quantified losses for the currently omitted parts and a defensible split of heatsink-part lead heat, package-to-pad contact, and body-to-air paths. Finally, measured enclosure airflow/air temperature, selected heatsink assembly, fabrication plating, and local package rating conditions are needed for physical qualification. Until then there is no full-board peak, Joule-only 20 °C acceptance result, via-barrel temperature, or part-rating PASS/FAIL.

Reproduce from the unit root using KiCad Python for [geometry extraction](extract_geometry.py), then Miniforge Python for [the bounded study](run_study.py):

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 validation-results/04-board-current-thermal/round3/b3-thermal/extract_geometry.py native-15/section.kicad_pcb validation-results/04-board-current-thermal/round3/b3-thermal/inputs/native15-all-copper.json.gz
MPLCONFIGDIR=/private/tmp/mpl-b3 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /Users/bennet/Miniforge3/bin/python3 validation-results/04-board-current-thermal/round3/b3-thermal/run_study.py
```

The [summary](outputs/summary.json) indexes eight case receipts, their PNGs, raw NPZ fields, and both analytic checks. The scripts and artifacts are confined to this B3 directory; board, source, A4, and historical round-3 files were not changed.
