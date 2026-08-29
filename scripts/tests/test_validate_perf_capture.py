"""Proof-first tests for the immutable performance capture validator."""

from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_perf_capture import (  # noqa: E402
    CaptureValidationError,
    aggregate_capture,
    parse_ndjson,
    validate_append_only,
    validate_capture,
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
    artifact = _write_ndjson(tmp_path / "capture.ndjson", rows)
    baseline = [_row("ratio", sha="f" * 40, timestamp="2026-08-28T00:00:00")]

    result = validate_capture(
        [artifact],
        requested_sha=capture_sha,
        expected_keys=KEYS,
        baseline_records=baseline,
        repo_root=repo,
    )

    assert len(result.records) == 10
    assert result.candidate_records[:1] == baseline
    assert result.candidate_records[1:] == rows
    assert result.manifest["capture_sha"] == capture_sha

    output = aggregate_capture(
        [artifact],
        requested_sha=capture_sha,
        expected_keys=KEYS,
        baseline_records=baseline,
        repo_root=repo,
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
    rows[-1]["git_commit"] = OTHER_SHA
    artifact = _write_ndjson(tmp_path / "capture.ndjson", rows)
    with pytest.raises(CaptureValidationError, match="one capture SHA"):
        validate_capture([artifact], requested_sha=capture_sha, expected_keys=KEYS, repo_root=repo)


def test_partial_benchmark_set_is_rejected(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = [row for row in _capture_rows(sha=capture_sha) if row["stage"] == "ratio"]
    artifact = _write_ndjson(tmp_path / "capture.ndjson", rows)
    with pytest.raises(CaptureValidationError, match="missing benchmark keys"):
        validate_capture([artifact], requested_sha=capture_sha, expected_keys=KEYS, repo_root=repo)


def test_duplicate_rows_are_rejected(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    rows = _capture_rows(sha=capture_sha)
    rows[-1] = rows[-2].copy()
    artifact = _write_ndjson(tmp_path / "capture.ndjson", rows)
    with pytest.raises(CaptureValidationError, match="duplicate"):
        validate_capture([artifact], requested_sha=capture_sha, expected_keys=KEYS, repo_root=repo)


def test_malformed_ndjson_is_rejected() -> None:
    with pytest.raises(CaptureValidationError, match="line 2.*not JSON"):
        parse_ndjson('{"ok": true}\nnot-json\n', source="capture")


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
    rows[0]["measurement_regime"] = {
        "fingerprint": hashlib.sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "metadata": metadata,
    }
    artifact = _write_ndjson(tmp_path / "capture.ndjson", rows)
    with pytest.raises(CaptureValidationError, match="changed registered paths"):
        validate_capture([artifact], requested_sha=capture_sha, expected_keys=KEYS, repo_root=repo)

    assert base_sha != capture_sha


def test_non_append_candidate_is_rejected() -> None:
    baseline = [_row("ratio", timestamp="2026-08-28T00:00:00")]
    candidate = [dict(baseline[0], metrics={"rust_over_oracle_ratio": 99.0}), _row("other")]
    with pytest.raises(CaptureValidationError, match="append-only"):
        validate_append_only(baseline, candidate)


def test_unsupported_margin_change_is_rejected(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    artifact = _write_ndjson(tmp_path / "capture.ndjson", _capture_rows(sha=capture_sha))
    with pytest.raises(CaptureValidationError, match="margin"):
        validate_capture(
            [artifact],
            requested_sha=capture_sha,
            expected_keys=KEYS,
            repo_root=repo,
            committed_margins={"gated": {"demo/ratio": 0.99}, "ungateable": {}},
        )


def test_candidate_baseline_must_preserve_existing_prefix(tmp_path: Path) -> None:
    repo, capture_sha = _git_repo(tmp_path)
    artifact = _write_ndjson(tmp_path / "capture.ndjson", _capture_rows(sha=capture_sha))
    baseline = [_row("ratio", timestamp="2026-08-28T00:00:00")]
    candidate = [dict(baseline[0], timestamp="edited")] + _capture_rows(sha=capture_sha)
    with pytest.raises(CaptureValidationError, match="append-only"):
        validate_capture(
            [artifact],
            requested_sha=capture_sha,
            expected_keys=KEYS,
            baseline_records=baseline,
            candidate_records=candidate,
            repo_root=repo,
        )
