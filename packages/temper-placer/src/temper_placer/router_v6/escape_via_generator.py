"""
Router V6 Stage 1.3: Compute Escape Via Positions

Calculates via positions for dense packages using dog-bone or via-in-pad strategies.
Part of temper-ipar (Stage 1 - Pin Escape Planning)

Wave 4 Phase B (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
``generate_escape_vias`` delegates to ``temper_geometry``
(``escape_generate_vias_py``), the pure geometry/clearance kernel. The
kernel was blocked (PR #751) on a real divergence -- it hardcoded
``DEFAULT_ROUNDRECT_RATIO`` while the shipped ``core/pin_geometry.py`` reads
``pin.roundrect_ratio`` -- fixed in #829 with a corpus row that pins the
fallback (``getattr(pin, "roundrect_ratio", None) or DEFAULT``: 0.0 is
falsy, so a zero ratio also takes the default). Re-verified here: the
shipped module is still AST-identical to its pinned oracle, and the fix is
present (see ``packages/temper-geometry/src/escape_via.rs``'s
``PadRow::world_radius``).

``_is_position_valid`` (private, previously called for every dog-bone
candidate) is gone: its entire body -- including the two traps documented
below -- now lives inside the kernel's own ``is_position_valid``, and the
kernel is exercised as part of ``generate_escape_vias``'s single Rust call
rather than as a separate Python-visible step. Two behaviours worth keeping
in mind because a "helpful" rewrite would silently break them:

* **NaN is ACCEPTED, not rejected.** ``dist < required_dist - 0.001`` is
  ``False`` when ``dist`` is NaN, so a NaN candidate distance makes the
  position valid and the via IS placed there.
* **The clearance check does not exempt the source pin's own net** --
  ``_ignore_net`` was accepted as a parameter and never read.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg

from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.stage0_data import DesignRules


@dataclass
class EscapeVia:
    """
    Computed escape via definition.

    Attributes:
        position: (x, y) absolute coordinates in mm.
        net_name: Name of the net.
        pin_number: Pin number being escaped.
        diameter: Via diameter in mm.
        drill: Via drill diameter in mm.
        via_type: "dog-bone" or "via-in-pad".
        layer: KiCad layer name resolved from the component's side
            (e.g. "F.Cu" or "B.Cu").
    """

    position: tuple[float, float]
    net_name: str
    pin_number: str
    diameter: float
    drill: float
    via_type: str
    layer: str = "F.Cu"


def _design_rules_wire(design_rules: DesignRules) -> tuple:
    """Marshal ``DesignRules`` into the kernel's ``(classes, assignments,
    defaults)`` tuple contract.

    Each ``NetClassRules``/defaults group is reduced to the 4-tuple
    ``(clearance_mm, trace_width_mm, via_diameter_mm, via_drill_mm)`` --
    exactly the fields ``escape_via.rs``'s ``Rules`` struct reads. The
    kernel's own ``DesignRules::for_net`` reproduces
    ``get_rules_for_net``'s fall-through (no assignment, an EMPTY class
    name, or a class name absent from ``net_classes`` all yield the
    defaults), so the assignments dict is passed through unmarshalled.
    """
    classes = {
        name: (r.clearance_mm, r.trace_width_mm, r.via_diameter_mm, r.via_drill_mm)
        for name, r in design_rules.net_classes.items()
    }
    defaults = (
        design_rules.default_clearance_mm,
        design_rules.default_trace_width_mm,
        design_rules.default_via_diameter_mm,
        design_rules.default_via_drill_mm,
    )
    return (classes, dict(design_rules.net_class_assignments), defaults)


def generate_escape_vias(
    dense_pkg: DensePackage,
    design_rules: DesignRules,
    strategy: str = "dog-bone",
) -> list[EscapeVia]:
    """
    Generate escape vias for a dense package.

    Args:
        dense_pkg: The DensePackage to process.
        design_rules: Board design rules (clearance, via sizes).
        strategy: "dog-bone" (default) or "via-in-pad".

    Returns:
        List of EscapeVia objects.
    """
    component = dense_pkg.component

    # `(initial_position, initial_rotation, initial_side, pitch_mm,
    # package_type, pins)` -- the kernel's `escape_generate_vias_py` package
    # contract. `package_type` is not read by the kernel (it has no bearing
    # on geometry) but the tuple shape requires the slot.
    package = (
        component.initial_position,
        component.initial_rotation,
        component.initial_side,
        dense_pkg.pitch_mm,
        dense_pkg.package_type,
        [
            (
                pin.number,
                pin.position,
                pin.net,
                pin.width,
                pin.height,
                pin.shape,
                pin.roundrect_ratio,
            )
            for pin in component.pins
        ],
    )
    rules = _design_rules_wire(design_rules)

    rows = _tg.escape_generate_vias_py(package, rules, strategy)

    return [
        EscapeVia(
            position=position,
            net_name=net_name,
            pin_number=pin_number,
            diameter=diameter,
            drill=drill,
            via_type=via_type,
            layer=layer,
        )
        for (position, net_name, pin_number, diameter, drill, via_type, layer) in rows
    ]
