"""Verbatim pre-migration oracle for the orchestration-port unit U-G
(Rust Orchestration Engine plan 2026-08-09-001): the RouterV6Pipeline.run()
stage-sequencing driver.

This file is a byte-exact snapshot of the ORCHESTRATION body of
``RouterV6Pipeline.run`` AS COMMITTED at the dispatch base (origin/main
565078e54), extracted verbatim from ``router_v6/_pipeline_core.py`` lines
268-527 (the whole method body INCLUDING its docstring), re-indented by one
level to module-function scope (the only rewrite; every statement is
byte-identical).

``run_verbatim(self, ...)`` is the pre-migration run-loop. The differential
drives it with a REAL shim ``RouterV6Pipeline`` instance whose leaf
call-backs (parse, legalize, escape-via generation, ``_run_stage2/3/4/5``,
``_run_fence``, ``_run_manufacturing_drc``, the ledger, the ERC gate) are
deterministic fakes -- so the oracle arm and the shim arm run the SAME leaf
compute and only the LOOP differs (exactly the U-E convention). The imports
below mirror the pre-migration module's own module-level imports; the body's
inline imports (``parse_kicad_pcb_v6``, the ERC gates) resolve at call time
from the real modules, so the differential's monkeypatch seams stay visible.

Do NOT edit: it is the reference.

"""

# --- BEGIN PINNED BODY ---

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from temper_placer.router_v6._pipeline_types import (
    ManufacturingDRCViolationError,
    RouterV6Result,
    Stage3Output,
)
from temper_placer.router_v6._pipeline_verify import (
    _stage_0_5_invariants,
    _stage_1_invariants,
    _stage_4_invariants,
)
from temper_placer.router_v6.dense_package_detection import identify_dense_packages
from temper_placer.router_v6.escape_via_generator import generate_escape_vias
from temper_placer.router_v6.placement_legalization import Legalizer


