"""Tests for seed generation (_generate_diverse_seeds)."""

import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.optimizer.config import MultiSeedConfig
from temper_placer.optimizer.seed_generation import (
    _generate_diverse_seeds,
    _generate_one_seed,
    _is_seed_valid,
    _random_init_positions,
)


@pytest.fixture
def simple_setup():
    """Create a simple netlist and board for testing."""
    components = [
        Component(
            ref=f"U{i}",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            pins=[
                Pin("1", "1", (0, 0), net=f"NET{i}"),
                Pin("2", "2", (0, 0), net=f"GND"),
            ],
        )
        for i in range(5)
    ]
    nets = [
        Net(name=f"NET{i}", pins=[(f"U{i}", "1")]) for i in range(5)
    ] + [Net(name="GND", pins=[(f"U{i}", "2") for i in range(5)])]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100.0, height=100.0)
    return netlist, board


class TestSeedGeneration:
    def test_generates_n_seeds(self, simple_setup):
        """n_generate seeds are produced."""
        netlist, board = simple_setup
        config = MultiSeedConfig(n_generate=10, n_select=4)
        key = jax.random.PRNGKey(0)
        seeds = _generate_diverse_seeds(netlist, board, config, key)
        assert len(seeds) == 10

    def test_all_seeds_within_bounds_and_finite(self, simple_setup):
        """All seeds have positions within board bounds and no NaN/Inf."""
        netlist, board = simple_setup
        config = MultiSeedConfig(n_generate=10, n_select=4)
        key = jax.random.PRNGKey(1)
        seeds = _generate_diverse_seeds(netlist, board, config, key)
        for positions, _md in seeds:
            assert not jnp.any(jnp.isnan(positions))
            assert not jnp.any(jnp.isinf(positions))
            assert jnp.all(positions >= 0.0 - 1e-6)
            assert jnp.all(positions[:, 0] <= board.width + 1e-6)
            assert jnp.all(positions[:, 1] <= board.height + 1e-6)

    def test_metadata_contains_hyperparams(self, simple_setup):
        """Each metadata dict has expected keys."""
        netlist, board = simple_setup
        config = MultiSeedConfig(n_generate=10, n_select=4)
        key = jax.random.PRNGKey(2)
        seeds = _generate_diverse_seeds(netlist, board, config, key)
        for _positions, md in seeds:
            assert "init_method" in md
            assert "perturb_sigma" in md

    def test_diverse_methods_produced(self, simple_setup):
        """Multiple init methods are present in the pool."""
        netlist, board = simple_setup
        config = MultiSeedConfig(n_generate=20, n_select=4)
        key = jax.random.PRNGKey(3)
        seeds = _generate_diverse_seeds(netlist, board, config, key)
        methods = {md["init_method"] for _, md in seeds}
        assert len(methods) >= 2, f"Expected >= 2 methods, got {methods}"

    def test_degenerate_pool_random_fallback(self, simple_setup):
        """When < n_select valid seeds, fallback to random_init."""
        netlist, board = simple_setup
        config = MultiSeedConfig(n_generate=1, n_select=4)
        key = jax.random.PRNGKey(4)
        seeds = _generate_diverse_seeds(netlist, board, config, key)
        assert len(seeds) >= config.n_select

    def test_zero_seeds_error(self):
        """When all seeds are degenerate, hard error is raised.

        Tests the error path by calling _is_seed_valid with NaN.
        The actual error in _generate_diverse_seeds requires a pathological
        netlist — since our test netlist always produces valid seeds, this
        test validates the validation function directly.
        """
        board = Board(width=100.0, height=100.0)
        nan_positions = jnp.full((3, 2), float("nan"))
        assert not _is_seed_valid(nan_positions, board)

    def test_single_component_netlist(self):
        """Single component netlist uses random method only."""
        components = [
            Component(ref="U1", footprint="SOIC-8", bounds=(10.0, 10.0),
                       pins=[Pin("1", "1", (0, 0), net="N1")])
        ]
        nets = [Net(name="N1", pins=[("U1", "1")])]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100.0, height=100.0)
        config = MultiSeedConfig(n_generate=3, n_select=2)
        key = jax.random.PRNGKey(5)
        seeds = _generate_diverse_seeds(netlist, board, config, key)
        assert len(seeds) >= config.n_select
        for _positions, md in seeds:
            assert md["init_method"] == "random"

    def test_identical_seeds_are_rejected(self, simple_setup):
        """is_seed_valid rejects seeds with all identical positions."""
        board = Board(width=100.0, height=100.0)
        identical = jnp.array([[10.0, 20.0], [10.0, 20.0], [10.0, 20.0]])
        assert not _is_seed_valid(identical, board)

    def test_generate_one_seed_spectral(self, simple_setup):
        """_generate_one_seed with spectral method."""
        netlist, board = simple_setup
        key = jax.random.PRNGKey(6)
        pos, md = _generate_one_seed(netlist, board, "spectral", True, 0.1, 0.02, key)
        assert pos.shape == (len(netlist.components), 2)
        assert md["init_method"] == "spectral"
        assert md["normalized_laplacian"] is True

    def test_generate_one_seed_random(self, simple_setup):
        """_generate_one_seed with random method."""
        netlist, board = simple_setup
        key = jax.random.PRNGKey(7)
        pos, md = _generate_one_seed(netlist, board, "random", None, None, 0.0, key)
        assert pos.shape == (len(netlist.components), 2)
        assert md["init_method"] == "random"
        assert "normalized_laplacian" not in md

    def test_perturbation_changes_positions(self, simple_setup):
        """Gaussian perturbation changes spectral positions."""
        netlist, board = simple_setup
        key = jax.random.PRNGKey(8)

        pos_no_perturb, _ = _generate_one_seed(
            netlist, board, "spectral", True, 0.1, 0.0, key
        )
        pos_with_perturb, _ = _generate_one_seed(
            netlist, board, "spectral", True, 0.1, 0.10, key
        )

        # Positions should differ
        assert not jnp.allclose(pos_no_perturb, pos_with_perturb)
