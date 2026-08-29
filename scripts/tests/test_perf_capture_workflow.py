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


def test_workflow_rebuilds_and_checks_extensions_before_measurement() -> None:
    text = workflow_text()
    assert "run: make extensions\n\n      - name: Verify extension freshness" in text
    assert "run: make extensions-check" in text
    assert text.index("run: make extensions-check") < text.index("name: Run performance A/B")


def test_workflow_aggregates_only_after_all_capture_legs_and_fails_closed() -> None:
    text = workflow_text()
    assert "needs: [validate-input, capture]" in text
    assert "if: always() && needs.validate-input.result == 'success'" in text
    assert "actions/download-artifact@v8" in text
    assert "for run in 1 2 3 4 5" in text
    assert "scripts/validate_perf_capture.py" in text
    for run in range(1, 6):
        assert f"captures/perf-capture-{run}.ndjson" in text


def test_workflow_is_read_only_and_uploads_raw_and_review_artifacts() -> None:
    text = workflow_text()
    assert "permissions:\n  contents: read" in text
    assert "contents: write" not in text
    assert "git push" not in text
    assert "git commit" not in text
    assert "candidate-baseline-append.jsonl" in text
    assert "capture-manifest.json" in text
    assert "actions/upload-artifact@v7" in text
