# maze_router Refactoring Tickets

## EPIC: maze_router: Refactor monolithic functions into composable, testable modules

**Type:** epic
**Labels:** router, refactor, architecture, testability
**Priority:** P2

### Summary

Refactor the 2000+ line `maze_router.py` into a set of small, focused modules with single responsibilities. The goal is elegant, DRY, YAGNI code that is easy to test, reason about, and maintain.

### Current State

The `MazeRouter` class violates many software design principles:
- `_get_neighbor_cost`: 220 lines doing 6+ different things
- `_get_neighbors`: 40+ lines with nested mode logic
- `_find_path_python_adaptive`: Mixed pathfinding and cost calculation
- Duplicated `_world_to_grid` function (lines 822 and 1426)
- DRC logic embedded throughout routing logic
- No separation between pathfinding, validation, and state management

### Target Architecture

```
maze_router/
  ├── __init__.py           # Main MazeRouter class (thin orchestrator)
  ├── cost/                 # Cost calculation modules
  │   ├── __init__.py
  │   ├── neighbor_cost.py  # _get_neighbor_cost broken into focused functions
  │   ├── layer_cost.py     # LayerCostCalculator class
  │   └── heuristic.py      # Heuristic strategy pattern
  ├── validation/           # DRC and validation modules
  │   ├── __init__.py
  │   └── drc_validator.py  # Dedicated DRCValidator class
  ├── grid/                 # Grid utilities
  │   ├── __init__.py
  │   └── converter.py      # GridConverter for coordinate transforms
  ├── occupancy/            # Occupancy management
  │   ├── __init__.py
  │   └── manager.py        # OccupancyManager class
  ├── neighbors/            # Neighbor generation
  │   ├── __init__.py
  │   └── generator.py      # Neighbor generation functions
  └── difficulty/           # Cell difficulty calculation
      ├── __init__.py
      └── calculator.py     # Difficulty calculation functions
```

### Principles

1. **Single Responsibility**: Each function does one thing well
2. **Short Functions**: 5-30 lines per function
3. **Testable**: Every function testable in isolation
4. **Composable**: Functions can be mixed and matched
5. **DRY**: No logic duplication
6. **YAGNI**: Only build what we need
7. **Functional**: Prefer pure functions where possible

---

## TASK: Refactor _get_neighbor_cost into focused single-responsibility functions

**Type:** task
**Labels:** router, refactor, high-priority
**Priority:** P2
**Parent:** maze_router-refactor-epic

### Summary

Split the 220-line `_get_neighbor_cost` function into 6-8 focused functions, each with a single responsibility.

### Current State

`_get_neighbor_cost` (lines 579-798) handles:
1. Base layer cost calculation
2. Wrong-way penalty
3. Difficulty gradient
4. History/congestion costs
5. Soft blocking with net isolation
6. Strategy multiplier
7. Layer balance penalty
8. Dynamic via cost
9. DRC via placement check
10. DRC track segment check

### Target Functions

1. `compute_base_cost(neighbor, net_rules) -> float`
2. `compute_wrong_way_penalty(current, neighbor) -> float`
3. `compute_sharing_penalty(neighbor, current_net) -> float`
4. `compute_layer_balance_penalty(neighbor) -> float`
5. `compute_via_penalty(current, neighbor, congestion) -> float`
6. `check_via_drc(neighbor) -> tuple[bool, str]`
7. `check_track_drc(current, neighbor) -> tuple[bool, str]`
8. `get_neighbor_cost(current, neighbor, cost_map, p_scale) -> float` (orchestrator)

### Acceptance Criteria

- [ ] No function exceeds 50 lines
- [ ] Each function has a single responsibility
- [ ] All functions are pure where possible
- [ ] Tests cover each function individually
- [ ] Original `_get_neighbor_cost` behavior preserved

---

## TASK: Extract path cost calculation from A* into pure functions

**Type:** task
**Labels:** router, refactor, algorithm
**Priority:** P2
**Parent:** maze_router-refactor-epic

