"""Test CP-SAT netclass constraint generation using DesignRules."""

from pathlib import Path

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


class TestDruResolvedPairs:
    """`dru_resolved_pairs=True` -- the figures the production encoder uses.

    `_encoder_core.encode_constraints` passes this flag on every full-board
    solve, so these are the separations the shipping placer actually
    enforces. The default-False path is pinned separately by the
    Rust-vs-Python oracle differential
    (`test_netclass_constraints_rust_differential.py`), which is why these
    live in their own class rather than editing the assertions above: both
    behaviours are real and both are pinned.
    """

    def test_hv_to_signal_is_raised_to_the_dru_pd3_figure(self, rules):
        """The headline: 6.0mm -> 12.6mm on an HV<->SELV pair.

        6.0mm is `netclass_rules.yaml`'s `class_pairs` figure, whose own
        `because` string calls itself "UNSOURCED legacy". 12.6mm is what
        `pcb/temper.kicad_dru` grades the same pair by (PD3 reinforced).
        """
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        c1, n1 = _make_mock_component("U1", "DC_BUS+")  # HighVoltage
        c2, n2 = _make_mock_component("U2", "SPI_CLK")  # Signal

        class MockNetlist:
            nets = [n1, n2]

        legacy = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules
        )
        assert legacy[0].min_distance_mm == 6.0

        dru = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules, dru_resolved_pairs=True
        )
        assert dru[0].min_distance_mm == 12.6
        assert "kicad_dru" in dru[0].because

    def test_raise_is_monotone_over_every_declared_class_pair(self, rules):
        """No pair may come out lower than it goes in.

        The DRU is deliberately LOOSER than `class_pairs` on some
        same-domain pairs (ACMains<->HighVoltage: 3.0mm vs 6.0mm), so a
        naive substitution would weaken the placement model there.
        `_dru_resolved_pair_overrides` takes a max against both the legacy
        figure and the per-class fallback; this asserts that property
        directly over the real config's full class universe rather than
        trusting the implementation comment.
        """
        from temper_placer.placer.cp_sat.netclass_constraints import (
            _dru_resolved_pair_overrides,
        )

        design_rules = rules.design_rules
        class_clearance = {
            cls: design_rules.get_rules_for_net("", net_class=cls).clearance
            for cls in design_rules.net_classes
        }
        legacy_overrides = [
            (key[0], key[1], value.get("clearance"), str(value.get("because", "")))
            for key, value in (getattr(design_rules, "class_pairs", {}) or {}).items()
            if isinstance(key, tuple) and len(key) == 2 and isinstance(value, dict)
        ]

        resolved = _dru_resolved_pair_overrides(legacy_overrides, class_clearance)
        by_pair = {(a, b): mm for a, b, mm, _ in resolved}

        # Every legacy override survives at >= its own figure.
        for key_a, key_b, clearance, _ in legacy_overrides:
            if clearance is None:
                continue
            pair = (key_a, key_b) if key_a <= key_b else (key_b, key_a)
            assert by_pair[pair] >= clearance, (
                f"{pair} weakened: {clearance}mm -> {by_pair[pair]}mm"
            )

        # And every emitted pair clears the no-override fallback it would
        # otherwise have received.
        for (class_a, class_b), mm in by_pair.items():
            fallback = max(
                class_clearance.get(class_a, 0.0), class_clearance.get(class_b, 0.0)
            )
            assert mm >= fallback, f"({class_a},{class_b}) below fallback {fallback}mm"

        # The specific same-domain pair that motivates the max().
        assert by_pair[("ACMains", "HighVoltage")] == 6.0
