"""U5/R4: KiCad writer coverage for compiled-route transition vias."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.adapter import _write_routes_to_content
from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.routing_results import CompiledRoute, CompiledTreeRoute
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry
from temper_placer.router_v6.via_placement import Via, place_vias

_PCB_CONTENT = """(kicad_pcb (version 20221018) (generator "test")
  (general (thickness 1.6))
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
  (setup (pad_to_mask_clearance 0))
  (net 1 "NET_A")
  (net 2 "NET_B")
  (net 7 "HV_NET")
)\n"""


def _compiled_route(net_name: str, vias: list[Via], path: object | None = None) -> CompiledRoute:
    return CompiledRoute(
        net_name=net_name,
        path=path or SimpleNamespace(path_length=0.0),
        width_mm=0.2,
        vias=vias,
        matched_length_mm=None,
    )


def _writer_result(routes: dict[str, CompiledRoute], pcb: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        stage4=SimpleNamespace(routing_results=SimpleNamespace(compiled_routes=routes)),
        pcb=pcb,
    )


def _writer_result_with_partial(
    partial_routes: dict[str, CompiledRoute], pcb: object | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(compiled_routes={}, partial_routes=partial_routes)
        ),
        pcb=pcb,
    )


def _writer_pcb_for_route(net_name: str, endpoint: tuple[float, float]) -> SimpleNamespace:
    """Minimal PCB model whose pads coincide with a generated test path."""
    return SimpleNamespace(
        components=[
            SimpleNamespace(ref="U1", initial_position=(0.0, 0.0)),
            SimpleNamespace(ref="U2", initial_position=endpoint),
        ],
        nets=[SimpleNamespace(name=net_name, pins=[("U1", "1"), ("U2", "1")])],
    )


def _via_prefix(via: Via, net_number: int) -> str:
    x, y = via.position
    return (
        f"  (via (at {x:.4f} {y:.4f}) (size {via.diameter:.4f})"
        f' (drill {via.drill:.4f}) (layers "{via.from_layer}" "{via.to_layer}")'
        f" (net {net_number})"
    )


def test_writer_emits_every_compiled_via_with_its_own_net_and_geometry() -> None:
    vias_a = [Via((10.25, 20.5), "F.Cu", "B.Cu", 0.6, 0.3, "NET_A")]
    vias_b = [
        Via((30.125, 40.75), "In1.Cu", "In2.Cu", 1.2, 0.6, "NET_B"),
        Via((31.0, 41.0), "In2.Cu", "B.Cu", 0.4, 0.2, "NET_B"),
    ]
    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result(
            {
                "NET_A": _compiled_route("NET_A", vias_a),
                "NET_B": _compiled_route("NET_B", vias_b),
            }
        ),
    )

    assert output.count("\n  (via ") == 3
    assert _via_prefix(vias_a[0], 1) in output
    assert all(_via_prefix(via, 2) in output for via in vias_b)
    tstamp_values = re.findall(r'\(via .*?\(tstamp "([^"]+)"\)\)', output)
    assert len(tstamp_values) == 3
    assert len(set(tstamp_values)) == 3


def test_writer_via_only_route_is_not_lost_to_empty_segment_early_return() -> None:
    via = Via((10.0, 20.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET_A")

    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result({"NET_A": _compiled_route("NET_A", [via])}),
    )

    assert _via_prefix(via, 1) in output
    assert "(segment " not in output


def test_writer_with_no_vias_preserves_existing_no_output_behavior() -> None:
    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result({"NET_A": _compiled_route("NET_A", [])}),
    )

    assert output == _PCB_CONTENT
    assert "(via " not in output


def test_writer_serializes_partial_prefix_without_pad_stitch_or_plane_mst() -> None:
    partial = _compiled_route(
        "NET_A", [], RoutePath("NET_A", [(0.0, 0.0), (10.0, 0.0)], "F.Cu", 10.0)
    )
    pcb = SimpleNamespace(
        components=[
            SimpleNamespace(ref="U1", initial_position=(0.0, 0.0)),
            SimpleNamespace(ref="U2", initial_position=(10.0, 0.0)),
            SimpleNamespace(ref="U3", initial_position=(40.0, 0.0)),
        ],
        nets=[SimpleNamespace(name="NET_A", pins=[("U1", "1"), ("U2", "1"), ("U3", "1")])],
    )

    output = _write_routes_to_content(_PCB_CONTENT, _writer_result_with_partial({"NET_A": partial}, pcb))

    assert output.count("(segment ") == 1
    assert '(start 0.0000 0.0000) (end 10.0000 0.0000)' in output
    assert "40.0000" not in output


def test_writer_serializes_tree_branches_without_sibling_bridge() -> None:
    root = PadIdentity("U1", "1", "NET_A", 0.0, 0.0, (0,))
    right = PadIdentity("U2", "1", "NET_A", 10.0, 0.0, (0,))
    top = PadIdentity("U3", "1", "NET_A", 0.0, 10.0, (0,))
    geometry = TreeRouteGeometry(
        "NET_A",
        (
            TreeRouteBranch(TerminalTreeEdge(root, right), RoutePath("NET_A", [(0, 0), (10, 0)], "F.Cu", 10.0)),
            TreeRouteBranch(TerminalTreeEdge(root, top), RoutePath("NET_A", [(0, 0), (0, 10)], "F.Cu", 10.0)),
        ),
    )
    result = SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes={}, partial_routes={},
                tree_routes={"NET_A": CompiledTreeRoute("NET_A", geometry, 0.37, [])},
                partial_tree_routes={},
            )
        ),
        pcb=SimpleNamespace(
            components=[
                SimpleNamespace(ref="U1", initial_position=(0.0, 0.0)),
                SimpleNamespace(ref="U2", initial_position=(10.0, 0.0)),
                SimpleNamespace(ref="U3", initial_position=(0.0, 10.0)),
            ],
            nets=[SimpleNamespace(name="NET_A", pins=[("U1", "1"), ("U2", "1"), ("U3", "1")])],
        ),
    )

    output = _write_routes_to_content(_PCB_CONTENT, result)

    assert '(start 0.0000 0.0000) (end 10.0000 0.0000)' in output
    assert '(start 0.0000 0.0000) (end 0.0000 10.0000)' in output
    assert '(start 10.0000 0.0000) (end 0.0000 10.0000)' not in output
    assert output.count("(width 0.3700)") == 2


@given(
    start_x=st.integers(min_value=0, max_value=20),
    length=st.integers(min_value=1, max_value=20),
    orphan_gap=st.integers(min_value=10, max_value=40),
)
@settings(max_examples=30, deadline=30_000)
def test_partial_prefix_writer_never_fabricates_an_unreached_pad(
    start_x: int, length: int, orphan_gap: int
) -> None:
    end_x = start_x + length
    orphan_x = end_x + orphan_gap
    partial = _compiled_route(
        "NET_A", [], RoutePath("NET_A", [(start_x, 0.0), (end_x, 0.0)], "F.Cu", float(length))
    )
    pcb = SimpleNamespace(
        components=[
            SimpleNamespace(ref="U1", initial_position=(start_x, 0.0)),
            SimpleNamespace(ref="U2", initial_position=(end_x, 0.0)),
            SimpleNamespace(ref="U3", initial_position=(orphan_x, 0.0)),
        ],
        nets=[SimpleNamespace(name="NET_A", pins=[("U1", "1"), ("U2", "1"), ("U3", "1")])],
    )

    output = _write_routes_to_content(_PCB_CONTENT, _writer_result_with_partial({"NET_A": partial}, pcb))

    assert output.count("(segment ") == 1
    assert f"{orphan_x:.4f}" not in output


def test_u3_u4_via_data_preserves_layer_span_and_netclass_size_into_kicad() -> None:
    path = RoutePath3D(
        net_name="HV_NET",
        segments=[(0.0, 0.0, "In1.Cu"), (1.0, 1.0, "In1.Cu"), (1.0, 1.0, "In2.Cu")],
        via_positions=[(1.0, 1.0)],
        path_length=1.0,
        via_count=1,
    )
    rules = DesignRules(
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
        net_class_assignments={"HV_NET": "HighVoltage"},
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                clearance_mm=6.0,
                trace_width_mm=3.0,
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
            )
        },
    )
    placed = place_vias(
        PathfindingResult(routed_paths={"HV_NET": path}, failed_nets=[]),
        design_rules=rules,
    ).vias

    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result({"HV_NET": _compiled_route("HV_NET", placed)}),
    )

    assert [_via_prefix(via, 7) for via in placed] == [
        '  (via (at 1.0000 1.0000) (size 1.2000) (drill 0.6000) (layers "In1.Cu" "In2.Cu") (net 7)'
    ]
    assert _via_prefix(placed[0], 7) in output


def test_u6_writes_3d_route_segments_on_their_actual_layer() -> None:
    path = RoutePath3D(
        net_name="NET_A",
        segments=[(0.0, 0.0, "B.Cu"), (1.0, 0.0, "B.Cu")],
        via_positions=[],
        path_length=1.0,
    )
    pcb = SimpleNamespace(
        components=[
            SimpleNamespace(ref="U1", initial_position=(0.0, 0.0)),
            SimpleNamespace(ref="U2", initial_position=(1.0, 0.0)),
        ],
        nets=[SimpleNamespace(name="NET_A", pins=[("U1", "1"), ("U2", "1")])],
    )

    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result({"NET_A": _compiled_route("NET_A", [], path)}, pcb=pcb),
    )

    assert (
        '(segment (start 0.0000 0.0000) (end 1.0000 0.0000) (width 0.2000) (layer "B.Cu") (net 1)'
        in output
    )
    assert '(layer "F.Cu") (net 1)' not in output


def test_u6_pad_stitch_remains_on_f_cu_when_nearest_route_node_is_b_cu() -> None:
    """A pad stitch must join the F.Cu pad-side of an explicit transition."""
    path = RoutePath3D(
        net_name="NET_A",
        segments=[(0.0, 0.0, "B.Cu"), (1.0, 0.0, "B.Cu")],
        via_positions=[],
        path_length=1.0,
    )
    pcb = _writer_pcb_for_route("NET_A", (2.0, 0.0))

    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result({"NET_A": _compiled_route("NET_A", [], path)}, pcb=pcb),
    )

    assert (
        '(segment (start 1.0000 0.0000) (end 2.0000 0.0000) '
        '(width 0.2000) (layer "F.Cu") (net 1)'
    ) in output
    assert (
        '(via (at 1.0000 0.0000) (size 0.6000) (drill 0.3000) '
        '(layers "F.Cu" "B.Cu") (net 1)'
    ) in output


@pytest.mark.property
@given(
    layers=st.lists(
        st.sampled_from(("F.Cu", "B.Cu", "In1.Cu", "In2.Cu")), min_size=1, max_size=8
    )
)
@settings(max_examples=100, deadline=5000)
def test_u6_writer_pbt_preserves_each_same_layer_run_without_cross_layer_tracks(
    layers: list[str],
) -> None:
    """U6/R5: each emitted track is an in-layer run of the 3D path."""
    points: list[tuple[float, float, str]] = [(0.0, 0.0, layers[0])]
    for index, layer in enumerate(layers):
        if index and layer != layers[index - 1]:
            points.append((float(index), 0.0, layer))
        points.append((float(index + 1), 0.0, layer))
    path = RoutePath3D(
        net_name="NET_A",
        segments=points,
        via_positions=[],
        path_length=float(len(layers)),
    )
    pcb = _writer_pcb_for_route("NET_A", (float(len(layers)), 0.0))
    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result({"NET_A": _compiled_route("NET_A", [], path)}, pcb=pcb),
    )

    expected: list[tuple[float, float, str]] = []
    run_start = 0
    for index in range(1, len(layers) + 1):
        if index == len(layers) or layers[index] != layers[index - 1]:
            expected.append((float(run_start), float(index), layers[index - 1]))
            run_start = index
    emitted = [
        (float(start), float(end), layer)
        for start, end, layer in re.findall(
            r'\(segment \(start ([\d.-]+) 0\.0000\) '
            r'\(end ([\d.-]+) 0\.0000\) \(width [\d.]+\) '
            r'\(layer "([^"]+)"\)',
            output,
        )
    ]
    assert emitted == expected


@st.composite
def _net_via_sequences(draw) -> dict[str, list[Via]]:
    layers = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    net_names = draw(
        st.lists(st.sampled_from(("NET_A", "NET_B")), min_size=1, max_size=2, unique=True)
    )
    routes: dict[str, list[Via]] = {}
    for net_name in net_names:
        via_count = draw(st.integers(min_value=0, max_value=5))
        vias: list[Via] = []
        for _ in range(via_count):
            from_layer = draw(st.sampled_from(layers))
            to_layer = draw(
                st.sampled_from(tuple(layer for layer in layers if layer != from_layer))
            )
            diameter = draw(st.floats(0.4, 1.5, allow_nan=False, allow_infinity=False))
            vias.append(
                Via(
                    position=(
                        draw(st.floats(0, 100, allow_nan=False, allow_infinity=False)),
                        draw(st.floats(0, 100, allow_nan=False, allow_infinity=False)),
                    ),
                    from_layer=from_layer,
                    to_layer=to_layer,
                    diameter=diameter,
                    drill=draw(
                        st.floats(
                            0.1,
                            diameter - 0.01,
                            allow_nan=False,
                            allow_infinity=False,
                        )
                    ),
                    net_name=net_name,
                )
            )
        routes[net_name] = vias
    return routes


@pytest.mark.property
@given(routes=_net_via_sequences())
@settings(max_examples=100, deadline=15000)
def test_writer_preserves_each_valid_via_sequence_and_distinct_net_mapping(
    routes: dict[str, list[Via]],
) -> None:
    output = _write_routes_to_content(
        _PCB_CONTENT,
        _writer_result(
            {net_name: _compiled_route(net_name, vias) for net_name, vias in routes.items()}
        ),
    )

    net_numbers = {"NET_A": 1, "NET_B": 2}
    assert output.count("\n  (via ") == sum(len(vias) for vias in routes.values())
    for net_name, vias in routes.items():
        assert all(_via_prefix(via, net_numbers[net_name]) in output for via in vias)


@pytest.mark.skipif(
    shutil.which("kicad-cli") is None, reason="kicad-cli is required for syntax validation"
)
def test_emitted_via_s_expression_parses_in_kicad_drc(tmp_path: Path) -> None:
    board = tmp_path / "via-output.kicad_pcb"
    report = tmp_path / "via-output-drc.json"
    via = Via((110.0, 90.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET_A")
    board.write_text(
        _write_routes_to_content(
            _PCB_CONTENT,
            _writer_result({"NET_A": _compiled_route("NET_A", [via])}),
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["kicad-cli", "pcb", "drc", "--format", "json", "--output", str(report), str(board)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert report.exists(), completed.stderr
