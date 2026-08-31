#!/usr/bin/env python3
"""Validate the approved split power/control-board contract.

This gate is intentionally separate from the legacy one-board gates.  It
validates the *inputs required before* a split-board generator may create
artifacts; it does not invent PCB files or treat the existing legacy board as
either new board.

The initial committed contract is ``contract-incomplete`` and therefore
returns ``EXIT_VIOLATION``.  That is deliberate: a future split-board
generator must call :func:`assert_generation_ready` before writing either
PCB.  The connector and enclosure reviews, both board artifacts, their DRC
reports, provenance records, and the PD3/12.6 mm cross-domain report are all
required before generation can be enabled.

Exit codes:

* 0 -- a complete contract and all referenced evidence passed;
* 2 -- the contract is well-formed but incomplete or blocked by prerequisites;
* 1 -- the gate could not parse or otherwise trust its input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from _lib.measurement_provenance import sha256_file
from _lib.repo import find_repo_root
from check_evidence_provenance import verify_commits_exist

try:
    from check_domain_partition import (  # type: ignore[import-not-found]
        GateError as DomainGateError,
    )
    from check_domain_partition import (
        check_board_interface_generation_ready,
        load_manifest,
    )
except ImportError:  # pragma: no cover - only needed when imported externally
    DomainGateError = Exception
    check_board_interface_generation_ready = None
    load_manifest = None

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_MALFORMED = 1
# Compatibility name for callers that used the initial implementation.
EXIT_VIOLATION = EXIT_BLOCKED
EXIT_GATE_ERROR = EXIT_MALFORMED

SCHEMA_VERSION = 1
ARCHITECTURE = "split_power_control"
REQUIRED_CREEPAGE_MM = 12.6
POLLUTION_DEGREE = 3
REQUIRED_BOARDS = ("power", "control")
REQUIRED_BLOCKERS = ("connector", "enclosure")
REQUIRED_INTERFACE_DOMAIN = "SELV"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ATOPILE_INTERFACE_SIGNAL = {
    "gnd": "gnd",
    "+15V": "vcc_15v",
    "+3V3": "vcc_3v3",
    "PWM_HS": "pwm_hs",
    "PWM_LS": "pwm_ls",
    "SHUTDOWN": "shutdown",
    "RELAY_CTRL": "relay_ctrl",
    "DISCHARGE_CTRL": "discharge_ctrl",
    "V_BUS_SENSE": "v_bus_sense",
    "I_SENSE": "i_sense",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "split_board_manifest.yaml"


class GateError(Exception):
    """The gate could not establish a trustworthy contract."""


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{context} must be a mapping")
    return value


def _text(value: Any, context: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"{context} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, context: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        qualifier = "non-empty " if nonempty else ""
        raise GateError(f"{context} must be a {qualifier}list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise GateError(f"{context} must contain non-empty strings")
    result = [item.strip() for item in value]
    if len(set(result)) != len(result):
        raise GateError(f"{context} must not contain duplicates")
    return result


def load_contract(path: Path) -> dict[str, Any]:
    """Load and structurally validate a split-board manifest."""

    if not path.is_file():
        raise GateError(f"split-board contract not found: {path}")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise GateError(f"split-board contract is empty: {path}")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise GateError(f"split-board contract is not valid YAML: {exc}") from exc
    data = _mapping(data, "split-board contract")

    if data.get("schema_version") != SCHEMA_VERSION:
        raise GateError(
            f"schema_version must be exactly {SCHEMA_VERSION}, got {data.get('schema_version')!r}"
        )
    if data.get("architecture") != ARCHITECTURE:
        raise GateError(f"architecture must be {ARCHITECTURE!r}")
    status = _text(data.get("status"), "status")
    if status not in {"contract-incomplete", "ready"}:
        raise GateError("status must be 'contract-incomplete' or 'ready'")

    generation = _mapping(data.get("generation"), "generation")
    if not isinstance(generation.get("enabled"), bool):
        raise GateError("generation.enabled must be a boolean")
    blockers = _string_list(
        generation.get("blocking_requirements"),
        "generation.blocking_requirements",
    )
    if set(blockers) != set(REQUIRED_BLOCKERS):
        raise GateError(
            "generation.blocking_requirements must name connector and enclosure exactly"
        )

    boards = _mapping(data.get("boards"), "boards")
    if set(boards) != set(REQUIRED_BOARDS):
        raise GateError("boards must contain exactly power and control entries")
    for board_role in REQUIRED_BOARDS:
        board = _mapping(boards[board_role], f"boards.{board_role}")
        board_id = _text(board.get("id"), f"boards.{board_role}.id")
        owner = _text(board.get("owner"), f"boards.{board_role}.owner")
        expected_id = "POWER_BOARD" if board_role == "power" else "CONTROL_BOARD"
        if board_id != expected_id:
            raise GateError(f"boards.{board_role}.id must be {expected_id}")
        if owner != board_role:
            raise GateError(f"boards.{board_role}.owner must be {board_role!r}")
        domains = _string_list(
            board.get("required_domains"), f"boards.{board_role}.required_domains"
        )
        if board_role == "control" and domains != [REQUIRED_INTERFACE_DOMAIN]:
            raise GateError("boards.control.required_domains must be exactly [SELV]")
        if board_role == "power" and "HV" not in domains:
            raise GateError("boards.power.required_domains must include HV")

        artifacts = _mapping(board.get("artifacts"), f"boards.{board_role}.artifacts")
        for artifact_name in ("pcb", "netlist"):
            _text(
                artifacts.get(artifact_name),
                f"boards.{board_role}.artifacts.{artifact_name}",
                allow_none=True,
            )
        source = _mapping(board.get("source"), f"boards.{board_role}.source")
        _text(source.get("entrypoint"), f"boards.{board_role}.source.entrypoint", allow_none=True)

        checks = _mapping(board.get("checks"), f"boards.{board_role}.checks")
        for check_name, record_name in (("drc", "report"), ("provenance", "record")):
            check = _mapping(checks.get(check_name), f"boards.{board_role}.checks.{check_name}")
            if check.get("required") is not True:
                raise GateError(
                    f"boards.{board_role}.checks.{check_name}.required must be true"
                )
            _text(
                check.get(record_name),
                f"boards.{board_role}.checks.{check_name}.{record_name}",
                allow_none=True,
            )

    interface = _mapping(data.get("interface"), "interface")
    _text(interface.get("name"), "interface.name")
    _text(interface.get("domain_manifest"), "interface.domain_manifest")
    _text(interface.get("connector_ref"), "interface.connector_ref")
    allowed_domains = _string_list(interface.get("allowed_domains"), "interface.allowed_domains")
    if allowed_domains != [REQUIRED_INTERFACE_DOMAIN]:
        raise GateError("interface.allowed_domains must be exactly [SELV]")
    nets = _string_list(interface.get("nets"), "interface.nets")
    if len(nets) != 10 or nets[-1] != "I_SENSE":
        raise GateError("interface.nets must contain the reconciled ten-net contract ending in I_SENSE")

    contract = _mapping(data.get("contract"), "contract")
    for review_name in REQUIRED_BLOCKERS:
        review = _mapping(contract.get(review_name), f"contract.{review_name}")
        review_status = _text(review.get("status"), f"contract.{review_name}.status")
        if review_status not in {"incomplete", "complete"}:
            raise GateError(
                f"contract.{review_name}.status must be 'incomplete' or 'complete'"
            )
        _text(review.get("evidence"), f"contract.{review_name}.evidence", allow_none=True)

    cross_domain = _mapping(data.get("cross_domain"), "cross_domain")
    if cross_domain.get("pollution_degree") != POLLUTION_DEGREE:
        raise GateError("cross_domain.pollution_degree must be 3")
    if cross_domain.get("reinforced_creepage_mm") != REQUIRED_CREEPAGE_MM:
        raise GateError("cross_domain.reinforced_creepage_mm must be exactly 12.6 mm")
    _text(cross_domain.get("method"), "cross_domain.method")
    _text(cross_domain.get("report"), "cross_domain.report", allow_none=True)

    return data


def _contract_repo_root(manifest_path: Path) -> Path:
    """Find the repository that owns a contract, with a fixture fallback.

    Production manifests live in a git worktree, so provenance lookups must
    use that worktree rather than the checkout containing this validator. A
    temporary directory used by unit tests is not a repository; its manifest
    directory is the containment root for those synthetic fixtures.
    """
    try:
        return find_repo_root(manifest_path.parent)
    except FileNotFoundError:
        return manifest_path.parent.resolve()


def _contract_git_root(manifest_path: Path) -> Path:
    """Find the git repository used for provenance verification.

    Synthetic contract fixtures have no git object database, so they use the
    validator checkout for their deliberately real commit fixture. Production
    contracts always resolve relative to their own worktree.
    """
    try:
        return find_repo_root(manifest_path.parent)
    except FileNotFoundError:
        return REPO_ROOT


def _resolve(path: str, manifest_path: Path) -> Path:
    """Resolve a contract path while keeping it inside its owning repo.

    Contract paths are intentionally relative to the manifest, but may use
    ``..`` to reach another repo-relative directory (the production method is
    ``../scripts/...``). ``Path.resolve`` makes the containment check include
    symlink targets, closing both lexical and symlink-based escapes.
    """
    if not isinstance(path, str) or not path.strip():
        raise GateError("contract paths must be non-empty strings")
    candidate = Path(path)
    if candidate.is_absolute():
        raise GateError(f"contract path must be repo-relative, got absolute path: {path}")
    resolved = (manifest_path.parent / candidate).resolve()
    repo_root = _contract_repo_root(manifest_path).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise GateError(
            f"contract path escapes its repository: {path!r} -> {resolved}"
        ) from exc
    return resolved


def _load_json(path: Path, context: str) -> dict[str, Any]:
    if not path.is_file():
        raise GateError(f"{context} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"{context} is not valid JSON: {path}: {exc}") from exc
    return _mapping(value, context)


def _require_versioned_evidence(path: Path, context: str) -> dict[str, Any]:
    """Load an approved, content-addressed engineering evidence record.

    A path existing on disk is not evidence: it must identify its source,
    approval, schema, and the bytes that were reviewed.  Keeping this small
    record contract here also means a future generator cannot accidentally
    accept a placeholder markdown file as a physical design decision.
    """
    record = _load_json(path, context)
    if record.get("schema_version") != 1:
        raise GateError(f"{context} schema_version must be 1")
    if record.get("approved") is not True:
        raise GateError(f"{context} must have approved=true")
    source = record.get("source_identity")
    if not isinstance(source, str) or not source.strip():
        raise GateError(f"{context} must record source_identity")
    values = record.get("engineering_values")
    if not isinstance(values, dict) or not values:
        raise GateError(f"{context} must record non-empty engineering_values")
    digest = record.get("content_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise GateError(f"{context} must record a full content_sha256")
    unsigned = dict(record)
    unsigned.pop("content_sha256", None)
    actual = sha256_file_from_json(unsigned)
    if digest != actual:
        raise GateError(f"{context} content_sha256 does not match the evidence record")
    return record


def sha256_file_from_json(value: dict[str, Any]) -> str:
    """Hash the canonical JSON representation used by evidence records."""
    import hashlib

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _check_source_interface(data: dict[str, Any], manifest_path: Path, errors: list[str]) -> None:
    interface = data["interface"]
    source_path = _resolve(interface["domain_manifest"], manifest_path)
    if not source_path.is_file():
        raise GateError(f"interface domain manifest not found: {source_path}")
    if load_manifest is None or check_board_interface_generation_ready is None:
        raise GateError("cannot import the domain-interface validator")
    try:
        source_manifest = load_manifest(source_path)
    except Exception as exc:
        raise GateError(f"interface domain manifest is malformed: {exc}") from exc
    declared = source_manifest.board_interface
    if declared is None:
        raise GateError("interface domain manifest has no board_interface mapping")
    expected = {
        "name": interface["name"],
        "power_board": "POWER_BOARD",
        "control_board": "CONTROL_BOARD",
        "connector": interface["connector_ref"],
        "nets": tuple(interface["nets"]),
        "allowed_domains": tuple(interface["allowed_domains"]),
    }
    actual = {
        "name": declared.name,
        "power_board": declared.power_board,
        "control_board": declared.control_board,
        "connector": declared.connector,
        "nets": declared.nets,
        "allowed_domains": declared.allowed_domains,
    }
    for field, wanted in expected.items():
        if actual[field] != wanted:
            raise GateError(
                f"interface {field} does not match elec/domain_manifest.yaml: "
                f"expected {wanted!r}, got {actual[field]!r}"
            )
    hierarchy_path = _contract_repo_root(manifest_path) / "elec" / "src" / "split_board_hierarchy.ato"
    if hierarchy_path.is_file():
        hierarchy = hierarchy_path.read_text(encoding="utf-8")
        match = re.search(
            r"(?ms)^interface\s+PowerControlSELV:\s*\n(?P<body>.*?)(?=^\S|\Z)",
            hierarchy,
        )
        if match is None:
            raise GateError(
                "split_board_hierarchy.ato has no PowerControlSELV interface"
            )
        actual_signals = tuple(
            re.findall(r"^\s+signal\s+([A-Za-z_]\w*)\s*$", match.group("body"), re.MULTILINE)
        )
        try:
            expected_signals = tuple(ATOPILE_INTERFACE_SIGNAL[net] for net in declared.nets)
        except KeyError as exc:
            raise GateError(
                "domain_manifest.yaml board_interface.nets contains an "
                f"unsupported net for the Atopile boundary: {exc.args[0]!r}"
            ) from exc
        if actual_signals != expected_signals:
            raise GateError(
                "split_board_hierarchy.ato PowerControlSELV signals do not "
                "match domain_manifest.yaml board_interface.nets: "
                f"expected {expected_signals!r}, got {actual_signals!r}"
            )
    # U3 consumes the typed readiness verdict from U1.  An unresolved
    # interface is a valid, machine-readable blocker, not malformed input.
    try:
        check_board_interface_generation_ready(source_manifest)
    except DomainGateError as exc:
        errors.append(f"domain interface readiness blocked: {exc}")


def _check_review_evidence(
    data: dict[str, Any], manifest_path: Path, errors: list[str]
) -> None:
    contract = data["contract"]
    for review_name in REQUIRED_BLOCKERS:
        review = contract[review_name]
        if review["status"] == "complete":
            evidence = review.get("evidence")
            if not evidence:
                errors.append(f"{review_name} contract is complete but has no evidence")
            else:
                evidence_path = _resolve(evidence, manifest_path)
                try:
                    _require_versioned_evidence(
                        evidence_path, f"{review_name} contract evidence"
                    )
                except GateError as exc:
                    raise GateError(str(exc)) from exc
        elif review.get("evidence") is not None:
            errors.append(f"{review_name} contract must keep evidence null while incomplete")


def _check_drc_report(path: Path, board_id: str) -> None:
    report = _load_json(path, f"{board_id} DRC report")
    if report.get("schema_version") != 1:
        raise GateError(f"{board_id} DRC report schema_version must be 1")
    if report.get("approved") is not True:
        raise GateError(f"{board_id} DRC report must have approved=true")
    if not isinstance(report.get("source_identity"), str) or not report["source_identity"].strip():
        raise GateError(f"{board_id} DRC report must record source_identity")
    if report.get("pollution_degree") != POLLUTION_DEGREE:
        raise GateError(f"{board_id} DRC report must use pollution degree 3")
    if report.get("required_creepage_mm") != REQUIRED_CREEPAGE_MM:
        raise GateError(f"{board_id} DRC report must require 12.6 mm creepage")
    values = report.get("engineering_values")
    if not isinstance(values, dict) or not values:
        raise GateError(f"{board_id} DRC report must record engineering_values")
    if not isinstance(report.get("sample_count"), int) or report["sample_count"] < 1:
        raise GateError(f"{board_id} DRC report must record a positive sample_count")
    nondeterministic = report.get("nondeterministic_error_types", [])
    if not isinstance(nondeterministic, list) or any(
        not isinstance(item, str) or not item.strip() for item in nondeterministic
    ):
        raise GateError(f"{board_id} DRC report nondeterministic_error_types must be a list")
    if nondeterministic and report["sample_count"] < 120:
        raise GateError(
            f"{board_id} DRC report needs at least 120 samples when "
            "nondeterministic error types are declared"
        )
    for field in ("violations_by_type", "warnings_by_type"):
        if not isinstance(report.get(field), dict):
            raise GateError(f"{board_id} DRC report must contain {field}")


def _check_provenance(
    path: Path,
    board_path: Path,
    board_id: str,
    manifest_path: Path,
) -> None:
    record = _load_json(path, f"{board_id} provenance record")
    if record.get("source") != "measured-live":
        raise GateError(f"{board_id} provenance source must be 'measured-live'")
    if record.get("dirty") is not False:
        raise GateError(f"{board_id} provenance dirty must be false")
    measured_at_commit = record.get("measured_at_commit")
    if not isinstance(measured_at_commit, str) or not COMMIT_RE.fullmatch(measured_at_commit):
        raise GateError(f"{board_id} provenance must record a full measured_at_commit SHA")
    repo_root = _contract_git_root(manifest_path)
    try:
        resolved_commits = verify_commits_exist({measured_at_commit}, repo_root)
    except RuntimeError as exc:
        raise GateError(f"{board_id} provenance commit verification failed: {exc}") from exc
    if not resolved_commits.get(measured_at_commit, False):
        raise GateError(f"{board_id} provenance measured_at_commit does not resolve")
    tool_versions = record.get("tool_versions")
    if not isinstance(tool_versions, dict) or not isinstance(tool_versions.get("kicad-cli"), str) or not tool_versions["kicad-cli"].strip():
        raise GateError(f"{board_id} provenance must record tool_versions.kicad-cli")
    inputs = record.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise GateError(f"{board_id} provenance must contain an inputs list")
    matching = False
    try:
        actual_hash = sha256_file(board_path) if board_path.is_file() else None
    except OSError as exc:
        raise GateError(f"{board_id} provenance PCB cannot be hashed: {exc}") from exc
    for item in inputs:
        if not isinstance(item, dict):
            continue
        item_path = item.get("path")
        item_hash = item.get("sha256")
        if isinstance(item_path, str) and _resolve(item_path, manifest_path) == board_path.resolve():
            matching = True
            if not isinstance(item_hash, str) or not SHA256_RE.fullmatch(item_hash):
                raise GateError(f"{board_id} provenance board input must contain a full sha256")
            elif actual_hash is not None and item_hash != actual_hash:
                raise GateError(f"{board_id} provenance board input sha256 does not match the PCB")
    if not matching:
        raise GateError(f"{board_id} provenance inputs must identify its PCB artifact")


def _check_cross_domain_report(path: Path) -> None:
    report = _require_versioned_evidence(path, "cross-domain report")
    if report.get("pollution_degree") != POLLUTION_DEGREE:
        raise GateError("cross-domain report must use pollution degree 3")
    if report.get("required_creepage_mm") != REQUIRED_CREEPAGE_MM:
        raise GateError("cross-domain report must require 12.6 mm creepage")
    measured = report.get("minimum_creepage_mm")
    if not isinstance(measured, (int, float)) or measured < REQUIRED_CREEPAGE_MM:
        raise GateError("cross-domain report minimum_creepage_mm is below 12.6 mm")
    if report.get("boards") != ["POWER_BOARD", "CONTROL_BOARD"]:
        raise GateError("cross-domain report must cover POWER_BOARD and CONTROL_BOARD")
    if report.get("violations") != []:
        raise GateError("cross-domain report must contain an empty violations list")


def validate_contract(path: Path = DEFAULT_MANIFEST) -> list[str]:
    """Return substantive contract errors; raise for untrustworthy input."""

    data = load_contract(path)
    errors: list[str] = []
    generation = data["generation"]
    status = data["status"]
    review_statuses = {name: data["contract"][name]["status"] for name in REQUIRED_BLOCKERS}

    _check_source_interface(data, path, errors)
    _check_review_evidence(data, path, errors)
    method_path = _resolve(data["cross_domain"]["method"], path)
    if not method_path.is_file():
        raise GateError(f"cross-domain method not found: {data['cross_domain']['method']}")

    if any(status == "incomplete" for status in review_statuses.values()):
        errors.extend(
            f"{name} contract is not complete" for name, value in review_statuses.items() if value != "complete"
        )
    if not generation["enabled"]:
        errors.append("generation is disabled until connector and enclosure reviews are complete")
    if status == "ready" and not generation["enabled"]:
        errors.append("status ready requires generation.enabled=true")
    if status == "contract-incomplete" and generation["enabled"]:
        errors.append("status contract-incomplete cannot enable generation")

    if generation["enabled"]:
        for board_role in REQUIRED_BOARDS:
            board = data["boards"][board_role]
            board_id = board["id"]
            artifacts = board["artifacts"]
            pcb_value = artifacts["pcb"]
            netlist_value = artifacts["netlist"]
            if not pcb_value:
                errors.append(f"{board_role} board PCB artifact is not declared")
                continue
            pcb_path = _resolve(pcb_value, path)
            if not pcb_path.is_file():
                errors.append(f"{board_role} board PCB artifact not found: {pcb_value}")
            if not netlist_value:
                errors.append(f"{board_role} board netlist artifact is not declared")
            elif not _resolve(netlist_value, path).is_file():
                errors.append(f"{board_role} board netlist artifact not found: {netlist_value}")
            source_entrypoint = board["source"]["entrypoint"]
            if not source_entrypoint:
                errors.append(f"{board_role} board source entrypoint is not declared")
            elif not _resolve(source_entrypoint, path).is_file():
                errors.append(
                    f"{board_role} board source entrypoint not found: {source_entrypoint}"
                )
            drc_report = board["checks"]["drc"]["report"]
            if not drc_report:
                errors.append(f"{board_role} board DRC report is not declared")
            else:
                _check_drc_report(_resolve(drc_report, path), board_id)
            provenance = board["checks"]["provenance"]["record"]
            if not provenance:
                errors.append(f"{board_role} board provenance record is not declared")
            elif pcb_path.is_file():
                _check_provenance(
                    _resolve(provenance, path), pcb_path, board_id, path
                )

        report = data["cross_domain"]["report"]
        if not report:
            errors.append("cross-domain report is not declared")
        else:
            _check_cross_domain_report(_resolve(report, path))
    else:
        for board_role in REQUIRED_BOARDS:
            artifacts = data["boards"][board_role]["artifacts"]
            for artifact_name in ("pcb", "netlist"):
                if artifacts[artifact_name] is not None:
                    errors.append(
                        f"boards.{board_role}.artifacts.{artifact_name} must remain null while generation is disabled"
                    )

    return errors


def assert_generation_ready(path: Path = DEFAULT_MANIFEST) -> None:
    """Raise :class:`GateError` unless split-board generation is authorized."""

    errors = validate_contract(path)
    if errors:
        raise GateError("split-board generation is not ready:\n- " + "\n- ".join(errors))


def generate_with_contract(
    path: Path, writer: Callable[[], Any]
) -> Any:
    """Run a future artifact writer only after the readiness gate passes.

    This is the integration seam for every split-board generator.  The
    callback is deliberately invoked *after* ``assert_generation_ready``;
    tests can therefore prove a blocked contract performs zero writes.
    """
    assert_generation_ready(path)
    return writer()


def run(path: Path = DEFAULT_MANIFEST) -> int:
    try:
        errors = validate_contract(path)
    except GateError as exc:
        print(f"SPLIT-BOARD CONTRACT GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR
    if errors:
        print("SPLIT-BOARD CONTRACT BLOCKED:")
        for error in errors:
            print(f"- {error}")
        print(
            "SPLIT_BOARD_CONTRACT_PAYLOAD="
            + json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "blocked",
                    "missing_prerequisites": errors,
                },
                sort_keys=True,
            )
        )
        return EXIT_BLOCKED
    print("SPLIT-BOARD CONTRACT PASSED: generation and safety evidence are complete")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    return run(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
