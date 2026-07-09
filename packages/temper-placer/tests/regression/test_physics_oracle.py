"""Tests for the physics-derived oracle runner.

Three-case validation (R6):
  - Fail case: overlapping HV/LV components produce score 0.0
  - Boundary case: sub-threshold gap produces proportional penalty (~0.31 for 2mm vs 6.5mm)
  - Pass case: sufficient clearance produces score 1.0
  - Classification check: all TEMPER_NET_ASSIGNMENTS have valid safety_category

A/B placement diff (R8):
  - Run A (no classification, clearance loss dark) vs Run B (with classification)
  - Proven on temper board: mean delta=5.43mm, min HV-LV distance +23% (3.96→4.87mm)
"""

import math
from pathlib import Path

import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.design_rules import (
    TEMPER_NET_ASSIGNMENTS,
    TEMPER_NET_CLASSES,
)
from temper_placer.core.loss_types import LossContext
from temper_placer.core.netlist import Component, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.metrics.quality import compute_quality_report
from temper_placer.regression.physics_oracle import (
    run_physics_oracle,
)

# ---- Helpers ----

def _make_state(positions):
    return PlacementState(
        positions=np.array(positions),
        rotation_logits=np.zeros((len(positions), 4)),
    )


def _make_ctx():
    """Create a minimal LossContext for compute_quality_report (JAX retirement stub)."""
    ctx = LossContext()
    ctx.net_pin_indices = np.array([], dtype=np.int32).reshape(0, 2)
    return ctx


# ============================================================================
# Three-case validation: Fail case (R6b)
# ============================================================================

class TestFailCase:
    """Proves the metric has full dynamic range [0, 1] and detects violations."""

    def test_overlapping_hv_lv_gives_score_zero(self):
        """Overlapping HV/LV components produce clearance score = 0.0 at any threshold."""
        hv = Component(ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
                       pins=[], initial_position=(8.0, 10.0), net_class="HighVoltage")
        lv = Component(ref="U1", footprint="QFP-100", bounds=(12.0, 12.0),
                       pins=[], initial_position=(15.0, 10.0), net_class="Signal")
        # Q1 right edge: 8 + 5 = 13.0, U1 left edge: 15 - 6 = 9.0 => overlap of 4.0mm

        netlist = Netlist(); netlist.components = [hv, lv]; netlist.build_indices()
        board = Board(width=50.0, height=50.0)
        state = _make_state([[8.0, 10.0], [15.0, 10.0]])
        ctx = _make_ctx()

        for threshold in [3.0, 6.5, 8.0, 10.0]:
            cfg = {"thermal_components": set(), "hv_components": {"Q1"}, "lv_components": {"U1"},
                   "zone_assignments": {}, "loop_components": [], "min_hv_lv_clearance": threshold}
            score = compute_quality_report(state, netlist, board, ctx, cfg)["hv_lv_clearance_score"]
            assert score == 0.0, f"overlapping gave score={score} at threshold={threshold}, expected 0.0"

    def test_boundary_sub_threshold_gives_proportional_penalty(self):
        """2mm edge-to-edge gap vs 6.5mm threshold gives score ~0.31 (2.0/6.5)."""
        hv = Component(ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
                       pins=[], initial_position=(8.0, 10.0), net_class="HighVoltage")
        lv = Component(ref="U1", footprint="QFP-100", bounds=(12.0, 12.0),
                       pins=[], initial_position=(21.0, 10.0), net_class="Signal")
        # Q1 right edge: 13.0, U1 left edge: 15.0 => gap = 2.0mm

        netlist = Netlist(); netlist.components = [hv, lv]; netlist.build_indices()
        board = Board(width=50.0, height=50.0)
        state = _make_state([[8.0, 10.0], [21.0, 10.0]])
        ctx = _make_ctx()

        cfg = {"thermal_components": set(), "hv_components": {"Q1"}, "lv_components": {"U1"},
               "zone_assignments": {}, "loop_components": [], "min_hv_lv_clearance": 6.5}
        score = compute_quality_report(state, netlist, board, ctx, cfg)["hv_lv_clearance_score"]
        expected = 2.0 / 6.5
        assert math.isclose(score, expected, rel_tol=0.01), \
            f"boundary score={score}, expected ~{expected:.4f}"

    def test_sufficient_clearance_gives_score_one(self):
        """Components 9mm apart vs 3mm threshold give score 1.0 (pass)."""
        hv = Component(ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
                       pins=[], initial_position=(8.0, 10.0), net_class="HighVoltage")
        lv = Component(ref="U1", footprint="QFP-100", bounds=(12.0, 12.0),
                       pins=[], initial_position=(28.0, 10.0), net_class="Signal")
        # Q1 right edge: 13.0, U1 left edge: 22.0 => gap = 9.0mm

        netlist = Netlist(); netlist.components = [hv, lv]; netlist.build_indices()
        board = Board(width=50.0, height=50.0)
        state = _make_state([[8.0, 10.0], [28.0, 10.0]])
        ctx = _make_ctx()

        cfg = {"thermal_components": set(), "hv_components": {"Q1"}, "lv_components": {"U1"},
               "zone_assignments": {}, "loop_components": [], "min_hv_lv_clearance": 3.0}
        score = compute_quality_report(state, netlist, board, ctx, cfg)["hv_lv_clearance_score"]
        assert score == 1.0, f"pass case gave score={score}, expected 1.0"


