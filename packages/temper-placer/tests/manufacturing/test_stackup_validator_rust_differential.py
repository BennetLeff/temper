"""Differential test: Rust stackup validator (``temper_io_types``) vs the
pinned Python oracle.

Wave 4, Phase 4 leftovers slice — the manufacturing/stackup_validator.py
migration. The Rust pyo3 pyclasses ``StackupValidationResult``,
``StackupValidationReport`` and the ``validate_stackup`` pyfunction (in
``temper_io_types``, from the ``temper-io-types`` crate) must reproduce the
pre-migration Python implementation of
``temper_placer/manufacturing/stackup_validator.py`` bit-identically. The
pre-migration implementation is pinned verbatim as the oracle
(``_stackup_validator_py_oracle.py``, commit 6290942be) and every assertion
here drives IDENTICAL inputs through both sides.

Comparison convention: the report's per-check results are canonicalized
into (check_name, passed, message, layer, details-hex) tuples — floats in
the details dicts are compared bit-exactly via ``float.hex()`` and the
message strings byte-for-byte. Both arms receive the SAME ``LayerStackup``
pyclass instance (``temper_placer.core.board.LayerStackup``), so the
layer-attribute boundary is identical on both sides.

Boundary notes:
- ``validate_stackup``'s ``routing_results`` arm calls back into
  ``temper_placer.router_v6.copper_balance.analyze_copper_balance`` on BOTH
  sides (the oracle imports it; the Rust pyfunction calls it back across
  the boundary) — this differential covers that arm via a stub routing
  result object so the call-back path is exercised without depending on the
  router.
"""

from __future__ import annotations

import pytest
import temper_io_types as _io

import tests.manufacturing._stackup_validator_py_oracle as _oracle
from temper_placer.core.board import LayerStackup

# Rust symbols under test — must exist or this file fails to collect (RED).
STACKUP_VALIDATION_RESULT = _io.StackupValidationResult
STACKUP_VALIDATION_REPORT = _io.StackupValidationReport
VALIDATE_STACKUP = _io.validate_stackup


# ---------------------------------------------------------------------------
# Fixtures / canonicalization.
# ---------------------------------------------------------------------------


def _details_key(details):
    if details is None:
        return None
    return tuple(sorted((k, float(v).hex()) for k, v in details.items()))


def _result_key(r):
    return (
        r.check_name,
        r.passed,
        r.message,
        r.layer,
        _details_key(r.details),
    )


def _report_keys(report):
    return tuple(_result_key(r) for r in report.results)


@pytest.fixture
def canonical_stackup() -> LayerStackup:
    return LayerStackup.default_4layer()


@pytest.fixture
def balanced_fill() -> dict[str, float]:
    return {"F.Cu": 35.0, "In1.Cu": 65.0, "In2.Cu": 65.0, "B.Cu": 30.0}


@pytest.fixture
def unbalanced_fill() -> dict[str, float]:
    return {"F.Cu": 95.0, "In1.Cu": 10.0, "In2.Cu": 90.0, "B.Cu": 3.0}


@pytest.fixture
def usb_differential_nets() -> frozenset[str]:
    return frozenset({"USB_D+", "USB_D-"})


def _both(stackup, **kw):
    py_report = _oracle.validate_stackup(stackup, **kw)
    rust_report = VALIDATE_STACKUP(stackup, **kw)
    return py_report, rust_report


# ---------------------------------------------------------------------------
# Full-report parity across the check matrix.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"copper_fill_percentages": {}},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"})},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 90.0},
        # Int specs: the oracle's f-string renders the ORIGINAL object —
        # `{90}` is "90" and `{-5}` is "-5" (an f64 extraction renders
        # "90.0"/"-5.0"). The messages must match byte-for-byte.
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 90},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": -5},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 0.0},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 150.0},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 70.0},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 120.0},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 69.99},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": 120.01},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "impedance_spec_ohms": -5.0},
        {"differential_nets": frozenset({"USB_D+", "USB_D-"}), "has_stitching_vias": True},
        {"differential_nets": frozenset({"USB_D+", "USB_D-", "USB_DP"})},
        {"copper_fill_percentages": {"F.Cu": 35.0, "In1.Cu": 65.0, "In2.Cu": 65.0, "B.Cu": 30.0}},
        {"copper_fill_percentages": {"F.Cu": 95.0, "In1.Cu": 10.0, "In2.Cu": 90.0, "B.Cu": 3.0}},
        {"copper_fill_percentages": {"F.Cu": 100.0, "In1.Cu": 0.0, "In2.Cu": 25.0, "B.Cu": 25.0}},
        {"copper_fill_percentages": {"F.Cu": 25.0, "In1.Cu": 75.0}},
        {"copper_fill_percentages": {"Only.Cu": 50.0}},
        {"copper_fill_percentages": {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0}},
    ],
)
def test_validate_stackup_full_report_parity(canonical_stackup, kwargs):
    """The full 4-check report is bit-identical for a broad argument matrix."""
    py_report, rust_report = _both(canonical_stackup, **kwargs)
    assert len(rust_report.results) == len(py_report.results) == 4
    assert _report_keys(rust_report) == _report_keys(py_report)
    # Result-order parity: the four checks appear in the same sequence.
    assert [r.check_name for r in rust_report.results] == [
        r.check_name for r in py_report.results
    ]
    # Each rust result is a StackupValidationResult instance.
    assert all(isinstance(r, STACKUP_VALIDATION_RESULT) for r in rust_report.results)


