//! Strict bounded checks for the authored hysteretic-driver candidate.
//! This validates traces and reports model-to-model deltas; it is not a
//! hardware qualification or an equivalence claim.
use std::{env, fs, process};

fn fail(message: impl AsRef<str>) -> ! { eprintln!("hysteretic-driver: {}", message.as_ref()); process::exit(1); }

#[derive(Clone)] struct Trace { names: Vec<String>, rows: Vec<Vec<f64>> }

fn read_trace_gap(path: &str, end: f64, max_gap: f64) -> Trace {
    let text = fs::read_to_string(path).unwrap_or_else(|e| fail(format!("read {path}: {e}")));
    let mut lines = text.lines();
    let names: Vec<_> = lines.next().unwrap_or_else(|| fail(format!("empty {path}")))
        .split_whitespace().map(str::to_owned).collect();
    if names.first().map(String::as_str) != Some("time") { fail(format!("{path}: missing time column")); }
    for i in 0..names.len() { if names[..i].contains(&names[i]) { fail(format!("{path}: duplicate {}", names[i])); } }
    let mut rows = Vec::new();
    let mut previous = None;
    for (line_no, line) in lines.enumerate() {
        let fields: Vec<_> = line.split_whitespace().collect();
        if fields.is_empty() { continue; }
        if fields.len() != names.len() { fail(format!("{path}: line {} fields {} != {}", line_no + 2, fields.len(), names.len())); }
        let row: Vec<f64> = fields.iter().map(|x| x.parse().unwrap_or_else(|_| fail(format!("{path}: nonnumeric {x}")))).collect();
        if row.iter().any(|x| !x.is_finite()) { fail(format!("{path}: nonfinite line {}", line_no + 2)); }
        if let Some(last) = previous {
            if row[0] <= last { fail(format!("{path}: non-increasing time at line {}", line_no + 2)); }
            if row[0] - last > max_gap { fail(format!("{path}: time gap {:.3e} s", row[0] - last)); }
        }
        previous = Some(row[0]); rows.push(row);
    }
    if rows.len() < 100 { fail(format!("{path}: too few rows")); }
    if rows[0][0].abs() > 2e-12 || (rows.last().unwrap()[0] - end).abs() > 2e-12 { fail(format!("{path}: endpoint {:.17e}, expected {end:.17e}", rows.last().unwrap()[0])); }
    Trace { names, rows }
}
fn read_trace(path: &str, end: f64) -> Trace { read_trace_gap(path, end, 1.001e-9) }

