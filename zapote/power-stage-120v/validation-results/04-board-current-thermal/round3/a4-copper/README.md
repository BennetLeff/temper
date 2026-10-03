# A4 board copper solve — native-15, round 3

**Status: electrical A4 numerical work complete for the stated conditional pad-current experiments; operating heating and temperature remain indeterminate.** Evidence class: simulation/model-based. The saved board is `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`. No PCB, placement, source, or shared solver file was changed. This packet extends the historical [round-3 solver correction](../README.md) and retains its results.

## Intake and numerical checks

The [input](inputs/power_copper.json.gz) was extracted from the actual native-15 board with KiCad 10.0.4's bundled Python and the committed round-2 extractor. It has 660 primitives and SHA-256 `521bae736e5cfc58fb9ad00efd6a5942ce184c003c56da5628f0247c1894b765`. A fresh extraction in this worktree produced an identical decompressed payload and identical compressed-file hash ([receipt](outputs/extraction_verify.txt)). Filled-zone holes, effective pad polygons, track widths, physical drill diameters and actual pad centres are carried through the input. Four same-number physical leads on each screw terminal remain four distinct injection/contact sites.

The [kit self-test](outputs/selftest.txt) passes, including the 10 × 50 mm uniform strip at 0.00% resistance error and two joined layers at 0.36% error. The [sim-kit smoke test](outputs/smoke_test.txt) passes with the vendor MOSFET library installed in the local copied kit (library SHA-256 `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`). The repository kit without this ignored vendor input aborts its three switching examples; that missing-input failure is not a copper-solver failure. The copied kit uses the same solver bytes as the committed kit, SHA-256 `0c45e6f602bd06f4d8c85410689e32902824855b58cec76eabe20e2aa8e4f03d`.

At 0.125 mm pitch the [seven-net topology preflight](outputs/topology-p0125.json) finds **zero false joins** and equal raster/physical component counts on every layer. The BUS_P comparison grids at [0.25](outputs/bus-topology-p025.json) and [0.0625 mm](outputs/bus-topology-p00625.json) also have zero false joins and no split physical components. Every one of the 35 current cases passed the separate radial barrel-to-copper contact audit. Energy residuals are below `2.3e-10 W` across the cases ([summary](outputs/summary.json)). Empty vias have eight azimuthal barrel sectors and a drilled void; soldered through-hole leads use one filled barrel node per layer. Vertical resistance includes only the plating, conservatively ignoring lead/solder conduction. Layer thickness is 70/61/61/70 µm, copper resistivity 1.68e-8 Ω·m at 20 °C. Finished plating was varied between 18 and 12 µm as an assumption, not a measured property.

## Current-path experiments

Each [case](run_cases.py) is an independent imposed-current pattern at 0.125 mm pitch. References, physical lead centres, exact source/sink allocation, and all 12/18 µm results are recorded in [cases.json](outputs/cases.json), [summary.json](outputs/summary.json), and the individual case JSONs. Source terminal leads share equally by assumption; equipotential reference sinks share according to the solved network. The HF local capacitor pairs are assigned equal 9.5 A currents; the three tank capacitors are assigned equal thirds of 18.7 A where they are sources. These shares have not been measured.

| Path, 18 µm plating | Imposed drive | R loss-equivalent (mΩ) | Copper heat (W) | Largest empty-via hop (A) | Via flags >3 A |
| --- | ---: | ---: | ---: | ---: | ---: |
| BUS_P J8.1 → Q2.2 | 15 A | 7.922720 | 1.7826 | 8.133 | 4 |
| BUS_P J8.1 + C38/C39 → Q2.2 | 15+19 A | 2.159433 | 2.4963 | 8.133 | 4 |
| HV_RET R5.4 → J10.1 | 15 A | 3.629901 | 0.8167 | 5.836 | 3 |
| HV_RET R5.4 → J10.1 and C38/C39 | 15+19 A | 1.353918 | 1.5651 | 13.798 | 3 |
| LEG_RET Q3.3 → R5.1 | 18.7 A | 1.879512 | 0.6572 | 7.011 | 3 |
| SW_A Q2.3 → T1.1 | 18.7 A | 4.865015 | 1.7012 | 6.271 | 2 |
| SW_B Q5.3 → C21/C22/C23 | 18.7 A | 4.609858 | 1.6120 | 0 | 0 |
| SW_B C21/C22/C23 → Q6.2 | 18.7 A | 5.920871 | 2.0705 | 0 | 0 |
| RES_A C21/C22/C23 → J5.1 | 18.7 A | 0.656658 | 0.2296 | 2.559 | 0 |
| COIL_FEED T1.2 → J2.1 | 18.7 A | 0.825406 | 0.2886 | no empty vias | 0 |

