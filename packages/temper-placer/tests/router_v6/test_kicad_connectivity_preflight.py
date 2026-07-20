"""Synthetic emission tests for kicad_connectivity — the U4 preflight parser.

Verifies that parsed emitted content produces correct connectivity verdicts
without requiring a full KiCad routing run.
"""

from __future__ import annotations

import pytest

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
        assert "NET" in result
        assert result["NET"].disposition == NetDisposition.ROUTED

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
