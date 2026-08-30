"""Policy tests for the reviewed immutable performance capture workflow."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "pr-perf-baseline-capture.yml"
)


def workflow_text() -> str:
    assert WORKFLOW.is_file(), f"workflow file not found: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_is_manual_and_requires_immutable_capture_sha() -> None:
    text = workflow_text()
    assert "workflow_dispatch:" in text
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text
    assert "capture_sha:" in text
    assert "required: true" in text
    assert "type: string" in text
    assert "^[0-9a-fA-F]{40}$" in text
    assert "repos.getCommit" in text


def test_workflow_captures_exact_sha_in_five_matrix_legs() -> None:
    text = workflow_text()
    assert "run: [1, 2, 3, 4, 5]" in text
    assert "ref: ${{ inputs.capture_sha }}" in text
    assert 'test "$checked_out" = "$requested"' not in text
    assert 'if [[ "$checked_out" != "$requested" ]]' in text
    assert 'uv run python benchmarks/perf_ab.py \\' in text
    assert '--commit "$CAPTURE_SHA"' in text
    assert "persist-credentials: false" in text


def test_workflow_rebuilds_and_checks_extensions_before_measurement() -> None:
    text = workflow_text()
    assert "uv pip install maturin" in text
    assert "env -u CONDA_PREFIX make extensions" in text
    assert "run: make extensions-check" in text
    assert "name: Fetch authoritative baseline from main\n        shell: bash" in text
    assert "name: Aggregate and validate candidate append\n        shell: bash" in text
    assert text.index("run: make extensions-check") < text.index("name: Run performance A/B")


def test_workflow_aggregates_only_after_all_capture_legs_and_fails_closed() -> None:
    text = workflow_text()
    assert "needs: [validate-input, capture, independent-current]" in text
    assert "needs['independent-current'].result == 'success'" in text
    assert "needs['independent-current'].result == 'skipped'" in text
    assert "actions/download-artifact@v8" in text
    assert "for run in 1 2 3 4 5" in text
    assert "scripts/validate_perf_capture.py" in text
    for run in range(1, 6):
        assert f"captures/perf-capture-{run}.ndjson" in text
        assert f"--metadata captures/capture-{run}.metadata" in text


def test_independent_current_mode_is_manual_and_wired_only_to_capture_workflow() -> None:
    text = workflow_text()
    assert "independent_sha:" in text
    assert "independent-current:" in text
    assert "--independent-current captures/perf-current.ndjson" in text
    assert "--independent-sha \"$INDEPENDENT_SHA\"" in text
    assert "must differ from capture_sha" in text

    ordinary_pr = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "pr-perf-check.yml"
    ).read_text(encoding="utf-8")
    assert "independent-current" not in ordinary_pr
    assert "origin/main" in ordinary_pr


def test_workflow_is_read_only_and_uploads_raw_and_review_artifacts() -> None:
    text = workflow_text()
    assert "permissions:\n  contents: read" in text
    assert "contents: write" not in text
    assert "git push" not in text
    assert "git commit" not in text
    assert "candidate-baseline-append.jsonl" in text
    assert "capture-manifest.json" in text
    assert "actions/upload-artifact@v7" in text


def test_aggregate_uses_trusted_default_branch_code_and_separate_capture_tree() -> None:
    text = workflow_text()
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "path: capture-source" in text
    assert "--repo-root \"$GITHUB_WORKSPACE/capture-source\"" in text
    assert "--registry \"$GITHUB_WORKSPACE/capture-source/benchmarks/perf_ab.py\"" in text
    assert "capture-source/scripts/validate_perf_capture.py" not in text


def test_baseline_refresh_path_is_fail_closed_and_keeps_ordinary_prs_on_main() -> None:
    text = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "pr-perf-check.yml"
    ).read_text(encoding="utf-8")
    assert "REFRESH_MANIFEST" in text
    assert "GH_TOKEN: ${{ github.token }}" in text
    assert "shell: bash" in text
    assert "Baseline changed without a reviewed refresh manifest" in text
    assert "git show origin/main:scripts/validate_perf_capture.py" in text
    assert "git show origin/main:scripts/pr_perf_compare.py" in text
    assert 'git show "origin/main:scripts/pr_perf_compare.py" > main-pr-perf-compare.py' in text
    assert "BASELINE_FOR_COMPARE=main-perf-baseline.jsonl" in text
    assert "BASELINE_FOR_COMPARE=$BASELINE_PATH" in text
    assert "candidate-baseline \"$BASELINE_PATH\"" in text
    assert "--validated-margins-output \"$RUNNER_TEMP/validated-perf-margins.json\"" in text
    assert "VALIDATED_MARGINS_JSON=$RUNNER_TEMP/validated-perf-margins.json" in text
    assert "gh api \"repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}\"" in text
    assert "gh api \"repos/${GITHUB_REPOSITORY}/actions/artifacts/${artifact_id}\"" in text
    assert "gh api \"repos/${GITHUB_REPOSITORY}/actions/artifacts/${artifact_id}/zip\"" in text
    assert "'.workflow_id'" in text
    assert "303796920" in text
    assert "'.path'" in text
    assert "perf-ab-baseline-rows-${run_id}-1" in text
    assert "primary_capture.captures" in text
    assert "five distinct" in text
    assert "BASELINE_REFRESH_SCHEMA_VERSION = 2" in text
    assert "python3 scripts/validate_perf_capture.py" not in text
    assert "python3 main-pr-perf-compare.py" in text
    assert "--validated-margins-json \"$VALIDATED_MARGINS_JSON\"" in text
    assert "uv run python scripts/pr_perf_compare.py" not in text
    assert "Trusted baseline-refresh validator is not yet present on origin/main" in text
    assert "actions: read" in text
    # The candidate assignment appears only after the trusted validator and
    # API provenance checks, while the default remains the main baseline.
    assert text.index("BASELINE_FOR_COMPARE=main-perf-baseline.jsonl") < text.index(
        "python3 \"$validator_dir/validate_perf_capture.py\""
    ) < text.index("BASELINE_FOR_COMPARE=$BASELINE_PATH")


def test_refresh_manifest_cannot_be_approved_by_the_capture_workflow_itself() -> None:
    text = workflow_text()
    assert "contents: write" not in text
    assert "git push" not in text
    assert "git commit" not in text
    assert "candidate-baseline-append.jsonl" in text
