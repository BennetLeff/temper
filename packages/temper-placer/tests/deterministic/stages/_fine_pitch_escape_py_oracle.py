"""VERBATIM pre-migration oracle for ``deterministic/stages/fine_pitch_escape.py``.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/fine_pitch_escape.py``
at the dispatch base (origin/main). Do NOT edit: this file is the Python arm
of the differential. If it drifts, the differential proves nothing.

The two pure kernels — ``_calculate_min_pin_pitch`` and
``_get_escape_layer_for_net`` — are pinned as module-level functions. The
``run`` orchestration (via construction, the two passes, the escape
validation) stays Python in the shim and is not part of the oracle.
"""

import math


def _calculate_min_pin_pitch(pins):
    """Calculate minimum pin-to-pin distance for a component.

    Args:
        pins: The component's pin list (each with ``.position``).

    Returns:
        Minimum distance between any two pins in mm, or None if < 2 pins
    """
    if len(pins) < 2:
        return None

    min_dist = float("inf")

    # Check all pin pairs
    for i, pin1 in enumerate(pins):
        for pin2 in pins[i + 1 :]:
            dx = pin1.position[0] - pin2.position[0]
            dy = pin1.position[1] - pin2.position[1]
            dist = math.sqrt(dx * dx + dy * dy)
            min_dist = min(min_dist, dist)

    return min_dist if min_dist != float("inf") else None


def _get_escape_layer_for_net(
    net_name: str,
    layer2_nets,
    layer3_nets,
    escape_layer: int = 1,
    secondary_escape_layer: int = 2,
) -> tuple[int, str]:
    """Determine which layer a net should escape to.

    Returns:
        Tuple of (layer_number, layer_name)
    """
    # EXP-9: Analog/sensing nets to B.Cu (layer 3) for outer-layer routing
    if net_name in layer3_nets:
        return (3, "B.Cu")
    if net_name in layer2_nets:
        return (secondary_escape_layer, "In2.Cu")
    return (escape_layer, "In1.Cu")
