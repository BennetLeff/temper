# Native-06 filled-copper power-path review

Input `/tmp/ps-finish/final49/section.kicad_pcb`, SHA-256 `500cdb4b9f3491bfed2535099ad0ed2a59a461f12dd79a7aeedae18014b0f3fe`. This **supersedes final46** after the terminal-hardware clearance fixes. It is a prototype routing/current **screen**, not a continuous-current, thermal, fabrication, or electrical-safety qualification. The approved design basis is 240 × 160 mm and four layers; the stackup proposes nominal 70 µm copper on every layer and a nominal 1.6 mm board.

## Exact-board checks

- KiCad 10.0.4 DRC `/tmp/ps-finish/final49-fill-drc.json`: 0 copper violations, 28 footprint-library mismatches, 3 silkscreen overlaps, one intended `leg_ret` open across the R5 current/Kelvin separation, and no schematic-parity mismatch.
- Rust all-layer 8.0 mm barrier output `/tmp/ps-finish/final49-review/barrier.json`: 0 violations and 0 cross-layer hits. The copper dump reports the matching board hash, 114 footprints, 333 pads, 560 tracks, 141 vias, 24 zones, and 30 filled polygons.
- Direct KiCad filled-zone scan `/tmp/ps-finish/final49-review/zones-holes.json`: 30 polygons and **0 holes**. This matters because the copper dump fills holes in its polygon approximation; that known limitation does not affect this board's sampled zone widths.
- Pad-only KiCad connected-items receipt `/tmp/ps-finish/final49-review/connectivity.json`: one component each for `bus_p` (19 copper pads), `hv_ret` (15), and `sw_b` (12). Only `leg_ret` has two components, with R5 pad 1 in the power-current component and R5 pad 2 in the Kelvin component. Pad-only grouping avoids the prior false closure from one filled-zone UUID containing disconnected polygons.

## Filled-path and current screen

The comparison uses the repo's Rust IPC-2221B forward formula (`packages/temper-geometry/src/trace_width_assignment.rs:118–143`): `I = k × ΔT^0.44 × A^0.725`, k=.024 for inner copper or .048 for outer copper, `A=width_mils × (2 oz × 1.37 mils)`, with a 20 °C rise. Treating nominal 70 µm as 2 oz is an assumption; the formula is a rough width screen, not this board's temperature prediction.

| Path | Filled section / modeled demand | Nominal screen and limit |
| --- | --- | --- |
| `BUS_P` In2 local row | A 0.3 mm-grid DC sheet solve over x110–150, scaled to an assumed 19 A, puts 5.86 A in the upper 3.197 mm branch at x125.75/y11.23–14.43; other branches take 10.07 and 3.07 A at x131.5. | The upper branch screens 6.20 A, ratio **0.945**. That narrow margin depends on assumed current splitting and nominal copper. |
| `BUS_P` western In2 | The **actual sampled minimum is 11.6995 mm** at x73.9/y0.6–12.2995; the single upper strip broadens to 13.65 mm near x84. The B.Cu lower branch stops near x69 and must not be added in parallel at x73.9. | 15.88 A at the minimum versus approximately 15 A rectifier replenishment demand: only ~6% nominal margin. The true RMS waveform is unknown, and this section must not be assigned all 19 A local HF circulation without a circuit model. |
| `HV_RET` In1 | An In1-only 0.25 mm-grid DC sheet solve scaled to 15 A gives a 0.899 mm sliver at x88.375/y25.80–26.70 carrying 2.63 A. | The isolated inner sheet screens 2.47 A there, ratio **1.064**. This is why the separate F.Cu bypass is necessary; omitting it understates the route, while calling the inner copper alone adequate would be wrong. |
| `HV_RET` F bypass | A continuous 5.0 mm F.Cu strap runs x83.5→90.0 at y29.9, with three 1.6/0.8 mm through-vias at each end. KiCad places both ends in the one connected `hv_ret` pad component. | The outer copper screens 17.15 A **if all** 15 A replenishment takes the strap. Via-bank capacity and real current sharing are not established by that width formula. |
| `SW_B` B.Cu tank path | The connected main tank strip x125–180/y20–39 narrows to **8.4995 mm** at x153.1–153.3; isolated side pockets are excluded. | 25.20 A nominal outer-layer screen versus the stated 18.7 A line-average tank RMS. The 26 A line-crest is transient and requires waveform/thermal treatment. |

