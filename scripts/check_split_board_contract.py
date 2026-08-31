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
* 3 -- the contract is valid but is incomplete or has a substantive
  violation;
* 5 -- the gate could not parse or otherwise trust its input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

SCHEMA_VERSION = 1
ARCHITECTURE = "split_power_control"
REQUIRED_CREEPAGE_MM = 12.6
POLLUTION_DEGREE = 3
REQUIRED_BOARDS = ("power", "control")
REQUIRED_BLOCKERS = ("connector", "enclosure")
REQUIRED_INTERFACE_DOMAIN = "SELV"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

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
    _string_list(interface.get("nets"), "interface.nets")

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


def _resolve(path: str, manifest_path: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate.resolve()


def _load_json(path: Path, context: str) -> dict[str, Any]:
    if not path.is_file():
        raise GateError(f"{context} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"{context} is not valid JSON: {path}: {exc}") from exc
    return _mapping(value, context)


def _check_source_interface(data: dict[str, Any], manifest_path: Path, errors: list[str]) -> None:
    interface = data["interface"]
    source_path = _resolve(interface["domain_manifest"], manifest_path)
    if not source_path.is_file():
        errors.append(f"interface domain manifest not found: {source_path}")
        return
    try:
        source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        errors.append(f"interface domain manifest is not valid YAML: {exc}")
        return
    if not isinstance(source, dict) or not isinstance(source.get("board_interface"), dict):
        errors.append("interface domain manifest has no board_interface mapping")
        return
    declared = source["board_interface"]
    if declared.get("name") != interface["name"]:
        errors.append("interface name does not match elec/domain_manifest.yaml")
    if declared.get("allowed_domains") != interface["allowed_domains"]:
        errors.append("interface allowed_domains does not match elec/domain_manifest.yaml")
    source_nets = declared.get("nets")
    if not isinstance(source_nets, list) or set(source_nets) != set(interface["nets"]):
        errors.append("interface nets do not match elec/domain_manifest.yaml")


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
            elif not _resolve(evidence, manifest_path).is_file():
                errors.append(f"{review_name} contract evidence not found: {evidence}")
        elif review.get("evidence") is not None:
            errors.append(f"{review_name} contract must keep evidence null while incomplete")


def _check_drc_report(path: Path, board_id: str, errors: list[str]) -> None:
    report = _load_json(path, f"{board_id} DRC report")
    if not isinstance(report.get("sample_count"), int) or report["sample_count"] < 1:
        errors.append(f"{board_id} DRC report must record a positive sample_count")
    for field in ("violations_by_type", "warnings_by_type"):
        if not isinstance(report.get(field), dict):
            errors.append(f"{board_id} DRC report must contain {field}")


def _check_provenance(
    path: Path,
    board_path: Path,
    board_id: str,
    manifest_path: Path,
    errors: list[str],
) -> None:
    record = _load_json(path, f"{board_id} provenance record")
    if record.get("source") != "measured-live":
        errors.append(f"{board_id} provenance source must be 'measured-live'")
    if record.get("dirty") is not False:
        errors.append(f"{board_id} provenance dirty must be false")
    measured_at_commit = record.get("measured_at_commit")
    if not isinstance(measured_at_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", measured_at_commit):
        errors.append(f"{board_id} provenance must record a full measured_at_commit SHA")
    if not isinstance(record.get("kicad_cli_version"), str) or not record["kicad_cli_version"].strip():
        errors.append(f"{board_id} provenance must record kicad_cli_version")
    inputs = record.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        errors.append(f"{board_id} provenance must contain an inputs list")
        return
    matching = False
    actual_hash = hashlib.sha256(board_path.read_bytes()).hexdigest() if board_path.is_file() else None
    for item in inputs:
        if not isinstance(item, dict):
            continue
        item_path = item.get("path")
        item_hash = item.get("sha256")
        if isinstance(item_path, str) and _resolve(item_path, manifest_path).resolve() == board_path.resolve():
            matching = True
            if not isinstance(item_hash, str) or not SHA256_RE.fullmatch(item_hash):
                errors.append(f"{board_id} provenance board input must contain a full sha256")
            elif actual_hash is not None and item_hash != actual_hash:
                errors.append(f"{board_id} provenance board input sha256 does not match the PCB")
    if not matching:
        errors.append(f"{board_id} provenance inputs must identify its PCB artifact")


def _check_cross_domain_report(path: Path, data: dict[str, Any], errors: list[str]) -> None:
    report = _load_json(path, "cross-domain report")
    if report.get("schema_version") != 1:
        errors.append("cross-domain report schema_version must be 1")
    if report.get("pollution_degree") != POLLUTION_DEGREE:
        errors.append("cross-domain report must use pollution degree 3")
    if report.get("required_creepage_mm") != REQUIRED_CREEPAGE_MM:
        errors.append("cross-domain report must require 12.6 mm creepage")
    measured = report.get("minimum_creepage_mm")
    if not isinstance(measured, (int, float)) or measured < REQUIRED_CREEPAGE_MM:
        errors.append("cross-domain report minimum_creepage_mm is below 12.6 mm")
    if report.get("boards") != ["POWER_BOARD", "CONTROL_BOARD"]:
        errors.append("cross-domain report must cover POWER_BOARD and CONTROL_BOARD")
    if report.get("violations") != []:
        errors.append("cross-domain report must contain an empty violations list")


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
        errors.append(f"cross-domain method not found: {data['cross_domain']['method']}")

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
                try:
                    _check_drc_report(_resolve(drc_report, path), board_id, errors)
                except GateError as exc:
                    errors.append(str(exc))
            provenance = board["checks"]["provenance"]["record"]
            if not provenance:
                errors.append(f"{board_role} board provenance record is not declared")
            elif pcb_path.is_file():
                try:
                    _check_provenance(
                        _resolve(provenance, path), pcb_path, board_id, path, errors
                    )
                except GateError as exc:
                    errors.append(str(exc))

        report = data["cross_domain"]["report"]
        if not report:
            errors.append("cross-domain report is not declared")
        else:
            try:
                _check_cross_domain_report(_resolve(report, path), data, errors)
            except GateError as exc:
                errors.append(str(exc))
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
        return EXIT_VIOLATION
    print("SPLIT-BOARD CONTRACT PASSED: generation and safety evidence are complete")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    return run(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
