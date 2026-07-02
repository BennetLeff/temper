"""
Automatic loop extraction from netlist data.

This module provides heuristic-based extraction of current loops from netlists.
It detects power switches, gate drivers, and other key components to automatically
infer commutation loops, gate drive loops, and bootstrap circuits.

Auto-extracted loops have names prefixed with "auto_" and can be overridden by
manual YAML definitions.

Example usage:
    >>> from temper_placer.core.loop_extractor import auto_extract_loops
    >>> from temper_placer.core.netlist import Netlist
    >>>
    >>> loops = auto_extract_loops(netlist, topology_hints={'topology': 'half_bridge'})
    >>> print(f"Found {len(loops)} loops")
    >>> for loop in loops.get_critical_loops():
    ...     print(f"  {loop.name}: {loop.loop_type}")
"""

from __future__ import annotations

from dataclasses import dataclass

from .loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopPriority,
    LoopType,
)
from .netlist import Component, Netlist


@dataclass
class ComponentClassification:
    """Classification of a component's role in power electronics."""

    ref: str
    category: str  # 'power_switch', 'gate_driver', 'capacitor', 'diode', 'resistor', 'other'
    subcategory: str | None = None  # 'igbt', 'mosfet', 'bootstrap_diode', etc.
    confidence: float = 1.0  # 0.0-1.0


def classify_component(component: Component) -> ComponentClassification:
    """
    Classify a component based on ref, footprint, and attributes.

    Args:
        component: Component to classify.

    Returns:
        ComponentClassification with detected role.
    """
    ref = component.ref.upper()
    footprint = component.footprint.upper()
    value = component.attributes.get("value", "").upper()
    mpn = component.attributes.get("MPN", "").upper()

    # Power switches (IGBTs, MOSFETs)
    if ref.startswith("Q"):
        # Check for IGBT indicators
        if any(pattern in mpn for pattern in ["IK", "IHW", "IRG", "STGP", "FGA", "IRGP"]):
            return ComponentClassification(
                ref=component.ref,
                category="power_switch",
                subcategory="igbt",
                confidence=0.9,
            )
        # Check for MOSFET indicators
        if any(pattern in mpn for pattern in ["FET", "SI", "IRF", "BSC", "IPP", "STP"]):
            return ComponentClassification(
                ref=component.ref,
                category="power_switch",
                subcategory="mosfet",
                confidence=0.9,
            )
        # Footprint-based detection
        if any(pkg in footprint for pkg in ["TO-247", "TO-220", "TO-263"]):
            return ComponentClassification(
                ref=component.ref,
                category="power_switch",
                subcategory="unknown",
                confidence=0.7,
            )

    # Gate drivers
    if ref.startswith("U") and any(
        pattern in mpn for pattern in ["UCC", "ISO", "SI82", "HCPL", "FOD", "SI827", "ACPL"]
    ):
        return ComponentClassification(
            ref=component.ref,
            category="gate_driver",
            confidence=0.9,
        )

    # Capacitors
    if ref.startswith("C"):
        # Try to extract capacitance value
        cap_value_uf = _parse_capacitance(value)
        if cap_value_uf and cap_value_uf > 100:
            # Large capacitor - likely bus cap
            return ComponentClassification(
                ref=component.ref,
                category="capacitor",
                subcategory="bus",
                confidence=0.8,
            )
        elif "BOOT" in ref:
            return ComponentClassification(
                ref=component.ref,
                category="capacitor",
                subcategory="bootstrap",
                confidence=0.9,
            )
        else:
            return ComponentClassification(
                ref=component.ref,
                category="capacitor",
                subcategory="decoupling",
                confidence=0.7,
            )

    # Diodes
    if ref.startswith("D"):
        if "BOOT" in ref or "schottky" in mpn.lower():
            return ComponentClassification(
                ref=component.ref,
                category="diode",
                subcategory="bootstrap",
                confidence=0.8,
            )
        return ComponentClassification(
            ref=component.ref,
            category="diode",
            confidence=0.7,
        )

    # Resistors (gate resistors)
    if ref.startswith("R") and ("GATE" in ref or "G_" in ref or "_G" in ref):
        return ComponentClassification(
            ref=component.ref,
            category="resistor",
            subcategory="gate",
            confidence=0.8,
        )

    return ComponentClassification(
        ref=component.ref,
        category="other",
        confidence=0.0,
    )


