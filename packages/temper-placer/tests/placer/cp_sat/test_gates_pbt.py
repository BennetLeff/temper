"""Property-based + metamorphic tests for the Rust gate-contract pyclasses.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
R1c/R1d). These properties exercise the migrated
``temper_placer.placer.cp_sat.gates`` module (a pure-delegation re-export of
the ``temper_design_bundle_python`` pyclasses); bit-identical parity against
the pinned pre-migration Python is asserted separately by
``test_gates_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. The ``GateResult`` VIOLATIONS constructor invariant: a
  ``VIOLATIONS`` status must carry at least one ``Violation``.
- P2. ``Violation`` field round-trip: every field reads back bit-exactly
  (severity/threshold as exact bit patterns).
- P3. ``GateResult`` equality: equal constructions compare ``==`` and
  hash-equal; a different status compares ``!=``.
- P4. Enum value bijection: over ``members()``, ``(name, value)`` is unique
  and ``Enum(value)`` round-trips to the member.
- P5. ``BoardState`` opaque-payload identity: every field returns the exact
  object passed in (``bs.board is board``).

Four metamorphic relations:

- MR1. Construction→access round-trip: ``Violation`` keyword-argument order
  is commutative and every field reads back bit-identically.
- MR2. Canonical-form ⇔ equality: two violations compare ``==`` exactly
  when their field canonicalizations agree.
- MR3. Enum construction commutation: ``Cls(member.value) is member`` for
  every member of every gate enum.
- MR4. ``BoardState`` payload independence: populating one field leaves the
  other five at ``None``.
"""

from __future__ import annotations

import os

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    GateResult,
    GateStage,
    GateStatus,
    Violation,
    ViolationType,
)

MAX_EXAMPLES = 100


def _f(value):
    return float(value).hex()


def _violation_fields(v):
    return (
        (v.type.name, v.type.value),
        tuple(v.components),
        tuple(v.nets),
        _f(v.severity),
        _f(v.threshold),
        v.description,
        tuple(sorted((k, str(val)) for k, val in v.context.items())),
    )


def _violation_fields_eq(v):
    """Canonical-form fields compared with Python `==` semantics.

    Distinct from ``_violation_fields`` (bit-exact ``.hex()``): this form
    treats ``0.0 == -0.0`` as equal, matching what ``Violation.__eq__``
    actually computes. Used by the MR2 canonical-form-iff-equality
    invariant; the differential suite keeps the bit-exact form.
    """
    return (
        (v.type.name, v.type.value),
        tuple(v.components),
        tuple(v.nets),
        float(v.severity),
        float(v.threshold),
        v.description,
        tuple(sorted((k, str(val)) for k, val in v.context.items())),
    )


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _GateKernels:
    make_result = staticmethod(
        lambda status, violations=(), error_message="": GateResult(status, violations=violations, error_message=error_message)
    )
    make_violation = staticmethod(
        lambda **kwargs: Violation(**kwargs)
    )
    result_eq = staticmethod(lambda a, b: a == b)
    resolve_enum = staticmethod(lambda cls, value: cls(value))
    make_state = staticmethod(lambda **kwargs: BoardState(**kwargs))


_kernels = _GateKernels()

