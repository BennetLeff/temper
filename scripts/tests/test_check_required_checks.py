from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_required_checks import (  # noqa: E402
    JobTrigger,
    Manifest,
    _run,
    evaluate_check_runs,
    job_should_run,
    load_manifest,
    load_workflow_trigger_paths,
    matching_patterns,
    path_matches,
    required_contexts_for_files,
    validate_job_conditions,
    validate_trigger_manifest,
    verify_skips,
)

CONTEXTS = ("Core Tests", "Type Check")


def manifest() -> Manifest:
    return Manifest(
        trigger_paths=("packages/**", "pcb/*.kicad_pro", ".loc-allowlist.txt", "pyproject.toml"),
        required_contexts=CONTEXTS,
        timeout_seconds=30,
        poll_interval_seconds=5,
    )


def skip_manifest() -> Manifest:
    return Manifest(
        trigger_paths=(
            "packages/**",
            "pcb/*.kicad_pro",
            ".loc-allowlist.txt",
            "docs/plans/**",
            "pyproject.toml",
        ),
        required_contexts=CONTEXTS,
        job_triggers={
            "Core Tests": JobTrigger(id="test", paths=("packages/**", "pcb/*.kicad_pro")),
            "Type Check": JobTrigger(id="type-check", paths=("packages/**",)),
        },
        catch_all_paths=("pyproject.toml", "uv.lock", "scripts/**"),
        mapped_to_nothing=("docs/**", "**/TRACEABILITY"),
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


def test_evaluation_reports_skipped_conclusions_separately() -> None:
    evaluation = evaluate_check_runs(
        CONTEXTS, [run("Core Tests"), run("Type Check", conclusion="skipped", run_id=2)]
    )
    assert evaluation.skipped == ("Type Check",)
    assert evaluation.failed == ()
    assert not evaluation.complete_success


def test_cancelled_conclusion_is_pending_not_failure() -> None:
    """A cancelled check is superseded work, not a verdict.

    python-tests sets `cancel-in-progress: true` on PRs, so every re-push
    cancels the previous run's jobs. Classifying that as a failure is terminal
    -- the poll loop returns 1 immediately -- which made rapid iteration fail
    on the run the author had just replaced.
    """

    evaluation = evaluate_check_runs(
        CONTEXTS, [run("Core Tests"), run("Type Check", conclusion="cancelled", run_id=2)]
    )
    assert evaluation.failed == ()
    assert evaluation.pending == ("Type Check (cancelled -- superseded, awaiting rerun)",)
    assert not evaluation.complete_success


def test_cancelled_is_superseded_by_a_newer_run_of_the_same_context() -> None:
    """The newer run must win, otherwise 'pending' would never resolve."""

    evaluation = evaluate_check_runs(
        CONTEXTS,
        [
            run("Core Tests"),
            run("Type Check", conclusion="cancelled", run_id=2),
            run("Type Check", conclusion="success", run_id=3),
        ],
    )
    assert evaluation.complete_success
    assert evaluation.pending == ()
    assert evaluation.failed == ()


def test_genuine_failure_is_still_terminal() -> None:
    """Softening `cancelled` must not soften real failures."""

    evaluation = evaluate_check_runs(
        CONTEXTS, [run("Core Tests"), run("Type Check", conclusion="failure", run_id=2)]
    )
    assert evaluation.failed == ("Type Check (failure)",)
    assert not evaluation.complete_success


def test_verified_skip_passes() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("docs/plans/2026-08-02-x.md",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                run("Core Tests", conclusion="skipped", run_id=2),
                run("Type Check", conclusion="skipped", run_id=3),
            )

    assert _run(skip_manifest(), FakeApi(), "BennetLeff/temper", 1, "abc123") == 0


def test_unverified_skip_fails_when_job_trigger_path_changed() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("packages/example.py",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                run("Core Tests", conclusion="skipped", run_id=2),
                run("Type Check", run_id=3),
            )

    assert _run(skip_manifest(), FakeApi(), "BennetLeff/temper", 1, "abc123") == 1


def test_unverified_skip_fails_when_catch_all_path_changed() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("pyproject.toml",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                run("Core Tests", conclusion="skipped", run_id=2),
                run("Type Check", run_id=3),
            )

    assert _run(skip_manifest(), FakeApi(), "BennetLeff/temper", 1, "abc123") == 1


def test_unverified_skip_fails_when_residual_path_changed() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("pyproject.toml", "README.md")

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                run("Core Tests", conclusion="skipped", run_id=2),
                run("Type Check", run_id=3),
            )

    assert _run(skip_manifest(), FakeApi(), "BennetLeff/temper", 1, "abc123") == 1


