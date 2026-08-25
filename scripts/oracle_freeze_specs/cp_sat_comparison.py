"""FREEZE spec: ``regression/cp_sat_comparison.py``'s portable compute
(``compare_metric_dicts`` parity gate) (U4 oracle retirement, batch 4).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/regression/_cp_sat_comparison_py_oracle.py
  VERBATIM copy of the pre-migration ``cp_sat_comparison.py`` as of commit
  ``0a29f15e3``; unchanged since creation — far past the plan's
  10-consecutive-commit R19-shaped retirement bar.

Kernel:
  packages/temper-design-bundle/src/cp_sat_comparison.rs ::
  compare_metric_maps + parity_summary
  The per-metric Pareto-style gate (clearance/thermal higher-is-better with
  a 1e-9 slack; the wirelength context metric lower-is-better within 5%)
  plus the aggregate verdict/summary composition. A pure
  ``(HashMap<String,String>, HashMap<String,String>, &str) ->
  Result<Vec<MetricComparisonRow>, FloatCoerceError>`` function — no pyo3
  objects in or out — so the golden-vector test is plain Rust data + an
  assert loop, exactly the copper_reach FREEZE model. The deliberate
  Python ``float("...")`` coercion semantics for string leaves (including
  CPython's ValueError text and inf/nan spellings) are reproduced by the
  kernel's ``py_float_str`` and pinned here via string-valued corpus leaves.

Differential (retired by this same change):
  packages/temper-placer/tests/regression/test_cp_sat_comparison_rust_differential.py
  The oracle-comparison tests are removed; the file is reduced to its
  wiring check, matching the copper_reach precedent. The production shim
  ``cp_sat_comparison.py`` itself stays: its public API (the two
  dataclasses + ``compare_metric_dicts``) is consumed by the promotion
  gate, and the pyo3 adapter owns the non-string-KEY TypeError class that
  cannot exist in the plain-map core by construction.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: a promotion-gate parity heuristic, not
    creepage/clearance/via-keepout geometry.
  - No host-facility or entropy dependency: pure map comparison +
    deterministic f64 arithmetic + fixed-format string rendering.
  - Input domain (two small string-valued score maps) is small and
    enumerable — exactly FREEZE's criterion.

Reproduction / regeneration note: ``run_oracle`` below drives the PINNED
oracle module's own ``compare_metric_dicts`` so the frozen corpus is
byte-for-byte the oracle's output. Once this spec has been run and the
oracle deleted (same commit), re-running the generator fails with an
actionable import error by design — revive from git history for that one
session only.
"""

from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib.oracle_freeze import (  # noqa: E402
    FreezeCase,
    FreezeSpec,
    NonVacuityCheck,
    SplitMix64,
)

_PLACER_TESTS_ROOT = Path(__file__).resolve().parent.parent.parent / "packages" / "temper-placer"


def _oracle_module():
    """Import the pinned oracle (fails with an actionable error post-retirement)."""
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    try:
        return importlib.import_module(
            "tests.regression._cp_sat_comparison_py_oracle"
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - post-retirement path
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first "
            "via `git log --diff-filter=D -- "
            "packages/temper-placer/tests/regression/_cp_sat_comparison_py_oracle.py` "
            "to find the deleting commit and `git show <before>:<path>` to restore it, "
            "run this generator, then discard the revived file again."
        ) from exc


WIRELENGTH = "total_manhattan_wirelength"


def _num_tag(v) -> str:
    if isinstance(v, bool):
        return "bool_leaf"
    if isinstance(v, int):
        return "int_leaf"
    if isinstance(v, float):
        if math.isnan(v):
            return "nan_leaf"
        if math.isinf(v):
            return "inf_leaf"
        return "float_leaf"
    if isinstance(v, str):
        try:
            f = float(v)
        except ValueError:
            return "non_numeric_str"
        if math.isnan(f):
            return "nan_leaf"  # the string spells a NaN that float() yields
        if math.isinf(f):
            return "inf_leaf"  # the string spells an infinity
        if math.isnan(f) or f != f:
            return "nan_str"
        return "numeric_str"
    return "other_leaf"


