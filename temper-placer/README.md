# temper-placer

JAX-based PCB placement optimizer for the Temper induction cooker.

## Overview

`temper-placer` is a standalone tool for optimizing PCB component placement using
gradient-based optimization in JAX. It encodes expert PCB layout knowledge into
differentiable loss functions.

## Features

- **Gumbel-Softmax discrete rotation** - Differentiable 0°/90°/180°/270° rotation
- **Multi-objective optimization** - Wirelength, overlap, thermal, EMI, congestion
- **Curriculum learning** - Progressive constraint introduction
- **Optimizer Robustness** - Overlap deadlock prevention via:
  - **Soft-Body Inflation**: Ramping component size to avoid early entanglement.
  - **Adaptive Weighting**: Per-component loss balancing for stuck components.
  - **Stochastic Jiggle**: Local minima escape via automated perturbations.
- **Live visualization** - Browser-based training dashboard
- **KiCad integration** - Native file format support via kiutils
- **Validation-in-the-loop** - KiCad DRC and ngspice integration

## Installation

```bash
# With uv (recommended)
uv venv
uv pip install -e ".[dev]"

# With pip
pip install -e ".[dev]"
```

## Usage

```bash
# Basic optimization
temper-placer optimize input.kicad_pcb -c constraints.yaml -o output.kicad_pcb

# With live visualization
temper-placer optimize input.kicad_pcb -c constraints.yaml --visualize

# Run DRC validation
temper-placer validate output.kicad_pcb
```

## Development

```bash
# Run tests
pytest

# Run linter
ruff check src tests

# Type checking
mypy src
```

## Documentation

See [TEMPER_PLACER_DESIGN.md](../TEMPER_PLACER_DESIGN.md) for the full design specification.

## License

MIT
