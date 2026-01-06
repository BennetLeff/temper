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
"""

from dataclasses import replace
from typing import FrozenSet, Dict, Optional
from ..state import BoardState
from .base import Stage
from .layer_assignment import LayerAssignment


# Temper board plane nets
TEMPER_PLANE_NETS: FrozenSet[str] = frozenset(
    {
        # Ground nets -> In1.Cu plane
        "GND",
        "PGND",
        "CGND",
        # Power rails -> In2.Cu islands
        "+15V",
        "+5V",
        "+3V3",
        "VCC_BOOT",
        # High current -> F.Cu pours (still plane-connected, not trace-routed)
        "DC_BUS+",
        "DC_BUS-",
        "SW_NODE",
    }
)

# Layer assignments for plane nets
# Layer 0 = F.Cu, Layer 1 = In1.Cu, Layer 2 = In2.Cu, Layer 3 = B.Cu
TEMPER_PLANE_LAYERS: Dict[str, int] = {
    # Ground to In1.Cu (inner ground plane)
    "GND": 1,
    "PGND": 1,
    "CGND": 1,
    # Power to In2.Cu (inner power islands)
    "+15V": 2,
    "+5V": 2,
    "+3V3": 2,
    "VCC_BOOT": 2,
    # HV nets stay on F.Cu for copper pours (but still plane-connected)
    "DC_BUS+": 0,
    "DC_BUS-": 0,
    "SW_NODE": 0,
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
        plane_nets: Optional[FrozenSet[str]] = None,
        plane_layers: Optional[Dict[str, int]] = None,
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

        # Build lookup for existing assignments
        assignment_by_net = {a.net_name: a for a in existing_assignments}

        # Get all net names from netlist
        all_nets = {net.name for net in state.netlist.nets}

        # Process plane nets
        new_assignments = []
        for net_name, assignment in assignment_by_net.items():
            if net_name in self.plane_nets:
                # Update to plane connection
                layer = self.plane_layers.get(net_name, 1)  # Default to In1.Cu
                new_assignments.append(
                    LayerAssignment(
                        net_name=net_name,
                        layer=layer,
                        allow_layer_change=assignment.allow_layer_change,
                        is_plane=True,
                    )
                )
            else:
                # Keep existing assignment
                new_assignments.append(assignment)

        # Add assignments for plane nets not in existing assignments
        assigned_nets = {a.net_name for a in new_assignments}
        for net_name in self.plane_nets:
            if net_name not in assigned_nets and net_name in all_nets:
                layer = self.plane_layers.get(net_name, 1)
                new_assignments.append(
                    LayerAssignment(
                        net_name=net_name,
                        layer=layer,
                        allow_layer_change=True,
                        is_plane=True,
                    )
                )

        # Add non-plane nets that weren't in existing assignments
        for net in state.netlist.nets:
            if net.name not in {a.net_name for a in new_assignments}:
                new_assignments.append(
                    LayerAssignment(
                        net_name=net.name,
                        layer=0,  # Default to F.Cu
                        allow_layer_change=True,
                        is_plane=False,
                    )
                )

        return replace(state, layer_assignments=tuple(new_assignments))