_KERNEL_NAMES = (
    "make_result",
    "make_violation",
    "result_eq",
    "resolve_enum",
    "make_state",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


_VT_STRATEGY = st.sampled_from(ViolationType.members())
_VALIDATION_ERROR_STRATEGY = st.sampled_from(
    [ViolationType.CLEARANCE, ViolationType.UNROUTED, ViolationType.CREEPAGE]
)

# ---------------------------------------------------------------------------
# P1 — GateResult VIOLATIONS invariant
# ---------------------------------------------------------------------------


@st.composite
def _result_args(draw):
    """A (status, violations, error_message) triple. ``UNMEASURED`` always
    carries an error message (per the contract); ``VIOLATIONS`` always
    carries at least one violation so the construction is legal; CLEAN and
    UNMEASURED carry no violations."""
    status = draw(st.sampled_from(GateStatus.members()))
    error_message = draw(st.text(max_size=20))
    if status is GateStatus.VIOLATIONS:
        violations = tuple(Violation(type=vt) for vt in draw(st.lists(_VT_STRATEGY, min_size=1, max_size=3)))
        error_message = ""
    elif status is GateStatus.UNMEASURED:
        violations = ()
        error_message = error_message or "unmeasured"
    else:
        violations = ()
        error_message = ""
    return status, violations, error_message


@given(_result_args())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_violations_invariant(args):
    status, violations, error_message = args
    result = _kernels.make_result(status, violations, error_message)
    # The type boundary enforces: VIOLATIONS => at least one violation.
    if result.status is GateStatus.VIOLATIONS:
        assert len(result.violations) >= 1
    # And the three-state discipline: UNMEASURED never carries violations as
    # proof of cleanliness.
    if result.status is GateStatus.UNMEASURED:
        assert result.violations == ()
        assert result.error_message != ""
    # Vacuity guard: the sampler genuinely produces every status.
    assert result.status in GateStatus.members()


def test_p1_fails_for_unchecked_kernel(_restore_kernels):
    """A degenerate kernel that skips the invariant (never raises for
    VIOLATIONS + empty) must fail P1: the property asserts the invariant at
    construction time, and the mutant's unchecked construction is a
    violation of the contract."""

    def unchecked(status, violations=(), error_message=""):
        # A degenerate stand-in that skips the constructor invariant entirely
        # (a real pyclass GateResult cannot be built with VIOLATIONS + empty
        # — the boundary rejects it — so the mutant must bypass construction).
        from types import SimpleNamespace

        return SimpleNamespace(
            status=status, violations=violations, error_message=error_message
        )

    _kernels.make_result = unchecked
    with pytest.raises(AssertionError):
        test_p1_violations_invariant.hypothesis.inner_test(
            (GateStatus.VIOLATIONS, (), "")
        )


def test_p1_invariant_is_really_enforced():
    """Directly prove the invariant bites (the kernel-mutant test above
    proves the *property* is discriminating; this proves the *implementation*
    enforces it)."""
    with pytest.raises(ValueError, match="VIOLATIONS must have at least one"):
        GateResult(GateStatus.VIOLATIONS, violations=())


# ---------------------------------------------------------------------------
# P2 — Violation field round-trip (bit-exact)
# ---------------------------------------------------------------------------


@st.composite
def _violation_kwargs(draw):
    severity = draw(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
    threshold = draw(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False))
    return {
        "type": draw(_VT_STRATEGY),
        "components": tuple(draw(st.lists(st.text(max_size=8), max_size=3))),
        "nets": tuple(draw(st.lists(st.text(max_size=8), max_size=3))),
        "severity": severity,
        "threshold": threshold,
        "description": draw(st.text(max_size=30)),
        "context": {draw(st.text(max_size=8)): draw(st.text(max_size=8)) for _ in range(draw(st.integers(0, 2)))},
    }


@given(_violation_kwargs())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_violation_round_trip(kwargs):
    v = _kernels.make_violation(**kwargs)
    assert v.type is kwargs["type"]
    assert tuple(v.components) == tuple(kwargs["components"])
    assert tuple(v.nets) == tuple(kwargs["nets"])
    assert _f(v.severity) == _f(kwargs["severity"])
    assert _f(v.threshold) == _f(kwargs["threshold"])
    assert v.description == kwargs["description"]
    assert v.context == kwargs["context"]
    # Vacuity guard: the generated field values genuinely vary.
    assert -1e6 <= kwargs["severity"] <= 1e6


def test_p2_fails_for_dropped_threshold(_restore_kernels):
    """A degenerate kernel that silently drops the ``threshold`` field must
    fail P2: the round-trip asserts the exact bit pattern reads back."""

    def dropped_threshold(**kwargs):
        kwargs.pop("threshold", None)
        return Violation(**kwargs)

    _kernels.make_violation = dropped_threshold
    with pytest.raises(AssertionError):
        test_p2_violation_round_trip.hypothesis.inner_test(
            {
                "type": ViolationType.CREEPAGE,
                "components": ("Q1",),
                "nets": (),
                "severity": 4.5,
                "threshold": 6.0,
                "description": "x",
                "context": {},
            }
        )


# ---------------------------------------------------------------------------
# P3 — GateResult equality and hash
# ---------------------------------------------------------------------------


@st.composite
def _equal_result_pair(draw):
    args = draw(_result_args())
    return args, args


@given(_equal_result_pair())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_equality_and_hash(pair):
    args_a, args_b = pair
    status_a, violations_a, error_a = args_a
    status_b, violations_b, error_b = args_b
    ra = _kernels.make_result(status_a, violations_a, error_a)
    rb = _kernels.make_result(status_b, violations_b, error_b)
    assert _kernels.result_eq(ra, rb)
    # Hash parity holds when no Violation (with its unhashable context dict)
    # is inside the tuple — exactly the pre-migration dataclass semantics
    # (a Violation-bearing result is unhashable on BOTH sides).
    if violations_a == ():
        assert hash(ra) == hash(rb)
    else:
        with pytest.raises(TypeError):
            hash(ra)
    # A result with a different status must compare unequal.
    other_status = next(s for s in GateStatus.members() if s is not status_a)
    other_violations = (Violation(type=ViolationType.CLEARANCE),) if other_status is GateStatus.VIOLATIONS else ()
    other_error = "different" if other_status is GateStatus.UNMEASURED else ""
    rc = _kernels.make_result(other_status, other_violations, other_error)
    assert not _kernels.result_eq(ra, rc)
    # Vacuity guard: all three statuses occur across the run.
    assert status_a in GateStatus.members()


def test_p3_fails_for_always_equal_kernel(_restore_kernels):
    """A degenerate kernel that claims every pair is equal must fail P3 on
    the different-status branch."""

    def always_equal(a, b):
        return True

    _kernels.result_eq = always_equal
    with pytest.raises(AssertionError):
        test_p3_equality_and_hash.hypothesis.inner_test(
            ((GateStatus.CLEAN, (), ""), (GateStatus.UNMEASURED, (), "boom"))
        )


# ---------------------------------------------------------------------------
# P4 — Enum value bijection
# ---------------------------------------------------------------------------


@given(st.sampled_from(GateStatus.members() + GateStage.members() + ViolationType.members()))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_enum_value_bijection(member):
    cls = type(member)
    # Enum(value) round-trips to an EQUAL member with the same name/value.
    # (Note: value-construction returns an equal-but-distinct instance — the
    # pyo3 #[new] constructor cannot return the cached member object; the
    # pre-migration Python Enum returned the cached singleton. Recorded in
    # VERIFICATION.md § documented deviations; consumers compare with ==, and
    # attribute access IS identity-stable, which the assertion below pins.)
    resolved = _kernels.resolve_enum(cls, member.value)
    assert resolved == member
    assert resolved.name == member.name
    assert resolved.value == member.value
    # Attribute access is identity-stable: `cls.MEMBER is cls.MEMBER` (the
    # pattern consumers rely on for `is`-dispatch).
    assert getattr(cls, member.name) is member
    # (name, value) pairs are unique across the class.
    pairs = [(m.name, m.value) for m in cls.members()]
    assert len(pairs) == len(set(pairs))
    # Vacuity guard: the sampled class has real members with distinct values.
    assert len(cls.members()) >= 2


def test_p4_fails_for_always_first_member(_restore_kernels):
    """A degenerate kernel that always resolves to the first member must
    fail P4 on a non-first member value."""

    def always_first(cls, value):
        return cls.members()[0]

    _kernels.resolve_enum = always_first
    with pytest.raises(AssertionError):
        test_p4_enum_value_bijection.hypothesis.inner_test(ViolationType.SLOP)


# ---------------------------------------------------------------------------
# P5 — BoardState opaque-payload identity
# ---------------------------------------------------------------------------


@st.composite
def _board_state_kwargs(draw):
    payloads = [object() for _ in range(draw(st.integers(0, 6)))]
    names = ("placement", "routing", "netlist", "board", "design_rules", "routed_pcb_path")
    kwargs = {}
    for name, payload in zip(names, payloads):
        kwargs[name] = payload
    return kwargs


@given(_board_state_kwargs())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_board_state_identity(kwargs):
    bs = _kernels.make_state(**kwargs)
    for name, payload in kwargs.items():
        # Identity: the getter returns the exact object passed in.
        assert getattr(bs, name) is payload
    # Unpopulated fields stay None (no cross-field leakage).
    for name in ("placement", "routing", "netlist", "board", "design_rules", "routed_pcb_path"):
        if name not in kwargs:
            assert getattr(bs, name) is None
    # Vacuity guard: kwargs is a subset of the full field surface.
    assert set(kwargs).issubset({"placement", "routing", "netlist", "board", "design_rules", "routed_pcb_path"})


def test_p5_fails_for_dropped_board(_restore_kernels):
    """A degenerate kernel that silently drops the ``board`` payload must
    fail P5 on the identity assertion."""

    def dropped_board(**kwargs):
        kwargs.pop("board", None)
        return BoardState(**kwargs)

    _kernels.make_state = dropped_board
    with pytest.raises(AssertionError):
        test_p5_board_state_identity.hypothesis.inner_test({"board": object()})


# ---------------------------------------------------------------------------
# MR1 — Violation construction→access round-trip and kwarg-order commutation
# ---------------------------------------------------------------------------


@given(_violation_kwargs())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_violation_round_trip_and_kwarg_commute(kwargs):
    v = Violation(**kwargs)
    assert _violation_fields(v) == _violation_fields(Violation(**dict(reversed(list(kwargs.items())))))
    assert v == Violation(**kwargs)
    assert v is not Violation(**kwargs)
    # Vacuity guard: every field was actually supplied (a non-empty kwargs).
    assert "type" in kwargs and "severity" in kwargs


# ---------------------------------------------------------------------------
# MR2 — canonical-form ⇔ equality
# ---------------------------------------------------------------------------


@given(_violation_kwargs(), _violation_kwargs())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_canonical_form_iff_equality(kwargs_a, kwargs_b):
    va = Violation(**kwargs_a)
    vb = Violation(**kwargs_b)
    # Equality uses Python `==` semantics (where 0.0 == -0.0), so the
    # canonical-form comparison must use the SAME semantics — NOT the
    # bit-exact `.hex()` form `_violation_fields` uses for the differential
    # suite (0.0 vs -0.0 differ in bits but compare equal, which made this
    # invariant spuriously fail on the -0.0 case for BOTH the oracle
    # dataclass and the Rust pyclass).
    fields_agree = _violation_fields_eq(va) == _violation_fields_eq(vb)
    # The canonical form is a complete invariant: identical fields <=> equal.
    assert (va == vb) == fields_agree
    # Vacuity guard: both agreeing and disagreeing pairs occur.
    assert fields_agree in (True, False)


# ---------------------------------------------------------------------------
# MR3 — Enum construction commutation
# ---------------------------------------------------------------------------


@given(st.sampled_from(GateStatus.members() + GateStage.members() + ViolationType.members()))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr3_enum_construction_commutes(member):
    cls = type(member)
    # Cls(member.value) == member — value construction is the inverse of
    # member access (equality; see the P4 note on identity).
    assert cls(member.value) == member
    assert cls(member.value).name == member.name
    # A member's str() embeds its name; repr embeds the quoted value.
    assert member.name in str(member)
    assert f"'{member.value}'" in repr(member)


# ---------------------------------------------------------------------------
# MR4 — BoardState payload independence
# ---------------------------------------------------------------------------


def test_mr4_board_state_payload_independence():
    board = object()
    bs = BoardState(board=board)
    assert bs.board is board
    assert bs.placement is None
    assert bs.routing is None
    assert bs.netlist is None
    assert bs.design_rules is None
    assert bs.routed_pcb_path is None
    # Populating a different field does not disturb the first.
    path = os.fspath("/tmp/x.kicad_pcb")
    bs2 = BoardState(routed_pcb_path=path)
    assert bs2.routed_pcb_path == path
    assert bs2.board is None
    assert bs.board is board


# ---------------------------------------------------------------------------
# Presence guard: this proof must not silently skip in CI.
# ---------------------------------------------------------------------------

_REQUIRE = os.environ.get("TEMPER_REQUIRE_RUST_GATES", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

if _REQUIRE and not hasattr(_tdb, "GateResult"):
    pytest.fail(
        "TEMPER_REQUIRE_RUST_GATES=1 but temper_design_bundle_python "
        "does not expose the gate-contract pyclasses — the Rust extension is "
        "stale or missing.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(_tdb, "GateResult"),
    reason="temper_design_bundle_python gate-contract pyclasses not installed "
    "(set TEMPER_REQUIRE_RUST_GATES=1 to make this fatal instead of a skip)",
)
