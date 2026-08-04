"""Differential test: ConstraintReporter / ConstraintReport compute
(temper-constraint-compiler) vs the pinned Python oracle.

Wave 4, Phase 4 — the constraints surface migration. The Rust migration
(reproducing ``temper_placer/constraints/reporter.py`` bit-identically in the
``temper-constraint-compiler`` crate) is driven through the delegation shim
``temper_placer.constraints.reporter``; the pre-migration implementation is
pinned verbatim as the oracle (``_reporter_py_oracle.py``, commit aece7c372).

Every assertion drives IDENTICAL inputs through both sides and compares
bit-exactly: floats via ``float.hex()``, messages and text/JSON output as
byte-identical strings, result lists canonicalised with concrete types.

The module-scope reference to ``_rust.check_constraints`` is the RED arm:
before the Rust surface lands this file fails to collect (AttributeError).
"""

from __future__ import annotations

import json
import random

import temper_constraint_compiler as _rust

import tests.constraints._reporter_py_oracle as _oracle
from temper_placer._constraint_types import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)
from temper_placer.constraints.reporter import (
    ConstraintReport,
    ConstraintReporter,
    ConstraintResult,
    ConstraintStatus,
)

# Module-scope RED arm.
assert hasattr(_rust, "check_constraints")
assert hasattr(_rust, "report_to_text")
assert hasattr(_rust, "report_to_json_data")


# ---------------------------------------------------------------------------
# Canonicalization (bit-exact floats, concrete types).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _result_key(r: ConstraintResult):
    return (
        r.constraint_type,
        r.status.value,
        r.tier,
        tuple(r.components),
        r.message,
        _f(r.actual_value),
        _f(r.expected_value),
        tuple(sorted(r.details.items())),
    )


def _random_constraints(rng: random.Random) -> PlacementConstraints:
    r = random.Random(rng.randint(0, 2**31))
    refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
    spacing = [
        ComponentSpacingRule(
            component_a=r.choice(refs),
            component_b=r.choice(refs),
            min_separation_mm=r.uniform(1.0, 40.0),
            tier=r.choice(["hard", "soft"]),
            weight=r.uniform(0.1, 5.0),
        )
        for _ in range(r.randint(0, 4))
    ]
    groups = []
    for _ in range(r.randint(0, 3)):
        comps = r.sample(refs, r.randint(2, 3))
        prox = [
            ProximityRule(
                component_a=a,
                component_b=b,
                max_distance_mm=r.uniform(5.0, 50.0),
                tier=r.choice(["hard", "soft"]),
            )
            for a, b in (r.sample(comps, 2) for _ in range(r.randint(0, 2)))
        ]
        groups.append(
            ComponentGroup(
                name=f"g{r.randint(1, 99)}",
                components=comps,
                max_spread_mm=r.uniform(10.0, 60.0),
                proximity_rules=prox,
            )
        )
    escapes = [
        EscapeClearance(
            component=r.choice(refs),
            clearance_mm=r.choice([None, r.uniform(2.0, 15.0)]),
            tier=r.choice(["hard", "soft"]),
        )
        for _ in range(r.randint(0, 3))
    ]
    corridors = [
        RoutingCorridor(
            name=f"c{i}",
            from_component=r.choice(refs),
            to_component=r.choice(refs),
            width_mm=r.uniform(1.0, 10.0),
            keep_clear=r.choice([True, False]),
            tier=r.choice(["hard", "soft"]),
        )
        for i in range(r.randint(0, 2))
    ]
    thermals = [
        ThermalConstraint(
            components=r.sample(refs, r.randint(1, 2)),
            prefer_edge=r.choice([True, False]),
            max_distance_from_edge_mm=r.uniform(5.0, 30.0),
        )
        for _ in range(r.randint(0, 2))
    ]
    return PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=80.0,
        component_spacing_rules=spacing,
        component_groups=groups,
        escape_clearances=escapes,
        routing_corridors=corridors,
        thermal_constraints=thermals,
    )


def _placements(rng: random.Random, refs: list[str]) -> dict:
    out = {}
    for ref in refs:
        if rng.random() < 0.6:
            out[ref] = (rng.uniform(-20.0, 120.0), rng.uniform(-20.0, 100.0))
    return out


