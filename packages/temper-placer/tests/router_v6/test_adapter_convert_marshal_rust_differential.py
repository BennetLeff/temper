"""R1a: behavioural A/B of the ``router_v6/_adapter_convert.py`` residual
adapter marshalling (the U-H unit) against the pinned pre-migration
implementation.

Rust Orchestration Engine plan 2026-08-09-001, Phase E E6 follow-on (the
orchestration-port unit U-H): the deterministic wire-format construction that
E6 left Python-side -- the board->pad_positions conversion, the per-route
payload marshalling that feeds ``run_write_route_segments`` (the
segments/coordinates duck-typed extraction + the chamfer call-back + the via
extraction), and the ``_build_routing_result`` failure-extraction assembly
(the router's OUTPUT wire format) -- moves to temper-orchestration's
``pipeline_route.rs``:

- ``_write_routes_to_content``'s pad-positions block  -> ``run_collect_pad_positions``
- ``_write_routes_to_content``'s per-route payload block -> ``run_build_route_payload``
- ``_build_routing_result``'s extraction core        -> ``run_build_routing_result``

The pre-migration implementations are pinned VERBATIM below (the
``_oracle_*`` blocks, content-addressed by their per-body SHA-256). Both arms
are driven with IDENTICAL inputs; every assertion is bit-exact (``==`` on
int/str leaves, ``float.hex()`` via the ``_canon`` walker on floats).

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
the shims bind to the ``temper_orchestration`` pyfunctions (``__module__``),
not resolving back onto the inline oracles.

What stays Python (the U-H boundary, argued in the shim header and
VERIFICATION.md): ``route_pcb`` (pipeline invocation / tempfile-subprocess),
``_apply_placements_to_pcb`` / ``_reorient_pads_in_footprint_block`` and the
net-name->number regex mapping (``re``-based s-expression handling -- the
crate has no regex engine), the tree-route folding
(``TreeRouteGeometry.iter_segments`` call-back), the s-expression injection,
the zone-pour emission call-backs and the ``connectivity_preflight``
call-back (driven with ``enable_connectivity_verifier=False`` throughout --
the call-back stays Python single-source, exercised by ``test_adapter.py``).
``_chamfer_path_points`` stays Python single-source and is CALLED BACK from
``run_build_route_payload`` (the D4/D5 mixin-call-back pattern).
"""

from __future__ import annotations

import ast
import hashlib
import random
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import temper_orchestration as _to

from temper_placer.router_v6._adapter_convert import (
    _build_routing_result as shim_build_routing_result,
)
from temper_placer.router_v6._adapter_convert import (
    _write_routes_to_content as shim_write_routes,
)
from temper_placer.router_v6._adapter_types import CongestionRegion, DrcViolation
from temper_placer.router_v6._zone_pour_stitch import _chamfer_path_points

# ---------------------------------------------------------------------------
# The oracles must stay verbatim
# ---------------------------------------------------------------------------
#
# Verbatim pre-migration copies of the `_adapter_convert.py` blocks AS
# COMMITTED at the dispatch base (origin/main 6ac9b8107).  Do NOT edit: they
# are the reference.  If the module's source really changes upstream,
# re-pin the bodies in their own commit (the `_ORACLE_*_SHA256` digests below
# fail on any drift).


def _oracle_collect_pad_positions(pcb: Any) -> dict[str, list[tuple[float, float]]]:
    """RE-PINNED 2026-08-15 (deliberate, with the rotation fix): the
    pre-migration pad-positions block of ``_write_routes_to_content`` summed
    ``comp_pos + pin_pos`` with NO component rotation, which placed zone hulls
    and the connectivity preflight at wrong coordinates for the 148/169
    components with nonzero rotation (measured: only 21/59 real pads inside
    same-layer hulls). The re-pinned oracle resolves each pin through the
    canonical temper-geometry kernel (mirror X on side==1, R(-theta) rotation,
    then comp_pos -- the same sanctioned math ``run_collect_pad_positions``
    now calls back into via ``pin_world_position_at_py``), so the differential
    asserts the Rust port matches canonical pad-position geometry rather than
    the historical bug. Missing ``initial_rotation_quadrant``/``initial_side``
    read as 0/0 (getattr defaults, exactly like the Rust kernel). Everything
    else (the ``comp_by_ref`` dict comprehension, the ``getattr(net, "pins",
    [])`` walk, the ``comp.get_pin`` duck-typed call, the comp-position
    fallback for a missing/None pin) is unchanged from the pre-migration
    body."""
    pad_positions: dict[str, list[tuple[float, float]]] = {}
    if pcb is not None:
        import temper_geometry as _tg

        comp_by_ref = {c.ref: c for c in pcb.components}
        for net in pcb.nets:
            positions: list[tuple[float, float]] = []
            for comp_ref, pin_name in getattr(net, "pins", []):
                comp = comp_by_ref.get(comp_ref)
                if comp is None:
                    continue
                comp_pos = getattr(comp, "initial_position", (0.0, 0.0))
                pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
                if pin is None:
                    positions.append((float(comp_pos[0]), float(comp_pos[1])))
                else:
                    rot = getattr(comp, "initial_rotation_quadrant", None)
                    rotation_rad = _tg.normalize_rotation_py(rot)
                    side = getattr(comp, "initial_side", None) or 0
                    px, py = pin.position
                    positions.append(
                        _tg.pin_world_position_kernel_py(
                            float(px),
                            float(py),
                            side,
                            rotation_rad,
                            float(comp_pos[0]),
                            float(comp_pos[1]),
                        )
                    )
            if positions:
                pad_positions[net.name] = positions
    return pad_positions


