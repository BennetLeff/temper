#!/usr/bin/env python3
"""Validate a five-run performance capture and emit review-only artifacts.

This module is deliberately side-effect free until :func:`aggregate_capture`
is given an ``output_dir``.  It never checks out a commit, edits the baseline,
or updates a git ref.  A capture is accepted only when every expected
benchmark has exactly five unique rows from one resolvable 40-hex commit and
the rows can be appended to the existing baseline without changing history.

The workflow-facing command is, for example::

    uv run python scripts/validate_perf_capture.py \
      --capture-sha 0123...89ab --baseline baseline.jsonl \
      --registry benchmarks/perf_ab.py --output-dir evidence \
      capture-1.ndjson capture-2.ndjson capture-3.ndjson \
      capture-4.ndjson capture-5.ndjson

The resulting ``capture-manifest.json`` and
``candidate-baseline-append.jsonl`` are review artifacts only.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


SHA_RE = re.compile(r"[0-9a-fA-F]{40}\Z")
REGIME_SHA_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
CAPTURE_COUNT = 5
SYNTHETIC_BOARD = "synthetic"


class CaptureValidationError(ValueError):
    """Raised when capture evidence cannot support a baseline append."""


@dataclass
class CaptureResult:
    """Validated capture and the review artifacts derived from it."""

    requested_sha: str
    records: list[dict[str, Any]]
    baseline_records: list[dict[str, Any]]
    candidate_records: list[dict[str, Any]]
    derived_margins: dict[str, dict[str, float]]
    manifest: dict[str, Any]
    patch_path: Path | None = None
    manifest_path: Path | None = None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def parse_ndjson(text: str, *, source: str = "capture") -> list[dict[str, Any]]:
    """Parse strict NDJSON, rejecting progress output and non-object rows."""

    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CaptureValidationError(
                f"{source}: line {line_number} is not JSON ({exc})"
            ) from exc
        if not isinstance(value, dict):
            raise CaptureValidationError(
                f"{source}: line {line_number} must be a JSON object, "
                f"got {type(value).__name__}"
            )
        records.append(value)
    return records


def load_capture_artifacts(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Load capture artifacts in argument order with strict NDJSON parsing."""

    records: list[dict[str, Any]] = []
    for path in paths:
        path = Path(path)
        if not path.is_file():
            raise CaptureValidationError(f"capture artifact not found: {path}")
        records.extend(parse_ndjson(path.read_text(encoding="utf-8"), source=str(path)))
    return records


def _read_ndjson_file(path: Path, *, source: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CaptureValidationError(f"{source} not found: {path}")
    return parse_ndjson(path.read_text(encoding="utf-8"), source=source)


def _key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("module", "")),
        str(record.get("board", "")),
        str(record.get("stage", "")),
    )


def normalize_keys(keys: Iterable[Sequence[str]]) -> set[tuple[str, str, str]]:
    """Normalize ``(module, stage)`` and ``(module, board, stage)`` keys."""

    result: set[tuple[str, str, str]] = set()
    for raw in keys:
        if len(raw) == 2:
            result.add((str(raw[0]), SYNTHETIC_BOARD, str(raw[1])))
        elif len(raw) == 3:
            result.add((str(raw[0]), str(raw[1]), str(raw[2])))
        else:
            raise CaptureValidationError(f"benchmark key must have 2 or 3 fields: {raw!r}")
    if not result:
        raise CaptureValidationError("registered benchmark key set is empty")
    return result


