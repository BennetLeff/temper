use serde::Serialize;
use std::{env, fs, process};
use temper_lcr::rev_e::{self, SweepE};
use temper_lcr::transport::{Board, Device, DeviceE};
use temper_lcr::{
    advise, analyze, calibrate, capture_grid, check_grid, correct, file_revision, frequency_hz,
    hazard_error, parse_calibration, parse_sweep, waive_source_off, Advice, Calibration,
    CaptureOptions, Result, Sweep,
};

const USAGE: &str = "Usage (the board, Rev D protocol 2 or Rev E protocol 3, is selected from INFO; files carry their revision):
  temper-lcr info PORT
  temper-lcr selftest PORT
  temper-lcr rails PORT
  temper-lcr boot PORT
  temper-lcr capture PORT RANGE_OHM FIXTURE FREQ_HZ[,FREQ_HZ...] OUT.json [--allow-hazard] [--no-source-off] [--short-standard]   (Rev D)
  temper-lcr noise PORT RANGE_OHM FIXTURE FREQ_HZ[,FREQ_HZ...] OUT.json [--allow-hazard]   (Rev D)
  temper-lcr capture PORT RANGE_OHM FIXTURE FREQ_HZ[,FREQ_HZ...] OUT.json [--mv=MV] [--skip=PERIODS] [--periods=N | --seconds=S] [--no-source-off]   (Rev E; sets the range relay, FREQ_HZ must be exact; each point is followed by a zero-waveform source-off capture)
  temper-lcr capture-wave PORT RANGE_OHM FIXTURE WAVE.txt BIN[,BIN...] OUT.json [--skip=PERIODS] [--periods=N | --seconds=S]   (Rev E multitone)
  temper-lcr refcheck PORT RANGE_OHM FREQ_HZ[,FREQ_HZ...] OUT.json [--mv=MV] [--skip=PERIODS] [--periods=N | --seconds=S]   (Rev E; internal 1 kOhm reference via K4, DUT terminals open)
  temper-lcr range PORT 100|5000|100000   (Rev E)
  temper-lcr off PORT   (Rev E)
  temper-lcr codec PORT   (Rev E)
  temper-lcr reg PORT N   (Rev E)
  temper-lcr tone PORT CYCLES PERIOD MV   (Rev E; frequency = 187500 x CYCLES / PERIOD)
  temper-lcr tone-hz PORT FREQ_HZ MV   (Rev E; smallest exact PERIOD, at most 85 kHz)
  temper-lcr wave PORT WAVE.txt   (Rev E; int32 DAC words, at most +-1419797733)
  temper-lcr raw PORT COUNT OUT.json   (Rev E; up to 8192 consecutive frames)
  temper-lcr tone-plan RANGE_OHM FREQ_HZ[,FREQ_HZ...]   (Rev E, no device: exact CYCLES/PERIOD, default SKIP and PERIODS)
  temper-lcr advise-grid FREQ_HZ[,FREQ_HZ...]   (Rev D)
  temper-lcr analyze CAPTURE.json [CAL.json] [--allow-source-off-fail]
  temper-lcr calibrate SHORT.json LOAD1.json LOAD1_OHM LOAD2.json LOAD2_OHM CAL.json [--allow-source-off-fail]
  temper-lcr calibrate SHORT.json LOAD1.json LOAD1_NAME LOAD2.json LOAD2_NAME CAL.json --standards=KIT.json [--allow-source-off-fail]   (Rev E; characterized standards, the short is SHORT)
  temper-lcr validate CAPTURE.json CAL.json KNOWN_OHM TOLERANCE_PERCENT [--allow-source-off-fail]
  temper-lcr validate CAPTURE.json CAL.json NAME TOLERANCE_PERCENT --standards=KIT.json [--allow-source-off-fail]   (Rev E; complex error against the characterized standard)";

