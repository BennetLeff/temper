
import jax
import jax.numpy as jnp

from temper_placer.ml.gnn_predictor import PlacementQualityGNN


def test_gnn_output_shape():
    """Verify that GNN produces a single scalar score between 0 and 1."""
    model = PlacementQualityGNN(hidden_dim=32)

    # Mock data
    n_nodes = 10
    n_edges = 20
    nodes = jnp.zeros((n_nodes, 3))
    positions = jnp.zeros((n_nodes, 2))
    edges = jnp.zeros((n_edges, 2), dtype=jnp.int32)

    # Initialize model
    rng = jax.random.PRNGKey(0)
    params = model.init(rng, nodes, positions, edges)['params']

    # Forward pass
    score = model.apply({'params': params}, nodes, positions, edges)

    assert score.shape == (1,)
    assert 0.0 <= float(score[0]) <= 1.0

def test_gnn_differentiable():
    """Verify that we can compute gradients w.r.t. positions."""
    model = PlacementQualityGNN(hidden_dim=16)
    nodes = jnp.zeros((5, 3))
    positions = jnp.zeros((5, 2))
    edges = jnp.array([[0, 1], [1, 2], [2, 3], [3, 4]])

    rng = jax.random.PRNGKey(42)
    params = model.init(rng, nodes, positions, edges)['params']

    def get_score(pos):
        return model.apply({'params': params}, nodes, pos, edges)[0]

    grad_fn = jax.grad(get_score)
    grads = grad_fn(positions)

    assert grads.shape == (5, 2)
    assert jnp.all(jnp.isfinite(grads))
