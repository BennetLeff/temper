#!/usr/bin/env python3
"""Offline replay gate for the ISO7741 gate-drive qualification package.

This script is intentionally an argument and exit-code shim.  The Rust
extension owns the package schema, evidence completeness, lifecycle, and
verdict.  Secure reads, protected-set checks, and atomic publication are
centralized in :mod:`scripts._lib.qualification_replay`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:  # package import for tests; direct-script import for the CLI
    from scripts._lib import qualification_replay
except ImportError:  # pragma: no cover - exercised by direct CLI invocation
    from _lib import qualification_replay


REPO_ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_ROOT = Path("elec/qualification/iso7741_gate_drive")
OUTPUT_ROOT = Path("power_pcb_dataset/qualification/iso7741_gate_drive")
DEFAULT_MANIFEST = REPO_ROOT / OUTPUT_ROOT / "evidence_index.json"
DEFAULT_RECEIPTS = REPO_ROOT / OUTPUT_ROOT / "source_receipts.json"
DEFAULT_SUBMISSION_INDEX = REPO_ROOT / OUTPUT_ROOT / "authority" / "submission_index.json"
DEFAULT_PRELIMINARY_RULING = REPO_ROOT / OUTPUT_ROOT / "authority" / "preliminary_ruling.json"
DEFAULT_PRELIMINARY_DECISION = REPO_ROOT / OUTPUT_ROOT / "preliminary_decision.json"
PROTECTED_PATHS = (
    "pcb/temper.kicad_pcb",
    "power_pcb_dataset/drc_ceiling.json",
    "elec/domain_manifest.yaml",
    "docs/ENVIRONMENTAL_SPEC.md",
    "packages/temper-placer/src/temper_placer/core/isolation_constants.py",
)
CANDIDATE_EXPORTS = {
    "default.csv": "iso7741_gate_drive.csv",
    "default.net": "iso7741_gate_drive.net",
}
_SHA256_LENGTH = 64
_SAFE_ARTIFACT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

QualificationGateError = qualification_replay.ReplayError


def _candidate_exports(project_root: Path) -> dict[str, str]:
    return qualification_replay.normalized_text_exports(
        project_root,
        CANDIDATE_EXPORTS,
        root_token=CANDIDATE_ROOT.as_posix(),
    )


def verify_candidate_build(project_root: Path, repo_root: Path = REPO_ROOT) -> None:
    canonical_root = repo_root / OUTPUT_ROOT / "generated"
    for name, actual in _candidate_exports(project_root).items():
        with (canonical_root / name).open(encoding="utf-8", newline="") as handle:
            expected = handle.read()
        if actual != expected:
            raise QualificationGateError(f"clean ISO7741 candidate build differs: {name}")


def publish_candidate_build(project_root: Path, repo_root: Path = REPO_ROOT) -> None:
    canonical_root = repo_root / OUTPUT_ROOT / "generated"
    qualification_replay.publish_text_exports(
        _candidate_exports(project_root),
        canonical_root,
        root=repo_root,
        protected_paths=PROTECTED_PATHS,
    )


def _parse_manifest_bytes(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationGateError(f"invalid ISO7741 manifest JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationGateError("ISO7741 manifest root must be a JSON object")
    return value


def _receipt_path(manifest_path: Path) -> Path:
    return manifest_path.with_name("source_receipts.json")


def _validate_source_receipts(manifest: Mapping[str, Any], repo_root: Path, manifest_path: Path) -> None:
    """Read source receipts once and verify local source bytes offline.

    A missing/empty receipt file is valid for the initial skeleton but cannot
    manufacture a favorable Rust result.  URL references are identifiers only;
    replay never performs network I/O.
    """

    receipts_path = _receipt_path(manifest_path)
    try:
        receipt_read = qualification_replay.read_once(receipts_path, root=repo_root)
    except QualificationGateError as exc:
        raise QualificationGateError(f"cannot read ISO7741 source receipts: {exc}") from exc
    try:
        receipts = json.loads(receipt_read.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationGateError(f"invalid ISO7741 source receipts JSON: {exc}") from exc
    if not isinstance(receipts, dict):
        raise QualificationGateError("ISO7741 source receipts root must be an object")
    if receipts.get("schema_version") != 1:
        raise QualificationGateError("ISO7741 source receipts schema version is unsupported")
    sources = receipts.get("sources", [])
    if not isinstance(sources, list):
        raise QualificationGateError("ISO7741 source receipts.sources must be a list")
    if sources:
        owners = receipts.get("owners", receipts.get("owner_signoffs"))
        if isinstance(owners, dict):
            owner_ids = set(owners)
        elif isinstance(owners, list):
            owner_ids = {
                item
                if isinstance(item, str)
                else item.get("owner_id")
                if isinstance(item, dict)
                else None
                for item in owners
            }
        else:
            owner_ids = set()
        if not {"A6", "A7"}.issubset(owner_ids):
            raise QualificationGateError(
                "ISO7741 source receipts require A6 and A7 ownership"
            )
    protected = qualification_replay.snapshot_paths(repo_root, PROTECTED_PATHS)
    protected_inodes = {
        (entry.identity[0], entry.identity[1])
        for entry in protected.values()
        if entry.identity is not None
    }
    for source in sources:
        if not isinstance(source, dict):
            raise QualificationGateError("ISO7741 source receipt must be an object")
        path = source.get("path")
        digest = source.get("sha256")
        revision = source.get("revision", source.get("document_revision"))
        review_state = str(source.get("review_state", "current")).strip().lower()
        if not isinstance(path, str) or not path.strip():
            raise QualificationGateError("ISO7741 source receipt path is required")
        if (
            not isinstance(digest, str)
            or len(digest) != _SHA256_LENGTH
            or any(char not in "0123456789abcdefABCDEF" for char in digest)
        ):
            raise QualificationGateError(f"ISO7741 source receipt {path}: invalid SHA-256")
        if (
            not isinstance(revision, str)
            or not revision.strip()
            or revision.strip().lower() in {"unknown", "tbd", "pending", "placeholder"}
        ):
            raise QualificationGateError(f"ISO7741 source receipt {path}: revision is required")
        if review_state in {"future", "superseded"}:
            raise QualificationGateError(
                f"ISO7741 source receipt {path}: review state is {review_state}"
            )
        try:
            relative = Path(path)
            if relative.is_absolute() or ".." in relative.parts:
                raise QualificationGateError(f"ISO7741 source path escapes repository: {path}")
            candidate_path = repo_root / relative
            read = qualification_replay.read_once(
                candidate_path,
                root=repo_root,
                expected_sha256=digest,
                reject_inodes=protected_inodes,
            )
        except QualificationGateError as exc:
            raise QualificationGateError(f"ISO7741 source receipt {path}: {exc}") from exc
        if not read.path.is_relative_to(repo_root / CANDIDATE_ROOT):
            raise QualificationGateError(
                f"ISO7741 source must live below candidate workspace: {path}"
            )


def _validate_owner_signoffs_sidecar(
    manifest: Mapping[str, Any], repo_root: Path, manifest_path: Path
) -> None:
    """Ensure the human-readable sign-off index cannot diverge from the DAG."""

    sidecar_path = manifest_path.with_name("owner_signoffs.json")
    read = qualification_replay.read_once(sidecar_path, root=repo_root)
    try:
        sidecar = json.loads(read.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationGateError(f"invalid ISO7741 owner sign-offs JSON: {exc}") from exc
    if not isinstance(sidecar, dict) or sidecar.get("schema_version") != 1:
        raise QualificationGateError("ISO7741 owner sign-offs schema version is unsupported")
    candidate = manifest.get("candidate")
    if not isinstance(candidate, Mapping):
        raise QualificationGateError("ISO7741 candidate is required for owner sign-offs")
    if (
        sidecar.get("candidate_id") != candidate.get("candidate_id")
        or sidecar.get("envelope_digest") != candidate.get("envelope_digest")
        or sidecar.get("evidence_root_digest") != manifest.get("evidence_root_digest")
    ):
        raise QualificationGateError("ISO7741 owner sign-offs identity diverges from evidence index")
    rows = sidecar.get("signoffs")
    embedded = manifest.get("owner_signoffs")
    if not isinstance(rows, list) or not isinstance(embedded, list):
        raise QualificationGateError("ISO7741 owner sign-offs must be lists")
    by_role = {
        item.get("role"): item
        for item in embedded
        if isinstance(item, Mapping) and isinstance(item.get("role"), str)
    }
    if len(rows) != len(by_role):
        raise QualificationGateError("ISO7741 owner sign-offs row count diverges from evidence index")
    for row in rows:
        if not isinstance(row, Mapping) or row.get("role") not in by_role:
            raise QualificationGateError("ISO7741 owner sign-offs contain an unknown role")
        source = by_role[row["role"]]
        for field in ("status", "scope_node_id", "scope_digest", "signature_artifact"):
            if row.get(field) != source.get(field):
                raise QualificationGateError(
                    f"ISO7741 owner sign-off {row['role']} diverges in {field}"
                )


def _validate_base_protected_set(manifest: Mapping[str, Any], repo_root: Path) -> None:
    """Require a resolvable base commit and exact protected-input pins."""

    commit = manifest.get("base_commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(
        char not in "0123456789abcdef" for char in commit
    ):
        raise QualificationGateError("ISO7741 manifest base_commit must be a 40-character lowercase commit")
    try:
        kind = subprocess.run(
            ["git", "cat-file", "-t", commit],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QualificationGateError(f"ISO7741 base_commit does not resolve: {commit}") from exc
    if kind != "commit":
        raise QualificationGateError(f"ISO7741 base_commit is not a commit: {commit}")
    raw_inputs = manifest.get("protected_inputs")
    if not isinstance(raw_inputs, list):
        raise QualificationGateError("ISO7741 manifest protected_inputs must be a list")
    pins: dict[str, str] = {}
    for item in raw_inputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise QualificationGateError("ISO7741 protected input requires path and sha256")
        path = item["path"]
        digest = item.get("sha256")
        if path in pins or not isinstance(digest, str) or len(digest) != _SHA256_LENGTH:
            raise QualificationGateError(f"invalid ISO7741 protected input pin: {path!r}")
        pins[path] = digest.lower()
    if tuple(sorted(pins)) != tuple(sorted(PROTECTED_PATHS)):
        raise QualificationGateError("ISO7741 protected_inputs must pin exactly the production set")
    for path in PROTECTED_PATHS:
        relative = Path(path)
        try:
            base = subprocess.run(
                ["git", "show", f"{commit}:{relative.as_posix()}"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise QualificationGateError(
                f"ISO7741 protected input is absent from base commit: {path}"
            ) from exc
        base_digest = hashlib.sha256(base).hexdigest()
        if pins[path] != base_digest:
            raise QualificationGateError(f"ISO7741 protected pin does not match base commit: {path}")
        current = qualification_replay.read_once(repo_root / relative, root=repo_root).sha256
        if current != pins[path]:
            raise QualificationGateError(f"ISO7741 protected input pin mismatch: {path}")


def _validate_output(
    manifest: Mapping[str, Any], decision: Mapping[str, Any], *, preliminary: bool = False
) -> None:
    """Require the Rust response to identify the replayed ISO envelope."""

    for field in ("schema_version", "candidate_id", "envelope_digest"):
        if field not in decision:
            raise QualificationGateError(f"ISO7741 Rust decision missing {field}")
    if decision.get("schema_version") != manifest.get("schema_version"):
        raise QualificationGateError("ISO7741 Rust decision schema does not match manifest")
    candidate = manifest.get("candidate")
    if not isinstance(candidate, dict):
        raise QualificationGateError("ISO7741 manifest candidate is missing")
    if decision.get("candidate_id") != candidate.get("candidate_id"):
        raise QualificationGateError("ISO7741 Rust decision candidate identity mismatch")
    if decision.get("envelope_digest") != candidate.get("envelope_digest"):
        raise QualificationGateError("ISO7741 Rust decision envelope digest mismatch")
    if preliminary:
        for field in ("submission_digest", "internal_stage"):
            if field not in decision:
                raise QualificationGateError(
                    f"ISO7741 preliminary decision missing {field}"
                )
        if "final_production" in decision or "production_construction_approved" in decision:
            raise QualificationGateError(
                "ISO7741 preliminary decision cannot contain a final-production field"
            )


def _repo_relative(path: str | Path) -> Path:
    relative = Path(path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise QualificationGateError(f"ISO7741 path must be repo-relative: {path!r}")
    return relative


def _payload_from_evidence_index(
    manifest: Mapping[str, Any],
    repo_root: Path,
    observations: dict[str, qualification_replay.ReadOnce] | None = None,
    *,
    allow_authority_artifacts: bool = False,
) -> dict[str, Any]:
    """Attach immutable evidence/signature bytes to the Rust input.

    The index is metadata only.  Rust receives the bytes captured by the
    sealed replay boundary, verifies their digests and computes the DAG root;
    this helper does not decide any evidence status or lifecycle result.
    """

    payload = dict(manifest)
    raw_objects = manifest.get("evidence_objects", [])
    if not isinstance(raw_objects, list):
        raise QualificationGateError("ISO7741 evidence_objects must be a list")
    raw_signoffs = manifest.get("owner_signoffs", [])
    if not isinstance(raw_signoffs, list):
        raise QualificationGateError("ISO7741 owner_signoffs must be a list")
    candidate_root = (repo_root / CANDIDATE_ROOT).resolve()
    output_root = (repo_root / OUTPUT_ROOT).resolve()
    protected = qualification_replay.snapshot_paths(repo_root, PROTECTED_PATHS)
    protected_inodes = {
        (entry.identity[0], entry.identity[1])
        for entry in protected.values()
        if entry.identity is not None
    }

    def read_candidate(entry: Mapping[str, Any], label: str) -> tuple[str, qualification_replay.ReadOnce]:
        item_id = entry.get("id")
        path = entry.get("path")
        if not isinstance(item_id, str) or not _SAFE_ARTIFACT_ID.fullmatch(item_id):
            raise QualificationGateError(f"ISO7741 {label} has an invalid id")
        if not isinstance(path, str):
            raise QualificationGateError(f"ISO7741 {label} requires path")
        relative = _repo_relative(path)
        absolute = repo_root / relative
        try:
            resolved = absolute.resolve(strict=False)
            if not (
                resolved.is_relative_to(candidate_root)
                or resolved.is_relative_to(output_root)
            ):
                raise ValueError
        except (OSError, RuntimeError, ValueError) as exc:
            raise QualificationGateError(
                f"ISO7741 evidence must live below candidate/output workspace: {path}"
            ) from exc
        read = qualification_replay.read_once(
            absolute, root=repo_root, reject_inodes=protected_inodes
        )
        if observations is not None:
            observations[relative.as_posix()] = read
        declared = entry.get("sha256")
        if declared is not None and declared != read.sha256:
            raise QualificationGateError(
                f"ISO7741 {label} digest mismatch: {item_id}"
            )
        return item_id, read

    objects: list[dict[str, Any]] = []
    object_ids: set[str] = set()
    for raw in raw_objects:
        if not isinstance(raw, Mapping):
            raise QualificationGateError("ISO7741 evidence object must be an object")
        item_id, read = read_candidate(raw, "evidence object")
        if item_id in object_ids:
            raise QualificationGateError(f"duplicate ISO7741 evidence object: {item_id}")
        object_ids.add(item_id)
        item = dict(raw)
        item["id"] = item_id
        item["sha256"] = read.sha256
        item["bytes"] = list(read.data)
        objects.append(item)
    payload["evidence_objects"] = sorted(objects, key=lambda item: item["id"])

    referenced_signatures: set[str] = set()
    signatures: list[dict[str, Any]] = []
    for signoff in raw_signoffs:
        if not isinstance(signoff, Mapping):
            raise QualificationGateError("ISO7741 owner sign-off must be an object")
        artifact = signoff.get("signature_artifact")
        if artifact is None:
            continue
        if not isinstance(artifact, Mapping):
            raise QualificationGateError("ISO7741 signature_artifact must be an object")
        artifact_id = artifact.get("artifact_id", artifact.get("id"))
        path = artifact.get("path")
        if not isinstance(artifact_id, str) or not _SAFE_ARTIFACT_ID.fullmatch(artifact_id):
            raise QualificationGateError("ISO7741 signature artifact has an invalid id")
        if not isinstance(path, str):
            raise QualificationGateError("ISO7741 signature artifact requires path")
        relative = _repo_relative(path)
        absolute = repo_root / relative
        if absolute.is_symlink():
            raise QualificationGateError(
                f"refusing symlink signature artifact: {path}"
            )
        try:
            absolute.resolve(strict=False).relative_to(output_root / "authority" / "signed")
        except (OSError, RuntimeError, ValueError) as exc:
            raise QualificationGateError(
                f"ISO7741 signature artifact must live below authority/signed: {path}"
            ) from exc
        read = qualification_replay.read_once(
            absolute, root=repo_root, reject_inodes=protected_inodes
        )
        if observations is not None:
            observations[relative.as_posix()] = read
        declared = artifact.get("sha256")
        if declared is not None and declared != read.sha256:
            raise QualificationGateError(
                f"ISO7741 signature artifact digest mismatch: {artifact_id}"
            )
        if artifact_id in referenced_signatures:
            raise QualificationGateError(
                f"duplicate ISO7741 signature artifact: {artifact_id}"
            )
        referenced_signatures.add(artifact_id)
        item = dict(artifact)
        item["artifact_id"] = artifact_id
        item["sha256"] = read.sha256
        item["bytes"] = list(read.data)
        signatures.append(item)
    signed_root = output_root / "authority" / "signed"
    if signed_root.exists():
        if signed_root.is_symlink() or not signed_root.is_dir():
            raise QualificationGateError("ISO7741 authority/signed must be a real directory")
        for path in sorted(signed_root.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise QualificationGateError(
                    f"ISO7741 signed artifact is not a regular file: {path.name}"
                )
            if not allow_authority_artifacts and path.name not in {
                Path(str(signoff.get("signature_artifact", {}).get("path", ""))).name
                for signoff in raw_signoffs
                if isinstance(signoff, Mapping)
                and isinstance(signoff.get("signature_artifact"), Mapping)
            }:
                raise QualificationGateError(
                    f"unreferenced ISO7741 signed artifact: {path.name}"
                )
    payload["signature_artifacts"] = sorted(
        signatures, key=lambda item: item["artifact_id"]
    )
    return payload


def _read_json_below_output(
    path: Path,
    repo_root: Path,
    observations: dict[str, qualification_replay.ReadOnce],
    label: str,
) -> dict[str, Any]:
    """Read one U7 authority object through the sealed replay boundary."""

    output_root = (repo_root / OUTPUT_ROOT).resolve()
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(output_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise QualificationGateError(
            f"ISO7741 {label} must live below the qualification output root: {path}"
        ) from exc
    read = qualification_replay.read_once(path, root=repo_root)
    observations[path.relative_to(repo_root).as_posix()] = read
    try:
        value = json.loads(read.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationGateError(f"invalid ISO7741 {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationGateError(f"ISO7741 {label} root must be an object")
    return value


def _payload_from_preliminary_authority(
    payload: Mapping[str, Any],
    manifest: Mapping[str, Any],
    repo_root: Path,
    manifest_path: Path,
    observations: dict[str, qualification_replay.ReadOnce],
) -> dict[str, Any]:
    """Attach the provider-neutral submission and independently captured A8 input."""

    output_root = repo_root / OUTPUT_ROOT
    submission_name = manifest.get("submission_index", "authority/submission_index.json")
    ruling_name = manifest.get("preliminary_ruling", "authority/preliminary_ruling.json")
    if not isinstance(submission_name, str) or not isinstance(ruling_name, str):
        raise QualificationGateError("ISO7741 preliminary authority paths must be strings")

    def authority_path(name: str) -> Path:
        relative = Path(name)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise QualificationGateError(f"ISO7741 authority path is not relative: {name!r}")
        return output_root / relative

    submission_path = authority_path(submission_name)
    ruling_path = authority_path(ruling_name)
    submission = _read_json_below_output(
        submission_path, repo_root, observations, "submission index"
    )
    ruling = _read_json_below_output(
        ruling_path, repo_root, observations, "preliminary ruling"
    )

    artifact = ruling.get("receipt_artifact")
    allowed_signed_names = {
        Path(str(signoff.get("signature_artifact", {}).get("path", ""))).name
        for signoff in payload.get("owner_signoffs", [])
        if isinstance(signoff, Mapping)
        and isinstance(signoff.get("signature_artifact"), Mapping)
    }
    if artifact is not None:
        if not isinstance(artifact, Mapping):
            raise QualificationGateError("ISO7741 receipt_artifact must be an object or null")
        artifact_path = artifact.get("path")
        if not isinstance(artifact_path, str):
            raise QualificationGateError("ISO7741 receipt artifact path is required")
        signed_root = (output_root / "authority" / "signed").resolve()
        signed_path = repo_root / _repo_relative(artifact_path)
        try:
            signed_path.resolve(strict=False).relative_to(signed_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise QualificationGateError(
                f"ISO7741 receipt artifact must live below authority/signed: {artifact_path}"
            ) from exc
        artifact_read = qualification_replay.read_once(signed_path, root=repo_root)
        observations[artifact_read.path.relative_to(repo_root).as_posix()] = artifact_read
        declared = artifact.get("sha256")
        if declared is not None and declared != artifact_read.sha256:
            raise QualificationGateError("ISO7741 receipt artifact digest mismatch")
        captured = dict(artifact)
        captured["sha256"] = artifact_read.sha256
        captured["bytes"] = list(artifact_read.data)
        ruling["receipt_artifact"] = captured
        allowed_signed_names.add(signed_path.name)

    signed_root = output_root / "authority" / "signed"
    if signed_root.exists():
        if signed_root.is_symlink() or not signed_root.is_dir():
            raise QualificationGateError("ISO7741 authority/signed must be a real directory")
        for path in sorted(signed_root.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise QualificationGateError(
                    f"ISO7741 signed artifact is not a regular file: {path.name}"
                )
            if path.name not in allowed_signed_names:
                raise QualificationGateError(
                    f"unreferenced ISO7741 signed artifact: {path.name}"
                )

    attached = dict(payload)
    attached["submission_index"] = submission
    attached["preliminary_ruling"] = ruling
    return attached


def _evaluate_in_rust(manifest: Mapping[str, Any]) -> str:
    """Call the uniquely registered Rust evaluator; Python owns no verdict."""

    try:
        import temper_quality_oracle
    except ImportError as exc:
        raise QualificationGateError(
            "temper_quality_oracle is unavailable; rebuild the pyo3 extension before replay"
        ) from exc
    evaluator = getattr(
        temper_quality_oracle,
        "evaluate_iso7741_gate_drive_qualification_json",
        None,
    )
    if not callable(evaluator):
        raise QualificationGateError("ISO7741 Rust evaluator registration is unavailable")
    try:
        payload = _payload_from_evidence_index(manifest, REPO_ROOT)
        return evaluator(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise QualificationGateError(f"ISO7741 Rust evaluator rejected manifest: {exc}") from exc


def _evaluate_in_rust_with_root(
    manifest: Mapping[str, Any],
    repo_root: Path,
    observations: dict[str, qualification_replay.ReadOnce],
    *,
    preliminary: bool = False,
    manifest_path: Path | None = None,
) -> str:
    """Evaluate an index after the sealed runner captured referenced bytes."""

    try:
        import temper_quality_oracle
    except ImportError as exc:
        raise QualificationGateError(
            "temper_quality_oracle is unavailable; rebuild the pyo3 extension before replay"
        ) from exc
    evaluator = getattr(
        temper_quality_oracle,
        "evaluate_iso7741_gate_drive_qualification_json",
        None,
    )
    if not callable(evaluator):
        raise QualificationGateError("ISO7741 Rust evaluator registration is unavailable")
    payload = _payload_from_evidence_index(
        manifest,
        repo_root,
        observations,
        allow_authority_artifacts=preliminary,
    )
    if preliminary:
        payload = _payload_from_preliminary_authority(
            payload,
            manifest,
            repo_root,
            manifest_path or (repo_root / OUTPUT_ROOT / "evidence_index.json"),
            observations,
        )
    try:
        return evaluator(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise QualificationGateError(f"ISO7741 Rust evaluator rejected manifest: {exc}") from exc


def replay(
    manifest_path: Path = DEFAULT_MANIFEST,
    output_path: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    preliminary: bool = False,
) -> str:
    """Replay one package and optionally publish below its explicit output root."""

    manifest_path = Path(manifest_path)
    if output_path is None:
        output_path = repo_root / (
            DEFAULT_PRELIMINARY_DECISION.relative_to(REPO_ROOT)
            if preliminary
            else OUTPUT_ROOT / "internal_decision.json"
        )
    else:
        output_path = Path(output_path)
        if not output_path.is_absolute():
            output_path = repo_root / output_path
    candidate_root = repo_root / CANDIDATE_ROOT
    output_root = repo_root / OUTPUT_ROOT
    try:
        output_path.resolve().relative_to(output_root.resolve())
    except (OSError, ValueError) as exc:
        raise QualificationGateError(
            f"ISO7741 output escapes qualification output root: {output_path}"
        ) from exc

    evidence_observations: dict[str, qualification_replay.ReadOnce] = {}

    def preflight(manifest: Mapping[str, Any]) -> None:
        _validate_base_protected_set(manifest, repo_root)
        _validate_source_receipts(manifest, repo_root, manifest_path)
        _validate_owner_signoffs_sidecar(manifest, repo_root, manifest_path)
        if not candidate_root.resolve().is_relative_to(repo_root.resolve()):
            raise QualificationGateError("ISO7741 candidate workspace escapes repository")

    return qualification_replay.sealed_replay(
        manifest_path,
        output_path,
        root=repo_root,
        protected_paths=PROTECTED_PATHS,
        output_root=output_root,
        parse_manifest=_parse_manifest_bytes,
        evaluate=lambda manifest: _evaluate_in_rust_with_root(
            manifest,
            repo_root,
            evidence_observations,
            preliminary=preliminary,
            manifest_path=manifest_path,
        ),
        validate_output=lambda manifest, decision: _validate_output(
            manifest, decision, preliminary=preliminary
        ),
        preflight=preflight,
        observations=evidence_observations,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    candidate_mode = parser.add_mutually_exclusive_group()
    candidate_mode.add_argument("--verify-candidate-build", type=Path)
    candidate_mode.add_argument("--publish-candidate-build", type=Path)
    parser.add_argument(
        "--preliminary",
        action="store_true",
        help="evaluate the U7 preliminary authority packet and publish preliminary_decision.json",
    )
    args = parser.parse_args(argv)
    try:
        if args.verify_candidate_build is not None:
            verify_candidate_build(args.verify_candidate_build)
            print("ISO7741 candidate build matches canonical exports")
            return 0
        if args.publish_candidate_build is not None:
            publish_candidate_build(args.publish_candidate_build)
            print("published ISO7741 canonical candidate exports")
            return 0
        result = replay(args.manifest, args.output, preliminary=args.preliminary)
    except QualificationGateError as exc:
        print(f"ISO7741 QUALIFICATION GATE ERROR: {exc}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.write(result)
    else:
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
