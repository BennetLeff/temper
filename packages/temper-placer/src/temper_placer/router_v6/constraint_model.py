"""
Router V6 Stage 3.1: Build Constraint Model

Defines the variables and constraints for the routing solver.
Part of temper-atsd (Stage 3 - Topological Routing)

Phase E batch E1 (rust-orchestration-engine plan 2026-08-09-001): the
``ModelBuilder`` model-building orchestration and the constraint-model data
model move to ``temper-design-bundle`` (the ``temper_design_bundle_python
.model_builder`` submodule) as the ``ModelBuilder``/``ConstraintModel``/
``Variable``/``Constraint`` pyclasses. This module keeps the pre-migration
public API unchanged and re-exports the Rust pyclasses (the pure-delegation
pattern, mirroring ``core/net_types.py``).

What stays Python (see the ``model_builder.rs`` module docstring for the
full split):

- ``ModelBuilder.build()``'s PCL application step (``_apply_pcl_constraints``)
  -- the PCL compiler (``temper_placer.pcl.constraints``) is Python-owned.
- ``ModelBuilder.build()``'s ``TEMPER_MODEL_TRACE`` build summary and the R10
  non-emptiness precondition, which interleave with the PCL step.
- The ortools encoder boundary (``placer/cp_sat/model.py`` /
  ``_encoder_solve.py`` / ``unsat.py``) -- the model this builder returns is
  consumed by ``temper_rust_router.solve_topology_rust``, and the ortools
  boundary itself is a recorded KEEP verdict (plan D4).
- ``ConstraintGenerationStage`` / ``validate_constraint_generation`` --
  ``Stage``/``BoardState`` pipeline glue.
- The ``canonical_channel_edges`` graph iteration (networkx edge order is
  the one remaining construction-order dependence) and the kernel shims.
- The ``esl()``/``ESL_REGISTRY`` ESL machinery is retired: its only
  consumers (``esl.py``/``bmc.py``) were deleted before this migration, no
  caller remains, and the ESL predicate *closures* cannot be represented as
  pyclass methods. ``ESL_REGISTRY`` is kept (it is exported from
  ``router_v6/__init__.py``) populated with the three constraint classes it
  mapped pre-migration.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import replace

import temper_design_bundle_python as _tdb
import temper_geometry as _tg


def _stage3_mem_trace_enabled() -> bool:
    """TEMPER_STAGE3_MEM_TRACE: per-phase PID+RSS entry/exit tracing.

    2026-08-15 Stage 3 memory-blowup investigation: prints
    ``[mem-trace pid=.. rss_kb=..]`` lines to stderr around
    ``ModelBuilder.build()`` so the exact phase where RSS climbs can be
    attributed without attaching a profiler. Off by default -- one
    env::var() call per check, zero cost otherwise. stderr (never stdout)
    so routed-board content and any stdout consumers are unaffected.
    """
    return os.environ.get("TEMPER_STAGE3_MEM_TRACE") is not None


def _stage3_mem_kb() -> int:
    """Current process RSS in KiB from /proc/<pid>/status (or -1)."""
    try:
        with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as _f:
            for _line in _f:
                if _line.startswith("VmRSS:"):
                    return int(_line.split()[1])
    except Exception:
        pass
    return -1


def _stage3_mem_trace(tag: str) -> None:
    if _stage3_mem_trace_enabled():
        print(
            f"[mem-trace pid={os.getpid()} rss_kb={_stage3_mem_kb()}] {tag}",
            file=sys.stderr,
            flush=True,
        )


# Phase E batch E1: the constraint-model data model and the ModelBuilder
# orchestration live in the Rust `model_builder` submodule; these names
# re-export the pyclasses (the pure-delegation pattern, mirroring
# `core/net_types.py`). Attribute access rather than `import
# temper_design_bundle_python.model_builder` — the submodule is registered
# as a parent attribute, not inserted into `sys.modules` (the established
# convention across this crate's shims).
_mb = _tdb.model_builder
CapacityConstraint = _mb.CapacityConstraint
ChannelSeparationConstraint = _mb.ChannelSeparationConstraint
Constraint = _mb.Constraint
ConstraintModel = _mb.ConstraintModel
ConstraintModelEmptyError = _mb.ConstraintModelEmptyError
DiffPairConstraint = _mb.DiffPairConstraint
LayerConstraint = _mb.LayerConstraint
NetChannelVar = _mb.NetChannelVar
NetLayerVar = _mb.NetLayerVar
OrderVar = _mb.OrderVar
Variable = _mb.Variable
ViaVar = _mb.ViaVar

from temper_placer.core.netlist import Net
from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.diff_pair_inference import DiffPair, infer_differential_pairs
from temper_placer.router_v6.stage0_data import DesignRules, ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)

__all__ = [
    "CapacityConstraint",
    "ChannelSeparationConstraint",
    "Constraint",
    "ConstraintModel",
    "ConstraintModelEmptyError",
    "DiffPairConstraint",
    "ESL_REGISTRY",
    "LayerConstraint",
    "ModelBuilder",
    "NetChannelVar",
    "NetLayerVar",
    "OrderVar",
    "Variable",
    "ViaVar",
]
#: only below this are the same physical point.
_EDGE_COORD_DECIMALS = 6

def _edge_endpoint_key(node) -> str:
    """A skeleton node's coordinates, quantised and formatted deterministically.

    Skeleton graph nodes ARE raw coordinate tuples (`channel_skeleton.py` does
    `G.add_node(p1, pos=p1)`), so interpolating a node straight into an f-string
    embeds `repr()` of un-rounded floats. Two geometrically identical skeletons
    produced by different code paths then yield different SAT variable NAMES.

    Wave 4: delegates to the Rust kernel
    ``temper_design_bundle_python.constraint_model.edge_endpoint_key_py``
    (see ``packages/temper-design-bundle/src/constraint_model.rs``), pinned
    bit-exactly by ``tests/router_v6/test_constraint_model_rust_differential.py``.
    """
    return _tdb.constraint_model.edge_endpoint_key_py((float(node[0]), float(node[1])))

def canonical_channel_edges(graph, layer_name: str):
    """Yield ``(edge_id, u, v)`` in an order independent of graph insertion.

    Edge identity previously came from ``enumerate(graph.edges)`` -- i.e. from
    networkx INSERTION ORDER -- plus the raw float repr of both endpoints. That
    made SAT variable names depend on how the skeleton happened to be built,
    which is why `channel_skeleton.py` could not be reimplemented: an
    independent Voronoi reproduces the geometry to <1e-9mm (measured, 12/12
    boards) but not the insertion order, so the model came out different while
    the geometry was identical.

    Ordering here is by the quantised endpoint keys, so it is a property of the
    GEOMETRY rather than of the construction. The index is retained as a
    tie-break, which also keeps names unique if two distinct edges quantise to
    the same endpoints.

    All six call sites must agree byte-for-byte: several build an ``edge_id``
    purely to look it up in ``model.net_channel_vars``, and a mismatch there
    fails silently as a missed constraint rather than an error.

    Wave 4: the key/sort/name computation delegates to the Rust kernel
    ``temper_design_bundle_python.constraint_model.canonical_channel_edges_py``;
    only the networkx edge iteration (whose order is the sole remaining
    construction-order dependence -- the stable-sort tie-break for distinct
    edges that quantise to identical keys) stays in Python, feeding the edges
    in the same order the pre-migration generator iterated them.
    """
    yield from _tdb.constraint_model.canonical_channel_edges_py(
        layer_name, list(graph.edges)
    )

ESL_REGISTRY: dict[str, type] = {}
"""Registry mapping constraint type names to their classes.

