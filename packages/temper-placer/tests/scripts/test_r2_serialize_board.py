"""Tests for ``tools/wasm/r2_serialize_board.py``'s K1 ``board_dict`` builder.

Issue #873: the WASM verification tier's R2 board producer
(``tools/wasm/r2_serialize_board.py::build_board_dict``) never populated the
K1 schema's optional ``traces``/``vias``/``zones`` keys, so every
routing-family DRC rule benchmarked by
``packages/temper-drc-rs/examples/r2_full_board_pass.rs`` ran against an
empty board even though the Rust side
(``packages/temper-drc-rs/src/board_py_bridge.rs``'s ``build_board_state``
and ``packages/temper-drc-rs/src/board.rs``'s ``BoardState``) already fully
supported them. These tests exercise the three new helper functions
(``_traces_from_parsed``, ``_vias_from_parsed``, ``_zones_from_parsed``)
directly against lightweight stand-ins for the ``ParsedPCB`` shape returned
by ``temper_placer.io.kicad_parser.parse_kicad_pcb_v6``, without requiring a
real ``.kicad_pcb`` file or the compiled parser extension.

Module import follows the ``importlib.util.spec_from_file_location``
pattern used elsewhere for testing standalone scripts outside the package
tree (see ``tests/geometry/test_drc_inflate_rust_differential.py``'s oracle
loader) -- ``tools/wasm`` is not on ``pythonpath`` and is not a package.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[4] / "tools" / "wasm" / "r2_serialize_board.py"
)
_spec = importlib.util.spec_from_file_location("r2_serialize_board", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
r2_serialize_board = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r2_serialize_board)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REAL_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"


# ---------------------------------------------------------------------------
# Lightweight stand-ins for the ParsedPCB / TraceData / ViaData / Zone shapes
# the real parser (temper_design_bundle_python.parse_engine) returns. Only
# the attributes build_board_dict's helpers actually read are populated.
# ---------------------------------------------------------------------------


@dataclass
class _FakeTrack:
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: str | None


@dataclass
class _FakeVia:
    position: tuple[float, float]
    diameter: float
    drill: float
    net: str | None
    layers: tuple[str, ...]


@dataclass
class _FakeZone:
    net_classes: list[str]
    polygon: list[tuple[float, float]] | None
    layers: list[str]


@dataclass
class _FakeBoard:
    width: float = 172.0
    height: float = 234.0
    origin: tuple[float, float] = (0.0, 0.0)


@dataclass
class _FakeParsed:
    tracks: list[_FakeTrack] = field(default_factory=list)
    vias: list[_FakeVia] = field(default_factory=list)
    zones: list[_FakeZone] = field(default_factory=list)
    board: _FakeBoard = field(default_factory=_FakeBoard)
    components: list[Any] = field(default_factory=list)
    nets: list[Any] = field(default_factory=list)
    design_rules: Any = field(
        default_factory=lambda: SimpleNamespace(net_classes={})
    )


# ---------------------------------------------------------------------------
# _traces_from_parsed
# ---------------------------------------------------------------------------


def test_traces_from_parsed_preserves_count_and_fields():
    parsed = _FakeParsed(
        tracks=[
            _FakeTrack((0.0, 0.0), (1.0, 1.0), 0.25, "F.Cu", "GND"),
            _FakeTrack((1.0, 1.0), (2.0, 3.0), 0.3, "In1.Cu", "+340V_BUS"),
            _FakeTrack((5.0, 5.0), (5.0, 6.0), 0.2, "B.Cu", None),
        ]
    )
    out = r2_serialize_board._traces_from_parsed(parsed)
    assert len(out) == 3
    assert out[0] == {
        "net": "GND",
        "layer": "F.Cu",
        "width": 0.25,
        "segments": [[0.0, 0.0, 1.0, 1.0]],
    }
    assert out[1]["net"] == "+340V_BUS"
    assert out[1]["layer"] == "In1.Cu"
    assert out[1]["segments"] == [[1.0, 1.0, 2.0, 3.0]]
    # A segment with no net (None) becomes "" -- extract_str in
    # board_py_bridge.rs requires a string, not an Optional.
    assert out[2]["net"] == ""


def test_traces_from_parsed_empty_input_yields_empty_output():
    assert r2_serialize_board._traces_from_parsed(_FakeParsed()) == []


def test_traces_from_parsed_groups_same_net_layer_segments():
    """Segments sharing a ``(net, layer)`` key must land in ONE entry, not
    one entry each. ``drc_trace_clearance``
    (``packages/temper-drc-rs/src/rules/drc/trace_clearance.rs``) never
    compares segments *within* one ``board.traces`` entry against each
    other, only *across* entries -- so two connected segments of the same
    physical route (which share an endpoint, i.e. touch at 0mm by
    construction) must be in the same entry, or the check misreads their
    shared junction as a same-net clearance violation. A 1:1
    segment-to-entry mapping produced exactly that: 2,911 spurious
    ``drc_trace_clearance`` violations against the committed board, every
    one a net compared against itself at ~0mm.
    """
    parsed = _FakeParsed(
        tracks=[
            _FakeTrack((0.0, 0.0), (1.0, 0.0), 0.25, "F.Cu", "GND"),
            # Second segment of the same physical route: shares the (1,0)
            # endpoint with the first, same net, same layer.
            _FakeTrack((1.0, 0.0), (2.0, 1.0), 0.25, "F.Cu", "GND"),
            # Different net, same layer -> stays a separate entry.
            _FakeTrack((5.0, 5.0), (6.0, 6.0), 0.25, "F.Cu", "+340V_BUS"),
            # Same net as the first two, different layer -> separate entry.
            _FakeTrack((0.0, 0.0), (1.0, 0.0), 0.25, "In1.Cu", "GND"),
        ]
    )
    out = r2_serialize_board._traces_from_parsed(parsed)
    assert len(out) == 3
    by_key = {(t["net"], t["layer"]): t for t in out}
    assert set(by_key) == {("GND", "F.Cu"), ("+340V_BUS", "F.Cu"), ("GND", "In1.Cu")}
    assert by_key[("GND", "F.Cu")]["segments"] == [
        [0.0, 0.0, 1.0, 0.0],
        [1.0, 0.0, 2.0, 1.0],
    ]
    # Total line-segment count is preserved regardless of grouping -- the
    # "N segments in -> N segments in BoardState" invariant.
    assert sum(len(t["segments"]) for t in out) == 4


# ---------------------------------------------------------------------------
# _vias_from_parsed
# ---------------------------------------------------------------------------


def test_vias_from_parsed_preserves_count_and_fields():
    parsed = _FakeParsed(
        vias=[
            _FakeVia((10.0, 20.0), 0.6, 0.3, "GND", ("F.Cu", "B.Cu")),
            _FakeVia((30.0, 40.0), 0.8, 0.4, None, ("F.Cu", "In1.Cu", "B.Cu")),
        ]
    )
    out = r2_serialize_board._vias_from_parsed(parsed)
    assert len(out) == 2
    assert out[0] == {
        "net": "GND",
        "x": 10.0,
        "y": 20.0,
        "drill": 0.3,
        "pad": 0.6,
        "from_layer": "F.Cu",
        "to_layer": "B.Cu",
    }
    # No net -> "" (not None); multi-layer via -> first/last layer span.
    assert out[1]["net"] == ""
    assert out[1]["from_layer"] == "F.Cu"
    assert out[1]["to_layer"] == "B.Cu"


def test_vias_from_parsed_defaults_layers_when_missing():
    parsed = _FakeParsed(vias=[_FakeVia((0.0, 0.0), 0.6, 0.3, "GND", ())])
    out = r2_serialize_board._vias_from_parsed(parsed)
    assert out[0]["from_layer"] == "F.Cu"
    assert out[0]["to_layer"] == "B.Cu"


# ---------------------------------------------------------------------------
# _zones_from_parsed
# ---------------------------------------------------------------------------


def test_zones_from_parsed_one_entry_per_zone_layer_pair():
    parsed = _FakeParsed(
        zones=[
            _FakeZone(
                net_classes=["GND"],
                polygon=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
                layers=["F.Cu", "B.Cu"],
            ),
        ]
    )
    out = r2_serialize_board._zones_from_parsed(parsed)
    # One CopperZone per (zone, layer) pair -- CopperZone is single-layer
    # on the Rust side (board.rs), a KiCad zone can span multiple layers.
    assert len(out) == 2
    assert {z["layer"] for z in out} == {"F.Cu", "B.Cu"}
    assert all(z["net"] == "GND" for z in out)
    assert all(z["polygon"] == [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]] for z in out)


def test_zones_from_parsed_skips_zones_with_no_polygon():
    parsed = _FakeParsed(
        zones=[_FakeZone(net_classes=["GND"], polygon=None, layers=["F.Cu"])]
    )
    assert r2_serialize_board._zones_from_parsed(parsed) == []


def test_zones_from_parsed_defaults_net_and_layer_when_absent():
    parsed = _FakeParsed(
        zones=[_FakeZone(net_classes=[], polygon=[(1.0, 1.0)], layers=[])]
    )
    out = r2_serialize_board._zones_from_parsed(parsed)
    assert len(out) == 1
    assert out[0]["net"] == ""
    assert out[0]["layer"] == "F.Cu"


def test_zones_from_parsed_polygon_passes_through_unchanged():
    """``extract_zones_pure`` (``parse_engine.rs``) always subtracts the
    board's Edge.Cuts origin from zone polygon points regardless of the
    ``normalize`` flag, so ``z.polygon`` already arrives in board-local
    ``[0, width_mm] x [0, height_mm]`` coordinates. ``_zones_from_parsed``
    must NOT re-shift it -- ``routing_copper_pullback``
    (``packages/temper-drc-rs/src/rules/routing/copper_pullback.rs``) reads
    ``board.width_mm``/``height_mm`` as an absolute ``[0, width]`` frame, so
    adding the origin back would push real zones past that boundary and
    fabricate board-edge-margin violations that aren't real (measured: 44
    spurious ``routing_copper_pullback`` errors against the committed board
    with an earlier, incorrect version of this function that did add the
    origin back).
    """
    parsed = _FakeParsed(
        board=_FakeBoard(origin=(20.0, 20.0)),
        zones=[
            _FakeZone(
                net_classes=["GND"],
                polygon=[(0.0, 0.0), (5.0, 0.0)],
                layers=["F.Cu"],
            ),
        ],
    )
    out = r2_serialize_board._zones_from_parsed(parsed)
    assert out[0]["polygon"] == [[0.0, 0.0], [5.0, 0.0]]


def test_traces_from_parsed_subtracts_board_origin():
    """Traces must land in the same board-local frame as zones (see
    ``test_zones_from_parsed_polygon_passes_through_unchanged``) --
    ``routing_split_plane_crossing`` cross-references trace segment
    midpoints against zone polygons
    (``packages/temper-drc-rs/src/rules/routing/split_plane_crossing.rs``),
    so a frame mismatch between the two would silently break every such
    geometric comparison.
    """
    parsed = _FakeParsed(
        board=_FakeBoard(origin=(20.0, 20.0)),
        tracks=[_FakeTrack((20.0, 20.0), (25.0, 30.0), 0.25, "F.Cu", "GND")],
    )
    out = r2_serialize_board._traces_from_parsed(parsed)
    assert out[0]["segments"] == [[0.0, 0.0, 5.0, 10.0]]


def test_vias_from_parsed_subtracts_board_origin():
    parsed = _FakeParsed(
        board=_FakeBoard(origin=(20.0, 20.0)),
        vias=[_FakeVia((30.0, 45.0), 0.6, 0.3, "GND", ("F.Cu", "B.Cu"))],
    )
    out = r2_serialize_board._vias_from_parsed(parsed)
    assert out[0]["x"] == 10.0
    assert out[0]["y"] == 25.0


def test_build_board_dict_components_subtract_board_origin():
    """Components must share the same board-local frame as
    traces/vias/zones (``drc_zone_containment`` cross-references component
    centers against zone polygons — a frame mismatch there would make every
    zone-assigned component look like it's outside its zone)."""
    fake_component = SimpleNamespace(
        ref="C1",
        initial_position=(30.0, 45.0),
        initial_rotation=0.0,
        initial_side=0,
        footprint="0805",
        width=1.0,
        height=1.0,
        net_class="Signal",
    )
    parsed = _FakeParsed(
        board=_FakeBoard(origin=(20.0, 20.0)),
        components=[fake_component],
    )
    board_dict = r2_serialize_board.build_board_dict(parsed)
    assert board_dict["components"][0]["x"] == 10.0
    assert board_dict["components"][0]["y"] == 25.0


# ---------------------------------------------------------------------------
# build_board_dict — end-to-end wiring
# ---------------------------------------------------------------------------


def test_build_board_dict_includes_routing_data_keys():
    # 5 segments across 5 *distinct* nets -> 5 groups in _traces_from_parsed
    # (same-net segments would collapse into one group; see
    # test_traces_from_parsed_groups_same_net_layer_segments below).
    parsed = _FakeParsed(
        tracks=[
            _FakeTrack((0.0, 0.0), (1.0, 0.0), 0.2, "F.Cu", f"NET_{i}") for i in range(5)
        ],
        vias=[_FakeVia((0.0, 0.0), 0.6, 0.3, "GND", ("F.Cu", "B.Cu"))] * 3,
        zones=[_FakeZone(["GND"], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], ["F.Cu"])] * 2,
    )
    board_dict = r2_serialize_board.build_board_dict(parsed)
    assert len(board_dict["traces"]) == 5
    assert sum(len(t["segments"]) for t in board_dict["traces"]) == 5
    assert len(board_dict["vias"]) == 3
    assert len(board_dict["zones"]) == 2


