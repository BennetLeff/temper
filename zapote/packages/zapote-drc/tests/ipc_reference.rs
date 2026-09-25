//! IPC-2221 scalar verification, not a temperature or IPC-2152 certificate.
//! Reference: KiCad 5.1 PCB Calculator manual, Track-Width formula:
//! https://docs.kicad.org/5.1/en/pcb_calculator/pcb_calculator.pdf
//! I=0.048 * deltaT^0.44 * area_mil_squared^0.725 (external copper).
use zapote_drc::power_contact::capacity_a;

#[test]
fn exact_mil_dimensions_match_published_scalar() {
    // 1 mil = exactly 0.0254 mm = 25.4 um. No oz conversion belongs
    // between an already specified physical thickness and copper area.
    for (width_mil, thickness_mil) in [(1_f64, 1_f64), (10., 1.), (100., 2.), (160., 3.)] {
        let expected = 0.048 * 20_f64.powf(0.44) * (width_mil * thickness_mil).powf(0.725);
        let actual = capacity_a(width_mil * 0.0254, thickness_mil * 25.4).unwrap();
        assert!(
            (actual - expected).abs() < 1e-12,
            "width={width_mil} mil, thickness={thickness_mil} mil: {actual} != {expected}"
        );
    }
}
