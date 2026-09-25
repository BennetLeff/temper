//! TEST_ONLY native42 FIFO producer; never an electrical simulation.
use std::{env, fs::OpenOptions, io::Write, path::Path};

const NAMES: [&str; 42] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)", "i(Lboost)", "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)", "v(fault)", "v(vcomp)", "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)", "v(pwm)", "v(pwm_input)", "v(xdriver.driver_req)", "v(xdriver.drv_delay)", "v(xu.phase)", "v(xu.blank)", "v(isense)", "v(xu.ov)", "v(xu.fault)", "v(xu.pcl_hold)", "v(xu.pcl_request)", "v(disable)", "v(xu.m1)", "v(xu.m2)", "v(acsrc,acn)", "i(Vchannel)", "i(Vbody)", "v(f2ctl)", "v(standby_req)", "v(arm)", "v(permit)", "i(Vf2sense)", "i(Vdboost1sense)", "i(Vdboost2sense)", "v(fault_inject)",
];

fn row(t: f64, fault: bool, event: bool) -> [f64; 42] {
    let mut values = [0.0; 42]; values[0] = t; values[4] = 100.0; values[5] = 390.0; values[7] = 400.0;
    values[10] = 5.0; values[11] = 5.0; values[36] = 5.0; values[37] = 5.0;
    values[34] = if event { 0.0 } else { 5.0 }; values[41] = if event { 5.0 } else { 0.0 }; values[12] = if fault { 5.0 } else { 0.0 }; values
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect(); if args.len() != 6 { return Err("usage: synthetic-native-host DECK WALL TSTOP FIFO SNAPSHOT".into()); }
    let tstop: f64 = args[3].parse()?; let fifo = Path::new(&args[4]);
    let rows = [row(0.0, false, false), row(0.8e-6, false, false), row(0.9e-6, false, false), row(1.0e-6, false, true), row(tstop, true, true)];
    let mut out = OpenOptions::new().write(true).open(fifo)?;
    writeln!(out, "Title: TEST_ONLY\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 42\nNo. Points: 5\nVariables:")?;
    for (i, name) in NAMES.iter().enumerate() { let unit = if *name == "time" { "time" } else if name.starts_with("i(") { "current" } else { "voltage" }; writeln!(out, "\t{i}\t{name}\t{unit}")?; }
    writeln!(out, "Binary:")?;
    for values in rows { for value in values { out.write_all(&value.to_le_bytes())?; } }
    std::fs::write("capture-metadata.json", "{\"stop_reason\": \"solver_stopped\", \"points\": 5, \"first_invalid\": false, \"seen_names_mask\": 65535, \"expected_names_mask\": 65535, \"duplicate_count\": 0, \"backwards_count\": 0, \"nonfinite_time\": false, \"diagnostic_only\": true, \"accepted\": false, \"export_format\": \"ngspice-real-native\", \"byte_order\": \"little\", \"schema\": \"fault42\"}\n")?;
    Ok(())
}
