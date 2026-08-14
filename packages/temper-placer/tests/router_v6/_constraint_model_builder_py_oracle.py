"""Verbatim pre-migration oracle for ``ModelBuilder`` (Phase E, batch E1).

Orchestration plan 2026-08-09-001 Phase E E1: the ``ModelBuilder`` model-
building orchestration in ``router_v6/constraint_model.py`` moves to
``temper-design-bundle`` as ``ModelBuilder::build()``. This file is a
VERBATIM snapshot of the pre-migration module -- ``class ModelBuilder`` and
every ``_create_*`` method, the ``ConstraintModel``/``Variable``/
``Constraint`` dataclasses, and the five pure-compute kernels as they were
before Wave 4 delegated them to Rust -- taken from commit ``8dce8f8a^``,
the parent of the Wave-4 kernel-migration commit. Everything after the
``# --- BEGIN PINNED BODY ---`` marker is the unmodified pre-migration
source; its SHA-256 is pinned by
``test_constraint_model_builder_rust_differential.py`` so it can never be
silently edited to agree with the port.

The tail of the pre-migration module that does NOT migrate (``Stage`` /
``BoardState`` glue: ``ConstraintGenerationStage``,
``validate_constraint_generation``) is deliberately omitted -- it stays
Python in the shim and is not part of the migrated surface.

Anti-vacuity: the differential suite drives this oracle against the
*delegated* shim ``ModelBuilder``; the shim must resolve to the Rust
builder (``temper_design_bundle_python.model_builder``), never back onto
this file. ``test_shim_and_oracle_are_different_implementations`` asserts
that structurally.

The oracle is self-contained: its ModelBuilder calls THIS file's
pure-Python kernels and imports only ``pin_world_position`` (outside the
migration scope) from the live package. It consumes networkx Graph
objects and plain dataclasses as inputs; it never touches the Rust
extension.

Re-pin 2026-08-11 (issue #987): ``_point_to_segment_distance`` was the
only kernel here that mirrored a deleted reimplementation
(constraint_model.rs's Wave-4 copy A). It now mirrors the canonical
temper-geometry hypot contract, and the body digest pin in
``test_constraint_model_builder_rust_differential.py`` was updated in the
same commit. Everything else after the marker is still the unmodified
pre-migration source. The re-pin is contract-preserving on real inputs
(≤1-ulp, decision-immune; see
``docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md``).
"""
# --- BEGIN PINNED BODY ---
from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass, field, replace

from temper_placer.core.netlist import Net
from temper_placer.core.pin_geometry import pin_world_position
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


class ConstraintModelEmptyError(RuntimeError):
    """Raised by ``ModelBuilder.build()`` when a non-empty skeleton set
    produces a zero-variable constraint model.

    R10 non-emptiness precondition for Stage 3.1
    (docs/evidence/2026-08-07-router-silent-noop-diagnosis.md): the
    diagnosis traced the router's silent-noop bug all the way to
    ``_create_per_net_channel_vars`` iterating
    ``self.skeletons.items()`` -- with an empty ``skeletons`` dict (the
    Stage 2.3 bug this file does not fix) that loop creates zero
    ``NetChannelVar``s for every net regardless of any other flag, and
    nothing downstream ever noticed. This precondition covers the
    complementary case this module *can* fail on its own: if skeletons
    were genuinely available going into ``build()`` but the resulting
    model still has zero variables, that is a Stage 3 defect in its own
    right, not merely a symptom of an empty upstream dict, and deserves a
    distinct, specific failure rather than proceeding to solve an empty
    SAT model and reporting a misleadingly "successful" completion rate
    from the router's post-Stage-3 fallback path.
    """


#: Decimal places a channel-edge endpoint is quantised to before it becomes
#: part of a SAT variable's identity. 1e-6 mm is one nanometre -- three orders
#: of magnitude below any manufacturing tolerance, so two endpoints that differ
#: only below this are the same physical point.
_EDGE_COORD_DECIMALS = 6


