// Wave-4 Phase-5 explainability-surface migration (temper-io-types).
//
// Migrates the compute of `temper_placer/explainability/{trace,decision,
// logger,markdown_report,serialization,traced_loss,pipeline}.py`
// bit-identically into this crate. The Python modules become delegation
// shims; the pre-migration implementations are pinned verbatim as the
// differential oracles (`tests/explainability/explain_oracle/`).
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

use crate::pyfmt::{py_float_fmt_1, py_float_fmt_2, py_float_fmt_4};
use crate::report::{iter_items, py_str, to_f64};

/// `seq[i]` — Python-level `__getitem__`, matching the oracle's indexing
/// (`new[0]` / `old[1]` / `pos[0]`), so ANY indexable sequence works:
/// tuple, list, numpy array. Out-of-range raises the sequence's own
/// IndexError (the oracle raises it too).
fn seq_index<'py>(seq: &Bound<'py, PyAny>, i: usize) -> PyResult<Bound<'py, PyAny>> {
    seq.get_item(i)
}
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
// logger.py — should_log / significant_change / log_* decision construction
// ---------------------------------------------------------------------------

/// Python modulo (result has the divisor's sign — non-negative for a
/// positive divisor); raises ZeroDivisionError for interval == 0 like
/// Python's `%`.
fn py_mod(epoch: i64, interval: i64) -> PyResult<i64> {
    if interval == 0 {
        return Err(pyo3::exceptions::PyZeroDivisionError::new_err(
            "integer division or modulo by zero",
        ));
    }
    Ok(epoch.rem_euclid(interval))
}

/// `DecisionLogger.should_log` — interval gating with Python modulo.
#[pyfunction]
#[pyo3(signature = (epoch, interval = 100, is_final = false))]
pub fn explain_should_log(epoch: i64, interval: i64, is_final: bool) -> PyResult<bool> {
    catch(|| {
        if is_final {
            return Ok(true);
        }
        Ok(py_mod(epoch, interval)? == 0)
    })
}

/// `DecisionLogger.significant_change` — Euclidean distance via IEEE sqrt.
#[pyfunction]
#[pyo3(signature = (old, new, threshold = 0.5))]
pub fn explain_significant_change(
    old: &Bound<'_, PyAny>,
    new: &Bound<'_, PyAny>,
    threshold: f64,
) -> PyResult<bool> {
    catch(|| {
        let ox = to_f64(&seq_index(old, 0)?)?;
        let oy = to_f64(&seq_index(old, 1)?)?;
        let nx = to_f64(&seq_index(new, 0)?)?;
        let ny = to_f64(&seq_index(new, 1)?)?;
        let dx = nx - ox;
        let dy = ny - oy;
        let distance = (dx * dx + dy * dy).sqrt();
        Ok(distance >= threshold)
    })
}

/// `DecisionLogger.log_position`'s decision-construction payload.
#[allow(clippy::too_many_arguments)] // mirrors DecisionLogger.log_position's signature
#[pyfunction]
#[pyo3(signature = (phase_value, subject, value, previous, reason, constraint_refs, alternatives, loss_delta, epoch, iteration))]
pub fn explain_log_position(
    py: Python<'_>,
    phase_value: &str,
    subject: &str,
    value: &Bound<'_, PyAny>,
    previous: Option<&Bound<'_, PyAny>>,
    reason: &str,
    constraint_refs: &Bound<'_, PyAny>,
    alternatives: &Bound<'_, PyAny>,
    loss_delta: Option<f64>,
    epoch: Option<i64>,
    iteration: Option<i64>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        let decision_type = if previous.is_some() {
            "position_update"
        } else {
            "initial_position"
        };
        out.set_item("decision_type", decision_type)?;
        out.set_item("phase", phase_value)?;
        out.set_item("subject", subject)?;
        out.set_item("value", value)?;
        match previous {
            Some(p) => out.set_item("previous_value", p)?,
            None => out.set_item("previous_value", py.None())?,
        }
        out.set_item("reason", reason)?;
        out.set_item("constraint_refs", constraint_refs)?;
        out.set_item("loss_contribution", loss_delta.unwrap_or(0.0))?;
        out.set_item("alternatives", alternatives)?;
        match epoch {
            Some(e) => out.set_item("epoch", e)?,
            None => out.set_item("epoch", py.None())?,
        }
        match iteration {
            Some(i) => out.set_item("iteration", i)?,
            None => out.set_item("iteration", py.None())?,
        }
        Ok(out.unbind())
    })
}

