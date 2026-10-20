#[path = "return_ratio_oracle.rs"]
mod oracle;
use std::fs;
fn main() {
    let fixed = std::env::args().any(|v| v == "--fixed-local");
    let mut out=String::from("# Final TIA sweep summary\n\nAll crossing angles use the principal signed separation from -1. Only descending crossings are summarized below; complete multiple-crossing records remain in the matrix files. These sampled values do not establish open-loop RHP-pole count.\n\n| Sweep | Range | Cases | Minimum descending angle | Minimum sampled return difference | Maximum adjacent return-difference angle | 45° criterion |\n|---|---|---:|---:|---:|---:|---|\n");
    for (sweep, expected) in if fixed {
        vec![("fixedgrid", 14), ("fixedcorners", 28), ("fixedlead", 16)]
    } else {
        vec![
            ("grid", 14),
            ("corners", 28),
            ("lead20", 14),
            ("lead50", 14),
        ]
    } {
        for range in ["r100_", "r5k_", "r100k_"] {
            let mut count = 0;
            let mut minangle = f64::INFINITY;
            let mut mindiff = f64::INFINITY;
            let mut maxstep: f64 = 0.;
            let mut worst = String::new();
            for entry in fs::read_dir(".").unwrap() {
                let p = entry.unwrap().path();
                let name = p.file_name().unwrap().to_str().unwrap();
                let prefix = if fixed {
                    if sweep == "fixedlead" {
                        "final_fixedlead"
                    } else {
                        "final_fixed"
                    }
                } else {
                    "final_rev_c"
                };
                if !name.starts_with(&format!("{prefix}_{range}"))
                    || !name.ends_with("_tia_return.csv")
                {
                    continue;
                }
                let select = match sweep {
                    "fixedgrid" => name.contains("_corner0_"),
                    "fixedcorners" => !name.contains("_corner0_"),
                    "fixedlead" => true,
                    "grid" => name.contains("_corner0_") && !name.contains("_lead"),
                    "corners" => !name.contains("_corner0_") && !name.contains("_lead"),
                    "lead20" => name.contains("_lead20_"),
                    _ => name.contains("_lead50_"),
                };
                if !select {
                    continue;
                }
                count += 1;
                let text = fs::read_to_string(&p).unwrap();
                let pts: Vec<oracle::Point> = text
                    .lines()
                    .skip(1)
                    .map(|l| {
                        let v: Vec<f64> = l.split(',').map(|v| v.parse().unwrap()).collect();
                        oracle::Point {
                            hz: v[0],
                            t: oracle::Complex::new(v[1], v[2]),
                        }
                    })
                    .collect();
                for c in oracle::crossings(&pts).unwrap() {
                    if c.direction == oracle::Direction::Down
                        && c.signed_angle_from_minus_one_deg < minangle
                    {
                        minangle = c.signed_angle_from_minus_one_deg;
                        worst = name.to_string();
                    }
                }
                for p in &pts {
                    mindiff = mindiff.min((p.t + oracle::Complex::new(1., 0.)).abs());
                }
                for w in pts.windows(2) {
                    let a = w[0].t + oracle::Complex::new(1., 0.);
                    let b = w[1].t + oracle::Complex::new(1., 0.);
                    maxstep = maxstep.max((b / a).arg().to_degrees().abs());
                }
            }
            assert_eq!(count, expected, "incomplete {sweep}/{range}");
            if sweep == "lead50" && range == "r100_" {
                assert!(minangle < 45., "negative control no longer fails");
            } else {
                assert!(
                    minangle >= 45.,
                    "margin below criterion {worst}: {minangle}"
                );
            }
            eprintln!("{sweep}/{range}: max step {maxstep}");
            assert!(
                maxstep < 30.,
                "undersampled return trajectory {}/{}, {}",
                sweep,
                range,
                maxstep
            );
            out += &format!(
                "| {sweep} | {} | {count} | {minangle:.5}° | {mindiff:.8} | {maxstep:.5}° | {} |\n",
                range.trim_end_matches('_'),
                if minangle >= 45. {
                    "PASS within stated model"
                } else {
                    "FAIL: rejected layout envelope"
                }
            );
            eprintln!("Worst descending case: {worst}");
        }
    }
    fs::write(
        if fixed {
            "fixed-summary.md"
        } else {
            "final-summary.md"
        },
        &out,
    )
    .unwrap();
    print!("{out}");
}
