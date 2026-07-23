"""U1: zone emission primitive — tests."""

from __future__ import annotations

from temper_placer.router_v6.zone_emission import (
    _bounding_box,
    _cluster_positions,
    compute_zone_for_net,
    compute_zones_for_net,
    emit_zone_s_expr,
)


def test_compute_zone_for_two_pads():
    zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
    assert zd.net_name == "GND"
    assert zd.net_number == 1
    assert zd.layer == "F.Cu"
    assert len(zd.points) >= 3  # polygon hull points


def test_compute_zone_for_empty_pads_raises():
    import pytest

    with pytest.raises(ValueError):
        compute_zone_for_net("EMPTY", 1, [])


def test_emit_zone_s_expr_contains_zone_keyword():
    zd = compute_zone_for_net("+3V3", 5, [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0)])
    expr = emit_zone_s_expr(zd)
    assert "(zone " in expr
    assert '(net_name "+3V3")' in expr
    assert "(net 5)" in expr
    assert "(layer " in expr
    assert "(polygon " in expr


def test_pwr_rtn_gets_bcu_layer():
    zd = compute_zone_for_net("PWR_RTN", 1, [(0.0, 0.0), (10.0, 0.0)], layer="B.Cu")
    assert zd.layer == "B.Cu"


def test_emit_zone_s_expr_includes_fill_directive():
    zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
    expr = emit_zone_s_expr(zd)
    assert "(fill yes" in expr


class TestZonePriority:
    """U2: KiCad-native zone priority field and s-expression emission."""

    def test_zone_definition_has_priority_field(self):
        zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
        assert hasattr(zd, "priority")
        assert zd.priority == 0

    def test_emit_zone_s_expr_includes_priority(self):
        zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
        expr = emit_zone_s_expr(zd)
        assert "(priority " in expr

    def test_priority_between_hatch_and_connect_pads(self):
        zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
        expr = emit_zone_s_expr(zd)
        hatch_pos = expr.index("(hatch ")
        priority_pos = expr.index("(priority ")
        connect_pos = expr.index("(connect_pads ")
        assert hatch_pos < priority_pos < connect_pos

    def test_acmains_higher_priority_than_signal(self):
        """ACMains (dru=10) -> KiCad 80 > Signal (dru=80) -> KiCad 10."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        ac = TEMPER_NET_CLASSES["ACMains"].dru_priority  # 10
        sig = TEMPER_NET_CLASSES["Signal"].dru_priority  # 80
        assert 90 - ac > 90 - sig


class TestDataInformedClustering:
    """U1: data-informed spatial clustering via scipy hierarchical linkage."""

    def test_tight_cluster_produces_single_group(self):
        """Pads within ~2mm → one cluster (data-informed threshold finds no
        significant NN-distance gap)."""
        pads = [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]
        zones = compute_zones_for_net("VCC", 1, pads, margin=1.0, cluster=True)
        assert len(zones) == 1

    def test_two_widely_separated_groups_produce_two_clusters(self):
        """Two dense groups ~50mm apart → two clusters."""
        pads = [
            (0.0, 0.0),
            (1.0, 0.0),
            (0.5, 1.0),  # group A
            (50.0, 0.0),
            (51.0, 0.0),
            (50.5, 1.0),  # group B
        ]
        zones = compute_zones_for_net("VCC", 1, pads, margin=1.0, cluster=True)
        assert len(zones) == 2

    def test_single_pad_is_single_cluster(self):
        pads = [(50.0, 50.0)]
        zones = compute_zones_for_net("SOLO", 1, pads, margin=1.0, cluster=True)
        assert len(zones) == 1
        assert len(zones[0].points) >= 3

    def test_cluster_false_produces_single_hull(self):
        """cluster=False gives one hull over all pads regardless of spacing."""
        pads = [(0.0, 0.0), (100.0, 0.0)]
        zones = compute_zones_for_net("GND", 1, pads, margin=1.0, cluster=False)
        assert len(zones) == 1

    def test_empty_pads_compute_zones_raises(self):
        import pytest

        with pytest.raises(ValueError):
            compute_zones_for_net("EMPTY", 1, [])

    def test_cluster_positions_single_cluster_at_adjacent_pitch(self):
        """NN-distance threshold finds no gap for pads at typical intra-component spacing."""
        pads = [(0.0, 0.0), (1.27, 0.0), (2.54, 0.0)]  # 50-mil pitch SOIC
        clusters = _cluster_positions(pads)
        assert len(clusters) == 1

    def test_bounding_box_still_available_as_fallback(self):
        bb = _bounding_box([(0.0, 0.0), (10.0, 0.0)], margin=1.0)
        assert len(bb) == 4
        assert bb[0] == (-1.0, -1.0)
        assert bb[1] == (11.0, -1.0)
