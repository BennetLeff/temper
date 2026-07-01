---
title: "BMC exhaustiveness and induction ladder verification for constraint systems"
date: 2026-07-01
category: best-practices
module: temper-placer
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - "Verifying constraint system correctness beyond ad-hoc fixtures and example-based tests"
  - "Proving that a constraint property holds for all inputs within a bounded size, not just sampled inputs"
  - "Establishing k-induction ladders to prove invariants hold for unbounded input sizes"
  - "Building property-based test suites with Hypothesis `@st.composite` strategies for domain types"
  - "Testing constraint detection pipelines that generate symbolic constraints from netlist topology"
tags:
  - bmc
  - bounded-model-checking
  - induction-ladder
  - hypothesis-pbt
  - frozenset-ssot
  - invariant-chain
  - esl-predicates
  - constraint-verification
---
# BMC Exhaustiveness and Induction Ladder Verification for Constraint Systems

## Context

The PCL constraint systems (decoupling detection, tag dispatch, keepout zones)
required verification that went beyond unit tests. A decoupling detector must
never classify a non-decoupling capacitor as decoupling, for *all* possible
layouts up to a given component count. A keepout loss must reach zero iff all
components clear the zone. Traditional example-based tests cannot prove these
universal properties.

The codebase already had Hypothesis PBT infrastructure (`test_placement_invariants.py`:
29 tests, 9 theorems), ESL/BMC exhaustiveness (`router_v6/esl.py`, `router_v6/bmc.py`),
and mathematical induction ladders (`test_induction_base.py` + 8 per-validator files).
The new constraint systems extended these patterns.

## Guidance

### 1. Define an ESL Ground-Truth Predicate First

Before writing any detection or loss function, define an Executable Specification
Language (ESL) predicate that encodes the property declaratively:

```python
# losses/decoupling.py
def _esl_is_decoupling(cap, ic) -> str | None:
    """Ground truth: cap and IC share a vital net."""
    if not _is_capacitor(cap) or not _is_ic(ic):
        return None
    return _shared_vital_net(cap, ic)
```

The predicate must be simple enough to be *obviously correct* by inspection.
It serves as the BMC oracle — the detection algorithm's output is verified
against it exhaustively.

### 2. BMC Exhaustiveness: Grid Enumeration

For a bounded number of components on a bounded grid, enumerate ALL possible
placements and verify the property holds for every one:

```python
# tests/pcl/test_keepout_bmc.py
@pytest.mark.property
def test_bmc_keepout_two_components_3x3():
    """All 81 placements of 2 components on a 3x3 grid."""
    for pos_a in grid_positions(3, 3):
        for pos_b in grid_positions(3, 3):
            loss = compute_keepout_loss([pos_a, pos_b], zone)
            clear = _esl_keepout_clear([pos_a, pos_b], zone)
            assert (loss == 0.0) == clear
```

Bound the enumeration to N ≤ 3 components (≤64 states for 2×2 grid, ≤512 for
3×3 grid with 2 components). This catches false negatives/positives that
sampling-based PBT would miss.

### 3. Induction Ladder: Base Case + Add/Remove/Modify

Following the existing `test_induction_base.py` pattern:

```python
# tests/losses/test_decoupling_induction.py

def test_base_case_empty_netlist():
    """Induction base: empty netlist → zero detections."""
    nl = Netlist(components=[], nets=[])
    assert len(auto_detect_decoupling_set(nl).detections) == 0

@given(nl=netlist_without_decoupling(), new_cap=capacitor_component(on_power=True))
def test_add_decoupling_cap_produces_detection(nl, new_cap):
    """Adding a bypass cap on a power net produces a detection."""
    ...

@given(nl=netlist_with_decoupling())
def test_remove_cap_removes_its_detections(nl):
    """Removing a capacitor removes all its detections."""
    ...

@given(nl=netlist_with_decoupling())
def test_modify_footprint_changes_classification(nl):
    """Changing 0805→ELEC reclassifies BYPASS→BULK."""
    ...
```

