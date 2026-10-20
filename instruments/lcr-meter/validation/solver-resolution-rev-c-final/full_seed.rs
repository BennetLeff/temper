use std::fs;
fn main() {
    let raw = fs::read_to_string("old-strict-good.raw").unwrap();
    let (h, v) = raw.split_once("Values:\n").unwrap();
    let names: Vec<_> = h
        .split_once("Variables:\n")
        .unwrap()
        .1
        .lines()
        .map(|l| l.split_whitespace().nth(1).unwrap())
        .collect();
    let values: Vec<f64> = v
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.split_whitespace().last().unwrap().parse().unwrap())
        .collect();
    assert_eq!(names.len(), values.len());
    let mut out = String::new();
    for (n, v) in names.iter().zip(values) {
        if n.starts_with("v(") {
            out += &format!(".nodeset {n}={v:.15e}\n")
        }
    }
    fs::write("old-full-seed.inc", out).unwrap();
    let base = fs::read_to_string("final-cap.cir").unwrap();
    for exponent in [24, 30, 36] {
        let n = format!("shunt{exponent}");
        let s = base
            .replace("old-offset-nodeset.inc", "old-full-seed.inc")
            .replace("method=gear", &format!("method=gear rshunt=1e{exponent}"))
            .replace("write final-cap.raw", &format!("write {n}.raw"));
        fs::write(format!("{n}.cir"), s).unwrap();
    }
}
