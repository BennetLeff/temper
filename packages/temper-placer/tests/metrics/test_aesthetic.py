"""Tests for aesthetic.py module.

Note: ``compute_aesthetic_score`` calls ``get_prefix_groups(netlist)`` internally,
which raises ``NotImplementedError`` (JAX retirement). The function only works
with empty netlists; non-empty netlists crash with an unhandled exception.
These tests cover the reachable execution paths without triggering the crash.
"""

import numpy as np

from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.metrics.aesthetic import compute_aesthetic_score


def test_compute_aesthetic_score_empty():
    """Empty placement returns perfect score."""
    state = PlacementState(
        positions=np.zeros((0, 2), dtype=np.float32),
        rotation_logits=np.zeros((0, 4), dtype=np.float32),
    )
    netlist = Netlist()
    result = compute_aesthetic_score(state, netlist)
    assert result["aesthetic_index"] == 1.0
