//! Conditional A3/A4 operating-envelope calculator.
//!
//! This executable is deliberately dependency-free so the result can be
//! rebuilt with `rustc --edition=2021 -O envelope.rs`.  It is a conservative
//! screening model, not a controller, magnetics, or semiconductor model.
//! Values which are not bounded by the retained evidence stay conditional or
//! unknown in the output.

use std::env;
use std::fmt::Write as _;

#[derive(Clone, Copy, Debug)]
pub struct Inputs {
    pub vin_rms_max_v: f64,
    pub c_min_f: f64,
    pub l_min_h: f64,
    pub l_max_h: f64,
    pub current_at_trip_a: f64,
    pub delay_s: f64,
    pub vd_start_v: f64,
    pub vb_initial_v: f64,
    pub vd_screen_v: f64,
    pub vd_rating_v: f64,
    pub vb_rating_v: f64,
    pub vds_rating_v: f64,
    pub diode_rating_v: f64,
    pub vgs_abs_v: f64,
}

impl Default for Inputs {
    fn default() -> Self {
        Self {
            // A3/A4 high-line input from the retained 108--132 Vac contract.
            vin_rms_max_v: 132.0,
            // 22 uF candidate at -10% tolerance. Effective C, ESL and ESR
            // remain unqualified; this is an explicit conditional input.
            c_min_f: 19.8e-6,
            // 100/216 uH are a conditional sensitivity pair. They are not
            // physical L(I,T) bounds and are never promoted by this program.
            l_min_h: 100e-6,
            l_max_h: 216e-6,
            // 50 A is an evaluation point only; it is not a fault maximum.
            current_at_trip_a: 50.0,
            delay_s: 2e-6,
            // Conditional static trip point from the timing audit.
            vd_start_v: 432.085945,
            vb_initial_v: 410.0,
            // Chosen engineering screen for the VD local reservoir. It is
            // below the candidate 630 V part rating and is not a guarantee.
            vd_screen_v: 500.0,
            // Ratings are recorded separately from operational targets.
            vd_rating_v: 630.0,
            vb_rating_v: 450.0,
            vds_rating_v: 650.0,
            diode_rating_v: 650.0,
            vgs_abs_v: 25.0,
        }
    }
}

impl Inputs {
    pub fn validate(&self) -> Result<(), String> {
        let fields = [
            ("vin_rms_max_v", self.vin_rms_max_v),
            ("c_min_f", self.c_min_f),
            ("l_min_h", self.l_min_h),
            ("l_max_h", self.l_max_h),
            ("current_at_trip_a", self.current_at_trip_a),
            ("delay_s", self.delay_s),
            ("vd_start_v", self.vd_start_v),
            ("vb_initial_v", self.vb_initial_v),
            ("vd_screen_v", self.vd_screen_v),
            ("vd_rating_v", self.vd_rating_v),
            ("vb_rating_v", self.vb_rating_v),
            ("vds_rating_v", self.vds_rating_v),
            ("diode_rating_v", self.diode_rating_v),
            ("vgs_abs_v", self.vgs_abs_v),
        ];
        for (name, value) in fields {
            if !value.is_finite() {
                return Err(format!("{name} must be finite, got {value:?}"));
            }
            if value < 0.0 {
                return Err(format!("{name} must be non-negative, got {value}"));
            }
        }
        for (name, value) in [
            ("vin_rms_max_v", self.vin_rms_max_v),
            ("c_min_f", self.c_min_f),
            ("l_min_h", self.l_min_h),
            ("l_max_h", self.l_max_h),
            ("vd_rating_v", self.vd_rating_v),
            ("vb_rating_v", self.vb_rating_v),
            ("vds_rating_v", self.vds_rating_v),
            ("diode_rating_v", self.diode_rating_v),
            ("vgs_abs_v", self.vgs_abs_v),
        ] {
            if value <= 0.0 {
                return Err(format!("{name} must be greater than zero, got {value}"));
            }
        }
        if self.vd_start_v < self.vin_rms_max_v * std::f64::consts::SQRT_2 {
            return Err(
                "charged-boost screen requires VD start at or above peak source voltage".into(),
            );
        }
        if self.l_max_h < self.l_min_h {
            return Err("l_max_h must be at least l_min_h".into());
        }
        if self.vd_screen_v > self.vd_rating_v {
            return Err("vd_screen_v cannot exceed vd_rating_v".into());
        }
        Ok(())
    }
}