/// `DecisionLogger.log_rotation`'s decision-construction payload.
#[allow(clippy::too_many_arguments)] // mirrors DecisionLogger.log_rotation's signature
#[pyfunction]
#[pyo3(signature = (phase_value, subject, rotation, previous, reason, epoch, iteration))]
pub fn explain_log_rotation(
    py: Python<'_>,
    phase_value: &str,
    subject: &str,
    rotation: i64,
    previous: Option<i64>,
    reason: &str,
    epoch: Option<i64>,
    iteration: Option<i64>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        out.set_item("decision_type", "rotation")?;
        out.set_item("phase", phase_value)?;
        out.set_item("subject", subject)?;
        out.set_item("value", rotation)?;
        match previous {
            Some(p) => out.set_item("previous_value", p)?,
            None => out.set_item("previous_value", py.None())?,
        }
        out.set_item("reason", reason)?;
        out.set_item("constraint_refs", PyList::empty(py))?;
        out.set_item("loss_contribution", 0.0)?;
        out.set_item("alternatives", PyList::empty(py))?;
        match epoch {
            Some(e) => out.set_item("epoch", e)?,
            None => out.set_item("epoch", py.None())?,
        }
        match iteration {
            Some(i) => out.set_item("iteration", i)?,
            None => out.set_item("iteration", py.None())?,
        }
        Ok(out.unbind())
    })
}

/// `DecisionLogger.log_heuristic`'s decision-construction payload
/// (effective-reason generation, confidence-as-loss, TOPOLOGICAL default).
#[allow(clippy::too_many_arguments)] // mirrors DecisionLogger.log_heuristic's signature
#[pyfunction]
#[pyo3(signature = (heuristic_name, subject, position, reason, confidence, epoch, iteration))]
pub fn explain_log_heuristic(
    py: Python<'_>,
    heuristic_name: &str,
    subject: &str,
    position: &Bound<'_, PyAny>,
    reason: &str,
    confidence: &Bound<'_, PyAny>,
    epoch: Option<i64>,
    iteration: Option<i64>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        let effective_reason = if reason.is_empty() {
            format!("Placed by {heuristic_name} heuristic")
        } else {
            reason.to_string()
        };
        out.set_item("decision_type", "initial_position")?;
        out.set_item("phase", "topological")?;
        out.set_item("subject", subject)?;
        out.set_item("value", position)?;
        out.set_item("previous_value", py.None())?;
        out.set_item("reason", effective_reason)?;
        out.set_item("constraint_refs", PyList::empty(py))?;
        // Pass the confidence through UNCHANGED (int stays int) — the oracle
        // stores `loss_contribution=confidence` raw (#715/#754 int-preservation).
        out.set_item("loss_contribution", confidence)?;
        out.set_item("alternatives", PyList::empty(py))?;
        match epoch {
            Some(e) => out.set_item("epoch", e)?,
            None => out.set_item("epoch", py.None())?,
        }
        match iteration {
            Some(i) => out.set_item("iteration", i)?,
            None => out.set_item("iteration", py.None())?,
        }
        Ok(out.unbind())
    })
}

