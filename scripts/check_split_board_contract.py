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
import math
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from _lib.measurement_provenance import sha256_file
from _lib.repo import find_repo_root
from check_evidence_provenance import verify_commits_exist

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
FIXTURE_CONTEXT = "unit-test"
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


def _reject_nonfinite(value: Any, context: str) -> None:
    """Reject JSON/YAML numbers that cannot be trusted as engineering data."""
    if isinstance(value, float) and not math.isfinite(value):
        raise GateError(f"{context} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_nonfinite(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_nonfinite(child, f"{context}[{index}]")


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


def _check_manifest_location(path: Path, fixture_context: Any) -> None:
    """Keep the fixture escape hatch out of production Git worktrees."""
    try:
        repo_root = find_repo_root(path.parent)
    except FileNotFoundError:
        if fixture_context != FIXTURE_CONTEXT:
            raise GateError(
                "split-board manifest outside a Git worktree must declare "
                "fixture_context: unit-test"
            ) from None
        return

    if fixture_context is not None:
        raise GateError(
            "fixture_context is permitted only for manifests outside a Git worktree"
        )
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise GateError(f"split-board manifest is outside its Git worktree: {path}") from exc
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(relative)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GateError(f"production split-board manifest must be tracked: {path}")


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
    _reject_nonfinite(data, "split-board contract")

    if data.get("schema_version") != SCHEMA_VERSION:
        raise GateError(
            f"schema_version must be exactly {SCHEMA_VERSION}, got {data.get('schema_version')!r}"
        )
    if data.get("architecture") != ARCHITECTURE:
        raise GateError(f"architecture must be {ARCHITECTURE!r}")
    status = _text(data.get("status"), "status")
    if status not in {"contract-incomplete", "ready"}:
        raise GateError("status must be 'contract-incomplete' or 'ready'")
    hierarchy = _text(data.get("hierarchy"), "hierarchy")
    if not hierarchy:
        raise GateError("hierarchy must identify the split-board Atopile hierarchy")
    fixture_context = data.get("fixture_context")
    if fixture_context is not None and fixture_context != FIXTURE_CONTEXT:
        raise GateError(f"fixture_context must be {FIXTURE_CONTEXT!r} when present")
    _check_manifest_location(path, fixture_context)

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
            if check_name == "drc":
                ceiling_source = _mapping(
                    check.get("ceiling_source"),
                    f"boards.{board_role}.checks.drc.ceiling_source",
                )
                _text(
                    ceiling_source.get("path"),
                    f"boards.{board_role}.checks.drc.ceiling_source.path",
                    allow_none=True,
                )
                _text(
                    ceiling_source.get("board_id"),
                    f"boards.{board_role}.checks.drc.ceiling_source.board_id",
                    allow_none=True,
                )
                digest = ceiling_source.get("sha256")
                if digest is not None and (
                    not isinstance(digest, str) or not SHA256_RE.fullmatch(digest)
                ):
                    raise GateError(
                        f"boards.{board_role}.checks.drc.ceiling_source.sha256 "
                        "must be a full SHA-256 when present"
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
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise GateError(f"cannot establish contract repository: {exc}") from exc
        if isinstance(raw, dict) and raw.get("fixture_context") == FIXTURE_CONTEXT:
            return manifest_path.parent.resolve()
        raise GateError(
            "split-board manifest must live in a Git worktree; non-repository "
            "fixtures must declare fixture_context: unit-test"
        ) from None


def _contract_git_root(manifest_path: Path) -> Path:
    """Find the git repository used for provenance verification.

    Synthetic contract fixtures have no git object database, so they use the
    validator checkout for their deliberately real commit fixture. Production
    contracts always resolve relative to their own worktree.
    """
    try:
        return find_repo_root(manifest_path.parent)
    except FileNotFoundError:
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise GateError(f"cannot establish contract repository: {exc}") from exc
        if isinstance(raw, dict) and raw.get("fixture_context") == FIXTURE_CONTEXT:
            return REPO_ROOT
        raise GateError(
            "cannot verify provenance outside a Git worktree without explicit "
            "fixture_context: unit-test"
        ) from None


def _is_fixture(manifest_path: Path) -> bool:
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    return isinstance(raw, dict) and raw.get("fixture_context") == FIXTURE_CONTEXT


def _require_tracked(path: Path, manifest_path: Path, context: str) -> None:
    """Require production evidence to be committed in the owning worktree."""
    if _is_fixture(manifest_path):
        return
    repo_root = _contract_repo_root(manifest_path)
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise GateError(f"{context} is outside the owning worktree: {path}") from exc
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(relative)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GateError(f"{context} must be a tracked production file: {path}")


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
    _reject_nonfinite(value, context)
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


def _evidence_digest(value: dict[str, Any]) -> str:
    """Return the digest of a JSON evidence record excluding its own digest."""
    unsigned = dict(value)
    unsigned.pop("content_sha256", None)
    return sha256_file_from_json(unsigned)


def _check_source_interface(data: dict[str, Any], manifest_path: Path, errors: list[str]) -> None:
    interface = data["interface"]
    source_path = _resolve(interface["domain_manifest"], manifest_path)
    if not source_path.is_file():
        raise GateError(f"interface domain manifest not found: {source_path}")
    _require_tracked(source_path, manifest_path, "interface domain manifest")
    try:
        source_data = yaml.safe_load(source_path.read_text(encoding="utf-8"))
        source_interface = _mapping(source_data.get("board_interface"), "board_interface")
        source_signals = source_interface.get("signals")
        if not isinstance(source_signals, list):
            raise GateError("board_interface.signals must be a list")
        declared_nets = tuple(source_interface.get("nets", ()))
        if not declared_nets or any(not isinstance(net, str) for net in declared_nets):
            raise GateError("board_interface.nets must be a non-empty string list")
        signal_nets = tuple(signal.get("net") for signal in source_signals if isinstance(signal, dict))
        if signal_nets != declared_nets:
            raise GateError("board_interface.signals must match board_interface.nets")
    except (OSError, yaml.YAMLError, AttributeError, TypeError) as exc:
        raise GateError(f"interface domain manifest is malformed: {exc}") from exc
    expected = {
        "name": interface["name"],
        "power_board": "POWER_BOARD",
        "control_board": "CONTROL_BOARD",
        "connector": interface["connector_ref"],
        "nets": tuple(interface["nets"]),
        "allowed_domains": tuple(interface["allowed_domains"]),
    }
    actual = {
        "name": source_interface.get("name"),
        "power_board": source_interface.get("power_board"),
        "control_board": source_interface.get("control_board"),
        "connector": source_interface.get("connector"),
        "nets": tuple(source_interface.get("nets", ())),
        "allowed_domains": tuple(source_interface.get("allowed_domains", ())),
    }
    for field, wanted in expected.items():
        if actual[field] != wanted:
            raise GateError(
                f"interface {field} does not match elec/domain_manifest.yaml: "
                f"expected {wanted!r}, got {actual[field]!r}"
            )
    hierarchy_path = _resolve(data["hierarchy"], manifest_path)
    if not hierarchy_path.is_file():
        raise GateError(f"split-board hierarchy not found: {data['hierarchy']}")
    _require_tracked(hierarchy_path, manifest_path, "split-board hierarchy")
    if not _is_fixture(manifest_path):
        try:
            from check_domain_partition import validate_split_domain_contract

            validate_split_domain_contract(
                source_path,
                src_dir=source_path.parent / "src",
            )
        except Exception as exc:
            if isinstance(exc, GateError):
                raise
            raise GateError(
                "authoritative split domain validation failed: " + str(exc)
            ) from exc
    hierarchy = hierarchy_path.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^interface\s+PowerControlSELV:\s*\n(?P<body>.*?)(?=^\S|\Z)",
        hierarchy,
    )
    if match is None:
        raise GateError(
            "split-board hierarchy has no PowerControlSELV interface"
        )
    actual_signals = tuple(
        re.findall(r"^\s+signal\s+([A-Za-z_]\w*)\s*$", match.group("body"), re.MULTILINE)
    )
    try:
        expected_signals = tuple(ATOPILE_INTERFACE_SIGNAL[net] for net in source_interface["nets"])
    except KeyError as exc:
        raise GateError(
            "domain_manifest.yaml board_interface.nets contains an "
            f"unsupported net for the Atopile boundary: {exc.args[0]!r}"
        ) from exc
    if actual_signals != expected_signals:
        raise GateError(
            "split-board hierarchy PowerControlSELV signals do not "
            "match domain_manifest.yaml board_interface.nets: "
            f"expected {expected_signals!r}, got {actual_signals!r}"
        )
    # U3 consumes the typed readiness verdict from U1.  An unresolved
    # interface is a valid, machine-readable blocker, not malformed input.
    unresolved = [
        signal.get("net") for signal in source_signals
        if signal.get("status") != "resolved"
    ]
    if unresolved:
        errors.append(
            "domain interface readiness blocked: unresolved signal semantics: "
            + ", ".join(sorted(str(net) for net in unresolved))
        )
    fault = source_interface.get("fault_aggregation")
    if not isinstance(fault, dict) or fault.get("status") != "resolved":
        errors.append("domain interface readiness blocked: fault aggregation semantics are unresolved")
    generation_spec = source_interface.get("generation")
    if not isinstance(generation_spec, dict) or generation_spec.get("status") != "ready":
        errors.append("domain interface readiness blocked: generation.status is not 'ready'")


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
                    _require_tracked(evidence_path, manifest_path, f"{review_name} contract evidence")
                except GateError as exc:
                    raise GateError(str(exc)) from exc
        elif review.get("evidence") is not None:
            errors.append(f"{review_name} contract must keep evidence null while incomplete")


def _read_artifact(path: Path, context: str, *, suffix: str | None = None) -> bytes:
    if not path.is_file():
        raise GateError(f"{context} not found: {path}")
    if suffix is not None and path.suffix != suffix:
        raise GateError(f"{context} must use {suffix} format: {path}")
    try:
        contents = path.read_bytes()
        contents.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise GateError(f"{context} is not readable UTF-8: {path}: {exc}") from exc
    if not contents.strip() or b"\x00" in contents:
        raise GateError(f"{context} is empty or contains NUL bytes: {path}")
    return contents


def _check_atopile_entrypoint(path: Path, context: str, board_role: str) -> bytes:
    """Require an Atopile source to contain a real module/interface shape."""
    contents = _read_artifact(path, context, suffix=".ato")
    text = contents.decode("utf-8")
    declarations = re.findall(
        r"(?m)^\s*(?:module|interface|component)\s+([A-Za-z_]\w*)\s*:",
        text,
    )
    if not declarations:
        raise GateError(f"{context} has no Atopile module, interface, or component declaration")
    if not re.search(r"(?m)^\s*module\s+[A-Za-z_]\w*\s*:", text):
        raise GateError(f"{context} must declare an Atopile module entrypoint")
    # A board entrypoint must have a board-shaped declaration, not merely an
    # imported library interface.  Accept the boundary names used by the
    # foundation and conventional generated PowerBoard/ControlBoard names.
    role_names = {
        "power": {"PowerBoard", "PowerBoardBoundary"},
        "control": {"ControlBoard", "ControlBoardBoundary"},
    }[board_role]
    if not role_names.intersection(declarations):
        raise GateError(
            f"{context} has no {board_role}-board module declaration "
            f"(expected one of {sorted(role_names)!r})"
        )
    return contents


def _parse_sexp(contents: bytes, context: str) -> list[Any]:
    """Parse the small structural subset needed by KiCad artifacts."""
    text = contents.decode("utf-8")
    tokens = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^()\s]+', text)
    position = 0

    def parse_list() -> list[Any]:
        nonlocal position
        if position >= len(tokens) or tokens[position] != "(":
            raise GateError(f"{context} has an invalid S-expression")
        position += 1
        result: list[Any] = []
        while position < len(tokens) and tokens[position] != ")":
            if tokens[position] == "(":
                result.append(parse_list())
            else:
                result.append(tokens[position])
                position += 1
        if position >= len(tokens):
            raise GateError(f"{context} has unbalanced parentheses")
        position += 1
        return result

    tree = parse_list()
    if position != len(tokens):
        raise GateError(f"{context} contains multiple top-level S-expressions")
    return tree


