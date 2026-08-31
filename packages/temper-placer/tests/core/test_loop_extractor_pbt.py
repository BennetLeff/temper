"""Property-based tests for the Rust loop-extractor classify kernel.

Verification unit (wave-4 discipline contract G4 note): the classify kernel
(``classify_component_py`` in
``temper-rust-router-core/src/loop_extractor/classify_py.rs``), exercised
through the ``temper_rust_router.classify_component_rs`` pyfunction. The
differential suite pins it under one oracle and one corpus
(``test_loop_extractor_rust_differential.py``), and the module-to-property
map is:

- P1, P2, P3, P4, P5  -> ``classify_component_rs`` (category/confidence
  coherence, determinism, capacitor threshold, gate-marker resistors)

Reachability is by construction: every generated example is fed DIRECTLY to
the kernel under test (the property call IS the kernel call), so no
property can be satisfied by a kernel the generated inputs never reach.

Five non-vacuous properties, each with a vacuity guard at the bottom
proving a degenerate kernel violates it via ``hypothesis.inner_test``.

Metamorphic relations (G5), exact -- string classification has no
float-arithmetic transforms to bound:
- M1 case-folding invariance: category/subcategory/confidence are
  invariant under any case change of all four inputs (the ``ref`` field
  tracks the input's own case).
- M2 capacitance-unit equivalence: unit variants of the same value
  (``1000uF``/``1000 UF``/``1000µF``/``1000UF``) classify a C-ref
  identically.
- M3 unrelated-attribute non-interference: an MPN that matches no pattern
  does not change a footprint-driven Q classification.
"""

from __future__ import annotations

import json

import pytest
import temper_rust_router
from hypothesis import given, settings
from hypothesis import strategies as st

# Kernel indirection -- vacuity mutants swap these.
RS_CLASSIFY = temper_rust_router.classify_component_rs

_EXACT_CONFIDENCES = (0.0, 0.7, 0.8, 0.9)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_PREFIX = st.sampled_from(["Q", "U", "C", "D", "R", "X", "G", "BOOT"])
_SUFFIX = st.text(
    alphabet=st.characters(codec="ascii", whitelist_categories=("L", "N", "P")),
    min_size=0,
    max_size=6,
)
_FOOTPRINT = st.sampled_from(
    ["TO-247", "TO-220-3", "TO-263", "R_0805", "C_0603", "CP_Radial_D10", "SOIC-8", "D_SOD-123"]
)
_LARGE_VALUE = st.sampled_from(["1000uF", "220µF", "10000uF", "1mF", "1F", "470uF"])
_MPN = st.sampled_from(
    ["", "IRG4PC50U", "IRF540", "UCC27714", "SI8275", "SS52", "BAT54", "STP75N75", "IKW75N60", "XYZ123"]
)
# Value strings that never trigger the CPython-raise path (no '.' in the
# numeric part => never a malformed numeric), so the structural properties
# hold over the whole generated corpus.
_VALUE_SAFE = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789µΜ ",
    min_size=0,
    max_size=10,
)


def _classify(ref: str, footprint: str, value: str, mpn: str) -> dict:
    payload = json.dumps({"ref": ref, "footprint": footprint, "value": value, "mpn": mpn})
    return json.loads(RS_CLASSIFY(payload))


# ---------------------------------------------------------------------------
# P1 — ref-prefix constrains the category
# ---------------------------------------------------------------------------


@given(_PREFIX, _SUFFIX, _FOOTPRINT, _VALUE_SAFE, _MPN)
@settings(max_examples=100, deadline=60000)
def test_p1_prefix_constrains_category(prefix, suffix, footprint, value, mpn):
    ref = (prefix + suffix).upper()
    out = _classify(ref, footprint, value, mpn)
    if ref.startswith("Q"):
        assert out["category"] in ("power_switch", "other")
    elif ref.startswith("U"):
        assert out["category"] in ("gate_driver", "other")
    elif ref.startswith("C"):
        assert out["category"] == "capacitor"
    elif ref.startswith("D"):
        assert out["category"] == "diode"
    elif ref.startswith("R"):
        assert out["category"] in ("resistor", "other")
    else:
        assert out["category"] == "other"


