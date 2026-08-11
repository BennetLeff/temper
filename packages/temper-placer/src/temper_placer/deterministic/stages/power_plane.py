"""
Power Plane Stage for deterministic routing pipeline.

This stage identifies power and ground nets and marks them for plane connection
instead of trace routing. Power nets connect through vias to copper pours on
inner layers rather than being trace-routed.

Temper Board Layer Strategy:
- F.Cu (Top): Components + Horizontal signals + HV copper pours
- In1.Cu: Ground plane (GND, PGND, CGND)
- In2.Cu: Power islands (+5V, +3V3, +15V, VCC_BOOT)
- B.Cu (Bottom): Vertical signals + escape vias

Phase D batch D7 of the Rust Orchestration Engine plan (2026-08-09-001): the
**run orchestration** (the ``state.netlist`` guard, the existing-assignment
``list(...)`` conversion, the netlist net-name collection and the
``frozenset`` write) is implemented in Rust (``temper-orchestration``'s
``PowerPlaneStage`` / ``run_power_plane``), crossing the FFI once per stage
call. The pure reassignment kernel stays single-source in
``temper_design_bundle_python`` (``recompute_plane_assignments``); the two
module-level plane-net tables (data, not compute) and the ``LayerAssignment``
pyclass re-export stay Python. The pre-migration implementation is pinned
VERBATIM in ``tests/deterministic/_power_plane_run_py_oracle.py``.
"""

import temper_orchestration as _to

from ..state import BoardState
from .base import Stage

# Temper board plane nets
# NOTE: Only include nets that should use plane connectivity (vias to copper pours).
# Nets routed as traces (PowerTrace class) should NOT be in this list.
# See: TemperPowerTopology in core/power_topology.py for power distribution strategy.
TEMPER_PLANE_NETS: frozenset[str] = frozenset(
    {
        # Ground nets -> In1.Cu plane
        "GND",
        "PGND",
        "CGND",
        # High-current power rail -> In2.Cu island
        "+15V",  # 5A, requires plane (PowerDeliveryStrategy.PLANE)
        # EXP-8: Add +3V3 and +5V for via stitching to power planes
        "+3V3",  # Via stitching to In2.Cu power island
        "+5V",  # Via stitching to In2.Cu power island
        # High current -> F.Cu pours (still plane-connected, not trace-routed)
        "DC_BUS+",
        "DC_BUS-",
        "SW_NODE",
        "AC_L",
        "AC_N",
        "PE",
    }
)

# Layer assignments for plane nets
# Layer 0 = F.Cu, Layer 1 = In1.Cu, Layer 2 = In2.Cu, Layer 3 = B.Cu
# Only include nets that are in TEMPER_PLANE_NETS above.
TEMPER_PLANE_LAYERS: dict[str, int] = {
    # Ground to In1.Cu (inner ground plane)
    "GND": 1,
    "PGND": 1,
    "CGND": 1,
    # High-current power rail to In2.Cu (inner power island)
    "+15V": 2,
    # EXP-8: +3V3 and +5V via stitching to power planes
    "+3V3": 2,  # Via stitch to In2.Cu power island
    "+5V": 2,  # Via stitch to In2.Cu power island
    # HV nets stay on F.Cu (layer 0) for copper pours
    "DC_BUS+": 0,
    "DC_BUS-": 0,
    "SW_NODE": 0,
    "AC_L": 0,
    "AC_N": 0,
    "PE": 0,
}


class PowerPlaneStage(Stage):
    """
    Mark power/ground nets for plane connection instead of trace routing.

    This stage modifies layer assignments to set is_plane=True for nets that
    should connect through copper pours rather than individual traces.

    Benefits:
    - Reduces A* routing attempts for nets that will fail anyway
    - Ensures power integrity through low-impedance planes
    - Proper thermal dissipation for high-current nets
    """

    def __init__(
        self,
        plane_nets: frozenset[str] | None = None,
        plane_layers: dict[str, int] | None = None,
    ):
        """
        Initialize PowerPlaneStage.

        Args:
            plane_nets: Set of net names that should be plane-connected.
                       Defaults to TEMPER_PLANE_NETS.
            plane_layers: Mapping of net name to layer index.
                         Defaults to TEMPER_PLANE_LAYERS.
        """
        self.plane_nets = plane_nets if plane_nets is not None else TEMPER_PLANE_NETS
        self.plane_layers = plane_layers if plane_layers is not None else TEMPER_PLANE_LAYERS

    @property
    def name(self) -> str:
        return "power_plane"

    def run(self, state: BoardState) -> BoardState:
        """
        Run the power-plane orchestration in Rust (Phase D D7); crosses the
        FFI once per stage call.

        If layer_assignments exist, updates them.
        If not, creates new assignments for plane nets.

        Args:
            state: Current board state

        Returns:
            Updated board state with plane nets marked
        """
        return _to.run_power_plane(state, self)
