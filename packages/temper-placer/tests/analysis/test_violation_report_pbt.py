"""Property-based + metamorphic tests for the Rust violation-report kernels.

Wave 4, Phase 4 — the analysis-surface migration (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
R1c/R1d).  These properties exercise the migrated ``temper_drc_rs``
pyfunctions (``build_report_rows``, ``render_report``) and the
``temper_placer.analysis._violation_report`` delegation shim;
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_violation_report_rust_differential.py``.

Properties (all non-vacuously guarded):

- P1. Rule filtering: every produced row's rule is in the target set, and
  every non-target-rule error is dropped.
- P2. Ref shaping: ``refs_sorted`` is the sorted component list for
  ``len >= 2`` and an identical copy otherwise.
- P3. Overlap-descending sort: rows are non-increasing in overlap area,
  and equal keys keep input order (stable sort contract).
- P4. Row field fidelity: rule / components / location / message /
  n_components are transcribed unchanged from the input error.
- P5. Render summary arithmetic: the Summary section counts equal the
  row-rule tallies and ``Total`` equals the row count.
- P6. Render table structure: each rule section's table-row count equals
  its row count, and the components cell is the ``", ".join`` of the
  sorted refs (or ``(none)`` for an empty list).

Metamorphic relations:

- MR1. Summary permutation invariance: the Summary section is identical
  for any permutation of the input rows.
- MR2. Filtering monotonicity: every row produced from an error subset
  appears identically in the rows produced from the superset.
- MR3. Ref-order symmetry: swapping the two components of a pair error
  yields the same row (``refs_sorted`` is the canonical order).
- MR4. Append-stability: appending zero-overlap rows at the end of the
  input preserves the relative order of the pre-existing rows.
"""

from __future__ import annotations

import random

import temper_drc_rs as _drc
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.validation._drc_api import DrcError

MAX_EXAMPLES = 80

_RULES = ["courtyards_overlap", "pth_inside_courtyard", "clearance", "creepage", "unknown"]
_REFS = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=8)
_MESSAGES = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789| _-", min_size=0, max_size=150)


def _err(rule, components, location, message):
    return DrcError(
        rule=rule,
        severity="error",
        location=location,
        message=message,
        components=list(components),
    )


def _rows_from_errors(errors):
    extracted = [
        (getattr(e, "rule", None), tuple(e.components), (e.location[0], e.location[1]), e.message)
        for e in errors
    ]
    return _drc.build_report_rows(extracted, None)


def _summary(rendered: str) -> str:
    idx = rendered.index("## Summary")
    return rendered[idx:]


# --- P1: rule filtering ----------------------------------------------------


