//! The pyo3 boundary for the cluster-D DFM kernels ([`crate::dfm`]).
//!
//! Everything here is marshalling: extract, call the pure kernel, convert
//! back. No arithmetic and no control flow that the kernel does not
//! already have, so `cargo test --no-default-features` still covers the
//! whole contract.
//!
//! The exported names are `REQUIRED_RUST_SYMBOLS` from
//! `packages/temper-placer/tests/router_v6/test_dfm_rust_differential.py`,
//! and each signature is fixed by the test that calls it. Three shapes are
//! worth stating because they look arbitrary otherwise:
//!
//! * kernels whose Python original reads a `Via`/`Board`/`CompiledRoute`
//!   take the *scalars* it reads instead — those objects are not pyclasses
//!   yet (survey slice 1), and the corpus is scalars for exactly that
//!   reason;
//! * a list of `(x, y, layer)` triples arrives as three parallel slices,
//!   because a `Vec<(f64, f64, String)>` extraction would allocate a
//!   String per vertex on the hot path;
//! * the four kernels whose *output type* depends on their input type
//!   (`int` in, `int` out) take `&Bound<PyAny>` and go through
//!   [`crate::dfm::PyNum`]; see its docs for why widening to `f64` fails
//!   the differential.
//!
//! pyo3 panic policy: every `#[pyfunction]` boundary is wrapped by pyo3's
//! default `catch_unwind`, so a panic surfaces as `PanicException` rather
//! than crossing the boundary as UB (R1g).

use pyo3::exceptions::{PyOverflowError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyAnyMethods, PyInt, PyList, PyString, PyStringMethods, PyTuple};
use pyo3::IntoPyObject;

use crate::dfm::{self, DfmError, PyNum};

// ---------------------------------------------------------------------------
// marshalling
// ---------------------------------------------------------------------------

fn extract_pynum(ob: &Bound<'_, PyAny>) -> PyResult<PyNum> {
    // `bool` is an `int` subclass and lands in the `Int` arm; see the
    // `PyNum` doc comment for that documented narrowing.
    if ob.is_instance_of::<PyInt>() {
        return Ok(PyNum::Int(ob.extract::<i64>()?));
    }
    Ok(PyNum::Float(ob.extract::<f64>()?))
}

fn pynum_into_py(py: Python<'_>, v: PyNum) -> PyResult<Py<PyAny>> {
    match v {
        PyNum::Int(i) => Ok(i.into_pyobject(py)?.into_any().unbind()),
        PyNum::Float(f) => Ok(f.into_pyobject(py)?.into_any().unbind()),
    }
}

/// `str(v)` as CPython renders it.
///
/// Delegated to the interpreter on purpose: `str(float)` is shortest-repr
/// with scientific notation below `1e-4` and at/above `1e16`, which Rust's
/// `Display` does not reproduce (`1e-300` renders as 300 zeroes and
/// `10.0` as `10`). This is *message* rendering on a cold error path, not
/// kernel arithmetic — the same boundary `validation.rs` draws for its
/// no-format-spec float interpolation.
fn pynum_str(py: Python<'_>, v: PyNum) -> PyResult<String> {
    Ok(pynum_into_py(py, v)?.bind(py).str()?.to_string())
}