def _tags_for(cand: dict, base: dict, ctx_metric_present: bool) -> frozenset[str]:
    tags: set[str] = set()
    all_vals = list(cand.values()) + list(base.values())
    for v in all_vals:
        tags.add(_num_tag(v))
    keys_c, keys_b = set(cand), set(base)
    if keys_c - keys_b:
        tags.add("candidate_only_key")
    if keys_b - keys_c:
        tags.add("baseline_only_key")
    if not cand and not base:
        tags.add("both_empty")
    if WIRELENGTH in (keys_c & keys_b):
        tags.add("wirelength_in_intersection")
    if ctx_metric_present:
        tags.add("context_case")
    if cand.get(WIRELENGTH) == 0 or base.get(WIRELENGTH) == 0:
        tags.add("zero_baseline_context")
    return frozenset(tags)


_CURATED: list[tuple[str, dict, dict]] = [
    ("empty_both", {}, {}),
    ("single_equal", {"m": 1.5}, {"m": 1.5}),
    ("candidate_higher", {"m": 2.0}, {"m": 1.0}),
    ("candidate_lower_epsilon_pass", {"m": 1.0 - 5e-10}, {"m": 1.0}),
    ("candidate_lower_real_fail", {"m": 0.9}, {"m": 1.0}),
    ("clearance_style_keys", {"clearance_3mm": 4.0, "clearance_6mm": 8.0},
     {"clearance_3mm": 4.0, "clearance_6mm": 9.0}),
    ("thermal_score_pass", {"thermal_score": 10.0}, {"thermal_score": 9.999999999}),
    ("thermal_score_fail", {"thermal_score": 9.0}, {"thermal_score": 10.0}),
    # Wirelength context cases: lower is better within 5%
    ("wirelength_within_tolerance", {WIRELENGTH: 104.0}, {WIRELENGTH: 100.0}),
    ("wirelength_at_tolerance_edge", {WIRELENGTH: 105.0}, {WIRELENGTH: 100.0}),
    ("wirelength_outside_tolerance", {WIRELENGTH: 106.0}, {WIRELENGTH: 100.0}),
    ("wirelength_improving", {WIRELENGTH: 95.0}, {WIRELENGTH: 100.0}),
    ("wirelength_zero_baseline_candidate_zero", {WIRELENGTH: 0.0}, {WIRELENGTH: 0}),
    ("wirelength_zero_baseline_candidate_pos", {WIRELENGTH: 1.0}, {WIRELENGTH: 0}),
    ("wirelength_zero_baseline_candidate_neg", {WIRELENGTH: -1.0}, {WIRELENGTH: 0}),
    # String-number coercion (the oracle's float("...") semantics)
    ("numeric_str_leaves", {"m": "2.5"}, {"m": "1.5"}),
    ("numeric_str_int_spelling", {"m": "3"}, {"m": "4"}),
    ("numeric_str_inf", {"m": "inf"}, {"m": "1.0"}),
    ("numeric_str_neg_inf", {"m": "-inf"}, {"m": "1.0"}),
    ("numeric_str_nan", {"m": "nan"}, {"m": "1.0"}),
    ("numeric_str_scientific", {"m": "1e3"}, {"m": "500"}),
    ("numeric_str_whitespace", {"m": " 2.5 "}, {"m": "1.5"}),
    ("numeric_str_underscore", {"m": "1_000"}, {"m": "999"}),
    # Disjoint-key shapes
    ("candidate_only_key", {"only_c": 1.0, "shared": 2.0}, {"shared": 1.0}),
    ("baseline_only_key", {"shared": 2.0}, {"only_b": 1.0, "shared": 1.0}),
    # Bool / int leaves (float(True) == 1.0 in the oracle's float() call;
    # bools arrive as real bools through the pyo3 wrapper)
    ("bool_leaves", {"m": True}, {"m": False}),
    # Mixed everything
    ("kitchen_sink", {
        "clearance_3mm": 4.0, WIRELENGTH: "102.5", "thermal_score": 7,
    }, {
        "clearance_3mm": "4.0", WIRELENGTH: 100.0, "thermal_score": 6.5,
    }),
]


def _curated_cases() -> list[FreezeCase]:
    out = []
    for name, cand, base in _CURATED:
        ctx = WIRELENGTH in (set(cand) & set(base))
        out.append(FreezeCase(
            input={
                "candidate": {k: v for k, v in cand.items()},
                "baseline": {k: v for k, v in base.items()},
                "context": WIRELENGTH,
            },
            tags=_tags_for(cand, base, ctx) | {f"named:{name}"},
        ))
    return out


