# Initial Placement from Topology - Design Document

**Task**: temper-5zp.4  
**Epic**: temper-5zp (Epic 3: Topological Placement Phase)  
**Status**: In Progress

## Overview

Generate initial (x, y) coordinates from topological relationships to provide a good starting point for geometric optimization.

### Dependencies
- temper-5zp.1: TopologicalGraph (adjacency clusters, separation detection)
- temper-5zp.2: ConstraintPropagator (inferred distance bounds)
- temper-5zp.3: ZoneSolver (component → zone assignments)

### Output
- Initial positions for all components
- Respects zone boundaries
- Adjacent components placed close together
- Separated components placed apart
- Feeds into ForceDirectedHeuristic for refinement

---

## Architecture

### Module Structure

```
packages/temper-placer/
├── src/temper_placer/
│   ├── topological/
│   │   ├── __init__.py              # Add exports
│   │   ├── initial_placement.py     # Core placement logic (~250 LOC)
│   │   └── force_refinement.py      # Force simulation (~150 LOC)
│   └── heuristics/
│       └── topological_init.py      # Heuristic wrapper (~80 LOC)
└── tests/
    └── topological/
        ├── test_initial_placement.py    # Core tests (~300 LOC)
        ├── test_force_refinement.py     # Force tests (~200 LOC)
        └── test_topological_init_heuristic.py  # Heuristic tests (~150 LOC)
```

---

## Data Structures

### InitialPlacement (Result)

```python
@dataclass
class InitialPlacement:
    """Result of initial placement generation.
    
    Attributes:
        positions: Component ref → (x, y) center position in mm
        zone_assignments: Component ref → zone name
        clusters: List of component clusters (sets of refs)
        rotation_hints: Component ref → suggested rotation (0, 90, 180, 270)
        warnings: Non-fatal issues encountered
    """
    positions: dict[str, tuple[float, float]]
    zone_assignments: dict[str, str]
    clusters: list[set[str]]
    rotation_hints: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
```

### PlacementError (Exception)

```python
class PlacementError(Exception):
    """Raised when placement is impossible.
    
    Examples:
    - Component has no valid zone (conflicting constraints)
    - Zone too small for assigned components
    - Circular dependency in constraints
    """
    pass
```

---

## Algorithms

### 1. Zone-Based Initial Placement

**Goal**: Distribute components within their assigned zones.

**Algorithm**: Circular layout around zone center

```python
def place_components_in_zone(
    zone: Zone,
    components: list[str],
    component_sizes: dict[str, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """Place components in circular arrangement within zone.
    
    For n components:
    - 1 component: place at zone center
    - 2+ components: place on circle around center
    
    Circle radius = min(zone.width, zone.height) / 4
    (leaves room for spreading during force refinement)
    
    Args:
        zone: Target zone with bounds
        components: Component refs to place
        component_sizes: Component ref → (width, height) in mm
        
    Returns:
        Dict mapping component ref → (x, y) position
        
    Raises:
        PlacementError: If zone is too small for components
    """
```

**Properties**:
- Deterministic (same input → same output)
- No overlaps guaranteed for small component counts
- Leaves headroom for force refinement

### 2. Cluster Identification

**Goal**: Group components that must stay together (transitively adjacent).

**Algorithm**: Connected components via BFS

```python
def identify_clusters(
    graph: TopologicalGraph,
    components: list[str],
) -> list[set[str]]:
    """Identify adjacency clusters.
    
    Components that are transitively adjacent form a cluster.
    Uses TopologicalGraph.get_adjacency_cluster() internally.
    
    Args:
        graph: Topological graph with adjacency edges
        components: All component refs
        
    Returns:
        List of clusters (sets of component refs)
        Each component appears in exactly one cluster.
        Singleton clusters for isolated components.
    """
```

### 3. Cluster Placement

**Goal**: Place entire clusters together, respecting zone assignments.

**Algorithm**: 
1. For each cluster, find the zone(s) where members are assigned
2. If all members in same zone: place cluster at zone subregion
3. If members span zones: place at zone boundaries (warn)

