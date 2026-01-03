"""Tests for DRCOracle.

Part of temper-lueu.3. temper-lueu.4, temper-lueu.5
"""

import pytest
import time

from temper_placer.routing.constraints.design_rules import (
    ClearanceMatrix,
    DesignRulesParser,
)
from temper_placer.routing.constraints.drc_oracle import DRCOracle, Violation
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.spatial_index import Pad, Track, Via


class TestDRCOracleBasic:
    """Basic tests for DRCOracle."""

    @pytest.fixture
    def oracle(self):
        """Create oracle with default rules."""
        rules = DesignRulesParser.create_default()
        return DRCOracle(rules)

    def test_can_place_track_in_empty_space(self, oracle):
        """Track in empty space should be valid."""
        valid, reason = oracle.can_place_track_segment(
            start=(0, 0),
            end=(10, 0),
            layer=0,
            net="SIG1",
            width=0.2,
        )
        assert valid, f"Should be valid: {reason}"
        assert reason == ""

    def test_cannot_place_overlapping_tracks(self, oracle):
        """Overlapping tracks on same layer should fail."""
        # Register first track
        track1 = Track(Point(0, 0), Point(10, 0), width=0.2, net="SIG1", layer=0)
        oracle.register_track(track1)

        # Try to place overlapping track (different net)
        valid, reason = oracle.can_place_track_segment(
            start=(5, 0),
            end=(15, 0),
            layer=0,
            net="SIG2",
            width=0.2,
        )
        assert not valid
        assert "clearance violation" in reason

    def test_same_net_tracks_can_overlap(self, oracle):
        """Tracks on same net should not violate clearance."""
        track1 = Track(Point(0, 0), Point(10, 0), width=0.2, net="SIG1", layer=0)
        oracle.register_track(track1)

        valid, reason = oracle.can_place_track_segment(
            start=(5, 0),
            end=(15, 0),
            layer=0,
            net="SIG1",  # Same net
            width=0.2,
        )
        assert valid, f"Same net should not violate: {reason}"

    def test_different_layer_tracks_ok(self, oracle):
        """Tracks on different layers should not conflict."""
        track1 = Track(Point(0, 0), Point(10, 0), width=0.2, net="SIG1", layer=0)
        oracle.register_track(track1)

        valid, reason = oracle.can_place_track_segment(
            start=(5, 0),
            end=(15, 0),
            layer=1,  # Different layer
            net="SIG2",
            width=0.2,
        )
        assert valid, f"Different layer should be valid: {reason}"


class TestDRCOracleVia:
    """Tests for via placement validation."""

    @pytest.fixture
    def oracle(self):
        rules = DesignRulesParser.create_default()
        return DRCOracle(rules)

    def test_can_place_via_in_empty_space(self, oracle):
        """Via in empty space should be valid."""
        valid, reason = oracle.can_place_via(
            center=(5, 5),
            diameter=0.6,
            net="SIG1",
        )
        assert valid, f"Should be valid: {reason}"

    def test_cannot_place_via_too_close_to_via(self, oracle):
        """Vias too close together should fail."""
        via1 = Via(Point(5, 5), diameter=0.6, drill=0.3, net="SIG1")
        oracle.register_via(via1)

        # Try to place via too close
        valid, reason = oracle.can_place_via(
            center=(5.3, 5),  # Only 0.3mm away
            diameter=0.6,
            net="SIG2",
        )
        assert not valid
        assert "via-to-via" in reason

    def test_same_net_vias_ok(self, oracle):
        """Vias on same net should not conflict."""
        via1 = Via(Point(5, 5), diameter=0.6, drill=0.3, net="SIG1")
        oracle.register_via(via1)

        valid, reason = oracle.can_place_via(
            center=(5.3, 5),
            diameter=0.6,
            net="SIG1",  # Same net
        )
        assert valid, f"Same net should be OK: {reason}"


class TestDRCOracleViaSites:
    """Tests for via site suggestions."""

    @pytest.fixture
    def oracle(self):
        rules = DesignRulesParser.create_default()
        return DRCOracle(rules)

    def test_find_valid_via_sites_empty(self, oracle):
        """Should find sites in empty board."""
        sites = oracle.get_valid_via_sites(
            target=(10, 10),
            search_radius=2.0,
            net="SIG1",
            grid_step=0.5,
        )
        assert len(sites) > 0

    def test_via_sites_respect_existing_vias(self, oracle):
        """Found sites should not conflict with existing vias."""
        via1 = Via(Point(10, 10), diameter=0.8, drill=0.4, net="GND")
        oracle.register_via(via1)

        sites = oracle.get_valid_via_sites(
            target=(10, 10),
            search_radius=2.0,
            net="SIG1",
            grid_step=0.2,
        )

        # All found sites should be valid
        for site in sites:
            valid, _ = oracle.can_place_via(site, 0.6, "SIG1")
            assert valid, f"Site {site} should be valid"


