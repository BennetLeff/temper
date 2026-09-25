use std::{env, fs, process::ExitCode};

fn check(input: &str) -> Result<(), String> {
    let mut lines = input.lines();
    let expected = [
        "time",
        "v(gate0)",
        "v(gate1)",
        "v(gate3)",
        "v(gatesh)",
        "v(xush.icomp_reset)",
    ];
    if lines
        .next()
        .unwrap_or("")
        .split_whitespace()
        .collect::<Vec<_>>()
        != expected
    {
        return Err("wrong PWM probe header".into());
    }
    let mut previous = None;
    let mut first_edges = [None; 3];
    let mut last = 0.0;
    for line in lines {
        let row = line
            .split_whitespace()
            .map(str::parse::<f64>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| "bad number")?;
        if row.len() != 6 || row.iter().any(|x| !x.is_finite()) {
            return Err("malformed/nonfinite PWM row".into());
        }
        if let Some(t) = previous {
            if row[0] <= t || row[0] - t > 2e-9 {
                return Err("PWM time gap/order".into());
            }
        } else if row[0] < 0.0 || row[0] > 1e-9 {
            return Err("missing PWM start".into());
        }
        for j in 0..3 {
            if row[j + 1] > 7.5 && first_edges[j].is_none() {
                first_edges[j] = Some(row[0]);
            }
        }
        if row[4].abs() > 0.1 || row[5].abs() > 0.1 {
            return Err("ICOMP short enabled gate or triggered undocumented reset".into());
        }
        previous = Some(row[0]);
        last = row[0];
    }
    if (last - 20e-6).abs() > 1e-12 {
        return Err("incomplete PWM probe".into());
    }
    let fsw = 2.0915334e9 / 16.2e3;
    let m2 = fsw / 65e3 * 0.1223 * 2.5_f64.powi(2);
    for (j, delta) in [0.0, 1.0, 3.0].into_iter().enumerate() {
        let observed = first_edges[j].ok_or("missing gate rise")?;
        let target = 570e-9 + delta / (m2 * 1e6);
        if (observed - target).abs() > 3e-9 {
            return Err(format!(
                "PWM crossing {j}: {observed:.12e} != {target:.12e}"
            ));
        }
        println!("PASS PWM crossing {j}: measured={observed:.12e}s expected={target:.12e}s");
    }
    println!(
        "PASS ICOMP-short inhibits gate without self-reset; nominal inferred PWM plateau only"
    );
    Ok(())
}

fn main() -> ExitCode {
    let result = env::args()
        .nth(1)
        .ok_or_else(|| "usage: pwm_checks TRACE".to_string())
        .and_then(|path| fs::read_to_string(path).map_err(|e| e.to_string()))
        .and_then(|input| check(&input));
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("FAIL {e}");
            ExitCode::FAILURE
        }
    }
}
