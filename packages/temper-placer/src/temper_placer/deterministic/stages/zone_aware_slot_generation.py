"""
Zone-aware slot generation for the DeterministicPipeline.

Extends SlotGenerationStage to avoid placing components in areas
covered by copper zones (GND/VCC fill), which would block routing channels.

Also avoids placing components in axis-aligned isolation-slot cutouts and
emits a per-(component, lv_pin, hv_pin) clearance reclaim dict that the
DRC oracle consumes (plan 2026-06-23-007, U2 / R2).

Wave 4, **Phase 5, final leaves**: the pure geometry kernels (``_point_in_polygon``
ray casting, ``_slot_intersects_iso`` AABB, and the
``RoutingChannelAwareSlotStage`` ``_point_to_segment_distance`` /
``_min_distance_to_polygon``) are implemented in Rust in the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_phase``).

Phase D batch D5 of the Rust Orchestration Engine plan (2026-08-09-001): the
**stage orchestration** is implemented in Rust (``temper-orchestration``'s
``ZoneAwareSlotGenerationStage``): the ``_isolation_filter`` + K4 reclaim
formula, ``_get_copper_zones`` (YAML + board.copper_zones + the board.zones
net-class scan over ``POWER_NET_NAMES``), the per-zone slot walk with the
copper-zone and isolation-cutout filters, the F.Cu / statistics log lines
and the ``zone_slots`` / ``reclaim_by_pin_pair`` writes all run Rust-side,
crossing the FFI once per stage call. This module keeps the public API (the
``ZoneAwareSlotGenerationStage`` / ``RoutingChannelAwareSlotStage`` Stage
subclasses, their constructors and ``name``, the ``POWER_NET_NAMES``
classification set and the Phase-5 leaf-kernel delegation helpers) and
delegates ``run`` across the FFI. The differential oracle for the
pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_zone_aware_slot_generation_run_py_oracle.py``.

Bit-exactness: the Rust kernels replicate the oracle's ray-casting half-open
edge semantics, the inclusive AABB test, and the ``** 0.5`` (libm ``pow``,
NOT ``sqrt``) segment-distance close. Verified by
``tests/deterministic/stages/test_zone_aware_slot_generation_rust_differential.py``
(the Phase-5 geometry leaves) and
``tests/deterministic/test_deterministic_d5_rust_differential.py`` (the D5
stage orchestration); the structural proofs live in
``packages/temper-design-bundle/VERIFICATION.md`` and
``packages/temper-orchestration/VERIFICATION.md``.
"""

import logging

import temper_design_bundle_python as _tdb
import temper_geometry as _tg
import temper_orchestration as _to

from ..state import BoardState
from .slot_generation import SlotGenerationStage

logger = logging.getLogger(__name__)

# @req(2026-06-23-007, R2/K4): K4 reclaim formula constants. The Rust stage
# (zone_aware_slot_generation_stage.rs) mirrors these; the differential pins
# them bit-exactly.
# perpendicular_clearance_budget is the minimum straight-line distance the
# creepage path needs outside the slot; original_requirement is the HV
# clearance without isolation-slot credit. Both are overridden by net_class_rules
# when present.
_K4_PERPENDICULAR_CLEARANCE_BUDGET_MM = 5.5
_K4_ORIGINAL_REQUIREMENT_MM = 6.0  # allow-safety-constant: K4 HV clearance baseline
# @req(2026-06-23-007, R2/K4): TO-247 pin-1 to pin-2 distance the K4
# derivation historically assumed. Used only as a fallback when the
# component's lv/hv pin positions cannot be resolved from the netlist
# (e.g. fixtures that build slots in isolation). For real components the
# per-slot pitch is computed from the placed component's pin offsets, so
# non-TO-247 packages get correct K4 reclaim values automatically.
_K4_TO247_PIN_PITCH_DEFAULT_MM = 5.45

