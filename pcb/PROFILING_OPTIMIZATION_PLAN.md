# Router V6 Profiling & Optimization Plan

**Goal**: Reduce Theta* runtime from >19 minutes to <8 minutes while maintaining 100% routing success

**Date**: January 13, 2026
**Status**: Planning

---

## Phase 1: Profiling & Hotspot Identification

### Experiment P1: Python cProfile Baseline

**Objective**: Identify which functions consume the most CPU time

**Method**:
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

pipeline = RouterV6Pipeline(verbose=True, enable_theta_star=True)
result = pipeline.run(pcb_path)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(50)  # Top 50 functions
```

**Expected Hotspots**:
1. `_line_of_sight()` - Bresenham line algorithm (called per neighbor expansion)
2. `_astar_search_theta_star()` - Main pathfinding loop
3. Heap operations (`heappush`, `heappop`)
4. Grid access (`grid.grid[y, x]`)
5. Distance calculations (`euclidean_dist`)

**Success Metric**: Identify functions consuming >5% of total runtime

**Output**: `profiling/theta_star_profile.txt`

---

### Experiment P2: Line Profiler for Theta*

**Objective**: Identify hotspots at line-level granularity

**Method**:
```bash
pip install line_profiler
kernprof -l -v run_router_v6.py --theta-star
```

Add `@profile` decorator to:
- `_astar_search_theta_star()`
- `_line_of_sight()`
- `_find_access_node()`

**Expected Findings**:
- Which lines in Theta* are slowest
- How many times line-of-sight is called
- Grid access patterns

**Output**: `profiling/theta_star_line_profile.txt`

---

### Experiment P3: Memory Profiler

**Objective**: Check if memory allocations contribute to slowdown

**Method**:
```bash
pip install memory_profiler
python -m memory_profiler run_router_v6.py --theta-star
```

**Expected Findings**:
- Peak memory usage during Theta*
- Whether large data structures cause GC pauses
- Memory growth during reroute passes

**Output**: `profiling/theta_star_memory_profile.txt`

---

### Experiment P4: Per-Net Timing Breakdown

**Objective**: Quantify time spent per net and identify outliers

**Method**: Add instrumentation to `_astar_route_with_ripup()`:
```python
import time

start = time.time()
route_path, ripped_ids = _astar_route_with_ripup(...)
elapsed = time.time() - start

net_timings[net_name] = elapsed
print(f"    {net_name}: {elapsed:.2f}s")
```

**Expected Findings**:
- Which nets take >30s
- Correlation between net complexity and runtime
- Reroute pass performance degradation

**Output**: `profiling/per_net_timings.json`

---

## Phase 2: Optimization Experiments

### Experiment O1: Adaptive Routing Strategy

**Hypothesis**: Most nets don't need Theta* - only use it when A* fails

**Implementation**:
```python
def _astar_route_adaptive(net_name, channel_path, grid):
    # Try A* first (fast)
    path_astar = _astar_route(net_name, channel_path, grid, use_theta_star=False)

    if path_astar and path_astar.forced_segment_count == 0:
        return path_astar  # A* succeeded

    # Fall back to Theta* only on failure
    print(f"    {net_name}: A* failed, trying Theta*...")
    path_theta = _astar_route(net_name, channel_path, grid, use_theta_star=True)
    return path_theta
```

**Expected Improvement**: 50-70% runtime reduction (only 3/18 nets need Theta*)

**Test**:
```bash
python run_router_v6.py --adaptive-routing
```

**Success Metric**: <10 min total runtime, 18/18 nets routed

---

### Experiment O2: Early Termination with "Good Enough" Paths

**Hypothesis**: Don't need optimal paths - first valid path is sufficient

**Implementation**:
```python
def _astar_search_theta_star(
    grid, start, goal, net_id,
    max_iterations: int = 100000  # NEW
):
    iterations = 0
    while open_set and iterations < max_iterations:
        iterations += 1
        _, _, current = heappop(open_set)

        if current == goal:
            return reconstruct_path(current)  # Found path!

        # ... rest of algorithm

    # Timeout: return best partial path if no complete path
    return None
```

**Expected Improvement**: 30-50% reduction in worst-case search time

**Test**: Add `--max-theta-iterations 50000`

**Success Metric**: No net takes >5 min

---

### Experiment O3: Line-of-Sight Caching

**Hypothesis**: Many LOS checks are redundant - cache results

**Implementation**:
```python
_los_cache = {}  # Global cache (grid_id, p1, p2) -> bool

