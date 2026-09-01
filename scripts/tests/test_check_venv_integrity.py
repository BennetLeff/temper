"""Tests for check_venv_integrity.py.

Four groups:

1. `TestPthParsing` -- `iter_pth_path_entries` correctly separates literal
   path lines from comments, blank lines, and `import ...` lines (the
   `_virtualenv.pth` / coverage auto-start shape).
2. `TestDirectUrlParsing` -- `direct_url_local_path` extracts a local path
   from a `file://` URL, ignores non-local (PyPI/index) installs, and fails
   closed (GateError) on unreadable/malformed JSON rather than skipping it.
3. `TestClassifyPath` -- the pure classification function: under repo root
   (OK), under a *different* registered worktree nested inside repo root
   (VIOLATION, and checked ahead of the repo-root prefix test), and
   entirely outside repo root (VIOLATION).
4. `TestHijackReconstruction` -- THE motivating-incident proof. Builds a
   scratch venv whose `.pth` files and `direct_url.json` entries are
   rewritten to point at a synthetic "agent worktree" nested under the
   synthetic repo root (reconstructing the exact 2026-08-11 incident
   layout: `_editable_impl_temper_placer.pth -> .claude/worktrees/agent-X`),
   and shows `run()` reports it as a violation with exit code
   `EXIT_VIOLATION`. Then repairs the same files to point at the repo root
   and shows a clean pass. Also covers the "entirely unrelated checkout"
   shape (a sibling directory, not nested under repo root at all) and the
   anti-vacuity backstop (empty site-packages is a GATE ERROR, not a PASS).
5. `TestFindCwdWorktree` / `TestMode5Warning` -- the mode-5 advisory (the
   2026-08-17 shape: a *healthy* shared venv serving main's code to a
   worktree agent). `find_cwd_worktree` resolves cwd to the most specific
   registered worktree (nested worktrees win over the main-checkout
   prefix); `mode5_warning` returns the advisory string exactly when cwd
   is a worktree and the venv (or `VIRTUAL_ENV`) resolves under the main
   checkout but not under that worktree, and None otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_venv_integrity import (  # noqa: E402
    EXIT_OK,
    EXIT_VIOLATION,
    GateError,
    classify_path,
    decide_exit_code,
    direct_url_local_path,
    find_cwd_worktree,
    find_site_packages,
    iter_pth_path_entries,
    mode5_warning,
    run,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _make_venv_skeleton(venv_root: Path) -> Path:
    site_packages = venv_root / "lib" / "python3.12" / "site-packages"
    site_packages.mkdir(parents=True)
    return site_packages


class TestPthParsing:
    def test_literal_path_line(self, tmp_path: Path) -> None:
        pth = _write(tmp_path / "x.pth", "/some/path/src\n")
        assert iter_pth_path_entries(pth) == ["/some/path/src"]

    def test_comment_and_blank_lines_skipped(self, tmp_path: Path) -> None:
        pth = _write(tmp_path / "x.pth", "# a comment\n\n   \n/real/path\n")
        assert iter_pth_path_entries(pth) == ["/real/path"]

    def test_import_line_not_treated_as_path(self, tmp_path: Path) -> None:
        # Exact shape of _virtualenv.pth in a real venv.
        pth = _write(tmp_path / "_virtualenv.pth", "import _virtualenv\n")
        assert iter_pth_path_entries(pth) == []

    def test_import_exec_form_not_treated_as_path(self, tmp_path: Path) -> None:
        # Exact shape of coverage's auto-start .pth (a1_coverage.pth).
        pth = _write(
            tmp_path / "a1_coverage.pth",
            "import sys; exec('import os\\nif os.getenv(\"X\"): pass\\n')\n",
        )
        assert iter_pth_path_entries(pth) == []

    def test_multiple_path_lines(self, tmp_path: Path) -> None:
        pth = _write(tmp_path / "x.pth", "/a/src\n/b/src\n")
        assert iter_pth_path_entries(pth) == ["/a/src", "/b/src"]

    def test_unreadable_file_raises_gate_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.pth"
        with pytest.raises(GateError):
            iter_pth_path_entries(missing)


class TestDirectUrlParsing:
    def test_file_url_extracted(self, tmp_path: Path) -> None:
        durl = _write(
            tmp_path / "direct_url.json",
            json.dumps({"url": "file:///home/x/repo/packages/temper-placer", "dir_info": {"editable": True}}),
        )
        assert direct_url_local_path(durl) == Path("/home/x/repo/packages/temper-placer")

    def test_non_file_url_ignored(self, tmp_path: Path) -> None:
        durl = _write(
            tmp_path / "direct_url.json",
            json.dumps({"url": "https://pypi.org/simple/numpy/"}),
        )
        assert direct_url_local_path(durl) is None

    def test_missing_url_field_ignored(self, tmp_path: Path) -> None:
        durl = _write(tmp_path / "direct_url.json", json.dumps({"dir_info": {}}))
        assert direct_url_local_path(durl) is None

    def test_malformed_json_fails_closed(self, tmp_path: Path) -> None:
        durl = _write(tmp_path / "direct_url.json", "{not valid json")
        with pytest.raises(GateError):
            direct_url_local_path(durl)

    def test_url_encoded_path_decoded(self, tmp_path: Path) -> None:
        durl = _write(
            tmp_path / "direct_url.json",
            json.dumps({"url": "file:///home/x/repo%20name/pkg"}),
        )
        assert direct_url_local_path(durl) == Path("/home/x/repo name/pkg")


class TestClassifyPath:
    def test_under_repo_root_is_ok(self, tmp_path: Path) -> None:
        repo_root = (tmp_path / "repo").resolve()
        candidate = repo_root / "packages" / "temper-placer" / "src"
        verdict = classify_path(candidate, repo_root, other_worktrees=[])
        assert verdict.ok

    def test_repo_root_itself_is_ok(self, tmp_path: Path) -> None:
        repo_root = (tmp_path / "repo").resolve()
        verdict = classify_path(repo_root, repo_root, other_worktrees=[])
        assert verdict.ok

    def test_nested_worktree_is_a_violation_even_though_under_repo_root(
        self, tmp_path: Path
    ) -> None:
        # This is the crux of the whole gate: .claude/worktrees/agent-X IS a
        # subdirectory of repo_root on disk, so a naive prefix test alone
        # would pass it. It must be caught because it is a DIFFERENT
        # registered worktree.
        repo_root = (tmp_path / "repo").resolve()
        worktree = repo_root / ".claude" / "worktrees" / "agent-ab1dbe8162fa0fbae"
        candidate = worktree / "packages" / "temper-placer" / "src"
        verdict = classify_path(candidate, repo_root, other_worktrees=[worktree])
        assert not verdict.ok
        assert "different git worktree" in verdict.detail

    def test_sibling_checkout_entirely_outside_repo_root_is_a_violation(
        self, tmp_path: Path
    ) -> None:
        repo_root = (tmp_path / "repo").resolve()
        sibling = (tmp_path / "repo-consolidation-inventory").resolve()
        candidate = sibling / "packages" / "temper-placer" / "src"
        verdict = classify_path(candidate, repo_root, other_worktrees=[])
        assert not verdict.ok
        assert "outside the expected repo root entirely" in verdict.detail

    def test_worktree_path_itself_flagged(self, tmp_path: Path) -> None:
        repo_root = (tmp_path / "repo").resolve()
        worktree = repo_root / ".claude" / "worktrees" / "agent-x"
        verdict = classify_path(worktree, repo_root, other_worktrees=[worktree])
        assert not verdict.ok


class TestFindSitePackages:
    def test_missing_venv_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GateError):
            find_site_packages(tmp_path / "no-such-venv")

    def test_finds_posix_layout(self, tmp_path: Path) -> None:
        venv_root = tmp_path / "venv"
        site_packages = _make_venv_skeleton(venv_root)
        assert find_site_packages(venv_root) == site_packages

    def test_no_site_packages_raises(self, tmp_path: Path) -> None:
        venv_root = tmp_path / "venv"
        venv_root.mkdir()
        with pytest.raises(GateError):
            find_site_packages(venv_root)


class TestHijackReconstruction:
    """The motivating-incident proof: reconstruct the exact 2026-08-11
    hijack shape in a scratch tree, show the real (unmodified) gate fails
    it, then show the same gate passes a clean venv.
    """

    def _setup(self, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
        repo_root = (tmp_path / "repo").resolve()
        (repo_root / "packages" / "temper-placer" / "src").mkdir(parents=True)
        (repo_root / ".git").mkdir()

        worktree = (repo_root / ".claude" / "worktrees" / "agent-ab1dbe8162fa0fbae").resolve()
        (worktree / "packages" / "temper-placer" / "src").mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: ../../../.git/worktrees/agent-ab1dbe8162fa0fbae\n")

        venv_root = tmp_path / "venv"
        site_packages = _make_venv_skeleton(venv_root)
        return repo_root, worktree, venv_root, site_packages

    def test_hijacked_pth_is_reported_as_a_violation(self, tmp_path: Path) -> None:
        repo_root, worktree, venv_root, site_packages = self._setup(tmp_path)

        # Exact reconstruction of the incident's own filenames and shape.
        _write(
            site_packages / "_editable_impl_temper_placer.pth",
            f"{worktree / 'packages' / 'temper-placer' / 'src'}\n",
        )

        report = run(venv_root, repo_root, other_worktrees=[repo_root, worktree])

        assert len(report.violations) == 1
        assert "different git worktree" in report.violations[0].verdict.detail
        assert decide_exit_code(report) == EXIT_VIOLATION

    def test_hijacked_direct_url_is_reported_as_a_violation(self, tmp_path: Path) -> None:
        repo_root, worktree, venv_root, site_packages = self._setup(tmp_path)

        dist_info = site_packages / "temper_placer-0.1.0.dist-info"
        dist_info.mkdir()
        hijacked_path = worktree / "packages" / "temper-placer"
        _write(
            dist_info / "direct_url.json",
            json.dumps({"url": f"file://{hijacked_path}", "dir_info": {"editable": True}}),
        )

        report = run(venv_root, repo_root, other_worktrees=[repo_root, worktree])

        assert len(report.violations) == 1
        assert report.violations[0].kind == "direct_url"
        assert decide_exit_code(report) == EXIT_VIOLATION

    def test_repaired_pth_passes_clean(self, tmp_path: Path) -> None:
        repo_root, worktree, venv_root, site_packages = self._setup(tmp_path)

        # Same file, now pointed at the repo root -- the "fixed" state.
        _write(
            site_packages / "_editable_impl_temper_placer.pth",
            f"{repo_root / 'packages' / 'temper-placer' / 'src'}\n",
        )

        report = run(venv_root, repo_root, other_worktrees=[repo_root, worktree])

        assert report.violations == []
        assert decide_exit_code(report) == EXIT_OK

    def test_mixed_venv_one_hijacked_one_clean_still_fails(self, tmp_path: Path) -> None:
        repo_root, worktree, venv_root, site_packages = self._setup(tmp_path)

        _write(
            site_packages / "_editable_impl_temper_placer.pth",
            f"{repo_root / 'packages' / 'temper-placer' / 'src'}\n",
        )
        _write(
            site_packages / "_editable_impl_temper_workflow.pth",
            f"{worktree / 'packages' / 'temper-placer' / 'src'}\n",
        )

        report = run(venv_root, repo_root, other_worktrees=[repo_root, worktree])

        assert len(report.entries) == 2
        assert len(report.violations) == 1
        assert decide_exit_code(report) == EXIT_VIOLATION

    def test_unrelated_sibling_checkout_also_fails(self, tmp_path: Path) -> None:
        repo_root, worktree, venv_root, site_packages = self._setup(tmp_path)
        sibling = (tmp_path / "repo-consolidation-inventory").resolve()
        (sibling / "packages" / "temper-placer" / "src").mkdir(parents=True)

        _write(
            site_packages / "_editable_impl_temper_placer.pth",
            f"{sibling / 'packages' / 'temper-placer' / 'src'}\n",
        )

        report = run(venv_root, repo_root, other_worktrees=[repo_root, worktree])

        assert len(report.violations) == 1
        assert "outside the expected repo root entirely" in report.violations[0].verdict.detail


class TestAntiVacuity:
    def test_empty_site_packages_is_a_gate_error_not_a_pass(self, tmp_path: Path) -> None:
        repo_root = (tmp_path / "repo").resolve()
        repo_root.mkdir()
        venv_root = tmp_path / "venv"
        _make_venv_skeleton(venv_root)  # empty: no .pth, no dist-info

        with pytest.raises(GateError):
            run(venv_root, repo_root, other_worktrees=[repo_root])

    def test_pth_files_with_only_import_lines_still_vacuous(self, tmp_path: Path) -> None:
        repo_root = (tmp_path / "repo").resolve()
        repo_root.mkdir()
        venv_root = tmp_path / "venv"
        site_packages = _make_venv_skeleton(venv_root)
        _write(site_packages / "_virtualenv.pth", "import _virtualenv\n")

        with pytest.raises(GateError):
            run(venv_root, repo_root, other_worktrees=[repo_root])

    def test_missing_venv_is_a_gate_error(self, tmp_path: Path) -> None:
        repo_root = (tmp_path / "repo").resolve()
        repo_root.mkdir()
        with pytest.raises(GateError):
            run(tmp_path / "no-such-venv", repo_root, other_worktrees=[repo_root])


class TestFindCwdWorktree:
    def test_cwd_in_main_checkout_resolves_to_main(self, tmp_path: Path) -> None:
        main_root = (tmp_path / "temper").resolve()
        main_root.mkdir()
        cwd = main_root / "packages"
        cwd.mkdir()
        assert find_cwd_worktree(cwd, [main_root]) == main_root

    def test_cwd_in_nested_worktree_wins_over_main_prefix(self, tmp_path: Path) -> None:
        main_root = (tmp_path / "temper").resolve()
        wt = main_root / ".claude" / "worktrees" / "agent-x"
        wt.mkdir(parents=True)
        cwd = wt / "scripts"
        cwd.mkdir()
        assert find_cwd_worktree(cwd, [main_root, wt]) == wt

    def test_cwd_in_sibling_worktree(self, tmp_path: Path) -> None:
        main_root = (tmp_path / "temper").resolve()
        main_root.mkdir()
        wt = (tmp_path / "temper-wt").resolve()
        wt.mkdir()
        assert find_cwd_worktree(wt, [main_root, wt]) == wt

    def test_cwd_outside_any_worktree(self, tmp_path: Path) -> None:
        main_root = (tmp_path / "temper").resolve()
        main_root.mkdir()
        elsewhere = (tmp_path / "elsewhere").resolve()
        elsewhere.mkdir()
        assert find_cwd_worktree(elsewhere, [main_root]) is None


class TestMode5Warning:
    """The 2026-08-17 shape: a *healthy* shared venv serving main's code."""

    def _make(self, tmp_path: Path):
        main_root = (tmp_path / "temper").resolve()
        main_root.mkdir()
        shared_venv = main_root / ".venv"
        wt = (tmp_path / "temper-wt").resolve()
        wt.mkdir()
        return main_root, shared_venv, wt

    def test_main_checkout_with_shared_venv_is_fine(self, tmp_path: Path) -> None:
        main_root, shared_venv, wt = self._make(tmp_path)
        assert mode5_warning(shared_venv, main_root, main_root) is None

    def test_worktree_with_shared_venv_warns(self, tmp_path: Path) -> None:
        main_root, shared_venv, wt = self._make(tmp_path)
        warning = mode5_warning(shared_venv, main_root, wt)
        assert warning is not None
        assert "make venv-isolate" in warning
        assert str(shared_venv) in warning

    def test_worktree_with_its_own_venv_is_fine(self, tmp_path: Path) -> None:
        main_root, shared_venv, wt = self._make(tmp_path)
        own_venv = wt / ".venv"
        assert mode5_warning(own_venv, main_root, wt) is None

    def test_worktree_with_venv_outside_repo_is_fine(self, tmp_path: Path) -> None:
        main_root, shared_venv, wt = self._make(tmp_path)
        outside = (tmp_path / "unrelated" / ".venv").resolve()
        assert mode5_warning(outside, main_root, wt) is None

    def test_cwd_outside_any_worktree_is_fine(self, tmp_path: Path) -> None:
        main_root, shared_venv, wt = self._make(tmp_path)
        assert mode5_warning(shared_venv, main_root, None) is None

    def test_nested_worktree_with_shared_venv_warns(self, tmp_path: Path) -> None:
        main_root, shared_venv, wt = self._make(tmp_path)
        nested_wt = main_root / ".claude" / "worktrees" / "agent-x"
        nested_wt.mkdir(parents=True)
        warning = mode5_warning(shared_venv, main_root, nested_wt)
        assert warning is not None
        assert "make venv-isolate" in warning

    def test_active_venv_env_var_triggers_warning(self, tmp_path: Path) -> None:
        main_root, shared_venv, wt = self._make(tmp_path)
        # the interpreter itself is fine (e.g. system python), but
        # VIRTUAL_ENV points at the shared venv -- still mode 5.
        system_python = (tmp_path / "usr" / "bin").resolve()
        system_python.mkdir(parents=True)
        warning = mode5_warning(system_python, main_root, wt, active_venv=shared_venv)
        assert warning is not None
        assert "make venv-isolate" in warning

    def test_checked_venv_is_shared_warns_even_if_virtual_env_points_elsewhere(self, tmp_path: Path) -> None:
        # The venv being *checked* (sys.prefix of the interpreter) is
        # authoritative: if it is the shared venv, imports resolve to main
        # regardless of what VIRTUAL_ENV claims.
        main_root, shared_venv, wt = self._make(tmp_path)
        own_venv = wt / ".venv"
        warning = mode5_warning(shared_venv, main_root, wt, active_venv=own_venv)
        assert warning is not None
        assert "make venv-isolate" in warning