/// `DecisionLogger.log_constraint_application`'s decision-construction
/// payload (effective-reason generation, constraint_refs=[id]).
#[allow(clippy::too_many_arguments)] // mirrors log_constraint_application's signature
#[pyfunction]
#[pyo3(signature = (phase_value, constraint_id, affected_components, action, reason, epoch, iteration))]
pub fn explain_log_constraint(
    py: Python<'_>,
    phase_value: &str,
    constraint_id: &str,
    affected_components: &Bound<'_, PyAny>,
    action: &str,
    reason: &str,
    epoch: Option<i64>,
    iteration: Option<i64>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        let effective_reason = if !reason.is_empty() {
            reason.to_string()
        } else {
            let joined = iter_items(affected_components)?
                .iter()
                .map(|c| py_str(c))
                .collect::<PyResult<Vec<_>>>()?
                .join(", ");
            format!("Constraint {constraint_id} {action}: affected {joined}")
        };
        out.set_item("decision_type", "constraint_applied")?;
        out.set_item("phase", phase_value)?;
        out.set_item("subject", constraint_id)?;
        out.set_item("value", affected_components)?;
        out.set_item("previous_value", py.None())?;
        out.set_item("reason", effective_reason)?;
        let refs = PyList::empty(py);
        refs.append(constraint_id)?;
        out.set_item("constraint_refs", refs)?;
        out.set_item("loss_contribution", 0.0)?;
        out.set_item("alternatives", PyList::empty(py))?;
        match epoch {
            Some(e) => out.set_item("epoch", e)?,
            None => out.set_item("epoch", py.None())?,
        }
        match iteration {
            Some(i) => out.set_item("iteration", i)?,
            None => out.set_item("iteration", py.None())?,
        }
        Ok(out.unbind())
    })
}

// ---------------------------------------------------------------------------
// markdown_report.py
// ---------------------------------------------------------------------------

/// `_format_value` — see markdown_report.py for the Python source.
fn format_value_impl(value: &Bound<'_, PyAny>) -> PyResult<String> {
    if value.is_none() {
        return Ok("-".to_string());
    }
    if is_seq(value) {
        let items = iter_items(value)?;
        let len = items.len();
        if len == 2 {
            let x = py_float_fmt_1(to_f64(&items[0])?);
            let y = py_float_fmt_1(to_f64(&items[1])?);
            return Ok(format!("({x}, {y})"));
        }
        if len == 3 {
            let x = py_float_fmt_1(to_f64(&items[0])?);
            let y = py_float_fmt_1(to_f64(&items[1])?);
            return Ok(format!("({x}, {y}) @ {}°", py_str(&items[2])?));
        }
        return py_str(value);
    }
    if let Ok(d) = value.cast::<PyDict>() {
        let has_x = d.get_item("x")?.is_some();
        let has_y = d.get_item("y")?.is_some();
        if has_x && has_y {
            let x_item = d
                .get_item("x")?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("x"))?;
            let y_item = d
                .get_item("y")?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("y"))?;
            let x = py_float_fmt_1(to_f64(&x_item)?);
            let y = py_float_fmt_1(to_f64(&y_item)?);
            let rot = match d.get_item("rotation")? {
                Some(r) => py_str(&r)?,
                None => "0".to_string(), // Python default: value.get("rotation", 0)
            };
            return Ok(format!("({x}, {y}) @ {rot}°"));
        }
        return py_str(value);
    }
    if value.is_instance_of::<pyo3::types::PyFloat>() {
        return Ok(py_float_fmt_2(value.extract::<f64>()?));
    }
    py_str(value)
}

/// `_truncate(text, max_len)` — Python slicing by code points.
fn truncate(text: &str, max_len: usize) -> String {
    let chars: Vec<char> = text.chars().collect();
    if chars.len() <= max_len {
        return text.to_string();
    }
    // Oracle: `text[:max_len - 3] + "..."`. For max_len < 3 the stop is
    // negative; CPython clamps `text[:-k]` to len - k code points
    // (max_len=2 -> text[:-1], 1 -> text[:-2], 0 -> text[:-3], floored at
    // ""). Unreachable from the 60/40/50 call sites, but pinned anyway.
    let cut: String = if max_len >= 3 {
        chars[..max_len - 3].iter().collect()
    } else {
        let keep = chars.len().saturating_sub(3 - max_len);
        chars[..keep].iter().collect()
    };
    format!("{cut}...")
}

/// Python `str.title()` restricted to the fixed lowercase enum values
/// ("geometric" -> "Geometric", "position_update" -> "Position Update").
fn py_title(s: &str) -> String {
    s.split('_')
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn count_by_phase_impl<'py>(
    py: Python<'py>,
    decisions: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    // Order by DecisionPhase enum order; only counts > 0.
    let order = [
        "semantic",
        "topological",
        "geometric",
        "routing",
        "refinement",
    ];
    let mut counts: [usize; 5] = [0; 5];
    for d in iter_items(decisions)? {
        let phase: String = d.getattr("phase")?.getattr("value")?.extract()?;
        if let Some(idx) = order.iter().position(|p| *p == phase) {
            counts[idx] += 1;
        }
    }
    let out = PyDict::new(py);
    for (i, phase) in order.iter().enumerate() {
        if counts[i] > 0 {
            out.set_item(*phase, counts[i])?;
        }
    }
    Ok(out)
}