def _rand_val(rng: SplitMix64):
    roll = rng.index(100)
    if roll < 30:
        return rng.next_f64() * 200.0 - 50.0  # float in [-50, 150)
    if roll < 45:
        return rng.range_i64(-20, 201)  # int
    if roll < 55:
        return rng.next_f64() > 0.5  # bool
    if roll < 75:
        # numeric string
        style = rng.index(4)
        x = rng.next_f64() * 100.0
        if style == 0:
            return repr(x)
        if style == 1:
            return str(int(x))
        if style == 2:
            return f"{x:.3f}"
        return f"{x:.6e}"
    if roll < 80:
        choice = rng.index(3)
        return ("inf", "-inf", "nan")[choice]
    if roll < 85:
        return rng.next_f64()
    # non-numeric string
    words = ("abc", "12x", "--", "", "1.2.3")
    return words[rng.index(len(words))]


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    out = []
    for _ in range(n):
        n_keys = rng.range_i64(0, 6)
        cand: dict = {}
        base: dict = {}
        alphabet = "abcdefghijklmnopqrstuvwxyz"
        shared: list[str] = []
        for i in range(n_keys):
            key = alphabet[rng.index(26)] + str(i)
            shared.append(key)
        for key in shared:
            roll = rng.index(10)
            if roll < 8:
                cand[key] = _rand_val(rng)
                base[key] = _rand_val(rng)
            elif roll == 8:
                cand[key] = _rand_val(rng)  # candidate-only
            else:
                base[key] = _rand_val(rng)  # baseline-only
        ctx = WIRELENGTH
        out.append(FreezeCase(
            input={"candidate": cand, "baseline": base, "context": ctx},
            tags=_tags_for(cand, base, WIRELENGTH in (set(cand) & set(base))),
        ))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(60, seed=0x00C0_5A7C)


