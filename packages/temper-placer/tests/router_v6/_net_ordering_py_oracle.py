"""Pinned Python oracle for ``router_v6/net_ordering.py`` (Wave-4 cluster G).

DO NOT EDIT -- THESE ARE THE REFERENCE.
=======================================
Every executable statement below is a **verbatim** ``git show`` extraction
from commit ``15110feccc6ec9389f0777d3cff1ce9f81b11068`` (``origin/main``,
2026-08-04) of ``temper_placer/router_v6/net_ordering.py`` (105 stmts):
``NetClass``, ``NetPriority``, ``get_net_class_from_string``,
``get_loop_criticality``, ``compute_hpwl``, ``compute_bbox_area``,
``order_nets`` -- i.e. the whole module except its import block.

Nothing has been cleaned up, refactored, or fixed.
``test_net_ordering_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts each definition from the pinned commit and compares the source
text character for character.

Why this is its OWN oracle module (a correction to the survey)
---------------------------------------------------------------
The survey groups ``net_ordering`` (105) with ``escape_via_generator`` (67)
as cluster **G**, while already flagging it "weak ... arithmetic over nets
with no shared type.  Do not force it".  Reading the two modules, they do not
cluster **with each other at all**, and this slice splits them:

* ``net_ordering``'s kernel is a **total-order comparator**: a 6-tuple sort
  key, an ``IntEnum``, a 22-entry string->enum table, and two
  bounding-box reductions over pin coordinates.  Its inputs are ``Netlist``
  and ``LoopCollection``.  Its output is a permutation of net names.  It has
  no geometry beyond ``max(xs) - min(xs)``.
* ``escape_via_generator``'s kernel is a **clearance predicate** --
  ``sqrt((x - px)**2 + (y - py)**2) < radius + pin_radius + clearance - eps``
  -- over pad geometry, driven by ``DensePackage``/``DesignRules`` and
  ``rotate_local_to_world``.

They share no type, no fixture, no input corpus and no divergence class.  The
one thing a merged oracle would have bought -- one file instead of two --
costs a corpus that is a union of two unrelated shapes, which is exactly the
"forcing" the survey warned against.  So: two oracle modules, two corpora,
two differential suites, two PBT suites.  See
``_escape_via_py_oracle.py`` for the other half.

Which language's operator each call site uses (catalog §2)
-----------------------------------------------------------
This module imports **no numpy**, so **B12 does not apply anywhere in it**.
Every ``max``/``min`` below is a CPython builtin and must be mirrored with
``py_max``/``py_min`` semantics (B5), never ``f64::max``/``f64::min``:

* ``compute_hpwl``: ``max(xs) - min(xs)`` and ``max(ys) - min(ys)`` --
  the **iterable** forms of the builtins, whose NaN rule is "whatever
  survives a left-to-right ``>``/``<`` scan", i.e. a single NaN early in the
  list poisons the result while a NaN late in it is silently dropped.  A
  Rust ``iter().fold(f64::max)`` gets the second case wrong.
* ``compute_bbox_area``: the same four calls, then ``width * height``
  (``compute_hpwl`` returns ``width + height`` -- the only difference between
  the two functions is that one operator).
* ``get_loop_criticality``: ``min(best_criticality, criticality)`` on
  **ints**, accumulated in iteration order over
  ``loops.get_loops_for_net(net_name)``.  The iteration order of that call is
  part of the contract even though ``min`` makes it commutative here.

Float-order note (B7): ``compute_hpwl`` returns ``width + height`` where
``width`` and ``height`` are each a two-operand subtraction.  That is a
three-op chain in a fixed grouping, ``(max_x - min_x) + (max_y - min_y)``.
Do not fuse, reassociate, or route it through ``hypot``.

Rounding note (B3): there is **no** rounding, formatting, or ``round()`` in
this module.  Recorded explicitly so a reviewer does not have to grep for it.

Determinism: the property that matters
---------------------------------------
``order_nets`` sorts ``(NetPriority, name)`` pairs with ``list.sort``, which
is stable, using ``NetPriority.__lt__`` -> ``self._key() < other._key()`` on
a 6-tuple ending in ``name``.  When net names are distinct and every HPWL is
finite, that key is a **total order**, so the output is invariant under
permutation of ``netlist.nets``.  Measured over all 24 permutations of a
4-net design, and over all 6 permutations of a 3-net design tied on every
field except ``name``: **0 mismatches**.  That is the sharpest property this
module has and it holds -- see ``test_net_ordering_pbt.py`` P1 and M1.

It does **not** hold when a pin coordinate is NaN: ``compute_hpwl`` then
returns NaN, the 6-tuple comparison stops being a total order (NaN is
unordered against everything), and ``list.sort``'s result becomes a function
of input order.  Measured: 6 permutations of a 3-net design with one NaN
coordinate produce **4 distinct orderings**.  This is a real order-dependence
and it is pinned (``test_nan_wirelength_breaks_the_total_order``) rather than
papered over -- but it is gated on a NaN *input*, not on ``PYTHONHASHSEED``
or on dict iteration, so it is not the class of bug PR #730 fixed.  A Rust
mirror must reproduce CPython's timsort placement here, or reject NaN keys;
it may not silently pick its own order.

Duplicate net names are a genuine full tie (all six key fields equal), so the
output is whatever stable-sort order the input had.  Measured and pinned by
``test_duplicate_net_names_are_a_stable_tie``.
"""

