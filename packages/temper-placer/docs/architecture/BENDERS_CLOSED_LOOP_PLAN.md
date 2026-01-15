# Benders Closed-Loop Implementation Plan

## Goal
Create a fully integrated Benders decomposition system where:
- **Master Problem (ILP)**: Optimizes component placement
- **Subproblem (Router)**: Validates routability, reports failures
- **Cut Generation**: Converts routing failures into ILP constraints
- **Loop**: Iterates until all nets route successfully

## Current State

```
ILP Placement ──► Router ──► 14/17 nets succeed, 3 fail
                            (no feedback to ILP)
```

## Target State

```
┌─────────────────────────────────────────────────────────┐
│                    BENDERS LOOP                         │
│                                                         │
│  ┌─────────┐    ┌─────────┐    ┌─────────────────────┐ │
│  │   ILP   │───►│ Router  │───►│ Failure Analysis    │ │
│  │ Master  │    │ Sub-    │    │ - Which nets failed │ │
│  │ Problem │    │ problem │    │ - Where blocked     │ │
│  └────▲────┘    └─────────┘    │ - Which components  │ │
│       │                        └──────────┬──────────┘ │
│       │                                   │            │
│       │         ┌─────────────────────────▼──────────┐ │
│       └─────────┤      Cut Generator                 │ │
│                 │  spacing_between(C1, C2) >= d      │ │
│                 └────────────────────────────────────┘ │
│                                                         │
│  CONVERGES WHEN: All nets route successfully           │
└─────────────────────────────────────────────────────────┘
```

---

## Task 1: Router Failure Reporting

### Current Router Output
```python
PathfindingResult:
    success_count: int
    failure_count: int
    routed_nets: list[str]
    # No detail on WHY nets failed
```

### Required Output
```python
@dataclass
class RoutingFailure:
    net_name: str
    reason: str  # "congestion", "blocked", "no_path", "layer_conflict"
    failed_segment: tuple[str, str]  # (from_pad, to_pad)
    blocking_region: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    blocking_nets: list[str]  # Nets that blocked the path
    attempted_layers: list[str]  # Layers tried

@dataclass
class PathfindingResultV2(PathfindingResult):
    failures: list[RoutingFailure]
```

### Implementation
**File**: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`

1. Modify `attempt_route()` to capture failure details
2. Track which cells were blocked and by which nets
3. Return `RoutingFailure` objects for each failed net

### Effort: ~2-3 hours

---

## Task 2: Failure-to-Component Mapping

### Purpose
Convert routing failures (in grid coordinates) to component pairs (for ILP cuts).

### Logic
```
RoutingFailure:
    net: "I_SENSE"
    blocking_region: (45.2, 32.1, 48.5, 35.0)
    blocking_nets: ["GND", "SW_NODE"]
    
    ↓ Map to components
    
BlockingPair:
    component_a: "U_OPAMP_CT"  (has I_SENSE pad)
    component_b: "Q1"          (has SW_NODE pad, in blocking region)
    required_spacing: 5.0mm    (current: 2.3mm)
```

### Implementation
**File**: `packages/temper-placer/src/temper_placer/placement/benders_failure_mapper.py`

```python
@dataclass
class BlockingPair:
    component_a: str
    component_b: str
    failed_net: str
    current_spacing: float
    required_spacing: float
    confidence: float  # How sure we are this is the blocking pair

def map_failure_to_components(
    failure: RoutingFailure,
    pcb: ParsedPCB,
    component_positions: dict[str, tuple[float, float]]
) -> list[BlockingPair]:
    """
    Map a routing failure to component pairs that need more spacing.
    
    Strategy:
    1. Find components with pads on the failed net
    2. Find components in/near the blocking region
    3. Identify pairs that are too close
    """
```

### Effort: ~2-3 hours

---

## Task 3: Cut Generator Integration

### Purpose
Convert `BlockingPair` objects into ILP constraints.

### Current Cut Generator
We already have `benders_cut_generator.py` that creates `RoutabilityCut` objects.

### Required Changes
Add new cut type: `ROUTER_FAILURE_CUT`

```python
@dataclass
class RouterFailureCut:
    """Cut generated from actual routing failure."""
    blocking_pair: BlockingPair
    min_spacing: float
    iteration: int
    
    def to_ilp_constraint(self) -> str:
        """Generate ILP constraint string."""
        # |x_a - x_b| + |y_a - y_b| >= min_spacing
        # Linearized as:
        # x_a - x_b >= min_spacing - M*(1-d1) - M*(1-d2)
        # etc.
