"""HV creepage and isolation-slot reduction for phased component assignment.

Contains the :class:`_PhaseHVMixin` with ghost-pad injection (U1),
isolation-slot reduction (U2), and HV-pin position collection.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


class _PhaseHVMixin:
    """HV creepage / ghost-pad injection and isolation-slot reduction.

    Provides _collect_hv_pin_positions, _effective_ghost_pad_radius,
    _reserve_slots_with_hv, and _is_hv_ref.
    """

    def _collect_hv_pin_positions(
        self,
        netlist: Netlist,
    ) -> list[tuple[float, float, str, str]]:
        """Collect component-relative (x, y) positions for every HV-class pin.

        Returns a list of (pin_x, pin_y, component_ref, pin_name) tuples
        for pins whose net class has a non-None ``safety_category`` in
        :attr:`_HV_SAFETY_CATEGORIES`.  Pins whose net is missing from
        :attr:`design_rules.net_classes` (or has a non-HV / None safety
        tag) are silently skipped — this preserves NFR4 parity on
        LV-only boards.

        Coordinates are component-RELATIVE (i.e. relative to the
        component's local origin).  Callers that need absolute board
        positions must combine them with the component's actual
        placement.  The placer's per-component hook
        ``_reserve_slots_with_hv`` does exactly that and is the
        production path; this helper exists for the post-stage DRC
        fence validator (U3) and for any future analytic consumer that
        needs the pin-relative coordinate set.
        """
        if self.design_rules is None or not getattr(self.design_rules, "net_classes", None):
            return []

        net_classes = self.design_rules.net_classes
        net_class_assignments = getattr(self.design_rules, "net_class_assignments", {}) or {}

        hv_pins: list[tuple[float, float, str, str]] = []
        for component in netlist.components:
            for pin in component.pins:
                if pin.net is None:
                    continue
                class_name = net_class_assignments.get(pin.net)
                if class_name is None:
                    class_name = next(
                        (nc for nc in net_classes if nc == pin.net),
                        None,
                    )
                if class_name is None or class_name not in net_classes:
                    continue
                safety = getattr(net_classes[class_name], "safety_category", None)
                if safety not in self._HV_SAFETY_CATEGORIES:
                    continue
                px, py = pin.position
                hv_pins.append((float(px), float(py), component.ref, pin.name))
        return hv_pins

    def _effective_ghost_pad_radius(
        self,
        component_ref: str,
        _pin_name: str,
        base_radius: float,
        current_pin_absolute: tuple[float, float],
        nearest_other_hv_pin_absolute: tuple[float, float],
    ) -> float:
        """Apply U2 isolation-slot reduction to a base ghost-pad radius.

        The reduction for each isolation slot is the projection of the
        slot's vector onto the unit vector from ``current_pin_absolute``
        to ``nearest_other_hv_pin_absolute`` (the nearest HV pin on a
        different component).  Slots that are perpendicular to the
        creepage direction reclaim 0mm; slots aligned with the
        direction reclaim their full length.  The projection is
        clamped at 0 (a slot that points away from the other HV pin
        does not extend creepage) and the total reduction is clamped
        at ``base_radius`` (the FR4 SSOT).

        When :attr:`use_isolation_slots` is False, returns
        ``base_radius`` unchanged (NFR4 bit-identical parity with U1).
        When True but the component has no isolation slots, the
        reduction is also 0 (the slot list is the source of truth, not
        the toggle alone).
        """
        if not self.use_isolation_slots:
            return base_radius
        slots = self._isolation_slots_by_ref.get(component_ref, [])
        if not slots:
            return base_radius
        dx = nearest_other_hv_pin_absolute[0] - current_pin_absolute[0]
        dy = nearest_other_hv_pin_absolute[1] - current_pin_absolute[1]
        d_len = math.hypot(dx, dy)
        if d_len <= 0.0:
            return base_radius
        ux, uy = dx / d_len, dy / d_len

        reduction = 0.0
        for slot in slots:
            sx0, sy0 = slot.start_offset
            sx1, sy1 = slot.end_offset
            sdx = sx1 - sx0
            sdy = sy1 - sy0
            projection = sdx * ux + sdy * uy
            if projection > 0.0:
                reduction += projection
        return max(0.0, base_radius - reduction)

    def _reserve_slots_with_hv(
        self,
        component: Component,
        placed_pos: tuple[float, float],
        all_slots: list[tuple[float, float]],
        used_slots: set[tuple[float, float]],
        placements: dict[str, tuple[float, float]] | None = None,
        netlist: Netlist | None = None,
    ) -> None:
        """Reserve the footprint ring AND any HV-pin creepage ring for a placed component.

        Wraps ``_reserve_slots`` (footprint ring) and, when the placer
        has design_rules available, adds a creepage-radius reservation
        around every HV pin's ABSOLUTE position (placed + pin-relative
        offset).  This is the per-placement hook for the U1
        ghost-pad injection: doing it at placement time, with the
        actual placed coordinates, is the only physically correct
        semantic — pin-relative injection would reserve slots at the
        wrong absolute location.

        HV ring reservation respects U2 isolation-slot reductions
        (``_effective_ghost_pad_radius``) and never expands beyond
        the FR4 base radius.

        ``placements`` and ``netlist`` are the cumulative placement
        view and the full netlist, used to find the nearest HV pin on
        a different component for the U2 projection.  When either is
        missing, the placer falls back to the full base radius (no
        isolation-slot reduction) — this preserves the NFR4 parity
        for callers that don't thread the full context.
        """
        radius = self._get_footprint_radius(component)
        self._reserve_slots(placed_pos, radius, all_slots, used_slots)

        if self.design_rules is None or component.pins is None:
            return

        base_radius = 0.0
        for rules in getattr(self.design_rules, "net_classes", {}).values():
            safety = getattr(rules, "safety_category", None)
            if safety in self._HV_SAFETY_CATEGORIES:
                base_radius = max(base_radius, float(getattr(rules, "creepage_mm", 0.0)))
        if base_radius <= 0.0:
            return

        other_hv_pins: list[tuple[float, float]] = []
        if placements is not None and netlist is not None:
            net_class_assignments_other = (
                getattr(self.design_rules, "net_class_assignments", {}) or {}
            )
            net_classes_other = getattr(self.design_rules, "net_classes", {}) or {}
            for other_ref, other_pos in placements.items():
                if other_ref == component.ref:
                    continue
                other_comp = next((c for c in netlist.components if c.ref == other_ref), None)
                if other_comp is None or other_comp.pins is None:
                    continue
                ox, oy = other_pos
                for op in other_comp.pins:
                    if op.net is None:
                        continue
                    other_class = net_class_assignments_other.get(op.net)
                    if other_class is None or other_class not in net_classes_other:
                        continue
                    other_safety = getattr(net_classes_other[other_class], "safety_category", None)
                    if other_safety not in self._HV_SAFETY_CATEGORIES:
                        continue
                    opx, opy = op.position
                    other_hv_pins.append((ox + float(opx), oy + float(opy)))

        net_class_assignments = getattr(self.design_rules, "net_class_assignments", {}) or {}
        net_classes = getattr(self.design_rules, "net_classes", {}) or {}
        cx, cy = placed_pos
        for pin in component.pins:
            if pin.net is None:
                continue
            class_name = net_class_assignments.get(pin.net)
            if class_name is None or class_name not in net_classes:
                continue
            safety = getattr(net_classes[class_name], "safety_category", None)
            if safety not in self._HV_SAFETY_CATEGORIES:
                continue
            px, py = pin.position
            abs_x = cx + float(px)
            abs_y = cy + float(py)
            nearest_other = (0.0, 0.0)
            if other_hv_pins:
                nearest_other = min(
                    other_hv_pins,
                    key=lambda p: (p[0] - abs_x) ** 2 + (p[1] - abs_y) ** 2,
                )
            ring_radius = self._effective_ghost_pad_radius(
                component.ref,
                pin.name,
                base_radius,
                (abs_x, abs_y),
                nearest_other,
            )
            if ring_radius <= 0.0:
                continue
            self._reserve_slots((abs_x, abs_y), ring_radius, all_slots, used_slots)

    def _is_hv_ref(self, ref: str, comp_by_ref: dict[str, Component]) -> bool:
        """Return True if ``ref`` participates in any HV-class net.

        "HV" is determined by :meth:`PlacementConstraints.get_net_class`
        (which flags names containing "HV"/"BUS"/"DC_BUS" as
        HighVoltage) and, when available, by the
        ``NetClassRules.safety_category`` field for that class.
        """
        comp = comp_by_ref.get(ref)
        if comp is None or not hasattr(comp, "pins") or not comp.pins:
            return False
        constraints = self.constraints
        get_net_class = getattr(constraints, "get_net_class", None)
        if get_net_class is None:
            return False
        for pin in comp.pins:
            net = getattr(pin, "net", None)
            if not net:
                continue
            try:
                net_class = get_net_class(net)
            except Exception:
                continue
            if net_class == "HighVoltage":
                return True
            rule = constraints.net_class_rules.get(net_class)
            if rule is not None and getattr(rule, "safety_category", None) == "HV":
                return True
        return False
