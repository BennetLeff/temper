"""Differential oracle tests: BusCohortConstraint.

This test pins the pre-migration Python dataclass implementation VERBATIM
as an inline oracle block (`_OracleBusCohortConstraint`) and compares the
Rust pyclass (imported via the delegation shim) against it bit-identically.

G1 (TDD): This file is committed BEFORE any Rust pyclass code. Git history
must show the test predating the pyclass implementation. In identity mode
(before Rust), the shim import IS the Python dataclass and the test compares
it against the oracle — the test is trivially green when the implementation
still lives in Python.

After the migration, the shim import is the Rust pyclass and the test compares
Rust vs Python oracle. The same assertions (canonicalized through
field-tupling and repr-name normalization) must stay green.

Migration plan: docs/plans/2026-08-08-002-feat-buscohort-pyclass-migration-plan.md
(U1). Precedent: test_net_graph_and_diff_pair_rust_differential.py (Wave C).

Module-to-property map (cross-referenced with test_bus_cohort_pbt.py):
  BusCohortConstraint: P1 (signal_count == len(nets)), P2 (repr round-trip),
                       P3 (empty-nets error first), P4 (pitch-before-skew
                       order), P5 (nets identity), MR1 (net-list permutation),
                       MR2 (default preservation), MR3 (construction order).
"""

from dataclasses import dataclass

import pytest

# Production class — after migration this is the Rust pyclass via the
# delegation shim. Before the migration, it IS the Python dataclass (identity
# mode).
from temper_placer.core.bus_cohort import BusCohortConstraint

# ---------------------------------------------------------------------------
# Oracle block — verbatim copy of `temper_placer/core/bus_cohort.py`'s
# `BusCohortConstraint` (origin/main, pre-migration).
# DO NOT EDIT — these are the reference implementations, name-suffixed _Oracle
# to avoid clashing with the shim imports.
# ---------------------------------------------------------------------------


@dataclass
class _OracleBusCohortConstraint:
    """Constraint for routing a bus cohort.

    Defines requirements for routing a group of nets in parallel with
    consistent spacing.

    Attributes:
        name: Name of the bus (e.g., 'SPI_BUS')
        nets: List of net names in the cohort (ordered).
        pitch_mm: Center-to-center spacing between traces in mm.
        max_skew_mm: Maximum length mismatch within the cohort in mm.
        allow_swapping: Whether signal order can be swapped to optimize routing.
    """

    name: str
    nets: list[str]
    pitch_mm: float = 0.5
    max_skew_mm: float = 2.0
    allow_swapping: bool = False

    def __post_init__(self):
        """Validate bus cohort parameters."""
        if not self.nets:
            raise ValueError("Bus cohort must contain at least one net.")
        if self.pitch_mm <= 0:
            raise ValueError(f"pitch_mm must be positive, got {self.pitch_mm}")
        if self.max_skew_mm < 0:
            raise ValueError(f"max_skew_mm must be non-negative, got {self.max_skew_mm}")

    @property
    def signal_count(self) -> int:
        """Total number of signals in the bus."""
        return len(self.nets)


# ---------------------------------------------------------------------------
# Canonicalization helpers — extract fields from both sides into comparable
# forms. This way the oracle class name doesn't need to match the pyclass name.
# ---------------------------------------------------------------------------


def _bus_fields(bus) -> tuple:
    """Extract canonical fields from a BusCohortConstraint (either oracle or pyclass)."""
    return (
        bus.name,
        tuple(bus.nets),
        bus.pitch_mm,
        bus.max_skew_mm,
        bus.allow_swapping,
    )


def _repr_normalized(obj, cls_name):
    """Return repr(obj) with the class name replaced by `cls_name`."""
    r = repr(obj)
    idx = r.index("(")
    return cls_name + r[idx:]


def _oracle_repr(oracle) -> str:
    """repr(oracle) with the oracle class-name prefix replaced by the pyclass name."""
    return repr(oracle).replace("_OracleBusCohortConstraint", "BusCohortConstraint")


def _value_error_text(fn) -> str:
    """Run `fn`, return the exact ValueError message it raises (else fail)."""
    with pytest.raises(ValueError) as excinfo:
        fn()
    return str(excinfo.value)


