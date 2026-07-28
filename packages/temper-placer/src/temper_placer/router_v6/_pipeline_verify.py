"""
Router V6 Pipeline: DRC verification and manufacturing checks.

Extracted from ``_pipeline_stages.py`` — contains fence integration,
per-stage invariants, and manufacturing DRC.
"""

from __future__ import annotations

import logging

from temper_placer.core.board import side_to_layer_name
from temper_placer.router_v6._pipeline_types import ManufacturingReport
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.validation.drc_fence import InvariantSpec


def _parsed_pcb_to_drc_input(
    pcb: ParsedPCB,
    escape_vias: list[EscapeVia] | None = None,
    routing_results: RoutingResults | None = None,
) -> tuple:
    """Convert ParsedPCB to temper_drc Placement and ConstraintSet.

    Bridges the RouterV6 pipeline's ParsedPCB representation to the
    DRC check input format. Extracts component positions, net assignments,
    and board dimensions.

    When escape_vias or routing_results are provided, they are converted
    to temper_drc ViaPlacement / TracePlacement types and attached to the
    Placement model for DRC checks that operate on geometry beyond
    component footprint overlap.
    """
    from temper_placer.validation.drc_types import ClearanceRule, ConstraintSet
    from temper_placer.validation.drc_types import ComponentPlacement as DRCCompPlacement
    from temper_placer.validation.drc_types import Placement as DRCPlacement

    board_width = pcb.board.width
    board_height = pcb.board.height

    components = {}
    for comp in pcb.components:
        if hasattr(comp, "initial_position") and comp.initial_position:
            x, y = comp.initial_position
        else:
            x, y = 0.0, 0.0

        side = getattr(comp, "initial_side", 0)
        layer = side_to_layer_name(side)

        components[comp.ref] = DRCCompPlacement(
            ref=comp.ref,
            footprint=comp.footprint,
            x=float(x),
            y=float(y),
            rotation=float(getattr(comp, "initial_rotation", 0) or 0),
            layer=layer,
            width=comp.width,
            height=comp.height,
            net_class=comp.net_class,
        )

    nets = {}
    for net in pcb.nets:
        if hasattr(net, "pins"):
            nets[net.name] = [pin[0] for pin in net.pins]

    zones = {}
    for zone in pcb.zones:
        if hasattr(zone, "name") and hasattr(zone, "bounds"):
            zones[zone.name] = zone.bounds

    placement = DRCPlacement(
        components=components,
        nets=nets,
        zones=zones,
        board_width=board_width,
        board_height=board_height,
    )

    if escape_vias:
        from temper_placer.validation.drc_types import Via as DRCVia
        from temper_placer.validation.drc_types import ViaPlacement as DRCViaPlacement

        drc_vias = [
            DRCVia(
                position=ev.position,
                from_layer=ev.layer,
                to_layer="B.Cu" if ev.layer == "F.Cu" else "F.Cu",
                diameter=ev.diameter,
                drill=ev.drill,
                net_name=ev.net_name,
            )
            for ev in escape_vias
        ]
        placement.via_placement = DRCViaPlacement(vias=drc_vias)

    if routing_results is not None:
        from temper_placer.validation.drc_types import TracePlacement as DRCTracePlacement
        from temper_placer.validation.drc_types import TraceSegment

        segments: list[TraceSegment] = []
        for net_name, net_result in getattr(routing_results, "results", {}).items():
            if not getattr(net_result, "success", False):
                continue
            route = getattr(net_result, "route", None)
            if route is None:
                continue
            coords = getattr(route, "coordinates", [])
            layer = getattr(route, "layer_name", "F.Cu")
            width = getattr(net_result, "width", 0.2)
            for i in range(len(coords) - 1):
                segments.append(
                    TraceSegment(
                        net_name=net_name,
                        layer=layer,
                        width=width,
                        start=coords[i],
                        end=coords[i + 1],
                    )
                )
        placement.trace_placement = DRCTracePlacement(segments=segments)

    default_clearance = getattr(pcb.design_rules, "default_clearance_mm", 0.3)
    constraints = ConstraintSet(
        clearances=[ClearanceRule(from_class="*", to_class="*", min_mm=default_clearance)],
        board_width=board_width,
        board_height=board_height,
    )

    return placement, constraints


def _stage_0_5_invariants() -> tuple:
    return (InvariantSpec("drc_component_overlap", "No component overlaps after legalization"),)


