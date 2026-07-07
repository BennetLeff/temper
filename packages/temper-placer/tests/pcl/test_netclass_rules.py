"""Tests for temper_placer.core.netclass_rules."""

from pathlib import Path

import pytest

from temper_placer.core.netclass_rules import (
    get_pair_because,
    get_pair_clearance,
    load_netclass_rules,
    resolve_net_class,
)

YAML_PATH = (
    Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"
)


@pytest.fixture(scope="module")
def rules():
    """Load netclass_rules.yaml once per test module."""
    return load_netclass_rules(YAML_PATH)


# -------------------------------------------------------------------
# get_pair_clearance
# -------------------------------------------------------------------


def test_get_pair_clearance_explicit_pair(rules):
    """HighVoltage↔Signal returns 6.0mm from YAML explicit pair."""
    assert get_pair_clearance("HighVoltage", "Signal", rules=rules) == 6.0


def test_get_pair_clearance_same_class(rules):
    """Signal↔Signal returns 0.15mm (self-clearance from net class definition)."""
    assert get_pair_clearance("Signal", "Signal", rules=rules) == 0.15


def test_get_pair_clearance_routine_pair(rules):
    """Power↔Signal returns 0.25mm = max(0.25, 0.15) since no explicit pair exists."""
    assert get_pair_clearance("Power", "Signal", rules=rules) == 0.25


def test_get_pair_clearance_unlisted_pair(rules):
    """Unlisted pair falls back to default_clearance_mm."""
    assert get_pair_clearance("BogusClass", "AlsoBogus", rules=rules) == 0.2


def test_get_pair_clearance_direction_agnostic(rules):
    """(HV, Signal) and (Signal, HV) return the same value."""
    a = get_pair_clearance("HighVoltage", "Signal", rules=rules)
    b = get_pair_clearance("Signal", "HighVoltage", rules=rules)
    assert a == b


# -------------------------------------------------------------------
# resolve_net_class
# -------------------------------------------------------------------


def test_resolve_net_class_explicit_assignment():
    """"DC_BUS+" returns "HighVoltage" via TEMPER_NET_ASSIGNMENTS."""
    assert resolve_net_class("DC_BUS+") == "HighVoltage"


def test_resolve_net_class_heuristic_fallback():
    """"UNKNOWN_RANDOM" returns "Signal" (catch-all)."""
    assert resolve_net_class("UNKNOWN_RANDOM") == "Signal"


# -------------------------------------------------------------------
# get_pair_because
# -------------------------------------------------------------------


def test_get_pair_because_safety_critical(rules):
    """get_pair_because("ACMains", "Signal") returns non-None string with IEC citation."""
    result = get_pair_because("ACMains", "Signal", rules=rules)
    assert result is not None
    assert "IEC" in result


def test_get_pair_because_routine(rules):
    """get_pair_because("Power", "Signal") returns None."""
    assert get_pair_because("Power", "Signal", rules=rules) is None


# -------------------------------------------------------------------
# load_netclass_rules
# -------------------------------------------------------------------


def test_load_netclass_rules_loads_successfully():
    """load_netclass_rules() returns dict with net_classes, pair_clearances, default_clearance_mm."""
    result = load_netclass_rules(YAML_PATH)
    assert "net_classes" in result
    assert "pair_clearances" in result
    assert "default_clearance_mm" in result