def _make(name="SPI_BUS", nets=None, **kwargs):
    """Build both the production BusCohortConstraint and its oracle twin."""
    nets = ["sclk", "sdi", "sdo"] if nets is None else nets
    prod = BusCohortConstraint(name=name, nets=nets, **kwargs)
    oracle = _OracleBusCohortConstraint(name=name, nets=nets, **kwargs)
    return prod, oracle


# ============================================================================
# Construction
# ============================================================================


class TestBusCohortConstruction:
    def test_construction_required_only(self):
        prod, oracle = _make()
        assert _repr_normalized(prod, "BusCohortConstraint") == _oracle_repr(oracle)
        assert _bus_fields(prod) == _bus_fields(oracle)

    def test_construction_all_defaults(self):
        prod, oracle = _make(name="TEST_BUS", nets=["NET_A", "NET_B"])
        assert prod.pitch_mm == 0.5
        assert prod.max_skew_mm == 2.0
        assert prod.allow_swapping is False
        assert _repr_normalized(prod, "BusCohortConstraint") == _oracle_repr(oracle)
        assert _bus_fields(prod) == _bus_fields(oracle)

    def test_construction_keyword_all_fields(self):
        kwargs = {
            "name": "SPI_BUS",
            "nets": ["SPI_CLK", "SPI_MOSI"],
            "pitch_mm": 0.4,
            "max_skew_mm": 1.5,
            "allow_swapping": True,
        }
        prod, oracle = _make(**kwargs)
        assert _repr_normalized(prod, "BusCohortConstraint") == _oracle_repr(oracle)
        assert _bus_fields(prod) == _bus_fields(oracle)
        assert prod.allow_swapping is True

    def test_construction_positional_all_fields(self):
        prod = BusCohortConstraint("PWM_BUS", ["PWM_H", "PWM_L"], 0.6, 3.0, True)
        oracle = _OracleBusCohortConstraint("PWM_BUS", ["PWM_H", "PWM_L"], 0.6, 3.0, True)
        assert _repr_normalized(prod, "BusCohortConstraint") == _oracle_repr(oracle)
        assert _bus_fields(prod) == _bus_fields(oracle)

    def test_field_type_identity_int_stays_int(self):
        """pitch_mm=1 stays an int (no float widening) — D1 opaque storage."""
        prod = BusCohortConstraint("X", ["a"], pitch_mm=1)
        oracle = _OracleBusCohortConstraint("X", ["a"], pitch_mm=1)
        assert isinstance(prod.pitch_mm, int)
        assert not isinstance(prod.pitch_mm, float)
        assert _repr_normalized(prod, "BusCohortConstraint") == _oracle_repr(oracle)
        assert _bus_fields(prod) == _bus_fields(oracle)

    def test_field_type_identity_bool_stays_bool(self):
        prod = BusCohortConstraint("X", ["a"], allow_swapping=True)
        assert prod.allow_swapping is True

    def test_nets_list_identity_preserved(self):
        """The passed list is stored by reference (dataclass semantics)."""
        orig = ["a", "b", "c"]
        prod = BusCohortConstraint("X", nets=orig)
        oracle = _OracleBusCohortConstraint("X", nets=orig)
        assert prod.nets is orig
        assert oracle.nets is orig


# ============================================================================
# repr / == / != / hash
# ============================================================================


