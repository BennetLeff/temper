"""Zone-pour stitch segments carry their net's netclass ``trace_width``.

``_stitch_isolated_pads`` emits the straight-line copper that joins a
zone-eligible net's outlying pads back to its pour.  Zone eligibility is
granted only to classes declaring ``routing_strategy plane_required`` /
``plane_preferred`` -- on this board, exactly ``ACMains`` and
``HighVoltage``.  So the hardcoded ``0.2`` this file's fix removed was, by
construction, only ever applied to mains and DC-bus copper.

Measured (docs/evidence/2026-08-13-router-netclass-trace-widths.md): after
Stage 4.4 was fixed to read the netclass table, this path was the entire
residual -- 4 undersized segments, all HighVoltage, at 6.7% of the required
3.0mm.
"""

from __future__ import annotations

import pytest

from temper_placer.router_v6._zone_pour_stitch import (
    _STITCH_FALLBACK_WIDTH_MM,
    _stitch_isolated_pads,
    _stitch_width_for_net,
    _zone_layers_for_net,
)


@pytest.mark.parametrize(
    ("net", "expected"),
    [
        ("DC_BUS_RTN", 3.0),
        ("hb.power_loop.q_high-g", 3.0),
        ("tank.c_tank1-p2", 3.0),
        ("discharge.k_dis1-nc", 3.0),
        ("SW_NODE", 3.0),
        ("ac_l", 2.5),
        ("ac_n", 2.5),
    ],
)
def test_stitch_width_comes_from_the_netclass_table(net, expected):
    assert _stitch_width_for_net(net) == pytest.approx(expected)
    # ... and is emphatically not the literal it replaced
    assert _stitch_width_for_net(net) != pytest.approx(_STITCH_FALLBACK_WIDTH_MM)


def test_classless_net_gets_the_named_floor():
    assert _stitch_width_for_net("no_such_net_anywhere") == pytest.approx(
        _STITCH_FALLBACK_WIDTH_MM
    )


def test_every_zone_eligible_net_stitches_at_its_own_class_width():
    """Anti-vacuity: the set this path can reach is non-empty, and every
    member of it needs more than the old 0.2mm literal."""
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS

    eligible = [n for n in TEMPER_NET_ASSIGNMENTS if _zone_layers_for_net(n)]
    assert eligible, "no zone-eligible nets -- this test would prove nothing"
    for net in eligible:
        assert _stitch_width_for_net(net) > _STITCH_FALLBACK_WIDTH_MM, net


def test_emitted_segment_carries_the_netclass_width():
    """End-to-end through the real emitter, not just the helper."""
    net = "DC_BUS_RTN"
    assert _zone_layers_for_net(net), "fixture net must be zone-eligible"

    # One pad far outside a small square pour -> exactly one stitch target.
    pad_positions = {net: [(0.0, 0.0), (50.0, 50.0)]}
    zone_points = {net: [((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))]}
    segments: list[str] = []

    _stitch_isolated_pads(pad_positions, segments, {net: 7}, zone_points)

    assert segments, "expected at least one stitch segment"
    for seg in segments:
        assert "(width 3.0000)" in seg, seg
        assert "(width 0.2000)" not in seg
