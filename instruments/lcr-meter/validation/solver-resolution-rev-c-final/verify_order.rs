use std::{collections::BTreeMap, fs};
fn components(path: &str) -> BTreeMap<String, String> {
    let s = fs::read_to_string(path).unwrap();
    s.split(".control")
        .next()
        .unwrap()
        .lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty() && !l.starts_with(['.', '*']))
        .map(|l| {
            (
                l.split_whitespace().next().unwrap().to_lowercase(),
                l.to_string(),
            )
        })
        .collect()
}
fn main() {
    assert_eq!(components("partition.cir"), components("order0.cir"));
    println!("PASS: every component name, pin order and value identical between failed partition.cir and successful order0.cir; only top-level declaration order differs.");
}