def _check_sexp_artifact(path: Path, context: str, root: bytes, suffix: str) -> bytes:
    contents = _read_artifact(path, context, suffix=suffix)
    if not contents.lstrip().startswith(b"(" + root):
        raise GateError(f"{context} does not have a parseable {root.decode()} root")
    tree = _parse_sexp(contents, context)
    if not tree or tree[0] != root.decode("ascii"):
        raise GateError(f"{context} does not have a parseable {root.decode()} root")
    children = [item for item in tree[1:] if isinstance(item, list) and item]
    heads = {item[0] for item in children if isinstance(item[0], str)}
    if root == b"kicad_pcb":
        required = {"version", "generator", "general", "layers", "setup"}
        if not required.issubset(heads):
            raise GateError(
                f"{context} is missing meaningful KiCad board structure: "
                f"{sorted(required - heads)}"
            )
        version = next(item for item in children if item[0] == "version")
        if len(version) != 2 or not re.fullmatch(r"\d+", str(version[1])):
            raise GateError(f"{context} must contain a numeric KiCad version")
    elif root == b"export":
        required = {"version", "components", "nets"}
        if not required.issubset(heads):
            raise GateError(
                f"{context} is missing meaningful netlist structure: "
                f"{sorted(required - heads)}"
            )
        components = next(item for item in children if item[0] == "components")
        nets = next(item for item in children if item[0] == "nets")
        comp_items = [item for item in components[1:] if isinstance(item, list) and item]
        net_items = [item for item in nets[1:] if isinstance(item, list) and item]
        if not comp_items or not net_items:
            raise GateError(f"{context} must contain components and nets")
        if any(
            item[0] != "comp"
            or not any(child[0] == "ref" for child in item[1:] if isinstance(child, list) and child)
            for item in comp_items
        ):
            raise GateError(f"{context} contains a component without a ref")
        if any(
            item[0] != "net"
            or not any(child[0] == "name" for child in item[1:] if isinstance(child, list) and child)
            or not any(child[0] == "node" for child in item[1:] if isinstance(child, list) and child)
            for item in net_items
        ):
            raise GateError(f"{context} contains a net without a name/node")
    return contents


