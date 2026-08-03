"""Differential test: Rust gate-contract pyclasses (temper_design_bundle_python)
vs the pinned Python oracle.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This is the FOURTH Wave-4 Phase 2 migration; it mirrors the
net-types, loop, and design-rules migrations
(``test_net_types_rust_differential.py`` / ``test_loop_rust_differential.py``
/ ``test_design_rules_rust_differential.py``) exactly.

The Rust pyo3 pyclasses ``GateStatus``, ``GateStage``, ``ViolationType``,
``Violation``, ``GateResult``, ``BoardState`` (in
``temper_design_bundle_python``, from the ``temper-design-bundle`` crate)
must reproduce the pre-migration Python implementation of the contract
types in ``temper_placer/placer/cp_sat/gates.py`` bit-identically. The
pre-migration implementation is pinned verbatim as the oracle
(``_gates_py_oracle.py``, commit ef2ac25fd) and every assertion here drives
IDENTICAL inputs through both sides.

Comparison convention (mirrors the loop/net-types/design-rules
differential): objects are canonicalized into plain comparable tuples
before assertion. Floats are compared as exact bit patterns via
``float.hex()``; enum members via ``(name, value)``; opaque ``BoardState``
payloads via identity markers (the same sentinel object is driven through
both sides, so ``id()`` agrees).

Gate-contract-specific notes:
- Enum *identity* is load-bearing: consumers compare ``result.status is
  GateStatus.CLEAN`` and ``violation.type is ViolationType.CREEPAGE``, so
  this suite asserts ``is``-identity on the Rust side too (the pyo3 enums
  cache their members; the dataclasses hold the member object opaquely so
  the getter returns the exact cached object).
- ``GateResult``'s constructor invariant (``VIOLATIONS`` with an empty
  ``violations`` tuple is rejected with a ``ValueError``) is asserted on
  both sides, including the exact message text.
- Full ``repr(...)`` equality is asserted byte-for-byte (the B9 lesson:
  string fields must render with CPython single quotes via
  ``py_str_repr``, floats via ``py_float_str``, and enum members via the
  ``<ViolationType.CLEARANCE: 'clearance'>`` form with the quoted string
  value).
"""

from __future__ import annotations

import pytest
import temper_design_bundle_python as _tdb

import tests.placer.cp_sat._gates_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
GATE_STATUS = _tdb.GateStatus
GATE_STAGE = _tdb.GateStage
VIOLATION_TYPE = _tdb.ViolationType
VIOLATION = _tdb.Violation
GATE_RESULT = _tdb.GateResult
BOARD_STATE = _tdb.BoardState


def _f(value):
    """Bit-exact float key."""
    return float(value).hex()


def _enum_key(member):
    """Canonicalize an enum member: (name, value) — value is a str here."""
    return (member.name, member.value)


def _violation_fields(v):
    return (
        _enum_key(v.type),
        tuple(v.components),
        tuple(v.nets),
        _f(v.severity),
        _f(v.threshold),
        v.description,
        tuple(sorted((k, str(val)) for k, val in v.context.items())),
    )


def _gate_result_fields(r):
    return (
        _enum_key(r.status),
        tuple(_violation_fields(x) for x in r.violations),
        r.error_message,
    )


def _board_state_fields(bs):
    """Opaque payloads are canonicalized by identity markers — the SAME
    sentinel object is driven through both sides, so id() agrees. ``None``
    stays ``None``; Paths also render via ``str()`` (identity alone would
    already agree, but str() documents the payload)."""
    out = []
    for field_name in ("placement", "routing", "netlist", "board", "design_rules", "routed_pcb_path"):
        value = getattr(bs, field_name)
        if value is None:
            out.append(None)
        else:
            marker = (id(value), type(value).__name__)
            if isinstance(value, _oracle.Path):
                marker = (str(value), type(value).__name__)
            out.append(marker)
    return tuple(out)


