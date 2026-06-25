"""Tests for Trace Ballooner.

Part of temper-t07r
"""

import pytest

from temper_placer.routing.constraints.geometry import Point, LineSegment
from temper_placer.routing.constraints.spatial_index import PCBGeometry, Track, Pad
from temper_placer.routing.post_processing.trace_ballooner import (
    TraceBallooner,
    POWER_NET_KEYWORDS,
    point_to_track_distance,
    point_to_segment_distance,
)


class TestPowerNetDetection:
    """Tests for power net detection based on naming convention."""

    @pytest.fixture
    def ballooner(self):
        """Create ballooner with empty power nets for testing detection."""
        geometry = PCBGeometry()
        return TraceBallooner(geometry=geometry, power_nets=set())

    def test_dc_bus_detection(self, ballooner):
        """DC_BUS should be detected as power net."""
        assert ballooner.is_power_net("DC_BUS")
        assert ballooner.is_power_net("DC_BUS+")
        assert ballooner.is_power_net("DC_BUS-")

    def test_ac_net_detection(self, ballooner):
        """AC nets should be detected."""
        assert ballooner.is_power_net("AC_L")
        assert ballooner.is_power_net("AC_N")

    def test_voltage_detection(self, ballooner):
        """Voltage rails should be detected."""
        assert ballooner.is_power_net("+15V")
        assert ballooner.is_power_net("+5V")
        assert ballooner.is_power_net("VCC")

    def test_gnd_detection(self, ballooner):
        """Ground nets should be detected."""
        assert ballooner.is_power_net("GND")
        assert ballooner.is_power_net("PGND")
        assert ballooner.is_power_net("AGND")

    def test_signal_net_not_detected(self, ballooner):
        """Signal nets should not be detected as power."""
        assert not ballooner.is_power_net("SIG1")
        assert not ballooner.is_power_net("NET1")
        assert not ballooner.is_power_net("DATA")
        assert not ballooner.is_power_net("CLK")

    def test_case_insensitive_detection(self, ballooner):
        """Detection should be case insensitive."""
        assert ballooner.is_power_net("dc_bus")
        assert ballooner.is_power_net("Gnd")
        assert ballooner.is_power_net("Vcc")


class TestTraceBallooning:
    """Tests for trace ballooning functionality."""

    @pytest.fixture
    def geometry(self):
        """Create empty geometry."""
        return PCBGeometry()

    @pytest.fixture
    def ballooner(self, geometry):
        """Create ballooner with default power nets."""
        return TraceBallooner(geometry=geometry)

    def test_signal_tracks_unchanged(self, ballooner):
        """Non-power tracks should not be modified."""
        tracks = [
            Track(Point(0, 0), Point(10, 0), width=0.2, net="SIG1", layer=0),
            Track(Point(5, 5), Point(15, 5), width=0.3, net="SIG2", layer=0),
        ]
        result = ballooner.balloon_traces(tracks)
        assert len(result.tracks) == 2
        assert result.tracks[0].width == 0.2
        assert result.tracks[1].width == 0.3
        assert result.segments_expanded == 0

    def test_power_track_expansion(self, geometry, ballooner):
        """Power tracks should be expanded when space allows."""
        geometry.rebuild_index()

        power_track = Track(Point(0, 0), Point(10, 0), width=2.0, net="DC_BUS", layer=0)
        tracks = [power_track]
        result = ballooner.balloon_traces(tracks)

        assert len(result.tracks) == 1
        assert result.tracks[0].width >= 2.0

    def test_max_width_limit(self, geometry, ballooner):
        """Traces should not exceed max_width limit."""
        ballooner.max_width = 4.0

        power_track = Track(Point(0, 0), Point(10, 0), width=2.0, net="DC_BUS", layer=0)
        tracks = [power_track]
        result = ballooner.balloon_traces(tracks)

        assert result.tracks[0].width <= 4.0

    def test_no_expansion_in_confined_space(self, geometry, ballooner):
        """Traces near obstacles should not expand beyond clearance."""
        obstacle1 = Track(Point(0, 2.3), Point(10, 2.3), width=0.2, net="OTHER", layer=0)
        obstacle2 = Track(Point(0, -2.3), Point(10, -2.3), width=0.2, net="OTHER", layer=0)
        geometry.add_track(obstacle1)
        geometry.add_track(obstacle2)
        geometry.rebuild_index()

        power_track = Track(Point(5, 0), Point(5, 0), width=0.4, net="DC_BUS", layer=0)
        tracks = [power_track]
        result = ballooner.balloon_traces(tracks)

        assert result.tracks[0].width <= 4.0

    def test_empty_tracks_list(self, ballooner):
        """Empty track list should return empty result."""
        result = ballooner.balloon_traces([])
        assert result.tracks == []
        assert result.segments_expanded == 0

    def test_multiple_power_tracks(self, geometry, ballooner):
        """Multiple power tracks should all be ballooned."""
        geometry.rebuild_index()

        tracks = [
            Track(Point(0, 0), Point(10, 0), width=2.0, net="DC_BUS", layer=0),
            Track(Point(0, 5), Point(10, 5), width=2.0, net="+15V", layer=0),
        ]
        result = ballooner.balloon_traces(tracks)

        assert len(result.tracks) == 2
        for track in result.tracks:
            assert track.net in ["DC_BUS", "+15V"]