/// Nominal RevB detector/controller anchors retained from the source-07
/// divider and UCC28180 datasheet. These are threshold calculations, not
/// operating limits or timing guarantees.
pub fn revb_anchors() -> (f64, f64, f64, f64, f64, f64) {
    // Four 200 kOhm + 187 kOhm = 987 kOhm upper chain, followed by the
    // 200 Ohm step and 5.62 kOhm bottom. The high tap sees 5.82 kOhm.
    let divider_total = 987_000.0 + 200.0 + 5_620.0;
    let vd_high_trip_v = 2.5 * divider_total / 5_820.0;
    let vd_low_trip_v = 2.5 * divider_total / 5_620.0;
    // UCC28180 VSENSE OVP reference anchors from the source audit. The
    // 5.0 V regulation anchor is the retained 389.615 V nominal PFC bus.
    let ucc_ovp_low_anchor_v = 5.35 * (1_000_000.0 + 13_000.0) / 13_000.0;
    let ucc_ovp_high_anchor_v = 5.45 * (1_000_000.0 + 13_000.0) / 13_000.0;
    // Current-sense negative overcurrent comparator anchors from the retained
    // UCC28180 screen, translated through the 10 mOhm shunt.
    let soc_typ_a = 0.285 / 0.010;
    let soc_min_a = 0.259 / 0.010;
    (
        vd_high_trip_v,
        vd_low_trip_v,
        ucc_ovp_low_anchor_v,
        ucc_ovp_high_anchor_v,
        soc_typ_a,
        soc_min_a,
    )
}

#[derive(Clone, Copy, Debug)]
pub struct ResultPoint {
    pub vin_peak_v: f64,
    pub current_start_a: f64,
    pub current_rise_a: f64,
    pub current_end_a: f64,
    pub vd_start_v: f64,
    pub vd_rise_during_delay_v: f64,
    pub vd_end_v: f64,
    pub cap_energy_increment_j: f64,
    pub inductor_energy_start_j: f64,
    pub inductor_energy_end_j: f64,
    pub vd_peak_v: f64,
    pub vd_screen_margin_v: f64,
    pub vd_rating_margin_v: f64,
    pub vb_rating_margin_v: f64,
    pub passes_vd_screen: bool,
}

