# Temper Pipeline Refactoring Plan

**Version:** 1.2
**Date:** 2026-01-03
**Status:** Draft
**Author:** AI Assistant

---

## Key Findings

| Category | Issues | Priority |
|----------|--------|----------|
| **State Management** | 11+ fragmented state classes, no versioning | P0 |
| **Exception Handling** | 7 bare `except:` blocks swallowing errors | P0 |
| **Orchestration** | Shell scripts with no state/recovery | P0 |
| **Constraints** | Dual YAML/PCL systems, incomplete loss bridge | P1 |
| **Routing** | 9+ independent router APIs | P1 |
| **Testing** | No integration/property-based tests | P2 |
| **Observability** | No tracing/metrics | P2 |
| **Performance** | Python bottlenecks in hot paths | P2 |

### Recommended Approach

- **Workflow Engine:** Temporal (lightweight, durable, Python-native)
- **State Model:** SerializableMixin base class with versioning
- **Constraint System:** PCL-only (deprecate YAML)
- **Router API:** Factory pattern for consistent instantiation
- **Documentation:** Decision log in plan
- **Acceleration Path:** Rust/Numba for hot paths (post-refactoring)
  - State serialization: 5-10x speedup
  - Loss functions: 3-5x speedup
  - Router algorithms: 2-4x speedup
  - See Appendix C for full strategy

---

## Part 1: Current State Assessment

### 1.1 Pipeline Components

#### Constraints Layer

| File | Lines | Purpose |
|------|-------|---------|
| `packages/temper-placer/configs/temper_constraints.yaml` | 576 | Main YAML constraint specification |
| `packages/temper-placer/configs/constraints/temper_induction_cooker.yaml` | 273 | Specialized constraints |
| `packages/temper-placer/src/temper_placer/pcl/constraints.py` | 661 | Python constraint objects |
| `packages/temper-drc/src/temper_drc/input/constraints.py` | 269 | DRC constraint loader |
| `packages/temper-placer/src/temper_placer/pcl/loss_bridge.py` | ~200 | Constraint → loss conversion |

**Issues:**
- Dual constraint systems (YAML + PCL) with potential drift
- `loss_bridge.py` implements only 3/7 constraint types:
  - ✅ AdjacentConstraint → ProximityLoss
  - ✅ SeparatedConstraint → SeparationLoss
  - ✅ LoopAreaConstraint → LoopAreaLoss
  - ❌ AlignedConstraint → NOT IMPLEMENTED
  - ❌ OnSideConstraint → NOT IMPLEMENTED
  - ❌ AnchoredConstraint → NOT IMPLEMENTED
  - ❌ EnclosingConstraint → PARTIAL

#### Placement Optimizer

| Component | File | Purpose |
|-----------|------|---------|
| NSGA-II | `optimizer/nsga2.py` | Multi-objective evolutionary algorithm |
| Configuration | `optimizer/config.py` | Temperature/learning rate schedules |
| Checkpoint | `optimizer/checkpoint.py` | State persistence |
| Losses | `losses/` | 12+ loss function modules |
| Core State | `core/state.py:PlacementState` | JAX-compatible state |

#### Routing Architecture

| Router | File | Strategy |
|--------|------|----------|
| UnifiedRouter | `routing/unified_router.py` | Strategy selection facade |
| MazeRouter | `routing/maze_router.py` | Grid-based A* |
| PushShoveRouter | `routing/fast_router.py` | Continuous push-shove |
| C-SpaceRouter | `routing/c_space_pipeline.py` | Configuration space |
| DiffPairRouter | `routing/diff_pair_router.py` | Differential pairs |
| PlaneConnectionRouter | `routing/plane_connection.py` | High-current vias |

**Issues:**
- 9+ independent router classes with inconsistent APIs
- No unified routing context
- Inconsistent result types across routers
- Cannot switch routers mid-pipeline

#### Pipeline Orchestration

| Component | File | Purpose |
|-----------|------|---------|
| Orchestrator | `pipeline/orchestrator.py` | Pipeline state machine |
| CLI | `cli/` | Command-line interface |
| Shell Script | `scripts/run_clean_flow.sh` | Linear bash orchestrator |
| Plane Generator | `add_power_planes_v2.py` | Procedural zone generation |

**Issues:**
- Shell-based orchestration with no state
- No workflow engine
- No rollback mechanism
- No observability

### 1.2 State Classes (11+ Fragmented)