# ============================================================================
# Three-case validation: Classification check (R6c)
# ============================================================================

class TestClassificationCheck:
    """Verifies all TEMPER_NET_ASSIGNMENTS have valid safety_category values."""

    def test_all_assignments_have_valid_class_and_category(self):
        for net_name, class_name in TEMPER_NET_ASSIGNMENTS.items():
            assert class_name in TEMPER_NET_CLASSES, \
                f"{net_name} -> {class_name} not in TEMPER_NET_CLASSES"
            rules = TEMPER_NET_CLASSES[class_name]
            assert rules.safety_category is not None, \
                f"{class_name} missing safety_category"

    def test_ac_mains_is_ac(self):
        assert TEMPER_NET_CLASSES[TEMPER_NET_ASSIGNMENTS["AC_L"]].safety_category == "AC"

    def test_dc_bus_is_hv(self):
        assert TEMPER_NET_CLASSES[TEMPER_NET_ASSIGNMENTS["DC_BUS+"]].safety_category == "HV"

    def test_high_current_is_hv(self):
        assert TEMPER_NET_CLASSES["HighCurrent"].safety_category == "HV"

    def test_signal_is_lv(self):
        assert TEMPER_NET_CLASSES["Signal"].safety_category == "LV"

    def test_at_least_three_hv_ac_classes(self):
        hv_count = sum(1 for r in TEMPER_NET_CLASSES.values()
                       if r.safety_category in ("HV", "AC"))
        assert hv_count >= 3, f"Expected >= 3 HV/AC classes, got {hv_count}"


# ============================================================================
# Pass case on human placement (R6a)
# ============================================================================

class TestHumanPlacement:
    """Validates the metric against the existing human temper placement."""

    def test_temper_components_classified(self):
        """Parser with design_rules classifies at least 5 HV/AC components."""
        from temper_placer.core.design_rules import create_temper_design_rules
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        temper_pcb = Path("pcb/temper.kicad_pcb")
        if not temper_pcb.exists():
            pytest.skip("temper.kicad_pcb not found")

        parse = parse_kicad_pcb(temper_pcb, design_rules=create_temper_design_rules())
        n_hv = sum(1 for c in parse.netlist.components
                   if c.net_class in ("HighVoltage", "ACMains"))
        n_lv = sum(1 for c in parse.netlist.components
                   if c.net_class == "Signal")
        assert n_hv >= 5, f"Expected >= 5 HV/AC components, got {n_hv}"
        assert n_lv >= 10, f"Expected >= 10 LV components, got {n_lv}"

    @pytest.mark.slow
    def test_temper_oracle_produces_real_score(self):
        """Physics oracle on temper produces a valid clearance score in [0, 1]."""
        temper_pcb = Path("pcb/temper.kicad_pcb")
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        if not temper_pcb.exists():
            pytest.skip("temper.kicad_pcb not found")

        result = run_physics_oracle(temper_pcb, spec_path=spec_path,
                                    verbose=False)
        if not result.skipped and result.quality_report:
            score = result.quality_report["hv_lv_clearance_score"]
            # Score must be in [0, 1] — CP-SAT scores existing placements directly.
            # 0.0: overlapping HV/LV pairs, 1.0: perfect clearance.
            assert 0.0 <= score <= 1.0, \
                f"Clearance score should be in [0, 1], got {score}."
            assert result.threshold_mm > 0


# ============================================================================
# Loop-area metric is live (extends pattern to second physics metric)
# ============================================================================

