"""Integration proof for the Rust-owned isolation authority boundary."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest

import temper_design_bundle_python as _rust


EXPECTED_PROJECTIONS = {
    (
        "packages/temper-placer/configs/netclass_rules.yaml",
        "classes.HighVoltage.clearance",
    ): 2.0,
    ("elec/src/constraints.ato", "HV_to_LV.min_clearance"): 6.0,
    (
        "packages/temper-placer/configs/netclass_rules.yaml",
        "classes.HighVoltageIsolated.clearance",
    ): 6.0,
}


def _request(rows: dict[tuple[str, str], float] = EXPECTED_PROJECTIONS) -> str:
    return json.dumps(
        {
            "schema_version": "temper-isolation-discovery/v1",
            "rows": [
                {"file": file, "name": name, "value_mm": value}
                for (file, name), value in rows.items()
            ],
        },
        sort_keys=True,
    )


def test_contract_projection_is_versioned_and_role_complete() -> None:
    contract = json.loads(_rust.isolation_authority_contract_json_py())

    assert contract["schema_version"] == "temper-isolation-authority/v1"
    assert len(contract["contract_digest"]) == 64
    assert len(contract["topology_authority_digest"]) == 64
    assert {row["role"] for row in contract["rows"]} == {
        "standards_minimum",
        "conservative_design_target",
        "fabrication_check",
        "production_requirement",
    }
    assert {
        (projection["file"], projection["name"]): (
            projection["value_mm"], projection["role"], projection["authority_key"]
        )
        for projection in contract["projections"]
    } == {
        (
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes.HighVoltage.clearance",
        ): (2.0, "fabrication_check", "clearance.hv_lv.generated.fabrication"),
        ("elec/src/constraints.ato", "HV_to_LV.min_clearance"): (
            6.0,
            "conservative_design_target",
            "clearance.hv_lv.project.target",
        ),
        (
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes.HighVoltageIsolated.clearance",
        ): (6.0, "fabrication_check", "clearance.hv_lv.isolated.fabrication"),
    }
    assert all(row["review_status"] == "current_edition_review_required" for row in contract["rows"])


def test_evaluator_accepts_exact_role_aware_baseline() -> None:
    verdict = json.loads(_rust.evaluate_isolation_authority_json_py(_request()))

    assert verdict["schema_version"] == "temper-isolation-verdict/v1"
    assert verdict["role_resolved"] is True
    assert len(verdict["request_digest"]) == 64
    assert sha256(verdict["canonical_request_json"].encode()).hexdigest() == verdict["request_digest"]
    assert [result["value_mm"] for result in verdict["results"]] == [
        2.0,
        6.0,
        6.0,
    ]
    assert verdict["review_required"]


@pytest.mark.parametrize("bad_value", [1.9, 6.1, float("nan"), float("inf"), -1.0])
def test_evaluator_rejects_value_drift_and_non_finite_values(bad_value: float) -> None:
    rows = dict(EXPECTED_PROJECTIONS)
    rows[("elec/src/constraints.ato", "HV_to_LV.min_clearance")] = bad_value

    with pytest.raises(ValueError):
        _rust.evaluate_isolation_authority_json_py(_request(rows))


def test_evaluator_rejects_missing_and_extra_projection_identity() -> None:
    missing = dict(EXPECTED_PROJECTIONS)
    missing.pop(("elec/src/constraints.ato", "HV_to_LV.min_clearance"))
    with pytest.raises(ValueError):
        _rust.evaluate_isolation_authority_json_py(_request(missing))

    extra = dict(EXPECTED_PROJECTIONS)
    extra[("elec/src/constraints.ato", "UNKNOWN.min_clearance")] = 6.0
    with pytest.raises(ValueError):
        _rust.evaluate_isolation_authority_json_py(_request(extra))