```python
def place_cluster(
    cluster: set[str],
    zone: Zone,
    graph: TopologicalGraph,
    component_sizes: dict[str, tuple[float, float]],
    cluster_index: int,
    total_clusters: int,
) -> dict[str, tuple[float, float]]:
    """Place a cluster of components within a zone.
    
    Subdivides zone into regions based on total cluster count,
    then places this cluster in its assigned region.
    
    Within the cluster, uses force-directed micro-layout to
    position members respecting adjacency constraints.
    
    Args:
        cluster: Set of component refs in this cluster
        zone: Zone where cluster should be placed
        graph: Topological graph for adjacency info
        component_sizes: Component dimensions
        cluster_index: Which cluster this is (0-based)
        total_clusters: Total clusters in this zone
        
    Returns:
        Dict mapping component ref → (x, y) position
    """
```

### 4. Force Refinement

**Goal**: Refine positions to better satisfy distance constraints.

**Algorithm**: Spring-embedder with:
- Attraction for adjacent components (pull toward target distance)
- Repulsion for separated components (push apart if too close)
- Boundary forces (keep components in assigned zones)

```python
def apply_force_refinement(
    positions: dict[str, tuple[float, float]],
    graph: TopologicalGraph,
    zones: dict[str, Zone],
    zone_assignments: dict[str, str],
    iterations: int = 100,
    learning_rate: float = 0.1,
    backend: str = "numpy",  # or "jax"
) -> dict[str, tuple[float, float]]:
    """Refine positions using force-directed simulation.
    
    Forces:
    1. Adjacency attraction: F = k * (distance - target)
       - Pulls adjacent components toward target max_distance
       
    2. Separation repulsion: F = -k / distance (if distance < min)
       - Pushes separated components apart
       
    3. Boundary containment: F = -k * overshoot
       - Pushes components back into zone if they escape
    
    Args:
        positions: Initial positions
        graph: Topological graph with distance constraints
        zones: Zone name → Zone object
        zone_assignments: Component → zone name
        iterations: Number of simulation steps
        learning_rate: Step size (damping factor)
        backend: "numpy" or "jax"
        
    Returns:
        Refined positions
    """
```

**NumPy Implementation**:
```python
def _force_refine_numpy(
    positions: np.ndarray,  # (N, 2)
    adjacencies: list[tuple[int, int, float]],  # (i, j, max_dist)
    separations: list[tuple[int, int, float]],  # (i, j, min_dist)
    zone_bounds: np.ndarray,  # (N, 4) per-component [xmin, ymin, xmax, ymax]
    iterations: int,
    lr: float,
) -> np.ndarray:
```

**JAX Implementation** (optional):
```python
@jax.jit
def _force_step_jax(
    positions: jnp.ndarray,
    adjacency_matrix: jnp.ndarray,  # (N, N) with target distances
    separation_matrix: jnp.ndarray,  # (N, N) with min distances
    zone_bounds: jnp.ndarray,
    lr: float,
) -> jnp.ndarray:
```

### 5. Main Generation Function

```python
def generate_initial_placement(
    graph: TopologicalGraph,
    zone_assignment: ZoneAssignment,
    zones: list[Zone],
    component_sizes: dict[str, tuple[float, float]],
    board_bounds: tuple[float, float, float, float] | None = None,
    force_iterations: int = 100,
    backend: str = "numpy",
) -> InitialPlacement:
    """Generate initial component positions from topological analysis.
    
    Pipeline:
    1. Validate inputs (all components have zones, zones exist)
    2. Identify adjacency clusters
    3. Group clusters by zone
    4. Place clusters within zones (circular layout)
    5. Apply force refinement
    6. Return result
    
    Args:
        graph: Topological graph with adjacency/separation edges
        zone_assignment: Result from ZoneSolver
        zones: Available placement zones
        component_sizes: Component ref → (width, height)
        board_bounds: Optional fallback if no zones (xmin, ymin, xmax, ymax)
        force_iterations: Force refinement iterations
        backend: "numpy" or "jax" for force simulation
        
    Returns:
        InitialPlacement with positions and metadata
        
    Raises:
        PlacementError: If placement is impossible
    """
```