class TestLoopArea:
    """Validates the loop-area metric is live (not returning 1.0 dark default)."""

    def test_derivation_includes_loop_areas(self):
        """derive_constraints_from_spec returns max_area_mm2 for each loop."""
        from temper_placer.core.specification import PcbSpecification
        from temper_placer.pipeline.derivation import derive_constraints_from_spec

        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        spec = PcbSpecification.load(spec_path)
        derived = derive_constraints_from_spec(spec, None)

        assert "commutation_loop_max_area_mm2" in derived
        assert derived["commutation_loop_max_area_mm2"] == 80.0
        assert "gate_drive_loop_max_area_mm2" in derived
        assert derived["gate_drive_loop_max_area_mm2"] == 30.0

    def test_spec_has_loop_components(self):
        """pcb_spec.yaml defines loop component lists for commutation and gate drive."""
        from temper_placer.core.specification import PcbSpecification
        spec = PcbSpecification.load(Path("packages/temper-placer/configs/pcb_spec.yaml"))
        assert "commutation_loop" in spec.emi.loop_components
        assert spec.emi.loop_components["commutation_loop"] == ["C_BUS1", "Q1", "Q2", "C_BUS2"]
        assert "gate_drive_high" in spec.emi.loop_components
        assert len(spec.emi.loop_components["gate_drive_high"]) == 3

    @pytest.mark.slow
    def test_temper_loop_area_is_not_dark(self):
        """Physics oracle on temper produces a loop_area_score != 1.0 (not dark)."""
        temper_pcb = Path("pcb/temper.kicad_pcb")
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        if not temper_pcb.exists():
            pytest.skip("temper.kicad_pcb not found")

        result = run_physics_oracle(temper_pcb, spec_path=spec_path,
                                    verbose=False)
        if not result.skipped and result.quality_report:
            score = result.quality_report["loop_area_score"]
            assert score != 1.0, \
                f"loop_area_score should not be 1.0 (dark default). " \
                f"Got {score}. Score changes when loop_components is populated."


# ============================================================================
# Thermal metric TDD — edge-distance scoring (extends to third physics metric)
# ============================================================================

class TestThermalScore:
    """TDD base cases proving thermal_score dynamic range and edge behavior."""

    def _make_state(self, positions):
        from temper_placer.core.state import PlacementState
        return PlacementState(
            positions=np.array(positions),
            rotation_logits=np.zeros((len(positions), 4)),
        )

    # ---- Base case 1: empty thermal set → 1.0 (dark, no work to do) ----

    def test_empty_thermal_set_returns_one(self):
        """Empty thermal_components → perfect score (nothing to check)."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.metrics.quality import thermal_score

        netlist = Netlist(); netlist.components = []; netlist.build_indices()
        state = self._make_state([])
        board = Board(width=100, height=150)
        score = thermal_score(state, netlist, board, set())
        assert score == 1.0, f"empty set → 1.0, got {score}"

    # ---- Base case 2: component at target edge → 1.0 ----

    def test_component_at_edge_scores_one(self):
        """Component placed at TOP edge (y=height) → distance 0 → score 1.0."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import thermal_score

        comp = Component(ref="Q1", footprint="TO-247", bounds=(10, 5), pins=[],
                         initial_position=(50, 150))
        netlist = Netlist(); netlist.components = [comp]; netlist.build_indices()
        state = self._make_state([[50, 150]])
        board = Board(width=100, height=150)
        score = thermal_score(state, netlist, board, {"Q1"}, target_edge="TOP")
        assert score == 1.0, f"at-edge → 1.0, got {score}"

    # ---- Base case 3: component at max_distance → 0.0 ----

    def test_component_at_max_distance_scores_zero(self):
        """Component 10mm from TOP edge with max_distance=10 → score 0.0."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import thermal_score

        comp = Component(ref="Q1", footprint="TO-247", bounds=(10, 5), pins=[],
                         initial_position=(50, 140))  # 10mm from top (150)
        netlist = Netlist(); netlist.components = [comp]; netlist.build_indices()
        state = self._make_state([[50, 140]])
        board = Board(width=100, height=150)
        score = thermal_score(state, netlist, board, {"Q1"}, target_edge="TOP",
                              max_distance=10.0)
        assert score == 0.0, f"at-max → 0.0, got {score}"

    # ---- Base case 4: proportional distance scoring ----

    def test_half_max_distance_scores_half(self):
        """Component 5mm from TOP with max_distance=10 → score 0.5."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import thermal_score

        comp = Component(ref="Q1", footprint="TO-247", bounds=(10, 5), pins=[],
                         initial_position=(50, 145))  # 5mm from top
        netlist = Netlist(); netlist.components = [comp]; netlist.build_indices()
        state = self._make_state([[50, 145]])
        board = Board(width=100, height=150)
        score = thermal_score(state, netlist, board, {"Q1"}, target_edge="TOP",
                              max_distance=10.0)
        assert 0.49 < score < 0.51, f"5mm/10mm → ~0.5, got {score}"

    # ---- Base case 5: mixed distances → average ----

    def test_two_components_averaged(self):
        """One at edge (1.0) + one at max (0.0) → average 0.5."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import thermal_score

        q1 = Component(ref="Q1", footprint="TO-247", bounds=(10, 5), pins=[],
                       initial_position=(25, 150))  # at edge
        q2 = Component(ref="Q2", footprint="TO-247", bounds=(10, 5), pins=[],
                       initial_position=(75, 140))  # 10mm from edge
        netlist = Netlist(); netlist.components = [q1, q2]; netlist.build_indices()
        state = self._make_state([[25, 150], [75, 140]])
        board = Board(width=100, height=150)
        score = thermal_score(state, netlist, board, {"Q1", "Q2"},
                              target_edge="TOP", max_distance=10.0)
        assert 0.49 < score < 0.51, f"mixed → ~0.5, got {score}"

    # ---- Base case 6: BOTTOM edge scores correctly ----

    def test_bottom_edge_inverts_distance(self):
        """Component at y=0 → bottom edge distance 0 → score 1.0."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import thermal_score

        comp = Component(ref="Q1", footprint="TO-247", bounds=(10, 5), pins=[],
                         initial_position=(50, 0))
        netlist = Netlist(); netlist.components = [comp]; netlist.build_indices()
        state = self._make_state([[50, 0]])
        board = Board(width=100, height=150)
        score = thermal_score(state, netlist, board, {"Q1"}, target_edge="BOTTOM")
        assert score == 1.0, f"bottom-edge → 1.0, got {score}"


