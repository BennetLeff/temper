#!/usr/bin/env python3
"""Sealed replay shim for the synthetic R24/R25 joint contract corpus.

All JSON is opened once through ``qualification_replay``.  This module only
assembles the six frozen fixture objects and invokes the Rust pyo3 function;
joint policy and the timing budget are not duplicated here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts._lib import qualification_replay
except ImportError:  # pragma: no cover
    from _lib import qualification_replay


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE_ROOT = REPO_ROOT / "packages/temper-placer/tests/fixtures/isolation_joint_qualification"
CONTRACT_PATH = Path("power_pcb_dataset/qualification/isolation_joint/contract.json")
U9_ROOT = Path("power_pcb_dataset/qualification/isolation_joint")
U9_INTERFACE_CONTRACT = Path("elec/qualification/isolation_joint/interface_contract.json")
U9_FIXTURE_CONTRACT = Path("elec/qualification/isolation_joint/validation/fixture_contract.json")
FIXTURE_NAMES = (
    "contract_manifest.json",
    "iso_receipt.json",
    "ct07_receipt.json",
    "combined_candidate.json",
    "shutdown_evidence.json",
    "owner_signoffs.json",
)


class JointReplayError(qualification_replay.ReplayError):
    """A fail-closed joint replay error."""


def _read_json(path: Path, root: Path) -> dict[str, Any] | list[Any]:
    try:
        read = qualification_replay.read_once(path, root=root)
    except qualification_replay.ReplayError as exc:
        raise JointReplayError(f"cannot read joint fixture {path.name}: {exc}") from exc
    try:
        value = json.loads(read.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JointReplayError(f"invalid joint fixture {path.name}: {exc}") from exc
    if not isinstance(value, (dict, list)):
        raise JointReplayError(f"joint fixture {path.name} must be an object or list")
    return value


def _read_json_with_bytes(
    path: Path, root: Path
) -> tuple[dict[str, Any] | list[Any], bytes]:
    read = qualification_replay.read_once(path, root=root)
    try:
        value = json.loads(read.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JointReplayError(f"invalid joint input {path}: {exc}") from exc
    if not isinstance(value, (dict, list)):
        raise JointReplayError(f"joint input must be an object or list: {path}")
    return value, read.data


def compose_fixture(fixture_root: Path = DEFAULT_FIXTURE_ROOT, *, root: Path = REPO_ROOT) -> dict[str, Any]:
    """Read and compose the frozen fixture corpus without policy decisions."""
    values = {name.removesuffix(".json"): _read_json(fixture_root / name, root) for name in FIXTURE_NAMES}
    manifest = values["contract_manifest"]
    if not isinstance(manifest, dict):
        raise JointReplayError("contract_manifest.json must be an object")
    contract, contract_bytes = _read_json_with_bytes(root / CONTRACT_PATH, root)
    if not isinstance(contract, dict):
        raise JointReplayError("canonical joint contract must be an object")
    if (
        contract.get("schema_version") != manifest.get("schema_version")
        or hashlib.sha256(contract_bytes).hexdigest() != manifest.get("joint_contract_digest")
        or contract.get("evaluator_identity") != manifest.get("evaluator_identity")
    ):
        raise JointReplayError("fixture manifest does not bind the canonical joint contract")
    for key in ("iso_receipt", "ct07_receipt", "combined_candidate", "shutdown_evidence"):
        if not isinstance(values[key], dict):
            raise JointReplayError(f"{key}.json must be an object")
    if not isinstance(values["owner_signoffs"], list):
        raise JointReplayError("owner_signoffs.json must be a list")
    package = dict(manifest)
    package["iso"] = values["iso_receipt"]
    package["ct07"] = values["ct07_receipt"]
    package["combined_candidate"] = values["combined_candidate"]
    package["shutdown"] = values["shutdown_evidence"]
    package["signoffs"] = values["owner_signoffs"]
    # Preserve the exact bytes used to establish the contract identity.  Rust
    # validates this binding; the manifest value is not accepted as an
    # independently editable hexadecimal label.
    package["joint_contract_bytes"] = list(contract_bytes)
    return package


U9_EVIDENCE_NAMES = (
    "corridor_evidence.json",
    "loop_evidence.json",
    "retention_evidence.json",
    "thermal_evidence.json",
    "interface_evidence.json",
    "shutdown_evidence.json",
    "fault_injection_evidence.json",
)


def _read_u9_json(
    relative: str | Path, *, root: Path, qualification_root: Path
) -> dict[str, Any] | list[Any]:
    path = qualification_root / relative
    return _read_json(path, root=root)


def compose_u9(
    *, root: Path = REPO_ROOT, qualification_root: Path | None = None
) -> dict[str, Any]:
    """Compose the real U9 input envelope, including its blocked state.

    U9 deliberately does not manufacture domain receipts, a combined board,
    captures, or sign-offs.  The manifest records the current producer states;
    this function binds those states to the checked-in source decisions and
    returns an input envelope for the fail-closed preflight below.
    """
    qualification_root = qualification_root or (root / U9_ROOT)
    manifest = _read_u9_json("manifest.json", root=root, qualification_root=qualification_root)
    combined = _read_u9_json(
        "combined_candidate.json", root=root, qualification_root=qualification_root
    )
    signoffs = _read_u9_json(
        "owner_signoffs.json", root=root, qualification_root=qualification_root
    )
    evidence = {
        name.removesuffix(".json"): _read_u9_json(
            name, root=root, qualification_root=qualification_root
        )
        for name in U9_EVIDENCE_NAMES
    }
    interface = _read_json(root / U9_INTERFACE_CONTRACT, root=root)
    fixture = _read_json(root / U9_FIXTURE_CONTRACT, root=root)
    contract, contract_bytes = _read_json_with_bytes(root / CONTRACT_PATH, root=root)
    if not all(isinstance(value, dict) for value in (manifest, combined, interface, fixture, contract)):
        raise JointReplayError("U9 contract and manifest roots must be objects")
    if not isinstance(signoffs, dict):
        raise JointReplayError("U9 owner_signoffs.json must be an object")
    if any(not isinstance(value, dict) for value in evidence.values()):
        raise JointReplayError("U9 evidence records must be objects")
    if (
        manifest.get("schema_version") != contract.get("schema_version")
        or manifest.get("joint_contract_digest") != hashlib.sha256(contract_bytes).hexdigest()
        or manifest.get("evaluator_identity") != contract.get("evaluator_identity")
    ):
        raise JointReplayError("U9 manifest does not bind the canonical U8 contract")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {"iso", "ct07"}:
        raise JointReplayError("U9 manifest must declare exactly the ISO and CT07 inputs")
    source_states: dict[str, dict[str, Any]] = {}
    for domain, record in inputs.items():
        if not isinstance(record, dict):
            raise JointReplayError(f"U9 {domain} input record must be an object")
        source_states[domain] = dict(record)
        handoff_path = record.get("handoff_path")
        source_states[domain]["handoff_available"] = bool(
            isinstance(handoff_path, str) and handoff_path and (root / handoff_path).is_file()
        )
        for source_key in ("internal_decision_path", "preliminary_decision_path"):
            source_path = record.get(source_key)
            if not isinstance(source_path, str) or not source_path:
                raise JointReplayError(f"U9 {domain} is missing {source_key}")
            source, source_raw = _read_json_with_bytes(root / source_path, root=root)
            if not isinstance(source, dict):
                raise JointReplayError(f"U9 {domain} source decision must be an object")
            source_stage = source.get("stage", source.get("status"))
            if source_stage != record.get("source_stage"):
                raise JointReplayError(
                    f"U9 {domain} source stage diverges from manifest: {source_path}"
                )
            if source_key == "preliminary_decision_path":
                source_states[domain]["preliminary_decision_digest"] = hashlib.sha256(source_raw).hexdigest()
        if source_states[domain]["handoff_available"]:
            handoff = _read_json(root / handoff_path, root=root)  # type: ignore[arg-type]
            if not isinstance(handoff, dict) or handoff.get("preliminary_decision_digest") != source_states[domain].get("preliminary_decision_digest"):
                source_states[domain]["handoff_available"] = False
                source_states[domain]["handoff_stale"] = True

    return {
        "schema_version": manifest["schema_version"],
        "candidate_id": manifest.get("candidate_id"),
        "joint_contract_digest": manifest.get("joint_contract_digest"),
        "evaluator_identity": manifest.get("evaluator_identity"),
        "inputs": source_states,
        "interface_contract": interface,
        "fixture_contract": fixture,
        "combined_candidate": combined,
        "evidence": evidence,
        "signoffs": signoffs,
    }


def evaluate_u9(package: dict[str, Any]) -> dict[str, Any]:
    """Read/publish adapter for the Rust-owned U9 prerequisite evaluator."""
    try:
        import temper_quality_oracle
    except ImportError as exc:  # pragma: no cover
        raise JointReplayError("temper_quality_oracle is unavailable; rebuild the pyo3 extension") from exc
    evaluator = getattr(temper_quality_oracle, "evaluate_isolation_joint_u9_json", None)
    if not callable(evaluator):
        raise JointReplayError("U9 Rust evaluator registration is missing")
    try:
        result = json.loads(evaluator(json.dumps(package, sort_keys=True, separators=(",", ":"))))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise JointReplayError(f"U9 Rust evaluator rejected package: {exc}") from exc
    if not isinstance(result, dict):
        raise JointReplayError("U9 Rust evaluator returned a non-object")
    return result


def replay_u9(
    *, output_path: Path | None = None, root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Replay current U9 inputs and optionally publish the stopped decision."""
    package = compose_u9(root=root)
    result = evaluate_u9(package)
    if output_path is not None:
        output = output_path if output_path.is_absolute() else root / output_path
        output_root = (root / U9_ROOT).resolve()
        try:
            output.resolve().relative_to(output_root)
        except ValueError as exc:
            raise JointReplayError("U9 output must remain under the joint qualification root") from exc
        qualification_replay.publish_atomic(
            output,
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            root=root,
        )
    return result


def evaluate(package: dict[str, Any]) -> str:
    """Invoke the sole Rust evaluator across the pyo3 boundary."""
    try:
        import temper_quality_oracle
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise JointReplayError("temper_quality_oracle is unavailable; rebuild the pyo3 extension") from exc
    evaluator = getattr(temper_quality_oracle, "evaluate_isolation_joint_qualification_json", None)
    if evaluator is None:
        raise JointReplayError("joint evaluator registration is missing from temper_quality_oracle")
    return evaluator(json.dumps(package, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--u9", action="store_true", help="replay the real, currently blocked U9 envelope")
    parser.add_argument("--output", type=Path, help="optional U9 decision output below its qualification root")
    args = parser.parse_args(argv)
    try:
        if args.u9:
            result = replay_u9(output_path=args.output)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        result = evaluate(compose_fixture(args.fixture_root))
    except JointReplayError as exc:
        print(f"joint replay stopped: {exc}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