# ---------------------------------------------------------------------------
# P2 — confidence is drawn from the exact literal set; "other" => 0.0
# ---------------------------------------------------------------------------


@given(_PREFIX, _SUFFIX, _FOOTPRINT, _VALUE_SAFE, _MPN)
@settings(max_examples=100, deadline=60000)
def test_p2_confidence_literal_set_and_other_zero(prefix, suffix, footprint, value, mpn):
    ref = (prefix + suffix).upper()
    out = _classify(ref, footprint, value, mpn)
    assert out["confidence"] in _EXACT_CONFIDENCES
    if out["category"] == "other":
        assert out["confidence"] == 0.0
    else:
        assert out["confidence"] != 0.0


# ---------------------------------------------------------------------------
# P3 — determinism: identical input => identical output, bit-exact
# ---------------------------------------------------------------------------


@given(_PREFIX, _SUFFIX, _FOOTPRINT, _VALUE_SAFE, _MPN)
@settings(max_examples=100, deadline=60000)
def test_p3_deterministic_bit_exact(prefix, suffix, footprint, value, mpn):
    ref = (prefix + suffix).upper()
    a = _classify(ref, footprint, value, mpn)
    b = _classify(ref, footprint, value, mpn)
    assert a["category"] == b["category"]
    assert a["subcategory"] == b["subcategory"]
    assert float(a["confidence"]).hex() == float(b["confidence"]).hex()
    assert a["ref"] == b["ref"] == ref


# ---------------------------------------------------------------------------
# P4 — a C-ref with a value > 100 uF is a bus capacitor
# ---------------------------------------------------------------------------


@given(st.sampled_from(["C"]), _SUFFIX, _FOOTPRINT, _LARGE_VALUE, _VALUE_SAFE)
@settings(max_examples=100, deadline=60000)
def test_p4_large_capacitance_is_bus(prefix, suffix, footprint, value, mpn):
    out = _classify((prefix + suffix).upper(), footprint, value, mpn)
    assert out["category"] == "capacitor"
    assert out["subcategory"] == "bus"
    assert out["confidence"] == 0.8


# ---------------------------------------------------------------------------
# P5 — an R-ref carrying a gate marker is a gate resistor
# ---------------------------------------------------------------------------


@given(st.sampled_from(["R_GATE", "R_G", "R_GR", "RG"]), _SUFFIX, _FOOTPRINT, _VALUE_SAFE, _MPN)
@settings(max_examples=100, deadline=60000)
def test_p5_gate_marker_resistor(prefix, suffix, footprint, value, mpn):
    ref = (prefix + suffix).upper()
    out = _classify(ref, footprint, value, mpn)
    if "GATE" in ref or "G_" in ref or "_G" in ref:
        assert out["category"] == "resistor"
        assert out["subcategory"] == "gate"
        assert out["confidence"] == 0.8


# ---------------------------------------------------------------------------
# Metamorphic relations (G5) -- exact
# ---------------------------------------------------------------------------


def test_m1_case_folding_invariance():
    cases = [
        ("Q1", "TO-247", "", "IRG4PC50U"),
        ("U1", "SOIC-8", "", "UCC27714"),
        ("C1", "C_0603", "1000uF", ""),
        ("R_GATE", "R_0805", "", ""),
        ("X9", "FOO", "abc", "def"),
    ]
    for ref, fp, value, mpn in cases:
        base = _classify(ref, fp, value, mpn)
        folded = _classify(ref.lower(), fp.lower(), value.upper(), mpn.upper())
        assert folded["category"] == base["category"]
        assert folded["subcategory"] == base["subcategory"]
        assert float(folded["confidence"]).hex() == float(base["confidence"]).hex()
        # the ref FIELD tracks the input's own case
        assert folded["ref"] == ref.lower()
        assert base["ref"] == ref


