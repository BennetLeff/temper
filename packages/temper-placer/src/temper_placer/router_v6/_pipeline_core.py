"""
Router V6 Pipeline: Core orchestrator class.

Contains ``RouterV6Pipeline.__init__`` (configuration) and ``run``
(orchestration).  Per-stage implementation methods live in
``_pipeline_grid.py``, ``_pipeline_route.py``, and ``_pipeline_verify.py``
and are patched onto the class at import time.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import temper_orchestration as _to

if TYPE_CHECKING:
    from temper_placer.validation.drc_fence import DRCFence

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
    RouterV6Result,
    Stage3Output,
)
from temper_placer.router_v6._pipeline_verify import (
    _run_fence,
    _run_manufacturing_drc,
)

# Stage-0 net ordering data (U-G): the power-first stable net sort keeps
# power/HV nets ahead of signal nets so the final-round displacement of
# SPI/USB/sense nets is prevented. The priority tuples mirror the
# pre-migration run()'s inner constants byte-for-byte.
_SIG = ("SPI_", "I_SENSE", "USB_", "TEMP_")
_PWR = ("GATE_", "PWM_", "DC_BUS", "AC_", "SW_NODE", "VCC_BOOT", "CGND", "PGND", "+", "GND")


def _net_sort_key(net) -> int:
    """The run()'s inner ``_prio`` net-sort key, module-level so the Rust
    RouterPipeline driver can hand it to CPython ``list.sort`` (the sort
    itself stays CPython; the key logic is the migrated orchestration's
    data)."""
    name = net.name if hasattr(net, "name") else str(net)
    if any(name.startswith(p) for p in _PWR):
        return 0
    return 1


def _run_stage0_setup(
    pcb,
    pcb_override=None,
    net_class_assignments: dict[str, str] | None = None,
    net_classes: dict[str, Any] | None = None,
):
    """The run()'s Stage-0 post-parse setup block (U-G boundary): the
    pcb_override swap, the netclass/assignment injection (with the 0.15mm
    Signal default clearance) and the power-first net sort. This is
    Python-object marshalling (dict updates, ``list.sort`` with the key
    callable) — the same category the U-E boundary keeps Python-side — and
    is invoked by the Rust driver right after the parse call-back. Pinned
    against the pre-migration inline block by
    ``test_router_pipeline_rust_differential.py``."""
    if pcb_override is not None:
        pcb = pcb_override

    if net_class_assignments or net_classes:
        dr = getattr(pcb, "design_rules", None)
        if dr is not None:
            if net_class_assignments:
                nc = getattr(dr, "net_class_assignments", {})
                if isinstance(nc, dict):
                    nc.update(net_class_assignments)
                    dr.net_class_assignments = nc
                dr.default_clearance_mm = 0.15
            if net_classes:
                existing = getattr(dr, "net_classes", {})
                if isinstance(existing, dict):
                    existing.update(net_classes)
                    dr.net_classes = existing

    pcb.nets.sort(key=_net_sort_key)
    return pcb


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
        sat_conflict_limit: int | None = 20_000,
        sat_time_limit_ms: int | None = None,
        enable_coarse_to_fine: bool = True,
        coarse_factor: int = 4,
        corridor_buffer_cells: int = 12,
        single_layer: bool = False,
        layer_constraints: dict[str, Any] | None = None,
        thermal_flat: Any = None,  # U8: (N,) float32 cost field
        thermal_weight: float = 0.0,  # U8: multiplier
        enable_all_pad_tree: bool = False,
        enable_zone_pours: bool = False,
        enable_connectivity_verifier: bool = False,
        enable_erc_check: bool = False,
        enable_geographic_pruning: bool = False,
        enable_net_batching: bool = False,
        net_batch_size: int = 10,
        enable_nlayer_astar_spike: bool = False,
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
                That table was measured on a 24-net smoke subset --
                re-swept on the full 96-net production board
                (docs/evidence/2026-07-27-forced-segment-analysis.md):
                500k/1M/2M/4M all produced the *same* 59-net failure
                count (2M and 4M byte-identical), so 500k remains
                justified as "no worse than 8x more compute," not
                because it is a strict local optimum on this board --
                raising this value is not a lever for completion here.
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
            sat_conflict_limit: Bound the Stage 3 CaDiCaL SAT solve to
                at most this many conflicts before giving up and
                returning "unknown" (the pipeline already handles this
                status by falling back to unguided A*, the same path
                skip_stage3=True exercises). Before this bound existed,
                the solve had no limit at all and measured 1,573.8s
                (95.5% of full-board wall time) on temper.kicad_pcb --
                see docs/evidence/2026-07-27-first-route-and-profile.md.
                Default 20_000 conflicts, chosen from the sweep in
                docs/evidence/2026-07-27-sat-bound-tradeoff.md.
                Conflict count is deterministic given a fixed CNF
                (unlike wall-clock time, it does not depend on machine
                load), which is why it is the primary/default bound
                rather than sat_time_limit_ms. Pass None for the old,
                unbounded behavior.
            sat_time_limit_ms: Secondary wall-clock bound on the same
                solve, applied independently via a terminator callback
                (CaDiCaL has no native wall-clock limit). None by
                default -- sat_conflict_limit alone is the recommended
                bound; set this in addition if a hard real-time ceiling
                is also needed (e.g. in a CI job with its own timeout).
                If both are set, whichever fires first wins.
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
            enable_geographic_pruning: Enable geographic pruning of the
                SAT model (U3 of plan 2026-08-07-001). Default False
                (behavior unchanged). When True, NetChannelVar and ViaVar
                variables are created only for edges/nodes within
                max(K * pin_span, M_min) of the net's pins, reducing
                CNF variables and clauses.
            enable_net_batching: Batch Stage 3's SAT solve over
                ``net_batch_size`` nets at a time instead of building one
                model for every net (`#871`'s net-batching prototype, see
                ``net_batching.py``). Default False (behavior unchanged
                -- the existing single-model path is untouched). Mutually
                orthogonal to ``enable_bundling``/``max_sat_nets``; if
                more than one is set, net_batching takes priority (it is
                checked first in ``_run_stage3``).
            net_batch_size: Nets per Stage 3 SAT batch when
                ``enable_net_batching=True``. Default 10, matching the
                reduction survey's own worked estimate (~2.04M raw vars
                per batch, corroborated by a MEASURED 2.6M-variable model
                that already survived construction under an 8GB
                ``ulimit -v`` cap on this same skeleton).
            enable_nlayer_astar_spike: Opt into the N-layer, via-aware A*
                pathfinding SPIKE PROTOTYPE (``_astar_nlayer.py``,
                ``spike/nlayer-via-astar`` branch) instead of the
                production ``run_astar_pathfinding`` (which is hardcoded
                to at most 2 layers -- see ``select_routing_grids`` and
                ``run_astar_pathfinding``'s ``alternate_grid`` singular
                parameter). Default False -- production behavior
                completely unchanged. See
                ``docs/evidence/2026-08-08-nlayer-via-astar-spike.md`` for
                what this buys, what it doesn't, and why it is not wired
                in as the default. Not combined with
                ``enable_all_pad_tree`` -- the spike's driver does not
                implement the experimental all-terminal-tree path (see
                ``_astar_nlayer.py``'s module docstring).
        """
        del enable_connectivity_verifier  # inherited unused arg (baseline debt)
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
        self.sat_conflict_limit = sat_conflict_limit
        self.sat_time_limit_ms = sat_time_limit_ms
        self.enable_coarse_to_fine = enable_coarse_to_fine
        self.coarse_factor = coarse_factor
        self.corridor_buffer_cells = corridor_buffer_cells
        self.single_layer = single_layer
        # U8: thermal cost field (flat float32 + weight) threaded to A* kernel
        self.thermal_flat = thermal_flat
        self.thermal_weight = thermal_weight
        self.enable_all_pad_tree = enable_all_pad_tree
        self.enable_zone_pours = enable_zone_pours
        self.enable_erc_check = enable_erc_check
        # U3: geographic SAT-model pruning (plan 2026-08-07-001)
        self.enable_geographic_pruning = enable_geographic_pruning
        # `#871` net-batching prototype (see net_batching.py)
        self.enable_net_batching = enable_net_batching
        self.net_batch_size = net_batch_size
        # Spike prototype opt-in (see enable_nlayer_astar_spike's docstring
        # above). Default False -- production behavior unchanged.
        self.enable_nlayer_astar_spike = enable_nlayer_astar_spike
        self.last_batch_results: list[Any] = []
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
        net_classes: dict[str, Any] | None = None,
    ) -> RouterV6Result:
        """Run complete Router V6 pipeline on a PCB file.

        Orchestration-port unit U-G (Rust Orchestration Engine plan
        2026-08-09-001): the stage SEQUENCING — Stage 0 load → Stage 0.5
        legalization → Stage 1 escape vias → Stage 2 channel analysis →
        Stage 3 topological routing → Stage 4 geometric realization →
        Stage 5 manufacturing DRC → result assembly, with the per-stage
        fences, the ledger checkin/checkout calls, the verbose print
        orchestration, the wall-clock runtime and the exception
        propagation — is implemented in Rust (``temper-orchestration``'s
        ``RouterPipeline`` pyclass), which drives the stages through the
        Rust ``PipelineRunner<BoardState>`` and calls the Python stage
        call-backs (the leaf compute: parsing, the Stage-0 setup
        marshalling, legalization, escape-via generation, the ortools /
        CP-SAT Stage 3 solve, the A* Stage 4, the DFM checks, the fences,
        the ledger and the ERC gate). The R7 skip decision is resolved
        here (its branch text is pinned by test_wave3_skip_sat.py); the
        driver consumes the resolved Stage3Output.

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
        if self.skip_stage3:
            if self.verbose:
                print("Stage 3: Topological routing... SKIPPED")
            _stage3 = Stage3Output(
                constraint_model=None,
                solution=None,
                topology_graph=None,
            )
        else:
            _stage3 = None
        return _to.RouterPipeline().run(
            self,
            pcb_path,
            pcb_override,
            net_class_assignments,
            net_classes,
            _stage3,
        )


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
