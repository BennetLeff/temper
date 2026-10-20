use std::{collections::HashMap, env, fs};
fn read(p: &str) -> Result<HashMap<String, f64>, String> {
    let t = fs::read_to_string(p).map_err(|e| e.to_string())?;
    if !t.contains("No. Points: 1\n") || !t.contains("Plotname: Operating Point\n") {
        return Err("not single operating point".into());
    }
    let (h, v) = t.split_once("Values:\n").ok_or("missing values")?;
    let vars = h.split_once("Variables:\n").ok_or("missing variables")?.1;
    let names: Vec<_> = vars
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.split_whitespace().nth(1).unwrap().to_string())
        .collect();
    let vals = v
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_whitespace()
                .last()
                .unwrap()
                .parse::<f64>()
                .map_err(|e| e.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if names.len() != vals.len() {
        return Err("variable/value count differs".into());
    }
    if vals.iter().any(|v| !v.is_finite()) {
        return Err("nonfinite".into());
    }
    Ok(names.into_iter().zip(vals).collect())
}
fn check(p: &str) -> Result<String, String> {
    let r = read(p)?;
    let v5 = r["v(v5)"];
    let expected = v5 / (2. + 1e-6);
    for amp in ["xa", "xb"] {
        let mid = r[&format!("v({amp}.mid)")];
        if (mid - expected).abs() > 1e-6 {
            return Err(format!(
                "{amp}.MID={mid:.12e}V; expected {expected:.12e}V; false DC state"
            ));
        }
    }
    let acin = r["v(acin)"];
    if acin.abs() > 1e-4 {
        return Err(format!("AC-coupled source has DC {acin}V"));
    }
    Ok(format!(
        "MID_A={:.9}V MID_B={:.9}V source_AC={acin:.12e}V",
        r["v(xa.mid)"], r["v(xb.mid)"]
    ))
}
fn main() {
    let a: Vec<_> = env::args().collect();
    if a.len() > 1 {
        match check(&a[1]) {
            Ok(m) => println!("PASS {m}"),
            Err(e) => {
                eprintln!("REJECT {e}");
                std::process::exit(1)
            }
        }
        return;
    }
    let mut out=String::from("# True-DC regression guard\n\nThe guard parses every value, requires exactly one operating point, checks both FDA internal MID references against the DC divider equation and checks the DC-blocked source input. It does not accept ngspice exit code or transient fallback as sufficient evidence.\n\n");
    for p in [
        "strict-good.raw",
        "100r_cap100n_op.raw",
        "100r_cap500n_op.raw",
        "100r_cap9u_op.raw",
        "100r_coil50u_op.raw",
        "5k_resistor_op.raw",
        "100k_resistor_op.raw",
    ] {
        let m = check(p).unwrap_or_else(|e| panic!("{p}: {e}"));
        out += &format!("- `{p}`: PASS {m}\n");
    }
    let e = check("target-base.raw").expect_err("negative regression unexpectedly accepted");
    out+=&format!("\nNegative regression: `target-base.raw` REJECTED: {e}.\n\nThis preserved log says `Transient op finished successfully`; it must not be treated as a true DC operating point. Initial guesses are never accepted without checking the resulting final DC state.\n");
    fs::write("dc-regression.md", out).unwrap();
    println!("Seven positive cases accepted; known false operating point rejected.");
}
