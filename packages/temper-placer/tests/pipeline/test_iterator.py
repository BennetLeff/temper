"""Tests for PlaceRouteIterator - TDD approach.

Part of temper-1d78.2
"""

from unittest.mock import MagicMock

import jax.numpy as jnp
import numpy as np


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
        res_fail1 = MagicMock()
        res_fail1.is_feasible.return_value = False
        res_fail1.completion_rate = 0.5

        res_fail2 = MagicMock()
        res_fail2.is_feasible.return_value = False
        res_fail2.completion_rate = 0.6

        res_success = MagicMock()
        res_success.is_feasible.return_value = True
        res_success.completion_rate = 1.0

        mock_router.route.side_effect = [res_fail1, res_fail2, res_success]

        # Mock placement update to just return the same positions for simplicity
        mock_updater = MagicMock(side_effect=lambda pos, _feedback: pos)

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

    def test_iterator_stops_on_stagnation(self):
        """Iterator should stop if improvement is below min_improvement."""
        from temper_placer.pipeline.iterator import PlaceRouteIterator

        mock_netlist = MagicMock()
        mock_board = MagicMock()
        mock_router = MagicMock()

        initial_pos = jnp.zeros((2, 2))

        # Mock router to show very small improvement
        res1 = MagicMock()
        res1.is_feasible.return_value = False
        res1.completion_rate = 0.5

        res2 = MagicMock()
        res2.is_feasible.return_value = False
        res2.completion_rate = 0.5001 # 0.0001 improvement

        mock_router.route.side_effect = [res1, res2]
        mock_updater = MagicMock(side_effect=lambda pos, _feedback: pos)

        iterator = PlaceRouteIterator(
            netlist=mock_netlist,
            board=mock_board,
            router=mock_router,
            placement_update_fn=mock_updater,
            min_improvement=0.01, # Threshold is 0.01
            max_iterations=5
        )

        result = iterator.run(initial_pos)

        # It should stop after 2nd iteration because improvement (0.0001) < 0.01
        assert result.iterations == 2
        assert result.converged is False

    def test_iterator_stops_on_max_iterations(self):
        """Iterator should stop after max_iterations."""
        from temper_placer.pipeline.iterator import PlaceRouteIterator

        mock_netlist = MagicMock()
        mock_board = MagicMock()
        mock_router = MagicMock()

        initial_pos = jnp.zeros((2, 2))

        # Mock router to always fail but with improvement
        def route_fn(_pos):
            res = MagicMock()
            res.is_feasible.return_value = False
            # Some improvement to avoid stagnation
            route_fn.call_count += 1
            res.completion_rate = 0.5 + 0.02 * route_fn.call_count
            return res
        route_fn.call_count = 0
        mock_router.route.side_effect = route_fn

        mock_updater = MagicMock(side_effect=lambda pos, _feedback: pos)

        iterator = PlaceRouteIterator(
            netlist=mock_netlist,
            board=mock_board,
            router=mock_router,
            placement_update_fn=mock_updater,
            max_iterations=3
        )

        result = iterator.run(initial_pos)

        assert result.iterations == 3
        assert result.converged is False
        assert len(result.iteration_history) == 3

    def test_iterator_returns_best_positions(self):
        """Iterator should return the positions that gave the best completion rate."""
        from temper_placer.pipeline.iterator import PlaceRouteIterator

        mock_netlist = MagicMock()
        mock_board = MagicMock()
        mock_router = MagicMock()

        # Positions as numpy for easier manipulation in mock
        pos1 = np.array([[1.0, 1.0]])
        pos2 = np.array([[2.0, 2.0]])
        pos3 = np.array([[3.0, 3.0]])

        # Iteration 1: 0.8 completion
        res1 = MagicMock()
        res1.is_feasible.return_value = False
        res1.completion_rate = 0.8

        # Iteration 2: 0.7 completion (worse!)
        res2 = MagicMock()
        res2.is_feasible.return_value = False
        res2.completion_rate = 0.7

        # Iteration 3: 0.75 completion (still worse than first)
        res3 = MagicMock()
        res3.is_feasible.return_value = False
        res3.completion_rate = 0.75

        mock_router.route.side_effect = [res1, res2, res3]

        # Mock updater to cycle through pos1, pos2, pos3
        mock_updater = MagicMock(side_effect=[pos2, pos3])

        iterator = PlaceRouteIterator(
            netlist=mock_netlist,
            board=mock_board,
            router=mock_router,
            placement_update_fn=mock_updater,
            max_iterations=3,
            min_improvement=-1.0 # Disable stagnation check
        )

        result = iterator.run(pos1)

        assert result.iterations == 3
        # Best positions should be pos1 (0.8 completion)
        assert np.allclose(result.final_positions, pos1)
