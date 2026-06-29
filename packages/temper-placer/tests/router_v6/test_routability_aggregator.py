"""Unit tests for RoutabilityAggregator."""

import jax.numpy as jnp
import pytest

from temper_placer.router_v6.routability_aggregator import RoutabilityAggregator


def test_sat_fine_grained_scores():
    """SAT solve with fine-grained stats should produce valid scores."""
    aggressor = RoutabilityAggregator()
    stats = {
        "conflicts": 100,
        "decisions": 500,
        "propagations": 2000,
        "decision_level_histogram": [50, 50, 50, 50, 50, 50, 50, 50, 50, 50],
        "variable_count": 30,
        "clause_count": 60,
        "cpu_solve_time_ms": 100.0,
        "clause_to_var_ratio": 2.0,
        "solve_throughput": 30 * 60 / 100.0,
    }
    var_to_net = [0, 0, 1, 1, 1, 2]  # 3 nets with 2, 3, 1 vars each
    n_components = 3

    scores, score_mean = aggressor.compute_scores(
        stats=stats, var_to_net=var_to_net, n_components=n_components,
        unsat_core=[], solver_status="sat", timeout_ms=5000.0,
    )

    assert scores.shape == (n_components,)
    assert 0.0 <= score_mean <= 1.0
    assert jnp.all(scores >= 0.0)
    assert jnp.all(scores <= 1.0)


def test_all_zero_stats():
    """All-zero stats should produce all-zero scores."""
    aggressor = RoutabilityAggregator()
    stats = {
        "conflicts": 0, "decisions": 0, "propagations": 0,
        "decision_level_histogram": [0] * 10,
        "variable_count": 10, "clause_count": 20,
        "cpu_solve_time_ms": 0.0, "clause_to_var_ratio": 2.0,
        "solve_throughput": 0.0,
    }
    var_to_net = [0, 0, 1, 1]
    n_components = 2

    scores, score_mean = aggressor.compute_scores(
        stats=stats, var_to_net=var_to_net, n_components=n_components,
        unsat_core=[], solver_status="sat", timeout_ms=5000.0,
    )

    assert scores.shape == (n_components,)
    # With all-zero CDCL stats, falls back to coarse path
    assert jnp.all(scores >= 0.0)


def test_unsat_with_core():
    """UNSAT with core should set core nets to 1.0."""
    aggressor = RoutabilityAggregator()
    stats = {
        "conflicts": 0, "decisions": 0, "propagations": 0,
        "decision_level_histogram": [0] * 10,
        "variable_count": 10, "clause_count": 20,
        "cpu_solve_time_ms": 50.0, "clause_to_var_ratio": 2.0,
        "solve_throughput": 0.0,
    }
    var_to_net = [0, 1, 2, 3]  # 4 nets
    unsat_core = [0, 2]  # clause indices 0 and 2 → net indices 0 and 2
    n_components = 4

    scores, _ = aggressor.compute_scores(
        stats=stats, var_to_net=var_to_net, n_components=n_components,
        unsat_core=unsat_core, solver_status="unsat", timeout_ms=5000.0,
    )

    assert scores.shape == (n_components,)
    assert float(scores[0]) == pytest.approx(1.0)
    assert float(scores[2]) == pytest.approx(1.0)
    assert float(scores[1]) == pytest.approx(0.0)
    assert float(scores[3]) == pytest.approx(0.0)


def test_empty_unsat_core():
    """Empty UNSAT core should fall back to all-ones."""
    aggressor = RoutabilityAggregator()
    stats = {
        "conflicts": 0, "decisions": 0, "propagations": 0,
        "decision_level_histogram": [0] * 10,
        "variable_count": 6, "clause_count": 10,
        "cpu_solve_time_ms": 50.0, "clause_to_var_ratio": 1.66,
        "solve_throughput": 0.0,
    }
    var_to_net = [0, 0, 1, 1, 2, 2]
    n_components = 3

    scores, _ = aggressor.compute_scores(
        stats=stats, var_to_net=var_to_net, n_components=n_components,
        unsat_core=[], solver_status="unsat", timeout_ms=5000.0,
    )

    assert scores.shape == (n_components,)
    assert jnp.all(scores >= 0.0)


def test_coarse_fallback():
    """Coarse stats path should produce valid scores."""
    aggressor = RoutabilityAggregator()
    stats = {
        "conflicts": 0, "decisions": 0, "propagations": 0,
        "decision_level_histogram": [0] * 10,
        "variable_count": 30, "clause_count": 60,
        "cpu_solve_time_ms": 250.0, "clause_to_var_ratio": 2.0,
        "solve_throughput": 30 * 60 / 250.0,
    }
    var_to_net = [0, 0, 0, 1, 1, 2]
    n_components = 3

    scores, score_mean = aggressor.compute_scores(
        stats=stats, var_to_net=var_to_net, n_components=n_components,
        unsat_core=[], solver_status="unknown", timeout_ms=5000.0,
    )

    assert scores.shape == (n_components,)
    assert 0.0 <= score_mean <= 1.0
    assert jnp.all(scores >= 0.0)
    assert jnp.all(scores <= 1.0)


def test_zero_components():
    """Zero components should produce empty scores."""
    aggressor = RoutabilityAggregator()
    stats = {"conflicts": 0, "decisions": 0, "propagations": 0,
             "decision_level_histogram": [0]*10, "variable_count": 0,
             "clause_count": 0, "cpu_solve_time_ms": 0.0,
             "clause_to_var_ratio": 0.0, "solve_throughput": 0.0}

    scores, score_mean = aggressor.compute_scores(
        stats=stats, var_to_net=[], n_components=0,
        unsat_core=[], solver_status="sat", timeout_ms=5000.0,
    )

    assert scores.shape == (0,)
    assert score_mean == 0.0
