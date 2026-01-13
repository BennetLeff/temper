"""
Enhanced routing congestion loss with spatial spreading and criticality weighting.

Improvements over basic RoutingCongestionLoss:
1. Gaussian blur to spread congestion influence spatially
2. Net criticality weighting (power nets more important than signals)
3. Zone boundary avoidance integrated into heatmap
4. Multi-scale congestion (local + global)

This provides better guidance to the placement optimizer by creating
smooth gradients that push components away from congested regions.
"""

from typing import Any

import jax.numpy as jnp
import numpy as np
from flax import struct
from scipy.ndimage import gaussian_filter

from temper_placer.losses.base import LossContext, LossFunction
from temper_placer.losses.types import LossResult


def compute_enhanced_congestion_heatmap(
    conflicts: list[dict[str, Any]],
    grid_size: tuple[int, int],
    cell_size_mm: float,
    blur_sigma: float = 2.0,
    net_criticality: dict[str, float] | None = None,
) -> jnp.ndarray:
    """
    Compute enhanced congestion heatmap with Gaussian blur and criticality weighting.

    Process:
    1. Rasterize conflicts to grid
    2. Weight by net criticality (power > gate drive > signal)
    3. Apply Gaussian blur for spatial spreading
    4. Normalize to [0, 1]

    Args:
        conflicts: List of conflict dictionaries with keys:
            - 'x', 'y': Grid coordinates
            - 'layer': Layer index
            - 'nets': List of conflicting net names
        grid_size: (width_cells, height_cells)
        cell_size_mm: Grid resolution
        blur_sigma: Gaussian blur sigma in grid cells (default 2.0 = ~0.4mm @ 0.2mm/cell)
        net_criticality: Map from net name to criticality weight (1.0-10.0)

    Returns:
        (width, height) congestion heatmap normalized to [0, 1]
    """
    width, height = grid_size
    heatmap = np.zeros((width, height), dtype=np.float32)

    # Default criticality weights if not provided
    if net_criticality is None:
        net_criticality = {}

    # Add conflicts to heatmap
    for conflict in conflicts:
        x = conflict.get("x", -1)
        y = conflict.get("y", -1)
        nets = conflict.get("nets", [])

        if x < 0 or x >= width or y < 0 or y >= height:
            continue

        # Compute weighted cost based on net criticality
        conflict_weight = 1.0
        for net_name in nets:
            # Get criticality (default 1.0 for unknown nets)
            crit = net_criticality.get(net_name, 1.0)
            conflict_weight = max(conflict_weight, crit)

        heatmap[x, y] += conflict_weight

    # Apply Gaussian blur for spatial spreading
    # This creates a "repulsion field" around congested areas
    if blur_sigma > 0:
        heatmap = gaussian_filter(heatmap, sigma=blur_sigma, mode="constant", cval=0.0)

    # Normalize to [0, 1]
    max_val = np.max(heatmap)
    if max_val > 1e-6:
        heatmap = heatmap / max_val

    return jnp.array(heatmap)


def infer_net_criticality(netlist: Any) -> dict[str, float]:
    """
    Infer net criticality from net names and types.

    Criticality hierarchy:
    - Power/Ground: 5.0 (most critical)
    - Gate Drive: 4.0
    - High Current: 3.0
    - Analog/Sensitive: 2.0
    - Digital/Signal: 1.0 (default)

    Args:
        netlist: Netlist with nets

    Returns:
        Map from net name to criticality weight
    """
    criticality = {}

    # Define patterns and weights
    patterns = [
        # (pattern, weight)
        (["GND", "VCC", "VDD", "VSS", "PGND", "CGND", "+"], 5.0),  # Power
        (["GATE", "DRIVE"], 4.0),  # Gate drive
        (["DC_BUS", "AC_", "SW_NODE"], 3.0),  # High current
        (["SENSE", "ANALOG", "ADC", "DAC"], 2.0),  # Analog
    ]

    # Get nets from netlist
    if hasattr(netlist, "nets"):
        nets = [n.name for n in netlist.nets]
    else:
        # Fallback: empty dict
        return criticality

    for net_name in nets:
        # Default criticality
        weight = 1.0

        # Check patterns
        net_upper = net_name.upper()
        for pattern_list, pattern_weight in patterns:
            if any(p in net_upper for p in pattern_list):
                weight = pattern_weight
                break

        criticality[net_name] = weight

    return criticality


