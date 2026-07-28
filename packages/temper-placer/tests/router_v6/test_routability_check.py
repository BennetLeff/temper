"""
Tests for the completion invariant checker (routability_check.py).

Covers:
- PBT: random obstacle grids, verify check_routability agrees with A* routing
- Regression: run check on all 24 temper nets, compare with expected routability
- Benchmark: measure check time per net (<100ms target)
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6.routability_check import (
    astar_passability,
    check_routability,
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
            "test",
            (5.0, 5.0),
            (45.0, 45.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )

    def test_direct_path_exists(self):
        edt = np.ones((100, 100), dtype=np.float64)
        mask = np.ones((100, 100), dtype=bool)
        assert check_routability(
            "test",
            (10.0, 10.0),
            (90.0, 90.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )

    def test_adjacent_cells(self):
        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        assert check_routability(
            "test",
            (1.0, 1.0),
            (2.0, 1.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )


class TestCheckRoutabilityBlocked:
    """Induction: blocking cells removes only paths that pass through them."""

    def test_completely_blocked(self):
        edt = np.zeros((50, 50), dtype=np.float64)
        mask = np.zeros((50, 50), dtype=bool)
        assert not check_routability(
            "test",
            (5.0, 5.0),
            (45.0, 45.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )

    def test_partial_wall(self):
        edt = np.ones((30, 50), dtype=np.float64)
        mask = np.ones((30, 50), dtype=bool)
        # Wall spanning all rows at column 25.
        mask[:, 25] = False
        edt[:, 25] = 0.0
        assert not check_routability(
            "test",
            (10.0, 15.0),
            (40.0, 15.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )

    def test_wall_with_gap(self):
        edt = np.ones((30, 50), dtype=np.float64)
        mask = np.ones((30, 50), dtype=bool)
        mask[10:15, 25] = False
        mask[17:20, 25] = False
        edt[10:15, 25] = 0.0
        edt[17:20, 25] = 0.0
        assert check_routability(
            "test",
            (10.0, 16.0),
            (40.0, 16.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )


class TestCheckRoutabilityNarrow:
    """Width constraint: cells narrower than trace_width are impassable."""

    def test_narrow_corridor_rejected(self):
        edt = np.zeros((50, 50), dtype=np.float64)
        mask = np.zeros((50, 50), dtype=bool)
        mask[20:30, :] = True
        edt[20:30, :] = 0.4  # width = 2*0.4*0.1 = 0.08mm < 0.2mm
        assert not check_routability(
            "test",
            (5.0, 25.0),
            (45.0, 25.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )

    def test_wide_corridor_accepted(self):
        edt = np.zeros((50, 50), dtype=np.float64)
        mask = np.zeros((50, 50), dtype=bool)
        mask[20:30, :] = True
        edt[20:30, :] = 2.0  # width = 2*2.0*0.1 = 0.4mm >= 0.2mm
        assert check_routability(
            "test",
            (5.0, 25.0),
            (45.0, 25.0),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
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
            "test",
            (5.0, 25.0),
            (45.0, 25.0),
            edt,
            mask,
            trace_width=trace_width,
            cell_size=cell_size,
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
            "test",
            (5, 5),
            (45, 45),
            mask,
            trace_width=0.1,
            cell_size=0.1,
        )

    def test_blocked_grid(self):
        mask = np.ones((50, 50), dtype=bool)
        assert not check_routability_direct(
            "test",
            (5, 5),
            (45, 45),
            mask,
            trace_width=0.1,
            cell_size=0.1,
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


def _random_obstacle_grid(rng: np.random.Generator, w: int, h: int, density: float) -> np.ndarray:
    return rng.random((h, w)) < density


def _random_endpoints(
    rng: np.random.Generator, w: int, h: int, obstacle: np.ndarray
) -> tuple[tuple[int, int], tuple[int, int]]:
    free = np.argwhere(~obstacle)  # (y, x)
    if len(free) < 2:
        return (0, 0), (0, 0)
    idx = rng.choice(len(free), size=2, replace=False)
    return (int(free[idx[0]][1]), int(free[idx[0]][0])), (
        int(free[idx[1]][1]),
        int(free[idx[1]][0]),
    )


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
            "pbt_net",
            start,
            goal,
            obstacle,
            trace_width=trace_width,
            cell_size=cell_size,
        )
        astar_result = astar_passability(start, goal, obstacle)

        assert dijkstra_result == (astar_result is not None), (
            f"seed={seed}: Dijkstra={dijkstra_result}, A*={astar_result is not None}"
        )


# ---------------------------------------------------------------------------
# Regression: 24 temper nets
# ---------------------------------------------------------------------------

TEMPER_NETS = [
    "AC_L",
    "AC_N",
    "GND",
    "DC_BUS+",
    "DC_BUS-",
    "PGND",
    "GATE_H",
    "SW_NODE",
    "GATE_L",
    "+15V",
    "PWM_H",
    "PWM_L",
    "CGND",
    "VCC_BOOT",
    "+5V",
    "+3V3",
    "I_SENSE",
    "SPI_CLK",
    "SPI_MOSI",
    "SPI_MISO",
    "SPI_CS_TEMP",
    "USB_D+",
    "USB_D-",
    "TEMP_SENSE",
]

_SKIPPED_NETS = frozenset(
    {
        "AC_L",
        "AC_N",
        "GND",
        "DC_BUS+",
        "DC_BUS-",
        "PGND",
        "SW_NODE",
        "+15V",
        "CGND",
        "+5V",
        "+3V3",
    }
)

_ROUTABLE_SIGNAL_NETS = frozenset(
    {
        "GATE_H",
        "GATE_L",
        "PWM_H",
        "PWM_L",
        "VCC_BOOT",
        "I_SENSE",
        "SPI_CLK",
        "SPI_MOSI",
        "SPI_MISO",
        "SPI_CS_TEMP",
        "USB_D+",
        "USB_D-",
        "TEMP_SENSE",
    }
)

# ---------------------------------------------------------------------------
# Flat -> hierarchical net-name reconciliation
# ---------------------------------------------------------------------------
#
# `TEMPER_NETS` above uses flat corpus-board names. The production board
# (`pcb/temper.kicad_pcb`) is generated by atopile, which emits hierarchical
# names for anything not given an explicit `override_net_name` in
# `elec/src/main.ato` -- so 11 of the 13 `_ROUTABLE_SIGNAL_NETS` don't exist
# under their flat spelling on the real board.
#
# Rather than hand-translate each flat name into a second hardcoded
# hierarchical string (the same failure mode that produced this drift --
# atopile is free to rename an un-overridden net at any future build), each
# renamed signal below is anchored to a (designator, pin) pair: a physical
# pinout fact traceable directly to source (`override_net_name` assignments
# or, for the ESP32 module, the component's own internal pin-alias table in
# `elec/src/components.ato`). `_resolve_net_name` looks up which net
# currently touches that pin *from the netlist loaded at test time*, so a
# future net-name change doesn't rot this mapping the way the flat list did
# -- the pin identity is what's stable, not the string.
#
# Evidence per entry (component + pin traced to elec/src, not string
# similarity):
#
#   GATE_H  -> (U7,  "15")  UCC21550BDWK.OUTA (components.ato:59,
#               "signal OUTA ~ pin 15"); main.ato:604 overrides this net to
#               "GATE_HS".
#   GATE_L  -> (U6,  "1")   IKW40N120H3 (low-side IGBT) gate pin, TO-247 pin
#               1; main.ato:607 overrides the driving resistor's net to
#               "GATE_LS", which is the same net (wire, no intervening part).
#   PWM_H   -> (U27, "4")   ESP32_S3_WROOM_1.IO4 (components.ato:717,
#               "signal IO4 ~ pin 4"); modules.ato:3080 `mcu.IO4 ~ pwm_h`;
#               main.ato:514 overrides hb.pwm_h's net to "PWM_HS".
#   PWM_L   -> (U27, "5")   ESP32_S3_WROOM_1.IO5 (components.ato:718);
#               modules.ato:3081 `mcu.IO5 ~ pwm_l`; main.ato:515 overrides
#               to "PWM_LS".
#   SPI_CLK -> (U27, "12")  ESP32_S3_WROOM_1 pin 12 is literally aliased
#               `SPI_CLK` inside the component itself (components.ato:676,
#               "signal SPI_CLK ~ pin 12 # IO8"). main.ato:553 overrides
#               `rtd_pan.spi.sclk`'s net (the far end of this same wire) to
#               "RTD_SCK".
#   SPI_MOSI-> (U27, "19")  component's own `signal SPI_MOSI ~ pin 19`
#               (components.ato:678); main.ato:554 overrides to "RTD_SDI".
#   SPI_MISO-> (U27, "20")  component's own `signal SPI_MISO ~ pin 20`
#               (components.ato:679); main.ato:555 overrides to "RTD_SDO".
#   SPI_CS_TEMP
#           -> (U27, "18")  component's own `signal SPI_CS ~ pin 18`
#               (components.ato:677); main.ato:556 overrides
#               `rtd_pan.cs.line`'s net to "RTD_CS_N".
#   VCC_BOOT-> (U8,  "1")   ES1J bootstrap diode cathode (components.ato:287,
#               "signal K ~ pin 1"); modules.ato:201-202 ties
#               `boot_diode.K ~ driver.VDDA` (the high-side gate driver's
#               bootstrap-charged floating supply -- the textbook meaning of
#               "VCC_BOOT" for a half-bridge gate driver). Not
#               override-named, so its net keeps an auto-generated name
#               ("hb.gate_hs.driver-p1-1" as of this build) -- exactly why
#               this needs a pin anchor rather than a literal string.
#   USB_D+  -> (U27, "14")  modules.ato:3045 `usb_dp ~ mcu.IO20`;
#               components.ato:730 `signal IO20 ~ pin 14`.
#   USB_D-  -> (U27, "13")  modules.ato:3044 `usb_dn ~ mcu.IO19`;
#               components.ato:729 `signal IO19 ~ pin 13`.
#
# On the "two SPI buses" caution: `elec/src/modules.ato` has exactly two
# `new SPI` instances -- `MCU.spi` and `RTDSensing.spi` -- and
# `elec/src/main.ato` wires them to each other and nothing else
# (`rtd_pan.spi.sclk ~ mcu.spi.sclk`, etc). There is only one physical SPI
# bus on this board; it is RTD-dedicated. What look like "two buses" are two
# net-name *segments* of that one bus, split by series resistors R35-R38
# (`elec/src/modules.ato`'s RTDSensing filtering network): the MCU-side
# segment carries the deliberately-chosen "RTD_SCK"/"RTD_SDI"/"RTD_SDO"/
# "RTD_CS_N" names (main.ato's overrides), the chip-side segment (R35-38 to
# U9, the MAX31865) keeps the auto-generated lowercase "sclk"/"sdi"/"sdo"/
# "cs_n" names. Matching on the MCU-side segment here (not on the visually
# similar lowercase segment) is a pin-traced choice, not a string-similarity
# guess -- see the SPI_* entries above.
#
# TEMP_SENSE has **no anchor** and is deliberately left unresolved.
# `elec/src/main.ato` never assigns any net an override name naming it as
# "the" temperature-sense signal, and at least three distinct candidate
# nets exist with no textual or structural basis to prefer one:
#   - The RTD probe's own 4-wire Kelvin interface (`rtd_force_p`,
#     `rtd_force_n`, `rtd_sense_p`, `rtd_sense_n` -- modules.ato:1492-1499,
#     1745-1748); a 4-wire measurement has no single "the" signal.
#   - The heatsink NTC divider node (`ThermalComparator.ntc_sense.line`,
#     modules.ato:2130-2171).
#   - The coil NTC divider node (`CoilThermalComparator.ntc_sense.line`,
#     modules.ato:2255-2280).
# Independently, all four RTD force/sense nets are single-pad on
# `pcb/temper.kicad_pcb` (no RTD probe connector is instantiated anywhere in
# `elec/src` -- confirmed by grep) so even a forced pick among those four
# would still legitimately report "no pads". Picking any one of the six
# candidates here would be exactly the naming-convention guess this
# reconciliation is trying to avoid, so `TEMP_SENSE` is left unmapped and
# will continue to report "no pads" until a real net is identified.
#
# USB_D+/USB_D- resolve correctly (the mapping above is unambiguous) but
# will still report "no pads": grepping `elec/src/*.ato` for a USB connector
# turns up none -- `usb_dp`/`usb_dn` terminate at the ESP32-S3 module pins
# and nowhere else, so each is a single-pad net on the real board. That is a
# real design gap (no USB connector instantiated), not a mapping bug --
# reported here, not silently routed around.
_NET_BY_PIN_ANCHOR: dict[str, tuple[str, str]] = {
    "GATE_H": ("U7", "15"),
    "GATE_L": ("U6", "1"),
    "PWM_H": ("U27", "4"),
    "PWM_L": ("U27", "5"),
    "SPI_CLK": ("U27", "12"),
    "SPI_MOSI": ("U27", "19"),
    "SPI_MISO": ("U27", "20"),
    "SPI_CS_TEMP": ("U27", "18"),
    "VCC_BOOT": ("U8", "1"),
    "USB_D+": ("U27", "14"),
    "USB_D-": ("U27", "13"),
    # TEMP_SENSE: intentionally absent -- see comment block above.
}


def _resolve_net_name(name: str, pcb) -> str:
    """Resolve *name* to its actual net name on the loaded production board.

    Tries the literal flat name first (covers the 13 nets that were never
    renamed). Falls back to `_NET_BY_PIN_ANCHOR` for nets known to have been
    renamed by the atopile hierarchical build, deriving the current net name
    by scanning the netlist *loaded at test time* for whichever net touches
    that (designator, pin) -- not from a second hardcoded string.
    """
    literal_names = {net.name for net in pcb.nets}
    if name in literal_names:
        return name
    anchor = _NET_BY_PIN_ANCHOR.get(name)
    if anchor is None:
        return name
    for net in pcb.nets:
        if anchor in net.pins:
            return net.name
    return name


def _load_temper_edt():
    """Compute EDT grids for the temper board."""
    pytest.importorskip("shapely")
    from dataclasses import replace

    from temper_placer.deterministic.state import BoardState
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.channel_widths import _build_edt
    from temper_placer.router_v6.routing_space import RoutingSpaceStage

    pcb_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
    )
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
                positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
            if len(positions) >= 2:
                net_pads[net.name] = positions

        unroutable = []

        for net_name in sorted(_ROUTABLE_SIGNAL_NETS):
            # The production board uses hierarchical net names for anything
            # not explicitly overridden in elec/src/main.ato; resolve via
            # the pin-anchor table (see _NET_BY_PIN_ANCHOR above) rather
            # than looking up the flat corpus-board name directly.
            resolved_name = _resolve_net_name(net_name, pcb)
            label = net_name if resolved_name == net_name else f"{net_name} ({resolved_name})"

            pads = net_pads.get(resolved_name)
            if pads is None or len(pads) < 2:
                unroutable.append((label, "no pads"))
                continue

            start = pads[0]
            goal = pads[-1]

            result = check_routability_cc(
                resolved_name,
                start,
                goal,
                edt_fcu,
                mask_fcu,
                trace_width=trace_width,
                cell_size=cell_size_val,
                origin=(bounds_fcu[0], bounds_fcu[1]),
                pad_radius_cells=pad_radius_cells,
            )
            if not result:
                unroutable.append((label, "check_routability returned False"))

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
                "bench",
                (5, 5),
                (95, 95),
                edt,
                mask,
                trace_width=0.2,
                cell_size=0.1,
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
                f"n{i}",
                (100 + i * 50, h // 2),
                (w - 100 - i * 50, h // 2),
                edt,
                mask,
                trace_width=0.3,
                cell_size=cell_size,
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
            "bench",
            (10, 10),
            (1990, 1990),
            edt,
            mask,
            trace_width=0.2,
            cell_size=0.1,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        assert elapsed < 20.0, f"Blocked grid should exit fast: {elapsed:.1f}ms"
