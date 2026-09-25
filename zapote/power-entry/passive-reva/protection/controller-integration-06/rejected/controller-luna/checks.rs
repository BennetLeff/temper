//! Rust verdicts for the bounded B1/B2 ngspice fixtures.
//! This parser intentionally consumes `.meas` scalars, not a synthetic
//! waveform proxy.  Dynamic applicability remains conditional as documented.
use std::{env, fs, process::ExitCode};

fn value(log: &str, name: &str) -> Option<f64> {
    log.lines().find_map(|line| {
        let mut fields = line.split_whitespace();
        let first = fields.next()?;
        if first == format!("{name}=") { return fields.next()?.parse().ok(); }
        if first != name || fields.next()? != "=" { return None; }
        fields.next()?.parse().ok()
    })
}

fn require(log: &str, name: &str, pred: impl FnOnce(f64) -> bool, why: &str) -> bool {
    match value(log, name) {
        Some(v) if pred(v) => { println!("PASS {name}={v:.6e}: {why}"); true }
        Some(v) => { println!("FAIL {name}={v:.6e}: {why}"); false }
        None => { println!("INDETERMINATE {name}: measurement absent ({why})"); false }
    }
}

fn main() -> ExitCode {
    let args: Vec<_> = env::args().collect();
    if args.len() != 5 { eprintln!("usage: checks functional.log pcl.log standby.log integrated.log"); return ExitCode::from(2); }
    let f = fs::read_to_string(&args[1]).expect("functional log");
    let p = fs::read_to_string(&args[2]).expect("pcl log");
    let s = fs::read_to_string(&args[3]).expect("standby log");
    let i = fs::read_to_string(&args[4]).expect("integrated log");
    let mut ok = true;
    ok &= require(&f, "gate_on", |v| v > 5.0, "run-qualified controller produces live feedback-driven gate");
    ok &= require(&f, "gate_ovp", |v| v < 0.5, "OVP_H inhibits PWM");
    ok &= require(&f, "gate_standby", |v| v < 0.5, "VSENSE standby inhibits PWM");
    ok &= require(&f, "comp_standby", |v| v < 0.6, "standby discharges VCOMP");
    ok &= require(&f, "gate_retry_max", |v| v > 5.0, "explicit run re-arm permits a later retry");
    ok &= require(&p, "pcl_flag", |v| v > 4.0, "PCL flag asserts after live ISENSE exceeds -0.4 V");
    ok &= require(&p, "gate_pcl_after_blank", |v| v < 0.5, "PCL negative control suppresses post-blanking pulse");
    ok &= require(&s, "gate_standby_max", |v| v < 0.5, "standby negative control suppresses gate with RUN held high");
    ok &= require(&s, "comp_standby", |v| v < 0.1, "standby negative control discharges VCOMP");
    ok &= require(&s, "gate_return_max", |v| v > 5.0, "VSENSE recovery permits controller retry");
    ok &= require(&i, "vd_preopen", |v| v > 100.0, "integrated plant reaches a source-bound pre-open state");
    ok &= require(&i, "vd_max", |v| v.is_finite() && v < 500.0, "integrated witness remains below provisional VD screen");
    println!("RESULT {} (conditional model; dynamics/thermal/magnetic limits remain unknown)", if ok { "PASS" } else { "FAIL" });
    if ok { ExitCode::SUCCESS } else { ExitCode::from(1) }
}
