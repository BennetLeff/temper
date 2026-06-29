"""CLI integration tests for pipeline_metrics.py."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Make scripts/ importable from tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Make temper_placer package importable for lazy imports inside cmd_* functions
_repo_root = Path(__file__).resolve().parents[2]
_tp_src = _repo_root / "packages" / "temper-placer" / "src"
if str(_tp_src) not in sys.path:
    sys.path.insert(0, str(_tp_src))

import pipeline_metrics


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_mock_record(board, stage, wall_time_ms, timestamp=None):
    return {
        "board": board,
        "stage": stage,
        "stage_name": stage,
        "metrics": {"wall_time_ms": float(wall_time_ms)},
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }


def _mock_repo_root(tmp_path):
    """Create a temp directory that looks enough like a repo root."""
    (tmp_path / ".git").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# _parse_window
# ---------------------------------------------------------------------------


class TestParseWindow:
    def test_valid_30d(self):
        result = pipeline_metrics._parse_window("30d")
        assert isinstance(result, timedelta)
        assert result.days == 30

    def test_valid_7d(self):
        result = pipeline_metrics._parse_window("7d")
        assert result.days == 7

    def test_invalid_unit_h(self):
        with pytest.raises(SystemExit) as excinfo:
            pipeline_metrics._parse_window("30h")
        assert excinfo.value.code == 2

    def test_invalid_format_abc(self):
        with pytest.raises(ValueError):
            pipeline_metrics._parse_window("abc")


# ---------------------------------------------------------------------------
# trend subcommand
# ---------------------------------------------------------------------------


class TestCmdTrend:
    def test_trend_exit_0_no_regression(self, tmp_path):
        """Stable wall_time_ms within 1-sigma -> no regression -> exit 0."""
        repo = _mock_repo_root(tmp_path)
        # Values with small variance: drift of latest from mean < 1.0 sigma
        records = [
            _make_mock_record("temper", "placement", v)
            for v in [100, 102, 99, 101, 100, 103, 98, 101, 100, 102]
        ]
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_trend(
                    board="temper", stage="placement", window="30d",
                    sigma_multiple=1.0, as_json=False,
                )
        assert exit_code == 0

    def test_trend_exit_1_has_regression(self, tmp_path):
        """Stable values + a big spike at the end -> regression -> exit 1."""
        repo = _mock_repo_root(tmp_path)
        records = [
            _make_mock_record("temper", "placement", v)
            for v in [100, 102, 99, 101, 100, 103, 98, 101, 100]
        ]
        # Add a spike at the end
        records.append(
            _make_mock_record("temper", "placement", 10000)
        )
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_trend(
                    board="temper", stage="placement", window="30d",
                    sigma_multiple=1.0, as_json=False,
                )
        assert exit_code == 1

    def test_trend_exit_2_no_records_match(self, tmp_path):
        """No records matching board/stage -> exit 2."""
        repo = _mock_repo_root(tmp_path)
        records = [
            _make_mock_record("other", "other", 100),
        ]
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_trend(
                    board="temper", stage="placement", window="30d",
                    sigma_multiple=1.0, as_json=False,
                )
        assert exit_code == 2

    def test_trend_json_output(self, tmp_path):
        """--json flag produces valid JSON on stdout."""
        repo = _mock_repo_root(tmp_path)
        records = [
            _make_mock_record("temper", "placement", 100 + i)
            for i in range(10)
        ]
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                with patch("sys.stdout") as mock_stdout:
                    exit_code = pipeline_metrics.cmd_trend(
                        board="temper", stage="placement", window="30d",
                        sigma_multiple=1.0, as_json=True,
                    )


# ---------------------------------------------------------------------------
# spc subcommand
# ---------------------------------------------------------------------------


class TestCmdSpc:
    def _make_spc_records(self, board, stage, values):
        """Records where the last value is a massive spike."""
        records = []
        now = datetime.now(timezone.utc)
        for i, v in enumerate(values):
            ts = (now - timedelta(days=len(values) - i)).isoformat()
            records.append(_make_mock_record(board, stage, v, timestamp=ts))
        return records

    def test_spc_silent_no_violation_exit_0(self, tmp_path):
        """Silent (no state file) + stable data -> exit 0."""
        repo = _mock_repo_root(tmp_path)
        values = [100 + i for i in range(30)]  # stable
        records = self._make_spc_records("temper", "placement", values)
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_spc(
                    board="temper", stage="placement", window=20,
                    as_json=False, summary=False,
                )
        assert exit_code == 0

    def test_spc_silent_with_violation_exit_0(self, tmp_path):
        """Silent (no state file) + SPC violation -> still exit 0 (not activated)."""
        repo = _mock_repo_root(tmp_path)
        # Stable values then a 3-sigma spike at the end
        values = [100] * 28 + [10000]
        records = self._make_spc_records("temper", "placement", values)
        # Ensure no observability_state.json exists
        metrics_dir = repo / "power_pcb_dataset" / "metrics"
        state_path = metrics_dir / "observability_state.json"
        assert not state_path.exists()
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_spc(
                    board="temper", stage=None, window=20,
                    as_json=False, summary=False,
                )
        assert exit_code == 0

    def test_spc_activated_violation_exit_1(self, tmp_path):
        """Activated + SPC violation -> exit 1."""
        repo = _mock_repo_root(tmp_path)
        # Create observability_state.json with activated=true
        metrics_dir = repo / "power_pcb_dataset" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "observability_state.json").write_text(
            json.dumps({"activated": True})
        )
        values = [100] * 28 + [10000]
        records = self._make_spc_records("temper", "placement", values)
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_spc(
                    board="temper", stage=None, window=20,
                    as_json=False, summary=False,
                )
        assert exit_code == 1

    def test_spc_activated_no_violation_exit_0(self, tmp_path):
        """Activated but no SPC violation -> exit 0."""
        repo = _mock_repo_root(tmp_path)
        metrics_dir = repo / "power_pcb_dataset" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "observability_state.json").write_text(
            json.dumps({"activated": True})
        )
        # Stable values with sufficient count for rules to evaluate
        values = [100] * 21
        records = self._make_spc_records("temper", "placement", values)
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_spc(
                    board="temper", stage=None, window=20,
                    as_json=False, summary=False,
                )
        assert exit_code == 0


# ---------------------------------------------------------------------------
# slo subcommand
# ---------------------------------------------------------------------------


class TestCmdSlo:
    def _make_slo_records(self, stage, values):
        records = []
        now = datetime.now(timezone.utc)
        for i, v in enumerate(values):
            ts = (now - timedelta(days=len(values) - i)).isoformat()
            records.append({
                "board": "temper",
                "stage": stage,
                "stage_name": stage,
                "metrics": {"wall_time_ms": float(v)},
                "timestamp": ts,
            })
        return records

    def _write_slo_file(self, tmp_path, content):
        path = tmp_path / "slo.yaml"
        path.write_text(content)
        return str(path)

    def test_slo_block_violation_activated_exit_1(self, tmp_path):
        """SLO block violation + activated=True -> exit 1."""
        repo = _mock_repo_root(tmp_path)
        # Activated
        metrics_dir = repo / "power_pcb_dataset" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "observability_state.json").write_text(
            json.dumps({"activated": True})
        )
        # SLO definition: max wall_time_ms must be <= 1000, block severity
        slo_path = self._write_slo_file(tmp_path, """
