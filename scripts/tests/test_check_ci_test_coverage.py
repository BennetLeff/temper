"""Tests for ``scripts/check_ci_test_coverage.py`` -- and its falsifiability.

Three layers, deliberately.

``TestSyntheticDetection`` builds a miniature repo in ``tmp_path`` -- its own
``.github/workflows``, its own package tree, its own ``CMakeLists.txt`` -- and
runs the gate against it. Detection *rules* are pinned there, independent of
whatever the real tree happens to contain on any given day. Both directions get
a positive (the seeded defect IS reported) and an adjacent negative (the nearly
identical clean shape is NOT reported); a detector with no adjacent negative is
indistinguishable from a rubber stamp.

``TestRealRepo`` runs the gate against the actual repository and pins the
properties that must hold whatever the counts are today: the scan is not
vacuous, every path it calls dead really is absent, and every path it credits
as covered really does exist. It deliberately does NOT pin today's dead-count
to a number -- that number is supposed to reach zero and stay there, and a test
asserting "exactly 8" would have to be edited by the very commit that fixes
them.

``TestMutation`` is the layer that makes the other two mean something. It
rewrites the gate's own source -- the comparison, the anti-vacuity guard, the
scan scope -- and requires that each weakening flips a DECLARED set of probes
from detecting to not-detecting, AND THAT NO OTHER PROBE MOVES. A mutation that
kills nothing is a blind spot in these tests; a mutation that kills everything
means the probes are coupled and prove less than they appear to. This repo
already shipped a vacuity gate (PR #1392) because 74 of 86 assertions could not
fail. This file is not allowed to add an 87th.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_ci_test_coverage as gate  # noqa: E402

REPO_ROOT = Path(gate.REPO_ROOT)
GATE_SOURCE = Path(gate.__file__).resolve()


# ---------------------------------------------------------------------------
# The synthetic repo.
#
# It exercises every working-directory spelling the real workflows use, because
# working-directory resolution is where a hand count of this exact defect got
# the answer wrong (10 reported, 8 true).
# ---------------------------------------------------------------------------

WORKFLOW = """\
name: Synthetic
on: [push]
jobs:
  step-wd:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: packages/pkg_a
    steps:
      - name: job-default wd
        run: uv run pytest tests/test_alpha.py -v --tb=short
      - name: step wd overrides job default
        working-directory: packages/pkg_b
        run: uv run pytest tests/test_beta.py -p no:cacheprovider
  root:
    runs-on: ubuntu-latest
    steps:
      - name: cd inside the run block
        run: |
          cd packages/pkg_a && uv run python ../../scripts/pytest_guard.py \\
            --min-tests 3 -- tests/sub/ -v --tb=short
      - name: cd inside a subshell, then back at the root
        run: |
          (cd packages/pkg_b && uv run pytest tests/test_gamma.py) &
          uv run pytest scripts/tests/test_delta.py -q
          wait
      - name: ctest
        run: |
          cmake -B firmware/test/build firmware/test
          ctest --test-dir firmware/test/build -R "registered" --output-on-failure
"""

CMAKELISTS = """\
add_executable(test_registered_only registered.c)
add_executable(test_orphan_guard_only orphan.c)
# add_executable(test_commented_out_only commented.c)
add_test(NAME registered_tests COMMAND test_registered_only)
add_test(NAME never_selected_tests COMMAND test_registered_only)
"""

SYNTHETIC_FILES = (
    "packages/pkg_a/tests/test_alpha.py",
    "packages/pkg_b/tests/test_beta.py",
    "packages/pkg_a/tests/sub/test_under_a_directory.py",
    "packages/pkg_b/tests/test_gamma.py",
    "scripts/tests/test_delta.py",
)


def _write(root: Path, rel: str, content: str = "def test_ok():\n    assert True\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clean miniature repo: every CI reference resolves, nothing is orphaned."""
    _write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)
    _write(tmp_path, "firmware/test/CMakeLists.txt", CMAKELISTS)
    for rel in SYNTHETIC_FILES:
        _write(tmp_path, rel)
    return tmp_path


