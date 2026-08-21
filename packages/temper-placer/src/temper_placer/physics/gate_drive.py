"""
Gate-drive-loop trace-geometry measurement (``PhysicsGate`` sub-check 2).

``placer/cp_sat/gates.py::PhysicsGate.check()`` sub-check 2 ("Gate-drive
tightness", ``@req(2026-07-08-005, R2)``) has always imported
``gate_drive_loop_area`` / ``gate_drive_spacing`` from
``temper_placer.physics.gate_drive`` -- this module. It never existed
until now, so every call fell through the ``try/except ImportError`` and
the sub-check has always reported ``UNMEASURED`` (see
``docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md``,
Priority 1, item 3, and
``docs/evidence/2026-08-17-gate-drive-loop-inductance-check.md``).

Contract (fixed by the caller -- ``gates.py`` is unmodified except for the
net-name SSOT correction documented in the evidence doc)::

    gate_drive_loop_area(pcb: Path, gate_net: str) -> float | None
    gate_drive_spacing(pcb: Path, gate_net: str) -> float | None

Both return ``None`` on measurement failure -- fail-closed, never a false
0.0/"clean" (mirrors ``physics/loop_area.py::commutation_loop_area``'s own
contract for sub-check 1).

Design plan intent vs. what is actually reachable on the real board
---------------------------------------------------------------------
The originating plan (``docs/plans/2026-07-08-005-...``, R2) assumed the
gate-drive loop's topology could be read off
``core/loop_extractor.py::trace_gate_drive_loop``/``auto_extract_loops``,
which in turn depends on ``find_power_switches``/``classify_component``.
That machinery is **structurally unreachable on this real board** for two
independent reasons, both confirmed by direct inspection, not assumed:

1. ``classify_component`` only classifies a component as ``power_switch``
   when its reference starts with ``"Q"``. On the real board the
   half-bridge power switches are ``U4`` (high side) / ``U5`` (low side)
   -- both ``Package_TO_SOT_THT:TO-247-3_Vertical`` -- while ``Q1``/``Q2``
   are unrelated small-signal ``SOT-23`` transistors (a relay driver and a
   discharge driver). ``find_power_switches`` therefore returns nothing
   useful on this board.
2. Even disregarding (1), ``get_pin_net(component, ["GATE", "G"])`` keys
   off a functional pin *name*. A ``Netlist`` built by
   ``io.kicad_parser.parse_kicad_pcb`` (the only netlist available for a
   routed board) populates ``Pin.name`` from the **pad number** (KiCad's
   ``.kicad_pcb`` layout format carries no schematic pin-function data) --
   there is no pin literally named ``"GATE"`` to find. This is the same
   root cause already documented for sub-check 1 in
   ``docs/evidence/2026-08-11-loop-area-cycle-basis-order-spike.md``
   (`auto_extract_loops` finds zero loops of any type on the real board).

Given that, this module does **not** use ``loop_extractor``/
``classify_component`` at all. It re-derives just enough topology directly
from the parsed board's pad-to-net connectivity to find the switch and the
gate loop's return net, generically (no hardcoded reference designators):

  * The "go" side starts at ``gate_net`` (the driver-output net named by
    ``PhysicsGate._GATE_NETS``) and extends through any 2-pad, ``R``/``L``
    -prefixed passive (a series gate resistor/ferrite) whose other pad
    sits on a new net -- this generically bridges the driver-side net to
    the device-side net where a series gate resistor splits them (as is
    the case for the real board's high-side loop: ``GATE_HS`` --[R18]--
    ``hb.power_loop.q_high-g``).
  * The walk stops the moment it reaches a net touched by a component
    whose footprint name contains ``TO-247``/``TO-220``/``TO-263`` -- the
    same package-based signal ``classify_component`` already uses for
    power-switch detection, just without that function's incorrect
    ``ref.startswith("Q")`` prerequisite (which is demonstrably false on
    this board, see above). That component is the switch.
  * The "return" side is chosen from the switch's own remaining pads:
    prefer a net whose name contains ``gnd``/``rtn``/``ground``/``return``
    (case-insensitive; the near-universal EE naming convention for a
    reference/return net); if none match, fall back to the unique
    remaining net that is not a fixed-supply-rail name (does not start
    with ``"+"``); otherwise the return net is ambiguous and measurement
    fails closed (``None``).

This is a from-scratch interpretation adopted because the plan's own
"topology from the netlist" approach does not execute on this board's
actual data. It is deliberately conservative: any ambiguity (more than
one candidate switch, more than one candidate return net, a walk that
does not terminate within a small hop bound) returns ``None`` rather than
guessing.

Loop area and spacing are computed exactly like sub-check 1's
implementation (``physics/loop_area.py``) and its own precedent in
``validation/trace_analyzer.py``: convex-hull area over the combined
endpoint set (``temper_geometry.convex_hull_area_py``, Rust QuickHull) and
the minimum trace endpoint-pair distance between the go/return arms
(``temper_drc_rs.min_hv_lv_trace_clearance``, the same kernel and the same
endpoint-pair approximation already used in production for the
HV/LV-clearance metric -- not a true segment-to-segment distance; that
approximation is pre-existing production precedent, not introduced here).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Netlist

_MAX_FORWARD_HOPS = 4
_SWITCH_FOOTPRINT_MARKERS: tuple[str, ...] = ("TO-247", "TO-220", "TO-263")
_RETURN_NAME_MARKERS: tuple[str, ...] = ("gnd", "rtn", "ground", "return")
_FORWARD_PASSIVE_REF_PREFIXES: tuple[str, ...] = ("R", "L")


class _TraceLike(Protocol):
    """Minimal trace interface accepted by the area/spacing helpers."""

    start: tuple[float, float]
    end: tuple[float, float]
    net: str | None


# ---------------------------------------------------------------------------
# Public entry points (the exact contract PhysicsGate.check() imports)
# ---------------------------------------------------------------------------


def gate_drive_loop_area(routed_pcb_path: Path, gate_net: str) -> float | None:
    """Convex-hull area (mm²) of the gate-drive loop for ``gate_net``.

    ``gate_net`` is the driver-output net name (e.g. ``"GATE_HS"``). The
    device-side net and the return net are resolved automatically (see
    module docstring). Returns ``None`` if any part of the measurement
    cannot be performed -- the gate must report ``UNMEASURED``, never a
    false 0.0.
    """
    resolved = _resolve_gate_loop(routed_pcb_path, gate_net)
    if resolved is None:
        return None
    go_traces, return_traces = resolved
    if not go_traces or not return_traces:
        return None
    return _hull_area(go_traces, return_traces)


def gate_drive_spacing(routed_pcb_path: Path, gate_net: str) -> float | None:
    """Minimum edge-to-edge spacing (mm) between the gate-drive "go" traces
    and their resolved return-path traces for ``gate_net``.

    Same resolution and fail-closed semantics as
    :func:`gate_drive_loop_area`.
    """
    resolved = _resolve_gate_loop(routed_pcb_path, gate_net)
    if resolved is None:
        return None
    go_traces, return_traces = resolved
    if not go_traces or not return_traces:
        return None
    return _min_spacing(go_traces, return_traces)


# ---------------------------------------------------------------------------
# Resolution: pcb -> (go_traces, return_traces)
# ---------------------------------------------------------------------------


def _resolve_gate_loop(
    routed_pcb_path: Path, gate_net: str
) -> tuple[list[_TraceLike], list[_TraceLike]] | None:
    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb
    except ImportError:
        return None

    try:
        result = parse_kicad_pcb(routed_pcb_path)
    except Exception:
        return None

    netlist = result.netlist
    trace_data: list[_TraceLike] = list(result.traces)

    walked = _walk_forward(netlist, gate_net)
    if walked is None:
        return None
    forward_nets, switch = walked

    return_net = _pick_return_net(switch, forward_nets)
    if return_net is None:
        return None

    go_traces = [t for t in trace_data if t.net in forward_nets]
    return_traces = [t for t in trace_data if t.net == return_net]
    return go_traces, return_traces


def _walk_forward(
    netlist: Netlist, gate_net: str
) -> tuple[set[str], Component] | None:
    """Walk from ``gate_net`` through series passives to the switch.

    Returns ``(forward_nets, switch_component)`` or ``None`` if no unique
    switch is found within the hop bound.
    """
    forward_nets: set[str] = {gate_net}
    visited_components: set[str] = set()

    for _ in range(_MAX_FORWARD_HOPS):
        switch = _find_switch(netlist, forward_nets)
        if switch is not None:
            return forward_nets, switch

        # Extend by exactly one hop per outer iteration: evaluate every
        # candidate against a snapshot of forward_nets taken BEFORE any of
        # this iteration's extensions are applied. Mutating forward_nets
        # in place while scanning components would let a second passive
        # (e.g. a gate-to-return pulldown resistor sitting on the
        # device-side net) chain onto the first hop's newly-added net in
        # the same pass, before the switch check ever re-runs against the
        # intermediate state -- silently pulling the return-path net into
        # the "go" side. Re-checking for the switch between every single
        # hop is what lets the walk stop at the real switch instead of
        # wandering onto its return-path pulldown.
        current_nets = frozenset(forward_nets)
        new_nets: set[str] = set()
        newly_visited: set[str] = set()
        for component in netlist.components:
            if component.ref in visited_components:
                continue
            if len(component.pins) != 2:
                continue
            if not component.ref.upper().startswith(_FORWARD_PASSIVE_REF_PREFIXES):
                continue
            pin_nets = {p.net for p in component.pins if p.net}
            if len(pin_nets) != 2:
                continue
            overlap = pin_nets & current_nets
            if len(overlap) == 1:
                # pin_nets has exactly 2 nets and exactly one overlaps
                # current_nets, so the difference has exactly one element;
                # sort it to avoid PYTHONHASHSEED-dependent set iteration.
                new_net = sorted(pin_nets - current_nets)[0]
                new_nets.add(new_net)
                newly_visited.add(component.ref)

        if not new_nets:
            return None

        forward_nets |= new_nets
        visited_components |= newly_visited

    return None


def _find_switch(netlist: Netlist, forward_nets: set[str]) -> Component | None:
    """Find the unique switch (by package footprint) touching ``forward_nets``.

    Returns ``None`` if no switch is found, or if more than one candidate
    is found (ambiguous -- fail closed rather than guess).
    """
    candidates: list[Component] = []
    for component in netlist.components:
        pin_nets = {p.net for p in component.pins if p.net}
        if not (pin_nets & forward_nets):
            continue
        footprint = (component.footprint or "").upper()
        if any(marker in footprint for marker in _SWITCH_FOOTPRINT_MARKERS):
            candidates.append(component)

    if len(candidates) == 1:
        return candidates[0]
    return None


def _pick_return_net(switch: Component, forward_nets: set[str]) -> str | None:
    """Pick the switch's return/reference net from its remaining pads."""
    other_nets = {p.net for p in switch.pins if p.net and p.net not in forward_nets}
    if not other_nets:
        return None

    # Iterate in sorted order: `other_nets` is a set whose iteration order is
    # PYTHONHASHSEED-dependent, and `named`/`non_supply` feed index-based picks.
    named = [
        n
        for n in sorted(other_nets)
        if any(m in n.lower() for m in _RETURN_NAME_MARKERS)
    ]
    if len(named) == 1:
        return named[0]
    if len(named) > 1:
        return None

    non_supply = [n for n in sorted(other_nets) if not n.startswith("+")]
    if len(non_supply) == 1:
        return non_supply[0]
    return None


