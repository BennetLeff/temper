"""Tests for PlaceRouteIterator - TDD approach.

Part of temper-1d78.2
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
import jax.numpy as jnp
import numpy as np

from temper_placer.pipeline.orchestrator import PipelineState, PipelineConfig
from temper_placer.core.state import PlacementState

class TestPlaceRouteIterator:
    """Tests for the PlaceRouteIterator class."""

    def test_iterator_exists(self):
        """PlaceRouteIterator class should exist."""
        from temper_placer.pipeline.iterator import PlaceRouteIterator
        assert PlaceRouteIterator is not None

    def test_iterator_initialization(self):
        """PlaceRouteIterator should initialize with required components."""
        from temper_placer.pipeline.iterator import PlaceRouteIterator
        
        mock_netlist = MagicMock()
        mock_board = MagicMock()
        mock_router = MagicMock()
        
        iterator = PlaceRouteIterator(
            netlist=mock_netlist,
            board=mock_board,
            router=mock_router
        )
        
        assert iterator.netlist == mock_netlist
        assert iterator.board == mock_board
        assert iterator.router == mock_router
        assert iterator.max_iterations == 10  # Default value

    def test_iterator_run_returns_result(self):
        """run() should return an IterationResult."""
        from temper_placer.pipeline.iterator import PlaceRouteIterator, PlaceRouteResult
        
        mock_netlist = MagicMock()
        mock_board = MagicMock()
        mock_router = MagicMock()
        
        # Mock initial positions
        n_comp = 5
        initial_pos = jnp.zeros((n_comp, 2))
        
        # Mock router results
        mock_routing_result = MagicMock()
        mock_routing_result.is_feasible.return_value = True
        mock_routing_result.completion_rate = 1.0
        mock_router.route.return_value = mock_routing_result
        
        iterator = PlaceRouteIterator(
            netlist=mock_netlist,
            board=mock_board,
            router=mock_router
        )
        
        result = iterator.run(initial_pos)
        
        assert isinstance(result, PlaceRouteResult)
        assert result.converged is True
        assert result.iterations == 1

    def test_iterator_loop_execution(self):
        """Iterator should run for multiple iterations if not feasible."""
        from temper_placer.pipeline.iterator import PlaceRouteIterator
        
        mock_netlist = MagicMock()
        mock_netlist.n_components = 2
        mock_board = MagicMock()
        mock_router = MagicMock()
        
        initial_pos = jnp.zeros((2, 2))
        
        # Mock router to fail twice then succeed
        res_fail = MagicMock()
        res_fail.is_feasible.return_value = False
        res_fail.completion_rate = 0.5
        
        res_success = MagicMock()
        res_success.is_feasible.return_value = True
        res_success.completion_rate = 1.0
        
        mock_router.route.side_effect = [res_fail, res_fail, res_success]
        
        # Mock placement update to just return the same positions for simplicity
        mock_updater = MagicMock(side_effect=lambda pos, feedback: pos)
        
        iterator = PlaceRouteIterator(
            netlist=mock_netlist,
            board=mock_board,
            router=mock_router,
            placement_update_fn=mock_updater,
            max_iterations=5
        )
        
        result = iterator.run(initial_pos)
        
        assert result.iterations == 3
        assert result.converged is True
        assert mock_router.route.call_count == 3
        assert mock_updater.call_count == 2
