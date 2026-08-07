"""Property-based + metamorphic tests for the migrated ConstraintBuilder.

Wave 4, Phase 4 (R1c/R1d). The Rust-migrated compute of
``temper_placer.constraints.builder`` — ``validate()`` error assembly and the
``to_yaml()`` serialization-shape logic — must satisfy these properties;
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_builder_rust_differential.py``.

Five properties (non-vacuously guarded):

- P1. Valid build validates clean: a builder whose every referenced component
  is in ``available_components`` (and every zone in ``available_zones``)
  produces zero errors — and the same build with a missing component produces
  at least one error.
- P2. Missing-reference count: each distinct missing component reference
  produces exactly one error mentioning it (per rule category), so the error
  list is non-empty iff some reference is missing.
- P3. Determinism: identical inputs yield identical error lists and identical
  YAML (validate and to_yaml are pure functions of the built constraints).
- P4. YAML shape: ``to_yaml()`` output parses (PyYAML round-trip) and every
  rule category present in the build appears in the parsed data; categories
  absent from the build are absent from the data.
- P5. YAML numeric round-trip: spacing ``min_separation_mm``/``weight`` survive
  the YAML round-trip exactly (float equality), and the emitted YAML preserves
  them as floats, not strings.

Four metamorphic relations (honestly bounded):

- MR1. ``available_components`` order independence: permuting the
  ``available_components`` list never changes the error list (membership is a
  set operation; the error ORDER follows the rule order, not the availability
  order).
- MR2. Zone check gating: the group-zone error appears iff ``available_zones``
  is not None; passing ``None`` vs ``[]`` for an otherwise-valid build yields
  the same (empty) errors — the None gate is the only difference.
- MR3. Serialization monotonicity: adding a rule with a non-default attribute
  (weight != 1.0, zone set, description set, proximity rules) adds exactly the
  corresponding key to the group's YAML dict; adding a defaulted rule does not
  (checked via parsed YAML).
- MR4. ``build()`` identity with base: building on a base object returns that
  exact object (``build() is base``), preserving the fluent-extend contract.
"""

from __future__ import annotations

import yaml

from temper_placer.constraints.builder import ConstraintBuilder

# ---------------------------------------------------------------------------
# P1 — valid build validates clean; missing reference is caught
# ---------------------------------------------------------------------------


def test_p1_valid_build_validates_clean():
    builder = (
        ConstraintBuilder()
        .add_spacing("Q1", "Q2", 10.0)
        .add_escape_clearance("U_MCU", 10.0)
        .add_routing_corridor("usb", "J_USB", "U_MCU", 6.0)
        .add_group("power", ["Q1", "Q2"], zone="HV")
        .add_thermal_constraint(["Q1"])
    )
    errors = builder.validate(
        100.0,
        100.0,
        available_components=["Q1", "Q2", "U_MCU", "J_USB"],
        available_zones=["HV"],
    )
    assert errors == []


def test_p1_missing_component_produces_errors():
    builder = ConstraintBuilder().add_spacing("Q1", "Q2", 10.0).add_escape_clearance("U_MCU", 10.0)
    errors = builder.validate(100.0, 100.0, available_components=["Q1"])
    assert len(errors) >= 1
    assert any("Q2" in e for e in errors)
    assert any("U_MCU" in e for e in errors)


# ---------------------------------------------------------------------------
# P2 — error count tracks missing references
# ---------------------------------------------------------------------------


def test_p2_one_error_per_missing_reference():
    builder = (
        ConstraintBuilder()
        .add_spacing("A", "B", 10.0)
        .add_proximity("C", "D", 10.0)
        .add_escape_clearance("E", 10.0)
        .add_routing_corridor("c", "F", "G", 6.0)
        .add_thermal_constraint(["H"])
        .add_group("grp", ["I"])
    )
    errors = builder.validate(100.0, 100.0, available_components=[])
    # A, B (spacing) + C, D (proximity group comps) + E (escape) + F, G
    # (corridor) + H (thermal) + I (group) = 9 missing references, 9 errors.
    assert len(errors) == 9
    for ref in "ABCDEFGHI":
        assert any(ref in e for e in errors), f"no error mentions {ref}"


# ---------------------------------------------------------------------------
# P3 — determinism
# ---------------------------------------------------------------------------


def test_p3_deterministic_validate_and_yaml():
    def build():
        return (
            ConstraintBuilder()
            .add_spacing("Q1", "Q2", 10.0, weight=1.5)
            .add_proximity("U_GATE", "Q1", 8.0, group_name="g")
            .add_escape_clearance("MISSING", 10.0)
        )

    expected_yaml = None
    for _ in range(5):
        b = build()
        errors = b.validate(100.0, 100.0, ["Q1", "Q2", "U_GATE"])
        yaml_str = b.to_yaml()
        assert errors == ["EscapeClearance: component 'MISSING' not found"]
        if expected_yaml is None:
            expected_yaml = yaml_str
        assert yaml_str == expected_yaml


# ---------------------------------------------------------------------------
# P4 — YAML shape: present categories appear, absent categories do not
# ---------------------------------------------------------------------------


def test_p4_yaml_shape_present_and_absent():
    builder = (
        ConstraintBuilder()
        .add_spacing("Q1", "Q2", 10.0, tier="hard")
        .add_thermal_constraint(["Q1"])
    )
    data = yaml.safe_load(builder.to_yaml())
    assert "minimum_spacing" in data
    assert "thermal_constraints" in data
    assert "groups" not in data
    assert "escape_clearances" not in data
    assert "routing_corridors" not in data

    empty = yaml.safe_load(ConstraintBuilder().to_yaml())
    assert empty == {}


