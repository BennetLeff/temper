"""Tests for Router V6 adapter module."""


import pytest

from temper_placer.router_v6.adapter import (
    RoutingResult,
    _apply_placements_to_pcb,
    _zone_layers_for_net,
    _zone_params_for_net,
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


class TestZoneParamsForNet:
    """Zone margin should be bounded by clearance (the project's own
    authoritative safety constant for these classes, see
    SAFETY_CONSTANT_AUTHORITY_NET_CLASSES in design_rules.py), not an
    arbitrary multiple of trace width. Previously: margin = trace_width * 10.0
    produced a 25-30mm zone-boundary expansion for ACMains/HighVoltage on a
    ~100-150mm board with no principled bound.

    NOTE: investigation on 2026-07-21 found this does NOT explain the
    shorting_items increase measured on the production board once zones were
    actually filled (PR #263) -- 0 of 85 shorting violations involved a zone.
    This coverage is kept because the bound is correct on its own merits, not
    because it fixes that regression. The actual root cause found that day
    was PYTHONHASHSEED-dependent net ordering in astar_pathfinding.py's
    _compute_net_order (see test_net_order_is_deterministic_across_hash_seeds
    in test_net_ordering.py).
    """

    def test_acmains_margin_is_not_oversized(self):
        # Previously 2.5mm trace_width * 10 = 25mm -- would sweep a huge
        # fraction of a 100-150mm board. Must be bounded by clearance (6.0mm).
        margin, clearance = _zone_params_for_net("AC_L")
        assert margin <= clearance
        assert margin < 10.0

    def test_highvoltage_margin_is_not_oversized(self):
        # Previously 3.0mm trace_width * 10 = 30mm.
        margin, clearance = _zone_params_for_net("DC_BUS+")
        assert margin <= clearance
        assert margin < 10.0

    def test_gnd_margin_matches_clearance(self):
        margin, clearance = _zone_params_for_net("CGND")
        assert margin == clearance

    def test_unknown_net_gets_conservative_default(self):
        margin, clearance = _zone_params_for_net("some_random_signal")
        assert margin <= clearance


class TestCrossClassZoneClearance:
    """U1: cross-class pairwise clearance resolution for zone emission."""

    def _make_result_with_zones(self, net_names, component_pairs, net_name_to_number_map=None,
                                 compiled_nets=None):
        """Build a mock pipeline result that triggers zone emission."""
        from types import SimpleNamespace

        from temper_placer.core.netlist import Component

        if compiled_nets is None:
            compiled_nets = list(net_names)[:1] or []

        compiled_routes = {}
        for net_name in compiled_nets:
            mock_path = SimpleNamespace(path_length=0.0, coordinates=[])
            compiled_routes[net_name] = SimpleNamespace(
                path=mock_path, width_mm=0.1, vias=[],
            )

        routing_results = SimpleNamespace(
            compiled_routes=compiled_routes,
            tree_routes={},
            partial_tree_routes={},
        )
        stage4 = SimpleNamespace(routing_results=routing_results)

        components = []
        nets = []
        for idx, net_name in enumerate(net_names):
            ref = f"C{idx+1}"
            x = float(idx * 10.0 + 10.0)
            y = float(idx * 10.0 + 10.0)
            comp = Component(
                ref=ref, footprint="0805", bounds=(2.0, 1.25),
                initial_position=(x, y),
            )
            components.append(comp)
            pairs_for_net = component_pairs.get(net_name, [(ref, "1")])
            # Use SimpleNamespace for Net to avoid strict dataclass constraints
            nets.append(SimpleNamespace(name=net_name, pins=pairs_for_net))

        pcb = SimpleNamespace(components=components, nets=nets)

        result = SimpleNamespace(
            stage4=stage4,
            pcb=pcb,
            enable_zone_pours=True,
        )
        return result

    def _build_design_rules_with_class_pairs(self, class_pairs=None):
        from temper_placer.core.design_rules import DesignRules
        dr = DesignRules()
        if class_pairs is not None:
            dr.class_pairs = class_pairs
        return dr

    def test_power_and_highvoltage_resolve_to_stricter_cross_class(self):
        """vcc (Power, 0.25mm) + +340V_BUS (HighVoltage, 6.0mm) -> effective 6.0mm."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        net_names = ["vcc", "+340V_BUS"]
        result = self._make_result_with_zones(
            net_names=net_names,
            component_pairs={"vcc": [("C1", "1")], "+340V_BUS": [("C2", "1")]},
        )
        dr = self._build_design_rules_with_class_pairs(
            {("HighVoltage", "Power"): {"clearance": 6.0, "because": ""}},
        )

        content = '(kicad_pcb (version 20240108) (net 1 "vcc") (net 2 "+340V_BUS"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)

        assert '(clearance 6.0000)' in output

    def test_same_class_nets_keep_own_clearance(self):
        """Two GND-class nets resolve to GND's own 0.3mm, unchanged (R4)."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        net_names = ["PWR_RTN", "CGND"]
        result = self._make_result_with_zones(
            net_names=net_names,
            component_pairs={"PWR_RTN": [("C1", "1")], "CGND": [("C2", "1")]},
        )
        dr = self._build_design_rules_with_class_pairs()

        content = '(kicad_pcb (version 20240108) (net 1 "PWR_RTN") (net 2 "CGND"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)

        assert '(clearance 0.3000)' in output

    def test_fallback_to_max_clearance_when_no_class_pair(self):
        """No class_pairs entry -> fallback to max(own, other) clearance."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        net_names = ["vcc", "+15V"]
        result = self._make_result_with_zones(
            net_names=net_names,
            component_pairs={"vcc": [("C1", "1")], "+15V": [("C2", "1")]},
        )
        # Both are Power-class (0.25mm clearance). No class_pairs entry.
        dr = self._build_design_rules_with_class_pairs()

        content = '(kicad_pcb (version 20240108) (net 1 "vcc") (net 2 "+15V"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)

        assert '(clearance 0.2500)' in output

    def test_single_netclass_no_cross_class(self):
        """Only one zone-eligible netclass present: clearance equals own."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        net_names = ["vcc"]
        result = self._make_result_with_zones(
            net_names=net_names,
            component_pairs={"vcc": [("C1", "1")]},
        )
        dr = self._build_design_rules_with_class_pairs()

        content = '(kicad_pcb (version 20240108) (net 1 "vcc"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)

        assert '(clearance 0.2500)' in output

    def test_route_pcb_e2e_threads_design_rules_to_zones(self):
        """End-to-end: route_pcb() with design_rules + enable_zone_pours
        produces zones whose clearance reflects cross-class resolution."""
        from types import SimpleNamespace
        from unittest import mock as umock

        from temper_placer.core.design_rules import DesignRules
        from temper_placer.core.netlist import Component
        from temper_placer.router_v6.adapter import route_pcb

        dr = DesignRules()
        dr.class_pairs = {
            ("HighVoltage", "Power"): {"clearance": 6.0, "because": ""},
        }

        components = [
            Component(ref="C1", footprint="0805", bounds=(2.0, 1.25), initial_position=(10.0, 10.0)),
            Component(ref="C2", footprint="0805", bounds=(2.0, 1.25), initial_position=(30.0, 30.0)),
        ]
        nets = [
            SimpleNamespace(name="vcc", pins=[("C1", "1")]),
            SimpleNamespace(name="+340V_BUS", pins=[("C2", "1")]),
        ]
        pcb_mock = SimpleNamespace(components=components, nets=nets)

        # Build a mock result with simple compiled routes
        mock_path = SimpleNamespace(path_length=1.0, segments=[(0, 0, "F.Cu"), (10, 0, "F.Cu")])
        compiled_routes = {
            "vcc": SimpleNamespace(path=mock_path, width_mm=0.5, vias=[]),
            "+340V_BUS": SimpleNamespace(path=mock_path, width_mm=0.5, vias=[]),
        }
        routing_results = SimpleNamespace(
            compiled_routes=compiled_routes, tree_routes={}, partial_tree_routes={},
            failed_nets=[],
        )
        stage4 = SimpleNamespace(routing_results=routing_results)
        mock_result_inner = SimpleNamespace(
            stage4=stage4, pcb=pcb_mock, enable_zone_pours=True, completion_rate=0.5,
        )
        # route_pcb patches `result.enable_zone_pours = enable_zone_pours` after run()
        mock_result_inner.enable_zone_pours = True

        with umock.patch(
            "temper_placer.router_v6.pipeline.RouterV6Pipeline"
        ) as mock_pipe_cls:
            mock_pipe = umock.MagicMock()
            mock_pipe.run.return_value = mock_result_inner
            mock_pipe_cls.return_value = mock_pipe

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as f:
                f.write(
                    '(kicad_pcb (version 20240108)'
                    ' (net 1 "vcc") (net 2 "+340V_BUS"))\n'
                )
                temp_path = f.name

            try:
                parsed = type("ParsedPCB", (), {"source_path": temp_path, "nets": nets})()

                result = route_pcb(
                    parsed,
                    placements={},
                    _seed=42,
                    design_rules=dr,
                    enable_zone_pours=True,
                )

                assert result.routed_pcb_content is not None
                # Power-class net (vcc) should use the stricter 6.0mm from class_pairs
                assert "(zone " in result.routed_pcb_content
                assert "(clearance 6.0000)" in result.routed_pcb_content
            finally:
                import os
                os.unlink(temp_path)