# ---------------------------------------------------------------------------
# Report-level parity: all_passed, warnings, summary.
# ---------------------------------------------------------------------------


def test_report_all_passed_parity(canonical_stackup, balanced_fill):
    py_report, rust_report = _both(
        canonical_stackup, copper_fill_percentages=balanced_fill
    )
    assert rust_report.all_passed == py_report.all_passed


def test_report_fail_closed_on_empty():
    """all_passed is False for a report with no results (anti-vacuity)."""
    py_report = _oracle.StackupValidationReport(results=[])
    rust_report = STACKUP_VALIDATION_REPORT(results=[])
    assert py_report.all_passed is False
    assert rust_report.all_passed is False


def test_report_warnings_parity(canonical_stackup, unbalanced_fill):
    py_report, rust_report = _both(
        canonical_stackup, copper_fill_percentages=unbalanced_fill
    )
    assert _report_keys(rust_report) == _report_keys(py_report)
    assert len(rust_report.warnings) == len(py_report.warnings)
    assert [w.check_name for w in rust_report.warnings] == [
        w.check_name for w in py_report.warnings
    ]
    assert [w.passed for w in rust_report.warnings] == [False] * len(py_report.warnings)


def test_report_summary_parity(canonical_stackup, unbalanced_fill):
    py_report, rust_report = _both(
        canonical_stackup,
        copper_fill_percentages=unbalanced_fill,
        differential_nets=frozenset({"USB_D+", "USB_D-"}),
        impedance_spec_ohms=None,
    )
    assert rust_report.summary() == py_report.summary()


def test_report_summary_parity_all_pass(canonical_stackup, balanced_fill):
    py_report, rust_report = _both(
        canonical_stackup, copper_fill_percentages=balanced_fill
    )
    assert rust_report.summary() == py_report.summary()


# ---------------------------------------------------------------------------
# Per-check message-pinning (byte-identical strings).
# ---------------------------------------------------------------------------


def test_symmetry_default_fill_message(canonical_stackup):
    """Default Temper fills: symmetry passes with the '22.4%' message."""
    py_report, rust_report = _both(canonical_stackup, copper_fill_percentages={})
    py_r = next(r for r in py_report.results if r.check_name == "Copper Symmetry")
    rust_r = next(r for r in rust_report.results if r.check_name == "Copper Symmetry")
    assert rust_r.message == py_r.message
    assert "22.4%" in rust_r.message


def test_symmetry_warn_details_bit_exact(canonical_stackup):
    """Unbalanced fills: warn message + details dict are bit-identical."""
    py_report, rust_report = _both(
        canonical_stackup,
        copper_fill_percentages={"F.Cu": 95.0, "In1.Cu": 10.0, "In2.Cu": 90.0, "B.Cu": 3.0},
    )
    py_r = next(r for r in py_report.results if r.check_name == "Copper Symmetry")
    rust_r = next(r for r in rust_report.results if r.check_name == "Copper Symmetry")
    assert rust_r.message == py_r.message
    assert rust_r.layer == py_r.layer
    assert _details_key(rust_r.details) == _details_key(py_r.details)


