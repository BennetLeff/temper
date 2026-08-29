"""Bounded, two-axis production experiment for a declared search corridor.

This module is deliberately an experiment entrypoint, not a production
configuration surface.  It prepares the production inputs once, gives the x
and y topologies fresh worker processes, and records solver, process, and
acceptance outcomes independently.  Exact creepage, REQ-SAFE-01, and F.Fab
remain post-solve truth functions; none is passed into ``solve_placement``
where a hard-audit exception would erase a feasible solver result.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import multiprocessing as mp
import os
import queue as queue_module
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from temper_placer.placer.cp_sat.displacement_deletion_frontier import canonical_json

EXPERIMENT_SCHEMA = "temper.creepage-search-corridor-experiment"
EXPERIMENT_VERSION = 1
EXPECTED_REQUIREMENT_COUNT = 9_176
EXPECTED_MAX_GAP_MM = 12.6
PRODUCTION_NUM_SEARCH_WORKERS = 4
POLARITY = "hv-low-selv-high"

SolverStatus = Literal["not-run", "optimal", "feasible", "infeasible", "unknown", "model-invalid"]
ExecutionOutcome = Literal["not-started", "returned", "timeout", "error"]
AcceptanceVerdict = Literal["accepted", "rejected", "not-run", "gate-error"]
GateStatus = Literal["passed", "failed", "error", "not-run"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _pairs(value: Mapping[str, Sequence[str]]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (name, tuple(sorted(str(ref) for ref in refs))) for name, refs in sorted(value.items())
    )


def _plain_pairs(value: object | None) -> tuple[tuple[str, object], ...]:
    if value is None:
        return ()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        raw = dataclasses.asdict(value)
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        return (("value", str(value)),)
    return tuple((str(key), raw[key]) for key in sorted(raw))


@dataclass(frozen=True, slots=True)
class ExperimentIdentity:
    """Canonical meaning of one two-axis comparison."""

    input_sha256: tuple[tuple[str, str], ...]
    requirement_sha256: str | None
    requirement_count: int | None
    requirements_by_gap_mm: tuple[tuple[float, int], ...]
    partition: tuple[tuple[str, tuple[str, ...]], ...]
    gap_mm: float | None
    polarity: str
    seed: int
    num_search_workers: int
    solve_limit_s: float
    watchdog_grace_s: float
    warm_start_limit_s: float
    tool_code_sha256: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.requirement_count is not None and self.requirement_count < 0:
            raise ValueError("requirement_count must be non-negative or None")
        if self.gap_mm is not None and (not math.isfinite(self.gap_mm) or self.gap_mm <= 0.0):
            raise ValueError("gap_mm must be finite and positive or None")
        if self.num_search_workers <= 0:
            raise ValueError("num_search_workers must be positive")
        for name, value in (
            ("solve_limit_s", self.solve_limit_s),
            ("watchdog_grace_s", self.watchdog_grace_s),
            ("warm_start_limit_s", self.warm_start_limit_s),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True, slots=True)
class CandidateGateResult:
    """One acceptance truth function, kept separate from solver status."""

    name: str
    status: GateStatus
    checked_count: int | None = None
    violation_count: int | None = None
    diagnostics: tuple[str, ...] = ()
    details: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("gate name must be nonempty")
        if self.status not in {"passed", "failed", "error", "not-run"}:
            raise ValueError(f"invalid gate status {self.status!r}")


@dataclass(frozen=True, slots=True)
class AxisExperimentResult:
    """Plain terminal record for one fresh axis model."""

    axis: Literal["x", "y"]
    solver_status: SolverStatus
    execution_outcome: ExecutionOutcome
    acceptance_verdict: AcceptanceVerdict
    elapsed_s: float
    candidate_complete: bool = False
    candidate_positions: tuple[tuple[str, float, float], ...] = ()
    candidate_rotations: tuple[tuple[str, int], ...] = ()
    telemetry: tuple[tuple[str, object], ...] = ()
    corridor: tuple[tuple[str, object], ...] = ()
    gates: tuple[CandidateGateResult, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.axis not in {"x", "y"}:
            raise ValueError(f"invalid experiment axis {self.axis!r}")
        if self.solver_status not in {
            "not-run",
            "optimal",
            "feasible",
            "infeasible",
            "unknown",
            "model-invalid",
        }:
            raise ValueError(f"invalid solver status {self.solver_status!r}")
        if self.execution_outcome not in {"not-started", "returned", "timeout", "error"}:
            raise ValueError(f"invalid execution outcome {self.execution_outcome!r}")
        if self.acceptance_verdict not in {"accepted", "rejected", "not-run", "gate-error"}:
            raise ValueError(f"invalid acceptance verdict {self.acceptance_verdict!r}")
        if not math.isfinite(self.elapsed_s) or self.elapsed_s < 0.0:
            raise ValueError("axis elapsed_s must be finite and non-negative")
        candidate_verdicts = {"accepted", "rejected", "gate-error"}
        if self.candidate_complete:
            if self.solver_status not in {"optimal", "feasible"}:
                raise ValueError("a complete candidate requires a feasible solver status")
            if self.execution_outcome != "returned":
                raise ValueError("a complete candidate requires a returned execution")
            if self.acceptance_verdict not in candidate_verdicts:
                raise ValueError("a complete candidate requires an acceptance verdict")
            expected_gates = ("rust-creepage", "req-safe-01", "f-fab")
            if tuple(gate.name for gate in self.gates) != expected_gates:
                raise ValueError("a complete candidate requires the exact acceptance gate set")
            gate_statuses = {gate.status for gate in self.gates}
            if self.acceptance_verdict == "accepted" and gate_statuses != {"passed"}:
                raise ValueError("an accepted candidate requires every gate to pass")
            if self.acceptance_verdict == "rejected" and (
                "failed" not in gate_statuses or "error" in gate_statuses
            ):
                raise ValueError("a rejected candidate requires a failed gate and no gate error")
            if self.acceptance_verdict == "gate-error" and "error" not in gate_statuses:
                raise ValueError("a candidate gate-error verdict requires an errored gate")
        else:
            if self.acceptance_verdict in {"accepted", "rejected"}:
                raise ValueError("acceptance requires a complete candidate")
            if self.gates:
                raise ValueError("acceptance gates require a complete candidate")


@dataclass(frozen=True, slots=True)
class CreepageSearchCorridorExperimentRecord:
    """Versioned evidence for both independent axis probes."""

    identity: ExperimentIdentity
    axes: tuple[AxisExperimentResult, AxisExperimentResult]
    schema: str = EXPERIMENT_SCHEMA
    version: int = EXPERIMENT_VERSION

    def __post_init__(self) -> None:
        if self.schema != EXPERIMENT_SCHEMA or self.version != EXPERIMENT_VERSION:
            raise ValueError("unsupported creepage-search-corridor schema or version")
        if tuple(axis.axis for axis in self.axes) != ("x", "y"):
            raise ValueError("experiment record must contain x then y exactly once")

    @property
    def success(self) -> bool:
        return any(axis.acceptance_verdict == "accepted" for axis in self.axes)

    def to_dict(self) -> dict[str, object]:
        payload = dataclasses.asdict(self)
        payload["success"] = self.success
        return payload

    def to_json(self) -> str:
        return canonical_experiment_json(self)

    def write(self, path: str | Path) -> None:
        write_experiment_record(self, path)

    @classmethod
    def from_json(cls, text: str) -> CreepageSearchCorridorExperimentRecord:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid creepage-search-corridor JSON: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError("creepage-search-corridor JSON root must be an object")
        return _record_from_payload(payload)

    @classmethod
    def read(cls, path: str | Path) -> CreepageSearchCorridorExperimentRecord:
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class PreparedCorridorExperiment:
    """Validated shared inputs; opaque live objects never enter JSON."""

    identity: ExperimentIdentity
    netlist: object
    board: object
    solve_kwargs: Mapping[str, object]
    expected_refs: tuple[str, ...]
    hint_positions: tuple[tuple[str, tuple[float, float, int]], ...]
    manifest_path: Path
    hv_only_refs: tuple[str, ...]
    selv_only_refs: tuple[str, ...]
    verifier: Callable[[object], object]
    domain_constraints: tuple[object, ...]
    validator_placement: Mapping[str, object]
    voltage_domains: Mapping[str, object]
    fab_bodies: Mapping[str, object]
    body_allowlist: object


class SharedPreflightError(ValueError):
    """Shared failure that truthfully prevents both workers from starting."""

    def __init__(
        self, category: Literal["input", "gate"], message: str, identity: ExperimentIdentity
    ):
        super().__init__(message)
        self.category = category
        self.identity = identity


def build_experiment_identity(
    *,
    pcb_path: Path,
    constraints_path: Path,
    manifest_path: Path,
    allowlist_path: Path,
    requirements: Sequence[Sequence[object]],
    partition: Mapping[str, Sequence[str]],
    gap_mm: float,
    polarity: str,
    seed: int,
    num_search_workers: int,
    solve_limit_s: float,
    watchdog_grace_s: float,
    warm_start_limit_s: float,
) -> ExperimentIdentity:
    """Hash every artifact and setting that changes experiment meaning."""

    normalized_requirements = tuple(
        sorted((str(row[0]), str(row[1]), float(row[2])) for row in requirements)
    )
    gaps = Counter(float(row[2]) for row in normalized_requirements)
    code_paths = {
        "experiment": Path(__file__),
        "corridor": Path(__file__).with_name("creepage_search_corridor.py"),
        "solver": Path(__file__).with_name("_encoder_solve.py"),
        "solver_telemetry": Path(__file__).with_name("solver_telemetry.py"),
        "production_inputs": Path(__file__).with_name("production_constraint_family_inputs.py"),
    }
    return ExperimentIdentity(
        input_sha256=tuple(
            sorted(
                (
                    ("pcb", _sha256(Path(pcb_path))),
                    ("constraints", _sha256(Path(constraints_path))),
                    ("manifest", _sha256(Path(manifest_path))),
                    ("body_allowlist", _sha256(Path(allowlist_path))),
                )
            )
        ),
        requirement_sha256=_digest_json(normalized_requirements),
        requirement_count=len(normalized_requirements),
        requirements_by_gap_mm=tuple(sorted(gaps.items())),
        partition=_pairs(partition),
        gap_mm=float(gap_mm),
        polarity=str(polarity),
        seed=int(seed),
        num_search_workers=int(num_search_workers),
        solve_limit_s=float(solve_limit_s),
        watchdog_grace_s=float(watchdog_grace_s),
        warm_start_limit_s=float(warm_start_limit_s),
        tool_code_sha256=tuple(sorted((name, _sha256(path)) for name, path in code_paths.items())),
    )


def _placeholder_identity(
    paths: Mapping[str, Path],
    *,
    seed: int,
    solve_limit_s: float,
    watchdog_grace_s: float,
    warm_start_limit_s: float,
) -> ExperimentIdentity:
    hashes: list[tuple[str, str]] = []
    for name, path in sorted(paths.items()):
        if path.is_file():
            hashes.append((name, _sha256(path)))
    return ExperimentIdentity(
        input_sha256=tuple(hashes),
        requirement_sha256=None,
        requirement_count=None,
        requirements_by_gap_mm=(),
        partition=(),
        gap_mm=None,
        polarity=POLARITY,
        seed=seed,
        num_search_workers=PRODUCTION_NUM_SEARCH_WORKERS,
        solve_limit_s=solve_limit_s,
        watchdog_grace_s=watchdog_grace_s,
        warm_start_limit_s=warm_start_limit_s,
        tool_code_sha256=(("experiment", _sha256(Path(__file__))),),
    )


def _validated_number(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def prepare_corridor_experiment(
    pcb_path: str | Path,
    constraints_path: str | Path,
    manifest_path: str | Path,
    *,
    hv_only_refs: Sequence[str],
    selv_only_refs: Sequence[str],
    seed: int = 0,
    solve_limit_s: float = 120.0,
    watchdog_grace_s: float = 5.0,
    warm_start_limit_s: float = 30.0,
    num_search_workers: int = PRODUCTION_NUM_SEARCH_WORKERS,
    input_builder: Callable[..., object] | None = None,
    warm_start_builder: Callable[..., object] | None = None,
) -> PreparedCorridorExperiment:
    """Prepare and validate all shared production artifacts exactly once."""

    pcb = Path(pcb_path).resolve()
    constraints = Path(constraints_path).resolve()
    manifest = Path(manifest_path).resolve()
    base_paths = {"pcb": pcb, "constraints": constraints, "manifest": manifest}
    placeholder = _placeholder_identity(
        base_paths,
        seed=seed,
        solve_limit_s=float(solve_limit_s),
        watchdog_grace_s=float(watchdog_grace_s),
        warm_start_limit_s=float(warm_start_limit_s),
    )
    try:
        solve_limit = _validated_number(solve_limit_s, "solve_limit_s")
        grace = _validated_number(watchdog_grace_s, "watchdog_grace_s")
        warm_limit = _validated_number(warm_start_limit_s, "warm_start_limit_s")
        if num_search_workers != PRODUCTION_NUM_SEARCH_WORKERS:
            raise ValueError(
                "production solve_placement currently pins num_search_workers=4; "
                "the experiment cannot truthfully request another value"
            )
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        for name, path in base_paths.items():
            if not path.is_file():
                raise ValueError(f"{name} input does not exist: {path}")

        if input_builder is None:
            from temper_placer.placer.cp_sat.production_constraint_family_inputs import (
                prepare_production_constraint_family_inputs,
            )

            input_builder = prepare_production_constraint_family_inputs
        inputs = input_builder(pcb, constraints, seed=seed, include_audits=True)
        instance = getattr(inputs, "stripped_instance", None)
        requirements = tuple(getattr(instance, "requirements", ()))
        if len(requirements) != EXPECTED_REQUIREMENT_COUNT:
            raise ValueError(
                "authoritative exact-creepage census mismatch: "
                f"expected {EXPECTED_REQUIREMENT_COUNT}, got {len(requirements)}"
            )
        if not requirements:
            raise ValueError("authoritative exact-creepage set is empty")
        gap_mm = max(float(row[2]) for row in requirements)
        if not math.isclose(gap_mm, EXPECTED_MAX_GAP_MM, abs_tol=1e-9):
            raise ValueError(
                "authoritative maximum creepage requirement drifted: "
                f"expected {EXPECTED_MAX_GAP_MM}mm, got {gap_mm}mm"
            )

        from temper_placer.placer.cp_sat.isolation_barrier import (
            classify_domain_partition,
            load_domain_manifest_nets,
        )

        hv_nets, selv_nets = load_domain_manifest_nets(manifest)
        partition_result = classify_domain_partition(inputs.netlist.components, hv_nets, selv_nets)
        partition = {
            "hv_only": tuple(sorted(partition_result.hv_only)),
            "selv_only": tuple(sorted(partition_result.selv_only)),
            "isolators": tuple(sorted(partition_result.isolators)),
            "unclassified": tuple(sorted(partition_result.unclassified)),
        }
        all_refs = tuple(sorted(str(component.ref) for component in inputs.netlist.components))
        flattened = [ref for refs in partition.values() for ref in refs]
        if len(flattened) != len(set(flattened)) or set(flattened) != set(all_refs):
            raise ValueError("authoritative domain partition does not exactly cover the netlist")

        normalized_requirements = tuple(
            sorted((str(row[0]), str(row[1]), float(row[2])) for row in requirements)
        )
        placeholder = dataclasses.replace(
            placeholder,
            requirement_sha256=_digest_json(normalized_requirements),
            requirement_count=len(normalized_requirements),
            requirements_by_gap_mm=tuple(
                sorted(Counter(row[2] for row in normalized_requirements).items())
            ),
            partition=_pairs(partition),
            gap_mm=gap_mm,
            tool_code_sha256=tuple(
                sorted(
                    (name, _sha256(path))
                    for name, path in {
                        "experiment": Path(__file__),
                        "corridor": Path(__file__).with_name("creepage_search_corridor.py"),
                        "solver": Path(__file__).with_name("_encoder_solve.py"),
                        "solver_telemetry": Path(__file__).with_name("solver_telemetry.py"),
                        "production_inputs": Path(__file__).with_name(
                            "production_constraint_family_inputs.py"
                        ),
                    }.items()
                )
            ),
        )

        declared_hv = tuple(sorted(str(ref) for ref in hv_only_refs))
        declared_selv = tuple(sorted(str(ref) for ref in selv_only_refs))
        if not declared_hv or not declared_selv:
            raise ValueError("designer HV-only and SELV-only declarations must both be nonempty")
        if len(declared_hv) != len(set(declared_hv)) or len(declared_selv) != len(
            set(declared_selv)
        ):
            raise ValueError("designer declarations must not contain duplicate refs")
        for name, declared in (("hv_only", declared_hv), ("selv_only", declared_selv)):
            if set(declared) != set(partition[name]):
                raise ValueError(
                    f"designer {name} declaration does not exactly match authoritative bucket: "
                    f"missing={sorted(set(partition[name]) - set(declared))}, "
                    f"unexpected={sorted(set(declared) - set(partition[name]))}"
                )

        families = getattr(inputs, "families", {})
        try:
            validator_input = families["validator_audit"]["validator_input"]
            body_input = families["body_collision_audit"]["body_collision_input"]
            tank_creepage = families["tank_creepage"]["tank_creepage"]
        except (KeyError, TypeError) as exc:
            raise SharedPreflightError(
                "gate", f"required acceptance artifact unavailable: {exc}", placeholder
            ) from exc
        if not isinstance(validator_input, Mapping):
            raise SharedPreflightError(
                "gate", "REQ-SAFE-01 validator input is malformed", placeholder
            )
        validator_placement = validator_input.get("placement")
        voltage_domains = validator_input.get("voltage_domains")
        if (
            not isinstance(validator_placement, Mapping)
            or not validator_placement.get("components")
            or not isinstance(voltage_domains, Mapping)
        ):
            raise SharedPreflightError(
                "gate", "REQ-SAFE-01 validator input is incomplete", placeholder
            )

        from temper_placer.placer.cp_sat.domain_clearance import (
            generate_domain_clearance_constraints,
        )

        try:
            domain_constraints = tuple(
                generate_domain_clearance_constraints(
                    dict(validator_placement), dict(voltage_domains), set(all_refs)
                )
            )
        except Exception as exc:
            raise SharedPreflightError(
                "gate",
                f"REQ-SAFE-01 constraint input is unusable: {type(exc).__name__}: {exc}",
                placeholder,
            ) from exc

        if not isinstance(body_input, Mapping):
            raise SharedPreflightError("gate", "F.Fab audit input is malformed", placeholder)
        fab_bodies = body_input.get("fab_bodies")
        allowlist = body_input.get("allowlist")
        if not isinstance(fab_bodies, Mapping) or not fab_bodies:
            raise SharedPreflightError(
                "gate", "input PCB has zero parsed F.Fab bodies", placeholder
            )
        if allowlist is None:
            raise SharedPreflightError("gate", "F.Fab allowlist is unavailable", placeholder)

        from temper_placer.placer.cp_sat.production_constraint_family_inputs import (
            _find_repo_file,
            make_production_constraint_family_verifier,
        )

        allowlist_path = _find_repo_file(
            "packages/temper-placer/configs/body_collision_allowlist.yaml", start=pcb
        )
        if allowlist_path is None:
            raise SharedPreflightError(
                "gate", "F.Fab allowlist source file is unavailable", placeholder
            )
        try:
            import temper_orchestration as orchestration

            if not callable(getattr(orchestration, "verify_stripped_creepage_py", None)):
                raise AttributeError("verify_stripped_creepage_py")
            verifier = make_production_constraint_family_verifier(inputs)
        except Exception as exc:
            raise SharedPreflightError(
                "gate",
                f"Rust exhaustive verifier unavailable: {type(exc).__name__}: {exc}",
                placeholder,
            ) from exc

        identity = build_experiment_identity(
            pcb_path=pcb,
            constraints_path=constraints,
            manifest_path=manifest,
            allowlist_path=allowlist_path,
            requirements=requirements,
            partition=partition,
            gap_mm=gap_mm,
            polarity=POLARITY,
            seed=seed,
            num_search_workers=num_search_workers,
            solve_limit_s=solve_limit,
            watchdog_grace_s=grace,
            warm_start_limit_s=warm_limit,
        )

        if warm_start_builder is None:
            from temper_placer.placer.cp_sat.stripped_warm_start import (
                solve_production_stripped_instance_warm_start,
            )

            warm_start_builder = solve_production_stripped_instance_warm_start
        warm = warm_start_builder(
            instance,
            timeout_s=warm_limit,
            num_search_workers=num_search_workers,
        )
        hints = getattr(warm, "hints", None)
        if getattr(warm, "usable", False) is not True or not isinstance(hints, Mapping):
            raise SharedPreflightError(
                "input",
                str(getattr(warm, "message", None) or "Rust-verified stripped hint unavailable"),
                identity,
            )
        if set(hints) != set(all_refs):
            raise SharedPreflightError(
                "input",
                "Rust-verified stripped hint does not cover the authoritative refs",
                identity,
            )

        solve_kwargs = dict(inputs.production_kwargs)
        solve_kwargs["experimental_omit_generated_creepage"] = False
        solve_kwargs["tank_creepage"] = tank_creepage
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
            hv_only_refs=declared_hv,
            selv_only_refs=declared_selv,
            verifier=verifier,
            domain_constraints=domain_constraints,
            validator_placement=validator_placement,
            voltage_domains=voltage_domains,
            fab_bodies=fab_bodies,
            body_allowlist=allowlist,
        )
    except SharedPreflightError:
        raise
    except Exception as exc:
        raise SharedPreflightError(
            "input", f"shared experiment input invalid: {type(exc).__name__}: {exc}", placeholder
        ) from exc


def _rust_gate(
    verifier: Callable[[object], object], candidate: object, count: int
) -> CandidateGateResult:
    try:
        result = verifier(candidate)
        violations = tuple(str(item) for item in getattr(result, "violations", ()))
        passed = getattr(result, "passed", not violations)
        if not isinstance(passed, bool):
            raise ValueError("verifier result has no boolean passed status")
        return CandidateGateResult(
            "rust-creepage",
            "passed" if passed and not violations else "failed",
            checked_count=count,
            violation_count=len(violations),
            diagnostics=violations,
        )
    except Exception as exc:
        return CandidateGateResult(
            "rust-creepage", "error", diagnostics=(f"{type(exc).__name__}: {exc}",)
        )


def _validator_gate(
    audit: Callable[..., object],
    prepared: PreparedCorridorExperiment,
    positions: dict[str, tuple[float, float]],
    rotations: dict[str, int],
) -> CandidateGateResult:
    try:
        result = audit(
            list(prepared.domain_constraints),
            positions,
            rotations,
            dict(prepared.validator_placement),
            dict(prepared.voltage_domains),
            prepared.netlist,
        )
        hard = tuple(getattr(result, "hard_failures", ()))
        coverage = tuple(getattr(result, "coverage_gaps", ()))
        intra = tuple(getattr(result, "intra_footprint", ()))
        trusted = getattr(result, "geometry_trusted", None)
        if not isinstance(trusted, bool):
            raise ValueError("validator audit has no geometry_trusted verdict")
        passed = trusted and not hard and not coverage
        diagnostics = []
        if not trusted:
            diagnostics.append("validator geometry is untrusted")
        if hard:
            diagnostics.append(f"{len(hard)} hard failure record(s)")
        if coverage:
            diagnostics.append(f"{len(coverage)} coverage gap record(s)")
        if intra:
            diagnostics.append(f"{len(intra)} placement-independent intra-footprint finding(s)")
        return CandidateGateResult(
            "req-safe-01",
            "passed" if passed else "failed",
            checked_count=int(getattr(result, "covered_pair_count", 0)),
            violation_count=len(hard) + len(coverage),
            diagnostics=tuple(diagnostics),
            details=(
                ("geometry_trusted", trusted),
                ("hard_failure_count", len(hard)),
                ("coverage_gap_count", len(coverage)),
                ("intra_footprint_count", len(intra)),
                ("validator_violation_count", int(getattr(result, "validator_violation_count", 0))),
                ("stats", getattr(result, "stats", {})),
            ),
        )
    except Exception as exc:
        return CandidateGateResult(
            "req-safe-01", "error", diagnostics=(f"{type(exc).__name__}: {exc}",)
        )


def _body_gate(
    audit: Callable[..., object],
    prepared: PreparedCorridorExperiment,
    positions: dict[str, tuple[float, float]],
    rotations: dict[str, int],
) -> CandidateGateResult:
    try:
        result = audit(dict(prepared.fab_bodies), positions, rotations, prepared.body_allowlist)
        violations = tuple(getattr(result, "violations", ()))
        missing = tuple(sorted(str(ref) for ref in getattr(result, "refs_without_geometry", ())))
        clean = getattr(result, "clean", None)
        if not isinstance(clean, bool):
            raise ValueError("F.Fab audit has no clean verdict")
        diagnostics = (f"refs without F.Fab geometry: {', '.join(missing)}",) if missing else ()
        return CandidateGateResult(
            "f-fab",
            "passed" if clean and not violations else "failed",
            checked_count=int(getattr(result, "checked_pairs", 0)),
            violation_count=len(violations),
            diagnostics=diagnostics,
            details=(
                ("allowlisted_count", len(tuple(getattr(result, "allowlisted", ())))),
                ("refs_without_geometry", missing),
            ),
        )
    except Exception as exc:
        return CandidateGateResult("f-fab", "error", diagnostics=(f"{type(exc).__name__}: {exc}",))


def execute_axis_probe(
    prepared: PreparedCorridorExperiment,
    axis: Literal["x", "y"],
    *,
    solver: Callable[..., object] | None = None,
    verifier: Callable[[object], object] | None = None,
    validator_audit: Callable[..., object] | None = None,
    body_audit: Callable[..., object] | None = None,
) -> AxisExperimentResult:
    """Build one fresh production model, then audit any complete candidate."""

    started = time.monotonic()
    if axis not in ("x", "y"):
        raise ValueError("axis must be x or y")
    if solver is None:
        from temper_placer.placer.cp_sat.encoder import solve_placement

        solver = solve_placement
    if validator_audit is None:
        from temper_placer.placer.cp_sat.validator_audit import audit_domain_clearance_validator

        validator_audit = audit_domain_clearance_validator
    if body_audit is None:
        from temper_placer.placer.cp_sat.body_collision import audit_body_collisions

        body_audit = audit_body_collisions
    verifier = verifier or prepared.verifier

    kwargs = dict(prepared.solve_kwargs)
    kwargs.update(
        {
            "timeout_ms": int(round(prepared.identity.solve_limit_s * 1000.0)),
            "hint_positions": dict(prepared.hint_positions),
            "capture_telemetry": True,
            "experimental_omit_generated_creepage": False,
            "creepage_search_corridor": {
                "manifest_path": prepared.manifest_path,
                "hv_only_refs": prepared.hv_only_refs,
                "selv_only_refs": prepared.selv_only_refs,
                "axis": axis,
                "gap_mm": prepared.identity.gap_mm,
            },
        }
    )
    # Acceptance is intentionally outside solve_placement so a rejection
    # cannot turn a feasible CP-SAT status into a worker exception.
    kwargs.pop("validator_input", None)
    kwargs.pop("body_collision_input", None)
    try:
        candidate = solver(prepared.netlist, prepared.board, **kwargs)
    except Exception as exc:
        return AxisExperimentResult(
            axis,
            "not-run",
            "error",
            "not-run",
            time.monotonic() - started,
            diagnostics=(f"solver raised {type(exc).__name__}: {exc}",),
        )

    raw_status = str(getattr(candidate, "status", "unknown")).strip().lower().replace("_", "-")
    solver_status: SolverStatus = (
        raw_status
        if raw_status in {"optimal", "feasible", "infeasible", "unknown", "model-invalid"}
        else "model-invalid"
    )  # type: ignore[assignment]
    if solver_status not in ("optimal", "feasible"):
        return AxisExperimentResult(
            axis,
            solver_status,
            "returned",
            "not-run",
            time.monotonic() - started,
            telemetry=_plain_pairs(getattr(candidate, "solver_telemetry", None)),
            corridor=_plain_pairs(getattr(candidate, "creepage_search_corridor_report", None)),
            diagnostics=(
                ()
                if raw_status == solver_status
                else (f"unrecognized solver status {raw_status!r}",)
            ),
        )

    positions_raw = getattr(candidate, "positions", None)
    rotations_raw = getattr(candidate, "rotations", None)
    if not isinstance(positions_raw, Mapping) or not isinstance(rotations_raw, Mapping):
        complete = False
        positions: dict[str, tuple[float, float]] = {}
        rotations: dict[str, int] = {}
    else:
        positions = {
            str(ref): (float(point[0]), float(point[1])) for ref, point in positions_raw.items()
        }
        rotations = {str(ref): int(value) for ref, value in rotations_raw.items()}
        complete = set(positions) == set(prepared.expected_refs) == set(rotations)
    if not complete:
        return AxisExperimentResult(
            axis,
            "model-invalid",
            "returned",
            "not-run",
            time.monotonic() - started,
            diagnostics=(
                "solver returned an incomplete candidate: "
                f"position_missing={sorted(set(prepared.expected_refs) - set(positions))}, "
                f"rotation_missing={sorted(set(prepared.expected_refs) - set(rotations))}",
            ),
        )

    gates = (
        _rust_gate(verifier, candidate, prepared.identity.requirement_count or 0),
        _validator_gate(validator_audit, prepared, positions, rotations),
        _body_gate(body_audit, prepared, positions, rotations),
    )
    if any(gate.status == "error" for gate in gates):
        acceptance: AcceptanceVerdict = "gate-error"
    elif all(gate.status == "passed" for gate in gates):
        acceptance = "accepted"
    else:
        acceptance = "rejected"
    return AxisExperimentResult(
        axis,
        solver_status,
        "returned",
        acceptance,
        time.monotonic() - started,
        candidate_complete=True,
        candidate_positions=tuple((ref, *positions[ref]) for ref in sorted(positions)),
        candidate_rotations=tuple((ref, rotations[ref]) for ref in sorted(rotations)),
        telemetry=_plain_pairs(getattr(candidate, "solver_telemetry", None)),
        corridor=_plain_pairs(getattr(candidate, "creepage_search_corridor_report", None)),
        gates=gates,
    )


def _axis_process_worker(
    output: Any, prepared: PreparedCorridorExperiment, axis: Literal["x", "y"]
) -> None:
    try:
        output.put(execute_axis_probe(prepared, axis))
    except BaseException as exc:
        output.put(
            AxisExperimentResult(
                axis,
                "not-run",
                "error",
                "not-run",
                0.0,
                diagnostics=(f"worker raised {type(exc).__name__}: {exc}",),
            )
        )


def run_axis_in_fresh_process(
    prepared: PreparedCorridorExperiment,
    axis: Literal["x", "y"],
    solve_limit_s: float,
    watchdog_grace_s: float,
) -> AxisExperimentResult:
    """Contain one axis behind an external watchdog and cleanup grace."""

    started = time.monotonic()
    context = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_axis_process_worker,
        args=(output, prepared, axis),
        name=f"temper-creepage-search-corridor-{axis}",
    )
    try:
        process.start()
    except BaseException as exc:
        return AxisExperimentResult(
            axis,
            "not-run",
            "error",
            "not-run",
            time.monotonic() - started,
            diagnostics=(f"could not start worker: {type(exc).__name__}: {exc}",),
        )

    # Consume the queue while the child is alive.  Waiting for process exit
    # first can deadlock when the telemetry payload exceeds the OS pipe
    # buffer: multiprocessing's feeder thread cannot flush until the parent
    # reads, while Process.join waits for that feeder thread to finish.
    deadline = started + float(solve_limit_s) + float(watchdog_grace_s)
    result: object | None = None
    while result is None and time.monotonic() < deadline:
        try:
            result = output.get(timeout=min(0.25, max(0.001, deadline - time.monotonic())))
        except queue_module.Empty:
            if not process.is_alive():
                with suppress(queue_module.Empty):
                    result = output.get(timeout=0.25)
                break

    if result is None and process.is_alive():
        process.terminate()
        process.join(float(watchdog_grace_s))
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(float(watchdog_grace_s))
        return AxisExperimentResult(
            axis,
            "not-run",
            "timeout",
            "not-run",
            time.monotonic() - started,
            diagnostics=(
                f"worker exceeded external watchdog of {solve_limit_s + watchdog_grace_s:.3f}s; "
                f"the internal CP-SAT limit remained {solve_limit_s:.3f}s",
            ),
        )
    if result is None:
        process.join(float(watchdog_grace_s))
        return AxisExperimentResult(
            axis,
            "not-run",
            "error",
            "not-run",
            time.monotonic() - started,
            diagnostics=(f"worker exited without a payload (exitcode={process.exitcode})",),
        )
    process.join(float(watchdog_grace_s))
    if process.is_alive():
        process.terminate()
        process.join(float(watchdog_grace_s))
    if not isinstance(result, AxisExperimentResult) or result.axis != axis:
        return AxisExperimentResult(
            axis,
            "model-invalid",
            "error",
            "not-run",
            time.monotonic() - started,
            diagnostics=("worker returned a malformed or wrong-axis payload",),
        )
    return dataclasses.replace(result, elapsed_s=time.monotonic() - started)


def run_prepared_corridor_experiment(
    prepared: PreparedCorridorExperiment,
    *,
    axis_runner: Callable[
        [PreparedCorridorExperiment, Literal["x", "y"], float, float], AxisExperimentResult
    ] = run_axis_in_fresh_process,
) -> CreepageSearchCorridorExperimentRecord:
    """Run x then y without allowing an axis-local failure to short-circuit."""

    results: list[AxisExperimentResult] = []
    for axis in ("x", "y"):
        try:
            result = axis_runner(
                prepared,
                axis,
                prepared.identity.solve_limit_s,
                prepared.identity.watchdog_grace_s,
            )
            if not isinstance(result, AxisExperimentResult) or result.axis != axis:
                raise ValueError("axis runner returned a malformed or wrong-axis result")
        except Exception as exc:
            result = AxisExperimentResult(
                axis,
                "not-run",
                "error",
                "not-run",
                0.0,
                diagnostics=(f"axis runner raised {type(exc).__name__}: {exc}",),
            )
        results.append(result)
    return CreepageSearchCorridorExperimentRecord(prepared.identity, (results[0], results[1]))


def _shared_failure_record(exc: SharedPreflightError) -> CreepageSearchCorridorExperimentRecord:
    solver: SolverStatus = "model-invalid" if exc.category == "input" else "not-run"
    acceptance: AcceptanceVerdict = "not-run" if exc.category == "input" else "gate-error"
    axes = tuple(
        AxisExperimentResult(
            axis,
            solver,
            "not-started",
            acceptance,
            0.0,
            diagnostics=(str(exc),),
        )
        for axis in ("x", "y")
    )
    return CreepageSearchCorridorExperimentRecord(exc.identity, axes)  # type: ignore[arg-type]


def run_with_shared_preflight(
    prepare: Callable[[], PreparedCorridorExperiment],
    *,
    axis_runner: Callable[
        [PreparedCorridorExperiment, Literal["x", "y"], float, float], AxisExperimentResult
    ] = run_axis_in_fresh_process,
) -> CreepageSearchCorridorExperimentRecord:
    try:
        prepared = prepare()
    except SharedPreflightError as exc:
        return _shared_failure_record(exc)
    return run_prepared_corridor_experiment(prepared, axis_runner=axis_runner)


def run_creepage_search_corridor_experiment(
    pcb_path: str | Path,
    constraints_path: str | Path,
    manifest_path: str | Path,
    *,
    hv_only_refs: Sequence[str],
    selv_only_refs: Sequence[str],
    seed: int = 0,
    solve_limit_s: float = 120.0,
    watchdog_grace_s: float = 5.0,
    warm_start_limit_s: float = 30.0,
) -> CreepageSearchCorridorExperimentRecord:
    return run_with_shared_preflight(
        lambda: prepare_corridor_experiment(
            pcb_path,
            constraints_path,
            manifest_path,
            hv_only_refs=hv_only_refs,
            selv_only_refs=selv_only_refs,
            seed=seed,
            solve_limit_s=solve_limit_s,
            watchdog_grace_s=watchdog_grace_s,
            warm_start_limit_s=warm_start_limit_s,
        )
    )


def canonical_experiment_json(record: CreepageSearchCorridorExperimentRecord) -> str:
    if record.schema != EXPERIMENT_SCHEMA or record.version != EXPERIMENT_VERSION:
        raise ValueError("unsupported creepage-search-corridor experiment schema or version")
    if tuple(axis.axis for axis in record.axes) != ("x", "y"):
        raise ValueError("experiment record must contain x then y exactly once")
    return canonical_json(record.to_dict())


def _record_from_payload(
    payload: Mapping[str, object],
) -> CreepageSearchCorridorExperimentRecord:
    """Rebuild typed evidence and reject schema or axis-order drift."""

    if payload.get("schema") != EXPERIMENT_SCHEMA or payload.get("version") != EXPERIMENT_VERSION:
        raise ValueError("unsupported creepage-search-corridor schema or version")
    identity_raw = payload.get("identity")
    axes_raw = payload.get("axes")
    if not isinstance(identity_raw, Mapping):
        raise ValueError("experiment identity must be an object")
    if (
        isinstance(axes_raw, (str, bytes))
        or not isinstance(axes_raw, Sequence)
        or len(axes_raw) != 2
    ):
        raise ValueError("experiment axes must contain exactly x and y")

    def rows(name: str) -> Sequence[Sequence[object]]:
        value = identity_raw.get(name, ())
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError(f"identity.{name} must be a sequence")
        return value  # type: ignore[return-value]

    identity = ExperimentIdentity(
        input_sha256=tuple((str(row[0]), str(row[1])) for row in rows("input_sha256")),
        requirement_sha256=(
            None
            if identity_raw.get("requirement_sha256") is None
            else str(identity_raw["requirement_sha256"])
        ),
        requirement_count=(
            None
            if identity_raw.get("requirement_count") is None
            else int(identity_raw["requirement_count"])
        ),
        requirements_by_gap_mm=tuple(
            (float(row[0]), int(row[1])) for row in rows("requirements_by_gap_mm")
        ),
        partition=tuple(
            (str(row[0]), tuple(str(ref) for ref in row[1])) for row in rows("partition")
        ),
        gap_mm=(None if identity_raw.get("gap_mm") is None else float(identity_raw["gap_mm"])),
        polarity=str(identity_raw.get("polarity")),
        seed=int(identity_raw.get("seed", 0)),
        num_search_workers=int(identity_raw.get("num_search_workers", 0)),
        solve_limit_s=float(identity_raw.get("solve_limit_s", 0.0)),
        watchdog_grace_s=float(identity_raw.get("watchdog_grace_s", 0.0)),
        warm_start_limit_s=float(identity_raw.get("warm_start_limit_s", 0.0)),
        tool_code_sha256=tuple((str(row[0]), str(row[1])) for row in rows("tool_code_sha256")),
    )

    def pairs(raw: Mapping[str, object], name: str) -> tuple[tuple[str, object], ...]:
        value = raw.get(name, ())
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ValueError(f"axis.{name} must be a sequence")
        return tuple((str(row[0]), row[1]) for row in value)  # type: ignore[index]

    def gate(raw: object) -> CandidateGateResult:
        if not isinstance(raw, Mapping):
            raise ValueError("candidate gate must be an object")
        return CandidateGateResult(
            name=str(raw.get("name")),
            status=str(raw.get("status")),  # type: ignore[arg-type]
            checked_count=raw.get("checked_count"),  # type: ignore[arg-type]
            violation_count=raw.get("violation_count"),  # type: ignore[arg-type]
            diagnostics=tuple(str(item) for item in raw.get("diagnostics", ())),  # type: ignore[union-attr]
            details=pairs(raw, "details"),
        )

    def axis(raw: object) -> AxisExperimentResult:
        if not isinstance(raw, Mapping):
            raise ValueError("axis record must be an object")
        position_rows = raw.get("candidate_positions", ())
        rotation_rows = raw.get("candidate_rotations", ())
        gate_rows = raw.get("gates", ())
        return AxisExperimentResult(
            axis=str(raw.get("axis")),  # type: ignore[arg-type]
            solver_status=str(raw.get("solver_status")),  # type: ignore[arg-type]
            execution_outcome=str(raw.get("execution_outcome")),  # type: ignore[arg-type]
            acceptance_verdict=str(raw.get("acceptance_verdict")),  # type: ignore[arg-type]
            elapsed_s=float(raw.get("elapsed_s", 0.0)),
            candidate_complete=bool(raw.get("candidate_complete", False)),
            candidate_positions=tuple(
                (str(row[0]), float(row[1]), float(row[2]))
                for row in position_rows  # type: ignore[union-attr]
            ),
            candidate_rotations=tuple(
                (str(row[0]), int(row[1]))
                for row in rotation_rows  # type: ignore[union-attr]
            ),
            telemetry=pairs(raw, "telemetry"),
            corridor=pairs(raw, "corridor"),
            gates=tuple(gate(item) for item in gate_rows),  # type: ignore[union-attr]
            diagnostics=tuple(str(item) for item in raw.get("diagnostics", ())),  # type: ignore[union-attr]
        )

    record = CreepageSearchCorridorExperimentRecord(
        identity=identity,
        axes=(axis(axes_raw[0]), axis(axes_raw[1])),
    )
    canonical_experiment_json(record)
    return record


def write_experiment_record(
    record: CreepageSearchCorridorExperimentRecord, path: str | Path
) -> None:
    """Write canonical JSON atomically without exposing a partial artifact."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(canonical_experiment_json(record) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise


