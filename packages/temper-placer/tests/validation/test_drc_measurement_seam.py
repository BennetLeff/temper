"""Focused contracts for the canonical raw kicad-cli measurement seam."""

from __future__ import annotations

import contextlib
import json
import subprocess
from pathlib import Path

import pytest

from temper_placer.validation import _drc_api


def _stage_context(tmp_path: Path, *, footprints: int = 1) -> Path:
    pcb = tmp_path / "board.kicad_pcb"
    blocks = "\n".join(
        f'  (footprint "Test:R" (property "Reference" "R{index}"))' for index in range(footprints)
    )
    pcb.write_text(f"(kicad_pcb\n{blocks}\n)\n", encoding="utf-8")
    pcb.with_suffix(".kicad_pro").write_text("{}\n", encoding="utf-8")
    pcb.with_suffix(".kicad_dru").write_text("(version 1)\n", encoding="utf-8")
    (tmp_path / "libs" / "test.pretty").mkdir(parents=True)
    (tmp_path / "fp-lib-table").write_text(
        '(fp_lib_table (lib (name "test")(type "KiCad")'
        '(uri "${KIPRJMOD}/libs/test.pretty")(options "")(descr "")))\n',
        encoding="utf-8",
    )
    return pcb


def _install_fake_kicad(monkeypatch, report: dict, seen: dict) -> None:
    monkeypatch.setattr(_drc_api, "is_kicad_cli_available", lambda: True)

    @contextlib.contextmanager
    def pinned():
        yield {"KICAD_CONFIG_HOME": "/strict-test-config"}

    monkeypatch.setattr(_drc_api, "_single_threaded_kicad_env", pinned)

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs["env"]
        output = Path(cmd[cmd.index("--output") + 1])
        output.write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(_drc_api.subprocess, "run", fake_run)


def test_strict_measurement_returns_raw_report_and_legacy_result(tmp_path, monkeypatch):
    pcb = _stage_context(tmp_path)
    finding = {
        "type": "silk_overlap",
        "severity": "warning",
        "description": "Silkscreen overlap",
        "items": [
            {
                "description": "Segment of R1 on F.Silkscreen",
                "pos": {"x": 1.0, "y": 2.0},
            }
        ],
    }
    report = {"violations": [finding], "included_severities": ["error", "warning"]}
    seen: dict = {}
    _install_fake_kicad(monkeypatch, report, seen)

    measurement = _drc_api.run_drc_measurement(pcb, strict=True)

    assert measurement.raw_report == report
    assert measurement.result.warning_count == 1
    assert measurement.raw_findings == [finding]
    assert measurement.thread_pinned is True
    assert "--all-track-errors" in seen["cmd"]
    assert seen["env"] == {"KICAD_CONFIG_HOME": "/strict-test-config"}


def test_run_drc_remains_a_parsed_result_wrapper(tmp_path, monkeypatch):
    pcb = _stage_context(tmp_path)
    seen: dict = {}
    _install_fake_kicad(monkeypatch, {"violations": []}, seen)

    result = _drc_api.run_drc(pcb)

    assert isinstance(result, _drc_api.DrcResult)
    assert result.error_count == 0


def test_strict_mode_rejects_ambient_thread_fallback_before_launch(tmp_path, monkeypatch):
    pcb = _stage_context(tmp_path)
    monkeypatch.setattr(_drc_api, "is_kicad_cli_available", lambda: True)

    @contextlib.contextmanager
    def unpinned():
        yield None

    monkeypatch.setattr(_drc_api, "_single_threaded_kicad_env", unpinned)
    monkeypatch.setattr(
        _drc_api.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("strict fallback must fail before kicad-cli"),
    )

    with pytest.raises(_drc_api.DrcRunnerError, match="single-thread"):
        _drc_api.run_drc_measurement(pcb, strict=True)


@pytest.mark.parametrize("missing", ["board.kicad_dru", "fp-lib-table", "libs/test.pretty"])
def test_strict_mode_rejects_incomplete_project_context(tmp_path, monkeypatch, missing):
    pcb = _stage_context(tmp_path)
    target = tmp_path / missing
    if target.is_dir():
        target.rmdir()
    else:
        target.unlink()
    monkeypatch.setattr(_drc_api, "is_kicad_cli_available", lambda: True)
    monkeypatch.setattr(
        _drc_api.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("context guard must fail before kicad-cli"),
    )

    with pytest.raises(_drc_api.DrcProjectContextError):
        _drc_api.run_drc_measurement(pcb, strict=True)


def test_strict_mode_rejects_dynamic_footprint_resolution_failure(tmp_path, monkeypatch):
    pcb = _stage_context(tmp_path, footprints=2)
    report = {
        "violations": [
            {
                "type": "lib_footprint_issues",
                "severity": "warning",
                "description": f"Footprint issue {index}",
                "items": [
                    {
                        "description": f"Footprint R{index}",
                        "pos": {"x": float(index), "y": 0.0},
                    }
                ],
            }
            for index in range(2)
        ],
    }
    _install_fake_kicad(monkeypatch, report, {})

    with pytest.raises(_drc_api.DrcProjectContextError, match="footprint resolution"):
        _drc_api.run_drc_measurement(pcb, strict=True)


def test_resolution_signature_requires_zero_mismatches(tmp_path, monkeypatch):
    pcb = _stage_context(tmp_path, footprints=1)
    report = {
        "violations": [
            {
                "type": category,
                "severity": "warning",
                "description": category,
                "items": [
                    {
                        "description": "Footprint R1",
                        "pos": {"x": 1.0, "y": 0.0},
                    }
                ],
            }
            for category in ("lib_footprint_issues", "lib_footprint_mismatch")
        ]
    }
    _install_fake_kicad(monkeypatch, report, {})

    measurement = _drc_api.run_drc_measurement(pcb, strict=True)

    assert measurement.result.warning_count == 2
