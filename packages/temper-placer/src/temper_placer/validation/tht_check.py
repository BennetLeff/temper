"""
Validation check for THT hole collisions.

Part of Phase 3: Placement Validation (temper-d336).
"""

import math

from temper_placer.core.netlist import Netlist


def validate_hole_clearance(
    netlist: Netlist,
    positions: list[tuple[float, float]],
    min_clearance: float = 0.25
) -> list[str]:
    """Check for THT hole collisions.

    Args:
        netlist: Component netlist
        positions: List of (x, y) positions corresponding to components
        min_clearance: Minimum required clearance between hole edges (mm)

    Returns:
        List of violation messages
    """
    violations = []
    holes = []

    # Extract all holes with their absolute positions
    for i, comp in enumerate(netlist.components):
        pos = positions[i]
        for pad in comp.pads:
            if pad.drill > 0:
                # Calculate absolute position (assuming 0 rotation for now)
                # TODO: Support rotation
                abs_x = pos[0] + pad.position[0]
                abs_y = pos[1] + pad.position[1]
                holes.append({
                    'ref': comp.ref,
                    'pad': pad.number,
                    'x': abs_x,
                    'y': abs_y,
                    'drill': pad.drill,
                    'radius': pad.drill / 2.0
                })

    # Check pairwise collisions
    for i in range(len(holes)):
        h1 = holes[i]
        for j in range(i + 1, len(holes)):
            h2 = holes[j]

            dx = h1['x'] - h2['x']
            dy = h1['y'] - h2['y']
            dist = math.sqrt(dx*dx + dy*dy)

            required = h1['radius'] + h2['radius'] + min_clearance

            if dist < required:
                violations.append(
                    f"{h1['ref']}.{h1['pad']} <-> {h2['ref']}.{h2['pad']}: "
                    f"dist={dist:.3f}mm (min {required:.3f}mm)"
                )

    return violations
