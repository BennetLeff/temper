"""Differential test: Rust classify/parse kernels vs the pinned Python oracle.

Wave-4 migration of the residual compute in ``core/loop_extractor.py``:
the ``classify_component`` leaf and its ``_parse_capacitance`` helper.
(``auto_extract_loops`` already delegates to the Rust extractor via
``loop_extractor_rs.py``; the Python classify leaf is what remains and it
feeds ``loop_ownership.classify_role``.)

The pre-migration implementations are pinned VERBATIM as the
``_oracle_*`` blocks below, copied from ``core/loop_extractor.py`` as
committed at ``68ea250f`` (origin/main, 2026-08-09). **Do not edit them --
they are the reference.** (R1a)

The Rust side is ``temper_rust_router.classify_component_rs`` /
``temper_rust_router.parse_capacitance_rs`` (kernels in
``temper-rust-router-core/src/loop_extractor/classify_py.rs``). Every
assertion drives IDENTICAL inputs through both sides. Floats are compared
as ``float.hex()``, never a tolerance (wave-4 discipline contract §2 B1-B13
-- this kernel is string classification plus one ``float()``-style
multiply, so the only bit-exactness risk is the CPython-vs-Rust float
parse, pinned here on the full parse edge corpus). Calls that can raise
(malformed capacitance values such as ``"1.2.3F"``) are compared for
error-*type* parity: CPython raises ``ValueError`` from ``float()`` and the
Rust pyfunction raises ``ValueError`` for the same inputs.

Divergence classes recorded in
``packages/temper-rust-router-core/VERIFICATION.md`` (contract §3 --
"reported, not faked"): a numeric part that overflows f64 (CPython
``float()`` saturates to ``inf``, e.g. ``"9"*400``) is excluded from the
raise-parity corpus and handled explicitly; everything else is pinned
bit-exact here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_rust_router
from temper_placer.core.netlist import Component

# ===========================================================================
# _oracle_* blocks -- VERBATIM pre-migration implementations copied from
# core/loop_extractor.py at commit 68ea250f. Do not edit: they are the
# reference the Rust kernel must reproduce bit-identically.
# ===========================================================================


@dataclass
class _OracleComponentClassification:
    """Classification of a component's role in power electronics."""

    ref: str
    category: str  # 'power_switch', 'gate_driver', 'capacitor', 'diode', 'resistor', 'other'
    subcategory: str | None = None  # 'igbt', 'mosfet', 'bootstrap_diode', etc.
    confidence: float = 1.0  # 0.0-1.0


