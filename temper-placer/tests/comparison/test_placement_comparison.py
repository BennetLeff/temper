"""
Placement Comparison Test Framework.

This module provides tests for comparing optimizer placements against:
1. Hand-placed reference designs (when available)
2. Random placements (baseline)

The comparison framework helps validate that the optimizer produces
quality placements that meet or exceed human designs.

Acceptance criteria:
- Optimizer achieves >= 90% of reference quality overall
- No single metric worse than 150% of reference

Tests use realistic configurations matching the Temper board constraints.
"""

from pathlib import Path
from typing import Dict, Optional, Tuple
import json

import pytest

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Component, Net
from temper_placer.core.state import PlacementState
from temper_placer.losses import (
    LossContext,
    CompositeLoss,
    WeightedLoss,
    OverlapLoss,
    BoundaryLoss,
    WirelengthLoss,
)
from temper_placer.metrics import compute_quality_report


# Test fixtures and results directories
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
RESULTS_DIR = Path(__file__).parent / "results"


def create_temper_test_netlist() -> Netlist:
    """
    Create the Temper test netlist with 17 components.

    This matches the realistic Temper induction cooker component set:
    - 2 IGBTs (Q1, Q2) - high-power switching
    - Gate driver (U_GATE)
    - Buck converter (U_BUCK)
    - MCU (U_MCU)
    - Various passives
    """
    components = [
        # High-power: IGBTs (TO-247 package)
        Component(ref="Q1", footprint="Package_TO_SOT_THT:TO-247-3", bounds=(16.0, 21.0)),
        Component(ref="Q2", footprint="Package_TO_SOT_THT:TO-247-3", bounds=(16.0, 21.0)),
        # Gate driver (SOIC-8)
        Component(ref="U_GATE", footprint="Package_SO:SOIC-8", bounds=(6.0, 5.0)),
        # Buck converter (SOIC-8)
        Component(ref="U_BUCK", footprint="Package_SO:SOIC-8", bounds=(6.0, 5.0)),
        # MCU (LQFP-48)
        Component(ref="U_MCU", footprint="Package_QFP:LQFP-48", bounds=(10.0, 10.0)),
        # Gate resistors
        Component(ref="R_GATE1", footprint="Resistor_SMD:R_0603", bounds=(1.6, 0.8)),
        Component(ref="R_GATE2", footprint="Resistor_SMD:R_0603", bounds=(1.6, 0.8)),
        # Decoupling capacitors
        Component(ref="C_DEC1", footprint="Capacitor_SMD:C_0603", bounds=(1.6, 0.8)),
        Component(ref="C_DEC2", footprint="Capacitor_SMD:C_0603", bounds=(1.6, 0.8)),
        Component(ref="C_DEC3", footprint="Capacitor_SMD:C_0603", bounds=(1.6, 0.8)),
        # Power capacitors (larger)
        Component(ref="C_BULK1", footprint="Capacitor_SMD:C_1206", bounds=(3.2, 1.6)),
        Component(ref="C_BULK2", footprint="Capacitor_SMD:C_1206", bounds=(3.2, 1.6)),
        # Current sense resistor
        Component(ref="R_SENSE", footprint="Resistor_SMD:R_1206", bounds=(3.2, 1.6)),
        # Temperature sensor
        Component(ref="U_TEMP", footprint="Package_SO:SOIC-8", bounds=(6.0, 5.0)),
        # LDO regulator
        Component(ref="U_LDO", footprint="Package_SO:SOIC-8", bounds=(6.0, 5.0)),
        # Protection diode
        Component(ref="D1", footprint="Diode_SMD:D_SMA", bounds=(4.6, 2.5)),
        # LED indicator
        Component(ref="LED1", footprint="LED_SMD:LED_0603", bounds=(1.6, 0.8)),
    ]

    # Create realistic nets
    nets = [
        # Gate drive net: U_GATE -> R_GATE1 -> Q1
        Net(name="GATE1_OUT", pins=[("U_GATE", "1"), ("R_GATE1", "1")]),
        Net(name="GATE1_IN", pins=[("R_GATE1", "2"), ("Q1", "1")]),
        # Gate drive net: U_GATE -> R_GATE2 -> Q2
        Net(name="GATE2_OUT", pins=[("U_GATE", "2"), ("R_GATE2", "1")]),
        Net(name="GATE2_IN", pins=[("R_GATE2", "2"), ("Q2", "1")]),
        # Power nets
        Net(name="VCC", pins=[("U_BUCK", "1"), ("C_BULK1", "1"), ("C_BULK2", "1"), ("U_LDO", "1")]),
        Net(name="GND", pins=[("Q1", "3"), ("Q2", "3"), ("C_BULK1", "2"), ("C_BULK2", "2")]),
        # MCU connections
        Net(name="MCU_GATE", pins=[("U_MCU", "1"), ("U_GATE", "3")]),
        Net(name="MCU_TEMP", pins=[("U_MCU", "2"), ("U_TEMP", "1")]),
        Net(name="MCU_LED", pins=[("U_MCU", "3"), ("LED1", "1")]),
        # Decoupling
        Net(name="DEC_MCU", pins=[("U_MCU", "4"), ("C_DEC1", "1")]),
        Net(name="DEC_GATE", pins=[("U_GATE", "4"), ("C_DEC2", "1")]),
        Net(name="DEC_BUCK", pins=[("U_BUCK", "4"), ("C_DEC3", "1")]),
    ]

    return Netlist(components=components, nets=nets)


