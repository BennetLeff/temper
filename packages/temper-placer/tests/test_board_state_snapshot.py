"""Tests for BoardState frozen dataclass immutability (U4)."""

from temper_placer.deterministic.state import BoardState


class TestBoardStateImmutability:
    """Test BoardState frozen dataclass operations."""

    def test_with_locked_route_creates_new_state(self):
        """with_locked_route returns a new distinct BoardState."""
        state = BoardState()
        modified = state.with_locked_route("NET1")
        assert modified is not state
        assert "NET1" not in state.locked_routes
        assert "NET1" in modified.locked_routes

    def test_with_locked_route_preserves_fields(self):
        """with_locked_route preserves other field values."""
        state = BoardState(
            board=None,
            netlist=None,
            net_order=("NET1", "NET2"),
            locked_routes=frozenset(),
        )
        modified = state.with_locked_route("NET_NEW")
        assert modified.net_order == state.net_order
        assert "NET_NEW" in modified.locked_routes
        assert "NET_NEW" not in state.locked_routes

    def test_with_locked_routes_adds_multiple(self):
        """with_locked_routes adds multiple nets atomically."""
        state = BoardState(locked_routes=frozenset({"A"}))
        result = state.with_locked_routes({"B", "C"})
        assert result.locked_routes == frozenset({"A", "B", "C"})

    def test_default_state_is_valid(self):
        """Default BoardState has sane defaults."""
        state = BoardState()
        assert state.board is None
        assert state.netlist is None
        assert state.net_order == ()
        assert state.locked_routes == frozenset()

    def test_is_route_locked(self):
        """is_route_locked correctly reports lock status."""
        state = BoardState(locked_routes=frozenset({"NET1"}))
        assert state.is_route_locked("NET1")
        assert not state.is_route_locked("NET2")
