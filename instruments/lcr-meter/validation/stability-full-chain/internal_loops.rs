//! Independent ideal controlled-GM input cuts. Derived probe copies alter only a
//! zero-current control input; all physical input/output loading remains intact.
#[path = "return_ratio_oracle.rs"]
mod oracle;
#[path = "../solver-resolution-rev-c-final/strict_order.rs"]
mod strict_order;
use std::{fs, process::Command};
fn data(path: &str) -> Vec<Vec<f64>> {
    fs::read_to_string(path)
        .unwrap()
        .lines()
        .skip(1)
        .map(|l| {
            l.split_whitespace()
                .map(|s| {
                    let v: f64 = s.parse().unwrap();
                    assert!(v.is_finite());
                    v
                })
                .collect()
        })
        .collect()
}
fn main() {
    let fixed = std::env::args().any(|v| v == "--fixed-local");
    let reuse = std::env::args().any(|v| v == "--analyze-only");
    for (file, model, old) in [
        (
            "opa2810_a.lib",
            "OPA2810",
            "X_AOL_1_OPA2810         N31014 N11991 MID AOLNET AOL_1_OPA2810",
        ),
        (
            "opa810_a.lib",
            "OPA810",
            "X_AOL_1         N31014 N11991 MID AOLNET AOL_1_OPA810",
        ),
    ] {
        let text = fs::read_to_string(format!("../../sources/ti/models/{file}")).unwrap();
        let start = format!(".subckt {model} ");
        let end = format!(".ENDS  {model}");
        let text = &text[text.find(&start).unwrap()..text.find(&end).unwrap() + end.len()];
        assert_eq!(text.matches(old).count(), 1);
        let probe = text
            .replace(
                &format!(".subckt {model} IN+"),
                &format!(".subckt {model}_PROBE IN+"),
            )
            .replace(
                old,
                &format!(
                    "VLOOP N31014 NPROBE DC 0 AC 1\n{}",
                    old.replacen("N31014", "NPROBE", 1)
                ),
            )
            .replace(&end, &format!(".ENDS {model}_PROBE"));
        fs::write(format!("{model}-internal-probe.lib"), probe).unwrap();
    }
    let mut report=String::from("# Final-network ideal-GM-control cuts\n\nAll other loops closed. Zero-current controlled-source input cut preserves all physical port loading. All DC helpers and AC-coupling bias asserted. These are typical-model conditional loop results, not a proof covering arbitrary coupled nonlinear modes.\n\n| Range / loop | Unity crossings: Hz, signed angle from -1, direction | Minimum sampled return difference |\n|---|---|---|\n");
    for (tag, r, cf) in [
        ("r100", 100., 100e-12),
        ("r5k", 5000., 10e-12),
        ("r100k", 100000., 5e-12),
    ] {
        for (lp, inst, model) in [
            ("source", "X5", "OPA810"),
            ("drive", "X6A", "OPA2810"),
            ("high", "X6B", "OPA2810"),
            ("low", "X7B", "OPA2810"),
            ("tia", "X7A", "OPA2810"),
        ] {
            let name = format!(
                "{}_internal_{tag}_{lp}",
                if fixed { "fixed" } else { "final" }
            );
            let mut s = fs::read_to_string("final-template.cir")
                .unwrap()
                .replace("RG source hi 100", &format!("RG source hi {r}"))
                .replace("RF low tia 100", &format!("RF low tia {r}"))
                .replace("CDUT hi low 100n", &format!("RDUT hi low {r}"));
            let oldcf = s
                .lines()
                .find(|l| l.starts_with("CF "))
                .unwrap()
                .to_string();
            s = s.replace(&oldcf, &format!("CF low tia {cf}"));
            if fixed {
                s = s
                    .replace(
                        &format!("CF low tia {cf}"),
                        "CF low cf_local 100p\nLlocal cf_local tia 5n",
                    )
                    .replace(
                        &format!("RF low tia {r}"),
                        &format!("RF low rf_end {r}\nLfeedback rf_end tia 100n"),
                    );
            }
            let old = s
                .lines()
                .find(|l| l.starts_with(&format!("{inst} ")))
                .unwrap()
                .to_string();
            s = s.replace(&old, &old.replace(model, &format!("{model}_PROBE")));
            let x = inst.to_lowercase();
            s+=&format!(".include {model}-internal-probe.lib\n.control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\nwrdata {name}_dc.dat v(x5.mid) v(x6a.mid) v(x6b.mid) v(x7a.mid) v(x7b.mid) v(xa.mid) v(xb.mid) v(acin)\nac dec 240 1 1G\nlet t=-v({x}.n31014,{x}.n11991)/v({x}.nprobe,{x}.n11991)\nwrdata {name}_return.dat real(t) imag(t)\nquit\n.endc\n.end\n");
            let (order, s) = if reuse {
                (
                    fs::read_to_string(format!("{name}-selected-order.txt"))
                        .unwrap()
                        .trim()
                        .parse::<u64>()
                        .unwrap(),
                    String::new(),
                )
            } else {
                strict_order::find_order(&name, &s, 64).expect("strict DC")
            };
            if !reuse {
                fs::write(format!("{name}.cir"), s).unwrap();
                for suffix in ["dc", "return"] {
                    let _ = fs::remove_file(format!("{name}_{suffix}.dat"));
                }
                let o = Command::new(
                    std::env::var("NGSPICE").unwrap_or("/opt/homebrew/bin/ngspice".into()),
                )
                .args(["-b", &format!("{name}.cir")])
                .output()
                .unwrap();
                let mut log = o.stdout;
                log.extend(o.stderr);
                fs::write(format!("{name}.log"), &log).unwrap();
                let l = String::from_utf8_lossy(&log);
                assert!(
                    o.status.success()
                        && !l.contains("Error:")
                        && !l.to_lowercase().contains("aborted")
                );
            }
            let dc = data(&format!("{name}_dc.dat"));
            assert_eq!(dc.len(), 1);
            for v in &dc[0][1..6] {
                assert!(v.abs() < 1e-6);
            }
            for v in &dc[0][6..8] {
                assert!((v - 2.5).abs() < 1e-4);
            }
            assert!(dc[0][8].abs() < 1e-5);
            let p: Vec<oracle::Point> = data(&format!("{name}_return.dat"))
                .iter()
                .map(|v| oracle::Point {
                    hz: v[0],
                    t: oracle::Complex::new(v[1], v[2]),
                })
                .collect();
            assert_eq!(p.len(), 2161);
            let crossings = oracle::crossings(&p).unwrap();
            let min = p
                .iter()
                .map(|p| (p.t + oracle::Complex::new(1., 0.)).abs())
                .fold(f64::INFINITY, f64::min);
            let row = format!(
                "| {name} (order {order}) | {} | {min:.8} |\n",
                crossings
                    .iter()
                    .map(|c| format!(
                        "{:.2}, {:.5}°, {:?}",
                        c.hz, c.signed_angle_from_minus_one_deg, c.direction
                    ))
                    .collect::<Vec<_>>()
                    .join("; ")
            );
            print!("{row}");
            report += &row;
            fs::write(
                if fixed {
                    "internal-loops-fixed.md"
                } else {
                    "internal-loops-final.md"
                },
                &report,
            )
            .unwrap();
        }
    }
}
