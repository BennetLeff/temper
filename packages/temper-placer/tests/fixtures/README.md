# Minimal Test Fixtures for temper-placer

This directory contains minimal, hand-crafted KiCad files for testing
the temper-placer IO layer without depending on external project files.

## Files

### minimal_board.kicad_pcb

A minimal PCB with 4 components:
- **R1** (0603 resistor) at (100, 80) - 0° rotation
- **R2** (0603 resistor) at (110, 80) - 90° rotation  
- **C1** (0603 capacitor) at (105, 90) - 0° rotation
- **U1** (SOIC-8 IC) at (120, 85) - 180° rotation

Nets:
- GND (power)
- VCC (power)
- SIG1 (signal)
- SIG2 (signal)

Board dimensions: 50mm x 30mm (from 90,70 to 140,100)

### constraints_minimal.yaml

Placement constraints matching the minimal board:
- Board dimensions and origin
- Zone definitions
- Component groups
- Net class weights
- Optimization parameters

## Usage

These fixtures are designed to be self-contained and version-controlled.
They should work on CI without requiring the full Temper project files.

```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
pcb_path = FIXTURES / "minimal_board.kicad_pcb"
constraints_path = FIXTURES / "constraints_minimal.yaml"
```

## Design Principles

1. **Minimal size** - Just enough to test key features
2. **Hand-written** - Not exported from KiCad, so predictable format
3. **Complete** - Covers footprints, nets, layers, zones
4. **Self-documenting** - Component names/values indicate purpose
