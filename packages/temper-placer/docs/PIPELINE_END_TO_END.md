# temper-placer: End-to-End Pipeline Guide

This document describes the high-level flow for running a PCB placement optimization from a raw KiCad design to a legalized, DRC-clean layout.

## 0. Build from Source (Optional)
If you are starting from `atopile` source files (`.ato`), you first need to compile the hardware design into a netlist and sync it to a KiCad PCB.

### Install Atopile
```bash
pip install atopile
```

### Build Hardware
Navigate to the electronics directory and build the project:
```bash
cd elec
ato build
```
This generates the netlist (`default.net`) and other artifacts in `elec/build/`.

### Sync to KiCad
1. Open `pcb/temper.kicad_pcb` in KiCad PCB Editor.
2. Go to **Tools > Update PCB from Schematic...**
3. Select the generated netlist if asked, or ensure the path matches.
4. Click **Update PCB** to pull in new footprints and nets. Components will be placed at (0,0) or default positions.
5. Save the PCB file. It is now ready for optimization.

## 1. Environment Preparation
Ensure you are using the `uv` environment for maximum performance and stability:

```bash
cd packages/temper-placer
uv venv
source .venv/bin/activate
uv pip install -e .
```

## 2. Input Requirements
The pipeline requires two primary inputs:
- **KiCad PCB (`.kicad_pcb`)**: A file containing board outlines and components (initial positions can be random or center-piled).
- **Constraints YAML (`.yaml`)**: Defines zones, group constraints, and layer stackups.

## 3. The Optimization Loop
The core pipeline follows a **Multiphase Gradient Descent** strategy:

1. **Explosion Phase**: High overlap/boundary weights to separate components rapidly.
2. **Refinement Phase**: Balanced weights to optimize wirelength while maintaining separation.
3. **Legalization (NumPy)**: A final geometric projection to snap components to grid and resolve residual collisions.

### Running with CLI
```bash
temper-placer optimize path/to/board.kicad_pcb \
  --config path/to/constraints.yaml \
  --output path/to/optimized.kicad_pcb \
  --epochs 8000 \
  --curriculum
```

### Running with Debug Script (Developer Flow)
For complex benchmarks like `piantor_right`, use the optimized debug script:
```bash
uv run debug_piantor.py
```

## 4. Post-Processing & Validation
After the gradient-based phases, the pipeline automatically runs:
- **Grid Snapping**: Aligns components to the specified manufacturing grid (e.g., 0.5mm).
- **Hard Legalization**: Uses an optimized NumPy-based geometric projection to force zero overlap.
- **Max-Flow Routability Analysis (V6)**: Optionally performs a mathematical feasibility check using the Max-Flow Min-Cut theorem to prove if the current placement is routable. See [ROUTABILITY_ANALYSIS.md](ROUTABILITY_ANALYSIS.md).
- **Plane Integrity Check**: Verifies that ground planes (L2/L3) have not been "cut" by accidental trace placement.

## 5. Inspection
Generate a visual report to verify the result:
```bash
temper-placer report path/to/optimized.kicad_pcb --output report.html
```
Open `report.html` in your browser. Green components are within bounds; Red components indicate residual errors (overlaps or boundary violations).

## 6. Export to KiCad
The `optimized.kicad_pcb` can be opened directly in **pcbnew**. Re-run DRC inside KiCad to confirm final manufacturing clearances.
