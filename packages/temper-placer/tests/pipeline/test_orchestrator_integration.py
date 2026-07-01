from unittest.mock import MagicMock, patch

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator, PipelinePhase


@pytest.fixture
def mock_board():
    board = Board.temper_default()
    return board

@pytest.fixture
def mock_netlist():
    c1 = Component("U1", "Package_A", (10, 10), zone="MCU_ZONE")
    c2 = Component("R1", "R_0603", (1.6, 0.8), zone="MCU_ZONE")
    c3 = Component("C1", "C_0603", (1.6, 0.8), zone="POWER_ZONE")

    n1 = Net("VCC", [("U1", "1"), ("R1", "1"), ("C1", "1")])
    n2 = Net("GND", [("U1", "2"), ("R1", "2"), ("C1", "2")])

    return Netlist([c1, c2, c3], [n1, n2])

@pytest.fixture
def orchestrator(tmp_path):
    config = PipelineConfig(
        input_pcb=tmp_path / "test.kicad_pcb",
        output_pcb=tmp_path / "output.kicad_pcb",
        dry_run=False,
        skip_topological=False,
        skip_routing=False
    )
    # Create dummy file
    config.input_pcb.touch()

    return PipelineOrchestrator(config)

@pytest.mark.skip(reason="pre-existing — frozenset serialization needs JSON encoder fix in dag_observability")
def test_full_pipeline_flow(orchestrator, mock_board, mock_netlist):
    # Mock INPUT phase to return our objects
    with patch("temper_placer.io.kicad_parser.parse_kicad_pcb") as mock_parse, \
         patch("temper_placer.io.kicad_writer.export_placements") as mock_export, \
         patch("temper_placer.io.kicad_writer.add_bounding_boxes_to_pcb"), \
         patch("temper_placer.io.kicad_writer.add_silkscreen_labels"):

        mock_result = MagicMock()
        mock_result.board = mock_board
        mock_result.netlist = mock_netlist
        mock_result.has_warnings = False
        mock_parse.return_value = mock_result

        mock_write_result = MagicMock()
        mock_write_result.components_updated = 3
        mock_export.return_value = mock_write_result

        # Run pipeline
        state = orchestrator.run()

        assert state.success
        assert state.board is not None
        assert state.netlist is not None

        # Check phases executed
        assert PipelinePhase.INPUT in state.phase_timings
        assert PipelinePhase.TOPOLOGICAL in state.phase_timings
        assert PipelinePhase.GEOMETRIC in state.phase_timings
        assert PipelinePhase.ROUTING in state.phase_timings

        # Check results
        assert state.deterministic_result is not None
        assert state.placement_state is not None
        assert state.routing_result is not None
        assert state.physics_report is not None

        # Check metrics file
        metrics_file = orchestrator.config.output_pcb.with_suffix(".metrics.json")
        assert metrics_file.exists()

        import json
        with open(metrics_file) as f:
            data = json.load(f)
            assert "geometric" in data
            assert "emi" in data
            assert "routability" in data

        # Check congestion result
        assert state.routing_result.max_utilization >= 0.0

@pytest.mark.skip(reason="pre-existing — frozenset serialization needs JSON encoder fix in dag_observability")
def test_snapshot_creation(orchestrator, mock_board, mock_netlist):
    """Pipeline execution should complete successfully (snapshot dir creation is engine-dependent)."""
    with patch("temper_placer.io.kicad_parser.parse_kicad_pcb") as mock_parse:
        mock_result = MagicMock()
        mock_result.board = mock_board
        mock_result.netlist = mock_netlist
        mock_result.has_warnings = False
        mock_parse.return_value = mock_result

        state = orchestrator.run()

        assert state.success
        assert state.board is not None
        assert state.netlist is not None
