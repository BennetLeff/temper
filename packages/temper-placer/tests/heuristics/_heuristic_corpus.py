"""Shared input corpus for the Wave 4 **Phase 5** heuristics differential
AND its performance benchmark.

Why one module rather than two lists
------------------------------------
PR #714 passed a differential at ``[0, 1, 2, 8, 17, 100]`` iterations and
then failed CI on a benchmark that ran **120**. #721 made that impossible
structurally by making the benchmark draw its inputs from the same module
the differential parametrises over. This file is that module for Phase 5.

The contract is enforced mechanically, not by convention:
``BENCH_CASES`` is a *subset selector over* ``CASES``, and
``test_structural_rust_differential.py`` asserts that every benchmark case
id is present in the differential's parametrisation and that no benchmark
case is larger — on any size axis — than the largest differential case.
Adding a bigger benchmark input without adding it here fails that test.

Size axes that matter for this surface
--------------------------------------
* ``n_components`` — every classification kernel is a scan over components.
* ``n_nets`` / ``pins_per_net`` — ``identify_decoupling_caps`` and
  ``classify_signal_domains`` walk nets per component.
* ``keepout_radius`` — ``create_keepout_mask`` rasterizes a disk per
  mounting hole, so cost is quadratic in the radius, and the *largest*
  radius is the one that must be differentially covered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from temper_placer._constraint_types.config import PlacementConstraints
from temper_placer._constraint_types.groups import ComponentGroup
from temper_placer._constraint_types.thermal import ThermalConstraint, ThermalProperties
from temper_placer._constraint_types.topology import CriticalLoop
from temper_placer.core.board import Board, MountingHole
from temper_placer.core.netlist import Component, Net, Netlist

# Reference-designator vocabulary chosen so that EVERY regex branch in
# structural.py and organizational.py is exercised by at least one ref, and
# so that several refs are ambiguous between branches (which is where a port
# that reorders the pattern checks diverges).
REF_TEMPLATES: tuple[str, ...] = (
    "J1_DC_IN",  # connector, power_input, power-flow input
    "J2_OUT",  # connector, power_output
    "J3_SWD",  # connector, debug
    "P1",  # connector by P-pattern
    "CON2",  # connector by CON-pattern
    "F1",  # power-flow input (fuse)
    "C_BULK_1",  # power-flow input (bulk cap), ground-domain PGND
    "C_IN_2",  # power-flow input
    "C_DEC_U1",  # decoupling cap by naming
    "C_BYPASS_9",  # decoupling cap by naming
    "U_BUCK_1",  # distribution, domain power, PGND
    "U_LDO_2",  # distribution
    "U_MCU_1",  # load, domain digital
    "U_GATE_DRV",  # load, domain power
    "U_SENS_3",  # analog
    "U_OPAMP_4",  # analog
    "U_ADC_5",  # analog
    "R_SENSE_1",  # analog
    "R_GATE_H",  # plain resistor
    "Q1",  # thermal (power pattern), domain power
    "Q2",  # thermal
    "L1",  # distribution + domain power
    "Y1",  # crystal, digital
    "D1_PWR",  # power diode
    "TP7",  # matches nothing -- default branches
    "MH1",  # matches nothing
)

# Footprints chosen to exercise the footprint-keyword branches of
# `identify_connectors` (conn/header/jst/molex/usb/terminal/barrel/dc_jack)
# and `identify_thermal_components` (to-220/to-247/to-263/d2pak/dpak/...).
FOOTPRINT_TEMPLATES: tuple[str, ...] = (
    "Connector_Barrel_Jack",
    "TerminalBlock_1x02",
    "USB_C_Receptacle",
    "PinHeader_1x04",
    "JST_PH_2",
    "Molex_KK",
    "TO-220-3_Vertical",
    "TO-263-3",
    "DPAK_TabPin2",
    "PowerSO-20",
    "R_0402_1005Metric",
    "C_0603_1608Metric",
    "SOIC-8_3.9x4.9mm",
    "",  # empty footprint -- lower() on "" must not classify
)

NET_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("VCC_3V3", "Power"),
    ("GND", "Power"),
    ("PGND", "Power"),
    ("AGND", "Signal"),
    ("DGND", "Signal"),
    ("VIN", "Power"),
    ("SPI_MOSI", "Signal"),
    ("I2C_SDA", "Signal"),
    ("UART_TX", "Signal"),
    ("ADC_SENSE", "Signal"),
    ("SW_NODE", "Signal"),
    ("ANALOG_REF", "Signal"),
)


@dataclass(frozen=True)
class Case:
    """One corpus point. `ident` is the pytest id AND the benchmark key."""

    ident: str
    n_components: int
    n_nets: int
    pins_per_net: int
    keepout_radius: float
    board_w: float
    board_h: float
    origin: tuple[float, float] = (0.0, 0.0)
    # Deliberately int-typed geometry: the dataclasses do no coercion, so an
    # int board dimension must stay an int all the way through the port.
    int_geometry: bool = False
    n_holes: int = 0
    resolution_mm: float = 1.0
    buffer_mm: float = 1.0
    margin_mm: float = 3.0
    fixed_every: int = 0  # every Nth component gets fixed=True (0 = none)
    thermal_refs: tuple[str, ...] = ()
    group_refs: tuple[str, ...] = ()
    loop_nets: tuple[str, ...] = ()
    keepout_rects: tuple[tuple[float, float, float, float], ...] = ()
    extra_refs: tuple[str, ...] = field(default_factory=tuple)


# --- The corpus -------------------------------------------------------------
#
# Ordered smallest-first. The degenerate points at the top are the ones that
# catch off-by-one and empty-container divergence; the large points at the
# bottom are what the benchmark is allowed to draw from.
CASES: tuple[Case, ...] = (
    Case("empty", 0, 0, 0, 0.0, 10.0, 10.0),
    Case("single_component", 1, 0, 0, 0.0, 10.0, 10.0),
    Case("single_net_single_pin", 1, 1, 1, 0.0, 10.0, 10.0),
    # margin_cells == 0 -- the `if margin_cells > 0` branch must NOT fire.
    Case("zero_margin", 4, 2, 2, 0.0, 20.0, 20.0, margin_mm=0.0, buffer_mm=0.0),
    # margin >= board -- `mask[-k:]` with k >= H, i.e. the whole array.
    Case("margin_exceeds_board", 4, 2, 2, 0.0, 6.0, 6.0, margin_mm=5.0, buffer_mm=2.0),
    # Integer board geometry: `ox + margin` stays an `int` and must not widen.
    Case("int_geometry", 6, 3, 2, 0, 40, 30, origin=(0, 0), int_geometry=True, margin_mm=2),
    # Negative origin -- `int((hx - ox) / res)` truncates TOWARD ZERO, so the
    # sign of the operand changes which cell a hole lands in.
    Case("negative_origin", 8, 4, 3, 2.5, 40.0, 30.0, origin=(-15.0, -7.5), n_holes=2),
    Case("fractional_resolution", 8, 4, 3, 1.5, 25.0, 25.0, n_holes=2, resolution_mm=0.25),
    Case("holes_only", 6, 2, 2, 4.0, 40.0, 40.0, n_holes=4),
    # Hole centred outside the board: the disk loop must clip, not index OOB.
    Case("hole_outside_board", 6, 2, 2, 6.0, 20.0, 20.0, n_holes=1, origin=(50.0, 50.0)),
    Case(
        "keepout_rects",
        10,
        5,
        3,
        1.0,
        50.0,
        40.0,
        n_holes=1,
        keepout_rects=((5.0, 5.0, 15.0, 12.0), (-3.0, -3.0, 2.0, 2.0), (48.0, 38.0, 60.0, 60.0)),
    ),
    # Inverted rectangle (x_max < x_min): the slice is empty, not reversed.
    Case("inverted_keepout_rect", 6, 3, 2, 0.0, 30.0, 30.0, keepout_rects=((20.0, 20.0, 5.0, 5.0),)),
    Case("fixed_components", 14, 6, 4, 2.0, 60.0, 50.0, n_holes=2, fixed_every=3),
    Case(
        "explicit_thermal_and_groups",
        18,
        8,
        4,
        3.0,
        70.0,
        60.0,
        n_holes=2,
        thermal_refs=("U_MCU_1", "TP7", "NOT_IN_NETLIST"),
        group_refs=("U_BUCK_1", "U_LDO_2", "ALSO_NOT_IN_NETLIST"),
        loop_nets=("SW_NODE", "PGND", "NO_SUCH_NET"),
    ),
    Case("medium", 40, 14, 5, 4.0, 90.0, 70.0, n_holes=4, loop_nets=("SW_NODE", "VIN")),
    # --- benchmark-eligible sizes ------------------------------------------
    Case(
        "large",
        160,
        60,
        8,
        8.0,
        180.0,
        140.0,
        n_holes=6,
        fixed_every=7,
        thermal_refs=("U_MCU_1",),
        group_refs=("U_BUCK_1", "U_LDO_2"),
        loop_nets=("SW_NODE", "PGND", "VIN"),
        keepout_rects=((20.0, 20.0, 45.0, 40.0),),
    ),
    # The benchmark ceiling. Every axis here is >= every axis of any case the
    # benchmark is allowed to use, and the differential runs it.
    Case(
        "xlarge",
        400,
        150,
        10,
        20.0,
        300.0,
        260.0,
        n_holes=8,
        fixed_every=11,
        thermal_refs=("U_MCU_1", "Y1"),
        group_refs=("U_BUCK_1", "U_LDO_2", "U_SENS_3"),
        loop_nets=("SW_NODE", "PGND", "VIN", "GND"),
        keepout_rects=((20.0, 20.0, 45.0, 40.0), (100.0, 90.0, 160.0, 150.0)),
        resolution_mm=0.5,
    ),
)

CASES_BY_ID: dict[str, Case] = {c.ident: c for c in CASES}

# The benchmark may ONLY name ids from CASES. The differential asserts this.
BENCH_CASE_IDS: tuple[str, ...] = ("medium", "large", "xlarge")


def bench_cases() -> tuple[Case, ...]:
    return tuple(CASES_BY_ID[i] for i in BENCH_CASE_IDS)


# --- Builders ---------------------------------------------------------------


def _ref_at(i: int) -> str:
    base = REF_TEMPLATES[i % len(REF_TEMPLATES)]
    cycle = i // len(REF_TEMPLATES)
    return base if cycle == 0 else f"{base}_{cycle}"


def build_netlist(case: Case) -> Netlist:
    """Build the case's netlist. Deterministic; no RNG anywhere."""
    components = []
    for i in range(case.n_components):
        ref = _ref_at(i)
        fp = FOOTPRINT_TEMPLATES[i % len(FOOTPRINT_TEMPLATES)]
        if case.int_geometry:
            bounds: tuple[float, float] | tuple[int, int] = (1 + (i % 5), 1 + (i % 3))
        else:
            # Deliberately includes exact ties on width*height (e.g. 2.0*3.0
            # and 3.0*2.0 and 6.0*1.0) so the thermal size sort's tie-break
            # is exercised rather than assumed.
            bounds = (float(1 + (i % 6)), float(6 - (i % 6)))
        components.append(
            Component(
                ref=ref,
                footprint=fp,
                bounds=bounds,
                net_class="Power" if i % 4 == 0 else "Signal",
                fixed=bool(case.fixed_every and i % case.fixed_every == 0),
            )
        )

    refs = [c.ref for c in components]
    nets = []
    for k in range(case.n_nets):
        name, net_class = NET_TEMPLATES[k % len(NET_TEMPLATES)]
        if k >= len(NET_TEMPLATES):
            name = f"{name}_{k // len(NET_TEMPLATES)}"
        pins = []
        for j in range(case.pins_per_net):
            if not refs:
                break
            pins.append((refs[(k * 3 + j) % len(refs)], str(j + 1)))
        nets.append(Net(name=name, pins=pins, net_class=net_class))

    return Netlist(components=components, nets=nets)


