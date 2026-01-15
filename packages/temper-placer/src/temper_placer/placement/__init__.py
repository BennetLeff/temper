"""
Placement optimization module for temper-placer.

This module provides tools for optimizing component placement on PCBs,
with a focus on achieving provably routable layouts.

Key Components:
    - BendersMasterProblem: ILP-based placement optimization
    - Legalization: Post-optimization placement adjustment
"""

from temper_placer.placement.benders_master import (
    BendersMasterProblem,
    BendersMasterResult,
    BoardData,
    ComponentData,
    PlacementConstraints,
    run_benders_master,
)

__all__ = [
    "BendersMasterProblem",
    "BendersMasterResult",
    "BoardData",
    "ComponentData",
    "PlacementConstraints",
    "run_benders_master",
]
