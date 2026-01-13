"""
Differential Pair Routing Experiments

This package contains incremental experiments for developing a true coupled
differential pair router that checks DRC oracle at every routing step.

Current Problem:
- Existing router operates on grid cells, applies post-processing offsets
- Post-offsets push traces into obstacles not in original obstacle set
- Results in 21 track_pad_clearance violations (all USB diff pairs)

New Approach:
- Route P and N traces simultaneously as coupled pair
- Check DRC oracle for BOTH actual trace positions at every step
- Maintain constant spacing (impedance control)
- Enforce length matching during routing
- Use 45° mitered corners

Experiments:
- EXP-0: Baseline measurement and documentation
- EXP-1: Minimal coupled router (straight lines + DRC oracle)
- EXP-2: 45° corner support
- EXP-3: A* with obstacle avoidance
- EXP-4: Length matching with serpentines
- EXP-5: Via transitions
- EXP-6: Full integration test on USB

Design Decisions:
- Grid resolution: 0.1mm (finer than 0.25mm normal routing)
- Corner style: 45° mitered (industry standard)
- Serpentine style: Trombone (rectangular bumps)
- Divergence: P outer, N inner
- Length matching: Enforced during routing
- Performance target: <2s per pair (correctness over speed)
"""

from .test_fixtures import TestFixture, create_test_fixtures
from .run_experiments import run_experiment, run_all_experiments

__all__ = [
    "TestFixture",
    "create_test_fixtures",
    "run_experiment",
    "run_all_experiments",
]
