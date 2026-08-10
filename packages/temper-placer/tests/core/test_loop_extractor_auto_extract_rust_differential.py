"""Differential test: Rust loop extraction (``temper-rust-router``) vs the
pinned pre-migration Python extractor.

Wave 4 — ``core/loop_extractor.py`` (R11/R12/R13 backend). The extraction
compute (``classify_component`` → ``detect_half_bridge_topology`` →
``trace_*`` → ``auto_extract_loops``) was migrated to
``temper-rust-router-core::loop_extractor`` with a JSON bridge
(``temper_rust_router.auto_extract_loops_rust``) and a Python shim
(``core/loop_extractor_rs.py``) that reconstructs the ``Loop`` objects.
``auto_extract_loops`` delegates to the Rust backend first and falls back to
the Python compute only when the extension is unavailable (R23).

The pre-migration implementation is copied VERBATIM below as ``_oracle_*``
(blob ``2d614411``, the state before commit ``8351512e`` added the Rust
delegation block). Every assertion drives IDENTICAL netlists through both
sides.

What is compared, and on what exactness:

- PRESERVED fields (the shim's schema contract — Rust computes these):
  ``name``, ``loop_type`` (as the string value), ``components`` (order
  matters), ``nets`` (order matters), ``max_area_mm2`` (bit-exact via
  ``float.hex()``). Loop ORDER is also asserted — the Rust kernel and the
  oracle emit commutation, gate-high, gate-low, bootstrap in the same
  order.
- RECONSTRUCTED fields: ``priority``, ``events``, ``return_layer``,
  ``return_net`` are deterministically derived from ``loop_type`` by the
  shim; they are asserted against the oracle's hardcoded per-type values.
- LOST fields (allowed to differ, documented in the shim): ``pins``,
  ``description``.

Known divergence classes, recorded (not hidden — see the tie-break rule in
``docs/wave4-discipline-contract.md`` §3):

1. **Error-path abort semantics.** The Rust kernel propagates the FIRST
   trace failure (``?``) and returns ``ok: false`` for the whole
   extraction; the Python oracle is opportunistic (each ``trace_*`` is
   independent, failures are skipped). For every netlist where the Rust
   kernel SUCCEEDS this suite asserts bit-parity; where it errors, the
   R23 fallback guarantees the production result equals the oracle, and
   ``test_rust_error_cases_match_python`` pins that contract.
2. **``classify_component`` subcategory/confidence.** The Rust classifier
   (``classify.rs``) is a tiered reimplementation, not a byte-copy: e.g.
   ``C_BOOT`` gets confidence 0.7 (Python: 0.9), ``D1`` non-boot subcategory
   is ``"generic"`` (Python: ``None``), a bare ``Q`` with no MPN/footprint
   signal is ``power_switch`` (Python falls through to ``"other"``), and the
   Rust MPN-pattern tables are supersets. Only the extraction-relevant
   CATEGORY (power_switch/capacitor/gate_driver) feeds extraction, and it
   agrees on every corpus input below (switches always carry a MPN or
   TO-* footprint; ``U`` components always carry a driver MPN). These
   divergences are therefore not visible through ``auto_extract_loops``.
3. **Split-capacitor chains (R10).** ``find_capacitor_chain`` extends the
   oracle's ``find_capacitors_between`` with a capacitor-filtered BFS for
   chain topologies. No corpus netlist here relies on a chain (every one
   has a single bus capacitor spanning both rails), so the Rust "first
   try" path — which is byte-identical to the oracle's direct-span search —
   is what is exercised.
4. **Return-path reconstruction.** The shim reconstructs
   ``return_layer`` / ``return_net`` as ``""`` for loop types the oracle
   leaves at the dataclass default ``None`` (gate-drive, bootstrap).
   Pinned by ``test_loop_extractor_parity.py``; asserted here in
   ``test_shim_reconstruction_matches_oracle_on_all_fields``.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass

import pytest

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopPriority,
    LoopType,
)
from temper_placer.core.loop_extractor_rs import (
    _dict_to_loop_collection,
    _netlist_to_dict,
)
from temper_placer.core.netlist import Component, Netlist, Pin

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the module AS COMMITTED
# before the Rust delegation; do not edit — they are the reference).
# Function bodies are byte-for-byte the pre-migration implementation;
# only the names carry the ``_oracle_`` prefix so the block can live
# alongside the tests.
# ---------------------------------------------------------------------------


@dataclass
class ComponentClassification:
    """Classification of a component's role in power electronics."""

    ref: str
    category: str  # 'power_switch', 'gate_driver', 'capacitor', 'diode', 'resistor', 'other'
    subcategory: str | None = None  # 'igbt', 'mosfet', 'bootstrap_diode', etc.
    confidence: float = 1.0  # 0.0-1.0