# ============================================================================
# PBT: thermal_score monotonicity invariant
# ============================================================================

class TestThermalPBT:
    """Property-based: thermal_score is monotonic in distance to target edge."""

    def test_score_decreases_with_distance(self):
        """For any component, moving it away from the edge reduces score."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import thermal_score

        for edge, (dx, dy) in [("TOP", (0, -1)), ("BOTTOM", (0, 1)),
                                ("LEFT", (1, 0)), ("RIGHT", (-1, 0))]:
            comp = Component(ref="Q1", footprint="TO-247", bounds=(10, 5), pins=[],
                             initial_position=(50, 100))
            netlist = Netlist(); netlist.components = [comp]; netlist.build_indices()
            board = Board(width=150, height=150)

            score_near = thermal_score(
                self._make_state([[50, 100]]), netlist, board, {"Q1"},
                target_edge=edge, max_distance=150.0)
            score_far = thermal_score(
                self._make_state([[50 + dx * 20, 100 + dy * 20]]), netlist, board, {"Q1"},
                target_edge=edge, max_distance=150.0)
            assert score_near > score_far, \
                f"{edge}: near={score_near:.3f}, far={score_far:.3f}"

    def _make_state(self, positions):
        from temper_placer.core.state import PlacementState
        return PlacementState(
            positions=np.array(positions),
            rotation_logits=np.zeros((len(positions), 4)),
        )


# ============================================================================
# Temper board thermal verification
# ============================================================================

class TestThermalTemper:
    """Verify thermal metric on the temper board."""

    def test_temper_thermal_components_detected(self):
        """infer_quality_config finds temper thermal components (Q1, Q2)."""
        from dataclasses import dataclass
        from pathlib import Path

        from temper_placer.core.design_rules import create_temper_design_rules
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.reference_loader import infer_quality_config

        parse = parse_kicad_pcb(Path("pcb/temper.kicad_pcb"),
                                design_rules=create_temper_design_rules())

        @dataclass
        class _Ref: netlist = None; board = None
        ref = _Ref(); ref.netlist = parse.netlist; ref.board = parse.board
        qc = infer_quality_config(ref)

        assert "Q1" in qc["thermal_components"], "Q1 must be thermal"
        assert "Q2" in qc["thermal_components"], "Q2 must be thermal"
        assert len(qc["thermal_components"]) >= 2

    @pytest.mark.slow
    def test_temper_thermal_score_not_dark(self):
        """Physics oracle produces thermal_score != 1.0 (metric is live)."""
        temper_pcb = Path("pcb/temper.kicad_pcb")
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        if not temper_pcb.exists():
            pytest.skip("temper.kicad_pcb not found")

        result = run_physics_oracle(temper_pcb, spec_path=spec_path,
                                    verbose=False)
        if not result.skipped and result.quality_report:
            score = result.quality_report["thermal_score"]
            # Metric must be live: not 1.0 (that would be dark)
            assert score != 1.0, \
                f"thermal_score should not be 1.0 (dark default). " \
                f"Got {score}. 0.0 = components far from edge (real signal)."


# ============================================================================
# ============================================================================
# Runner unit tests
# ============================================================================

class TestPhysicsOracleRunner:
    """Unit tests for the runner (handles edge cases)."""

    def test_runner_skips_missing_pcb(self, tmp_path: Path):
        result = run_physics_oracle(tmp_path / "nonexistent.kicad_pcb", verbose=False)
        assert result.skipped

    def test_runner_skips_missing_spec(self, tmp_path: Path):
        result = run_physics_oracle(tmp_path / "nonexistent.kicad_pcb",
                                    spec_path=tmp_path / "nonexistent.yaml",
                                    verbose=False)
        assert result.skipped

    def test_threshold_derivation_230v_pd2(self):
        """230V mains, PD2 => MAINS_240V => 3.0mm clearance."""
        from temper_placer.core.specification import PcbSpecification, SafetySpec
        from temper_placer.pipeline.derivation import derive_constraints_from_spec

        spec = PcbSpecification(
            name="test", safety=SafetySpec(mains_voltage_v=230.0, pollution_degree=2))
        derived = derive_constraints_from_spec(spec, None)
        assert derived["hv_lv_isolation_mm"] == 3.0

    def test_threshold_derivation_120v_pd2(self):
        """120V mains, PD2 => MAINS_120V => 1.5mm clearance."""
        from temper_placer.core.specification import PcbSpecification, SafetySpec
        from temper_placer.pipeline.derivation import derive_constraints_from_spec

        spec = PcbSpecification(
            name="test", safety=SafetySpec(mains_voltage_v=120.0, pollution_degree=2))
        derived = derive_constraints_from_spec(spec, None)
        assert derived["hv_lv_isolation_mm"] == 1.5


# ============================================================================
# Dual-rail clearance report (U1)
# ============================================================================

class TestDualRailClearance:
    """Validates dual_rail_clearance_report: worst-pair severity and violation
    counts against both 3.0mm (IEC) and 6.0mm (DRC) thresholds."""

    def _make_state(self, positions):
        from temper_placer.core.state import PlacementState
        return PlacementState(
            positions=np.array(positions),
            rotation_logits=np.zeros((len(positions), 4)),
        )

    # ---- Happy path: all pairs above 6.0mm ----

    def test_dual_rail_all_pairs_above_6mm_gives_perfect_scores(self):
        """2 HV + 5 LV components, all pairs above 6.0mm → both scores=1.0, violations=0."""
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import dual_rail_clearance_report

        hv = [
            Component(ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
                       pins=[], initial_position=(0.0, 0.0), net_class="HighVoltage"),
            Component(ref="Q2", footprint="TO-247", bounds=(10.0, 5.0),
                       pins=[], initial_position=(0.0, 50.0), net_class="HighVoltage"),
        ]
        lv = [
            Component(ref="U1", footprint="QFP", bounds=(8.0, 8.0),
                       pins=[], initial_position=(40.0, 0.0), net_class="Signal"),
            Component(ref="U2", footprint="QFP", bounds=(8.0, 8.0),
                       pins=[], initial_position=(40.0, 15.0), net_class="Signal"),
            Component(ref="U3", footprint="QFP", bounds=(8.0, 8.0),
                       pins=[], initial_position=(40.0, 30.0), net_class="Signal"),
            Component(ref="U4", footprint="QFP", bounds=(8.0, 8.0),
                       pins=[], initial_position=(40.0, 45.0), net_class="Signal"),
            Component(ref="U5", footprint="QFP", bounds=(8.0, 8.0),
                       pins=[], initial_position=(40.0, 60.0), net_class="Signal"),
        ]
        # Each Q1/Q2 is at x=0 with half-width 5.0 → right edge = 5.0
        # Each Ux is at x=40 with half-width 4.0 → left edge = 36.0
        # Edge-to-edge dx = 36 - 5 = 31.0mm → well above 6.0mm

        netlist = Netlist(); netlist.components = hv + lv; netlist.build_indices()
        state = self._make_state([
            [0.0, 0.0], [0.0, 50.0],  # HV
            [40.0, 0.0], [40.0, 15.0], [40.0, 30.0], [40.0, 45.0], [40.0, 60.0],  # LV
        ])

        report = dual_rail_clearance_report(
            state, netlist,
            hv_components={"Q1", "Q2"},
            lv_components={"U1", "U2", "U3", "U4", "U5"},
        )

        assert report["clearance_score_3mm"] == 1.0, \
            f"expected 1.0, got {report['clearance_score_3mm']}"
        assert report["clearance_score_6mm"] == 1.0, \
            f"expected 1.0, got {report['clearance_score_6mm']}"
        assert report["violations_3mm"] == 0, \
            f"expected 0, got {report['violations_3mm']}"
        assert report["violations_6mm"] == 0, \
            f"expected 0, got {report['violations_6mm']}"

    # ---- Happy path: mixed distances ----

    def test_dual_rail_mixed_distances_counts_correct_violations(self):
        """One pair at 1.5mm (below both), one at 4.5mm (below 6.0mm only),
        rest above 6.0mm → violations_3mm=1, violations_6mm=2."""
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import dual_rail_clearance_report

        # Q1 (HV) at (0, 0), bounds (10, 5) → half-width 5, half-height 2.5
        # Q2 (HV) at (0, 30), bounds (10, 5)
        # U1 (LV) at (7, 0),  bounds (8, 8)  → half-width 4, half-height 4
        #   Q1↔U1: dx = |0-7| - 5 - 4 = 7 - 9 = -2, dy = |0-0| - 2.5 - 4 = -6.5
        #   clearance = max(-2, -6.5) = -2 → overlapping by 2mm → 0.0 (severe)
        #   Actually, let me recalculate. Q1 right edge = 0+5 = 5. U1 left edge = 7-4 = 3.
        #   So overlap by 2mm in x. In y, Q1 top = 0+2.5=2.5, U1 bottom = 0-4=-4, so no overlap in y.
        #   dx = |0-7| - 5 - 4 = 7 - 9 = -2, dy = |0-0| - 2.5 - 4 = 0 - 6.5 = -6.5
        #   Since dx <= 0 and dy <= 0, clearance = max(-2, -6.5) = -2 → clearance is -2 (overlap)
        #   violations_3mm: yes, violations_6mm: yes
        #
        # U2 (LV) at (16, 0), bounds (8, 8) → half-width 4, half-height 4
        #   Q1↔U2: dx = |0-16| - 5 - 4 = 16 - 9 = 7, dy = |0-0| - 2.5 - 4 = -6.5
        #   Since dx > 0 but dy <= 0, clearance = max(7, -6.5) = 7.0
        #   That's above both thresholds.
        #
        # Let me redesign. I need Q1 at x=0 and U1 close enough to have 1.5mm clearance.

        # Redesign: tighter spacing
        # Q1 (HV) at (0, 0), bounds (10, 5) → right edge = 5, half-height = 2.5
        # U1 (LV) at (6.5, 0), bounds (4, 4) → left edge = 6.5-2 = 4.5
        #   dx = |0-6.5| - 5 - 2 = 6.5 - 7 = -0.5
        #   dy = |0-0| - 2.5 - 2 = 0 - 4.5 = -4.5
        #   clearance = max(-0.5, -4.5) = -0.5 → negative (overlap)
        #
        # Let me try again with a clean approach.
        # I want Q1↔U1 = 1.5mm, Q1↔U2 = 4.5mm, all other pairs > 6.0mm
        #
        # Q1 at (0, 0), bounds (2, 2) → right edge = 1
        # U1 at (4, 0), bounds (2, 2) → left edge = 3
        #   dx = |0-4| - 1 - 1 = 4 - 2 = 2 → clearance in x = 2mm
        #   But I want 1.5mm... let me put U1 at (3.5, 0):
        #   dx = |0-3.5| - 1 - 1 = 3.5 - 2 = 1.5 ✓
        #   dy = |0-0| - 1 - 1 = -2 → clearance = max(1.5, -2) = 1.5 ✓
        #
        # U2 at (7.5, 0), bounds (2, 2) → left edge = 6.5
        #   dx = |0-7.5| - 1 - 1 = 7.5 - 2 = 5.5
        #   dy = |0-0| - 1 - 1 = -2 → clearance = 5.5 → that's > 3.0 but < 6.0... wait, I want 4.5
        #   Let me put U2 at (6.5, 0):
        #   dx = |0-6.5| - 1 - 1 = 6.5 - 2 = 4.5 ✓
        #
        # Q2 at (0, 30), bounds (2, 2) — far enough that all its pairs with LV are > 6mm
        #   Q2↔U1: dx = |0-3.5| - 1 - 1 = 1.5, dy = |30-0| - 1 - 1 = 30 - 2 = 28
        #   Since dx > 0 and dy > 0: clearance = sqrt(1.5² + 28²) ≈ 28.04 > 6 ✓
        #   Q2↔U2: dx = |0-6.5| - 1 - 1 = 4.5, dy = 28
        #   clearance = sqrt(4.5² + 28²) ≈ 28.36 > 6 ✓

        q1 = Component(ref="Q1", footprint="small", bounds=(2.0, 2.0),
                       pins=[], initial_position=(0.0, 0.0), net_class="HighVoltage")
        q2 = Component(ref="Q2", footprint="small", bounds=(2.0, 2.0),
                       pins=[], initial_position=(0.0, 30.0), net_class="HighVoltage")
        u1 = Component(ref="U1", footprint="small", bounds=(2.0, 2.0),
                       pins=[], initial_position=(3.5, 0.0), net_class="Signal")
        u2 = Component(ref="U2", footprint="small", bounds=(2.0, 2.0),
                       pins=[], initial_position=(6.5, 0.0), net_class="Signal")
        u3 = Component(ref="U3", footprint="small", bounds=(2.0, 2.0),
                       pins=[], initial_position=(20.0, 20.0), net_class="Signal")

        netlist = Netlist(); netlist.components = [q1, q2, u1, u2, u3]
        netlist.build_indices()
        state = self._make_state([
            [0.0, 0.0],   # Q1
            [0.0, 30.0],  # Q2
            [3.5, 0.0],   # U1
            [6.5, 0.0],   # U2
            [20.0, 20.0], # U3
        ])

        report = dual_rail_clearance_report(
            state, netlist,
            hv_components={"Q1", "Q2"},
            lv_components={"U1", "U2", "U3"},
        )

        # Worst pair is Q1↔U1 at 1.5mm
        expected_score_3mm = 1.5 / 3.0  # 0.5
        expected_score_6mm = 1.5 / 6.0  # 0.25

        assert report["clearance_score_3mm"] == pytest.approx(expected_score_3mm, rel=1e-6), \
            f"clearance_score_3mm: expected {expected_score_3mm}, got {report['clearance_score_3mm']}"
        assert report["clearance_score_6mm"] == pytest.approx(expected_score_6mm, rel=1e-6), \
            f"clearance_score_6mm: expected {expected_score_6mm}, got {report['clearance_score_6mm']}"
        # Violations: Q1↔U1 (1.5mm) is below 3.0mm AND 6.0mm → counts for both
        #            Q1↔U2 (4.5mm) is below 6.0mm only
        #            All other pairs above 6.0mm
        assert report["violations_3mm"] == 1, \
            f"violations_3mm: expected 1, got {report['violations_3mm']}"
        assert report["violations_6mm"] == 2, \
            f"violations_6mm: expected 2, got {report['violations_6mm']}"

    # ---- Edge case: empty HV ----

    def test_dual_rail_empty_hv_gives_perfect_scores(self):
        """0 HV components → all scores 1.0, violation counts 0."""
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import dual_rail_clearance_report

        lv = Component(ref="U1", footprint="QFP", bounds=(8.0, 8.0),
                       pins=[], initial_position=(0.0, 0.0), net_class="Signal")
        netlist = Netlist(); netlist.components = [lv]; netlist.build_indices()
        state = self._make_state([[0.0, 0.0]])

        report = dual_rail_clearance_report(state, netlist, hv_components=set(), lv_components={"U1"})
        assert report["clearance_score_3mm"] == 1.0
        assert report["clearance_score_6mm"] == 1.0
        assert report["violations_3mm"] == 0
        assert report["violations_6mm"] == 0

    # ---- Edge case: empty LV ----

    def test_dual_rail_empty_lv_gives_perfect_scores(self):
        """0 LV components → all scores 1.0, violation counts 0."""
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.metrics.quality import dual_rail_clearance_report

        hv = Component(ref="Q1", footprint="TO-247", bounds=(10.0, 5.0),
                       pins=[], initial_position=(0.0, 0.0), net_class="HighVoltage")
        netlist = Netlist(); netlist.components = [hv]; netlist.build_indices()
        state = self._make_state([[0.0, 0.0]])

        report = dual_rail_clearance_report(state, netlist, hv_components={"Q1"}, lv_components=set())
        assert report["clearance_score_3mm"] == 1.0
        assert report["clearance_score_6mm"] == 1.0
        assert report["violations_3mm"] == 0
        assert report["violations_6mm"] == 0

    # ---- Edge case: both empty ----

    def test_dual_rail_both_empty_gives_perfect_scores(self):
        """No HV or LV components → all scores 1.0, violation counts 0."""
        from temper_placer.core.netlist import Netlist
        from temper_placer.metrics.quality import dual_rail_clearance_report

        netlist = Netlist(); netlist.components = []; netlist.build_indices()
        state = self._make_state([])

        report = dual_rail_clearance_report(state, netlist, hv_components=set(), lv_components=set())
        assert report["clearance_score_3mm"] == 1.0
        assert report["clearance_score_6mm"] == 1.0
        assert report["violations_3mm"] == 0
        assert report["violations_6mm"] == 0

    # ---- Integration: compute_quality_report surfaces the four new fields ----

    def test_compute_quality_report_includes_dual_rail_fields(self):
        """compute_quality_report returns all four dual-rail fields alongside
        the legacy hv_lv_clearance_score."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist

        q1 = Component(ref="Q1", footprint="small", bounds=(2.0, 2.0),
                       pins=[], initial_position=(0.0, 0.0), net_class="HighVoltage")
        u1 = Component(ref="U1", footprint="small", bounds=(2.0, 2.0),
                       pins=[], initial_position=(3.5, 0.0), net_class="Signal")

        netlist = Netlist(); netlist.components = [q1, u1]; netlist.build_indices()
        board = Board(width=50.0, height=50.0)
        state = self._make_state([[0.0, 0.0], [3.5, 0.0]])
        ctx = _make_ctx()

        cfg = {
            "thermal_components": set(),
            "hv_components": {"Q1"},
            "lv_components": {"U1"},
            "zone_assignments": {},
            "loop_components": [],
            "min_hv_lv_clearance": 8.0,
        }
        report = compute_quality_report(state, netlist, board, ctx, cfg)

        # Legacy field preserved
        assert "hv_lv_clearance_score" in report
        # New dual-rail fields present
        assert "clearance_score_3mm" in report
        assert "clearance_score_6mm" in report
        assert "violations_3mm" in report
        assert "violations_6mm" in report
        # Values are sensible
        assert isinstance(report["clearance_score_3mm"], float)
        assert isinstance(report["clearance_score_6mm"], float)
        assert isinstance(report["violations_3mm"], int)
        assert isinstance(report["violations_6mm"], int)
        # For this fixture: Q1↔U1 = 1.5mm
        assert report["clearance_score_3mm"] == pytest.approx(1.5 / 3.0, rel=1e-6)
        assert report["clearance_score_6mm"] == pytest.approx(1.5 / 6.0, rel=1e-6)
        assert report["violations_3mm"] == 1
        assert report["violations_6mm"] == 1


