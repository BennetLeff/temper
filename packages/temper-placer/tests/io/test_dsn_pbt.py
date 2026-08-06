"""Property-based tests for the migrated DSN surface.

Wave 4, Phase 3 — candidate 6 (gates R1c, R1d). Companion to
``test_dsn_rust_differential.py``, which pins fixed inputs; this suite searches
the input space for a divergence the fixtures did not think of.

``dsn_exporter`` — properties:

- E1. Byte parity under search: for ANY generated board+netlist, the migrated
  exporter's ``export_pcb`` bytes equal the pinned oracle's, exactly.
- E2. Structural parity under search: the expression trees agree leaf-for-leaf,
  with floats compared as ``float.hex()`` and every non-float leaf carrying its
  concrete type, so an int/float drift cannot pass on rendered equality.
- E3. Component totality: every component reference appears exactly once in the
  placement section, for any netlist.
- E4. Deterministic-mode order invariance: permuting the input component and
  net lists leaves the emitted bytes unchanged.
- E5. Net exclusion totality: excluding every net name leaves no ``(net ...)``
  form, and excluding none leaves every non-empty net present.
- E6. Structural well-formedness: the emitted text is balanced-parenthesized
  once quoted tokens are accounted for.

``dsn`` (primitives) — properties:

- P1. ``str(dsn_list(...))`` matches the pinned Python for any argument tuple
  drawn from the types the DSN emitter can produce.
- P2. Float rendering is the ``{:.6f}``-then-trim convention, exactly.
- P3. Quoting is exactly "quote iff the token contains a space, a parenthesis
  or a double quote, or is empty", with ``"`` escaped.
- P4. Nesting is compositional: a nested expression renders as its own
  rendering, substituted in place.
- P5. ``with_comment`` prepends ``";<line>\\n"`` and changes nothing else.
- P6. Shape helpers (``DSNRect``/``DSNCircle``/``DSNPath``) render identically
  to the pinned Python for any geometry.

Metamorphic relations (R1d), each honestly bounded:

- MR1. Uniform pad translation is absorbed by the image's self-centering, so
  ``export_library`` is invariant while ``export_placement`` moves. Bounded:
  exact only for translations that subtract back exactly in binary floating
  point, so the strategy draws dyadic offsets; the general case is not claimed.
- MR2. Sanitization is idempotent — a net already named with ``_PLUS``/
  ``_MINUS`` is unchanged by a second pass. Bounded: stated over the emitted
  net name only, not over classification, which reads the sanitized name.
- MR3. Keepout count monotonicity: appending a keepout adds exactly one
  ``(keepout ...)`` form and leaves the layer/boundary prefix untouched.
  Bounded: the ordering of the resulting set is the pinned string sort, which
  is asserted against the oracle rather than restated here.

Every property carries a G4 vacuity mutant: a degenerate kernel is swapped in
through the ``_kernels`` indirection and the property's inner test re-run,
asserting it fails. A property no mutant can break is not a property.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import tests.io._dsn_exporter_py_oracle as _oracle
import tests.io._dsn_py_oracle as _dsn_oracle
from temper_placer.core.board import Board, Layer, LayerStackup
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.dsn import DSNCircle, DSNExpression, DSNPath, DSNRect, dsn_list
from temper_placer.io.dsn_exporter import DSNExporter
from tests.io.test_dsn_rust_differential import canon

MAX_EXAMPLES = 40
SETTINGS = settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------

# Names are kept to the character classes a KiCad design actually produces plus
# the DSN-significant punctuation, so quoting and sanitization are exercised
# without drifting into the documented Unicode bounds (non-ASCII decimal digits
# in a natural-sort key; see VERIFICATION.md).
_NAME_CHARS = st.sampled_from(list("abcXYZ019_.-+/: ()\""))
_NAME = st.text(_NAME_CHARS, min_size=0, max_size=8)
_REF = st.text(st.sampled_from(list("URCJQ012ab")), min_size=1, max_size=4)

# Finite, board-scale coordinates. Values that land on exact .5 ticks after the
# x100 scale are drawn deliberately, since that is where the rounding mode is
# observable.
_COORD = st.one_of(
    st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    st.sampled_from([0.005, -0.005, 0.015, 0.025, -0.025, 0.035, 0.0, -0.0]),
)
_DIM = st.one_of(
    st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    st.sampled_from([0.0005, 0.0015, 0.0025, 0.9995, 1.0 / 3.0]),
)
_SHAPE = st.sampled_from(["rect", "circle", "oval", "roundrect", "thru_hole", ""])
_LAYER = st.sampled_from(["F.Cu", "B.Cu", "In1.Cu", "In2.Cu", "all"])


@st.composite
def _pins(draw, min_size=0, max_size=4):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return [
        Pin(
            name=draw(_NAME) or "p",
            number=draw(st.text(st.sampled_from(list("0123456789ab-")), min_size=0, max_size=4)),
            position=(draw(_COORD), draw(_COORD)),
            width=draw(_DIM),
            height=draw(_DIM),
            shape=draw(_SHAPE),
            layer=draw(_LAYER),
        )
        for _ in range(n)
    ]


@st.composite
def _components(draw, min_size=0, max_size=4):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return [
        Component(
            ref=f"{draw(_REF)}{i}",
            footprint=draw(_NAME) or "fp",
            bounds=(1.0, 1.0),
            pins=draw(_pins()),
            initial_position=draw(st.one_of(st.none(), st.tuples(_COORD, _COORD))),
            initial_rotation=draw(st.one_of(st.none(), st.integers(min_value=0, max_value=3))),
        )
        for i in range(n)
    ]


@st.composite
def _netlists(draw):
    comps = draw(_components())
    refs = [c.ref for c in comps]
    nets = []
    if refs:
        n = draw(st.integers(min_value=0, max_value=4))
        for _ in range(n):
            pin_refs = draw(
                st.lists(
                    st.tuples(st.sampled_from(refs), st.sampled_from(["0", "1", "2", "10", "x"])),
                    max_size=4,
                )
            )
            nets.append(Net(name=draw(_NAME), pins=pin_refs))
    return Netlist(components=comps, nets=nets)


@st.composite
def _boards(draw):
    stackup = draw(
        st.one_of(
            st.none(),
            st.just(
                LayerStackup(
                    layers=[
                        Layer(name="F.Cu", layer_type="signal"),
                        Layer(name="In1.Cu", layer_type="plane"),
                        Layer(name="In2.Cu", layer_type="mixed"),
                        Layer(name="B.Cu", layer_type="signal"),
                    ]
                )
            ),
        )
    )
    board = Board(
        width=draw(st.floats(min_value=0.001, max_value=500.0, allow_nan=False)),
        height=draw(st.floats(min_value=0.001, max_value=500.0, allow_nan=False)),
        keepouts=draw(st.lists(st.tuples(_COORD, _COORD, _COORD, _COORD), max_size=13)),
    )
    # Assigned after construction: Board.__post_init__ substitutes a default
    # 4-layer stackup for a falsy one, and the `None` case must be reachable.
    board.layer_stackup = stackup
    return board


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _Kernels:
    """Every kernel a property depends on, swappable for mutation testing."""

    exporter = staticmethod(lambda *a, **k: DSNExporter(*a, **k))
    dsn_list = staticmethod(lambda name, *args: dsn_list(name, *args))
    rect = staticmethod(lambda *a: DSNRect(*a))
    circle = staticmethod(lambda *a: DSNCircle(*a))
    path = staticmethod(lambda *a: DSNPath(*a))


_kernels = _Kernels()

_KERNEL_NAMES = ("exporter", "dsn_list", "rect", "circle", "path")


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


def _assert_property_fails(property_fn, *args):
    """Run a hypothesis-wrapped property's inner test and require a failure.

    A mutant that the property tolerates means the property is vacuous.
    """
    with pytest.raises((AssertionError, KeyError, AttributeError, TypeError, IndexError)):
        property_fn.hypothesis.inner_test(*args)


def _balanced(text: str) -> bool:
    """Parenthesis balance, skipping quoted tokens and the comment line."""
    depth = 0
    in_quote = False
    escaped = False
    for line in text.split("\n"):
        if line.startswith(";"):
            continue
        for ch in line:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_quote = not in_quote
            elif not in_quote:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth < 0:
                        return False
    return depth == 0 and not in_quote


# ---------------------------------------------------------------------------
# dsn_exporter — properties
# ---------------------------------------------------------------------------


@SETTINGS
@given(board=_boards(), netlist=_netlists(), deterministic=st.booleans())
def test_e1_export_pcb_bytes_match_the_pinned_python(board, netlist, deterministic):
    """E1: the emitted DSN is byte-identical to the pre-migration output."""
    rust = _kernels.exporter(board, netlist, deterministic=deterministic)
    py = _oracle.DSNExporter(board, netlist, deterministic=deterministic)
    assert str(rust.export_pcb("t")) == str(py.export_pcb("t"))


@SETTINGS
@given(board=_boards(), netlist=_netlists())
def test_e2_expression_trees_match_leaf_for_leaf(board, netlist):
    """E2: structural parity, floats as exact bit patterns and types pinned."""
    rust = _kernels.exporter(board, netlist)
    py = _oracle.DSNExporter(board, netlist)
    for section in ("export_structure", "export_library", "export_placement", "export_network"):
        assert canon(getattr(rust, section)()) == canon(getattr(py, section)()), section


@SETTINGS
@given(board=_boards(), netlist=_netlists())
def test_e3_every_component_is_placed_exactly_once(board, netlist):
    """E3: placement is total — one `(place <ref> ...)` per component."""
    rust = _kernels.exporter(board, netlist)
    text = str(rust.export_placement())
    for comp in netlist.components:
        assert text.count(f"(place {comp.ref} ") == 1, comp.ref


@SETTINGS
@given(board=_boards(), netlist=_netlists())
def test_e4_deterministic_output_is_input_order_invariant(board, netlist):
    """E4: permuting the inputs cannot change deterministic-mode bytes.

    Bounded to netlists whose component refs and net names are DISTINCT. With
    duplicates the sort keys tie, and Python's stable sort — which the port
    reproduces — is then *required* to preserve input order, so a permutation
    legitimately changes the output. Asserting invariance there would be
    asserting a bug.
    """
    assume(len({c.ref for c in netlist.components}) == len(netlist.components))
    assume(len({n.name for n in netlist.nets}) == len(netlist.nets))
    shuffled = Netlist(
        components=list(reversed(netlist.components)),
        nets=list(reversed(netlist.nets)),
    )
    a = _kernels.exporter(board, netlist, deterministic=True)
    b = _kernels.exporter(board, shuffled, deterministic=True)
    assert str(a.export_placement()) == str(b.export_placement())
    assert str(a.export_network()) == str(b.export_network())


@SETTINGS
@given(board=_boards(), netlist=_netlists())
def test_e5_excluding_every_net_empties_the_network(board, netlist):
    """E5: exclusion is total, and non-exclusion drops no non-empty net."""
    rust = _kernels.exporter(board, netlist)
    everything = {n.name for n in netlist.nets} | {
        n.name.replace("+", "_PLUS").replace("-", "_MINUS") for n in netlist.nets
    }
    assert "(net " not in str(rust.export_network(exclude_nets=everything))
    kept = str(rust.export_network(exclude_nets=set()))
    for net in netlist.nets:
        if net.pins:
            clean = net.name.replace("+", "_PLUS").replace("-", "_MINUS")
            token = clean if not set(' ()"') & set(clean) and clean else None
            if token is not None:
                assert f"(net {token} " in kept, clean


@SETTINGS
@given(board=_boards(), netlist=_netlists(), deterministic=st.booleans())
def test_e6_emitted_text_is_balanced(board, netlist, deterministic):
    """E6: the emitted S-expression is well formed for any input."""
    rust = _kernels.exporter(board, netlist, deterministic=deterministic)
    text = str(rust.export_pcb("t"))
    assert _balanced(text), text[:400]


# ---------------------------------------------------------------------------
# dsn_exporter — G4 vacuity mutants
# ---------------------------------------------------------------------------


def _degenerate_board():
    b = Board(width=1.005, height=2.015, keepouts=[(0.0, 0.0, 1.0, 1.0), (2.0, 2.0, 3.0, 3.0)])
    b.layer_stackup = None
    return b


def _degenerate_netlist():
    return Netlist(
        components=[
            Component(ref="U1", footprint="fp", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (0.5, 0.5), width=0.5, height=0.5)]),
            Component(ref="U2", footprint="fp", bounds=(1.0, 1.0),
                      pins=[Pin("1", "2", (1.5, 1.5), width=0.5, height=0.5)]),
        ],
        nets=[Net(name="A", pins=[("U1", "1")]), Net(name="B", pins=[("U2", "2")])],
    )


class _NoopExporter:
    """A kernel that emits a constant — no property may survive it."""

    def __init__(self, *a, **k):
        pass

    def _empty(self, *a, **k):
        return dsn_list("empty")

    export_pcb = _empty
    export_structure = _empty
    export_library = _empty
    export_placement = _empty
    export_network = _empty


def test_e1_fails_for_constant_exporter(_restore_kernels):
    _kernels.exporter = _NoopExporter
    _assert_property_fails(
        test_e1_export_pcb_bytes_match_the_pinned_python,
        _degenerate_board(), _degenerate_netlist(), True,
    )


def test_e2_fails_for_constant_exporter(_restore_kernels):
    _kernels.exporter = _NoopExporter
    _assert_property_fails(
        test_e2_expression_trees_match_leaf_for_leaf,
        _degenerate_board(), _degenerate_netlist(),
    )


def test_e3_fails_for_dropping_exporter(_restore_kernels):
    class _DropsSecondComponent(DSNExporter):
        def export_placement(self):
            text = super().export_placement()
            return dsn_list("placement", *list(text.args)[:1])

    _kernels.exporter = _DropsSecondComponent
    _assert_property_fails(
        test_e3_every_component_is_placed_exactly_once,
        _degenerate_board(), _degenerate_netlist(),
    )


@pytest.mark.filterwarnings("ignore::hypothesis.errors.HypothesisDeprecationWarning")
def test_e4_fails_for_input_order_dependent_exporter(_restore_kernels):
    class _NonDeterministic(DSNExporter):
        def __init__(self, board, netlist, **kwargs):
            kwargs["deterministic"] = False
            super().__init__(board, netlist, **kwargs)

    _kernels.exporter = _NonDeterministic
    netlist = Netlist(
        components=[
            Component(ref="AA", footprint="a", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (0.0, 0.0))]),
            Component(ref="BB", footprint="b", bounds=(1.0, 1.0),
                      pins=[Pin("1", "1", (1.0, 1.0))]),
        ],
        nets=[],
    )
    _assert_property_fails(
        test_e4_deterministic_output_is_input_order_invariant, _degenerate_board(), netlist
    )


def test_e5_fails_for_exclusion_ignoring_exporter(_restore_kernels):
    class _IgnoresExclusion(DSNExporter):
        def export_network(self, use_net_classes=True, exclude_nets=None):
            return super().export_network(use_net_classes, None)

    _kernels.exporter = _IgnoresExclusion
    _assert_property_fails(
        test_e5_excluding_every_net_empties_the_network,
        _degenerate_board(), _degenerate_netlist(),
    )


def test_e6_fails_for_unbalanced_emitter(_restore_kernels):
    class _RawUnbalanced:
        # Renders raw, UNQUOTED text — a quoted token would be skipped by the
        # balance walker and the mutant would survive vacuously.
        def __str__(self):
            return "(pcb (structure (("

    class _Unbalanced(DSNExporter):
        def export_pcb(self, *a, **k):
            return _RawUnbalanced()

    _kernels.exporter = _Unbalanced
    _assert_property_fails(
        test_e6_emitted_text_is_balanced, _degenerate_board(), _degenerate_netlist(), True
    )


# ---------------------------------------------------------------------------
# dsn primitives — properties
# ---------------------------------------------------------------------------


_ARG = st.one_of(
    st.text(_NAME_CHARS, max_size=10),
    st.integers(min_value=-(10**18), max_value=10**18),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
)


@SETTINGS
@given(name=st.text(st.sampled_from(list("abcXYZ_")), min_size=1, max_size=6),
       args=st.lists(_ARG, max_size=6))
def test_p1_dsn_list_rendering_matches_the_pinned_python(name, args):
    """P1: rendering parity for any argument tuple the emitter can produce."""
    assert str(_kernels.dsn_list(name, *args)) == str(_dsn_oracle.dsn_list(name, *args))


@SETTINGS
@given(value=st.floats(allow_nan=False, allow_infinity=False, width=64))
def test_p2_float_rendering_is_the_pinned_trim_convention(value):
    """P2: `f"{v:.6f}"` then strip trailing zeros then the trailing dot."""
    rendered = str(_kernels.dsn_list("v", value))
    expected_body = f"{value:.6f}".rstrip("0").rstrip(".")
    assert rendered == f"(v {expected_body})"
    assert rendered == str(_dsn_oracle.dsn_list("v", value))


@SETTINGS
@given(token=st.text(_NAME_CHARS, max_size=12))
def test_p3_quoting_rule_is_exact(token):
    """P3: quote iff empty or containing a space, a paren, or a double quote."""
    rendered = str(_kernels.dsn_list("v", token))
    body = rendered[len("(v ") : -1]
    needs_quote = (not token) or bool(set(' ()"') & set(token))
    assert body.startswith('"') == needs_quote, (token, body)
    assert rendered == str(_dsn_oracle.dsn_list("v", token))


@SETTINGS
@given(outer=st.text(st.sampled_from(list("abc")), min_size=1, max_size=4),
       inner=st.text(st.sampled_from(list("xyz")), min_size=1, max_size=4),
       args=st.lists(_ARG, max_size=3))
def test_p4_nesting_is_compositional(outer, inner, args):
    """P4: a nested expression renders as its own rendering, substituted in."""
    child = _kernels.dsn_list(inner, *args)
    parent = _kernels.dsn_list(outer, child)
    assert str(parent) == f"({outer} {child})"
    py_child = _dsn_oracle.dsn_list(inner, *args)
    assert str(parent) == str(_dsn_oracle.dsn_list(outer, py_child))


@SETTINGS
@given(name=st.text(st.sampled_from(list("abc")), min_size=1, max_size=4),
       args=st.lists(_ARG, max_size=4),
       line=st.text(st.sampled_from(list("abc: 0123456789sha")), max_size=20))
def test_p5_with_comment_prepends_exactly_one_line(name, args, line):
    """P5: `with_comment` prepends ";<line>\\n" iff the line is TRUTHY.

    The empty-string case is not an edge case to tolerate but the rule itself:
    the renderer tests `if self.comment:`, so `with_comment("")` must leave the
    output untouched rather than emit a bare ";" line.
    """
    base = _kernels.dsn_list(name, *args)
    body = str(base)
    expected = f";{line}\n{body}" if line else body
    assert str(base.with_comment(line)) == expected
    py = _dsn_oracle.dsn_list(name, *args)
    assert str(base.with_comment(line)) == str(py.with_comment(line))


@SETTINGS
@given(
    layer=st.text(_NAME_CHARS, max_size=8),
    a=st.floats(allow_nan=False, allow_infinity=False, width=64),
    b=st.floats(allow_nan=False, allow_infinity=False, width=64),
    c=st.floats(allow_nan=False, allow_infinity=False, width=64),
    d=st.floats(allow_nan=False, allow_infinity=False, width=64),
    points=st.lists(
        st.tuples(
            st.floats(allow_nan=False, allow_infinity=False, width=64),
            st.floats(allow_nan=False, allow_infinity=False, width=64),
        ),
        max_size=5,
    ),
)
def test_p6_shape_helpers_match_the_pinned_python(layer, a, b, c, d, points):
    """P6: the rect/circle/path helpers render identically to the oracle."""
    assert str(_kernels.rect(layer, a, b, c, d).to_dsn()) == str(
        _dsn_oracle.DSNRect(layer, a, b, c, d).to_dsn()
    )
    assert str(_kernels.circle(layer, a, b, c).to_dsn()) == str(
        _dsn_oracle.DSNCircle(layer, a, b, c).to_dsn()
    )
    assert str(_kernels.path(layer, a, points).to_dsn()) == str(
        _dsn_oracle.DSNPath(layer, a, points).to_dsn()
    )


# ---------------------------------------------------------------------------
# dsn primitives — G4 vacuity mutants
# ---------------------------------------------------------------------------


def test_p1_fails_for_constant_renderer(_restore_kernels):
    _kernels.dsn_list = staticmethod(lambda name, *_args: dsn_list(name))
    _assert_property_fails(
        test_p1_dsn_list_rendering_matches_the_pinned_python, "a", [1, "x"]
    )


def test_p2_fails_for_wrong_precision_kernel(_restore_kernels):
    class _FivePlaces:
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return f"(v {f'{self.value:.5f}'.rstrip('0').rstrip('.')})"

    _kernels.dsn_list = staticmethod(lambda _name, *args: _FivePlaces(args[0]))
    _assert_property_fails(test_p2_float_rendering_is_the_pinned_trim_convention, 0.1234567)


def test_p3_fails_for_always_quoting_kernel(_restore_kernels):
    class _AlwaysQuotes:
        def __init__(self, token):
            self.token = token

        def __str__(self):
            return f'(v "{self.token}")'

    _kernels.dsn_list = staticmethod(lambda _name, *args: _AlwaysQuotes(args[0]))
    _assert_property_fails(test_p3_quoting_rule_is_exact, "GND")


def test_p4_fails_for_flattening_kernel(_restore_kernels):
    real = dsn_list

    def _flatten(name, *args):
        return real(name, *[str(a) if isinstance(a, DSNExpression) else a for a in args])

    _kernels.dsn_list = staticmethod(_flatten)
    _assert_property_fails(test_p4_nesting_is_compositional, "a", "x", ["has space"])


def test_p5_fails_for_comment_dropping_kernel(_restore_kernels):
    class _DropsComment:
        def __init__(self, expr):
            self.expr = expr

        def with_comment(self, line):
            return self.expr

        def __str__(self):
            return str(self.expr)

    _kernels.dsn_list = staticmethod(lambda name, *args: _DropsComment(dsn_list(name, *args)))
    _assert_property_fails(test_p5_with_comment_prepends_exactly_one_line, "a", [1], "hi")


def test_p6_fails_for_axis_swapping_kernel(_restore_kernels):
    _kernels.rect = staticmethod(lambda layer, x1, y1, x2, y2: DSNRect(layer, y1, x1, y2, x2))
    _assert_property_fails(
        test_p6_shape_helpers_match_the_pinned_python, "F.Cu", 1.0, 2.0, 3.0, 4.0, []
    )


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d)
# ---------------------------------------------------------------------------


_DYADIC = st.sampled_from([0.0, 0.25, 0.5, 1.0, -0.5, 2.0, -4.0, 0.125])


@SETTINGS
@given(dx=_DYADIC, dy=_DYADIC)
def test_mr1_uniform_pad_translation_is_absorbed_by_the_image(dx, dy):
    """MR1: translating every pad alike leaves the image identical.

    Bounded to dyadic offsets, where the self-centering subtraction is exact in
    binary floating point. The general float case is not claimed.
    """
    def _netlist(ox, oy):
        return Netlist(
            components=[
                Component(
                    ref="U1", footprint="fp", bounds=(4.0, 4.0),
                    pins=[
                        Pin("1", "1", (-1.0 + ox, -1.0 + oy), width=0.5, height=0.5),
                        Pin("2", "2", (1.0 + ox, 1.0 + oy), width=0.5, height=0.5),
                    ],
                    initial_position=(10.0, 10.0),
                )
            ]
        )

    board = Board(width=40.0, height=40.0)
    base = _kernels.exporter(board, _netlist(0.0, 0.0))
    moved = _kernels.exporter(board, _netlist(dx, dy))
    assert str(base.export_library()) == str(moved.export_library())
    if (dx, dy) != (0.0, 0.0):
        assert str(base.export_placement()) != str(moved.export_placement())


@SETTINGS
@given(name=st.text(st.sampled_from(list("abAB01+-_")), min_size=1, max_size=8))
def test_mr2_net_name_sanitization_is_idempotent(name):
    """MR2: sanitizing an already-sanitized name is a no-op.

    Bounded to the emitted net NAME; classification reads the sanitized name
    and is therefore not claimed invariant here.
    """
    once = name.replace("+", "_PLUS").replace("-", "_MINUS")
    twice = once.replace("+", "_PLUS").replace("-", "_MINUS")
    assert once == twice

    board = Board(width=10.0, height=10.0)

    def _nl(n):
        return Netlist(
            components=[Component(ref="U1", footprint="f", bounds=(1.0, 1.0),
                                  pins=[Pin("1", "1", (0.0, 0.0))])],
            nets=[Net(name=n, pins=[("U1", "1")])],
        )

    a = str(_kernels.exporter(board, _nl(name)).export_network())
    b = str(_kernels.exporter(board, _nl(once)).export_network())
    assert a == b


@SETTINGS
@given(keepouts=st.lists(st.tuples(_COORD, _COORD, _COORD, _COORD), min_size=0, max_size=6),
       extra=st.tuples(_COORD, _COORD, _COORD, _COORD))
def test_mr3_appending_a_keepout_adds_exactly_one_form(keepouts, extra):
    """MR3: one more keepout in, exactly one more `(keepout ...)` out.

    Bounded: the RESULTING ORDER is the pinned string sort over "KO_<i>", which
    the differential asserts against the oracle rather than this relation
    restating it.
    """
    def _board(kos):
        b = Board(width=50.0, height=50.0, keepouts=list(kos))
        b.layer_stackup = None
        return b

    before = str(_kernels.exporter(_board(keepouts), Netlist()).export_structure())
    after = str(_kernels.exporter(_board([*keepouts, extra]), Netlist()).export_structure())
    assert after.count("(keepout ") == before.count("(keepout ") + 1
    assert before.count("(keepout ") == len(keepouts)


def test_mr_relations_are_discriminating(_restore_kernels):
    """The relations above must all be breakable — otherwise they are decor."""
    class _IgnoresCentering(DSNExporter):
        def export_library(self):
            # Emit the raw pin positions, defeating the self-centering.
            return dsn_list("library", str(self.netlist.components[0].pins[0].position))

    _kernels.exporter = _IgnoresCentering
    _assert_property_fails(test_mr1_uniform_pad_translation_is_absorbed_by_the_image, 0.25, 0.5)

    _kernels.exporter = staticmethod(lambda *_a, **_k: _NoopExporter())
    _assert_property_fails(test_mr3_appending_a_keepout_adds_exactly_one_form, [], (0.0, 0.0, 1.0, 1.0))
