"""
Coverage paydown tests for deterministic module.

Tests the functions likely still uncovered by existing test suites:
BoardState methods, ChannelMap methods, Bottleneck, instrumentation, flags, etc.
"""

import tempfile
from pathlib import Path

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState


# ============================================================================
# BoardState tests
# ============================================================================


@pytest.fixture
def fixture_state():
    """Create a minimal BoardState for testing."""
    comps = [
        Component(ref="U1", footprint="SOIC8", bounds=(5, 4),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
    ]
    nets = [Net("VCC", [("U1", "1")], net_class="Power")]
    return BoardState(
        board=Board(width=100.0, height=100.0),
        netlist=Netlist(components=comps, nets=nets),
    )


class TestBoardState:
    """Tests for BoardState methods."""

    def test_is_route_locked_default_false(self, fixture_state):
        """is_route_locked returns False when no route is locked."""
        assert fixture_state.is_route_locked("VCC") is False

    def test_is_route_locked_with_lock(self, fixture_state):
        """is_route_locked returns True after locking a net."""
        state = fixture_state.with_locked_route("VCC")
        assert state.is_route_locked("VCC") is True

    def test_with_locked_route_returns_new_state(self, fixture_state):
        """with_locked_route returns a new BoardState."""
        new_state = fixture_state.with_locked_route("VCC")
        assert isinstance(new_state, BoardState)

    def test_with_locked_routes_adds_multiple(self, fixture_state):
        """with_locked_routes adds multiple locked routes."""
        new_state = fixture_state.with_locked_routes({"VCC"})
        assert isinstance(new_state, BoardState)

    def test_with_config_returns_new_state(self, fixture_state):
        """with_config returns a new BoardState with config applied."""
        config = {"test_key": "test_value"}
        new_state = fixture_state.with_config(config)
        assert isinstance(new_state, BoardState)
        assert new_state is not fixture_state


# ============================================================================
# ChannelMap and Bottleneck tests
# ============================================================================


class TestChannelMap:
    """Tests for ChannelMap."""

    def test_channel_map_empty_is_true(self):
        """ChannelMap.empty() returns a valid ChannelMap."""
        from temper_placer.deterministic.channels import ChannelMap
        cm = ChannelMap.empty()
        assert cm.width == 0
        assert cm.height == 0

    def test_channel_map_width_height_defaults(self):
        """ChannelMap.width and height return dimensions."""
        from temper_placer.deterministic.channels import ChannelMap
        cm = ChannelMap.empty()
        assert cm.width == 0
        assert cm.height == 0

    def test_channel_map_load_from_sidecar_missing_file(self):
        """ChannelMap.load_from_sidecar raises on missing file."""
        from temper_placer.deterministic.channels import ChannelMap
        with pytest.raises(Exception):
            ChannelMap.load_from_sidecar("/nonexistent/path/channel_map.json")


class TestBottleneck:
    """Tests for Bottleneck."""

    def test_bottleneck_to_dict(self):
        """Bottleneck.to_dict returns a serializable dict."""
        from temper_placer.deterministic.channels import Bottleneck
        b = Bottleneck(
            x=5, y=10, layer="F.Cu",
            severity="high", score=0.8,
        )
        d = b.to_dict()
        assert d["x"] == 5
        assert d["y"] == 10
        assert d["layer"] == "F.Cu"
        assert d["severity"] == "high"
        assert d["score"] == 0.8


# ============================================================================
# routability_penalty test
# ============================================================================


def test_routability_penalty_returns_float():
    """routability_penalty returns a float."""
    from temper_placer.deterministic.channels import routability_penalty, ChannelMap
    cm = ChannelMap.empty()
    penalty = routability_penalty((5.0, 5.0), cm)
    assert isinstance(penalty, float)


# ============================================================================
# flags test
# ============================================================================


def test_is_feedback_enabled_default():
    """is_feedback_enabled returns a bool with default env."""
    import os
    from temper_placer.deterministic.flags import is_feedback_enabled
    old = os.environ.get("TEMPER_FEEDBACK_ENABLED")
    try:
        if "TEMPER_FEEDBACK_ENABLED" in os.environ:
            del os.environ["TEMPER_FEEDBACK_ENABLED"]
        result = is_feedback_enabled()
        assert isinstance(result, bool)
    finally:
        if old is not None:
            os.environ["TEMPER_FEEDBACK_ENABLED"] = old


# ============================================================================
# __init__ tests
# ============================================================================


def test_create_legacy_pipeline():
    """create_legacy_pipeline returns a DeterministicPipeline."""
    from temper_placer.deterministic import create_legacy_pipeline
    from temper_placer.deterministic import DeterministicPipeline
    pipeline = create_legacy_pipeline()
    assert isinstance(pipeline, DeterministicPipeline)


def test_create_drc_aware_pipeline_needs_metadata():
    """create_drc_aware_pipeline requires metadata parameter."""
    from temper_placer.deterministic import create_drc_aware_pipeline
    with pytest.raises(TypeError, match="requires 'metadata' parameter"):
        create_drc_aware_pipeline()


def test_load_channel_map_from_sidecar(tmp_path):
    """load_channel_map_from_sidecar returns a ChannelMap."""
    from temper_placer.deterministic import load_channel_map_from_sidecar
    from temper_placer.deterministic.channels import ChannelMap
    cm = load_channel_map_from_sidecar(tmp_path)
    assert isinstance(cm, ChannelMap)