/// Evaluate the conservative delay screen.
///
/// The construction intentionally credits final current for capacitor charge
/// and independently uses the maximum L for post-delay commutation.  It is an
/// upper-bound screen that may double-count mutually exclusive trajectory
/// details; it is not a claim that both extrema occur simultaneously.
pub fn evaluate(p: Inputs) -> Result<ResultPoint, String> {
    p.validate()?;
    let vin_peak_v = p.vin_rms_max_v * 2.0_f64.sqrt();
    let current_rise_a = vin_peak_v / p.l_min_h * p.delay_s;
    let current_end_a = p.current_at_trip_a + current_rise_a;
    let vd_rise_during_delay_v = current_end_a * p.delay_s / p.c_min_f;
    let vd_end_v = p.vd_start_v + vd_rise_during_delay_v;
    let cap_energy_increment_j = 0.5 * p.c_min_f * (vd_end_v.powi(2) - p.vd_start_v.powi(2));
    let inductor_energy_start_j = 0.5 * p.l_max_h * p.current_at_trip_a.powi(2);
    let inductor_energy_end_j = 0.5 * p.l_max_h * current_end_a.powi(2);
    let vd_peak_v = vin_peak_v
        + ((vd_end_v - vin_peak_v).powi(2) + p.l_max_h / p.c_min_f * current_end_a.powi(2)).sqrt();
    let values = [
        vin_peak_v,
        current_rise_a,
        current_end_a,
        vd_rise_during_delay_v,
        vd_end_v,
        cap_energy_increment_j,
        inductor_energy_start_j,
        inductor_energy_end_j,
        vd_peak_v,
    ];
    if values.iter().any(|v| !v.is_finite()) {
        return Err("non-finite result; check input scale".into());
    }
    Ok(ResultPoint {
        vin_peak_v,
        current_start_a: p.current_at_trip_a,
        current_rise_a,
        current_end_a,
        vd_start_v: p.vd_start_v,
        vd_rise_during_delay_v,
        vd_end_v,
        cap_energy_increment_j,
        inductor_energy_start_j,
        inductor_energy_end_j,
        vd_peak_v,
        vd_screen_margin_v: p.vd_screen_v - vd_peak_v,
        vd_rating_margin_v: p.vd_rating_v - vd_peak_v,
        // VB is not charged by the post-F2-open local-cap screen. Keep its
        // rating margin explicit instead of silently crediting VB capacitance.
        vb_rating_margin_v: p.vb_rating_v - p.vb_initial_v,
        passes_vd_screen: vd_peak_v <= p.vd_screen_v,
    })
}

/// Maximum delay for a fixed current and plant pair, or None if delay zero
/// already exceeds the selected VD screen.
pub fn allowable_delay(p: Inputs, current_a: f64) -> Result<Option<f64>, String> {
    if !current_a.is_finite() || current_a < 0.0 {
        return Err("current_a must be finite and non-negative".into());
    }
    let mut q = p;
    q.current_at_trip_a = current_a;
    q.delay_s = 0.0;
    q.validate()?;
    if evaluate(q)?.vd_peak_v > q.vd_screen_v {
        return Ok(None);
    }
    let mut low = 0.0;
    let mut high = 1e-3;
    loop {
        q.delay_s = high;
        if evaluate(q)?.vd_peak_v > q.vd_screen_v {
            break;
        }
        high *= 2.0;
        if !high.is_finite() {
            return Err("delay boundary search overflow".into());
        }
    }
    for _ in 0..100 {
        let mid = (low + high) / 2.0;
        q.delay_s = mid;
        if evaluate(q)?.vd_peak_v <= q.vd_screen_v {
            low = mid;
        } else {
            high = mid;
        }
    }
    Ok(Some(low))
}

/// Maximum current at the start of the delay that remains within the VD
/// screen. This is a conditional inverse boundary, not a device rating.
pub fn allowable_current(p: Inputs, delay_s: f64) -> Result<Option<f64>, String> {
    if !delay_s.is_finite() || delay_s < 0.0 {
        return Err("delay_s must be finite and non-negative".into());
    }
    let mut q = p;
    q.delay_s = delay_s;
    q.current_at_trip_a = 0.0;
    q.validate()?;
    if evaluate(q)?.vd_peak_v > q.vd_screen_v {
        return Ok(None);
    }
    let mut low = 0.0;
    let mut high = 1.0;
    while {
        q.current_at_trip_a = high;
        evaluate(q)?.vd_peak_v <= q.vd_screen_v
    } {
        high *= 2.0;
        if !high.is_finite() || high > 1e9 {
            return Err("current boundary search overflow".into());
        }
    }
    for _ in 0..100 {
        let mid = (low + high) / 2.0;
        q.current_at_trip_a = mid;
        if evaluate(q)?.vd_peak_v <= q.vd_screen_v {
            low = mid;
        } else {
            high = mid;
        }
    }
    Ok(Some(low))
}

fn json_num(value: f64) -> String {
    if value.is_finite() {
        format!("{value:.9}")
    } else {
        "null".into()
    }
}

fn json_bool(value: bool) -> &'static str {
    if value {
        "true"
    } else {
        "false"
    }
}

