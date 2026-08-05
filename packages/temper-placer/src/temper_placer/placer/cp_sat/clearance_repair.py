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

**Validator-aligned audit (issue #523 gap 2).** ``run_clearance_repair_solve``
passes ``validator_input={"placement": placement, "voltage_domains":
voltage_domains}`` into every ``solve_placement`` call, so each solve round
re-runs the REQ-SAFE-01 validator itself on the solved placement and
classifies its violations (see ``validator_audit.py``). The behavior contract
is **fail-closed and round-aborting**: a HARD failure (a constraint-covered
inter-component pair that the exact-copper validator still flags on a
feasible/optimal solve -- the run-B "box-separated but copper-touching" case)
**raises RuntimeError inside solve_placement**, and the loop catches it and
terminates with status ``"gap"`` carrying the offending pair(s) -- it never
returns a report that claims repairability over an encoding-unsound solve. A
round-1 hard failure therefore aborts the whole repair (no further rounds are
attempted), but it surfaces as a loud ``"gap"`` report rather than propagating
the exception: the caller gets the classified evidence on the report, and the
"safety net" property of the raise is preserved inside ``solve_placement``
(any caller that does NOT catch it fails closed by construction). Intra-
footprint straddlers (placement-independent, e.g. K3's own G5LE-1 coil-to-
contact gap) and coverage gaps (inter pairs the generator never constrained --
the reinforcement loop's normal work) are **reported**, never raised: they
land on ``ClearanceRepairReport.validator_audit`` (the final round's
``DomainClearanceValidatorAuditResult``). The loop's own independent checker
stays (it drives reinforcement); the audit inside the solve is additive and is
the one that gates on exact copper.

**Fixed-copper hoisted (issue #617).** ``run_clearance_repair_solve`` now
accepts ``fixed_copper=`` (a dict, default ``None``) and forwards it into
every ``solve_placement`` round, so the production repair caller can express
the full run-B recipe -- the free refs' pads must not land on different-net
fixed copper (traces/vias/other pads; see ``fixed_copper.py``). This closes
the interface gap the wave-2 board write exposed (docs/evidence/2026-08-02-
k3-swap-and-board-write.md): Run A through this caller could not express
fixed-copper, moved 166 refs and regressed DRC to 1428-1437 errors, while the
Run-B direct solve (with fixed-copper) was the written, clean board. The
fixed-copper post-solve audit shares the validator audit's fail-closed
contract **exactly**: a violation on a feasible/optimal solve raises
``RuntimeError`` inside ``solve_placement``, the loop catches it and
terminates with status ``"gap"`` naming the offending ref(s) -- round-aborting
and never a repairable report over an encoding-unsound solve. The two audits'
handling is therefore consistent by construction (same raise, same catch,
same ``"gap"`` terminal status); the report's ``reason`` distinguishes which
audit fired. Absent (default ``None``), behaviour is byte-identical to before:
the loop callers that do not pass it are unchanged.

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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat._encoder_solve import solve_placement
from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance,
    generate_domain_clearance_constraints,
    generate_unclassified_hv_keepaway_constraints,
)
from temper_placer.placer.cp_sat.validator_audit import (
    DomainClearanceValidatorAuditResult,
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
    - ``"gap"``: a post-solve audit hard failure on a feasible solve -- a
      checker-flagged inter pair that survived a SAT solve (the solver's box
      model does not contain the component's real pad copper), OR a
      fixed-copper audit violation (a free ref's pad on different-net fixed
      copper within the margin) OR a REQ-SAFE-01 validator audit HARD failure
      (a constraint-covered inter pair the exact-copper validator still flags).
      All three classes mean the encoding is unsound for that solve. Reported
      loudly; never treated as success.
    - ``"max_rounds"``: reinforcement did not converge within the bound
      (should not happen given the termination argument above; reported).

    **Validator-aligned audit (issue #523 gap 2).** Every feasible solve
    round re-runs the REQ-SAFE-01 validator on the solved placement
    (``validator_input`` wired unconditionally into ``solve_placement``).
    The final round's classified result lands on ``validator_audit`` (plus
    the convenience counts below). A HARD failure never appears in this
    report's audit buckets: it RAISES inside ``solve_placement``, the loop
    catches it, and the repair terminates with status ``"gap"`` naming the
    offending pair(s) -- fail-closed, so an encoding-unsound solve is never
    reported as a repairable outcome (see the module docstring).

    **Fixed-copper recipe (issue #617).** When ``fixed_copper=`` is passed
    to ``run_clearance_repair_solve``, the recipe is forwarded into every
    solve round and recorded here (``fixed_copper_free_refs`` /
    ``fixed_copper_margin_mm``) so the caller's evidence can show exactly
    which recipe produced the placement. A fixed-copper audit hard failure
    (a free ref's pad on different-net fixed copper within the margin on a
    feasible solve) aborts the repair exactly like the validator audit's:
    the loop catches the raise from ``solve_placement`` and terminates with
    status ``"gap"``, ``fixed_copper_audit_violations`` carries the count
    from the aborting audit, and ``reason`` names the offending ref(s).
    ``fixed_copper_audit_violations`` is 0 on every other outcome (including
    a clean fixed-copper run -- the audit PASSED then, it did not count 0
    violations into a report field).
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
    #: REQ-SAFE-01 validator-aligned post-solve audit from the FINAL solve
    #: round (issue #523 gap 2) -- a ``DomainClearanceValidatorAuditResult``
    #: mirroring ``CpSatPlacementResult.validator_audit``: the classified
    #: buckets ``hard_failures`` / ``intra_footprint`` / ``coverage_gaps``,
    #: ``covered_pair_count``, ``validator_violation_count``, ``stats`` and
    #: ``geometry_trusted``. None when no feasible/optimal solve completed
    #: (status infeasible/unknown/gap/max_rounds with no usable round).
    #: HARD failures never land here: they RAISE inside solve_placement and
    #: abort the whole repair (fail-closed -- see the module docstring).
    validator_audit: DomainClearanceValidatorAuditResult | None = None
    #: Convenience counts mirroring the final round's validator audit
    #: buckets (0 when no audit ran). ``validator_hard_failures`` is
    #: contractually always 0 here -- a hard failure aborts the repair
    #: before a report is built.
    validator_hard_failures: int = 0
    validator_intra_footprint: int = 0
    validator_coverage_gaps: int = 0
    #: Whether the final round's audit measured trustworthy pad geometry
    #: (False when no audit ran -- nothing was verified, so the solve must
    #: not be treated as validator-clean on the strength of these counts).
    validator_geometry_trusted: bool = False
    #: Fixed-copper recipe forwarded into every solve round (issue #617):
    #: the sorted free refs (empty when no fixed_copper was passed) and the
    #: margin in mm (None when no fixed_copper was passed). Evidence fields
    #: only -- they record what the caller asked for, not what the audit
    #: found (see ``fixed_copper_audit_violations``).
    fixed_copper_free_refs: tuple[str, ...] = ()
    fixed_copper_margin_mm: float | None = None
    #: Number of fixed-copper audit violations when a fixed-copper audit
    #: hard failure aborted the repair (0 otherwise -- including a clean
    #: fixed-copper run, where the audit PASSED). Mirrors the
    #: ``validator_hard_failures`` contract: a hard failure never lands in
    #: a success report, it terminates the repair with status ``"gap"``.
    fixed_copper_audit_violations: int = 0

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
    fixed_copper: dict | None = None,
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
        fixed_copper: optional pad-vs-fixed-copper NoOverlap recipe
            (issue #617), forwarded unchanged into every ``solve_placement``
            round. The dict carries ``parse_result`` (a ``ParseResult``
            carrying ``.traces``/``.vias``/``.board``), ``free_refs`` (the
            refs whose pads must not land on different-net fixed copper),
            ``margin_mm`` (default 0.05) and ``include_other_pads`` (default
            True) -- see ``solve_placement``/``fixed_copper.py``. This is the
            piece the production caller could not express before the hoist
            (Run A vs Run B of the wave-2 write differ only by it). The
            fixed-copper post-solve audit runs inside every feasible round
            and shares the validator audit's fail-closed contract: a
            violation raises inside ``solve_placement``, the loop catches it
            and terminates with status ``"gap"`` (round-aborting; see the
            module docstring). The recipe is recorded on the report
            (``fixed_copper_free_refs``/``fixed_copper_margin_mm``). Default
            ``None``: no fixed-copper constraints, byte-identical to the
            pre-hoist behaviour.
        netlist/board: optional pre-parsed CP-SAT inputs (tests inject
            synthetic ones); parsed from ``pcb_path`` when absent.

    Returns:
        A ``ClearanceRepairReport`` (see its docstring for status values).

    Raises:
        RuntimeError: a REQ-SAFE-01 validator-aligned post-solve audit HARD
            failure on any feasible/optimal solve round -- a constraint-
            covered inter-component pair the exact-copper validator still
            flags (the run-B "box-separated but copper-touching" class) -- or
            a fixed-copper post-solve audit violation (a free ref's pad on
            different-net fixed copper within the margin), which shares the
            same raise contract (issue #617). Both are FAIL-CLOSED by design:
            the encoding is unsound for that solve. The loop catches either
            and returns status ``"gap"`` naming the offending pair(s)/ref(s)
            (see the module docstring); they are only re-raised here if the
            catch itself is not reached, which never happens in this loop --
            the raise is documented for the ``solve_placement`` contract, not
            as this function's normal exit. The repair recipe is expected
            validator-clean and fixed-copper-clean; this is the safety net,
            not the normal path.
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
    #: Fixed-copper audit violation count when a fixed-copper audit hard
    #: failure aborted the repair (0 otherwise). Set in the catch below.
    fixed_copper_audit_violations = 0
    #: The final successful round's validator-aligned audit result (None when
    #: no feasible/optimal solve completed -- hard failures raise instead).
    #: Cast from ``CpSatPlacementResult.validator_audit`` (typed ``object``
    #: on the result for import-layering) to the concrete audit result type:
    #: safe because ``validator_input`` is passed unconditionally on every
    #: round, so a feasible solve ALWAYS ran the audit.
    final_validator_audit: DomainClearanceValidatorAuditResult | None = None
    status = "max_rounds"
    reason = ""

    for round_index in range(max_rounds):
        try:
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
                # Issue #523 gap 2: re-run the REQ-SAFE-01 validator itself on
                # the solved placement (exact copper-to-copper, the function the
                # CI gate runs). HARD failures raise inside solve_placement and
                # are caught below -- the repair terminates with status "gap"
                # (fail-closed, never a repairable report); intra-footprint /
                # coverage-gap buckets land on result.validator_audit and are
                # copied to the report below. The cheap center audit
                # (audit_domain_clearance) stays independent of this.
                validator_input={
                    "placement": placement,
                    "voltage_domains": voltage_domains,
                },
                # Issue #617: the fixed-copper recipe (free refs' pads must
                # not land on different-net fixed copper) is forwarded into
                # every round so the production caller can express the full
                # run-B recipe. Its post-solve audit raises inside
                # solve_placement on a violation -- caught below, same
                # fail-closed "gap" handling as the validator audit.
                fixed_copper=fixed_copper,
            )
        except RuntimeError as exc:
            # Post-solve audit hard failure on a feasible/optimal solve.
            # Two classes share this raise contract (issue #617 makes them
            # consistent by construction):
            #   (1) the REQ-SAFE-01 validator audit (issue #523 gap 2): a
            #       constraint-covered inter pair the exact-copper validator
            #       still flags -- the box encoding is unsound for this solve;
            #   (2) the fixed-copper audit: a free ref's pad lands on
            #       different-net fixed copper within the margin -- the
            #       fixed-copper encoding is unsound for this solve.
            # Both are the same class the loop's own "gap" status exists for
            # (a checker-flagged pair whose hard constraint was SAT), so both
            # terminate with a loud "gap" report naming the offender(s)
            # instead of propagating the exception -- the caller gets the
            # evidence on the report, and no further rounds are attempted (a
            # round-1 hard failure aborts the whole repair).
            _msg = str(exc)
            if _msg.startswith("fixed-copper post-solve audit FAILED"):
                _fc_match = re.search(r"(\d+) violation\(s\)", _msg)
                _fc_refs = re.findall(r"([A-Za-z0-9_]+) pad ", _msg)
                fixed_copper_audit_violations = (
                    int(_fc_match.group(1)) if _fc_match else 0
                )
                status = "gap"
                unreinforced = [
                    (ref, "") for ref in dict.fromkeys(_fc_refs)
                ]  # dedupe, keep order
                reason = (
                    f"round {round_index + 1}: fixed-copper post-solve audit "
                    f"HARD failure ({fixed_copper_audit_violations} "
                    f"violation(s)) -- a free ref's pad overlaps different-"
                    f"net fixed copper within the margin on a feasible "
                    f"solve; the fixed-copper encoding is unsound for this "
                    f"solve (fail-closed). Ref(s): "
                    f"{sorted(set(_fc_refs)) or '?'}. {exc}"
                )
                logger.error(
                    "repair round %d: fixed-copper audit hard failure -> gap: %s",
                    round_index + 1,
                    exc,
                )
                break
            _pairs = re.findall(
                r"([A-Za-z0-9_]+)<->([A-Za-z0-9_]+)", _msg
            )
            status = "gap"
            unreinforced = list(dict.fromkeys(_pairs))  # dedupe, keep order
            reason = (
                f"round {round_index + 1}: REQ-SAFE-01 validator post-solve "
                f"audit HARD failure -- the solver's box model does not "
                f"contain the real pad copper for pair(s) {unreinforced}; no "
                f"placement constraint can fix them. Encoding-unsound for "
                f"this solve (fail-closed). {exc}"
            )
            logger.error(
                "repair round %d: validator audit hard failure -> gap: %s",
                round_index + 1,
                exc,
            )
            break

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
        final_validator_audit = cast(
            DomainClearanceValidatorAuditResult | None, result.validator_audit
        )

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

    _v_audit = final_validator_audit
    _fc_free_refs: tuple[str, ...] = ()
    _fc_margin: float | None = None
    if fixed_copper is not None:
        _fc_free_refs = tuple(sorted(fixed_copper.get("free_refs", ())))
        _fc_margin = (
            float(fixed_copper["margin_mm"]) if "margin_mm" in fixed_copper else 0.05
        )
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
        validator_audit=final_validator_audit,
        validator_hard_failures=(
            len(final_validator_audit.hard_failures)
            if final_validator_audit is not None
            else 0
        ),
        validator_intra_footprint=(
            len(final_validator_audit.intra_footprint)
            if final_validator_audit is not None
            else 0
        ),
        validator_coverage_gaps=(
            len(final_validator_audit.coverage_gaps)
            if final_validator_audit is not None
            else 0
        ),
        validator_geometry_trusted=(
            bool(final_validator_audit.geometry_trusted)
            if final_validator_audit is not None
            else False
        ),
        fixed_copper_free_refs=_fc_free_refs,
        fixed_copper_margin_mm=_fc_margin,
        fixed_copper_audit_violations=fixed_copper_audit_violations,
    )


__all__ = [
    "ClearanceRepairReport",
    "ClearanceRepairRound",
    "run_clearance_repair_solve",
]