def _edge_endpoint_key(node) -> str:
    """A skeleton node's coordinates, quantised and formatted deterministically.

    Skeleton graph nodes ARE raw coordinate tuples (`channel_skeleton.py` does
    `G.add_node(p1, pos=p1)`), so interpolating a node straight into an f-string
    embeds `repr()` of un-rounded floats. Two geometrically identical skeletons
    produced by different code paths then yield different SAT variable NAMES.
    """
    return "(" + ", ".join(f"{round(float(c), _EDGE_COORD_DECIMALS):.6f}" for c in node) + ")"


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
    """
    rows = []
    for u, v in graph.edges:
        ku, kv = _edge_endpoint_key(u), _edge_endpoint_key(v)
        if kv < ku:
            u, v, ku, kv = v, u, kv, ku
        rows.append((ku, kv, u, v))
    rows.sort(key=lambda r: (r[0], r[1]))
    for i, (ku, kv, u, v) in enumerate(rows):
        yield f"{layer_name}_E{i}_{ku}_{kv}", u, v


@dataclass(kw_only=True)
class Variable:
    """Base class for routing variables."""

    name: str
    var_type: str  # "bool", "int", "continuous"


@dataclass(kw_only=True)
class NetChannelVar(Variable):
    """
    Variable representing if a net uses a specific channel segment.
    uses[net_id, channel_id]
    """

    net_idx: int
    channel_id: str  # Unique ID for channel edge (e.g. "L1_E5")
    var_type: str = "bool"


@dataclass(kw_only=True)
class NetLayerVar(Variable):
    """
    Variable representing the layer assignment of a net segment.
    layer[net_id, segment_id]
    """

    net_idx: int
    segment_id: str
    var_type: str = "int"  # Layer index


@dataclass(kw_only=True)
class ViaVar(Variable):
    """
    Variable representing if a via exists for a net at a specific location.
    via[net_id, location_id]

    **Currently unconstrained -- not bundled, by design (2026-08-07,
    docs/evidence/2026-08-07-via-var-characterization.md).** Before adding
    bundling support for this variable (the same treatment
    ``bundle_analyzer.py`` gives ``NetChannelVar``), an audit of every
    ``Constraint`` subclass in this file and every ``InternalConstraint``
    variant in ``temper-rust-router-core/src/types.rs`` found **none of
    them ever reference a ``ViaVar``** -- ``CapacityConstraint``,
    ``DiffPairConstraint``, ``LayerConstraint``, and
    ``ChannelSeparationConstraint`` (and their Rust mirrors) only ever
    hold ``NetChannelVar``/bundle-channel terms. ``extract_topology``
    (``extraction.rs``) also only parses ``uses_``-prefixed solved
    variable names -- a ``via_N...`` name never matches, so a via var's
    solved value (arbitrary, since nothing constrains it) is never read
    back either. Separately, the pipeline's actual physical via placement
    (``via_placement.place_vias``, Stage 4) derives via locations directly
    from A*-pathfinding layer transitions, entirely independent of this
    SAT variable. Net effect: today, a ``ViaVar`` is a free boolean that
    costs a CNF variable slot and Python construction memory and
    influences nothing. Bundling would only be a sound optimization of a
    *load-bearing* term; there is no load here to bear, so the higher-
    leverage, equally-sound fix is not creating these variables at all
    (see ``ModelBuilder.enable_via_vars``) until some future feature
    (e.g. via-density/drill-spacing capacity) actually adds a constraint
    that consumes them -- at which point this docstring's "unconstrained"
    claim would need updating alongside that feature, and bundling would
    become a live question worth re-asking.
    """

    net_idx: int
    location_id: str  # Unique ID for potential via location (node)
    var_type: str = "bool"


@dataclass(kw_only=True)
class OrderVar(Variable):
    """
    Variable representing relative ordering of two nets in a channel.
    order[net1_idx, net2_idx, channel_id]
    True if net1 is "before" net2 in channel.
    """

    net1_idx: int
    net2_idx: int
    channel_id: str
    var_type: str = "bool"


ESL_REGISTRY: dict[str, type] = {}
"""Registry mapping constraint type names to their classes with ``esl()`` methods.

# @req(2026-06-28-006, FR-LANG2): Each constraint type has exactly one esl() method
# @req(2026-06-28-006, FR-ADOPT1): New constraint types register here