slo_version: 1
stages:
  closure:
    - metric: wall_time_ms
      type: max
      threshold: 1000
      window: 5
      severity: block
""")
        # Records where the last few have wall_time > threshold
        records = self._make_slo_records("closure", [100, 200, 300, 400, 1500])
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_slo(
                    slo_file=slo_path, as_json=False,
                )
        assert exit_code == 1

    def test_slo_block_violation_silent_exit_0(self, tmp_path):
        """SLO block violation but not activated -> exit 0."""
        repo = _mock_repo_root(tmp_path)
        # NOT activated (no state file)
        slo_path = self._write_slo_file(tmp_path, """
slo_version: 1
stages:
  closure:
    - metric: wall_time_ms
      type: max
      threshold: 1000
      window: 5
      severity: block
""")
        records = self._make_slo_records("closure", [100, 200, 300, 400, 1500])
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_slo(
                    slo_file=slo_path, as_json=False,
                )
        assert exit_code == 0

    def test_slo_no_violation_exit_0(self, tmp_path):
        """SLO not violated -> exit 0 regardless of activation."""
        repo = _mock_repo_root(tmp_path)
        metrics_dir = repo / "power_pcb_dataset" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "observability_state.json").write_text(
            json.dumps({"activated": True})
        )
        slo_path = self._write_slo_file(tmp_path, """
slo_version: 1
stages:
  closure:
    - metric: wall_time_ms
      type: max
      threshold: 1000
      window: 5
      severity: block
""")
        records = self._make_slo_records("closure", [100, 200, 300, 400, 500])
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_slo(
                    slo_file=slo_path, as_json=False,
                )
        assert exit_code == 0

    def test_slo_warn_violation_exit_0(self, tmp_path):
        """WARN severity violations do NOT trigger exit 1 (only block does)."""
        repo = _mock_repo_root(tmp_path)
        metrics_dir = repo / "power_pcb_dataset" / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "observability_state.json").write_text(
            json.dumps({"activated": True})
        )
        slo_path = self._write_slo_file(tmp_path, """
slo_version: 1
stages:
  closure:
    - metric: wall_time_ms
      type: max
      threshold: 1000
      window: 5
      severity: warn
""")
        records = self._make_slo_records("closure", [100, 200, 300, 400, 1500])
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                exit_code = pipeline_metrics.cmd_slo(
                    slo_file=slo_path, as_json=False,
                )
        assert exit_code == 0


# ---------------------------------------------------------------------------
# --list subcommand (via cmd_list)
# ---------------------------------------------------------------------------


class TestCmdList:
    def test_list_json_output(self, tmp_path):
        repo = _mock_repo_root(tmp_path)
        records = [
            _make_mock_record("temper", "placement", 100),
            _make_mock_record("temper", "routing", 200),
            _make_mock_record("beta", "placement", 150),
        ]
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                with patch("temper_placer.regression.metrics_recorder.find_metrics_file",
                           return_value=Path("/fake.jsonl")):
                    # Capture stdout via a context manager
                    from io import StringIO
                    stdout_capture = StringIO()
                    with patch("sys.stdout", stdout_capture):
                        pipeline_metrics.cmd_list(as_json=True)
                    output = stdout_capture.getvalue()
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        boards = {(r["board"], r["stage"]) for r in parsed}
        assert boards == {("beta", "placement"), ("temper", "placement"), ("temper", "routing")}

    def test_list_text_output(self, tmp_path):
        repo = _mock_repo_root(tmp_path)
        records = [
            _make_mock_record("temper", "placement", 100),
        ]
        with patch("pipeline_metrics._find_repo_root", return_value=repo):
            with patch("temper_placer.regression.metrics_recorder.load_metrics",
                       return_value=records):
                with patch("temper_placer.regression.metrics_recorder.find_metrics_file",
                           return_value=Path("/fake.jsonl")):
                    from io import StringIO
                    stdout_capture = StringIO()
                    with patch("sys.stdout", stdout_capture):
                        pipeline_metrics.cmd_list(as_json=False)
                    output = stdout_capture.getvalue()
        assert "temper / placement" in output
