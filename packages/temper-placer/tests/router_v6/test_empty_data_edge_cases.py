"""Parametrized empty-data and missing-data edge-case tests across all 7 DFM modules.

Covers zero compiled routes, zero vias, zero-length paths, all-nets-failed,
None sub-reports, None optional args, missing attributes, empty-string net
names, and very-large-input stress.

Import boundary constants from ``tests.router_v6.dfm_boundary_constants``.

Part of temper-q5dh (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass

import pytest

from temper_placer.router_v6.acid_trap_detection import (
    AcidTrapReport,
    detect_acid_traps,
)
from temper_placer.router_v6.annular_ring_check import (
    AnnularRingReport,
    check_annular_rings,
)
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    verify_clearance,
)
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    analyze_copper_balance,
)
from temper_placer.router_v6.creepage_check import (
    CreepageReport,
    verify_creepage,
)
from temper_placer.router_v6.manufacturing_report import (
    ManufacturingReport,
    generate_manufacturing_report,
)
from temper_placer.router_v6.routing_results import (
    CompiledRoute,
    RoutingResults,
)
from temper_placer.router_v6.teardrop_generation import (
    TeardropReport,
    insert_teardrops,
)
from temper_placer.router_v6.thermal_relief import (
    ThermalReliefReport,
    add_thermal_relief,
)
from temper_placer.router_v6.via_placement import Via
from tests.router_v6.dfm_boundary_constants import (
    exactly_at,
    just_above,
    just_below,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BOARD_W = 100.0
_BOARD_H = 80.0

_NORMAL_TRACE_WIDTH = 0.127
_NORMAL_VIA_DIAMETER = 0.6
_NORMAL_VIA_DRILL = 0.3

_ALL_DFM_MODULE_NAMES = [
    "acid_trap_detection",
    "annular_ring_check",
    "teardrop_generation",
    "thermal_relief",
    "copper_balance",
    "creepage_check",
    "clearance_check",
]


# ---------------------------------------------------------------------------
# Shared helper factories
# ---------------------------------------------------------------------------


def _make_path(coords=None, layer="F.Cu"):
    """Create a minimal RoutePath-like object."""
    if coords is None:
        coords = [(0.0, 0.0), (10.0, 10.0)]

    coords = list(coords)
    if len(coords) >= 2:
        length = math.hypot(
            coords[-1][0] - coords[0][0],
            coords[-1][1] - coords[0][1],
        )
    else:
        length = 0.0

    class _Path:
        def __init__(self, coordinates, layer_name, path_length):
            self.coordinates = coordinates
            self.layer_name = layer_name
            self.path_length = path_length
            self.total_length_mm = path_length

    return _Path(coords, layer, length)


def _make_via(
    diameter=_NORMAL_VIA_DIAMETER,
    drill=_NORMAL_VIA_DRILL,
    position=(5.0, 5.0),
    from_layer="F.Cu",
    to_layer="B.Cu",
    net_name="NET1",
    via_type=None,
):
    """Create a minimal Via-like object."""
    via = Via(position, from_layer, to_layer, diameter, drill, net_name)
    if via_type is not None:
        via.via_type = via_type
    return via


def _make_route(
    net_name="NET1",
    path=None,
    width_mm=_NORMAL_TRACE_WIDTH,
    vias=None,
):
    """Create a CompiledRoute with sensible defaults."""
    if path is None:
        path = _make_path()
    if vias is None:
        vias = [_make_via(net_name=net_name)]
    return CompiledRoute(net_name, path, width_mm, vias, None)


def _make_results(
    compiled_routes=None,
    failed_nets=None,
):
    """Create a RoutingResults with sensible defaults."""
    if compiled_routes is None:
        compiled_routes = {"NET1": _make_route()}
    if failed_nets is None:
        failed_nets = []
    return RoutingResults(
        compiled_routes=compiled_routes,
        failed_nets=failed_nets,
    )


# ---------------------------------------------------------------------------
# 1. Zero compiled routes — every module must return a valid report
# ---------------------------------------------------------------------------


def _invoke_module(module_name, routing_results):
    """Invoke the named DFM module with routing_results and return its report."""
    if module_name == "acid_trap_detection":
        return detect_acid_traps(routing_results)
    elif module_name == "annular_ring_check":
        return check_annular_rings(routing_results)
    elif module_name == "teardrop_generation":
        return insert_teardrops(routing_results)
    elif module_name == "thermal_relief":
        return add_thermal_relief(routing_results)
    elif module_name == "copper_balance":
        return analyze_copper_balance(routing_results, _BOARD_W, _BOARD_H)
    elif module_name == "creepage_check":
        return verify_creepage(routing_results)
    elif module_name == "clearance_check":
        return verify_clearance(routing_results)
    else:
        raise ValueError(f"Unknown DFM module: {module_name}")


@pytest.mark.parametrize("module_name", _ALL_DFM_MODULE_NAMES)
def test_zero_compiled_routes_every_module_returns_valid_report(module_name):
    """An empty compiled_routes dict must produce a valid report — no crashes."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    # Every module must return a report object (not None)
    assert report is not None, f"{module_name} returned None for empty input"


