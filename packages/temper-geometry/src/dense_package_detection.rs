// Wave 4: `temper_placer/router_v6/dense_package_detection.py` — Stage 1.1
// pitch estimation and package-type inference.  The `DensePackage`
// dataclass, the `Component`/`Pin` object access, and the
// `identify_dense_packages` loop stay in Python; the two per-component
// classifiers cross this boundary.
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_spatial_drc_cluster_rust_differential.py`.
//
// ---------------------------------------------------------------------------
// Contract
// ---------------------------------------------------------------------------
// * `_estimate_pitch` regex 1 — `[_-](\d+\.?\d*)\s*MM` on the UPPERCASED
//   footprint: the capture is returned via `float()` (correctly rounded;
//   `str::parse::<f64>` agrees bit-for-bit on the plain decimal captures
//   `\d+(\.\d*)?` this pattern produces).  Regex 2 — `[_P](\d+\.?\d*)
//   (?:[_-]|$)` on the ORIGINAL-case footprint; the first (leftmost) match's
//   capture is parsed; a failed parse falls through to the pin-distance
//   fallback (exactly the reference's `except ValueError: pass`), and a
//   value > 10 is mils (`* 0.0254`).
// * The fallback is the minimum pairwise `((x2-x1)**2 + (y2-y1)**2) ** 0.5`
//   over pins with >= 4 pins, ignoring pairs <= 0.01 mm.  `** 2` and
//   `** 0.5` are CPython float `**` = host libm `pow` (class B1, via
//   `host_math::pow`), NOT `x * x`/`sqrt` and NOT `math.hypot` (Dekker).  A
//   FINITE base whose square overflows raises `OverflowError` exactly like
//   the reference (no try/except around the distance arithmetic), mapped at
//   the pyo3 boundary via `crate::py_errors::overflow_error()`.
// * `_infer_package_type` scans the fixed package-type list in order with
//   substring containment on the uppercased footprint, mapping each hit to
//   the base family ("BGA", "QFN", "TQFP", "SOIC", "SOT") or the literal
//   type, and `"UNKNOWN"` when nothing matches.
// * Footprint strings are ASCII (Python `str.upper()` replicated with
//   `to_ascii_uppercase()`); this is the pinned contract.

use crate::host_math::pow as math_pow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Overflow marker for a finite base whose `** 2` overflows.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KernelError {
    Overflow,
}

fn pow_checked(base: f64, exp: f64) -> Result<f64, KernelError> {
    let r = math_pow(base, exp);
    if r.is_infinite() && base.is_finite() {
        return Err(KernelError::Overflow);
    }
    Ok(r)
}

/// `\d+\.?\d*` starting at `start`: returns the exclusive end index (the
/// greedy maximal capture), or `None` when no digit starts the run.
fn digit_capture_end(b: &[u8], start: usize) -> Option<usize> {
    let mut i = start;
    let mut digits = 0;
    while i < b.len() && b[i].is_ascii_digit() {
        i += 1;
        digits += 1;
    }
    if digits == 0 {
        return None;
    }
    if i < b.len() && b[i] == b'.' {
        i += 1;
        while i < b.len() && b[i].is_ascii_digit() {
            i += 1;
        }
    }
    Some(i)
}

/// Python `\s` — `[ \t\n\r\f\v]`.
fn is_py_whitespace(b: u8) -> bool {
    matches!(b, b' ' | b'\t' | b'\n' | b'\r' | 0x0c | 0x0b)
}

/// Regex 1: `[_-](\d+\.?\d*)\s*MM` on the uppercased footprint.
fn regex_mm_pitch(footprint_upper: &str) -> Option<f64> {
    let b = footprint_upper.as_bytes();
    for i in 0..b.len() {
        if b[i] != b'_' && b[i] != b'-' {
            continue;
        }
        if let Some(end) = digit_capture_end(b, i + 1) {
            let mut j = end;
            while j < b.len() && is_py_whitespace(b[j]) {
                j += 1;
            }
            if j + 1 < b.len() && b[j] == b'M' && b[j + 1] == b'M' {
                let cap = &footprint_upper[i + 1..end];
                if let Ok(v) = cap.parse::<f64>() {
                    return Some(v);
                }
            }
        }
    }
    None
}

/// Regex 2: `[_P](\d+\.?\d*)(?:[_-]|$)` on the original-case footprint.
/// Only the FIRST (leftmost) match is consulted — a failed `float()` on it
/// falls through to the pin fallback, never to a later match.
fn regex_underscore_p_pitch(footprint: &str) -> Option<f64> {
    let b = footprint.as_bytes();
    for i in 0..b.len() {
        if b[i] != b'_' && b[i] != b'P' {
            continue;
        }
        if let Some(end) = digit_capture_end(b, i + 1) {
            let after_ok = end == b.len() || b[end] == b'_' || b[end] == b'-';
            if after_ok {
                let cap = &footprint[i + 1..end];
                if let Ok(pitch) = cap.parse::<f64>() {
                    return Some(pitch);
                }
            }
        }
    }
    None
}

