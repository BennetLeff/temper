"""Focused execution tests for the Net-41 corridor campaign driver."""

from __future__ import annotations

from scripts import run_net41_corridor_campaign as campaign


def test_materialize_candidate_threads_moved_board_into_rust_route_writer(
    monkeypatch,
) -> None:
    instruction = {
        "candidate_id": "NET41-CORRIDOR-" + "a" * 64,
        "footprint_positions": [
            {"reference": "R14", "x_mm": 1.0, "y_mm": 2.0, "rotation_deg": 90.0}
        ],
        "route_net": 41,
        "route_layer": "In3.Cu",
        "route_width_mm": 5.0,
        "via_size_mm": 2.0,
        "via_drill_mm": 1.0,
        "via_span": ["In3.Cu", "F.Cu"],
        "fixed_ref": "C7",
        "fixed_pad_number": "1",
        "moving_ref": "R14",
        "moving_pad_number": "2",
        "old_segment_tstamps": ["old-segment"],
        "old_via_tstamp": "old-via",
        "route_points": [[0.0, 0.0], [1.0, 1.0]],
    }
    parse_engine = campaign.design_bundle.parse_engine
    monkeypatch.setattr(
        parse_engine,
        "update_declared_footprint_positions_exact_py",
        lambda board, placements: f"moved:{board}:{placements!r}",
    )

    def replace(board, *args):
        assert board.startswith("moved:base-board:")
        assert args[0] == instruction["candidate_id"]
        assert args[-1] == [tuple(point) for point in instruction["route_points"]]
        return "routed-board"

    monkeypatch.setattr(parse_engine, "replace_declared_route_with_points_py", replace)

    assert campaign.materialize_candidate("base-board", instruction) == "routed-board"
