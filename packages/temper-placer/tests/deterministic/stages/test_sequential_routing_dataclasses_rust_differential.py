"""Differential test: DiffPairConfig dataclass, Rust pyclass vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The plain dataclass
``DiffPairConfig`` from ``deterministic/stages/sequential_routing_dataclasses.py``
moves to the ``temper-design-bundle`` crate; the Python module becomes a
delegation shim re-exporting the pyclass. The pre-migration implementation
is pinned VERBATIM as the oracle (``_sequential_routing_dataclasses_py_oracle.py``).

R1a: construction/field defaults/equality/repr parity with the type-carrying
``canon`` (int-vs-float and str typing preserved), plus CPython-repr parity
(py_float_str / py_str_repr rendering).
"""

from __future__ import annotations

import pytest

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._sequential_routing_dataclasses_py_oracle as _oracle
from tests.core._contract_canon import canon


def test_field_surface_matches_oracle():
    """The pyclass exposes the same five fields (repr/strs), typed identically."""
    a = _tdb.DiffPairConfig("USB_D+", "USB_D-")
    b = _oracle.DiffPairConfig("USB_D+", "USB_D-")
    assert canon(a) == canon(b)
    assert type(a.net_pos) is str and type(a.spacing_mm) is float


def test_defaults_match_oracle():
    """Construction defaults are identical (0.15 / 0.5 / 0.5)."""
    a = _tdb.DiffPairConfig("N+", "N-")
    b = _oracle.DiffPairConfig("N+", "N-")
    assert a.net_pos == b.net_pos
    assert a.net_neg == b.net_neg
    assert a.spacing_mm == b.spacing_mm
    assert a.coupling_tolerance_mm == b.coupling_tolerance_mm
    assert a.max_skew_mm == b.max_skew_mm
    assert isinstance(a.spacing_mm, float) and isinstance(a.coupling_tolerance_mm, float)


def test_positional_and_kwarg_construction():
    """Both positional and keyword construction resolve identically."""
    a_pos = _tdb.DiffPairConfig("P", "N", 0.3, 0.6, 0.7)
    b_pos = _oracle.DiffPairConfig("P", "N", 0.3, 0.6, 0.7)
    assert canon(a_pos) == canon(b_pos)

    a_kw = _tdb.DiffPairConfig(net_pos="P", net_neg="N", max_skew_mm=0.9)
    b_kw = _oracle.DiffPairConfig(net_pos="P", net_neg="N", max_skew_mm=0.9)
    assert canon(a_kw) == canon(b_kw)


def test_equality_matches_oracle():
    """All-five-field equality; differing floats make instances unequal."""
    a1 = _tdb.DiffPairConfig("P", "N")
    a2 = _tdb.DiffPairConfig("P", "N")
    assert a1 == a2
    assert a1 != _tdb.DiffPairConfig("P", "N", spacing_mm=0.2)
    b1 = _oracle.DiffPairConfig("P", "N")
    assert (a1 == a2) == (b1 == _oracle.DiffPairConfig("P", "N"))
    assert (a1 != _tdb.DiffPairConfig("P", "N", spacing_mm=0.2)) == (
        b1 != _oracle.DiffPairConfig("P", "N", spacing_mm=0.2)
    )


def test_repr_matches_oracle():
    """CPython-repr parity: single-quoted strs, float rendering, field order."""
    a = _tdb.DiffPairConfig("USB_D+", "USB_D-", 0.15, 0.5, 0.5)
    b = _oracle.DiffPairConfig("USB_D+", "USB_D-", 0.15, 0.5, 0.5)
    assert repr(a) == repr(b)
    # Explicit literal expectations so a drift on BOTH sides cannot hide.
    assert repr(a) == (
        "DiffPairConfig(net_pos='USB_D+', net_neg='USB_D-', spacing_mm=0.15, "
        "coupling_tolerance_mm=0.5, max_skew_mm=0.5)"
    )


def test_int_values_preserved_in_repr():
    """Dataclass field typing is uncoerced: int leaves stay int in repr."""
    a = _tdb.DiffPairConfig("P", "N", spacing_mm=1, coupling_tolerance_mm=2)
    b = _oracle.DiffPairConfig("P", "N", spacing_mm=1, coupling_tolerance_mm=2)
    assert type(a.spacing_mm) is int and type(b.spacing_mm) is int
    assert repr(a) == repr(b)


def test_missing_required_args_raise():
    """net_pos / net_neg are required; omitting them raises TypeError."""
    with pytest.raises(TypeError):
        _tdb.DiffPairConfig("P")
    with pytest.raises(TypeError):
        _tdb.DiffPairConfig()