class TestBusCohortReprEqHash:
    def test_repr_roundtrip_field_order(self):
        prod, oracle = _make()
        r = _repr_normalized(prod, "BusCohortConstraint")
        assert _oracle_repr(oracle) == r
        # dataclass field order
        assert r.index("name=") < r.index("nets=") < r.index("pitch_mm=")
        assert r.index("pitch_mm=") < r.index("max_skew_mm=") < r.index("allow_swapping=")

    def test_repr_strings_use_single_quotes(self):
        prod, _ = _make()
        r = repr(prod)
        assert "'SPI_BUS'" in r and "'sclk'" in r

    def test_repr_renders_list_and_bool(self):
        prod, _ = _make(allow_swapping=False)
        r = repr(prod)
        assert "nets=['sclk', 'sdi', 'sdo']" in r
        assert "allow_swapping=False" in r

    def test_repr_float_rendering(self):
        prod, oracle = _make(pitch_mm=0.5, max_skew_mm=2.0)
        assert _oracle_repr(oracle) == _repr_normalized(prod, "BusCohortConstraint")
        assert "pitch_mm=0.5" in repr(prod)
        assert "max_skew_mm=2.0" in repr(prod)

    def test_equality_identical_fields(self):
        a = BusCohortConstraint("X", ["a", "b"])
        b = BusCohortConstraint("X", ["a", "b"])
        assert a == b
        assert (a == b) == (_OracleBusCohortConstraint("X", ["a", "b"]) == _OracleBusCohortConstraint("X", ["a", "b"]))

    def test_equality_different_pitch(self):
        a = BusCohortConstraint("X", ["a"], pitch_mm=0.5)
        b = BusCohortConstraint("X", ["a"], pitch_mm=0.6)
        assert a != b

    def test_equality_different_nets(self):
        a = BusCohortConstraint("X", ["a", "b"])
        b = BusCohortConstraint("X", ["a"])
        assert a != b

    def test_equality_different_swapping(self):
        a = BusCohortConstraint("X", ["a"], allow_swapping=False)
        b = BusCohortConstraint("X", ["a"], allow_swapping=True)
        assert a != b

    def test_equality_cross_impl(self):
        """Production pyclass == oracle dataclass with identical fields -> equal."""
        prod = BusCohortConstraint("X", ["a"], pitch_mm=1)
        oracle = _OracleBusCohortConstraint("X", ["a"], pitch_mm=1)
        assert _bus_fields(prod) == _bus_fields(oracle)

    def test_hash_unhashable(self):
        prod = BusCohortConstraint("X", ["a"])
        with pytest.raises(TypeError, match="unhashable type: 'BusCohortConstraint'"):
            hash(prod)


# ============================================================================
# nets identity / mutation / signal_count
# ============================================================================


class TestBusCohortNetsAndSignalCount:
    def test_nets_getter_identity(self):
        """The `nets` getter returns the SAME list object on every read.

        Two separate attribute reads = two separate pyo3 getter calls; a
        getter that rebuilt the list would hand back distinct objects and
        in-place `.append()` would silently not persist. Asserted through
        two named reads (not `prod.nets is prod.nets`, which is the
        always-true `X is X` shape a reader cannot distinguish from a real
        check -- check_vacuous_gates.py #3), plus the observable
        consequence: a mutation through the first handle is visible on a
        third, fresh read.
        """
        prod = BusCohortConstraint("X", ["a", "b"])
        first_read = prod.nets
        second_read = prod.nets
        assert first_read is second_read
        first_read.append("c")
        assert prod.nets == ["a", "b", "c"]
        assert prod.signal_count == 3

    def test_nets_append_persists(self):
        prod = BusCohortConstraint("SPI_BUS", ["a"])
        oracle = _OracleBusCohortConstraint("SPI_BUS", ["a"])
        prod.nets.append("b")
        oracle.nets.append("b")
        assert _bus_fields(prod) == _bus_fields(oracle)
        assert prod.signal_count == 2

    def test_nets_assignment_replaces(self):
        """Dataclass-field assignment `bus.nets = [...]` replaces the list."""
        prod = BusCohortConstraint("X", ["a"])
        oracle = _OracleBusCohortConstraint("X", ["a"])
        prod.nets = ["a", "b", "c"]
        oracle.nets = ["a", "b", "c"]
        assert len(prod.nets) == 3
        assert _bus_fields(prod) == _bus_fields(oracle)

    def test_signal_count_equals_len(self):
        for size in (1, 3, 7):
            nets = [f"N{i}" for i in range(size)]
            prod = BusCohortConstraint("X", nets)
            oracle = _OracleBusCohortConstraint("X", nets)
            assert prod.signal_count == oracle.signal_count == size

    def test_signal_count_reflects_in_place_mutation(self):
        """signal_count reads the stored list length live (D4)."""
        prod = BusCohortConstraint("X", ["a"])
        assert prod.signal_count == 1
        prod.nets.append("b")
        assert prod.signal_count == 2
        oracle = _OracleBusCohortConstraint("X", ["a"])
        oracle.nets.append("b")
        assert oracle.signal_count == 2

    def test_nets_assignment_rejects_non_list(self):
        """Assignment of a non-list raises TypeError (pyclass strictness).

        The pre-migration dataclass accepted any assignable object; the pyclass
        requires a list. This is a documented, deliberate deviation (a
        non-list assignment was never reachable in production) — the pyclass
        fails loudly instead of silently storing a foreign object. Same
        rationale as NetGraph.edges' typed setter.
        """
        prod = BusCohortConstraint("X", ["a"])
        with pytest.raises(TypeError):
            prod.nets = "not-a-list"