# ruff: noqa: UP037
#   ``NetPriority.__lt__`` is annotated ``other: "NetPriority"``.  The quotes
#   are part of the verbatim pin; unquoting them is an edit to the oracle.

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from functools import total_ordering

from temper_placer.core.loop import LoopCollection, LoopPriority
from temper_placer.core.netlist import Netlist
from temper_placer.core.pin_geometry import pin_world_position

__all__ = [
    "NetClass",
    "NetPriority",
    "compute_bbox_area",
    "compute_hpwl",
    "get_loop_criticality",
    "get_net_class_from_string",
    "order_nets",
]


# --- net_ordering.py ---------------------------------------------------


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
        # High voltage nets (route first)
        "HighVoltage": NetClass.HIGH_VOLTAGE,
        "highvoltage": NetClass.HIGH_VOLTAGE,
        "HV": NetClass.HIGH_VOLTAGE,
        # Differential pairs (route early for length matching)
        "Differential": NetClass.DIFFERENTIAL,
        "differential": NetClass.DIFFERENTIAL,
        "DiffPair": NetClass.DIFFERENTIAL,
        # Power nets
        "Power": NetClass.POWER,
        "power": NetClass.POWER,
        # Gate drive nets
        "GateDrive": NetClass.GATE_DRIVE,
        "gatedrive": NetClass.GATE_DRIVE,
        "Gate": NetClass.GATE_DRIVE,
        # Split 2026-07-28 (R4): "GateDrive" no longer exists as a netclass
        # name in packages/temper-placer/configs/netclass_rules.yaml --
        # without these entries, GATE_*/PWM_* nets would silently fall
        # through to the NetClass.SIGNAL default below and lose their
        # routing-priority boost.
        "GateDriveHV": NetClass.GATE_DRIVE,
        "gatedrivehv": NetClass.GATE_DRIVE,
        "GateDriveSELV": NetClass.GATE_DRIVE,
        "gatedriveselv": NetClass.GATE_DRIVE,
        # Signal nets (default, includes FinePitch)
        "Signal": NetClass.SIGNAL,
        "signal": NetClass.SIGNAL,
        "FinePitch": NetClass.SIGNAL,  # Fine-pitch pads, treat as signal
        "finepitch": NetClass.SIGNAL,
        # Ground nets (route last, usually planes)
        "Ground": NetClass.GROUND,
        "ground": NetClass.GROUND,
        "GND": NetClass.GROUND,
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
                pin_x, pin_y = pin_world_position(pin, component)
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
                pin_x, pin_y = pin_world_position(pin, component)
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

    # Default priority for nets not in config
    DEFAULT_PRIORITY = 5
    priority_map = net_priority_config or {}

    # Build priority for each net
    priorities: list[tuple[NetPriority, str]] = []

    for net in netlist.nets:
        # EXP-6: Get explicit config priority (lower = routes first)
        config_priority = priority_map.get(net.name, DEFAULT_PRIORITY)

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
            config_priority=config_priority,  # EXP-6: New field
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
