// Wave 4, spatial-tier-2 unit: the `estimated_traces` estimate inside
// `router_v6/layer_capacity.py`'s `calculate_layer_capacity`.
//
// The formula, transcribed verbatim:
//
//     trace_pitch = min_trace_width + 2 * min_clearance
//     if avg_channel_width > 0 and trace_pitch > 0:
//         traces_per_channel = int(avg_channel_width / trace_pitch)
//         estimated_traces = max(1, int(free_cells * 0.01 * traces_per_channel))
//     else:
//         estimated_traces = 0
//
// Bit-exactness notes:
// * `avg_channel_width / trace_pitch` is IEEE f64 division; `int()` in
//   Python truncates toward zero, matching `f64 as i64` in Rust.
// * `free_cells * 0.01` is `int * float` -> `(free_cells as f64) * 0.01`;
//   `0.01` is the same f64 literal in both languages; the two-op chain
//   order is preserved exactly (class B7).
// * `int(inf)` raises OverflowError and `int(nan)` raises ValueError in
//   Python; the kernel raises the corresponding error at the pyo3
//   boundary.  A finite ratio >= 2^63 would be an exact bigint in Python
//   while `as i64` saturates here — physically unreachable (it needs an
//   average channel width on the order of 1e18 mm), recorded in
//   VERIFICATION.md.

/// Overflow marker for `int(inf)` — mirrored at the pyo3 boundary as
/// `OverflowError`.  The `int(nan)` ValueError path is unreachable: the
/// reference's `avg_channel_width > 0 and trace_pitch > 0` guard is false
/// for a NaN operand (IEEE), so a NaN ratio can never reach `int()`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KernelError {
    Overflow,
}

/// `estimated_traces` from the grid/width scalars.
pub fn estimate_traces(
    free_cells: i64,
    avg_channel_width: f64,
    min_trace_width: f64,
    min_clearance: f64,
) -> Result<i64, KernelError> {
    let trace_pitch = min_trace_width + 2.0 * min_clearance;
    if avg_channel_width > 0.0 && trace_pitch > 0.0 {
        let ratio = avg_channel_width / trace_pitch;
        if ratio.is_infinite() {
            return Err(KernelError::Overflow);
        }
        let traces_per_channel = ratio as i64;
        let raw = (free_cells as f64) * 0.01 * (traces_per_channel as f64);
        if raw.is_infinite() {
            return Err(KernelError::Overflow);
        }
        let estimated = raw as i64;
        Ok(1_i64.max(estimated))
    } else {
        Ok(0)
    }
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// pyo3 surface for `estimate_traces`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn estimate_traces_py(
    free_cells: i64,
    avg_channel_width: f64,
    min_trace_width: f64,
    min_clearance: f64,
) -> PyResult<i64> {
    temper_py_bridge::catch_unwind(move || estimate_traces(free_cells, avg_channel_width, min_trace_width, min_clearance))
        .map_err(temper_py_bridge::panic_to_err)?
        .map_err(|KernelError::Overflow| {
            pyo3::exceptions::PyOverflowError::new_err("cannot convert float infinity to integer")
        })
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(estimate_traces_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn typical_estimate() {
        // avg 5.0, pitch 0.381 -> 13 traces/channel; free 8000 -> 1040.
        assert_eq!(estimate_traces(8000, 5.0, 0.127, 0.127), Ok(1040));
    }

    #[test]
    fn max_one_floor() {
        // free 50 -> 50*0.01*1 = 0.5 -> 0 -> clamped to 1.
        assert_eq!(estimate_traces(50, 0.381, 0.127, 0.127), Ok(1));
        // free 1 -> 0.01 -> 0 -> 1.
        assert_eq!(estimate_traces(1, 10.0, 0.127, 0.127), Ok(1));
    }

    #[test]
    fn zero_edges() {
        assert_eq!(estimate_traces(100, 0.0, 0.127, 0.127), Ok(0));
        assert_eq!(estimate_traces(100, 2.0, 0.0, 0.0), Ok(0));
        assert_eq!(estimate_traces(100, 2.0, 0.1, -0.2), Ok(0)); // negative pitch
    }

    #[test]
    fn inf_and_nan_raise_or_skip() {
        // inf avg width passes the > 0 guard and int(inf) raises OverflowError.
        assert_eq!(estimate_traces(100, f64::INFINITY, 0.127, 0.127), Err(KernelError::Overflow));
        // NaN avg width fails the reference's `> 0` guard -> the else branch,
        // exactly as Python: `nan > 0` is False -> estimated_traces = 0.
        assert_eq!(estimate_traces(100, f64::NAN, 0.127, 0.127), Ok(0));
    }
}
