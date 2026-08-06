"""R1a differential: Rust PCL parse primitives vs the pinned Python oracle.

Wave 4, Phase 2 -- the contracts-as-pyo3 pivot. The Rust implementation in
``temper-design-bundle``'s ``pcl_parse.rs`` (exposed as
``temper_design_bundle_python.pcl_parse_*``) must reproduce the pre-migration
``temper_placer/pcl/_parse_utils.py`` bit-identically. The pre-migration
implementation is pinned verbatim as ``_parse_utils_py_oracle.py`` (commit
``5a17025b1``) and every assertion here drives IDENTICAL inputs through both
sides.

Comparison is by **type-carrying signature** (``_pclsig.signature``): floats
as ``float.hex()``, enums by owning-class + member name, exceptions by class
qualname + exact message. There is no tolerance anywhere in this file.

Exception-class note: the oracle module re-declares its own
``PCLParseError``, so oracle and live raise classes with the same
``__qualname__`` from different modules. ``_norm`` erases only the module
component; ``test_live_parse_error_class_identity_is_unchanged`` separately
pins that the *live* class is still the one every ``except PCLParseError`` in
the tree binds against.
"""

from __future__ import annotations

import math

import pytest
import temper_design_bundle_python as _tdb
import tests.pcl._parse_utils_py_oracle as _oracle
from tests.pcl._pclsig import call_signature

# Rust symbols under test -- must exist or this file fails to collect (RED).
RUST_DISTANCE = _tdb.pcl_parse_distance_with_unit
RUST_TIER = _tdb.pcl_parse_tier
RUST_METRIC = _tdb.pcl_parse_metric
RUST_AXIS = _tdb.pcl_parse_axis
RUST_SIDE = _tdb.pcl_parse_board_side
RUST_EDGE = _tdb.pcl_parse_edge_type


def _norm(sig):
    """Drop the module component of a raised exception's class name.

    The oracle is a *copy* of the module, so its ``PCLParseError`` is a
    distinct class object living in ``tests.pcl._parse_utils_py_oracle``.
    Only that difference is normalised -- the qualname and the full message
    text are still compared exactly, so a wrong exception *kind*
    (ValueError vs PCLParseError) or a single changed character in the
    message still fails.
    """
    if sig[0] == "raise":
        return ("raise", sig[2], sig[3])
    return sig


def _both(rust_fn, oracle_fn, value):
    got = _norm(call_signature(rust_fn, value))
    want = _norm(call_signature(oracle_fn, value))
    assert got == want, f"input={value!r}\n  rust  = {got!r}\n  oracle= {want!r}"
    return want


# ---------------------------------------------------------------------------
# _parse_distance_with_unit -- the R24 quantity conversion.
# ---------------------------------------------------------------------------

# Every case below is a behaviour the pre-migration code actually exhibits.
# They were enumerated by running the oracle, not by reading it, so the list
# includes several the docstring does not mention.
DISTANCE_CASES = [
    # --- plain numbers (int/float/bool all satisfy isinstance(x,(int,float)))
    0,
    1,
    -3,
    10**30,
    0.0,
    -0.0,
    2.5,
    -2.5,
    float("inf"),
    float("-inf"),
    float("nan"),
    5e-324,  # smallest positive subnormal
    1.7976931348623157e308,
    True,  # bool IS an int -> 1.0
    False,  # -> 0.0
    # --- unit-less strings (the for...else path)
    "10",
    "10.5",
    "0",
    "-5",  # NEGATIVE IS ACCEPTED here but not with a unit
    "-0",
    "3.",
    ".5",
    "000012",
    "1" * 400,  # overflows to inf in both
    # --- with units
    "10mm",
    "5mil",
    "0.1in",
    "2cm",
    "5MM",
    "5 MIL",
    "  7 mm ",
    "5mm ",
    "5\tmm",
    "0mm",
    "0mil",
    "1mil",
    "3.14159in",
    "1e-3mm" if False else "0.001mm",
    # --- rejected units / malformed
    "5m",
    "1e5",
    "0x10",
    "5 metres",
    "-5mm",
    "-0.1in",
    "+3",
    "inf",
    "nan",
    "1_0",
    "5mm5",
    # --- bare ValueError (NOT PCLParseError) from the for...else float()
    "",
    ".",
    "-",
    "...",
    "--",
    "-.",
    ".-",
    # --- Unicode: str.isdigit() and float() both accept these
    "１０",  # fullwidth '10'
    "１０mm",
    "٣",  # Arabic-Indic 3
    "٣mil",
    "²",  # superscript 2: isdigit() True but float() rejects
    # --- CPython treats \x1c-\x1f as whitespace; Rust's trim() does not
    "\x1c5\x1c",
    "5\x1cmm",
    "\x1f5mm\x1f",
    # --- non-str, non-number
    None,
    [1],
    (1,),
    {"a": 1},
    b"5mm",
]


