# Routing Analysis & Automation

The `temper-placer` package includes tools for automating the routing process (using FreeRouter) and collecting detailed statistics on routability. This allows for closed-loop optimization where placement decisions are informed by actual routing results.

## Overview

The routing analysis pipeline consists of:
1.  **`RoutingAnalyzer`**: A Python class in `temper_placer.routing.analyzer` that handles the interaction with FreeRouter (export DSN, run headless, parse SES/output).
2.  **`experiment_tracker.py`**: A CLI tool in `experiments/` for running batch routing experiments and tracking results over time.

## Prerequisites

- **FreeRouting**: You must have `freerouting.jar` installed.
  - Default locations checked: `~/tools/freerouting.jar`, `/opt/freerouting/freerouting.jar`, `/usr/local/freerouting.jar`.
- **Java**: A Java Runtime Environment (JRE) compatible with FreeRouter.

## Usage

### 1. Python API (`RoutingAnalyzer`)

Use this class to integrate routing into your own scripts or optimization loops.

```python
from pathlib import Path
from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.analyzer import RoutingAnalyzer

# 1. Load your board and state
result = parse_kicad_pcb(Path("board.kicad_pcb"))
context = LossContext.from_netlist_and_board(result.netlist, result.board)
state = PlacementState.from_positions(positions)

# 2. Initialize Analyzer
analyzer = RoutingAnalyzer() # Auto-detects freerouting.jar

# 3. Run Analysis
# This runs FreeRouter in headless mode (no GUI)
analysis = analyzer.analyze(
    state=state,
    context=context,
    pcb_path=Path("board.dsn"), # Must provide a DSN file
    max_passes=100
)

# 4. Inspect Results
print(f"Completion: {analysis.routing_result.completion_percent}%")
print(f"Unrouted Nets: {analysis.routing_result.unrouted_nets}")
print(f"Via Count: {analysis.routing_result.via_count}")

# 5. Save Record
analysis.save(Path("analysis_result.json"))
```

### 2. Experiment Tracker CLI

Use this script to benchmark existing DSN files or track improvements.

**Record a single run:**
```bash
# Runs FreeRouter in headless mode for 100 passes
uv run python3 experiments/experiment_tracker.py record \
    --dsn pcb/temper_ordered.dsn \
    --placement-source "manual_baseline" \
    --passes 100 \
    --notes "Baseline run with net ordering"
```

**Run a batch on multiple files:**
```bash
# Useful for sweeping parameters or seeds
uv run python3 experiments/experiment_tracker.py batch 'pcb/*.dsn' \
    --placement-source "batch_sweep"
```

**View Results:**
```bash
# Show top 10 results by routing completion
uv run python3 experiments/experiment_tracker.py best --top 10

# Show recent history
uv run python3 experiments/experiment_tracker.py history
```

## Metrics Collected

The tools automatically collect:
- **Pre-routing**: HPWL (Half-Perimeter Wire Length), Congestion (Max/Mean), Bottleneck count.
- **Routing**: Completion %, Routed/Unrouted net counts, List of specific failed nets, Via count, Total trace length, Execution time.
- **Post-routing**: (Placeholder for future DRC/DFM metrics).

## Troubleshooting

- **"freerouting.jar not found"**: Ensure the JAR is in `~/tools/` or one of the checked paths.
- **Hangs**: The tools use `timeout=600` (10 minutes) by default. If your board is very complex, you may need to increase this in the code.
- **Zero Completion**: Ensure your DSN file is valid and that `freerouting.jar` is compatible with your Java version. The tools use `-Djava.awt.headless=true` to prevent GUI creation.
