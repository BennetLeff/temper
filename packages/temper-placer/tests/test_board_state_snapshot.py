"""Tests for BoardState.copy() and StageOutput.to_snapshot_dict() (U4)."""

from temper_placer.deterministic.state import BoardState


class TestBoardStateCopy:
    """Test BoardState.copy() method."""

    def test_copy_creates_distinct_object(self):
        """copy() returns a distinct object from the original."""
        state = BoardState()
        copied = state.copy()
        assert copied is not state
        assert id(copied) != id(state)

    def test_copy_preserves_field_values(self):
        """Copy preserves all field values."""
        state = BoardState(
            board=None,
            netlist=None,
            loops=None,
            grid=None,
            drc_oracle=None,
            net_order=("NET1", "NET2"),
            locked_routes=frozenset({"NET1"}),
        )
        copied = state.copy()
        assert copied.board is state.board
        assert copied.net_order == state.net_order
        assert copied.locked_routes == state.locked_routes

    def test_copy_is_independent(self):
        """Modifications to one copy don't affect the original."""
        state = BoardState()
        copied = state.copy()
        modified = copied.with_locked_route("NET_NEW")
        assert "NET_NEW" in modified.locked_routes
        assert "NET_NEW" not in state.locked_routes
        assert "NET_NEW" not in copied.locked_routes

    def test_copy_empty_state(self):
        """Copy of empty state works."""
        state = BoardState()
        copied = state.copy()
        assert copied.board is None
        assert copied.netlist is None
        assert copied.net_order == ()
        assert copied.locked_routes == frozenset()
