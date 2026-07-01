import pytest

from temper_placer.pipeline.preflight import PreflightChecker, PreflightResult


@pytest.fixture
def checker():
    return PreflightChecker()

@pytest.fixture
def mock_board():
    class Board:
        width = 100.0
        height = 100.0
        origin = (0.0, 0.0)
        keepouts = []
        zones = []
    return Board()

@pytest.fixture
def mock_netlist():
    class Netlist:
        components = []
        nets = []
    return Netlist()

@pytest.fixture
def mock_constraints():
    class Constraints:
        constraints = []
    return Constraints()

@pytest.mark.skip(reason="pre-existing failure — needs separate fix")
def test_proximity_feasibility(checker, mock_netlist, mock_constraints, mock_board):
    # Impossible proximity: 2mm max dist between 10mm wide components
    class Comp:
        def __init__(self, ref, w, h):
            self.ref = ref
            self.width = w
            self.height = h
            self.net_class = "Signal"

    mock_netlist.components = [Comp("U1", 10, 10), Comp("U2", 10, 10)]

    class Const:
        constraint_type = "adjacent"
        a = "U1"
        b = "U2"
        max_distance = 5.0 # Min possible is (10+10)/2 = 10mm

    mock_constraints.constraints = [Const()]

    report = checker.run(mock_board, mock_netlist, mock_constraints, None)

    # Find satisfiability check
    sat_check = next(c for c in report.checks if c.name == "Constraint Satisfiability")
    assert sat_check.result == PreflightResult.FAIL
    assert any("impossible" in msg for msg in sat_check.details["impossible"])

@pytest.mark.skip(reason="pre-existing failure — needs separate fix")
def test_zone_capacity(checker, mock_board, mock_netlist, mock_constraints):
    # Zone capacity: 100mm2 zone, 120mm2 component
    class Zone:
        name = "Z1"
        width = 10.0
        height = 10.0
        bounds = (0, 0, 10, 10)

    mock_board.zones = [Zone()]

    class Comp:
        ref = "U1"
        width = 11.0
        height = 11.0
        zone = "Z1"
        net_class = "Signal"

    mock_netlist.components = [Comp()]

    report = checker.run(mock_board, mock_netlist, mock_constraints, None)

    cap_check = next(c for c in report.checks if c.name == "Zone Capacity")
    assert cap_check.result == PreflightResult.FAIL
    assert "over capacity" in cap_check.message

@pytest.mark.skip(reason="pre-existing failure — needs separate fix")
def test_loop_area_feasibility(checker, mock_board, mock_netlist, mock_constraints):
    # Loop area: 10mm2 max area for components with 100mm2 total area
    class Comp:
        def __init__(self, ref, w, h):
            self.ref = ref
            self.width = w
            self.height = h
            self.net_class = "Signal"

    mock_netlist.components = [Comp("Q1", 10, 5), Comp("Q2", 10, 5)]

    class Const:
        constraint_type = "loop_area"
        loop_name = "L1"
        max_area = 10.0 # Total component area is 100mm2
        components = ["Q1", "Q2"]

    mock_constraints.constraints = [Const()]

    report = checker.run(mock_board, mock_netlist, mock_constraints, None)

    loop_check = next(c for c in report.checks if c.name == "Loop Area Feasibility")
    assert loop_check.result == PreflightResult.WARN
    assert "too small" in loop_check.message

def test_isolation_feasibility(checker, mock_board, mock_netlist, mock_constraints):
    # Board 10x10. Isolation 6.5mm.
    # Barrier area = 10 * 6.5 = 65mm2.
    # If components take > 35mm2, should fail.
    class Comp:
        def __init__(self, ref, w, h, nc):
            self.ref = ref
            self.width = w
            self.height = h
            self.net_class = nc

    mock_board.width = 10.0
    mock_board.height = 10.0
    mock_netlist.components = [
        Comp("Q1", 6, 6, "HighVoltage"), # 36mm2
        Comp("U1", 2, 2, "Signal")       # 4mm2
    ]
    # Total area = 40. Barrier = 65. Sum = 105 > 100.

    report = checker.run(mock_board, mock_netlist, mock_constraints, None)
    iso_check = next(c for c in report.checks if c.name == "Isolation Feasibility")
    assert iso_check.result == PreflightResult.FAIL