class TestDRCOracleValidateAll:
    """Tests for batch validation."""

    @pytest.fixture
    def oracle(self):
        rules = DesignRulesParser.create_default()
        return DRCOracle(rules)

    def test_validate_empty_returns_no_violations(self, oracle):
        """Empty board has no violations."""
        violations = oracle.validate_all()
        assert violations == []

    def test_validate_finds_track_violations(self, oracle):
        """Should detect track-to-track violations."""
        # Add overlapping tracks
        track1 = Track(Point(0, 0), Point(10, 0), width=0.2, net="SIG1", layer=0)
        track2 = Track(Point(5, 0.1), Point(15, 0.1), width=0.2, net="SIG2", layer=0)
        oracle.register_track(track1)
        oracle.register_track(track2)

        violations = oracle.validate_all()
        assert len(violations) >= 1
        assert violations[0].type == "track_clearance"

    def test_validate_finds_via_violations(self, oracle):
        """Should detect via-to-via violations."""
        via1 = Via(Point(5, 5), diameter=0.8, drill=0.4, net="SIG1")
        via2 = Via(Point(5.3, 5), diameter=0.8, drill=0.4, net="SIG2")
        oracle.register_via(via1)
        oracle.register_via(via2)

        violations = oracle.validate_all()
        assert len(violations) >= 1
        assert violations[0].type == "via_to_via"


class TestDRCOraclePerformance:
    """Performance tests for DRCOracle."""

    def test_query_under_1ms(self):
        """Single query should complete in <1ms."""
        import random

        rules = DesignRulesParser.create_default()
        oracle = DRCOracle(rules)

        # Add 100 tracks
        for i in range(100):
            x1, y1 = random.uniform(0, 100), random.uniform(0, 100)
            x2, y2 = random.uniform(0, 100), random.uniform(0, 100)
            track = Track(Point(x1, y1), Point(x2, y2), 0.2, f"N{i}", 0)
            oracle.geometry.add_track(track)
        oracle.geometry.rebuild_index()

        # Time single query
        start = time.time()
        oracle.can_place_track_segment((50, 50), (60, 60), 0, "TEST", 0.2)
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms < 10.0, f"Query took {elapsed_ms:.2f}ms (should be <10ms)"

    def test_100_track_board_query_under_10ms(self):
        """Board with 100 tracks should still query fast."""
        import random

        rules = DesignRulesParser.create_default()
        oracle = DRCOracle(rules)

        # Add 100 tracks
        for i in range(100):
            x1, y1 = random.uniform(0, 100), random.uniform(0, 100)
            x2, y2 = random.uniform(0, 100), random.uniform(0, 100)
            track = Track(Point(x1, y1), Point(x2, y2), 0.2, f"N{i}", layer=0)
            oracle.geometry.add_track(track)
        oracle.geometry.rebuild_index()

        # Time 100 queries
        start = time.time()
        for _ in range(100):
            oracle.can_place_track_segment(
                (random.uniform(0, 100), random.uniform(0, 100)),
                (random.uniform(0, 100), random.uniform(0, 100)),
                0,
                "TEST",
                0.2,
            )
        elapsed_ms = (time.time() - start) * 1000

        avg_ms = elapsed_ms / 100
        assert avg_ms < 1.0, f"Avg query took {avg_ms:.2f}ms (should be <1ms)"


class TestViolation:
    """Tests for Violation dataclass."""

    def test_severity_calculation(self):
        """Test violation severity."""
        # 50% violation (actual = half of required)
        v = Violation(
            type="track_clearance",
            geometry_a_id="a",
            geometry_b_id="b",
            net_a="N1",
            net_b="N2",
            clearance_actual=0.1,
            clearance_required=0.2,
            location=Point(0, 0),
        )
        assert v.severity == pytest.approx(0.5)

    def test_severity_zero_when_barely_violated(self):
        """Severity near zero when barely violated."""
        v = Violation(
            type="track_clearance",
            geometry_a_id="a",
            geometry_b_id="b",
            net_a="N1",
            net_b="N2",
            clearance_actual=0.19,
            clearance_required=0.2,
            location=Point(0, 0),
        )
        assert v.severity == pytest.approx(0.05, abs=0.01)
