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

## Performance

`temper-placer` is highly optimized using JAX JIT-compilation and vectorized operations.

### Benchmarks (CPU - M1 Pro)

Typical optimization times for 8,000 epochs with all loss functions enabled:

| Components | ms/epoch | Total (8k epochs) |
|------------|----------|-------------------|
| 50         | ~0.57ms  | ~4.5s             |
| 100        | ~0.68ms  | ~5.4s             |
| 200        | ~1.17ms  | ~9.4s             |

*Note: Initial run includes JAX compilation time (usually 2-5 seconds).*

### Memory Usage

Memory scales quadratically with component count due to pairwise distance matrices, but uses chunking for $N \ge 50$ to maintain a linear-ish profile for common designs.

| Components | Expected Peak RAM |
|------------|-------------------|
| 50         | < 500MB           |
| 100        | < 1.0GB           |
| 200        | < 2.0GB           |
| 500        | < 4.0GB           |

### CPU vs GPU Performance

- **CPU (Apple M-series/Modern x86)**: Excellent for designs up to 200 components. JAX leverages AMX/AVX instructions for high throughput.
- **GPU (NVIDIA/Metal)**: Recommended for $N > 500$. Expect 5-10x speedup on overlap and wirelength calculations. For small designs, the overhead of host-to-device transfers may make CPU faster.

### Optimization Tips

- **Curriculum Stages**: Reduce epochs in early curriculum stages (e.g., 500 instead of 2000) to speed up initial coarse placement.
- **Selective Loss**: Disable expensive losses like `CongestionLoss` or `ThermalLoss` during early exploration if they are not critical.
- **Device Specification**: Use `--device gpu` to force execution on a specific accelerator if JAX doesn't auto-detect it correctly.
- **Chunk Size**: For very large designs, adjust `overlap_chunk_size` in the config to balance memory vs speed.

## Documentation

See [TEMPER_PLACER_DESIGN.md](../TEMPER_PLACER_DESIGN.md) for the full design specification.

## License

MIT