def run_oracle(case_input: dict):
    """Drive the pinned oracle's own compare_metric_dicts.

    Non-numeric string leaves raise ValueError inside the oracle's
    ``float(...)`` — that IS pinned behavior (the kernel returns
    ``FloatCoerceError`` for it). We capture it as a structured output so
    render_rust can emit a coerce-error expectation instead of failing.
    """
    oracle = _oracle_module()
    try:
        result = oracle.compare_metric_dicts(
            case_input["candidate"],
            case_input["baseline"],
            wirelength_metric=case_input["context"],
        )
    except ValueError as exc:
        # Identify which leaf failed by driving float() over both maps in
        # the oracle's own evaluation order (candidate first, then baseline,
        # sorted metric names).
        import builtins

        names = set(case_input["candidate"]) & set(case_input["baseline"])
        if case_input["context"] in names:
            names.discard(case_input["context"])
            ordered = sorted(names) + [case_input["context"]]
        else:
            ordered = sorted(names)
        bad_key = None
        bad_side = None
        for name in ordered:
            for side, source in (("candidate", case_input["candidate"]), ("baseline", case_input["baseline"])):
                if name not in source:
                    continue
                try:
                    builtins.float(source[name])
                except (TypeError, ValueError):
                    if isinstance(source[name], str):
                        bad_key = name
                        bad_side = side
                        break
                # only strings map onto FloatCoerceError; TypeError-class
                # leaves (None etc.) stay in the pyo3 wrapper's domain and
                # are excluded from the corpus by construction.
            if bad_key:
                break
        assert bad_key is not None, f"ValueError without a string leaf: {exc}"
        return {
            "coerce_error": True,
            "key": bad_key,
            "side": bad_side,
            "message": str(exc),
            "passed": None,
            "rows": [],
            "summary": "",
        }
    return {
        "coerce_error": False,
        "key": None,
        "passed": result.passed,
        "rows": [
            [c.name, c.cp_sat_value, c.jax_value, c.passed, c.detail]
            for c in result.comparisons
        ],
        "summary": result.summary,
    }


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `compare_metric_maps` + `parity_summary`")
    lines.append("    /// (FREEZE, U4/U5). Regenerate:")
    lines.append("    /// `python3 scripts/gen_oracle_freeze.py --spec cp_sat_comparison`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/cp_sat_comparison.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_tests {")
    lines.append("        use super::*;")
    lines.append("        use std::collections::HashMap;")
    lines.append("")
    lines.append("        struct FrozenCpSatComparisonCase<'a> {")
    lines.append("            candidate: &'a [(&'a str, &'a str)],")
    lines.append("            baseline: &'a [(&'a str, &'a str)],")
    lines.append("            /// None = expect FloatCoerceError on this key")
    lines.append("            coerce_error_key: Option<&'static str>,")
    lines.append("            expected_rows: &'a [(&'a str, u64, u64, bool)],")
    lines.append("            expected_passed: bool,")
    lines.append("            expected_summary: &'a str,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        fn to_map(pairs: &[(&str, &str)]) -> HashMap<String, String> {")
    lines.append("            pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_CP_SAT_COMPARISON_GOLDEN: &[FrozenCpSatComparisonCase] = &[")
    for case, output in results:
        ci = case.input
        cand_items = ", ".join(
            f'("{k}", {_py_str_literal(v)})' for k, v in ci["candidate"].items()
        )
        base_items = ", ".join(
            f'("{k}", {_py_str_literal(v)})' for k, v in ci["baseline"].items()
        )
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))

        if output.get("coerce_error"):
            rows_rs = ""
            summary_lit = '""'
            coerce_key = f'Some("{output["key"]}")'
            passed_lit = "false"
        else:
            rows_rs = ", ".join(
                '("{name}", {actual_bits:#018x}_u64, {expected_bits:#018x}_u64, {passed})'.format(
                    name=r[0],
                    actual_bits=_bits(float(r[1])),
                    expected_bits=_bits(float(r[2])),
                    passed=str(bool(r[3])).lower(),
                )
                for r in output["rows"]
            )
            summary_lit = _py_str_literal(output["summary"])
            coerce_key = "None"
            passed_lit = str(bool(output["passed"])).lower()

        lines.append("            FrozenCpSatComparisonCase {")
        lines.append(f"                candidate: &[{cand_items}],")
        lines.append(f"                baseline: &[{base_items}],")
        lines.append(f"                coerce_error_key: {coerce_key},")
        lines.append(f"                expected_rows: &[{rows_rs}],")
        lines.append(f"                expected_passed: {passed_lit},")
        lines.append(f"                expected_summary: {summary_lit},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_cp_sat_comparison_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_CP_SAT_COMPARISON_GOLDEN {")
    lines.append("                let expected = to_map(case.baseline);")
    lines.append("                let actual = to_map(case.candidate);")
    lines.append("                let result = compare_metric_maps(&expected, &actual, \"total_manhattan_wirelength\");")
    lines.append("                match (case.coerce_error_key, result) {")
    lines.append("                    (Some(key), Err(err)) => assert_eq!(&err.key, key, \"tags={:?}\", case.tags),")
    lines.append("                    (Some(key), Ok(_)) => panic!(\"expected coerce error on {:?}, got rows -- tags={:?}\", key, case.tags),")
    lines.append("                    (None, Err(err)) => panic!(\"unexpected coerce error on {:?} -- tags={:?}\", err.key, case.tags),")
    lines.append("                    (None, Ok(rows)) => {")
    lines.append("                        assert_eq!(rows.len(), case.expected_rows.len(), \"tags={:?}\", case.tags);")
    lines.append("                        for (got, want) in rows.iter().zip(case.expected_rows.iter()) {")
    lines.append("                            assert_eq!(got.name, want.0, \"tags={:?}\", case.tags);")
    lines.append("                            let got_a = f64::from_bits(got.actual.to_bits());")
    lines.append("                            let want_a = f64::from_bits(want.1);")
    lines.append("                            let got_e = f64::from_bits(got.expected.to_bits());")
    lines.append("                            let want_e = f64::from_bits(want.2);")
    lines.append("                            let bits_ok = |g: f64, w: f64| (g.is_nan() && w.is_nan()) || g.to_bits() == w.to_bits();")
    lines.append("                            assert!(bits_ok(got_a, want_a) && bits_ok(got_e, want_e), \"tags={:?}: got row {{}} vs expected {{?}}\", case.tags);")
    lines.append("                            assert_eq!(got.passed, want.3, \"tags={:?}\", case.tags);")
    lines.append("                        }")
    lines.append("                        let (passed, summary) = parity_summary(&rows);")
    lines.append("                        assert_eq!(passed, case.expected_passed, \"tags={:?}\", case.tags);")
    lines.append("                        assert_eq!(summary, case.expected_summary, \"tags={:?}\", case.tags);")
    lines.append("                    }")
    lines.append("                }")
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard.")
    lines.append("        #[test]")
    lines.append("        fn frozen_cp_sat_comparison_corpus_is_non_vacuous() {")
    lines.append("            let n = FROZEN_CP_SAT_COMPARISON_GOLDEN.len() as u32;")
    lines.append("            let count = |tag: &str| FROZEN_CP_SAT_COMPARISON_GOLDEN.iter()")
    lines.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    for nvc in _NON_VACUITY:
        if nvc.min_count:
            lines.append(
                f'            assert!(count("{nvc.tag}") >= {nvc.min_count}, '
                f'"{nvc.tag}: only {{}} (need >= {nvc.min_count}) -- {nvc.description}", '
                f'count("{nvc.tag}"));'
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
    body = "\n".join(lines)
    return body


def _py_str_literal(v) -> str:
    """Render a Python value as a Rust &str literal (leaves are stringified
    exactly as they'd cross the PyDict boundary: non-string leaves become
    their float()-coercible spelling upstream, but the corpus stores the
    RAW leaf so the oracle arm sees identical input).

    NOTE: bool leaves are NOT representable here — the oracle receives a
    real Python bool (float(True)==1.0), but the plain-map core takes
    strings only, and str(True)="True" is NOT float()-coercible. The
    bool->float path is owned by the pyo3 wrapper (py_builtin_float) and
    is pinned by the differential's wiring check instead. Bool leaves in
    gen_cases() are rendered as their float() spelling so the corpus stays
    honest about the value the comparison actually sees post-coercion.
    """
    if isinstance(v, bool):
        return '"1.0"' if v else '"0.0"'
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(v, float):
        if math.isnan(v):
            return '"nan"'
        if math.isinf(v):
            return '"-inf"' if v < 0 else '"inf"'
        return f'"{v!r}"'
    if isinstance(v, int):
        return f'"{v}"'
    return f'"{v!r}"'


def _bits(x) -> int:
    import struct

    if isinstance(x, bool):
        x = float(x)
    return struct.unpack(">Q", struct.pack(">d", float(x)))[0]


_NON_VACUITY = [
    NonVacuityCheck(
        tag="numeric_str",
        description="string-number coercion leaves must be common (the oracle's float('...') path)",
        min_fraction=0.15,
    ),
    NonVacuityCheck(
        tag="non_numeric_str",
        description="non-numeric strings must be present (coercion failure boundary)",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="wirelength_in_intersection",
        description="the 5%-tolerance context rule must be exercised",
        min_count=8,
    ),
    NonVacuityCheck(
        tag="candidate_only_key",
        description="asymmetric candidate-only keys must be exercised",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="baseline_only_key",
        description="asymmetric baseline-only keys must be exercised",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="nan_leaf",
        description="NaN must appear among raw leaves",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="inf_leaf",
        description="infinities must appear among raw leaves",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="bool_leaf",
        description="float(True)==1.0 semantics must be pinned",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="both_empty",
        description="the empty-vs-empty shape must be exercised",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="zero_baseline_context",
        description="the baseline==0 wirelength branch must be exercised",
        min_count=3,
    ),
]


SPEC = FreezeSpec(
    name="cp_sat_comparison",
    description=(
        "cp_sat_comparison parity gate: per-metric Pareto comparison over "
        "string-valued score maps with Python-float() coercion semantics "
        "(oracle: tests/regression/_cp_sat_comparison_py_oracle.py; kernels: "
        "temper-design-bundle/src/cp_sat_comparison.rs :: compare_metric_maps "
        "+ parity_summary)"
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/regression/_cp_sat_comparison_py_oracle.py "
        "(VERBATIM of temper_placer/regression/cp_sat_comparison.py @ 0a29f15e3)"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/cp_sat_comparison.rs :: "
        "compare_metric_maps + parity_summary"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/cp_sat_comparison.rs",
    insert_before_marker=(
        "/// Call Python's builtin `float()` on a value (the oracle's `float(x)`"
    ),
)