/// `_estimate_pitch`: footprint-name pitch, then pin-position minimum
/// pairwise distance (>= 4 pins), then the 0.65 mm default.  `positions` is
/// a flat `[x0, y0, x1, y1, ...]` array of pin world positions.
pub fn estimate_pitch(footprint: &str, positions: &[f64]) -> Result<f64, KernelError> {
    let footprint_upper = footprint.to_ascii_uppercase();

    if let Some(pitch) = regex_mm_pitch(&footprint_upper) {
        return Ok(pitch);
    }
    if let Some(mut pitch) = regex_underscore_p_pitch(footprint) {
        if pitch > 10.0 {
            pitch *= 0.0254;
        }
        return Ok(pitch);
    }

    let n = positions.len() / 2;
    if n >= 4 {
        let mut min_dist = f64::INFINITY;
        for i in 0..n {
            let (x1, y1) = (positions[2 * i], positions[2 * i + 1]);
            for j in (i + 1)..n {
                let (x2, y2) = (positions[2 * j], positions[2 * j + 1]);
                let dx = x2 - x1;
                let dy = y2 - y1;
                let dist = pow_checked(pow_checked(dx, 2.0)? + pow_checked(dy, 2.0)?, 0.5)?;
                if dist > 0.01 && dist < min_dist {
                    min_dist = dist;
                }
            }
        }
        if min_dist != f64::INFINITY {
            return Ok(min_dist);
        }
    }

    Ok(0.65)
}

const PACKAGE_TYPES: &[&str] = &[
    "BGA", "FBGA", "LFBGA", "TFBGA", "QFN", "DFN", "SON", "TQFP", "LQFP", "QFP", "SOIC", "SOP",
    "SSOP", "TSSOP", "TO-", "SOT-",
];

/// `_infer_package_type`: first list hit wins, mapped to the base family.
pub fn infer_package_type(footprint: &str) -> String {
    let upper = footprint.to_ascii_uppercase();
    for pkg_type in PACKAGE_TYPES {
        if upper.contains(pkg_type) {
            if pkg_type.contains("BGA") {
                return "BGA".to_string();
            } else if pkg_type.contains("QFN") || pkg_type.contains("DFN") || pkg_type.contains("SON")
            {
                return "QFN".to_string();
            } else if pkg_type.contains("QFP") {
                return "TQFP".to_string();
            } else if pkg_type.contains("SOIC") || pkg_type.contains("SOP") {
                return "SOIC".to_string();
            } else if pkg_type.contains("TO-") || pkg_type.contains("SOT-") {
                return "SOT".to_string();
            }
            return pkg_type.to_string();
        }
    }
    "UNKNOWN".to_string()
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn estimate_pitch_py(footprint: String, positions: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| estimate_pitch(&footprint, &positions))
        .map_err(temper_py_bridge::panic_to_err)?
        .map_err(|KernelError::Overflow| crate::py_errors::overflow_error())
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn infer_package_type_py(footprint: String) -> PyResult<String> {
    temper_py_bridge::catch_unwind(|| infer_package_type(&footprint))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(estimate_pitch_py, m)?)?;
    m.add_function(wrap_pyfunction!(infer_package_type_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn estimate_pitch_mm_footprints() {
        assert_eq!(estimate_pitch("QFN-48_0.5mm", &[]), Ok(0.5));
        assert_eq!(estimate_pitch("TQFP-100_0.4mm", &[]), Ok(0.4));
        assert_eq!(estimate_pitch("BGA-256_0.8mm", &[]), Ok(0.8));
        assert_eq!(estimate_pitch("SOIC-16_1.27mm", &[]), Ok(1.27));
    }

    #[cfg_attr(test, test)]
    fn estimate_pitch_bare_and_mils() {
        // regex 2: bare `_50` = 50 mils -> 1.27 mm
        assert_eq!(estimate_pitch("X_50", &[]), Ok(50.0 * 0.0254));
        // regex 2: `_0.5` -> 0.5 mm
        assert_eq!(estimate_pitch("X_0.5", &[]), Ok(0.5));
    }

    #[cfg_attr(test, test)]
    fn estimate_pitch_fallback_and_default() {
        // unknown footprint, 4 pins at 0.5 spacing -> 0.5
        let positions = [0.0, 0.0, 0.0, 0.5, 0.0, 1.0, 0.0, 1.5];
        assert_eq!(estimate_pitch("CUSTOM", &positions), Ok(0.5));
        // fewer than 4 pins -> default 0.65
        assert_eq!(estimate_pitch("CUSTOM", &[0.0, 0.0, 0.0, 0.5]), Ok(0.65));
    }

    #[cfg_attr(test, test)]
    fn estimate_pitch_overflow_raises() {
        // 4 pins required for the distance fallback to run; a finite base
        // whose square overflows raises like the reference.
        assert_eq!(
            estimate_pitch("CUSTOM", &[0.0, 0.0, 1e308, 0.0, 1e308, 1e308, 0.0, 1e308]),
            Err(KernelError::Overflow)
        );
    }

    #[cfg_attr(test, test)]
    fn infer_package_type_cases() {
        assert_eq!(infer_package_type("QFN-48_0.5mm"), "QFN");
        assert_eq!(infer_package_type("BGA-256_0.8mm"), "BGA");
        assert_eq!(infer_package_type("FBGA-484"), "BGA");
        assert_eq!(infer_package_type("TQFP-100"), "TQFP");
        assert_eq!(infer_package_type("LQFP-64"), "TQFP");
        assert_eq!(infer_package_type("SOIC-16"), "SOIC");
        assert_eq!(infer_package_type("SSOP-28"), "SOIC");
        assert_eq!(infer_package_type("SOT-23"), "SOT");
        assert_eq!(infer_package_type("UNKNOWN_PKG"), "UNKNOWN");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("dense_package_detection::tests::estimate_pitch_mm_footprints", estimate_pitch_mm_footprints),
        ("dense_package_detection::tests::estimate_pitch_bare_and_mils", estimate_pitch_bare_and_mils),
        ("dense_package_detection::tests::estimate_pitch_fallback_and_default", estimate_pitch_fallback_and_default),
        ("dense_package_detection::tests::estimate_pitch_overflow_raises", estimate_pitch_overflow_raises),
        ("dense_package_detection::tests::infer_package_type_cases", infer_package_type_cases),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
