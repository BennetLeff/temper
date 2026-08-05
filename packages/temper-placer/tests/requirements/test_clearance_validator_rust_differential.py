"""Differential test: the REQ-SAFE-01 clearance/creepage validator compute
(temper-drc-rs) vs the pinned Python oracles.

Wave 4, Phase 5 — the requirements surface migration. The Rust migration
(reproducing ``temper_placer/requirements/validators/clearance.py`` and
``_copper.py`` bit-identically in ``temper-drc-rs``) is driven through the
delegation shims; the pre-migration implementations are pinned verbatim as
oracles (``tests/requirements/clearance_oracle/`` — a package so the
relative ``from ._copper`` import survives verbatim).

Compared bit-exactly:
- every ``ClearanceViolation`` field (floats via ``float.hex()``),
- the whole ``stats`` dict (concrete leaf types),
- ``passed``,
- ``format_clearance_report`` text byte-identical,
- the requirement matrix,
- WARNING log records (message text; logger names differ by module
  location and are not part of the behaviour being pinned).

The copper geometry half (temper-geometry) was already migrated in Wave 3
and is pinned by ``tests/requirements/test_clearance_rust_differential.py``;
BOTH arms call the same ``temper_geometry`` bindings, so this differential
pins the validator's own pairing/measurement/reporting logic.

Module-scope RED arm: ``_rust.req_safe_01_*`` must exist (fails to collect
until the temper-drc-rs surface lands).
"""

from __future__ import annotations

import random

import temper_drc_rs as _rust

from temper_placer.requirements.validators.clearance import (
    InsulationType,
    VoltageDomain,
    check_creepage_path,
    check_domain_clearance,
    format_clearance_report,
    get_requirement_matrix,
    verify_iec60335_compliance,
)
from tests.requirements import clearance_oracle as _oracle_pkg
from tests.requirements.clearance_oracle import _copper as _oracle_copper

# Module-scope RED arm.
assert hasattr(_rust, "req_safe_01_check_domain_clearance")
assert hasattr(_rust, "req_safe_01_check_creepage_path")
assert hasattr(_rust, "req_safe_01_verify_iec60335")
assert hasattr(_rust, "req_safe_01_format_clearance_report")
assert hasattr(_rust, "req_safe_01_requirement_matrix")

HV = "N_HV"
LV = "N_LV"
NETS = {
    HV: {"domain": VoltageDomain.DC_BUS},
    LV: {"domain": VoltageDomain.LV_CONTROL},
}
NETS_STR = {HV: "DC_BUS", LV: "LV_CONTROL"}


def _pad(net, offset, width, height, shape, number="1", roundrect_ratio=0.25, pad_rot=0.0):
    return {
        "number": number,
        "net": net,
        "offset": offset,
        "width": width,
        "height": height,
        "shape": shape,
        "roundrect_ratio": roundrect_ratio,
        "pad_rotation_deg": pad_rot,
    }


def _comp(ref, position, pads=None, nets=None, rotation_deg=0.0):
    comp = {"ref": ref, "position": position, "rotation_deg": rotation_deg}
    if pads is not None:
        comp["pads"] = pads
        comp["nets"] = sorted({p["net"] for p in pads if p["net"]})
    else:
        comp["nets"] = nets or []
    return comp


def _placement(components, cutouts=None, nets=None):
    out = {"components": components, "nets": nets or dict(NETS)}
    if cutouts is not None:
        out["board"] = {"surface_cutouts": cutouts}
    return out


# ---------------------------------------------------------------------------
# Canonicalisation
# ---------------------------------------------------------------------------

def _f(v):
    """Bit-exact float key (None stays None)."""
    return None if v is None else float(v).hex()


def _violation_key(v):
    return (
        v.code,
        v.message,
        None if v.location is None else (_f(v.location[0]), _f(v.location[1])),
        v.severity,
        v.boundary,
        None if v.insulation_type is None else v.insulation_type.value,
        _f(v.measured_clearance_mm),
        _f(v.measured_creepage_mm),
        _f(v.required_clearance_mm),
        _f(v.required_creepage_mm),
        v.ref_a,
        v.ref_b,
        v.metric,
        _f(v.measured_mm),
        _f(v.required_mm),
        v.geometry_model,
        v.creepage_model,
        v.pair_kind,
        v.closest_pads,
        _f(v.shortfall_mm),
    )


