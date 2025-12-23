# temper-testing

Testing toolkit for verification of numerical optimization, constraint satisfaction, and placement algorithms.

## Installation

```bash
pip install -e packages/temper-testing
```

## Features

### 1. Oracle Testing Framework
Test against known-correct answers, not just properties.

```python
from temper_testing import oracle

# Define oracle with exact expected result
@oracle.exact(expected=12.0, tolerance=1e-10)
def test_rectangle_area():
    return shoelace_area([(0,0), (4,0), (4,3), (0,3)])

# Define oracle with bounds
@oracle.bounded(min_val=0.0, max_val=100.0)
def test_loss_value():
    return compute_loss(positions)
```

### 2. Gradient Verification
Compare autodiff gradients against numerical approximation.

```python
from temper_testing import gradients

# Verify gradient correctness
gradients.check_gradient(
    fn=loss_function,
    params=positions,
    epsilon=1e-5,
    rtol=1e-3,
    atol=1e-6
)

# Find gradient discontinuities
discontinuities = gradients.find_discontinuities(
    fn=loss_function,
    params=positions,
    num_samples=1000
)
```

### 3. Visual Grid Debugging
ASCII visualization for failed tests.

```python
from temper_testing import viz

# Render grid state on failure
viz.render_grid(
    occupancy=router.occupancy,
    components=components,
    path=failed_path,
    pins=pins
)
# Output:
# . . . . . . . .
# . # # # . . . .
# . # C C P→→→. .
# . # # # . . ↓ .
# . . . . . . G .
```

### 4. Determinism Verification
Ensure same input → same output.

```python
from temper_testing import determinism

# Run N times, verify identical
determinism.verify(
    fn=spectral_init,
    args=(netlist,),
    runs=10,
    compare=np.allclose
)

# With JAX PRNG
determinism.verify_with_seed(
    fn=optimize,
    seed=42,
    runs=5
)
```

### 5. Metamorphic Testing
Test relationships between inputs/outputs.

```python
from temper_testing import metamorphic

class LargerMarginBlocksMore(metamorphic.Property):
    """margin1 < margin2 → blocked1 ⊆ blocked2"""

    def transform(self, margin1):
        return margin1 + 0.5  # margin2

    def relation(self, blocked1, blocked2):
        return blocked1.issubset(blocked2)

# Auto-generates test cases
metamorphic.verify(LargerMarginBlocksMore(), num_cases=100)
```

### 6. Hypothesis Strategies (Domain-Specific)
Reusable strategies for PCB placement domain.

```python
from temper_testing.strategies import (
    realistic_component,
    valid_board_position,
    connected_netlist,
    non_overlapping_placement,
)

@given(comp=realistic_component(pins=(2, 8)))
def test_component(comp):
    assert len(comp.pins) >= 2
```

### 7. Invariant Checking (Runtime)
Enable/disable runtime invariant checks.

```python
from temper_testing import invariants

@invariants.check
class MazeRouter:
    def route(self, net):
        result = self._route_impl(net)

        # These run only when TEMPER_CHECK_INVARIANTS=1
        invariants.assert_path_connected(result.path)
        invariants.assert_within_bounds(result.path, self.grid)
        invariants.assert_no_blocked_cells(result.path, self.occupancy)

        return result
```

### 8. Snapshot/Golden Testing
Compare against known-good outputs.

```python
from temper_testing import golden

# First run: saves to .golden/test_optimize.json
# Later runs: compares against saved
@golden.test
def test_optimize():
    return optimizer.run(netlist)

# Update golden files
# TEMPER_UPDATE_GOLDEN=1 pytest tests/
```

### 9. Coverage Analysis
Track which code paths are tested.

```python
from temper_testing import coverage

# Track edge case coverage
coverage.register_edge_cases([
    "empty_netlist",
    "single_component",
    "all_components_fixed",
    "overlapping_initial",
    "outside_board_initial",
])

@coverage.covers("empty_netlist")
def test_empty():
    pass
```

## Recommended External Libraries

| Library | Purpose | Install |
|---------|---------|---------|
| `hypothesis[numpy]` | Property-based testing with NumPy/JAX | `pip install hypothesis[numpy]` |
| `pytest-benchmark` | Performance regression testing | `pip install pytest-benchmark` |
| `pytest-timeout` | Prevent hanging tests | `pip install pytest-timeout` |
| `pytest-randomly` | Randomize test order (find dependencies) | `pip install pytest-randomly` |
| `mutmut` | Mutation testing | `pip install mutmut` |
| `hypothesis-jsonschema` | Generate test data from schemas | `pip install hypothesis-jsonschema` |
| `icontract` | Design-by-contract with runtime checks | `pip install icontract` |
| `deal` | Another DbC library with Hypothesis integration | `pip install deal` |
| `crosshair-tool` | Symbolic execution for Python | `pip install crosshair-tool` |

## Configuration

```toml
# pyproject.toml
[tool.temper-testing]
check_invariants = true  # Enable runtime invariants
golden_dir = ".golden"   # Golden file location
gradient_epsilon = 1e-5  # Numerical gradient step
determinism_runs = 10    # Default verification runs

[tool.temper-testing.hypothesis]
max_examples = 500
deadline = 5000  # ms
database = ".hypothesis"
```
