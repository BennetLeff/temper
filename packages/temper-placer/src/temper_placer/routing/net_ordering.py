"""
Net ordering algorithm for deterministic routing (temper-wna.1).

This module determines the order in which nets should be routed. Deterministic
ordering is critical - same inputs MUST produce the same ordering for reproducible
routing results.

Priority order (highest to lowest):
1. Loop membership: Nets in critical loops route first
2. Net class: HV > Power > GateDrive > Signal
3. Pin count: Fewer pins = higher priority (easier to route)
4. Estimated wirelength: Shorter = higher priority (HPWL)
5. Alphabetical: Final deterministic tie-breaker

Example usage:
    >>> from temper_placer.routing.net_ordering import order_nets, NetClass
    >>> from temper_placer.core.netlist import Netlist
    >>> from temper_placer.core.loop import LoopCollection
    >>>
    >>> ordered = order_nets(netlist, loops)
    >>> print(ordered)  # ['DC_BUS_P', 'SW_NODE', 'DC_BUS_N', 'GATE_H', ...]
"""

from dataclasses import dataclass
from enum import IntEnum
from functools import total_ordering

from temper_placer.core.loop import LoopCollection, LoopPriority
from temper_placer.core.netlist import Netlist


class NetClass(IntEnum):
    """Classification of net types for routing priority.

    Lower values = higher routing priority. HV nets route first to ensure
    they get the best routing channels before other nets consume resources.

    Attributes:
        HIGH_VOLTAGE: High voltage nets (DC bus, switching nodes) - route first
        POWER: Power distribution nets (VCC, power rails)
        GATE_DRIVE: Gate drive signals (critical timing)
        SIGNAL: General signals - route last
    """

    HIGH_VOLTAGE = 0
    POWER = 1
    GATE_DRIVE = 2
    SIGNAL = 3


@total_ordering
@dataclass
class NetPriority:
    """Composite priority key for deterministic net ordering.

    This dataclass implements comparison operators for sorting nets.
    The comparison is performed lexicographically on the tuple:
    (loop_criticality, net_class, pin_count, estimated_wirelength, name)

    Lower values in any field = higher priority (routes earlier).

    Attributes:
        loop_criticality: 0=critical, 1=high, 2=medium, 3=low/none
        net_class: NetClass enum value (0=HV, 1=Power, 2=GateDrive, 3=Signal)
        pin_count: Number of pins on the net (fewer = easier to route)
        estimated_wirelength: Estimated wirelength in mm (smaller = shorter routes)
        name: Net name (alphabetical tiebreaker for determinism)
    """

    loop_criticality: int
    net_class: NetClass
    pin_count: int
    estimated_wirelength: float
    name: str

    def _key(self) -> tuple:
        """Generate comparison key tuple."""
        return (
            self.loop_criticality,
            self.net_class.value,
            self.pin_count,
            self.estimated_wirelength,
            self.name,
        )

    def __lt__(self, other: "NetPriority") -> bool:
        """Less than comparison for sorting."""
        if not isinstance(other, NetPriority):
            return NotImplemented
        return self._key() < other._key()

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if not isinstance(other, NetPriority):
            return NotImplemented
        return self._key() == other._key()


def get_net_class_from_string(net_class_str: str) -> NetClass:
    """Map netlist string net class to NetClass enum.

    Args:
        net_class_str: Net class string from netlist (e.g., 'HighVoltage', 'Signal')

    Returns:
        Corresponding NetClass enum value. Unknown strings default to SIGNAL.

    Example:
        >>> get_net_class_from_string("HighVoltage")
        NetClass.HIGH_VOLTAGE
        >>> get_net_class_from_string("unknown")
        NetClass.SIGNAL
    """
    mapping = {
        "HighVoltage": NetClass.HIGH_VOLTAGE,
        "highvoltage": NetClass.HIGH_VOLTAGE,
        "HV": NetClass.HIGH_VOLTAGE,
        "Power": NetClass.POWER,
        "power": NetClass.POWER,
        "GateDrive": NetClass.GATE_DRIVE,
        "gatedrive": NetClass.GATE_DRIVE,
        "Gate": NetClass.GATE_DRIVE,
        "Signal": NetClass.SIGNAL,
        "signal": NetClass.SIGNAL,
    }
    return mapping.get(net_class_str, NetClass.SIGNAL)


def get_loop_criticality(net_name: str, loops: LoopCollection) -> int:
    """Compute loop criticality for a net.

    Searches all loops to find the highest priority loop that contains this net.
    If the net is in multiple loops, the highest priority (lowest number) wins.

    Args:
        net_name: Name of the net to check.
        loops: LoopCollection containing all design loops.

    Returns:
        Criticality level: 0=critical, 1=high, 2=medium, 3=low/none

    Example:
        >>> criticality = get_loop_criticality("DC_BUS_P", loops)
        >>> criticality
        0  # Net is in a critical priority loop
    """
    # Priority mapping: LoopPriority enum -> integer criticality
    priority_to_criticality = {
        LoopPriority.CRITICAL: 0,
        LoopPriority.HIGH: 1,
        LoopPriority.MEDIUM: 2,
        LoopPriority.LOW: 3,
    }

    # Find all loops containing this net
    containing_loops = loops.get_loops_for_net(net_name)

    if not containing_loops:
        return 3  # Not in any loop = low priority

    # Return the best (lowest) criticality
    best_criticality = 3
    for loop in containing_loops:
        criticality = priority_to_criticality.get(loop.priority, 3)
        best_criticality = min(best_criticality, criticality)

    return best_criticality


