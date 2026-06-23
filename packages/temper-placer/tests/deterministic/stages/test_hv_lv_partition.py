"""
Unit tests for HvLvPartitionStage (U1: state, config, exception).

Part of feat/hv-lv-guard-strip (plan 2026-06-23-001).
"""

from __future__ import annotations

import pytest

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.hv_lv_partition import (
    HvLvGuardConfig,
    PartitionError,
    load_guard_config,
)


# ---------------------------------------------------------------------------
# BoardState defaults (NFR6)
# ---------------------------------------------------------------------------


def test_board_state_default_component_domain_map_empty():
    state = BoardState()
    assert state.component_domain_map == frozenset()


def test_board_state_default_routing_corridors_empty():
    state = BoardState()
    assert state.routing_corridors == ()


def test_board_state_default_domain_regions_empty():
    state = BoardState()
    assert state.domain_regions == ()


def test_board_state_default_config_none():
    state = BoardState()
    assert state.config is None


# ---------------------------------------------------------------------------
# HvLvGuardConfig pydantic round-trip (FR9)
# ---------------------------------------------------------------------------


def test_hv_lv_guard_config_round_trip_disabled():
    cfg = HvLvGuardConfig(enabled=False, width_mm=None, fallback_to_unconstrained=True)
    assert cfg.enabled is False
    assert cfg.width_mm is None
    assert cfg.fallback_to_unconstrained is True
    assert cfg.model_dump() == {
        "enabled": False,
        "width_mm": None,
        "fallback_to_unconstrained": True,
    }


def test_hv_lv_guard_config_defaults():
    cfg = HvLvGuardConfig()
    assert cfg.enabled is True
    assert cfg.width_mm is None
    assert cfg.fallback_to_unconstrained is True


# ---------------------------------------------------------------------------
# load_guard_config
# ---------------------------------------------------------------------------


def test_load_guard_config_with_block_present():
    cfg = load_guard_config(
        {
            "hv_lv_guard_strip": {
                "enabled": False,
                "width_mm": 8.0,
                "fallback_to_unconstrained": False,
            }
        }
    )
    assert cfg.enabled is False
    assert cfg.width_mm == 8.0
    assert cfg.fallback_to_unconstrained is False


def test_load_guard_config_missing_block_returns_defaults():
    cfg = load_guard_config({"some_other_block": {"foo": 1}})
    assert cfg.enabled is True
    assert cfg.width_mm is None
    assert cfg.fallback_to_unconstrained is True


def test_load_guard_config_none_returns_defaults():
    cfg = load_guard_config(None)
    assert cfg == HvLvGuardConfig()


def test_load_guard_config_empty_dict_returns_defaults():
    cfg = load_guard_config({})
    assert cfg == HvLvGuardConfig()


def test_load_guard_config_invalid_block_logs_and_returns_defaults(caplog):
    with caplog.at_level("WARNING"):
        cfg = load_guard_config({"hv_lv_guard_strip": "not-a-mapping"})
    assert cfg == HvLvGuardConfig()
    assert any("not a mapping" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# PartitionError (FR7)
# ---------------------------------------------------------------------------


def test_partition_error_exposes_structured_fields():
    err = PartitionError("HV", "Q1", 25.0, 80.0)
    assert err.bucket == "HV"
    assert err.largest_ref == "Q1"
    assert err.region_area_mm2 == 25.0
    assert err.required_area_mm2 == 80.0


def test_partition_error_is_exception():
    assert issubclass(PartitionError, Exception)
    with pytest.raises(PartitionError):
        raise PartitionError("LV", "U1", 10.0, 50.0)
