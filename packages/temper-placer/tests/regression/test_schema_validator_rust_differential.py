"""Differential test: metric schema validation kernel in Rust
(``temper_design_bundle_python.validate_schema``) vs the pinned Python oracle
(Wave 4, Phase 4 — regression slice).

``temper_placer/regression/schema_validator.py`` moves its validation
decision compute — the two-pass check (pass 1: every metric field must be
declared, first unknown in insertion order; pass 2: min/max/zero_is_valid
range checks in insertion order) — into ``temper-design-bundle``. The
pre-migration module is pinned verbatim as the oracle
(``_schema_validator_py_oracle.py``, commit ``0a29f15e3``).

Design boundaries, argued in the migrated module and
``packages/temper-design-bundle/VERIFICATION.md``:

- YAML loading and the schema-shape checks in ``SchemaValidator.__init__``
  stay Python (I/O + marshalling). The kernel operates on the parsed field
  table.
- The kernel returns a ``(field, reason_code)`` pair; the delegation module
  formats the exact message with Python ``str()`` on the ORIGINAL dict
  values (no-format ``str(float)`` is a Python library semantic — ``1.0``
  vs ``1`` — so int-vs-float leaves are type-carried Python-side).
- Iteration is over the metric dict's insertion order (a Vec, not a
  HashMap) — first-violation semantics must be preserved exactly.
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb

import tests.regression._schema_validator_py_oracle as _oracle

# Rust symbol under test — must exist or this file fails to collect (RED).
VALIDATE_SCHEMA = _tdb.validate_schema

from temper_placer.regression.schema_validator import (  # noqa: E402
    SchemaValidationError,
    SchemaValidator as ShimValidator,
)


def _schema_dict(rng):
    fields = {}
    for i in range(rng.randint(1, 5)):
        f = f"m{i}"
        spec = {}
        if rng.random() < 0.8:
            spec["min"] = rng.choice([0, 0.0, -10, -10.5, 42])
        if rng.random() < 0.8:
            spec["max"] = rng.choice([100, 100.0, 50.5, 100000])
        spec["zero_is_valid"] = rng.choice([True, False])
        fields[f] = spec
    return fields


def _metrics_dict(rng, field_names):
    d = {}
    for f in field_names:
        d[f] = rng.choice([0, 0.0, -1, 1.5, 42, 43.0, 99.9])
    return d


def _as_field_table(fields):
    out = []
    for name, spec in fields.items():
        out.append(
            (
                name,
                spec.get("min"),
                spec.get("max"),
                spec.get("zero_is_valid", True),
            )
        )
    return out


# ---------------------------------------------------------------------------
# R1a — differential
# ---------------------------------------------------------------------------


def test_differential_random(tmp_path):
    rng = random.Random(0x5A5A)
    for _ in range(400):
        fields = _schema_dict(rng)
        # metrics: mix of declared + a 30% chance of an unknown field
        names = list(fields) + (["_unknown_"] if rng.random() < 0.3 else [])
        metrics = _metrics_dict(rng, names)
        p = tmp_path / "schema.yaml"
        p.write_text("schema_version: 1\n" + _yaml(fields))
        oracle = _oracle.SchemaValidator(p)
        shim = ShimValidator(p)
        o_exc = None
        s_exc = None
        try:
            oracle.validate(metrics)
        except SchemaValidationError as e:
            o_exc = e
        try:
            shim.validate(metrics)
        except SchemaValidationError as e:
            s_exc = e
        if o_exc is None:
            assert s_exc is None, f"shim raised but oracle passed: {metrics}"
        else:
            assert s_exc is not None, f"shim passed but oracle raised: {metrics}"
            assert (s_exc.field, s_exc.reason, str(s_exc)) == (
                o_exc.field,
                o_exc.reason,
                str(o_exc),
            )


def _yaml(fields):
    lines = ["metrics:"]
    for name, spec in fields.items():
        lines.append(f"  {name}:")
        if "min" in spec:
            lines.append(f"    min: {spec['min']}")
        if "max" in spec:
            lines.append(f"    max: {spec['max']}")
        lines.append(f"    zero_is_valid: {str(spec['zero_is_valid']).lower()}")
    return "\n".join(lines) + "\n"


def test_differential_first_unknown_field(tmp_path):
    """Pass 1 (unknown-field sweep) runs before pass 2 (range checks): an
    unknown field raises even when an earlier known field is also out of
    range."""
    p = tmp_path / "schema.yaml"
    p.write_text(_yaml({"m0": {"min": 0, "max": 100, "zero_is_valid": True}}))
    oracle = _oracle.SchemaValidator(p)
    shim = ShimValidator(p)
    metrics = {"m0": 500, "mystery": 1.0}
    with pytest.raises(SchemaValidationError) as oe:
        oracle.validate(metrics)
    with pytest.raises(SchemaValidationError) as se:
        shim.validate(metrics)
    assert se.value.field == "mystery"
    assert (se.value.field, se.value.reason, str(se.value)) == (
        oe.value.field,
        oe.value.reason,
        str(oe.value),
    )
    assert "unknown field" in str(se.value)


def test_differential_int_vs_float_message_leaves(tmp_path):
    """int and float leaves in the metrics/schema dicts render differently
    in the message (str(int) vs str(float)) — the shim must type-carry."""
    p = tmp_path / "schema.yaml"
    p.write_text(_yaml({"m0": {"min": 0.0, "max": 10.0, "zero_is_valid": True}}))
    oracle = _oracle.SchemaValidator(p)
    shim = ShimValidator(p)
    with pytest.raises(SchemaValidationError) as oe:
        oracle.validate({"m0": 5})
    with pytest.raises(SchemaValidationError) as se:
        shim.validate({"m0": 5})
    assert (se.value.field, se.value.reason, str(se.value)) == (
        oe.value.field,
        oe.value.reason,
        str(oe.value),
    )
    assert "value 5 is below minimum 0.0" in str(se.value)


def test_differential_zero_is_valid_false(tmp_path):
    p = tmp_path / "schema.yaml"
    p.write_text(_yaml({"m0": {"min": 42.0, "max": 42.0, "zero_is_valid": False}}))
    oracle = _oracle.SchemaValidator(p)
    shim = ShimValidator(p)
    for metrics in ({"m0": 0.0}, {"m0": 0}, {"m0": 42.0}):
        with pytest.raises(SchemaValidationError) as oe:
            oracle.validate(metrics)
        with pytest.raises(SchemaValidationError) as se:
            shim.validate(metrics)
        assert (se.value.field, se.value.reason, str(se.value)) == (
            oe.value.field,
            oe.value.reason,
            str(oe.value),
        )
    # 42.0 is within [42.0, 42.0] and non-zero -> passes
    oracle.validate({"m0": 42.0})


def test_differential_valid_metrics_pass(tmp_path):
    p = tmp_path / "schema.yaml"
    p.write_text(_yaml({"m0": {"min": 0, "max": 100, "zero_is_valid": True}}))
    oracle = _oracle.SchemaValidator(p)
    shim = ShimValidator(p)
    oracle.validate({"m0": 50.0})
    shim.validate({"m0": 50.0})
    oracle.validate({"m0": 0})
    shim.validate({"m0": 0})


def test_differential_kernel_direct():
    """The kernel itself, driven directly against the oracle's decision."""
    schema = _as_field_table(
        {"wall_time_ms": {"min": 0, "max": 100, "zero_is_valid": True}}
    )
    assert VALIDATE_SCHEMA([("wall_time_ms", 50.0)], schema) is None
    assert VALIDATE_SCHEMA([("wall_time_ms", -1.0)], schema) == ("wall_time_ms", "below_min")
    assert VALIDATE_SCHEMA([("wall_time_ms", 101.0)], schema) == ("wall_time_ms", "above_max")
    schema2 = _as_field_table(
        {"x": {"min": 1, "max": 10, "zero_is_valid": False}}
    )
    assert VALIDATE_SCHEMA([("x", 0.0)], schema2) == ("x", "zero_invalid")
    assert VALIDATE_SCHEMA([("y", 1.0)], schema2) == ("y", "unknown")


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (>=3, honestly bounded)
# ---------------------------------------------------------------------------