fn text(path: &str) -> Result<String> {
    fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))
}
fn sweep(path: &str) -> Result<Sweep> {
    parse_sweep(&text(path)?).map_err(|e| format!("{path}: {e}"))
}
fn standards(path: &str) -> Result<rev_e::StandardsFileE> {
    rev_e::parse_standards_e(&text(path)?).map_err(|e| format!("{path}: {e}"))
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

/// Options of the Rev E capture commands, parsed from `--name=value` flags.
#[derive(Default)]
struct EOptions {
    mv: Option<u32>,
    skip: Option<u32>,
    periods: Option<u32>,
    seconds: Option<f64>,
}
const E_VALUE_FLAGS: [&str; 4] = ["--mv", "--skip", "--periods", "--seconds"];
fn flag_value<'a>(flags: &[&'a str], name: &str) -> Option<&'a str> {
    flags
        .iter()
        .find_map(|f| f.strip_prefix(name).and_then(|r| r.strip_prefix('=')))
}
fn e_options(flags: &[&str]) -> Result<EOptions> {
    let get = |name: &str| flag_value(flags, name);
    let o = EOptions {
        mv: get("--mv").map(number).transpose()?,
        skip: get("--skip").map(number).transpose()?,
        periods: get("--periods").map(number).transpose()?,
        seconds: get("--seconds").map(number).transpose()?,
    };
    if o.periods.is_some() && o.seconds.is_some() {
        return Err("--periods and --seconds are alternatives".into());
    }
    Ok(o)
}
impl EOptions {
    fn any(&self) -> bool {
        self.mv.is_some() || self.skip.is_some() || self.periods.is_some() || self.seconds.is_some()
    }
    /// SUMMED periods: explicit, from seconds, or None for the default length.
    fn periods_for(&self, period: u32) -> Result<Option<u32>> {
        match (self.periods, self.seconds) {
            (Some(n), _) => Ok(Some(n)),
            (None, Some(s)) => rev_e::periods_for_seconds(s, period).map(Some),
            (None, None) => Ok(None),
        }
    }
}
fn rev_e_only(board: Board, command: &str) -> Result<DeviceE> {
    match board {
        Board::E(d) => Ok(d),
        Board::D(_) => Err(format!(
            "'{command}' is a Rev E (protocol 3) command; this board is Rev D"
        )),
    }
}
fn rev_d_only(board: Board, command: &str) -> Result<Device> {
    match board {
        Board::D(d) => Ok(d),
        Board::E(_) => Err(format!(
            "'{command}' is a Rev D (protocol 2) command; this board is Rev E"
        )),
    }
}
/// Revision named by a capture or calibration file; None if it is not JSON or names none, so
/// the Rev D loaders report such files as they always have.
fn revision_of(path: &str) -> Option<String> {
    let value: serde_json::Value = serde_json::from_str(&fs::read_to_string(path).ok()?).ok()?;
    file_revision(&value)
}
fn is_rev_e(path: &str) -> bool {
    revision_of(path).as_deref() == Some(rev_e::HARDWARE_REVISION_E)
}
fn sweep_e(path: &str) -> Result<SweepE> {
    rev_e::parse_sweep_e(&text(path)?).map_err(|e| format!("{path}: {e}"))
}
fn warn_sof(hz: f64, seconds: f64) {
    let response = rev_e::sof_response(hz, seconds);
    if response > 0.1 {
        eprintln!(
            "warning: {hz} Hz is within the reach of a USB start-of-frame line (a 1 kHz multiple, +-560 ppm); a {seconds:.2} s coherent capture rejects it only to {response:.2} of its amplitude. Prefer a frequency a few hertz away if the source-off noise is not already quiet."
        );
    }
}
/// Advisory above 0.429 fs (see [`rev_e::image_advisory`]); the capture still runs.
fn warn_image(hz: f64) {
    if let Some(advice) = rev_e::image_advisory(hz) {
        eprintln!("warning: {advice}");
    }
}
fn capture_e(
    d: &mut DeviceE,
    freqs: &[f64],
    out: &str,
    o: &EOptions,
    source_off: bool,
) -> Result<()> {
    // Every frequency must be exact before the instrument is touched.
    for &hz in freqs {
        rev_e::tone_for_hz(hz)?;
    }
    let mv = o.mv.unwrap_or(rev_e::DEFAULT_TONE_MV);
    rev_e::check_tone(1, rev_e::MAX_PERIOD, mv)?;
    d.selftest()?;
    d.rails()?;
    d.range(d.setup.range_ohm)?;
    let mut records = Vec::new();
    let mut source_off_failures = Vec::new();
    for &hz in freqs {
        let (_, period) = rev_e::tone_for_hz(hz)?;
        let seconds = rev_e::capture_seconds(
            o.skip.unwrap_or(0),
            o.periods_for(period)?
                .unwrap_or_else(|| rev_e::default_periods(period)),
            period,
        );
        warn_sof(hz, seconds);
        warn_image(hz);
        let mut record = d.capture_tone(hz, mv, o.skip, o.periods_for(period)?)?;
        eprintln!(
            "captured {hz} Hz: {} periods of {} frames after skipping {}, clipping A {} B {}",
            record.periods,
            record.period,
            record.skip,
            record.clipped(0),
            record.clipped(1)
        );
        if source_off {
            // A failed check does not stop the sweep: the file is saved with the diagnostics.
            let check = d.source_off_check(&record)?;
            eprintln!(
                "source-off check {:.4} Hz: {} (A {:.2e}, B {:.2e} of source-on; limit {:.0e})",
                check.frequency_hz,
                if check.pass { "PASS" } else { "FAIL" },
                check.channels[0].ratio,
                check.channels[1].ratio,
                check.limit_ratio
            );
            if !check.pass {
                source_off_failures.push(format!("{hz} Hz: {}", check.diagnostic));
            }
            record.source_off_check = Some(check);
        }
        records.push(record);
    }
    d.off()?;
    write(
        out,
        &SweepE {
            setup: d.setup.clone(),
            records,
        },
    )?;
    if !source_off_failures.is_empty() {
        return Err(format!(
            "{} point(s) failed the source-off check (saved to {out} with diagnostics; analyze refuses them unless --allow-source-off-fail):\n{}",
            source_off_failures.len(),
            source_off_failures.join("\n")
        ));
    }
    Ok(())
}
/// `REFCAPTURE` per frequency: the internal 1 kOhm reference on `range`, for a drift or self
/// check. The file is an ordinary Rev E capture with fixture `internal-reference-1k`.
fn refcheck_e(d: &mut DeviceE, range: u32, freqs: &[f64], out: &str, o: &EOptions) -> Result<()> {
    for &hz in freqs {
        rev_e::tone_for_hz(hz)?;
    }
    let mv = match o.mv {
        Some(mv) => mv,
        None => rev_e::reference_default_mv(range)?,
    };
    rev_e::check_tone(1, rev_e::MAX_PERIOD, mv)?;
    d.selftest()?;
    d.rails()?;
    let mut records = Vec::new();
    for &hz in freqs {
        let (_, period) = rev_e::tone_for_hz(hz)?;
        warn_image(hz);
        let record = d.reference_tone(range, hz, mv, o.skip, o.periods_for(period)?)?;
        records.push(record);
    }
    d.off()?;
    let mut setup = d.setup.clone();
    setup.range_ohm = range;
    setup.fixture = rev_e::REFERENCE_FIXTURE.into();
    for record in &records {
        for m in rev_e::analyze_e(record, range)? {
            println!(
                "{} Hz, {range} ohm range, {mv} mV: |Z| {:.4} ohm ({:+.4} % from 1 kOhm), phase {:.4} deg, uncalibrated{}",
                m.frequency_hz,
                m.magnitude_ohm,
                (m.magnitude_ohm / rev_e::REFERENCE_OHM - 1.0) * 100.0,
                m.phase_degrees,
                if m.issues.is_empty() {
                    String::new()
                } else {
                    format!(" ({})", m.issues.join("; "))
                }
            );
        }
    }
    write(out, &SweepE { setup, records })
}
fn capture_wave_e(
    d: &mut DeviceE,
    words_file: &str,
    bins: &str,
    out: &str,
    o: &EOptions,
) -> Result<()> {
    let words =
        rev_e::parse_wave_text(&text(words_file)?).map_err(|e| format!("{words_file}: {e}"))?;
    let period = words.len() as u32;
    let bins: Vec<u32> = bins.split(',').map(number).collect::<Result<_>>()?;
    rev_e::check_bins(&bins, period)?;
    for &bin in &bins {
        warn_image(rev_e::tone_frequency_hz(bin, period));
    }
    d.selftest()?;
    d.rails()?;
    d.range(d.setup.range_ohm)?;
    let record = d.capture_wave(&words, &bins, o.skip, o.periods_for(period)?)?;
    d.off()?;
    eprintln!(
        "captured {} bins of a {period}-frame waveform: {} periods after skipping {}",
        bins.len(),
        record.periods,
        record.skip
    );
    write(
        out,
        &SweepE {
            setup: d.setup.clone(),
            records: vec![record],
        },
    )
}
/// Notes on stderr how many records of a Rev E file carry no source-off check. Rev D reports
/// such files the same way: not checked, not refused.
fn note_unchecked(sweep: &SweepE) {
    let unchecked = sweep
        .records
        .iter()
        .filter(|r| r.source_off_check.is_none())
        .count();
    if unchecked > 0 {
        eprintln!(
            "note: {unchecked} of {} record(s) not source-off checked (captured with --no-source-off, a waveform record, or a file from before the check)",
            sweep.records.len()
        );
    }
}
fn analyze_e_file(a: &[&str], waive: bool) -> Result<()> {
    let sweep = sweep_e(a[1])?;
    sweep.setup.validate()?;
    note_unchecked(&sweep);
    let cal = a
        .get(2)
        .map(|path| rev_e::parse_calibration_e(&text(path)?).map_err(|e| format!("{path}: {e}")))
        .transpose()?;
    let mut values = Vec::new();
    for r in &sweep.records {
        for mut m in rev_e::analyze_e(r, sweep.setup.range_ohm)? {
            if waive {
                rev_e::waive_source_off_e(&mut m);
            }
            if let Some(c) = &cal {
                rev_e::correct_e(&mut m, &sweep.setup, c)?;
            }
            values.push(m);
        }
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
    Ok(())
}
fn validate_e_file(a: &[&str], waive: bool, standards_path: Option<&str>) -> Result<()> {
    let sweep = sweep_e(a[1])?;
    note_unchecked(&sweep);
    let cal = rev_e::parse_calibration_e(&text(a[2])?).map_err(|e| format!("{}: {e}", a[2]))?;
    let known = match standards_path {
        Some(path) => standards(path)?.get(a[3])?,
        None => rev_e::StandardE::resistor(number(a[3])?),
    };
    let tolerance: f64 = number(a[4])?;
    if !known.r_ohm.is_finite() || known.r_ohm <= 0.0 || !tolerance.is_finite() || tolerance <= 0.0
    {
        return Err("validation resistance and percent tolerance must be positive".into());
    }
    let mut pass = !sweep.records.is_empty();
    for r in &sweep.records {
        for mut m in rev_e::analyze_e(r, sweep.setup.range_ohm)? {
            if waive {
                rev_e::waive_source_off_e(&mut m);
            }
            rev_e::correct_e(&mut m, &sweep.setup, &cal)?;
            let truth = known.impedance(m.frequency_hz);
            let error = (m.impedance_ohm - truth).abs() / truth.abs() * 100.0;
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
    }
    if !pass {
        return Err("independent-standard validation failed".into());
    }
    Ok(())
}

/// Rev D's frequency-hazard check (R1): refuses a hazardous grid, or warns under `--allow-hazard`.
fn hazard_precheck(freqs: &[f64], allow_hazard: bool) -> Result<()> {
    for (hz, report) in freqs.iter().zip(check_grid(freqs, allow_hazard)?) {
        if report.hazardous {
            let warning = hazard_error(*hz, &report).replace('\n', "\nwarning: ");
            eprintln!("warning: --allow-hazard: {warning}");
        }
    }
    Ok(())
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
    let valued: &[&str] = match command {
        "calibrate" | "validate" => &["--standards"],
        "capture" => &E_VALUE_FLAGS,
        "capture-wave" => &["--skip", "--periods", "--seconds"],
        "refcheck" => &E_VALUE_FLAGS,
        _ => &[],
    };
    if let Some(bad) = flags.iter().find(|f| {
        !known.contains(f)
            && !valued
                .iter()
                .any(|v| f.strip_prefix(v).is_some_and(|r| r.starts_with('=')))
    }) {
        return Err(format!("unknown option {bad} for '{command}'\n{USAGE}"));
    }
    let flag = |name: &str| flags.contains(&name);
    match (command, a.len()) {
        ("info" | "selftest", 2) => match Board::open(a[1], 100, "diagnostic")? {
            Board::D(mut d) => {
                d.selftest()?;
                println!("{}", json(&d.setup)?);
                println!("ADC dual-channel fixed-pattern link test: PASS");
                println!("{}", json(&d.rails()?)?);
            }
            Board::E(mut d) => {
                d.selftest()?;
                let info = d.refresh_info()?;
                println!("{}", json(&d.setup)?);
                println!("{}", json(&info)?);
                println!("codec TDM digital-loopback self-test: PASS");
                println!("{}", json(&d.codec()?)?);
                println!("{}", json(&d.rails()?)?);
            }
        },
        ("rails", 2) => match Board::open(a[1], 100, "diagnostic")? {
            Board::D(mut d) => println!("{}", json(&d.rails()?)?),
            Board::E(mut d) => println!("{}", json(&d.rails()?)?),
        },
        ("boot", 2) => {
            match Board::open(a[1], 100, "diagnostic")? {
                Board::D(mut d) => d.boot()?,
                Board::E(mut d) => d.boot()?,
            }
            println!("rebooted into the USB bootloader: copy the UF2 to the RPI-RP2 drive");
        }
        ("refcheck", 5) => {
            let range: u32 = number(a[2])?;
            let freqs = frequencies(a[3])?;
            let mut d = rev_e_only(Board::open(a[1], range, rev_e::REFERENCE_FIXTURE)?, command)?;
            refcheck_e(&mut d, range, &freqs, a[4], &e_options(&flags)?)?;
        }
        ("range", 3) => {
            let mut d = rev_e_only(Board::open(a[1], number(a[2])?, "diagnostic")?, command)?;
            d.range(number(a[2])?)?;
            println!("range {} ohm selected", a[2]);
        }
        ("off", 2) => {
            let mut d = rev_e_only(Board::open(a[1], 100, "diagnostic")?, command)?;
            d.off()?;
            println!("source off");
        }
        ("codec", 2) => {
            let mut d = rev_e_only(Board::open(a[1], 100, "diagnostic")?, command)?;
            println!("{}", json(&d.codec()?)?);
        }
        ("reg", 3) => {
            let mut d = rev_e_only(Board::open(a[1], 100, "diagnostic")?, command)?;
            let register: u32 = number(a[2])?;
            println!("REG {register} = {}", d.reg(register)?);
        }
        ("tone", 5) => {
            let mut d = rev_e_only(Board::open(a[1], 100, "diagnostic")?, command)?;
            let (cycles, period, mv): (u32, u32, u32) =
                (number(a[2])?, number(a[3])?, number(a[4])?);
            d.tone(cycles, period, mv)?;
            println!(
                "tone {} Hz ({cycles}/{period}) at {mv} mV",
                rev_e::tone_frequency_hz(cycles, period)
            );
        }
        ("tone-hz", 4) => {
            let mut d = rev_e_only(Board::open(a[1], 100, "diagnostic")?, command)?;
            let (cycles, period) = d.tone_hz(number(a[2])?, number(a[3])?)?;
            println!(
                "tone {} Hz ({cycles}/{period}) at {} mV",
                rev_e::tone_frequency_hz(cycles, period),
                a[3]
            );
        }
        ("wave", 3) => {
            let mut d = rev_e_only(Board::open(a[1], 100, "diagnostic")?, command)?;
            let words =
                rev_e::parse_wave_text(&text(a[2])?).map_err(|e| format!("{}: {e}", a[2]))?;
            d.wave(&words)?;
            println!("waveform of {} frames playing", words.len());
        }
        ("raw", 4) => {
            let mut d = rev_e_only(Board::open(a[1], 100, "diagnostic")?, command)?;
            let (header, frames) = d.raw(number(a[2])?)?;
            let stats = rev_e::raw_stats(&frames);
            write(
                a[3],
                &serde_json::json!({
                    "setup": d.setup,
                    "extremes": header,
                    "stats": stats,
                    "frames": frames,
                }),
            )?;
            println!("{}", json(&stats)?);
        }
        ("capture-wave", 7) => {
            let mut d = rev_e_only(Board::open(a[1], number(a[2])?, a[3])?, command)?;
            capture_wave_e(&mut d, a[4], a[5], a[6], &e_options(&flags)?)?;
        }
        ("capture" | "noise", 6) => {
            let freqs = frequencies(a[4])?;
            let board = match Board::open(a[1], number(a[2])?, a[3]) {
                Ok(board) => board,
                Err(open_error) => {
                    // Rev D refused hazardous grids before opening the port; keep that order
                    // when the board cannot be asked which revision it is.
                    hazard_precheck(&freqs, flag("--allow-hazard")).map_err(|hazard| {
                        format!("{hazard}\n(the port could not be opened ({open_error}), so the board revision is unknown: this Rev D hazard check does not apply to a Rev E board)")
                    })?;
                    return Err(open_error);
                }
            };
            let mut d = match board {
                Board::E(mut d) => {
                    if command == "noise" {
                        return Err("'noise' is a Rev D command: on Rev E run 'off PORT', then 'raw PORT COUNT OUT.json'".into());
                    }
                    if flag("--allow-hazard") || flag("--short-standard") {
                        return Err("--allow-hazard and --short-standard are Rev D options (DDS hazards and the short-standard source-off judgement); this board is Rev E".into());
                    }
                    return capture_e(
                        &mut d,
                        &freqs,
                        a[5],
                        &e_options(&flags)?,
                        !flag("--no-source-off"),
                    );
                }
                board => rev_d_only(board, command)?,
            };
            if e_options(&flags)?.any() {
                return Err(
                    "--mv, --skip, --periods and --seconds are Rev E options; this board is Rev D"
                        .into(),
                );
            }
            let options = CaptureOptions {
                source_on: command == "capture",
                allow_hazard: flag("--allow-hazard"),
                source_off: !flag("--no-source-off"),
                short_standard: flag("--short-standard"),
            };
            hazard_precheck(&freqs, options.allow_hazard)?;
            d.selftest()?;
            d.rails()?;
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
        ("tone-plan", 3) => {
            let range: u32 = number(a[1])?;
            let plan = frequencies(a[2])?
                .into_iter()
                .map(|hz| rev_e::tone_plan(range, hz))
                .collect::<Result<Vec<_>>>()?;
            println!("{}", json(&plan)?);
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
        ("calibrate", 7) if is_rev_e(a[1]) => {
            let (short, load1, load2) = (sweep_e(a[1])?, sweep_e(a[2])?, sweep_e(a[4])?);
            for sweep in [&short, &load1, &load2] {
                note_unchecked(sweep);
            }
            let waive = flag("--allow-source-off-fail");
            let cal = match flag_value(&flags, "--standards") {
                Some(path) => {
                    let kit = standards(path)?;
                    rev_e::calibrate_e_checked(
                        &short,
                        kit.get("SHORT")?,
                        &load1,
                        kit.get(a[3])?,
                        &load2,
                        kit.get(a[5])?,
                        Some(&format!("{} ({path})", kit.kit)),
                        waive,
                    )?
                }
                None => rev_e::calibrate_e_waiving(
                    &short,
                    &load1,
                    number(a[3])?,
                    &load2,
                    number(a[5])?,
                    waive,
                )?,
            };
            write(a[6], &cal)?;
            println!(
                "Saved {} frequency-specific calibration points.",
                cal.points.len()
            );
        }
        ("calibrate" | "validate", 5 | 7)
            if !is_rev_e(a[1]) && flag_value(&flags, "--standards").is_some() =>
        {
            return Err("--standards applies to Rev E captures only".into());
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
        ("analyze", 2 | 3) if is_rev_e(a[1]) => {
            analyze_e_file(&a, flag("--allow-source-off-fail"))?
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
        ("validate", 5) if is_rev_e(a[1]) => validate_e_file(
            &a,
            flag("--allow-source-off-fail"),
            flag_value(&flags, "--standards"),
        )?,
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