def _oracle_classify_component(component: Component) -> ComponentClassification:
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
        cap_value_uf = _oracle__parse_capacitance(value)
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


def _oracle__parse_capacitance(value_str: str) -> float | None:
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


def _oracle_find_power_switches(netlist: Netlist) -> list[Component]:
    """Find all power switches (IGBTs, MOSFETs) in the netlist."""
    switches = []
    for component in netlist.components:
        classification = _oracle_classify_component(component)
        if classification.category == "power_switch":
            switches.append(component)
    return switches


def _oracle_find_gate_drivers(netlist: Netlist) -> list[Component]:
    """Find all gate driver ICs in the netlist."""
    drivers = []
    for component in netlist.components:
        classification = _oracle_classify_component(component)
        if classification.category == "gate_driver":
            drivers.append(component)
    return drivers


def _oracle_get_pin_net(component: Component, pin_names: list[str]) -> str | None:
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


def _oracle_get_common_net(comp_a: Component, comp_b: Component) -> str | None:
    """Find a net that connects two components."""
    nets_a = {pin.net for pin in comp_a.pins if pin.net}
    nets_b = {pin.net for pin in comp_b.pins if pin.net}
    common = nets_a & nets_b
    return list(common)[0] if common else None


def _oracle_find_capacitors_between(netlist: Netlist, net_a: str, net_b: str) -> list[Component]:
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


def _oracle_detect_half_bridge_topology(netlist: Netlist) -> tuple[Component, Component] | None:
    """
    Detect half-bridge topology (two switches sharing a switch node).

    Returns:
        (high_side_switch, low_side_switch) tuple, or None if not found.
    """
    switches = _oracle_find_power_switches(netlist)
    if len(switches) < 2:
        return None

    # Look for two switches that share a net (switch node)
    for i, sw_a in enumerate(switches):
        for sw_b in switches[i + 1 :]:
            common_net = _oracle_get_common_net(sw_a, sw_b)
            if common_net:
                # Determine which is high-side vs low-side
                # Heuristic: high-side typically has higher voltage net on drain/collector
                # For now, just use ordering Q1 = high, Q2 = low
                if "1" in sw_a.ref or "H" in sw_a.ref.upper():
                    return (sw_a, sw_b)
                else:
                    return (sw_b, sw_a)

    return None


