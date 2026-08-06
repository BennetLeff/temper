"""R1c property-based tests and R1d metamorphic relations for dag_expr.

The PBTs generate expressions from the grammar and assert the Rust port and
the pinned oracle agree by type-carrying signature. The metamorphic relations
assert structural laws that must hold for BOTH arms.

One candidate relation does NOT hold. It gets a witness test naming exactly
why (``test_witness_double_negation_is_not_identity_on_the_tree``) rather than
being quietly dropped or narrowed until it passes.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ._dag_expr_fixtures import (
    ast_signature,
    make_env,
    outcome_signature,
    py_oracle,
    rust_impl,
)

_SETTINGS = settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# ---------------------------------------------------------------------------
# Grammar-shaped strategies
# ---------------------------------------------------------------------------

_CONFIG_FIELDS = ["epochs", "seed", "dry_run", "name", "nothing", "one_int", "one_float"]
_STATE_FIELDS = ["iteration", "loss", "thermal_anchoring_applied", "routing_result"]
_CONTEXT_KEYS = ["routability", "epochs", "flag", "label", "zero", "missing_value"]

_accessors = st.one_of(
    st.sampled_from([f"config.{f}" for f in _CONFIG_FIELDS]),
    st.sampled_from([f"state.{f}" for f in _STATE_FIELDS]),
    st.sampled_from([f"context.{k}" for k in _CONTEXT_KEYS]),
    # Unknown names too: the error path is behaviour under port.
    st.sampled_from(["config.nope", "state.nope", "context.nope", "bogus.field"]),
)

_int_literals = st.integers(min_value=-(10**25), max_value=10**25).map(
    # A leading '-' is not in the grammar, so generate the magnitude only.
    lambda n: str(abs(n))
)
_float_literals = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False, width=64)
    .filter(lambda f: f >= 0)
    .map(repr),
    st.sampled_from(["0.0", "1.", ".5", "1e3", "1E3", "1e-3", "1.5e+10", "0.1"]),
)
# Surrogates are excluded DELIBERATELY and the exclusion is witnessed by
# test_witness_lone_surrogate_is_not_representable_in_rust below. A lone
# surrogate is a legal Python `str` but has no UTF-8 encoding, so it cannot
# cross the pyo3 boundary at all -- the port raises UnicodeEncodeError where
# the oracle parses happily. That is a real, accepted difference; narrowing
# the strategy without recording it would be exactly the silent narrowing this
# gate set is supposed to prevent.
_string_literals = st.text(
    alphabet=st.characters(blacklist_characters="'\"\\\n", blacklist_categories=("Cs",)),
    max_size=8,
).map(lambda s: f"'{s}'")

_literals = st.one_of(
    st.sampled_from(["true", "false", "null", "''", '""']),
    _int_literals,
    _float_literals,
    _string_literals,
)

_atoms = st.one_of(_literals, _accessors)
_cmp_ops = st.sampled_from(["==", "!=", "<", ">", "<=", ">="])


def _expressions(max_leaves: int = 12):
    def extend(children):
        return st.one_of(
            children.map(lambda c: f"not {c}"),
            children.map(lambda c: f"({c})"),
            st.tuples(children, children).map(lambda p: f"{p[0]} and {p[1]}"),
            st.tuples(children, children).map(lambda p: f"{p[0]} or {p[1]}"),
        )

    comparisons = st.tuples(_atoms, _cmp_ops, _atoms).map(lambda t: f"{t[0]} {t[1]} {t[2]}")
    return st.recursive(st.one_of(_atoms, comparisons), extend, max_leaves=max_leaves)


# ---------------------------------------------------------------------------
# R1c: properties
# ---------------------------------------------------------------------------


@_SETTINGS
@given(src=_expressions())
def test_pbt_parse_agrees(src: str) -> None:
    """PBT 1: parsing agrees on tree shape and on every error."""
    assert outcome_signature(rust_impl.parse_skip_expr, src) == outcome_signature(
        py_oracle.parse_skip_expr, src
    )


@_SETTINGS
@given(src=_expressions())
def test_pbt_evaluate_agrees(src: str) -> None:
    """PBT 2: evaluation agrees on result, result type, and error type."""
    py_env = make_env()
    rs_env = make_env()
    assert outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), *rs_env)
    ) == outcome_signature(
        lambda: py_oracle.evaluate_skip_expr(py_oracle.parse_skip_expr(src), *py_env)
    )


@_SETTINGS
@given(src=_expressions(), pad=st.text(alphabet=" \t", max_size=6))
def test_pbt_surrounding_whitespace_is_irrelevant(src: str, pad: str) -> None:
    """PBT 3: leading/trailing space and tab never change the parse.

    They are stripped before tokenizing, so this must hold for successes AND
    for error messages -- positions are measured on the STRIPPED source.
    """
    base = outcome_signature(rust_impl.parse_skip_expr, src)
    padded = outcome_signature(rust_impl.parse_skip_expr, pad + src + pad)
    assert padded == base


@_SETTINGS
@given(src=_expressions())
def test_pbt_result_is_always_bool_or_declared_error(src: str) -> None:
    """PBT 4: evaluate returns a real bool, or raises a declared type."""
    outcome = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), *make_env())
    )
    if outcome[0] == "ok":
        assert outcome[1][0] == "bool", f"non-bool result {outcome[1]} for {src!r}"
    else:
        assert outcome[1] in {
            "DAGExprError",
            "DAGExprSyntaxError",
            "TypeError",  # from CPython rich compare, e.g. `None < 1`
        }, f"undeclared exception {outcome[1]} for {src!r}"


@_SETTINGS
@given(src=_expressions())
def test_pbt_parse_is_deterministic(src: str) -> None:
    """PBT 5: parsing twice yields the identical tree.

    Guards against any hidden dependence on interning, hashing or global
    state inside the Rust constant pool.
    """
    a = outcome_signature(rust_impl.parse_skip_expr, src)
    b = outcome_signature(rust_impl.parse_skip_expr, src)
    assert a == b


@_SETTINGS
@given(
    src=_expressions(),
    order=st.permutations(_CONTEXT_KEYS),
)
def test_pbt_context_insertion_order_does_not_change_result(src: str, order) -> None:
    """PBT 6 (ordering): the context dict's INSERTION ORDER is not an input.

    dict iteration order is insertion order in CPython, and this program has
    already been bitten by order-dependent results (a solver mapping identical
    inputs to different outputs across PYTHONHASHSEED values). Rather than
    sorting anything -- which would be an undetectable behaviour change -- the
    live order is passed through and INVARIANCE IS PROVEN here.
    """
    cfg, state, base_ctx = make_env()
    reordered = {k: base_ctx[k] for k in order}
    assert list(reordered) != list(base_ctx) or list(order) == list(base_ctx)

    expected = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), cfg, state, base_ctx)
    )
    actual = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), cfg, state, reordered)
    )
    assert actual == expected


# ---------------------------------------------------------------------------
# R1d: metamorphic relations
# ---------------------------------------------------------------------------


@_SETTINGS
@given(src=_expressions())
def test_mr1_parenthesising_preserves_meaning(src: str) -> None:
    """MR1: wrapping a whole expression in parentheses changes nothing.

    Holds for the RESULT. It does not hold for the token stream, which is why
    the relation is asserted on evaluation rather than on the tree.
    """
    inner = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), *make_env())
    )
    wrapped = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(f"({src})"), *make_env())
    )
    assert wrapped == inner


@_SETTINGS
@given(src=_expressions())
def test_mr2_double_negation_preserves_the_boolean_result(src: str) -> None:
    """MR2: `not not X` evaluates to the same bool as `X`.

    True because evaluate_skip_expr coerces with `bool(...)`: `not not X` is
    the boolean projection of X, and the top level projects anyway.
    """
    plain = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), *make_env())
    )
    if plain[0] != "ok":
        return  # errors are MR-exempt; the differential already covers them
    doubled = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(
            rust_impl.parse_skip_expr(f"not not ({src})"), *make_env()
        )
    )
    assert doubled == plain


@_SETTINGS
@given(a=_expressions(max_leaves=5), b=_expressions(max_leaves=5))
def test_mr3_de_morgan(a: str, b: str) -> None:
    """MR3: `not (A and B)` == `not A or not B`, for both arms.

    A genuine semantic law, and a sharp one: it is only true because `and`/
    `or` return bools here (via all()/any()) rather than the operand values
    Python's own `and`/`or` would return.
    """
    lhs_src = f"not (({a}) and ({b}))"
    rhs_src = f"not ({a}) or not ({b})"

    lhs = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(lhs_src), *make_env())
    )
    if lhs[0] != "ok":
        return
    rhs = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(rhs_src), *make_env())
    )
    if rhs[0] != "ok":
        return  # short-circuiting can spare an error on one side only
    assert lhs == rhs

    # ... and the oracle agrees with the port on the same law.
    py_lhs = outcome_signature(
        lambda: py_oracle.evaluate_skip_expr(py_oracle.parse_skip_expr(lhs_src), *make_env())
    )
    assert py_lhs == lhs


@_SETTINGS
@given(src=_expressions())
def test_mr4_comparison_negation_duality(src: str) -> None:
    """MR4: `X == Y` and `not (X != Y)` agree whenever both evaluate."""
    eq_src = f"({src}) == ({src})"
    ne_src = f"not (({src}) != ({src}))"
    eq = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(eq_src), *make_env())
    )
    ne = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(ne_src), *make_env())
    )
    assert eq == ne


# ---------------------------------------------------------------------------
# Witnessed non-relation
# ---------------------------------------------------------------------------


def test_witness_double_negation_is_not_identity_on_the_tree() -> None:
    """A relation that does NOT hold, recorded instead of narrowed away.

    The tempting stronger form of MR2 is "`not not X` parses to the same tree
    as `X`". It does not: the parser is faithful, so `not not X` really is
    UnaryOp(Not, UnaryOp(Not, X)). Only the *evaluated* result coincides, and
    only because the top level applies `bool(...)`.

    Asserting the tree-level form and then "fixing" it by comparing evaluated
    results only would have silently weakened MR2 into something that cannot
    detect a parser that drops `not` pairs. This test pins the difference so
    that weakening is impossible.
    """
    plain = rust_impl.parse_skip_expr("config.epochs")
    doubled = rust_impl.parse_skip_expr("not not config.epochs")

    assert ast_signature(plain) != ast_signature(doubled)
    assert ast_signature(doubled) == (
        "Expression",
        ("UnaryOp", "Not", ("UnaryOp", "Not", ("_AccessorExpr", ("str", "config"), ("str", "epochs")))),
    )

    # The oracle has exactly the same non-identity -- so this is a property of
    # the specification, not a port artifact.
    assert ast_signature(py_oracle.parse_skip_expr("not not config.epochs")) == ast_signature(
        doubled
    )

    # And the evaluated results DO coincide, which is what MR2 asserts.
    cfg, state, ctx = make_env()
    assert rust_impl.evaluate_skip_expr(plain, cfg, state, ctx) is True
    assert rust_impl.evaluate_skip_expr(doubled, cfg, state, ctx) is True


def test_witness_lone_surrogate_is_not_representable_in_rust() -> None:
    """A REAL divergence, found by test_pbt_evaluate_agrees. Not narrowed away.

    ``"'\\ud800'"`` is a perfectly legal Python ``str``: CPython's internal
    representation allows unpaired surrogates. It has no UTF-8 encoding, so it
    cannot be handed to Rust as a ``&str`` at all -- pyo3 raises
    ``UnicodeEncodeError`` before the tokenizer ever runs.

    Behaviour:
      - oracle: parses, evaluates the string literal as truthy -> True
      - port:   raises UnicodeEncodeError

    Why this is accepted rather than fixed:
      - the only way to preserve it would be to keep a pure-Python parser
        alongside the Rust one and dispatch on encodability, which reinstates
        the code the port exists to remove;
      - ``str.to_string_lossy()`` is NOT an option: it would substitute U+FFFD
        and silently change what the expression means, which is worse than
        raising;
      - the input is unreachable through the real pipeline. `skip_if` comes
        from a YAML manifest parsed by ``yaml.safe_load`` from a UTF-8 file,
        and a lone surrogate cannot survive UTF-8 decoding, so no manifest can
        express one.

    The PBT string strategy excludes category Cs, pointing here.
    """
    src = "'\ud800'"
    cfg, state, ctx = make_env()

    py_outcome = outcome_signature(
        lambda: py_oracle.evaluate_skip_expr(py_oracle.parse_skip_expr(src), cfg, state, ctx)
    )
    rs_outcome = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), cfg, state, ctx)
    )

    assert py_outcome == ("ok", ("bool", "True"))
    assert rs_outcome[0] == "raise"
    assert rs_outcome[1] == "UnicodeEncodeError"
    assert py_outcome != rs_outcome, "if these ever agree, delete this witness"

    # The boundary is encodability, not "contains a high codepoint": a valid
    # astral character round-trips through the port unchanged.
    astral = "'\U0001f600'"
    assert outcome_signature(rust_impl.parse_skip_expr, astral) == outcome_signature(
        py_oracle.parse_skip_expr, astral
    )


def test_witness_and_or_do_not_return_the_operand() -> None:
    """Another non-relation: this `and` is NOT Python's `and`.

    Python's `a and b` returns b (the object). This grammar's `and` is
    implemented with `all(...)`, so it returns a bool. A port that "helpfully"
    used Rust's short-circuit to return the operand would pass a naive
    truthiness comparison and fail here.
    """
    cfg, state, ctx = make_env()
    # `config.epochs` is 100 (truthy, not a bool).
    out = rust_impl.evaluate_skip_expr(
        rust_impl.parse_skip_expr("true and config.epochs"), cfg, state, ctx
    )
    assert out is True
    assert type(out) is bool

    tree = rust_impl.parse_skip_expr("true and config.epochs")
    handle = tree._temper_rs_skip_expr
    assert handle.evaluate(cfg, state, ctx) is True


@pytest.mark.parametrize("src", ["config.nothing < 1", "config.name < 1", "null < 1"])
def test_type_error_from_rich_compare_is_cpythons_own(src: str) -> None:
    """Comparison errors must be CPython's, message included."""
    env = make_env()
    expected = outcome_signature(
        lambda: py_oracle.evaluate_skip_expr(py_oracle.parse_skip_expr(src), *env)
    )
    actual = outcome_signature(
        lambda: rust_impl.evaluate_skip_expr(rust_impl.parse_skip_expr(src), *env)
    )
    assert actual == expected
    assert expected[1] == "TypeError"
