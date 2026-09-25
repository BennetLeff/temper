use std::{env, fs, process::ExitCode};
fn check(text: &str) -> Result<(), String> {
    let mut lines = text.lines();
    if lines
        .next()
        .unwrap_or("")
        .split_whitespace()
        .collect::<Vec<_>>()
        != ["time", "v(gate)"]
    {
        return Err("wrong hold-probe header".into());
    }
    let mut previous = None;
    let mut last = 0.0;
    let mut witnessed = [false; 4];
    let windows = [
        (1e-6, 1.5e-6, true),
        (2.1e-6, 3e-6, true),
        (6.5e-6, 7e-6, true),
        (7.8e-6, 8e-6, false),
    ];
    for line in lines {
        let v = line
            .split_whitespace()
            .map(str::parse::<f64>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| "bad hold-probe number")?;
        if v.len() != 2 || v.iter().any(|x| !x.is_finite()) {
            return Err("malformed hold-probe row".into());
        }
        if let Some(t) = previous {
            if v[0] <= t || v[0] - t > 2e-9 {
                return Err("hold-probe time gap/order".into());
            }
        } else if v[0] < 0.0 || v[0] > 1e-9 {
            return Err("hold-probe missing start".into());
        }
        for (i, (lo, hi, on)) in windows.iter().enumerate() {
            if v[0] >= *lo && v[0] <= *hi {
                witnessed[i] = true;
                if (*on && v[1] < 7.5) || (!*on && v[1] > 0.1) {
                    return Err(format!(
                        "PWM latch hold/reset failed in window{i} at{}s",
                        v[0]
                    ));
                }
            }
        }
        previous = Some(v[0]);
        last = v[0];
    }
    if (last - 20e-6).abs() > 1e-12 || witnessed.iter().any(|x| !*x) {
        return Err("incomplete hold-probe".into());
    }
    println!("PASS PWM remains high after comparator recrossing, resets at next oscillator cycle");
    Ok(())
}
fn main() -> ExitCode {
    let result = env::args()
        .nth(1)
        .ok_or_else(|| "usage: hold_checks TRACE".to_string())
        .and_then(|p| fs::read_to_string(p).map_err(|e| e.to_string()))
        .and_then(|s| check(&s));
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("FAIL {e}");
            ExitCode::FAILURE
        }
    }
}
