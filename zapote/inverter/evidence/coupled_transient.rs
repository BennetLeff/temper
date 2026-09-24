// Standalone, standard-library-only conditional bank/tank screen.
// rustc --edition=2021 -O zapote/inverter/evidence/coupled_transient.rs -o /tmp/zapote-coupled-transient
// /tmp/zapote-coupled-transient zapote/inverter/evidence/transient-cases.csv
use std::env;
use std::fs;

const HEADER: &str = "id,topology,f2,vd0_v,vb0_v,i0_a,vc0_v,cd_uf,cb_uf,local_uf,l_uh,c_nf,r_coil_ohm,r_pan_ohm,f_khz,dead_ns,run_ms,stop_kind,stop_at_ms,stop_delay_us,source_off_ms,source_command_a,source_target_v,source_gain_a_per_v,source_max_a,source_max_w,rd_ohm,rb_ohm,screen_ceiling_v,stop_threshold_a,tank_v_screen_v,tank_i_screen_a,dt_ns";
const OUT_HEADER: &str = "id,status,reason,run_ms,e_start_j,e_source_j,e_end_j,e_coil_j,e_pan_j,e_vd_bleed_j,e_vb_bleed_j,e_residual_j,unallocated_device_cap_switch_loss,vd_end_v,vb_end_v,vb_min_v,vd_max_v,vb_max_v,i_peak_a,vc_peak_v,local_c_start_j,diode_path_ms,gate_off_ms,last_current_above_ms";
// Numerical zero-crossing tolerance. Its maximum discarded inductor energy
// at 88 uH is 0.11 uJ, and it is below every fixture's 0.1 A stop threshold.
const DIODE_ZERO_A: f64 = 0.05;

#[derive(Clone, Debug)]
struct Case {
    id: String,
    topology: String,
    f2: String,
    s0: [f64; 4], // VD, VB, tank current (SW to HOT0), tank-capacitor voltage.
    cd: f64,
    cb: f64,
    local_c: f64,
    l: f64,
    c: f64,
    r_coil: f64,
    r_pan: f64,
    f: f64,
    dead: f64,
    run: f64,
    stop_kind: String,
    stop_at: Option<f64>,
    stop_delay: f64,
    source_off: Option<f64>,
    source_command: f64,
    source_target: f64,
    source_gain: f64,
    source_max_i: f64,
    source_max_p: f64,
    rd: f64,
    rb: f64,
    ceiling: f64,
    stop_threshold: f64,
    tank_v_screen: f64,
    tank_i_screen: f64,
    dt: f64,
}

fn number(fields: &[&str], index: usize) -> Result<f64, String> {
    fields[index]
        .parse::<f64>()
        .map_err(|_| format!("invalid numeric input at column {}", index + 1))
}

fn optional_ms(fields: &[&str], index: usize) -> Result<Option<f64>, String> {
    if fields[index] == "never" {
        Ok(None)
    } else {
        number(fields, index).map(|v| Some(v * 1e-3))
    }
}

fn parse_case(line: &str) -> Result<Case, String> {
    let v: Vec<&str> = line.split(',').map(str::trim).collect();
    if v.len() != 33 {
        return Err(format!("expected 33 fields, got {}", v.len()));
    }
    let case = Case {
        id: v[0].to_owned(),
        topology: v[1].to_owned(),
        f2: v[2].to_owned(),
        s0: [
            number(&v, 3)?,
            number(&v, 4)?,
            number(&v, 5)?,
            number(&v, 6)?,
        ],
        cd: number(&v, 7)? * 1e-6,
        cb: number(&v, 8)? * 1e-6,
        local_c: number(&v, 9)? * 1e-6,
        l: number(&v, 10)? * 1e-6,
        c: number(&v, 11)? * 1e-9,
        r_coil: number(&v, 12)?,
        r_pan: number(&v, 13)?,
        f: number(&v, 14)? * 1e3,
        dead: number(&v, 15)? * 1e-9,
        run: number(&v, 16)? * 1e-3,
        stop_kind: v[17].to_owned(),
        stop_at: optional_ms(&v, 18)?,
        stop_delay: number(&v, 19)? * 1e-6,
        source_off: optional_ms(&v, 20)?,
        source_command: number(&v, 21)?,
        source_target: number(&v, 22)?,
        source_gain: number(&v, 23)?,
        source_max_i: number(&v, 24)?,
        source_max_p: number(&v, 25)?,
        rd: number(&v, 26)?,
        rb: number(&v, 27)?,
        ceiling: number(&v, 28)?,
        stop_threshold: number(&v, 29)?,
        tank_v_screen: number(&v, 30)?,
        tank_i_screen: number(&v, 31)?,
        dt: number(&v, 32)? * 1e-9,
    };
    validate(&case)?;
    Ok(case)
}