def _oracle_classify_component(component):
    """
    Classify a component based on ref, footprint, and attributes.

    Args:
        component: Component to classify.

    Returns:
        ComponentClassification with detected role.
    """
    ref = component.ref.upper()
    footprint = component.footprint.upper()
    value = component.attributes.get("value", "").upper()
    mpn = component.attributes.get("MPN", "").upper()

    # Power switches (IGBTs, MOSFETs)
    if ref.startswith("Q"):
        # Check for IGBT indicators
        if any(pattern in mpn for pattern in ["IK", "IHW", "IRG", "STGP", "FGA", "IRGP"]):
            return _OracleComponentClassification(
                ref=component.ref,
                category="power_switch",
                subcategory="igbt",
                confidence=0.9,
            )
        # Check for MOSFET indicators
        if any(pattern in mpn for pattern in ["FET", "SI", "IRF", "BSC", "IPP", "STP"]):
            return _OracleComponentClassification(
                ref=component.ref,
                category="power_switch",
                subcategory="mosfet",
                confidence=0.9,
            )
        # Footprint-based detection
        if any(pkg in footprint for pkg in ["TO-247", "TO-220", "TO-263"]):
            return _OracleComponentClassification(
                ref=component.ref,
                category="power_switch",
                subcategory="unknown",
                confidence=0.7,
            )

    # Gate drivers
    if ref.startswith("U") and any(
        pattern in mpn for pattern in ["UCC", "ISO", "SI82", "HCPL", "FOD", "SI827", "ACPL"]
    ):
        return _OracleComponentClassification(
            ref=component.ref,
            category="gate_driver",
            confidence=0.9,
        )

    # Capacitors
    if ref.startswith("C"):
        # Try to extract capacitance value
        cap_value_uf = _oracle_parse_capacitance(value)
        if cap_value_uf and cap_value_uf > 100:
            # Large capacitor - likely bus cap
            return _OracleComponentClassification(
                ref=component.ref,
                category="capacitor",
                subcategory="bus",
                confidence=0.8,
            )
        elif "BOOT" in ref:
            return _OracleComponentClassification(
                ref=component.ref,
                category="capacitor",
                subcategory="bootstrap",
                confidence=0.9,
            )
        else:
            return _OracleComponentClassification(
                ref=component.ref,
                category="capacitor",
                subcategory="decoupling",
                confidence=0.7,
            )

    # Diodes
    if ref.startswith("D"):
        if "BOOT" in ref or "schottky" in mpn.lower():
            return _OracleComponentClassification(
                ref=component.ref,
                category="diode",
                subcategory="bootstrap",
                confidence=0.8,
            )
        return _OracleComponentClassification(
            ref=component.ref,
            category="diode",
            confidence=0.7,
        )

    # Resistors (gate resistors)
    if ref.startswith("R") and ("GATE" in ref or "G_" in ref or "_G" in ref):
        return _OracleComponentClassification(
            ref=component.ref,
            category="resistor",
            subcategory="gate",
            confidence=0.8,
        )

    return _OracleComponentClassification(
        ref=component.ref,
        category="other",
        confidence=0.0,
    )


def _oracle_parse_capacitance(value_str):
    """Parse capacitance string like '100uF', '220µF' to float in uF."""
    if not value_str:
        return None
    # Remove spaces and convert to upper
    value_str = value_str.replace(" ", "").upper()
    # Try to extract numeric part
    import re

    match = re.match(r"([\d.]+)\s*([UPNΜ]?F)?", value_str)
    if not match:
        return None
    numeric = float(match.group(1))
    unit = match.group(2) if match.group(2) else "F"

    # Convert to uF
    multipliers = {
        "PF": 1e-6,
        "NF": 1e-3,
        "UF": 1.0,
        "µF": 1.0,
        "F": 1e6,
    }
    return numeric * multipliers.get(unit, 1.0)


# ===========================================================================
# Rust bridge helpers
# ===========================================================================
# Rust symbols under test -- must exist or this file fails to collect (RED).
RS_CLASSIFY = temper_rust_router.classify_component_rs
RS_PARSE = temper_rust_router.parse_capacitance_rs


def _rs_classify(ref: str, footprint: str, value: str, mpn: str) -> dict:
    payload = json.dumps({"ref": ref, "footprint": footprint, "value": value, "mpn": mpn})
    return json.loads(RS_CLASSIFY(payload))


def _rs_parse(value: str):
    return json.loads(RS_PARSE(value))["uf"]


def _py_classify(ref: str, footprint: str, value: str, mpn: str) -> dict:
    comp = Component(ref, footprint, (0.0, 0.0), attributes={"value": value, "MPN": mpn})
    cls = _oracle_classify_component(comp)
    return {
        "ref": cls.ref,
        "category": cls.category,
        "subcategory": cls.subcategory,
        "confidence": cls.confidence,
    }


# ===========================================================================
# Hand-crafted corpus covering every branch of the oracle
# ===========================================================================

