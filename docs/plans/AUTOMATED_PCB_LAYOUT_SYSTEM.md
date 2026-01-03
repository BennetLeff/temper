# Automated PCB Layout System: End-to-End Placer-Router

**Status**: Planning
**Created**: 2025-12-29
**Goal**: Zero-input automated PCB layout: netlist in → routed board out

---

## Executive Summary

The current placement-routing feedback loop achieves 31% completion with 1 conflict—a metric mismatch where the optimizer "games" the objective by making nets unroutable (failed nets produce zero conflicts). This document outlines a systematic plan to build a robust end-to-end automated PCB design system.

### Current State
- **Completion**: 31% (5/16 nets routed)
- **Conflicts**: 1
- **Problem**: Optimizer spreads components apart to reduce conflicts, but this makes nets unroutable

### Target State
- **Completion**: 100% (16/16 nets routed)
- **Conflicts**: ≤10 (resolvable by RRR)
- **Automation**: No user input required

---

## Root Cause Analysis

### The Metric Mismatch

The feedback loop optimizes for `num_conflicts`, but:

1. **Failed nets produce zero conflicts** - A net that can't route never occupies grid cells
2. **Congestion heatmap ignores failures** - Only sees where routes overlap, not where they fail
3. **Gradient descent spreads components** - Reducing conflicts by making routing impossible

### Evidence

| Iteration | Routed Nets | Conflicts | Insight |
|-----------|-------------|-----------|---------|
| 1 (no optimization) | 13/16 (81%) | 32 | Original placement works |
| 2 (after optimization) | 5/16 (31%) | 1 | Optimizer broke routing |

### Architectural Gap

```
Current Feedback Loop:
  Placement → Router → Conflicts → Heatmap → Placement
                ↓
           FAILED NETS → (no feedback!) ← PROBLEM
```

The system has no mechanism to tell the placer "these nets failed, move components closer."

---

## Solution Architecture

### Phase 0: Diagnostic Experiments

Before writing code, establish ground truth about router capabilities.

#### Experiment 0.1: Router Ceiling Test
**Question**: What's the best the router can achieve with unlimited effort?

```bash
uv run python scripts/internal_route.py pcb/temper_ready_for_route.kicad_pcb \
  --exclude-power-nets \
  --rrr-iters 50 \
  --soft-blocking \
  --cell-size 0.25
```

**Interpretation**:
- 16/16 → Router works, feedback loop is the problem
- <16/16 → Router has fundamental limitations

#### Experiment 0.2: Placement Sensitivity Test
**Question**: How much does placement affect routability?

Create 3 placement variants manually, route each, compare completion rates.

#### Experiment 0.3: Grid Resolution Impact
**Question**: Is 0.5mm grid too coarse?

```bash
for cell_size in 0.25 0.5 1.0; do
  uv run python scripts/internal_route.py pcb/temper_ready_for_route.kicad_pcb \
    --cell-size $cell_size --rrr-iters 10 --exclude-power-nets
done
```

---

### Phase 1: Router Hardening

#### 1.1 Pin Escape Routing (High Priority)

**Problem**: Router routes component-center to component-center. Real routing must escape from actual pin locations.

**Solution**: Two-stage routing:
1. **Pin Escape**: Find path from each pin to nearest unblocked cell
2. **Net Connection**: Route between escape points

```python
def route_net_with_escape(self, net_name: str, pin_positions: list[tuple], ...):
    escape_points = []
    for pin_pos in pin_positions:
        escape = self._find_escape_point(pin_pos)
        if escape is None:
            return RoutePath(success=False, failure_reason="pin_blocked")
        escape_points.append(escape)

    return self._route_between_points(escape_points, ...)
```

#### 1.2 Steiner Tree for Multi-Pin Nets (Medium Priority)

**Problem**: Pairwise routing (A→B→C) creates suboptimal topologies.

**Solution**: Use MST/RST to determine optimal connection order.

#### 1.3 Adaptive A* Heuristic (Medium Priority)

**Problem**: Manhattan heuristic is optimistic when obstacles block direct path.

**Solution**: Precompute distance map via BFS that accounts for obstacles.

#### 1.4 Layer Utilization Balance (Low Priority)

**Problem**: Nets cluster on one layer.

**Solution**: Add layer balance cost to routing.

---

### Phase 2: Feedback Loop Reconstruction

#### 2.1 Routability Score (Replaces Conflict Count)

```python
def compute_routability_score(results: dict[str, RoutePath], net_order: list[str]) -> float:
    """
    Score that captures true routing quality. Higher is better.

    Components:
    - Completion (80%): How many nets routed successfully
    - Clean routes (15%): How many routes have zero conflicts
    - Efficiency (5%): How short are the paths
    """
    total_nets = len(net_order)
    successful = sum(1 for r in results.values() if r.success)

    # Completion dominates (0-800 points)
    completion_score = (successful / total_nets) * 800

    # Conflict-free bonus (0-150 points)
    conflict_free = sum(1 for r in results.values() if r.success and r.conflict_count == 0)
    clean_score = (conflict_free / total_nets) * 150

    # Path efficiency (0-50 points)
    if successful > 0:
        avg_stretch = np.mean([r.length / r.min_length for r in results.values() if r.success])
        efficiency_score = 50 / max(1.0, avg_stretch)
    else:
        efficiency_score = 0

    return completion_score + clean_score + efficiency_score
```

#### 2.2 Failed Net Loss

Pull components of failed nets closer together:

```python
class FailedNetLoss:
    """Penalize placements where nets cannot route."""

    def update_from_routing(self, results: dict[str, RoutePath], netlist: Netlist):
        self.failed_nets = [name for name, r in results.items() if not r.success]
        # Map each failed net to component indices
        ...

    def __call__(self, positions: Array) -> float:
        total = 0.0
        for net_name, indices in self.net_to_components.items():
            # Penalize HPWL of failed net's components
            xs = positions[jnp.array(indices), 0]
            ys = positions[jnp.array(indices), 1]
            hpwl = (jnp.max(xs) - jnp.min(xs)) + (jnp.max(ys) - jnp.min(ys))
            total += hpwl ** 2
        return self.weight * total
```

#### 2.3 Successful Net Anchor Loss

Prevent breaking routes that already work:

```python
class SuccessfulNetAnchorLoss:
    """Anchor components of successfully routed nets."""

    def update_from_routing(self, results: dict, netlist: Netlist, positions: Array):
        # Record positions of components in conflict-free nets
        ...

    def __call__(self, positions: Array) -> float:
        # Penalize moving anchored components beyond radius
        ...
```

#### 2.4 Two-Phase Optimization

```python
phase = "completion"  # or "refinement"

for iteration in range(max_iterations):
    results = router.rrr_route_all_nets(...)
    successful = sum(1 for r in results.values() if r.success)

    # Phase transition at 100% completion
    if phase == "completion" and successful == len(net_order):
        phase = "refinement"
        anchor_loss.update_from_routing(results, netlist, positions)

    # Different losses per phase
    if phase == "completion":
        losses = [overlap, boundary, failed_net, mcu_clustering]
    else:
        losses = [overlap, boundary, congestion, anchor]
```

---

### Phase 3: Pin-Level Feedback (Advanced)

#### 3.1 Pin Accessibility Loss

Check if each pin can escape to open routing space:

```python
class PinAccessibilityLoss:
    def __call__(self, positions: Array, netlist: Netlist) -> float:
        for comp in netlist.components:
            for pin in comp.pins:
                if not router.check_pin_escape(pin_world, radius=5):
                    total_penalty += 10.0
        return self.weight * total_penalty
```

#### 3.2 Route Difficulty Gradient

Measure "how hard was this to route" for soft feedback:
- A* iterations / max iterations
- Path stretch factor
- Via count vs expected

---

### Phase 4: System Integration

#### Unified Pipeline

```python
def auto_layout_pcb(netlist: Netlist, board: Board) -> tuple[Array, dict]:
    # Stage 1: Initial placement
    positions = initial_placement(netlist, board)

    # Stage 2: Placement-routing loop
    for outer_iter in range(MAX_ITERATIONS):
        results = router.rrr_route_all_nets(netlist, positions, ...)

        if converged(results):
            break

        # Update losses from routing feedback
        failed_net_loss.update_from_routing(results, netlist)
        anchor_loss.update_from_routing(results, netlist, positions)

        # Optimize placement
        positions = optimize_placement(positions, losses, ...)

    # Stage 3: Final routing pass
    final_results = router.rrr_route_all_nets(netlist, positions, max_iterations=50)

    return positions, final_results
```

#### Convergence Criteria

```python
def is_converged(results, prev_results) -> bool:
    # Same successful nets?
    # Conflict count stable?
    # Positions stable?
```

#### Failure Recovery

```python
if not all_routed(results):
    # Try finer grid
    # Try relaxed via cost
    # Signal failure if nothing works
```

---

## Implementation Priority

| Priority | Task | Impact | Effort |
|----------|------|--------|--------|
| P0 | Phase 0 experiments | Validates approach | 1 day |
| P1 | Routability score metric | Fixes core problem | 0.5 day |
| P1 | Failed net loss | Enables completion | 1 day |
| P1 | Two-phase optimization | Prevents oscillation | 1 day |
| P2 | Pin escape routing | Handles pin blockage | 2 days |
| P2 | Successful net anchor | Stabilizes convergence | 1 day |
| P3 | Steiner tree routing | Better multi-pin nets | 2 days |
| P3 | Adaptive A* heuristic | Faster routing | 1 day |
| P4 | Pin accessibility loss | Fine-grained feedback | 2 days |

---

## Success Metrics

| Metric | Current | Target | Stretch |
|--------|---------|--------|---------|
| Completion rate | 31% | 100% | 100% |
| Conflicts | 1 | ≤10 | 0 |
| Outer loop iterations | Diverges | ≤5 | ≤3 |
| Runtime | ~30s/iter | <60s total | <30s |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Router can't achieve 100% | Medium | High | Phase 0 experiments reveal early |
| Oscillation between phases | Medium | Medium | Anchor loss prevents |
| Local minima | High | Medium | Random restarts, SA |
| Runtime blowup | Medium | Low | Profile, hierarchical routing |

---

## Files to Create/Modify

### New Files
- `losses/failed_net.py` - FailedNetLoss implementation
- `losses/anchor.py` - SuccessfulNetAnchorLoss implementation
- `routing/pin_escape.py` - Pin escape routing logic
- `routing/steiner.py` - Steiner tree for multi-pin nets
- `metrics/routability.py` - Routability score computation

### Modified Files
- `scripts/placement_routing_loop.py` - Two-phase optimization, new metrics
- `routing/maze_router.py` - Pin escape, adaptive A*
- `losses/__init__.py` - Export new losses

---

## References

- Architecture Doc Section 4: Placement ↔ Routing Loop
- `docs/PLACEMENT_IMPROVEMENT_TASKS.md` - Original routing-aware losses
- `docs/plans/ROUTER_IMPROVEMENT_STRATEGY.md` - RRR implementation plan
