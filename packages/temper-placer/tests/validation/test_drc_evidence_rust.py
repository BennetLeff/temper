"""Production-shaped checks for the Rust-owned KiCad DRC evidence boundary."""

from __future__ import annotations

import json

import pytest
import temper_drc_rs

from tests.validation._drc_evidence_py_oracle import identities as oracle_identities


def _creepage(*, actual: str = "10.2975", track_length: str = "0.8485") -> dict:
    return {
        "type": "creepage",
        "description": (
            "Creepage violation (rule 'HighVoltageSignal to LV' creepage "
            f"12.6000 mm; actual {actual} mm)"
        ),
        "items": [
            {
                "description": "Pad 2 [discharge.r_snub1-p2] of R14 on F.Cu",
                "pos": {"x": 130.0, "y": 87.5},
                "uuid": "provider-generated-pad-uuid",
            },
            {
                "description": (
                    f"Track [V_BUS_SENSE] on F.Cu, length {track_length} mm"
                ),
                "pos": {"x": 139.1, "y": 87.5},
                "uuid": "provider-generated-track-uuid",
            },
        ],
    }


def _envelope(samples: list[list[dict]]) -> dict:
    encoded = temper_drc_rs.drc_evidence_envelope_json(
        json.dumps(samples, separators=(",", ":"))
    )
    return json.loads(encoded)


def _compare(baseline: list[list[dict]], candidate: list[list[dict]]) -> dict:
    return json.loads(
        temper_drc_rs.drc_admission_comparison_json(
            json.dumps(
                {
                    "baseline_samples": baseline,
                    "candidate_samples": candidate,
                    "baseline_capped_categories": [],
                    "candidate_capped_categories": [],
                    "baseline_silk_receipt": None,
                    "candidate_silk_receipt": None,
                },
                separators=(",", ":"),
            )
        )
    )


def test_provider_item_churn_is_raw_fringe_not_semantic_change() -> None:
    result = _envelope(
        [
            [_creepage(track_length="0.8485")],
            [_creepage(track_length="11.9000")],
            [_creepage(track_length="0.8485")],
        ]
    )

    assert result["schema"] == "temper.drc-semantic-envelope/v1"
    assert result["observation"]["stable"] is True
    assert result["observation"]["intersection_size"] == 1
    assert result["observation"]["union_size"] == 1
    assert result["raw"]["stable"] is False
    assert result["raw"]["intersection_size"] == 0
    assert result["raw"]["union_size"] == 2
    assert len(result["raw"]["unstable_fringe"]) == 2


@pytest.mark.parametrize(
    "finding",
    [
        _creepage(),
        {
            "type": "shorting_items",
            "description": "Items shorting two nets (nets rtd_sense_p and gnd)",
            "items": [
                {"description": "Via [gnd] on F.Cu - B.Cu", "pos": {"x": 96.5, "y": 91.0}},
                {
                    "description": "Track [rtd_sense_p] on F.Cu, length 2.2000 mm",
                    "pos": {"x": 97.0, "y": 91.0},
                },
            ],
        },
    ],
)
def test_rust_identity_matches_pinned_python_oracle_on_production_shapes(finding: dict) -> None:
    family, observation, raw = oracle_identities(finding)
    result = _envelope([[finding]])

    assert result["family"]["intersection"] == [{"key": family, "count": 1}]
    assert result["observation"]["intersection"] == [{"key": observation, "count": 1}]
    assert result["raw"]["intersection"] == [{"key": raw, "count": 1}]


def test_actual_distance_and_finding_multiplicity_remain_identity_bearing() -> None:
    distance = _envelope([[_creepage()], [_creepage(actual="10.1975")]])
    assert distance["observation"]["stable"] is False

    multiplicity = _envelope([[_creepage()], [_creepage(), _creepage()]])
    assert multiplicity["observation"]["stable"] is False
    assert multiplicity["observation"]["intersection_size"] == 1
    assert multiplicity["observation"]["union_size"] == 2


def test_non_creepage_item_position_remains_identity_bearing() -> None:
    baseline = {
        "type": "clearance",
        "description": (
            "Clearance violation (netclass 'Power' clearance 0.5000 mm; "
            "actual 0.2868 mm)"
        ),
        "items": [
            {
                "description": "Via [gnd] on F.Cu",
                "pos": {"x": 100.0, "y": 80.0},
            }
        ],
    }
    moved = json.loads(json.dumps(baseline))
    moved["items"][0]["pos"]["x"] = 100.1

    result = _envelope([[baseline], [moved]])

    assert result["family"]["stable"] is False
    assert result["observation"]["stable"] is False


def test_malformed_report_fails_with_typed_evidence_code() -> None:
    malformed = [[{"type": "creepage", "description": "actual nope", "items": []}]]
    with pytest.raises(ValueError, match="DRC_EVIDENCE_MALFORMED_DISTANCE"):
        temper_drc_rs.drc_evidence_envelope_json(json.dumps(malformed))


def test_cross_subject_comparison_uses_same_semantic_family_and_ranked_distance() -> None:
    baseline = [
        [_creepage(actual="10.2", track_length=provider)]
        for provider in ("0.8", "11.9", "0.8")
    ]
    candidate = [
        [_creepage(actual="10.1", track_length=provider)]
        for provider in ("11.9", "0.8", "11.9")
    ]

    receipt = _compare(baseline, candidate)

    assert receipt["semantic_repeats_agree"] is True
    assert receipt["worsened_hard_observation_count"] == 1
    assert receipt["new_hard_observation_count"] == 0
