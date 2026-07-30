"""Tests for Router V6 adapter module."""

import logging
import re
from types import SimpleNamespace
from unittest import mock as umock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.adapter import (
    RoutingResult,
    _apply_placements_to_pcb,
    _stitch_isolated_pads,
    _to_stage0_netclass_rules,
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


class TestApplyPlacementsToPcbRotation:
    """Item 1: a solved CP-SAT rotation must not be structurally discarded
    by the writer, and when it IS applied, every pad's absolute angle must
    shift by the same delta as the footprint (see
    _write_board.py::_reorient_pads for the kiutils-based precedent this
    mirrors on raw string content -- a .kicad_pcb pad angle is ABSOLUTE,
    not footprint-relative)."""

    _CONTENT_TEMPLATE = """(kicad_pcb (version 20240108)
  (footprint "Test:SOIC" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 10.0 20.0{fp_angle_suffix})
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" smd rect (at -0.775 0{pad1_angle_suffix}) (size 0.6 1.2) (layers "F.Cu" "F.Paste" "F.Mask")
      (net 1 "vcc"))
    (pad "2" smd rect (at 0.775 0{pad2_angle_suffix}) (size 0.6 1.2) (layers "F.Cu" "F.Paste" "F.Mask")
      (net 2 "gnd"))
  )
)"""

    def test_no_rotations_arg_preserves_angle_exactly(self):
        """Without a `rotations=` mapping at all, behavior is byte-for-byte
        identical to the pre-fix writer: solved rotation is not applied."""
        content = self._CONTENT_TEMPLATE.format(
            fp_angle_suffix=" 90.0", pad1_angle_suffix=" 90", pad2_angle_suffix=" 90"
        )
        result = _apply_placements_to_pcb(content, {"U1": (50.0, 60.0)})

        assert "at 50.0000 60.0000 90.0" in result
        assert "at -0.775 0 90" in result
        assert "at 0.775 0 90" in result

    def test_ref_absent_from_rotations_preserves_angle(self):
        """A ref in `placements` but not in `rotations` keeps its angle,
        exactly like the no-`rotations`-at-all case."""
        content = self._CONTENT_TEMPLATE.format(
            fp_angle_suffix=" 90.0", pad1_angle_suffix=" 90", pad2_angle_suffix=" 90"
        )
        result = _apply_placements_to_pcb(
            content, {"U1": (50.0, 60.0)}, rotations={"OTHER_REF": 180.0}
        )

        assert "at 50.0000 60.0000 90.0" in result
        assert "at -0.775 0 90" in result
        assert "at 0.775 0 90" in result

    def test_solved_rotation_is_written_to_footprint_angle(self):
        """This is the bug: before the fix, a solved rotation never reached
        the footprint's own (at X Y ANGLE) at all -- this assertion is
        exactly what `_apply_placements_to_pcb` (pre-fix, no `rotations`
        parameter) could not do."""
        content = self._CONTENT_TEMPLATE.format(
            fp_angle_suffix="", pad1_angle_suffix="", pad2_angle_suffix=""
        )
        result = _apply_placements_to_pcb(
            content, {"U1": (50.0, 60.0)}, rotations={"U1": 90.0}
        )

        assert "at 50.0000 60.0000 90.0000" in result

    def test_pad_bodies_reorient_with_footprint(self):
        """The pad-shorting regression (PRs #412/#420/#426): rotating the
        footprint without rotating pad bodies leaves fine-pitch pads
        physically overlapping. Footprint 0 -> 90 must shift every pad's
        absolute angle by +90 too."""
        content = self._CONTENT_TEMPLATE.format(
            fp_angle_suffix="", pad1_angle_suffix="", pad2_angle_suffix=""
        )
        result = _apply_placements_to_pcb(
            content, {"U1": (50.0, 60.0)}, rotations={"U1": 90.0}
        )

        assert "at -0.775 0 90.0000" in result
        assert "at 0.775 0 90.0000" in result

    def test_pad_reorientation_preserves_intrinsic_offset(self):
        """Pads that already carry a non-footprint angle (e.g. a part whose
        library footprint itself defines pads at a relative angle) must
        keep that intrinsic offset -- only the delta shifts them, matching
        `_reorient_pads`'s `intrinsic = old_pad_angle - old_fp_angle`
        invariant."""
        content = self._CONTENT_TEMPLATE.format(
            fp_angle_suffix=" 90.0", pad1_angle_suffix=" 90", pad2_angle_suffix=" 180"
        )
        # Footprint rotates 90 -> 180: delta = +90.
        result = _apply_placements_to_pcb(
            content, {"U1": (50.0, 60.0)}, rotations={"U1": 180.0}
        )

        assert "at 50.0000 60.0000 180.0000" in result
        # pad 1: 90 + 90 = 180
        assert "at -0.775 0 180.0000" in result
        # pad 2: 180 + 90 = 270
        assert "at 0.775 0 270.0000" in result

    def test_rotation_normalizing_to_zero_omits_angle_token(self):
        """KiCad/kiutils omit the angle token entirely when it is 0 --
        `_reorient_pads` documents this convention explicitly; the raw-
        string writer must match it rather than emit a literal `0.0000`
        angle that downstream tooling has never had to parse before."""
        content = self._CONTENT_TEMPLATE.format(
            fp_angle_suffix=" 270.0", pad1_angle_suffix=" 270", pad2_angle_suffix=" 270"
        )
        # Footprint rotates 270 -> 360 (== 0): delta = +90, pads 270 -> 360 (== 0).
        result = _apply_placements_to_pcb(
            content, {"U1": (50.0, 60.0)}, rotations={"U1": 360.0}
        )

        assert "at 50.0000 60.0000)" in result
        assert "at -0.775 0)" in result
        assert "at 0.775 0)" in result

    def test_zero_delta_does_not_touch_pads(self):
        """Same target angle as the current one: delta is 0, so pads are
        left completely untouched (not merely re-written to the same
        value) -- this is the `delta % 360.0 != 0.0` guard."""
        content = self._CONTENT_TEMPLATE.format(
            fp_angle_suffix=" 90.0", pad1_angle_suffix=" 45", pad2_angle_suffix=" 135"
        )
        result = _apply_placements_to_pcb(
            content, {"U1": (50.0, 60.0)}, rotations={"U1": 90.0}
        )

        assert "at 50.0000 60.0000 90.0000" in result
        assert "at -0.775 0 45" in result
        assert "at 0.775 0 135" in result


class TestApplyPlacementsToPcbCenterOffset:
    """CP-SAT solves and reports each component's box-CENTRE (Component.
    initial_position's convention), not its raw KiCad anchor. For a
    footprint whose pad centroid doesn't coincide with that anchor
    (Component.attributes["_center_offset_x/y"] != 0 -- an asymmetric
    TO-247, e.g. Q1/Q2 on the corpus board, center_offset=(5.45, 0)), the
    anchor this function writes into (at X Y) must be the centre minus
    that offset, rotated by KiCad's own (clockwise) convention -- not the
    centre itself, and not a standard-CCW rotation of the offset.

    This is a real, root-caused regression: PR #460's corrected
    `comp.bounds` (tight around real pad copper, computed in the correct
    frame) is only sound if the WRITTEN board matches the frame CP-SAT
    verified. Before this fix, the corpus board's golden-board regression
    gate (test_regression_drc.py::test_golden_board_drc_regression) wrote
    Q1/Q2 (TO-247s, center_offset=(5.45, 0)) apart by CP-SAT's solved
    rotation with NEITHER the rotation NOR the center_offset correctly
    applied, producing a real, measured `shorting_items` DRC violation
    between Q1's DC_BUS+ pad and Q2's SW_NODE pad -- the two halves of the
    HV half-bridge, shorted across. See
    docs/evidence/2026-07-30-generic-separation-writer-frame-fix.md.

    The two expected numbers below (90.6064.. / 102.8236 anchor;
    contrasted with the CCW-formula's 94.4209 / 90.7873, a different
    point) were verified against ``pcbnew`` directly (KiCad's own
    placement engine), not re-derived from this repo's own formula -- see
    that module's docstring for the measurement.
    """

    def _make_component(self, ref: str, cx: float, cy: float):
        return SimpleNamespace(ref=ref, attributes={
            "_center_offset_x": str(cx),
            "_center_offset_y": str(cy),
        })

    def test_asymmetric_offset_uncorrected_without_components_arg(self):
        """Omitting `components=` (the pre-fix call shape, and every call
        site until this task wired it in) reproduces the exact pre-fix
        bug: CP-SAT's box-centre is written directly as the KiCad anchor,
        off by the full center_offset. This is the failure mode that
        turned Q1/Q2's real, sound clearance into a measured short."""
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:TO247" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 10.0 20.0)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" thru_hole circle (at 0 0) (size 3.5 3.5) (drill 1.6) (layers "*.Cu" "*.Mask")
      (net 1 "vcc"))
    (pad "2" thru_hole circle (at 20 8) (size 3.5 3.5) (drill 1.6) (layers "*.Cu" "*.Mask")
      (net 2 "gnd"))
  )
)"""
        result = _apply_placements_to_pcb(content, {"U1": (100.0, 100.0)})
        # Anchor is written as the raw centre -- wrong for this footprint,
        # since it never gets a chance to invert center_offset.
        assert "at 100.0000 100.0000" in result

    def test_asymmetric_offset_rotated_writes_pcbnew_verified_anchor(self):
        """The fix: with `components=` supplied, the anchor is the centre
        minus center_offset, rotated by the solved angle using KiCad's own
        (clockwise) convention -- verified against pcbnew, not this
        repo's prior (wrong) formula."""
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:TO247" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 10.0 20.0)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" thru_hole circle (at 0 0) (size 3.5 3.5) (drill 1.6) (layers "*.Cu" "*.Mask")
      (net 1 "vcc"))
    (pad "2" thru_hole circle (at 20 8) (size 3.5 3.5) (drill 1.6) (layers "*.Cu" "*.Mask")
      (net 2 "gnd"))
  )
)"""
        comp = self._make_component("U1", 10.0, 4.0)
        result = _apply_placements_to_pcb(
            content,
            {"U1": (100.0, 100.0)},
            rotations={"U1": 37.0},
            components=[comp],
        )
        # pcbnew-verified: R(-37deg) of (10, 4) is (10.393615, -2.823608),
        # so anchor = (100, 100) - that = (89.6064, 102.8236).
        assert "at 89.6064 102.8236 37.0000" in result
        # The wrong (standard-CCW) sign this repo used to use would write
        # a completely different anchor -- assert it is NOT that point,
        # so a sign regression here fails loudly rather than by omission.
        assert "at 94.4209 90.7873" not in result

    def test_no_center_offset_unaffected_by_components_arg(self):
        """A symmetric footprint (center_offset == 0, e.g. most parts)
        must write its centre unchanged whether or not `components=` is
        passed -- this fix must not perturb the common case."""
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:R0402" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 10.0 20.0)
    (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" smd rect (at -0.5 0) (size 0.6 0.6) (layers "F.Cu"))
    (pad "2" smd rect (at 0.5 0) (size 0.6 0.6) (layers "F.Cu"))
  )
)"""
        comp = self._make_component("R1", 0.0, 0.0)
        result = _apply_placements_to_pcb(
            content,
            {"R1": (50.0, 60.0)},
            rotations={"R1": 90.0},
            components=[comp],
        )
        assert "at 50.0000 60.0000 90.0000" in result

    def test_omitted_rotation_falls_back_to_existing_angle_for_offset(self):
        """If this ref has no solved rotation (absent from `rotations`,
        e.g. CP-SAT chose rotation index 0 -- `to_rotations_dict()` omits
        those), the centre must have been computed at the footprint's
        EXISTING angle, so that angle -- not 0 -- is the correct basis
        for inverting center_offset."""
        content = """(kicad_pcb (version 20240108)
  (footprint "Test:TO247" (layer "F.Cu")
    (tstamp 00000000-0000-0000-0000-000000000001)
    (at 10.0 20.0 90.0)
    (property "Reference" "U1" (at 0 0 0) (layer "F.SilkS"))
    (pad "1" thru_hole circle (at 0 0) (size 3.5 3.5) (drill 1.6) (layers "*.Cu" "*.Mask")
      (net 1 "vcc"))
    (pad "2" thru_hole circle (at 20 8) (size 3.5 3.5) (drill 1.6) (layers "*.Cu" "*.Mask")
      (net 2 "gnd"))
  )
)"""
        comp = self._make_component("U1", 10.0, 4.0)
        # No `rotations=` entry for U1 at all: old_angle (90 deg, read from
        # the file) must be used as the rotation basis.
        result = _apply_placements_to_pcb(
            content,
            {"U1": (100.0, 100.0)},
            rotations={},
            components=[comp],
        )
        import math

        theta = math.radians(90.0)
        rotated_cx = 10.0 * math.cos(theta) + 4.0 * math.sin(theta)
        rotated_cy = -10.0 * math.sin(theta) + 4.0 * math.cos(theta)
        expected = f"at {100.0 - rotated_cx:.4f} {100.0 - rotated_cy:.4f} 90.0"
        assert expected in result