```

### Implementation
**File**: `packages/temper-placer/src/temper_placer/placement/benders_cut_generator.py`

Add method:
```python
def generate_cuts_from_router_failures(
    failures: list[RoutingFailure],
    pcb: ParsedPCB,
    positions: dict[str, tuple[float, float]]
) -> list[RouterFailureCut]:
```

### Effort: ~2 hours

---

## Task 4: Closed-Loop Orchestrator

### Current BendersLoop
```python
def run_benders_optimization(self, ...):
    while iteration < max_iterations:
        # 1. Solve ILP
        placement = self.master.solve()
        
        # 2. Check routability (ultra-fast heuristic)
        is_routable, _ = self._check_routability_ultrafast(placement)
        
        # 3. If routable, done
        if is_routable:
            return placement
        
        # 4. Generate cuts (from max-flow, not router)
        cuts = self._generate_cuts(...)
        self.master.add_cuts(cuts)
```

### Required Changes
```python
def run_benders_optimization(self, ...):
    while iteration < max_iterations:
        # 1. Solve ILP
        placement = self.master.solve()
        
        # 2. Run ACTUAL ROUTER (not heuristic)
        router_result = self._run_router(placement)
        
        # 3. If all nets routed, done
        if router_result.failure_count == 0:
            return placement, router_result
        
        # 4. Map failures to component pairs
        blocking_pairs = self._map_failures_to_components(
            router_result.failures,
            placement
        )
        
        # 5. Generate spacing cuts
        cuts = self._generate_router_failure_cuts(blocking_pairs)
        
        # 6. Add cuts to ILP
        self.master.add_cuts(cuts)
        
        # 7. Continue iteration
```

### Speed Consideration
Full router takes ~35s per iteration. For 5 iterations = ~3 minutes.
This is acceptable for final optimization.

For fast iteration, keep ultra-fast check as "pre-filter":
```python
# Quick pre-check
if not self._check_routability_ultrafast(placement):
    # Add heuristic cuts, don't run full router
    continue

# Passed heuristic, run full router
router_result = self._run_router(placement)
```

### Implementation
**File**: `packages/temper-placer/src/temper_placer/placement/benders_loop.py`

### Effort: ~3-4 hours

---

## Task 5: DRC Integration

### Purpose
Routing success ≠ manufacturable. We need real KiCad DRC validation.

### Current State
We have `kicad_drc.py` with `run_drc()` function, but it's not integrated into the loop.

### DRC Error Categories

| Category | Source | Actionable? |
|----------|--------|-------------|
| `tracks_crossing` | Router bug | Yes - re-route |
| `clearance` | Traces too close | Yes - widen spacing |
| `unconnected_items` | Failed nets | Yes - re-route |
| `lib_footprint_issues` | KiCad library | No - ignore |
| `silk_over_copper` | Cosmetic | No - ignore |

### Implementation

**File**: `packages/temper-placer/src/temper_placer/placement/benders_loop.py`

```python
from temper_placer.io.kicad_drc import run_drc, DRCResult

def _check_drc(self, pcb_file: Path) -> tuple[bool, list[DRCViolation]]:
    """
    Run KiCad DRC and return actionable violations.
    """
    result = run_drc(pcb_file)
    
    # Filter to actionable violations only
    actionable_types = {
        "tracks_crossing",
        "clearance", 
        "unconnected_items",
        "short",
        "track_dangling",
    }
    
    actionable = [v for v in result.violations 
                  if v.type in actionable_types]
    
    return len(actionable) == 0, actionable

def _map_drc_to_cuts(
    self, 
    violations: list[DRCViolation]
) -> list[RoutabilityCut]:
    """
    Convert DRC violations to ILP cuts.
    
    - clearance violation → increase spacing between nearby components
    - tracks_crossing → push apart components on those nets
    """
