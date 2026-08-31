"""Test CP-SAT netclass constraint generation using DesignRules."""

from pathlib import Path
from types import SimpleNamespace

import pytest

RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"


def _make_mock_component(ref: str, net_name: str = ""):
    """Create a minimal mock component with ref and a connected pin."""

    class MockPin:
        def __init__(self, number, component, net):
            self.number = number
            self.component = component
            self.net = net

    class MockComp:
        def __init__(self, ref, pins):
            self.ref = ref
            self.pins = pins

    class MockNet:
        def __init__(self, name, pins):
            self.name = name
            self.pins = pins

    pin = MockPin("1", ref, net_name)
    net = MockNet(net_name, [pin])
    comp = MockComp(ref, [pin])
    return comp, net


@pytest.fixture
def rules():
    from temper_placer.io.netclass_loader import load_netclass_rules

    return load_netclass_rules(RULES_PATH)


class TestResolveComponentNetClass:
    """Unit tests for _resolve_component_net_class."""

    def test_mixed_pins_returns_max_severity(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            _resolve_component_net_class,
        )

        class MockPin:
            def __init__(self, number, net):
                self.number = number
                self.component = "Q2"
                self.net = net

        class MockComp:
            def __init__(self, ref, pins):
                self.ref = ref
                self.pins = pins

        comp = MockComp(
            "Q2",
            [
                MockPin("1", "GATE_H"),  # GateDriveHV (safety_category HV)
                MockPin("2", "DC_BUS-"),  # HighVoltage (safety_category HV)
                MockPin("3", "SW_NODE"),  # HighVoltage (safety_category HV)
            ],
        )
        result = _resolve_component_net_class(comp, None, rules.design_rules)
        assert result == "HighVoltage", (
            f"Expected HighVoltage (max severity across all pins), got {result}"
        )

    def test_all_signal_pins_returns_signal(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            _resolve_component_net_class,
        )

        class MockPin:
            def __init__(self, number, net):
                self.number = number
                self.component = "U1"
                self.net = net

        class MockComp:
            def __init__(self, ref, pins):
                self.ref = ref
                self.pins = pins

        comp = MockComp(
            "U1",
            [
                MockPin("1", "SPI_CLK"),
                MockPin("2", "SPI_MOSI"),
            ],
        )
        # Neither net has a TEMPER_NET_ASSIGNMENTS entry nor matches any
        # pattern-cascade tier, so get_rules_for_net() falls through to its
        # own "Default" class -- normalized to "Signal" here (see
        # _resolve_component_net_class's docstring) to keep this generic-LV
        # bucket reachable in netclass_rules.yaml's class_pairs table.
        result = _resolve_component_net_class(comp, None, rules.design_rules)
        assert result == "Signal"