def test_symmetry_tie_for_heaviest_layer_names_first(canonical_stackup):
    """When In1.Cu and In2.Cu tie for max effective weight, the warn names
    the FIRST (In1.Cu) as heaviest — CPython max()/min() first-wins on ties
    (discriminates a last-wins argmax mutant)."""
    fills = {"F.Cu": 5.0, "In1.Cu": 95.0, "In2.Cu": 95.0, "B.Cu": 2.0}
    py_report, rust_report = _both(canonical_stackup, copper_fill_percentages=fills)
    py_r = next(r for r in py_report.results if r.check_name == "Copper Symmetry")
    rust_r = next(r for r in rust_report.results if r.check_name == "Copper Symmetry")
    assert not rust_r.passed  # imbalance (0.95-0.02)/2.02 > 0.25 -> warn
    assert rust_r.message == py_r.message
    assert rust_r.layer == "In1.Cu vs B.Cu"
    assert rust_r.details["max_eff"] == py_r.details["max_eff"] == 0.95
    assert float(rust_r.details["imbalance"]).hex() == float(py_r.details["imbalance"]).hex()


def test_symmetry_zero_effective_copper(canonical_stackup):
    """All-zero fill: 'Zero effective copper' skip message."""
    py_report, rust_report = _both(
        canonical_stackup, copper_fill_percentages={"F.Cu": 0.0, "In1.Cu": 0.0}
    )
    py_r = next(r for r in py_report.results if r.check_name == "Copper Symmetry")
    rust_r = next(r for r in rust_report.results if r.check_name == "Copper Symmetry")
    assert rust_r.message == py_r.message == "Zero effective copper -- symmetry check skipped"


def test_symmetry_nonstandard_layers():
    """A stackup whose layers are not the default names: no defaults applied."""
    from temper_placer.core.board import Layer

    stackup = LayerStackup(
        layers=(
            Layer("L1", "signal", 1.0, True),
            Layer("L2", "plane", 1.0, False),
        )
    )
    py_report, rust_report = _both(stackup)
    assert _report_keys(rust_report) == _report_keys(py_report)
    # No fill data -> symmetry + balance skipped; 2 layers -> adjacency pass.
    names = [r.check_name for r in rust_report.results]
    assert all(r.passed for r in rust_report.results), rust_report.summary()


def test_impedance_none_message_contains_sorted_nets(usb_differential_nets):
    """Missing spec: message names the nets in sorted order (byte-identical)."""
    stackup = LayerStackup.default_4layer()
    py_report, rust_report = _both(
        stackup, differential_nets=usb_differential_nets, impedance_spec_ohms=None
    )
    py_r = next(r for r in py_report.results if r.check_name == "Controlled Impedance")
    rust_r = next(r for r in rust_report.results if r.check_name == "Controlled Impedance")
    assert rust_r.message == py_r.message
    assert "90 Omega" in rust_r.message


def test_impedance_invalid_message(canonical_stackup):
    py_report, rust_report = _both(
        canonical_stackup,
        differential_nets=frozenset({"USB_D+"}),
        impedance_spec_ohms=0.0,
    )
    py_r = next(r for r in py_report.results if r.check_name == "Controlled Impedance")
    rust_r = next(r for r in rust_report.results if r.check_name == "Controlled Impedance")
    assert rust_r.message == py_r.message
    assert "Invalid impedance value: 0.0 Omega" in rust_r.message


def test_balance_warn_message_and_details(canonical_stackup):
    py_report, rust_report = _both(
        canonical_stackup,
        copper_fill_percentages={"F.Cu": 95.0, "In1.Cu": 10.0, "In2.Cu": 90.0, "B.Cu": 3.0},
    )
    py_r = next(r for r in py_report.results if r.check_name == "Copper Balance")
    rust_r = next(r for r in rust_report.results if r.check_name == "Copper Balance")
    assert rust_r.message == py_r.message
    assert _details_key(rust_r.details) == _details_key(py_r.details)


def test_balance_pass_message(canonical_stackup, balanced_fill):
    py_report, rust_report = _both(canonical_stackup, copper_fill_percentages=balanced_fill)
    py_r = next(r for r in py_report.results if r.check_name == "Copper Balance")
    rust_r = next(r for r in rust_report.results if r.check_name == "Copper Balance")
    assert rust_r.message == py_r.message
    assert "25.0%-75.0%" not in rust_r.message  # pass message has no target
    assert "balanced" in rust_r.message


