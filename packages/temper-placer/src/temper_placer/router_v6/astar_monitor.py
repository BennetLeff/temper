"""
Runtime invariant monitor for A* pathfinding.

Context-manager-activated monitor that checks four structural invariants
during ``_astar_search`` execution. Zero overhead when the context
manager is not active (R11, SC6).

Activation::
    from temper_placer.router_v6.astar_monitor import astar_monitor
    with astar_monitor():
        path = _astar_search(start, goal, grid)

If any invariant is violated, violations are accumulated and reported
when the context manager exits.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

# Thread-safe monitor activation flag (R11: context-manager, no signature changes)
_local = threading.local()


def _is_monitor_active() -> bool:
    return getattr(_local, "active", False)


def _set_monitor_active(active: bool) -> None:
    _local.active = active


@dataclass
class InvariantViolation:
    """A single invariant violation detected by the monitor."""
    invariant: str
    detail: str
    context: dict[str, Any] | None = None

    def __str__(self) -> str:
        ctx = f" ({self.context})" if self.context else ""
        return f"[{self.invariant}] {self.detail}{ctx}"


class MonitorState:
    """Accumulated monitor state during one A* execution."""

    def __init__(self) -> None:
        self.violations: list[InvariantViolation] = []
        self.last_f: float | None = None
        self.start: tuple[int, int] | None = None
        self.goal: tuple[int, int] | None = None
        self.monitor_closed: set[tuple[int, int]] = set()
        self.check_single_expansion: bool = False  # Disabled: _astar_search allows re-expansion

    def record_pop(self, current: tuple[int, int], f_cost: float) -> None:
        """Record a node pop from the frontier."""
        # (a) f-cost monotonicity.
        # Allow 1e-3 epsilon: the code uses 1.414 for diagonal move cost
        # while octile heuristic uses sqrt(2)-1, creating a ~2e-4 gap per
        # diagonal step.  With up to ~100 cells per path the cumulative
        # gap may reach ~2e-2, so 1e-3 per-step tolerance is tight enough
        # to catch genuine PQ ordering bugs while accepting the 1.414
        # approximation.
        if self.last_f is not None:
            if f_cost + 1e-3 < self.last_f:
                self.violations.append(InvariantViolation(
                    "f_cost_monotonicity",
                    f"f-cost decreased: last={self.last_f:.6f}, current={f_cost:.6f}",
                    {"current": current},
                ))
        self.last_f = f_cost

        # (b) Single-expansion check (standard A* only)
        if self.check_single_expansion:
            if current in self.monitor_closed:
                self.violations.append(InvariantViolation(
                    "single_expansion",
                    f"Node re-expanded: {current}",
                    {"current": current},
                ))
            self.monitor_closed.add(current)

    def validate_cost_lower_bound(
        self, path: list[tuple[int, int]], g_score: dict, came_from: dict
    ) -> None:
        """(c) Recompute path cost from came_from chain and compare to g_score[goal]."""
        if not path:
            return
        goal = path[-1]
        if goal not in g_score:
            return

        # Recompute cost by traversing came_from chain using the same
        # move costs as astar_core.py (1.414 for diagonal, 1.0 for cardinal).
        # The code uses 1.414 rather than exact sqrt(2).
        recomputed = 0.0
        node = goal
        while node in came_from and came_from[node] is not None:
            parent = came_from[node]
            dx = abs(node[0] - parent[0])
            dy = abs(node[1] - parent[1])
            step = 1.414 if dx != 0 and dy != 0 else 1.0
            recomputed += step
            node = parent

        stored = g_score[goal]
        if abs(recomputed - stored) > 1e-9:
            self.violations.append(InvariantViolation(
                "cost_lower_bound",
                f"Recomputed cost {recomputed} != g_score[goal] {stored}",
                {"goal": goal},
            ))

    def validate_path_completeness(
        self, path: list[tuple[int, int]], start: tuple[int, int], goal: tuple[int, int]
    ) -> None:
        """(d) Verify path starts at start, ends at goal, consecutive adjacency."""
        if not path:
            self.violations.append(InvariantViolation(
                "path_completeness",
                "Empty path returned",
            ))
            return

        if path[0] != start:
            self.violations.append(InvariantViolation(
                "path_completeness",
                f"Path does not start at start: first={path[0]}, start={start}",
            ))
        if path[-1] != goal:
            self.violations.append(InvariantViolation(
                "path_completeness",
                f"Path does not end at goal: last={path[-1]}, goal={goal}",
            ))

        for i in range(len(path) - 1):
            dx = abs(path[i + 1][0] - path[i][0])
            dy = abs(path[i + 1][1] - path[i][1])
            if dx > 1 or dy > 1 or (dx == 0 and dy == 0):
                self.violations.append(InvariantViolation(
                    "path_completeness",
                    f"Non-adjacent or duplicate step: {path[i]} -> {path[i + 1]}",
                    {"i": i},
                ))
                break  # One violation is enough for the path


# Global state shared between context manager and A* functions
_current_monitor_state: MonitorState | None = None


def get_monitor_state() -> MonitorState | None:
    """Return the current monitor state, or None if monitor is inactive."""
    return _current_monitor_state if _is_monitor_active() else None


class astar_monitor:
    """Context manager that activates the A* runtime invariant monitor.

    On enter: enables monitoring, resets state.
    On exit: disables monitoring, validates accumulated state, reports
    violations via pytest.fail (CI) or logging (production).
    """

    def __init__(self, check_single_expansion: bool = False) -> None:
        self._check_single_expansion = check_single_expansion

    def __enter__(self) -> MonitorState:
        global _current_monitor_state
        _set_monitor_active(True)
        _current_monitor_state = MonitorState()
        _current_monitor_state.check_single_expansion = self._check_single_expansion
        return _current_monitor_state

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        global _current_monitor_state
        state = _current_monitor_state
        _set_monitor_active(False)
        _current_monitor_state = None

        if state is not None and state.violations:
            import logging
            import os

            lines = [f"- {v}" for v in state.violations]
            msg = "A* invariant violations detected:\n" + "\n".join(lines)

            # CI mode: hard-fail via pytest so regressions block PRs
            if os.environ.get("PYTEST_CURRENT_TEST"):
                import pytest  # noqa: F811
                pytest.fail(msg)

            logging.getLogger(__name__).warning(msg)

        return False  # Don't suppress exceptions
