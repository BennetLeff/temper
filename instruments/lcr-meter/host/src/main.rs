use serde::Serialize;
use std::{env, fs, process};
use temper_lcr::transport::Device;
use temper_lcr::{
    advise, analyze, calibrate, capture_grid, check_grid, correct, frequency_hz, hazard_error,
    parse_calibration, parse_sweep, waive_source_off, Advice, Calibration, CaptureOptions, Result,
    Sweep,
};

const USAGE: &str = "Usage:
  temper-lcr info PORT
  temper-lcr selftest PORT
  temper-lcr capture PORT RANGE_OHM FIXTURE FREQ_HZ[,FREQ_HZ...] OUT.json [--allow-hazard] [--no-source-off] [--short-standard]
  temper-lcr noise PORT RANGE_OHM FIXTURE FREQ_HZ[,FREQ_HZ...] OUT.json [--allow-hazard]
  temper-lcr advise-grid FREQ_HZ[,FREQ_HZ...]
  temper-lcr analyze CAPTURE.json [CAL.json] [--allow-source-off-fail]
  temper-lcr calibrate SHORT.json LOAD1.json LOAD1_OHM LOAD2.json LOAD2_OHM CAL.json [--allow-source-off-fail]
  temper-lcr validate CAPTURE.json CAL.json KNOWN_OHM TOLERANCE_PERCENT [--allow-source-off-fail]";

fn text(path: &str) -> Result<String> {
    fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))
}
fn sweep(path: &str) -> Result<Sweep> {
    parse_sweep(&text(path)?).map_err(|e| format!("{path}: {e}"))
}
fn calibration(path: &str) -> Result<Calibration> {
    parse_calibration(&text(path)?).map_err(|e| format!("{path}: {e}"))
}
fn json<T: Serialize>(value: &T) -> Result<String> {
    serde_json::to_string_pretty(value).map_err(|e| e.to_string())
}
fn write<T: Serialize>(path: &str, value: &T) -> Result<()> {
    fs::write(path, json(value)?).map_err(|e| e.to_string())
}
fn number<T: std::str::FromStr>(s: &str) -> Result<T> {
    s.parse().map_err(|_| format!("invalid number: {s}"))
}
fn frequencies(list: &str) -> Result<Vec<f64>> {
    list.split(',').map(number).collect()
}

#[derive(Serialize)]
struct GridAdvice {
    all_clean: bool,
    /// Comma-separated clean grid to pass to `capture`, if every point has one.
    suggested_grid: Option<String>,
    frequencies: Vec<Advice>,
}

