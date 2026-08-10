"""HV creepage and isolation-slot reduction for phased component assignment.

Contains the :class:`_PhaseHVMixin` with ghost-pad injection (U1),
isolation-slot reduction (U2), and HV-pin position collection.

Wave 4, **Phase 5, final leaves**: the U2 isolation-slot reduction kernel
(``_effective_ghost_pad_radius``) is implemented in Rust in the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_phase``).

Phase D batch D5 of the Rust Orchestration Engine plan (2026-08-09-001): the
per-placement HV reservation orchestration (``_reserve_slots_with_hv`` -- the
footprint ring, the HV/AC base-radius scan, the nearest-other-HV-pin
resolution and the per-pin ghost-pad ring) is implemented in Rust
(``temper-orchestration``'s ``PhasedAssignmentStage``) and runs inside the
migrated ``run()``; it calls ``_get_footprint_radius`` and
``_effective_ghost_pad_radius`` back on the stage (single-source). This
module keeps the public API unchanged: ``_collect_hv_pin_positions``,
``_effective_ghost_pad_radius`` (design-bundle kernel) and ``_is_hv_ref``.

Bit-exactness: the Rust kernel replicates the oracle's ``math.hypot`` (Dekker
vector_norm, NOT libm hypot), the ``d_len <= 0.0`` early-out, the strict
``projection > 0.0`` accumulation and the ``max(0.0, ...)`` clamp. Verified by
``tests/deterministic/stages/test_phase_rotation_rust_differential.py``
(oracle: ``tests/deterministic/stages/_phase_rotation_py_oracle.py``); the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

if TYPE_CHECKING:
    from temper_placer.core.component import Component
    from temper_placer.core.netlist import Netlist


class _PhaseHVMixin:
    """HV creepage / ghost-pad injection and isolation-slot reduction.

    Provides _collect_hv_pin_positions, _effective_ghost_pad_radius,
    and _is_hv_ref.
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
        flat_slots = []
        for slot in slots:
            sx0, sy0 = slot.start_offset
            sx1, sy1 = slot.end_offset
            flat_slots.append((sx0, sy0, sx1, sy1))
        return _tdb.deterministic_phase.effective_ghost_pad_radius_py(
            base_radius,
            current_pin_absolute,
            nearest_other_hv_pin_absolute,
            flat_slots,
        )

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
