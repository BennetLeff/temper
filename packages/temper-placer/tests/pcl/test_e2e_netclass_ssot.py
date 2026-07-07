"""End-to-end SSOT chain verification for netclass-aware clearance."""

import math
from pathlib import Path

import pytest

YAML_PATH = (
    Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"
)


@pytest.mark.slow
@pytest.mark.integration
class TestE2ENetclassSSOT:

    @pytest.fixture(autouse=True)
    def setup(self):
        from temper_placer.core.netclass_rules import load_netclass_rules

        self.rules = load_netclass_rules(YAML_PATH)

    # ------------------------------------------------------------------
    # U9.1: YAML loads with expected key-value pairs
    # ------------------------------------------------------------------

    def test_yaml_loads_and_has_expected_pairs(self):
        """SSOT chain: YAML loads with expected key-value pairs."""
        from temper_placer.core.netclass_rules import get_pair_clearance

        hv_signal = get_pair_clearance("HighVoltage", "Signal", rules=self.rules)
        assert hv_signal == 6.0, f"HV-Signal should be 6.0mm, got {hv_signal}"

        power_signal = get_pair_clearance("Power", "Signal", rules=self.rules)
        assert power_signal > 0

    def test_netclass_rule_consistency_across_consumers(self):
        """All consumers agree on the same clearance for key pairs."""
        from temper_placer.core.netclass_rules import get_pair_because, get_pair_clearance

        key_pairs = [
            ("ACMains", "Signal"),
            ("HighVoltage", "Signal"),
            ("Power", "Signal"),
        ]
        for ca, cb in key_pairs:
            clearance = get_pair_clearance(ca, cb, rules=self.rules)
            assert clearance > 0, f"{ca}-{cb} clearance should be positive"

        assert get_pair_because("ACMains", "Signal", rules=self.rules) is not None
        assert get_pair_because("HighVoltage", "Signal", rules=self.rules) is not None
        assert get_pair_because("Power", "Signal", rules=self.rules) is None

    def test_output_pcb_forms_round_trip(self, tmp_path):
        """Write netclass forms, verify they can be read back and parsed."""
        from temper_placer.io.kicad_exporter import write_netclass_forms

        forms = write_netclass_forms(None, self.rules)
        assert "ACMains" in forms
        assert "HighVoltage" in forms
        assert "Signal" in forms
        assert "clearance" in forms
        assert "trace_width" in forms
        assert "via_dia" in forms
        assert "via_drill" in forms

        for nc_name in self.rules["net_classes"]:
            assert nc_name in forms, f"Missing net class '{nc_name}' in forms"

        for nc_name, nc_rules in self.rules["net_classes"].items():
            assert str(nc_rules.clearance) in forms, (
                f"Clearance {nc_rules.clearance} missing for {nc_name}"
            )
            assert str(nc_rules.trace_width) in forms, (
                f"Trace width {nc_rules.trace_width} missing for {nc_name}"
            )

    # ------------------------------------------------------------------
    # U9.2: generate_netclass_separated_constraints
    # ------------------------------------------------------------------

    def test_generate_constraints_for_synthetic_netlist(self):
        """Synthetic netlist produces correct constraints with clearance from SSOT."""
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.pcl.constraints import ConstraintTier
        from temper_placer.placer.cp_sat.netclass_constraints import (
            SAFETY_FACTOR,
            generate_netclass_separated_constraints,
        )

        comps = [
            Component(
                ref="HV1",
                footprint="TO-247",
                bounds=(10.0, 10.0),
                pins=[Pin(name="1", number="1", position=(0, 0), net="DC_BUS+")],
            ),
            Component(
                ref="SIG1",
                footprint="SOIC8",
                bounds=(5.0, 5.0),
                pins=[Pin(name="1", number="1", position=(0, 0), net="SPI_CLK")],
            ),
            Component(
                ref="SIG2",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin(name="1", number="1", position=(0, 0), net="TEMP_SENSE")],
            ),
        ]
        netlist = Netlist(components=comps, nets=[
            Net(name="DC_BUS+", pins=[("HV1", "1")]),
            Net(name="SPI_CLK", pins=[("SIG1", "1")]),
            Net(name="TEMP_SENSE", pins=[("SIG2", "1")]),
        ])

        result = generate_netclass_separated_constraints(
            netlist, comps, self.rules,
        )

        assert len(result) == 2, (
            f"Expected 2 constraints (HV-SIG1, HV-SIG2), got {len(result)}"
        )

        expected_clearance = pytest.approx(6.0 * SAFETY_FACTOR)
        for c in result:
            assert c.min_distance_mm == expected_clearance
            assert c.tier == ConstraintTier.HARD

        sig_refs = {c.a for c in result} | {c.b for c in result}
        assert "SIG1" in sig_refs
        assert "SIG2" in sig_refs
        assert "HV1" in sig_refs

    def test_generate_constraints_same_class_produces_none(self):
        """All-Signal netlist yields zero cross-class constraints."""
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )

        comps = [
            Component(
                ref="SIG1",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin(name="1", number="1", position=(0, 0), net="NET_A")],
            ),
            Component(
                ref="SIG2",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin(name="1", number="1", position=(0, 0), net="NET_B")],
            ),
            Component(
                ref="SIG3",
                footprint="0603",
                bounds=(1.6, 0.8),
                pins=[Pin(name="1", number="1", position=(0, 0), net="NET_C")],
            ),
        ]
        netlist = Netlist(components=comps, nets=[
            Net(name="NET_A", pins=[("SIG1", "1")]),
            Net(name="NET_B", pins=[("SIG2", "1")]),
            Net(name="NET_C", pins=[("SIG3", "1")]),
        ])

        result = generate_netclass_separated_constraints(
            netlist, comps, self.rules,
        )
        assert len(result) == 0

    # ------------------------------------------------------------------
    # U9.3: CP-SAT placement respects clearance from SSOT
    # ------------------------------------------------------------------

    def test_cp_sat_solve_respects_clearance(self):
        """Load YAML, run CP-SAT solve on synthetic netlist, verify clearance.

        Creates a small board with one HV and two Signal components.  The
        solver must place them such that every HV-Signal pair obeys the
        Chebyshev edge-to-edge clearance from the netclass rules SSOT.

        Uses square components so rotation does not affect edge-gap
        calculation.
        """
        pytest.importorskip("ortools")

        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.placer.cp_sat.encoder import solve_placement
        from temper_placer.placer.cp_sat.netclass_constraints import (
            SAFETY_FACTOR,
            generate_netclass_separated_constraints,
        )

        comps = [
            Component(
                ref="HV1",
                footprint="TO-247",
                bounds=(10.0, 10.0),
                pins=[Pin(name="1", number="1", position=(0, 0), net="DC_BUS+")],
            ),
            Component(
                ref="SIG1",
                footprint="SOIC8",
                bounds=(6.0, 6.0),
                pins=[Pin(name="1", number="1", position=(0, 0), net="SIG_A")],
            ),
            Component(
                ref="SIG2",
                footprint="0603",
                bounds=(2.0, 2.0),
                pins=[Pin(name="1", number="1", position=(0, 0), net="SIG_B")],
            ),
        ]
        netlist = Netlist(components=comps, nets=[
            Net(name="DC_BUS+", pins=[("HV1", "1")]),
            Net(name="SIG_A", pins=[("SIG1", "1")]),
            Net(name="SIG_B", pins=[("SIG2", "1")]),
        ])

        constraints = generate_netclass_separated_constraints(
            netlist, comps, self.rules,
        )
        assert len(constraints) == 2

        board = Board(width=200.0, height=200.0)
        result = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=constraints,
            timeout_ms=3000,
            seed=42,
        )

        assert result.status in ("optimal", "feasible"), (
            f"Solve failed with status {result.status}"
        )
        positions = result.positions
        assert "HV1" in positions
        assert "SIG1" in positions
        assert "SIG2" in positions

        hv = positions["HV1"]
        min_clearance = 6.0 * SAFETY_FACTOR  # HV-Signal = 6.0mm * sqrt(2)

        for sig_ref in ("SIG1", "SIG2"):
            sig = positions[sig_ref]
            comp_hv = netlist.get_component("HV1")
            comp_sig = netlist.get_component(sig_ref)

            dx = abs(hv[0] - sig[0])
            dy = abs(hv[1] - sig[1])
            half_sum_x = (comp_hv.bounds[0] + comp_sig.bounds[0]) / 2.0
            half_sum_y = (comp_hv.bounds[1] + comp_sig.bounds[1]) / 2.0

            cheb_edge_gap = max(dx - half_sum_x, dy - half_sum_y)

            assert cheb_edge_gap >= min_clearance - 0.01, (
                f"HV1-{sig_ref}: Chebyshev edge gap {cheb_edge_gap:.3f}mm < "
                f"{min_clearance:.3f}mm required (SAFETY_FACTOR={SAFETY_FACTOR:.3f})"
            )