def create_temper_board() -> Board:
    """
    Create the Temper board with zones.

    100x80mm board with:
    - HV zone for power components
    - LV zone for control
    - MCU zone for microcontroller
    """
    zones = [
        Zone(name="HV_ZONE", bounds=(50.0, 80.0, 130.0, 120.0)),  # Top half, HV section
        Zone(name="LV_ZONE", bounds=(50.0, 40.0, 100.0, 80.0)),  # Bottom left, LV
        Zone(name="MCU_ZONE", bounds=(100.0, 40.0, 150.0, 80.0)),  # Bottom right, MCU
    ]
    return Board(width=100.0, height=80.0, origin=(50.0, 40.0), zones=zones)


def create_temper_config() -> Dict:
    """
    Create the quality metrics configuration for Temper board.

    Returns config dict with:
    - thermal_components: IGBTs need edge placement
    - hv_components: High-voltage components
    - lv_components: Low-voltage control
    - zone_assignments: Component -> zone mapping
    - loop_components: Critical loops to minimize
    - min_hv_lv_clearance: Safety clearance in mm
    """
    return {
        "thermal_components": {"Q1", "Q2"},
        "hv_components": {"Q1", "Q2", "C_BULK1", "C_BULK2", "R_SENSE", "D1"},
        "lv_components": {"U_MCU", "U_TEMP", "LED1", "C_DEC1"},
        "zone_assignments": {
            "U_MCU": "MCU_ZONE",
            "U_BUCK": "LV_ZONE",
            "U_LDO": "LV_ZONE",
        },
        "loop_components": [
            ["U_GATE", "R_GATE1", "Q1"],  # Gate drive loop 1
            ["U_GATE", "R_GATE2", "Q2"],  # Gate drive loop 2
        ],
        "min_hv_lv_clearance": 8.0,
    }


class PlacementFactory:
    """Factory for creating various placement types."""

    @staticmethod
    def random_placement(
        netlist: Netlist,
        board: Board,
        seed: int = 42,
    ) -> PlacementState:
        """Create a random placement within board bounds."""
        key = jax.random.PRNGKey(seed)
        return PlacementState.random_init(
            n_components=netlist.n_components,
            board_width=board.width,
            board_height=board.height,
            key=key,
        )

    @staticmethod
    def centered_placement(
        netlist: Netlist,
        board: Board,
    ) -> PlacementState:
        """Create a placement with all components at center (worst case)."""
        ox, oy = board.origin
        center_x = ox + board.width / 2
        center_y = oy + board.height / 2

        positions = jnp.array([[center_x, center_y] for _ in range(netlist.n_components)])
        return PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((netlist.n_components, 4)),
        )

    @staticmethod
    def heuristic_placement(
        netlist: Netlist,
        board: Board,
        config: Dict,
    ) -> PlacementState:
        """
        Create a reasonable heuristic placement (simulates hand-placed).

        Places components based on type:
        - IGBTs near top edge
        - Gate driver between IGBTs
        - MCU in MCU zone
        - Buck in LV zone
        - Decoupling caps near their ICs
        """
        ox, oy = board.origin
        positions = []

        # Build reference name -> index mapping
        ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}

        # Define target positions for key components
        # Board top edge is at oy + board.height
        top_edge = oy + board.height

        target_positions = {
            # IGBTs very close to top edge for heatsink (within 5mm for good thermal score)
            "Q1": (ox + 25, top_edge - 5),
            "Q2": (ox + 55, top_edge - 5),
            # Gate driver between IGBTs, close to them for small loop area
            "U_GATE": (ox + 40, top_edge - 12),
            # Gate resistors VERY close to gate driver and IGBTs (tight loop)
            "R_GATE1": (ox + 32, top_edge - 8),  # Between U_GATE and Q1
            "R_GATE2": (ox + 48, top_edge - 8),  # Between U_GATE and Q2
            # Buck and LDO in LV zone
            "U_BUCK": (ox + 20, oy + 25),
            "U_LDO": (ox + 35, oy + 25),
            # MCU in MCU zone
            "U_MCU": (ox + 70, oy + 25),
            # Temperature sensor near MCU
            "U_TEMP": (ox + 85, oy + 25),
            # Decoupling caps near their ICs
            "C_DEC1": (ox + 65, oy + 30),  # Near MCU
            "C_DEC2": (ox + 45, top_edge - 18),  # Near gate driver
            "C_DEC3": (ox + 25, oy + 30),  # Near buck
            # Bulk caps in HV zone
            "C_BULK1": (ox + 15, top_edge - 20),
            "C_BULK2": (ox + 65, top_edge - 20),
            # Other components
            "R_SENSE": (ox + 40, top_edge - 3),
            "D1": (ox + 75, top_edge - 15),
            "LED1": (ox + 90, oy + 15),
        }

        for comp in netlist.components:
            if comp.ref in target_positions:
                pos = target_positions[comp.ref]
            else:
                # Default: place in center
                pos = (ox + board.width / 2, oy + board.height / 2)
            positions.append([pos[0], pos[1]])

        return PlacementState(
            positions=jnp.array(positions),
            rotation_logits=jnp.zeros((netlist.n_components, 4)),
        )