/// `PyErr_SetFromErrno(PyExc_OverflowError)` after `errno = ERANGE`, which
/// is how CPython's `float_pow` reports an overflowing `x ** y`.
///
/// The exception's args are `(errno, strerror(errno))`, so its `str()` is
/// `"(34, 'Result too large')"` on macOS and
/// `"(34, 'Numerical result out of range')"` on glibc. The differential
/// compares exception *messages*, so the string is resolved through the
/// platform's own `strerror` — exactly the call CPython makes — rather
/// than hardcoded.
fn errno_overflow_error() -> PyErr {
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

/// Render a [`DfmError`] as the exception CPython raises, byte for byte:
/// the differential compares raised exceptions as values (type **and**
/// message), so a paraphrase is a failure.
fn to_pyerr(py: Python<'_>, e: DfmError) -> PyErr {
    match e {
        DfmError::NegativeIsolationGap { gap } => match pynum_str(py, gap) {
            Ok(s) => PyValueError::new_err(format!("isolation_gap_mm must be >= 0, got {s}")),
            Err(err) => err,
        },
        DfmError::BoardTooNarrow { total_width, n, gap } => {
            match (pynum_str(py, total_width), pynum_str(py, gap)) {
                (Ok(w), Ok(g)) => PyValueError::new_err(format!(
                    "Board too narrow ({w}mm) for {n} isolated pours with {g}mm gaps"
                )),
                (Err(err), _) | (_, Err(err)) => err,
            }
        }
        DfmError::NotAPerfectSquare { count } => {
            PyValueError::new_err(format!("count must be a perfect square, got {count}"))
        }
        // `(-1) ** 0.5` is a complex, and `round` has no complex overload.
        DfmError::ComplexRound => {
            PyTypeError::new_err("type complex doesn't define __round__ method")
        }
        DfmError::PowOverflow => errno_overflow_error(),
        DfmError::IntOverflow => PyOverflowError::new_err(
            "int arithmetic overflowed i64: this port carries Python ints as i64 \
             (see PyNum in packages/temper-drc-rs/src/dfm.rs)",
        ),
        DfmError::RaggedInput(msg) => PyValueError::new_err(msg),
    }
}

// ===========================================================================
// thermal_relief
// ===========================================================================

#[pyfunction]
fn dfm_is_power_net_py(net_name: &str) -> bool {
    dfm::is_power_net(net_name)
}

#[pyfunction]
fn dfm_connects_to_power_plane_py(
    net_name: &str,
    from_layer: &str,
    to_layer: &str,
    plane_layers: Vec<String>,
    plane_nets: Vec<String>,
) -> bool {
    dfm::connects_to_power_plane(net_name, from_layer, to_layer, &plane_layers, &plane_nets)
}

#[pyfunction]
fn dfm_generate_spoke_segments_py(
    center_x: f64,
    center_y: f64,
    pad_w: f64,
    pad_h: f64,
    spoke_count: i64,
    spoke_width: f64,
    clearance_gap: f64,
) -> Vec<((f64, f64), (f64, f64))> {
    dfm::generate_spoke_segments(
        center_x,
        center_y,
        pad_w,
        pad_h,
        spoke_count,
        spoke_width,
        clearance_gap,
    )
}

#[pyfunction]
fn dfm_clamp_to_rect_outline_py(
    py: Python<'_>,
    x: &Bound<'_, PyAny>,
    y: &Bound<'_, PyAny>,
    origin_x: &Bound<'_, PyAny>,
    origin_y: &Bound<'_, PyAny>,
    width: &Bound<'_, PyAny>,
    height: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let (cx, cy) = dfm::clamp_to_rect_outline(
        extract_pynum(x)?,
        extract_pynum(y)?,
        extract_pynum(origin_x)?,
        extract_pynum(origin_y)?,
        extract_pynum(width)?,
        extract_pynum(height)?,
    )
    .map_err(|e| to_pyerr(py, e))?;
    let items = [pynum_into_py(py, cx)?, pynum_into_py(py, cy)?];
    Ok(PyTuple::new(py, items)?.into_any().unbind())
}

// ===========================================================================
// acid_trap_detection
// ===========================================================================

#[pyfunction]
fn dfm_calculate_angle_py(
    py: Python<'_>,
    p1x: f64,
    p1y: f64,
    p2x: f64,
    p2y: f64,
    p3x: f64,
    p3y: f64,
) -> PyResult<f64> {
    dfm::calculate_angle(p1x, p1y, p2x, p2y, p3x, p3y).map_err(|e| to_pyerr(py, e))
}

#[pyfunction]
#[pyo3(signature = (angle, trace_width_mm = 0.2))]
fn dfm_classify_severity_py(angle: f64, trace_width_mm: f64) -> &'static str {
    dfm::classify_severity(angle, trace_width_mm)
}

// ===========================================================================
// power_plane
// ===========================================================================

#[pyfunction]
fn dfm_board_bounds_py(
    py: Python<'_>,
    origin_x: &Bound<'_, PyAny>,
    origin_y: &Bound<'_, PyAny>,
    width: &Bound<'_, PyAny>,
    height: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let (a, b, c, d) = dfm::board_bounds(
        extract_pynum(origin_x)?,
        extract_pynum(origin_y)?,
        extract_pynum(width)?,
        extract_pynum(height)?,
    )
    .map_err(|e| to_pyerr(py, e))?;
    let items = [
        pynum_into_py(py, a)?,
        pynum_into_py(py, b)?,
        pynum_into_py(py, c)?,
        pynum_into_py(py, d)?,
    ];
    Ok(PyTuple::new(py, items)?.into_any().unbind())
}

