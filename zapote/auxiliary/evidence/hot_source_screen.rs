//! Static feasibility screen for the proposed IRM-20-15 HOT source.
//!
//! Run: `rustc --edition=2021 --test zapote/auxiliary/evidence/hot_source_screen.rs -o /tmp/hot_source_screen && /tmp/hot_source_screen`
//! The screen never certifies fault-output peak, gate shutdown or an installed circuit.

const NOMINAL_V: f64 = 15.0;
const TOLERANCE: f64 = 0.025;
const RIPPLE_PP_V: f64 = 0.2;
const TEMP_COEFFICIENT_PER_C: f64 = 0.0003;
const AUX_MIN_V: f64 = 14.25;
const AUX_MAX_V: f64 = 15.75;
const RATED_SOURCE_A: f64 = 1.4;

#[derive(Debug, PartialEq)]
struct Screen {
    source_low_v: f64,
    source_high_v: f64,
    max_allowed_drop_v: f64,
    unresolved: Vec<&'static str>,
    violations: Vec<&'static str>,
}

#[derive(Clone, Copy)]
struct Inputs {
    local_temp_c: Option<f64>,
    total_run_a: Option<f64>,
    startup_peak_a: Option<f64>,
    complete_path_resistance_ohm: Option<f64>,
    fault_peak_at_driver_v: Option<f64>,
    permitted_driver_peak_v: Option<f64>,
    fed_before_run: Option<bool>,
}

/// Ideal closed-loop feedback-only bounds for the proposed 24 V to 15 V buck.
/// No line/load transient, ripple, path drop or fault behavior is included.
fn buck_feedback_window(top_to_bottom_ratio: f64, resistor_deviation: f64) -> (f64, f64) {
    let low_ratio = top_to_bottom_ratio * (1.0 - resistor_deviation) / (1.0 + resistor_deviation);
    let high_ratio = top_to_bottom_ratio * (1.0 + resistor_deviation) / (1.0 - resistor_deviation);
    (0.985 * (1.0 + low_ratio), 1.015 * (1.0 + high_ratio))
}

fn screen(input: Inputs) -> Screen {
    let mut unresolved = Vec::new();
    let mut violations = Vec::new();
    let temp_delta = match input.local_temp_c {
        Some(temp) if (0.0..=50.0).contains(&temp) => (temp - 25.0).abs(),
        Some(_) => {
            unresolved.push("temperature outside published coefficient interval 0-50 C");
            0.0
        }
        None => {
            unresolved.push("local module temperature");
            0.0
        }
    };

    // An entire 200 mVpp is put on either adverse end. This is an explicitly
    // conservative screen, not a guaranteed terminal waveform or peak.
    let deviation = NOMINAL_V * (TOLERANCE + TEMP_COEFFICIENT_PER_C * temp_delta) + RIPPLE_PP_V;
    let source_low_v = NOMINAL_V - deviation;
    let source_high_v = NOMINAL_V + deviation;
    let max_allowed_drop_v = source_low_v - AUX_MIN_V;

    if source_high_v > AUX_MAX_V {
        violations.push("static source high exceeds protected AUX operating ceiling");
    }
    if max_allowed_drop_v <= 0.0 {
        violations.push("static source low leaves no downstream voltage-drop budget");
    }
    match input.total_run_a {
        Some(current) if current >= 0.0 && current <= RATED_SOURCE_A => {}
        Some(_) => violations.push("total run current exceeds source rating or is invalid"),
        None => unresolved.push("complete run current including HOT logic5 input"),
    }
    match input.startup_peak_a {
        Some(current) if current >= 0.0 => {
            // A nameplate continuous-current rating is not an allowed peak.
            let _ = current;
            unresolved.push("source startup current-time envelope and load-charge waveform");
        }
        Some(_) => violations.push("startup peak current is invalid"),
        None => unresolved.push("startup peak current and duration"),
    }
    match (input.total_run_a, input.complete_path_resistance_ohm) {
        (Some(current), Some(resistance)) if current >= 0.0 && resistance >= 0.0 => {
            if current * resistance >= max_allowed_drop_v {
                violations.push("source-to-consumer resistive drop uses full low-voltage margin");
            }
        }
        (_, Some(resistance)) if resistance < 0.0 => {
            violations.push("path resistance is invalid");
        }
        _ => unresolved.push("complete cutoff FET, shunt, copper and cable drop"),
    }
    match (input.fault_peak_at_driver_v, input.permitted_driver_peak_v) {
        (Some(peak), Some(limit)) if peak >= 0.0 && limit >= 0.0 => {
            if peak > limit {
                violations.push("fault peak exceeds approved driver supply limit");
            }
        }
        _ => unresolved.push("measured fault peak and approved driver supply limit"),
    }
    match input.fed_before_run {
        Some(true) => {}
        Some(false) => violations.push("source input depends on PFC RUN"),
        None => unresolved.push("constructed pre-RUN AC input branch"),
    }

    Screen {
        source_low_v,
        source_high_v,
        max_allowed_drop_v,
        unresolved,
        violations,
    }
}

