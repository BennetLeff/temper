"""Tests for gen_repo_state.py.

No test file existed for this gate before this change -- CI only ever ran
``gen_repo_state.py --check`` as a bare shell step, with no pytest coverage
asserting *why* it passes or fails. That gap was live: on 2026-07-30 the gate
correctly went red twice in a row (runs for commits ``3bddb8d0`` and
``96726eac``) because ``docs/plans/README.md``'s generated block went stale
the moment PR #423 landed a new ``active`` plan without anyone re-running the
generator -- and nothing but the bare CI step itself would have caught a
regression in that behaviour. It was fixed forward by hand (commit
``54372bbf``, "docs(plans): regenerate the index after rebase") before this
file was written, so ``TestRealRepoIsClean`` below documents that main is
presently green rather than reproducing a live failure.

Groups:
  TestSplice              -- the marker-splicing primitive: missing markers
                              fail closed (GenError), present markers splice cleanly.
  TestCompletenessCheck   -- render_repo_map()'s core contract: an undescribed
                              tracked top-level directory is a hard error.
  TestAntiVacuity          -- the real repo, mutated in a scratch/revert
                              pattern, to prove the completeness check is not
                              vacuous today (matches this repo's convention of
                              distrusting gates that pass on the input they
                              exist to catch).
  TestPlanInventory        -- render_plan_status()/plan_inventory() against an
                              isolated docs/plans/ fixture: adding one active
                              plan changes the count and the active list.
  TestDriftDetection       -- reproduces the actual 2026-07-30 incident class
                              end-to-end via build(): a docs/plans/README.md
                              block that is stale relative to the plan
                              fixtures is flagged; a matching one is not.
  TestRealRepoIsClean      -- the live repo's committed blocks currently match
                              generated output (documents the fixed-forward
                              state; not a tautology, since it calls the same
                              build() path CI does).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gen_repo_state as grs

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# splice()
# ---------------------------------------------------------------------------


class TestSplice:
    def test_missing_begin_marker_fails_closed(self):
        text = f"before\n{grs.MARKER_END.format(name='x')}\nafter\n"
        with pytest.raises(grs.GenError, match="missing the 'x' markers"):
            grs.splice(text, "x", "body", "doc.md")

    def test_missing_end_marker_fails_closed(self):
        text = f"before\n{grs.MARKER_BEGIN.format(name='x')}\nafter\n"
        with pytest.raises(grs.GenError, match="missing the 'x' markers"):
            grs.splice(text, "x", "body", "doc.md")

    def test_missing_both_markers_fails_closed(self):
        with pytest.raises(grs.GenError):
            grs.splice("no markers anywhere", "x", "body", "doc.md")

    def test_present_markers_splice_the_body_between_them(self):
        begin = grs.MARKER_BEGIN.format(name="x")
        end = grs.MARKER_END.format(name="x")
        text = f"head\n{begin}\nstale\n{end}\ntail\n"
        result = grs.splice(text, "x", "fresh body", "doc.md")
        assert "stale" not in result
        assert "fresh body" in result
        assert result.startswith("head\n")
        assert result.endswith("tail\n")

    def test_splice_is_idempotent(self):
        begin = grs.MARKER_BEGIN.format(name="x")
        end = grs.MARKER_END.format(name="x")
        text = f"head\n{begin}\nstale\n{end}\ntail\n"
        once = grs.splice(text, "x", "fresh body", "doc.md")
        twice = grs.splice(once, "x", "fresh body", "doc.md")
        assert once == twice


# ---------------------------------------------------------------------------
# render_repo_map() completeness check, in isolation from git/filesystem
# ---------------------------------------------------------------------------


class TestCompletenessCheck:
    def test_undescribed_directory_is_a_hard_error(self, monkeypatch):
        monkeypatch.setattr(
            grs, "tracked_top_level_dirs", lambda: sorted({*grs.DIRECTORY_PURPOSE, "wat"})
        )
        with pytest.raises(grs.GenError, match="wat"):
            grs.render_repo_map()

    def test_multiple_undescribed_directories_are_all_named(self, monkeypatch):
        monkeypatch.setattr(
            grs,
            "tracked_top_level_dirs",
            lambda: sorted({*grs.DIRECTORY_PURPOSE, "zeta", "alpha"}),
        )
        with pytest.raises(grs.GenError) as exc_info:
            grs.render_repo_map()
        assert "alpha" in str(exc_info.value)
        assert "zeta" in str(exc_info.value)

    def test_fully_described_directories_render_cleanly(self, monkeypatch):
        monkeypatch.setattr(grs, "tracked_top_level_dirs", lambda: ["docs", "scripts"])
        body = grs.render_repo_map()
        assert "`docs/`" in body
        assert "`scripts/`" in body
        assert grs.DIRECTORY_PURPOSE["docs"] in body


# ---------------------------------------------------------------------------
# Anti-vacuity: the completeness check against the REAL, live repo, via a
# scratch mutation that is always reverted. Per this repo's own documented
# pattern (docs/evidence/*), a gate must be shown failing on the input it
# exists to catch -- this codifies that as a permanent regression test
# instead of a one-off manual check.
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_removing_a_real_directorys_description_fails_closed(self, monkeypatch):
        """Delete one real, currently-described directory's entry and confirm
        the completeness check fires -- proving it is not vacuous today."""
        real_dirs = grs.tracked_top_level_dirs()
        assert real_dirs, "expected at least one tracked top-level directory"
        victim = real_dirs[0]
        assert victim in grs.DIRECTORY_PURPOSE

        monkeypatch.delitem(grs.DIRECTORY_PURPOSE, victim)
        with pytest.raises(grs.GenError, match=victim):
            grs.render_repo_map()
        # monkeypatch restores DIRECTORY_PURPOSE[victim] on teardown.

    def test_main_check_exits_2_for_an_undescribed_directory(self, monkeypatch, capsys):
        """End-to-end: main(["--check"]) against the real repo, with one real
        directory's description removed, must exit 2 (tool error), not 1
        (mere drift) and not 0."""
        real_dirs = grs.tracked_top_level_dirs()
        victim = real_dirs[0]
        monkeypatch.delitem(grs.DIRECTORY_PURPOSE, victim)
        monkeypatch.setattr(sys, "argv", ["gen_repo_state.py", "--check"])
        assert grs.main() == 2
        assert victim in capsys.readouterr().err

    def test_real_repo_currently_describes_every_tracked_directory(self):
        """Control for the two tests above: today, with no mutation, the real
        repo has zero undescribed directories (--check would not fire this
        path). If this starts failing, someone added a directory without a
        DIRECTORY_PURPOSE entry -- fix that, don't loosen this test."""
        undescribed = set(grs.tracked_top_level_dirs()) - set(grs.DIRECTORY_PURPOSE)
        assert undescribed == set()