def run_verbatim(
    self,
    pcb_path: Path,
    pcb_override=None,
    net_class_assignments: dict[str, str] | None = None,
    net_classes: dict[str, Any] | None = None,
) -> RouterV6Result:
    """Run complete Router V6 pipeline on a PCB file.

    Args:
        pcb_path: Path to .kicad_pcb file.
        pcb_override: Optional pre-parsed ``ParsedPCB`` to use.
        net_class_assignments: Optional ``{net_name: netclass_name}``
            map to inject into the parsed board's design rules for
            per-net clearance-aware routing (R4 FinePitch 0.15mm).
        net_classes: Optional ``{class_name: stage0 NetClassRules}``
            dict injected into ``pcb.design_rules.net_classes`` after
            parsing.  This is the primary path for ``safety_category``
            to reach the A* engine (used by the HV/AC forced-segment
            fail-closed gate, R6 in 2026-07-23-008).
    """
    start_time = time.time()

    # Stage 0: Load PCB
    if self.verbose:
        print("Stage 0: Loading PCB...")
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    # use_declared_layer_roles=True (R8): layer_type comes from structural
    # position in the declared stackup (outer = signal, inner = mixed),
    # never from "does at least one zone on this layer sit on a
    # plane-required net". Fixes the quantifier bug in _extract_stackup()
    # (docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md):
    # before this, a handful of plane-required zones (4 of 48 on
    # pcb/temper.kicad_pcb's F.Cu) condemned the *entire* physical layer
    # to layer_type="plane", which routing_space.py:85 then drops from
    # the router's routing space wholesale -- collapsing
    # state.channel_skeletons to {} and route_pcb() to a 0-variable
    # model that silently degrades to a per-net fallback (see
    # docs/evidence/2026-08-07-router-silent-noop-diagnosis.md).
    #
    # This flag was flagged NOT SAFE alone: obstacle_map.py's zone loop
    # (build_obstacle_map, section 3) already unions every zone on a
    # layer into that layer's obstacle polygon unconditionally --
    # regardless of layer_type -- so opening F.Cu/B.Cu here does not
    # skip registering their existing pours as obstacles (verified by
    # reading obstacle_map.py: the zone loop has no layer_type guard,
    # unlike the pad/via loops next to it). The companion risk named in
    # the solutions doc (obstacle_map.py unioning ALL pours net-blind,
    # previously measured to cut F.Cu's available area to ~24.7% and
    # cause a 12x completion regression when the outer layers were
    # forced open by a1fe623e/60d441f2) is real but is the documented,
    # separate, not-yet-landed "pours become derived output" project
    # (docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md, R7/U3,
    # status: swept -- not implemented). Flipping this flag here does not
    # depend on that project to be *safe* in the sense of "never routes
    # through copper" -- it only affects how much free area remains once
    # the layer is legitimately open.
    pcb = parse_kicad_pcb_v6(pcb_path, use_declared_layer_roles=True)
    if pcb_override is not None:
        pcb = pcb_override

    # Inject per-net netclass assignments so ``get_rules_for_net`` can
    # resolve a class for the nets that have one.
    #
    # ``dr.default_clearance_mm = 0.15`` was DELETED here on 2026-08-12, in
    # lockstep with the shim (``router_v6/_pipeline_core.py``'s
    # ``_run_stage0_setup``). This oracle pins the MIGRATION contract --
    # shim output == pre-migration output -- not the VALUE, so a deliberate
    # value correction has to be made on both sides or the differential
    # starts asserting the defect. The floor for an unclassified net is
    # 0.2mm in all three declaring sources (netclass_rules.yaml,
    # temper.kicad_pro's Default class, generate_kicad_dru.py's RULE 10);
    # 0.15 was a global relaxation of the fallback, not any net's
    # requirement. See that file's comment,
    # scripts/check_router_clearance_floor.py, and
    # docs/evidence/2026-08-12-clearance-congestion-band.md.
    if net_class_assignments or net_classes:
        dr = getattr(pcb, "design_rules", None)
        if dr is not None:
            if net_class_assignments:
                nc = getattr(dr, "net_class_assignments", {})
                if isinstance(nc, dict):
                    nc.update(net_class_assignments)
                    dr.net_class_assignments = nc
            if net_classes:
                existing = getattr(dr, "net_classes", {})
                if isinstance(existing, dict):
                    existing.update(net_classes)
                    dr.net_classes = existing

    # Reorder nets: power/HV nets first, signal nets last.
    # Prevents final-round displacement of SPI/USB/sense nets.
    _SIG = ("SPI_", "I_SENSE", "USB_", "TEMP_")
    _PWR = ("GATE_", "PWM_", "DC_BUS", "AC_", "SW_NODE", "VCC_BOOT", "CGND", "PGND", "+", "GND")

    def _prio(net):
        name = net.name if hasattr(net, "name") else str(net)
        if any(name.startswith(p) for p in _PWR):
            return 0
        return 1

    pcb.nets.sort(key=_prio)

    # Stage 0.5: Legalization
    if self.enable_legalization:
        if self.verbose:
            print("Stage 0.5: Checking and Legalizing Placement...")

        legalizer = Legalizer(pcb)
        # Check collisions before
        if self.verbose:
            collisions = legalizer.auditor.check_collisions()
            print(f"  Found {len(collisions)} initial collisions")

        if legalizer.legalize():
            if self.verbose:
                print("  Placement collision check passed (0 overlaps)")
        else:
            collisions = legalizer.auditor.check_collisions()
            # Pin-hull collision detection is intentionally advisory. It
            # is not a substitute for KiCad's footprint-courtyard DRC and
            # must not move CP-SAT coordinates outside their constraints.
            if self.verbose:
                print(
                    "  Advisory pin-hull overlaps: "
                    + ", ".join(
                        f"{collision.ref1}/{collision.ref2}" for collision in collisions[:8]
                    )
                )

    # Validate placement (Post-Legalization)
    # ``Legalizer`` above is deliberately non-mutating: CP-SAT owns all
    # constraint-preserving component movement, and KiCad DRC remains the
    # authoritative physical-overlap gate.
    errors = pcb.validate_placement()
    if errors:
        raise ValueError(f"PCB validation failed: {errors}")

    # Stage 0.5 Fence: Check component overlap after legalization
    if self.fence:
        self._run_fence(
            stage_name="router_v6.legalization",
            invariants=_stage_0_5_invariants(),
            pcb=pcb,
        )
    self.ledger.checkin(pcb)

    # Stage 1: Generate escape vias
    if self.verbose:
        print(f"Stage 1: Detecting dense packages in {len(pcb.components)} components...")
    dense_packages = identify_dense_packages(pcb.components)
    if self.verbose:
        print(f"  Found {len(dense_packages)} dense packages")

    escape_vias = []
    for dense_pkg in dense_packages:
        # Try dog-bone first
        vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="dog-bone")

        # If that fails (tight pitch), try via-in-pad
        if not vias:
            if self.verbose:
                print(f"    Falling back to via-in-pad for {dense_pkg.component.ref}")
            vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="via-in-pad")

        escape_vias.extend(vias)
    if self.verbose:
        print(f"  Generated {len(escape_vias)} escape vias")

    # Stage 1 fence: verify escape via placement correctness
    if self.fence and escape_vias:
        self._run_fence(
            stage_name="router_v6.escape_vias",
            invariants=_stage_1_invariants(),
            pcb=pcb,
            escape_vias=escape_vias,
        )
    self.ledger.checkout("escape_vias", pcb)

    # Stage 2: Channel analysis
    if self.verbose:
        print("Stage 2: Channel analysis...")
    stage2 = self._run_stage2(pcb, escape_vias)

    # Resource exhaustion bound (after EDT grids are built)
    self._compute_resource_bound(pcb, stage2)

    # Stage 3: Topological routing.  When skip_stage3 is True,
    # bypass the SAT solver entirely and feed Stage 4 an empty
    # topology graph.  After Dijkstra removal (2026-06-28),
    # skip_stage3 routes nets via direct A* on the occupancy
    # grid without skeleton guidance (previously used Dijkstra).
    # The SAT code stays in place; this is a guarded bypass,
    # not a removal.
    if self.skip_stage3:
        if self.verbose:
            print("Stage 3: Topological routing... SKIPPED")
        stage3 = Stage3Output(
            constraint_model=None,
            solution=None,
            topology_graph=None,
        )
    else:
        if self.verbose:
            print("Stage 3: Topological routing...")
        stage3 = self._run_stage3(pcb, stage2)

    # Stage 4: Geometric realization
    if self.verbose:
        print("Stage 4: Geometric realization...")
    stage4 = self._run_stage4(pcb, stage2, stage3, escape_vias)

    # Stage 5: Manufacturing DRC (opt-in)
    manufacturing_report = None
    if self.enable_manufacturing_drc:
        manufacturing_report = self._run_manufacturing_drc(pcb, stage4.routing_results)
        if self.dfm_fail_on != "none":
            should_fail = (
                manufacturing_report.critical_violations > 0
                if self.dfm_fail_on == "critical"
                else manufacturing_report.total_violations > 0
            )
            if should_fail:
                raise ManufacturingDRCViolationError(
                    f"Manufacturing DRC: "
                    f"{manufacturing_report.total_violations} violations "
                    f"({manufacturing_report.critical_violations} critical). "
                    f"Fail mode: {self.dfm_fail_on}."
                )

    # Stage 4 fence: verify routed trace and via clearance
    if self.fence and stage4.routing_results:
        self._run_fence(
            stage_name="router_v6.geometric",
            invariants=_stage_4_invariants(),
            pcb=pcb,
            routing_results=stage4.routing_results,
        )

    # Post-routing ERC check (plan 2026-07-23-001 U2)
    if self.enable_erc_check:
        from temper_placer.placer.cp_sat.gates import BoardState, ErcGate, GateStatus

        erc_result = ErcGate().check(BoardState(routed_pcb_path=pcb_path))
        if erc_result.status is GateStatus.UNMEASURED:
            _logger = logging.getLogger(__name__)
            _logger.warning("ERC gate UNMEASURED: %s", erc_result.error_message)
        elif erc_result.status is GateStatus.VIOLATIONS:
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "ERC gate found %d violation(s) on routed board",
                len(erc_result.violations),
            )

    runtime = time.time() - start_time

    if self.verbose:
        print(f"\nRouter V6 complete in {runtime:.1f}s")
        print(f"  Routed: {stage4.routing_results.success_count} nets")
        print(f"  Failed: {stage4.routing_results.failure_count} nets")
        print(
            f"  Completion: {100 * stage4.routing_results.success_count / max(1, stage4.routing_results.success_count + stage4.routing_results.failure_count):.1f}%"
        )

    result = RouterV6Result(
        pcb=pcb,
        escape_vias=escape_vias,
        stage2=stage2,
        stage3=stage3,
        stage4=stage4,
        manufacturing_report=manufacturing_report,
        runtime_seconds=runtime,
        batch_results=list(self.last_batch_results),
    )
    self.ledger.checkout("routing_complete", result)
    return result
