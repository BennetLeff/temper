//! Rust-owned checks for the isolated Diodes Inc. BAV23C model experiment.
//!
//! The model is an alternative manufacturer model for BAV23C.  This binary
//! checks the retained ngspice outputs and applies the engineering arithmetic;
//! it does not promote the model to a production qualification.

use std::{env, fs, process::ExitCode};

#[derive(Debug, Clone, Copy)]
struct Record {
    temp_c: f64,
    isense_v: f64,
    diode_a: f64,
}

fn parse_records(text: &str) -> Vec<Record> {
    let mut out = Vec::new();
    let mut temp = None;
    let mut isense = None;
    for line in text.lines() {
        let t = line.trim();
        if t.starts_with("Doing analysis at TEMP =") {
            temp = Some(t.split_whitespace().nth(5).and_then(parse_finite).expect("finite temperature"));
            // A repeated analysis header with no result must not reuse the
            // previous analysis's ISENSE value.
            isense = None;
        } else if t.starts_with("v(isense) =") {
            assert!(temp.is_some(), "ISENSE result before analysis header");
            assert!(isense.is_none(), "duplicate ISENSE result");
            isense = Some(t.split('=').nth(1).and_then(parse_finite).expect("finite ISENSE"));
        } else if t.starts_with("@dclamp[id] =") {
            assert!(temp.is_some(), "diode result before analysis header");
            let isense_v = isense.take().expect("diode result without ISENSE");
            let diode_a = t.split('=').nth(1).and_then(parse_finite).expect("finite diode current");
            out.push(Record { temp_c: temp.unwrap(), isense_v, diode_a });
        }
    }
    assert!(isense.is_none(), "unterminated ISENSE result");
    out
}

fn nearly(a: f64, b: f64, tol: f64) -> bool { (a - b).abs() <= tol }

fn parse_finite(s: &str) -> Option<f64> {
    let value = s.trim().parse::<f64>().ok()?;
    value.is_finite().then_some(value)
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() != 5 {
        eprintln!("usage: vendor_clamp_checks <nominal.log> <temp.log> <fault.log> <reversed.log>");
        return ExitCode::from(2);
    }
    let nominal = fs::read_to_string(&args[1]).expect("read nominal log");
    let temp = fs::read_to_string(&args[2]).expect("read temperature log");
    let fault = fs::read_to_string(&args[3]).expect("read fault log");
    let reversed = fs::read_to_string(&args[4]).expect("read reversed log");

    let nominal_rows = parse_records(&nominal);
    assert_eq!(nominal_rows.len(), 1);
    let n = nominal_rows[0];
    // The nominal .op is the max-PCL shunt point, -0.438 V, at ngspice's
    // default 27 C.  This is a measured model output, not a datasheet limit.
    let nominal_shift_mv = (n.isense_v + 0.438) * 1_000.0;
    assert!(n.diode_a > 0.0);
    assert!(nearly(n.diode_a, nominal_shift_mv / 220_000.0, 2e-8));

    let temp_rows = parse_records(&temp);
    assert_eq!(temp_rows.len(), 5);
    let expected_temps = [-40.0, -20.0, 25.0, 85.0, 125.0];
    for (row, expected) in temp_rows.iter().zip(expected_temps) {
        assert!(nearly(row.temp_c, expected, 1e-9));
        assert!(row.diode_a >= 0.0);
        let shift_v = row.isense_v + 0.438;
        assert!(shift_v >= 0.0 && shift_v < 0.438);
        assert!(nearly(row.diode_a, shift_v / 220.0, 2e-7));
    }
    let t25 = temp_rows.iter().find(|r| nearly(r.temp_c, 25.0, 1e-9)).unwrap();
    let t125 = temp_rows.iter().find(|r| nearly(r.temp_c, 125.0, 1e-9)).unwrap();
    println!("PCL_MAX_ANCHOR_MODEL 25C: isense={:.6} V diode={:.3e} A shift={:.3} mV", t25.isense_v, t25.diode_a, (t25.isense_v + 0.438) * 1e3);
    println!("PCL_MAX_ANCHOR_MODEL 125C: isense={:.6} V diode={:.3e} A shift={:.3} mV", t125.isense_v, t125.diode_a, (t125.isense_v + 0.438) * 1e3);
    // The chosen 1 uA / 2 mV screen is intentionally reported, not treated
    // as a TI requirement.  This alternative model fails it at all points.
    assert!(temp_rows.iter().all(|r| r.diode_a >= 1e-6 || (r.isense_v + 0.438).abs() * 1e3 >= 2.0));

    let fault_rows = parse_records(&fault);
    assert_eq!(fault_rows.len(), 4);
    let expected_fault_temps = [-40.0, 25.0, 85.0, 125.0];
    for (row, expected) in fault_rows.iter().zip(expected_fault_temps) {
        assert!(nearly(row.temp_c, expected, 1e-9));
    }
    for row in &fault_rows {
        // The -5 V shunt excursion must leave the controller-side pin above
        // TI's -1.1 V bound in this model.  The diode current is checked from
        // the actual 220-ohm path: (ISENSE - SHUNT) / 220.
        assert!(row.isense_v > -1.1);
        let expected_a = (row.isense_v + 5.0) / 220.0;
        assert!(nearly(row.diode_a, expected_a, 2e-5));
        assert!(row.diode_a > 0.015);
    }
    println!("NEGATIVE_EXCURSION: all {} temperatures keep ISENSE above -1.1 V; diode current {:.3}..{:.3} mA",
        fault_rows.len(), fault_rows.iter().map(|r| r.diode_a).fold(f64::INFINITY, f64::min) * 1e3,
        fault_rows.iter().map(|r| r.diode_a).fold(f64::NEG_INFINITY, f64::max) * 1e3);

    let rev_rows = parse_records(&reversed);
    assert_eq!(rev_rows.len(), 1);
    assert!(rev_rows[0].isense_v < -1.1);
    println!("NEGATIVE_TOPOLOGY_CONTROL: reversed clamp leaves ISENSE={:.6} V (expected fail)", rev_rows[0].isense_v);
    println!("PASS bounded alternative-model checks; no production qualification implied");
    ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parser_pairs_temperature_and_values() {
        let text = "Doing analysis at TEMP = 25.000000 and TNOM = 27.000000\nv(isense) = -4.18e-1\n@dclamp[id] = 9.0e-5\n";
        let rows = parse_records(text);
        assert_eq!(rows.len(), 1);
        assert!(nearly(rows[0].temp_c, 25.0, 1e-9));
        assert!(nearly(rows[0].isense_v, -0.418, 1e-12));
        assert!(nearly(rows[0].diode_a, 90e-6, 1e-12));
    }

    #[test]
    fn resistor_shift_calculation_is_explicit() {
        let shunt = -0.438;
        let isense = -0.418288;
        let current = (isense - shunt) / 220.0;
        assert!(nearly(current, 89.6e-6, 1e-7));
    }
}
