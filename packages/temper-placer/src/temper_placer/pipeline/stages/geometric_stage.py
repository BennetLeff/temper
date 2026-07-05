"""Geometric stage: CP-SAT placement (JAX gradient-descent removed)."""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from temper_placer.pipeline.dag_types import DataContext, StageResult


class GeometricStage:
    """CP-SAT placement dispatch stage (JAX gradient descent removed)."""

    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start_time = time.time()

        deterministic_result = context.get("deterministic_result")
        if deterministic_result is None:
            from temper_placer.pipeline.topological import run_topological_phase
            state = run_topological_phase(state)
            deterministic_result = state.deterministic_result

        from temper_placer.core.state import PlacementState

        positions = np.array(deterministic_result.positions, dtype=np.float32)
        placement_state = PlacementState.from_positions(positions)
        state.placement_state = placement_state

        elapsed = time.time() - start_time
        return StageResult(
            outputs={"placement_state": placement_state},
            duration_s=elapsed,
        )
