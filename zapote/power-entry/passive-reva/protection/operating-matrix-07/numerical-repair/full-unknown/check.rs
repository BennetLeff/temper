use std::{env, fs, process::ExitCode};

fn run(path: &str, expect_safe: bool) -> Result<(), String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let mut lines = text.lines();
    let header = lines
        .next()
        .unwrap_or("")
        .split_whitespace()
        .collect::<Vec<_>>();
    if header
        != [
            "time",
            "v(gate)",
            "v(xu.pwm_hold)",
            "v(xu.raw)",
            "v(xu.fault)",
            "v(xu.ov)",
            "v(xu.pcl_hold)",
        ]
    {
        return Err("unexpected analog header".into());
    }
    let mut previous = None;
    let mut rows = 0usize;
    let mut max_gate = 0.0_f64;
    let mut last = [0.0_f64; 7];
    for line in lines {
        let row = line
            .split_whitespace()
            .map(str::parse::<f64>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| "non-numeric row".to_string())?;
        if row.len() != 7 || row.iter().any(|x| !x.is_finite()) {
            return Err("nonfinite or wrong-width row".into());
        }
        if let Some(t) = previous {
            if row[0] <= t || row[0] - t > 2e-9 {
                return Err("non-increasing time".into());
            }
        }
        if rows == 0 && (row[0] < 0.0 || row[0] > 1e-9) {
            return Err("missing initial samples".into());
        }
        previous = Some(row[0]);
        max_gate = max_gate.max(row[1].abs());
        last.copy_from_slice(&row);
        rows += 1;
    }
    if rows < 100 || (last[0] - 20e-6).abs() > 1e-12 {
        return Err(format!("incomplete trace rows={rows} end={:.17e}", last[0]));
    }
    if last[3] < 2.5 || last[4] > 1e-3 || last[5] > 1e-3 || last[6] > 1e-3 {
        return Err("test must exercise PWM with all fault masks permissive".into());
    }
    if expect_safe {
        if max_gate > 1e-3 {
            return Err(format!("safe candidate gate reached {max_gate:.9} V"));
        }
        println!("PASS safe unknown-state gate max={max_gate:.9} V rows={rows}");
    } else {
        if (last[1] - 7.5).abs() > 1e-6 || (last[2] - 2.5).abs() > 1e-6 {
            return Err(format!(
                "negative witness missing gate={:.9} hold={:.9}",
                last[1], last[2]
            ));
        }
        if last[4] > 1e-3 || last[5] > 1e-3 || last[6] > 1e-3 {
            return Err("negative witness was not under permissive fault masks".into());
        }
        println!(
            "PASS negative unknown-state witness gate={:.9} V hold={:.9} V rows={rows}",
            last[1], last[2]
        );
    }
    Ok(())
}

fn main() -> ExitCode {
    let args = env::args().collect::<Vec<_>>();
    if args.len() != 3 {
        eprintln!("usage: check TRACE safe|unsafe");
        return ExitCode::from(2);
    }
    if args[2] != "safe" && args[2] != "unsafe" {
        eprintln!("unknown mode");
        return ExitCode::from(2);
    }
    match run(&args[1], args[2] == "safe") {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("FAIL {e}");
            ExitCode::FAILURE
        }
    }
}