def _inventory(root: Path, entries: tuple[tuple[str, str], ...] = ()) -> Path:
    path = root / ".ci-test-coverage-inventory"
    lines = ["# synthetic ledger"]
    lines += [f"{kind}\t{ident}\tsynthetic-reason" for kind, ident in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# The synthetic repo's baseline direction-B population: the two ctest findings
# that CMAKELISTS deliberately seeds. Written out so a test that adds a NEW
# uncovered file can ledger these and isolate its own seeded finding.
BASELINE_LEDGER = (
    ("ctest-unregistered", "test_orphan_guard_only"),
    ("ctest-unselected", "never_selected_tests"),
)


def _run(mod, root: Path, inv: Path):
    return mod.analyze(root, inv)


# ---------------------------------------------------------------------------
# Layer 1 -- detection rules, on a synthetic tree
# ---------------------------------------------------------------------------


class TestWorkingDirectoryResolution:
    """The crux: a path means nothing without the cwd it is resolved against."""

    def test_every_spelling_resolves_to_the_right_file(self, repo: Path) -> None:
        refs, _ = gate.parse_workflows(repo)
        resolved = {r.path for r in refs if r.kind == gate.KIND_TARGET}
        assert "packages/pkg_a/tests/test_alpha.py" in resolved  # job default wd
        assert "packages/pkg_b/tests/test_beta.py" in resolved  # step wd override
        assert "packages/pkg_a/tests/sub" in resolved  # cd in the run block
        assert "packages/pkg_b/tests/test_gamma.py" in resolved  # cd in a subshell
        assert "scripts/tests/test_delta.py" in resolved  # back at the root

    def test_a_subshell_cd_does_not_leak_to_the_next_command(self, repo: Path) -> None:
        """`(cd pkg_b && ...) &` then `pytest scripts/...` -- the second is at root.

        Getting this wrong is not a cosmetic error: it turns a live reference
        into a phantom dead one, which is the direction-A false positive that
        would make this gate un-landable.
        """
        refs, _ = gate.parse_workflows(repo)
        delta = [r for r in refs if r.path.endswith("test_delta.py")]
        assert delta, "the post-subshell reference was lost entirely"
        assert delta[0].cwd == ".", f"subshell cd leaked; cwd was {delta[0].cwd!r}"
        assert delta[0].path == "scripts/tests/test_delta.py"

    def test_resolving_everything_against_one_package_would_invent_dead_refs(
        self, repo: Path
    ) -> None:
        """Pin the failure mode the per-step resolution exists to avoid.

        This is the mistake that produced a hand count of 10 where the truth
        was 8. If someone later replaces the cwd walk with a single root, this
        test is what tells them the number they get is wrong.
        """
        refs, _ = gate.parse_workflows(repo)
        naive_dead = [
            r
            for r in refs
            if r.kind == gate.KIND_TARGET
            and not (repo / "packages/pkg_a" / r.raw.split("::")[0]).exists()
        ]
        assert naive_dead, "the fixture no longer distinguishes the two resolutions"
        assert gate.dead_references(refs, repo) == [], (
            "the correct per-step resolution must report NO dead references here"
        )


class TestDirectionA:
    """A CI job naming a nonexistent path. Hard fail, no ledger."""

    def test_clean_repo_reports_no_dead_references(self, repo: Path) -> None:
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        assert result.dead_refs == []
        assert result.dead_selectors == []

    def test_detects_a_deleted_file_still_named_by_a_job(self, repo: Path) -> None:
        """THE falsifiability proof for direction A.

        Reproduces the real incident in miniature: delete a test file, leave
        its name in the job's list. pytest would exit 4 with zero collected and
        the whole step would run nothing.
        """
        (repo / "packages/pkg_b/tests/test_beta.py").unlink()
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        dead = {r.path for r in result.dead_refs}
        assert "packages/pkg_b/tests/test_beta.py" in dead
        assert not result.ok

    def test_exit_code_is_one_and_the_report_names_the_file(self, repo: Path) -> None:
        (repo / "packages/pkg_b/tests/test_beta.py").unlink()
        _inventory(repo, BASELINE_LEDGER)
        code = gate.main(["--repo-root", str(repo)])
        assert code == 1

    def test_detects_a_deleted_file_named_only_in_a_deselect(self, repo: Path) -> None:
        """A `--deselect` naming a deleted file is dead weight that hides the gap."""
        wf = repo / ".github/workflows/ci.yml"
        wf.write_text(
            WORKFLOW.replace(
                "uv run pytest tests/test_alpha.py -v --tb=short",
                "uv run pytest tests/ --deselect tests/test_vanished.py::test_x",
            ),
            encoding="utf-8",
        )
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        assert "packages/pkg_a/tests/test_vanished.py" in {
            r.path for r in result.dead_refs
        }

    def test_an_alternation_branch_matching_nothing_is_reported(self, repo: Path) -> None:
        """`-R "a|b"` is TWO requests, and a live half hides a dead one.

        Not hypothetical: `firmware-tests.yml` compiles `test_fault_list_only`
        and then runs `ctest -R "state_machine|fault_list"`, but no `add_test`
        NAME contains `fault_list`. Confirmed directly with
        `ctest -N -R "state_machine|fault_list"` against a real configure of
        `firmware/test`: Total Tests: 1 (`state_machine_tests`). The binary is
        built on every CI run and never executed.
        """
        wf = repo / ".github/workflows/ci.yml"
        wf.write_text(
            WORKFLOW.replace('-R "registered"', '-R "registered|never_built"'),
            encoding="utf-8",
        )
        result = _run(gate, repo, _inventory(repo))
        assert [s.regex for s in result.dead_selectors] == ["never_built"]

    def test_split_on_top_level_pipes_only(self) -> None:
        """A `|` inside a group or a character class is not an alternative."""
        assert gate.top_level_alternatives("a|b") == ["a", "b"]
        assert gate.top_level_alternatives("(a|b)c") == ["(a|b)c"]
        assert gate.top_level_alternatives("[a|b]c|d") == ["[a|b]c", "d"]
        assert gate.top_level_alternatives(r"a\|b") == [r"a\|b"]
        assert gate.top_level_alternatives("solo") == ["solo"]

    def test_a_ctest_regex_matching_nothing_is_reported(self, repo: Path) -> None:
        """`ctest -R` on an empty selection exits 0 -- silent unless someone looks."""
        cmake = repo / "firmware/test/CMakeLists.txt"
        cmake.write_text(
            CMAKELISTS.replace("add_test(NAME registered_tests", "add_test(NAME other_tests"),
            encoding="utf-8",
        )
        result = _run(gate, repo, _inventory(repo))
        assert [s.regex for s in result.dead_selectors] == ["registered"]


class TestDirectionB:
    """A test file that exists and that no CI job runs. Shrink-only ratchet."""

    def test_detects_a_test_file_no_job_runs(self, repo: Path) -> None:
        """THE falsifiability proof for direction B."""
        _write(repo, "packages/pkg_a/tests/test_never_run.py")
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        assert (
            "pytest-uncovered",
            "packages/pkg_a/tests/test_never_run.py",
        ) in result.new_uncovered
        assert not result.ok

    def test_a_ledgered_file_passes(self, repo: Path) -> None:
        """The adjacent negative: the ratchet must not fail on recorded debt."""
        _write(repo, "packages/pkg_a/tests/test_never_run.py")
        inv = _inventory(
            repo,
            BASELINE_LEDGER
            + (("pytest-uncovered", "packages/pkg_a/tests/test_never_run.py"),),
        )
        result = _run(gate, repo, inv)
        assert result.new_uncovered == []
        assert result.ok

    def test_a_ledgered_entry_that_became_covered_is_a_failure(self, repo: Path) -> None:
        """Paid-down debt must leave the books, or it hides the next regression."""
        inv = _inventory(
            repo,
            BASELINE_LEDGER + (("pytest-uncovered", "packages/pkg_a/tests/test_alpha.py"),),
        )
        result = _run(gate, repo, inv)
        assert (
            "pytest-uncovered",
            "packages/pkg_a/tests/test_alpha.py",
        ) in result.stale_entries
        assert not result.ok

    def test_the_ratchet_cannot_be_widened_by_hand_without_a_diff(self, repo: Path) -> None:
        """--write-inventory is the only sanctioned way to change the ledger."""
        _write(repo, "packages/pkg_a/tests/test_never_run.py")
        inv = _inventory(repo)
        assert gate.main(["--repo-root", str(repo)]) == 1
        gate.main(["--repo-root", str(repo), "--write-inventory"])
        body = inv.read_text(encoding="utf-8")
        assert "packages/pkg_a/tests/test_never_run.py" in body
        assert gate.DEFAULT_REASON in body
        assert gate.main(["--repo-root", str(repo)]) == 0

    def test_a_directory_reference_covers_the_files_beneath_it(self, repo: Path) -> None:
        _write(repo, "packages/pkg_a/tests/sub/test_second_file.py")
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        assert result.new_uncovered == [], (
            "a file under a directory CI names must count as covered"
        )

    def test_deselect_does_not_remove_a_file_from_coverage(self, repo: Path) -> None:
        """Deselecting one test does not stop the file's other tests running."""
        wf = repo / ".github/workflows/ci.yml"
        wf.write_text(
            WORKFLOW.replace(
                "uv run pytest tests/test_alpha.py -v --tb=short",
                "uv run pytest tests/test_alpha.py --deselect tests/test_alpha.py::test_ok",
            ),
            encoding="utf-8",
        )
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        assert result.new_uncovered == []

    def test_ignore_does_remove_a_file_from_coverage(self, repo: Path) -> None:
        """An --ignored file is a file CI does not run. That is the whole point."""
        wf = repo / ".github/workflows/ci.yml"
        wf.write_text(
            WORKFLOW.replace(
                "uv run python ../../scripts/pytest_guard.py \\\n            --min-tests 3 -- tests/sub/ -v --tb=short",
                "uv run python ../../scripts/pytest_guard.py \\\n            --min-tests 3 -- tests/sub/ --ignore=tests/sub/test_under_a_directory.py",
            ),
            encoding="utf-8",
        )
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        assert (
            "pytest-uncovered",
            "packages/pkg_a/tests/sub/test_under_a_directory.py",
        ) in result.new_uncovered

    def test_a_copy_inside_a_build_tree_is_not_a_test_file(self, repo: Path) -> None:
        """The denominator must not depend on whether cmake has been run here.

        `firmware/test/build/` is created by the firmware job's own
        `cmake -B firmware/test/build firmware/test`, and it contains copies of
        generated test sources. Counting those would make the ratchet's
        denominator differ between a fresh checkout and a built one -- a
        ratchet that moves on its own is not a ratchet.
        """
        _write(repo, "firmware/test/build/CMakeFiles/test_copied_artifact.py")
        _write(repo, "packages/pkg_a/tests/__pycache__/test_alpha.py")
        universe = gate.discover_test_files(repo)
        assert not [f for f in universe if "build/" in f or "__pycache__" in f]
        result = _run(gate, repo, _inventory(repo, BASELINE_LEDGER))
        assert result.new_uncovered == []

    def test_a_ctest_binary_with_no_add_test_is_reported(self, repo: Path) -> None:
        """The shape that hid a thermistor conversion wrong by ~60 C."""
        result = _run(gate, repo, _inventory(repo))
        assert ("ctest-unregistered", "test_orphan_guard_only") in result.new_uncovered

    def test_a_registered_ctest_no_ci_selector_matches_is_reported(self, repo: Path) -> None:
        result = _run(gate, repo, _inventory(repo))
        assert ("ctest-unselected", "never_selected_tests") in result.new_uncovered

    def test_a_registered_ctest_a_selector_does_match_is_not_reported(
        self, repo: Path
    ) -> None:
        result = _run(gate, repo, _inventory(repo))
        assert ("ctest-unselected", "registered_tests") not in result.new_uncovered


class TestAntiVacuity:
    """A collapsed denominator is a TOOL ERROR, never a clean run."""

    def test_zero_ci_references_is_a_tool_error(self, repo: Path) -> None:
        (repo / ".github/workflows/ci.yml").write_text(
            "name: X\non: [push]\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: echo hello\n",
            encoding="utf-8",
        )
        with pytest.raises(gate.ToolError):
            _run(gate, repo, _inventory(repo))
        assert gate.main(["--repo-root", str(repo)]) == 2

    def test_zero_test_files_is_a_tool_error(self, repo: Path) -> None:
        for rel in SYNTHETIC_FILES:
            (repo / rel).unlink()
        with pytest.raises(gate.ToolError):
            _run(gate, repo, _inventory(repo))
        assert gate.main(["--repo-root", str(repo)]) == 2

    def test_both_counts_are_printed_on_a_passing_run(self, repo: Path, capsys) -> None:
        """A denominator collapsing to zero must be visible, not inferable."""
        _inventory(repo, BASELINE_LEDGER)
        assert gate.main(["--repo-root", str(repo)]) == 0
        out = capsys.readouterr().out
        assert "CI-referenced test paths enumerated :" in out
        assert "test files on disk                  :" in out
        assert "VERDICT: PASS" in out


# ---------------------------------------------------------------------------
# Layer 2 -- the real repository
# ---------------------------------------------------------------------------


class TestRealRepo:
    def test_the_scan_is_not_vacuous(self) -> None:
        result = gate.analyze(REPO_ROOT, REPO_ROOT / gate.INVENTORY.name)
        assert result.referenced_paths > 0
        assert result.test_files > 0
        assert result.covered_files > 0

    def test_every_reported_dead_reference_really_is_absent(self) -> None:
        """Soundness. A false positive here would block every PR in the repo."""
        refs, _ = gate.parse_workflows(REPO_ROOT)
        for ref in gate.dead_references(refs, REPO_ROOT):
            assert not (REPO_ROOT / ref.path).exists(), (
                f"{ref.path} was reported dead but exists ({ref.where})"
            )

    def test_every_file_credited_as_covered_really_exists(self) -> None:
        refs, _ = gate.parse_workflows(REPO_ROOT)
        universe = gate.discover_test_files(REPO_ROOT)
        for rel in gate.covered_test_files(refs, REPO_ROOT, universe):
            assert (REPO_ROOT / rel).is_file()

    def test_the_inventory_is_parseable_and_every_entry_is_reachable_in_kind(self) -> None:
        entries = gate.read_inventory(REPO_ROOT / gate.INVENTORY.name)
        assert entries, "the ledger is empty -- see --write-inventory"
        kinds = {k for k, _ in entries}
        assert kinds <= {"pytest-uncovered", "ctest-unregistered", "ctest-unselected"}

    def test_every_ledgered_entry_carries_a_reason(self) -> None:
        for (kind, ident), reason in gate.read_inventory(
            REPO_ROOT / gate.INVENTORY.name
        ).items():
            assert reason, f"{kind} {ident} has no reason"

    def test_the_five_known_unregistered_firmware_suites_are_seen(self) -> None:
        """Named in the incident. If the CMake parser breaks, these vanish first."""
        binaries, _ = gate.parse_ctest(REPO_ROOT)
        unregistered = {b.target for b in binaries if not b.registered_as}
        for target in (
            "test_ntc_guard_only",
            "test_adc_guard_only",
            "test_fan_guard_only",
            "test_coil_guard_only",
            "test_pwm_guard_only",
        ):
            assert target in unregistered

    def test_gate_runs_as_a_subprocess(self) -> None:
        """It must work from a cold interpreter, not only under this session."""
        proc = subprocess.run(
            [sys.executable, str(GATE_SOURCE)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert proc.returncode in (0, 1), proc.stderr
        assert "CI-referenced test paths enumerated" in proc.stdout


# ---------------------------------------------------------------------------
# Layer 3 -- mutation. Neutering the comparison must fail these tests, and
# only these.
# ---------------------------------------------------------------------------


def _probe_direction_a(mod, repo: Path) -> bool:
    """Does the gate notice a CI reference to a deleted file?"""
    (repo / "packages/pkg_b/tests/test_beta.py").unlink()
    result = _run(mod, repo, _inventory(repo, BASELINE_LEDGER))
    return "packages/pkg_b/tests/test_beta.py" in {r.path for r in result.dead_refs}


def _probe_direction_a_clean(mod, repo: Path) -> bool:
    """Does the gate stay quiet when every referenced path exists?"""
    result = _run(mod, repo, _inventory(repo, BASELINE_LEDGER))
    return result.dead_refs == []


def _probe_direction_b_new(mod, repo: Path) -> bool:
    """Does the gate notice a test file no job runs?"""
    _write(repo, "packages/pkg_a/tests/test_never_run.py")
    result = _run(mod, repo, _inventory(repo, BASELINE_LEDGER))
    return (
        "pytest-uncovered",
        "packages/pkg_a/tests/test_never_run.py",
    ) in result.new_uncovered


def _probe_direction_b_clean(mod, repo: Path) -> bool:
    """Does the gate stay quiet when the uncovered set is exactly the ledger?

    Deliberately reads the ratchet fields rather than ``result.ok``: ``ok``
    folds in direction A, and a probe that moves when the OTHER direction is
    weakened would be reporting coupling as coverage.
    """
    result = _run(mod, repo, _inventory(repo, BASELINE_LEDGER))
    return not result.new_uncovered and not result.stale_entries


def _probe_scope_scripts_tests(mod, repo: Path) -> bool:
    """Is `scripts/tests` inside the direction-B denominator at all?"""
    _write(repo, "scripts/tests/test_orphan_under_scripts.py")
    result = _run(mod, repo, _inventory(repo, BASELINE_LEDGER))
    return (
        "pytest-uncovered",
        "scripts/tests/test_orphan_under_scripts.py",
    ) in result.new_uncovered


def _probe_ctest_alternation(mod, repo: Path) -> bool:
    """Does the gate notice a `-R` alternative that selects nothing?"""
    (repo / ".github/workflows/ci.yml").write_text(
        WORKFLOW.replace('-R "registered"', '-R "registered|never_built"'),
        encoding="utf-8",
    )
    result = _run(mod, repo, _inventory(repo))
    return "never_built" in {s.regex for s in result.dead_selectors}


def _probe_anti_vacuity_refs(mod, repo: Path) -> bool:
    """Does a zero-reference scan raise instead of reporting a clean run?"""
    (repo / ".github/workflows/ci.yml").write_text(
        "name: X\non: [push]\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo hello\n",
        encoding="utf-8",
    )
    try:
        _run(mod, repo, _inventory(repo))
    except mod.ToolError:
        return True
    return False


def _probe_anti_vacuity_files(mod, repo: Path) -> bool:
    """Does a zero-test-file scan raise instead of reporting a clean run?"""
    for rel in SYNTHETIC_FILES:
        (repo / rel).unlink()
    try:
        _run(mod, repo, _inventory(repo))
    except mod.ToolError:
        return True
    return False


PROBES = {
    "direction-a": _probe_direction_a,
    "direction-a-clean": _probe_direction_a_clean,
    "direction-b-new": _probe_direction_b_new,
    "direction-b-clean": _probe_direction_b_clean,
    "scope-scripts-tests": _probe_scope_scripts_tests,
    "ctest-alternation": _probe_ctest_alternation,
    "anti-vacuity-refs": _probe_anti_vacuity_refs,
    "anti-vacuity-files": _probe_anti_vacuity_files,
}


# (mutation id) -> (old source, new source, probes that MUST flip to False).
#
# Every mutation is a weakening this repo has actually shipped at least once:
# a comparison stubbed to a constant, an existence test inverted, a scan root
# quietly dropped, an anti-vacuity raise deleted, a ratchet diff neutered.
MUTATIONS: dict[str, tuple[str, str, frozenset[str]]] = {
    # "return a constant success" -- the highest-severity mutant there is.
    "direction-a-return-constant": (
        "    dead: list[CIReference] = []\n"
        "    for ref in refs:\n"
        "        if not (repo_root / ref.path).exists():\n"
        "            dead.append(ref)\n"
        "    return dead",
        "    return []",
        frozenset({"direction-a"}),
    ),
    # The backwards-comparison class: `not exists` -> `exists`.
    "direction-a-invert-existence": (
        "        if not (repo_root / ref.path).exists():",
        "        if (repo_root / ref.path).exists():",
        frozenset({"direction-a", "direction-a-clean"}),
    ),
    # Credit every file as covered: the direction-B comparison, stubbed.
    "direction-b-cover-everything": (
        "        covered |= selected - ignored",
        "        covered |= universe",
        frozenset({"direction-b-new", "scope-scripts-tests"}),
    ),
    # Keep the comparison but neuter the ratchet diff.
    "direction-b-never-report-new": (
        "    new_uncovered = sorted(current - set(previous))",
        "    new_uncovered = []",
        frozenset({"direction-b-new", "scope-scripts-tests"}),
    ),
    # Gate-subset blindness: a whole scan root silently stops being counted.
    "scope-remove-scripts-tests": (
        '    "packages/*/tests",\n    "scripts/tests",',
        '    "packages/*/tests",',
        frozenset({"scope-scripts-tests"}),
    ),
    # Check the `-R` pattern as a whole instead of per alternative -- the
    # weakening that would let `ctest -R "state_machine|fault_list"` look
    # green while its `fault_list` half selects nothing.
    "ctest-check-whole-pattern-only": (
        "        for alternative in top_level_alternatives(sel.regex):",
        "        for alternative in [sel.regex]:",
        frozenset({"ctest-alternation"}),
    ),
    # Strip the anti-vacuity guard, so an empty scan reports a clean run
    # instead of a tool error. Mutated as a WHOLE because the three checks
    # inside `require_nonvacuous` are layered and each subsumes the next --
    # see that function's docstring. A single-line strip would SURVIVE, and a
    # mutation that cannot be killed is not evidence of anything, so it is not
    # registered here dressed up as one.
    "anti-vacuity-strip-all-guards": (
        "    covered = covered_test_files(refs, repo_root, universe)\n"
        "    require_nonvacuous(refs, universe, covered)",
        "    covered = covered_test_files(refs, repo_root, universe)",
        frozenset({"anti-vacuity-refs", "anti-vacuity-files"}),
    ),
    # The cwd walk itself: pin every path to the repo root. This is the exact
    # approximation that produced a hand count of 10 where the truth was 8 --
    # it must be visible to these tests, not merely documented.
    "cwd-ignore-working-directory": (
        "            start = _normalize(\".\", wd)",
        '            start = "."',
        # The blast radius is wide ON PURPOSE, and recorded rather than
        # trimmed: with everything resolved against the repo root, live paths
        # get reported dead (direction-a-clean), the genuinely dead one is
        # reported under the wrong name so the probe misses it (direction-a),
        # and files CI does run stop being credited (direction-b-clean). That
        # is precisely what the 10-where-8-was-true count looked like from
        # the inside.
        frozenset({"direction-a", "direction-a-clean", "direction-b-clean"}),
    ),
}


def _load_mutant(source: str, name: str, tmp_path: Path):
    """Import a mutated copy under a throwaway module name.

    Registered in ``sys.modules`` for the duration of the exec (dataclasses
    resolves ``cls.__module__`` through it) and removed immediately after, so
    no mutant is ever importable under the gate's real name.
    """
    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.fixture
def pristine_source() -> str:
    return GATE_SOURCE.read_text(encoding="utf-8")


class TestMutation:
    def test_every_probe_passes_against_the_unmutated_gate(self, tmp_path: Path) -> None:
        """The baseline. A probe that cannot pass proves nothing when it fails."""
        for probe_name, probe in PROBES.items():
            scratch = tmp_path / f"pristine-{probe_name}"
            scratch.mkdir()
            _write(scratch, ".github/workflows/ci.yml", WORKFLOW)
            _write(scratch, "firmware/test/CMakeLists.txt", CMAKELISTS)
            for rel in SYNTHETIC_FILES:
                _write(scratch, rel)
            assert probe(gate, scratch), f"probe {probe_name!r} fails on the real gate"

    @pytest.mark.parametrize("mutation_id", sorted(MUTATIONS))
    def test_mutation_kills_exactly_the_declared_probes(
        self, mutation_id: str, pristine_source: str, tmp_path: Path
    ) -> None:
        old, new, expected_killed = MUTATIONS[mutation_id]
        assert expected_killed, (
            f"mutation {mutation_id!r} declares an EMPTY kill set. A mutation "
            "no probe notices is a registered blind spot, not a passing test; "
            "it must never be spelled as an expectation."
        )
        occurrences = pristine_source.count(old)
        assert occurrences == 1, (
            f"mutation {mutation_id!r} no longer locates its target "
            f"({occurrences} matches). The gate drifted; the mutation applied "
            "nothing and therefore proves nothing. Re-anchor it -- do not delete it."
        )
        mutant_source = pristine_source.replace(old, new)
        mutant = _load_mutant(
            mutant_source, f"mutant_{mutation_id.replace('-', '_')}", tmp_path
        )

        killed: set[str] = set()
        for probe_name, probe in PROBES.items():
            scratch = tmp_path / f"{mutation_id}-{probe_name}"
            scratch.mkdir()
            _write(scratch, ".github/workflows/ci.yml", WORKFLOW)
            _write(scratch, "firmware/test/CMakeLists.txt", CMAKELISTS)
            for rel in SYNTHETIC_FILES:
                _write(scratch, rel)
            try:
                detected = probe(mutant, scratch)
            except Exception:  # a mutant that explodes is also "noticed"
                detected = False
            if not detected:
                killed.add(probe_name)

        assert killed == set(expected_killed), (
            f"mutation {mutation_id!r} killed {sorted(killed)}, "
            f"declared {sorted(expected_killed)}.\n"
            "  Extra kills mean the probes are coupled and prove less than they look.\n"
            "  Missing kills mean this weakening is INVISIBLE to these tests -- a "
            "blind spot, which is the finding, not a reason to relax the assertion."
        )

    def test_the_committed_gate_is_never_mutated_on_disk(
        self, pristine_source: str
    ) -> None:
        """No mutant is ever written where the repository can pick it up."""
        digest = hashlib.sha256(GATE_SOURCE.read_bytes()).hexdigest()
        assert (
            hashlib.sha256(pristine_source.encode("utf-8")).hexdigest() == digest
        )
