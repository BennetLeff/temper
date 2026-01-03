import numpy as np
import pytest
from unittest.mock import Mock, MagicMock
from temper_placer.routing.maze_router import MazeRouter, GridCell


class MockComponent:
    def __init__(self, bounds=(1.0, 1.0), pins=None):
        self.bounds = bounds
        self.pins = pins or []
        self.initial_rotation = 0
        self.initial_side = 0


class MockPin:
    def __init__(self, position=(0, 0), net="NET1", width=1.0, height=1.0, shape="smd"):
        self.position = position
        self.net = net
        self.width = width
        self.height = height
        self.shape = shape

    def absolute_position(self, comp_pos, rotation_angle, side):
        import math

        rot_rad = rotation_angle
        cx, cy = comp_pos
        px, py = self.position

        cos_r, sin_r = math.cos(rot_rad), math.sin(rot_rad)
        rx = px * cos_r - py * sin_r
        ry = px * sin_r + py * cos_r

        if side == 1:
            rx = -rx
            ry = -ry

        return (cx + rx, cy + ry)


class TestVectorizedBlocking:
    def test_block_components_vectorized_equals_loop(self):
        n_comps = 5
        components = [MockComponent(bounds=(2.0, 2.0)) for _ in range(n_comps)]
        positions = np.array(
            [[10.0 + i * 5.0, 20.0 + i * 3.0] for i in range(n_comps)], dtype=np.float32
        )

        router1 = MazeRouter(
            grid_size=(100, 100), cell_size_mm=1.0, num_layers=2, origin=(0.0, 0.0)
        )
        router1._component_positions = positions

        pos_array = np.asarray(positions)
        cx = pos_array[:, 0]
        cy = pos_array[:, 1]
        half_widths = np.array([comp.bounds[0] / 2 + 0.5 for comp in components])
        half_heights = np.array([comp.bounds[1] / 2 + 0.5 for comp in components])

        x_min = np.round((cx - half_widths - router1.origin[0]) / router1.cell_size).astype(int)
        x_max = np.round((cx + half_widths - router1.origin[0]) / router1.cell_size).astype(int)
        y_min = np.round((cy - half_heights - router1.origin[1]) / router1.cell_size).astype(int)
        y_max = np.round((cy + half_heights - router1.origin[1]) / router1.cell_size).astype(int)

        widths = x_max - x_min
        heights = y_max - y_min

        for i in range(n_comps):
            router1.block_rect(
                int(x_min[i]), int(y_min[i]), int(widths[i]), int(heights[i]), layer=-1
            )

        router2 = MazeRouter(
            grid_size=(100, 100), cell_size_mm=1.0, num_layers=2, origin=(0.0, 0.0)
        )
        router2._component_positions = positions

        for i, comp in enumerate(components):
            cx_loop, cy_loop = float(positions[i, 0]), float(positions[i, 1])
            hw, hh = comp.bounds[0] / 2 + 0.5, comp.bounds[1] / 2 + 0.5
            x_min_loop = int(round((cx_loop - hw - router2.origin[0]) / router2.cell_size))
            x_max_loop = int(round((cx_loop + hw - router2.origin[0]) / router2.cell_size))
            y_min_loop = int(round((cy_loop - hh - router2.origin[1]) / router2.cell_size))
            y_max_loop = int(round((cy_loop + hh - router2.origin[1]) / router2.cell_size))
            router2.block_rect(
                x_min_loop, y_min_loop, x_max_loop - x_min_loop, y_max_loop - y_min_loop, layer=-1
            )

        assert np.array_equal(router1.occupancy, router2.occupancy), (
            "block_components vectorized vs loop: occupancy mismatch"
        )

    def test_try_escape_route_vectorized_equals_loop(self):
        router1 = MazeRouter(grid_size=(50, 50), cell_size_mm=1.0, num_layers=4, origin=(0.0, 0.0))
        router2 = MazeRouter(grid_size=(50, 50), cell_size_mm=1.0, num_layers=4, origin=(0.0, 0.0))

        pin_x, pin_y = 25.0, 25.0
        step_x, step_y = 1, 0
        escape_length = 5

        gx, gy = router1._world_to_grid(pin_x, pin_y)
        for s in range(escape_length):
            if not (
                0 <= gx + s * step_x < router1.grid_size[0]
                and 0 <= gy + s * step_y < router1.grid_size[1]
            ):
                break
        else:
            for s in range(escape_length):
                for l in range(router1.num_layers):
                    router1.occupancy[gx + s * step_x, gy + s * step_y, l] = 0

        end_x = gx + (escape_length - 1) * step_x
        end_y = gy + (escape_length - 1) * step_y
        result2 = True
        if not (0 <= gx < router2.grid_size[0] and 0 <= gy < router2.grid_size[1]):
            result2 = False
        if not (0 <= end_x < router2.grid_size[0] and 0 <= end_y < router2.grid_size[1]):
            result2 = False

        if result2:
            steps = np.arange(escape_length)
            xs = gx + steps * step_x
            ys = gy + steps * step_y
            router2.occupancy[xs, ys, :] = 0

        assert np.array_equal(router1.occupancy, router2.occupancy), (
            "_try_escape_route vectorized vs loop: occupancy mismatch"
        )

    def test_neckdown_mask_vectorized_equals_loop(self):
        router1 = MazeRouter(grid_size=(50, 50), cell_size_mm=1.0, num_layers=2, origin=(0.0, 0.0))
        router2 = MazeRouter(grid_size=(50, 50), cell_size_mm=1.0, num_layers=2, origin=(0.0, 0.0))

        gx_min_neck, gy_min_neck = 10, 15
        gx_max_neck, gy_max_neck = 20, 25

        for x in range(gx_min_neck, gx_max_neck + 1):
            for y in range(gy_min_neck, gy_max_neck + 1):
                for l in range(router1.num_layers):
                    if 0 <= x < router1.grid_size[0] and 0 <= y < router1.grid_size[1]:
                        router1.neckdown_mask[x, y, l] = True

        x_neck_start = max(0, gx_min_neck)
        x_neck_end = min(router2.grid_size[0], gx_max_neck + 1)
        y_neck_start = max(0, gy_min_neck)
        y_neck_end = min(router2.grid_size[1], gy_max_neck + 1)

        if x_neck_start < x_neck_end and y_neck_start < y_neck_end:
            router2.neckdown_mask[x_neck_start:x_neck_end, y_neck_start:y_neck_end, :] = True

        assert np.array_equal(router1.neckdown_mask, router2.neckdown_mask), (
            "neckdown mask vectorized vs loop: mask mismatch"
        )


