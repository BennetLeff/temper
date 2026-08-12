"""
Per-stage DRC fence validator for PhasedComponentAssignmentStage.

The validator orchestration — the ``_creepage_mm`` / ``_absolute_hv_pins``
extraction, the fallback ``used_slots`` recompute and the legitimate-origin
set (through the D5 mixin helpers ``_get_footprint_radius`` /
``_effective_ghost_pad_radius``), the bucketed slot-index kernels (already
Rust in ``temper-design-bundle``) and the two failure scans (coverage in pin
order then slot order; over-claim in ``used_slots`` set order) — is
implemented in Rust (``temper-orchestration``'s ``run_phased_validator_hv``,
Phase D batch D4 of the Rust Orchestration Engine plan 2026-08-09-001). The
router_v6 ``StageDRCFailure`` construction stays Python: this shim wraps the
Rust kernel's ``(field, value, reason)`` triples into the failure objects.

``_infer_slot_spacing`` / ``_build_slot_index`` /
``_slots_within_radius`` stay as thin delegations to the already-Rust
design-bundle kernels; ``_flatten_slots`` delegates to
``temper_drc_rs.flatten_zone_slots_py`` (Wave 4 orchestration-port);
``_absolute_hv_pins`` / ``_creepage_mm`` stay Python
(public module API exercised by ``tests/property/test_ghost_pad_injection.py``;
the Rust kernel inlines the same computation, so the two cannot drift
separately from the differential).

The differential oracle for the pre-migration implementation is pinned
VERBATIM in ``tests/deterministic/_phased_component_assignment_validator_py_oracle.py``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb
import temper_drc_rs as _drc
import temper_orchestration as _to

if TYPE_CHECKING:
    from temper_placer.router_v6.stage_validators import StageDRCFailure

_HV_SAFETY_CATEGORIES = frozenset({"HV", "AC"})

# Default slot spacing used when the grid is degenerate (single slot
# or non-uniform).  Smaller values over-bucket (more memory, exact
# results), larger values under-bucket (less memory, still correct).
_DEFAULT_SLOT_SPACING = 5.0

_RS = _tdb.deterministic_leaves


def _flatten_slots(state) -> list[tuple[float, float]]:
    """All grid slots from every zone in state.zone_slots.

    The flatten (the pure compute) lives in the
    ``temper_drc_rs.flatten_zone_slots_py`` kernel (Wave 4 orchestration-port);
    this is the marshalling shim.
    """
    return _drc.flatten_zone_slots_py(state.zone_slots)


def _infer_slot_spacing(slots: list[tuple[float, float]]) -> float:
    """Infer the regular slot-grid spacing from a flat list of slots.

    The placer's zone_slots are emitted by ``_build_state`` on a
    regular grid, so the minimum non-zero coordinate difference is
    the spacing.  Falls back to ``_DEFAULT_SLOT_SPACING`` for
    degenerate inputs (0, 1, or 2 slots; non-uniform grids).
    """
    return _RS.infer_slot_spacing_py(slots)


def _build_slot_index(
    slots: Iterable[tuple[float, float]],
    spacing: float,
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """Build a 2D bucketed cell map ``(i, j) -> [slots in that cell]``.

    Cells are unit squares of side ``spacing`` aligned to the
    inferred grid origin (0, 0).  A slot ``(x, y)`` lives in cell
    ``(round(x/spacing), round(y/spacing))``.
    """
    return _RS.build_slot_index_py(slots, spacing)


def _slots_within_radius(
    center: tuple[float, float],
    radius: float,
    index: dict[tuple[int, int], list[tuple[float, float]]],
    spacing: float,
) -> list[tuple[float, float]]:
    """Yield all slots within ``radius`` of ``center`` using the cell index.

    Walks the (2k+1) x (2k+1) cell window where
    ``k = ceil(radius / spacing)``.  Each candidate slot is
    distance-checked exactly once (de-duplicated via a per-call
    seen-set) so the result is O(k^2 + matched) where matched is
    the number of slots actually within the radius.
    """
    return _RS.slots_within_radius_py(center, radius, index, spacing)


def _absolute_hv_pins(state) -> list[tuple[float, float, str, str]]:
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
    pins: list[tuple[float, float, str, str]] = []
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
            pins.append((cx + float(px), cy + float(py), comp.ref, pin.name))
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
            max_creepage = max(max_creepage, float(getattr(rules_entry, "creepage_mm", 0.0)))
    return max_creepage


def validate_phased_component_assignment_hv(state) -> list["StageDRCFailure"]:
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

    The coverage / over-claim compute runs in the Rust kernel
    (``run_phased_validator_hv``); the router_v6 ``StageDRCFailure``
    construction stays here.
    """
    from temper_placer.router_v6.stage_validators import StageDRCFailure

    return [
        StageDRCFailure(field=field, value=value, reason=reason, stage="PhasedComponentAssignment")
        for (field, value, reason) in _to.run_phased_validator_hv(state)
    ]
