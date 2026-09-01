// Wave-4 Phase-5 explainability compute retained by temper-io-types.
//
// The trace/decision query kernels below remain the single-source Rust
// implementation used by the live orchestration pyclasses.
// Markdown rendering, logging, and persistence orchestration are owned by
// temper-orchestration or test-local adapters; no duplicate PyO3 wrappers are
// kept here.
//
// Boundary decisions (argued in-source and in VERIFICATION.md):
//   - Dataclasses, enums and their construction stay Python (frozen tuple
//     storage, Enum member identity, dataclass field access, `uuid`/
//     `datetime` defaults). The Rust side computes *fields*; the shim
//     constructs the objects.
//   - `str(value)` of arbitrary Python objects, `set` iteration order
//     (`unique_subjects`), `strftime`, `datetime` arithmetic and
//     `json.dumps` stay Python runtime semantics (called back across the
//     boundary where a value is needed inside Rust).
//   - `Trace.why`'s tuple-value `:.1f` rendering goes through
//     `crate::pyfmt` (nan/inf lowercase — the py_float_fmt seam).

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::pyfmt::{iter_items, py_float_fmt_1, py_float_fmt_4, py_str, to_f64};
// ---------------------------------------------------------------------------
// trace.py — Trace.why
// ---------------------------------------------------------------------------

fn trace_why_impl(
    entries: &Bound<'_, PyAny>,
    subject: &str,
    max_reasons: usize,
) -> PyResult<String> {
    let mut filtered: Vec<Bound<'_, PyAny>> = Vec::new();
    for entry in iter_items(entries)? {
        let s: String = entry.getattr("subject")?.extract()?;
        if s == subject {
            filtered.push(entry);
        }
    }

    if filtered.is_empty() {
        return Ok(format!("No decisions recorded for {subject}"));
    }

    let final_entry = filtered.last().ok_or_else(|| {
        pyo3::exceptions::PyRuntimeError::new_err(
            "internal: subject entries emptied between the emptiness check and the read",
        )
    })?;
    let value = final_entry.getattr("value")?;
    let value_str = if value.is_instance_of::<PyTuple>() {
        let tup = value.cast::<PyTuple>()?;
        if tup.len() == 2 {
            let x = py_float_fmt_1(to_f64(&tup.get_item(0)?)?);
            let y = py_float_fmt_1(to_f64(&tup.get_item(1)?)?);
            format!("({x}, {y})")
        } else {
            py_str(&value)?
        }
    } else {
        py_str(&value)?
    };

    let mut lines = vec![format!("{subject} is at {value_str} because:")];
    for entry in filtered.iter().take(max_reasons) {
        lines.push(format!("  - {}", py_str(&entry.getattr("because")?)?));
    }
    if filtered.len() > max_reasons {
        lines.push(format!(
            "  ... and {} more reasons",
            filtered.len() - max_reasons
        ));
    }
    Ok(lines.join("\n"))
}

/// `Trace.why`'s compute — the shim keeps the frozen dataclasses.
#[pyfunction]
#[pyo3(signature = (entries, subject, max_reasons = 3))]
pub fn explain_trace_why(
    entries: &Bound<'_, PyAny>,
    subject: &str,
    max_reasons: usize,
) -> PyResult<String> {
    catch(|| trace_why_impl(entries, subject, max_reasons))
}

// ---------------------------------------------------------------------------
// decision.py — DecisionTrace.why / why_not / history / summary
// ---------------------------------------------------------------------------

fn filter_by_subject<'py>(
    decisions: &Bound<'py, PyAny>,
    subject: &str,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out = Vec::new();
    for d in iter_items(decisions)? {
        let s: String = d.getattr("subject")?.extract()?;
        if s == subject {
            out.push(d);
        }
    }
    Ok(out)
}

