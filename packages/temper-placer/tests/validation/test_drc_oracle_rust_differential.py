"""Differential test: drc_oracle kernels in Rust (temper_drc_rs) vs the
pinned Python oracle (Wave 4, Phase 4 — validation DRC-check slice).

``temper_placer/validation/drc_oracle.py`` moves two compute kernels to
``temper_drc_rs``:
- ``_infer_package_type`` (footprint → package-type classification) →
  ``temper_drc_rs.infer_package_type``
- ``DRCOracle._violations_to_run_result`` (grouping + severity
  normalization of Rust-engine violation dicts) → the shared
  ``temper_drc_rs.group_violations`` kernel (also consumed by
  ``drc_runner``; pinned there for the kernel-level PBT).

The K1-schema dict builders (``_build_board_dict``,
``_build_constraints_dict``) stay Python, argued in-source: they are
marshalling over Phase-2 contract objects, and ``_build_board_dict``'s net
ref lists are built from a set comprehension whose iteration order is
hash-randomized per process (the guide's "iteration order over sets" trap —
sorting to stabilise would be a behaviour change no differential could
catch). The oracle is the verbatim pre-migration module
(``_drc_oracle_py_oracle.py``, commit ``aece7c372``).

Comparison convention: floats bit-exact via ``float.hex()``; RunResult
objects canonicalized into typed tuples.
"""

from __future__ import annotations

import random

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation._drc_oracle_py_oracle as _oracle
from temper_placer.validation.drc_oracle import DRCOracle as ShimOracle

# Rust symbol under test — must exist or this file fails to collect (RED).
INFER_PACKAGE_TYPE = _tdrc.infer_package_type
GROUP_VIOLATIONS = _tdrc.group_violations

from temper_placer.validation.drc_oracle import _infer_package_type as shim_infer  # noqa: E402

# ---------------------------------------------------------------------------
# infer_package_type — differential
# ---------------------------------------------------------------------------

_FOOTPRINT = st.text(min_size=0, max_size=40)


@settings(max_examples=120, deadline=None)
@given(_FOOTPRINT)
def test_infer_differential_random(fp):
    assert INFER_PACKAGE_TYPE(fp) == _oracle._infer_package_type(fp)


def test_infer_differential_deterministic():
    cases = [
        (None, "smd"),
        ("", "smd"),
        ("Resistor_SMD:R_0603", "smd"),
        ("Package_SO:SOIC-8", "smd"),
        ("Package_TO_SOT:TO-247", "to247"),
        ("Package_TO_SOT:TO-220", "to220"),
        ("TO247", "to247"),
        ("to-247", "to247"),
        ("BGA-100", "bga"),
        ("QFN-32", "qfn"),
        ("TQFP-64", "qfp"),
        ("QFP-100", "qfp"),
        ("DPAK", "dpak"),
        ("D2PAK", "dpak"),
        ("THT", "tht"),
        ("ThroughHole", "tht"),
        ("PIN_HEADER", "tht"),
        ("DIP-8", "tht"),
        ("CAPACITOR_THT_ELECTRO", "tht"),
        # precedence: tht keywords win over to-247 even when both present
        ("TO-247-THT", "tht"),
        # first-match order: "bga" is checked before "qfn"/"qfp"/"dpak"
        ("QFN_DPAK", "qfn"),
        ("QFP_BGA", "bga"),  # "bga" precedes "qfp" in the keyword order
        ("QFN_TQFP", "qfn"),  # "qfn" precedes "tqfp"
        # substring containment is NOT word-bounded (verbatim semantics)
        ("XYBGAX", "bga"),
        ("XQFNX", "qfn"),
        # case insensitivity
        ("to-247", "to247"),
        ("TqFp", "qfp"),
        ("D2PaK", "dpak"),
        # mixed garbage
        ("   ", "smd"),
        ("Not A Real Footprint!??", "smd"),
    ]
    for fp, expected in cases:
        assert INFER_PACKAGE_TYPE(fp) == expected, fp
        assert shim_infer(fp) == expected, fp


# ---------------------------------------------------------------------------
# group_violations — differential via the DRCOracle._violations_to_run_result
# wrapper (the verbatim oracle staticmethod vs the shim's delegating one)
# ---------------------------------------------------------------------------