@given(
    st.lists(
        st.tuples(st.sampled_from(_RULES), st.lists(_REFS, min_size=0, max_size=4)),
        min_size=0,
        max_size=15,
    )
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_rule_filtering(specs):
    errors = [_err(rule, refs, (1.0, 2.0), "m") for rule, refs in specs]
    rows = _rows_from_errors(errors)
    target = {"courtyards_overlap", "pth_inside_courtyard"}
    assert all(r["rule"] in target for r in rows)
    expected_count = sum(1 for rule, _r in specs if rule in target)
    assert len(rows) == expected_count


# --- P2: ref shaping -------------------------------------------------------


@given(
    st.lists(st.tuples(st.sampled_from(["courtyards_overlap", "pth_inside_courtyard"]), st.lists(_REFS, min_size=0, max_size=4)), min_size=1, max_size=12)
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_refs_shaping(specs):
    errors = [_err(rule, refs, (1.0, 2.0), "m") for rule, refs in specs]
    rows = _rows_from_errors(errors)
    assert len(rows) == len(specs)
    for (_rule, refs), row in zip(specs, rows):
        expected = sorted(refs) if len(refs) >= 2 else list(refs)
        assert row["refs_sorted"] == expected
        assert row["components"] == list(refs)


# --- P3: sort contract -----------------------------------------------------

_TWO_REF_SPECS = st.lists(
    st.tuples(
        st.sampled_from(["courtyards_overlap", "pth_inside_courtyard"]),
        st.lists(_REFS, min_size=0, max_size=4),
        st.floats(allow_nan=False, allow_infinity=False, min_value=0.0, max_value=1e4),
    ),
    min_size=0,
    max_size=15,
)


def _overlap_callback(specs):
    """Deterministic synthetic overlap callback: the spec's overlap value
    keyed by the sorted ref pair (only courtyards_overlap rows with exactly
    two components get called — same dispatch as the real shim callback)."""
    overlap_map = {}
    for rule, refs, overlap in specs:
        if rule == "courtyards_overlap" and len(refs) == 2:
            overlap_map[tuple(sorted(refs))] = overlap
    return lambda a, b: overlap_map.get((a, b), 0.0)


def _rows_with_overlaps(specs):
    return _drc.build_report_rows(
        [(rule, list(refs), (0.0, 0.0), "m") for rule, refs, _overlap in specs],
        _overlap_callback(specs),
    )


@given(_TWO_REF_SPECS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_sort_contract(specs):
    rows = _rows_with_overlaps(specs)
    areas = [r["overlap_area_mm2"] for r in rows]
    assert all(areas[i] >= areas[i + 1] for i in range(len(areas) - 1))


def test_p3_stable_for_equal_keys():
    """Equal overlap areas keep input order (both arms' stable-sort
    contract; the differential pins it against the oracle too)."""
    errors = [
        _err("courtyards_overlap", ["A", "B"], (0.0, 0.0), "first"),
        _err("pth_inside_courtyard", ["Z"], (0.0, 0.0), "second"),
        _err("courtyards_overlap", ["C", "D"], (0.0, 0.0), "third"),
    ]
    rows = _rows_from_errors(errors)
    messages = [r["message"] for r in rows]
    assert messages.index("first") < messages.index("third")
    assert "second" in messages


# --- P4: row field fidelity -------------------------------------------------


@given(
    st.lists(
        st.tuples(st.sampled_from(["courtyards_overlap", "pth_inside_courtyard"]), st.lists(_REFS, min_size=0, max_size=4), st.tuples(st.floats(min_value=-1e4, max_value=1e4), st.floats(min_value=-1e4, max_value=1e4)), _MESSAGES),
        min_size=1,
        max_size=12,
    )
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_row_field_fidelity(specs):
    rows = _drc.build_report_rows(specs, None)
    assert len(rows) == len(specs)
    for row, (rule, refs, location, message) in zip(rows, specs):
        assert row["rule"] == rule
        assert row["location_x"] == location[0]
        assert row["location_y"] == location[1]
        assert row["message"] == message
        assert row["n_components"] == len(refs)


# --- P5: render summary arithmetic -----------------------------------------


@given(_TWO_REF_SPECS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_render_summary(specs):
    rows = _rows_with_overlaps(specs)
    rendered = _drc.render_report(rows)
    summary = _summary(rendered)
    c = sum(1 for r in rows if r["rule"] == "courtyards_overlap")
    p = sum(1 for r in rows if r["rule"] == "pth_inside_courtyard")
    assert f"- `courtyards_overlap` violations: {c}" in summary
    assert f"- `pth_inside_courtyard` violations: {p}" in summary
    assert f"- Total: {len(rows)}" in summary


# --- P6: render table structure --------------------------------------------


@given(_TWO_REF_SPECS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p6_render_table_structure(specs):
    rows = _rows_with_overlaps(specs)
    rendered = _drc.render_report(rows)
    # Count table data rows (lines starting with "| " and a digit).
    table_rows = [ln for ln in rendered.splitlines() if ln.startswith("| ") and ln[2].isdigit()]
    assert len(table_rows) == len(rows)
    for row in rows:
        comps = ", ".join(row["refs_sorted"]) if row["refs_sorted"] else "(none)"
        assert comps in rendered


# --- MR1: summary permutation invariance -----------------------------------


def test_mr1_summary_permutation_invariance():
    rows = [
        {
            "rule": "courtyards_overlap", "refs_sorted": ["A", "B"],
            "location_x": 1.0, "location_y": 2.0, "overlap_area_mm2": 3.0,
            "message": "m1", "n_components": 2, "components": ["A", "B"],
        },
        {
            "rule": "pth_inside_courtyard", "refs_sorted": ["Z"],
            "location_x": 4.0, "location_y": 5.0, "overlap_area_mm2": 0.0,
            "message": "m2", "n_components": 1, "components": ["Z"],
        },
        {
            "rule": "courtyards_overlap", "refs_sorted": ["C", "D"],
            "location_x": 6.0, "location_y": 7.0, "overlap_area_mm2": 1.0,
            "message": "m3", "n_components": 2, "components": ["C", "D"],
        },
    ]
    base = _summary(_drc.render_report(rows))
    for _ in range(30):
        shuffled = rows[:]
        random.Random(20260804 + len(shuffled)).shuffle(shuffled)
        assert _summary(_drc.render_report(shuffled)) == base


# --- MR2: filtering monotonicity -------------------------------------------


@given(
    st.lists(
        st.tuples(st.sampled_from(["courtyards_overlap", "pth_inside_courtyard", "clearance"]), st.lists(_REFS, min_size=0, max_size=4)),
        min_size=0,
        max_size=10,
    )
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_filtering_monotonicity(specs):
    errors = [_err(rule, refs, (1.0, 2.0), f"msg{i}") for i, (rule, refs) in enumerate(specs)]
    subset_rows = _rows_from_errors(errors[: len(errors) // 2])
    superset_rows = _rows_from_errors(errors)
    subset_keys = {(r["rule"], tuple(r["components"]), r["message"]) for r in subset_rows}
    superset_keys = {(r["rule"], tuple(r["components"]), r["message"]) for r in superset_rows}
    assert subset_keys <= superset_keys


# --- MR3: ref-order symmetry ------------------------------------------------
#
# The canonical ``refs_sorted`` field and the overlap are invariant under a
# swap of the two components (the sort canonicalises the pair order).  The
# ``components`` field deliberately preserves the INPUT order (it mirrors the
# oracle's ``err.components`` verbatim), so the invariant is asserted on the
# canonicalised fields only — that is the honest bound.


@given(st.lists(_REFS, min_size=2, max_size=4))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr3_ref_order_symmetry(refs):
    a = _rows_from_errors([_err("courtyards_overlap", refs, (0.0, 0.0), "m")])
    b = _rows_from_errors([_err("courtyards_overlap", list(reversed(refs)), (0.0, 0.0), "m")])
    assert len(a) == len(b) == 1
    assert a[0]["refs_sorted"] == b[0]["refs_sorted"] == sorted(refs)
    assert a[0]["overlap_area_mm2"] == b[0]["overlap_area_mm2"]


# --- MR4: append-stability --------------------------------------------------


def test_mr4_append_stability():
    errors = [
        _err("courtyards_overlap", ["A", "B"], (0.0, 0.0), "first"),
        _err("courtyards_overlap", ["C", "D"], (0.0, 0.0), "second"),
        _err("pth_inside_courtyard", ["Z"], (0.0, 0.0), "third"),
    ]
    base = _rows_from_errors(errors)
    base_ids = [r["message"] for r in base]
    appended = _rows_from_errors(
        errors + [_err("courtyards_overlap", ["E", "F"], (0.0, 0.0), "appended")]
    )
    appended_ids = [r["message"] for r in appended]
    # Stable sort: appended 0.0-overlap row lands after all pre-existing
    # rows, preserving their relative order.
    assert [m for m in appended_ids if m in base_ids] == base_ids
    assert appended_ids[-1] == "appended"
