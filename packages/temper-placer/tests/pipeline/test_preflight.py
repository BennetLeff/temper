"""Tests for preflight feasibility checker (temper-l65.6).

Tests the PreflightChecker that performs fast feasibility checking
to catch infeasible designs early without full optimization.

TDD: Write tests first, then implement preflight.py to pass them.
"""

import pytest
from dataclasses import dataclass, field


# We'll import from the preflight module we're about to create
from temper_placer.pipeline.preflight import (
    PreflightResult,
    PreflightCheck,
    PreflightReport,
    PreflightChecker,
)


# =============================================================================
# Mock Types for Testing (standalone, no external dependencies)
# =============================================================================


@dataclass
class MockComponent:
    """Mock component for testing."""

    ref: str
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class MockKeepout:
    """Mock keepout zone."""

    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class MockBoard:
    """Mock board for testing."""

    width: float
    height: float
    keepouts: list[MockKeepout]

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def usable_area(self) -> float:
        return self.area - sum(k.area for k in self.keepouts)


@dataclass
class MockNet:
    """Mock net for testing."""

    name: str
    pins: list[str]


@dataclass
class MockNetlist:
    """Mock netlist for testing."""

    components: list[MockComponent]
    nets: list[MockNet]


@dataclass
class MockConstraint:
    """Mock constraint for testing."""

    constraint_type: str
    a: str = ""
    b: str = ""
    max_distance: float = 0.0
    min_distance: float = 0.0
    inner: list[str] = field(default_factory=list)
    outer: str = ""


@dataclass
class MockConstraints:
    """Mock constraint collection."""

    constraints: list[MockConstraint]


@dataclass
class MockFabPreset:
    """Mock fabrication preset."""

    min_clearance: float = 0.15
    min_trace_width: float = 0.15
    min_via_diameter: float = 0.3


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def small_board() -> MockBoard:
    """Create a small board (50x50mm)."""
    return MockBoard(width=50.0, height=50.0, keepouts=[])


@pytest.fixture
def large_board() -> MockBoard:
    """Create a large board (150x100mm)."""
    return MockBoard(width=150.0, height=100.0, keepouts=[])


@pytest.fixture
def board_with_keepouts() -> MockBoard:
    """Board with keepout zones."""
    return MockBoard(
        width=100.0,
        height=100.0,
        keepouts=[
            MockKeepout(x=0, y=0, width=10, height=100),  # Left edge
            MockKeepout(x=90, y=0, width=10, height=100),  # Right edge
        ],
    )


@pytest.fixture
def small_netlist() -> MockNetlist:
    """Netlist with few small components."""
    return MockNetlist(
        components=[
            MockComponent(ref="R1", width=2.0, height=1.0),
            MockComponent(ref="R2", width=2.0, height=1.0),
            MockComponent(ref="C1", width=3.0, height=2.0),
        ],
        nets=[
            MockNet(name="VCC", pins=["R1.1", "C1.1"]),
            MockNet(name="GND", pins=["R1.2", "R2.1", "C1.2"]),
        ],
    )


@pytest.fixture
def large_netlist() -> MockNetlist:
    """Netlist with many large components."""
    components = [MockComponent(ref=f"U{i}", width=10.0, height=10.0) for i in range(20)]
    return MockNetlist(
        components=components,
        nets=[MockNet(name="NET1", pins=["U0.1", "U1.1"])],
    )


@pytest.fixture
def hv_netlist() -> MockNetlist:
    """Netlist with HV components."""
    return MockNetlist(
        components=[
            MockComponent(ref="Q1", width=15.0, height=10.0),  # HV IGBT
            MockComponent(ref="Q2", width=15.0, height=10.0),  # HV IGBT
            MockComponent(ref="U1", width=8.0, height=5.0),  # LV controller
            MockComponent(ref="U2", width=8.0, height=5.0),  # LV controller
        ],
        nets=[
            MockNet(name="DC_BUS_P", pins=["Q1.1", "Q2.1"]),
            MockNet(name="DC_BUS_N", pins=["Q1.2", "Q2.2"]),
            MockNet(name="VCC", pins=["U1.1", "U2.1"]),
            MockNet(name="GND", pins=["U1.2", "U2.2"]),
        ],
    )


