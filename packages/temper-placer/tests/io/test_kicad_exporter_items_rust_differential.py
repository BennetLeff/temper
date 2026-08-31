"""Differential test: the ``kicad_exporter.py`` board-item additions
(``segment_sexpr_py`` / ``via_sexpr_py``) vs the pinned Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates ``add_segments_to_board`` /
``add_vias_to_board``'s Segment/Via constructions. Net-code lookup remains
Python object plumbing rather than a Rust boundary.

The Rust kernels return parsed s-expression trees that kiutils'
`Segment.from_sexpr` / `Via.from_sexpr` consume; the oracle constructs the
kiutils dataclasses directly (verbatim pin,
``_kicad_exporter_items_py_oracle.py``, origin/main ``5e528b8aa`` — a
separate file because the sibling ``_kicad_exporter_py_oracle.py`` is itself
a frozen pin). The exporter tstamps are random `uuid.uuid4()` in the
pre-migration code and stay random (deliberately not determinized); the
oracle parameterises them.

"""

from __future__ import annotations

from kiutils.items.brditems import Segment, Via
from temper_io_types import kicad_write_geometry as _GEOM

import tests.io._kicad_exporter_items_py_oracle as _oracle

TSTAMP = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ---------------------------------------------------------------------------
# segment / via construction byte-identity
# ---------------------------------------------------------------------------


def test_segment_construction_matches_oracle_byte_identical():
    start, end, width, layer, net = (1.5, 2.5), (3.5, 4.5), 0.254, "F.Cu", 2
    py_text = _oracle.segment_to_sexpr(start, end, width, layer, net, TSTAMP)
    rust_text = Segment.from_sexpr(
        _GEOM.segment_sexpr_py(start[0], start[1], end[0], end[1], width, layer, net, TSTAMP)
    ).to_sexpr()
    assert rust_text == py_text


def test_via_construction_matches_oracle_byte_identical():
    pos, size, drill, layers, net = (1.5, 2.5), 0.6, 0.3, ["F.Cu", "B.Cu"], 2
    py_text = _oracle.via_to_sexpr(pos, size, drill, layers, net, TSTAMP)
    rust_text = Via.from_sexpr(
        _GEOM.via_sexpr_py(pos[0], pos[1], size, drill, layers, net, TSTAMP)
    ).to_sexpr()
    assert rust_text == py_text


# ---------------------------------------------------------------------------
# Delegation proofs
# ---------------------------------------------------------------------------
