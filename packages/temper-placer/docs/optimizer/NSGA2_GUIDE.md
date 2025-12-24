# NSGA-II Multi-Objective Optimization Guide

This guide covers using NSGA-II for multi-objective PCB placement optimization in temper-placer.

## Table of Contents

- [Overview](#overview)
- [When to Use NSGA-II](#when-to-use-nsga-ii)
- [Quick Start](#quick-start)
- [Understanding the Algorithm](#understanding-the-algorithm)
- [Defining Objectives](#defining-objectives)
- [Working with Results](#working-with-results)
- [Parameter Tuning](#parameter-tuning)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)

---

## Overview

NSGA-II (Non-dominated Sorting Genetic Algorithm II) is an evolutionary algorithm for multi-objective optimization. Unlike gradient descent which combines objectives into a single scalar loss, NSGA-II finds the **Pareto front** - the set of optimal trade-offs where improving one objective requires sacrificing another.

### Key Benefits

- **No weight tuning**: Explore all trade-offs without committing to specific objective weights
- **Diverse solutions**: Get multiple placement options representing different priorities
- **Global search**: Evolutionary approach escapes local optima better than gradient descent
- **Interpretable**: Visualize trade-offs on Pareto front plots

### Comparison with Gradient Descent

| Aspect | NSGA-II | Gradient Descent |
|--------|---------|------------------|
| Objectives | 2-4 competing objectives | Single combined loss |
| Output | Pareto front (many solutions) | Single solution |
| Speed | Slower (evaluates population) | Faster (single path) |
| Local optima | Good escape via mutation | Can get stuck |
| Weights | Not needed | Must specify per-objective |

---

## When to Use NSGA-II

### Good Use Cases

✅ **Conflicting objectives**: Wirelength vs. thermal vs. DRC compliance  
✅ **Exploring trade-offs**: You want to understand what's achievable  
✅ **Multiple valid designs**: Different placement strategies are acceptable  
✅ **Rough global search**: Before fine-tuning with gradient descent  

### When to Prefer Gradient Descent

❌ **Known objective weights**: You know thermal is 2x more important than wirelength  
❌ **Speed-critical**: Need placement in seconds, not minutes  
❌ **Single clear goal**: Only care about wirelength  
❌ **Fine-tuning**: Already have a good placement, need small improvements  

### Hybrid Approach (Recommended)

Use NSGA-II for initial exploration, then refine the best trade-off with gradient descent:

```python
# 1. NSGA-II: Find Pareto front
nsga_result = optimizer.evolve(netlist, board, objectives, context, generations=100)

# 2. Select preferred trade-off (knee point or manual)
best_idx = select_knee_point(nsga_result.objectives, nsga_result.best_indices)
initial_state = PlacementState(
    positions=nsga_result.population_positions[best_idx],
    rotation_logits=nsga_result.population_rotations[best_idx]
)

# 3. Gradient descent: Refine placement
final_result = train_multiphase(
    netlist, board, loss_factory, context,
    config=config,
    initial_state=initial_state
)
```

---

## Quick Start

### Basic Example

```python
from temper_placer.optimizer.nsga2 import NSGAOptimizer, select_knee_point, plot_pareto_front
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.losses.thermal import EdgePreferenceLoss
from temper_placer.losses.base import LossContext

# 1. Setup board and netlist (assumed already loaded)
context = LossContext.from_netlist_and_board(netlist, board)

# 2. Define objectives
wirelength = WirelengthLoss()
thermal = EdgePreferenceLoss(
    thermal_pad_indices=jnp.array([0, 1]),  # Component indices for Q1, Q2
    board_width=board.width,
    board_height=board.height,
    preferred_margin_mm=5.0
)
objectives = [wirelength, thermal]

# 3. Create optimizer and run
optimizer = NSGAOptimizer(
    population_size=50,
    mutation_rate=0.15,
    mutation_sigma=2.0
)

result = optimizer.evolve(
    netlist=netlist,
    board=board,
    objectives=objectives,
    context=context,
    generations=100,
    seed=42
)

# 4. Visualize Pareto front
fig = plot_pareto_front(result, ["Wirelength (mm)", "Thermal Distance"])
fig.show()

# 5. Select best trade-off
best_idx = select_knee_point(result.objectives, result.best_indices)
print(f"Knee point objectives: {result.objectives[best_idx]}")
```

### Using with Pipeline

```python
from temper_placer.optimizer.phases import NsgaPhase, OptimizationPipeline

# Create pipeline with NSGA phase enabled
pipeline = OptimizationPipeline(
    netlist=netlist,
    board=board,
    constraints=constraints,
    opt_config=optimizer_config,
    loss_factory=loss_factory,
    context=context,
    use_nsga=True  # Enable NSGA-II phase
)

result = pipeline.run()

# Pipeline result includes Pareto front states
for i, state in enumerate(result.final_states):
    print(f"Solution {i}: {state.positions.shape}")
```

---

## Understanding the Algorithm

### Pareto Dominance

Solution A **dominates** solution B if:
1. A is **not worse** than B in all objectives
2. A is **strictly better** than B in at least one objective

Solutions that are not dominated by any other are called **Pareto-optimal** or **non-dominated**.

```
Objectives: [Wirelength, Thermal]

A: [100, 50]  - Low wirelength, high thermal penalty
B: [150, 30]  - Higher wirelength, lower thermal penalty  
C: [120, 60]  - Worse than A in both → Dominated by A

A and B are both Pareto-optimal (neither dominates the other)
C is dominated (by A)
```

### Pareto Fronts

The algorithm partitions solutions into **fronts**:
- **Front 0**: All non-dominated solutions (the Pareto front)
- **Front 1**: Solutions dominated only by front 0
- **Front 2**: Solutions dominated only by fronts 0-1
- etc.

Selection pressure drives the population toward front 0.

### Crowding Distance

Within each front, solutions are ranked by **crowding distance** - how isolated they are from neighbors. Solutions in less crowded regions are preferred to maintain diversity across the Pareto front.

```
Front 0: [A, B, C, D, E] sorted by objective 1

A --- B ----- C -- D --- E
     ↑              ↑
   crowded      isolated

D has higher crowding distance → preferred for diversity
```

### Evolution Loop

Each generation:
1. **Evaluate**: Compute objectives for all individuals
2. **Sort**: Assign fronts via non-dominated sorting
3. **Select**: Tournament selection using rank + crowding distance
4. **Crossover**: BLX-α blending of parent genes
5. **Mutate**: Gaussian perturbation of offspring
6. **Combine**: Merge parents and offspring (2N individuals)
7. **Survive**: Select best N by rank, then crowding distance

---

## Defining Objectives

### Objective Function Interface

Each objective function must follow this signature:

```python
def objective(positions, rotations, context, epoch, total_epochs):
    """
    Args:
        positions: (N, 2) component positions
        rotations: (N, 4) rotation logits
        context: LossContext with precomputed data
        epoch: Current generation
        total_epochs: Total generations
        
    Returns:
        Object with .value attribute (scalar JAX array)
    """
    # Calculate objective value (lower is better)
    value = ...
    return type('Result', (), {'value': value})()
```

### Built-in Objectives

temper-placer provides several loss functions usable as objectives:

| Loss | Description | Import |
|------|-------------|--------|
| `WirelengthLoss` | Total half-perimeter wirelength | `temper_placer.losses.wirelength` |
| `OverlapLoss` | Component overlap penalty | `temper_placer.losses.overlap` |
| `BoundaryLoss` | Out-of-bounds penalty | `temper_placer.losses.boundary` |
| `EdgePreferenceLoss` | Push components to edges | `temper_placer.losses.thermal` |
| `GroupSpreadLoss` | Keep component groups together | `temper_placer.losses.grouping` |
| `ZoneLoss` | Zone assignment compliance | `temper_placer.losses.zone` |

### Custom Objectives

```python
from temper_placer.losses.base import LossResult

class CustomDRCLoss:
    """Penalize DRC violations."""
    
    def __call__(self, positions, rotations, context, epoch, total_epochs):
        # Example: penalize components too close together
        dists = compute_pairwise_distances(positions)
        min_clearance = 1.0  # mm
        violations = jnp.maximum(0, min_clearance - dists)
        value = jnp.sum(violations)
        return LossResult(value=value, components={})
```

### Choosing Objectives

**Recommended 2-3 objectives for PCB placement:**

1. **Wirelength** (always include) - Drives connectivity
2. **Thermal** (if power components) - Edge placement for dissipation
3. **DRC/Overlap** (optional) - Can be handled as constraint instead

⚠️ **Avoid > 4 objectives** - Pareto fronts become very large and selection pressure weakens.

---

## Working with Results

### NSGAResult Structure

```python
result = optimizer.evolve(...)

# Population data
result.population_positions  # (pop_size, n_components, 2)
result.population_rotations  # (pop_size, n_components, 4)
result.objectives            # (pop_size, n_objectives)

# Pareto fronts
result.fronts       # List of fronts, each a list of indices
result.best_indices # Indices in front 0 (Pareto-optimal)
```

### Selecting from Pareto Front

**Knee Point (Automatic)**

The knee point maximizes perpendicular distance from the line connecting extreme solutions - it represents the "best" trade-off.

```python
from temper_placer.optimizer.nsga2 import select_knee_point

# Automatic knee point selection
best_idx = select_knee_point(result.objectives, result.best_indices)
```

**Weighted Selection**

Bias toward objectives you care about more:

```python
# Prioritize wirelength (2x weight) over thermal (1x weight)
weights = jnp.array([2.0, 1.0])
best_idx = select_knee_point(result.objectives, result.best_indices, weights=weights)
```

**Manual Selection**

Inspect the Pareto front and choose manually:

```python
# Get Pareto front objectives
front_indices = jnp.array(result.best_indices)
front_objs = result.objectives[front_indices]

# Print options
for i, idx in enumerate(result.best_indices):
    print(f"Solution {i}: {result.objectives[idx]}")

# Select solution 3
chosen_idx = result.best_indices[3]
```

### Creating PlacementState

```python
from temper_placer.core.state import PlacementState

best_state = PlacementState(
    positions=result.population_positions[best_idx],
    rotation_logits=result.population_rotations[best_idx]
)
```

### Visualization

```python
from temper_placer.optimizer.nsga2 import plot_pareto_front

# 2D Pareto front
fig = plot_pareto_front(result, ["Wirelength", "Thermal"])
fig.show()

# Save to file
fig.write_html("pareto_front.html")
```

---

## Parameter Tuning

### Population Size

| Problem Size | Recommended | Rationale |
|--------------|-------------|-----------|
| < 20 components | 30-50 | Small search space |
| 20-50 components | 50-100 | Balance exploration/speed |
| > 50 components | 100-200 | Need more diversity |

**Effects:**
- Larger → Better exploration, slower per-generation
- Smaller → Faster, may miss good solutions

### Generations

| Goal | Recommended | Notes |
|------|-------------|-------|
| Quick exploration | 30-50 | See rough Pareto shape |
| Standard run | 100-200 | Good convergence |
| Thorough search | 300-500 | Maximum quality |

**Convergence check:** Run with 50, 100, 200 generations and compare Pareto fronts. If 100 and 200 look similar, 100 is sufficient.

### Mutation Rate

| Value | Effect |
|-------|--------|
| 0.01-0.05 | Low: Exploitation, may stagnate |
| 0.1-0.2 | Medium: Balanced (recommended) |
| 0.3+ | High: Exploration, slow convergence |

**Start with 0.15** and adjust based on convergence behavior.

### Mutation Sigma

Scale based on board dimensions:

```python
# Rule of thumb: 1-3% of board dimension
mutation_sigma = 0.02 * board.width  # e.g., 2.0 for 100mm board
```

### Crossover Alpha

| Value | Effect |
|-------|--------|
| 0.0 | Offspring between parents only |
| 0.5 | Standard BLX-0.5 (recommended) |
| 1.0 | Wide exploration, may slow down |

**Default 0.5 works well for most cases.**

### Example Configuration

```python
# Conservative (exploitation-focused)
optimizer = NSGAOptimizer(
    population_size=40,
    mutation_rate=0.05,
    mutation_sigma=1.5,
    crossover_alpha=0.3
)

# Balanced (recommended starting point)
optimizer = NSGAOptimizer(
    population_size=50,
    mutation_rate=0.15,
    mutation_sigma=2.0,
    crossover_alpha=0.5
)

# Exploratory (for complex problems)
optimizer = NSGAOptimizer(
    population_size=100,
    mutation_rate=0.25,
    mutation_sigma=3.0,
    crossover_alpha=0.7
)
```

---

## Advanced Usage

### Seeding with Initial State

Start from a known good placement:

```python
# Load existing placement
initial_state = load_placement_from_kicad("board.kicad_pcb")

result = optimizer.evolve(
    netlist=netlist,
    board=board,
    objectives=objectives,
    context=context,
    generations=100,
    initial_state=initial_state  # Seed population
)
```

The population is initialized by perturbing the initial state with Gaussian noise.

### Checkpointing (Coming Soon)

```python
# Not yet implemented - save/resume functionality
# result = optimizer.evolve(..., checkpoint_path="checkpoint.pkl")
```

### Combining with Gradient Descent

Use NSGA-II for global exploration, gradient descent for local refinement:

```python
# Phase 1: NSGA-II exploration
nsga_result = optimizer.evolve(
    netlist, board, objectives, context,
    generations=50
)

# Phase 2: Refine each Pareto solution with gradient descent
refined_states = []
for idx in nsga_result.best_indices:
    initial = PlacementState(
        positions=nsga_result.population_positions[idx],
        rotation_logits=nsga_result.population_rotations[idx]
    )
    refined = train_multiphase(
        netlist, board, loss_factory, context,
        config=config,
        initial_state=initial
    )
    refined_states.append(refined.best_state)
```

### Custom Selection Strategies

Implement domain-specific selection from Pareto front:

```python
def select_best_drc(result, drc_checker):
    """Select Pareto solution with fewest DRC violations."""
    best_idx = None
    min_violations = float('inf')
    
    for idx in result.best_indices:
        state = PlacementState(
            positions=result.population_positions[idx],
            rotation_logits=result.population_rotations[idx]
        )
        violations = drc_checker.count_violations(state)
        if violations < min_violations:
            min_violations = violations
            best_idx = idx
    
    return best_idx
```

---

## Troubleshooting

### Pareto Front Has Only 1-2 Solutions

**Causes:**
- Objectives not actually conflicting
- Population too small
- Not enough generations

**Solutions:**
- Verify objectives are truly in tension
- Increase `population_size` to 100+
- Run for more generations (200+)

### Slow Convergence

**Causes:**
- Population too large
- Too many generations
- Inefficient objectives

**Solutions:**
- Reduce `population_size` if Pareto front looks stable
- Use profiling to find slow objectives
- Consider pre-computing objective data

### Solutions Don't Improve

**Causes:**
- Mutation rate too low
- Stuck in local optimum
- Objectives have flat regions

**Solutions:**
- Increase `mutation_rate` to 0.2-0.3
- Increase `mutation_sigma`
- Add diversity-promoting objective

### Out of Memory

**Causes:**
- Population too large
- Too many components

**Solutions:**
- Reduce `population_size`
- Run on GPU if available
- Consider problem decomposition

### Runtime Error: Odd Population Size

**Known Bug:** Population size must be even due to crossover pairing.

**Solution:** Use even population sizes (50, 100, etc.)

---

## API Reference

### NSGAOptimizer

```python
class NSGAOptimizer:
    def __init__(
        self,
        population_size: int = 50,
        mutation_rate: float = 0.1,
        mutation_sigma: float = 2.0,
        crossover_alpha: float = 0.5
    ): ...
    
    def evolve(
        self,
        netlist: Netlist,
        board: Board,
        objectives: list[Callable],
        context: LossContext,
        generations: int = 100,
        initial_state: PlacementState | None = None,
        seed: int = 42
    ) -> NSGAResult: ...
```

### NSGAResult

```python
@dataclass
class NSGAResult:
    population_positions: Array   # (pop_size, n_components, 2)
    population_rotations: Array   # (pop_size, n_components, 4)
    objectives: Array             # (pop_size, n_objectives)
    fronts: list[list[int]]       # Pareto fronts
    best_indices: list[int]       # Indices in front 0
```

### Helper Functions

```python
def fast_non_dominated_sort(objectives: Array) -> list[list[int]]
def calculate_crowding_distance(objectives: Array) -> Array
def select_knee_point(
    objectives: Array,
    front_indices: list[int] | None = None,
    weights: Array | None = None
) -> int
def plot_pareto_front(result: NSGAResult, objective_names: list[str]) -> Figure
```

---

## References

- Deb, K., Pratap, A., Agarwal, S., & Meyarivan, T. (2002). "A Fast and Elitist Multiobjective Genetic Algorithm: NSGA-II". IEEE Transactions on Evolutionary Computation, 6(2), 182-197.
- Branke, J., Deb, K., Dierolf, H., & Osswald, M. (2004). "Finding Knees in Multi-objective Optimization". Parallel Problem Solving from Nature - PPSN VIII.
- Eshelman, L. J., & Schaffer, J. D. (1993). "Real-coded genetic algorithms and interval-schemata". Foundations of Genetic Algorithms, 2, 187-202.
