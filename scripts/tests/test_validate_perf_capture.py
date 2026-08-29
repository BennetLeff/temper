"""Proof-first tests for the immutable performance capture validator."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validate_perf_capture as validator  # noqa: E402
from validate_perf_capture import (  # noqa: E402
    CaptureValidationError,
    aggregate_capture,
    parse_capture_metadata,
    parse_ndjson,
    validate_append_only,
    validate_baseline_refresh,
    validate_capture,
    validate_independent_capture,
)

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "89abcdef0123456789abcdef0123456789abcdef"
KEYS = {
    ("demo", "synthetic", "ratio"),
    ("demo", "synthetic", "other"),
}


def _row(stage: str, *, sha: str = SHA, timestamp: str = "2026-08-29T00:00:00", value: float = 0.5) -> dict:
    return {
        "schema_version": 2,
        "timestamp": timestamp,
        "git_commit": sha,
        "board": "synthetic",
        "stage": stage,
        "module": "demo",
        "metrics": {"rust_over_oracle_ratio": value},
    }


def _capture_rows(*, sha: str = SHA) -> list[dict]:
    rows: list[dict] = []
    for run in range(5):
        for index, stage in enumerate(("ratio", "other")):
            rows.append(
                _row(
                    stage,
                    sha=sha,
                    timestamp=f"2026-08-29T00:0{run}:{index:02d}",
                    value=0.5 + run * 0.001,
                )
            )
    return rows


def _write_ndjson(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _write_bundle(tmp_path: Path, rows: list[dict], *, workflow_run_id: str = "123") -> tuple[list[Path], list[Path]]:
    artifacts: list[Path] = []
    metadata: list[Path] = []
    for run in range(1, 6):
        artifact = tmp_path / f"perf-capture-{run}.ndjson"
        run_rows = [row for row in rows if row["timestamp"].startswith(f"2026-08-29T00:0{run - 1}:")]
        artifacts.append(_write_ndjson(artifact, run_rows))
        sidecar = tmp_path / f"capture-{run}.metadata"
        sidecar.write_text(
            f"capture_sha={rows[0]['git_commit']}\n"
            f"checked_out_sha={rows[0]['git_commit']}\n"
            f"matrix_run={run}\n"
            f"workflow_run_id={workflow_run_id}\n"
            "workflow_run_attempt=1\n",
            encoding="utf-8",
        )
        metadata.append(sidecar)
    return artifacts, metadata


def _git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "tracked.txt").write_text("stable\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "base"],
        check=True,
    )
    return repo, subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def test_valid_five_run_capture_aggregates_without_mutating_baseline(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = _capture_rows(sha=capture_sha)
    artifacts, metadata = _write_bundle(tmp_path, rows)
    baseline = [_row("ratio", sha="f" * 40, timestamp="2026-08-28T00:00:00")]

    result = validate_capture(
        artifacts,
        requested_sha=capture_sha,
        expected_keys=KEYS,
        metadata_paths=metadata,
        baseline_records=baseline,
        repo_root=repo,
        committed_margins={"gated": {}, "ungateable": {}},
    )

    assert len(result.records) == 10
    assert result.candidate_records[:1] == baseline
    assert result.candidate_records[1:] == rows
    assert result.manifest["capture_sha"] == capture_sha

    output = aggregate_capture(
        artifacts,
        requested_sha=capture_sha,
        expected_keys=KEYS,
        metadata_paths=metadata,
        baseline_records=baseline,
        repo_root=repo,
        committed_margins={"gated": {}, "ungateable": {}},
        output_dir=tmp_path / "evidence",
    )
    assert output.patch_path and output.patch_path.is_file()
    assert output.manifest_path and output.manifest_path.is_file()
    assert output.patch_path.read_text().count("\n") == 10


def test_malformed_sha_is_rejected() -> None:
    with pytest.raises(CaptureValidationError, match="40-hex"):
        validate_capture([], requested_sha="main", expected_keys=KEYS)


def test_symbolic_sha_is_rejected_before_git_lookup() -> None:
    with pytest.raises(CaptureValidationError, match="40-hex"):
        validate_capture([], requested_sha="HEAD", expected_keys=KEYS)


def test_unresolved_sha_is_rejected(tmp_path: Path) -> None:
    repo, _ = _git_repo(tmp_path)
    with pytest.raises(CaptureValidationError, match="does not resolve"):
        validate_capture([], requested_sha=SHA, expected_keys=KEYS, repo_root=repo)


def test_mixed_sha_is_rejected(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = _capture_rows(sha=capture_sha)
    artifacts, metadata = _write_bundle(tmp_path, rows)
    rows[0]["git_commit"] = OTHER_SHA
    _write_ndjson(artifacts[0], rows[:2])
    with pytest.raises(CaptureValidationError, match="one capture SHA"):
        validate_capture(artifacts, requested_sha=capture_sha, expected_keys=KEYS, metadata_paths=metadata, repo_root=repo)


def test_partial_benchmark_set_is_rejected(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = [row for row in _capture_rows(sha=capture_sha) if row["stage"] == "ratio"]
    artifacts, metadata = _write_bundle(tmp_path, rows)
    with pytest.raises(CaptureValidationError, match="missing benchmark keys"):
        validate_capture(artifacts, requested_sha=capture_sha, expected_keys=KEYS, metadata_paths=metadata, repo_root=repo)


def test_duplicate_rows_are_rejected(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = _capture_rows(sha=capture_sha)
    rows[-1] = rows[-2].copy()
    artifacts, metadata = _write_bundle(tmp_path, rows)
    with pytest.raises(CaptureValidationError, match="duplicate"):
        validate_capture(artifacts, requested_sha=capture_sha, expected_keys=KEYS, metadata_paths=metadata, repo_root=repo)


def test_malformed_ndjson_is_rejected() -> None:
    with pytest.raises(CaptureValidationError, match="line 2.*not JSON"):
        parse_ndjson('{"ok": true}\nnot-json\n', source="capture")


def test_metadata_requires_one_matrix_run_per_artifact(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    artifacts, metadata = _write_bundle(tmp_path, _capture_rows(sha=capture_sha))
    metadata[1].write_text(
        metadata[0].read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(CaptureValidationError, match="duplicates matrix_run"):
        validate_capture(
            artifacts,
            requested_sha=capture_sha,
            expected_keys=KEYS,
            metadata_paths=metadata,
            repo_root=repo,
            committed_margins={"gated": {}, "ungateable": {}},
        )


def test_metadata_parser_rejects_unknown_or_missing_fields() -> None:
    with pytest.raises(CaptureValidationError, match="missing metadata fields"):
        parse_capture_metadata("capture_sha=abc\n")
    with pytest.raises(CaptureValidationError, match="unsupported metadata fields"):
        parse_capture_metadata(
            "capture_sha=a\nchecked_out_sha=b\nmatrix_run=1\n"
            "workflow_run_id=2\nworkflow_run_attempt=1\nextra=x\n"
        )


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), "1", True])
def test_non_finite_or_non_positive_metrics_are_rejected(tmp_path: Path, value: object) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = _capture_rows(sha=capture_sha)
    rows[0]["metrics"]["rust_over_oracle_ratio"] = value
    artifacts, metadata = _write_bundle(tmp_path, rows)
    with pytest.raises(CaptureValidationError, match="finite and positive"):
        validate_capture(
            artifacts,
            requested_sha=capture_sha,
            expected_keys=KEYS,
            metadata_paths=metadata,
            repo_root=repo,
            committed_margins={"gated": {}, "ungateable": {}},
        )


def test_declared_regime_is_required_and_uniform(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = _capture_rows(sha=capture_sha)
    artifacts, metadata = _write_bundle(tmp_path, rows)
    with pytest.raises(CaptureValidationError, match="requires current"):
        validate_capture(
            artifacts,
            requested_sha=capture_sha,
            expected_keys=KEYS,
            metadata_paths=metadata,
            declared_regime_keys={("demo", "synthetic", "ratio")},
            repo_root=repo,
            committed_margins={"gated": {}, "ungateable": {}},
        )

    regime_metadata = {
        "algorithm": "sha256-canonical-json-v1",
        "arms": {},
        "harness": {},
    }
    regime = {
        "fingerprint": hashlib.sha256(
            json.dumps(regime_metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "metadata": regime_metadata,
    }
    for row in rows[:1]:
        row["measurement_regime"] = regime
    artifacts, metadata = _write_bundle(tmp_path, rows)
    with pytest.raises(CaptureValidationError, match="mixed measurement regimes"):
        validate_capture(
            artifacts,
            requested_sha=capture_sha,
            expected_keys=KEYS,
            metadata_paths=metadata,
            repo_root=repo,
            committed_margins={"gated": {}, "ungateable": {}},
        )


def test_capture_tree_cannot_replace_trusted_margin_authority(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    malicious = repo / "scripts" / "pr_perf_compare.py"
    malicious.parent.mkdir()
    malicious.write_text("raise RuntimeError('capture code executed')\n", encoding="utf-8")
    (malicious.parent / "validate_perf_capture.py").write_text(
        "raise RuntimeError('capture validator executed')\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "scripts"],
        check=True,
    )
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Test", "-c",
            "user.email=test@example.com", "commit", "-qm", "malicious capture code",
        ],
        check=True,
    )
    capture_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    artifacts, metadata = _write_bundle(tmp_path, _capture_rows(sha=capture_sha))
    result = validator.validate_capture(
        artifacts,
        requested_sha=capture_sha,
        expected_keys=KEYS,
        metadata_paths=metadata,
        repo_root=repo,
        committed_margins={"gated": {}, "ungateable": {}},
    )
    assert result.manifest["capture_sha"] == capture_sha


def test_changed_registered_source_is_rejected_for_merge_commit(tmp_path: Path) -> None:
    repo, base_sha = _git_repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "branch", "-M", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-qb", "side"], check=True)
    (repo / "tracked.txt").write_text("side\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "side"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "main"], check=True)
    (repo / "main.txt").write_text("main\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "main.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "main"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "merge", "--no-ff", "-m", "merge", "side"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    capture_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    digest = hashlib.sha256((repo / "tracked.txt").read_bytes()).hexdigest()
    metadata = {
        "algorithm": "sha256-canonical-json-v1",
        "arms": {"rust": {"sources": [{"path": "tracked.txt", "sha256": digest}]}},
        "harness": {},
    }
    regime = {
        "fingerprint": hashlib.sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "metadata": metadata,
    }
    rows = _capture_rows(sha=capture_sha)
    for row in rows:
        row["measurement_regime"] = regime
    artifacts, sidecars = _write_bundle(tmp_path, rows)
    with pytest.raises(CaptureValidationError, match="changed registered paths"):
        validate_capture(
            artifacts,
            requested_sha=capture_sha,
            expected_keys=KEYS,
            metadata_paths=sidecars,
            repo_root=repo,
            committed_margins={"gated": {}, "ungateable": {}},
        )
    assert base_sha != capture_sha


def test_changed_registered_source_is_rejected(tmp_path: Path) -> None:
    repo, base_sha = _git_repo(tmp_path)
    source = repo / "tracked.txt"
    source.write_text("changed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "capture"],
        check=True,
    )
    capture_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    rows = _capture_rows(sha=capture_sha)
    metadata = {
        "algorithm": "sha256-canonical-json-v1",
        "arms": {"rust": {"sources": [{"path": "tracked.txt", "sha256": "0" * 64}]}},
        "harness": {},
    }
    for row in rows:
        row["measurement_regime"] = {
            "fingerprint": hashlib.sha256(
                json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "metadata": metadata,
        }
    artifacts, metadata = _write_bundle(tmp_path, rows)
    with pytest.raises(CaptureValidationError, match="changed registered paths"):
        validate_capture(artifacts, requested_sha=capture_sha, expected_keys=KEYS, metadata_paths=metadata, repo_root=repo)

    assert base_sha != capture_sha


def test_non_append_candidate_is_rejected() -> None:
    baseline = [_row("ratio", timestamp="2026-08-28T00:00:00")]
    candidate = [dict(baseline[0], metrics={"rust_over_oracle_ratio": 99.0}), _row("other")]
    with pytest.raises(CaptureValidationError, match="append-only"):
        validate_append_only(baseline, candidate)


def test_unsupported_margin_change_is_rejected(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    artifacts, metadata = _write_bundle(tmp_path, _capture_rows(sha=capture_sha))
    with pytest.raises(CaptureValidationError, match="margin"):
        validate_capture(
            artifacts,
            requested_sha=capture_sha,
            expected_keys=KEYS,
            metadata_paths=metadata,
            repo_root=repo,
            committed_margins={"gated": {"demo/ratio": 0.99}, "ungateable": {}},
        )


def test_candidate_baseline_must_preserve_existing_prefix(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    artifacts, metadata = _write_bundle(tmp_path, _capture_rows(sha=capture_sha))
    baseline = [_row("ratio", timestamp="2026-08-28T00:00:00")]
    candidate = [dict(baseline[0], timestamp="edited")] + _capture_rows(sha=capture_sha)
    with pytest.raises(CaptureValidationError, match="append-only"):
        validate_capture(
            artifacts,
            requested_sha=capture_sha,
            expected_keys=KEYS,
            metadata_paths=metadata,
            baseline_records=baseline,
            candidate_records=candidate,
            repo_root=repo,
        )


def _commit_current_revision(repo: Path) -> str:
    (repo / "current.txt").write_text("current\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "current.txt"], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Test", "-c",
            "user.email=test@example.com", "commit", "-qm", "current",
        ],
        check=True,
    )
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()


def test_independent_current_capture_is_compared_to_candidate_baseline(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    independent_sha = _commit_current_revision(repo)
    candidate = _capture_rows(sha=capture_sha)
    current = [_row(stage, sha=independent_sha, value=0.5) for stage in ("ratio", "other")]
    artifact = _write_ndjson(tmp_path / "perf-current.ndjson", current)

    results = validate_independent_capture(
        artifact,
        requested_sha=independent_sha,
        capture_sha=capture_sha,
        expected_keys=KEYS,
        candidate_records=candidate,
        repo_root=repo,
    )

    assert all(result["status"] == "OK" for result in results)


def test_independent_current_capture_must_use_a_different_sha(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    current = [_row(stage, sha=capture_sha, value=0.5) for stage in ("ratio", "other")]
    artifact = _write_ndjson(tmp_path / "perf-current.ndjson", current)
    with pytest.raises(CaptureValidationError, match="different commit"):
        validate_independent_capture(
            artifact,
            requested_sha=capture_sha,
            capture_sha=capture_sha,
            expected_keys=KEYS,
            candidate_records=_capture_rows(sha=capture_sha),
            repo_root=repo,
        )


def test_independent_current_capture_rejects_candidate_baseline_regression(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    independent_sha = _commit_current_revision(repo)
    current = [_row(stage, sha=independent_sha, value=0.8) for stage in ("ratio", "other")]
    artifact = _write_ndjson(tmp_path / "perf-current.ndjson", current)
    with pytest.raises(CaptureValidationError, match="does not validate"):
        validate_independent_capture(
            artifact,
            requested_sha=independent_sha,
            capture_sha=capture_sha,
            expected_keys=KEYS,
            candidate_records=_capture_rows(sha=capture_sha),
            repo_root=repo,
        )


def test_aggregate_capture_records_independent_validation_in_manifest(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    independent_sha = _commit_current_revision(repo)
    rows = _capture_rows(sha=capture_sha)
    artifacts, metadata = _write_bundle(tmp_path, rows)
    current = [_row(stage, sha=independent_sha, value=0.5) for stage in ("ratio", "other")]
    current_artifact = _write_ndjson(tmp_path / "perf-current.ndjson", current)

    result = aggregate_capture(
        artifacts,
        requested_sha=capture_sha,
        expected_keys=KEYS,
        metadata_paths=metadata,
        baseline_records=[_row("ratio", sha="f" * 40, timestamp="2026-08-28T00:00:00")],
        repo_root=repo,
        committed_margins={"gated": {}, "ungateable": {}},
        independent_artifact=current_artifact,
        independent_sha=independent_sha,
    )

    assert result.manifest["independent_current"]["validated"] is True
    assert result.manifest["independent_current"]["capture_sha"] == independent_sha


def _write_refresh_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    repo, capture_sha = _git_repo(tmp_path)
    registry = repo / "benchmarks" / "perf_ab.py"
    registry.parent.mkdir()
    registry.write_text(
        "_BENCHMARKS = {('demo', 'ratio'): object, ('demo', 'other'): object}\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "benchmarks"], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Test", "-c",
            "user.email=test@example.com", "commit", "-qm", "registry",
        ],
        check=True,
    )
    # The capture must name the registry commit, which is now the repository
    # head; the independent commit is deliberately a different earlier SHA.
    capture_sha = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    rows = _capture_rows(sha=capture_sha)
    root = repo / "power_pcb_dataset" / "metrics" / "perf_ab_refresh"
    root.mkdir(parents=True)
    artifacts, _sidecars = _write_bundle(root, rows)
    baseline_path = repo / "power_pcb_dataset" / "metrics" / "perf_ab_baseline.jsonl"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(_row("ratio", sha="f" * 40, timestamp="2026-08-28T00:00:00")) + "\n",
        encoding="utf-8",
    )
    candidate_path = repo / "power_pcb_dataset" / "metrics" / "perf_ab_baseline.candidate.jsonl"
    candidate_rows = [
        _row("ratio", sha="f" * 40, timestamp="2026-08-28T00:00:00"),
        *rows,
    ]
    candidate_path.write_text(
        "".join(json.dumps(row) + "\n" for row in candidate_rows), encoding="utf-8"
    )
    append_text = "".join(validator._canonical(row) + "\n" for row in rows)
    manifest = {
        "schema_version": 2,
        "source": "measured-live",
        "evidence_source": "github-actions-artifact",
        "baseline_path": "power_pcb_dataset/metrics/perf_ab_baseline.jsonl",
        "candidate_baseline_path": "power_pcb_dataset/metrics/perf_ab_baseline.candidate.jsonl",
        "benchmark_owned_prefixes": list(validator.BASELINE_REFRESH_PROTECTED_PREFIXES),
        "primary_capture": {
            "capture_sha": capture_sha,
            "captures": [
                {
                    "workflow_run_id": str(123 + index),
                    "artifact_id": str(101 + index),
                    "artifact": str(path.relative_to(repo)),
                    "artifact_sha256": validator._file_sha256(path),
                }
                for index, path in enumerate(artifacts)
            ],
        },
        "candidate_append_sha256": hashlib.sha256(append_text.encode()).hexdigest(),
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return repo, baseline_path, candidate_path, str(manifest_path.relative_to(repo)), str(registry.relative_to(repo))


def test_baseline_refresh_requires_five_distinct_immutable_captures(tmp_path: Path) -> None:
    repo, baseline, candidate, manifest_rel, registry_rel = _write_refresh_fixture(tmp_path)
    result = validate_baseline_refresh(
        baseline_path=baseline.relative_to(repo),
        candidate_path=candidate.relative_to(repo),
        manifest_path=Path(manifest_rel),
        registry_path=Path(registry_rel),
        repo_root=repo,
        committed_margins={"gated": {}, "ungateable": {}},
        changed_paths={
            str(candidate.relative_to(repo)), manifest_rel,
            *[str(path.relative_to(repo)) for path in (repo / "power_pcb_dataset/metrics/perf_ab_refresh").iterdir() if path.name != "manifest.json"],
        },
    )
    assert result.manifest["capture_runs"] == ["123", "124", "125", "126", "127"]

    raw = json.loads((repo / manifest_rel).read_text(encoding="utf-8"))
    raw["primary_capture"]["captures"][1]["workflow_run_id"] = "123"
    (repo / manifest_rel).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CaptureValidationError, match="five distinct workflow runs"):
        validate_baseline_refresh(
            baseline_path=baseline.relative_to(repo),
            candidate_path=candidate.relative_to(repo),
            manifest_path=Path(manifest_rel),
            registry_path=Path(registry_rel),
            repo_root=repo,
            committed_margins={"gated": {}, "ungateable": {}},
        )


def test_baseline_refresh_rejects_owned_input_change_and_digest_substitution(tmp_path: Path) -> None:
    repo, baseline, candidate, manifest_rel, registry_rel = _write_refresh_fixture(tmp_path)
    common = {
        "baseline_path": baseline.relative_to(repo),
        "candidate_path": candidate.relative_to(repo),
        "manifest_path": Path(manifest_rel),
        "registry_path": Path(registry_rel),
        "repo_root": repo,
    }
    with pytest.raises(CaptureValidationError, match="evidence manifest"):
        validate_baseline_refresh(
            **common,
            changed_paths={str(candidate.relative_to(repo))},
        )
    raw = json.loads((repo / manifest_rel).read_text(encoding="utf-8"))
    raw["primary_capture"]["captures"][0]["artifact_sha256"] = "0" * 64
    (repo / manifest_rel).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CaptureValidationError, match="digest mismatch"):
        validate_baseline_refresh(
            **common, committed_margins={"gated": {}, "ungateable": {}}
        )


@pytest.mark.parametrize("rewrite", ["reformat", "duplicate-key"])
def test_baseline_refresh_rejects_semantically_equal_baseline_rewrite(
    tmp_path: Path, rewrite: str
) -> None:
    repo, baseline, candidate, manifest_rel, registry_rel = _write_refresh_fixture(tmp_path)
    original, remainder = candidate.read_bytes().split(b"\n", 1)
    parsed = json.loads(original)
    if rewrite == "reformat":
        replacement = json.dumps(parsed, separators=(",", ":")).encode("utf-8")
    else:
        replacement = original.replace(
            b'"stage": "ratio"', b'"stage": "ratio", "stage": "ratio"', 1
        )
    assert replacement != original
    assert json.loads(replacement) == parsed
    candidate.write_bytes(replacement + b"\n" + remainder)

    with pytest.raises(CaptureValidationError, match="exact byte append"):
        validate_baseline_refresh(
            baseline_path=baseline.relative_to(repo),
            candidate_path=candidate.relative_to(repo),
            manifest_path=Path(manifest_rel),
            registry_path=Path(registry_rel),
            repo_root=repo,
            committed_margins={"gated": {}, "ungateable": {}},
        )


def test_baseline_refresh_rejects_benchmark_input_changed_after_capture(tmp_path: Path) -> None:
    repo, _baseline, candidate, manifest_rel, registry_rel = _write_refresh_fixture(tmp_path)
    registry = repo / registry_rel
    registry.write_text(registry.read_text(encoding="utf-8") + "# changed after capture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", registry_rel], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "-c", "user.name=Test", "-c",
            "user.email=test@example.com", "commit", "-qm", "changed benchmark",
        ],
        check=True,
    )
    with pytest.raises(CaptureValidationError, match="benchmark-owned inputs changed"):
        validate_baseline_refresh(
            baseline_path=Path("power_pcb_dataset/metrics/perf_ab_baseline.jsonl"),
            candidate_path=candidate.relative_to(repo),
            manifest_path=Path(manifest_rel),
            registry_path=Path(registry_rel),
            repo_root=repo,
        )


def test_baseline_refresh_rejects_paths_outside_repository(tmp_path: Path) -> None:
    repo, _baseline, candidate, manifest_rel, registry_rel = _write_refresh_fixture(tmp_path)
    with pytest.raises(CaptureValidationError, match="inside repository root"):
        validate_baseline_refresh(
            baseline_path=Path("/tmp/not-the-repository-baseline.jsonl"),
            candidate_path=candidate.relative_to(repo),
            manifest_path=Path(manifest_rel),
            registry_path=Path(registry_rel),
            repo_root=repo,
        )