fn count_by_type_impl<'py>(
    py: Python<'py>,
    decisions: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    // Counter(...).most_common(): count descending, ties by first-seen
    // (CPython's sort is stable).
    let mut counts: Vec<(String, usize)> = Vec::new();
    for d in iter_items(decisions)? {
        let dtype: String = d.getattr("decision_type")?.getattr("value")?.extract()?;
        if let Some(e) = counts.iter_mut().find(|(k, _)| *k == dtype) {
            e.1 += 1;
        } else {
            counts.push((dtype, 1));
        }
    }
    counts.sort_by(|a, b| b.1.cmp(&a.1)); // stable sort by count desc
    let out = PyDict::new(py);
    for (k, v) in &counts {
        out.set_item(k, v)?;
    }
    Ok(out)
}

fn render_component_section_impl(
    _py: Python<'_>,
    subject: &str,
    decisions: &Bound<'_, PyAny>,
    max_decisions: usize,
) -> PyResult<String> {
    let decisions_vec = iter_items(decisions)?;
    let mut lines: Vec<String> = vec![format!("### {subject}"), String::new()];

    if decisions_vec.is_empty() {
        lines.push("*No decisions recorded*".to_string());
        lines.push(String::new());
        return Ok(lines.join("\n"));
    }

    let final_decision = decisions_vec.last().ok_or_else(|| {
        pyo3::exceptions::PyRuntimeError::new_err(
            "internal: decisions emptied between the emptiness check and the read",
        )
    })?;
    lines.push(format!(
        "**Final Value**: {}",
        format_value_impl(&final_decision.getattr("value")?)?
    ));
    let final_reason: String = final_decision.getattr("reason")?.extract()?;
    if !final_reason.is_empty() {
        lines.push(format!("**Final Reason**: {}", truncate(&final_reason, 60)));
    }
    lines.push(String::new());

    lines.push("#### Decision History".to_string());
    lines.push(String::new());
    lines.push("| # | Type | Epoch | Value | Reason |".to_string());
    lines.push("|---|------|-------|-------|--------|".to_string());

    let n = decisions_vec.len();
    let shown: Vec<&Bound<'_, PyAny>> = decisions_vec
        .iter()
        .skip(n.saturating_sub(max_decisions))
        .collect();
    let start_idx = n - shown.len() + 1;
    for (offset, d) in shown.iter().enumerate() {
        let i = start_idx + offset;
        let epoch = match d.getattr("epoch")? {
            e if e.is_none() => "-".to_string(),
            e => py_str(&e)?,
        };
        let dtype: String = d.getattr("decision_type")?.getattr("value")?.extract()?;
        let value = format_value_impl(&d.getattr("value")?)?;
        let reason: String = d.getattr("reason")?.extract()?;
        lines.push(format!(
            "| {i} | {} | {epoch} | {value} | {} |",
            py_title(&dtype),
            truncate(&reason, 40)
        ));
    }

    if n > max_decisions {
        lines.push(format!(
            "| ... | *{} earlier decisions omitted* | | | |",
            n - max_decisions
        ));
    }
    lines.push(String::new());

    let final_refs = final_decision.getattr("constraint_refs")?;
    if !final_refs.is_empty()? {
        lines.push("**Binding Constraints**:".to_string());
        lines.push(String::new());
        for r in iter_items(&final_refs)? {
            lines.push(format!("- `{}`", py_str(&r)?));
        }
        lines.push(String::new());
    }

    let mut all_alts: Vec<Bound<'_, PyAny>> = Vec::new();
    for d in &decisions_vec {
        for alt in iter_items(&d.getattr("alternatives")?)? {
            all_alts.push(alt);
        }
    }
    if !all_alts.is_empty() {
        lines.push("**Rejected Alternatives**:".to_string());
        lines.push(String::new());
        for (i, alt) in all_alts.iter().take(5).enumerate() {
            let value = format_value_impl(&alt.getattr("value")?)?;
            let reason: String = alt.getattr("rejection_reason")?.extract()?;
            let constraint_violated = alt.getattr("constraint_violated")?;
            if constraint_violated.is_truthy()? {
                lines.push(format!(
                    "{}. {value}: {} (`{}`)",
                    i + 1,
                    truncate(&reason, 50),
                    py_str(&constraint_violated)?
                ));
            } else {
                lines.push(format!("{}. {value}: {}", i + 1, truncate(&reason, 50)));
            }
        }
        if all_alts.len() > 5 {
            lines.push(format!(
                "   *...and {} more alternatives*",
                all_alts.len() - 5
            ));
        }
        lines.push(String::new());
    }

    Ok(lines.join("\n"))
}

