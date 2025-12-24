"""
Training script for the GNN placement quality predictor.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import jax
import jax.numpy as jnp
import optax
from flax.training import train_state

from temper_placer.ml.data_loader import PcbDataset, create_batch
from temper_placer.ml.gnn_predictor import PlacementQualityGNN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrainState(train_state.TrainState):
    """Custom train state to handle GNN parameters."""
    pass

def create_train_state(rng, model, learning_rate):
    """Initializes the training state."""
    # Dummy inputs for initialization
    nodes = jnp.zeros((1, 3))
    positions = jnp.zeros((1, 2))
    edges = jnp.zeros((0, 2), dtype=jnp.int32)

    variables = model.init(rng, nodes, positions, edges)
    params = variables['params']
    tx = optax.adam(learning_rate)
    return TrainState.create(apply_fn=model.apply, params=params, tx=tx)

@jax.jit
def train_step(state, nodes, positions, edges, target_score):
    """Single training step."""
    def loss_fn(params):
        score_pred = state.apply_fn({'params': params}, nodes, positions, edges)
        loss = jnp.mean((score_pred - target_score) ** 2)
        return loss

    grad_fn = jax.value_and_grad(loss_fn)
    loss, grads = grad_fn(state.params)
    state = state.apply_gradients(grads=grads)
    return state, loss

def train_gnn(
    dataset_dir: Path,
    epochs: int = 100,
    batch_size: int = 8,
    learning_rate: float = 1e-3,
    seed: int = 42
):
    """Main training loop."""
    rng = jax.random.PRNGKey(seed)

    # 1. Load Dataset
    dataset = PcbDataset(dataset_dir)
    if len(dataset) == 0:
        logger.error(f"No samples found in {dataset_dir}")
        return

    logger.info(f"Loaded dataset with {len(dataset)} samples")

    # 2. Initialize Model
    model = PlacementQualityGNN()
    rng, init_rng = jax.random.split(rng)
    state = create_train_state(init_rng, model, learning_rate)

    # 3. Training Loop
    for epoch in range(epochs):
        # Shuffle indices
        rng, shuffle_rng = jax.random.split(rng)
        indices = jax.random.permutation(shuffle_rng, len(dataset))

        epoch_loss = 0.0
        n_batches = 0

        for i in range(0, len(dataset), batch_size):
            batch_indices = indices[i:i+batch_size]
            samples = [dataset.get_sample(int(idx)) for idx in batch_indices]

            # Batch samples (NetlistGraph -> Unified graph)
            graph, pos, target = create_batch(samples)

            # Update weights
            state, loss = train_step(state, graph.nodes, pos, graph.edges, target)
            epoch_loss += loss
            n_batches += 1

        if epoch % 10 == 0:
            avg_loss = epoch_loss / n_batches
            logger.info(f"Epoch {epoch}: Loss = {avg_loss:.6f}")

    return state

def main():
    parser = argparse.ArgumentParser(description="Train Placement Quality GNN")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to dataset directory")
    parser.add_argument("--epochs", type=int, default=100, help="Number of epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--output", type=Path, default=Path("gnn_model.pkl"), help="Model output path")
    args = parser.parse_args()

    final_state = train_gnn(
        dataset_dir=args.dataset,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr
    )

    if final_state:
        # Save model (simplified)
        import pickle
        with open(args.output, "wb") as f:
            pickle.dump(final_state.params, f)
        logger.info(f"Saved model to {args.output}")

if __name__ == "__main__":
    main()
