"""Differential test: the Rust write/export engine vs the pinned Python oracle.

Wave 4, Phase 3 — candidate 4 of
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`` (the
write/export engine; gate ``R1 with round-trip bit-parity (R3)``, gate set
R1a-R1h, plan D5/Q1 duck-typed boundary).

The migrated surface is ``temper_placer/io/kicad_exporter.py``,
``_write_board.py``, ``_write_tracks.py``, ``_write_zones.py``,
``_write_modules.py``, ``_write_types.py``, ``kicad_writer.py`` and
``placement_exporter.py`` — now delegation shims over ``temper-io-types``'
``kicad_write`` kernels. The pre-migration implementations are pinned
VERBATIM as ``tests/io/_*_py_oracle.py``, and every assertion here drives
IDENTICAL inputs through both sides.

Two shapes of evidence:

1. **Kernel differentials** — pure transformation functions driven directly:
   oracle function vs shim function on identical inputs, canonicalized
   leaf-by-leaf (floats as ``float.hex()``, every non-float leaf carrying its
   concrete ``type``, numpy arrays as ``(dtype, shape, tobytes())``).

2. **Full-function A/Bs** — the file-producing write functions driven end to
   end (template in, output ``.kicad_pcb`` out). Both arms write through
   kiutils' ``board.to_file``, so byte-identical output files ⟺ identical
   board mutations ⟺ a correct plan. Item-creating functions receive a
   deterministic ``uuid.uuid4`` patch so the tstamp fields (which kiutils
   embeds in every Segment/Via/Zone) match between the arms.

The oracle modules import the LIVE (shimmed) dependency modules exactly as
the pre-migration files did (verbatim copies); every migrated helper is
pinned by its own direct differential, so an oracle arm accidentally sharing
a Rust kernel is caught there.
"""

from __future__ import annotations

import math
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import tests.io._kicad_exporter_py_oracle as _exporter_oracle
import tests.io._placement_exporter_py_oracle as _placement_oracle
import tests.io._write_board_py_oracle as _board_oracle
import tests.io._write_modules_py_oracle as _modules_oracle
import tests.io._write_tracks_py_oracle as _tracks_oracle
import tests.io._write_types_py_oracle as _types_oracle
import tests.io._write_zones_py_oracle as _zones_oracle
from temper_placer.core.state import PlacementState
from temper_placer.io import (
    _write_board as _board_shim,
)
from temper_placer.io import (
    _write_modules as _modules_shim,
)
from temper_placer.io import (
    _write_tracks as _tracks_shim,
)
from temper_placer.io import (
    _write_types as _types_shim,
)
from temper_placer.io import (
    _write_zones as _zones_shim,
)
from temper_placer.io.kicad_exporter import (
    _generate_connector_segments as shim_generate_connectors,
)
from temper_placer.io.kicad_exporter import (
    _validate_4_layer_output as shim_validate_4layer,
)
from temper_placer.io.kicad_exporter import (
    export_board_state as shim_export_board_state,
)
from temper_placer.io.kicad_exporter import (
    export_from_geometry as shim_export_from_geometry,
)
from temper_placer.io.kicad_exporter import (
    export_routed_pcb as shim_export_routed_pcb,
)
from temper_placer.io.kicad_exporter import (
    extract_pad_centers as shim_extract_pad_centers,
)
from temper_placer.io.kicad_exporter import (
    path_to_segments as shim_path_to_segments,
)
from temper_placer.io.kicad_exporter import (
    path_to_vias as shim_path_to_vias,
)
from temper_placer.io.kicad_exporter import (
    snap_to_nearest_pad as shim_snap,
)
from temper_placer.io.kicad_writer import (
    placements_from_json as shim_placements_from_json,
)
from temper_placer.io.kicad_writer import (
    placements_to_json as shim_placements_to_json,
)
from temper_placer.io.placement_exporter import (
    positions_to_placements as shim_positions_to_placements,
)
from temper_placer.io.placement_exporter import (
    rotation_index_to_degrees as shim_rotation_index_to_degrees,
)
from temper_placer.router_v6.grid_converter import GridCell

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_CORPUS = _REPO_ROOT / "power_pcb_dataset" / "corpus"


# ---------------------------------------------------------------------------
# canonicalization
# ---------------------------------------------------------------------------


def _leaf(value):
    """A comparison key that pins both the VALUE and its concrete TYPE.

    Floats become their exact ``float.hex()`` bit pattern. Everything else
    carries ``type(value).__name__`` alongside the value, so ``10`` (int) and
    ``10.0`` (float) are never equal here, and a bool cannot hide behind an
    int.
    """
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, tuple):
        return ("tuple", tuple(_leaf(v) for v in value))
    if isinstance(value, list):
        return ("list", tuple(_leaf(v) for v in value))
    if isinstance(value, dict):
        return (
            "dict",
            tuple((_leaf(k), _leaf(v)) for k, v in value.items()),
        )
    if isinstance(value, np.ndarray):
        return ("ndarray", value.dtype.str, value.shape, value.tobytes())
    if isinstance(value, np.generic):
        return ("np_scalar", value.dtype.str, value.item())
    if hasattr(value, "ref") and hasattr(value, "x") and hasattr(value, "rotation"):
        # PlacementUpdate-like (dataclass or pyclass)
        return (
            "placement_update",
            _leaf(value.ref),
            _leaf(value.x),
            _leaf(value.y),
            _leaf(value.rotation),
        )
    # Fall back to repr (names the concrete class) plus repr of the object.
    return (type(value).__name__, repr(value))


def _canon(v):
    if isinstance(v, dict):
        return ("dict", tuple((_leaf(k), _leaf(x)) for k, x in v.items()))
    if isinstance(v, list):
        return ("list", tuple(_leaf(x) for x in v))
    return _leaf(v)


def assert_same(a, b, ctx: str):
    """Assert two values are identical leaf-by-leaf (order-sensitive)."""
    assert _canon(a) == _canon(b), f"{ctx}: {_canon(a)!r} != {_canon(b)!r}"


def _uuid_seq():
    """Deterministic uuid.uuid4 stand-in for the item-creating A/Bs."""
    counter = [0]

    def _next():
        counter[0] += 1
        return f"00000000-0000-0000-0000-{counter[0]:012d}"

    return _next


# ---------------------------------------------------------------------------
# fixtures: synthetic inputs
# ---------------------------------------------------------------------------


def _grid_path(net="GND", cells=None, cell_size=0.5, layer_map=None, success=True, failure_reason=None, explicit_vias=None):
    return SimpleNamespace(
        net_name=net,
        net=net,
        cells=cells if cells is not None else [GridCell(0, 0, 0), GridCell(2, 0, 0)],
        cell_size=cell_size,
        layer_name="F.Cu",
        success=success,
        failure_reason=failure_reason,
        explicit_vias=explicit_vias or [],
    )


def _segment(net, start, end, width=0.25, layer="F.Cu"):
    from temper_placer.io.export_types import TraceSegment

    return TraceSegment(net=net, start=start, end=end, width=width, layer=layer)


def _via(net, position, size=0.8, drill=0.4, layers=None):
    from temper_placer.io.export_types import TraceVia

    return TraceVia(net=net, position=position, size=size, drill=drill, layers=layers or ["F.Cu", "B.Cu"])


# ---------------------------------------------------------------------------
# board templates
# ---------------------------------------------------------------------------


def _board_content(fp_blocks: str) -> str:
    return (
        "(kicad_pcb (version 20240108) (generator pcbnew)\n"
        "  (general (thickness 1.6))\n"
        '  (paper "A4")\n'
        "  (layers\n"
        '    (0 "F.Cu" signal)\n'
        '    (31 "B.Cu" signal)\n'
        '    (44 "Edge.Cuts" user)\n'
        "  )\n"
        "  (setup (pad_to_mask_clearance 0))\n"
        "  (nets\n"
        '    (0 "")\n'
        '    (1 "n1")\n'
        "  )\n"
        f"{fp_blocks}\n"
        ")\n"
    )


def _fp(
    ref: str,
    at: tuple[float, float, float | None],
    pads: list[tuple[str, float, float, float | None]],
    lib: str = "Test:PART",
    net: int = 1,
) -> str:
    at_x, at_y, at_ang = at
    at_suffix = "" if at_ang is None else f" {at_ang}"
    pad_blocks = []
    for num, px, py, p_ang in pads:
        p_suffix = "" if p_ang is None else f" {p_ang}"
        pad_blocks.append(
            f'    (pad "{num}" smd rect (at {px} {py}{p_suffix}) (size 0.6 1.2)'
            f' (layers "F.Cu" "F.Paste" "F.Mask") (net {net} "n1"))'
        )
    pads_str = "\n".join(pad_blocks)
    return (
        f'  (footprint "{lib}" (layer "F.Cu")\n'
        f"    (tstamp 00000000-0000-0000-0000-000000000001)\n"
        f"    (at {at_x} {at_y}{at_suffix})\n"
        f'    (property "Reference" "{ref}" (at 0 0 0) (layer "F.SilkS"))\n'
        f'    (property "Value" "10k" (at 0 0 0) (layer "F.Fab"))\n'
        f"{pads_str}\n"
        "  )"
    )