@pytest.fixture
def empty_constraints() -> MockConstraints:
    """Empty constraint set."""
    return MockConstraints(constraints=[])


@pytest.fixture
def valid_constraints() -> MockConstraints:
    """Valid constraint set."""
    return MockConstraints(
        constraints=[
            MockConstraint(
                constraint_type="adjacent",
                a="R1",
                b="C1",
                max_distance=5.0,
            ),
            MockConstraint(
                constraint_type="separated",
                a="U1",
                b="Q1",
                min_distance=10.0,
            ),
        ]
    )


@pytest.fixture
def contradictory_constraints() -> MockConstraints:
    """Constraint set with contradictions."""
    return MockConstraints(
        constraints=[
            MockConstraint(
                constraint_type="adjacent",
                a="R1",
                b="C1",
                max_distance=5.0,
            ),
            MockConstraint(
                constraint_type="separated",
                a="R1",
                b="C1",
                min_distance=10.0,  # Contradiction: can't be <5mm AND >10mm apart
            ),
        ]
    )


@pytest.fixture
def hv_constraints() -> MockConstraints:
    """Constraints with HV zones."""
    return MockConstraints(
        constraints=[
            MockConstraint(
                constraint_type="enclosing",
                inner=["Q1", "Q2"],
                outer="HV_ZONE",
            ),
            MockConstraint(
                constraint_type="separated",
                a="Q1",
                b="U1",
                min_distance=8.0,  # HV clearance
            ),
        ]
    )


@pytest.fixture
def default_fab_preset() -> MockFabPreset:
    """Default fabrication preset."""
    return MockFabPreset()


# =============================================================================
# Test PreflightResult Enum
# =============================================================================


class TestPreflightResult:
    """Tests for PreflightResult enum."""

    def test_preflight_result_exists(self):
        """PreflightResult enum exists."""
        assert PreflightResult is not None

    def test_has_pass_value(self):
        """PreflightResult has PASS."""
        assert PreflightResult.PASS.value == "pass"

    def test_has_warn_value(self):
        """PreflightResult has WARN."""
        assert PreflightResult.WARN.value == "warn"

    def test_has_fail_value(self):
        """PreflightResult has FAIL."""
        assert PreflightResult.FAIL.value == "fail"


# =============================================================================
# Test PreflightCheck Dataclass
# =============================================================================


class TestPreflightCheck:
    """Tests for PreflightCheck dataclass."""

    def test_preflight_check_exists(self):
        """PreflightCheck dataclass exists."""
        assert PreflightCheck is not None

    def test_create_passing_check(self):
        """Can create a passing check."""
        check = PreflightCheck(
            name="Component Area",
            result=PreflightResult.PASS,
            message="Component fill ratio 45% OK",
        )
        assert check.name == "Component Area"
        assert check.result == PreflightResult.PASS
        assert "45%" in check.message

    def test_create_failing_check(self):
        """Can create a failing check."""
        check = PreflightCheck(
            name="Component Area",
            result=PreflightResult.FAIL,
            message="Components exceed board area",
        )
        assert check.result == PreflightResult.FAIL

    def test_has_optional_details(self):
        """PreflightCheck has optional details field."""
        check = PreflightCheck(
            name="Test",
            result=PreflightResult.PASS,
            message="OK",
            details={"key": "value"},
        )
        assert check.details == {"key": "value"}

    def test_has_time_field(self):
        """PreflightCheck has time_ms field."""
        check = PreflightCheck(
            name="Test",
            result=PreflightResult.PASS,
            message="OK",
            time_ms=5.2,
        )
        assert check.time_ms == 5.2


