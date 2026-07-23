"""Synthetic emission tests for kicad_connectivity — the U4 preflight parser.

Verifies that parsed emitted content produces correct connectivity verdicts
without requiring a full KiCad routing run.
"""

from __future__ import annotations

from temper_placer.router_v6.connectivity import NetDisposition
from temper_placer.router_v6.kicad_connectivity import connectivity_preflight


def _make_two_pad_pcb(net_name: str, x1: float, y1: float, x2: float, y2: float) -> str:
    """Synthetic KiCad s-expression with one net and one segment joining two pads."""
    return f"""(kicad_pcb (version 20240108)
  (net 1 "{net_name}")
  (segment (start {x1} {y1}) (end {x2} {y2}) (width 0.2) (layer "F.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000000"))
)
"""


def _make_two_pad_bcu_pcb(net_name: str, x1: float, y1: float, x2: float, y2: float) -> str:
    """Same but the segment is on B.Cu."""
    return f"""(kicad_pcb (version 20240108)
  (net 1 "{net_name}")
  (segment (start {x1} {y1}) (end {x2} {y2}) (width 0.2) (layer "B.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000000"))
)
"""


class TestPreflightParsesEmittedPCB:
    """Synthetic emitted-content connectivity checks without real routing."""

    def test_two_pad_connected_returns_routed(self):
        """Two pads joined by one emitted segment → ROUTED."""
        pcb = _make_two_pad_pcb("NET", 0.0, 0.0, 5.0, 0.0)
        pads = {"NET": [(0.0, 0.0), (5.0, 0.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.ROUTED


class TestZoneConnectivity:
    """U5: zone/pour geometry recognized by connectivity verifier."""

    def test_pad_inside_zone_is_connected(self):
        """A pad whose center lies inside a pour polygon is counted as
        connected to it in the union-find."""
        pcb = """(kicad_pcb (version 20240108)
  (net 1 "NET")
  (zone (net 1) (net_name "NET") (layer "F.Cu")
    (hatch full 0.5)
    (priority 0)
    (connect_pads yes (clearance 0.25))
    (min_thickness 0.25)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts
      (xy 0.0 0.0) (xy 10.0 0.0) (xy 10.0 10.0) (xy 0.0 10.0)
    ))
  )
)
"""
        pads = {"NET": [(5.0, 5.0), (7.0, 7.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.ROUTED

    def test_pad_outside_zone_is_not_connected(self):
        """A pad outside the zone polygon is reported INCOMPLETE."""
        pcb = """(kicad_pcb (version 20240108)
  (net 1 "NET")
  (zone (net 1) (net_name "NET") (layer "F.Cu")
    (hatch full 0.5)
    (priority 0)
    (connect_pads yes (clearance 0.25))
    (min_thickness 0.25)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts
      (xy 0.0 0.0) (xy 10.0 0.0) (xy 10.0 10.0) (xy 0.0 10.0)
    ))
  )
)
"""
        pads = {"NET": [(5.0, 5.0), (20.0, 20.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.INCOMPLETE

    def test_two_pad_disconnected_returns_incomplete(self):
        """Track between pad A and nowhere near pad B → INCOMPLETE."""
        pcb = _make_two_pad_pcb("NET", 0.0, 0.0, 2.0, 0.0)
        pads = {"NET": [(0.0, 0.0), (10.0, 0.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.INCOMPLETE

    def test_bcu_segment_with_both_layer_pads_returns_routed(self):
        """A B.Cu segment connecting both-layer pads → ROUTED (preflight is permissive)."""
        pcb = _make_two_pad_bcu_pcb("NET", 0.0, 0.0, 5.0, 0.0)
        pads = {"NET": [(0.0, 0.0), (5.0, 0.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.ROUTED

    def test_three_pad_net_with_only_two_connected_is_incomplete(self):
        """Three pads, one segment joining only two → INCOMPLETE."""
        pcb = _make_two_pad_pcb("NET", 0.0, 0.0, 5.0, 0.0)
        pads = {"NET": [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.INCOMPLETE
        assert result["NET"].connected_pad_count == 2
        assert result["NET"].total_required_pad_count == 3

    def test_empty_content_returns_incomplete_for_known_nets(self):
        """Empty content with pads → INCOMPLETE (no copper to join them)."""
        result = connectivity_preflight("", {"NET": [(0.0, 0.0)]})
        assert "NET" in result
        assert result["NET"].disposition == NetDisposition.INCOMPLETE

    def test_width_field_direct_parsing(self):
        """Regression test: the CopperTrack constructor accepts 'width' not 'width_mm'.

        This would have caught the silent TypeError that returned
        connectivity=None from the broad exception handler.
        """
        pcb = _make_two_pad_pcb("NET", 0.0, 0.0, 5.0, 0.0)
        pads = {"NET": [(0.0, 0.0), (5.0, 0.0)]}
        result = connectivity_preflight(pcb, pads)
        # If the kwarg was wrong, connectivity_preflight raises inside
        # the try block and _compute_connectivity returns None — but
        # here we call it directly, so TypeError surfaces.
        assert result["NET"].disposition == NetDisposition.ROUTED


class TestViaConnectivity:
    """U4: via parsing and cross-layer connectivity."""

    def test_via_parsed_and_joins_cross_layer_segments(self):
        """A via connecting F.Cu and B.Cu tracks of the same net creates
        one connected component."""
        pcb = """"(kicad_pcb (version 20240108)
  (net 1 "NET")
  (segment (start 0.0 0.0) (end 5.0 0.0) (width 0.2) (layer "F.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000001"))
  (via (at 5.0 0.0) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000002"))
  (segment (start 5.0 0.0) (end 10.0 0.0) (width 0.2) (layer "B.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000003"))
)
"""
        pads = {"NET": [(0.0, 0.0), (10.0, 0.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.ROUTED

    def test_via_missing_net_field_skipped(self):
        """A via without a net field is silently skipped (not fatal)."""
        pcb = """"(kicad_pcb (version 20240108)
  (net 1 "NET")
  (segment (start 0.0 0.0) (end 5.0 0.0) (width 0.2) (layer "F.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000001"))
  (via (at 5.0 0.0) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu"))
)
"""
        pads = {"NET": [(0.0, 0.0), (5.0, 0.0)]}
        result = connectivity_preflight(pcb, pads)
        assert result["NET"].disposition == NetDisposition.ROUTED
