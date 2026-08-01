// CongestionTensor — PathFinder-style per-cell congestion cost for A*
//
// Python reference: temper_placer/router_v6/congestion_tensor.py
//
// Stores per-cell usage counts in a flat Vec<f32> and computes a
// logarithmic cost function: min(max_cost, 1.0 + ln(1.0 + usage)).

use pyo3::prelude::*;
use pyo3::types::PyBytes;

#[pyclass(name = "CongestionTensor")]
pub struct CongestionTensor {
    #[pyo3(get)]
    data: Vec<f32>,
    #[pyo3(get)]
    rows: usize,
    #[pyo3(get)]
    cols: usize,
    #[pyo3(get, set)]
    max_cost: f32,
    #[pyo3(get, set)]
    weight: f32,
}

#[pymethods]
impl CongestionTensor {
    #[new]
    #[pyo3(signature = (rows, cols, max_cost = 100.0_f32, weight = 1.0_f32))]
    pub fn new(rows: usize, cols: usize, max_cost: f32, weight: f32) -> Self {
        Self { data: vec![0.0_f32; rows * cols], rows, cols, max_cost, weight }
    }

    #[staticmethod]
    #[pyo3(signature = (rows, cols, max_cost = 100.0_f32, weight = 1.0_f32))]
    pub fn zeros(rows: usize, cols: usize, max_cost: f32, weight: f32) -> Self {
        Self::new(rows, cols, max_cost, weight)
    }

    #[pyo3(signature = (row, col, weight = 1.0_f32))]
    pub fn increment(&mut self, row: usize, col: usize, weight: f32) {
        // Per-dimension bounds (same rationale as increment_cells): a flat
        // idx < len check alone would fold (0, 2) on a 2x2 grid onto
        // cell (1, 0). The Python original raised IndexError; we sanitize
        // to a no-op.
        if row >= self.rows || col >= self.cols { return; }
        self.data[row * self.cols + col] += weight;
    }

    // Batch increment over pre-mapped (row, col) pairs. The Python wrapper
    // performs the world->grid mapping (grid.world_to_grid is a Python
    // method) and batches here instead of calling increment() per cell
    // across the FFI boundary.
    // Batch increment over pre-mapped (row, col) pairs. The Python wrapper
    // performs the world->grid mapping (grid.world_to_grid is a Python
    // method) and batches here instead of calling increment() per cell
    // across the FFI boundary. Signed pairs: the mapper can legitimately
    // return negative coords for out-of-board cells, which are skipped
    // here (mirroring the original numpy bounds check).
    #[pyo3(signature = (pairs, weight = 1.0_f32))]
    pub fn increment_cells(&mut self, pairs: Vec<(i64, i64)>, weight: f32) {
        for (row, col) in pairs {
            if row < 0 || col < 0 {
                continue;
            }
            self.increment(row as usize, col as usize, weight);
        }
    }

    // Computed in f64, mirroring the Python oracle exactly (float64 raw,
    // math.log1p, min against max_cost), then returned as f32: the f32 cast
    // of a correctly-rounded f64 result is the correctly-rounded f32, so
    // this is bit-identical to np.float32(python_cost(...)). A pure f32
    // ln_1p chain would differ at the max_cost clamp (1 ulp band).
    #[pyo3(signature = (row, col))]
    pub fn cost(&self, row: usize, col: usize) -> f32 {
        // Per-dimension bounds (same rationale as increment): the Python
        // original raised IndexError; we sanitize to the cost floor.
        if row >= self.rows || col >= self.cols { return 1.0; }
        let raw = self.data[row * self.cols + col] as f64;
        if raw <= 0.0 { 1.0 }
        else {
            let cost = 1.0_f64 + raw.ln_1p();
            if cost > self.max_cost as f64 { self.max_cost } else { cost as f32 }
        }
    }