class TestVectorizedPerformance:
    def test_block_components_initialization_time(self):
        import time

        n_comps = 100
        components = [MockComponent(bounds=(2.0, 2.0)) for _ in range(n_comps)]
        positions = np.array(
            [[10.0 + i * 5.0, 20.0 + i * 3.0] for i in range(n_comps)], dtype=np.float32
        )

        router = MazeRouter(grid_size=(500, 500), cell_size_mm=1.0, num_layers=4, origin=(0.0, 0.0))

        start = time.perf_counter()
        for _ in range(10):
            router.block_components(components, positions, margin=0.5)
        elapsed = time.perf_counter() - start

        print(f"block_components (100 components, 10 iterations): {elapsed * 1000:.2f}ms")
        assert elapsed < 2.0, f"block_components took too long: {elapsed * 1000:.2f}ms"

    def test_block_pads_initialization_time(self):
        import time

        n_comps = 50
        pins = [MockPin(position=(0.5, 0.5), net=f"NET{i % 10}") for i in range(8)]
        components = [MockComponent(bounds=(2.0, 2.0), pins=pins) for _ in range(n_comps)]
        positions = np.array(
            [[10.0 + i * 5.0, 20.0 + i * 3.0] for i in range(n_comps)], dtype=np.float32
        )

        mock_netlist = Mock()
        mock_netlist.nets = []

        router = MazeRouter(grid_size=(500, 500), cell_size_mm=1.0, num_layers=4, origin=(0.0, 0.0))

        start = time.perf_counter()
        for _ in range(5):
            router.block_pads(components, positions, mock_netlist, margin=0.2)
        elapsed = time.perf_counter() - start

        print(f"block_pads (50 components, 5 iterations): {elapsed * 1000:.2f}ms")
        assert elapsed < 3.0, f"block_pads took too long: {elapsed * 1000:.2f}ms"