def _parse_capacitance(value_str: str) -> float | None:
    """Parse capacitance string like '100uF', '220µF' to float in uF."""
    if not value_str:
        return None
    # Remove spaces and convert to upper
    value_str = value_str.replace(" ", "").upper()
    # Try to extract numeric part
    import re

    match = re.match(r"([\d.]+)\s*([UPNΜ]?F)?", value_str)
    if not match:
        return None
    numeric = float(match.group(1))
    unit = match.group(2) if match.group(2) else "F"

    # Convert to uF
    multipliers = {
        "PF": 1e-6,
        "NF": 1e-3,
        "UF": 1.0,
        "µF": 1.0,
        "F": 1e6,
    }
    return numeric * multipliers.get(unit, 1.0)


def find_power_switches(netlist: Netlist) -> list[Component]:
    """Find all power switches (IGBTs, MOSFETs) in the netlist."""
    switches = []
    for component in netlist.components:
        classification = classify_component(component)
        if classification.category == "power_switch":
            switches.append(component)
    return switches


def find_gate_drivers(netlist: Netlist) -> list[Component]:
    """Find all gate driver ICs in the netlist."""
    drivers = []
    for component in netlist.components:
        classification = classify_component(component)
        if classification.category == "gate_driver":
            drivers.append(component)
    return drivers


def get_pin_net(component: Component, pin_names: list[str]) -> str | None:
    """
    Get net name for a pin, trying multiple possible pin names.

    Args:
        component: Component to query.
        pin_names: List of possible pin names (e.g., ['DRAIN', 'D']).

    Returns:
        Net name if found, None otherwise.
    """
    for pin_name in pin_names:
        pin = component.get_pin(pin_name)
        if pin and pin.net:
            return pin.net
    return None


def get_common_net(comp_a: Component, comp_b: Component) -> str | None:
    """Find a net that connects two components."""
    nets_a = {pin.net for pin in comp_a.pins if pin.net}
    nets_b = {pin.net for pin in comp_b.pins if pin.net}
    common = nets_a & nets_b
    return list(common)[0] if common else None


def find_capacitors_between(netlist: Netlist, net_a: str, net_b: str) -> list[Component]:
    """Find capacitors connected between two nets."""
    caps = []
    for component in netlist.components:
        if not component.ref.startswith("C"):
            continue
        # Check if component connects to both nets
        comp_nets = {pin.net for pin in component.pins if pin.net}
        if net_a in comp_nets and net_b in comp_nets:
            caps.append(component)
    return caps


def detect_half_bridge_topology(netlist: Netlist) -> tuple[Component, Component] | None:
    """
    Detect half-bridge topology (two switches sharing a switch node).

    Returns:
        (high_side_switch, low_side_switch) tuple, or None if not found.
    """
    switches = find_power_switches(netlist)
    if len(switches) < 2:
        return None

    # Look for two switches that share a net (switch node)
    for i, sw_a in enumerate(switches):
        for sw_b in switches[i + 1 :]:
            common_net = get_common_net(sw_a, sw_b)
            if common_net:
                # Determine which is high-side vs low-side
                # Heuristic: high-side typically has higher voltage net on drain/collector
                # For now, just use ordering Q1 = high, Q2 = low
                if "1" in sw_a.ref or "H" in sw_a.ref.upper():
                    return (sw_a, sw_b)
                else:
                    return (sw_b, sw_a)

    return None