struct MarkdownRenderOpts<'a> {
    include_config: bool,
    include_positions: bool,
    start_str: &'a str,
    end_str: Option<&'a str>,
    duration: Option<f64>,
    max_decisions_per_component: usize,
}

fn render_markdown_report_impl(
    py: Python<'_>,
    trace: &Bound<'_, PyAny>,
    opts: MarkdownRenderOpts<'_>,
) -> PyResult<String> {
    let mut lines: Vec<String> = Vec::new();

    // -- header --
    let run_id: String = trace.getattr("run_id")?.extract()?;
    lines.push("# Placement Decision Report".to_string());
    lines.push(String::new());
    lines.push(format!("**Run ID**: `{run_id}`"));
    lines.push(format!("**Started**: {}", opts.start_str));
    if let Some(end) = opts.end_str {
        lines.push(format!("**Ended**: {end}"));
        let d = opts.duration.ok_or_else(|| {
            pyo3::exceptions::PyRuntimeError::new_err(
                "internal: ended timestamp present without a opts.duration",
            )
        })?;
        lines.push(format!("**Duration**: {} seconds", py_float_fmt_1(d)));
    }
    let decisions = trace.getattr("decisions")?;
    let subjects: std::collections::HashSet<String> = iter_items(&decisions)?
        .iter()
        .map(|d| d.getattr("subject").and_then(|s| s.extract::<String>()))
        .collect::<PyResult<_>>()?;
    lines.push(format!("**Components**: {}", subjects.len()));
    lines.push(format!(
        "**Total Decisions**: {}",
        iter_items(&decisions)?.len()
    ));
    lines.push(String::new());

    // -- summary metrics --
    let final_metrics = trace.getattr("final_metrics")?;
    if !final_metrics.is_empty()? {
        lines.push("## Summary Metrics".to_string());
        lines.push(String::new());
        lines.push("| Metric | Value |".to_string());
        lines.push("|--------|-------|".to_string());
        let mut items: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
        for (k, v) in final_metrics.cast::<PyDict>()?.iter() {
            items.push((py_str(&k)?, v));
        }
        items.sort_by(|a, b| a.0.cmp(&b.0));
        for (metric, value) in &items {
            if value.is_instance_of::<pyo3::types::PyFloat>() {
                lines.push(format!(
                    "| {metric} | {} |",
                    py_float_fmt_4(value.extract::<f64>()?)
                ));
            } else {
                lines.push(format!("| {metric} | {} |", py_str(value)?));
            }
        }
        lines.push(String::new());
    }

    // -- phase summary --
    let phase_counts = count_by_phase_impl(py, &decisions)?;
    if !phase_counts.is_empty() {
        lines.push("## Phase Summary".to_string());
        lines.push(String::new());
        lines.push("| Phase | Decisions |".to_string());
        lines.push("|-------|-----------|".to_string());
        for (phase, count) in phase_counts.iter() {
            let phase_str = py_str(&phase)?;
            lines.push(format!("| {} | {count} |", py_title(&phase_str)));
        }
        lines.push(String::new());
    }

    // -- type summary --
    let type_counts = count_by_type_impl(py, &decisions)?;
    if !type_counts.is_empty() {
        lines.push("## Decision Types".to_string());
        lines.push(String::new());
        lines.push("| Type | Count |".to_string());
        lines.push("|------|-------|".to_string());
        for (dtype, count) in type_counts.iter() {
            let dtype_str = py_str(&dtype)?;
            lines.push(format!("| {} | {count} |", py_title(&dtype_str)));
        }
        lines.push(String::new());
    }

    // -- component decisions (sorted subjects) --
    let mut subject_list: Vec<String> = subjects.into_iter().collect();
    subject_list.sort();
    if !subject_list.is_empty() {
        lines.push("## Component Decisions".to_string());
        lines.push(String::new());
        for subject in &subject_list {
            let subj_decisions = filter_by_subject(&decisions, subject)?;
            let subj_list = PyList::empty(py);
            for d in subj_decisions {
                subj_list.append(d)?;
            }
            lines.push(render_component_section_impl(
                py,
                subject,
                &subj_list.into_any(),
                opts.max_decisions_per_component,
            )?);
        }
    }

    // -- final positions --
    if opts.include_positions {
        let final_positions = trace.getattr("final_positions")?;
        if !final_positions.is_empty()? {
            lines.push("## Final Positions".to_string());
            lines.push(String::new());
            lines.push("| Component | X | Y |".to_string());
            lines.push("|-----------|---|---|".to_string());
            let mut items: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
            for (k, v) in final_positions.cast::<PyDict>()?.iter() {
                items.push((py_str(&k)?, v));
            }
            items.sort_by(|a, b| a.0.cmp(&b.0));
            for (comp, pos) in &items {
                let x = py_float_fmt_2(to_f64(&seq_index(pos, 0)?)?);
                let y = py_float_fmt_2(to_f64(&seq_index(pos, 1)?)?);
                lines.push(format!("| {comp} | {x} | {y} |"));
            }
            lines.push(String::new());
        }
    }

    // -- config snapshot --
    if opts.include_config {
        let config = trace.getattr("config_snapshot")?;
        if !config.is_empty()? {
            lines.push("## Configuration".to_string());
            lines.push(String::new());
            lines.push("```yaml".to_string());
            let mut items: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
            for (k, v) in config.cast::<PyDict>()?.iter() {
                items.push((py_str(&k)?, v));
            }
            items.sort_by(|a, b| a.0.cmp(&b.0));
            for (key, value) in &items {
                lines.push(format!("{key}: {}", py_str(value)?));
            }
            lines.push("```".to_string());
            lines.push(String::new());
        }
    }

    Ok(lines.join("\n"))
}