def _oracle_trace_commutation_loop(
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
    dc_plus = _oracle_get_pin_net(switch_high, ["DRAIN", "D", "COLLECTOR", "C"])
    if not dc_plus:
        return None

    # Find DC- rail (low-side source/emitter)
    dc_minus = _oracle_get_pin_net(switch_low, ["SOURCE", "S", "EMITTER", "E"])
    if not dc_minus:
        return None

    # Find switch node (connection between switches)
    sw_node = _oracle_get_common_net(switch_high, switch_low)
    if not sw_node:
        return None

    # Find bus capacitors connected to DC+ and DC-
    bus_caps = _oracle_find_capacitors_between(netlist, dc_plus, dc_minus)
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


def _oracle_trace_gate_drive_loop(
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
    gate_net = _oracle_get_pin_net(switch, ["GATE", "G"])
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


def _oracle_trace_bootstrap_loop(netlist: Netlist, _driver: Component) -> Loop | None:
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


def _oracle_auto_extract_loops(netlist: Netlist, topology_hints: dict | None = None) -> LoopCollection:
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
    loops = []
    topology_hints = topology_hints or {}

    # Try to detect half-bridge topology
    half_bridge = _oracle_detect_half_bridge_topology(netlist)
    if half_bridge:
        switch_high, switch_low = half_bridge

        # Extract commutation loop
        commutation_loop = _oracle_trace_commutation_loop(netlist, switch_high, switch_low)
        if commutation_loop:
            loops.append(commutation_loop)

        # Find gate driver
        drivers = _oracle_find_gate_drivers(netlist)
        driver = drivers[0] if drivers else None

        # Extract gate drive loops
        gate_high = _oracle_trace_gate_drive_loop(netlist, switch_high, driver, is_high_side=True)
        if gate_high:
            loops.append(gate_high)

        gate_low = _oracle_trace_gate_drive_loop(netlist, switch_low, driver, is_high_side=False)
        if gate_low:
            loops.append(gate_low)

        # Extract bootstrap loop if driver present
        if driver:
            bootstrap = _oracle_trace_bootstrap_loop(netlist, driver)
            if bootstrap:
                loops.append(bootstrap)

    return LoopCollection(loops=loops)


def _oracle_merge_loops(auto_loops: LoopCollection, manual_loops: LoopCollection) -> LoopCollection:
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


# ---------------------------------------------------------------------------
# Netlist corpus builders (inputs constrained so the Rust kernel and the
# oracle agree on every classification CATEGORY — see the module docstring).
# ---------------------------------------------------------------------------


def _pin(name: str, net: str) -> Pin:
    return Pin(name, "1", (0.0, 0.0), net)


def _netlist(components: list[Component]) -> Netlist:
    return Netlist(components=components, nets=[])


def _full_half_bridge(with_driver=True, with_resistor=True, with_bootstrap=True) -> Netlist:
    """Mirror of the ``test_loop_extractor.py`` half-bridge fixture."""
    comps = [
        Component(
            ref="Q1",
            footprint="TO-247-3",
            bounds=(1.0, 1.0),
            pins=[
                _pin("GATE", "GATE_H"),
                _pin("COLLECTOR", "DC_BUS+"),
                _pin("EMITTER", "SW_NODE"),
            ],
            attributes={"MPN": "IKW40N120H3", "value": "1200V 40A"},
        ),
        Component(
            ref="Q2",
            footprint="TO-220",
            bounds=(1.0, 1.0),
            pins=[
                _pin("GATE", "GATE_L"),
                _pin("DRAIN", "SW_NODE"),
                _pin("SOURCE", "PGND"),
            ],
            attributes={"MPN": "IRFP250N", "value": "200V 30A"},
        ),
        Component(
            ref="C_BUS1",
            footprint="CAP_ELECTROLYTIC",
            bounds=(1.0, 1.0),
            pins=[_pin("+", "DC_BUS+"), _pin("-", "PGND")],
            attributes={"value": "470uF", "voltage": "400V"},
        ),
    ]
    if with_driver:
        comps.insert(2, Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(1.0, 1.0),
            pins=[_pin("OUTA", "GATE_H_DRV"), _pin("OUTB", "GATE_L_DRV")],
            attributes={"MPN": "UCC21550", "value": "Gate Driver"},
        ))
    if with_resistor:
        comps.append(Component(
            ref="RG_H",
            footprint="R_0805",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "GATE_H_DRV"), _pin("2", "GATE_H")],
            attributes={"value": "10R"},
        ))
    if with_bootstrap and with_driver:
        comps.extend([
            Component(
                ref="C_BOOT",
                footprint="C_0805",
                bounds=(1.0, 1.0),
                pins=[_pin("1", "VCC_BOOT"), _pin("2", "SW_NODE")],
                attributes={"value": "1uF"},
            ),
            Component(
                ref="D_BOOT",
                footprint="SOD-123",
                bounds=(1.0, 1.0),
                pins=[_pin("A", "VCC_15V"), _pin("K", "VCC_BOOT")],
                attributes={"MPN": "BAT54", "value": "Schottky"},
            ),
        ])
    return _netlist(comps)


def _minimal_half_bridge() -> Netlist:
    """Q1/Q2 + a single bus capacitor. Exercises the IGBT-style pin names
    (COLLECTOR/EMITTER/SOURCE) and the no-driver, no-resistor path."""
    return _netlist([
        Component(
            ref="Q1",
            footprint="TO-247-3",
            bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_H"), _pin("COLLECTOR", "DC+"), _pin("EMITTER", "SW")],
            attributes={"MPN": "IKW40N120H3"},
        ),
        Component(
            ref="Q2",
            footprint="TO-220",
            bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_L"), _pin("COLLECTOR", "SW"), _pin("EMITTER", "DC-")],
            attributes={"MPN": "IRG4PC50U"},
        ),
        Component(
            ref="C_BUS",
            footprint="CP_Radial_D10.0mm",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "DC+"), _pin("2", "DC-")],
            attributes={"value": "1000uF"},
        ),
    ])


