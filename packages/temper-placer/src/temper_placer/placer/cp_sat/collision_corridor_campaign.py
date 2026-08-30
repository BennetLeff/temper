"""Fresh-model collision-aware creepage corridor campaign.

The loop in this module is intentionally an adapter, not a second campaign
state machine.  Rust owns cut identity, legal transitions, and checkpoint
bytes; Python only builds one CP-SAT model per round, audits its complete
candidate, and projects the immutable Rust frontier into that model.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import temper_orchestration as _rust

from temper_placer.placer.cp_sat.collision_cut_adapter import RUST_MODEL_UNITS_PER_MM
from temper_placer.placer.cp_sat.creepage_search_corridor_experiment import (
    CandidateGateResult,
    PreparedCorridorExperiment,
    _body_gate,
    _rust_gate,
    _validator_gate,
)
from temper_placer.placer.cp_sat.displacement_deletion_frontier import canonical_json

Axis = Literal["x", "y"]
TerminalKind = Literal[
    "accepted",
    "solver_unresolved",
    "proven_infeasible",
    "verifier_rejected",
    "invalid_experiment",
    "no_progress",
    "budget_exhausted",
    "error",
]


@dataclass(frozen=True, slots=True)
class CollisionCorridorLimits:
    """Independent limits for one axis campaign."""

    max_rounds: int = 4
    round_budget_s: float = 120.0
    total_budget_s: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.max_rounds, bool) or self.max_rounds <= 0:
            raise ValueError("max_rounds must be positive")
        for name, value in (
            ("round_budget_s", self.round_budget_s),
            ("total_budget_s", self.total_budget_s),
        ):
            if value is None:
                continue
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.total_budget_s is not None and not math.isclose(
            float(self.total_budget_s),
            self.max_rounds * float(self.round_budget_s),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("total_budget_s must equal max_rounds * round_budget_s")


@dataclass(frozen=True, slots=True)
class CollisionCorridorRoundTelemetry:
    """Plain evidence for one fresh child model."""

    round_index: int
    model_identity: str
    frontier_size: int
    cuts_applied: int
    elapsed_s: float
    solver_status: str
    candidate_digest: str | None = None
    first_incumbent_s: float | None = None
    conflicts: int | None = None
    branches: int | None = None
    diagnostics: tuple[str, ...] = ()
    witnesses: tuple[dict[str, object], ...] = ()
    cuts: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class CollisionCorridorTerminal:
    kind: TerminalKind
    reason: str = ""
    round_index: int | None = None


@dataclass(frozen=True, slots=True)
class CollisionCorridorCampaignResult:
    axis: Axis
    terminal: CollisionCorridorTerminal
    rounds: tuple[CollisionCorridorRoundTelemetry, ...] = ()
    gates: tuple[CandidateGateResult, ...] = ()
    candidate_positions: tuple[tuple[str, float, float], ...] = ()
    candidate_rotations: tuple[tuple[str, int], ...] = ()
    candidate_digest: str | None = None
    checkpoint_path: str | None = None

    @property
    def accepted(self) -> bool:
        return self.terminal.kind == "accepted"

    @property
    def terminal_kind(self) -> TerminalKind:
        return self.terminal.kind


def candidate_digest(positions: Mapping[str, Sequence[float]], rotations: Mapping[str, int]) -> str:
    """Hash the complete, sorted candidate representation deterministically."""

    rows = []
    for ref in sorted(positions):
        point = positions[ref]
        if isinstance(point, (str, bytes)) or len(point) != 2:
            raise ValueError("candidate positions must contain two coordinates")
        rows.append(
            {
                "ref": ref,
                "x_model": int(round(float(point[0]) * RUST_MODEL_UNITS_PER_MM)),
                "y_model": int(round(float(point[1]) * RUST_MODEL_UNITS_PER_MM)),
                "rotation": int(rotations[ref]),
            }
        )
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()


def _identity_parts(prepared: PreparedCorridorExperiment, axis: Axis) -> tuple[str, str, str, str]:
    hashes = dict(prepared.identity.input_sha256)
    code = dict(prepared.identity.tool_code_sha256)
    board = hashes.get("pcb") or next(iter(hashes.values()), "board")
    rules = hashlib.sha256(
        canonical_json(
            {
                "inputs": {key: value for key, value in hashes.items() if key != "pcb"},
                "requirements": prepared.identity.requirement_sha256,
            }
        ).encode("utf-8")
    ).hexdigest()
    solver = hashlib.sha256(canonical_json(code).encode("utf-8")).hexdigest()
    return board, rules, solver, axis


def _new_rust_campaign(
    prepared: PreparedCorridorExperiment,
    axis: Axis,
    limits: CollisionCorridorLimits,
    factory: Callable[..., object] | None,
) -> object:
    maker = factory or _rust.prepare_collision_campaign
    board, rules, solver, rust_axis = _identity_parts(prepared, axis)
    return maker(
        board,
        rules,
        solver,
        rust_axis,
        list(prepared.expected_refs),
        limits.max_rounds,
        int(round(limits.round_budget_s * 1000.0)),
    )


def _complete_candidate(
    solving: object,
    candidate: object,
    expected_refs: tuple[str, ...],
) -> tuple[object, dict[str, tuple[float, float]], dict[str, int], str]:
    positions_raw = getattr(candidate, "positions", None)
    rotations_raw = getattr(candidate, "rotations", None)
    if not isinstance(positions_raw, Mapping) or not isinstance(rotations_raw, Mapping):
        raise ValueError("solver returned no complete position and rotation mappings")
    if set(positions_raw) != set(expected_refs) or set(rotations_raw) != set(expected_refs):
        raise ValueError(
            "solver candidate coverage is incomplete: "
            f"position_missing={sorted(set(expected_refs) - set(positions_raw))}, "
            f"rotation_missing={sorted(set(expected_refs) - set(rotations_raw))}"
        )
    positions: dict[str, tuple[float, float]] = {}
    rotations: dict[str, int] = {}
    poses: dict[str, tuple[int, int, int]] = {}
    for ref in expected_refs:
        point = positions_raw[ref]
        if isinstance(point, (str, bytes)) or not isinstance(point, Sequence) or len(point) != 2:
            raise ValueError(f"candidate position for {ref!r} is malformed")
        x, y = float(point[0]), float(point[1])
        rotation = rotations_raw[ref]
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"candidate position for {ref!r} is non-finite")
        if isinstance(rotation, bool) or not isinstance(rotation, int) or rotation not in range(4):
            raise ValueError(f"candidate rotation for {ref!r} is malformed")
        positions[ref] = (x, y)
        rotations[ref] = rotation
        poses[ref] = (
            int(round(x * RUST_MODEL_UNITS_PER_MM)),
            int(round(y * RUST_MODEL_UNITS_PER_MM)),
            rotation,
        )
    digest = candidate_digest(positions, rotations)
    return solving.complete_candidate(poses), positions, rotations, digest


def _solver_status(candidate: object) -> str:
    return str(getattr(candidate, "status", "unknown")).strip().lower().replace("-", "_")


def _terminal_from_status(status: str) -> TerminalKind:
    if status == "infeasible":
        return "proven_infeasible"
    if status in {"unknown", "timeout"}:
        return "solver_unresolved"
    if status in {"model_invalid", "invalid"}:
        return "invalid_experiment"
    return "error"


def _telemetry(candidate: object) -> tuple[float | None, int | None, int | None]:
    raw = getattr(candidate, "solver_telemetry", None)
    if raw is None:
        return None, None, None

    def value(*names: str) -> tuple[object | None, str | None]:
        for attr in names:
            item = getattr(raw, attr, None)
            if item is not None:
                return item, attr
        return None, None

    first, first_name = value("first_incumbent_s", "first_incumbent_time_s", "first_incumbent_ms")
    if first_name and first_name.endswith("_ms") and first is not None:
        first = float(first) / 1000.0
    return (
        None if first is None else float(first),
        None if value("conflicts")[0] is None else int(value("conflicts")[0]),
        None
        if value("branches", "branches_explored")[0] is None
        else int(value("branches", "branches_explored")[0]),
    )


def _frontier_projection(cuts: Sequence[object]) -> list[dict[str, object]]:
    """Project opaque cuts only for a deterministic model-construction id."""

    fields = (
        "first",
        "second",
        "x_first",
        "y_first",
        "rotation_first",
        "x_second",
        "y_second",
        "rotation_second",
        "candidate_digest",
    )
    return [{field: getattr(cut, field) for field in fields} for cut in cuts]


def _terminal_witness_cut_projection(
    cuts: Sequence[object],
    witness_records: Sequence[Mapping[str, object]],
    positions: Mapping[str, Sequence[float]],
    rotations: Mapping[str, int],
) -> list[dict[str, object]]:
    """Project collision assignments added by a terminal round for evidence.

    Rust keeps the post-audit frontier inside its consuming terminal state.  A
    terminal decision cannot expose that state without making the decision
    resumable, so the evidence record also carries the exact assignment that
    the validated Rust witness would have added.  This is a projection only:
    it is never fed back into CP-SAT or used to decide whether a witness is
    actionable.
    """

    fields = (
        "first",
        "second",
        "x_first",
        "y_first",
        "rotation_first",
        "x_second",
        "y_second",
        "rotation_second",
    )
    existing = {tuple(getattr(cut, field) for field in fields) for cut in cuts}
    projected: list[dict[str, object]] = []
    for witness in witness_records:
        raw_a = witness.get("ref_a")
        raw_b = witness.get("ref_b")
        digest = witness.get("candidate_digest")
        if not isinstance(raw_a, str) or not isinstance(raw_b, str):
            raise ValueError("terminal collision witness has malformed component refs")
        if not isinstance(digest, str) or not digest:
            raise ValueError("terminal collision witness has no candidate digest")
        if raw_a not in positions or raw_b not in positions:
            raise ValueError("terminal collision witness is missing a candidate pose")
        first, second = raw_a, raw_b
        if first > second:
            first, second = second, first
        first_x, first_y = positions[first]
        second_x, second_y = positions[second]
        row = {
            "first": first,
            "second": second,
            "x_first": int(round(float(first_x) * RUST_MODEL_UNITS_PER_MM)),
            "y_first": int(round(float(first_y) * RUST_MODEL_UNITS_PER_MM)),
            "rotation_first": int(rotations[first]),
            "x_second": int(round(float(second_x) * RUST_MODEL_UNITS_PER_MM)),
            "y_second": int(round(float(second_y) * RUST_MODEL_UNITS_PER_MM)),
            "rotation_second": int(rotations[second]),
            "candidate_digest": digest,
        }
        key = tuple(row[field] for field in fields)
        if key in existing:
            continue
        existing.add(key)
        projected.append(row)
    return projected


def run_collision_corridor_campaign(
    prepared: PreparedCorridorExperiment,
    axis: Axis,
    *,
    limits: CollisionCorridorLimits | None = None,
    solver: Callable[..., object] | None = None,
    verifier: Callable[[object], object] | None = None,
    validator_audit: Callable[..., object] | None = None,
    body_audit: Callable[..., object] | None = None,
    campaign_factory: Callable[..., object] | None = None,
    checkpoint_path: str | None = None,
    checkpoint: object | None = None,
) -> CollisionCorridorCampaignResult:
    """Run one axis using a fresh model and complete Rust cut frontier each round."""

    if axis not in ("x", "y"):
        raise ValueError("axis must be x or y")
    limits = limits or CollisionCorridorLimits()
    expected = set(prepared.expected_refs)
    body_coverage = getattr(prepared, "body_coverage", None)
    if body_coverage is None:
        return CollisionCorridorCampaignResult(
            axis,
            CollisionCorridorTerminal(
                "invalid_experiment",
                "explicit F.Fab extraction coverage is required before Prepared",
            ),
        )
    if not getattr(body_coverage, "complete", False):
        missing = getattr(body_coverage, "missing", ())
        invalid = getattr(body_coverage, "invalid", {})
        return CollisionCorridorCampaignResult(
            axis,
            CollisionCorridorTerminal(
                "invalid_experiment",
                f"incomplete F.Fab coverage: missing={tuple(missing)}, invalid={tuple(sorted(invalid))}",
            ),
        )
    if set(prepared.fab_bodies) != expected:
        return CollisionCorridorCampaignResult(
            axis,
            CollisionCorridorTerminal(
                "invalid_experiment",
                "complete expected F.Fab geometry coverage is required before Prepared",
            ),
        )
    cuts: tuple[object, ...] = ()
    if checkpoint is None and checkpoint_path is not None and Path(checkpoint_path).exists():
        from temper_placer.placer.cp_sat.collision_corridor_checkpoint import (
            read_collision_campaign_checkpoint,
        )

        try:
            checkpoint = read_collision_campaign_checkpoint(checkpoint_path)
        except FileNotFoundError:
            checkpoint = None
        except ValueError as exc:
            return CollisionCorridorCampaignResult(
                axis, CollisionCorridorTerminal("invalid_experiment", str(exc))
            )
    if checkpoint is None:
        try:
            campaign = _new_rust_campaign(prepared, axis, limits, campaign_factory)
            start_round = int(getattr(campaign, "round", 0))
            solving = campaign.start_solving()
        except Exception as exc:
            return CollisionCorridorCampaignResult(
                axis,
                CollisionCorridorTerminal(
                    "invalid_experiment", f"campaign preparation failed: {exc}"
                ),
            )
    else:
        try:
            checkpoint.validate_for(*_identity_parts(prepared, axis))
            if int(checkpoint.max_rounds) != limits.max_rounds or int(
                checkpoint.round_budget_ms
            ) != int(round(limits.round_budget_s * 1000.0)):
                return CollisionCorridorCampaignResult(
                    axis,
                    CollisionCorridorTerminal(
                        "invalid_experiment",
                        "checkpoint campaign limits do not match requested limits",
                    ),
                )
            stored_kind = getattr(checkpoint, "terminal_kind", None)
            if stored_kind:
                stored_reason = str(getattr(checkpoint, "terminal_reason", None) or "")
                stored_terminal: TerminalKind = (
                    "budget_exhausted" if stored_kind == "round_limit" else stored_kind
                )
                return CollisionCorridorCampaignResult(
                    axis,
                    CollisionCorridorTerminal(stored_terminal, stored_reason),
                    checkpoint_path=checkpoint_path,
                )
            campaign = checkpoint.restore_for(*_identity_parts(prepared, axis))
            start_round = int(getattr(campaign, "round", len(cuts)))
            cuts = tuple(campaign.cuts())
            solving = campaign.start_solving()
        except Exception as exc:
            return CollisionCorridorCampaignResult(
                axis,
                CollisionCorridorTerminal(
                    "invalid_experiment", f"checkpoint restore failed: {exc}"
                ),
            )

    if solver is None:
        from temper_placer.placer.cp_sat.encoder import solve_placement

        solver = solve_placement
    verifier = verifier or prepared.verifier
    if validator_audit is None:
        from temper_placer.placer.cp_sat.validator_audit import audit_domain_clearance_validator

        validator_audit = audit_domain_clearance_validator
    if body_audit is None:
        from temper_placer.placer.cp_sat.body_collision import audit_body_collisions

        body_audit = audit_body_collisions

    rounds: list[CollisionCorridorRoundTelemetry] = []
    started_campaign = time.monotonic()
    last_positions: tuple[tuple[str, float, float], ...] = ()
    last_rotations: tuple[tuple[str, int], ...] = ()
    last_digest: str | None = None
    last_gates: tuple[CandidateGateResult, ...] = ()
    # Rust's checkpoint frontier is authoritative.  A cut is added after a
    # completed round, so its cardinality is also the next zero-based round
    # index for this bounded campaign (the Rust state enforces the actual
    # max-round transition).
    for round_index in range(start_round, limits.max_rounds):
        if (
            limits.total_budget_s is not None
            and time.monotonic() - started_campaign >= limits.total_budget_s
        ):
            return CollisionCorridorCampaignResult(
                axis,
                CollisionCorridorTerminal(
                    "budget_exhausted", "total campaign budget exhausted", round_index
                ),
                tuple(rounds),
                last_gates,
                last_positions,
                last_rotations,
                last_digest,
                checkpoint_path,
            )
        round_started = time.monotonic()
        frontier_before = len(cuts)
        kwargs = dict(prepared.solve_kwargs)
        kwargs.update(
            {
                "timeout_ms": int(round(limits.round_budget_s * 1000.0)),
                "hint_positions": dict(prepared.hint_positions),
                "capture_telemetry": True,
                "experimental_omit_generated_creepage": False,
                "collision_campaign_cuts": cuts,
                "creepage_search_corridor": {
                    "manifest_path": prepared.manifest_path,
                    "hv_only_refs": prepared.hv_only_refs,
                    "selv_only_refs": prepared.selv_only_refs,
                    "axis": axis,
                    "gap_mm": prepared.identity.gap_mm,
                },
            }
        )
        # The campaign intentionally omits both legacy raising audit inputs.
        kwargs.pop("validator_input", None)
        kwargs.pop("body_collision_input", None)
        model_identity = hashlib.sha256(
            canonical_json(
                {
                    "identity": _identity_parts(prepared, axis),
                    "round": round_index,
                    "frontier": _frontier_projection(cuts),
                }
            ).encode()
        ).hexdigest()
        try:
            raw_candidate = solver(prepared.netlist, prepared.board, **kwargs)
        except Exception as exc:
            rounds.append(
                CollisionCorridorRoundTelemetry(
                    round_index,
                    model_identity,
                    len(cuts),
                    0,
                    time.monotonic() - round_started,
                    "error",
                    diagnostics=(f"solver raised {type(exc).__name__}: {exc}",),
                )
            )
            return CollisionCorridorCampaignResult(
                axis,
                CollisionCorridorTerminal("error", str(exc), round_index),
                tuple(rounds),
                last_gates,
                last_positions,
                last_rotations,
                last_digest,
                checkpoint_path,
            )
        status = _solver_status(raw_candidate)
        first, conflicts, branches = _telemetry(raw_candidate)
        if status not in {"optimal", "feasible"}:
            rounds.append(
                CollisionCorridorRoundTelemetry(
                    round_index,
                    model_identity,
                    len(cuts),
                    0,
                    time.monotonic() - round_started,
                    status,
                    first_incumbent_s=first,
                    conflicts=conflicts,
                    branches=branches,
                )
            )
            kind = _terminal_from_status(status)
            return CollisionCorridorCampaignResult(
                axis,
                CollisionCorridorTerminal(kind, f"solver returned {status}", round_index),
                tuple(rounds),
                last_gates,
                last_positions,
                last_rotations,
                last_digest,
                checkpoint_path,
            )
        try:
            candidate, positions, rotations, digest = _complete_candidate(
                solving, raw_candidate, prepared.expected_refs
            )
            # Cache the body audit so the collision result used to derive
            # witnesses is exactly the result represented by the typed gate.
            body_result_cache: list[object] = []

            def cached_body_audit(
                *args: object, _cache: list[object] = body_result_cache
            ) -> object:
                if not _cache:
                    _cache.append(body_audit(*args))
                return _cache[0]

            gates = (
                _rust_gate(verifier, raw_candidate, prepared.identity.requirement_count or 0),
                _validator_gate(validator_audit, prepared, positions, rotations),
                _body_gate(cached_body_audit, prepared, positions, rotations),
            )
            last_positions = tuple((ref, *positions[ref]) for ref in sorted(positions))
            last_rotations = tuple((ref, rotations[ref]) for ref in sorted(rotations))
            last_digest = digest
            last_gates = gates
            rust_creepage, validator, body = gates
            gate_errors = [
                f"{gate.name}: {gate.diagnostics[0] if gate.diagnostics else 'audit failed'}"
                for gate in gates
                if gate.status == "error"
            ]
            if gate_errors:
                raise RuntimeError("acceptance instrument error: " + "; ".join(gate_errors))
            rust_creepage_status = (
                "passed"
                if rust_creepage.status == "passed"
                else f"rejected:{rust_creepage.diagnostics[0] if rust_creepage.diagnostics else 'creepage gate failed'}"
            )
            provenance_status = (
                "trusted"
                if validator.status == "passed"
                else f"rejected:{validator.diagnostics[0] if validator.diagnostics else 'REQ-SAFE-01 gate failed'}"
            )
            body_status = (
                "passed"
                if body.status == "passed"
                else f"rejected:{body.diagnostics[0] if body.diagnostics else 'F.Fab collision'}"
            )
            witnesses = []
            witness_records: list[dict[str, object]] = []
            body_result = body_result_cache[0] if body_result_cache else None
            for violation in getattr(body_result, "violations", ()):
                ref_a = str(violation.ref_a)
                ref_b = str(violation.ref_b)
                overlap_mm2 = float(violation.overlap_mm2)
                witnesses.append((ref_a, ref_b, overlap_mm2, digest))
                witness_records.append(
                    {
                        "ref_a": ref_a,
                        "ref_b": ref_b,
                        "overlap_mm2": overlap_mm2,
                        "candidate_digest": digest,
                    }
                )
            decision = candidate.audit(
                rust_creepage_status, body_status, provenance_status, witnesses
            )
        except Exception as exc:
            rounds.append(
                CollisionCorridorRoundTelemetry(
                    round_index,
                    model_identity,
                    len(cuts),
                    0,
                    time.monotonic() - round_started,
                    "model-invalid",
                    digest if "digest" in locals() else None,
                    first,
                    conflicts,
                    branches,
                    (str(exc),),
                )
            )
            return CollisionCorridorCampaignResult(
                axis,
                CollisionCorridorTerminal("invalid_experiment", str(exc), round_index),
                tuple(rounds),
                last_gates,
                last_positions,
                last_rotations,
                last_digest,
                checkpoint_path,
            )
        if decision.kind == "terminal":
            terminal_checkpoint = decision.terminal_checkpoint()
            terminal_kind = str(terminal_checkpoint.terminal_kind or "")
            terminal_cut_projection: list[dict[str, object]] = []
            if terminal_kind == "round_limit":
                terminal_cut_projection = _terminal_witness_cut_projection(
                    cuts,
                    witness_records,
                    positions,
                    rotations,
                )
            rounds.append(
                CollisionCorridorRoundTelemetry(
                    round_index,
                    model_identity,
                    len(cuts),
                    len(terminal_cut_projection),
                    time.monotonic() - round_started,
                    status,
                    digest,
                    first,
                    conflicts,
                    branches,
                    witnesses=tuple(witness_records),
                    cuts=tuple(_frontier_projection(cuts) + terminal_cut_projection),
                )
            )
            if checkpoint_path:
                from temper_placer.placer.cp_sat.collision_corridor_checkpoint import (
                    write_collision_campaign_checkpoint,
                )

                write_collision_campaign_checkpoint(checkpoint_path, terminal_checkpoint)
            terminal = decision.take_terminal()
            kind = str(terminal.kind)
            if kind == "accepted":
                terminal_kind: TerminalKind = "accepted"
            elif kind == "no_progress":
                terminal_kind = "no_progress"
            elif kind == "round_limit":
                terminal_kind = "budget_exhausted"
            elif kind == "invalid_experiment":
                terminal_kind = "invalid_experiment"
            else:
                terminal_kind = "verifier_rejected"
            return CollisionCorridorCampaignResult(
                axis,
                CollisionCorridorTerminal(terminal_kind, str(terminal.reason or ""), round_index),
                tuple(rounds),
                last_gates,
                last_positions,
                last_rotations,
                last_digest,
                checkpoint_path,
            )
        refining = decision.take_refining()
        cuts = tuple(refining.cuts())
        rounds.append(
            CollisionCorridorRoundTelemetry(
                round_index,
                model_identity,
                frontier_before,
                len(witness_records),
                time.monotonic() - round_started,
                status,
                digest,
                first,
                conflicts,
                branches,
                witnesses=tuple(witness_records),
                cuts=tuple(_frontier_projection(cuts)),
            )
        )
        if checkpoint_path:
            from temper_placer.placer.cp_sat.collision_corridor_checkpoint import (
                write_collision_campaign_checkpoint,
            )

            write_collision_campaign_checkpoint(checkpoint_path, refining.checkpoint())
        solving = refining.next_round()
    return CollisionCorridorCampaignResult(
        axis,
        CollisionCorridorTerminal("budget_exhausted", "maximum rounds exhausted"),
        tuple(rounds),
        last_gates,
        last_positions,
        last_rotations,
        last_digest,
        checkpoint_path,
    )


def resume_collision_corridor_campaign(
    prepared: PreparedCorridorExperiment,
    axis: Axis,
    checkpoint_path: str,
    **kwargs: object,
) -> CollisionCorridorCampaignResult:
    """Resume only from Rust-validated checkpoint bytes."""

    return run_collision_corridor_campaign(
        prepared,
        axis,
        checkpoint_path=checkpoint_path,
        **kwargs,
    )


__all__ = [
    "CollisionCorridorCampaignResult",
    "CollisionCorridorLimits",
    "CollisionCorridorRoundTelemetry",
    "CollisionCorridorTerminal",
    "candidate_digest",
    "resume_collision_corridor_campaign",
    "run_collision_corridor_campaign",
]
