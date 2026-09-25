//! Live independent circuit solver check. Does not write oracle pins or PCBs.
//! Run: cargo run -p zapote-erc --example verify_pfc_spice -- NGSPICE NEW_DIR
use serde_json::json;
use std::{
    error::Error,
    f64::consts::{PI, SQRT_2},
    fs,
    path::Path,
    process::Command,
};
use zapote_erc::pfc_currents::{Config, calculate};

fn measured(log: &str, name: &str) -> Result<f64, Box<dyn Error>> {
    for line in log.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        if key.trim() == name {
            let number: f64 = value
                .split_whitespace()
                .next()
                .ok_or("missing measure")?
                .parse()?;
            if !number.is_finite() {
                return Err("nonfinite measure".into());
            }
            return Ok(number);
        }
    }
    Err(format!("ngspice did not produce {name}").into())
}

fn close(actual: f64, expected: f64, tolerance: f64, context: &str) -> Result<(), Box<dyn Error>> {
    if (actual - expected).abs() > tolerance * expected.abs().max(1e-3) {
        return Err(
            format!("{context}: {actual} != {expected} (relative tolerance {tolerance})").into(),
        );
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 {
        return Err("usage: verify_pfc_spice NGSPICE NEW_OUTPUT_DIRECTORY".into());
    }
    let out = Path::new(&args[1]);
    fs::create_dir(out)?;
    let version = Command::new(&args[0]).arg("--version").output()?;
    fs::write(out.join("ngspice-version.txt"), &version.stdout)?;
    if !version.status.success() {
        return Err("ngspice version probe failed".into());
    }
    let c = Config {
        line_rms_v: 120.,
        input_rms_limit_a: 15.,
        bus_v: 389.615,
        inductance_h: 180e-6,
        switching_hz: 129_000.,
        phase_samples: 256,
    };
    let production = calculate(c)?;
    // Closed-form full-line integral sets initial conditions independently;
    // production samples never become sources in the SPICE circuit.
    let m = SQRT_2 * c.line_rms_v / c.bus_v;
    let k = SQRT_2 * c.line_rms_v / (c.inductance_h * c.switching_hz);
    let variance = k * k / 12. * (0.5 - 2. * m * 4. / (3. * PI) + m * m * 3. / 8.);
    let fundamental = (c.input_rms_limit_a.powi(2) - variance).sqrt();
    let load = c.line_rms_v * fundamental / c.bus_v;
    let mut results = vec![];
    for phase in [2, 23, 55] {
        let theta = 2. * PI * (phase as f64 + 0.5) / c.phase_samples as f64;
        let vin = SQRT_2 * c.line_rms_v * theta.sin();
        let average = SQRT_2 * fundamental * theta.sin();
        let duty = 1. - vin / c.bus_v;
        let ripple = vin * duty / (c.inductance_h * c.switching_hz);
        let valley = average - ripple / 2.;
        let local = &production.samples[phase * 8..(phase + 1) * 8];
        let rms = |field: fn(&zapote_erc::pfc_currents::Sample) -> f64| {
            local
                .iter()
                .map(|s| s.weight * c.phase_samples as f64 * field(s).powi(2))
                .sum::<f64>()
                .sqrt()
        };
        let expected = [
            rms(|s| s.inductor_a),
            rms(|s| s.switch_a),
            rms(|s| s.diode_a),
            rms(|s| s.capacitor_a),
        ];
        let mut previous: Option<Vec<f64>> = None;
        for step in [5e-9, 2.5e-9] {
            let stem = format!("phase-{phase}-step-{step:.1e}");
            let deck = format!(
                r#"Independent initialized boost, frozen line phase {phase}
.param VIN={vin:.15e} BUS={bus:.15e} LVAL={inductance:.15e} FSW={frequency:.15e}
.param DUTY={{1-VIN/BUS}} PERIOD={{1/FSW}}
Vline input 0 {{VIN}}
Lboost input sw {{LVAL}} IC={valley:.15e}
Sboost sw sense_switch gate 0 SWITCH
Vsense_switch sense_switch 0 0
Vgate gate 0 PULSE(0 5 0 1p 1p {{DUTY*PERIOD-1p}} {{PERIOD}})
Bdiode_control diode_control 0 V=V(sw)-V(bus)
Sdiode sw sense_diode diode_control 0 DIODE_SWITCH
Vsense_diode sense_diode bus 0
Vbus bus 0 {{BUS}}
Iload bus 0 {load:.15e}
.model SWITCH SW(Ron=1u Roff=1G Vt=2.5 Vh=0.01)
.model DIODE_SWITCH SW(Ron=1u Roff=1G Vt=0 Vh=0.01)
.options method=gear reltol=1e-7 abstol=1e-10 vntol=1e-7 maxord=2
.tran {step:.15e} {{20*PERIOD}} 0 {step:.15e} UIC
.meas tran inductor_rms RMS I(Lboost) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.meas tran switch_rms RMS I(Vsense_switch) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.meas tran diode_rms RMS I(Vsense_diode) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.meas tran capacitor_rms RMS I(Vbus) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.meas tran inductor_avg AVG I(Lboost) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.meas tran diode_avg AVG I(Vsense_diode) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.meas tran inductor_min MIN I(Lboost) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.meas tran inductor_max MAX I(Lboost) FROM={{10*PERIOD}} TO={{20*PERIOD}}
.end
"#,
                bus = c.bus_v,
                inductance = c.inductance_h,
                frequency = c.switching_hz
            );
            let path = out.join(format!("{stem}.cir"));
            fs::write(&path, deck)?;
            let output = Command::new(&args[0]).arg("-b").arg(&path).output()?;
            let log = format!(
                "{}\n{}",
                String::from_utf8_lossy(&output.stdout),
                String::from_utf8_lossy(&output.stderr)
            );
            fs::write(out.join(format!("{stem}.log")), &log)?;
            if !output.status.success()
                || log.contains("Timestep too small")
                || log.contains("timestep too small")
            {
                return Err(format!("ngspice failed: {stem}; raw log retained").into());
            }
            let actual = ["inductor_rms", "switch_rms", "diode_rms", "capacitor_rms"]
                .iter()
                .map(|name| measured(&log, name))
                .collect::<Result<Vec<_>, _>>()?;
            for (a, e) in actual.iter().zip(expected) {
                close(*a, e, 5e-4, &stem)?;
            }
            close(
                measured(&log, "inductor_avg")?,
                average,
                5e-4,
                "inductor average",
            )?;
            close(
                measured(&log, "inductor_min")?,
                valley,
                5e-4,
                "inductor valley",
            )?;
            close(
                measured(&log, "inductor_max")?,
                average + ripple / 2.,
                5e-4,
                "inductor peak",
            )?;
            close(
                vin * measured(&log, "inductor_avg")?,
                c.bus_v * measured(&log, "diode_avg")?,
                5e-4,
                "energy balance",
            )?;
            if let Some(prior) = &previous {
                for (a, p) in actual.iter().zip(prior) {
                    close(*a, *p, 1e-4, "timestep refinement")?;
                }
            }
            results.push(json!({"phase_index":phase,"vin_v":vin,"average_a":average,
                "max_timestep_s":step,"rust_rms_a":expected,"ngspice_rms_a":actual,
                "deck":format!("{stem}.cir"),"log":format!("{stem}.log")}));
            previous = Some(actual);
        }
    }
    fs::write(
        out.join("result.json"),
        serde_json::to_string_pretty(&json!({
        "status":"pass","config":c,"rms_fields":["inductor","switch","diode","capacitor"],
        "comparison_relative_tolerance":5e-4,"refinement_relative_tolerance":1e-4,
        "scope":"Three frozen line-phase initialized ideal CCM boost circuits; full line-cycle control and physical devices are not modeled",
        "results":results}))?,
    )?;
    println!(
        "PASS: 3 frozen line phases, 2 timesteps, 4 branch RMS values plus extrema and energy; {}",
        out.display()
    );
    Ok(())
}