fn col(t: &Trace, name: &str) -> usize { t.names.iter().position(|n| n == name).unwrap_or_else(|| fail(format!("missing {name}"))) }
fn window<'a>(t: &'a Trace, time: usize, value: usize, lo: f64, hi: f64) -> Vec<f64> { t.rows.iter().filter(|r| r[time] >= lo && r[time] <= hi).map(|r| r[value]).collect() }
fn minv(v: &[f64]) -> f64 { v.iter().copied().fold(f64::INFINITY, f64::min) }
fn maxabs(v: &[f64]) -> f64 { v.iter().map(|x| x.abs()).fold(0.0, f64::max) }
fn crossing(t: &Trace, input: usize, output: usize, level: f64, rising: bool) -> (f64, f64) {
    for pair in t.rows.windows(2) {
        let (a, b) = (&pair[0], &pair[1]);
        let hit = if rising { a[output] < level && b[output] >= level } else { a[output] >= level && b[output] < level };
        if hit { let f = (level - a[output]) / (b[output] - a[output]); return (a[0] + f * (b[0] - a[0]), a[input] + f * (b[input] - a[input])); }
    }
    fail(format!("no {} crossing at {level} V", if rising { "rising" } else { "falling" }))
}
fn crossing_window(t: &Trace, input: usize, output: usize, level: f64, rising: bool, lo: f64, hi: f64) -> (f64, f64) {
    for pair in t.rows.windows(2) {
        let (a, b) = (&pair[0], &pair[1]);
        if b[0] < lo || a[0] > hi { continue; }
        let hit = if rising { a[output] < level && b[output] >= level } else { a[output] >= level && b[output] < level };
        if hit { let f = (level - a[output]) / (b[output] - a[output]); return (a[0] + f * (b[0] - a[0]), a[input] + f * (b[input] - a[input])); }
    }
    fail(format!("no {} crossing at {level} V in [{lo:.3e},{hi:.3e}]", if rising { "rising" } else { "falling" }))
}
fn report_pair(label: &str, vendor: &Trace, authored: &Trace, vi: &str, vo: &str, ai: &str, ao: &str) {
    let v_in = col(vendor, vi); let v_out = col(vendor, vo); let a_in = col(authored, ai); let a_out = col(authored, ao);
    let vr = crossing(vendor, v_in, v_out, 13.5, true); let vf = crossing(vendor, v_in, v_out, 13.5, false);
    let ar = crossing(authored, a_in, a_out, 13.5, true); let af = crossing(authored, a_in, a_out, 13.5, false);
    println!("{label}: vendor 13.5 V rise {:.3} ns @ {:.4} V, fall {:.3} ns @ {:.4} V; authored rise {:.3} ns @ {:.4} V, fall {:.3} ns @ {:.4} V", vr.0*1e9,vr.1,vf.0*1e9,vf.1,ar.0*1e9,ar.1,af.0*1e9,af.1);
}
fn report_gate_pair(label: &str, vendor: &Trace, authored: &Trace, vi: &str, ai: &str) {
    let v_in = col(vendor, vi); let a_in = col(authored, ai);
    let vg = col(vendor, "v(gate)"); let ag = col(authored, "v(gate)");
    let vr = crossing(vendor, v_in, vg, 4.0, true); let vf = crossing(vendor, v_in, vg, 4.0, false);
    let ar = crossing(authored, a_in, ag, 4.0, true); let af = crossing(authored, a_in, ag, 4.0, false);
    let vp = vendor.rows.iter().map(|r| r[vg]).fold(f64::NEG_INFINITY, f64::max);
    let ap = authored.rows.iter().map(|r| r[ag]).fold(f64::NEG_INFINITY, f64::max);
    println!("{label} gate4: vendor rise {:.3} ns @ {:.4} V, fall {:.3} ns @ {:.4} V, peak {:.6} V; authored rise {:.3} ns @ {:.4} V, fall {:.3} ns @ {:.4} V, peak {:.6} V", vr.0*1e9,vr.1,vf.0*1e9,vf.1,vp,ar.0*1e9,ar.1,af.0*1e9,af.1,ap);
}
fn main() {
    let dir = env::args().nth(1).unwrap_or_else(|| ".".into());
    let p = |n: &str| format!("{dir}/{n}");
    let vendor = read_trace(&p("vendor-threshold.tsv"), 8e-6);
    let authored = read_trace(&p("authored-threshold-hysteretic.tsv"), 8e-6);
    report_pair("slow", &vendor, &authored, "v(pwm_input)", "v(outh)", "v(pwm_input)", "v(driver_out)");
    report_gate_pair("slow", &vendor, &authored, "v(pwm_input)", "v(pwm_input)");
    let vf = read_trace(&p("vendor-fast.tsv"), 8e-6);
    let af = read_trace(&p("authored-fast.tsv"), 8e-6);
    report_pair("1 ns", &vf, &af, "v(pwm_input)", "v(outh)", "v(pwm_input)", "v(driver_out)");
    report_gate_pair("1 ns", &vf, &af, "v(pwm_input)", "v(pwm_input)");
    let at = col(&authored, "v(gate)");
    if minv(&window(&authored, col(&authored,"time"), at, 3.5e-6, 4.8e-6)) < 14.0 { fail("authored slow high plateau below 14 V"); }
    let vs = read_trace(&p("vendor-sequence.tsv"), 35e-6);
    let as_ = read_trace(&p("authored-sequence.tsv"), 35e-6);
    let ti = col(&vs, "time"); let ai = col(&as_, "time"); let vg = col(&vs, "v(gate)"); let ag = col(&as_, "v(gate)");
    let windows = [("default-off",0.0,0.9e-6,false,0.1), ("pwm-high",2e-6,4.5e-6,true,14.0), ("pwm-off",6e-6,7.5e-6,false,0.1), ("pwm-reenabled",9e-6,11.5e-6,true,14.0), ("run-off",13e-6,14.5e-6,false,0.1), ("aux-high",17e-6,19.5e-6,true,14.0), ("aux-drop",21e-6,26.5e-6,false,0.1), ("aux-return-disarmed",28e-6,29.5e-6,false,0.1), ("rearmed",32e-6,34.5e-6,true,14.0)];
    for (name,lo,hi,high,limit) in windows {
        let av = window(&as_, ai, ag, lo, hi); let vv = window(&vs, ti, vg, lo, hi);
        if av.is_empty() || vv.is_empty() { fail(format!("{name}: empty window")); }
        let am = if high { minv(&av) } else { maxabs(&av) };
        let vm = if high { minv(&vv) } else { maxabs(&vv) };
        if high && am < limit { fail(format!("{name}: authored min {am:.6} V below {limit}")); }
        if !high && am > limit { fail(format!("{name}: authored max(abs) {am:.6} V above {limit}")); }
        let vm_limit = if high { 14.0 } else { 0.1 };
        if (high && vm < vm_limit) || (!high && vm > vm_limit) { fail(format!("{name}: vendor check {vm:.6} V outside {vm_limit}")); }
        println!("sequence {name}: vendor {:.6} V, authored {:.6} V", vm, am);
    }
    let vrun = crossing_window(&vs, ti, vg, 4.0, false, 12e-6, 14.5e-6);
    let arun = crossing_window(&as_, ai, ag, 4.0, false, 12e-6, 14.5e-6);
    let vaux = crossing_window(&vs, ti, vg, 4.0, false, 20e-6, 26.5e-6);
    let aaux = crossing_window(&as_, ai, ag, 4.0, false, 20e-6, 26.5e-6);
    println!("sequence gate4 fall: RUN event vendor {:.3} ns / authored {:.3} ns; AUX event vendor {:.3} ns / authored {:.3} ns", vrun.0*1e9, arun.0*1e9, vaux.0*1e9, aaux.0*1e9);
    let late = read_trace_gap(&p("authored-late.tsv"), 0.25702, 500.001e-9);
    let lt = col(&late, "time"); let lp = col(&late, "v(pwm_input)"); let lg = col(&late, "v(gate)");
    let late_pre = window(&late, lt, lg, 0.25698, 0.256989);
    let late_post = window(&late, lt, lg, 0.257005, 0.25702);
    if late_pre.is_empty() || minv(&late_pre) < 14.0 { fail("late probe did not hold a high gate plateau"); }
    if late_post.is_empty() || maxabs(&late_post) > 0.1 { fail("late probe did not settle gate off"); }
    println!("late screen: {:.0} rows, PWM {:.3}->{:.3} V; gate pre-min {:.6} V, post-max(abs) {:.6} V", late.rows.len(), late.rows.first().unwrap()[lp], late.rows.last().unwrap()[lp], minv(&late_pre), maxabs(&late_post));

    let aux = read_trace(&p("authored-aux-sweep.tsv"), 8e-6);
    let aux_t = col(&aux, "time"); let aux_v = col(&aux, "v(aux15)"); let aux_s = col(&aux, "v(xdriver.aux_state)"); let aux_g = col(&aux, "v(gate)");
    let aux_r = crossing(&aux, aux_v, aux_s, 0.5, true); let aux_f = crossing(&aux, aux_v, aux_s, 0.5, false);
    if !(4.19..=4.21).contains(&aux_r.1) || !(3.89..=3.91).contains(&aux_f.1) { fail(format!("AUX state crossings {:.6} V/{:.6} V outside 4.2/3.9 V", aux_r.1, aux_f.1)); }
    let aux_high = window(&aux, aux_t, aux_g, 4.0e-6, 4.8e-6); let aux_low0 = window(&aux, aux_t, aux_g, 0.0, 0.8e-6); let aux_low1 = window(&aux, aux_t, aux_g, 7.2e-6, 8.0e-6);
    if aux_high.is_empty() || minv(&aux_high) < 5.8 { fail("AUX=6 V plateau did not reach 5.8 V gate"); }
    if maxabs(&aux_low0) > 0.1 || maxabs(&aux_low1) > 0.1 { fail("AUX invalid windows did not hold gate off"); }
    println!("AUX sweep: state rise {:.6} V at {:.3} us, fall {:.6} V at {:.3} us; 6 V gate min {:.6} V", aux_r.1, aux_r.0*1e6, aux_f.1, aux_f.0*1e6, minv(&aux_high));

    let inm = read_trace(&p("authored-inm-sweep.tsv"), 8e-6);
    let inm_t = col(&inm, "time"); let inm_v = col(&inm, "v(disable)"); let inm_s = col(&inm, "v(xdriver.inm_state)"); let inm_g = col(&inm, "v(gate)");
    let inm_r = crossing(&inm, inm_v, inm_s, 0.5, true); let inm_f = crossing(&inm, inm_v, inm_s, 0.5, false);
    if !(2.19..=2.21).contains(&inm_r.1) || !(1.19..=1.21).contains(&inm_f.1) { fail(format!("INM state crossings {:.6} V/{:.6} V outside 2.2/1.2 V", inm_r.1, inm_f.1)); }
    let inm_on0 = window(&inm, inm_t, inm_g, 0.0, 0.8e-6); let inm_off = window(&inm, inm_t, inm_g, 3.5e-6, 5.5e-6); let inm_on1 = window(&inm, inm_t, inm_g, 7.2e-6, 8.0e-6);
    if inm_on0.is_empty() || minv(&inm_on0) < 14.0 || inm_on1.is_empty() || minv(&inm_on1) < 14.0 { fail("INM enabled windows did not hold gate high"); }
    if maxabs(&inm_off) > 0.1 { fail("INM disabled window did not hold gate off"); }
    println!("INM sweep: state rise {:.6} V at {:.3} us, fall {:.6} V at {:.3} us; enabled peaks {:.6}/{:.6} V", inm_r.1, inm_r.0*1e6, inm_f.1, inm_f.0*1e6, minv(&inm_on0), minv(&inm_on1));
    println!("hysteretic-driver: PASS (strict finite traces; authored interface remains an explicitly approximate candidate)");
}
