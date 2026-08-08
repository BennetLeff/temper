"""DRC must never run project-context-blind (2026-08-08 audit).

kicad-cli resolves a KiCad project by finding ``<stem>.kicad_pro`` next to
the board file it is asked to DRC. When that file is missing, kicad-cli does
NOT error and does NOT warn -- it silently drops every violation sourced
from the project's custom ``pcb/temper.kicad_dru`` rules (``track_width``
and, critically, ``creepage`` -- the IEC 60335-1 HV/LV isolation check) and
from ``temper.kicad_pro``'s ``rule_severities`` overrides
(``missing_courtyard``, ``annular_width``). See
docs/evidence/2026-08-08-drc-power-token-jump-root-cause.md and
docs/evidence/2026-08-08-drc-project-context-audit.md for the measured
magnitude: on this repo's board, WITH project context 1249 errors / 489
warnings; WITHOUT it, 828 errors / 621 warnings, with creepage/track_width/
annular_width/missing_courtyard entirely absent (not zero -- absent) from
the report.

This module asserts the fix: every kicad-cli DRC entry point in this
codebase (``_drc_api.run_drc`` and the test suite's independent
``_parallel_drc.run_drc_loud``) refuses to run rather than silently
under-measuring, and ``copy_kicad_project_sidecar`` is the supported way to
give a scratch board copy a resolvable project.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from temper_placer.validation._drc_api import (
    DrcProjectContextError,
    DrcRunnerError,
    copy_kicad_project_sidecar,
    ensure_resolvable_kicad_project,
    is_kicad_cli_available,
    run_drc,
)

from tests.placer.cp_sat._parallel_drc import run_drc_loud

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REAL_BOARD = _REPO_ROOT / "pcb" / "temper.kicad_pcb"
_REAL_PROJECT = _REPO_ROOT / "pcb" / "temper.kicad_pro"


class TestEnsureResolvableKicadProject:
    """Unit tests for the guard function itself -- no subprocess involved."""

    def test_raises_when_sibling_project_missing(self, tmp_path):
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        with pytest.raises(DrcProjectContextError, match="No resolvable KiCad project"):
            ensure_resolvable_kicad_project(pcb)

    def test_passes_when_sibling_project_present(self, tmp_path):
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        pcb.with_suffix(".kicad_pro").write_text("{}")
        ensure_resolvable_kicad_project(pcb)  # must not raise

    def test_project_context_error_is_a_drc_runner_error(self):
        """Callers that already catch the broad DrcRunnerError (CI's
        ci_check_drc.py, RegressionRunner._run_board, ...) must not need a
        second except clause to see this failure -- it has to surface as a
        measurement failure, never pass silently through a broad handler
        that assumes 'no DrcRunnerError' means 'measured cleanly'."""
        assert issubclass(DrcProjectContextError, DrcRunnerError)


class TestCopyKicadProjectSidecar:
    def test_propagates_project_and_dru_under_the_copy_s_own_stem(self, tmp_path):
        source_pcb = tmp_path / "source" / "real.kicad_pcb"
        source_pcb.parent.mkdir()
        source_pcb.write_text("(kicad_pcb)")
        (tmp_path / "source" / "real.kicad_pro").write_text('{"marker": "source-project"}')
        (tmp_path / "source" / "real.kicad_dru").write_text("(version 1)(rule x)")

        scratch_pcb = tmp_path / "scratch" / "routed.kicad_pcb"
        scratch_pcb.parent.mkdir()
        scratch_pcb.write_text("(kicad_pcb) ; routed copy")

        copy_kicad_project_sidecar(scratch_pcb, source_pcb)

        dest_project = scratch_pcb.with_suffix(".kicad_pro")
        dest_dru = scratch_pcb.with_suffix(".kicad_dru")
        assert dest_project.exists(), "expected routed.kicad_pro next to the scratch copy"
        assert "source-project" in dest_project.read_text()
        assert dest_dru.exists(), "expected routed.kicad_dru propagated alongside it"

        # And now the guard is satisfied for the scratch copy specifically.
        ensure_resolvable_kicad_project(scratch_pcb)

    def test_no_dru_on_source_is_not_fatal(self, tmp_path):
        """Not every project has custom DRU rules -- only .kicad_pro is
        required for kicad-cli to resolve rule_severities; .kicad_dru is
        optional on top of that."""
        source_pcb = tmp_path / "source" / "real.kicad_pcb"
        source_pcb.parent.mkdir()
        source_pcb.write_text("(kicad_pcb)")
        (tmp_path / "source" / "real.kicad_pro").write_text("{}")

        scratch_pcb = tmp_path / "scratch" / "routed.kicad_pcb"
        scratch_pcb.parent.mkdir()
        scratch_pcb.write_text("(kicad_pcb)")

        copy_kicad_project_sidecar(scratch_pcb, source_pcb)  # must not raise
        assert scratch_pcb.with_suffix(".kicad_pro").exists()
        assert not scratch_pcb.with_suffix(".kicad_dru").exists()

    def test_raises_when_source_has_no_project_to_propagate(self, tmp_path):
        source_pcb = tmp_path / "source.kicad_pcb"
        source_pcb.write_text("(kicad_pcb)")  # no source.kicad_pro

        scratch_pcb = tmp_path / "scratch.kicad_pcb"
        scratch_pcb.write_text("(kicad_pcb)")

        with pytest.raises(FileNotFoundError, match="has no"):
            copy_kicad_project_sidecar(scratch_pcb, source_pcb)


class TestRunDrcRefusesBlindMeasurement:
    """run_drc() must hit the guard before it ever shells out to kicad-cli."""

    def test_raises_before_touching_kicad_cli(self, tmp_path, monkeypatch):
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")  # no sibling .kicad_pro

        called = {"subprocess": False}

        def _fail_if_called(*args, **kwargs):
            called["subprocess"] = True
            raise AssertionError("run_drc must not shell out without a resolvable project")

        monkeypatch.setattr(
            "temper_placer.validation._drc_api.is_kicad_cli_available", lambda: True
        )
        monkeypatch.setattr(
            "temper_placer.validation._drc_api.subprocess.run", _fail_if_called
        )

        with pytest.raises(DrcProjectContextError):
            run_drc(pcb)

        assert called["subprocess"] is False


class TestRunDrcLoudRefusesBlindMeasurement:
    """_parallel_drc.run_drc_loud -- the SECOND, independent raw kicad-cli
    invocation this test suite uses (the router-output DRC regression
    gates) -- must carry the identical guard. It historically did not:
    every routed-board sample measured through it was project-context-blind.
    """

    def test_raises_before_touching_kicad_cli(self, tmp_path, monkeypatch):
        pcb = tmp_path / "routed.kicad_pcb"
        pcb.write_text("(kicad_pcb)")  # no sibling .kicad_pro

        called = {"subprocess": False}

        def _fail_if_called(*args, **kwargs):
            called["subprocess"] = True
            raise AssertionError("run_drc_loud must not shell out without a resolvable project")

        monkeypatch.setattr("tests.placer.cp_sat._parallel_drc.subprocess.Popen", _fail_if_called)

        with pytest.raises(DrcProjectContextError):
            run_drc_loud(pcb, timeout=5, label="test")

        assert called["subprocess"] is False


@pytest.mark.integration
@pytest.mark.skipif(not is_kicad_cli_available(), reason="requires real kicad-cli")
class TestRealKicadCliConcealmentMagnitude:
    """The measurement this bug actually produced, reproduced against real
    kicad-cli: DRC'ing a real board copy with vs without a resolvable
    project must show the concealed categories, not just an aggregate-count
    difference (an aggregate delta alone would not distinguish this bug
    from ordinary DRC nondeterminism -- see
    docs/evidence/2026-08-04-drc-measurement-determinism.md)."""

    def test_missing_project_drops_creepage_and_track_width_entirely(self, tmp_path):
        if not (_REAL_BOARD.exists() and _REAL_PROJECT.exists()):
            pytest.skip("real production board/project not present in this checkout")

        # WITH project context (the fixed, correct call): run in place.
        with_ctx = run_drc(_REAL_BOARD)
        with_ctx_rules = {e.rule for e in with_ctx.errors} | {w.rule for w in with_ctx.warnings}

        # WITHOUT project context: a bare copy of the same board content,
        # deliberately with no sibling .kicad_pro -- reproduces exactly the
        # harness bug this audit root-caused, on demand, in CI.
        blind_pcb = tmp_path / "temper.kicad_pcb"
        shutil.copyfile(_REAL_BOARD, blind_pcb)
        # dru is optional to reproduce with; the project alone is enough to
        # make kicad-cli see any project-derived category.
        real_dru = _REAL_BOARD.with_suffix(".kicad_dru")
        if real_dru.exists():
            shutil.copyfile(real_dru, blind_pcb.with_suffix(".kicad_dru"))

        with pytest.raises(DrcProjectContextError):
            run_drc(blind_pcb)

        # And bypassing our own guard to observe kicad-cli's raw behaviour
        # directly (what the pre-fix code path actually measured) --
        # confirms the guard is preventing a REAL silent gap, not a
        # hypothetical one.
        import subprocess as _subprocess
        import tempfile as _tempfile
        import json as _json

        json_out = _tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        json_out.close()
        try:
            _subprocess.run(
                [
                    "kicad-cli", "pcb", "drc", "--all-track-errors",
                    "--format", "json", "--output", json_out.name, str(blind_pcb),
                ],
                capture_output=True, text=True, timeout=60, check=True,
            )
            data = _json.loads(Path(json_out.name).read_text())
            blind_rules = {v["type"] for v in data["violations"]}
        finally:
            Path(json_out.name).unlink(missing_ok=True)

        concealed = {"creepage", "track_width", "missing_courtyard", "annular_width"}
        present_with_context = concealed & with_ctx_rules
        assert present_with_context, (
            "expected the real board to have at least one of "
            f"{concealed} with project context resolved -- got {with_ctx_rules}; "
            "if this now legitimately reads empty the board's real defects "
            "were fixed and this assertion should be revisited, not deleted"
        )
        vanished = present_with_context - blind_rules
        assert vanished == present_with_context, (
            f"expected ALL of {present_with_context} to vanish (not just shrink) "
            f"without project context -- still present blind: {present_with_context & blind_rules}. "
            "If kicad-cli's project-resolution behaviour changed, this test "
            "documents that change; do not silently loosen the assertion."
        )
