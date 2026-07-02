"""
Tests for net classification in kicad_parser.

Verifies that ``_apply_safety_classifications`` correctly sets ``comp.net_class``
based on the ``safety_category`` of connected nets from design rules, and that
the ``parse_kicad_pcb`` integration (with and without ``design_rules``) works
correctly.

Requirements: R1 (net classification wired into parser), R2 (maintainer verified).
"""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to the test fixtures directory."""
    return Path(__file__).resolve().parent.parent / "fixtures"

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.kicad_parser import (
    _apply_safety_classifications,
    parse_kicad_pcb,
)
from temper_placer.losses.base import LossContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temper_design_rules() -> DesignRules:
    """DesignRules mirroring the temper board's net classes and assignments."""
    return DesignRules(
        net_classes={
            "ACMains": NetClassRules(
                name="ACMains",
                trace_width=2.5,
                clearance=6.0,
                via_diameter=1.2,
                via_drill=0.6,
                creepage_mm=6.0,
                dru_priority=10,
                safety_category="AC",
            ),
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                trace_width=3.0,
                clearance=6.0,
                via_diameter=1.2,
                via_drill=0.6,
                creepage_mm=6.0,
                dru_priority=20,
                safety_category="HV",
            ),
            "FinePitch": NetClassRules(
                name="FinePitch",
                trace_width=0.127,
                clearance=0.1,
                via_diameter=0.4,
                via_drill=0.2,
                dru_priority=30,
                safety_category="LV",
            ),
            "GND": NetClassRules(
                name="GND",
                trace_width=1.0,
                clearance=0.3,
                via_diameter=1.0,
                via_drill=0.5,
                dru_priority=60,
                safety_category="LV",
            ),
            "Power": NetClassRules(
                name="Power",
                trace_width=0.5,
                clearance=0.25,
                via_diameter=0.8,
                via_drill=0.4,
                dru_priority=40,
                safety_category="LV",
            ),
            "Signal": NetClassRules(
                name="Signal",
                trace_width=0.2,
                clearance=0.15,
                via_diameter=0.6,
                via_drill=0.3,
                dru_priority=80,
                safety_category="LV",
            ),
        },
        net_class_assignments={
            # ACMains
            "AC_L": "ACMains",
            "AC_N": "ACMains",
            "PE": "ACMains",
            # HighVoltage
            "DC_BUS+": "HighVoltage",
            "DC_BUS-": "HighVoltage",
            "SW_NODE": "HighVoltage",
            # FinePitch
            "PWM_H": "FinePitch",
            "PWM_L": "FinePitch",
        },
    )


def _make_netlist_from_components(components: list[Component]) -> Netlist:
    """Build a Netlist from a list of components, auto-extracting nets from pins."""
    nets_dict: dict[str, Net] = {}
    for comp in components:
        for pin in comp.pins:
            if not pin.net:
                continue
            if pin.net not in nets_dict:
                nets_dict[pin.net] = Net(name=pin.net, pins=[])
            nets_dict[pin.net].pins.append((comp.ref, pin.name))
    nets = [n for n in nets_dict.values() if len(n.pins) >= 2]
    return Netlist(components=components, nets=nets)


@pytest.fixture
def simple_board() -> Board:
    """A 100x100mm board for LossContext tests."""
    return Board(width=100.0, height=100.0, origin=(0.0, 0.0))


# ---------------------------------------------------------------------------
# `_apply_safety_classifications` unit tests
# ---------------------------------------------------------------------------


