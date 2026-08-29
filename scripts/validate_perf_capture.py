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
      --metadata capture-1.metadata --metadata capture-2.metadata \
      --metadata capture-3.metadata --metadata capture-4.metadata \
      --metadata capture-5.metadata \
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
import math
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pr_perf_compare import (
    LEGACY_REGIME_IDENTITY,
    compare,
    gate_failures,
    load_main_baselines,
)

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


def parse_capture_metadata(text: str, *, source: str = "metadata") -> dict[str, str]:
    """Parse the key/value metadata emitted beside one capture artifact."""

    fields: dict[str, str] = {}
    required = {
        "capture_sha",
        "checked_out_sha",
        "matrix_run",
        "workflow_run_id",
        "workflow_run_attempt",
    }
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if "=" not in line:
            raise CaptureValidationError(
                f"{source}: line {line_number} is not key=value metadata"
            )
        key, value = line.split("=", 1)
        if not key or not value or key in fields:
            raise CaptureValidationError(
                f"{source}: line {line_number} has malformed or duplicate metadata"
            )
        fields[key] = value
    missing = sorted(required - fields.keys())
    if missing:
        raise CaptureValidationError(f"{source}: missing metadata fields: {missing!r}")
    unknown = sorted(set(fields) - required)
    if unknown:
        raise CaptureValidationError(f"{source}: unsupported metadata fields: {unknown!r}")
    return fields


def load_capture_artifacts(paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Load capture artifacts in argument order with strict NDJSON parsing."""

    records: list[dict[str, Any]] = []
    for path in paths:
        path = Path(path)
        if not path.is_file():
            raise CaptureValidationError(f"capture artifact not found: {path}")
        records.extend(parse_ndjson(path.read_text(encoding="utf-8"), source=str(path)))
    return records


def load_capture_metadata(paths: Iterable[Path]) -> list[dict[str, str]]:
    """Load the metadata sidecar for each independent capture run."""

    records: list[dict[str, str]] = []
    for path in paths:
        path = Path(path)
        if not path.is_file():
            raise CaptureValidationError(f"capture metadata not found: {path}")
        records.append(
            parse_capture_metadata(path.read_text(encoding="utf-8"), source=str(path))
        )
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


def declared_regime_keys_from_source(path: Path) -> set[tuple[str, str, str]]:
    """Read benchmark keys that have an explicit regime declaration."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise CaptureValidationError(f"cannot read benchmark registry {path}: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "_BENCHMARK_REGIME_METADATA"
            for target in targets
        ):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            raise CaptureValidationError(
                f"benchmark regime registry {path} is not a literal mapping"
            )
        keys: list[tuple[str, str]] = []
        for key in value.keys:
            if not isinstance(key, ast.Tuple) or len(key.elts) != 2:
                raise CaptureValidationError(
                    f"benchmark regime registry {path} contains a non-literal two-field key"
                )
            if not all(
                isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in key.elts
            ):
                raise CaptureValidationError(
                    f"benchmark regime registry {path} contains a non-string key"
                )
            keys.append((key.elts[0].value, key.elts[1].value))
        return normalize_keys(keys)
    return set()


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