fn validate(c: &Case) -> Result<(), String> {
    if c.id.is_empty() || c.id.contains(' ') {
        return Err("missing or malformed case id".into());
    }
    if c.topology != "hot0" {
        return Err("historical PWR_RTN midpoint is absent; tank return must be HOT0".into());
    }
    if !["closed", "open", "opening", "reclosing"].contains(&c.f2.as_str()) {
        return Err("unknown F2 state".into());
    }
    if !["none", "pwm", "permit", "rail"].contains(&c.stop_kind.as_str()) {
        return Err("unknown stop cause".into());
    }
    if (c.stop_kind == "none") != c.stop_at.is_none() {
        return Err("stop kind and command time disagree".into());
    }
    let finite = [
        c.s0[0],
        c.s0[1],
        c.s0[2],
        c.s0[3],
        c.cd,
        c.cb,
        c.local_c,
        c.l,
        c.c,
        c.r_coil,
        c.r_pan,
        c.f,
        c.dead,
        c.run,
        c.stop_delay,
        c.source_command,
        c.source_target,
        c.source_gain,
        c.source_max_i,
        c.source_max_p,
        c.rd,
        c.rb,
        c.ceiling,
        c.stop_threshold,
        c.tank_v_screen,
        c.tank_i_screen,
        c.dt,
    ];
    if finite.iter().any(|x| !x.is_finite())
        || c.stop_at.is_some_and(|x| !x.is_finite() || x < 0.0)
        || c.source_off.is_some_and(|x| !x.is_finite() || x < 0.0)
    {
        return Err("non-finite or negative event time".into());
    }
    if c.s0[0] < 0.0
        || c.s0[1] < 0.0
        || c.cd <= 0.0
        || c.cb <= 0.0
        || c.local_c < 0.0
        || c.l <= 0.0
        || c.c <= 0.0
        || c.f <= 0.0
        || c.dead < 0.0
        || c.dead * c.f >= 0.5
        || c.run <= 0.0
        || c.dt <= 0.0
        || c.dt > 0.01 / c.f
        || c.r_coil < 0.0
        || c.r_pan < 0.0
        || c.rd <= 0.0
        || c.rb <= 0.0
        || c.source_command < 0.0
        || c.source_target < 0.0
        || c.source_gain < 0.0
        || c.source_max_i < 0.0
        || c.source_max_p < 0.0
        || c.ceiling <= 0.0
        || c.stop_threshold < 0.0
        || c.stop_delay < 0.0
        || c.tank_v_screen <= 0.0
        || c.tank_i_screen <= 0.0
    {
        return Err("nonphysical or unresolved electrical bound".into());
    }
    if c.s0[0] > c.ceiling || c.s0[1] > c.ceiling {
        return Err("initial bus exceeds declared voltage screen ceiling".into());
    }
    if c.s0[2].abs() > c.tank_i_screen || c.s0[3].abs() > c.tank_v_screen {
        return Err("initial tank state exceeds declared screen ceiling".into());
    }
    if c.f2 == "closed" && (c.s0[0] - c.s0[1]).abs() > 1e-9 {
        return Err("closed ideal F2 requires equal initial VD and VB".into());
    }
    if c.f2 == "reclosing" && (c.s0[0] - c.s0[1]).abs() > 1e-9 {
        return Err("unequal-voltage F2 reclose requires interconnect R/L model".into());
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct Rate {
    ds: [f64; 4],
    de: [f64; 5], // source, copper, reflected pan, VD bleed, VB bleed.
    diode: bool,
    floating: bool,
}

fn gate_off(c: &Case) -> Option<f64> {
    c.stop_at.map(|t| t + c.stop_delay)
}

fn source_current(c: &Case, t: f64, vd: f64) -> f64 {
    if c.source_off.is_some_and(|off| t >= off) {
        return 0.0;
    }
    let power_bound = if vd > 0.0 {
        c.source_max_p / vd
    } else {
        c.source_max_i
    };
    let command = (c.source_command + c.source_gain * (c.source_target - vd)).max(0.0);
    command.min(c.source_max_i).min(power_bound)
}

fn rate(c: &Case, t: f64, s: [f64; 4]) -> Rate {
    let stopped = gate_off(c).is_some_and(|off| t >= off);
    let phase = (t * c.f).fract();
    let gap = c.dead * c.f * 0.5;
    let high_on = !stopped && phase >= gap && phase < 0.5 - gap;
    let low_on = !stopped && phase >= 0.5 + gap && phase < 1.0 - gap;
    // Both gates off: positive current uses the HOT0-to-SW low diode,
    // negative current uses the SW-to-VB high diode. Near zero, neither
    // conducts if the tank capacitor is between the bus rails; SW floats.
    let floating =
        !high_on && !low_on && s[2].abs() <= DIODE_ZERO_A && (0.0..=s[1]).contains(&s[3]);
    let high_path = high_on
        || (!low_on
            && !high_on
            && (s[2] < -DIODE_ZERO_A || (s[2].abs() <= DIODE_ZERO_A && s[3] > s[1])));
    let diode = !floating && if high_path { s[2] < 0.0 } else { s[2] > 0.0 };
    let switch_fraction = if high_path { 1.0 } else { 0.0 };
    let vd = s[0];
    let vb = s[1];
    let i = s[2];
    let source_i = source_current(c, t, vd);
    let bridge_current = if floating { 0.0 } else { switch_fraction * i };
    let (dvd, dvb) = if c.f2 == "closed" {
        let dv = (source_i - bridge_current - vd / c.rd - vb / c.rb) / (c.cd + c.cb + c.local_c);
        (dv, dv)
    } else {
        (
            (source_i - vd / c.rd) / c.cd,
            (-bridge_current - vb / c.rb) / (c.cb + c.local_c),
        )
    };
    Rate {
        ds: [
            dvd,
            dvb,
            if floating {
                0.0
            } else {
                (switch_fraction * vb - s[3] - (c.r_coil + c.r_pan) * i) / c.l
            },
            if floating { 0.0 } else { i / c.c },
        ],
        de: [
            source_i * vd,
            c.r_coil * i * i,
            c.r_pan * i * i,
            vd * vd / c.rd,
            vb * vb / c.rb,
        ],
        diode,
        floating,
    }
}

fn add(a: [f64; 4], k: [f64; 4], scale: f64) -> [f64; 4] {
    std::array::from_fn(|j| a[j] + scale * k[j])
}

fn step(c: &Case, t: f64, s: [f64; 4], h: f64) -> ([f64; 4], [f64; 5], bool) {
    let a = rate(c, t, s);
    let b = rate(c, t + h / 2.0, add(s, a.ds, h / 2.0));
    let d = rate(c, t + h / 2.0, add(s, b.ds, h / 2.0));
    // One-sided endpoint sample: an event exactly at t+h belongs to the
    // next interval, not the interval just integrated.
    let e = rate(c, t + h - h * 1e-6, add(s, d.ds, h));
    let next = std::array::from_fn(|j| {
        s[j] + h * (a.ds[j] + 2.0 * b.ds[j] + 2.0 * d.ds[j] + e.ds[j]) / 6.0
    });
    let ledger =
        std::array::from_fn(|j| h * (a.de[j] + 2.0 * b.de[j] + 2.0 * d.de[j] + e.de[j]) / 6.0);
    (next, ledger, a.diode)
}

fn step_h(c: &Case, t: f64) -> f64 {
    let mut h = c.dt.min(c.run - t);
    let mut events = [None; 2];
    events[0] = gate_off(c);
    events[1] = c.source_off;
    for event in events.into_iter().flatten() {
        if event > t + 1e-14 && event < t + h {
            h = event - t;
        }
    }
    let cycle = (t * c.f).floor();
    let gap = c.dead * c.f / 2.0;
    for n in [cycle, cycle + 1.0] {
        for phase in [gap, 0.5 - gap, 0.5 + gap, 1.0 - gap, 1.0] {
            let event = (n + phase) / c.f;
            if event > t + 1e-14 && event < t + h {
                h = event - t;
            }
        }
    }
    h
}

fn stored(c: &Case, s: [f64; 4]) -> f64 {
    0.5 * c.cd * s[0] * s[0]
        + 0.5 * (c.cb + c.local_c) * s[1] * s[1]
        + 0.5 * c.l * s[2] * s[2]
        + 0.5 * c.c * s[3] * s[3]
}

#[derive(Debug)]
struct ResultRow {
    id: String,
    status: &'static str,
    reason: String,
    t: f64,
    e0: f64,
    ledger: [f64; 5],
    e1: f64,
    residual: f64,
    s: [f64; 4],
    min_vb: f64,
    max_vd: f64,
    max_vb: f64,
    max_i: f64,
    max_vc: f64,
    local_e0: f64,
    diode_s: f64,
    gate_off: Option<f64>,
    last_current_above: Option<f64>,
}

fn simulate(c: &Case) -> ResultRow {
    let mut row = ResultRow {
        id: c.id.clone(),
        status: "CONDITIONAL",
        reason: "ideal fixed-topology waveform only".into(),
        t: 0.0,
        e0: stored(c, c.s0),
        ledger: [0.0; 5],
        e1: stored(c, c.s0),
        residual: 0.0,
        s: c.s0,
        min_vb: c.s0[1],
        max_vd: c.s0[0],
        max_vb: c.s0[1],
        max_i: c.s0[2].abs(),
        max_vc: c.s0[3].abs(),
        local_e0: 0.5 * c.local_c * c.s0[1] * c.s0[1],
        diode_s: 0.0,
        gate_off: gate_off(c),
        last_current_above: None,
    };
    if c.f2 == "opening" {
        row.status = "INDETERMINATE";
        row.reason = "F2 opening current and interconnect/arc/snubber energy unmodeled".into();
        return row;
    }
    if c.f2 == "reclosing" {
        row.status = "INDETERMINATE";
        row.reason = "F2 closing transient requires interconnect R/L model".into();
        return row;
    }
    // Fixed-step RK4. Stop precisely at the declared horizon; the source and
    // gate/PWM events partition intervals, and convergence is checked.
    while row.t < c.run {
        let h = step_h(c, row.t);
        let (mut next, energy, diode) = step(c, row.t, row.s, h);
        row.t += h;
        if rate(c, row.t, next).floating {
            next[2] = 0.0;
        }
        row.s = next;
        for (total, increment) in row.ledger.iter_mut().zip(energy) {
            *total += increment;
        }
        if diode {
            row.diode_s += h;
        }
        row.min_vb = row.min_vb.min(next[1]);
        row.max_vd = row.max_vd.max(next[0]);
        row.max_vb = row.max_vb.max(next[1]);
        row.max_i = row.max_i.max(next[2].abs());
        row.max_vc = row.max_vc.max(next[3].abs());
        if row.gate_off.is_some_and(|off| row.t >= off) && next[2].abs() > c.stop_threshold {
            row.last_current_above = Some(row.t);
        }
        if next.iter().any(|x| !x.is_finite()) || next[0] < 0.0 || next[1] < 0.0 {
            row.status = "INDETERMINATE";
            row.reason = "ideal model exited nonnegative bus state".into();
            break;
        }
        if next[0] > c.ceiling || next[1] > c.ceiling {
            row.status = "REJECTED";
            row.reason = "declared voltage screen ceiling crossed".into();
            break;
        }
    }
    row.e1 = stored(c, row.s);
    row.residual = row.e1 - row.e0 - row.ledger[0]
        + row.ledger[1]
        + row.ledger[2]
        + row.ledger[3]
        + row.ledger[4];
    let scale = row.e0.abs().max(row.ledger[0].abs()).max(1.0);
    if row.status == "CONDITIONAL" && row.residual.abs() > 1e-3 * scale {
        row.status = "INDETERMINATE";
        row.reason = "numerical energy residual exceeds 0.1 percent".into();
    }
    if row.status == "CONDITIONAL" && row.max_vc > c.tank_v_screen {
        row.status = "REJECTED";
        row.reason = "tank capacitor voltage exceeds declared screen ceiling".into();
    }
    if row.status == "CONDITIONAL" && row.max_i > c.tank_i_screen {
        row.status = "REJECTED";
        row.reason = "tank current exceeds declared screen ceiling".into();
    }
    if row.status == "CONDITIONAL" && row.gate_off.is_some_and(|off| off > row.t) {
        row.status = "INDETERMINATE";
        row.reason = "gate-off event lies beyond modeled horizon".into();
    }
    if row.status == "CONDITIONAL"
        && row.gate_off.is_some_and(|off| off <= row.t)
        && row.s[2].abs() > c.stop_threshold
    {
        row.status = "INDETERMINATE";
        row.reason = "tank current remains above threshold at modeled horizon".into();
    }
    row
}

fn fmt_optional(v: Option<f64>) -> String {
    v.map_or_else(|| "na".into(), |x| format!("{:.6}", x * 1e3))
}

fn csv_row(r: &ResultRow) -> String {
    format!(
        "{},{},{},{:.6},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},{:.9},UNMODELED,{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.9},{:.6},{},{}",
        r.id, r.status, r.reason, r.t * 1e3, r.e0, r.ledger[0], r.e1,
        r.ledger[1], r.ledger[2], r.ledger[3], r.ledger[4], r.residual,
        r.s[0], r.s[1], r.min_vb, r.max_vd, r.max_vb, r.max_i, r.max_vc,
        r.local_e0, r.diode_s * 1e3, fmt_optional(r.gate_off),
        fmt_optional(r.last_current_above)
    )
}

fn run(input: &str) -> Result<String, String> {
    let mut lines = input
        .lines()
        .filter(|line| !line.trim().is_empty() && !line.starts_with('#'));
    if lines.next() != Some(HEADER) {
        return Err("scenario header differs from model schema".into());
    }
    let mut output = OUT_HEADER.to_owned();
    for line in lines {
        let id = line.split(',').next().unwrap_or("unknown").trim();
        let row = match parse_case(line) {
            Ok(c) => csv_row(&simulate(&c)),
            Err(reason) => format!("{id},REJECTED,{reason},na,na,na,na,na,na,na,na,na,UNMODELED,na,na,na,na,na,na,na,na,na,na,na"),
        };
        output.push('\n');
        output.push_str(&row);
    }
    output.push('\n');
    Ok(output)
}

fn main() {
    let path = env::args().nth(1).expect("provide transient scenario CSV");
    let input = fs::read_to_string(path).expect("read scenario CSV");
    print!("{}", run(&input).expect("parse scenario file"));
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> Case {
        parse_case("test,hot0,closed,390,390,0,0,22.47,2240,0.47,59.84,300,0.2,0.8,47,300,1,permit,0,0,0,0,390,0,0,0,500000,450000,430,0.1,1600,160,50").unwrap()
    }

    #[test]
    fn closed_source_off_rc_matches_analytic_solution() {
        let c = base();
        let r = simulate(&c);
        let effective_rate = (1.0 / c.rd + 1.0 / c.rb) / (c.cd + c.cb + c.local_c);
        let expected = 390.0 * (-effective_rate * c.run).exp();
        assert!((r.s[0] - expected).abs() < 1e-5);
        assert!((r.s[1] - expected).abs() < 1e-5);
        assert!(r.residual.abs() < 1e-7);
    }

    #[test]
    fn open_source_off_island_rc_matches_two_analytic_solutions() {
        let mut c = base();
        c.f2 = "open".into();
        c.s0[0] = 400.0;
        c.s0[1] = 380.0;
        let r = simulate(&c);
        assert!((r.s[0] - 400.0 * (-c.run / (c.rd * c.cd)).exp()).abs() < 1e-5);
        assert!((r.s[1] - 380.0 * (-c.run / (c.rb * (c.cb + c.local_c))).exp()).abs() < 1e-5);
        assert!(r.residual.abs() < 1e-7);
    }

    #[test]
    fn driven_tank_energy_ledger_and_timestep_converge() {
        let mut c = base();
        c.source_off = None;
        c.source_command = 20.0;
        c.source_max_i = 6.0;
        c.source_max_p = 1800.0;
        c.stop_at = Some(0.0005);
        c.stop_delay = 20e-6;
        let fine = simulate(&c);
        c.dt *= 2.0;
        let coarse = simulate(&c);
        assert_eq!(fine.status, "CONDITIONAL", "{}", fine.reason);
        assert!(fine.residual.abs() < 0.01);
        assert!(coarse.residual.abs() < 0.02);
        assert!((fine.s[1] - coarse.s[1]).abs() < 1.0);
        assert!((fine.max_i - coarse.max_i).abs() < 1.0);
        assert!(fine.ledger[0] >= 0.0);
    }

    #[test]
    fn rejects_midpoint_missing_load_and_unequal_reclose() {
        let mut c = base();
        c.topology = "pwr_rtn".into();
        assert!(validate(&c).is_err());
        c = base();
        c.l = 0.0;
        assert!(validate(&c).is_err());
        c = base();
        c.f2 = "reclosing".into();
        c.s0[1] = 380.0;
        assert!(validate(&c).is_err());
        c = base();
        c.s0[0] = 450.0;
        assert!(validate(&c).is_err());
    }

    #[test]
    fn gate_command_is_not_instantaneous_current_extinction() {
        let mut c = base();
        c.s0[2] = 10.0;
        c.stop_at = Some(0.0);
        c.stop_delay = 10e-6;
        let r = simulate(&c);
        assert!(r.max_i >= 10.0);
        assert!(r.last_current_above.is_some());
        assert!(r.diode_s > 0.0);
    }

    #[test]
    fn stop_after_horizon_cannot_receive_conditional_verdict() {
        let mut c = base();
        c.stop_at = Some(0.0005);
        c.stop_delay = 0.002;
        c.run = 0.001;
        let r = simulate(&c);
        assert_eq!(r.status, "INDETERMINATE");
        assert_eq!(r.reason, "gate-off event lies beyond modeled horizon");
    }

    #[test]
    fn post_gate_off_threshold_time_converges() {
        let mut c = base();
        c.s0[3] = 195.0;
        c.run = 0.002;
        c.stop_at = Some(0.0005);
        c.stop_delay = 20e-6;
        c.source_off = None;
        c.source_command = 6.0;
        c.source_max_i = 6.0;
        c.source_max_p = 1800.0;
        c.dt = 5e-9;
        let a = simulate(&c);
        c.dt = 2.5e-9;
        let b = simulate(&c);
        let ta = a.last_current_above.expect("threshold crossed after stop");
        let tb = b.last_current_above.expect("threshold crossed after stop");
        assert!((ta - tb).abs() < 0.1e-6);
        assert!((a.s[1] - b.s[1]).abs() < 0.005);
        assert!(a.residual.abs() < 0.002);
        assert!(b.residual.abs() < 0.001);
    }

    #[test]
    fn off_state_diodes_obey_zero_current_complementarity() {
        let mut c = base();
        c.s0[3] = 195.0;
        let idle = rate(&c, 0.0001, c.s0);
        assert!(idle.floating);
        assert_eq!(idle.ds[2], 0.0);
        c.s0[3] = 500.0;
        let high_diode = rate(&c, 0.0001, c.s0);
        assert!(!high_diode.floating);
        assert!(high_diode.ds[2] < 0.0);
        c.s0[3] = -10.0;
        let low_diode = rate(&c, 0.0001, c.s0);
        assert!(!low_diode.floating);
        assert!(low_diode.ds[2] > 0.0);
    }

    #[test]
    fn independent_power_identity_and_capacitance_dimensions() {
        let c = base();
        assert!((0.5 * c.cb * 390.0_f64.powi(2) - 170.352).abs() < 1e-9);
        assert!((0.5 * c.local_c * 390.0_f64.powi(2) - 0.0357435).abs() < 1e-9);
        for f2 in ["closed", "open"] {
            let mut x = c.clone();
            x.f2 = f2.into();
            x.s0 = if f2 == "closed" {
                [390.0, 390.0, 12.0, 85.0]
            } else {
                [400.0, 380.0, -12.0, 85.0]
            };
            x.source_command = 20.0;
            x.source_max_i = 6.0;
            x.source_max_p = 1800.0;
            x.source_off = None;
            let k = rate(&x, 0.000123, x.s0);
            let d_stored = x.cd * x.s0[0] * k.ds[0]
                + (x.cb + x.local_c) * x.s0[1] * k.ds[1]
                + x.l * x.s0[2] * k.ds[2]
                + x.c * x.s0[3] * k.ds[3];
            let external_power = k.de[0] - k.de[1..].iter().sum::<f64>();
            assert!((d_stored - external_power).abs() < 1e-7);
            assert!(source_current(&x, 0.0, x.s0[0]) >= 0.0);
            assert!(source_current(&x, 0.0, x.s0[0]) <= x.source_max_i);
            x.source_command = 0.0;
            x.source_gain = 100.0;
            x.source_target = 390.0;
            assert_eq!(source_current(&x, 0.0, 400.0), 0.0);
        }
    }
}