Retained for the pre-migration public surface (``router_v6/__init__.py``
exports it) with the same three entries it carried pre-migration. The
``esl()`` predicates themselves are retired -- ``esl.py``/``bmc.py`` (their
only consumers) were deleted before this migration -- so this is now an
informational index, not a code-adoption registry.
"""
ESL_REGISTRY["CapacityConstraint"] = CapacityConstraint
ESL_REGISTRY["DiffPairConstraint"] = DiffPairConstraint
ESL_REGISTRY["LayerConstraint"] = LayerConstraint

#: ``temper-rust-router-core::pruning::PruningParams::k_factor``).
_DEFAULT_PRUNE_K_FACTOR = 2.0

#: Default absolute floor margin in mm for geographic pruning (matches
#: ``temper-rust-router-core::pruning::PruningParams::m_min``).
_DEFAULT_PRUNE_M_MIN = 30.0

def _point_to_segment_distance(
    px: float, py: float,
    seg_ax: float, seg_ay: float,
    seg_bx: float, seg_by: float,
) -> float:
    """Minimum Euclidean distance from point ``(px, py)`` to line segment
    ``(seg_a, seg_b)``.

    When the perpendicular projection falls outside the segment, returns
    the distance to the nearer endpoint.  Degenerate (zero-length) segment
    returns the distance to the single endpoint.

    Wave 4: delegates to the Rust kernel
    ``temper_geometry.point_to_segment_distance_py`` — the canonical
    point-to-segment kernel (issue #987); the design-bundle binding this
    shim used to call was deleted in the dedupe.  Pinned by
    ``tests/router_v6/test_constraint_model_rust_differential.py``.
    """
    return _tg.point_to_segment_distance_py(px, py, seg_ax, seg_ay, seg_bx, seg_by)

def _dist_min_edge_to_pins(
    edge_ax: float, edge_ay: float,
    edge_bx: float, edge_by: float,
    pin_positions: list[tuple[float, float]],
) -> float:
    """Minimum Euclidean distance from the line segment *edge* to any pin.

    Wave 4: delegates to the Rust kernel
    ``temper_design_bundle_python.constraint_model.dist_min_edge_to_pins_py``.
    """
    return _tdb.constraint_model.dist_min_edge_to_pins_py(
        edge_ax, edge_ay, edge_bx, edge_by, pin_positions
    )

def _pin_span(pin_positions: list[tuple[float, float]]) -> float:
    """Maximum Euclidean distance between any two pins.

    Wave 4: delegates to the Rust kernel
    ``temper_design_bundle_python.constraint_model.pin_span_py``.
    """
    return _tdb.constraint_model.pin_span_py(pin_positions)

def _is_candidate_edge(
    pin_positions: list[tuple[float, float]],
    edge_ax: float, edge_ay: float,
    edge_bx: float, edge_by: float,
    k_factor: float = _DEFAULT_PRUNE_K_FACTOR,
    m_min: float = _DEFAULT_PRUNE_M_MIN,
) -> bool:
    """Geographic pruning predicate: is net *n* a candidate for edge *e*?

    ``candidate(n, e) = dist_min(e, P_n) <= M_n``
    where ``M_n = max(K * S_n, M_min)``.

    This is an exact Python replica of
    ``temper_rust_router_core::pruning::is_candidate_edge``.  The
    test ``test_pruning_python_parity_with_rust`` cross-checks.

    Wave 4: delegates to the Rust kernel
    ``temper_design_bundle_python.constraint_model.is_candidate_edge_py``.
    """
    return _tdb.constraint_model.is_candidate_edge_py(
        pin_positions, edge_ax, edge_ay, edge_bx, edge_by, k_factor, m_min
    )

class ModelBuilder:
    """Builder for generating the constraint model from skeletons and nets.

    Phase E batch E1: the build orchestration lives in Rust
    (``temper_design_bundle_python.model_builder.ModelBuilder``); this class
    keeps the pre-migration constructor/``build()`` public API, threads the
    inputs into the Rust builder, and applies the two steps that must stay
    Python (the PCL compilation and the R10 emptiness precondition).
    """

    def __init__(
        self,
        skeletons: dict[str, ChannelSkeleton] | None,
        nets: list[Net],
        channel_widths: dict[str, ChannelWidths] | None = None,
        design_rules: DesignRules | None = None,
        diff_pairs: list[DiffPair] | None = None,
        pcb: ParsedPCB | None = None,
        pcl_constraints=None,
        enable_bundling: bool = False,
        bundle_manifest=None,
        enable_geographic_pruning: bool = False,
        enable_via_vars: bool = False,
        net_filter: list[str] | None = None,
    ):
        self.skeletons = skeletons or {}
        self.nets = nets
        self.channel_widths = channel_widths or {}
        self.design_rules = design_rules
        self.diff_pairs = diff_pairs or []
        self.pcb = pcb
        self.pcl_constraints = pcl_constraints
        self.enable_bundling = enable_bundling
        self.bundle_manifest = bundle_manifest
        self.enable_geographic_pruning = enable_geographic_pruning
        self.enable_via_vars = enable_via_vars
        self.net_filter = net_filter
        self.net_to_idx = {net.name: i for i, net in enumerate(self.nets)}
        self._rust = _mb.ModelBuilder(
            skeletons=self.skeletons,
            nets=self.nets,
            channel_widths=self.channel_widths,
            design_rules=self.design_rules,
            diff_pairs=self.diff_pairs,
            pcb=self.pcb,
            pcl_constraints=self.pcl_constraints,
            enable_bundling=self.enable_bundling,
            bundle_manifest=self.bundle_manifest,
            enable_geographic_pruning=self.enable_geographic_pruning,
            enable_via_vars=self.enable_via_vars,
            net_filter=self.net_filter,
        )
        self.model = ConstraintModel()

    def build(self) -> ConstraintModel:
        """
        Generate all variables and constraints for the routing problem.

        The model-building orchestration itself (channel vars, via vars,
        capacity / diff-pair / layer constraints) runs in Rust; the PCL
        compilation, the ``TEMPER_MODEL_TRACE`` summary and the R10
        non-emptiness precondition stay Python (see the module docstring).
        """
        t0 = time.perf_counter() if os.environ.get("TEMPER_MODEL_TRACE") else None
        _stage3_mem_trace("ModelBuilder.build() ENTER")
        self.model = self._rust.build()
        _stage3_mem_trace("ModelBuilder.build() rust _mb.build() done")
        self._apply_pcl_constraints()
        _stage3_mem_trace("ModelBuilder.build() PCL applied")
        if t0 is not None:
            # 2026-08-07 U5 measurement instrumentation
            # (docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md).
            # Reports the *pre-CNF* Python model size -- NetChannelVar /
            # ViaVar counts and constraint counts -- before the model is
            # handed to the Rust encode_to_cnf + CaDiCaL solve step.
            n_net_channel = sum(
                1 for v in self.model.variables if type(v).__name__ == "NetChannelVar"
            )
            n_via = sum(1 for v in self.model.variables if type(v).__name__ == "ViaVar")
            elapsed = time.perf_counter() - t0
            print(
                f"[model-trace t={elapsed:.3f}s] ModelBuilder.build() done, "
                f"pruning={self.enable_geographic_pruning}, "
                f"primary_vars={self.model.variable_count} "
                f"(net_channel={n_net_channel}, via={n_via}), "
                f"constraints={self.model.constraint_count}",
                file=sys.stderr,
                flush=True,
            )

        # R10 non-emptiness precondition (docs/evidence/2026-08-07-router-
        # silent-noop-diagnosis.md): a non-empty skeleton set with real
        # nets to route must produce a non-zero-variable model.
        if self.skeletons and self.nets and not self.model.variables:
            node_counts = {
                name: len(sk.graph.nodes) for name, sk in self.skeletons.items()
            }
            raise ConstraintModelEmptyError(
                f"ModelBuilder.build() produced 0 variables (0 constraints) "
                f"from {len(self.skeletons)} non-empty skeleton(s) "
                f"({sorted(self.skeletons)!r}, node counts {node_counts!r}) "
                f"and {len(self.nets)} net(s) ({[n.name for n in self.nets][:5]!r}"
                f"{'...' if len(self.nets) > 5 else ''}). A non-empty "
                f"skeleton set must produce a non-zero-variable constraint "
                f"model -- see "
                f"docs/evidence/2026-08-07-router-silent-noop-diagnosis.md."
            )

        _stage3_mem_trace(
            f"ModelBuilder.build() EXIT vars={self.model.variable_count} "
            f"cons={self.model.constraint_count}"
        )
        return self.model

    def _apply_pcl_constraints(self):
        """Apply supplied PCL constraints to the routing constraint model.

        When ``pcl_constraints`` is provided, it is lowered through the
        explicit router compiler and the resulting constraints are added to
        the model.  Compilation errors deliberately propagate: a supplied
        designer constraint must never become an accidental no-op.

        ``None`` means that no PCL constraints were supplied and remains a
        no-op.

        Phase E batch E1: this is the PCL-bound step that stays Python --
        the router compiler owns the PCL-to-router lowering boundary.
        """
        if self.pcl_constraints is None:
            return

        from temper_placer.core.netlist import Netlist
        from temper_placer.pcl.constraints import CompilationContext
        from temper_placer.pcl.router_compiler import compile_pcl_for_router

        # Build a Netlist from available PCB data.
        netlist = Netlist(
            components=self.pcb.components if self.pcb else [],
            nets=self.nets,
        )

        ctx = CompilationContext(
            netlist=netlist,
            board=self.pcb.board if self.pcb else None,
            skeletons=self.skeletons,
            channel_widths=self.channel_widths,
            design_rules=self.design_rules,
        )

        # Do not catch compiler errors here.  The compiler is the single
        # source of truth for supported router lowering, and its contract is
        # fail-closed for every supplied constraint.
        compiled = compile_pcl_for_router(self.pcl_constraints, ctx)
        for constraint in compiled.constraints:
            self.model.add_constraint(constraint)

class ConstraintGenerationStage(Stage):
    """Stage 3.1: Build constraint model from skeletons and nets."""

    @property
    def name(self) -> str:
        return "ConstraintGeneration"

    def run(self, state: BoardState) -> BoardState:
        assert state._parsed_pcb is not None
        pcb: ParsedPCB = state._parsed_pcb
        skeletons = state.channel_skeletons
        channel_widths = state.channel_widths
        diff_pairs = infer_differential_pairs([net.name for net in pcb.nets])
        pcl_constraints = getattr(state, "pcl_constraints", None)
        enable_geographic_pruning: bool = getattr(
            state, "enable_geographic_pruning", False
        )
        model_builder = ModelBuilder(
            skeletons=skeletons,
            nets=pcb.nets,
            channel_widths=channel_widths,
            design_rules=pcb.design_rules,
            diff_pairs=diff_pairs,
            pcb=pcb,
            pcl_constraints=pcl_constraints,
            enable_geographic_pruning=enable_geographic_pruning,
        )
        constraint_model = model_builder.build()
        return replace(state, constraint_model=constraint_model)

@register_validator("ConstraintGeneration")
def validate_constraint_generation(state: BoardState) -> list[StageDRCFailure]:
    failures: list[StageDRCFailure] = []
    cm = state.constraint_model
    if cm is None:
        failures.append(
            StageDRCFailure(
                field="constraint_model",
                value=None,
                reason="Constraint model not generated",
                stage="ConstraintGeneration",
            )
        )
        return failures
    if cm.variable_count == 0 and cm.constraint_count == 0:
        failures.append(
            StageDRCFailure(
                field="constraint_model",
                value=cm.variable_count,
                reason="Constraint model has zero variables and zero constraints",
                stage="ConstraintGeneration",
                fatal=True,
            )
        )
    channel_var_ids = set()
    for var in cm.variables:
        if hasattr(var, "channel_id"):
            if var.channel_id in channel_var_ids:
                failures.append(
                    StageDRCFailure(
                        field="net_channel_vars",
                        value=var.channel_id,
                        reason=f"Duplicate channel variable name: {var.channel_id}",
                        stage="ConstraintGeneration",
                    )
                )
            channel_var_ids.add(var.channel_id)
    return failures
