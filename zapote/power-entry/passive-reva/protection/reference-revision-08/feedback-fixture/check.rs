use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader};
use std::process::ExitCode;

const HEADER: &str = "time v(vb) v(vd) v(vb_sense) v(vd_sense) v(gate_old) v(gate_cand) v(xold.ov) v(xcand.ov) v(xold.pwm_hold) v(xcand.pwm_hold) v(xold.raw) v(xcand.raw)";

#[derive(Clone, Copy)]
struct Row {
    t: f64,
    vb: f64,
    vd: f64,
    vb_sense: f64,
    vd_sense: f64,
    gate_old: f64,
    gate_cand: f64,
    ov_old: f64,
    ov_cand: f64,
    raw_old: f64,
    raw_cand: f64,
}

fn parse<R: BufRead>(reader: R) -> Result<Vec<Row>, String> {
    let mut lines = reader.lines();
    let header = lines
        .next()
        .ok_or("missing trace header")?
        .map_err(|e| e.to_string())?;
    if header.split_whitespace().collect::<Vec<_>>()
        != HEADER.split_whitespace().collect::<Vec<_>>()
    {
        return Err("trace header/order does not match feedback.cir".into());
    }
    let mut rows: Vec<Row> = Vec::new();
    for (line_no, line) in lines.enumerate() {
        let line_no = line_no + 2;
        let text = line.map_err(|e| format!("line {line_no}: {e}"))?;
        if text.trim().is_empty() {
            return Err(format!("line {line_no}: blank row"));
        }
        let values = text
            .split_whitespace()
            .map(|s| {
                s.parse::<f64>()
                    .map_err(|_| format!("line {line_no}: invalid number"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        if values.len() != 13 || values.iter().any(|v| !v.is_finite()) {
            return Err(format!("line {line_no}: expected 13 finite values"));
        }
        if let Some(previous) = rows.last() {
            let dt = values[0] - previous.t;
            if dt <= 0.0 || dt > 20.0e-9 + 1.0e-15 {
                return Err(format!(
                    "line {line_no}: non-increasing or >20 ns timestep ({dt:.4e})"
                ));
            }
        }
        rows.push(Row {
            t: values[0],
            vb: values[1],
            vd: values[2],
            vb_sense: values[3],
            vd_sense: values[4],
            gate_old: values[5],
            gate_cand: values[6],
            ov_old: values[7],
            ov_cand: values[8],
            raw_old: values[11],
            raw_cand: values[12],
        });
    }
    if rows.len() < 1000 || rows[0].t.abs() > 1.0e-12 {
        return Err("trace is too short or missing t=0 startup".into());
    }
    let end = rows.last().unwrap().t;
    if (end - 500.0e-6).abs() > 1.0e-12 {
        return Err(format!("wrong trace end time: {end:.12e}"));
    }
    Ok(rows)
}

fn window<'a>(rows: &'a [Row], lo: f64, hi: f64) -> Vec<&'a Row> {
    rows.iter().filter(|r| r.t >= lo && r.t <= hi).collect()
}

fn pulse_count(window: &[&Row], candidate: bool) -> usize {
    let mut count = 0;
    let mut was_high = false;
    for row in window {
        let high = if candidate {
            row.gate_cand > 7.5
        } else {
            row.gate_old > 7.5
        };
        if high && !was_high {
            count += 1;
        }
        was_high = high;
    }
    count
}

fn range(
    window: &[&Row],
    name: &str,
    values: impl Fn(&Row) -> f64,
    lo: f64,
    hi: f64,
) -> Result<(), String> {
    if window.iter().any(|row| {
        let value = values(row);
        !value.is_finite() || value < lo || value > hi
    }) {
        return Err(format!("{name}: value outside [{lo}, {hi}]"));
    }
    Ok(())
}

fn validate(rows: &[Row]) -> Result<(), String> {
    if rows.len() < 1000 {
        return Err("trace is too short".into());
    }
    if rows.iter().any(|row| {
        [
            row.t,
            row.vb,
            row.vd,
            row.vb_sense,
            row.vd_sense,
            row.gate_old,
            row.gate_cand,
            row.ov_old,
            row.ov_cand,
            row.raw_old,
            row.raw_cand,
        ]
        .iter()
        .any(|value| !value.is_finite())
    }) {
        return Err("trace contains a non-finite value".into());
    }
    if rows[0].t.abs() > 1.0e-12 {
        return Err("trace does not start at t=0".into());
    }
    for pair in rows.windows(2) {
        let dt = pair[1].t - pair[0].t;
        if !pair[1].t.is_finite() || dt <= 0.0 || dt > 20.0e-9 + 1.0e-15 {
            return Err("trace has non-increasing, non-finite, or >20 ns timestep".into());
        }
    }
    let end = rows.last().ok_or("trace has no final row")?.t;
    if (end - 500.0e-6).abs() > 1.0e-12 {
        return Err(format!("wrong trace end time: {end:.12e}"));
    }
    let base = window(rows, 20e-6, 90e-6);
    let vd_trip = window(rows, 110e-6, 145e-6);
    let vd_recovery = window(rows, 180e-6, 240e-6);
    let vb_trip = window(rows, 260e-6, 300e-6);
    let final_recovery = window(rows, 340e-6, 480e-6);
    for (name, w) in [
        ("baseline", &base),
        ("VD trip", &vd_trip),
        ("VD recovery", &vd_recovery),
        ("VB trip", &vb_trip),
        ("final recovery", &final_recovery),
    ] {
        if w.is_empty() {
            return Err(format!("{name}: missing assertion window"));
        }
    }
    range(&base, "baseline VB", |r| r.vb, 389.0, 391.0)?;
    range(&base, "baseline VD", |r| r.vd, 389.0, 391.0)?;
    range(&base, "baseline VB_SENSE", |r| r.vb_sense, 4.95, 5.06)?;
    range(&base, "baseline VD_SENSE", |r| r.vd_sense, 4.95, 5.06)?;
    range(&vd_trip, "VD-trip VB", |r| r.vb, 389.0, 391.0)?;
    range(&vd_trip, "VD-trip VD", |r| r.vd, 449.0, 451.0)?;
    range(&vd_trip, "VD-trip VB_SENSE", |r| r.vb_sense, 4.95, 5.06)?;
    range(&vd_trip, "VD-trip VD_SENSE", |r| r.vd_sense, 5.4, 5.9)?;
    range(&vd_recovery, "VD-recovery VB", |r| r.vb, 389.0, 391.0)?;
    range(&vd_recovery, "VD-recovery VD", |r| r.vd, 389.0, 391.0)?;
    range(
        &vd_recovery,
        "VD-recovery VB_SENSE",
        |r| r.vb_sense,
        4.95,
        5.2,
    )?;
    range(
        &vd_recovery,
        "VD-recovery VD_SENSE",
        |r| r.vd_sense,
        4.95,
        5.2,
    )?;
    range(&vb_trip, "VB-trip VB", |r| r.vb, 449.0, 451.0)?;
    range(&vb_trip, "VB-trip VD", |r| r.vd, 389.0, 391.0)?;
    range(&vb_trip, "VB-trip VB_SENSE", |r| r.vb_sense, 5.4, 5.9)?;
    range(&vb_trip, "VB-trip VD_SENSE", |r| r.vd_sense, 4.95, 5.06)?;
    range(&final_recovery, "final-recovery VB", |r| r.vb, 389.0, 391.0)?;
    range(&final_recovery, "final-recovery VD", |r| r.vd, 389.0, 391.0)?;
    range(
        &final_recovery,
        "final-recovery VB_SENSE",
        |r| r.vb_sense,
        4.95,
        5.2,
    )?;
    range(
        &final_recovery,
        "final-recovery VD_SENSE",
        |r| r.vd_sense,
        4.95,
        5.2,
    )?;
    if base.iter().any(|r| r.ov_old > 2.5 || r.ov_cand > 2.5) {
        return Err("baseline OVP is not clear".into());
    }
    if pulse_count(&base, false) < 3 || pulse_count(&base, true) < 3 {
        return Err("baseline: both controllers lack PWM pulse activity".into());
    }
    if vd_trip.iter().any(|r| r.ov_cand <= 2.5) || vd_trip.iter().any(|r| r.ov_old > 2.5) {
        return Err("VD-only excursion did not hold candidate OVP only".into());
    }
    if vd_trip.iter().any(|r| r.gate_cand > 0.1) || pulse_count(&vd_trip, false) < 3 {
        return Err("VD-only excursion did not suppress only candidate gate".into());
    }
    if vd_recovery
        .iter()
        .any(|r| r.ov_old > 2.5 || r.ov_cand > 2.5)
        || pulse_count(&vd_recovery, true) < 3
    {
        return Err("candidate did not recover after VD returned to 390 V".into());
    }
    if vb_trip.iter().any(|r| r.ov_old <= 2.5) || vb_trip.iter().any(|r| r.ov_cand > 2.5) {
        return Err("VB-only excursion did not hold old-controller OVP only".into());
    }
    if vb_trip.iter().any(|r| r.gate_old > 0.1) || pulse_count(&vb_trip, true) < 3 {
        return Err("VB-only excursion did not suppress only old gate".into());
    }
    if final_recovery
        .iter()
        .any(|r| r.ov_old > 2.5 || r.ov_cand > 2.5)
        || pulse_count(&final_recovery, false) < 3
        || pulse_count(&final_recovery, true) < 3
    {
        return Err("both controllers failed post-excursion recovery".into());
    }
    if !vd_trip.iter().any(|r| r.raw_cand > 2.5) || !vb_trip.iter().any(|r| r.raw_old > 2.5) {
        return Err("raw comparator pulse witness missing".into());
    }
    Ok(())
}

fn main() -> ExitCode {
    let result = (|| -> Result<(), String> {
        let mut args = env::args().skip(1);
        let first = args
            .next()
            .ok_or("usage: check [--self-test] TRACE|-".to_string())?;
        let self_test = first == "--self-test";
        let input = if self_test { args.next() } else { Some(first) }
            .ok_or("usage: check [--self-test] TRACE|-".to_string())?;
        let reader: Box<dyn BufRead> = if input == "-" {
            Box::new(BufReader::new(io::stdin()))
        } else {
            Box::new(BufReader::new(
                File::open(input).map_err(|e| e.to_string())?,
            ))
        };
        let rows = parse(reader)?;
        validate(&rows)?;
        let base = window(&rows, 20e-6, 90e-6);
        if self_test {
            let mut nonfinite = rows.clone();
            nonfinite[100].gate_old = f64::NAN;
            if validate(&nonfinite).is_ok() {
                return Err("negative nonfinite mutation unexpectedly passed".into());
            }
            let mut backwards = rows.clone();
            backwards[100].t = backwards[99].t;
            if validate(&backwards).is_ok() {
                return Err("negative duplicate-time mutation unexpectedly passed".into());
            }
            let incomplete = rows[..rows.len() - 100].to_vec();
            if validate(&incomplete).is_ok() {
                return Err("negative incomplete-end mutation unexpectedly passed".into());
            }
            let mut missing_ovp = rows.clone();
            for row in &mut missing_ovp {
                if (110e-6..=145e-6).contains(&row.t) {
                    row.ov_cand = 0.0;
                }
            }
            if validate(&missing_ovp).is_ok() {
                return Err("negative missing-OVP mutation unexpectedly passed".into());
            }
            let mut gate_on = rows.clone();
            for row in &mut gate_on {
                if (110e-6..=145e-6).contains(&row.t) {
                    row.gate_cand = 15.0;
                }
            }
            if validate(&gate_on).is_ok() {
                return Err("negative gate-off mutation unexpectedly passed".into());
            }
            println!("PASS negative mutations: nonfinite, duplicate time, incomplete end, missing OVP, and gate-off failure rejected");
        }
        println!(
            "PASS trace shape: {} rows, end={:.3} us",
            rows.len(),
            rows.last().unwrap().t * 1e6
        );
        println!(
            "PASS baseline PWM: old={} candidate={} rising gate pulses",
            pulse_count(&base, false),
            pulse_count(&base, true)
        );
        println!("PASS VD-only 450 V: candidate OVP asserted and candidate gate off; old gate remained active");
        println!("PASS recovery after VD restore: candidate gate resumed");
        println!("PASS VB-only 450 V: old OVP asserted and old gate off; candidate OVP stayed clear and candidate gate remained active");
        println!("PASS final recovery: both controllers resumed PWM");
        Ok(())
    })();
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("FAIL {error}");
            ExitCode::FAILURE
        }
    }
}
