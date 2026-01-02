# Differential Pair Routing: Algorithm Research (Phase 1)

## Research Summary

**Date:** 2026-01-02  
**Task:** temper-bsr8  
**Goal:** Design dual-front A* algorithm for coupled differential pair routing

---

## Key Findings from Literature

### Differential Pair Requirements
1. **Impedance Control:** Maintain constant differential impedance (90Ω USB, 100Ω Ethernet)
2. **Length Matching:** Minimize skew between P/N traces (typically <0.5mm)
3. **Tight Coupling:** Keep traces close and equidistant (typical spacing: 0.2mm)
4. **Minimize Vias:** Each via introduces impedance discontinuity
5. **Solid Ground Plane:** Provides reference and reduces EMI

### Current Router Limitation (EXP-06-A)
- Treats P and N as independent nets
- Splits around obstacles → **violates coupling requirement**
- No length matching → **violates skew requirement**
- Coupling ratio: Low (<50% in EXP-06-A)

---

## Proposed Algorithm: Dual-Front Coupled A*

### Core Concept
Route both P and N traces **simultaneously** while maintaining coupling constraints throughout the search.

### State Space (7D)
```python
@dataclass
class DiffPairState:
    pos_x: int          # P trace X coordinate (grid)
    pos_y: int          # P trace Y coordinate
    pos_layer: int      # P trace layer
    neg_x: int          # N trace X coordinate
    neg_y: int          # N trace Y coordinate
    neg_layer: int      # N trace layer
    separation_mm: float  # Current spacing between traces
```

**Comparison:**
- Single-net A*: 3D state space (x, y, layer)
- Diff pair A*: 7D state space → **Much larger search space**

**Challenge:** State space explosion requires aggressive pruning

---

## Cost Function Design

### Total Cost
```
f(state) = g(state) + h(state)

where:
  g = actual_cost_from_start
  h = heuristic_cost_to_goal
```

### G-Cost Components (Actual Cost)
```python
g_cost = (
    manhattan_dist_traveled_P +
    manhattan_dist_traveled_N +
    separation_penalty +
    via_penalty +
    layer_change_penalty +
    length_mismatch_penalty
)
```

**Separation Penalty:**
```python
target_sep = 0.2  # mm (from config)
actual_sep = distance(pos_P, pos_N)

separation_penalty = coupling_weight * abs(actual_sep - target_sep)
```
- Penalizes deviation from target spacing
- Allows temporary divergence (e.g., around obstacles)
- `coupling_weight`: Higher = stricter coupling enforcement

**Length Mismatch Penalty:**
```python
length_diff = abs(len(path_P) - len(path_N))
length_penalty = skew_weight * length_diff
```
- Encourages balanced path lengths
- `skew_weight`: Higher = stricter length matching

### H-Cost (Heuristic)
```python
h_pos = manhattan_distance(state.pos, goal.pos)
h_neg = manhattan_distance(state.neg, goal.neg)

# Use MAX to ensure admissibility
h_cost = max(h_pos, h_neg)
```

**Admissibility:** Never overestimates true cost (required for optimality)

---

## Neighbor Generation

For each state, generate neighbors where:

**1. Both Move Together (Ideal)**
- P moves (dx, dy, dL)
- N moves (dx, dy, dL) **same direction**
- Maintains coupling and parallelism
- Cost: Low

**2. One Waits, Other Navigates Obstacle**
- P moves, N stays
- OR N moves, P stays
- Temporary divergence
- Cost: Medium (separation penalty)

**3. Both Change Layers Together**
- P: via to new layer
- N: via to new layer **same transition**
- Ideal for layer changes (maintains coupling)
- Cost: Medium (via penalty)

**4. Diverge Around Obstacle (Last Resort)**
- P and N take different paths
- Large separation penalty
- Only when no coupled path exists
- Cost: High

---

## Dual-Front Search (Bidirectional)

### Concept
Search from **both ends simultaneously**:
- Forward front: Expands from source pins (P_start, N_start)
- Backward front: Expands from target pins (P_goal, N_goal)
- Terminate when fronts meet

### Advantages
- Reduces search space (~50% compared to unidirectional)
- Fast convergence for simple paths
- Earlier obstacle detection

### Meeting Condition
```python
if forward_state.pos == backward_state.pos and \
   forward_state.neg == backward_state.neg:
    # Fronts met - reconstruct path
    return merge_paths(forward_path, backward_path)
```

