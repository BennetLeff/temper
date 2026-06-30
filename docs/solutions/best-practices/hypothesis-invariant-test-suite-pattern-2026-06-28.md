---
title: "Hypothesis invariant test suite pattern for algorithmic pipelines"
date: "2026-06-28"
category: "best-practices"
module: "temper-placer"
problem_type: "best_practice"
component: "testing_framework"
severity: "medium"
applies_when:
  - "Building invariant-based test suites for algorithmic pipelines with large combinatorial input spaces"
  - "Verifying mathematical properties hold across arbitrary valid inputs using Hypothesis property-based testing"
  - "Testing computational geometry, EDA/PCB routing, or DRC-heavy code where manual fixtures are insufficient"
tags:
  - "hypothesis"
  - "property-based-testing"
  - "invariant-testing"
  - "temper-placer"
  - "router-v6"
  - "computational-geometry"
  - "drc"
  - "pytest"
---

# Hypothesis invariant test suite pattern for algorithmic pipelines

## Context

Router V6 takes deeply structured inputs — `ParsedPCB`, `Netlist`, `Component` lists, layer stacks — and produces `RoutingResults` with `RoutePath`s, `Via`s, and geometry. The existing test suite relied on hand-picked fixtures: a few known boards, a few crafted netlists, each exercising one expected behavior. These caught regressions in the code paths that were explicitly modeled, but bugs kept surfacing in production that no fixture thought to cover — via stacks placed on component courtyards, missing `@dataclass` decorators producing silent wrong output, route segments drifting outside board bounds. Every new bug asked the same question: "Why didn't a test catch this?" The answer was always the same: no test expressed the *invariant* that was violated.

## Guidance

Build the suite in four layers: shared strategies, theorem classes, per-class test files, and CI integration.

### 1. Shared strategy file

Create one module containing `@st.composite` strategies for every domain type the system consumes and produces. Compose them bottom-up: a `Via` strategy builds from coordinate and layer strategies; a `RoutePath` strategy composes `Via` lists with path geometry; a `ParsedPCB` strategy composes layers, components, and nets. The key rule: each composite strategy calls the strategies for its sub-parts — never duplicate generation logic.

```python
@st.composite
def board(draw: st.DrawFn) -> Board:
    """Generate a Board with random dimensions within anchored ranges."""
    w = draw(st.floats(min_value=50.0, max_value=300.0))
    h = draw(st.floats(min_value=50.0, max_value=300.0))
    return Board(width=w, height=h, origin=(0.0, 0.0))

@st.composite
def design_rules(draw: st.DrawFn) -> DesignRules:
    """Generate Router V6 DesignRules with random net classes and defaults."""
    n_classes = draw(st.integers(min_value=1, max_value=4))
    ...

@st.composite
def parsed_pcb(draw: st.DrawFn) -> ParsedPCB:
    """Generate a complete ParsedPCB from its constituent strategies."""
    b = draw(board())
    comps = draw(component_list(board_width=b.width, board_height=b.height))
    nl = draw(netlist_from_components(components=comps))
    dr = draw(design_rules())
    return ParsedPCB(components=comps, nets=nl.nets, board=b, design_rules=dr, ...)
```

### 2. Categorize invariants into theorem classes

Group tests by what property of the system they verify, not by what file they test:

| Theorem class | What it proves |
|---|---|
| Output validity | Every return value is structurally well-formed (non-None fields, correct types, array dimensions match input count) |
| Geometric consistency | Spatial invariants: traces within board bounds, via diameters positive, path lengths match coordinate distances |
| Topological correctness | Net assignments complete, SAT solution consistency, channel capacities respected, escape vias generated |
| DRC conformance | Clearance/annular ring/creepage minimums met, empty-is-zero, no-crash, consistency (total >= critical) |

### 3. Per-class test files, single convention

Each theorem class gets its own file (e.g., `test_router_v6_geometric_invariants_pbt.py`). Every test follows the same convention:

```python
import pytest
from hypothesis import given, settings

@pytest.mark.property
@given(pcb=parsed_pcb())
@settings(max_examples=100, deadline=30000)
def test_all_path_coordinates_within_board_bounds(pcb):
    result = route(pcb)
    for route in result.compiled_routes.values():
        for x, y in route.path.coordinates:
            assert 0 <= x <= pcb.board.width, f"x={x} outside board"
            assert 0 <= y <= pcb.board.height, f"y={y} outside board"
```

`max_examples=100` balances confidence against runtime. `deadline=30000` catches strategies that accidentally generate pathologically slow cases. `@pytest.mark.property` enables selective CI execution.

### 4. Extend, don't duplicate

If an existing fuzzing file exists (e.g., `test_dfm_hypothesis_fuzzing.py` that tests no-crash, non-negativity, and consistency), layer the new domain-correctness invariants on top rather than creating a parallel file. The original fuzzing suite continues to test "does it run without crashing?" while the new tests prove "does it flag the *right* violations?"

