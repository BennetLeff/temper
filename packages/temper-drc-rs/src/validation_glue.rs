//! Wave 4 — validation-glue kernels (port-inventory entry-5 cluster).
//!
//! Migrates the portable compute of three `temper_placer/validation/`
//! modules (pinned verbatim as `_oracle_*` blocks in
//! `tests/validation/test_validation_glue_rust_differential.py`, commit
//! `5b2a03cfe`):
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `drc_extract_ref` | `_drc_api._extract_ref_from_item_description` |
//! | `drc_extract_net` | `_drc_api._extract_net_from_item_description` |
//! | `drc_parse_violations` | `_drc_api._parse_drc_json` — the per-violation item loop: ref/net extraction, dedup, first-ref-position preference, severity bucket split |
//! | `scheduler_is_final_phase` / `scheduler_get_interval` / `scheduler_should_run` | `scheduler.ValidationScheduler`'s `is_final_phase` / `get_drc_interval` / `get_spice_interval` / `should_run_drc` / `should_run_spice` |
//! | `gate_placement_complete` / `gate_routing_complete` / `gate_production_ready` / `gate_validated` | `validation_gates`'s four gate `check()` decision kernels |
//!
//! ## Home-crate decision
//!
//! temper-drc-rs. All `temper_placer/validation/` compute kernels already
//! live here — `validation.rs` (the Phase-4 DRC-check slice), the
//! drc_fence kernels, `rdl_sum`, and the regression slice's
//! `ratchet_check`/`closure_test`/`physics_oracle` (validation-adjacent,
//! hosted here per the #717/#761 precedent). The gate decision kernels gate
//! on DRC-adjacent metrics (`drc_errors`, `hv_clearance_violations`) and the
//! DRC-report parsing is squarely DRC. temper-orchestration is the wrong
//! home: it hosts pipeline *stages*, not leaf decision kernels, and using it
//! would split one cluster across two crates.
//!
//! ## What stays Python (argued in-source in the modules)
//!
//! - `_drc_api.py`: the kicad-cli subprocess, the `--all-track-errors`
//!   flag, the `run_drc` signature and its env/error handling, and the
//!   `DrcResult`/`DrcError`/`DrcWarning` dataclass shapes — the DRC-ceiling
//!   re-measurement path (`power_pcb_dataset/drc_ceiling.json` +
//!   `scripts/check_measurement_provenance.py`) requires the observable
//!   output to stay byte-identical. The shim marshals the kernel's parsed
//!   records into the unchanged dataclasses.
//! - `scheduler.py`: YAML load/save, `to_dict`/`from_dict`, the config
//!   dataclasses, and the scheduler's mutable run-state sets
//!   (`_drc_epochs`/`_spice_epochs` — process-local state, not a kernel).
//! - `validation_gates.py`: wall-clock `elapsed_ms`, the
//!   `GateResult`/`GateStatus`/`ValidationGatesResult` dataclasses, the
//!   `ValidationGate` ABC, and `check_all_gates`/`check_gate` orchestration.
//!
//! ## CPython `re` semantics the kernels reproduce
//!
//! - `\S`, `\b`, `.` (no-newline), `[^...]` and lazy `\S+?` behave
//!   identically in the `regex` crate and CPython `re` for these patterns
//!   (both Unicode-aware by default); the differential drives adversarial
//!   descriptions to pin the equivalence.
//! - CPython's `$` ALSO matches immediately before a single trailing `\n`
//!   (not `\r\n`); the `regex` crate's `$` matches only at the very end.
//!   The end-anchored ref patterns therefore strip one trailing `\n`
//!   before matching (`strip_trailing_lf`) — pinned by the differential.
//! - The position default `pos.get("x", 0.0)` returns the RAW value when
//!   the key exists (an int stays int) and the `0.0` float when missing;
//!   the kernel returns the raw objects so int-vs-float is preserved.
//!
//! pyo3 panic policy: every `#[pyfunction]` boundary relies on pyo3's
//! default `catch_unwind` (panics surface as `pyo3_runtime.PanicException`,
//! never across the boundary as UB) — R1g. No `unwrap`/`expect` outside
//! `#[cfg(test)]` (crate `[lints.clippy]` denies both).

use std::sync::OnceLock;

use pyo3::exceptions::{PyTypeError, PyZeroDivisionError};
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyAnyMethods, PyDict, PyList, PyModule, PyString, PyTuple};

use regex::Regex;

// ---------------------------------------------------------------------------
// DRC-report line parsing (port of _drc_api.py's parsing half)
// ---------------------------------------------------------------------------

fn footprint_desc_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        #[expect(
            clippy::unwrap_used,
            reason = "compile-time-constant pattern; `ref_patterns_compile` proves it parses"
        )]
        Regex::new(r"^Footprint (\S+)$").unwrap()
    })
}

fn of_ref_desc_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        #[expect(
            clippy::unwrap_used,
            reason = "compile-time-constant pattern; `ref_patterns_compile` proves it parses"
        )]
        Regex::new(r"\bof (\S+?)(?:\s+on\s+\S.*)?$").unwrap()
    })
}

fn net_in_brackets_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        #[expect(
            clippy::unwrap_used,
            reason = "compile-time-constant pattern; `ref_patterns_compile` proves it parses"
        )]
        Regex::new(r"\[([^\]]+)\]").unwrap()
    })
}

/// CPython `re`'s `$` also matches immediately before a single trailing
/// `\n` (never before `\r\n`); the `regex` crate's `$` does not. Strip one
/// trailing `\n` so the end-anchored ref patterns agree with CPython on
/// trailing-newline inputs (pinned by
/// `test_ref_extraction_trailing_newline_semantics`).
fn strip_trailing_lf(description: &str) -> &str {
    description.strip_suffix('\n').unwrap_or(description)
}

