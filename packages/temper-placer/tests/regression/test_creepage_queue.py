"""TDD/PBT/metamorphic tests for the creepage work queue."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from temper_placer.regression.creepage_queue import (
    CreepageObservation,
    classify_creepage,
    creepage_observations_from_errors,
    observation_from_drc_error,
)
from temper_placer.validation._drc_api import DrcError


def _observation(
    *,
    location: tuple[float, float] = (10.0, 20.0),
    components: tuple[str, ...] = ("U1", "U2"),
    nets: tuple[str, ...] = ("HV", "LV"),
) -> CreepageObservation:
    return CreepageObservation(
        rule="creepage",
        location=location,
        message="Creepage violation: actual 4.0 mm, required 12.6 mm",
        components=components,
        nets=nets,
        actual_distance_mm=4.0,
        required_distance_mm=12.6,
    )


def test_observation_rejects_non_violation_measurements() -> None:
    with pytest.raises(ValueError, match="actual distance"):
        replace(_observation(), actual_distance_mm=13.0)


def test_queue_classifies_layout_package_and_investigation_items() -> None:
    queue = classify_creepage(
        [
            _observation(),
            _observation(location=(11.0, 20.0), components=("U7",)),
            _observation(
                location=(12.0, 20.0),
                nets=(),
                components=(),
            ),
        ]
    )

    assert {
        item.observation.location: item.fix_class for item in queue
    } == {
        (10.0, 20.0): "layout_routing",
        (11.0, 20.0): "same_package_bom",
        (12.0, 20.0): "rule_policy",
    }
    assert all(item.rationale for item in queue)


def test_explicit_rule_policy_identity_overrides_heuristic() -> None:
    observation = _observation()
    queue = classify_creepage(
        [observation], rule_policy_identities={observation.stable_identity}
    )

    assert queue[0].fix_class == "rule_policy"
    assert "explicit" in queue[0].rationale


@given(st.permutations([0, 1, 2]))
def test_input_permutation_does_not_change_queue(permutation: tuple[int, ...]) -> None:
    observations = [
        _observation(location=(10.0, 20.0)),
        _observation(location=(11.0, 20.0), components=("U7",)),
        _observation(location=(12.0, 20.0), nets=(), components=()),
    ]

    queue = classify_creepage([observations[index] for index in permutation])

    assert tuple(item.stable_identity for item in queue) == tuple(
        item.stable_identity for item in classify_creepage(observations)
    )


def test_duplicate_observations_are_idempotent() -> None:
    observation = _observation()

    once = classify_creepage([observation])
    repeated = classify_creepage([observation, observation, observation])

    assert repeated == once


@given(
    x=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    y=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    actual=st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False),
    margin=st.floats(min_value=0.01, max_value=10, allow_nan=False, allow_infinity=False),
)
def test_valid_generated_measurements_remain_deterministic(
    x: float, y: float, actual: float, margin: float
) -> None:
    observation = replace(
        _observation(),
        location=(x, y),
        actual_distance_mm=actual,
        required_distance_mm=actual + margin,
    )

    queue = classify_creepage([observation, observation])

    assert len(queue) == 1
    assert queue[0].stable_identity == observation.stable_identity


def test_component_reference_renaming_does_not_change_identity() -> None:
    original = _observation(components=("U1", "U2"))
    renamed = replace(original, components=("U99", "U100"))

    assert renamed.stable_identity == original.stable_identity
    assert classify_creepage([renamed])[0].fix_class == "layout_routing"


@pytest.mark.parametrize(
    "change",
    [
        {"nets": ("HV", "PE")},
        {"location": (10.01, 20.0)},
        {"actual_distance_mm": 4.1},
    ],
)
def test_physical_identity_change_changes_queue_identity(
    change: dict[str, object],
) -> None:
    original = _observation()
    changed = replace(original, **change)

    assert changed.stable_identity != original.stable_identity


def test_unrelated_observation_does_not_change_existing_items() -> None:
    original = _observation()
    unrelated = _observation(location=(90.0, 90.0), nets=("A", "B"))

    baseline = classify_creepage([original])
    expanded = classify_creepage([original, unrelated])

    assert baseline[0] == next(
        item for item in expanded if item.stable_identity == original.stable_identity
    )


def test_drc_error_adapter_parses_labelled_distances() -> None:
    error = DrcError(
        rule="creepage",
        severity="error",
        location=(10.0, 20.0),
        message="Creepage violation: actual 4.0 mm, required 12.6 mm",
        components=["U1", "U2"],
        nets=["HV", "LV"],
    )

    observation = observation_from_drc_error(error)

    assert observation.actual_distance_mm == pytest.approx(4.0)
    assert observation.required_distance_mm == pytest.approx(12.6)
    assert observation.components == ("U1", "U2")


def test_drc_error_adapter_parses_strict_inequality() -> None:
    error = DrcError(
        rule="creepage",
        severity="error",
        location=(10.0, 20.0),
        message="Creepage violation (4.0 mm < 12.6 mm)",
    )

    observation = observation_from_drc_error(error)

    assert observation.actual_distance_mm == pytest.approx(4.0)
    assert observation.required_distance_mm == pytest.approx(12.6)


def test_drc_error_adapter_parses_kicad_creepage_message() -> None:
    error = DrcError(
        rule="creepage",
        severity="error",
        location=(10.0, 20.0),
        message=(
            "Creepage violation (rule 'HV to LV' creepage 12.6000 mm; "
            "actual 0.9458 mm)"
        ),
    )

    observation = observation_from_drc_error(error)

    assert observation.actual_distance_mm == pytest.approx(0.9458)
    assert observation.required_distance_mm == pytest.approx(12.6)


def test_drc_error_without_structured_distance_remains_investigation() -> None:
    error = DrcError(
        rule="creepage",
        severity="error",
        location=(10.0, 20.0),
        message="Creepage violation; inspect package geometry",
        components=["U1", "U2"],
        nets=["HV", "LV"],
    )

    item = classify_creepage([observation_from_drc_error(error)])[0]

    assert item.fix_class == "rule_policy"
    assert "insufficient" in item.rationale


def test_drc_error_adapter_rejects_non_creepage_rule() -> None:
    error = DrcError(
        rule="clearance",
        severity="error",
        location=(10.0, 20.0),
        message="Clearance violation (0.1 mm < 0.2 mm)",
    )

    with pytest.raises(ValueError, match="creepage"):
        observation_from_drc_error(error)


def test_batch_adapter_ignores_unrelated_drc_errors() -> None:
    creepage = DrcError(
        rule="creepage",
        severity="error",
        location=(10.0, 20.0),
        message="Creepage violation (4.0 mm < 12.6 mm)",
    )
    unrelated = DrcError(
        rule="clearance",
        severity="error",
        location=(11.0, 20.0),
        message="Clearance violation (0.1 mm < 0.2 mm)",
    )

    baseline = creepage_observations_from_errors([creepage])
    with_unrelated = creepage_observations_from_errors([creepage, unrelated])

    assert with_unrelated == baseline
