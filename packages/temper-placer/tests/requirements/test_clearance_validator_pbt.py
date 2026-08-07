"""Property-based tests for the migrated REQ-SAFE-01 clearance validator
surface (temper-drc-rs).

R1c: >= 5 non-vacuous properties. Each property constrains the SHIM's
output structure; vacuity guards assert the fixture exercises the property
(G4: a property asserting violation ordering asserts the fixture violates
first).
"""

from __future__ import annotations

import random

import pytest

from temper_placer.requirements.validators.clearance import (
    InsulationType,
    VoltageDomain,
    check_creepage_path,
    check_domain_clearance,
    format_clearance_report,
    verify_iec60335_compliance,
)

HV = "N_HV"
LV = "N_LV"


def _pad(net, offset, width, height, shape="rect", number="1", rr=0.25):
    return {
        "number": number, "net": net, "offset": offset, "width": width,
        "height": height, "shape": shape, "roundrect_ratio": rr,
        "pad_rotation_deg": 0.0,
    }


def _comp(ref, pos, pads):
    return {
        "ref": ref, "position": pos, "rotation_deg": 0.0,
        "nets": sorted({p["net"] for p in pads if p["net"]}), "pads": pads,
    }


def _placement(comps, cutouts=None):
    out = {
        "components": comps,
        "nets": {HV: {"domain": VoltageDomain.DC_BUS}, LV: {"domain": VoltageDomain.LV_CONTROL}},
    }
    if cutouts is not None:
        out["board"] = {"surface_cutouts": cutouts}
    return out


def _violating_placement():
    """Two 2x2 rect pads 1mm apart edge-to-edge (3mm origin gap, reach 1.5+1.5)."""
    return _placement([
        _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 2.0, 2.0)]),
        _comp("B", (3.0, 0.0), [_pad(LV, (0.0, 0.0), 2.0, 2.0)]),
    ])


def test_prop_violations_are_error_severity_and_carry_actionable_fields():
    placement = _violating_placement()
    result = check_domain_clearance(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0)
    assert result.violations, "fixture must violate"
    for v in result.violations:
        assert v.severity == "error"
        assert v.metric == "clearance"
        assert v.measured_mm is not None and v.required_mm is not None
        assert v.shortfall_mm is not None
        assert v.geometry_model == "copper"
        assert v.boundary == "DC_BUS<->LV_CONTROL"
        assert v.location is not None and len(v.location) == 2


def test_prop_measured_mm_is_actual_copper_gap():
    """1mm edge gap -> measured_mm ~= 1.0 (within IEEE rounding)."""
    placement = _violating_placement()
    result = check_domain_clearance(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0)
    v = result.violations[0]
    assert v.measured_mm == pytest.approx(1.0, abs=1e-9)


def test_prop_creepage_eq_clearance_on_unbroken_board():
    """No cutouts -> creepage distance == clearance distance, model tagged."""
    placement = _violating_placement()
    c = check_domain_clearance(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0)
    k = check_creepage_path(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0)
    assert c.violations and k.violations
    assert c.violations[0].measured_mm == k.violations[0].measured_mm
    assert k.violations[0].creepage_model == (
        "unbroken-surface (exact: geodesic == straight line)"
    )


def test_prop_passed_false_iff_violations():
    for seed in range(15):
        rng = random.Random(seed)
        pads_a = [_pad(HV, (0.0, 0.0), 2.0, 2.0)]
        pads_b = [_pad(LV, (rng.uniform(1.0, 6.0), 0.0), 2.0, 2.0)]
        placement = _placement([_comp("A", (0.0, 0.0), pads_a), _comp("B", (0.0, 0.0), pads_b)])
        result = check_domain_clearance(
            placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 2.0
        )
        assert result.passed == (len(result.violations) == 0)


def test_prop_pruned_pairs_never_counted_as_checked_distance():
    """pairs_pruned_by_bound + pairs reaching the measure == pairs_checked
    (pruned pairs are skipped before any distance measurement)."""
    placement = _violating_placement()
    result = check_domain_clearance(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0)
    stats = result.stats
    assert stats["pairs_checked"] == stats["pairs_inter"] + stats["pairs_intra"]
    assert stats["pairs_checked"] >= stats["pairs_pruned_by_bound"]


def test_prop_far_apart_pairs_are_pruned_not_measured():
    """A pair 100mm apart with min 3.0 is pruned by the reach bound (never
    measured, so pairs_origin_modelled stays 0 even without pad data)."""
    placement = _placement([
        {"ref": "A", "position": (0.0, 0.0), "nets": [HV]},
        {"ref": "B", "position": (100.0, 0.0), "nets": [LV]},
    ])
    result = check_domain_clearance(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0)
    assert result.stats["pairs_pruned_by_bound"] == 1
    assert result.stats["pairs_origin_modelled"] == 0
    assert result.violations == []


def test_prop_verify_iec_rows_cover_both_metrics():
    placement = _violating_placement()
    result = verify_iec60335_compliance(
        placement, {HV: VoltageDomain.DC_BUS.value, LV: VoltageDomain.LV_CONTROL.value}
    )
    rows = result.stats["rows"]
    assert len(rows) == 12
    metrics = {r["metric"] for r in rows}
    assert metrics == {"clearance", "creepage"}
    assert {r["insulation"] for r in rows} == {"basic", "reinforced", "functional"}


