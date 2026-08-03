from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_required_checks import RequiredChecksError  # noqa: E402
from classify_changed_paths import main  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


SYNTHETIC_MANIFEST = {
    "version": 2,
    "trigger_paths": ["packages/**", "docs/plans/**", "pyproject.toml"],
    "required_contexts": ["Core Tests", "Type Check"],
    "job_triggers": {
        "Core Tests": {"id": "test", "paths": ["packages/temper-placer/**"]},
        "Type Check": {"id": "type-check", "paths": ["packages/temper-dsn/**"]},
    },
    "catch_all_paths": ["pyproject.toml"],
    "mapped_to_nothing": ["docs/**", "**/TRACEABILITY"],
}


def _make_repo(root: Path) -> tuple[Path, str, str]:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test")
    _git(repo, "config", "user.name", "test")
    (repo / "file.txt").write_text("base")
    (repo / ".github").mkdir()
    (repo / ".github/required-checks.json").write_text(json.dumps(SYNTHETIC_MANIFEST))
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base, base


def _run_classifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo: Path, base: str, head: str
) -> Path:
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"base": {"sha": base}, "head": {"sha": head}}})
    )
    output = tmp_path / "output.txt"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.chdir(repo)
    assert main() == 0
    return output


def _commit(repo: Path, path: str, content: str) -> str:
    full = repo / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "change")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def test_docs_only_change_skips_every_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base, _ = _make_repo(tmp_path)
    head = _commit(repo, "docs/plans/2026-08-02-x.md", "plan")
    output = _run_classifier(tmp_path, monkeypatch, repo, base, head)
    lines = [line for line in output.read_text().splitlines() if line]
    assert lines
    assert all(line.endswith("=false") for line in lines)


def test_package_change_runs_consuming_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base, _ = _make_repo(tmp_path)
    head = _commit(repo, "packages/temper-placer/src/example.py", "x = 1")
    output = _run_classifier(tmp_path, monkeypatch, repo, base, head)
    decisions = dict(line.split("=", 1) for line in output.read_text().splitlines() if line)
    assert decisions == {"test": "true", "type-check": "false"}


def test_disjoint_crate_change_runs_only_its_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, base, _ = _make_repo(tmp_path)
    head = _commit(repo, "packages/temper-dsn/src/lib.rs", "fn main() {}")
    output = _run_classifier(tmp_path, monkeypatch, repo, base, head)
    decisions = dict(line.split("=", 1) for line in output.read_text().splitlines() if line)
    assert decisions == {"test": "false", "type-check": "true"}


def test_unmapped_path_runs_every_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base, _ = _make_repo(tmp_path)
    head = _commit(repo, "README.md", "readme")
    output = _run_classifier(tmp_path, monkeypatch, repo, base, head)
    lines = [line for line in output.read_text().splitlines() if line]
    assert all(line.endswith("=true") for line in lines)


def test_catch_all_path_runs_every_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base, _ = _make_repo(tmp_path)
    head = _commit(repo, "pyproject.toml", "x")
    output = _run_classifier(tmp_path, monkeypatch, repo, base, head)
    lines = [line for line in output.read_text().splitlines() if line]
    assert all(line.endswith("=true") for line in lines)


def test_unreadable_manifest_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, base, _ = _make_repo(tmp_path)
    (repo / ".github/required-checks.json").write_text("{not json")
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"base": {"sha": base}, "head": {"sha": base}}})
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.chdir(repo)
    with pytest.raises(RequiredChecksError):
        main()  # manifest failure is intentionally fail-closed, not caught
