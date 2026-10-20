use std::{collections::HashMap, fs};
fn main() {
    let old = fs::read_to_string("corner-results.csv").unwrap();
    fs::write("corner-initial-attempts.csv", &old).unwrap();
    let retry = fs::read_to_string("retry-results.csv").unwrap();
    let map: HashMap<_, _> = retry
        .lines()
        .map(|l| (l.split(',').next().unwrap(), l))
        .collect();
    assert_eq!(map.len(), 3);
    let mut changed = 0;
    let out = old
        .lines()
        .map(|l| {
            if let Some(r) = map.get(l.split(',').next().unwrap()) {
                assert!(l.contains("FAIL:timeout"));
                changed += 1;
                *r
            } else {
                l
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    assert_eq!(changed, 3);
    assert_eq!(out.lines().count(), 55);
    assert!(!out.contains("FAIL"));
    fs::write("corner-results.csv", out).unwrap();
}