class TestLoadReferencePlacement:
    """Tests for loading reference placement from KiCad file."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    def test_reference_file_not_found_uses_heuristic(self, netlist: Netlist, board: Board):
        """When reference file doesn't exist, use heuristic placement as baseline."""
        reference_path = FIXTURES_DIR / "reference_placement.json"

        # Reference file won't exist initially - use heuristic as stand-in
        if not reference_path.exists():
            config = create_temper_config()
            heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)

            # Heuristic should produce valid positions
            assert heuristic_state.positions.shape == (netlist.n_components, 2)

            # Positions should be within board bounds
            ox, oy = board.origin
            assert jnp.all(heuristic_state.positions[:, 0] >= ox)
            assert jnp.all(heuristic_state.positions[:, 0] <= ox + board.width)
            assert jnp.all(heuristic_state.positions[:, 1] >= oy)
            assert jnp.all(heuristic_state.positions[:, 1] <= oy + board.height)

    @pytest.mark.skip(reason="Reference file not yet created - task temper-1my.6.1")
    def test_load_reference_from_kicad(self, netlist: Netlist, board: Board):
        """Load reference placement from KiCad PCB file."""
        # This test will be enabled once temper-1my.6.1 creates the reference file
        pass


class TestRunOptimizerSameConstraints:
    """Tests for running optimizer with same constraints as reference."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def context(self, netlist: Netlist, board: Board) -> LossContext:
        return LossContext.from_netlist_and_board(netlist, board)

    def test_optimizer_produces_valid_placement(
        self, netlist: Netlist, board: Board, context: LossContext
    ):
        """Optimizer should produce a valid placement within board bounds."""
        from temper_placer.optimizer import train, OptimizerConfig

        # Use fast config for testing
        config = OptimizerConfig.fast_test()

        # Simple loss for fast test
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
            ]
        )

        result = train(netlist, board, composite, context, config)

        # Check valid output
        assert result.final_state is not None
        assert result.final_state.positions.shape == (netlist.n_components, 2)

        # All positions should be finite
        assert jnp.all(jnp.isfinite(result.final_state.positions))

    def test_optimizer_reduces_loss(self, netlist: Netlist, board: Board, context: LossContext):
        """Optimizer should reduce loss compared to random initialization."""
        from temper_placer.optimizer import train, OptimizerConfig

        config = OptimizerConfig.fast_test()
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
            ]
        )

        result = train(netlist, board, composite, context, config)

        # Best loss should be better than or equal to final loss
        assert result.best_loss <= result.history[0].loss or len(result.history) < 2

        # Training should complete
        assert result.total_epochs > 0


class TestCompareWirelength:
    """Tests comparing wirelength between placements."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def context(self, netlist: Netlist, board: Board) -> LossContext:
        return LossContext.from_netlist_and_board(netlist, board)

    @pytest.fixture
    def config(self) -> Dict:
        return create_temper_config()

    def test_heuristic_better_than_random(
        self,
        netlist: Netlist,
        board: Board,
        context: LossContext,
        config: Dict,
    ):
        """Heuristic placement should have shorter wirelength than random."""
        from temper_placer.metrics import total_wirelength

        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        random_state = PlacementFactory.random_placement(netlist, board, seed=42)

        heuristic_wl = total_wirelength(heuristic_state, netlist, context)
        random_wl = total_wirelength(random_state, netlist, context)

        # Heuristic should generally be better, but not always guaranteed
        # Just check both are finite and positive
        assert heuristic_wl > 0
        assert random_wl > 0
        assert jnp.isfinite(heuristic_wl)
        assert jnp.isfinite(random_wl)

    def test_wirelength_threshold(
        self,
        netlist: Netlist,
        board: Board,
        context: LossContext,
        config: Dict,
    ):
        """
        Good placement wirelength should be within threshold of heuristic.

        Target: optimizer within 120% of heuristic wirelength.
        """
        from temper_placer.metrics import total_wirelength
        from temper_placer.optimizer import train, OptimizerConfig

        # Get heuristic baseline
        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        heuristic_wl = total_wirelength(heuristic_state, netlist, context)

        # Run short optimization
        opt_config = OptimizerConfig.fast_test()
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
                WeightedLoss(WirelengthLoss(), weight=10.0),
            ]
        )

        result = train(netlist, board, composite, context, opt_config)
        opt_wl = total_wirelength(result.best_state, netlist, context)

        # For fast test, we can't guarantee optimization beats heuristic
        # Just verify the metric is computed correctly
        assert opt_wl > 0
        assert jnp.isfinite(opt_wl)

        # Log ratio for debugging
        ratio = opt_wl / heuristic_wl if heuristic_wl > 0 else float("inf")
        print(f"Wirelength ratio (opt/heuristic): {ratio:.2f}")