| Class | File | Purpose |
|-------|------|---------|
| `PlacementState` | `core/state.py` | Component positions and rotations |
| `PipelineState` | `pipeline/state.py` | Pipeline phase and iteration |
| `TrainingState` | `optimizer/train.py` | Optimization training state |
| `ConvergenceState` | `pipeline/convergence.py` | Convergence tracking |
| `CurriculumState` | `optimizer/curriculum.py` | Curriculum learning state |
| `ScheduleState` | `optimizer/scheduler.py` | Learning rate schedule |
| `DiffPairState` | `routing/diff_pair_router.py` | Differential pair routing |
| `VisualizationState` | `visualization/model.py` | Visualization data |
| `ServerState` | `visualization/server.py` | Web server state |
| `TrainState` | `ml/train_gnn.py` | GNN training state |

**Issues:**
- No unified state protocol
- No versioning
- No serialization standardization
- 100+ `to_dict()` calls with inconsistent patterns

### 1.3 Exception Handling Analysis

**Bare `except:` blocks found (7 total):**

| File | Line | Context |
|------|------|---------|
| `routing/fast_router.py` | 796 | Warmup try 1 |
| `routing/fast_router.py` | 804 | Warmup try 2 |
| `routing/fast_router.py` | 812 | Warmup try 3 |
| `routing/fast_router.py` | 821 | Warmup try 4 |
| `routing/fast_router.py` | 858 | Warmup try 5 |
| `routing/fast_router.py` | 895 | Warmup try 6 |
| `routing/fast_router.py` | 901 | Warmup try 7 |

**Impact:**
- Silent failures during router warmup
- Impossible to debug routing failures
- No error context or recovery

**Total try/except blocks:** ~100
**With specific exceptions:** ~93
**Bare except blocks:** 7 (7%)

### 1.4 Testing Coverage

| Metric | Value |
|--------|-------|
| Test files in temper-placer | 323 |
| Test functions | 500+ |
| Integration tests | ~5 |
| Property-based tests | 0 |
| Hypothesis in deps | Yes (unused) |

**Issues:**
- No full pipeline integration tests
- No property-based testing (Hypothesis unused)
- No negative testing (impossible constraints)
- No regression baseline

---

## Part 2: Proposed Architecture

### 2.1 Workflow Engine Comparison

| Engine | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **Temporal** | Native Python, durable execution, built-in retries/circuit breakers, lightweight | New dependency | ✅ **RECOMMENDED** |
| Prefect | Pythonic, mature ecosystem | Heavier for EDA workflows | Alternative |
| Airflow | Battle-tested, large community | Batch-oriented, less dynamic | Not recommended |
| Custom | Full control | Rewriting wheel | Avoid |

**Why Temporal:**
1. **Durable execution** - State survives process crashes
2. **Built-in circuit breakers** - Solves P0 timeout issues
3. **Activity-level retries** - Automatic backoff on failures
4. **Lightweight** - Single binary + database
5. **Python-native** - Clean SDK for our use case

### 2.2 SerializableMixin State Model

```
┌─────────────────────────────────────────────────────────────┐
│                 SerializableMixin (Base Class)              │
│  + version: str                                             │
│  + to_dict() -> dict                                        │
│  + from_dict(dict) -> instance                              │
│  + migrate(dict, from_version) -> instance                  │
│  + _jax_to_dict(value) -> JSON-serializable                 │
│  + _jax_from_dict(value) -> DeviceArray                     │
└─────────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼─────────────────┐
         │                │                 │
         ▼                ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│PlacementState │ │RoutingState   │ │ValidationState│
│ - positions   │ │ - traces      │ │ - violations  │
│ - rotations   │ │ - vias        │ │ - metrics     │
│ - nets        │ │ - wirelength  │ │ - pass/fail   │
└───────────────┘ └───────────────┘ └───────────────┘
```

**Key features:**
- Mixin provides `to_dict()`/`from_dict()` for all state classes
- Version field enables migration
- `_jax_to_dict()`/`_jax_from_dict()` handle DeviceArray conversion
- Composable (each module owns its state)
- Works with dataclasses automatically

**JAX DeviceArray handling:**
```python
def _jax_to_dict(self, value):
    """Convert JAX arrays to numpy for JSON serialization."""
    if hasattr(value, 'device_buffer'):  # DeviceArray
        return jax.device_get(value).tolist()
    return value

def _jax_from_dict(self, value):
    """Convert back to DeviceArray after deserialization."""
    if isinstance(value, list):
        return jnp.array(value)
    return value
```