def _both(constraints, board_bounds=None):
    o = _oracle.ConstraintReporter(constraints, board_bounds)
    s = ConstraintReporter(constraints, board_bounds)
    return o, s


# ---------------------------------------------------------------------------
# R1a — behavioural A/B: check() result lists, bit-identical.
# ---------------------------------------------------------------------------


class TestCheckDifferential:
    def test_empty_constraints_empty_report(self):
        o, s = _both(PlacementConstraints())
        or_, sr = o.check({}), s.check({})
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        assert len(sr.results) == 0  # empty-input semantics asserted, not assumed

    def test_empty_constraints_with_placements(self):
        o, s = _both(PlacementConstraints())
        placements = {"A": (1.0, 2.0), "B": (3.0, 4.0)}
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]

    def test_random_differential(self):
        rng = random.Random(0x3E3F0E)
        refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
        for case in range(120):
            constraints = _random_constraints(rng)
            bounds = None if case % 3 == 0 else (0.0, 0.0, 100.0, 80.0)
            o, s = _both(constraints, bounds)
            placements = _placements(rng, refs)
            or_, sr = o.check(placements), s.check(placements)
            assert [_result_key(r) for r in or_.results] == [
                _result_key(r) for r in sr.results
            ], f"check mismatch case={case}"
            # Result ORDER is part of the contract (rule order + placements iteration).
            assert [r.constraint_type for r in or_.results] == [
                r.constraint_type for r in sr.results
            ]

    def test_escape_corridor_violation_order_follows_placements(self):
        """Multi-violation results follow placements dict insertion order on BOTH sides."""
        constraints = PlacementConstraints(
            escape_clearances=[EscapeClearance(component="U1", clearance_mm=10.0, tier="hard")],
            routing_corridors=[
                RoutingCorridor(
                    name="path", from_component="A", to_component="B", width_mm=6.0, tier="hard"
                )
            ],
        )
        o, s = _both(constraints)
        placements = {
            "U1": (50.0, 50.0),
            "X1": (55.0, 50.0),
            "X2": (50.0, 58.0),
            "A": (0.0, 0.0),
            "B": (20.0, 0.0),
            "Y1": (10.0, 2.0),
            "Y2": (10.0, -2.0),
        }
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        # The multi-violation paths are actually exercised (not vacuous).
        assert any(r.constraint_type == "EscapeClearance" and r.status == ConstraintStatus.VIOLATED for r in sr.results)
        assert any(r.constraint_type == "RoutingCorridor" and r.status == ConstraintStatus.VIOLATED for r in sr.results)

    def test_dict_subclass_raising_getitem_raises_in_check(self):
        """A dict subclass whose ``__getitem__`` raises must surface that raise
        from ``check()``: the oracle reaches the value via ``placements[ref]``
        (Python-level ``__getitem__``), so the shim must not fall back to a
        pre-extracted C-level list of placement values, which would silently
        return a normal report. (Compiler-side raising-``__getitem__`` parity
        is covered in the compiler differential; this is the reporter half.)"""

        class RaisingDict(dict):
            def __getitem__(self, key):
                if key == "A":
                    raise RuntimeError("boom from __getitem__")
                return dict.__getitem__(self, key)

        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard")
            ]
        )
        o, s = _both(constraints)
        placements = RaisingDict({"A": (1.0, 2.0), "B": (3.0, 4.0)})
        try:
            o.check(placements)
        except Exception as oe:  # noqa: BLE001
            oracle_err = oe
        else:
            raise AssertionError("oracle check() did not raise")
        try:
            s.check(placements)
        except Exception as se:  # noqa: BLE001
            shim_err = se
        else:
            raise AssertionError(
                "shim check() did not raise (returned a normal report); "
                f"oracle raised {type(oracle_err).__name__}"
            )
        assert type(shim_err) is type(oracle_err)
        assert str(shim_err) == str(oracle_err)