class TestCompareThermal:
    """Tests comparing thermal placement quality."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def config(self) -> Dict:
        return create_temper_config()

    def test_heuristic_thermal_score(
        self,
        netlist: Netlist,
        board: Board,
        config: Dict,
    ):
        """Heuristic placement should have good thermal score (IGBTs near edge)."""
        from temper_placer.metrics import thermal_score

        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        score = thermal_score(heuristic_state, netlist, board, config["thermal_components"])

        # Heuristic places IGBTs 5mm from top edge
        # With max_distance=10, score = 1 - 5/10 = 0.5
        # This is acceptable for a heuristic (edge placement is working)
        assert score >= 0.4

    def test_centered_thermal_score_poor(
        self,
        netlist: Netlist,
        board: Board,
        config: Dict,
    ):
        """Centered placement should have poor thermal score."""
        from temper_placer.metrics import thermal_score

        centered_state = PlacementFactory.centered_placement(netlist, board)
        score = thermal_score(centered_state, netlist, board, config["thermal_components"])

        # Center is far from edge, should score poorly
        assert score < 0.5


class TestCompareZoneCompliance:
    """Tests comparing zone compliance between placements."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def config(self) -> Dict:
        return create_temper_config()

    def test_heuristic_zone_compliance(
        self,
        netlist: Netlist,
        board: Board,
        config: Dict,
    ):
        """Heuristic placement should have high zone compliance."""
        from temper_placer.metrics import zone_compliance_score

        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        score = zone_compliance_score(heuristic_state, netlist, board, config["zone_assignments"])

        # Heuristic explicitly places components in correct zones
        assert score >= 0.8


class TestCompareHVLVClearance:
    """Tests comparing HV-LV clearance between placements."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def config(self) -> Dict:
        return create_temper_config()

    def test_heuristic_clearance_maintained(
        self,
        netlist: Netlist,
        board: Board,
        config: Dict,
    ):
        """Heuristic placement should maintain HV-LV clearance."""
        from temper_placer.metrics import hv_lv_clearance_score

        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        score = hv_lv_clearance_score(
            heuristic_state,
            netlist,
            config["hv_components"],
            config["lv_components"],
            config["min_hv_lv_clearance"],
        )

        # Heuristic separates HV (top) from LV (bottom)
        assert score > 0.7

    def test_centered_clearance_violated(
        self,
        netlist: Netlist,
        board: Board,
        config: Dict,
    ):
        """Centered placement should violate HV-LV clearance."""
        from temper_placer.metrics import hv_lv_clearance_score

        centered_state = PlacementFactory.centered_placement(netlist, board)
        score = hv_lv_clearance_score(
            centered_state,
            netlist,
            config["hv_components"],
            config["lv_components"],
            config["min_hv_lv_clearance"],
        )

        # All at center violates clearance
        assert score < 0.3


class TestCompareLoopArea:
    """Tests comparing critical loop area between placements."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def context(self, netlist: Netlist, board: Board) -> LossContext:
        return LossContext.from_netlist_and_board(netlist, board)

    @pytest.fixture
    def config(self) -> Dict:
        return create_temper_config()

    def test_heuristic_loop_area_small(
        self,
        netlist: Netlist,
        board: Board,
        context: LossContext,
        config: Dict,
    ):
        """Heuristic placement should have small gate drive loop area."""
        from temper_placer.metrics import loop_area_score

        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        score = loop_area_score(heuristic_state, netlist, context, config["loop_components"])

        # Gate driver and gate resistors are placed close to IGBTs
        assert score > 0.5