### 2.3 Router Protocol

```python
@runtime_checkable
class Router(Protocol):
    """Protocol for all router implementations."""

    @property
    def strategy(self) -> RoutingStrategy:
        """Routing algorithm used."""

    def route_net(self, net_name: str, pins: list[Point], board: Board) -> RoutingResult:
        """Route single net."""

    def route_all_nets(self, netlist: Netlist, positions: Array, board: Board) -> RoutingResult:
        """Route all nets."""
```

**Router implementations:**
- `MazeRouter` → `RoutingStrategy.MAZE`
- `PushShoveRouter` → `RoutingStrategy.PUSH_SHOVE`
- `DiffPairRouter` → `RoutingStrategy.DIFF_PAIR`
- `AutoRouter` → `RoutingStrategy.AUTO` (tries maze, fallback to push-shove)

### 2.4 Exception Hierarchy

```
TemperError (base)
├── PlacementError
│   ├── OptimizationFailed
│   ├── ConvergenceError
│   └── IllegalPlacementError
├── RoutingError
│   ├── UnroutableError
│   ├── RoutingTimeoutError
│   └── DRCError
├── ValidationError
│   ├── SchemaValidationError
│   └── ConstraintConflictError
└── ConfigError
    ├── ConstraintError
    └── NetlistError
```

### 2.5 Rust/Numba Acceleration Boundaries

The refactoring creates safe boundaries for future Rust/Numba acceleration:

#### Serialization Boundary
```python
# Python interface (frozen after Task 1.1)
class SerializableMixin:
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "SerializableMixin": ...
```
**Rust target:** `temper-serialization` crate with PyO3 bindings.

#### Loss Function Boundary
```python
# Python interface (frozen after Task 2.1)
LossFunction = Callable[[jnp.ndarray, SerializableMixin], float]
```
**Numba target:** `@njit(cache=True, parallel=True)` decorated functions.

#### Router Boundary
```python
# Python interface (frozen after Task 2.2)
class Router(Protocol):
    def route_net(self, net_name: str, pins: list[Point], board: Board) -> RoutingResult: ...
```
**Rust target:** `temper-router` crate with strategy pattern.

#### Component Lookup Boundary
```python
# Python interface (frozen after Task 2.3)
class ComponentID:
    @classmethod
    def from_ref(cls, ref: str) -> "ComponentID": ...
    @property
    def index(self) -> int: ...
```
**Rust target:** `temper-lookup` crate with FNV hash map.

**Key principle:** Implement in Python first, swap in Rust later. The interface stays the same.

---

## Part 3: Implementation Plan

### Phase 1: Critical Durability (P0)

#### Task 1.1: SerializableMixin Base Class

**Decision Gate:** If adoption requires >3 files to change per state class, abort and use simpler approach.

**Note:** This interface is designed to be Rust-compatible (PyO3). After Phase 4, `to_dict()` can delegate to a `temper-serialization` Rust crate without changing callers.

**Deliverable:** `packages/temper-placer/src/temper_placer/core/mixins.py`

```python
from dataclasses import dataclass, fields, is_dataclass
from typing import Any
import jax.numpy as jnp
import json

VERSION = "1.0"

class SerializableMixin:
    """Base mixin for serializable state classes."""

    version: str = VERSION

    def to_dict(self) -> dict:
        """Convert state to JSON-serializable dict."""
        result = {"version": self.version}
        for field in fields(self):
            value = getattr(self, field.name)
            result[field.name] = self._jax_to_dict(value)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "SerializableMixin":
        """Create state from dict with validation."""
        if data.get("version") != VERSION:
            data = cls.migrate(data, data.get("version", "unknown"))
        return cls(**{
            f.name: cls._jax_from_dict(data[f.name])
            for f in fields(cls) if f.name in data
        })

    @classmethod
    def migrate(cls, data: dict, from_version: str) -> dict:
        """Migrate state from older version."""
        if from_version == "unknown":
            raise ValueError(f"Cannot migrate from unknown version")
        return data

    @staticmethod
    def _jax_to_dict(value: Any) -> Any:
        """Convert JAX arrays to JSON-serializable format."""
        if hasattr(value, 'device_buffer'):
            return jax.device_get(value).tolist()
        return value

    @staticmethod
    def _jax_from_dict(value: Any) -> Any:
        """Convert JSON data back to appropriate type."""
        if isinstance(value, list):
            return jnp.array(value)
        return value

# Usage:
@dataclass
class PlacementState(SerializableMixin):
    positions: jnp.ndarray
    rotations: jnp.ndarray
    iteration: int = 0
```

