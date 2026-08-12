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


def cross_workflow_manifest() -> Manifest:
    """A manifest where one context is owned by a different workflow.

    `PR Performance Comparison` lives in `pr-perf-check.yml`, whose path filter
    is narrower than the aggregate's. Without `context_triggers`, any match on
    the global list demanded it too -- and because its workflow never ran, no
    check run was created at all.
    """
    return Manifest(
        trigger_paths=("packages/**", "docs/**", "pyproject.toml"),
        required_contexts=("Core Tests", "PR Performance Comparison"),
        context_triggers={"PR Performance Comparison": ("benchmarks/**", "scripts/pr_perf_compare.py")},
        timeout_seconds=30,
        poll_interval_seconds=5,
    )


def test_cross_workflow_context_not_required_when_its_paths_miss() -> None:
    # The wedge condition: a docs-only PR must not wait on a check run that
    # GitHub will never create. Before context_triggers this returned both.
    assert required_contexts_for_files(("docs/plans/x.md",), cross_workflow_manifest()) == (
        "Core Tests",
    )


def test_cross_workflow_context_required_when_its_paths_hit() -> None:
    assert required_contexts_for_files(
        ("benchmarks/perf_ab.py",), cross_workflow_manifest()
    ) == ("PR Performance Comparison",)


def test_both_required_when_both_match() -> None:
    assert required_contexts_for_files(
        ("docs/plans/x.md", "scripts/pr_perf_compare.py"), cross_workflow_manifest()
    ) == ("Core Tests", "PR Performance Comparison")


def test_no_contexts_when_nothing_matches() -> None:
    assert required_contexts_for_files(("README.md",), cross_workflow_manifest()) == ()