@pytest.mark.parametrize("value", DISTANCE_CASES, ids=repr)
def test_parse_distance_with_unit_matches_oracle(value):
    _both(RUST_DISTANCE, _oracle._parse_distance_with_unit, value)


def test_negative_sign_asymmetry_is_preserved():
    """'-5' returns -5.0 but '-5mm' raises -- the check is after the early return."""
    assert RUST_DISTANCE("-5") == -5.0
    assert _oracle._parse_distance_with_unit("-5") == -5.0
    for fn in (RUST_DISTANCE, _oracle._parse_distance_with_unit):
        with pytest.raises(Exception, match="Distance cannot be negative"):
            fn("-5mm")


def test_unitless_malformed_raises_bare_valueerror_not_pclparseerror():
    """The for...else path calls float() directly, so its ValueError escapes."""
    for bad in ("", ".", "-", "..."):
        rust = call_signature(RUST_DISTANCE, bad)
        oracle = call_signature(_oracle._parse_distance_with_unit, bad)
        assert rust[0] == "raise" and rust[2] == "ValueError", rust
        assert oracle[0] == "raise" and oracle[2] == "ValueError", oracle
        assert rust[3] == oracle[3]


def test_bool_is_an_int_so_true_parses_as_one_millimetre():
    assert RUST_DISTANCE(True) == 1.0
    assert RUST_DISTANCE(False) == 0.0
    # ...and the result is a float, not a bool -- checked via the signature.
    _both(RUST_DISTANCE, _oracle._parse_distance_with_unit, True)


def test_unicode_digits_are_accepted_exactly_as_cpython_accepts_them():
    """A Rust port using char::is_ascii_digit would reject these."""
    assert RUST_DISTANCE("１０") == 10.0
    assert RUST_DISTANCE("１０mm") == 10.0
    assert RUST_DISTANCE("٣") == 3.0


def test_c0_separators_are_whitespace_to_cpython_and_therefore_to_us():
    """A Rust port using str::trim() would fail these."""
    assert RUST_DISTANCE("\x1c5\x1c") == 5.0
    assert RUST_DISTANCE("5\x1cmm") == 5.0


@pytest.mark.parametrize(
    "text,expected",
    [("5mil", 0.127), ("0.1in", 2.54), ("2cm", 20.0), ("1mil", 0.0254), ("1in", 25.4)],
)
def test_r24_unit_conversions_are_bit_exact(text, expected):
    """R24: the mm results are exact IEEE-754 doubles, compared by hex."""
    assert RUST_DISTANCE(text).hex() == expected.hex()
    assert _oracle._parse_distance_with_unit(text).hex() == expected.hex()


# ---------------------------------------------------------------------------
# _parse_tier
# ---------------------------------------------------------------------------

TIER_CASES = [
    1,
    2,
    3,
    0,
    4,
    -1,
    2**70,
    -(2**70),
    True,  # -> HARD (bool is an int, and True == 1)
    False,  # -> error, and the message says "False", not "0"
    "hard",
    "HARD",
    "Hard",
    "strong",
    "soft",
    "SOFT",
    "1",
    "2",
    "3",
    "0",
    "4",
    "",
    "x",
    " hard",
    1.0,
    None,
    [1],
    b"hard",
]


@pytest.mark.parametrize("value", TIER_CASES, ids=repr)
def test_parse_tier_matches_oracle(value):
    _both(RUST_TIER, _oracle._parse_tier, value)


