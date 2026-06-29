"""Integration tests for routability gradient feedback in refinement stage.

Verifies end-to-end flow: SAT solver -> stats -> scores -> loss -> gradient.
"""

import pytest
import jax.numpy as jnp
import numpy as np

from temper_placer.router_v6.routability_aggregator import RoutabilityAggregator
from temper_placer.losses.routability_gradient import RoutabilityGradientLoss
from temper_placer.losses.base import StatefulLossFunction, LossContext
from temper_placer.losses.types import NetlistContext


class TestEndToEndRoutabilityFlow:
    """Integration tests for the full routability -> loss flow."""

    def test_sat_stats_to_scores_to_loss(self):
        """Full pipeline: stats -> aggregator -> scores -> blend -> compute_loss."""
        stats = {
            "conflicts": 100, "decisions": 500, "propagations": 2000,
            "decision_level_histogram": [50] * 10,
            "variable_count": 30, "clause_count": 60,
            "cpu_solve_time_ms": 100.0, "clause_to_var_ratio": 2.0,
            "solve_throughput": 30 * 60 / 100.0,
        }
        var_to_net = [0, 0, 1, 1, 1, 2]
        n_components = 3

        aggressor = RoutabilityAggregator()
        scores, score_mean = aggressor.compute_scores(
            stats=stats, var_to_net=var_to_net, n_components=n_components,
            unsat_core=[], solver_status="sat", timeout_ms=5000.0,
        )

        assert 0.0 <= score_mean <= 1.0

        loss = RoutabilityGradientLoss()
        loss.blend({"routability_scores": scores, "iteration": 1})

        pos = jnp.array([[1.0, 1.0], [6.0, 2.0], [11.0, 11.0]])
        rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
        net_pin_indices = jnp.array([[0, 1], [1, 2]])
        net_pin_offsets = jnp.zeros((2, 2, 2))
        net_pin_mask = jnp.ones((2, 2), dtype=jnp.bool_)
        ctx = LossContext(
            netlist_data=NetlistContext(
                net_pin_indices=net_pin_indices,
                net_pin_offsets=net_pin_offsets,
                net_pin_mask=net_pin_mask,
            )
        )
        result = loss.compute_loss(pos, rot, ctx)
        assert float(result.value) >= 0.0

    def test_unsat_flow(self):
        """UNSAT solver result -> core-based scores -> loss with amplified signal."""
        stats = {
            "conflicts": 50, "decisions": 200, "propagations": 800,
            "decision_level_histogram": [0] * 10,
            "variable_count": 10, "clause_count": 20,
            "cpu_solve_time_ms": 50.0, "clause_to_var_ratio": 2.0,
            "solve_throughput": 0.0,
        }
        var_to_net = [0, 1, 2, 3]
        unsat_core = [0, 2]

        aggressor = RoutabilityAggregator()
        scores, _ = aggressor.compute_scores(
            stats=stats, var_to_net=var_to_net, n_components=4,
            unsat_core=unsat_core, solver_status="unsat", timeout_ms=5000.0,
        )

        assert float(scores[0]) == pytest.approx(1.0)
        assert float(scores[2]) == pytest.approx(1.0)
        assert float(scores[1]) == pytest.approx(0.0)

    def test_coarse_fallback_flow(self):
        """Coarse stats path: no CDCL stats -> fallback scores -> loss."""
        stats = {
            "conflicts": 0, "decisions": 0, "propagations": 0,
            "decision_level_histogram": [0] * 10,
            "variable_count": 12, "clause_count": 24,
            "cpu_solve_time_ms": 250.0, "clause_to_var_ratio": 2.0,
            "solve_throughput": 12 * 24 / 250.0,
        }
        var_to_net = [0, 0, 1, 1, 2, 2]

        aggressor = RoutabilityAggregator()
        scores, score_mean = aggressor.compute_scores(
            stats=stats, var_to_net=var_to_net, n_components=3,
            unsat_core=[], solver_status="unknown", timeout_ms=5000.0,
        )

        assert scores.shape == (3,)
        assert 0.0 <= score_mean <= 1.0

        loss = RoutabilityGradientLoss()
        loss.blend({"routability_scores": scores, "iteration": 2})
        pos = jnp.zeros((3, 2))
        rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
        ctx = LossContext()
        result = loss.compute_loss(pos, rot, ctx)
        assert float(result.value) >= 0.0

    def test_stateful_loss_type_hierarchy(self):
        """RoutabilityGradientLoss should inherit from StatefulLossFunction."""
        loss = RoutabilityGradientLoss()
        assert isinstance(loss, StatefulLossFunction)
        assert loss.name == "routability_gradient"

    def test_iterate_then_blend_produces_scores(self):
        """Multiple blend calls should produce EWMA-smoothed scores."""
        loss = RoutabilityGradientLoss()
        loss.blend({"routability_scores": jnp.array([1.0, 0.0, 0.0]), "iteration": 1})
        loss.blend({"routability_scores": jnp.array([0.5, 0.5, 0.0]), "iteration": 2})
        
        assert loss._ema_scores is not None
        assert loss._blend_count == 2
        mean = float(jnp.mean(loss._ema_scores))
        assert 0.0 <= mean <= 1.0
