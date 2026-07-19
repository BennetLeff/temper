"""Fail-closed provenance checks for APC1 all-pad baseline evidence."""

from __future__ import annotations

from copy import deepcopy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from temper_placer.router_v6.all_pad_evidence import (
    AllPadEvidenceError,
    validate_all_pad_baseline,
)


def _board(*, unconnected: int) -> dict:
    return {
        "measurement_status": "VIOLATIONS" if unconnected else "CLEAN",
        "source_board": {"path": "pcb/example.kicad_pcb", "sha256": "a" * 64},
        "routed_output_sha256": "b" * 64,
        "drc_report_sha256": "c" * 64,
        "command": ["kicad-cli", "pcb", "drc", "--format", "json"],
        "kicad_cli_version": "10.0.4",
        "router_invocation": {"seed": 42, "existing_component_positions": True},
        "drc_counts": {"clearance": 2, "unconnected_items": unconnected},
        "unconnected_items": unconnected,
        "unconnected_by_net": {
            "status": "UNAVAILABLE",
            "reason": "KiCad JSON has no structured per-net attribution",
        },
    }


def _valid_record() -> dict:
    return {
        "schema_version": 1,
        "evidence_kind": "APC1_U0_ALL_PAD_ROUTING_BASELINE",
        "generated_at_utc": "2026-07-19T12:00:00Z",
        "source_commit": "d" * 40,
        "boards": {
            "corpus": _board(unconnected=0),
            "production": _board(unconnected=149),
        },
    }


def test_baseline_requires_measured_hashed_kicad_output_and_ratchet() -> None:
    validate_all_pad_baseline(_valid_record())

    invalid = deepcopy(_valid_record())
    invalid["boards"]["corpus"]["measurement_status"] = "UNMEASURED"
    with pytest.raises(AllPadEvidenceError, match="UNMEASURED"):
        validate_all_pad_baseline(invalid)

    invalid = deepcopy(_valid_record())
    invalid["boards"]["production"]["unconnected_items"] = 150
    invalid["boards"]["production"]["drc_counts"]["unconnected_items"] = 150
    with pytest.raises(AllPadEvidenceError, match="149"):
        validate_all_pad_baseline(invalid)

    invalid = deepcopy(_valid_record())
    del invalid["boards"]["corpus"]["drc_counts"]["unconnected_items"]
    with pytest.raises(AllPadEvidenceError, match="must include unconnected_items"):
        validate_all_pad_baseline(invalid)


@given(st.recursive(st.none() | st.booleans() | st.integers() | st.text(), lambda x: st.lists(x) | st.dictionaries(st.text(), x), max_leaves=20))
def test_baseline_pbt_rejects_malformed_evidence(payload: object) -> None:
    with pytest.raises(AllPadEvidenceError):
        validate_all_pad_baseline(payload)
