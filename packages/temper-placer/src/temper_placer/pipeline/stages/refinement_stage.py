"""Refinement stage: iterative placement-routing loop with routability gradient."""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from temper_placer.pipeline.dag_types import DataContext, StageResult
from temper_placer.router_v6.adapter import MazeRouter


class RefinementStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start_time = time.time()
        from temper_placer.core.state import PlacementState
        from temper_placer.pipeline.iterator import PlaceRouteIterator

        board = context["board"]
        netlist = context["netlist"]
        routing_result = context.get("routing_result")
        placement_state = context.get("placement_state")
        max_iterations = context.get("max_iterations", 5)
        routability_threshold = context.get("routability_threshold", 0.85)
        convergence_threshold = context.get("convergence_threshold", 0.01)
        deadline = context.get("deadline", None)

        # U10: Routability gradient config
        routability_gradient_weight = context.get("routability_gradient_weight", 50.0)
        routability_gradient_max_grad_norm = context.get("routability_gradient_max_grad_norm", 1.0)
        routability_gradient_unsat_movement_multiplier = context.get(
            "routability_gradient_unsat_movement_multiplier", 2.0
        )
        routability_gradient_sat_timeout_ms = context.get("routability_gradient_sat_timeout_ms", 500.0)
        routability_gradient_unsat_escape_iterations = context.get(
            "routability_gradient_unsat_escape_iterations", 3
        )

        if routing_result is None:
            elapsed = time.time() - start_time
            return StageResult(outputs={}, duration_s=elapsed)

        if routing_result.is_feasible(threshold=routability_threshold):
            state._refinement_complete = True
            elapsed = time.time() - start_time
            return StageResult(
                outputs={"placement_state": placement_state, "routing_result": routing_result},
                duration_s=elapsed,
            )

        print(f"Starting iterative refinement (max {max_iterations} iterations)...")

        class OrchestratorRouter:
            def __init__(self, st):
                self.state = st

            def route(self, pos):
                router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
                router.block_board_features(board)
                router.block_components(netlist.components, pos, margin=-0.1, escape_length=5)

                success_count = 0
                for net in netlist.nets:
                    from temper_placer.router_v6.congestion import _get_pin_positions
                    pins = _get_pin_positions(netlist, net.name, pos)
                    if len(pins) < 2:
                        continue
                    res = router.route_net_adaptive(net.name, pins, None)
                    if res.success:
                        success_count += 1

                completion = success_count / len(netlist.nets)

                class Result:
                    def __init__(self, c, r):
                        self.completion_rate = c
                        self.router = r
                        self.is_feasible = lambda: c >= 1.0
                return Result(completion, router)

        def update_fn(pos, routing_res):
            # JAX gradient descent is retired; pass through CP-SAT placement directly.
            return np.array(pos)

        router = OrchestratorRouter(state)
        iterator = PlaceRouteIterator(
            netlist=netlist,
            board=board,
            router=router,
            placement_update_fn=update_fn,
            max_iterations=max_iterations,
            target_completion=routability_threshold,
            min_improvement=convergence_threshold,
        )

        current_pos = (placement_state.positions if placement_state is not None
                       else np.array(context["deterministic_result"].positions))
        result = iterator.run(current_pos)

        new_placement_state = PlacementState.from_positions(result.final_positions)
        state.placement_state = new_placement_state
        state.iteration = result.iterations
        state._refinement_complete = True

        print(f"Refinement complete. Best completion: {result.iteration_history[-1].completion_rate:.2%}")

        elapsed = time.time() - start_time
        return StageResult(
            outputs={
                "refinement_placement": new_placement_state,
                "refinement_routing_result": routing_result,
            },
            duration_s=elapsed,
        )


