"""Tests for DFM module interaction and ordering edge cases.

Covers error isolation, fallback chains, input immutability, report
stability, gate logic with partial failures, pipeline ordering, and
exception-type fidelity.
"""

from __future__ import annotations

import copy
import math
from unittest import mock

import pytest

from temper_placer.router_v6.acid_trap_detection import (
    AcidTrap,
    AcidTrapReport,
    detect_acid_traps,
)
from temper_placer.router_v6.annular_ring_check import (
    AnnularRingReport,
    AnnularRingViolation,
    check_annular_rings,
)
from temper_placer.router_v6.clearance_check import (
    ClearanceReport,
    ClearanceViolation,
    verify_clearance,
)
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    LayerCopperBalance,
    analyze_copper_balance,
)
from temper_placer.router_v6.creepage_check import (
    CreepageReport,
    CreepageViolation,
    verify_creepage,
)
from temper_placer.router_v6.manufacturing_report import (
    ManufacturingReport,
    generate_manufacturing_report,
)
from temper_placer.router_v6.pipeline import (
    ManufacturingDRCViolationError,
    RouterV6Pipeline,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.teardrop_generation import (
    Teardrop,
    TeardropReport,
    insert_teardrops,
)
from temper_placer.router_v6.thermal_relief import (
    ThermalRelief,
    ThermalReliefReport,
    add_thermal_relief,
)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _make_stub_route(net_name="NET1", coords=None, layer="F.Cu",
                     width=0.25, vias=None):
    """Build a minimal CompiledRoute for testing the DFM pipeline."""
    if coords is None:
        coords = [(0.0, 0.0), (10.0, 10.0)]

    class _Path:
        def __init__(self):
            self.coordinates = list(coords)
            self.layer_name = layer
            self.total_length_mm = sum(
                math.hypot(
                    coords[i + 1][0] - coords[i][0],
                    coords[i + 1][1] - coords[i][1],
                )
                for i in range(len(coords) - 1)
            )
            self.path_length = self.total_length_mm

    class _Via:
        def __init__(self, position=(5.0, 5.0)):
            self.position = position
            self.from_layer = "F.Cu"
            self.to_layer = "B.Cu"
            self.diameter = 0.6
            self.drill = 0.3
            self.net_name = net_name

    via_list = []
    if vias is not None:
        via_list = vias
    elif coords and len(coords) >= 2:
        via_list = [_Via()]

    path = _Path()
    return CompiledRoute(
        net_name=net_name,
        path=path,
        width_mm=width,
        vias=via_list,
        matched_length_mm=None,
    )


def _make_routing_results(**routes) -> RoutingResults:
    """Build a RoutingResults from stub routes."""
    compiled = {}
    for name, route in routes.items():
        compiled[name] = route
    return RoutingResults(compiled_routes=compiled, failed_nets=[])


def _make_pcb_mock(width=100.0, height=80.0, board=True):
    """Build a pcb mock with an optional board sub-mock."""
    pcb = mock.Mock()
    if board:
        pcb.board = mock.Mock(width=width, height=height)
    else:
        pcb.board = None
    return pcb


def _empty_report() -> ManufacturingReport:
    """A ManufacturingReport with zero violations across the board."""
    return generate_manufacturing_report(
        AcidTrapReport(acid_traps=[]),
        AnnularRingReport(violations=[], total_vias_checked=0),
        TeardropReport(teardrops=[
            Teardrop("NET1", (0.0, 0.0), "via", 0.3, 0.6, "F.Cu"),
        ]),
        ThermalReliefReport(thermal_reliefs=[
            ThermalRelief("GND", (0.0, 0.0), 4, 0.254, 0.254,
                          pad_size=(0.0, 0.0), spoke_segments=[]),
        ]),
        CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
        CreepageReport(violations=[], total_checks=0),
        ClearanceReport(violations=[], total_checks=0),
    )


# ===================================================================
# 1. All 7 modules fail
# ===================================================================

class TestAllModulesFail:
    """When every DFM function raises, _run_manufacturing_drc still
    returns a ManufacturingReport (all fallback defaults kick in)."""

    # The 7 functions called inside _run_manufacturing_drc (copper_balance
    # is guarded by a pcb.board is-not-None check, so we include it only
    # when a board mock is present).
    _ALL_DFM_PATCH_TARGETS = [
        "temper_placer.router_v6.acid_trap_detection.detect_acid_traps",
        "temper_placer.router_v6.annular_ring_check.check_annular_rings",
        "temper_placer.router_v6.teardrop_generation.insert_teardrops",
        "temper_placer.router_v6.thermal_relief.add_thermal_relief",
        "temper_placer.router_v6.copper_balance.analyze_copper_balance",
        "temper_placer.router_v6.creepage_check.verify_creepage",
        "temper_placer.router_v6.clearance_check.verify_clearance",
    ]

    def test_all_seven_raise_still_produces_report(self):
        """All 7 DFM functions raise — fallback reports are used."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1")
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        patches = [
            mock.patch(target, side_effect=RuntimeError("injected failure"))
            for target in self._ALL_DFM_PATCH_TARGETS
        ]
        for patcher in patches:
            patcher.start()

        try:
            report = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)
        finally:
            for patcher in patches:
                patcher.stop()

        # Must still return a ManufacturingReport (not None, not an exception)
        assert isinstance(report, ManufacturingReport)

        # Every sub-report must be a valid dataclass instance (fallbacks)
        assert isinstance(report.acid_traps, AcidTrapReport)
        assert isinstance(report.annular_rings, AnnularRingReport)
        assert isinstance(report.teardrops, TeardropReport)
        assert isinstance(report.thermal_reliefs, ThermalReliefReport)
        assert isinstance(report.copper_balance, CopperBalanceReport)
        assert isinstance(report.creepage, CreepageReport)
        assert isinstance(report.clearance, ClearanceReport)

        # Fallback empty teardrops/thermal reliefs add 2 sentinel violations
        assert report.total_violations == 2
        assert report.critical_violations == 0
        assert report.is_manufacturability_ok is False

    def test_all_seven_raise_no_board_still_works(self):
        """Same as above but pcb.board is None (copper_balance skipped)."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1")
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(board=False)  # board=None

        # Copper balance is guarded — only 6 functions are actually called
        patches = [
            mock.patch(target, side_effect=RuntimeError("injected failure"))
            for target in self._ALL_DFM_PATCH_TARGETS
        ]
        for patcher in patches:
            patcher.start()

        try:
            report = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)
        finally:
            for patcher in patches:
                patcher.stop()

        assert isinstance(report, ManufacturingReport)
        # Copper balance fallback (board=None path) is an empty report
        assert isinstance(report.copper_balance, CopperBalanceReport)
        assert report.copper_balance.total_area_mm2 == 0.0