def _asymmetric_fp(ref: str, at: tuple[float, float, float | None]) -> str:
    """3-pad asymmetric footprint with a distinct intrinsic pad angle."""
    return _fp(
        ref,
        at,
        [("1", 0.0, 0.0, 45.0), ("2", 10.0, 0.0, None), ("3", 20.0, 0.0, None)],
        lib="Test:ASYM3",
    )


@pytest.fixture
def template(tmp_path: Path) -> Path:
    content = _board_content(
        _asymmetric_fp("U1", (10.0, 10.0, None)) + "\n" + _asymmetric_fp("U2", (40.0, 10.0, None))
    )
    p = tmp_path / "template.kicad_pcb"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def routed_template(tmp_path: Path) -> Path:
    """A template with pre-existing traces/vias/zones for strip/stats tests."""
    content = _board_content(
        _asymmetric_fp("U1", (10.0, 10.0, None))
        + "\n"
        + _asymmetric_fp("U2", (40.0, 10.0, None))
    )
    content = content.replace(
        "  (setup (pad_to_mask_clearance 0))\n",
        "  (setup (pad_to_mask_clearance 0))\n"
        "  (segment (start 1 1) (end 5 5) (width 0.25) (layer F.Cu) (net 1) (tstamp 00000000-0000-0000-0000-0000000000aa))\n"
        "  (segment (start 6 6) (end 9 9) (width 0.25) (layer B.Cu) (net 1) (tstamp 00000000-0000-0000-0000-0000000000ab))\n"
        "  (via (at 5 5) (size 0.8) (drill 0.4) (layers F.Cu B.Cu) (net 1) (tstamp 00000000-0000-0000-0000-0000000000ac))\n"
        "  (gr_line (start 0 0) (end 10 10) (layer Edge.Cuts) (width 0.1) (tstamp 00000000-0000-0000-0000-0000000000ad))\n"
        "  (zone (net 1) (net_name n1) (layer F.Cu) (tstamp 00000000-0000-0000-0000-0000000000ae)\n"
        "    (polygon (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5)))\n"
        "    (filled_polygon (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5)))\n"
        "  )\n",
    )
    p = tmp_path / "routed.kicad_pcb"
    p.write_text(content, encoding="utf-8")
    return p


def _corpus_board(name: str) -> Path:
    p = _CORPUS / name
    if not p.exists():
        pytest.skip(f"corpus board {name} not present")
    return p


def _corpus_temper() -> Path:
    return _corpus_board("temper/temper.kicad_pcb")


# ---------------------------------------------------------------------------
# Group A — path -> segments / vias
# ---------------------------------------------------------------------------


class TestPathToSegments:
    def test_cells_path(self):
        path = _grid_path(net="GND", cells=[GridCell(0, 0, 0), GridCell(2, 0, 0), GridCell(2, 2, 1)], cell_size=0.5)
        o = _exporter_oracle.path_to_segments(path, (0.0, 0.0), 0.5, 0.25)
        s = shim_path_to_segments(path, (0.0, 0.0), 0.5, 0.25)
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "cells")

    def test_cells_simplification_removes_collinear(self):
        path = _grid_path(
            net="VCC",
            cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0), GridCell(2, 2, 0), GridCell(2, 2, 1)],
        )
        o = _exporter_oracle.path_to_segments(path, (1.0, 2.0), 0.5, 0.5)
        s = shim_path_to_segments(path, (1.0, 2.0), 0.5, 0.5)
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "simplify")

    def test_segments_path_3d(self):
        path = SimpleNamespace(
            net_name="SIG",
            segments=[(0.0, 0.0, "F.Cu"), (5.0, 0.0, "F.Cu"), (5.0, 5.0, "B.Cu")],
            layer_name="F.Cu",
        )
        o = _exporter_oracle.path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        s = shim_path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "segments3d")

    def test_coordinates_path_2d(self):
        path = SimpleNamespace(net_name="", net="AN", coordinates=[(0.0, 0.0), (3.0, 4.0)], layer_name="F.Cu")
        o = _exporter_oracle.path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        s = shim_path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "coordinates")

    def test_empty_path(self):
        path = SimpleNamespace(net_name="X", coordinates=[], layer_name="F.Cu")
        o = _exporter_oracle.path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        s = shim_path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        assert o == []
        assert s == []

    def test_layer_transition_skipped(self):
        path = SimpleNamespace(net_name="X", segments=[(0.0, 0.0, "F.Cu"), (5.0, 0.0, "B.Cu")], layer_name="F.Cu")
        o = _exporter_oracle.path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        s = shim_path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        assert o == []
        assert s == []

    def test_unknown_net_falls_back(self):
        path = SimpleNamespace(coordinates=[(0.0, 0.0), (1.0, 1.0)], layer_name="F.Cu")
        o = _exporter_oracle.path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        s = shim_path_to_segments(path, (0.0, 0.0), 1.0, 0.2)
        assert o[0].net == "unknown"
        assert s[0].net == "unknown"

    def test_custom_layer_map(self):
        path = _grid_path(net="GND", cells=[GridCell(0, 0, 3), GridCell(1, 0, 3)], cell_size=0.5)
        layer_map = {3: "B.Cu"}
        o = _exporter_oracle.path_to_segments(path, (0.0, 0.0), 0.5, 0.25, layer_map)
        s = shim_path_to_segments(path, (0.0, 0.0), 0.5, 0.25, layer_map)
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "layer_map")


class TestPathToVias:
    def test_cells_layer_transition(self):
        path = _grid_path(net="GND", cells=[GridCell(0, 0, 0), GridCell(2, 0, 0), GridCell(2, 2, 1)], cell_size=0.5)
        o = _exporter_oracle.path_to_vias(path, (0.0, 0.0), 0.5)
        s = shim_path_to_vias(path, (0.0, 0.0), 0.5)
        assert_same([(v.net, v.position, v.size, v.drill, v.layers) for v in o],
                    [(v.net, v.position, v.size, v.drill, v.layers) for v in s], "via cells")

    def test_segments_path(self):
        path = SimpleNamespace(
            net_name="SIG",
            segments=[(0.0, 0.0, "F.Cu"), (5.0, 0.0, "F.Cu"), (5.0, 5.0, "B.Cu")],
            layer_name="F.Cu",
        )
        o = _exporter_oracle.path_to_vias(path, (0.0, 0.0), 1.0, 0.8, 0.4)
        s = shim_path_to_vias(path, (0.0, 0.0), 1.0, 0.8, 0.4)
        assert_same([(v.net, v.position, v.size, v.drill, v.layers) for v in o],
                    [(v.net, v.position, v.size, v.drill, v.layers) for v in s], "via segments")

    def test_no_transition(self):
        path = _grid_path(net="GND", cells=[GridCell(0, 0, 0), GridCell(2, 0, 0)], cell_size=0.5)
        o = _exporter_oracle.path_to_vias(path, (0.0, 0.0), 0.5)
        s = shim_path_to_vias(path, (0.0, 0.0), 0.5)
        assert o == []
        assert s == []

    def test_sorted_layers(self):
        path = SimpleNamespace(
            net_name="SIG",
            segments=[(0.0, 0.0, "B.Cu"), (1.0, 1.0, "F.Cu")],
            layer_name="B.Cu",
        )
        o = _exporter_oracle.path_to_vias(path, (0.0, 0.0), 1.0)
        s = shim_path_to_vias(path, (0.0, 0.0), 1.0)
        assert o[0].layers == ["B.Cu", "F.Cu"]
        assert s[0].layers == ["B.Cu", "F.Cu"]


# ---------------------------------------------------------------------------
# Group B — pad geometry
# ---------------------------------------------------------------------------


def _synthetic_board(pads_by_net):
    """footprints: list of ((at_x, at_y, angle), [(net, pad_x, pad_y, pad_angle), ...])."""
    fps = []
    for (at_x, at_y, angle), pads in pads_by_net:
        pad_objs = [
            SimpleNamespace(
                net=SimpleNamespace(name=net),
                position=SimpleNamespace(X=px, Y=py, angle=pa),
            )
            for net, px, py, pa in pads
        ]
        fps.append(SimpleNamespace(position=SimpleNamespace(X=at_x, Y=at_y, angle=angle), pads=pad_objs))
    return SimpleNamespace(footprints=fps)


