"""Proof for the CT07 U7-A identity/source eligibility checkpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_ct07_u7_a_identity as gate  # noqa: E402


def _copy_inputs(tmp_path: Path) -> Path:
    source = tmp_path / gate.SOURCE_PATH
    source.parent.mkdir(parents=True)
    source.write_bytes(
        (Path(__file__).resolve().parents[4] / gate.SOURCE_PATH).read_bytes()
    )
    package = tmp_path / "identity_eligibility.json"
    package.write_bytes(
        (
            Path(__file__).resolve().parents[4]
            / "power_pcb_dataset/qualification/ct07_t2/identity_eligibility.json"
        ).read_bytes()
    )
    return package


def _install_pending_oracle(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeOracle:
        @staticmethod
        def evaluate_ct07_u7_a_identity_json(value: str) -> str:
            package = json.loads(value)
            return json.dumps(
                {
                    "schema_version": package["schema_version"],
                    "candidate_id": package["candidate_id"],
                    "identity_digest": package["identity_digest"],
                    "status": "stopped-indeterminate",
                    "construction_release_eligible": False,
                    "reasons": ["identity.lifecycle"],
                }
            )

    monkeypatch.setattr(gate, "temper_quality_oracle", FakeOracle)


def test_u7_a_replays_current_candidate_as_stopped_without_fabrication_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _copy_inputs(tmp_path)
    _install_pending_oracle(monkeypatch)

    result = json.loads(gate.replay(package, repo_root=tmp_path))

    assert result["status"] == "stopped-indeterminate"
    assert result["construction_release_eligible"] is False


def test_u7_a_rejects_a_changed_u4_b_source_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _copy_inputs(tmp_path)
    _install_pending_oracle(monkeypatch)
    source = tmp_path / gate.SOURCE_PATH
    source_payload = json.loads(source.read_text(encoding="utf-8"))
    source_payload["status"] = "changed"
    source.write_text(json.dumps(source_payload), encoding="utf-8")

    with pytest.raises(gate.U7AIdentityGateError, match="source digest"):
        gate.replay(package, repo_root=tmp_path)


def test_u7_a_requires_the_canonical_candidate_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _copy_inputs(tmp_path)
    payload = json.loads(package.read_text(encoding="utf-8"))
    payload["candidate_source"]["source_path"] = "other/manifest.json"
    package.write_text(json.dumps(payload), encoding="utf-8")
    _install_pending_oracle(monkeypatch)

    with pytest.raises(gate.U7AIdentityGateError, match="canonical U4-B"):
        gate.replay(package, repo_root=tmp_path)