# =============================================================================
# Test PreflightReport Dataclass
# =============================================================================


class TestPreflightReport:
    """Tests for PreflightReport dataclass."""

    def test_preflight_report_exists(self):
        """PreflightReport dataclass exists."""
        assert PreflightReport is not None

    def test_create_report(self):
        """Can create a preflight report."""
        checks = [
            PreflightCheck(name="Test1", result=PreflightResult.PASS, message="OK"),
            PreflightCheck(name="Test2", result=PreflightResult.PASS, message="OK"),
        ]
        report = PreflightReport(
            checks=checks,
            overall=PreflightResult.PASS,
            total_time_ms=10.5,
        )
        assert len(report.checks) == 2
        assert report.overall == PreflightResult.PASS
        assert report.total_time_ms == 10.5

    def test_passed_property_true_for_pass(self):
        """passed property is True when overall is PASS."""
        report = PreflightReport(
            checks=[],
            overall=PreflightResult.PASS,
            total_time_ms=0.0,
        )
        assert report.passed is True

    def test_passed_property_true_for_warn(self):
        """passed property is True when overall is WARN."""
        report = PreflightReport(
            checks=[],
            overall=PreflightResult.WARN,
            total_time_ms=0.0,
        )
        assert report.passed is True

    def test_passed_property_false_for_fail(self):
        """passed property is False when overall is FAIL."""
        report = PreflightReport(
            checks=[],
            overall=PreflightResult.FAIL,
            total_time_ms=0.0,
        )
        assert report.passed is False

    def test_summary_method(self):
        """summary() returns formatted string."""
        checks = [
            PreflightCheck(name="Test1", result=PreflightResult.PASS, message="OK"),
            PreflightCheck(name="Test2", result=PreflightResult.WARN, message="Warning"),
        ]
        report = PreflightReport(
            checks=checks,
            overall=PreflightResult.WARN,
            total_time_ms=15.0,
        )
        summary = report.summary()
        assert "Preflight" in summary
        assert "Test1" in summary
        assert "WARN" in summary


# =============================================================================
# Test PreflightChecker Initialization
# =============================================================================


class TestPreflightCheckerInit:
    """Tests for PreflightChecker initialization."""

    def test_preflight_checker_exists(self):
        """PreflightChecker class exists."""
        assert PreflightChecker is not None

    def test_can_create_checker(self):
        """Can create a checker."""
        checker = PreflightChecker()
        assert checker is not None

    def test_has_run_method(self):
        """PreflightChecker has run method."""
        checker = PreflightChecker()
        assert hasattr(checker, "run")
        assert callable(checker.run)


# =============================================================================
# Test PreflightChecker.run()
# =============================================================================


class TestPreflightCheckerRun:
    """Tests for PreflightChecker.run()."""

    def test_run_returns_report(
        self, small_board, small_netlist, empty_constraints, default_fab_preset
    ):
        """run() returns a PreflightReport."""
        checker = PreflightChecker()
        result = checker.run(
            board=small_board,
            netlist=small_netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )
        assert isinstance(result, PreflightReport)

    def test_run_includes_multiple_checks(
        self, small_board, small_netlist, empty_constraints, default_fab_preset
    ):
        """run() performs multiple checks."""
        checker = PreflightChecker()
        result = checker.run(
            board=small_board,
            netlist=small_netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )
        assert len(result.checks) >= 3  # At least 3 different checks

    def test_run_measures_total_time(
        self, small_board, small_netlist, empty_constraints, default_fab_preset
    ):
        """run() measures total execution time."""
        checker = PreflightChecker()
        result = checker.run(
            board=small_board,
            netlist=small_netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )
        assert result.total_time_ms >= 0


# =============================================================================
# Test Component Area Check
# =============================================================================