# ---------------------------------------------------------------------------
# plan_inventory() / render_plan_status(), isolated from README.md/packages/.
# ---------------------------------------------------------------------------


def _write_plan(plans_dir: Path, name: str, status: str | None, title: str = "A plan") -> None:
    if status is None:
        plans_dir.joinpath(name).write_text(f"# {title}\n\nNo frontmatter.\n")
        return
    plans_dir.joinpath(name).write_text(
        f'---\nstatus: "{status}"\ntitle: "{title}"\n---\n\n# {title}\n'
    )


class TestParseFrontmatterStatus:
    """Tests for parse_frontmatter_status() — the YAML frontmatter parser."""

    def test_single_line_status(self, tmp_path):
        path = tmp_path / "plan.md"
        path.write_text('---\nstatus: active\ntitle: "Test"\n---\n\n# Test\n')
        assert grs.parse_frontmatter_status(path) == "active"

    def test_quoted_status(self, tmp_path):
        path = tmp_path / "plan.md"
        path.write_text('---\nstatus: "active"\ntitle: "Test"\n---\n\n# Test\n')
        assert grs.parse_frontmatter_status(path) == "active"

    def test_no_frontmatter(self, tmp_path):
        path = tmp_path / "plan.md"
        path.write_text("# No frontmatter\n\nJust a doc.\n")
        assert grs.parse_frontmatter_status(path) is None

    def test_frontmatter_without_status(self, tmp_path):
        path = tmp_path / "plan.md"
        path.write_text('---\ntitle: "Test"\n---\n\n# Test\n')
        assert grs.parse_frontmatter_status(path) is None

    def test_multiline_status_yaml_continuation(self, tmp_path):
        """Multi-line YAML plain scalar: indented continuation lines are
        part of the same value. The parser must concatenate them, not
        silently drop the continuation (which produced the corrupted
        'research-only, no elec/src or pcb/ changes made -- this is a'
        row in the plan index)."""
        path = tmp_path / "plan.md"
        path.write_text(
            '---\n'
            'status: research-only, no elec/src or pcb/ changes made -- this is a\n'
            '  requirements document for a human/planning decision, not an implementation\n'
            'actors: someone\n'
            '---\n\n# Plan\n'
        )
        result = grs.parse_frontmatter_status(path)
        assert result == (
            "research-only, no elec/src or pcb/ changes made -- this is a "
            "requirements document for a human/planning decision, not an implementation"
        )

    def test_multiline_status_only_one_continuation_line(self, tmp_path):
        """Continuation stops at the next key (unindented line with colon)."""
        path = tmp_path / "plan.md"
        path.write_text(
            '---\n'
            'status: foo bar\n'
            '  baz qux\n'
            'title: "Test"\n'
            '---\n\n# Plan\n'
        )
        result = grs.parse_frontmatter_status(path)
        assert result == "foo bar baz qux"

    def test_status_with_no_continuation(self, tmp_path):
        """Single-line status with no indented continuation."""
        path = tmp_path / "plan.md"
        path.write_text(
            '---\n'
            'status: completed\n'
            'title: "Test"\n'
            '---\n\n# Plan\n'
        )
        result = grs.parse_frontmatter_status(path)
        assert result == "completed"

    def test_status_followed_by_blank_line_then_next_key(self, tmp_path):
        """Blank line before next key is not a continuation."""
        path = tmp_path / "plan.md"
        path.write_text(
            '---\n'
            'status: active\n'
            '\n'
            'title: "Test"\n'
            '---\n\n# Plan\n'
        )
        result = grs.parse_frontmatter_status(path)
        assert result == "active"


