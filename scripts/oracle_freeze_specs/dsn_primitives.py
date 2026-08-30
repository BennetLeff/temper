"""FREEZE spec: ``io/dsn.py``'s DSN S-expression formatting kernels (U4
oracle retirement, batch 3).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/io/_dsn_py_oracle.py
  VERBATIM copy as of commit ``3488051ea``; unchanged 1482 commits as of freeze.

Kernel:
  packages/temper-io-types/src/dsn_types.rs :: format_dsn_arg /
  dsn_expression_to_string — the float formatting (``{:.6f}`` trim), string
  quoting/escaping, nested expression rendering, and comment prefix logic.
  Pure functions over DsnArg/DsnExpressionData — no pyo3 objects in or out.

Disposition: FREEZE. Not a safety kernel. No host-facility or entropy
dependency: pure string formatting over simple data.
"""

from __future__ import annotations

import math
import sys
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
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    import importlib
    try:
        return importlib.import_module("tests.io._dsn_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 3488051ea:packages/temper-placer/tests/io/"
            "_dsn_py_oracle.py > packages/temper-placer/tests/io/"
            "_dsn_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


_ARG_TYPES = ("float", "int", "str", "bool", "nested", "raw")


def _py_arg(arg):
    kind, val = arg
    if kind == "float":
        return float(val)
    if kind == "int":
        return int(val)
    if kind == "str":
        return str(val)
    if kind == "bool":
        return bool(val)
    if kind == "nested":
        oracle = _oracle_module()
        return _build_expr(oracle, val)
    if kind == "raw":
        return val
    raise ValueError(f"unknown arg kind: {kind}")


def _build_expr(oracle, case_input):
    name = case_input["name"]
    args = [_py_arg(a) for a in case_input["args"]]
    expr = oracle.dsn_list(name, *args)
    comment = case_input.get("comment")
    if comment is not None:
        expr = expr.with_comment(comment)
    return expr


def run_oracle(case_input: dict) -> str:
    oracle = _oracle_module()
    expr = _build_expr(oracle, case_input)
    return str(expr)


def _tags_for(case_input, output) -> frozenset[str]:
    tags: set[str] = set()
    arg_kinds = {a[0] for a in case_input["args"]}
    for k in arg_kinds:
        tags.add(f"arg:{k}")
    if not case_input["args"]:
        tags.add("empty_args")
    if case_input.get("comment"):
        tags.add("has_comment")
    if any(a[0] == "str" for a in case_input["args"]):
        s_args = [a[1] for a in case_input["args"] if a[0] == "str"]
        if any(" " in s or "(" in s or ")" in s or '"' in s for s in s_args):
            tags.add("str:special_chars")
        if any(s == "" for s in s_args):
            tags.add("str:empty")
    if any(a[0] == "float" for a in case_input["args"]):
        f_args = [a[1] for a in case_input["args"] if a[0] == "float"]
        if any(f == 0.0 or f == 0 for f in f_args):
            tags.add("float:zero")
        if any(isinstance(f, float) and not math.isinf(f) and f != int(f) for f in f_args):
            tags.add("float:fractional")
        if any(f < 0 for f in f_args):
            tags.add("float:negative")
        if any(abs(f) < 1e-6 for f in f_args):
            tags.add("float:tiny")
        if any(abs(f) > 1e15 for f in f_args):
            tags.add("float:huge")
    if any(a[0] == "nested" for a in case_input["args"]):
        tags.add("nested")
    if any(a[0] == "bool" for a in case_input["args"]):
        tags.add("bool_arg")
    return frozenset(tags)


def _tagged_case(name, case_input):
    output = run_oracle(case_input)
    tags = _tags_for(case_input, output)
    if name:
        tags = tags | {f"named:{name}"}
    return FreezeCase(input=case_input, tags=tags)


def _curated_cases() -> list[FreezeCase]:
    cases = []
    def add(name, ci):
        cases.append((name, ci))

    add("empty_expr", {"name": "pcb", "args": [], "comment": None})
    add("simple_floats", {"name": "coord", "args": [("float", 10.0), ("float", 10.5), ("float", 10.54321), ("float", 0.0), ("float", -0.0)], "comment": None})
    add("simple_ints", {"name": "pins", "args": [("int", 1), ("int", 2), ("int", 100)], "comment": None})
    add("simple_strs", {"name": "name", "args": [("str", "GND"), ("str", "VCC (Power)"), ("str", 'Quoted "String"'), ("str", "")], "comment": None})
    add("nested", {"name": "pcb", "args": [("str", "sample"), ("nested", {"name": "unit", "args": [("str", "mm")], "comment": None})], "comment": None})
    add("with_comment", {"name": "pcb", "args": [("str", "sample")], "comment": "c: 1"})
    add("empty_comment", {"name": "pcb", "args": [("str", "sample")], "comment": ""})
    add("mixed", {"name": "mixed", "args": [("int", 1), ("float", 2.0), ("str", "three"), ("int", 10**30)], "comment": None})
    add("tiny_floats", {"name": "tiny", "args": [("float", 1e-7), ("float", 1e-6), ("float", 1e-9), ("float", 123456789.123456789)], "comment": None})
    add("inf_floats", {"name": "inf", "args": [("float", float("inf")), ("float", float("-inf"))], "comment": None})
    add("bool_args", {"name": "flags", "args": [("bool", True), ("bool", False)], "comment": None})
    add("negative_floats", {"name": "neg", "args": [("float", -0.5), ("float", -1e-9), ("float", -123.456)], "comment": None})
    add("fractional_trim", {"name": "frac", "args": [("float", 1.0 / 3.0), ("float", 2.0 / 3.0), ("float", 0.1 + 0.2)], "comment": None})
    add("large_int", {"name": "big", "args": [("int", 10**18), ("int", -10**18)], "comment": None})
    add("deeply_nested", {"name": "a", "args": [("nested", {"name": "b", "args": [("nested", {"name": "c", "args": [("str", "deep")], "comment": None})], "comment": None})], "comment": None})
    add("raw_arg", {"name": "raw", "args": [("raw", "None")], "comment": None})
    add("unicode_str", {"name": "u", "args": [("str", "uni-Δ")], "comment": None})
    add("tab_str", {"name": "t", "args": [("str", "tab\tsep")], "comment": None})
    add("comment_with_newline_ref", {"name": "c", "args": [("str", "x")], "comment": "multi word comment"})
    add("only_int_args", {"name": "ints", "args": [("int", 0), ("int", -1), ("int", 42)], "comment": None})

    return [_tagged_case(name, ci) for name, ci in cases]


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    float_pool = [0.0, 1.0, -1.0, 0.5, -0.5, 1e-7, 1e6, 123.456, 1.0/3.0, 2.0/3.0, 0.1+0.2, float("inf"), float("-inf"), 10.54321, 0.005, 0.025, 1e-320, 5e-324, 123456789.987654321, -999.999]
    str_pool = ["GND", "VCC", "has space", 'has"quote"', "", "simple", "(paren)", "tab\tsep", "uni-Δ", "Net-(U1-Pad1)"]
    int_pool = [0, 1, -1, 42, 100, 1000000, 10**15, -10**15, 7, 255]
    out: list[FreezeCase] = []
    for _ in range(n):
        n_args = rng.range_i64(0, 6)
        args = []
        for _ in range(n_args):
            kind_idx = rng.range_i64(0, 5)
            kind = _ARG_TYPES[kind_idx]
            if kind == "float":
                args.append(("float", float_pool[rng.index(len(float_pool))]))
            elif kind == "int":
                args.append(("int", int_pool[rng.index(len(int_pool))]))
            elif kind == "str":
                args.append(("str", str_pool[rng.index(len(str_pool))]))
            elif kind == "bool":
                args.append(("bool", rng.boolean()))
            elif kind == "nested":
                args.append(("nested", {"name": "sub", "args": [("str", "x"), ("float", 1.0)], "comment": None}))
            elif kind == "raw":
                args.append(("raw", "None"))
        name = str_pool[rng.index(len(str_pool))]
        has_comment = rng.boolean()
        comment = "comment text" if has_comment else None
        out.append(_tagged_case(None, {"name": name, "args": args, "comment": comment}))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(80, seed=0x054F2002)


_NON_VACUITY = [
    NonVacuityCheck(tag="arg:float", description="float args must be exercised", min_count=20),
    NonVacuityCheck(tag="arg:int", description="int args must be exercised", min_count=10),
    NonVacuityCheck(tag="arg:str", description="str args must be exercised", min_count=20),
    NonVacuityCheck(tag="arg:bool", description="bool args (str(v) fallback) must be exercised", min_count=3),
    NonVacuityCheck(tag="arg:nested", description="nested expressions must be exercised", min_count=5),
    NonVacuityCheck(tag="empty_args", description="empty-args expression must be exercised", min_count=2),
    NonVacuityCheck(tag="has_comment", description="comment prefix must be exercised", min_count=5),
    NonVacuityCheck(tag="str:special_chars", description="strings needing quoting/escaping must be exercised", min_count=5),
    NonVacuityCheck(tag="str:empty", description="empty string (-> \"\") must be exercised", min_count=3),
    NonVacuityCheck(tag="float:zero", description="zero floats must be exercised", min_count=3),
    NonVacuityCheck(tag="float:fractional", description="fractional floats must be exercised", min_count=10),
    NonVacuityCheck(tag="float:negative", description="negative floats must be exercised", min_count=5),
    NonVacuityCheck(tag="float:tiny", description="tiny (subnormal) floats must be exercised", min_count=2),
    NonVacuityCheck(tag="bool_arg", description="bool args must be exercised", min_count=3),
    NonVacuityCheck(tag="nested", description="nested expressions must be exercised", min_count=5),
]


def _render_arg(arg) -> str:
    kind, val = arg
    if kind == "float":
        return f"DsnArg::Float({rust_f64_literal(float(val))})"
    if kind == "int":
        return f"DsnArg::Int({int(val)}_i64)"
    if kind == "str":
        escaped = val.replace('\\', '\\\\').replace('"', '\\"')
        return f'DsnArg::Str("{escaped}".to_string())'
    if kind == "bool":
        return f'DsnArg::Raw("{"True" if val else "False"}".to_string())'
    if kind == "nested":
        sub = _render_expr(val)
        return f"DsnArg::Nested(Box::new({sub}))"
    if kind == "raw":
        escaped = val.replace('\\', '\\\\').replace('"', '\\"')
        return f'DsnArg::Raw("{escaped}".to_string())'
    raise ValueError(f"unknown arg kind: {kind}")


def _render_expr(case_input) -> str:
    name = case_input["name"]
    name_escaped = name.replace('\\', '\\\\').replace('"', '\\"')
    args_rs = ", ".join(_render_arg(a) for a in case_input["args"])
    comment = case_input.get("comment")
    if comment is not None:
        escaped = comment.replace('\\', '\\\\').replace('"', '\\"')
        comment_rs = f'Some("{escaped}".to_string())'
    else:
        comment_rs = "None"
    return (
        f"DsnExpressionData {{ "
        f'name: "{name_escaped}".to_string(), '
        f"args: vec![{args_rs}], "
        f"comment: {comment_rs} "
        f"}}"
    )


def _render_string(s: str) -> str:
    escaped = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
    return f'"{escaped}"'


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for DSN S-expression formatting (FREEZE, U4/U5, batch 3).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec dsn_primitives`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/dsn_primitives.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_dsn_tests {")
    lines.append("        use super::*;")
    lines.append("")
    lines.append("        #[derive(Clone, Copy)]")
    lines.append("        enum FrozenDsnArg {")
    lines.append("            Float(f64),")
    lines.append("            Int(i64),")
    lines.append("            Str(&'static str),")
    lines.append("            Nested(&'static FrozenDsnExpr),")
    lines.append("            Raw(&'static str),")
    lines.append("        }")
    lines.append("")
    lines.append("        #[derive(Clone, Copy)]")
    lines.append("        struct FrozenDsnExpr {")
    lines.append("            name: &'static str,")
    lines.append("            args: &'static [FrozenDsnArg],")
    lines.append("            comment: Option<&'static str>,")
    lines.append("        }")
    lines.append("")
    lines.append("        struct FrozenDsnCase {")
    lines.append("            expr: FrozenDsnExpr,")
    lines.append("            expected: &'static str,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")

    # First, emit any nested expressions as named statics
    nested_exprs: dict[str, dict] = {}
    for case, output in results:
        for arg in case.input["args"]:
            if arg[0] == "nested":
                sub = arg[1]
                key = f"NESTED_{len(nested_exprs)}"
                nested_exprs[key] = sub

    # Recursively collect nested expressions
    changed = True
    while changed:
        changed = False
        for key, sub in list(nested_exprs.items()):
            for arg in sub["args"]:
                if arg[0] == "nested":
                    sub2 = arg[1]
                    key2 = f"NESTED_{len(nested_exprs)}"
                    if sub2 not in list(nested_exprs.values()):
                        nested_exprs[key2] = sub2
                        changed = True

    # Assign stable keys
    nested_list = list(nested_exprs.values())
    nested_keys = {}
    for i, sub in enumerate(nested_list):
        # Find by identity
        for k, v in nested_exprs.items():
            if v is sub and k not in nested_keys.values():
                nested_keys[id(sub)] = f"NESTED_{i}"
                break

    # Emit nested statics
    for i, sub in enumerate(nested_list):
        key = f"NESTED_{i}"
        name_esc = sub["name"].replace('\\', '\\\\').replace('"', '\\"')
        args_rs = ", ".join(_render_frozen_arg(a, nested_keys) for a in sub["args"])
        comment = sub.get("comment")
        if comment is not None:
            c_esc = comment.replace('\\', '\\\\').replace('"', '\\"')
            comment_rs = f'Some("{c_esc}")'
        else:
            comment_rs = "None"
        lines.append(f"        static {key}: FrozenDsnExpr = FrozenDsnExpr {{")
        lines.append(f'            name: "{name_esc}",')
        lines.append(f"            args: &[{args_rs}],")
        lines.append(f"            comment: {comment_rs},")
        lines.append("        };")
        lines.append("")

    lines.append("        const FROZEN_DSN_GOLDEN: &[FrozenDsnCase] = &[")
    for case, output in results:
        expr_rs = _render_frozen_expr(case.input, nested_keys)
        expected_rs = _render_string(str(output))
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenDsnCase {")
        lines.append(f"                expr: {expr_rs},")
        lines.append(f"                expected: {expected_rs},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")

    # Helper to convert FrozenDsnArg -> DsnArg
    lines.append("        fn frozen_arg_to_dsn(arg: &FrozenDsnArg) -> DsnArg {")
    lines.append("            match arg {")
    lines.append("                FrozenDsnArg::Float(f) => DsnArg::Float(*f),")
    lines.append("                FrozenDsnArg::Int(i) => DsnArg::Int(*i),")
    lines.append("                FrozenDsnArg::Str(s) => DsnArg::Str(s.to_string()),")
    lines.append("                FrozenDsnArg::Nested(e) => DsnArg::Nested(Box::new(frozen_expr_to_dsn(e))),")
    lines.append("                FrozenDsnArg::Raw(s) => DsnArg::Raw(s.to_string()),")
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        fn frozen_expr_to_dsn(e: &FrozenDsnExpr) -> DsnExpressionData {")
    lines.append("            DsnExpressionData {")
    lines.append("                name: e.name.to_string(),")
    lines.append("                args: e.args.iter().map(frozen_arg_to_dsn).collect(),")
    lines.append("                comment: e.comment.map(|c| c.to_string()),")
    lines.append("            }")
    lines.append("        }")
    lines.append("")

    # Test functions
    lines.append("        #[test]")
    lines.append("        fn frozen_dsn_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_DSN_GOLDEN {")
    lines.append("                let expr = frozen_expr_to_dsn(&case.expr);")
    lines.append("                let got = dsn_expression_to_string(&expr);")
    lines.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")

    # Non-vacuity guard
    lines.append("        /// Q2 non-vacuity guard.")
    lines.append("        #[test]")
    lines.append("        fn frozen_dsn_corpus_is_non_vacuous() {")
    lines.append("            let n = FROZEN_DSN_GOLDEN.len() as u32;")
    lines.append("            let count = |tag: &str| FROZEN_DSN_GOLDEN.iter()")
    lines.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    for nvc in _NON_VACUITY:
        desc_escaped = nvc.description.replace('"', '\\"')
        if nvc.min_count:
            lines.append(
                f'            assert!(count("{nvc.tag}") >= {nvc.min_count}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {nvc.min_count}) -- {desc_escaped}", '
                f'count("{nvc.tag}"), n);'
            )
        else:
            pct = int(round(nvc.min_fraction * 100))
            lines.append(
                f'            assert!(count("{nvc.tag}") * 100 >= n * {pct}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {pct}%) -- {desc_escaped}", '
                f'count("{nvc.tag}"), n);'
            )
    lines.append("        }")
    lines.append("    }")
    return "\n".join(lines)


def _render_frozen_arg(arg, nested_keys) -> str:
    kind, val = arg
    if kind == "float":
        return f"FrozenDsnArg::Float({rust_f64_literal(float(val))})"
    if kind == "int":
        iv = int(val)
        if -9223372036854775808 <= iv <= 9223372036854775807:
            return f"FrozenDsnArg::Int({iv}_i64)"
        else:
            return f'FrozenDsnArg::Raw("{iv}")'
    if kind == "str":
        escaped = val.replace('\\', '\\\\').replace('"', '\\"')
        return f'FrozenDsnArg::Str("{escaped}")'
    if kind == "bool":
        return f'FrozenDsnArg::Raw("{"True" if val else "False"}")'
    if kind == "nested":
        key = nested_keys.get(id(val), "NESTED_0")
        return f"FrozenDsnArg::Nested(&{key})"
    if kind == "raw":
        escaped = val.replace('\\', '\\\\').replace('"', '\\"')
        return f'FrozenDsnArg::Raw("{escaped}")'
    raise ValueError(f"unknown arg kind: {kind}")


def _render_frozen_expr(case_input, nested_keys) -> str:
    name = case_input["name"]
    name_escaped = name.replace('\\', '\\\\').replace('"', '\\"')
    args_rs = ", ".join(_render_frozen_arg(a, nested_keys) for a in case_input["args"])
    comment = case_input.get("comment")
    if comment is not None:
        escaped = comment.replace('\\', '\\\\').replace('"', '\\"')
        comment_rs = f'Some("{escaped}")'
    else:
        comment_rs = "None"
    return (
        f"FrozenDsnExpr {{ "
        f'name: "{name_escaped}", '
        f"args: &[{args_rs}], "
        f"comment: {comment_rs} "
        f"}}"
    )


SPEC = FreezeSpec(
    name="dsn_primitives",
    description=(
        "io/dsn.py — DSN S-expression formatting kernels: format_dsn_arg / "
        "dsn_expression_to_string (float trim, string quoting, nesting, comments)."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/io/_dsn_py_oracle.py, "
        "VERBATIM from pre-migration commit 3488051ea, unchanged 1482 commits "
        "as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-io-types/src/dsn_types.rs :: format_dsn_arg / dsn_expression_to_string"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-io-types/src/dsn_types.rs",
    insert_before_marker="    #[cfg_attr(test, test)]",
)