def _oracle_build_route_payload(
    path: Any,
    compiled_route: Any,
    net_name: str,
    net_num: int,
    pads: list,
) -> tuple:
    """VERBATIM per-route payload block of ``_write_routes_to_content`` (the
    pre-migration Python body: the ``path_length``/``width`` reads with the
    ``not width or width <= 0.0`` snap, the segments/coordinates extraction
    branches, the chamfer call and the via extraction). ``pads`` is the net's
    pad-positions list exactly as the writer's ``pad_positions.get(net_name,
    [])`` would produce it -- only ``len(pads)`` feeds the guard, and the
    returned payload carries ``len(pads)`` like the writer's."""
    path_length = getattr(path, "path_length", 0.0)
    width = getattr(compiled_route, "width_mm", 0.2)
    # Defense-in-depth: never emit a zero/negative-width track (KiCad DRC
    # flags these as track_width violations). getattr's default does not
    # catch a present-but-zero width, so guard explicitly.
    if not width or width <= 0.0:
        width = 0.2

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
        path_points = _chamfer_path_points(path_points, chamfer_offset=0.1)
    else:
        path_points = []

    vias = []
    for via in getattr(compiled_route, "vias", []):
        vx, vy = via.position
        vias.append((vx, vy, via.diameter, via.drill, via.from_layer, via.to_layer))

    return (net_name, path_length, path_points, width, net_num, vias, len(pads))


def _oracle_build_routing_result(
    result: Any,
    routed_content: str | None = None,
    *,
    pad_positions: dict[str, list[tuple[float, float]]] | None = None,
    enable_connectivity_verifier: bool = False,
) -> Any:
    """VERBATIM pre-migration ``_build_routing_result`` body (as committed at
    the dispatch base -- the failure-extraction assembly this unit ports). The
    ``connectivity_preflight`` call-back stays Python single-source and is not
    exercised by this differential (``enable_connectivity_verifier=False`` on
    every arm; the call-back is covered by ``test_adapter.py``)."""
    routing_results = result.stage4.routing_results
    unrouted_nets = list(routing_results.failed_nets)

    # R5: Extract forced-segment net names from compiled routes.
    forced_segment_nets: list[str] = []
    compiled = getattr(routing_results, "compiled_routes", None)
    if compiled:
        forced_segment_nets = [
            net_name
            for net_name, route in compiled.items()
            if getattr(getattr(route, "path", None), "forced_segment_count", 0) > 0
        ]

    drc_violations: list[DrcViolation] = []
    congestion_regions: list[CongestionRegion] = []

    for report in getattr(routing_results, "net_reports", []):
        # Collect DRC violations from per-net reports
        drc_count = getattr(report, "drc_violations", 0)
        if drc_count > 0:
            drc_violations.append(
                DrcViolation(
                    net_name=getattr(report, "net_name", "unknown"),
                    count=drc_count,
                    message=getattr(report, "message", ""),
                )
            )

        # Collect congestion regions from bottleneck geometry
        bottleneck = getattr(report, "bottleneck", None)
        if bottleneck is not None:
            pair_kind = getattr(bottleneck, "pair_kind", None)
            if pair_kind in ("component_edge", "component_keepout"):
                comps = getattr(bottleneck, "component_pair", ("unknown", "unknown"))
                gap = getattr(bottleneck, "current_gap_mm", 0.0)
                positions = getattr(bottleneck, "positions_mm", ((0.0, 0.0), (0.0, 0.0)))
                congestion_regions.append(
                    CongestionRegion(
                        net_name=getattr(report, "net_name", "unknown"),
                        comp_a=comps[0],
                        comp_b=comps[1],
                        current_distance_mm=gap,
                        positions=positions,
                    )
                )

    # Pull DRC data from manufacturing report if available
    mfg = getattr(result, "manufacturing_report", None)
    if mfg is not None:
        for v in getattr(mfg, "violations", []):
            drc_violations.append(
                DrcViolation(
                    type=getattr(v, "type", "unknown"),
                    message=getattr(v, "message", ""),
                    net_name=getattr(v, "net_name", ""),
                    location=getattr(v, "location", (0.0, 0.0)),
                )
            )

    # U4: post-write connectivity preflight
    connectivity = None
    if enable_connectivity_verifier and routed_content and pad_positions:
        from temper_placer.router_v6.kicad_connectivity import (
            connectivity_preflight,
        )

        connectivity = connectivity_preflight(routed_content, pad_positions)

    stage3 = getattr(result, "stage3", None)
    topology_graph = getattr(stage3, "topology_graph", None)
    net_topologies = getattr(topology_graph, "net_topologies", None) or {}
    topology_solved_nets = list(net_topologies.keys())

    return SimpleNamespace(
        completion_rate=result.completion_rate,
        unrouted_nets=unrouted_nets,
        drc_violations=drc_violations,
        congestion_regions=congestion_regions,
        routed_pcb_content=routed_content,
        connectivity=connectivity,
        forced_segment_nets=forced_segment_nets,
        topology_solved_nets=topology_solved_nets,
    )