def test_run_narrows_required_contexts_via_context_triggers() -> None:
    """Regression test for the exact PR #1028 production incident.

    Before the `_run` fix (check_required_checks.py's `required = ...`
    assignment), `required` was `manifest.required_contexts` unconditionally
    once ANY global trigger_path matched -- so `context_triggers` was
    computed, validated, and unit-tested in isolation
    (`required_contexts_for_files`) but never actually consulted by the live
    polling loop. A real docs/evidence/**-only PR (#1028) hit exactly this:
    its own "Required Python Tests" run logged
    `missing: PR Performance Comparison` and failed, because pr-perf-check.yml
    never triggers on a docs-only diff and no check run by that name was ever
    created. This reproduces that PR's shape: a docs-only change, and a
    check-run set that contains everything EXCEPT the cross-workflow context.
    """

    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("docs/plans/x.md",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            # No check-run named "PR Performance Comparison" exists at all --
            # exactly what GitHub produces when pr-perf-check.yml never fires.
            return (run("Core Tests"),)

    assert _run(cross_workflow_manifest(), FakeApi(), "BennetLeff/temper", 1, "abc123") == 0


def test_run_still_requires_cross_workflow_context_when_its_own_paths_hit() -> None:
    # The other half of the same fix: narrowing must not become "never
    # required". When the cross-workflow context's OWN paths match, it is
    # still required, and a genuinely missing check-run must still fail
    # (fast-forwarded clock/sleep so this doesn't burn real wall-clock time).
    #
    # Needs a manifest whose GLOBAL trigger_paths also cover the changed
    # file -- cross_workflow_manifest()'s global list and its
    # context_triggers path deliberately do not overlap (that asymmetry is
    # what test_cross_workflow_context_not_required_when_its_paths_miss
    # exercises), so `_run`'s own coarse "did anything in trigger_paths
    # match at all" pre-check would short-circuit to a legitimate PASS
    # before context_triggers is even consulted -- not the scenario this
    # test wants. This manifest's `benchmarks/**` is in both lists, mirroring
    # the real repo (e.g. `pcb/temper.kicad_sch` is in both the global list
    # and erc-gate's own context_triggers entry).
    manifest_with_overlap = Manifest(
        trigger_paths=("packages/**", "docs/**", "pyproject.toml", "benchmarks/**"),
        required_contexts=("Core Tests", "PR Performance Comparison"),
        context_triggers={
            "PR Performance Comparison": ("benchmarks/**", "scripts/pr_perf_compare.py")
        },
        timeout_seconds=30,
        poll_interval_seconds=5,
    )

    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("benchmarks/perf_ab.py",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return (run("Core Tests"),)  # "PR Performance Comparison" never posted

    now = [0.0]
    result = _run(
        manifest_with_overlap,
        FakeApi(),
        "BennetLeff/temper",
        1,
        "abc123",
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
        clock=lambda: now[0],
    )
    assert result == 1


def test_run_polls_for_a_context_triggers_only_path_missing_from_the_global_list() -> None:
    """The second half of the `_run` fix: a diff touching ONLY a path a
    context_triggers entry owns, but that is absent from the manifest's
    global `trigger_paths`, must still be polled and enforced -- not treated
    as "nothing relevant changed" and passed instantly. This is the real
    shape of e.g. `firmware/**` for "Firmware Tests (state-machine +
    fault-injection)": that context's own workflow triggers on it, but the
    global list (owned by python-tests.yml, which has no reason to care
    about a firmware-only change) does not mention `firmware/**` at all.
    Before the fix, `_run`'s early bail-out tested only the coarse global
    list and would have returned PASS here without ever looking at
    check-runs, even though the required context's own workflow ran.
    """
    manifest_narrow_context_only = Manifest(
        trigger_paths=("packages/**", "docs/**", "pyproject.toml"),
        required_contexts=("Core Tests", "Firmware Tests (state-machine + fault-injection)"),
        context_triggers={
            "Firmware Tests (state-machine + fault-injection)": ("firmware/**", "pcb/**")
        },
        timeout_seconds=30,
        poll_interval_seconds=5,
    )

    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("firmware/main/state_machine.c",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            # The required context's real check-run IS present -- proving
            # the workflow genuinely ran -- but "Core Tests" is not required
            # for this diff (global list doesn't match), so only this one
            # context-run needs to exist for a clean pass.
            return (run("Firmware Tests (state-machine + fault-injection)"),)

    result = _run(
        manifest_narrow_context_only,
        FakeApi(),
        "BennetLeff/temper",
        1,
        "abc123",
    )
    assert result == 0


def test_run_fails_for_a_context_triggers_only_path_when_its_check_never_posts() -> None:
    # Same shape as above, but the check-run never shows up (as if the
    # workflow silently failed to trigger) -- must still fail, not pass by
    # virtue of the global list missing the path.
    manifest_narrow_context_only = Manifest(
        trigger_paths=("packages/**", "docs/**", "pyproject.toml"),
        required_contexts=("Core Tests", "Firmware Tests (state-machine + fault-injection)"),
        context_triggers={
            "Firmware Tests (state-machine + fault-injection)": ("firmware/**", "pcb/**")
        },
        timeout_seconds=30,
        poll_interval_seconds=5,
    )

    class FakeApi:
        def pull_request_files(self, repository: str, number: int) -> tuple[str, ...]:
            return ("firmware/main/state_machine.c",)

        def check_runs(self, repository: str, sha: str) -> tuple[dict[str, object], ...]:
            return ()

    now = [0.0]
    result = _run(
        manifest_narrow_context_only,
        FakeApi(),
        "BennetLeff/temper",
        1,
        "abc123",
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
        clock=lambda: now[0],
    )
    assert result == 1


def test_contexts_without_own_triggers_keep_global_behaviour() -> None:
    # Regression guard: the pre-existing contract is that a context with no
    # context_triggers entry is required whenever the global list matches.
    assert required_contexts_for_files(("packages/a.py",), manifest()) == CONTEXTS


def test_context_triggers_rejects_unknown_context() -> None:
    # A typo would otherwise silently never match, quietly dropping the gate.
    try:
        Manifest.from_mapping(
            {
                "trigger_paths": ["packages/**"],
                "required_contexts": ["Core Tests"],
                "context_triggers": {"Core Testz": ["benchmarks/**"]},
                "backlog_grace_seconds": 1,
            }
        )
    except Exception as exc:
        assert "not in required_contexts" in str(exc)
    else:
        raise AssertionError("expected an unknown-context rejection")


def test_context_triggers_rejects_empty_paths() -> None:
    # An empty list would make the context unreachable rather than always-required.
    try:
        Manifest.from_mapping(
            {
                "trigger_paths": ["packages/**"],
                "required_contexts": ["Core Tests"],
                "context_triggers": {"Core Tests": []},
                "backlog_grace_seconds": 1,
            }
        )
    except Exception as exc:
        assert "must be a list of non-empty strings" in str(exc)
    else:
        raise AssertionError("expected an empty-paths rejection")


def test_context_triggers_rejects_overlap_with_job_triggers() -> None:
    # A context is owned by exactly one workflow; declaring both is ambiguous.
    try:
        Manifest.from_mapping(
            {
                "trigger_paths": ["packages/**"],
                "required_contexts": ["Core Tests"],
                "job_triggers": {"Core Tests": {"id": "test", "paths": ["packages/**"]}},
                "context_triggers": {"Core Tests": ["benchmarks/**"]},
                "backlog_grace_seconds": 1,
            }
        )
    except Exception as exc:
        assert "exactly one of the two" in str(exc)
    else:
        raise AssertionError("expected an overlap rejection")


def test_partial_backlog_gets_the_grace_extension() -> None:
    """Some contexts done, others never created -> still queue latency.

    This is the case that failed on real pull requests: python-tests completed
    for the jobs that got runners, the rest had no check run at all, and the
    aggregate reported `missing: Rust Checks, Core Tests, ...` and failed at the
    base deadline while those jobs were merely waiting for the pool.

    `_any_started` returned True (something had started), so the grace never
    fired. `_any_still_queueing` asks the question that matters instead: is any
    required context still waiting to run?
    """
    from check_required_checks import _any_still_queueing

    # "Core Tests" completed; "Type Check" has no check run at all yet.
    runs = (run("Core Tests"),)
    assert _any_still_queueing(("Core Tests", "Type Check"), runs) is True


def test_all_contexts_present_and_terminal_gets_no_extension() -> None:
    """Nothing is waiting -> the grace must not fire.

    The extension exists for queue latency. Once every required context has a
    terminal check run, a still-incomplete evaluation is a real verdict, and
    granting more time would only delay failing closed.
    """
    from check_required_checks import _any_still_queueing

    runs = (run("Core Tests"), run("Type Check", run_id=2))
    assert _any_still_queueing(("Core Tests", "Type Check"), runs) is False


def test_queued_check_run_still_counts_as_waiting() -> None:
    """The original backlog case must keep working.

    A check run that exists but sits in `queued` has not been given a runner.
    Narrowing the predicate to only-absent runs would have silently dropped
    this, which is what the existing backlog tests caught.
    """
    from check_required_checks import _any_still_queueing

    runs = (run("Core Tests"), queued_run("Type Check", run_id=2))
    assert _any_still_queueing(("Core Tests", "Type Check"), runs) is True