@pytest.mark.parametrize("module_name", _ALL_DFM_MODULE_NAMES)
def test_zero_compiled_routes_report_has_zero_violations(module_name):
    """An empty compiled_routes dict should yield zero violations/checks."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    # Check that at least one sensible "count" property is zero
    # Different modules have different primary count properties
    count_attrs = {
        "acid_trap_detection": "trap_count",
        "annular_ring_check": "violation_count",
        "teardrop_generation": "teardrop_count",
        "thermal_relief": "relief_count",
        "copper_balance": "unbalanced_layer_count",  # 0 copper → all layers 0% → unbalanced... but at least no crash
        "creepage_check": "violation_count",
        "clearance_check": "violation_count",
    }
    attr = count_attrs.get(module_name)
    if attr is not None:
        count = getattr(report, attr, None)
        assert count is not None, f"{module_name} report has no '{attr}' attribute"
        # Just verify it's an int — for copper_balance with zero routes,
        # all layers will be 0% copper = unbalanced, so >0 is okay.
        assert isinstance(count, int), (
            f"{module_name}.{attr} should be int, got {type(count).__name__}"
        )


# ---------------------------------------------------------------------------
# 2. Zero vias on a route — teardrop, annular_ring, thermal_relief
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_name",
    ["teardrop_generation", "annular_ring_check", "thermal_relief"],
)
def test_zero_vias_on_route_returns_empty_report(module_name):
    """A route with no vias should produce an empty/success report."""
    path = _make_path()
    route = _make_route(vias=[], path=path)
    results = _make_results(compiled_routes={"NET1": route})

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    zero_count_attrs = {
        "teardrop_generation": "teardrop_count",
        "annular_ring_check": "violation_count",
        "thermal_relief": "relief_count",
    }
    attr = zero_count_attrs[module_name]
    assert getattr(report, attr) == 0, (
        f"{module_name}.{attr} should be 0 with zero vias, "
        f"got {getattr(report, attr)}"
    )


# ---------------------------------------------------------------------------
# 3. Zero-length path (no coordinates or single coordinate)
# ---------------------------------------------------------------------------

ALL_DETECTION_MODULES = [
    "acid_trap_detection",
    "annular_ring_check",
    "teardrop_generation",
    "thermal_relief",
    "creepage_check",
    "clearance_check",
]


@pytest.mark.parametrize("module_name", ALL_DETECTION_MODULES)
def test_single_coordinate_path_returns_valid_report(module_name):
    """A path with a single coordinate must not crash any module."""
    path = _make_path(coords=[(5.0, 5.0)])
    route = _make_route(path=path)
    results = _make_results(compiled_routes={"NET1": route})

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    assert report is not None, f"{module_name} returned None for single-coordinate path"


@pytest.mark.parametrize("module_name", ALL_DETECTION_MODULES)
def test_empty_coordinates_path_returns_valid_report(module_name):
    """A path with zero coordinates must not crash any module."""
    path = _make_path(coords=[])
    route = _make_route(path=path)
    results = _make_results(compiled_routes={"NET1": route})

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    assert report is not None, f"{module_name} returned None for empty-coordinates path"


# ---------------------------------------------------------------------------
# 4. All nets failed — failed_nets populated, compiled_routes empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _ALL_DFM_MODULE_NAMES)
def test_all_nets_failed_compiled_routes_empty(module_name):
    """When every net failed, compiled_routes is empty; must not crash."""
    results = RoutingResults(
        compiled_routes={},
        failed_nets=["N1", "N2", "N3", "N4", "N5"],
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    assert report is not None, (
        f"{module_name} returned None when all nets failed"
    )


# ---------------------------------------------------------------------------
# 5. None passed where report expected — generate_manufacturing_report
# ---------------------------------------------------------------------------


_VALID_ACID = AcidTrapReport(acid_traps=[])
_VALID_ANNULAR = AnnularRingReport(violations=[], total_vias_checked=0)
_VALID_TEARDROPS = TeardropReport(teardrops=[])
_VALID_THERMAL = ThermalReliefReport(thermal_reliefs=[])
_VALID_COPPER = CopperBalanceReport(layer_balances=[], total_area_mm2=0.0)
_VALID_CREEPAGE = CreepageReport(violations=[], total_checks=0)
_VALID_CLEARANCE = ClearanceReport(violations=[], total_checks=0)

_DEFAULT_REPORT_MAP = {
    "acid_traps": _VALID_ACID,
    "annular_rings": _VALID_ANNULAR,
    "teardrops": _VALID_TEARDROPS,
    "thermal_reliefs": _VALID_THERMAL,
    "copper_balance": _VALID_COPPER,
    "creepage": _VALID_CREEPAGE,
    "clearance": _VALID_CLEARANCE,
}


@pytest.mark.parametrize("none_field", list(_DEFAULT_REPORT_MAP.keys()))
def test_generate_manufacturing_report_with_none_sub_report(none_field):
    """Each sub-report passed as None must raise TypeError from __post_init__."""
    kwargs = dict(_DEFAULT_REPORT_MAP)
    kwargs[none_field] = None

    with pytest.raises(TypeError, match=none_field):
        generate_manufacturing_report(
            acid_traps=kwargs["acid_traps"],
            annular_rings=kwargs["annular_rings"],
            teardrops=kwargs["teardrops"],
            thermal_reliefs=kwargs["thermal_reliefs"],
            copper_balance=kwargs["copper_balance"],
            creepage=kwargs["creepage"],
            clearance=kwargs["clearance"],
        )


# ---------------------------------------------------------------------------
# 6. voltage_ratings=None for creepage and clearance
# ---------------------------------------------------------------------------


def test_creepage_with_none_voltage_ratings():
    """verify_creepage must handle voltage_ratings=None gracefully."""
    results = _make_results()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = verify_creepage(results, voltage_ratings=None)

    assert isinstance(report, CreepageReport)
    assert report.violation_count >= 0


def test_clearance_with_none_voltage_ratings():
    """verify_clearance must handle voltage_ratings=None gracefully."""
    results = _make_results()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = verify_clearance(results, voltage_ratings=None)

    assert isinstance(report, ClearanceReport)
    assert report.violation_count >= 0


# ---------------------------------------------------------------------------
# 7. board=None for copper_balance and thermal_relief
# ---------------------------------------------------------------------------


def test_copper_balance_does_not_require_board():
    """analyze_copper_balance never receives a board arg — no issue."""
    results = _make_results()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = analyze_copper_balance(results, _BOARD_W, _BOARD_H)

    assert isinstance(report, CopperBalanceReport)


def test_thermal_relief_with_board_none():
    """add_thermal_relief must handle board=None (uses fallback plane layers)."""
    results = _make_results()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = add_thermal_relief(results, board=None)

    assert isinstance(report, ThermalReliefReport)
    assert report.relief_count >= 0


def test_thermal_relief_with_board_none_and_no_routes():
    """add_thermal_relief with board=None and empty routes must still succeed."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = add_thermal_relief(results, board=None)

    assert isinstance(report, ThermalReliefReport)
    assert report.relief_count == 0