def test_m2_capacitance_unit_equivalence():
    variants = ["1000uF", "1000 UF", "1000µF", "1000μF", "1000UF", " 1000uF"]
    results = [_classify("C1", "CP_Radial", v, "") for v in variants]
    for out in results:
        assert out["category"] == "capacitor"
        assert out["subcategory"] == "bus"
        assert out["confidence"] == 0.8
    assert len({(o["category"], o["subcategory"], float(o["confidence"]).hex()) for o in results}) == 1


def test_m3_unrelated_attribute_non_interference():
    base = _classify("Q7", "TO-247", "", "")
    assert (base["category"], base["subcategory"], base["confidence"]) == (
        "power_switch",
        "unknown",
        0.7,
    )
    for mpn in ["", "XYZ123", "not-a-real-part", "12345"]:
        out = _classify("Q7", "TO-247", "", mpn)
        assert out["category"] == base["category"]
        assert out["subcategory"] == base["subcategory"]
        assert float(out["confidence"]).hex() == float(base["confidence"]).hex()


# ---------------------------------------------------------------------------
# Non-vacuity: each property fails against a mutated (degenerate) kernel
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    global RS_CLASSIFY
    orig_classify = RS_CLASSIFY
    yield
    RS_CLASSIFY = orig_classify


def _mutate_classify(kernel):
    global RS_CLASSIFY
    RS_CLASSIFY = kernel


def _j(ref, footprint, value, mpn):
    return json.dumps({"ref": ref, "footprint": footprint, "value": value, "mpn": mpn})


def test_p1_fails_for_constant_diode_kernel(_restore_kernels):
    _mutate_classify(lambda _s: json.dumps({"ref": "X1", "category": "diode", "subcategory": None, "confidence": 0.7}))
    with pytest.raises(AssertionError):
        test_p1_prefix_constrains_category.hypothesis.inner_test("X", "1", "R_0805", "", "")


def test_p2_fails_for_off_literal_confidence(_restore_kernels):
    _mutate_classify(lambda _s: json.dumps({"ref": "X1", "category": "other", "subcategory": None, "confidence": 0.5}))
    with pytest.raises(AssertionError):
        test_p2_confidence_literal_set_and_other_zero.hypothesis.inner_test("X", "1", "R_0805", "", "")


def test_p3_fails_for_stateful_counter_kernel(_restore_kernels):
    state = {"n": 0}

    def stateful(s):
        state["n"] += 1
        return json.dumps({"ref": "Q1", "category": "power_switch", "subcategory": "igbt", "confidence": state["n"] * 0.1})

    _mutate_classify(stateful)
    with pytest.raises(AssertionError):
        test_p3_deterministic_bit_exact.hypothesis.inner_test("Q", "1", "TO-247", "", "IRG4PC50U")


def test_p4_fails_for_constant_decoupling_kernel(_restore_kernels):
    _mutate_classify(lambda _s: json.dumps({"ref": "C1", "category": "capacitor", "subcategory": "decoupling", "confidence": 0.7}))
    with pytest.raises(AssertionError):
        test_p4_large_capacitance_is_bus.hypothesis.inner_test("C", "1", "CP_Radial", "1000uF", "")


def test_p5_fails_for_constant_other_kernel(_restore_kernels):
    _mutate_classify(lambda _s: json.dumps({"ref": "R_GATE1", "category": "other", "subcategory": None, "confidence": 0.0}))
    with pytest.raises(AssertionError):
        test_p5_gate_marker_resistor.hypothesis.inner_test("R_GATE", "1", "R_0805", "", "")


# sanity: the strategy corpus genuinely discriminates (P4's bus-cap input
# class is reachable with real inputs)
def test_p4_input_class_is_reachable():
    out = _classify("C1", "CP_Radial", "1000uF", "")
    assert out["category"] == "capacitor"
    assert out["subcategory"] == "bus"