### Summary

Extract path cost and heuristic calculations from `_find_path_python_adaptive` into testable pure functions.

### Current State

`_find_path_python_adaptive` (lines 1717-1783) mixes:
- A* loop logic
- Cost calculation (`_get_neighbor_cost`)
- Heuristic lookup (`dist_map` vs fallback)
- Path reconstruction

### Target Functions

1. `compute_g_score(current_g, move_cost) -> float`
2. `compute_h_score(neighbor, end_cell, dist_map) -> float`
3. `compute_f_score(g_score, h_score) -> float`
4. `get_heuristic(neighbor, end_cell, dist_map) -> float`
5. `reconstruct_path(came_from, current) -> list[GridCell]`

### Acceptance Criteria

- [ ] Path cost logic separated from A* loop
- [ ] Heuristic selection is a strategy pattern
- [ ] Path reconstruction is a pure function
- [ ] Each function can be tested independently
- [ ] A* loop becomes ~30 lines

---

## TASK: Create OccupancyManager class for cell ownership

**Type:** task
**Labels:** router, refactor, state-management
**Priority:** P3
**Parent:** maze_router-refactor-epic

### Summary

Extract occupancy and net ownership tracking into a dedicated `OccupancyManager` class.

### Current State

Occupancy logic scattered across:
- `rip_up_net` (lines 475-500)
- `_mark_path_occupied` (not shown, but exists)
- `_get_neighbor_cost` (net ownership check)
- `register_pre_routes` (lines 502-546)

### Target Class

```python
class OccupancyManager:
    def __init__(self, grid_size, num_layers):
        self.occupancy = np.zeros(...)
        self.net_occupancy = {}  # (gx, gy, layer) -> set[str]
        self.cell_owner = {}     # (gx, gy, layer) -> str
        self.owner_grid = np.zeros(...)

    def block_cells(self, cells, net_name): ...
    def unblock_cells(self, cells, net_name): ...
    def mark_routed(self, cells, net_name): ...
    def rip_up_net(self, net_name): ...
    def get_cell_owner(self, cell) -> str | None: ...
    def is_blocked(self, cell) -> bool: ...
    def is_occupied(self, cell) -> bool: ...
```

### Acceptance Criteria

- [ ] All occupancy operations go through OccupancyManager
- [ ] Net isolation enforced consistently
- [ ] Occupancy and ownership state always consistent
- [ ] Tests verify state transitions

---

## TASK: Extract cell difficulty calculation into separate module

**Type:** task
**Labels:** router, refactor, difficulty
**Priority:** P3
**Parent:** maze_router-refactor-epic

### Summary

Refactor `_get_cell_difficulty` and `_compute_density_map` into focused functions.

### Current State

- `_get_cell_difficulty` (lines 548-577): Mixed proximity + density
- `_compute_density_map` (lines 1335-1375): Vectorized density computation
- `_compute_local_density` (lines 1327-1333): Single-point density

### Target Functions

1. `compute_proximity_difficulty(cell, occupancy, grid_size) -> float`
2. `compute_density_difficulty(cell, density_map) -> float`
3. `get_cell_difficulty(cell, density_map, occupancy, grid_size) -> float`
4. `compute_density_map(positions, grid_size, cell_size, origin, radius_mm) -> np.ndarray`

### Acceptance Criteria

- [ ] Each difficulty factor computed separately
- [ ] Density map can be computed independently
- [ ] O(1) difficulty lookup preserved
- [ ] Tests cover all difficulty calculations

---

## TASK: Create DRCValidator class for validation logic

**Type:** task
**Labels:** router, refactor, validation
**Priority:** P2
**Parent:** maze_router-refactor-epic

### Summary

Extract all DRC checking logic into a dedicated `DRCValidator` class.

### Current State

DRC checks embedded in:
- `_get_neighbor_cost` (via and track validation)
- `_register_routed_path` (Track/Via object creation)
- `_check_class_clearance` (HV/LV separation)

