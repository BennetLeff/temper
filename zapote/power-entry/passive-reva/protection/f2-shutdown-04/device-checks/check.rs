//! Check actual ngspice DC solutions against independent device anchors.
use std::{collections::BTreeMap, env, fs};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let text = fs::read_to_string(env::args().nth(1).ok_or("log path required")?)?;
    let mut values = BTreeMap::new();
    for line in text.lines() {
        if let Some((key, value)) = line.split_once(" = ") {
            if ["v(d)", "i(vsense)", "v(da)", "i(vrs)"].contains(&key) {
                let value: f64 = value.trim().parse()?;
                if !value.is_finite() || values.insert(key, value).is_some() { return Err("invalid or duplicate measurement".into()); }
            }
        }
    }
    if values.len() != 4 { return Err("missing DC measurements".into()); }
    let resistance = values["v(d)"] / values["i(vsense)"];
    if (values["i(vsense)"] - 30.0).abs() > 1e-6 || !(0.049..0.051).contains(&resistance) { return Err("MOS conduction anchor failed".into()); }
    if !(1.40..1.55).contains(&values["v(da)"]) { return Err("SiC forward voltage anchor failed".into()); }
    if values["i(vrs)"].abs() > 1e-9 { return Err("intrinsic MOS diode was not suppressed".into()); }
    println!("PASS actual ngspice DC: RDS={resistance:.9}ohm at30.0A/VGS10V; diodeVF={}V at10A/27C; suppressed intrinsic current={}A atVDS=-0.8V/VGS0",values["v(da)"],values["i(vrs)"]);
    Ok(())
}