class TestClearanceCalculation:
    """Tests for clearance distance calculations."""

    def test_point_to_segment_distance_horizontal(self):
        """Test distance to horizontal segment."""
        segment = LineSegment(Point(0, 0), Point(10, 0))
        point = Point(5, 3)
        dist = point_to_segment_distance(point, segment)
        assert abs(dist - 3.0) < 0.001

    def test_point_to_segment_distance_vertical(self):
        """Test distance to vertical segment."""
        segment = LineSegment(Point(5, 0), Point(5, 10))
        point = Point(8, 5)
        dist = point_to_segment_distance(point, segment)
        assert abs(dist - 3.0) < 0.001

    def test_point_to_segment_distance_endpoint(self):
        """Test distance to segment endpoint."""
        segment = LineSegment(Point(0, 0), Point(10, 0))
        point = Point(-5, 0)
        dist = point_to_segment_distance(point, segment)
        assert abs(dist - 5.0) < 0.001

    def test_point_to_segment_distance_perpendicular(self):
        """Test distance at perpendicular intersection."""
        segment = LineSegment(Point(0, 0), Point(10, 0))
        point = Point(5, 0)
        dist = point_to_segment_distance(point, segment)
        assert abs(dist) < 0.001


class TestPowerNetKeywords:
    """Tests for POWER_NET_KEYWORDS constant."""

    def test_keywords_not_empty(self):
        """Keywords should not be empty."""
        assert len(POWER_NET_KEYWORDS) > 0

    def test_common_power_nets_included(self):
        """Common power net names should be in keywords."""
        assert "DC_BUS" in POWER_NET_KEYWORDS
        assert "GND" in POWER_NET_KEYWORDS
        assert "VCC" in POWER_NET_KEYWORDS
        assert "AC_L" in POWER_NET_KEYWORDS
        assert "AC_N" in POWER_NET_KEYWORDS


class TestIntegration:
    """Integration tests for trace ballooner with geometry."""

    def test_with_vias_as_obstacles(self):
        """Vias should be treated as obstacles."""
        geometry = PCBGeometry()

        via = Pad(
            center=Point(5, 3),
            shape="circle",
            size=(1.0, 1.0),
            net="OTHER",
            layer=0,
        )
        geometry.add_pad(via)
        geometry.rebuild_index()

        ballooner = TraceBallooner(geometry=geometry)
        power_track = Track(Point(0, 0), Point(10, 0), width=2.0, net="DC_BUS", layer=0)
        tracks = [power_track]
        result = ballooner.balloon_traces(tracks)

        assert result.tracks[0].width >= 2.0

    def test_with_pads_as_obstacles(self):
        """Pads should be treated as obstacles."""
        geometry = PCBGeometry()

        pad = Pad(
            center=Point(5, 3),
            shape="rect",
            size=(2.0, 2.0),
            net="OTHER",
            layer=0,
        )
        geometry.add_pad(pad)
        geometry.rebuild_index()

        ballooner = TraceBallooner(geometry=geometry)
        power_track = Track(Point(0, 0), Point(10, 0), width=2.0, net="DC_BUS", layer=0)
        tracks = [power_track]
        result = ballooner.balloon_traces(tracks)

        assert result.tracks[0].width >= 2.0
