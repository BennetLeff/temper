"""Differential test: ConstraintBuilder compute (temper-constraint-compiler)
vs the pinned Python oracle.

Wave 4, Phase 4 — the constraints surface migration. The Rust migration
(reproducing ``temper_placer/constraints/builder.py``'s compute — ``validate``
error assembly and the ``to_yaml`` serialization-shape logic — bit-identically
in the ``temper-constraint-compiler`` crate) is driven through the delegation
shim ``temper_placer.constraints.builder``; the pre-migration implementation
is pinned verbatim as the oracle (``_builder_py_oracle.py``, commit aece7c372).

The fluent ``add_*`` construction methods stay Python (they build pydantic
``_constraint_types`` objects — orchestration, not compute); the differential
here pins the migrated compute: ``validate()`` error strings byte-for-byte and
``to_yaml()`` output byte-for-byte (the dict-shape logic in Rust, PyYAML
``yaml.dump`` still on the Python side per the Wave-4 guide's PyYAML ruling).

The module-scope reference to ``_rust.builder_validate`` is the RED arm:
before the Rust surface lands this file fails to collect (AttributeError).
"""

from __future__ import annotations

import random

import temper_constraint_compiler as _rust
import yaml

import tests.constraints._builder_py_oracle as _oracle
from temper_placer.constraints.builder import ConstraintBuilder

# Module-scope RED arm.
assert hasattr(_rust, "builder_validate")
assert hasattr(_rust, "builder_to_yaml_data")


def _random_chain(rng: random.Random):
    """A random but deterministic chain of fluent add_* calls."""
    calls = []
    refs = ["Q1", "Q2", "U_GATE", "U_MCU", "C1", "C2", "R5", "J_USB"]
    for _ in range(rng.randint(0, 6)):
        kind = rng.randint(0, 5)
        if kind == 0:
            calls.append(("add_spacing", (rng.choice(refs), rng.choice(refs), rng.uniform(1.0, 30.0)),
                          {"tier": rng.choice(["hard", "soft"]), "weight": rng.choice([1.0, 1.0, 2.5]),
                           "description": rng.choice(["", "keep apart"])}))
        elif kind == 1:
            calls.append(("add_proximity", (rng.choice(refs), rng.choice(refs), rng.uniform(5.0, 40.0)),
                          {"tier": rng.choice(["hard", "soft"]),
                           "group_name": rng.choice([None, None, "grp", "power"])}))
        elif kind == 2:
            calls.append(("add_escape_clearance", (rng.choice(refs),),
                          {"clearance_mm": rng.choice([None, rng.uniform(2.0, 12.0)]),
                           "tier": rng.choice(["hard", "soft"])}))
        elif kind == 3:
            calls.append(("add_routing_corridor", (f"c{rng.randint(1, 9)}", rng.choice(refs), rng.choice(refs), rng.uniform(1.0, 8.0)),
                          {"keep_clear": rng.choice([True, False]), "tier": rng.choice(["hard", "soft"])}))
        elif kind == 4:
            calls.append(("add_thermal_constraint", (rng.sample(refs, rng.randint(1, 2)),),
                          {"prefer_edge": rng.choice([True, False]),
                           "max_distance_from_edge_mm": rng.uniform(5.0, 25.0)}))
        else:
            calls.append(("add_group", (f"grp{rng.randint(1, 9)}", rng.sample(refs, rng.randint(1, 3))),
                          {"max_spread_mm": rng.uniform(10.0, 50.0), "zone": rng.choice([None, None, "Zone1"]),
                           "weight": rng.choice([1.0, 1.0, 3.0])}))
    return calls


def _apply(builder, calls):
    for name, args, kwargs in calls:
        getattr(builder, name)(*args, **kwargs)
    return builder


# ---------------------------------------------------------------------------
# R1a — behavioural A/B: validate() error strings, byte-identical.
# ---------------------------------------------------------------------------


class TestBuilderValidateDifferential:
    def test_empty_validate(self):
        """Empty constraints validate clean regardless of availability."""
        o = _oracle.ConstraintBuilder()
        s = ConstraintBuilder()
        for avail in ([], ["Q1", "Q2"], ["A", "B", "C", "D", "E", "U1"]):
            for zones in (None, [], ["Zone1"]):
                assert o.validate(100.0, 100.0, avail, zones) == s.validate(100.0, 100.0, avail, zones)

    def test_random_differential(self):
        rng = random.Random(0xB01D)
        refs = ["Q1", "Q2", "U_GATE", "U_MCU", "C1", "C2", "R5", "J_USB", "MISSING1", "MISSING2"]
        for case in range(100):
            calls = _random_chain(rng)
            o = _apply(_oracle.ConstraintBuilder(), calls)
            s = _apply(ConstraintBuilder(), calls)
            avail = rng.sample(refs, rng.randint(0, len(refs)))
            zones = rng.choice([None, [], ["Zone1"], ["Zone1", "HV"]])
            oe, se = o.validate(100.0, 100.0, avail, zones), s.validate(100.0, 100.0, avail, zones)
            assert oe == se, f"builder validate mismatch case={case}"

    def test_missing_component_error_text(self):
        """Exact error strings for a missing component."""
        o = _apply(_oracle.ConstraintBuilder(), [("add_escape_clearance", ("MISSING",), {})])
        s = _apply(ConstraintBuilder(), [("add_escape_clearance", ("MISSING",), {})])
        assert o.validate(100.0, 100.0, ["Q1"]) == s.validate(100.0, 100.0, ["Q1"])
        assert s.validate(100.0, 100.0, ["Q1"]) == ["EscapeClearance: component 'MISSING' not found"]

    def test_zone_missing_only_reported_when_zones_given(self):
        """group.zone missing is reported only when available_zones is not None."""
        o = _apply(_oracle.ConstraintBuilder(), [("add_group", ("g", ["A"]), {"zone": "NOPE"})])
        s = _apply(ConstraintBuilder(), [("add_group", ("g", ["A"]), {"zone": "NOPE"})])
        assert o.validate(100.0, 100.0, ["A"], None) == s.validate(100.0, 100.0, ["A"], None)
        assert s.validate(100.0, 100.0, ["A"], None) == []
        assert o.validate(100.0, 100.0, ["A"], ["Zone1"]) == s.validate(100.0, 100.0, ["A"], ["Zone1"])
        assert s.validate(100.0, 100.0, ["A"], ["Zone1"]) == [
            "ComponentGroup 'g': zone 'NOPE' not found"
        ]


