"""Defect shape: endpoint-only bounding without a monotonicity proof.

docs/solutions/logic-errors/endpoint-bounding-unsound-without-monotonicity-2026-07-09.md:
physics/operating_point.py bounded the coupled-load operating point by
evaluating only the coupling extremes (k=0, k=1) and treating them as bounds
on [0,1]. Endpoint evaluation bounds the interior only if the function is
monotone; an interior extremum can breach a ceiling while both endpoints pass.
"""


def _bound_worst_case(k_lo, k_hi):
    # BUG: samples only the two extremes; no monotonicity proof, no interior.
    return max(_eval(0.0), _eval(1.0))  # interior extremum can exceed both