class TestExtractPadCenters:
    def test_rotation_applied(self):
        board = _synthetic_board([((10.0, 10.0, 90.0), [("N1", 1.0, 0.0, None)])])
        o = _exporter_oracle.extract_pad_centers(board)
        s = shim_extract_pad_centers(board)
        # R(-90).(1,0) = (0,-1): absolute (10, 9)
        assert o["N1"][0] == (10.0, 9.0)
        assert_same(o, s, "pad centers rotate")

    def test_multiple_nets_insertion_order(self):
        board = _synthetic_board(
            [
                ((0.0, 0.0, 0.0), [("A", 1.0, 0.0, None), ("B", 2.0, 0.0, None)]),
                ((5.0, 5.0, 0.0), [("A", 0.5, 0.5, None)]),
            ]
        )
        o = _exporter_oracle.extract_pad_centers(board)
        s = shim_extract_pad_centers(board)
        assert_same(o, s, "multi-net order")
        assert list(o.keys()) == list(s.keys()) == ["A", "B"]

    # NOTE: a pad whose `position` is None is deliberately NOT differentially
    # tested: the pinned Python raises AttributeError on it while the kernel
    # reads (0, 0) — pads without an `at` token are outside the input space of
    # every real board, and the bound is recorded in VERIFICATION.md.


class TestSnap:
    @pytest.mark.parametrize(
        "x,y,pads,tol,expected",
        [
            (0.0, 0.0, [(0.5, 0.0)], 0.15, (0.0, 0.0)),
            (0.0, 0.0, [(0.1, 0.0)], 0.15, (0.1, 0.0)),
            (0.0, 0.0, [(0.15, 0.0)], 0.15, (0.0, 0.0)),  # strict < at boundary
            (0.0, 0.0, [(0.15, 0.0), (0.14, 0.0)], 0.15, (0.14, 0.0)),
            (5.0, 5.0, [(5.0, 5.0)], 0.0, (5.0, 5.0)),
        ],
    )
    def test_snap_cases(self, x, y, pads, tol, expected):
        o = _exporter_oracle.snap_to_nearest_pad(x, y, pads, tol)
        s = shim_snap(x, y, pads, tol)
        assert o == expected
        assert_same(o, s, f"snap {x},{y}")

    def test_negative_coordinates(self):
        pads = [(-3.5, 2.25)]
        o = _exporter_oracle.snap_to_nearest_pad(-3.4, 2.2, pads, 0.15)
        s = shim_snap(-3.4, 2.2, pads, 0.15)
        assert_same(o, s, "negative")


class TestGenerateConnectors:
    def test_bridges_gap(self):
        segments = [_segment("N1", (0.0, 0.0), (10.0, 0.0))]
        pad_centers = {"N1": [(10.5, 0.0)]}
        o = _exporter_oracle._generate_connector_segments(segments, pad_centers)
        s = shim_generate_connectors(segments, pad_centers)
        assert len(o) == 1
        assert o[0].end == (10.5, 0.0)
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "bridge")

    def test_connected_pad_not_bridged(self):
        segments = [_segment("N1", (0.0, 0.0), (10.0, 0.0))]
        pad_centers = {"N1": [(10.0, 0.0)]}  # exact match
        o = _exporter_oracle._generate_connector_segments(segments, pad_centers)
        s = shim_generate_connectors(segments, pad_centers)
        assert o == []
        assert s == []

    def test_far_pad_not_bridged(self):
        segments = [_segment("N1", (0.0, 0.0), (10.0, 0.0))]
        pad_centers = {"N1": [(20.0, 0.0)]}
        o = _exporter_oracle._generate_connector_segments(segments, pad_centers)
        s = shim_generate_connectors(segments, pad_centers)
        assert o == []
        assert s == []

    def test_multiple_nets_ordering(self):
        segments = [
            _segment("A", (0.0, 0.0), (10.0, 0.0)),
            _segment("B", (0.0, 5.0), (10.0, 5.0)),
        ]
        pad_centers = {"A": [(10.4, 0.0)], "B": [(10.3, 5.0)]}
        o = _exporter_oracle._generate_connector_segments(segments, pad_centers)
        s = shim_generate_connectors(segments, pad_centers)
        assert [t.net for t in o] == ["A", "B"]
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "multi-net order")

    def test_max_dist_honored(self):
        segments = [_segment("N1", (0.0, 0.0), (10.0, 0.0))]
        pad_centers = {"N1": [(12.5, 0.0)]}
        o = _exporter_oracle._generate_connector_segments(segments, pad_centers, max_dist=2.0)
        s = shim_generate_connectors(segments, pad_centers, max_dist=2.0)
        assert o == []
        assert s == []

    def test_tie_break_matches_set_order_reviewer_triple(self):
        """Exact-distance tie discriminator (adversarial-review construct).

        Pad (-17.62, -34.92) with endpoints (-18.12, -35.42) and
        (-17.12, -34.42): both sqrt(0.5) away — an exact float tie. CPython's
        ``set`` iterates this pair in the REVERSE of insertion order, so the
        strict-< nearest-endpoint pick lands on the second-inserted endpoint.
        The kernel must iterate a REAL Python set (same interpreter, same hash
        order) — a first-appearance Vec picks the first-inserted endpoint and
        emits different connector bytes. Demonstrated RED against the Vec
        implementation before the fix: oracle (-17.12, -34.42) vs Vec
        (-18.12, -35.42).
        """
        segments = [_segment("N1", (-18.12, -35.42), (-17.12, -34.42))]
        pad_centers = {"N1": [(-17.62, -34.92)]}
        o = _exporter_oracle._generate_connector_segments(segments, pad_centers)
        s = shim_generate_connectors(segments, pad_centers)
        assert o[0].start == (-17.12, -34.42), "set-iteration-order pick"
        assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                    [(t.net, t.start, t.end, t.width, t.layer) for t in s], "reviewer tie")

    def test_tie_break_reversed_insertion_both_orders(self):
        """The same tie with the OTHER relative insertion order.

        Pad (199.25, -153.75) is exactly equidistant from a=(198.75, -153.25)
        and b=(199.75, -154.25). For THIS pair the set's slot order FLIPS with
        insertion order, so both segment orientations are discriminators: the
        oracle picks b when endpoints are inserted a-then-b and a when
        inserted b-then-a. A first-appearance Vec picks the first-inserted
        endpoint in both cases — RED on both orientations pre-fix.
        """
        pad_centers = {"N1": [(199.25, -153.75)]}
        for start, end, expected in [
            ((198.75, -153.25), (199.75, -154.25), (199.75, -154.25)),
            ((199.75, -154.25), (198.75, -153.25), (198.75, -153.25)),
        ]:
            segments = [_segment("N1", start, end)]
            o = _exporter_oracle._generate_connector_segments(segments, pad_centers)
            s = shim_generate_connectors(segments, pad_centers)
            assert o[0].start == expected, f"set-iteration-order pick {start}->{end}"
            assert_same([(t.net, t.start, t.end, t.width, t.layer) for t in o],
                        [(t.net, t.start, t.end, t.width, t.layer) for t in s],
                        f"tie {start}->{end}")


# ---------------------------------------------------------------------------
# Group C — layer validation
# ---------------------------------------------------------------------------


