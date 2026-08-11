// The decision-trace filtering compute of
// `temper_placer/cli/trace_commands.py` (Wave 4, Phase 5).
//
// The pre-migration module computed these INLINE in its click command
// bodies (`why`, `why_not`); the delegation shim keeps the full click
// surface (flags, help, exit codes, output text) and calls across the pyo3
// boundary here. The differential
// (`tests/cli/test_trace_commands_rust_differential.py`, oracle
// `tests/cli/_trace_commands_py_oracle.py`) extracts the inline expressions
// mechanically and pins bit-identical parity.
//
// The comparisons that decide the filters are Python value semantics
// (`dict.get` defaulting to `None`, `None == x`, `str()` of an arbitrary
// JSON leaf), so this module calls BACK into Python for each leaf
// comparison — `d.call_method1("get", ...)` raises the same `AttributeError`
// a non-dict element would, `PyAny::str()` is Python's `str()`, `PyAny::eq`
// is Python's `==`. The control flow (iteration, subject equality, the
// nested scan, first-match return) is Rust. Error parity for a
// non-iterable `decisions` (TypeError with CPython's message) comes from
// `PyObject_GetIter` on the Rust side, i.e. by identity.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyIterator, PyList};

#[cfg(feature = "python")]
/// The `why` subject filter, returned as the ORIGINAL indices of the
/// matching decisions (the shim's access pattern for printing):
///
/// ```python
/// [i for i, d in enumerate(decisions) if d.get("subject") == subject]
/// ```
#[pyfunction]
pub fn filter_decisions<'py>(
    decisions: &Bound<'py, PyAny>,
    subject: &Bound<'py, PyAny>,
) -> PyResult<Vec<usize>> {
    let mut out = Vec::new();
    for (i, item) in PyIterator::from_object(decisions)?.enumerate() {
        let d: Bound<'py, PyAny> = item?;
        // Python: d.get("subject") — missing key -> None; None == subject is
        // False for a non-None subject, True for subject=None. Both are
        // Python semantics, preserved by the call-back.
        let val = d.call_method1("get", ("subject",))?;
        if val.eq(subject)? {
            out.push(i);
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// The `why_not` nested scan: within the first subject-matching decision,
/// the first alternative whose ``str(alt.get("value")) == value``. Returns
/// the ORIGINAL decision index and the alternative index, or None.
///
/// ```python
/// for d in [d for d in decisions if d.get("subject") == subject]:
///     for alt in d.get("alternatives_considered", []):
///         if str(alt.get("value")) == value:
///             return (the alt's info)
/// ```
#[pyfunction]
pub fn find_rejected_alternative<'py>(
    py: Python<'py>,
    decisions: &Bound<'py, PyAny>,
    subject: &Bound<'py, PyAny>,
    value: &Bound<'py, PyAny>,
) -> PyResult<Option<(usize, usize)>> {
    let empty_list = PyList::empty(py);
    for (di, item) in PyIterator::from_object(decisions)?.enumerate() {
        let d = item?;
        let subj_val = d.call_method1("get", ("subject",))?;
        if !subj_val.eq(subject)? {
            continue;
        }
        // Python: d.get("alternatives_considered", [])
        let alts = d.call_method1("get", ("alternatives_considered", &empty_list))?;
        for (ai, aitem) in PyIterator::from_object(&alts)?.enumerate() {
            let alt: Bound<'py, PyAny> = aitem?;
            // Python: str(alt.get("value")) == value
            let av = alt.call_method1("get", ("value",))?;
            let av_str = av.str()?;
            if av_str.as_any().eq(value)? {
                return Ok(Some((di, ai)));
            }
        }
    }
    Ok(None)
}