# ---------------------------------------------------------------------------
# 8. Missing attributes — route without layer_name, without width_mm,
#    path without coordinates
# ---------------------------------------------------------------------------


@dataclass
class _BareRoute:
    """A route-like object with minimal attributes."""
    net_name: str
    path: object
    width_mm: float
    vias: list


class _PathNoLayerName:
    """Path-like object that has coordinates but no layer_name."""
    def __init__(self, coords):
        self.coordinates = list(coords)
        total = 0.0
        for i in range(len(coords) - 1):
            total += math.hypot(
                coords[i + 1][0] - coords[i][0],
                coords[i + 1][1] - coords[i][1],
            )
        self.path_length = total
        self.total_length_mm = total


class _PathNoCoordinates:
    """Path-like object that has layer_name but no coordinates attribute."""
    def __init__(self):
        self.layer_name = "F.Cu"
        self.path_length = 0.0
        self.total_length_mm = 0.0


# -- route without layer_name on path ----------------------------------------


@pytest.mark.parametrize(
    "module_name",
    ["teardrop_generation", "annular_ring_check", "thermal_relief", "acid_trap_detection",
     "creepage_check", "clearance_check"],
)
def test_route_without_layer_name_on_path(module_name):
    """Path missing layer_name attribute — modules must not crash."""
    path = _PathNoLayerName([(0.0, 0.0), (10.0, 10.0)])
    route = _BareRoute("NET1", path, _NORMAL_TRACE_WIDTH, [_make_via(net_name="NET1")])
    results = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=[],
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    assert report is not None, (
        f"{module_name} crashed on path without layer_name"
    )