/// Port of `_extract_ref_from_item_description` (without the trailing-\n
/// semantics applied — callers that mirror CPython `$` apply
/// [`strip_trailing_lf`] first).
fn extract_ref_impl(description: &str) -> Option<String> {
    if let Some(caps) = footprint_desc_re().captures(description) {
        return Some(caps.get(1)?.as_str().to_string());
    }
    if let Some(caps) = of_ref_desc_re().captures(description) {
        return Some(caps.get(1)?.as_str().to_string());
    }
    None
}

/// Port of `_extract_net_from_item_description`.
fn extract_net_impl(description: &str) -> Option<String> {
    net_in_brackets_re()
        .captures(description)
        .and_then(|c| c.get(1))
        .map(|m| m.as_str().to_string())
}

/// `_extract_ref_from_item_description` — component reference designator
/// from a DRC item's free-text description, or None if the item isn't owned
/// by a single component.
#[pyfunction]
fn drc_extract_ref(description: &str) -> Option<String> {
    extract_ref_impl(strip_trailing_lf(description))
}

/// `_extract_net_from_item_description` — net name from the square-bracket
/// segment of a DRC item description, or None.
#[pyfunction]
fn drc_extract_net(description: &str) -> Option<String> {
    extract_net_impl(description)
}

/// Read a violation/item field with the oracle's `Mapping.get(key, default)`
/// semantics: the RAW value when the key exists (even when it is `None`),
/// the default when missing — type preservation by construction.
fn get_raw_or<'py>(
    py: Python<'py>,
    dict: &Bound<'py, PyDict>,
    key: &str,
    default: &str,
) -> PyResult<Py<PyAny>> {
    match dict.get_item(key)? {
        Some(obj) => Ok(obj.unbind()),
        None => Ok(default.into_pyobject(py)?.into_any().unbind()),
    }
}

/// Read an item's `pos` dict with `item.get("pos", {}).get("x"/"y", 0.0)`
/// semantics — raw x/y objects (int stays int), `0.0` float defaults.
fn item_pos(py: Python<'_>, item: &Bound<'_, PyDict>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    let pos: Bound<'_, PyAny> = match item.get_item("pos")? {
        Some(obj) => obj,
        None => PyDict::new(py).into_any(),
    };
    let pos_dict = pos.cast::<PyDict>()?;
    let x = match pos_dict.get_item("x")? {
        Some(v) => v.unbind(),
        None => 0.0_f64.into_pyobject(py)?.into_any().unbind(),
    };
    let y = match pos_dict.get_item("y")? {
        Some(v) => v.unbind(),
        None => 0.0_f64.into_pyobject(py)?.into_any().unbind(),
    };
    Ok((x, y))
}

/// Is the violation's severity the literal string `"warning"` (the oracle's
/// `severity == "warning"` — a non-string severity, including `None`, is
/// False)?
fn severity_is_warning(py: Python<'_>, severity: &Py<PyAny>) -> bool {
    severity.extract::<String>(py).is_ok_and(|s| s == "warning")
}

/// Build one parsed record dict with the oracle's exact key set.
#[allow(clippy::too_many_arguments)]
fn build_record(
    py: Python<'_>,
    rule: &Py<PyAny>,
    severity: &Py<PyAny>,
    message: &Py<PyAny>,
    location: &(Py<PyAny>, Py<PyAny>),
    components: &[String],
    nets: &[String],
    items: &[Py<PyAny>],
) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("rule", rule.clone_ref(py))?;
    d.set_item("severity", severity.clone_ref(py))?;
    d.set_item("message", message.clone_ref(py))?;

    let loc = PyTuple::new(py, [location.0.clone_ref(py), location.1.clone_ref(py)])?;
    d.set_item("location", loc)?;

    let comps = PyList::empty(py);
    for c in components {
        comps.append(c)?;
    }
    d.set_item("components", comps)?;

    let nets_list = PyList::empty(py);
    for n in nets {
        nets_list.append(n)?;
    }
    d.set_item("nets", nets_list)?;

    let items_list = PyList::empty(py);
    for it in items {
        items_list.append(it.clone_ref(py))?;
    }
    d.set_item("items", items_list)?;

    Ok(d.unbind())
}