class TestApplySafetyClassifications:
    """Direct unit tests of the private _apply_safety_classifications function."""

    def test_hv_component(self, temper_design_rules: DesignRules):
        """Q1 connected to DC_BUS+ (HV), SW_NODE (HV), GND (LV) → HighVoltage."""
        q1 = Component(
            ref="Q1",
            footprint="Package_TO_SOT_SMD:SOT-23",
            bounds=(3.0, 3.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="SW_NODE"),
                Pin(name="3", number="3", position=(0.0, 1.0), net="GND"),
            ],
        )
        netlist = _make_netlist_from_components([q1])
        _apply_safety_classifications(netlist, temper_design_rules)
        assert netlist.components[0].net_class == "HighVoltage"

    def test_lv_component(self, temper_design_rules: DesignRules):
        """U_MCU connected to +3V3, GND, PWM_H, PWM_L → Signal (all LV nets)."""
        u_mcu = Component(
            ref="U_MCU",
            footprint="Package_QFP:TQFP-32_7x7mm_P0.8mm",
            bounds=(7.0, 7.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="+3V3"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="GND"),
                Pin(name="3", number="3", position=(0.0, 1.0), net="PWM_H"),
                Pin(name="4", number="4", position=(1.0, 1.0), net="PWM_L"),
            ],
        )
        netlist = _make_netlist_from_components([u_mcu])
        _apply_safety_classifications(netlist, temper_design_rules)
        assert netlist.components[0].net_class == "Signal"

    def test_ac_component_classified_as_hv(self, temper_design_rules: DesignRules):
        """Component connected to AC_L (AC safety_category) → HighVoltage."""
        relay = Component(
            ref="K1",
            footprint="Relay_THT:Relay_DPDT_10A",
            bounds=(15.0, 10.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="AC_L"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="AC_N"),
            ],
        )
        netlist = _make_netlist_from_components([relay])
        _apply_safety_classifications(netlist, temper_design_rules)
        assert netlist.components[0].net_class == "HighVoltage"

    def test_mixed_hv_and_lv_hv_dominates(self, temper_design_rules: DesignRules):
        """Component with one HV net and one LV net → HighVoltage (HV > LV)."""
        comp = Component(
            ref="Q2",
            footprint="Package_TO_SOT_SMD:SOT-23",
            bounds=(3.0, 3.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="GND"),
            ],
        )
        netlist = _make_netlist_from_components([comp])
        _apply_safety_classifications(netlist, temper_design_rules)
        assert netlist.components[0].net_class == "HighVoltage"

    def test_ac_and_hv_mixed_hv_dominates(self, temper_design_rules: DesignRules):
        """Component with AC_L (AC) and DC_BUS+ (HV) → HighVoltage (HV > AC)."""
        comp = Component(
            ref="Q3",
            footprint="Package_TO_SOT_SMD:SOT-23",
            bounds=(3.0, 3.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="AC_L"),
            ],
        )
        netlist = _make_netlist_from_components([comp])
        _apply_safety_classifications(netlist, temper_design_rules)
        assert netlist.components[0].net_class == "HighVoltage"

    def test_no_pins_defaults_to_signal(self, temper_design_rules: DesignRules):
        """Component with no pins → net_class stays 'Signal'."""
        comp = Component(
            ref="TP1",
            footprint="TestPoint:TestPoint_Pad_D1.0mm",
            bounds=(2.0, 2.0),
            pins=[],
        )
        netlist = _make_netlist_from_components([comp])
        _apply_safety_classifications(netlist, temper_design_rules)
        assert netlist.components[0].net_class == "Signal"

    def test_unconnected_pins_defaults_to_signal(self, temper_design_rules: DesignRules):
        """Component with pins but no net connections → net_class stays 'Signal'."""
        comp = Component(
            ref="J1",
            footprint="Connector:PinHeader_2x5",
            bounds=(10.0, 5.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net=None),
                Pin(name="2", number="2", position=(2.0, 0.0), net=None),
            ],
        )
        netlist = _make_netlist_from_components([comp])
        _apply_safety_classifications(netlist, temper_design_rules)
        assert netlist.components[0].net_class == "Signal"

    def test_unknown_net_name_defaults_to_signal(self, temper_design_rules: DesignRules):
        """Net name not in net_class_assignments → treated as LV → stays 'Signal'."""
        comp = Component(
            ref="R1",
            footprint="Resistor_SMD:R_0603_1608Metric",
            bounds=(1.6, 0.8),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="PWM_H"),
                Pin(name="2", number="2", position=(0.8, 0.0), net="UNKNOWN_NET"),
            ],
        )
        netlist = _make_netlist_from_components([comp])
        _apply_safety_classifications(netlist, temper_design_rules)
        # PWM_H is FinePitch → LV, UNKNOWN_NET is not assigned → stays Signal
        assert netlist.components[0].net_class == "Signal"


# ---------------------------------------------------------------------------
# LossContext integration test
# ---------------------------------------------------------------------------


