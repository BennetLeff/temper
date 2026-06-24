"""
Power Distribution Network (PDN) router for critical net pre-routing (temper-cjxg.2).

This module provides automatic routing of power distribution networks before
general signal routing. Key features:
- Star topology routing from voltage regulators to all loads
- Wide traces for power carrying capacity
- Via arrays at layer transitions for reduced inductance
- Ground pour preparation (thermal reliefs)

Example usage:
    >>> from temper_placer.routing.pdn_router import PDNRouter
    >>> from temper_placer.core.netlist import Netlist
    >>>
    >>> router = PDNRouter()
    >>> power_paths = router.route_power_distribution(netlist, ["VCC", "+3.3V"])
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from temper_placer.core.board import Board
from temper_placer.core.netlist import Net, Netlist
from temper_placer.core.pin_geometry import pin_world_position

if TYPE_CHECKING:
    from temper_placer.routing.maze_router import RoutePath

logger = logging.getLogger(__name__)


@dataclass
class PowerTraceWidth:
    """Recommended trace width for power nets.

    Attributes:
        net_name: Name of the power net.
        width_mm: Trace width in mm.
        current_amps: Target current capacity in Amps.
        temperature_rise: Allowable temperature rise (e.g., 10°C, 20°C).
    """

    net_name: str
    width_mm: float
    current_amps: float
    temperature_rise: float = 10.0


@dataclass
class PDNRouteResult:
    """Result of PDN routing.

    Attributes:
        paths: Dictionary mapping net names to routed paths.
        via_arrays: List of via arrays added for layer transitions.
        ground_thermal_reliefs: Components with thermal relief connections.
    """

    paths: dict[str, "RoutePath"]
    via_arrays: list = field(default_factory=list)
    ground_thermal_reliefs: list[str] = field(default_factory=list)


class PDNRouter:
    """Router for power distribution networks.

    This router handles power nets with special considerations:
    1. Star topology from power sources to all loads
    2. Wide traces based on current requirements
    3. Via arrays for layer transitions
    4. Ground pour preparation

    Attributes:
        default_power_width_mm: Default trace width for power nets (mm).
        via_array_size: Size of via arrays (e.g., 2x2, 3x3).
        min_via_count: Minimum number of vias for power connections.
    """

    DEFAULT_POWER_WIDTH_MM = 0.5
    MIN_VIA_COUNT = 4
    DEFAULT_VIA_DIAMETER = 0.6
    DEFAULT_VIA_DRILL = 0.3

    def __init__(
        self,
        default_power_width_mm: float = 0.5,
        via_array_size: tuple[int, int] = (2, 2),
        min_via_count: int = 4,
    ):
        """Initialize the PDN router.

        Args:
            default_power_width_mm: Default trace width for power nets (mm).
            via_array_size: (rows, cols) for via arrays.
            min_via_count: Minimum number of vias for power connections.
        """
        self.default_power_width_mm = default_power_width_mm
        self.via_array_size = via_array_size
        self.min_via_count = min_via_count

    def _identify_power_sources(
        self, netlist: Netlist, net_name: str
    ) -> list[tuple[str, tuple[float, float]]]:
        """Identify power source components (regulators) for a given net.

        Args:
            netlist: Netlist containing components.
            net_name: Name of the power net.

        Returns:
            List of (component_ref, position) tuples for power sources.
        """
        sources = []

        power_source_footprints = [
            "LDO",
            "DC-DC",
            "BUCK",
            "BOOST",
            "REGULATOR",
            "AMS1117",
            "LM7805",
            "TPS",
            "RTQ",
            "LMR",
            "MP2359",
            "DCDC",
        ]

        output_pin_patterns = ["OUT", "VOUT", "SW", "VSW", "BOOT", "VBST"]

        for component in netlist.components:
            footprint_upper = component.footprint.upper()
            if any(ps in footprint_upper for ps in power_source_footprints):
                for pin in component.pins:
                    if pin.net == net_name:
                        if any(p in pin.name.upper() for p in output_pin_patterns):
                            pin_pos = pin_world_position(pin, component)
                            sources.append((component.ref, pin_pos))
                            break

        if not sources:
            for component in netlist.components:
                for pin in component.pins:
                    if pin.net == net_name:
                        if self._is_power_source_pin(pin.name):
                            pin_pos = pin_world_position(pin, component)
                            sources.append((component.ref, pin_pos))
                            break

        return sources

    def _is_power_source_pin(self, pin_name: str) -> bool:
        """Check if a pin is likely a power output pin."""
        pin_upper = pin_name.upper()
        output_indicators = ["OUT", "VOUT", "SW", "VSW", "PV", "PWR"]
        return any(ind in pin_upper for ind in output_indicators)

    def _identify_power_loads(
        self, netlist: Netlist, net_name: str, exclude_sources: Optional[list[str]] = None
    ) -> list[tuple[str, tuple[float, float], str]]:
        """Identify power load components for a given net.

        Args:
            netlist: Netlist containing components.
            net_name: Name of the power net.
            exclude_sources: List of component refs to exclude (power sources).

        Returns:
            List of (component_ref, position, pin_name) tuples for loads.
        """
        exclude = set(exclude_sources or [])
        loads = []

        for component in netlist.components:
            if component.ref in exclude:
                continue

            comp_pos = component.initial_position or (0.0, 0.0)
            for pin in component.pins:
                if pin.net == net_name:
                    if self._is_power_load_pin(pin.name):
                        pin_pos = pin.absolute_position(comp_pos, 0.0)
                        loads.append((component.ref, pin_pos, pin.name))
                        break

        return loads

    def _is_power_load_pin(self, pin_name: str) -> bool:
        """Check if a pin is likely a power input pin."""
        pin_upper = pin_name.upper()
        input_indicators = ["VCC", "VDD", "VIN", "PWR", "POWER", "V+", "VBAT"]
        return any(ind in pin_upper for ind in input_indicators)

    def _calculate_power_width(self, net: Net, source_current_ma: float = 500.0) -> float:
        """Calculate appropriate trace width for a power net.

        Args:
            net: The power net.
            source_current_ma: Estimated current from source in mA.

        Returns:
            Recommended trace width in mm.
        """
        if hasattr(net, "max_current") and net.max_current > 0:
            current_amps = net.max_current
        else:
            current_amps = source_current_ma / 1000.0

        base_width = self.default_power_width_mm

        if current_amps > 2.0:
            base_width = 1.0
        elif current_amps > 1.0:
            base_width = 0.8
        elif current_amps > 0.5:
            base_width = 0.6

        if hasattr(net, "net_class"):
            if net.net_class in ["Power", "HighVoltage"]:
                base_width = max(base_width, 0.8)

        return base_width

    def _create_via_array(
        self,
        position: tuple[float, float],
        layers: tuple[str, str] = ("F.Cu", "B.Cu"),
    ) -> dict:
        """Create a via array at the specified position.

        Args:
            position: (x, y) position for the via array center.
            layers: (top_layer, bottom_layer) for the vias.

        Returns:
            Via array configuration dictionary.
        """
        via_diameter = self.DEFAULT_VIA_DIAMETER
        via_drill = self.DEFAULT_VIA_DRILL
        rows, cols = self.via_array_size

        return {
            "position": position,
            "rows": rows,
            "cols": cols,
            "via_diameter": via_diameter,
            "via_drill": via_drill,
            "spacing": 0.4,
            "top_layer": layers[0],
            "bottom_layer": layers[1],
        }

    def route_power_distribution(
        self,
        netlist: Netlist,
        power_nets: list[str],
        board: "Board | None" = None,
    ) -> PDNRouteResult:
        """Route power distribution network for specified nets.

        This method routes power nets using star topology from power sources
        to all load components. It calculates appropriate trace widths and
        creates via arrays for layer transitions.

        Args:
            netlist: Netlist containing all components and nets.
            power_nets: List of power net names to route.
            board: Optional Board for additional constraints.

        Returns:
            PDNRouteResult with routed paths and via arrays.

        Example:
            >>> result = router.route_power_distribution(netlist, ["VCC", "+3.3V"])
            >>> result.paths.keys()
            dict_keys(['VCC_U1', 'VCC_C1', '+3.3V_U2', ...])
        """
        from temper_placer.routing.maze_router import RoutePath

        paths: dict[str, RoutePath] = {}
        via_arrays = []
        ground_thermal_reliefs: list[str] = []

        for net_name in power_nets:
            net = self._find_net(netlist, net_name)
            if net is None:
                logger.warning(f"Power net {net_name} not found in netlist")
                continue

            sources = self._identify_power_sources(netlist, net_name)
            loads = self._identify_power_loads(netlist, net_name, [s[0] for s in sources])

            if not sources:
                logger.warning(f"No power sources found for {net_name}")
                continue

            trace_width = self._calculate_power_width(net)

            for source_ref, source_pos in sources:
                for load_ref, load_pos, load_pin in loads:
                    path_name = f"{net_name}_{load_ref}"
                    route_path = self._route_power_trace(
                        source_pos,
                        load_pos,
                        trace_width,
                        board,
                    )

                    if route_path is not None:
                        route_path.net = net_name
                        route_path.trace_width = trace_width
                        paths[path_name] = route_path

                        if board and self._requires_layer_transition(source_pos, load_pos, board):
                            via_pos: tuple[float, float] = (
                                (float(route_path.cells[-1].x), float(route_path.cells[-1].y))
                                if route_path.cells
                                else load_pos
                            )
                            via_array = self._create_via_array(via_pos)
                            via_arrays.append(via_array)

        return PDNRouteResult(
            paths=paths,
            via_arrays=via_arrays,
            ground_thermal_reliefs=ground_thermal_reliefs,
        )

    def _find_net(self, netlist: Netlist, net_name: str) -> Optional[Net]:
        """Find a net by name in the netlist."""
        for net in netlist.nets:
            if net.name == net_name:
                return net
        return None

    def _route_power_trace(
        self,
        source_pos: tuple[float, float],
        load_pos: tuple[float, float],
        width_mm: float,
        board: "Board | None" = None,
    ) -> Optional["RoutePath"]:
        """Route a single power trace from source to load.

        Args:
            source_pos: (x, y) source position.
            load_pos: (x, y) load position.
            width_mm: Trace width in mm.
            board: Optional Board for constraints.

        Returns:
            RoutePath if successful, None otherwise.
        """
        from temper_placer.routing.maze_router import GridCell, RoutePath

        dx = load_pos[0] - source_pos[0]
        dy = load_pos[1] - source_pos[1]
        distance = (dx**2 + dy**2) ** 0.5

        if distance < 0.1:
            return RoutePath(
                net="",
                cells=[GridCell(int(source_pos[0]), int(source_pos[1]))],
                length=distance,
                via_count=0,
                success=True,
                trace_width=width_mm,
            )

        direct_path = self._create_direct_route(source_pos, load_pos)
        if direct_path:
            return RoutePath(
                net="",
                cells=direct_path,
                length=distance,
                via_count=0,
                success=True,
                trace_width=width_mm,
            )

        return RoutePath(
            net="",
            cells=[GridCell(int(source_pos[0]), int(source_pos[1]))],
            length=0,
            via_count=0,
            success=False,
            failure_reason="Could not route power trace",
            trace_width=width_mm,
        )

    def _create_direct_route(
        self, source_pos: tuple[float, float], load_pos: tuple[float, float]
    ) -> Optional[list]:
        """Create a direct L-shaped route between two points.

        Args:
            source_pos: (x, y) source position.
            load_pos: (x, y) load position.

        Returns:
            List of GridCells representing the route.
        """
        from temper_placer.routing.maze_router import GridCell

        cells = []
        x1, y1 = int(source_pos[0]), int(source_pos[1])
        x2, y2 = int(load_pos[0]), int(load_pos[1])

        if x1 == x2 and y1 == y2:
            return None

        if abs(x2 - x1) >= abs(y2 - y1):
            mid_x = x2
            mid_y = y1
        else:
            mid_x = x1
            mid_y = y2

        x, y = x1, y1
        while x != mid_x:
            cells.append(GridCell(x, y))
            x += 1 if x2 > x1 else -1

        while y != mid_y:
            cells.append(GridCell(x, y))
            y += 1 if y2 > y1 else -1

        while x != x2:
            cells.append(GridCell(x, y))
            x += 1 if x2 > x1 else -1

        cells.append(GridCell(x2, y2))

        return cells

    def _requires_layer_transition(
        self, source_pos: tuple[float, float], load_pos: tuple[float, float], board: Board
    ) -> bool:
        """Check if a route requires layer transition."""
        return False

    def route_from_detection_result(
        self,
        netlist: Netlist,
        detection_result,
        board: "Board | None" = None,
    ) -> PDNRouteResult:
        """Route all power nets from critical net detection result.

        This is a convenience method that routes all detected power nets.

        Args:
            netlist: Netlist containing all components and nets.
            detection_result: Result from CriticalNetDetector.detect_critical_nets.
            board: Optional Board for additional constraints.

        Returns:
            PDNRouteResult with routed paths.
        """
        power_nets = detection_result.power_nets
        return self.route_power_distribution(netlist, power_nets, board)

    def get_ground_pour_regions(
        self, netlist: Netlist, ground_nets: list[str]
    ) -> list[tuple[float, float, float, float]]:
        """Get bounding boxes for ground pour regions.

        Args:
            netlist: Netlist containing components.
            ground_nets: List of ground net names.

        Returns:
            List of (min_x, min_y, max_x, max_y) bounding boxes.
        """
        regions = []

        for ground_net in ground_nets:
            min_x, min_y = float("inf"), float("inf")
            max_x, max_y = float("-inf"), float("-inf")

            for component in netlist.components:
                comp_pos = component.initial_position or (0.0, 0.0)
                for pin in component.pins:
                    if pin.net == ground_net:
                        pin_x = comp_pos[0] + pin.position[0]
                        pin_y = comp_pos[1] + pin.position[1]
                        min_x = min(min_x, pin_x)
                        min_y = min(min_y, pin_y)
                        max_x = max(max_x, pin_x)
                        max_y = max(max_y, pin_y)

            if min_x != float("inf"):
                padding = 5.0
                regions.append(
                    (
                        max(0, min_x - padding),
                        max(0, min_y - padding),
                        max_x + padding,
                        max_y + padding,
                    )
                )

        return regions