class TestCrossClassGeneration:
    def test_lazy_budget_is_bounded_by_round_and_total_time(self):
        from temper_placer.placer.cp_sat._encoder_solve import (
            _lazy_solver_budget_seconds,
        )

        assert _lazy_solver_budget_seconds(90_000, 28.0, 30_000) == pytest.approx(30.0)
        assert _lazy_solver_budget_seconds(90_000, 75.0, 30_000) == pytest.approx(15.0)
        assert _lazy_solver_budget_seconds(90_000, 90.0, 30_000) == 0.0

    @staticmethod
    def _tiny_netlist():
        def component(ref, net):
            pin = SimpleNamespace(number="1", component=ref, net=net)
            return SimpleNamespace(ref=ref, pins=[pin], bounds=(2.0, 2.0))

        return SimpleNamespace(
            components=[component("U_HV", "DC_BUS+"), component("U_LV", "SPI_CLK")],
            nets=[],
        )

    def test_lazy_creepage_converges_after_adding_cut(self, monkeypatch):
        from temper_placer.placer.cp_sat import _encoder_solve

        monkeypatch.setattr(_encoder_solve, "_resolve_loop_components", lambda _nl: {})
        calls = []

        def oracle(*_args):
            calls.append(None)
            return [("U_HV", "U_LV", 12.6, 0.0)] if len(calls) == 1 else []

        monkeypatch.setattr(
            "temper_placer.placer.cp_sat.netclass_constraints.verify_generated_creepage",
            oracle,
        )
        result = _encoder_solve.solve_placement(
            self._tiny_netlist(),
            SimpleNamespace(width=30.0, height=20.0, zones=[], constraints=[]),
            timeout_ms=2_000,
            lazy_creepage=True,
            lazy_creepage_max_rounds=2,
        )
        assert result.status in ("optimal", "feasible")
        assert len(calls) == 2

    def test_lazy_creepage_cap_is_fail_closed(self, monkeypatch):
        from temper_placer.placer.cp_sat import _encoder_solve

        monkeypatch.setattr(_encoder_solve, "_resolve_loop_components", lambda _nl: {})
        monkeypatch.setattr(
            "temper_placer.placer.cp_sat.netclass_constraints.verify_generated_creepage",
            lambda *_args: [("U_HV", "U_LV", 12.6, 0.0)],
        )
        result = _encoder_solve.solve_placement(
            self._tiny_netlist(),
            SimpleNamespace(width=30.0, height=20.0, zones=[], constraints=[]),
            timeout_ms=2_000,
            lazy_creepage=True,
            lazy_creepage_max_rounds=0,
        )
        assert result.status == "unknown"
        assert result.positions == {}

    def test_rust_creepage_verifier_is_exhaustive_and_uses_generated_value(self, rules):
        """The lazy-solve oracle checks every actual component pair in Rust."""
        from temper_placer.placer.cp_sat.netclass_constraints import (
            verify_generated_creepage,
        )

        hv, hv_net = _make_mock_component("U_HV", "DC_BUS+")
        lv, lv_net = _make_mock_component("U_LV", "SPI_CLK")

        class MockNetlist:
            components = [hv, lv]
            nets = [hv_net, lv_net]

        overlapping = verify_generated_creepage(
            MockNetlist(),
            rules.design_rules,
            [("U_HV", 10.0, 12.0, 10.0, 12.0), ("U_LV", 10.0, 12.0, 10.0, 12.0)],
        )
        assert overlapping == [("U_HV", "U_LV", pytest.approx(12.6), pytest.approx(0.0))]

        separated = verify_generated_creepage(
            MockNetlist(),
            rules.design_rules,
            [("U_HV", 0.0, 2.0, 0.0, 2.0), ("U_LV", 14.6, 16.6, 0.0, 2.0)],
        )
        assert separated == []

    def test_cross_class_pair_count(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U1", "DC_BUS+")  # HighVoltage
        c2, n2 = _make_mock_component("U2", "SPI_CLK")  # Signal
        c3, n3 = _make_mock_component("U3", "SPI_MOSI")  # Signal

        class MockNetlist:
            nets = [n1, n2, n3]

        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2, c3], rules.design_rules
        )
        # U1(HV) vs U2(Signal) + U1(HV) vs U3(Signal) = 2 constraints
        assert len(constraints) == 2

    def test_cross_class_clearance_value(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U1", "DC_BUS+")
        c2, n2 = _make_mock_component("U2", "SPI_CLK")

        class MockNetlist:
            nets = [n1, n2]

        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules
        )
        assert constraints[0].min_distance_mm == 6.0

    def test_constraint_tier_is_hard(self, rules):
        from temper_placer.pcl.constraints import ConstraintTier
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U1", "DC_BUS+")
        c2, n2 = _make_mock_component("U2", "SPI_CLK")

        class MockNetlist:
            nets = [n1, n2]

        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules
        )
        assert constraints[0].tier == ConstraintTier.HARD

    def test_generated_creepage_matrix_raises_hv_to_unassigned_lv_pair(self, rules):
        """The production HV/LV pair must use the generated KiCad value.

        ``DC_BUS+`` is an actual board net classified ``HighVoltage`` while
        ``SPI_CLK`` is an actual unassigned/SELV-side net (the DesignRules
        fallback normalizes ``Default`` to ``Signal`` for placer classes).
        The generated KiCad creepage matrix calls this pair 12.6 mm; the
        legacy placer ``class_pairs`` clearance is only 6.0 mm.  This test
        therefore proves that the CP-SAT path consumes the generated matrix
        instead of silently falling back to the clearance table.
        """
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U_HV", "DC_BUS+")
        c2, n2 = _make_mock_component("U_LV", "SPI_CLK")

        class MockNetlist:
            nets = [n1, n2]

        constraints = generate_netclass_separated_constraints(
            MockNetlist(),
            [c1, c2],
            rules.design_rules,
            enforce_creepage=True,
        )
        assert len(constraints) == 1
        assert constraints[0].min_distance_mm == pytest.approx(12.6)
        assert constraints[0].min_distance_mm > 6.0
        assert "Generated KiCad creepage" in constraints[0].because

    def test_generated_creepage_checks_all_pin_class_pairs(self, rules):
        """A mixed real footprint cannot hide its LV pin behind HV dominance.

        Gate-drive footprints on this board carry both ``GATE_H`` (HV) and
        ``PWM_HS`` (SELV/LV) pins.  The component-level dominant class is
        intentionally HV for the clearance reducer, but creepage must still
        inspect every pin-class cross product.  Pairing that mixed footprint
        with the actual tank-node net ``tank.c_tank1-p2`` exercises the
        matrix path independently of the dominant-class result.
        """
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U7", "GATE_H")
        # Add the primary-side net carried by the real U7 footprint.
        c1.pins.append(type(c1.pins[0])("2", "U7", "PWM_HS"))
        c2, n2 = _make_mock_component("C25", "tank.c_tank1-p2")

        class MockNetlist:
            nets = [n1, n2]

        constraints = generate_netclass_separated_constraints(
            MockNetlist(),
            [c1, c2],
            rules.design_rules,
            enforce_creepage=True,
        )
        assert len(constraints) == 1
        # The dominant classes are GateDriveHV and HighVoltageTank, a pair
        # with no generated creepage row.  The non-dominant PWM_HS pin is
        # GateDriveSELV, however, and GateDriveSELV<->HighVoltageTank is a
        # generated 12.6 mm pair.  A dominant-class-only implementation
        # would incorrectly return the 2 mm class clearance here.
        assert constraints[0].min_distance_mm == pytest.approx(12.6)
        assert "Generated KiCad creepage" in constraints[0].because


