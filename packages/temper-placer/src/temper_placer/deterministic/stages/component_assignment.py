"""Component assignment with multi-slot reservation for large footprints.

The stage orchestration is implemented in Rust (``temper-orchestration``'s
``ComponentAssignmentStage``, Phase D batch D4 of the Rust Orchestration
Engine plan 2026-08-09-001): the state guards, the ``_domain_lookups``
extraction, the GEOS domain filter PRECOMPUTED into the per-ref ``domain_ok``
set, the sheetpath-first/ref-fallback fixed-placement resolution, the greedy
kernel call (``temper_design_bundle_python.deterministic_leaves.
assign_components_to_slots`` — the Wave-4 Phase-5 leaf migration) and the
``frozenset(placements.items())`` write all run Rust-side, crossing the FFI
once per stage call. The shapely/GEOS domain filter itself stays Python —
the Rust stage drives the ``region.covers(Point(x, y))`` predicate through
the shapely objects at runtime, exactly like the oracle.

This module keeps the public API (the ``ComponentAssignmentStage`` Stage
subclass, its constructor and ``name``, and the ``_assign_components_to_slots``
leaf helper the existing kernel differential drives) and delegates ``run``
and the leaf helper across the FFI. The differential oracle for the
pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_component_assignment_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage


class ComponentAssignmentStage(Stage):
    """Assign components to slots with multi-slot reservation for large footprints."""

    def __init__(self, slot_spacing: float = 12.0, fixed_placements: dict[str, dict] | None = None):
        """Initialize with slot spacing and optional fixed placements.

        Args:
            slot_spacing: Spacing between slots in mm
            fixed_placements: Dict of ref -> {'position': [x, y], 'rotation': deg}
        """
        self.slot_spacing = slot_spacing
        self.fixed_placements = fixed_placements or {}

    @property
    def name(self) -> str:
        return "component_assignment"

    def run(self, state: BoardState) -> BoardState:
        return _to.run_component_assignment(state, self.slot_spacing, self.fixed_placements)

    def _assign_components_to_slots(
        self,
        netlist,
        component_zone_map: dict[str, str],
        zone_slots: dict[str, tuple],
        domain_for_ref=None,
        domain_regions=None,
    ) -> dict[str, tuple[float, float]]:
        """Assign components to slots using greedy wirelength minimization.

        The greedy kernel (fixed placements → largest-first → per-zone
        availability → cross-zone fallback → wirelength scoring → footprint
        reservation) runs in Rust; the GEOS domain filter is precomputed into
        the per-ref ``domain_ok`` predicate. All of it is Rust-side now
        (Phase D D4); this method is kept as a thin FFI delegation for
        public-API parity.
        """
        return _to.run_component_assignment_kernel(
            netlist,
            component_zone_map,
            zone_slots,
            self.fixed_placements,
            domain_for_ref,
            domain_regions,
            self.slot_spacing,
        )