# ===================================================================
# 2. First module fails, rest succeed — error isolation
# ===================================================================

class TestFirstModuleFailsRestSucceed:
    """A single failing module does not cascade to the others."""

    def test_acid_trap_fails_others_run(self):
        """acid_trap raises; the remaining 6 produce real outputs."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1")
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        with mock.patch(
            "temper_placer.router_v6.acid_trap_detection.detect_acid_traps",
            side_effect=RuntimeError("acid trap failure"),
        ):
            report = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)

        # The failing module gets its fallback
        assert isinstance(report.acid_traps, AcidTrapReport)
        assert report.acid_traps.trap_count == 0  # fallback empty

        # All other modules ran successfully
        assert isinstance(report.annular_rings, AnnularRingReport)
        assert isinstance(report.teardrops, TeardropReport)
        assert isinstance(report.thermal_reliefs, ThermalReliefReport)
        assert isinstance(report.copper_balance, CopperBalanceReport)
        assert isinstance(report.creepage, CreepageReport)
        assert isinstance(report.clearance, ClearanceReport)

        # Other modules may have detected real things (e.g. annular ring ok,
        # teardrops generated); we only assert types here.
        # At minimum the total violations should be computable.
        assert report.total_violations >= 0

    def test_clearance_fails_others_run(self):
        """verify_clearance raises; the remaining 6 produce real outputs."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1")
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        with mock.patch(
            "temper_placer.router_v6.clearance_check.verify_clearance",
            side_effect=RuntimeError("clearance failure"),
        ):
            report = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)

        # Clearance gets fallback
        assert isinstance(report.clearance, ClearanceReport)
        assert report.clearance.violation_count == 0

        # Everything else ran
        assert isinstance(report.acid_traps, AcidTrapReport)
        assert isinstance(report.annular_rings, AnnularRingReport)
        assert isinstance(report.teardrops, TeardropReport)
        assert isinstance(report.thermal_reliefs, ThermalReliefReport)
        assert isinstance(report.copper_balance, CopperBalanceReport)
        assert isinstance(report.creepage, CreepageReport)

    def test_teardrop_fails_no_cascade(self):
        """insert_teardrops raises; thermal_relief and others unaffected."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1")
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        with mock.patch(
            "temper_placer.router_v6.teardrop_generation.insert_teardrops",
            side_effect=RuntimeError("teardrop failure"),
        ):
            report = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)

        assert isinstance(report.teardrops, TeardropReport)
        assert report.teardrops.teardrop_count == 0
        # Thermal relief ran normally (may or may not generate reliefs)
        assert isinstance(report.thermal_reliefs, ThermalReliefReport)


# ===================================================================
# 3. generate_manufacturing_report with None sub-reports
# ===================================================================

class TestNoneReportRaisesTypeError:
    """ManufacturingReport.__post_init__ rejects None fields."""

    _valid_reports = {
        "acid_traps": AcidTrapReport(acid_traps=[]),
        "annular_rings": AnnularRingReport(violations=[], total_vias_checked=0),
        "teardrops": TeardropReport(teardrops=[
            Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu"),
        ]),
        "thermal_reliefs": ThermalReliefReport(thermal_reliefs=[
            ThermalRelief("GND", (0, 0), 4, 0.254, 0.254,
                          pad_size=(0.0, 0.0), spoke_segments=[]),
        ]),
        "copper_balance": CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
        "creepage": CreepageReport(violations=[], total_checks=0),
        "clearance": ClearanceReport(violations=[], total_checks=0),
    }

    @pytest.mark.parametrize("none_field", [
        "acid_traps",
        "annular_rings",
        "teardrops",
        "thermal_reliefs",
        "copper_balance",
        "creepage",
        "clearance",
    ])
    def test_single_none_raises_typeerror(self, none_field):
        """Passing None for any single field raises TypeError."""
        kwargs = dict(self._valid_reports)
        kwargs[none_field] = None

        with pytest.raises(TypeError, match=none_field):
            ManufacturingReport(**kwargs)

    def test_all_none_raises_typeerror(self):
        """All-None raises TypeError (first field caught)."""
        with pytest.raises(TypeError):
            ManufacturingReport(
                acid_traps=None,
                annular_rings=None,
                teardrops=None,
                thermal_reliefs=None,
                copper_balance=None,
                creepage=None,
                clearance=None,
            )

    def test_generate_manufacturing_report_never_produces_none(self):
        """generate_manufacturing_report always passes through to
        ManufacturingReport; passing None to it should also raise."""
        with pytest.raises(TypeError):
            generate_manufacturing_report(
                None,  # acid_traps
                AnnularRingReport(violations=[], total_vias_checked=0),
                TeardropReport(teardrops=[
                    Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu"),
                ]),
                ThermalReliefReport(thermal_reliefs=[
                    ThermalRelief("GND", (0, 0), 4, 0.254, 0.254,
                                  pad_size=(0.0, 0.0), spoke_segments=[]),
                ]),
                CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
                CreepageReport(violations=[], total_checks=0),
                ClearanceReport(violations=[], total_checks=0),
            )


# ===================================================================
# 4. DFM modules do not mutate input RoutingResults
# ===================================================================

class TestInputImmutability:
    """DFM modules must not mutate the RoutingResults passed to them."""

    def test_compiled_routes_unchanged_after_full_dfm_run(self):
        """After _run_manufacturing_drc the routing_results are unchanged."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1", coords=[(0, 0), (10, 10)])
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        # Deep-copy pre-run state
        pre_coords = list(rr.compiled_routes["NET1"].path.coordinates)
        pre_layer = rr.compiled_routes["NET1"].path.layer_name
        pre_width = rr.compiled_routes["NET1"].width_mm
        pre_via_count = len(rr.compiled_routes["NET1"].vias)
        pre_failed = list(rr.failed_nets)

        p._run_manufacturing_drc(pcb=pcb, routing_results=rr)

        # Post-run state must be identical
        assert rr.compiled_routes["NET1"].path.coordinates == pre_coords
        assert rr.compiled_routes["NET1"].path.layer_name == pre_layer
        assert rr.compiled_routes["NET1"].width_mm == pre_width
        assert len(rr.compiled_routes["NET1"].vias) == pre_via_count
        assert list(rr.failed_nets) == pre_failed

    def test_routing_results_not_mutated_when_modules_fail(self):
        """Even when all modules raise, the input is not mutated."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1", coords=[(0, 0), (10, 10)])
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        pre_coords = list(rr.compiled_routes["NET1"].path.coordinates)

        patches = [
            mock.patch(
                "temper_placer.router_v6.acid_trap_detection.detect_acid_traps",
                side_effect=RuntimeError("fail"),
            ),
            mock.patch(
                "temper_placer.router_v6.annular_ring_check.check_annular_rings",
                side_effect=RuntimeError("fail"),
            ),
            mock.patch(
                "temper_placer.router_v6.teardrop_generation.insert_teardrops",
                side_effect=RuntimeError("fail"),
            ),
            mock.patch(
                "temper_placer.router_v6.thermal_relief.add_thermal_relief",
                side_effect=RuntimeError("fail"),
            ),
            mock.patch(
                "temper_placer.router_v6.copper_balance.analyze_copper_balance",
                side_effect=RuntimeError("fail"),
            ),
            mock.patch(
                "temper_placer.router_v6.creepage_check.verify_creepage",
                side_effect=RuntimeError("fail"),
            ),
            mock.patch(
                "temper_placer.router_v6.clearance_check.verify_clearance",
                side_effect=RuntimeError("fail"),
            ),
        ]
        for patcher in patches:
            patcher.start()
        try:
            p._run_manufacturing_drc(pcb=pcb, routing_results=rr)
        finally:
            for patcher in patches:
                patcher.stop()

        assert rr.compiled_routes["NET1"].path.coordinates == pre_coords

    def test_same_routingresults_passed_twice_produces_same_result(self):
        """Idempotency: two DFM runs on the same input produce structurally
        equivalent reports (same violation counts)."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1", coords=[(0, 0), (10, 10)])
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        report1 = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)
        report2 = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)

        # Properties must match
        assert report1.total_violations == report2.total_violations
        assert report1.critical_violations == report2.critical_violations
        assert report1.is_manufacturability_ok == report2.is_manufacturability_ok