/// Port of `_parse_drc_json`'s per-violation loop: split the violations
/// into error/warning RECORDS (dicts with `rule`, `severity`, `message`,
/// `location` (a 2-tuple), `components`, `nets`, `items`), preserving the
/// oracle's ordering, dedup and position-preference rules exactly.
///
/// Returns `(error_records, warning_records)`; the Python shim marshals
/// them into the unchanged `DrcError`/`DrcWarning`/`DrcResult` dataclasses
/// and computes `error_count`/`warning_count` as `len(...)`.
///
/// Documented narrowing: the kernel takes a list of dicts (pyo3 `PyDict`
/// extraction); a non-dict violation raises `TypeError` where the oracle
/// raises `AttributeError` at the first `.get` — both fail closed, and real
/// kicad-cli JSON is always a list of plain dicts.
#[pyfunction]
#[pyo3(signature = (violations))]
fn drc_parse_violations(
    py: Python<'_>,
    violations: Vec<Bound<'_, PyDict>>,
) -> PyResult<(Py<PyList>, Py<PyList>)> {
    let errors = PyList::empty(py);
    let warnings = PyList::empty(py);

    for violation in violations {
        let rule = get_raw_or(py, &violation, "type", "unknown")?;
        let severity = get_raw_or(py, &violation, "severity", "error")?;
        let message = get_raw_or(py, &violation, "description", "")?;

        // `violation.get("items", [])` — missing key is an empty list.
        let items: Vec<Bound<'_, PyDict>> = match violation.get_item("items")? {
            Some(obj) => obj.extract()?,
            None => Vec::new(),
        };

        let mut components: Vec<String> = Vec::new();
        let mut nets: Vec<String> = Vec::new();
        let mut raw_items: Vec<Py<PyAny>> = Vec::new();
        let mut location: Option<(Py<PyAny>, Py<PyAny>)> = None;
        let mut fallback_pos: Option<(Py<PyAny>, Py<PyAny>)> = None;

        for (idx, item) in items.iter().enumerate() {
            let description: Option<Bound<'_, PyAny>> = item.get_item("description")?;
            let description_str: &str = match &description {
                Some(obj) => obj.extract().map_err(|_| {
                    PyTypeError::new_err(
                        "expected string or bytes-like object for item description",
                    )
                })?,
                None => "",
            };
            raw_items.push(match &description {
                Some(obj) => obj.clone().unbind(),
                None => PyString::new(py, "").into_any().unbind(),
            });

            if idx == 0 {
                fallback_pos = Some(item_pos(py, item)?);
            }

            let ref_opt = extract_ref_impl(strip_trailing_lf(description_str));
            if let Some(r) = &ref_opt
                && !components.contains(r)
            {
                components.push(r.clone());
            }
            let net_opt = extract_net_impl(description_str);
            if let Some(n) = &net_opt
                && !nets.contains(n)
            {
                nets.push(n.clone());
            }
            // Prefer the position of the first item that resolves to a real
            // component ref over a board-level feature's item; fall back to
            // the first item's position if no item has an extractable ref.
            if ref_opt.is_some() && location.is_none() {
                location = Some(item_pos(py, item)?);
            }
        }
        if location.is_none() {
            location = fallback_pos;
        }
        // `pos.get("x", 0.0)` / `pos.get("y", 0.0)` default: the float 0.0
        // (f64 -> PyAny conversion is infallible, but the pyo3 API returns
        // PyResult; propagate with `?` rather than unwrapping).
        let zero = 0.0_f64.into_pyobject(py)?.into_any().unbind();
        let location = location.unwrap_or_else(|| (zero.clone_ref(py), zero.clone_ref(py)));

        let record = build_record(
            py,
            &rule,
            &severity,
            &message,
            &location,
            &components,
            &nets,
            &raw_items,
        )?;
        if severity_is_warning(py, &severity) {
            warnings.append(record)?;
        } else {
            errors.append(record)?;
        }
    }

    Ok((errors.into(), warnings.into()))
}

// ---------------------------------------------------------------------------
// Scheduler decision kernels (port of scheduler.ValidationScheduler)
// ---------------------------------------------------------------------------

/// CPython's `%` operator: the result carries the SIGN OF THE DIVISOR
/// (`-7 % 5 == 3`, `7 % -5 == -3`). Rust's `%` truncates toward zero and
/// `rem_euclid` always returns non-negative — neither matches. CPython
/// computes `a - b * (a // b)` with floored division; `py_floor_div` is
/// that floored division (one less than truncation when the signs differ
/// and the truncating remainder is non-zero). Callers guard `b != 0`
/// (CPython raises `ZeroDivisionError`, division would panic).
fn py_floor_div(a: i64, b: i64) -> i64 {
    let q = a / b;
    let r = a % b;
    if r != 0 && (r < 0) != (b < 0) {
        q - 1
    } else {
        q
    }
}

/// CPython's `%` operator (see [`py_floor_div`]).
fn py_mod(a: i64, b: i64) -> i64 {
    a - b * py_floor_div(a, b)
}

/// `ValidationScheduler.is_final_phase`.
#[pyfunction]
fn scheduler_is_final_phase(epoch: i64, total_epochs: i64, final_phase_epochs: i64) -> bool {
    let final_start = total_epochs - final_phase_epochs;
    epoch >= final_start
}

/// `ValidationScheduler.get_drc_interval` / `get_spice_interval`.
#[pyfunction]
fn scheduler_get_interval(
    epoch: i64,
    total_epochs: i64,
    final_phase_epochs: i64,
    interval: i64,
    final_phase_interval: i64,
) -> i64 {
    if scheduler_is_final_phase(epoch, total_epochs, final_phase_epochs) {
        final_phase_interval
    } else {
        interval
    }
}

/// `ValidationScheduler.should_run_drc` / `should_run_spice` — the full
/// decision: the master/kind enabled guards, the already-run guard, the
/// final-phase interval selection, and `epoch % interval == 0 or epoch ==
/// total_epochs - 1`.
///
/// The mutable run-state (`epoch in self._drc_epochs`) is process-local
/// state and stays Python; the shim passes its result as `already_run`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn scheduler_should_run(
    epoch: i64,
    total_epochs: i64,
    final_phase_epochs: i64,
    interval: i64,
    final_phase_interval: i64,
    enabled: bool,
    kind_enabled: bool,
    already_run: bool,
) -> PyResult<bool> {
    if !enabled || !kind_enabled {
        return Ok(false);
    }
    if already_run {
        return Ok(false);
    }
    let interval =
        scheduler_get_interval(epoch, total_epochs, final_phase_epochs, interval, final_phase_interval);
    if interval == 0 {
        // CPython: `epoch % 0` -> ZeroDivisionError: integer division or
        // modulo by zero.
        return Err(PyZeroDivisionError::new_err("integer division or modulo by zero"));
    }
    let should_run = py_mod(epoch, interval) == 0 || epoch == total_epochs - 1;
    Ok(should_run)
}

// ---------------------------------------------------------------------------
// Validation-gate decision kernels (port of validation_gates.py)
// ---------------------------------------------------------------------------

