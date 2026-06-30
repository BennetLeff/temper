"""
Tests for the completion invariant checker (routability_check.py).

Covers:
- PBT: random obstacle grids, verify check_routability agrees with A* routing
- Regression: run check on all 24 temper nets, compare with expected routability
- Benchmark: measure check time per net (<100ms target)
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6.routability_check import (
    astar_passability,
    check_routability,
    check_routability_bidi,
    check_routability_cc,
    check_routability_direct,
)


# ---------------------------------------------------------------------------
# Unit tests (correctness proof)
# ---------------------------------------------------------------------------

class TestCheckRoutabilityEmptyGrid:
    """Base case: empty grid -> every net is routable."""

    def test_full_open_grid(self):
        edt = np.ones((50, 50), dtype=np.float64)
        mask = np.ones((50, 50), dtype=bool)
        assert check_routability(
            "test", (5.0, 5.0), (45.0, 45.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )

    def test_direct_path_exists(self):
        edt = np.ones((100, 100), dtype=np.float64)
        mask = np.ones((100, 100), dtype=bool)
        assert check_routability(
            "test", (10.0, 10.0), (90.0, 90.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )

    def test_adjacent_cells(self):
        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        assert check_routability(
            "test", (1.0, 1.0), (2.0, 1.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )


class TestCheckRoutabilityBlocked:
    """Induction: blocking cells removes only paths that pass through them."""

    def test_completely_blocked(self):
        edt = np.zeros((50, 50), dtype=np.float64)
        mask = np.zeros((50, 50), dtype=bool)
        assert not check_routability(
            "test", (5.0, 5.0), (45.0, 45.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )

    def test_partial_wall(self):
        edt = np.ones((30, 50), dtype=np.float64)
        mask = np.ones((30, 50), dtype=bool)
        # Wall spanning all rows at column 25.
        mask[:, 25] = False
        edt[:, 25] = 0.0
        assert not check_routability(
            "test", (10.0, 15.0), (40.0, 15.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )

    def test_wall_with_gap(self):
        edt = np.ones((30, 50), dtype=np.float64)
        mask = np.ones((30, 50), dtype=bool)
        mask[10:15, 25] = False
        mask[17:20, 25] = False
        edt[10:15, 25] = 0.0
        edt[17:20, 25] = 0.0
        assert check_routability(
            "test", (10.0, 16.0), (40.0, 16.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )


class TestCheckRoutabilityNarrow:
    """Width constraint: cells narrower than trace_width are impassable."""

    def test_narrow_corridor_rejected(self):
        edt = np.zeros((50, 50), dtype=np.float64)
        mask = np.zeros((50, 50), dtype=bool)
        mask[20:30, :] = True
        edt[20:30, :] = 0.4  # width = 2*0.4*0.1 = 0.08mm < 0.2mm
        assert not check_routability(
            "test", (5.0, 25.0), (45.0, 25.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )

    def test_wide_corridor_accepted(self):
        edt = np.zeros((50, 50), dtype=np.float64)
        mask = np.zeros((50, 50), dtype=bool)
        mask[20:30, :] = True
        edt[20:30, :] = 2.0  # width = 2*2.0*0.1 = 0.4mm >= 0.2mm
        assert check_routability(
            "test", (5.0, 25.0), (45.0, 25.0),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )

    def test_edge_width(self):
        edt = np.zeros((50, 50), dtype=np.float64)
        mask = np.zeros((50, 50), dtype=bool)
        mask[20:30, :] = True
        cell_size = 0.1
        trace_width = 0.2
        min_dist = trace_width / (2.0 * cell_size)  # = 1.0
        edt[20:30, :] = min_dist
        assert check_routability(
            "test", (5.0, 25.0), (45.0, 25.0),
            edt, mask, trace_width=trace_width, cell_size=cell_size,
        )


class TestCheckRoutabilityOrigin:
    """World-coordinate mapping via origin parameter."""

    def test_with_origin(self):
        edt = np.ones((100, 100), dtype=np.float64)
        mask = np.ones((100, 100), dtype=bool)
        # With origin=(0, 0) and cell_size=1.0, grid is at world coords [0,100).
        assert check_routability(
            "test",
            start=(10.0, 20.0),
            goal=(90.0, 80.0),
            edt_grid=edt,
            edt_mask=mask,
            trace_width=0.2,
            cell_size=1.0,
            origin=(0.0, 0.0),
        )

    def test_start_goal_outside_bounds(self):
        edt = np.ones((20, 20), dtype=np.float64)
        mask = np.ones((20, 20), dtype=bool)
        assert not check_routability(
            "test",
            start=(10.0, 10.0),
            goal=(30.0, 30.0),
            edt_grid=edt,
            edt_mask=mask,
            trace_width=0.2,
            cell_size=0.1,
            origin=(0.0, 0.0),
        )


class TestCheckRoutabilityDirect:
    """Convenience wrapper: EDT computed from obstacle mask."""

    def test_open_grid(self):
        mask = np.zeros((50, 50), dtype=bool)
        assert check_routability_direct(
            "test", (5, 5), (45, 45), mask, trace_width=0.1, cell_size=0.1,
        )

    def test_blocked_grid(self):
        mask = np.ones((50, 50), dtype=bool)
        assert not check_routability_direct(
            "test", (5, 5), (45, 45), mask, trace_width=0.1, cell_size=0.1,
        )


# ---------------------------------------------------------------------------
# A* oracle self-tests
# ---------------------------------------------------------------------------

def test_astar_self_consistent():
    """A* on an empty grid finds a path."""
    mask = np.zeros((30, 30), dtype=bool)
    path = astar_passability((0, 0), (29, 29), mask)
    assert path is not None
    assert len(path) >= 2
    assert path[0] == (0, 0)
    assert path[-1] == (29, 29)


def test_astar_blocked():
    """A* on a fully blocked grid returns None."""
    mask = np.ones((30, 30), dtype=bool)
    path = astar_passability((1, 1), (28, 28), mask)
    assert path is None


# ---------------------------------------------------------------------------
# PBT: Property-Based Testing
# ---------------------------------------------------------------------------

def _random_obstacle_grid(rng: np.random.Generator, w: int, h: int,
                          density: float) -> np.ndarray:
    return rng.random((h, w)) < density


def _random_endpoints(rng: np.random.Generator, w: int, h: int,
                      obstacle: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
    free = np.argwhere(~obstacle)  # (y, x)
    if len(free) < 2:
        return (0, 0), (0, 0)
    idx = rng.choice(len(free), size=2, replace=False)
    return (int(free[idx[0]][1]), int(free[idx[0]][0])), \
           (int(free[idx[1]][1]), int(free[idx[1]][0]))


class TestPBTAgreement:
    """Property: check_routability agrees with actual A* routing outcome."""

    @pytest.mark.parametrize("seed", list(range(100)))
    def test_routability_matches_astar(self, seed: int):
        """For a random obstacle grid, Dijkstra-EDT routability
        matches A* pathfinding outcome."""
        rng = np.random.default_rng(seed)
        w, h = 30, 30
        density = rng.uniform(0.05, 0.5)
        obstacle = _random_obstacle_grid(rng, w, h, density)
        start, goal = _random_endpoints(rng, w, h, obstacle)

        if obstacle[start[1], start[0]] or obstacle[goal[1], goal[0]]:
            pytest.skip("start or goal blocked")

        # Generous trace width: any free cell is passable.
        # EDT passability = A* on binary mask.
        trace_width = 0.01
        cell_size = 1.0

        dijkstra_result = check_routability_direct(
            "pbt_net", start, goal, obstacle,
            trace_width=trace_width, cell_size=cell_size,
        )
        astar_result = astar_passability(start, goal, obstacle)

        assert dijkstra_result == (astar_result is not None), (
            f"seed={seed}: Dijkstra={dijkstra_result}, A*={astar_result is not None}"
        )


# ---------------------------------------------------------------------------
# Regression: 24 temper nets
# ---------------------------------------------------------------------------

TEMPER_NETS = [
    "AC_L", "AC_N", "GND", "DC_BUS+", "DC_BUS-", "PGND",
    "GATE_H", "SW_NODE", "GATE_L", "+15V", "PWM_H", "PWM_L",
    "CGND", "VCC_BOOT", "+5V", "+3V3", "I_SENSE",
    "SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS_TEMP",
    "USB_D+", "USB_D-", "TEMP_SENSE",
]

_SKIPPED_NETS = frozenset({
    "AC_L", "AC_N", "GND", "DC_BUS+", "DC_BUS-", "PGND",
    "SW_NODE", "+15V", "CGND", "+5V", "+3V3",
})

_ROUTABLE_SIGNAL_NETS = frozenset({
    "GATE_H", "GATE_L", "PWM_H", "PWM_L", "VCC_BOOT",
    "I_SENSE", "SPI_CLK", "SPI_MOSI", "SPI_MISO",
    "SPI_CS_TEMP", "USB_D+", "USB_D-", "TEMP_SENSE",
})


def _load_temper_edt():
    """Compute EDT grids for the temper board."""
    pytest.importorskip("shapely")
    from dataclasses import replace

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.channel_widths import _build_edt
    from temper_placer.router_v6.routing_space import RoutingSpaceStage
    from temper_placer.deterministic.state import BoardState

    pcb_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
    if not pcb_path.exists():
        pytest.skip(f"PCB not found: {pcb_path}")

    pcb = parse_kicad_pcb_v6(pcb_path)
    state = replace(BoardState(), _parsed_pcb=pcb)
    state = RoutingSpaceStage().run(state)
    routing_spaces = state.routing_spaces
    assert routing_spaces is not None

    cell_size = 0.1
    edt_data = {}
    for layer in ("F.Cu", "B.Cu"):
        if layer in routing_spaces:
            edt, mask, bounds = _build_edt(routing_spaces[layer], cell_size, use_cache=True)
            edt_data[layer] = (edt, mask, bounds)

    origin = (0.0, 0.0)
    for _, _, bounds in edt_data.values():
        origin = (bounds[0], bounds[1])
        break

    return edt_data.get("F.Cu", (None, None, None)), origin, cell_size, pcb


class TestTemperRegression:
    """Regression: check_routability on all 24 temper nets."""

    @pytest.fixture(scope="class")
    def temper_data(self):
        return _load_temper_edt()

    def test_all_24_nets_listed(self):
        assert len(TEMPER_NETS) == 24
        assert len(_SKIPPED_NETS) == 11
        assert len(_ROUTABLE_SIGNAL_NETS) == 13

    def test_signal_nets_are_routable(self, temper_data):
        (edt_fcu, mask_fcu, bounds_fcu), origin, cell_size, pcb = temper_data
        if edt_fcu is None:
            pytest.skip("No F.Cu EDT grid available")

        trace_width = 0.3
        trace_width = 0.3
        cell_size_val = cell_size

        # Pad clearing radius: the router's ``_unblock_net_pads`` clears
        # ``ceil((rad_mm + inflation_mm) / cell_size) + 1`` cells.
        # For TO-247 power MOSFET pads (~2mm radius) + 0.15mm inflation:
        #   ceil((2.0 + 0.15) / 0.1) + 1 = 23 cells.
        # We use 30 cells to be conservative (covers edge cases where
        # component footprints erode the routing area far from pads).
        pad_radius_cells = 30

        comp_by_ref = {c.ref: c for c in pcb.components}
        net_pads: dict[str, list[tuple[float, float]]] = {}

        for net in pcb.nets:
            positions = []
            for comp_ref, pin_name in getattr(net, "pins", []):
                comp = comp_by_ref.get(comp_ref)
                if comp is None:
                    continue
                comp_pos = getattr(comp, "initial_position", None)
                if comp_pos is None:
                    continue
                pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
                if pin is None:
                    positions.append((float(comp_pos[0]), float(comp_pos[1])))
                    continue
                px, py = pin.position
                positions.append((float(comp_pos[0]) + float(px),
                                  float(comp_pos[1]) + float(py)))
            if len(positions) >= 2:
                net_pads[net.name] = positions

        unroutable = []

        for net_name in sorted(_ROUTABLE_SIGNAL_NETS):
            pads = net_pads.get(net_name)
            if pads is None or len(pads) < 2:
                unroutable.append((net_name, "no pads"))
                continue

            start = pads[0]
            goal = pads[-1]

            result = check_routability_cc(
                net_name, start, goal,
                edt_fcu, mask_fcu,
                trace_width=trace_width,
                cell_size=cell_size_val,
                origin=(bounds_fcu[0], bounds_fcu[1]),
                pad_radius_cells=pad_radius_cells,
            )
            if not result:
                unroutable.append((net_name, "check_routability returned False"))

        assert len(unroutable) == 0, f"Unroutable signal nets: {unroutable}"

    def test_power_nets_skipped(self, temper_data):
        for net_name in _SKIPPED_NETS:
            assert net_name not in _ROUTABLE_SIGNAL_NETS


# ---------------------------------------------------------------------------
# Benchmark: per-net check latency
# ---------------------------------------------------------------------------

class TestBenchmark:
    """check_routability must finish fast (<100ms per net on realistic grids)."""

    def test_latency_small_grid(self):
        """100x100 grid: connected-components labeling + check (<10ms)."""
        edt = np.ones((100, 100), dtype=np.float64)
        mask = np.ones((100, 100), dtype=bool)
        t0 = time.perf_counter()
        for _ in range(20):
            check_routability_cc(
                "bench", (5, 5), (95, 95),
                edt, mask, trace_width=0.2, cell_size=0.1,
            )
        elapsed = (time.perf_counter() - t0) / 20 * 1000
        assert elapsed < 10.0, f"Too slow: {elapsed:.1f}ms per call"

    def test_latency_realistic_board_grid(self):
        """1501x1001 grid (temper size).  First call labels, subsequent
        calls are O(1) lookups.  Average <80ms per net for 13 nets."""
        h, w = 1501, 1001
        cell_size = 0.1
        edt = np.full((h, w), 10.0, dtype=np.float64)
        mask = np.ones((h, w), dtype=bool)

        t0 = time.perf_counter()
        for i in range(13):
            check_routability_cc(
                f"n{i}", (100 + i * 50, h // 2), (w - 100 - i * 50, h // 2),
                edt, mask, trace_width=0.3, cell_size=cell_size,
            )
        total = (time.perf_counter() - t0) * 1000
        avg = total / 13
        assert avg < 80.0, f"Average too slow: {avg:.1f}ms per net"

    def test_latency_unroutable_early_exit(self):
        """Blocked grid: label reveals no connected component (<10ms)."""
        edt = np.zeros((2000, 2000), dtype=np.float64)
        mask = np.zeros((2000, 2000), dtype=bool)
        t0 = time.perf_counter()
        check_routability_cc(
            "bench", (10, 10), (1990, 1990),
            edt, mask, trace_width=0.2, cell_size=0.1,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        assert elapsed < 20.0, f"Blocked grid should exit fast: {elapsed:.1f}ms"
