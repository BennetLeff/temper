"""Authoritative schema for production constraint-family probe inputs.

This is a pure marshalling/validation layer.  It does not parse a board,
construct a model, or call :func:`solve_placement`.  The adapter can use the
schema to turn a family name into the exact top-level solver keyword and to
reject a probe whose required artifact is missing before starting a fresh
worker.

The generic production model (board bounds, component rectangles,
NoOverlap2D, courtyard/netclass separation, and PCL ``extra_constraints``)
is the common base and is intentionally not listed as an optional family.
``decomposed_creepage`` is a search strategy/alternate encoding, not a
production requirement family, and is likewise excluded.  Validator and
body-collision entries are post-solve audits: they are listed because they
can reject a candidate, but are marked separately from model constraints.

| family | ``solve_placement`` kwarg | authoritative source | required artifact |
| --- | --- | --- | --- |
| ``exact_creepage`` | ``experimental_omit_generated_creepage`` | ``_encoder_solve.py`` generated matrix | ``False`` switch |
| ``isolation_barrier`` | ``isolation_barrier`` | ``isolation_barrier.py`` | ``manifest_path`` |
| ``tank_creepage`` | ``tank_creepage`` | ``tank_creepage.py`` | optional ``margin_mm`` (default 10 mm) |
| ``heatsink_colocation`` | ``heatsink_colocation`` | ``heatsink_colocation.py`` | rotation index 0..3 |
| ``protective_impedance_colocation`` | ``protective_impedance_colocation`` | ``protective_impedance_colocation.py`` | ``manifest_path`` or ``chains`` |
| ``fixed_copper`` | ``fixed_copper`` | ``fixed_copper.py`` | ``parse_result`` and ``free_refs`` |
| ``validator_audit`` | ``validator_input`` | ``validator_audit.py`` | ``placement`` and ``voltage_domains`` |
| ``body_collision_audit`` | ``body_collision_input`` | ``body_collision.py`` | ``fab_bodies`` and ``allowlist`` |

The returned mappings are suitable for the independent family campaign:
each mapping is a complete top-level ``solve_placement`` keyword fragment,
not a cumulative mutation of another family's options.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class ConstraintFamilySourceKind(StrEnum):
    """Where a family affects the candidate."""

    MODEL_CONSTRAINT = "model_constraint"
    POST_SOLVE_AUDIT = "post_solve_audit"


@dataclass(frozen=True, slots=True)
class ConstraintFamilyDefinition:
    """Stable metadata for one production family."""

    name: str
    solve_kwarg: str
    source_module: str
    source_kind: ConstraintFamilySourceKind
    required_mapping_keys: tuple[str, ...] = ()
    alternative_mapping_keys: tuple[tuple[str, ...], ...] = ()

    @property
    def is_model_constraint(self) -> bool:
        return self.source_kind is ConstraintFamilySourceKind.MODEL_CONSTRAINT


_DEFINITIONS: tuple[ConstraintFamilyDefinition, ...] = (
    ConstraintFamilyDefinition(
        "exact_creepage", "experimental_omit_generated_creepage",
        "temper_placer.placer.cp_sat._encoder_solve", ConstraintFamilySourceKind.MODEL_CONSTRAINT,
    ),
    ConstraintFamilyDefinition(
        "isolation_barrier", "isolation_barrier",
        "temper_placer.placer.cp_sat.isolation_barrier", ConstraintFamilySourceKind.MODEL_CONSTRAINT,
        required_mapping_keys=("manifest_path",),
    ),
    ConstraintFamilyDefinition(
        "tank_creepage", "tank_creepage",
        "temper_placer.placer.cp_sat.tank_creepage", ConstraintFamilySourceKind.MODEL_CONSTRAINT,
    ),
    ConstraintFamilyDefinition(
        "heatsink_colocation", "heatsink_colocation",
        "temper_placer.placer.cp_sat.heatsink_colocation", ConstraintFamilySourceKind.MODEL_CONSTRAINT,
    ),
    ConstraintFamilyDefinition(
        "protective_impedance_colocation", "protective_impedance_colocation",
        "temper_placer.placer.cp_sat.protective_impedance_colocation",
        ConstraintFamilySourceKind.MODEL_CONSTRAINT,
        alternative_mapping_keys=(("manifest_path",), ("chains",)),
    ),
    ConstraintFamilyDefinition(
        "fixed_copper", "fixed_copper",
        "temper_placer.placer.cp_sat.fixed_copper", ConstraintFamilySourceKind.MODEL_CONSTRAINT,
        required_mapping_keys=("parse_result", "free_refs"),
    ),
    ConstraintFamilyDefinition(
        "validator_audit", "validator_input",
        "temper_placer.placer.cp_sat.validator_audit", ConstraintFamilySourceKind.POST_SOLVE_AUDIT,
        required_mapping_keys=("placement", "voltage_domains"),
    ),
    ConstraintFamilyDefinition(
        "body_collision_audit", "body_collision_input",
        "temper_placer.placer.cp_sat.body_collision", ConstraintFamilySourceKind.POST_SOLVE_AUDIT,
        required_mapping_keys=("fab_bodies", "allowlist"),
    ),
)
_BY_NAME = {definition.name: definition for definition in _DEFINITIONS}


def production_constraint_family_definitions() -> tuple[ConstraintFamilyDefinition, ...]:
    """Return definitions in the documented production order."""

    return _DEFINITIONS


def constraint_family_definition(name: str) -> ConstraintFamilyDefinition:
    """Look up one family or raise a useful schema error."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("constraint family name must be a non-empty string")
    try:
        return _BY_NAME[name.strip()]
    except KeyError as exc:
        raise ValueError(f"unknown production constraint family {name!r}") from exc