def build_board(case: Case) -> Board:
    holes = []
    for h in range(case.n_holes):
        ox, oy = case.origin
        hx = ox + (h + 1) * case.board_w / (case.n_holes + 1)
        hy = oy + (h + 1) * case.board_h / (case.n_holes + 1)
        holes.append(
            MountingHole(
                position=(hx, hy),
                diameter=3.2,
                keepout_radius=case.keepout_radius,
            )
        )
    return Board(
        width=case.board_w,
        height=case.board_h,
        origin=case.origin,
        mounting_holes=holes,
        keepouts=list(case.keepout_rects),
    )


def build_constraints(case: Case) -> PlacementConstraints:
    kwargs: dict = {
        "board_width_mm": float(case.board_w),
        "board_height_mm": float(case.board_h),
        "board_margin_mm": case.margin_mm,
    }
    if case.thermal_refs:
        kwargs["thermal_properties"] = ThermalProperties(
            high_power_components=list(case.thermal_refs[:1]),
            thermal_pad_components=list(case.thermal_refs[1:]),
        )
        kwargs["thermal_constraints"] = [ThermalConstraint(components=list(case.thermal_refs))]
    if case.group_refs:
        kwargs["component_groups"] = [
            ComponentGroup(name="grp0", components=list(case.group_refs)),
            # An all-missing group: `valid_refs` is empty, so NO module is
            # appended -- the branch a port is most likely to get wrong.
            ComponentGroup(name="grp_absent", components=["ZZZ_MISSING"]),
        ]
    if case.loop_nets:
        kwargs["critical_loops"] = [CriticalLoop(name="loop0", nets=list(case.loop_nets))]
    return PlacementConstraints(**kwargs)


def build_all(case: Case) -> tuple[Board, Netlist, PlacementConstraints]:
    return build_board(case), build_netlist(case), build_constraints(case)
