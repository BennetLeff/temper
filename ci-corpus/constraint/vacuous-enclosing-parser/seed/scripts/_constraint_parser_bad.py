def _is_resolved(constraint):
    inner_ok = all(r.ok for r in constraint.inner)
    return inner_ok