fn main() {
    let candidate = screen(Inputs {
        local_temp_c: Some(50.0),
        total_run_a: None,
        startup_peak_a: None,
        complete_path_resistance_ohm: None,
        fault_peak_at_driver_v: None,
        permitted_driver_peak_v: None,
        fed_before_run: None,
    });
    println!("IRM-20-15 conditional static screen at 50 C local: {candidate:#?}");
    println!("decision: INDETERMINATE; missing load, branch, dynamic fault and physical data");
    let (buck_low, buck_high) = buck_feedback_window(14.0, 0.001);
    println!(
        "IRM-20-24 + LMR36015FBRNXT ideal feedback-only screen: {buck_low:.5}..{buck_high:.5} V"
    );
    println!("decision: INDETERMINATE; buck, cutoff, load and fault waveforms remain unbounded");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn specimen() -> Inputs {
        Inputs {
            local_temp_c: Some(50.0),
            total_run_a: Some(0.5),
            startup_peak_a: None,
            complete_path_resistance_ohm: Some(0.1),
            fault_peak_at_driver_v: None,
            permitted_driver_peak_v: None,
            fed_before_run: Some(true),
        }
    }

    #[test]
    fn fifty_degree_screen_leaves_only_sixty_two_point_five_millivolts() {
        let result = screen(specimen());
        assert!((result.max_allowed_drop_v - 0.0625).abs() < 1e-9);
    }

    #[test]
    fn plausible_series_drop_can_consume_all_lower_margin() {
        let mut input = specimen();
        input.complete_path_resistance_ohm = Some(0.125);
        let result = screen(input);
        assert!(result
            .violations
            .contains(&"source-to-consumer resistive drop uses full low-voltage margin"));
    }

    #[test]
    fn unknown_total_load_cannot_be_promoted_from_partial_subtotal() {
        let mut input = specimen();
        input.total_run_a = None;
        let result = screen(input);
        assert!(result
            .unresolved
            .contains(&"complete run current including HOT logic5 input"));
    }

    #[test]
    fn current_nameplate_does_not_establish_startup_peak() {
        let result = screen(specimen());
        assert!(result
            .unresolved
            .contains(&"startup peak current and duration"));
    }

    #[test]
    fn nominally_adequate_source_must_exist_before_run() {
        let mut input = specimen();
        input.fed_before_run = Some(false);
        let result = screen(input);
        assert!(result
            .violations
            .contains(&"source input depends on PFC RUN"));
    }

    #[test]
    fn absent_fault_waveform_is_not_an_overvoltage_pass() {
        let result = screen(specimen());
        assert!(result
            .unresolved
            .contains(&"measured fault peak and approved driver supply limit"));
    }

    #[test]
    fn temperature_extrapolation_is_rejected_as_unresolved() {
        let mut input = specimen();
        input.local_temp_c = Some(60.0);
        let result = screen(input);
        assert!(result
            .unresolved
            .contains(&"temperature outside published coefficient interval 0-50 C"));
    }

    #[test]
    fn regulated_comparison_has_wider_ideal_feedback_margin() {
        let (low, high) = buck_feedback_window(14.0, 0.001);
        assert!((low - 14.74745).abs() < 0.00001);
        assert!((high - 15.25345).abs() < 0.00001);
    }
}
