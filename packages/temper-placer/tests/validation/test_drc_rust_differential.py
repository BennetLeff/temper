"""Differential test: KiCad-DRC compute kernels in Rust (temper_drc_rs) vs
the pinned Python implementations (Wave 4, Phase 4 — validation DRC-check
slice).

``temper_placer/validation/drc.py`` moves two pure kernels to
``temper_drc_rs``:
- ``KiCadDRCValidator._parse_single_violation`` → ``temper_drc_rs.parse_drc_violation``
  (the kicad-cli JSON → normalized-violation classification; the DRCViolation
  contract construction and the enum lookup stay in the delegation module)
- ``KiCadDRCValidator.compute_penalty``   → ``temper_drc_rs.compute_drc_penalty``

The kicad-cli subprocess invocation stays Python (an I/O boundary — nothing
to migrate; argued in the module source). The pre-migration implementations
are pinned VERBATIM below (commit ``aece7c372``).

Comparison convention: floats bit-exact via ``float.hex()``; the parse
record's fields are compared as typed tuples.
"""

from __future__ import annotations

import random

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.validation.base import ValidationSeverity
from temper_placer.validation.drc import DRCViolationType, KiCadDRCValidator

# Rust symbols under test — must exist or this file fails to collect (RED).
PARSE_DRC_VIOLATION = _tdrc.parse_drc_violation
COMPUTE_DRC_PENALTY = _tdrc.compute_drc_penalty


# ---------------------------------------------------------------------------
# Oracles — the pre-migration implementations, verbatim (commit aece7c372)
# ---------------------------------------------------------------------------


def _ref_parse_single_violation(item: dict) -> object | None:
    """Pre-migration ``_parse_single_violation`` body, verbatim (the ``self``
    parameter is unused by the oracle body — pinned standalone)."""
    try:
        # Get severity
        severity_str = item.get("severity", "warning").lower()
        if severity_str == "error":
            severity = ValidationSeverity.ERROR
        else:
            severity = ValidationSeverity.WARNING

        # Get violation type
        type_str = item.get("type", "").lower().replace(" ", "_").replace("-", "_")
        try:
            violation_type = DRCViolationType(type_str)
        except ValueError:
            violation_type = DRCViolationType.OTHER

        # Get position
        position = None
        pos_data = item.get("pos", {})
        if pos_data:
            x = pos_data.get("x", 0)
            y = pos_data.get("y", 0)
            position = (float(x), float(y))

        # Get affected items
        affected_items = []
        for affected in item.get("items", []):
            if isinstance(affected, dict):
                ref = affected.get("reference", affected.get("net", ""))
                if ref:
                    affected_items.append(str(ref))
            elif isinstance(affected, str):
                affected_items.append(affected)

        # Build message
        description = item.get("description", "")
        message = description or f"{violation_type.value} violation"

        return {
            "severity": severity,
            "violation_type": violation_type,
            "position": position,
            "affected_items": affected_items,
            "description": description,
            "message": message,
            "code": f"DRC_{violation_type.value.upper()}",
            "rule": item.get("rule", ""),
        }
    except Exception:
        return None


def _ref_compute_penalty(violations: list[tuple[str, str]], severity_weights: dict, violation_weights: dict) -> float:
    """Pre-migration ``compute_penalty`` body, verbatim (self → args; the
    result.success short-circuit lives in the delegating method)."""
    penalty = 0.0
    for (severity_key, type_key) in violations:
        base_weight = severity_weights.get(severity_key, 1.0)
        type_mult = violation_weights.get(type_key, 1.0)
        penalty += base_weight * type_mult
    return penalty


# ---------------------------------------------------------------------------
# Parse differential
# ---------------------------------------------------------------------------


def _normalize_parse_record(rec):
    if rec is None:
        return None
    type_key = rec.get("type")
    if type_key is None:
        type_key = rec["violation_type"].value  # oracle schema (already resolved)
    else:
        # kernel schema: raw normalized string — resolve through the enum
        # exactly like the oracle's ValueError → OTHER path
        try:
            type_key = DRCViolationType(type_key).value
        except ValueError:
            type_key = DRCViolationType.OTHER.value
    severity = rec["severity"]
    if not isinstance(severity, str):
        severity = severity.name  # oracle returns the enum; kernel the string
    return (
        severity,
        type_key,
        None if rec["position"] is None else tuple(float(v).hex() for v in rec["position"]),
        tuple(rec["affected_items"]),
        rec["description"],
        rec["message"],
        rec["code"],
        rec["rule"],
    )


def _parse_both(item):
    ref = _ref_parse_single_violation(item)
    got = PARSE_DRC_VIOLATION(item)
    return ref, got


