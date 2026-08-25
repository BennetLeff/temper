"""FREEZE spec: ``regression/schema_validator.py``'s validation-decision
kernel (``validate_schema``) (U4 oracle retirement, batch 1).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/regression/_schema_validator_py_oracle.py
  VERBATIM copy of the pre-migration ``schema_validator.py`` as of commit
  ``0a29f15e3``; the oracle file itself was created (and never touched
  again) at ``de1f6ac9d`` — unchanged for 1489 commits as of this freeze
  (measured 2026-08-20 against ``origin/main``), far past the plan's
  10-consecutive-commit R19-shaped retirement bar.

Kernel:
  packages/temper-design-bundle/src/schema_validator.rs :: validate_schema
  The two-pass validation decision (pass 1: unknown-field sweep in
  insertion order; pass 2: min/max/zero_is_valid range checks in insertion
  order), returning ``(field, reason_code)`` or ``None``. A pure function
  over ``Vec<(String, f64)>`` / ``Vec<(String, Option<f64>, Option<f64>,
  bool)>`` — no pyo3 objects in or out (only the ``PyResult`` wrapper) — so
  the golden-vector test is plain Rust data + an assert loop, exactly the
  copper_reach FREEZE model.

Differential (retired by this same change):
  packages/temper-placer/tests/regression/test_schema_validator_rust_differential.py
  The oracle-comparison tests (``test_differential_*`` and the kernel-only
  MR/prop blocks) are removed; the file is reduced to its
  ``test_shipped_module_delegates_to_rust`` wiring check, matching the
  copper_reach precedent. ``schema_validator.py`` itself is NOT deleted:
  it remains the shim that formats the kernel's reason codes into exact
  messages with Python ``str()`` (int-vs-float type-carrying), and its
  import path is pinned inside the VERBATIM oracle
  ``tests/pipeline/_metrics_observer_py_oracle.py`` (whose bytes cannot be
  edited) — see ``.orphaned-python-module-inventory``.

Reason-code mapping (why run_oracle maps, and why that is not a
re-transcription): the oracle raises ``SchemaValidationError(field, reason)``
where ``reason`` is the formatted MESSAGE (``"value 5 is below minimum
10.0"``), while the kernel returns short reason CODES (``"below_min"``).
The code<->message mapping is the delegation shim's own contract
(``schema_validator.py::SchemaValidator.validate`` maps codes to messages
via Python ``str()`` on the ORIGINAL dict values); the freeze spec merely
classifies the oracle's message back into the code the shim would produce,
using the same four-way classification the shim owns. Messages themselves
are Python-``str()``-semantics and stay Python-side by design — they are
not part of the frozen decision.

Corpus tags are grounded in the pinned oracle itself: ``_tagged_case``
runs the oracle (via ``run_oracle``) at generation time, so the non-vacuity
measurement reflects the oracle's true decisions, never a hand-written
re-implementation of its two-pass logic.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: a metrics-dict validation gate for pipeline
    observability, not creepage/clearance/via-keepout geometry (those live
    in temper-drc-rs and are explicitly excluded from this batch).
  - No host-facility or entropy dependency: pure f64 comparisons over
    small Vecs, first-violation semantics, three reason codes plus unknown.
  - Input domain (a short metrics list + a short schema field table) is
    small and well enumerable — exactly FREEZE's "enumerable or samplable"
    criterion.

Reproduction / regeneration note: ``run_oracle`` below drives the PINNED
oracle module's own ``SchemaValidator`` (writing the schema field table to
a temp YAML file, exactly the differential's ``_yaml`` convention) and
classifies its exception into the shim's reason code, so the frozen corpus
is byte-for-byte the oracle's decision, not a re-transcription of its
two-pass logic (transcribing it here would risk the exact "two copies of
the same bug" failure the plan's oracle-disposition table warns against).
Once this spec has been run and the oracle file deleted (which happens in
the same commit), re-running this generator will fail with an import error
by design — the frozen corpus is meant to be extended, if ever, by
reviving the oracle from git history
(`git show de1f6ac9d:packages/temper-placer/tests/regression/
_schema_validator_py_oracle.py`) for that one session, not by leaving a
live copy around indefinitely (which would defeat the retirement).
"""

from __future__ import annotations

import importlib
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib.oracle_freeze import (  # noqa: E402
    FreezeCase,
    FreezeSpec,
    NonVacuityCheck,
    SplitMix64,
    rust_f64_literal,
)

_PLACER_TESTS_ROOT = Path(__file__).resolve().parent.parent.parent / "packages" / "temper-placer"


