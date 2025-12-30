from typing import Any
import jax.numpy as jnp
from jax.scipy.ndimage import map_coordinates
from flax import struct

from temper_placer.losses.base import LossFunction, LossContext
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
        net_virtual_nodes: jnp.ndarray | None = None,
    ) -> LossResult:
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