def _validate_artifact_mapping(definition: ConstraintFamilyDefinition, value: object) -> None:
    if definition.name == "exact_creepage":
        if value is not False:
            raise ValueError("exact_creepage requires experimental_omit_generated_creepage=False")
        return
    if definition.name == "heatsink_colocation":
        if isinstance(value, bool) or not isinstance(value, int) or value not in range(4):
            raise ValueError("heatsink_colocation requires an integer rotation index in [0, 3]")
        return
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise ValueError(f"{definition.name} must be a mapping of solver artifact options")
    missing = [key for key in definition.required_mapping_keys if key not in value]
    if missing:
        raise ValueError(f"{definition.name} is missing required artifact key(s): {', '.join(missing)}")
    def alternative_matches(alternative: tuple[str, ...]) -> bool:
        # An empty alternative would make all(...) vacuously true and turn a
        # malformed schema into an accepted artifact. Reject it explicitly
        # before aggregating the required-key checks.
        if not alternative:
            return False
        return all(key in value for key in alternative)

    if definition.alternative_mapping_keys and not any(
        alternative_matches(alternative) for alternative in definition.alternative_mapping_keys
    ):
        alternatives = " or ".join("{" + ", ".join(keys) + "}" for keys in definition.alternative_mapping_keys)
        raise ValueError(f"{definition.name} requires one of {alternatives}")


def validate_constraint_family_kwargs(
    family_kwargs: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Validate and copy family fragments for an independent campaign.

    Each family must provide exactly its declared top-level ``solve_placement``
    keyword.  Copies are returned in insertion order so a caller can preserve
    its declared cumulative order; no object is mutated by this function.
    """

    if isinstance(family_kwargs, (str, bytes)) or not isinstance(family_kwargs, Mapping):
        raise TypeError("family_kwargs must be a mapping of family names to solver fragments")
    result: dict[str, dict[str, object]] = {}
    for raw_name, raw_fragment in family_kwargs.items():
        definition = constraint_family_definition(raw_name)
        if isinstance(raw_fragment, (str, bytes)) or not isinstance(raw_fragment, Mapping):
            raise TypeError(f"{definition.name} solver fragment must be a mapping")
        fragment = dict(raw_fragment)
        if set(fragment) != {definition.solve_kwarg}:
            raise ValueError(
                f"{definition.name} fragment must contain exactly {definition.solve_kwarg!r}"
            )
        _validate_artifact_mapping(definition, fragment[definition.solve_kwarg])
        result[definition.name] = fragment
    return result


def production_family_kwargs(
    *,
    exact_creepage: bool = True,
    isolation_barrier: Mapping[str, object] | None = None,
    tank_creepage: Mapping[str, object] | None = None,
    heatsink_colocation: int | None = None,
    protective_impedance_colocation: Mapping[str, object] | None = None,
    fixed_copper: Mapping[str, object] | None = None,
    validator_input: Mapping[str, object] | None = None,
    body_collision_input: Mapping[str, object] | None = None,
) -> dict[str, dict[str, object]]:
    """Build validated top-level kwargs from production artifacts.

    ``exact_creepage=False`` omits that family entirely.  This is useful for
    the stripped-base adapter; a family probe that restores exact generated
    creepage must explicitly use the returned ``False`` switch rather than
    relying on a cumulative mutation of the base's omission flag.
    """

    if not isinstance(exact_creepage, bool):
        raise TypeError("exact_creepage must be a boolean")
    fragments: dict[str, dict[str, object]] = {}
    if exact_creepage:
        fragments["exact_creepage"] = {"experimental_omit_generated_creepage": False}
    supplied: tuple[tuple[str, str, object], ...] = (
        ("isolation_barrier", "isolation_barrier", isolation_barrier),
        ("tank_creepage", "tank_creepage", tank_creepage),
        ("heatsink_colocation", "heatsink_colocation", heatsink_colocation),
        ("protective_impedance_colocation", "protective_impedance_colocation", protective_impedance_colocation),
        ("fixed_copper", "fixed_copper", fixed_copper),
        ("validator_audit", "validator_input", validator_input),
        ("body_collision_audit", "body_collision_input", body_collision_input),
    )
    for family, keyword, value in supplied:
        if value is not None:
            fragments[family] = {keyword: value}
    return validate_constraint_family_kwargs(fragments)


__all__ = [
    "ConstraintFamilyDefinition",
    "ConstraintFamilySourceKind",
    "constraint_family_definition",
    "production_constraint_family_definitions",
    "production_family_kwargs",
    "validate_constraint_family_kwargs",
]