fn decision_trace_why_impl(decisions: &Bound<'_, PyAny>, subject: &str) -> PyResult<String> {
    let filtered = filter_by_subject(decisions, subject)?;
    if filtered.is_empty() {
        return Ok(format!("No decisions recorded for {subject}"));
    }
    let last = filtered.last().ok_or_else(|| {
        pyo3::exceptions::PyRuntimeError::new_err(
            "internal: subject entries emptied between the emptiness check and the read",
        )
    })?;
    let value = py_str(&last.getattr("value")?)?;
    let reason: String = last.getattr("reason")?.extract()?;
    let mut msg = format!("{subject} is at {value} because: {reason}");
    let refs = last.getattr("constraint_refs")?;
    if !refs.is_empty()? {
        let joined = iter_items(&refs)?
            .iter()
            .map(|r| py_str(r))
            .collect::<PyResult<Vec<_>>>()?
            .join(", ");
        msg.push_str(&format!(" (Constraints: {joined})"));
    }
    Ok(msg)
}

/// `DecisionTrace.why`'s compute.
#[pyfunction]
pub fn explain_decision_trace_why(decisions: &Bound<'_, PyAny>, subject: &str) -> PyResult<String> {
    catch(|| decision_trace_why_impl(decisions, subject))
}

/// Python `isinstance(v, (list, tuple))` — both PyList and PyTuple.
fn is_seq(v: &Bound<'_, PyAny>) -> bool {
    v.is_instance_of::<PyList>() || v.is_instance_of::<PyTuple>()
}

/// `values_match(v1, v2)`: list/tuple on BOTH sides compare elementwise;
/// anything else uses Python `==`.
fn values_match(_py: Python<'_>, v1: &Bound<'_, PyAny>, v2: &Bound<'_, PyAny>) -> PyResult<bool> {
    if is_seq(v1) && is_seq(v2) {
        let a = iter_items(v1)?;
        let b = iter_items(v2)?;
        if a.len() != b.len() {
            return Ok(false);
        }
        for (x, y) in a.iter().zip(b.iter()) {
            if !x.eq(y)? {
                return Ok(false);
            }
        }
        return Ok(true);
    }
    v1.eq(v2)
}

fn decision_trace_why_not_impl(
    py: Python<'_>,
    decisions: &Bound<'_, PyAny>,
    subject: &str,
    value: &Bound<'_, PyAny>,
) -> PyResult<String> {
    let filtered = filter_by_subject(decisions, subject)?;
    for d in &filtered {
        for alt in iter_items(&d.getattr("alternatives")?)? {
            if values_match(py, &alt.getattr("value")?, value)? {
                let value_str = py_str(value)?;
                let rejection: String = alt.getattr("rejection_reason")?.extract()?;
                let mut msg = format!("{value_str} was rejected: {rejection}");
                // Python truthiness (`if alt.constraint_violated:`): '' is
                // falsy and suppresses the suffix.
                let constraint_violated = alt.getattr("constraint_violated")?;
                if constraint_violated.is_truthy()? {
                    msg.push_str(&format!(
                        " (Constraint violated: {})",
                        py_str(&constraint_violated)?
                    ));
                }
                let loss = alt.getattr("loss_if_chosen")?;
                if !loss.is_none() {
                    msg.push_str(&format!(
                        " (Loss if chosen: {})",
                        py_float_fmt_4(to_f64(&loss)?)
                    ));
                }
                return Ok(msg);
            }
        }
    }
    Ok(format!(
        "No record of {} being considered for {subject}",
        py_str(value)?
    ))
}

/// `DecisionTrace.why_not`'s compute.
#[pyfunction]
pub fn explain_decision_trace_why_not(
    py: Python<'_>,
    decisions: &Bound<'_, PyAny>,
    subject: &str,
    value: &Bound<'_, PyAny>,
) -> PyResult<String> {
    catch(|| decision_trace_why_not_impl(py, decisions, subject, value))
}