Used by the CI adoption gate to verify every ``Constraint`` subclass has an
ESL declaration.  Populated by each constraint class at import time.
"""


@dataclass(kw_only=True)
class Constraint:
    """Base class for routing constraints.

    Each subclass MUST implement:
    - esl() -> Callable[[dict[str, bool]], bool]: ESL predicate for BMC verification
    - Registration in ESL_REGISTRY dict

    # @req(2026-06-28-006, FR-ADOPT1): Contribute exactly one encoding branch
    """

    name: str
    description: str = ""


@dataclass(kw_only=True)
class CapacityConstraint(Constraint):
    """
    Constraint: sum(uses[n,c] * width[n]) <= capacity[c] * slack

    **AtMostK encoding soundness proof (R24 item 1) — re-homed 2026-08-02
    from ``docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md``
    (plan 2026-08-02-004 U1).** The CNF encoding of this constraint's
    ``esl()`` semantics (``sum(width_i * uses_i) <= capacity * slack``,
    equivalently ``sum(vars) <= K`` with ``K = capacity * slack / min_width``)
    is the Sinz (2005) **sequential counter**: ``sum(vars) <= K`` in O(n*k)
    auxiliary variables and O(n*k) clauses.  The encoding is **exact — sound
    AND complete**: a SAT assignment exists iff the capacity bound holds, the
    strongest form of the R24 conservative-bound branch (it can never admit
    an assignment the capacity bound forbids, and it rejects no assignment
    the bound permits).

    Induction (k-induction over n = |terms|): the auxiliary variables
    ``s[i][j]`` form the transitive closure of partial sums — ``s[i][j]`` is
    true iff at least j+1 of ``vars[0..i]`` are true.  Base case n <= 1 is
    vacuous (no auxiliary variables; a single term is within capacity iff its
    coefficient fits, which the unit clauses enforce).  Step n -> n+1: the
    new term only *extends* the chain with clauses over previously defined
    variables, so the existing counter's semantics are unaffected.  The
    broken predecessor encoding (a single "at least one surplus variable
    false" clause) is the documented counterexample this replaces: for K=3,
    N=10 it admitted 6 nets.  Exhaustive verification: all n <= 8, all
    k <= n-1, all 2^n primary assignments (3,286 SAT checks, 0.06s) via the
    mini DPLL solver, plus Hypothesis PBT cross-validation against pysat
    Glucose3 (91 BMC tests in ``tests/router_v6/``).

    **Physics-gated surface (KTD4):** ``physics_gated: true`` — the encoded
    capacity bound limits the total routed width of a channel, a physical
    routing resource in the same family as the ampacity-derived width bounds
    ``core/ipc2152`` enforces. See the register entry in
    ``power_pcb_dataset/physics_soundness_register.yaml``.
    """

    channel_id: str
    capacity: float
    slack_factor: float
    terms: list[tuple[NetChannelVar, float]]  # (variable, coefficient/width)

    def esl(self):
        """Return an ESL predicate for this capacity constraint.

        # @req(2026-06-28-006, FR-LANG2): Constraint ESL declaration

        The predicate is True iff at most *max_nets* of the term variables
        are True in the assignment, where *max_nets* = capacity * slack / min_width.
        """
        min_width = min(width for _, width in self.terms)
        max_nets = int(self.capacity * self.slack_factor / min_width)
        var_names = [var.name for var, _ in self.terms]
        return lambda ass: sum(1 for v in var_names if ass.get(v, False)) <= max_nets


ESL_REGISTRY["CapacityConstraint"] = CapacityConstraint


@dataclass(kw_only=True)
class DiffPairConstraint(Constraint):
    """
    Constraint: uses[p_net, channel] == uses[n_net, channel]
    Ensures both nets of a differential pair follow the same path.
    """

    channel_id: str
    p_net_idx: int
    n_net_idx: int
    p_var: NetChannelVar
    n_var: NetChannelVar

    def esl(self):
        """Return an ESL predicate: p_var iff n_var (both True or both False).

        # @req(2026-06-28-006, FR-LANG2): Constraint ESL declaration
        """
        p_name = self.p_var.name
        n_name = self.n_var.name
        return lambda ass: ass.get(p_name, False) == ass.get(n_name, False)


ESL_REGISTRY["DiffPairConstraint"] = DiffPairConstraint


@dataclass(kw_only=True)
class LayerConstraint(Constraint):
    """
    Constraint: uses[n, c] == value (usually 0 or 1)
    Restricts a net to a specific layer for a given channel.
    """

    net_idx: int
    channel_id: str
    allowed: bool

    def esl(self):
        """Return an ESL predicate: var == allowed.

        # @req(2026-06-28-006, FR-LANG2): Constraint ESL declaration
        """
        var_name = f"uses_N{self.net_idx}_{self.channel_id}"
        return lambda ass: ass.get(var_name, False) == self.allowed


ESL_REGISTRY["LayerConstraint"] = LayerConstraint


@dataclass(kw_only=True)
class ChannelSeparationConstraint(Constraint):
    """
    Constraint: nets from group A and group B must not share channels
    within `min_slots` slots of each other.

    Encodes the SAT grounding of PCL SeparatedConstraint. For a given
    channel, enforces at least `min_slots` empty slots between nets
    from the two groups via OrderVar-based separation.
    """

    group_a_indices: list[int]
    group_b_indices: list[int]
    min_slots: int
    channel_id: str


@dataclass
class ConstraintModel:
    """
    SAT/SMT Constraint Model for Topological Routing.

    # @req(2026-06-28-006, FR-LANG2): Constraints contribute ESL predicates
    # @req(2026-06-28-006, FR-BMC1): BMC verifies ESL vs CNF agreement

    Holds all variables and constraints (in abstract form).
    Each constraint exposes an ``esl()`` method returning a declarative
    predicate that is verified against the CNF encoding by the BMC layer.

    The ``eval_esl(model, assignment)`` function in ``esl.py`` evaluates
    all constraint ESL predicates against a primary-variable assignment.
    """

    variables: list[Variable] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    net_channel_vars: dict[tuple[int, str], NetChannelVar] = field(default_factory=dict)
    #: Bundle-level channel variables, keyed by ``(bundle_id, channel_id)``.
    #: Kept in a SEPARATE dict from ``net_channel_vars`` -- both a
    #: ``NetChannelVar``'s ``net_idx`` (real net index, 0..n_nets-1) and a
    #: bundle var's ``net_idx`` (bundle id, 0..bundle_count-1, stored in the
    #: same field for historical reasons -- see ``_create_bundle_channel_vars``)
    #: are small integers starting at 0, so a single shared dict keyed by
    #: ``(net_idx, channel_id)`` silently collides the two ID spaces: a real
    #: net whose index happens to equal some bundle's id would either find
    #: no entry (net_idx not numerically a bundle id -> capacity constraint
    #: silently drops that net's term) or find the WRONG entry (a bundle
    #: var, contributing that bundle's constraint term under the real net's
    #: identity). Found and fixed 2026-08-07,
    #: docs/evidence/2026-08-07-sat-model-reduction-options.md Sec 3.3;
    #: regression test: test_bundled_capacity_constraints.py::
    #: test_net_index_bundle_id_collision_does_not_corrupt_capacity.
    bundle_channel_vars: dict[tuple[int, str], NetChannelVar] = field(default_factory=dict)
    via_vars: dict[tuple[int, str], ViaVar] = field(default_factory=dict)

    def add_variable(self, var: Variable) -> None:
        self.variables.append(var)
        if isinstance(var, NetChannelVar):
            if var.var_type == "bundle":
                self.bundle_channel_vars[(var.net_idx, var.channel_id)] = var
            else:
                self.net_channel_vars[(var.net_idx, var.channel_id)] = var
        elif isinstance(var, ViaVar):
            self.via_vars[(var.net_idx, var.location_id)] = var

    def add_constraint(self, constraint: Constraint) -> None:
        self.constraints.append(constraint)

    @property
    def variable_count(self) -> int:
        return len(self.variables)

    @property
    def constraint_count(self) -> int:
        return len(self.constraints)


#: Default detour-factor headroom for geographic pruning (matches
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

    Re-pinned 2026-08-11 (issue #987) to the canonical temper-geometry
    contract (creepage_check): the Wave-4 ``sqrt``/``if/elif/else`` copy this
    oracle used to mirror was deleted.  CPython ``math.hypot`` == the Rust
    ``py_hypot`` Dekker double-double; ``denom == 0`` OR non-finite triggers
    the degenerate arm; builtin ``min``/``max`` clamp a NaN ``t`` to 1.0.
    ``math.sqrt``/``math.hypot`` parity with the Rust kernel on the
    differential corpus is asserted by
    ``test_constraint_model_rust_differential.py`` (whose own ``_oracle_*``
    block carries the same re-pin).
    """
    dx = seg_bx - seg_ax
    dy = seg_by - seg_ay
    denom = dx * dx + dy * dy

    if denom == 0.0 or not math.isfinite(denom):
        return math.hypot(px - seg_ax, py - seg_ay)

    t = ((px - seg_ax) * dx + (py - seg_ay) * dy) / denom
    t = max(0.0, min(1.0, t))

    proj_x = seg_ax + t * dx
    proj_y = seg_ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _pin_world_positions(net: Net, pcb: ParsedPCB) -> list[tuple[float, float]]:
    """Collect the world positions of every pin on *net* from *pcb*.

    Returns an empty list for nets with no assignable pins (e.g. zone-pour
    nets whose pads aren't matched to a component pin).
    """
    positions: list[tuple[float, float]] = []
    for comp in pcb.components:
        for pin in comp.pins:
            if pin.net == net.name:
                pos = pin_world_position(pin, comp)
                positions.append((pos[0], pos[1]))
    return positions


def _dist_min_edge_to_pins(
    edge_ax: float, edge_ay: float,
    edge_bx: float, edge_by: float,
    pin_positions: list[tuple[float, float]],
) -> float:
    """Minimum Euclidean distance from the line segment *edge* to any pin."""
    if not pin_positions:
        return float("inf")
    best = float("inf")
    for px, py in pin_positions:
        d = _point_to_segment_distance(px, py, edge_ax, edge_ay, edge_bx, edge_by)
        if d < best:
            best = d
    return best


def _pin_span(pin_positions: list[tuple[float, float]]) -> float:
    """Maximum Euclidean distance between any two pins."""
    if len(pin_positions) < 2:
        return 0.0
    max_d = 0.0
    for i in range(len(pin_positions)):
        xi, yi = pin_positions[i]
        for j in range(i + 1, len(pin_positions)):
            xj, yj = pin_positions[j]
            d = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2)
            if d > max_d:
                max_d = d
    return max_d


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

    Same predicate shape as ``temper_rust_router_core::pruning::is_candidate_edge``
    (a separate Rust kernel in another crate, out of the 2026-08-11 dedupe's
    scope), but the point-to-segment distance underneath is now the canonical
    temper-geometry hypot contract (issue #987).
    """
    span = _pin_span(pin_positions)
    margin = max(k_factor * span, m_min)
    dist = _dist_min_edge_to_pins(edge_ax, edge_ay, edge_bx, edge_by, pin_positions)
    return dist <= margin


class ModelBuilder:
    """Builder for generating the constraint model from skeletons and nets."""

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
        # Default False: see ViaVar's own docstring for the audit this
        # relies on (2026-08-07). No Constraint subclass here, no
        # InternalConstraint variant in the Rust encoder, and no reader in
        # extract_topology ever references a ViaVar -- and Stage 4's real
        # via placement is computed independently from A* paths. Until a
        # feature that actually consumes ViaVar exists, creating ~110x
        # (unique node count) of them is pure CNF-var and Python-construction
        # overhead with zero effect on solve correctness or output geometry
        # (~16.9M of them on the production board -- comparable in scale to
        # the entire bundled channel-var term). Opt in explicitly once a
        # real consumer exists.
        self.enable_via_vars = enable_via_vars
        self.model = ConstraintModel()

        # Build net name to index mapping for fast lookup
        self.net_to_idx = {net.name: i for i, net in enumerate(self.nets)}

    def build(self) -> ConstraintModel:
        """
        Generate all variables and constraints for the routing problem.
        """
        t0 = time.perf_counter() if os.environ.get("TEMPER_MODEL_TRACE") else None
        self._create_channel_vars()
        if self.enable_via_vars:
            self._create_via_vars()
        self._create_capacity_constraints()
        self._create_diff_pair_constraints()
        self._create_layer_constraints()
        self._apply_pcl_constraints()
        if t0 is not None:
            # 2026-08-07 U5 measurement instrumentation
            # (docs/plans/2026-08-07-001-feat-router-encoding-pruning-plan.md).
            # Reports the *pre-CNF* Python model size -- NetChannelVar /
            # ViaVar / OrderVar counts and constraint counts -- before the
            # model is handed to the Rust encode_to_cnf + CaDiCaL solve
            # step. The Rust side already emits an "encode_to_cnf done"
            # phase-trace line (TEMPER_REWRITE_TRACE=1) with CNF var/clause
            # counts, but that line only prints if encode_to_cnf finishes;
            # if the encode or solve step OOMs, this earlier print is the
            # only var/constraint count that survives.
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
        # nets to route must produce a non-zero-variable model. Scoped to
        # skeletons+nets both non-empty deliberately -- a board with
        # skeletons but zero nets (or vice versa) legitimately has nothing
        # to build a model from, and is not this bug's shape. An empty
        # `self.skeletons` on a board with routable nets is instead the
        # Stage 2.3 (ChannelSkeleton) failure mode, guarded separately by
        # vacuity_guards.validate_channel_skeleton_nonvacuous.
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

        return self.model

    def _create_channel_vars(self):
        """Create variables for net-channel assignment."""
        if self.enable_bundling and self.bundle_manifest is not None:
            self._create_bundle_channel_vars()
        else:
            self._create_per_net_channel_vars()

    def _create_per_net_channel_vars(self):
        """Create per-net channel variables (unbundled path).

        When ``enable_geographic_pruning`` is True, a ``NetChannelVar``
        is created only if the net's pins are within geographic range of
        the edge (the ``_is_candidate_edge`` predicate).  Otherwise every
        (net, edge) pair gets a variable unconditionally.
        """
        if self.enable_geographic_pruning and self.pcb is not None:
            # Pre-compute pin world positions per net, indexed by net_idx.
            net_pins: dict[int, list[tuple[float, float]]] = {
                net_idx: _pin_world_positions(net, self.pcb)
                for net_idx, net in enumerate(self.nets)
            }

        # 2026-08-07 U5 measurement instrumentation (see build()'s
        # TEMPER_MODEL_TRACE block). This loop is exactly where the 2026-08-07
        # unpruned production-board run raised MemoryError under an 8GB
        # ulimit -v cap -- inside dict-assignment in add_variable(), never
        # reaching build()'s own post-loop print. Printing progress here,
        # gated behind the same env var, means a crash mid-loop still leaves
        # a last-known count instead of zero data.
        trace = os.environ.get("TEMPER_MODEL_TRACE")
        t_loop = time.perf_counter() if trace else None
        report_every = 200_000
        edge_count_by_layer: dict[str, int] = {}

        for net_idx, _net in enumerate(self.nets):
            for layer_name, skeleton in self.skeletons.items():
                if trace and net_idx == 0 and layer_name not in edge_count_by_layer:
                    n_edges = sum(
                        1 for _ in canonical_channel_edges(skeleton.graph, layer_name)
                    )
                    edge_count_by_layer[layer_name] = n_edges
                    print(
                        f"[model-trace] layer={layer_name}: {n_edges} channel-skeleton "
                        f"edges (canonical_channel_edges); running total="
                        f"{sum(edge_count_by_layer.values())}",
                        file=sys.stderr,
                        flush=True,
                    )
                for edge_id, u, v in canonical_channel_edges(skeleton.graph, layer_name):

                    if self.enable_geographic_pruning and self.pcb is not None:
                        pin_positions = net_pins.get(net_idx, [])
                        if not _is_candidate_edge(pin_positions, u[0], u[1], v[0], v[1]):
                            continue

                    var = NetChannelVar(
                        name=f"uses_N{net_idx}_{edge_id}", net_idx=net_idx, channel_id=edge_id
                    )
                    self.model.add_variable(var)

                    if trace and self.model.variable_count % report_every == 0:
                        elapsed = time.perf_counter() - t_loop
                        print(
                            f"[model-trace t={elapsed:.3f}s] "
                            f"_create_per_net_channel_vars progress: "
                            f"net_idx={net_idx}/{len(self.nets)}, "
                            f"vars_so_far={self.model.variable_count}",
                            file=sys.stderr,
                            flush=True,
                        )

        if trace and edge_count_by_layer:
            print(
                f"[model-trace] channel-skeleton edge counts by layer "
                f"(canonical_channel_edges, net_idx=0 pass): {edge_count_by_layer}, "
                f"total={sum(edge_count_by_layer.values())}, "
                f"nets={len(self.nets)}, "
                f"unpruned_upper_bound={sum(edge_count_by_layer.values()) * len(self.nets)}",
                file=sys.stderr,
                flush=True,
            )

    def _create_bundle_channel_vars(self):
        """Create bundle-level channel variables (bundled path).

        Each bundle gets one NetChannelVar per edge with uses_B prefix
        and var_type='bundle'. Unbundled (singleton) nets get per-net
        uses_N variables.

        Works with both full BundleManifest objects (which have .bundles)
        and minimal manifests (which only have bundle_id_for_net and
        unbundled_net_indices).

        ``var_type='bundle'`` routes these into ``ConstraintModel.
        bundle_channel_vars`` (keyed by ``(bundle_id, channel_id)``) rather
        than ``net_channel_vars`` (keyed by ``(net_idx, channel_id)``) --
        see that field's docstring for why sharing one dict between the two
        ID spaces was a real bug (2026-08-07, Sec 3.3 of
        docs/evidence/2026-08-07-sat-model-reduction-options.md).
        """
        manifest = self.bundle_manifest
        bundle_id_for_net: dict[int, int] = getattr(manifest, "bundle_id_for_net", {})
        set(getattr(manifest, "unbundled_net_indices", []))

        # Collect unique bundle IDs and the nets in each bundle
        unique_bundle_ids: set[int] = set(bundle_id_for_net.values())

        # 2026-08-07 (docs/evidence/2026-08-07-sat-model-reduction-options.md
        # Sec 3.4): this loop is where the bundled path's own MemoryError
        # fires -- the exact same failure mode (add_variable's dict
        # assignment) as _create_per_net_channel_vars, which already has
        # TEMPER_MODEL_TRACE progress instrumentation (U5). This path had
        # none, so a bundled-path OOM previously left zero partial data.
        # Mirrors that instrumentation here for parity.
        trace = os.environ.get("TEMPER_MODEL_TRACE")
        t_loop = time.perf_counter() if trace else None
        report_every = 200_000
        if trace:
            print(
                f"[model-trace] _create_bundle_channel_vars: {len(unique_bundle_ids)} "
                f"bundle(s), {len(bundle_id_for_net)} bundled net(s) of {len(self.nets)} total",
                file=sys.stderr,
                flush=True,
            )

        for bid in sorted(unique_bundle_ids):
            for layer_name, skeleton in self.skeletons.items():
                for edge_id, u, v in canonical_channel_edges(skeleton.graph, layer_name):

                    var = NetChannelVar(
                        name=f"uses_B{bid}_{edge_id}",
                        net_idx=bid,
                        channel_id=edge_id,
                        var_type="bundle",
                    )
                    self.model.add_variable(var)

                    if trace and self.model.variable_count % report_every == 0:
                        elapsed = time.perf_counter() - t_loop
                        print(
                            f"[model-trace t={elapsed:.3f}s] "
                            f"_create_bundle_channel_vars progress (bundle phase): "
                            f"bundle_id={bid}, vars_so_far={self.model.variable_count}",
                            file=sys.stderr,
                            flush=True,
                        )

        # Create per-net vars for unbundled nets
        bundled_net_indices: set[int] = set(bundle_id_for_net.keys())
        for net_idx, _net in enumerate(self.nets):
            if net_idx in bundled_net_indices:
                continue
            # Also skip nets that are explicitly unbundled (redundant but safe)
            for layer_name, skeleton in self.skeletons.items():
                for edge_id, u, v in canonical_channel_edges(skeleton.graph, layer_name):

                    var = NetChannelVar(
                        name=f"uses_N{net_idx}_{edge_id}", net_idx=net_idx, channel_id=edge_id
                    )
                    self.model.add_variable(var)

                    if trace and self.model.variable_count % report_every == 0:
                        elapsed = time.perf_counter() - t_loop
                        print(
                            f"[model-trace t={elapsed:.3f}s] "
                            f"_create_bundle_channel_vars progress (unbundled-net phase): "
                            f"net_idx={net_idx}/{len(self.nets)}, "
                            f"vars_so_far={self.model.variable_count}",
                            file=sys.stderr,
                            flush=True,
                        )

    def _create_via_vars(self):
        """Create variables for via placement.

        Only called from ``build()`` when ``enable_via_vars`` is True
        (default False — see ``ModelBuilder.__init__`` and ``ViaVar``'s own
        docstring for why: these variables are unconstrained and unread by
        every consumer audited 2026-08-07).

        Count formula: ``len(self.nets) * n_unique_node_locations``, where
        ``n_unique_node_locations`` is the number of distinct ``(x, y)``
        coordinates across the union of every layer skeleton's graph nodes
        (deduplicated across layers, since a via's location is layer-
        independent — it is the thing that *connects* layers). On the
        204,490-edge production skeleton this is 153,432 unique locations x
        110 nets ~= 16.9M variables — comparable in scale to the entire
        18,404,100-variable bundled channel-var term this same task's sibling
        work reduced.

        When ``enable_geographic_pruning`` is True, a ``ViaVar`` is
        created only if the via-anchor node is within geographic range
        of the net's pins (the same ``_is_candidate_edge`` predicate,
        using a zero-length "edge" at the node position — so
        ``_point_to_segment_distance`` degenerates to point-to-point
        distance, which is the intended behaviour). Measured elsewhere
        (docs/evidence/2026-08-07-pruned-encoding-measurement.md) this
        pruning is ~0% effective on the production board (nets are not
        spatially local), so it would not meaningfully shrink this count
        even if ``enable_via_vars`` were turned back on.
        """
        # Collect all unique node locations across all skeletons
        all_nodes = set()
        for skeleton in self.skeletons.values():
            for node in skeleton.graph.nodes:
                all_nodes.add(node)  # node is (x, y) tuple

        # Sort for stability
        sorted_nodes = sorted(all_nodes)

        if self.enable_geographic_pruning and self.pcb is not None:
            net_pins: dict[int, list[tuple[float, float]]] = {
                net_idx: _pin_world_positions(net, self.pcb)
                for net_idx, net in enumerate(self.nets)
            }

        for net_idx, _net in enumerate(self.nets):
            for i, node in enumerate(sorted_nodes):
                if self.enable_geographic_pruning and self.pcb is not None:
                    pin_positions = net_pins.get(net_idx, [])
                    # Via at node: treat as a degenerate (zero-length) edge.
                    # _is_candidate_edge with equal endpoints → point-to-point
                    # distance.
                    if not _is_candidate_edge(pin_positions, node[0], node[1], node[0], node[1]):
                        continue

                node_id = f"VIA_N{i}_{node[0]:.2f}_{node[1]:.2f}"

                var = ViaVar(name=f"via_N{net_idx}_{node_id}", net_idx=net_idx, location_id=node_id)
                self.model.add_variable(var)

    def _net_width(self, net_idx: int) -> float:
        """A net's physical footprint on a channel: trace width + spacing."""
        rule = self.design_rules.get_rules_for_net(self.nets[net_idx].name)
        return rule.trace_width_mm + rule.clearance_mm

    def _create_capacity_constraints(self):
        """
        Create capacity constraints for each channel.
        sum(uses[n, c] * width[n]) <= capacity[c] * 0.8

        **Bundled path, and the net-index/bundle-id collision fix
        (2026-08-07, docs/evidence/2026-08-07-sat-model-reduction-options.md
        Sec 3.3):** ``_create_bundle_channel_vars`` stores one shared
        channel variable per *bundle*, keyed by ``bundle_id`` -- a
        different, smaller index space than real net indices, but
        previously stored in the SAME ``net_channel_vars`` dict, so a real
        net whose index numerically coincided with some bundle's id would
        either silently get no capacity term (no true collision) or get
        the WRONG term (a bundle's variable, misattributed as that net's
        own). ``ConstraintModel`` now keeps bundle variables in a separate
        ``bundle_channel_vars`` dict (see its own docstring), so that
        collision can no longer happen structurally.

        A bundle's shared variable stands in for every net inside that
        bundle using the edge *together* (see ``bundle_analyzer.py``'s
        soundness note), so its capacity term is the SUM of every member
        net's own ``trace_width_mm + clearance_mm`` -- not one
        representative member's width, and not the bundle's own now-dropped
        exact-match width/clearance (``bundle_analyzer.TypeSignature`` no
        longer requires members to share identical width/clearance; this
        per-member summation is what keeps that widening capacity-sound).
        Nets already covered by a bundle term are excluded from the
        per-net loop below so they are never double-counted.
        """
        if not self.channel_widths or not self.design_rules:
            return

        slack_factor = 0.8

        # Bundle membership for this build, if bundling produced any bundles.
        bundle_id_for_net: dict[int, int] = {}
        bundle_members: dict[int, list[int]] = {}
        if self.enable_bundling and self.bundle_manifest is not None:
            bundle_id_for_net = dict(getattr(self.bundle_manifest, "bundle_id_for_net", {}))
            for net_idx, bid in bundle_id_for_net.items():
                bundle_members.setdefault(bid, []).append(net_idx)

        for layer_name, skeleton in self.skeletons.items():
            widths = self.channel_widths.get(layer_name)
            if not widths:
                continue

            for edge_id, u, v in canonical_channel_edges(skeleton.graph, layer_name):

                # Get capacity (min width of edge)
                # Try both directions
                capacity = widths.edge_widths.get((u, v))
                if capacity is None:
                    capacity = widths.edge_widths.get((v, u), 0.0)

                if capacity <= 0:
                    continue

                terms = []

                # Bundle-level terms: the bundle's shared variable stands
                # in for every member net using this edge at once, so its
                # width contribution is the sum of its members' widths.
                for bid, members in bundle_members.items():
                    bvar = self.model.bundle_channel_vars.get((bid, edge_id))
                    if bvar is None:
                        continue
                    bundle_width = sum(self._net_width(ni) for ni in members)
                    terms.append((bvar, bundle_width))

                # Per-net terms: every net not already covered by a bundle
                # term above (all nets when bundling is off; only the
                # unbundled/singleton nets when it's on).
                for net_idx in range(len(self.nets)):
                    if net_idx in bundle_id_for_net:
                        continue
                    if (net_idx, edge_id) in self.model.net_channel_vars:
                        var = self.model.net_channel_vars[(net_idx, edge_id)]
                        terms.append((var, self._net_width(net_idx)))
                    elif self.enable_geographic_pruning and self.pcb is not None:
                        # Defense-in-depth: if pruning is active, every term
                        # that appears in a capacity constraint for this edge
                        # MUST have been created by _create_per_net_channel_vars,
                        # which already applied the predicate.  A net-variable
                        # that passes the predicate for one edge will NOT be
                        # spuriously invisible here.  Silence is correct — the
                        # net legitimately has no variable on this edge.
                        pass

                if terms:
                    constraint = CapacityConstraint(
                        name=f"cap_{edge_id}",
                        channel_id=edge_id,
                        capacity=capacity,
                        slack_factor=slack_factor,
                        terms=terms,
                    )
                    self.model.add_constraint(constraint)

    def _create_diff_pair_constraints(self):
        """
        Create constraints for differential pairs.
        uses[p_net, c] == uses[n_net, c]

        Skipped when bundling is enabled — diff pairs are tracked
        at the bundle level in the Rust solver.
        """
        if self.enable_bundling:
            return

        for pair in self.diff_pairs:
            if pair.p_net not in self.net_to_idx or pair.n_net not in self.net_to_idx:
                continue

            p_idx = self.net_to_idx[pair.p_net]
            n_idx = self.net_to_idx[pair.n_net]

            for layer_name, skeleton in self.skeletons.items():
                for edge_id, u, v in canonical_channel_edges(skeleton.graph, layer_name):

                    if (p_idx, edge_id) in self.model.net_channel_vars and (
                        n_idx,
                        edge_id,
                    ) in self.model.net_channel_vars:
                        p_var = self.model.net_channel_vars[(p_idx, edge_id)]
                        n_var = self.model.net_channel_vars[(n_idx, edge_id)]

                        constraint = DiffPairConstraint(
                            name=f"diff_{pair.base_name}_{edge_id}",
                            channel_id=edge_id,
                            p_net_idx=p_idx,
                            n_net_idx=n_idx,
                            p_var=p_var,
                            n_var=n_var,
                        )
                        self.model.add_constraint(constraint)

    def _create_layer_constraints(self):
        """
        Create layer constraints for pins.
        Ensures SMD pins only connect to their respective layer.
        """
        if not self.pcb:
            return

        for comp in self.pcb.components:
            comp_x, comp_y = comp.initial_position or (0.0, 0.0)
            float(comp.initial_rotation_quadrant or 0) * math.pi / 2.0

            for pin in comp.pins:
                if not pin.net or pin.net not in self.net_to_idx:
                    continue

                net_idx = self.net_to_idx[pin.net]
                pin_pos = pin_world_position(pin, comp)

                # SMD pins are restricted to one layer
                if not pin.is_pth:
                    target_layer = pin.layer

                    # Find all breakout edges for this pin
                    # A breakout edge is an edge where one endpoint is the pin position
                    for layer_name, skeleton in self.skeletons.items():
                        if layer_name == target_layer:
                            continue  # Allowed

                        # Restricted layer: for all edges connected to this pin position,
                        # set uses[net, edge] == 0
                        for edge_id, u, v in canonical_channel_edges(
                            skeleton.graph, layer_name
                        ):
                            # Check if either endpoint matches pin position (with tolerance)
                            match = False
                            for node in [u, v]:
                                if (
                                    abs(node[0] - pin_pos[0]) < 0.01
                                    and abs(node[1] - pin_pos[1]) < 0.01
                                ):
                                    match = True
                                    break

                            if match:

                                if (net_idx, edge_id) in self.model.net_channel_vars:
                                    self.model.net_channel_vars[(net_idx, edge_id)]
                                    constraint = LayerConstraint(
                                        name=f"layer_restr_N{net_idx}_{edge_id}",
                                        net_idx=net_idx,
                                        channel_id=edge_id,
                                        allowed=False,
                                    )
                                    self.model.add_constraint(constraint)

    def _apply_pcl_constraints(self):
        """Apply PCL constraints to the SAT constraint model (R22).

        When pcl_constraints is provided, compiles them to SAT via the
        SAT bridge and adds the resulting constraints to the model.
        When None, behavior is identical to current (R23).
        """
        if self.pcl_constraints is None:
            return

        try:
            from temper_placer.core.netlist import Netlist
            from temper_placer.pcl.constraints import CompilationContext, CompilationTarget

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

            compiled = self.pcl_constraints.compile(CompilationTarget.SAT, ctx)
            for c_list in compiled:
                if isinstance(c_list, list):
                    for c in c_list:
                        self.model.add_constraint(c)
                elif hasattr(c_list, "name"):
                    self.model.add_constraint(c_list)
        except Exception as e:
            import warnings

            warnings.warn(f"PCL→SAT compilation failed: {e}", stacklevel=2)