/// `render_markdown_report` — the shim pre-formats the two timestamp
/// strings and the duration (strftime / datetime arithmetic stay Python).
#[allow(clippy::too_many_arguments)] // mirrors markdown_report.render_markdown_report's signature
#[pyfunction]
#[pyo3(signature = (trace, include_config, include_positions, start_str, end_str, duration, max_decisions_per_component = 10))]
pub fn explain_render_markdown_report(
    py: Python<'_>,
    trace: &Bound<'_, PyAny>,
    include_config: bool,
    include_positions: bool,
    start_str: &str,
    end_str: Option<&str>,
    duration: Option<f64>,
    max_decisions_per_component: usize,
) -> PyResult<String> {
    catch(|| {
        render_markdown_report_impl(
            py,
            trace,
            MarkdownRenderOpts {
                include_config,
                include_positions,
                start_str,
                end_str,
                duration,
                max_decisions_per_component,
            },
        )
    })
}

/// `render_component_report` — max_decisions=50, no timestamps needed.
#[pyfunction]
pub fn explain_render_component_report(
    py: Python<'_>,
    trace: &Bound<'_, PyAny>,
    subject: &str,
) -> PyResult<String> {
    catch(|| {
        let decisions = trace.getattr("decisions")?;
        let subj = filter_by_subject(&decisions, subject)?;
        let subj_list = PyList::empty(py);
        for d in subj {
            subj_list.append(d)?;
        }
        let run_id: String = trace.getattr("run_id")?.extract()?;
        let mut lines: Vec<String> = vec![
            format!("# Decision Report: {subject}"),
            String::new(),
            format!("**Run ID**: `{run_id}`"),
            format!("**Total Decisions**: {}", subj_list.len()),
            String::new(),
        ];
        lines.push(render_component_section_impl(
            py,
            subject,
            &subj_list.into_any(),
            50,
        )?);
        Ok(lines.join("\n"))
    })
}

// ---------------------------------------------------------------------------
// serialization.py
// ---------------------------------------------------------------------------

