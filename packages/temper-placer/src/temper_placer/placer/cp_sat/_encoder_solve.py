"""CP-SAT placement solver entry point.

Builds the model, encodes constraints, solves, and returns a result.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import BaseConstraint, ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat import _encoder_core
from temper_placer.placer.cp_sat._encoder_core import (
    EncoderContext,
    encode_constraints,
    validate_constraint_refs,
)
from temper_placer.placer.cp_sat.model import CpSatModel

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.fixed_copper import PadRectLocal

logger = logging.getLogger(__name__)

# Industry-standard solder mask expansion (mm): the mask-expansion term
# of the courtyard clearance τ (C1).  Kept here — not in the Rust crate —
# because it is board/setup data with a TODO to parse it from the board;
# only the arithmetic moves to Rust (``courtyard_clearance_mm``).
MASK_EXPANSION_MM = 0.1

# The real-board local sub-envelope measurement needs roughly 57 seconds in
# the worst partition.  This is a cap, not a promise that the preparation
# phase may consume the whole coarse budget: a reserved fraction below keeps
# the outer envelope model from being starved.
_DEFAULT_DECOMPOSED_LOCAL_PACK_TIMEOUT_MS = 57_000
_DEFAULT_DECOMPOSED_ENVELOPE_HEADROOM_MM = 0.0
_DEFAULT_DECOMPOSED_RESTRICTION_SLACK_MM = 2.0
_DEFAULT_LAZY_POST_CUT_RESERVE_MS = 1_000
_DECOMPOSED_OUTER_RESERVE_FRACTION = 0.20
_HIERARCHICAL_DECOMPOSED_PARTITION_THRESHOLD = 8


def _decomposed_quantization_padding_units(component_count: int) -> int:
    """Reserve model-grid slack for independently rounded component sizes.

    Rust sizes an envelope from aggregate millimetres and the envelope solver
    rounds that aggregate upward.  Component boxes, however, are converted
    independently through the nearest-even ``mm_to_units`` boundary.  Each
    member can therefore consume one extra grid unit relative to the
    aggregate.  Padding every edge by the component count is conservative
    for that quantization only; exact creepage constraints and global
    no-overlap remain authoritative below this boundary.
    """

    if component_count <= 0:
        raise ValueError("decomposed envelope must contain a component")
    return max(1, component_count)


def _refs_by_partition_in_input_order(
    partitions: Sequence[tuple[str, Sequence[str], float, float]],
) -> dict[str, tuple[str, ...]]:
    """Project partition membership without introducing hash order.

    ``prepare_envelope_inputs`` validates and emits ``partitions`` in its
    canonical input order.  Keep that order when materialising the lookup;
    partition membership is metadata, not a set to enumerate.
    """
    return {
        partition_id: tuple(partition_refs)
        for partition_id, partition_refs, _width, _height in partitions
    }


def _authoritative_rotatable_component_refs(
    model_wrapper: CpSatModel,
    component_refs: list[str],
    fixed_rotations: Mapping[str, int] | None,
    fixed_positions: Mapping[str, tuple[float, float, int]] | None,
) -> set[str] | None:
    """Read the model's rotation proof for the coarse-envelope boundary.

    ``CpSatModel`` records components whose rotation is pinned by its
    authoritative geometry model.  The coarse plan must not consult the
    legacy ref-name list or infer rotatability from dimensions.  If that
    model metadata is unavailable or malformed, return ``None`` so envelope
    preparation fails closed with an empty allowlist.
    """

    pinned = getattr(model_wrapper, "_rotation_pinned_refs", None)
    if not isinstance(pinned, set) or any(
        not isinstance(ref, str) for ref in pinned
    ):
        logger.warning(
            "coarse envelope rotation metadata unavailable; disabling partition rotation"
        )
        return None
    refs = set(component_refs)
    if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
        logger.warning(
            "coarse envelope rotation metadata has malformed component refs; "
            "disabling partition rotation"
        )
        return None
    excluded = set(pinned)
    for constrained in (fixed_rotations, fixed_positions):
        if constrained is not None:
            if any(not isinstance(ref, str) or not ref.strip() for ref in constrained):
                logger.warning(
                    "coarse envelope fixed-rotation metadata is malformed; "
                    "disabling partition rotation"
                )
                return None
            excluded.update(constrained)
    return refs - excluded


def _decomposed_restriction_window(
    raw_bounds_units: tuple[int, int, int, int],
    *,
    padding_units: int,
    restriction_slack_units: int,
    margin_units: int,
    board_width_units: int,
    board_height_units: int,
) -> tuple[int, int, int, int]:
    """Expand a coarse envelope window and clamp it to the board interior."""

    if padding_units < 0 or restriction_slack_units < 0:
        raise ValueError("restriction window expansion must be non-negative")
    x_min_raw, y_min_raw, x_max_raw, y_max_raw = raw_bounds_units
    expansion = padding_units + restriction_slack_units
    return (
        max(margin_units, margin_units + x_min_raw - expansion),
        max(margin_units, margin_units + y_min_raw - expansion),
        min(board_width_units - margin_units, margin_units + x_max_raw + expansion),
        min(board_height_units - margin_units, margin_units + y_max_raw + expansion),
    )


def _canonical_creepage_cuts(
    raw_cuts: Sequence[tuple[str, str, float]] | None,
    known_refs: set[str],
) -> list[tuple[str, str, float]]:
    """Validate and max-reduce replayed or verifier-discovered cuts."""

    if raw_cuts is None:
        return []
    if isinstance(raw_cuts, (str, bytes)):
        raise ValueError("decomposed_creepage_prior_cuts must be a sequence")
    reduced: dict[tuple[str, str], float] = {}
    try:
        rows = list(raw_cuts)
    except TypeError as exc:
        raise ValueError("decomposed_creepage_prior_cuts must be a sequence") from exc
    for index, row in enumerate(rows):
        if not isinstance(row, (tuple, list)) or len(row) != 3:
            raise ValueError(f"creepage cut {index} must be (ref_a, ref_b, required_mm)")
        ref_a, ref_b, required_raw = row
        if (
            not isinstance(ref_a, str)
            or not ref_a.strip()
            or not isinstance(ref_b, str)
            or not ref_b.strip()
        ):
            raise ValueError(f"creepage cut {index} has invalid refs")
        if ref_a == ref_b:
            raise ValueError(f"creepage cut {index} cannot reference the same component")
        if ref_a not in known_refs or ref_b not in known_refs:
            raise ValueError(f"creepage cut {index} references an unknown component")
        if (
            isinstance(required_raw, bool)
            or not isinstance(required_raw, (int, float))
            or not math.isfinite(float(required_raw))
            or float(required_raw) < 0.0
        ):
            raise ValueError(f"creepage cut {index} has an invalid required distance")
        key = (ref_a, ref_b) if ref_a < ref_b else (ref_b, ref_a)
        required = float(required_raw)
        reduced[key] = max(required, reduced.get(key, 0.0))
    return [(ref_a, ref_b, reduced[(ref_a, ref_b)]) for ref_a, ref_b in sorted(reduced)]


def _canonical_creepage_violations(
    raw_violations: Sequence[tuple[str, str, float, float]],
    known_refs: set[str],
) -> tuple[tuple[str, str, float, float], ...]:
    """Validate and deterministically max-reduce verifier diagnostics."""

    reduced: dict[tuple[str, str], tuple[float, float]] = {}
    for index, row in enumerate(raw_violations):
        if not isinstance(row, (tuple, list)) or len(row) != 4:
            raise ValueError(
                f"creepage violation {index} must be (ref_a, ref_b, required_mm, gap_mm)"
            )
        ref_a, ref_b, required_raw, gap_raw = row
        if (
            not isinstance(ref_a, str)
            or not ref_a.strip()
            or not isinstance(ref_b, str)
            or not ref_b.strip()
        ):
            raise ValueError(f"creepage violation {index} has invalid refs")
        if ref_a == ref_b:
            raise ValueError(f"creepage violation {index} cannot reference the same component")
        if ref_a not in known_refs or ref_b not in known_refs:
            raise ValueError(f"creepage violation {index} references an unknown component")
        values = (required_raw, gap_raw)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
            for value in values
        ):
            raise ValueError(f"creepage violation {index} has invalid distance data")
        key = (ref_a, ref_b) if ref_a < ref_b else (ref_b, ref_a)
        candidate = (float(required_raw), float(gap_raw))
        prior = reduced.get(key)
        # Keep the strongest required row.  For equal requirements preserve
        # the smallest measured gap as the most informative diagnostic.
        if prior is None or candidate[0] > prior[0] or (
            candidate[0] == prior[0] and candidate[1] < prior[1]
        ):
            reduced[key] = candidate
    return tuple(
        (ref_a, ref_b, required, gap)
        for (ref_a, ref_b), (required, gap) in sorted(reduced.items())
    )


# ---------------------------------------------------------------------------
# Solver result
# ---------------------------------------------------------------------------


@dataclass
class CpSatPlacementResult:
    """Result of a CP-SAT placement solve.

    Carries placed component positions, rotation indices, solve status
    and timing metadata.  This is the interface that the place→route loop
    reads — every field that loop.py accesses must be defined here.
    """

    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    rotations: dict[str, int] = field(default_factory=dict)
    # Retained for feedback-loop compatibility.  New solver results derive
    # this from ``positions`` when absent; legacy callers may provide it
    # explicitly.
    placed_refs: list[str] = field(default_factory=list)
    # Compatibility metadata used by callers that distinguish a proven UNSAT
    # result from a partial/unknown placement.
    unplaced_refs: list[str] = field(default_factory=list)
    status: str = "unknown"  # "optimal" | "feasible" | "infeasible" | "model_invalid"
    solve_time_ms: float = 0.0
    objective_value: float = 0.0
    unsat_core: list[dict] = field(default_factory=list)  # [{name, because}] when infeasible
    # Populated only when solve_placement(isolation_barrier=...) was passed;
    # see isolation_barrier.py::IsolationBarrierReport.
    isolation_barrier_report: object | None = None
    # Populated only when solve_placement(validator_input=...) was passed;
    # see validator_audit.py::DomainClearanceValidatorAuditResult. Carries
    # the REQ-SAFE-01 validator's classified violations (hard failures are
    # raised, not returned; intra-footprint and coverage-gap buckets land
    # here for the caller to act on).
    validator_audit: object | None = None
    # Populated only when solve_placement(tank_creepage=...) was passed;
    # see tank_creepage.py::TankCreepageReport.
    tank_creepage_report: object | None = None
    # Populated only when solve_placement(body_collision_input=...) was
    # passed; see body_collision.py::BodyCollisionAuditResult. A NEW or
    # WORSENED F.Fab body collision raises inside solve_placement rather
    # than landing here (fail-closed); allowlisted (unchanged-or-better)
    # pre-existing collisions are reported on this field for visibility.
    body_collision_audit: object | None = None
    # Lazy generated-creepage diagnostics. A non-zero cut count means the
    # candidate passed CP-SAT but required additional hard separations; an
    # ``unknown`` result with zero cuts may have timed out before a candidate
    # existed and is never a partially verified placement.
    lazy_creepage_rounds: int = 0
    lazy_creepage_constraints_added: int = 0
    # Canonical replayable generated-creepage cuts accumulated from prior
    # seeds and every verifier round, including capped/unknown solves.
    decomposed_creepage_cuts: list[tuple[str, str, float]] = field(default_factory=list)
    # Counts distinguish the canonical replay seed set from verifier cuts
    # discovered during this solve.  A strengthened row is a new cut even
    # when it replaces an existing seed for the same unordered pair.
    decomposed_creepage_prior_cut_count: int = 0
    decomposed_creepage_new_cut_count: int = 0
    # Canonical diagnostics from the last exhaustive Rust verifier call.
    # ``required_mm`` and the measured ``gap_mm`` are retained together so a
    # capped/unknown solve can be diagnosed and replayed without exposing a
    # mutable Rust/Python container.
    decomposed_creepage_remaining_violations: tuple[
        tuple[str, str, float, float], ...
    ] = ()
    decomposed_creepage_group_count: int = 0
    decomposed_creepage_shared_group_pair_count: int = 0
    decomposed_creepage_grouped_cut_count: int = 0
    decomposed_creepage_independent_cut_count: int = 0
    decomposed_creepage_direction_bool_count: int = 0
    # Optional coarse partition-envelope diagnostics.  These remain zero for
    # the default (non-decomposed) solve path.
    decomposed_creepage_partition_count: int = 0
    decomposed_creepage_envelope_solve_time_ms: float = 0.0
    decomposed_creepage_error: str | None = None

    def to_placements_dict(self) -> dict[str, tuple[float, float]]:
        """Return {component_ref: (x_mm, y_mm)} mapping (loop.py interface)."""
        return dict(self.positions)

    def to_rotations_dict(self) -> dict[str, float]:
        """Return {component_ref: rotation_degrees}, converting each solved
        rotation index (0-3) to degrees via ``index * 90.0``.

        **Dense by construction -- every ref in ``self.rotations`` is
        included, even index 0.** This used to filter with ``if idx``
        (dropping index-0 refs to keep the dict "sparse"), on the claimed
        premise that "absence and explicit-zero are handled identically" by
        consumers such as ``_apply_placements_to_pcb``. That premise was
        false: ``_apply_placements_to_pcb`` (and
        ``io/_write_board.py::write_placements_to_pcb``) treat a MISSING ref
        as "no rotation change -- keep the footprint's pre-solve board
        angle" but treat an EXPLICIT ``0.0`` as "write absolute rotation
        0" (they compare ``target_angle is None``, and ``0.0 is not
        None``). For a non-square component (``w0 != h0``) whose pre-solve
        board angle was already non-zero, dropping a genuine solved
        rotation-index-0 decision silently made the writer keep the OLD
        angle -- while the CP-SAT/Pumpkin box (``x_size``/``y_size``, tied
        to ``rot_ref`` via the model's own ``AddElement`` rotation table)
        had been sized for the SOLVED absolute-0 orientation. The written
        footprint then no longer matched the box the solver verified was
        safe, and real pad copper could land outside the board outline
        (measured: forcing a component to solve at rot=0 with a non-zero
        prior board angle and writing through the old filtered dict
        produced real ``check_board_containment.py`` violations; writing
        the same solve through the dense dict produced none -- see
        ``docs/evidence/2026-08-12-component-bounds-rotation-write-back-defect.md``
        for the full measurement, including how many real-board components
        this hit in a single solve, and
        ``tests/placer/cp_sat/test_geometry_constraints_pbt.py``'s rotation-
        consistency regression test).

        The production ``cli/__init__.py`` ``optimize`` command never had
        this bug -- it builds its own dense mapping directly off
        ``cp_result.rotations.get(ref, 0) * 90.0`` for every solved ref
        (see that module's own comment contrasting itself with "the sparse
        to_rotations_dict() shape"), which is now exactly what this method
        also returns.
        """
        return {ref: idx * 90.0 for ref, idx in self.rotations.items()}


# ---------------------------------------------------------------------------
# Solver entry point
# ---------------------------------------------------------------------------


def _lazy_solver_budget_seconds(
    total_timeout_ms: int,
    elapsed_s: float,
    iteration_timeout_ms: int | None,
    reserve_s: float = 0.0,
) -> float:
    """Return the next CP-SAT budget, bounded by total and per-round time."""
    remaining_s = max(0.0, total_timeout_ms / 1000.0 - elapsed_s - reserve_s)
    if iteration_timeout_ms is not None:
        remaining_s = min(remaining_s, iteration_timeout_ms / 1000.0)
    return remaining_s


def solve_placement(
    netlist,
    board,
    extra_constraints: list | None = None,
    timeout_ms: int = 1_000,
    seed: int = 0,
    zones: dict[str, tuple[float, float, float, float]] | None = None,
    loop_components: dict[str, list[str]] | None = None,
    zone_components: dict[str, list[str]] | None = None,
    hint_positions: dict[str, tuple[float, float, int]] | None = None,
    minimize_displacement_to: dict[str, tuple[float, float]] | None = None,
    reference_aliases: Mapping[str, str] | None = None,
    loop_aliases: Mapping[str, str] | None = None,
    fixed_rotations: dict[str, int] | None = None,
    max_displacement_mm: float | None = None,
    isolation_barrier: dict | None = None,
    tank_creepage: dict | None = None,
    heatsink_colocation: int | None = None,
    protective_impedance_colocation: dict | None = None,
    fixed_positions: dict[str, tuple[float, float, int]] | None = None,
    fixed_copper: dict | None = None,
    validator_input: dict | None = None,
    body_collision_input: dict | None = None,
    auto_pairwise_touch_refs: set[str] | None = None,
    lazy_creepage: bool = False,
    lazy_creepage_max_rounds: int = 4,
    lazy_creepage_iteration_timeout_ms: int | None = None,
    decomposed_creepage: bool = False,
    decomposed_creepage_eager_constraints: bool = True,
    decomposed_creepage_prior_cuts: Sequence[tuple[str, str, float]] | None = None,
    decomposed_creepage_group_prior_cuts: bool = False,
    decomposed_creepage_group_max_size: int = 8,
    decomposed_creepage_group_min_cross_edges: int = 3,
    lazy_creepage_post_cut_reserve_ms: int = _DEFAULT_LAZY_POST_CUT_RESERVE_MS,
    decomposed_creepage_envelope_timeout_ms: int = 30_000,
    decomposed_creepage_envelope_workers: int = 16,
    decomposed_creepage_local_pack_timeout_ms: int = _DEFAULT_DECOMPOSED_LOCAL_PACK_TIMEOUT_MS,
    decomposed_creepage_envelope_headroom_mm: float = _DEFAULT_DECOMPOSED_ENVELOPE_HEADROOM_MM,
    decomposed_creepage_restriction_slack_mm: float = _DEFAULT_DECOMPOSED_RESTRICTION_SLACK_MM,
) -> CpSatPlacementResult:
    """Build a CP-SAT model, encode constraints, solve, and return the result.

    This is the single entry point consumed by PlaceRouteLoop and ``temper
    optimize``.  It wires the full pipeline: model creation → PCL encoding
    → solve → position extraction.

    Args:
        hint_positions: Optional warm-start hints.  Dict mapping component
            ref to ``(x_mm, y_mm, rotation_0_3)``.  Hints are seeded via
            ``CpModel.AddHint()`` before solving so CP-SAT searches locally
            from the supplied positions rather than exploring the full space.
        minimize_displacement_to: Optional reference coordinates for an
            opt-in Manhattan-distance objective: ``{ref: (x_mm, y_mm)}``.
            The objective is a *preference*, not a constraint -- hard
            constraints stay authoritative and the solver returns the
            feasible placement closest (in Manhattan distance) to the
            reference.  This is the "minimum-displacement" half of the
            route-aware repair loop (issue #504): a repair solve over a
            routed board starts from the current positions, so components
            only move as far as the clearance constraints force them, and
            the existing routed copper is not disturbed wholesale the way a
            free reshuffle disturbs it.
        reference_aliases: Optional explicit config-to-netlist component
            reference mapping applied before validation. Unmapped names
            remain subject to the fail-closed unresolved-reference policy.
        loop_aliases: Optional explicit mapping for legacy loop names to the
            loop namespace supplied by ``loop_components`` or netlist loop
            extraction.
        fixed_rotations: Optional hard pinning of component rotations to
            their current 0-3 quadrant index: ``{ref: rotation_0_3}``.
            Routed-board repair must not rotate footprints (a rotation moves
            every pad, disconnecting the routed copper attached to it), so
            repair callers pin every ref to its current board rotation.
        max_displacement_mm: Optional hard per-component Manhattan
            displacement bound applied to every ref in
            ``minimize_displacement_to``: each such component may move at
            most ``max_displacement_mm`` in total (|dx| + |dy|). This is
            the bounded-repair formulation -- it *guarantees* the solved
            placement stays inside a displacement envelope around the
            current board (feasibility permitting), rather than trusting
            the objective search to find a low-displacement solution. Only
            meaningful together with ``minimize_displacement_to``.
        fixed_positions: Optional HARD position pins.  Dict mapping component
            ref to ``(x_mm, y_mm, rotation_0_3)``.  Unlike ``hint_positions``,
            these are binding equality constraints -- the solver cannot move a
            pinned ref (it will report ``infeasible`` if a pin conflicts with
            the encoded constraints).  This is the minimal-disruption
            primitive: freeze every component NOT involved in a violation at
            its current board position, and re-solve only the violating
            neighborhood (issue #504).  Rotation is pinned only when the ref
            has a rotation variable (polarized refs are pinned by
            construction to rot=0).
        isolation_barrier: Optional kwargs forwarded to
            ``isolation_barrier.add_isolation_barrier_to_model`` (minus
            ``model``/``netlist``/``board_w_mm``/``board_h_mm``, which this
            function supplies) -- e.g. ``{"manifest_path": Path(...),
            "corridor_width_mm": 8.5, "orientation": "vertical"}``. When
            given, registers the mains<->SELV physical isolation-barrier
            HARD constraint (see ``isolation_barrier.py``) before encoding.
            The resulting report is attached to the returned
            ``CpSatPlacementResult.isolation_barrier_report``.
        tank_creepage: Optional kwargs forwarded to
            ``tank_creepage.add_tank_creepage_to_model`` (minus
            ``model``/``netlist``, which this function supplies) -- e.g.
            ``{"margin_mm": 10.0}``. When given, registers a HARD
            ``separated`` constraint (min_distance_mm=margin_mm, default
            10.0mm/PD3) between every ``tank.c_tank1-p2`` component and
            every other classified-HighVoltage component (see
            ``tank_creepage.py`` for exactly what this does and does not
            guarantee against the IEC 60335-1 Table 18 functional-creepage
            requirement). Same opt-in shape as ``isolation_barrier`` above,
            posted at the same point in the sequence (after every
            component is registered). The resulting report is attached to
            ``CpSatPlacementResult.tank_creepage_report``.
        heatsink_colocation: Optional common rotation index (0-3). When
            given, registers the shared-heatsink co-location HARD
            constraint for every group in
            ``heatsink_colocation.HEATSINK_GROUPS`` -- today, the two
            TO-247 IGBTs (``U5``/``U6``) that bolt to ``HS1``. Without it a
            clean solve is free to return the two devices at rotations 90
            degrees apart, which no single flat heatsink face can contact
            (measured: ``docs/evidence/2026-08-12-igbt-shared-heatsink-hard-constraint.md``).
            Opt-in, and an explicit rotation rather than a bool, because
            the wire vocabulary can only PIN a rotation, not equate two --
            callers that need true equality sweep 0..3. Same opt-in shape
            as ``isolation_barrier`` above.
        protective_impedance_colocation: Optional kwargs for the
            ``protective_impedance_colocation`` safety constraint. The
            mapping must include ``manifest_path`` (or a pre-loaded
            ``chains`` iterable) and may include ``max_gap_mm``. Chain
            membership is resolved from the manifest's interior nets against
            this solve's netlist and is strict/fail-closed: a malformed or
            stale declaration raises instead of silently constraining fewer
            parts. Absent (the default), existing solves are unchanged.
        fixed_copper: Optional pad-vs-fixed-copper NoOverlap constraint set
            (issue #523). A dict with keys ``parse_result`` (a
            ``ParseResult`` carrying ``.traces``/``.vias``/``.board``),
            ``free_refs`` (set of component refs being placed -- their pads
            must not land on different-net fixed copper), ``margin_mm``
            (default 0.05) and ``include_other_pads`` (default True: pinned
            components' pads are obstacles too). When given, the fixed-copper
            constraints are encoded for every free ref and the R24 post-solve
            audit is run on the resolved placement -- a feasible solve with
            audit violations raises (an encoding bug; see ``fixed_copper.py``).
            Absent (default): existing behaviour is unchanged.
        validator_input: Optional validator-aligned post-solve audit
            (issue #523 gap 2). A dict carrying the validator-consumable
            placement and its net-domain map:
            ``{"placement": <validator-shape placement>, "voltage_domains":
            {net: VoltageDomain}}``. When given AND the solve is
            feasible/optimal, the REQ-SAFE-01 validator itself
            (``verify_iec60335_compliance`` -- exact copper-to-copper on pad
            geometry, the function the CI gate runs) is re-run on a placement
            whose positions/rotations come from this solve
            (``validator_audit.audit_domain_clearance_validator``). A
            violation on a constraint-covered inter-component pair (a HARD
            failure) means the box separation the solver SAT did not imply
            the validator's copper separation -- the encoding is unsound for
            this solve and the solve raises, same contract as
            ``audit_fixed_copper``. Intra-footprint straddlers (unfixable by
            placement) and coverage gaps (pairs the generator never
            constrained) are surfaced on ``CpSatPlacementResult.validator_audit``,
            never raised. The cheaper center-distance audit
            (``audit_domain_clearance``) stays independent of this; when
            ``validator_input`` is absent the solve is unchanged. When given
            but the solve does NOT terminate (infeasible/model_invalid/
            unknown) there is no placement to audit -- the skip is logged at
            WARNING, never silent, so an unaudited solve is distinguishable
            from a clean one in the logs.

        body_collision_input: Optional fail-closed ``F.Fab`` body-collision
            post-solve audit (the guard this parameter exists for: commit
            ``de59c0458`` moved 12 components and created a 7.73mm real
            body interpenetration that nothing in the pipeline rejected).
            A dict carrying ``{"fab_bodies": {ref: FabBody}, "allowlist":
            BodyCollisionAllowlist}`` -- see ``body_collision.py`` and
            ``io.fab_body_extraction.extract_fab_bodies``. When given AND
            the solve is feasible/optimal, recomputes true ``F.Fab`` body
            overlap for every component pair with known geometry
            (``body_collision.audit_body_collisions``) and RAISES when any
            pair shows a body collision that is either not on the
            allowlist (a NEW collision) or worse than the allowlist's
            recorded baseline for that pair (a WORSENED pre-existing
            collision) -- both are hard failures, unlike the reportable-
            only intra-footprint/coverage-gap buckets of the validator
            audit above, because there is no placement-independent reason
            for a real body interpenetration to exist. Allowlisted pairs at
            or below baseline are reported on
            ``CpSatPlacementResult.body_collision_audit``, never raised.
            Absent (default): the solve is unaudited for body collisions,
            logged at WARNING when the solve terminated feasible/optimal
            (mirrors validator_input's documented-skip logging) so an
            unaudited solve is distinguishable from a clean one.
       auto_pairwise_touch_refs: Optional restriction on EVERY
            auto-generated (not explicitly requested) pairwise SEPARATED
            constraint family -- both the courtyard tau generator and the
            netclass cross-class generator (issue #504 minimal-disruption
            follow-up). When given, only pairs where at least one ref is in
            this set get an auto-generated constraint. ``None`` (default):
            unrestricted, identical to prior behaviour for every existing
            caller. This matters specifically for a caller that pins most
            of the board via ``fixed_positions`` -- absent this filter, a
            pair where BOTH refs are frozen at their real, unchanged
            coordinates still gets unconditional courtyard AND netclass
            constraints, and if that pair already violates either on the
            real board (measured: 48 courtyard-violating pairs on
            ``pcb/temper.kicad_pcb`` as of 2026-08-13, none involving the
            component(s) being placed; netclass cross-class clearances are
            typically larger and were independently confirmed to trigger
            the same failure mode), the solve is spuriously infeasible for
            a reason unrelated to what is actually being placed. See
            ``_generate_courtyard_separated_constraints`` and
            ``generate_netclass_separated_constraints``'s docstrings for
            the full argument.
        lazy_creepage: Enable bounded cutting-plane enforcement of the full
            generated creepage matrix. Each feasible candidate is verified
            exhaustively in Rust; every violating pair is added as a HARD
            constraint before the next solve. A capped or unknown round is
            returned as ``unknown`` with no placement.
        lazy_creepage_max_rounds: Maximum number of cut rounds. The initial
            solve is always counted separately; reaching the cap with any
            remaining violation fails closed.
        lazy_creepage_iteration_timeout_ms: Optional per-round CP-SAT time
            cap. ``timeout_ms`` remains the overall wall-clock budget.
        decomposed_creepage: Enable the opt-in Rust partition plus bounded
            coarse-envelope phase before the ordinary CP-SAT solve. This
            mode requires ``lazy_creepage`` so the full Rust verifier remains
            the acceptance gate for the final placement.
        decomposed_creepage_eager_constraints: When true (the default), post
            the complete Rust-backed generated creepage constraint set before
            the first decomposed restricted solve. The lazy verifier still
            audits every candidate and can add discrepancy cuts. This flag
            has no effect on non-decomposed solves.
        decomposed_creepage_prior_cuts: Optional plain replay sequence of
            ``(ref_a, ref_b, required_mm)`` rows. Rows are canonicalized,
            max-reduced, and posted as hard ``SeparatedConstraint`` seeds
            before the first solve. Invalid, self, or unknown refs fail
            closed.
        lazy_creepage_post_cut_reserve_ms: Milliseconds reserved from the
            global timeout after the first lazy solve so a discovered cut can
            be posted and solved. The reserve applies only to lazy replay or
            decomposed runs; lazy-disabled and ordinary non-decomposed paths
            retain their existing budget.
        decomposed_creepage_envelope_timeout_ms: Maximum wall-clock time for
            the coarse envelope phase. This time is included in ``timeout_ms``
            and an incomplete coarse result fails closed as ``unknown``.
            Production-sized plans use the exact hierarchical warm-start
            solver; smaller plans use the direct hinted solver.
        decomposed_creepage_envelope_workers: Number of bounded CP-SAT search
            workers for the coarse envelope phase (1--64).
        decomposed_creepage_local_pack_timeout_ms: Maximum wall-clock time
            allocated to Rust partition preparation's local sub-envelope
            packing.  The default is 57 seconds, based on the measured
            production partition; the effective value is additionally capped
            to 80% of the coarse envelope budget so the outer envelope solve
            always receives a bounded remainder.  This time is included in
            both ``decomposed_creepage_envelope_timeout_ms`` and the overall
            ``timeout_ms`` deadline.
        decomposed_creepage_envelope_headroom_mm: Additional local-envelope
            headroom in millimetres.  The default is zero: local preparation
            reports the exact compact envelope, while integration slack is
            controlled separately by ``decomposed_creepage_restriction_slack_mm``.
        decomposed_creepage_restriction_slack_mm: Additional millimetres by
            which each component restriction window is expanded before it is
            clamped to the board interior.  The conservative 2.0 mm default
            prevents false infeasibility at this integration boundary; exact
            generated creepage gaps and component no-overlap remain hard
            constraints and the Rust verifier remains authoritative.
        decomposed_creepage_group_prior_cuts: Use the Rust neighborhood
            planner to share four relative-direction literals across dense
            replay-cut blocks. This is a decomposed-only search restriction;
            every component pair retains its exact distance inequality.

    """
    from ortools.sat.python import cp_model as cp

    if lazy_creepage and lazy_creepage_max_rounds < 0:
        raise ValueError("lazy_creepage_max_rounds must be non-negative")
    if lazy_creepage_iteration_timeout_ms is not None and lazy_creepage_iteration_timeout_ms <= 0:
        raise ValueError("lazy_creepage_iteration_timeout_ms must be positive")
    if decomposed_creepage and not lazy_creepage:
        raise ValueError("decomposed_creepage requires lazy_creepage")
    if decomposed_creepage_group_prior_cuts and not decomposed_creepage:
        raise ValueError("grouped prior cuts require decomposed_creepage")
    if not isinstance(decomposed_creepage_group_prior_cuts, bool):
        raise ValueError("decomposed_creepage_group_prior_cuts must be a boolean")
    if (
        isinstance(decomposed_creepage_group_max_size, bool)
        or not isinstance(decomposed_creepage_group_max_size, int)
        or decomposed_creepage_group_max_size <= 0
    ):
        raise ValueError("decomposed_creepage_group_max_size must be positive")
    if (
        isinstance(decomposed_creepage_group_min_cross_edges, bool)
        or not isinstance(decomposed_creepage_group_min_cross_edges, int)
        or decomposed_creepage_group_min_cross_edges < 2
    ):
        raise ValueError("decomposed_creepage_group_min_cross_edges must be at least 2")
    if not isinstance(decomposed_creepage_eager_constraints, bool):
        raise ValueError("decomposed_creepage_eager_constraints must be a boolean")
    if (
        isinstance(lazy_creepage_post_cut_reserve_ms, bool)
        or not isinstance(lazy_creepage_post_cut_reserve_ms, int)
        or lazy_creepage_post_cut_reserve_ms < 0
    ):
        raise ValueError("lazy_creepage_post_cut_reserve_ms must be non-negative")
    if (
        isinstance(decomposed_creepage_envelope_timeout_ms, bool)
        or not isinstance(decomposed_creepage_envelope_timeout_ms, int)
        or decomposed_creepage_envelope_timeout_ms <= 0
    ):
        raise ValueError("decomposed_creepage_envelope_timeout_ms must be positive")
    if (
        isinstance(decomposed_creepage_envelope_workers, bool)
        or not isinstance(decomposed_creepage_envelope_workers, int)
        or not 1 <= decomposed_creepage_envelope_workers <= 64
    ):
        raise ValueError("decomposed_creepage_envelope_workers must be between 1 and 64")
    if (
        isinstance(decomposed_creepage_local_pack_timeout_ms, bool)
        or not isinstance(decomposed_creepage_local_pack_timeout_ms, int)
        or decomposed_creepage_local_pack_timeout_ms <= 0
    ):
        raise ValueError("decomposed_creepage_local_pack_timeout_ms must be positive")
    if (
        isinstance(decomposed_creepage_envelope_headroom_mm, bool)
        or not isinstance(decomposed_creepage_envelope_headroom_mm, (int, float))
        or not math.isfinite(float(decomposed_creepage_envelope_headroom_mm))
        or decomposed_creepage_envelope_headroom_mm < 0.0
    ):
        raise ValueError(
            "decomposed_creepage_envelope_headroom_mm must be finite and non-negative"
        )
    if (
        isinstance(decomposed_creepage_restriction_slack_mm, bool)
        or not isinstance(decomposed_creepage_restriction_slack_mm, (int, float))
        or not math.isfinite(float(decomposed_creepage_restriction_slack_mm))
        or decomposed_creepage_restriction_slack_mm < 0.0
    ):
        raise ValueError(
            "decomposed_creepage_restriction_slack_mm must be finite and non-negative"
        )

    t_start = time.monotonic()

    # Determine board dimensions.
    board_w = float(getattr(board, "width", 100.0))
    board_h = float(getattr(board, "height", 100.0))

    model_wrapper = CpSatModel(units_per_mm=100)
    board_w_units = model_wrapper.mm_to_units(board_w)
    board_h_units = model_wrapper.mm_to_units(board_h)

    # Register every board component in the model.
    comp_refs: list[str] = []
    for comp in netlist.components:
        ref = comp.ref
        comp_refs.append(ref)
        bounds = getattr(comp, "bounds", (10.0, 10.0))
        model_wrapper.add_component(
            ref,
            x_start_val=0,
            y_start_val=0,
            width=model_wrapper.mm_to_units(float(bounds[0])),
            height=model_wrapper.mm_to_units(float(bounds[1])),
        )
        # Add rotation unless it's a known polarized part.
        polarized = ref in _POLARIZED_REFS
        model_wrapper.add_rotation(ref, is_polarized=polarized)

    accumulated_cut_map = {
        (ref_a, ref_b): required
        for ref_a, ref_b, required in _canonical_creepage_cuts(
            decomposed_creepage_prior_cuts,
            set(comp_refs),
        )
    }
    prior_cut_count = len(accumulated_cut_map)
    new_cut_count = 0
    remaining_violations: tuple[tuple[str, str, float, float], ...] = ()
    grouped_cut_stats = None

    # Routed-board repair: pin every requested component's rotation to its
    # current board value (hard constraint). A rotation would move every pad
    # and disconnect the routed copper attached to it, so repair callers
    # pin all refs; the min-displacement objective then only has translation
    # freedom to work with.
    if fixed_rotations:
        for ref, rot in fixed_rotations.items():
            model_wrapper.add_fixed_rotation(ref, rot)

    # Load netclass rules early — needed for auto-generated cross-class
    # separation AND for computing courtyard clearance τ (U1).
    loaded_netclass_rules = None
    default_clearance_mm = 0.2
    try:
        from pathlib import Path

        from temper_placer.io.netclass_loader import load_netclass_rules

        _config_yaml = (
            Path(__file__).parent.parent.parent.parent.parent / "configs" / "netclass_rules.yaml"
        )
        if _config_yaml.exists():
            loaded_netclass_rules = load_netclass_rules(_config_yaml)
            default_clearance_mm = loaded_netclass_rules.design_rules.default_clearance
    except Exception:
        logger.debug("Could not load netclass_rules.yaml", exc_info=True)

    # Compute courtyard clearance τ (C1) and board-edge margin m (C2).
    # τ = default_clearance_mm + 2 * mask_expansion_mm (strict >, not max).
    # mask_expansion_mm = 0.1 is the industry-standard solder mask expansion.
    # Using + instead of max() guarantees strict separation so mask apertures
    # never touch at 0, preventing solder mask bridging.
    # TODO: parse mask_expansion_mm from board (setup) via kiutils.
    tau_mm = courtyard_clearance_mm(default_clearance_mm)

    # m derives from copper_edge_clearance_mm.
    # copper_edge_clearance_mm = 0.5 is a conservative default.
    # TODO: parse copper_edge_clearance_mm from board (setup) via kiutils.
    COPPER_EDGE_CLEARANCE_MM = 0.5
    margin_units = model_wrapper.mm_to_units(COPPER_EDGE_CLEARANCE_MM)

    # Constrain all components to lie within board bounds with edge margin (C2).
    #
    # 2026-08-13 (PR #1144 follow-up): restricted to `auto_pairwise_touch_refs`
    # for the same reason as the courtyard/netclass/NoOverlap2D restrictions
    # above -- a frozen (fixed_positions) ref's real board position may
    # already violate this margin (measured: 22 of 168 components on
    # pcb/temper.kicad_pcb as of 2026-08-13), which is an immediate,
    # unconditional contradiction with that ref's own frozen-position
    # equality, independent of anything else in the model. This was the
    # dominant cause of a reported spurious-UNSAT control-test failure
    # (an uninvolved component's placement request returning INFEASIBLE
    # purely because SOME OTHER frozen, unrelated component's real position
    # sits within/past the edge margin) that survived the courtyard/
    # netclass/NoOverlap2D fixes alone -- see `CpSatModel.set_bounds`'s
    # docstring for the full argument.
    model_wrapper.set_bounds(
        margin_units,
        margin_units,
        board_w_units - margin_units,
        board_h_units - margin_units,
        touch_refs=auto_pairwise_touch_refs,
    )

    # Optional coarse decomposition. The Rust planner/sizer owns partition
    # ownership and shelf dimensions; Python only marshals its plain output
    # and applies the resulting hard envelope bounds to the normal model.
    # This phase is deliberately before any ordinary placement constraints:
    # every invalid, infeasible, or incomplete coarse result returns an
    # explicit unknown with no positions rather than silently widening the
    # search back to the unrestricted model.
    decomposed_partition_count = 0
    decomposed_envelope_solve_ms = 0.0
    decomposed_error: str | None = None

    def _decomposed_unknown(message: str) -> CpSatPlacementResult:
        nonlocal decomposed_error
        decomposed_error = message
        elapsed_ms = (time.monotonic() - t_start) * 1000.0
        logger.warning("decomposed creepage failed closed: %s", message)
        return CpSatPlacementResult(
            positions={},
            rotations={},
            placed_refs=[],
            unplaced_refs=list(comp_refs),
            status="unknown",
            solve_time_ms=elapsed_ms,
            decomposed_creepage_partition_count=decomposed_partition_count,
            decomposed_creepage_envelope_solve_time_ms=decomposed_envelope_solve_ms,
            decomposed_creepage_error=message,
            decomposed_creepage_cuts=[
                (ref_a, ref_b, accumulated_cut_map[(ref_a, ref_b)])
                for ref_a, ref_b in sorted(accumulated_cut_map)
            ],
            decomposed_creepage_prior_cut_count=prior_cut_count,
            decomposed_creepage_new_cut_count=new_cut_count,
            decomposed_creepage_remaining_violations=remaining_violations,
        )

    if decomposed_creepage and comp_refs:
        if loaded_netclass_rules is None:
            return _decomposed_unknown(
                "generated netclass rules are unavailable for partition planning"
            )
        coarse_budget_s = min(
            decomposed_creepage_envelope_timeout_ms / 1000.0,
            _lazy_solver_budget_seconds(timeout_ms, time.monotonic() - t_start, None),
        )
        if coarse_budget_s <= 0.0:
            return _decomposed_unknown("overall timeout exhausted before envelope planning")
        # Local preparation used to receive the entire coarse budget, leaving
        # no time for the outer envelope model after a hard local timeout.
        # Keep both phases inside the same deadline and reserve an explicit
        # outer share.  If preparation finishes early, the outer phase may use
        # the naturally remaining time, still bounded by the global deadline.
        local_pack_budget_s = min(
            decomposed_creepage_local_pack_timeout_ms / 1000.0,
            coarse_budget_s * (1.0 - _DECOMPOSED_OUTER_RESERVE_FRACTION),
        )
        if local_pack_budget_s <= 0.0:
            return _decomposed_unknown("no budget remains for local envelope preparation")
        coarse_started = time.monotonic()
        try:
            from temper_placer.placer.cp_sat.envelope_preparation import (
                prepare_envelope_inputs,
            )
            from temper_placer.placer.cp_sat.envelope_solver import solve_envelopes

            interior_width_mm = board_w - 2.0 * COPPER_EDGE_CLEARANCE_MM
            interior_height_mm = board_h - 2.0 * COPPER_EDGE_CLEARANCE_MM
            rotatable_component_refs = _authoritative_rotatable_component_refs(
                model_wrapper,
                comp_refs,
                fixed_rotations,
                fixed_positions,
            )
            prepared = prepare_envelope_inputs(
                netlist,
                loaded_netclass_rules.design_rules,
                interior_width_mm,
                interior_height_mm,
                tau_mm,
                local_pack_total_timeout_s=local_pack_budget_s,
                local_pack_workers=decomposed_creepage_envelope_workers,
                rotatable_component_refs=rotatable_component_refs,
                headroom_mm=decomposed_creepage_envelope_headroom_mm,
            )
            decomposed_partition_count = len(prepared.partitions)
            remaining_coarse_s = max(
                0.0, coarse_budget_s - (time.monotonic() - coarse_started)
            )
            remaining_overall_s = _lazy_solver_budget_seconds(
                timeout_ms, time.monotonic() - t_start, None
            )
            outer_budget_s = min(remaining_coarse_s, remaining_overall_s)
            if outer_budget_s <= 0.0:
                return _decomposed_unknown(
                    "overall timeout exhausted during local envelope preparation"
                )
            # Preparation records absent hints as ``None`` so callers can
            # distinguish missing data from a measured origin.  The solver's
            # partial mapping accepts only present origins; omitting ``None``
            # entries preserves that explicit absence without inventing one.
            initial_position_hints = {
                partition_id: hint
                for partition_id, hint in prepared.initial_position_hints.items()
                if hint is not None
            }
            expected_partition_ids = {partition_id for partition_id, *_rest in prepared.partitions}
            raw_rotatable_partition_ids: object = getattr(
                prepared, "rotatable_partition_ids", frozenset()
            )
            if not isinstance(raw_rotatable_partition_ids, (set, frozenset)):
                return _decomposed_unknown("coarse envelope rotation allowlist is malformed")
            rotatable_partition_ids = set(raw_rotatable_partition_ids)
            if any(
                not isinstance(partition_id, str) or not partition_id.strip()
                for partition_id in rotatable_partition_ids
            ) or not rotatable_partition_ids <= expected_partition_ids:
                return _decomposed_unknown(
                    "coarse envelope rotation allowlist does not match the prepared plan"
                )
            if len(prepared.partitions) >= _HIERARCHICAL_DECOMPOSED_PARTITION_THRESHOLD:
                # The hierarchical kernel uses batches only to create a warm
                # start; its final solve receives the original partitions and
                # exact pair requirements.  Keep the full call bounded by the
                # reserved outer share and fail closed on any incomplete
                # result.
                from temper_placer.placer.cp_sat.hierarchical_envelope_solver import (
                    solve_hierarchical_envelopes,
                )

                envelope_result = solve_hierarchical_envelopes(
                    prepared.partitions,
                    prepared.pair_requirements,
                    interior_width_mm,
                    interior_height_mm,
                    time_limit_s=outer_budget_s,
                    num_search_workers=decomposed_creepage_envelope_workers,
                    # Component rotatability is not represented in the
                    # partition plan.  Do not let the abstract envelope
                    # solver choose a 90-degree orientation that the
                    # restricted component model cannot realize.
                    rotatable_partition_ids=rotatable_partition_ids,
                )
            else:
                envelope_result = solve_envelopes(
                    prepared.partitions,
                    prepared.pair_requirements,
                    interior_width_mm,
                    interior_height_mm,
                    time_limit_s=outer_budget_s,
                    num_search_workers=decomposed_creepage_envelope_workers,
                    initial_position_hints=initial_position_hints,
                    # There is no rotatability proof in PreparedEnvelopeInputs;
                    # require the conservative, declared orientation.
                    rotatable_partition_ids=rotatable_partition_ids,
                )
            decomposed_envelope_solve_ms = float(
                getattr(envelope_result, "solve_time_s", 0.0)
            ) * 1000.0
            if not bool(getattr(envelope_result, "feasible", False)):
                return _decomposed_unknown(
                    "coarse envelope solve did not produce a complete feasible plan"
                )

            envelope_bounds = getattr(envelope_result, "envelopes", None)
            if not isinstance(envelope_bounds, dict):
                return _decomposed_unknown("coarse envelope result has no envelope mapping")
            if set(envelope_bounds) != expected_partition_ids:
                return _decomposed_unknown(
                    "coarse envelope result partition IDs do not match the prepared plan"
                )
            refs_by_partition = _refs_by_partition_in_input_order(prepared.partitions)
            restriction_slack_units = model_wrapper.mm_to_units(
                float(decomposed_creepage_restriction_slack_mm)
            )
            for ref, partition_id in prepared.ref_to_partition.items():
                envelope = envelope_bounds.get(partition_id)
                if envelope is None:
                    return _decomposed_unknown(
                        f"coarse envelope result omitted partition {partition_id!r}"
                    )
                cv = model_wrapper.get_component(ref)
                # Rust envelopes are expressed in the board interior origin;
                # translate each edge by the normal board copper margin.
                raw_bounds = (
                    envelope.x_min_mm,
                    envelope.y_min_mm,
                    envelope.x_max_mm,
                    envelope.y_max_mm,
                )
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    for value in raw_bounds
                ):
                    return _decomposed_unknown(
                        f"coarse envelope for {ref!r} has non-finite bounds"
                    )
                # The Rust compact sizer works in aggregate floating-point
                # millimetres, while component boxes are independently
                # nearest-even rounded into the CP-SAT grid.  A partition
                # containing several half-grid-sized components can otherwise
                # be reported feasible by the envelope model but become
                # falsely infeasible here.  Add bounded quantization and
                # explicitly configured restriction slack, clamped to the
                # same board interior; this does not relax any creepage
                # requirement, which remains encoded by the exact generated
                # pair constraints.
                padding_units = _decomposed_quantization_padding_units(
                    len(refs_by_partition[partition_id])
                )
                raw_bounds_units = (
                    model_wrapper.mm_to_units(float(raw_bounds[0])),
                    model_wrapper.mm_to_units(float(raw_bounds[1])),
                    model_wrapper.mm_to_units(float(raw_bounds[2])),
                    model_wrapper.mm_to_units(float(raw_bounds[3])),
                )
                x_min, y_min, x_max, y_max = _decomposed_restriction_window(
                    raw_bounds_units,
                    padding_units=padding_units,
                    restriction_slack_units=restriction_slack_units,
                    margin_units=margin_units,
                    board_width_units=board_w_units,
                    board_height_units=board_h_units,
                )
                if x_min > x_max or y_min > y_max:
                    return _decomposed_unknown(
                        f"coarse envelope for {ref!r} has inverted bounds"
                    )
                model_wrapper.add(cv.x_start >= x_min)
                model_wrapper.add(cv.x_end <= x_max)
                model_wrapper.add(cv.y_start >= y_min)
                model_wrapper.add(cv.y_end <= y_max)
        except Exception as exc:
            # Preparation and Rust output validation are intentionally
            # fail-closed. Do not let a malformed plan fall through to an
            # unrestricted placement solve.
            return _decomposed_unknown(f"invalid coarse envelope plan: {exc}")

    # Wire up NoOverlap2D (redundant global for propagation — per-pair
    # SEPARATED-τ is added during constraint encoding in U2).
    #
    # 2026-08-13 (PR #1144 follow-up): this global constraint is added
    # UNCONDITIONALLY over every ref in *no_overlap_2d_refs* -- unlike the
    # courtyard/netclass SeparatedConstraint generators (which honour
    # `auto_pairwise_touch_refs`), it is not even assumption-gated in a way
    # that actually enforces conditionally (`add_no_overlap_2d`'s returned
    # assumption literal is registered for labelling but never attached via
    # `OnlyEnforceIf` to the `AddNoOverlap2D` call itself). For a caller
    # that pins most of the board via `fixed_positions`, including every
    # frozen ref here means a pair of two frozen, unrelated components
    # whose courtyard boxes TRULY overlap at their real committed positions
    # (measured: 34 such pairs on pcb/temper.kicad_pcb as of 2026-08-13,
    # none involving the component(s) being placed) makes the model
    # infeasible for a reason that has nothing to do with what is actually
    # being solved for -- the same spurious-UNSAT mechanism the courtyard/
    # netclass filter closes, for the "redundant propagation" global
    # instead of the per-pair constraints. Restricting the ref list to
    # `auto_pairwise_touch_refs` when given drops only frozen-vs-frozen
    # pairs; touch-set-vs-frozen and touch-set-vs-touch-set overlap
    # avoidance is still fully covered by the (now also `touch_refs`-aware)
    # per-pair courtyard SeparatedConstraint, which this call was always
    # documented as merely a redundant propagation aid for.
    no_overlap_2d_refs = (
        [r for r in comp_refs if r in auto_pairwise_touch_refs]
        if auto_pairwise_touch_refs is not None
        else comp_refs
    )
    model_wrapper.add_no_overlap_2d(no_overlap_2d_refs)

    # Mains<->SELV physical isolation barrier (opt-in). Must run AFTER every
    # real component is registered (above) — add_isolation_barrier_to_model
    # calls model_wrapper.get_component(ref) for every HV/SELV/isolator ref
    # and adds its constraints directly to the model; nothing further needs
    # encoding for it.
    isolation_barrier_report = None
    if isolation_barrier is not None:
        from temper_placer.placer.cp_sat.isolation_barrier import add_isolation_barrier_to_model

        isolation_barrier_report = add_isolation_barrier_to_model(
            model_wrapper,
            netlist,
            board_w_mm=board_w,
            board_h_mm=board_h,
            **isolation_barrier,
        )

    # Tank-node functional creepage (opt-in). Same placement in the
    # sequence and same reason as the barrier above: it calls
    # model_wrapper.component_map, so every component must already be
    # registered, and it posts directly to the model via the existing
    # `separated` handler (no PCL round-trip needed).
    tank_creepage_report = None
    if tank_creepage is not None:
        from temper_placer.placer.cp_sat.tank_creepage import add_tank_creepage_to_model

        tank_creepage_report = add_tank_creepage_to_model(
            model_wrapper,
            netlist,
            **tank_creepage,
        )

    # Shared-heatsink co-location (opt-in). Same placement in the sequence
    # and same reason as the barrier above: it calls get_component() for
    # every ref in its groups, so every component must already be
    # registered, and it posts directly to the model.
    if heatsink_colocation is not None:
        from temper_placer.placer.cp_sat.heatsink_colocation import (
            HEATSINK_GROUPS,
            add_heatsink_colocation_to_model,
        )

        for group in HEATSINK_GROUPS:
            add_heatsink_colocation_to_model(model_wrapper, group, heatsink_colocation)

    # Protective-impedance chain co-location (opt-in). These are hard safety
    # constraints: each declared series-chain interior node must remain a
    # local stub. Resolve from the manifest and live netlist after all
    # components are registered, so refdes changes cannot silently retarget
    # the constraint. Strict resolution fails closed on stale declarations.
    if protective_impedance_colocation is not None:
        from temper_placer.placer.cp_sat.protective_impedance_colocation import (
            add_chain_colocation_to_model,
            load_protective_impedance_chains,
            resolve_chain_pairs,
        )

        chain_kwargs = dict(protective_impedance_colocation)
        chains = chain_kwargs.pop("chains", None)
        manifest_path = chain_kwargs.pop("manifest_path", None)
        if chains is None:
            if manifest_path is None:
                raise ValueError(
                    "protective_impedance_colocation requires manifest_path "
                    "or pre-loaded chains"
                )
            chains = load_protective_impedance_chains(manifest_path)
        pairs = resolve_chain_pairs(chains, netlist.components, strict=True)
        add_chain_colocation_to_model(model_wrapper, pairs, **chain_kwargs)

    # Warm-start: seed solver with hint positions so CP-SAT searches
    # locally from a known-feasible point rather than exploring the full
    # space.  Hints are validated against constraints by the solver;
    # AddHint is a soft suggestion, not a binding assignment.
    if hint_positions:
        for ref, (x_mm, y_mm, rot) in hint_positions.items():
            if ref in model_wrapper.component_map:
                cv = model_wrapper.get_component(ref)
                hint_x = model_wrapper.mm_to_units(x_mm)
                hint_y = model_wrapper.mm_to_units(y_mm)
                model_wrapper.model_ref.AddHint(cv.x_center, hint_x)
                model_wrapper.model_ref.AddHint(cv.y_center, hint_y)
                if cv.rot_ref is not None:
                    model_wrapper.model_ref.AddHint(cv.rot_ref, rot)

    # Minimum-displacement repair objective (issue #504): the solver returns
    # the feasible placement closest (Manhattan) to these reference
    # positions.  A preference, never a hard bound -- the objective is
    # applied below via model_wrapper.apply_objective() BEFORE solving; this
    # is what makes the parameter actually steer the solve (a previous,
    # never-landed attempt registered objective terms without ever calling
    # Minimize on this path, making the parameter a silent no-op).
    if max_displacement_mm is not None and not minimize_displacement_to:
        # Same no-op class as the #498 bug: a bound with no reference would
        # silently constrain nothing. Fail loudly instead.
        raise ValueError(
            "max_displacement_mm requires minimize_displacement_to (the bound "
            "applies to every ref in the reference dict)"
        )
    if minimize_displacement_to:
        bound_units = None
        if max_displacement_mm is not None:
            bound_units = model_wrapper.mm_to_units(max_displacement_mm)
        for ref, (x_mm, y_mm) in minimize_displacement_to.items():
            model_wrapper.add_displacement_objective(
                ref,
                model_wrapper.mm_to_units(x_mm),
                model_wrapper.mm_to_units(y_mm),
                max_units=bound_units,
            )

    # Hard position pins (minimal-disruption API): unlike AddHint above,
    # these are binding equality constraints -- the solver cannot move a
    # pinned ref.  This is the "freeze these refs, re-solve the rest"
    # primitive issue #504's minimum-displacement loop needs.  An
    # unresolved ref is a silent no-op if skipped here, so fail loudly
    # (same fail-closed discipline as validate_constraint_refs below).
    if fixed_positions:
        for ref, (x_mm, y_mm, rot) in fixed_positions.items():
            if ref not in model_wrapper.component_map:
                raise ValueError(
                    f"fixed_positions references unknown component {ref!r}; "
                    "a silent skip would freeze nothing and produce a "
                    "misleadingly 'minimal' displacement"
                )
            cv = model_wrapper.get_component(ref)
            pin_x = model_wrapper.mm_to_units(x_mm)
            pin_y = model_wrapper.mm_to_units(y_mm)
            model_wrapper.model_ref.Add(cv.x_center == pin_x)  # type: ignore[operator]
            model_wrapper.model_ref.Add(cv.y_center == pin_y)  # type: ignore[operator]
            if cv.rot_ref is not None:
                model_wrapper.model_ref.Add(cv.rot_ref == rot)  # type: ignore[operator]

    # Build EncoderContext from board and netlist data.
    # Coerce every zone rectangle to a validated Rect (x_min,y_min,x_max,y_max)
    # so an inverted/degenerate zone — the (x,y,w,h) convention mismatch —
    # fails loudly here instead of silently encoding an empty, infeasible
    # enclosing region.
    from temper_placer.core.board import Rect

    resolved_zones: dict[str, Rect] = {
        name: Rect.coerce(bounds) for name, bounds in (zones or {}).items()
    }
    resolved_zone_components: dict[str, list[str]] = dict(zone_components or {})
    for z in board.zones:
        if z.name not in resolved_zones:
            resolved_zones[z.name] = Rect.coerce(z.bounds)
        zone_refs = list(z.components)
        for comp in netlist.components:
            if getattr(comp, "zone", None) == z.name and comp.ref not in zone_refs:
                zone_refs.append(comp.ref)
        if zone_refs:
            resolved_zone_components[z.name] = zone_refs

    resolved_loop_components = loop_components or _resolve_loop_components(netlist)
    loop_reconciliation = _encoder_core.reconcile_loop_components(
        resolved_loop_components,
        reference_aliases,
        loop_aliases,
    )
    if loop_reconciliation.aliases_applied:
        logger.info("Applied loop aliases: %s", loop_reconciliation.aliases_applied)

    ctx = EncoderContext(
        board_w,
        board_h,
        zones={k: (v.x_min, v.y_min, v.x_max, v.y_max) for k, v in resolved_zones.items()},
        loop_components=loop_reconciliation.loop_components,
        zone_components=resolved_zone_components,
        board_x_min_units=0,
        board_y_min_units=0,
        board_x_max_units=board_w_units,
        board_y_max_units=board_h_units,
        courtyard_clearance_mm=tau_mm,
        board_edge_margin_units=margin_units,
    )

    constraint_objects: list[BaseConstraint] = list(extra_constraints or [])
    pcl_coll = getattr(board, "constraints", None)
    if pcl_coll is not None:
        constraint_objects.extend(pcl_coll)
    for index, ((ref_a, ref_b), required) in enumerate(sorted(accumulated_cut_map.items())):
        if decomposed_creepage_group_prior_cuts:
            continue
        constraint_objects.append(
            SeparatedConstraint(
                a=ref_a,
                b=ref_b,
                min_distance_mm=required,
                tier=ConstraintTier.HARD,
                because="Replayed generated KiCad creepage cutting-plane requirement",
                id=f"replayed_creepage_{index}_{ref_a}_{ref_b}",
            )
        )

    reconciliation = _encoder_core.reconcile_constraint_refs(
        constraint_objects,
        reference_aliases,
        loop_aliases=loop_aliases,
    )
    constraint_objects = list(reconciliation.constraints)
    if reconciliation.aliases_applied:
        logger.info("Applied constraint aliases: %s", reconciliation.aliases_applied)

    # Fail loud on config↔netlist drift: a constraint operand that resolves
    # to nothing is a silent no-op, so validate before encoding. This is the
    # fail-closed guard for the "looks applied but isn't" failure mode.
    unresolved_refs = validate_constraint_refs(
        constraint_objects,
        component_refs=set(model_wrapper.component_map.keys()),
        zone_names=set(resolved_zones.keys()),
        loop_names=set(ctx.loop_components.keys()),
        # Read through the module rather than a `from ... import` binding.
        # A module-level `from _encoder_core import _UNRESOLVED_REF_POLICY`
        # snapshots the value at import time, so tests that downgrade the
        # policy would set an attribute nothing ever reads -- green, and
        # vacuous. One canonical location, read at call time.
        on_unresolved=_encoder_core._UNRESOLVED_REF_POLICY,
    )
    # The validator is the single source of truth for the explicit ``warn``
    # downgrade.  Handlers remain fail-closed when called directly, but the
    # dispatcher must not re-raise for a constraint it was just instructed to
    # downgrade after reconciliation.
    ctx.unresolved_constraint_ids = set(unresolved_refs)

    encode_constraints(
        constraint_objects,
        model_wrapper,
        ctx,
        netlist=netlist,
        netclass_rules_data=loaded_netclass_rules,
        auto_pairwise_touch_refs=auto_pairwise_touch_refs,
        # The Rust-backed generator emits the complete reduced component-pair
        # matrix. Decomposed mode opts into posting it eagerly, while the
        # existing non-decomposed lazy behavior remains unchanged.
        enforce_creepage=(
            not lazy_creepage
            or (decomposed_creepage and decomposed_creepage_eager_constraints)
        ),
    )
    if decomposed_creepage_group_prior_cuts and accumulated_cut_map:
        from temper_placer.placer.cp_sat.grouped_creepage_cuts import encode_grouped_creepage_cuts

        grouped_cut_stats = encode_grouped_creepage_cuts(
            model_wrapper,
            [(a, b, distance) for (a, b), distance in sorted(accumulated_cut_map.items())],
            max_group_size=decomposed_creepage_group_max_size,
            min_cross_edges=decomposed_creepage_group_min_cross_edges,
        )

    # Pad-vs-fixed-copper NoOverlap (issue #523): encode one BoolOr per
    # (free pad, fixed item) pair after every other constraint so the
    # rotation variables and sizes are fully wired. See fixed_copper.py.
    _fixed_copper_pads: dict[str, list[PadRectLocal]] | None = None
    _fixed_copper_items: list | None = None
    if fixed_copper is not None:
        from temper_placer.placer.cp_sat.fixed_copper import (
            build_fixed_copper_items,
            build_free_component_pads,
            encode_fixed_copper_constraints,
        )

        free_refs = set(fixed_copper.get("free_refs", ()))
        margin_mm = float(fixed_copper.get("margin_mm", 0.05))
        include_other_pads = bool(fixed_copper.get("include_other_pads", True))
        parse_result = fixed_copper["parse_result"]
        _fixed_copper_pads = build_free_component_pads(netlist, free_refs)
        _fixed_copper_items = build_fixed_copper_items(
            parse_result,
            netlist,
            free_refs,
            margin_mm=margin_mm,
            include_other_pads=include_other_pads,
        )
        encode_fixed_copper_constraints(
            model_wrapper,
            _fixed_copper_pads,
            _fixed_copper_items,
            free_refs=free_refs,
        )
        logger.info(
            "fixed-copper constraints encoded for %d free ref(s) (%d pads, %d items)",
            len(free_refs),
            sum(len(p) for p in _fixed_copper_pads.values()),
            len(_fixed_copper_items),
        )

    # Phase 1 (feasibility): no objective — find any valid placement.
    # Phase 2 (wirelength polish) runs separately with a longer timeout
    # and bounded pair count.  The full O(n²) objective with 33 components
    # creates ~2100 extra variables and makes the solver hit the timeout.
    # See loop.py:_solve_phase2 for the polish path.

    # Apply the accumulated objective (if any) BEFORE solving.  This is the
    # single point where the minimum-displacement objective becomes real:
    # without it the terms registered by add_displacement_objective() would
    # be collected and never used.
    model_wrapper.apply_objective()

    status_map = {
        cp.OPTIMAL: "optimal",
        cp.FEASIBLE: "feasible",
        cp.INFEASIBLE: "infeasible",
        cp.MODEL_INVALID: "model_invalid",
        cp.UNKNOWN: "unknown",
    }
    status_code = cp.UNKNOWN
    status_str = "unknown"
    solver = cp.CpSolver()
    lazy_round = 0
    lazy_cut_count = 0
    post_cut_reserve_s = (
        lazy_creepage_post_cut_reserve_ms / 1000.0
        if lazy_creepage
        and (decomposed_creepage or decomposed_creepage_prior_cuts is not None)
        else 0.0
    )
    while True:
        reserve_s = post_cut_reserve_s if lazy_round == 0 else 0.0
        remaining_s = _lazy_solver_budget_seconds(
            timeout_ms,
            time.monotonic() - t_start,
            lazy_creepage_iteration_timeout_ms if lazy_creepage else None,
            reserve_s=reserve_s,
        )
        if remaining_s <= 0:
            status_code = cp.UNKNOWN
            status_str = "unknown"
            break
        solver = cp.CpSolver()
        solver.parameters.max_time_in_seconds = remaining_s
        solver.parameters.random_seed = seed
        solver.parameters.num_search_workers = 4
        solver.parameters.log_search_progress = False
        status_code = solver.Solve(model_wrapper.model_ref)
        status_str = status_map.get(status_code, "unknown")
        if not lazy_creepage or status_str not in ("optimal", "feasible"):
            break

        from temper_placer.placer.cp_sat.netclass_constraints import (
            verify_generated_creepage,
        )

        if loaded_netclass_rules is None:
            raise RuntimeError("lazy creepage requires the generated netclass rules")
        boxes = []
        for ref in comp_refs:
            cv = model_wrapper.get_component(ref)
            boxes.append(
                (
                    ref,
                    solver.Value(cv.x_start) / model_wrapper.units_per_mm,
                    solver.Value(cv.x_end) / model_wrapper.units_per_mm,
                    solver.Value(cv.y_start) / model_wrapper.units_per_mm,
                    solver.Value(cv.y_end) / model_wrapper.units_per_mm,
                )
            )
        violations = verify_generated_creepage(
            netlist, loaded_netclass_rules.design_rules, boxes
        )
        remaining_violations = _canonical_creepage_violations(
            violations,
            set(comp_refs),
        )
        if not remaining_violations:
            logger.info("lazy creepage converged after %d cut round(s)", lazy_round)
            break
        discovered = _canonical_creepage_cuts(
            [
                (ref_a, ref_b, required_mm)
                for ref_a, ref_b, required_mm, _gap_mm in remaining_violations
            ],
            set(comp_refs),
        )
        new_cuts: list[tuple[str, str, float]] = []
        for ref_a, ref_b, required in discovered:
            prior = accumulated_cut_map.get((ref_a, ref_b))
            if prior is None or required > prior:
                accumulated_cut_map[(ref_a, ref_b)] = required
                new_cuts.append((ref_a, ref_b, required))
        new_cut_count += len(new_cuts)
        if not new_cuts:
            logger.warning(
                "lazy creepage verifier found only already-posted cuts; failing closed"
            )
            status_code = cp.UNKNOWN
            status_str = "unknown"
            break
        if lazy_round >= lazy_creepage_max_rounds:
            logger.warning(
                "lazy creepage reached cap (%d round(s)) with %d violation(s)",
                lazy_creepage_max_rounds,
                len(violations),
            )
            status_code = cp.UNKNOWN
            status_str = "unknown"
            break

        from temper_placer.placer.cp_sat.handlers.separated import encode_separated

        for index, (ref_a, ref_b, required_mm) in enumerate(new_cuts):
            cut = SeparatedConstraint(
                a=ref_a,
                b=ref_b,
                min_distance_mm=required_mm,
                tier=ConstraintTier.HARD,
                because="Generated KiCad creepage cutting-plane requirement",
                id=f"lazy_creepage_{lazy_round}_{index}_{ref_a}_{ref_b}",
            )
            encode_separated(cut, model_wrapper.component_map, model_wrapper, ctx)
            constraint_objects.append(cut)
            lazy_cut_count += 1
        logger.info(
            "lazy creepage round %d added %d hard cut(s)",
            lazy_round,
            len(new_cuts),
        )
        lazy_round += 1

    # An infeasible solve after coarse envelopes only proves that restricted
    # submodel is unsatisfiable.  It is not a proof that the unrestricted
    # placement problem is infeasible, so decomposition must fail closed as
    # unknown and must not expose a misleading UNSAT core.
    if decomposed_creepage and status_str == "infeasible":
        status_code = cp.UNKNOWN
        status_str = "unknown"
        decomposed_error = "restricted coarse-envelope model is infeasible"
        logger.warning("decomposed creepage restricted model is infeasible; returning unknown")

    elapsed_ms = (time.monotonic() - t_start) * 1000.0

    positions: dict[str, tuple[float, float]] = {}
    rotations: dict[str, int] = {}
    objective = 0.0

    if status_str in ("optimal", "feasible"):
        objective = solver.ObjectiveValue()
        for ref in comp_refs:
            cv = model_wrapper.get_component(ref)
            x_mm = solver.Value(cv.x_center) / model_wrapper.units_per_mm
            y_mm = solver.Value(cv.y_center) / model_wrapper.units_per_mm
            positions[ref] = (round(x_mm, 3), round(y_mm, 3))
            if cv.rot_ref is not None:
                rotations[ref] = solver.Value(cv.rot_ref)

    unsat_core: list[dict] = []
    if status_str in ("infeasible", "model_invalid"):
        try:
            proto_indices = solver.SufficientAssumptionsForInfeasibility()
            for idx in proto_indices:
                label = model_wrapper._assumption_labels.get(idx, f"constraint_{idx}")
                unsat_core.append({"name": label, "because": "", "literal_index": idx})
        except Exception:
            pass

    # R24 item-3 post-solve audit (issue #523): recompute the EXACT
    # pad-to-copper clearance from the resolved coordinates, independent of
    # the solver's feasibility claim. By fixed_copper.py's soundness proof a
    # feasible solve must clear every applicable item by at least the margin;
    # any violation means the encoding is unsound for this solve and is a
    # hard failure, not a reportable "warning".
    if (
        status_str in ("optimal", "feasible")
        and _fixed_copper_items is not None
        and _fixed_copper_pads is not None
    ):
        from temper_placer.placer.cp_sat.fixed_copper import audit_fixed_copper

        audit_violations = audit_fixed_copper(
            _fixed_copper_pads,
            _fixed_copper_items,
            positions,
            rotations,
        )
        if audit_violations:
            first = audit_violations[0]
            raise RuntimeError(
                f"fixed-copper post-solve audit FAILED for a {status_str} solve: "
                f"{len(audit_violations)} violation(s); first: "
                f"{getattr(first, 'ref', '<unknown>')} pad "
                f"{getattr(first, 'pad_number', '<unknown>')} vs "
                f"{getattr(first, 'item_kind', '<unknown>')} "
                f"({getattr(first, 'item_net', '<unknown>')}): actual clearance "
                f"{getattr(first, 'actual_mm', float('nan')):.4f}mm < required "
                f"{getattr(first, 'required_mm', float('nan'))}mm. The fixed-copper encoding "
                "is unsound for this solve (see fixed_copper.py soundness proof)."
            )
        logger.info("fixed-copper post-solve audit: %d violation(s)", len(audit_violations))

    # R24 item-3 validator-aligned post-solve audit (issue #523 gap 2): when
    # validator_input is provided, re-run the REQ-SAFE-01 validator itself
    # (exact copper-to-copper on pad geometry -- the same function the CI
    # gate runs, and the one that caught run-B being "audit-clean but not
    # validator-clean") against the solved placement. The center-distance
    # audit above stays; this is additive. By domain_clearance.py's soundness
    # proof, a constraint-covered inter-component violation in a
    # feasible/optimal solve means the encoding is unsound -- a hard error,
    # same contract as audit_fixed_copper. Intra-footprint straddlers and
    # coverage gaps are placement-independent / alignment findings: reported
    # on the result, never raised.
    validator_audit = None
    if status_str in ("optimal", "feasible") and validator_input is not None:
        from temper_placer.placer.cp_sat.validator_audit import (
            audit_domain_clearance_validator,
        )

        v_placement = validator_input.get("placement")
        v_domains = validator_input.get("voltage_domains")
        if v_placement is None or v_domains is None:
            raise ValueError(
                "validator_input must carry both 'placement' and "
                "'voltage_domains' -- a silent skip would leave the solve "
                "unaudited against the REQ-SAFE-01 gate"
            )
        # The solve's domain-clearance constraint set is the pair coverage
        # the classification needs. Other SeparatedConstraints (courtyard,
        # netclass, keepaway) are not the validator-audit's concern -- the
        # REQ-SAFE-01 validator only pairs domain-classified components.
        domain_constraints = [
            c
            for c in constraint_objects
            if isinstance(c, SeparatedConstraint) and c.id.startswith("domain_clearance_")
        ]
        validator_audit = audit_domain_clearance_validator(
            domain_constraints,
            positions,
            rotations,
            v_placement,
            v_domains,
            netlist,
        )
        if validator_audit.hard_failures:
            first_hard = validator_audit.hard_failures[0]
            # One physical pair emits 4-8 violation records (clearance/
            # creepage x basic/reinforced), so report DISTINCT pairs as the
            # headline count -- "N hard violation(s)" with N=records would
            # inflate a 1-pair failure into a 4-8-pair failure. The
            # ``hard_failures`` list itself keeps the records.
            distinct_pairs = {
                frozenset((v.ref_a, v.ref_b)) for v in validator_audit.hard_failures
            }
            raise RuntimeError(
                f"REQ-SAFE-01 validator post-solve audit FAILED for a "
                f"{status_str} solve: {len(distinct_pairs)} distinct violating "
                f"pair(s) ({len(validator_audit.hard_failures)} violation "
                f"record(s) -- clearance/creepage x basic/reinforced rows); "
                f"first: {first_hard.ref_a}<->{first_hard.ref_b} {first_hard.metric} "
                f"{first_hard.measured_mm:.4f}mm < required {first_hard.required_mm}mm. "
                "The domain-clearance encoding is unsound for this solve (see "
                "domain_clearance.py soundness proof): the solver's box "
                "separation did NOT imply the validator's exact copper-to-"
                "copper separation. Run audit_domain_clearance_validator "
                "directly to inspect the full classified result."
            )
        logger.info(
            "REQ-SAFE-01 validator post-solve audit: %d hard failure(s), "
            "%d intra-footprint (placement-independent), %d coverage gap(s)",
            len(validator_audit.hard_failures),
            len(validator_audit.intra_footprint),
            len(validator_audit.coverage_gaps),
        )
    elif validator_input is not None:
        logger.warning(
            "REQ-SAFE-01 validator post-solve audit did NOT run: the solve "
            "terminated with status %r (only an optimal/feasible solve has a "
            "placement to audit) -- this solve was NOT verified against the "
            "REQ-SAFE-01 gate.",
            status_str,
        )
    elif status_str in ("optimal", "feasible"):
        logger.debug("validator post-solve audit skipped (validator_input not provided)")

    # R24 fail-closed F.Fab body-collision post-solve audit: this is the
    # chokepoint every produced placement passes through (both `temper
    # optimize --no-loop` and PlaceRouteLoop route their CP-SAT calls here),
    # so this is where a placement with a real physical body collision must
    # fail -- not three steps downstream as an opaque courtyards_overlap
    # ratchet number (see body_collision.py's module docstring for the
    # de59c0458/#602 and PR #1168 incidents this closes). A NEW or WORSENED
    # collision is a hard failure, same posture as fixed-copper/validator
    # audits above; a pre-existing allowlisted collision at or below its
    # recorded baseline is reported, never raised.
    body_collision_audit = None
    if status_str in ("optimal", "feasible") and body_collision_input is not None:
        from temper_placer.placer.cp_sat.body_collision import audit_body_collisions

        fab_bodies = body_collision_input.get("fab_bodies")
        allowlist = body_collision_input.get("allowlist")
        if fab_bodies is None or allowlist is None:
            raise ValueError(
                "body_collision_input must carry both 'fab_bodies' and "
                "'allowlist' -- a silent skip would leave the solve "
                "unaudited for physically-unassemblable body collisions"
            )
        body_collision_audit = audit_body_collisions(
            fab_bodies, positions, rotations, allowlist
        )
        if body_collision_audit.violations:
            worst = max(body_collision_audit.violations, key=lambda v: v.overlap_mm2)
            raise RuntimeError(
                f"F.Fab body-collision post-solve audit FAILED for a "
                f"{status_str} solve: {len(body_collision_audit.violations)} "
                f"violating pair(s); worst: {worst.describe()}. This placement "
                "is physically unassemblable (two component bodies occupy the "
                "same space) and is rejected before it can be written to a "
                "board. Run audit_body_collisions directly to inspect the "
                "full result, or see body_collision.py's module docstring."
            )
        logger.info(
            "F.Fab body-collision post-solve audit: 0 violations, %d "
            "allowlisted (unchanged-or-better) pre-existing collision(s) over "
            "%d checked pair(s)",
            len(body_collision_audit.allowlisted),
            body_collision_audit.checked_pairs,
        )
    elif body_collision_input is not None:
        logger.warning(
            "F.Fab body-collision post-solve audit did NOT run: the solve "
            "terminated with status %r (only an optimal/feasible solve has a "
            "placement to audit) -- this solve was NOT verified against "
            "physical body collisions.",
            status_str,
        )
    elif status_str in ("optimal", "feasible"):
        logger.debug("body-collision post-solve audit skipped (body_collision_input not provided)")

    return CpSatPlacementResult(
        positions=positions,
        rotations=rotations,
        placed_refs=list(positions),
        unplaced_refs=[ref for ref in comp_refs if ref not in positions],
        status=status_str,
        solve_time_ms=elapsed_ms,
        objective_value=objective,
        unsat_core=unsat_core,
        isolation_barrier_report=isolation_barrier_report,
        validator_audit=validator_audit,
        tank_creepage_report=tank_creepage_report,
        body_collision_audit=body_collision_audit,
        lazy_creepage_rounds=lazy_round,
        lazy_creepage_constraints_added=lazy_cut_count,
        decomposed_creepage_partition_count=decomposed_partition_count,
        decomposed_creepage_envelope_solve_time_ms=decomposed_envelope_solve_ms,
        decomposed_creepage_error=decomposed_error,
        decomposed_creepage_cuts=[
            (ref_a, ref_b, accumulated_cut_map[(ref_a, ref_b)])
            for ref_a, ref_b in sorted(accumulated_cut_map)
        ],
        decomposed_creepage_prior_cut_count=prior_cut_count,
        decomposed_creepage_group_count=grouped_cut_stats.group_count if grouped_cut_stats else 0,
        decomposed_creepage_shared_group_pair_count=grouped_cut_stats.shared_group_pair_count if grouped_cut_stats else 0,
        decomposed_creepage_grouped_cut_count=grouped_cut_stats.grouped_cut_count if grouped_cut_stats else 0,
        decomposed_creepage_independent_cut_count=grouped_cut_stats.independent_cut_count if grouped_cut_stats else 0,
        decomposed_creepage_direction_bool_count=grouped_cut_stats.direction_bool_count if grouped_cut_stats else 0,
        decomposed_creepage_new_cut_count=new_cut_count,
        decomposed_creepage_remaining_violations=remaining_violations,
    )


def _resolve_loop_components(netlist) -> dict[str, list[str]]:
    """Return {loop_name: [comp_ref, ...]} for all detectable commutation loops."""
    from temper_placer.core.loop_extractor import auto_extract_loops

    try:
        loops = auto_extract_loops(netlist)
        return {loop.name: loop.components for loop in loops}
    except Exception:
        return {}


def courtyard_clearance_mm(default_clearance_mm: float) -> float:
    """Courtyard clearance τ (C1): the separated-constraint margin the
    encoder applies to every component pair.

    ``default_clearance_mm + 2 * mask_expansion_mm`` — a strict ``+``,
    not ``max()``, so solder-mask apertures never touch at 0 (the
    ``+`` vs ``max`` distinction is the point; see the C1 comment in
    :func:`solve_placement`).

    Computed in the ``temper-constraints`` Rust crate
    (``encoder.rs::courtyard_clearance_mm``) with the exact f64
    operation order (``2 * expansion`` first, then the addition);
    pinned bit-exactly by
    ``tests/placer/cp_sat/test_encoder_rust_differential.py``.
    """
    import temper_constraints as _tc

    return _tc.courtyard_clearance_mm_py(default_clearance_mm, MASK_EXPANSION_MM)


# List of component refs known to be polarized on the temper board.
# This is the v1 fallback; automatic footprint detection is a follow-up.
_POLARIZED_REFS: set[str] = {
    "D_1",
    "D_2",
    "D_3",
    "D_4",
    "D_5",
    "D_6",  # diodes
    "K_1",
    "K_2",
    "K_5",
    "K_6",  # electrolytic capacitors
}