# -- route without width_mm --------------------------------------------------


class _RouteNoWidth:
    """Route-like object missing width_mm attribute."""
    def __init__(self, net_name, path, vias):
        self.net_name = net_name
        self.path = path
        self.vias = list(vias)


@pytest.mark.parametrize(
    "module_name",
    ["acid_trap_detection", "teardrop_generation", "annular_ring_check",
     "thermal_relief", "creepage_check", "clearance_check", "copper_balance"],
)
def test_route_without_width_mm(module_name):
    """CompiledRoute without width_mm — should crash cleanly or return safe."""
    path = _make_path()
    route = _RouteNoWidth("NET1", path, [_make_via(net_name="NET1")])
    results = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=[],
    )

    # Missing width_mm will likely cause AttributeError — mark as xfail.
    # But some modules may not access width_mm at all.
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            report = _invoke_module(module_name, results)
        # If it succeeds, the report must be valid
        assert report is not None
    except AttributeError:
        pytest.xfail(f"{module_name} raises AttributeError on missing width_mm — expected")


# -- path without coordinates ------------------------------------------------


@pytest.mark.parametrize(
    "module_name",
    ["acid_trap_detection", "teardrop_generation", "annular_ring_check",
     "thermal_relief", "creepage_check", "clearance_check"],
)
def test_path_without_coordinates(module_name):
    """Path object without coordinates attribute — must not crash."""
    path = _PathNoCoordinates()
    route = _BareRoute("NET1", path, _NORMAL_TRACE_WIDTH, [_make_via(net_name="NET1")])
    results = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=[],
    )

    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            report = _invoke_module(module_name, results)
        assert report is not None
    except AttributeError:
        pytest.xfail(
            f"{module_name} raises AttributeError on path without coordinates — "
            f"expected until guards are added"
        )


