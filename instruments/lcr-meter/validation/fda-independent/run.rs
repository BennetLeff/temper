//! Independent internal controlled-source loop cut; vendor source libraries remain intact.
use std::{fs, process::Command};

fn verify_legacy_extraction() {
    let archive = Command::new("unzip")
        .args([
            "-p",
            "../../sources/ti/SBOC476.zip",
            "TINA-TI_Open Loop No Load response Figure99_THS4551.TSC",
        ])
        .output()
        .unwrap();
    assert!(archive.status.success());
    let data = archive.stdout;
    let start = data
        .windows(b"* THS4551".len())
        .position(|w| w == b"* THS4551")
        .expect("embedded model start");
    let mut offset = start - 1;
    let mut extracted = String::new();
    // TINA length-prefixed ASCII records: N-1 text bytes, then five zero bytes.
    for _ in 0..978 {
        let n = data[offset] as usize;
        assert!(n > 0);
        assert_eq!(&data[offset + n..offset + n + 5], &[0; 5]);
        extracted.push_str(std::str::from_utf8(&data[offset + 1..offset + n]).unwrap());
        extracted.push('\n');
        offset += n + 5;
    }
    assert_eq!(
        extracted,
        fs::read_to_string("ths4551-legacy-extracted.lib").unwrap(),
        "extracted model differs from archived primary source"
    );
}

fn instrument(model: &str) -> String {
    if model == "gwl" {
        let source = fs::read_to_string("../../sources/ti/models/ths4551.lib").unwrap();
        let needle = "X_AOL_1_THS4551         INP INN MID AOLNET AOL_1_THS4551";
        assert_eq!(source.matches(needle).count(), 1);
        source.replace(needle, "Vloop INP INP_PROBE DC 0 AC 1\nX_AOL_1_THS4551         INP_PROBE INN MID AOLNET AOL_1_THS4551")
    } else {
        let source = fs::read_to_string("ths4551-legacy-extracted.lib").unwrap();
        let needle = "XI43 VINP_INT VINM_INT NET32 NET31 VEE_INT VCC_INT POWER GmItail";
        assert_eq!(source.matches(needle).count(), 1);
        source.replace(needle, "Vloop VINP_INT VINP_INT_PROBE DC 0 AC 1\nXI43 VINP_INT_PROBE VINM_INT NET32 NET31 VEE_INT VCC_INT POWER GmItail")
    }
}

fn margins(path: &str) -> (Vec<(f64, f64)>, f64) {
    let data = fs::read_to_string(path).unwrap();
    let mut prior: Option<(f64, f64, f64)> = None;
    let mut crossings = Vec::new();
    let mut distance = f64::INFINITY;
    let mut count = 0;
    for line in data.lines().skip(1) {
        let r: Vec<f64> = line
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        assert_eq!(r.len(), 3);
        assert!(r.iter().all(|v| v.is_finite()));
        let (f, re, im) = (r[0], r[1], r[2]);
        let db = 20. * re.hypot(im).log10();
        let mut phase = im.atan2(re).to_degrees();
        if let Some((pf, pd, pp)) = prior {
            while phase - pp > 180. {
                phase -= 360.;
            }
            while phase - pp < -180. {
                phase += 360.;
            }
            if (db >= 0.) != (pd >= 0.) {
                assert!(db < pd, "unexpected upward crossing; inspect full Nyquist");
                let k = pd / (pd - db);
                crossings.push((
                    (pf.ln() + k * (f / pf).ln()).exp(),
                    180. + pp + k * (phase - pp),
                ));
            }
        }
        distance = distance.min((1. + re).hypot(im));
        prior = Some((f, db, phase));
        count += 1;
    }
    assert_eq!(count, 1081);
    assert_eq!(crossings.len(), 1);
    (crossings, distance)
}

