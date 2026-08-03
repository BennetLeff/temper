"""Defect shape: weak-nooverlap2d encoding allowed zero-gap touching.

docs/solutions/logic-errors/weak-nooverlap2d-encoding-allows-zero-gap-2026-07-08.md:
the SEPARATED encoding must enforce a Chebyshev gap >= tau between bounds
boxes; the weak form permitted the boxes to touch (gap == 0) while still
reporting a satisfied constraint -- DRC then saw real shorts at the pad
level. The fix (encoder.py::_encode_separated) encodes the Chebyshev
disjunction with an explicit tau separation.
"""


def _encode_separated_unsound(placement, a, b, tau):
    # BUG: allows the boxes to share an edge (gap 0) -- "weak" no-overlap.
    return _chebyshev_gap(a, b) >= 0  # should be >= tau
