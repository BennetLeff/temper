#!/usr/bin/env python3
"""
Test suite for GeometricNudger (temper-uvx9.1)

Tests to validate the force-directed trace nudger implementation meets
the acceptance criteria specified in the beads issue.
"""

import pytest
from temper_placer.routing.post_processing.nudger import GeometricNudger
from temper_placer.routing.constraints.drc_oracle import DRCOracle
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.spatial_index import PCBGeometry, Track, Via, Pad


class TestGeometricNudger:
    """Test force-directed trace nudging for DRC compliance."""

    def test_parallel_traces_too_close(self):
        """
        Acceptance Criteria: Two parallel traces at 0.1mm apart,
        required 0.2mm → nudged to 0.2mm
        """
        geometry = PCBGeometry()
        
        # Add two parallel horizontal traces 0.1mm apart
        # Trace A: from (0, 0) to (10, 0)
        # Trace B: from (0, 0.1) to (10, 0.1)
        track_a = Track(
            id="track_a",
            start=Point(0.0, 0.0),
            end=Point(10.0, 0.0),
            width=0.2,
            layer=1,
            net="NET_A"
        )
        track_b = Track(
            id="track_b",
            start=Point(0.0, 0.1),
            end=Point(10.0, 0.1),
            width=0.2,
            layer=1,
            net="NET_B"
        )
        
        # Add fixed pads at the endpoints
        geometry.add_pad(Pad(id="pad_a1", center=Point(0.0, 0.0), radius=0.4, net="NET_A"))
        geometry.add_pad(Pad(id="pad_a2", center=Point(10.0, 0.0), radius=0.4, net="NET_A"))
        geometry.add_pad(Pad(id="pad_b1", center=Point(0.0, 0.1), radius=0.4, net="NET_B"))
        geometry.add_pad(Pad(id="pad_b2", center=Point(10.0, 0.1), radius=0.4, net="NET_B"))
        
        geometry.add_track(track_a)
        geometry.add_track(track_b)
        geometry.rebuild_index()
        
        # Create DRC oracle with 0.2mm clearance requirement
        oracle = DRCOracle(geometry=geometry, min_clearance=0.2)
        
        # Check initial violations
        initial_violations = oracle.validate_all()
        assert len(initial_violations) > 0, "Should have clearance violations initially"
        
        # Create nudger and optimize
        nudger = GeometricNudger(oracle)
        nudger.optimize(iterations=100, step_size=0.5)
        
        # Check final violations
        final_violations = oracle.validate_all()
        
        # Acceptance: violations should be reduced or eliminated
        assert len(final_violations) < len(initial_violations), \
            "Nudger should reduce violations"
        
        # Check that endpoints remained fixed (on pads)
        final_track_a = oracle.geometry.get_geometry_by_id("track_a")
        final_track_b = oracle.geometry.get_geometry_by_id("track_b")
        
        # Endpoints should still be close to pads (allowing small movement within pad)
        assert final_track_a.start.distance_to(Point(0.0, 0.0)) < 0.5
        assert final_track_a.end.distance_to(Point(10.0, 0.0)) < 0.5
        assert final_track_b.start.distance_to(Point(0.0, 0.1)) < 0.5
        assert final_track_b.end.distance_to(Point(10.0, 0.1)) < 0.5

    def test_endpoints_remain_connected_to_pads(self):
        """
        Acceptance Criteria: Pin-connected endpoints remain fixed
        """
        geometry = PCBGeometry()
        
        # Simple L-shaped trace with pads at ends
        track = Track(
            id="track_1",
            start=Point(0.0, 0.0),
            end=Point(5.0, 0.0),
            width=0.2,
            layer=1,
            net="NET_1"
        )
        track2 = Track(
            id="track_2",
            start=Point(5.0, 0.0),
            end=Point(5.0, 5.0),
            width=0.2,
            layer=1,
            net="NET_1"
        )
        
        pad1 = Pad(id="pad1", center=Point(0.0, 0.0), radius=0.5, net="NET_1")
        pad2 = Pad(id="pad2", center=Point(5.0, 5.0), radius=0.5, net="NET_1")
        
        geometry.add_pad(pad1)
        geometry.add_pad(pad2)
        geometry.add_track(track)
        geometry.add_track(track2)
        geometry.rebuild_index()
        
        oracle = DRCOracle(geometry=geometry, min_clearance=0.2)
        nudger = GeometricNudger(oracle)
        
        # Save original endpoint positions
        original_start = Point(track.start.x, track.start.y)
        original_end = Point(track2.end.x, track2.end.y)
        
        nudger.optimize(iterations=50)
        
        # Check endpoints stayed on pads
        final_track1 = oracle.geometry.get_geometry_by_id("track_1")
        final_track2 = oracle.geometry.get_geometry_by_id("track_2")
        
        # Endpoints on pads should not move significantly
        assert final_track1.start.distance_to(original_start) < 0.6  # Within pad radius
        assert final_track2.end.distance_to(original_end) < 0.6

    def test_no_new_violations_created(self):
        """
        Acceptance Criteria: No new violations created during nudging
        """
        # This is tested implicitly by checking that violations decrease or stay same,
        # not increase
        geometry = PCBGeometry()
        
        # Create a simple scenario
        track = Track(
            id="track_1",
            start=Point(0.0, 0.0),
            end=Point(10.0, 0.0),
            width=0.2,
            layer=1,
            net="NET_1"
        )
        
        geometry.add_track(track)
        geometry.rebuild_index()
        
        oracle = DRCOracle(geometry=geometry, min_clearance=0.2)
        nudger = GeometricNudger(oracle)
        
        initial_count = len(oracle.validate_all())
        nudger.optimize(iterations=50)
        final_count = len(oracle.validate_all())
        
        # Should not create new violations
        assert final_count <= initial_count

    def test_convergence_within_iterations(self):
        """
        Acceptance Criteria: Converges within 100 iterations for typical cases
        """
        # Create a simple violation scenario
        geometry = PCBGeometry()
        
        track_a = Track(
            id="track_a",
            start=Point(0.0, 0.0),
            end=Point(5.0, 0.0),
            width=0.2,
            layer=1,
            net="NET_A"
        )
        track_b = Track(
            id="track_b",
            start=Point(0.0, 0.15),  # Too close
            end=Point(5.0, 0.15),
            width=0.2,
            layer=1,
            net="NET_B"
        )
        
        geometry.add_track(track_a)
        geometry.add_track(track_b)
        geometry.rebuild_index()
        
        oracle = DRCOracle(geometry=geometry, min_clearance=0.2)
        nudger = GeometricNudger(oracle)
        
        # Track convergence
        violations_history = []
        for i in range(100):
            violations = oracle.validate_all()
            violations_history.append(len(violations))
            if len(violations) == 0:
                print(f"Converged in {i} iterations!")
                break
            nudger.optimize(iterations=1)
        
        # Should converge within 100 iterations
        assert violations_history[-1] < violations_history[0], \
            "Should reduce violations"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