/// `(status, message, failed)` where `status` is `"pass"`/`"fail"`/`"skip"`
/// and `failed` is `[(metric_name, value), ...]` in check order.
type GateVerdict = (String, String, Vec<(String, f64)>);

/// `PlacementCompleteGate.check` decision kernel. Returns
/// `(status, message, failed)` where `failed` is `[(metric_name, value), ...]`
/// in check order; the shim rebuilds `failed_metrics` and computes
/// `elapsed_ms` (wall-clock, stays Python).
#[pyfunction]
fn gate_placement_complete(
    overlap_loss: f64,
    boundary_loss: f64,
    hv_clearance_violations: f64,
    zone_violations: f64,
    convergence_epoch: i64,
) -> PyResult<GateVerdict> {
    let mut failed: Vec<(String, f64)> = Vec::new();
    let checks: [(&str, f64, f64); 4] = [
        ("overlap_loss", overlap_loss, 0.01),
        ("boundary_loss", boundary_loss, 0.01),
        ("hv_clearance_violations", hv_clearance_violations, 0.0),
        ("zone_violations", zone_violations, 0.0),
    ];
    for (name, value, threshold) in checks {
        if value > threshold {
            failed.push((name.to_string(), value));
        }
    }
    if !failed.is_empty() {
        return Ok((
            "fail".to_string(),
            format!("Failed {} constraint(s)", failed.len()),
            failed,
        ));
    }
    if convergence_epoch == 0 {
        return Ok((
            "fail".to_string(),
            "Did not converge".to_string(),
            failed,
        ));
    }
    Ok(("pass".to_string(), "All constraints met".to_string(), failed))
}

/// `RoutingCompleteGate.check` decision kernel.
#[pyfunction]
fn gate_routing_complete(
    routing_completion_percent: f64,
    drc_errors: f64,
) -> PyResult<GateVerdict> {
    if routing_completion_percent < 0.0 {
        return Ok((
            "skip".to_string(),
            "Routing not measured".to_string(),
            Vec::new(),
        ));
    }
    let mut failed: Vec<(String, f64)> = Vec::new();
    if routing_completion_percent < 90.0 {
        failed.push(("routing_completion_percent".to_string(), routing_completion_percent));
    }
    if drc_errors > 0.0 {
        failed.push(("drc_errors".to_string(), drc_errors));
    }
    if failed.is_empty() {
        Ok((
            "pass".to_string(),
            "Routing complete with 0 DRC errors".to_string(),
            failed,
        ))
    } else {
        Ok((
            "fail".to_string(),
            format!("Failed {} requirement(s)", failed.len()),
            failed,
        ))
    }
}

/// `ProductionReadyGate.check` decision kernel — runs the placement gate
/// internally and, on a placement failure, propagates its message and
/// failed metrics verbatim.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn gate_production_ready(
    overlap_loss: f64,
    boundary_loss: f64,
    hv_clearance_violations: f64,
    zone_violations: f64,
    convergence_epoch: i64,
    routing_completion_percent: f64,
    drc_errors: f64,
) -> PyResult<GateVerdict> {
    let (placement_status, placement_message, placement_failed) = gate_placement_complete(
        overlap_loss,
        boundary_loss,
        hv_clearance_violations,
        zone_violations,
        convergence_epoch,
    )?;
    if placement_status != "pass" {
        return Ok((
            "fail".to_string(),
            format!("Placement not ready: {placement_message}"),
            placement_failed,
        ));
    }
    let mut failed: Vec<(String, f64)> = Vec::new();
    if (0.0..90.0).contains(&routing_completion_percent) {
        failed.push(("routing_completion_percent".to_string(), routing_completion_percent));
    }
    if drc_errors > 0.0 {
        failed.push(("drc_errors".to_string(), drc_errors));
    }
    if failed.is_empty() {
        Ok(("pass".to_string(), "Production ready".to_string(), failed))
    } else {
        Ok((
            "fail".to_string(),
            format!("Failed {} requirement(s)", failed.len()),
            failed,
        ))
    }
}

/// `ValidatedGate.check` decision kernel. A `None` input (the oracle's
/// `getattr(metrics, ..., None)` when the metric was never measured) yields
/// SKIP.
#[pyfunction]
fn gate_validated(
    failure_rate: Option<f64>,
    loss_cv: Option<f64>,
) -> PyResult<GateVerdict> {
    let (Some(failure_rate), Some(loss_cv)) = (failure_rate, loss_cv) else {
        return Ok((
            "skip".to_string(),
            "Statistical validation not performed".to_string(),
            Vec::new(),
        ));
    };
    let mut failed: Vec<(String, f64)> = Vec::new();
    if failure_rate > 5.0 {
        failed.push(("failure_rate".to_string(), failure_rate));
    }
    if loss_cv > 0.15 {
        failed.push(("loss_cv".to_string(), loss_cv));
    }
    if failed.is_empty() {
        Ok((
            "pass".to_string(),
            "Statistically validated".to_string(),
            failed,
        ))
    } else {
        Ok((
            "fail".to_string(),
            format!("Failed {} statistical requirement(s)", failed.len()),
            failed,
        ))
    }
}

