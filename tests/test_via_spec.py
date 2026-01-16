"""
Test suite for Via specifications and clearance model.

TDD Approach:
1. Write tests for expected behavior
2. Implement minimal code to pass
3. Refactor
4. Repeat
"""

import pytest
from temper_placer.router_v6.via_model import ViaSpec, ViaType


class TestViaSpec:
    """Test via specifications and clearance calculations"""
    
    def test_standard_via_dimensions(self):
        """Standard via should have sensible dimensions"""
        via = ViaSpec.standard()
        
        assert via.diameter == 0.8  # mm
        assert via.drill == 0.4  # mm
        assert via.clearance == 0.2  # mm
        assert via.type == ViaType.THROUGH_HOLE
    
    def test_via_keepout_radius(self):
        """Keepout radius should be diameter/2 + clearance + margin"""
        via = ViaSpec.standard()
        
        # keepout = (0.8/2) + 0.2 + 0.1 = 0.7mm
        assert via.keepout_radius == pytest.approx(0.7, abs=0.01)
    
    def test_min_via_spacing(self):
        """Minimum via-to-via spacing should be 2x keepout radius"""
        via = ViaSpec.standard()
        
        # min_spacing = 2 * 0.7 = 1.4mm
        assert via.min_spacing == pytest.approx(1.4, abs=0.01)
    
    def test_microvia_smaller_than_standard(self):
        """Microvia should have smaller dimensions"""
        standard = ViaSpec.standard()
        micro = ViaSpec.microvia()
        
        assert micro.diameter < standard.diameter
        assert micro.drill < standard.drill
        assert micro.keepout_radius < standard.keepout_radius
    
    def test_via_area(self):
        """Via annular ring area calculation"""
        via = ViaSpec.standard()
        
        # Area = π * (diameter/2)^2 - π * (drill/2)^2
        # = π * (0.4^2 - 0.2^2) = π * 0.12
        expected_area = 3.14159 * 0.12
        assert via.annular_area == pytest.approx(expected_area, rel=0.01)
    
    def test_via_hole_overlaps(self):
        """Test if via holes would overlap"""
        via1 = ViaSpec.standard()
        via2 = ViaSpec.standard()
        
        # Same position - definitely overlaps
        assert via1.holes_overlap((0, 0), (0, 0), via2)
        
        # 0.3mm apart - holes overlap (drill=0.4mm, so radius=0.2mm each)
        assert via1.holes_overlap((0, 0), (0.3, 0), via2)
        
        # 0.5mm apart - holes don't overlap
        assert not via1.holes_overlap((0, 0), (0.5, 0), via2)
    
    def test_via_keepouts_overlap(self):
        """Test if via keepout zones would overlap"""
        via1 = ViaSpec.standard()
        via2 = ViaSpec.standard()
        
        # 1.0mm apart - keepouts overlap (keepout_radius=0.7mm each)
        assert via1.keepouts_overlap((0, 0), (1.0, 0), via2)
        
        # 1.5mm apart - keepouts don't overlap
        assert not via1.keepouts_overlap((0, 0), (1.5, 0), via2)


class TestViaType:
    """Test via type enumeration"""
    
    def test_via_types_defined(self):
        """All via types should be defined"""
        assert ViaType.THROUGH_HOLE is not None
        assert ViaType.BLIND is not None
        assert ViaType.BURIED is not None
        assert ViaType.MICROVIA is not None
    
    def test_via_type_layer_span(self):
        """Different via types span different layers"""
        # Through-hole: all layers
        assert ViaType.THROUGH_HOLE.spans_all_layers()
        
        # Blind: surface to inner
        assert not ViaType.BLIND.spans_all_layers()
        
        # Buried: inner to inner only
        assert not ViaType.BURIED.spans_all_layers()


class TestViaPlacement:
    """Test via placement legality checking"""
    
    def test_via_too_close_to_pad(self):
        """Via should not be placeable too close to existing pad"""
        from temper_placer.router_v6.via_model import can_place_via
        from shapely.geometry import Point
        
        via_spec = ViaSpec.standard()
        
        # Pad at origin with 0.4mm radius
        pad = Point(0, 0).buffer(0.4)
        obstacles = [pad]
        
        # Try to place via 0.5mm away - too close
        # (pad edge at 0.4mm + via keepout 0.7mm = need 1.1mm clearance)
        assert not can_place_via((0.5, 0), via_spec, obstacles)
        
        # 1.0mm away - still too close
        assert not can_place_via((1.0, 0), via_spec, obstacles)
        
        # 1.2mm away - legal
        assert can_place_via((1.2, 0), via_spec, obstacles)
    
    def test_via_too_close_to_via(self):
        """Via should not be placeable too close to another via"""
        from temper_placer.router_v6.via_model import can_place_via
        from shapely.geometry import Point
        
        via_spec = ViaSpec.standard()
        
        # Existing via at origin
        via_keepout = Point(0, 0).buffer(via_spec.keepout_radius)
        obstacles = [via_keepout]
        
        # Try to place via 1.0mm away - too close (need 1.4mm)
        assert not can_place_via((1.0, 0), via_spec, obstacles)
        
        # 1.5mm away - legal
        assert can_place_via((1.5, 0), via_spec, obstacles)


class TestViaInBoard:
    """Test via placement within board boundaries"""
    
    def test_via_outside_board(self):
        """Via should not be placeable outside board area"""
        from temper_placer.router_v6.via_model import ViaSpec
        from shapely.geometry import box
        
        via_spec = ViaSpec.standard()
        board_area = box(0, 0, 100, 100)  # 100x100mm board
        
        # Via at (50, 50) - inside board
        assert via_spec.is_within_bounds((50, 50), board_area)
        
        # Via at (-1, 50) - outside board
        assert not via_spec.is_within_bounds((-1, 50), board_area)
        
        # Via at (0.3, 0.3) - too close to edge (keepout_radius=0.7mm)
        assert not via_spec.is_within_bounds((0.3, 0.3), board_area)
        
        # Via at (1.0, 1.0) - legal distance from edge
        assert via_spec.is_within_bounds((1.0, 1.0), board_area)