# ============================================================================
# Validation (__post_init__) — exact message text AND order
# ============================================================================


class TestBusCohortValidation:
    def test_validation_empty_nets(self):
        prod_msg = _value_error_text(lambda: BusCohortConstraint("X", nets=[]))
        oracle_msg = _value_error_text(lambda: _OracleBusCohortConstraint("X", nets=[]))
        assert prod_msg == oracle_msg == "Bus cohort must contain at least one net."

    def test_validation_no_net_arg_raises_typeerror(self):
        """`nets` is a REQUIRED field in the source (`nets: list[str]`, no
        default factory) — omitting it raises TypeError, exactly like the
        oracle dataclass. (This supersedes plan R-A's `default_factory=list`
        premise, which the verbatim source does not have.)"""
        with pytest.raises(TypeError):
            BusCohortConstraint(name="X")
        with pytest.raises(TypeError):
            _OracleBusCohortConstraint(name="X")

    def test_validation_pitch_zero(self):
        prod_msg = _value_error_text(lambda: BusCohortConstraint("X", ["a"], pitch_mm=0))
        oracle_msg = _value_error_text(lambda: _OracleBusCohortConstraint("X", ["a"], pitch_mm=0))
        assert prod_msg == oracle_msg == "pitch_mm must be positive, got 0"

    def test_validation_pitch_negative_float(self):
        prod_msg = _value_error_text(
            lambda: BusCohortConstraint("X", ["a"], pitch_mm=-0.5)
        )
        oracle_msg = _value_error_text(
            lambda: _OracleBusCohortConstraint("X", ["a"], pitch_mm=-0.5)
        )
        assert prod_msg == oracle_msg == "pitch_mm must be positive, got -0.5"

    def test_validation_pitch_int_rendering(self):
        """pitch_mm=-1 (int) renders as 'got -1' on both sides."""
        prod_msg = _value_error_text(lambda: BusCohortConstraint("X", ["a"], pitch_mm=-1))
        oracle_msg = _value_error_text(lambda: _OracleBusCohortConstraint("X", ["a"], pitch_mm=-1))
        assert prod_msg == oracle_msg == "pitch_mm must be positive, got -1"

    def test_validation_max_skew_negative(self):
        prod_msg = _value_error_text(
            lambda: BusCohortConstraint("X", ["a"], max_skew_mm=-0.5)
        )
        oracle_msg = _value_error_text(
            lambda: _OracleBusCohortConstraint("X", ["a"], max_skew_mm=-0.5)
        )
        assert prod_msg == oracle_msg == "max_skew_mm must be non-negative, got -0.5"

    def test_validation_max_skew_zero_ok(self):
        prod = BusCohortConstraint("X", ["a"], max_skew_mm=0)
        oracle = _OracleBusCohortConstraint("X", ["a"], max_skew_mm=0)
        assert _bus_fields(prod) == _bus_fields(oracle)

    def test_validation_order_empty_nets_first(self):
        """nets=[] raises the empty-nets error, not the pitch error (D3)."""
        prod_msg = _value_error_text(
            lambda: BusCohortConstraint("X", nets=[], pitch_mm=-1.0, max_skew_mm=-1.0)
        )
        oracle_msg = _value_error_text(
            lambda: _OracleBusCohortConstraint("X", nets=[], pitch_mm=-1.0, max_skew_mm=-1.0)
        )
        assert prod_msg == oracle_msg == "Bus cohort must contain at least one net."

    def test_validation_order_pitch_before_skew(self):
        """pitch <= 0 raises before max_skew < 0 (declaration order)."""
        prod_msg = _value_error_text(
            lambda: BusCohortConstraint("X", ["a"], pitch_mm=0.0, max_skew_mm=-1.0)
        )
        oracle_msg = _value_error_text(
            lambda: _OracleBusCohortConstraint("X", ["a"], pitch_mm=0.0, max_skew_mm=-1.0)
        )
        assert prod_msg == oracle_msg == "pitch_mm must be positive, got 0.0"
