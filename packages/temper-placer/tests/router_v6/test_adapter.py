"""Tests for Router V6 adapter module."""


import pytest

from temper_placer.router_v6.adapter import (
    RoutingResult,
    _apply_placements_to_pcb,
    _zone_layers_for_net,
    route_pcb,
)


class TestRoutingResult:
    def test_defaults(self):
        result = RoutingResult()
        assert result.completion_rate == 0.0

    def test_custom_completion(self):
        result = RoutingResult(completion_rate=0.75)
        assert result.completion_rate == 0.75


class TestApplyPlacementsToPcb:
    def test_replaces_footprint_position(self):
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:SOIC" (layer "F.Cu")
    (at 10.0 20.0 90.0)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  )
)"""
        placements = {"U1": (50.0, 60.0)}
        result = _apply_placements_to_pcb(content, placements)

        assert "at 50.0000 60.0000 90.0" in result
        assert "at 10.0 20.0" not in result

    def test_no_changes_when_ref_not_in_placements(self):
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:SOIC" (layer "F.Cu")
    (at 10.0 20.0)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
  )
)"""
        placements = {"U99": (50.0, 60.0)}
        result = _apply_placements_to_pcb(content, placements)

        assert "at 10.0 20.0" in result

    def test_multiple_components(self):
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:SOIC" (layer "F.Cu")
    (at 10.0 20.0)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
  )
  (footprint "Test:CAP" (layer "F.Cu")
    (at 5.0 8.0 180.0)
    (property "Reference" "C1" (at 0 0 0) (layer "F.SilkS"))
  )
)"""
        placements = {"U1": (50.0, 60.0), "C1": (70.0, 80.0)}
        result = _apply_placements_to_pcb(content, placements)

        assert "at 50.0000 60.0000" in result
        assert "at 70.0000 80.0000 180.0" in result
        assert "at 10.0 20.0" not in result
        assert "at 5.0 8.0" not in result

    def test_no_footprints_returns_unchanged(self):
        content = "(kicad_pcb (version 20240108)\n  (general\n    (thickness 1.6)\n  )\n)"
        placements = {"U1": (50.0, 60.0)}
        result = _apply_placements_to_pcb(content, placements)
        assert result == content

    def test_position_without_angle(self):
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:R" (layer "F.Cu")
    (at 1.0 2.0)
    (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS"))
  )
)"""
        placements = {"R1": (100.0, 200.0)}
        result = _apply_placements_to_pcb(content, placements)

        assert "at 100.0000 200.0000" in result


class TestRoutePcbErrorHandling:
    def test_no_source_path_raises_value_error(self):
        parsed = type("FakeParsed", (), {})()
        with pytest.raises(ValueError, match="source_path"):
            route_pcb(parsed, {}, 42)


class TestZoneLayersForNet:
    """TEMPER_NET_ASSIGNMENTS coverage against the production board's real
    net names (pcb/temper.kicad_pcb) -- see docs/evidence/2026-07-20-tree-executor-resilience-U5-measurement.json.
    """

    def test_dc_bus_plus_is_zone_eligible(self):
        assert _zone_layers_for_net("DC_BUS+") == ["F.Cu", "B.Cu"]

    def test_dc_bus_minus_is_zone_eligible(self):
        assert _zone_layers_for_net("DC_BUS-") == ["F.Cu", "B.Cu"]

    def test_cgnd_is_zone_eligible(self):
        assert _zone_layers_for_net("CGND") == ["F.Cu", "B.Cu"]

    def test_gate_l_short_form_is_zone_eligible(self):
        assert _zone_layers_for_net("GATE_L") == ["F.Cu", "B.Cu"]

    def test_gate_h_short_form_is_zone_eligible(self):
        assert _zone_layers_for_net("GATE_H") == ["F.Cu", "B.Cu"]

    def test_pwm_l_short_form_is_zone_eligible(self):
        assert _zone_layers_for_net("PWM_L") == ["F.Cu", "B.Cu"]

    def test_gate_ls_long_form_still_zone_eligible(self):
        """Existing long-form names must keep working -- additive fix only."""
        assert _zone_layers_for_net("GATE_LS") == ["F.Cu", "B.Cu"]

    def test_spi_mosi_is_not_zone_eligible(self):
        """SPI signal lines must never get a copper pour -- signal integrity,
        not a coverage gap. Confirms the fix doesn't overcorrect."""
        assert _zone_layers_for_net("SPI_MOSI") == []

    def test_spi_clk_is_not_zone_eligible(self):
        assert _zone_layers_for_net("SPI_CLK") == []

    def test_spi_miso_is_not_zone_eligible(self):
        assert _zone_layers_for_net("SPI_MISO") == []

    def test_unknown_net_is_not_zone_eligible(self):
        assert _zone_layers_for_net("some_random_signal") == []