class TestValidate4Layer:
    def test_canonical_4layer_ok(self, tmp_path):
        content = (
            "(kicad_pcb (version 20240108)\n"
            "  (layers\n"
            '    (0 "F.Cu" signal)\n'
            '    (1 "In1.Cu" signal)\n'
            '    (2 "In2.Cu" signal)\n'
            '    (31 "B.Cu" signal)\n'
            '    (44 "Edge.Cuts" user)\n'
            "  )\n"
            ")\n"
        )
        p = tmp_path / "b.kicad_pcb"
        p.write_text(content, encoding="utf-8")
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(p))
        import logging

        with unittest.mock.patch.object(logging.getLogger("temper_placer.io.kicad_exporter"), "warning") as warn:
            shim_validate_4layer(board)
            assert warn.call_count == 0

    def test_non4layer_warns(self, tmp_path):
        content = (
            "(kicad_pcb (version 20240108)\n"
            "  (layers\n"
            '    (0 "F.Cu" signal)\n'
            '    (44 "Edge.Cuts" user)\n'
            "  )\n"
            ")\n"
        )
        p = tmp_path / "b.kicad_pcb"
        p.write_text(content, encoding="utf-8")
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(p))
        import logging

        with unittest.mock.patch.object(logging.getLogger("temper_placer.io.kicad_exporter"), "warning") as warn:
            shim_validate_4layer(board)
            assert warn.call_count == 1
            msg = str(warn.call_args[0][1])
            assert "copper layers" in msg

    def test_wrong_names_raises(self, tmp_path):
        content = (
            "(kicad_pcb (version 20240108)\n"
            "  (layers\n"
            '    (0 "F.Cu" signal)\n'
            '    (1 "In1.Cu" signal)\n'
            '    (2 "In2.Cu" signal)\n'
            '    (31 "BOGUS.Cu" signal)\n'
            "  )\n"
            ")\n"
        )
        p = tmp_path / "b.kicad_pcb"
        p.write_text(content, encoding="utf-8")
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(p))
        with pytest.raises(RuntimeError, match="Copper layer names must match canonical set"):
            shim_validate_4layer(board)

    # -- exact-message differentials ----------------------------------------
    # The oracle modules import _validate_4_layer_output from the LIVE shimmed
    # modules, so the file-producing A/Bs run the Rust kernel on BOTH arms — a
    # formatting defect in the kernel is invisible there. These pin the
    # kernel's decision strings directly against the VERBATIM oracle copy
    # (_kicad_exporter_py_oracle._validate_4_layer_output), which logs
    # / raises its own text.

    def _capture_warn(self, fn, board, logger_name):
        import logging

        recs = []
        logger = logging.getLogger(logger_name)
        old_level = logger.level
        logger.setLevel(logging.WARNING)
        handler = logging.Handler()
        handler.emit = lambda r: recs.append(r.getMessage())
        logger.addHandler(handler)
        try:
            fn(board)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        return recs

    def _board_from(self, layers_sexpr, tmp_path):
        from kiutils.board import Board as KiBoard

        content = "(kicad_pcb (version 20240108)\n  (layers\n" + layers_sexpr + "  )\n)\n"
        p = tmp_path / "b.kicad_pcb"
        p.write_text(content, encoding="utf-8")
        return KiBoard.from_file(str(p))

    def test_exact_message_differential_warn(self, tmp_path):
        """Warn path: the full message text (layer count + sorted canonical
        list) must be byte-identical oracle-vs-shim."""
        board = self._board_from('    (0 "F.Cu" signal)\n    (44 "Edge.Cuts" user)\n', tmp_path)
        o_msgs = self._capture_warn(
            _exporter_oracle._validate_4_layer_output, board, "tests.io._kicad_exporter_py_oracle"
        )
        s_msgs = self._capture_warn(
            shim_validate_4layer, board, "temper_placer.io.kicad_exporter"
        )
        assert len(o_msgs) == len(s_msgs) == 1
        assert o_msgs[0] == s_msgs[0]
        assert o_msgs[0] == (
            "Board has 1 copper layers (canonical 4-layer stackup: "
            "['B.Cu', 'F.Cu', 'In1.Cu', 'In2.Cu']). "
            "Proceeding — non-4-layer boards are valid for test fixtures and prototypes."
        )

    def test_exact_message_differential_raise(self, tmp_path):
        """Raise path: the sorted, deduped, quoted got-list must be
        byte-identical oracle-vs-shim."""
        board = self._board_from(
            '    (0 "F.Cu" signal)\n    (1 "In1.Cu" signal)\n'
            '    (2 "In2.Cu" signal)\n    (31 "BOGUS.Cu" signal)\n',
            tmp_path,
        )
        with pytest.raises(RuntimeError) as eo:
            _exporter_oracle._validate_4_layer_output(board)
        with pytest.raises(RuntimeError) as es:
            shim_validate_4layer(board)
        assert str(eo.value) == str(es.value)
        assert str(eo.value) == (
            "Copper layer names must match canonical set "
            "['B.Cu', 'F.Cu', 'In1.Cu', 'In2.Cu'], "
            "got ['BOGUS.Cu', 'F.Cu', 'In1.Cu', 'In2.Cu']"
        )

    def test_exact_message_differential_no_layers(self):
        """Missing `layers` attribute raises the exact pinned text on both
        arms."""
        board = SimpleNamespace()  # no layers attribute
        with pytest.raises(RuntimeError) as eo:
            _exporter_oracle._validate_4_layer_output(board)
        with pytest.raises(RuntimeError) as es:
            shim_validate_4layer(board)
        assert str(eo.value) == str(es.value) == (
            "KiCad board has no layers attribute — cannot validate layer count"
        )

    def test_exact_message_differential_ok(self, tmp_path):
        """Canonical 4-layer board (unsorted layer order) produces NO warning
        and NO error on either arm."""
        board = self._board_from(
            '    (0 "F.Cu" signal)\n    (1 "In2.Cu" signal)\n'
            '    (2 "In1.Cu" signal)\n    (31 "B.Cu" signal)\n',
            tmp_path,
        )
        o_msgs = self._capture_warn(
            _exporter_oracle._validate_4_layer_output, board, "tests.io._kicad_exporter_py_oracle"
        )
        s_msgs = self._capture_warn(
            shim_validate_4layer, board, "temper_placer.io.kicad_exporter"
        )
        assert o_msgs == s_msgs == []


# ---------------------------------------------------------------------------
# Group D — placements
# ---------------------------------------------------------------------------


def _state(positions, logits):
    return PlacementState.from_positions(np.array(positions, dtype=float), rotation_logits=np.array(logits, dtype=float))


def _component(ref, attributes=None):
    return SimpleNamespace(ref=ref, attributes=attributes or {})


class TestStateToPlacements:
    def test_basic_conversion(self):
        state = _state([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]],
                       [[10.0, 0.0, 0.0, 0.0], [0.0, 10.0, 0.0, 0.0], [0.0, 0.0, 10.0, 0.0]])
        refs = ["U1", "R1", "C1"]
        o = _board_oracle.state_to_placements(state, refs)
        s = _board_shim.state_to_placements(state, refs)
        assert_same(o, s, "basic")
        assert s["U1"].rotation == 0.0
        assert s["R1"].rotation == 90.0
        assert s["C1"].rotation == 180.0

    def test_origin(self):
        state = _state([[10.0, 20.0]], [[0.0, 10.0, 0.0, 0.0]])
        o = _board_oracle.state_to_placements(state, ["U1"], origin=(100.0, 50.0))
        s = _board_shim.state_to_placements(state, ["U1"], origin=(100.0, 50.0))
        assert_same(o, s, "origin")
        assert s["U1"].x == 110.0
        assert s["U1"].y == 70.0

    def test_center_offsets(self):
        state = _state([[100.0, 100.0]], [[0.0, 10.0, 0.0, 0.0]])
        comps = [_component("Q1", {"_center_offset_x": "10", "_center_offset_y": "0"})]
        o = _board_oracle.state_to_placements(state, ["Q1"], components=comps)
        s = _board_shim.state_to_placements(state, ["Q1"], components=comps)
        assert_same(o, s, "center offset")
        # R(-90).(10,0) = (0,-10): 100 - 0 = 100, 100 - (-10) = 110
        assert s["Q1"].x == 100.0
        assert s["Q1"].y == 110.0

    def test_original_angle_offset_preserved(self):
        state = _state([[10.0, 20.0]], [[10.0, 0.0, 0.0, 0.0]])
        angles = {"Q1": 45.0}  # quantized 0, offset 45
        o = _board_oracle.state_to_placements(state, ["Q1"], original_angles=angles)
        s = _board_shim.state_to_placements(state, ["Q1"], original_angles=angles)
        assert_same(o, s, "original angle")
        assert s["Q1"].rotation == 45.0

    def test_original_angle_small_offset_ignored(self):
        state = _state([[10.0, 20.0]], [[0.0, 10.0, 0.0, 0.0]])
        angles = {"Q1": 90.1}  # quantized 90, offset 0.1 -> ignored
        o = _board_oracle.state_to_placements(state, ["Q1"], original_angles=angles)
        s = _board_shim.state_to_placements(state, ["Q1"], original_angles=angles)
        assert_same(o, s, "small offset")
        assert s["Q1"].rotation == 90.0

    def test_rotation_modulo(self):
        state = _state([[10.0, 20.0]], [[0.0, 0.0, 0.0, 10.0]])
        angles = {"Q1": -45.0}
        o = _board_oracle.state_to_placements(state, ["Q1"], original_angles=angles)
        s = _board_shim.state_to_placements(state, ["Q1"], original_angles=angles)
        assert_same(o, s, "modulo")
        assert 0.0 <= s["Q1"].rotation < 360.0


