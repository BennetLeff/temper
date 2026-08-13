"""Object builders for the ``escape_via_generator`` corpus.

``_escape_via_cases.py`` is pure data on purpose; this module is the
data -> object adapter for the Python arms.
"""

from __future__ import annotations

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

__all__ = ["build_component", "build_dense_package", "build_design_rules", "build_pads"]


def build_component(
    position: tuple[float, float] | None,
    rotation: int | None,
    side: int | None,
    pins: list,
) -> Component:
    """``pins`` rows are ``(number, (px, py), net, width, height, shape)``."""
    return Component(
        ref="U1",
        footprint="TEST-BGA",
        bounds=(10.0, 10.0),
        pins=[
            Pin(
                name=num,
                number=num,
                position=pos,
                net=net,
                width=w,
                height=h,
                shape=shape,
            )
            for (num, pos, net, w, h, shape) in pins
        ],
        initial_position=position,
        initial_rotation_quadrant=rotation,
        initial_side=side,
    )


def build_dense_package(case: tuple) -> DensePackage:
    _label, position, rotation, side, pitch, package_type, pins = case
    return DensePackage(
        component=build_component(position, rotation, side, pins),
        pin_count=len(pins),
        pitch_mm=pitch,
        package_type=package_type,
        requires_escape=True,
    )


def build_design_rules(case: tuple) -> DesignRules:
    _label, classes, assignments, defaults = case
    clearance, trace_w, via_dia, via_drill = defaults
    return DesignRules(
        net_classes={
            name: NetClassRules(
                name=name,
                clearance_mm=c,
                trace_width_mm=t,
                via_diameter_mm=vd,
                via_drill_mm=vdr,
                diff_pair_gap_mm=None,
                diff_pair_width_mm=None,
                current_rating_amps=None,
                safety_category=None,
            )
            for name, (c, t, vd, vdr) in classes.items()
        },
        net_class_assignments=dict(assignments),
        default_clearance_mm=clearance,
        default_trace_width_mm=trace_w,
        default_via_diameter_mm=via_dia,
        default_via_drill_mm=via_drill,
        min_hole_to_hole_mm=0.5,
        min_annular_ring_mm=0.1,
    )


def build_pads(pads: list) -> Component:
    """``[(x, y, width, height, shape)]`` -> a component of bare pads.

    Used by the ``_is_position_valid`` probes, which take a ``Component``
    only to iterate ``component.pins``.
    """
    def _pin(i, row):
        # 5-tuple keeps the historical shape; a 6th element carries
        # ``roundrect_ratio``, which ``pin_world_radius`` reads and the Rust
        # kernel hardcoded to the default until 2026-08-06.
        x, y, w, h, s = row[:5]
        ratio = row[5] if len(row) > 5 else None
        kw = {} if ratio is None else {"roundrect_ratio": ratio}
        return Pin(
            name=str(i), number=str(i), position=(x, y), net=None,
            width=w, height=h, shape=s, **kw,
        )

    return Component(
        ref="P",
        footprint="PADS",
        bounds=(10.0, 10.0),
        pins=[_pin(i, row) for i, row in enumerate(pads)],
        initial_position=(0.0, 0.0),
        initial_rotation_quadrant=0,
    )
