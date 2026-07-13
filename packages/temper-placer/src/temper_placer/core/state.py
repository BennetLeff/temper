"""
PlacementState: Core state representation for PCB placement optimization.

This module defines the central state object that holds component positions
and rotation parameters during optimization. The state is designed to be
JAX-compatible for automatic differentiation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from temper_placer.core.netlist import Netlist

if TYPE_CHECKING:
    from temper_placer.core.board import Board


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

    positions: NDArray  # (N, 2) float32
    rotation_logits: NDArray  # (N, 4) float32
    net_virtual_nodes: NDArray | None = None  # (M, 2) float32, optional for backward compat

    @classmethod
    def from_positions(
        cls,
        positions: NDArray,
        rotation_logits: NDArray | None = None,
        net_virtual_nodes: NDArray | None = None,
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
            rotation_logits = np.zeros((n_components, 4), dtype=np.float32)
        return cls(
            positions=positions,
            rotation_logits=rotation_logits,
            net_virtual_nodes=net_virtual_nodes,
        )

    @classmethod
    def from_positions_dict(
        cls,
        positions_dict: dict[str, tuple[float, float]],
        netlist: Netlist | None = None,
        component_order: list[str] | None = None,
        *,
        rotation_logits: Array | None = None,
        net_virtual_nodes: Array | None = None,
    ) -> PlacementState:
        """
        Create a PlacementState from a dict of ``{component_ref: (x_mm, y_mm)}``.

        This factory wraps numpy/Python data into JAX arrays internally so the
        caller does **not** need to import JAX.  Either *netlist* or
        *component_order* must be provided to define the component ordering.

        Args:
            positions_dict: Mapping of component reference designator to
                ``(x_mm, y_mm)`` position.
            netlist: Netlist whose component order determines the row index of
                each position.  Components present in the netlist but absent
                from *positions_dict* will be placed at ``(0.0, 0.0)``.
            component_order: Alternative to *netlist* — an explicit list of
                component refs in order.  Exactly one of *netlist* or
                *component_order* must be given.
            rotation_logits: Optional ``(N, 4)`` array.  If ``None``, initialized
                to zeros (uniform distribution over rotations).
            net_virtual_nodes: Optional ``(M, 2)`` array of net virtual nodes.

        Returns:
            New ``PlacementState`` instance.

        Raises:
            ValueError: If neither *netlist* nor *component_order* is provided.
        """
        # @req(2026-07-03-001, R7): score_placement constructs PlacementState
        # from raw positions without JAX import by the caller
        if netlist is None and component_order is None:
            raise ValueError(
                "Either netlist or component_order must be provided "
                "to define component ordering"
            )

        order = (
            component_order
            if component_order is not None
            else [c.ref for c in netlist.components]  # type: ignore[union-attr]
        )

        positions_list = []
        for ref in order:
            if ref in positions_dict:
                positions_list.append(list(positions_dict[ref]))
            else:
                positions_list.append([0.0, 0.0])

        if not positions_list:
            raise ValueError("No positions provided and no components in netlist/order")

        positions_arr = jnp.array(positions_list, dtype=jnp.float32)
        n = positions_arr.shape[0]
        rot = rotation_logits if rotation_logits is not None else jnp.zeros((n, 4), dtype=jnp.float32)

        return cls(
            positions=positions_arr,
            rotation_logits=rot,
            net_virtual_nodes=net_virtual_nodes,
        )

    @classmethod
    def from_netlist_and_board(
        cls,
        netlist: Netlist,
        board: Board,
    ) -> PlacementState:
        """
        Create a PlacementState from a Netlist and Board.

        Args:
            netlist: The netlist containing components.
            board: The board definition.

        Returns:
            New PlacementState instance initialized from component data.
        """

        # Extract initial positions and rotations
        positions_list = []
        rotation_logits_list = []

        for comp in netlist.components:
            # Position
            if comp.initial_position:
                positions_list.append(list(comp.initial_position))
            else:
                # Default to board center if no initial position
                positions_list.append([board.width / 2.0, board.height / 2.0])

            # Rotation
            logits = [0.0, 0.0, 0.0, 0.0]
            if comp.initial_rotation is not None:
                # Set high logit for initial rotation (e.g. 10.0 vs 0.0)
                # This makes it the preferred rotation but allows optimization to change it
                idx = comp.initial_rotation % 4
                logits[idx] = 10.0
            rotation_logits_list.append(logits)

        positions = np.array(positions_list, dtype=np.float32)
        rotation_logits = np.array(rotation_logits_list, dtype=np.float32)

        # Initialize virtual nodes for nets
        n_nets = netlist.n_nets
        net_virtual_nodes = None
        if n_nets > 0:
            # Initialize to board center
            net_virtual_nodes = np.full((n_nets, 2),
                                       np.array([board.width / 2.0, board.height / 2.0]),
                                       dtype=np.float32)

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
        key: NDArray | None = None,
        margin: float = 10.0,
        origin: tuple[float, float] = (0.0, 0.0),
        n_nets: int = 0,
    ) -> PlacementState:
        """DEPRECATED: JAX random initialization removed.

        Use CP-SAT placer for initial placement instead.
        """
        raise NotImplementedError(
            "PlacementState.random_init removed (JAX retirement). "
            "Use CP-SAT placer for initial placement."
        )

    def get_rotations(self, temperature: float, key: NDArray) -> NDArray:
        """DEPRECATED: JAX Gumbel-Softmax rotation sampling removed."""
        raise NotImplementedError(
            "get_rotations removed (JAX retirement). "
            "Use CP-SAT placer for discrete placement decisions."
        )

    def get_rotation_angles(self, temperature: float, key: NDArray) -> NDArray:
        """DEPRECATED: JAX Gumbel-Softmax rotation sampling removed."""
        raise NotImplementedError(
            "get_rotation_angles removed (JAX retirement). "
            "Use CP-SAT placer for discrete placement decisions."
        )

    def to_discrete(self) -> tuple[NDArray, NDArray]:
        """
        Convert to discrete placement (argmax rotations).

        Returns:
            Tuple of (positions, rotation_indices) where rotation_indices
            are integers 0-3 representing 0°, 90°, 180°, 270°.
        """
        # Helper for returning just clean positions/rotations
        rotation_indices = np.argmax(self.rotation_logits, axis=-1)
        return self.positions, rotation_indices

    @property
    def n_components(self) -> int:
        """Number of components in this state."""
        return self.positions.shape[0]


def sample_rotation(logits: NDArray, key: NDArray, temperature: float = 1.0) -> NDArray:
    """DEPRECATED: JAX Gumbel-Softmax rotation sampling removed.

    Use CP-SAT placer for discrete placement decisions instead.
    """
    raise NotImplementedError(
        "sample_rotation removed (JAX retirement). "
        "Use CP-SAT placer for discrete placement decisions."
    )


def rotation_matrix(angle: float) -> NDArray:
    """
    Create a 2D rotation matrix for the given angle.

    Args:
        angle: Rotation angle in radians.

    Returns:
        (2, 2) rotation matrix.
    """
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    return np.array([[cos_a, -sin_a], [sin_a, cos_a]])


def rotate_points(points: NDArray, angle: float, center: NDArray | None = None) -> NDArray:
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
