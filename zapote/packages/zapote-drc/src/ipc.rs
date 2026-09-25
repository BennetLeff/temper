//! Small IPC-2221 scalar used by the local escape eligibility rule.
//!
//! Provenance: copied from `packages/temper-drc-rs/src/ipc.rs` (the
//! `estimate_trace_current` kernel), whose source hash is recorded in
//! `zapote/ports.toml`. Zapote keeps this independent copy so the RTD
//! validator has no runtime dependency on the donor crate.

/// Estimate external-layer trace capacity using the IPC-2221 scalar.
pub(crate) fn external_capacity_a(width_mm: f64, copper_thickness_um: f64) -> f64 {
    // Physical dimensions are already supplied; avoid approximate ounce
    // conversions inherited from the donor. One mil is exactly 25.4 um.
    let width_mils = width_mm / 0.0254;
    let thickness_mils = copper_thickness_um / 25.4;
    let area_mils2 = width_mils * thickness_mils;
    0.048 * 20.0_f64.powf(0.44) * area_mils2.powf(0.725)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seven_tenths_millimeter_seventy_um_carries_low_current_branch() {
        assert!(external_capacity_a(0.7, 70.0) > 0.5);
    }

    #[test]
    fn capacity_increases_with_width_and_finished_thickness() {
        let narrow = external_capacity_a(0.25, 70.0);
        let wide = external_capacity_a(0.5, 70.0);
        let thick = external_capacity_a(0.25, 105.0);
        assert!(wide > narrow);
        assert!(thick > narrow);
    }
}