@struct.dataclass
class EnhancedCongestionLoss(LossFunction):
    """
    Enhanced congestion loss with spatial spreading and criticality weighting.

    Attributes:
        heatmap: (W, H) congestion heatmap with Gaussian blur applied
        origin: (2,) board origin [x, y] in mm
        cell_size: Grid cell size in mm
        grid_size: (2,) grid dimensions [width, height] in cells
        weight: Loss weight multiplier
        power: Exponent for non-linear penalty (default 1.0 = linear)
    """

    heatmap: jnp.ndarray
    origin: jnp.ndarray
    cell_size: float
    grid_size: jnp.ndarray
    weight: float = 1.0
    power: float = 1.0  # Can use 2.0 for quadratic penalty

    @property
    def name(self) -> str:
        return "enhanced_congestion"

    @classmethod
    def from_conflicts(
        cls,
        conflicts: list[dict[str, Any]],
        grid_size: tuple[int, int],
        cell_size_mm: float,
        origin: tuple[float, float],
        netlist: Any = None,
        weight: float = 50.0,
        blur_sigma: float = 2.0,
        power: float = 1.0,
    ) -> "EnhancedCongestionLoss":
        """
        Create from routing conflicts with automatic criticality inference.

        Args:
            conflicts: Router conflict locations
            grid_size: Grid dimensions (width, height) in cells
            cell_size_mm: Cell size in mm
            origin: Board origin (x, y) in mm
            netlist: Optional netlist for criticality inference
            weight: Loss weight
            blur_sigma: Gaussian blur sigma in grid cells
            power: Penalty exponent (1.0 = linear, 2.0 = quadratic)

        Returns:
            EnhancedCongestionLoss instance
        """
        # Infer net criticality
        net_criticality = infer_net_criticality(netlist) if netlist is not None else None

        # Compute heatmap
        heatmap = compute_enhanced_congestion_heatmap(
            conflicts,
            grid_size,
            cell_size_mm,
            blur_sigma=blur_sigma,
            net_criticality=net_criticality,
        )

        return cls(
            heatmap=heatmap,
            origin=jnp.array(origin),
            cell_size=cell_size_mm,
            grid_size=jnp.array(grid_size),
            weight=weight,
            power=power,
        )

    @classmethod
    def from_file(
        cls, path: str, weight: float = 50.0, power: float = 1.0
    ) -> "EnhancedCongestionLoss":
        """Load from saved .npz file."""
        data = np.load(path)
        return cls(
            heatmap=jnp.array(data["congestion_grid"]),
            origin=jnp.array(data["origin"]),
            cell_size=float(data["cell_size"]),
            grid_size=jnp.array(data["grid_size"]),
            weight=weight,
            power=power,
        )

    def __call__(
        self,
        positions: jnp.ndarray,
        rotations: jnp.ndarray,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: jnp.ndarray | None = None,
        **kwargs: Any,
    ) -> LossResult:
        """
        Calculate congestion penalty for component positions.

        Uses bilinear interpolation to sample heatmap at component positions,
        then applies non-linear penalty if power != 1.0.

        Args:
            positions: (N, 2) component positions in board coordinates
            rotations: (N, 4) rotation matrices (unused)
            context: Loss context
            epoch: Current epoch (unused)
            total_epochs: Total epochs (unused)
            net_virtual_nodes: Virtual nodes (unused)
            **kwargs: Additional args

        Returns:
            LossResult with congestion penalty
        """
        from jax.scipy.ndimage import map_coordinates

        # Transform positions to grid coordinates
        grid_pos = (positions - self.origin) / self.cell_size

        # Transpose for map_coordinates: expects sequence of [x_coords, y_coords]
        x_coords = grid_pos[:, 0]
        y_coords = grid_pos[:, 1]

        # Sample heatmap using bilinear interpolation
        congestion_values = map_coordinates(
            self.heatmap,
            [x_coords, y_coords],
            order=1,
            mode="nearest",
        )

        # Apply non-linear penalty if power != 1.0
        if self.power != 1.0:
            congestion_values = jnp.power(congestion_values, self.power)

        # Compute loss metrics
        mean_congestion = jnp.mean(congestion_values)
        max_congestion = jnp.max(congestion_values)
        loss_val = mean_congestion * self.weight

        return LossResult(
            value=loss_val,
            breakdown={
                "max_congestion": max_congestion,
                "mean_congestion": mean_congestion,
                "p95_congestion": jnp.percentile(congestion_values, 95),
            },
        )