def _canon_run_result(rr):
    if rr is None:
        return None
    out = []
    for cr in rr.check_results:
        issues = []
        for i in cr.issues:
            issues.append(
                (
                    i.severity.name,
                    i.code,
                    i.message,
                    i.category,
                    i.check_name,
                    tuple(i.affected_items),
                    None
                    if i.location is None
                    else (None if i.location.x is None else float(i.location.x).hex(),
                          None if i.location.y is None else float(i.location.y).hex(),
                          i.location.layer),
                    tuple(sorted((k, repr(v)) for k, v in i.details.items())),
                )
            )
        out.append((cr.check_name, cr.passed, tuple(issues)))
    return tuple(out)


def _violation_dict(check_name="drc_clearance", severity="ERROR", code="DRC_CLR_001",
                    message="m", category="drc", affected=None, location=None, details=None):
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "category": category,
        "check_name": check_name,
        "affected_items": affected if affected is not None else ["C1"],
        "location": location,
        "details": details if details is not None else {},
    }


def test_group_violations_differential_deterministic():
    vs = [
        _violation_dict("drc_clearance", "ERROR", location={"x": 1.0, "y": 2.0, "layer": "F.Cu"}),
        _violation_dict("drc_clearance", "CRITICAL"),
        _violation_dict("safety_creepage", "WARNING", affected=[]),
        _violation_dict("drc_clearance", "INFO"),
        _violation_dict("erc_power_domain", "BOGUS"),  # unknown → ERROR + failure
        _violation_dict("safety_creepage", "ERROR", location=None, details={"a": 1, "b": [1, 2]}),
        # missing optional keys → defaults
        {"severity": "ERROR", "check_name": "drc_clearance"},
        {"check_name": "zzz"},  # missing severity → "ERROR" default
    ]
    oracle_rr = _oracle.DRCOracle._violations_to_run_result(vs)
    shim_rr = ShimOracle._violations_to_run_result(vs)
    assert _canon_run_result(shim_rr) == _canon_run_result(oracle_rr)
    # sorted group order
    assert [cr.check_name for cr in shim_rr.check_results] == sorted(
        {v.get("check_name", "unknown") for v in vs}
    )


def test_group_violations_differential_random():
    rng = random.Random(77)
    severities = ["INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"]
    for _ in range(200):
        vs = []
        for _ in range(rng.randint(0, 10)):
            has_loc = rng.random() < 0.5
            vs.append(
                _violation_dict(
                    check_name=rng.choice(["drc_clearance", "safety_creepage", "emc_loop_area", "erc_floating"]),
                    severity=rng.choice(severities),
                    affected=[f"C{rng.randint(0, 20)}" for _ in range(rng.randint(0, 3))],
                    location={"x": rng.uniform(-10, 10), "y": rng.uniform(-10, 10), "layer": "F.Cu"}
                    if has_loc else None,
                    details={"k": rng.uniform(-5, 5)} if rng.random() < 0.3 else {},
                )
            )
        oracle_rr = _oracle.DRCOracle._violations_to_run_result(vs)
        shim_rr = ShimOracle._violations_to_run_result(vs)
        assert _canon_run_result(shim_rr) == _canon_run_result(oracle_rr)


def test_group_violations_empty():
    oracle_rr = _oracle.DRCOracle._violations_to_run_result([])
    shim_rr = ShimOracle._violations_to_run_result([])
    assert _canon_run_result(shim_rr) == _canon_run_result(oracle_rr)
    assert shim_rr.check_results == []


def test_group_violations_non_string_check_name_narrowing():
    """Documented narrowing (VERIFICATION.md deviations): the oracle groups by
    any hashable key (``v.get('check_name', 'unknown')`` — an int key works
    there, flowing into the str-typed CheckResult contract unenforced); the
    kernel requires a string and raises PyValueError. Pinned here so the
    narrowing can neither silently widen (a non-string key accepted) nor
    narrow further (a missing key behaving differently)."""
    with pytest.raises(ValueError):
        GROUP_VIOLATIONS([{"check_name": 5, "severity": "ERROR"}])
    with pytest.raises(ValueError):
        GROUP_VIOLATIONS([{"check_name": None, "severity": "ERROR"}])


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties of the migrated kernels
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(st.text(min_size=0, max_size=30))
def test_prop1_infer_returns_known_types(fp):
    """P1: the result is always one of the eight package-type tokens."""
    assert INFER_PACKAGE_TYPE(fp) in ("tht", "to247", "to220", "bga", "qfn", "qfp", "dpak", "smd")