---

## Heuristic Wrapper

```python
class TopologicalInitializationHeuristic(Heuristic):
    """Initialize placement from topological analysis.
    
    This heuristic runs BEFORE ForceDirectedHeuristic to provide
    semantically-aware initial positions based on:
    - Zone assignments (components in correct regions)
    - Adjacency clusters (related components grouped)
    - Separation constraints (isolated components apart)
    
    The positions are then refined by ForceDirectedHeuristic.
    """
    
    def __init__(
        self,
        force_iterations: int = 100,
        backend: str = "numpy",
    ):
        self._force_iterations = force_iterations
        self._backend = backend
    
    @property
    def name(self) -> str:
        return "topological_initialization"
    
    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.INITIALIZATION
    
    @property
    def description(self) -> str:
        return "Initialize placement from topological constraints"
    
    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Apply topological initialization.
        
        Steps:
        1. Build TopologicalGraph from PCL constraints
        2. Run ZoneSolver to assign components to zones
        3. Generate initial placement
        4. Convert to HeuristicResult
        """
```

---

## Test Plan

### Unit Tests: initial_placement.py

| Test | Description | Assertions |
|------|-------------|------------|
| `test_place_single_component_at_zone_center` | One component in zone | Position at zone.center ± tolerance |
| `test_place_two_components_opposite` | Two components in zone | On circle, 180° apart |
| `test_place_multiple_components_circular` | N components in zone | Evenly spaced on circle |
| `test_zone_too_small_raises_error` | Components larger than zone | Raises PlacementError |
| `test_empty_components_list` | No components | Returns empty dict |
| `test_respects_component_sizes` | Different sized components | No overlaps at boundary |
| `test_identify_clusters_single_component` | Isolated component | Singleton cluster |
| `test_identify_clusters_pair` | Two adjacent components | One cluster with both |
| `test_identify_clusters_transitive` | A-B, B-C adjacent | One cluster {A, B, C} |
| `test_identify_clusters_separate` | A-B adjacent, C isolated | Two clusters |
| `test_identify_clusters_multiple` | Complex graph | Correct cluster count |
| `test_place_cluster_single_zone` | Cluster in one zone | All positions in zone bounds |
| `test_place_cluster_respects_adjacency` | Adjacent components | Distance ≤ max_distance |
| `test_cluster_subdivision` | Multiple clusters in zone | Non-overlapping regions |
| `test_generate_placement_integration` | Full pipeline | Valid positions for all |
| `test_unassigned_components_raises` | Component without zone | Raises PlacementError |
| `test_missing_zone_raises` | Zone in assignment doesn't exist | Raises PlacementError |
| `test_no_zones_uses_board_bounds` | No zones, board_bounds given | Uses board as implicit zone |
| `test_deterministic_output` | Same input twice | Identical output |

### Unit Tests: force_refinement.py

| Test | Description | Assertions |
|------|-------------|------------|
| `test_no_forces_stable` | No constraints | Positions unchanged |
| `test_adjacency_attraction` | Two adjacent components far apart | Move closer |
| `test_adjacency_at_target_stable` | Already at target distance | Stay approximately same |
| `test_separation_repulsion` | Two separated components too close | Move apart |
| `test_separation_satisfied_stable` | Already far enough | Stay approximately same |
| `test_boundary_containment` | Component outside zone | Pushed back in |
| `test_mixed_forces_converge` | Complex scenario | Final positions satisfy more constraints |
| `test_convergence_iterations` | Check convergence | Energy decreases over iterations |
| `test_numpy_backend_works` | backend="numpy" | No errors, valid output |
| `test_jax_backend_works` | backend="jax" | No errors, valid output |
| `test_backends_produce_similar_results` | Same input both backends | Positions within tolerance |
| `test_learning_rate_effect` | Different learning rates | Higher lr = faster but less stable |
| `test_zero_iterations` | iterations=0 | Returns input unchanged |
| `test_large_component_count` | 100 components | Completes in reasonable time |