fn main() {
    verify_legacy_extraction();
    fs::create_dir_all("cases").unwrap();
    fs::copy(".spiceinit", "cases/.spiceinit").unwrap();
    let mut report =
        String::from("model,case,inside_ohm,rail_v,crossing_hz,margin_deg,min_return_difference\n");
    for model in ["gwl", "legacy"] {
        fs::write(format!("{model}-probe.lib"), instrument(model)).unwrap();
        let mut minimum = f64::INFINITY;
        for case in -3_i32..64 {
            let sign = |bit: u32| {
                if case >= 0 && (case & (1 << bit)) != 0 {
                    1.
                } else if case >= 0 {
                    -1.
                } else {
                    0.
                }
            };
            let inside = if case == -3 {
                3.3
            } else if case == -2 {
                10.
            } else {
                22.
            } * (1. + 0.01 * sign(0));
            let outside = if case == -3 { 4.02 } else { 4.32 } * (1. + 0.01 * sign(1));
            let rg = 1000. * (1. + 0.001 * sign(2));
            let rf = 1000. * (1. - 0.001 * sign(2));
            let cf = if case == -3 { 0. } else { 100e-12 } * (1. + 0.05 * sign(3));
            let cl = 1. + 0.05 * sign(4);
            let rail = 5. * (1. + 0.05 * sign(5));
            let tag = format!(
                "{model}-{}",
                if case == -3 {
                    "original".into()
                } else if case == -2 {
                    "evm10".into()
                } else if case == -1 {
                    "selected22".into()
                } else {
                    format!("corner{case:02}")
                }
            );
            let (instance, returned, forward, mid) = if model == "gwl" {
                (
                    "X1 ip im op om cm vp 0 THS4551",
                    "v(x1.inp)-v(x1.inn)",
                    "v(x1.inp_probe)-v(x1.inn)",
                    "print v(x1.mid)\n",
                )
            } else {
                (
                    "X1 om op cm im ip 0 vp vp THS4551",
                    "v(x1.xi0.xi0.vinp_int)-v(x1.xi0.xi0.vinm_int)",
                    "v(x1.xi0.xi0.vinp_int_probe)-v(x1.xi0.xi0.vinm_int)",
                    "",
                )
            };
            let (loadp, loadm) = if case == -3 {
                ("op", "om")
            } else {
                ("fbp", "fbm")
            };
            let deck = format!("Independent FDA internal control cut; {tag}\n.include ../{model}-probe.lib\n.options reltol=1e-5 abstol=1e-12 vntol=1e-7\nV5 vp 0 {rail}\nVcm cm 0 2.048\nVin inp 0 0\nRin1 inp ip {rg}\nRin2 0 im {rg}\nRout1 om fbm {inside}\nRout2 op fbp {inside}\nRfb1 fbm ip {rf}\nRfb2 fbp im {rf}\nCfb1 fbm ip {cf}\nCfb2 fbp im {cf}\n{instance}\nRiso1 {loadp} ap {outside}\nRiso2 {loadm} am {outside}\nCflt1 ap 0 {}\nCflt2 am 0 {}\nCdiff ap am {}\nCadc1 ap 0 16p\nCadc2 am 0 16p\n.control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\nprint v(op) v(om)\n{mid}ac dec 120 1 1G\nlet returned={returned}\nlet forward={forward}\nlet loop=-returned/forward\nwrdata {tag}.dat real(loop) imag(loop)\nquit\n.endc\n.end\n",330e-12*cl,330e-12*cl,3.3e-9*cl);
            fs::write(format!("cases/{tag}.cir"), deck).unwrap();
            let data_path = format!("cases/{tag}.dat");
            if fs::exists(&data_path).unwrap() {
                fs::remove_file(&data_path).unwrap();
            }
            let out = Command::new(std::env::var("NGSPICE").unwrap_or("ngspice".into()))
                .current_dir("cases")
                .args(["-b", &format!("{tag}.cir")])
                .output()
                .unwrap();
            let log = format!(
                "{}{}",
                String::from_utf8_lossy(&out.stdout),
                String::from_utf8_lossy(&out.stderr)
            );
            fs::write(format!("cases/{tag}.log"), &log).unwrap();
            assert!(
                out.status.success()
                    && !log.contains("Error:")
                    && !log.to_lowercase().contains("transient op")
                    && !log.to_lowercase().contains("aborted"),
                "invalid OP {tag}"
            );
            let value = |name: &str| -> f64 {
                log.lines()
                    .find_map(|l| {
                        l.strip_prefix(name)
                            .and_then(|v| v.trim().strip_prefix('='))
                            .and_then(|v| v.trim().parse().ok())
                    })
                    .expect("missing OP")
            };
            assert!((value("v(op)") - 2.048).abs() < 0.02 && (value("v(om)") - 2.048).abs() < 0.02);
            if model == "gwl" {
                assert!((value("v(x1.mid)") - rail / 2.).abs() < 5e-5);
            }
            let (crossings, distance) = margins(&format!("cases/{tag}.dat"));
            let (hz, margin) = crossings[0];
            if case >= -1 {
                assert!(margin > 45., "insufficient margin {tag}: {margin}");
                minimum = minimum.min(margin);
            }
            report += &format!("{model},{tag},{inside},{rail},{hz:.9},{margin:.9},{distance:.9}\n");
        }
        println!(
            "{model}: selected 22-ohm minimum margin across nominal + 64 corners: {minimum:.6} deg"
        );
    }
    fs::write("results.csv", report).unwrap();
}
