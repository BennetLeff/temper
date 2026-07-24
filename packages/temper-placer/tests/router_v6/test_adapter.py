"""Tests for Router V6 adapter module."""

import pytest

from temper_placer.router_v6.adapter import (
    RoutingResult,
    _apply_placements_to_pcb,
    _stitch_isolated_pads,
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


class TestRoutePcbLayerConstraintsResolution:
    """Regression coverage for a silent-no-op bug: route_pcb() resolves
    per-net layer constraints from ``getattr(parsed, "nets", [])`` -- a
    caller whose ``parsed`` object has no usable ``.nets`` gets an empty
    ``layer_constraints`` dict with no error, silently disabling netclass-SSOT
    layer assignment. This bit every production-board measurement test in
    this suite (they all built ``parsed_stub`` with only ``source_path``) --
    every net stayed on F.Cu regardless of its netclass's declared ``layer``.
    See docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md.
    """

    def _patched_pipeline(self):
        """Patch RouterV6Pipeline so route_pcb never does real routing;
        return the mock class so callers can inspect construction kwargs."""
        from types import SimpleNamespace
        from unittest import mock as umock

        mock_result_inner = SimpleNamespace(
            stage4=SimpleNamespace(
                routing_results=SimpleNamespace(
                    compiled_routes={},
                    tree_routes={},
                    partial_tree_routes={},
                    failed_nets=[],
                ),
            ),
            pcb=SimpleNamespace(components=[], nets=[]),
            enable_zone_pours=False,
            completion_rate=0.0,
        )
        patcher = umock.patch("temper_placer.router_v6.pipeline.RouterV6Pipeline")
        mock_pipe_cls = patcher.start()
        mock_pipe = umock.MagicMock()
        mock_pipe.run.return_value = mock_result_inner
        mock_pipe_cls.return_value = mock_pipe
        return patcher, mock_pipe_cls

    def _write_minimal_pcb(self):
        import tempfile

        with tempfile.NamedTemporaryFile(
            suffix=".kicad_pcb",
            mode="w",
            delete=False,
        ) as f:
            f.write('(kicad_pcb (version 20240108) (net 1 "vcc"))\n')
            return f.name

    def test_resolves_nonempty_layer_constraints_when_nets_present(self):
        """parsed.nets populated + design_rules given -> layer_constraints
        is actually resolved (not silently empty)."""
        import os
        from types import SimpleNamespace

        from temper_placer.core.design_rules import DesignRules

        patcher, mock_pipe_cls = self._patched_pipeline()
        temp_path = self._write_minimal_pcb()
        try:
            parsed = type(
                "ParsedPCB",
                (),
                {"source_path": temp_path, "nets": [SimpleNamespace(name="vcc")]},
            )()
            route_pcb(parsed, {}, _seed=1, design_rules=DesignRules())

            _, kwargs = mock_pipe_cls.call_args
            layer_constraints = kwargs.get("layer_constraints")
            assert layer_constraints, (
                "layer_constraints must not be empty when parsed.nets is "
                "populated and design_rules is provided"
            )
            assert "vcc" in layer_constraints
        finally:
            patcher.stop()
            os.unlink(temp_path)

    def test_layer_constraints_empty_and_warns_when_nets_missing(self, caplog):
        """parsed has no .nets at all + design_rules given -> layer_constraints
        stays empty (existing graceful fallback), but this must be LOUD
        (a warning), not silent -- this is the exact shape of the bug."""
        import logging
        import os

        from temper_placer.core.design_rules import DesignRules

        patcher, mock_pipe_cls = self._patched_pipeline()
        temp_path = self._write_minimal_pcb()
        try:
            parsed = type("ParsedPCB", (), {"source_path": temp_path})()  # no .nets
            with caplog.at_level(logging.WARNING):
                route_pcb(parsed, {}, _seed=1, design_rules=DesignRules())

            _, kwargs = mock_pipe_cls.call_args
            assert kwargs.get("layer_constraints") == {}
            assert any("no resolvable .nets" in rec.message for rec in caplog.records), (
                "missing .nets with design_rules provided must log a warning"
            )
        finally:
            patcher.stop()
            os.unlink(temp_path)

    def test_no_warning_when_design_rules_is_none(self, caplog):
        """Callers that don't pass design_rules at all (layer assignment
        genuinely not wanted) must NOT get the warning -- it's specific to
        the misconfiguration case, not a blanket nag on every missing-nets
        stub used by unrelated tests."""
        import logging
        import os

        patcher, mock_pipe_cls = self._patched_pipeline()
        temp_path = self._write_minimal_pcb()
        try:
            parsed = type("ParsedPCB", (), {"source_path": temp_path})()  # no .nets
            with caplog.at_level(logging.WARNING):
                route_pcb(parsed, {}, _seed=1, design_rules=None)

            assert not any("no resolvable .nets" in rec.message for rec in caplog.records)
        finally:
            patcher.stop()
            os.unlink(temp_path)


class TestCrossClassZoneClearance:
    """U2: cross-class pairwise clearance resolution for zone emission."""

    def _make_result_with_zones(self, net_names, component_pairs, compiled_nets=None):
        from types import SimpleNamespace

        from temper_placer.core.netlist import Component

        if compiled_nets is None:
            compiled_nets = list(net_names)[:1] or []

        compiled_routes = {}
        for net_name in compiled_nets:
            mock_path = SimpleNamespace(path_length=0.0, coordinates=[])
            compiled_routes[net_name] = SimpleNamespace(
                path=mock_path,
                width_mm=0.1,
                vias=[],
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
            ref = f"C{idx + 1}"
            x = float(idx * 10.0 + 10.0)
            y = float(idx * 10.0 + 10.0)
            comp = Component(
                ref=ref,
                footprint="0805",
                bounds=(2.0, 1.25),
                initial_position=(x, y),
            )
            components.append(comp)
            pairs = component_pairs.get(net_name, [(ref, "1")])
            nets.append(SimpleNamespace(name=net_name, pins=pairs))

        pcb = SimpleNamespace(components=components, nets=nets)
        return SimpleNamespace(stage4=stage4, pcb=pcb, enable_zone_pours=True)

    def _build_dr(self, class_pairs=None):
        from temper_placer.core.design_rules import DesignRules

        dr = DesignRules()
        if class_pairs is not None:
            dr.class_pairs = class_pairs
        return dr

    def test_power_and_hv_resolve_to_stricter_cross_class(self):
        """vcc (Power, 0.25mm) + +340V_BUS (HV, 6.0mm) -> effective 6.0mm."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["vcc", "+340V_BUS"],
            {"vcc": [("C1", "1")], "+340V_BUS": [("C2", "1")]},
        )
        dr = self._build_dr({("HighVoltage", "Power"): {"clearance": 6.0}})
        content = '(kicad_pcb (version 20240108) (net 1 "vcc") (net 2 "+340V_BUS"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 6.0000)" in output

    def test_same_class_nets_keep_own_clearance(self):
        """Two GND-class nets resolve to GND's own 0.3mm (never weaken)."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["PWR_RTN", "CGND"],
            {"PWR_RTN": [("C1", "1")], "CGND": [("C2", "1")]},
        )
        dr = self._build_dr()
        content = '(kicad_pcb (version 20240108) (net 1 "PWR_RTN") (net 2 "CGND"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 0.3000)" in output

    def test_fallback_to_max_clearance_no_class_pair(self):
        """No class_pairs entry -> fallback to max(own, other)."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["vcc", "+15V"],
            {"vcc": [("C1", "1")], "+15V": [("C2", "1")]},
        )
        dr = self._build_dr()
        content = '(kicad_pcb (version 20240108) (net 1 "vcc") (net 2 "+15V"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 0.2500)" in output

    def test_single_netclass_no_cross_class(self):
        """Only one zone-eligible netclass: clearance equals own."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["vcc"],
            {"vcc": [("C1", "1")]},
        )
        dr = self._build_dr()
        content = '(kicad_pcb (version 20240108) (net 1 "vcc"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 0.2500)" in output

    def test_route_pcb_e2e_threads_design_rules_to_zone_pours_and_pipeline(self):
        """End-to-end: route_pcb + enable_zone_pours reflects cross-class
        clearance in zone-pour output AND forwards design_rules to the pipeline.

        Verifies both downstream consumers of the design_rules parameter:
        1. The writer's zone-pour clearance resolution (zone geometry).
        2. The pipeline's layer-constraint resolution (constructor kwargs).
        """
        import os
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest import mock as umock

        from temper_placer.core.design_rules import DesignRules
        from temper_placer.core.netlist import Component

        dr = DesignRules()
        dr.class_pairs = {("HighVoltage", "Power"): {"clearance": 6.0}}

        components = [
            Component(
                ref="C1", footprint="0805", bounds=(2.0, 1.25), initial_position=(10.0, 10.0)
            ),
            Component(
                ref="C2", footprint="0805", bounds=(2.0, 1.25), initial_position=(30.0, 30.0)
            ),
        ]
        nets = [
            SimpleNamespace(name="vcc", pins=[("C1", "1")]),
            SimpleNamespace(name="+340V_BUS", pins=[("C2", "1")]),
        ]
        pcb_mock = SimpleNamespace(components=components, nets=nets)

        mock_path = SimpleNamespace(path_length=1.0, segments=[(0, 0, "F.Cu"), (10, 0, "F.Cu")])
        compiled_routes = {
            "vcc": SimpleNamespace(path=mock_path, width_mm=0.5, vias=[]),
            "+340V_BUS": SimpleNamespace(path=mock_path, width_mm=0.5, vias=[]),
        }
        rr = SimpleNamespace(
            compiled_routes=compiled_routes,
            tree_routes={},
            partial_tree_routes={},
            failed_nets=[],
        )
        stage4 = SimpleNamespace(routing_results=rr)
        mock_result_inner = SimpleNamespace(
            stage4=stage4,
            pcb=pcb_mock,
            enable_zone_pours=True,
            completion_rate=0.5,
        )

        patcher = umock.patch("temper_placer.router_v6.pipeline.RouterV6Pipeline")
        mock_pipe_cls = patcher.start()
        mock_pipe = umock.MagicMock()
        mock_pipe.run.return_value = mock_result_inner
        mock_pipe_cls.return_value = mock_pipe

        try:
            with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as f:
                f.write('(kicad_pcb (version 20240108) (net 1 "vcc") (net 2 "+340V_BUS"))\n')
                temp_path = f.name

            parsed = type("ParsedPCB", (), {"source_path": temp_path, "nets": nets})()
            result = route_pcb(
                parsed,
                {},
                _seed=42,
                design_rules=dr,
                enable_zone_pours=True,
            )

            # Zone-pour output: cross-class clearance emitted in PCB content.
            assert result.routed_pcb_content is not None
            assert "(zone " in result.routed_pcb_content
            assert "(clearance 6.0000)" in result.routed_pcb_content

            # Pipeline wiring: constructor receives layer_constraints from
            # the design_rules SSOT and enable_zone_pours flag.
            mock_pipe_cls.assert_called_once()
            _, ctor_kwargs = mock_pipe_cls.call_args
            assert ctor_kwargs.get("enable_zone_pours") is True, (
                "enable_zone_pours must be forwarded to the pipeline constructor"
            )
            layer_constraints = ctor_kwargs.get("layer_constraints")
            assert layer_constraints, (
                "layer_constraints must not be empty when parsed.nets is "
                "populated and design_rules is provided"
            )
            assert "vcc" in layer_constraints
            assert "+340V_BUS" in layer_constraints

            # Pipeline invocation: run() receives the PCB path.
            mock_pipe.run.assert_called_once()
            run_args, _run_kwargs = mock_pipe.run.call_args
            assert len(run_args) == 1
            assert isinstance(run_args[0], Path)
        finally:
            patcher.stop()
            os.unlink(temp_path)