**Files to modify:**
- `core/state.py` - Inherit SerializableMixin
- `pipeline/state.py` - Inherit SerializableMixin
- `optimizer/train.py` - Inherit SerializableMixin
- `optimizer/curriculum.py` - Inherit SerializableMixin
- `optimizer/scheduler.py` - Inherit SerializableMixin
- `pipeline/convergence.py` - Inherit SerializableMixin
- `routing/diff_pair_router.py` - Inherit SerializableMixin
- `visualization/model.py` - Inherit SerializableMixin
- `visualization/server.py` - Inherit SerializableMixin

**Testing:**
```python
# tests/core/test_mixins.py
def test_state_serialization_roundtrip(tmp_path):
    """State must serialize and deserialize identically."""
    state = PlacementState(
        positions=jnp.array([[1.0, 2.0], [3.0, 4.0]]),
        rotations=jnp.array([0.0, 90.0]),
        iteration=100,
    )
    data = state.to_dict()
    restored = PlacementState.from_dict(data)
    assert jnp.allclose(state.positions, restored.positions)
    assert jnp.allclose(state.rotations, restored.rotations)
    assert state.iteration == restored.iteration
```

**Existing checkpoint migration:**
```python
# scripts/migrate_checkpoints.py
def migrate_legacy_checkpoint(data: dict) -> dict:
    """Migrate legacy PlacementState checkpoints."""
    if "positions" in data and "rotation" in data:
        data["rotations"] = data.pop("rotation")
    if "version" not in data:
        data["version"] = "0.9"
    return data
```

---

#### Task 1.2: Replace Shell Scripts with Temporal

**Deliverable:** Replace `scripts/run_clean_flow.sh` with Temporal workflows

**Files to create:**
- `packages/temper-placer/src/temper_placer/workflows/__init__.py`
- `packages/temper-placer/src/temper_placer/workflows/placement_workflow.py`
- `packages/temper-placer/src/temper_placer/workflows/activities.py`
- `packages/temper-placer/src/temper_placer/workflows/worker.py`
- `docker-compose.yml` (Temporal server)

**Example workflow:**
```python
@workflow.defn
class PlacementWorkflow:
    @workflow.run
    async def run(self, input_pcb: str, constraints_path: str) -> dict:
        # Step 1: Load PCB (with retry)
        pcb = await workflow.execute_activity(
            load_pcb_activity,
            args=[input_pcb],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Step 2: Preflight validation
        await workflow.execute_activity(
            preflight_check_activity,
            args=[pcb, constraints_path],
            start_to_close_timeout=timedelta(minutes=5),
        )

        # Step 3: Optimization (checkpointable)
        placement = await workflow.execute_activity(
            optimize_placement_activity,
            args=[pcb, constraints_path],
            start_to_close_timeout=timedelta(hours=4),
            heartbeat_timeout=timedelta(minutes=1),
        )

        # Step 4: Routing with fallback
        routing = await workflow.execute_activity(
            route_nets_activity,
            args=[placement],
            start_to_close_timeout=timedelta(hours=2),
        )

        return routing.to_dict()
```

**Circuit breaker:**
```python
worker = Worker(
    client,
    task_queue="temper-placer",
    workflows=[PlacementWorkflow],
    activities=[load_pcb_activity, optimize_activity, route_activity],
    workflow_failure_exception_types=[PlacementError, RoutingError],
)
```

---

#### Task 1.3: Fix Bare Exception Handling

**Decision Gate:** If hidden exception patterns > 15, create follow-up issue instead of expanding scope.

**Deliverable:** Zero bare `except:` blocks in codebase

**Pattern change:**

```python
# BEFORE (fast_router.py:796)
try:
    find_path_astar_numba(...)
except:
    pass  # Silent failure!

# AFTER
try:
    find_path_astar_numba(...)
except MemoryError:
    logger.warning("OOM, reducing grid size")
    reduce_grid_and_retry()
except (ValueError, IndexError) as e:
    logger.error(f"Path finding failed: {e}", exc_info=True)
    raise RoutingError(f"Path search failed: {e}") from e
except Exception as e:
    logger.critical(f"Unexpected error: {e}", exc_info=True)
    raise
```

**Files to modify:**
- `routing/fast_router.py` - Lines 796, 804, 812, 821, 858, 895, 901