class TestPlanInventory:
    def test_counts_by_status_and_active_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(grs, "REPO_ROOT", tmp_path)
        plans_dir = tmp_path / "docs" / "plans"
        plans_dir.mkdir(parents=True)
        _write_plan(plans_dir, "0001-a.md", "active", title="Plan A")
        _write_plan(plans_dir, "0002-b.md", "completed", title="Plan B")
        _write_plan(plans_dir, "0003-c.md", None)

        counts, no_status, active = grs.plan_inventory()
        assert counts == {"active": 1, "completed": 1}
        assert no_status == 1
        assert active == [("0001-a.md", "Plan A")]

    def test_adding_one_active_plan_changes_count_and_active_list(self, tmp_path, monkeypatch):
        """Reproduces the shape of the 2026-07-30 incident: a plan lands with
        ``status: active`` and the derived count/active-list must move."""
        monkeypatch.setattr(grs, "REPO_ROOT", tmp_path)
        plans_dir = tmp_path / "docs" / "plans"
        plans_dir.mkdir(parents=True)
        _write_plan(plans_dir, "0001-a.md", "active", title="Plan A")

        counts_before, _, active_before = grs.plan_inventory()
        assert counts_before["active"] == 1

        _write_plan(plans_dir, "0002-new.md", "active", title="Plan New")
        counts_after, _, active_after = grs.plan_inventory()
        assert counts_after["active"] == 2
        assert ("0002-new.md", "Plan New") in active_after
        assert len(active_after) == len(active_before) + 1

    def test_no_status_documents_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(grs, "REPO_ROOT", tmp_path)
        plans_dir = tmp_path / "docs" / "plans"
        plans_dir.mkdir(parents=True)
        _write_plan(plans_dir, "0001-a.md", None)
        with pytest.raises(grs.GenError, match="no plan documents"):
            grs.plan_inventory()

    def test_missing_plans_dir_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(grs, "REPO_ROOT", tmp_path)
        with pytest.raises(grs.GenError, match="docs/plans/ not found"):
            grs.plan_inventory()