_CLASSIFY_CASES = [
    # (ref, footprint, value, mpn)
    ("Q1", "TO-247", "", ""),  # Q + TO-247 footprint -> power_switch/unknown/0.7
    ("q1", "to-247", "", ""),  # case-folded -> identical classification
    ("Q1", "TO-247", "IRG4PC50U", ""),  # IGBT MPN -> igbt/0.9
    ("Q2", "TO-220", "IRF540", ""),  # MOSFET MPN -> mosfet/0.9
    ("Q3", "TO-263-3", "", ""),  # TO-263 footprint -> unknown/0.7
    ("Q4", "R_0805", "", ""),  # no MPN/footprint match -> other/0.0
    ("Q1", "TO-247", "IKW75N60", ""),  # IGBT pattern "IK"
    ("Q5", "TO-247", "FGA25N120", ""),  # IGBT pattern "FGA"
    ("Q6", "TO-220", "STP75N75", ""),  # MOSFET pattern "STP"
    ("U1", "SOIC-8", "UCC27714", ""),  # gate driver -> 0.9
    ("U2", "SOIC-8", "random", ""),  # U without driver MPN -> other
    ("U3", "SOIC-8", "SI8275", ""),  # driver pattern "SI82"
    ("U4", "QFN-32", "ACPL-337J", ""),  # driver pattern "ACPL"
    ("C1", "CP_Radial", "1000uF", ""),  # bus cap -> bus/0.8
    ("C2", "C_0603", "10nF", ""),  # decoupling/0.7
    ("C3", "C_0603", "", ""),  # no value -> decoupling/0.7
    ("C_BOOT1", "C_0603", "10nF", ""),  # BOOT in ref -> bootstrap/0.9
    ("C4", "C_0603", "0uF", ""),  # 0.0 is falsy -> decoupling
    ("C5", "C_0603", "100uF", ""),  # not >100 -> not bus
    ("C6", "C_0603", "220µF", ""),  # micro sign -> 220uF -> bus
    ("D1", "D_SOD", "", ""),  # plain diode -> subcat None/0.7
    ("D_BOOT1", "D_SOD", "", ""),  # BOOT ref -> bootstrap/0.8
    ("D2", "D_SOD", "SS52 Schottky", ""),  # schottky mpn -> bootstrap/0.8
    ("D3", "D_SOD", "BAT54", ""),  # plain diode
    ("R_GATE1", "R_0805", "", ""),  # GATE in ref -> resistor/gate/0.8
    ("R_G1", "R_0805", "", ""),  # _G in ref -> gate
    ("RG1", "R_0805", "", ""),  # no gate marker -> other
    ("R1", "R_0805", "", ""),  # plain R -> other
    ("X1", "Foo", "", ""),  # unknown -> other/0.0
    ("", "Foo", "", ""),  # empty ref -> other
]

_PARSE_CASES = [
    "",
    "abc",
    "1abc",
    "1000uF",
    "220µF",
    "10nF",
    "100pF",
    "1F",
    "0.1uF",
    "47NF",
    "2.2UF",
    "1M",
    "1MF",
    "1000 UF",
    "1000uF ",
    "\t10uF",
    "10 µF",
    "1.5UFxyz",
    "0.5",
    ".5",
    "5.",
    "10P",
    "10PF",
    "1.5pF",
    "1000μF",
    "1u",
    "1uf",
    "1UF",
    "22 nF",
    "4.7mF",
    "10",
    "10F",
]


def _assert_classification_equal(rs: dict, py: dict) -> None:
    assert rs["ref"] == py["ref"]
    assert rs["category"] == py["category"]
    assert rs["subcategory"] == py["subcategory"]
    assert float(rs["confidence"]).hex() == py["confidence"].hex(), (
        f"confidence diverges: rust={rs['confidence']!r} py={py['confidence']!r}"
    )


def test_classify_hand_crafted_corpus_bit_exact():
    for ref, fp, value, mpn in _CLASSIFY_CASES:
        rs = _rs_classify(ref, fp, value, mpn)
        py = _py_classify(ref, fp, value, mpn)
        _assert_classification_equal(rs, py)


def test_parse_capacitance_hand_crafted_corpus_bit_exact():
    for value in _PARSE_CASES:
        py = _oracle_parse_capacitance(value)
        if py is None:
            assert _rs_parse(value) is None, f"parse {value!r}: rust gave a value"
            continue
        # Guard against accidental float-classification divergences in the
        # corpus itself: the oracle must produce a float here.
        assert isinstance(py, float)
        rs = _rs_parse(value)
        assert rs is not None, f"parse {value!r}: rust returned None"
        assert float(rs).hex() == py.hex(), f"parse {value!r}: {rs!r} vs {py!r}"


