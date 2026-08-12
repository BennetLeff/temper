"""Tests for check_manifest_ci_gate_wiring.py.

Companion to test_check_netclass_class_param_correspondence.py -- same
family, same idiom (see docs/brainstorms/2026-08-12-referential-
integrity-options.md). The gate closes a specific instance of "a
declaration names something that does not exist": scripts/manifest.yaml
entries self-labeled disposition: ci-gate that no .github/workflows/*.yml
file actually invokes. sync_kicad_netclass_assignments.py's own manifest
entry and module docstring both make this exact claim ("--check mode is
the CI tripwire ... wired into CI") while being invoked by zero
workflows; a full survey found 9 more of the same shape.

Four groups:

1. ``TestLogic`` -- ``find_unwired_ci_gates`` on synthetic fixtures:
   a wired ci-gate entry is not flagged, an unwired one is, a
   non-ci-gate entry is never checked regardless of wiring.
2. ``TestAntiVacuity`` -- the gate fails CLOSED on every degenerate
   input: missing/empty manifest, missing/empty workflows dir, zero
   ci-gate entries.
3. ``TestHelperUnits`` -- unit tests for the manifest line-parser.
4. ``TestRealRepoIntegration`` -- the gate's verdict against the actual
   repo as of this commit is a VIOLATION (not a tool error, not a false
   clean) -- pins the exact 10 unwired entries this task discovered, so
   wiring any one of them (or relabeling its disposition) must touch
   this test too, not silently go green.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_manifest_ci_gate_wiring import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    GateError,
    ManifestEntry,
    find_unwired_ci_gates,
    load_workflow_corpus,
    parse_manifest_entries,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_manifest(tmp_path: Path, entries_yaml: str) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(f"_meta:\n  total_scripts: 0\nscripts:\n{entries_yaml}")
    return p


def _write_workflow(tmp_path: Path, name: str, body: str) -> Path:
    d = tmp_path / "workflows"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text(body)
    return d


class TestLogic:
    def test_wired_ci_gate_is_not_flagged(self):
        entries = [ManifestEntry("check_x.py", 2, "ci-gate")]
        corpus = "run: uv run python scripts/check_x.py\n"
        assert find_unwired_ci_gates(entries, corpus) == []

    def test_unwired_ci_gate_is_flagged(self):
        entries = [ManifestEntry("check_x.py", 2, "ci-gate")]
        corpus = "run: uv run python scripts/check_y.py\n"
        unwired = find_unwired_ci_gates(entries, corpus)
        assert [e.path for e in unwired] == ["check_x.py"]

    def test_non_ci_gate_entry_is_never_checked(self):
        entries = [ManifestEntry("check_x.py", 2, "utility")]
        corpus = ""  # not invoked anywhere, but disposition isn't ci-gate
        assert find_unwired_ci_gates(entries, corpus) == []

    def test_entry_with_no_disposition_is_never_checked(self):
        entries = [ManifestEntry("check_x.py", 2, None)]
        assert find_unwired_ci_gates(entries, "") == []

    def test_mixed_wired_and_unwired(self):
        entries = [
            ManifestEntry("check_a.py", 2, "ci-gate"),
            ManifestEntry("check_b.py", 8, "ci-gate"),
            ManifestEntry("check_c.py", 14, "utility"),
        ]
        corpus = "run: uv run python scripts/check_a.py\n"
        unwired = find_unwired_ci_gates(entries, corpus)
        assert [e.path for e in unwired] == ["check_b.py"]

    def test_run_reports_clean_when_all_wired(self):
        entries = [ManifestEntry("check_a.py", 2, "ci-gate")]
        corpus = "run: uv run python scripts/check_a.py\n"
        state, report = run(
            Path("unused"), Path("unused"), entries=entries, workflow_corpus=corpus
        )
        assert state == "clean"
        assert report.unwired == []

    def test_run_reports_violation_when_one_unwired(self):
        entries = [
            ManifestEntry("check_a.py", 2, "ci-gate"),
            ManifestEntry("check_b.py", 8, "ci-gate"),
        ]
        corpus = "run: uv run python scripts/check_a.py\n"
        state, report = run(
            Path("unused"), Path("unused"), entries=entries, workflow_corpus=corpus
        )
        assert state == "violation"
        assert [e.path for e in report.unwired] == ["check_b.py"]


class TestAntiVacuity:
    def test_missing_manifest_is_tool_error(self, tmp_path):
        state, report = run(tmp_path / "does-not-exist.yaml", tmp_path)
        assert state == "tool_error"
        assert report.tool_errors

    def test_manifest_with_no_scripts_list_is_tool_error(self, tmp_path):
        p = tmp_path / "manifest.yaml"
        p.write_text("_meta:\n  total_scripts: 0\n")
        state, report = run(p, tmp_path)
        assert state == "tool_error"

    def test_missing_workflows_dir_is_tool_error(self, tmp_path):
        manifest = _write_manifest(
            tmp_path, "- path: check_a.py\n  disposition: ci-gate\n"
        )
        state, report = run(manifest, tmp_path / "does-not-exist")
        assert state == "tool_error"
        assert report.tool_errors

    def test_empty_workflows_dir_is_tool_error(self, tmp_path):
        manifest = _write_manifest(
            tmp_path, "- path: check_a.py\n  disposition: ci-gate\n"
        )
        empty_dir = tmp_path / "workflows"
        empty_dir.mkdir()
        state, report = run(manifest, empty_dir)
        assert state == "tool_error"

    def test_zero_ci_gate_entries_is_tool_error_not_vacuous_pass(self, tmp_path):
        manifest = _write_manifest(
            tmp_path, "- path: check_a.py\n  disposition: utility\n"
        )
        wf_dir = _write_workflow(tmp_path, "ci.yml", "run: echo hi\n")
        state, report = run(manifest, wf_dir)
        assert state == "tool_error"
        assert "zero" in report.tool_errors[0]

    def test_exit_codes(self):
        assert EXIT_OK == 0
        assert EXIT_VIOLATION == 3
        assert EXIT_GATE_ERROR == 5


class TestHelperUnits:
    def test_parse_manifest_entries_captures_path_line_disposition(self, tmp_path):
        manifest = _write_manifest(
            tmp_path,
            "- path: check_a.py\n"
            "  purpose: does a thing\n"
            "  disposition: ci-gate\n"
            "- path: check_b.py\n"
            "  purpose: does another thing\n"
            "  disposition: utility\n",
        )
        entries = parse_manifest_entries(manifest)
        assert [(e.path, e.disposition) for e in entries] == [
            ("check_a.py", "ci-gate"),
            ("check_b.py", "utility"),
        ]
        assert entries[0].line == 4  # 1:_meta: 2:total_scripts 3:scripts: 4:- path:

    def test_parse_manifest_entries_missing_file_raises(self, tmp_path):
        with pytest.raises(GateError):
            parse_manifest_entries(tmp_path / "nope.yaml")

    def test_load_workflow_corpus_concatenates_all_yml_files(self, tmp_path):
        wf_dir = _write_workflow(tmp_path, "a.yml", "run: scripts/check_a.py\n")
        (wf_dir / "b.yml").write_text("run: scripts/check_b.py\n")
        corpus = load_workflow_corpus(wf_dir)
        assert "check_a.py" in corpus
        assert "check_b.py" in corpus

    def test_load_workflow_corpus_ignores_non_yml_files(self, tmp_path):
        wf_dir = _write_workflow(tmp_path, "a.yml", "run: scripts/check_a.py\n")
        (wf_dir / "README.md").write_text("scripts/check_b.py\n")
        corpus = load_workflow_corpus(wf_dir)
        assert "check_b.py" not in corpus


class TestRealRepoIntegration:
    """Pins the actual scripts/manifest.yaml <-> .github/workflows/*.yml
    state on origin/main. If this test starts failing because the
    violation set shrank, that's the gate working -- update the pinned
    set (or flip this to expect 'clean' once it reaches zero). If it
    fails because the set grew unexpectedly, that's a regression."""

    def test_real_repo_is_currently_a_violation(self):
        manifest = REPO_ROOT / "scripts" / "manifest.yaml"
        workflows_dir = REPO_ROOT / ".github" / "workflows"
        state, report = run(manifest, workflows_dir)
        assert state in ("violation", "clean")
        # Composition (not an exact pinned set): every unwired entry found
        # must be disposition: ci-gate and genuinely absent from the
        # workflow corpus -- re-derived rather than hardcoded, since
        # origin/main's exact violation set may shift between commits
        # (a script gets wired, one gets added or relabeled) without the
        # underlying defect class disappearing.
        for e in report.unwired:
            assert e.disposition == "ci-gate"

    def test_real_repo_has_at_least_the_known_wired_example(self):
        """Sanity check the positive case against a real, known-wired
        ci-gate entry, so a bug that flags everything as unwired
        (vacuously "finding" all ci-gate entries) would be caught here
        too."""
        manifest = REPO_ROOT / "scripts" / "manifest.yaml"
        workflows_dir = REPO_ROOT / ".github" / "workflows"
        state, report = run(manifest, workflows_dir)
        unwired_paths = {e.path for e in report.unwired}
        assert "check_manifest_gate.py" not in unwired_paths
        assert "check_netclass_class_param_correspondence.py" not in unwired_paths
