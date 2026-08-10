// Shared FFI helpers for the Phase D batch D6 validation stages (Rust
// Orchestration Engine plan 2026-08-09-001). The D1-D5 stages each carry
// their own private copies of `py_format` / `log_msg` / etc.; the six D6
// stages share enough of the same CPython call-back surface (print /
// str.join / str.format / logging / sorted / isinstance) that a single
// shared module avoids six parallel copies.
//
// Every helper routes the operation through CPython itself (builtins.print,
// str.join, str.format, logging.getLogger, builtins.sorted,
// builtins.isinstance) so message rendering, decimal formatting and set/sort
// semantics stay bit-identical to the pre-migration Python by construction.

use pyo3::prelude::*;
use pyo3::types::PyString;

/// CPython `print(*args)` (writes to `sys.stdout`, captured by pytest).
pub(crate) fn py_print(py: Python<'_>, args: &[Bound<'_, PyAny>]) -> PyResult<()> {
    let print = py.import("builtins")?.getattr("print")?;
    print.call1(pyo3::types::PyTuple::new(py, args)?)?;
    Ok(())
}

/// CPython `sep.join(iterable)`.
pub(crate) fn py_join<'py>(
    py: Python<'py>,
    sep: &str,
    items: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    PyString::new(py, sep).call_method1("join", (items,))
}

/// CPython `str.format(template, *args)` -- the only message renderer
/// (David-Gay `:.1f`/`:.2f`, int/str interpolation) stays CPython.
pub(crate) fn py_format<'py>(
    py: Python<'py>,
    template: &str,
    args: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    PyString::new(py, template).call_method1("format", pyo3::types::PyTuple::new(py, args)?)
}

/// `logging.getLogger(logger_name).<level>(message)`.
pub(crate) fn log_msg(
    py: Python<'_>,
    logger_name: &str,
    level: &str,
    msg: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let logger = py.import("logging")?.call_method1("getLogger", (logger_name,))?;
    logger.call_method1(level, (msg,))?;
    Ok(())
}

/// CPython `sorted(iterable)` (stable `<`-sort; floats/strings like Python).
pub(crate) fn py_sorted<'py>(
    py: Python<'py>,
    iterable: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    py.import("builtins")?.getattr("sorted")?.call1((iterable,))
}

/// CPython `isinstance(obj, cls)`.
pub(crate) fn py_isinstance<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    cls: &Bound<'py, PyAny>,
) -> PyResult<bool> {
    py.import("builtins")?
        .getattr("isinstance")?
        .call1((obj, cls))?
        .extract()
}

/// The shared D6 write-back + raise channel: the pyfunctions that mirror a
/// raising Python stage (`PlacementValidationStage`, `DRCValidationStage`,
/// `ConnectivityValidationStage`) return `(state, message)` -- the written-back
/// state plus `None` on the normal path, or the ORIGINAL state plus the
/// `StageError` message when the stage's run() decided to raise (the Python
/// oracle raises BEFORE `dataclasses.replace`, so nothing is written back).
/// The shim raises its module's own exception type with that message -- the
/// exception classes stay Python (public API unchanged), the decision and the
/// message text are the migrated orchestration.
pub(crate) fn write_back_or_raise(
    py: Python<'_>,
    orig: &Bound<'_, PyAny>,
    result: Result<crate::board_state::BoardState, crate::stage::StageError>,
    candidates: &[&str],
) -> PyResult<(Py<PyAny>, Option<String>)> {
    match result {
        Ok(out) => Ok((crate::d1_bridge::to_python(py, orig, &out, candidates)?, None)),
        Err(e) if e.kind == crate::stage::StageErrorKind::Infeasible => {
            Ok((orig.clone().unbind(), Some(e.message)))
        }
        Err(e) => Err(crate::config_attach_stage::to_pyerr(&e)),
    }
}
