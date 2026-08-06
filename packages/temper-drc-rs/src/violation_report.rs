//! Courtyard/PTH violation-pair report kernels — the Wave 4 Phase 4
//! analysis-surface migration (plan
//! `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`).
//!
//! Python reference: `temper_placer/analysis/_violation_report.py`, pinned
//! VERBATIM in
//! `packages/temper-placer/tests/analysis/_violation_report_py_oracle.py`
//! (commit `c5875adad`).  The pyo3 pyfunctions here must reproduce that
//! implementation bit-identically; the differential test
//! `packages/temper-placer/tests/analysis/test_violation_report_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! Boundary (argued in the delegation shim and in
//! `temper-drc-rs/VERIFICATION.md`): the kiutils parse (`KiBoard.from_file`,
//! footprint position extraction) and the shapely/GEOS overlap-area kernel
//! (`_compute_overlap_area_mm2` — `get_global_polygon`/`intersection`) stay
//! Python-side: kiutils object construction and GEOS intersection are
//! library semantics that cannot be crossed bit-exactly (the guide's
//! "library semantics are not reimplementable" precedent).  The Rust side
//! owns the report-building/shape logic that is genuinely compute:
//!
//! - `build_report_rows` — target-rule filtering (`_TARGET_RULES`),
//!   component-ref shaping (`sorted` for `len >= 2`, copy otherwise), row
//!   dict construction, the overlap-area callback dispatch (courtyards
//!   overlap with exactly two refs), and the stable overlap-descending
//!   sort.
//! - `render_report` — the Markdown renderer, byte-identical to the
//!   oracle: first-appearance rule-section order, CPython fixed-format
//!   floats (`f"{x:.1f}"` / `f"{x:.2f}"`), the `> 0` em-dash gate (NaN and
//!   -0.0 both render the em-dash), and the pipe-escaped 120-char message
//!   truncation.
//!
//! Known, documented deviation (see `VERIFICATION.md`): Python's
//! `list.sort` with a NaN key is not a strict weak order — TimSort's merge
//! moves NaN-keyed elements order-dependently (measured: all 6 orders over
//! 3 elements).  This module's stable sort treats NaN keys as equal to
//! everything (`partial_cmp` -> `Ordering::Equal`), which is deterministic
//! and stable.  The domains agree on every non-NaN key, and the overlap key
//! is never NaN in production (shapely polygon area or `0.0`).

use pyo3::exceptions::{PyKeyError, PyTypeError};
use pyo3::prelude::*;
use pyo3::types::{PyAnyMethods, PyDict, PyList};

const TARGET_RULES: [&str; 2] = ["courtyards_overlap", "pth_inside_courtyard"];

/// One pre-extracted DRC item: (rule, components, (x, y), message).
type ErrorItem = (Option<String>, Vec<String>, (f64, f64), String);

/// Render `v` exactly as CPython's `f"{v:.{precision}f}"` (fixed notation,
/// correctly rounded).  Rust's `{:.precision$}` agrees with CPython's dtoa
/// for every finite double; only the specials diverge (`nan`/`inf` vs
/// `NaN`/`inf`), handled here (verified against a corpus in the
/// differential).
fn py_float_fixed(v: f64, precision: usize) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    if v.is_infinite() {
        return if v.is_sign_negative() { "-inf".to_string() } else { "inf".to_string() };
    }
    format!("{v:.precision$}")
}

#[cfg(test)]
mod py_float_fixed_tests {
    use super::py_float_fixed;

    #[test]
    fn matches_cpython_on_rounding_classes() {
        assert_eq!(py_float_fixed(2.675, 2), "2.67");
        assert_eq!(py_float_fixed(123.456, 1), "123.5");
        assert_eq!(py_float_fixed(-0.05, 1), "-0.1");
        assert_eq!(py_float_fixed(1.005, 2), "1.00");
        assert_eq!(py_float_fixed(-0.0, 1), "-0.0");
        assert_eq!(py_float_fixed(f64::NAN, 2), "nan");
        assert_eq!(py_float_fixed(f64::INFINITY, 1), "inf");
    }
}

