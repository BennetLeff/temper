//! Checks the imposed-source passive-network experiment, not LT4363 behavior.
use std::{collections::BTreeMap, error::Error, fs, path::Path};

fn measurements(text: &str) -> Result<BTreeMap<String, f64>, String> {
    let mut out = BTreeMap::new();
    for line in text
        .lines()
        .filter(|l| l.starts_with("old_") || l.starts_with("ref_"))
    {
        let (name, rhs) = line.split_once('=').ok_or("malformed measurement")?;
        let value: f64 = rhs.trim().parse().map_err(|_| "invalid measurement")?;
        if !value.is_finite() || out.insert(name.trim().into(), value).is_some() {
            return Err("non-finite or duplicate measurement".into());
        }
    }
    if out.is_empty() {
        return Err("missing measurements".into());
    }
    Ok(out)
}
fn close(actual: f64, expected: f64) -> Result<(), String> {
    if !actual.is_finite() || !expected.is_finite() || (actual - expected).abs() > 0.00005 {
        return Err(format!("{actual} != {expected} within 50uV"));
    }
    Ok(())
}
fn get(m: &BTreeMap<String, f64>, key: &str) -> Result<f64, String> {
    m.get(key).copied().ok_or_else(|| format!("missing {key}"))
}
fn fast_q(c: f64) -> f64 {
    // Exact linear-ramp forcing, followed by free exponential decay.
    let tau = 110. * c;
    let fall = 10e-9;
    25. * tau / fall * -(-fall / tau).exp_m1() * (-(11e-6 - 10e-6 - fall) / tau).exp() * 10. / 110.
}
fn verify(root: &Path) -> Result<(), Box<dyn Error>> {
    println!("case,measurement,simulated_V,closed_form_V");
    for mode in ["fast", "weak"] {
        let mut previous = None;
        for suffix in ["", "-refined"] {
            let m = measurements(&fs::read_to_string(
                root.join(format!("{mode}{suffix}.log")),
            )?)?;
            let expected_count = if mode == "fast" { 4 } else { 7 };
            if m.len() != expected_count {
                return Err("unexpected measurement count".into());
            }
            for (label, cap) in [("lo", 1.3e-6), ("hi", 1.7e-6)] {
                for topology in ["old", "ref"] {
                    let key = format!("{topology}_{label}_q");
                    let expected = if mode == "fast" {
                        if topology == "old" {
                            fast_q(cap)
                        } else {
                            0.
                        }
                    } else {
                        10. - 50e-6 * 0.120 / cap - 50e-6 * 100.
                    };
                    let actual = get(&m, &key)?;
                    close(actual, expected)?;
                    println!("{mode}{suffix},{key},{actual:.9},{expected:.9}");
                }
            }
            if mode == "weak" {
                let cap_v = 10. - 50e-6 * 0.120 / 1.7e-6;
                for (key, expected) in [
                    ("old_hi_c", cap_v),
                    ("old_hi_driver", cap_v - 50e-6 * 110.),
                    ("ref_hi_driver", cap_v - 50e-6 * 100.),
                ] {
                    close(get(&m, key)?, expected)?;
                }
            }
            if let Some(prior) = previous {
                for (key, value) in &m {
                    close(*value, get(&prior, key)?)?;
                }
            }
            previous = Some(m);
        }
    }
    eprintln!(
        "PASS: 22 closed-form comparisons; 11 timestep-refinement comparisons (50uV tolerance)"
    );
    Ok(())
}
fn main() -> Result<(), Box<dyn Error>> {
    let arg = std::env::args().nth(1).unwrap_or_else(|| ".".into());
    verify(Path::new(&arg))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_measurements_is_not_success() {
        assert!(measurements("simulation failed").is_err());
    }
    #[test]
    fn nan_is_not_success() {
        assert!(measurements("old_lo_q = NaN").is_err());
    }
    #[test]
    fn duplicate_is_not_success() {
        assert!(measurements("old_lo_q = 1\nold_lo_q = 2").is_err());
    }
    #[test]
    fn wrong_branch_trace_fails_oracle() {
        assert!(close(0., fast_q(1.3e-6)).is_err());
    }
}
