//! Small, fail-closed power-stage sanity models used by Zapote ERC.
//! These are analytical checks, not component qualification or SPICE.
//! (The passive voltage-doubler simulation that also lived here was archived
//! with the Rev38/doubler-era work: tag archive/zapote-coil-intake-2026-09-25.)

#[derive(Debug, Clone, PartialEq)]
pub enum ModelError {
    InvalidInput(&'static str),
}

fn finite_positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DeadTimeSummary {
    pub nominal_ns: f64,
    pub min_ns: f64,
    pub max_ns: f64,
}

/// TI's approximate DT equation. Scale is an explicit characterization
/// envelope assumption, not a datasheet guarantee.
pub fn dead_time_corners(
    nominal_kohm: f64,
    tolerance: f64,
    tcr_ppm: f64,
    temperatures_c: &[f64],
    scale: (f64, f64),
) -> Result<DeadTimeSummary, ModelError> {
    if !finite_positive(nominal_kohm)
        || !tolerance.is_finite()
        || tolerance < 0.0
        || tolerance >= 1.0
        || !tcr_ppm.is_finite()
        || tcr_ppm < 0.0
        || temperatures_c.is_empty()
        || !scale.0.is_finite()
        || !scale.1.is_finite()
        || scale.0 <= 0.0
        || scale.1 < scale.0
    {
        return Err(ModelError::InvalidInput("invalid DT corner inputs"));
    }
    let nominal = 8.6 * nominal_kohm + 13.0;
    let mut min: f64 = f64::INFINITY;
    let mut max: f64 = 0.0;
    for &temp in temperatures_c {
        if !temp.is_finite() || !(-40.0..=125.0).contains(&temp) {
            return Err(ModelError::InvalidInput("temperature must be finite"));
        }
        for tolerance_sign in [-1.0, 1.0] {
            for tcr_sign in [-1.0, 1.0] {
                let r = nominal_kohm
                    * (1.0 + tolerance_sign * tolerance)
                    * (1.0 + tcr_sign * tcr_ppm * 1e-6 * (temp - 25.0));
                if !r.is_finite() || !(1.7..=100.0).contains(&r) {
                    return Err(ModelError::InvalidInput(
                        "DT resistance corner is outside the equation's 1.7–100 kohm range",
                    ));
                }
                min = min.min((8.6 * r + 13.0) * scale.0);
                max = max.max((8.6 * r + 13.0) * scale.1);
            }
        }
    }
    Ok(DeadTimeSummary {
        nominal_ns: nominal,
        min_ns: min,
        max_ns: max,
    })
}
