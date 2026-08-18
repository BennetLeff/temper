"""Differential test: the Rust-ported ``netclass_constraints`` orchestration
(``temper_orchestration.netclass_separated_constraints_py`` /
``netclass_resolve_component_class_py``) vs the pinned pre-Rust-port Python
oracle (placer constraint/clearance Rust-port stage 2, 2026-08-17; rebased
onto main PR #1323's classifier fix).

``netclass_constraints.py::generate_netclass_separated_constraints`` is
LIVE BY DEFAULT (``_encoder_core.py`` calls it on every full-board solve,
unlike ``domain_clearance.py`` which the spike found unwired) -- a
regression here changes every solve's output today, not just a future one.
This differential is therefore run over hand-built scenarios covering every
branch the pre-port Python had (cross-class pairing, same-class skip,
``existing_constraints`` suppression incl. the ``AdjacentConstraint``
non-suppression case, ``touch_refs`` restriction, real ``class_pairs``
overrides, multi-component O(n^2) pairing with >2 components) PLUS a
Hypothesis property test generating random component/net combinations,
comparing the full constraint list (a, b, min_distance_mm, tier, because,
id) field-for-field between the two implementations.

RE-PINNED, DOCUMENTED DIVERGENCE (see ``_netclass_constraints_py_oracle.py``'s
own module docstring for the full rationale, same discipline PR #1307 used):
this suite originally pinned the module as it stood BEFORE main PR #1323's
classifier fix (net-NAME keyword heuristic). #1323 is a safety fix -- the
old heuristic misclassified K1's HV relay-contact nets as "signal", the
same bucket J1's SELV RTD nets fall into, generating ZERO separation
constraint for the pair that later proved unroutable. After rebasing this
port onto #1323, the oracle was re-pinned to #1323's OWN committed
implementation (the correct pre-Rust-port baseline) rather than reverting
#1323's fix to match the stale oracle. ``test_j1_k1_style_defect_pair_gets_a_constraint``
below asserts the corrected behaviour survives the Rust port end-to-end:
an HV relay-contact-style net and an unassigned SELV-style net must resolve
to DIFFERENT classes and produce a real SeparatedConstraint, on both sides
of the differential.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tests.pcl._netclass_constraints_py_oracle as _oracle
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.netclass_constraints import (
    _resolve_component_net_class,
    generate_netclass_separated_constraints,
)

RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"


class _MockPin:
    def __init__(self, number: str, component: str, net: str):
        self.number = number
        self.component = component
        self.net = net


class _MockComp:
    def __init__(self, ref: str, nets: list[str]):
        self.ref = ref
        self.pins = [_MockPin(str(i + 1), ref, n) for i, n in enumerate(nets)]


class _MockNet:
    def __init__(self, name: str, pins: list):
        self.name = name
        self.pins = pins


def _make_component(ref: str, nets: list[str]) -> _MockComp:
    return _MockComp(ref, nets)


def _mock_netlist(components: list[_MockComp]) -> object:
    class _MockNetlist:
        pass

    nl = _MockNetlist()
    nl.nets = [_MockNet(pin.net, [pin]) for comp in components for pin in comp.pins]
    return nl


@pytest.fixture(scope="module")
def rules():
    from temper_placer.io.netclass_loader import load_netclass_rules

    return load_netclass_rules(RULES_PATH)


def _canon(constraints: list[SeparatedConstraint]) -> list[tuple]:
    """Canonicalize a constraint list for comparison: field tuples, in
    emission order (order itself is part of what is being differentially
    tested -- see netclass.rs's own doc comment on why component iteration
    order is load-bearing)."""
    return [
        (
            c.a,
            c.b,
            float(c.min_distance_mm).hex(),
            (c.tier.name, c.tier.value),
            c.because,
            c.id,
        )
        for c in constraints
    ]


def _assert_matches_oracle(netlist, components, design_rules, **kwargs):
    ours = generate_netclass_separated_constraints(netlist, components, design_rules, **kwargs)
    theirs = _oracle.generate_netclass_separated_constraints(
        netlist, components, design_rules, **kwargs
    )
    assert _canon(ours) == _canon(theirs)
    return ours


class TestResolveComponentNetClassDifferential:
    def test_mixed_pins_returns_max_severity(self, rules):
        # GATE_H -> GateDriveHV (HV), DC_BUS- / SW_NODE -> HighVoltage (HV):
        # same category, HighVoltage's clearance (2.0) beats GateDriveHV's
        # (0.25) on the tiebreak.
        comp = _make_component("Q2", ["GATE_H", "DC_BUS-", "SW_NODE"])
        ours = _resolve_component_net_class(comp, None, rules.design_rules)
        theirs = _oracle._resolve_component_net_class(comp, None, rules.design_rules)
        assert ours == theirs == "HighVoltage"

    def test_all_signal_pins_returns_signal(self, rules):
        # Neither net has a TEMPER_NET_ASSIGNMENTS entry nor matches any
        # pattern-cascade tier -- both fall through to "Default", normalized
        # to "Signal".
        comp = _make_component("U1", ["SPI_CLK", "SPI_MOSI"])
        ours = _resolve_component_net_class(comp, None, rules.design_rules)
        theirs = _oracle._resolve_component_net_class(comp, None, rules.design_rules)
        assert ours == theirs == "Signal"

    def test_no_pins_returns_none(self, rules):
        comp = _make_component("U9", [])
        ours = _resolve_component_net_class(comp, None, rules.design_rules)
        theirs = _oracle._resolve_component_net_class(comp, None, rules.design_rules)
        assert ours == theirs is None

    def test_all_empty_net_names_returns_none(self, rules):
        comp = _MockComp("U10", [])
        comp.pins = [_MockPin("1", "U10", "")]
        ours = _resolve_component_net_class(comp, None, rules.design_rules)
        theirs = _oracle._resolve_component_net_class(comp, None, rules.design_rules)
        assert ours == theirs is None

    def test_ground_net(self, rules):
        # "gnd" is explicitly assigned "Power" in TEMPER_NET_ASSIGNMENTS
        # (matches pcb/temper.kicad_pro -- see design_rules.py's own
        # comment), NOT "GND" -- a real, deliberate divergence from the old
        # keyword heuristic's "gnd" -> ground -> "GND" verdict.
        comp = _make_component("R1", ["gnd"])
        ours = _resolve_component_net_class(comp, None, rules.design_rules)
        theirs = _oracle._resolve_component_net_class(comp, None, rules.design_rules)
        assert ours == theirs == "Power"

    def test_power_net(self, rules):
        comp = _make_component("R2", ["+3V3"])
        ours = _resolve_component_net_class(comp, None, rules.design_rules)
        theirs = _oracle._resolve_component_net_class(comp, None, rules.design_rules)
        assert ours == theirs == "Power"

    def test_j1_k1_style_defect_pair_classifies_differently(self, rules):
        """The exact defect shape #1323 fixed: an HV relay-contact-style net
        (assigned HighVoltage in TEMPER_NET_ASSIGNMENTS, no HV-sounding
        keyword in its name) and an unassigned SELV-style net (falls to
        Default/Signal) must resolve to DIFFERENT classes -- under the old
        keyword heuristic both landed in "signal". Verified on both the
        ported Rust path and the pinned #1323 oracle.
        """
        k1_style = _make_component("K1", ["power_in.ntc-no"])
        j1_style = _make_component("J1", ["RTD_SDO"])  # FinePitch, not Signal/Default here -- see below
        ours_k1 = _resolve_component_net_class(k1_style, None, rules.design_rules)
        theirs_k1 = _oracle._resolve_component_net_class(k1_style, None, rules.design_rules)
        ours_j1 = _resolve_component_net_class(j1_style, None, rules.design_rules)
        theirs_j1 = _oracle._resolve_component_net_class(j1_style, None, rules.design_rules)
        assert ours_k1 == theirs_k1 == "HighVoltage"
        assert ours_j1 == theirs_j1 == "FinePitch"
        assert ours_k1 != ours_j1


class TestOrchestrationDifferential:
    def test_two_cross_class_components(self, rules):
        c1 = _make_component("U1", ["DC_BUS+"])
        c2 = _make_component("U2", ["SPI_CLK"])
        _assert_matches_oracle(_mock_netlist([c1, c2]), [c1, c2], rules.design_rules)

    def test_same_class_no_generation(self, rules):
        c1 = _make_component("U1", ["SPI_CLK"])
        c2 = _make_component("U2", ["SPI_MOSI"])
        result = _assert_matches_oracle(_mock_netlist([c1, c2]), [c1, c2], rules.design_rules)
        assert result == []

    def test_three_components_full_pairing(self, rules):
        c1 = _make_component("U1", ["DC_BUS+"])  # HighVoltage
        c2 = _make_component("U2", ["SPI_CLK"])  # Signal (Default)
        c3 = _make_component("U3", ["gnd"])  # Power
        _assert_matches_oracle(_mock_netlist([c1, c2, c3]), [c1, c2, c3], rules.design_rules)

    def test_five_components_mixed_classes(self, rules):
        comps = [
            _make_component("U1", ["DC_BUS+"]),  # HighVoltage
            _make_component("U2", ["SPI_CLK"]),  # Signal (Default)
            _make_component("U3", ["gnd"]),  # Power
            _make_component("U4", ["+3V3"]),  # Power
            _make_component("U5", ["SPI_MOSI"]),  # Signal (Default)
        ]
        _assert_matches_oracle(_mock_netlist(comps), comps, rules.design_rules)

    def test_component_with_no_resolvable_class_excluded(self, rules):
        c1 = _make_component("U1", ["DC_BUS+"])
        c2 = _make_component("U2", ["SPI_CLK"])
        c3 = _MockComp("U3", [])  # no pins at all
        _assert_matches_oracle(_mock_netlist([c1, c2]), [c1, c2, c3], rules.design_rules)

    def test_adjacent_constraint_does_not_suppress(self, rules):
        c1 = _make_component("U1", ["DC_BUS+"])
        c2 = _make_component("U2", ["SPI_CLK"])
        adjacent = AdjacentConstraint(
            a="U1", b="U2", max_distance_mm=10.0, tier=ConstraintTier.HARD,
            because="Unrelated adjacency requirement",
        )
        _assert_matches_oracle(
            _mock_netlist([c1, c2]), [c1, c2], rules.design_rules,
            existing_constraints=[adjacent],
        )

    def test_separated_constraint_suppresses(self, rules):
        c1 = _make_component("U1", ["DC_BUS+"])
        c2 = _make_component("U2", ["SPI_CLK"])
        separated = SeparatedConstraint(
            a="U1", b="U2", min_distance_mm=6.0, tier=ConstraintTier.HARD,
            because="Already covered",
        )
        result = _assert_matches_oracle(
            _mock_netlist([c1, c2]), [c1, c2], rules.design_rules,
            existing_constraints=[separated],
        )
        assert result == []

    def test_touch_refs_restricts_pairs(self, rules):
        c1 = _make_component("U1", ["DC_BUS+"])  # HighVoltage
        c2 = _make_component("U2", ["SPI_CLK"])  # Signal
        c3 = _make_component("U3", ["SPI_MOSI"])  # Signal
        _assert_matches_oracle(
            _mock_netlist([c1, c2, c3]), [c1, c2, c3], rules.design_rules,
            touch_refs={"U1"},
        )

    def test_touch_refs_excludes_untouched_pair(self, rules):
        # Neither U2 nor U3 is in touch_refs -- their cross-class pair (if
        # any) must be excluded on both sides.
        c1 = _make_component("U1", ["DC_BUS+"])  # HighVoltage
        c2 = _make_component("U2", ["SPI_CLK"])  # Signal
        c3 = _make_component("U3", ["gnd"])  # Power
        result = _assert_matches_oracle(
            _mock_netlist([c1, c2, c3]), [c1, c2, c3], rules.design_rules,
            touch_refs={"U1"},
        )
        # Only U1-U2 and U1-U3 survive; U2-U3 (both untouched) is excluded.
        pairs = {(c.a, c.b) for c in result}
        assert ("U2", "U3") not in pairs

    def test_class_pair_override_from_real_config(self, rules):
        # ACMains<->Signal has a real, cited class_pair override in
        # netclass_rules.yaml (per test_e2e_netclass_ssot.py).
        c1 = _make_component("U1", ["ac_l"])  # ACMains
        c2 = _make_component("U2", ["SPI_CLK"])  # Signal
        _assert_matches_oracle(_mock_netlist([c1, c2]), [c1, c2], rules.design_rules)

    def test_gatedrive_class_pair_override_from_1323(self, rules):
        # GateDriveHV<->GateDriveSELV is one of the 10 rows #1323 added to
        # close the gap its own classifier fix newly activated (GateDriveHV/
        # GateDriveSELV could never be resolved by the old keyword
        # heuristic). Exercises that this port reads the completed table.
        c1 = _make_component("U1", ["GATE_HS"])  # GateDriveHV
        c2 = _make_component("U2", ["PWM_HS"])  # GateDriveSELV
        result = _assert_matches_oracle(_mock_netlist([c1, c2]), [c1, c2], rules.design_rules)
        assert len(result) == 1
        assert result[0].min_distance_mm == 6.0

    def test_j1_k1_style_pair_gets_a_constraint(self, rules):
        """The end-to-end proof the coordinator asked for: after the
        rebase, does the ported orchestration still produce a real
        constraint for the K1/J1-style pair the old keyword heuristic
        dropped to zero? K1's `power_in.ntc-no` resolves to HighVoltage;
        an unassigned SELV-style net resolves to Signal (Default) -- a
        genuine cross-class pair, which must produce exactly one
        SeparatedConstraint on both the Rust path and the oracle, at the
        real board's HighVoltage<->Signal `class_pairs` figure (6.0mm,
        `docs/evidence/2026-08-17-netclass-classifier-manifest-and-
        ieccreepagegate-liveness.md`'s own measured value for this exact
        pair).
        """
        k1_style = _make_component("K1", ["power_in.ntc-no"])
        j1_style = _make_component("J1", ["V_RTD_SELV_UNASSIGNED"])
        result = _assert_matches_oracle(
            _mock_netlist([k1_style, j1_style]), [k1_style, j1_style], rules.design_rules
        )
        assert len(result) == 1
        assert {result[0].a, result[0].b} == {"K1", "J1"}
        assert result[0].min_distance_mm == 6.0

    def test_single_component_no_pairs(self, rules):
        c1 = _make_component("U1", ["DC_BUS+"])
        result = _assert_matches_oracle(_mock_netlist([c1]), [c1], rules.design_rules)
        assert result == []

    def test_empty_components(self, rules):
        result = _assert_matches_oracle(_mock_netlist([]), [], rules.design_rules)
        assert result == []


# A vocabulary of real net names spanning the SSOT classifier's tiers
# (explicit TEMPER_NET_ASSIGNMENTS entries across several classes, plus
# names that fall through to the Default/Signal catch-all), used by the
# property test below.
_ASSIGNED_NETS = [
    "gnd", "PWR_RTN", "+3V3", "+15V", "vcc",  # Power / HighVoltage
    "DC_BUS+", "DC_BUS-", "ac_l", "SW_NODE", "power_in.ntc-no", "w1_1",  # HighVoltage / ACMains
    "GATE_HS", "GATE_LS",  # GateDriveHV
    "PWM_HS", "PWM_LS",  # GateDriveSELV
    "sclk", "cs_n",  # FinePitch
]
_UNASSIGNED_NETS = ["SPI_CLK", "SPI_MOSI", "random_selv_net", "another_unassigned"]
_ALL_NETS = _ASSIGNED_NETS + _UNASSIGNED_NETS

_component_strategy = st.builds(
    lambda ref, nets: (ref, nets),
    ref=st.from_regex(r"[A-Z][0-9]{1,2}", fullmatch=True),
    nets=st.lists(st.sampled_from(_ALL_NETS), min_size=0, max_size=3),
)


class TestOrchestrationDifferentialProperty:
    @settings(max_examples=60, deadline=None)
    @given(
        specs=st.lists(_component_strategy, min_size=0, max_size=8, unique_by=lambda s: s[0])
    )
    def test_random_components_match_oracle(self, rules, specs):
        components = [_make_component(ref, nets) for ref, nets in specs]
        _assert_matches_oracle(_mock_netlist(components), components, rules.design_rules)