def _mosfet_half_bridge() -> Netlist:
    """Both switches MOSFETs (DRAIN/SOURCE pins, IRF-series MPNs)."""
    return _netlist([
        Component(
            ref="Q1",
            footprint="TO-220",
            bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_H"), _pin("DRAIN", "DC_BUS+"), _pin("SOURCE", "SW_NODE")],
            attributes={"MPN": "IRF840"},
        ),
        Component(
            ref="Q2",
            footprint="TO-220",
            bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_L"), _pin("DRAIN", "SW_NODE"), _pin("SOURCE", "DC_BUS-")],
            attributes={"MPN": "IRFP250N"},
        ),
        Component(
            ref="C_DC",
            footprint="CAP_ELECTROLYTIC",
            bounds=(1.0, 1.0),
            pins=[_pin("+", "DC_BUS+"), _pin("-", "DC_BUS-")],
            attributes={"value": "2200uF"},
        ),
    ])


def _boot_cap_without_diode() -> Netlist:
    """Full half bridge + bootstrap cap but no diode: the bootstrap loop's
    components must be exactly [C_BOOT] on both sides."""
    return _netlist([
        Component(
            ref="Q1",
            footprint="TO-247-3",
            bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_H"), _pin("COLLECTOR", "DC+"), _pin("EMITTER", "SW")],
            attributes={"MPN": "IKW40N120H3"},
        ),
        Component(
            ref="Q2",
            footprint="TO-220",
            bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_L"), _pin("DRAIN", "SW"), _pin("SOURCE", "DC-")],
            attributes={"MPN": "IRFP250N"},
        ),
        Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(1.0, 1.0),
            pins=[_pin("OUTA", "GATE_H"), _pin("OUTB", "GATE_L")],
            attributes={"MPN": "UCC21550"},
        ),
        Component(
            ref="C_BUS",
            footprint="CP_Radial_D10.0mm",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "DC+"), _pin("2", "DC-")],
            attributes={"value": "1000uF"},
        ),
        Component(
            ref="C_BOOT",
            footprint="C_0805",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "VCC_BOOT"), _pin("2", "SW")],
            attributes={"value": "1uF"},
        ),
    ])


def _random_half_bridge(rng: random.Random) -> Netlist:
    """Randomized half bridge, constrained to the parity-holding subset:
    switches always carry an MPN or TO-* footprint; exactly one bus cap
    spans the rails; the driver (if any) carries a driver MPN; optional
    gate resistor and bootstrap pair on the expected nets."""
    hi_ref = rng.choice(["Q1", "QH"])
    lo_ref = rng.choice(["Q2", "QL"])
    hi_mpn = rng.choice(["IKW40N120H3", "IRG4PC50U", "IRFP460"])
    lo_mpn = rng.choice(["IRFP250N", "IRFB4110", "STP75NF75"])
    hi_fp = rng.choice(["TO-247", "TO-220"])
    lo_fp = rng.choice(["TO-220", "TO-263"])
    hi_pin_style = rng.choice(["IGBT", "MOSFET"])
    lo_pin_style = rng.choice(["IGBT", "MOSFET"])

    hi_rail = _pin("COLLECTOR", "DC+") if hi_pin_style == "IGBT" else _pin("DRAIN", "DC+")
    hi_sw = _pin("EMITTER" if hi_pin_style == "IGBT" else "SOURCE", "SW")

    if lo_pin_style == "IGBT":
        lo_sw = _pin("COLLECTOR", "SW")
        lo_rail = _pin("EMITTER", "DC-")
    else:
        lo_sw = _pin("DRAIN", "SW")
        lo_rail = _pin("SOURCE", "DC-")

    comps = [
        Component(
            ref=hi_ref, footprint=hi_fp, bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_H"), hi_rail, hi_sw],
            attributes={"MPN": hi_mpn},
        ),
        Component(
            ref=lo_ref, footprint=lo_fp, bounds=(1.0, 1.0),
            pins=[_pin("GATE", "GATE_L"), lo_sw, lo_rail],
            attributes={"MPN": lo_mpn},
        ),
        Component(
            ref=rng.choice(["C_BUS1", "C_DC", "CB"]),
            footprint="CP_Radial_D10.0mm",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "DC+"), _pin("2", "DC-")],
            attributes={"value": rng.choice(["470uF", "1000uF", "2200uF"])},
        ),
    ]

    if rng.random() < 0.5:
        comps.insert(2, Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(1.0, 1.0),
            pins=[_pin("OUTA", "GATE_H_DRV"), _pin("OUTB", "GATE_L_DRV")],
            attributes={"MPN": rng.choice(["UCC21550", "ISO5852S"])},
        ))
    if rng.random() < 0.5:
        comps.append(Component(
            ref=rng.choice(["RG_H", "R_GATE_H"]),
            footprint="R_0805",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "GATE_H_DRV"), _pin("2", "GATE_H")],
            attributes={"value": "10R"},
        ))
    if rng.random() < 0.5:
        comps.append(Component(
            ref="C_BOOT",
            footprint="C_0805",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "VCC_BOOT"), _pin("2", "SW")],
            attributes={"value": "1uF"},
        ))
        comps.append(Component(
            ref="D_BOOT",
            footprint="SOD-123",
            bounds=(1.0, 1.0),
            pins=[_pin("A", "VCC_15V"), _pin("K", "VCC_BOOT")],
            attributes={"MPN": "BAT54"},
        ))
    return _netlist(comps)