# Common power net names that indicate copper fill zones (SSOT for the
# copper-zone net-class classification; the Rust stage reads it through FFI).
POWER_NET_NAMES = {
    "GND",
    "PGND",
    "AGND",
    "DGND",
    "CGND",
    "SGND",
    "VCC",
    "VDD",
    "VSS",
    "VBUS",
    "VIN",
    "VOUT",
    "+3V3",
    "+3.3V",
    "3V3",
    "3.3V",
    "+5V",
    "5V",
    "+12V",
    "12V",
    "+15V",
    "15V",
    "+24V",
    "24V",
    "V+",
    "V-",
}


def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """
    Check if point (x, y) is inside polygon using ray casting algorithm.

    Args:
        x, y: Point coordinates
        polygon: List of (x, y) vertices

    Returns:
        True if point is inside polygon

    Wave 4, Phase 5, final leaves: the ray-casting body is the migrated Rust
    kernel ``temper_design_bundle_python.deterministic_phase.point_in_polygon_py``.
    """
    return _tdb.deterministic_phase.point_in_polygon_py(x, y, polygon)


class ZoneAwareSlotGenerationStage(SlotGenerationStage):
    """
    Slot generation that avoids copper zone coverage.

    Slots are not generated within copper fill zones (GND/VCC planes)
    to preserve routing channels and avoid congestion.

    Attributes:
        slot_spacing_mm: Spacing between slots in mm
        copper_zone_margin: Additional margin around copper zones (mm)
        min_routing_channel: Minimum gap required for routing (mm)
    """

    def __init__(
        self,
        slot_spacing_mm: float = 5.0,
        copper_zone_margin: float = 2.0,
        min_routing_channel: float = 3.0,
        yaml_copper_zones: list | None = None,
        yaml_isolation_slots: list | None = None,  # @req(2026-06-23-007, R1)
        net_class_rules: dict | None = None,  # @req(2026-06-23-007, R2)
    ):
        super().__init__(slot_spacing_mm=slot_spacing_mm)
        self.copper_zone_margin = copper_zone_margin
        self.min_routing_channel = min_routing_channel
        self.yaml_copper_zones = yaml_copper_zones or []
        # @req(2026-06-23-007, R1): Stash isolation slots on the stage so U2 can
        # filter candidate slots against the cutout footprints and emit the
        # per-(component, pin-pair) reclaim dict that U3 consumes.
        self.yaml_isolation_slots = list(yaml_isolation_slots) if yaml_isolation_slots else []
        # @req(2026-06-23-007, R2): Per-net-class clearance rules so the K4
        # reclaim formula can read HV override values from config when present.
        self.net_class_rules = dict(net_class_rules) if net_class_rules else {}

    @property
    def name(self) -> str:
        return "zone_aware_slot_generation"

    def run(self, state: BoardState) -> BoardState:
        """Generate slots, filtering out those covered by copper zones or
        isolation cutouts.

        The full run orchestration (the isolation filter + K4 reclaim, the
        copper-zone collection, the per-zone slot walk with the copper and
        isolation-cutout filters, the log lines and the ``zone_slots`` /
        ``reclaim_by_pin_pair`` writes) is implemented in Rust (Phase D D5);
        this method crosses the FFI once per stage call.
        """
        return _to.run_zone_aware_slot_generation(
            state,
            self.slot_spacing_mm,
            self.copper_zone_margin,
            self.min_routing_channel,
            self.yaml_copper_zones,
            self.yaml_isolation_slots,
            self.net_class_rules,
        )

    @staticmethod
    def _slot_intersects_iso(
        slot: tuple[float, float],
        iso_aabbs: list[tuple[tuple[float, float], tuple[float, float]]],
    ) -> bool:
        """AABB-vs-AABB test: a slot is blocked by a cutout that overlaps its footprint."""
        return _tdb.deterministic_phase.slot_intersects_iso_py(slot, iso_aabbs)

    def _is_slot_in_copper_zone(
        self,
        slot: tuple[float, float],
        copper_zones: list,
        placement_layer: str = "F.Cu",
    ) -> bool:
        """
        Check if a slot position falls within any copper zone on the placement layer.

        Args:
            slot: (x, y) position
            copper_zones: List of copper zone objects
            placement_layer: The layer where components are placed (default: "F.Cu")

        Returns:
            True if slot is covered by a copper zone on the same layer

        Kept as a public helper; the D5 Rust stage run() drives the identical
        predicate through FFI.
        """
        x, y = slot

        for zone in copper_zones:
            # Skip zones that are not on the placement layer
            # Copper zones on internal/bottom layers don't block top-layer placement
            if hasattr(zone, "layers") and zone.layers:
                zone_layers = zone.layers
                # Handle both list and string formats
                if isinstance(zone_layers, str):
                    zone_layers = [zone_layers]
                # Skip if placement layer is not in zone's layers
                if placement_layer not in zone_layers:
                    continue

            # Check polygon containment
            if hasattr(zone, "polygon") and zone.polygon:
                if _point_in_polygon(x, y, zone.polygon):
                    return True

            # Check bounding box containment (fallback)
            elif hasattr(zone, "bounds") and zone.bounds:
                bounds = zone.bounds
                if len(bounds) == 4:
                    # (x_min, y_min, x_max, y_max) format
                    x_min, y_min, x_max, y_max = bounds
                elif len(bounds) == 2:
                    # ((x_min, y_min), (x_max, y_max)) format
                    (x_min, y_min), (x_max, y_max) = bounds
                else:
                    continue

                # Add margin
                x_min -= self.copper_zone_margin
                y_min -= self.copper_zone_margin
                x_max += self.copper_zone_margin
                y_max += self.copper_zone_margin

                if x_min <= x <= x_max and y_min <= y <= y_max:
                    return True

        return False