def test_skip_without_manifest_entry_fails_closed() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("pyproject.toml",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                run("Core Tests", run_id=2),
                run("Type Check", conclusion="skipped", run_id=3),
            )

    assert _run(manifest(), FakeApi(), "BennetLeff/temper", 1, "abc123") == 1


def test_skip_verification_is_noop_without_skipped_conclusions() -> None:
    evaluation = evaluate_check_runs(
        CONTEXTS, [run("Core Tests"), run("Type Check", run_id=2)]
    )
    assert verify_skips(evaluation, ("docs/plans/x.md",), skip_manifest()) == evaluation


def test_job_should_run_three_category_mapping() -> None:
    skip_map = skip_manifest()
    assert job_should_run("Core Tests", ("packages/x.py",), skip_map)
    assert job_should_run("Core Tests", ("pyproject.toml",), skip_map)
    assert job_should_run("Core Tests", ("README.md",), skip_map)
    assert not job_should_run("Core Tests", ("docs/plans/x.md",), skip_map)
    assert not job_should_run("Core Tests", ("TRACEABILITY",), skip_map)
    assert not job_should_run("Type Check", ("docs/plans/x.md",), skip_map)
    assert not job_should_run("Type Check", ("pcb/temper.kicad_pro",), skip_map)
    assert job_should_run("Unknown Context", ("docs/plans/x.md",), skip_map)


def test_evaluation_uses_newest_duplicate_check_run() -> None:
    evaluation = evaluate_check_runs(
        ("Core Tests",),
        [
            run("Core Tests", conclusion="failure", run_id=1),
            run("Core Tests", conclusion="success", run_id=2),
        ],
    )
    assert evaluation.complete_success


def grace_manifest() -> Manifest:
    return Manifest(
        trigger_paths=manifest().trigger_paths,
        required_contexts=CONTEXTS,
        timeout_seconds=30,
        backlog_grace_seconds=100,
        poll_interval_seconds=5,
    )


def queued_run(name: str, run_id: int = 1) -> dict[str, object]:
    return run(name, status="queued", conclusion=None, run_id=run_id)


