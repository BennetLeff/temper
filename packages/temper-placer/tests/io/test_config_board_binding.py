"""Tests for config-to-board binding verification (plan 2026-07-15-001, U2).

These use synthetic netlists and config dicts, not the repo's real configs.
The real configs are authored against the 33-component fixture and are not
migrated by this unit; they will fail the gate only once applied to the real
board (unit U4 wiring).
"""

import pytest

from temper_placer.core.netlist import Component, Netlist
from temper_placer.io.config_board_binding import (
    ConfigBoardMismatchError,
    extract_config_refs,
    verify_config_matches_netlist,
)


def _component(ref: str) -> Component:
    return Component(ref=ref, footprint="R_0603", bounds=(1.6, 0.8), pins=[])


def _netlist(refs: list[str]) -> Netlist:
    return Netlist(components=[_component(r) for r in refs], nets=[])


# --- extract_config_refs ---------------------------------------------------


def test_extract_refs_from_list_keys():
    config = {
        "fixed_components": ["U1", "U2"],
        "component_groups": [{"components": ["Q1", "Q2"]}],
    }
    assert extract_config_refs(config) == {"U1", "U2", "Q1", "Q2"}


def test_extract_refs_from_single_ref_keys():
    config = {
        "hv_safety": [
            {"signal_component": "U_GATE", "target_component": "Q1", "hv_component": "Q1"},
        ],
        "routing_aware": [{"from_component": "U_GATE", "to_component": "R_GATE_H"}],
        "thermal": [{"component_ref": "Q2"}],
    }
    assert extract_config_refs(config) == {"U_GATE", "Q1", "R_GATE_H", "Q2"}


def test_extract_refs_from_fixed_components_mapping():
    # fixed_components may be a ref -> placement mapping instead of a list.
    config = {"fixed_components": {"U1": {"x": 1.0, "y": 2.0}, "C5": {"x": 3.0}}}
    assert extract_config_refs(config) == {"U1", "C5"}


def test_extract_refs_ignores_unknown_structure():
    config = {"board": {"width": 100, "height": 80}, "loss_weights": {"overlap": 1.0}}
    assert extract_config_refs(config) == set()


def test_extract_refs_deeply_nested():
    config = {"a": {"b": {"c": [{"components": ["U9"]}]}}}
    assert extract_config_refs(config) == {"U9"}


# --- verify_config_matches_netlist -----------------------------------------


def test_config_refs_subset_of_netlist_passes():
    netlist = _netlist(["U1", "U2", "Q1", "Q2", "C1"])
    config_refs = {"U1", "Q1"}
    # Should not raise.
    verify_config_matches_netlist(
        config_refs, {c.ref for c in netlist.components}, config_name="ok.yaml"
    )


def test_fixture_refs_rejected_against_production_netlist():
    # Fixture config names U_GATE/C_BUS1; production netlist has U1..U100.
    production_refs = {f"U{i}" for i in range(1, 101)}
    config_refs = {"U_GATE", "C_BUS1", "Q1"}
    with pytest.raises(ConfigBoardMismatchError) as exc:
        verify_config_matches_netlist(
            config_refs, production_refs, config_name="temper_deterministic_config.yaml"
        )
    assert exc.value.config_name == "temper_deterministic_config.yaml"
    assert exc.value.missing_refs == ["C_BUS1", "Q1", "U_GATE"]
    assert "not present in the board netlist" in str(exc.value)


def test_empty_config_refs_always_passes():
    verify_config_matches_netlist(set(), {"U1"}, config_name="empty.yaml")


def test_partial_overlap_reports_only_missing():
    netlist_refs = {"U1", "U2"}
    config_refs = {"U1", "U3", "U4"}
    with pytest.raises(ConfigBoardMismatchError) as exc:
        verify_config_matches_netlist(config_refs, netlist_refs, config_name="partial.yaml")
    assert exc.value.missing_refs == ["U3", "U4"]


def test_error_message_truncates_large_missing_sets():
    netlist_refs: set[str] = set()
    config_refs = {f"R{i}" for i in range(25)}
    with pytest.raises(ConfigBoardMismatchError) as exc:
        verify_config_matches_netlist(config_refs, netlist_refs, config_name="big.yaml")
    assert len(exc.value.missing_refs) == 25
    assert "+15 more" in str(exc.value)


# --- integration: extract + verify -----------------------------------------


def test_extract_then_verify_fixture_config_against_production_board():
    fixture_config = {
        "component_groups": [{"components": ["Q1", "Q2"]}],
        "hv_safety": [{"signal_component": "U_GATE", "hv_component": "Q1"}],
    }
    production_netlist = _netlist([f"U{i}" for i in range(1, 101)])
    refs = extract_config_refs(fixture_config)
    with pytest.raises(ConfigBoardMismatchError):
        verify_config_matches_netlist(
            refs,
            {c.ref for c in production_netlist.components},
            config_name="fixture.yaml",
        )


def test_extract_then_verify_matching_config_passes():
    config = {"fixed_components": ["U1", "U2"], "component_groups": [{"components": ["U3"]}]}
    netlist = _netlist(["U1", "U2", "U3", "U4"])
    refs = extract_config_refs(config)
    verify_config_matches_netlist(
        refs, {c.ref for c in netlist.components}, config_name="match.yaml"
    )
