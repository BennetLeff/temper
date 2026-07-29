"""Golden-check field classification: descriptive vs. genuine ratchet.

``power_pcb_dataset/baselines/temper_production_baseline.yaml`` used to pin
``component_count``/``net_count`` as frozen absolutes compared for exact
equality against whatever the live board measured. Those two fields are
DESCRIPTIONS of the board, not quality metrics -- a board legitimately
gains and loses parts and nets as the design changes -- so pinning them
guaranteed a recurring false failure on every legitimate board change. It
happened three times in three days on this exact file (149->169->170->168,
see docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md)
and was still red on ``main`` a fourth time before a fifth hand edit papered
over it again.

``RegressionRunner._run_board`` (the code ``golden-check`` actually runs,
via ``temper-placer regression``) now measures component_count/net_count
live from the checked-in board on every run and never compares them to a
stored number -- see ``board_shape`` on the result. ``drc_errors``/
``drc_warnings`` are the opposite case: a real quality ratchet where an
increase is a genuine regression, so they stay pinned and must still fail
the gate.

This module proves both halves of that split directly against
``RegressionRunner._run_board``, exercising a real parsed board (the
``minimal_board.kicad_pcb`` fixture: 4 components, 4 nets) rather than
mocking the parser -- so a future change to the parser or the comparison
logic that reintroduces the old exact-match behavior fails this test, not
just a hand audit.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from temper_placer.regression.manifest import GoldenBoard, GoldenManifest
from temper_placer.regression.runner import RegressionRunner

_FIXTURE_PCB = Path(__file__).resolve().parent.parent / "fixtures" / "minimal_board.kicad_pcb"

# Ground truth for the fixture board, measured once via parse_kicad_pcb.
_FIXTURE_COMPONENT_COUNT = 4
_FIXTURE_NET_COUNT = 4


def _make_runner(tmp_path: Path, baseline: dict) -> tuple[RegressionRunner, GoldenBoard]:
    """Build a RegressionRunner wired to a tmp repo root containing a copy
    of the fixture board and a caller-supplied baseline YAML, mirroring the
    real golden_manifest.yaml + baselines/<id>_baseline.yaml layout.
    """
    repo_root = tmp_path
    pcb_dir = repo_root / "pcb"
    pcb_dir.mkdir(parents=True, exist_ok=True)
    pcb_path = pcb_dir / "board.kicad_pcb"
    pcb_path.write_text(_FIXTURE_PCB.read_text())

    baselines_dir = repo_root / "power_pcb_dataset" / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)
    (baselines_dir / "board_baseline.yaml").write_text(yaml.dump(baseline))

    board_entry = GoldenBoard(
        id="board",
        path="pcb/board.kicad_pcb",
        component_count=baseline.get("component_count", 0),
        net_count=baseline.get("net_count", 0),
        baseline_git_hash="test",
    )
    manifest = GoldenManifest(version=1, boards=[board_entry])
    runner = RegressionRunner(manifest, repo_root=repo_root)
    return runner, board_entry


class TestDescriptiveFieldsNeverGate:
    """component_count/net_count must never fail the gate, regardless of
    what the baseline YAML happens to say -- that is the entire point of
    no longer comparing them.
    """

    def test_matching_counts_pass(self, tmp_path):
        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": _FIXTURE_COMPONENT_COUNT,
                "net_count": _FIXTURE_NET_COUNT,
                "drc_available": False,
                "drc_errors": 0,
                "drc_warnings": 0,
            },
        )
        result = runner._run_board(board_entry)
        assert result.passed, result.errors

    def test_stale_component_count_does_not_fail(self, tmp_path):
        """A baseline recorded against a board shape that no longer exists
        -- exactly the temper_production_baseline.yaml failure mode,
        hand-corrected three times in three days and red on `main` a
        fourth -- must not fail the gate anymore.
        """
        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": 999,  # wildly stale, deliberately wrong
                "net_count": 1,
                "drc_available": False,
                "drc_errors": 0,
                "drc_warnings": 0,
            },
        )
        result = runner._run_board(board_entry)
        assert result.passed, result.errors
        assert not any(d.regression for d in result.deltas)

    def test_board_shape_is_still_reported_for_visibility(self, tmp_path):
        """Not comparing the fields is not the same as hiding them --
        golden-check's output must still show what the board measures.
        """
        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": 999,
                "net_count": 1,
                "drc_available": False,
                "drc_errors": 0,
                "drc_warnings": 0,
            },
        )
        result = runner._run_board(board_entry)
        assert result.board_shape["component_count"] == _FIXTURE_COMPONENT_COUNT
        assert result.board_shape["net_count"] == _FIXTURE_NET_COUNT


class TestGenuineRatchetStillFails:
    """drc_errors/drc_warnings are real quality ratchets: an increase over
    the pinned baseline must still fail the gate. Proven against the same
    `_run_board` code path, with `run_drc` stubbed so the assertion is
    about the comparison logic, not about kicad-cli's availability.
    """

    def test_drc_error_increase_fails(self, tmp_path, monkeypatch):
        import temper_placer.validation._drc_api as drc_api

        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": _FIXTURE_COMPONENT_COUNT,
                "net_count": _FIXTURE_NET_COUNT,
                "drc_available": True,
                "drc_errors": 5,
                "drc_warnings": 0,
            },
        )
        result_obj = type("R", (), {"error_count": 12, "warning_count": 0})()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)

        result = runner._run_board(board_entry)
        assert not result.passed
        assert any(d.name == "drc_errors" and d.regression for d in result.deltas)
        assert "drc_errors" in result.errors[0]
        # The failure message must say what to do, not just that it failed.
        assert "re-measure" in result.errors[0].lower()

    def test_drc_error_within_baseline_passes(self, tmp_path, monkeypatch):
        import temper_placer.validation._drc_api as drc_api

        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": _FIXTURE_COMPONENT_COUNT,
                "net_count": _FIXTURE_NET_COUNT,
                "drc_available": True,
                "drc_errors": 12,
                "drc_warnings": 0,
            },
        )
        result_obj = type("R", (), {"error_count": 5, "warning_count": 0})()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)

        result = runner._run_board(board_entry)
        assert result.passed, result.errors

    def test_drc_warning_increase_fails(self, tmp_path, monkeypatch):
        import temper_placer.validation._drc_api as drc_api

        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": _FIXTURE_COMPONENT_COUNT,
                "net_count": _FIXTURE_NET_COUNT,
                "drc_available": True,
                "drc_errors": 0,
                "drc_warnings": 3,
            },
        )
        result_obj = type("R", (), {"error_count": 0, "warning_count": 9})()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)

        result = runner._run_board(board_entry)
        assert not result.passed
        assert any(d.name == "drc_warnings" and d.regression for d in result.deltas)

    def test_drc_is_sampled_and_medianed_not_read_once(self, tmp_path, monkeypatch):
        """KiCad's DRC scatters run-to-run on an unchanged board
        (test_regression_drc.py documents shorting_items varying by ~20) --
        a single reading can't tell a real regression from noise. This
        proves _run_board takes the median of DRC_SAMPLE_RUNS samples
        rather than a single `run_drc()` call.
        """
        import temper_placer.validation._drc_api as drc_api
        from temper_placer.regression import runner as runner_module

        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": _FIXTURE_COMPONENT_COUNT,
                "net_count": _FIXTURE_NET_COUNT,
                "drc_available": True,
                "drc_errors": 10,
                "drc_warnings": 0,
            },
        )
        # Scatter: median of [9, 9, 9, 20, 20] is 9 -- passes. A
        # single-sample implementation would sometimes read 20 and fail.
        samples = iter(
            [
                type("R", (), {"error_count": 9, "warning_count": 0})(),
                type("R", (), {"error_count": 20, "warning_count": 0})(),
                type("R", (), {"error_count": 9, "warning_count": 0})(),
                type("R", (), {"error_count": 20, "warning_count": 0})(),
                type("R", (), {"error_count": 9, "warning_count": 0})(),
            ]
        )
        calls = []

        def _fake_run_drc(_p):
            calls.append(1)
            return next(samples)

        monkeypatch.setattr(drc_api, "run_drc", _fake_run_drc)

        result = runner._run_board(board_entry)
        assert len(calls) == runner_module.DRC_SAMPLE_RUNS == 5
        assert result.passed, result.errors
        (err_delta,) = [d for d in result.deltas if d.name == "drc_errors"]
        assert err_delta.current == 9  # median, not the last/first/max sample

    def test_drc_available_but_unmeasurable_hard_fails_not_silent_zero(self, tmp_path, monkeypatch):
        """drc_available: true means the baseline was measured WITH real
        DRC data. If DRC can't actually run (kicad-cli missing, crashes,
        whatever), silently falling back to comparing a fabricated 0
        against the pinned ceiling would always pass -- turning a genuine
        ratchet vacuous exactly the way golden-check went vacuous when it
        ran on an image with no kicad-cli at all. This must be a hard
        failure, not a skip that reads as clean.
        """
        import temper_placer.validation._drc_api as drc_api

        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": _FIXTURE_COMPONENT_COUNT,
                "net_count": _FIXTURE_NET_COUNT,
                "drc_available": True,
                "drc_errors": 999999,  # would trivially "pass" against a fake 0
                "drc_warnings": 999999,
            },
        )

        def _boom(_p):
            raise RuntimeError("kicad-cli: command not found")

        monkeypatch.setattr(drc_api, "run_drc", _boom)

        result = runner._run_board(board_entry)
        assert not result.passed
        assert not result.skipped  # a hard failure, not a soft skip
        assert "hard failure" in result.errors[0].lower()
        assert "kicad-cli" in result.errors[0].lower()


class TestBothTogether:
    """The realistic case: the board's descriptive shape changed AND a
    genuine DRC regression landed in the same run. Only the ratchet may
    fail the gate.
    """

    def test_shape_change_plus_real_regression_fails_for_drc_only(self, tmp_path, monkeypatch):
        import temper_placer.validation._drc_api as drc_api

        runner, board_entry = _make_runner(
            tmp_path,
            {
                "component_count": 999,  # stale, would have failed the old gate
                "net_count": 1,  # stale, would have failed the old gate
                "drc_available": True,
                "drc_errors": 0,
                "drc_warnings": 0,
            },
        )
        result_obj = type("R", (), {"error_count": 3, "warning_count": 0})()
        monkeypatch.setattr(drc_api, "run_drc", lambda _p: result_obj)

        result = runner._run_board(board_entry)
        assert not result.passed
        regressed_names = {d.name for d in result.deltas if d.regression}
        assert regressed_names == {"drc_errors"}