class TestSameClassNoGeneration:
    def test_all_signal_no_constraints(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U1", "SPI_CLK")
        c2, n2 = _make_mock_component("U2", "SPI_MOSI")

        class MockNetlist:
            nets = [n1, n2]

        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules
        )
        assert len(constraints) == 0


class TestExistingConstraintSkip:
    """`existing_constraints` should only suppress a pair's auto-generated
    netclass clearance when a SEPARATED constraint already covers that pair
    -- an ADJACENT constraint on the same pair asserts a maximum distance,
    not a minimum separation, and must not be treated as equivalent.
    """

    def test_adjacent_constraint_does_not_suppress_netclass_clearance(self, rules):
        from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U1", "DC_BUS+")  # HighVoltage
        c2, n2 = _make_mock_component("U2", "SPI_CLK")  # Signal

        class MockNetlist:
            nets = [n1, n2]

        # An AdjacentConstraint on the exact same pair -- has `a`/`b`
        # attributes like SeparatedConstraint, but asserts a *maximum*
        # distance, not a minimum separation.
        adjacent = AdjacentConstraint(
            a="U1",
            b="U2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Unrelated adjacency requirement",
        )

        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules, existing_constraints=[adjacent]
        )
        assert len(constraints) == 1, (
            "an AdjacentConstraint on a pair must not suppress that pair's "
            "netclass clearance SEPARATED constraint"
        )
        assert constraints[0].min_distance_mm == 6.0

    def test_separated_constraint_does_suppress_netclass_clearance(self, rules):
        from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U1", "DC_BUS+")  # HighVoltage
        c2, n2 = _make_mock_component("U2", "SPI_CLK")  # Signal

        class MockNetlist:
            nets = [n1, n2]

        separated = SeparatedConstraint(
            a="U1",
            b="U2",
            min_distance_mm=6.0,
            tier=ConstraintTier.HARD,
            because="Already covered by an explicit rule",
        )

        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules, existing_constraints=[separated]
        )
        assert len(constraints) == 0, (
            "an existing SeparatedConstraint on a pair should still suppress "
            "the auto-generated netclass clearance for that pair"
        )