**Create exception hierarchy:**
- `packages/temper-placer/src/temper_placer/errors.py`

---

#### Task 1.4: Implement Rollback Mechanism

**Deliverable:** `packages/temper-placer/src/temper_placer/workflows/rollback.py`

```python
@dataclass
class Transaction:
    """Atomic transaction with rollback support."""
    state_before: SerializableMixin
    operations: list[Callable]

    async def commit(self) -> None:
        try:
            for op in self.operations:
                op()
        except Exception as e:
            await self.rollback()
            raise WorkflowRollbackError(f"Commit failed: {e}") from e

    async def rollback(self) -> None:
        logger.info(f"Rolling back to version {self.state_before.version}")
        restore_state(self.state_before)
```

---

### Phase 2: Architectural Debt (P1)

#### Task 2.1: Consolidate Constraint Systems

**Decision Gate:** If YAML constraint migration requires manual intervention > 10% of files, maintain dual system indefinitely.

**Note:** Loss functions are designed for Numba JIT compilation. Use `@njit(cache=True, parallel=True)` decorator when implementing. Hot loops must avoid Python objects.

**Deliverable:** PCL-only constraint system with migration path

**Implement missing constraints in `loss_bridge.py`:**

| Constraint | Loss Function |
|------------|---------------|
| AlignedConstraint | `aligned_to_placement_loss()` |
| OnSideConstraint | `on_side_to_placement_loss()` |
| AnchoredConstraint | `anchored_to_placement_loss()` |
| EnclosingConstraint | `enclosing_to_placement_loss()` |

**Deprecation workflow:**
1. Add deprecation warning to `temper_constraints.yaml`
2. Create migration script: `scripts/migrate_constraints.py`
3. Update `AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md`

---

#### Task 2.2: Unify Router APIs

**Decision Gate:** If adapter overhead > 20% per router, use call-site adapters only.

**Note:** This task consolidates router selection, not internal algorithms. The Router protocol is designed for Rust implementation via PyO3. Internal algorithms (A*, push-shove) can be rewritten in Rust later while preserving this interface.

**Deliverable:** Router factory for consistent instantiation

**Files to create:**
- `packages/temper-placer/src/temper_placer/routing/router_protocol.py`
- `packages/temper-placer/src/temper_placer/routing/factory.py`

**Router factory:**
```python
def create_router(
    strategy: RoutingStrategy = RoutingStrategy.AUTO,
    config: RouterConfig | None = None,
) -> Router:
    if strategy == RoutingStrategy.MAZE:
        return MazeRouter(config=config)
    elif strategy == RoutingStrategy.PUSH_SHOVE:
        return PushShoveRouter(config=config)
    elif strategy == RoutingStrategy.AUTO:
        return AutoRouter(config=config)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
```

**Files to modify:**
- `routing/maze_router.py` - Add router_type attribute
- `routing/fast_router.py` - Add router_type attribute
- `routing/unified_router.py` - Use factory pattern

---

#### Task 2.3: Type-Safe Component References

**Deliverable:** `ComponentID` class replacing string refs

```python
@dataclass(frozen=True, eq=True)
class ComponentID:
    """Type-safe component reference."""
    ref: str

    _REGISTRY: ClassVar[dict[str, int]] = {}

    @classmethod
    def from_ref(cls, ref: str) -> "ComponentID":
        if ref not in cls._REGISTRY:
            raise ValueError(f"Unknown component: {ref}")
        return cls(ref)

    @classmethod
    def register_netlist(cls, netlist: Netlist) -> None:
        cls._REGISTRY = {comp.ref: idx for idx, comp in enumerate(netlist.components)}

    @property
    def index(self) -> int:
        return self._REGISTRY[self.ref]
```

**Mypy configuration (update `pyproject.toml`):**
```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
```

---

### Phase 3: Rigor Improvements (P2)

#### Task 3.1: Schema Validation

**Deliverable:** JSON schema for constraint YAML

**Files to create:**
- `packages/temper-placer/configs/schemas/temper_constraints.schema.json`
- `packages/temper-placer/src/temper_placer/validation/schema_validator.py`

```python
def validate_constraints(yaml_path: Path) -> ValidationResult:
    """Validate constraint YAML against JSON schema."""
    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    with open("configs/schemas/temper_constraints.schema.json") as f:
        schema = json.load(f)

    try:
        validate(instance=config, schema=schema)
        return ValidationResult(valid=True, errors=[])
    except ValidationError as e:
        return ValidationResult(valid=False, errors=[...])
```

