"""Proof-first tests for the CT07 U8 producer boundary."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_ct07_u8_handoff as runner  # noqa: E402


def _stopped_package() -> dict[str, object]:
    return {
        "schema_version": 1,
        "construction_id": "ct07-test-construction",
        "construction_digest": "pending-u6-freeze",
        "internal_decision_digest": "a" * 64,
        "internal_stage": "stopped-indeterminate",
        "internal_reasons": ["u7-a.pending", "u5.evidence"],
        "construction_projection_digest": "b" * 64,
        "allowed_transform_policy_digest": "c" * 64,
        "joint_contract_digest": "d" * 64,
        "ocp02_status": "DNF",
        "preliminary": None,
    }


def _install_oracle(monkeypatch: pytest.MonkeyPatch, output: dict[str, object]) -> None:
    class FakeOracle:
        @staticmethod
        def evaluate_ct07_u8_handoff_json(value: str) -> str:
            package = json.loads(value)
            result = dict(output)
            result.setdefault("schema_version", package["schema_version"])
            return json.dumps(result)

    monkeypatch.setitem(sys.modules, "temper_quality_oracle", FakeOracle)


def test_pending_internal_state_is_stopped_and_never_publishes_handoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _stopped_package()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(package), encoding="utf-8")
    _install_oracle(
        monkeypatch,
        {
            "stage": "stopped-indeterminate",
            "reasons": package["internal_reasons"],
            "handoff": None,
        },
    )

    result = runner.replay(input_path, repo_root=tmp_path)

    assert result["stage"] == "stopped-indeterminate"
    assert result["handoff"] is None
    assert not (tmp_path / "joint_handoff.json").exists()


def test_runner_rejects_favorable_result_without_handoff(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    package = _stopped_package()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(package), encoding="utf-8")
    _install_oracle(
        monkeypatch,
        {"stage": "construction-envelope-approved", "handoff": None},
    )

    with pytest.raises(runner.Ct07U8ReplayError, match="favorable CT07 U8 result"):
        runner.replay(input_path, repo_root=tmp_path)


def test_runner_rejects_handoff_with_joint_aggregate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    package = _stopped_package()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(package), encoding="utf-8")
    _install_oracle(
        monkeypatch,
        {
            "stage": "construction-envelope-approved",
            "handoff": {"joint_total_ns": 4000},
        },
    )

    with pytest.raises(runner.Ct07U8ReplayError, match="aggregate"):
        runner.replay(input_path, repo_root=tmp_path)


def test_fixture_mode_cannot_publish_decision_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = _stopped_package()
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(package), encoding="utf-8")
    output_root = tmp_path / runner.OUTPUT_ROOT
    output_root.mkdir(parents=True)
    target = output_root / "protected.json"
    target.write_text("protected", encoding="utf-8")
    output = output_root / "decision.json"
    output.symlink_to(target)
    _install_oracle(
        monkeypatch,
        {
            "stage": "stopped-indeterminate",
            "handoff": None,
        },
    )

    with pytest.raises(runner.Ct07U8ReplayError, match="fixture mode cannot publish"):
        runner.replay(input_path, output, repo_root=tmp_path)
    assert target.read_text(encoding="utf-8") == "protected"


def test_compose_input_reads_evidence_but_does_not_send_legacy_metadata(
    tmp_path: Path,
) -> None:
    source_root = runner.REPO_ROOT
    relative_inputs = (
        runner.OUTPUT_ROOT / "construction_manifest.json",
        runner.OUTPUT_ROOT / "construction_projection.json",
        runner.OUTPUT_ROOT / "evidence_index.json",
        runner.OUTPUT_ROOT / "authority/preliminary_ruling.json",
        runner.CONTRACT,
    )
    for relative in relative_inputs:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, destination)

    package = runner.compose_input(root=tmp_path)

    assert "source_evidence_digest" not in package
    assert "source_status" not in package
    (tmp_path / runner.OUTPUT_ROOT / "evidence_index.json").unlink()
    with pytest.raises(runner.Ct07U8ReplayError, match="evidence_index"):
        runner.compose_input(root=tmp_path)