class TestExtractOriginalAngles:
    def test_none(self):
        comps = [_component("U1"), _component("R1", {"_center_offset_x": "1"})]
        o = _board_oracle.extract_original_angles(comps)
        s = _board_shim.extract_original_angles(comps)
        assert_same(o, s, "none")
        assert o == {}

    def test_with_angles(self):
        comps = [_component("U1", {"_original_angle": "45"}), _component("R1", {"_original_angle": 90.0})]
        o = _board_oracle.extract_original_angles(comps)
        s = _board_shim.extract_original_angles(comps)
        assert_same(o, s, "with angles")
        assert o["U1"] == 45.0
        assert o["R1"] == 90.0

    def test_invalid_suppressed(self):
        comps = [_component("U1", {"_original_angle": "not-a-number"})]
        o = _board_oracle.extract_original_angles(comps)
        s = _board_shim.extract_original_angles(comps)
        assert_same(o, s, "invalid suppressed")
        assert o == {}


class TestPlacementExporter:
    def test_positions_to_placements(self):
        positions = np.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = np.array([[10.0, 0.0, 0.0, 0.0], [0.0, 0.0, 10.0, 0.0]])
        refs = ["U1", "R1"]
        o = _placement_oracle.positions_to_placements(positions, rotations, refs)
        s = shim_positions_to_placements(positions, rotations, refs)
        assert_same(o, s, "positions_to_placements")
        assert s["R1"].rotation == 180.0

    def test_positions_to_placements_origin(self):
        positions = np.array([[10.0, 20.0]])
        rotations = np.array([[0.0, 10.0, 0.0, 0.0]])
        o = _placement_oracle.positions_to_placements(positions, rotations, ["U1"], origin=(5.0, 7.0))
        s = shim_positions_to_placements(positions, rotations, ["U1"], origin=(5.0, 7.0))
        assert_same(o, s, "origin")
        assert s["U1"].x == 15.0
        assert s["U1"].y == 27.0

    def test_rotation_index_to_degrees(self):
        for idx in range(4):
            assert shim_rotation_index_to_degrees(idx) == _placement_oracle.rotation_index_to_degrees(idx)
        assert shim_rotation_index_to_degrees(2) == 180.0

    def test_shape_mismatch_raises(self):
        positions = np.array([[10.0, 20.0]])
        rotations = np.array([[0.0, 10.0, 0.0, 0.0]])
        with pytest.raises(ValueError, match="Position count"):
            shim_positions_to_placements(positions, rotations, ["U1", "U2"])


class TestPlacementsJson:
    def test_to_json(self):
        from temper_placer.io.kicad_writer import PlacementUpdate

        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0),
            "R1": PlacementUpdate(ref="R1", x=30.0, y=40.0, rotation=0.0),
        }
        o = _exporter_oracle  # noqa — placement JSON oracle lives in kicad_writer oracle
        from tests.io import _kicad_writer_py_oracle as _writer_oracle

        oj = _writer_oracle.placements_to_json(placements)
        sj = shim_placements_to_json(placements)
        assert_same(oj, sj, "to_json")
        assert sj["U1"]["x"] == 10.0

    def test_from_json(self):
        from tests.io import _kicad_writer_py_oracle as _writer_oracle

        data = {"U1": {"x": 10, "y": 20, "rotation": 90}, "R1": {"x": 30.5, "y": 40.5, "rotation": 0}}
        o = _writer_oracle.placements_from_json(data)
        s = shim_placements_from_json(data)
        assert_same(o, s, "from_json")
        assert s["U1"].ref == "U1"
        assert s["U1"].x == 10.0

    def test_roundtrip(self):
        from temper_placer.io.kicad_writer import PlacementUpdate

        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.5, y=20.5, rotation=180.0),
            "C1": PlacementUpdate(ref="C1", x=0.0, y=0.0, rotation=270.0),
        }
        restored = shim_placements_from_json(shim_placements_to_json(placements))
        for ref in placements:
            assert restored[ref].x == placements[ref].x
            assert restored[ref].y == placements[ref].y
            assert restored[ref].rotation == placements[ref].rotation

    def test_missing_key_raises_keyerror(self):
        """The oracle reads `values['x']` — a missing key raises
        KeyError('x'), not ValueError. Demonstrated RED pre-fix: oracle
        KeyError('x') vs kernel ValueError(\"missing 'x'\")."""
        from tests.io import _kicad_writer_py_oracle as _writer_oracle

        data = {"U1": {"y": 1.0, "rotation": 0.0}}
        with pytest.raises(KeyError) as eo:
            _writer_oracle.placements_from_json(data)
        with pytest.raises(KeyError) as es:
            shim_placements_from_json(data)
        assert eo.value.args == es.value.args == ("x",)

    def test_non_float_value_raises_valueerror(self):
        """A non-numeric value fails float() with CPython's exact message
        (value repr included) on both arms."""
        from tests.io import _kicad_writer_py_oracle as _writer_oracle

        data = {"U1": {"x": "abc", "y": 1.0, "rotation": 0.0}}
        with pytest.raises(ValueError) as eo:
            _writer_oracle.placements_from_json(data)
        with pytest.raises(ValueError) as es:
            shim_placements_from_json(data)
        assert str(eo.value) == str(es.value) == "could not convert string to float: 'abc'"


class TestTo247Slots:
    def test_compute_slots(self):
        o = _board_oracle.compute_to247_isolation_slots(["Q1", "Q2"])
        s = _board_shim.compute_to247_isolation_slots(["Q1", "Q2"])
        assert len(o) == len(s) == 2
        for oo, ss in zip(o, s):
            assert oo.name == ss.name
            assert oo.component_ref == ss.component_ref
            assert oo.start_offset == ss.start_offset
            assert oo.end_offset == ss.end_offset
            assert oo.width_mm == ss.width_mm
            assert oo.lv_pin == ss.lv_pin
            assert oo.hv_pin == ss.hv_pin
            assert oo.description == ss.description
        assert o[0].name == "q1_gate_isolation"
        assert o[0].start_offset == (-2.725, -5.0)

    def test_custom_dimensions(self):
        o = _board_oracle.compute_to247_isolation_slots(["Q1"], slot_width_mm=2.0, slot_length_mm=8.0)
        s = _board_shim.compute_to247_isolation_slots(["Q1"], slot_width_mm=2.0, slot_length_mm=8.0)
        assert o[0].width_mm == s[0].width_mm == 2.0
        assert o[0].end_offset == s[0].end_offset == (-2.725, 4.0)


class TestWriteTypesSurface:
    def test_placement_update_surface(self):

        from temper_placer.io.kicad_writer import PlacementUpdate

        u = PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0)
        assert u.ref == "U1"
        assert u.x == 10.0
        assert u.y == 20.0
        assert u.rotation == 90.0
        # mutability matches the dataclass
        u.x = 11.0
        assert u.x == 11.0

    def test_write_result_surface(self):
        from temper_placer.io.kicad_writer import WriteResult

        r = WriteResult(output_path=Path("/tmp/x.kicad_pcb"), components_updated=1, components_skipped=2, warnings=[])
        assert not r.has_warnings
        r2 = WriteResult(output_path=Path("/tmp/x.kicad_pcb"), components_updated=1, components_skipped=2, warnings=["w"])
        assert r2.has_warnings


class TestGetFootprintReference:
    def test_dict_properties(self, template):
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        fp = board.footprints[0]
        o = _types_oracle._get_footprint_reference(fp)
        s = _types_shim._get_footprint_reference(fp)
        assert o == "U1"
        assert s == "U1"

    def test_missing_reference(self, template):
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        fp = board.footprints[0]
        fp.properties = {}
        o = _types_oracle._get_footprint_reference(fp)
        s = _types_shim._get_footprint_reference(fp)
        assert o is None
        assert s is None


