from dataclasses import dataclass
from typing import Any

import jax.numpy as jnp
import numpy as np
from flax import struct
from jax.scipy.ndimage import map_coordinates

from temper_placer.losses.base import LossContext, LossFunction
from temper_placer.losses.types import LossResult


@struct.dataclass
class RoutingCongestionLoss(LossFunction):
    """
    Penalizes placing components in areas identified as congested by the router.
    """
    heatmap: jnp.ndarray  # 2D array of congestion per grid cell (normalized)
    origin: jnp.ndarray   # (2,) [x, y] of grid origin in mm
    cell_size: float      # size of grid cell in mm
    grid_size: jnp.ndarray # (2,) [width, height] in cells
    weight: float = 1.0

    @property
    def name(self) -> str:
        return "routing_congestion"

    @classmethod
    def from_file(cls, path: str, weight: float = 1.0) -> "RoutingCongestionLoss":
        import numpy as np
        data = np.load(path)
        return cls(
            heatmap=jnp.array(data["congestion_grid"]),
            origin=jnp.array(data["origin"]),
            cell_size=float(data["cell_size"]),
            grid_size=jnp.array(data["grid_size"]),
            weight=weight,
        )

    def __call__(
        self,
        positions: jnp.ndarray,
        rotations: jnp.ndarray,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: jnp.ndarray | None = None, **kwargs: Any) -> LossResult:
        """
        Calculate congestion penalty.
        """
        # 1. Transform positions to grid coordinates
        grid_pos = (positions - self.origin) / self.cell_size

        # 2. Add batch dimension for N components if needed?
        # grid_pos is (N, 2). map_coordinates expects coords as (rank, N)
        coords = grid_pos.T  # (2, N)

        # 3. Sample heatmap
        congestion_values = map_coordinates(self.heatmap, coords, order=1, mode='nearest')

        # 4. Compute loss
        mean_congestion = jnp.mean(congestion_values)
        loss_val = mean_congestion * self.weight

        return LossResult(
            value=loss_val,
            breakdown={"max_congestion": jnp.max(congestion_values), "mean_congestion": mean_congestion}
        )

@dataclass
class ConflictLocation:
    x: int
    y: int
    layer: int
    nets: list[str]

def compute_congestion_heatmap(
    conflicts: list[ConflictLocation],
    grid_size: tuple[int, int],
    cell_size_mm: float,
    origin: tuple[float, float]
) -> jnp.ndarray:
    """Compute congestion heatmap from conflict locations."""
    width, height = grid_size
    heatmap = np.zeros((width, height), dtype=np.float32)

    for c in conflicts:
        if 0 <= c.x < width and 0 <= c.y < height:
            heatmap[c.x, c.y] += 1.0

    # Normalize
    max_val = np.max(heatmap)
    if max_val > 0:
        heatmap = heatmap / max_val

    return jnp.array(heatmap)