def read_experiment_record(path: str | Path) -> CreepageSearchCorridorExperimentRecord:
    return CreepageSearchCorridorExperimentRecord.read(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcb", type=Path, required=True)
    parser.add_argument("--constraints", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hv-ref", action="append", required=True, dest="hv_refs")
    parser.add_argument("--selv-ref", action="append", required=True, dest="selv_refs")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--solve-limit-s", type=float, default=120.0)
    parser.add_argument("--watchdog-grace-s", type=float, default=5.0)
    parser.add_argument("--warm-start-limit-s", type=float, default=30.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    record = run_creepage_search_corridor_experiment(
        args.pcb,
        args.constraints,
        args.manifest,
        hv_only_refs=args.hv_refs,
        selv_only_refs=args.selv_refs,
        seed=args.seed,
        solve_limit_s=args.solve_limit_s,
        watchdog_grace_s=args.watchdog_grace_s,
        warm_start_limit_s=args.warm_start_limit_s,
    )
    write_experiment_record(record, args.output)
    print(
        f"wrote {args.output}: success={record.success}; "
        + ", ".join(
            f"{axis.axis}={axis.solver_status}/{axis.execution_outcome}/{axis.acceptance_verdict}"
            for axis in record.axes
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AxisExperimentResult",
    "CandidateGateResult",
    "CreepageSearchCorridorExperimentRecord",
    "ExperimentIdentity",
    "PreparedCorridorExperiment",
    "SharedPreflightError",
    "build_experiment_identity",
    "canonical_experiment_json",
    "execute_axis_probe",
    "prepare_corridor_experiment",
    "read_experiment_record",
    "run_axis_in_fresh_process",
    "run_creepage_search_corridor_experiment",
    "run_prepared_corridor_experiment",
    "run_with_shared_preflight",
    "write_experiment_record",
]