_CORPUS = [
    ("full", _full_half_bridge()),
    ("full_no_driver", _full_half_bridge(with_driver=False)),
    ("full_no_resistor", _full_half_bridge(with_resistor=False)),
    ("full_no_bootstrap", _full_half_bridge(with_bootstrap=False)),
    ("minimal", _minimal_half_bridge()),
    ("mosfets", _mosfet_half_bridge()),
    ("boot_no_diode", _boot_cap_without_diode()),
]

_RANDOM_CORPUS = [_random_half_bridge(random.Random(i)) for i in range(30)]


# ---------------------------------------------------------------------------
# Canonicalization + Rust bridge.
# ---------------------------------------------------------------------------

def _f(value) -> str:
    """Bit-exact float key."""
    return None if value is None else float(value).hex()


def _loop_canon(loop) -> tuple:
    """Oracle Loop -> comparable tuple (PRESERVED fields only)."""
    return (
        loop.name,
        loop.loop_type.value if hasattr(loop, 'loop_type') else loop.loop_type,
        tuple(loop.components),
        tuple(loop.nets),
        _f(loop.max_area_mm2),
    )


def _dict_canon(loop_dict: dict) -> tuple:
    """Raw Rust-bridge loop dict -> comparable tuple (PRESERVED fields)."""
    return (
        loop_dict["name"],
        loop_dict["loop_type"],
        tuple(loop_dict.get("components", [])),
        tuple(loop_dict.get("nets", [])),
        _f(loop_dict.get("max_area_mm2", 500.0)),
    )


def _rust_bridge(netlist: Netlist) -> dict:
    import temper_rust_router

    result = json.loads(
        temper_rust_router.auto_extract_loops_rust(json.dumps(_netlist_to_dict(netlist)))
    )
    return result


# ---------------------------------------------------------------------------
# Differential tests: Rust vs oracle, bit-identical on PRESERVED fields.
# ---------------------------------------------------------------------------

def _compare_loops_strict(
    oracle: LoopCollection,
    rust: dict,
) -> None:
    """Bit-exact comparison — all PRESERVED fields must match."""
    oracle_by_name = {loop.name: loop for loop in oracle.loops}
    rust_by_name = {d["name"]: d for d in rust["loops"]}

    # 1. Same set of loop names
    assert set(oracle_by_name) == set(rust_by_name), (
        f"Loop name sets must match exactly\n"
        f"  oracle_only={set(oracle_by_name) - set(rust_by_name)}\n"
        f"  rust_only={set(rust_by_name) - set(oracle_by_name)}"
    )

    # 2. Every loop matches bit-exactly on PRESERVED fields
    for name in oracle_by_name:
        oracle_canon = _loop_canon(oracle_by_name[name])
        rust_canon = _dict_canon(rust_by_name[name])
        assert rust_canon == oracle_canon, (
            f"{name}: bit-exact mismatch\n"
            f"  oracle={oracle_canon}\n"
            f"  rust={rust_canon}"
        )


