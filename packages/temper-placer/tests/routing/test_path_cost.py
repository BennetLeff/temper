"""Tests for path cost calculation."""

import pytest

from temper_placer.routing.cost import (
    BLOCKED_COST,
    analyze_path_difficulty,
    compute_path_cost,
    compute_path_length_mm,
    count_vias,
    extract_cells_from_paths,
)


class MockCell:
    """Mock cell for testing."""

    def __init__(self, x: int, y: int, layer: int):
        self.x = x
        self.y = y
        self.layer = layer


class TestComputePathCost:
    """Test path cost computation."""

    def test_empty_path(self):
        cost = compute_path_cost([], via_cost=1.0)
        assert cost == 0.0

    def test_single_cell(self):
        path = [MockCell(0, 0, 0)]
        cost = compute_path_cost(path, via_cost=1.0)
        assert cost == 1.0

    def test_no_vias(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0), MockCell(2, 0, 0)]
        cost = compute_path_cost(path, via_cost=1.0)
        assert cost == 3.0

    def test_single_via(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0), MockCell(2, 0, 1)]
        cost = compute_path_cost(path, via_cost=1.0)
        assert cost == 4.0

    def test_multiple_vias(self):
        path = [
            MockCell(0, 0, 0),
            MockCell(1, 0, 0),
            MockCell(2, 0, 1),
            MockCell(3, 0, 1),
            MockCell(4, 0, 0),
        ]
        cost = compute_path_cost(path, via_cost=1.0)
        assert cost == 7.0

    def test_custom_via_cost(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0), MockCell(2, 0, 1)]
        cost = compute_path_cost(path, via_cost=2.0)
        assert cost == 5.0


class TestCountVias:
    """Test via counting."""

    def test_empty_path(self):
        count = count_vias([])
        assert count == 0

    def test_single_cell(self):
        count = count_vias([MockCell(0, 0, 0)])
        assert count == 0

    def test_no_vias(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0), MockCell(2, 0, 0)]
        count = count_vias(path)
        assert count == 0

    def test_single_via(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0), MockCell(2, 0, 1)]
        count = count_vias(path)
        assert count == 1

    def test_multiple_vias(self):
        path = [
            MockCell(0, 0, 0),
            MockCell(1, 0, 0),
            MockCell(2, 0, 1),
            MockCell(3, 0, 1),
            MockCell(4, 0, 0),
        ]
        count = count_vias(path)
        assert count == 2


class TestComputePathLengthMm:
    """Test path length computation."""

    def test_empty_path(self):
        length = compute_path_length_mm([], cell_size=1.0)
        assert length == 0.0

    def test_single_cell(self):
        length = compute_path_length_mm([MockCell(0, 0, 0)], cell_size=1.0)
        assert length == 0.0

    def test_multiple_cells(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0), MockCell(2, 0, 0)]
        length = compute_path_length_mm(path, cell_size=0.5)
        assert length == 1.5

    def test_custom_cell_size(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0)]
        length = compute_path_length_mm(path, cell_size=0.25)
        assert length == 0.5


class TestExtractCellsFromPaths:
    """Test cell extraction from paths."""

    def test_empty_paths(self):
        cells = extract_cells_from_paths([])
        assert cells == []

    def test_single_path_no_duplicates(self):
        path = [MockCell(0, 0, 0), MockCell(1, 0, 0)]
        cells = extract_cells_from_paths([path])
        assert len(cells) == 2

    def test_multiple_paths_with_duplicates(self):
        path1 = [MockCell(0, 0, 0), MockCell(1, 0, 0)]
        path2 = [MockCell(1, 0, 0), MockCell(2, 0, 0)]
        cells = extract_cells_from_paths([path1, path2])
        assert len(cells) == 3

    def test_same_cell_different_layer(self):
        path1 = [MockCell(0, 0, 0), MockCell(1, 0, 0)]
        path2 = [MockCell(0, 0, 1), MockCell(1, 0, 1)]
        cells = extract_cells_from_paths([path1, path2])
        assert len(cells) == 4


class TestAnalyzePathDifficulty:
    """Test path difficulty analysis."""

    def test_empty_path(self):
        def get_difficulty(cell):
            return 1.0

        total, difficulties = analyze_path_difficulty([], get_difficulty)
        assert total == 0.0
        assert difficulties == []

    def test_single_cell(self):
        def get_difficulty(cell):
            return 2.0

        path = [MockCell(0, 0, 0)]
        total, difficulties = analyze_path_difficulty(path, get_difficulty)
        assert total == 2.0
        assert difficulties == [2.0]

    def test_multiple_cells(self):
        def get_difficulty(cell):
            return float(cell.x)

        path = [MockCell(0, 0, 0), MockCell(1, 0, 0), MockCell(2, 0, 0)]
        total, difficulties = analyze_path_difficulty(path, get_difficulty)
        assert total == 3.0
        assert difficulties == [0.0, 1.0, 2.0]


class TestPathCostConstants:
    """Test path cost constants."""

    def test_blocked_cost(self):
        assert BLOCKED_COST == 1e9