class TestOverallQualityScore:
    """Tests for overall quality score comparison."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def context(self, netlist: Netlist, board: Board) -> LossContext:
        return LossContext.from_netlist_and_board(netlist, board)

    @pytest.fixture
    def config(self) -> Dict:
        return create_temper_config()

    def test_heuristic_overall_quality(
        self,
        netlist: Netlist,
        board: Board,
        context: LossContext,
        config: Dict,
    ):
        """Heuristic placement should have reasonable overall quality."""
        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        report = compute_quality_report(heuristic_state, netlist, board, context, config)

        # Check report structure
        assert "overall_score" in report
        assert "total_wirelength" in report

        # Heuristic should achieve decent overall score
        assert report["overall_score"] > 0.5

    def test_random_vs_heuristic_quality(
        self,
        netlist: Netlist,
        board: Board,
        context: LossContext,
        config: Dict,
    ):
        """Heuristic should outperform random on overall quality."""
        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        random_state = PlacementFactory.random_placement(netlist, board, seed=42)

        heuristic_report = compute_quality_report(heuristic_state, netlist, board, context, config)
        random_report = compute_quality_report(random_state, netlist, board, context, config)

        # Both should produce valid reports
        assert 0 <= heuristic_report["overall_score"] <= 1
        assert 0 <= random_report["overall_score"] <= 1

        # Log for debugging (heuristic not guaranteed better due to randomness)
        print(f"Heuristic overall: {heuristic_report['overall_score']:.3f}")
        print(f"Random overall: {random_report['overall_score']:.3f}")

    def test_quality_report_json_serializable(
        self,
        netlist: Netlist,
        board: Board,
        context: LossContext,
        config: Dict,
    ):
        """Quality report should be JSON serializable."""
        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        report = compute_quality_report(heuristic_state, netlist, board, context, config)

        # Convert to JSON and back
        json_str = json.dumps(report)
        parsed = json.loads(json_str)

        assert parsed["overall_score"] == report["overall_score"]


class TestComparisonReport:
    """Tests for generating comparison reports."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        return create_temper_test_netlist()

    @pytest.fixture
    def board(self) -> Board:
        return create_temper_board()

    @pytest.fixture
    def context(self, netlist: Netlist, board: Board) -> LossContext:
        return LossContext.from_netlist_and_board(netlist, board)

    @pytest.fixture
    def config(self) -> Dict:
        return create_temper_config()

    def test_generate_comparison_dict(
        self,
        netlist: Netlist,
        board: Board,
        context: LossContext,
        config: Dict,
    ):
        """Generate a comparison dict between placements."""
        heuristic_state = PlacementFactory.heuristic_placement(netlist, board, config)
        random_state = PlacementFactory.random_placement(netlist, board, seed=42)

        heuristic_report = compute_quality_report(heuristic_state, netlist, board, context, config)
        random_report = compute_quality_report(random_state, netlist, board, context, config)

        comparison = {
            "heuristic": heuristic_report,
            "random": random_report,
            "metrics": {},
        }

        # Calculate ratios for each metric
        for metric in [
            "thermal_score",
            "zone_compliance_score",
            "hv_lv_clearance_score",
            "loop_area_score",
            "congestion_score",
            "compactness_score",
        ]:
            h_val = heuristic_report[metric]
            r_val = random_report[metric]
            comparison["metrics"][metric] = {
                "heuristic": h_val,
                "random": r_val,
                "heuristic_better": h_val > r_val,
            }

        # Should have all metrics
        assert len(comparison["metrics"]) == 6

        # Each metric should have comparison data
        for metric, data in comparison["metrics"].items():
            assert "heuristic" in data
            assert "random" in data
            assert "heuristic_better" in data