class TestComputePadBounds:
    def test_matches_verbatim_loop(self, template):
        """The oracle has no standalone bounds function (it is inlined in
        add_bounding_boxes/add_silkscreen); this reconstructs the verbatim
        loop from _write_modules.py and pins the kernel against it."""
        import temper_io_types as tio
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        fp = board.footprints[0]
        s = tio.compute_pad_bounds(fp)
        # verbatim loop (from _write_modules.py add_bounding_boxes_to_pcb)
        fp_x = fp.position.X if fp.position else 0.0
        fp_y = fp.position.Y if fp.position else 0.0
        fp_angle = fp.position.angle if fp.position and fp.position.angle else 0.0
        angle_rad = math.radians(fp_angle)
        x_min, y_min = float("inf"), float("inf")
        x_max, y_max = float("-inf"), float("-inf")
        for pad in fp.pads:
            local_x = pad.position.X if pad.position else 0.0
            local_y = pad.position.Y if pad.position else 0.0
            if abs(fp_angle) > 0.1:
                from temper_placer.geometry.kicad_transform import rotate_local_to_world

                rotated_x, rotated_y = rotate_local_to_world(local_x, local_y, angle_rad)
            else:
                rotated_x, rotated_y = local_x, local_y
            pad_w = pad.size.X if pad.size else 1.0
            pad_h = pad.size.Y if pad.size else 1.0
            abs_x = fp_x + rotated_x
            abs_y = fp_y + rotated_y
            x_min = min(x_min, abs_x - pad_w / 2)
            y_min = min(y_min, abs_y - pad_h / 2)
            x_max = max(x_max, abs_x + pad_w / 2)
            y_max = max(y_max, abs_y + pad_h / 2)
        assert_same(s, (x_min, y_min, x_max, y_max), "pad bounds")

    def test_rotated_footprint(self, template):
        import temper_io_types as tio
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        fp = board.footprints[0]
        fp.position.angle = 37.0
        s = tio.compute_pad_bounds(fp)
        fp.position.angle = 0.0
        s0 = tio.compute_pad_bounds(fp)
        assert s != s0  # rotation must change the bounds

    def test_no_pads_returns_none(self):
        import temper_io_types as tio

        fp = SimpleNamespace(position=None, pads=[])
        assert tio.compute_pad_bounds(fp) is None


class TestStatsAndMaps:
    def test_get_routing_statistics(self, routed_template):
        o = _tracks_oracle.get_routing_statistics(routed_template)
        s = _tracks_shim.get_routing_statistics(routed_template)
        assert_same(o, s, "stats")
        assert o["traces"] == 2
        assert o["vias"] == 1
        assert o["components"] == 2

    def test_net_name_to_index_map(self, template):
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        import temper_io_types as tio

        s = tio.net_name_to_index_map(board.nets)
        o = {}
        for net in board.nets:
            if hasattr(net, "name") and hasattr(net, "number"):
                o[net.name] = net.number
        assert_same(o, s, "net map")

    def test_build_net_name_to_index_map(self, template):
        o = _zones_oracle.build_net_name_to_index_map(template)
        s = _zones_shim.build_net_name_to_index_map(template)
        assert_same(o, s, "build net map")


# ---------------------------------------------------------------------------
# Full-function A/Bs — file-producing write functions
# ---------------------------------------------------------------------------


def _canon_result(r):
    if r is None:
        return None
    out = {}
    for field in (
        "output_path",
        "components_updated",
        "components_skipped",
        "traces_removed",
        "vias_removed",
        "zones_removed",
        "components_preserved",
        "slots_added",
        "slots_skipped",
        "segments_added",
        "vias_added",
        "nets_exported",
        "nets_failed",
        "warnings",
    ):
        if hasattr(r, field):
            if field == "output_path":
                # the two arms intentionally write to different files
                out[field] = ("path", str(getattr(r, field)).endswith(".kicad_pcb"))
            else:
                out[field] = _leaf(getattr(r, field))
    return tuple(sorted(out.items()))


class TestWritePlacementsAB:
    def test_mixed_rotations_asymmetric(self, template, tmp_path):
        from temper_placer.io.kicad_writer import PlacementUpdate

        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=10.0, rotation=0.0),
            "U2": PlacementUpdate(ref="U2", x=40.0, y=10.0, rotation=90.0),
        }
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.write_placements_to_pcb(template, out_o, placements)
        rs = _board_shim.write_placements_to_pcb(template, out_s, placements)
        assert out_o.read_bytes() == out_s.read_bytes(), "byte-identical output"
        assert _canon_result(ro) == _canon_result(rs)

    def test_center_offset_subtraction(self, template, tmp_path):
        from temper_placer.io.kicad_writer import PlacementUpdate

        comps = [SimpleNamespace(ref="U1", attributes={"_center_offset_x": "10", "_center_offset_y": "0"}),
                 SimpleNamespace(ref="U2", attributes={})]
        placements = {"U1": PlacementUpdate(ref="U1", x=100.0, y=100.0, rotation=90.0)}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        _ro = _board_oracle.write_placements_to_pcb(template, out_o, placements, components=comps)
        _rs = _board_shim.write_placements_to_pcb(template, out_s, placements, components=comps)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert "at 100.0 110.0 90.0" in out_s.read_text()  # R(-90).(10,0)=(0,-10)

    def test_preserve_unmatched_false_warns(self, template, tmp_path):
        from temper_placer.io.kicad_writer import PlacementUpdate

        placements = {"U1": PlacementUpdate(ref="U1", x=1.0, y=1.0, rotation=0.0)}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.write_placements_to_pcb(template, out_o, placements, preserve_unmatched=False)
        rs = _board_shim.write_placements_to_pcb(template, out_s, placements, preserve_unmatched=False)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert any("U2 not in placements" in w for w in rs.warnings)
        assert _canon_result(ro) == _canon_result(rs)

    def test_duplicate_ref_center_offset_last_wins(self, template, tmp_path):
        """Duplicate component refs: the oracle's dict
        `center_offsets[comp.ref] = (cx, cy)` is LAST-wins. A first-wins
        Vec+find would shift the written footprint by 1 mm (offset 1 vs 2).
        Demonstrated RED pre-fix: oracle `at 100.0 102.0 90.0` vs Vec
        `at 100.0 101.0 90.0`."""
        from temper_placer.io.kicad_writer import PlacementUpdate

        comps = [
            SimpleNamespace(ref="U1", attributes={"_center_offset_x": "1", "_center_offset_y": "0"}),
            SimpleNamespace(ref="U1", attributes={"_center_offset_x": "2", "_center_offset_y": "0"}),
        ]
        placements = {"U1": PlacementUpdate(ref="U1", x=100.0, y=100.0, rotation=90.0)}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.write_placements_to_pcb(template, out_o, placements, components=comps)
        rs = _board_shim.write_placements_to_pcb(template, out_s, placements, components=comps)
        assert out_o.read_bytes() == out_s.read_bytes()
        # R(-90).(2,0) = (0,-2): 100 - (-2) = 102 (the LAST duplicate wins)
        assert "at 100.0 102.0 90.0" in out_s.read_text()
        assert _canon_result(ro) == _canon_result(rs)

    def test_duplicate_ref_cross_kernel_consistency(self, template, tmp_path):
        """The SAME duplicate-ref input through both center-offset paths must
        agree: write_placements_plan's inline build and the
        extract_center_offsets kernel are last-wins on the same ref."""
        import temper_io_types as tio

        from temper_placer.io.kicad_writer import PlacementUpdate

        comps = [
            SimpleNamespace(ref="U1", attributes={"_center_offset_x": "1", "_center_offset_y": "0"}),
            SimpleNamespace(ref="U1", attributes={"_center_offset_x": "2", "_center_offset_y": "0"}),
        ]
        placements = {"U1": PlacementUpdate(ref="U1", x=100.0, y=100.0, rotation=90.0)}
        out_s = tmp_path / "s.kicad_pcb"
        _board_shim.write_placements_to_pcb(template, out_s, placements, components=comps)
        # the written y encodes which duplicate won: 102 => offset (2, 0)
        assert "at 100.0 102.0 90.0" in out_s.read_text(), "inline build is last-wins"
        offsets = tio.extract_center_offsets(comps)
        assert dict(offsets) == {"U1": (2.0, 0.0)}, "extract_center_offsets is last-wins"

    def test_footprint_without_position(self, template, tmp_path):
        from kiutils.board import Board as KiBoard

        from temper_placer.io.kicad_writer import PlacementUpdate

        board = KiBoard.from_file(str(template))
        board.footprints[1].position = None
        t = tmp_path / "t.kicad_pcb"
        board.to_file(str(t))
        placements = {"U2": PlacementUpdate(ref="U2", x=5.0, y=6.0, rotation=270.0)}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.write_placements_to_pcb(t, out_o, placements)
        rs = _board_shim.write_placements_to_pcb(t, out_s, placements)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)

    def test_pad_orientation_roundtrip(self, template, tmp_path):
        """Pad bodies must rotate with the footprint (the #374 class)."""
        from temper_placer.io.kicad_writer import PlacementUpdate

        placements = {"U1": PlacementUpdate(ref="U1", x=10.0, y=10.0, rotation=90.0)}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.write_placements_to_pcb(template, out_o, placements)
        rs = _board_shim.write_placements_to_pcb(template, out_s, placements)
        assert _canon_result(ro) == _canon_result(rs)
        assert out_o.read_bytes() == out_s.read_bytes()
        # pad 1 intrinsic 45: new absolute angle 90 + 45 = 135
        text = out_s.read_text()
        assert "at 10 10 90" in text or "at 10.0 10.0 90.0" in text


