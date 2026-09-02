"""Focused proof for the sealed U8 fixture runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_isolation_joint_qualification as runner  # noqa: E402


FIXTURES = Path(__file__).parents[1] / "fixtures" / "isolation_joint_qualification"
U9_ROOT = Path(__file__).resolve().parents[4] / "power_pcb_dataset/qualification/isolation_joint"


def test_fixture_composition_is_complete_and_deterministic() -> None:
    first = runner.compose_fixture(FIXTURES)
    second = runner.compose_fixture(FIXTURES)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["schema_version"] == 1
    assert len(first["combined_rows"]) == 8
    # External certification authorities are receipt signers, not combined
    # owner dispositions; the shared matrix therefore has 7 ISO + 6 CT07 rows.
    assert len(first["signoffs"]) == 13
    assert len(first["shutdown"]["direct_captures"]) == 8


def test_missing_fixture_fails_closed(tmp_path: Path) -> None:
    for path in FIXTURES.iterdir():
        target = tmp_path / path.name
        target.write_bytes(path.read_bytes())
    (tmp_path / "ct07_receipt.json").unlink()
    with pytest.raises(runner.JointReplayError):
        runner.compose_fixture(tmp_path, root=tmp_path)


def test_runner_does_not_implement_policy() -> None:
    source = Path(runner.__file__).read_text(encoding="utf-8")
    assert "5000" not in source
    assert "eligible-for-refloorplan" not in source


def test_u9_current_real_inputs_stop_without_partial_aggregate() -> None:
    package = runner.compose_u9()
    result = runner.evaluate_u9(package)

    assert result["verdict"] == "stopped-indeterminate"
    assert result["domain_results"] == {
        "iso": "rejected",
        "ct07": "stopped-indeterminate",
    }
    assert result["partial_result"] is None
    for aggregate_field in ("decomposed_total_ns", "direct_total_ns", "timing_pass"):
        assert aggregate_field not in result
    assert "iso.u7_approval_missing" in result["reasons"]
    assert "ct07.u8_handoff_missing" in result["reasons"]
    assert "combined.candidate_not_materialized" in result["reasons"]
    assert "evidence.direct_captures_missing" in result["reasons"]
    assert "signoffs.combined_matrix_missing" in result["reasons"]


def test_u9_missing_iso_approval_cannot_be_overridden_by_ct07_status() -> None:
    package = runner.compose_u9()
    package["inputs"]["ct07"]["status"] = "construction-envelope-approved"
    package["inputs"]["ct07"]["handoff_path"] = "power_pcb_dataset/qualification/ct07_t2/joint_handoff.json"
    result = runner.evaluate_u9(package)

    assert result["verdict"] == "stopped-indeterminate"
    assert "iso.u7_approval_missing" in result["reasons"]
    assert result["partial_result"] is None


def test_u9_missing_evidence_stops_even_if_domain_statuses_are_present() -> None:
    package = runner.compose_u9()
    package["inputs"]["iso"]["status"] = "construction-envelope-approved"
    package["inputs"]["iso"]["handoff_path"] = "power_pcb_dataset/qualification/isolation_joint/iso_handoff.json"
    package["inputs"]["ct07"]["status"] = "construction-envelope-approved"
    package["inputs"]["ct07"]["handoff_path"] = "power_pcb_dataset/qualification/ct07_t2/joint_handoff.json"
    package["combined_candidate"]["status"] = "materialized"
    package["evidence"]["status"] = "complete"
    package["signoffs"] = ["synthetic-signoff"]
    result = runner.evaluate_u9(package)

    assert result["verdict"] == "stopped-indeterminate"
    assert result["partial_result"] is None
    assert "inputs.iso_handoff_unavailable" in result["reasons"]
    assert "inputs.ct07_handoff_unavailable" in result["reasons"]
    assert "evidence.direct_captures_missing" in result["reasons"]


def test_u9_replay_matches_committed_blocked_decision() -> None:
    committed = json.loads(
        (U9_ROOT / "decision.json").read_text(encoding="utf-8")
    )
    assert runner.replay_u9() == committed