def trace_commutation_loop(
    netlist: Netlist, switch_high: Component, switch_low: Component
) -> Loop | None:
    """
    Trace commutation loop for a half-bridge.

    Args:
        netlist: Full netlist.
        switch_high: High-side switch component.
        switch_low: Low-side switch component.

    Returns:
        Loop if successful, None if loop cannot be traced.
    """
    # Find DC+ rail (high-side drain/collector)
    dc_plus = get_pin_net(switch_high, ["DRAIN", "D", "COLLECTOR", "C"])
    if not dc_plus:
        return None

    # Find DC- rail (low-side source/emitter)
    dc_minus = get_pin_net(switch_low, ["SOURCE", "S", "EMITTER", "E"])
    if not dc_minus:
        return None

    # Find switch node (connection between switches)
    sw_node = get_common_net(switch_high, switch_low)
    if not sw_node:
        return None

    # Find bus capacitors connected to DC+ and DC-
    bus_caps = find_capacitors_between(netlist, dc_plus, dc_minus)
    if not bus_caps:
        return None

    # Build component list
    components = [bus_caps[0].ref, switch_high.ref, switch_low.ref]

    # Build pin path
    pins = [
        LoopPin(bus_caps[0].ref, "+", dc_plus),
        LoopPin(switch_high.ref, "COLLECTOR", dc_plus),
        LoopPin(switch_high.ref, "EMITTER", sw_node),
        LoopPin(switch_low.ref, "COLLECTOR", sw_node),
        LoopPin(switch_low.ref, "EMITTER", dc_minus),
        LoopPin(bus_caps[0].ref, "-", dc_minus),
    ]

    # Build nets list
    nets = [dc_plus, sw_node, dc_minus]

    return Loop(
        name="auto_commutation",
        loop_type=LoopType.COMMUTATION,
        description=f"Auto-extracted commutation loop: {switch_high.ref} + {switch_low.ref}",
        components=components,
        pins=pins,
        nets=nets,
        priority=LoopPriority.CRITICAL,
        max_area_mm2=500.0,
        events=LoopEvent(
            di_dt=1.0e9,  # 1 A/ns typical IGBT turn-off
            dv_dt=5.0e9,  # 5 V/ns switch node
            frequency_hz=25000.0,  # 25 kHz default
            peak_current_a=30.0,  # Conservative estimate
        ),
        return_layer="L2_GND",
        return_net="PGND",
    )


def trace_gate_drive_loop(
    netlist: Netlist, switch: Component, driver: Component | None, is_high_side: bool
) -> Loop | None:
    """
    Trace gate drive loop from driver to switch.

    Args:
        netlist: Full netlist.
        switch: Power switch component.
        driver: Gate driver component (if known).
        is_high_side: True if this is high-side switch.

    Returns:
        Loop if successful, None if loop cannot be traced.
    """
    gate_net = get_pin_net(switch, ["GATE", "G"])
    if not gate_net:
        return None

    # Find gate resistor (resistor connected to gate net)
    gate_resistor = None
    for component in netlist.components:
        if component.ref.startswith("R"):
            comp_nets = {pin.net for pin in component.pins if pin.net}
            if gate_net in comp_nets:
                gate_resistor = component
                break

    # Build component list
    components = [switch.ref]
    if driver:
        components.insert(0, driver.ref)
    if gate_resistor:
        components.insert(1 if driver else 0, gate_resistor.ref)

    # Determine loop type
    loop_type = LoopType.GATE_DRIVE_HIGH if is_high_side else LoopType.GATE_DRIVE_LOW

    return Loop(
        name=f"auto_gate_drive_{switch.ref}",
        loop_type=loop_type,
        description=f"Auto-extracted gate drive loop for {switch.ref}",
        components=components,
        nets=[gate_net],
        priority=LoopPriority.CRITICAL,
        max_area_mm2=100.0,
        events=LoopEvent(
            di_dt=1.0e8,  # 100 mA/ns gate current
            frequency_hz=25000.0,
        ),
    )