class TestReorientPads:
    def test_reorient(self, template):
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        fp = board.footprints[0]
        fp_o = KiBoard.from_file(str(template)).footprints[0]
        _board_oracle._reorient_pads(fp_o, 0.0, 90.0)
        _board_shim._reorient_pads(fp, 0.0, 90.0)
        for po, ps in zip(fp_o.pads, fp.pads):
            assert po.position.angle == ps.position.angle
        # pad 1 has intrinsic 45: 45 + 90 = 135; pad 2: 0 + 90 = 90
        assert fp.pads[0].position.angle == 135.0
        assert fp.pads[1].position.angle == 90.0

    def test_noop_when_delta_multiple_of_360(self, template):
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        fp = board.footprints[0]
        _board_shim._reorient_pads(fp, 30.0, 390.0)
        assert fp.pads[0].position.angle == 45.0  # untouched (intrinsic 45)


class TestExportRoutedPcbAB:
    def test_full_export(self, template, tmp_path):
        routes = {
            "GND": _grid_path(net="GND", cells=[GridCell(0, 0, 0), GridCell(2, 0, 0), GridCell(2, 2, 1)], cell_size=0.5),
            "VCC": _grid_path(net="VCC", cells=[GridCell(0, 3, 0), GridCell(3, 3, 0)], cell_size=0.5),
            "FAIL": _grid_path(net="FAIL", cells=[GridCell(0, 0, 0)], success=False, failure_reason="blocked"),
        }
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _exporter_oracle.export_routed_pcb(template, routes, out_o, auto_fill_zones=False)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = shim_export_routed_pcb(template, routes, out_s, auto_fill_zones=False)
        assert out_o.read_bytes() == out_s.read_bytes(), "byte-identical routed export"
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.nets_exported == 2
        assert rs.nets_failed == 1
        assert any("routing failed: blocked" in w for w in rs.warnings)

    def test_explicit_vias(self, template, tmp_path):
        routes = {
            "GND": _grid_path(
                net="GND",
                cells=[GridCell(0, 0, 0), GridCell(2, 0, 1)],
                cell_size=0.5,
                explicit_vias=[_via("GND", (1.0, 0.5))],
            )
        }
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            _ro = _exporter_oracle.export_routed_pcb(template, routes, out_o, auto_fill_zones=False)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = shim_export_routed_pcb(template, routes, out_s, auto_fill_zones=False)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert rs.vias_added == 1

    def test_via_dedup_round3(self, template, tmp_path):
        """Duplicate vias (within round(x,3) of each other) collapse to one.

        The route flips F.Cu -> In1.Cu -> F.Cu at the SAME grid cell, so the
        two layer transitions create vias at the identical position with the
        identical layer pair — the dedup key collides and only one may be
        emitted.
        """
        routes = {
            "GND": _grid_path(
                net="GND",
                cells=[GridCell(0, 0, 0), GridCell(0, 0, 1), GridCell(0, 0, 0)],
                cell_size=0.5,
            )
        }
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _exporter_oracle.export_routed_pcb(template, routes, out_o, auto_fill_zones=False)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = shim_export_routed_pcb(template, routes, out_s, auto_fill_zones=False)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.vias_added == 1  # deduped: both transitions at (0.25, 0.25)

    def test_round3_half_tick_key(self, template, tmp_path):
        """A via at a round-half-to-even boundary must dedup like CPython:
        10.0005 -> round(.,3) == 10.001 (exact value sits above the tie)."""
        vias = [_via("N1", (10.0005, 0.0)), _via("N1", (10.001, 0.0))]
        routes = {"N1": SimpleNamespace(net_name="N1", cells=[], explicit_vias=vias, success=True)}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _exporter_oracle.export_routed_pcb(template, routes, out_o, auto_fill_zones=False)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = shim_export_routed_pcb(template, routes, out_s, auto_fill_zones=False)
        assert out_o.read_bytes() == out_s.read_bytes()
        # both vias share the round-3 key -> dedup to 1
        assert ro.vias_added == 1
        assert rs.vias_added == 1


class TestExportBoardStateAB:
    def _state_via(self, net, position, width=0.8, drill=0.4, layers=None):
        """BoardState.vias are core.board.Via pyclasses (.width, not .size)."""
        from temper_placer.core.board import Via

        return Via(position=position, drill=drill, width=width, layers=layers or ["F.Cu", "B.Cu"], net=net)

    def test_full_export(self, template, tmp_path):
        state = SimpleNamespace(
            routes=[
                _segment("n1", (10.0, 10.0), (10.5, 10.5)),
                _segment("n1", (0.0, 0.0), (0.0, 0.0)),  # zero-length -> rejected
                _segment("n1", (10.4, 10.0), (30.0, 30.0)),  # endpoint snaps to pad
            ],
            vias=[
                self._state_via("n1", (10.25, 10.25)),
                self._state_via("n1", (10.250001, 10.25)),  # dedup pair
            ],
        )
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _exporter_oracle.export_board_state(template, state, out_o, auto_fill_zones=False)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = shim_export_board_state(template, state, out_s, auto_fill_zones=False)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.segments_added == 2  # zero-length rejected
        assert rs.vias_added == 1  # deduped

    def test_snapping(self, template, tmp_path):
        """A trace endpoint within 0.15mm of a pad snaps onto it."""
        state = SimpleNamespace(
            routes=[_segment("n1", (10.1, 10.1), (20.0, 20.0))],
            vias=[],
        )
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            _exporter_oracle.export_board_state(template, state, out_o, auto_fill_zones=False)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            shim_export_board_state(template, state, out_s, auto_fill_zones=False)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert "at 10 10" in out_s.read_text()


class TestExportFromGeometryAB:
    def test_full_export(self, template, tmp_path):
        from temper_placer.core.geometry_types import Point, Track
        from temper_placer.core.geometry_types import Via as GeoVia

        tracks = [
            Track(start=Point(1.0, 1.0), end=Point(5.0, 5.0), width=0.25, net="n1", layer=0),
            Track(start=Point(6.0, 6.0), end=Point(9.0, 9.0), width=0.25, net="n1", layer=3),
        ]
        vias = [GeoVia(center=Point(5.0, 5.0), diameter=0.8, drill=0.4, net="n1")]
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _exporter_oracle.export_from_geometry(template, out_o, tracks, vias)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = shim_export_from_geometry(template, out_s, tracks, vias)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.segments_added == 2
        assert rs.vias_added == 1


class TestStripRoutingAB:
    def test_strip_routing(self, routed_template, tmp_path):
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _tracks_oracle.strip_routing(routed_template, out_o)
        rs = _tracks_shim.strip_routing(routed_template, out_s)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.traces_removed == 2
        assert rs.vias_removed == 1
        assert rs.components_preserved == 2

    def test_strip_zones_too(self, routed_template, tmp_path):
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        _ro = _tracks_oracle.strip_routing(routed_template, out_o, keep_zones=False)
        rs = _tracks_shim.strip_routing(routed_template, out_s, keep_zones=False)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert rs.zones_removed == 1
        assert "zone" not in out_s.read_text()

    def test_strip_keep_fills(self, routed_template, tmp_path):
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        _ro = _tracks_oracle.strip_routing(routed_template, out_o, keep_fills=True)
        _rs = _tracks_shim.strip_routing(routed_template, out_s, keep_fills=True)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert "filled_polygon" in out_s.read_text()

    def test_strip_preserve_nets(self, routed_template, tmp_path):
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _tracks_oracle.strip_routing_preserve_nets(routed_template, out_o)
        rs = _tracks_shim.strip_routing_preserve_nets(routed_template, out_s)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)


