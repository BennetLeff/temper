"""
Tests for conflict analysis module.
"""

import pytest
import jax.numpy as jnp
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.routing.maze_router import MazeRouter, RoutingProgress
from temper_placer.routing.layer_assignment import LayerAssignment, Layer
from temper_placer.routing.conflict_analysis import (
    ConflictType,
    ConflictInfo,
    ConflictAnalysis,
    analyze_conflicts,
    get_conflict_heatmap,
    format_conflict_report,
)


class TestConflictType:
    """Tests for ConflictType enum."""
    
    def test_conflict_types_exist(self):
        """Should have all expected conflict types."""
        assert ConflictType.OVERLAP.value == "overlap"
        assert ConflictType.BOTTLENECK.value == "bottleneck"
        assert ConflictType.ESCAPE.value == "escape"
        assert ConflictType.BOUNDARY.value == "boundary"


class TestConflictInfo:
    """Tests for ConflictInfo dataclass."""
    
    def test_conflict_info_creation(self):
        """Should create a valid conflict info."""
        info = ConflictInfo(
            cell=(10, 20, 0),
            nets=["NET_A", "NET_B"],
            conflict_type=ConflictType.OVERLAP,
            severity=0.3,
            location_mm=(10.0, 20.0),
        )
        
        assert info.cell == (10, 20, 0)
        assert len(info.nets) == 2
        assert info.conflict_type == ConflictType.OVERLAP
        assert info.severity == 0.3


class TestAnalyzeConflicts:
    """Tests for analyze_conflicts function."""
    
    def test_analyze_no_conflicts(self):
        """Should return empty analysis when no conflicts."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0) 
        
        # Route nothing - no conflicts
        analysis = analyze_conflicts(router)
        
        assert analysis.total_conflicts == 0
        assert analysis.overlap_count == 0
        assert analysis.bottleneck_count == 0
        assert len(analysis.conflicted_nets) == 0
    
    def test_analyze_with_conflicts(self):
        """Should classify conflicts correctly."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0)
        
        # Manually add conflicting occupancy
        router.net_occupancy[(5, 5, 0)] = {"NET_A", "NET_B"}  # overlap
        router.net_occupancy[(10, 10, 0)] = {"NET_C", "NET_D", "NET_E"}  # bottleneck
        
        analysis = analyze_conflicts(router)
        
        assert analysis.total_conflicts == 2
        assert analysis.overlap_count == 1
        assert analysis.bottleneck_count == 1
        assert "NET_A" in analysis.conflicted_nets
        assert "NET_C" in analysis.conflicted_nets


class TestRoutingProgress:
    """Tests for RoutingProgress dataclass."""
    
    def test_progress_creation(self):
        """Should create valid progress dataclass."""
        progress = RoutingProgress(
            iteration=1,
            total_iterations=10,
            p_scale=1.0,
            total_conflicts=5,
            overlap_conflicts=3,
            bottleneck_conflicts=2,
            nets_routed=10,
            nets_failed=2,
            avg_path_length=15.5,
            total_vias=5,
            iteration_time_ms=100.0,
            nets_per_second=100.0,
            conflicted_nets=["NET_A", "NET_B"],
        )
        
        assert progress.iteration == 1
        assert progress.total_conflicts == 5
        assert progress.overlap_conflicts == 3


class TestProgressCallback:
    """Tests for progress callback in rrr_route_all_nets."""
    
    def test_progress_callback_called(self):
        """Should call progress callback each iteration."""
        board = Board(width=20, height=20)
        
        c1 = Component(ref="C1", footprint="P", bounds=(2, 2), 
                       pins=[Pin("1", "1", (0, 0), "N1")], initial_position=(5, 5))
        c2 = Component(ref="C2", footprint="P", bounds=(2, 2), 
                       pins=[Pin("1", "1", (0, 0), "N1")], initial_position=(15, 5))
        
        n1 = Net("N1", [("C1", "1"), ("C2", "1")])
        
        netlist = Netlist(components=[c1, c2], nets=[n1])
        positions = jnp.array([[5., 5.], [15., 5.]])
        
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)
        
        progress_reports = []
        def capture_progress(p: RoutingProgress):
            progress_reports.append(p)
        
        net_order = ["N1"]
        assignments = {"N1": LayerAssignment("N1", Layer.L1_TOP, {Layer.L1_TOP})}
        
        router.rrr_route_all_nets(
            netlist, positions, net_order, assignments, 
            max_iterations=3, 
            progress_callback=capture_progress
        )
        
        # Should have at least 1 progress report
        assert len(progress_reports) >= 1
        assert progress_reports[0].iteration == 1
        assert progress_reports[0].nets_routed >= 0


class TestConflictHeatmap:
    """Tests for conflict heatmap generation."""
    
    def test_heatmap_shape(self):
        """Heatmap should have correct shape."""
        router = MazeRouter(grid_size=(30, 40), cell_size_mm=1.0, num_layers=2)
        
        heatmap = get_conflict_heatmap(router)
        
        assert heatmap.shape == (30, 40, 2)
    
    def test_heatmap_values(self):
        """Heatmap should reflect conflict severity."""
        router = MazeRouter(grid_size=(20, 20), cell_size_mm=1.0, num_layers=1)
        
        # Add a 3-net conflict at (5, 5, 0)
        router.net_occupancy[(5, 5, 0)] = {"A", "B", "C"}
        
        heatmap = get_conflict_heatmap(router)
        
        assert float(heatmap[5, 5, 0]) == 2.0  # 3 nets - 1 = 2
        assert float(heatmap[0, 0, 0]) == 0.0  # no conflict


class TestFormatConflictReport:
    """Tests for conflict report formatting."""
    
    def test_format_report(self):
        """Should generate readable report."""
        analysis = ConflictAnalysis(
            total_conflicts=5,
            overlap_count=3,
            bottleneck_count=2,
            escape_count=0,
            boundary_count=0,
            conflicts=[],
            conflicted_nets=["NET_A", "NET_B"],
            worst_cells=[(5, 5, 0, 3)],
        )
        
        report = format_conflict_report(analysis)
        
        assert "Total Conflicts: 5" in report
        assert "Overlap" in report
        assert "Bottleneck" in report
        assert "NET_A" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
