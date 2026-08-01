from dataclasses import dataclass
from typing import Any

import numpy as np
import temper_geometry as _tg

from ._grid_hv import _STANDARD_LAYER_NAMES


@dataclass
class ClearanceGrid:
    """Multi-layer 2D grid tracking blocked and available cells for routing."""

    width_mm: float
    height_mm: float
    cell_size_mm: float
    layer_count: int = 2

    def __post_init__(self):
        self.cols = int(self.width_mm / self.cell_size_mm)
        self.rows = int(self.height_mm / self.cell_size_mm)
        # 0 = free, -1 = multiple nets (restricted), -2 = obstacle, >0 = net ID
        self._trace_net_ids = [
            np.zeros((self.rows, self.cols), dtype=np.int32) for _ in range(self.layer_count)
        ]
        self._pad_net_ids = [
            np.zeros((self.rows, self.cols), dtype=np.int32) for _ in range(self.layer_count)
        ]
        # Map net names to IDs
        self._net_to_id = {}
        self._id_to_net = {}
        self._next_net_id = 1
        # Cache for occupancy_grid property (lazy init)
        self._occupancy_grid_cache = None
        self._bitmap_cache = None
        self._bitmap_stride_cache = None

    @property
    def occupancy_grid(self) -> np.ndarray:
        """Get 3D occupancy grid view (layers, rows, cols) for Cython A*.

        Combines trace and pad net IDs into single 3D array.
        This is cached and recomputed if grid is modified.

        Returns:
            np.ndarray of shape (layer_count, rows, cols) with dtype int32
        """
        # For now, just stack trace arrays (pads are less important for routing)
        # TODO: properly merge trace and pad net IDs
        return np.stack(self._trace_net_ids, axis=0)

    @property
    def occupancy_bitmap(self) -> np.ndarray:
        if self._bitmap_cache is not None:
            return self._bitmap_cache
        cols = self.cols
        stride = (cols + 63) // 64
        bitmap = np.zeros((self.layer_count, self.rows, stride), dtype=np.uint64)
        for layer in range(self.layer_count):
            trace = self._trace_net_ids[layer]
            pad = self._pad_net_ids[layer]
            # Rasterised in temper-geometry (grid_raster.rs) with the exact
            # bit-layout of the former pure-Python loop.
            words = _tg.occupancy_bitmap_row_py(trace, pad, self.rows, self.cols, stride)
            bitmap[layer] = np.asarray(words, dtype=np.uint64).reshape((self.rows, stride))
        self._bitmap_cache = bitmap
        self._bitmap_stride_cache = stride
        return bitmap

    @property
    def bitmap_row_stride(self) -> int:
        if self._bitmap_stride_cache is None:
            _ = self.occupancy_bitmap
        return self._bitmap_stride_cache

    def _invalidate_cache(self) -> None:
        self._occupancy_grid_cache = None
        self._bitmap_cache = None
        self._bitmap_stride_cache = None

    def get_net_id(self, net_name: str) -> int:
        """Get or create unique integer ID for a net name."""
        if not net_name:
            return 0
        if net_name not in self._net_to_id:
            self._net_to_id[net_name] = self._next_net_id
            self._id_to_net[self._next_net_id] = net_name
            self._next_net_id += 1
        return self._net_to_id[net_name]

    def _mm_to_cell(self, x_mm: float, y_mm: float) -> tuple[int, int]:
        """Convert mm coordinates to grid cell indices."""
        col = int(x_mm / self.cell_size_mm)
        row = int(y_mm / self.cell_size_mm)
        return (row, col)

    def is_available(
        self,
        x_mm: float,
        y_mm: float,
        layer: int = 0,
        net_name: str | None = None,
        net_id: int | None = None,
    ) -> bool:
        """Check if a position is available for routing on specified layer."""
        if layer < 0 or layer >= self.layer_count:
            return False
        row, col = self._mm_to_cell(x_mm, y_mm)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            if net_id is None and net_name:
                net_id = self.get_net_id(net_name)

            # Check traces
            t_id = self._trace_net_ids[layer][row, col]
            if t_id != 0 and t_id != net_id:
                return False

            # Check pads
            p_id = self._pad_net_ids[layer][row, col]
            return not (p_id != 0 and p_id != net_id)
        return False  # Out of bounds = blocked

    def block_circle(
        self,
        center: tuple[float, float],
        radius_mm: float,
        clearance_mm: float,
        layer: int = 0,
        net_name: str | None = None,
        is_pad: bool = True,
    ):
        """Block cells within radius + clearance of center on specified layer."""
        if layer < 0 or layer >= self.layer_count:
            return
        total_radius = radius_mm + clearance_mm
        cx, cy = center

        # Calculate bounding box in grid coordinates
        min_col = max(0, int((cx - total_radius) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + total_radius) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - total_radius) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + total_radius) / self.cell_size_mm) + 1)

        net_id = self.get_net_id(net_name) if net_name else -2

        target_grid = self._pad_net_ids[layer] if is_pad else self._trace_net_ids[layer]

        # Rasterise in temper-geometry (grid_raster.rs) with the exact f64
        # operation order of the former JIT kernel (libm pow for **2 / **0.5).
        _tg.block_circle_into_grid_py(
            target_grid,
            cx,
            cy,
            total_radius,
            net_id,
            self.cell_size_mm,
            min_row,
            max_row,
            min_col,
            max_col,
        )
        self._invalidate_cache()

    def block_trace(
        self,
        path: list[tuple[float, float]],
        width_mm: float,
        clearance_mm: float,
        layer: int = 0,
        net_name: str | None = None,
    ):
        """Block cells along a trace path with given width and clearance on specified layer."""
        if not path:
            return

        # Treat as a series of connected circles and rectangles
        for i in range(len(path)):
            # Block circle at current point
            self.block_circle(
                path[i], width_mm / 2.0, clearance_mm, layer, net_name=net_name, is_pad=False
            )

            if i < len(path) - 1:
                # Block segment between path[i] and path[i+1]
                self._block_segment(
                    path[i], path[i + 1], width_mm, clearance_mm, layer, net_name=net_name
                )

    def _block_segment(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        width_mm: float,
        clearance_mm: float,
        layer: int = 0,
        net_name: str | None = None,
    ):
        """Block cells along a straight segment on specified layer."""
        if layer < 0 or layer >= self.layer_count:
            return
        total_radius = width_mm / 2.0 + clearance_mm
        x1, y1 = start
        x2, y2 = end

        # Calculate segment bounding box
        min_x = min(x1, x2) - total_radius
        max_x = max(x1, x2) + total_radius
        min_y = min(y1, y2) - total_radius
        max_y = max(y1, y2) + total_radius

        min_col = max(0, int(min_x / self.cell_size_mm))
        max_col = min(self.cols, int(max_x / self.cell_size_mm) + 1)
        min_row = max(0, int(min_y / self.cell_size_mm))
        max_row = min(self.rows, int(max_y / self.cell_size_mm) + 1)

        # Segment vector
        dx = x2 - x1
        dy = y2 - y1
        L2 = dx * dx + dy * dy

        if L2 == 0:
            return

        net_id = self.get_net_id(net_name) if net_name else -2

        target_grid = self._trace_net_ids[layer]

        # Rasterise in temper-geometry (grid_raster.rs) with the exact f64
        # operation order of the former JIT kernel.
        _tg.block_segment_into_grid_py(
            target_grid,
            x1,
            y1,
            x2,
            y2,
            total_radius,
            net_id,
            self.cell_size_mm,
            min_row,
            max_row,
            min_col,
            max_col,
        )
        self._invalidate_cache()

    def block_rect(
        self,
        center: tuple[float, float],
        size: tuple[float, float],
        clearance_mm: float,
        layer: int = 0,
        net_name: str | None = None,
        is_obstacle: bool = True,
    ):
        """Block a rectangular region on specified layer.

        EXP-13: Used for HV exclusion zones where signals must avoid.

        Args:
            center: (x, y) center position in mm
            size: (width, height) in mm
            clearance_mm: Additional clearance around the rectangle
            layer: Layer index
            net_name: Optional net name (if blocking for a specific net)
            is_obstacle: If True, mark as obstacle (-2); if False, mark as net
        """
        if layer < 0 or layer >= self.layer_count:
            return

        cx, cy = center
        half_w, half_h = size[0] / 2.0 + clearance_mm, size[1] / 2.0 + clearance_mm

        # Calculate bounding box in grid coordinates
        min_col = max(0, int((cx - half_w) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + half_w) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - half_h) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + half_h) / self.cell_size_mm) + 1)

        if is_obstacle:
            net_id = -2  # Generic obstacle
        elif net_name:
            net_id = self.get_net_id(net_name)
        else:
            net_id = -2

        target_grid = self._trace_net_ids[layer]

        # Rasterise in temper-geometry (grid_raster.rs) — integer-only
        # merge over the bbox, bit-exact by construction.
        _tg.block_rect_into_grid_py(target_grid, net_id, min_row, max_row, min_col, max_col)
        self._invalidate_cache()

    def unblock_circle(self, center: tuple[float, float], radius_mm: float, layer: int = 0):
        """Unblock cells within radius of center on specified layer."""
        if layer < 0 or layer >= self.layer_count:
            return
        cx, cy = center

        # Calculate bounding box in grid coordinates
        min_col = max(0, int((cx - radius_mm) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + radius_mm) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - radius_mm) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + radius_mm) / self.cell_size_mm) + 1)

        # Clear the circle in both grids (temper-geometry grid_raster.rs, same
        # per-cell distance semantics as the former pure-Python loop).
        for grid in (self._trace_net_ids[layer], self._pad_net_ids[layer]):
            _tg.clear_circle_from_grid_py(
                grid, cx, cy, radius_mm, self.cell_size_mm, min_row, max_row, min_col, max_col
            )
        self._invalidate_cache()

    @property
    def blocked_count(self) -> int:
        """Total blocked cells across all layers."""
        count = 0
        for layer in range(self.layer_count):
            count += np.sum(self._trace_net_ids[layer] != 0)
            count += np.sum(self._pad_net_ids[layer] != 0)
        return int(count)

    def blocked_count_on_layer(self, layer: int) -> int:
        """Blocked cells on specific layer."""
        if layer < 0 or layer >= self.layer_count:
            return 0
        return int(np.sum(self._trace_net_ids[layer] != 0) + np.sum(self._pad_net_ids[layer] != 0))

    @property
    def blocked_cells(self) -> frozenset:
        """Return frozenset of blocked (row, col, layer) tuples across all layers."""
        blocked = []
        for layer_idx in range(self.layer_count):
            rows, cols = np.where(
                (self._trace_net_ids[layer_idx] != 0) | (self._pad_net_ids[layer_idx] != 0)
            )
            blocked.extend([(r, c, layer_idx) for r, c in zip(rows.tolist(), cols.tolist())])
        return frozenset(blocked)

    def blocked_cells_on_layer(self, layer: int) -> frozenset:
        """Return frozenset of blocked (row, col) tuples on specific layer."""
        if layer < 0 or layer >= self.layer_count:
            return frozenset()
        rows, cols = np.where((self._trace_net_ids[layer] != 0) | (self._pad_net_ids[layer] != 0))
        return frozenset(zip(rows.tolist(), cols.tolist()))

    def export_visualization(
        self,
        output_path: str,
        layer: int = 0,
        component_positions: dict | None = None,
        _highlight_nets: list | None = None,
    ):
        """Export clearance grid as a PNG visualization.

        Args:
            output_path: Path to save the PNG file
            layer: Layer index to visualize (0=F.Cu, 1=In1.Cu, etc.)
            component_positions: Optional dict of {ref: (x, y)} to overlay
            highlight_nets: Optional list of net names to highlight
        """
        try:
            import matplotlib.patches as mpatches
            import matplotlib.pyplot as plt
        except ImportError:
            print("WARNING: matplotlib not available, skipping visualization")
            return

        if layer < 0 or layer >= self.layer_count:
            return

        # Combine pad and trace grids
        combined = self._pad_net_ids[layer].copy()
        trace_mask = self._trace_net_ids[layer] != 0
        combined[trace_mask] = self._trace_net_ids[layer][trace_mask]

        # Create figure
        fig, ax = plt.subplots(figsize=(16, 12))

        # Create color map: 0=white (free), -1=red (conflict), -2=gray (obstacle), >0=colors per net
        unique_ids = np.unique(combined)
        n_nets = len([i for i in unique_ids if i > 0])

        # Build colormap

        # Generate distinct colors for nets
        if n_nets > 0:
            cmap = plt.cm.get_cmap("tab20", max(20, n_nets))
            net_colors = {
                net_id: cmap(i % 20)
                for i, net_id in enumerate(sorted([i for i in unique_ids if i > 0]))
            }
        else:
            net_colors = {}

        # Create display array
        display = np.zeros_like(combined, dtype=float)
        for row in range(self.rows):
            for col in range(self.cols):
                val = combined[row, col]
                if val == 0:
                    display[row, col] = 0  # Free
                elif val == -1:
                    display[row, col] = 1  # Conflict
                elif val == -2:
                    display[row, col] = 2  # Obstacle
                elif val > 0:
                    display[row, col] = 3 + list(net_colors.keys()).index(val)

        # Plot
        ax.imshow(
            display, origin="lower", aspect="equal", extent=[0, self.width_mm, 0, self.height_mm]
        )

        # Add component positions
        if component_positions:
            for ref, (x, y) in component_positions.items():
                ax.plot(x, y, "ko", markersize=3)
                ax.annotate(ref, (x, y), fontsize=6, ha="center", va="bottom")

        # Create legend
        legend_patches = [
            mpatches.Patch(color="white", label="Free"),
            mpatches.Patch(color="red", label="Conflict"),
            mpatches.Patch(color="gray", label="Obstacle"),
        ]

        # Add net labels (first 10)
        for _i, (net_id, color) in enumerate(list(net_colors.items())[:10]):
            net_name = self._id_to_net.get(net_id, f"Net_{net_id}")
            legend_patches.append(mpatches.Patch(color=color, label=net_name))

        ax.legend(handles=legend_patches, loc="upper right", fontsize=8)

        layer_name = (
            _STANDARD_LAYER_NAMES[layer] if layer < len(_STANDARD_LAYER_NAMES) else f"Layer_{layer}"
        )
        ax.set_title(
            f"Clearance Grid - {layer_name}\n"
            f"Grid: {self.cols}x{self.rows} cells, Cell size: {self.cell_size_mm}mm\n"
            f"Blocked: {self.blocked_count_on_layer(layer)} cells"
        )
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")

        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        plt.close()
        print(f"Saved clearance grid visualization to {output_path}")

    def export_stats(self) -> dict[str, Any]:
        """Export statistics about the clearance grid."""
        stats: dict[str, Any] = {
            "dimensions": {
                "width_mm": self.width_mm,
                "height_mm": self.height_mm,
                "cell_size_mm": self.cell_size_mm,
                "rows": self.rows,
                "cols": self.cols,
                "total_cells": self.rows * self.cols,
            },
            "layer_count": self.layer_count,
            "nets_registered": len(self._net_to_id),
            "net_names": list(self._net_to_id.keys()),
            "blocking": {},
        }

        for layer in range(self.layer_count):
            layer_names = list(_STANDARD_LAYER_NAMES)
            layer_name = layer_names[layer] if layer < len(layer_names) else f"Layer_{layer}"

            pad_blocked = int(np.sum(self._pad_net_ids[layer] != 0))
            trace_blocked = int(np.sum(self._trace_net_ids[layer] != 0))
            total = self.rows * self.cols

            stats["blocking"][layer_name] = {
                "pad_blocked_cells": pad_blocked,
                "trace_blocked_cells": trace_blocked,
                "total_blocked_cells": pad_blocked + trace_blocked,
                "blocked_percentage": 100.0 * (pad_blocked + trace_blocked) / total,
            }

        return stats
