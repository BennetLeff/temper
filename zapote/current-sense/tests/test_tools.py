"""Focused fail-closed tests for the standalone current-sense adapters."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from native_report import load_kicad_report, require_success  # noqa: E402


def _load_tool(name: str):
    path = TOOLS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_native = _load_tool("build_current_sense_native.py")
native_checks = _load_tool("run_current_sense_native_checks.py")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_erc_report_requires_kicad_schema_and_sheet_violations(tmp_path: Path) -> None:
    report = tmp_path / "erc.json"
    _write_json(report, {"sheets": []})
    with pytest.raises(ValueError, match="unexpected \\$schema"):
        load_kicad_report(report, "erc")

    _write_json(
        report,
        {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "sheets": [{"path": "/root", "violations": {}}],
        },
    )
    with pytest.raises(ValueError, match="violations list"):
        load_kicad_report(report, "erc")


def test_drc_report_requires_all_finding_lists(tmp_path: Path) -> None:
    report = tmp_path / "drc.json"
    _write_json(
        report,
        {
            "$schema": "https://schemas.kicad.org/drc.v1.json",
            "violations": [],
            "unconnected_items": [],
        },
    )
    with pytest.raises(ValueError, match="schematic_parity list"):
        load_kicad_report(report, "drc")


def test_missing_report_and_nonzero_command_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="produced no erc report"):
        load_kicad_report(tmp_path / "missing.json", "erc")
    with pytest.raises(RuntimeError, match="returncode=7"):
        require_success("ERC", 7, "stdout", "stderr")


def test_native_check_runner_records_then_rejects_nonzero_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailedProcess:
        returncode = 9
        stdout = "tool output"
        stderr = "tool failure"

    monkeypatch.setattr(native_checks.subprocess, "run", lambda *args, **kwargs: FailedProcess())
    output = tmp_path / "reports"
    output.mkdir()
    with pytest.raises(RuntimeError, match="returncode=9"):
        native_checks._run(["kicad-cli", "sch", "erc"], output / "erc.json", output, {})
    command_receipt = json.loads((output / "erc-command.json").read_text(encoding="utf-8"))
    assert command_receipt["returncode"] == 9


def test_source_hash_map_is_required_and_contained(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "source-build"
    source.mkdir(parents=True)
    source_file = source / "elec" / "src" / "current_sense_unit.ato"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("component CurrentSenseUnit:\n", encoding="utf-8")
    digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
    export = {"source_sha256": {"elec/src/current_sense_unit.ato": digest}}
    assert build_native._require_source_hashes(repo, source, export)

    with pytest.raises(ValueError, match="nonempty source_sha256"):
        build_native._require_source_hashes(repo, source, {})
    with pytest.raises(ValueError, match="escapes source build"):
        build_native._require_source_hashes(
            repo, source, {"source_sha256": {"../outside": digest}}
        )
    with pytest.raises(ValueError, match="contained under repo"):
        build_native._require_source_hashes(
            repo, tmp_path / "outside", export
        )