def _ensure_checks_loaded(fence, invariants: tuple) -> None:
    """Auto-register any checks referenced by invariants that are not yet
    in the fence's runner.  Without this, referencing ``drc_via_spacing``
    or ``drc_trace_clearance`` would silently produce zero violations."""
    needed = {inv.check_name for inv in invariants}
    try:
        existing = {c.name for c in fence._runner.checks}
    except (AttributeError, TypeError):
        return
    missing = needed - existing
    if not missing:
        return
    try:
        from temper_placer.validation.drc_result import (
            TraceClearanceCheck,
            ViaSpacingCheck,
        )
    except ImportError:
        return
    if "drc_via_spacing" in missing:
        fence._runner.checks.append(ViaSpacingCheck())
    if "drc_trace_clearance" in missing:
        fence._runner.checks.append(TraceClearanceCheck())


def _stage_1_invariants() -> tuple:
    return (InvariantSpec("drc_via_spacing", "Escape vias satisfy minimum spacing"),)


def _stage_4_invariants() -> tuple:
    return (InvariantSpec("drc_trace_clearance", "Routed traces satisfy minimum clearance"),)


def _run_fence(
    self,
    *,
    stage_name: str,
    invariants: tuple,
    pcb: ParsedPCB,
    escape_vias: list[EscapeVia] | None = None,
    routing_results: RoutingResults | None = None,
):
    """Run fence checks for a Router V6 stage.

    Creates DRC inputs from the PCB data and invokes the fence.
    When escape_vias or routing_results are provided, they are
    converted to temper_drc ViaPlacement / TracePlacement types
    and attached to the Placement model for geometry-level DRC
    checks (via spacing, trace clearance).
    """
    assert self.fence is not None, "_run_fence called with no fence configured"
    placement, constraints = _parsed_pcb_to_drc_input(
        pcb,
        escape_vias=escape_vias,
        routing_results=routing_results,
    )
    _ensure_checks_loaded(self.fence, invariants)
    self.fence.check(
        stage_name=stage_name,
        invariants=invariants,
        placement=placement,
        constraints=constraints,
    )


