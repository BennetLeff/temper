"""Property-based tests for the migrated drc validation kernels
(temper_drc_rs.validation) — the suites-only home for the R20
discriminators moved out of the `test_{drc_oracle,tht_check,geometric,drc,
drc_fence}_rust_differential.py` files.

#850's differential-disabled re-run (docs/evidence/2026-08-06-r20-differential-
disabled-rerun.md) found 10 of the 12 drc-validation campaign mutants survive
the suites-only run because their discriminating assertions lived only inside
the differential files. Every one of those assertions is a deterministic
invariant of a kernel exported on ``temper_drc_rs`` (each is a verbatim port
of the pre-migration Python), so it is pinned here as a literal property case
— no oracle import, no shim round-trip. The differentials keep their own
(identical) assertions; nothing here weakens them.

Each test documents which surviving mutant it discriminates (vMx labels match
the campaign in /tmp/wt9-r20_r20_driver.py).
"""

from __future__ import annotations

import temper_drc_rs as _tdrc

# ---------------------------------------------------------------------------
# vM1 — infer_package_type drops "dip" from the THT keyword list
# ---------------------------------------------------------------------------


def test_p1_infer_package_type_tht_keyword_table():
    """Every THT keyword — including ``dip`` — maps to ``tht`` (DIP-8 is the
    canonical case). A port that dropped ``dip`` classifies DIP-8 as ``smd``
    and fails the pin (surviving mutant vM1)."""
    cases = [
        ("THT", "tht"),
        ("ThroughHole", "tht"),
        ("PIN_HEADER", "tht"),
        ("DIP-8", "tht"),
        ("CAPACITOR_THT_ELECTRO", "tht"),
        ("to-247", "to247"),
        ("TO-220", "to220"),
        ("BGA-100", "bga"),
        ("QFN-32", "qfn"),
        ("TQFP-64", "qfp"),
        ("D2PAK", "dpak"),
        ("R_0603", "smd"),
    ]
    for footprint, expected in cases:
        assert _tdrc.infer_package_type(footprint) == expected, footprint


# ---------------------------------------------------------------------------
# vM2 / vM3 — tht_hole_collisions message precision and +min_clearance
# ---------------------------------------------------------------------------


def test_p2_tht_message_three_decimal_precision():
    """Every THT message renders both ``dist`` and ``min`` with exactly three
    decimals. A ``:.2`` port renders two and fails the token pin (surviving
    mutant vM2)."""
    holes = [("C1", "P1", 0.0, 0.0, 1.0), ("C1", "P2", 0.0, 0.0, 1.0)]
    msgs = _tdrc.tht_hole_collisions(holes, 0.0)
    assert msgs == ["C1.P1 <-> C1.P2: dist=0.000mm (min 2.000mm)"]
    for m in msgs:
        tail = m.partition(": ")[2]
        for tok in (tail.split("dist=")[1].split("mm")[0],
                    tail.split("min ")[1].split("mm)")[0]):
            assert "." in tok and len(tok.split(".")[1]) == 3, m


def test_p3_tht_clearance_included_in_required():
    """The ``min`` value in the message is ``r_i + r_j + min_clearance``: a
    pair 1.5mm apart with radii 0.5+0.5 and clearance 0.6 violates (1.5 < 1.6)
    and reports ``min 1.600mm``. A port that dropped ``+ min_clearance``
    requires only 1.0 and reports no violation (surviving mutant vM3)."""
    holes = [("C1", "P1", 0.0, 0.0, 0.5), ("C2", "P1", 1.5, 0.0, 0.5)]
    assert _tdrc.tht_hole_collisions(holes, 0.6) == [
        "C1.P1 <-> C2.P1: dist=1.500mm (min 1.600mm)"
    ]
    # Coincident holes: the message's min value carries the clearance too.
    msgs = _tdrc.tht_hole_collisions([("C1", "P1", 0.0, 0.0, 1.0), ("C2", "P1", 0.0, 0.0, 2.0)], 0.5)
    assert msgs == ["C1.P1 <-> C2.P1: dist=0.000mm (min 3.500mm)"]


# ---------------------------------------------------------------------------
# vM6 / vM7 — geometric_validate overlap severity and boundary flag
# ---------------------------------------------------------------------------


def _two_box_overlap_findings():
    """geometric_validate for two 10x10 boxes 1mm apart center-to-center
    (overlap_amount 9.0) — no boundary/keepout/hole inputs."""
    positions = [(0.0, 0.0), (1.0, 0.0)]
    half_widths = [5.0, 5.0]
    half_heights = [5.0, 5.0]
    net_classes = ["Signal", "Signal"]
    boundary = []
    keepouts = []
    mounting_holes = []
    distances = [0.0, -9.0, 0.0, 0.0]  # n*n row-major; only d01 is read
    return _tdrc.geometric_validate(
        positions, half_widths, half_heights, net_classes, boundary, keepouts,
        mounting_holes, distances, 0.01, 0.2, 10.0,
    )


def test_p4_geometric_overlap_severity_critical():
    """Overlap of 9.0mm is CRITICAL (the ``> 5.0`` tier). A port that raised
    the threshold to ``> 50.0`` would demote it to ERROR and fail the pin
    (surviving mutant vM6)."""
    findings, _metrics = _two_box_overlap_findings()
    overlaps = [f for f in findings if f["kind"] == "overlap"]
    assert len(overlaps) == 1
    assert overlaps[0]["severity"] == "CRITICAL"
    assert overlaps[0]["overlap_amount"] == 9.0