### Target Class

```python
class DRCValidator:
    def __init__(self, drc_oracle, rules, cell_size, origin, neckdown_mask):
        ...

    def can_place_track(self, start, end, layer, net, width, neckdown) -> tuple[bool, str]: ...
    def can_place_via(self, x, y, net, diameter) -> tuple[bool, str]: ...
    def check_class_clearance(self, cell, current_class, class_grid) -> bool: ...
    def validate_path(self, path, net) -> list[str]: ...
    def register_path(self, path, net): ...
```

### Acceptance Criteria

- [ ] All DRC logic in one place
- [ ] Consistent validation across all code paths
- [ ] Can mock DRCValidator for fast tests
- [ ] DRC rules can be swapped/changed easily

---

## TASK: Extract layer cost logic into LayerCostCalculator class

**Type:** task
**Labels:** router, refactor, cost
**Priority:** P3
**Parent:** maze_router-refactor-epic

### Summary

Refactor `get_layer_cost` into a dedicated `LayerCostCalculator` class.

### Current State

`get_layer_cost` (lines 1910-1933) handles:
- Default layer preferences
- Net class layer rules
- Routing strategy costs

### Target Class

```python
class LayerCostCalculator:
    def __init__(self, layer_stackup, num_layers):
        ...

    def get_cost_for_net(self, net_rules, layer_idx) -> float: ...
    def get_preferred_layers(self, net_rules) -> list[int]: ...
    def is_surface_layer(self, layer_idx) -> bool: ...
    def is_plane_layer(self, layer_idx) -> bool: ...
```

### Acceptance Criteria

- [ ] Layer cost logic isolated
- [ ] Works with or without layer_stackup
- [ ] Routing strategy handled consistently
- [ ] Tests cover all rule combinations

---

## TASK: Create GridConverter for coordinate transformations

**Type:** task
**Labels:** router, refactor, utilities
**Priority:** P4
**Parent:** maze_router-refactor-epic

### Summary

Extract coordinate conversion logic into a dedicated `GridConverter` class.

### Current State

- `_world_to_grid` exists twice (lines 822 and 1426)
- Conversion logic duplicated with slight variations
- No centralized coordinate handling

### Target Class

```python
class GridConverter:
    def __init__(self, grid_size, cell_size, origin):
        self.grid_size = grid_size
        self.cell_size = cell_size
        self.origin = origin

    def world_to_grid(self, x, y) -> tuple[int, int]: ...
    def world_to_grid_cell(self, x, y, layer) -> GridCell: ...
    def grid_to_world(self, gx, gy) -> tuple[float, float]: ...
    def grid_to_world_center(self, gx, gy, layer) -> tuple[float, float]: ...
    def clamp_to_grid(self, gx, gy) -> tuple[int, int]: ...
```

### Acceptance Criteria

- [ ] Single source of truth for conversions
- [ ] No duplicated conversion logic
- [ ] Clamping consistent across all uses
- [ ] Tests verify edge cases (out of bounds)

---

## TASK: Extract neighbor generation into focused functions

**Type:** task
**Labels:** router, refactor, algorithm
**Priority:** P2
**Parent:** maze_router-refactor-epic

### Summary

Refactor `_get_neighbors` into focused neighbor generation functions.

### Current State

`_get_neighbors` (lines 1935-1977) handles:
- Cardinal direction neighbors
- Layer change neighbors
- Mode logic (plane layer restrictions)
- Occupancy filtering

### Target Functions

1. `get_cardinal_neighbors(cell, occupancy, grid_size, soft_blocking) -> list[GridCell]`
2. `get_layer_neighbors(cell, occupancy, grid_size, allowed_layers, soft_blocking) -> list[GridCell]`
3. `get_all_neighbors(cell, occupancy, grid_size, allow_layer_change, allowed_layers, soft_blocking, layer_stackup) -> list[GridCell]`

### Acceptance Criteria