class TestWriteRoutesAB:
    def test_write_routes(self, template, tmp_path):
        from temper_placer.core.board import Via as BoardVia

        routes = {_segment("n1", (1.0, 1.0), (5.0, 5.0))}
        vias = {BoardVia(position=(5.0, 5.0), drill=0.4, width=0.8, layers=("F.Cu", "B.Cu"), net="n1")}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _tracks_oracle.write_routes_to_pcb(template, out_o, routes, vias)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = _tracks_shim.write_routes_to_pcb(template, out_s, routes, vias)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.components_updated == 1  # traces added

    def test_unknown_net_warns(self, template, tmp_path):
        from temper_placer.core.board import Via as BoardVia

        routes = {_segment("MISSING", (1.0, 1.0), (5.0, 5.0))}
        vias = {BoardVia(position=(5.0, 5.0), drill=0.4, width=0.8, layers=("F.Cu", "B.Cu"), net="MISSING")}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            _ro = _tracks_oracle.write_routes_to_pcb(template, out_o, routes, vias)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = _tracks_shim.write_routes_to_pcb(template, out_s, routes, vias)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert any("MISSING" in w and "index 0" in w for w in rs.warnings)

    def test_clear_existing(self, routed_template, tmp_path):
        routes = {_segment("n1", (1.0, 1.0), (5.0, 5.0))}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            _ro = _tracks_oracle.write_routes_to_pcb(routed_template, out_o, routes, clear_existing=True)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = _tracks_shim.write_routes_to_pcb(routed_template, out_s, routes, clear_existing=True)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert any("Cleared 3 existing trace items" in w for w in rs.warnings)

    def test_explicit_empty_net_map_not_rebuilt(self, tmp_path):
        """An explicitly-passed empty net_name_to_index must NOT be rebuilt:
        the oracle builds the map only `if net_name_to_index is None`. A
        caller passing `{}` gets index 0 + the not-found warning even when
        the board HAS nets; silently rebuilding would assign the real index
        and drop the warning. Demonstrated RED pre-fix: oracle warning +
        `(net 0)` vs shim no-warning + `(net 1)`."""
        content = (
            "(kicad_pcb (version 20240108) (generator pcbnew)\n"
            "  (general (thickness 1.6))\n"
            '  (paper "A4")\n'
            "  (layers\n"
            '    (0 "F.Cu" signal)\n    (31 "B.Cu" signal)\n'
            '    (44 "Edge.Cuts" user)\n'
            "  )\n"
            "  (setup (pad_to_mask_clearance 0))\n"
            '  (net 0 "")\n  (net 1 "n1")\n'
            f"{_asymmetric_fp('U1', (10.0, 10.0, None))}\n{_asymmetric_fp('U2', (40.0, 10.0, None))}\n"
            ")\n"
        )
        t = tmp_path / "t.kicad_pcb"
        t.write_text(content, encoding="utf-8")
        routes = {_segment("n1", (1.0, 1.0), (5.0, 5.0))}
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _tracks_oracle.write_routes_to_pcb(t, out_o, routes, net_name_to_index={})
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = _tracks_shim.write_routes_to_pcb(t, out_s, routes, net_name_to_index={})
        assert out_o.read_bytes() == out_s.read_bytes()
        assert ro.warnings == rs.warnings == ["Net 'n1' not found in board, using index 0"]
        assert "(net 0)" in out_s.read_text() and "(net 1)" not in out_s.read_text()
        assert _canon_result(ro) == _canon_result(rs)


class TestWriteZonesAB:
    def test_write_zones(self, template, tmp_path):
        zones = [{"net_name": "n1", "layer": "F.Cu", "polygon_pts": [(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)]}]
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            ro = _zones_oracle.write_zones_to_pcb(template, out_o, zones)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            rs = _zones_shim.write_zones_to_pcb(template, out_s, zones)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.components_updated == 1

    def test_int_coordinates_pass_through(self, template, tmp_path):
        """Integer polygon coordinates must reach the kiutils sexpr as ints
        ('3', not '3.0'): the oracle forwards p[0]/p[1] raw through
        Position(). Extracting the plan's pts to f64 would coerce the
        rendering."""
        zones = [{"net_name": "n1", "layer": "F.Cu", "polygon_pts": [(0, 0), (5, 0), (5, 5), (0, 5)]}]
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            _zones_oracle.write_zones_to_pcb(template, out_o, zones)
        with unittest.mock.patch("uuid.uuid4", side_effect=_uuid_seq()):
            _zones_shim.write_zones_to_pcb(template, out_s, zones)
        assert out_o.read_bytes() == out_s.read_bytes()
        text = out_s.read_text()
        assert "(xy 0 0)" in text and "(xy 5 0)" in text and "(xy 5 5)" in text


class TestIsolationSlotsAB:
    def test_add_slots(self, template, tmp_path):
        slots = [
            SimpleNamespace(
                name="q1_slot",
                component_ref="U1",
                start_offset=(-2.0, -2.5),
                end_offset=(-2.0, 7.5),
                width_mm=1.5,
            )
        ]
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.add_isolation_slots_to_pcb(template, slots, out_o)
        rs = _board_shim.add_isolation_slots_to_pcb(template, slots, out_s)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
        assert rs.slots_added == 1

    def test_rotated_component_slot(self, template, tmp_path):
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        board.footprints[0].position.angle = 90.0
        t = tmp_path / "t.kicad_pcb"
        board.to_file(str(t))
        slots = [
            SimpleNamespace(
                name="rot_slot",
                component_ref="U1",
                start_offset=(1.0, 0.0),
                end_offset=(1.0, 5.0),
                width_mm=1.5,
            )
        ]
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.add_isolation_slots_to_pcb(t, slots, out_o)
        rs = _board_shim.add_isolation_slots_to_pcb(t, slots, out_s)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)

    def test_missing_component(self, template, tmp_path):
        slots = [SimpleNamespace(name="missing", component_ref="ZZZ", start_offset=(0, 0), end_offset=(1, 1), width_mm=1.0)]
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        _ro = _board_oracle.add_isolation_slots_to_pcb(template, slots, out_o)
        rs = _board_shim.add_isolation_slots_to_pcb(template, slots, out_s)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert any("ZZZ" in w for w in rs.warnings)
        assert rs.slots_skipped == 1


class TestModuleAnnotationsAB:
    def test_bounding_boxes(self, template):
        import shutil

        o = template.parent / "o.kicad_pcb"
        s = template.parent / "s.kicad_pcb"
        shutil.copy(template, o)
        shutil.copy(template, s)
        ro = _modules_oracle.add_bounding_boxes_to_pcb(o)
        rs = _modules_shim.add_bounding_boxes_to_pcb(s)
        assert o.read_bytes() == s.read_bytes()
        assert ro == rs
        assert ro == 2

    def test_silkscreen_labels(self, template):
        import shutil

        o = template.parent / "o.kicad_pcb"
        s = template.parent / "s.kicad_pcb"
        shutil.copy(template, o)
        shutil.copy(template, s)
        ro = _modules_oracle.add_silkscreen_labels(o)
        rs = _modules_shim.add_silkscreen_labels(s)
        assert o.read_bytes() == s.read_bytes()
        assert ro == rs
        assert rs["references"] == 2
        assert rs["values"] == 2  # template has Value props
        assert rs["outlines"] == 2

    def test_silkscreen_no_values(self, template):
        import shutil

        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template))
        for fp in board.footprints:
            fp.properties = {"Reference": fp.properties["Reference"]}
        t = template.parent / "t.kicad_pcb"
        board.to_file(str(t))
        o = template.parent / "o.kicad_pcb"
        s = template.parent / "s.kicad_pcb"
        shutil.copy(t, o)
        shutil.copy(t, s)
        ro = _modules_oracle.add_silkscreen_labels(o)
        rs = _modules_shim.add_silkscreen_labels(s)
        assert o.read_bytes() == s.read_bytes()
        assert ro == rs
        assert rs["values"] == 0


class TestValidateOutputPcbAB:
    def test_valid(self, template):
        assert _board_oracle.validate_output_pcb(template) == _board_shim.validate_output_pcb(template)

    def test_missing_file(self, tmp_path):
        assert _board_oracle.validate_output_pcb(tmp_path / "nope.kicad_pcb") == \
            _board_shim.validate_output_pcb(tmp_path / "nope.kicad_pcb")


# ---------------------------------------------------------------------------
# corpus end-to-end
# ---------------------------------------------------------------------------


class TestCorpusEndToEnd:
    def test_corpus_strip_stats(self, tmp_path):
        """Run the write path over a real corpus board (both arms byte-equal)."""
        board = _corpus_temper()
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _tracks_oracle.strip_routing(board, out_o, keep_zones=True)
        rs = _tracks_shim.strip_routing(board, out_s, keep_zones=True)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)

    def test_corpus_placements(self, tmp_path):
        from kiutils.board import Board as KiBoard

        from temper_placer.io.kicad_writer import PlacementUpdate

        board = _corpus_temper()
        ki = KiBoard.from_file(str(board))
        fps = ki.footprints[:3]
        placements = {}
        for i, fp in enumerate(fps):
            from temper_placer.io._write_types import _get_footprint_reference

            ref = _get_footprint_reference(fp)
            if ref:
                placements[ref] = PlacementUpdate(ref=ref, x=10.0 + i, y=20.0 + i, rotation=90.0 * i)
        out_o = tmp_path / "o.kicad_pcb"
        out_s = tmp_path / "s.kicad_pcb"
        ro = _board_oracle.write_placements_to_pcb(board, out_o, placements)
        rs = _board_shim.write_placements_to_pcb(board, out_s, placements)
        assert out_o.read_bytes() == out_s.read_bytes()
        assert _canon_result(ro) == _canon_result(rs)
