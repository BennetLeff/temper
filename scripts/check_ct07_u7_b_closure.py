#!/usr/bin/env python3
"""Replay CT07 U7-B final owner/FMEA closure without inventing authority."""

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

try:
    import temper_quality_oracle
except ImportError:  # pragma: no cover
    temper_quality_oracle = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPO_ROOT / "power_pcb_dataset/qualification/ct07_t2"
DEFAULT_INDEX = OUTPUT_ROOT / "evidence_index.json"


class U7BClosureGateError(RuntimeError):
    """The U7-B package cannot be replayed from its bound inputs."""


def _rust_debug_status(value: Any) -> str:
    """Match Rust's ``Debug`` spelling used by the semantic digest contract."""
    return {"pass": "Pass", "fail": "Fail", "pending": "Pending"}.get(
        str(value), ""
    )


def _dispositions_content_digest(dispositions: dict[str, Any]) -> str:
    """Calculate the Rust-owned semantic digest after index binding injection."""
    fields = [
        str(dispositions["schema_version"]),
        dispositions["candidate_id"],
        dispositions["construction_id"],
        dispositions["construction_digest"],
        dispositions["evidence_index_digest"],
        _rust_debug_status(dispositions["status"]),
    ]
    rows = sorted(dispositions["dispositions"], key=lambda row: row["axis"])
    for row in rows:
        fields.extend(
            [
                row["axis"],
                row["owner_role"],
                row["verifier_role"],
                _rust_debug_status(row["status"]),
                row["construction_digest"],
                row["evidence_index_digest"],
                row["scope_digest"],
                row.get("signed_artifact_digest") or "",
                row.get("manual_verification_digest") or "",
                row["reason"],
            ]
        )
    return hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()


def _read_json(path: Path, *, root: Path) -> tuple[dict[str, Any], bytes]:
    try:
        read = qualification_replay.read_once(path, root=root)
    except qualification_replay.ReplayError as exc:
        raise U7BClosureGateError(f"cannot securely read U7-B input {path}: {exc}") from exc
    raw = read.data
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise U7BClosureGateError(f"invalid U7-B JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise U7BClosureGateError(f"U7-B JSON root must be an object: {path}")
    return value, raw


def _relative_input(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise U7BClosureGateError(f"U7-B input path must be repo-relative: {relative}")
    return root / "power_pcb_dataset/qualification/ct07_t2" / candidate


def _load_package(index_path: Path, root: Path) -> dict[str, Any]:
    index, index_raw = _read_json(index_path, root=root)
    u7_b = index.get("u7_b")
    if not isinstance(u7_b, dict):
        raise U7BClosureGateError("evidence index has no U7-B binding")
    identity, _ = _read_json(root / "power_pcb_dataset/qualification/ct07_t2/identity_eligibility.json", root=root)
    u7_a = index.get("u7_a")
    if not isinstance(u7_a, dict) or u7_a.get("identity_package") != "identity_eligibility.json":
        raise U7BClosureGateError("evidence index has no canonical U7-A identity binding")
    if u7_a.get("identity_digest") != identity.get("identity_digest"):
        raise U7BClosureGateError("evidence index U7-A identity digest does not match the package")
    fault, fault_raw = _read_json(_relative_input(root, u7_b.get("single_fault_analysis", "")), root=root)
    dispositions, dispositions_raw = _read_json(_relative_input(root, u7_b.get("internal_dispositions", "")), root=root)
    actual_index_digest = hashlib.sha256(index_raw).hexdigest()
    actual_fault_digest = hashlib.sha256(fault_raw).hexdigest()
    actual_dispositions_digest = hashlib.sha256(dispositions_raw).hexdigest()
    dependencies = u7_b.get("dependencies")
    if not isinstance(dependencies, dict):
        raise U7BClosureGateError("U7-B dependency records are required")
    for name in ("u5", "u6", "u9"):
        if not isinstance(dependencies.get(name), dict):
            raise U7BClosureGateError(f"U7-B dependency {name} is missing")
    # The digest of the evidence index is deliberately computed from bytes,
    # while the index may name it only indirectly; this avoids self-hashing.
    dispositions["evidence_index_digest"] = actual_index_digest
    for row in dispositions.get("dispositions", []):
        if isinstance(row, dict):
            row["evidence_index_digest"] = actual_index_digest
    # The file's bytes are bound separately below. The semantic digest is
    # computed over this runtime-bound projection so the evidence index can
    # be self-referential only through a derived, non-self-hashed value.
    dispositions["dispositions_digest"] = _dispositions_content_digest(dispositions)
    return {
        "schema_version": 1,
        "candidate_id": u7_b.get("candidate_id", identity.get("candidate_id")),
        "construction_id": u7_b.get("construction_id"),
        "construction_digest": u7_b.get("construction_digest"),
        "construction_projection_digest": u7_b.get("construction_projection_digest"),
        "allowed_transform_policy_digest": u7_b.get("allowed_transform_policy_digest"),
        "evidence_index_digest": actual_index_digest,
        "fault_analysis_file_digest": actual_fault_digest,
        "dispositions_file_digest": actual_dispositions_digest,
        "u7a": identity,
        "u5": dependencies["u5"],
        "u6": dependencies["u6"],
        "u9": dependencies["u9"],
        "fault_analysis": fault,
        "internal_dispositions": dispositions,
        "raw_evidence": [
            {"id": "evidence-index", "sha256": actual_index_digest, "bytes": list(index_raw)},
            {"id": "single-fault-analysis", "sha256": actual_fault_digest, "bytes": list(fault_raw)},
            {"id": "internal-dispositions", "sha256": actual_dispositions_digest, "bytes": list(dispositions_raw)},
        ],
    }


def replay(index_path: Path = DEFAULT_INDEX, output_path: Path | None = None, *, repo_root: Path = REPO_ROOT) -> str:
    package = _load_package(Path(index_path), repo_root)
    if temper_quality_oracle is None:
        raise U7BClosureGateError("temper_quality_oracle is unavailable; rebuild extensions before U7-B replay")
    evaluator = getattr(temper_quality_oracle, "evaluate_ct07_u7_b_closure_json", None)
    if not callable(evaluator):
        raise U7BClosureGateError("CT07 U7-B Rust evaluator registration is unavailable")
    try:
        result = evaluator(json.dumps(package, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise U7BClosureGateError(f"CT07 U7-B Rust evaluator rejected package: {exc}") from exc
    try:
        decision = json.loads(result)
    except json.JSONDecodeError as exc:
        raise U7BClosureGateError(f"Rust U7-B decision is not JSON: {exc}") from exc
    if not isinstance(decision, dict) or decision.get("candidate_id") != package["candidate_id"]:
        raise U7BClosureGateError("U7-B decision does not preserve candidate identity")
    rendered = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if output_path is not None:
        output = Path(output_path)
        output_root = repo_root / "power_pcb_dataset/qualification/ct07_t2"
        try:
            output.resolve().relative_to(output_root.resolve())
        except ValueError as exc:
            raise U7BClosureGateError("U7-B output must remain under the CT07 qualification root") from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            qualification_replay.publish_atomic(output, rendered, root=repo_root)
        except qualification_replay.ReplayError as exc:
            raise U7BClosureGateError(f"cannot publish U7-B decision: {exc}") from exc
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        rendered = replay(args.index, args.output)
    except U7BClosureGateError as exc:
        print(f"CT07 U7-B CLOSURE GATE ERROR: {exc}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