def compute_hpwl(net_name: str, netlist: Netlist) -> float:
    """Compute Half-Perimeter Wire Length (HPWL) for a net.

    HPWL is the half-perimeter of the bounding box of all pins.
    HPWL = (max_x - min_x) + (max_y - min_y).

    Args:
        net_name: Name of the net.
        netlist: Netlist containing component and pin information.

    Returns:
        HPWL in mm. Returns 0.0 for single-pin nets or non-existent nets.
    """
    pin_positions: list[tuple[float, float]] = []

    for component in netlist.components:
        comp_x, comp_y = 0.0, 0.0
        if hasattr(component, "initial_position") and component.initial_position:
            comp_x, comp_y = component.initial_position

        for pin in component.pins:
            if pin.net == net_name:
                pin_x = comp_x + pin.position[0]
                pin_y = comp_y + pin.position[1]
                pin_positions.append((pin_x, pin_y))

    if len(pin_positions) < 2:
        return 0.0

    xs = [p[0] for p in pin_positions]
    ys = [p[1] for p in pin_positions]

    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    return width + height


def compute_bbox_area(net_name: str, netlist: Netlist) -> float:
    """Compute bounding box area for a net based on pin positions.

    The bounding box is the smallest rectangle that contains all pins
    on the net. Area is computed as width * height in mm².

    Args:
        net_name: Name of the net.
        netlist: Netlist containing component and pin information.

    Returns:
        Bounding box area in mm². Returns 0.0 for single-pin nets or
        non-existent nets.

    Example:
        >>> area = compute_bbox_area("VCC", netlist)
        >>> area
        50.0  # 10mm x 5mm bounding box
    """
    # Collect all pin positions for this net
    pin_positions: list[tuple[float, float]] = []

    for component in netlist.components:
        # Get component position (default to origin if not set)
        comp_x, comp_y = 0.0, 0.0
        if hasattr(component, "initial_position") and component.initial_position:
            comp_x, comp_y = component.initial_position

        for pin in component.pins:
            if pin.net == net_name:
                # Pin position is component position + pin position offset
                pin_x = comp_x + pin.position[0]
                pin_y = comp_y + pin.position[1]
                pin_positions.append((pin_x, pin_y))

    # Need at least 2 pins to have a bounding box
    if len(pin_positions) < 2:
        return 0.0

    # Compute bounding box
    xs = [p[0] for p in pin_positions]
    ys = [p[1] for p in pin_positions]

    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    return width * height


def order_nets(netlist: Netlist, loops: LoopCollection) -> list[str]:
    """Determine deterministic routing order for all nets.

    Produces a sorted list of net names where earlier nets should be
    routed first. The ordering is fully deterministic - same inputs
    always produce the same output.

    Priority order:
    1. Loop membership (nets in critical loops first)
    2. Net class (HV > Power > GateDrive > Signal)
    3. Pin count (fewer pins = higher priority)
    4. Estimated wirelength (smaller = higher priority)
    5. Alphabetical (final tiebreaker)

    Args:
        netlist: Netlist containing all nets and components.
        loops: LoopCollection with loop definitions and priorities.

    Returns:
        List of net names in routing order (first = highest priority).

    Example:
        >>> ordered = order_nets(netlist, loops)
        >>> ordered
        ['DC_BUS_P', 'SW_NODE', 'DC_BUS_N', 'GATE_H', 'GATE_L', ...]
    """
    if not netlist.nets:
        return []

    # Build priority for each net
    priorities: list[tuple[NetPriority, str]] = []

    for net in netlist.nets:
        # Get net class
        net_class_str = getattr(net, "net_class", None) or "Signal"
        net_class = get_net_class_from_string(net_class_str)

        # Get loop criticality
        loop_criticality = get_loop_criticality(net.name, loops)

        # Get pin count
        pin_count = len(net.pins)

        # Get estimated wirelength (HPWL)
        estimated_wirelength = compute_hpwl(net.name, netlist)

        # Create priority object
        priority = NetPriority(
            loop_criticality=loop_criticality,
            net_class=net_class,
            pin_count=pin_count,
            estimated_wirelength=estimated_wirelength,
            name=net.name,
        )

        priorities.append((priority, net.name))

    # Sort by priority (lower = routes first)
    priorities.sort(key=lambda x: x[0])

    # Extract just the net names in sorted order
    return [name for _, name in priorities]