# ---------------------------------------------------------------------------
# P5 — YAML numeric round-trip (floats survive)
# ---------------------------------------------------------------------------


def test_p5_yaml_numeric_round_trip():
    builder = ConstraintBuilder().add_spacing("A", "B", 10.25, weight=1.5)
    data = yaml.safe_load(builder.to_yaml())
    rule = data["minimum_spacing"][0]
    assert rule["min_separation_mm"] == 10.25
    assert rule["weight"] == 1.5
    assert isinstance(rule["min_separation_mm"], float)
    assert isinstance(rule["weight"], float)


# ---------------------------------------------------------------------------
# MR1 — available_components order independence
# ---------------------------------------------------------------------------


def test_mr1_available_components_order_independence():
    builder = ConstraintBuilder().add_spacing("A", "B", 10.0).add_group("g", ["C"])
    base = builder.validate(100.0, 100.0, ["A", "B", "C", "X", "Y"])
    for perm in (["Y", "X", "C", "B", "A"], ["C", "A", "Y", "B", "X"], ["X", "C", "Y", "A", "B"]):
        assert builder.validate(100.0, 100.0, perm) == base


# ---------------------------------------------------------------------------
# MR2 — zone check gating on available_zones None-ness
# ---------------------------------------------------------------------------


def test_mr2_zone_check_gated_on_zones_not_none():
    builder = ConstraintBuilder().add_group("g", ["A"], zone="NOPE")
    assert builder.validate(100.0, 100.0, ["A"], None) == []
    assert builder.validate(100.0, 100.0, ["A"], []) == ["ComponentGroup 'g': zone 'NOPE' not found"]
    assert builder.validate(100.0, 100.0, ["A"], ["Zone1"]) == [
        "ComponentGroup 'g': zone 'NOPE' not found"
    ]


# ---------------------------------------------------------------------------
# MR3 — serialization monotonicity of conditional keys
# ---------------------------------------------------------------------------


def test_mr3_yaml_conditional_key_monotonicity():
    default_group = ConstraintBuilder().add_group("g", ["A", "B"])
    default_data = yaml.safe_load(default_group.to_yaml())["groups"][0]
    assert set(default_data.keys()) == {"name", "components", "max_spread_mm"}

    with_zone = ConstraintBuilder().add_group("g", ["A", "B"], zone="HV")
    assert set(yaml.safe_load(with_zone.to_yaml())["groups"][0].keys()) == {
        "name",
        "components",
        "max_spread_mm",
        "zone",
    }

    with_weight = ConstraintBuilder().add_group("g", ["A", "B"], weight=2.5)
    assert set(yaml.safe_load(with_weight.to_yaml())["groups"][0].keys()) == {
        "name",
        "components",
        "max_spread_mm",
        "weight",
    }

    with_proximity = (
        ConstraintBuilder().add_group("g", ["A", "B"]).add_proximity("A", "B", 10.0, group_name="g")
    )
    assert set(yaml.safe_load(with_proximity.to_yaml())["groups"][0].keys()) == {
        "name",
        "components",
        "max_spread_mm",
        "proximity",
    }


# ---------------------------------------------------------------------------
# MR4 — build() identity with base
# ---------------------------------------------------------------------------


def test_mr4_build_identity_with_base():
    from temper_placer._constraint_types import PlacementConstraints

    base = PlacementConstraints()
    builder = ConstraintBuilder(base)
    assert builder.build() is base
    builder.add_spacing("A", "B", 10.0)
    assert builder.build() is base
    assert len(base.component_spacing_rules) == 1


# ---------------------------------------------------------------------------
# R20 suite hardening — discriminator moved from the differential. #850's
# differential-disabled re-run found M8 (builder empty-string-zone gate)
# survives the suites-only run; its discriminating assertion lived only in
# `test_builder_rust_differential.py`. The gate is a deterministic invariant
# of the validate()/to_yaml() surface, so it is pinned here. The differential
# keeps its own assertion.
# ---------------------------------------------------------------------------


def test_p6_empty_string_zone_is_ignored():
    """An empty-string group zone is falsy: ``validate()`` reports no zone
    error even when ``available_zones`` is given, and ``to_yaml()`` omits the
    ``zone`` key exactly as for ``zone=None``. A port that dropped the
    ``!zone.is_empty()`` gate would treat ``zone=''`` as a real zone and emit
    a 'not found' error (surviving mutant M8)."""
    builder = ConstraintBuilder().add_group("g", ["A"], zone="")
    for zones in (None, [], ["Zone1"], ["HV", "Zone1"]):
        assert builder.validate(100.0, 100.0, ["A"], zones) == [], zones
    data = yaml.safe_load(builder.to_yaml())
    assert "zone" not in data["groups"][0]
    # The zone=None build serializes identically (falsy-equivalence).
    none_builder = ConstraintBuilder().add_group("g", ["A"], zone=None)
    none_data = yaml.safe_load(none_builder.to_yaml())
    assert "zone" not in none_data["groups"][0]
    # Non-vacuity: a non-empty zone IS validated and serialized.
    real = ConstraintBuilder().add_group("g", ["A"], zone="HV")
    assert real.validate(100.0, 100.0, ["A"], ["Zone1"]) == [
        "ComponentGroup 'g': zone 'HV' not found"
    ]
    assert "zone" in yaml.safe_load(real.to_yaml())["groups"][0]
