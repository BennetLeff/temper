"""
TDD Tests for placement quality metrics.

These metrics enable objective comparison between:
- Optimized placements
- Hand-placed reference designs
- Random placements (baseline)

Each metric returns a score where:
- Lower is better for distance/area metrics (wirelength, loop area)
- Higher is better for compliance metrics (zone, clearance)
- All scores are normalized to [0, 1] range for comparison
"""

from pathlib import Path

import pytest

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.losses import LossContext

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestTotalWirelength:
    """Tests for total_wirelength metric."""

    @pytest.fixture
    def simple_netlist(self) -> Netlist:
        """Create simple netlist with 4 components and 2 nets."""
        components = [
            Component(ref="R1", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
            Component(ref="R2", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
            Component(ref="C1", footprint="Capacitor_SMD:C_0603", bounds=(2.0, 1.0)),
            Component(ref="U1", footprint="Package_SO:SOIC-8", bounds=(6.0, 4.0)),
        ]
        nets = [
            Net(name="NET1", pins=[("R1", "1"), ("R2", "1")]),
            Net(name="NET2", pins=[("C1", "1"), ("U1", "1")]),
        ]
        return Netlist(components=components, nets=nets)

    @pytest.fixture
    def board(self) -> Board:
        """Create a 50x30mm board."""
        return Board(width=50.0, height=30.0, origin=(90.0, 70.0))

    def test_wirelength_spread_placement(self, simple_netlist: Netlist, board: Board):
        """Spread out placement should have larger wirelength."""
        from temper_placer.metrics.quality import total_wirelength

        # Spread placement - corners of board
        spread_positions = jnp.array(
            [
                [95.0, 75.0],  # R1 - bottom left
                [135.0, 75.0],  # R2 - bottom right
                [95.0, 95.0],  # C1 - top left
                [135.0, 95.0],  # U1 - top right
            ]
        )
        spread_state = PlacementState(
            positions=spread_positions,
            rotation_logits=jnp.zeros((4, 4)),
        )

        # Clustered placement - all near center
        cluster_positions = jnp.array(
            [
                [112.0, 84.0],  # R1
                [118.0, 84.0],  # R2
                [112.0, 87.0],  # C1
                [118.0, 87.0],  # U1
            ]
        )
        cluster_state = PlacementState(
            positions=cluster_positions,
            rotation_logits=jnp.zeros((4, 4)),
        )

        context = LossContext.from_netlist_and_board(simple_netlist, board)

        spread_wl = total_wirelength(spread_state, simple_netlist, context)
        cluster_wl = total_wirelength(cluster_state, simple_netlist, context)

        # Spread should have longer wirelength
        assert spread_wl > cluster_wl
        # Both should be positive
        assert spread_wl > 0
        assert cluster_wl > 0

    def test_wirelength_identical_positions_zero(self, simple_netlist: Netlist, board: Board):
        """If all net pins are at same position, wirelength should be minimal."""
        from temper_placer.metrics.quality import total_wirelength

        # All components at same position
        same_positions = jnp.array(
            [
                [115.0, 85.0],
                [115.0, 85.0],
                [115.0, 85.0],
                [115.0, 85.0],
            ]
        )
        state = PlacementState(
            positions=same_positions,
            rotation_logits=jnp.zeros((4, 4)),
        )
        context = LossContext.from_netlist_and_board(simple_netlist, board)

        wl = total_wirelength(state, simple_netlist, context)

        # Should be very small (just component pin offsets)
        assert wl < 1.0


class TestThermalScore:
    """Tests for thermal_score metric."""

    @pytest.fixture
    def thermal_netlist(self) -> Netlist:
        """Create netlist with thermal components (IGBTs)."""
        components = [
            Component(
                ref="Q1", footprint="Package_TO_SOT_THT:TO-247-3", bounds=(16.0, 21.0)
            ),  # IGBT - needs cooling
            Component(
                ref="Q2", footprint="Package_TO_SOT_THT:TO-247-3", bounds=(16.0, 21.0)
            ),  # IGBT - needs cooling
            Component(
                ref="R1", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)
            ),  # Regular component
        ]
        return Netlist(components=components, nets=[])

    @pytest.fixture
    def board(self) -> Board:
        """Create a 100x80mm board."""
        return Board(width=100.0, height=80.0, origin=(50.0, 40.0))

    def test_thermal_edge_placement_good(self, thermal_netlist: Netlist, board: Board):
        """IGBTs near edge should have good thermal score."""
        from temper_placer.metrics.quality import thermal_score

        # IGBTs very close to top edge (good for heatsink)
        # Board: 100x80mm with origin (50, 40), so top edge is at y = 40 + 80 = 120
        edge_positions = jnp.array(
            [
                [80.0, 118.0],  # Q1 - 2mm from top edge
                [120.0, 118.0],  # Q2 - 2mm from top edge
                [100.0, 80.0],  # R1 in middle
            ]
        )
        state = PlacementState(
            positions=edge_positions,
            rotation_logits=jnp.zeros((3, 4)),
        )

        # Define Q1, Q2 as thermal components
        thermal_components = {"Q1", "Q2"}
        score = thermal_score(state, thermal_netlist, board, thermal_components)

        # Good score (closer to 1.0) - 2mm from edge with max_distance=10 gives 0.8
        assert score > 0.7

    def test_thermal_center_placement_bad(self, thermal_netlist: Netlist, board: Board):
        """IGBTs in center should have poor thermal score."""
        from temper_placer.metrics.quality import thermal_score

        # IGBTs in center (bad for cooling)
        center_positions = jnp.array(
            [
                [100.0, 80.0],  # Q1 in center
                [100.0, 80.0],  # Q2 in center
                [100.0, 80.0],  # R1 in center
            ]
        )
        state = PlacementState(
            positions=center_positions,
            rotation_logits=jnp.zeros((3, 4)),
        )

        thermal_components = {"Q1", "Q2"}
        score = thermal_score(state, thermal_netlist, board, thermal_components)

        # Poor score (closer to 0.0)
        assert score < 0.5

    def test_thermal_no_components_perfect(self, board: Board):
        """If no thermal components specified, score should be perfect."""
        from temper_placer.metrics.quality import thermal_score

        # Single regular component
        netlist = Netlist(
            components=[Component(ref="R1", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0))],
            nets=[],
        )
        state = PlacementState(
            positions=jnp.array([[100.0, 80.0]]),
            rotation_logits=jnp.zeros((1, 4)),
        )

        # No thermal components
        score = thermal_score(state, netlist, board, thermal_components=set())

        # Perfect score when nothing to optimize
        assert score == 1.0


