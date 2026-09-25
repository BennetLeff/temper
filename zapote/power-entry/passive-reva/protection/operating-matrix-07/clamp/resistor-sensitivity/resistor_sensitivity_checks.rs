//! Rust-owned bounded resistor sensitivity extraction for the alternate
//! Diodes Inc. BAV23C model.  This is a model-only comparison: changing RIN
//! also changes the existing 1 nF ISENSE pole, so no dynamic equivalence is
//! implied.

use std::{env, fs, process::ExitCode};

#[derive(Clone, Copy, Debug)]
struct Row {
    shunt_v: f64,
    isense_v: f64,
}

fn finite(field: &str, context: &str) -> f64 {
    let v: f64 = field
        .parse()
        .unwrap_or_else(|_| panic!("{context}: malformed numeric field {field:?}"));
    assert!(v.is_finite(), "{context}: non-finite numeric field");
    v
}

fn read_sweep(path: &str) -> Vec<Row> {
    let text = fs::read_to_string(path).expect("read sweep");
    let mut rows: Vec<Row> = Vec::new();
    for (line_no, line) in text.lines().enumerate() {
        let context = format!("{path}:{}", line_no + 1);
        let fields: Vec<_> = line.split_whitespace().collect();
        assert_eq!(fields.len(), 4, "{context}: malformed width");
        // wrdata emits scale/value pairs.  Values are fields 1 and 3; both
        // scale fields must repeat exactly as a transport-integrity guard.
        let scale0 = finite(fields[0], &context);
        let shunt_v = finite(fields[1], &context);
        let scale1 = finite(fields[2], &context);
        let isense_v = finite(fields[3], &context);
        assert!((scale0 - scale1).abs() < 1e-12, "{context}: scale mismatch");
        if let Some(previous) = rows.last() {
            assert!(shunt_v < previous.shunt_v, "{context}: non-decreasing sweep");
        }
        rows.push(Row { shunt_v, isense_v });
    }
    assert!(rows.len() > 100, "{path}: sweep too short");
    rows
}

#[derive(Clone, Copy, Debug)]
struct Trip {
    shunt_v: f64,
    diode_a: f64,
}

fn crossing(rows: &[Row], target_isense_v: f64, rin_ohm: f64) -> Trip {
    for pair in rows.windows(2) {
        let (a, b) = (pair[0], pair[1]);
        if (a.isense_v - target_isense_v) * (b.isense_v - target_isense_v) <= 0.0
            && (a.isense_v - b.isense_v).abs() > 0.0
        {
            let fraction = (target_isense_v - a.isense_v) / (b.isense_v - a.isense_v);
            let shunt_v = a.shunt_v + fraction * (b.shunt_v - a.shunt_v);
            let diode_a = (target_isense_v - shunt_v) / rin_ohm;
            assert!(shunt_v.is_finite() && diode_a.is_finite());
            assert!(diode_a >= -1e-9, "negative diode current at crossing");
            return Trip { shunt_v, diode_a };
        }
    }
    panic!("target {target_isense_v} V not reached");
}

#[derive(Clone, Copy, Debug)]
struct Fault {
    temp_c: f64,
    isense_v: f64,
    diode_a: f64,
}