fn decision_trace_history_impl<'py>(
    py: Python<'py>,
    decisions: &Bound<'py, PyAny>,
    subject: &str,
) -> PyResult<Bound<'py, PyList>> {
    let filtered = filter_by_subject(decisions, subject)?;
    let out = PyList::empty(py);
    for d in &filtered {
        let tup = PyTuple::new(py, [d.getattr("value")?, d.getattr("reason")?])?;
        out.append(tup)?;
    }
    Ok(out)
}

/// `DecisionTrace.history`'s compute — list of (value, reason) 2-tuples.
#[pyfunction]
pub fn explain_decision_trace_history(
    py: Python<'_>,
    decisions: &Bound<'_, PyAny>,
    subject: &str,
) -> PyResult<Py<PyList>> {
    catch(|| decision_trace_history_impl(py, decisions, subject).map(|l| l.unbind()))
}

fn decision_trace_summary_impl<'py>(
    py: Python<'py>,
    decisions: &Bound<'py, PyAny>,
    unique_subjects: &Bound<'py, PyAny>,
    duration_seconds: Option<f64>,
    run_id: &str,
    final_metrics: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let mut by_phase: Vec<(String, usize)> = Vec::new();
    let mut by_type: Vec<(String, usize)> = Vec::new();
    for d in iter_items(decisions)? {
        let phase: String = d.getattr("phase")?.getattr("value")?.extract()?;
        if let Some(e) = by_phase.iter_mut().find(|(k, _)| *k == phase) {
            e.1 += 1;
        } else {
            by_phase.push((phase, 1));
        }
        let dtype: String = d.getattr("decision_type")?.getattr("value")?.extract()?;
        if let Some(e) = by_type.iter_mut().find(|(k, _)| *k == dtype) {
            e.1 += 1;
        } else {
            by_type.push((dtype, 1));
        }
    }

    let phase_dict = PyDict::new(py);
    for (k, v) in &by_phase {
        phase_dict.set_item(k, v)?;
    }
    let type_dict = PyDict::new(py);
    for (k, v) in &by_type {
        type_dict.set_item(k, v)?;
    }

    let subjects_count = iter_items(unique_subjects)?.len();

    let out = PyDict::new(py);
    out.set_item("run_id", run_id)?;
    out.set_item("total_decisions", iter_items(decisions)?.len())?;
    out.set_item("unique_subjects", unique_subjects)?;
    out.set_item("component_count", subjects_count)?;
    out.set_item("decisions_by_phase", phase_dict)?;
    out.set_item("decisions_by_type", type_dict)?;
    match duration_seconds {
        Some(d) => out.set_item("duration_seconds", d)?,
        None => out.set_item("duration_seconds", py.None())?,
    }
    out.set_item("final_metrics", final_metrics)?;
    Ok(out)
}

/// `DecisionTrace.summary`'s compute. `unique_subjects` (a Python set
/// iteration) and `duration_seconds` (datetime arithmetic) are computed by
/// the shim; everything else is Rust.
#[pyfunction]
#[pyo3(signature = (decisions, unique_subjects, duration_seconds, run_id, final_metrics))]
pub fn explain_decision_trace_summary(
    py: Python<'_>,
    decisions: &Bound<'_, PyAny>,
    unique_subjects: &Bound<'_, PyAny>,
    duration_seconds: Option<f64>,
    run_id: &str,
    final_metrics: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        decision_trace_summary_impl(
            py,
            decisions,
            unique_subjects,
            duration_seconds,
            run_id,
            final_metrics,
        )
        .map(|d| d.unbind())
    })
}

// ---------------------------------------------------------------------------
// catch_unwind seam (R1g)
// ---------------------------------------------------------------------------

fn catch<T>(f: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(res) => res,
        Err(panic) => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
            "panicked in temper-io-types: {}",
            panic_message(&panic)
        ))),
    }
}

fn panic_message(panic: &Box<dyn std::any::Any + Send>) -> String {
    if let Some(s) = panic.downcast_ref::<&str>() {
        (*s).to_string()
    } else if let Some(s) = panic.downcast_ref::<String>() {
        s.clone()
    } else {
        "unknown panic payload".to_string()
    }
}
