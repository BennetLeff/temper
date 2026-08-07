#!/usr/bin/env python3
"""One-time board serialisation for the R2 full-board-pass benchmark.

Parses ``pcb/temper.kicad_pcb`` via the KiCad parser and the Python→Rust
bridge, then calls ``temper_drc_rs.serialize_board_state`` to produce a
JSON snapshot the Rust example ``r2_full_board_pass`` can deserialise.
Also writes a constraints JSON (``ConstraintSet::default()``).

Usage:
    uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json

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


def build_board_dict(parsed: Any) -> dict[str, Any]:
    """Build the K1-schema board dict consumed by the Rust bridge.

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
                "net_class": c.net_class,
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
        comp_refs = list({ref for ref, _ in net.pins})
        nets[net.name] = comp_refs
        net_classes[net.name] = net.net_class

    net_class_rules: dict[str, dict[str, Any]] = {}
    for class_name, rules in parsed.design_rules.net_classes.items():
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
        "zones": _zones_from_parsed(parsed),
    }


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


def build_constraints_dict(parsed: Any) -> dict[str, Any]:
    """Build a minimal ConstraintSet dict matching the Rust serde schema."""
    return {
        "clearances": [],
        "zones": [],
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
    args = parser.parse_args()

    # --- path setup --------------------------------------------------------
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))

    # --- parse PCB ---------------------------------------------------------
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6  # noqa: E402

    pcb_path = repo_root / args.pcb
    print(f"Parsing {pcb_path} ...", file=sys.stderr)
    parsed = parse_kicad_pcb_v6(str(pcb_path))
    print(
        f"  components: {len(parsed.components)}  nets: {len(parsed.nets)}",
        file=sys.stderr,
    )

    # --- build board dict -------------------------------------------------
    board_dict = build_board_dict(parsed)

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

    # --- board hash (for evidence doc) ------------------------------------
    import hashlib

    board_bytes = pcb_path.read_bytes()
    board_hash = hashlib.sha256(board_bytes).hexdigest()
    print(f"\nBoard sha256: {board_hash}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
