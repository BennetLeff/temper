# Router V6 Pipeline API Reference

This document provides the correct API usage for integrating with the Router V6 pipeline, particularly for Max-Flow routability analysis in the Benders decomposition system.

## Quick Start

```python
from pathlib import Path
from temper_placer.router_v6.pipeline import RouterV6Pipeline

# Initialize pipeline
pipeline = RouterV6Pipeline(
    verbose=False,
    enable_routability_analysis=False,  # Set True for Max-Flow
)

# Run full pipeline
result = pipeline.run(Path("path/to/board.kicad_pcb"))

# Access results
skeletons = result.stage2.skeletons  # dict[layer_name, ChannelSkeleton]
widths = result.stage2.channel_widths  # dict[layer_name, ChannelWidths]
design_rules = result.pcb.design_rules  # DesignRules
```

## RouterV6Pipeline Class

### Constructor

```python
RouterV6Pipeline(
    verbose: bool = False,
    enable_theta_star: bool = False,
    enable_lazy_theta_star: bool = False,
    enable_smoothing: bool = False,
    enable_legalization: bool = True,
    enable_negotiated_congestion: bool = False,
    enable_routability_analysis: bool = False,
    enable_topological_ordering: bool = False,
    placement_mode: str = "physics",
    max_nets: int | None = None,
    target_nets: list[str] | None = None,
)
```

**Key Parameters:**
- `verbose`: Enable logging
- `enable_routability_analysis`: Enable Max-Flow feasibility analysis
- `enable_legalization`: Auto-fix component overlaps (default: ON)
- `placement_mode`: "physics" or "analytical"

### Main Method

```python
def run(self, pcb_path: Path) -> RouterV6Result
```

Runs the complete Router V6 pipeline (Stages 0-4):
- **Stage 0**: Load PCB data
- **Stage 1**: Generate escape vias
- **Stage 2**: Channel extraction and analysis
- **Stage 3**: Topological routing (SAT-based)
- **Stage 4**: Geometric realization (A*)

**Returns:** `RouterV6Result` object with complete routing solution.

## Result Structure

### RouterV6Result

```python
@dataclass
class RouterV6Result:
    pcb: ParsedPCB                  # Parsed board data
    escape_vias: list[EscapeVia]    # Generated vias
    stage2: Stage2Output            # Channel analysis
    stage3: Stage3Output            # Topological routing
    stage4: Stage4Output            # Geometric realization
    runtime_seconds: float          # Total runtime
```

### Stage2Output

```python
@dataclass
class Stage2Output:
    obstacle_maps: dict[str, any]               # layer -> obstacles
    routing_spaces: dict[str, RoutingSpace]     # layer -> routing space
    skeletons: dict[str, ChannelSkeleton]       # layer -> skeleton
    channel_widths: dict[str, ChannelWidths]    # layer -> widths
    occupancy_grids: dict[str, OccupancyGrid]   # layer -> grid
    hv_occupancy_grids: dict[str, OccupancyGrid] # HV grids
    layer_capacities: dict[str, LayerCapacity]  # layer -> capacity
    routing_demand: RoutingDemand
    bottleneck_analysis: BottleneckAnalysis
```

**Most commonly used:**
- `skeletons`: Channel topology graphs for each layer
- `channel_widths`: Available routing widths
- `routing_spaces`: Routing space information

## ParsedPCB Structure

### DesignRules

```python
@dataclass
class DesignRules:
    net_classes: dict[str, NetClassRules]       # class_name -> rules
    net_class_assignments: dict[str, str]       # net_name -> class_name
    default_clearance_mm: float
    default_trace_width_mm: float
    default_via_diameter_mm: float
    default_via_drill_mm: float
    min_hole_to_hole_mm: float = 0.25
    min_annular_ring_mm: float = 0.1
    
    def get_rules_for_net(self, net_name: str) -> NetClassRules
```

### Net Class

```python
@dataclass
class Net:
    name: str                           # Net name (e.g., "GND", "USB_D+")
    pins: list[tuple[str, str]]         # [(component_ref, pin_name), ...]
    net_class: str = "Signal"           # Net class for design rules
    weight: float = 1.0                 # Wirelength optimization weight
    max_current: float = 0.0            # Maximum current (Amps)
    voltage_class: str = "LV"           # "LV" or "HV"
```