fn point_json(p: &ResultPoint) -> String {
    format!(
        "{{\"vin_peak_v\":{},\"current_start_a\":{},\"current_rise_a\":{},\"current_end_a\":{},\"vd_start_v\":{},\"vd_rise_during_delay_v\":{},\"vd_end_v\":{},\"cap_energy_increment_j\":{},\"inductor_energy_start_j\":{},\"inductor_energy_end_j\":{},\"vd_peak_v\":{},\"vd_screen_margin_v\":{},\"vd_rating_margin_v\":{},\"vb_rating_margin_v\":{},\"vds_rating_margin_v\":null,\"diode_rating_margin_v\":null,\"passes_vd_screen\":{}}}",
        json_num(p.vin_peak_v), json_num(p.current_start_a), json_num(p.current_rise_a),
        json_num(p.current_end_a), json_num(p.vd_start_v), json_num(p.vd_rise_during_delay_v),
        json_num(p.vd_end_v), json_num(p.cap_energy_increment_j), json_num(p.inductor_energy_start_j),
        json_num(p.inductor_energy_end_j), json_num(p.vd_peak_v), json_num(p.vd_screen_margin_v),
        json_num(p.vd_rating_margin_v), json_num(p.vb_rating_margin_v), json_bool(p.passes_vd_screen)
    )
}