@settings(max_examples=60, deadline=None)
@given(st.text(min_size=0, max_size=30))
def test_prop2_infer_case_insensitive(fp):
    """P2: case does not change the classification (verbatim semantics:
    the footprint is lowercased first)."""
    assert INFER_PACKAGE_TYPE(fp) == INFER_PACKAGE_TYPE(fp.upper()) == INFER_PACKAGE_TYPE(fp.lower())


def test_prop3_infer_none_and_empty_are_smd():
    """P3: None and "" classify as "smd" (the None→""→smd default path)."""
    assert INFER_PACKAGE_TYPE(None) == "smd"
    assert INFER_PACKAGE_TYPE("") == "smd"


def test_prop4_group_sorted_and_partitioned():
    """P4: group_violations returns groups sorted by check_name, each
    violation appears in exactly one group, and each group preserves input
    order within it."""
    vs = [
        _violation_dict("b_check", "ERROR"),
        _violation_dict("a_check", "WARNING"),
        _violation_dict("b_check", "INFO"),
        _violation_dict("a_check", "ERROR"),
        _violation_dict("b_check", "ERROR"),
    ]
    groups = GROUP_VIOLATIONS(vs)
    assert [g[0] for g in groups] == ["a_check", "b_check"]
    assert [r["severity"] for r in groups[0][1]] == ["WARNING", "ERROR"]
    assert [r["severity"] for r in groups[1][1]] == ["ERROR", "INFO", "ERROR"]
    total = sum(len(g[1]) for g in groups)
    assert total == len(vs)


def test_prop5_group_failure_flags():
    """P5: has_failure is True iff the normalized severity is not in
    {INFO, WARNING} (unknown severities fail closed — the oracle maps them
    to Severity.ERROR)."""
    for sev, expected in [("INFO", False), ("WARNING", False), ("ERROR", True),
                          ("CRITICAL", True), ("BOGUS", True), ("", True)]:
        groups = GROUP_VIOLATIONS([_violation_dict(severity=sev)])
        assert groups[0][1][0]["has_failure"] is expected, sev


# ---------------------------------------------------------------------------
# Metamorphic relations — three, honestly bounded
# ---------------------------------------------------------------------------


def test_mr1_infer_substring_addition():
    """MR1: the FIRST matching keyword wins (checked in fixed order) — so a
    footprint whose lowercased form contains a later keyword is unchanged by
    adding an EARLIER-priority keyword to a NON-matching region. Bounded to
    the fixed keyword precedence order, pinned verbatim."""
    assert INFER_PACKAGE_TYPE("QFN-32") == "qfn"
    assert INFER_PACKAGE_TYPE("XQFN-32X") == "qfn"
    # adding "tht" (first priority) changes it; adding "dpak" (last) does not
    assert INFER_PACKAGE_TYPE("QFN-THT") == "tht"
    assert INFER_PACKAGE_TYPE("QFN_DPAK") == "qfn"


def test_mr2_group_permutation_preserves_partition():
    """MR2: permuting the input violation list permutes each group's members
    accordingly — the partition (check_name → member multiset of normalized
    records) is invariant. Bounded to the multiset of records per group."""
    rng = random.Random(78)
    vs = [_violation_dict(rng.choice(["a", "b", "c"]), rng.choice(["ERROR", "WARNING", "INFO"]))
          for _ in range(12)]
    base = GROUP_VIOLATIONS(vs)
    base_map = {name: tuple(sorted((r["severity"], r["code"]) for r in recs)) for name, recs in base}
    for _ in range(5):
        perm = vs[:]
        rng.shuffle(perm)
        groups = GROUP_VIOLATIONS(perm)
        perm_map = {name: tuple(sorted((r["severity"], r["code"]) for r in recs)) for name, recs in groups}
        assert perm_map == base_map


def test_mr3_group_adding_violation_is_monotone():
    """MR3: adding violations to an existing check group preserves the
    earlier groups' records and only grows the affected group (append is
    order-preserving within a group)."""
    base = [
        _violation_dict("x", "ERROR"),
        _violation_dict("y", "WARNING"),
    ]
    extended = base + [_violation_dict("x", "CRITICAL"), _violation_dict("x", "INFO")]
    g_base = {n: [r["severity"] for r in recs] for n, recs in GROUP_VIOLATIONS(base)}
    g_ext = {n: [r["severity"] for r in recs] for n, recs in GROUP_VIOLATIONS(extended)}
    assert g_ext["y"] == g_base["y"]
    assert g_ext["x"][:1] == g_base["x"]
    assert len(g_ext["x"]) == len(g_base["x"]) + 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
