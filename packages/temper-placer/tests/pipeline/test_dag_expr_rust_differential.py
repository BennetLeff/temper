"""R1a: behavioural A/B of the dag_expr Rust port against its pinned oracle.

Both arms are compared by TYPE-CARRYING SIGNATURE with no tolerance: floats by
``float.hex()``, every other leaf by concrete type name plus exact value, and
exceptions by concrete class name plus message text.

Read ``_dag_expr_fixtures.py`` first -- the corpus lives there and is shared
with the benchmark on purpose.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import pickle

import pytest

from ._dag_expr_fixtures import (
    CORPUS,
    EVAL_CORPUS,
    NESTING_DEPTHS,
    ORACLE_PATH,
    ast_signature,
    make_env,
    nested_expr,
    outcome_signature,
    py_oracle,
    rust_impl,
    type_signature,
)

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_PINNED_BODY_SHA256 = "5e56ad7789c501d34d1d317157f45fe443f1cc3e9070515ca521af5262a69064"
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_body_matches_pinned_digest() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied body is content-addressed. If this fails, either
    the oracle was edited (revert it) or dag_expr.py's pre-port source really
    changed upstream (re-pin deliberately, in its own commit).
    """
    text = ORACLE_PATH.read_text(encoding="utf-8")
    assert _BODY_MARKER in text, "oracle header marker missing"
    body = text.split(_BODY_MARKER, 1)[1]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert digest == _PINNED_BODY_SHA256, (
        "the pinned oracle body changed; it must stay verbatim "
        f"(expected {_PINNED_BODY_SHA256}, got {digest})"
    )


def test_oracle_and_port_are_different_implementations() -> None:
    """Anti-vacuity: guard against both arms being the same object.

    If a refactor ever made the shim re-export the oracle, every differential
    below would pass unconditionally while testing nothing.
    """
    assert py_oracle is not rust_impl
    assert py_oracle.parse_skip_expr is not rust_impl.parse_skip_expr
    # The port must actually be routed through Rust.
    assert hasattr(rust_impl, "_rs")
    assert hasattr(rust_impl._rs, "parse_skip_expr_rs")


# ---------------------------------------------------------------------------
# Comparator self-tests
# ---------------------------------------------------------------------------
#
# A comparator that cannot tell these apart would make every assertion below
# vacuous. Each case asserts a DIFFERENCE the naive `==` would miss.


def test_signature_self_distinguishes_bool_from_int() -> None:
    assert True == 1  # noqa: E712 - demonstrating what `==` cannot see
    assert type_signature(True) != type_signature(1)
    assert type_signature(False) != type_signature(0)


def test_signature_self_distinguishes_int_from_float() -> None:
    assert 1 == 1.0
    assert type_signature(1) != type_signature(1.0)


def test_signature_self_distinguishes_signed_zero() -> None:
    assert 0.0 == -0.0
    assert type_signature(0.0) != type_signature(-0.0)
    assert type_signature(-0.0) == ("float", "-0x0.0p+0")


def test_signature_self_distinguishes_one_ulp() -> None:
    import math

    x = 1.0
    y = math.nextafter(1.0, 2.0)
    assert x != y
    assert abs(y - x) < 1e-15  # invisible to any sane tolerance
    assert type_signature(x) != type_signature(y)


def test_signature_self_distinguishes_f32_from_f64() -> None:
    np = pytest.importorskip("numpy")
    a = np.float32(0.1)
    b = np.float64(np.float32(0.1))  # same numeric value, different dtype
    assert float(a) == float(b)
    assert type_signature(a) != type_signature(b)


def test_signature_self_distinguishes_array_dtype_and_shape() -> None:
    np = pytest.importorskip("numpy")
    assert type_signature(np.zeros(4, dtype=np.float32)) != type_signature(
        np.zeros(4, dtype=np.float64)
    )
    assert type_signature(np.zeros((2, 2))) != type_signature(np.zeros((4,)))


def test_signature_self_distinguishes_str_from_none() -> None:
    """The `''` wart depends on telling `None` from `""`."""
    assert type_signature(None) != type_signature("")


