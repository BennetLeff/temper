"""Tests for core.board module."""


from temper_placer.core.board import (
    GroundDomain,
    LayerStackup,
    MountingHole,
    Zone,
)


class TestZone:
    """Tests for Zone dataclass."""

    def test_basic_zone(self):
        """Test basic zone properties."""
        zone = Zone("HV_ZONE", (0, 0, 50, 80))
        assert zone.name == "HV_ZONE"
        assert zone.width == 50.0
        assert zone.height == 80.0
        assert zone.area == 4000.0
        assert zone.center == (25.0, 40.0)

    def test_contains_point(self):
        """Test point containment."""
        zone = Zone("TEST", (10, 20, 30, 40))
        assert zone.contains_point(20.0, 30.0)  # Inside
        assert zone.contains_point(10.0, 20.0)  # On corner
        assert not zone.contains_point(5.0, 30.0)  # Outside left
        assert not zone.contains_point(35.0, 30.0)  # Outside right


class TestLayerStackup:
    """Tests for LayerStackup dataclass."""

    def test_default_4layer(self):
        """Test default 4-layer stackup."""
        stackup = LayerStackup.default_4layer()
        assert len(stackup.layers) == 4
        assert stackup.thickness == 1.6

        # Check layer properties
        assert stackup.layers[0].name == "F.Cu"
        assert stackup.layers[0].copper_weight == 2.0
        assert stackup.layers[0].is_routable

        assert stackup.layers[1].name == "In1.Cu"
        assert not stackup.layers[1].is_routable  # GND plane

    def test_routable_layers_hv(self):
        """Test routable layers for high voltage."""
        stackup = LayerStackup.default_4layer()
        layers = stackup.routable_layers("HighVoltage")
        assert layers == [0]  # Only L1 for HV

    def test_routable_layers_signal(self):
        """Test routable layers for signal."""
        stackup = LayerStackup.default_4layer()
        layers = stackup.routable_layers("Signal")
        assert layers == [0, 3]  # L1 and L4

    def test_tracks_per_cell(self):
        """Test routing capacity estimation."""
        stackup = LayerStackup.default_4layer()

        # HV has wide traces with large clearance
        hv_tracks = stackup.tracks_per_cell(1.0, "HighVoltage")
        assert hv_tracks < 1.0  # Less than 1 track per mm

        # Signal has thin traces
        sig_tracks = stackup.tracks_per_cell(1.0, "Signal")
        assert sig_tracks > hv_tracks  # More tracks fit


class TestBoard:
    """Tests for Board dataclass."""

    def test_simple_board(self, simple_board):
        """Test simple board properties."""
        assert simple_board.width == 100.0
        assert simple_board.height == 100.0
        assert simple_board.area == 10000.0
        assert len(simple_board.zones) == 2

    def test_temper_default(self, temper_board):
        """Test default Temper board."""
        assert temper_board.width == 100.0
        assert temper_board.height == 150.0
        assert len(temper_board.zones) == 4
        assert len(temper_board.mounting_holes) == 4
        assert len(temper_board.ground_domains) == 2

    def test_get_zone(self, temper_board):
        """Test getting zone by name."""
        hv_zone = temper_board.get_zone("HV_ZONE")
        assert hv_zone.name == "HV_ZONE"
        assert hv_zone.bounds == (0, 0, 50, 80)

    def test_get_zone_for_point(self, temper_board):
        """Test finding zone containing a point."""
        zone = temper_board.get_zone_for_point(25.0, 40.0)
        assert zone is not None
        assert zone.name == "HV_ZONE"

        zone = temper_board.get_zone_for_point(75.0, 120.0)
        assert zone is not None
        assert zone.name == "MCU_ZONE"

    def test_get_ground_domain(self, temper_board):
        """Test finding ground domain for a point."""
        domain = temper_board.get_ground_domain(25.0, 40.0)
        assert domain is not None
        assert domain.name == "PGND"

        domain = temper_board.get_ground_domain(75.0, 50.0)
        assert domain is not None
        assert domain.name == "CGND"

    def test_contains_point(self, simple_board):
        """Test board boundary checking."""
        assert simple_board.contains_point(50.0, 50.0)
        assert simple_board.contains_point(0.0, 0.0)
        assert simple_board.contains_point(100.0, 100.0)
        assert not simple_board.contains_point(-1.0, 50.0)
        assert not simple_board.contains_point(50.0, 101.0)

    def test_contains_point_non_zero_origin(self):
        """Test board boundary checking with non-zero origin."""
        from temper_placer.core.board import Board
        board = Board(width=50.0, height=50.0, origin=(100.0, 100.0))
        # (25, 25) is relative position, should be inside
        assert board.contains_point(25.0, 25.0)
        # (125, 125) is absolute position, should be outside relative bounds [0, 50]
        assert not board.contains_point(125.0, 125.0)

    def test_point_in_keepout(self, temper_board):
        """Test keepout region checking."""
        # Point near mounting hole (5, 5) should be in keepout
        assert temper_board.point_in_keepout(5.0, 5.0)
        assert temper_board.point_in_keepout(7.0, 5.0)  # Within 5mm radius

        # Point far from holes should not be in keepout
        assert not temper_board.point_in_keepout(50.0, 75.0)

    def test_get_bounds_array(self, temper_board):
        """Test getting bounds as JAX array."""
        bounds = temper_board.get_bounds_array()
        assert bounds.shape == (4,)
        assert float(bounds[0]) == 0.0  # x_min
        assert float(bounds[1]) == 0.0  # y_min
        assert float(bounds[2]) == 100.0  # x_max
        assert float(bounds[3]) == 150.0  # y_max


class TestMountingHole:
    """Tests for MountingHole dataclass."""

    def test_basic_hole(self):
        """Test basic mounting hole."""
        hole = MountingHole((10.0, 10.0), 3.2, keepout_radius=5.0)
        assert hole.position == (10.0, 10.0)
        assert hole.diameter == 3.2
        assert hole.keepout_radius == 5.0

    def test_default_keepout(self):
        """Test default keepout radius."""
        hole = MountingHole((0.0, 0.0), 3.0)
        assert hole.keepout_radius == 3.0


class TestGroundDomain:
    """Tests for GroundDomain dataclass."""

    def test_basic_domain(self):
        """Test basic ground domain."""
        domain = GroundDomain("PGND", (0, 0, 50, 80))
        assert domain.name == "PGND"
        assert domain.contains_point(25.0, 40.0)
        assert not domain.contains_point(60.0, 40.0)

    def test_domain_with_star_point(self):
        """Test ground domain with star point."""
        domain = GroundDomain("CGND", (50, 0, 100, 150), star_point=(50, 40))
        assert domain.star_point == (50, 40)
