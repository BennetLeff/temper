"""Minimum-displacement REQ-SAFE-01 clearance repair loop (issue #504).

**Problem.** The routed board carries 123 REQ-SAFE-01 clearance/creepage
violations across 86 pairs at the enforced 12.6mm reinforced margin (PD3).
A free CP-SAT reshuffle (full-domain constraint set, no objective) clears
the movable pairs but reproducibly regresses the routed board's DRC:
`shorting_items` and `unconnected_items` rise because the solve moves nearly
every component, and the board's existing routed copper connects pads at
their *current* positions (docs/evidence/2026-07-30-copper-aware-domain-
resolve.md, 2026-07-30-current-board-clearance-debt.md).

**What this module adds.** A repair mode for the solve pipeline:

1. ``solve_placement(minimize_displacement_to=...)`` -- an opt-in
   Manhattan-distance objective toward the current board positions. Hard
   constraints stay authoritative; the solver returns the feasible
   placement *closest* (in Manhattan distance) to today's board, so
   components only move as far as the clearance constraints force them.
2. ``solve_placement(fixed_rotations=...)`` -- every ref pinned to its
   current 0-3 rotation index: a rotation would move every pad and
   disconnect the routed copper attached to it.
3. ``run_clearance_repair_solve`` -- the loop: full domain-clearance
   constraint set + unclassified-near-HV keep-away constraints +
   min-displacement objective + fixed rotations + warm-start hints,
   followed by the R24 post-solve audit, an *independent* re-check with
   ``verify_iec60335_compliance`` (copper-to-copper on exact pad geometry),
   and a bounded constraint-reinforcement step for any inter-component pair
   the checker still flags.

**Loop invariant and termination (the induction that makes this a loop,
not a script).**

- *Invariant*: at the start of every round, the constraint set contains a
  hard ``SeparatedConstraint`` for every domain-crossing component pair
  (full set) AND for every inter-component pair the previous round's
  independent check flagged (reinforcement).
- *Base case*: round 0 starts with the full domain-clearance set generated
  from the same classifier the checker uses (imported, not reimplemented).
- *Induction step*: if round k's checker flags inter pairs not already
  constrained, round k+1 adds one hard constraint per pair (at the
  checker's own required margin) and re-solves. Each such round either
  reaches 0 inter violations or adds >= 1 new constraint; the number of
  distinct inter pairs is finite (<= N^2), so the loop terminates in at
  most (number of distinct inter pairs) + 1 rounds.
- *No-progress termination*: if a round's checker flags a pair whose hard
  constraint was SAT in the same round's solve, that contradicts the
  constraint's soundness proof (box separation implies pad-copper
  separation -- see ``domain_clearance.py``'s module docstring) and means
  the box model does not contain the real pad copper (a genuine
  constraint-model gap). The loop terminates immediately with status
  ``"gap"`` and the pair reported -- it never silently claims success, and
  it never spins.

**Intra-footprint pairs are reported, never claimed fixed.** A component
whose own pads straddle a domain boundary (C6/K1/K2/K3/T1/U6-family) cannot
be fixed by any placement; the loop separates them out of the checker
result and reports them as blockers.

**Success criterion.** A run whose final solve is feasible (status
``"clean"``/``"intra_only"``) has *every* inter-component REQ-SAFE-01
violation at 0, verified by the independent copper-to-copper checker, not
by the solver's own feasibility claim. The caller (board-output workstream,
issue #517) may then write the returned positions and evaluate the DRC /
routing delta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat._encoder_solve import solve_placement
from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance,
    generate_domain_clearance_constraints,
    generate_unclassified_hv_keepaway_constraints,
)
from temper_placer.requirements.validators.clearance import (
    ClearanceResult,
    verify_iec60335_compliance,
)

logger = logging.getLogger(__name__)


@dataclass
class ClearanceRepairRound:
    """One solve round of the repair loop."""

    index: int
    solve_status: str
    solve_time_ms: float
    total_constraints: int
    audit_violations: int
    checker_after_inter: int
    checker_after_intra: int
    displacement_mm: float
    moved_refs: tuple[str, ...] = ()
    #: CP-SAT objective value in model grid units (units_per_mm=100, so
    #: divide by 100 for mm) -- the minimized total Manhattan displacement.
    objective_value: float = 0.0


@dataclass
class ClearanceRepairReport:
    """Outcome of ``run_clearance_repair_solve``.

    ``status`` values:
    - ``"clean"``: feasible solve, 0 inter-component violations, 0 intra.
    - ``"intra_only"``: feasible solve, 0 inter-component violations; the
      remaining checker records are intra-footprint (unfixable by
      placement, listed in ``intra_blocker_refs``).
    - ``"infeasible"``: the solver PROVED the full constraint set has no
      feasible placement (UNSAT core in ``reason``) -- a board-layout/
      footprint problem, not a machinery failure.
    - ``"unknown"``: the solver returned without finding a solution within
      the time budget (or the model was invalid) -- NOT a proof of
      infeasibility, reported as distinct from ``"infeasible"`` so a caller
      never mistakes a timeout for a proven UNSAT.
    - ``"gap"``: a checker-flagged inter pair survived a SAT solve -- the
      solver's box model does not contain the component's real pad copper.
      Reported loudly; never treated as success.
    - ``"max_rounds"``: reinforcement did not converge within the bound
      (should not happen given the termination argument above; reported).
    """

    pcb_path: str
    status: str
    reason: str
    rounds: list[ClearanceRepairRound] = field(default_factory=list)
    baseline_violations: int = 0
    baseline_pairs: int = 0
    final_inter_violations: int = 0
    final_intra_violations: int = 0
    intra_blocker_refs: tuple[str, ...] = ()
    unreinforced_pairs: tuple[tuple[str, str], ...] = ()
    final_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    final_rotations: dict[str, int] = field(default_factory=dict)
    total_displacement_mm: float = 0.0
    audit_violations: int = 0
    keepaway_constraints: int = 0
    domain_constraints: int = 0

    @property
    def moved_refs(self) -> tuple[str, ...]:
        """Refs whose solved position differs from the current board by
        more than 0.001mm -- the routing-disruption surface."""
        if not self.rounds:
            return ()
        return self.rounds[-1].moved_refs


def _inter_intra_split(result: ClearanceResult) -> tuple[list[Any], list[Any]]:
    """Split checker violations into (inter-component, intra-footprint)."""
    inter: list[Any] = []
    intra: list[Any] = []
    for v in result.violations:
        if v.pair_kind == "intra":
            intra.append(v)
        else:
            inter.append(v)
    return inter, intra


def _override_positions(
    placement: dict[str, Any], positions: dict[str, tuple[float, float]]
) -> dict[str, Any]:
    """Copy *placement* with component positions replaced by *positions*
    (both in the local, origin-subtracted frame)."""
    import copy

    out = copy.deepcopy(placement)
    for comp in out.get("components", []):
        pos = positions.get(comp.get("ref"))
        if pos is not None:
            comp["position"] = pos
    return out


def run_clearance_repair_solve(
    *,
    pcb_path: Path,
    placement: dict[str, Any],
    voltage_domains: dict[str, Any],
    timeout_ms: int = 180_000,
    seed: int = 0,
    max_rounds: int = 4,
    max_displacement_mm: float | None = None,
    chain_exempt_pairs: set[frozenset[str]] | None = None,
    netlist: Any = None,
    board: Any = None,
) -> ClearanceRepairReport:
    """Run the minimum-displacement clearance repair loop.

    Args:
        pcb_path: Path to the routed board (used to parse the netlist/board
            when ``netlist``/``board`` are not supplied, and recorded in the
            report for provenance).
        placement: Validator-shape placement (see
            ``tests/requirements/safety/_real_board_fixture.py::load_real_board_placement``
            -- pass the FULL-classification placement for the whole-board
            picture). Positions must be in the local (origin-subtracted)
            frame, matching ``parse_kicad_pcb``'s default output.
        voltage_domains: net -> domain map for the checker.
        timeout_ms: per-solve time budget.
        seed: CP-SAT random seed (determinism: same input + seed -> same
            output).
        max_rounds: reinforcement bound (see module docstring's termination
            argument).
        max_displacement_mm: optional hard per-component Manhattan
            displacement bound for every ref in the repair (see
            ``solve_placement``). When set, the repair is a *bounded*
            repair: no component may move farther than this (feasibility
            permitting) -- the formulation that keeps the solved placement
            inside a displacement envelope around the current board and
            therefore protects the existing routed copper.
        chain_exempt_pairs: protective-impedance-chain sibling pairs
            exempted from the keep-away constraints (the same single
            exemption the real-board fixture's proximity check applies).
        netlist/board: optional pre-parsed CP-SAT inputs (tests inject
            synthetic ones); parsed from ``pcb_path`` when absent.

    Returns:
        A ``ClearanceRepairReport`` (see its docstring for status values).
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    if netlist is None or board is None:
        parse_result = parse_kicad_pcb(pcb_path)
        netlist = parse_result.netlist
        board = parse_result.board
        assert board is not None, "Board geometry parsing failed"

    comp_refs: set[str] = set()
    current_positions: dict[str, tuple[float, float]] = {}
    current_rotations: dict[str, int] = {}
    for comp in netlist.components:
        if comp.initial_position is None:
            continue
        ref = comp.ref
        comp_refs.add(ref)
        current_positions[ref] = comp.initial_position
        current_rotations[ref] = int(comp.initial_rotation or 0)

    # Baseline: the independent checker on the CURRENT board (no solve).
    baseline_result = verify_iec60335_compliance(placement, voltage_domains)
    baseline_inter, baseline_intra = _inter_intra_split(baseline_result)
    baseline_pairs = len(
        {
            frozenset((v.ref_a, v.ref_b))
            for v in baseline_inter
            if v.ref_a and v.ref_b
        }
    )

    # Constraint set: full domain-clearance + unclassified-near-HV keep-away.
    domain_constraints = generate_domain_clearance_constraints(
        placement, voltage_domains, component_refs=comp_refs
    )
    keepaway_constraints = generate_unclassified_hv_keepaway_constraints(
        placement,
        voltage_domains,
        component_refs=comp_refs,
        exempt_pairs=chain_exempt_pairs,
    )
    constraints: list[SeparatedConstraint] = [
        *domain_constraints,
        *keepaway_constraints,
    ]
    constrained_pairs: set[frozenset[str]] = {
        frozenset((c.a, c.b))
        for c in constraints
        if isinstance(c.a, str) and isinstance(c.b, str)
    }

    hint_positions = {
        ref: (x, y, current_rotations.get(ref, 0)) for ref, (x, y) in current_positions.items()
    }

    rounds: list[ClearanceRepairRound] = []
    unreinforced: list[tuple[str, str]] = []
    final_positions: dict[str, tuple[float, float]] = {}
    final_rotations: dict[str, int] = {}
    total_displacement = 0.0
    audit_violations_total = 0
    status = "max_rounds"
    reason = ""

    for round_index in range(max_rounds):
        result = solve_placement(
            netlist=netlist,
            board=board,
            extra_constraints=list(constraints),
            timeout_ms=timeout_ms,
            seed=seed,
            hint_positions=hint_positions,
            minimize_displacement_to=current_positions,
            fixed_rotations=current_rotations,
            max_displacement_mm=max_displacement_mm,
        )

        if result.status not in ("optimal", "feasible"):
            names = [u.get("name", "?") for u in result.unsat_core[:8]]
            # Distinguish a PROVEN UNSAT from an inconclusive timeout: only
            # the former is an infeasibility finding. A caller must never
            # mistake "the solver gave up at the time budget" for "no
            # feasible placement exists" -- the issue #504 requirement that
            # the machinery reports infeasibility honestly, not by
            # conflation.
            status = "infeasible" if result.status == "infeasible" else "unknown"
            reason = (
                f"solve {round_index + 1} returned {result.status}; "
                f"unsat_core={len(result.unsat_core)} ({', '.join(names)}); "
                + (
                    "proven UNSAT -- no feasible placement exists for this "
                    "constraint set (board-layout/footprint problem, not "
                    "machinery failure)"
                    if result.status == "infeasible"
                    else "no solution found within the time budget -- NOT a "
                    "proof of infeasibility; retry with a larger timeout_ms "
                    "or smaller constraint set"
                )
            )
            break

        # R24 item-3 post-solve audit: recompute real distances from the
        # resolved coordinates, independent of the solver's feasibility claim.
        audit = audit_domain_clearance(constraints, result.positions)
        audit_violations_total = len(audit)

        # Independent re-check with the copper-to-copper checker.
        solved_placement = _override_positions(placement, result.positions)
        check = verify_iec60335_compliance(solved_placement, voltage_domains)
        inter, intra = _inter_intra_split(check)

        displacement = sum(
            abs(result.positions[ref][0] - x) + abs(result.positions[ref][1] - y)
            for ref, (x, y) in current_positions.items()
            if ref in result.positions
        )
        moved = tuple(
            sorted(
                ref
                for ref, (x, y) in current_positions.items()
                if ref in result.positions
                and (
                    abs(result.positions[ref][0] - x) > 0.001
                    or abs(result.positions[ref][1] - y) > 0.001
                )
            )
        )

        rounds.append(
            ClearanceRepairRound(
                index=round_index,
                solve_status=result.status,
                solve_time_ms=result.solve_time_ms,
                total_constraints=len(constraints),
                audit_violations=len(audit),
                checker_after_inter=len(inter),
                checker_after_intra=len(intra),
                displacement_mm=displacement,
                moved_refs=moved,
                objective_value=result.objective_value,
            )
        )

        final_positions = dict(result.positions)
        final_rotations = dict(result.rotations)
        total_displacement = displacement

        if len(inter) == 0:
            status = "clean" if len(intra) == 0 else "intra_only"
            reason = (
                "all inter-component REQ-SAFE-01 pairs cleared; "
                f"{len(intra)} intra-footprint record(s) remain "
                "(unfixable by placement, reported as blockers)"
            )
            break

        # Reinforcement: hard-constrain every inter pair the checker still
        # flags that is not already constrained.
        new_constraints: list[SeparatedConstraint] = []
        seen: set[frozenset[str]] = set()
        for v in inter:
            if not v.ref_a or not v.ref_b:
                continue
            pair = frozenset((v.ref_a, v.ref_b))
            if pair in constrained_pairs or pair in seen:
                continue
            seen.add(pair)
            margin = max(
                (vv.required_mm for vv in inter if frozenset((vv.ref_a, vv.ref_b)) == pair),
                default=v.required_mm or 0.0,
            )
            new_constraints.append(
                SeparatedConstraint(
                    a=v.ref_a,
                    b=v.ref_b,
                    min_distance_mm=max(margin, 0.0),
                    tier=ConstraintTier.HARD,
                    because=(
                        f"reinforcement round {round_index + 1}: independent "
                        f"copper-to-copper checker still flags {v.ref_a}<->{v.ref_b}"
                    ),
                    id=f"domain_clearance_{v.ref_a}_{v.ref_b}",
                )
            )

        if not new_constraints:
            # Every flagged pair already has a hard constraint that was SAT
            # this round -- a contradiction with the constraint's soundness
            # proof (box separation implies pad-copper separation). This is
            # a genuine constraint-model gap (bounds do not contain the real
            # pad copper); report it loudly and stop.
            status = "gap"
            unreinforced = [
                (v.ref_a or "", v.ref_b or "") for v in inter if v.ref_a and v.ref_b
            ]
            reason = (
                f"round {round_index + 1}: checker flags {len(inter)} inter "
                f"pair(s) whose hard constraints were SAT in the same solve -- "
                f"the solver's box model does not contain the real pad copper "
                f"for these pair(s); no placement constraint can fix them. "
                f"Pairs: {unreinforced}"
            )
            break

        constraints.extend(new_constraints)
        constrained_pairs |= seen
        logger.info(
            "repair round %d: added %d reinforcement constraint(s); re-solving",
            round_index + 1,
            len(new_constraints),
        )
    else:
        remaining_inter = len(inter) if "inter" in locals() else len(baseline_inter)
        reason = (
            f"reinforcement did not converge within max_rounds={max_rounds}; "
            f"{remaining_inter} inter violation(s) remain"
        )

    final_inter = rounds[-1].checker_after_inter if rounds else len(baseline_inter)
    final_intra = rounds[-1].checker_after_intra if rounds else len(baseline_intra)

    # Intra-footprint blockers, from the final solved placement: the refs
    # whose own pads straddle a domain boundary and therefore can never be
    # fixed by placement.
    intra_blocker_refs: tuple[str, ...] = ()
    if final_positions:
        final_check = verify_iec60335_compliance(
            _override_positions(placement, final_positions), voltage_domains
        )
        _, final_intra_violations = _inter_intra_split(final_check)
        intra_blocker_refs = tuple(
            sorted({v.ref_a or "" for v in final_intra_violations if v.ref_a})
        )
        final_intra = len(final_intra_violations)

    return ClearanceRepairReport(
        pcb_path=str(pcb_path),
        status=status,
        reason=reason,
        rounds=rounds,
        baseline_violations=baseline_result.error_count,
        baseline_pairs=baseline_pairs,
        final_inter_violations=final_inter,
        final_intra_violations=final_intra,
        intra_blocker_refs=intra_blocker_refs,
        unreinforced_pairs=tuple(unreinforced),
        final_positions=final_positions,
        final_rotations=final_rotations,
        total_displacement_mm=total_displacement,
        audit_violations=audit_violations_total,
        keepaway_constraints=len(keepaway_constraints),
        domain_constraints=len(domain_constraints),
    )


__all__ = [
    "ClearanceRepairReport",
    "ClearanceRepairRound",
    "run_clearance_repair_solve",
]
