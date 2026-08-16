"""Verbatim pre-migration oracle for the Phase E batch E6 pipeline-adapter
orchestration (Rust Orchestration Engine plan 2026-08-09-001, Phase E E6).

This file is a byte-exact snapshot of the ORCHESTRATION bodies of
``router_v6/_adapter_convert.py`` AS COMMITTED at the dispatch base
(origin/main cfc9415c1), extracted verbatim (AST ranges):

- ``_next_tstamp`` -- the deterministic KiCad ``tstamp`` UUIDv5 sequence
- ``_to_stage0_netclass_rules`` -- the netclass SSOT->stage0 conversion
  boundary (explicit attribute checking, the unrepresented-field warnings)
- ``_write_routes_to_content`` -- the routing-result -> ``.kicad_pcb``
  content writer (the segment/via emission core the E6 Rust port drives)

The rest of ``_adapter_convert.py`` (``route_pcb`` / ``_build_routing_result`` /
``_apply_placements_to_pcb`` / ``_reorient_pads_in_footprint_block``) stays
Python in the shim -- the pipeline-invocation glue, the failure-extraction
assembly and the ``re``-based s-expression text rewriting (no regex engine
in the crate; the E6 boundary), argued in the shim header and
VERIFICATION.md.

The ``temper_placer`` imports below resolve to the pinned pre-E6 modules
the verbatim bodies call back into (``_zone_pour_stitch``'s
``_chamfer_path_points`` / ``_emit_zone_pours`` and ``_strip_copper``'s
``strip_existing_zones`` stay Python single-source).  ``logger`` here names
the ORIGINAL module's logger so the unrepresented-field warnings hit the
same record the shim's do.  Do NOT edit: it is the reference.

RE-PIN 2026-08-15 (router pad-avoidance fix): the ``_write_routes_to_content``
pad-positions block was re-pinned to be rotation-aware (see the in-block
comment and ``docs/evidence/2026-08-15-router-pad-avoidance-fix.md``) --
the pre-migration body omitted component rotation, which put every pad of
a rotated component at the other pad's position and caused the zone-stitch
writer to emit dead shorts (204 ``shorting_items`` + 2
``tracks_crossing``). Everything else in this file is still verbatim from
the dispatch base; the content hash in ``scripts/oracle_hashes.json`` was
updated in the same commit.

"""

from __future__ import annotations

import logging
import math
import re
import uuid
from pathlib import Path

from temper_placer.router_v6._strip_copper import strip_existing_zones
from temper_placer.router_v6._zone_pour_stitch import (
    _chamfer_path_points,
    _emit_zone_pours,
)

logger = logging.getLogger("temper_placer.router_v6._adapter_convert")

# Fixed namespace for deriving synthetic KiCad ``tstamp`` UUIDs
# deterministically (see ``_next_tstamp`` below).
_TSTAMP_NAMESPACE = uuid.UUID("f8b1a2b0-6c4e-4a3a-9b7a-1a2b3c4d5e6f")

def _next_tstamp(counter: list[int]) -> str:
    """Return the next deterministic KiCad ``tstamp`` UUID.

    A single ``route_pcb()`` call writes many synthetic ``(segment ...)``/
    ``(via ...)`` elements. The previous implementation drew each
    ``tstamp`` from ``uuid.uuid4()``, which reads ``os.urandom`` -- so
    identical code and identical input produced a byte-different
    ``.kicad_pcb`` on every single run. Measurement showed this was the
    *only* source of that non-determinism: net topology, routed geometry,
    and layer/via assignment were already stable across 8 independent
    runs with default (randomized) ``PYTHONHASHSEED`` -- diffing two
    such runs after normalizing ``tstamp`` fields to a placeholder
    produced a zero-line diff (see
    docs/evidence/2026-07-27-router-determinism.md).

    ``tstamp`` is a KiCad object identifier only; it carries no
    electrical, geometric, or DRC meaning, so replacing the random draw
    with a value derived from a stable emission-order sequence number is
    safe and does not change what gets routed.

    This *does* depend on segment/via emission happening in a fixed
    order within one ``route_pcb()`` call -- an explicit, documented
    dependency rather than an incidental one. That order is already
    deterministic today (net iteration in ``_write_routes_to_content``
    walks a plain ``dict`` in insertion order, not a ``set``/``HashMap``
    in hash order), so a monotonic counter over that order is sufficient;
    it is not itself a tie-break.
    """
    n = counter[0]
    counter[0] = n + 1
    return str(uuid.uuid5(_TSTAMP_NAMESPACE, f"temper-router-v6-tstamp-{n}"))