# ---------------------------------------------------------------------------
# End-to-end drift detection via build(), reproducing the actual incident
# class: docs/plans/README.md goes stale relative to the plan fixtures while
# README.md (repo-map/inventory) stays put.
# ---------------------------------------------------------------------------


def _scaffold_repo(tmp_path: Path, monkeypatch, *, plan_status_body: str) -> None:
    monkeypatch.setattr(grs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(grs, "tracked_top_level_dirs", lambda: ["docs", "packages"])
    monkeypatch.setitem(grs.DIRECTORY_PURPOSE, "docs", "test docs")
    monkeypatch.setitem(grs.DIRECTORY_PURPOSE, "packages", "test packages")

    (tmp_path / "packages" / "pkg-a").mkdir(parents=True)

    repo_map_body = grs.render_repo_map()
    inventory_body = grs.render_inventory()

    begin_rm = grs.MARKER_BEGIN.format(name="repo-map")
    end_rm = grs.MARKER_END.format(name="repo-map")
    begin_inv = grs.MARKER_BEGIN.format(name="inventory")
    end_inv = grs.MARKER_END.format(name="inventory")
    readme = (
        f"# README\n\n{begin_rm}\n\n{repo_map_body}\n\n{end_rm}\n\n"
        f"{begin_inv}\n\n{inventory_body}\n\n{end_inv}\n"
    )
    (tmp_path / "README.md").write_text(readme)

    plans_dir = tmp_path / "docs" / "plans"
    plans_dir.mkdir(parents=True)
    _write_plan(plans_dir, "0001-a.md", "active", title="Plan A")

    begin_ps = grs.MARKER_BEGIN.format(name="plan-status")
    end_ps = grs.MARKER_END.format(name="plan-status")
    plans_readme = f"# Plans\n\n{begin_ps}\n\n{plan_status_body}\n\n{end_ps}\n"
    plans_dir.joinpath("README.md").write_text(plans_readme)


class TestDriftDetection:
    def test_stale_plan_status_block_is_flagged_and_only_that_doc(self, tmp_path, monkeypatch):
        # Bake in a plan-status body that does NOT match what render_plan_status()
        # would currently produce (1 active plan) -- simulating main() having
        # moved on since this block was last generated.
        _scaffold_repo(
            tmp_path,
            monkeypatch,
            plan_status_body="*0 plan documents. Generated from frontmatter.*",
        )

        docs = grs.build()
        readme_matches = (tmp_path / "README.md").read_text() == docs["README.md"]
        plans_readme_matches = (tmp_path / "docs" / "plans" / "README.md").read_text() == docs[
            "docs/plans/README.md"
        ]

        assert not plans_readme_matches, "stale plan-status block must be detected as drift"
        assert readme_matches, "repo-map/inventory were baked consistent and must NOT drift"

    def test_matching_plan_status_block_is_not_flagged(self, tmp_path, monkeypatch):
        # First pass: discover what render_plan_status() actually produces for
        # a single-active-plan fixture (same shape _scaffold_repo() bakes),
        # computed in a throwaway root so the real _scaffold_repo() call below
        # creates docs/plans/ fresh -- must round-trip clean.
        scratch_root = tmp_path / "_scratch_for_correct_body"
        scratch_plans_dir = scratch_root / "docs" / "plans"
        scratch_plans_dir.mkdir(parents=True)
        _write_plan(scratch_plans_dir, "0001-a.md", "active", title="Plan A")
        monkeypatch.setattr(grs, "REPO_ROOT", scratch_root)
        correct_body = grs.render_plan_status()

        _scaffold_repo(tmp_path, monkeypatch, plan_status_body=correct_body)

        docs = grs.build()
        assert (tmp_path / "README.md").read_text() == docs["README.md"]
        assert (tmp_path / "docs" / "plans" / "README.md").read_text() == docs[
            "docs/plans/README.md"
        ]


# ---------------------------------------------------------------------------
# The live repo, as actually checked out, via the real CI command.
# ---------------------------------------------------------------------------


class TestRealRepoIsClean:
    def test_check_subprocess_exits_zero(self):
        """Runs the literal command CI runs. Documents that main is
        currently green -- see module docstring for the incident this gate
        went red on earlier the same day, fixed forward before this test
        existed."""
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "gen_repo_state.py"), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "OK" in proc.stdout