class TestPriorityInversion:
    """U2: verify dru_priority → KiCad (priority N) inversion in emitted s-expr."""

    def _make_result(self, net_names, component_pairs):
        from types import SimpleNamespace

        from temper_placer.core.netlist import Component

        compiled_routes = {}
        mock_path = SimpleNamespace(path_length=0.0, coordinates=[])
        for net_name in net_names[:1]:
            compiled_routes[net_name] = SimpleNamespace(
                path=mock_path,
                width_mm=0.1,
                vias=[],
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
            x = float(idx * 10.0 + 10.0)
            y = float(idx * 10.0 + 10.0)
            comp = Component(
                ref=f"C{idx + 1}",
                footprint="0805",
                bounds=(2.0, 1.25),
                initial_position=(x, y),
            )
            components.append(comp)
            nets.append(
                SimpleNamespace(
                    name=net_name,
                    pins=[(f"C{idx + 1}", "1")],
                )
            )

        pcb = SimpleNamespace(components=components, nets=nets)
        return SimpleNamespace(stage4=stage4, pcb=pcb, enable_zone_pours=True)

    def test_acmains_priority_higher_than_power_in_emitted_zones(self):
        """ACMains (dru=10→KiCad 80) > Power (dru=40→KiCad 50) in s-expr."""
        import re

        from temper_placer.core.design_rules import DesignRules
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result(
            ["AC_L", "vcc"],
            {"AC_L": [("C1", "1")], "vcc": [("C2", "1")]},
        )
        dr = DesignRules()
        content = '(kicad_pcb (version 20240108) (net 1 "AC_L") (net 2 "vcc"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)

        # Each net gets 2 zones (F.Cu + B.Cu); extract priority per net
        priorities_by_net: dict[str, set[int]] = {}
        for m in re.finditer(
            r'\(net_name "([^"]+)"\).*?\(priority (\d+)\)',
            output,
            re.DOTALL,
        ):
            priorities_by_net.setdefault(m.group(1), set()).add(int(m.group(2)))

        assert "AC_L" in priorities_by_net
        assert "vcc" in priorities_by_net
        ac_max = max(priorities_by_net["AC_L"])
        pwr_max = max(priorities_by_net["vcc"])
        assert ac_max > pwr_max, f"ACMains ({ac_max}) should be > Power ({pwr_max})"
        assert ac_max == 80
        assert pwr_max == 50


class TestStitchIsolatedPads:
    """U3: trace-stitch pads outside pour polygons."""

    def test_pad_inside_zone_is_not_stitched(self):
        segments: list[str] = []
        pad_positions = {"vcc": [(5.0, 5.0)]}
        net_map = {"vcc": 1}
        zone_points = {"vcc": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
        _stitch_isolated_pads(pad_positions, segments, net_map, zone_points)
        assert len(segments) == 0

    def test_pad_outside_zone_gets_stitch_trace(self):
        segments: list[str] = []
        pad_positions = {"vcc": [(5.0, 5.0), (50.0, 50.0)]}
        net_map = {"vcc": 1}
        zone_points = {"vcc": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
        _stitch_isolated_pads(pad_positions, segments, net_map, zone_points)
        assert len(segments) == 1
        assert "(segment " in segments[0]
        assert "(start 50.0000 50.0000)" in segments[0]

    def test_non_zone_eligible_net_skipped(self):
        segments: list[str] = []
        _stitch_isolated_pads(
            {"SPI_MOSI": [(50.0, 50.0)]},
            segments,
            {"SPI_MOSI": 1},
            {},
        )
        assert len(segments) == 0

    def test_empty_zone_points_skipped(self):
        segments: list[str] = []
        _stitch_isolated_pads({"vcc": [(50.0, 50.0)]}, segments, {"vcc": 1}, {})
        assert len(segments) == 0

    def test_single_pad_inside_is_noop(self):
        segments: list[str] = []
        zone_points = {"vcc": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
        _stitch_isolated_pads({"vcc": [(5.0, 5.0)]}, segments, {"vcc": 1}, zone_points)
        assert len(segments) == 0  # pad inside, no stitch


# ---------------------------------------------------------------------------
# _chamfer_path_points tests
# ---------------------------------------------------------------------------


class TestChamferPathPoints:
    """Tests for _chamfer_path_points, the grid-staircasing DRC fix."""

    def test_orthogonal_turn_is_chamfered(self):
        """A 90-degree orthogonal turn gets chamfered with a diagonal."""
        from temper_placer.router_v6._adapter_convert import _chamfer_path_points

        points = [
            (0.0, 0.0, "F.Cu"),
            (0.0, 10.0, "F.Cu"),
            (10.0, 10.0, "F.Cu"),
        ]
        result = _chamfer_path_points(points, chamfer_offset=0.1)

        assert result[0] == (0.0, 0.0, "F.Cu")
        assert result[-1] == (10.0, 10.0, "F.Cu")
        assert len(result) == 4
        assert result[1] == (0.0, 9.9, "F.Cu")
        assert result[2] == (0.1, 10.0, "F.Cu")

    def test_straight_line_unchanged(self):
        """Collinear same-direction points pass through unchanged."""
        from temper_placer.router_v6._adapter_convert import _chamfer_path_points

        points = [
            (0.0, 0.0, "F.Cu"),
            (5.0, 0.0, "F.Cu"),
            (10.0, 0.0, "F.Cu"),
        ]
        result = _chamfer_path_points(points, chamfer_offset=0.1)
        assert result == points

    def test_layer_change_preserved(self):
        """Turn point at a layer boundary (via) is never chamfered."""
        from temper_placer.router_v6._adapter_convert import _chamfer_path_points

        points = [
            (0.0, 0.0, "F.Cu"),
            (0.0, 10.0, "F.Cu"),
            (0.0, 10.0, "B.Cu"),
        ]
        result = _chamfer_path_points(points, chamfer_offset=0.1)
        assert result == points

    def test_segment_too_short_skipped(self):
        """Turn where one segment is shorter than 2*offset skips chamfer."""
        from temper_placer.router_v6._adapter_convert import _chamfer_path_points

        points = [
            (0.0, 0.0, "F.Cu"),
            (0.0, 0.15, "F.Cu"),
            (10.0, 0.15, "F.Cu"),
        ]
        result = _chamfer_path_points(points, chamfer_offset=0.1)
        assert result == points

    def test_empty_and_two_point_paths(self):
        """Edge cases: zero, one, and two point paths are identity."""
        from temper_placer.router_v6._adapter_convert import _chamfer_path_points

        assert _chamfer_path_points([], chamfer_offset=0.1) == []
        single = [(1.0, 2.0, "F.Cu")]
        assert _chamfer_path_points(single, chamfer_offset=0.1) == single
        pair = [(0.0, 0.0, "F.Cu"), (10.0, 0.0, "F.Cu")]
        assert _chamfer_path_points(pair, chamfer_offset=0.1) == pair

    def test_multiple_consecutive_turns(self):
        """A zigzag path gets all orthogonal turns chamfered."""
        from temper_placer.router_v6._adapter_convert import _chamfer_path_points

        points = [
            (0.0, 0.0, "F.Cu"),
            (10.0, 0.0, "F.Cu"),
            (10.0, 10.0, "F.Cu"),
            (20.0, 10.0, "F.Cu"),
            (20.0, 20.0, "F.Cu"),
        ]
        result = _chamfer_path_points(points, chamfer_offset=0.1)
        assert result[0] == (0.0, 0.0, "F.Cu")
        assert result[-1] == (20.0, 20.0, "F.Cu")
        assert len(result) == 8

    def test_second_turn_after_chamfered_first(self):
        """After chamfering first turn, second turn still gets chamfered."""
        from temper_placer.router_v6._adapter_convert import _chamfer_path_points

        points = [
            (0.0, 0.0, "F.Cu"),
            (0.0, 10.0, "F.Cu"),
            (10.0, 10.0, "F.Cu"),
            (10.0, 20.0, "F.Cu"),
        ]
        result = _chamfer_path_points(points, chamfer_offset=0.1)
        assert len(result) == 6
        assert result[1] == (0.0, 9.9, "F.Cu")
        assert result[2] == (0.1, 10.0, "F.Cu")
        assert result[3] == (9.9, 10.0, "F.Cu")
        assert result[4] == (10.0, 10.1, "F.Cu")