def test_outcome_signature_distinguishes_exception_type_and_message() -> None:
    def raise_a():
        raise ValueError("boom")

    def raise_b():
        raise TypeError("boom")

    def raise_c():
        raise ValueError("bang")

    assert outcome_signature(raise_a) != outcome_signature(raise_b)  # type
    assert outcome_signature(raise_a) != outcome_signature(raise_c)  # message
    assert outcome_signature(raise_a) == outcome_signature(raise_a)


# ---------------------------------------------------------------------------
# R1a: parse differential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("src", CORPUS, ids=repr)
def test_parse_differential(src: str) -> None:
    """Parsing agrees on the tree, and on every error type and message."""
    expected = outcome_signature(py_oracle.parse_skip_expr, src)
    actual = outcome_signature(rust_impl.parse_skip_expr, src)
    assert actual == expected, f"parse divergence for {src!r}"


@pytest.mark.parametrize("depth", NESTING_DEPTHS, ids=lambda d: f"depth{d}")
def test_parse_differential_nested(depth: int) -> None:
    src = nested_expr(depth)
    expected = outcome_signature(py_oracle.parse_skip_expr, src)
    actual = outcome_signature(rust_impl.parse_skip_expr, src)
    assert actual == expected, f"parse divergence at nesting depth {depth}"


# ---------------------------------------------------------------------------
# R1a: evaluate differential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("src", EVAL_CORPUS, ids=repr)
def test_evaluate_differential(src: str) -> None:
    """Evaluation agrees on the bool, its exact type, and on error behaviour."""
    py_cfg, py_state, py_ctx = make_env()
    rs_cfg, rs_state, rs_ctx = make_env()

    expected = outcome_signature(
        lambda: py_oracle.evaluate_skip_expr(
            py_oracle.parse_skip_expr(src), py_cfg, py_state, py_ctx
        )
    )
    actual = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(
            rust_impl.parse_skip_expr(src), rs_cfg, rs_state, rs_ctx
        )
    )
    assert actual == expected, f"evaluate divergence for {src!r}"


@pytest.mark.parametrize("depth", NESTING_DEPTHS, ids=lambda d: f"depth{d}")
def test_evaluate_differential_nested(depth: int) -> None:
    src = nested_expr(depth)
    py_cfg, py_state, py_ctx = make_env()
    rs_cfg, rs_state, rs_ctx = make_env()
    expected = outcome_signature(
        lambda: py_oracle.evaluate_skip_expr(
            py_oracle.parse_skip_expr(src), py_cfg, py_state, py_ctx
        )
    )
    actual = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(
            rust_impl.parse_skip_expr(src), rs_cfg, rs_state, rs_ctx
        )
    )
    assert actual == expected, f"evaluate divergence at nesting depth {depth}"


def test_evaluate_returns_exactly_bool_not_truthy_object() -> None:
    """`bool(...)` at the end of evaluate_skip_expr is load-bearing."""
    cfg, state, ctx = make_env()
    result = rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr("config.epochs"), cfg, state, ctx)
    assert type(result) is bool


# ---------------------------------------------------------------------------
# Specific warts, pinned individually
# ---------------------------------------------------------------------------


def test_empty_single_quote_is_none_not_empty_string() -> None:
    """`''` is Python None; `""` is the empty string. Both arms agree."""
    py_tree = py_oracle.parse_skip_expr("''")
    rs_tree = rust_impl.parse_skip_expr("''")
    assert ast_signature(py_tree) == ast_signature(rs_tree)
    assert py_tree.body.value is None
    assert rs_tree.body.value is None

    assert rust_impl.parse_skip_expr('""').body.value == ""

    # ... and therefore `'' == ""` is False, in both arms.
    cfg, state, ctx = make_env()
    assert rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr("'' == \"\""), cfg, state, ctx) is False
    assert py_oracle.evaluate_skip_expr(py_oracle.parse_skip_expr("'' == \"\""), cfg, state, ctx) is False