def test_parse_capacitance_error_parity():
    """Malformed numeric parts raise ValueError on BOTH sides (CPython
    ``float()`` vs the Rust pyfunction)."""
    malformed = ["1.2.3F", "1.2.3", ".", "...", "1...1", "1.5.5"]
    for value in malformed:
        with pytest.raises(ValueError):
            _oracle_parse_capacitance(value)
        with pytest.raises(ValueError):
            _rs_parse(value)


def test_classify_error_parity_on_malformed_capacitance():
    """A C-ref whose value has a malformed numeric part raises ValueError
    from the oracle; the Rust kernel raises ValueError for the same input."""
    for value in ["1.2.3F", ".", "1...1"]:
        with pytest.raises(ValueError):
            _py_classify("C1", "C_0603", value, "")
        with pytest.raises(ValueError):
            _rs_classify("C1", "C_0603", value, "")


# ===========================================================================
# Randomized differential (hypothesis) -- identical inputs both sides
# ===========================================================================

_PREFIX = st.sampled_from(["Q", "U", "C", "D", "R", "X", "G", "BOOT", ""])
_SUFFIX = st.text(alphabet=st.characters(codec="ascii", whitelist_categories=("L", "N", "P")), min_size=0, max_size=6)
_FOOTPRINT = st.one_of(
    st.sampled_from(["TO-247", "TO-220-3", "TO-263", "R_0805", "C_0603", "CP_Radial_D10", "SOIC-8", "QFN-32", "D_SOD-123", ""]),
    st.text(alphabet=st.characters(codec="ascii"), min_size=0, max_size=12),
)
_NUM = st.sampled_from(["", "1", "10", "100", "101", "0.1", "0", "220", "1e", "1.2"])
_UNIT = st.sampled_from(["", "uF", "µF", "nF", "pF", "F", "UF", "NF", "PF", "M"])
_VALUE = st.one_of(
    st.sampled_from(["", "1000uF", "10nF", "220µF", "1F", "0.5"]),
    st.text(alphabet="0123456789.uUnNpPFµΜ ", min_size=0, max_size=10),
)
_MPN = st.one_of(
    st.sampled_from(["", "IRG4PC50U", "IRF540", "UCC27714", "SI8275", "SS52", "Schottky", "BAT54", "STP75N75", "IKW75N60"]),
    st.text(alphabet=st.characters(codec="ascii", whitelist_categories=("L", "N", "P")), min_size=0, max_size=12),
)


@given(_PREFIX, _SUFFIX, _FOOTPRINT, _VALUE, _MPN)
@settings(max_examples=300, deadline=60000)
def test_classify_randomized_bit_exact(prefix, suffix, footprint, value, mpn):
    ref = prefix + suffix
    try:
        py = _py_classify(ref, footprint, value, mpn)
    except ValueError:
        # malformed capacitance value -> the Rust side must raise too
        with pytest.raises(ValueError):
            _rs_classify(ref, footprint, value, mpn)
        return
    rs = _rs_classify(ref, footprint, value, mpn)
    _assert_classification_equal(rs, py)


@given(_VALUE)
@settings(max_examples=300, deadline=60000)
def test_parse_capacitance_randomized_bit_exact(value):
    try:
        py = _oracle_parse_capacitance(value)
    except ValueError:
        with pytest.raises(ValueError):
            _rs_parse(value)
        return
    if py is None:
        assert _rs_parse(value) is None
        return
    rs = _rs_parse(value)
    assert rs is not None
    assert float(rs).hex() == py.hex(), f"parse {value!r}: {rs!r} vs {py!r}"


def test_overflow_saturates_like_cpython():
    """CPython float() saturates an overflowing digit string to ``inf``; the
    Rust kernel replicates that (recorded divergence class in VERIFICATION.md)."""
    huge = "9" * 400
    assert _oracle_parse_capacitance(huge) == float("inf")
    rs = _rs_parse(huge)
    assert float(rs) == float("inf")
    assert float(rs).hex() == float("inf").hex()