# ---------------------------------------------------------------------------
# R1a — behavioural A/B: to_yaml(), byte-identical (PyYAML stays Python).
# ---------------------------------------------------------------------------


class TestToYamlDifferential:
    def test_empty_to_yaml(self):
        o = _oracle.ConstraintBuilder()
        s = ConstraintBuilder()
        assert o.to_yaml() == s.to_yaml()
        assert s.to_yaml() == "{}\n"

    def test_random_differential(self):
        rng = random.Random(0x9A11)
        for case in range(80):
            calls = _random_chain(rng)
            o = _apply(_oracle.ConstraintBuilder(), calls)
            s = _apply(ConstraintBuilder(), calls)
            assert o.to_yaml() == s.to_yaml(), f"to_yaml mismatch case={case}"

    def test_conditional_keys(self):
        """Serialization-shape logic: weight/zone/description/proximity omitted when default."""
        o = _apply(
            _oracle.ConstraintBuilder(),
            [("add_group", ("g", ["A", "B"]), {"max_spread_mm": 30.0, "weight": 1.0})],
        )
        s = _apply(
            ConstraintBuilder(),
            [("add_group", ("g", ["A", "B"]), {"max_spread_mm": 30.0, "weight": 1.0})],
        )
        assert o.to_yaml() == s.to_yaml()
        data = yaml.safe_load(s.to_yaml())
        assert "weight" not in data["groups"][0]
        assert "zone" not in data["groups"][0]
        assert "proximity" not in data["groups"][0]

    def test_conditional_keys_present(self):
        o = _apply(
            _oracle.ConstraintBuilder(),
            [
                ("add_group", ("g", ["A", "B"]), {"zone": "Zone1", "weight": 2.0, "description": "d"}),
                ("add_proximity", ("A", "B", 10.0), {"group_name": "g"}),
            ],
        )
        s = _apply(
            ConstraintBuilder(),
            [
                ("add_group", ("g", ["A", "B"]), {"zone": "Zone1", "weight": 2.0, "description": "d"}),
                ("add_proximity", ("A", "B", 10.0), {"group_name": "g"}),
            ],
        )
        assert o.to_yaml() == s.to_yaml()
        data = yaml.safe_load(s.to_yaml())
        group = data["groups"][0]
        assert group["zone"] == "Zone1"
        assert group["weight"] == 2.0
        assert group["description"] == "d"
        assert len(group["proximity"]) == 1

    def test_float_precision_in_yaml(self):
        """Non-integer floats must serialize identically (PyYAML formatting of the values)."""
        o = _apply(_oracle.ConstraintBuilder(), [("add_spacing", ("A", "B", 10.25), {"weight": 1.5})])
        s = _apply(ConstraintBuilder(), [("add_spacing", ("A", "B", 10.25), {"weight": 1.5})])
        assert o.to_yaml() == s.to_yaml()
        assert "10.25" in s.to_yaml()
        assert "1.5" in s.to_yaml()

    def test_empty_string_zone_is_ignored(self):
        """An empty-string group zone is falsy in Python: no zone error is
        reported even when available_zones is given. Discriminates the
        `group.zone` truthiness gate (surviving mutant M8)."""
        o = _apply(_oracle.ConstraintBuilder(), [("add_group", ("g", ["A"]), {"zone": ""})])
        s = _apply(ConstraintBuilder(), [("add_group", ("g", ["A"]), {"zone": ""})])
        for zones in (None, [], ["Zone1"]):
            assert o.validate(100.0, 100.0, ["A"], zones) == s.validate(100.0, 100.0, ["A"], zones)
            assert s.validate(100.0, 100.0, ["A"], zones) == []

    def test_empty_string_zone_omitted_in_to_yaml(self):
        """The `if group.zone:` gate applies to the to_yaml dict-shape too:
        an empty-string zone is falsy, so the `zone` key is omitted exactly
        as for zone=None. `test_empty_string_zone_is_ignored` pins the same
        gate on validate(); this pins it on the serialization shape (the
        `if let Some(zone) = &g.zone` variant would emit `zone: ''`)."""
        for zone in ("", None):
            o = _apply(_oracle.ConstraintBuilder(), [("add_group", ("g", ["A"]), {"zone": zone})])
            s = _apply(ConstraintBuilder(), [("add_group", ("g", ["A"]), {"zone": zone})])
            assert o.to_yaml() == s.to_yaml(), f"to_yaml mismatch zone={zone!r}"
        data = yaml.safe_load(s.to_yaml())
        assert "zone" not in data["groups"][0]
