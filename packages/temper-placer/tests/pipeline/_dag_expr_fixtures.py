"""Shared fixtures for the dag_expr Rust-port gate set.

Every dag_expr test AND the performance benchmark import their inputs from
this one module. That is structural, not stylistic: PR #714 in this program
passed its differential at iteration counts ``[0,1,2,8,17,100]`` and then
failed CI on a benchmark that ran 120, because the benchmark owned its own
parameters. #721 fixed that class of bug by making the two share a single
fixture module, so a benchmark can never reach a parameter the differential
has not already covered. ``CORPUS`` and ``NESTING_DEPTHS`` below are that
shared surface; ``test_benchmark_inputs_are_covered_by_differential`` enforces
it.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import pathlib
import sys
import types
from typing import Any

# ---------------------------------------------------------------------------
# Import bootstrap
# ---------------------------------------------------------------------------
#
# ``temper_placer/__init__.py`` eagerly imports core.board, which needs the
# temper_design_bundle_python extension. In a full CI checkout that is built
# and the plain import works. In a partial dev environment it is not, and
# without this shim the whole dag_expr gate set would fail to COLLECT -- i.e.
# report green-by-absence, the exact vacuity failure this program keeps paying
# for. So: try the real import first, and fall back to loading only
# pipeline/dag_types + pipeline/dag_expr from their true source paths, then
# assert the module actually loaded is the file we intended.

_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_SRC = _TESTS_DIR.parents[1] / "src" / "temper_placer"


def _bootstrap() -> None:
    try:
        importlib.import_module("temper_placer.pipeline.dag_expr")
        return
    except ModuleNotFoundError as exc:
        # Only a missing *sibling* extension may be worked around. A missing
        # dag_expr itself is a real failure and must surface.
        if exc.name in {"temper_placer.pipeline.dag_expr", "temper_io_types"}:
            raise
    for name, path in (
        ("temper_placer", _SRC),
        ("temper_placer.pipeline", _SRC / "pipeline"),
    ):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = [str(path)]  # type: ignore[attr-defined]
            sys.modules[name] = mod


_bootstrap()

from temper_placer.pipeline import dag_expr as rust_impl  # noqa: E402
from temper_placer.pipeline.dag_types import (  # noqa: E402
    DAGExprError,
    DAGExprSyntaxError,
)

assert (
    pathlib.Path(rust_impl.__file__).resolve() == (_SRC / "pipeline" / "dag_expr.py").resolve()
), f"bootstrap loaded the wrong dag_expr: {rust_impl.__file__}"


def _load_oracle():
    """Load the pinned oracle by path (tests/pipeline is not a package)."""
    path = _TESTS_DIR / "_dag_expr_py_oracle.py"
    spec = importlib.util.spec_from_file_location("_dag_expr_py_oracle", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load dag_expr oracle from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


py_oracle = _load_oracle()

ORACLE_PATH = _TESTS_DIR / "_dag_expr_py_oracle.py"

__all__ = [
    "CORPUS",
    "DAGExprError",
    "DAGExprSyntaxError",
    "EVAL_CORPUS",
    "NESTING_DEPTHS",
    "ORACLE_PATH",
    "ast_signature",
    "make_env",
    "nested_expr",
    "outcome_signature",
    "py_oracle",
    "rust_impl",
    "type_signature",
]


# ---------------------------------------------------------------------------
# Type-carrying signatures (R1a)
# ---------------------------------------------------------------------------


def type_signature(value: Any) -> tuple:
    """A comparison key carrying the value's *type*, not just its value.

    Rules:
      - every float contributes ``float.hex()`` -- exact bits, no tolerance,
        so ``0.0`` and ``-0.0`` are distinguishable where ``==`` calls them
        equal, and a 1-ulp difference cannot hide;
      - every leaf carries its CONCRETE type name, so ``True`` never compares
        equal to ``1``, nor ``numpy.float32`` to ``numpy.float64``;
      - arrays contribute dtype + shape as well as per-element bits.

    Each of those distinctions is pinned by a ``test_signature_self_*`` case
    in test_dag_expr_rust_differential.py -- a comparator nobody has tried to
    fool is not evidence of anything.
    """
    tname = type(value).__name__

    # bool BEFORE int: bool subclasses int, so an isinstance(int) test first
    # would collapse True and 1 -- the exact collision the self-test pins.
    if value is None or isinstance(value, bool):
        return (tname, repr(value))
    if isinstance(value, float):
        return (tname, value.hex())
    if isinstance(value, int):
        return (tname, str(value))
    if isinstance(value, str):
        return (tname, value)
    if isinstance(value, bytes):
        return (tname, value.hex())

    # numpy is optional: dag_expr never produces arrays, but this comparator
    # is shared and must not silently degrade if one ever appears.
    if type(value).__module__.startswith("numpy"):
        import numpy as np

        if isinstance(value, np.ndarray):
            return (
                tname,
                str(value.dtype),
                tuple(value.shape),
                tuple(type_signature(x) for x in value.ravel().tolist()),
            )
        if isinstance(value, np.floating):
            # dtype keeps float32 and float64 apart even when the widened
            # decimal value prints identically.
            return (tname, str(value.dtype), float(value).hex())
        if isinstance(value, np.integer):
            return (tname, str(value.dtype), str(int(value)))

    if isinstance(value, (list, tuple)):
        return (tname, tuple(type_signature(v) for v in value))
    if isinstance(value, dict):
        return (tname, tuple((type_signature(k), type_signature(v)) for k, v in value.items()))
    return (tname, repr(value))


def ast_signature(node: Any) -> tuple:
    """Type-carrying signature of a parsed skip-expression tree.

    ``_AccessorExpr`` is compared by class NAME: the oracle copy and the
    shipped module each define their own, so they are distinct classes by
    identity while being the same node behaviourally.
    """
    if isinstance(node, ast.Expression):
        return ("Expression", ast_signature(node.body))
    if isinstance(node, ast.Constant):
        return ("Constant", type_signature(node.value))
    if isinstance(node, ast.UnaryOp):
        return ("UnaryOp", type(node.op).__name__, ast_signature(node.operand))
    if isinstance(node, ast.BoolOp):
        return ("BoolOp", type(node.op).__name__, tuple(ast_signature(v) for v in node.values))
    if isinstance(node, ast.Compare):
        return (
            "Compare",
            ast_signature(node.left),
            tuple(type(o).__name__ for o in node.ops),
            tuple(ast_signature(c) for c in node.comparators),
        )
    if type(node).__name__ == "_AccessorExpr":
        return ("_AccessorExpr", type_signature(node.ns), type_signature(node.field))
    return ("UNKNOWN", type(node).__name__, repr(node))


def outcome_signature(fn, *args, **kwargs) -> tuple:
    """Run ``fn``; describe what happened, exception types included.

    An exception is behaviour under port, so it is compared by concrete class
    name AND message text -- never merely "both raised something".
    """
    try:
        result = fn(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 - the type IS the observable
        return ("raise", type(exc).__name__, str(exc))
    if isinstance(result, ast.Expression):
        return ("ok", ast_signature(result))
    return ("ok", type_signature(result))


# ---------------------------------------------------------------------------
# Evaluation environment
# ---------------------------------------------------------------------------


class _Config:
    """Stand-in for the pipeline config object (an attribute namespace)."""

    def __init__(self) -> None:
        self.epochs = 100
        self.seed = 0
        self.dry_run = False
        self.skip_routing = True
        self.convergence_threshold = 0.05
        self.negative_zero = -0.0
        self.positive_zero = 0.0
        self.big = 99999999999999999999
        self.name = "temper"
        self.empty = ""
        self.nothing = None
        self.one_int = 1
        self.one_float = 1.0
        self.true_bool = True


class _State:
    def __init__(self) -> None:
        self.thermal_anchoring_applied = False
        self.routing_result = None
        self.iteration = 3
        self.loss = 0.125


def make_env() -> tuple[Any, Any, dict[str, Any]]:
    """A fresh (config, state, context) triple.

    Fresh per call, so a test that mutates one cannot leak into another.
    """
    context = {
        "routability": 0.75,
        "epochs": 100,
        "flag": True,
        "missing_value": None,
        "label": "ok",
        "zero": 0,
    }
    return _Config(), _State(), context


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------

#: Parenthesis-nesting depths exercised by BOTH the differential and the
#: benchmark. A benchmark may not use a depth outside this tuple.
NESTING_DEPTHS: tuple[int, ...] = (0, 1, 2, 5, 17, 60, 120, 170)

#: Expression sources. Deliberately includes syntax and runtime errors: an
#: error's type and message are behaviour under port, not "not applicable".
CORPUS: tuple[str, ...] = (
    # --- literals -------------------------------------------------------
    "true",
    "false",
    "null",
    "1",
    "0",
    "1.",
    ".5",
    "1.5",
    "1e3",
    "1E3",
    "1e-3",
    "1.5e+10",
    "007",
    "99999999999999999999",  # exceeds i64; CPython int is arbitrary precision
    "'abc'",
    '"abc"',
    "''",  # the group(1)-falsy wart: this is None, not ""
    '""',  # ... but this really is ""
    "'a b'",
    "'it\\'s'",
    '"say \\"hi\\""',
    "'\\\\'",
    "'中文'",
    "'\\n'",
    # --- accessors ------------------------------------------------------
    "config.epochs",
    "config.dry_run",
    "config.nothing",
    "config.big",
    "state.iteration",
    "state.thermal_anchoring_applied",
    "context.routability",
    "context.flag",
    "context.zero",
    # --- comparisons ----------------------------------------------------
    "config.epochs == 100",
    "config.epochs != 100",
    "config.epochs < 100",
    "config.epochs > 99",
    "config.epochs <= 100",
    "config.epochs >= 101",
    "config.name == 'temper'",
    "config.one_int == 1",
    "config.one_float == 1",  # int/float cross-type equality
    "config.true_bool == 1",  # True == 1 is True in Python
    "config.positive_zero == config.negative_zero",  # 0.0 == -0.0 is True
    "config.empty == ''",  # "" == None -> False, thanks to the wart
    "config.nothing == null",
    "config.nothing == ''",  # None == None -> True, same wart, other side
    "context.routability < 0.8",
    "config.big > 1",
    # --- boolean structure ----------------------------------------------
    "not true",
    "not not true",
    "not config.dry_run",
    "true and false",
    "true or false",
    "true and true and false",
    "false or false or true",
    "config.dry_run or config.skip_routing",
    "config.epochs == 100 and context.flag",
    "not (true and false)",
    "(true or false) and not false",
    "config.epochs > 10 and context.routability < 0.9 or config.dry_run",
    "not config.epochs == 100",
    # --- whitespace -----------------------------------------------------
    "  true  ",
    "true\tand\tfalse",
    "true",  # isspace() but NOT char::is_whitespace()
    " true ",  # NBSP: isspace() and White_Space
    " true ",
    # --- syntax errors ---------------------------------------------------
    "",
    "   ",
    "foo",
    "notx",
    "config",
    "config.",
    "(true",
    "true)",
    "and",
    "==",
    "true ==",
    "1 2",
    "config.a @ 1",
    "'unterminated",
    "config.a == '中' @",
    "true\nand false",  # \n is not in the SKIP class -> error
    "@",
    "config..a",
    "true and",
    # --- runtime (evaluation) errors -------------------------------------
    "config.does_not_exist",
    "state.does_not_exist",
    "context.does_not_exist",
    "bogus.field",
    "config.nothing < 1",  # TypeError from CPython's rich compare
    "config.name < 1",  # TypeError: str vs int
)


def nested_expr(depth: int) -> str:
    """A parenthesis-nested expression of the given depth.

    Shared by differential and benchmark so the benchmark cannot reach a
    depth the differential has not.
    """
    return "(" * depth + "config.epochs == 100" + ")" * depth


def _parses_cleanly(src: str) -> bool:
    try:
        py_oracle.parse_skip_expr(src)
    except BaseException:  # noqa: BLE001
        return False
    return True


#: The subset that parses cleanly, so evaluation can be differentialled too.
EVAL_CORPUS: tuple[str, ...] = tuple(src for src in CORPUS if _parses_cleanly(src))
