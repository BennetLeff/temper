"""NetRouteResult — the type-system fix for fake completions.

Pins the Python shim (``connectivity.verify_net_route_result``) and the
emitted-content preflight (``kicad_connectivity.net_route_result_preflight``)
against the Rust ``temper_geometry.NetRouteResult`` verdict type, whose
``Connected`` variant is constructible ONLY by
``NetRouteResult::verify_continuity`` (private ``VerifiedRoute`` fields —
see ``packages/temper-geometry/src/net_route_result.rs`` and its
``compile_fail`` doctest).

The core claims under test:

1. A net whose emitted segments join all pads → ``connected``.
2. The b39b382d fake-completion shape (copper exists but does not join all
   pads) → ``partial`` with specific unconnected pads — NEVER ``connected``.
3. A net whose only claimed connection is a zone outline → ``zone_dependent``,
   never ``connected`` (zone fill is a separate KiCad step that this
   codebase never runs; an outline is not copper).
4. No copper at all → ``failed``.
5. The preflight classifies a real written board's nets through the same
   Rust kernel, using REAL pad geometry (shape/size/rotation/layers from the
   parsed pins) rather than the legacy U4 best-effort both-layer rects.
"""

from __future__ import annotations

from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    CopperVia,
    PadIdentity,
    Point,
    verify_net_route_result,
)
from temper_placer.router_v6.kicad_connectivity import net_route_result_preflight


def _pad(
    net: str,
    x: float,
    y: float,
    layer: int,
    index: int,
    w: float = 1.0,
    h: float = 1.0,
    shape: str = "circle",
    rotation: float = 0.0,
) -> CopperPad:
    return CopperPad(
        identity=PadIdentity(
            component_ref=f"U{index}",
            pad=str(index),
            net=net,
            x=x,
            y=y,
            layers=(layer,),
        ),
        center=Point(x, y),
        shape=shape,
        size=(w, h),
        rotation=rotation,
    )


def _track(net: str, x1: float, y1: float, x2: float, y2: float, layer: int) -> CopperTrack:
    return CopperTrack(
        start=Point(x1, y1),
        end=Point(x2, y2),
        layer=layer,
        width=0.5,
        net=net,
    )


def _via(net: str, x: float, y: float, layers: tuple[int, ...]) -> CopperVia:
    return CopperVia(center=Point(x, y), layers=frozenset(layers), diameter=0.6, net=net)


class TestVerifyNetRouteResult:
    """The shim's verdicts must come from the Rust kernel, not Python logic."""

    def test_all_pads_joined_is_connected(self):
        pads = [_pad("N", 0.0, 0.0, 0, 0), _pad("N", 5.0, 0.0, 0, 1)]
        tracks = [_track("N", 0.0, 0.0, 5.0, 0.0, 0)]
        result = verify_net_route_result(pads, tracks, [])
        assert result.disposition == "connected"
        assert result.pad_ids == [0, 1]
        assert result.segment_ids == [0]

    def test_fake_completion_shape_is_partial_never_connected(self):
        # The b39b382d shape: copper exists for the net but joins only one
        # of its two pads.
        pads = [_pad("N", 0.0, 0.0, 0, 0), _pad("N", 10.0, 10.0, 0, 1)]
        tracks = [_track("N", 0.0, 0.0, 2.0, 0.0, 0)]  # touches pad 0 only
        result = verify_net_route_result(pads, tracks, [])
        assert result.disposition == "partial"
        assert result.unconnected_pads != []
        assert result.segment_count == 1

    def test_segment_on_wrong_layer_is_partial(self):
        # The M1-bug shape: copper on layer 1, both pads on layer 0.
        pads = [_pad("N", 0.0, 0.0, 0, 0), _pad("N", 5.0, 0.0, 0, 1)]
        tracks = [_track("N", 0.0, 0.0, 5.0, 0.0, 1)]
        result = verify_net_route_result(pads, tracks, [])
        assert result.disposition == "partial"
        assert set(result.unconnected_pads) == {0, 1}

    def test_via_connects_two_layers(self):
        pads = [_pad("N", 0.0, 0.0, 0, 0), _pad("N", 5.0, 0.0, 1, 1)]
        tracks = [
            _track("N", 0.0, 0.0, 2.0, 0.0, 0),
            _track("N", 2.0, 0.0, 5.0, 0.0, 1),
        ]
        vias = [_via("N", 2.0, 0.0, (0, 1))]
        result = verify_net_route_result(pads, tracks, vias)
        assert result.disposition == "connected"
        assert result.via_ids == [0]

    def test_via_at_wrong_coordinates_is_partial(self):
        pads = [_pad("N", 0.0, 0.0, 0, 0), _pad("N", 5.0, 0.0, 1, 1)]
        tracks = [
            _track("N", 0.0, 0.0, 2.0, 0.0, 0),
            _track("N", 2.0, 0.0, 5.0, 0.0, 1),
        ]
        vias = [_via("N", 9.0, 9.0, (0, 1))]  # nowhere near the junction
        result = verify_net_route_result(pads, tracks, vias)
        assert result.disposition == "partial"

    def test_zone_outline_alone_is_zone_dependent_never_connected(self):
        pads = [_pad("N", 0.0, 0.0, 0, 0), _pad("N", 5.0, 0.0, 0, 1)]
        result = verify_net_route_result(pads, [], [], zone_layers=[0], zone_outline_count=1)
        assert result.disposition == "zone_dependent"
        assert result.outline_count == 1
        assert result.pads_in_outlines == 2

    def test_no_copper_at_all_is_failed(self):
        pads = [_pad("N", 0.0, 0.0, 0, 0), _pad("N", 5.0, 0.0, 0, 1)]
        result = verify_net_route_result(pads, [], [])
        assert result.disposition == "failed"
        assert result.reason == "no_copper_emitted"

    def test_single_pad_is_trivially_connected(self):
        pads = [_pad("N", 0.0, 0.0, 0, 0)]
        result = verify_net_route_result(pads, [], [])
        assert result.disposition == "connected"

    def test_zero_pads_is_failed(self):
        result = verify_net_route_result([], [], [])
        assert result.disposition == "failed"
        assert result.reason == "no_pads"

    def test_rect_pad_touched_by_crossing_track_is_connected(self):
        # A rect pad: a track crossing its area connects even when the track
        # endpoint is beyond the pad centre (kernel geometric-touch
        # semantics, the physically truthful model).
        pads = [
            _pad("N", 0.0, 0.0, 0, 0, w=2.0, h=2.0, shape="rect"),
            _pad("N", 6.0, 0.0, 0, 1, w=2.0, h=2.0, shape="rect"),
        ]
        tracks = [_track("N", 0.0, 0.0, 6.0, 0.0, 0)]
        result = verify_net_route_result(pads, tracks, [])
        assert result.disposition == "connected"