fn parse_fault_log(path: &str) -> Vec<Fault> {
    let text = fs::read_to_string(path).expect("read fault log");
    let mut rows = Vec::new();
    let mut current_temp: Option<f64> = None;
    let mut current_isense: Option<f64> = None;
    for (line_no, line) in text.lines().enumerate() {
        let context = format!("{path}:{}", line_no + 1);
        if let Some(rest) = line.strip_prefix("Doing analysis at TEMP = ") {
            let value = rest
                .split_whitespace()
                .next()
                .unwrap_or_else(|| panic!("{context}: malformed temperature header"));
            let temp = finite(value, &context);
            assert!(current_isense.is_none(), "{context}: stale isense before new OP");
            current_temp = Some(temp);
        } else if let Some(rest) = line.strip_prefix("v(isense) = ") {
            assert!(current_temp.is_some(), "{context}: isense without temperature");
            assert!(current_isense.is_none(), "{context}: duplicate isense");
            current_isense = Some(finite(rest.trim(), &context));
        } else if let Some(rest) = line.strip_prefix("@dclamp[id] = ") {
            let temp = current_temp.unwrap_or_else(|| panic!("{context}: diode current without temperature"));
            let isense = current_isense.take().unwrap_or_else(|| panic!("{context}: diode current without isense"));
            let diode_a = finite(rest.trim(), &context);
            rows.push(Fault { temp_c: temp, isense_v: isense, diode_a });
            current_temp = None;
        }
    }
    assert!(current_isense.is_none(), "fault log ended with incomplete OP");
    assert_eq!(rows.len(), 16, "fault log must contain 16 resistor/temperature points");
    rows
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() != 2 {
        eprintln!("usage: resistor_sensitivity_checks <sensitivity-folder>");
        return ExitCode::from(2);
    }
    let folder = &args[1];
    let resistors = [220.0, 100.0, 47.0, 22.0];
    let temperatures = [-40.0, 25.0, 85.0, 125.0];
    let targets = [("SOC", -0.285), ("PCL_typ", -0.400), ("PCL_max", -0.438)];

    for &rin in &resistors {
        println!("RIN {rin:.0} ohm");
        for &temp in &temperatures {
            let suffix = if temp < 0.0 { "m40".to_string() } else { format!("{temp:.0}") };
            let path = format!("{folder}/r{rin:.0}_{suffix}.tsv");
            let rows = read_sweep(&path);
            println!("  TEMP {temp:.0} C");
            for (name, target) in targets {
                let trip = crossing(&rows, target, rin);
                let effective_a = trip.shunt_v.abs() / 0.010;
                let ideal_a = target.abs() / 0.010;
                let extra_percent = (effective_a / ideal_a - 1.0) * 100.0;
                let shift_mv = (trip.shunt_v - target) * 1_000.0;
                println!(
                    "    {name:8} pin={target:.3} V: shunt={:.6} V, shunt_I={effective_a:.3} A, ideal10mR={ideal_a:.3} A, extra={extra_percent:.2}%, shift={shift_mv:.2} mV, diode={:.3e} A",
                    trip.shunt_v, trip.diode_a
                );
            }
        }
    }

    let fault_log = format!("{folder}/sensitivity.log");
    let faults = parse_fault_log(&fault_log);
    println!("FAULT VSHUNT=-5 V (Diodes Inc. model only)");
    let mut index = 0;
    for &rin in &resistors {
        for &temp in &temperatures {
            let row = faults[index];
            index += 1;
            assert!((row.temp_c - temp).abs() < 1e-9, "fault temperature/order mismatch");
            let kcl_a = (row.isense_v + 5.0) / rin;
            // The log prints six significant digits, so the absolute check
            // is intentionally looser than the underlying DC solve.
            assert!((kcl_a - row.diode_a).abs() < 2e-6, "fault KCL mismatch");
            println!(
                "  RIN={rin:.0} ohm TEMP={temp:.0} C: ISENSE={:.6} V, diode={:.6} A, KCL={kcl_a:.6} A",
                row.isense_v, row.diode_a
            );
        }
    }
    println!("PASS finite, complete, monotone sweeps; fault-log order/KCL validated");
    ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interpolates_crossing_with_resistor() {
        let rows = vec![
            Row { shunt_v: -0.2, isense_v: -0.1 },
            Row { shunt_v: -0.4, isense_v: -0.3 },
        ];
        let t = crossing(&rows, -0.2, 100.0);
        assert!((t.shunt_v + 0.3).abs() < 1e-12);
        assert!((t.diode_a - 1.0e-3).abs() < 1e-12);
    }

    #[test]
    #[should_panic(expected = "malformed width")]
    fn rejects_malformed_row() {
        let path = "/tmp/resistor-sensitivity-malformed.tsv";
        fs::write(path, "-1 -1\n").unwrap();
        let _ = read_sweep(path);
    }
}
