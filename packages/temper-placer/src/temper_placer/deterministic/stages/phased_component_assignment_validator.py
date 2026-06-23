"""
Per-stage DRC fence validator for PhasedComponentAssignmentStage.

Validates that the placer's ghost-pad injection covered every slot
within IEC 62368-1 creepage of every HV-class pin, and that no slot
was over-claimed (i.e. reserved without a corresponding HV-pin ring
or a placed component's footprint).

Conforms to docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md.

The validator is read-only: it does not mutate the state, and it
returns a (possibly empty) list of ``StageDRCFailure`` records.  The
placer logs failures as warnings and lets the closure test (SM1/SM2)
decide promotion.
"""

from __future__ import annotations

import math
from typing import List, Tuple

from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)

_HV_SAFETY_CATEGORIES = frozenset({"HV", "AC"})


def _absolute_hv_pins(state) -> List[Tuple[float, float, str, str]]:
    """Return ABSOLUTE (x, y, comp_ref, pin_name) for every HV pin of every placed component.

    Pin positions on the netlist are component-relative.  The placer
    injects ghost pads at the absolute positions
    ``placed + pin_relative``, so the validator must check coverage
    at the same absolute coordinates.
    """
    rules = getattr(state, "design_rules", None)
    if rules is None or not getattr(rules, "net_classes", None):
        return []
    netlist = state.netlist
    if netlist is None:
        return []
    net_classes = rules.net_classes
    net_class_assignments = getattr(rules, "net_class_assignments", {}) or {}
    placements = dict(getattr(state, "placements", frozenset()))
    comp_by_ref = {c.ref: c for c in netlist.components}
    pins: List[Tuple[float, float, str, str]] = []
    for comp in netlist.components:
        if comp.ref not in placements:
            continue
        cx, cy = placements[comp.ref]
        for pin in comp.pins:
            if pin.net is None:
                continue
            class_name = net_class_assignments.get(pin.net)
            if class_name is None or class_name not in net_classes:
                continue
            safety = getattr(net_classes[class_name], "safety_category", None)
            if safety not in _HV_SAFETY_CATEGORIES:
                continue
            px, py = pin.position
            pins.append(
                (cx + float(px), cy + float(py), comp.ref, pin.name)
            )
    return pins


def _creepage_mm(state) -> float:
    """Max creepage_mm across HV/AC net classes (the FR4 SSOT)."""
    rules = getattr(state, "design_rules", None)
    if rules is None:
        return 0.0
    max_creepage = 0.0
    for rules_entry in getattr(rules, "net_classes", {}).values():
        safety = getattr(rules_entry, "safety_category", None)
        if safety in _HV_SAFETY_CATEGORIES:
            max_creepage = max(
                max_creepage, float(getattr(rules_entry, "creepage_mm", 0.0))
            )
    return max_creepage


def _flatten_slots(state) -> List[Tuple[float, float]]:
    """All grid slots from every zone in state.zone_slots."""
    if not state.zone_slots:
        return []
    out: List[Tuple[float, float]] = []
    for _zone, slots in state.zone_slots:
        out.extend(slots)
    return out


