//! Check actual ngspice fixture measurements; no device-bound promotion.
use std::{error::Error, fs, path::Path};

fn measurement(log: &str, name: &str) -> Result<f64, Box<dyn Error>> {
    for line in log.lines() {
        if let Some((left, right)) = line.split_once('=') {
            if left.trim() == name {
                let value: f64 = right
                    .split_whitespace()
                    .next()
                    .ok_or("empty measurement")?
                    .parse()?;
                if value.is_finite() {
                    return Ok(value);
                }
                return Err(format!("non-finite {name}").into());
            }
        }
    }
    Err(format!("missing measurement {name}").into())
}

fn main() -> Result<(), Box<dyn Error>> {
    let directory = std::env::args()
        .nth(1)
        .ok_or("usage: check_measurements <vendor-directory>")?;
    let directory = Path::new(&directory);
    let latch = fs::read_to_string(directory.join("latch-behavior-check.log"))?;
    for (name, high) in [
        ("q_after_arm", true),
        ("q_during_fault", false),
        ("q_after_clear_with_arm_held", false),
        ("q_after_fresh_arm", true),
    ] {
        let value = measurement(&latch, name)?;
        if !(if high { value > 4.0 } else { value.abs() < 0.5 }) {
            return Err(format!("{name}: unexpected {value}V").into());
        }
        println!("PASS {name}: {value:.6}V");
    }
    let driver = fs::read_to_string(directory.join("driver-load-check.log"))?;
    let output = measurement(&driver, "output_disable")?;
    let gate = measurement(&driver, "loaded_gate_to4v")?;
    if !(output > 0.0 && gate > output) {
        return Err("invalid driver measurement ordering".into());
    }
    println!(
        "OBSERVED driver EN0.8V→OUT13.5V {:.6}us; EN0.8V→gate4V {:.6}us",
        output * 1e6,
        gate * 1e6
    );
    println!("Illustrative 12nF load; actual MOSFET current-turnoff bound=null");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn absent_or_nonfinite_measurement_is_not_success() {
        assert!(measurement("measurement failed", "q").is_err());
        assert!(measurement("q = NaN", "q").is_err());
    }
}