---

#### Task 3.2: Property-Based Testing

**Note:** Defer until Phase 1-2 are complete. This task depends on stable state classes.

**Deliverable:** Hypothesis tests for invariants

**Files to create:**
- `packages/temper-placer/tests/properties/test_placement_invariants.py`
- `packages/temper-placer/tests/properties/test_routing_invariants.py`
- `packages/temper-placer/tests/properties/test_constraint_invariants.py`

**Example tests:**
```python
@given(st.builds(PlacementState))
def test_placement_within_bounds(state):
    """All components must stay within board bounds."""
    positions = state.positions
    assert jnp.all(positions[:, 0] >= MARGIN)
    assert jnp.all(positions[:, 0] <= BOARD_WIDTH - MARGIN)
    assert jnp.all(positions[:, 1] >= MARGIN)
    assert jnp.all(positions[:, 1] <= BOARD_HEIGHT - MARGIN)

@given(st.builds(RoutingResult))
def test_traces_connected(result):
    """All traces must connect from source to destination."""
    for trace in result.traces:
        assert trace.segments[0].start == trace.source_pin
        assert trace.segments[-1].end == trace.target_pin
```

---

#### Task 3.3: Pipeline Integration Tests

**Deliverable:** Full pipeline tests without mocks

**Files to create:**
- `packages/temper-placer/tests/integration/test_full_pipeline.py`
- `packages/temper-placer/tests/integration/test_recovery.py`
- `packages/temper-placer/tests/integration/test_checkpoint_resume.py`

```python
@pytest.mark.integration
async def test_full_pipeline_flow(sample_pcb, sample_constraints):
    """End-to-end test: placement → routing → validation → export."""
    workflow = PlacementWorkflow()
    result = await workflow.run(
        input_pcb=str(sample_pcb),
        constraints_path=str(sample_constraints),
    )

    assert result["success"]
    assert result["placements_routed"] > 0
    assert result["drc_violations"] == 0
```

---

### Phase 4: Observability (P2)

#### Task 4.1: Structured Logging & Tracing

**Deliverable:** OpenTelemetry integration

```python
# observability/tracing.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@workflow.defn
class PlacementWorkflow:
    @workflow.run
    async def run(self, input_pcb: str):
        with tracer.start_as_current_span("placement_workflow"):
            with tracer.start_as_current_span("load_pcb"):
                pcb = await load_pcb_activity(input_pcb)
            with tracer.start_as_current_span("optimize"):
                placement = await optimize_activity(pcb)
```

---

#### Task 4.2: Metrics Dashboard

**Deliverable:** Prometheus + Grafana dashboards

```python
# observability/metrics.py
from prometheus_client import Histogram, Counter

placement_duration = Histogram(
    "placement_duration_seconds",
    "Time spent in placement optimization",
    ["board_size", "num_components"],
)

routing_success_rate = Counter(
    "routing_success_total",
    "Number of successful routing attempts",
    ["router_type"],
)
```

---

## Part 4: Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| State corruption during migration | HIGH | MEDIUM | Versioning + migration tests + legacy checkpoint script |
| Temporal dependency overhead | MEDIUM | MEDIUM | Evaluate after Task 1.2, revert if overhead > 10% |
| Hidden exception patterns | HIGH | MEDIUM | Decision gate in Task 1.3 to scope limit |
| Constraint migration failure | HIGH | MEDIUM | Decision gate to maintain dual system if needed |
| Router API fragmentation persists | MEDIUM | LOW | Call-site adapters acceptable alternative |
| JAX DeviceArray serialization bugs | HIGH | LOW | Unit tests for serialization roundtrip |
| Rust/Numba build complexity | MEDIUM | MEDIUM | Maturin + PyO3, keep Python fallback |
| Benchmark regression (acceleration) | HIGH | LOW | Automated benchmarks in CI |

---

## Part 5: Success Criteria

### Phase 1 (Durability)
- [ ] All 11+ state classes inherit SerializableMixin
- [ ] Shell scripts replaced with Temporal workflows
- [ ] 0 bare exception handlers
- [ ] Rollback mechanism working
- [ ] Existing checkpoints can be migrated

### Phase 2 (Architecture)
- [ ] PCL-only constraint system (or decision to keep dual system)
- [ ] Router factory for consistent instantiation
- [ ] ComponentID replaces string refs in hot paths
- [ ] Mypy strict mode passing