---

## Algorithm Pseudocode

```python
def dual_front_coupled_astar(pair_config, start_pins, goal_pins):
    # Initialize both fronts
    forward_frontier = PriorityQueue()
    backward_frontier = PriorityQueue()
    
    start_state = DiffPairState(
        pos=start_pins.pos, neg=start_pins.neg, sep=target_sep
    )
    goal_state = DiffPairState(
        pos=goal_pins.pos, neg=goal_pins.neg, sep=target_sep
    )
    
    forward_frontier.push(start_state, f=h(start_state, goal_state))
    backward_frontier.push(goal_state, f=h(goal_state, start_state))
    
    forward_visited = {}
    backward_visited = {}
    
    while forward_frontier and backward_frontier:
        # Expand forward front
        current = forward_frontier.pop()
        
        if current in backward_visited:
            # Fronts met!
            return reconstruct_path(current, forward_visited, backward_visited)
        
        for neighbor in generate_coupled_neighbors(current):
            if is_valid_state(neighbor):
                g_new = forward_visited[current].g + cost(current, neighbor)
                f_new = g_new + h(neighbor, goal_state)
                
                if neighbor not in forward_visited or g_new < forward_visited[neighbor].g:
                    forward_visited[neighbor] = Node(g=g_new, parent=current)
                    forward_frontier.push(neighbor, f=f_new)
        
        # Expand backward front (symmetric)
        ...
    
    return None  # No path found
```

---

## Pruning Strategies (Essential!)

State space is 7D → Exponential growth → **Must prune aggressively**

**1. Coupling Threshold**
```python
if abs(sep - target_sep) > max_divergence:
    discard_state()  # Too separated
```

**2. Length Mismatch Threshold**
```python
if abs(len_P - len_N) > max_skew:
    discard_state()  # Too much skew
```

**3. Beam Search**
- Keep only top N states per frontier expansion
- N ~ 100-1000 (tunable)

**4. A* Frontier Pruning**
- Discard states with f-cost > best_f + threshold

---

## Fallback: Sequential Coupled Routing

If dual-front A* fails or is too slow:

**Simpler Algorithm:**
1. Route P trace first using standard A*
2. Route N trace following P's path at fixed offset
3. Apply local corrections for obstacles

**Advantages:**
-Much simpler (3D + 3D instead of 7D)
- Faster (two sequential 3D searches)

**Disadvantages:**
- Less optimal (N forced to follow P)
- May fail in tight spaces where P succeeds but N can't follow

**Use Case:** Fallback when dual-front exceeds time budget

---

## Implementation Plan

### Phase 2A: Data Structures (Week 1)
- [ ] `DiffPairState` dataclass
- [ ] `DiffPairPath` result type
- [ ] Priority queue for 7D states
- [ ] Visited set for 7D states (hashing)

### Phase 2B: Core Algorithm (Week 1-2)
- [ ] `generate_coupled_neighbors()` function
- [ ] Cost function implementation
- [ ] Heuristic function
- [ ] Dual-front search loop

### Phase 2C: Pruning & Optimization (Week 2)
- [ ] Beam search implementation
- [ ] Coupling/skew threshold enforcement
- [ ] Performance profiling

### Phase 3: Length Matching (Week 2)
- [ ] Serpentine pattern generation
- [ ] Length measurement
- [ ] Post-processing insertion

### Phase 4: Integration (Week 3)
- [ ] UnifiedRouter integration
- [ ] Config parsing for differential pairs
- [ ] EXP-06-A benchmark verification

---

## Success Criteria

**Functional:**
- [x] Algorithm designed and documented (THIS DOCUMENT)
- [ ] Dual-front A* routes pairs without splitting (EXP-06-A)
- [ ] Coupling ratio >80% (EXP-06-A success metric)
- [ ] Length mismatch <0.5mm (configurable)

**Performance:**
- [ ] Route time <10x single-net time
- [ ] Memory usage reasonable (<1GB for typical board)

**Robustness:**
- [ ] Fallback to sequential if dual-front fails
- [ ] Clear error messages for impossible constraints

---

## Next Steps

1. ✅ Research complete (this document)
2. **Next:** Create `diff_pair_router.py` module skeleton
3. Implement `DiffPairState` and neighbors
4. Unit test neighbor generation
5. Implement cost function
6. Prototype dual-front search

**Estimated Time to Working Prototype:** 1-2 weeks