def _line_of_sight_cached(p1, p2, grid, net_id):
    cache_key = (id(grid), p1, p2)

    if cache_key in _los_cache:
        return _los_cache[cache_key]

    result = _line_of_sight(p1, p2, grid, net_id)
    _los_cache[cache_key] = result
    return result
```

**Expected Improvement**: 10-20% speedup if LOS checks dominate

**Risk**: Cache invalidation when grid changes (reroute passes)

**Test**: Profile before/after caching

**Success Metric**: >15% reduction in LOS computation time

---

### Experiment O4: Lazy Line-of-Sight (Only Check Parent)

**Hypothesis**: Theta* checks LOS for every neighbor - only check when g-score improves

**Implementation**:
```python
# CURRENT: Always check LOS
if parent and _line_of_sight(parent, neighbor, grid, net_id):
    # ...

# OPTIMIZED: Only check if potentially better
if parent:
    direct_dist = euclidean_dist(parent, neighbor)
    current_dist = euclidean_dist(current, neighbor)

    # Only check LOS if direct path could be shorter
    if g_score[parent] + direct_dist < g_score[current] + current_dist:
        if _line_of_sight(parent, neighbor, grid, net_id):
            # ...
```

**Expected Improvement**: 20-40% reduction in LOS calls

**Test**: Add `--lazy-los` flag

**Success Metric**: 30% fewer LOS checks in profiler

---

### Experiment O5: A* Warm-Start for Theta*

**Hypothesis**: Use A* solution to guide Theta* search (better heuristic)

**Implementation**:
```python
def _astar_search_theta_star(
    grid, start, goal, net_id,
    came_from_init: dict = None  # A* solution as seed
):
    # Initialize with A* path
    if came_from_init:
        for node, parent in came_from_init.items():
            came_from[node] = parent
            g_score[node] = compute_path_cost(start, node, came_from)

    # Run Theta* to optimize
    # ...
```

**Expected Improvement**: 20-30% faster convergence

**Test**: Run A* first, pass `came_from` to Theta*

**Success Metric**: 25% reduction in Theta* iterations

---

### Experiment O6: Per-Net Timeout with Fallback

**Hypothesis**: Don't let any single net take >5 min - fall back to forced routing

**Implementation**:
```python
import signal

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Theta* search timeout")

def _astar_route_with_timeout(net_name, channel_path, grid, timeout_sec=300):
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_sec)  # 5 min timeout

    try:
        path = _astar_search_theta_star(...)
    except TimeoutError:
        print(f"    {net_name}: Timeout, using forced routing")
        path = create_forced_path(channel_path)  # Direct line
    finally:
        signal.alarm(0)  # Cancel alarm

    return path
```

**Expected Improvement**: Guaranteed <10 min total runtime

**Trade-off**: May produce forced (DRC-violating) paths for timeout nets

**Test**: Add `--theta-timeout 300`

**Success Metric**: No net takes >5 min, forced routing documented

---

### Experiment O7: Smoothing on A* Results (No Theta*)

**Hypothesis**: Force-directed smoothing alone may fix baseline failures

**Implementation**:
```bash
# Run baseline A* with smoothing
python run_router_v6.py --smoothing
```

**Expected Result**:
- 15/18 nets routed by A*
- Smoothing fixes near-miss violations
- May not solve DC_BUS-, PWM_H, SW_NODE (topology-blocked)

**Test**: Measure DRC violations before/after smoothing

**Success Metric**: <50 DRC violations remaining

---

### Experiment O8: Hybrid Approach (A* + Smoothing + Theta* Fallback)

**Hypothesis**: Best of all worlds - fast A* + smoothing for most nets, Theta* only when needed

**Implementation**:
```python
class RouterV6Pipeline:
    def __init__(
        self,
        enable_theta_star: str = "adaptive",  # "always", "never", "adaptive"
        enable_smoothing: bool = True,
        theta_timeout: int = 300,
    ):
        # ...
