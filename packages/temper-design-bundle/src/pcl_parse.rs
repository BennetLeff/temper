//! PCL parse primitives — Wave 4 Phase 2 (the contracts pivot).
//!
//! Python reference: `temper_placer/pcl/_parse_utils.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/pcl/_parse_utils_py_oracle.py` (commit
//! `5a17025b1`). The differential
//! `packages/temper-placer/tests/pcl/test_parse_utils_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! # Why this file is not "just string parsing"
//!
//! `_parse_distance_with_unit` is an R24 physical-quantity conversion (mil /
//! inch / cm -> mm) wrapped in a hand-rolled scanner whose behaviour depends
//! on three CPython details that a naive Rust port gets wrong:
//!
//! 1. **`str.isdigit()` is not `char::is_ascii_digit()`.** CPython's
//!    `isdigit` is true for every Unicode character with the `Numeric_Type`
//!    digit property — fullwidth `'１'`, Arabic-Indic `'٣'`, and superscript
//!    `'²'` all qualify. `'１０mm'` therefore parses to `10.0` in Python.
//!    Handled by [`py_isdigit`]: ASCII decided locally, non-ASCII delegated
//!    to CPython so the two can never disagree.
//! 2. **`float(s)` accepts Unicode digits and PEP-515 underscores.**
//!    `float('١٠')` is `10.0`; `float('1_0')` is `10.0`. Rust's
//!    `str::parse::<f64>` rejects both. Underscores cannot survive the
//!    scanner (they terminate the number), but Unicode digits can — so
//!    [`py_float`] uses Rust's (correctly-rounded) parser only for pure-ASCII
//!    input and hands anything else to CPython's `float()`.
//! 3. **`str.strip()` strips more than `str::trim()` does, inside ASCII.**
//!    CPython treats `\x1c`–`\x1f` (the C0 file/group/record/unit separators)
//!    as whitespace; Rust's `char::is_whitespace` does not, because they are
//!    not in the Unicode `White_Space` property. `'\x1c5\x1c'` parses to
//!    `5.0` in Python and would fail under `trim()`. Handled by [`py_strip`].
//!
//! Both `str::parse::<f64>` and CPython's `float()` are correctly-rounded
//! shortest-path parsers, so over the character class the scanner can
//! actually produce (ASCII digits, `.`, `-`) they agree on every input by
//! construction — there is no rounding gap to bridge. `test_parse_utils_pbt`
//! fuzzes that equivalence rather than assuming it.
//!
//! # Sign asymmetry (preserved, not fixed)
//!
//! `'-5'` returns `-5.0` but `'-5mm'` raises: the negativity check lives
//! *after* the scanner's `for...else` early return, so it only guards the
//! with-unit path. That is the shipped behaviour and this port reproduces
//! it exactly; see the differential's `test_negative_sign_asymmetry`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyAnyMethods, PyBool, PyFloat, PyInt, PyString};

// ---------------------------------------------------------------------------
// Cached handles into the (unmigrated, still-Python) enum + exception classes.
// ---------------------------------------------------------------------------

/// The PCL enums stay Python `enum.Enum` classes: they are declarative type
/// definitions, and `for t in SomeEnum` / `SomeEnum(value)` are part of the
/// public API that a pyo3 `#[pyclass]` enum cannot reproduce (class-level
/// iteration needs a metaclass hook pyo3 does not expose — the deviation the
/// `priority` migration had to document). Rust therefore returns the very
/// same singletons Python owns, and the differential compares them by
/// identity.
struct PclTypes {
    parse_error: Py<PyAny>,
    tier: Py<PyAny>,
    distance_metric: Py<PyAny>,
    axis: Py<PyAny>,
    board_side: Py<PyAny>,
    edge_type: Py<PyAny>,
}

static PCL_TYPES: PyOnceLock<PclTypes> = PyOnceLock::new();

