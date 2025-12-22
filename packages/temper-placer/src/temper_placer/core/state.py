"""
PlacementState: Core state representation for PCB placement optimization.

This module defines the central state object that holds component positions
and rotation parameters during optimization. The state is designed to be
JAX-compatible for automatic differentiation.
"""

from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
from jax import Array


@dataclass
class PlacementState:
    """
    JAX-compatible state holding component positions and rotation logits.

    Attributes:
        positions: (N, 2) array of component center (x, y) positions in mm.
        rotation_logits: (N, 4) array of rotation preference logits.
            Index 0=0°, 1=90°, 2=180°, 3=270°.

    The rotation_logits are used with Gumbel-Softmax to sample discrete
    rotations differentiably during training.
    """

    positions: Array  # (N, 2) float32
    rotation_logits: Array  # (N, 4) float32
    net_virtual_nodes: Array | None = None  # (M, 2) float32, optional for backward compat

    @classmethod
    def from_positions(
        cls,
        positions: Array,
        rotation_logits: Array | None = None,
        net_virtual_nodes: Array | None = None,
    ) -> PlacementState:
        """
        Create a PlacementState from positions, with optional initial rotation logits.

        Args:
            positions: (N, 2) array of component positions.
            rotation_logits: Optional (N, 4) array. If None, initialized to zeros
                (uniform distribution over rotations).
            net_virtual_nodes: Optional (M, 2) array of net virtual nodes.

        Returns:
            New PlacementState instance.
        """
        n_components = positions.shape[0]
        if rotation_logits is None:
            rotation_logits = jnp.zeros((n_components, 4), dtype=jnp.float32)
        return cls(
            positions=positions,
            rotation_logits=rotation_logits,
            net_virtual_nodes=net_virtual_nodes,
        )

    @classmethod
    def random_init(
        cls,
        n_components: int,
        board_width: float,
        board_height: float,
        key: Array,
        margin: float = 10.0,
        origin: tuple[float, float] = (0.0, 0.0),
        n_nets: int = 0,
    ) -> PlacementState:
        """
        Create a random initial placement within board bounds.

        Args:
            n_components: Number of components to place.
            board_width: Board width in mm.
            board_height: Board height in mm.
            key: JAX random key.
            margin: Margin from board edges in mm.
            origin: Board origin offset (ox, oy) in mm. Positions will be in
                absolute coordinates: [origin[0] + margin, origin[0] + width - margin].
                Default (0, 0) gives relative coordinates for backward compatibility.
            n_nets: Number of nets for virtual node initialization. If 0,
                net_virtual_nodes will be None.

        Returns:
            New PlacementState with random positions and uniform rotation logits.

        Note:
            For KiCad PCBs, the board origin is typically non-zero (e.g., (100, 50)).
            When optimizing for DRC compliance, use the board's actual origin to
            ensure positions are in absolute coordinates that match the PCB file.
        """
        key1, key2, key3, key4 = jax.random.split(key, 4)
        ox, oy = origin

        # Random positions within margins (absolute coordinates)
        x = jax.random.uniform(
            key1, (n_components,), minval=ox + margin, maxval=ox + board_width - margin
        )
        y = jax.random.uniform(
            key2, (n_components,), minval=oy + margin, maxval=oy + board_height - margin
        )
        positions = jnp.stack([x, y], axis=-1)

        # Uniform rotation logits (zeros = equal probability)
        rotation_logits = jnp.zeros((n_components, 4), dtype=jnp.float32)

        # Initialize net virtual nodes if requested
        net_virtual_nodes = None
        if n_nets > 0:
            # Randomly place net nodes on board too
            nx = jax.random.uniform(
                key3, (n_nets,), minval=ox + margin, maxval=ox + board_width - margin
            )
            ny = jax.random.uniform(
                key4, (n_nets,), minval=oy + margin, maxval=oy + board_height - margin
            )
            net_virtual_nodes = jnp.stack([nx, ny], axis=-1)

        return cls(
            positions=positions,
            rotation_logits=rotation_logits,
            net_virtual_nodes=net_virtual_nodes,
        )

    def get_rotations(self, temperature: float, key: Array) -> Array:
        """
        Sample rotations differentiably using Gumbel-Softmax.

        Args:
            temperature: Softmax temperature. High (e.g., 5.0) for exploration,
                low (e.g., 0.1) for near-discrete sampling.
            key: JAX random key.

        Returns:
            (N, 4) soft one-hot rotation indicators. During training these are
            continuous; use straight-through estimator for gradients.
        """
        return sample_rotation(self.rotation_logits, key, temperature)

    def get_rotation_angles(self, temperature: float, key: Array) -> Array:
        """
        Get rotation angles in radians using Gumbel-Softmax sampling.

        Args:
            temperature: Softmax temperature.
            key: JAX random key.

        Returns:
            (N,) array of rotation angles in radians.
        """
        rotations = self.get_rotations(temperature, key)
        angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])
        return jnp.sum(rotations * angles, axis=-1)

    def to_discrete(self) -> tuple[Array, Array]:
        """
        Convert to discrete placement (argmax rotations).

        Returns:
            Tuple of (positions, rotation_indices) where rotation_indices
            are integers 0-3 representing 0°, 90°, 180°, 270°.
        """
        # Helper for returning just clean positions/rotations
        rotation_indices = jnp.argmax(self.rotation_logits, axis=-1)
        return self.positions, rotation_indices

    @property
    def n_components(self) -> int:
        """Number of components in this state."""
        return self.positions.shape[0]


