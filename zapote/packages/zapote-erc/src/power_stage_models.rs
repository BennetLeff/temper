//! Small, fail-closed power-stage sanity models used by Zapote ERC.
//! These are analytical checks, not component qualification or SPICE.

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DoublerConfig {
    pub line_rms_v: f64,
    pub line_hz: f64,
    pub load_w: f64,
    pub diode_drop_v: f64,
    pub series_r_ohm: f64,
    pub capacitance_per_physical_cap_f: f64,
    pub parallel_caps_per_half: u32,
    pub timestep_s: f64,
    pub cycles: u32,
    pub convergence_tolerance: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DoublerSummary {
    pub bus_mean_v: f64,
    pub bus_ripple_pp_v: f64,
    pub physical_cap_ripple_pp_v: f64,
    pub physical_cap_rms_a: f64,
    pub input_rms_a: f64,
    pub input_real_power_w: f64,
    pub power_factor: f64,
    pub peak_input_a: f64,
    pub energy_balance_error_w: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ModelError {
    InvalidInput(&'static str),
    NonConverged {
        previous_v: f64,
        current_v: f64,
        previous_a: f64,
        current_a: f64,
        previous_b: f64,
        current_b: f64,
    },
}

fn finite_positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

/// Integrate a passive two-capacitor voltage doubler over complete line cycles.
/// Capacitor voltage is the voltage of one physical cap; `parallel_caps_per_half`
/// scales stored charge, while reported capacitor ripple/current is per physical
/// cap. The final two cycles must agree before a result is returned.
pub fn simulate_doubler(config: DoublerConfig) -> Result<DoublerSummary, ModelError> {
    if !finite_positive(config.line_rms_v)
        || !finite_positive(config.line_hz)
        || !finite_positive(config.load_w)
        || !config.diode_drop_v.is_finite()
        || config.diode_drop_v < 0.0
        || !finite_positive(config.series_r_ohm)
        || !finite_positive(config.capacitance_per_physical_cap_f)
        || config.parallel_caps_per_half == 0
        || !finite_positive(config.timestep_s)
        || config.cycles < 8
        || !finite_positive(config.convergence_tolerance)
    {
        return Err(ModelError::InvalidInput(
            "all values must be finite, positive, and cycles >= 8",
        ));
    }
    let vp = config.line_rms_v * 2.0_f64.sqrt();
    let c_half = config.capacitance_per_physical_cap_f * config.parallel_caps_per_half as f64;
    let raw_samples = 1.0 / config.line_hz / config.timestep_s;
    if !raw_samples.is_finite() || raw_samples < 20.0 || raw_samples > 2_000_000.0 {
        return Err(ModelError::InvalidInput(
            "timestep must resolve the line cycle within the work bound",
        ));
    }
    let samples = raw_samples.round() as usize;
    let effective_dt = 1.0 / (config.line_hz * samples as f64);
    let total = samples
        .checked_mul(config.cycles as usize)
        .filter(|steps| *steps <= 50_000_000)
        .ok_or(ModelError::InvalidInput(
            "simulation exceeds 50 million steps",
        ))?;
    let measure_start = total - samples * 2;
    let mut a = vp - config.diode_drop_v;
    if !finite_positive(a) || !finite_positive(c_half) {
        return Err(ModelError::InvalidInput(
            "nonphysical initial state or total capacitance",
        ));
    }
    let mut b = a;
    let mut last_cycle_mean: Option<f64> = None;
    let mut last_cycle_state: Option<(f64, f64)> = None;
    let mut cycle_mean = 0.0;
    let mut cycle_count = 0usize;
    let mut isq = 0.0;
    let mut pin = 0.0;
    let mut cap_isq = 0.0;
    let mut bus_min: f64 = f64::INFINITY;
    let mut bus_max: f64 = 0.0;
    let mut bus_sum: f64 = 0.0;
    let mut cap_min: f64 = f64::INFINITY;
    let mut cap_max: f64 = 0.0;
    let mut peak_i: f64 = 0.0;
    let mut loss_r = 0.0;
    let mut loss_d = 0.0;
    let mut energy_start = 0.0;
    for k in 0..total {
        let t = k as f64 * effective_dt;
        let vs = vp * (2.0 * std::f64::consts::PI * config.line_hz * t).sin();
        let bus = a + b;
        let il = config.load_w / bus;
        if k == measure_start {
            energy_start = 0.5 * c_half * (a * a + b * b);
        }
        let mut charge = 0.0;
        let mut signed = 0.0;
        let (ia, ib);
        if vs >= 0.0 && vs > a + config.diode_drop_v {
            charge = (vs - a - config.diode_drop_v) / config.series_r_ohm;
            a += (charge - il) * effective_dt / c_half;
            b -= il * effective_dt / c_half;
            signed = charge;
            ia = charge - il;
            ib = -il;
        } else if vs < 0.0 && -vs > b + config.diode_drop_v {
            charge = (-vs - b - config.diode_drop_v) / config.series_r_ohm;
            b += (charge - il) * effective_dt / c_half;
            a -= il * effective_dt / c_half;
            signed = -charge;
            ia = -il;
            ib = charge - il;
        } else {
            a -= il * effective_dt / c_half;
            b -= il * effective_dt / c_half;
            ia = -il;
            ib = -il;
        }
        if a <= 0.0 || b <= 0.0 || !a.is_finite() || !b.is_finite() {
            return Err(ModelError::InvalidInput("nonphysical capacitor state"));
        }
        if k >= measure_start {
            isq += signed * signed;
            pin += vs * signed;
            let n = config.parallel_caps_per_half as f64;
            cap_isq += (ia * ia + ib * ib) / (2.0 * n * n);
            let now = a + b;
            bus_sum += now;
            bus_min = bus_min.min(now);
            bus_max = bus_max.max(now);
            cap_min = cap_min.min(a.min(b));
            cap_max = cap_max.max(a.max(b));
            cycle_mean += now;
            loss_r += signed * signed * config.series_r_ohm;
            loss_d += charge * config.diode_drop_v;
            peak_i = peak_i.max(charge);
            cycle_count += 1;
            if cycle_count == samples {
                let mean = cycle_mean / samples as f64;
                if let Some(prev) = last_cycle_mean {
                    let Some((prev_a, prev_b)) = last_cycle_state else {
                        return Err(ModelError::InvalidInput("missing convergence state"));
                    };
                    let state_scale = mean.max(1.0);
                    if (mean - prev).abs() > config.convergence_tolerance * state_scale
                        || (a - prev_a).abs() > config.convergence_tolerance * state_scale
                        || (b - prev_b).abs() > config.convergence_tolerance * state_scale
                    {
                        return Err(ModelError::NonConverged {
                            previous_v: prev,
                            current_v: mean,
                            previous_a: prev_a,
                            current_a: a,
                            previous_b: prev_b,
                            current_b: b,
                        });
                    }
                }
                last_cycle_mean = Some(mean);
                last_cycle_state = Some((a, b));
                cycle_mean = 0.0;
                cycle_count = 0;
            }
        }
    }
    let count = (samples * 2) as f64;
    let duration = count * effective_dt;
    let end_energy = 0.5 * c_half * (a * a + b * b);
    let vrms = config.line_rms_v;
    let irms = (isq / count).sqrt();
    let p = pin / count;
    let balance = p
        - config.load_w
        - loss_r / count
        - loss_d / count
        - (end_energy - energy_start) / duration;
    Ok(DoublerSummary {
        bus_mean_v: bus_sum / count,
        bus_ripple_pp_v: bus_max - bus_min,
        physical_cap_ripple_pp_v: cap_max - cap_min,
        physical_cap_rms_a: (cap_isq / count).sqrt(),
        input_rms_a: irms,
        input_real_power_w: p,
        power_factor: p / (vrms * irms),
        peak_input_a: peak_i,
        energy_balance_error_w: balance,
    })
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
