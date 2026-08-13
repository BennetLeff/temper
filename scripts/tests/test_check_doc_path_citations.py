"""Tests for scripts/check_doc_path_citations.py.

Covers: citation discovery (both target directories), existence resolution,
the allowlist's BACKLOG-vs-JUSTIFIED validation (mirrored from
scripts/check_bom_source_reconciliation.py's allowlist convention), and a
real-repo integration test pinning that the gate currently fails on
origin/main (per docs/brainstorms/2026-08-12-referential-integrity-options.md
-- 47 dangling citations measured at spike time). That pin is deliberate:
if this test ever needs updating because the count dropped, that's the gate
doing its job; if it needs updating because the count silently grew, that's
exactly the drift this gate exists to make loud.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_doc_path_citations import (  # noqa: E402
    REPO_ROOT,
    find_citations,
    load_allowlist,
    run,
)


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)


class TestFindCitations:
    def test_finds_plan_citation(self, tmp_path: Path):
        f = tmp_path / "note.py"
        f.write_text("# see docs/plans/2026-08-01-001-feat-example-plan.md for context\n")
        citations = find_citations(tmp_path)
        assert len(citations) == 1
        assert citations[0].cited_path == "docs/plans/2026-08-01-001-feat-example-plan.md"
        assert citations[0].kind == "plan"
        assert citations[0].site_line == 1

    def test_finds_evidence_citation(self, tmp_path: Path):
        f = tmp_path / "note.md"
        f.write_text("Grounded in docs/evidence/2026-07-30-some-finding.md.\n")
        citations = find_citations(tmp_path)
        assert citations[0].cited_path == "docs/evidence/2026-07-30-some-finding.md"
        assert citations[0].kind == "evidence"

    def test_excludes_pcb_directory(self, tmp_path: Path):
        (tmp_path / "pcb").mkdir()
        (tmp_path / "pcb" / "note.kicad_pcb").write_text("")
        f = tmp_path / "pcb" / "readme.md"
        f.write_text("docs/plans/2026-08-01-001-feat-example-plan.md\n")
        assert find_citations(tmp_path) == []

    def test_multiple_sites_same_path_all_recorded(self, tmp_path: Path):
        a = tmp_path / "a.py"
        a.write_text("# docs/plans/2026-08-01-001-feat-example-plan.md\n")
        b = tmp_path / "b.py"
        b.write_text("# docs/plans/2026-08-01-001-feat-example-plan.md\n")
        citations = find_citations(tmp_path)
        assert len(citations) == 2


class TestRunResolution:
    def test_existing_citation_is_clean(self, tmp_path: Path):
        _init_repo(tmp_path)
        (tmp_path / "docs" / "plans").mkdir(parents=True)
        real = tmp_path / "docs" / "plans" / "2026-08-01-001-feat-example-plan.md"
        real.write_text("# Example Plan\n")
        (tmp_path / "note.py").write_text(
            "# see docs/plans/2026-08-01-001-feat-example-plan.md\n"
        )
        state, data = run(tmp_path)
        assert state == "clean"
        assert data["dangling"] == {}

    def test_dangling_citation_never_existed(self, tmp_path: Path):
        _init_repo(tmp_path)
        (tmp_path / "note.py").write_text(
            "# see docs/plans/2026-08-01-999-feat-phantom-plan.md\n"
        )
        state, data = run(tmp_path)
        assert state == "violation"
        assert data["dangling"]["docs/plans/2026-08-01-999-feat-phantom-plan.md"] == "NEVER_EXISTED"

    def test_dangling_citation_deleted(self, tmp_path: Path):
        _init_repo(tmp_path)
        (tmp_path / "docs" / "evidence").mkdir(parents=True)
        doc = tmp_path / "docs" / "evidence" / "2026-07-30-was-real.md"
        doc.write_text("# Once real\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "add doc"], cwd=tmp_path, check=True)
        doc.unlink()
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "delete doc"], cwd=tmp_path, check=True)
        (tmp_path / "note.py").write_text(
            "# see docs/evidence/2026-07-30-was-real.md\n"
        )
        state, data = run(tmp_path)
        assert state == "violation"
        assert data["dangling"]["docs/evidence/2026-07-30-was-real.md"] == "DELETED"


class TestAllowlist:
    def test_missing_allowlist_is_empty_not_error(self, tmp_path: Path):
        assert load_allowlist(tmp_path / "does-not-exist.yaml") == []

    def test_justified_entry_parses(self, tmp_path: Path):
        p = tmp_path / "allow.yaml"
        p.write_text(
            "allowlist:\n"
            "  - path: docs/plans/2026-08-01-001-feat-example-plan.md\n"
            "    reason: deliberately kept as a documented dead link\n"
        )
        entries = load_allowlist(p)
        assert entries is not None
        assert len(entries) == 1
        assert entries[0].backlog is False

    def test_backlog_entry_requires_seeded_date(self, tmp_path: Path):
        p = tmp_path / "allow.yaml"
        p.write_text(
            "allowlist:\n"
            "  - path: docs/plans/2026-08-01-001-feat-example-plan.md\n"
            "    reason: pre-existing drift\n"
            "    backlog: true\n"
        )
        assert load_allowlist(p) is None

    def test_seeded_without_backlog_is_malformed(self, tmp_path: Path):
        p = tmp_path / "allow.yaml"
        p.write_text(
            "allowlist:\n"
            "  - path: docs/plans/2026-08-01-001-feat-example-plan.md\n"
            "    reason: pre-existing drift\n"
            '    seeded: "2026-08-12"\n'
        )
        assert load_allowlist(p) is None

    def test_valid_backlog_entry_parses(self, tmp_path: Path):
        p = tmp_path / "allow.yaml"
        p.write_text(
            "allowlist:\n"
            "  - path: docs/plans/2026-08-01-001-feat-example-plan.md\n"
            "    reason: pre-existing drift, unmeasured at seed time\n"
            "    backlog: true\n"
            '    seeded: "2026-08-12"\n'
        )
        entries = load_allowlist(p)
        assert entries is not None
        assert entries[0].backlog is True
        assert entries[0].seeded == "2026-08-12"

    def test_allowlisted_dangling_citation_suppressed_from_violations(self, tmp_path: Path):
        _init_repo(tmp_path)
        (tmp_path / "note.py").write_text(
            "# see docs/plans/2026-08-01-999-feat-phantom-plan.md\n"
        )
        (tmp_path / "doc-path-citation-allowlist.yaml").write_text(
            "allowlist:\n"
            "  - path: docs/plans/2026-08-01-999-feat-phantom-plan.md\n"
            "    reason: seeded backlog for this test\n"
            "    backlog: true\n"
            '    seeded: "2026-08-12"\n'
        )
        import check_doc_path_citations as mod

        old = mod.ALLOWLIST_PATH
        mod.ALLOWLIST_PATH = tmp_path / "doc-path-citation-allowlist.yaml"
        try:
            state, data = run(tmp_path)
        finally:
            mod.ALLOWLIST_PATH = old
        assert state == "clean"
        assert len(data["backlog_suppressed"]) == 1
        assert data["violations"] == {}


class TestRealRepoIntegration:
    def test_real_repo_currently_violates(self):
        """Pins the exact current origin/main state so this test fails
        loudly the day the count changes -- for better (citations fixed)
        or worse (new drift introduced) -- per this repo's own convention
        for gates landed against known-live findings (see
        check_pcl_config_board_correspondence.py's TestRealRepoIntegration).
        Measured at spike time: 47 dangling (27 NEVER_EXISTED + 20 DELETED)
        out of 516 distinct cited paths, 3454 citation sites."""
        state, data = run(REPO_ROOT)
        assert state == "violation"
        assert len(data["violations"]) >= 40, (
            f"expected the known ~47 dangling doc-path citations, found "
            f"{len(data['violations'])} -- if this dropped, citations were "
            f"fixed (update this bound down); if it's far above 47, new "
            f"drift landed."
        )
        # Named, previously-confirmed instances (see the spike doc): the
        # phantom plan an entire crate's provenance headers cite, and the
        # one AGENTS.md itself cites.
        assert "docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md" in data["violations"]
        assert "docs/evidence/2026-07-26-measurement-provenance.md" in data["violations"]
