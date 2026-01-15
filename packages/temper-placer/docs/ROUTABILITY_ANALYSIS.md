# Max-Flow Routability Analysis

Router V6 includes a mathematically rigorous routability analysis tool based on the **Max-Flow Min-Cut Theorem**. This tool allows designers to prove whether a given component placement can physically support 100% routing completion before spending time on actual pathfinding.

## Purpose
In complex, high-density, or safety-critical boards (like **Temper**), aggressive clearance requirements (e.g., 6mm for AC Mains) can create hidden bottlenecks. Standard A* routers may fail to reach 100% completion, but it is often unclear if the failure is due to a poor routing algorithm or a physically impossible placement.

The Max-Flow analysis:
1.  **Quantifies Capacity**: Calculates the maximum number of parallel traces that can pass through the board's channels.
2.  **Identifies Bottlenecks**: Pinpoints the exact "min-cut" edges where routing capacity is restricted or zero.
3.  **Saves Time**: Fails fast if the board is mathematically unroutable.

## How it Works
1.  **Skeleton Extraction**: The tool extracts a medial axis skeleton of the available routing space on each layer.
2.  **Width Measurement**: It measures the channel width at every point along the skeleton, accounting for all obstacles (pads, keepouts, other nets).
3.  **Capacity Mapping**: Channels are converted into a flow network where edge capacity $C$ is defined by:
    $$C = \lfloor \frac{W - TraceWidth}{Pitch} \rfloor + 1$$
    where $W$ is the measured width.
4.  **Max-Flow Computation**: It computes the total flow from net sources to sinks. If $MaxFlow < TotalNets$, the board is unroutable.

## Usage in Pipeline
You can enable this analysis in the `RouterV6Pipeline`:

```python
from temper_placer.router_v6.pipeline import RouterV6Pipeline

pipeline = RouterV6Pipeline(
    enable_routability_analysis=True,
    verbose=True
)
pipeline.run("my_board.kicad_pcb")
```

When enabled, the pipeline will log the capacity and demand during Stage 2:
```text
Stage 2: Channel Analysis...
  2.9: Running Max-Flow Routability Analysis...
    Max-Flow Capacity: 5.0 traces
    Net Demand: 11.0 nets
    WARNING: Board is MATHEMATICALLY UNROUTABLE! Bottleneck: 6 edges.
```

## Interpreting Results
- **Feasible**: The board has enough physical capacity for all nets. If routing still fails, the problem is likely in the pathfinding sequence or rip-up strategy.
- **Infeasible**: The placement must be changed. Moving a single component by even 0.5mm can often "open" a bottleneck identified by the min-cut.

## Global Cut Analysis
The analysis also identifies "Global Cuts" (e.g., total capacity from Left-to-Right), which help determine if the overall board density is too high, even if individual net paths are not yet blocked.