def registered_keys_from_source(path: Path) -> set[tuple[str, str, str]]:
    """Read literal ``_BENCHMARKS`` keys without importing the benchmark module."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise CaptureValidationError(f"cannot read benchmark registry {path}: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "_BENCHMARKS" for target in targets):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            raise CaptureValidationError(f"benchmark registry {path} is not a literal mapping")
        keys: list[tuple[str, str]] = []
        for key in value.keys:
            if not isinstance(key, ast.Tuple) or len(key.elts) != 2:
                raise CaptureValidationError(
                    f"benchmark registry {path} contains a non-literal two-field key"
                )
            if not all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in key.elts):
                raise CaptureValidationError(
                    f"benchmark registry {path} contains a non-string key"
                )
            keys.append((key.elts[0].value, key.elts[1].value))
        return normalize_keys(keys)
    raise CaptureValidationError(f"benchmark registry {path} has no _BENCHMARKS mapping")


def _resolve_capture_sha(requested_sha: str, repo_root: Path) -> str:
    if not isinstance(requested_sha, str) or not SHA_RE.fullmatch(requested_sha):
        raise CaptureValidationError("capture SHA must be an immutable 40-hex commit SHA")
    requested = requested_sha.lower()
    try:
        resolved = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{requested}^{{commit}}"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CaptureValidationError(f"capture SHA {requested} does not resolve to a commit") from exc
    if resolved != requested:
        raise CaptureValidationError(
            f"capture SHA {requested} resolves to a different commit {resolved}"
        )
    return requested


def _changed_paths(repo_root: Path, sha: str) -> set[str]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(repo_root), "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha],
            text=True,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CaptureValidationError(f"cannot inspect capture commit {sha}") from exc
    return {line.strip() for line in output.splitlines() if line.strip()}


def _regime_sources(record: dict[str, Any]) -> list[tuple[str, str]]:
    regime = record.get("measurement_regime")
    if regime is None:
        return []
    if not isinstance(regime, dict):
        raise CaptureValidationError("measurement regime must be an object")
    fingerprint = regime.get("fingerprint")
    if not isinstance(fingerprint, str) or not REGIME_SHA_RE.fullmatch(fingerprint):
        raise CaptureValidationError("measurement regime has an invalid fingerprint")
    metadata = regime.get("metadata")
    if not isinstance(metadata, dict):
        raise CaptureValidationError("measurement regime metadata is missing or malformed")
    expected_fingerprint = hashlib.sha256(_canonical(metadata).encode("utf-8")).hexdigest()
    if fingerprint.lower() != expected_fingerprint:
        raise CaptureValidationError("measurement regime fingerprint does not match its metadata")
    arms = metadata.get("arms")
    if not isinstance(arms, dict):
        raise CaptureValidationError("measurement regime metadata has no arms mapping")
    result: list[tuple[str, str]] = []
    for arm_name, arm in arms.items():
        if not isinstance(arm, dict) or not isinstance(arm.get("sources"), list):
            raise CaptureValidationError(f"measurement regime arm {arm_name!r} has malformed sources")
        for source in arm["sources"]:
            if not isinstance(source, dict) or not isinstance(source.get("path"), str):
                raise CaptureValidationError(f"measurement regime arm {arm_name!r} has a malformed source")
            digest = source.get("sha256")
            if not isinstance(digest, str) or not REGIME_SHA_RE.fullmatch(digest):
                raise CaptureValidationError(f"measurement regime source {source['path']!r} has an invalid SHA-256")
            result.append((source["path"], digest.lower()))
    return result


def _verify_regime_sources(records: Iterable[dict[str, Any]], repo_root: Path, sha: str) -> None:
    paths: set[str] = set()
    source_digests: dict[str, str] = {}
    for record in records:
        for path, digest in _regime_sources(record):
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise CaptureValidationError(f"registered source path is not repository-relative: {path}")
            paths.add(path)
            previous = source_digests.setdefault(path, digest)
            if previous != digest:
                raise CaptureValidationError(
                    f"registered source path {path!r} has conflicting regime digests"
                )

    changed = _changed_paths(repo_root, sha)
    changed_registered = sorted(changed & paths)
    if changed_registered:
        raise CaptureValidationError(
            "capture commit changed registered paths relative to its parent: "
            + ", ".join(changed_registered)
        )

    for path, digest in source_digests.items():
        try:
            content = subprocess.check_output(
                ["git", "-C", str(repo_root), "show", f"{sha}:{path}"],
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CaptureValidationError(
                f"registered source path {path!r} is absent at capture SHA {sha}"
            ) from exc
        actual = hashlib.sha256(content).hexdigest()
        if actual != digest:
            raise CaptureValidationError(
                f"registered source path {path!r} bytes do not match its regime digest"
            )


def validate_append_only(
    baseline_records: Sequence[dict[str, Any]], candidate_records: Sequence[dict[str, Any]]
) -> None:
    """Require candidate history to preserve the baseline byte-level record prefix."""

    if len(candidate_records) < len(baseline_records):
        raise CaptureValidationError("candidate baseline is not append-only: rows were removed")
    for index, (before, after) in enumerate(zip(baseline_records, candidate_records)):
        if _canonical(before) != _canonical(after):
            raise CaptureValidationError(
                f"candidate baseline is not append-only: existing row {index} was edited"
            )


def _margin_key(key: tuple[str, str]) -> str:
    return f"{key[0]}/{key[1]}"


def _derive_margins(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Use the comparator's fixed-commit arithmetic as the single authority."""

    path = Path(__file__).resolve().parent / "pr_perf_compare.py"
    spec = importlib.util.spec_from_file_location("_capture_pr_perf_compare", path)
    if spec is None or spec.loader is None:
        raise CaptureValidationError(f"cannot load margin authority {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    gated, ungateable = module.derive_margin_table(records)
    return {
        "gated": {_margin_key(key): value for key, value in sorted(gated.items())},
        "ungateable": {_margin_key(key): value for key, value in sorted(ungateable.items())},
    }


def _normalize_margin_file(value: dict[str, Any]) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        raise CaptureValidationError("committed margins must be a JSON object")
    result: dict[str, dict[str, float]] = {"gated": {}, "ungateable": {}}
    for category in result:
        raw = value.get(category, {})
        if not isinstance(raw, dict):
            raise CaptureValidationError(f"committed margins {category!r} must be an object")
        for key, margin in raw.items():
            if not isinstance(key, str) or not isinstance(margin, (int, float)) or isinstance(margin, bool):
                raise CaptureValidationError(f"committed margin {category}/{key!r} is malformed")
            result[category][key] = float(margin)
    unknown = set(value) - set(result)
    if unknown:
        raise CaptureValidationError(f"committed margins contain unsupported fields: {sorted(unknown)}")
    return result


def _validate_margins(records: list[dict[str, Any]], committed: dict[str, Any] | None) -> dict[str, dict[str, float]]:
    derived = _derive_margins(records)
    if committed is not None:
        expected = _normalize_margin_file(committed)
        if expected != derived:
            raise CaptureValidationError(
                "committed margins do not exactly match fixed-commit, same-regime "
                f"derivation (expected {derived!r}, got {expected!r})"
            )
    return derived


def validate_capture(
    artifact_paths: Iterable[Path],
    *,
    requested_sha: str,
    expected_keys: Iterable[Sequence[str]],
    baseline_records: Sequence[dict[str, Any]] = (),
    candidate_records: Sequence[dict[str, Any]] | None = None,
    repo_root: Path | None = None,
    committed_margins: dict[str, Any] | None = None,
) -> CaptureResult:
    """Validate capture evidence and return an in-memory append candidate."""

    root = (repo_root or Path.cwd()).resolve()
    sha = _resolve_capture_sha(requested_sha, root)
    expected = normalize_keys(expected_keys)
    records = load_capture_artifacts(artifact_paths)
    if not records:
        raise CaptureValidationError("capture artifacts are empty")

    seen: set[str] = set()
    seen_runs: set[tuple[tuple[str, str, str], str]] = set()
    counts: dict[tuple[str, str, str], int] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise CaptureValidationError(f"capture row {index} is not an object")
        row_sha = record.get("git_commit")
        if not isinstance(row_sha, str) or not SHA_RE.fullmatch(row_sha):
            raise CaptureValidationError(f"capture row {index} has an invalid or symbolic git_commit")
        if row_sha.lower() != sha:
            raise CaptureValidationError(
                f"capture rows must use one capture SHA {sha}; row {index} uses {row_sha!r}"
            )
        key = _key(record)
        if key not in expected:
            raise CaptureValidationError(f"capture contains unexpected benchmark key {key!r}")
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise CaptureValidationError(f"capture row {index} has no valid timestamp")
        run_identity = (key, timestamp)
        if run_identity in seen_runs:
            raise CaptureValidationError(
                f"capture contains duplicate run identity {key!r} at timestamp {timestamp!r}"
            )
        seen_runs.add(run_identity)
        identity = _canonical(record)
        if identity in seen:
            raise CaptureValidationError(f"capture contains duplicate row {index} for {key!r}")
        seen.add(identity)
        counts[key] = counts.get(key, 0) + 1

    missing = sorted(expected - counts.keys())
    if missing:
        raise CaptureValidationError(f"capture is missing benchmark keys: {missing!r}")
    wrong_counts = {key: count for key, count in counts.items() if count != CAPTURE_COUNT}
    if wrong_counts:
        raise CaptureValidationError(
            f"each benchmark must have exactly {CAPTURE_COUNT} rows; got {wrong_counts!r}"
        )

    baseline = list(baseline_records)
    candidate = list(candidate_records) if candidate_records is not None else baseline + records
    validate_append_only(baseline, candidate)
    if candidate[len(baseline):] != records:
        raise CaptureValidationError(
            "candidate baseline append does not exactly equal the validated capture rows"
        )

    _verify_regime_sources(records, root, sha)
    derived_margins = _validate_margins(candidate, committed_margins)
    regimes = sorted({
        str((record.get("measurement_regime") or {}).get("fingerprint", "legacy-v2"))
        for record in records
    })
    manifest = {
        "schema_version": 1,
        "capture_sha": sha,
        "rows": len(records),
        "baseline_rows": len(baseline),
        "candidate_rows": len(candidate),
        "benchmarks": [
            {"module": key[0], "board": key[1], "stage": key[2], "rows": counts[key]}
            for key in sorted(expected)
        ],
        "measurement_regimes": regimes,
        "derived_margins": derived_margins,
        "append_only": True,
    }
    return CaptureResult(
        requested_sha=sha,
        records=records,
        baseline_records=baseline,
        candidate_records=candidate,
        derived_margins=derived_margins,
        manifest=manifest,
    )


def aggregate_capture(
    artifact_paths: Iterable[Path],
    *,
    requested_sha: str,
    expected_keys: Iterable[Sequence[str]],
    baseline_records: Sequence[dict[str, Any]] = (),
    candidate_records: Sequence[dict[str, Any]] | None = None,
    repo_root: Path | None = None,
    committed_margins: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> CaptureResult:
    """Validate a capture and optionally write only review artifacts."""

    result = validate_capture(
        artifact_paths,
        requested_sha=requested_sha,
        expected_keys=expected_keys,
        baseline_records=baseline_records,
        candidate_records=candidate_records,
        repo_root=repo_root,
        committed_margins=committed_margins,
    )
    if output_dir is None:
        return result
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    patch_path = output / "candidate-baseline-append.jsonl"
    patch_text = "".join(_canonical(record) + "\n" for record in result.records)
    patch_path.write_text(patch_text, encoding="utf-8")
    manifest = dict(result.manifest)
    manifest["candidate_patch"] = patch_path.name
    manifest["candidate_patch_sha256"] = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    manifest_path = output / "capture-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result.manifest = manifest
    result.patch_path = patch_path
    result.manifest_path = manifest_path
    return result


def _parse_cli_key(value: str) -> tuple[str, str, str]:
    parts = value.split("/")
    if len(parts) == 2:
        return (parts[0], SYNTHETIC_BOARD, parts[1])
    if len(parts) == 3:
        return (parts[0], parts[1], parts[2])
    raise argparse.ArgumentTypeError("benchmark key must be module/stage or module/board/stage")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--capture-sha", required=True, help="immutable 40-hex capture commit")
    parser.add_argument("--baseline", type=Path, required=True, help="existing baseline NDJSON")
    parser.add_argument("--registry", type=Path, default=Path("benchmarks/perf_ab.py"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-baseline", type=Path, default=None)
    parser.add_argument("--margins-json", type=Path, default=None)
    parser.add_argument("--key", type=_parse_cli_key, action="append", dest="keys", default=None)
    parser.add_argument("artifacts", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        keys = args.keys if args.keys is not None else registered_keys_from_source(args.registry)
        baseline = _read_ndjson_file(args.baseline, source="baseline")
        candidate = (
            _read_ndjson_file(args.candidate_baseline, source="candidate baseline")
            if args.candidate_baseline is not None
            else None
        )
        margins = (
            json.loads(args.margins_json.read_text(encoding="utf-8"))
            if args.margins_json is not None
            else None
        )
        result = aggregate_capture(
            args.artifacts,
            requested_sha=args.capture_sha,
            expected_keys=keys,
            baseline_records=baseline,
            candidate_records=candidate,
            repo_root=args.repo_root,
            committed_margins=margins,
            output_dir=args.output_dir,
        )
    except (CaptureValidationError, OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"validated {len(result.records)} rows for {len(result.manifest['benchmarks'])} benchmarks")
    print(f"manifest: {result.manifest_path}")
    print(f"candidate append: {result.patch_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