### Phase 3 (Rigor)
- [ ] JSON schema validation active
- [ ] Property-based tests (deferred from Phase 3)
- [ ] Integration test suite passing
- [ ] Regression tests in CI

### Phase 4 (Observability)
- [ ] Traces visible in Jaeger UI
- [ ] Metrics in Prometheus
- [ ] Grafana dashboard shows pipeline health

### Phase 5 (Rust/Numba Acceleration) - Post-Refactoring
- [ ] `temper-serialization` crate implemented
- [ ] Serialization benchmark: <1ms for 1000 components (5-10x speedup)
- [ ] `temper-router` crate implemented
- [ ] Router benchmark: <50ms for 100 nets (2-4x speedup)
- [ ] Numba loss functions implemented
- [ ] Loss function benchmark: <0.5ms for 1000 components (3-5x speedup)
- [ ] Python fallback works if Rust binary unavailable
- [ ] Total pipeline speedup: 2-3x

---

## Appendix C: Rust/Numba Acceleration Strategy

> **Note:** This is a post-refactoring optimization path. Execute after Phase 2 complete.

### Why Now?

The refactoring plan establishes clear module boundaries:
- `SerializableMixin` → `to_dict()`/`from_dict()`
- `LossFunction` → `__call__(positions) -> float`
- `Router` → `route_net(pins) -> RoutingResult`
- `ComponentID` → `from_ref() -> index`

These boundaries make it safe to swap implementations without affecting the rest of the pipeline.

### Candidate Components

#### 1. State Serialization (`to_dict`/`from_dict`)

**Current Python:**
```python
def _jax_to_dict(self, value):
    if hasattr(value, 'device_buffer'):
        return jax.device_get(value).tolist()  # CPU copy + Python list
    return value
```

**Rust Alternative (serde + numpy):**
```rust
// temper-core/src/serialization.rs
pub fn serialize_jax_array(arr: &PyArray<f32>) -> Vec<f32> {
    // Direct memory copy from GPU buffer
    arr.to_vec().unwrap()
}
```

**Expected Speedup:** 5-10x
- Eliminates Python loop overhead
- Direct memory access to JAX buffers
- SIMD-optimized serialization

**Interface to preserve:**
```python
# After refactoring, this signature is frozen
def to_dict(self) -> dict:
    ...
```

---

#### 2. Loss Bridge Functions

**Current Python:**
```python
def proximity_loss(positions, constraints):
    for constraint in constraints:
        dist = jnp.linalg.norm(positions[i] - positions[j])
        loss += jnp.maximum(0, dist - min_spacing)
    return loss
```

**Numba JIT Alternative:**
```python
@njit(cache=True, parallel=True)
def proximity_loss(positions, min_spacing, n_components):
    loss = 0.0
    for i in prange(n_components):
        for j in range(i + 1, n_components):
            dist = norm(positions[i] - positions[j])
            if dist < min_spacing:
                loss += (min_spacing - dist) ** 2
    return loss
```

**Expected Speedup:** 3-5x
- Parallel execution (`prange`)
- No Python interpreter overhead
- SIMD in tight loops

**Benchmark baseline (add to CI):**
```python
# benchmarks/loss_functions.py
def benchmark_proximity_loss():
    """Loss function must complete in <1ms for 1000 components."""
    positions = jnp.random.random((1000, 2))
    start = time.perf_counter()
    for _ in range(1000):
        result = proximity_loss(positions, min_spacing=0.5)
    elapsed = time.perf_counter() - start
    assert elapsed / 1000 < 0.001, f"Loss took {elapsed/1000*1000:.2f}ms"
```

---

#### 3. Router Algorithms (A*, Push-Shove)

**Current Python:**
```python
# routing/maze_router.py
def find_path_astar(self, start, goal, obstacles):
    # Pure Python A* implementation
    open_set = [start]
    came_from = {}
    g_score = {start: 0}
    while open_set:
        current = min(open_set, key=lambda x: g_score[x])
        # ... Python loop
```

**Rust Alternative:**
```rust
// temper-router/src/astar.rs
pub fn find_path_astar(
    start: (f32, f32),
    goal: (f32, f32),
    obstacles: &ObstacleGrid,
) -> Option<Vec<Point>> {
    // Priority queue with binary heap
    // Inline distance calculations
    // Bit-level obstacle checking
}
```