def test_error_position_is_character_index_not_byte_offset() -> None:
    src = "config.a == '中' @"
    with pytest.raises(Exception) as py_exc:
        py_oracle.parse_skip_expr(src)
    with pytest.raises(Exception) as rs_exc:
        rust_impl.parse_skip_expr(src)
    assert str(rs_exc.value) == str(py_exc.value)
    assert "position 16" in str(rs_exc.value)


def test_information_separator_is_stripped_like_cpython() -> None:
    """U+001C is `str.isspace()` but not Rust's `char::is_whitespace()`."""
    src = "true"
    assert outcome_signature(rust_impl.parse_skip_expr, src) == outcome_signature(
        py_oracle.parse_skip_expr, src
    )


def test_big_int_literal_is_exact() -> None:
    """Beyond i64: CPython ints are arbitrary precision."""
    src = "99999999999999999999"
    tree = rust_impl.parse_skip_expr(src)
    assert tree.body.value == 99999999999999999999
    assert type_signature(tree.body.value) == type_signature(
        py_oracle.parse_skip_expr(src).body.value
    )


def test_accessor_does_two_attribute_reads() -> None:
    """hasattr-then-getattr means a property is evaluated twice, in both arms."""

    class Counting:
        def __init__(self) -> None:
            self.reads = 0

        @property
        def probe(self) -> int:
            self.reads += 1
            return 1

    _, state, ctx = make_env()
    py_cfg, rs_cfg = Counting(), Counting()
    py_oracle.evaluate_skip_expr(py_oracle.parse_skip_expr("config.probe"), py_cfg, state, ctx)
    rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr("config.probe"), rs_cfg, state, ctx)
    assert rs_cfg.reads == py_cfg.reads == 2


def test_non_attribute_error_from_property_propagates_unchanged() -> None:
    """`hasattr` swallows only AttributeError; anything else must escape."""

    class Exploding:
        @property
        def boom(self):
            raise RuntimeError("kaboom")

    _, state, ctx = make_env()
    expected = outcome_signature(
        lambda: py_oracle.evaluate_skip_expr(
            py_oracle.parse_skip_expr("config.boom"), Exploding(), state, ctx
        )
    )
    actual = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(
            rust_impl.parse_skip_expr("config.boom"), Exploding(), state, ctx
        )
    )
    assert actual == expected
    assert expected[0] == "raise" and expected[1] == "RuntimeError"


def test_and_or_short_circuit_and_return_bool() -> None:
    """`all`/`any` over a generator: RHS not evaluated, and result is a bool."""

    class Tripwire:
        def __init__(self) -> None:
            self.touched = False

        @property
        def rhs(self) -> bool:
            self.touched = True
            return True

        @property
        def falsy(self) -> int:
            return 0

    _, state, ctx = make_env()
    cfg = Tripwire()
    out = rust_impl.evaluate_skip_expr(
        rust_impl.parse_skip_expr("config.falsy and config.rhs"), cfg, state, ctx
    )
    assert out is False
    assert cfg.touched is False, "right operand must not be evaluated"


# ---------------------------------------------------------------------------
# Vacuity traps this program has already paid for
# ---------------------------------------------------------------------------


def test_skip_expr_pickle_and_deepcopy_roundtrip() -> None:
    """#724: a pyclass is unpicklable by default and nothing noticed for 941
    assertions. The handle rides on an ast.Expression callers may copy, so
    both protocols are exercised explicitly."""
    cfg, state, ctx = make_env()
    src = "config.epochs == 100 and context.flag"
    tree = rust_impl.parse_skip_expr(src)
    expected = rust_impl.evaluate_skip_expr(tree, cfg, state, ctx)

    handle = getattr(tree, "_temper_rs_skip_expr")
    revived = pickle.loads(pickle.dumps(handle))
    assert revived.evaluate(cfg, state, ctx) == expected

    copied_handle = copy.deepcopy(handle)
    assert copied_handle.evaluate(cfg, state, ctx) == expected

    copied_tree = copy.deepcopy(tree)
    assert rust_impl.evaluate_skip_expr(copied_tree, cfg, state, ctx) == expected