def test_parse_tier_returns_the_live_enum_singleton():
    """Not a look-alike: the very same object the enum module owns."""
    from temper_placer.pcl.constraints import ConstraintTier

    assert RUST_TIER(1) is ConstraintTier.HARD
    assert RUST_TIER("soft") is ConstraintTier.SOFT


def test_false_reports_itself_as_False_not_as_zero():
    """f-string interpolation uses str(), and str(False) == 'False'."""
    sig = call_signature(RUST_TIER, False)
    assert sig[3] == "Invalid tier value: False. Must be 1, 2, or 3"
    assert sig[3] == call_signature(_oracle._parse_tier, False)[3]


# ---------------------------------------------------------------------------
# _parse_metric / _parse_axis / _parse_board_side / _parse_edge_type
# ---------------------------------------------------------------------------

METRIC_CASES = [
    None,
    "edge_to_edge",
    "EDGE_TO_EDGE",
    "edge-to-edge",
    "center_to_center",
    "CENTER-TO-CENTER",
    "pin_to_pin",
    "pin-to-pin",
    "",
    "bogus",
    "edge to edge",
    "-",
    "_",
    1,
    [1],
]

AXIS_CASES = [
    "x",
    "X",
    "y",
    "Y",
    "major",
    "MAJOR",
    "minor",
    "horizontal",
    "HORIZONTAL",
    "h",
    "H",
    "vertical",
    "v",
    "V",
    "",
    "z",
    "bogus",
    1,
]

SIDE_CASES = ["top", "TOP", "bottom", "left", "RIGHT", "right", "", "front", 1]

EDGE_CASES = ["flush", "FLUSH", "near", "overhang", "OverHang", "", "far", 1]


@pytest.mark.parametrize("value", METRIC_CASES, ids=repr)
def test_parse_metric_matches_oracle(value):
    _both(RUST_METRIC, _oracle._parse_metric, value)


@pytest.mark.parametrize("value", AXIS_CASES, ids=repr)
def test_parse_axis_matches_oracle(value):
    _both(RUST_AXIS, _oracle._parse_axis, value)


@pytest.mark.parametrize("value", SIDE_CASES, ids=repr)
def test_parse_board_side_matches_oracle(value):
    _both(RUST_SIDE, _oracle._parse_board_side, value)


@pytest.mark.parametrize("value", EDGE_CASES, ids=repr)
def test_parse_edge_type_matches_oracle(value):
    _both(RUST_EDGE, _oracle._parse_edge_type, value)


def test_axis_aliases_beat_the_enum_value_scan():
    """'h'/'horizontal' map to X even though neither is an enum value."""
    from temper_placer.pcl.constraints import Axis

    assert RUST_AXIS("horizontal") is Axis.X
    assert RUST_AXIS("h") is Axis.X
    assert RUST_AXIS("vertical") is Axis.Y
    assert RUST_AXIS("v") is Axis.Y


def test_enum_parsers_return_live_singletons():
    from temper_placer.pcl.constraints import Axis, BoardSide, DistanceMetric, EdgeType

    assert RUST_METRIC(None) is DistanceMetric.EDGE_TO_EDGE
    assert RUST_METRIC("pin-to-pin") is DistanceMetric.PIN_TO_PIN
    assert RUST_AXIS("major") is Axis.MAJOR
    assert RUST_SIDE("bottom") is BoardSide.BOTTOM
    assert RUST_EDGE("overhang") is EdgeType.OVERHANG


# ---------------------------------------------------------------------------
# Live-module identity: the public API callers actually bind against.
# ---------------------------------------------------------------------------


def test_live_parse_error_class_identity_is_unchanged():
    """Rust raises the class `_parse_utils` defines, not a look-alike."""
    from temper_placer.pcl import _parse_utils

    with pytest.raises(_parse_utils.PCLParseError):
        _parse_utils._parse_distance_with_unit("5furlongs")
    # ...and it is the same object the rest of the tree imports.
    from temper_placer.pcl.parser import PCLParseError as reexported

    assert reexported is _parse_utils.PCLParseError


