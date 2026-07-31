from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_required_checks import (  # noqa: E402
    Manifest,
    _run,
    evaluate_check_runs,
    load_manifest,
    load_workflow_trigger_paths,
    matching_patterns,
    path_matches,
    required_contexts_for_files,
    validate_trigger_manifest,
)

CONTEXTS = ("Core Tests", "Type Check")


def manifest() -> Manifest:
    return Manifest(
        trigger_paths=("packages/**", "pcb/*.kicad_pro", ".loc-allowlist.txt"),
        required_contexts=CONTEXTS,
        timeout_seconds=30,
        poll_interval_seconds=5,
    )


def run(name: str, status: str = "completed", conclusion: str | None = "success", run_id: int = 1) -> dict[str, object]:
    return {
        "id": run_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "updated_at": f"2026-07-30T00:00:0{run_id}Z",
    }


def test_path_matching_handles_repo_globs_and_root_double_star() -> None:
    assert path_matches("packages/temper-placer/src/x.py", "packages/**")
    assert path_matches("pcb/temper.kicad_pro", "pcb/*.kicad_pro")
    assert path_matches("TRACEABILITY", "**/TRACEABILITY")
    assert not path_matches("pcb/nested/temper.kicad_pro", "pcb/*.kicad_pro")


def test_matching_patterns_preserves_manifest_order() -> None:
    assert matching_patterns(
        ("pcb/temper.kicad_pro", "packages/x.py"), manifest().trigger_paths
    ) == ("packages/**", "pcb/*.kicad_pro")


def test_no_matching_path_is_an_explicit_legitimate_skip() -> None:
    assert required_contexts_for_files(("CHANGELOG.md",), manifest()) == ()


def test_relevant_path_requires_all_candidate_contexts() -> None:
    assert required_contexts_for_files(("pcb/temper.kicad_pro",), manifest()) == CONTEXTS


def test_evaluation_requires_completed_success() -> None:
    evaluation = evaluate_check_runs(CONTEXTS, [run("Core Tests"), run("Type Check")])
    assert evaluation.complete_success
    assert evaluation.passed == CONTEXTS


def test_evaluation_reports_missing_and_pending_contexts() -> None:
    evaluation = evaluate_check_runs(
        CONTEXTS, [run("Core Tests", status="in_progress", conclusion=None)]
    )
    assert evaluation.missing == ("Type Check",)
    assert evaluation.pending == ("Core Tests (in_progress)",)
    assert not evaluation.complete_success


def test_evaluation_treats_skipped_as_failure_for_relevant_paths() -> None:
    evaluation = evaluate_check_runs(
        CONTEXTS, [run("Core Tests"), run("Type Check", conclusion="skipped", run_id=2)]
    )
    assert evaluation.failed == ("Type Check (skipped)",)
    assert not evaluation.complete_success


def test_evaluation_uses_newest_duplicate_check_run() -> None:
    evaluation = evaluate_check_runs(
        ("Core Tests",),
        [
            run("Core Tests", conclusion="failure", run_id=1),
            run("Core Tests", conclusion="success", run_id=2),
        ],
    )
    assert evaluation.complete_success


def test_run_accepts_checks_after_polling() -> None:
    class FakeApi:
        def __init__(self) -> None:
            self.polls = 0

        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("packages/example.py",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            self.polls += 1
            if self.polls == 1:
                return (run("Core Tests", status="in_progress", conclusion=None),)
            return (run("Core Tests"), run("Type Check", run_id=2))

    now = [0.0]
    sleeps: list[float] = []
    api = FakeApi()
    result = _run(
        manifest(),
        api,
        "BennetLeff/temper",
        1,
        "abc123",
        sleep=lambda seconds: (sleeps.append(seconds), now.__setitem__(0, now[0] + seconds)),
        clock=lambda: now[0],
    )
    assert result == 0
    assert api.polls == 2
    assert sleeps == [5]


def test_run_skips_api_check_poll_for_irrelevant_paths() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("CHANGELOG.md",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            raise AssertionError("irrelevant PR must not poll check-runs")

    assert _run(manifest(), FakeApi(), "BennetLeff/temper", 1, "abc123") == 0


def test_workflow_trigger_lists_match_manifest() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = root / ".github/workflows/python-tests.yml"
    configured = load_manifest(root / ".github/required-checks.json")
    trigger_paths = load_workflow_trigger_paths(workflow)
    assert trigger_paths[0] == trigger_paths[1] == configured.trigger_paths


def test_manifest_validator_rejects_drift(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(
        "on:\n"
        "  push:\n"
        "    paths:\n"
        "      - 'packages/**'\n"
        "  pull_request:\n"
        "    paths:\n"
        "      - 'elec/**'\n"
    )
    try:
        validate_trigger_manifest(manifest(), workflow)
    except RuntimeError as error:
        assert "diverge" in str(error)
    else:
        raise AssertionError("expected trigger-list drift to fail")
