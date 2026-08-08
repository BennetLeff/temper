"""Tests for validation.metrics module (PlacementMetrics)."""

from temper_placer.validation.metrics import PlacementMetrics


class TestPlacementMetrics:
    """Tests for PlacementMetrics properties and methods."""

    def test_is_valid_true(self):
        """A clean placement with no violations should be valid."""
        m = PlacementMetrics(
            overlap_count=0,
            boundary_violations=0,
            hv_lv_violations=0,
            keepout_violations=0,
        )
        assert m.is_valid is True

    def test_is_valid_overlap(self):
        m = PlacementMetrics(overlap_count=1)
        assert m.is_valid is False

    def test_is_valid_boundary(self):
        m = PlacementMetrics(boundary_violations=1)
        assert m.is_valid is False

    def test_is_valid_hv_lv(self):
        m = PlacementMetrics(hv_lv_violations=1)
        assert m.is_valid is False

    def test_is_valid_keepout(self):
        m = PlacementMetrics(keepout_violations=1)
        assert m.is_valid is False

    def test_summary_contains_key_info(self):
        m = PlacementMetrics(
            overlap_count=2,
            total_overlap_area=5.0,
            boundary_violations=1,
            total_wirelength=100.0,
            avg_net_length=10.0,
            utilization=0.5,
            computation_time_ms=42.0,
        )
        s = m.summary()
        assert "Placement Metrics" in s
        assert "Overlaps: 2" in s
        assert "Boundary violations: 1" in s
        assert "Wirelength: 100.0" in s

    def test_to_dict(self):
        m = PlacementMetrics(
            overlap_count=2,
            total_overlap_area=5.0,
            worst_overlap=3.0,
            boundary_violations=1,
            clearance_violations=4,
            min_hv_lv_clearance=10.0,
            total_wirelength=100.0,
            max_net_length=50.0,
            avg_net_length=10.0,
            max_congestion=0.8,
            avg_congestion=0.3,
            utilization=0.5,
            spread_score=0.7,
            center_of_mass=(50.0, 30.0),
            computation_time_ms=42.0,
        )
        d = m.to_dict()
        assert isinstance(d, dict)
        assert d["overlap_count"] == 2
        assert d["total_overlap_area"] == 5.0
        assert d["worst_overlap"] == 3.0
        assert d["boundary_violations"] == 1
        assert d["clearance_violations"] == 4
        assert d["min_hv_lv_clearance"] == 10.0
        assert d["total_wirelength"] == 100.0
        assert d["max_net_length"] == 50.0
        assert d["avg_net_length"] == 10.0
        assert d["utilization"] == 0.5
        assert d["spread_score"] == 0.7
        assert d["center_of_mass"] == (50.0, 30.0)
        assert d["computation_time_ms"] == 42.0

    def test_to_dict_inf_clearance(self):
        """min_hv_lv_clearance inf -> None in dict."""
        m = PlacementMetrics(min_hv_lv_clearance=float("inf"))
        d = m.to_dict()
        assert d["min_hv_lv_clearance"] is None
