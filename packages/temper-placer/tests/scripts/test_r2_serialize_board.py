"""Tests for ``tools/wasm/r2_serialize_board.py``'s K1 ``board_dict`` builder.

Issue #873: the WASM verification tier's R2 board producer
(``tools/wasm/r2_serialize_board.py::build_board_dict``) never populated the
K1 schema's optional ``traces``/``vias``/``zones`` keys, so every
routing-family DRC rule benchmarked by
``packages/temper-drc-rs/examples/r2_full_board_pass.rs`` ran against an
empty board even though the Rust side
(``packages/temper-drc-rs/src/board_py_bridge.rs``'s ``build_board_state``
and ``packages/temper-drc-rs/src/board.rs``'s ``BoardState``) already fully
supported them. The first half of this file (through the "R8" section
below) exercises the three original helper functions (``_traces_from_parsed``,
``_vias_from_parsed``, ``_zones_from_parsed``) directly against lightweight
stand-ins for the ``ParsedPCB`` shape returned by
``temper_placer.io.kicad_parser.parse_kicad_pcb_v6``, without requiring a
real ``.kicad_pcb`` file or the compiled parser extension.

R8 (goal-set plan, "the board the tier checks is regenerated from the
committed placement, so the input changes when the harness changes"): the
second half tests ``build_board_dict``'s default ``zone_source="placement"``
path (``_zones_from_placement``, ``_pad_positions_by_net``,
``_harness_component_safety_classes``) -- zones and net-class metadata
re-derived from pad positions and the harness's net-class SSOT
(``temper_placer.core.design_rules``), without ``route_pcb()``. See
``docs/evidence/2026-08-07-router-free-r8-producer.md``.

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
        initial_rotation_quadrant=0.0,
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
    board_dict = r2_serialize_board.build_board_dict(parsed, pads=[])
    assert board_dict["components"][0]["x"] == 10.0
    assert board_dict["components"][0]["y"] == 25.0


# ---------------------------------------------------------------------------
# build_board_dict — end-to-end wiring
# ---------------------------------------------------------------------------


def test_build_board_dict_includes_routing_data_keys():
    # 5 segments across 5 *distinct* nets -> 5 groups in _traces_from_parsed
    # (same-net segments would collapse into one group; see
    # test_traces_from_parsed_groups_same_net_layer_segments below).
    #
    # zone_source="committed" here: this test exercises the traces/vias/
    # zones K1-schema WIRING (issue #873) using synthetic _FakeZone objects
    # that have no corresponding real pad/net-class-SSOT data for the R8
    # placement-derived path to consume -- see
    # test_build_board_dict_placement_zones_* below for that path.
    parsed = _FakeParsed(
        tracks=[
            _FakeTrack((0.0, 0.0), (1.0, 0.0), 0.2, "F.Cu", f"NET_{i}") for i in range(5)
        ],
        vias=[_FakeVia((0.0, 0.0), 0.6, 0.3, "GND", ("F.Cu", "B.Cu"))] * 3,
        zones=[_FakeZone(["GND"], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], ["F.Cu"])] * 2,
    )
    board_dict = r2_serialize_board.build_board_dict(parsed, zone_source="committed")
    assert len(board_dict["traces"]) == 5
    assert sum(len(t["segments"]) for t in board_dict["traces"]) == 5
    assert len(board_dict["vias"]) == 3
    assert len(board_dict["zones"]) == 2


def test_build_board_dict_empty_board_still_has_empty_routing_keys():
    # Default zone_source="placement" with an empty `pads` list: 0 pads ->
    # 0 zone-eligible net groups -> [] zones, exercising the R8 default
    # path's own empty-input degenerate case (not the "committed" path).
    board_dict = r2_serialize_board.build_board_dict(_FakeParsed(), pads=[])
    assert board_dict["traces"] == []
    assert board_dict["vias"] == []
    assert board_dict["zones"] == []


def test_build_board_dict_placement_zone_source_requires_pads():
    """The default ``zone_source="placement"`` fails closed -- rather than
    silently falling back to committed/empty zones -- when the caller
    forgets to pass ``pads``, since ``ParsedPCB`` (unlike the legacy
    ``ParseResult``) has no ``.pads`` attribute to fall back to."""
    with pytest.raises(ValueError, match="requires `pads`"):
        r2_serialize_board.build_board_dict(_FakeParsed())


def test_build_board_dict_rejects_unknown_zone_source():
    with pytest.raises(ValueError, match="unknown zone_source"):
        r2_serialize_board.build_board_dict(_FakeParsed(), pads=[], zone_source="bogus")


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
    # zone_source="committed": this test is specifically about the
    # traces/vias/zones K1-schema WIRING (issue #873) and its pre-existing
    # committed-geometry pass-through determinism, unaffected by the R8
    # placement-derived default added later -- see
    # test_real_board_placement_zones_are_deterministic_across_parses below
    # for the R8 path's own determinism check.
    board_dict_1 = r2_serialize_board.build_board_dict(parsed_1, zone_source="committed")
    board_dict_2 = r2_serialize_board.build_board_dict(parsed_2, zone_source="committed")

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


# ---------------------------------------------------------------------------
# R8: placement-derived zones (default zone_source="placement") against the
# real committed board -- determinism, non-vacuity, and sensitivity to BOTH
# the committed placement AND the harness (design_rules.py's net-class SSOT).
# ---------------------------------------------------------------------------


def _parse_real_board_with_pads():
    sys.path.insert(0, str(_REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.io.kicad_parser import parse_kicad_pcb, parse_kicad_pcb_v6

    parsed = parse_kicad_pcb_v6(str(_REAL_PCB_PATH))
    pads = list(parse_kicad_pcb(_REAL_PCB_PATH, normalize=False).pads)
    return parsed, pads


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_placement_zones_are_deterministic_across_parses():
    """The R8 default path (``zone_source="placement"``): two independent
    parses of the committed board must produce byte-identical
    ``zones``/``net_class_rules`` -- the same "regenerate, don't
    re-serialize" determinism bar as the committed-geometry path above,
    now for the re-derived-from-placement geometry."""
    parsed_1, pads_1 = _parse_real_board_with_pads()
    parsed_2, pads_2 = _parse_real_board_with_pads()

    board_dict_1 = r2_serialize_board.build_board_dict(parsed_1, pads_1)
    board_dict_2 = r2_serialize_board.build_board_dict(parsed_2, pads_2)

    assert board_dict_1["zones"] == board_dict_2["zones"]
    assert board_dict_1["net_class_rules"] == board_dict_2["net_class_rules"]
    # Anti-vacuity: the production board has ACMains/HighVoltage-class nets
    # with real pad geometry, so the zone-eligible set (routing_strategy ==
    # "plane_required") must be non-empty.
    assert len(board_dict_1["zones"]) > 0


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_placement_zones_differ_from_committed_zones():
    """The whole point of R8: re-derived zones must not simply be a
    reformatting of the committed ones. Both are non-empty (anti-vacuity)
    but the two sets of polygons are not equal -- proof this path is
    actually re-deriving geometry from pads, not re-serializing
    ``parsed.zones`` under a different code path that happens to produce
    the same numbers."""
    parsed, pads = _parse_real_board_with_pads()
    placement_zones = r2_serialize_board.build_board_dict(parsed, pads)["zones"]
    committed_zones = r2_serialize_board.build_board_dict(parsed, zone_source="committed")["zones"]

    assert len(placement_zones) > 0
    assert len(committed_zones) > 0
    assert placement_zones != committed_zones


class _PerturbedPad:
    """Thin wrapper overriding ``.position`` on a real ``PadData`` --
    ``PadData`` is a pyo3 pyclass (``temper_design_bundle_python``), not a
    plain Python object whose fields can be reassigned in place from a test
    without risking mutating shared parser state other tests might read.
    """

    def __init__(self, pad, position):
        self._pad = pad
        self.position = position

    def __getattr__(self, name):
        return getattr(self._pad, name)


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_placement_zones_change_when_placement_changes():
    """R8's "input changes when the harness changes" has a placement half
    too: perturbing a single pad's committed position must change the
    re-derived zone geometry. Directly perturbs the parsed ``pads`` list
    (not the committed .kicad_pcb file, which this task must not modify)
    to simulate a placement change."""
    parsed, pads = _parse_real_board_with_pads()
    baseline = r2_serialize_board.build_board_dict(parsed, pads)["zones"]
    assert len(baseline) > 0

    # Shift every pad on the first zone-eligible net encountered by 5mm --
    # large enough to move a convex-hull vertex, small enough to stay
    # on-board.
    target_net = baseline[0]["net"]
    perturbed_pads = []
    for p in pads:
        if p.net == target_net:
            x, y = p.position
            p = _PerturbedPad(p, (x + 5.0, y + 5.0))
        perturbed_pads.append(p)

    perturbed = r2_serialize_board.build_board_dict(parsed, perturbed_pads)["zones"]
    assert perturbed != baseline


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_net_class_rules_change_when_harness_changes(monkeypatch):
    """R8's "input changes when the harness changes" -- the net-class half:
    editing ``TEMPER_NET_CLASSES`` (the harness SSOT this producer now
    reads for ``net_class_rules``) must change the producer's output with a
    byte-identical committed board. Monkeypatches the harness table
    in-process (auto-reverted by pytest) rather than editing
    ``design_rules.py`` on disk."""
    sys.path.insert(0, str(_REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.core import design_rules as design_rules_module

    parsed, pads = _parse_real_board_with_pads()
    baseline = r2_serialize_board.build_board_dict(parsed, pads)["net_class_rules"]

    hv_baseline = baseline.get("HighVoltage")
    assert hv_baseline is not None, "production board must declare a HighVoltage net class"
    assert hv_baseline["clearance_mm"] == design_rules_module.TEMPER_NET_CLASSES["HighVoltage"].clearance

    patched = design_rules_module.TEMPER_NET_CLASSES["HighVoltage"].model_copy(
        update={"clearance": hv_baseline["clearance_mm"] + 1.0}
    )
    monkeypatch.setitem(design_rules_module.TEMPER_NET_CLASSES, "HighVoltage", patched)

    changed = r2_serialize_board.build_board_dict(parsed, pads)["net_class_rules"]
    assert changed["HighVoltage"]["clearance_mm"] == hv_baseline["clearance_mm"] + 1.0
    assert changed["HighVoltage"] != hv_baseline


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_constraints_zones_populated_from_zone_eligible_classes():
    """``build_constraints_dict``'s ``zones`` key (consumed by
    ``drc_zone_containment``) must name the same zone-eligible classes
    ``_zones_from_placement`` derives ``board.zones`` geometry for --
    otherwise a component of net class "HighVoltage" would have real zone
    geometry to be checked against but no constraint entry telling
    ``drc_zone_containment`` to check it."""
    sys.path.insert(0, str(_REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    parsed = parse_kicad_pcb_v6(str(_REAL_PCB_PATH))
    constraints = r2_serialize_board.build_constraints_dict(parsed)
    zone_names = {z["name"] for z in constraints["zones"]}
    assert "HighVoltage" in zone_names
    assert "ACMains" in zone_names
    for z in constraints["zones"]:
        assert z["net_classes"] == [z["name"]]


# ---------------------------------------------------------------------------
# 7-gap closure (2026-08-07): max_current_rating via the IPC-2221 fallback
# already shipped in config_loader.rs, and the isolator-device "iso" safety
# category via elec/domain_manifest.yaml's isolators: list matched against
# the parsed component's own Sheetpath property. See
# docs/evidence/2026-08-07-r9-harness-table-gap-closure.md.
# ---------------------------------------------------------------------------


_REAL_DOMAIN_MANIFEST_PATH = _REPO_ROOT / "elec" / "domain_manifest.yaml"


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
@pytest.mark.skipif(
    not _REAL_DOMAIN_MANIFEST_PATH.exists(), reason="elec/domain_manifest.yaml not present"
)
def test_real_board_isolator_component_refs_resolve_to_real_components():
    """Every ``instance_path`` in ``elec/domain_manifest.yaml``'s
    ``isolators:`` list must resolve to a real, live refdes on the committed
    board via the footprint's own ``Sheetpath`` property.

    The expected set tracks ``elec/domain_manifest.yaml``'s current
    ``isolators:`` list -- 7 components as of 2026-08-08. ``U3`` is absent by
    design: ``power_in.zcd_opto`` (H11L1 mains-ZCD optocoupler) was removed
    from the manifest and from ``elec/src`` by commit ``5842767c`` (plus
    ``300c4a70``), a deliberate, documented deletion (no firmware consumer,
    no architectural role, 8.560mm HV<->SELV pad separation failing the
    12.6mm PD3 target -- see
    ``docs/evidence/2026-07-30-zcd-optocoupler-removal.md``). The committed
    board still physically carries U3 (its board resync was explicitly
    deferred), but the refset is derived from the manifest SSOT, so it no
    longer includes U3. ``safety.ocp2.ct`` (the OCP-02 CT, added to the
    manifest 2026-08-07) likewise has no footprint on the un-resynced board
    yet and so resolves to nothing here."""
    sys.path.insert(0, str(_REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    parsed = parse_kicad_pcb_v6(str(_REAL_PCB_PATH))
    refs = r2_serialize_board._isolator_component_refs(parsed)
    assert refs == {"C6", "K1", "K2", "K3", "PS1", "T1", "U7"}


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_isolator_components_get_iso_safety_category():
    """Components resolved by ``_isolator_component_refs`` must be
    reclassified to a net class whose ``net_class_rules`` entry declares
    ``safety_category == "iso"`` -- the fix that makes
    ``safety_isolation``/``safety_creepage``'s ``is_iso_component`` see them
    (both kernels were previously vacuous for every real component: no
    ``TEMPER_NET_CLASSES`` entry ever declared ``"iso"``, see
    docs/evidence/2026-08-07-router-free-r8-producer.md §6.2)."""
    parsed, pads = _parse_real_board_with_pads()
    board_dict = r2_serialize_board.build_board_dict(parsed, pads)

    isolator_refs = r2_serialize_board._isolator_component_refs(parsed)
    assert isolator_refs, "production board must have at least one declared isolator"

    by_ref = {c["ref"]: c for c in board_dict["components"]}
    for ref in isolator_refs:
        net_class = by_ref[ref]["net_class"]
        rules = board_dict["net_class_rules"][net_class]
        assert rules["safety_category"] == "iso", (
            f"{ref} (declared isolator) must resolve to an iso-category net class, "
            f"got {net_class!r} -> safety_category={rules['safety_category']!r}"
        )


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_isolation_device_clearance_not_weaker_than_highvoltage():
    """The synthetic ``IsolationDevice`` net class must not weaken
    ``drc_clearance`` protection for the real isolator components -- they
    were already classified "HighVoltage" (severity override) before this
    fix, so ``IsolationDevice``'s clearance/trace_width must be at least as
    strict, not an arbitrary new number."""
    parsed, pads = _parse_real_board_with_pads()
    board_dict = r2_serialize_board.build_board_dict(parsed, pads)
    rules = board_dict["net_class_rules"]
    assert "IsolationDevice" in rules
    assert rules["IsolationDevice"]["clearance_mm"] >= rules["HighVoltage"]["clearance_mm"]
    assert rules["IsolationDevice"]["trace_width_mm"] >= rules["HighVoltage"]["trace_width_mm"]


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_max_current_rating_populated_via_ipc2221_fallback():
    """Every ``net_class_rules`` entry's ``max_current_rating`` must be
    populated (not ``None``) -- previously every one of the 11
    ``TEMPER_NET_CLASSES`` entries left it unset, which made
    ``routing_tht_thermal_relief`` permanently vacuous (its gate is
    ``Some(rating) if rating <= 10.0``, never reachable with `None`; see
    docs/evidence/2026-08-07-router-free-r8-producer.md §6.4). The fallback
    (``estimate_current_from_net_class(trace_width_mm)``, IPC-2221) mirrors
    the one already shipped in ``config_loader.rs``'s
    ``validate_current_capacity``, not an invented number."""
    parsed, pads = _parse_real_board_with_pads()
    board_dict = r2_serialize_board.build_board_dict(parsed, pads)
    rules = board_dict["net_class_rules"]
    assert rules, "production board must declare at least one net class"
    for class_name, r in rules.items():
        assert r["max_current_rating"] is not None, (
            f"{class_name}: max_current_rating must be populated (IPC-2221 fallback)"
        )
        assert r["max_current_rating"] > 0


@pytest.mark.skipif(
    not _REAL_PCB_PATH.exists(), reason="pcb/temper.kicad_pcb not present"
)
def test_real_board_max_current_rating_prefers_declared_value_over_fallback(monkeypatch):
    """When the harness DOES declare ``max_current_rating`` for a class, that
    value must be used verbatim -- the IPC-2221 fallback only fills the gap
    when the harness is silent, it never overrides an authoritative value."""
    sys.path.insert(0, str(_REPO_ROOT / "packages" / "temper-placer" / "src"))
    from temper_placer.core import design_rules as design_rules_module

    parsed, pads = _parse_real_board_with_pads()
    patched = design_rules_module.TEMPER_NET_CLASSES["HighVoltage"].model_copy(
        update={"max_current_rating": 123.0}
    )
    monkeypatch.setitem(design_rules_module.TEMPER_NET_CLASSES, "HighVoltage", patched)

    board_dict = r2_serialize_board.build_board_dict(parsed, pads)
    assert board_dict["net_class_rules"]["HighVoltage"]["max_current_rating"] == 123.0