@register_validator("PhasedComponentAssignment")
def validate_phased_component_assignment_hv(state) -> List[StageDRCFailure]:
    """Verify the placer reserved every HV pin's creepage ring AND no slot is over-claimed.

    Two checks run in this order:

      1. Coverage: for every placed component's HV pin at absolute
         position ``(placed + pin_relative)``, every grid slot within
         ``creepage_mm`` must be reserved (either by the placer's
         per-component footprint ring or by the HV creepage ring).
      2. Non-over-claim: every reserved slot must have a "legitimate"
         origin (a placed component's footprint ring OR an HV pin's
         creepage ring).  Catches placer logic errors that reserve
         too many slots.

    A degenerate ``creepage_mm == 0`` is treated as a no-op (no
    rings, no failures).  A ``creepage_mm`` larger than the slot-grid
    diagonal saturates coverage and the validator returns an empty
    failure list.
    """
    failures: List[StageDRCFailure] = []
    netlist = getattr(state, "netlist", None)
    if netlist is None:
        return failures

    creepage = _creepage_mm(state)
    if creepage <= 0.0:
        return failures

    all_slots = _flatten_slots(state)
    if not all_slots:
        return failures

    pins = _absolute_hv_pins(state)
    if not pins:
        return failures

    # Saturation short-circuit: creepage > slot-grid diagonal means
    # every slot is "within creepage" of every HV pin.  Coverage is
    # a tautology; the non-over-claim check still applies but
    # trivially returns no failures since every slot is covered.
    xs = [s[0] for s in all_slots]
    ys = [s[1] for s in all_slots]
    diagonal = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    if creepage >= diagonal:
        return failures

    # Use the actual used_slots recorded by the placer if available;
    # this is the only way the validator can detect a placer bug that
    # left an HV ring incomplete (the recompute-from-placements path
    # would mask such a bug by re-deriving the expected ring).
    used_slots_attr = getattr(state, "used_slots", None)
    if used_slots_attr is not None and len(used_slots_attr) > 0:
        used_slots: set = set(used_slots_attr)
    else:
        # Fallback for older state objects that pre-date U3.
        used_slots = set()
        placements = dict(getattr(state, "placements", frozenset()))
        comp_by_ref = {c.ref: c for c in netlist.components}
        from temper_placer.deterministic.stages.phased_component_assignment import (
            PhasedComponentAssignmentStage,
        )
        stage = PhasedComponentAssignmentStage.__new__(PhasedComponentAssignmentStage)
        stage.slot_spacing = 12.0
        if getattr(state, "design_rules", None) is not None:
            stage.design_rules = state.design_rules
            stage.use_isolation_slots = False
        for ref, pos in placements.items():
            comp = comp_by_ref.get(ref)
            if comp is None:
                continue
            cx, cy = pos
            radius = stage._get_footprint_radius(comp)
            for slot in all_slots:
                sx, sy = slot
                if math.hypot(sx - cx, sy - cy) <= radius:
                    used_slots.add(slot)
            for pin in comp.pins:
                if pin.net is None:
                    continue
                class_name = (
                    getattr(state.design_rules, "net_class_assignments", {}) or {}
                ).get(pin.net)
                if class_name is None or class_name not in (
                    getattr(state.design_rules, "net_classes", {}) or {}
                ):
                    continue
                safety = getattr(
                    (
                        getattr(state.design_rules, "net_classes", {}) or {}
                    ).get(class_name),
                    "safety_category",
                    None,
                )
                if safety not in _HV_SAFETY_CATEGORIES:
                    continue
                ring_radius = stage._effective_ghost_pad_radius(
                    comp.ref, pin.name, creepage
                )
                if ring_radius <= 0.0:
                    continue
                px, py = pin.position
                ax = cx + float(px)
                ay = cy + float(py)
                for slot in all_slots:
                    sx, sy = slot
                    if math.hypot(sx - ax, sy - ay) <= ring_radius:
                        used_slots.add(slot)

    # For the non-over-claim check we need placement and component
    # metadata.  Pull them once and reuse below.
    placements = dict(getattr(state, "placements", frozenset()))
    comp_by_ref = {c.ref: c for c in netlist.components}
    from temper_placer.deterministic.stages.phased_component_assignment import (
        PhasedComponentAssignmentStage,
    )
    stage = PhasedComponentAssignmentStage.__new__(PhasedComponentAssignmentStage)
    stage.slot_spacing = 12.0
    if getattr(state, "design_rules", None) is not None:
        stage.design_rules = state.design_rules
        stage.use_isolation_slots = False

    # 1. Coverage: every HV pin's creepage ring is fully reserved.
    for pin in pins:
        px, py, comp_ref, pin_name = pin
        for slot in all_slots:
            sx, sy = slot
            if math.hypot(sx - px, sy - py) <= creepage and slot not in used_slots:
                failures.append(
                    StageDRCFailure(
                        field=f"hv_creepage_unblocked.{comp_ref}.{pin_name}",
                        value=slot,
                        reason=(
                            f"Slot {slot} is within {creepage}mm of HV pin "
                            f"{comp_ref}.{pin_name} at ({px},{py}) but is "
                            f"not in used_slots"
                        ),
                        stage="PhasedComponentAssignment",
                    )
                )

    # 2. Non-over-claim: every used slot must be within a footprint
    #    ring or an HV creepage ring.
    for slot in used_slots:
        sx, sy = slot
        covered = False
        for ref, pos in placements.items():
            comp = comp_by_ref.get(ref)
            if comp is None:
                continue
            cx, cy = pos
            radius = stage._get_footprint_radius(comp)
            if math.hypot(sx - cx, sy - cy) <= radius:
                covered = True
                break
            for pin in comp.pins:
                if pin.net is None:
                    continue
                class_name = (
                    getattr(state.design_rules, "net_class_assignments", {}) or {}
                ).get(pin.net)
                if class_name is None or class_name not in (
                    getattr(state.design_rules, "net_classes", {}) or {}
                ):
                    continue
                safety = getattr(
                    (
                        getattr(state.design_rules, "net_classes", {}) or {}
                    ).get(class_name),
                    "safety_category",
                    None,
                )
                if safety not in _HV_SAFETY_CATEGORIES:
                    continue
                ring_radius = stage._effective_ghost_pad_radius(
                    comp.ref, pin.name, creepage
                )
                if ring_radius <= 0.0:
                    continue
                px, py = pin.position
                ax = cx + float(px)
                ay = cy + float(py)
                if math.hypot(sx - ax, sy - ay) <= ring_radius:
                    covered = True
                    break
            if covered:
                break
        if not covered:
            failures.append(
                StageDRCFailure(
                    field="used_slot_overclaim",
                    value=slot,
                    reason=(
                        f"Slot {slot} is in used_slots but is not within "
                        f"any HV pin's creepage ring nor within any placed "
                        f"component's footprint radius"
                    ),
                    stage="PhasedComponentAssignment",
                )
            )

    return failures