**Note:** Net does NOT have an `is_power` attribute. To detect power nets:

```python
def is_power_net(net: Net) -> bool:
    """Check if a net is a power/ground net."""
    return any(
        keyword in net.name.upper()
        for keyword in ["GND", "VCC", "VDD", "VBUS", "+", "POWER"]
    ) or net.max_current > 1.0  # High current nets
```

## Usage Patterns

### Pattern 1: Extract Channel Skeletons for Max-Flow

```python
from temper_placer.router_v6.pipeline import RouterV6Pipeline
from pathlib import Path

def get_channel_data(pcb_file: Path):
    pipeline = RouterV6Pipeline(
        verbose=False,
        enable_routability_analysis=False,
    )
    
    result = pipeline.run(pcb_file)
    
    return {
        "skeletons": result.stage2.skeletons,
        "widths": result.stage2.channel_widths,
        "rules": result.pcb.design_rules,
    }
```

### Pattern 2: Extract Net Information

```python
from temper_placer.io.kicad_parser import parse_kicad_pcb

def extract_signal_nets(pcb_file: Path):
    parse_result = parse_kicad_pcb(pcb_file, normalize=False)
    
    signal_nets = []
    for net in parse_result.netlist.nets:
        # Skip power/ground
        is_power = any(
            keyword in net.name.upper()
            for keyword in ["GND", "VCC", "VDD", "VBUS", "+"]
        )
        
        if not is_power and len(net.pins) >= 2:
            signal_nets.append(net)
    
    return signal_nets
```

### Pattern 3: Get Design Rules for Net

```python
design_rules = result.pcb.design_rules

# Get rules for specific net
net_rules = design_rules.get_rules_for_net("USB_D+")
print(f"Trace width: {net_rules.trace_width_mm}mm")
print(f"Clearance:   {net_rules.clearance_mm}mm")

# Check if differential pair
is_pair, gap = design_rules.are_differential_pair("USB_D+", "USB_D-")
if is_pair:
    print(f"Differential pair gap: {gap}mm")
```

## Common Mistakes to Avoid

### ❌ Wrong: Using non-existent methods

```python
# DON'T DO THIS
pipeline.load_board(pcb_path)  # Method doesn't exist!
stage2 = pipeline.run_stage_2()  # Private method!
```

### ✅ Correct: Use the public API

```python
# DO THIS
result = pipeline.run(pcb_path)
stage2 = result.stage2
```

### ❌ Wrong: Checking non-existent Net attributes

```python
# DON'T DO THIS
if net.is_power:  # Attribute doesn't exist!
    skip_net()
```

### ✅ Correct: Use heuristics

```python
# DO THIS
is_power = any(
    keyword in net.name.upper()
    for keyword in ["GND", "VCC", "VDD", "+"]
)
```

## Integration with Benders Decomposition

The Benders loop (`benders_loop.py`) integrates with Router V6 as follows:

```python
def _run_router_pipeline(self):
    """Get channel data for Max-Flow analysis."""
    from temper_placer.router_v6.pipeline import RouterV6Pipeline
    
    pipeline = RouterV6Pipeline(
        verbose=False,
        enable_routability_analysis=False,  # Don't recurse!
    )
    
    result = pipeline.run(self._pcb_file)
    
    return (
        result.stage2.skeletons,      # For Max-Flow graph
        result.stage2.channel_widths,  # For capacity computation
        result.pcb.design_rules        # For trace width/clearance
    )
```

## Performance Notes

- **Full pipeline**: ~5-30s for typical boards (33 components)
- **Stage 2 only**: Would be faster, but not exposed as public API
- **Max-Flow analysis**: Add ~0.5-2s per iteration

## See Also

- `BENDERS_INTEGRATION_GUIDE.md` - Max-Flow integration details
- `ROUTER_V6_TOPOLOGICAL_ARCHITECTURE.md` - Full architecture
- `temper_placer/router_v6/pipeline.py` - Source code
- `temper_placer/router_v6/stage0_data.py` - Data structures