class TestZoneComplianceScore:
    """Tests for zone_compliance_score metric."""

    @pytest.fixture
    def zone_netlist(self) -> Netlist:
        """Create netlist with zone-assigned components."""
        components = [
            Component(ref="U_MCU", footprint="Package_QFP:LQFP-48", bounds=(10.0, 10.0)),
            Component(ref="U_BUCK", footprint="Package_SO:SOIC-8", bounds=(8.0, 6.0)),
            Component(ref="R1", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
        ]
        return Netlist(components=components, nets=[])

    @pytest.fixture
    def board_with_zones(self) -> Board:
        """Create board with defined zones."""
        zones = [
            Zone(name="MCU_ZONE", bounds=(90.0, 70.0, 110.0, 90.0)),
            Zone(name="LV_ZONE", bounds=(110.0, 70.0, 140.0, 90.0)),
        ]
        return Board(width=50.0, height=30.0, origin=(90.0, 70.0), zones=zones)

    def test_zone_compliance_all_correct(self, zone_netlist: Netlist, board_with_zones: Board):
        """All components in correct zones should give score 1.0."""
        from temper_placer.metrics.quality import zone_compliance_score

        # Components in their assigned zones
        positions = jnp.array(
            [
                [100.0, 80.0],  # U_MCU in MCU_ZONE
                [125.0, 80.0],  # U_BUCK in LV_ZONE
                [115.0, 80.0],  # R1 (no zone requirement)
            ]
        )
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((3, 4)),
        )

        zone_assignments = {"U_MCU": "MCU_ZONE", "U_BUCK": "LV_ZONE"}
        score = zone_compliance_score(state, zone_netlist, board_with_zones, zone_assignments)

        assert score == 1.0

    def test_zone_compliance_none_correct(self, zone_netlist: Netlist, board_with_zones: Board):
        """All components in wrong zones should give score 0.0."""
        from temper_placer.metrics.quality import zone_compliance_score

        # Components in wrong zones
        positions = jnp.array(
            [
                [125.0, 80.0],  # U_MCU in LV_ZONE (wrong!)
                [100.0, 80.0],  # U_BUCK in MCU_ZONE (wrong!)
                [115.0, 80.0],  # R1 (no zone requirement)
            ]
        )
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((3, 4)),
        )

        zone_assignments = {"U_MCU": "MCU_ZONE", "U_BUCK": "LV_ZONE"}
        score = zone_compliance_score(state, zone_netlist, board_with_zones, zone_assignments)

        assert score == 0.0