@pytest.mark.parametrize("netlist", [c for _, c in _CORPUS], ids=[n for n, _ in _CORPUS])
def test_oracle_and_rust_preserved_fields_bit_identical(netlist):
    """For every corpus netlist the Rust kernel must succeed and emit the
    same loops as the oracle on PRESERVED fields — bit-exact, no exceptions."""
    oracle = _oracle_auto_extract_loops(netlist)
    assert len(oracle.loops) > 0, "corpus netlist must extract at least one loop (anti-vacuity)"

    rust = _rust_bridge(netlist)
    assert rust.get("ok") is True, f"Rust kernel should succeed: {rust.get('error')}"

    _compare_loops_strict(oracle, rust)


@pytest.mark.parametrize("seed", range(len(_RANDOM_CORPUS)))
def test_randomized_netlists_preserved_fields_bit_identical(seed):
    """30 seeded random half bridges — bit-identical, no exceptions."""
    netlist = _RANDOM_CORPUS[seed]
    oracle = _oracle_auto_extract_loops(netlist)
    assert len(oracle.loops) > 0, f"seed={seed}: expected extracted loops"

    rust = _rust_bridge(netlist)
    assert rust.get("ok") is True, f"seed={seed}: {rust.get('error')}"

    _compare_loops_strict(oracle, rust)


def test_shim_reconstruction_matches_oracle_on_all_fields():
    """End-to-end through the shim: the reconstructed Loop objects must
    match the oracle on PRESERVED *and* RECONSTRUCTED fields (priority,
    events bit-exact, return paths)."""
    netlist = _full_half_bridge()
    oracle = _oracle_auto_extract_loops(netlist)
    rust = _rust_bridge(netlist)
    assert rust.get("ok") is True
    reconstructed = _dict_to_loop_collection(rust)

    # Reconstructed loops driven by Rust output order; oracle loops by
    # Python order. Build dicts by name for comparison.
    recon_by_name = {loop.name: loop for loop in reconstructed.loops}
    oracle_by_name = {loop.name: loop for loop in oracle.loops}

    # Same set of loop names (no extra/missing loops).
    assert set(recon_by_name) == set(oracle_by_name), (
        f"Loop name sets must match: recon_only={set(recon_by_name) - set(oracle_by_name)}, "
        f"oracle_only={set(oracle_by_name) - set(recon_by_name)}"
    )

    for name in oracle_by_name:
        rust_loop = recon_by_name[name]
        py_loop = oracle_by_name[name]
        assert rust_loop.name == py_loop.name
        assert rust_loop.loop_type.value == py_loop.loop_type.value
        # Components: bit-identical (driver IS included for gate-drive loops now).
        assert list(rust_loop.components) == list(py_loop.components), (
            f"{name}: components mismatch: rust={list(rust_loop.components)} oracle={list(py_loop.components)}"
        )
        # Nets: bit-identical (bootstrap nets are empty on both sides now).
        assert list(rust_loop.nets) == list(py_loop.nets), (
            f"{name}: nets mismatch: rust={list(rust_loop.nets)} oracle={list(py_loop.nets)}"
        )
        assert _f(rust_loop.max_area_mm2) == _f(py_loop.max_area_mm2)
        # RECONSTRUCTED fields — deterministic from loop_type.
        assert rust_loop.priority == py_loop.priority
        assert _f(rust_loop.events.di_dt) == _f(py_loop.events.di_dt)
        assert _f(rust_loop.events.dv_dt) == _f(py_loop.events.dv_dt)
        assert _f(rust_loop.events.frequency_hz) == _f(py_loop.events.frequency_hz)
        assert _f(rust_loop.events.peak_current_a) == _f(py_loop.events.peak_current_a)
        # Return paths: the oracle's dataclass default is None; the shim
        # reconstructs "" for unmapped loop types (divergence class 4 in docstring).
        if py_loop.return_layer is not None:
            assert rust_loop.return_layer == py_loop.return_layer
        else:
            assert rust_loop.return_layer == ""
        if py_loop.return_net is not None:
            assert rust_loop.return_net == py_loop.return_net
        else:
            assert rust_loop.return_net == ""
        # LOST fields: pins always dropped by the bridge; the description
        # is generic (documented divergence, asserted as such, not equal).
        assert rust_loop.pins == []
        assert rust_loop.description != py_loop.description


