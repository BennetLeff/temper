"""Tests for DRC ratchet."""

import json
from pathlib import Path

import pytest

from temper_placer.regression.drc_ratchet import DrcCeilingEntry, DrcRatchet, DrcRatchetResult


class TestDrcRatchet:
    def test_load_ceiling(self, tmp_path: Path):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(json.dumps({
            "boards": [
                {
                    "board_id": "temper_routed",
                    "path": "pcb/temper_routed.kicad_pcb",
                    "error_ceiling": 3042,
                    "warning_ceiling": 0,
                }
            ]
        }))
        ratchet = DrcRatchet(ceiling_path)
        ratchet.load()
        assert "temper_routed" in ratchet.entries
        entry = ratchet.entries["temper_routed"]
        assert entry.error_ceiling == 3042
        assert entry.warning_ceiling == 0

    def test_check_missing_pcb(self, tmp_path: Path):
        ceiling_path = tmp_path / "drc_ceiling.json"
        ceiling_path.write_text(json.dumps({
            "boards": [
                {
                    "board_id": "missing",
                    "path": "pcb/missing.kicad_pcb",
                    "error_ceiling": 10,
                    "warning_ceiling": 0,
                }
            ]
        }))
        ratchet = DrcRatchet(ceiling_path)
        ratchet.load()
        results = ratchet.check(tmp_path)
        assert len(results) == 1
        assert not results[0].passed
        assert results[0].exit_code == 1

    def test_detect_ceiling_raise_not_approved(self):
        ratchet = DrcRatchet(Path("dummy.json"))

        old = {"boards": [{"board_id": "b1", "error_ceiling": 100, "warning_ceiling": 0}]}
        new = {"boards": [{"board_id": "b1", "error_ceiling": 200, "warning_ceiling": 0}]}

        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: update ceiling")
        assert result is not None
        assert result.exit_code == 2
        assert "requires explicit approval" in result.message

    def test_detect_ceiling_raise_approved(self):
        ratchet = DrcRatchet(Path("dummy.json"))

        old = {"boards": [{"board_id": "b1", "error_ceiling": 100, "warning_ceiling": 0}]}
        new = {"boards": [{"board_id": "b1", "error_ceiling": 200, "warning_ceiling": 0}]}

        result = ratchet.detect_ceiling_raise(
            old, new, commit_message="Ceiling-Approval: reviewer-id\nfix: update ceiling"
        )
        assert result is None

    def test_detect_no_raise(self):
        ratchet = DrcRatchet(Path("dummy.json"))

        old = {"boards": [{"board_id": "b1", "error_ceiling": 100, "warning_ceiling": 0}]}
        new = {"boards": [{"board_id": "b1", "error_ceiling": 50, "warning_ceiling": 0}]}

        result = ratchet.detect_ceiling_raise(old, new, commit_message="fix: lowered ceiling")
        assert result is None


class TestDrcRatchetResult:
    def test_pass_result(self):
        result = DrcRatchetResult(passed=True, board_id="b1", message="ok")
        assert result.passed
        assert result.exit_code == 0

    def test_fail_result(self):
        result = DrcRatchetResult(
            passed=False, board_id="b1", message="ceiling exceeded", exit_code=1
        )
        assert not result.passed
        assert result.exit_code == 1

    def test_ceiling_raise_result(self):
        result = DrcRatchetResult(
            passed=False, board_id="b1", message="requires approval", exit_code=2
        )
        assert result.exit_code == 2