def test_mr1_first_violation_in_insertion_order(tmp_path):
    """Only the first failing metric (in dict insertion order) is reported —
    later violations are not visible."""
    p = tmp_path / "schema.yaml"
    p.write_text(_yaml({"m0": {"min": 0, "max": 100, "zero_is_valid": True}}))
    oracle = _oracle.SchemaValidator(p)
    shim = ShimValidator(p)
    with pytest.raises(SchemaValidationError) as se:
        shim.validate({"m0": -5, "m1": 999})
    assert se.value.field == "m0"
    with pytest.raises(SchemaValidationError) as oe:
        oracle.validate({"m0": -5, "m1": 999})
    assert (se.value.field, str(se.value)) == (oe.value.field, str(oe.value))
    # reorder: m1 is now first and unknown
    with pytest.raises(SchemaValidationError) as se2:
        shim.validate({"m1": 999, "m0": -5})
    assert se2.value.field == "m1"


def test_mr2_passing_metric_addition_is_idempotent():
    """Adding a metric that satisfies its constraints to a passing set keeps
    the set passing (no spurious failure from a valid addition)."""
    schema = _as_field_table({"a": (0.0, 10.0, True), "b": (0.0, 10.0, True)})
    assert VALIDATE_SCHEMA([("a", 5.0)], schema) is None
    assert VALIDATE_SCHEMA([("a", 5.0), ("b", 5.0)], schema) is None


