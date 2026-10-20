mod strict_order;
use std::{
    env, fs,
    process::{Command, Stdio},
};
fn main() {
    let execute = env::args().nth(1).as_deref() == Some("--full");
    let cases = fs::read_to_string("accepted-cases.txt").expect("final accepted case manifest");
    let cases: Vec<_> = cases
        .lines()
        .filter(|l| !l.trim().is_empty() && !l.starts_with('#'))
        .collect();
    assert_eq!(cases.len(), 75, "complete expected case matrix");
    for name in cases {
        let deck = fs::read_to_string(format!("{name}.cir")).unwrap();
        let outputs: Vec<_> = deck
            .lines()
            .filter_map(|l| {
                let p: Vec<_> = l.split_whitespace().collect();
                if p.first() == Some(&"write") || p.first() == Some(&"wrdata") {
                    Some(p[1].to_string())
                } else {
                    None
                }
            })
            .collect();
        assert!(!outputs.is_empty());
        if execute {
            for p in &outputs {
                let _ = fs::remove_file(p);
            }
            let log = fs::File::create(format!("{name}.log")).unwrap();
            let status =
                Command::new(env::var("NGSPICE").unwrap_or("/opt/homebrew/bin/ngspice".into()))
                    .args(["-b", &format!("{name}.cir")])
                    .stdout(Stdio::from(log.try_clone().unwrap()))
                    .stderr(Stdio::from(log))
                    .status()
                    .unwrap();
            assert!(status.success(), "{name}: process failed");
        }
        let log = fs::read_to_string(format!("{name}.log")).unwrap();
        assert!(
            !log.contains("Error") && !log.contains("aborted"),
            "{name}: analysis error"
        );
        for output in outputs {
            if output.ends_with(".raw") {
                strict_order::true_op(&output).unwrap_or_else(|e| panic!("{name}: {e}"));
            } else {
                let t = fs::read_to_string(&output).unwrap();
                let mut count = 0;
                for l in t.lines().skip(1) {
                    let row: Vec<f64> = l.split_whitespace().map(|x| x.parse().unwrap()).collect();
                    assert!(row.iter().all(|x| x.is_finite()), "{output}: nonfinite");
                    if !row.is_empty() {
                        count += 1
                    }
                }
                assert!(count > 0, "{output}: empty output");
            }
        }
        println!("PASS {name}");
    }
    for validator in [
        "verify_final",
        "summarize_corners",
        "before_after_stats",
        "verify_extended",
    ] {
        assert!(
            Command::new(format!("./{validator}"))
                .status()
                .unwrap()
                .success(),
            "{validator} failed"
        );
    }
}
