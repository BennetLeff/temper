"""Routing-data (traces/vias/zones) bridge tests — issue #873.

``packages/temper-drc-rs/src/board_py_bridge.rs``'s ``build_board_state``
(and the ``BoardState`` struct it fills, in ``board.rs``) already had full
support for the K1 schema's optional ``traces``/``vias``/``zones`` keys —
the gap that made every routing-family DRC check in the WASM verification
tier's R2 cost-model run against an *empty* board was entirely in the
Python-side producer (``tools/wasm/r2_serialize_board.py``), which never
populated those keys. See ``tests/scripts/test_r2_serialize_board.py`` for
that producer's own unit tests.

These tests exercise the bridge itself (via
``temper_drc_rs.serialize_board_state``, the same entry point the R2
producer calls) directly against the K1 schema, independent of the KiCad
parser:

1. Routing data actually arrives — an N-segment/M-via/K-zone board dict
   yields exactly N/M/K entries in the serialized ``BoardState``. A test
   that only checked the field's *presence* would not catch an
   empty-list regression, which is exactly the bug this closes.
2. Serialization is deterministic — two independently-built board dicts
   with identical content produce byte-identical JSON. Required by R5
   (content-hash-addressed findings) per the R3 producer's recorded
   frozenset-ordering caveat (``docs/evidence/2026-08-07-r3-frozenset-order-verification.md``).
"""

from __future__ import annotations

import copy
import json
from typing import Any

import temper_drc_rs as _tdrc


def _minimal_board_dict(**overrides: Any) -> dict[str, Any]:
    """The smallest valid K1-schema dict (see ``build_board_state``'s
    docstring in ``board_py_bridge.rs``), with ``traces``/``vias``/``zones``
    overridable by the caller.
    """
    board_dict: dict[str, Any] = {
        "board": {"width_mm": 172.0, "height_mm": 234.0, "margin_mm": 3.0},
        "components": [],
        "nets": {},
        "net_classes": {},
        "net_class_rules": {},
    }
    board_dict.update(overrides)
    return board_dict


def _n_traces(n: int, segments_per_trace: int = 1) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        segs = [
            [float(i), float(j), float(i) + 1.0, float(j) + 1.0]
            for j in range(segments_per_trace)
        ]
        out.append({"net": f"NET_{i}", "layer": "F.Cu", "width": 0.25, "segments": segs})
    return out


def _m_vias(m: int) -> list[dict[str, Any]]:
    return [
        {
            "net": f"NET_{i}",
            "x": float(i),
            "y": float(i) * 2.0,
            "drill": 0.3,
            "pad": 0.6,
            "from_layer": "F.Cu",
            "to_layer": "B.Cu",
        }
        for i in range(m)
    ]


def _k_zones(k: int) -> list[dict[str, Any]]:
    return [
        {
            "net": f"NET_{i}",
            "layer": "F.Cu" if i % 2 == 0 else "B.Cu",
            "polygon": [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
        }
        for i in range(k)
    ]


# ---------------------------------------------------------------------------
# 1. Routing data actually arrives (anti-vacuity: N in -> N in BoardState)
# ---------------------------------------------------------------------------


def test_n_traces_yields_n_traces_in_board_state():
    n = 7
    board_dict = _minimal_board_dict(traces=_n_traces(n))
    board_json = json.loads(_tdrc.serialize_board_state(board_dict))
    assert len(board_json["traces"]) == n


def test_trace_segments_are_preserved_not_just_the_trace_count():
    """A trace with multiple line segments must keep all of them — this
    catches a regression that preserves the trace *count* but drops or
    truncates the nested ``segments`` list.
    """
    board_dict = _minimal_board_dict(traces=_n_traces(3, segments_per_trace=4))
    board_json = json.loads(_tdrc.serialize_board_state(board_dict))
    assert len(board_json["traces"]) == 3
    for trace in board_json["traces"]:
        assert len(trace["segments"]) == 4


def test_m_vias_yields_m_vias_in_board_state():
    m = 5
    board_dict = _minimal_board_dict(vias=_m_vias(m))
    board_json = json.loads(_tdrc.serialize_board_state(board_dict))
    assert len(board_json["vias"]) == m


def test_k_zones_yields_k_zones_in_board_state():
    k = 4
    board_dict = _minimal_board_dict(zones=_k_zones(k))
    board_json = json.loads(_tdrc.serialize_board_state(board_dict))
    assert len(board_json["zones"]) == k


def test_empty_board_still_round_trips_to_empty_routing_lists():
    """Regression guard for the inverse failure mode: omitting the keys
    entirely must still produce empty (not missing/null) lists, matching
    ``BoardState``'s ``Vec::new()`` defaults in ``board.rs``.
    """
    board_json = json.loads(_tdrc.serialize_board_state(_minimal_board_dict()))
    assert board_json["traces"] == []
    assert board_json["vias"] == []
    assert board_json["zones"] == []


def test_routing_data_survives_alongside_nonempty_board():
    """Combines all three so a bridge regression that only wires up one of
    traces/vias/zones (while leaving the others silently empty) is caught.
    """
    board_dict = _minimal_board_dict(
        traces=_n_traces(11), vias=_m_vias(6), zones=_k_zones(3)
    )
    board_json = json.loads(_tdrc.serialize_board_state(board_dict))
    assert len(board_json["traces"]) == 11
    assert len(board_json["vias"]) == 6
    assert len(board_json["zones"]) == 3


# ---------------------------------------------------------------------------
# 2. Determinism (R5: content-hash-addressed findings)
# ---------------------------------------------------------------------------


def test_serialize_board_state_is_deterministic_across_independent_dicts():
    """Two structurally-identical but independently-constructed board
    dicts (own list/dict objects, not shared references) must serialize to
    byte-identical JSON. Guards against the frozenset/dict-hash-order
    nondeterminism class recorded in
    ``docs/evidence/2026-08-07-r3-frozenset-order-verification.md`` (R3's
    frozenset-ordering caveat) leaking into the bridge's own serialization.
    """
    board_dict_1 = _minimal_board_dict(
        traces=_n_traces(20, segments_per_trace=3),
        vias=_m_vias(15),
        zones=_k_zones(9),
    )
    board_dict_2 = copy.deepcopy(board_dict_1)
    assert board_dict_1 is not board_dict_2

    json_1 = _tdrc.serialize_board_state(board_dict_1)
    json_2 = _tdrc.serialize_board_state(board_dict_2)
    assert json_1 == json_2


def test_serialize_board_state_is_stable_across_repeated_calls():
    """The same dict, serialized N times in a row, must always produce the
    same bytes (catches per-call nondeterminism, e.g. HashMap iteration
    order surfacing in repeated calls within one process).
    """
    board_dict = _minimal_board_dict(
        traces=_n_traces(12), vias=_m_vias(8), zones=_k_zones(5)
    )
    outputs = {_tdrc.serialize_board_state(board_dict) for _ in range(5)}
    assert len(outputs) == 1