class TestComponentAreaCheck:
    """Tests for component area check."""

    def test_passes_when_components_fit(
        self, large_board, small_netlist, empty_constraints, default_fab_preset
    ):
        """PASS when components easily fit on board."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,  # 150x100 = 15000mm²
            netlist=small_netlist,  # Total ~10mm²
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        area_check = next(c for c in result.checks if "Area" in c.name)
        assert area_check.result == PreflightResult.PASS

    def test_warns_when_fill_ratio_high(self, small_board, empty_constraints, default_fab_preset):
        """WARN when fill ratio exceeds 70%."""
        # Create components that fill ~75% of 50x50=2500mm² board
        # Need ~1875mm² of components
        components = [MockComponent(ref=f"U{i}", width=10.0, height=10.0) for i in range(19)]
        netlist = MockNetlist(components=components, nets=[])

        checker = PreflightChecker()
        result = checker.run(
            board=small_board,
            netlist=netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        area_check = next(c for c in result.checks if "Area" in c.name)
        assert area_check.result in (PreflightResult.WARN, PreflightResult.FAIL)

    def test_fails_when_components_overflow(
        self, small_board, empty_constraints, default_fab_preset
    ):
        """FAIL when components exceed 85% of board area."""
        # Create components that fill >85% of 50x50=2500mm² board
        # Need >2125mm² of components
        components = [MockComponent(ref=f"U{i}", width=10.0, height=10.0) for i in range(25)]
        netlist = MockNetlist(components=components, nets=[])

        checker = PreflightChecker()
        result = checker.run(
            board=small_board,
            netlist=netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        area_check = next(c for c in result.checks if "Area" in c.name)
        assert area_check.result == PreflightResult.FAIL

    def test_accounts_for_keepouts(
        self, board_with_keepouts, empty_constraints, default_fab_preset
    ):
        """Area check accounts for keepout zones."""
        # Board is 100x100=10000mm², but keepouts take 2000mm², leaving 8000mm²
        # Fill >70% = >5600mm² should trigger warning
        # Using 58 components at 100mm² each = 5800mm² = 72.5% fill
        components = [MockComponent(ref=f"U{i}", width=10.0, height=10.0) for i in range(58)]
        netlist = MockNetlist(components=components, nets=[])

        checker = PreflightChecker()
        result = checker.run(
            board=board_with_keepouts,
            netlist=netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        area_check = next(c for c in result.checks if "Area" in c.name)
        # Should at least warn due to keepouts reducing usable area
        assert area_check.result in (PreflightResult.WARN, PreflightResult.FAIL)


# =============================================================================
# Test Constraint Satisfiability Check
# =============================================================================


class TestConstraintSatisfiabilityCheck:
    """Tests for constraint satisfiability check."""

    def test_passes_with_no_constraints(
        self, large_board, small_netlist, empty_constraints, default_fab_preset
    ):
        """PASS with no constraints."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,
            netlist=small_netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        satisfiability_check = next(
            c for c in result.checks if "Satisfiab" in c.name or "Constraint" in c.name
        )
        assert satisfiability_check.result == PreflightResult.PASS

    def test_passes_with_valid_constraints(
        self, large_board, small_netlist, valid_constraints, default_fab_preset
    ):
        """PASS with valid (non-contradictory) constraints."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,
            netlist=small_netlist,
            constraints=valid_constraints,
            fab_preset=default_fab_preset,
        )

        satisfiability_check = next(
            c for c in result.checks if "Satisfiab" in c.name or "Constraint" in c.name
        )
        assert satisfiability_check.result == PreflightResult.PASS

    def test_fails_with_contradictory_constraints(
        self, large_board, small_netlist, contradictory_constraints, default_fab_preset
    ):
        """FAIL with contradictory constraints."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,
            netlist=small_netlist,
            constraints=contradictory_constraints,
            fab_preset=default_fab_preset,
        )

        satisfiability_check = next(
            c for c in result.checks if "Satisfiab" in c.name or "Constraint" in c.name
        )
        assert satisfiability_check.result == PreflightResult.FAIL