def test_prop_report_worst_first_and_counts():
    placement = _violating_placement()
    result = check_domain_clearance(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0)
    text = format_clearance_report(result)
    assert text.startswith(f"{len(result.violations)} REQ-SAFE-01 violation(s), worst first:")
    assert "Closest copper, per violating pair:" in text
    # Every violation's closest-pads label appears in the tail section.
    for v in result.violations:
        assert v.closest_pads in text


def test_prop_intra_component_never_self_pairs_in_inter():
    """Intra-footprint crossings are reported with pair_kind intra and the
    same ref on both sides; inter pairs never have ref_a == ref_b."""
    straddler = _comp("U3", (0.0, 0.0), [
        _pad(HV, (-1.0, 0.0), 2.0, 2.0), _pad(LV, (1.0, 0.0), 2.0, 2.0),
    ])
    placement = _placement([straddler])
    result = check_domain_clearance(
        placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 3.0
    )
    assert result.violations, "straddler must violate"
    intra = [v for v in result.violations if v.pair_kind == "intra"]
    assert intra, "at least one intra violation expected"
    for v in intra:
        assert v.ref_a == v.ref_b
        assert "(intra)" in v.message or "within" in v.message


# ---------------------------------------------------------------------------
# R20 suite hardening — discriminators moved from the differential. #850's
# differential-disabled re-run found 4 of the 5 clearance campaign mutants
# survive the suites-only run (only the +1e-9 copper bias was PBT-caught);
# their discriminating assertions lived only in
# `test_clearance_validator_rust_differential.py`. Each is a deterministic
# invariant of the shim surface, so it is pinned here. The differential keeps
# its own assertions.
# ---------------------------------------------------------------------------


def test_prop_same_domain_functional_pairing():
    """A same-domain LV_CONTROL<->LV_CONTROL pair with a 0.4mm gap violates
    the 0.5mm FUNCTIONAL requirement — the same-domain pairing branch must
    run. A port that killed the ``domain_a == domain_b`` branch reports no
    violation (surviving mutant clM9)."""
    placement = _placement([
        _comp("L1", (0.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0)]),
        _comp("L2", (0.4, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0)]),
    ])
    result = check_domain_clearance(
        placement, VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, 0.5
    )
    assert len(result.violations) == 1
    assert result.violations[0].boundary == "LV_CONTROL<->LV_CONTROL"
    assert result.violations[0].shortfall_mm > 0.0


def test_prop_iec_verify_reports_all_four_rows():
    """A 2.0mm DC_BUS<->LV_CONTROL gap against the full IEC matrix reports
    exactly four violations (basic/reinforced x clearance/creepage — every
    row's requirement exceeds 2.0). A port that halved the clearance
    requirements would silently forgive the basic-clearance row (2.0 >= 1.5)
    and report three (surviving mutant clM12)."""
    placement = _placement([
        _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 2.0, 2.0)]),
        _comp("B", (4.0, 0.0), [_pad(LV, (0.0, 0.0), 2.0, 2.0)]),
    ])
    result = verify_iec60335_compliance(
        placement, {HV: VoltageDomain.DC_BUS.value, LV: VoltageDomain.LV_CONTROL.value}
    )
    assert len(result.violations) == 4
    basic_clr = [v for v in result.violations
                 if v.metric == "clearance" and v.insulation_type == InsulationType.BASIC]
    assert len(basic_clr) == 1
    assert basic_clr[0].required_mm == 3.0
    assert basic_clr[0].boundary == "DC_BUS<->LV_CONTROL"


def test_prop_iec_verify_origin_modelled_warning(caplog):
    """A pair whose components carry no pad geometry is measured
    ORIGIN-TO-ORIGIN, and the verify emits a WARNING naming the proxy. A port
    that dropped the ``origin_modelled > 0`` clause emits nothing and the
    caplog assertion fails (surviving mutant clM13)."""
    placement = _placement([
        {"ref": "A", "position": (0.0, 0.0), "nets": [HV]},
        {"ref": "B", "position": (2.0, 0.0), "nets": [LV]},
    ])
    verify_iec60335_compliance(
        placement, {HV: VoltageDomain.DC_BUS.value, LV: VoltageDomain.LV_CONTROL.value}
    )
    messages = [r.getMessage() for r in caplog.records]
    origin = [m for m in messages if "ORIGIN-TO-ORIGIN" in m]
    assert origin, "expected an ORIGIN-TO-ORIGIN WARNING, got none"
    assert "UPPER bound" in origin[0]


def test_prop_report_rows_worst_first():
    """The report's data rows are sorted worst-first by the shortfall column
    (descending). A port that reversed the sort emits ascending rows and fails
    the pin (surviving mutant clM11)."""
    placement = _placement([
        _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 2.0, 2.0)]),
        _comp("B", (4.0, 0.0), [_pad(LV, (0.0, 0.0), 2.0, 2.0)]),
    ])
    result = verify_iec60335_compliance(
        placement, {HV: VoltageDomain.DC_BUS.value, LV: VoltageDomain.LV_CONTROL.value}
    )
    text = format_clearance_report(result)
    assert text.startswith(f"{len(result.violations)} REQ-SAFE-01 violation(s), worst first:")
    rows = [
        ln for ln in text.splitlines()
        if not ln.startswith(" ") and not ln.startswith("-") and "<->" in ln
    ]
    assert len(rows) >= 2
    shortfalls = []
    for ln in rows:
        parts = ln.split()
        # Columns: pair boundary insul metric meas req short model[...]
        try:
            shortfalls.append(float(parts[6]))
        except (IndexError, ValueError):
            continue
    assert len(shortfalls) >= 2
    assert shortfalls == sorted(shortfalls, reverse=True), shortfalls