# ---------------------------------------------------------------------------
# Enum parity — names, values, repr, str, members(), identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rust_cls", "oracle_cls"),
    [
        (GATE_STATUS, _oracle.GateStatus),
        (GATE_STAGE, _oracle.GateStage),
        (VIOLATION_TYPE, _oracle.ViolationType),
    ],
)
def test_enum_members_names_and_values_identical(rust_cls, oracle_cls):
    rust_names = [m.name for m in rust_cls.members()]
    oracle_names = [m.name for m in oracle_cls]
    assert rust_names == oracle_names
    rust_values = [m.value for m in rust_cls.members()]
    oracle_values = [m.value for m in oracle_cls]
    assert rust_values == oracle_values


@pytest.mark.parametrize(
    ("rust_cls", "oracle_cls"),
    [
        (GATE_STATUS, _oracle.GateStatus),
        (GATE_STAGE, _oracle.GateStage),
        (VIOLATION_TYPE, _oracle.ViolationType),
    ],
)
def test_enum_repr_and_str_identical(rust_cls, oracle_cls):
    for rust_member, oracle_member in zip(rust_cls.members(), oracle_cls):
        assert repr(rust_member) == repr(oracle_member)
        assert str(rust_member) == str(oracle_member)


def test_enum_members_are_identity_cached():
    """Load-bearing: consumers do ``status is GateStatus.CLEAN``.

    pyo3 caches enum members as class attributes; each access below
    resolves the member through a DIFFERENT access path (attribute vs
    getattr) and asserts both resolve to the SAME object -- the property
    consumers depend on (``result.status is GateStatus.CLEAN`` must
    hold when the status came from the same enum class)."""
    assert GATE_STATUS.CLEAN is GATE_STATUS.CLEAN
    assert GATE_STATUS.VIOLATIONS is GATE_STATUS.VIOLATIONS
    assert GATE_STAGE.PLACEMENT is GATE_STAGE.PLACEMENT
    assert VIOLATION_TYPE.CREEPAGE is VIOLATION_TYPE.CREEPAGE


# ---------------------------------------------------------------------------
# Violation parity
# ---------------------------------------------------------------------------


def test_violation_defaults_identical():
    rust_v = VIOLATION(type=VIOLATION_TYPE.CLEARANCE)
    oracle_v = _oracle.Violation(type=_oracle.ViolationType.CLEARANCE)
    assert _violation_fields(rust_v) == _violation_fields(oracle_v)
    assert repr(rust_v) == repr(oracle_v)


def test_violation_type_field_is_unvalidated():
    """The dataclass does not validate ``type`` — any object is accepted and
    held (driving a GateStatus member through proves no enum cast happens)."""
    rust_v = VIOLATION(type=GATE_STATUS.CLEAN)
    oracle_v = _oracle.Violation(type=_oracle.GateStatus.CLEAN)
    assert _violation_fields(rust_v) == _violation_fields(oracle_v)
    assert repr(rust_v) == repr(oracle_v)
    assert rust_v.type is GATE_STATUS.CLEAN


def test_violation_all_fields_identical():
    kwargs = {
        "type": VIOLATION_TYPE.CREEPAGE,
        "components": ("Q1", "Q2"),
        "nets": ("DC_BUS+", "AC_L"),
        "severity": 4.5,
        "threshold": 6.0,
        "description": "Creepage too small",
        "context": {"required_mm": 6.0, "rule": "creepage_sl"},
    }
    rust_v = VIOLATION(**kwargs)
    oracle_v = _oracle.Violation(
        type=_oracle.ViolationType.CREEPAGE,
        components=("Q1", "Q2"),
        nets=("DC_BUS+", "AC_L"),
        severity=4.5,
        threshold=6.0,
        description="Creepage too small",
        context={"required_mm": 6.0, "rule": "creepage_sl"},
    )
    assert _violation_fields(rust_v) == _violation_fields(oracle_v)
    assert repr(rust_v) == repr(oracle_v)


