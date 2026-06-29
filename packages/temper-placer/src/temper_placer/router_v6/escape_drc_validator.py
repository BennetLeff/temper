"""
Router V6 Stage 1.5: Validate Escape Plan DRC

Validates escape vias against design rules (spacing, annular ring).
Part of temper-ipar (Stage 1 - Pin Escape Planning)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from temper_placer.core.netlist import Component
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.stage0_data import DesignRules


@dataclass
class DRCViolation:
    """
    Design Rule Check violation.

    Attributes:
        message: Description of the violation.
        violation_type: Type code (e.g. "via-via", "via-pad", "annular").
        location: (x, y) coordinates of the violation.
        related_objects: List of related object descriptions (e.g. ["Via 1", "Via 2"]).
    """

    message: str
    violation_type: str
    location: tuple[float, float]
    related_objects: list[str]


def validate_escape_plan(
    vias: list[EscapeVia],
    components: list[Component],
    design_rules: DesignRules,
) -> list[DRCViolation]:
    """
    Validate an escape via plan against design rules.

    Checks:
    1. Via-to-Via spacing (clearance and hole-to-hole).
    2. Via-to-Pad spacing (clearance).
    3. Annular ring dimensions.

    Args:
        vias: List of planned escape vias.
        components: List of placed components (for pad checks).
        design_rules: Design rules (clearances, minimums).

    Returns:
        List of DRCViolation objects. Empty if clean.
    """
    violations = []

    # 1. Annular Ring Check
    violations.extend(_check_annular_rings(vias, design_rules))

    # 2. Via-to-Via Spacing
    violations.extend(_check_via_via_spacing(vias, design_rules))

    # 3. Via-to-Pad Spacing
    violations.extend(_check_via_pad_spacing(vias, components, design_rules))

    return violations


def _check_annular_rings(vias: list[EscapeVia], rules: DesignRules) -> list[DRCViolation]:
    violations = []
    min_ring = rules.min_annular_ring_mm

    for via in vias:
        ring = (via.diameter - via.drill) / 2.0
        if ring < min_ring - 1e-6:
            violations.append(DRCViolation(
                message=f"Insufficient annular ring: {ring:.3f}mm < {min_ring}mm",
                violation_type="annular",
                location=via.position,
                related_objects=[f"Via {via.net_name} (Pin {via.pin_number})"]
            ))
    return violations


def _check_via_via_spacing(vias: list[EscapeVia], rules: DesignRules) -> list[DRCViolation]:
    violations = []
    n = len(vias)
    min_hole_to_hole = rules.min_hole_to_hole_mm

    for i in range(n):
        for j in range(i + 1, n):
            v1 = vias[i]
            v2 = vias[j]

            # Distance between centers
            dx = v1.position[0] - v2.position[0]
            dy = v1.position[1] - v2.position[1]
            dist = math.sqrt(dx*dx + dy*dy)

            # Check 1: Hole-to-Hole (Physical constraint, regardless of net)
            hole_dist = dist - (v1.drill / 2.0) - (v2.drill / 2.0)
            if hole_dist < min_hole_to_hole - 1e-6:
                violations.append(DRCViolation(
                    message=f"Insufficient hole-to-hole spacing: {hole_dist:.3f}mm < {min_hole_to_hole}mm",
                    violation_type="hole-to-hole",
                    location=v1.position,
                    related_objects=[f"Via {v1.net_name}", f"Via {v2.net_name}"]
                ))

            # Check 2: Electrical Clearance (Different Nets)
            if v1.net_name != v2.net_name:
                # Get max clearance requirement of the two nets
                c1 = rules.get_rules_for_net(v1.net_name).clearance_mm
                c2 = rules.get_rules_for_net(v2.net_name).clearance_mm
                req_clearance = max(c1, c2)

                # Copper-to-Copper distance
                copper_dist = dist - (v1.diameter / 2.0) - (v2.diameter / 2.0)

                if copper_dist < req_clearance - 1e-6:
                    violations.append(DRCViolation(
                        message=f"Insufficient via-via clearance: {copper_dist:.3f}mm < {req_clearance}mm",
                        violation_type="via-via",
                        location=v1.position,
                        related_objects=[f"Via {v1.net_name}", f"Via {v2.net_name}"]
                    ))

    return violations


def _check_via_pad_spacing(
    vias: list[EscapeVia],
    components: list[Component],
    rules: DesignRules
) -> list[DRCViolation]:
    violations = []

    # Pre-calculate component transforms for efficiency?
    # For now, just iterate.

    for comp in components:
        comp_x, comp_y = 0.0, 0.0
        if comp.initial_position:
            comp_x, comp_y = comp.initial_position

        if comp.initial_rotation is not None:
            float(comp.initial_rotation) * math.pi / 2.0

        for pin in comp.pins:
            pin_pos = pin_world_position(pin, comp)
            # Conservative radius for pad
            pin_radius = max(pin.width, pin.height) / 2.0

            for via in vias:
                # If same net, clearance usually doesn't apply (connected)
                # Unless it's a "via-in-pad" check for fabrication reasons, but
                # here we are checking electrical clearance.
                if via.net_name == pin.net:
                    continue

                # If via is "via-in-pad" on THIS pin, it's fine (but net check handles it).

                dx = via.position[0] - pin_pos[0]
                dy = via.position[1] - pin_pos[1]
                dist = math.sqrt(dx*dx + dy*dy)

                # Electrical Clearance
                c_via = rules.get_rules_for_net(via.net_name).clearance_mm
                c_pin = 0.0
                if pin.net:
                    c_pin = rules.get_rules_for_net(pin.net).clearance_mm
                req_clearance = max(c_via, c_pin)

                copper_dist = dist - (via.diameter / 2.0) - pin_radius

                if copper_dist < req_clearance - 1e-6:
                    violations.append(DRCViolation(
                        message=f"Insufficient via-pad clearance: {copper_dist:.3f}mm < {req_clearance}mm",
                        violation_type="via-pad",
                        location=via.position,
                        related_objects=[f"Via {via.net_name}", f"Pin {comp.ref}-{pin.number}"]
                    ))

    return violations
