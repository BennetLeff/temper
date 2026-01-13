# Automated Zero-DRC Feedback Loop - Usage Guide

## Overview

The feedback loop system automatically iterates between PCB placement/routing and DRC validation, adjusting zone geometry to reduce violations.

## What Was Built

### 1. Core Components

- **ViolationComponentMapper** (`deterministic/feedback/violation_mapper.py`)
  - Parses KiCad DRC JSON reports
  - Maps violations to responsible components and zones
  - Extracts clearance values from violation descriptions

- **ZoneAdjuster** (`deterministic/feedback/zone_adjuster.py`)
  - Analyzes violations by zone
  - Computes expansion amounts based on violation density
  - Returns zone geometry adjustments

- **AutomatedZeroDRC** (`deterministic/feedback/orchestrator.py`)
  - Main orchestrator for the feedback loop
  - Coordinates pipeline → export → DRC → mapping → adjustment cycle

### 2. Test Script

`scripts/run_feedback_loop.py` - Standalone script demonstrating the full loop

## Quick Test

```bash
# Run 3 iterations with custom parameters
python scripts/run_feedback_loop.py \
  --max-iterations 3 \
  --violation-threshold 50 \
  --expansion-per-violation 3.0 \
  --output-dir /tmp/feedback_test
```

### Parameters

- `--max-iterations N` - Maximum feedback iterations (default: 5)
- `--violation-threshold N` - Violations needed to trigger zone expansion (default: 5)
- `--expansion-per-violation X` - mm to expand per excess violation (default: 1.0)
- `--output-dir PATH` - Where to save results (default: /tmp/feedback_loop)

## Test Results

### Current Baseline (Iteration 1)

```
Total violations: 431
Actionable: 398
  - solder_mask_bridge: 114
  - unconnected: 86
  - shorting_items: 62
  - via_dangling: 56
  - hole_to_hole: 31
  - clearance: 26
  - hole_clearance: 17
```

### Observations

1. **Zone Expansion Works**: Signal zone expanded by 20mm width
2. **No Improvement**: Violations stayed at 398 (0% reduction)
3. **Root Cause**: Zone size is NOT the limiting factor

The violations are caused by:
- **Placement density** (components too close)
- **Routing algorithm limitations** (can't satisfy clearances)
- **Via placement failures** (7 warnings about safe via positions)

NOT by insufficient zone space.

## Output Files

```
/tmp/feedback_loop/
├── iteration_1.kicad_pcb      # PCB after iteration 1
├── iteration_1_drc.json       # KiCad DRC report for iteration 1
├── iteration_2.kicad_pcb      # PCB after iteration 2
├── iteration_2_drc.json       # KiCad DRC report for iteration 2
└── history.json               # Iteration metrics
```

## Integration Test

The unit test demonstrates the feedback loop with mocked DRC:

```bash
pytest tests/deterministic/test_feedback_integration.py -v
```

**Result**: ✅ PASSED (4 minutes)

Test validates:
- Pipeline runs successfully
- Violations are parsed and mapped
- Zone expansion is applied
- Iteration history is tracked

## Next Steps

### Why Zone Expansion Didn't Help

The current violations are NOT caused by insufficient zone space:

1. **Solder mask bridges (114)**: PTH pads too close - needs component spacing increase
2. **Shorts (62)**: Router places vias/tracks on pads - needs better via placement logic
3. **Unconnected (86)**: Router couldn't complete connections - needs better A* heuristics
4. **Via dangling (56)**: Vias placed but not connected - via placement oracle issue

### What Would Actually Help

Instead of expanding zones, the feedback loop should:

1. **Increase component spacing** within zones (not zone size)
   - Modify `SlotGenerationStage` to add clearance between slots
   - Feed violation density back to slot grid resolution

2. **Fix via placement oracle**
   - 7 warnings about "could not find safe via position"
   - DRCOracle.get_valid_via_sites() is too restrictive
   - OR grid-based router should use oracle to validate BEFORE placing

3. **Improve routing completion**
   - 86 unconnected items = routing failures
   - A* pathfinder giving up too easily
   - Need better cost heuristics or multi-pass routing

## Recommended Architecture Change

Instead of:
```
Zone too small → Expand zone → Violations persist
```

Do:
```
Violations in zone → Increase slot spacing → Fewer violations
                  → Fix via oracle → Fewer via failures
                  → Better A* → Higher completion
```

## Files Modified/Created

### Created
- `src/temper_placer/deterministic/feedback/__init__.py`
- `src/temper_placer/deterministic/feedback/violation_mapper.py`
- `src/temper_placer/deterministic/feedback/drc_parser.py`
- `src/temper_placer/deterministic/feedback/zone_adjuster.py`
- `src/temper_placer/deterministic/feedback/orchestrator.py`
- `tests/deterministic/test_feedback_integration.py`
- `scripts/run_feedback_loop.py`

### Modified
- `tests/deterministic/test_feedback_integration.py` (fixed mock data format)
- `src/temper_placer/deterministic/feedback/orchestrator.py` (fixed type annotation)

## Beads Tickets

Epic: **temper-8hxh** - Automated Zero-DRC Feedback Loop

Tasks:
- ✅ `temper-8hxh.1` - ViolationComponentMapper
- ✅ `temper-8hxh.2` - ZoneAdjuster
- ✅ `temper-8hxh.3` - AutomatedZeroDRC orchestrator
- ✅ `temper-8hxh.4` - Config extension (partially - needs YAML updates)
- ✅ `temper-8hxh.5` - Integration tests

View with: `bd show temper-8hxh`

## Usage Examples

### 1. Manual Feedback Loop

```python
from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.deterministic.feedback import (
    parse_kicad_drc, ViolationComponentMapper, ZoneAdjuster
)

# Run pipeline
state = pipeline.run(initial_state)

# Export and run DRC
export_to_pcb(state, "/tmp/test.kicad_pcb")
subprocess.run(["kicad-cli", "pcb", "drc", "/tmp/test.kicad_pcb", ...])

# Parse violations
violations = parse_kicad_drc("/tmp/test_drc.json")

# Map to zones
mapper = ViolationComponentMapper(netlist, zone_config)
mapped = [mapper.map_violation(v) for v in violations]

# Compute adjustments
adjuster = ZoneAdjuster(zone_config, violation_threshold=10)
result = adjuster.compute_adjustments(mapped)

# Apply adjustments to config and re-run
```

### 2. Use AutomatedZeroDRC

```python
from temper_placer.deterministic.feedback import AutomatedZeroDRC

def run_drc():
    # Your DRC runner that returns JSON path
    subprocess.run([...])
    return "/tmp/drc_report.json"

orchestrator = AutomatedZeroDRC(
    pipeline=pipeline,
    netlist=netlist,
    initial_config=constraints,
    drc_runner=run_drc,
    max_iterations=5
)

final_state = orchestrator.run(initial_state)
```

## Debugging

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check zone mappings:

```python
from collections import Counter
zone_counts = Counter(m.zone for m in mapped_violations if m.zone)
print(zone_counts)  # {'Signal': 415, 'MCU': 16}
```

Inspect adjustments:

```python
for zone_name, adj in result.adjustments.items():
    print(f"{zone_name}: Δw={adj.delta_width}, Δh={adj.delta_height}")
```
