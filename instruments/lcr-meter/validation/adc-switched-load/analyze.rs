//! Executable simulation assertions; expected failures abort this verification harness.
use std::fs;
fn main() {
    for tag in ["operating", "stress"] {
        let log = fs::read_to_string(format!("{tag}.log")).unwrap();
        assert!(
            !log.contains("Error:")
                && !log.to_ascii_lowercase().contains("transient op")
                && !log.to_ascii_lowercase().contains("aborted"),
            "invalid operating-point fallback"
        );
        for prefix in [
            "reference",
            "center",
            "positive",
            "negative",
            "lowcm",
            "highcm",
        ] {
            let key = format!("x{prefix}.mid");
            let mid: f64 = log
                .lines()
                .find_map(|line| {
                    let mut cells = line.split_whitespace();
                    if cells.next() == Some(key.as_str()) {
                        cells.next().and_then(|v| v.parse().ok())
                    } else {
                        None
                    }
                })
                .expect("missing model MID validation");
            assert!((mid - 2.5).abs() < 5e-5, "incorrect internal model bias");
        }
        let text = fs::read_to_string(format!("{tag}.dat")).unwrap();
        let rows: Vec<Vec<f64>> = text
            .lines()
            .skip(1)
            .map(|line| {
                line.split_whitespace()
                    .map(|v| v.parse::<f64>().unwrap())
                    .collect()
            })
            .collect();
        assert!(rows
            .iter()
            .all(|r| r.len() == 25 && r.iter().all(|v| v.is_finite())));
        assert!(rows.len() > 10000 && (rows.last().unwrap()[0] - 15e-6).abs() < 1e-15);
        let mut differential = [0.0_f64; 5];
        let mut common = [0.0_f64; 5];
        let mut pin_min = f64::INFINITY;
        let mut pin_max = f64::NEG_INFINITY;
        let mut cm_min = f64::INFINITY;
        let mut cm_max = f64::NEG_INFINITY;
        for row in rows.iter().filter(|r| r[0] >= 3e-6) {
            for pins in row[13..25].chunks_exact(2) {
                pin_min = pin_min.min(pins[0]).min(pins[1]);
                pin_max = pin_max.max(pins[0]).max(pins[1]);
                let cm = (pins[0] + pins[1]) / 2.;
                cm_min = cm_min.min(cm);
                cm_max = cm_max.max(cm);
            }
        }
        assert!(
            pin_min >= 0. && pin_max <= 4.096,
            "instantaneous ADC pin range"
        );
        assert!(
            cm_min >= 1.848 && cm_max <= 2.248,
            "instantaneous ADC pin common mode"
        );
        for n in 4..=14 {
            let target = n as f64 * 1e-6 - 0.5e-9;
            let row = rows.iter().filter(|r| r[0] <= target).last().unwrap();
            assert!(target - row[0] < 1e-9 && row[1] > 0.9);
            for i in 0..5 {
                differential[i] = differential[i].max(row[i + 3].abs());
                common[i] = common[i].max(row[i + 8].abs());
            }
        }
        if tag == "operating" {
            assert!(
                differential.iter().all(|v| *v < 62.5e-6),
                "operating-window acquisition recovery exceeds half an ADC LSB"
            );
            assert!(
                common.iter().all(|v| *v < 0.2),
                "sample common mode outside the ADC's specified window"
            );
        } else {
            assert!(
                differential.iter().any(|v| *v > 62.5e-6),
                "short-window negative control unexpectedly passed; check switched load"
            );
        }
        println!("{tag}: max differential endpoint errors V: {differential:?}; common-mode errors V: {common:?}; half-LSB=62.5uV");
        println!("{tag}: instantaneous ADC pin min/max V: {pin_min:.9}/{pin_max:.9}; pin common-mode min/max V: {cm_min:.9}/{cm_max:.9}");
    }
}