```

**Routing Strategy**:
1. Route all nets with A* (fast)
2. Apply smoothing to fix violations
3. For remaining failures, re-route with Theta* (timeout=5 min)

**Expected Result**: <8 min total, 18/18 nets, 0 DRC violations

**Test**:
```bash
python run_router_v6.py --adaptive-routing --smoothing --theta-timeout 300
```

**Success Metric**: Production-ready performance

---

## Phase 3: Validation & Testing

### Test Matrix

| Configuration | Expected Runtime | Expected Success | DRC Violations |
|---------------|------------------|------------------|----------------|
| Baseline (A*) | 6.75 min | 15/18 (83%) | ~170 |
| A* + Smoothing | 8 min | 15/18 (83%) | <50 |
| Theta* Always | >19 min | 18/18 (100%) | 0 (untested) |
| Adaptive (O1) | 10 min | 18/18 (100%) | 0 (untested) |
| Adaptive + Early Term (O2) | 8 min | 18/18 (100%) | <20 |
| Hybrid (O8) | 7-8 min | 18/18 (100%) | 0 |

### Validation Criteria

✅ **Must Have**:
- Runtime <10 minutes
- 18/18 nets routed (100%)
- 0 forced segments
- No crashes

🎯 **Should Have**:
- Runtime <8 minutes
- <20 DRC violations
- Reproducible results

🌟 **Nice to Have**:
- Runtime <7 minutes
- 0 DRC violations
- <5% path length overhead vs optimal

---

## Phase 4: Implementation Priority

### Week 1: Profiling
1. ✅ **P1**: cProfile baseline (2 hours)
2. ✅ **P2**: Line profiler (2 hours)
3. ✅ **P4**: Per-net timing (1 hour)

**Deliverable**: Hotspot analysis report

### Week 2: Quick Wins
1. ✅ **O1**: Adaptive routing (4 hours)
2. ✅ **O2**: Early termination (2 hours)
3. ✅ **O6**: Per-net timeout (2 hours)

**Deliverable**: Adaptive routing working at <10 min

### Week 3: Advanced Optimizations
1. ✅ **O3**: LOS caching (4 hours)
2. ✅ **O4**: Lazy LOS (4 hours)
3. ✅ **O5**: A* warm-start (6 hours)

**Deliverable**: <8 min runtime with all optimizations

### Week 4: Integration & Testing
1. ✅ **O7**: Test smoothing on A* (2 hours)
2. ✅ **O8**: Hybrid implementation (4 hours)
3. ✅ **Phase 3**: Validation matrix (4 hours)

**Deliverable**: Production-ready Router V6

---

## Success Metrics Summary

| Metric | Current | Target | Stretch Goal |
|--------|---------|--------|--------------|
| **Runtime** | >19 min | <10 min | <7 min |
| **Success Rate** | 100% | 100% | 100% |
| **DRC Violations** | Unknown | <20 | 0 |
| **Forced Segments** | 0 | 0 | 0 |
| **Avg Path Length** | N/A | <1.3x optimal | <1.1x optimal |

---

## Tools & Infrastructure

### Profiling Scripts
```bash
# Run profiler
./scripts/profile_router_v6.sh --theta-star

# Generate flamegraph
pip install flameprof
python -m cProfile -o router.prof run_router_v6.py --theta-star
flameprof router.prof > router_flamegraph.svg
```

### Benchmarking Harness
```python
# packages/temper-placer/scripts/benchmark_router_v6.py
def benchmark_configuration(config: dict) -> BenchmarkResult:
    """Run router with given config and measure performance."""
    start = time.time()
    result = pipeline.run(pcb_path)
    runtime = time.time() - start

    return BenchmarkResult(
        config=config,
        runtime=runtime,
        success_count=result.success_count,
        failure_count=result.failure_count,
        drc_violations=count_drc_violations(result)
    )

# Run benchmark suite
configs = [
    {"enable_theta_star": False, "enable_smoothing": False},  # Baseline
    {"enable_theta_star": False, "enable_smoothing": True},   # A* + Smoothing
    {"enable_theta_star": "adaptive", "enable_smoothing": True, "theta_timeout": 300},  # Hybrid
]

results = [benchmark_configuration(cfg) for cfg in configs]
print_comparison_table(results)
```

---

## Next Steps

1. **Immediate**: Run Experiment P1 (cProfile) to confirm hotspots
2. **This week**: Implement O1 (Adaptive routing) for quick win
3. **Next week**: Implement O2, O6 for production readiness
4. **Following week**: Advanced optimizations (O3-O5) if needed

**Decision Point**: After O1+O2+O6, if runtime <8 min → production. Otherwise, continue to O3-O5.
