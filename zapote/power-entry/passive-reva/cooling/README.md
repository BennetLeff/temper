# Passive GBJ Rev A cooling checkpoint

This directory records the next passive power-entry milestone's cooling work. It applies the
retained GBJ2510-F package study to a concrete cooling arrangement and defines
the evidence required before the arrangement can be called thermally qualified.

The result is **conditional and unqualified**. The numerical model is
replayable, but the bridge loss, package heat paths, installed airflow and
whole-board loss are not bounded by a powered measurement. No PCB, BOM or
fabrication file is changed here.

## Proposed installed arrangement

Use the retained passive GBJ candidate from
`zapote/power-entry/shunt-repair/candidate/`, with the model in
`zapote/power-entry/shunt-repair/bridge-thermal-02/assessment.json`. The
catalogue sources under `zapote/thermal/gbj-study/evidence-01/` support:

* Wakefield-Vette **392-120AB** bonded-fin sink, with the source-bound
  `0.16 K/W at 100 CFM` catalog datum.
* Sanyo Denki **9RA1212E1001** fan, driven from its specified supply. Its
  `120 CFM free-air` and `100 Pa shutoff` values are endpoints, not an
  installed 100 CFM guarantee.
* A mechanically supported bridge-to-sink spreader and electrically safe
  interface. The board and bridge leads must not carry sink or duct loads.
* A duct or plenum whose pressure-flow curve is measured with the actual sink,
  fan, grille and enclosure installed. The target is at least 100 CFM through
  the fin path at the measured operating point.

This deliberately reuses the GBJ study's 392-120AB model boundary. The newer
395-1AB/two-fan concept is not transferred: it is a different sink, fan set and
air path.

## What the retained model says

The GBJ study used the exact bridge geometry and waveform binding, six cases,
96 local Gmsh/Elmer solves, energy residuals below 1 microwatt and mesh/domain
changes below 0.05 K in nominal cases. Its nominal package node is about
80.22 °C and its nominal whole-joint peak is about 84.35 °C under a prescribed
60 °C sink and 80 °C board-cut reservoirs. The weak-assembly case reaches
95.95 °C at the lumped diode node and 117.82 °C at the joint; the fan-loss case
reaches 119.53 °C at the lumped node. These are model sensitivities, not a
worst-case envelope or measurements.

The cooling screen combines a 40 W bridge allowance, 65 W other-PFC allowance
and 5.6 W fan allowance. At the **forced-flow** catalog datum of 0.16 K/W and
the recorded bulk-air-rise calculation it reports 59.64 °C as a conditional
sink temperature. The 0.50 K/W figure is the sink's natural-convection catalog
datum; it cannot be used with the 60 °C forced-flow boundary. At 0.50 K/W,
40 °C inlet and no bulk-air credit, only 40 W total heat reaches a 60 °C sink.
The complete loss budget therefore remains null.

The retained STW65N65DM2AG screen is a separate sensitivity. At 120 Vrms it
reports 112.90–157.44 W of switch-plus-gate loss across assumed 9–11 V gate
points. Those gate points are not measured and the passive baseline does not
yet establish their AUX15V producer. If the screen were representative,
bridge + STW + fan would be 158.50–203.04 W, exceeding the existing 110.6 W
screen by 47.90–92.84 W; this is still not a whole-board total because other
PFC, control and enclosure terms are excluded. The forced-flow calculation would put the sink around
68.1–76.1 °C using the recorded air-rise method. This is not a qualified loss
prediction, but it means the 65 W allowance cannot be treated as established.

The source-bound arithmetic and the required gates are in
[`thermal-budget.json`](thermal-budget.json) and
[`qualification-protocol.md`](qualification-protocol.md). The finite arithmetic
is implemented and tested in [`budget_calc.rs`](budget_calc.rs); it reproduces
the retained 59.639 °C screen before calculating sensitivities.

## Milestone decision

The passive design can proceed to mechanical cooling design and a controlled
prototype qualification. It cannot proceed to “thermally accepted” until the
installed airflow, bridge case/spreader temperature, bridge loss and board
contact temperatures are measured at the required operating points. For the
60 °C shared-budget boundary, the forced-flow target is 0.16 K/W; 0.50 K/W is
the natural-convection catalog datum and is not an acceptance substitute. The
STW sensitivity must not be treated as settled until its gate supply and
switching loss are independently established.