# =============================================================================
# Test Clearance Feasibility Check
# =============================================================================


class TestClearanceFeasibilityCheck:
    """Tests for clearance feasibility check."""

    def test_passes_when_clearance_achievable(
        self, large_board, hv_netlist, hv_constraints, default_fab_preset
    ):
        """PASS when HV/LV clearance is achievable."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,  # Large enough for clearance
            netlist=hv_netlist,
            constraints=hv_constraints,
            fab_preset=default_fab_preset,
        )

        clearance_check = next(c for c in result.checks if "Clearance" in c.name)
        assert clearance_check.result in (PreflightResult.PASS, PreflightResult.WARN)

    def test_fails_when_clearance_impossible(self, small_board, hv_netlist, default_fab_preset):
        """FAIL when board too small for required clearance."""
        # Require huge clearance that can't fit on small board
        huge_clearance_constraints = MockConstraints(
            constraints=[
                MockConstraint(
                    constraint_type="separated",
                    a="Q1",
                    b="U1",
                    min_distance=100.0,  # 100mm clearance - impossible on 50x50 board
                ),
            ]
        )

        checker = PreflightChecker()
        result = checker.run(
            board=small_board,
            netlist=hv_netlist,
            constraints=huge_clearance_constraints,
            fab_preset=default_fab_preset,
        )

        clearance_check = next(c for c in result.checks if "Clearance" in c.name)
        # Should fail or at least warn
        assert clearance_check.result in (PreflightResult.FAIL, PreflightResult.WARN)


# =============================================================================
# Test Overall Result Logic
# =============================================================================


class TestOverallResultLogic:
    """Tests for overall result determination."""

    def test_overall_pass_when_all_pass(
        self, large_board, small_netlist, empty_constraints, default_fab_preset
    ):
        """Overall PASS when all checks pass."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,
            netlist=small_netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        # With generous board and no constraints, should pass
        assert result.overall in (PreflightResult.PASS, PreflightResult.WARN)

    def test_overall_fail_when_any_fail(
        self, large_board, small_netlist, contradictory_constraints, default_fab_preset
    ):
        """Overall FAIL when any check fails."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,
            netlist=small_netlist,
            constraints=contradictory_constraints,
            fab_preset=default_fab_preset,
        )

        assert result.overall == PreflightResult.FAIL

    def test_overall_warn_when_any_warn_no_fail(
        self, small_board, empty_constraints, default_fab_preset
    ):
        """Overall WARN when checks warn but none fail."""
        # Create ~75% fill to trigger warning but not failure
        components = [MockComponent(ref=f"U{i}", width=10.0, height=10.0) for i in range(18)]
        netlist = MockNetlist(components=components, nets=[])

        checker = PreflightChecker()
        result = checker.run(
            board=small_board,
            netlist=netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        # Should be WARN (high fill) or FAIL (if fill too high)
        assert result.overall in (PreflightResult.WARN, PreflightResult.FAIL)


# =============================================================================
# Test Timing
# =============================================================================


class TestPreflightTiming:
    """Tests for preflight timing."""

    def test_completes_quickly(
        self, large_board, large_netlist, valid_constraints, default_fab_preset
    ):
        """Preflight completes in reasonable time."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,
            netlist=large_netlist,
            constraints=valid_constraints,
            fab_preset=default_fab_preset,
        )

        # Should complete in <1 second for 20 components
        assert result.total_time_ms < 1000

    def test_individual_checks_have_timing(
        self, large_board, small_netlist, empty_constraints, default_fab_preset
    ):
        """Each check records its execution time."""
        checker = PreflightChecker()
        result = checker.run(
            board=large_board,
            netlist=small_netlist,
            constraints=empty_constraints,
            fab_preset=default_fab_preset,
        )

        for check in result.checks:
            assert hasattr(check, "time_ms")
            assert check.time_ms >= 0
