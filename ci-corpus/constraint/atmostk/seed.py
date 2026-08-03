"""Defect shape: unsound AtMostK capacity encoding in the router_v6 SAT solver.

docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md: the single
clause "at least one of the surplus N-K variables must be false" lets a
K=3 channel accept 6 nets -- necessary but not sufficient for K > 1.
"""


def _encode_atmostk_single_clause(vars_, k):
    # BUG: one clause over the surplus set is not a K-cap for K > 1.
    surplus = vars_[k:]
    return [sum(surplus) <= len(surplus) - 1]  # unsound for K > 1
