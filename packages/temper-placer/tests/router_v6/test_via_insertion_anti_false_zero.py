"""U8 anti-false-zero provenance checks for via-aware routed boards."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from temper_placer.router_v6.audit_provenance import (
    MeasurementRecordError,
    validate_via_routing_measurement,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def _valid_record() -> dict:
    return {
        "schema_version": 1,
        "boards": {
            "corpus": {
                "completion_rate": 1.0,
                "baseline_unconnected_items": 0,
                "unconnected_items": 0,
                "contains_vias": True,
                "drc_counts": {"clearance": 1},
                "gates": {"clearance": "VIOLATIONS", "iec_creepage": "CLEAN"},
            },
            "production": {
                "completion_rate": 1.0,
                "baseline_unconnected_items": 149,
                "unconnected_items": 149,
                "contains_vias": True,
                "drc_counts": {"shorting_items": 2},
                "gates": {"clearance": "VIOLATIONS", "iec_creepage": "VIOLATIONS"},
            },
        },
    }


def test_measurement_requires_real_gate_results_and_nonregressing_connectivity() -> None:
    """A record cannot hide worsening DRC connectivity behind completion."""
    validate_via_routing_measurement(_valid_record())

    invalid = _valid_record()
    invalid["boards"]["corpus"]["gates"]["clearance"] = "UNMEASURED"
    with pytest.raises(MeasurementRecordError, match="UNMEASURED"):
        validate_via_routing_measurement(invalid)

    invalid = _valid_record()
    invalid["boards"]["production"]["unconnected_items"] = 150
    with pytest.raises(MeasurementRecordError, match="exceeds"):
        validate_via_routing_measurement(invalid)


@given(
    st.one_of(
        st.none(),
        st.text(),
        st.dictionaries(st.text(), st.integers()),
        st.lists(st.integers()),
    )
)
def test_measurement_record_pbt_rejects_malformed_top_level_payloads(payload: object) -> None:
    """Malformed provenance payloads never become a false clean measurement."""
    with pytest.raises(MeasurementRecordError):
        validate_via_routing_measurement(payload)


def test_committed_u8_measurement_record_is_well_formed() -> None:
    """The audit evidence is a checked artifact, not a prose-only claim."""
    record_path = REPO_ROOT / "docs" / "evidence" / "2026-07-19-via-aware-routing-u8.json"
    assert record_path.exists(), f"Missing U8 measurement record: {record_path}"
    validate_via_routing_measurement(record_path)