def _invoke_sat_solver(
    board, netlist, positions,  # noqa: ARG001, ARG001
    timeout_ms: float = 500.0,  # noqa: ARG001
    constraint_model_data: dict | None = None,
):
    """Invoke SAT solver for routability statistics (FR4.2, FR4.3).

    Returns:
        (solver_status, routability_scores, solver_stats, var_to_net, unsat_core)
    """
    # Build minimal constraint model if data available; else use coarse fallback.
    solver_stats = {}
    var_to_net = []
    unsat_core = []
    solver_status = "unknown"

    if constraint_model_data is not None:
        try:
            from temper_rust_router import solve_topology_rust
            py_vars = list(constraint_model_data.get("variables", []))
            py_cons = list(constraint_model_data.get("constraints", []))
            net_names = constraint_model_data.get("net_names", [])
            if py_vars and py_cons:
                rust_result = solve_topology_rust(py_vars, py_cons, net_names)
                solver_status = rust_result.get("status", "unknown")
                solver_stats = rust_result.get("solver_stats", {})
                var_to_net = list(rust_result.get("var_to_net", []))
                unsat_core = list(rust_result.get("unsat_core", []))
                return solver_status, None, solver_stats, var_to_net, unsat_core
        except Exception:
            pass

    # Coarse fallback: compute stats from board/netlist geometry (FR1.7).
    n_nets = len(netlist.nets) if hasattr(netlist, 'nets') else 0
    n_comps = netlist.n_components if hasattr(netlist, 'n_components') else 0
    num_vars = max(n_nets * 3, 1)  # Heuristic: 3 vars per net
    num_clauses = max(n_nets * 2, 1)
    solver_stats = {
        "conflicts": 0,
        "decisions": 0,
        "propagations": 0,
        "decision_level_histogram": [0] * 10,
        "unsat_core_size": 0,
        "variable_count": num_vars,
        "clause_count": num_clauses,
        "cpu_solve_time_ms": 10.0,  # nominal
        "clause_to_var_ratio": num_clauses / max(num_vars, 1),
        "solve_throughput": 0.0,
    }
    var_to_net = list(range(n_comps))
    solver_status = "unknown"

    return solver_status, None, solver_stats, var_to_net, unsat_core


def _log_routability_iteration(
    iteration_idx: int,
    score_mean: float,
    scores,
    solver_status: str,
    unsat_core_size: int,
    unsat_streak: int,
):
    """U9: Per-iteration routability logging (NFR3.1)."""
    top_n = 5
    if hasattr(scores, 'shape') and scores.shape[0] > 0:
        score_arr = np.asarray(scores)
        sorted_idx = np.argsort(score_arr)[::-1]
        worst_nets = sorted_idx[:top_n].tolist()
        worst_values = score_arr[worst_nets].tolist()
        worst_str = ", ".join(
            f"{i}:{v:.2f}" for i, v in zip(worst_nets, worst_values)
        )
    else:
        worst_str = "n/a"

    unsat_info = f", core={unsat_core_size}" if solver_status == "unsat" else ""
    streak_info = f", streak={unsat_streak}" if unsat_streak > 0 else ""

    print(
        f"Iteration {iteration_idx}: routability_mean={score_mean:.3f}, "
        f"worst_nets=[{worst_str}], sat_status={solver_status}"
        f"{unsat_info}{streak_info}"
    )


def _log_unsat_escape(streak: int):
    """U7: Log UNSAT persistence escape (FR6.4)."""
    print(
        f"    SAT solver could not guide convergence within budget "
        f"after {streak} UNSAT iterations — applying simple_congestion_repel"
    )


def simple_congestion_repel(positions, heatmap, netlist, board):  # noqa: ARG001, ARG001
    """U7: Fallback to congestion-based repulsion (FR6.4)."""
    pos_np = np.asarray(positions)
    from temper_placer.router_v6.congestion_heatmap import CongestionHeatmap
    if not isinstance(heatmap, CongestionHeatmap):
        return np.array(pos_np)
    indices = heatmap.get_hotspots(threshold=0.3)
    if not indices:
        return np.array(pos_np)
    max_disp = 2.0
    for (gx, gy) in indices[:50]:
        cx = gx * 0.5 + 5.0
        cy = gy * 0.5 + 5.0
        hotspot = np.array([cx, cy])
        for ci in range(min(len(pos_np), 10)):
            disp = pos_np[ci] - hotspot
            dist = float(np.linalg.norm(disp))
            if dist < max_disp:
                pos_np[ci] += disp / max(dist, 0.1) * 1.5
    return np.array(pos_np)