- [ ] Each neighbor type generated separately
- [ ] Can mix and match as needed
- [ ] Tests verify all boundary conditions
- [ ] Plane layer restrictions isolated

---

## TASK: Create heuristic strategy pattern for A*

**Type:** task
**Labels:** router, refactor, algorithm
**Priority:** P3
**Parent:** maze_router-refactor-epic

### Summary

Refactor heuristic calculation into a strategy pattern for flexibility.

### Current State

- `_heuristic` (line 1514): Manhattan distance
- `_compute_distance_map` (lines 1517-1593): BFS distance map
- Mixed in `_find_path_python_adaptive`

### Target Architecture

```python
class HeuristicStrategy(ABC):
    @abstractmethod
    def compute(self, current: GridCell, goal: GridCell) -> float: ...
    @abstractmethod
    def precompute(self, goal: GridCell, occupancy: np.ndarray) -> np.ndarray | None: ...

class ManhattanHeuristic(HeuristicStrategy): ...

class DistanceMapHeuristic(HeuristicStrategy):
    def __init__(self, has_numba=False): ...
    def precompute(self, goal, occupancy) -> np.ndarray: ...

class AdaptiveHeuristic(HeuristicStrategy):
    def __init__(self, heuristic: HeuristicStrategy, distance_map_heuristic: HeuristicStrategy): ...
```

### Acceptance Criteria

- [ ] Heuristic can be swapped at runtime
- [ ] Distance map caching works with any strategy
- [ ] Numba fallback preserved
- [ ] Tests verify all strategies produce valid paths

---

## TASK: Create NetRouter orchestrator class

**Type:** task
**Labels:** router, refactor, architecture
**Priority:** P2
**Parent:** maze_router-refactor-epic

### Summary

Create a `NetRouter` class that orchestrates routing for a single net, reducing `route_net_adaptive` complexity.

### Current State

`route_net_adaptive` (lines 1785-1907) handles:
- Pin validation
- Layer assignment interpretation
- Pathfinding calls
- Pin unblocking/restoring
- Path marking
- Result construction

### Target Class

```python
class NetRouter:
    def __init__(self, occupancy_manager, drc_validator, heuristic_strategy):
        ...

    def route(self, net_name, pin_positions, assignment) -> RoutePath: ...

    def _validate_pins(self, pins) -> bool: ...
    def _find_paths(self, pins, assignment) -> list[list[GridCell]]: ...
    def _merge_paths(self, paths) -> list[GridCell]: ...
    def _mark_path_routed(self, path, net_name): ...
    def _construct_result(self, path, net_name) -> RoutePath: ...
```

### Acceptance Criteria

- [ ] Net routing logic isolated
- [ ] Each step can be tested independently
- [ ] Pin unblocking centralized
- [ ] Result construction testable in isolation

---

## TASK: Migrate maze_router.py to new modular architecture

**Type:** task
**Labels:** router, refactor, migration
**Priority:** P2
**Parent:** maze_router-refactor-epic

### Summary

Perform the actual file reorganization and migration to the new modular architecture.

### Steps

1. Create new directory structure:
   ```
   packages/temper-placer/src/temper_placer/routing/maze_router/
   ```

2. Create empty `__init__.py` files for each subpackage

3. Migrate code in dependency order (no cycles):
   - grid/converter.py (no dependencies)
   - difficulty/calculator.py (grid only)
   - neighbors/generator.py (grid only)
   - occupancy/manager.py (grid only)
   - cost/layer_cost.py (no routing deps)
   - validation/drc_validator.py (grid + difficulty)
   - cost/neighbor_cost.py (all above)
   - heuristic.py (depends on grid)
   - NetRouter (depends on all)
   - Update maze_router/__init__.py to import and re-export

4. Update all imports in:
   - Test files
   - Fast router integration
   - Any other consumers

5. Run full test suite

### Acceptance Criteria

- [ ] All tests pass
- [ ] No import cycles
- [ ] Original API preserved (backward compatible)
- [ ] New module structure matches target architecture
