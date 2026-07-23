// CongestionTensor — PathFinder-style per-cell congestion cost for A*
//
// Python reference: temper_placer/router_v6/congestion_tensor.py
//
// Stores per-cell usage counts in a flat Vec<f32> and computes a
// logarithmic cost function: min(max_cost, 1.0 + ln(1.0 + usage)).

use pyo3::prelude::*;

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
        let idx = row * self.cols + col;
        if idx < self.data.len() { self.data[idx] += weight; }
    }

    #[pyo3(signature = (row, col))]
    pub fn cost(&self, row: usize, col: usize) -> f32 {
        let idx = row * self.cols + col;
        if idx >= self.data.len() { return 1.0; }
        let raw = self.data[idx];
        if raw <= 0.0 { 1.0 }
        else {
            let cost = 1.0_f32 + raw.ln_1p();
            if cost > self.max_cost { self.max_cost } else { cost }
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
}

#[cfg(test)]
mod tests {
    use super::*;

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
        let ct = CongestionTensor {
            data: vec![1e6_f32, 0.0], rows: 1, cols: 2, max_cost: 50.0, weight: 1.0,
        };
        assert_eq!(ct.cost(0, 0), 50.0);
    }

    #[test]
    fn test_reset_zeros_all() {
        let mut ct = CongestionTensor::new(1, 3, 100.0, 1.0);
        ct.increment(0, 0, 5.0);
        ct.reset();
        assert!(ct.data.iter().all(|&v| v == 0.0));
    }
}