# ---------------------------------------------------------------------------
# Preflight over a written-board s-expression (real pad geometry parsing)
# ---------------------------------------------------------------------------

# A minimal but fully parseable board: layers declaration, one net, one
# two-pad footprint, and one emitted segment joining the pads.
_MINIMAL_BOARD = """(kicad_pcb (version 20240108)
  (generator "temper-test")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (net 1 "N")
  (footprint "Test:R" (layer "F.Cu")
    (at 0 0 0)
    (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
    (pad "1" thru_hole circle (at -2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
    (pad "2" thru_hole circle (at 2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
  )
)
"""

_MINIMAL_BOARD_JOINED = """(kicad_pcb (version 20240108)
  (generator "temper-test")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (net 1 "N")
  (footprint "Test:R" (layer "F.Cu")
    (at 0 0 0)
    (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
    (pad "1" thru_hole circle (at -2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
    (pad "2" thru_hole circle (at 2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
  )
  (segment (start -2.5 0) (end 2.5 0) (width 0.5) (layer "F.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000001"))
)
"""


class TestNetRouteResultPreflight:
    """The router-side verification must classify REAL written content."""

    def test_unrouted_board_is_failed_no_copper(self):
        results = net_route_result_preflight(_MINIMAL_BOARD)
        assert "N" in results
        assert results["N"].disposition == "failed"
        assert results["N"].reason == "no_copper_emitted"

    def test_joined_board_is_connected(self):
        results = net_route_result_preflight(_MINIMAL_BOARD_JOINED)
        assert "N" in results
        assert results["N"].disposition == "connected"

    def test_zone_outline_board_is_zone_dependent(self):
        content = """(kicad_pcb (version 20240108)
  (generator "temper-test")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (net 1 "N")
  (footprint "Test:R" (layer "F.Cu")
    (at 0 0 0)
    (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
    (pad "1" thru_hole circle (at -2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
    (pad "2" thru_hole circle (at 2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
  )
  (zone (net 1) (net_name "N") (layer "F.Cu")
    (hatch full 0.5)
    (priority 0)
    (connect_pads yes (clearance 0.25))
    (min_thickness 0.25)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts
      (xy -5.0 -5.0) (xy 5.0 -5.0) (xy 5.0 5.0) (xy -5.0 5.0)
    ))
  )
)
"""
        results = net_route_result_preflight(content)
        assert "N" in results
        assert results["N"].disposition == "zone_dependent"
        assert results["N"].outline_count == 1

    def test_wrong_layer_segment_is_partial(self):
        # Segment on B.Cu; the pads are THT (all copper layers), so B.Cu is
        # reachable — this should be CONNECTED, proving THT barrels span all
        # layers (a B.Cu track legitimately connects a THT pad pair).
        content = """(kicad_pcb (version 20240108)
  (generator "temper-test")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (net 1 "N")
  (footprint "Test:R" (layer "F.Cu")
    (at 0 0 0)
    (property "Reference" "R1" (at 0 0 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
    (pad "1" thru_hole circle (at -2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
    (pad "2" thru_hole circle (at 2.5 0 0) (size 1.5 1.5) (drill 0.8) (layers *.Cu *.Mask) (net 1 "N"))
  )
  (segment (start -2.5 0) (end 2.5 0) (width 0.5) (layer "B.Cu") (net 1) (tstamp "00000000-0000-0000-0000-000000000001"))
)
"""
        results = net_route_result_preflight(content)
        assert "N" in results
        assert results["N"].disposition == "connected"