def _run_manufacturing_drc(
    self,
    pcb: ParsedPCB,
    routing_results: RoutingResults,
) -> ManufacturingReport:
    """Run all 8 DFM checks and compile the manufacturing report.

    Each DFM module is called in isolation -- a failure in one
    module does not prevent the remaining checks from running.
    """
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
        generate_manufacturing_report,
    )
    from temper_placer.router_v6.teardrop_generation import (
        TeardropReport,
        insert_teardrops,
    )
    from temper_placer.router_v6.thermal_relief import (
        ThermalReliefReport,
        add_thermal_relief,
    )

    _logger = logging.getLogger(__name__)

    if self.verbose:
        print("Stage 5: Manufacturing DRC...")

    def _run_one(name, fn, *args, **kwargs):
        """Run one DFM check in isolation.

        Returns ``(result, errored)``. ``errored`` is True exactly when
        ``fn`` raised. **Every call site must fold ``errored`` into the
        substituted report's own ``errored`` field** -- a crashed check
        must be visibly distinct from a clean run *in the returned
        report*, not only in this log line. Silently substituting an
        empty/clean-looking report for a crash was the actual defect;
        see docs/evidence/2026-07-25-manufacturing-drc-crash-swallow.md.
        """
        try:
            return fn(*args, **kwargs), False
        except Exception:
            _logger.warning(
                "Manufacturing DRC: %s check failed, continuing",
                name,
                exc_info=True,
            )
            return None, True

    # Computed up front (not just before creepage/clearance below) because
    # the anti-vacuous-truth guard now also applies to annular_ring.
    has_routed_copper = bool(
        getattr(routing_results, "compiled_routes", None)
        or getattr(routing_results, "tree_routes", None)
    )
    has_vias = bool(
        any(
            getattr(cr, "vias", None)
            for cr in getattr(routing_results, "compiled_routes", {}).values()
        )
        or any(
            getattr(tr, "vias", None)
            for tr in getattr(routing_results, "tree_routes", {}).values()
        )
        or any(
            getattr(tr, "vias", None)
            for tr in getattr(routing_results, "partial_tree_routes", {}).values()
        )
    )

    acid_traps_result, acid_traps_errored = _run_one(
        "acid_trap",
        detect_acid_traps,
        routing_results,
    )
    acid_traps = acid_traps_result or AcidTrapReport(acid_traps=[], errored=acid_traps_errored)

    annular_result, annular_errored = _run_one(
        "annular_ring",
        check_annular_rings,
        routing_results,
    )
    annular_rings = annular_result or AnnularRingReport(
        violations=[], total_vias_checked=0, errored=annular_errored
    )
    # Anti-vacuous-truth guard (METHODOLOGY.md Sec 5), same pattern as
    # creepage/clearance below: a check that ran without raising but
    # inspected zero vias while the board actually has vias present is as
    # untrustworthy as a crash. See
    # docs/evidence/2026-07-27-drc-checks-repaired.md.
    if not annular_errored and annular_rings.total_vias_checked == 0 and has_vias:
        _logger.error(
            "Manufacturing DRC: annular_ring check reported "
            "total_vias_checked=0 on a board with vias present -- "
            "anti-vacuous-truth guard (METHODOLOGY.md Sec 5) fired; "
            "treating as errored/fail-closed."
        )
        annular_rings.errored = True

    teardrops_result, teardrops_errored = _run_one(
        "teardrop",
        insert_teardrops,
        routing_results,
    )
    teardrops = teardrops_result or TeardropReport(teardrops=[], errored=teardrops_errored)

    thermal_result, thermal_errored = _run_one(
        "thermal_relief",
        add_thermal_relief,
        routing_results,
        board=pcb.board,
    )
    thermal_reliefs = thermal_result or ThermalReliefReport(
        thermal_reliefs=[], errored=thermal_errored
    )

    if pcb.board is not None:
        from temper_placer.router_v6.power_plane import generate_power_planes

        geometry, power_planes_errored = _run_one(
            "power_planes",
            generate_power_planes,
            pcb.board,
            pcb.components,
        )
        if geometry is not None:
            _logger.info(
                "Power planes: GND pour on %s, %d domain pours on In2.Cu, %d thermal vias",
                geometry.ground_pour.layer,
                len(geometry.power_pours),
                geometry.via_count,
            )
        elif power_planes_errored:
            # power_planes has no dedicated slot in ManufacturingReport, so
            # this is the only place a crash here is visible. Log at error
            # (not warning) so it is not lost among routine warnings.
            _logger.error(
                "Manufacturing DRC: power_planes check errored -- no power "
                "plane geometry was generated for this board (see warning "
                "above for the traceback)."
            )

    copper_balance = CopperBalanceReport(layer_balances=[], total_area_mm2=0.0)
    if pcb.board is not None:
        cb_result, cb_errored = _run_one(
            "copper_balance",
            analyze_copper_balance,
            routing_results,
            board_width=pcb.board.width,
            board_height=pcb.board.height,
        )
        copper_balance = cb_result or CopperBalanceReport(
            layer_balances=[], total_area_mm2=0.0, errored=cb_errored
        )
    else:
        _logger.warning("Manufacturing DRC: skipping copper balance -- no board geometry")

    # creepage and clearance carry HV safety meaning on a mains-connected
    # board and must FAIL CLOSED, matching the `_allow_forced_segments`
    # precedent in _astar_reconstruct.py: on error, do not fall back to a
    # report that *reads* as clean. `ManufacturingReport` folds
    # `errored=True` into critical_violations/total_violations as if a
    # violation had been found.
    #
    # This also covers the anti-vacuous-truth axis (METHODOLOGY.md Sec 5):
    # a check that ran without raising but examined zero conductor pairs
    # on a board that has actual routed copper is just as untrustworthy
    # as a crash, and is tagged `errored=True` too.
    # (`has_routed_copper` computed once, up front -- also used by the
    # annular_ring guard above.)

    creepage_result, creepage_errored = _run_one(
        "creepage",
        verify_creepage,
        routing_results,
    )
    creepage = creepage_result or CreepageReport(violations=[], total_checks=0, errored=True)
    if not creepage_errored and creepage.total_checks == 0 and has_routed_copper:
        _logger.error(
            "Manufacturing DRC: creepage check reported total_checks=0 on "
            "a board with routed copper -- anti-vacuous-truth guard "
            "(METHODOLOGY.md Sec 5) fired; treating as errored/fail-closed."
        )
        creepage.errored = True

    clearance_result, clearance_errored = _run_one(
        "clearance",
        verify_clearance,
        routing_results,
    )
    clearance = clearance_result or ClearanceReport(violations=[], total_checks=0, errored=True)
    if not clearance_errored and clearance.total_checks == 0 and has_routed_copper:
        _logger.error(
            "Manufacturing DRC: clearance check reported total_checks=0 on "
            "a board with routed copper -- anti-vacuous-truth guard "
            "(METHODOLOGY.md Sec 5) fired; treating as errored/fail-closed."
        )
        clearance.errored = True

    return generate_manufacturing_report(
        acid_traps,
        annular_rings,
        teardrops,
        thermal_reliefs,
        copper_balance,
        creepage,
        clearance,
    )