def _oracle_module():
    """Import the pinned oracle.

    Expected to fail once the oracle has been retired (this spec's own
    first run deletes it in the same commit) — see the module docstring's
    "Reproduction / regeneration note". Raises a clear, actionable error
    rather than a bare ``ModuleNotFoundError`` so `--check`/regeneration
    attempts after retirement fail with an explanation instead of a stack
    trace.
    """
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    try:
        return importlib.import_module("tests.regression._schema_validator_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show de1f6ac9d:packages/temper-placer/tests/regression/"
            "_schema_validator_py_oracle.py > packages/temper-placer/tests/regression/"
            "_schema_validator_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


def _code_for(message: str) -> str:
    """Classify the oracle's formatted reason MESSAGE back into the reason
    CODE the delegation shim would produce — the shim's own four-way map,
    inverted. See the module docstring's "Reason-code mapping" note."""
    if "unknown field" in message:
        return "unknown"
    if "below minimum" in message:
        return "below_min"
    if "exceeds maximum" in message:
        return "above_max"
    if "zero_is_valid is false" in message:
        return "zero_invalid"
    raise AssertionError(f"unrecognized oracle reason message: {message!r}")


def _tags_for(metrics, schema, outcome) -> frozenset[str]:
    tags: set[str] = set()
    if not metrics:
        tags.add("empty_metrics")
    values = [v for _, v in metrics]
    if any(v == 0 or v == 0.0 for v in values):
        tags.add("zero_value")
    if any(isinstance(v, float) and math.isnan(v) for v in values):
        tags.add("nan_value")
    if any(mn is None and mx is None for _, mn, mx, _ in schema):
        tags.add("unconstrained")
    if any(mn is None and mx is not None for _, mn, mx, _ in schema):
        tags.add("no_min")
    if any(mn is not None and mx is None for _, mn, mx, _ in schema):
        tags.add("no_max")
    if outcome is None:
        tags.add("pass")
    else:
        _field, code = outcome
        tags.add(code)
        if code == "unknown":
            tags.add("pass1_unknown")
    # Exact-boundary values (value == min or value == max) present?
    lookup = {name: (mn, mx, zv) for name, mn, mx, zv in schema}
    for name, value in metrics:
        if name in lookup:
            mn, mx, _ = lookup[name]
            if (mn is not None and value == mn) or (mx is not None and value == mx):
                tags.add("exact_boundary")
    return frozenset(tags)


def _run_oracle_arm(validator, metrics):
    """Run one arm and return (field, code) on failure, None on pass —
    the oracle's own SchemaValidationError carries .field; the code is
    classified from the message via the shim's own map (see docstring)."""
    try:
        validator.validate(metrics)
    except Exception as e:  # noqa: BLE001 — the oracle's own error class
        return (getattr(e, "field", None), _code_for(getattr(e, "reason", str(e))))
    return None


def _schema_yaml(schema: list[tuple[str, object, object, bool]]) -> str:
    """Render a schema field table as the metrics_schema.yaml shape the
    oracle's SchemaValidator parses (the differential's own _yaml helper)."""
    lines = ["metrics:"]
    for name, mn, mx, zv in schema:
        lines.append(f"  {name}:")
        if mn is not None:
            lines.append(f"    min: {mn}")
        if mx is not None:
            lines.append(f"    max: {mx}")
        lines.append(f"    zero_is_valid: {str(zv).lower()}")
    return "\n".join(lines) + "\n"


def run_oracle(case_input: dict):
    """Drive the pinned oracle's own ``SchemaValidator`` against a temp
    YAML schema and return the ``(field, reason_code)`` decision (or None
    on pass) — the exact decision the Rust kernel must reproduce."""
    oracle = _oracle_module()
    metrics = dict(case_input["metrics"])
    schema = case_input["schema"]
    with tempfile.TemporaryDirectory() as td:
        schema_path = Path(td) / "schema.yaml"
        schema_path.write_text(_schema_yaml(schema))
        validator = oracle.SchemaValidator(schema_path)
        return _run_oracle_arm(validator, metrics)


def _tagged_case(name: str | None, metrics, schema):
    """Build a FreezeCase whose tags are grounded in the PINNED ORACLE's own
    outcome (not a re-transcription): gen_cases runs while the oracle still
    exists, so the corpus's non-vacuity measurement reflects the oracle's
    true decisions. ``run_freeze`` re-runs the oracle for the output."""
    outcome = run_oracle({"metrics": metrics, "schema": schema})
    tags = _tags_for(metrics, schema, outcome)
    if name is not None:
        tags = tags | {f"named:{name}"}
    return FreezeCase(input={"metrics": metrics, "schema": schema}, tags=tags)


def _curated_cases() -> list[FreezeCase]:
    cases: list[tuple[str, list[tuple[str, float]], list[tuple[str, object, object, bool]]]] = [
        ("valid_pass", [("wall_time_ms", 50.0)], [("wall_time_ms", 0, 100, True)]),
        ("below_min", [("wall_time_ms", -1.0)], [("wall_time_ms", 0, 100, True)]),
        ("above_max", [("wall_time_ms", 101.0)], [("wall_time_ms", 0, 100, True)]),
        ("exactly_min_passes", [("wall_time_ms", 0.0)], [("wall_time_ms", 0, 100, True)]),
        ("exactly_max_passes", [("wall_time_ms", 100.0)], [("wall_time_ms", 0, 100, True)]),
        ("zero_invalid", [("x", 0.0)], [("x", 0, 10, False)]),
        ("zero_valid_passes", [("x", 0.0)], [("x", 0, 10, True)]),
        ("unknown_field", [("nope", 1.0)], [("x", 0, 10, True)]),
        ("empty_metrics_pass", [], [("x", 0, 10, False)]),
        ("unconstrained_passes", [("m", -1e9)], [("m", None, None, True)]),
        ("no_min_only", [("m", -1e9)], [("m", None, 0.0, True)]),
        ("no_max_only", [("m", 1e9)], [("m", 0.0, None, True)]),
        (
            "pass1_unknown_beats_range",
            [("m0", -5.0), ("m1", 999.0)],
            [("m0", 0, 100, True)],
        ),
        (
            "insertion_order_first_violation",
            [("a", 500.0), ("b", 50.0)],
            [("a", 0, 100, True), ("b", 0, 100, True)],
        ),
        ("below_min_precedes_zero", [("m", 0.0)], [("m", 1.0, 10.0, False)]),
        ("nan_value_passes", [("m", math.nan)], [("m", 0, 10, True)]),
        ("negative_in_range", [("m", -9.5)], [("m", -10, 10, True)]),
        ("ulp_above_max", [("m", 10.0 + 1e-15)], [("m", 1.0, 10.0, True)]),
        ("int_leaf_below_float_min", [("m", 5)], [("m", 10.0, 20.0, True)]),
        ("zero_at_pinned_min_invalid", [("m", 0.0)], [("m", 0.0, 0.0, False)]),
        ("high_max_pass", [("m", 100000)], [("m", 0, 100000, True)]),
        ("fractional_min", [("m", 1.5)], [("m", 0.5, 2.5, True)]),
        ("below_fractional_min", [("m", 0.4)], [("m", 0.5, 2.5, True)]),
        (
            "multiple_metrics_one_bad",
            [("a", 5.0), ("b", 500.0)],
            [("a", 0, 10, True), ("b", 0, 10, True)],
        ),
    ]
    return [_tagged_case(name, metrics, schema) for name, metrics, schema in cases]


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    min_choices = [0, 0.0, -10, -10.5, 42, None]
    max_choices = [100, 100.0, 50.5, 100000, None]
    value_choices = [0, 0.0, -1, 1.5, 42, 43.0, 99.9, 5.0, 100.0, -10.0]
    out: list[FreezeCase] = []
    for _ in range(n):
        n_fields = rng.range_i64(1, 5)
        schema: list[tuple[str, object, object, bool]] = []
        for i in range(n_fields):
            mn = min_choices[rng.index(len(min_choices))]
            mx = max_choices[rng.index(len(max_choices))]
            zv = rng.boolean()
            schema.append((f"m{i}", mn, mx, zv))
        names = [s[0] for s in schema]
        if rng.index(100) < 30:
            names = names + ["_unknown_"]
        metrics: list[tuple[str, float]] = []
        for name in names:
            v = value_choices[rng.index(len(value_choices))]
            if rng.index(20) == 0:
                v = math.nan  # NaN must be present, not a rare fluke
            metrics.append((name, v))
        out.append(_tagged_case(None, metrics, schema))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(80, seed=0x5C4A3A_FA11ED)


def _render_f64_opt(x) -> str:
    return "None" if x is None else f"Some({rust_f64_literal(float(x))})"


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `validate_schema` (FREEZE, U4/U5).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec schema_validator`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/schema_validator.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    // Frozen cases are pinned oracle output; the module sits where the")
    lines.append("    // generator emits it, and unwrapping a frozen-known-Ok result is the")
    lines.append("    // assertion, not an oversight.")
    lines.append("    #[allow(clippy::items_after_test_module, clippy::unwrap_used)]")
    lines.append("    mod frozen_tests {")
    lines.append("        use super::*;")
    lines.append("")
    lines.append("        struct FrozenSchemaValidatorCase {")
    lines.append("            metrics: &'static [(&'static str, f64)],")
    lines.append("            schema: &'static [(&'static str, Option<f64>, Option<f64>, bool)],")
    lines.append("            expected: Option<(&'static str, &'static str)>,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_SCHEMA_VALIDATOR_GOLDEN: &[FrozenSchemaValidatorCase] = &[")
    for case, output in results:
        ci = case.input
        metrics_rs = ", ".join(
            f'("{n}", {rust_f64_literal(float(v))})' for n, v in ci["metrics"]
        )
        schema_rs = ", ".join(
            f'("{n}", {_render_f64_opt(mn)}, {_render_f64_opt(mx)}, {str(zv).lower()})'
            for n, mn, mx, zv in ci["schema"]
        )
        if output is None:
            expected_rs = "None"
        else:
            field, code = output
            expected_rs = f'Some(("{field}", "{code}"))'
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenSchemaValidatorCase {")
        lines.append(f"                metrics: &[{metrics_rs}],")
        lines.append(f"                schema: &[{schema_rs}],")
        lines.append(f"                expected: {expected_rs},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_schema_validator_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_SCHEMA_VALIDATOR_GOLDEN {")
    lines.append("                let got = validate_schema(")
    lines.append(
        "                    case.metrics.iter().map(|(n, v)| (n.to_string(), *v)).collect(),"
    )
    lines.append(
        "                    case.schema.iter()"
        ".map(|(n, mn, mx, zv)| (n.to_string(), *mn, *mx, *zv)).collect(),"
    )
    lines.append("                )")
    lines.append("                .unwrap();")
    lines.append(
        "                let want = case.expected.map(|(f, r)| (f.to_string(), r.to_string()));"
    )
    lines.append('                assert_eq!(got, want, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable. Mirrors the")
    lines.append("        /// coverage-guard convention in creepage_check.rs / via_clearance.rs (PR")
    lines.append("        /// #1007), property_campaigns.rs's IPC-2221 bracket guard, and")
    lines.append("        /// copper_reach.rs's own frozen-corpus guard.")
    lines.append("        #[test]")
    lines.append("        fn frozen_schema_validator_corpus_is_non_vacuous() {")
    lines.append("            let n = FROZEN_SCHEMA_VALIDATOR_GOLDEN.len() as u32;")
    lines.append(
        "            let count = |tag: &str| FROZEN_SCHEMA_VALIDATOR_GOLDEN.iter()."
        "filter(|c| c.tags.contains(&tag)).count() as u32;"
    )
    for nvc in _NON_VACUITY:
        if nvc.min_count:
            lines.append(
                f'            assert!(count("{nvc.tag}") >= {nvc.min_count}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {nvc.min_count}) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
        else:
            pct = int(round(nvc.min_fraction * 100))
            lines.append(
                f'            assert!(count("{nvc.tag}") * 100 >= n * {pct}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {pct}%) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
    lines.append("        }")
    lines.append("    }")
    return "\n".join(lines)


_NON_VACUITY = [
    NonVacuityCheck(
        tag="pass",
        description="the pass (None) outcome must be well represented, not a rare fluke",
        min_fraction=0.25,
    ),
    NonVacuityCheck(
        tag="below_min",
        description="the below-min branch must be exercised",
        min_count=8,
    ),
    NonVacuityCheck(
        tag="above_max",
        description="the above-max branch must be exercised",
        min_count=8,
    ),
    NonVacuityCheck(
        tag="unknown",
        description="the pass-1 unknown-field branch must be exercised",
        min_count=6,
    ),
    NonVacuityCheck(
        tag="zero_invalid",
        description="the zero_is_valid=False branch must be exercised",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="empty_metrics",
        description="the empty-metrics vacuous-pass branch must be exercised",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="nan_value",
        description="NaN metric values (which pass every range check) must be exercised",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="exact_boundary",
        description="value == min / value == max inclusive boundaries must be exercised",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="pass1_unknown",
        description="pass 1 must run before pass 2 (unknown beats range) -- the ordering contract",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="unconstrained",
        description="a field with neither min nor max must be exercised",
        min_count=3,
    ),
]


SPEC = FreezeSpec(
    name="schema_validator",
    description=(
        "regression/schema_validator.py::validate_schema -- the two-pass metrics "
        "validation decision (unknown-field sweep, then min/max/zero_is_valid "
        "range checks in insertion order)."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/regression/_schema_validator_py_oracle.py, "
        "VERBATIM from pre-migration commit 0a29f15e3, unchanged 1489 commits "
        "as of freeze (created de1f6ac9d)"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/schema_validator.rs :: validate_schema"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/schema_validator.rs",
    insert_before_marker="/// Register the kernel on the `temper_design_bundle_python` module.",
)