// ===========================================================================
// copper_balance
// ===========================================================================

#[pyfunction]
fn dfm_via_annular_area_py(diameter: f64, drill: f64) -> f64 {
    dfm::via_annular_area(diameter, drill)
}

#[pyfunction]
fn dfm_layer_is_between_py(from_layer: &str, to_layer: &str, candidate: &str) -> bool {
    dfm::layer_is_between(from_layer, to_layer, candidate)
}

/// `seg_layers` is taken as a borrowed sequence rather than
/// `Vec<String>`: extracting owned `String`s allocates once per vertex,
/// and on the shared corpus (runs of 2-65 vertices) that allocation made
/// the Rust arm **1.42x slower than the Python it replaces**. Borrowing
/// the interned Python `str` payloads for the duration of the call costs
/// nothing and leaves the kernel's comparison unchanged.
#[pyfunction]
fn dfm_segment_run_copper_area_py(
    py: Python<'_>,
    seg_xs: Vec<f64>,
    seg_ys: Vec<f64>,
    seg_layers: &Bound<'_, PyAny>,
    layer_name: &str,
    width_mm: f64,
) -> PyResult<f64> {
    let mut bound: Vec<Bound<'_, PyAny>> = Vec::with_capacity(seg_xs.len());
    for item in seg_layers.try_iter()? {
        bound.push(item?);
    }
    let layers: Vec<&str> = bound
        .iter()
        .map(|s| s.cast::<PyString>().map_err(PyErr::from)?.to_str())
        .collect::<PyResult<_>>()?;
    dfm::segment_run_copper_area(&seg_xs, &seg_ys, &layers, layer_name, width_mm)
        .map_err(|e| to_pyerr(py, e))
}

// ===========================================================================
// annular_ring_check
// ===========================================================================

#[pyfunction]
fn dfm_check_annular_ring_py(
    diameter: f64,
    drill: f64,
    from_layer: &str,
    to_layer: &str,
    via_type: Option<&str>,
    min_annular_ring: f64,
    microvia_ring_mm: f64,
) -> Option<(f64, f64, f64)> {
    dfm::check_annular_ring(
        diameter,
        drill,
        from_layer,
        to_layer,
        via_type,
        min_annular_ring,
        microvia_ring_mm,
    )
}

// ===========================================================================
// teardrop_generation
// ===========================================================================

type PyTeardrop = ((f64, f64), f64, f64, String);

#[pyfunction]
#[expect(
    clippy::too_many_arguments,
    reason = "the flattened call shape is fixed by test_dfm_rust_differential.py"
)]
fn dfm_via_teardrop_py(
    py: Python<'_>,
    via_x: f64,
    via_y: f64,
    diameter: f64,
    from_layer: &str,
    to_layer: &str,
    path_layer: Option<String>,
    coord_xs: Vec<f64>,
    coord_ys: Vec<f64>,
    width_mm: f64,
    length_ratio: f64,
) -> PyResult<Option<PyTeardrop>> {
    let dims = dfm::via_teardrop(
        via_x,
        via_y,
        diameter,
        from_layer,
        to_layer,
        path_layer.as_deref(),
        &coord_xs,
        &coord_ys,
        width_mm,
        length_ratio,
    )
    .map_err(|e| to_pyerr(py, e))?;
    // `path_layer` is threaded back as `Teardrop.layer`; the kernel only
    // gates on it, so the string never leaves this layer.
    Ok(dims.map(|(point, length, width)| (point, length, width, path_layer.unwrap_or_default())))
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Register the DFM kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, pyo3::types::PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(dfm_is_power_net_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_connects_to_power_plane_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_generate_spoke_segments_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_clamp_to_rect_outline_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_calculate_angle_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_classify_severity_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_board_bounds_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_via_annular_area_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_layer_is_between_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_segment_run_copper_area_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_check_annular_ring_py, m)?)?;
    m.add_function(wrap_pyfunction!(dfm_via_teardrop_py, m)?)?;
    Ok(())
}
