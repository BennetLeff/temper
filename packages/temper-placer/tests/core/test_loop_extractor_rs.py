"""Tests for the Rust loop-extractor wrapper's priority mapping.

Regression coverage for #227: _dict_to_loop_collection hardcoded
priority=0 (a raw int, not a LoopPriority enum member) for every
loop regardless of loop_type, so get_critical_loops() always returned
empty -- extraction worked, classification silently didn't.
"""

from __future__ import annotations

from temper_placer.core.loop import LoopPriority
from temper_placer.core.loop_extractor_rs import _dict_to_loop_collection


def _rust_result(loop_type: str, name: str = "auto_x") -> dict:
    return {
        "ok": True,
        "loops": [
            {
                "name": name,
                "loop_type": loop_type,
                "components": ["Q1"],
                "nets": ["N1"],
                "max_area_mm2": 100.0,
            }
        ],
    }


class TestDictToLoopCollectionPriority:
    def test_commutation_loop_is_critical(self):
        collection = _dict_to_loop_collection(_rust_result("commutation"))
        assert collection.loops[0].priority == LoopPriority.CRITICAL
        assert isinstance(collection.loops[0].priority, LoopPriority)

    def test_gate_drive_high_loop_is_critical(self):
        collection = _dict_to_loop_collection(_rust_result("gate_drive_high"))
        assert collection.loops[0].priority == LoopPriority.CRITICAL

    def test_gate_drive_low_loop_is_critical(self):
        collection = _dict_to_loop_collection(_rust_result("gate_drive_low"))
        assert collection.loops[0].priority == LoopPriority.CRITICAL

    def test_bootstrap_loop_is_high(self):
        collection = _dict_to_loop_collection(_rust_result("bootstrap"))
        assert collection.loops[0].priority == LoopPriority.HIGH

    def test_unmapped_loop_type_defaults_to_medium(self):
        collection = _dict_to_loop_collection(_rust_result("buck_switch"))
        assert collection.loops[0].priority == LoopPriority.MEDIUM

    def test_get_critical_loops_finds_rust_extracted_critical_loops(self):
        """End-to-end: get_critical_loops() must actually see these as critical,
        not just have the right enum value in isolation."""
        data = {
            "ok": True,
            "loops": [
                {"name": "auto_commutation", "loop_type": "commutation", "components": [], "nets": []},
                {"name": "auto_gate_drive_hi", "loop_type": "gate_drive_high", "components": [], "nets": []},
                {"name": "auto_gate_drive_lo", "loop_type": "gate_drive_low", "components": [], "nets": []},
                {"name": "auto_bootstrap", "loop_type": "bootstrap", "components": [], "nets": []},
            ],
        }
        collection = _dict_to_loop_collection(data)
        assert len(collection.get_critical_loops()) == 3
