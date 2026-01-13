"""Unit tests for Cython A* data structures.

Tests the core C data structures:
- MinHeap (priority queue)
- State indexing (3D to flat index conversion)
- GridView (direct memory access for grids)
"""

import pytest
import numpy as np


class TestMinHeap:
    """Test MinHeap operations."""

    def test_push_pop_single(self):
        """Single push/pop should work."""
        from temper_placer.routing.astar.astar_core import test_heap_operations

        assert test_heap_operations("push_pop_single") == True

    def test_push_pop_multiple_maintains_order(self):
        """Multiple push/pop should maintain min-heap order."""
        from temper_placer.routing.astar.astar_core import test_heap_operations

        assert test_heap_operations("min_order") == True

    def test_heap_resize(self):
        """Heap should automatically resize when full."""
        from temper_placer.routing.astar.astar_core import test_heap_operations

        assert test_heap_operations("resize") == True

    def test_heap_empty(self):
        """Pop from empty heap should return -1."""
        from temper_placer.routing.astar.astar_core import test_heap_operations

        assert test_heap_operations("empty") == True


class TestStateIndexing:
    """Test state indexing functions."""

    def test_roundtrip_conversion(self):
        """state_to_index -> index_to_state should be identity."""
        from temper_placer.routing.astar.astar_core import test_state_indexing

        assert test_state_indexing("roundtrip", 100, 80, 4) == True

    def test_all_states_unique(self):
        """All (row, col, layer) combinations should map to unique indices."""
        from temper_placer.routing.astar.astar_core import test_state_indexing

        assert test_state_indexing("unique", 100, 80, 4) == True

    def test_layer_separation(self):
        """States on different layers should have different indices."""
        from temper_placer.routing.astar.astar_core import test_state_indexing

        assert test_state_indexing("layer_separation", 100, 80, 4) == True


class TestGridView:
    """Test GridView operations."""

    def test_grid_get_set(self):
        """Grid get/set should work correctly."""
        from temper_placer.routing.astar.astar_core import test_grid_access

        assert test_grid_access("get_set") == True

    def test_grid_is_available_empty(self):
        """Empty cells should be available."""
        from temper_placer.routing.astar.astar_core import test_grid_access

        assert test_grid_access("available_empty") == True

    def test_grid_is_available_same_net(self):
        """Cells with same net_id should be available."""
        from temper_placer.routing.astar.astar_core import test_grid_access

        assert test_grid_access("available_same_net") == True

    def test_grid_is_available_blocked(self):
        """Cells with different net_id should be blocked."""
        from temper_placer.routing.astar.astar_core import test_grid_access

        assert test_grid_access("available_blocked") == True

    def test_grid_bounds_checking(self):
        """Out of bounds access should return False."""
        from temper_placer.routing.astar.astar_core import test_grid_access

        assert test_grid_access("bounds_check") == True