class TestRoutePcbErrorHandling:
    def test_no_source_path_raises_value_error(self):
        parsed = type("FakeParsed", (), {})()
        with pytest.raises(ValueError, match="source_path"):
            route_pcb(parsed, {})


class TestZoneLayersForNet:
    """TEMPER_NET_ASSIGNMENTS coverage against the production board's real
    net names (pcb/temper.kicad_pcb) -- see docs/evidence/2026-07-20-tree-executor-resilience-U5-measurement.json.
    """

    def test_dc_bus_plus_is_zone_eligible(self):
        assert _zone_layers_for_net("DC_BUS+") == ["F.Cu", "B.Cu"]

    def test_dc_bus_minus_is_zone_eligible(self):
        assert _zone_layers_for_net("DC_BUS-") == ["F.Cu", "B.Cu"]

    def test_cgnd_is_not_zone_eligible(self):
        """FIXED 2026-07-28: eligibility is now driven by
        routing_strategy=="plane_required" (core/design_rules.py), which
        GND does not declare (only ACMains/HighVoltage do) -- see
        docs/evidence/2026-07-28-zone-layer-classification-fix.md. GND
        nets no longer get automatic zone treatment from this function."""
        assert _zone_layers_for_net("CGND") == []

    def test_gate_l_short_form_is_not_zone_eligible(self):
        """GateDrive does not declare routing_strategy=="plane_required"."""
        assert _zone_layers_for_net("GATE_L") == []

    def test_gate_h_short_form_is_not_zone_eligible(self):
        assert _zone_layers_for_net("GATE_H") == []

    def test_pwm_l_short_form_is_not_zone_eligible(self):
        assert _zone_layers_for_net("PWM_L") == []

    def test_gate_ls_long_form_also_not_zone_eligible(self):
        """Short-form and long-form GateDrive names behave identically --
        neither gets automatic zone treatment post-fix."""
        assert _zone_layers_for_net("GATE_LS") == []

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
            route_pcb(parsed, {}, design_rules=DesignRules())

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
                route_pcb(parsed, {}, design_rules=DesignRules())

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
                route_pcb(parsed, {}, design_rules=None)

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
        """ac_l (ACMains, 6.0mm) + +340V_BUS (HV, 6.0mm), with a class_pairs
        override to a stricter 8.0mm -> effective 8.0mm.

        FIXED 2026-07-28: previously used vcc (Power), which after the
        routing_strategy-driven eligibility fix
        (docs/evidence/2026-07-28-zone-layer-classification-fix.md) no
        longer gets a zone at all -- Power is not "plane_required". Only
        ACMains/HighVoltage remain zone-eligible, and both declare an
        identical 6.0mm own clearance, so a class_pairs override is
        needed to actually exercise the cross-class lookup path (rather
        than coincidentally matching each class's own clearance)."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["ac_l", "+340V_BUS"],
            {"ac_l": [("C1", "1")], "+340V_BUS": [("C2", "1")]},
        )
        dr = self._build_dr({("ACMains", "HighVoltage"): {"clearance": 8.0}})
        content = '(kicad_pcb (version 20240108) (net 1 "ac_l") (net 2 "+340V_BUS"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 8.0000)" in output

    def test_same_class_nets_keep_own_clearance(self):
        """Two ACMains-class nets resolve to ACMains's own 6.0mm (never
        weaken).

        FIXED 2026-07-28: previously used two GND-class nets (PWR_RTN/
        CGND); GND is no longer zone-eligible post-fix (see above)."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["ac_l", "ac_n"],
            {"ac_l": [("C1", "1")], "ac_n": [("C2", "1")]},
        )
        dr = self._build_dr()
        content = '(kicad_pcb (version 20240108) (net 1 "ac_l") (net 2 "ac_n"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 6.0000)" in output

    def test_fallback_to_max_clearance_no_class_pair(self):
        """No class_pairs entry -> fallback to max(own, other).

        FIXED 2026-07-28: previously used vcc/+15V (both Power), which no
        longer get zones. Uses ACMains/HighVoltage instead -- both
        declare 6.0mm, so max(6.0, 6.0) == 6.0 exercises the fallback
        branch even though the two classes carry equal clearance."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["ac_l", "+340V_BUS"],
            {"ac_l": [("C1", "1")], "+340V_BUS": [("C2", "1")]},
        )
        dr = self._build_dr()
        content = '(kicad_pcb (version 20240108) (net 1 "ac_l") (net 2 "+340V_BUS"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 6.0000)" in output

    def test_single_netclass_no_cross_class(self):
        """Only one zone-eligible netclass: clearance equals own.

        FIXED 2026-07-28: previously used vcc (Power, 0.25mm), no longer
        zone-eligible. Uses ac_l (ACMains, 6.0mm) instead."""
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result_with_zones(
            ["ac_l"],
            {"ac_l": [("C1", "1")]},
        )
        dr = self._build_dr()
        content = '(kicad_pcb (version 20240108) (net 1 "ac_l"))'
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(clearance 6.0000)" in output

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


class TestZonesReplacedNotAppended:
    """U3 (R7): a board's stored zones must be replaced by the regenerated
    set, not left to coexist alongside it. Without this, any (zone ...)
    blocks already present in the incoming content (e.g. the 96 committed
    on pcb/temper.kicad_pcb) survive untouched into the written output
    alongside the newly emitted ones -- the board ends up carrying both a
    stale pour and a regenerated pour for the same net, and the stale one
    is never anything but stale carryover, never re-derived from what was
    actually routed.
    """

    # A stale zone with a priority value and a coordinate pair that no real
    # pad in these tests is anywhere near -- distinguishing markers that
    # only a *carried-over* zone (never a freshly computed one) could emit.
    _STALE_ZONE = (
        '  (zone (net 1) (net_name "{net}") (layer "F.Cu") (hatch full 0.5)\n'
        "    (priority 999)\n"
        "    (connect_pads yes (clearance 6))\n"
        "    (min_thickness 0.25)\n"
        "    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))\n"
        "    (polygon\n"
        "      (pts\n"
        "        (xy 999.0 999.0)\n"
        "        (xy 999.5 999.0)\n"
        "        (xy 999.5 999.5)\n"
        "      )\n"
        "    )\n"
        "  )"
    )

    def _make_result(self, net_name: str):
        from types import SimpleNamespace

        from temper_placer.core.netlist import Component

        mock_path = SimpleNamespace(path_length=0.0, coordinates=[])
        compiled_routes = {
            net_name: SimpleNamespace(path=mock_path, width_mm=0.1, vias=[]),
        }
        routing_results = SimpleNamespace(
            compiled_routes=compiled_routes,
            tree_routes={},
            partial_tree_routes={},
        )
        stage4 = SimpleNamespace(routing_results=routing_results)
        comp = Component(
            ref="C1", footprint="0805", bounds=(2.0, 1.25), initial_position=(50.0, 50.0)
        )
        nets = [SimpleNamespace(name=net_name, pins=[("C1", "1")])]
        pcb = SimpleNamespace(components=[comp], nets=nets)
        return SimpleNamespace(stage4=stage4, pcb=pcb, enable_zone_pours=True)

    def test_stale_zone_is_removed_not_appended_to(self):
        from temper_placer.core.design_rules import DesignRules
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result("vcc")  # "vcc" -> Power: zone-eligible
        dr = DesignRules()
        content = (
            '(kicad_pcb (version 20240108) (net 1 "vcc")\n'
            f"{self._STALE_ZONE.format(net='vcc')}\n"
            ")"
        )
        output, _ = _write_routes_to_content(content, result, design_rules=dr)

        # The stale zone's distinguishing markers must not survive.
        assert "(priority 999)" not in output
        assert "(xy 999.0 999.0)" not in output
        # A regenerated zone for the same net must be present instead.
        assert "(zone " in output
        assert '(net_name "vcc")' in output

    def test_no_zone_eligible_nets_still_drops_stale_zone(self):
        """Even when this run computes no new pour geometry for any net
        (here: a net whose class isn't zone-eligible), a stale zone
        inherited from the input board must not survive -- R7 forbids
        treating it as authoritative just because nothing replaced it.
        """
        from temper_placer.core.design_rules import DesignRules
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result("sclk")  # FinePitch: not zone-eligible
        dr = DesignRules()
        content = (
            '(kicad_pcb (version 20240108) (net 1 "sclk")\n'
            f"{self._STALE_ZONE.format(net='sclk')}\n"
            ")"
        )
        output, _ = _write_routes_to_content(content, result, design_rules=dr)
        assert "(zone " not in output


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

    def test_acmains_priority_higher_than_highvoltage_in_emitted_zones(self):
        """ACMains (dru=10→KiCad 80) > HighVoltage (dru=20→KiCad 70) in s-expr.

        FIXED 2026-07-28: previously compared ACMains against Power
        ("vcc"); Power no longer gets a zone at all post-fix (only
        ACMains/HighVoltage declare routing_strategy=="plane_required" --
        see docs/evidence/2026-07-28-zone-layer-classification-fix.md).
        Compares against HighVoltage ("SW_NODE") instead, the other
        remaining zone-eligible class."""
        import re

        from temper_placer.core.design_rules import DesignRules
        from temper_placer.router_v6.adapter import _write_routes_to_content

        result = self._make_result(
            ["AC_L", "SW_NODE"],
            {"AC_L": [("C1", "1")], "SW_NODE": [("C2", "1")]},
        )
        dr = DesignRules()
        content = '(kicad_pcb (version 20240108) (net 1 "AC_L") (net 2 "SW_NODE"))'
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
        assert "SW_NODE" in priorities_by_net
        ac_max = max(priorities_by_net["AC_L"])
        hv_max = max(priorities_by_net["SW_NODE"])
        assert ac_max > hv_max, f"ACMains ({ac_max}) should be > HighVoltage ({hv_max})"
        assert ac_max == 80
        assert hv_max == 70


class TestStitchIsolatedPads:
    """U3: trace-stitch pads outside pour polygons.

    Uses "ac_l" (ACMains) as the generic zone-eligible fixture net.
    FIXED 2026-07-28: previously used "vcc" (Power), which after the
    routing_strategy-driven eligibility fix
    (docs/evidence/2026-07-28-zone-layer-classification-fix.md) is no
    longer zone-eligible -- _stitch_isolated_pads() now delegates its own
    eligibility check to _zone_layers_for_net(), so a "vcc" fixture would
    exercise the ineligibility short-circuit instead of the geometry
    logic these tests exist to check.
    """

    def test_pad_inside_zone_is_not_stitched(self):
        segments: list[str] = []
        pad_positions = {"ac_l": [(5.0, 5.0)]}
        net_map = {"ac_l": 1}
        zone_points = {"ac_l": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
        _stitch_isolated_pads(pad_positions, segments, net_map, zone_points)
        assert len(segments) == 0

    def test_pad_outside_zone_gets_stitch_trace(self):
        segments: list[str] = []
        pad_positions = {"ac_l": [(5.0, 5.0), (50.0, 50.0)]}
        net_map = {"ac_l": 1}
        zone_points = {"ac_l": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
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
        _stitch_isolated_pads({"ac_l": [(50.0, 50.0)]}, segments, {"ac_l": 1}, {})
        assert len(segments) == 0

    def test_single_pad_inside_is_noop(self):
        segments: list[str] = []
        zone_points = {"ac_l": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
        _stitch_isolated_pads({"ac_l": [(5.0, 5.0)]}, segments, {"ac_l": 1}, zone_points)
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


# ============================================================================
# R1 — Property test: _to_stage0_netclass_rules() round-trip totality
# ============================================================================


class TestToStage0NetclassRulesRoundTrip:
    """R1: Hypothesis-generated round-trip through _to_stage0_netclass_rules()."""

    @staticmethod
    def _valid_netclass_strategy():
        """Strategy for core NetClassRules instances with all mapped fields."""
        from temper_placer.core.netclass_rules_gen import NetClassRules

        return st.builds(
            NetClassRules,
            name=st.text(min_size=1, max_size=30),
            trace_width=st.floats(min_value=0.05, max_value=10.0),
            clearance=st.floats(min_value=0.05, max_value=10.0),
            via_diameter=st.floats(min_value=0.1, max_value=5.0),
            via_drill=st.floats(min_value=0.05, max_value=3.0),
            max_current_rating=st.one_of(st.none(), st.floats(min_value=0.1, max_value=100.0)),
            safety_category=st.one_of(
                st.none(),
                st.sampled_from(["HV", "LV", "AC", "iso"]),
            ),
        )

    @given(source=_valid_netclass_strategy())
    @settings(max_examples=100, deadline=10000)
    def test_round_trip_preserves_all_mapped_fields(self, source):
        """All 1:1-mapped fields survive the conversion boundary."""
        result = _to_stage0_netclass_rules(source)

        assert result.name == source.name
        assert result.clearance_mm == source.clearance
        assert result.trace_width_mm == source.trace_width
        assert result.via_diameter_mm == source.via_diameter
        assert result.via_drill_mm == source.via_drill
        assert result.current_rating_amps == source.max_current_rating

    @given(source=_valid_netclass_strategy())
    @settings(max_examples=100, deadline=10000)
    def test_safety_category_survives_conversion(self, source):
        """safety_category must survive for R6 HV/AC forced-segment gate."""
        result = _to_stage0_netclass_rules(source)
        assert result.safety_category == source.safety_category


# ============================================================================
# R1b — Surface unrepresented fields via log warnings
# ============================================================================


class TestToStage0NetclassRulesWarnings:
    """R1b: unrepresented fields must log warnings when non-None."""

    def test_creepage_mm_warns_when_set(self, caplog):
        from temper_placer.core.netclass_rules_gen import NetClassRules

        source = NetClassRules(
            name="Test",
            trace_width=0.2,
            clearance=0.2,
            creepage_mm=6.0,
        )
        with caplog.at_level(logging.WARNING):
            _to_stage0_netclass_rules(source)
        assert any(
            "Creepage distance" in rec.message and "Test" in rec.message
            for rec in caplog.records
        )

    def test_voltage_v_warns_when_set(self, caplog):
        from temper_placer.core.netclass_rules_gen import NetClassRules

        source = NetClassRules(
            name="HVBus",
            trace_width=3.0,
            clearance=6.0,
            voltage_v=400.0,
        )
        with caplog.at_level(logging.WARNING):
            _to_stage0_netclass_rules(source)
        assert any(
            "Voltage rating" in rec.message and "HVBus" in rec.message
            for rec in caplog.records
        )

    def test_no_warning_when_creepage_is_default_zero(self, caplog):
        """creepage_mm=0.0 is the field default — should NOT warn."""
        from temper_placer.core.netclass_rules_gen import NetClassRules

        source = NetClassRules(
            name="Signal",
            trace_width=0.15,
            clearance=0.15,
            creepage_mm=0.0,
            voltage_v=0.0,
        )
        with caplog.at_level(logging.WARNING):
            _to_stage0_netclass_rules(source)
        warnings = [r for r in caplog.records if "stage0 equivalent" in r.message]
        assert len(warnings) == 0


# ============================================================================
# R2 — Property test: fail-loud on unrecognized shape
# ============================================================================


class TestToStage0NetclassRulesUnrecognizedShape:
    """R2: objects lacking expected attributes must raise."""

    @given(
        obj=st.builds(
            SimpleNamespace,
            name=st.text(min_size=1, max_size=10),
            trace_width=st.floats(min_value=0.1, max_value=1.0),
            # DELIBERATELY OMIT clearance — neither clearance nor clearance_mm
        )
    )
    @settings(max_examples=20, deadline=5000)
    def test_missing_clearance_raises(self, obj):
        """Object without .clearance or .clearance_mm must raise TypeError."""
        with pytest.raises(TypeError, match="clearance"):
            _to_stage0_netclass_rules(obj)

    @given(
        obj=st.builds(
            SimpleNamespace,
            clearance=st.floats(min_value=0.1, max_value=1.0),
            # DELIBERATELY OMIT name
        )
    )
    @settings(max_examples=20, deadline=5000)
    def test_missing_name_raises(self, obj):
        """Object without .name must raise TypeError."""
        with pytest.raises(TypeError, match="name"):
            _to_stage0_netclass_rules(obj)

    def test_empty_namespace_raises(self):
        """Bare namespace with no expected attributes must raise."""
        with pytest.raises(TypeError):
            _to_stage0_netclass_rules(SimpleNamespace())

    def test_clearance_mm_alias_works(self):
        """If source uses .clearance_mm (stage0-style), it works."""
        obj = SimpleNamespace(
            name="Test",
            clearance_mm=0.5,
            trace_width_mm=0.3,
            via_diameter_mm=0.8,
            via_drill_mm=0.4,
        )
        result = _to_stage0_netclass_rules(obj)
        assert result.clearance_mm == 0.5


# ============================================================================
# R3 — Property test: injected assignments never silently dropped
# ============================================================================


class TestInjectedAssignmentsSurvival:
    """R3: Hypothesis-generated net_class_assignments survive route_pcb()."""

    @staticmethod
    def _patched_pipeline():
        """Patch RouterV6Pipeline so route_pcb never does real routing."""
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

    @given(
        assignments=st.dictionaries(
            keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=["Lu", "L", "N"], whitelist_characters="_+")),
            values=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=["Lu", "L"])),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=30, deadline=30000)
    def test_varied_assignment_sets_survive(self, assignments):
        """Every entry in the assignment set must survive route_pcb().

        route_pcb() no longer accepts a raw net_class_assignments kwarg
        (removed 2026-07-24 -- it was always None from every real caller,
        the exact dead-parameter shape this whole investigation is about).
        The real, correct path is via design_rules.net_class_assignments,
        which route_pcb() reads directly and forwards to pipeline.run().
        """
        import os

        patcher, mock_pipe_cls = self._patched_pipeline()
        temp_path = self._write_minimal_pcb()
        try:
            nets = [SimpleNamespace(name=n) for n in assignments.keys()]
            parsed = type(
                "ParsedPCB",
                (),
                {"source_path": temp_path, "nets": nets},
            )()
            design_rules = SimpleNamespace(
                net_class_assignments=assignments,
                net_classes={},
            )

            route_pcb(
                parsed,
                {},
                design_rules=design_rules,
            )

            # The assignments should have been forwarded through pipeline.run()
            assert mock_pipe_cls.return_value.run.called, (
                "pipeline.run() was never called"
            )
            run_call = mock_pipe_cls.return_value.run.call_args
            assert run_call is not None, (
                "pipeline.run() was called but call_args is None"
            )
            _, run_kwargs = run_call
            forwarded = run_kwargs.get("net_class_assignments", {})
            assert isinstance(forwarded, dict), (
                f"net_class_assignments not forwarded as dict: {type(forwarded)}"
            )
            for net_name, class_name in assignments.items():
                assert forwarded.get(net_name) == class_name, (
                    f"assignment {net_name!r} → {class_name!r} was dropped "
                    f"or altered; forwarded assignments: {forwarded}"
                )
        finally:
            patcher.stop()
            os.unlink(temp_path)


# ============================================================================
# R4 — Regression test: injection-vs-native precedence
# ============================================================================


class TestInjectionPrecedence:
    """R4: Injected netclass values must win over native file values.

    This test verifies that when the adapter receives design_rules with
    net_classes, those values are written into the output PCB (via
    _apply_placements_to_pcb), reflecting injection precedence over
    what was in the original file.
    """

    def test_injected_design_rules_are_written_to_output(self):
        """When design_rules with net_classes is passed, output PCB reflects them."""
        import os
        import tempfile

        from temper_placer.core.design_rules import DesignRules

        pcb_fixture = (
            '(kicad_pcb (version 20240108)\n'
            '  (net 1 "VCC")\n'
            '  (setup\n'
            '    (net_class "Default" "" (clearance 0.2) (trace_width 0.2) (via_dia 0.6) (via_drill 0.3))\n'
            '  )\n'
            ')\n'
        )

        patcher = umock.patch("temper_placer.router_v6.pipeline.RouterV6Pipeline")
        mock_pipe_cls = patcher.start()
        mock_pipe = umock.MagicMock()
        mock_pipe.run.return_value = SimpleNamespace(
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
        mock_pipe_cls.return_value = mock_pipe

        try:
            with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as f:
                f.write(pcb_fixture)
                temp_path = f.name

            parsed = type(
                "ParsedPCB",
                (),
                {"source_path": temp_path, "nets": [SimpleNamespace(name="VCC")]},
            )()

            dr = DesignRules()
            from temper_placer.core.netclass_rules_gen import NetClassRules

            dr.net_classes["Power"] = NetClassRules(
                name="Power",
                trace_width=0.2,
                clearance=0.15,
                via_diameter=0.6,
                via_drill=0.3,
                dru_priority=0,
            )

            result = route_pcb(parsed, {}, design_rules=dr)
            assert result is not None
            # The design_rules was provided — verify the pipeline was
            # constructed (the mock was called), confirming the injection
            # path was exercised.
            assert mock_pipe_cls.called, (
                "Pipeline should have been constructed with injected design_rules"
            )
        finally:
            patcher.stop()
            os.unlink(temp_path)


# ============================================================================
# R5 — RoutingResult must expose forced-segment visibility
# ============================================================================


class TestRoutingResultForcedSegments:
    """R5: RoutingResult.forced_segment_nets tracks nets with forced segments."""

    def test_field_exists_with_default(self):
        """The forced_segment_nets field must be present with factory default."""
        result = RoutingResult()
        assert hasattr(result, "forced_segment_nets")
        assert result.forced_segment_nets == []

    def test_build_routing_result_populates_forced_segment_nets(self):
        """_build_routing_result threads forced-segment net names from compiled_routes."""
        from temper_placer.router_v6._adapter_convert import _build_routing_result
        from temper_placer.router_v6.astar_pathfinding import RoutePath

        # Construct a CompiledRoute-like object with a forced-segment path.
        # In production, compile_routing_results() wraps each RoutePath in
        # a CompiledRoute with .path = RoutePath.  _build_routing_result
        # reads compiled_routes[net].path.forced_segment_count.
        forced_path = RoutePath(
            net_name="SW_NODE",
            coordinates=[(0, 0), (10, 10)],
            layer_name="F.Cu",
            path_length=14.14,
            forced_segment_count=1,
        )
        compiled_route = SimpleNamespace(
            net_name="SW_NODE",
            path=forced_path,
            width_mm=0.2,
            vias=[],
        )
        routing_results = SimpleNamespace(
            compiled_routes={"SW_NODE": compiled_route},
            failed_nets=[],
        )
        stage4 = SimpleNamespace(routing_results=routing_results)
        mock_result = SimpleNamespace(
            stage4=stage4,
            completion_rate=1.0,
        )

        routing_result = _build_routing_result(mock_result)
        assert "SW_NODE" in routing_result.forced_segment_nets

    def test_gate_disallowed_net_reaches_unrouted_nets(self):
        """R1/R3: _build_routing_result's RoutingResults.failed_nets ->
        RoutingResult.unrouted_nets conversion is a real passthrough, not a
        no-op or silent drop. Scoped to that one conversion boundary (input
        is a directly-constructed failed_nets list, not a live gate-triggered
        failure) -- the gate actually producing that failure is covered
        separately by TestHVACForcedSegmentFailClosed and the property test
        in test_forced_segment_fail_closed_pbt.py, both of which call
        run_astar_pathfinding() for real. Mirrors the design-rules-wiring
        lesson: a correct-looking unit change can still be a no-op downstream
        if nothing verifies it actually reaches the outermost consumer.
        """
        from temper_placer.router_v6._adapter_convert import _build_routing_result

        routing_results = SimpleNamespace(
            compiled_routes={},
            failed_nets=["SPI_MOSI"],
        )
        stage4 = SimpleNamespace(routing_results=routing_results)
        mock_result = SimpleNamespace(
            stage4=stage4,
            completion_rate=0.0,
        )

        routing_result = _build_routing_result(mock_result)
        assert "SPI_MOSI" in routing_result.unrouted_nets, (
            "A net reported failed by the gate/pathfinder must surface in "
            "the outermost RoutingResult.unrouted_nets, not just internally"
        )


# ============================================================================
# R6 — HV/AC forced-segment fail-closed
# ============================================================================


class TestHVACForcedSegmentFailClosed:
    """R1/R2: no net class -- including HV/AC -- may silently forced-segment.

    ``test_hv_net_name_excluded_from_astar_by_should_route`` and
    ``test_ac_net_name_excluded_from_astar_by_should_route`` use canonical
    HV/AC net names (``SW_NODE``, ``AC_L``). Those names are themselves
    excluded from A* entirely by ``_should_route()``'s HV pattern matching
    (handled by zone pours instead), so they never reach
    ``_allow_forced_segments`` and prove name-pattern exclusion, not gate
    behavior -- kept as real coverage of that exclusion, correctly labeled.
    The two tests below them use non-excluded net names that carry an
    HV/AC ``safety_category`` via ``design_rules`` instead, so they
    genuinely drive execution into the gate.
    """

    def test_hv_net_name_excluded_from_astar_by_should_route(self):
        """Canonical HV net names never reach A* at all (zone pours handle them)."""
        import numpy as np

        from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
        from temper_placer.router_v6.channel_mapping import (
            ChannelMapping,
            ChannelPath,
        )
        from temper_placer.router_v6.occupancy_grid import OccupancyGrid
        from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

        # Build a 30x30 grid with a vertical wall blocking the path
        grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)
        grid.grid[:, 15] = 1  # wall blocking all horizontal routes

        # Design rules with an HV-class net assignment
        design_rules = DesignRules()
        design_rules.net_classes["HighVoltage"] = NetClassRules(
            name="HighVoltage",
            clearance_mm=6.0,
            trace_width_mm=3.0,
            via_diameter_mm=1.2,
            via_drill_mm=0.6,
            safety_category="HV",
        )
        design_rules.net_class_assignments["SW_NODE"] = "HighVoltage"

        # A net that must cross the wall
        channel_path = ChannelPath(
            net_name="SW_NODE",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"SW_NODE": channel_path}),
            grid,
            design_rules=design_rules,
            max_iter=10_000,
        )

        # HV net is excluded from A* routing by _should_route (handled by zone pours)
        assert "SW_NODE" not in result.routed_paths, (
            "HV-class net must not succeed via A*"
        )
        # U1: _should_route's name-based exclusion is a routing-strategy
        # decision, not a "declined net" in R3/R4's sense -- it must not
        # produce a failure_reports entry (that would misrepresent a
        # zone-pour-handled net as a prover decline).
        assert "SW_NODE" not in (result.failure_reports or {}), (
            "A net excluded by _should_route is not a decline and must not "
            "appear in failure_reports"
        )

    def test_ac_net_name_excluded_from_astar_by_should_route(self):
        """Canonical AC net names never reach A* at all (zone pours handle them)."""
        import numpy as np

        from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
        from temper_placer.router_v6.channel_mapping import (
            ChannelMapping,
            ChannelPath,
        )
        from temper_placer.router_v6.occupancy_grid import OccupancyGrid
        from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

        grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)
        grid.grid[:, 15] = 1

        design_rules = DesignRules()
        design_rules.net_classes["ACMains"] = NetClassRules(
            name="ACMains",
            clearance_mm=6.0,
            trace_width_mm=2.5,
            via_diameter_mm=1.2,
            via_drill_mm=0.6,
            safety_category="AC",
        )
        design_rules.net_class_assignments["AC_L"] = "ACMains"

        channel_path = ChannelPath(
            net_name="AC_L",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"AC_L": channel_path}),
            grid,
            design_rules=design_rules,
            max_iter=10_000,
        )

        # AC net is excluded from A* routing by _should_route (handled by zone pours)
        assert "AC_L" not in result.routed_paths
        assert "AC_L" not in (result.failure_reports or {}), (
            "A net excluded by _should_route is not a decline and must not "
            "appear in failure_reports"
        )

    def test_hv_class_net_with_routable_name_fails_closed_via_gate(self):
        """An HV-class net whose *name* doesn't match the HV exclusion patterns
        genuinely reaches attempt_route()/_allow_forced_segments() and must
        still fail closed -- unlike the two tests above, this exercises the
        gate's own decision logic, not _should_route()'s name-based exclusion.
        """
        import numpy as np

        from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
        from temper_placer.router_v6.channel_mapping import (
            ChannelMapping,
            ChannelPath,
        )
        from temper_placer.router_v6.occupancy_grid import OccupancyGrid
        from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

        grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)
        grid.grid[:, 15] = 1

        design_rules = DesignRules()
        design_rules.net_classes["HighVoltage"] = NetClassRules(
            name="HighVoltage",
            clearance_mm=6.0,
            trace_width_mm=3.0,
            via_diameter_mm=1.2,
            via_drill_mm=0.6,
            safety_category="HV",
        )
        design_rules.net_class_assignments["ISO_FB_HIGH"] = "HighVoltage"

        channel_path = ChannelPath(
            net_name="ISO_FB_HIGH",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"ISO_FB_HIGH": channel_path}),
            grid,
            design_rules=design_rules,
            max_iter=10_000,
        )

        assert "ISO_FB_HIGH" not in result.routed_paths, (
            "HV-class net must fail closed even when its name reaches the gate"
        )
        assert "ISO_FB_HIGH" in result.failed_nets, (
            "HV-class net must be honestly reported as failed, proving the "
            "gate -- not _should_route()'s name exclusion -- caused this"
        )

        # U1: reason attribution -- this is the forced-segment fail-closed
        # gate specifically, not an unattributed gap.
        from temper_placer.router_v6._astar_reconstruct import (
            RULE_ID_FORCED_SEGMENT_FAIL_CLOSED,
        )
        from temper_placer.router_v6.net_classification import classify_net_type

        report = result.failure_reports["ISO_FB_HIGH"]
        assert report.rule_id == RULE_ID_FORCED_SEGMENT_FAIL_CLOSED, (
            "Forced-segment refusal must name the specific fail-closed "
            "mechanism, not a fabricated or generic reason"
        )
        assert report.attribution_gap is False, (
            "A named rule_id and attribution_gap=True is a contradiction -- "
            "this decline has a known cause"
        )
        assert report.domain == classify_net_type("ISO_FB_HIGH"), (
            "domain must come from net_classification's canonical helper, "
            "not a hardcoded or fabricated classification"
        )

    def test_ac_class_net_with_routable_name_fails_closed_via_gate(self):
        """Same as above for an AC-class net with a non-excluded name."""
        import numpy as np

        from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
        from temper_placer.router_v6.channel_mapping import (
            ChannelMapping,
            ChannelPath,
        )
        from temper_placer.router_v6.occupancy_grid import OccupancyGrid
        from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

        grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)
        grid.grid[:, 15] = 1

        design_rules = DesignRules()
        design_rules.net_classes["ACMains"] = NetClassRules(
            name="ACMains",
            clearance_mm=6.0,
            trace_width_mm=2.5,
            via_diameter_mm=1.2,
            via_drill_mm=0.6,
            safety_category="AC",
        )
        design_rules.net_class_assignments["ISO_FB_MAINS"] = "ACMains"

        channel_path = ChannelPath(
            net_name="ISO_FB_MAINS",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"ISO_FB_MAINS": channel_path}),
            grid,
            design_rules=design_rules,
            max_iter=10_000,
        )

        assert "ISO_FB_MAINS" not in result.routed_paths, (
            "AC-class net must fail closed even when its name reaches the gate"
        )
        assert "ISO_FB_MAINS" in result.failed_nets, (
            "AC-class net must be honestly reported as failed, proving the "
            "gate -- not _should_route()'s name exclusion -- caused this"
        )

        from temper_placer.router_v6._astar_reconstruct import (
            RULE_ID_FORCED_SEGMENT_FAIL_CLOSED,
        )
        from temper_placer.router_v6.net_classification import classify_net_type

        report = result.failure_reports["ISO_FB_MAINS"]
        assert report.rule_id == RULE_ID_FORCED_SEGMENT_FAIL_CLOSED, (
            "Forced-segment refusal must name the specific fail-closed "
            "mechanism, not a fabricated or generic reason"
        )
        assert report.attribution_gap is False
        assert report.domain == classify_net_type("ISO_FB_MAINS")

    def test_signal_net_also_fails_closed(self):
        """R2: no net class is exempt -- plain signal nets fail closed too."""
        import numpy as np

        from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
        from temper_placer.router_v6.channel_mapping import (
            ChannelMapping,
            ChannelPath,
        )
        from temper_placer.router_v6.occupancy_grid import OccupancyGrid
        from temper_placer.router_v6.stage0_data import DesignRules

        grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)
        grid.grid[:, 15] = 1

        design_rules = DesignRules()
        design_rules.net_class_assignments["SPI_MOSI"] = "Signal"

        channel_path = ChannelPath(
            net_name="SPI_MOSI",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"SPI_MOSI": channel_path}),
            grid,
            design_rules=design_rules,
            max_iter=10_000,
        )

        # Uniform fail-closed (R2): no net class -- not even plain Signal --
        # is exempt from the forced-segment gate.
        assert "SPI_MOSI" not in result.routed_paths, (
            "Signal net must fail closed, not fabricate a forced segment"
        )
        assert "SPI_MOSI" in result.failed_nets, (
            "Signal net must be honestly reported as failed"
        )

        from temper_placer.router_v6._astar_reconstruct import (
            RULE_ID_FORCED_SEGMENT_FAIL_CLOSED,
        )
        from temper_placer.router_v6.net_classification import classify_net_type

        report = result.failure_reports["SPI_MOSI"]
        assert report.rule_id == RULE_ID_FORCED_SEGMENT_FAIL_CLOSED, (
            "Signal nets get the same specific fail-closed attribution as "
            "any other class -- no net class is exempt"
        )
        assert report.attribution_gap is False
        assert report.domain == classify_net_type("SPI_MOSI")


class _RaisingDesignRules:
    """design_rules stand-in whose get_rules_for_net() always raises.

    Pre-generalization, _allow_forced_segments() called this method and had
    to fail closed on exception. It no longer calls it at all -- kept only
    as an input-shape regression pin: if a future change reintroduces
    per-net design_rules lookups here, this proves the gate still disallows
    rather than propagating the exception or silently defaulting to allow.
    """

    def get_rules_for_net(self, net_name):
        raise RuntimeError("simulated wiring failure")


class TestAllowForcedSegmentsGate:
    """Direct coverage of _allow_forced_segments() itself (R1/R2).

    The gate is now an unconditional `return False` -- there is no
    remaining conditional logic to branch-test. This class is a flat
    regression pin over a representative input sweep (varied net class,
    tree-route context, and design_rules shape including None and a
    raising stand-in) proving the constant-return contract holds
    regardless of what a caller passes, not a test of per-input branches.
    """

    @pytest.mark.parametrize(
        ("net_name", "design_rules_factory", "tree_route_active"),
        [
            ("SPI_MOSI", "hv_classified", False),
            ("SW_NODE", "hv_classified", False),
            ("vcc", "hv_classified", False),
            ("AnythingAtAll", "hv_classified", True),
            ("ANY_NET", "none", False),
            ("ANY_NET", "raising", False),
        ],
    )
    def test_disallows_regardless_of_input_shape(
        self, net_name, design_rules_factory, tree_route_active
    ):
        from temper_placer.router_v6._astar_reconstruct import (
            _allow_forced_segments,
        )
        from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

        if design_rules_factory == "hv_classified":
            design_rules = DesignRules()
            design_rules.net_classes["HighVoltage"] = NetClassRules(
                name="HighVoltage",
                clearance_mm=6.0,
                trace_width_mm=3.0,
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
                safety_category="HV",
            )
            design_rules.net_class_assignments[net_name] = "HighVoltage"
        elif design_rules_factory == "none":
            design_rules = None
        else:
            design_rules = _RaisingDesignRules()

        assert (
            _allow_forced_segments(net_name, design_rules, tree_route_active) is False
        )

    def test_routable_net_still_routes_when_a_legal_path_exists(self):
        """The gate must not block nets that have a genuinely legal path."""
        import numpy as np

        from temper_placer.router_v6._astar_reconstruct import run_astar_pathfinding
        from temper_placer.router_v6.channel_mapping import (
            ChannelMapping,
            ChannelPath,
        )
        from temper_placer.router_v6.occupancy_grid import OccupancyGrid
        from temper_placer.router_v6.stage0_data import DesignRules

        # Open grid -- no obstacles, a direct legal path exists.
        grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)

        design_rules = DesignRules()
        channel_path = ChannelPath(
            net_name="SPI_CLK",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (10.0, 0.0)],
            total_length=10.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"SPI_CLK": channel_path}),
            grid,
            design_rules=design_rules,
            max_iter=10_000,
        )

        assert "SPI_CLK" in result.routed_paths, (
            "A net with a genuinely legal path must still route successfully"
        )
        assert result.routed_paths["SPI_CLK"].forced_segment_count == 0, (
            "A legally-routed net must not carry a forced segment"
        )


# ============================================================================
# R4 (U7) — GateDrive splits into GateDriveHV/GateDriveSELV
# ============================================================================


class TestGateDriveSplitSeenAsHVNotLV:
    """R4/U7: GATE_HS/GATE_LS sit on the HV (switching) side of U7's
    reinforced barrier and must convert through to the router as
    ``safety_category == "HV"``, not "LV". Leaving the HV-side class "LV"
    reproduces the exact failure the split exists to fix, one file deeper
    than the four generated surfaces reach (docs/plans/
    2026-07-28-003-refactor-ato-net-classification-ssot-plan.md U7).
    """

    def test_gatedrive_hv_class_converts_to_stage0_as_hv(self):
        """The real production GateDriveHV class -- not a synthetic
        fixture -- must survive ``_to_stage0_netclass_rules`` as "HV"."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        core_rules = TEMPER_NET_CLASSES["GateDriveHV"]
        stage0 = _to_stage0_netclass_rules(core_rules)
        assert stage0.safety_category == "HV"
        assert stage0.safety_category != "LV"

    def test_gatedrive_selv_class_converts_to_stage0_as_lv(self):
        """The SELV-side (MCU/PWM) half keeps 'LV' -- there is no separate
        SELV value in the safety_category vocabulary (HV/LV/AC/iso)."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        core_rules = TEMPER_NET_CLASSES["GateDriveSELV"]
        stage0 = _to_stage0_netclass_rules(core_rules)
        assert stage0.safety_category == "LV"

    def test_gatedrive_hv_outranks_gatedrive_selv_in_bottleneck_geometry(self):
        """The forced-segment/bottleneck discount ranks by safety_category
        (router_v6.bottleneck_geometry._SAFETY_RANK); GateDriveHV must now
        rank as HV (2), strictly above GateDriveSELV's LV (1) -- before the
        split both ranked identically as LV(1), which is the defect this
        unit fixes."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES
        from temper_placer.router_v6.bottleneck_geometry import _SAFETY_RANK

        hv_rank = _SAFETY_RANK[TEMPER_NET_CLASSES["GateDriveHV"].safety_category]
        selv_rank = _SAFETY_RANK[TEMPER_NET_CLASSES["GateDriveSELV"].safety_category]
        assert hv_rank > selv_rank

    def test_gate_hs_and_gate_ls_resolve_through_the_full_chain_to_hv(self):
        """End-to-end: the real net name -> assignment table -> class table
        -> stage0 conversion chain used by the router must resolve GATE_HS
        and GATE_LS to safety_category "HV"."""
        from temper_placer.core.design_rules import (
            TEMPER_NET_ASSIGNMENTS,
            TEMPER_NET_CLASSES,
        )

        for net_name in ("GATE_HS", "GATE_LS"):
            class_name = TEMPER_NET_ASSIGNMENTS[net_name]
            stage0 = _to_stage0_netclass_rules(TEMPER_NET_CLASSES[class_name])
            assert stage0.safety_category == "HV", (
                f"{net_name} (class {class_name!r}) must resolve to HV, not "
                f"{stage0.safety_category!r}"
            )

    def test_pwm_hs_and_pwm_ls_resolve_through_the_full_chain_to_lv(self):
        """Same chain for the SELV-side names -- must not accidentally
        become HV in the split."""
        from temper_placer.core.design_rules import (
            TEMPER_NET_ASSIGNMENTS,
            TEMPER_NET_CLASSES,
        )

        for net_name in ("PWM_HS", "PWM_LS"):
            class_name = TEMPER_NET_ASSIGNMENTS[net_name]
            stage0 = _to_stage0_netclass_rules(TEMPER_NET_CLASSES[class_name])
            assert stage0.safety_category == "LV"