```

### Updated Loop Logic

```python
def run_benders_optimization(self, ...):
    while iteration < max_iterations:
        # 1. Solve ILP
        placement = self.master.solve()
        
        # 2. Quick pre-filter
        if not self._check_routability_ultrafast(placement):
            cuts = self._generate_heuristic_cuts(...)
            self.master.add_cuts(cuts)
            continue
        
        # 3. Run full router
        router_result = self._run_router(placement)
        
        if router_result.failure_count > 0:
            # Generate cuts from routing failures
            cuts = self._generate_router_failure_cuts(...)
            self.master.add_cuts(cuts)
            continue
        
        # 4. ✅ NEW: Run KiCad DRC
        drc_clean, violations = self._check_drc(output_pcb)
        
        if not drc_clean:
            # Generate cuts from DRC violations
            cuts = self._map_drc_to_cuts(violations)
            self.master.add_cuts(cuts)
            continue
        
        # 5. SUCCESS: All nets routed AND DRC clean
        return OptimizationResult(
            placement=placement,
            router_result=router_result,
            drc_result=drc_result,
            iterations=iteration,
        )
```

### Effort: ~2-3 hours

---

## Task 6: End-to-End Test

### Test Case
```python
def test_benders_closed_loop_drc_clean():
    """
    Verify Benders loop produces DRC-clean output.
    """
    loop = BendersLoop(pcb_file="temper_placed.kicad_pcb")
    
    result = loop.run_benders_optimization(
        max_iterations=15,
        use_router_feedback=True,
        require_drc_clean=True,  # NEW
    )
    
    # All signal nets routed
    assert result.router_result.failure_count == 0
    assert result.router_result.success_count == 17
    
    # DRC clean (excluding footprint issues)
    assert result.drc_result.actionable_errors == 0
    
    # Convergence
    assert result.iterations_used <= 15
    print(f"Converged in {result.iterations_used} iterations")
    print(f"DRC: {result.drc_result.total_errors} total, "
          f"{result.drc_result.actionable_errors} actionable")
```

### Success Criteria
- [ ] 17/17 signal nets route successfully
- [ ] 0 actionable DRC errors (clearance, shorts, crossings)
- [ ] Loop converges in reasonable iterations (<15)
- [ ] Total time < 10 minutes
- [ ] Output PCB is manufacturable

### Effort: ~1-2 hours

---

## Implementation Order

```
Task 1 (Router Reporting) ──► Task 2 (Failure Mapping) ──┐
                                                          │
                                                          ▼
                              Task 3 (Cut Generator) ◄────┘
                                      │
                                      ▼
                              Task 4 (Orchestrator)
                                      │
                                      ▼
                              Task 5 (DRC Integration)
                                      │
                                      ▼
                              Task 6 (End-to-End Test)
```

**Dependencies:**
- Task 2 depends on Task 1 (needs failure data)
- Task 3 depends on Task 2 (needs blocking pairs)
- Task 4 depends on Tasks 1, 2, 3
- Task 5 depends on Task 4 (DRC validates router output)
- Task 6 depends on Task 5

---

## Estimated Total Effort

| Task | Effort | Risk |
|------|--------|------|
| 1. Router Failure Reporting | 2-3h | Medium (touches core router) |
| 2. Failure-to-Component Mapping | 2-3h | Low (new module) |
| 3. Cut Generator Integration | 2h | Low (extends existing) |
| 4. Closed-Loop Orchestrator | 3-4h | Medium (integration) |
| 5. DRC Integration | 2-3h | Low (uses existing kicad_drc.py) |
| 6. End-to-End Test | 1-2h | Low |
| **Total** | **12-17h** | |

---

## Risk Mitigation

### Risk 1: Router failures don't map cleanly to component pairs
**Mitigation**: Use confidence scores, generate multiple candidate pairs

### Risk 2: Cuts don't improve routability
**Mitigation**: Increase spacing aggressively (2x estimated), log cut effectiveness

### Risk 3: Loop doesn't converge
**Mitigation**: 
- Max iteration limit
- Detect oscillation (same failures repeating)
- Fall back to manual intervention suggestions

### Risk 4: Too slow for practical use
**Mitigation**:
- Use ultra-fast pre-filter
- Cache routing results
- Parallelize where possible

---

## Files to Create/Modify

### New Files
- `benders_failure_mapper.py` - Map failures to components
- `router_failure_types.py` - Data classes for failure info
- `benders_drc_mapper.py` - Map DRC violations to cuts

### Modified Files
- `astar_pathfinding.py` - Add failure reporting
- `benders_cut_generator.py` - Add router failure cuts + DRC cuts
- `benders_loop.py` - Closed-loop orchestration with DRC gate
- `pipeline.py` - Expose failure details in result
- `kicad_drc.py` - Add violation categorization (actionable vs cosmetic)

### Test Files
- `test_failure_mapper.py`
- `test_router_failure_cuts.py`
- `test_drc_mapper.py`
- `test_closed_loop_drc_clean.py`