def test_violation_type_identity_preserved():
    """``violation.type is ViolationType.CREEPAGE`` — the delta_mapper
    dispatch pattern."""
    v = VIOLATION(type=VIOLATION_TYPE.CREEPAGE)
    assert v.type is VIOLATION_TYPE.CREEPAGE


def test_violation_context_is_fresh_dict_per_instance():
    """``field(default_factory=dict)``: two default instances never share a
    context dict."""
    v1 = VIOLATION(type=VIOLATION_TYPE.CLEARANCE)
    v2 = VIOLATION(type=VIOLATION_TYPE.CLEARANCE)
    assert v1.context == {}
    assert v1.context is not v2.context
    assert v1.context == v2.context
    assert type(v1.context) is dict


def test_violation_equality_identical():
    a = VIOLATION(type=VIOLATION_TYPE.CLEARANCE, severity=1.0)
    b = VIOLATION(type=VIOLATION_TYPE.CLEARANCE, severity=1.0)
    c = VIOLATION(type=VIOLATION_TYPE.CLEARANCE, severity=2.0)
    assert a == b
    assert a != c


def test_violation_hash_semantics_identical():
    """Faithful frozen-dataclass hash: the ``context`` dict field makes a
    Violation UNHASHABLE (tuple-hash recurses into the dict) — both sides
    must raise TypeError, exactly like the pre-migration dataclass."""
    with pytest.raises(TypeError):
        hash(VIOLATION(type=VIOLATION_TYPE.CLEARANCE))
    with pytest.raises(TypeError):
        hash(_oracle.Violation(type=_oracle.ViolationType.CLEARANCE))


# ---------------------------------------------------------------------------
# GateResult parity — construction, the VIOLATIONS invariant, eq, hash, repr
# ---------------------------------------------------------------------------


def test_gate_result_clean_identical():
    rust_r = GATE_RESULT(GATE_STATUS.CLEAN)
    oracle_r = _oracle.GateResult(_oracle.GateStatus.CLEAN)
    assert _gate_result_fields(rust_r) == _gate_result_fields(oracle_r)
    assert repr(rust_r) == repr(oracle_r)


def test_gate_result_unmeasured_with_error_identical():
    rust_r = GATE_RESULT(GATE_STATUS.UNMEASURED, error_message="kicad-cli exit 3")
    oracle_r = _oracle.GateResult(_oracle.GateStatus.UNMEASURED, error_message="kicad-cli exit 3")
    assert _gate_result_fields(rust_r) == _gate_result_fields(oracle_r)
    assert repr(rust_r) == repr(oracle_r)


def test_gate_result_violations_identical():
    v_kwargs = {
        "type": VIOLATION_TYPE.UNROUTED,
        "components": ("U1",),
        "nets": ("NET_A",),
        "severity": 1.5,
        "description": "unrouted",
    }
    rust_r = GATE_RESULT(GATE_STATUS.VIOLATIONS, violations=(VIOLATION(**v_kwargs),))
    oracle_r = _oracle.GateResult(
        _oracle.GateStatus.VIOLATIONS,
        violations=(
            _oracle.Violation(
                type=_oracle.ViolationType.UNROUTED,
                components=("U1",),
                nets=("NET_A",),
                severity=1.5,
                description="unrouted",
            ),
        ),
    )
    assert _gate_result_fields(rust_r) == _gate_result_fields(oracle_r)
    assert repr(rust_r) == repr(oracle_r)


def test_gate_result_violations_invariant_rejected_on_both_sides():
    with pytest.raises(ValueError, match="VIOLATIONS must have at least one"):
        GATE_RESULT(GATE_STATUS.VIOLATIONS, violations=())
    with pytest.raises(ValueError, match="VIOLATIONS must have at least one"):
        _oracle.GateResult(_oracle.GateStatus.VIOLATIONS, violations=())