def _body_sha256(name: str) -> str:
    src = Path(__file__).read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = "".join(lines[node.lineno - 1 : node.end_lineno])
            return hashlib.sha256(textwrap.dedent(body).encode()).hexdigest()
    raise AssertionError(f"oracle function {name} not found")


# The oracles are evidence only while they are unmodified.  Pinned so a body
# edit fails this test rather than silently re-pinning the differential.
_ORACLE_COLLECT_PAD_POSITIONS_SHA256 = (
    "ab4c4b81dca817238c1e2a03c0a76377cae2d97543a4183e2ac728b2afc5918c"
)
_ORACLE_BUILD_ROUTE_PAYLOAD_SHA256 = (
    "63a2da4cd8a3022a60f96541dcec29285f6635a0c3a4d454c91b43254cfe5c05"
)
_ORACLE_BUILD_ROUTING_RESULT_SHA256 = (
    "85637cf33e371178c95bfc18a5f60b306b69bf8705e595071950f4ac882ac561"
)


def test_oracle_bodies_match_pinned_digests() -> None:
    """The oracle bodies are content-addressed: any edit changes the digest
    and fails here (re-pin deliberately, in its own commit, if the module's
    source really changed upstream)."""
    assert _body_sha256("_oracle_collect_pad_positions") == _ORACLE_COLLECT_PAD_POSITIONS_SHA256
    assert _body_sha256("_oracle_build_route_payload") == _ORACLE_BUILD_ROUTE_PAYLOAD_SHA256
    assert _body_sha256("_oracle_build_routing_result") == _ORACLE_BUILD_ROUTING_RESULT_SHA256


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shims must bind to the temper_orchestration
    pyfunctions, not resolve back onto the inline oracles."""
    assert _to.run_collect_pad_positions.__module__ == "temper_orchestration.temper_orchestration"
    assert _to.run_build_route_payload.__module__ == "temper_orchestration.temper_orchestration"
    assert _to.run_build_routing_result.__module__ == "temper_orchestration.temper_orchestration"
    assert _oracle_build_routing_result.__module__ != "temper_orchestration.temper_orchestration"


# ---------------------------------------------------------------------------
# Fixtures + canon
# ---------------------------------------------------------------------------


def _canon(x: Any) -> Any:
    """Bit-exact walker: floats via ``float.hex()`` (the established canon),
    tuples/lists recursively, everything else by identity/equality."""
    if isinstance(x, float):
        return float.hex(x)
    if isinstance(x, tuple):
        return tuple(_canon(i) for i in x)
    if isinstance(x, list):
        return [_canon(i) for i in x]
    return x


def _comp(ref, initial_position=(1.0, 2.0), pins=None):
    """A duck-typed component: with ``pins`` it has a real ``get_pin``."""
    if pins is None:
        return SimpleNamespace(ref=ref, initial_position=initial_position)
    return SimpleNamespace(
        ref=ref,
        initial_position=initial_position,
        get_pin=lambda name: SimpleNamespace(position=pins[name]) if name in pins else None,
    )


def _net(name, pins):
    return SimpleNamespace(name=name, pins=pins)


def _pcb(components, nets):
    return SimpleNamespace(components=list(components), nets=list(nets))


def _assert_pad_positions_same(pcb, msg=""):
    want = _oracle_collect_pad_positions(pcb)
    got = dict(_to.run_collect_pad_positions(pcb))
    assert _canon(got) == _canon(want), f"{msg}: pad_positions differ\nwant {want}\ngot  {got}"


def _route(path, width=0.2, vias=()):
    return SimpleNamespace(path=path, width_mm=width, vias=list(vias))


def _assert_payload_same(path, route, net_name, net_num, pads, msg=""):
    want = _oracle_build_route_payload(path, route, net_name, net_num, pads)
    got = _to.run_build_route_payload(path, route, net_name, net_num, len(pads))
    assert _canon(got) == _canon(want), (
        f"{msg}: payload differs\nwant {want!r}\ngot  {got!r}"
    )


def _assert_result_same(result, msg=""):
    want = _oracle_build_routing_result(result)
    got = shim_build_routing_result(result)
    assert got.completion_rate == want.completion_rate, f"{msg}: completion_rate"
    assert got.unrouted_nets == want.unrouted_nets, f"{msg}: unrouted_nets"
    assert got.forced_segment_nets == want.forced_segment_nets, f"{msg}: forced_segment_nets"
    assert _canon(list(got.drc_violations)) == _canon(list(want.drc_violations)), (
        f"{msg}: drc_violations\nwant {want.drc_violations!r}\ngot  {got.drc_violations!r}"
    )
    assert _canon(list(got.congestion_regions)) == _canon(list(want.congestion_regions)), (
        f"{msg}: congestion_regions\nwant {want.congestion_regions!r}\ngot  {got.congestion_regions!r}"
    )
    assert got.topology_solved_nets == want.topology_solved_nets, f"{msg}: topology_solved_nets"
    assert got.net_batch_summary == {}, f"{msg}: net_batch_summary must be empty (batch off)"


# ---------------------------------------------------------------------------
# run_collect_pad_positions
# ---------------------------------------------------------------------------


def test_collect_pad_positions_none_pcb():
    assert _to.run_collect_pad_positions(None) == []
    assert _oracle_collect_pad_positions(None) == {}


def test_collect_pad_positions_empty_pcb():
    pcb = _pcb([], [])
    _assert_pad_positions_same(pcb, "empty pcb")


def test_collect_pad_positions_pins_resolve_through_get_pin():
    comps = [
        _comp("C1", pins={"1": (0.5, 1.5), "2": (2.0, 3.0)}),
        _comp("C2", pins={"1": (1.0, 0.0)}),
    ]
    nets = [_net("NET_A", [("C1", "1"), ("C2", "1")]), _net("NET_B", [("C1", "2")])]
    pcb = _pcb(comps, nets)
    _assert_pad_positions_same(pcb, "resolved pins")
    got = dict(_to.run_collect_pad_positions(pcb))
    assert got["NET_A"] == [(1.5, 3.5), (2.0, 2.0)]
    assert got["NET_B"] == [(3.0, 5.0)]


def test_collect_pad_positions_missing_comp_and_no_get_pin():
    comps = [_comp("C1")]  # no get_pin -> falls back to comp_pos
    nets = [
        _net("NET_MISSING", [("C9", "1")]),  # comp absent -> skipped
        _net("NET_FALLBACK", [("C1", "1")]),  # no get_pin -> comp_pos
        _net("NET_EMPTY", []),  # no pins -> not added
    ]
    pcb = _pcb(comps, nets)
    _assert_pad_positions_same(pcb, "missing comp / fallback / empty")
    got = dict(_to.run_collect_pad_positions(pcb))
    assert "NET_MISSING" not in got
    assert "NET_EMPTY" not in got
    assert got["NET_FALLBACK"] == [(1.0, 2.0)]


def test_collect_pad_positions_get_pin_returns_none():
    comps = [_comp("C1", pins={"1": (0.5, 1.5)})]
    nets = [_net("NET_X", [("C1", "7")])]  # get_pin("7") -> None -> comp_pos
    pcb = _pcb(comps, nets)
    _assert_pad_positions_same(pcb, "get_pin None")
    assert dict(_to.run_collect_pad_positions(pcb))["NET_X"] == [(1.0, 2.0)]


def test_collect_pad_positions_missing_pins_attr_and_initial_position():
    comps = [_comp("C1")]
    nets = [SimpleNamespace(name="NET_X")]  # no .pins -> getattr default []
    pcb = _pcb(comps, nets)
    _assert_pad_positions_same(pcb, "missing pins attr")
    assert dict(_to.run_collect_pad_positions(pcb)) == {}

    comps2 = [SimpleNamespace(ref="C1")]  # no initial_position -> (0.0, 0.0)
    pcb2 = _pcb(comps2, [_net("NET_Y", [("C1", "1")])])
    _assert_pad_positions_same(pcb2, "missing initial_position")
    assert dict(_to.run_collect_pad_positions(pcb2))["NET_Y"] == [(0.0, 0.0)]


def test_collect_pad_positions_duplicate_ref_last_writer_wins():
    comps = [_comp("C1", initial_position=(1.0, 1.0)), _comp("C1", initial_position=(9.0, 9.0))]
    pcb = _pcb(comps, [_net("NET_Z", [("C1", "1")])])
    _assert_pad_positions_same(pcb, "duplicate ref")
    assert dict(_to.run_collect_pad_positions(pcb))["NET_Z"] == [(9.0, 9.0)]


def test_collect_pad_positions_many_randomized():
    rng = random.Random(20260812)
    for _ in range(30):
        comps = [
            _comp(f"C{i}", initial_position=(rng.uniform(-5, 5), rng.uniform(-5, 5)))
            for i in range(rng.randint(0, 6))
        ]
        nets = []
        for n in range(rng.randint(0, 6)):
            pins = []
            for _p in range(rng.randint(0, 5)):
                ref = f"C{rng.randint(0, 7)}"
                name = str(rng.randint(0, 4))
                pins.append((ref, name))
            nets.append(_net(f"NET{n}", pins))
        pcb = _pcb(comps, nets)
        _assert_pad_positions_same(pcb, f"randomized {_}")
    # A duplicate-ref randomized case: last writer wins even under churn.
    dup = _pcb(
        [_comp("C1", initial_position=(1.0, 1.0)), _comp("C1", initial_position=(2.0, 2.0))],
        [_net("N", [("C1", "1")])],
    )
    _assert_pad_positions_same(dup, "randomized duplicate-ref")


def test_collect_pad_positions_applies_component_rotation():
    """The rotation fix must not be vacuous: a component rotated 180 deg about
    its origin moves a pin at local (1.0, 0.0) to (cx - 1.0, cy) -- NOT the
    naive (cx + 1.0, cy) the pre-fix code produced (148/169 components on the
    board carry nonzero rotation). Compared bit-exactly against the canonical
    ``pin_world_position_at`` (mirror + R(-theta) + comp_pos)."""
    from temper_placer.core.pin_geometry import pin_world_position_at

    comp = SimpleNamespace(
        ref="U1",
        initial_position=(10.0, 20.0),
        initial_rotation_quadrant=2,  # 180 deg
        initial_side=0,
        get_pin=lambda _name: SimpleNamespace(position=(1.0, 0.0)),
    )
    pcb = _pcb([comp], [_net("NET_R", [("U1", "1")])])
    _assert_pad_positions_same(pcb, "rotated comp")

    got = dict(_to.run_collect_pad_positions(pcb))["NET_R"][0]
    want = pin_world_position_at(SimpleNamespace(position=(1.0, 0.0)), comp)
    assert _canon(got) == _canon(want), f"rotated world pos {got} != canonical {want}"
    assert got != (11.0, 20.0), (
        "must not regress to the naive comp_pos + pin_pos sum (11.0, 20.0)"
    )
    assert got[0] == 9.0, "180-deg rotation must land the pin at cx - 1.0"

    # Side mirror: a bottom-side (side==1) component mirrors X before rotation.
    comp_bottom = SimpleNamespace(
        ref="U2",
        initial_position=(5.0, 5.0),
        initial_rotation_quadrant=0,
        initial_side=1,
        get_pin=lambda _name: SimpleNamespace(position=(2.0, 0.0)),
    )
    pcb_bottom = _pcb([comp_bottom], [_net("NET_S", [("U2", "1")])])
    got_b = dict(_to.run_collect_pad_positions(pcb_bottom))["NET_S"][0]
    want_b = pin_world_position_at(SimpleNamespace(position=(2.0, 0.0)), comp_bottom)
    assert _canon(got_b) == _canon(want_b), f"mirrored world pos {got_b} != {want_b}"
    assert got_b != (7.0, 5.0), "side mirror must flip the pin x-offset (3.0, not 7.0)"


# ---------------------------------------------------------------------------
# run_build_route_payload
# ---------------------------------------------------------------------------


def test_build_route_payload_zero_length_path():
    path = SimpleNamespace(path_length=0.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 1.0, "F.Cu")])
    route = _route(path, vias=[SimpleNamespace(position=(5.0, 6.0), diameter=0.6, drill=0.3, from_layer="F.Cu", to_layer="B.Cu")])
    _assert_payload_same(path, route, "NET1", 2, [(0.0, 0.0), (1.0, 1.0)], "zero-length")
    got = _to.run_build_route_payload(path, route, "NET1", 2, 2)
    assert got[2] == [], "zero-length path must carry no path points"
    assert len(got[5]) == 1, "vias still extracted outside the path guard"


def test_build_route_payload_single_pad_guard():
    path = SimpleNamespace(path_length=5.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")])
    route = _route(path)
    _assert_payload_same(path, route, "NET1", 3, [(0.0, 0.0)], "single pad")
    got = _to.run_build_route_payload(path, route, "NET1", 3, 1)
    assert got[2] == [], "len(pads) < 2 must carry no path points"


def test_build_route_payload_segments_branch_with_chamfer():
    # An orthogonal turn (0,0)->(1,0)->(1,1): the chamfer replaces the corner
    # with a 45-degree diagonal -- the payload must carry the CHAMFERED
    # points (the call-back runs inside the kernel, exactly like the oracle).
    path = SimpleNamespace(path_length=2.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu"), (1.0, 1.0, "F.Cu")])
    route = _route(path)
    pads = [(0.0, 0.0), (1.0, 1.0)]
    _assert_payload_same(path, route, "NET1", 1, pads, "chamfered corner")
    got = _to.run_build_route_payload(path, route, "NET1", 1, len(pads))
    want_points = _chamfer_path_points([(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu"), (1.0, 1.0, "F.Cu")], chamfer_offset=0.1)
    assert _canon(got[2]) == _canon(want_points), "payload carries the chamfered points"


def test_build_route_payload_coordinates_branch_with_layer():
    path = SimpleNamespace(
        path_length=1.0,
        coordinates=[(0, 0), (10, 10)],
        layer_name="B.Cu",
    )
    route = _route(path)
    _assert_payload_same(path, route, "SW_NODE", 0, [(0.0, 0.0), (10.0, 10.0)], "coordinates branch")
    got = _to.run_build_route_payload(path, route, "SW_NODE", 0, 2)
    assert got[2] == [(0.0, 0.0, "B.Cu"), (10.0, 10.0, "B.Cu")], "coordinates use path.layer_name"


def test_build_route_payload_coordinates_branch_default_layer():
    path = SimpleNamespace(path_length=1.0, coordinates=[(0, 0), (10, 10)])  # no layer_name
    route = _route(path)
    _assert_payload_same(path, route, "NET1", 4, [(0.0, 0.0), (10.0, 10.0)], "default layer")
    got = _to.run_build_route_payload(path, route, "NET1", 4, 2)
    assert got[2] == [(0.0, 0.0, "F.Cu"), (10.0, 10.0, "F.Cu")]


def test_build_route_payload_width_snap():
    for bad in (0.0, 0, -0.5):
        route = _route(SimpleNamespace(path_length=1.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")]), width=bad)
        _assert_payload_same(route.path, route, "NET1", 1, [(0.0, 0.0), (1.0, 0.0)], f"width {bad!r}")
        assert _to.run_build_route_payload(route.path, route, "NET1", 1, 2)[3] == 0.2
    # Missing width_mm -> default 0.2
    route = SimpleNamespace(path=SimpleNamespace(path_length=1.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")]), vias=[])
    _assert_payload_same(route.path, route, "NET1", 1, [(0.0, 0.0), (1.0, 0.0)], "missing width")
    assert _to.run_build_route_payload(route.path, route, "NET1", 1, 2)[3] == 0.2
    # NaN survives (truthy, never <= 0.0) -- float NaN equality-free check.
    route = _route(SimpleNamespace(path_length=1.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")]), width=float("nan"))
    got = _to.run_build_route_payload(route.path, route, "NET1", 1, 2)
    assert got[3] != got[3], "NaN width must survive the snap"


def test_build_route_payload_vias_extraction_order():
    vias = [
        SimpleNamespace(position=(1.0, 2.0), diameter=0.6, drill=0.3, from_layer="F.Cu", to_layer="B.Cu"),
        SimpleNamespace(position=(3.0, 4.0), diameter=0.8, drill=0.4, from_layer="In1.Cu", to_layer="In2.Cu"),
    ]
    path = SimpleNamespace(path_length=0.0, coordinates=[])
    route = _route(path, vias=vias)
    _assert_payload_same(path, route, "NET1", 7, [], "via order")
    got = _to.run_build_route_payload(path, route, "NET1", 7, 0)
    assert got[5] == [
        (1.0, 2.0, 0.6, 0.3, "F.Cu", "B.Cu"),
        (3.0, 4.0, 0.8, 0.4, "In1.Cu", "In2.Cu"),
    ]


def test_build_route_payload_many_randomized():
    rng = random.Random(20260812)
    for _ in range(30):
        n = rng.randint(0, 8)
        pts = [(rng.uniform(0, 5), rng.uniform(0, 5), "F.Cu") for _ in range(n)]
        path = SimpleNamespace(path_length=rng.choice([0.0, 0.5, 2.0]), segments=pts)
        vias = [
            SimpleNamespace(position=(rng.uniform(0, 5), rng.uniform(0, 5)), diameter=0.6, drill=0.3, from_layer="F.Cu", to_layer="B.Cu")
            for _ in range(rng.randint(0, 3))
        ]
        route = _route(path, width=rng.choice([0.2, 0.5, 0.0, -1.0]), vias=vias)
        pads = [(0.0, 0.0)] * rng.randint(0, 4)
        _assert_payload_same(path, route, f"N{rng.randint(0, 3)}", rng.randint(0, 9), pads, f"randomized {_}")

    # randomized coordinates branch
    for _ in range(10):
        n = rng.randint(2, 8)
        coords = [(rng.uniform(0, 5), rng.uniform(0, 5)) for _ in range(n)]
        path = SimpleNamespace(path_length=1.0, coordinates=coords, layer_name="B.Cu")
        route = _route(path)
        _assert_payload_same(path, route, "NET1", 1, [(0.0, 0.0)] * 2, f"randomized coords {_}")


# ---------------------------------------------------------------------------
# run_build_routing_result
# ---------------------------------------------------------------------------


def _routing_results(**attrs):
    base = {"compiled_routes": {}, "failed_nets": [], "net_reports": []}
    base.update(attrs)
    return SimpleNamespace(**base)


def _minimal_result(**extra):
    result = SimpleNamespace(
        stage4=SimpleNamespace(routing_results=_routing_results()),
        completion_rate=0.5,
    )
    for k, v in extra.items():
        setattr(result, k, v)
    return result


def test_build_routing_result_empty_result():
    _assert_result_same(_minimal_result(), "empty result")


def test_build_routing_result_failed_nets_passthrough():
    result = _minimal_result()
    result.stage4.routing_results.failed_nets = ["SPI_MOSI", "NET2"]
    _assert_result_same(result, "failed nets")
    got = shim_build_routing_result(result)
    assert got.unrouted_nets == ["SPI_MOSI", "NET2"]


def test_build_routing_result_preserves_rust_extracted_failure_evidence():
    report = SimpleNamespace(
        failure_reason="pad_layer_landing_blocked:source",
        blocking_nets=["HV_OBSTACLE", "GND"],
        attempted_ripups=0,
        congestion_region=(12.5, 9.25),
        pin_count=3,
        rule_id="pad_layer_landing",
        domain="signal",
    )
    result = _minimal_result()
    result.stage4.pathfinding_result = SimpleNamespace(
        failure_reports={"SPI_MOSI": report}
    )

    got = shim_build_routing_result(result)

    assert list(got.failure_reports) == ["SPI_MOSI"]
    preserved = got.failure_reports["SPI_MOSI"]
    assert preserved.failure_reason == "pad_layer_landing_blocked:source"
    assert preserved.blocking_nets == ["HV_OBSTACLE", "GND"]
    assert preserved.congestion_region == (12.5, 9.25)
    assert preserved.rule_id == "pad_layer_landing"
    assert preserved.attribution_gap is False


def test_build_routing_result_forced_segment_nets():
    rr = _routing_results(
        compiled_routes={
            "SW_NODE": SimpleNamespace(
                path=SimpleNamespace(forced_segment_count=1),
            ),
            "OK_NET": SimpleNamespace(path=SimpleNamespace(forced_segment_count=0)),
            "NO_PATH": SimpleNamespace(),  # no .path -> getattr default 0
            "NO_COMPILED_PATH": SimpleNamespace(path=None),  # path None -> 0
        },
    )
    result = SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=1.0)
    _assert_result_same(result, "forced segments")
    got = shim_build_routing_result(result)
    assert got.forced_segment_nets == ["SW_NODE"]


def test_build_routing_result_net_report_drc_violations():
    rr = _routing_results(
        net_reports=[
            SimpleNamespace(net_name="A", drc_violations=2, message="two violations"),
            SimpleNamespace(net_name="B", drc_violations=0, message="clean"),
            SimpleNamespace(net_name="C", message="missing drc_violations -> 0"),
            SimpleNamespace(drc_violations=3),  # missing net_name -> "unknown"
        ],
    )
    result = SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=0.0)
    _assert_result_same(result, "report violations")
    got = shim_build_routing_result(result)
    assert len(got.drc_violations) == 2
    assert got.drc_violations[0].net_name == "A" and got.drc_violations[0].count == 2
    assert got.drc_violations[0].message == "two violations"
    assert got.drc_violations[0].type == "unknown"
    assert got.drc_violations[1].net_name == "unknown"


def test_build_routing_result_congestion_regions():
    rr = _routing_results(
        net_reports=[
            SimpleNamespace(
                net_name="NET1",
                bottleneck=SimpleNamespace(
                    pair_kind="component_edge",
                    component_pair=("C1", "C2"),
                    current_gap_mm=0.35,
                    positions_mm=((1.0, 2.0), (3.0, 4.0)),
                ),
            ),
            SimpleNamespace(
                net_name="NET2",
                bottleneck=SimpleNamespace(pair_kind="component_keepout", component_pair=("C3", "keepout:HS1")),
            ),
            SimpleNamespace(
                net_name="NET3",
                bottleneck=SimpleNamespace(pair_kind="component_component"),  # not collected
            ),
            SimpleNamespace(net_name="NET4", bottleneck=None),
            SimpleNamespace(net_name="NET5"),  # missing bottleneck
        ],
    )
    result = SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=0.0)
    _assert_result_same(result, "congestion regions")
    got = shim_build_routing_result(result)
    assert len(got.congestion_regions) == 2
    assert got.congestion_regions[0].net_name == "NET1"
    assert got.congestion_regions[0].comp_a == "C1" and got.congestion_regions[0].comp_b == "C2"
    assert got.congestion_regions[0].current_distance_mm == 0.35
    assert got.congestion_regions[0].positions == ((1.0, 2.0), (3.0, 4.0))
    assert got.congestion_regions[1].comp_b == "keepout:HS1"


def test_build_routing_result_manufacturing_report_appended():
    rr = _routing_results(
        net_reports=[SimpleNamespace(net_name="REPORT_NET", drc_violations=1, message="r")],
    )
    mfg = SimpleNamespace(
        violations=[
            SimpleNamespace(type="clearance", message="too close", net_name="MFG_NET", location=(0.5, 0.5)),
            SimpleNamespace(message="no type attr", net_name="MFG2"),  # defaults: type unknown, location (0,0)
        ]
    )
    result = SimpleNamespace(
        stage4=SimpleNamespace(routing_results=rr),
        completion_rate=0.0,
        manufacturing_report=mfg,
    )
    _assert_result_same(result, "mfg violations appended")
    got = shim_build_routing_result(result)
    assert [v.net_name for v in got.drc_violations] == ["REPORT_NET", "MFG_NET", "MFG2"]
    assert got.drc_violations[1].type == "clearance"
    assert got.drc_violations[1].location == (0.5, 0.5)
    assert got.drc_violations[2].type == "unknown"
    assert got.drc_violations[2].location == (0.0, 0.0)


def test_build_routing_result_topology_solved_nets():
    rr = _routing_results(failed_nets=["F"])
    result = SimpleNamespace(
        stage4=SimpleNamespace(routing_results=rr),
        completion_rate=1.0,
        stage3=SimpleNamespace(
            topology_graph=SimpleNamespace(net_topologies={"NET_A": 1, "NET_B": 2})
        ),
    )
    _assert_result_same(result, "topology solved")
    got = shim_build_routing_result(result)
    assert got.topology_solved_nets == ["NET_A", "NET_B"]

    # Missing stage3 / topology_graph / net_topologies -> []
    for extra in (
        {},
        {"stage3": SimpleNamespace()},
        {"stage3": SimpleNamespace(topology_graph=SimpleNamespace())},
        {"stage3": SimpleNamespace(topology_graph=SimpleNamespace(net_topologies={}))},
    ):
        result2 = _minimal_result(**extra)
        _assert_result_same(result2, f"topology missing {extra}")
        assert shim_build_routing_result(result2).topology_solved_nets == []


def test_build_routing_result_many_randomized():
    rng = random.Random(20260812)
    for _ in range(30):
        reports = []
        for i in range(rng.randint(0, 5)):
            attrs = {"net_name": f"N{i}"}
            if rng.random() < 0.5:
                attrs["drc_violations"] = rng.randint(0, 4)
            if rng.random() < 0.5:
                attrs["message"] = f"msg{i}"
            if rng.random() < 0.6:
                kind = rng.choice(["component_edge", "component_keepout", "component_component"])
                attrs["bottleneck"] = SimpleNamespace(
                    pair_kind=kind,
                    component_pair=(f"C{i}a", f"C{i}b"),
                    current_gap_mm=rng.uniform(0.0, 2.0),
                    positions_mm=((rng.uniform(0, 5), rng.uniform(0, 5)), (rng.uniform(0, 5), rng.uniform(0, 5))),
                )
            reports.append(SimpleNamespace(**attrs))
        compiled = {
            f"N{i}": SimpleNamespace(
                path=SimpleNamespace(forced_segment_count=rng.randint(0, 1))
            )
            for i in range(rng.randint(0, 4))
        }
        rr = _routing_results(
            failed_nets=[f"F{i}" for i in range(rng.randint(0, 4))],
            compiled_routes=compiled,
            net_reports=reports,
        )
        result = SimpleNamespace(
            stage4=SimpleNamespace(routing_results=rr),
            completion_rate=rng.uniform(0.0, 1.0),
        )
        if rng.random() < 0.4:
            result.manufacturing_report = SimpleNamespace(
                violations=[
                    SimpleNamespace(
                        type="creepage",
                        message=f"m{i}",
                        net_name=f"MN{i}",
                        location=(rng.uniform(0, 5), rng.uniform(0, 5)),
                    )
                    for i in range(rng.randint(0, 3))
                ]
            )
        if rng.random() < 0.6:
            result.stage3 = SimpleNamespace(
                topology_graph=SimpleNamespace(
                    net_topologies={f"T{i}": i for i in range(rng.randint(0, 4))}
                )
            )
        _assert_result_same(result, f"randomized {_}")


# ---------------------------------------------------------------------------
# Shim end-to-end: the E6 differential already pins _write_routes_to_content
# byte-for-byte against the pre-E6 oracle; these two tests additionally pin
# the U-H kernels through the FULL shim surface (pad positions + payload
# feeding the emission), so a payload-marshalling regression shows up as a
# content diff, not only as a payload diff.
# ---------------------------------------------------------------------------


_CONTENT = '(kicad_pcb (version 20240108) (net 1 "NET1") (net 2 "NET2") (net 3 "NET3"))'


def _full_result(compiled, *, components=(), nets=(), enable_zone_pours=False):
    routing_results = SimpleNamespace(
        compiled_routes=dict(compiled),
        tree_routes={},
        partial_tree_routes={},
    )
    pcb = SimpleNamespace(components=list(components), nets=list(nets))
    return SimpleNamespace(
        stage4=SimpleNamespace(routing_results=routing_results),
        pcb=pcb,
        enable_zone_pours=enable_zone_pours,
    )


def test_write_routes_full_shim_with_payload_marshalling():
    # Two nets with real routed paths (segments branch, chamfered corners)
    # plus vias; the shim must produce the byte-identical content the
    # pre-E6 oracle produces.
    from temper_placer.router_v6._adapter_convert import (
        _write_routes_to_content as shim_writer,
    )
    from tests.router_v6 import _adapter_convert_py_oracle as oracle_mod

    path1 = SimpleNamespace(
        path_length=2.0,
        segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu"), (1.0, 1.0, "F.Cu")],
    )
    path2 = SimpleNamespace(
        path_length=1.0,
        coordinates=[(0.0, 0.0), (2.0, 0.0)],
        layer_name="B.Cu",
    )
    via = SimpleNamespace(position=(1.0, 0.5), diameter=0.6, drill=0.3, from_layer="F.Cu", to_layer="B.Cu")
    compiled = {
        "NET1": SimpleNamespace(path=path1, width_mm=0.25, vias=[via]),
        "NET2": SimpleNamespace(path=path2, width_mm=0.3, vias=[]),
        "NET3": SimpleNamespace(path=SimpleNamespace(path_length=0.0), width_mm=0.2, vias=[]),
    }
    comps = [
        _comp("C1", pins={"1": (0.5, 0.0), "2": (1.5, 0.0)}),
        _comp("C2", pins={"1": (0.0, 1.0)}),
    ]
    nets = [_net("NET1", [("C1", "1"), ("C2", "1")]), _net("NET2", [("C1", "2")])]
    result = _full_result(compiled, components=comps, nets=nets)

    want_content, want_pads = oracle_mod._write_routes_to_content(_CONTENT, result)
    got_content, got_pads = shim_writer(_CONTENT, result)
    assert got_content == want_content, "routed content must be byte-identical to the pre-E6 oracle"
    assert _canon(got_pads) == _canon(want_pads)


def test_write_routes_full_shim_randomized_payloads():
    from tests.router_v6 import _adapter_convert_py_oracle as oracle_mod

    rng = random.Random(20260812)
    for _ in range(15):
        compiled = {}
        comps = [_comp(f"C{i}", pins={"1": (float(i), 0.0)}) for i in range(4)]
        nets = []
        for n in range(rng.randint(0, 3)):
            name = f"NET{n}"
            npts = rng.randint(0, 6)
            pts = [(rng.uniform(0, 4), rng.uniform(0, 4), "F.Cu") for _ in range(npts)]
            path = SimpleNamespace(path_length=rng.choice([0.0, 1.0, 3.0]), segments=pts)
            vias = [
                SimpleNamespace(position=(rng.uniform(0, 4), rng.uniform(0, 4)), diameter=0.6, drill=0.3, from_layer="F.Cu", to_layer="B.Cu")
                for _ in range(rng.randint(0, 2))
            ]
            compiled[name] = SimpleNamespace(path=path, width_mm=rng.choice([0.2, 0.4, 0.0]), vias=vias)
            nets.append(_net(name, [("C0", "1"), ("C1", "1")]))
        result = _full_result(compiled, components=comps, nets=nets)
        want_content, want_pads = oracle_mod._write_routes_to_content(_CONTENT, result)
        got_content, got_pads = shim_write_routes(_CONTENT, result)
        assert got_content == want_content, f"content differs on randomized case {_}"
        assert _canon(got_pads) == _canon(want_pads)
