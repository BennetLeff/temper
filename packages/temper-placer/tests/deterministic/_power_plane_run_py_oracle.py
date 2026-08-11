"""
D7 run-orchestration oracle for `deterministic/stages/power_plane.py`.

Verbatim pre-D7 snapshot of the module at the D7 dispatch base (origin/main
`3a7dd1d9`), with ONLY the documented relative-import rewrites below. The body
below `# --- BEGIN PINNED BODY ---` is byte-identical to the module except for
the three relative imports (`from ..state` / `from .base` / `from
.layer_assignment`) rewritten to their absolute forms so the oracle imports
from the test tree; the D7 Rust port (`temper-orchestration::PowerPlaneStage`)
is the differential subject, pinned by `test_deterministic_d7_rust_differential.py`.
The reassignment kernel (`recompute_plane_assignments`) stays single-source in
`temper_design_bundle_python.deterministic_leaves`; the `LayerAssignment`
pyclass re-export and the two module-level plane-net tables (data, not compute)
stay Python.
"""

from dataclasses import replace

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.stages.layer_assignment import LayerAssignment

# --- BEGIN PINNED BODY ---

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
        Process layer assignments and mark plane nets.

        If layer_assignments exist, updates them.
        If not, creates new assignments for plane nets.

        Args:
            state: Current board state

        Returns:
            Updated board state with plane nets marked
        """
        if not state.netlist:
            return state

        # Get existing assignments or create empty list
        existing_assignments = list(state.layer_assignments) if state.layer_assignments else []

        # Get all net names from netlist
        all_nets = [net.name for net in state.netlist.nets]

        # Process plane nets
        new_assignments = _tdb.deterministic_leaves.recompute_plane_assignments(
            existing_assignments, self.plane_nets, self.plane_layers, all_nets
        )

        return replace(state, layer_assignments=frozenset(new_assignments))