_DICT_KEY = st.text(min_size=0, max_size=16)
_STR = st.text(min_size=0, max_size=20)


@settings(max_examples=80, deadline=None)
@given(
    st.dictionaries(
        st.sampled_from(["severity", "type", "pos", "items", "rule", "description", "extra"]),
        st.one_of(
            _STR,
            st.none(),
            st.integers(-1000, 1000),
            st.dictionaries(st.text(max_size=8), st.one_of(_STR, st.none(), st.integers(-10, 10))),
            st.lists(st.one_of(_STR, st.dictionaries(st.sampled_from(["reference", "net", "other"]), st.one_of(_STR, st.none())))),
        ),
        max_size=6,
    )
)
def test_parse_differential_random(item):
    ref, got = _parse_both(dict(item))
    if ref is None:
        assert got is None
    else:
        assert got is not None
        assert _normalize_parse_record(got) == _normalize_parse_record(ref)


def test_parse_differential_all_enum_members():
    """Every DRCViolationType member must be classified identically by the
    kernel's embedded catalog and the oracle's enum (pins the catalog copy
    against the live enum — a drift in either fails here)."""
    for member in DRCViolationType:
        item = {"severity": "error", "type": member.value, "items": [], "description": ""}
        ref, got = _parse_both(item)
        assert got is not None
        assert _normalize_parse_record(got) == _normalize_parse_record(ref)
        # the fallback message uses the RESOLVED value (enum member value)
        assert got["message"] == f"{member.value} violation"
        assert got["code"] == f"DRC_{member.value.upper()}"


def test_parse_differential_deterministic():
    cases = [
        # canonical error with position + dict items
        {
            "severity": "error",
            "type": "clearance",
            "pos": {"x": 10.5, "y": -3.25},
            "items": [{"reference": "U1"}, {"net": "GND"}, "R5"],
            "rule": "clearance",
            "description": "Clearance violation",
        },
        # warning, missing type → OTHER, missing description → message fallback
        {"severity": "warning"},
        # weird casing / separators
        {"severity": "ERROR", "type": "Silk Clearance", "items": []},
        {"severity": "error", "type": "hole-clearance"},
        # missing pos → no position
        {"severity": "error", "type": "courtyard_overlap", "items": [{"reference": "C1"}]},
        # items with missing reference/net → skipped
        {"severity": "error", "items": [{"foo": "bar"}, 42, None]},
        # pos present but empty dict → falsy → no position
        {"severity": "error", "pos": {}},
        # severity None → AttributeError → None (oracle except → None)
        {"severity": None},
        # severity missing → defaults to "warning"
        {"type": "track_width"},
        # pos with only y
        {"severity": "error", "pos": {"y": 5}},
        # pos values as strings → float() coercion
        {"severity": "error", "pos": {"x": "1.5", "y": "2.5"}},
        # description empty string → message fallback to type value
        {"severity": "error", "type": "via_dangling", "description": ""},
    ]
    for item in cases:
        ref, got = _parse_both(item)
        if ref is None:
            assert got is None, item
        else:
            assert _normalize_parse_record(got) == _normalize_parse_record(ref), item


# ---------------------------------------------------------------------------
# Penalty differential
# ---------------------------------------------------------------------------

_SEV_WEIGHTS = {"error": 10.0, "warning": 1.0, "exclusion": 0.0}
_TYPE_WEIGHTS = {
    "clearance": 2.0, "hole_clearance": 1.5, "unconnected_items": 1.5,
    "track_width": 1.2, "courtyard_overlap": 1.0, "silk_clearance": 0.5,
}


def _penalty_both(violations, sev_weights, type_weights):
    ref = _ref_compute_penalty(violations, sev_weights, type_weights)
    got = COMPUTE_DRC_PENALTY(violations, sev_weights, type_weights)
    return ref, got


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["error", "warning", "exclusion", "unknown_sev"]),
            st.sampled_from(list(_TYPE_WEIGHTS) + ["unknown_type"]),
        ),
        min_size=0,
        max_size=12,
    )
)
def test_penalty_differential_random(violations):
    ref, got = _penalty_both(violations, _SEV_WEIGHTS, _TYPE_WEIGHTS)
    assert got.hex() == ref.hex()


