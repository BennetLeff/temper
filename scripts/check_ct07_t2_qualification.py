#!/usr/bin/env python3
"""Offline replay gate for the CT07/T2 qualification evidence index.

The CT07 rules and verdict are owned by ``temper_quality_oracle``.  This
module is deliberately a small adapter around ``qualification_replay``: it
selects the evidence-index input and Rust registration, and formats the CLI
result.  Secure opening, one-read identity binding, protected-set snapshots,
and atomic publication remain in the shared replay helper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
CANDIDATE_ROOT = Path("elec/qualification/ct07_t2")
OUTPUT_ROOT = Path("power_pcb_dataset/qualification/ct07_t2")
DEFAULT_MANIFEST = REPO_ROOT / OUTPUT_ROOT / "evidence_index.json"
DEFAULT_OUTPUT = REPO_ROOT / OUTPUT_ROOT / "internal_decision.json"
CANONICAL_OUTPUT = Path("docs/evidence/2026-09-01-ct07-t2-owner-qualification.json")

# R18's direct production files.  Keep this tuple stable: it is part of the
# descriptor contract and is intentionally broader than the ISO runner's
# earlier five-file boundary.
REQUIRED_PROTECTED_FILES = (
    "pcb/temper.kicad_pcb",
    "power_pcb_dataset/drc_ceiling.json",
    "elec/domain_manifest.yaml",
    "docs/ENVIRONMENTAL_SPEC.md",
    "packages/temper-placer/src/temper_placer/core/isolation_constants.py",
    "elec/ato.yaml",
    "docs/hardware/BOM.md",
)
INVENTORY_CLASSES = (
    ("pcb", "*.kicad_sch"),
    ("elec/src", "**"),
    ("firmware", "**"),
)
BUILD_ROOT = "elec/build"
BUILD_OUTPUTS = (
    "default.csv",
    "default.layouts.json",
    "default.net",
    "default.net.source-digest",
    "manifest.json",
)
CANDIDATE_EXPORTS = {
    "default.csv": "candidate.csv",
    "default.layouts.json": "candidate.layouts.json",
    "default.net": "candidate.net",
}

# This is serialized into the evidence index and passed unchanged to Rust.
# Equality is strict so omission, weakening, renaming, or adding a protected
# entry cannot silently widen the replay boundary.
R18_DESCRIPTOR: dict[str, Any] = {
    "schema_version": 1,
    "required_files": list(REQUIRED_PROTECTED_FILES),
    "inventories": [
        {"path": path, "pattern": pattern, "kind": "git-visible-exact"}
        for path, pattern in INVENTORY_CLASSES
    ],
    "working_tree_only": {
        "path": BUILD_ROOT,
        "kind": "recursive-snapshot",
        "required_files": list(BUILD_OUTPUTS),
        "absent_is_valid": True,
    },
}

PROTECTED_PATHS = tuple(REQUIRED_PROTECTED_FILES) + (BUILD_ROOT,)


def _candidate_exports(project_root: Path) -> dict[str, str]:
    """Return deterministic Atopile exports with only the build-root path normalized."""

    return qualification_replay.normalized_text_exports(
        project_root,
        CANDIDATE_EXPORTS,
        root_token=CANDIDATE_ROOT.as_posix(),
    )


def verify_candidate_build(project_root: Path, repo_root: Path = REPO_ROOT) -> None:
    exports = _candidate_exports(project_root)
    canonical_root = repo_root / OUTPUT_ROOT / "generated"
    for name, actual in exports.items():
        with (canonical_root / name).open(encoding="utf-8", newline="") as handle:
            expected = handle.read()
        if actual != expected:
            raise QualificationGateError(f"clean CT07 candidate build differs: {name}")


def publish_candidate_build(project_root: Path, repo_root: Path = REPO_ROOT) -> None:
    """Atomically publish normalized candidate exports without touching production outputs."""

    canonical_root = repo_root / OUTPUT_ROOT / "generated"
    qualification_replay.publish_text_exports(
        _candidate_exports(project_root),
        canonical_root,
        root=repo_root,
        protected_paths=PROTECTED_PATHS,
    )
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_DIGEST_RE = re.compile(r"[0-9a-fA-F]{64}")
QualificationGateError = qualification_replay.ReplayError


def _parse_manifest_bytes(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationGateError(f"invalid CT07 evidence index JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationGateError("CT07 evidence index root must be an object")
    return value


def _repo_relative(path: str | Path) -> Path:
    relative = Path(path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise QualificationGateError(f"protected input path must be repo-relative: {path!r}")
    return relative


def _descriptor_from(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    descriptor = manifest.get("protected_descriptor")
    if not isinstance(descriptor, Mapping):
        raise QualificationGateError("CT07 evidence index protected_descriptor is required")
    return descriptor


def _validate_r18_descriptor(manifest: Mapping[str, Any]) -> None:
    """Require the exact Rust-facing R18 descriptor before replay I/O."""

    descriptor = _descriptor_from(manifest)
    expected = json.dumps(R18_DESCRIPTOR, sort_keys=True, separators=(",", ":"))
    actual = json.dumps(dict(descriptor), sort_keys=True, separators=(",", ":"))
    if actual != expected:
        raise QualificationGateError(
            "CT07 protected_descriptor does not exactly match the R18 production boundary"
        )


def _commit_from(manifest: Mapping[str, Any]) -> str:
    commit = manifest.get("base_commit")
    if commit is None and isinstance(manifest.get("provenance"), Mapping):
        commit = manifest["provenance"].get("commit")
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise QualificationGateError(
            "CT07 base_commit must be a resolvable 40-character lowercase commit"
        )
    return commit


def _git_bytes(repo_root: Path, commit: str, relative: Path) -> bytes:
    try:
        return subprocess.run(
            ["git", "show", f"{commit}:{relative.as_posix()}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QualificationGateError(
            f"CT07 protected input is absent from base commit {commit}: {relative}"
        ) from exc


def _git_paths(repo_root: Path, args: list[str]) -> tuple[str, ...]:
    try:
        output = subprocess.run(
            ["git", *args], cwd=repo_root, check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QualificationGateError("unable to inventory protected Git paths") from exc
    return tuple(sorted(path for path in output.decode("utf-8").splitlines() if path))


def _base_inventory(repo_root: Path, commit: str, path: str, pattern: str) -> tuple[str, ...]:
    prefix = path.rstrip("/")
    paths = _git_paths(repo_root, ["ls-tree", "-r", "--name-only", commit, "--", prefix])
    if pattern == "*.kicad_sch":
        return tuple(sorted(p for p in paths if Path(p).parent.as_posix() == prefix and p.endswith(".kicad_sch")))
    return tuple(sorted(p for p in paths if p == prefix or p.startswith(prefix + "/")))


def _live_inventory(repo_root: Path, path: str, pattern: str) -> tuple[str, ...]:
    prefix = path.rstrip("/")
    paths = _git_paths(
        repo_root,
        ["ls-files", "--cached", "--others", "--exclude-standard", "--", prefix],
    )
    if pattern == "*.kicad_sch":
        paths = tuple(p for p in paths if Path(p).parent.as_posix() == prefix and p.endswith(".kicad_sch"))
    else:
        paths = tuple(p for p in paths if p == prefix or p.startswith(prefix + "/"))
    for item in paths:
        absolute = repo_root / _repo_relative(item)
        # read_once is the only file-open path used by this runner.  It rejects
        # symlinks, non-regular files, path escapes, and replacement races.
        qualification_replay.read_once(absolute, root=repo_root)
    return tuple(sorted(paths))


def _validate_protected_base_and_inventories(
    manifest: Mapping[str, Any], repo_root: Path
) -> None:
    """Bind static files and recursive production inventories to one base tree."""

    commit = _commit_from(manifest)
    try:
        kind = subprocess.run(
            ["git", "cat-file", "-t", commit],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QualificationGateError(f"CT07 base_commit does not resolve: {commit}") from exc
    if kind != "commit":
        raise QualificationGateError(f"CT07 base_commit is not a commit: {commit}")

    pins = manifest.get("protected_inputs")
    if not isinstance(pins, list):
        raise QualificationGateError("CT07 protected_inputs must be a list")
    pin_map: dict[str, str] = {}
    for item in pins:
        if not isinstance(item, Mapping):
            raise QualificationGateError("CT07 protected input descriptor must be an object")
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or path in pin_map or not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise QualificationGateError(f"invalid CT07 protected input pin: {path!r}")
        pin_map[path] = digest.lower()
    if tuple(sorted(pin_map)) != tuple(sorted(REQUIRED_PROTECTED_FILES)):
        raise QualificationGateError("CT07 protected_inputs must pin exactly the R18 required files")

    identities: set[tuple[int, int]] = set()
    for path in REQUIRED_PROTECTED_FILES:
        relative = _repo_relative(path)
        expected = hashlib.sha256(_git_bytes(repo_root, commit, relative)).hexdigest()
        if pin_map[path] != expected:
            raise QualificationGateError(f"CT07 protected pin does not match base commit: {path}")
        current = qualification_replay.read_once(repo_root / relative, root=repo_root)
        if current.sha256 != expected:
            raise QualificationGateError(f"CT07 protected input differs from base commit: {path}")
        identity = current.identity[:2]
        if identity in identities:
            raise QualificationGateError(f"CT07 protected input is a hard-link alias: {path}")
        identities.add(identity)

    for path, pattern in INVENTORY_CLASSES:
        expected = _base_inventory(repo_root, commit, path, pattern)
        actual = _live_inventory(repo_root, path, pattern)
        if actual != expected:
            raise QualificationGateError(
                f"CT07 protected inventory drift for {path}: expected {expected}, found {actual}"
            )
        for item in actual:
            read = qualification_replay.read_once(repo_root / _repo_relative(item), root=repo_root)
            base_digest = hashlib.sha256(_git_bytes(repo_root, commit, _repo_relative(item))).hexdigest()
            if read.sha256 != base_digest:
                raise QualificationGateError(f"CT07 protected inventory payload differs from base: {item}")
            inode = read.identity[:2]
            if inode in identities:
                raise QualificationGateError(f"CT07 protected input is a hard-link alias: {item}")
            identities.add(inode)


def _validate_build_snapshot(
    repo_root: Path, *, protected_inodes: set[tuple[int, int]] | None = None
) -> None:
    """Validate the working-tree-only generated-output class before replay."""

    root = repo_root / BUILD_ROOT
    if root.is_symlink():
        raise QualificationGateError("CT07 elec/build must be a real directory")
    if not root.exists():
        return
    if not root.is_dir():
        raise QualificationGateError("CT07 elec/build must be a real directory")
    files = tuple(sorted(path.name for path in root.iterdir() if path.is_file()))
    if tuple(BUILD_OUTPUTS) != files:
        raise QualificationGateError(
            "CT07 elec/build must contain exactly the five required generated outputs"
        )
    identities = set(protected_inodes or ())
    for name in BUILD_OUTPUTS:
        read = qualification_replay.read_once(root / name, root=repo_root)
        inode = read.identity[:2]
        if inode in identities:
            raise QualificationGateError(f"CT07 elec/build contains a hard-link alias: {name}")
        identities.add(inode)


def _evidence_entries(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries = manifest.get("evidence_files", manifest.get("evidence", []))
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise QualificationGateError("CT07 evidence_files must be a list")
    result: list[Mapping[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise QualificationGateError("CT07 evidence entry must be an object")
        result.append(entry)
    return result


def _payload_from_same_bytes(
    manifest: Mapping[str, Any],
    repo_root: Path,
    observations: dict[str, qualification_replay.ReadOnce] | None = None,
) -> dict[str, Any]:
    """Populate Rust evidence blobs from one helper-owned read per artifact."""

    payload = dict(manifest)
    entries = _evidence_entries(manifest)
    if not entries and isinstance(manifest.get("raw_evidence"), list):
        entries = [entry for entry in manifest["raw_evidence"] if isinstance(entry, Mapping) and "path" in entry]
    if not entries:
        payload["raw_evidence"] = []
        payload["evidence_digest"] = hashlib.sha256(b"").hexdigest()
        return payload
    candidate_root = (repo_root / CANDIDATE_ROOT).resolve()
    protected = qualification_replay.snapshot_paths(repo_root, REQUIRED_PROTECTED_FILES)
    protected_inodes = {
        (entry.identity[0], entry.identity[1])
        for entry in protected.values()
        if entry.identity is not None
    }
    blobs: list[dict[str, Any]] = []
    for entry in entries:
        path = entry.get("path")
        blob_id = entry.get("id")
        if not isinstance(path, str) or not isinstance(blob_id, str) or not blob_id.strip():
            raise QualificationGateError("CT07 evidence entry requires id and path")
        relative = _repo_relative(path)
        absolute = (repo_root / relative).resolve(strict=False)
        try:
            absolute.relative_to(candidate_root)
        except ValueError as exc:
            raise QualificationGateError(
                f"CT07 evidence must live below candidate workspace: {path}"
            ) from exc
        read = qualification_replay.read_once(
            repo_root / relative,
            root=repo_root,
            reject_inodes=protected_inodes,
        )
        if observations is not None:
            observations[relative.as_posix()] = read
        blobs.append({"id": blob_id, "sha256": read.sha256, "bytes": list(read.data)})
    payload["raw_evidence"] = sorted(blobs, key=lambda item: item["id"])
    evidence_bytes = b"".join(bytes(item["bytes"]) for item in payload["raw_evidence"])
    payload["evidence_digest"] = hashlib.sha256(evidence_bytes).hexdigest()
    return payload


def _evaluate_in_rust(
    manifest: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
    observations: dict[str, qualification_replay.ReadOnce] | None = None,
) -> str:
    """Call the one CT07 evaluator registration; Python owns no verdict logic."""

    try:
        import temper_quality_oracle
    except ImportError as exc:
        raise QualificationGateError(
            "temper_quality_oracle is unavailable; rebuild the pyo3 extension before replay"
        ) from exc
    evaluator = getattr(temper_quality_oracle, "evaluate_ct07_t2_qualification_json", None)
    if not callable(evaluator):
        raise QualificationGateError("CT07 Rust evaluator registration is unavailable")
    payload = _payload_from_same_bytes(manifest, repo_root, observations)
    try:
        return evaluator(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise QualificationGateError(f"CT07 Rust evaluator rejected evidence index: {exc}") from exc


def _validate_output(manifest: Mapping[str, Any], decision: Mapping[str, Any]) -> None:
    for field in ("schema_version", "construction_id", "construction_digest"):
        if field not in decision:
            raise QualificationGateError(f"CT07 Rust decision missing {field}")
        if decision.get(field) != manifest.get(field):
            raise QualificationGateError(f"CT07 Rust decision field {field} does not match evidence index")


def _safe_output(path: Path, repo_root: Path) -> Path:
    candidate = path if path.is_absolute() else repo_root / path
    if candidate.resolve() == (repo_root / CANONICAL_OUTPUT).resolve():
        return candidate
    output_root = (repo_root / OUTPUT_ROOT).resolve()
    try:
        resolved = candidate.resolve()
        resolved.relative_to(output_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise QualificationGateError(
            f"CT07 output escapes qualification output root: {path}"
        ) from exc
    return candidate


def replay(
    manifest_path: Path = DEFAULT_MANIFEST,
    output_path: Path | None = None,
    *,
    repo_root: Path = REPO_ROOT,
) -> str:
    """Replay an evidence index and optionally publish its canonical decision."""

    manifest_path = Path(manifest_path)
    # A replay without ``--output`` is stdout-only.  Publication is only
    # permitted when the caller supplies an explicit path below OUTPUT_ROOT.
    output = _safe_output(output_path, repo_root) if output_path is not None else None
    publication_root = (
        (repo_root / CANONICAL_OUTPUT).parent
        if output is not None
        and output.resolve() == (repo_root / CANONICAL_OUTPUT).resolve()
        else repo_root / OUTPUT_ROOT
    )
    evidence_observations: dict[str, qualification_replay.ReadOnce] = {}

    def preflight(manifest: Mapping[str, Any]) -> None:
        _validate_r18_descriptor(manifest)
        _validate_protected_base_and_inventories(manifest, repo_root)
        static_snapshot = qualification_replay.snapshot_paths(
            repo_root, REQUIRED_PROTECTED_FILES
        )
        protected_inodes = {
            entry.identity[:2]
            for entry in static_snapshot.values()
            if entry.identity is not None
        }
        _validate_build_snapshot(repo_root, protected_inodes=protected_inodes)
        candidate = (repo_root / CANDIDATE_ROOT).resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError as exc:
            raise QualificationGateError("CT07 candidate workspace escapes repository") from exc

    return qualification_replay.sealed_replay(
        manifest_path,
        output,
        root=repo_root,
        protected_paths=PROTECTED_PATHS,
        output_root=publication_root,
        parse_manifest=_parse_manifest_bytes,
        evaluate=lambda manifest: _evaluate_in_rust(
            manifest, repo_root, evidence_observations
        ),
        validate_output=lambda manifest, decision: _validate_output_and_evidence(
            manifest, decision, repo_root, evidence_observations
        ),
        preflight=preflight,
    )


def _validate_output_and_evidence(
    manifest: Mapping[str, Any],
    decision: Mapping[str, Any],
    repo_root: Path,
    observations: Mapping[str, qualification_replay.ReadOnce],
) -> None:
    """Validate output and identity-recheck evidence without reading it again."""

    _validate_output(manifest, decision)
    for relative, read in observations.items():
        try:
            current = os.lstat(repo_root / _repo_relative(relative))
        except OSError as exc:
            raise QualificationGateError(
                f"CT07 evidence changed after its single read: {relative}"
            ) from exc
        identity = (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
        )
        if identity != read.identity:
            raise QualificationGateError(
                f"CT07 evidence changed after its single read: {relative}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    candidate_mode = parser.add_mutually_exclusive_group()
    candidate_mode.add_argument("--verify-candidate-build", type=Path)
    candidate_mode.add_argument("--publish-candidate-build", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify_candidate_build is not None:
            verify_candidate_build(args.verify_candidate_build)
            print("CT07 candidate build matches canonical exports")
            return 0
        if args.publish_candidate_build is not None:
            publish_candidate_build(args.publish_candidate_build)
            print("published CT07 canonical candidate exports")
            return 0
        result = replay(args.manifest, args.output)
    except QualificationGateError as exc:
        print(f"CT07 QUALIFICATION GATE ERROR: {exc}", file=sys.stderr)
        return 2
    if args.output is None:
        sys.stdout.write(result)
    else:
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
