"""Evidence schema and live runner for the collision-aware corridor probe.

The runner deliberately reuses the production preparation, solver, Rust
creepage verifier, and collision-campaign adapter.  This module owns only
the comparison envelope and its fail-closed validation; it is not a second
placement or collision policy.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from temper_placer.placer.cp_sat.collision_corridor_campaign import (
    CollisionCorridorCampaignResult,
    CollisionCorridorLimits,
    candidate_digest,
    run_collision_corridor_campaign,
)
from temper_placer.placer.cp_sat.creepage_search_corridor_experiment import (
    POLARITY,
    PRODUCTION_NUM_SEARCH_WORKERS,
    CandidateGateResult,
    PreparedCorridorExperiment,
    _body_gate,
    _rust_gate,
    _validator_gate,
    build_experiment_identity,
)
from temper_placer.placer.cp_sat.displacement_deletion_frontier import canonical_json

EVIDENCE_SCHEMA = "temper.collision-aware-creepage-corridor"
EVIDENCE_VERSION = 1
TERMINAL_KINDS = {
    "accepted",
    "solver_unresolved",
    "proven_infeasible",
    "verifier_rejected",
    "invalid_experiment",
    "no_progress",
    "budget_exhausted",
    "error",
}
RUN_KINDS = {"unrestricted_control", "collision_aware_campaign"}


class EvidenceValidationError(ValueError):
    """Raised when a measurement artifact cannot support its claims."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_identity() -> dict[str, object]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "UNKNOWN", None
    return {"commit": commit, "dirty": dirty}


def _solver_identity(prepared: PreparedCorridorExperiment) -> dict[str, object]:
    try:
        import ortools

        ortools_version = str(getattr(ortools, "__version__", "unknown"))
    except Exception:
        ortools_version = "unavailable"
    return {
        "solver": "ortools-cp-sat",
        "ortools_version": ortools_version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "seed": int(prepared.identity.seed),
        "num_search_workers": int(prepared.identity.num_search_workers),
    }


def _plain_gate(gate: CandidateGateResult) -> dict[str, object]:
    return {
        "name": gate.name,
        "status": gate.status,
        "checked_count": gate.checked_count,
        "violation_count": gate.violation_count,
        "diagnostics": list(gate.diagnostics),
        "details": {str(key): value for key, value in gate.details},
    }