def test_live_module_functions_delegate_and_still_match_the_oracle():
    """The public entry points, not just the raw Rust symbols."""
    from temper_placer.pcl import _parse_utils

    for value in DISTANCE_CASES:
        _both(_parse_utils._parse_distance_with_unit, _oracle._parse_distance_with_unit, value)
    for value in TIER_CASES:
        _both(_parse_utils._parse_tier, _oracle._parse_tier, value)
    for value in METRIC_CASES:
        _both(_parse_utils._parse_metric, _oracle._parse_metric, value)
    for value in AXIS_CASES:
        _both(_parse_utils._parse_axis, _oracle._parse_axis, value)
    for value in SIDE_CASES:
        _both(_parse_utils._parse_board_side, _oracle._parse_board_side, value)
    for value in EDGE_CASES:
        _both(_parse_utils._parse_edge_type, _oracle._parse_edge_type, value)


# ---------------------------------------------------------------------------
# Mutation-closing / equivalence evidence.
# ---------------------------------------------------------------------------


def test_M10_the_empty_unit_arm_is_provably_unreachable():
    """M10 (`"mm" | ""` -> `"mm"`) SURVIVED the corpus. This proves it is an
    EQUIVALENT mutant, rather than closing it with a weakened claim.

    Structural argument. `value` is `str.strip()`ped before the scan, so its
    last character is not whitespace. The scan breaks at the first index `i`
    whose character is not a digit, `.` or `-`; `unit_str` is
    `value[i:].strip().lower()`. For `unit_str` to be empty, `value[i:]` must
    be entirely whitespace -- but `value[i:]` is non-empty (i < len) and ends
    with `value[-1]`, which is not whitespace. Contradiction. The `""` arm is
    therefore dead code carried over from the reference, and changing it
    cannot change behaviour.

    Empirical backing: an exhaustive search over every string of length <= 4
    from the alphabet ``" \\t\\x1c.-0123456789ax"`` (16 chars, 69,904 strings)
    finds zero inputs that reach it. That search is re-run below rather than
    quoted, so it cannot rot.
    """
    import itertools

    alphabet = " \t\x1c.-0123456789ax"
    witnesses = []
    for n in range(1, 5):
        for tup in itertools.product(alphabet, repeat=n):
            raw = "".join(tup)
            stripped = raw.strip()
            for i, ch in enumerate(stripped):
                if not (ch.isdigit() or ch in ".-"):
                    if stripped[i:].strip().lower() == "":
                        witnesses.append(raw)
                    break
    assert witnesses == [], f"the empty-unit arm IS reachable: {witnesses[:5]!r}"


def test_the_leading_strip_is_load_bearing():
    """Kills M29 (dropping the leading `str.strip()`)."""
    for text in ("  7 mm ", " 5mm", "5mm ", "\t5mm\n", "\x1c5mm\x1f"):
        _both(RUST_DISTANCE, _oracle._parse_distance_with_unit, text)
    assert RUST_DISTANCE("  7 mm ") == 7.0


def test_cm_conversion_uses_multiplication_not_division():
    """Kills M30 (`x * 10.0` -> `x / 0.1`).

    The two are algebraically equal and agree on most inputs, but not all:
    `x / 0.1` rounds the divisor's binary representation into the result.
    Compared by hex, so a single-ulp difference fails.
    """
    # Integer-valued centimetres never diverge -- the first corpus run used
    # only those and the mutant survived. These four-decimal witnesses do.
    witnesses = [28.3475, 445.3872, 228.7622, 939.1492, 381.2042]
    for v in witnesses:
        assert (v * 10.0) != (v / 0.1), f"{v} is not a witness any more"
        got = RUST_DISTANCE(f"{v}cm")
        want = _oracle._parse_distance_with_unit(f"{v}cm")
        assert got.hex() == want.hex() == (v * 10.0).hex()
        assert got.hex() != (v / 0.1).hex()


def test_nan_and_infinity_pass_through_numeric_inputs_unchanged():
    """Numbers short-circuit before the scanner; NaN keeps its sign bit."""
    for v in (float("nan"), float("-nan"), float("inf"), float("-inf")):
        r = RUST_DISTANCE(v)
        o = _oracle._parse_distance_with_unit(v)
        if math.isnan(v):
            assert math.isnan(r) and math.isnan(o)
            assert math.copysign(1, r) == math.copysign(1, o) == math.copysign(1, v)
        else:
            assert r == o == v