class TestReportTextAndJsonDifferential:
    def test_empty_report_text(self):
        """Empty-input semantics for to_text: header + blank line + bare SUMMARY."""
        o, s = ConstraintReport(), ConstraintReport()
        assert o.to_text() == s.to_text()
        assert s.to_text() == "=== Constraint Satisfaction Report ===\n\nSUMMARY:"

    def test_empty_report_json(self):
        o, s = ConstraintReport(), ConstraintReport()
        assert o.to_json() == s.to_json()
        assert json.loads(s.to_json())["summary"]["total_constraints"] == 0

    def test_text_json_identical_on_random_checks(self):
        rng = random.Random(0xA11CE)
        refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
        for case in range(60):
            constraints = _random_constraints(rng)
            bounds = None if case % 2 == 0 else (0.0, 0.0, 100.0, 80.0)
            o, s = _both(constraints, bounds)
            placements = _placements(rng, refs)
            or_, sr = o.check(placements), s.check(placements)
            assert or_.to_text() == sr.to_text(), f"to_text mismatch case={case}"
            assert or_.to_json() == sr.to_json(), f"to_json mismatch case={case}"

    def test_hand_built_report_with_details(self):
        """Reports built by hand (not via check) with details must round-trip."""
        o = ConstraintReport(
            results=[
                ConstraintResult(
                    "ComponentSpacing",
                    ConstraintStatus.VIOLATED,
                    "hard",
                    ["A", "B"],
                    "Test violation",
                    actual_value=5.0,
                    expected_value=10.0,
                    details={"side": "left"},
                ),
                ConstraintResult(
                    "Proximity",
                    ConstraintStatus.SATISFIED,
                    "soft",
                    ["C", "D"],
                    "OK",
                ),
            ]
        )
        s = ConstraintReport(
            results=[
                ConstraintResult(
                    "ComponentSpacing",
                    ConstraintStatus.VIOLATED,
                    "hard",
                    ["A", "B"],
                    "Test violation",
                    actual_value=5.0,
                    expected_value=10.0,
                    details={"side": "left"},
                ),
                ConstraintResult(
                    "Proximity",
                    ConstraintStatus.SATISFIED,
                    "soft",
                    ["C", "D"],
                    "OK",
                ),
            ]
        )
        assert o.to_text() == s.to_text()
        assert o.to_json() == s.to_json()
        data = json.loads(s.to_json())
        assert data["violations"][0]["details"] == {"side": "left"}

    def test_hand_built_report_int_and_bool_leaves_json(self):
        """Hand-built reports with int/bool ``actual_value``/``expected_value``
        leaves must round-trip through ``to_json`` preserving the leaf TYPE:
        the oracle emits ``r.actual_value`` untouched, so ``json.dumps``
        renders ``5``/``true``, not ``5.0``/``1.0``. (check()-produced leaves
        are floats on both sides and are unaffected.) The shim's Rust json
        builder must marshal the original Python leaf through rather than
        re-emitting an f64-coerced value."""

        def make(cls, result_cls, status_enum):
            return cls(
                results=[
                    result_cls(
                        "ComponentSpacing",
                        status_enum.VIOLATED,
                        "hard",
                        ["A", "B"],
                        "int leaf",
                        actual_value=5,
                        expected_value=10,
                    ),
                    result_cls(
                        "Proximity",
                        status_enum.SATISFIED,
                        "soft",
                        ["C", "D"],
                        "bool leaf",
                        actual_value=True,
                        expected_value=False,
                    ),
                    result_cls(
                        "Thermal",
                        status_enum.WARNING,
                        "soft",
                        ["T"],
                        "float leaf",
                        actual_value=1.5,
                        expected_value=3,
                    ),
                    result_cls(
                        "RoutingCorridor",
                        status_enum.VIOLATED,
                        "hard",
                        ["X", "Y"],
                        "none leaf",
                    ),
                ]
            )

        o = make(_oracle.ConstraintReport, _oracle.ConstraintResult, _oracle.ConstraintStatus)
        s = make(ConstraintReport, ConstraintResult, ConstraintStatus)
        assert o.to_text() == s.to_text()
        assert o.to_json() == s.to_json()
        data = json.loads(s.to_json())
        # violations[0] (ComponentSpacing): int leaves stay int.
        assert type(data["violations"][0]["actual"]) is int
        assert data["violations"][0]["actual"] == 5
        assert type(data["violations"][0]["expected"]) is int
        assert data["violations"][0]["expected"] == 10
        # violations[1] (RoutingCorridor): None leaves stay None.
        assert data["violations"][1]["actual"] is None
        # warnings[0] (Thermal): float actual + int expected both preserved.
        assert data["warnings"][0]["actual"] == 1.5
        assert type(data["warnings"][0]["actual"]) is float
        assert type(data["warnings"][0]["expected"]) is int
        # all_results[1] (Proximity): bool leaves stay bool.
        assert data["all_results"][1]["actual"] is True
        assert type(data["all_results"][1]["actual"]) is bool
        assert data["all_results"][1]["expected"] is False

    def test_summary_counts(self):
        """Summary counts reflect hard/soft/satisfied splits exactly."""
        s = ConstraintReport(
            results=[
                ConstraintResult("A", ConstraintStatus.VIOLATED, "hard", ["X"], "m1"),
                ConstraintResult("B", ConstraintStatus.SATISFIED, "hard", ["X"], "m2"),
                ConstraintResult("C", ConstraintStatus.VIOLATED, "soft", ["X"], "m3"),
                ConstraintResult("D", ConstraintStatus.WARNING, "soft", ["X"], "m4"),
                ConstraintResult("E", ConstraintStatus.SKIPPED, "soft", ["X"], "m5"),
            ]
        )
        data = json.loads(s.to_json())
        assert data["summary"] == {
            "total_constraints": 5,
            "hard_satisfied": 1,
            "hard_total": 2,
            "soft_satisfied": 0,
            "soft_total": 3,
            "violations": 1,
            "warnings": 1,
        }
        text = s.to_text()
        assert "Hard: 1/2 satisfied" in text
        assert "Soft: 0/3 satisfied" in text
        assert "VIOLATIONS: 1" in text