def _telemetry(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    result: dict[str, object] = {}
    for name in (
        "first_incumbent_s",
        "first_incumbent_time_s",
        "conflicts",
        "branches",
        "branches_explored",
        "solver_wall_time_s",
        "wall_time_s",
    ):
        value = getattr(raw, name, None)
        if value is not None:
            result[name] = float(value) if isinstance(value, float) else int(value)
    if "first_incumbent_time_s" in result and "first_incumbent_s" not in result:
        result["first_incumbent_s"] = result["first_incumbent_time_s"]
    if "branches_explored" in result and "branches" not in result:
        result["branches"] = result["branches_explored"]
    return result


def _candidate_record(candidate: object, expected: Sequence[str]) -> dict[str, object]:
    positions = getattr(candidate, "positions", None)
    rotations = getattr(candidate, "rotations", None)
    if not isinstance(positions, Mapping) or not isinstance(rotations, Mapping):
        return {"complete": False, "positions": [], "rotations": [], "digest": None}
    expected_set = set(expected)
    if set(positions) != expected_set or set(rotations) != expected_set:
        return {"complete": False, "positions": [], "rotations": [], "digest": None}
    normalized_positions = []
    normalized_rotations = []
    position_map: dict[str, tuple[float, float]] = {}
    rotation_map: dict[str, int] = {}
    for ref in sorted(expected_set):
        point = positions[ref]
        if isinstance(point, (str, bytes)) or not isinstance(point, Sequence) or len(point) != 2:
            return {"complete": False, "positions": [], "rotations": [], "digest": None}
        x, y = float(point[0]), float(point[1])
        rotation = rotations[ref]
        if not math.isfinite(x) or not math.isfinite(y) or isinstance(rotation, bool):
            return {"complete": False, "positions": [], "rotations": [], "digest": None}
        position_map[ref] = (x, y)
        rotation_map[ref] = int(rotation)
        normalized_positions.append([ref, x, y])
        normalized_rotations.append([ref, int(rotation)])
    return {
        "complete": True,
        "positions": normalized_positions,
        "rotations": normalized_rotations,
        "digest": candidate_digest(position_map, rotation_map),
    }


def _unrestricted_control(
    prepared: PreparedCorridorExperiment,
    name: str,
    budget_s: float,
    *,
    solver: Callable[..., object] | None = None,
    verifier: Callable[[object], object] | None = None,
    validator_audit: Callable[..., object] | None = None,
    body_audit: Callable[..., object] | None = None,
) -> dict[str, object]:
    """Run one unrestricted model and retain the same gates as a campaign."""

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

    kwargs = dict(prepared.solve_kwargs)
    kwargs.update(
        {
            "timeout_ms": int(round(float(budget_s) * 1000.0)),
            "hint_positions": dict(prepared.hint_positions),
            "capture_telemetry": True,
            "experimental_omit_generated_creepage": False,
        }
    )
    kwargs.pop("validator_input", None)
    kwargs.pop("body_collision_input", None)
    started = time.monotonic()
    try:
        candidate = solver(prepared.netlist, prepared.board, **kwargs)
    except Exception as exc:
        elapsed = time.monotonic() - started
        return {
            "id": name,
            "kind": "unrestricted_control",
            "axis": None,
            "budget_s": float(budget_s),
            "terminal": {"kind": "error", "reason": f"solver raised {type(exc).__name__}: {exc}"},
            "rounds": [{
                "round_index": 0,
                "model_identity": hashlib.sha256(f"{name}:{budget_s}".encode()).hexdigest(),
                "frontier_size": 0,
                "cuts_applied": 0,
                "elapsed_s": elapsed,
                "solver_status": "error",
                "candidate_complete": False,
                "telemetry": {},
                "witnesses": [],
                "cuts": [],
            }],
            "cumulative": {
                "round_count": 1,
                "wall_time_s": elapsed,
                "first_incumbent_s": 0,
                "conflicts": 0,
                "branches": 0,
                "unique_cuts": 0,
            },
            "final": {"candidate": {"complete": False}, "gates": []},
            "classification": "insufficient_evidence",
        }

    status = str(getattr(candidate, "status", "unknown")).strip().lower().replace("-", "_")
    telemetry = _telemetry(getattr(candidate, "solver_telemetry", None))
    model_identity = hashlib.sha256(f"{name}:{budget_s}".encode()).hexdigest()
    if status not in {"optimal", "feasible"}:
        terminal = "proven_infeasible" if status == "infeasible" else "solver_unresolved"
        elapsed = time.monotonic() - started
        round_record = {
            "round_index": 0,
            "model_identity": model_identity,
            "frontier_size": 0,
            "cuts_applied": 0,
            "elapsed_s": elapsed,
            "solver_status": status,
            "candidate_complete": False,
            "telemetry": telemetry,
            "witnesses": [],
            "cuts": [],
        }
        return {
            "id": name,
            "kind": "unrestricted_control",
            "axis": None,
            "budget_s": float(budget_s),
            "terminal": {"kind": terminal, "reason": f"solver returned {status}"},
            "rounds": [round_record],
            "cumulative": {
                "round_count": 1,
                "wall_time_s": elapsed,
                "first_incumbent_s": float(telemetry.get("first_incumbent_s", 0) or 0),
                "conflicts": int(telemetry.get("conflicts", 0) or 0),
                "branches": int(telemetry.get("branches", 0) or 0),
                "unique_cuts": 0,
            },
            "final": {"candidate": {"complete": False}, "gates": []},
            "classification": "insufficient_evidence",
        }

    candidate_record = _candidate_record(candidate, prepared.expected_refs)
    gates: tuple[CandidateGateResult, ...] = ()
    if candidate_record["complete"]:
        positions = {str(row[0]): (float(row[1]), float(row[2])) for row in candidate_record["positions"]}  # type: ignore[index]
        rotations = {str(row[0]): int(row[1]) for row in candidate_record["rotations"]}  # type: ignore[index]
        gates = (
            _rust_gate(verifier, candidate, prepared.identity.requirement_count or 0),
            _validator_gate(validator_audit, prepared, positions, rotations),
            _body_gate(body_audit, prepared, positions, rotations),
        )
    passed = bool(gates) and all(gate.status == "passed" for gate in gates)
    gate_error = any(gate.status == "error" for gate in gates)
    terminal = "accepted" if passed else ("invalid_experiment" if gate_error else "verifier_rejected")
    classification = "accepted" if passed else "insufficient_evidence"
    elapsed = time.monotonic() - started
    return {
        "id": name,
        "kind": "unrestricted_control",
        "axis": None,
        "budget_s": float(budget_s),
        "terminal": {"kind": terminal, "reason": "all gates passed" if passed else "complete control was not accepted"},
        "rounds": [{
            "round_index": 0,
            "model_identity": model_identity,
            "frontier_size": 0,
            "cuts_applied": 0,
            "elapsed_s": elapsed,
            "solver_status": status,
            "candidate_complete": bool(candidate_record["complete"]),
            "candidate_digest": candidate_record.get("digest"),
            "telemetry": telemetry,
            "witnesses": [],
            "cuts": [],
        }],
        "cumulative": {
            "round_count": 1,
            "wall_time_s": elapsed,
            "first_incumbent_s": float(telemetry.get("first_incumbent_s", 0) or 0),
            "conflicts": int(telemetry.get("conflicts", 0) or 0),
            "branches": int(telemetry.get("branches", 0) or 0),
            "unique_cuts": 0,
        },
        "final": {"candidate": candidate_record, "gates": [_plain_gate(gate) for gate in gates]},
        "classification": classification,
    }


def _campaign_record(result: CollisionCorridorCampaignResult, budget_s: float) -> dict[str, object]:
    rounds = []
    for telemetry in result.rounds:
        rounds.append(
            {
                "round_index": telemetry.round_index,
                "model_identity": telemetry.model_identity,
                "frontier_size": telemetry.frontier_size,
                "cuts_applied": telemetry.cuts_applied,
                "elapsed_s": telemetry.elapsed_s,
                "solver_status": telemetry.solver_status,
                "candidate_digest": telemetry.candidate_digest,
                "candidate_complete": telemetry.candidate_digest is not None,
                "telemetry": {
                    "first_incumbent_s": telemetry.first_incumbent_s,
                    "conflicts": telemetry.conflicts,
                    "branches": telemetry.branches,
                },
                "witnesses": list(telemetry.witnesses),
                "cuts": list(telemetry.cuts),
                "diagnostics": list(telemetry.diagnostics),
            }
        )
    if not rounds:
        rounds.append(
            {
                "round_index": 0,
                "model_identity": hashlib.sha256(
                    f"campaign_{result.axis}:preflight".encode()
                ).hexdigest(),
                "frontier_size": 0,
                "cuts_applied": 0,
                "elapsed_s": 0.0,
                "solver_status": "not-run",
                "candidate_complete": False,
                "candidate_digest": None,
                "telemetry": {},
                "witnesses": [],
                "cuts": [],
                "diagnostics": [result.terminal.reason],
            }
        )
    gates = [_plain_gate(gate) for gate in result.gates]
    candidate = {
        "complete": result.candidate_digest is not None,
        "digest": result.candidate_digest,
        "positions": [list(row) for row in result.candidate_positions],
        "rotations": [list(row) for row in result.candidate_rotations],
    }
    unique_cuts = {
        canonical_json(cut)
        for round_record in rounds
        for cut in round_record["cuts"]  # type: ignore[index]
    }
    complete_rejected = any(
        bool(item["candidate_complete"]) and item["cuts_applied"] > 0 for item in rounds
    )
    falsification = complete_rejected and result.terminal_kind in {"no_progress", "budget_exhausted"}
    classification = "accepted" if result.accepted else (
        "bounded_non_convergence" if falsification else "insufficient_evidence"
    )
    first_values = [
        item["telemetry"]["first_incumbent_s"]
        for item in rounds
        if item["telemetry"].get("first_incumbent_s") is not None  # type: ignore[union-attr]
    ]
    conflicts = [
        item["telemetry"]["conflicts"]
        for item in rounds
        if item["telemetry"].get("conflicts") is not None  # type: ignore[union-attr]
    ]
    branches = [
        item["telemetry"]["branches"]
        for item in rounds
        if item["telemetry"].get("branches") is not None  # type: ignore[union-attr]
    ]
    return {
        "id": f"campaign_{result.axis}",
        "kind": "collision_aware_campaign",
        "axis": result.axis,
        "budget_s": float(budget_s),
        "terminal": {
            "kind": result.terminal_kind,
            "reason": result.terminal.reason,
            "round_index": result.terminal.round_index,
        },
        "rounds": rounds,
        "cumulative": {
            "round_count": len(rounds),
            "wall_time_s": sum(float(item["elapsed_s"]) for item in rounds),
            "first_incumbent_s": sum(float(value) for value in first_values),
            "conflicts": sum(int(value) for value in conflicts),
            "branches": sum(int(value) for value in branches),
            "unique_cuts": len(unique_cuts),
        },
        "final": {"candidate": candidate, "gates": gates},
        "falsification_preconditions": {
            "complete_rejected_candidate": complete_rejected,
            "sound_applied_cut": any(item["cuts_applied"] > 0 for item in rounds),
            "repeated_frontier_or_exhausted_bound": result.terminal_kind in {"no_progress", "budget_exhausted"},
        },
        "classification": classification,
    }


def validate_collision_corridor_evidence(payload: Mapping[str, object]) -> None:
    """Validate schema, identity, run totals, and acceptance claims."""

    def fail(message: str) -> None:
        raise EvidenceValidationError(message)

    if payload.get("schema") != EVIDENCE_SCHEMA or payload.get("version") != EVIDENCE_VERSION:
        fail("unsupported collision corridor evidence schema or version")
    provenance = payload.get("provenance")
    regime = payload.get("regime")
    runs = payload.get("runs")
    if not isinstance(provenance, Mapping) or not isinstance(regime, Mapping):
        fail("provenance and regime objects are required")
    if not isinstance(runs, Sequence) or isinstance(runs, (str, bytes)) or len(runs) != 4:
        fail("evidence must contain exactly four runs")
    if provenance.get("board_hash_before") != provenance.get("board_hash_after"):
        fail("board changed during measurement")
    if provenance.get("board_byte_identical") is not True:
        fail("board_byte_identical must be true")
    board_hash = provenance.get("board_sha256")
    if (
        not isinstance(board_hash, str)
        or len(board_hash) != 64
        or any(character not in "0123456789abcdef" for character in board_hash)
        or board_hash != provenance.get("board_hash_before")
    ):
        fail("board hash identity is stale or malformed")
    corridor = regime.get("corridor")
    campaign_limits = regime.get("campaign_limits")
    if not isinstance(corridor, Mapping) or corridor.get("axis") != "both":
        fail("regime must declare one exact corridor shared by x and y")
    if not isinstance(campaign_limits, Mapping):
        fail("campaign_limits are required")
    if float(campaign_limits.get("max_rounds", 0)) != 4 or float(campaign_limits.get("round_budget_s", 0)) != 120.0:
        fail("campaign limits must be four independent 120-second rounds")
    if float(campaign_limits.get("total_budget_s", 0)) != 480.0:
        fail("campaign total allowance must be 480 seconds")
    seen_ids: set[str] = set()
    seen_axes: set[str] = set()
    for raw in runs:
        if not isinstance(raw, Mapping):
            fail("run record must be an object")
        run_id = str(raw.get("id", ""))
        if not run_id or run_id in seen_ids:
            fail("run ids must be nonempty and unique")
        seen_ids.add(run_id)
        kind = raw.get("kind")
        if kind not in RUN_KINDS:
            fail(f"unknown run kind: {kind!r}")
        axis = raw.get("axis")
        if kind == "collision_aware_campaign":
            if axis not in {"x", "y"} or axis in seen_axes:
                fail("campaigns must contain independent x and y axes exactly once")
            seen_axes.add(str(axis))
            if float(raw.get("budget_s", 0)) != 480.0:
                fail("campaign budget must equal four 120-second rounds")
        elif axis is not None:
            fail("unrestricted controls cannot carry a campaign axis")
        if run_id == "historical_control_120s" and (
            kind != "unrestricted_control" or float(raw.get("budget_s", 0)) != 120.0
        ):
            fail("historical control must use the 120-second regime")
        if run_id == "matched_control_480s" and (
            kind != "unrestricted_control" or float(raw.get("budget_s", 0)) != 480.0
        ):
            fail("matched control must use the 480-second regime")
        terminal = raw.get("terminal")
        rounds = raw.get("rounds")
        if not isinstance(terminal, Mapping) or terminal.get("kind") not in TERMINAL_KINDS:
            fail(f"unknown terminal kind in {run_id}")
        if not isinstance(rounds, Sequence) or isinstance(rounds, (str, bytes)) or not rounds:
            fail(f"run {run_id} has no rounds")
        cumulative = raw.get("cumulative")
        final = raw.get("final")
        if not isinstance(cumulative, Mapping):
            fail(f"run {run_id} has no cumulative telemetry")
        if int(cumulative.get("round_count", -1)) != len(rounds):
            fail(f"run {run_id} cumulative round count is inconsistent")
        round_maps = [item for item in rounds if isinstance(item, Mapping)]
        if len(round_maps) != len(rounds):
            fail(f"run {run_id} contains a malformed round")
        expected_wall = sum(float(item.get("elapsed_s", 0.0)) for item in round_maps)
        expected_first = sum(
            float(telemetry.get("first_incumbent_s", 0.0) or 0.0)
            for item in round_maps
            if isinstance((telemetry := item.get("telemetry", {})), Mapping)
        )
        expected_conflicts = sum(
            int(telemetry.get("conflicts", 0) or 0)
            for item in round_maps
            if isinstance((telemetry := item.get("telemetry", {})), Mapping)
        )
        expected_branches = sum(
            int(telemetry.get("branches", 0) or 0)
            for item in round_maps
            if isinstance((telemetry := item.get("telemetry", {})), Mapping)
        )
        unique_cuts = {
            canonical_json(cut)
            for item in round_maps
            for cut in item.get("cuts", ())
            if isinstance(cut, Mapping)
        }
        if not math.isclose(
            float(cumulative.get("wall_time_s", -1)), expected_wall, rel_tol=0.0, abs_tol=1e-6
        ):
            fail(f"run {run_id} cumulative wall time is inconsistent")
        if not math.isclose(
            float(cumulative.get("first_incumbent_s", -1)),
            expected_first,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            fail(f"run {run_id} cumulative first-incumbent time is inconsistent")
        if int(cumulative.get("conflicts", -1)) != expected_conflicts:
            fail(f"run {run_id} cumulative conflicts are inconsistent")
        if int(cumulative.get("branches", -1)) != expected_branches:
            fail(f"run {run_id} cumulative branches are inconsistent")
        if int(cumulative.get("unique_cuts", -1)) != len(unique_cuts):
            fail(f"run {run_id} unique cut total is inconsistent")
        if not isinstance(final, Mapping):
            fail(f"run {run_id} has no final gate record")
        candidate = final.get("candidate")
        gates = final.get("gates")
        if not isinstance(candidate, Mapping) or not isinstance(gates, Sequence):
            fail(f"run {run_id} final record is malformed")
        if terminal.get("kind") == "accepted":
            if candidate.get("complete") is not True:
                fail(f"accepted run {run_id} has no complete candidate")
            statuses = {gate.get("status") for gate in gates if isinstance(gate, Mapping)}
            if statuses != {"passed"} or len(gates) != 3:
                fail(f"accepted run {run_id} does not pass all three gates")
    if seen_axes != {"x", "y"}:
        fail("both independent campaign axes are required")
    required_ids = {
        "historical_control_120s",
        "matched_control_480s",
        "campaign_x",
        "campaign_y",
    }
    if seen_ids != required_ids:
        fail("comparison must contain the two named controls and independent x/y campaigns")


def canonical_collision_corridor_evidence(payload: Mapping[str, object]) -> str:
    validate_collision_corridor_evidence(payload)
    return canonical_json(payload)


def read_collision_corridor_evidence(path: str | Path) -> dict[str, object]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError(f"could not read evidence: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise EvidenceValidationError("evidence root must be an object")
    validate_collision_corridor_evidence(payload)
    return dict(payload)


def write_collision_corridor_evidence(payload: Mapping[str, object], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_collision_corridor_evidence(payload) + "\n"
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(destination)


def run_collision_corridor_comparison(
    prepared: PreparedCorridorExperiment,
    *,
    historical_control_s: float = 120.0,
    matched_control_s: float = 480.0,
    campaign_limits: CollisionCorridorLimits | None = None,
    solver: Callable[..., object] | None = None,
    progress: Callable[[str, Mapping[str, object]], None] | None = None,
) -> dict[str, object]:
    """Run controls then independent collision-aware x/y campaigns."""

    limits = campaign_limits or CollisionCorridorLimits(max_rounds=4, round_budget_s=120.0, total_budget_s=480.0)
    board_path = next(
        path for path in (Path("pcb/temper.kicad_pcb"),) if path.is_file()
    )
    board_hash_before = _sha256(board_path)
    controls = []
    for name, budget in (("historical_control_120s", historical_control_s), ("matched_control_480s", matched_control_s)):
        record = _unrestricted_control(prepared, name, budget, solver=solver)
        controls.append(record)
        if progress:
            progress(name, record)
    campaigns = []
    for axis in ("x", "y"):
        result = run_collision_corridor_campaign(prepared, axis, limits=limits, solver=solver)
        record = _campaign_record(result, limits.max_rounds * limits.round_budget_s)
        campaigns.append(record)
        if progress:
            progress(f"campaign_{axis}", record)
    board_hash_after = _sha256(board_path)
    identity = prepared.identity
    payload: dict[str, object] = {
        "schema": EVIDENCE_SCHEMA,
        "version": EVIDENCE_VERSION,
        "provenance": {
            **_git_identity(),
            "source": "measured-live",
            "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "board_hash_before": board_hash_before,
            "board_hash_after": board_hash_after,
            "board_byte_identical": board_hash_before == board_hash_after,
            "board_sha256": board_hash_before,
            "input_sha256": dict(identity.input_sha256),
            "tool_code_sha256": dict(identity.tool_code_sha256),
            "engine": _solver_identity(prepared),
        },
        "regime": {
            "requirement_count": identity.requirement_count,
            "requirement_sha256": identity.requirement_sha256,
            "gap_mm": identity.gap_mm,
            "polarity": identity.polarity,
            "corridor": {
                "axis": "both",
                "gap_mm": identity.gap_mm,
                "hv_only_refs": list(prepared.hv_only_refs),
                "selv_only_refs": list(prepared.selv_only_refs),
            },
            "seed": identity.seed,
            "num_search_workers": identity.num_search_workers,
            "historical_control_budget_s": historical_control_s,
            "matched_control_budget_s": matched_control_s,
            "campaign_limits": {
                "max_rounds": limits.max_rounds,
                "round_budget_s": limits.round_budget_s,
                "total_budget_s": limits.total_budget_s,
            },
        },
        "runs": controls + campaigns,
    }
    validate_collision_corridor_evidence(payload)
    return payload


def prepare_u6_corridor_experiment(
    pcb_path: str | Path,
    constraints_path: str | Path,
    manifest_path: str | Path,
    *,
    seed: int = 0,
    warm_start_limit_s: float = 30.0,
) -> PreparedCorridorExperiment:
    """Prepare U6 inputs when optional acceptance artifacts are unavailable.

    This is intentionally narrower than ``prepare_corridor_experiment``:
    controls may still measure solver search, while campaign rounds fail
    closed before model construction if complete F.Fab coverage is absent.
    Missing REQ-SAFE-01 artifacts are retained as an untrusted gate input;
    no netlist or geometry fallback is synthesized.
    """

    from temper_placer.io.fab_body_extraction import (
        extract_fab_bodies,
        extract_fab_body_coverage,
    )
    from temper_placer.placer.cp_sat.body_collision import load_body_collision_allowlist
    from temper_placer.placer.cp_sat.isolation_barrier import (
        classify_domain_partition,
        load_domain_manifest_nets,
    )
    from temper_placer.placer.cp_sat.production_constraint_family_inputs import (
        _find_repo_file,
        make_production_constraint_family_verifier,
        prepare_production_constraint_family_inputs,
    )
    from temper_placer.placer.cp_sat.stripped_warm_start import (
        solve_production_stripped_instance_warm_start,
    )

    pcb = Path(pcb_path).resolve()
    constraints = Path(constraints_path).resolve()
    manifest = Path(manifest_path).resolve()
    inputs = prepare_production_constraint_family_inputs(
        pcb, constraints, seed=seed, include_audits=False
    )
    instance = inputs.stripped_instance
    requirements = tuple(getattr(instance, "requirements", ()))
    hv_nets, selv_nets = load_domain_manifest_nets(manifest)
    partition_result = classify_domain_partition(inputs.netlist.components, hv_nets, selv_nets)
    partition = {
        "hv_only": tuple(sorted(partition_result.hv_only)),
        "selv_only": tuple(sorted(partition_result.selv_only)),
        "isolators": tuple(sorted(partition_result.isolators)),
        "unclassified": tuple(sorted(partition_result.unclassified)),
    }
    all_refs = tuple(sorted(str(component.ref) for component in inputs.netlist.components))
    allowlist_path = _find_repo_file(
        "packages/temper-placer/configs/body_collision_allowlist.yaml", start=pcb
    )
    if allowlist_path is None:
        raise ValueError("F.Fab allowlist source file is unavailable")
    identity = build_experiment_identity(
        pcb_path=pcb,
        constraints_path=constraints,
        manifest_path=manifest,
        allowlist_path=allowlist_path,
        requirements=requirements,
        partition=partition,
        gap_mm=max(float(row[2]) for row in requirements),
        polarity=POLARITY,
        seed=seed,
        num_search_workers=PRODUCTION_NUM_SEARCH_WORKERS,
        solve_limit_s=120.0,
        watchdog_grace_s=5.0,
        warm_start_limit_s=warm_start_limit_s,
    )
    warm = solve_production_stripped_instance_warm_start(
        instance, timeout_s=warm_start_limit_s, num_search_workers=PRODUCTION_NUM_SEARCH_WORKERS
    )
    hints = getattr(warm, "hints", None)
    if getattr(warm, "usable", False) is not True or not isinstance(hints, Mapping):
        raise ValueError(str(getattr(warm, "message", None) or "Rust-verified stripped hint unavailable"))
    body_allowlist = load_body_collision_allowlist(allowlist_path)
    body_bodies = extract_fab_bodies(pcb)
    coverage = extract_fab_body_coverage(pcb, all_refs)
    solve_kwargs = dict(inputs.production_kwargs)
    solve_kwargs.update(
        {
            "experimental_omit_generated_creepage": False,
            "tank_creepage": inputs.families["tank_creepage"]["tank_creepage"],
        }
    )
    solve_kwargs.pop("validator_input", None)
    solve_kwargs.pop("body_collision_input", None)
    return PreparedCorridorExperiment(
        identity=identity,
        netlist=inputs.netlist,
        board=inputs.board,
        solve_kwargs=solve_kwargs,
        expected_refs=all_refs,
        hint_positions=tuple(
            (ref, (float(hints[ref][0]), float(hints[ref][1]), int(hints[ref][2])))
            for ref in all_refs
        ),
        manifest_path=manifest,
        hv_only_refs=partition["hv_only"],
        selv_only_refs=partition["selv_only"],
        verifier=make_production_constraint_family_verifier(inputs),
        domain_constraints=(),
        validator_placement={},
        voltage_domains={},
        fab_bodies=body_bodies,
        body_allowlist=body_allowlist,
        body_coverage=coverage,
    )


__all__ = [
    "EVIDENCE_SCHEMA",
    "EVIDENCE_VERSION",
    "EvidenceValidationError",
    "canonical_collision_corridor_evidence",
    "read_collision_corridor_evidence",
    "prepare_u6_corridor_experiment",
    "run_collision_corridor_comparison",
    "validate_collision_corridor_evidence",
    "write_collision_corridor_evidence",
]
