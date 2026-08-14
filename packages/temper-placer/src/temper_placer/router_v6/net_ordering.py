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

Wave 4 Phase B (``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
``order_nets``, ``compute_hpwl``, ``compute_bbox_area``,
``get_net_class_from_string`` and ``get_loop_criticality`` delegate to
``temper_rust_router`` (``order_nets_py`` and neighbours) -- a total-order
comparator over nets and loops, not geometry. ``order_nets_py`` was blocked
(PR #751) on a real divergence -- the kernel had no slot for
``Component.initial_side``, so it never modelled the bottom-side X mirror
``core/pin_geometry.py`` applies -- fixed in #829 with a corpus row
(``mixed_side_mirror``) that pins the mirror. Re-verified here: the shipped
module is still AST-identical to its pinned oracle, and the fix is present
(see ``packages/temper-rust-router/src/net_ordering.rs``'s
``pin_world_position``).

``NetPriority`` is NOT wired to its two kernel-side comparison probes (see
``packages/temper-rust-router/src/net_ordering.rs`` for the pair that exist
to reproduce ``NetPriority``'s comparison semantics bit-for-bit under the
differential's NaN/identity-shortcut corpus rows -- their names are
deliberately not spelled out here, so this docstring itself does not trip
``scripts/check_unwired_kernels.py``'s substring scan into reporting a
production reference that is not real): ``order_nets`` no longer constructs
``NetPriority`` at all now that the whole function delegates in one call,
and nothing else in this repository constructs or compares a
``NetPriority`` directly. Wiring its comparison dunders to the kernel would
need inventing a caller rather than serving one -- exactly the "inert
kernel" failure mode that gate's own module docstring names.

Net-membership marshalling note: the kernel's ``loop_criticality`` matches a
net against a loop's explicit net list only. The shipped
``LoopCollection.get_loops_for_net``/``Loop.involves_net`` match against
``loop.nets`` OR any of the loop's pins' nets. ``_loop_specs_wire`` below
passes the UNION of both, not ``loop.nets`` alone -- every loop source in
this repository today (``configs/templates/loops/*.yaml`` via
``io/loop_loader.py``, and ``core/loop_extractor.py``'s auto-extraction)
keeps ``nets`` a superset of its pins' nets, so the union is a no-op against
every loop this repo currently constructs, but computing it directly (rather
than only auditing today's callers) is what keeps this correct for a loop
built with ``pins=`` and no explicit ``nets=``.
"""

from dataclasses import dataclass
from enum import IntEnum
from functools import total_ordering

import temper_rust_router as _trr

from temper_placer.core.loop import LoopCollection
from temper_placer.core.netlist import Netlist


class NetClass(IntEnum):
    """Classification of net types for routing priority.

    Lower values = higher routing priority. HV nets route first to ensure
    they get the best routing channels before other nets consume resources.

    Attributes:
        HIGH_VOLTAGE: High voltage nets (DC bus, switching nodes) - route first
        DIFFERENTIAL: Differential pairs (USB, etc.) - route early for matched lengths
        POWER: Power distribution nets (VCC, power rails)
        GATE_DRIVE: Gate drive signals (critical timing)
        SIGNAL: General signals (including FinePitch)
        GROUND: Ground plane nets - route last (usually via zones)
    """

    HIGH_VOLTAGE = 0
    DIFFERENTIAL = 1
    POWER = 2
    GATE_DRIVE = 3
    SIGNAL = 4
    GROUND = 5


@total_ordering
@dataclass
class NetPriority:
    """Composite priority key for deterministic net ordering.

    This dataclass implements comparison operators for sorting nets.
    The comparison is performed lexicographically on the tuple:
    (config_priority, loop_criticality, net_class, pin_count, estimated_wirelength, name)

    Lower values in any field = higher priority (routes earlier).

    Attributes:
        config_priority: Explicit priority from config (1=highest, 5=default, 6+=low)
        loop_criticality: 0=critical, 1=high, 2=medium, 3=low/none
        net_class: NetClass enum value (0=HV, 1=Power, 2=GateDrive, 3=Signal)
        pin_count: Number of pins on the net (fewer = easier to route)
        estimated_wirelength: Estimated wirelength in mm (smaller = shorter routes)
        name: Net name (alphabetical tiebreaker for determinism)
    """

    config_priority: int  # EXP-6: Explicit priority from config (1=highest)
    loop_criticality: int
    net_class: NetClass
    pin_count: int
    estimated_wirelength: float
    name: str

    def _key(self) -> tuple:
        """Generate comparison key tuple."""
        return (
            self.config_priority,  # EXP-6: Config priority is first tiebreaker
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


def _components_wire(netlist: Netlist) -> list[tuple]:
    """Marshal ``netlist.components`` into the kernel's component-row
    contract: ``[(ref, initial_position, rotation, [(pin_number, position,
    net)], initial_side)]``.

    ``initial_side`` is the #829 fix's slot -- an optional 5th element so the
    kernel mirrors X for back-side pads exactly as
    ``core/pin_geometry.pin_world_position`` does.
    """
    return [
        (
            comp.ref,
            comp.initial_position,
            comp.initial_rotation_quadrant,
            [(pin.number, pin.position, pin.net) for pin in comp.pins],
            comp.initial_side,
        )
        for comp in netlist.components
    ]


def _loop_specs_wire(loops: LoopCollection) -> list[tuple[str, str, list[str]]]:
    """Marshal a ``LoopCollection`` into the kernel's ``[(loop_name,
    priority_name, [net, ...])]`` contract.

    See the module docstring's "Net-membership marshalling note": the net
    list here is the union of ``loop.nets`` and every net named by
    ``loop.pins``, reproducing ``Loop.involves_net``'s OR rather than
    ``loop.nets`` alone.
    """
    specs = []
    for loop in loops.loops:
        nets = list(dict.fromkeys([*loop.nets, *(p.net_name for p in loop.pins if p.net_name)]))
        specs.append((loop.name, loop.priority.name, nets))
    return specs


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
    return NetClass(_trr.net_class_from_string_py(net_class_str))


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
    return _trr.net_loop_criticality_py(net_name, _loop_specs_wire(loops))


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
    return _trr.net_compute_hpwl_py(net_name, _components_wire(netlist))


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
    return _trr.net_compute_bbox_area_py(net_name, _components_wire(netlist))


def order_nets(
    netlist: Netlist,
    loops: LoopCollection,
    net_priority_config: dict[str, int] | None = None,
) -> list[str]:
    """Determine deterministic routing order for all nets.

    Produces a sorted list of net names where earlier nets should be
    routed first. The ordering is fully deterministic - same inputs
    always produce the same output.

    Priority order (EXP-6 enhanced):
    1. Config priority (explicit from net_priority config section)
    2. Loop membership (nets in critical loops first)
    3. Net class (HV > Power > GateDrive > Signal)
    4. Pin count (fewer pins = higher priority)
    5. Estimated wirelength (smaller = higher priority)
    6. Alphabetical (final tiebreaker)

    Args:
        netlist: Netlist containing all nets and components.
        loops: LoopCollection with loop definitions and priorities.
        net_priority_config: Optional dict mapping net names to priority (1=highest, 5=default).

    Returns:
        List of net names in routing order (first = highest priority).

    Example:
        >>> ordered = order_nets(netlist, loops, {"USB_D+": 1, "USB_D-": 1})
        >>> ordered
        ['USB_D+', 'USB_D-', 'DC_BUS_P', 'SW_NODE', ...]
    """
    if not netlist.nets:
        return []

    components = _components_wire(netlist)
    nets = [(net.name, net.pins, net.net_class) for net in netlist.nets]
    loop_specs = _loop_specs_wire(loops)

    return _trr.order_nets_py(components, nets, loop_specs, net_priority_config)