def test_penalty_differential_deterministic():
    # empty
    assert COMPUTE_DRC_PENALTY([], _SEV_WEIGHTS, _TYPE_WEIGHTS) == 0.0
    # single default-weight unknown type
    assert COMPUTE_DRC_PENALTY([("error", "zzz")], _SEV_WEIGHTS, {}) == 10.0
    # unknown severity → 1.0 default
    assert COMPUTE_DRC_PENALTY([("weird", "clearance")], _SEV_WEIGHTS, _TYPE_WEIGHTS) == 2.0
    # sums in order
    ref, got = _penalty_both(
        [("error", "clearance"), ("warning", "silk_clearance"), ("exclusion", "zzz")],
        _SEV_WEIGHTS, _TYPE_WEIGHTS,
    )
    assert got == ref == 10.0 * 2.0 + 1.0 * 0.5 + 0.0 * 1.0
    # custom weight dicts
    ref, got = _penalty_both([("error", "clearance")], {"error": 3.5}, {"clearance": 0.25})
    assert got == ref == 3.5 * 0.25


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties of the migrated kernels
# ---------------------------------------------------------------------------


def test_prop1_parse_severity_classification():
    """P1: severity "error" (any case) → ERROR; anything else → WARNING."""
    for sev in ("error", "ERROR", "Error"):
        rec = PARSE_DRC_VIOLATION({"severity": sev, "type": "clearance"})
        assert rec["severity"] == "ERROR"
    for sev in ("warning", "info", "", "bogus", None):
        item = {"severity": sev, "type": "clearance"}
        if sev is None:
            assert PARSE_DRC_VIOLATION(item) is None  # AttributeError path
        else:
            rec = PARSE_DRC_VIOLATION(item)
            if rec is not None:
                assert rec["severity"] == "WARNING"


def test_prop2_parse_type_normalization():
    """P2: the type string is lowercased with spaces and hyphens replaced by
    underscores; unknown types resolve to the catalog's OTHER fallback
    (code DRC_OTHER, message "other violation" — the oracle's enum
    ValueError path)."""
    assert PARSE_DRC_VIOLATION({"type": "Silk Clearance"})["type"] == "silk_clearance"
    assert PARSE_DRC_VIOLATION({"type": "hole-clearance"})["type"] == "hole_clearance"
    rec = PARSE_DRC_VIOLATION({"type": "not_a_real_type"})
    assert rec["type"] == "not_a_real_type"
    assert rec["code"] == "DRC_OTHER"
    assert rec["message"] == "other violation"
    rec2 = PARSE_DRC_VIOLATION({})
    assert rec2["type"] == ""
    assert rec2["code"] == "DRC_OTHER"
    assert rec2["message"] == "other violation"
    # message falls back to f"{violation_type.value} violation" — for a known
    # type the value is the normalized type string itself
    assert PARSE_DRC_VIOLATION({"type": "track_width"})["message"] == "track_width violation"


def test_prop3_parse_position_and_items():
    """P3: position is (float(x), float(y)) when pos is truthy; affected
    items collect dict reference/net and bare strings in order."""
    rec = PARSE_DRC_VIOLATION({"pos": {"x": 1, "y": 2}, "items": [{"reference": "U1"}, "R2", {"net": "GND"}]})
    assert rec["position"] == (1.0, 2.0)
    assert rec["affected_items"] == ["U1", "R2", "GND"]
    rec2 = PARSE_DRC_VIOLATION({})
    assert rec2["position"] is None
    assert rec2["affected_items"] == []


def test_prop4_penalty_zero_and_defaults():
    """P4: empty violation list → 0.0; every violation contributes at least
    1.0 (the default weight floor), so penalty ≥ len(violations)."""
    assert COMPUTE_DRC_PENALTY([], {}, {}) == 0.0
    for n in range(1, 6):
        vs = [("unknown_sev", "unknown_type")] * n
        assert COMPUTE_DRC_PENALTY(vs, {}, {}) == float(n)


def test_prop5_penalty_matches_independent_recompute():
    """P5: the kernel result equals an independent recompute of the same
    in-order ``+=`` accumulation (the oracle's summation strategy).

    Summation-strategy trap, honestly bounded: CPython 3.12's ``sum()`` is
    Neumaier-compensated and legitimately disagrees with ``+=`` at the last
    bit for well-conditioned but non-exact sums (measured: 4×0.1+1.0+1.0
    +20.0 → ``0x1.6666666666667p+4`` by ``+=`` vs ``0x1.6666666666666p+4``
    by ``sum()``), so the independent arm below re-implements the oracle's
    ``penalty += base * mult`` exactly rather than calling ``sum()``."""
    rng = random.Random(8)
    for _ in range(100):
        vs = [(rng.choice(["error", "warning"]), rng.choice(list(_TYPE_WEIGHTS))) for _ in range(rng.randint(0, 10))]
        got = COMPUTE_DRC_PENALTY(vs, _SEV_WEIGHTS, _TYPE_WEIGHTS)
        independent = 0.0
        for (s, t) in vs:
            independent += _SEV_WEIGHTS.get(s, 1.0) * _TYPE_WEIGHTS.get(t, 1.0)
        assert got.hex() == independent.hex()


