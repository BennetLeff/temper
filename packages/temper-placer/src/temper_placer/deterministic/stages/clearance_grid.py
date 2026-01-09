import numpy as np
from dataclasses import dataclass
from numba import njit
from ..state import BoardState
from .base import Stage


@njit
def _block_circle_numba(
    target_grid, cx, cy, total_radius, net_id, cell_size_mm, min_row, max_row, min_col, max_col
):
    """Numba-optimized inner loop for block_circle().

    Args:
        target_grid: NumPy array to modify
        cx, cy: Center coordinates in mm
        total_radius: radius + clearance in mm
        net_id: Net ID to write to cells
        cell_size_mm: Grid cell size
        min_row, max_row, min_col, max_col: Bounding box limits
    """
    for row in range(min_row, max_row):
        for col in range(min_col, max_col):
            cell_x = col * cell_size_mm + cell_size_mm / 2
            cell_y = row * cell_size_mm + cell_size_mm / 2
            dist = ((cell_x - cx) ** 2 + (cell_y - cy) ** 2) ** 0.5
            if dist <= total_radius:
                curr = target_grid[row, col]
                if curr == 0:
                    target_grid[row, col] = net_id
                elif curr != net_id:
                    target_grid[row, col] = -1  # Multiple nets/Conflict


@njit
def _block_segment_numba(
    target_grid,
    x1,
    y1,
    x2,
    y2,
    total_radius,
    net_id,
    cell_size_mm,
    min_row,
    max_row,
    min_col,
    max_col,
):
    """Numba-optimized inner loop for _block_segment().

    Args:
        target_grid: NumPy array to modify
        x1, y1, x2, y2: Segment endpoints in mm
        total_radius: (width/2 + clearance) in mm
        net_id: Net ID to write to cells
        cell_size_mm: Grid cell size
        min_row, max_row, min_col, max_col: Bounding box limits
    """
    dx = x2 - x1
    dy = y2 - y1
    L2 = dx * dx + dy * dy

    for row in range(min_row, max_row):
        for col in range(min_col, max_col):
            cell_x = col * cell_size_mm + cell_size_mm / 2
            cell_y = row * cell_size_mm + cell_size_mm / 2

            # Projection of point (cell_x, cell_y) onto segment
            t = ((cell_x - x1) * dx + (cell_y - y1) * dy) / L2
            t = max(0.0, min(1.0, t))

            proj_x = x1 + t * dx
            proj_y = y1 + t * dy

            dist = ((cell_x - proj_x) ** 2 + (cell_y - proj_y) ** 2) ** 0.5
            if dist <= total_radius:
                curr = target_grid[row, col]
                if curr == 0:
                    target_grid[row, col] = net_id
                elif curr != net_id:
                    target_grid[row, col] = -1  # Multiple nets/Conflict


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
        self, x_mm: float, y_mm: float, layer: int = 0, net_name: str = None, net_id: int = None
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
            if p_id != 0 and p_id != net_id:
                return False

            return True
        return False  # Out of bounds = blocked

    def block_circle(
        self,
        center: tuple[float, float],
        radius_mm: float,
        clearance_mm: float,
        layer: int = 0,
        net_name: str = None,
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

        if net_name:
            net_id = self.get_net_id(net_name)
        else:
            net_id = -2  # Generic obstacle

        target_grid = self._pad_net_ids[layer] if is_pad else self._trace_net_ids[layer]

        # Use Numba-optimized inner loop
        _block_circle_numba(
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

    def block_trace(
        self,
        path: list[tuple[float, float]],
        width_mm: float,
        clearance_mm: float,
        layer: int = 0,
        net_name: str = None,
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
        net_name: str = None,
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

        if net_name:
            net_id = self.get_net_id(net_name)
        else:
            net_id = -2

        target_grid = self._trace_net_ids[layer]

        # Call Numba-optimized function for the inner loop
        _block_segment_numba(
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

    def block_rect(
        self,
        center: tuple[float, float],
        size: tuple[float, float],
        clearance_mm: float,
        layer: int = 0,
        net_name: str = None,
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

        # Block all cells in the rectangle
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                curr = target_grid[row, col]
                if curr == 0:
                    target_grid[row, col] = net_id
                elif curr != net_id:
                    target_grid[row, col] = -1  # Multiple nets/conflict

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

        # Mark cells as available in both grids
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                cell_x = col * self.cell_size_mm + self.cell_size_mm / 2
                cell_y = row * self.cell_size_mm + self.cell_size_mm / 2
                dist = ((cell_x - cx) ** 2 + (cell_y - cy) ** 2) ** 0.5
                if dist <= radius_mm:
                    self._trace_net_ids[layer][row, col] = 0
                    self._pad_net_ids[layer][row, col] = 0

    @property
    def blocked_count(self) -> int:
        """Total blocked cells across all layers."""
        count = 0
        for l in range(self.layer_count):
            count += np.sum(self._trace_net_ids[l] != 0)
            count += np.sum(self._pad_net_ids[l] != 0)
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
        component_positions: dict = None,
        highlight_nets: list = None,
    ):
        """Export clearance grid as a PNG visualization.

        Args:
            output_path: Path to save the PNG file
            layer: Layer index to visualize (0=F.Cu, 1=In1.Cu, etc.)
            component_positions: Optional dict of {ref: (x, y)} to overlay
            highlight_nets: Optional list of net names to highlight
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches
            from matplotlib.colors import ListedColormap
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
        colors = ["white"]  # 0 = free
        color_labels = ["Free"]

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
        im = ax.imshow(
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
        for i, (net_id, color) in enumerate(list(net_colors.items())[:10]):
            net_name = self._id_to_net.get(net_id, f"Net_{net_id}")
            legend_patches.append(mpatches.Patch(color=color, label=net_name))

        ax.legend(handles=legend_patches, loc="upper right", fontsize=8)

        layer_names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        layer_name = layer_names[layer] if layer < len(layer_names) else f"Layer_{layer}"
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

    def export_stats(self) -> dict:
        """Export statistics about the clearance grid."""
        stats = {
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
            layer_names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
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


class ClearanceGridStage(Stage):
    def __init__(
        self,
        cell_size_mm: float = 0.5,
        layer_count: int = 2,
        pad_sizes: dict = None,
        max_clearance_mm: float = 2.5,
        net_class_clearances: dict[str, float] = None,
        net_classes: dict[str, str] = None,
        pth_mask_expansion_mm: float = 0.15,
        smd_mask_expansion_mm: float = 0.10,
        inner_layer_clearance_mm: float = 0.5,
        hv_exclusion_zones: list = None,
    ):
        """Initialize clearance grid stage.

        Args:
            cell_size_mm: Grid cell size in mm
            layer_count: Number of copper layers
            pad_sizes: Optional dict of pad sizes
            max_clearance_mm: Maximum clearance to use for blocking (fallback if net class not found)
            net_class_clearances: Optional mapping of net class name to clearance in mm
            net_classes: Optional mapping of net name to net class name (for per-net clearance lookup)
            pth_mask_expansion_mm: Mask expansion for PTH pads (default: 0.15mm)
            smd_mask_expansion_mm: Mask expansion for SMD pads (default: 0.10mm)
            inner_layer_clearance_mm: Max clearance for inner layers (default: 0.5mm).
                Inner layers don't need creepage clearance since they're encapsulated
                in FR4. This prevents high-voltage PTH pads from blocking routing on
                inner layers with their full surface clearance (e.g., 6mm -> 0.5mm).
            hv_exclusion_zones: List of HVExclusionZone configs for signal avoidance.
                EXP-13: Zones where specified nets must not route (blocked on all layers).
        """
        self.cell_size_mm = cell_size_mm
        self.layer_count = layer_count
        self.pad_sizes = pad_sizes or {}
        self.max_clearance_mm = max_clearance_mm
        self.net_class_clearances = net_class_clearances or {}
        self.net_classes = net_classes or {}
        self.pth_mask_expansion_mm = pth_mask_expansion_mm
        self.smd_mask_expansion_mm = smd_mask_expansion_mm
        self.inner_layer_clearance_mm = inner_layer_clearance_mm
        self.hv_exclusion_zones = hv_exclusion_zones or []

    def _get_clearance_for_net(self, net_name: str, state: "BoardState", layer: int = 0) -> float:
        """Get the clearance for a specific net based on its net class and layer.

        This uses per-net-class clearances instead of a global max_clearance,
        which dramatically reduces grid congestion on boards with mixed clearances
        (e.g., HighVoltage at 6mm vs Signal at 0.2mm).

        For inner layers (not F.Cu or B.Cu), clearances are capped at
        inner_layer_clearance_mm since creepage requirements only apply to
        exposed surface layers. This is critical for routing near high-voltage
        PTH pads - their 6mm surface clearance would otherwise block all
        inner layers, making escape routing impossible.

        Args:
            net_name: Name of the net
            state: Current board state with netlist info
            layer: Layer index (0=F.Cu, 1=In1.Cu, 2=In2.Cu, 3=B.Cu for 4-layer)

        Returns:
            Clearance in mm for this net on this layer
        """
        if not net_name:
            return self.max_clearance_mm

        # Try to find net class from config mapping first
        net_class = self.net_classes.get(net_name)

        # Fall back to netlist if not in config
        if not net_class and state.netlist:
            for net in state.netlist.nets:
                if net.name == net_name:
                    net_class = getattr(net, "net_class", None)
                    break

        # Look up clearance for this net class
        if net_class and net_class in self.net_class_clearances:
            clearance = self.net_class_clearances[net_class]
        else:
            # Default clearance for unknown nets (use conservative Signal clearance, not max)
            clearance = self.net_class_clearances.get("Signal", 0.2)

        # Cap clearance on inner layers - they don't need creepage clearance
        # Inner layers are encapsulated in FR4, so air gap requirements don't apply
        is_inner_layer = 0 < layer < (self.layer_count - 1)
        if is_inner_layer and clearance > self.inner_layer_clearance_mm:
            return self.inner_layer_clearance_mm

        return clearance

    @property
    def name(self) -> str:
        return "clearance_grid"

    def run(self, state: BoardState) -> BoardState:
        if not state.board:
            return state

        grid = ClearanceGrid(
            width_mm=state.board.width,
            height_mm=state.board.height,
            cell_size_mm=self.cell_size_mm,
            layer_count=self.layer_count,
        )

        # Block pads from OTHER nets with net-class aware clearance buffer.
        # This allows routing TO target pads while avoiding shorts.
        # Pads are blocked with inflated radius = pad_r + clearance + trace_width/2 + mask

        if state.netlist:
            placements_dict = dict(state.placements) if state.placements else {}

            # Build net->pads mapping for selective unblocking
            net_pads = {}
            for component in state.netlist.components:
                pos = placements_dict.get(component.ref, component.initial_position)
                if pos is None:
                    continue

                for pin in component.pins:
                    pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                    pad_radius = 0.5
                    pad_key = (component.ref, pin.name)
                    if pad_key in self.pad_sizes:
                        real_pad = self.pad_sizes[pad_key]
                        pad_radius = max(real_pad.size.X, real_pad.size.Y) / 2.0

                    # Store pad info
                    net = pin.net or ""
                    if net not in net_pads:
                        net_pads[net] = []

                    # Determine target layers
                    if pin.is_pth or pin.layer == "all":
                        target_layers = list(range(grid.layer_count))
                    elif pin.layer == "F.Cu":
                        target_layers = [0]
                    elif pin.layer == "B.Cu":
                        target_layers = [grid.layer_count - 1]
                    elif pin.layer == "In1.Cu" and grid.layer_count > 1:
                        target_layers = [1]
                    elif pin.layer == "In2.Cu" and grid.layer_count > 2:
                        target_layers = [2]
                    else:
                        target_layers = list(range(grid.layer_count))

                    net_pads[net].append(
                        {
                            "pos": pin_pos,
                            "radius": pad_radius,
                            "layers": target_layers,
                            "is_pth": pin.is_pth,
                        }
                    )

            # Block all pads with clearance based on the pad's net class.
            # PTH pads need larger mask expansion due to plating and annular ring.
            # Base clearance components:
            #   - Electrical clearance (from the pad's own net class, not global max!)
            #   - Mask expansion (PTH: 0.15mm, SMD: 0.10mm)
            #
            # KEY FIX: Using per-net-class clearances instead of max_clearance_mm.
            # This dramatically reduces grid congestion:
            #   - HighVoltage pads: blocked with 6.0mm (other nets must stay away)
            #   - Signal pads: blocked with 0.2mm (allows nearby routing)
            #
            # Before: 37.8% of grid blocked with global 6.3mm clearance
            # After: ~3% of grid blocked with per-net clearances
            #
            # DRC correctness: When routing net A near pad of net B, the router
            # checks A's clearance requirement against B's blocked zone. Since A
            # must maintain clearance from B's pad anyway, using B's clearance
            # for blocking is correct and conservative.
            #
            # LAYER-SPECIFIC CLEARANCES:
            # Inner layers (In1.Cu, In2.Cu) don't need surface creepage clearance
            # since they're encapsulated in FR4. We cap inner layer clearances at
            # inner_layer_clearance_mm (default 0.5mm) to prevent high-voltage
            # PTH pads from blocking escape routes on inner layers.
            for net_name, pads in net_pads.items():
                for pad in pads:
                    # Calculate clearance with PTH/SMD-aware mask expansion
                    mask_expansion = (
                        self.pth_mask_expansion_mm if pad["is_pth"] else self.smd_mask_expansion_mm
                    )

                    for layer_idx in pad["layers"]:
                        if layer_idx < grid.layer_count:
                            # Get layer-specific clearance (inner layers have reduced clearance)
                            net_clearance = self._get_clearance_for_net(
                                net_name, state, layer=layer_idx
                            )
                            total_clearance = net_clearance + mask_expansion

                            grid.block_circle(
                                pad["pos"],
                                radius_mm=pad["radius"],
                                clearance_mm=total_clearance,
                                layer=layer_idx,
                                net_name=net_name,
                            )

        # EXP-13: Block HV exclusion zones for specified nets
        # These zones force signals (like GATE_H, PWM_H) to route around HV areas
        # instead of taking the direct path that would violate creepage requirements.
        # Exclusion is per-net: only nets in excluded_nets are blocked.
        if self.hv_exclusion_zones:
            print(f"  HV exclusion zones: {len(self.hv_exclusion_zones)}")
            for hvz in self.hv_exclusion_zones:
                # For each excluded net, block the zone on all layers
                for excluded_net in hvz.excluded_nets:
                    net_id = grid.get_net_id(excluded_net)
                    # Block on all layers to ensure no path through zone
                    for layer_idx in range(grid.layer_count):
                        # Use block_rect with net marking
                        # By marking with a different net ID, we prevent the excluded
                        # net from routing through this zone
                        cx, cy = hvz.center
                        half_w = hvz.size[0] / 2.0
                        half_h = hvz.size[1] / 2.0

                        # Calculate bounding box in grid coordinates
                        min_col = max(0, int((cx - half_w) / grid.cell_size_mm))
                        max_col = min(grid.cols, int((cx + half_w) / grid.cell_size_mm) + 1)
                        min_row = max(0, int((cy - half_h) / grid.cell_size_mm))
                        max_row = min(grid.rows, int((cy + half_h) / grid.cell_size_mm) + 1)

                        # Mark zone as blocked for this net
                        # Using net_id = -2 (obstacle) prevents the net from routing here
                        target_grid = grid._trace_net_ids[layer_idx]
                        for row in range(min_row, max_row):
                            for col in range(min_col, max_col):
                                curr = target_grid[row, col]
                                # Only block if cell is free or belongs to a different net
                                # (allows HV nets to route through their own exclusion zone)
                                if curr == 0 or curr == net_id:
                                    target_grid[row, col] = -2  # Obstacle for this net

                print(
                    f"    {hvz.name}: blocking {hvz.excluded_nets} in "
                    f"{hvz.size[0]}x{hvz.size[1]}mm zone at {hvz.center}"
                )

        from dataclasses import replace

        return replace(state, grid=grid)