def sample_rotation(logits: Array, key: Array, temperature: float = 1.0) -> Array:
    """
    Sample rotation differentiably using Gumbel-Softmax.

    This implements the Gumbel-Softmax trick for differentiable discrete sampling.
    During training, returns soft one-hot vectors. Uses straight-through estimator
    for gradients (forward uses hard, backward uses soft).

    Args:
        logits: (N, 4) rotation preference logits for N components.
        key: JAX random key for Gumbel noise.
        temperature: Softmax temperature. Anneal from ~5.0 to ~0.1 during training.

    Returns:
        (N, 4) one-hot rotation indicators. Soft during training (continuous),
        hard in forward pass via straight-through.

    Example:
        >>> key = jax.random.PRNGKey(0)
        >>> logits = jnp.zeros((10, 4))  # 10 components, uniform priors
        >>> rotations = sample_rotation(logits, key, temperature=1.0)
        >>> # rotations.shape == (10, 4), each row sums to ~1
    """
    # Add Gumbel noise: -log(-log(U)) where U ~ Uniform(0, 1)
    eps = 1e-10
    uniform = jax.random.uniform(key, logits.shape, minval=eps, maxval=1.0 - eps)
    gumbel = -jnp.log(-jnp.log(uniform))

    # Soft sample
    soft = jax.nn.softmax((logits + gumbel) / temperature)

    # Hard sample (one-hot)
    hard = jax.nn.one_hot(jnp.argmax(soft, axis=-1), 4)

    # Straight-through estimator: use hard in forward, soft gradients in backward
    return soft + jax.lax.stop_gradient(hard - soft)


def rotation_matrix(angle: float) -> Array:
    """
    Create a 2D rotation matrix for the given angle.

    Args:
        angle: Rotation angle in radians.

    Returns:
        (2, 2) rotation matrix.
    """
    cos_a = jnp.cos(angle)
    sin_a = jnp.sin(angle)
    return jnp.array([[cos_a, -sin_a], [sin_a, cos_a]])


def rotate_points(points: Array, angle: float, center: Array | None = None) -> Array:
    """
    Rotate points around a center.

    Args:
        points: (..., 2) array of points.
        angle: Rotation angle in radians.
        center: (2,) rotation center. If None, rotate around origin.

    Returns:
        (..., 2) rotated points.
    """
    if center is not None:
        points = points - center
    rotated = points @ rotation_matrix(angle).T
    if center is not None:
        rotated = rotated + center
    return rotated