    #[pyo3(signature = (factor = 0.95_f32))]
    pub fn decay(&mut self, factor: f32) {
        for v in &mut self.data { *v *= factor; }
    }

    pub fn reset(&mut self) { self.data.fill(0.0); }

    #[pyo3(signature = (row, col))]
    pub fn get_usage(&self, row: usize, col: usize) -> f32 {
        let idx = row * self.cols + col;
        if idx < self.data.len() { self.data[idx] } else { 0.0 }
    }

    // Bulk-overwrite the storage (used by the Python wrapper's array-based
    // constructor, which the pre-migration dataclass public API exposed).
    // Infallible by design: the wrapper validates the length and raises
    // ValueError there; a mismatch here is a wrapper bug, caught by the
    // debug assert. (Avoids pyo3 exceptions in a crate that otherwise
    // raises none — pyo3 error machinery breaks `cargo test` linking for
    // extension-module crates without libpython.)
    #[pyo3(signature = (flat))]
    pub fn load_flat(&mut self, flat: Vec<f32>) {
        debug_assert_eq!(flat.len(), self.data.len());
        let n = flat.len().min(self.data.len());
        self.data[..n].copy_from_slice(&flat[..n]);
    }

    // Expose the raw float32 storage as bytes so the Python wrapper can
    // build a zero-copy numpy view (np.frombuffer). The wrapper MUST NOT
    // cache this buffer: per-net increment_path mutations happen between
    // searches, so every access re-copies from Rust (no-cache invariant).
    pub fn to_flat_bytes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        PyBytes::new_with(py, self.data.len() * 4, |b| {
            for (chunk, v) in b.chunks_exact_mut(4).zip(&self.data) {
                chunk.copy_from_slice(&v.to_le_bytes());
            }
            Ok(())
        })
    }

    /// Pure-Rust byte serialization of the storage (row-major little-endian
    /// float32) — kept separate from the pyo3 boundary so unit tests can
    /// exercise it without linking libpython.
    fn flat_bytes(&self) -> Vec<u8> {
        let mut buf = Vec::with_capacity(self.data.len() * 4);
        for v in &self.data {
            buf.extend_from_slice(&v.to_le_bytes());
        }
        buf
    }
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn test_load_flat_overwrites_storage() {
        let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
        ct.increment(0, 0, 5.0);
        ct.load_flat(vec![1.0, 2.0, 3.0, 4.0]);
        assert_eq!(ct.data, vec![1.0, 2.0, 3.0, 4.0]);
    }

    #[test]
    fn test_cost_zero_usage_returns_one() {
        let ct = CongestionTensor::new(2, 2, 100.0, 1.0);
        assert_eq!(ct.cost(0, 0), 1.0);
    }

    #[test]
    fn test_increment_adds_to_cell() {
        let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
        ct.increment(0, 0, 1.0);
        assert!((ct.cost(0, 0) - (1.0_f32 + 2.0_f32.ln())).abs() < 1e-5);
    }

    #[test]
    fn test_cost_respects_cap() {
        // Need raw > e^49 ≈ 1.9e21 to exceed cap of 50. Use f32::MAX.
        let mut ct = CongestionTensor::new(1, 2, 50.0, 1.0);
        ct.increment(0, 0, f32::MAX);
        assert_eq!(ct.cost(0, 0), 50.0);
    }

    #[test]
    fn test_reset_zeros_all() {
        let mut ct = CongestionTensor::new(1, 3, 100.0, 1.0);
        ct.increment(0, 0, 5.0);
        ct.reset();
        assert!(ct.data.iter().all(|&v| v == 0.0));
    }

    #[test]
    fn test_increment_cells_batch() {
        let mut ct = CongestionTensor::new(2, 3, 100.0, 1.0);
        ct.increment_cells(vec![(0, 0), (1, 2), (0, 0)], 1.0);
        assert_eq!(ct.data[0], 2.0);
        assert_eq!(ct.data[5], 1.0);
        assert_eq!(ct.data[1], 0.0);
    }

    #[test]
    fn test_increment_cells_skips_out_of_bounds() {
        let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
        ct.increment_cells(vec![(0, 0), (2, 0), (0, 2), (9, 9)], 1.0);
        assert_eq!(ct.data[0], 1.0);
        assert_eq!(ct.data.iter().sum::<f32>(), 1.0);
    }

    #[test]
    fn test_increment_cells_skips_negative_coords() {
        // world_to_grid can return negative coords for out-of-board cells.
        let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
        ct.increment_cells(vec![(-1, 0), (0, -3), (1, 1)], 1.0);
        assert_eq!(ct.data.iter().sum::<f32>(), 1.0);
        assert_eq!(ct.data[3], 1.0);
    }

    #[test]
    fn test_increment_cells_cannot_overflow_into_another_cell() {
        // (0, 2) on a 2x2 grid must be skipped, not folded onto idx 2.
        let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
        ct.increment_cells(vec![(0, 2), (1, 1)], 1.0);
        assert_eq!(ct.data[0], 0.0);
        assert_eq!(ct.data[3], 1.0);
    }

    #[test]
    fn test_increment_cells_applies_weight() {
        let mut ct = CongestionTensor::new(1, 1, 100.0, 1.0);
        ct.increment_cells(vec![(0, 0), (0, 0)], 0.5);
        assert_eq!(ct.data[0], 1.0);
    }

    #[test]
    fn test_to_flat_bytes_roundtrip() {
        let mut ct = CongestionTensor::new(2, 2, 100.0, 1.0);
        ct.increment(1, 0, 3.5);
        let bytes = ct.flat_bytes();
        assert_eq!(bytes.len(), 4 * 4);
        let mut vals = Vec::new();
        for chunk in bytes.chunks_exact(4) {
            vals.push(f32::from_le_bytes(chunk.try_into().unwrap()));
        }
        assert_eq!(vals, ct.data);
    }

    #[test]
    // 3.14159 in the loop below is deliberate test data (~π but not exactly π),
    // not a constant-in-place-of-PI slip.
    #[expect(clippy::approx_constant, reason = "intentional ~π test input value")]
    fn test_cost_computed_in_f64_matches_python_oracle() {
        // Python oracle: raw = float(array[row, col]); if raw <= 0: 1.0;
        // else min(max_cost, 1.0 + math.log1p(raw)). Rust must be
        // bit-identical to np.float32 of that f64 result.
        let mut ct = CongestionTensor::new(1, 1, 100.0, 1.0);
        for raw in [1.0f32, 0.001, 1e-7, 1e-8, 3.14159, 17.0, 1e6] {
            ct.data[0] = raw;
            let expect = if raw <= 0.0 {
                1.0f32
            } else {
                let cost = 1.0f64 + (raw as f64).ln_1p();
                (if cost > 100.0f64 { 100.0f64 } else { cost }) as f32
            };
            assert_eq!(ct.cost(0, 0), expect, "raw={raw}");
        }
    }

    #[test]
    fn test_cost_clamp_band_is_exact_at_max_cost() {
        // The f32-vs-f64 min mismatch band: raw just below the value that
        // pushes 1.0 + ln1p(raw) to max_cost must clamp to max_cost exactly
        // (f64 min then f32 cast), never to the next f32 down.
        let mut ct = CongestionTensor::new(1, 1, 2.0, 1.0);
        ct.data[0] = 1.71828; // ln1p(1.71828) < 1.0 by ~1e-5
        let near = ct.cost(0, 0);
        assert!(near > 1.9999 && near < 2.0, "near={near}");
        ct.data[0] = 1.7183; // ln1p(1.7183) > 1.0 -> clamp
        assert_eq!(ct.cost(0, 0), 2.0);
        ct.data[0] = 1e6;
        assert_eq!(ct.cost(0, 0), 2.0);
    }
}
