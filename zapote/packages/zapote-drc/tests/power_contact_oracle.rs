use serde::Deserialize;
use zapote_drc::manufacturing::Polygon;
use zapote_drc::power_contact::entry;

#[derive(Deserialize)]
struct Fixture {
    trace: Trace,
    pad: Polygon,
    drill: Polygon,
}
#[derive(Deserialize)]
struct Trace {
    start_mm: [f64; 2],
    end_mm: [f64; 2],
    width_mm: f64,
}

fn fixture() -> Fixture {
    serde_json::from_str(include_str!(
        "../../../validation/p1-current/contact-oracle.json"
    ))
    .unwrap()
}

#[test]
fn native_rotated_oval_and_oblong_drill_provide_contact_certificate() {
    let f = fixture();
    // Independent analytical R(-30deg) position of local (2,1), plus the
    // projected extents of a 6x3 oval. A zero/+30 pose cannot pass this probe.
    for (axis, center, span) in [(0, 22.2320508076, 5.5980762114), (1, 19.8660254038, 4.5)] {
        let lo = f
            .pad
            .vertices_mm
            .iter()
            .map(|p| p[axis])
            .fold(f64::INFINITY, f64::min);
        let hi = f
            .pad
            .vertices_mm
            .iter()
            .map(|p| p[axis])
            .fold(f64::NEG_INFINITY, f64::max);
        assert!(((lo + hi) / 2. - center).abs() < 0.002);
        assert!((hi - lo - span).abs() < 0.003);
    }
    let result = entry(
        std::slice::from_ref(&f.pad),
        Some(&f.drill),
        f.trace.start_mm,
        f.trace.end_mm,
        f.trace.width_mm,
    )
    .unwrap();
    assert!(result.certified_chord_mm >= f.trace.width_mm - 1e-9);
    assert!(result.full_width_chord_observed);
    assert!(result.sections_examined > 0);
    let void = entry(
        std::slice::from_ref(&f.pad),
        Some(&f.drill),
        [22.2, 19.86],
        [22.25, 19.86],
        0.05,
    )
    .unwrap();
    assert_eq!(void.certified_chord_mm, 0.);

    // An independently chosen 3.05 mm trace exceeds the native 3 mm pad
    // minor dimension, so the real entry routine must reject full width.
    let mutated = entry(
        &[f.pad],
        Some(&f.drill),
        f.trace.start_mm,
        f.trace.end_mm,
        3.05,
    )
    .unwrap();
    assert!(!mutated.full_width_chord_observed);
}