def test_benchmark_inputs_are_covered_by_differential() -> None:
    """#714/#721: no benchmark parameter may exceed the differential's.

    The benchmark imports the same CORPUS and NESTING_DEPTHS from the fixture
    module. This asserts that structural fact rather than trusting it.
    """
    from . import _dag_expr_fixtures as fixtures
    from . import test_dag_expr_perf as perf

    assert perf.BENCH_CORPUS is fixtures.CORPUS
    assert perf.BENCH_DEPTHS is fixtures.NESTING_DEPTHS
    assert max(perf.BENCH_DEPTHS) == max(NESTING_DEPTHS)


def test_fallback_walker_matches_rust() -> None:
    """The compatibility walker must not drift from the Rust path.

    ``evaluate_skip_expr`` falls back to a pure-Python walk when handed an
    ast.Expression it did not build. Nothing in-tree does that, so without
    this test that branch would rot unobserved.
    """
    cfg, state, ctx = make_env()
    for src in EVAL_CORPUS:
        tree = rust_impl.parse_skip_expr(src)
        stripped = ast.Expression(body=tree.body)  # no handle attached
        assert not hasattr(stripped, "_temper_rs_skip_expr")
        expected = outcome_signature(lambda: rust_impl.evaluate_skip_expr(tree, cfg, state, ctx))
        actual = outcome_signature(
            lambda: rust_impl.evaluate_skip_expr(stripped, cfg, state, ctx)
        )
        assert actual == expected, f"fallback walker diverged for {src!r}"


def test_public_api_surface_unchanged() -> None:
    """Signatures and exported names must match the oracle exactly."""
    import inspect

    for name in ("parse_skip_expr", "evaluate_skip_expr"):
        assert inspect.signature(getattr(rust_impl, name)) == inspect.signature(
            getattr(py_oracle, name)
        ), f"{name} signature changed"

    tree = rust_impl.parse_skip_expr("true")
    assert isinstance(tree, ast.Expression)
    assert type(tree) is ast.Expression, "must be a plain ast.Expression, not a subclass"


def test_accessor_node_shape_preserved() -> None:
    """_AccessorExpr keeps its _fields, ns/field attributes and lineno."""
    node = rust_impl.parse_skip_expr("config.epochs").body
    assert type(node).__name__ == "_AccessorExpr"
    assert node._fields == ("ns", "field")
    assert (node.ns, node.field) == ("config", "epochs")
    assert (node.lineno, node.col_offset) == (1, 0)


# ---------------------------------------------------------------------------
# Witnessed divergence (R1d honesty clause)
# ---------------------------------------------------------------------------


def test_witness_deep_nesting_divergence() -> None:
    """Where the two arms STOP agreeing, pinned rather than hidden.

    Python recurses and dies with RecursionError at a depth that depends on
    ``sys.getrecursionlimit()`` and the remaining C stack. Rust cannot recurse
    unboundedly without aborting the process, so the port imposes an explicit
    ``MAX_DEPTH`` and raises DAGExprError instead.

    Both refuse deep input; they refuse it at different depths and with
    different exception types. That is a real, accepted difference. It is
    recorded here -- with the differential still covering every depth in
    NESTING_DEPTHS, all of which are below both limits -- instead of being
    concealed by quietly shrinking the tested range.
    """
    deep = nested_expr(5000)

    py_outcome = outcome_signature(py_oracle.parse_skip_expr, deep)
    rs_outcome = outcome_signature(rust_impl.parse_skip_expr, deep)

    assert py_outcome[0] == "raise"
    assert rs_outcome[0] == "raise"
    assert py_outcome[1] == "RecursionError"
    assert rs_outcome[1] == "DAGExprError"
    assert "nested deeper" in rs_outcome[2]

    # The agreed band: every depth the differential exercises is well inside
    # both limits, so the divergence cannot leak into the parity claim.
    assert max(NESTING_DEPTHS) < 180
