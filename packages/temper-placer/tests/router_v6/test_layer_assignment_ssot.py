"""Tests for netclass-SSOT-driven layer assignment (W2 U2 / R2).

Verifies the per-net-class ``layer`` field flows from netclass_rules.yaml
through the loader into a deterministic net->layer resolution.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.io.netclass_loader import load_netclass_rules
from temper_placer.router_v6.layer_assignment import (
    Layer,
    get_layer_for_net,
    layer_assignments_from_netclass,
    layer_name_to_enum,
    layer_name_to_index,
)

RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"

# R2 table: net class -> KiCad layer name.
EXPECTED_CLASS_LAYERS = {
    "ACMains": "F.Cu",
    "HighVoltage": "F.Cu",
    "HighCurrent": "F.Cu",
    "GateDrive": "B.Cu",
    "Power": "B.Cu",
    "Signal": "F.Cu",
    "GND": "In1.Cu",
    "FinePitch": "B.Cu",
    "HighSpeed": "B.Cu",
}


@pytest.fixture()
def design_rules():
    return load_netclass_rules(RULES_PATH).design_rules


class TestNetClassLayerField:
    def test_all_classes_carry_layer(self, design_rules):
        for cls, expected in EXPECTED_CLASS_LAYERS.items():
            assert design_rules.net_classes[cls].layer == expected, cls

    def test_no_signal_class_on_in2(self, design_rules):
        """In2.Cu is reserved for power-domain pours, never a signal class."""
        for cls in EXPECTED_CLASS_LAYERS:
            assert design_rules.net_classes[cls].layer != "In2.Cu"


class TestLayerNameMapping:
    def test_name_to_enum(self):
        assert layer_name_to_enum("F.Cu") is Layer.L1_TOP
        assert layer_name_to_enum("In1.Cu") is Layer.L2_GND
        assert layer_name_to_enum("In2.Cu") is Layer.L3_PWR
        assert layer_name_to_enum("B.Cu") is Layer.L4_BOT

    def test_name_to_index(self):
        assert layer_name_to_index("F.Cu") == 0
        assert layer_name_to_index("In1.Cu") == 1
        assert layer_name_to_index("In2.Cu") == 2
        assert layer_name_to_index("B.Cu") == 3

    def test_unknown_name_raises(self):
        with pytest.raises(KeyError):
            layer_name_to_enum("F.Mask")


class TestGetLayerForNet:
    def test_hv_nets_on_front(self, design_rules):
        assert get_layer_for_net("AC_L", design_rules) == "F.Cu"
        assert get_layer_for_net("DC_BUS+", design_rules) == "F.Cu"

    def test_ground_on_in1(self, design_rules):
        assert get_layer_for_net("GND", design_rules) == "In1.Cu"

    def test_power_domain_rails_on_in2(self, design_rules):
        for rail in ("+3V3", "+5V", "+15V"):
            assert get_layer_for_net(rail, design_rules) == "In2.Cu"

    def test_finepitch_on_back(self, design_rules):
        assert get_layer_for_net("PWM_H", design_rules) == "B.Cu"

    def test_unclassified_falls_back_to_default(self, design_rules):
        assert get_layer_for_net("SOME_RANDOM_NET", design_rules) == "B.Cu"

    def test_none_design_rules_falls_back(self):
        assert get_layer_for_net("whatever", None) == "B.Cu"

    def test_deterministic(self, design_rules):
        first = {n: get_layer_for_net(n, design_rules) for n in ("AC_L", "GND", "+3V3", "PWM_H")}
        second = {n: get_layer_for_net(n, design_rules) for n in ("AC_L", "GND", "+3V3", "PWM_H")}
        assert first == second


class TestLayerAssignmentsFromNetclass:
    def test_each_net_gets_one_primary_layer(self, design_rules):
        nets = ["AC_L", "DC_BUS+", "GND", "+3V3", "PWM_H"]
        assignments = layer_assignments_from_netclass(design_rules, nets)
        assert set(assignments) == set(nets)
        for a in assignments.values():
            assert len(a.allowed_layers) == 1
            assert a.primary_layer in a.allowed_layers

    def test_no_signal_net_on_in2(self, design_rules):
        nets = ["AC_L", "DC_BUS+", "GND", "PWM_H", "SPI_MOSI"]
        assignments = layer_assignments_from_netclass(design_rules, nets)
        for a in assignments.values():
            assert a.primary_layer is not Layer.L3_PWR

    def test_gnd_resolves_in1_only(self, design_rules):
        assignments = layer_assignments_from_netclass(design_rules, ["GND"])
        assert assignments["GND"].primary_layer is Layer.L2_GND

    def test_deterministic(self, design_rules):
        nets = ["AC_L", "GND", "+3V3", "PWM_H"]
        a1 = layer_assignments_from_netclass(design_rules, nets)
        a2 = layer_assignments_from_netclass(design_rules, nets)
        assert {k: v.primary_layer for k, v in a1.items()} == {
            k: v.primary_layer for k, v in a2.items()
        }

    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    whitelist_characters="_+-",
                ),
                min_size=1,
                max_size=12,
            ),
            min_size=0,
            max_size=30,
            unique=True,
        ),
    )
    def test_no_net_silently_dropped_or_duplicated(self, design_rules, net_names):
        """Regression coverage for the class of bug in
        docs/solutions/logic-errors/parsed-stub-missing-nets-silently-disables-layer-constraints-2026-07-22.md:
        a caller passing N distinct net names must get back assignments for
        exactly those N nets -- never fewer (silently dropped) nor more
        (stale/duplicated), for any net-name set including the empty one.
        """
        assignments = layer_assignments_from_netclass(design_rules, net_names)
        assert set(assignments.keys()) == set(net_names)
        assert len(assignments) == len(net_names)
