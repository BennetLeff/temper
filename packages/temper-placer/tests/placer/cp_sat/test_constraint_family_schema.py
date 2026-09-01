"""Pure schema contracts for production constraint-family adapters."""

from __future__ import annotations

import pytest

from temper_placer.placer.cp_sat.constraint_family_schema import (
    ConstraintFamilySourceKind,
    constraint_family_definition,
    production_constraint_family_definitions,
    production_family_kwargs,
    validate_constraint_family_kwargs,
)


def test_definitions_match_top_level_solver_keywords_and_source_kinds() -> None:
    definitions = production_constraint_family_definitions()
    assert [definition.name for definition in definitions] == [
        "exact_creepage",
        "isolation_barrier",
        "tank_creepage",
        "heatsink_colocation",
        "protective_impedance_colocation",
        "fixed_copper",
        "validator_audit",
        "body_collision_audit",
    ]
    assert constraint_family_definition("tank_creepage").solve_kwarg == "tank_creepage"
    assert constraint_family_definition("validator_audit").source_kind is ConstraintFamilySourceKind.POST_SOLVE_AUDIT
    assert constraint_family_definition("fixed_copper").is_model_constraint


def test_production_family_builder_returns_independent_top_level_fragments() -> None:
    fragments = production_family_kwargs(
        isolation_barrier={"manifest_path": "/tmp/barrier.yaml"},
        tank_creepage={"margin_mm": 10.0},
        heatsink_colocation=2,
        protective_impedance_colocation={"chains": ()},
        fixed_copper={"parse_result": object(), "free_refs": {"U1"}},
        validator_input={"placement": {}, "voltage_domains": {}},
        body_collision_input={"fab_bodies": {}, "allowlist": object()},
    )
    assert fragments["exact_creepage"] == {"experimental_omit_generated_creepage": False}
    assert fragments["tank_creepage"] == {"tank_creepage": {"margin_mm": 10.0}}
    assert fragments["heatsink_colocation"] == {"heatsink_colocation": 2}
    assert list(fragments) == [
        "exact_creepage",
        "isolation_barrier",
        "tank_creepage",
        "heatsink_colocation",
        "protective_impedance_colocation",
        "fixed_copper",
        "validator_audit",
        "body_collision_audit",
    ]

    stripped_base = production_family_kwargs(exact_creepage=False)
    assert stripped_base == {}


def test_schema_requires_declared_artifacts_and_rejects_extra_top_level_keys() -> None:
    with pytest.raises(ValueError, match="manifest_path"):
        validate_constraint_family_kwargs({"isolation_barrier": {"isolation_barrier": {}}})
    with pytest.raises(ValueError, match="parse_result"):
        validate_constraint_family_kwargs({"fixed_copper": {"fixed_copper": {"free_refs": set()}}})
    with pytest.raises(ValueError, match="exactly 'tank_creepage'"):
        validate_constraint_family_kwargs({"tank_creepage": {"margin_mm": 10.0}})
    with pytest.raises(ValueError, match="rotation index"):
        validate_constraint_family_kwargs({"heatsink_colocation": {"heatsink_colocation": 4}})


def test_protective_impedance_allows_exactly_one_artifact_form() -> None:
    valid = validate_constraint_family_kwargs(
        {"protective_impedance_colocation": {"protective_impedance_colocation": {"chains": ()}}}
    )
    assert valid["protective_impedance_colocation"]["protective_impedance_colocation"] == {"chains": ()}
    with pytest.raises(ValueError, match="manifest_path.*chains"):
        validate_constraint_family_kwargs(
            {"protective_impedance_colocation": {"protective_impedance_colocation": {}}}
        )


def test_schema_rejects_unknown_family_and_does_not_mutate_artifact_mapping() -> None:
    with pytest.raises(ValueError, match="unknown production constraint family"):
        validate_constraint_family_kwargs({"decomposed_creepage": {"decomposed_creepage": True}})
    options = {"tank_creepage": {"margin_mm": 10.0}}
    result = validate_constraint_family_kwargs({"tank_creepage": options})
    assert result["tank_creepage"] is not options
    assert result["tank_creepage"]["tank_creepage"] is options["tank_creepage"]
