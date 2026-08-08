//! Shared CPython-exact `OverflowError` construction.
//!
//! `escape_via.rs` and `placement_suggestions.rs` each replicate CPython's
//! `x ** y` float-power overflow behaviour (see their `pow_operator` doc
//! comments for the measured trap: a FINITE base whose result overflows to
//! infinity raises, while an already-infinite/NaN base does not). Until this
//! fix both hardcoded the exception message as the literal string
//! `"Result too large"` -- macOS's `strerror(ERANGE)` text -- which does not
//! match glibc's `"Numerical result out of range"`. CPython's `float_pow`
//! builds this exception via `PyErr_SetFromErrno(PyExc_OverflowError)` after
//! `errno = ERANGE`, i.e. `OverflowError(errno, strerror(errno))` using
//! whatever the *host platform's* C library returns for that errno -- so the
//! only way to match it everywhere is to resolve the string the same way,
//! not to hardcode either platform's text.
//!
//! `packages/temper-drc-rs/src/dfm_py.rs::errno_overflow_error` already
//! carries this exact fix for cluster D; this is the same construction
//! (independently duplicated rather than shared across crates, since the two
//! crates don't otherwise depend on each other).

use pyo3::PyErr;
use pyo3::exceptions::PyOverflowError;

/// `PyErr_SetFromErrno(PyExc_OverflowError)` after `errno = ERANGE`, which is
/// how CPython's `float_pow` reports an overflowing `x ** y`.
///
/// The exception's `args` are `(errno, strerror(errno))`, so its `str()` is
/// `"(34, 'Result too large')"` on macOS and
/// `"(34, 'Numerical result out of range')"` on glibc. Resolving through the
/// platform's own `strerror` -- the same call CPython makes -- is what keeps
/// this matching the oracle everywhere instead of only on the platform
/// whatever string happened to be hardcoded.
pub(crate) fn overflow_error() -> PyErr {
    // ERANGE is 34 on Linux, macOS and the Windows CRT alike.
    const ERANGE: i32 = 34;
    unsafe extern "C" {
        fn strerror(errnum: i32) -> *const std::ffi::c_char;
    }
    // SAFETY: `strerror` returns a pointer to a static, NUL-terminated
    // string (or null); both are handled.
    let msg = unsafe {
        let p = strerror(ERANGE);
        if p.is_null() {
            "Result too large".to_owned()
        } else {
            std::ffi::CStr::from_ptr(p).to_string_lossy().into_owned()
        }
    };
    PyOverflowError::new_err((ERANGE, msg))
}