/// `_serialize_value` — recursion with shallow tuple conversion and the
/// `tolist` protocol (called back).
fn serialize_value_impl<'py>(
    py: Python<'py>,
    value: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if value.is_none() {
        return Ok(value.clone());
    }
    if value.is_instance_of::<PyTuple>() {
        let tup = value.cast::<PyTuple>()?;
        return Ok(tup.to_list().into_any());
    }
    if value.hasattr("tolist")? {
        return value.call_method0("tolist");
    }
    if let Ok(d) = value.cast::<PyDict>() {
        let out = PyDict::new(py);
        for (k, v) in d.iter() {
            out.set_item(&k, serialize_value_impl(py, &v)?)?;
        }
        return Ok(out.into_any());
    }
    if let Ok(l) = value.cast::<PyList>() {
        let out = PyList::empty(py);
        for v in l.iter() {
            out.append(serialize_value_impl(py, &v)?)?;
        }
        return Ok(out.into_any());
    }
    Ok(value.clone())
}

/// `_serialize_value`'s compute.
#[pyfunction]
pub fn explain_serialize_value(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    catch(|| serialize_value_impl(py, value).map(|v| v.unbind()))
}

/// `_deserialize_value`'s compute (list -> tuple when as_tuple).
#[pyfunction]
#[pyo3(signature = (value, as_tuple = false))]
pub fn explain_deserialize_value(
    py: Python<'_>,
    value: &Bound<'_, PyAny>,
    as_tuple: bool,
) -> PyResult<Py<PyAny>> {
    catch(|| {
        if value.is_none() {
            return Ok(value.clone().unbind());
        }
        if as_tuple && let Ok(l) = value.cast::<PyList>() {
            return Ok(PyTuple::new(py, l.iter())?.into_any().unbind());
        }
        Ok(value.clone().unbind())
    })
}

/// `serialize_alternative`'s dict shape.
#[pyfunction]
pub fn explain_serialize_alternative(
    py: Python<'_>,
    alt: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        out.set_item("value", serialize_value_impl(py, &alt.getattr("value")?)?)?;
        out.set_item("rejection_reason", alt.getattr("rejection_reason")?)?;
        out.set_item("constraint_violated", alt.getattr("constraint_violated")?)?;
        out.set_item("loss_if_chosen", alt.getattr("loss_if_chosen")?)?;
        Ok(out.unbind())
    })
}

/// `serialize_decision`'s dict shape (timestamp.isoformat() called back).
#[pyfunction]
pub fn explain_serialize_decision(
    py: Python<'_>,
    decision: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        out.set_item("id", decision.getattr("id")?)?;
        let ts = decision.getattr("timestamp")?.call_method0("isoformat")?;
        out.set_item("timestamp", ts)?;
        let phase: String = decision.getattr("phase")?.getattr("value")?.extract()?;
        out.set_item("phase", phase)?;
        let dtype: String = decision
            .getattr("decision_type")?
            .getattr("value")?
            .extract()?;
        out.set_item("decision_type", dtype)?;
        out.set_item("subject", decision.getattr("subject")?)?;
        out.set_item(
            "value",
            serialize_value_impl(py, &decision.getattr("value")?)?,
        )?;
        out.set_item(
            "previous_value",
            serialize_value_impl(py, &decision.getattr("previous_value")?)?,
        )?;
        out.set_item("reason", decision.getattr("reason")?)?;
        out.set_item("constraint_refs", decision.getattr("constraint_refs")?)?;
        out.set_item("loss_contribution", decision.getattr("loss_contribution")?)?;
        let alts = PyList::empty(py);
        for alt in iter_items(&decision.getattr("alternatives")?)? {
            alts.append(explain_serialize_alternative(py, &alt)?)?;
        }
        out.set_item("alternatives", alts)?;
        out.set_item("epoch", decision.getattr("epoch")?)?;
        out.set_item("iteration", decision.getattr("iteration")?)?;
        Ok(out.unbind())
    })
}