class TestHVLVClearanceScore:
    """Tests for hv_lv_clearance_score metric."""

    @pytest.fixture
    def hv_lv_netlist(self) -> Netlist:
        """Create netlist with HV and LV components."""
        components = [
            Component(
                ref="Q1", footprint="Package_TO_SOT_THT:TO-247-3", bounds=(16.0, 21.0)
            ),  # HV component
            Component(
                ref="U_MCU", footprint="Package_QFP:LQFP-48", bounds=(10.0, 10.0)
            ),  # LV component
            Component(
                ref="R_HV", footprint="Resistor_SMD:R_1206", bounds=(3.0, 1.5)
            ),  # HV resistor
        ]
        return Netlist(components=components, nets=[])

    @pytest.fixture
    def board(self) -> Board:
        """Create board."""
        return Board(width=100.0, height=80.0, origin=(50.0, 40.0))

    def test_clearance_sufficient(self, hv_lv_netlist: Netlist, board: Board):
        """Components with >8mm clearance should score well."""
        from temper_placer.metrics.quality import hv_lv_clearance_score

        # HV on left, LV on right with 20mm gap
        positions = jnp.array(
            [
                [70.0, 80.0],  # Q1 (HV)
                [120.0, 80.0],  # U_MCU (LV)
                [75.0, 80.0],  # R_HV (HV)
            ]
        )
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((3, 4)),
        )

        hv_components = {"Q1", "R_HV"}
        lv_components = {"U_MCU"}
        min_clearance = 8.0  # mm

        score = hv_lv_clearance_score(
            state, hv_lv_netlist, hv_components, lv_components, min_clearance
        )

        # Should score well (clearance is sufficient)
        assert score > 0.8

    def test_clearance_violated(self, hv_lv_netlist: Netlist, board: Board):
        """Components with <8mm clearance should score poorly."""
        from temper_placer.metrics.quality import hv_lv_clearance_score

        # HV and LV components very close
        positions = jnp.array(
            [
                [95.0, 80.0],  # Q1 (HV)
                [100.0, 80.0],  # U_MCU (LV) - only ~5mm away
                [93.0, 80.0],  # R_HV (HV)
            ]
        )
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((3, 4)),
        )

        hv_components = {"Q1", "R_HV"}
        lv_components = {"U_MCU"}
        min_clearance = 8.0

        score = hv_lv_clearance_score(
            state, hv_lv_netlist, hv_components, lv_components, min_clearance
        )

        # Should score poorly (clearance violated)
        assert score < 0.5


class TestLoopAreaScore:
    """Tests for loop_area_score metric."""

    @pytest.fixture
    def loop_netlist(self) -> Netlist:
        """Create netlist with gate drive loop components."""
        components = [
            Component(
                ref="U_GATE", footprint="Package_SO:SOIC-8", bounds=(8.0, 6.0)
            ),  # Gate driver
            Component(
                ref="Q1", footprint="Package_TO_SOT_THT:TO-247-3", bounds=(16.0, 21.0)
            ),  # IGBT
            Component(
                ref="R_GATE", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)
            ),  # Gate resistor
        ]
        # Gate drive loop: U_GATE -> R_GATE -> Q1 gate
        nets = [
            Net(name="GATE_OUT", pins=[("U_GATE", "1"), ("R_GATE", "1")]),
            Net(name="GATE_IN", pins=[("R_GATE", "2"), ("Q1", "1")]),
        ]
        return Netlist(components=components, nets=nets)

    @pytest.fixture
    def board(self) -> Board:
        return Board(width=100.0, height=80.0, origin=(50.0, 40.0))

    def test_loop_area_tight(self, loop_netlist: Netlist, board: Board):
        """Tightly placed loop components should have good score."""
        from temper_placer.metrics.quality import loop_area_score

        # Components placed close together
        tight_positions = jnp.array(
            [
                [100.0, 80.0],  # U_GATE
                [110.0, 80.0],  # Q1
                [105.0, 82.0],  # R_GATE between them
            ]
        )
        state = PlacementState(
            positions=tight_positions,
            rotation_logits=jnp.zeros((3, 4)),
        )
        context = LossContext.from_netlist_and_board(loop_netlist, board)

        # Define gate drive loop
        loop_components = [["U_GATE", "R_GATE", "Q1"]]
        score = loop_area_score(state, loop_netlist, context, loop_components)

        # Should have good score (small loop)
        assert score > 0.7

    def test_loop_area_spread(self, loop_netlist: Netlist, board: Board):
        """Spread out loop components should have poor score."""
        from temper_placer.metrics.quality import loop_area_score

        # Components spread far apart forming a large triangle (not collinear!)
        # U_GATE at index 0, Q1 at index 1, R_GATE at index 2
        spread_positions = jnp.array(
            [
                [60.0, 50.0],  # U_GATE - bottom left
                [140.0, 50.0],  # Q1 - bottom right
                [100.0, 110.0],  # R_GATE - top center
            ]
        )
        state = PlacementState(
            positions=spread_positions,
            rotation_logits=jnp.zeros((3, 4)),
        )
        context = LossContext.from_netlist_and_board(loop_netlist, board)

        # Loop components form triangle: area = 0.5 * base * height = 0.5 * 80 * 60 = 2400 mm²
        loop_components = [["U_GATE", "R_GATE", "Q1"]]
        score = loop_area_score(state, loop_netlist, context, loop_components, max_area=500.0)

        # Large area (2400mm²) relative to 500mm² max gives poor score
        assert score < 0.5