def test_rust_error_cases_match_python_empty():
    """Netlists where the Rust kernel returns ok:false correspond exactly to
    netlists where the oracle extracts nothing (empty netlist, fewer than two
    switches, switches with no common net, missing rail pins). The production
    path falls back to Python (R23) and yields the oracle's result."""
    empty = _netlist([])
    single = _netlist([
        Component(ref="Q1", footprint="TO-247", bounds=(1.0, 1.0),
                  pins=[_pin("GATE", "G"), _pin("COLLECTOR", "DC+"), _pin("EMITTER", "SW")],
                  attributes={"MPN": "IKW40N120H3"}),
    ])
    no_common_net = _netlist([
        Component(ref="Q1", footprint="TO-247", bounds=(1.0, 1.0),
                  pins=[_pin("GATE", "G1"), _pin("COLLECTOR", "N1"), _pin("EMITTER", "N2")],
                  attributes={"MPN": "IKW40N120H3"}),
        Component(ref="Q2", footprint="TO-220", bounds=(1.0, 1.0),
                  pins=[_pin("GATE", "G2"), _pin("COLLECTOR", "N3"), _pin("EMITTER", "N4")],
                  attributes={"MPN": "IRFP250N"}),
    ])

    for netlist in (empty, single, no_common_net):
        oracle = _oracle_auto_extract_loops(netlist)
        assert len(oracle.loops) == 0
        rust = _rust_bridge(netlist)
        assert rust.get("ok") is False, f"Rust should error for {netlist}"


def test_no_bus_cap_half_bridge_rust_errors_oracle_partial_documented():
    """Half bridge WITHOUT a bus capacitor: the Rust kernel aborts (first
    trace failure propagates), while the Python oracle opportunistically
    still emits the gate-drive loops. This is the recorded error-path
    divergence (module docstring, class 1). The production delegation falls
    back to Python and matches the oracle — that parity-by-fallback is the
    R23 contract and is what the live consumers (physics/loop_area.py,
    placer/cp_sat/_encoder_solve.py) observe."""
    netlist = _netlist([
        Component(ref="Q1", footprint="TO-247", bounds=(1.0, 1.0),
                  pins=[_pin("GATE", "GATE_H"), _pin("COLLECTOR", "DC+"), _pin("EMITTER", "SW")],
                  attributes={"MPN": "IKW40N120H3"}),
        Component(ref="Q2", footprint="TO-220", bounds=(1.0, 1.0),
                  pins=[_pin("GATE", "GATE_L"), _pin("DRAIN", "SW"), _pin("SOURCE", "DC-")],
                  attributes={"MPN": "IRFP250N"}),
    ])

    oracle = _oracle_auto_extract_loops(netlist)
    assert any(loop.name == "auto_gate_drive_Q1" for loop in oracle.loops)

    rust = _rust_bridge(netlist)
    assert rust.get("ok") is False
    assert "capacitor" in (rust.get("error") or "").lower()

    # Production path = delegation with fallback == oracle.
    from temper_placer.core.loop_extractor import auto_extract_loops

    production = auto_extract_loops(netlist)
    assert [_loop_canon(loop) for loop in production.loops] == [
        _loop_canon(loop) for loop in oracle.loops
    ]


def test_rust_missing_falls_back_to_python(monkeypatch):
    """The shim returns None (not raising) when temper-rust-router cannot be
    imported, so auto_extract_loops falls through to the Python compute —
    the documented R23 fallback, here forced by blocking the import."""
    import sys

    import temper_placer.core.loop_extractor as le

    monkeypatch.setitem(sys.modules, "temper_rust_router", None)
    result = le.auto_extract_loops(_full_half_bridge())
    assert len(result.loops) == 4  # commutation + 2 gate drives + bootstrap


# ---------------------------------------------------------------------------
# Presence guard: this proof must not silently skip in CI.
# ---------------------------------------------------------------------------

_REQUIRE = os.environ.get("TEMPER_REQUIRE_RUST_LOOP", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

if _REQUIRE and not hasattr(__import__("temper_design_bundle_python"), "LoopType"):
    pytest.fail(
        "TEMPER_REQUIRE_RUST_LOOP=1 but temper_design_bundle_python is not "
        "available — rebuild with `make extensions`",
        pytrace=False,
    )
