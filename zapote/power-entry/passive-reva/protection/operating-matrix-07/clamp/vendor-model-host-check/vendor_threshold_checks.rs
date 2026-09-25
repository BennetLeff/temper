//! Rust-owned effective SOC/PCL trip extraction from ngspice DC sweeps.
//! The source resistor is the 10 mOhm PFC shunt; the 220 ohm element is the
//! controller-side ISENSE protection resistor.

use std::{env, fs, process::ExitCode};

#[derive(Clone, Copy, Debug)]
struct Row { shunt_v: f64, isense_v: f64 }

fn finite(s: &str) -> f64 {
    let value: f64 = s.parse().expect("finite numeric field");
    assert!(value.is_finite(), "non-finite numeric field");
    value
}

fn read_sweep(path: &str) -> Vec<Row> {
    let text = fs::read_to_string(path).expect("read sweep");
    let mut rows: Vec<Row> = Vec::new();
    for (line_no, line) in text.lines().enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        assert_eq!(fields.len(), 4, "{}:{} malformed width", path, line_no + 1);
        // wrdata emits scale/value pairs for each vector.  The values are at
        // positions 1 and 3; positions 0 and 2 must repeat the same sweep
        // scale and are checked as a transport-integrity guard.
        let x0 = finite(fields[0]);
        let shunt = finite(fields[1]);
        let x1 = finite(fields[2]);
        let isense = finite(fields[3]);
        assert!((x0 - shunt).abs() < 1e-12);
        assert!((x0 - x1).abs() < 1e-12);
        if let Some(previous) = rows.last() {
            assert!(shunt < previous.shunt_v, "{}:{} non-decreasing sweep", path, line_no + 1);
        }
        rows.push(Row { shunt_v: shunt, isense_v: isense });
    }
    assert!(rows.len() > 100, "{} sweep too short", path);
    rows
}

#[derive(Clone, Copy)]
struct Trip { shunt_v: f64, diode_a: f64 }

fn crossing(rows: &[Row], target_isense_v: f64) -> Trip {
    for pair in rows.windows(2) {
        let (a, b) = (pair[0], pair[1]);
        let crossed = (a.isense_v - target_isense_v) * (b.isense_v - target_isense_v) <= 0.0;
        if crossed && (a.isense_v - b.isense_v).abs() > 0.0 {
            let f = (target_isense_v - a.isense_v) / (b.isense_v - a.isense_v);
            let shunt_v = a.shunt_v + f * (b.shunt_v - a.shunt_v);
            let diode_a = (target_isense_v - shunt_v) / 220.0;
            assert!(shunt_v.is_finite() && diode_a.is_finite());
            return Trip { shunt_v, diode_a };
        }
    }
    panic!("target {target_isense_v} V not reached");
}

fn main() -> ExitCode {
    let args: Vec<String> = env::args().collect();
    if args.len() != 6 {
        eprintln!("usage: vendor_threshold_checks <m40.tsv> <m20.tsv> <25.tsv> <85.tsv> <125.tsv>");
        return ExitCode::from(2);
    }
    let temperatures = [-40.0, -20.0, 25.0, 85.0, 125.0];
    let targets = [("SOC", -0.285), ("PCL_typ", -0.400), ("PCL_max", -0.438)];
    for (path, temp_c) in args[1..].iter().zip(temperatures) {
        let rows = read_sweep(path);
        println!("TEMP {temp_c:.0} C");
        for (name, target) in targets {
            let trip = crossing(&rows, target);
            let effective_a = trip.shunt_v.abs() / 0.010;
            let ideal_a = target.abs() / 0.010;
            let extra_percent = (effective_a / ideal_a - 1.0) * 100.0;
            let shift_mv = (trip.shunt_v - target) * 1_000.0;
            let resistor_a = (target - trip.shunt_v) / 220.0;
            assert!(resistor_a >= -1e-9);
            assert!((resistor_a - trip.diode_a).abs() < 2e-6);
            println!("  {name:8} pin={target:.3} V: shunt={:.6} V, shunt_I={effective_a:.3} A, ideal10mR={ideal_a:.3} A, extra={extra_percent:.2}%, shift={shift_mv:.2} mV, diode={:.3e} A", trip.shunt_v, trip.diode_a);
        }
    }
    println!("PASS finite, monotone, complete threshold extraction");
    ExitCode::SUCCESS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn interpolates_crossing() {
        let rows = vec![
            Row { shunt_v: -0.2, isense_v: -0.1 },
            Row { shunt_v: -0.4, isense_v: -0.3 },
        ];
        let t = crossing(&rows, -0.2);
        assert!((t.shunt_v + 0.3).abs() < 1e-12);
        assert!((t.diode_a - 4.545454545e-4).abs() < 1e-12);
    }

    #[test]
    #[should_panic(expected = "malformed width")]
    fn rejects_malformed_row() {
        let path = "/tmp/vendor-threshold-malformed.tsv";
        std::fs::write(path, "-1 -1\n").unwrap();
        let _ = read_sweep(path);
    }
}