/// Register the validation-glue kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(drc_extract_ref, m)?)?;
    m.add_function(wrap_pyfunction!(drc_extract_net, m)?)?;
    m.add_function(wrap_pyfunction!(drc_parse_violations, m)?)?;
    m.add_function(wrap_pyfunction!(scheduler_is_final_phase, m)?)?;
    m.add_function(wrap_pyfunction!(scheduler_get_interval, m)?)?;
    m.add_function(wrap_pyfunction!(scheduler_should_run, m)?)?;
    m.add_function(wrap_pyfunction!(gate_placement_complete, m)?)?;
    m.add_function(wrap_pyfunction!(gate_routing_complete, m)?)?;
    m.add_function(wrap_pyfunction!(gate_production_ready, m)?)?;
    m.add_function(wrap_pyfunction!(gate_validated, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use proptest::prelude::*;
    use super::*;

    /// Test-only helper to unwrap a `PyResult<GateVerdict>` without
    /// clippy-flagged `.unwrap()` (crate denies `unwrap_used` on all
    /// targets).
    fn get_verdict(r: PyResult<GateVerdict>) -> GateVerdict {
        match r {
            Ok(v) => v,
            Err(e) => panic!("kernel error: {e}"),
        }
    }

    // ------------------------------------------------------------------
    // Strategies
    // ------------------------------------------------------------------

    /// Non-zero i64, bounded to avoid overflow in `b * q` product.
    fn nonzero_i64() -> impl Strategy<Value = i64> {
        prop_oneof![
            1i64..=1_000_000i64,
            (-1_000_000i64)..=-1i64,
        ]
    }

    /// An i64 in a safe range where `a = b * q + r` won't overflow.
    fn safe_i64() -> impl Strategy<Value = i64> {
        -1_000_000i64..=1_000_000i64
    }

    /// A small i64 in a realistic epoch range.
    fn epoch_like() -> impl Strategy<Value = i64> {
        -100i64..=10000i64
    }

    /// A positive i64 for total_epochs, bounded.
    fn positive() -> impl Strategy<Value = i64> {
        1i64..=10_000i64
    }

    /// A non-negative i64, bounded.
    fn nonneg() -> impl Strategy<Value = i64> {
        0i64..=10_000i64
    }

    /// An f64 that is neither NaN nor infinite.
    fn finite_f64() -> impl Strategy<Value = f64> {
        prop_oneof![
            -1e4f64..1e4f64,
            (-1e-4f64..1e-4f64).prop_map(|x| x),
        ]
    }

    // ------------------------------------------------------------------
    // py_mod / py_floor_div properties
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn prop_py_mod_identity(a in safe_i64(), b in nonzero_i64()) {
            // a == b * floor_div(a, b) + mod(a, b)
            let q = py_floor_div(a, b);
            let r = py_mod(a, b);
            assert_eq!(a, b * q + r,
                "identity a = b*q + r failed: a={a}, b={b}, q={q}, r={r}");
        }

        #[test]
        fn prop_py_mod_magnitude_less_than_divisor(a in safe_i64(), b in nonzero_i64()) {
            let r = py_mod(a, b);
            let abs_r = r.unsigned_abs();
            let abs_b = b.unsigned_abs();
            assert!(abs_r < abs_b,
                "|r| < |b| failed: a={a}, b={b}, r={r}");
        }

        #[test]
        fn prop_py_mod_sign_matches_divisor(a in safe_i64(), b in nonzero_i64()) {
            let r = py_mod(a, b);
            if r == 0 {
                // 0 has no sign
            } else if b > 0 {
                assert!(r >= 0, "r must be >= 0 when b > 0: a={a}, b={b}, r={r}");
            } else {
                assert!(r <= 0, "r must be <= 0 when b < 0: a={a}, b={b}, r={r}");
            }
        }

        #[test]
        fn prop_py_mod_periodicity(a in safe_i64(), b in nonzero_i64(), k in 0i64..100i64) {
            // py_mod repeats with period |b|, but a + k*|b| can overflow.
            // Use checked arithmetic.
            let abs_b = b.unsigned_abs() as i64;
            if let Some(shifted) = a.checked_add(k * abs_b) {
                let (a_check, b_check) = if b < 0 { (shifted, -b) } else { (shifted, b) };
                // Only compare when both are computable without overflow.
                let r_orig = py_mod(a, b);
                // Re-derive for the shifted value safely.
                let r_shift = {
                    let q = py_floor_div(shifted, b);
                    shifted - b * q
                };
                assert_eq!(r_orig, r_shift,
                    "periodicity failed: a={a}, b={b}, k={k}, shifted={shifted}");
                let _ = (a_check, b_check, r_orig, r_shift);
            }
        }

        #[test]
        fn prop_py_floor_div_rounds_down(a in safe_i64(), b in nonzero_i64()) {
            // floor(a / b) <= a / b (as rational) < floor(a / b) + 1
            let q = py_floor_div(a, b);
            let r = py_mod(a, b);
            // a = b * q + r, and |r| < |b|, and sign(r) matches sign(b) or r == 0
            // So 0 <= r/b < 1 (when b > 0), and -1 < r/b <= 0 (when b < 0)
            // In both cases: q <= a/b < q + 1
            if b > 0 {
                assert!(r >= 0);
                // q * b <= a < (q + 1) * b
                // Multiply by b (positive): no overflow if we check product.
                if let (Some(low), Some(high)) =
                    (q.checked_mul(b), (q + 1).checked_mul(b))
                {
                    assert!(low <= a, "floor div rounds down: a={a}, b={b}, q={q}, low={low}");
                    assert!(a < high, "floor div upper bound: a={a}, b={b}, q={q}, high={high}");
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // extract_ref / extract_net regex invariants
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn prop_extract_ref_none_for_non_matching(
            s in "\\PC*"  // any printable ASCII string, including empty
        ) {
            // Patterns that should never extract a ref from a random string
            // that doesn't look like a KiCad item description.
            let result = extract_ref_impl(&s);
            // If it extracts, the string should contain "Footprint " at start
            // or "of " somewhere.
            if let Some(ref r) = result {
                assert!(
                    s.starts_with("Footprint ") || s.contains("of "),
                    "extracted ref '{r}' from unexpected input: '{s}'"
                );
            }
        }

        #[test]
        fn prop_extract_net_none_for_non_matching(
            s in "\\PC*"
        ) {
            let result = extract_net_impl(&s);
            if let Some(ref n) = result {
                assert!(
                    s.contains('[') && s.contains(']'),
                    "extracted net '{n}' from input without brackets: '{s}'"
                );
            }
        }

        #[test]
        fn prop_strip_trailing_lf_idempotent(s in "\\PC*") {
            let once = strip_trailing_lf(&s);
            let twice = strip_trailing_lf(once);
            assert_eq!(once, twice, "strip_trailing_lf not idempotent: s='{s}'");
        }

        #[test]
        fn prop_strip_trailing_lf_only_strips_one_newline(s in "\\PC*") {
            let stripped = strip_trailing_lf(&s);
            if s.ends_with('\n') {
                // The stripped version should NOT end with \n (or only if there are two)
                assert!(
                    !stripped.ends_with('\n') || s.ends_with("\n\n"),
                    "strip_trailing_lf should only strip ONE \\n: s='{s}', stripped='{stripped}'"
                );
            } else {
                assert_eq!(stripped, s, "unmodified when no trailing \\n");
            }
        }
    }

    // ------------------------------------------------------------------
    // Gate decision invariants
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn prop_placement_gate_pass_when_all_zero_and_converged(
            conv in 1i64..10000i64
        ) {
            let (status, msg, failed) =
                get_verdict(gate_placement_complete(0.0, 0.0, 0.0, 0.0, conv));
            assert_eq!(status, "pass");
            assert_eq!(msg, "All constraints met");
            assert!(failed.is_empty());
        }

        #[test]
        fn prop_placement_gate_fail_not_converged(
            ol in finite_f64(), bl in finite_f64(),
            hv in finite_f64(), zv in finite_f64(),
        ) {
            let (status, msg, failed) =
                get_verdict(gate_placement_complete(ol, bl, hv, zv, 0));
            if ol <= 0.01 && bl <= 0.01 && hv <= 0.0 && zv <= 0.0 {
                // All metrics are within thresholds, but not converged.
                // The convergence check dominates.
                assert_eq!(status, "fail");
                assert_eq!(msg, "Did not converge");
                assert!(failed.is_empty());
            } else {
                // At least one metric fails, so the gate should fail for that reason.
                assert_eq!(status, "fail");
                assert!(!failed.is_empty() || msg == "Did not converge");
            }
        }

        #[test]
        fn prop_routing_gate_skip_when_negative(pct in (-1e4f64..0.0f64).prop_filter(
            "exclude NaN and -0.0", |x| x.is_sign_negative() && *x < 0.0
        ), drc in finite_f64()) {
            let (status, msg, failed) = get_verdict(gate_routing_complete(pct, drc));
            assert_eq!(status, "skip");
            assert_eq!(msg, "Routing not measured");
            assert!(failed.is_empty());
        }

        #[test]
        fn prop_validated_gate_skip_when_none(
            fr: Option<f64>, lc: Option<f64>
        ) {
            let (fr_param, lc_param) = (fr, lc);
            let (status, msg, failed) = get_verdict(gate_validated(fr_param, lc_param));
            if fr.is_none() || lc.is_none() {
                assert_eq!(status, "skip");
                assert_eq!(msg, "Statistical validation not performed");
                assert!(failed.is_empty());
            }
        }

        #[test]
        fn prop_gate_status_is_valid_enum(
            ol in finite_f64(), bl in finite_f64(),
            hv in finite_f64(), zv in finite_f64(),
            conv in 0i64..1000i64,
            rp in finite_f64(), de in finite_f64(),
            fr in proptest::option::of(finite_f64()),
            lc in proptest::option::of(finite_f64()),
        ) {
            // Every gate output status is one of the three known values.
            let valid = ["pass", "fail", "skip"];
            let (s, _, _) = get_verdict(gate_placement_complete(ol, bl, hv, zv, conv));
            assert!(valid.contains(&s.as_str()), "placement status: {s}");
            let (s, _, _) = get_verdict(gate_routing_complete(rp, de));
            assert!(valid.contains(&s.as_str()), "routing status: {s}");
            let (s, _, _) = get_verdict(gate_production_ready(ol, bl, hv, zv, conv, rp, de));
            assert!(valid.contains(&s.as_str()), "production status: {s}");
            let (s, _, _) = get_verdict(gate_validated(fr, lc));
            assert!(valid.contains(&s.as_str()), "validated status: {s}");
        }
    }

    // ------------------------------------------------------------------
    // Scheduler invariants
    // ------------------------------------------------------------------

    proptest! {
        #[test]
        fn prop_scheduler_is_final_phase_monotone(
            total in 1i64..10000i64,
            final_epochs in 0i64..5000i64,
            e1 in epoch_like(),
            e2 in epoch_like(),
        ) {
            // If e1 <= e2, then is_final_phase(e1) <= is_final_phase(e2)
            let fp1 = scheduler_is_final_phase(e1, total, final_epochs);
            let fp2 = scheduler_is_final_phase(e2, total, final_epochs);
            if e1 <= e2 {
                assert!(fp1 <= fp2 || (!fp1 && fp2),
                    "final phase not monotone: e1={e1}, e2={e2}, total={total}, fin={final_epochs}");
            }
        }

        #[test]
        fn prop_scheduler_get_interval_returns_one_of_two(
            epoch in epoch_like(),
            total in positive(),
            final_epochs in nonneg(),
            interval in nonzero_i64().prop_map(|x| x.unsigned_abs()),
            fpi in nonzero_i64().prop_map(|x| x.unsigned_abs()),
        ) {
            let got = scheduler_get_interval(epoch, total, final_epochs, interval as i64, fpi as i64);
            assert!(got == interval as i64 || got == fpi as i64,
                "interval must be one of the two configured: got={got}, interval={interval}, fpi={fpi}");
        }

        #[test]
        fn prop_scheduler_should_run_disabled_always_false(
            epoch in epoch_like(),
            total in positive(),
            final_epochs in nonneg(),
            interval in nonzero_i64().prop_map(|x| x.unsigned_abs()),
            fpi in nonzero_i64().prop_map(|x| x.unsigned_abs()),
            enabled: bool,
            kind_enabled: bool,
            already_run: bool,
        ) {
            let result = scheduler_should_run(
                epoch, total, final_epochs,
                interval as i64, fpi as i64,
                enabled, kind_enabled, already_run,
            );
            if let Ok(should) = result
                && (!enabled || !kind_enabled || already_run)
            {
                assert!(!should,
                    "should be false when disabled/already_run: enabled={enabled}, kind={kind_enabled}, already={already_run}");
            }
        }

        #[test]
        fn prop_scheduler_last_epoch_always_runs(
            total in 1i64..10000i64,
            final_epochs in nonneg(),
            interval in nonzero_i64().prop_map(|x| x.unsigned_abs()),
            fpi in nonzero_i64().prop_map(|x| x.unsigned_abs()),
        ) {
            let last = total - 1;
            let result = scheduler_should_run(
                last, total, final_epochs,
                interval as i64, fpi as i64,
                true, true, false,
            );
            match result {
                Ok(should) => assert!(should,
                    "last epoch must always run: total={total}, last={last}, interval={interval}, fpi={fpi}"),
                Err(e) => {
                    // interval might be 0, but that's an error condition — check it.
                    let effective = if last >= total - final_epochs { fpi as i64 } else { interval as i64 };
                    assert!(effective == 0,
                        "only expect error when effective interval is 0: total={total}, effective={effective}");
                    let _ = e;
                }
            }
        }

        #[test]
        fn prop_scheduler_epoch_zero_runs_with_positive_interval(
            total in 1i64..10000i64,
            interval in 1i64..10000i64,
        ) {
            let result = scheduler_should_run(
                0, total, 0,
                interval, interval,
                true, true, false,
            );
            match result {
                Ok(should) => assert!(should,
                    "epoch 0 must run with positive interval: total={total}, interval={interval}"),
                Err(e) => {
                    // interval is positive so this shouldn't error
                    panic!("epoch 0 should not error: {e}");
                }
            }
        }
    }

    #[test]
    fn ref_patterns_compile() {
        // The `#[expect(clippy::unwrap_used)]` regex compilations above are
        // guarded by this test proving the constant patterns parse.
        assert!(footprint_desc_re().is_match("Footprint D3"));
        assert!(of_ref_desc_re().is_match("of C1"));
        assert!(net_in_brackets_re().is_match("Via [GND]"));
    }

    #[test]
    fn extract_ref_matches_cpython_shapes() {
        assert_eq!(extract_ref_impl("Footprint D3"), Some("D3".to_string()));
        assert_eq!(
            extract_ref_impl("Reference field of C1"),
            Some("C1".to_string())
        );
        assert_eq!(
            extract_ref_impl("Segment of C16 on F.Silkscreen"),
            Some("C16".to_string())
        );
        assert_eq!(
            extract_ref_impl("Pad 13 [power_in.ntc-no] of K1 on F.Cu"),
            Some("K1".to_string())
        );
        assert_eq!(extract_ref_impl("PTH pad 1 [+15V] of R1"), Some("R1".to_string()));
        // Vias / board-level features carry no single-owner ref.
        assert_eq!(extract_ref_impl("Via [bias] on F.Cu - B.Cu"), None);
        assert_eq!(extract_ref_impl("Polygon on Edge.Cuts"), None);
    }

    #[test]
    fn extract_ref_trailing_newline_matches_cpython_dollar() {
        // CPython `$` matches before a single trailing `\n`.
        assert_eq!(extract_ref_impl(strip_trailing_lf("Footprint D3\n")), Some("D3".to_string()));
        assert_eq!(extract_ref_impl(strip_trailing_lf("of C16\n")), Some("C16".to_string()));
    }

    #[test]
    fn extract_net_matches_cpython_shapes() {
        assert_eq!(extract_net_impl("Via [GND] on F.Cu - B.Cu"), Some("GND".to_string()));
        assert_eq!(
            extract_net_impl("Pad 2 [hb.gate_hs.driver-p2] of C22 on F.Cu"),
            Some("hb.gate_hs.driver-p2".to_string())
        );
        assert_eq!(extract_net_impl("Polygon on Edge.Cuts"), None);
        // Leftmost-first: the first bracket group wins.
        assert_eq!(extract_net_impl("[a][b]"), Some("a".to_string()));
    }

    #[test]
    fn py_mod_follows_cpython_divisor_sign() {
        assert_eq!(py_mod(7, 5), 2);
        assert_eq!(py_mod(-7, 5), 3);
        assert_eq!(py_mod(7, -5), -3);
        assert_eq!(py_mod(-7, -5), -2);
        assert_eq!(py_mod(0, 5), 0);
        assert_eq!(py_mod(100, 100), 0);
        assert_eq!(py_mod(101, 100), 1);
    }

    #[test]
    fn scheduler_is_final_phase_matches_oracle() {
        // total=5000, final=500 -> final_start=4500.
        assert!(!scheduler_is_final_phase(4499, 5000, 500));
        assert!(scheduler_is_final_phase(4500, 5000, 500));
        assert!(scheduler_is_final_phase(4999, 5000, 500));
        assert!(!scheduler_is_final_phase(0, 5000, 500));
    }

    #[test]
    fn scheduler_get_interval_selects_final_phase_interval() {
        assert_eq!(scheduler_get_interval(1000, 5000, 500, 100, 20), 100);
        assert_eq!(scheduler_get_interval(4500, 5000, 500, 100, 20), 20);
    }

    #[test]
    fn scheduler_should_run_matches_oracle_cases() {
        // Epoch 0, interval 100 -> run.
        assert!(scheduler_should_run(0, 5000, 500, 100, 20, true, true, false).is_ok_and(|b| b));
        // Epoch 50 -> no.
        assert!(!scheduler_should_run(50, 5000, 500, 100, 20, true, true, false).is_ok_and(|b| b));
        // Last epoch always runs.
        assert!(scheduler_should_run(4999, 5000, 500, 100, 20, true, true, false).is_ok_and(|b| b));
        // Disabled master / kind.
        assert!(!scheduler_should_run(0, 5000, 500, 100, 20, false, true, false).is_ok_and(|b| b));
        assert!(!scheduler_should_run(0, 5000, 500, 100, 20, true, false, false).is_ok_and(|b| b));
        // Already run.
        assert!(!scheduler_should_run(100, 5000, 500, 100, 20, true, true, true).is_ok_and(|b| b));
        // Final phase uses the finer interval.
        assert!(scheduler_should_run(4520, 5000, 500, 100, 20, true, true, false).is_ok_and(|b| b));
        assert!(!scheduler_should_run(4510, 5000, 500, 100, 20, true, true, false).is_ok_and(|b| b));
    }

    #[test]
    fn scheduler_should_run_zero_interval_raises_zero_division() {
        assert!(scheduler_should_run(5, 10, 0, 0, 0, true, true, false).is_err());
    }

    #[test]
    fn gate_placement_complete_decisions() {
        let (status, message, failed) = get_verdict(gate_placement_complete(0.0, 0.0, 0.0, 0.0, 100));
        assert_eq!(status, "pass");
        assert_eq!(message, "All constraints met");
        assert!(failed.is_empty());

        let (status, message, failed) = get_verdict(gate_placement_complete(0.05, 0.0, 0.0, 0.0, 100));
        assert_eq!(status, "fail");
        assert_eq!(message, "Failed 1 constraint(s)");
        assert_eq!(failed, vec![("overlap_loss".to_string(), 0.05)]);

        let (status, message, failed) = get_verdict(gate_placement_complete(0.0, 0.0, 2.0, 1.0, 100));
        assert_eq!(status, "fail");
        assert_eq!(message, "Failed 2 constraint(s)");
        assert_eq!(
            failed,
            vec![
                ("hv_clearance_violations".to_string(), 2.0),
                ("zone_violations".to_string(), 1.0),
            ]
        );

        let (status, message, _failed) = get_verdict(gate_placement_complete(0.0, 0.0, 0.0, 0.0, 0));
        assert_eq!(status, "fail");
        assert_eq!(message, "Did not converge");
    }

    #[test]
    fn gate_routing_complete_decisions() {
        let (status, message, failed) = get_verdict(gate_routing_complete(-1.0, 0.0));
        assert_eq!(status, "skip");
        assert_eq!(message, "Routing not measured");
        assert!(failed.is_empty());

        let (status, message, failed) = get_verdict(gate_routing_complete(100.0, 0.0));
        assert_eq!(status, "pass");
        assert_eq!(message, "Routing complete with 0 DRC errors");
        assert!(failed.is_empty());

        let (status, message, failed) = get_verdict(gate_routing_complete(80.0, 3.0));
        assert_eq!(status, "fail");
        assert_eq!(message, "Failed 2 requirement(s)");
        assert_eq!(
            failed,
            vec![
                ("routing_completion_percent".to_string(), 80.0),
                ("drc_errors".to_string(), 3.0),
            ]
        );
    }

    #[test]
    fn gate_production_ready_propagates_placement_failure() {
        let (status, message, failed) = get_verdict(gate_production_ready(0.5, 0.0, 0.0, 0.0, 100, 100.0, 0.0));
        assert_eq!(status, "fail");
        assert_eq!(message, "Placement not ready: Failed 1 constraint(s)");
        assert_eq!(failed, vec![("overlap_loss".to_string(), 0.5)]);

        let (status, message, _failed) =
            get_verdict(gate_production_ready(0.0, 0.0, 0.0, 0.0, 100, 100.0, 0.0));
        assert_eq!(status, "pass");
        assert_eq!(message, "Production ready");

        let (status, _message, failed) =
            get_verdict(gate_production_ready(0.0, 0.0, 0.0, 0.0, 100, 50.0, 2.0));
        assert_eq!(status, "fail");
        assert_eq!(
            failed,
            vec![
                ("routing_completion_percent".to_string(), 50.0),
                ("drc_errors".to_string(), 2.0),
            ]
        );
    }

    #[test]
    fn gate_validated_decisions() {
        let (status, message, failed) = get_verdict(gate_validated(None, Some(0.05)));
        assert_eq!(status, "skip");
        assert_eq!(message, "Statistical validation not performed");
        assert!(failed.is_empty());

        let (status, message, _failed) = get_verdict(gate_validated(Some(1.0), Some(0.05)));
        assert_eq!(status, "pass");
        assert_eq!(message, "Statistically validated");

        let (status, message, failed) = get_verdict(gate_validated(Some(10.0), Some(0.2)));
        assert_eq!(status, "fail");
        assert_eq!(message, "Failed 2 statistical requirement(s)");
        assert_eq!(
            failed,
            vec![
                ("failure_rate".to_string(), 10.0),
                ("loss_cv".to_string(), 0.2),
            ]
        );
    }
}