# ---------------------------------------------------------------------------
# Geometry (Rust kernels, matching physics/loop_area.py's precedent)
# ---------------------------------------------------------------------------


def _hull_area(go_traces: list[_TraceLike], return_traces: list[_TraceLike]) -> float | None:
    points: set[tuple[float, float]] = set()
    for t in (*go_traces, *return_traces):
        points.add((round(t.start[0], 3), round(t.start[1], 3)))
        points.add((round(t.end[0], 3), round(t.end[1], 3)))

    if len(points) < 3:
        return None

    import temper_geometry

    flat: list[float] = [c for p in sorted(points) for c in (float(p[0]), float(p[1]))]
    try:
        return float(temper_geometry.convex_hull_area_py(flat))
    except Exception:
        return None


def _min_spacing(go_traces: list[_TraceLike], return_traces: list[_TraceLike]) -> float | None:
    if not go_traces or not return_traces:
        return None

    import temper_drc_rs

    go = [(float(t.start[0]), float(t.start[1]), float(t.end[0]), float(t.end[1])) for t in go_traces]
    ret = [(float(t.start[0]), float(t.start[1]), float(t.end[0]), float(t.end[1])) for t in return_traces]
    try:
        value = float(temper_drc_rs.min_hv_lv_trace_clearance(go, ret))
    except Exception:
        return None

    if value == float("inf"):
        return None
    return value