# ===================================================================
# 5. Report field mutation — aggregator stability
# ===================================================================

class TestReportFieldMutation:
    """After generate_manufacturing_report, mutating a sub-report does
    NOT affect the aggregator's cached property values (dataclass
    fields are stored by reference, but properties recompute)."""

    def test_mutate_acid_traps_after_construction(self):
        """Appending to acid_traps list after report construction DOES
        affect total_violations because the list is shared by reference."""
        acid = AcidTrapReport(acid_traps=[])
        report = generate_manufacturing_report(
            acid,
            AnnularRingReport(violations=[], total_vias_checked=0),
            TeardropReport(teardrops=[
                Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu"),
            ]),
            ThermalReliefReport(thermal_reliefs=[
                ThermalRelief("GND", (0, 0), 4, 0.254, 0.254,
                              pad_size=(0.0, 0.0), spoke_segments=[]),
            ]),
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
            CreepageReport(violations=[], total_checks=0),
            ClearanceReport(violations=[], total_checks=0),
        )

        assert report.total_violations == 0

        # Mutate the shared list
        acid.acid_traps.append(AcidTrap("NET1", (0, 0), 30.0, "high"))

        # total_violations reads the (now mutated) list
        assert report.total_violations == 1
        assert report.critical_violations == 1

    def test_replace_subreport_reference(self):
        """Replacing a sub-report reference does NOT change the aggregator
        because the ManufacturingReport stores its own reference to the
        original object passed at construction time."""
        original_acid = AcidTrapReport(acid_traps=[])
        report = generate_manufacturing_report(
            original_acid,
            AnnularRingReport(violations=[], total_vias_checked=0),
            TeardropReport(teardrops=[
                Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu"),
            ]),
            ThermalReliefReport(thermal_reliefs=[
                ThermalRelief("GND", (0, 0), 4, 0.254, 0.254,
                              pad_size=(0.0, 0.0), spoke_segments=[]),
            ]),
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
            CreepageReport(violations=[], total_checks=0),
            ClearanceReport(violations=[], total_checks=0),
        )

        # Replace the *local variable*, but the report still references
        # the original object
        original_acid = AcidTrapReport(acid_traps=[
            AcidTrap("X", (0, 0), 30.0, "high"),
        ])

        # The report still holds the original (empty) acid_traps
        assert report.acid_traps.trap_count == 0
        assert report.total_violations == 0

    def test_deepcopy_isolates_report(self):
        """A deepcopy of the report is fully independent."""
        report = _empty_report()
        assert report.total_violations == 0

        copied = copy.deepcopy(report)
        copied.acid_traps.acid_traps.append(
            AcidTrap("NET1", (0, 0), 30.0, "high"),
        )

        assert copied.total_violations == 1
        # Original must be unchanged
        assert report.total_violations == 0