/// `serialize_trace`'s dict shape (`final_positions` tuples -> lists via
/// Python's `list()`).
#[pyfunction]
pub fn explain_serialize_trace(py: Python<'_>, trace: &Bound<'_, PyAny>) -> PyResult<Py<PyDict>> {
    catch(|| {
        let out = PyDict::new(py);
        out.set_item("run_id", trace.getattr("run_id")?)?;
        let start = trace.getattr("start_time")?.call_method0("isoformat")?;
        out.set_item("start_time", start)?;
        let end = trace.getattr("end_time")?;
        if end.is_none() {
            out.set_item("end_time", py.None())?;
        } else {
            out.set_item("end_time", end.call_method0("isoformat")?)?;
        }
        out.set_item("config_snapshot", trace.getattr("config_snapshot")?)?;
        let decisions = PyList::empty(py);
        for d in iter_items(&trace.getattr("decisions")?)? {
            decisions.append(explain_serialize_decision(py, &d)?)?;
        }
        out.set_item("decisions", decisions)?;
        let positions = trace.getattr("final_positions")?;
        let pos_out = PyDict::new(py);
        for (k, v) in positions.cast::<PyDict>()?.iter() {
            let lst = py.import("builtins")?.getattr("list")?.call1((&v,))?;
            pos_out.set_item(&k, lst)?;
        }
        out.set_item("final_positions", pos_out)?;
        out.set_item("final_metrics", trace.getattr("final_metrics")?)?;
        Ok(out.unbind())
    })
}

// ---------------------------------------------------------------------------
// traced_loss.py + pipeline.py
// ---------------------------------------------------------------------------

/// `constraint_to_traced_loss`'s subject/because introspection (the
/// hasattr chain). Returns (subject, because).
#[pyfunction]
pub fn explain_constraint_subject(constraint: &Bound<'_, PyAny>) -> PyResult<(String, String)> {
    catch(|| {
        let subject = if constraint.hasattr("a")? {
            py_str(&constraint.getattr("a")?)?
        } else if constraint.hasattr("component")? {
            py_str(&constraint.getattr("component")?)?
        } else if constraint.hasattr("components")? {
            let components = constraint.getattr("components")?;
            let first = iter_items(&components)?.into_iter().next();
            match first {
                Some(c) => py_str(&c)?,
                None => "unknown".to_string(),
            }
        } else {
            "unknown".to_string()
        };
        let because = if constraint.hasattr("because")? {
            py_str(&constraint.getattr("because")?)?
        } else {
            "constraint".to_string()
        };
        Ok((subject, because))
    })
}

/// The `float(value) > threshold` gate (float conversion stays Python).
#[pyfunction]
pub fn explain_trace_threshold(value: f64, threshold: f64) -> PyResult<bool> {
    catch(|| Ok(value > threshold))
}

/// `compose_traces`'s monoid fold — concatenate the entries of N traces,
/// order-preserving, returning the combined entries tuple.
#[pyfunction]
pub fn explain_compose_traces(py: Python<'_>, traces: &Bound<'_, PyAny>) -> PyResult<Py<PyTuple>> {
    catch(|| {
        let mut entries: Vec<Bound<'_, PyAny>> = Vec::new();
        for t in iter_items(traces)? {
            for e in iter_items(&t.getattr("entries")?)? {
                entries.push(e);
            }
        }
        Ok(PyTuple::new(py, entries)?.unbind())
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncate_matches_cpython_negative_stop() {
        // Oracle `text[:max_len - 3] + "..."`: for max_len < 3 the stop is
        // negative and CPython clamps it (max_len=2 -> text[:-1],
        // max_len=1 -> text[:-2], max_len=0 -> text[:-3], floored at "").
        // Values measured against CPython on 2026-08-05. Unreachable from
        // the 60/40/50 call sites, but pinned anyway.
        assert_eq!(truncate("abcdefghij", 2), "abcdefghi...");
        assert_eq!(truncate("abcdefghij", 1), "abcdefgh...");
        assert_eq!(truncate("abcdefghij", 0), "abcdefg...");
        assert_eq!(truncate("abcd", 0), "a...");
        assert_eq!(truncate("abc", 1), "a...");
        assert_eq!(truncate("ab", 1), "...");
        assert_eq!(truncate("ab", 0), "...");
        // Untruncated and normal paths unchanged.
        assert_eq!(truncate("ab", 2), "ab");
        assert_eq!(truncate("abcdefghij", 8), "abcde...");
        assert_eq!(truncate("abcdefghij", 3), "...");
    }
}
