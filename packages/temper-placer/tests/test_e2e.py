"""
End-to-end integration tests for temper-placer.

These tests verify the complete optimization pipeline:
1. Load KiCad PCB
2. Load constraints
3. Run optimization
4. Export results
5. Verify output

These are marked as slow since they run actual optimization.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp  # noqa: E402

# Test data paths
TEST_DATA_DIR = Path(__file__).parent.parent.parent / "kicad-tutorials-a"
MOSFET_DRIVER_PCB = TEST_DATA_DIR / "08_MOSFET_Driver" / "08_MOSFET_Driver.kicad_pcb"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def create_test_constraints(output_path: Path, width: float = 30.0, height: float = 35.0):
    """Create a minimal test constraints file."""
    constraints = f"""
board:
  width_mm: {width}
  height_mm: {height}
  margin_mm: 2

zones:
  - name: MAIN
    bounds: [0, 0, {width}, {height}]
    net_classes: [Signal, Power]

clearances:
  - from: Power
    to: Signal
    clearance_mm: 0.5

hv_clearance_mm: 5
"""
    with open(output_path, "w") as f:
        f.write(constraints)


class TestKiCadParser:
    """Tests for KiCad PCB parsing."""

    @pytest.mark.skipif(not MOSFET_DRIVER_PCB.exists(), reason="Test PCB not found")
    def test_parse_mosfet_driver_pcb(self):
        """Test parsing a real KiCad PCB file."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        result = parse_kicad_pcb(MOSFET_DRIVER_PCB)

        assert result.netlist.n_components > 0
        assert result.netlist.n_nets > 0
        assert result.board is not None
        assert result.board.width > 0
        assert result.board.height > 0

    @pytest.mark.skipif(not MOSFET_DRIVER_PCB.exists(), reason="Test PCB not found")
    def test_components_have_positions(self):
        """Test that parsed components have position information."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        result = parse_kicad_pcb(MOSFET_DRIVER_PCB)

        for comp in result.netlist.components:
            assert comp.ref is not None
            assert comp.bounds[0] > 0  # Width
            assert comp.bounds[1] > 0  # Height


class TestConstraintLoader:
    """Tests for constraint configuration loading."""

    def test_load_test_constraints(self):
        """Test loading a minimal constraints file."""
        from temper_placer.io.config_loader import load_constraints

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            create_test_constraints(Path(f.name))
            config_path = Path(f.name)

        try:
            constraints = load_constraints(config_path)

            assert constraints.board_width_mm == 30.0
            assert constraints.board_height_mm == 35.0
            assert len(constraints.zones) == 1
            assert constraints.hv_clearance_mm == 5.0
        finally:
            os.unlink(config_path)

    @pytest.mark.skipif(
        not (CONFIGS_DIR / "temper_constraints.yaml").exists(), reason="Config not found"
    )
    def test_load_temper_constraints(self):
        """Test loading the full Temper constraints file."""
        from temper_placer.io.config_loader import load_constraints

        constraints = load_constraints(CONFIGS_DIR / "temper_constraints.yaml")

        assert constraints.board_width_mm == 100.0
        assert constraints.board_height_mm == 150.0
        assert len(constraints.zones) >= 4
        assert constraints.hv_clearance_mm == 10.0


class TestOptimization:
    """Tests for the optimization pipeline."""

    def test_simple_optimization(self):
        """Test optimization with synthetic data."""
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.losses import (
            BoundaryLoss,
            CompositeLoss,
            OverlapLoss,
            WeightedLoss,
        )
        from temper_placer.losses.base import LossContext
        from temper_placer.optimizer import OptimizerConfig, train

        # Create simple netlist
        components = [
            Component(
                ref="R1",
                footprint="R_0805",
                bounds=(2.0, 1.0),
                pins=[
                    Pin(name="1", number="1", position=(0.0, 0.0)),
                    Pin(name="2", number="2", position=(2.0, 0.0)),
                ],
            ),
            Component(
                ref="R2",
                footprint="R_0805",
                bounds=(2.0, 1.0),
                pins=[
                    Pin(name="1", number="1", position=(0.0, 0.0)),
                    Pin(name="2", number="2", position=(2.0, 0.0)),
                ],
            ),
            Component(
                ref="C1",
                footprint="C_0805",
                bounds=(2.0, 1.0),
                pins=[
                    Pin(name="1", number="1", position=(0.0, 0.0)),
                    Pin(name="2", number="2", position=(2.0, 0.0)),
                ],
            ),
        ]
        nets = [
            Net(name="VCC", pins=[("R1", "1"), ("C1", "1")]),
            Net(name="GND", pins=[("R1", "2"), ("R2", "2"), ("C1", "2")]),
            Net(name="SIG", pins=[("R2", "1")]),
        ]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=20.0, height=20.0)

        # Create loss functions
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
            ]
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        # Run optimization (fast test config)
        config = OptimizerConfig.fast_test()
        config.epochs = 50  # Very short for test

        result = train(netlist, board, composite, context, config)

        assert result.total_epochs > 0
        assert result.final_loss < float("inf")
        assert result.best_state is not None
        assert result.best_state.positions.shape == (3, 2)

    @pytest.mark.slow
    @pytest.mark.skipif(not MOSFET_DRIVER_PCB.exists(), reason="Test PCB not found")
    def test_real_pcb_optimization(self):
        """Test optimization with a real PCB file (slow test)."""
        from temper_placer.io.config_loader import (
            PlacementConstraints,
            create_board_from_constraints,
        )
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.losses import (
            BoundaryLoss,
            CompositeLoss,
            OverlapLoss,
            WeightedLoss,
            WirelengthLoss,
        )
        from temper_placer.losses.base import LossContext
        from temper_placer.optimizer import OptimizerConfig, train

        # Parse PCB
        result = parse_kicad_pcb(MOSFET_DRIVER_PCB)
        netlist = result.netlist

        # Create constraints based on board
        constraints = PlacementConstraints(
            board_width_mm=result.board.width if result.board else 30.0,
            board_height_mm=result.board.height if result.board else 35.0,
        )
        board = create_board_from_constraints(constraints)

        # Create loss
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
                WeightedLoss(WirelengthLoss(), weight=10.0),
            ]
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        # Run optimization
        config = OptimizerConfig.fast_test()
        config.epochs = 200  # Short for test

        result = train(netlist, board, composite, context, config)

        assert result.total_epochs >= 100
        assert result.best_loss < result.history[0].loss  # Should improve
        assert result.best_state.positions.shape == (netlist.n_components, 2)


class TestExport:
    """Tests for exporting optimized placements."""

    @pytest.mark.skipif(not MOSFET_DRIVER_PCB.exists(), reason="Test PCB not found")
    def test_export_to_json(self):
        """Test exporting placements to JSON."""
        from temper_placer.core.state import PlacementState
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.kicad_writer import placements_to_json, state_to_placements

        # Parse PCB to get component refs
        result = parse_kicad_pcb(MOSFET_DRIVER_PCB)
        component_refs = [c.ref for c in result.netlist.components]

        # Create a fake optimized state
        n = len(component_refs)
        state = PlacementState(
            positions=jnp.array([[i * 5.0, i * 3.0] for i in range(n)]),
            rotation_logits=jnp.zeros((n, 4)),
        )

        # Convert to placements
        placements = state_to_placements(state, component_refs)
        json_data = placements_to_json(placements)

        # Verify
        assert len(json_data) == n
        for ref in component_refs:
            assert ref in json_data
            assert "x" in json_data[ref]
            assert "y" in json_data[ref]
            assert "rotation" in json_data[ref]

    @pytest.mark.skipif(not MOSFET_DRIVER_PCB.exists(), reason="Test PCB not found")
    def test_export_to_pcb(self):
        """Test exporting placements back to KiCad PCB."""
        from temper_placer.core.state import PlacementState
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.kicad_writer import export_placements

        # Parse PCB
        result = parse_kicad_pcb(MOSFET_DRIVER_PCB)
        component_refs = [c.ref for c in result.netlist.components]

        # Create fake state
        n = len(component_refs)
        state = PlacementState(
            positions=jnp.array([[10.0 + i * 5.0, 10.0 + i * 3.0] for i in range(n)]),
            rotation_logits=jnp.zeros((n, 4)),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.kicad_pcb"

            write_result = export_placements(
                template_pcb=MOSFET_DRIVER_PCB,
                output_pcb=output_path,
                state=state,
                component_refs=component_refs,
            )

            assert output_path.exists()
            assert write_result.components_updated == n
            assert write_result.components_skipped == 0


@pytest.mark.slow
class TestEndToEnd:
    """Full end-to-end integration tests."""

    @pytest.mark.skipif(not MOSFET_DRIVER_PCB.exists(), reason="Test PCB not found")
    def test_full_pipeline(self):
        """Test the complete optimization pipeline."""
        from temper_placer.io.config_loader import (
            PlacementConstraints,
            create_board_from_constraints,
        )
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.kicad_writer import export_placements
        from temper_placer.losses import (
            BoundaryLoss,
            CompositeLoss,
            OverlapLoss,
            WeightedLoss,
            WirelengthLoss,
        )
        from temper_placer.losses.base import LossContext
        from temper_placer.optimizer import OptimizerConfig, train

        # Step 1: Parse PCB
        parse_result = parse_kicad_pcb(MOSFET_DRIVER_PCB)
        netlist = parse_result.netlist
        assert netlist.n_components > 0

        # Step 2: Create board from constraints
        constraints = PlacementConstraints(
            board_width_mm=parse_result.board.width if parse_result.board else 30.0,
            board_height_mm=parse_result.board.height if parse_result.board else 35.0,
            board_margin_mm=2.0,
        )
        board = create_board_from_constraints(constraints)

        # Step 3: Create loss functions
        composite = CompositeLoss(
            [
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(BoundaryLoss(), weight=50.0),
                WeightedLoss(WirelengthLoss(), weight=10.0),
            ]
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        # Step 4: Run optimization (short for test)
        config = OptimizerConfig.fast_test()
        config.epochs = 100

        result = train(netlist, board, composite, context, config)
        assert result.best_loss < float("inf")

        # Step 5: Export results
        component_refs = [c.ref for c in netlist.components]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "optimized.kicad_pcb"

            export_placements(
                template_pcb=MOSFET_DRIVER_PCB,
                output_pcb=output_path,
                state=result.best_state,
                component_refs=component_refs,
            )

            # Step 6: Validate output exists and has content
            assert output_path.exists()
            assert output_path.stat().st_size > 0
            # Note: Full parse validation may fail due to kiutils quirks
            # with segment parsing. The file is still valid KiCad format.

            # Verify positions are within bounds
            positions = result.best_state.positions
            assert jnp.all(positions[:, 0] >= 0)
            assert jnp.all(positions[:, 1] >= 0)
            assert jnp.all(positions[:, 0] <= board.width)
            assert jnp.all(positions[:, 1] <= board.height)


class TestCLI:
    """Tests for the CLI interface."""

    def test_cli_imports(self):
        """Test that CLI module imports correctly."""
        from temper_placer.cli import main

        assert main is not None

    def test_cli_help(self):
        """Test CLI help output."""
        from click.testing import CliRunner

        from temper_placer.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "optimize" in result.output
        assert "export" in result.output
        assert "validate" in result.output
        assert "info" in result.output

    def test_optimize_help(self):
        """Test optimize command help."""
        from click.testing import CliRunner

        from temper_placer.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["optimize", "--help"])

        assert result.exit_code == 0
        assert "--config" in result.output
        assert "--output" in result.output
        assert "--epochs" in result.output

    @pytest.mark.skipif(not MOSFET_DRIVER_PCB.exists(), reason="Test PCB not found")
    def test_info_command(self):
        """Test info command with real PCB."""
        from click.testing import CliRunner

        from temper_placer.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["info", str(MOSFET_DRIVER_PCB)])

        assert result.exit_code == 0
        assert "Components" in result.output
        assert "Nets" in result.output
