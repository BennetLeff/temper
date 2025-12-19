# temper-placer Usage Guide

This guide covers installation, basic usage, and detailed command reference for temper-placer.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Configuration File](#configuration-file)
- [Troubleshooting](#troubleshooting)

---

## Installation

### Requirements

- Python 3.10 or higher
- pip or uv package manager

### Standard Installation

```bash
# Clone the repository
git clone https://github.com/temper-project/temper.git
cd temper/temper-placer

# Install with pip
pip install -e ".[dev]"

# Or with uv (faster, recommended)
uv venv
uv pip install -e ".[dev]"
```

### Dependencies

The following packages are automatically installed:

| Package | Version | Purpose |
|---------|---------|---------|
| `jax` | >=0.4.20 | Automatic differentiation and optimization |
| `jaxlib` | >=0.4.20 | JAX backend |
| `optax` | >=0.1.7 | Gradient-based optimizers |
| `kiutils` | >=1.4.0 | KiCad file parsing |
| `numpy` | >=1.24.0 | Numerical operations |
| `pyyaml` | >=6.0 | Configuration file parsing |
| `plotly` | >=5.18.0 | Interactive visualizations |
| `websockets` | >=12.0 | Live visualization server |
| `click` | >=8.1.0 | CLI framework |
| `rich` | >=13.0.0 | Terminal output formatting |

### GPU Acceleration (Optional)

For NVIDIA GPU support, install with CUDA:

```bash
# Install with CUDA 12 support
pip install -e ".[gpu]"

# Or manually install JAX with CUDA
pip install jax[cuda12_pip]
```

**Note:** GPU acceleration requires:
- NVIDIA GPU with CUDA support
- CUDA 12 and cuDNN installed
- See [JAX GPU installation guide](https://github.com/google/jax#installation) for details

### macOS Notes

On Apple Silicon (M1/M2/M3), JAX uses the Metal backend automatically:

```bash
# JAX on Apple Silicon works out of the box
pip install -e ".[dev]"
```

### Linux Notes

On Linux, the default CPU installation works everywhere. For GPU:

```bash
# Check CUDA version
nvcc --version

# Install matching JAX version
pip install jax[cuda12_pip]  # For CUDA 12
```

### Windows Notes

Windows is supported but less tested. WSL2 is recommended for GPU support:

```bash
# In WSL2 Ubuntu
pip install -e ".[dev]"
```

### Development Installation

For contributing to temper-placer:

```bash
# Clone and install in development mode
git clone https://github.com/temper-project/temper.git
cd temper/temper-placer
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests to verify installation
pytest
```

---

## Quick Start

### 5-Minute Tutorial

This tutorial walks through optimizing a PCB placement from start to finish.

#### Step 1: Prepare Your Files

You need two files:
1. **KiCad PCB file** (`.kicad_pcb`) - Your board with components
2. **Constraints YAML** - Placement rules and zones

#### Step 2: Create a Constraints File

Create `constraints.yaml`:

```yaml
board:
  width_mm: 100
  height_mm: 80
  margin_mm: 3

zones:
  - name: main
    bounds: [0, 0, 100, 80]
    net_classes: [Signal, Power]

groups:
  - name: decoupling
    components: [C1, C2, C3, C4]
    max_spread_mm: 15
```

#### Step 3: Run Optimization

```bash
temper-placer optimize board.kicad_pcb \
  -c constraints.yaml \
  -o optimized.kicad_pcb \
  --epochs 4000
```

#### Step 4: View Results

```bash
# Visualize the result
temper-placer visualize optimized.kicad_pcb

# Or generate a report
temper-placer report optimized.kicad_pcb -o report.html
```

#### Step 5: Open in KiCad

Open `optimized.kicad_pcb` in KiCad to see the optimized placement.

### Example Workflow for Temper Board

```bash
cd temper/temper-placer

# Check the input PCB
temper-placer info ../pcb/temper.kicad_pcb

# Validate before optimization
temper-placer validate ../pcb/temper.kicad_pcb \
  -c ../configs/temper_constraints.yaml

# Run optimization (this may take several minutes)
temper-placer optimize ../pcb/temper.kicad_pcb \
  -c ../configs/temper_constraints.yaml \
  -o output/temper_optimized.kicad_pcb \
  --epochs 8000 \
  --checkpoint output/checkpoint.json \
  --placements-json output/placements.json

# Generate report
temper-placer report output/temper_optimized.kicad_pcb \
  -o output/report.html
```

---

## CLI Reference

### Global Options

```
temper-placer --version    Show version and exit
temper-placer --help       Show help and exit
```

### Commands Overview

| Command | Description |
|---------|-------------|
| `optimize` | Run placement optimization |
| `validate` | Pre-flight validation checks |
| `export` | Apply placements to PCB |
| `info` | Show PCB information |
| `report` | Generate HTML report |
| `visualize` | Interactive PCB visualization |
| `version` | Show version info |

---

### optimize

Run gradient-based placement optimization.

```bash
temper-placer optimize INPUT_PCB -c CONFIG -o OUTPUT [OPTIONS]
```

**Arguments:**
- `INPUT_PCB` - Input KiCad PCB file (required)

**Required Options:**
- `-c, --config PATH` - Constraints YAML file
- `-o, --output PATH` - Output KiCad PCB file

**Optional:**
| Option | Default | Description |
|--------|---------|-------------|
| `-n, --epochs INT` | 8000 | Number of optimization epochs |
| `-v, --visualize` | off | Enable live browser visualization |
| `--port INT` | 8080 | Port for visualization server |
| `--seed INT` | 42 | Random seed for reproducibility |
| `--checkpoint PATH` | - | Save checkpoint JSON file |
| `--curriculum/--no-curriculum` | on | Use curriculum learning |
| `--placements-json PATH` | - | Also save placements as JSON |

**Examples:**

```bash
# Basic optimization
temper-placer optimize board.kicad_pcb -c constraints.yaml -o output.kicad_pcb

# With checkpointing and JSON export
temper-placer optimize board.kicad_pcb \
  -c constraints.yaml \
  -o output.kicad_pcb \
  --checkpoint checkpoint.json \
  --placements-json placements.json

# Faster optimization (fewer epochs)
temper-placer optimize board.kicad_pcb \
  -c constraints.yaml \
  -o output.kicad_pcb \
  --epochs 2000

# Reproducible run with specific seed
temper-placer optimize board.kicad_pcb \
  -c constraints.yaml \
  -o output.kicad_pcb \
  --seed 12345
```

---

### validate

Run pre-flight validation checks before optimization.

```bash
temper-placer validate INPUT_PCB [OPTIONS]
```

**Arguments:**
- `INPUT_PCB` - Input KiCad PCB file (required)

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `-c, --config PATH` | - | Constraints YAML (for constraint validation) |
| `--tools/--no-tools` | on | Check external tool availability |
| `--zones/--no-zones` | on | Check zone assignments |
| `--constraints/--no-constraints` | on | Check for impossible constraints |
| `--drc/--no-drc` | off | Run KiCad DRC (requires kicad-cli) |
| `--strict` | off | Treat warnings as errors |
| `--json-output` | off | Output results as JSON |

**Exit Codes:**
- `0` - All checks passed
- `1` - Errors found

**Examples:**

```bash
# Basic validation
temper-placer validate board.kicad_pcb -c constraints.yaml

# Check only external tools
temper-placer validate board.kicad_pcb --tools --no-zones --no-constraints

# Run DRC validation
temper-placer validate board.kicad_pcb --drc

# Strict mode (fail on warnings)
temper-placer validate board.kicad_pcb -c constraints.yaml --strict

# Machine-readable output
temper-placer validate board.kicad_pcb --json-output
```

---

### export

Apply a placements JSON file to a template PCB.

```bash
temper-placer export -p PLACEMENTS --pcb TEMPLATE -o OUTPUT
```

**Required Options:**
- `-p, --placements PATH` - Placements JSON file
- `--pcb PATH` - Template KiCad PCB file
- `-o, --output PATH` - Output KiCad PCB file

**Examples:**

```bash
# Apply placements to template
temper-placer export \
  -p placements.json \
  --pcb template.kicad_pcb \
  -o output.kicad_pcb
```

---

### info

Display information about a KiCad PCB file.

```bash
temper-placer info INPUT_PCB
```

**Examples:**

```bash
temper-placer info board.kicad_pcb
```

**Output includes:**
- Component count
- Net count
- Board dimensions
- Layer information

---

### report

Generate an HTML report for a placed PCB.

```bash
temper-placer report INPUT_PCB -o OUTPUT [OPTIONS]
```

**Arguments:**
- `INPUT_PCB` - Input KiCad PCB file (required)

**Required Options:**
- `-o, --output PATH` - Output HTML file

**Optional:**
| Option | Default | Description |
|--------|---------|-------------|
| `--loss-history PATH` | - | Loss history JSON from optimization |
| `--title TEXT` | - | Report title |
| `--no-board/--board` | show | Include board visualization |
| `--no-components/--components` | show | Include component table |

**Examples:**

```bash
# Basic report
temper-placer report optimized.kicad_pcb -o report.html

# With loss curves from optimization
temper-placer report optimized.kicad_pcb \
  -o report.html \
  --loss-history losses.json \
  --title "Temper Board Placement Report"
```

---

### visualize

Generate interactive HTML visualization of a PCB.

```bash
temper-placer visualize INPUT_PCB [OPTIONS]
```

**Arguments:**
- `INPUT_PCB` - Input KiCad PCB file (required)

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `-o, --output PATH` | - | Output HTML file (opens browser if not set) |
| `--title TEXT` | - | Visualization title |
| `--no-refs/--refs` | show | Show component references |
| `--no-zones/--zones` | show | Show board zones |
| `--show-traces/--no-traces` | show | Show copper traces |
| `--show-pads/--no-pads` | show | Show component pads |
| `--debug` | off | Print coordinate debug info |
| `--grid/--no-grid` | show | Show coordinate grid |
| `--width INT` | - | Figure width in pixels |
| `--height INT` | - | Figure height in pixels |
| `--export-coords PATH` | - | Export coordinates to CSV |

**Examples:**

```bash
# Open visualization in browser
temper-placer visualize board.kicad_pcb

# Save to HTML file
temper-placer visualize board.kicad_pcb -o board.html

# Simplified view (no traces or pads)
temper-placer visualize board.kicad_pcb --no-traces --no-pads

# Export coordinates for external comparison
temper-placer visualize board.kicad_pcb --export-coords coords.csv
```

---

## Configuration File

The constraints YAML file defines placement rules, zones, and optimization parameters.

### Complete Example

```yaml
# Board geometry
board:
  width_mm: 100      # Board width in millimeters
  height_mm: 150     # Board height in millimeters
  margin_mm: 3       # Minimum distance from board edge

# Placement zones
zones:
  - name: HV_ZONE
    bounds: [0, 0, 50, 80]        # [x, y, width, height] in mm
    net_classes: [HighVoltage, Power]
    
  - name: LV_ZONE
    bounds: [50, 0, 100, 80]
    net_classes: [Signal, Power]
    
  - name: MCU_ZONE
    bounds: [0, 80, 100, 150]
    net_classes: [Signal]
    components: [U1, U2]          # Specific components for this zone

# Ground domains (for star grounding)
ground_domains:
  - name: ANALOG_GND
    bounds: [0, 0, 50, 80]
    star_point: [25, 40]          # Star ground connection point
    
  - name: DIGITAL_GND
    bounds: [50, 0, 100, 80]
    star_point: [75, 40]

# Clearance rules between net classes
clearances:
  - from: HighVoltage
    to: Signal
    clearance_mm: 10
    description: "HV to signal clearance for safety"
    
  - from: HighVoltage
    to: Power
    clearance_mm: 5

# High-voltage clearance default
hv_clearance_mm: 8.0

# Critical current loops to minimize
critical_loops:
  - name: gate_drive_high
    nets: [GATE_H, SW_NODE, VCC_15V]
    max_area_mm2: 100
    weight: 2.0
    description: "High-side gate drive loop"
    
  - name: gate_drive_low
    nets: [GATE_L, GND, VCC_15V]
    max_area_mm2: 100
    weight: 2.0

# Thermal constraints
thermal:
  - components: [Q1, Q2]          # Power MOSFETs
    prefer_edge: true             # Place near board edge
    min_spacing_mm: 10            # Minimum spacing between them
    max_distance_from_edge_mm: 15
    
  - components: [U3]              # Voltage regulator
    prefer_edge: true
    min_spacing_mm: 5

# Component groups (place together)
groups:
  - name: mcu_decoupling
    components: [U1, C1, C2, C3, C4]
    max_spread_mm: 20
    zone: MCU_ZONE
    description: "MCU and bypass capacitors"
    
  - name: gate_driver_high
    components: [U2, R1, R2, C5]
    max_spread_mm: 15
    zone: HV_ZONE

# Net importance weights (higher = more important to minimize length)
net_weights:
  GATE_H: 3.0
  GATE_L: 3.0
  SW_NODE: 2.0
  VCC: 0.5
  GND: 0.5
```

### Field Reference

#### board

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width_mm` | float | 100.0 | Board width in mm |
| `height_mm` | float | 150.0 | Board height in mm |
| `margin_mm` | float | 3.0 | Minimum edge margin |

#### zones

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Zone identifier |
| `bounds` | [x, y, w, h] | yes | Zone rectangle in mm |
| `net_classes` | list | no | Allowed net classes |
| `components` | list | no | Specific components for zone |

#### clearances

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `from` | string | yes | Source net class |
| `to` | string | yes | Target net class |
| `clearance_mm` | float | yes | Required clearance |
| `description` | string | no | Human-readable note |

#### critical_loops

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Loop identifier |
| `nets` | list | yes | Nets forming the loop |
| `max_area_mm2` | float | no | Maximum loop area |
| `weight` | float | no | Optimization weight (default: 1.0) |

#### thermal

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `components` | list | required | Component refs |
| `prefer_edge` | bool | true | Place near board edge |
| `min_spacing_mm` | float | 5.0 | Min spacing between |
| `max_distance_from_edge_mm` | float | 20.0 | Max distance from edge |

#### groups

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Group identifier |
| `components` | list | yes | Component refs |
| `max_spread_mm` | float | no | Max group spread (default: 30.0) |
| `zone` | string | no | Required zone for group |

---

## Troubleshooting

### Common Issues

#### "Module not found" errors

```bash
# Ensure you're in the right directory
cd temper/temper-placer

# Reinstall in development mode
pip install -e ".[dev]"
```

#### "KiCad file not found" errors

```bash
# Check the file exists
ls -la your_board.kicad_pcb

# Ensure it's a valid KiCad 6+ file (version 20221018+)
head -5 your_board.kicad_pcb
```

#### Optimization produces NaN or Inf

This usually indicates numerical instability. Try:

```bash
# Use curriculum learning (default)
temper-placer optimize board.kicad_pcb \
  -c constraints.yaml \
  -o output.kicad_pcb \
  --curriculum

# Or reduce epochs for faster convergence check
temper-placer optimize board.kicad_pcb \
  -c constraints.yaml \
  -o output.kicad_pcb \
  --epochs 1000
```

#### Slow optimization

```bash
# Reduce epochs for initial testing
temper-placer optimize board.kicad_pcb \
  -c constraints.yaml \
  -o output.kicad_pcb \
  --epochs 2000

# Check for GPU availability
python -c "import jax; print(jax.devices())"
```

#### DRC validation fails

```bash
# Check if kicad-cli is installed
which kicad-cli

# Run validation without DRC
temper-placer validate board.kicad_pcb --no-drc
```

### Getting Help

- **Issues:** [GitHub Issues](https://github.com/temper-project/temper/issues)
- **Design Doc:** See `TEMPER_PLACER_DESIGN.md` for architecture details
- **Tests:** Run `pytest` to verify your installation

### Performance Tips

1. **Start with fewer epochs** (1000-2000) to validate your setup
2. **Use GPU** if available for 5-10x speedup
3. **Reduce component count** by fixing some components in place
4. **Simplify constraints** initially, then add complexity
5. **Use checkpoints** to resume interrupted optimizations