fn emit_json(base: Inputs) -> Result<String, String> {
    base.validate()?;
    let evaluation = evaluate(base)?;
    let delay_budget = allowable_delay(base, base.current_at_trip_a)?;
    let current_budget = allowable_current(base, base.delay_s)?;
    let (
        vd_high_trip_v,
        vd_low_trip_v,
        ucc_ovp_low_anchor_v,
        ucc_ovp_high_anchor_v,
        soc_typ_a,
        soc_min_a,
    ) = revb_anchors();
    let mut out = String::new();
    out.push_str("{\n  \"status\": \"INDETERMINATE\",\n");
    out.push_str("  \"model\": {\"kind\": \"conditional_conservative_screen\", \"double_count_warning\": true, \"instantaneous_current_is_not_bounded\": true},\n");
    out.push_str("  \"node_limits\": [\n");
    writeln!(out, "    {{\"node\":\"VD_local_reservoir\",\"rating_v\":{},\"operational_target_v\":{},\"target_kind\":\"chosen_conditional_screen\",\"status\":\"conditional\"}},", base.vd_rating_v, base.vd_screen_v).unwrap();
    out.push_str("    {\"node\":\"VB_bulk_bank\",\"rating_v\":450.0,\"operational_target_v\":410.0,\"target_kind\":\"conditional_initial_state_only\",\"status\":\"rating_only\"},\n");
    out.push_str("    {\"node\":\"VDS\",\"rating_v\":650.0,\"operational_target_v\":null,\"target_kind\":\"unresolved_switching_overshoot\",\"status\":\"rating_only\"},\n");
    out.push_str("    {\"node\":\"diode_reverse\",\"rating_v\":650.0,\"operational_target_v\":null,\"target_kind\":\"unresolved_switching_overshoot\",\"status\":\"rating_only\"},\n");
    out.push_str("    {\"node\":\"VGS\",\"abs_rating_v\":25.0,\"operational_target_v\":15.0,\"target_kind\":\"chosen_conditional_gate_drive\",\"status\":\"conditional\"}\n  ],\n");
    write!(
        out,
        "  \"revb_nominal_threshold_anchors\": {{\"vd_high_tap_2p5v_derived_v\":{},\"vd_low_tap_2p5v_derived_v\":{},\"ucc28180_regulation_bus_nominal_v\":389.615,\"ucc28180_ovp_5p35v_anchor_v\":{},\"ucc28180_ovp_5p45v_anchor_v\":{},\"soc_typ_a\":{},\"soc_min_a\":{},\"kind\":\"nominal_threshold_anchor_not_operating_limit\"}},\n",
        json_num(vd_high_trip_v), json_num(vd_low_trip_v), json_num(ucc_ovp_low_anchor_v),
        json_num(ucc_ovp_high_anchor_v), json_num(soc_typ_a), json_num(soc_min_a)
    ).unwrap();
    write!(
        out,
        "  \"inputs\": {{\"vin_rms_max_v\":{},\"c_min_f\":{},\"l_min_h\":{},\"l_max_h\":{},\"current_at_trip_a\":{},\"delay_s\":{},\"vd_start_v\":{},\"vb_initial_v\":{},\"vd_screen_v\":{}}},\n",
        json_num(base.vin_rms_max_v), json_num(base.c_min_f), json_num(base.l_min_h),
        json_num(base.l_max_h), json_num(base.current_at_trip_a), json_num(base.delay_s),
        json_num(base.vd_start_v), json_num(base.vb_initial_v), json_num(base.vd_screen_v)
    ).unwrap();
    write!(out, "  \"evaluation\": {},\n", point_json(&evaluation)).unwrap();
    write!(
        out,
        "  \"boundary\": {{\"allowable_delay_us_at_start_current\":{},\"allowable_current_a_at_delay\":{}}},\n",
        delay_budget.map(|v| json_num(v * 1e6)).unwrap_or_else(|| "null".into()),
        current_budget.map(json_num).unwrap_or_else(|| "null".into())
    ).unwrap();
    out.push_str("  \"conditional_region\": [\n");
    let plants = [(180e-6, 180e-6), (144e-6, 216e-6), (100e-6, 216e-6)];
    let currents = [40.0, 45.0, 50.0, 60.0];
    let mut first = true;
    for (l_min_h, l_max_h) in plants {
        for current_a in currents {
            let mut q = base;
            q.l_min_h = l_min_h;
            q.l_max_h = l_max_h;
            q.current_at_trip_a = current_a;
            let mut at_2us = q;
            at_2us.delay_s = 2e-6;
            let mut at_5us = q;
            at_5us.delay_s = 5e-6;
            let p2 = evaluate(at_2us)?;
            let p5 = evaluate(at_5us)?;
            let budget = allowable_delay(q, current_a)?;
            if !first {
                out.push_str(",\n");
            }
            first = false;
            write!(
                out,
                "    {{\"l_min_h\":{},\"l_max_h\":{},\"c_min_f\":{},\"current_start_a\":{},\"peak_at_2us_v\":{},\"peak_at_5us_v\":{},\"allowable_delay_us\":{}}}",
                json_num(l_min_h), json_num(l_max_h), json_num(base.c_min_f), json_num(current_a),
                json_num(p2.vd_peak_v), json_num(p5.vd_peak_v),
                budget.map(|v| json_num(v * 1e6)).unwrap_or_else(|| "null".into())
            ).unwrap();
        }
    }
    out.push_str("\n  ],\n");
    out.push_str("  \"unknowns\": [\"effective_C_over_temperature_and_frequency\",\"L(I,T) trajectory and saturation\",\"UCC28180 PCL-to-gate maximum delay\",\"loaded STW65N65DM2AG current cessation bound\",\"wiring/fuse arcing and parasitic ringing\",\"installed VD/VDS/diode transient acceptance\"],\n");
    out.push_str("  \"sources\": [\"../f2-timing-02/README.md (retained source audit)\",\"TI UCC28180D datasheet §7.5: 0.400 V typ / 0.438 V max PCL threshold; no applicable end-to-end delay maximum\",\"Würth 760800301 datasheet: 180 uH ±20%; 43 A saturation figure typical at ΔL/L=30%, not a fault-current bound\"]\n}\n");
    Ok(out)
}

