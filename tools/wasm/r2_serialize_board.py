#!/usr/bin/env python3
"""Board serialisation for the R2 full-board-pass benchmark AND the
router-free R8 producer (goal-set plan: "the board the tier checks is
regenerated from the committed placement, so the input changes when the
harness changes").

Parses ``pcb/temper.kicad_pcb`` via the KiCad parser and the Python→Rust
bridge, then calls ``temper_drc_rs.serialize_board_state`` to produce a
JSON snapshot the Rust example ``r2_full_board_pass`` can deserialise.
Also writes a constraints JSON.

By default (``--zone-source placement``), ``zones`` and the six
harness-sourced ``net_class_rules`` fields (creepage_mm, voltage_v,
max_current_rating, safety_category, required_layer, routing_strategy) are
RE-DERIVED from the committed placement (component/pad positions) and the
current harness (``temper_placer.core.design_rules``'s net-class SSOT) --
without invoking ``route_pcb()`` or reading any already-routed copper off
disk. ``components``/``nets``/``net_classes`` are the committed placement
itself (the input, not something to regenerate). ``traces``/``vias`` are
still read verbatim from committed copper -- deriving them without a SAT
router is not possible; see
``docs/evidence/2026-08-07-router-free-r8-producer.md`` for the exact
per-rule-kernel coverage boundary this implies.

Usage:
    uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json
    # Compare against the pre-R8 behaviour (committed zones, not regenerated):
    uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json --zone-source committed

Output (two files):
    <output>               — BoardState JSON (for r2_full_board_pass)
    <output>.constraints   — ConstraintSet JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def build_board_dict(
    parsed: Any,
    pads: list[Any] | None = None,
    *,
    zone_source: str = "placement",
) -> dict[str, Any]:
    """Build the K1-schema board dict consumed by the Rust bridge.

    R8 (goal-set plan, "the board the tier checks is regenerated from the
    committed placement, so the input changes when the harness changes"):
    ``zone_source`` selects how the ``zones`` key is produced.

    - ``"placement"`` (default): zones are RE-DERIVED from pad positions
      (the committed placement) plus the harness's net-class SSOT
      (``temper_placer.core.design_rules.TEMPER_NET_CLASSES``/
      ``TEMPER_NET_ASSIGNMENTS``), via ``_zones_from_placement`` --
      without invoking ``route_pcb()`` or reading any already-routed
      copper off disk. This is the router-free R8 producer path: the
      output changes when EITHER the placement changes (pads move) OR the
      harness changes (a net-class's ``routing_strategy``/``clearance``
      changes in ``design_rules.py``). See
      ``docs/evidence/2026-08-07-router-free-r8-producer.md``.
    - ``"committed"``: zones are re-serialized verbatim from the parsed
      board's already-routed zone geometry (``_zones_from_parsed``, the
      pre-existing behaviour). Kept for comparison/measurement, not the
      default -- using this path does NOT satisfy R8, since the zones
      never change unless the committed copper itself changes.

    ``pads`` (``ParseResult.pads``, from a separate ``parse_kicad_pcb(...,
    normalize=False)`` call -- ``ParsedPCB`` from ``parse_kicad_pcb_v6``
    does not carry pads) is required when ``zone_source="placement"``;
    ignored otherwise.

    Mirrors the logic in ``scripts/ci_closure_test.py`` and
    ``scripts/calibrate_drc_ceiling.py`` for components/nets/net_classes.

    Issue #873: those two scripts (and, until this change, this one) never
    populated the K1 schema's optional ``traces``/``vias``/``zones`` keys,
    so every routing-family DRC check driven by this producer ran against
    an empty board even though ``build_board_state``
    (``packages/temper-drc-rs/src/board_py_bridge.rs``) and ``BoardState``
    (``packages/temper-drc-rs/src/board.rs``) already fully support them —
    the gap was entirely in this bridge-side dict construction, not the
    Rust side. See ``_traces_from_parsed``/``_vias_from_parsed``/
    ``_zones_from_parsed`` below.

    Coordinate frame (discovered wiring zones in for the first time):
    ``parse_kicad_pcb_v6`` parses with ``normalize=False``, so
    ``parsed.components``/``.tracks``/``.vias`` come back in raw/absolute
    KiCad sheet coordinates (offset from the board by the Edge.Cuts origin
    -- 20mm/20mm on the committed board). ``parsed.zones``
    (``parsed.board.zones``) is different: ``extract_zones_pure`` in
    ``parse_engine.rs`` *always* subtracts that same origin, regardless of
    ``normalize``, so zone polygons already arrive in board-local
    ``[0, width_mm] x [0, height_mm]`` coordinates -- which is exactly what
    ``routing_copper_pullback`` (the only rule that reads
    ``board.width_mm``/``height_mm`` as an absolute frame) assumes. Rules
    that cross-reference zones against traces or components
    (``routing_split_plane_crossing``, ``drc_zone_containment``) instead
    need zones and the rest of the board in the *same* frame, whichever it
    is. Both constraints are satisfied at once by normalizing everything
    to board-local: components/traces/vias get the origin subtracted here
    (zones need no change, they are already local). An earlier version of
    this fix instead added the origin back onto zones to match components'
    raw frame -- that broke ``routing_copper_pullback``, which flagged 44
    real zones as exceeding the board-edge margin purely because they'd
    been shifted 20mm past a `[0, width_mm]` boundary that was never moved
    to match. Caught by re-running the routing family against the real
    board (see the R2 measurement in this change's evidence), not by
    inspection -- exactly the kind of spatially-wrong-but-present data this
    change is supposed to avoid.
    """
    ox, oy = parsed.board.origin

    # Single guarded harness-SSOT lookup, shared by three sub-steps below
    # (component-level safety reclassification, per-net class-name
    # override, and net_class_rules construction) -- guarded once here
    # rather than three times, and still a no-op import for fake-board
    # unit tests with no real nets/net-classes to enrich.
    harness_net_classes: dict[str, Any] = {}
    harness_net_assignments: dict[str, str] = {}
    if parsed.nets or parsed.design_rules.net_classes:
        from temper_placer.core.design_rules import (
            TEMPER_NET_ASSIGNMENTS as harness_net_assignments,
        )
        from temper_placer.core.design_rules import (
            TEMPER_NET_CLASSES as harness_net_classes,
        )

    harness_safety_classes = _harness_component_safety_classes(parsed, harness_net_assignments, harness_net_classes)
    components: list[dict[str, Any]] = []
    for c in parsed.components:
        raw_x, raw_y = c.initial_position or (0.0, 0.0)
        x, y = raw_x - ox, raw_y - oy
        rotation = (
            float(c.initial_rotation * 90)
            if c.initial_rotation is not None
            else 0.0
        )
        side = (
            "bottom"
            if c.initial_side is not None and c.initial_side == 1
            else "top"
        )
        fp_lower = c.footprint.lower() if c.footprint else ""
        if any(p in fp_lower for p in ("tht", "through", "pin", "dip")):
            package_type = "tht"
        elif "to-247" in fp_lower or "to247" in fp_lower:
            package_type = "to247"
        elif "to-220" in fp_lower or "to220" in fp_lower:
            package_type = "to220"
        elif "bga" in fp_lower:
            package_type = "bga"
        elif "qfn" in fp_lower:
            package_type = "qfn"
        elif "qfp" in fp_lower or "tqfp" in fp_lower:
            package_type = "qfp"
        elif "dpak" in fp_lower or "d2pak" in fp_lower:
            package_type = "dpak"
        else:
            package_type = "smd"

        is_mechanical = c.ref.startswith("MH")
        components.append(
            {
                "ref": c.ref,
                "x": x,
                "y": y,
                "rot": rotation,
                "side": side,
                "width": float(c.width),
                "height": float(c.height),
                "net_class": harness_safety_classes.get(c.ref, c.net_class),
                "package_type": package_type,
                "power_dissipation_w": None,
                "is_magnetic": False,
                "is_electrolytic": False,
                "is_mechanical": is_mechanical,
                "vent_direction": None,
                "footprint_polygon": None,
            }
        )

    nets: dict[str, list[str]] = {}
    net_classes: dict[str, str] = {}
    for net in parsed.nets:
        # dict.fromkeys, not a set: a set comprehension dedups but its
        # iteration order is hash-seed dependent, so this list differed
        # across processes and broke content-addressing (R5). dict
        # preserves first-encounter order and dedups identically.
        comp_refs = list(dict.fromkeys(ref for ref, _ in net.pins))
        nets[net.name] = comp_refs
        # Issue #873-adjacent gap, found while wiring R8: `net.net_class`
        # (the KiCad-declared class) is the single literal class
        # ("Signal") for every net on the production board -- confirmed
        # by direct parse, `parse_kicad_pcb_v6` never applies the
        # harness's per-net classification. `TEMPER_NET_ASSIGNMENTS` (the
        # harness SSOT `_zone_layers_for_net` already consults for zone
        # eligibility below) maps ~53 named nets to their real class
        # (ACMains/HighVoltage/GND/Power/...); preferring it here is what
        # makes a rule keyed on `board.nets[i].class` (e.g.
        # `high_current_net_names` in `rules/mod.rs`) see the harness's
        # real classification rather than "Signal" for every net.
        net_classes[net.name] = harness_net_assignments.get(net.name, net.net_class)

    # Issue #873-adjacent gap, continued: `net_class_rules` used to be
    # built ONLY by iterating `parsed.design_rules.net_classes` (the raw
    # KiCad-declared net-class blocks -- just {"Signal"} on the production
    # board, per `_extract_design_rules`'s own docstring: that extraction
    # is "vestigial", not authoritative), filling ONLY trace_width_mm/
    # clearance_mm and hardcoding every other field to None. Even after
    # `net_classes` above starts naming real harness classes like
    # "HighVoltage", there was no corresponding `net_class_rules["HighVoltage"]`
    # entry for the Rust bridge to look up -- `board.net_class_rules.get(&net.class)`
    # would still miss. Building from the harness SSOT directly (all 11
    # declared classes, not only the ones a `.kicad_pcb` net_class block
    # happens to mention) closes that gap and, same as before, makes this
    # dict a function of the *harness* (`design_rules.py`) as well as of
    # the committed board: editing a class's clearance/safety_category/
    # routing_strategy now changes this producer's output even with a
    # byte-identical `pcb/temper.kicad_pcb` -- R8's "input changes when the
    # harness changes" property. Any KiCad-declared class NOT in the
    # harness SSOT (there are none today, but the fallback is kept for
    # boards/classes the harness doesn't know about) keeps the prior
    # KiCad-declared-only, mostly-None behaviour.
    net_class_rules: dict[str, dict[str, Any]] = {}
    for class_name, harness in harness_net_classes.items():
        net_class_rules[class_name] = {
            "trace_width_mm": harness.trace_width,
            "clearance_mm": harness.clearance,
            "creepage_mm": harness.creepage_mm,
            "voltage_v": harness.voltage_v,
            "max_current_rating": harness.max_current_rating,
            "safety_category": harness.safety_category,
            "required_layer": harness.required_layer,
            "routing_strategy": harness.routing_strategy,
        }
    for class_name, rules in parsed.design_rules.net_classes.items():
        if class_name in net_class_rules:
            continue
        net_class_rules[class_name] = {
            "trace_width_mm": rules.trace_width_mm,
            "clearance_mm": rules.clearance_mm,
            "creepage_mm": None,
            "voltage_v": None,
            "max_current_rating": None,
            "safety_category": None,
            "required_layer": None,
            "routing_strategy": None,
        }

    if zone_source == "placement":
        if pads is None:
            raise ValueError(
                "build_board_dict(zone_source='placement') requires `pads` "
                "(ParseResult.pads, from a separate parse_kicad_pcb(..., "
                "normalize=False) call -- ParsedPCB.pads does not exist)."
            )
        ox, oy = parsed.board.origin
        pad_positions = _pad_positions_by_net(pads, ox, oy)
        zones = _zones_from_placement(pad_positions)
    elif zone_source == "committed":
        zones = _zones_from_parsed(parsed)
    else:
        raise ValueError(f"unknown zone_source {zone_source!r} (expected 'placement' or 'committed')")

    return {
        "board": {
            "width_mm": float(parsed.board.width),
            "height_mm": float(parsed.board.height),
            "margin_mm": 3.0,
        },
        "components": components,
        "nets": nets,
        "net_classes": net_classes,
        "net_class_rules": net_class_rules,
        "traces": _traces_from_parsed(parsed),
        "vias": _vias_from_parsed(parsed),
        "zones": zones,
    }


def _harness_component_safety_classes(
    parsed: Any,
    harness_net_assignments: dict[str, str],
    harness_net_classes: dict[str, Any],
) -> dict[str, str]:
    """Component ref -> harness safety reclassification (``"HighVoltage"``
    for any component with at least one pin on an HV- or AC-classified
    net), mirroring ``_apply_safety_classifications``'s severity-worst-case
    rule (``temper_placer/io/_parse_nets.py``: HV > AC > LV, ties toward
    the more severe class) but computed directly from the harness SSOT
    (``TEMPER_NET_ASSIGNMENTS``/``TEMPER_NET_CLASSES``, passed in already
    resolved by ``build_board_dict`` -- see its own comment for why the
    import is guarded there) over ``parsed.nets``' pin membership, rather
    than depending on ``parsed.design_rules`` -- which
    ``_extract_design_rules`` documents as **vestigial**, not authoritative
    ("The authoritative source is ``configs/netclass_rules.yaml``...
    injected into the pipeline by ``route_pcb()``" -- exactly the call
    this task must not make).

    Found while wiring R8: ``parse_kicad_pcb_v6`` never calls
    ``_apply_safety_classifications`` (it has no ``design_rules`` argument
    to pass), so every component this producer has ever emitted carries
    whatever KiCad literally declared as its net class -- on the
    production board, verified, that is the single literal class
    ``"Signal"`` for every net and every component, regardless of whether
    it is tied to mains voltage or a 3.3V logic rail. Every net-class-keyed
    DRC/safety kernel this producer feeds (``safety_hv_lv_separation``,
    ``safety_creepage``, ``safety_isolation``, ``drc_zone_containment``)
    was therefore silently vacuous on this producer's output -- structurally
    unable to ever see an HV-classified component -- independent of
    routing and independent of this change's zone-geometry work.
    """
    severity_order = {"HV": 3, "AC": 2, "LV": 1}
    best_severity: dict[str, int] = {}
    for net in parsed.nets:
        nc = harness_net_classes.get(harness_net_assignments.get(net.name, ""))
        if nc is None or nc.safety_category not in severity_order:
            continue
        sev = severity_order[nc.safety_category]
        for ref, _pin_name in net.pins:
            if sev > best_severity.get(ref, 0):
                best_severity[ref] = sev
    # Matches _apply_safety_classifications's severity_to_class: HV(3) and
    # AC(2) both collapse to "HighVoltage"; LV(1)/unclassified keep the
    # existing (KiCad-declared) class untouched.
    return {ref: "HighVoltage" for ref, sev in best_severity.items() if sev >= 2}


def _traces_from_parsed(parsed: Any) -> list[dict[str, Any]]:
    """Convert ``parsed.tracks`` (``ParsedPCB.tracks``, one entry per raw
    KiCad ``segment`` record) into the K1 ``traces`` schema, grouped by
    ``(net, layer)`` — every segment on the same net and layer becomes one
    ``{net, layer, width, segments}`` entry holding all of that net's line
    segments on that layer.

    Grouping (not a 1:1 segment-to-entry mapping) is required for
    correctness, not just convenience: ``drc_trace_clearance``
    (``packages/temper-drc-rs/src/rules/drc/trace_clearance.rs``) computes
    pairwise clearance *across* ``board.traces`` entries but never *within*
    one entry's own ``segments`` list — that is the schema's implicit
    contract for what one entry means (an already-mutually-compatible
    group). A first version of this function emitted one entry per raw
    KiCad segment; two consecutive segments of the same physical route
    share an endpoint by construction (that is what makes them one
    connected track), so the clearance check saw them as two different
    "traces" of the same net touching at distance 0mm and flagged each
    junction as a same-net clearance violation — 2,911 of them on the
    committed board, none real (verified: every sampled violation was a
    net compared against itself at ~0mm, exactly the connected-segment
    junction pattern, not a real proximity issue between distinct
    routes). Grouping by ``(net, layer)`` removes that whole class of
    false positives while still checking genuinely distinct
    nets/layers against each other, and preserves the *total* segment
    count exactly (``sum(len(t["segments"]) for t in traces) == len
    (parsed.tracks)``) — the invariant the "N segments in -> N segments in
    BoardState" bridge test checks, since grouping only changes which
    top-level entry a segment lands in, never whether it lands at all.

    ``width`` is taken from the first segment encountered per (net, layer)
    group (a track's width is occasionally not perfectly uniform end to
    end in KiCad, e.g. at a taper); this is an approximation, not exact
    per-segment width tracking, which the K1 schema's per-entry (not
    per-segment) ``width`` field does not support.

    Coordinate frame: ``parsed.tracks`` comes back in raw/absolute KiCad
    coordinates (``parse_kicad_pcb_v6`` parses with ``normalize=False``).
    The board-origin correction is applied here to land in the same
    board-local frame as ``_zones_from_parsed`` and the (also corrected)
    components loop in ``build_board_dict`` — see that function's
    docstring for why all of components/traces/vias/zones must share one
    frame, and why that frame has to be board-local rather than raw.

    Grouping uses a plain ``dict`` keyed by ``(net, layer)``, built by
    iterating ``parsed.tracks`` in its already-deterministic list order
    (the parser's own output order, not a set/hash-ordered structure).
    Python ``dict`` insertion order is guaranteed since 3.7 and is NOT the
    frozenset/HashMap-iteration-order hazard recorded in
    ``docs/evidence/2026-08-07-r3-frozenset-order-verification.md`` — that
    caveat is about ``set``/``frozenset`` (and Rust ``HashMap``)
    iteration, not ``dict`` insertion order.
    """
    ox, oy = parsed.board.origin
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for t in parsed.tracks:
        net = t.net or ""
        key = (net, t.layer)
        entry = groups.get(key)
        if entry is None:
            entry = {"net": net, "layer": t.layer, "width": float(t.width), "segments": []}
            groups[key] = entry
        x1, y1 = t.start
        x2, y2 = t.end
        entry["segments"].append(
            [float(x1) - ox, float(y1) - oy, float(x2) - ox, float(y2) - oy]
        )
    return list(groups.values())


def _vias_from_parsed(parsed: Any) -> list[dict[str, Any]]:
    """Convert ``parsed.vias`` (``ParsedPCB.vias``, ``ViaData``) into the
    K1 ``vias`` schema (``{net, x, y, drill, pad, from_layer, to_layer}``,
    consumed by ``extract_via`` in ``board_py_bridge.rs``).

    Same board-local coordinate-frame correction as ``_traces_from_parsed``.
    """
    ox, oy = parsed.board.origin
    out: list[dict[str, Any]] = []
    for v in parsed.vias:
        x, y = v.position
        layers = tuple(v.layers) if v.layers else ("F.Cu", "B.Cu")
        out.append(
            {
                "net": v.net or "",
                "x": float(x) - ox,
                "y": float(y) - oy,
                "drill": float(v.drill),
                "pad": float(v.diameter),
                "from_layer": layers[0],
                "to_layer": layers[-1],
            }
        )
    return out


def _zones_from_parsed(parsed: Any) -> list[dict[str, Any]]:
    """Convert ``parsed.zones`` (== ``parsed.board.zones``, the generic
    placement ``Zone`` dataclass reused by the KiCad copper-zone parse path
    -- see ``build_board`` in ``parse_engine.rs``) into the K1 ``zones``
    schema (``{net, layer, polygon}``, one entry per zone-layer pair, since
    ``CopperZone`` on the Rust side is single-layer while a KiCad zone can
    declare multiple layers).

    ``zone.net_classes[0]`` is the zone's net name despite the field name
    (the KiCad-zone code path repurposes the placement ``Zone``'s
    ``net_classes`` field to carry the actual net name; it defaults to the
    literal string ``"Signal"`` when the zone record had no net).

    No coordinate correction needed: ``extract_zones_pure`` in
    ``parse_engine.rs`` *always* subtracts the board's Edge.Cuts origin
    from zone polygon points regardless of the ``normalize`` flag, so
    ``z.polygon`` already arrives in board-local ``[0, width_mm] x
    [0, height_mm]`` coordinates — see ``build_board_dict``'s docstring for
    why that (not raw/absolute) is the frame the whole board_dict must
    share, and why zones are the anchor rather than components/traces/vias.
    """
    out: list[dict[str, Any]] = []
    for z in parsed.zones:
        if not z.polygon:
            continue
        net = z.net_classes[0] if z.net_classes else ""
        polygon = [[float(x), float(y)] for x, y in z.polygon]
        layers = z.layers if z.layers else ["F.Cu"]
        for layer in layers:
            out.append({"net": net, "layer": layer, "polygon": polygon})
    return out


def _pad_positions_by_net(
    pads: list[Any], ox: float, oy: float
) -> dict[str, list[tuple[float, float]]]:
    """Group raw pad positions (``ParseResult.pads``, ``PadData`` objects --
    NOT ``ParsedPCB.pads``, which does not exist; see ``main()``) by net
    name, in the same board-local frame as components/traces/vias/zones
    (``build_board_dict``'s docstring).

    ``PadData.position`` comes back as a raw/absolute ``(x, y)`` tuple
    regardless of the ``normalize`` flag passed to ``parse_kicad_pcb``
    (``extract_pads_pure`` in ``parse_engine.rs`` never receives
    ``origin_to_use``) -- same frame as components'/traces'/vias' raw
    coordinates, so the same origin subtraction applies here.

    Pads with no net (``p.net`` is ``None`` or ``""``) are skipped -- an
    unconnected pad contributes no zone/pour geometry, matching the shape
    of the ``pad_positions: dict[str, list[tuple[float, float]]]``
    parameter ``_emit_zone_pours``/``_stitch_isolated_pads`` expect in
    ``router_v6/_zone_pour_stitch.py``.
    """
    out: dict[str, list[tuple[float, float]]] = {}
    for p in pads:
        net = p.net
        if not net:
            continue
        x, y = p.position
        out.setdefault(net, []).append((float(x) - ox, float(y) - oy))
    return out


def _zones_from_placement(
    pad_positions: dict[str, list[tuple[float, float]]],
) -> list[dict[str, Any]]:
    """Re-derive zone/pour geometry from the committed *placement* (pad
    positions, grouped by net) and the harness's net-class SSOT
    (``temper_placer.core.design_rules.TEMPER_NET_CLASSES``/
    ``TEMPER_NET_ASSIGNMENTS``), WITHOUT invoking ``route_pcb()`` or the SAT
    router, and without reading any already-routed copper off disk.

    This is the R8 producer path (goal-set plan: "the board the tier checks
    is regenerated from the committed placement, so the input changes when
    the harness changes" -- see
    ``docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md`` §4 and
    ``docs/evidence/2026-08-07-router-free-r8-producer.md``).

    Reuses the *exact* zone-eligibility and clustering logic the SAT
    router's own zone-emission stage uses --
    ``_zone_layers_for_net``/``_zone_params_for_net``/
    ``_CONTINUITY_EXEMPT_CLASSES`` (``router_v6/_zone_pour_stitch.py``) and
    ``compute_zones_for_net`` (``router_v6/zone_emission.py``, convex hull
    + hierarchical clustering over pad positions). None of these four call
    ``route_pcb()`` or the CP-SAT/SAT solver -- confirmed by reading them:
    they are pure geometry (shapely/scipy) plus a dict lookup into the
    net-class SSOT. Reusing the production functions (rather than
    reimplementing the eligibility/clustering rules a second time) is what
    keeps this producer's zones representative of what the router would
    actually pour, not an independent approximation that could silently
    drift from it.

    Deliberately does NOT read ``parsed.zones`` (the already-routed zone
    polygons committed on disk) -- doing so would make the artifact
    re-serialize committed output rather than regenerate it, exactly the
    gap the status audit identified. The output changes when EITHER the
    placement changes (pad positions move, changing the convex hulls) OR
    the harness changes (a class's ``routing_strategy``/``clearance`` is
    edited in ``design_rules.py``, changing which nets get zones and how
    large they are) -- both are exercised in
    ``test_r2_serialize_board.py`` and in the evidence doc's determinism/
    harness-sensitivity checks.

    ``net_number`` (the ``ZoneDefinition``/``compute_zones_for_net``
    parameter, not part of the K1 zones schema this function returns) has
    no KiCad-assigned value available here -- ``Net`` (the pyo3 netlist
    pyclass) carries no ``.number`` field, only ``name``/``pins``/
    ``net_class``/etc. A synthetic 1-based index over ``sorted(net names)``
    is used instead: deterministic (string sort, no hash-seed dependency,
    unlike a set), and harmless since ``compute_zones_for_net`` only uses
    it to require ``> 0`` and to stamp the (unused, discarded)
    ``ZoneDefinition.net_number`` field -- it never reaches this
    function's output.
    """
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
    from temper_placer.router_v6._zone_pour_stitch import (
        _CONTINUITY_EXEMPT_CLASSES,
        _zone_layers_for_net,
        _zone_params_for_net,
    )
    from temper_placer.router_v6.zone_emission import compute_zones_for_net

    out: list[dict[str, Any]] = []
    for net_num, net_name in enumerate(sorted(pad_positions), start=1):
        zone_layers = _zone_layers_for_net(net_name)
        if not zone_layers:
            continue
        positions = pad_positions[net_name]
        if not positions:
            continue
        nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
        exempt = nc in _CONTINUITY_EXEMPT_CLASSES
        margin, _clearance = _zone_params_for_net(net_name)
        for layer in zone_layers:
            try:
                zds = compute_zones_for_net(
                    net_name,
                    net_num,
                    positions,
                    layer=layer,
                    margin=margin,
                    cluster=not exempt,
                )
            except ValueError:
                # compute_zones_for_net raises on an empty pad list; this
                # net's positions were already checked non-empty above, but
                # the per-cluster hull step can still degenerate (e.g. a
                # single cluster of coincident points) -- skip, matching
                # _emit_zone_pours's own try/except ValueError: pass.
                continue
            for zd in zds:
                out.append(
                    {
                        "net": zd.net_name,
                        "layer": zd.layer,
                        "polygon": [[float(x), float(y)] for x, y in zd.points],
                    }
                )
    return out


def _zone_eligible_class_names() -> list[str]:
    """Net-class names the harness SSOT marks zone-eligible
    (``routing_strategy == "plane_required"``), in a deterministic
    (sorted) order. Used to populate ``ConstraintSet.zones`` (see
    ``build_constraints_dict``) so ``drc_zone_containment`` -- which is
    gated on ``constraints.zones``, not ``board.zones`` directly -- has a
    real, non-vacuous input instead of the permanently-empty list every
    prior producer left it. Scoped deliberately to *this one* mechanical
    fact (which classes get zone/pour treatment): synthesizing keyword-
    matched "ground"/"isolation" constraint zones (which
    ``emc_ground_plane``/``safety_isolation``/``routing_isolation_slot``
    also read) would require guessing at role semantics the harness does
    not declare anywhere -- see the evidence doc's coverage boundary.
    """
    from temper_placer.core.design_rules import TEMPER_NET_CLASSES

    return sorted(
        name
        for name, rules in TEMPER_NET_CLASSES.items()
        if rules.routing_strategy == "plane_required"
    )


def build_constraints_dict(parsed: Any) -> dict[str, Any]:
    """Build a minimal ConstraintSet dict matching the Rust serde schema.

    ``zones`` is populated from the harness's zone-eligible net classes
    (see ``_zone_eligible_class_names``) -- one ``ZoneDefinition`` per
    class, named after the class itself, so ``drc_zone_containment`` can
    check real components against real ``board.zones`` polygons instead of
    silently no-op'ing on an empty constraint list (as every prior producer
    run did, independent of routing). ``critical_loops``/
    ``isolation_barriers`` remain empty -- no harness table maps a critical
    loop's net names or an isolation barrier's board-space line to source
    data this producer can read without guessing; see the evidence doc.
    """
    zone_classes = _zone_eligible_class_names()
    return {
        "clearances": [],
        "zones": [{"name": c, "net_classes": [c]} for c in zone_classes],
        "critical_loops": [],
        "noise_domains": [],
        "isolation_barriers": [],
        "thermal_properties": [],
        "matched_length_groups": [],
        "snubber_requirements": [],
        "bleed_resistor": None,
        "skin_effect_derating": None,
        "hv_clearance_mm": 10.0,
        "board_width": float(parsed.board.width),
        "board_height": float(parsed.board.height),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serialize production board for R2 cost-model benchmark"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the BoardState JSON (constraints written to <output>.constraints)",
    )
    parser.add_argument(
        "--pcb",
        default="pcb/temper.kicad_pcb",
        help="Path to the KiCad PCB file (default: pcb/temper.kicad_pcb)",
    )
    parser.add_argument(
        "--zone-source",
        choices=["placement", "committed"],
        default="placement",
        help=(
            "'placement' (default, R8): re-derive zones from pad positions "
            "+ the harness net-class SSOT, without route_pcb(). 'committed': "
            "re-serialize the already-routed zone polygons verbatim (does "
            "NOT satisfy R8 -- kept for comparison/measurement only)."
        ),
    )
    args = parser.parse_args()

    # --- path setup --------------------------------------------------------
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))

    # --- parse PCB ---------------------------------------------------------
    from temper_placer.io.kicad_parser import parse_kicad_pcb, parse_kicad_pcb_v6  # noqa: E402

    pcb_path = repo_root / args.pcb
    print(f"Parsing {pcb_path} ...", file=sys.stderr)
    parsed = parse_kicad_pcb_v6(str(pcb_path))
    print(
        f"  components: {len(parsed.components)}  nets: {len(parsed.nets)}",
        file=sys.stderr,
    )

    # ParsedPCB (parse_kicad_pcb_v6's return type) does not carry `.pads` --
    # only the legacy ParseResult does. A second parse call is the cheapest
    # way to reach them without widening ParsedPCB's shared dataclass (used
    # far beyond this script) for one producer's benefit. normalize=False
    # matches parse_kicad_pcb_v6's own internal call, so pad positions land
    # in the same raw/absolute frame as components/traces/vias (see
    # _pad_positions_by_net's docstring).
    pads: list[Any] = []
    if args.zone_source == "placement":
        pads_result = parse_kicad_pcb(pcb_path, normalize=False)
        pads = list(pads_result.pads)
        print(f"  pads: {len(pads)}", file=sys.stderr)

    # --- build board dict -------------------------------------------------
    board_dict = build_board_dict(parsed, pads, zone_source=args.zone_source)
    print(
        f"  zones ({args.zone_source}): {len(board_dict['zones'])}",
        file=sys.stderr,
    )

    # --- serialise via Rust bridge ----------------------------------------
    import temper_drc_rs  # type: ignore[import-untyped]  # noqa: E402

    board_json_str = temper_drc_rs.serialize_board_state(board_dict)
    constraints_dict = build_constraints_dict(parsed)

    # --- write ------------------------------------------------------------
    out = Path(args.output)
    out.write_text(board_json_str, encoding="utf-8")
    print(f"Wrote BoardState JSON → {out}  ({len(board_json_str):,} bytes)", file=sys.stderr)

    constraints_out = out.with_suffix(out.suffix + ".constraints")
    constraints_out.write_text(json.dumps(constraints_dict), encoding="utf-8")
    print(f"Wrote ConstraintSet JSON → {constraints_out}", file=sys.stderr)

    # --- hashes (for evidence doc) -----------------------------------------
    import hashlib

    board_bytes = pcb_path.read_bytes()
    input_hash = hashlib.sha256(board_bytes).hexdigest()
    artifact_hash = hashlib.sha256(board_json_str.encode("utf-8")).hexdigest()
    print(f"\nInput pcb/temper.kicad_pcb sha256:  {input_hash}", file=sys.stderr)
    print(f"Output BoardState JSON sha256:      {artifact_hash}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