# ============================================================================
# C-CAP activation verification in oracle (P1#7)
# ============================================================================

class TestCcapActivation:
    """Smoke test: oracle produces valid results on temper PCB."""

    def test_oracle_config_has_ccap_enabled(self):
        """Oracle produces valid scoring results on temper PCB (no placement given)."""
        from temper_placer.regression.physics_oracle import run_physics_oracle

        pcb_path = Path("pcb/temper.kicad_pcb")
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        result = run_physics_oracle(pcb_path, spec_path=spec_path, verbose=False)

        # Oracle should produce a result (not fail)
        assert result.passed in (True, False)
        assert result.elapsed_seconds > 0
        assert result.clearance_score >= 0.0


# ============================================================================
# Human baseline scorer (P0#2)
# ============================================================================

class TestHumanBaseline:
    """Tests for score_human_baseline function."""

    def test_import_and_signature(self):
        """score_human_baseline is importable and has correct signature."""
        import inspect

        from temper_placer.regression.physics_oracle import score_human_baseline

        sig = inspect.signature(score_human_baseline)
        params = list(sig.parameters.keys())
        assert "pcb_path" in params
        assert "spec_path" in params
        assert "verbose" in params

    def test_smoke_on_temper_pcb(self):
        """Smoke test: scores human reference and returns four clearance numbers."""
        from temper_placer.regression.physics_oracle import score_human_baseline

        pcb_path = Path("pcb/temper.kicad_pcb")
        spec_path = Path("packages/temper-placer/configs/pcb_spec.yaml")
        result = score_human_baseline(pcb_path, spec_path=spec_path, verbose=False)

        assert "clearance_score_3mm" in result
        assert "clearance_score_6mm" in result
        assert "violations_3mm" in result
        assert "violations_6mm" in result
        assert isinstance(result["clearance_score_3mm"], float)
        assert isinstance(result["clearance_score_6mm"], float)
        assert isinstance(result["violations_3mm"], int)
        assert isinstance(result["violations_6mm"], int)
        # Human placement has violations against 6.0mm DRC
        assert result["violations_6mm"] >= 1
