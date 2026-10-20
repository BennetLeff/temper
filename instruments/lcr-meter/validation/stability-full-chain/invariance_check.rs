#[path = "return_ratio_oracle.rs"]
mod oracle;
use std::fs;
fn rows(p: &str, sep: char) -> Vec<Vec<f64>> {
    fs::read_to_string(p)
        .unwrap()
        .lines()
        .skip(1)
        .map(|l| {
            if sep == ',' {
                l.split(',').map(|v| v.parse().unwrap()).collect()
            } else {
                l.split_whitespace().map(|v| v.parse().unwrap()).collect()
            }
        })
        .collect()
}
fn main() {
    let fixed = std::env::args().any(|a| a == "--fixed-local");
    let mut report=String::from("# Final-network bridge invariance\n\nExact declared bridge values are checked in each accepted deck. The physical DC-node comparison excludes the inserted probe node and compares the same source/follower/TIA/FDA nodes. All four bridge values must agree in near-unity return ratio and unity-crossing angles; the all-frequency numerical limit is reported below.\n\n| RF compensation | Fixture each terminal | Maximum DC-node change | Maximum normalized complex-return change (all / near-unity band) | Maximum crossing-angle change |\n|---|---|---:|---:|---:|\n");
    for cf in if fixed {
        vec!["100.0"]
    } else {
        vec!["0.0", "2.2", "4.7", "10.0"]
    } {
        for stray in ["0", "100"] {
            let base = if fixed {
                format!("final_fixed5k_stray{stray}_bridge1_caplead5_local100_lead100_tia")
            } else {
                format!("final_5k_cf{cf}_stray{stray}_bridge1_tia")
            };
            let reference = rows(&format!("{base}_return.csv"), ',');
            let dc0 = rows(&format!("{base}_dc.dat"), ' ');
            let p0: Vec<_> = reference
                .iter()
                .map(|v| oracle::Point {
                    hz: v[0],
                    t: oracle::Complex::new(v[1], v[2]),
                })
                .collect();
            let c0 = oracle::crossings(&p0).unwrap();
            let (mut dd, mut dt, mut da, mut dband, mut worstf, mut worstgain) =
                (0f64, 0f64, 0f64, 0f64, 0f64, 0f64);
            for bridge in [1, 10, 100, 1000] {
                let name = if fixed {
                    format!(
                        "final_fixed5k_stray{stray}_bridge{bridge}_caplead5_local100_lead100_tia"
                    )
                } else {
                    format!("final_5k_cf{cf}_stray{stray}_bridge{bridge}_tia")
                };
                let deck = fs::read_to_string(format!("{name}.cir")).unwrap();
                assert_eq!(
                    deck.lines()
                        .filter(|l| *l == format!("Rbridge low probe_f {bridge}"))
                        .count(),
                    1
                );
                let a = rows(&format!("{name}_return.csv"), ',');
                assert_eq!(a.len(), reference.len());
                let dc = rows(&format!("{name}_dc.dat"), ' ');
                for (i, v) in dc[0].iter().enumerate().skip(1) {
                    dd = dd.max((v - dc0[0][i]).abs());
                }
                let p: Vec<_> = a
                    .iter()
                    .zip(&reference)
                    .map(|(v, r)| {
                        assert_eq!(v[0], r[0]);
                        let t = oracle::Complex::new(v[1], v[2]);
                        let tr = oracle::Complex::new(r[1], r[2]);
                        let err = (t - tr).abs() / (1. + tr.abs());
                        if err > dt {
                            dt = err;
                            worstf = v[0];
                            worstgain = tr.abs();
                        }
                        if tr.abs() > 0.01 && tr.abs() < 100. {
                            dband = dband.max(err);
                        }
                        oracle::Point { hz: v[0], t }
                    })
                    .collect();
                let cs = oracle::crossings(&p).unwrap();
                assert_eq!(cs.len(), c0.len());
                for (c, b) in cs.iter().zip(&c0) {
                    assert_eq!(c.direction, b.direction);
                    da = da.max(
                        (c.signed_angle_from_minus_one_deg - b.signed_angle_from_minus_one_deg)
                            .abs(),
                    );
                }
            }
            assert!(
                dd < 1e-6 && dband < 1e-4 && da < 0.01,
                "bridge invariance failed: {dd} {dt} {dband} {da}"
            );
            eprintln!("cf{cf}/stray{stray}: maximum error{dt} at{worstf}Hz gain{worstgain}");
            report += &format!(
                "| {cf} pF | {stray} pF | {dd:.5e} V | {dt:.5e} / {dband:.5e} | {da:.7}° |\n"
            );
        }
    }
    report+="\nAt very high low-frequency loop gain, finite-precision cancellation in de-embedding a small bridge gives percent-level complex-return variation. The table reports that limitation rather than calling the whole curve invariant. The near-unity band is0.01<|T|<100; its error and every crossing angle are checked separately. Together with independent ideal-GM cuts, this supports the reported margins; it is not an all-frequency Nyquist proof.\n";
    fs::write(
        if fixed {
            "bridge-invariance-fixed.md"
        } else {
            "bridge-invariance-final.md"
        },
        &report,
    )
    .unwrap();
    print!("{report}");
}
