"""Shared utility functions for the place-route loop controller.

Extracted from ``loop.py`` to avoid circular imports between
the loop class and its mixin modules.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.feedback import ConstraintDelta

logger = logging.getLogger(__name__)


def load_netclass_rules():
    import logging as _logging

    _logger = _logging.getLogger(__name__)
    try:
        from pathlib import Path

        from temper_placer.io.netclass_loader import load_netclass_rules as _load

        config_path = (
            Path(__file__).parent.parent.parent.parent.parent / "configs" / "netclass_rules.yaml"
        )
        if config_path.exists():
            return _load(config_path)
    except Exception:
        _logger.debug("netclass_rules.yaml not loaded", exc_info=True)
    return None


def positions_equal(a, b) -> bool:
    """Compare two position representations for equality within tolerance.

    Supports both numpy arrays (legacy) and dict[str, tuple[float, float]]
    (current CpSatPlacementResult.positions format).
    """
    if a is b:
        return True
    if type(a) is not type(b):
        return False

    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        for key in a:
            pa, pb = a[key], b[key]
            if abs(pa[0] - pb[0]) > 0.1 or abs(pa[1] - pb[1]) > 0.1:
                return False
        return True

    import numpy as np

    return bool(np.allclose(a, b, atol=0.1))


def deduplicate_deltas(deltas: list[ConstraintDelta]) -> list[ConstraintDelta]:
    """Deduplicate ConstraintDeltas by constraint ID, keeping latest.

    Prevents accumulated deltas from causing UNSAT when different
    rounds produce overlapping feedback for the same constraint.
    """
    seen: dict[str, ConstraintDelta] = {}
    for delta in deltas:
        cid = getattr(delta.constraint, "id", str(id(delta)))
        seen[cid] = delta
    return list(seen.values())