def test_build_board_dict_empty_board_still_has_empty_routing_keys():
    board_dict = r2_serialize_board.build_board_dict(_FakeParsed())
    assert board_dict["traces"] == []
    assert board_dict["vias"] == []
    assert board_dict["zones"] == []


# ---------------------------------------------------------------------------
# Real-board determinism (task requirement: "two builds of the same board
# produce identical output"), against the actual committed
# pcb/temper.kicad_pcb -- not just the synthetic fixtures above.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_traces_vias_zones_are_deterministic_across_parses():
    """Parse the committed board twice (two independent
    ``parse_kicad_pcb_v6`` calls -> two independent ``build_board_dict``
    calls) and assert the ``traces``/``vias``/``zones`` this change adds are
    byte-for-byte identical both times.

    Scoped deliberately to ``traces``/``vias``/``zones`` -- NOT the whole
    dict. A run of this comparison during verification found ``nets`` is
    itself nondeterministic across process-level re-parses of the real
    board (order depends on Rust ``HashMap`` iteration inside
    ``extract_nets_pure``/``build_netlist`` in
    ``packages/temper-design-bundle/src/parse_engine.rs`` -- confirmed NOT
    a Python ``PYTHONHASHSEED`` effect, since pinning it to 0 did not
    change the result). That is a pre-existing bug in a different crate,
    outside this change's scope (issue #873 is traces/vias/zones only);
    fixing it here would be scope creep into code this task does not own.
    Recorded as a finding, not silently swept into a looser assertion.
    """
    sys.path.insert(0, str(_REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    parsed_1 = parse_kicad_pcb_v6(str(_REAL_PCB_PATH))
    parsed_2 = parse_kicad_pcb_v6(str(_REAL_PCB_PATH))
    board_dict_1 = r2_serialize_board.build_board_dict(parsed_1)
    board_dict_2 = r2_serialize_board.build_board_dict(parsed_2)

    assert board_dict_1["traces"] == board_dict_2["traces"]
    assert board_dict_1["vias"] == board_dict_2["vias"]
    assert board_dict_1["zones"] == board_dict_2["zones"]
    # Anti-vacuity: the committed board is non-trivially routed (issue #873's
    # own numbers -- 2290 segments, 48 vias, 96 zones), so an empty-vs-empty
    # comparison can't pass this by accident. ``traces`` entries are grouped
    # by (net, layer) (see _traces_from_parsed), so the top-level count is
    # smaller than the raw segment count -- the total segment count is the
    # invariant that must match the issue's number exactly.
    assert len(board_dict_1["traces"]) > 10
    total_segments = sum(len(t["segments"]) for t in board_dict_1["traces"])
    assert total_segments == 2290
    assert len(board_dict_1["vias"]) == 48
    assert len(board_dict_1["zones"]) == 96
