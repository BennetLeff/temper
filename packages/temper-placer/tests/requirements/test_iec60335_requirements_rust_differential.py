"""Differential test: the single-sourced ``requirement_matrix()`` Rust
table vs the pinned pre-port Python ``IEC60335_REQUIREMENTS`` oracle
(placer constraint/clearance Rust-port stage 1, 2026-08-17).

Before this port, the same 6-row matrix was hand-duplicated in two places
(the Python ``IEC60335_REQUIREMENTS`` dict and ``temper-drc-rs``'s
``MATRIX_ROWS`` const), nominally kept in sync by a
``test_requirement_matrix_values_pinned`` referenced in both files'
comments but that does not actually exist anywhere in the tree (confirmed
by grep at port time -- see the spike,
``docs/evidence/2026-08-17-placer-constraint-rust-port-spike.md``). Neither
side had an oracle matching the ``_*_py_oracle.py`` pinned-oracle naming
convention (``scripts/oracle_hashes.json`` had zero entries for this
matrix), so this is oracle CREATION per the migration pipeline's stage-3
TDD requirement (pin the pre-migration Python, then prove the Rust
replacement matches it), not a re-pin.

What is compared:
- ``packages/temper-design-bundle``'s ``requirement_matrix()`` (via the
  pyo3-exposed ``req_safe_01_requirement_matrix()`` in ``temper-drc-rs``,
  the actual pyo3 surface Python calls) against the pinned oracle's
  ``IEC60335_REQUIREMENTS``, row for row, value for value, in the same
  dict insertion order.
- The now-generated production ``IEC60335_REQUIREMENTS``
  (``temper_placer.requirements.validators.clearance``, built from the
  Rust accessor at import time) against the same oracle -- proving the
  single-sourcing wiring is live, not just that the Rust table itself is
  correct in isolation.

Every value must be bit-identical (``float.hex()`` comparison) -- this is a
safety matrix; any divergence here is exactly the kind of drift the
consolidation exists to make impossible.
"""

from __future__ import annotations

import temper_drc_rs as _rust

import tests.requirements.clearance_oracle._iec60335_requirements_py_oracle as _oracle
from temper_placer.requirements.validators.clearance import (
    IEC60335_REQUIREMENTS as PRODUCTION_REQUIREMENTS,
)

# Module-scope RED arm: the pyo3 accessor must exist.
assert hasattr(_rust, "req_safe_01_requirement_matrix")


def _f(value: float) -> str:
    """Bit-exact float key."""
    return float(value).hex()


def _oracle_rows_by_string_key() -> dict[tuple[str, str, str], dict[str, float]]:
    """The oracle's enum-tuple-keyed dict, re-keyed to (str, str, str) --
    the same shape both Rust accessors return -- in insertion order."""
    return {
        (domain_a.value, domain_b.value, insulation.value): dict(requirements)
        for (domain_a, domain_b, insulation), requirements in _oracle.IEC60335_REQUIREMENTS.items()
    }


class TestRequirementMatrixRustDifferential:
    def test_row_count_matches(self):
        oracle_rows = _oracle_rows_by_string_key()
        rust_rows = _rust.req_safe_01_requirement_matrix()
        assert len(rust_rows) == len(oracle_rows) == 6

    def test_rust_accessor_matches_oracle_row_for_row(self):
        oracle_rows = _oracle_rows_by_string_key()
        rust_rows = _rust.req_safe_01_requirement_matrix()

        assert set(rust_rows.keys()) == set(oracle_rows.keys())
        for key, oracle_req in oracle_rows.items():
            rust_req = rust_rows[key]
            for field in ("min_clearance_mm", "min_creepage_mm", "design_value_mm"):
                assert _f(rust_req[field]) == _f(oracle_req[field]), (
                    f"{key} {field}: rust={rust_req[field]!r} oracle={oracle_req[field]!r}"
                )

    def test_insertion_order_matches(self):
        """Dict insertion order is part of the pin -- both
        ``domain_clearance.py::_matrix_rows()`` and
        ``req_safe_01.rs``'s own matrix walk are order-sensitive (the
        dedup/canonicalization logic only, per that module's docstring —
        but a silent reorder is still worth catching early)."""
        oracle_keys = list(_oracle_rows_by_string_key().keys())
        rust_keys = list(_rust.req_safe_01_requirement_matrix().keys())
        assert rust_keys == oracle_keys

    def test_production_iec60335_requirements_matches_oracle(self):
        """The production dict (built from the Rust accessor at import
        time, replacing the pre-port hand-written literal) must still
        expose the identical enum-tuple-keyed shape every existing
        consumer relies on, with byte-identical values -- proving the
        single-sourcing wiring is live end to end, not just that the Rust
        table is correct in isolation."""
        assert set(PRODUCTION_REQUIREMENTS.keys()) == set(_oracle.IEC60335_REQUIREMENTS.keys())
        for key, oracle_req in _oracle.IEC60335_REQUIREMENTS.items():
            prod_req = PRODUCTION_REQUIREMENTS[key]
            for field in ("min_clearance_mm", "min_creepage_mm", "design_value_mm"):
                assert _f(prod_req[field]) == _f(oracle_req[field]), (
                    f"{key} {field}: production={prod_req[field]!r} oracle={oracle_req[field]!r}"
                )

    def test_production_keys_are_the_real_enum_types(self):
        """The production dict's keys must stay ``VoltageDomain``/
        ``InsulationType`` enum members (not raw strings) -- every existing
        consumer (``domain_clearance.py``, ``real_board.py``,
        ``drc_result.py``) indexes by enum tuple."""
        from temper_placer.requirements.validators.clearance import (
            InsulationType,
            VoltageDomain,
        )

        for domain_a, domain_b, insulation in PRODUCTION_REQUIREMENTS:
            assert isinstance(domain_a, VoltageDomain)
            assert isinstance(domain_b, VoltageDomain)
            assert isinstance(insulation, InsulationType)
