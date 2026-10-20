use std::{fs, process::Command};
fn main() {
    let mut count = 0;
    for e in fs::read_dir(".").unwrap() {
        let p = e.unwrap().path();
        let n = p.file_name().unwrap().to_str().unwrap();
        if !n.ends_with(".cir") {
            continue;
        }
        let positive = [
            "100r_",
            "5k_resistor",
            "100k_resistor",
            "revc_",
            "corner_cf",
            "cm100r",
            "cm5k_cf10",
            "cm100k",
            "c100_",
            "c100k_coil_",
        ]
        .iter()
        .any(|prefix| n.starts_with(prefix));
        if !positive {
            continue;
        }
        let base = n.trim_end_matches(".cir");
        let log = fs::read_to_string(format!("{base}.log")).unwrap();
        assert!(
            !log.contains("Error") && !log.contains("aborted"),
            "{base} log failure"
        );
        let guard = Command::new("./op_guard")
            .arg(format!("{base}_op.raw"))
            .output()
            .unwrap();
        assert!(
            guard.status.success(),
            "{base}: {}",
            String::from_utf8_lossy(&guard.stderr)
        );
        let deck = fs::read_to_string(&p).unwrap();
        let tran = deck
            .lines()
            .find(|s| s.starts_with("tran "))
            .unwrap()
            .split_whitespace()
            .nth(2)
            .unwrap();
        let stop: f64 = tran.trim_end_matches('u').parse::<f64>().unwrap() * 1e-6;
        let text = fs::read_to_string(format!("{base}_tran.dat")).unwrap();
        let mut rows = 0;
        let mut end = 0.;
        for line in text.lines().skip(1).filter(|s| !s.trim().is_empty()) {
            let values: Vec<f64> = line
                .split_whitespace()
                .map(|s| s.parse().unwrap())
                .collect();
            assert!(values.iter().all(|x| x.is_finite()));
            end = values[0];
            rows += 1;
        }
        assert!(rows > 8000);
        assert!((end - stop).abs() < 1e-12);
        count += 1;
    }
    assert_eq!(count, 80, "expected6B+6C+54corners+3CM+10extended+1longtail");
    println!("{count} positive full-OP/transient cases checked.");
}
