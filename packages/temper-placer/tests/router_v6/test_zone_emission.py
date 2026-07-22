"""U1: zone emission primitive — tests."""

from __future__ import annotations

from temper_placer.router_v6.zone_emission import (
    ZoneDefinition,
    compute_zone_for_net,
    emit_zone_s_expr,
)


def test_compute_zone_for_two_pads():
    zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
    assert zd.net_name == "GND"
    assert zd.net_number == 1
    assert zd.layer == "F.Cu"
    assert len(zd.points) >= 3  # convex hull polygon corners


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
    """Regression: without (fill yes ...), a zone is only an outline
    polygon -- KiCad DRC's connectivity check sees it as no copper at
    all. CI's kicad-cli 8.0.9 doesn't support --refill-zones, so the
    fill directive must live in the emitted geometry itself, not a CLI
    flag, to work across KiCad versions."""
    zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
    expr = emit_zone_s_expr(zd)
    assert "(fill yes" in expr


class TestZonePriority:
    """U2: KiCad-native zone priority emission."""

    def test_zone_definition_has_priority_field(self):
        zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
        assert hasattr(zd, "priority")
        assert zd.priority == 0  # default

    def test_emit_zone_s_expr_includes_priority(self):
        zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
        expr = emit_zone_s_expr(zd)
        assert "(priority " in expr

    def test_priority_positioned_between_hatch_and_connect_pads(self):
        """(priority N) must appear between (hatch ...) and (connect_pads ...)
        matching the corpus-confirmed field ordering."""
        zd = compute_zone_for_net("GND", 1, [(0.0, 0.0), (10.0, 0.0)])
        expr = emit_zone_s_expr(zd)
        hatch_pos = expr.index("(hatch ")
        priority_pos = expr.index("(priority ")
        connect_pos = expr.index("(connect_pads ")
        assert hatch_pos < priority_pos < connect_pos

    def test_acmains_has_higher_priority_than_signal(self):
        """ACMains (dru_priority=10) should invert to a higher KiCad
        priority than Signal (dru_priority=80)."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        ac_dru = TEMPER_NET_CLASSES["ACMains"].dru_priority  # 10
        sig_dru = TEMPER_NET_CLASSES["Signal"].dru_priority  # 80

        _MAX = 90
        ac_ki_prio = _MAX - ac_dru
        sig_ki_prio = _MAX - sig_dru

        assert ac_ki_prio > sig_ki_prio, (
            f"ACMains KiCad priority ({ac_ki_prio}) should be higher than "
            f"Signal ({sig_ki_prio})"
        )

    def test_non_zone_netclass_dru_priority_default(self):
        """A net not in TEMPER_NET_CLASSES gets a default priority
        rather than raising."""
        zd = ZoneDefinition(
            net_name="UNKNOWN", net_number=1, layer="F.Cu",
            points=((0, 0), (10, 0), (10, 10), (0, 10)),
        )
        assert zd.priority == 0
        expr = emit_zone_s_expr(zd)
        assert "(priority 0)" in expr


class TestClusteredHull:
    """U3: localized pour shape via clustered convex hull."""

    def test_tight_cluster_produces_small_hull(self):
        """A net whose pads are tightly clustered produces a hull
        materially smaller than the old board-wide bounding box."""
        from temper_placer.router_v6.zone_emission import (
            _bounding_box,
            compute_zones_for_net,
        )
        # Three pads in a 2mm triangle
        pads = [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0)]
        zones = compute_zones_for_net(
            "VCC", 1, pads, margin=1.0, cluster_distance=5.0,
        )
        assert len(zones) == 1  # all pads in one cluster
        hull_area = _polygon_area(zones[0].points)
        bbox_area = _polygon_area(_bounding_box(pads, margin=1.0))
        # Hull should be tighter than the axis-aligned bounding box
        assert hull_area < bbox_area, (
            f"Hull area {hull_area:.2f} should be less than "
            f"bbox area {bbox_area:.2f}"
        )

    def test_separated_clusters_produce_two_hulls(self):
        """Pads in two widely-separated groups produce two zone definitions."""
        from temper_placer.router_v6.zone_emission import compute_zones_for_net
        pads = [(0.0, 0.0), (1.0, 0.0), (100.0, 0.0), (101.0, 0.0)]
        zones = compute_zones_for_net(
            "SIG", 2, pads, margin=1.0, cluster_distance=5.0,
        )
        assert len(zones) == 2, (
            f"Expected 2 clusters for pads 100mm apart, got {len(zones)}"
        )

    def test_single_pad_produces_minimal_hull(self):
        """A single pad position does not crash and produces a sane shape."""
        from temper_placer.router_v6.zone_emission import compute_zones_for_net
        pads = [(50.0, 50.0)]
        zones = compute_zones_for_net(
            "SOLO", 3, pads, margin=1.0, cluster_distance=5.0,
        )
        assert len(zones) == 1
        assert len(zones[0].points) >= 3  # valid polygon

    def test_no_clustering_produces_one_hull(self):
        """cluster_distance=None produces a single hull over all pads."""
        from temper_placer.router_v6.zone_emission import compute_zones_for_net
        # Two groups 100mm apart, but clustering disabled
        pads = [(0.0, 0.0), (100.0, 0.0)]
        zones = compute_zones_for_net(
            "GND", 4, pads, margin=1.0, cluster_distance=None,
        )
        assert len(zones) == 1

    def test_scattered_pads_still_hull_everything(self):
        """Known limitation (R6): genuinely board-scattered pads produce
        a hull covering the span between them -- this is expected, not a
        defect.  The hull is tighter than the old bounding box but still
        covers the required area."""
        from temper_placer.router_v6.zone_emission import compute_zones_for_net
        # Pads at opposite corners of a 100mm board
        pads = [(0.0, 0.0), (100.0, 100.0)]
        zones = compute_zones_for_net(
            "PWR_RTN", 5, pads, margin=1.0, cluster_distance=None,
        )
        assert len(zones) == 1
        area = _polygon_area(zones[0].points)
        # Hull of two distant points with a 1mm margin: covers the span
        assert area > 200.0, (
            f"Hull area {area:.2f} for scattered pads should span the pad gap"
        )


class TestContinuityExemption:
    """U3: GND/ACMains/HighVoltage-class nets are exempt from clustering."""

    def test_gnd_class_not_clustered(self):
        """GND net's zone produced with no clustering produces one hull
        even when pads are widely separated."""
        from temper_placer.router_v6.zone_emission import compute_zones_for_net
        pads = [(0.0, 0.0), (1.0, 0.0), (100.0, 0.0), (101.0, 0.0)]
        # cluster_distance=None simulates the adapter's exempt behavior
        zones = compute_zones_for_net(
            "CGND", 1, pads, margin=1.0, cluster_distance=None,
        )
        assert len(zones) == 1

    def test_signal_class_is_clustered(self):
        """Signal-class net with cluster_distance set produces multiple
        zones for widely-separated pads (unlike GND above)."""
        from temper_placer.router_v6.zone_emission import compute_zones_for_net
        pads = [(0.0, 0.0), (1.0, 0.0), (100.0, 0.0), (101.0, 0.0)]
        zones = compute_zones_for_net(
            "SPI_MOSI", 2, pads, margin=1.0, cluster_distance=5.0,
        )
        assert len(zones) == 2


def _polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    """Shoelace formula for simple polygon area."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0