class TestLossContextIntegration:
    """After classification, LossContext hv/lv indices should be non-empty."""

    def test_hv_and_lv_indices_populated(
        self, temper_design_rules: DesignRules, simple_board: Board
    ):
        """LossContext.from_netlist_and_board produces non-empty hv_indices and lv_indices."""
        hv_comp = Component(
            ref="Q1",
            footprint="Package_TO_SOT_SMD:SOT-23",
            bounds=(3.0, 3.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="GND"),
            ],
        )
        lv_comp = Component(
            ref="U1",
            footprint="Package_QFP:TQFP-32",
            bounds=(7.0, 7.0),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="+3V3"),
                Pin(name="2", number="2", position=(1.0, 0.0), net="GND"),
                Pin(name="3", number="3", position=(0.0, 1.0), net="PWM_H"),
            ],
        )
        netlist = _make_netlist_from_components([hv_comp, lv_comp])
        _apply_safety_classifications(netlist, temper_design_rules)

        context = LossContext.from_netlist_and_board(netlist, simple_board)

        assert context.netlist_data.hv_indices.shape[0] > 0, (
            f"Expected non-empty hv_indices, got shape {context.netlist_data.hv_indices.shape}"
        )
        assert context.netlist_data.lv_indices.shape[0] > 0, (
            f"Expected non-empty lv_indices, got shape {context.netlist_data.lv_indices.shape}"
        )

        # Verify the specific indices
        hv_idx = netlist.get_component_index("Q1")
        lv_idx = netlist.get_component_index("U1")
        assert hv_idx in context.netlist_data.hv_indices.tolist(), "Q1 should be in hv_indices"
        assert lv_idx in context.netlist_data.lv_indices.tolist(), "U1 should be in lv_indices"

    def test_no_hv_components_still_produces_empty_hv_indices(
        self, temper_design_rules: DesignRules, simple_board: Board
    ):
        """All-LV netlist → hv_indices stays empty, lv_indices non-empty."""
        lv_comp = Component(
            ref="R1",
            footprint="Resistor_SMD:R_0603_1608Metric",
            bounds=(1.6, 0.8),
            pins=[
                Pin(name="1", number="1", position=(0.0, 0.0), net="PWM_H"),
                Pin(name="2", number="2", position=(0.8, 0.0), net="GND"),
            ],
        )
        netlist = _make_netlist_from_components([lv_comp])
        _apply_safety_classifications(netlist, temper_design_rules)

        context = LossContext.from_netlist_and_board(netlist, simple_board)

        assert context.netlist_data.hv_indices.shape[0] == 0
        assert context.netlist_data.lv_indices.shape[0] > 0


# ---------------------------------------------------------------------------
# parse_kicad_pcb integration tests
# ---------------------------------------------------------------------------


class TestParseKicadPCBIntegration:
    """Tests that parse_kicad_pcb handles the design_rules parameter correctly."""

    def test_backward_compat_no_design_rules(self, fixtures_dir: Path):
        """parse_kicad_pcb called without design_rules → all components default to 'Signal'."""
        pcb_path = fixtures_dir / "minimal_board.kicad_pcb"
        if not pcb_path.exists():
            pytest.skip(f"Test fixture not found: {pcb_path}")

        result = parse_kicad_pcb(pcb_path, normalize=False)
        for comp in result.netlist.components:
            assert comp.net_class == "Signal", (
                f"Component {comp.ref} should default to 'Signal' when no design_rules, "
                f"got '{comp.net_class}'"
            )

    def test_with_design_rules_classifies_components(self, fixtures_dir: Path):
        """parse_kicad_pcb with design_rules → at least one component gets classified."""
        pcb_path = fixtures_dir / "minimal_board.kicad_pcb"
        if not pcb_path.exists():
            pytest.skip(f"Test fixture not found: {pcb_path}")

        # Build design rules that match the minimal board's nets (GND, VCC, SIG1, SIG2)
        dr = DesignRules(
            net_classes={
                "HighVoltage": NetClassRules(
                    name="HighVoltage",
                    trace_width=3.0,
                    clearance=2.0,
                    via_diameter=1.2,
                    via_drill=0.6,
                    dru_priority=20,
                    safety_category="HV",
                ),
                "Signal": NetClassRules(
                    name="Signal",
                    trace_width=0.2,
                    clearance=0.15,
                    via_diameter=0.6,
                    via_drill=0.3,
                    dru_priority=80,
                    safety_category="LV",
                ),
            },
            net_class_assignments={
                "VCC": "HighVoltage",
            },
        )

        result = parse_kicad_pcb(pcb_path, normalize=False, design_rules=dr)
        # VCC is assigned to HighVoltage, so any component on VCC gets "HighVoltage"
        hv_comps = [c for c in result.netlist.components if c.net_class == "HighVoltage"]
        assert len(hv_comps) > 0, (
            "Expected at least one component classified as 'HighVoltage' "
            "when design_rules with VCC→HighVoltage are provided"
        )
        # GND/SIG1/SIG2 components stay at default "Signal"
        signal_comps = [c for c in result.netlist.components if c.net_class == "Signal"]
        assert len(signal_comps) > 0, "Expected at least one component to stay 'Signal'"
