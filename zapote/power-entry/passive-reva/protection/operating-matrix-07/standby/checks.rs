use std::{env, fs};
fn check(text: &str) -> Result<(), String> {
    let mut lines = text.lines();
    let header =
        "time v(aux15) v(permit) v(vsense) v(xstandby.inhibit_gate) v(xstandby.permit_gate)";
    if lines
        .next()
        .map(|s| s.split_whitespace().collect::<Vec<_>>())
        != Some(header.split_whitespace().collect())
    {
        return Err("wrong header".into());
    }
    let mut rows: Vec<Vec<f64>> = Vec::new();
    for line in lines {
        let r = line
            .split_whitespace()
            .map(|s| s.parse::<f64>().map_err(|_| "invalid number".to_string()))
            .collect::<Result<Vec<_>, _>>()?;
        if r.len() != 6 || r.iter().any(|x| !x.is_finite()) {
            return Err("width/nonfinite".into());
        }
        if let Some(p) = rows.last() {
            if r[0] <= p[0] || r[0] - p[0] > 101e-9 {
                return Err("time gap/order".into());
            }
        }
        if r[4].abs() > 12. || r[5].abs() > 12. {
            return Err("gate absolute limit".into());
        }
        rows.push(r);
    }
    let first = rows.first().ok_or("empty trace")?;
    let last = rows.last().ok_or("empty trace")?;
    if first[0] < 0. || first[0] > 1e-8 || (last[0] - 800e-6).abs() > 1e-9 {
        return Err("incomplete trace".into());
    }
    for (name, a, b, on) in [
        ("default standby", 40., 90., false),
        ("permit releases", 170., 240., true),
        ("permit loss clamps", 290., 390., false),
        ("repeat release", 470., 490., true),
        ("floating permit defaults off", 740., 790., false),
    ] {
        let w = rows
            .iter()
            .filter(|r| r[0] >= a * 1e-6 && r[0] <= b * 1e-6)
            .collect::<Vec<_>>();
        if w.is_empty() {
            return Err(format!("missing {name}"));
        }
        if w.iter().any(|r| {
            if on {
                r[3] < 4.9 || r[3] > 5.1
            } else {
                r[3] > 0.1
            }
        }) {
            return Err(format!("{name} violated"));
        }
    }
    Ok(())
}
fn main() {
    let result = (|| {
        let args = env::args().collect::<Vec<_>>();
        if args.len() != 2 {
            return Err("usage: checks TRACE.tsv".into());
        }
        check(&fs::read_to_string(&args[1]).map_err(|e| e.to_string())?)
    })();
    match result{Ok(())=>println!("PASS physical standby topology: default, release, driven low, repeated release, floating permit; VGS within12V"),Err(e)=>{eprintln!("FAIL {e}");std::process::exit(1)}}
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_trace_fails() {
        assert!(check("").is_err())
    }
    #[test]
    fn wrong_probe_names_fail() {
        assert!(check("time v(foo)").unwrap_err().contains("header"))
    }
}