/// Build report rows from extracted error tuples.
///
/// `errors` is a list of `(rule, components, (x, y), message)` 4-tuples,
/// pre-extracted Python-side from the DRC item objects (the shim's
/// `getattr(err, "rule", None)` duck-typing lives in the shim).  Rows with
/// a rule outside the target set are dropped.  `overlap_fn`, when given, is
/// called with `(ref_a, ref_b)` for `courtyards_overlap` rows with exactly
/// two refs and its float result becomes the row's `overlap_area_mm2`;
/// without it the field stays `0.0`.  The returned list of dicts is sorted
/// by overlap area descending (stable).
#[pyfunction]
#[pyo3(signature = (errors, overlap_fn=None))]
fn build_report_rows(
    py: Python<'_>,
    errors: Vec<ErrorItem>,
    overlap_fn: Option<Py<PyAny>>,
) -> PyResult<Py<PyList>> {
    let mut rows: Vec<(f64, Bound<'_, PyDict>)> = Vec::with_capacity(errors.len());
    for (rule, components, location, message) in errors {
        let Some(rule) = rule else {
            continue; // getattr(err, "rule", None) -> None: not in target
        };
        if !TARGET_RULES.contains(&rule.as_str()) {
            continue;
        }
        let refs: Vec<String> = if components.len() >= 2 {
            let mut sorted_refs = components.clone();
            sorted_refs.sort();
            sorted_refs
        } else {
            components.clone()
        };
        let overlap: f64 = if rule == "courtyards_overlap" && refs.len() == 2 {
            match &overlap_fn {
                Some(cb) => {
                    let args = (refs[0].clone(), refs[1].clone());
                    let value = cb.bind(py).call1(args)?;
                    value.extract::<f64>()?
                }
                None => 0.0,
            }
        } else {
            0.0
        };
        let row = PyDict::new(py);
        row.set_item("rule", &rule)?;
        row.set_item("components", &components)?;
        row.set_item("refs_sorted", &refs)?;
        row.set_item("location_x", location.0)?;
        row.set_item("location_y", location.1)?;
        row.set_item("message", &message)?;
        row.set_item("overlap_area_mm2", overlap)?;
        row.set_item("n_components", components.len())?;
        rows.push((overlap, row));
    }
    // Python: rows.sort(key=lambda r: r["overlap_area_mm2"], reverse=True)
    // — stable; NaN keys (production-unreachable) sort as Equal (see the
    // module docstring's deviation note).
    rows.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
    let list = PyList::empty(py);
    for (_overlap, row) in rows {
        list.append(row)?;
    }
    Ok(list.unbind())
}

/// Render the report as a Markdown string — a byte-identical port of the
/// oracle's `_render_report`.
///
/// `rows` is a list of dicts with at least the six rendered keys (`rule`,
/// `refs_sorted`, `location_x`, `location_y`, `overlap_area_mm2`,
/// `message`); a missing key raises `KeyError`, matching the oracle's
/// subscript access.
#[pyfunction]
fn render_report(rows: &Bound<'_, PyAny>) -> PyResult<String> {
    let rows = rows.try_iter()?.collect::<PyResult<Vec<Bound<'_, PyAny>>>>()?;

    // by_rule in first-appearance order (mirrors dict insertion order).
    let mut by_rule: Vec<(String, Vec<Bound<'_, PyDict>>)> = Vec::new();
    for row in &rows {
        let dict = row.cast::<PyDict>().map_err(|_| {
            PyTypeError::new_err("render_report: row is not a dict")
        })?;
        let rule: String = match dict.get_item("rule")? {
            Some(v) => v.extract()?,
            None => return Err(PyKeyError::new_err("rule")),
        };
        match by_rule.iter_mut().find(|(r, _)| *r == rule) {
            Some((_, list)) => list.push(dict.clone()),
            None => by_rule.push((rule, vec![dict.clone()])),
        }
    }

    let mut lines: Vec<String> = vec![
        "# Courtyard / PTH Violation-Pair Decision-Support Report".to_string(),
        String::new(),
        "This report lists every `courtyards_overlap` and `pth_inside_courtyard` violation from `kicad-cli pcb drc`.  It does **not** judge which pairs are safe \u{2014} that judgment requires a human PCB-layout reviewer (option C, deferred until a decision lands).".to_string(),
        String::new(),
        "## Violation Pairs".to_string(),
        String::new(),
    ];

    let mut courtyard_count = 0usize;
    let mut pth_count = 0usize;
    for (rule, rule_rows) in &by_rule {
        lines.push(format!("### {rule} ({} violations)", rule_rows.len()));
        lines.push(String::new());
        lines.push(
            "| # | Components | Location (x, y) | Overlap Area (mm^2) | kicad-cli Message |"
                .to_string(),
        );
        lines.push("|---|-----------|----------------|--------------------|------------------|".to_string());
        for (idx, dict) in rule_rows.iter().enumerate() {
            let refs_sorted: Vec<String> = match dict.get_item("refs_sorted")? {
                Some(v) => v.extract()?,
                None => return Err(PyKeyError::new_err("refs_sorted")),
            };
            let location_x: f64 = match dict.get_item("location_x")? {
                Some(v) => v.extract()?,
                None => return Err(PyKeyError::new_err("location_x")),
            };
            let location_y: f64 = match dict.get_item("location_y")? {
                Some(v) => v.extract()?,
                None => return Err(PyKeyError::new_err("location_y")),
            };
            let overlap: f64 = match dict.get_item("overlap_area_mm2")? {
                Some(v) => v.extract()?,
                None => return Err(PyKeyError::new_err("overlap_area_mm2")),
            };
            let message: String = match dict.get_item("message")? {
                Some(v) => v.extract()?,
                None => return Err(PyKeyError::new_err("message")),
            };
            let comps = if refs_sorted.is_empty() {
                "(none)".to_string()
            } else {
                refs_sorted.join(", ")
            };
            let loc = format!(
                "({}, {})",
                py_float_fixed(location_x, 1),
                py_float_fixed(location_y, 1),
            );
            let area = if overlap > 0.0 {
                py_float_fixed(overlap, 2)
            } else {
                "\u{2014}".to_string()
            };
            let escaped: String = message.replace('|', "\\|");
            let msg: String = escaped.chars().take(120).collect();
            lines.push(format!("| {} | {comps} | {loc} | {area} | {msg} |", idx + 1));
        }
        lines.push(String::new());
        if rule == "courtyards_overlap" {
            courtyard_count += rule_rows.len();
        } else if rule == "pth_inside_courtyard" {
            pth_count += rule_rows.len();
        }
    }

    lines.push("## Summary".to_string());
    lines.push(String::new());
    lines.push(format!("- `courtyards_overlap` violations: {courtyard_count}"));
    lines.push(format!("- `pth_inside_courtyard` violations: {pth_count}"));
    lines.push(format!("- Total: {}", rows.len()));
    lines.push(String::new());
    Ok(lines.join("\n"))
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(build_report_rows, m)?)?;
    m.add_function(wrap_pyfunction!(render_report, m)?)?;
    Ok(())
}