fn parse_args(args: &[String]) -> Result<Inputs, String> {
    let mut p = Inputs::default();
    let mut seen = std::collections::BTreeSet::new();
    let mut iter = args.iter();
    while let Some(name) = iter.next() {
        if !seen.insert(name.as_str()) {
            return Err(format!("duplicate argument {name}"));
        }
        if name == "--json" {
            continue;
        }
        let slot = match name.as_str() {
            "--vin-rms-v" => (&mut p.vin_rms_max_v, 1.0),
            "--cmin-uf" => (&mut p.c_min_f, 1e-6),
            "--lmin-uh" => (&mut p.l_min_h, 1e-6),
            "--lmax-uh" => (&mut p.l_max_h, 1e-6),
            "--current-a" => (&mut p.current_at_trip_a, 1.0),
            "--delay-us" => (&mut p.delay_s, 1e-6),
            "--vd-start-v" => (&mut p.vd_start_v, 1.0),
            "--screen-v" => (&mut p.vd_screen_v, 1.0),
            _ => return Err(format!("unknown argument {name}")),
        };
        let raw = iter
            .next()
            .ok_or_else(|| format!("missing value after {name}"))?;
        *slot.0 = raw
            .parse::<f64>()
            .map_err(|_| format!("invalid number {raw}"))?
            * slot.1;
    }
    p.validate()?;
    Ok(p)
}

fn cli() -> Result<String, String> {
    emit_json(parse_args(&env::args().skip(1).collect::<Vec<_>>())?)
}

