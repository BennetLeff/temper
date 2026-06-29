from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.routing_failure_handler import FlaggedNet, handle_routing_failures


def test_handle_routing_failures():
    # Mock a pathfinding result with one success and one failure
    result = PathfindingResult(
        routed_paths={"NET1": None}, # Value doesn't matter for this test
        failed_nets=["NET2"]
    )

    report = handle_routing_failures(result)

    assert report.failure_count == 1
    assert "NET2" in report.flagged_nets

    flagged = report.flagged_nets["NET2"]
    assert isinstance(flagged, FlaggedNet)
    assert flagged.net_name == "NET2"
    assert len(flagged.suggestions) > 0
    # failure_point, blocking_nets, etc. are currently placeholders but should be present
    assert flagged.failure_point is not None

def test_no_failures():
    result = PathfindingResult(
        routed_paths={"NET1": None},
        failed_nets=[]
    )

    report = handle_routing_failures(result)
    assert report.failure_count == 0