def test_adjacency_l4_pwr_warn(canonical_stackup, usb_differential_nets):
    """L4 references L3 (PWR plane) -> warn with the L4 (B.Cu) layer tag."""
    py_report, rust_report = _both(canonical_stackup, differential_nets=usb_differential_nets)
    py_r = next(r for r in py_report.results if r.check_name == "Return-Path Adjacency")
    rust_r = next(r for r in rust_report.results if r.check_name == "Return-Path Adjacency")
    assert rust_r.message == py_r.message
    assert rust_r.layer == py_r.layer == "L4 (B.Cu)"


def test_adjacency_stitching_vias_mitigated(canonical_stackup, usb_differential_nets):
    py_report, rust_report = _both(
        canonical_stackup,
        differential_nets=usb_differential_nets,
        has_stitching_vias=True,
    )
    py_r = next(r for r in py_report.results if r.check_name == "Return-Path Adjacency")
    rust_r = next(r for r in rust_report.results if r.check_name == "Return-Path Adjacency")
    assert rust_r.message == py_r.message
    assert rust_r.passed is True


def test_adjacency_no_diff_nets_skips(canonical_stackup):
    py_report, rust_report = _both(canonical_stackup, differential_nets=frozenset())
    py_r = next(r for r in py_report.results if r.check_name == "Return-Path Adjacency")
    rust_r = next(r for r in rust_report.results if r.check_name == "Return-Path Adjacency")
    assert rust_r.message == py_r.message
    assert "No differential nets" in rust_r.message


def test_adjacency_indexes_layer_3_not_layer_2():
    """The adjacency check reads layers[2] (the L3 plane slot). A stackup
    whose L2 slot is a plane but whose L3 slot is a signal layer passes —
    discriminating an off-by-one (layers[1]) mutant."""
    from temper_placer.core.board import Layer

    stackup = LayerStackup(
        layers=(
            Layer("F.Cu", "signal", 2.0, True),
            Layer("In1.Cu", "plane", 1.0, False),  # layers[1] IS a plane
            Layer("In2.Cu", "signal", 1.0, False),  # layers[2] is NOT
            Layer("B.Cu", "signal", 1.0, True),
        )
    )
    nets = frozenset({"USB_D+"})
    py_report, rust_report = _both(stackup, differential_nets=nets)
    py_r = next(r for r in py_report.results if r.check_name == "Return-Path Adjacency")
    rust_r = next(r for r in rust_report.results if r.check_name == "Return-Path Adjacency")
    assert py_r.passed is True  # oracle: layers[2] is not a plane -> pass
    assert rust_r.message == py_r.message
    assert rust_r.passed is True


# ---------------------------------------------------------------------------
# Int-typed fill values (dtype polymorphism — fill dicts may hold ints).
# ---------------------------------------------------------------------------


def test_int_typed_fill_values_parity(canonical_stackup):
    """int fill values promote identically (35/100.0 vs 35.0/100.0)."""
    py_report, rust_report = _both(
        canonical_stackup,
        copper_fill_percentages={"F.Cu": 35, "In1.Cu": 65, "In2.Cu": 65, "B.Cu": 30},
    )
    assert _report_keys(rust_report) == _report_keys(py_report)


def test_int_copper_weight_layer():
    """A Layer with an int copper_weight (e.g. 1) computes identically."""
    from temper_placer.core.board import Layer

    stackup = LayerStackup(
        layers=(
            Layer("F.Cu", "signal", 1, True),
            Layer("In1.Cu", "plane", 1, False),
            Layer("In2.Cu", "plane", 1, False),
            Layer("B.Cu", "signal", 1, True),
        )
    )
    py_report, rust_report = _both(
        stackup,
        copper_fill_percentages={"F.Cu": 50.0, "In1.Cu": 50.0, "In2.Cu": 50.0, "B.Cu": 50.0},
    )
    assert _report_keys(rust_report) == _report_keys(py_report)


# ---------------------------------------------------------------------------
# Routing-results fill arm (the Python call-back path).
# ---------------------------------------------------------------------------


class _StubRoutingResults:
    """Minimal stand-in for RoutingResults so the call-back arm runs.

    ``analyze_copper_balance`` iterates ``compiled_routes``; an empty dict
    yields zero copper area on every layer, so the resolved fill is all
    zeros — exercising the routing call-back arm on both sides.
    """

    compiled_routes = {}


def test_routing_results_fill_arm_parity(canonical_stackup):
    """routing_results + board_dims resolves fill via the Python call-back."""
    py_report, rust_report = _both(
        canonical_stackup,
        routing_results=_StubRoutingResults(),
        board_dims=(50.0, 40.0),
    )
    assert _report_keys(rust_report) == _report_keys(py_report)