def _via_type_token(from_layer: str, to_layer: str) -> str | None:
    """KiCad via type token for a declared layer pair, or ``None`` for through.

    Byte-identical twin of ``via_type_token`` in
    ``temper-orchestration/src/pipeline_route.rs`` (the differential suites
    pin the two to each other). KiCad's canonical outer copper layers are
    ``F.Cu``/``B.Cu`` on every board, so the full-stack pair is always
    ``F.Cu``/``B.Cu``:

    * ``F.Cu`` <-> ``B.Cu``           -> through  (no token; KiCad's format
                                                  default is through)
    * exactly one outer layer         -> ``"blind"`` (outer <-> inner)
    * two inner layers                -> ``"buried"`` (inner <-> inner)
    * same layer on both ends         -> through  (degenerate; unchanged from
                                                  the pre-fix emission)

    Without the token KiCad silently widens every layer-pair via to a
    through via piercing every copper layer -- 16 phantom DRC shorts on
    layers outside the declared pair (see
    docs/evidence/2026-08-15-via-type-emission-fix.md).
    """
    outer = ("F.Cu", "B.Cu")
    # Degenerate same-layer pair (should not occur -- the router derives
    # pairs from real layer transitions): keep the pre-fix emission (no
    # token), which is also the conservative KiCad default.
    if from_layer == to_layer:
        return None
    if from_layer in outer and to_layer in outer:
        return None
    if from_layer in outer or to_layer in outer:
        return "blind"
    return "buried"


def _to_stage0_netclass_rules(rules: Any) -> Any:
    """Convert a core NetClassRules (or duck-type-compatible shape) into a
    stage0 NetClassRules dataclass.

    This adapter is the single conversion boundary between the YAML SSOT
    representation (``core.netclass_rules_gen.NetClassRules``) and the A*
    engine's internal representation (``stage0_data.NetClassRules``).

    Explicit attribute checking replaces the previous ``getattr(rules, attr,
    default)`` duck-type approach: unrecognized shapes raise ``TypeError``
    rather than silently returning defaults.
    """
    from temper_placer.router_v6.stage0_data import NetClassRules as Stage0NetClassRules

    # --- Resolve each mapped field with explicit shape checking ---

    def _resolve(name: str, *aliases: str) -> Any:
        """Return the first attribute of *aliases* that exists on *rules*."""
        del name  # kept for call-site symmetry; only *aliases* are consulted
        for alias in aliases:
            if hasattr(rules, alias):
                return getattr(rules, alias)
        raise TypeError(
            f"Cannot convert {type(rules).__name__!r} to stage0 NetClassRules: "
            f"no attribute matching any of {list(aliases)} found"
        )

    name = _resolve("name", "name")
    clearance_mm = _resolve("clearance", "clearance", "clearance_mm")
    trace_width_mm = _resolve("trace_width", "trace_width", "trace_width_mm")
    via_diameter_mm = _resolve("via_diameter", "via_diameter", "via_diameter_mm")
    via_drill_mm = _resolve("via_drill", "via_drill", "via_drill_mm")

    # max_current_rating → current_rating_amps (R1 fix)
    current_rating_amps: float | None = None
    if hasattr(rules, "max_current_rating"):
        current_rating_amps = rules.max_current_rating

    # safety_category survives conversion (needed by R6 HV/AC forced-segment gate)
    safety_category: str | None = None
    if hasattr(rules, "safety_category"):
        val = rules.safety_category
        if val is not None:
            safety_category = str(val)

    # creepage_mm survives conversion: stage0_data.NetClassRules carries the
    # field (default 0.0), and `_required_creepage_mm` reads it for the
    # mains-adjacent bottleneck analysis -- dropping it here silently
    # replaced a declared creepage (e.g. 6.0mm) with 0.0.
    creepage_mm = getattr(rules, "creepage_mm", 0.0)

    # --- R1b: Warn on unrepresented fields that are explicitly set ---
    _UNREPRESENTED_WARN = (
        ("voltage_v", "Voltage rating", 0.0),
        ("routing_strategy", "Routing strategy", None),
        ("via_cost_multiplier", "Via cost multiplier", 1.0),
        ("layer_costs", "Layer cost overrides", None),
        ("via_template", "Via template", None),
        ("target_impedance", "Target impedance", None),
        ("required_layer", "Required KiCad layer", None),
        ("layer", "KiCad layer", None),
        ("dru_priority", "DRU priority", 0),
    )
    for attr_name, human_label, default_val in _UNREPRESENTED_WARN:
        val = getattr(rules, attr_name, None)
        if val is not None and val != default_val:
            logger.warning(
                "_to_stage0_netclass_rules: dropping %s=%s for netclass %r "
                "— no stage0 equivalent field exists",
                human_label,
                val,
                name,
            )

    return Stage0NetClassRules(
        name=name,
        clearance_mm=clearance_mm,
        trace_width_mm=trace_width_mm,
        via_diameter_mm=via_diameter_mm,
        via_drill_mm=via_drill_mm,
        current_rating_amps=current_rating_amps,
        safety_category=safety_category,
        creepage_mm=creepage_mm,
    )


