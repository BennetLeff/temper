# Native copper current feedback

`make -C zapote check-current` extracts saved filled copper and drill geometry
with KiCad, then runs the conditional `a4-two-terminal.v1` profile in Rust.
It is also part of `make check`. It does not change placement or routing.

```sh
make -C zapote check-current \
  KICAD_PYTHON=/path/to/python-with-pcbnew \
  CURRENT_RUN_DIR=/tmp/current-before

make -C zapote check-current \
  KICAD_PYTHON=/path/to/python-with-pcbnew \
  LAYOUT_BOARD=/absolute/path/to/edited.kicad_pcb \
  CURRENT_RUN_DIR=/tmp/current-after \
  CURRENT_BASELINE=/tmp/current-before/report.json
```

The direct CLI adds `--current-profile a4-two-terminal.v1` to the
[native command](NATIVE.md). Baselines need the same evaluator, extractor and
profile. `comparison.changes` includes conditional resistance and loss deltas.
A failed/missing solve removes the corresponding measurement with null values;
it cannot appear as an improvement to zero. `current.cases` retains the reason.

Exit 0 means all declared numerical experiments completed and met the numerical
checks below. Exit 2 means an invalid input, extraction failure, geometry gap,
solver failure or insufficient resistance refinement. The overall report still
says physical models are incomplete. Neither exit 0 nor a lower R is electrical
acceptance, an ampacity pass or proof of acceptable board temperature.

## Declared experiments

The profile uses the current levels and plating sensitivities of the retained
[A4 study](../power-stage-120v/validation-results/04-board-current-thermal/round3/a4-copper/README.md).
It is a seven-case two-terminal subset, not the complete bridge operating model.
The older study used native-15 and different contact/injection assumptions;
its numerical results are not transferred to native-17.

| Case | Net | Source → sink | Imposed current |
|---|---|---|---:|
| bus-a | bus_p | J8.1 → Q2.2 | 15 A |
| bus-b | bus_p | J8.1 → Q5.2 | 15 A |
| hv-return | hv_ret | R5.4 → J10.1 | 15 A |
| leg-a | leg_ret | Q3.3 → R5.1 | 18.7 A |
| leg-b | leg_ret | Q6.3 → R5.1 | 18.7 A |
| switch-a | sw_a | Q2.3 → T1.1 | 18.7 A |
| coil-feed | coil_feed | T1.2 → J2.1 | 18.7 A |

Each runs at **12 and 18 µm assumed plating**, with mesh maximum triangle areas
of **0.5 and 0.125 mm²**. Copper thickness and layer height come from the saved
stackup (native-17: 70/61/61/70 µm). Resistivity is explicitly 1.724e-8 Ω·m at
20 °C. Plating values are sensitivity assumptions, not vendor-certified minima.
The imposed current is DC; applying I²R to RMS heating requires an applicable
waveform/current-distribution model that this profile does not supply.

## Model and numerical checks

Rust unions actual same-net/layer filled polygons and triangulates each island
separately, retaining holes. Native pad/via boundary vertices prevent small
terminals from disappearing inside large zone triangles. Refinement and total
node budgets fail closed. Polygonization uses the extractor's 1 µm setting;
meshing does not deliberately snap separate boundaries together.

Linear triangular sheet elements solve divergence of sheet conductance times
voltage gradient equal to zero. Diagonally equilibrated sparse Cholesky comes
from `faer`; iterative refinement uses the original current operator. Computing
current and gradients from voltage differences avoids cancellation of large
absolute nodal terms on short, highly conductive edges. The abandoned Jacobi-CG
attempt exhausted its iteration limit on the real board despite passing small
analytical tests; its failed report is retained as development evidence.

Each flashed pad/via annulus is an **ideal equipotential electrode**. Its plated
barrel has finite R between consecutive flashed layers. Round and slotted holes
use the nominal finished-hole perimeter and assumed plating cross-section.
Source/sink terminal contacts, including duplicate physical pads and flashed
layers, are ideal equipotential terminal electrodes. Other same-number physical
pads are not automatically connected through an unmodelled component package.
This model excludes radial annular crowding, lead/contact resistance and solder.
It differs from the older study's equal source-lead injection model.

The solver requires connected source/sink copper. Unconnected same-net islands
are excluded from the solve and counted. Reports include R, total loss, active
and unused nodes, triangle count, every barrel's signed current/loss and
coordinates, and each layer's sampled peak density/location. Peaks are mesh
samples; they are **not converged local maxima or allowable-current verdicts**.

Every accepted solution must meet:

- True KCL residual at all active nodes, including both terminals: ≤1e-6 times
  imposed current.
- Independently integrated sheet/barrel loss versus terminal I·V: relative
  discrepancy <1e-6.
- Relative resistance change between the two mesh sizes: ≤3%.

This is a refinement check, not a rigorous 3% error bound. It does not bound
geometry approximation or physical-model error. Failed cases retain their data
and reasons; resolved R/loss alone enter the before/after metric comparison.

## What the native-17 experiment shows

The [retained run](mesh-evidence/README.md) resolves all 14 cases. Resistance
changes 0.24–1.62% under refinement. At assumed 18 µm plating:

| Case | R, mΩ | Conditional I²R, W |
|---|---:|---:|
| bus-a | 7.352 | 1.654 |
| bus-b | 6.349 | 1.429 |
| hv-return | 3.258 | 0.733 |
| leg-a | 1.452 | 0.508 |
| leg-b | 0.439 | 0.154 |
| switch-a | 4.514 | 1.578 |
| coil-feed | 0.542 | 0.189 |

The A/B leg-return asymmetry is useful evidence when comparing layout edits
under these same boundary conditions. It does not by itself justify a copper
change: actual switching-state currents, contact behavior and thermal paths
still matter. Individual barrel currents also differ; nominal via counts are
not an equal-sharing model.

The remaining software work is complete multiterminal switching-state injection
and time/RMS weighting, annular/lead models, AC effects, mutual/shared inductance,
and thermal transfer. Physical inputs still needed include finished plating,
assembly cooling and adopted waveform/load limits. The current report does not
close the separate five-unit P1 gaps or register full 120 V board acceptance.
