"""Tests for register_strategies.py — U7 coverage paydown."""

import pytest

from temper_placer.adapters.register_strategies import PlacementStage, RoutingStage
from temper_placer.protocol import StageInput, StageMeta, StageOutput


class TestPlacementStage:
    """Tests for PlacementStage adapter."""

    def test_placement_stage_defaults(self):
        """PlacementStage initializes with default empty requires/provides."""
        ps = PlacementStage()
        assert ps.name == "placement_template"
        assert ps.requires == []
        assert ps.provides == []

    def test_placement_stage_custom_provides(self):
        """PlacementStage accepts custom requires/provides."""
        ps = PlacementStage(requires=["parsed_pcb"], provides=["placements"])
        assert ps.requires == ["parsed_pcb"]
        assert ps.provides == ["placements"]

    def test_placement_stage_run_raises_not_implemented(self):
        """PlacementStage.run raises NotImplementedError (JAX retired)."""
        ps = PlacementStage()
        inp = StageInput(data=None, meta=StageMeta())
        with pytest.raises(NotImplementedError, match="JAX-based placement"):
            ps.run(inp)


class TestRoutingStage:
    """Tests for RoutingStage adapter."""

    def test_routing_stage_defaults(self):
        """RoutingStage initializes with default empty requires/provides."""
        rs = RoutingStage()
        assert rs.name == "router_v6_full"
        assert rs.requires == []
        assert rs.provides == []

    def test_routing_stage_custom_provides(self):
        """RoutingStage accepts custom requires/provides."""
        rs = RoutingStage(requires=["parsed_pcb"], provides=["routing_results"])
        assert rs.requires == ["parsed_pcb"]
        assert rs.provides == ["routing_results"]
