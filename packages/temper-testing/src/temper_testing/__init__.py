"""
temper-testing: Testing toolkit for numerical optimization and placement verification.

Modules:
    oracle      - Test against known-correct answers
    gradients   - Verify autodiff vs numerical gradients
    viz         - Visual debugging for grids and paths
    determinism - Verify reproducibility
    metamorphic - Relationship-based testing
    strategies  - Hypothesis strategies for PCB domain
    invariants  - Runtime invariant checking
    golden      - Snapshot/golden file testing
"""

from temper_testing.determinism import verify, verify_with_seed
from temper_testing.gradients import check_gradient, find_discontinuities
from temper_testing.invariants import assert_invariant, check
from temper_testing.metamorphic import Property, verify_property
from temper_testing.oracle import bounded, exact, oracle_test
from temper_testing.viz import render_grid, render_placement

__all__ = [
    # Oracle
    "exact",
    "bounded",
    "oracle_test",
    # Gradients
    "check_gradient",
    "find_discontinuities",
    # Visualization
    "render_grid",
    "render_placement",
    # Determinism
    "verify",
    "verify_with_seed",
    # Metamorphic
    "Property",
    "verify_property",
    # Invariants
    "check",
    "assert_invariant",
]
