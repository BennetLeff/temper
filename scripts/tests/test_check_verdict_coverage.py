"""Tests for check_verdict_coverage.py.

The script measures two independent things against the same file inventory:
R7 ("should this compute move to Rust?", the ``surfaces:`` list) and R1
("what has to happen before the interpreter can go away?", the new
``removal_surfaces:`` list). These tests focus on the removal axis, since R7's
matching/validation logic is unchanged from before this file existed and the
removal axis reuses it through the same ``entry_matches``/``matches``
functions -- covered incidentally by the shared-matcher tests below.

None of these rely on the real ``docs/wave4-verdicts.yaml`` or the real
``packages/`` tree -- matching the convention in
``test_check_isolation_keepout.py``: every fixture is synthetic, built fresh
per test, so a test failure points at the code under test rather than at
today's ledger contents.

Groups:
  TestMatches            -- pattern/paths matching primitives
  TestValidateRemoval    -- malformed removal_surfaces entries are rejected
  TestComputeCoverage    -- coverage counting: matched/unmatched/multi-match
  TestAntiVacuity         -- a surface with no removal verdict makes the
                             checker FAIL, never silently report 100%
  TestFailBeforePassAfter -- explicit before/after pair, no git stash,
                             mirroring test_check_isolation_keepout.py's
                             falsifier convention
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_verdict_coverage import (  # noqa: E402
    compute_coverage,
    entry_matches,
    matches,
    print_removal_report,
    validate_removal_entries,
)

# ---------------------------------------------------------------------------
# TestMatches
# ---------------------------------------------------------------------------


class TestMatches:
    def test_recursive_pattern_matches_direct_child(self) -> None:
        assert matches("a/b.py", "a/**")

    def test_recursive_pattern_matches_nested_child(self) -> None:
        assert matches("a/b/c/d.py", "a/**")

    def test_recursive_pattern_matches_the_root_itself(self) -> None:
        assert matches("a", "a/**")

    def test_non_recursive_pattern_matches_direct_child(self) -> None:
        assert matches("a/b.py", "a/*.py")

    def test_non_recursive_pattern_does_not_cross_a_slash(self) -> None:
        """The bug this repo's docstring calls out: fnmatch alone gets this
        wrong because its `*` happily crosses `/`."""
        assert not matches("a/b/c.py", "a/*.py")

    def test_unrelated_directory_does_not_match(self) -> None:
        assert not matches("b/c.py", "a/**")

    def test_paths_entry_matches_exact_membership(self) -> None:
        surface = {"paths": ["a/one.py", "a/two.py"], "verdict": "PORT"}
        assert entry_matches("a/one.py", surface)
        assert entry_matches("a/two.py", surface)
        assert not entry_matches("a/three.py", surface)

    def test_pattern_entry_respects_exclude(self) -> None:
        surface = {
            "pattern": "a/**",
            "exclude": ["a/b.py"],
            "verdict": "PORT",
        }
        assert entry_matches("a/c.py", surface)
        assert not entry_matches("a/b.py", surface)


# ---------------------------------------------------------------------------
# TestValidateRemoval
# ---------------------------------------------------------------------------


class TestValidateRemoval:
    def test_well_formed_port_entry_needs_nothing_extra(self) -> None:
        surfaces = [{"paths": ["a/one.py"], "verdict": "PORT"}]
        assert validate_removal_entries(surfaces) == []

    def test_blocker_ortools_without_blocker_field_fails(self) -> None:
        surfaces = [{"paths": ["a/one.py"], "verdict": "BLOCKER-ORTOOLS"}]
        errors = validate_removal_entries(surfaces)
        assert any("requires a `blocker:`" in e for e in errors)

    def test_blocker_scipy_with_blocker_field_passes(self) -> None:
        surfaces = [
            {"paths": ["a/one.py"], "verdict": "BLOCKER-SCIPY", "blocker": "scipy EDT"}
        ]
        assert validate_removal_entries(surfaces) == []

    @pytest.mark.parametrize("verdict", ["REPLACE", "DELETE", "OUT-OF-RUNTIME"])
    def test_note_required_verdicts_without_note_fail(self, verdict: str) -> None:
        surfaces = [{"paths": ["a/one.py"], "verdict": verdict}]
        errors = validate_removal_entries(surfaces)
        assert any("requires a `note:`" in e for e in errors)

    @pytest.mark.parametrize("verdict", ["REPLACE", "DELETE", "OUT-OF-RUNTIME"])
    def test_note_required_verdicts_with_note_pass(self, verdict: str) -> None:
        surfaces = [{"paths": ["a/one.py"], "verdict": verdict, "note": "why"}]
        assert validate_removal_entries(surfaces) == []

    def test_undecided_without_owed_fails(self) -> None:
        surfaces = [{"paths": ["a/one.py"], "verdict": "UNDECIDED"}]
        errors = validate_removal_entries(surfaces)
        assert any("requires an `owed:`" in e for e in errors)

    def test_undecided_with_owed_passes(self) -> None:
        surfaces = [
            {"paths": ["a/one.py"], "verdict": "UNDECIDED", "owed": "a decision"}
        ]
        assert validate_removal_entries(surfaces) == []

    def test_unknown_verdict_rejected(self) -> None:
        surfaces = [{"paths": ["a/one.py"], "verdict": "MIGRATE"}]
        errors = validate_removal_entries(surfaces)
        assert any("unknown removal verdict" in e for e in errors)

    def test_entry_needs_pattern_or_paths(self) -> None:
        surfaces = [{"verdict": "PORT"}]
        errors = validate_removal_entries(surfaces)
        assert any("needs a `pattern:` or a `paths:`" in e for e in errors)

    def test_entry_cannot_have_both_pattern_and_paths(self) -> None:
        surfaces = [
            {"pattern": "a/**", "paths": ["a/one.py"], "verdict": "PORT"}
        ]
        errors = validate_removal_entries(surfaces)
        assert any("cannot have both" in e for e in errors)

    def test_stale_exclude_on_pattern_entry_rejected(self) -> None:
        surfaces = [
            {
                "pattern": "a/**",
                "exclude": ["b/not_under_a.py"],
                "verdict": "PORT",
            }
        ]
        errors = validate_removal_entries(surfaces)
        assert any("excludes nothing" in e for e in errors)


# ---------------------------------------------------------------------------
# TestComputeCoverage
# ---------------------------------------------------------------------------


def _write(root: Path, rel: str, lines: int = 3) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(f"line {i}" for i in range(lines)) + "\n")
    return p


class TestComputeCoverage:
    def test_matched_file_counted_under_its_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        f = _write(tmp_path, "pkg/a.py", lines=5)
        surfaces = [{"pattern": "pkg/**", "verdict": "PORT"}]
        by_verdict, loc_by_verdict, unmatched, multi = compute_coverage([f], surfaces)
        assert len(by_verdict["PORT"]) == 1
        assert loc_by_verdict["PORT"] == 5
        assert unmatched == []
        assert multi == []

    def test_uncovered_file_reported_unmatched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        f = _write(tmp_path, "pkg/a.py")
        by_verdict, loc_by_verdict, unmatched, multi = compute_coverage([f], surfaces=[])
        assert unmatched == ["pkg/a.py"]
        assert by_verdict == {}

    def test_double_matched_file_reported_as_multi(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        f = _write(tmp_path, "pkg/a.py")
        surfaces = [
            {"pattern": "pkg/**", "verdict": "PORT"},
            {"paths": ["pkg/a.py"], "verdict": "DELETE", "note": "x"},
        ]
        by_verdict, loc_by_verdict, unmatched, multi = compute_coverage([f], surfaces)
        assert unmatched == []
        assert len(multi) == 1
        assert "pkg/a.py" in multi[0]


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    """A checker that can only ever say "covered" is worthless. These pin
    the failure mode this whole file exists to prevent: a Python surface
    with no recorded removal verdict must make ``print_removal_report``
    return False (and, at the CLI layer, exit 1), never silently pass."""

    def test_single_uncovered_surface_fails_the_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        f = _write(tmp_path, "pkg/untriaged.py")
        ok = print_removal_report([f], surfaces=[], errors=[])
        assert ok is False

    def test_empty_removal_surfaces_list_fails_on_any_real_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression guard for the specific bug this module replaces: before
        removal_surfaces existed, every file was implicitly "not yet
        triaged" -- an empty list must reproduce that honestly (FAIL), not
        report 0/0 = vacuously 100%."""
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        files = [_write(tmp_path, "pkg/a.py"), _write(tmp_path, "pkg/b.py")]
        ok = print_removal_report(files, surfaces=[], errors=[])
        assert ok is False

    def test_no_files_at_all_is_the_only_vacuous_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The one legitimate 0/0 case: no Python files under the roots at
        all. Distinct from the empty-surfaces case above, which has real
        files going untriaged."""
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        ok = print_removal_report([], surfaces=[], errors=[])
        assert ok is True

    def test_malformed_entry_fails_even_if_every_file_matches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A BLOCKER-ORTOOLS entry with no `blocker:` reason must not count
        as coverage -- an unjustified verdict is the same decorative-100%
        failure mode as an unmatched file, just recorded instead of
        omitted."""
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        f = _write(tmp_path, "pkg/a.py")
        surfaces = [{"pattern": "pkg/**", "verdict": "BLOCKER-ORTOOLS"}]
        errors = validate_removal_entries(surfaces)
        assert errors  # malformed: no blocker given
        ok = print_removal_report([f], surfaces, errors)
        assert ok is False


# ---------------------------------------------------------------------------
# TestFailBeforePassAfter
# ---------------------------------------------------------------------------


class TestFailBeforePassAfter:
    def test_adding_the_missing_verdict_flips_fail_to_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import check_verdict_coverage as cvc

        monkeypatch.setattr(cvc, "REPO_ROOT", tmp_path)
        f = _write(tmp_path, "pkg/a.py")

        # Before: no removal_surfaces entry covers pkg/a.py.
        assert print_removal_report([f], surfaces=[], errors=[]) is False

        # After: a well-formed PORT entry covers it.
        surfaces = [{"paths": ["pkg/a.py"], "verdict": "PORT"}]
        errors = validate_removal_entries(surfaces)
        assert errors == []
        assert print_removal_report([f], surfaces, errors) is True
