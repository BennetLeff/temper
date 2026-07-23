"""
Router V6 Pipeline: Core orchestrator class.

Contains ``RouterV6Pipeline.__init__`` (configuration) and ``run``
(orchestration).  Per-stage implementation methods live in
``_pipeline_grid.py``, ``_pipeline_route.py``, and ``_pipeline_verify.py``
and are patched onto the class at import time.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from temper_placer.router_v6._pipeline_grid import (
    _compute_resource_bound,
    _run_stage2,
)
from temper_placer.router_v6._pipeline_route import (
    _augment_with_pcl_constraints,
    _run_stage3,
    _run_stage4,
    _run_stage5,
    _select_sat_nets,
)
from temper_placer.router_v6._pipeline_types import (
    ManufacturingDRCViolationError,
    RouterV6Result,
    Stage3Output,
)
from temper_placer.router_v6._pipeline_verify import (
    _run_fence,
    _run_manufacturing_drc,
    _stage_0_5_invariants,
    _stage_1_invariants,
    _stage_4_invariants,
)
from temper_placer.router_v6.dense_package_detection import identify_dense_packages
from temper_placer.router_v6.escape_via_generator import generate_escape_vias
from temper_placer.router_v6.placement_legalization import Legalizer
from temper_placer.validation.drc_fence import DRCFence


class RouterV6Pipeline:
    """Router V6 end-to-end pipeline."""

    def __init__(
        self,
        verbose: bool = False,
        enable_theta_star: bool = True,
        enable_lazy_theta_star: bool = True,
        enable_smoothing: bool = False,
        enable_legalization: bool = True,
        max_nets: int | None = None,
        target_nets: list[str] | None = None,
        fence: DRCFence | None = None,
        profiler: Any | None = None,
        skip_stage3: bool = False,
        congestion_weight: float = 0.0,
        max_iter: int = 500_000,  # proven sweet spot: faster AND better closure than 1M
        enable_manufacturing_drc: bool = False,
        dfm_fail_on: str = "critical",
        max_sat_nets: int | None = None,
        enable_bundling: bool = False,
        enable_coarse_to_fine: bool = True,
        coarse_factor: int = 4,
        corridor_buffer_cells: int = 12,
        enable_numba_los: bool = True,
        single_layer: bool = False,
        layer_constraints: dict[str, Any] | None = None,
        thermal_flat: Any = None,  # U8: (N,) float32 cost field
        thermal_weight: float = 0.0,  # U8: multiplier
        enable_all_pad_tree: bool = False,
        enable_zone_pours: bool = False,
        enable_connectivity_verifier: bool = False,
        enable_erc_check: bool = False,
    ):
        """
        Initialize Router V6 pipeline.

        Args:
            verbose: Enable verbose logging
            enable_theta_star: Use Theta* any-angle routing (Experiment F)
            enable_lazy_theta_star: Use Lazy Theta* (Experiment O4)
            enable_smoothing: Apply force-directed smoothing (Experiment G)
            enable_legalization: Verify that the constraint-aware placement
                has no component overlaps before routing.
            max_nets: Limit number of nets to route (for profiling)
            target_nets: List of specific net names to route
            fence: Optional DRCFence for per-stage DRC verification
            profiler: Optional PipelineProfiler for stage timing instrumentation
            congestion_weight: U7 / R11 PathFinder history-cost
                weight.  0.0 (default) disables — the closure
                test does not benefit from the detour behavior
                on temper.kicad_pcb's hard signal nets.
            max_iter: Per-A* iteration cap.  Default 1M (kernel
                default).  On temper.kicad_pcb the path-quality
                sweet spot is 500k -- 1M hits a different
                tie-break for SPI_MOSI and fails it (95.83% vs
                100.0%).  Closure-test adapter should pass
                500_000 to match the SM1 measurement table
                recorded in
                docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md.
            enable_manufacturing_drc: Run DFM checks after routing
                (teardrops, acid traps, annular rings, thermal
                relief, copper balance, creepage, clearance).
            dfm_fail_on: Gate threshold -- "none" (never block),
                "critical" (block on critical violations), or
                "all" (block on any violation).  Default "critical".
            enable_bundling: Enable net bundling with type-gated lazy
                grounding (R9). When True, nets are partitioned into
                bundle equivalence classes and only Safety constraints
                are encoded eagerly; Performance constraints are lazily
                grounded via CEGAR loop. Deprecated max_sat_nets if set.
            thermal_flat: U8 optional (N,) float32 thermal cost field
                (from CostFieldInput.cost_flat).  Threaded to A*
                kernel step-cost.
            thermal_weight: U8 multiplier on per-cell thermal cost
                (from CostFieldInput.weight).  0.0 = field-off.
            enable_all_pad_tree: Enable experimental all-terminal tree
                expansion. Disabled pending production KiCad DRC evidence.
            enable_erc_check: Run kicad-cli pcb erc on the routed board
                after stage-4 geometric realization. Default-off —
                promotion is a separate decision, matching
                enable_connectivity_verifier's discipline (plan
                2026-07-23-001 U2).
        """
        if dfm_fail_on not in ("none", "critical", "all"):
            raise ValueError(
                f"dfm_fail_on must be 'none', 'critical', or 'all', got {dfm_fail_on!r}"
            )
        self.verbose = verbose
        self.enable_theta_star = enable_theta_star
        self.enable_lazy_theta_star = enable_lazy_theta_star
        self.enable_smoothing = enable_smoothing
        self.enable_legalization = enable_legalization
        self.max_nets = max_nets
        self.target_nets = target_nets
        self.fence = fence
        self.profiler = profiler
        self.skip_stage3 = skip_stage3
        self.congestion_weight = congestion_weight
        self.max_iter = max_iter
        self.enable_manufacturing_drc = enable_manufacturing_drc
        self.dfm_fail_on = dfm_fail_on
        self.max_sat_nets = max_sat_nets
        self.enable_bundling = enable_bundling
        self.enable_coarse_to_fine = enable_coarse_to_fine
        self.coarse_factor = coarse_factor
        self.corridor_buffer_cells = corridor_buffer_cells
        self.enable_numba_los = enable_numba_los
        self.single_layer = single_layer
        # U8: thermal cost field (flat float32 + weight) threaded to A* kernel
        self.thermal_flat = thermal_flat
        self.thermal_weight = thermal_weight
        self.enable_all_pad_tree = enable_all_pad_tree
        self.enable_zone_pours = enable_zone_pours
        self.enable_connectivity_verifier = enable_connectivity_verifier
        self.enable_erc_check = enable_erc_check
        # Per-net layer assignments resolved from the netclass SSOT (W2 R2).
        # Maps net name -> LayerAssignment; consumed to constrain layer choice.
        self.layer_constraints = layer_constraints or {}

        # Warn if both max_sat_nets and enable_bundling are set
        if enable_bundling and max_sat_nets is not None:
            import warnings

            warnings.warn(
                "enable_bundling=True supersedes max_sat_nets; max_sat_nets will be ignored.",
                stacklevel=2,
            )

        # Stage ledger: tracks object cardinality across stage boundaries.
        # `fail_on_imbalance` is False by default — ledger violations are
        # warnings, not runtime errors.  Set True for debugging only.
        from temper_placer.router_v6.stage_ledger import StageLedger

        self.ledger = StageLedger(fail_on_imbalance=False)

    def run(
        self,
        pcb_path: Path,
        pcb_override=None,
        net_class_assignments: dict[str, str] | None = None,
    ) -> RouterV6Result:
        """Run complete Router V6 pipeline on a PCB file.

        Args:
            pcb_path: Path to .kicad_pcb file.
            pcb_override: Optional pre-parsed ``ParsedPCB`` to use.
            net_class_assignments: Optional ``{net_name: netclass_name}``
                map to inject into the parsed board's design rules for
                per-net clearance-aware routing (R4 FinePitch 0.15mm).
        """
        start_time = time.time()

        # Stage 0: Load PCB
        if self.verbose:
            print("Stage 0: Loading PCB...")
        from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

        pcb = parse_kicad_pcb_v6(pcb_path)
        if pcb_override is not None:
            pcb = pcb_override

        # Inject per-net netclass assignments and lower default clearance
        # to the SSOT Signal netclass (0.15mm). FinePitch nets (SPI, USB,
        # PWM, I_SENSE, TEMP_SENSE) coexist with other low-voltage signals;
        # 0.15mm is the correct inter-net signal clearance from netclass_rules.yaml.
        if net_class_assignments:
            dr = getattr(pcb, "design_rules", None)
            if dr is not None:
                nc = getattr(dr, "net_class_assignments", {})
                if isinstance(nc, dict):
                    nc.update(net_class_assignments)
                    dr.net_class_assignments = nc
                dr.default_clearance_mm = 0.15

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
                sat_model=None,
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
        )
        self.ledger.checkout("routing_complete", result)
        return result


# Patch per-stage methods onto RouterV6Pipeline.
# The module-level functions (split across _pipeline_grid, _pipeline_route,
# and _pipeline_verify) receive ``self`` as their first argument; assigning
# them as class attributes turns them into bound methods at call time.
RouterV6Pipeline._run_stage2 = _run_stage2
RouterV6Pipeline._compute_resource_bound = _compute_resource_bound
RouterV6Pipeline._select_sat_nets = _select_sat_nets
RouterV6Pipeline._augment_with_pcl_constraints = _augment_with_pcl_constraints
RouterV6Pipeline._run_stage3 = _run_stage3
RouterV6Pipeline._run_stage4 = _run_stage4
RouterV6Pipeline._run_stage5 = _run_stage5
RouterV6Pipeline._run_manufacturing_drc = _run_manufacturing_drc
RouterV6Pipeline._run_fence = _run_fence