### Unit Tests: topological_init_heuristic.py

| Test | Description | Assertions |
|------|-------------|------------|
| `test_heuristic_name` | Check name property | Returns "topological_initialization" |
| `test_heuristic_priority` | Check priority | Returns INITIALIZATION |
| `test_heuristic_apply_empty` | Empty netlist | Success with no placements |
| `test_heuristic_apply_simple` | Simple netlist with zones | Valid HeuristicResult |
| `test_heuristic_respects_fixed` | Fixed components | Fixed components not moved |
| `test_heuristic_updates_context` | Apply heuristic | current_placements updated |
| `test_heuristic_with_pcl_constraints` | PCL with adjacency | Adjacency respected |
| `test_heuristic_integration_pipeline` | In full pipeline | Runs before force-directed |
| `test_heuristic_failure_handling` | Invalid constraints | Returns success=False |
| `test_heuristic_confidence_score` | Check confidence | Returns reasonable confidence (0.4-0.6) |

---

## Edge Cases

1. **Empty input**: No components → empty result
2. **Single component**: Placed at zone center
3. **No zones defined**: Use board bounds as implicit zone
4. **Zone smaller than component**: Raise PlacementError
5. **Circular adjacency**: A-B-C-A all adjacent → single cluster
6. **Conflicting constraints**: Adjacent AND separated → use propagated bounds
7. **Component in multiple zones**: Invalid (should be caught by ZoneSolver)
8. **All components in one zone**: All placed in that zone
9. **Empty zone**: Zone gets no components (valid)
10. **Overlapping zones**: Component goes to first matching zone

---

## Performance Considerations

### Complexity

| Operation | Time Complexity | Space Complexity |
|-----------|-----------------|------------------|
| Cluster identification | O(V + E) | O(V) |
| Zone placement | O(n) per zone | O(n) |
| Force refinement (NumPy) | O(n² × iterations) | O(n²) |
| Force refinement (JAX) | O(n² × iterations) | O(n²) but GPU |

For typical Temper board (50-100 components), all operations complete in <100ms.

### When to Use JAX

JAX backend recommended when:
- Component count > 200
- Force iterations > 500
- GPU available

NumPy backend preferred when:
- Component count < 100
- Debugging/testing
- No GPU

---

## Integration Points

### With Existing Heuristics

```python
# In heuristics/pipeline.py
DEFAULT_HEURISTICS = [
    TopologicalInitializationHeuristic(),  # NEW: Run first
    SpectralLayoutHeuristic(),             # Global layout
    ForceDirectedHeuristic(),              # Refinement
    # ... rest of pipeline
]
```

### With PCL

```python
# TopologicalInitHeuristic.apply()
from temper_placer.pcl.parser import parse_pcl_file
from temper_placer.topological import (
    TopologicalGraph,
    ConstraintPropagator,
    ZoneSolver,
    generate_initial_placement,
)

pcl = parse_pcl_file(constraints_path)
graph = TopologicalGraph.from_pcl(pcl)
propagator = ConstraintPropagator(graph)
propagator.propagate()
solver = ZoneSolver(zones, pcl.constraints, component_refs)
assignment = solver.solve()
placement = generate_initial_placement(graph, assignment, zones, sizes)
```

---

## Acceptance Criteria

- [ ] All unit tests pass (50+ tests)
- [ ] Integration with ZoneSolver works
- [ ] Integration with TopologicalGraph works
- [ ] Heuristic runs in pipeline before ForceDirected
- [ ] Positions are within zone bounds
- [ ] Adjacent components are placed close
- [ ] Separated components are placed apart
- [ ] Deterministic output (same seed → same result)
- [ ] Performance: <100ms for 100 components
- [ ] Documentation complete

---

## Open Questions (Resolved)

1. ~~Should this run before or after ForceDirected?~~ → **Before** (provides semantic layout)
2. ~~What about unassigned components?~~ → **Raise PlacementError** (fail fast)
3. ~~JAX or NumPy?~~ → **Both**, NumPy default, JAX optional
