"""Pinned pre-migration oracle for the Wave-4 Phase 2 ``core/`` contract layer.

**Do not edit.**  This is a *verbatim* copy of the compute AS COMMITTED at
``origin/main`` (``facaed149``) before the Rust contract types in
``packages/temper-io-types/src/placer_core/`` existed.  It is the
reference the R1a differential is pinned to; changing it would move the
goalposts rather than test the migration.

Copied from, in order:

* ``temper_placer/core/board.py``            -- ``Rect``
* ``temper_placer/core/units.py``            -- the eight conversions
* ``temper_placer/core/net_classification.py`` -- patterns + ten predicates
* ``temper_placer/core/manufacturing.py``    -- ``FabPreset`` + two functions
* ``temper_placer/core/placement_drc.py``    -- ``PinInfo``,
  ``PlacementViolation``, ``validate_placement_drc``
* ``temper_placer/core/netlist.py``          -- ``build_adjacency_matrix``

Only pure compute is copied.  Nothing here imports the production
modules, so the oracle keeps working after they start delegating.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# board.Rect
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Rect:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        if not (self.x_max > self.x_min):
            raise ValueError(
                f"Rect requires x_max > x_min, got x_min={self.x_min}, "
                f"x_max={self.x_max}. If you have (x, y, width, height) "
                f"bounds, build with Rect.from_xywh(...)."
            )
        if not (self.y_max > self.y_min):
            raise ValueError(
                f"Rect requires y_max > y_min, got y_min={self.y_min}, "
                f"y_max={self.y_max}. If you have (x, y, width, height) "
                f"bounds, build with Rect.from_xywh(...)."
            )

    @classmethod
    def from_xyxy(cls, x_min: float, y_min: float, x_max: float, y_max: float) -> Rect:
        return cls(float(x_min), float(y_min), float(x_max), float(y_max))

    @classmethod
    def from_xywh(cls, x: float, y: float, width: float, height: float) -> Rect:
        return cls(float(x), float(y), float(x) + float(width), float(y) + float(height))

    @classmethod
    def coerce(cls, value: Rect | tuple[float, float, float, float]) -> Rect:
        if isinstance(value, cls):
            return value
        x_min, y_min, x_max, y_max = value
        return cls.from_xyxy(x_min, y_min, x_max, y_max)

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    def __iter__(self):
        yield self.x_min
        yield self.y_min
        yield self.x_max
        yield self.y_max

    def __getitem__(self, index: int) -> float:
        return (self.x_min, self.y_min, self.x_max, self.y_max)[index]

    def __len__(self) -> int:
        return 4

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Rect):
            other = (other.x_min, other.y_min, other.x_max, other.y_max)
        if isinstance(other, (tuple, list)) and len(other) == 4:
            return (self.x_min, self.y_min, self.x_max, self.y_max) == tuple(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.x_min, self.y_min, self.x_max, self.y_max))


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------


def deg_to_rad(degrees):
    """Convert degrees to radians."""
    return degrees * np.pi / 180.0


def rad_to_deg(radians):
    """Convert radians to degrees."""
    return radians * 180.0 / np.pi


def mm_to_cell(mm, cell_size_mm):
    return int(mm / cell_size_mm)


def cell_to_mm(cell, cell_size_mm):
    return cell * cell_size_mm


def distance_mm(x1, y1, x2, y2):
    import math

    dx = x2 - x1
    dy = y2 - y1
    return math.sqrt(dx * dx + dy * dy)


def manhattan_distance_mm(x1, y1, x2, y2):
    return abs(x2 - x1) + abs(y2 - y1)


def is_valid_layer(layer, max_layers: int = 4) -> bool:
    return 0 <= layer < max_layers


def is_valid_net_id(net_id) -> bool:
    return net_id >= 0


# ---------------------------------------------------------------------------
# net_classification
# ---------------------------------------------------------------------------

GROUND_NET_PATTERNS: frozenset[str] = frozenset({"GND", "PGND", "CGND", "AGND", "DGND", "VSS"})
POWER_NET_PATTERNS: frozenset[str] = frozenset(
    {"+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"}
)
HV_NET_PATTERNS: frozenset[str] = frozenset({"AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"})

GROUND_PIN_PATTERNS: frozenset[str] = frozenset({"GND", "VSS", "AGND", "DGND", "PGND", "CGND"})
POWER_PIN_PATTERNS: frozenset[str] = frozenset({"VCC", "VDD", "VIN", "VOUT", "PVCC", "VBUS", "PWR"})
HV_PIN_PATTERNS: frozenset[str] = frozenset({"AC_L", "AC_N", "PE", "HV", "MAINS", "RECT"})
CLOCK_PIN_PATTERNS: frozenset[str] = frozenset(
    {"CLK", "CLOCK", "XTAL1", "XTAL2", "OSC_IN", "OSC_OUT"}
)


def _matches_any(name: str, patterns: frozenset[str]) -> bool:
    upper = name.upper()
    for p in patterns:
        escaped = re.escape(p)
        if p and not p[-1].isalnum():
            if re.search(rf"(?:^|_){escaped}", upper):
                return True
        elif re.search(rf"(?:^|_){escaped}(?:$|[\d_])", upper):
            return True
    return False


def is_ground_net(name: str) -> bool:
    return _matches_any(name, GROUND_NET_PATTERNS)


def is_power_net(name: str) -> bool:
    return _matches_any(name, POWER_NET_PATTERNS)


def is_hv_net(name: str) -> bool:
    return _matches_any(name, HV_NET_PATTERNS)


def is_signal_net(name: str) -> bool:
    return not (is_ground_net(name) or is_power_net(name) or is_hv_net(name))


def classify_net_type(name: str) -> str:
    if is_ground_net(name):
        return "ground"
    if is_power_net(name):
        return "power"
    if is_hv_net(name):
        return "hv"
    return "signal"


def is_ground_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, GROUND_PIN_PATTERNS)


def is_power_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, POWER_PIN_PATTERNS)


def is_hv_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, HV_PIN_PATTERNS)


def is_clock_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, CLOCK_PIN_PATTERNS)


# ---------------------------------------------------------------------------
# manufacturing
# ---------------------------------------------------------------------------


@dataclass
class FabPreset:
    """Manufacturing capabilities and tolerances for a specific fab process."""

    name: str
    trace_width_pct: float = 0.15
    min_trace_mm: float = 0.127
    min_clearance_mm: float = 0.127
    etch_undercut_mm: float = 0.05
    layer_registration_mm: float = 0.1
    drill_tolerance_mm: float = 0.05

    @classmethod
    def jlcpcb_standard(cls) -> FabPreset:
        return cls(
            name="jlcpcb_standard",
            trace_width_pct=0.15,
            min_trace_mm=0.127,
            min_clearance_mm=0.127,
            etch_undercut_mm=0.05,
            layer_registration_mm=0.1,
        )

    @classmethod
    def jlcpcb_hdi(cls) -> FabPreset:
        return cls(
            name="jlcpcb_hdi",
            trace_width_pct=0.10,
            min_trace_mm=0.075,
            min_clearance_mm=0.075,
            etch_undercut_mm=0.03,
            layer_registration_mm=0.05,
        )

    @classmethod
    def oshpark(cls) -> FabPreset:
        return cls(
            name="oshpark",
            trace_width_pct=0.12,
            min_trace_mm=0.152,
            min_clearance_mm=0.152,
            etch_undercut_mm=0.04,
        )


def get_fab_presets() -> dict[str, FabPreset]:
    return {
        "jlcpcb_standard": FabPreset.jlcpcb_standard(),
        "jlcpcb_hdi": FabPreset.jlcpcb_hdi(),
        "oshpark": FabPreset.oshpark(),
    }


def inflated_clearance(nominal: float, tolerance: float = 0.1) -> float:
    return max(0.0, nominal - tolerance)


def inflated_width(nominal: float, tolerance: float = 0.1) -> float:
    return nominal + tolerance


# ---------------------------------------------------------------------------
# placement_drc
# ---------------------------------------------------------------------------


@dataclass
class PinInfo:
    x: float
    y: float
    net_name: str
    component_name: str
    pin_name: str
    diameter_mm: float = 1.0

    @property
    def radius(self) -> float:
        return self.diameter_mm / 2.0


@dataclass
class PlacementViolation:
    item_a: PinInfo
    item_b: PinInfo
    distance: float
    required: float
    violation_type: str
    message: str


def validate_placement_drc(
    pins: list[PinInfo], min_clearance_mm: float, _trace_width_mm: float = 0.25
) -> list[PlacementViolation]:
    violations = []

    n = len(pins)
    for i in range(n):
        for j in range(i + 1, n):
            pin_a = pins[i]
            pin_b = pins[j]

            if pin_a.net_name == pin_b.net_name:
                continue

            dx = pin_a.x - pin_b.x
            dy = pin_a.y - pin_b.y
            dist = math.sqrt(dx * dx + dy * dy)

            pad_r_sum = pin_a.radius + pin_b.radius

            if dist < pad_r_sum:
                violations.append(
                    PlacementViolation(
                        item_a=pin_a,
                        item_b=pin_b,
                        distance=dist,
                        required=pad_r_sum,
                        violation_type="SHORT",
                        message=f"Pads overlapping! {pin_a.net_name} vs {pin_b.net_name}",
                    )
                )
                continue

            required_clearance = pad_r_sum + min_clearance_mm
            if dist < required_clearance:
                violations.append(
                    PlacementViolation(
                        item_a=pin_a,
                        item_b=pin_b,
                        distance=dist,
                        required=required_clearance,
                        violation_type="CLEARANCE",
                        message=f"Clearance violation! Dist {dist:.3f}mm < {required_clearance:.3f}mm",
                    )
                )
                continue

    return violations


# ---------------------------------------------------------------------------
# netlist.build_adjacency_matrix
#
# The oracle takes the two projections the kernel needs rather than a whole
# Netlist, so it does not have to duplicate Netlist/Component/Net (which are
# not migrated).  The projections are exactly what the reference reads:
# ``[c.ref for c in netlist.components]`` and, per net,
# ``[comp_ref for comp_ref, _ in net.pins]``.
# ---------------------------------------------------------------------------


@dataclass
class _OracleNet:
    pins: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _OracleComponent:
    ref: str


@dataclass
class _OracleNetlist:
    components: list[_OracleComponent] = field(default_factory=list)
    nets: list[_OracleNet] = field(default_factory=list)


def make_oracle_netlist(component_refs: list[str], net_pin_refs: list[list[str]]):
    return _OracleNetlist(
        components=[_OracleComponent(r) for r in component_refs],
        nets=[_OracleNet(pins=[(r, "1") for r in pins]) for pins in net_pin_refs],
    )


def build_adjacency_matrix(netlist):
    import numpy as np

    n = len(netlist.components)

    if n == 0:
        return np.array([]).reshape(0, 0)

    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    adj = np.zeros((n, n), dtype=np.float32)

    for net in netlist.nets:
        comp_indices = []
        for comp_ref, _ in net.pins:
            if comp_ref in ref_to_idx:
                comp_indices.append(ref_to_idx[comp_ref])

        comp_indices = list(set(comp_indices))

        for i in range(len(comp_indices)):
            for j in range(i + 1, len(comp_indices)):
                idx_i = comp_indices[i]
                idx_j = comp_indices[j]

                adj[idx_i, idx_j] += 1
                adj[idx_j, idx_i] += 1

    return np.array(adj)