**Expected Speedup:** 2-4x
- Binary heap priority queue (Python's heapq is slower)
- Inline function calls
- Bit-level operations for obstacle checking

**Interface to preserve:**
```python
class Router(Protocol):
    def route_net(self, net_name: str, pins: list[Point], board: Board) -> RoutingResult:
        ...
```

---

#### 4. Component Lookup (`ComponentID`)

**Current Python:**
```python
@dataclass(frozen=True, eq=True)
class ComponentID:
    ref: str
    _REGISTRY: ClassVar[dict[str, int]] = {}
```

**Rust Alternative (FNV hash + perfect hashing):**
```rust
// temper-core/src/lookup.rs
pub struct ComponentLookup {
    // FNV-1a hash map (faster for short keys)
    map: FnvHashMap<String, usize>,
    // Or: perfect hashing for O(1) with no collision overhead
}

impl ComponentLookup {
    pub fn from_netlist(netlist: &Netlist) -> Self {
        // Pre-compute perfect hash function
    }
    
    pub fn get_index(&self, ref_str: &str) -> Option<usize> {
        self.map.get(ref_str).copied()
    }
}
```

**Expected Speedup:** 2-3x on cold lookups
- FNV-1a hash is faster than Python's default hash for short strings
- No Python object overhead
- Zero-allocation lookups

---

#### 5. YAML Parsing

**Current Python:**
```python
config = yaml.safe_load(f)  # PyYAML, Python-based
```

**Rust Alternative:**
```rust
// temper-config/src/yaml.rs
pub fn load_constraints(path: &Path) -> Result<Constraints, Error> {
    // yaml-rs with serde
    // Direct mapping to PCL structs
}
```

**Expected Speedup:** 2-3x
- yaml-rs is faster than PyYAML
- Direct deserialization to Rust structs
- No intermediate Python objects

---

### Implementation Roadmap

```
Phase 5: Rust/Numba Acceleration (Post-Phase 4)

Week 27-28: PyO3 setup
- Create `packages/temper-rust/` subdirectory
- Set up maturin build system
- Define Rust interfaces matching Python protocols

Week 29-31: Serialization + Config
- Implement `temper-serialization` crate
- Implement `temper-config` crate
- Benchmark against Python baseline

Week 32-34: Loss Functions
- JIT-compile loss bridge with Numba
- Add parallel execution
- Validate against existing tests

Week 35-37: Router Algorithms
- Implement A* in Rust
- Implement push-shove in Rust
- Preserve Python fallback

Week 38-40: Integration
- Replace hot-path calls with Rust implementations
- Add runtime feature flags
- Full benchmark suite
```

### Performance Targets

| Component | Current (Python) | Target (Rust/Numba) | Speedup |
|-----------|-----------------|---------------------|---------|
| State serialization (1000 components) | 5-10ms | 0.5-1ms | 5-10x |
| Loss function (1000 components) | 1-2ms | 0.2-0.5ms | 3-5x |
| Router A* (100 nets) | 100-200ms | 30-50ms | 2-4x |
| Component lookup (1000 lookups) | 50μs | 15-20μs | 2-3x |
| YAML parsing (576 lines) | 50-100ms | 20-30ms | 2-3x |

### Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rust build complexity | MEDIUM | Use maturin, keep Python fallback |
| PyO3 compatibility | MEDIUM | Test on all platforms in CI |
| Benchmark regression | HIGH | Automated benchmarks in CI |
| Debugging difficulty | HIGH | Maintain Python implementations for debugging |

### Success Criteria (Post-Refactoring)

- [ ] Serialization benchmark: <1ms for 1000 components
- [ ] Loss function benchmark: <0.5ms for 1000 components
- [ ] Router benchmark: <50ms for 100 nets
- [ ] Total pipeline speedup: 2-3x
- [ ] Python fallback works if Rust binary unavailable

| File | Lines | Issue |
|------|-------|-------|
| `packages/temper-placer/configs/temper_constraints.yaml` | 576 | Dual constraint system |
| `packages/temper-placer/src/temper_placer/pcl/constraints.py` | 661 | Incomplete loss bridge |
| `packages/temper-placer/src/temper_placer/core/state.py` | 305 | Needs SerializableMixin |
| `packages/temper-placer/src/temper_placer/pipeline/state.py` | 80+ | Needs SerializableMixin |
| `packages/temper-placer/src/temper_placer/routing/fast_router.py` | 950+ | 7 bare except blocks |
| `packages/temper-placer/src/temper_placer/routing/unified_router.py` | 500+ | Needs refactor |
| `scripts/run_clean_flow.sh` | 68 | Replace with Temporal |

---

*End of Plan*