class RoutingChannelAwareSlotStage(ZoneAwareSlotGenerationStage):
    """
    Extended slot generation that also ensures routing channels remain open.

    In addition to avoiding copper zones, this stage ensures that slots
    are not placed in critical routing corridors between components.
    """

    def __init__(
        self,
        slot_spacing_mm: float = 5.0,
        copper_zone_margin: float = 2.0,
        min_routing_channel: float = 3.0,
        channel_density_threshold: float = 0.6,
    ):
        super().__init__(
            slot_spacing_mm=slot_spacing_mm,
            copper_zone_margin=copper_zone_margin,
            min_routing_channel=min_routing_channel,
        )
        self.channel_density_threshold = channel_density_threshold

    @property
    def name(self) -> str:
        return "routing_channel_aware_slot_generation"

    def _compute_slot_routing_cost(
        self,
        slot: tuple[float, float],
        copper_zones: list,
        board_width: float,
        board_height: float,
    ) -> float:
        """
        Compute routing cost for a slot position.

        Higher cost = less desirable for placement due to routing impact.

        Factors:
        - Distance to copper zone boundaries (closer = more congested)
        - Distance to board edges (too close = no routing room)
        - Density of nearby slots (clustering = congestion)

        Args:
            slot: (x, y) position
            copper_zones: List of copper zones
            board_width, board_height: Board dimensions

        Returns:
            Cost value (0 = ideal, 1 = avoid)
        """
        x, y = slot
        cost = 0.0

        # Penalize positions near board edges
        edge_margin = self.min_routing_channel
        if x < edge_margin or x > board_width - edge_margin:
            cost += 0.3
        if y < edge_margin or y > board_height - edge_margin:
            cost += 0.3

        # Penalize positions near copper zone boundaries
        for zone in copper_zones:
            if hasattr(zone, "polygon") and zone.polygon:
                # Find minimum distance to zone boundary
                min_dist = self._min_distance_to_polygon(x, y, zone.polygon)
                if min_dist < self.min_routing_channel:
                    # Closer to boundary = higher cost
                    cost += 0.4 * (1 - min_dist / self.min_routing_channel)

        return min(1.0, cost)

    def _min_distance_to_polygon(
        self,
        x: float,
        y: float,
        polygon: list[tuple[float, float]],
    ) -> float:
        """Compute minimum distance from point to polygon boundary."""
        return _tdb.deterministic_phase.min_distance_to_polygon_py(x, y, polygon)

    def _point_to_segment_distance(
        self,
        px: float,
        py: float,
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> float:
        """Compute distance from point (px, py) to line segment p1-p2.

        Issue #987: delegates to temper-geometry's canonical kernel (the
        deterministic_phase binding this used to call was deleted in the
        dedupe).
        """
        return _tg.point_to_segment_distance_py(px, py, *p1, *p2)
