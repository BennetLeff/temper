//! Fail-closed checks of the retained TI-model fixture, not device guarantees.
use std::{error::Error, fs};
fn measurement(log: &str, name: &str) -> Result<f64, Box<dyn Error>> {
    let mut found = None;
    for line in log.lines() {
        if let Some((left, right)) = line.split_once('=') {
            if left.trim() == name {
                let value: f64 = right
                    .split_whitespace()
                    .next()
                    .ok_or("empty measurement")?
                    .parse()?;
                if !value.is_finite() || found.is_some() {
                    return Err("invalid or duplicate measurement".into());
                }
                found = Some(value);
            }
        }
    }
    found.ok_or_else(|| format!("missing {name}").into())
}
fn check(log: &str) -> Result<(), Box<dyn Error>> {
    for name in [
        "default_off",
        "disarmed_low",
        "absent_aux",
        "returned_aux_disarmed",
    ] {
        let v = measurement(log, name)?;
        if v.abs() > 0.1 {
            return Err(format!("{name} {v}V exceeds fixture off window").into());
        }
        println!("PASS {name}: {v:.9}V");
    }
    let high = measurement(log, "armed_high")?;
    if high < 14. {
        return Err("positive enable control did not exercise loaded gate".into());
    }
    let gate = measurement(log, "loaded_gate_to4v")?;
    let output = measurement(log, "output_disable")?;
    if !(output > 0. && output < gate && gate < 1e-6) {
        return Err("invalid observed timing".into());
    }
    println!(
        "PASS positive enable: {high:.6}V; observed RUNfall to gate4V: {:.6}us",
        gate * 1e6
    );
    Ok(())
}
fn main() -> Result<(), Box<dyn Error>> {
    let path = std::env::args().nth(1).ok_or("usage: check_driver <log>")?;
    check(&fs::read_to_string(path)?)?;
    for startup in std::env::args().skip(2) {
        let peak = measurement(&fs::read_to_string(&startup)?, "default_off")?;
        if peak.abs() > 0.1 {
            return Err(format!("startup gate peak {peak}V: {startup}").into());
        }
        println!("PASS startup gate peak {peak:.9}V: {startup}");
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_absent_nonfinite_and_duplicate_results() {
        for text in ["", "x = NaN", "x = 1\nx = 2"] {
            assert!(measurement(text, "x").is_err());
        }
    }
    #[test]
    fn failed_positive_control_cannot_pass() {
        let log="default_off=0\ndisarmed_low=0\nabsent_aux=0\nreturned_aux_disarmed=0\narmed_high=0\nloaded_gate_to4v=0.0000002\noutput_disable=0.00000001";
        assert!(check(log).is_err());
    }
}
