"""
PlacementState: Core state representation for PCB placement optimization.

This module defines the central state object that holds component positions
and rotation parameters during optimization. The state is designed to be
JAX-compatible for automatic differentiation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PlacementState:
    """
    Standard NumPy-based state holding component positions and rotation logits.

    Attributes:
        positions: (N, 2) array of component center (x, y) positions in mm.
        rotation_logits: (N, 4) array of rotation preference logits.
            Index 0=0°, 1=90°, 2=180°, 3=270°.
    """

    positions: np.ndarray  # (N, 2) float32
    rotation_logits: np.ndarray  # (N, 4) float32
    net_virtual_nodes: np.ndarray | None = None  # (M, 2) float32, optional

    @classmethod
    def from_positions(
        cls,
        positions: np.ndarray,
        rotation_logits: np.ndarray | None = None,
        net_virtual_nodes: np.ndarray | None = None,
    ) -> PlacementState:
        """
        Create a PlacementState from positions.
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
    def from_netlist_and_board(
        cls,
        netlist: "Netlist",
        board: "Board",
    ) -> PlacementState:
        """
        Create a PlacementState from a Netlist and Board.
        """
        n_components = netlist.n_components
        
        # Extract initial positions and rotations
        positions_list = []
        rotation_logits_list = []
        
        for comp in netlist.components:
            # Position
            if comp.initial_position:
                positions_list.append(list(comp.initial_position))
            else:
                positions_list.append([board.width / 2.0, board.height / 2.0])
                
            # Rotation
            logits = [0.0, 0.0, 0.0, 0.0]
            if comp.initial_rotation is not None:
                idx = comp.initial_rotation % 4
                logits[idx] = 10.0
            rotation_logits_list.append(logits)
            
        positions = np.array(positions_list, dtype=np.float32)
        rotation_logits = np.array(rotation_logits_list, dtype=np.float32)
        
        # Initialize virtual nodes for nets
        n_nets = netlist.n_nets
        net_virtual_nodes = None
        if n_nets > 0:
            net_virtual_nodes = np.full((n_nets, 2), 
                                       np.array([board.width / 2.0, board.height / 2.0]), 
                                       dtype=np.float32)
            
        return cls(
            positions=positions,
            rotation_logits=rotation_logits,
            net_virtual_nodes=net_virtual_nodes,
        )

    def to_discrete(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Convert to discrete placement (argmax rotations).

        Returns:
            Tuple of (positions, rotation_indices)
        """
        rotation_indices = np.argmax(self.rotation_logits, axis=-1)
        return self.positions, rotation_indices

    @property
    def n_components(self) -> int:
        """Number of components in this state."""
        return self.positions.shape[0]


def rotation_matrix(angle: float) -> np.ndarray:
    """
    Create a 2D rotation matrix for the given angle.
    """
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    return np.array([[cos_a, -sin_a], [sin_a, cos_a]])


def rotate_points(points: np.ndarray, angle: float, center: np.ndarray | None = None) -> np.ndarray:
    """
    Rotate points around a center.
    """
    if center is not None:
        points = points - center
    rotated = points @ rotation_matrix(angle).T
    if center is not None:
        rotated = rotated + center
    return rotated
