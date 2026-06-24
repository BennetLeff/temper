"""Tests for the minimum-viable DRC fence (U1: 3-state DRC status).

R1 (3-state) / R6 (replace default-to-100%) are exercised here.  U2
(posture) and U3 (schema) / U4 (cache) tests live alongside these
because the fence is one object with three orthogonal properties, but
the U1 contract is the load-bearing one: ``DrcStatus`` is the typed
enum that the rest of the fence composes on.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.regression.closure_test import ClosureResult, ClosureTest
from temper_placer.regression.measure_closure import measure_closure
from temper_placer.validation.drc_runner import (
    DrcError,
    DrcResult,
    DrcRunnerError,
    DrcStatus,
    DrcWarning,
    FencePosture,
    run_drc,
)
from temper_placer.validation.drc_schema import (
    DRCC_V1_SCHEMA_VERSION,
    EMPTY_SHA256,
    compute_board_hash,
    compute_design_rule_set_hash,
    compute_kicad_cli_version,
    compute_provenance,
    compute_router_commit,
    from_drcc_v1,
    to_drcc_v1,
)
from temper_placer.validation.drc_state import DRCC_V1, FenceState
from temper_placer.validation.drc_cache import DrcCache, make_cache_key


class TestDrcStatusEnum:
    """The 3-state enum is the load-bearing type for the fence."""

    def test_three_members(self) -> None:
        """DrcStatus must have exactly PASS / FAIL / UNVERIFIED."""
        members = {m.name for m in DrcStatus}
        assert members == {"PASS", "FAIL", "UNVERIFIED"}

    def test_values_are_stringly_distinct(self) -> None:
        """Each member has a unique string value (used in JSON output)."""
        values = {m.value for m in DrcStatus}
        assert len(values) == 3
        assert "PASS" in values
        assert "FAIL" in values
        assert "UNVERIFIED" in values


class TestDrcResultDefaultStatus:
    """The default status must be UNVERIFIED, never PASS."""

    def test_default_is_unverified(self) -> None:
        """An uninitialized DrcResult must not look like a PASS."""
        result = DrcResult(error_count=0, warning_count=0)
        assert result.drc_status == DrcStatus.UNVERIFIED

    def test_default_with_zero_errors_is_still_unverified(self) -> None:
        """``error_count=0`` alone does not imply PASS — the dataclass
        default is UNVERIFIED, and only ``_parse_drc_json`` ever
        promotes to PASS / FAIL.  This is the property that closes
        the false-PASS path: you cannot construct a clean-looking
        DrcResult without explicitly setting the status.
        """
        result = DrcResult(error_count=0, warning_count=0)
        assert result.error_count == 0
        assert result.drc_status == DrcStatus.UNVERIFIED


class TestParseDrcJsonDerivesStatus:
    """``_parse_drc_json`` is the only place that promotes UNVERIFIED→PASS/FAIL."""

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_clean_board_yields_pass(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """No errors, no warnings → drc_status == PASS."""
        from temper_placer.validation import drc_runner

        pcb = tmp_path / "clean.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "violations": [],
                    "unconnected_items": [],
                    "schematic_parity": [],
                    "ignored_checks": [],
                }
            )
        )
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = run_drc(pcb)

        assert result.drc_status == DrcStatus.PASS
        assert result.error_count == 0

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_warnings_only_yields_pass(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Warnings (no errors) → drc_status == PASS — warnings are
        non-blocking, only errors are gating.
        """
        from temper_placer.validation import drc_runner

        pcb = tmp_path / "warn.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "violations": [
                        {
                            "type": "silk_over_pads",
                            "severity": "warning",
                            "description": "Silkscreen over pad",
                            "pos": {"x": 0.0, "y": 0.0},
                            "items": [{"reference": "R1"}],
                        }
                    ],
                }
            )
        )
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = run_drc(pcb)

        assert result.drc_status == DrcStatus.PASS
        assert result.error_count == 0
        assert result.warning_count == 1

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_errors_yield_fail(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Any error-severity violation → drc_status == FAIL."""
        from temper_placer.validation import drc_runner

        pcb = tmp_path / "dirty.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "violations": [
                        {
                            "type": "clearance",
                            "severity": "error",
                            "description": "Clearance violation",
                            "pos": {"x": 1.0, "y": 2.0},
                            "items": [{"reference": "U1"}, {"reference": "U2"}],
                        }
                    ],
                }
            )
        )
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = run_drc(pcb)

        assert result.drc_status == DrcStatus.FAIL
        assert result.error_count == 1

    @patch("temper_placer.validation.drc_runner.is_kicad_cli_available", return_value=False)
    def test_missing_kicad_cli_raises_drc_runner_error(
        self, mock_avail: MagicMock, tmp_path: Path
    ) -> None:
        """With no kicad-cli, run_drc raises — no DrcResult is produced
        (U1 only; U2 introduces the posture=REPORT path that returns
        UNVERIFIED instead of raising).
        """
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        with pytest.raises(DrcRunnerError):
            run_drc(pcb)


class TestClosureResultDrcStatus:
    """``ClosureResult`` must surface ``drc_status`` from the runner."""

    def test_closure_result_has_drc_status_field(self) -> None:
        """The field exists with default None (legacy / not-yet-run)."""
        r = ClosureResult(passed=True, board_id="temper")
        assert hasattr(r, "drc_status")
        assert r.drc_status is None

    def test_closure_result_drc_status_round_trip(self) -> None:
        """The field accepts a DrcStatus enum value."""
        r = ClosureResult(
            passed=True, board_id="temper", drc_status=DrcStatus.PASS
        )
        assert r.drc_status == DrcStatus.PASS
        r2 = ClosureResult(
            passed=False, board_id="temper", drc_status=DrcStatus.UNVERIFIED
        )
        assert r2.drc_status == DrcStatus.UNVERIFIED


class TestMeasureClosureStatusMapping:
    """The match-statement in ``measure_closure`` is the false-PASS fix.

    The pre-U1 bug was: ``if stages_exercised >= 4 and drc_errors == 0:
    100.0``.  This made a missing measurement (kicad-cli unavailable,
    ``drc_errors == 0`` because the exception was swallowed) look like
    a perfect PASS.  The U1 contract is that an UNVERIFIED measurement
    is ``None`` — distinct from 100.0 — so the SM2 gate fails loudly.
    """

    def _build_closure_result(
        self,
        *,
        drc_status: DrcStatus | None,
        drc_errors: int = 0,
        stages_exercised: int = 4,
    ) -> ClosureResult:
        return ClosureResult(
            passed=drc_status == DrcStatus.PASS,
            board_id="temper",
            benders_iterations=1,
            benders_cuts=0,
            router_completion_pct=100.0,
            drc_errors=drc_errors,
            drc_warnings=0,
            drc_status=drc_status,
            stages_exercised=stages_exercised,
        )

    def test_unverified_yields_none_not_100(self) -> None:
        """The pre-U1 false-PASS: this is the bug fix."""
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.UNVERIFIED, stages_exercised=4
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] is None
        assert payload["drc_status"] == "UNVERIFIED"
        # The pre-U1 bug would have produced 100.0 here.

    def test_pass_yields_100(self) -> None:
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.PASS, stages_exercised=4
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 100.0
        assert payload["drc_status"] == "PASS"

    def test_fail_yields_penalty_formula(self) -> None:
        """A FAIL is a measured result, not a default.  The penalty
        is ``max(0, 100 - 10*errors)`` — the same formula as the
        pre-U1 code, but reached only when a real measurement exists.
        """
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.FAIL,
                drc_errors=3,
                stages_exercised=4,
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 70.0
        assert payload["drc_status"] == "FAIL"

    def test_fail_with_zero_errors_is_100(self) -> None:
        """Defensive: ``DrcStatus.FAIL`` with 0 errors is a degenerate
        case (the parser would normally produce PASS).  The penalty
        formula produces 100.0, which is correct.
        """
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=DrcStatus.FAIL,
                drc_errors=0,
                stages_exercised=4,
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 100.0

    def test_none_drc_status_falls_through_to_zero(self) -> None:
        """Legacy / pre-U1 callers that set ``drc_status=None`` map to
        ``0.0`` — the same as ``stages_exercised < 4``.  This is the
        only path where the result is a numeric zero rather than a
        typed-null or a real measurement.
        """
        with patch.object(ClosureTest, "run") as mock_run:
            mock_run.return_value = self._build_closure_result(
                drc_status=None, stages_exercised=2
            )
            payload = measure_closure(Path("/fake/board.kicad_pcb"))
        assert payload["drc_clearance_pass_pct"] == 0.0
        assert payload["drc_status"] is None


class TestFalsePassBugRegression:
    """Regression: the pre-U1 default-to-100% line must not exist."""

    def test_measure_closure_does_not_hard_code_100(self, tmp_path: Path) -> None:
        """The literal pattern ``drc_clearance_pass_pct = 100.0`` must
        not appear in ``measure_closure.py`` — the only way to get
        100.0 is via the ``match DrcStatus.PASS`` arm.  This is a
        guard against re-introducing the false-PASS bug.
        """
        from temper_placer.regression import measure_closure

        src = Path(measure_closure.__file__).read_text()
        assert "drc_clearance_pass_pct = 100.0" not in src, (
            "The pre-U1 false-PASS bug has been re-introduced: "
            "drc_clearance_pass_pct is hard-coded to 100.0. The 3-state "
            "DrcStatus match statement is the only path that should "
            "produce 100.0, and only for a measured PASS."
        )


# ===========================================================================
# U2: Fence posture contract (R2) + crash-only FenceState (R3)
# ===========================================================================


class TestFencePostureEnum:
    """The posture enum has three orthogonal roles."""

    def test_three_members(self) -> None:
        members = {m.name for m in FencePosture}
        assert members == {"REPORT", "FENCE", "GATE"}

    def test_default_is_gate(self) -> None:
        """``run_drc`` defaults to GATE so a forgotten keyword fails
        the merge rather than silently skipping.  Explicit > implicit
        at the gate.
        """
        from temper_placer.validation import drc_runner

        sig = drc_runner.run_drc.__kwdefaults__
        assert sig is not None
        assert sig.get("posture") is FencePosture.GATE


class TestRunDrcPostureBehavior:
    """Posture controls how ``run_drc`` handles a missing kicad-cli."""

    @patch(
        "temper_placer.validation.drc_runner.is_kicad_cli_available",
        return_value=False,
    )
    def test_gate_posture_raises(self, mock_avail: MagicMock, tmp_path: Path) -> None:
        """POSTURE=GATE on missing tool: raises DrcRunnerError.  No
        DrcResult is produced — the gate fails loudly.
        """
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        with pytest.raises(DrcRunnerError) as exc_info:
            run_drc(pcb, posture=FencePosture.GATE)
        assert "kicad-cli" in str(exc_info.value).lower()
        assert "POSTURE=GATE" in str(exc_info.value)

    @patch(
        "temper_placer.validation.drc_runner.is_kicad_cli_available",
        return_value=False,
    )
    def test_fence_posture_returns_unverified(
        self, mock_avail: MagicMock, tmp_path: Path
    ) -> None:
        """POSTURE=FENCE on missing tool: returns DrcResult(UNVERIFIED),
        logs WARNING, does not raise.
        """
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        result = run_drc(pcb, posture=FencePosture.FENCE)
        assert result.drc_status == DrcStatus.UNVERIFIED
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.errors == []
        assert result.warnings == []

    @patch(
        "temper_placer.validation.drc_runner.is_kicad_cli_available",
        return_value=False,
    )
    def test_report_posture_returns_unverified(
        self, mock_avail: MagicMock, tmp_path: Path
    ) -> None:
        """POSTURE=REPORT on missing tool: returns DrcResult(UNVERIFIED),
        logs INFO, does not raise.
        """
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        result = run_drc(pcb, posture=FencePosture.REPORT)
        assert result.drc_status == DrcStatus.UNVERIFIED
        assert result.error_count == 0

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_gate_with_violations_returns_fail_not_raise(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """POSTURE=GATE with kicad-cli present and a dirty board:
        returns DrcResult(FAIL) — POSTURE_GATE only controls missing
        tool behavior, not the FAIL path.  A measured FAIL is a
        legitimate result, not a gate error.
        """
        from temper_placer.validation import drc_runner

        pcb = tmp_path / "dirty.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps(
                {
                    "violations": [
                        {
                            "type": "clearance",
                            "severity": "error",
                            "description": "Clearance violation",
                            "pos": {"x": 0.0, "y": 0.0},
                            "items": [],
                        }
                    ],
                }
            )
        )
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = run_drc(pcb, posture=FencePosture.GATE)

        assert result.drc_status == DrcStatus.FAIL
        assert result.error_count == 1

    def test_posture_must_be_keyword(self, tmp_path: Path) -> None:
        """Posture is keyword-only — positional posture would be
        ambiguous with the pcb_path ordering and the lint test would
        miss it.  ``run_drc(pcb, FencePosture.GATE)`` is a TypeError.
        """
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        with pytest.raises(TypeError):
            run_drc(pcb, FencePosture.GATE)  # type: ignore[misc]


class TestFenceStateCrashOnly:
    """``FenceState.check`` is one mtime comparison + one schema check.

    The crash-only property: ``Fenced`` iff ``mtime(artifact) >
    mtime(router_output)`` AND ``schema_version == "drcc.v1"``.
    Anything else is ``NOT_FENCED`` — there is no middle state.
    """

    def _write_artifact(self, path: Path, mtime: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": DRCC_V1, "drc_status": "PASS"})
        )
        import os

        os.utime(path, (mtime, mtime))

    def _write_router(self, path: Path, mtime: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("(kicad_pcb)")
        import os

        os.utime(path, (mtime, mtime))

    def test_fresh_artifact_and_valid_schema_yields_fenced(
        self, tmp_path: Path
    ) -> None:
        """The happy path: artifact is newer than router, schema
        version matches.  Fence is ``FENCED``.
        """
        artifact = tmp_path / "drcc.v1.json"
        router = tmp_path / "temper.kicad_pcb"
        self._write_router(router, mtime=100.0)
        self._write_artifact(artifact, mtime=200.0)
        assert FenceState.check(artifact, router) is FenceState.FENCED

    def test_stale_artifact_yields_not_fenced(self, tmp_path: Path) -> None:
        """Artifact is older than router: the board moved and we did
        not re-measure.  Fence is ``NOT_FENCED``.
        """
        artifact = tmp_path / "drcc.v1.json"
        router = tmp_path / "temper.kicad_pcb"
        self._write_router(router, mtime=200.0)
        self._write_artifact(artifact, mtime=100.0)
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED

    def test_equal_mtime_yields_not_fenced(self, tmp_path: Path) -> None:
        """Equal mtime is treated as stale (not strictly greater) —
        the ``>`` check is deliberate, equality is not fresh.
        """
        artifact = tmp_path / "drcc.v1.json"
        router = tmp_path / "temper.kicad_pcb"
        self._write_router(router, mtime=100.0)
        self._write_artifact(artifact, mtime=100.0)
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED

    def test_missing_artifact_yields_not_fenced(self, tmp_path: Path) -> None:
        artifact = tmp_path / "missing_drcc.json"
        router = tmp_path / "temper.kicad_pcb"
        self._write_router(router, mtime=100.0)
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED

    def test_missing_router_yields_not_fenced(self, tmp_path: Path) -> None:
        artifact = tmp_path / "drcc.v1.json"
        router = tmp_path / "missing.kicad_pcb"
        self._write_artifact(artifact, mtime=200.0)
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED

    def test_wrong_schema_version_yields_not_fenced(self, tmp_path: Path) -> None:
        """The schema-validity check is the second half of crash-only:
        a fresh artifact with the wrong schema version is still
        ``NOT_FENCED`` — the gate cannot trust it.
        """
        artifact = tmp_path / "drcc.v1.json"
        router = tmp_path / "temper.kicad_pcb"
        self._write_router(router, mtime=100.0)
        self._write_artifact(artifact, mtime=200.0)
        # Overwrite the schema_version
        import os

        artifact.write_text(
            json.dumps({"schema_version": "drc.v1", "drc_status": "PASS"})
        )
        os.utime(artifact, (200.0, 200.0))
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED

    def test_corrupt_artifact_yields_not_fenced(self, tmp_path: Path) -> None:
        """A corrupt JSON file (e.g., disk-full truncated write) is
        treated as ``NOT_FENCED`` — the fence fails loudly rather
        than raising during the check, so the gate's error handler
        runs once.
        """
        artifact = tmp_path / "drcc.v1.json"
        router = tmp_path / "temper.kicad_pcb"
        self._write_router(router, mtime=100.0)
        artifact.write_text("{not json")
        import os

        os.utime(artifact, (200.0, 200.0))
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED

    def test_non_dict_artifact_yields_not_fenced(self, tmp_path: Path) -> None:
        """A valid JSON file that is not a dict (e.g., a list) is
        treated as ``NOT_FENCED`` — the schema check requires a
        dict-shaped artifact.
        """
        artifact = tmp_path / "drcc.v1.json"
        router = tmp_path / "temper.kicad_pcb"
        self._write_router(router, mtime=100.0)
        artifact.write_text(json.dumps([1, 2, 3]))
        import os

        os.utime(artifact, (200.0, 200.0))
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED

    def test_there_is_no_third_state(self) -> None:
        """Crash-only: FenceState has exactly two members.  Adding a
        third (e.g., ``STALE``) would re-introduce the mid-state
        problem.
        """
        members = {m.name for m in FenceState}
        assert members == {"FENCED", "NOT_FENCED"}


class TestRunDrcCallSitesHavePosture:
    """Static lint: every production call to ``run_drc`` carries a posture.

    This test walks the source tree, finds every ``run_drc(...)`` call
    in production code (under ``src/temper_placer/``), and asserts
    that each call site has a ``posture=`` keyword.  A new call site
    without a posture fails the test — and the build.

    Test files (``tests/``) and the function definition itself
    (``drc_runner.py``) are excluded.
    """

    # Production directories where kicad-cli is invoked as a real
    # measurement.  The ``validation`` directory is the runner
    # itself, so it is excluded — the function is defined there and
    # does not need a posture keyword for its own definition.
    _PROD_DIRS = [
        Path("packages/temper-placer/src/temper_placer/regression"),
    ]

    # The two patterns we look for: bare ``run_drc(...)`` (after
    # ``from ... import run_drc``) and qualified
    # ``drc_runner.run_drc(...)``.  ``validator.run_drc(...)`` etc.
    # are different functions (instance methods on
    # ``KiCadDRCValidator``) and are not in scope of the posture
    # contract.
    @staticmethod
    def _is_run_drc_call(node: ast.Call) -> bool:
        if isinstance(node.func, ast.Name) and node.func.id == "run_drc":
            return True
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "run_drc"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "drc_runner"
        ):
            return True
        return False

    @staticmethod
    def _has_posture_keyword(node: ast.Call) -> bool:
        return any(kw.arg == "posture" for kw in node.keywords)

    def test_every_production_run_drc_call_has_posture(self) -> None:
        """Find every ``run_drc(...)`` call in production and assert
        each carries a ``posture=`` keyword.  No exceptions.
        """
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        violations: list[str] = []
        for prod_dir in self._PROD_DIRS:
            for py_file in (repo_root / prod_dir).rglob("*.py"):
                try:
                    tree = ast.parse(py_file.read_text())
                except SyntaxError:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and self._is_run_drc_call(node):
                        if not self._has_posture_keyword(node):
                            violations.append(
                                f"{py_file.relative_to(repo_root)}:"
                                f"{node.lineno}: run_drc() call missing "
                                f"posture= keyword"
                            )
        assert not violations, (
            "run_drc() call sites must declare a FencePosture "
            "(GATE / FENCE / REPORT). The posture contract is a "
            "build-time lint — every call site must make its role "
            "explicit. Violations:\n  "
            + "\n  ".join(violations)
        )

    def test_drc_runner_module_defines_posture(self) -> None:
        """The posture enum must be exported from the runner module
        so call sites can ``from ... import FencePosture``.
        """
        from temper_placer.validation import drc_runner

        assert hasattr(drc_runner, "FencePosture")
        assert FencePosture.GATE in drc_runner.FencePosture


# ===========================================================================
# U3: drcc.v1.json schema (R4)
# ===========================================================================


class TestDrccV1SchemaVersion:
    """The schema version is the contract; ``drcc.v1`` is the
    wrapper's namespace, distinct from kicad-cli's ``drc.v1``.
    """

    def test_version_constant(self) -> None:
        """The exported constant must be ``drcc.v1`` (with two c's
        in the wrapper name — KiCad uses ``drc.v1``).
        """
        assert DRCC_V1_SCHEMA_VERSION == "drcc.v1"

    def test_fence_state_uses_same_constant(self) -> None:
        """The fence's schema-version check must use the same
        constant as the schema serializer — a typo here would
        silently make every artifact fail the FenceState check.
        """
        assert DRCC_V1 == DRCC_V1_SCHEMA_VERSION


class TestToDrccV1RequiredFields:
    """The schema must always include all required fields."""

    def _clean_result(self) -> DrcResult:
        return DrcResult(
            error_count=0,
            warning_count=0,
            drc_status=DrcStatus.PASS,
        )

    def test_all_required_fields_present(self) -> None:
        d = to_drcc_v1(
            result=self._clean_result(),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
            provenance={
                "board_hash": "abc",
                "router_commit": "def",
                "kicad_cli_version": "9.0.7",
                "design_rule_set_hash": EMPTY_SHA256,
            },
        )
        for required in (
            "schema_version",
            "fence_state",
            "drc_status",
            "posture",
            "board_hash",
            "router_commit",
            "kicad_cli_version",
            "design_rule_set_hash",
            "summary",
            "violations",
            "cache_hit",
        ):
            assert required in d, f"missing required field: {required!r}"

    def test_schema_version_is_drcc_v1(self) -> None:
        d = to_drcc_v1(
            result=self._clean_result(),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        assert d["schema_version"] == "drcc.v1"

    def test_default_provenance_keys_present(self) -> None:
        """When provenance is missing, the keys must still be present
        (empty strings), not absent.  Cache invalidation depends on
        key presence, not just values.
        """
        d = to_drcc_v1(
            result=self._clean_result(),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        for key in (
            "board_hash",
            "router_commit",
            "kicad_cli_version",
            "design_rule_set_hash",
        ):
            assert key in d
            assert d[key] == ""

    def test_status_values_are_stringly_distinct(self) -> None:
        """The schema serializes the enums by ``.value``, so the
        wire format is the same as the enum's value (PASS/FAIL/
        UNVERIFIED for status, FENCED/NOT_FENCED for fence_state,
        REPORT/FENCE/GATE for posture).
        """
        for status in DrcStatus:
            d = to_drcc_v1(
                result=DrcResult(error_count=0, warning_count=0, drc_status=status),
                fence_state=FenceState.FENCED,
                posture=FencePosture.GATE,
            )
            assert d["drc_status"] == status.value

        for state in FenceState:
            d = to_drcc_v1(
                result=self._clean_result(),
                fence_state=state,
                posture=FencePosture.GATE,
            )
            assert d["fence_state"] == state.value

        for posture in FencePosture:
            d = to_drcc_v1(
                result=self._clean_result(),
                fence_state=FenceState.FENCED,
                posture=posture,
            )
            assert d["posture"] == posture.value


class TestToDrccV1Summary:
    """The summary block: error/warning counts + drc_clearance_pass_pct."""

    def test_pass_yields_100(self) -> None:
        d = to_drcc_v1(
            result=DrcResult(error_count=0, warning_count=0, drc_status=DrcStatus.PASS),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        assert d["summary"]["error_count"] == 0
        assert d["summary"]["warning_count"] == 0
        assert d["summary"]["drc_clearance_pass_pct"] == 100.0

    def test_fail_yields_penalty(self) -> None:
        d = to_drcc_v1(
            result=DrcResult(error_count=3, warning_count=0, drc_status=DrcStatus.FAIL),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        assert d["summary"]["error_count"] == 3
        assert d["summary"]["drc_clearance_pass_pct"] == 70.0

    def test_unverified_yields_null_pct(self) -> None:
        """The schema's UNVERIFIED summary emits ``None`` for the
        percentage — consistent with the U1 false-PASS fix in
        ``measure_closure``.  A missing measurement is a hole, not
        a 100%.
        """
        d = to_drcc_v1(
            result=DrcResult(
                error_count=0, warning_count=0, drc_status=DrcStatus.UNVERIFIED
            ),
            fence_state=FenceState.NOT_FENCED,
            posture=FencePosture.FENCE,
        )
        assert d["summary"]["drc_clearance_pass_pct"] is None
        assert d["drc_status"] == "UNVERIFIED"

    def test_summary_override_is_respected(self) -> None:
        """The caller can override the summary block (e.g., the
        closure report may merge in sm1/sm6 from its own run).  The
        override is taken verbatim.
        """
        override = {"error_count": 5, "warning_count": 2, "drc_clearance_pass_pct": 50.0}
        d = to_drcc_v1(
            result=DrcResult(error_count=0, warning_count=0, drc_status=DrcStatus.PASS),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
            summary=override,
        )
        assert d["summary"] == override


class TestToDrccV1Violations:
    """Violations are serialized as dicts; round-trip preserves them."""

    def test_no_violations_yields_empty_list(self) -> None:
        d = to_drcc_v1(
            result=DrcResult(error_count=0, warning_count=0, drc_status=DrcStatus.PASS),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        assert d["violations"] == []

    def test_errors_and_warnings_both_serialized(self) -> None:
        result = DrcResult(
            error_count=1,
            warning_count=1,
            errors=[
                DrcError(
                    rule="clearance",
                    severity="error",
                    location=(10.0, 20.0),
                    message="Clearance violation",
                    components=["U1", "U2"],
                )
            ],
            warnings=[
                DrcWarning(
                    rule="silk_over_pads",
                    severity="warning",
                    location=(5.0, 6.0),
                    message="Silkscreen over pad",
                    components=["R1"],
                )
            ],
            drc_status=DrcStatus.FAIL,
        )
        d = to_drcc_v1(
            result=result,
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        assert len(d["violations"]) == 2
        clearance = next(v for v in d["violations"] if v["type"] == "clearance")
        assert clearance["severity"] == "error"
        assert clearance["message"] == "Clearance violation"
        assert clearance["location"] == [10.0, 20.0]
        assert clearance["components"] == ["U1", "U2"]


class TestToDrccV1CacheHit:
    """The ``cache_hit`` flag distinguishes fresh measurements from
    cached ones.  Downstream consumers may want to log cache hits.
    """

    def test_default_cache_hit_is_false(self) -> None:
        d = to_drcc_v1(
            result=DrcResult(error_count=0, warning_count=0, drc_status=DrcStatus.PASS),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        assert d["cache_hit"] is False

    def test_cache_hit_propagates(self) -> None:
        d = to_drcc_v1(
            result=DrcResult(error_count=0, warning_count=0, drc_status=DrcStatus.PASS),
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
            cache_hit=True,
        )
        assert d["cache_hit"] is True


class TestFromDrccV1:
    """The inverse parser must reject unsupported schema versions."""

    def test_rejects_wrong_schema_version(self) -> None:
        with pytest.raises(ValueError, match="unsupported schema_version"):
            from_drcc_v1(
                {
                    "schema_version": "drc.v1",
                    "drc_status": "PASS",
                    "fence_state": "fenced",
                    "posture": "GATE",
                    "violations": [],
                }
            )

    def test_rejects_missing_required_field(self) -> None:
        with pytest.raises(ValueError, match="missing required field"):
            from_drcc_v1(
                {
                    "schema_version": "drcc.v1",
                    "drc_status": "PASS",
                    "fence_state": "fenced",
                    # posture missing
                    "violations": [],
                }
            )

    def test_rejects_unknown_status_value(self) -> None:
        with pytest.raises(ValueError):
            from_drcc_v1(
                {
                    "schema_version": "drcc.v1",
                    "drc_status": "MAYBE",
                    "fence_state": "fenced",
                    "posture": "GATE",
                    "violations": [],
                }
            )


class TestSchemaRoundTrip:
    """to_drcc_v1 -> json.dumps -> json.loads -> from_drcc_v1 must
    produce a DrcResult equivalent to the input.  This is the
    load-bearing test: the schema is the contract surface, and a
    round-trip mismatch is a contract bug.
    """

    def test_clean_result_round_trips(self) -> None:
        original = DrcResult(
            error_count=0, warning_count=0, drc_status=DrcStatus.PASS
        )
        d = to_drcc_v1(
            result=original,
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        parsed, fence_state, posture = from_drcc_v1(json.loads(json.dumps(d)))
        assert parsed.drc_status == DrcStatus.PASS
        assert parsed.error_count == 0
        assert parsed.warning_count == 0
        assert fence_state is FenceState.FENCED
        assert posture is FencePosture.GATE

    def test_unverified_round_trips(self) -> None:
        """A result with no measurement is honest: it serializes,
        deserializes, and reads as UNVERIFIED.  The schema does not
        pretend UNVERIFIED is a 100% pass.
        """
        original = DrcResult(
            error_count=0,
            warning_count=0,
            drc_status=DrcStatus.UNVERIFIED,
        )
        d = to_drcc_v1(
            result=original,
            fence_state=FenceState.NOT_FENCED,
            posture=FencePosture.FENCE,
        )
        assert d["violations"] == []
        assert d["summary"]["drc_clearance_pass_pct"] is None
        parsed, fence_state, posture = from_drcc_v1(json.loads(json.dumps(d)))
        assert parsed.drc_status == DrcStatus.UNVERIFIED
        assert fence_state is FenceState.NOT_FENCED
        assert posture is FencePosture.FENCE

    def test_dirty_result_round_trips(self) -> None:
        original = DrcResult(
            error_count=2,
            warning_count=1,
            errors=[
                DrcError(
                    rule="clearance",
                    severity="error",
                    location=(10.0, 20.0),
                    message="Clearance violation",
                    components=["U1", "U2"],
                ),
                DrcError(
                    rule="courtyard_overlap",
                    severity="error",
                    location=(50.0, 60.0),
                    message="Courtyard overlap",
                    components=["R1", "C1"],
                ),
            ],
            warnings=[
                DrcWarning(
                    rule="silk_over_pads",
                    severity="warning",
                    location=(5.0, 6.0),
                    message="Silkscreen over pad",
                    components=["R1"],
                )
            ],
            drc_status=DrcStatus.FAIL,
        )
        d = to_drcc_v1(
            result=original,
            fence_state=FenceState.FENCED,
            posture=FencePosture.GATE,
        )
        parsed, _, _ = from_drcc_v1(json.loads(json.dumps(d)))
        assert parsed.drc_status == DrcStatus.FAIL
        assert parsed.error_count == 2
        assert parsed.warning_count == 1
        assert parsed.errors[0].rule == "clearance"
        assert parsed.errors[0].location == (10.0, 20.0)
        assert parsed.warnings[0].rule == "silk_over_pads"


class TestProvenanceHelpers:
    """The provenance helpers compute the cache-key inputs."""

    def test_board_hash_is_sha256(self, tmp_path: Path) -> None:
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        h = compute_board_hash(pcb)
        import hashlib

        assert h == hashlib.sha256(b"(kicad_pcb)").hexdigest()
        assert len(h) == 64

    def test_design_rule_set_hash_for_missing_dru(self, tmp_path: Path) -> None:
        """No companion ``.kicad_dru`` → ``EMPTY_SHA256``."""
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        assert compute_design_rule_set_hash(pcb) == EMPTY_SHA256

    def test_design_rule_set_hash_for_existing_dru(self, tmp_path: Path) -> None:
        pcb = tmp_path / "board.kicad_pcb"
        dru = tmp_path / "board.kicad_dru"
        pcb.write_text("(kicad_pcb)")
        dru.write_text("(kicad_dru contents)")
        import hashlib

        assert compute_design_rule_set_hash(pcb) == hashlib.sha256(
            b"(kicad_dru contents)"
        ).hexdigest()

    def test_kicad_cli_version_present(self) -> None:
        """When kicad-cli is installed, the helper returns a non-empty
        string.  When missing, empty string.  Either way, no exception.
        """
        v = compute_kicad_cli_version()
        import shutil

        if shutil.which("kicad-cli"):
            assert v
        else:
            assert v == ""

    def test_compute_provenance_has_all_keys(self, tmp_path: Path) -> None:
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        prov = compute_provenance(pcb)
        assert "board_hash" in prov
        assert "router_commit" in prov
        assert "kicad_cli_version" in prov
        assert "design_rule_set_hash" in prov
        # board_hash is computed from the file content; the others may
        # be empty if git / kicad-cli is unavailable in the test env.
        assert prov["board_hash"] != ""


class TestFenceStateReadsSchemaVersion:
    """The fence and the schema must agree on the version constant.

    A typo in either place would silently make every artifact fail
    the FenceState check.  This test is a guard against that drift.
    """

    def test_fence_state_uses_drcc_v1(self, tmp_path: Path) -> None:
        """An artifact with ``schema_version='drcc.v1'`` and a fresh
        mtime is FENCED.  An artifact with any other version is
        NOT_FENCED.  The fence does not silently accept other
        versions.
        """
        router = tmp_path / "temper.kicad_pcb"
        router.write_text("(kicad_pcb)")
        import os

        os.utime(router, (100.0, 100.0))

        artifact = tmp_path / "drcc.v1.json"
        artifact.write_text(json.dumps({"schema_version": "drcc.v1"}))
        os.utime(artifact, (200.0, 200.0))
        assert FenceState.check(artifact, router) is FenceState.FENCED

        artifact.write_text(json.dumps({"schema_version": "drc.v1"}))
        os.utime(artifact, (200.0, 200.0))
        assert FenceState.check(artifact, router) is FenceState.NOT_FENCED


# ===========================================================================
# U4: hash-keyed DRC regression cache (R5)
# ===========================================================================


class TestCacheKey:
    """``make_cache_key`` is a pure function of the input tuple."""

    def test_key_is_deterministic(self) -> None:
        a = make_cache_key(
            router_commit="abc",
            board_hash="def",
            kicad_cli_version="9.0.7",
            design_rule_set_hash="ghi",
            posture=FencePosture.GATE,
        )
        b = make_cache_key(
            router_commit="abc",
            board_hash="def",
            kicad_cli_version="9.0.7",
            design_rule_set_hash="ghi",
            posture=FencePosture.GATE,
        )
        assert a == b

    def test_key_is_sha256(self) -> None:
        k = make_cache_key(
            router_commit="abc",
            board_hash="def",
            kicad_cli_version="9.0.7",
            design_rule_set_hash="ghi",
            posture=FencePosture.GATE,
        )
        assert len(k) == 64
        import hashlib

        payload = "abc|def|9.0.7|ghi|GATE"
        assert k == hashlib.sha256(payload.encode()).hexdigest()

    def test_posture_is_part_of_key(self) -> None:
        """GATE / FENCE / REPORT are different roles; same board on
        different postures must not share a cache entry.
        """
        base = dict(
            router_commit="abc",
            board_hash="def",
            kicad_cli_version="9.0.7",
            design_rule_set_hash="ghi",
        )
        gate = make_cache_key(posture=FencePosture.GATE, **base)
        fence = make_cache_key(posture=FencePosture.FENCE, **base)
        report = make_cache_key(posture=FencePosture.REPORT, **base)
        assert len({gate, fence, report}) == 3

    def test_each_input_changes_key(self) -> None:
        base = dict(
            router_commit="abc",
            board_hash="def",
            kicad_cli_version="9.0.7",
            design_rule_set_hash="ghi",
            posture=FencePosture.GATE,
        )
        keys = {
            make_cache_key(**base),
            make_cache_key(**{**base, "router_commit": "XYZ"}),
            make_cache_key(**{**base, "board_hash": "XYZ"}),
            make_cache_key(**{**base, "kicad_cli_version": "XYZ"}),
            make_cache_key(**{**base, "design_rule_set_hash": "XYZ"}),
        }
        # 5 distinct keys: 4 single-field perturbations + the base.
        assert len(keys) == 5


class TestDrcResultCacheHit:
    """``DrcResult.cache_hit`` defaults to False; the cache layer sets
    it to True on hits.
    """

    def test_default_is_false(self) -> None:
        r = DrcResult(error_count=0, warning_count=0, drc_status=DrcStatus.PASS)
        assert r.cache_hit is False

    def test_explicit_true(self) -> None:
        r = DrcResult(
            error_count=0, warning_count=0, drc_status=DrcStatus.PASS, cache_hit=True
        )
        assert r.cache_hit is True


class TestDrcCacheGetOrRun:
    """The cache wraps ``run_drc`` with hit/miss/invalidation semantics."""

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_first_run_is_miss_writes_artifact(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """First run with a given input tuple: cache miss, kicad-cli
        runs, the artifact is written, ``cache_hit=False``.
        """
        from temper_placer.validation import drc_runner

        cache_dir = tmp_path / "cache"
        cache = DrcCache(cache_dir=cache_dir)

        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(json.dumps({"violations": []}))
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            result = cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )

        assert result.drc_status == DrcStatus.PASS
        assert result.cache_hit is False
        # Artifact was written to the cache dir
        assert cache_dir.exists()
        written = list(cache_dir.glob("*.json"))
        assert len(written) == 1

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_second_run_is_hit_does_not_invoke_kicad(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Second run with the same input tuple: cache hit,
        kicad-cli does NOT run, ``cache_hit=True``.
        """
        from temper_placer.validation import drc_runner

        cache_dir = tmp_path / "cache"
        cache = DrcCache(cache_dir=cache_dir)

        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(json.dumps({"violations": []}))
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            first = cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )
            assert first.cache_hit is False
            # Reset the mock to detect the second invocation
            mock_run.reset_mock()
            second = cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )
            assert second.cache_hit is True
            # kicad-cli was NOT invoked on the second run
            mock_run.assert_not_called()

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_kicad_cli_version_change_invalidates_cache(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A kicad-cli version bump must invalidate the cache: the
        second run is a miss, kicad-cli runs again.
        """
        from temper_placer.validation import drc_runner

        cache = DrcCache(cache_dir=tmp_path / "cache")
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        # Each run_drc invocation deletes the JSON output file in
        # its ``finally`` block.  Recreate the file before each
        # call so the second ``run_drc`` finds the file present.
        def _reset_mocks(report_path: Path) -> None:
            report_path.write_text(json.dumps({"violations": []}))
            mock_run.reset_mock()
            mock_run.return_value = MagicMock(returncode=0)
            ctx = MagicMock()
            ctx.name = str(report_path)
            ctx.__enter__.return_value = ctx
            mock_temp_file.return_value = ctx

        report = tmp_path / "report.json"

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            _reset_mocks(report)
            cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )
            _reset_mocks(report)
            cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.8",  # version bump
                design_rule_set_hash="r1",
            )
            mock_run.assert_called()

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_board_hash_change_invalidates_cache(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A board content change must invalidate the cache."""
        from temper_placer.validation import drc_runner

        cache = DrcCache(cache_dir=tmp_path / "cache")
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        def _reset_mocks(report_path: Path) -> None:
            report_path.write_text(json.dumps({"violations": []}))
            mock_run.reset_mock()
            mock_run.return_value = MagicMock(returncode=0)
            ctx = MagicMock()
            ctx.name = str(report_path)
            ctx.__enter__.return_value = ctx
            mock_temp_file.return_value = ctx

        report = tmp_path / "report.json"

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            _reset_mocks(report)
            cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )
            _reset_mocks(report)
            cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b2",  # board change
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )
            mock_run.assert_called()

    def test_unverified_is_never_cached(self, tmp_path: Path) -> None:
        """UNVERIFIED is never written to the cache: caching "we
        don't know" is a memory leak.  The next run with the same
        inputs is a miss, not a hit on a stale "we don't know".
        """
        cache = DrcCache(cache_dir=tmp_path / "cache")
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available",
            return_value=False,
        ):
            first = cache.get_or_run(
                pcb,
                posture=FencePosture.FENCE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="",
                design_rule_set_hash="",
            )
            assert first.drc_status == DrcStatus.UNVERIFIED
            assert first.cache_hit is False
            # Nothing was written to cache
            assert list((tmp_path / "cache").glob("*.json")) == []

    def test_missing_cache_dir_is_non_fatal(self, tmp_path: Path) -> None:
        """A nonexistent cache directory is created on first write
        and a missing dir on read is treated as a miss.  The cache
        is best-effort — a transient filesystem error is not a
        fence failure.
        """
        cache_dir = tmp_path / "does_not_exist_yet" / "drc"
        assert not cache_dir.exists()
        cache = DrcCache(cache_dir=cache_dir)
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available",
            return_value=False,
        ):
            # Missing kicad-cli + FENCE: returns UNVERIFIED, no
            # cache write (UNVERIFIED never cached).
            result = cache.get_or_run(
                pcb,
                posture=FencePosture.FENCE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="",
                design_rule_set_hash="",
            )
            assert result.drc_status == DrcStatus.UNVERIFIED
        # No cache directory was created (UNVERIFIED never writes)
        assert not cache_dir.exists()

    def test_corrupt_cache_entry_triggers_fresh_run(
        self, tmp_path: Path
    ) -> None:
        """A corrupt cache file (e.g., truncated write) is detected,
        deleted, and the next call runs kicad-cli.  A bad cache is
        a recoverable failure, not a permanent one.
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cache = DrcCache(cache_dir=cache_dir)
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        # Plant a corrupt cache entry under the expected key.
        from temper_placer.validation.drc_cache import make_cache_key

        key = make_cache_key(
            router_commit="abc",
            board_hash="b1",
            kicad_cli_version="9.0.7",
            design_rule_set_hash="r1",
            posture=FencePosture.FENCE,
        )
        corrupt = cache_dir / f"{key}.json"
        corrupt.write_text("{not json")

        # POSTURE=FENCE + missing kicad-cli: cache hit attempt sees
        # the corrupt file, deletes it, falls through to a fresh
        # run_drc which returns UNVERIFIED (FENCE doesn't raise).
        with patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available",
            return_value=False,
        ):
            result = cache.get_or_run(
                pcb,
                posture=FencePosture.FENCE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )
            # UNVERIFIED never cached, so no second write either.
            assert result.drc_status == DrcStatus.UNVERIFIED
            assert result.cache_hit is False

        # The corrupt file was deleted by the cache's recovery path.
        assert not corrupt.exists()

    def test_clear_removes_all_entries(self, tmp_path: Path) -> None:
        """``clear()`` removes every ``*.json`` entry and returns
        the count.  Used by tests and by future rule-set-change
        invalidation.
        """
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # Plant 3 entries
        for i in range(3):
            (cache_dir / f"key{i}.json").write_text("{}")
        assert len(list(cache_dir.glob("*.json"))) == 3
        cache = DrcCache(cache_dir=cache_dir)
        n = cache.clear()
        assert n == 3
        assert list(cache_dir.glob("*.json")) == []

    def test_clear_on_missing_dir_returns_zero(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "nonexistent"
        cache = DrcCache(cache_dir=cache_dir)
        assert cache.clear() == 0


class TestDrcCachePostureContract:
    """``get_or_run`` must accept a posture; GATE raises on missing tool."""

    def test_gate_posture_propagates_missing_tool_error(self, tmp_path: Path) -> None:
        """POSTURE=GATE on missing kicad-cli raises DrcRunnerError
        through the cache layer — the cache is transparent to
        posture semantics.
        """
        from temper_placer.validation.drc_runner import DrcRunnerError

        cache = DrcCache(cache_dir=tmp_path / "cache")
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available",
            return_value=False,
        ):
            with pytest.raises(DrcRunnerError):
                cache.get_or_run(
                    pcb,
                    posture=FencePosture.GATE,
                    router_commit="abc",
                    board_hash="b1",
                )

    def test_fence_posture_returns_unverified(self, tmp_path: Path) -> None:
        cache = DrcCache(cache_dir=tmp_path / "cache")
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available",
            return_value=False,
        ):
            result = cache.get_or_run(
                pcb,
                posture=FencePosture.FENCE,
                router_commit="abc",
                board_hash="b1",
            )
            assert result.drc_status == DrcStatus.UNVERIFIED
            assert result.cache_hit is False


class TestDrcCacheIntegrationWithSchema:
    """The cache artifact is a ``drcc.v1.json`` file consumable by
    ``FenceState.check`` — the cache and the fence state must agree
    on the file format.
    """

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_written_artifact_is_drcc_v1(
        self,
        mock_run: MagicMock,
        mock_temp_file: MagicMock,
        tmp_path: Path,
    ) -> None:
        from temper_placer.validation import drc_runner

        cache = DrcCache(cache_dir=tmp_path / "cache")
        pcb = tmp_path / "board.kicad_pcb"
        pcb.write_text("(kicad_pcb)")
        report = tmp_path / "report.json"
        report.write_text(json.dumps({"violations": []}))
        mock_run.return_value = MagicMock(returncode=0)
        ctx = MagicMock()
        ctx.name = str(report)
        ctx.__enter__.return_value = ctx
        mock_temp_file.return_value = ctx

        with patch.object(drc_runner, "is_kicad_cli_available", return_value=True):
            cache.get_or_run(
                pcb,
                posture=FencePosture.GATE,
                router_commit="abc",
                board_hash="b1",
                kicad_cli_version="9.0.7",
                design_rule_set_hash="r1",
            )

        written = list((tmp_path / "cache").glob("*.json"))
        assert len(written) == 1
        data = json.loads(written[0].read_text())
        assert data["schema_version"] == "drcc.v1"
        assert data["drc_status"] == "PASS"
        assert data["posture"] == "GATE"
        # The artifact is parseable by the fence state module
        import os

        os.utime(written[0], (200.0, 200.0))
        os.utime(pcb, (100.0, 100.0))
        assert FenceState.check(written[0], pcb) is FenceState.FENCED