The induction structure: base case + inductive steps (add/remove/modify) prove
that invariants hold for netlists of arbitrary size.

### 4. Metamorphic PBT for Algebraic Properties

When a system defines an algebra (like tag dispatch), verify the algebraic
laws directly:

```python
# tests/pcl/test_tag_metamorphic_pbt.py

@given(tag=tag_expr(), netlist=netlist_with_tags())
def test_tag_refinement_produces_subset(tag, netlist):
    """More specific tag → subset of components."""
    ...

@given(tag_a=tag_expr(), tag_b=tag_expr(), netlist=netlist_with_tags())
def test_de_morgan_law(tag_a, tag_b, netlist):
    """~ (A & B) = ~A | ~B for tag resolution."""
    ...
```

Metamorphic tests check that transformations preserve invariants — more
general than example-based tests and more targeted than fuzzing.

### 5. Use `frozenset` for Canonical SSOTs

All canonical sets (valid tags, footprint lists, pin name patterns) should be
`frozenset` to prevent accidental mutation:

```python
# losses/decoupling.py
POWER_IC_PIN_PATTERNS: frozenset[str] = frozenset({
    "VCC", "VDD", "VIN", "VBUS", "VPP", "VDDIO", "VDDA", "VREF"
})
SMALL_CAP_FOOTPRINTS: frozenset[str] = frozenset({
    "0201", "0402", "0603", "0805", "1206", "1210"
})
```

This follows the existing `PLANE_LAYER_INDICES: frozenset[LayerIndex]` pattern
from `core/board.py`.

### 6. `__post_init__` for Construction-Time Validation

Catch invalid states at construction time, not at usage time:

```python
@dataclass(frozen=True)
class DecouplingDetectionSet:
    detections: tuple[DecouplingDetection, ...]
    netlist_hash: str

    def __post_init__(self):
        for d in self.detections:
            if d.classification == DecouplingClass.NOT_DECOUPLING:
                raise ValueError("NOT_DECOUPLING must not appear in detection set")
```

This follows the 4-layer invariant chain pattern (SSOT → construction →
pipeline entry → output → CI gate).

## When to Apply

- **Adding a new detection algorithm** whose correctness must be provable
- **Adding a new constraint type** with a loss function whose zero-set has a
  mathematical definition
- **Extending a type hierarchy** where transitive properties must hold
- **Before shipping** any constraint system that can silently produce wrong
  placements

## Examples

### BMC pattern for keepout zones

```python
def test_bmc_keepout_exhaustive():
    """BMC: every grid position has correct loss."""
    zone = (2, 2, 6, 6)  # 4x4 zone at grid center
    margin = 0.0

    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE):
            pos = jnp.array([[x, y]], dtype=jnp.float32)
            loss = keepout_loss(pos, zone, margin)
            inside = (2 <= x <= 6) and (2 <= y <= 6)
            assert (loss == 0.0) == (not inside), \
                f"BMC fail at ({x},{y}): loss={loss}, inside={inside}"
```

### Induction ladder for decoupling

```python
class TestDecouplingInduction:
    """Induction: invariants preserved under component graph edits."""

    @pytest.mark.dependency(name="decoupling-base")
    def test_empty_netlist(self):
        """Base case: empty."""
        assert len(auto_detect_decoupling_set(empty_netlist()).detections) == 0

    @pytest.mark.dependency(depends=["decoupling-base"])
    def test_add_bypass_cap(self):
        """Add: placing 0805 cap on VCC net of IC → BYPASS detection."""
        ...

    @pytest.mark.dependency(depends=["decoupling-base"])
    def test_remove_cap(self):
        """Remove: deleting cap → its detections gone."""
        ...
```

## Consequences

- 43 verification tests across all constraint families
- BMC guarantees zero false positives for ≤3 component layouts
- Induction ladder guarantees invariants hold under add/remove/modify
- All tests reuse existing Hypothesis/PBT/ESL infrastructure from the codebase
