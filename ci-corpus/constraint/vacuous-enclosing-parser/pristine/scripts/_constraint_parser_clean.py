def _is_resolved(constraint):
    if not constraint.inner:
        return False
    inner_ok = all(r.ok for r in constraint.inner)
    return inner_ok
