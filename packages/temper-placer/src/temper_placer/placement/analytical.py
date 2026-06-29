"""
Analytical Legalizer.

Uses Linear Programming to snap spectral placement to a valid grid
while preserving relative order.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog

from temper_placer.placement.audit import PlacementAuditor
from temper_placer.router_v6.stage0_data import ParsedPCB


class AnalyticalLegalizer:
    def __init__(self, pcb: ParsedPCB):
        self.pcb = pcb
        self.auditor = PlacementAuditor(pcb)
        self.components = pcb.components
        self.ref_to_idx = {c.ref: i for i, c in enumerate(self.components)}

    def legalize(
        self,
        target_coords: dict[str, tuple[float, float]],
        board_bounds: tuple[float, float, float, float],
    ):
        """
        Legalize placement using LP.

        Args:
            target_coords: dict {ref: (x, y)} from Spectral Placer (scaled).
            board_bounds: (min_x, min_y, max_x, max_y)
        """
        # 1. Extract sizes
        widths = []
        heights = []
        for c in self.components:
            # Get courtyard bounds
            poly = self.auditor.courtyards[c.ref]
            minx, miny, maxx, maxy = poly.bounds
            widths.append(maxx - minx)
            heights.append(maxy - miny)

        # 2. Separate X and Y problems
        # We solve them sequentially or independently.

        # Build Constraint Graphs based on Target Order
        # Sort indices by X target
        x_sorted = sorted(
            range(len(self.components)), key=lambda i: target_coords[self.components[i].ref][0]
        )
        y_sorted = sorted(
            range(len(self.components)), key=lambda i: target_coords[self.components[i].ref][1]
        )

        # Solve X
        new_x = self._solve_1d(
            [target_coords[c.ref][0] for c in self.components],
            widths,
            x_sorted,
            board_bounds[0],
            board_bounds[2],
        )

        # Solve Y
        new_y = self._solve_1d(
            [target_coords[c.ref][1] for c in self.components],
            heights,
            y_sorted,
            board_bounds[1],
            board_bounds[3],
        )

        # Update positions
        for i, c in enumerate(self.components):
            c.initial_position = (float(new_x[i]), float(new_y[i]))

        return True

    def _solve_1d(
        self,
        targets: list[float],
        sizes: list[float],
        order: list[int],
        min_val: float,
        max_val: float,
    ) -> np.ndarray:
        """
        Solve 1D compaction problem.
        Minimize sum |x_i - target_i|.
        Subject to: x_{order[i+1]} >= x_{order[i]} + (size_i + size_{i+1})/2
        And bounds.
        """
        n = len(targets)

        # LP Variables: x_0 ... x_{n-1}
        # But |x - t| is non-linear.
        # Standard trick: x_i - t_i <= u_i, t_i - x_i <= u_i. Minimize sum u_i.
        # Variables: [x_0...x_{n-1}, u_0...u_{n-1}] (2n vars)

        # Objective: 0*x + 1*u
        c = np.zeros(2 * n)
        c[n:] = 1.0

        A_ub = []
        b_ub = []

        # Constraints for absolute value:
        # x_i - u_i <= t_i  -> x_i - u_i <= t_i
        # -x_i - u_i <= -t_i
        for i in range(n):
            # x_i - u_i <= t_i
            row = np.zeros(2 * n)
            row[i] = 1
            row[n + i] = -1
            A_ub.append(row)
            b_ub.append(targets[i])

            # -x_i - u_i <= -t_i
            row = np.zeros(2 * n)
            row[i] = -1
            row[n + i] = -1
            A_ub.append(row)
            b_ub.append(-targets[i])

        # Separation constraints (based on sorted order)
        # x_{next} - x_{curr} >= min_dist
        # -x_{next} + x_{curr} <= -min_dist
        for k in range(n - 1):
            curr_idx = order[k]
            next_idx = order[k + 1]

            min_dist = (sizes[curr_idx] + sizes[next_idx]) / 2.0 + 0.1  # 0.1mm margin

            row = np.zeros(2 * n)
            row[curr_idx] = 1
            row[next_idx] = -1
            A_ub.append(row)
            b_ub.append(-min_dist)

        # Bounds constraints
        # x_i >= min + w/2
        # x_i <= max - w/2
        bounds = []
        for i in range(n):
            w = sizes[i] / 2.0
            bounds.append((min_val + w, max_val - w))
        # u_i bounds (0, inf)
        for _i in range(n):
            bounds.append((0, None))

        # Solve
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

        if res.success:
            return res.x[:n]
        else:
            print(f"LP Failed: {res.message}")
            return np.array(targets)  # Fallback