fn pcl_types(py: Python<'_>) -> PyResult<&'static PclTypes> {
    PCL_TYPES.get_or_try_init(py, || {
        let constraints = py.import("temper_placer.pcl.constraints")?;
        let parse_utils = py.import("temper_placer.pcl._parse_utils")?;
        Ok(PclTypes {
            parse_error: parse_utils.getattr("PCLParseError")?.unbind(),
            tier: constraints.getattr("ConstraintTier")?.unbind(),
            distance_metric: constraints.getattr("DistanceMetric")?.unbind(),
            axis: constraints.getattr("Axis")?.unbind(),
            board_side: constraints.getattr("BoardSide")?.unbind(),
            edge_type: constraints.getattr("EdgeType")?.unbind(),
        })
    })
}

/// Build a `PCLParseError` — the *same* class object `_parse_utils.py`
/// defines, so `except PCLParseError` at every existing call site keeps
/// working and the differential's class-identity check passes.
fn parse_error(py: Python<'_>, msg: String) -> PyErr {
    match pcl_types(py) {
        Ok(t) => match t.parse_error.bind(py).call1((msg,)) {
            Ok(exc) => PyErr::from_value(exc),
            Err(e) => e,
        },
        Err(e) => e,
    }
}

/// Look up `EnumClass.MEMBER_NAME`, returning the live Python singleton.
fn enum_member(py: Python<'_>, class: &Py<PyAny>, name: &str) -> PyResult<Py<PyAny>> {
    Ok(class.bind(py).getattr(name)?.unbind())
}

// ---------------------------------------------------------------------------
// CPython string primitives, replicated for ASCII and delegated beyond it.
// ---------------------------------------------------------------------------

/// True for the ten ASCII digits. Non-ASCII is not this function's business.
fn is_ascii_digit(c: char) -> bool {
    c.is_ascii_digit()
}

/// CPython `str.isdigit()` for a single character.
///
/// ASCII is decided here; every non-ASCII character is handed to CPython so
/// the answer is CPython's by definition rather than by a replicated table
/// that could drift with a Unicode version bump.
fn py_isdigit(py: Python<'_>, c: char) -> PyResult<bool> {
    if c.is_ascii() {
        return Ok(is_ascii_digit(c));
    }
    let s = PyString::new(py, &c.to_string());
    s.call_method0("isdigit")?.extract()
}

/// True for the characters CPython's `str.strip()` removes, restricted to
/// ASCII. Note `\x1c`–`\x1f`: CPython counts them as whitespace, Rust's
/// `char::is_whitespace` does not.
fn is_py_ascii_space(c: char) -> bool {
    matches!(
        c,
        '\t' | '\n' | '\x0b' | '\x0c' | '\r' | '\x1c'..='\x1f' | ' '
    )
}

/// CPython `str.strip()` (no argument).
fn py_strip(py: Python<'_>, s: &str) -> PyResult<String> {
    if s.is_ascii() {
        return Ok(s.trim_matches(|c: char| is_py_ascii_space(c)).to_string());
    }
    PyString::new(py, s).call_method0("strip")?.extract()
}

/// CPython `str.lower()`.
///
/// The ASCII fast path is exact (CPython's ASCII lowering is the identity
/// outside `A`–`Z`). Non-ASCII delegates rather than betting that Rust's
/// `to_lowercase` and CPython's full-casing tables agree on every codepoint.
pub(crate) fn py_lower(py: Python<'_>, s: &str) -> PyResult<String> {
    if s.is_ascii() {
        return Ok(s.to_ascii_lowercase());
    }
    PyString::new(py, s).call_method0("lower")?.extract()
}

/// CPython `str.upper()`. Same reasoning as [`py_lower`]: ASCII locally,
/// everything else delegated. (Used by `pcl_tags::resolve`, which uppercases
/// every component tag on every membership test -- the hottest string
/// operation in the whole PCL layer.)
pub(crate) fn py_upper(py: Python<'_>, s: &str) -> PyResult<String> {
    if s.is_ascii() {
        return Ok(s.to_ascii_uppercase());
    }
    PyString::new(py, s).call_method0("upper")?.extract()
}

/// CPython `float(str)` — Unicode digits, PEP-515 underscores and all.
///
/// For pure-ASCII input Rust's parser is used: both implementations are
/// correctly rounded, so they agree bit-for-bit, and the FFI hop is skipped
/// on the overwhelmingly common path. Anything else is CPython's answer.
fn py_float(py: Python<'_>, s: &str) -> PyResult<f64> {
    if s.is_ascii() {
        // Restrict the Rust fast path to the character class the scanner can
        // hand us. Outside it (e.g. an underscore that reached here through a
        // future edit) CPython decides, so a widened caller cannot silently
        // change meaning.
        if !s.is_empty() && s.chars().all(|c| is_ascii_digit(c) || c == '.' || c == '-') {
            return match s.parse::<f64>() {
                Ok(v) => Ok(v),
                Err(_) => Err(PyValueError::new_err(format!(
                    "could not convert string to float: '{s}'"
                ))),
            };
        }
    }
    py.get_type::<PyFloat>()
        .call1((PyString::new(py, s),))?
        .extract()
}

// ---------------------------------------------------------------------------
// _parse_distance_with_unit
// ---------------------------------------------------------------------------

/// Port of `_parse_distance_with_unit`.
///
/// R24: the returned quantity is millimetres. The three conversion factors
/// are the exact decimal constants the Python used (`0.0254` mm/mil,
/// `25.4` mm/in, `10.0` mm/cm), so each is the identical IEEE-754 double in
/// both languages and `number * factor` is a single correctly-rounded
/// multiply on both sides — no reassociation, no fused multiply-add.
#[pyfunction]
#[pyo3(name = "pcl_parse_distance_with_unit")]
pub fn parse_distance_with_unit(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<f64> {
    // `isinstance(value, (int, float))` — and bool IS an int in Python, so
    // True becomes 1.0 exactly as it did before. `PyInt` covers `PyBool`.
    if value.is_instance_of::<PyInt>() || value.is_instance_of::<PyFloat>() {
        return value.call_method0("__float__")?.extract();
    }

    if !value.is_instance_of::<PyString>() {
        let ty = value.get_type().repr()?;
        return Err(parse_error(
            py,
            format!("Distance must be number or string with unit, got {ty}"),
        ));
    }

    let raw: String = value.extract()?;
    let value = py_strip(py, &raw)?;

    // Scan for the first character that is neither a digit nor '.' nor '-'.
    // Python's `for ... else` runs the else-branch only if no break fired.
    let mut split: Option<(String, String)> = None;
    for (i, ch) in value.char_indices() {
        if !(py_isdigit(py, ch)? || ch == '.' || ch == '-') {
            let number_str = value[..i].to_string();
            let unit_str = py_lower(py, &py_strip(py, &value[i..])?)?;
            split = Some((number_str, unit_str));
            break;
        }
    }

    let Some((number_str, unit_str)) = split else {
        // for...else: no unit suffix. NOTE the two behaviours this branch
        // carries that the with-unit branch does not:
        //   * negatives are ACCEPTED ('-5' -> -5.0),
        //   * a malformed value raises a bare ValueError, NOT PCLParseError
        //     ('' / '.' / '-' / '...' all reach here).
        // Both are shipped behaviour and are asserted by the differential.
        return py_float(py, &value);
    };

    let number = match py_float(py, &number_str) {
        Ok(v) => v,
        Err(_) => {
            // `raise PCLParseError(...) from e` — the message interpolates the
            // stripped *whole* value, not the scanned number_str.
            return Err(parse_error(py, format!("Invalid distance value: {value}")));
        }
    };

    // `number < 0` is false for NaN, matching Python's comparison exactly.
    // (NaN cannot reach here anyway: 'nan' has no leading digit, so the
    // scanner splits at 'n' and float('') fails first.)
    if number < 0.0 {
        return Err(parse_error(
            py,
            format!("Distance cannot be negative: {value}"),
        ));
    }

    match unit_str.as_str() {
        "mm" | "" => Ok(number),
        "mil" => Ok(number * 0.0254),
        "in" => Ok(number * 25.4),
        "cm" => Ok(number * 10.0),
        other => Err(parse_error(py, format!("Unknown distance unit: {other}"))),
    }
}

// ---------------------------------------------------------------------------
// _parse_tier
// ---------------------------------------------------------------------------

/// Port of `_parse_tier`.
///
/// Two preserved quirks: `isinstance(tier_value, int)` is true for `bool`,
/// so `True` -> HARD and `False` -> the *integer* error branch; and that
/// branch's message renders the original object with `str()`, so it reads
/// `"Invalid tier value: False"`, not `"... 0"`.
#[pyfunction]
#[pyo3(name = "pcl_parse_tier")]
pub fn parse_tier(py: Python<'_>, tier_value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let types = pcl_types(py)?;

    if tier_value.is_instance_of::<PyInt>() {
        // `extract::<i64>` fails only for ints outside i64; those are simply
        // not 1/2/3 and fall through to the same error branch.
        let name = match tier_value.extract::<i64>() {
            Ok(1) => Some("HARD"),
            Ok(2) => Some("STRONG"),
            Ok(3) => Some("SOFT"),
            _ => None,
        };
        return match name {
            Some(n) => enum_member(py, &types.tier, n),
            None => Err(parse_error(
                py,
                format!(
                    "Invalid tier value: {}. Must be 1, 2, or 3",
                    tier_value.str()?
                ),
            )),
        };
    }

    if tier_value.is_instance_of::<PyString>() {
        let raw: String = tier_value.extract()?;
        let lowered = py_lower(py, &raw)?;
        let name = match lowered.as_str() {
            "hard" | "1" => Some("HARD"),
            "strong" | "2" => Some("STRONG"),
            "soft" | "3" => Some("SOFT"),
            _ => None,
        };
        return match name {
            Some(n) => enum_member(py, &types.tier, n),
            None => Err(parse_error(
                py,
                format!("Invalid tier: {raw}. Must be HARD/STRONG/SOFT or 1/2/3"),
            )),
        };
    }

    Err(parse_error(
        py,
        format!(
            "Tier must be integer or string, got {}",
            tier_value.get_type().repr()?
        ),
    ))
}

// ---------------------------------------------------------------------------
// _parse_metric / _parse_axis / _parse_board_side / _parse_edge_type
// ---------------------------------------------------------------------------

/// Port of `_parse_metric`.
///
/// The Python scans `for dm in DistanceMetric` and compares `dm.value`; the
/// enum's declaration order is fixed and its values are disjoint, so the
/// scan is equivalent to the match below. Non-`str`, non-`None` input hits
/// `.lower()` and raises `AttributeError` — reproduced by delegating the
/// lowering through CPython's own `str.lower` lookup.
#[pyfunction]
#[pyo3(name = "pcl_parse_metric")]
pub fn parse_metric(py: Python<'_>, metric_value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let types = pcl_types(py)?;
    if metric_value.is_none() {
        return enum_member(py, &types.distance_metric, "EDGE_TO_EDGE");
    }
    // `metric_value.lower().replace("-", "_")` — call through Python so a
    // non-str argument raises the same AttributeError it always did.
    let lowered = metric_value.call_method0("lower")?;
    let normalized: String = lowered.call_method1("replace", ("-", "_"))?.extract()?;

    let name = match normalized.as_str() {
        "edge_to_edge" => Some("EDGE_TO_EDGE"),
        "center_to_center" => Some("CENTER_TO_CENTER"),
        "pin_to_pin" => Some("PIN_TO_PIN"),
        _ => None,
    };
    match name {
        Some(n) => enum_member(py, &types.distance_metric, n),
        None => Err(parse_error(
            py,
            format!(
                "Invalid metric: {}. Valid: edge_to_edge, center_to_center, pin_to_pin",
                metric_value.str()?
            ),
        )),
    }
}

/// Port of `_parse_axis`. `horizontal`/`h` alias to X and `vertical`/`v` to
/// Y *before* the enum-value scan, so those aliases win even though they are
/// not enum values.
#[pyfunction]
#[pyo3(name = "pcl_parse_axis")]
pub fn parse_axis(py: Python<'_>, axis_value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let types = pcl_types(py)?;
    let lowered: String = axis_value.call_method0("lower")?.extract()?;
    let name = match lowered.as_str() {
        "horizontal" | "h" | "x" => Some("X"),
        "vertical" | "v" | "y" => Some("Y"),
        "major" => Some("MAJOR"),
        "minor" => Some("MINOR"),
        _ => None,
    };
    match name {
        Some(n) => enum_member(py, &types.axis, n),
        None => Err(parse_error(
            py,
            format!(
                "Invalid axis: {}. Valid: x, y, major, minor, horizontal, vertical",
                axis_value.str()?
            ),
        )),
    }
}

/// Port of `_parse_board_side`.
#[pyfunction]
#[pyo3(name = "pcl_parse_board_side")]
pub fn parse_board_side(py: Python<'_>, side_value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let types = pcl_types(py)?;
    let lowered: String = side_value.call_method0("lower")?.extract()?;
    let name = match lowered.as_str() {
        "top" => Some("TOP"),
        "bottom" => Some("BOTTOM"),
        "left" => Some("LEFT"),
        "right" => Some("RIGHT"),
        _ => None,
    };
    match name {
        Some(n) => enum_member(py, &types.board_side, n),
        None => Err(parse_error(
            py,
            format!(
                "Invalid side: {}. Valid: top, bottom, left, right",
                side_value.str()?
            ),
        )),
    }
}

/// Port of `_parse_edge_type`.
#[pyfunction]
#[pyo3(name = "pcl_parse_edge_type")]
pub fn parse_edge_type(py: Python<'_>, edge_value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let types = pcl_types(py)?;
    let lowered: String = edge_value.call_method0("lower")?.extract()?;
    let name = match lowered.as_str() {
        "flush" => Some("FLUSH"),
        "near" => Some("NEAR"),
        "overhang" => Some("OVERHANG"),
        _ => None,
    };
    match name {
        Some(n) => enum_member(py, &types.edge_type, n),
        None => Err(parse_error(
            py,
            format!(
                "Invalid edge type: {}. Valid: flush, near, overhang",
                edge_value.str()?
            ),
        )),
    }
}

/// Guard against an accidental `PyBool`-is-not-`PyInt` regression: this is
/// the assumption `parse_tier`/`parse_distance_with_unit` rest on.
#[allow(dead_code)]
fn _bool_is_int_assumption(b: &Bound<'_, PyBool>) -> bool {
    b.is_instance_of::<PyInt>()
}

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_distance_with_unit, module)?)?;
    module.add_function(wrap_pyfunction!(parse_tier, module)?)?;
    module.add_function(wrap_pyfunction!(parse_metric, module)?)?;
    module.add_function(wrap_pyfunction!(parse_axis, module)?)?;
    module.add_function(wrap_pyfunction!(parse_board_side, module)?)?;
    module.add_function(wrap_pyfunction!(parse_edge_type, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn py_ascii_space_matches_cpython_ascii_isspace() {
        // CPython: [c for c in range(128) if chr(c).isspace()] ==
        // [0x9, 0xa, 0xb, 0xc, 0xd, 0x1c, 0x1d, 0x1e, 0x1f, 0x20]
        let expected: Vec<u32> = vec![0x9, 0xa, 0xb, 0xc, 0xd, 0x1c, 0x1d, 0x1e, 0x1f, 0x20];
        let got: Vec<u32> = (0u32..128)
            .filter(|c| char::from_u32(*c).is_some_and(is_py_ascii_space))
            .collect();
        assert_eq!(got, expected);
    }

    #[test]
    fn rust_whitespace_would_have_missed_the_c0_separators() {
        // The regression this guards: `str::trim()` leaves \x1c-\x1f in place.
        for c in ['\x1c', '\x1d', '\x1e', '\x1f'] {
            assert!(is_py_ascii_space(c));
            assert!(!c.is_whitespace(), "Rust considers {c:?} whitespace now");
        }
    }

    #[test]
    fn unit_factors_are_the_exact_decimal_doubles_python_used() {
        // R24: mil/in/cm -> mm. Bit patterns, not approximate equality.
        assert_eq!((0.0254f64).to_bits(), 0x3F9A_0275_2546_0AA6u64);
        assert_eq!((25.4f64).to_bits(), 0x4039_6666_6666_6666u64);
        assert_eq!((10.0f64).to_bits(), 0x4024_0000_0000_0000u64);
        // and the canonical conversions round exactly as Python's do
        assert_eq!(5.0f64 * 0.0254, 0.127);
        assert_eq!(0.1f64 * 25.4, 2.54);
        assert_eq!(2.0f64 * 10.0, 20.0);
    }
}
