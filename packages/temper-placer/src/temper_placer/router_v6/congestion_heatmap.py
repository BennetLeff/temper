"""
Congestion heatmap for placer-router feedback.

Extracts routing difficulty from MazeRouter to inform placement optimization.

Part of temper-gzur.1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass  # MazeRouter was deleted; congestion_heatmap uses duck-typed router objects


@dataclass
class CongestionHeatmap:
    """2D congestion map from routing analysis.
    
    Provides query interface for placement optimization:
    - High congestion areas should repel components
    - Enables RoutingCongestionLoss to steer placement
    """
    
    grid: np.ndarray  # 2D float array, values 0-1 (normalized congestion)
    cell_size: float  # mm per grid cell
    origin: tuple[float, float]  # world coordinates of grid origin
    
    @classmethod
    def from_router(cls, router: "MazeRouter") -> "CongestionHeatmap":
        """Build heatmap from router's congestion data.
        
        Combines:
        - present_congestion: current net overlap counts
        - history_cost: accumulated routing difficulty
        - conflict_locations: explicit conflict points
        
        Args:
            router: MazeRouter with routing results
            
        Returns:
            Normalized congestion heatmap
        """
        # Aggregate congestion across layers (max per cell)
        congestion_3d = router.present_congestion
        congestion_2d = np.max(congestion_3d, axis=2)
        
        # Add contribution from history costs (routing difficulty)
        history_3d = router.history_cost
        history_2d = np.max(history_3d, axis=2) - 1.0  # Base cost is 1.0
        
        # Combine (weighted sum)
        combined = congestion_2d + 0.5 * history_2d
        
        # Boost explicit conflict locations
        conflict_locs = router.get_conflict_locations()
        for loc in conflict_locs:
            gx = int((loc["world_x"] - router.origin[0]) / router.cell_size)
            gy = int((loc["world_y"] - router.origin[1]) / router.cell_size)
            if 0 <= gx < combined.shape[0] and 0 <= gy < combined.shape[1]:
                combined[gx, gy] += len(loc["nets"])  # More nets = worse
        
        # Normalize to 0-1
        max_val = np.max(combined)
        if max_val > 0:
            normalized = combined / max_val
        else:
            normalized = combined
        
        return cls(
            grid=normalized.astype(np.float32),
            cell_size=router.cell_size,
            origin=router.origin,
        )
    
    def get_congestion_at(self, x: float, y: float) -> float:
        """Query congestion at world coordinate.
        
        Args:
            x, y: World coordinates in mm
            
        Returns:
            Congestion score 0-1 (0 = free, 1 = highly congested)
        """
        gx = int((x - self.origin[0]) / self.cell_size)
        gy = int((y - self.origin[1]) / self.cell_size)
        
        # Clamp to grid bounds
        gx = max(0, min(gx, self.grid.shape[0] - 1))
        gy = max(0, min(gy, self.grid.shape[1] - 1))
        
        return float(self.grid[gx, gy])
    
    def get_total_congestion(self) -> float:
        """Sum of all congestion values."""
        return float(np.sum(self.grid))
    
    def get_hotspots(self, threshold: float = 0.5, max_count: int = 10) -> list[tuple[float, float, float]]:
        """Find high-congestion locations.
        
        Args:
            threshold: Minimum congestion to consider a hotspot
            max_count: Maximum hotspots to return
            
        Returns:
            List of (x, y, congestion) tuples in world coordinates
        """
        hotspots = []
        
        # Find cells above threshold
        for gx in range(self.grid.shape[0]):
            for gy in range(self.grid.shape[1]):
                val = self.grid[gx, gy]
                if val >= threshold:
                    world_x = gx * self.cell_size + self.origin[0]
                    world_y = gy * self.cell_size + self.origin[1]
                    hotspots.append((world_x, world_y, val))
        
        # Sort by congestion descending
        hotspots.sort(key=lambda h: h[2], reverse=True)
        
        return hotspots[:max_count]