def test_backlog_grace_waits_past_original_deadline_when_nothing_started() -> None:
    class FakeApi:
        def __init__(self) -> None:
            self.polls = 0

        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("packages/example.py",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            self.polls += 1
            if self.polls <= 7:
                return (
                    queued_run("Core Tests"),
                    queued_run("Type Check", run_id=2),
                )
            return (run("Core Tests"), run("Type Check", run_id=2))

    now = [0.0]
    sleeps: list[float] = []
    api = FakeApi()
    result = _run(
        grace_manifest(),
        api,
        "BennetLeff/temper",
        1,
        "abc123",
        sleep=lambda seconds: (sleeps.append(seconds), now.__setitem__(0, now[0] + seconds)),
        clock=lambda: now[0],
    )
    assert result == 0
    assert now[0] == 35.0
    assert api.polls == 8


def test_backlog_grace_exhausted_fails_closed() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("packages/example.py",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                queued_run("Core Tests"),
                queued_run("Type Check", run_id=2),
            )

    now = [0.0]
    sleeps: list[float] = []
    api = FakeApi()
    result = _run(
        grace_manifest(),
        api,
        "BennetLeff/temper",
        1,
        "abc123",
        sleep=lambda seconds: (sleeps.append(seconds), now.__setitem__(0, now[0] + seconds)),
        clock=lambda: now[0],
    )
    assert result == 1
    assert now[0] == 130.0
    assert len(sleeps) > 10


def test_started_but_slow_fails_at_original_deadline_despite_grace() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("packages/example.py",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                run("Core Tests", status="in_progress", conclusion=None),
                run("Type Check", status="in_progress", conclusion=None, run_id=2),
            )

    now = [0.0]
    sleeps: list[float] = []
    api = FakeApi()
    result = _run(
        grace_manifest(),
        api,
        "BennetLeff/temper",
        1,
        "abc123",
        sleep=lambda seconds: (sleeps.append(seconds), now.__setitem__(0, now[0] + seconds)),
        clock=lambda: now[0],
    )
    assert result == 1
    assert now[0] == 30.0


def test_no_grace_by_default_preserves_original_timeout_behavior() -> None:
    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("packages/example.py",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (
                queued_run("Core Tests"),
                queued_run("Type Check", run_id=2),
            )

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
    assert result == 1
    assert now[0] == 30.0


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


def canonical_workflow_text() -> str:
    return (
        "on:\n"
        "  push:\n"
        "    paths:\n"
        "      - 'packages/**'\n"
        "  pull_request:\n"
        "    paths:\n"
        "      - 'packages/**'\n"
        "jobs:\n"
        "  changes:\n"
        "    name: Change Classification\n"
        "    outputs:\n"
        "      test: ${{ steps.classify.outputs.test }}\n"
        "      type-check: ${{ steps.classify.outputs.type-check }}\n"
        "    steps:\n"
        "      - uses: actions/checkout@v7\n"
        "        with:\n"
        "          fetch-depth: 0\n"
        "      - name: Classify changed paths against manifest trigger sets\n"
        "        id: classify\n"
        "        run: python3 scripts/classify_changed_paths.py\n"
        "  test:\n"
        "    name: Core Tests\n"
        "    needs: [changes]\n"
        "    if: ${{ github.event_name == 'push' || needs.changes.outputs.test == 'true' }}\n"
        "  type-check:\n"
        "    name: Type Check\n"
        "    needs: [changes]\n"
        "    if: ${{ github.event_name == 'push' || needs.changes.outputs.type-check == 'true' }}\n"
    )


def test_job_condition_validation_accepts_canonical_workflow(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(canonical_workflow_text())
    validate_job_conditions(skip_manifest(), workflow)


def test_job_condition_validation_is_inert_without_filters(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text("jobs:\n  test:\n    name: Core Tests\n  type-check:\n    name: Type Check\n")
    validate_job_conditions(manifest(), workflow)


def test_job_condition_validation_rejects_non_pure_predicate(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(
        canonical_workflow_text().replace(
            "needs.changes.outputs.test == 'true'",
            "needs.changes.outputs.test == 'true' && github.event.sender.type == 'bot'",
        )
    )
    try:
        validate_job_conditions(skip_manifest(), workflow)
    except RuntimeError as error:
        assert "not a pure path predicate" in str(error)
    else:
        raise AssertionError("expected non-pure-path predicate to fail")


def test_job_condition_validation_rejects_condition_drift(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(
        canonical_workflow_text().replace(
            "needs.changes.outputs.type-check == 'true'",
            "needs.changes.outputs.core == 'true'",
        )
    )
    try:
        validate_job_conditions(skip_manifest(), workflow)
    except RuntimeError as error:
        assert "not a pure path predicate" in str(error)
    else:
        raise AssertionError("expected drifted condition to fail")


def test_job_condition_validation_rejects_condition_without_manifest_entry(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(
        canonical_workflow_text()
        + "  extra:\n"
        + "    name: Extra Job\n"
        + "    needs: [changes]\n"
        + "    if: ${{ github.event_name == 'push' || needs.changes.outputs.extra == 'true' }}\n"
    )
    try:
        validate_job_conditions(skip_manifest(), workflow)
    except RuntimeError as error:
        assert "no manifest job_triggers entry" in str(error)
    else:
        raise AssertionError("expected condition-without-manifest-entry to fail")


def test_job_condition_validation_rejects_missing_changes_job(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(
        "jobs:\n"
        "  test:\n"
        "    name: Core Tests\n"
        "    needs: [changes]\n"
        "    if: ${{ github.event_name == 'push' || needs.changes.outputs.test == 'true' }}\n"
        "  type-check:\n"
        "    name: Type Check\n"
        "    needs: [changes]\n"
        "    if: ${{ github.event_name == 'push' || needs.changes.outputs.type-check == 'true' }}\n"
    )
    try:
        validate_job_conditions(skip_manifest(), workflow)
    except RuntimeError as error:
        assert "missing the changes job" in str(error)
    else:
        raise AssertionError("expected missing changes job to fail")


def test_job_condition_validation_rejects_name_mismatch(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(canonical_workflow_text().replace("name: Core Tests", "name: Renamed Tests"))
    try:
        validate_job_conditions(skip_manifest(), workflow)
    except RuntimeError as error:
        assert "manifest job_triggers key" in str(error)
    else:
        raise AssertionError("expected name mismatch to fail")


def test_job_condition_validation_rejects_missing_outputs(tmp_path: Path) -> None:
    workflow = tmp_path / "python-tests.yml"
    workflow.write_text(
        canonical_workflow_text().replace(
            "      type-check: ${{ steps.classify.outputs.type-check }}\n", ""
        )
    )
    try:
        validate_job_conditions(skip_manifest(), workflow)
    except RuntimeError as error:
        assert "do not match path-conditional job ids" in str(error)
    else:
        raise AssertionError("expected missing changes output to fail")
