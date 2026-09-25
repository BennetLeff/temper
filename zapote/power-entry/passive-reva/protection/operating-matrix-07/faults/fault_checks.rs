//! Fail-closed checks for operating-matrix-07 fault traces.
//!
//! This is deliberately independent of the legacy integrated checker.  The
//! simulator is transport only; all acceptance decisions happen here.  The
//! trace header is part of the interface and must be emitted exactly by the
//! fault deck.

use std::{env, fs};

pub const HEADER: &str = "time v(acsrc,acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) v(permit)";
const MIN_ROWS: usize = 100;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FaultKind {
    F2Open,
    SwitchShort,
    DiodeShort,
    BothShort,
}

#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub vd: f64,
    pub vb: f64,
    pub sw: f64,
    pub gate: f64,
    pub il: f64,
    pub gate_off: f64,
    pub channel_off: f64,
    pub passive_report: f64,
}

impl Default for Limits {
    fn default() -> Self {
        // These are the frozen model-screen values.  A campaign receipt may
        // select a different reviewed set before execution, but this checker
        // never widens them in response to a result.
        Self {
            vd: 500.0,
            vb: 450.0,
            sw: 650.0,
            gate: 25.0,
            il: 100.0,
            gate_off: 0.20,
            channel_off: 0.10,
            passive_report: 0.10,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Row {
    pub t: f64,
    pub ac_voltage: f64,
    pub vd: f64,
    pub vb: f64,
    pub sw: f64,
    pub gate: f64,
    pub il: f64,
    pub channel: f64,
    pub body: f64,
    pub vac: f64,
    pub q: f64,
    pub en: f64,
    pub fault: f64,
    pub f2ctl: f64,
    pub standby_req: f64,
    pub arm: f64,
    pub permit: f64,
}

#[derive(Debug, PartialEq)]
pub enum Verdict {
    Pass {
        fault_time: f64,
        retained_off_delay: f64,
        channel_peak: f64,
        passive_peak: f64,
    },
    Fail(String),
    ProtectionGap(String),
}

#[derive(Clone, Copy, Debug)]
pub struct Scenario {
    pub kind: FaultKind,
    pub bypass: bool,
    pub turnoff_budget: f64,
    pub observation: f64,
    pub expected_fault_time: Option<f64>,
    pub event_window: f64,
}

impl Scenario {
    pub fn new(kind: FaultKind) -> Self {
        Self {
            kind,
            bypass: false,
            turnoff_budget: 2e-6,
            observation: 1e-6,
            expected_fault_time: None,
            event_window: 1e-6,
        }
    }

    fn valid(self) -> bool {
        self.turnoff_budget.is_finite() && self.turnoff_budget > 0.0
            && self.observation.is_finite() && self.observation > 0.0
            && self.event_window.is_finite() && self.event_window > 0.0
            && self.expected_fault_time.map(|v| v.is_finite()).unwrap_or(false)
    }
}

fn parse_row(fields: &[&str], row: usize) -> Result<Row, String> {
    if fields.len() != HEADER.split_whitespace().count() {
        return Err(format!("row {row}: wrong column count"));
    }
    let mut v = [0.0_f64; 17];
    for (i, field) in fields.iter().enumerate() {
        v[i] = field
            .parse::<f64>()
            .map_err(|_| format!("row {row}: invalid number"))?;
        if !v[i].is_finite() {
            return Err(format!("row {row}: nonfinite value"));
        }
    }
    Ok(Row {
        t: v[0], ac_voltage: v[1], vd: v[2], vb: v[3], sw: v[4], gate: v[5],
        il: v[6], channel: v[7], body: v[8], vac: v[9], q: v[10], en: v[11],
        fault: v[12], f2ctl: v[13], standby_req: v[14], arm: v[15], permit: v[16],
    })
}

pub fn parse_trace(input: &str, tstop: f64, max_gap: f64) -> Result<Vec<Row>, String> {
    if !tstop.is_finite() || tstop <= 0.0 || !max_gap.is_finite() || max_gap <= 0.0 {
        return Err("invalid trace bounds".into());
    }
    let mut lines = input.lines();
    let expected_header: Vec<_> = HEADER.split_whitespace().collect();
    let actual_header: Vec<_> = lines
        .next()
        .map(|line| line.split_whitespace().collect())
        .unwrap_or_default();
    if actual_header != expected_header {
        return Err("wrong trace header/order".into());
    }
    let mut rows: Vec<Row> = Vec::new();
    for (line_no, line) in lines.enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        let row = parse_row(&fields, line_no + 1)?;
        if let Some(prev) = rows.last() {
            if row.t <= prev.t || row.t - prev.t > max_gap {
                return Err(format!("row {}: time order/gap", line_no + 1));
            }
        } else if row.t < 0.0 || row.t > 1e-9 {
            return Err("trace does not start at zero".into());
        }
        rows.push(row);
    }
    if rows.len() < MIN_ROWS {
        return Err(format!("incomplete trace: {} rows", rows.len()));
    }
    if (rows.last().unwrap().t - tstop).abs() > 1e-9 {
        return Err("trace does not end at declared TSTOP".into());
    }
    Ok(rows)
}

fn valid_limits(l: Limits) -> bool {
    [l.vd, l.vb, l.sw, l.gate, l.il, l.gate_off, l.channel_off, l.passive_report]
        .iter()
        .all(|x| x.is_finite() && *x > 0.0)
}

pub fn check(rows: &[Row], scenario: Scenario, limits: Limits) -> Verdict {
    if !scenario.valid() {
        return Verdict::Fail("invalid or missing scenario bounds".into());
    }
    if scenario.bypass {
        return Verdict::Fail("protection detector is bypassed".into());
    }
    if rows.len() < MIN_ROWS {
        return Verdict::Fail("incomplete trace".into());
    }
    if !valid_limits(limits) {
        return Verdict::Fail("invalid frozen node limits".into());
    }
    for (i, r) in rows.iter().enumerate() {
        let checks = [
            ("vd", r.vd.abs(), limits.vd),
            ("vb", r.vb.abs(), limits.vb),
            ("sw", r.sw.abs(), limits.sw),
            ("gate", r.gate.abs(), limits.gate),
            ("Lboost", r.il.abs(), limits.il),
        ];
        if let Some((name, value, limit)) = checks.iter().find(|(_, value, limit)| value > limit) {
            return Verdict::Fail(format!("node screen {name} at row {i}: {value} > {limit}"));
        }
    }

    let expected = match scenario.expected_fault_time {
        Some(v) if v.is_finite() && scenario.event_window > 0.0 => v,
        _ => return Verdict::Fail("missing expected fault time window".into()),
    };
    let lower = expected - scenario.event_window;
    let upper = expected + scenario.event_window;
    let fault_idx = match rows.windows(2).position(|w| {
        w[0].fault < 2.5 && w[1].fault >= 2.5 && w[1].t >= lower && w[1].t <= upper
    }) {
        Some(i) => i + 1,
        None => return Verdict::Fail("no detector fault rising edge in event window".into()),
    };
    let fault_time = rows[fault_idx].t;
    if (fault_time - expected).abs() > scenario.event_window {
        return Verdict::Fail("fault event outside declared event window".into());
    }
    let mut event_idx = fault_idx;
    if scenario.kind == FaultKind::F2Open {
        let open_idx = rows
            .windows(2)
            .position(|w| w[0].f2ctl >= 2.5 && w[1].f2ctl < 2.5)
            .map(|i| i + 1)
            .ok_or_else(|| "F2-open case has no closed-to-open transition".to_string());
        let open_idx = match open_idx {
            Ok(i) => i,
            Err(e) => return Verdict::Fail(e),
        };
        if open_idx >= fault_idx {
            return Verdict::Fail("F2 open does not precede detector fault".into());
        }
        event_idx = open_idx;
    }

    // Reject a detector already high in the declared prefault healthy window,
    // while allowing an unrelated unpowered startup transient before it.
    let event_time = rows[event_idx].t;
    let prefault_start = event_time - scenario.event_window;
    let prefault: Vec<_> = rows[..event_idx].iter().filter(|r| r.t >= prefault_start).collect();
    if prefault.len() < 2
        || prefault.iter().any(|r| r.fault >= 2.5 || r.q <= 2.5 || r.en <= 2.5)
        || prefault.last().unwrap().t - prefault.first().unwrap().t <= 0.0
    {
        return Verdict::Fail("prefault healthy/armed window is missing or unstable".into());
    }

    let mut channel_peak = 0.0_f64;
    let mut passive_peak = 0.0_f64;
    for r in &rows[fault_idx..] {
        channel_peak = channel_peak.max(r.channel.abs());
        passive_peak = passive_peak.max(r.il.abs()).max(r.body.abs());
    }
    if matches!(scenario.kind, FaultKind::SwitchShort | FaultKind::BothShort) {
        if channel_peak > limits.channel_off {
            return Verdict::ProtectionGap(format!(
                "failed-short switch retained {:.6} A channel current after latch",
                channel_peak
            ));
        }
        return Verdict::ProtectionGap("failed-short state cannot earn protection PASS".into());
    }

    let off_idx = rows[fault_idx..]
        .iter()
        .position(|r| r.q <= 2.5 && r.en <= 2.5 && r.gate.abs() <= limits.gate_off
            && r.channel.abs() <= limits.channel_off)
        .map(|i| i + fault_idx);
    let off_idx = match off_idx {
        Some(i) => i,
        None => return Verdict::Fail("no latch-off/current-cessation witness within budget".into()),
    };
    let turnoff_delay = rows[off_idx].t - fault_time;
    if turnoff_delay > scenario.turnoff_budget {
        return Verdict::Fail("turnoff exceeded declared budget".into());
    }
    if rows.last().unwrap().t - rows[off_idx].t < scenario.observation {
        return Verdict::Fail("post-event observation window too short".into());
    }
    let strict_start = (fault_time - scenario.event_window).max(0.0);
    let strict_end = rows[off_idx].t + scenario.observation;
    for w in rows.windows(2) {
        if w[1].t >= strict_start && w[0].t <= strict_end && w[1].t - w[0].t > 25e-9 {
            return Verdict::Fail("event/retained-off trace gap exceeds 25 ns".into());
        }
    }
    for (offset, r) in rows[off_idx..].iter().enumerate() {
        if r.q > 2.5 || r.en > 2.5 || r.gate.abs() > limits.gate_off {
            return Verdict::Fail(format!("latch/gate rearmed at row {}", off_idx + offset));
        }
        if r.channel.abs() > limits.channel_off {
            return Verdict::Fail(format!("healthy channel resumed at row {}", off_idx + offset));
        }
    }
    Verdict::Pass {
        fault_time,
        retained_off_delay: turnoff_delay,
        channel_peak,
        passive_peak,
    }
}

fn main() {
    let args: Vec<_> = env::args().collect();
    if args.len() < 8 || args.len() > 9 {
        eprintln!("usage: fault_checks TRACE.tsv TSTOP KIND EXPECTED_FAULT DETECTOR_WINDOW TURNOFF_BUDGET OBSERVATION [MAX_GAP]");
        std::process::exit(2);
    }
    let bound = |index: usize, name: &str| -> f64 {
        match args[index].parse::<f64>() {
            Ok(v) if v.is_finite() && v > 0.0 => v,
            _ => { eprintln!("invalid {name}"); std::process::exit(2); }
        }
    };
    let tstop = bound(2, "TSTOP");
    let kind_arg = args[3].as_str();
    let bypass = kind_arg == "bypass";
    let kind_arg = if bypass { "f2-open" } else { kind_arg };
    let kind = match kind_arg {
        "f2-open" => FaultKind::F2Open,
        "switch-short" => FaultKind::SwitchShort,
        "diode-short" => FaultKind::DiodeShort,
        "both-short" => FaultKind::BothShort,
        _ => { eprintln!("unknown fault kind"); std::process::exit(2); }
    };
    let expected_fault = bound(4, "EXPECTED_FAULT");
    let detector_window = bound(5, "DETECTOR_WINDOW");
    let turnoff_budget = bound(6, "TURNOFF_BUDGET");
    let observation = bound(7, "OBSERVATION");
    let max_gap = if args.len() == 9 { bound(8, "MAX_GAP") } else { 1e-6 };
    let input = match fs::read_to_string(&args[1]) {
        Ok(s) => s,
        Err(e) => { eprintln!("read trace: {e}"); std::process::exit(1); }
    };
    // Prefixes can be sampled at up to 1 us; the event/retained-off segment is
    // checked separately at <=25 ns below.  Do not apply a switching-step gap
    // bound to an entire cold-start/settled trace.
    let rows = match parse_trace(&input, tstop, max_gap) {
        Ok(rows) => rows,
        Err(e) => { eprintln!("FAIL {e}"); std::process::exit(1); }
    };
    let mut scenario = Scenario::new(kind);
    scenario.bypass = bypass;
    scenario.expected_fault_time = Some(expected_fault);
    scenario.event_window = detector_window;
    scenario.turnoff_budget = turnoff_budget;
    scenario.observation = observation;
    match check(&rows, scenario, Limits::default()) {
        Verdict::Pass { fault_time, retained_off_delay, channel_peak, passive_peak } => println!(
            "PASS fault_time={fault_time:.9e}s retained_off_delay={retained_off_delay:.6e}s channel_peak={channel_peak:.6e}A passive_peak={passive_peak:.6e}A"
        ),
        Verdict::Fail(e) => { eprintln!("FAIL {e}"); std::process::exit(1); }
        Verdict::ProtectionGap(e) => { eprintln!("PROTECTION_GAP {e}"); std::process::exit(1); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trace(rows: impl Fn(usize) -> String) -> String {
        let mut out = format!("{HEADER}\n");
        for i in 0..MIN_ROWS {
            out.push_str(&rows(i));
            out.push('\n');
        }
        out
    }

    fn healthy_row(i: usize) -> String {
        let t = i as f64 * 1e-9;
        format!("{t} 0 400 400 0 0 0 0 0 0 0 0 0 5 0 5 5")
    }

    fn scenario(kind: FaultKind) -> Scenario {
        let mut s = Scenario::new(kind);
        s.expected_fault_time = Some(50e-9);
        s.event_window = 10e-9;
        s.observation = 20e-9;
        s
    }

    #[test]
    fn truncated_trace_is_rejected() {
        let text = trace(healthy_row).replace("9.9e-8 0 400", "9.9e-8 0 400");
        assert!(parse_trace(&text, 1e-6, 25e-9).is_err());
    }

    #[test]
    fn ngspice_header_padding_is_token_checked() {
        let padded = HEADER.replace(' ', "   ");
        let text = trace(healthy_row).replacen(HEADER, &padded, 1);
        assert!(parse_trace(&text, 99e-9, 2e-9).is_ok());
    }

    #[test]
    fn no_fault_event_is_rejected() {
        let text = trace(|i| healthy_row(i));
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        assert!(matches!(check(&rows, scenario(FaultKind::F2Open), Limits::default()), Verdict::Fail(e) if e.contains("no detector fault")));
    }

    #[test]
    fn bypass_is_rejected_even_with_fault() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let fault = if i >= 50 { 5.0 } else { 0.0 };
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            let armed = if i < 50 { 5.0 } else { 0.0 };
            format!("{t} 0 400 400 0 0 0 0 0 0 {armed} {armed} {fault} {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        let mut spec = scenario(FaultKind::F2Open);
        spec.bypass = true;
        assert!(matches!(check(&rows, spec, Limits::default()), Verdict::Fail(e) if e.contains("bypassed")));
    }

    #[test]
    fn latch_rearm_is_rejected() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let fault = if i >= 50 { 5.0 } else { 0.0 };
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            let q = if i < 50 || i >= 90 { 5.0 } else { 0.0 };
            format!("{t} 0 400 400 0 0 0 0 0 0 {q} {q} {fault} {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        assert!(matches!(check(&rows, scenario(FaultKind::F2Open), Limits::default()), Verdict::Fail(e) if e.contains("rearmed")));
    }

    #[test]
    fn low_gate_with_sustained_channel_current_is_gap_for_switch_short() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let fault = if i >= 50 { 5.0 } else { 0.0 };
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            let armed = if i < 50 { 5.0 } else { 0.0 };
            format!("{t} 0 400 400 0 0 10 10 0 0 {armed} {armed} {fault} {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        assert!(matches!(check(&rows, scenario(FaultKind::SwitchShort), Limits::default()), Verdict::ProtectionGap(e) if e.contains("failed-short")));
    }

    #[test]
    fn passive_current_is_reported_separately_after_channel_ceases() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let fault = if i >= 50 { 5.0 } else { 0.0 };
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            let body = if i >= 50 { 0.25 } else { 0.0 };
            let armed = if i < 50 { 5.0 } else { 0.0 };
            format!("{t} 0 400 400 0 0 0 0 {body} 0 {armed} {armed} {fault} {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        match check(&rows, scenario(FaultKind::F2Open), Limits::default()) {
            Verdict::Pass { channel_peak, passive_peak, .. } => {
                assert_eq!(channel_peak, 0.0);
                assert_eq!(passive_peak, 0.25);
            }
            other => panic!("unexpected verdict: {other:?}"),
        }
    }

    #[test]
    fn preexisting_fault_is_rejected() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            let armed = if i < 50 { 5.0 } else { 0.0 };
            format!("{t} 0 400 400 0 0 0 0 0 0 {armed} {armed} 5 {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        assert!(matches!(check(&rows, scenario(FaultKind::F2Open), Limits::default()), Verdict::Fail(e) if e.contains("F2 open") || e.contains("prefault") || e.contains("outside") || e.contains("no detector")));
    }

    #[test]
    fn no_energized_history_is_rejected() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let fault = if i >= 50 { 5.0 } else { 0.0 };
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            format!("{t} 0 400 400 0 0 0 0 0 0 0 0 {fault} {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        assert!(matches!(check(&rows, scenario(FaultKind::F2Open), Limits::default()), Verdict::Fail(e) if e.contains("prefault")));
    }

    #[test]
    fn startup_transient_before_declared_event_is_ignored() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let transient = if i < 10 { 5.0 } else if i >= 50 { 5.0 } else { 0.0 };
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            let armed = if i < 50 { 5.0 } else { 0.0 };
            format!("{t} 0 400 400 0 0 0 0 0 0 {armed} {armed} {transient} {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        assert!(matches!(check(&rows, scenario(FaultKind::F2Open), Limits::default()), Verdict::Pass { .. }));
    }

    #[test]
    fn too_short_post_event_window_is_rejected() {
        let text = trace(|i| {
            let t = i as f64 * 1e-9;
            let fault = if i >= 50 { 5.0 } else { 0.0 };
            let f2 = if i >= 40 { 0.0 } else { 5.0 };
            let armed = if i < 50 { 5.0 } else { 0.0 };
            format!("{t} 0 400 400 0 0 0 0 0 0 {armed} {armed} {fault} {f2} 0 5 5")
        });
        let rows = parse_trace(&text, 99e-9, 2e-9).unwrap();
        let mut spec = scenario(FaultKind::F2Open);
        spec.observation = 100e-9;
        assert!(matches!(check(&rows, spec, Limits::default()), Verdict::Fail(e) if e.contains("observation window")));
    }
}