def _check_drc_report(
    path: Path,
    board_id: str,
    board_path: Path,
    provenance_path: Path,
    provenance: dict[str, Any],
    manifest_path: Path,
    ceiling_limits: dict[str, Any],
) -> dict[str, Any]:
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
        counts = report.get(field)
        if not isinstance(counts, dict) or any(
            not isinstance(name, str) or not name.strip()
            or not isinstance(count, int) or isinstance(count, bool) or count < 0
            for name, count in counts.items()
        ):
            raise GateError(f"{board_id} DRC report must contain non-negative integer {field}")
    pcb_hash = sha256_file(board_path)
    provenance_hash = _evidence_digest(provenance)
    if report.get("pcb_sha256") != pcb_hash:
        raise GateError(f"{board_id} DRC report pcb_sha256 does not match its PCB")
    if report.get("provenance_sha256") != provenance_hash:
        raise GateError(f"{board_id} DRC report provenance_sha256 does not match its provenance")
    if not isinstance(report.get("method_config"), dict) or not report["method_config"]:
        raise GateError(f"{board_id} DRC report must record non-empty method_config")
    # The report itself is content-addressed, so a copied/stale report cannot
    # be made to agree with a new PCB merely by changing its binding fields.
    digest = report.get("content_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise GateError(f"{board_id} DRC report must record a full content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if digest != sha256_file_from_json(unsigned):
        raise GateError(f"{board_id} DRC report content_sha256 does not match the report")
    acceptance = report.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("source") != "project-drc-ceiling":
        raise GateError(f"{board_id} DRC report must name project-drc-ceiling acceptance")
    if "ceilings" in acceptance:
        raise GateError(
            f"{board_id} DRC report must not carry self-declared ceilings; "
            "use the tracked ceiling source"
        )
    if acceptance.get("ceiling_source") != ceiling_limits["source_ref"]:
        raise GateError(f"{board_id} DRC report ceiling_source does not match the manifest")
    if acceptance.get("ceiling_board_id") != ceiling_limits["board_id"]:
        raise GateError(f"{board_id} DRC report ceiling_board_id does not match the manifest")
    for field in ("violations_by_type", "warnings_by_type"):
        limits = ceiling_limits[field]
        if not isinstance(limits, dict) or any(
            not isinstance(name, str) or not isinstance(value, int)
            or isinstance(value, bool) or value < 0 for name, value in limits.items()
        ):
            raise GateError(f"{board_id} DRC acceptance must contain non-negative {field} ceilings")
        for rule, count in report[field].items():
            if count > limits.get(rule, 0):
                raise GateError(
                    f"{board_id} DRC {field}[{rule!r}]={count} exceeds "
                    f"project ceiling {limits.get(rule, 0)}"
                )
    for field, count_field in (("error_ceiling", "violations_by_type"), ("warning_ceiling", "warnings_by_type")):
        limit = ceiling_limits[field]
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise GateError(f"{board_id} DRC acceptance must contain non-negative {field}")
        if sum(report[count_field].values()) > limit:
            raise GateError(f"{board_id} DRC {count_field} exceeds project {field}")
    _require_tracked(path, manifest_path, f"{board_id} DRC report")
    _require_tracked(provenance_path, manifest_path, f"{board_id} provenance record")
    return report


def _load_ceiling_source(
    path: Path,
    board_id: str,
    expected_sha256: str | None,
    manifest_path: Path,
) -> dict[str, Any]:
    """Load limits from a tracked, content-addressed project ceiling file."""
    _require_tracked(path, manifest_path, f"{board_id} DRC ceiling source")
    try:
        actual_sha256 = sha256_file(path)
    except OSError as exc:
        raise GateError(f"{board_id} DRC ceiling source cannot be hashed: {exc}") from exc
    if not expected_sha256:
        raise GateError(f"{board_id} DRC ceiling source must declare its expected sha256")
    if actual_sha256 != expected_sha256:
        raise GateError(f"{board_id} DRC ceiling source sha256 does not match the manifest")
    source = _load_json(path, f"{board_id} DRC ceiling source")
    boards = source.get("boards")
    if isinstance(boards, list):
        selected = next(
            (entry for entry in boards if isinstance(entry, dict) and entry.get("board_id") == board_id),
            None,
        )
        if selected is None:
            # The project ceiling is commonly keyed by its legacy board name;
            # the manifest's explicit board_id is the authoritative selector.
            selected = next(
                (entry for entry in boards if isinstance(entry, dict) and entry.get("board_id") == "temper"),
                None,
            )
        if selected is None:
            raise GateError(f"{board_id} DRC ceiling source has no selected board")
    else:
        selected = source
    limits: dict[str, Any] = {"source_ref": None, "board_id": board_id}
    for field in ("violations_by_type", "warnings_by_type", "error_ceiling", "warning_ceiling"):
        if field not in selected:
            raise GateError(f"{board_id} DRC ceiling source is missing {field}")
        limits[field] = selected[field]
    limits["source_ref"] = str(path.relative_to(_contract_repo_root(manifest_path)))
    limits["board_id"] = selected.get("board_id", board_id)
    return limits


def _check_provenance(
    path: Path,
    board_path: Path,
    board_id: str,
    manifest_path: Path,
) -> dict[str, Any]:
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
    digest = record.get("content_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise GateError(f"{board_id} provenance must record a full content_sha256")
    if digest != _evidence_digest(record):
        raise GateError(f"{board_id} provenance content_sha256 does not match the record")
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
    return record


def _check_cross_domain_report(
    path: Path,
    manifest_path: Path,
    method_path: Path,
    board_bindings: dict[str, dict[str, str]],
) -> None:
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
    if report.get("method") != str(method_path.relative_to(_contract_repo_root(manifest_path))):
        raise GateError("cross-domain report method does not match the manifest method")
    if report.get("method_sha256") != sha256_file(method_path):
        raise GateError("cross-domain report method_sha256 does not match the method")
    config = report.get("configuration")
    if not isinstance(config, dict) or config.get("pollution_degree") != POLLUTION_DEGREE or config.get("reinforced_creepage_mm") != REQUIRED_CREEPAGE_MM:
        raise GateError("cross-domain report configuration must record PD3 and 12.6 mm")
    if report.get("board_inputs") != board_bindings:
        raise GateError("cross-domain report board_inputs do not match both board PCB/provenance records")
    _require_tracked(path, manifest_path, "cross-domain report")
    _require_tracked(method_path, manifest_path, "cross-domain measurement method")


def _check_distinct_board_artifacts(
    board_paths: dict[str, dict[str, Path]],
    board_hashes: dict[str, dict[str, str]],
    evidence_paths: dict[str, dict[str, Path]] | None = None,
    evidence_hashes: dict[str, dict[str, str]] | None = None,
) -> None:
    """Reject reused paths or byte-identical artifacts across board roles."""
    if len(board_paths) != len(REQUIRED_BOARDS):
        return
    for artifact_name in ("source", "pcb", "netlist"):
        paths = [board_paths[role][artifact_name].resolve() for role in REQUIRED_BOARDS]
        if len(set(paths)) != len(paths):
            raise GateError(f"board {artifact_name} artifacts must be distinct per board")
        hashes = [board_hashes[role][artifact_name] for role in REQUIRED_BOARDS]
        if len(set(hashes)) != len(hashes):
            raise GateError(f"board {artifact_name} artifacts must not be reused byte-for-byte")
    if (
        evidence_paths is not None
        and evidence_hashes is not None
        and len(evidence_paths) == len(REQUIRED_BOARDS)
        and len(evidence_hashes) == len(REQUIRED_BOARDS)
    ):
        for artifact_name in ("drc", "provenance"):
            paths = [evidence_paths[role][artifact_name].resolve() for role in REQUIRED_BOARDS]
            if len(set(paths)) != len(paths):
                raise GateError(f"board {artifact_name} evidence must be distinct per board")
            hashes = [evidence_hashes[role][artifact_name] for role in REQUIRED_BOARDS]
            if len(set(hashes)) != len(hashes):
                raise GateError(f"board {artifact_name} evidence must not be reused byte-for-byte")


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
    _require_tracked(method_path, path, "cross-domain measurement method")

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
        board_paths: dict[str, dict[str, Path]] = {}
        board_hashes: dict[str, dict[str, str]] = {}
        board_provenance: dict[str, dict[str, Any]] = {}
        evidence_paths: dict[str, dict[str, Path]] = {}
        evidence_hashes: dict[str, dict[str, str]] = {}
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
            if (
                pcb_path.is_file()
                and netlist_value
                and _resolve(netlist_value, path).is_file()
                and source_entrypoint
                and _resolve(source_entrypoint, path).is_file()
            ):
                source_path = _resolve(source_entrypoint, path)
                netlist_path = _resolve(netlist_value, path)
                _check_atopile_entrypoint(
                    source_path, f"{board_role} board source entrypoint", board_role
                )
                _check_sexp_artifact(pcb_path, f"{board_role} board PCB artifact", b"kicad_pcb", ".kicad_pcb")
                _check_sexp_artifact(netlist_path, f"{board_role} board netlist artifact", b"export", ".net")
                for artifact_path, context in (
                    (source_path, f"{board_role} board source entrypoint"),
                    (pcb_path, f"{board_role} board PCB artifact"),
                    (netlist_path, f"{board_role} board netlist artifact"),
                ):
                    _require_tracked(artifact_path, path, context)
                board_paths[board_role] = {
                    "source": source_path,
                    "pcb": pcb_path,
                    "netlist": netlist_path,
                }
                board_hashes[board_role] = {
                    key: sha256_file(value) for key, value in board_paths[board_role].items()
                }
            ceiling_spec = board["checks"]["drc"]["ceiling_source"]
            ceiling_path_value = ceiling_spec.get("path")
            ceiling_limits: dict[str, Any] | None = None
            if not ceiling_path_value:
                errors.append(f"{board_role} board DRC ceiling source is not declared")
            else:
                ceiling_path = _resolve(ceiling_path_value, path)
                if not ceiling_path.is_file():
                    raise GateError(
                        f"{board_id} DRC ceiling source not found: {ceiling_path_value}"
                    )
                ceiling_limits = _load_ceiling_source(
                    ceiling_path,
                    ceiling_spec.get("board_id"),
                    ceiling_spec.get("sha256"),
                    path,
                )
            drc_report = board["checks"]["drc"]["report"]
            if not drc_report:
                errors.append(f"{board_role} board DRC report is not declared")
            else:
                drc_path = _resolve(drc_report, path)
                if not drc_path.is_file():
                    raise GateError(f"{board_id} DRC report not found: {drc_report}")
                provenance_value = board["checks"]["provenance"]["record"]
                provenance_path = _resolve(provenance_value, path) if provenance_value else None
                if (
                    provenance_path is not None
                    and provenance_path.is_file()
                    and pcb_path.is_file()
                    and ceiling_limits is not None
                ):
                    provenance = _check_provenance(provenance_path, pcb_path, board_id, path)
                    board_provenance[board_role] = provenance
                    _check_drc_report(
                        drc_path,
                        board_id,
                        pcb_path,
                        provenance_path,
                        provenance,
                        path,
                        ceiling_limits,
                    )
                    evidence_paths[board_role] = {
                        "drc": drc_path,
                        "provenance": provenance_path,
                    }
                    evidence_hashes[board_role] = {
                        "drc": sha256_file(drc_path),
                        "provenance": _evidence_digest(provenance),
                    }
            provenance = board["checks"]["provenance"]["record"]
            if not provenance:
                errors.append(f"{board_role} board provenance record is not declared")
            elif pcb_path.is_file():
                provenance_path = _resolve(provenance, path)
                if not provenance_path.is_file():
                    raise GateError(f"{board_id} provenance record not found: {provenance}")
                if board_role not in board_provenance:
                    board_provenance[board_role] = _check_provenance(
                        provenance_path, pcb_path, board_id, path
                    )

        # A split contract must not silently point both sides at one artifact
        # (or at byte-identical copies).  This catches stale/reused evidence
        # before any generator trusts the readiness verdict.
        _check_distinct_board_artifacts(
            board_paths, board_hashes, evidence_paths, evidence_hashes
        )
        if len(board_provenance) == len(REQUIRED_BOARDS):
            provenance_hashes = [_evidence_digest(board_provenance[role]) for role in REQUIRED_BOARDS]
            if len(set(provenance_hashes)) != len(provenance_hashes):
                raise GateError("board provenance records must be distinct")
            bindings = {
                ("POWER_BOARD" if role == "power" else "CONTROL_BOARD"): {
                    "pcb_sha256": board_hashes[role]["pcb"],
                    "provenance_sha256": provenance_hashes[REQUIRED_BOARDS.index(role)],
                }
                for role in REQUIRED_BOARDS
                if role in board_hashes
            }

        report = data["cross_domain"]["report"]
        if not report:
            errors.append("cross-domain report is not declared")
        else:
            if len(board_provenance) == len(REQUIRED_BOARDS) and len(board_hashes) == len(REQUIRED_BOARDS):
                _check_cross_domain_report(
                    _resolve(report, path), path, method_path, bindings
                )
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