def _stats_key(stats):
    out = {}
    for k, v in sorted(stats.items()):
        if isinstance(v, list):
            out[k] = tuple(_leaf(x) for x in v)
        elif isinstance(v, dict):
            out[k] = tuple(sorted((kk, _leaf(vv)) for kk, vv in v.items()))
        else:
            out[k] = _leaf(v)
    return tuple(sorted(out.items()))


def _leaf(x):
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, int):
        return ("int", x)
    if isinstance(x, float):
        return ("float", x.hex())
    return ("str", x)


def _result_key(r):
    return (r.passed, tuple(_violation_key(v) for v in r.violations), _stats_key(r.stats))


def _log_messages(caplog, before):
    return [(rec.levelname, rec.getMessage()) for rec in caplog.records[before:]]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _fixture_placements() -> list[dict]:
    rng = random.Random(0x5AFE)
    shapes = ["circle", "oval", "rect", "roundrect", "thru_hole", "custom"]
    placements = []

    # No-pad (origin model) fixtures.
    placements.append(_placement([
        _comp("U1", (10, 10), nets=["N_HV"]),
        _comp("Q1", (12, 10), nets=["N_LV"]),
    ]))
    placements.append(_placement([
        _comp("A", (0.0, 0.0), nets=["N_HV"]),
        _comp("B", (100.0, 0.0), nets=["N_LV"]),
    ]))
    placements.append({"components": [], "nets": dict(NETS)})

    # Pad-geometry fixtures.
    for _ in range(30):
        comps = []
        for j in range(rng.randint(1, 5)):
            ref = f"C{j}"
            net = rng.choice([HV, LV])
            rot = rng.choice([0.0, 90.0, 45.0, 180.0, -30.0])
            pads = []
            for k in range(rng.randint(1, 4)):
                pads.append(_pad(
                    net,
                    (rng.uniform(-5, 5), rng.uniform(-5, 5)),
                    rng.choice([1.0, 2.0, 4.0, 8.0]),
                    rng.choice([1.0, 2.0, 4.0, 8.0]),
                    rng.choice(shapes),
                    number=str(k + 1),
                    roundrect_ratio=rng.choice([0.0, 0.25, 0.5]),
                    pad_rot=rng.choice([0.0, 45.0, 90.0]),
                ))
            comps.append(_comp(ref, (rng.uniform(-60, 60), rng.uniform(-60, 60)), pads, rotation_deg=rot))
        placements.append(_placement(comps))

    # A component whose own pads straddle the domain boundary.
    straddler = _comp("U3", (5.0, 5.0), [
        _pad(HV, (-1.0, 0.0), 2.0, 2.0, "rect"),
        _pad(LV, (1.0, 0.0), 2.0, 2.0, "rect"),
    ])
    other = _comp("R9", (50.0, 50.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")])
    placements.append(_placement([straddler, other]))

    # Cutouts declared.
    placements.append(_placement([
        _comp("A", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 4.0, 4.0, "rect")]),
        _comp("B", (10.0, 0.0), [_pad(LV, (0.0, 0.0), 4.0, 4.0, "rect")]),
    ], cutouts=[(5.0, -2.0), (5.0, 2.0), (6.0, 2.0), (6.0, -2.0)]))

    # Missing nets key on a component.
    placements.append(_placement([
        {"ref": "X1", "position": (0.0, 0.0), "nets": ["N_HV", "UNKNOWN"]},
        _comp("X2", (5.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
    ]))

    # Component with ref defaulting to "?".
    placements.append(_placement([
        {"position": (0.0, 0.0), "nets": ["N_HV"]},
        {"position": (4.0, 0.0), "nets": ["N_LV"]},
    ]))

    # Duplicate refs (same ref in both domains).
    placements.append(_placement([
        _comp("D1", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 1.0, 1.0, "rect")]),
        _comp("D1", (3.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
    ]))

    # Same-domain (LV<->LV FUNCTIONAL row).
    placements.append(_placement([
        _comp("L1", (0.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
        _comp("L2", (0.4, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
    ]))

    # Overrides path (voltage_domains passed to verify).
    placements.append(_placement([
        _comp("A", (0.0, 0.0), [_pad("N_X", (0.0, 0.0), 1.0, 1.0, "rect")]),
        _comp("B", (8.0, 0.0), [_pad("N_Y", (0.0, 0.0), 1.0, 1.0, "rect")]),
    ], nets={"N_X": {"domain": VoltageDomain.MAINS}, "N_Y": {"domain": VoltageDomain.LV_CONTROL}}))

    # Component with an EMPTY-STRING ref: "" is falsy, so the report's pair
    # column falls back to '?' via `ref_a or "?"` (None and '' must render
    # identically). Appended LAST so the index-based fixtures above (e.g.
    # placements[38]) keep pointing at their fixtures.
    placements.append(_placement([
        _comp("", (0.0, 0.0), [_pad(HV, (0.0, 0.0), 1.0, 1.0, "rect")]),
        _comp("B", (4.0, 0.0), [_pad(LV, (0.0, 0.0), 1.0, 1.0, "rect")]),
    ]))

    return placements


# ---------------------------------------------------------------------------
# Differential tests
# ---------------------------------------------------------------------------

class TestCheckDomainClearance:
    def test_clearance_identical(self, caplog):
        for placement in _fixture_placements():
            caplog.clear()
            ours = check_domain_clearance(
                placement, VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, 3.0
            )
            logs_ours = _log_messages(caplog, 0)
            caplog.clear()
            theirs = _oracle_pkg.clearance.check_domain_clearance(
                placement, VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, 3.0
            )
            logs_theirs = _log_messages(caplog, 0)
            assert _result_key(ours) == _result_key(theirs)
            assert logs_ours == logs_theirs

    def test_clearance_min_thresholds(self, caplog):
        for min_mm in [0.5, 1.0, 2.5, 1000.0]:
            for placement in _fixture_placements()[:8]:
                caplog.clear()
                ours = check_domain_clearance(
                    placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, min_mm
                )
                logs_ours = _log_messages(caplog, 0)
                caplog.clear()
                theirs = _oracle_pkg.clearance.check_domain_clearance(
                    placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, min_mm
                )
                logs_theirs = _log_messages(caplog, 0)
                assert _result_key(ours) == _result_key(theirs)
                assert logs_ours == logs_theirs

    def test_same_domain_functional_pairing(self, caplog):
        placement = _fixture_placements()[38]  # L1/L2 same-domain fixture
        caplog.clear()
        ours = check_domain_clearance(
            placement, VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, 0.5
        )
        logs_ours = _log_messages(caplog, 0)
        caplog.clear()
        theirs = _oracle_pkg.clearance.check_domain_clearance(
            placement, VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, 0.5
        )
        logs_theirs = _log_messages(caplog, 0)
        assert _result_key(ours) == _result_key(theirs)
        assert logs_ours == logs_theirs
        # 0.4mm gap against a 0.5mm FUNCTIONAL requirement must violate.
        assert len(ours.violations) == 1


class TestCheckCreepage:
    def test_creepage_no_cutouts_identical(self, caplog):
        for placement in _fixture_placements()[:12]:
            caplog.clear()
            ours = check_creepage_path(
                placement, VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, 4.0
            )
            logs_ours = _log_messages(caplog, 0)
            caplog.clear()
            theirs = _oracle_pkg.clearance.check_creepage_path(
                placement, VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, 4.0
            )
            logs_theirs = _log_messages(caplog, 0)
            assert _result_key(ours) == _result_key(theirs)
            assert logs_ours == logs_theirs

    def test_creepage_with_cutouts_identical(self, caplog):
        for placement in _fixture_placements():
            if "board" not in placement:
                continue
            caplog.clear()
            ours = check_creepage_path(
                placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 2.0
            )
            logs_ours = _log_messages(caplog, 0)
            caplog.clear()
            theirs = _oracle_pkg.clearance.check_creepage_path(
                placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 2.0
            )
            logs_theirs = _log_messages(caplog, 0)
            assert _result_key(ours) == _result_key(theirs)
            assert logs_ours == logs_theirs

    def test_creepage_models_pinned(self, caplog):
        """Unbroken surface vs straight-line-lower-bound tagging."""
        placement = _fixture_placements()[34]  # has cutouts
        result = check_creepage_path(placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 1000.0)
        assert result.violations, "cutout fixture must violate at 1000mm"
        models = {v.creepage_model for v in result.violations}
        assert models == {_oracle_copper.CREEPAGE_MODEL_STRAIGHT_LINE_LOWER_BOUND}
        placement2 = _fixture_placements()[6]  # no cutouts
        result2 = check_creepage_path(placement2, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 1000.0)
        assert result2.violations, "no-cutout fixture must violate at 1000mm"
        for v in result2.violations:
            assert v.creepage_model == _oracle_copper.CREEPAGE_MODEL_UNBROKEN_SURFACE


class TestVerifyIec60335:
    def test_verify_identical(self, caplog):
        for placement in _fixture_placements():
            caplog.clear()
            ours = verify_iec60335_compliance(placement, dict(NETS_STR))
            logs_ours = _log_messages(caplog, 0)
            caplog.clear()
            theirs = _oracle_pkg.clearance.verify_iec60335_compliance(placement, dict(NETS_STR))
            logs_theirs = _log_messages(caplog, 0)
            assert _result_key(ours) == _result_key(theirs)
            assert logs_ours == logs_theirs

    def test_verify_no_overrides_defaults_to_nets_domains(self, caplog):
        placement = _fixture_placements()[6]
        caplog.clear()
        ours = verify_iec60335_compliance(placement, {})
        logs_ours = _log_messages(caplog, 0)
        caplog.clear()
        theirs = _oracle_pkg.clearance.verify_iec60335_compliance(placement, {})
        logs_theirs = _log_messages(caplog, 0)
        assert _result_key(ours) == _result_key(theirs)
        assert logs_ours == logs_theirs

    def test_verify_insulation_type_annotated(self):
        placement = _fixture_placements()[1]  # origin-model violation
        result = verify_iec60335_compliance(placement, dict(NETS_STR))
        for v in result.violations:
            assert v.insulation_type is not None
            assert v.insulation_type in (
                InsulationType.BASIC, InsulationType.REINFORCED, InsulationType.FUNCTIONAL,
            )

    def test_verify_stats_components_and_rows(self):
        placement = _fixture_placements()[1]  # 2 comps (A/B, no pads)
        result = verify_iec60335_compliance(placement, dict(NETS_STR))
        stats = result.stats
        assert stats["components"] == 2
        assert len(stats["rows"]) == 12  # 6 matrix rows x clearance+creepage
        assert all(r["insulation"] in ("basic", "reinforced", "functional") for r in stats["rows"])


class TestFormatClearanceReport:
    def test_report_byte_identical(self):
        placements = _fixture_placements()
        for placement in placements:
            result = check_domain_clearance(
                placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 1000.0
            )
            theirs = _oracle_pkg.clearance.format_clearance_report(result)
            ours = format_clearance_report(result)
            assert ours == theirs

    def test_report_limit_identical(self):
        placements = _fixture_placements()
        result = check_domain_clearance(
            placements[19], VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 1000.0
        )
        assert len(result.violations) >= 2
        for limit in [1, 2, 5, None, 0, -1, -2]:
            theirs = _oracle_pkg.clearance.format_clearance_report(result, limit)
            ours = format_clearance_report(result, limit)
            assert ours == theirs

    def test_report_empty(self):
        placement = _fixture_placements()[2]
        result = check_domain_clearance(placement, VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, 3.0)
        assert result.violations == []
        assert format_clearance_report(result) == "No clearance/creepage violations."

    def test_report_sorted_worst_first(self):
        placement = _fixture_placements()[19]
        result = check_domain_clearance(
            placement, VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, 1000.0
        )
        assert len(result.violations) >= 2
        ours = format_clearance_report(result)
        theirs = _oracle_pkg.clearance.format_clearance_report(result)
        assert ours == theirs
        # The REPORT's data rows are sorted worst-first (shortfall column
        # descending). The raw `result.violations` list is candidate-order by
        # design — only the report sorts — so the assertion reads the report's
        # own shortfall column at its fixed offset (pair:16 bnd:22 ins:11
        # metric:9 meas:8 req:7 short:8).
        rows = [
            r for r in ours.splitlines()
            if not r.startswith(" ") and (" <-> " in r or "(intra)" in r)
        ]
        shortfalls = []
        for r in rows:
            try:
                shortfalls.append(float(r[79:87].strip()))
            except ValueError:
                continue
        assert shortfalls == sorted(shortfalls, reverse=True)


class TestRequirementMatrix:
    def test_matrix_identical(self):
        ours = get_requirement_matrix()
        theirs = _oracle_pkg.clearance.get_requirement_matrix()
        assert set(ours.keys()) == set(theirs.keys())
        for key in theirs:
            assert ours[key] == theirs[key]

    def test_matrix_values_pinned(self):
        matrix = get_requirement_matrix()
        assert matrix[("MAINS", "LV_CONTROL", "basic")] == {
            "min_clearance_mm": 3.0, "min_creepage_mm": 4.0, "design_value_mm": 6.0,
        }
        assert matrix[("MAINS", "LV_CONTROL", "reinforced")] == {
            "min_clearance_mm": 6.0, "min_creepage_mm": 8.0, "design_value_mm": 10.0,
        }
        assert matrix[("LV_CONTROL", "LV_CONTROL", "functional")] == {
            "min_clearance_mm": 0.5, "min_creepage_mm": 1.0, "design_value_mm": 2.0,
        }