The maximum **sheet-edge** current per millimetre of width and the board coordinate of that edge are recorded for **every layer in every case** as `layer_max_a_per_mm`; the top levels in the table above range from 2.90 A/mm on RES_A/F.Cu to 74.56 A/mm on the coherent HV_RET/F.Cu contact edge. These are grid-local values, often next to a pad or barrel, and are not area-average IPC width limits. The exact per-hop current of **every** barrel, including leads and unused-island `null` statuses, is in [via_currents.json](outputs/via_currents.json); >3 A flags apply only to empty vias. A flag is not a via-rating failure. The current-density maxima themselves have not been shown mesh-converged; the 3% numerical criterion below concerns path resistance.

Four [current-density maps](outputs/current_density_In2_Cu.png) were rendered for the BUS_P coherent A-leg experiment, one on each layer (`current_density_F_Cu.png`, `current_density_In1_Cu.png`, `current_density_In2_Cu.png`, `current_density_B_Cu.png`). They use the kit's centred voltage gradient as a visual aid; the recorded edge-current maxima and coordinates are the quantitative results, especially near pad and barrel boundaries where centred gradients can be undefined.

At 12 µm plating the selected 0.125 mm path resistances increase, relative to 18 µm, by 2.59% for BUS_P J8→Q2, 6.84% for the BUS_P coherent A-leg mixture, 1.33% for HV_RET west return, 4.50% for LEG_RET A, 5.39% for SW_B high-side path, and 0% for COIL_FEED (which uses no empty-via layer transfer on this path). The complete sensitivity and individual barrel sharing changes are in the summary and case files.

The required full BUS_P J8.1→Q2.2 convergence, at 15 A and 18 µm plating, is:

| Pitch (mm) | R (mΩ) | Joule heat (W) |
| ---: | ---: | ---: |
| 0.25 | 8.036539 | 1.808221 |
| 0.125 | 7.922720 | 1.782612 |
| 0.0625 | 7.880150 | 1.773034 |

The full coarse-to-fine spread is **1.985% relative to the fine value**, within the required 3%; the final step is 0.540%. This is a resistance convergence statement, not a convergence proof for local current-density peaks, currents at every via, or temperature.

## B3 thermal handoff and limits

Each scenario JSON references a compressed `<case>-heat.npz` with per-layer `x_mm`, `y_mm`, copper mask, copper thickness and nodal Joule watts. It also contains `barrel_heat_by_layer` at exact board coordinates, including filled-lead and empty-via geometry. **For B3, sum all `*_joule_w` arrays from that NPZ plus every `barrel_heat_by_layer[*].layer_joule_w`; this equals `loss_w` to the recorded energy residual.** Radial annulus loss is split half onto its copper cell and half onto the barrel. `sheet_joule_w + barrel_network_joule_w` is an independent energy audit of the same loss and must not be added to the NPZ heat. All 35 cases retain the node and barrel heat needed to remap onto a 2.5-D thermal grid.

No row in the current-path table is a simultaneous full-board operating state, and their losses must not be summed. The 15 A DC and 19 A HF coherent `34 A` cases deliberately impose one signed overlap to expose shared copper; they are **not** the RMS copper-heating result. Actual mean heat requires the signed pad-current waveforms, local/bulk capacitor sharing and cross-correlation of spatial current fields. Even for a zero-mean HF term, quadrature of scalar current magnitudes alone cannot recover every edge's heat without the field/covariance distribution. The A5 worker reported 26.43676 A tank RMS at cast-iron-low/1710 and 33.722 A in a low-R ideal case where CT trip intervenes; those figures do not identify each capacitor's or mains terminal's pad current. The 18.7 A tank cases here remain the task-04 prescribed assumption and are parameterized by the case script for an A5-informed rerun.

The thermal B3 solve awaits A6 component heat and heat partition plus the missing operating-current covariance. Consequently the task-04 Joule-only 20 °C rise, complete 50 °C-ambient board temperatures, component local ratings and via temperature rise have **no verdict** here. The 35 kHz copper thickness is below the stated ~0.35 mm skin depth, so this DC model is a reasonable resistive-spreading first approximation; it does not include proximity effect or measured fabrication variation. Hardware confirmation remains pad/terminal current sharing and full-power IR or thermocouple temperature rise.

The older IPC-2221 width screens in `native-09/verification/README.md` put the west BUS_P neck at demand/screen 0.457 and the SW_B tank strip at 18.7/25.25 A. This multilayer solve is consistent with their cautions: the west path genuinely shares across layers, but transfer is uneven (8.133 A in one BUS_P via), and SW_B branch direction and capacitor contacts change path loss. IPC screens use a nominal uniform section and a 20 °C rise; they cannot be compared directly to a point-contact edge A/mm peak or used as a temperature verdict.

Reproduce from the unit directory using Miniforge Python with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`: run `validation-plan/sim-kit/04-current/sheet_solver.py --selftest`, the topology script against the input at 0.125 mm, `round3/a4-copper/run_cases.py`, then `round3/a4-copper/summarize.py`. The local copied kit and ignored vendor model under `sim-kit-check/` are retained solely to reproduce the passing smoke test without writing outside this packet.
