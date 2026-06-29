from unittest.mock import MagicMock

from temper_placer.io.kicad_parser import _extract_board_geometry


class Pt:
    def __init__(self, x, y):
        self.X = x
        self.Y = y

def test_zone_parsing_l_shape_warning():
    mock_board = MagicMock()
    mock_board.graphicItems = []
    mock_board.footprints = []

    # Define an L-shaped zone
    # Bounds: 0,0 to 100,100 (area 10000)
    # Polygon: (0,0), (100,0), (100,20), (20,20), (20,100), (0,100)
    # Area = 100*20 + 20*80 = 2000 + 1600 = 3600
    # Bbox area = 10000
    # Mismatch = (10000 - 3600) / 10000 = 0.64 > 0.05 -> Warning!

    mock_poly = MagicMock()

    points = [Pt(0,0), Pt(100,0), Pt(100,20), Pt(20,20), Pt(20,100), Pt(0,100)]
    mock_poly.points = points # Newer kiutils
    mock_poly.pts = points # Older kiutils backup

    mock_zone = MagicMock()
    mock_zone.polygons = [mock_poly]
    mock_zone.name = "L_Zone"
    mock_zone.netName = "GND"

    mock_board.zones = [mock_zone]

    # We also need edge cuts for the board bounds to work
    edge_cut = MagicMock()
    edge_cut.layer = "Edge.Cuts"
    edge_cut.start = Pt(0,0)
    edge_cut.end = Pt(200,200) # Big board
    mock_board.graphicItems = [edge_cut]

    warnings = []
    board = _extract_board_geometry(mock_board, warnings)

    assert len(board.zones) == 1
    zone = board.zones[0]
    assert zone.name == "L_Zone"
    # Check if warning was generated
    assert any("Approximating polygon" in w for w in warnings)
    assert any("L_Zone" in w for w in warnings)

    # Check that polygon attribute is populated
    assert zone.polygon is not None
    assert len(zone.polygon) == 6

def test_zone_parsing_rectangular_no_warning():
    mock_board = MagicMock()
    mock_board.graphicItems = []
    mock_board.footprints = []

    # Rectangular zone

    points = [Pt(0,0), Pt(100,0), Pt(100,100), Pt(0,100)]
    mock_poly = MagicMock()
    mock_poly.points = points
    mock_poly.pts = points

    mock_zone = MagicMock()
    mock_zone.polygons = [mock_poly]
    mock_zone.name = "Rect_Zone"
    mock_zone.netName = "GND"

    mock_board.zones = [mock_zone]

    edge_cut = MagicMock()
    edge_cut.layer = "Edge.Cuts"
    edge_cut.start = Pt(0,0)
    edge_cut.end = Pt(200,200)
    mock_board.graphicItems = [edge_cut]

    warnings = []
    board = _extract_board_geometry(mock_board, warnings)

    assert len(board.zones) == 1
    # Should be no warnings about approximation
    assert not any("Approximating polygon" in w for w in warnings)