fn main() {
    match cli() {
        Ok(json) => print!("{json}"),
        Err(error) => {
            eprintln!("error: {error}");
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_nonfinite_and_invalid_geometry() {
        let mut p = Inputs::default();
        p.c_min_f = f64::NAN;
        assert!(p.validate().is_err());
        p = Inputs::default();
        p.l_min_h = 220e-6;
        p.l_max_h = 180e-6;
        assert!(p.validate().is_err());
    }

    #[test]
    fn highline_ramp_is_reported_separately_from_start_current() {
        let mut p = Inputs::default();
        p.current_at_trip_a = 40.0;
        p.delay_s = 2e-6;
        let result = evaluate(p).unwrap();
        assert!(result.current_rise_a > 0.0);
        assert!(
            (result.current_end_a - result.current_start_a - result.current_rise_a).abs() < 1e-12
        );
        assert!(result.current_end_a > result.current_start_a);
    }

    #[test]
    fn local_cap_energy_is_positive_and_scales_with_delay() {
        let mut p = Inputs::default();
        p.delay_s = 1e-6;
        let short = evaluate(p).unwrap();
        p.delay_s = 2e-6;
        let long = evaluate(p).unwrap();
        assert!(short.cap_energy_increment_j > 0.0);
        assert!(long.cap_energy_increment_j > short.cap_energy_increment_j);
    }

    #[test]
    fn lower_lmin_increases_current_and_reduces_delay_budget() {
        let mut nominal = Inputs::default();
        nominal.l_min_h = 180e-6;
        nominal.l_max_h = 180e-6;
        let mut low = nominal;
        low.l_min_h = 100e-6;
        low.l_max_h = 216e-6;
        assert!(evaluate(low).unwrap().current_end_a > evaluate(nominal).unwrap().current_end_a);
        assert!(
            allowable_delay(low, 50.0).unwrap().unwrap()
                < allowable_delay(nominal, 50.0).unwrap().unwrap()
        );
    }

    #[test]
    fn inverse_current_boundary_matches_forward_screen() {
        let p = Inputs::default();
        let current = allowable_current(p, 2e-6).unwrap().unwrap();
        let mut q = p;
        q.current_at_trip_a = current;
        assert!(evaluate(q).unwrap().passes_vd_screen);
        q.current_at_trip_a = current + 0.01;
        assert!(!evaluate(q).unwrap().passes_vd_screen);
    }

    #[test]
    fn zero_delay_does_not_turn_threshold_into_a_physical_current_limit() {
        let mut p = Inputs::default();
        p.delay_s = 0.0;
        p.current_at_trip_a = 40.0;
        let result = evaluate(p).unwrap();
        assert!(result.current_end_a == result.current_start_a);
        assert!(result.vd_peak_v.is_finite());
    }

    #[test]
    fn default_json_is_machine_readable_shape() {
        let json = emit_json(Inputs::default()).unwrap();
        assert!(json.starts_with("{\n  \"status\": \"INDETERMINATE\""));
        assert!(json.contains("\"node_limits\""));
        assert!(json.contains("\"allowable_current_a_at_delay\""));
    }

    #[test]
    fn revb_anchor_calculation_is_not_confused_with_a_physical_limit() {
        let (high, low, ovp_low, ovp_high, soc_typ, soc_min) = revb_anchors();
        assert!((high - 426.469072).abs() < 1e-3);
        assert!((low - 441.645907).abs() < 1e-3);
        assert!((ovp_low - 416.888461).abs() < 1e-3);
        assert!((ovp_high - 424.680769).abs() < 1e-3);
        assert!((soc_typ - 28.5).abs() < 1e-12);
        assert!((soc_min - 25.9).abs() < 1e-12);
    }
}

#[cfg(test)]
mod independent_checks {
    use super::*;

    #[test]
    fn rejects_start_below_source_where_inverse_monotonicity_is_not_established() {
        let p = Inputs {
            vd_start_v: 10.0,
            ..Inputs::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn delay_search_is_not_silently_capped_at_one_millisecond() {
        let p = Inputs {
            l_min_h: 1.0,
            l_max_h: 1.0,
            c_min_f: 1.0,
            current_at_trip_a: 0.01,
            ..Inputs::default()
        };
        let boundary = allowable_delay(p, 0.01).unwrap().unwrap();
        assert!(boundary > 0.001);
        let beyond = Inputs {
            delay_s: boundary * 1.0001,
            ..p
        };
        assert!(!evaluate(beyond).unwrap().passes_vd_screen);
    }

    #[test]
    fn commutation_peak_agrees_with_independent_rk4_circuit_equations() {
        // Integrate dV/dt=I/C, dI/dt=(Vin-V)/L until diode current reaches zero.
        // The oracle never uses the closed-form peak equation under test.
        for (l, i0) in [(100e-6, 40.0), (180e-6, 45.0), (216e-6, 50.0)] {
            let p = Inputs {
                l_min_h: l,
                l_max_h: l,
                current_at_trip_a: i0,
                delay_s: 0.0,
                ..Inputs::default()
            };
            let expected = evaluate(p).unwrap();
            let vin = p.vin_rms_max_v * std::f64::consts::SQRT_2;
            let (mut v, mut i) = (p.vd_start_v, i0);
            let dt = 1e-9;
            let mut peak = v;
            let mut source_work = 0.0;
            for _ in 0..1_000_000 {
                if i <= 0.0 {
                    break;
                }
                let f = |v: f64, i: f64| (i / p.c_min_f, (vin - v) / l);
                let a = f(v, i);
                let b = f(v + dt * a.0 / 2.0, i + dt * a.1 / 2.0);
                let c = f(v + dt * b.0 / 2.0, i + dt * b.1 / 2.0);
                let d = f(v + dt * c.0, i + dt * c.1);
                let old_i = i;
                v += dt * (a.0 + 2.0 * b.0 + 2.0 * c.0 + d.0) / 6.0;
                i += dt * (a.1 + 2.0 * b.1 + 2.0 * c.1 + d.1) / 6.0;
                source_work += vin * (old_i + i) * dt / 2.0;
                peak = peak.max(v);
            }
            assert!(i <= 0.0, "oracle never reached zero diode current");
            assert!((peak - expected.vd_peak_v).abs() < 1e-5);
            let cap_gain = 0.5 * p.c_min_f * (v * v - p.vd_start_v * p.vd_start_v);
            let l_loss = 0.5 * l * (i0 * i0 - i * i);
            assert!(
                (cap_gain - l_loss - source_work).abs() < 1e-7,
                "independent circuit energy balance must include continuing source work"
            );
        }
    }
}