def _write_routes_to_content(
    pcb_content: str, result: Any, *, design_rules: Any = None
) -> tuple[str, dict[str, list[tuple[float, float]]]]:
    """Inject routing tracks from RouterV6Pipeline result into KiCad PCB content.

    Extracts successfully routed paths from the pipeline result and writes
    them as ``(segment ...)`` entries into the PCB content. For plane nets
    (zero-length dummy paths) and for missing pins on multi-pin signal nets,
    creates direct connections using pad positions from the parsed PCB.
    """
    from types import SimpleNamespace

    # Single deterministic tstamp sequence shared by every segment/via
    # this call emits (routed paths, vias, and -- via _emit_zone_pours --
    # zone pours and isolated-pad stitch segments). See _next_tstamp.
    tstamp_counter: list[int] = [0]

    pad_positions: dict[str, list[tuple[float, float]]] = {}

    routing_results = getattr(result.stage4, "routing_results", None)
    if routing_results is None:
        return pcb_content, pad_positions

    compiled = getattr(routing_results, "compiled_routes", {})
    tree_compiled = getattr(routing_results, "tree_routes", {})
    partial_tree_compiled = getattr(routing_results, "partial_tree_routes", {})
    if not compiled and not tree_compiled and not partial_tree_compiled:
        return pcb_content, pad_positions

    # U7: fold tree routes into the compiled-routes iteration so the
    # writer emits tree-routed net geometry alongside legacy paths.
    _tree_seen: set[str] = set()
    for net_name, ctr in {**tree_compiled, **partial_tree_compiled}.items():
        if net_name in compiled or net_name in _tree_seen:
            continue
        _tree_seen.add(net_name)
        fake_path = SimpleNamespace(
            path_length=1.0,
            coordinates=[],  # tree routes have no serial coordinates
        )
        compiled[net_name] = SimpleNamespace(
            path=fake_path,
            width_mm=getattr(ctr, "width_mm", 0.2),
            vias=getattr(ctr, "vias", []),
            _tree_route=ctr,
        )

    # Build net name -> net number mapping from the PCB content
    net_name_to_number: dict[str, int] = {}
    for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', pcb_content):
        net_name_to_number[m.group(2)] = int(m.group(1))

    # Collect pad world positions from the parsed PCB data
    #
    # RE-PINNED 2026-08-15 (rotation): the pre-migration body summed
    # ``comp.initial_position + pin.position`` with no component rotation,
    # which placed every pad of a rotated component at its MIRROR position
    # across the anchor -- for a 2-pad part that is the OTHER pad -- so the
    # zone-stitch writer emitted each net's stitch track from the other
    # net's physical pad (204 ``shorting_items`` + 2 ``tracks_crossing`` on
    # the 2026-08-15 routed board; see
    # ``docs/evidence/2026-08-15-router-pad-avoidance-fix.md``). This block
    # now applies the same mirror + R(-theta) transform as
    # ``temper_geometry.pin_world_position_at_py`` (rotation quadrant 0-3 ->
    # q*pi/2, side 1 -> mirror X, then ``x*c + y*s`` / ``-x*s + y*c``),
    # keeping the duck-typed attribute defaults (missing rotation/side
    # attrs -> 0 -> identical to the pre-fix body). The same correction was
    # applied to ``temper-orchestration::run_collect_pad_positions`` (the
    # Rust port this oracle pins) and the marshal differential's
    # ``_oracle_collect_pad_positions``, in this same commit.
    pcb = getattr(result, "pcb", None)
    if pcb is not None:
        comp_by_ref = {c.ref: c for c in pcb.components}
        for net in pcb.nets:
            positions: list[tuple[float, float]] = []
            for comp_ref, pin_name in getattr(net, "pins", []):
                comp = comp_by_ref.get(comp_ref)
                if comp is None:
                    continue
                comp_pos = getattr(comp, "initial_position", (0.0, 0.0)) or (0.0, 0.0)
                pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
                if pin is None:
                    positions.append((float(comp_pos[0]), float(comp_pos[1])))
                    continue
                px, py = pin.position
                rot_q = getattr(comp, "initial_rotation_quadrant", None)
                if rot_q is None:
                    rotation_rad = 0.0
                elif isinstance(rot_q, int):  # bool included, like pyo3's i64 extract
                    rotation_rad = rot_q * math.pi / 2.0
                else:
                    rotation_rad = float(rot_q)
                side_attr = getattr(comp, "initial_side", None)
                if side_attr is None or not side_attr:
                    side = 0
                elif isinstance(side_attr, int):
                    side = int(side_attr)
                else:
                    side = 0
                mx = -px if side == 1 else px
                c = math.cos(rotation_rad)
                s = math.sin(rotation_rad)
                wx = mx * c + py * s
                wy = -mx * s + py * c
                positions.append((float(comp_pos[0]) + wx, float(comp_pos[1]) + wy))
            if positions:
                pad_positions[net.name] = positions

    segments: list[str] = []
    for net_name, compiled_route in compiled.items():
        path = getattr(compiled_route, "path", None)
        if path is None:
            continue

        # U7: emit tree-route branch geometry directly.  Each branch's
        # segments are written as independent track segments; sibling
        # branches are never bridged by synthetic copper.
        tree_route = getattr(compiled_route, "_tree_route", None)
        if tree_route is not None:
            tree_width = getattr(compiled_route, "width_mm", 0.2)
            net_num = net_name_to_number.get(net_name, 0)
            # iter_segments() lives on TreeRouteGeometry (yields pairs of
            # (x, y, layer) points across all branches), not on a branch's
            # individual RoutePath/RoutePath3D -- neither has iter_segments.
            for (sx, sy, s_layer), (ex, ey, e_layer) in tree_route.geometry.iter_segments():
                if s_layer != e_layer or (sx == ex and sy == ey):
                    # A layer change between consecutive points is a via
                    # crossing, not a same-layer copper run -- KiCad segments
                    # are single-layer. Via emission for tree-routed nets
                    # isn't wired yet (pre-existing gap; the vias loop below
                    # is skipped for this branch by the `continue`), so this
                    # point-pair is dropped rather than drawn incorrectly.
                    # Coincident points are dropped for the same reason as in
                    # the path branch below: a start == end track is copper
                    # joining a node to itself, carrying no connectivity but
                    # leaving DRC's tracks_crossing test without a direction.
                    continue
                seg_id = _next_tstamp(tstamp_counter)
                segments.append(
                    f"  (segment (start {sx:.4f} {sy:.4f}) (end {ex:.4f} {ey:.4f})"
                    f' (width {tree_width:.4f}) (layer "{s_layer}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
            continue

        path_length = getattr(path, "path_length", 0.0)
        width = getattr(compiled_route, "width_mm", 0.2)
        # Defense-in-depth: never emit a zero/negative-width track (KiCad DRC
        # flags these as track_width violations). getattr's default does not
        # catch a present-but-zero width, so guard explicitly.
        if not width or width <= 0.0:
            width = 0.2
        net_num = net_name_to_number.get(net_name, 0)
        pads = pad_positions.get(net_name, [])

        if path_length > 0 and len(pads) >= 2:
            # Real routed net: extract path coordinates with per-step layer
            path_points: list[tuple[float, float, str]] = []
            path_segs = getattr(path, "segments", None)
            if path_segs:
                for s in path_segs:
                    path_points.append((s[0], s[1], s[2]))
            else:
                coords = getattr(path, "coordinates", None)
                if coords:
                    default_layer = getattr(path, "layer_name", "F.Cu")
                    for c in coords:
                        path_points.append((c[0], c[1], default_layer))

            # Chamfer 90-degree orthogonal turns to reduce grid-staircasing.
            # After collapse, remaining turns are still sharp 90-degree
            # corners from the 0.1 mm A* grid.  Two adjacent traces following
            # similar grid paths have edge-to-edge clearance violations at
            # these corners because the staircase stagger pushes segments
            # closer than the minimum clearance.  Chamfering replaces each
            # orthogonal turn with a 45-degree diagonal, reducing both
            # shorting_items and tracks_crossing DRC violations.
            path_points = _chamfer_path_points(path_points, chamfer_offset=0.1)

            # Write path segments, collapsing consecutive same-direction
            # same-layer steps to avoid A* grid-stepping staircasing.
            # Each individual grid step (0.1mm) emitted as its own
            # (segment ...) creates 8k+ micro-segments that KiCad DRC
            # flags as clearance / shorting / masking violations because
            # adjacent segments from different nets interleave with
            # edge-to-edge gaps under the 0.2mm rule. Only merge
            # consecutive steps that share the same layer -- a layer
            # change always splits the merged chain.
            i = 0
            while i < len(path_points) - 1:
                x1, y1, lyr = path_points[i]
                x2, y2, l2 = path_points[i + 1]
                if l2 != lyr or (x2 == x1 and y2 == y1):
                    # Not a copper run on `lyr`, so it must not become a
                    # (segment ...) -- the rule the tree-route branch above
                    # already applies. A layer change IS the via crossing:
                    # astar_core records it as the same (x, y) on two layers
                    # and never merges that pair, and _chamfer_path_points
                    # passes it through, so reading it as from-layer copper
                    # emitted a start == end track (48 on the committed board,
                    # one per via, each on a via position). Such a track joins
                    # a node to itself: no connectivity (the via already ties
                    # the layers) and no direction, which leaves its crossing
                    # point undefined for DRC's tracks_crossing test. The
                    # coincident-point half of the test is the same defect via
                    # a duplicated same-layer point, guarded so "no zero-length
                    # segment is emitted" holds outright, not as a consequence.
                    i += 1
                    continue
                dx_prev = x2 - x1
                dy_prev = y2 - y1
                j = i + 2
                while j < len(path_points):
                    xm, ym, _ = path_points[j - 1]
                    xn, yn, lyr_n = path_points[j]
                    dx_cur = xn - xm
                    dy_cur = yn - ym
                    if (
                        abs(dx_cur - dx_prev) < 1e-12
                        and abs(dy_cur - dy_prev) < 1e-12
                        and lyr_n == lyr
                    ):
                        x2, y2 = xn, yn
                        j += 1
                    else:
                        break
                seg_id = _next_tstamp(tstamp_counter)
                segments.append(
                    f"  (segment (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})"
                    f' (width {width:.4f}) (layer "{lyr}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
                i = j - 1
        # U5: emit real (via ...) s-expressions for each Via in the compiled route.
        # KiCad via-type emission: a via whose declared layer pair is NOT the
        # full copper stack must carry a `blind`/`buried` type token, or KiCad
        # defaults it to a THROUGH via piercing every copper layer. This is the
        # byte-identical twin of the Rust `via_type_token` helper in
        # temper-orchestration pipeline_route.rs (see
        # docs/evidence/2026-08-15-via-type-emission-fix.md). The differential
        # suites pin the two to each other.
        for via in getattr(compiled_route, "vias", []):
            vx, vy = via.position
            type_token = _via_type_token(via.from_layer, via.to_layer)
            via_head = f"  (via {type_token} (at" if type_token else "  (via (at"
            segments.append(
                f"{via_head} {vx:.4f} {vy:.4f}) (size {via.diameter:.4f})"
                f' (drill {via.drill:.4f}) (layers "{via.from_layer}" "{via.to_layer}")'
                f' (net {net_num}) (tstamp "{_next_tstamp(tstamp_counter)}"))'
            )

    if getattr(result, "enable_zone_pours", False):
        pcb_content, _ = strip_existing_zones(pcb_content)  # R7: replace, don't append
        _emit_zone_pours(
            pad_positions,
            segments,
            net_name_to_number,
            design_rules=design_rules,
            tstamp_counter=tstamp_counter,
            pcb=pcb,
        )

    if not segments:
        return pcb_content, pad_positions

    # Inject segments before the closing ")" of the kicad_pcb s-expression
    segment_block = "\n" + "\n".join(segments) + "\n"
    pcb_content = pcb_content.rstrip()
    if pcb_content.endswith(")"):
        pcb_content = pcb_content[:-1] + segment_block + ")\n"

    return pcb_content, pad_positions