def _boundary_findings():
    """geometric_validate for one 20x20 box at (95, 50) on a 100x100 board —
    extends 5mm past the right edge (boundary violation, max 5.0)."""
    positions = [(95.0, 50.0)]
    half_widths = [10.0]
    half_heights = [10.0]
    net_classes = ["Signal"]
    boundary = [(0.0, 5.0, 0.0, 0.0)]  # (left, right, bottom, top) violations
    keepouts = []
    mounting_holes = []
    distances = [0.0]
    return _tdrc.geometric_validate(
        positions, half_widths, half_heights, net_classes, boundary, keepouts,
        mounting_holes, distances, 0.01, 0.2, 10.0,
    )


def test_p5_geometric_boundary_finding_emitted():
    """A 5mm past-edge violation emits a GEO_BOUNDARY finding with
    max_violation 5.0 and severity ERROR. A port whose flag predicate was
    ``> 1e9`` would emit nothing (surviving mutant vM7)."""
    findings, metrics = _boundary_findings()
    boundaries = [f for f in findings if f["kind"] == "boundary"]
    assert len(boundaries) == 1
    assert boundaries[0]["code"] == "GEO_BOUNDARY"
    assert boundaries[0]["severity"] == "ERROR"
    assert boundaries[0]["max_violation"] == 5.0
    assert metrics["boundary_violations"] == 1


# ---------------------------------------------------------------------------
# vM8 / vM9 — parse_drc_violation default severity / penalty default weight
# ---------------------------------------------------------------------------


def test_p6_parse_default_severity_warning():
    """A violation dict with no ``severity`` key parses to ``WARNING``. A port
    that defaulted to ``error`` fails the pin (surviving mutant vM8)."""
    rec = _tdrc.parse_drc_violation({"type": "track_width"})
    assert rec["severity"] == "WARNING"
    # Explicit severities still map case-insensitively to the canonical names.
    assert _tdrc.parse_drc_violation({"type": "x", "severity": "Error"})["severity"] == "ERROR"


def test_p7_penalty_default_weight_one():
    """A (severity, type) pair absent from both weight dicts scores the 1.0
    defaults: ``1.0 * 1.0 == 1.0``. A port whose default weight was 0.0 would
    score 0.0 and fail the pin (surviving mutant vM9)."""
    assert _tdrc.compute_drc_penalty([("bogus_sev", "bogus_type")], {}, {}) == 1.0
    # Sanity: the lookup path with real weights still applies both multipliers.
    assert _tdrc.compute_drc_penalty(
        [("ERROR", "clearance")], {"ERROR": 10.0}, {"clearance": 2.0}
    ) == 20.0


# ---------------------------------------------------------------------------
# vM10 — group_violations sorted group order
# ---------------------------------------------------------------------------


def test_p8_group_violations_sorted_by_name():
    """Groups are returned in sorted check-name order (``sorted(grouped.
    items())``), independent of first-seen order. A port that dropped the
    ``order.sort()`` would return first-seen order and fail the pin
    (surviving mutant vM10)."""
    groups = _tdrc.group_violations([
        {"check_name": "b_check", "code": "B1"},
        {"check_name": "a_check", "code": "A1"},
        {"check_name": "b_check", "code": "B2"},
    ])
    assert [g[0] for g in groups] == ["a_check", "b_check"]
    assert [r["code"] for r in groups[0][1]] == ["A1"]
    assert [r["code"] for r in groups[1][1]] == ["B1", "B2"]


# ---------------------------------------------------------------------------
# vM11 — issue_fingerprint separator
# ---------------------------------------------------------------------------


def test_p9_fingerprint_comma_separator():
    """The fingerprint joins the sorted affected items with ``,``. A port that
    switched to ``;`` fails the literal pin (surviving mutant vM11)."""
    assert _tdrc.issue_fingerprint("DRC_001", "m", ["b", "a", "c"]) == "DRC_001:m:a,b,c"
    assert _tdrc.issue_fingerprint("DRC_001", "m", []) == "DRC_001:m:"
    assert _tdrc.issue_fingerprint("X", "m", ["Z1", "R10", "R2"]) == "X:m:R10,R2,Z1"


# ---------------------------------------------------------------------------
# vM12 — metrics_summary "erc" category arm
# ---------------------------------------------------------------------------


def test_p10_metrics_summary_erc_arm_counts_erc():
    """An ``erc``-category issue increments ``erc_issues``, not ``drc_issues``.
    A port whose erc arm incremented ``drc`` instead fails the pin (surviving
    mutant vM12)."""
    out = _tdrc.metrics_summary([("c1", 1.0, ["erc"], [])])
    assert out["erc_issues"] == 1
    assert out["drc_issues"] == 0
    assert out["safety_issues"] == 0
    assert out["emc_issues"] == 0
    mixed = _tdrc.metrics_summary([("c1", 1.0, ["erc", "drc", "other", "erc"], [])])
    assert mixed["erc_issues"] == 2
    assert mixed["drc_issues"] == 1