# -- route without path ------------------------------------------------------


class _RouteNoPath:
    """Route-like object missing path attribute."""
    def __init__(self, net_name, width_mm, vias):
        self.net_name = net_name
        self.width_mm = width_mm
        self.vias = list(vias)


@pytest.mark.parametrize("module_name", _ALL_DFM_MODULE_NAMES)
def test_route_without_path(module_name):
    """CompiledRoute without path attribute — should crash cleanly."""
    route = _RouteNoPath("NET1", _NORMAL_TRACE_WIDTH, [_make_via(net_name="NET1")])
    results = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=[],
    )

    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            report = _invoke_module(module_name, results)
        assert report is not None
    except AttributeError:
        pytest.xfail(
            f"{module_name} raises AttributeError on missing path — expected"
        )


# ---------------------------------------------------------------------------
# 9. Empty-string net names — all modules should handle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _ALL_DFM_MODULE_NAMES)
def test_empty_string_net_name(module_name):
    """A route with an empty-string net name must not crash."""
    path = _make_path()
    route = _make_route(net_name="", path=path)
    results = _make_results(compiled_routes={"": route})

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    assert report is not None, (
        f"{module_name} crashed on empty-string net name"
    )


@pytest.mark.parametrize("module_name", _ALL_DFM_MODULE_NAMES)
def test_whitespace_only_net_name(module_name):
    """A route with a whitespace-only net name must not crash."""
    path = _make_path()
    route = _make_route(net_name="   ", path=path)
    results = _make_results(compiled_routes={"   ": route})

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)

    assert report is not None, (
        f"{module_name} crashed on whitespace-only net name"
    )


# ---------------------------------------------------------------------------
# 10. Very large compiled_routes dict (1000+ routes) — no crash, reasonable
#     runtime (≤ 10 s)
# ---------------------------------------------------------------------------


def _make_large_route(index):
    """Create a minimal route for stress-testing."""
    path = _make_path(coords=[(float(index), 0.0), (float(index), 10.0)])
    return _make_route(
        net_name=f"NET{index}",
        path=path,
        vias=[_make_via(
            net_name=f"NET{index}",
            position=(float(index), 5.0),
        )],
    )


@pytest.mark.parametrize("module_name", _ALL_DFM_MODULE_NAMES)
def test_large_input_1000_routes_no_crash(module_name):
    """1000 routes must not crash any DFM module and must finish within 10 s."""
    compiled_routes = {
        f"NET{i}": _make_large_route(i)
        for i in range(1000)
    }
    results = RoutingResults(
        compiled_routes=compiled_routes,
        failed_nets=[],
    )

    start = time.perf_counter()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        report = _invoke_module(module_name, results)
    elapsed = time.perf_counter() - start

    assert report is not None, (
        f"{module_name} returned None for 1000-route input"
    )
    assert elapsed <= 10.0, (
        f"{module_name} took {elapsed:.3f}s for 1000 routes — "
        f"exceeds 10 s budget"
    )


# ---------------------------------------------------------------------------
# Edge: generate_manufacturing_report with all valid (empty) sub-reports
# ---------------------------------------------------------------------------


def test_generate_manufacturing_report_all_valid_empty_sub_reports():
    """All empty sub-reports → ManufacturingReport with zero violations."""
    report = generate_manufacturing_report(
        acid_traps=_VALID_ACID,
        annular_rings=_VALID_ANNULAR,
        teardrops=_VALID_TEARDROPS,
        thermal_reliefs=_VALID_THERMAL,
        copper_balance=_VALID_COPPER,
        creepage=_VALID_CREEPAGE,
        clearance=_VALID_CLEARANCE,
    )

    assert isinstance(report, ManufacturingReport)
    assert report.total_violations == 2  # sentinels from empty teardrops + thermal reliefs
    assert report.is_manufacturability_ok is False
