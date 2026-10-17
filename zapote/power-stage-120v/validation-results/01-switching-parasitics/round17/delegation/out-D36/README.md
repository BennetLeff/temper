# D-36: power board + heatsink + airflow in the R4 enclosure (done by Claude, 2026-10-06)

**Answer: native-20 as laid out does not fit R4, and a re-shaped native-21 does.**
The constraints are R4's front-panel module (y 7–92), the centre-sensor service
corridor (Ø36 mm at (0, 261) plus 3 mm tool margin), the coil-support legs at
(±157, 190/330) and the coil support plate at Z 85. Within them, a 240 × 160 mm
board fits nowhere. A **≤ 290 × 140 mm board fits in the front-middle band**
(x −149…141, y 96…236, board bottom Z ≈ 26), with an **edge sink on its rear
edge, right of the corridor**. That sink models at **0.24 °C/W at 20 CFM and 0.21
at 30 CFM**, inside D-18's 0.29 hard limit. Air enters from the right wall and
exhausts through the rear wall beside the rear mains connector.

Tool: [`validation-plan/enclosure-fit/`](../../../../../validation-plan/enclosure-fit/)
- `board_boxes.py` (CadQuery 2.6.1): one box per populated solid from the KiCad
  STEP. Native-20: 216 solids, Z −14.2 (TO-247s through the board) to +49.6 (C5/C6),
  STEP SHA-256 `67721e2a…`.
- `fit_gate.py --mode native`: searches board rotation × 5 mm position × 1 mm
  height plus an edge sink and a straight duct. **Native-20: 0 placements.**
- `--mode scan`: rectangle envelopes (−14.5…+50 mm about the board bottom) →
  `rect-scan.json`. Two bands: **A** front-middle, up to 290 × 140; **B** rear,
  up to 240 × 150 (x −139…101, y 284…434).
- `--mode plan native21-plan.json`: checks the chosen arrangement box by box
  against every R4 catalog solid, the sensor corridor and R4's own `roof(y)`.
  → `plan-result.json`: **PASS**, plus the sink thermal estimate.

Obstacles are R4 catalog AABBs (conservative), minus the shell and the Oct-2
study's own allocations (old PCB/tray/lid/PS1, compact sink, fan, duct), which
this gate replaces.

## Why band A, not band B

Band B (rear) places connectors next to the rear wall, but the sink has nowhere
to go. In front of the board it crosses the sensor corridor. At the rear wall it
costs about 50 mm of board depth (≈ 240 × 100 left), which is too small for
native-21's 347 parts. Band A keeps a 290 × 140 board (≈ 40,600 mm², above
native-20's 38,400) and gives the sink 114 mm of clear length right of the
corridor. Rear-wall connectors (owner's intent, 2026-10-06) are reached by short
harnesses (≈ 200 mm) from the board's rear edge.

## Sink and fan (model estimates, not bounds; `fit_gate.sink_model`)

Plate fins parallel to the flow: 114 mm flow length, 44 mm fins, 73 mm stack
(Z 10–83, under the coil plate), 1.5 mm fins at 3 mm gap (16 fins), 6 mm base.
The model is Teertstra developing-flow channel Nusselt plus fin efficiency, with
0.03 °C/W spreading allocated:

| Flow | RθSA (sink to local air) | Fin Δp | Channel velocity |
| ---: | ---: | ---: | ---: |
| 20 CFM | 0.243 °C/W | 44 Pa | 4.8 m/s |
| 30 CFM | 0.212 °C/W | 86 Pa | 7.2 m/s |

Against D-18 (50 °C inlet, right → left), the hard limit is 0.29 °C/W at a
1.0 °C/W MOSFET interface, or 0.37 at 0.5 °C/W. **Recommend 30 CFM and an
interface ≤ 0.7 °C/W (AlN + compound).** The 0.15 allocation is not reached by
anything that fits under the coil plate. Fan duty: about 30 CFM at fin
86 Pa + duct bend/grilles (allocate 50 Pa) ≈ 140 Pa. That is beyond a slim
60 × 25 fan's curve; choose a 60 × 38 high-pressure fan or a small blower from
its published curve. The fan is not selected here.

## Constraints handed to native-21 (appended to RELAYOUT-REQUIREMENTS L11–L17)

1. **Outline ≤ 290 × 140 mm**, placed at x −149…141, y 96…236 (R4 frame), board
   bottom Z 26 ± 1 (TO-247 underside ≥ Z 11.5).
2. **All parts ≤ 50 mm above the board bottom** (≤ Z 76; the coil plate is at
   Z 85 over y ≥ 157). C5/C6 at 49.6 mm are the limit; do not grow them.
3. **BR1 + Q5/Q6/Q3/Q2 in one row on the board's REAR edge, within world x
   35…141** (≈ 106 mm; native-20's row spans 150 mm). Order upstream (right)
   → downstream (left): **Q2, Q3, Q6, Q5, BR1**, matching D-18's
   right-to-left flow. Tabs flush with or proud of the edge.
4. **Keep-out behind the rear edge:** sink 114 × 50 × 73 at x 35…149, y 236…284,
   Z 10…83. Nothing else there, and nothing over x −21…21 behind y 236
   (sensor corridor).
5. **Ducts:** inlet x 149…183 from the right wall; exhaust x 35…95 from the sink
   to the rear wall (y 284…438). The rear-wall exhaust grille sits left of the
   mains connector blank (x 101…169).
6. **Connectors:** mains and probe exit the **rear wall**. The board's mains
   entry, coil terminals and J4 belong on or near the rear edge (outside the sink
   span), so harnesses run rearward without crossing the duct.
7. Re-run `fit_gate.py --mode plan` on native-21's own STEP (`board_boxes.py`)
   before release.

## Limits

AABB geometry (conservative for round parts); duct losses allocated, not
modelled; sink thermal is a correlation estimate with no measured curve; no
tolerance stack; the R4 internals themselves (front module, legs, plate) are
taken as fixed. If the owner moves the legs or the sensor corridor, re-run the
scan, since band B may then win.
