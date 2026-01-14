#!/usr/bin/env python3
"""
Experiment MT2: Pseudo-Boolean Constraints with PySAT.

Tests efficiency of encoding weighted capacity constraints (Metric Topology).
"""

from pysat.pb import PBEnc
from pysat.solvers import Glucose3
import time


def run_pb_experiment():
    print("Experiment MT2: PB Constraint Encoding")

    # Scenario: Channel width 2.0mm.
    # Signal Net: 0.2mm (Weight 2).
    # Power Net: 0.6mm (Weight 6).
    # Capacity: 20 units (0.1mm resolution).

    # 20 Nets total (15 Signal, 5 Power).
    # Which subset can pass?

    n_signals = 15
    n_power = 5
    total_vars = n_signals + n_power

    weights = [2] * n_signals + [6] * n_power
    literals = list(range(1, total_vars + 1))

    capacity = 20

    print(f"Problem: Select subset of {total_vars} nets to fit in {capacity} units.")
    print(f"Weights: {weights}")

    start = time.time()

    # Encode Sum(w_i * l_i) <= Capacity
    # PBEnc.atmost(lits, weights, bound)
    cnf = PBEnc.atmost(lits=literals, weights=weights, bound=capacity)

    encoding_time = time.time() - start
    print(f"Encoding Time: {encoding_time:.4f}s")
    print(f"Clauses generated: {len(cnf.clauses)}")

    solver = Glucose3()
    solver.append_formula(cnf.clauses)

    # Force at least 5 signals and 1 power
    # This forces the solver to find a non-trivial packing
    # 5 * 2 + 1 * 6 = 16 <= 20. Valid.
    # 6 * 2 + 2 * 6 = 12 + 12 = 24 > 20. Invalid.

    # We want to maximize flow? SAT just finds *one* valid assignment.
    # Let's force specific vars to be True and see if it holds.

    solve_start = time.time()
    is_sat = solver.solve(assumptions=[1, 2, 3, 4, 5, 16])  # 5 signals (1-5), 1 power (16)
    solve_time = time.time() - solve_start

    print(f"Solve Time: {solve_time:.4f}s")
    print(f"Result: {'SAT' if is_sat else 'UNSAT'}")

    # Try impossible: 2 power (16, 17) + 5 signals
    # 12 + 10 = 22 > 20.
    is_sat_bad = solver.solve(assumptions=[1, 2, 3, 4, 5, 16, 17])
    print(f"Impossible Result: {'SAT' if is_sat_bad else 'UNSAT'}")


if __name__ == "__main__":
    run_pb_experiment()
