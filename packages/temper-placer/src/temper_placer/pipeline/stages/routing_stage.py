"""Routing stage: congestion-based routing verification."""

from __future__ import annotations

import time
from typing import Any

import jax.numpy as jnp

from temper_placer.pipeline.dag_types import DataContext, StageResult


class RoutingStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start = time.time()
        from temper_placer.router_v6.congestion import analyze_congestion

        print("Running routing verification...")

        board = context["board"]
        netlist = context["netlist"]
        placement_state = context.get("placement_state")

        if placement_state is not None:
            positions = placement_state.positions
        else:
            deterministic_result = context.get("deterministic_result")
            positions = jnp.array(deterministic_result.positions)

        result = analyze_congestion(netlist, board, positions=positions)
        print(f"Max congestion: {result.max_utilization:.2f}, Total overflow: {result.total_overflow:.2f}")

        state.routing_result = result

        completion = result.max_utilization
        if hasattr(result, "completion_rate"):
            completion = result.completion_rate
        elif hasattr(result, "is_feasible"):
            completion = 1.0 if result.is_feasible() else completion

        if not result.is_feasible():
            print("Warning: High congestion detected!")

        elapsed = time.time() - start
        return StageResult(
            outputs={
                "routing_result": result,
                "routing_completion": completion,
            },
            duration_s=elapsed,
        )