class TestReportBoundaryDifferential:
    """Exact-boundary cases discriminating strict-vs-non-strict comparisons in
    the reporter checks. Added to close surviving mutants found by the
    anti-vacuity mutation campaign (M6 corridor, M11 spacing): random inputs
    almost never land exactly on a threshold."""

    def test_spacing_check_exact_threshold_satisfied(self):
        """dist == min_separation is SATISFIED (>=), not violated."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard")
            ]
        )
        o, s = _both(constraints)
        placements = {"A": (0.0, 0.0), "B": (10.0, 0.0)}  # dist exactly 10.0
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        assert sr.results[0].status == ConstraintStatus.SATISFIED
        assert sr.results[0].message == "ComponentSpacing: A - B (10.0mm ≥ 10.0mm)"

    def test_spacing_message_multi_decimal_threshold(self):
        """A multi-decimal threshold discriminates `py_float_str` from
        `{:.1}` in messages: str(10.25) == '10.25' but format('{:.1}',
        10.25) == '10.2' (mutant M5). An integral `.0` threshold like 10.0
        does NOT discriminate — both render '10.0'."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.25, tier="hard")
            ]
        )
        o, s = _both(constraints)
        placements = {"A": (0.0, 0.0), "B": (5.0, 0.0)}  # dist 5.0 < 10.25 -> violated
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        assert sr.results[0].message == "ComponentSpacing: A - B (5.0mm < 10.25mm)"

    def test_nan_placements_messages_byte_identical(self):
        """NaN placement coordinates must render in messages exactly as
        CPython's `%.1f` does ('nan'), not Rust Display's 'NaN' — and the
        divergence must not leak into to_text()/to_json(). NaN enters only
        through the placements dict (every constraint-side float is
        pydantic-bounded ge/gt=0, so NaN cannot ride a rule field); with NaN
        as the FIRST element of the group-spread positions list it survives
        py_min/py_max (first element is the running result), and a NaN
        component position makes the thermal edge distance NaN. The escape/
        corridor DISTANCE message sites are unreachable with NaN through
        check() (`NaN < x` is False, so no violation ever carries a NaN
        distance) — the shared `py_float_fmt_1` helper covers them anyway."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard"),
                ComponentSpacingRule(component_a="C", component_b="D", min_separation_mm=10.0, tier="soft"),
            ],
            component_groups=[
                ComponentGroup(
                    name="g",
                    components=["A", "B"],
                    max_spread_mm=30.0,
                    proximity_rules=[
                        ProximityRule(component_a="A", component_b="B", max_distance_mm=5.0, tier="soft")
                    ],
                ),
                # D first: its NaN x survives py_min/py_max as the running
                # first element, so the bounding-box diagonal is NaN.
                ComponentGroup(name="gn", components=["D", "C"], max_spread_mm=40.0),
            ],
            escape_clearances=[EscapeClearance(component="A", clearance_mm=8.0, tier="hard")],
            routing_corridors=[
                RoutingCorridor(name="path", from_component="A", to_component="B", width_mm=6.0, tier="hard")
            ],
            thermal_constraints=[
                ThermalConstraint(components=["T"], prefer_edge=True, max_distance_from_edge_mm=10.0)
            ],
        )
        o, s = _both(constraints, (0.0, 0.0, 100.0, 80.0))
        placements = {
            "A": (0.0, 0.0),
            "B": (float("nan"), 0.0),
            "C": (0.0, 0.0),
            "D": (float("nan"), 0.0),
            "T": (float("nan"), 5.0),
        }
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        assert or_.to_text() == sr.to_text()
        assert or_.to_json() == sr.to_json()
        msgs = [r.message for r in sr.results]
        # Pins CPython's %.1f rendering of NaN ('nan'), not Rust Display's 'NaN'.
        assert any("nanmm" in m for m in msgs), msgs
        assert all("NaN" not in m for m in msgs), msgs
        # The NaN-reaching message sites are all actually exercised (not vacuous).
        assert any(m.startswith("ComponentSpacing: A - B (nanmm") for m in msgs)
        assert any(m.startswith("Proximity: A - B (nanmm") for m in msgs)
        assert any(m.startswith("Thermal: T edge distance (nanmm") for m in msgs)
        assert any(m.startswith("GroupSpread: gn (nanmm") for m in msgs)
        # Status/actual/expected agree with the oracle even on the NaN rows.
        nan_rows = [
            (r.status.value, r.actual_value, r.expected_value)
            for r in sr.results
            if "nanmm" in r.message
        ]
        assert all(st == "violated" and ac != ac and ac is not None for st, ac, _ in nan_rows)

    def test_corridor_check_exact_half_width_clear(self):
        """dist == half_width is NOT a violation (strict <)."""
        constraints = PlacementConstraints(
            routing_corridors=[
                RoutingCorridor(
                    name="path", from_component="A", to_component="B", width_mm=6.0, tier="hard"
                )
            ]
        )
        o, s = _both(constraints)
        # Segment (0,0)-(20,0); component at (10, 3.0) -> dist exactly 3.0 == half.
        placements = {"A": (0.0, 0.0), "B": (20.0, 0.0), "X": (10.0, 3.0)}
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        assert sr.results[0].status == ConstraintStatus.SATISFIED
        # A hair inside is a violation.
        placements2 = dict(placements)
        placements2["X"] = (10.0, 2.999)
        or2, sr2 = o.check(placements2), s.check(placements2)
        assert [_result_key(r) for r in or2.results] == [_result_key(r) for r in sr2.results]
        assert sr2.results[0].status == ConstraintStatus.VIOLATED

    def test_proximity_check_exact_threshold_satisfied(self):
        """dist == max_distance is SATISFIED (<=), not violated."""
        constraints = PlacementConstraints(
            component_groups=[
                ComponentGroup(
                    name="g",
                    components=["A", "B"],
                    proximity_rules=[
                        ProximityRule(component_a="A", component_b="B", max_distance_mm=10.0, tier="soft")
                    ],
                )
            ]
        )
        o, s = _both(constraints)
        placements = {"A": (0.0, 0.0), "B": (10.0, 0.0)}
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        prox = [r for r in sr.results if r.constraint_type == "Proximity"][0]
        assert prox.status == ConstraintStatus.SATISFIED


class TestReportPropertiesDifferential:
    def test_properties_parity(self):
        """violations/warnings/satisfied/hard/soft filters match the oracle."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard"),
                ComponentSpacingRule(component_a="C", component_b="D", min_separation_mm=10.0, tier="soft"),
            ],
            component_groups=[
                ComponentGroup(name="g", components=["E", "F"], proximity_rules=[])
            ],
        )
        o, s = _both(constraints)
        placements = {"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (0.0, 0.0), "D": (5.0, 0.0)}
        or_, sr = o.check(placements), s.check(placements)
        for prop in ["violations", "warnings", "satisfied", "hard_results", "soft_results"]:
            assert [_result_key(r) for r in getattr(or_, prop)] == [
                _result_key(r) for r in getattr(sr, prop)
            ], prop
        assert or_.has_violations() == sr.has_violations()