def _changed_paths(
    repo_root: Path, sha: str, source_digests: Mapping[str, str]
) -> set[str]:
    if not source_digests:
        return set()
    try:
        parents_line = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-list", "--parents", "-n", "1", sha],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CaptureValidationError(f"cannot inspect capture commit {sha}") from exc
    fields = parents_line.split()
    if not fields or fields[0].lower() != sha.lower():
        raise CaptureValidationError(f"cannot inspect capture commit {sha}: malformed parent list")
    parents = fields[1:]
    commands: list[list[str]]
    if parents:
        # Compare against every parent. Plain diff-tree on a merge commit
        # suppresses the merge diff and would let a changed second-parent arm
        # through the source-change guard.
        commands = [
            ["git", "-C", str(repo_root), "diff", "--name-only", parent, sha]
            for parent in parents
        ]
    else:
        commands = [[
            "git", "-C", str(repo_root), "diff-tree", "--no-commit-id",
            "--name-only", "-r", "--root", sha,
        ]]
    changed: set[str] = set()
    for command in commands:
        try:
            output = subprocess.check_output(
                command, text=True, stderr=subprocess.PIPE
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CaptureValidationError(
                f"cannot inspect capture commit {sha} against its parent"
            ) from exc
        changed.update(line.strip() for line in output.splitlines() if line.strip())
    return changed


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
    source_digests: dict[str, str] = {}
    for record in records:
        for path, digest in _regime_sources(record):
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise CaptureValidationError(f"registered source path is not repository-relative: {path}")
            previous = source_digests.setdefault(path, digest)
            if previous != digest:
                raise CaptureValidationError(
                    f"registered source path {path!r} has conflicting regime digests"
                )

    changed = _changed_paths(repo_root, sha, source_digests)
    changed_registered = sorted(changed & source_digests.keys())
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
    for index, (before, after) in enumerate(
        zip(baseline_records, candidate_records[: len(baseline_records)], strict=True)
    ):
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
    expected = _normalize_margin_file(committed) if committed is not None else _load_committed_margins()
    if expected != derived:
        raise CaptureValidationError(
            "committed margins do not exactly match fixed-commit, same-regime "
            f"derivation (expected {derived!r}, got {expected!r})"
        )
    return derived


def _load_committed_margins() -> dict[str, dict[str, float]]:
    """Load the margin table committed in the comparator source."""

    path = Path(__file__).resolve().parent / "pr_perf_compare.py"
    spec = importlib.util.spec_from_file_location("_capture_committed_margins", path)
    if spec is None or spec.loader is None:
        raise CaptureValidationError(f"cannot load margin authority {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ungateable: dict[str, float] = {}
    for key, reason in module.UNGATEABLE_BENCHMARKS.items():
        match = re.search(r"margin (\d+)%", reason)
        if match is None:
            raise CaptureValidationError(
                f"cannot parse committed ungateable margin for {key!r}"
            )
        ungateable[_margin_key(key)] = int(match.group(1)) / 100
    return {
        "gated": {
            _margin_key(key): float(value)
            for key, value in module.PER_BENCHMARK_TIMING_MARGIN.items()
        },
        "ungateable": ungateable,
    }


def validate_capture(
    artifact_paths: Iterable[Path],
    *,
    requested_sha: str,
    expected_keys: Iterable[Sequence[str]],
    metadata_paths: Iterable[Path] | None = None,
    declared_regime_keys: Iterable[Sequence[str]] = (),
    baseline_records: Sequence[dict[str, Any]] = (),
    candidate_records: Sequence[dict[str, Any]] | None = None,
    repo_root: Path | None = None,
    committed_margins: dict[str, Any] | None = None,
) -> CaptureResult:
    """Validate capture evidence and return an in-memory append candidate."""

    root = (repo_root or Path.cwd()).resolve()
    sha = _resolve_capture_sha(requested_sha, root)
    expected = normalize_keys(expected_keys)
    artifact_list = [Path(path) for path in artifact_paths]
    if len(artifact_list) != CAPTURE_COUNT:
        raise CaptureValidationError(
            f"exactly {CAPTURE_COUNT} capture artifacts are required; got {len(artifact_list)}"
        )
    if metadata_paths is None:
        raise CaptureValidationError(
            f"exactly {CAPTURE_COUNT} capture metadata artifacts are required"
        )
    metadata_list = [Path(path) for path in metadata_paths]
    if len(metadata_list) != CAPTURE_COUNT:
        raise CaptureValidationError(
            f"exactly {CAPTURE_COUNT} capture metadata artifacts are required; got {len(metadata_list)}"
        )
    metadata = load_capture_metadata(metadata_list)
    seen_matrix_runs: set[int] = set()
    workflow_identity: tuple[str, str] | None = None
    for index, fields in enumerate(metadata, start=1):
        matrix_run = fields["matrix_run"]
        if not matrix_run.isdigit() or not 1 <= int(matrix_run) <= CAPTURE_COUNT:
            raise CaptureValidationError(
                f"metadata {index} has matrix_run outside 1..{CAPTURE_COUNT}"
            )
        run_number = int(matrix_run)
        if run_number in seen_matrix_runs:
            raise CaptureValidationError(f"capture metadata duplicates matrix_run {run_number}")
        seen_matrix_runs.add(run_number)
        capture_sha = fields["capture_sha"].lower()
        checked_out_sha = fields["checked_out_sha"].lower()
        if not SHA_RE.fullmatch(capture_sha) or capture_sha != sha:
            raise CaptureValidationError(
                f"metadata {index} does not carry requested capture SHA {sha}"
            )
        if not SHA_RE.fullmatch(checked_out_sha) or checked_out_sha != sha:
            raise CaptureValidationError(
                f"metadata {index} does not carry checked-out SHA {sha}"
            )
        identity = (fields["workflow_run_id"], fields["workflow_run_attempt"])
        if not all(value.isdigit() for value in identity):
            raise CaptureValidationError(
                f"metadata {index} has a non-numeric workflow run identity"
            )
        if workflow_identity is None:
            workflow_identity = identity
        elif identity != workflow_identity:
            raise CaptureValidationError(
                "capture metadata must share one workflow run and attempt"
            )
    if seen_matrix_runs != set(range(1, CAPTURE_COUNT + 1)):
        raise CaptureValidationError(
            f"capture metadata must contain exactly matrix_run 1..{CAPTURE_COUNT}"
        )

    expected_regime_keys = normalize_keys(declared_regime_keys) if declared_regime_keys else set()
    undeclared_capture_keys = expected_regime_keys - expected
    if undeclared_capture_keys:
        raise CaptureValidationError(
            f"regime registry contains keys absent from benchmark registry: {sorted(undeclared_capture_keys)!r}"
        )
    per_artifact: list[list[dict[str, Any]]] = []
    for artifact_index, path in enumerate(artifact_list, start=1):
        rows = _read_ndjson_file(path, source=str(path))
        if not rows:
            raise CaptureValidationError(f"capture artifact {artifact_index} is empty")
        artifact_keys = [_key(row) for row in rows]
        if len(artifact_keys) != len(set(artifact_keys)):
            raise CaptureValidationError(
                f"capture artifact {artifact_index} contains a duplicate benchmark key"
            )
        if set(artifact_keys) != expected:
            raise CaptureValidationError(
                f"capture artifact {artifact_index} is missing benchmark keys or contains unexpected keys"
            )
        per_artifact.append(rows)
    records = [record for rows in per_artifact for record in rows]
    if not records:
        raise CaptureValidationError("capture artifacts are empty")

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
        metrics = record.get("metrics")
        if not isinstance(metrics, dict) or "rust_over_oracle_ratio" not in metrics:
            raise CaptureValidationError(
                f"capture row {index} is missing rust_over_oracle_ratio"
            )
        for metric_name, metric_value in metrics.items():
            if (
                isinstance(metric_value, bool)
                or not isinstance(metric_value, (int, float))
                or not math.isfinite(float(metric_value))
                or float(metric_value) <= 0
            ):
                raise CaptureValidationError(
                    f"capture row {index} metric {metric_name!r} must be finite and positive"
                )
        run_identity = (key, timestamp)
        if run_identity in seen_runs:
            raise CaptureValidationError(
                f"capture contains duplicate run identity {key!r} at timestamp {timestamp!r}"
            )
        seen_runs.add(run_identity)
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
    for key in expected:
        identities: set[str] = set()
        for record in records:
            if _key(record) != key:
                continue
            regime = record.get("measurement_regime")
            if key in expected_regime_keys and regime is None:
                raise CaptureValidationError(
                    f"benchmark {key!r} requires current measurement regime metadata"
                )
            if regime is None:
                identities.add(LEGACY_REGIME_IDENTITY)
            else:
                identities.add(str(regime["fingerprint"]).lower())
        if len(identities) != 1:
            raise CaptureValidationError(
                f"benchmark {key!r} has mixed measurement regimes"
            )
    derived_margins = _validate_margins(candidate, committed_margins)
    regimes = sorted({
        str(
            (record.get("measurement_regime") or {}).get(
                "fingerprint", LEGACY_REGIME_IDENTITY
            )
        )
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


def validate_independent_capture(
    artifact_path: Path,
    *,
    requested_sha: str,
    capture_sha: str,
    expected_keys: Iterable[Sequence[str]],
    candidate_records: Sequence[dict[str, Any]],
    repo_root: Path | None = None,
    declared_regime_keys: Iterable[Sequence[str]] = (),
) -> list[dict[str, Any]]:
    """Compare one independently captured commit against a candidate baseline.

    This is deliberately separate from the ordinary PR comparator. A reset
    candidate must prove that a different, resolvable commit can be compared
    against the proposed append; normal PRs continue to read origin/main in
    ``pr-perf-check.yml``.
    """

    root = (repo_root or Path.cwd()).resolve()
    capture = _resolve_capture_sha(capture_sha, root)
    current = _resolve_capture_sha(requested_sha, root)
    if current == capture:
        raise CaptureValidationError(
            "independent current capture must use a different commit than the five-run capture"
        )

    expected = normalize_keys(expected_keys)
    records = _read_ndjson_file(Path(artifact_path), source=str(artifact_path))
    if not records:
        raise CaptureValidationError("independent current capture is empty")
    if len(records) != len(expected) or {_key(record) for record in records} != expected:
        raise CaptureValidationError(
            "independent current capture must contain exactly one row for every benchmark"
        )

    for index, record in enumerate(records, start=1):
        row_sha = record.get("git_commit")
        if not isinstance(row_sha, str) or not SHA_RE.fullmatch(row_sha):
            raise CaptureValidationError(
                f"independent capture row {index} has an invalid or symbolic git_commit"
            )
        if row_sha.lower() != current:
            raise CaptureValidationError(
                f"independent capture rows must use requested SHA {current}; "
                f"row {index} uses {row_sha!r}"
            )
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise CaptureValidationError(
                f"independent capture row {index} has no valid timestamp"
            )
        metrics = record.get("metrics")
        if not isinstance(metrics, dict) or "rust_over_oracle_ratio" not in metrics:
            raise CaptureValidationError(
                f"independent capture row {index} is missing rust_over_oracle_ratio"
            )
        for metric_name, metric_value in metrics.items():
            if (
                isinstance(metric_value, bool)
                or not isinstance(metric_value, (int, float))
                or not math.isfinite(float(metric_value))
                or float(metric_value) <= 0
            ):
                raise CaptureValidationError(
                    f"independent capture row {index} metric {metric_name!r} "
                    "must be finite and positive"
                )

    expected_regime_keys = (
        normalize_keys(declared_regime_keys) if declared_regime_keys else set()
    )
    if expected_regime_keys - expected:
        raise CaptureValidationError(
            "regime registry contains keys absent from benchmark registry"
        )
    for key in expected:
        for record in records:
            if _key(record) != key:
                continue
            if key in expected_regime_keys and record.get("measurement_regime") is None:
                raise CaptureValidationError(
                    f"independent benchmark {key!r} requires current measurement regime metadata"
                )

    _verify_regime_sources(records, root, current)
    baselines = load_main_baselines(list(candidate_records))
    results = compare(records, baselines)
    failures = gate_failures(results)
    if failures:
        raise CaptureValidationError(
            "independent current capture does not validate against candidate baseline: "
            + "; ".join(failures)
        )
    return results


def aggregate_capture(
    artifact_paths: Iterable[Path],
    *,
    requested_sha: str,
    expected_keys: Iterable[Sequence[str]],
    metadata_paths: Iterable[Path] | None = None,
    declared_regime_keys: Iterable[Sequence[str]] = (),
    baseline_records: Sequence[dict[str, Any]] = (),
    candidate_records: Sequence[dict[str, Any]] | None = None,
    repo_root: Path | None = None,
    committed_margins: dict[str, Any] | None = None,
    independent_artifact: Path | None = None,
    independent_sha: str | None = None,
    output_dir: Path | None = None,
) -> CaptureResult:
    """Validate a capture and optionally write only review artifacts."""

    result = validate_capture(
        artifact_paths,
        requested_sha=requested_sha,
        expected_keys=expected_keys,
        metadata_paths=metadata_paths,
        declared_regime_keys=declared_regime_keys,
        baseline_records=baseline_records,
        candidate_records=candidate_records,
        repo_root=repo_root,
        committed_margins=committed_margins,
    )
    if (independent_artifact is None) != (independent_sha is None):
        raise CaptureValidationError(
            "independent_artifact and independent_sha must be supplied together"
        )
    if independent_artifact is not None and independent_sha is not None:
        independent_results = validate_independent_capture(
            independent_artifact,
            requested_sha=independent_sha,
            capture_sha=requested_sha,
            expected_keys=expected_keys,
            candidate_records=result.candidate_records,
            repo_root=repo_root,
            declared_regime_keys=declared_regime_keys,
        )
        result.manifest["independent_current"] = {
            "capture_sha": independent_sha.lower(),
            "validated": True,
            "results": independent_results,
        }
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
    parser.add_argument(
        "--independent-current", type=Path, default=None,
        help="one current-capture NDJSON to validate against the candidate baseline",
    )
    parser.add_argument(
        "--independent-sha", default=None,
        help="immutable SHA for --independent-current; must differ from --capture-sha",
    )
    parser.add_argument("--metadata", type=Path, action="append", required=True)
    parser.add_argument("--key", type=_parse_cli_key, action="append", dest="keys", default=None)
    parser.add_argument("artifacts", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        keys = args.keys if args.keys is not None else registered_keys_from_source(args.registry)
        declared_regimes = declared_regime_keys_from_source(args.registry)
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
            metadata_paths=args.metadata,
            declared_regime_keys=declared_regimes,
            baseline_records=baseline,
            candidate_records=candidate,
            repo_root=args.repo_root,
            committed_margins=margins,
            independent_artifact=args.independent_current,
            independent_sha=args.independent_sha,
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