## Why This Matters

Conventional fixture-based tests prove the system works for *the inputs we thought to test*. Invariant tests prove it works for *any input that fits the schema*.

- **Example-based tests** catch regressions in specific code paths. They verify: "This exact board still routes correctly."
- **Invariant tests** catch structural violations, interaction bugs, and edge-case combinatorics. They verify: "No matter what valid board you throw at the router, paths will never be outside bounds, vias will have physically meaningful dimensions, and clearance violations will be correctly flagged."

A single invariant test exercising 100 randomly-generated inputs per CI run explores more of the input space than a year of hand-written fixtures. When the system has 12+ configurable features, each with 3-5 valid states, the combinatorial space is enormous — invariant tests sample it systematically.

The placement invariants suite (`test_placement_invariants.py`, 29 tests across 9 theorems) proved this diagnostic power: it was the tool that isolated the 250M boundary loss bug to a single line in `corpus_runner.py` — a bug that conventional tests had missed for weeks because they never exercised the rotation logits-to-softmax transformation path.

## When to Apply

This pattern fits when:

- Inputs are complex structured types (not just scalars). If you can write a `@st.composite` strategy, Hypothesis can generate it.
- You can articulate universal truths about outputs independently of the input. "Every via has a non-negative drill size" is a good invariant; "the route matches this golden file" is not.
- The input space is too large to enumerate with fixtures. If you'd need more than ~20 fixtures to feel confident, you're in invariant-test territory.
- Bugs tend to be **interaction bugs** — things that only fail when two or more features combine.

Do NOT apply when:
- The subsystem is I/O-bound (well-specified edge cases benefit more from parameterized fixtures).
- Invariants are too weak to justify the test runtime (e.g., "output is not None").
- The strategy to generate inputs is as complex as the system under test.

## Examples

**Strategy composition bottom-up.** Each strategy draws from simpler strategies, never from raw primitives:

```python
@st.composite
def realistic_paths(
    draw: st.DrawFn,
    board_width: float = 200.0,
    board_height: float = 150.0,
) -> RoutePath:
    n_points = draw(st.integers(min_value=2, max_value=50))
    xs = [draw(st.floats(0, board_width)) for _ in range(n_points)]
    ys = [draw(st.floats(0, board_height)) for _ in range(n_points)]
    path = RoutePath(net_name=draw(st.sampled_from(NET_NAME_VOCAB)),
                     coordinates=list(zip(xs, ys)),
                     layer_name=draw(st.sampled_from(LAYERS)),
                     path_length=0.0)
    # Compute path length from coordinates
    path.path_length = sum(
        ((xs[i]-xs[i-1])**2 + (ys[i]-ys[i-1])**2) ** 0.5
        for i in range(1, len(xs))
    )
    return path

@st.composite
def routing_results(draw: st.DrawFn) -> RoutingResults:
    lines = {}
    for i in range(draw(st.integers(0, 15))):
        lines[f"NET_{i}"] = draw(compiled_route())
    return RoutingResults(
        compiled_routes=lines,
        failed_nets=[f"FAIL_{j}" for j in range(draw(st.integers(0, 5)))],
    )
```

**Spanning multiple invariant classes.** Each theorem file imports the shared strategies and asserts one category:

```python
# test_router_v6_output_validity_pbt.py — structural correctness
@pytest.mark.property
@given(pcb=parsed_pcb())
@settings(max_examples=100, deadline=30000)
def test_parsed_pcb_valid_structure(pcb):
    assert pcb.board.width > 0
    assert len(pcb.components) >= 2
    assert pcb.design_rules is not None
    assert pcb.stackup is not None

# test_router_v6_geometric_invariants_pbt.py — spatial invariants
@pytest.mark.property
@given(rr=routing_results(board_width=200.0, board_height=150.0))
@settings(max_examples=100, deadline=30000)
def test_all_path_coordinates_within_board_bounds(rr):
    for route in rr.compiled_routes.values():
        for x, y in route.path.coordinates:
            assert 0 <= x <= 200.0 and 0 <= y <= 150.0
```

## Related

- `docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md` — placement invariant suite that caught the 250M boundary loss bug using this pattern
- `docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md` — existing PBT pattern for 17 Stage 2 micro-steps with conventions documented
- `packages/temper-placer/tests/router_v6/router_v6_property_strategies.py` — shared strategy file for Router V6 invariant tests
- `packages/temper-placer/tests/router_v6/test_router_v6_*_pbt.py` — 4-class invariant test suite (26 tests)
- `packages/temper-placer/tests/router_v6/test_dfm_hypothesis_fuzzing.py` — existing DFM fuzzing suite extended (not duplicated) by the DRC class
- `docs/solutions/architecture-patterns/4layer-invariant-chain-boundary-enforcement-2026-06-30.md` — concise (< 80 lines) implementation of this pattern in `test_4layer_output_properties.py`: single invariant theorem, 5 test methods, CI-gated on every push
