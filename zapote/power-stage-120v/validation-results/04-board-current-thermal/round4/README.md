# Task 04 round 4: re-extraction on corrected copper (native-17)

Round-4 review (`round4-coordination/README.md`, D1) found that the
copper exports used by round-3 A4 and B3 counted every pad on every layer
(`IsOnLayer`), including rings KiCad doesn't fabricate. It also turned up
native-15's missing PTH outer lands, fixed in native-17
(`native-17/verification/README.md`). This packet repeats A4 and B3 on
native-17 with a `FlashLayer`-aware export.

- **Board:** `native-17/section.kicad_pcb` (presentation), SHA-256
  `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`;
  copper identical to the electrical record `33fe1cff…`.
- **Exporter:** `tools/export_power_copper.py`. It exports pads and vias
  only where `FlashLayer` is true, unfractures zone holes, and refuses any
  PTH pad without both outer lands; on native-15 it stops at PS2.1. The
  sheet solver subtracts drill bores from the final per-layer union.
- **Evidence class:** simulation/model-based, as in round 3. The same
  imposed-current experiments, not operating waveforms.

## Checks before solving

`round3/scripts/kit_topology_native13.py` on the new export at 0.125 mm
(`reextract/outputs/kit_topology_p0125.json`): 0 grid components span two
physical components, and grid components equal physical components on
every net and layer.

## A4 electrical: all 35 cases (`reextract/`)

Same runner and cases as round 3 (`run_cases.py`, 0.125 mm, 12/18 µm
plating), input swapped. 35/35 completed, 0 uncovered contacts. The full
per-case comparison is in `reextract/outputs/compare_native15_native17.json`.

| Nets | Change vs round 3 (native-15 export) |
| --- | --- |
| BUS_P, HV_RET, LEG_RET, RES_A, COIL_FEED | R within −0.09 % … +0.00 %; peak A/mm and barrel currents unchanged |
| SW_A | R +1.7 % (4.865 → 4.950 mΩ at 18 µm); peak A/mm unchanged |
| **SW_B** | **R +7.5 … +8.0 %** (high-side state 4.610 → 4.972 mΩ; low-side state 5.921 → 6.393 mΩ at 18 µm); **peak 7.5 → 9.8 A/mm and 8.5 → 12.6 A/mm** |

The switch-node pads had unconnected inner rings that the old export
counted as current paths. SW_B's loss rises by about 0.13–0.17 W per case.

**Mains, new in this round** (15 A imposed, 18 µm):

| Case | R | Loss | Highest density |
| --- | ---: | ---: | --- |
| `ac_n_main` J1.2 → L1.2 | 1.609 mΩ | 0.362 W | 7.0 A/mm In2, 6.7 A/mm B.Cu, at the J1.2 exit stub (11.2, 155.9) |
| `ac_l_main` J1.1 → F1.1 | 0.605 mΩ | 0.136 W | 6.6 A/mm F.Cu at J1.1 |

Native-17 narrowed the neutral's B.Cu channel run from 3.6 to 3.0 mm. Its
peak density isn't in that run; it's at the J1.2 exit, as for other
terminals.

## B3 thermal: all eight studies (`reextract-b3/`)

Same thermal model, geometry re-extracted with the new exporter, heat from
the new A4 fields.

| Study | native-15 peak | native-17 peak |
| --- | ---: | ---: |
| BUS_P DC, h 10, 2 / 1 / 0.5 mm | 79.62 / 85.83 / 78.17 °C | 79.78 / 85.95 / 78.23 °C |
| BUS_P DC, h 25, 2 / 1 mm | 70.81 / 77.22 °C | 70.90 / 77.30 °C |
| A6 partial, h 10, 2 / 1 mm | 153.23 / 131.86 °C | 154.01 / 132.66 °C |
| A6 partial, h 25, 2 mm | 128.71 °C | 129.50 °C |

Every peak rises by 0.06–0.8 °C at the same location. **Round 3's
limitation stands:** the peak still moves 7.7 K (BUS_P) and 21.4 K (A6)
with mesh, and the operating heat inputs are incomplete, so these are
conditional observations, not temperatures to use for a decision.

## Not done here

D1's FastHenry board extraction is still blocked on the geometry work its
README lists (finite-width contacts, 1,327 omitted narrow links, the crop
through active planes, mesh size). The new exporter gives it corrected
native-17 input (`reextract-b3/inputs/native17-all-copper.json.gz`), but
the extraction itself isn't attempted in this packet.

## Reproduce (unit root)

```sh
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
MP=/Users/bennet/Miniforge3/bin/python3
R=validation-results/04-board-current-thermal/round4
$KP tools/export_power_copper.py native-17/section.kicad_pcb $R/reextract/inputs/power_copper.json.gz
$MP validation-results/04-board-current-thermal/round3/scripts/kit_topology_native13.py $R/reextract/inputs/power_copper.json.gz $R/reextract/outputs/kit_topology_p0125.json 0.125
OPENBLAS_NUM_THREADS=1 $MP $R/reextract/run_cases.py
OPENBLAS_NUM_THREADS=1 $MP $R/reextract/run_board.py --net ac_n_in --source J1.2:15 --sink L1.2 --pitch 0.125 --plating 18 --name ac_n_main-p0125-pl18
OPENBLAS_NUM_THREADS=1 $MP $R/reextract/run_board.py --net ac_l_in --source J1.1:15 --sink F1.1 --pitch 0.125 --plating 18 --name ac_l_main-p0125-pl18
$KP $R/reextract-b3/extract_geometry.py native-17/section.kicad_pcb $R/reextract-b3/inputs/native17-all-copper.json.gz
MPLCONFIGDIR=/private/tmp/mpl-b3 OPENBLAS_NUM_THREADS=1 $MP $R/reextract-b3/run_study.py
```

Heat-field arrays (`*.npz`) are ignored by git, as in rounds 3–4.
