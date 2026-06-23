"""Tests for golden serializers — U1."""
import json
import pytest
import yaml

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.io.golden_serializers import (
    CURRENT_FORMAT_VERSION,
    SERIALIZER_REGISTRY,
    serialize_boardstate_to_dsn,
    serialize_boardstate_to_ses,
    serialize_connectivity_to_json,
    serialize_violations_to_json,
)


def _make_minimal_state():
    board = Board(width=100, height=80)
    comp = Component(
        ref="U1",
        footprint="SOIC-8",
        bounds=(5.0, 4.0),
        pins=[Pin("VCC", "1", (2.0, 1.5)), Pin("GND", "4", (-2.0, -1.5))],
        initial_position=(50.0, 50.0),
        initial_rotation=0,
    )
    netlist = Netlist(
        components=[comp],
        nets=[Net("NET1", [("U1", "1"), ("U1", "4")])],
    )
    state = BoardState(board=board, netlist=netlist, placements=frozenset({("U1", (50.0, 50.0))}))
    return state


def test_serialize_dsn_basic():
    state = _make_minimal_state()
    output = serialize_boardstate_to_dsn(state)
    assert output.startswith("(pcb")
    assert "(layer" in output
    assert "(place U1" in output
    assert "(net NET1" in output


def test_serialize_dsn_deterministic():
    state = _make_minimal_state()
    output1 = serialize_boardstate_to_dsn(state)
    output2 = serialize_boardstate_to_dsn(state)
    assert output1 == output2


def test_serialize_ses_basic():
    board = Board(width=100, height=80)
    state = BoardState(board=board, routes=frozenset())
    output = serialize_boardstate_to_ses(state)
    assert output.startswith("(session")
    assert "(routes)" in output


def test_serialize_ses_deterministic():
    board = Board(width=100, height=80)
    state = BoardState(board=board, routes=frozenset())
    output1 = serialize_boardstate_to_ses(state)
    output2 = serialize_boardstate_to_ses(state)
    assert output1 == output2


def test_serialize_violations_to_json():
    state = BoardState(drc_violations=())
    output = serialize_violations_to_json(state)
    data = json.loads(output)
    assert data["format_version"] == CURRENT_FORMAT_VERSION
    assert data["violations"] == []


def test_serialize_violations_sort_keys():
    state = BoardState(drc_violations=())
    output = serialize_violations_to_json(state)
    data = json.loads(output)
    keys = sorted(data.keys())
    assert list(data.keys()) == keys


def test_serialize_connectivity_to_json():
    state = BoardState(connectivity_violations=())
    output = serialize_connectivity_to_json(state)
    data = json.loads(output)
    assert data["format_version"] == CURRENT_FORMAT_VERSION
    assert data["violations"] == []


def test_serializer_registry_has_all_names():
    assert "serialize_boardstate_to_dsn" in SERIALIZER_REGISTRY
    assert "serialize_boardstate_to_ses" in SERIALIZER_REGISTRY
    assert "serialize_violations_to_json" in SERIALIZER_REGISTRY
    assert "serialize_connectivity_to_json" in SERIALIZER_REGISTRY


def test_serializer_registry_callables():
    for name, fn in SERIALIZER_REGISTRY.items():
        assert callable(fn), f"Serializer {name} is not callable"


def test_serialize_dsn_raises_on_missing_board():
    state = BoardState()
    with pytest.raises(ValueError, match="board"):
        serialize_boardstate_to_dsn(state)


def test_serialize_dsn_raises_on_missing_netlist():
    board = Board(width=100, height=80)
    state = BoardState(board=board)
    with pytest.raises(ValueError, match="netlist"):
        serialize_boardstate_to_dsn(state)