def trace_bootstrap_loop(netlist: Netlist, _driver: Component) -> Loop | None:
    """
    Trace bootstrap charging loop if present.

    Args:
        netlist: Full netlist.
        driver: Gate driver component.

    Returns:
        Loop if bootstrap detected, None otherwise (isolated supply).
    """
    # Find bootstrap capacitor (look for components with "BOOT" in ref)
    boot_cap = None
    for component in netlist.components:
        if "BOOT" in component.ref.upper() and component.ref.startswith("C"):
            boot_cap = component
            break

    if not boot_cap:
        return None  # No bootstrap circuit

    # Find bootstrap diode
    boot_diode = None
    for component in netlist.components:
        if component.ref.startswith("D"):
            # Check if diode connects to bootstrap cap
            diode_nets = {pin.net for pin in component.pins if pin.net}
            cap_nets = {pin.net for pin in boot_cap.pins if pin.net}
            if diode_nets & cap_nets:
                boot_diode = component
                break

    components = []
    if boot_diode:
        components.append(boot_diode.ref)
    components.append(boot_cap.ref)

    return Loop(
        name="auto_bootstrap",
        loop_type=LoopType.BOOTSTRAP,
        description="Auto-extracted bootstrap charging loop",
        components=components,
        priority=LoopPriority.HIGH,
        max_area_mm2=50.0,
        events=LoopEvent(
            frequency_hz=25000.0,
            peak_current_a=0.5,  # Low bootstrap charging current
        ),
    )


def auto_extract_loops(netlist: Netlist, topology_hints: dict | None = None) -> LoopCollection:
    """
    Extract loops automatically from netlist.

    This function uses heuristics to detect power electronics topologies
    and extract critical current loops. All auto-extracted loops have
    names prefixed with "auto_" to distinguish them from manual definitions.

    Args:
        netlist: Parsed netlist with component and net info.
        topology_hints: Optional hints like {'topology': 'half_bridge'}.

    Returns:
        LoopCollection with auto-extracted loops.

    Example:
        >>> loops = auto_extract_loops(netlist, {'topology': 'half_bridge'})
        >>> print(f"Found {len(loops)} loops")
        >>> for loop in loops.get_critical_loops():
        ...     print(f"  {loop.name}: {loop.loop_type}")
    """
    # Try Rust backend first (R23: fallback)
    try:
        from temper_placer.core.loop_extractor_rs import auto_extract_loops_rs
        rs_result = auto_extract_loops_rs(netlist, topology_hints)
        if rs_result is not None:
            return rs_result
    except Exception:
        pass  # Fall through to Python implementation

    loops = []
    topology_hints = topology_hints or {}

    # Try to detect half-bridge topology
    half_bridge = detect_half_bridge_topology(netlist)
    if half_bridge:
        switch_high, switch_low = half_bridge

        # Extract commutation loop
        commutation_loop = trace_commutation_loop(netlist, switch_high, switch_low)
        if commutation_loop:
            loops.append(commutation_loop)

        # Find gate driver
        drivers = find_gate_drivers(netlist)
        driver = drivers[0] if drivers else None

        # Extract gate drive loops
        gate_high = trace_gate_drive_loop(netlist, switch_high, driver, is_high_side=True)
        if gate_high:
            loops.append(gate_high)

        gate_low = trace_gate_drive_loop(netlist, switch_low, driver, is_high_side=False)
        if gate_low:
            loops.append(gate_low)

        # Extract bootstrap loop if driver present
        if driver:
            bootstrap = trace_bootstrap_loop(netlist, driver)
            if bootstrap:
                loops.append(bootstrap)

    return LoopCollection(loops=loops)


def merge_loops(auto_loops: LoopCollection, manual_loops: LoopCollection) -> LoopCollection:
    """
    Merge auto-extracted and manual loop definitions.

    Manual definitions always take precedence. If a manual loop has the same
    name as an auto loop (without "auto_" prefix), the manual version is used.

    Args:
        auto_loops: Auto-extracted loops.
        manual_loops: Manually defined loops.

    Returns:
        Merged LoopCollection with manual overrides applied.

    Example:
        >>> auto = auto_extract_loops(netlist)
        >>> manual = load_loop_collection("loops/")
        >>> merged = merge_loops(auto, manual)
    """
    # Start with all manual loops
    merged = list(manual_loops.loops)

    # Add auto loops that don't have manual overrides
    manual_names = {loop.name for loop in manual_loops.loops}
    # Also check for manual names that match auto names without "auto_" prefix
    manual_base_names = {loop.name.replace("auto_", "") for loop in manual_loops.loops}

    for auto_loop in auto_loops.loops:
        # Check if there's a manual override
        auto_base_name = auto_loop.name.replace("auto_", "")
        if auto_loop.name not in manual_names and auto_base_name not in manual_base_names:
            merged.append(auto_loop)

    return LoopCollection(loops=merged)
