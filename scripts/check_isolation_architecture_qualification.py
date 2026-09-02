#!/usr/bin/env python3
"""Replay the committed isolation-architecture qualification manifest.

This is intentionally a small orchestration gate.  JSON parsing, protected
input hashing, and output I/O live here; candidate validation and verdict
aggregation are owned by ``temper_quality_oracle``'s Rust evaluator.

The gate is offline: URLs in the manifest identify reviewed evidence but are
never fetched during replay.  A run is refused if the five production inputs
move, if the manifest does not pin exactly those inputs, or if the requested
output would overwrite a protected input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:  # package import for tests; direct-script import for the CLI
    from scripts._lib import qualification_replay
except ImportError:  # pragma: no cover - exercised by direct CLI invocation
    from _lib import qualification_replay

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "power_pcb_dataset" / "isolation_architecture_candidates.json"

PROTECTED_PATHS = (
    "pcb/temper.kicad_pcb",
    "power_pcb_dataset/drc_ceiling.json",
    "elec/domain_manifest.yaml",
    "docs/ENVIRONMENTAL_SPEC.md",
    "packages/temper-placer/src/temper_placer/core/isolation_constants.py",
)
_SHA256_LENGTH = 64
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")


QualificationGateError = qualification_replay.ReplayError


def sha256_file(path: Path, *, root: Path | None = None) -> str:
    """Compatibility shim; the sealed helper performs the actual read/hash."""

    if root is None:
        root = path.parent
    return qualification_replay.read_once(path, root=root).sha256


def _repo_relative(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise QualificationGateError(f"protected input path must be repo-relative: {path!r}")
    return candidate


def protected_hashes(manifest: dict[str, Any], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """Validate and return current hashes for the plan-owned protected set."""

    pins = _protected_pins(manifest)
    current = {
        path: qualification_replay.read_once(
            repo_root / _repo_relative(path), root=repo_root
        ).sha256
        for path in PROTECTED_PATHS
    }
    mismatches = [
        f"{path}: expected {pins[path]}, found {current[path]}"
        for path in PROTECTED_PATHS
        if current[path] != pins[path]
    ]
    if mismatches:
        raise QualificationGateError("protected input pin mismatch: " + "; ".join(mismatches))
    return current


def _protected_pins(manifest: dict[str, Any]) -> dict[str, str]:
    """Return the validated manifest pins without reading working-tree files."""

    raw_inputs = manifest.get("protected_inputs")
    if not isinstance(raw_inputs, list):
        raise QualificationGateError("manifest protected_inputs must be a list")
    pins: dict[str, str] = {}
    for item in raw_inputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise QualificationGateError("each protected input must have a path and sha256")
        path = item["path"]
        digest = item.get("sha256")
        if (
            path in pins
            or not isinstance(digest, str)
            or len(digest) != _SHA256_LENGTH
            or any(char not in "0123456789abcdefABCDEF" for char in digest)
        ):
            raise QualificationGateError(f"invalid protected input pin: {path!r}")
        pins[path] = digest.lower()
    if tuple(sorted(pins)) != tuple(sorted(PROTECTED_PATHS)):
        raise QualificationGateError(
            "manifest protected_inputs must pin exactly the plan-owned set: "
            + ", ".join(PROTECTED_PATHS)
        )
    return pins


def _base_tree_hashes(manifest: dict[str, Any], repo_root: Path) -> dict[str, str]:
    """Return protected-input hashes from the manifest's resolved Git commit.

    The campaign pin must identify the exact base tree, not merely happen to
    match the current working tree.  All Git arguments are passed as argv so
    neither a path nor a commit can become shell syntax.
    """

    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise QualificationGateError("manifest provenance must be an object")
    commit = provenance.get("commit")
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise QualificationGateError(
            "manifest provenance.commit must be a resolvable 40-character lowercase commit"
        )
    try:
        resolved = subprocess.run(
            ["git", "cat-file", "-t", commit],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QualificationGateError(
            f"manifest provenance.commit does not resolve: {commit}"
        ) from exc
    if resolved != "commit":
        raise QualificationGateError(
            f"manifest provenance.commit is not a commit object: {commit}"
        )

    pins = _protected_pins(manifest)
    base_hashes: dict[str, str] = {}
    for path in PROTECTED_PATHS:
        relative = _repo_relative(path)
        try:
            content = subprocess.run(
                ["git", "show", f"{commit}:{relative.as_posix()}"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise QualificationGateError(
                f"protected input {path} is unavailable in provenance base {commit}"
            ) from exc
        base_hashes[path] = hashlib.sha256(content).hexdigest()
        if pins[path] != base_hashes[path]:
            raise QualificationGateError(
                f"manifest pin for {path} does not match provenance base {commit}: "
                f"expected {base_hashes[path]}, found {pins[path]}"
            )
    return base_hashes


def _geometry_source(axis: dict[str, Any]) -> dict[str, Any] | None:
    """Read the canonical geometry source field, accepting old aliases on input."""

    for field in ("source", "geometry_source", "source_reference"):
        value = axis.get(field)
        if value is not None:
            return value
    return None


def _provenance_commit(manifest: dict[str, Any]) -> str:
    provenance = manifest.get("provenance")
    commit = provenance.get("commit") if isinstance(provenance, dict) else None
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise QualificationGateError(
            "manifest provenance.commit must be a resolvable 40-character lowercase commit"
        )
    return commit


def _git_source_bytes(repo_root: Path, commit: str, path: Path) -> bytes | None:
    """Return base-tree bytes, or ``None`` when the path is not in that tree."""

    try:
        return subprocess.run(
            ["git", "show", f"{commit}:{path.as_posix()}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _validate_geometry_sources(manifest: dict[str, Any], repo_root: Path) -> None:
    """Bind every measured straight-corridor result to immutable base evidence.

    The evaluator cannot inspect repository bytes, so this orchestration check
    closes that boundary: a source must be a local file whose current bytes
    match its digest, and a source that already existed in the provenance base
    must have the same bytes there.  A newly introduced source is acceptable
    only for an explicitly pending axis; it can never establish a pass/fail
    result in the same campaign.
    """

    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        return
    commit = _provenance_commit(manifest)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get("candidate_id", "<unknown>")
        references = [candidate.get("datasheet"), *(candidate.get("certification_references") or [])]
        for axis in candidate.get("axes", []):
            if not isinstance(axis, dict) or axis.get("code") != "geometry.straight_corridor":
                continue
            status = axis.get("status")
            source = _geometry_source(axis)
            if status in {"pass", "fail"} and not isinstance(source, dict):
                raise QualificationGateError(
                    f"candidate {candidate_id}: non-pending straight geometry must have a source reference"
                )
            if source is None:
                continue
            if not isinstance(source, dict):
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source reference must be an object"
                )
            path_value = source.get("path")
            digest = source.get("sha256")
            if (
                not isinstance(path_value, str)
                or not isinstance(digest, str)
                or len(digest) != _SHA256_LENGTH
                or any(char not in "0123456789abcdefABCDEF" for char in digest)
            ):
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source must contain path and sha256"
                )
            try:
                relative = _repo_relative(path_value)
            except QualificationGateError as exc:
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source path must be repo-relative: {path_value!r}"
                ) from exc
            if path_value.startswith(("http://", "https://")):
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source must be a repository-local path"
                )
            matching_reference = any(
                isinstance(reference, dict)
                and reference.get("url") == path_value
                and isinstance(reference.get("sha256"), str)
                and reference["sha256"].lower() == digest.lower()
                for reference in references
            )
            if not matching_reference:
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source is not an exact candidate evidence reference"
                )
            local_path = repo_root / relative
            try:
                resolved_local = local_path.resolve()
                resolved_root = repo_root.resolve()
                resolved_local.relative_to(resolved_root)
            except (OSError, ValueError) as exc:
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source escapes repository root: {path_value}"
                ) from exc
            if not local_path.is_file():
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source is missing: {path_value}"
                )
            actual = sha256_file(local_path, root=repo_root)
            if actual != digest.lower():
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source digest mismatch for {path_value}: "
                    f"expected {digest}, found {actual}"
                )
            base_bytes = _git_source_bytes(repo_root, commit, relative)
            if base_bytes is None:
                if status in {"pass", "fail"}:
                    raise QualificationGateError(
                        f"candidate {candidate_id}: geometry source {path_value} is new since provenance base; "
                        "straight geometry must remain pending"
                    )
                continue
            base_digest = hashlib.sha256(base_bytes).hexdigest()
            if base_digest != digest.lower():
                raise QualificationGateError(
                    f"candidate {candidate_id}: geometry source {path_value} does not match provenance base: "
                    f"expected {digest}, found {base_digest}"
                )


def _validate_decision_package(
    manifest: dict[str, Any], decision: dict[str, Any]
) -> None:
    """Reject a Rust response that is not a faithful package for *manifest*."""

    for field in ("schema_version", "campaign_id", "provenance", "corridor_requirement_mm"):
        if decision.get(field) != manifest.get(field):
            raise QualificationGateError(
                f"Rust decision package field {field!r} does not match manifest"
            )

    expected_inputs = _protected_pins(manifest)
    output_inputs = decision.get("protected_inputs")
    if not isinstance(output_inputs, list):
        raise QualificationGateError("Rust decision package protected_inputs is missing or invalid")
    output_pins: dict[str, str] = {}
    for item in output_inputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise QualificationGateError("Rust decision package has an invalid protected input")
        path = item["path"]
        digest = item.get("sha256")
        if path in output_pins or not isinstance(digest, str):
            raise QualificationGateError("Rust decision package has duplicate or invalid protected input")
        output_pins[path] = digest.lower()
    if output_pins != expected_inputs:
        raise QualificationGateError(
            "Rust decision package protected_inputs do not match the manifest"
        )

    input_candidates = manifest.get("candidates")
    output_candidates = decision.get("candidates")
    if not isinstance(input_candidates, list) or not isinstance(output_candidates, list):
        raise QualificationGateError("Rust decision package candidates are missing or invalid")
    expected_by_id = {
        item.get("candidate_id"): item
        for item in input_candidates
        if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
    }
    output_by_id: dict[str, Any] = {}
    for row in output_candidates:
        candidate = row.get("candidate") if isinstance(row, dict) else None
        candidate_id = candidate.get("candidate_id") if isinstance(candidate, dict) else None
        if not isinstance(candidate_id, str):
            raise QualificationGateError(
                "Rust decision package contains a candidate without an identity"
            )
        if candidate_id in output_by_id:
            raise QualificationGateError(
                "Rust decision package candidate identity set does not match the manifest"
            )
        output_by_id[candidate_id] = candidate
    if set(output_by_id) != set(expected_by_id):
        raise QualificationGateError(
            "Rust decision package candidate identity set does not match the manifest"
        )
    for candidate_id, expected in expected_by_id.items():
        if _canonical_candidate(output_by_id[candidate_id]) != _canonical_candidate(expected):
            raise QualificationGateError(
                f"Rust decision package candidate payload does not match manifest: {candidate_id}"
            )


def _canonical_candidate(candidate: dict[str, Any]) -> str:
    """Canonicalize candidate content while allowing Rust to sort evidence axes."""

    normalized = dict(candidate)
    axes = normalized.get("axes")
    if isinstance(axes, list):
        normalized_axes = []
        for axis in axes:
            if isinstance(axis, dict):
                axis_copy = dict(axis)
                for field in ("authority", "measured_mm", "required_mm"):
                    axis_copy.setdefault(field, None)
                normalized_axes.append(axis_copy)
            else:
                normalized_axes.append(axis)
        normalized["axes"] = sorted(
            normalized_axes,
            key=lambda axis: json.dumps(axis, sort_keys=True, separators=(",", ":")),
        )
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _load_manifest(path: Path) -> dict[str, Any]:
    """Compatibility loader; replay itself uses the sealed one-read path."""

    try:
        raw = qualification_replay.read_once(path, root=REPO_ROOT).data
    except QualificationGateError as exc:
        raise QualificationGateError(f"cannot read candidate manifest {path}: {exc}") from exc
    return _parse_manifest_bytes(raw)


def _parse_manifest_bytes(raw: bytes) -> dict[str, Any]:
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise QualificationGateError(f"invalid candidate manifest encoding: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise QualificationGateError(f"invalid candidate manifest JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise QualificationGateError("candidate manifest root must be a JSON object")
    return manifest


def _validate_evidence_references(manifest: dict[str, Any], repo_root: Path) -> None:
    """Check local evidence identities without attempting network access.

    The Rust engine validates the reference shape.  This runner additionally
    verifies repository-local evidence bytes against their recorded digest;
    otherwise a changed evidence note could silently masquerade as the bytes
    that were reviewed.  HTTP(S) references remain offline citations and are
    accepted only when their revision, retrieval date, and digest are
    concrete non-placeholder values.
    """

    candidates = manifest.get("candidates")
    if not isinstance(candidates, list):
        return
    placeholder_values = {"", "unknown", "tbd", "pending", "placeholder"}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        references = [candidate.get("datasheet"), *(candidate.get("certification_references") or [])]
        for reference in references:
            if not isinstance(reference, dict):
                continue
            for field in ("revision", "retrieved_at", "sha256"):
                value = reference.get(field)
                if not isinstance(value, str) or value.strip().lower() in placeholder_values:
                    raise QualificationGateError(
                        f"candidate {candidate.get('candidate_id', '<unknown>')}: "
                        f"reference.{field} is missing or a placeholder"
                    )
            url = reference.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            if url.startswith(("http://", "https://")):
                continue
            local_path = repo_root / _repo_relative(url)
            if not local_path.is_file():
                raise QualificationGateError(
                    f"candidate {candidate.get('candidate_id', '<unknown>')}: "
                    f"local evidence reference is missing: {url}"
                )
            actual = sha256_file(local_path, root=repo_root)
            if actual != reference["sha256"].lower():
                raise QualificationGateError(
                    f"candidate {candidate.get('candidate_id', '<unknown>')}: "
                    f"evidence digest mismatch for {url}: expected {reference['sha256']}, found {actual}"
                )


def _evaluate_in_rust(manifest: dict[str, Any]) -> str:
    """Call the sole verdict owner, keeping Python free of qualification rules."""

    try:
        import temper_quality_oracle
    except ImportError as exc:
        raise QualificationGateError(
            "temper_quality_oracle is unavailable; rebuild the pyo3 extension before replay"
        ) from exc
    try:
        return temper_quality_oracle.evaluate_isolation_qualification_json(
            json.dumps(manifest, separators=(",", ":"), ensure_ascii=False)
        )
    except (TypeError, ValueError) as exc:
        raise QualificationGateError(f"Rust qualification evaluator rejected manifest: {exc}") from exc


def replay(
    manifest_path: Path = DEFAULT_MANIFEST,
    output_path: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> str:
    """Replay *manifest_path* and optionally write a canonical output file.

    The output is written only after both protected-input observations match
    the manifest pins.  The returned string always has exactly one trailing
    newline, making stdout and committed evidence byte-comparable.
    """

    def preflight(manifest: dict[str, Any]) -> None:
        _validate_evidence_references(manifest, repo_root)
        _base_tree_hashes(manifest, repo_root)
        _validate_geometry_sources(manifest, repo_root)
        protected_hashes(manifest, repo_root)

    return qualification_replay.sealed_replay(
        manifest_path,
        output_path,
        root=repo_root,
        protected_paths=PROTECTED_PATHS,
        output_root=output_path.parent.resolve() if output_path is not None else None,
        parse_manifest=_parse_manifest_bytes,
        evaluate=_evaluate_in_rust,
        validate_output=_validate_decision_package,
        preflight=preflight,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output",
        type=Path,
        help="explicit decision-package path; omit to print canonical JSON to stdout",
    )
    args = parser.parse_args(argv)
    try:
        result = replay(args.manifest, args.output)
    except QualificationGateError as exc:
        print(f"QUALIFICATION GATE ERROR: {exc}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.write(result)
    else:
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
