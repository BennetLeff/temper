// FuseTrace — IPC-2152 trace width for fuse elements, const-evaluated.
//
// PCB fuse traces must be wide enough to survive the fault current until
// the fuse clears. IPC-2152 provides the standard trace width calculation:
//
//   I = k × ΔT^0.44 × A^0.725
//
// where I = current, k = 0.048 (external) / 0.024 (internal),
// ΔT = temperature rise in °C, A = cross-sectional area in mils².
//
// FuseTrace<const I2T: f64, const FAULT_I: f64> would ideally use const
// generics for compile-time width assertions, but Rust's const generics
// do not yet support f64. Instead, we provide const-evaluable helper
// functions and a struct with runtime validate().
//
// At runtime: FuseTrace::validate() computes the required width via
// ipc_2152_width_mm() and compares against actual_width_mm.
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

/// IPC-2152 external conductor derating constant (k).
pub const K_EXTERNAL: f64 = 0.048;
/// IPC-2152 internal conductor derating constant (k).
pub const K_INTERNAL: f64 = 0.024;

/// Calculate the minimum trace width for a given current per IPC-2152.
///
/// IPC-2152: I = k × ΔT^0.44 × A^0.725
///
/// Note: This is not `const fn` because `f64::powf` is not stable as a const fn
/// in Rust. Use this at runtime for width calculations.
///
/// # Arguments
/// * `current_a` - The fault current in amperes
/// * `copper_weight_oz` - Copper weight in oz/ft² (e.g., 1.0, 2.0)
/// * `max_temp_rise_c` - Maximum allowed temperature rise in °C (default 100°C for fuses)
/// * `is_external` - Whether the trace is on an external layer (true) or internal (false)
///
/// # Returns
/// The minimum trace width in millimeters.
pub fn ipc_2152_width_mm(
    current_a: f64,
    copper_weight_oz: f64,
    max_temp_rise_c: f64,
    is_external: bool,
) -> f64 {
    let k = if is_external { K_EXTERNAL } else { K_INTERNAL };
    // I = k × ΔT^0.44 × A^0.725
    // A = (I / (k × ΔT^0.44))^(1/0.725)
    // Using the same approach as the spec but with explicit steps.
    let temp_factor = max_temp_rise_c.powf(0.44);
    let area_mils2 = (current_a / (k * temp_factor)).powf(1.0 / 0.725);
    // A = width_mils × thickness_mils
    // thickness_mils = copper_weight_oz × 1.37 (1oz = 1.37 mils)
    let thickness_mils = copper_weight_oz * 1.37;
    let width_mils = area_mils2 / thickness_mils;
    // Convert mils to mm (1 mil = 0.0254 mm)
    width_mils * 0.0254
}

/// A PCB trace designed to act as a fuse element.
///
/// The trace is intentionally narrow to act as a fuse, clearing during
/// a fault condition. It must be wide enough to carry the fault current
/// for the required duration without exceeding the temperature rise.
pub struct FuseTrace {
    /// Net name of the fuse trace.
    pub net: String,
    /// I²t rating of the fuse element in A²s.
    pub i2t_rating_a2s: f64,
    /// Maximum fault current the trace must survive (A).
    pub fault_current_a: f64,
    /// Duration of the fault condition (ms).
    pub fault_duration_ms: f64,
    /// Actual trace width on the board (mm).
    pub actual_width_mm: f64,
}

impl FuseTrace {
    /// Validate the fuse trace width against IPC-2152 requirements.
    ///
    /// Computes the minimum required width for the given fault current
    /// with a 100°C temperature rise (standard for fuse elements) and
    /// compares against the actual trace width.
    ///
    /// # Arguments
    /// * `copper_oz` - Copper weight in oz/ft²
    /// * `is_external` - Whether the trace is on an external layer
    ///
    /// # Returns
    /// * `Ok(required_width_mm)` if the actual width meets or exceeds requirements
    /// * `Err(...)` if the trace is undersized, with required vs actual dimensions
    pub fn validate(&self, copper_oz: f64, is_external: bool) -> Result<f64, Vec<String>> {
        let required = ipc_2152_width_mm(self.fault_current_a, copper_oz, 100.0, is_external);
        if self.actual_width_mm < required {
            Err(vec![format!(
                "Fuse trace {} undersized: {:.2}mm actual vs {:.2}mm required for I²t={}A²s, {}A fault",
                self.net, self.actual_width_mm, required, self.i2t_rating_a2s, self.fault_current_a
            )])
        } else {
            Ok(required)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ipc_2152_external_baseline() {
        // 1A, 1oz, 10°C rise, external — should produce a reasonable width (~0.30mm).
        let w = ipc_2152_width_mm(1.0, 1.0, 10.0, true);
        assert!(w > 0.0);
        assert!(w < 2.0); // sanity: not astronomically large
    }

    #[test]
    fn test_ipc_2152_internal_narrower() {
        // Internal trace (lower k) → wider for same current.
        let external = ipc_2152_width_mm(1.0, 1.0, 10.0, true);
        let internal = ipc_2152_width_mm(1.0, 1.0, 10.0, false);
        assert!(internal > external);
    }

    #[test]
    fn test_fuse_trace_validate_ok() {
        // 5A fault, 1oz, 100°C rise: requires ~0.69mm — use 1.0mm to pass
        let trace = FuseTrace {
            net: "FUSE1".into(),
            i2t_rating_a2s: 10.0,
            fault_current_a: 5.0,
            fault_duration_ms: 100.0,
            actual_width_mm: 1.0, // generous for 5A
        };
        let result = trace.validate(1.0, true);
        assert!(result.is_ok());
    }

    #[test]
    fn test_fuse_trace_validate_undersized() {
        // 10A fault, 1oz, 100°C rise: requires ~1.79mm — use 0.5mm to fail
        let trace = FuseTrace {
            net: "FUSE1".into(),
            i2t_rating_a2s: 50.0,
            fault_current_a: 10.0,
            fault_duration_ms: 100.0,
            actual_width_mm: 0.5, // undersized for 10A
        };
        let result = trace.validate(1.0, true);
        assert!(result.is_err());
        let errs = result.unwrap_err();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("FUSE1"));
        assert!(errs[0].contains("undersized"));
    }

    #[test]
    fn test_fuse_trace_exact_boundary() {
        // At exactly the required width — should pass.
        let required = ipc_2152_width_mm(5.0, 1.0, 100.0, true);
        let trace = FuseTrace {
            net: "FUSE2".into(),
            i2t_rating_a2s: 10.0,
            fault_current_a: 5.0,
            fault_duration_ms: 100.0,
            actual_width_mm: required,
        };
        let result = trace.validate(1.0, true);
        assert!(result.is_ok());
    }
}
