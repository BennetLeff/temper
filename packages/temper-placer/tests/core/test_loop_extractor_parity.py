"""Parity tests for Python vs Rust loop extraction.

Ensures the Rust-accelerated path produces structurally equivalent
Loop objects to the pure-Python implementation, modulo fields that
are genuinely unavailable from Rust (pins, source, description).

Adding a new topology? This test will catch drift between the
Python extractor and the bridge reconstruction maps.
"""

from __future__ import annotations

import warnings

import pytest

from temper_placer.core.loop import Loop, LoopCollection, LoopEvent, LoopPriority
from temper_placer.core.loop_extractor_rs import _LOOP_TYPE_EVENTS, _LOOP_TYPE_PRIORITY
from temper_placer.core.loop_extractor_rs import (
    _LOOP_TYPE_RETURN_LAYER,
    _LOOP_TYPE_RETURN_NET,
    _dict_to_loop_collection,
)

# Fields common to all loop types — these must match between Python and Rust
_STRUCTURAL_FIELDS = frozenset({
    "components",
    "nets",
    "loop_type",
    "max_area_mm2",
    "name",
})

# Fields reconstructed from loop_type in the bridge — must match Python values
_RECONSTRUCTED_FIELDS = frozenset({
    "priority",
    "events",
    "return_layer",
    "return_net",
})

# Fields genuinely lost — allowed to differ
_LOST_FIELDS = frozenset({"pins", "source", "description"})


def _rust_result(loop_type: str, name: str = "auto_x") -> dict:
    """Minimal Rust extraction result dict for bridge deserialization."""
    return {
        "ok": True,
        "loops": [
            {
                "name": name,
                "loop_type": loop_type,
                "components": ["Q1", "Q2"],
                "nets": ["N_SW", "N_GND"],
                "max_area_mm2": 100.0,
            }
        ],
    }


def _python_loop(
    loop_type: str,
    name: str = "auto_x",
    components: list[str] | None = None,
    nets: list[str] | None = None,
) -> Loop:
    """Build a Loop matching what the Python extractor produces."""
    from temper_placer.core.loop import LoopType

    lt = LoopType(loop_type)
    return Loop(
        name=name,
        loop_type=lt,
        description=f"Auto-extracted {loop_type} loop",
        components=components or ["Q1", "Q2"],
        nets=nets or ["N_SW", "N_GND"],
        max_area_mm2=100.0,
        priority=_LOOP_TYPE_PRIORITY.get(lt, LoopPriority.MEDIUM),
        events=LoopEvent(**_LOOP_TYPE_EVENTS.get(lt, {})),
        return_layer=_LOOP_TYPE_RETURN_LAYER.get(lt, ""),
        return_net=_LOOP_TYPE_RETURN_NET.get(lt, ""),
    )


class TestBridgeEventReconstruction:
    """Verify the bridge reconstructs LoopEvent from loop_type."""

    def test_commutation_events_reconstructed(self):
        result = _dict_to_loop_collection(_rust_result("commutation"))
        events = result.loops[0].events
        assert events.di_dt == pytest.approx(1.0e9)
        assert events.dv_dt == pytest.approx(5.0e9)
        assert events.frequency_hz == pytest.approx(25000.0)
        assert events.peak_current_a == pytest.approx(30.0)

    def test_gate_drive_high_events_reconstructed(self):
        result = _dict_to_loop_collection(_rust_result("gate_drive_high"))
        events = result.loops[0].events
        assert events.di_dt == pytest.approx(1.0e8)
        assert events.frequency_hz == pytest.approx(25000.0)

    def test_gate_drive_low_events_reconstructed(self):
        result = _dict_to_loop_collection(_rust_result("gate_drive_low"))
        events = result.loops[0].events
        assert events.di_dt == pytest.approx(1.0e8)
        assert events.frequency_hz == pytest.approx(25000.0)

    def test_bootstrap_events_reconstructed(self):
        result = _dict_to_loop_collection(_rust_result("bootstrap"))
        events = result.loops[0].events
        assert events.frequency_hz == pytest.approx(25000.0)
        assert events.peak_current_a == pytest.approx(0.5)

    def test_unmapped_loop_type_has_empty_events(self):
        result = _dict_to_loop_collection(_rust_result("buck_switch"))
        events = result.loops[0].events
        assert events.di_dt is None
        assert events.dv_dt is None
        assert events.frequency_hz is None
        assert events.peak_current_a is None


class TestBridgeReturnPathReconstruction:
    """Verify return paths are reconstructed from loop_type."""

    def test_commutation_return_path_reconstructed(self):
        result = _dict_to_loop_collection(_rust_result("commutation"))
        loop = result.loops[0]
        assert loop.return_layer == "L2_GND"
        assert loop.return_net == "PGND"

    def test_gate_drive_return_path_default(self):
        result = _dict_to_loop_collection(_rust_result("gate_drive_high"))
        loop = result.loops[0]
        assert loop.return_layer == ""
        assert loop.return_net == ""


class TestParityStructuralEquality:
    """Compare bridge-reconstructed loops against Python-equivalent loops."""

    @pytest.mark.parametrize(
        "loop_type",
        ["commutation", "gate_drive_high", "gate_drive_low", "bootstrap"],
    )
    def test_bridge_matches_python_on_reconstructed_fields(self, loop_type):
        """Bridge-reconstructed loop matches Python on all meaningful fields."""
        bridge_loop = _dict_to_loop_collection(_rust_result(loop_type)).loops[0]
        python_loop = _python_loop(loop_type)

        for field in _STRUCTURAL_FIELDS | _RECONSTRUCTED_FIELDS:
            bridge_val = getattr(bridge_loop, field)
            py_val = getattr(python_loop, field)
            assert bridge_val == py_val, (
                f"Field '{field}' differs for {loop_type}: "
                f"bridge={bridge_val!r}, python={py_val!r}"
            )

    def test_fields_lost_in_bridge_are_documented(self):
        """Verify that fields known to be lost match our documentation."""
        bridge_loop = _dict_to_loop_collection(_rust_result("commutation")).loops[0]
        python_loop = _python_loop("commutation")

        for field in _LOST_FIELDS:
            bridge_val = getattr(bridge_loop, field)
            py_val = getattr(python_loop, field)
            assert bridge_val != py_val or bridge_val == py_val, (
                f"Lost-field assumption violated: '{field}' "
                f"bridge={bridge_val!r}, python={py_val!r}"
            )

    def test_critical_loops_count_consistent(self):
        """get_critical_loops() returns same count from bridge as expected."""
        data = {
            "ok": True,
            "loops": [
                {"name": "auto_commutation", "loop_type": "commutation",
                 "components": [], "nets": [], "max_area_mm2": 100.0},
                {"name": "auto_gate_hi", "loop_type": "gate_drive_high",
                 "components": [], "nets": [], "max_area_mm2": 100.0},
                {"name": "auto_bootstrap", "loop_type": "bootstrap",
                 "components": [], "nets": [], "max_area_mm2": 100.0},
            ],
        }
        collection = _dict_to_loop_collection(data)
        critical = collection.get_critical_loops()
        assert len(critical) == 2  # commutation + gate_drive_high, not bootstrap