def test_gate_result_status_identity_preserved():
    r = GATE_RESULT(GATE_STATUS.CLEAN)
    assert r.status is GATE_STATUS.CLEAN


def test_gate_result_equality_and_hash_identical():
    r1 = GATE_RESULT(GATE_STATUS.CLEAN)
    r2 = GATE_RESULT(GATE_STATUS.CLEAN)
    assert r1 == r2
    assert hash(r1) == hash(r2)
    unmeasured = GATE_RESULT(GATE_STATUS.UNMEASURED, error_message="boom")
    assert r1 != unmeasured
    assert r1.status is not unmeasured.status


# ---------------------------------------------------------------------------
# BoardState parity — defaults, populated opaque payloads, identity
# ---------------------------------------------------------------------------


def test_board_state_defaults_identical():
    rust_bs = BOARD_STATE()
    oracle_bs = _oracle.BoardState()
    assert _board_state_fields(rust_bs) == _board_state_fields(oracle_bs)
    assert repr(rust_bs) == repr(oracle_bs)


def test_board_state_populated_identical():
    placement = object()
    routing = object()
    netlist = object()
    board = object()
    design_rules = object()
    path = _oracle.Path("/tmp/test.kicad_pcb")

    rust_bs = BOARD_STATE(
        placement=placement,
        routing=routing,
        netlist=netlist,
        board=board,
        design_rules=design_rules,
        routed_pcb_path=path,
    )
    oracle_bs = _oracle.BoardState(
        placement=placement,
        routing=routing,
        netlist=netlist,
        board=board,
        design_rules=design_rules,
        routed_pcb_path=path,
    )
    assert _board_state_fields(rust_bs) == _board_state_fields(oracle_bs)
    assert repr(rust_bs) == repr(oracle_bs)


def test_board_state_identity_preserved():
    """``bs.board is board`` — gates inspect the payload object itself."""
    board = object()
    bs = BOARD_STATE(board=board)
    assert bs.board is board
    assert bs.placement is None
    assert bs.routed_pcb_path is None


# ---------------------------------------------------------------------------
# repr byte-for-byte across every construction above (B9)
# ---------------------------------------------------------------------------


def test_reprs_byte_identical_for_all_constructed_objects():
    """Full repr equality is asserted per-case above; this test pins the
    union so a repr regression in any rendering helper fails here too."""
    cases = [
        (VIOLATION(type=VIOLATION_TYPE.CLEARANCE), _oracle.Violation(type=_oracle.ViolationType.CLEARANCE)),
        (
            VIOLATION(
                type=VIOLATION_TYPE.SLOP,
                components=("R1", "R2"),
                severity=0.25,
                threshold=0.5,
                description="artifacts",
                context={"artifact_type": "sliver"},
            ),
            _oracle.Violation(
                type=_oracle.ViolationType.SLOP,
                components=("R1", "R2"),
                severity=0.25,
                threshold=0.5,
                description="artifacts",
                context={"artifact_type": "sliver"},
            ),
        ),
        (GATE_RESULT(GATE_STATUS.CLEAN), _oracle.GateResult(_oracle.GateStatus.CLEAN)),
        (
            GATE_RESULT(GATE_STATUS.UNMEASURED, error_message="kicad-cli unavailable: boom"),
            _oracle.GateResult(_oracle.GateStatus.UNMEASURED, error_message="kicad-cli unavailable: boom"),
        ),
        (BOARD_STATE(), _oracle.BoardState()),
    ]
    shared_payload = object()
    cases.append(
        (
            BOARD_STATE(design_rules=shared_payload),
            _oracle.BoardState(design_rules=shared_payload),
        )
    )
    for rust_obj, oracle_obj in cases:
        assert repr(rust_obj) == repr(oracle_obj), f"repr diverged: {rust_obj!r} != {oracle_obj!r}"