The two sheet solves use ideal equipotential rectangle edges and nominal DC copper resistance. They omit real pad/via injection, layer coupling, AC effects, temperature, and tolerances. Their branch flows are diagnostic, **not** measured currents. The scripts and outputs are `/tmp/ps-finish/final49-review/final49-bus-sheet.py`, `bus-sheet.txt`, `final49-hv-sheet.py`, and `hv-sheet.txt`. The independent zone-section/via script and JSON are `geometry_via_screen.py` and `geometry-via.json` in the same directory.

## Via sharing limits

The BUS_P B↔In2 transfer bank now has **two upper** vias (67.2,32.2) and (67.2,34.0), **two middle** vias (68.5,47.0/48.8), and **four lower** vias (68.5,53.0/54.8/56.6/58.4). All eight are nominal 1.6 mm diameter/0.8 mm drill per pcbnew (`bus-via-pcbnew.txt`), and the filled-zone geometry contains every via center on both In2.Cu and B.Cu (`bus-via-zone-contact.txt`). The lower and middle vias do not prove that the upper two share current equally or that they avoid a local upper-branch concentration. A pessimistic thought experiment putting the entire 15 A through those **two** upper vias yields 7.5 A each; 19 A yields 9.5 A each. At assumed 15 µm finished barrel plating and pessimistic full 1.6 mm barrel length, each via is about 0.700 mΩ and dissipates respectively ~39 or ~63 mW. At 10 µm plating it is ~1.056 mΩ and ~59 or ~95 mW. These are resistance sensitivities, **not via current ratings**; actual In2-to-B barrel length is shorter, while spreading, nonuniform sharing, finished-hole size, and thermal coupling remain unknown. Do not claim the eight vias form one uniform 8-via bank.

The HV_RET F bypass's six 1.6/0.8 mm vias remain three per end; all six centers contact the filled In1 HV_RET zone (`hv-via-zone-contact.txt`). With hypothetical 15 µm plating, a full 15 A evenly split gives 5 A/via, ~17.5 mW/via, and ~0.779 mΩ/~0.175 W for both via banks plus the 6.5×5.0×0.07 mm strap. At 10 µm plating the corresponding full-path sensitivity is ~1.016 mΩ/~0.229 W. This does not establish finished-via temperature or a continuous rating.

## Reproduction and remaining evidence

The review scripts and outputs are all under `/tmp/ps-finish/final49-review/`; they are scratch evidence that can be copied to the canonical review packet. Use KiCad's bundled Python to run `copper_zones_with_holes.py` and `connectivity-receipt.py`, and `/Users/bennet/Miniforge3/bin/python3` for the Shapely/Scipy screens. DRC must include the board's sibling `section.kicad_dru`, `section.kicad_pro`, `fp-lib-table`, and `candidate-libs`; a board-only run can silently misreport library and creepage checks.

Before fabrication or energized operation, obtain fabricator minimum **finished** copper and via plating, measure branch/current waveforms and assembled-board temperature rise, verify turn-off overshoot and the bus clamp, and close the outstanding insulation/certification evidence. This review does not claim those tests were performed.

The coordinator preserved these review probes and outputs under [power-probes](power-probes/). Absolute scratch paths above are historical provenance. The canonical board is `../section.kicad_pcb` and the main copper census is `copper.json`; all carry the same full board hash. These one-shot diagnostic models are not production engineering validators.