# ---------------------------------------------------------------------------
# Metamorphic relations — three, honestly bounded
# ---------------------------------------------------------------------------


def test_mr1_parse_ignores_unknown_keys():
    """MR1: adding unrelated keys to the violation dict does not change the
    parsed record (the kernel reads a fixed key set, like the oracle's
    ``dict.get`` calls)."""
    base = {"severity": "error", "type": "clearance", "pos": {"x": 1.0, "y": 2.0}, "items": ["U1"]}
    r0 = PARSE_DRC_VIOLATION(base)
    for extra in ({"zzz": 123}, {"severity_extra": "x", "nested": {"a": 1}}, {"items_extra": [1, 2, 3]}):
        r1 = PARSE_DRC_VIOLATION({**base, **extra})
        assert r1 == r0


def test_mr2_penalty_doubled_weights_double_result():
    """MR2: doubling ONE weight dict doubles the penalty bit-exactly when
    every key is KNOWN (multiplication by 2 is exact in IEEE-754).

    Honestly bounded in two ways: (a) keys must be known — unknown keys hit
    the 1.0 DEFAULT, which doubling a dict does NOT scale (a version of
    this test that sampled unknown keys failed on exactly that asymmetry,
    kernel and verbatim oracle agreeing on the non-doubled value); (b) only
    ONE dict is doubled — doubling both would scale a known-known
    contribution by (2s)(2t) = 4st, i.e. quadruple the total, not double
    it."""
    rng = random.Random(9)
    vs = [(rng.choice(list(_SEV_WEIGHTS)), rng.choice(list(_TYPE_WEIGHTS))) for _ in range(8)]
    base = COMPUTE_DRC_PENALTY(vs, _SEV_WEIGHTS, _TYPE_WEIGHTS)
    doubled_sev = {k: 2.0 * v for k, v in _SEV_WEIGHTS.items()}
    d = COMPUTE_DRC_PENALTY(vs, doubled_sev, _TYPE_WEIGHTS)
    assert (2.0 * base).hex() == d.hex()
    # default asymmetry, pinned explicitly: an unknown type contributes the
    # UNDOUBLED default (1.0), not 2.0 — same in kernel and oracle
    ref = _ref_compute_penalty([("error", "zzz")], doubled_sev, {})
    assert COMPUTE_DRC_PENALTY([("error", "zzz")], doubled_sev, {}) == ref == 20.0


def test_mr3_penalty_zero_weights_annihilate():
    """MR3: zeroing all type weights for known types makes the penalty sum to
    zero for known types only (unknown types still hit the 1.0 default)."""
    vs = [("error", "clearance"), ("warning", "track_width"), ("error", "zzz")]
    zeroed = dict.fromkeys(_TYPE_WEIGHTS, 0.0)
    got = COMPUTE_DRC_PENALTY(vs, _SEV_WEIGHTS, zeroed)
    # known types contribute 0; "zzz" hits the 1.0 default → 10.0 * 1.0
    assert got == 10.0


# ---------------------------------------------------------------------------
# Shim-level smoke: the delegating methods still produce contract objects
# ---------------------------------------------------------------------------


def test_shim_parse_and_penalty_roundtrip():
    """The migrated module's methods still construct the contract objects
    (DRCViolation with the enum-resolved violation type) and compute the
    penalty from a real DRCResult."""

    from temper_placer.validation.drc import DRCResult, DRCViolation

    validator = KiCadDRCValidator()
    result = DRCResult(
        success=True,
        violations=[
            DRCViolation(
                severity=ValidationSeverity.ERROR,
                code="DRC_CLEARANCE",
                message="Clearance violation",
                violation_type=DRCViolationType.CLEARANCE,
            ),
            DRCViolation(
                severity=ValidationSeverity.WARNING,
                code="DRC_SILK_CLEARANCE",
                message="Silk",
                violation_type=DRCViolationType.SILK_CLEARANCE,
            ),
        ],
    )
    # default weights: 10.0*2.0 + 1.0*0.5 = 20.5
    assert validator.compute_penalty(result) == 20.5
    # parse path: feed the shim's _parse_single_violation through a patched
    # kicad-cli-free path — call the internal method directly with JSON-like data
    v = validator._parse_single_violation(  # noqa: SLF001
        {"severity": "error", "type": "clearance", "pos": {"x": 1.0, "y": 2.0}, "items": [{"reference": "U1"}]}
    )
    assert v is not None
    assert v.violation_type == DRCViolationType.CLEARANCE
    assert v.code == "DRC_CLEARANCE"
    assert v.position == (1.0, 2.0)
    assert v.affected_items == ["U1"]
    assert v.severity == ValidationSeverity.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