def test_mr3_zero_is_valid_negation_boundary():
    """zero_is_valid True vs False is the ONLY thing distinguishing a zero
    metric's outcome — the same metric with zero_is_valid True passes."""
    schema_true = _as_field_table({"x": (1.0, 10.0, True)})
    schema_false = _as_field_table({"x": (1.0, 10.0, False)})
    assert VALIDATE_SCHEMA([("x", 0.0)], schema_true) is None
    assert VALIDATE_SCHEMA([("x", 0.0)], schema_false) == ("x", "zero_invalid")


def test_mr4_min_max_boundary_inclusive():
    """value == min or value == max passes; one ulp beyond fails."""
    schema = _as_field_table({"x": (1.0, 10.0, True)})
    assert VALIDATE_SCHEMA([("x", 1.0)], schema) is None
    assert VALIDATE_SCHEMA([("x", 10.0)], schema) is None
    import struct
    above_max = struct.unpack("d", struct.pack("d", 10.0))[0]
    below_min = struct.unpack("d", struct.pack("d", 1.0))[0]
    assert VALIDATE_SCHEMA([("x", above_max + 1e-15)], schema) == ("x", "above_max")
    assert VALIDATE_SCHEMA([("x", below_min - 1e-15)], schema) == ("x", "below_min")


# ---------------------------------------------------------------------------
# R1c — non-vacuous properties (>=5)
# ---------------------------------------------------------------------------


def test_prop1_unknown_field_reason():
    assert VALIDATE_SCHEMA([("nope", 1.0)], _as_field_table({})) == ("nope", "unknown")


def test_prop2_below_min_reason():
    assert VALIDATE_SCHEMA(
        [("m", 4.9)], _as_field_table({"m": (5.0, 10.0, True)})
    ) == ("m", "below_min")


def test_prop3_above_max_reason():
    assert VALIDATE_SCHEMA(
        [("m", 10.1)], _as_field_table({"m": (5.0, 10.0, True)})
    ) == ("m", "above_max")


def test_prop4_no_min_no_max_is_unconstrained():
    # None min/max -> no range check; only zero_is_valid applies
    schema = _as_field_table({"m": (None, None, True)})
    assert VALIDATE_SCHEMA([("m", -1e9)], schema) is None
    assert VALIDATE_SCHEMA([("m", 1e9)], schema) is None


def test_prop5_empty_metrics_pass():
    assert VALIDATE_SCHEMA([], _as_field_table({"m": (0.0, 10.0, False)})) is None


def test_prop6_zero_is_valid_default_true():
    """A schema field without a zero_is_valid key defaults to True."""
    # (min, max, zero_is_valid) — the shim marshals the default; direct kernel
    # call with an explicit True is the same decision
    assert VALIDATE_SCHEMA([("m", 0.0)], _as_field_table({"m": (1.0, 10.0, True)})) is None


def test_prop7_below_min_precedes_zero_check():
    """A negative zero-value reports below_min, not zero_invalid (check
    order: min, max, then zero_is_valid)."""
    schema = _as_field_table({"m": (1.0, 10.0, False)})
    assert VALIDATE_SCHEMA([("m", 0.0)], schema) == ("m", "below_min")
    schema2 = _as_field_table({"m": (0.0, 10.0, False)})
    assert VALIDATE_SCHEMA([("m", 0.0)], schema2) == ("m", "zero_invalid")