fn run(args: &[String]) -> Result<()> {
    let (flags, a): (Vec<&str>, Vec<&str>) = args
        .iter()
        .skip(1)
        .map(String::as_str)
        .partition(|s| s.starts_with("--"));
    let command = a.first().copied().unwrap_or("");
    let known: &[&str] = match command {
        "capture" => &["--allow-hazard", "--no-source-off", "--short-standard"],
        "noise" => &["--allow-hazard"],
        "analyze" | "calibrate" | "validate" => &["--allow-source-off-fail"],
        _ => &[],
    };
    if let Some(bad) = flags.iter().find(|f| !known.contains(f)) {
        return Err(format!("unknown option {bad} for '{command}'\n{USAGE}"));
    }
    let flag = |name: &str| flags.contains(&name);
    match (command, a.len()) {
        ("info" | "selftest", 2) => {
            let mut d = Device::open(a[1], 100, "diagnostic")?;
            d.selftest()?;
            println!("{}", json(&d.setup)?);
            println!("ADC dual-channel fixed-pattern link test: PASS");
        }
        ("capture" | "noise", 6) => {
            let options = CaptureOptions {
                source_on: command == "capture",
                allow_hazard: flag("--allow-hazard"),
                source_off: !flag("--no-source-off"),
                short_standard: flag("--short-standard"),
            };
            let freqs = frequencies(a[4])?;
            // Refuse hazards before touching the instrument.
            for (hz, report) in freqs.iter().zip(check_grid(&freqs, options.allow_hazard)?) {
                if report.hazardous {
                    let warning = hazard_error(*hz, &report).replace('\n', "\nwarning: ");
                    eprintln!("warning: --allow-hazard: {warning}");
                }
            }
            let mut d = Device::open(a[1], number(a[2])?, a[3])?;
            d.selftest()?;
            let grid = capture_grid(&freqs, options, |word, decimation, source_on| {
                let record = d.capture(word, decimation, source_on)?;
                eprintln!(
                    "captured {:.4} Hz {}: {} output samples per channel, each the sum of {decimation} consecutive 1 MSPS conversions",
                    frequency_hz(word),
                    if source_on { "source on" } else { "source off" },
                    record.sums.len()
                );
                Ok(record)
            })?;
            for record in &grid.records {
                if !options.source_on {
                    println!(
                        "{}",
                        serde_json::to_string(&temper_lcr::noise(record)?)
                            .map_err(|e| e.to_string())?
                    );
                }
                if let Some(check) = &record.source_off_check {
                    eprintln!(
                        "source-off check {:.4} Hz: {} (A {:.2e}, B {:.2e} of source-on; limit {:.0e})",
                        check.frequency_hz,
                        if check.pass { "PASS" } else { "FAIL" },
                        check.channels[0].ratio,
                        check.channels[1].ratio,
                        check.limit_ratio
                    );
                }
            }
            write(
                a[5],
                &Sweep {
                    setup: d.setup.clone(),
                    records: grid.records,
                },
            )?;
            if !grid.source_off_failures.is_empty() {
                return Err(format!(
                    "{} point(s) failed the source-off check (saved to {} with diagnostics; analyze refuses them unless --allow-source-off-fail):\n{}",
                    grid.source_off_failures.len(),
                    a[5],
                    grid.source_off_failures.join("\n")
                ));
            }
        }
        ("advise-grid", 2) => {
            let frequencies = frequencies(a[1])?
                .into_iter()
                .map(advise)
                .collect::<Result<Vec<_>>>()?;
            let suggested_grid = frequencies
                .iter()
                .map(|f| f.suggested_hz.map(|hz| hz.to_string()))
                .collect::<Option<Vec<_>>>()
                .map(|grid| grid.join(","));
            println!(
                "{}",
                json(&GridAdvice {
                    all_clean: frequencies.iter().all(|f| f.clean),
                    suggested_grid,
                    frequencies,
                })?
            );
        }
        ("calibrate", 7) => {
            let short = sweep(a[1])?;
            let one = sweep(a[2])?;
            let two = sweep(a[4])?;
            let cal = calibrate(
                &short,
                &one,
                number(a[3])?,
                &two,
                number(a[5])?,
                flag("--allow-source-off-fail"),
            )?;
            write(a[6], &cal)?;
            println!(
                "Saved {} frequency-specific calibration points.",
                cal.points.len()
            );
        }
        ("analyze", 2 | 3) => {
            let sweep = sweep(a[1])?;
            sweep.setup.validate()?;
            let cal = a.get(2).map(|path| calibration(path)).transpose()?;
            let mut values = Vec::new();
            for r in &sweep.records {
                let mut m = analyze(r, sweep.setup.range_ohm)?;
                if flag("--allow-source-off-fail") {
                    waive_source_off(&mut m);
                }
                if let Some(c) = &cal {
                    correct(&mut m, r, &sweep.setup, c)?;
                }
                values.push(m);
            }
            println!("{}", json(&values)?);
            let invalid: Vec<String> = values
                .iter()
                .filter(|m| !m.valid)
                .map(|m| format!("{:.4} Hz: {}", m.frequency_hz, m.issues.join("; ")))
                .collect();
            if !invalid.is_empty() {
                return Err(format!(
                    "one or more measurements failed signal-quality or source-off checks:\n{}",
                    invalid.join("\n")
                ));
            }
        }
        ("validate", 5) => {
            let sweep = sweep(a[1])?;
            let cal = calibration(a[2])?;
            let resistance: f64 = number(a[3])?;
            let tolerance: f64 = number(a[4])?;
            if !resistance.is_finite()
                || resistance <= 0.0
                || !tolerance.is_finite()
                || tolerance <= 0.0
            {
                return Err("validation resistance and percent tolerance must be positive".into());
            }
            let mut pass = !sweep.records.is_empty();
            for r in &sweep.records {
                let mut m = analyze(r, sweep.setup.range_ohm)?;
                if flag("--allow-source-off-fail") {
                    waive_source_off(&mut m);
                }
                correct(&mut m, r, &sweep.setup, &cal)?;
                let error = (m.impedance_ohm - temper_lcr::Complex::new(resistance, 0.0)).abs()
                    / resistance
                    * 100.0;
                let ok = m.valid && error <= tolerance;
                pass &= ok;
                println!(
                    "{:.6} Hz: complex error {:.6}% {}{}",
                    m.frequency_hz,
                    error,
                    if ok { "PASS" } else { "FAIL" },
                    if m.issues.is_empty() {
                        String::new()
                    } else {
                        format!(" ({})", m.issues.join("; "))
                    }
                );
            }
            if !pass {
                return Err("independent-standard validation failed".into());
            }
        }
        _ => return Err(USAGE.into()),
    }
    Ok(())
}
fn main() {
    if let Err(e) = run(&env::args().collect::<Vec<_>>()) {
        eprintln!("{e}");
        process::exit(1);
    }
}