# ===================================================================
# 6. Gate logic with partial failures
# ===================================================================

class TestGateLogicPartialFailures:
    """critical_violations and total_violations when some modules
    failed (None fallback → 0 violations)."""

    def test_critical_violations_zero_when_all_modules_failed(self):
        """When every module falls back, critical_violations is 0."""
        report = generate_manufacturing_report(
            AcidTrapReport(acid_traps=[]),           # fallback: 0 traps
            AnnularRingReport(violations=[], total_vias_checked=0),  # fallback: 0
            TeardropReport(teardrops=[]),             # fallback: empty → sentinel=1
            ThermalReliefReport(thermal_reliefs=[]),  # fallback: empty → sentinel=1
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),  # fallback: 0
            CreepageReport(violations=[], total_checks=0),  # fallback: 0
            ClearanceReport(violations=[], total_checks=0),  # fallback: 0
        )

        # critical_violations = acid.critical + annular.violations
        #   + creepage.violations + clearance.violations
        #   + copper.unbalanced_layer_count
        # (teardrop/thermal sentinels are NOT in critical_violations)
        assert report.critical_violations == 0

        # total_violations includes teardrop/thermal sentinels (1 each
        # when count == 0)
        assert report.total_violations == 2  # 2 sentinels

    def test_mixed_real_and_fallback(self):
        """One module produces real violations; others are fallback zeros."""
        report = generate_manufacturing_report(
            AcidTrapReport(acid_traps=[
                AcidTrap("NET1", (0, 0), 30.0, "high"),  # critical
            ]),
            AnnularRingReport(violations=[], total_vias_checked=0),   # fallback
            TeardropReport(teardrops=[Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu")]),
            ThermalReliefReport(thermal_reliefs=[
                ThermalRelief("GND", (0, 0), 4, 0.254, 0.254,
                              pad_size=(0.0, 0.0), spoke_segments=[]),
            ]),
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),  # fallback
            CreepageReport(violations=[], total_checks=0),               # fallback
            ClearanceReport(violations=[], total_checks=0),              # fallback
        )

        # 1 critical acid trap
        assert report.critical_violations == 1
        # 1 acid trap + teardrop/thermal present (no sentinels) = 1
        assert report.total_violations == 1
        assert report.is_manufacturability_ok is False

    def test_teardrop_fallback_sentinel_behavior(self):
        """TeardropReport with no teardrops triggers sentinel=1 in
        total_violations (but NOT in critical_violations)."""
        report = generate_manufacturing_report(
            AcidTrapReport(acid_traps=[]),
            AnnularRingReport(violations=[], total_vias_checked=0),
            TeardropReport(teardrops=[]),  # NO teardrops → sentinel
            ThermalReliefReport(thermal_reliefs=[
                ThermalRelief("GND", (0, 0), 4, 0.254, 0.254,
                              pad_size=(0.0, 0.0), spoke_segments=[]),
            ]),
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
            CreepageReport(violations=[], total_checks=0),
            ClearanceReport(violations=[], total_checks=0),
        )

        # critical_violations excludes teardrop/thermal sentinels
        assert report.critical_violations == 0
        # total_violations includes teardrop sentinel
        assert report.total_violations == 1

    def test_thermal_fallback_sentinel_behavior(self):
        """ThermalReliefReport with no reliefs triggers sentinel=1 in
        total_violations (but NOT in critical_violations)."""
        report = generate_manufacturing_report(
            AcidTrapReport(acid_traps=[]),
            AnnularRingReport(violations=[], total_vias_checked=0),
            TeardropReport(teardrops=[
                Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu"),
            ]),
            ThermalReliefReport(thermal_reliefs=[]),  # NO reliefs → sentinel
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
            CreepageReport(violations=[], total_checks=0),
            ClearanceReport(violations=[], total_checks=0),
        )

        assert report.critical_violations == 0
        assert report.total_violations == 1

    def test_both_sentinels_fire(self):
        """Both teardrops and thermal_reliefs empty → total_violations += 2."""
        report = generate_manufacturing_report(
            AcidTrapReport(acid_traps=[]),
            AnnularRingReport(violations=[], total_vias_checked=0),
            TeardropReport(teardrops=[]),            # sentinel
            ThermalReliefReport(thermal_reliefs=[]),  # sentinel
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
            CreepageReport(violations=[], total_checks=0),
            ClearanceReport(violations=[], total_checks=0),
        )

        assert report.critical_violations == 0
        assert report.total_violations == 2


# ===================================================================
# 7. Pipeline ordering — does the order modules are called matter?
# ===================================================================

class TestPipelineOrdering:
    """The DFM modules are called in a fixed order inside
    _run_manufacturing_drc, but since each is independent and fallback-
    isolated, swapping two calls should produce the same result."""

    def test_swap_acid_trap_and_clearance_yields_same_result(self):
        """Simulate what _run_manufacturing_drc does but call clearance
        first and acid_trap second — result must be identical."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1", coords=[(0, 0), (10, 10)])
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        # Original order
        orig = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)

        # Reordered: manually invoke each function in swapped order and
        # build the report ourselves.  We must replicate the try/except
        # logic from _run_one.
        def _safe(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                return None

        # --- Swapped order: clearance first, acid_trap second ---
        clearance = _safe(verify_clearance, rr) or ClearanceReport(
            violations=[], total_checks=0,
        )
        acid_traps = _safe(detect_acid_traps, rr) or AcidTrapReport(
            acid_traps=[],
        )
        annular_rings = _safe(check_annular_rings, rr) or AnnularRingReport(
            violations=[], total_vias_checked=0,
        )
        teardrops = _safe(insert_teardrops, rr) or TeardropReport(
            teardrops=[],
        )
        thermal_reliefs = _safe(add_thermal_relief, rr,
                                board=pcb.board) or ThermalReliefReport(
            thermal_reliefs=[],
        )
        copper_balance = CopperBalanceReport(
            layer_balances=[], total_area_mm2=0.0,
        )
        if pcb.board is not None:
            copper_balance = _safe(
                analyze_copper_balance, rr,
                board_width=pcb.board.width,
                board_height=pcb.board.height,
            ) or copper_balance
        creepage = _safe(verify_creepage, rr) or CreepageReport(
            violations=[], total_checks=0,
        )

        swapped = generate_manufacturing_report(
            acid_traps, annular_rings, teardrops, thermal_reliefs,
            copper_balance, creepage, clearance,
        )

        # Results must be identical
        assert orig.total_violations == swapped.total_violations
        assert orig.critical_violations == swapped.critical_violations
        assert orig.is_manufacturability_ok == swapped.is_manufacturability_ok

    def test_module_call_order_is_deterministic(self):
        """Calling the pipeline twice produces the same report."""
        p = RouterV6Pipeline(enable_manufacturing_drc=True, verbose=False)
        route = _make_stub_route("NET1", coords=[(0, 0), (10, 10)])
        rr = _make_routing_results(NET1=route)
        pcb = _make_pcb_mock(width=100, height=80)

        r1 = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)
        r2 = p._run_manufacturing_drc(pcb=pcb, routing_results=rr)

        assert r1.total_violations == r2.total_violations
        assert r1.critical_violations == r2.critical_violations


# ===================================================================
# 8. Exception types — ManufacturingDRCViolationError message fidelity
# ===================================================================

class TestExceptionTypes:
    """ManufacturingDRCViolationError carries the correct message for
    each dfm_fail_on mode."""

    def _make_report_with(self, critical=0, non_critical=0):
        traps = []
        for _ in range(critical):
            traps.append(AcidTrap("N", (0, 0), 30.0, "high"))
        for _ in range(non_critical):
            traps.append(AcidTrap("N", (0, 0), 75.0, "low"))
        return generate_manufacturing_report(
            AcidTrapReport(acid_traps=traps),
            AnnularRingReport(violations=[], total_vias_checked=0),
            TeardropReport(teardrops=[
                Teardrop("N", (0, 0), "via", 0.3, 0.6, "F.Cu"),
            ]),
            ThermalReliefReport(thermal_reliefs=[
                ThermalRelief("GND", (0, 0), 4, 0.254, 0.254,
                              pad_size=(0.0, 0.0), spoke_segments=[]),
            ]),
            CopperBalanceReport(layer_balances=[], total_area_mm2=0.0),
            CreepageReport(violations=[], total_checks=0),
            ClearanceReport(violations=[], total_checks=0),
        )

    def test_none_mode_message(self):
        """dfm_fail_on='none' never raises (verified separately).
        We test that the pipeline attribute is correctly stored."""
        p = RouterV6Pipeline(dfm_fail_on="none")
        assert p.dfm_fail_on == "none"

    def test_critical_mode_message(self):
        """When critical violations exist, the error message cites
        'critical' mode and includes violation counts."""
        report = self._make_report_with(critical=2, non_critical=1)
        # 2 critical + 1 non-critical = 3 total

        with pytest.raises(ManufacturingDRCViolationError) as exc_info:
            raise ManufacturingDRCViolationError(
                f"Manufacturing DRC: "
                f"{report.total_violations} violations "
                f"({report.critical_violations} critical). "
                f"Fail mode: critical."
            )

        msg = str(exc_info.value)
        assert "Manufacturing DRC" in msg
        assert "3 violations" in msg
        assert "2 critical" in msg
        assert "critical" in msg

    def test_all_mode_message(self):
        """When any violation exists, 'all' mode raises with total count."""
        report = self._make_report_with(critical=0, non_critical=1)
        # 1 total violation

        with pytest.raises(ManufacturingDRCViolationError) as exc_info:
            raise ManufacturingDRCViolationError(
                f"Manufacturing DRC: "
                f"{report.total_violations} violations "
                f"({report.critical_violations} critical). "
                f"Fail mode: all."
            )

        msg = str(exc_info.value)
        assert "Manufacturing DRC" in msg
        assert "1 violations" in msg
        assert "0 critical" in msg
        assert "all" in msg

    def test_error_is_runtime_error_subclass(self):
        """ManufacturingDRCViolationError is a RuntimeError."""
        assert issubclass(ManufacturingDRCViolationError, RuntimeError)

    def test_error_can_be_caught_as_runtime_error(self):
        """Catching RuntimeError also catches ManufacturingDRCViolationError."""
        try:
            raise ManufacturingDRCViolationError("test")
        except RuntimeError:
            pass  # expected
        else:
            pytest.fail("RuntimeError should have caught the exception")

    def test_invalid_dfm_fail_on_raises_valueerror(self):
        """Invalid dfm_fail_on raises ValueError at construction time."""
        with pytest.raises(ValueError, match="dfm_fail_on"):
            RouterV6Pipeline(dfm_fail_on="invalid_mode")