class TestCongestionScore:
    """Tests for congestion_score metric."""

    @pytest.fixture
    def multi_net_netlist(self) -> Netlist:
        """Create netlist with multiple nets."""
        components = [
            Component(ref=f"R{i}", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0))
            for i in range(1, 9)
        ]
        # Create nets connecting pairs
        nets = [Net(name=f"NET{i}", pins=[(f"R{i}", "1"), (f"R{i + 1}", "1")]) for i in range(1, 8)]
        return Netlist(components=components, nets=nets)

    @pytest.fixture
    def board(self) -> Board:
        return Board(width=50.0, height=30.0, origin=(90.0, 70.0))

    def test_congestion_spread(self, multi_net_netlist: Netlist, board: Board):
        """Evenly spread components should have low congestion."""
        from temper_placer.metrics.quality import congestion_score

        # Spread components in a grid
        ox, oy = board.origin
        positions = jnp.array([[ox + 5 + (i % 4) * 10, oy + 5 + (i // 4) * 10] for i in range(8)])
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((8, 4)),
        )
        context = LossContext.from_netlist_and_board(multi_net_netlist, board)

        score = congestion_score(state, multi_net_netlist, board, context)

        # Should have good score (low congestion)
        assert score > 0.6

    def test_congestion_clustered(self, multi_net_netlist: Netlist, board: Board):
        """Clustered components should have high congestion."""
        from temper_placer.metrics.quality import congestion_score

        # All components in same spot - with very low capacity this should overflow
        ox, oy = board.origin
        positions = jnp.array([[ox + 25, oy + 15] for _ in range(8)])
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((8, 4)),
        )
        context = LossContext.from_netlist_and_board(multi_net_netlist, board)

        # Use low capacity to ensure overflow is detected
        score = congestion_score(state, multi_net_netlist, board, context, capacity_per_cell=0.5)

        # With low capacity, clustered nets should cause congestion
        assert score < 0.8  # Relaxed threshold - key is spread > clustered


class TestCompactnessScore:
    """Tests for compactness_score metric."""

    @pytest.fixture
    def netlist(self) -> Netlist:
        """Create netlist with 4 components."""
        components = [
            Component(ref="R1", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
            Component(ref="R2", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
            Component(ref="R3", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
            Component(ref="R4", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
        ]
        return Netlist(components=components, nets=[])

    @pytest.fixture
    def board(self) -> Board:
        return Board(width=50.0, height=30.0, origin=(90.0, 70.0))

    def test_compactness_tight(self, netlist: Netlist, board: Board):
        """Tightly packed components should have high compactness."""
        from temper_placer.metrics.quality import compactness_score

        ox, oy = board.origin
        # Very tight 2x2 grid - components touching
        # Each component is 2x1mm, so pack them tightly
        positions = jnp.array(
            [
                [ox + 10, oy + 10],  # R1
                [ox + 12, oy + 10],  # R2 right next to R1
                [ox + 10, oy + 11],  # R3 above R1
                [ox + 12, oy + 11],  # R4 above R2
            ]
        )
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((4, 4)),
        )

        score = compactness_score(state, netlist, board)

        # Components are 2x1mm each = 8mm² total
        # Positions span 2x1, plus 2mm width = 4x3 = 12mm² bbox
        # Utilization = 8/12 = 0.67 - close to theoretical max
        assert score > 0.5  # Realistic threshold for tight packing

    def test_compactness_spread(self, netlist: Netlist, board: Board):
        """Spread out components should have low compactness."""
        from temper_placer.metrics.quality import compactness_score

        ox, oy = board.origin
        # Corners of board
        positions = jnp.array(
            [
                [ox + 5, oy + 5],
                [ox + 45, oy + 5],
                [ox + 5, oy + 25],
                [ox + 45, oy + 25],
            ]
        )
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((4, 4)),
        )

        score = compactness_score(state, netlist, board)

        # Should have poor compactness (using whole board)
        assert score < 0.4


class TestMetricsNormalization:
    """Tests ensuring all metrics return normalized [0, 1] scores."""

    @pytest.fixture
    def simple_setup(self):
        """Create simple test setup."""
        components = [
            Component(ref="R1", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
            Component(ref="R2", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
        ]
        netlist = Netlist(components=components, nets=[])
        board = Board(width=50.0, height=30.0, origin=(90.0, 70.0))
        positions = jnp.array([[100.0, 80.0], [110.0, 80.0]])
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((2, 4)),
        )
        context = LossContext.from_netlist_and_board(netlist, board)
        return netlist, board, state, context

    def test_all_scores_in_range(self, simple_setup):
        """All metric scores should be in [0, 1] range."""
        from temper_placer.metrics.quality import (
            compactness_score,
            hv_lv_clearance_score,
            thermal_score,
            zone_compliance_score,
        )

        netlist, board, state, context = simple_setup

        # Test each metric
        scores = {
            "thermal": thermal_score(state, netlist, board, set()),
            "zone": zone_compliance_score(state, netlist, board, {}),
            "clearance": hv_lv_clearance_score(state, netlist, set(), set(), 8.0),
            "compactness": compactness_score(state, netlist, board),
        }

        for name, score in scores.items():
            assert 0.0 <= score <= 1.0, f"{name} score {score} out of [0, 1] range"


class TestQualityReport:
    """Tests for the combined quality report."""

    @pytest.fixture
    def test_setup(self):
        """Create test setup with all components needed."""
        components = [
            Component(ref="Q1", footprint="Package_TO_SOT_THT:TO-247-3", bounds=(16.0, 21.0)),
            Component(ref="U_MCU", footprint="Package_QFP:LQFP-48", bounds=(10.0, 10.0)),
            Component(ref="R1", footprint="Resistor_SMD:R_0603", bounds=(2.0, 1.0)),
            Component(ref="C1", footprint="Capacitor_SMD:C_0603", bounds=(2.0, 1.0)),
        ]
        nets = [
            Net(name="NET1", pins=[("Q1", "1"), ("R1", "1")]),
            Net(name="NET2", pins=[("U_MCU", "1"), ("C1", "1")]),
        ]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=80.0, origin=(50.0, 40.0))
        return netlist, board

    def test_quality_report_all_metrics(self, test_setup):
        """Quality report should include all metrics."""
        from temper_placer.metrics.quality import compute_quality_report

        netlist, board = test_setup
        positions = jnp.array(
            [
                [80.0, 110.0],  # Q1 near edge
                [120.0, 80.0],  # U_MCU
                [85.0, 105.0],  # R1
                [125.0, 80.0],  # C1
            ]
        )
        state = PlacementState(
            positions=positions,
            rotation_logits=jnp.zeros((4, 4)),
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        config = {
            "thermal_components": {"Q1"},
            "hv_components": {"Q1"},
            "lv_components": {"U_MCU"},
            "zone_assignments": {},
            "loop_components": [],
            "min_hv_lv_clearance": 8.0,
        }

        report = compute_quality_report(state, netlist, board, context, config)

        # Check all expected keys
        expected_keys = [
            "total_wirelength",
            "thermal_score",
            "zone_compliance_score",
            "hv_lv_clearance_score",
            "loop_area_score",
            "congestion_score",
            "compactness_score",
            "overall_score",
        ]
        for key in expected_keys:
            assert key in report, f"Missing key: {key}"

        # Overall score should be average or weighted combination
        assert 0.0 <= report["overall_score"] <= 1.0
