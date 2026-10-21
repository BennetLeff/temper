//! Tian bilateral return ratio from a two-current-injection admittance matrix.
//! Test bridge is de-embedded mathematically; resistor connected node guesses
//! initialize unmodified TI macromodels without forcing any final node voltage.
#[path = "return_ratio_oracle.rs"]
mod oracle;
#[path = "../solver-resolution-rev-c-final/strict_order.rs"]
mod strict_order;
use std::{
    fs,
    ops::{Add, Div, Mul, Sub},
    process::Command,
};
#[derive(Clone, Copy, Debug)]
struct C {
    r: f64,
    i: f64,
}
impl C {
    fn n(r: f64, i: f64) -> Self {
        Self { r, i }
    }
    fn abs(self) -> f64 {
        self.r.hypot(self.i)
    }
    fn phase(self) -> f64 {
        self.i.atan2(self.r)
    }
}
impl Add for C {
    type Output = Self;
    fn add(self, b: Self) -> Self {
        Self::n(self.r + b.r, self.i + b.i)
    }
}
impl Sub for C {
    type Output = Self;
    fn sub(self, b: Self) -> Self {
        Self::n(self.r - b.r, self.i - b.i)
    }
}
impl Mul for C {
    type Output = Self;
    fn mul(self, b: Self) -> Self {
        Self::n(self.r * b.r - self.i * b.i, self.r * b.i + self.i * b.r)
    }
}
impl Div for C {
    type Output = Self;
    fn div(self, b: Self) -> Self {
        let q = b.r * b.r + b.i * b.i;
        Self::n(
            (self.r * b.r + self.i * b.i) / q,
            (self.i * b.r - self.r * b.i) / q,
        )
    }
}
#[derive(Clone)]
struct Case {
    name: String,
    r: f64,
    cf: f64,
    dut: String,
    stray: f64,
    rail: f64,
    five: f64,
    rtol: f64,
    bridge: f64,
    riso: f64,
}
/// Rev E decks: TAC5112 codec front end (codec-template.cir) instead of the FDA/ADS9224R chain.
fn codec(name: &str) -> bool {
    name.contains("codec_") || name.contains("relay_")
}
fn circuit(c: &Case, lp: &str) -> (String, f64) {
    let final_design = c.name.starts_with("final_");
    let mut s = fs::read_to_string(if codec(&c.name) {
        "codec-template.cir"
    } else if final_design {
        "final-template.cir"
    } else {
        "base-template.cir"
    })
    .unwrap();
    if let Some(values) = c.name.strip_prefix("fda_ng_") {
        let values: Vec<f64> = values.split('_').map(|v| v.parse().unwrap()).collect();
        for p in ["a", "b"] {
            s += &format!(
                "Rng{p} {p}ip {p}ng {}\nCng{p} {p}ng {p}im {}\n",
                values[0],
                values[1] * 1e-12
            );
        }
    }
    if let Some(values) = c.name.strip_prefix("fda_filter_") {
        let cap: f64 = values.split('_').next().unwrap().parse().unwrap();
        s = s.replace(" 3.3n\n", &format!(" {}\n", cap * 1e-12));
    }
    if let Some(value) = c.name.strip_prefix("fda_cf_") {
        let cap: f64 = value.parse().unwrap();
        for p in ["a", "b"] {
            s += &format!(
                "Cfb{p}1 {p}fbm {p}ip {}\nCfb{p}2 {p}fbp {p}im {}\n",
                cap * 1e-12,
                cap * 1e-12
            );
        }
    }
    if let Some(value) = c.name.strip_prefix("fda_evm_") {
        let cap: f64 = value.parse().unwrap();
        for p in ["a", "b"] {
            s = s.replace(
                &format!("R{p}int1 {p}om {p}fbm 3.3"),
                &format!("R{p}int1 {p}om {p}fbm 10"),
            );
            s = s.replace(
                &format!("R{p}int2 {p}op {p}fbp 3.3"),
                &format!("R{p}int2 {p}op {p}fbp 10"),
            );
            s = s.replace(&format!("R{p}iso1 {p}op"), &format!("R{p}iso1 {p}fbp"));
            s = s.replace(&format!("R{p}iso2 {p}om"), &format!("R{p}iso2 {p}fbm"));
            s += &format!(
                "Cfb{p}1 {p}fbm {p}ip {}\nCfb{p}2 {p}fbp {p}im {}\n",
                cap * 1e-12,
                cap * 1e-12
            );
        }
    }
    s = s
        .replace(
            "RG source hi 100",
            &format!("RG source hi {}", c.r * (1. + c.rtol)),
        )
        .replace(
            "RF low tia 100",
            &format!("RF low tia {}", c.r * (1. - c.rtol)),
        )
        .replace("CDUT hi low 100n", &c.dut);
    // `_srciso{R}` (reverelay drive-loop fix candidate): R ohm between the source-driver output
    // (X6A, whose feedback stays at its own pin) and the SOURCE_BUF bus (srcbus: RG, relay
    // contacts, board copper). Board elements on `srcdrv` (Rev E R104 board: net SRC_DRV, driver
    // side of R104) land on the X6A node.
    if let Some((_, value)) = c.name.split_once("_srciso") {
        let r: f64 = value.split('_').next().unwrap().parse().unwrap();
        s = s
            .lines()
            .map(|l| {
                if l.starts_with("X6A ") || l.starts_with('.') || l.starts_with('*') {
                    l.to_string()
                } else {
                    l.split(' ').map(|t| match t { "source" => "srcbus", "srcdrv" => "source", _ => t }).collect::<Vec<_>>().join(" ")
                }
            })
            .collect::<Vec<_>>()
            .join("\n")
            + "\n";
        s += &format!("Rsrciso source srcbus {r}\n");
    }
    s = s.replace(" 4.02\n", &format!(" {}\n", c.riso));
    let oldcf = s
        .lines()
        .find(|l| l.starts_with("CF "))
        .unwrap()
        .to_string();
    s = s.replace(&oldcf, &format!("CF low tia {}", c.cf.max(1e-24)));
    s = s
        .replace("Vp vp 0 12", &format!("Vp vp 0 {}", c.rail))
        .replace("Vn vn 0 -12", &format!("Vn vn 0 -{}", c.rail))
        .replace("V5 v5 0 5", &format!("V5 v5 0 {}", c.five));
    // Optional isolation resistor between the J3 LO pin (node low: DUT, LOW follower and
    // fixture capacitance) and the TIA summing node (node sum: U7A -IN, RF, CF and C104).
    let risolo = c
        .name
        .split_once("_risolo")
        .map(|(_, v)| v.split('_').next().unwrap().parse::<f64>().unwrap());
    let sum = if risolo.is_some() { "sum" } else { "low" };
    if let Some(r) = risolo {
        s = s
            .replace("X7A 0 low tia", "X7A 0 sum tia")
            .replace("RF low tia", "RF sum tia")
            .replace("CF low tia", "CF sum tia");
        s += &format!("Risolo low sum {r}\n");
    }
    s += &format!(
        "Cstraylo low 0 {}\nCstrayhi hi 0 {}\n",
        c.stray.max(1e-24),
        c.stray.max(1e-24)
    );
    let (ve, vf, bridge, second): (String, String, f64, String) = if lp.starts_with("fda_") {
        let p = if lp.starts_with("fda_a") { "a" } else { "b" };
        let cm = lp.ends_with("_cm");
        s = s.replace(
            &format!("X{p} {p}ip {p}im {p}op {p}om cm v5 0 THS4551"),
            &format!("X{p} probe_fp probe_fm {p}op {p}om cm v5 0 THS4551"),
        );
        s+=&format!("Rbridgep {p}ip probe_fp {}\nRbridgem {p}im probe_fm {}\n.nodeset v(probe_fp)=1.0228 v(probe_fm)=1.0228\n",c.bridge,c.bridge);
        if cm {
            s+=&format!("Iinj 0 {p}ip DC 0 AC 0.5\nIinjm 0 {p}im DC 0 AC 0.5\nIinj2 0 probe_fp DC 0 AC 0\nIinj2m 0 probe_fm DC 0 AC 0\n");
            (
                format!("(v({p}ip)+v({p}im))/2"),
                "(v(probe_fp)+v(probe_fm))/2".into(),
                c.bridge / 2.,
                "alter Iinj ac=0\nalter Iinjm ac=0\nalter Iinj2 ac=0.5\nalter Iinj2m ac=0.5\n"
                    .into(),
            )
        } else {
            s+=&format!("Iinj 0 {p}ip DC 0 AC 1\nIinjm {p}im 0 DC 0 AC 1\nIinj2 0 probe_fp DC 0 AC 0\nIinj2m probe_fm 0 DC 0 AC 0\n");
            (
                format!("v({p}ip)-v({p}im)"),
                "v(probe_fp)-v(probe_fm)".into(),
                c.bridge * 2.,
                "alter Iinj ac=0\nalter Iinjm ac=0\nalter Iinj2 ac=1\nalter Iinj2m ac=1\n".into(),
            )
        }
    } else {
        let (inst, positive, negative, out, model, guess) = match lp {
            "source" => ("X5", "acin", "srcfb", "excite", "OPA810", 0.00007590665),
            "drive" => ("X6A", "excite", "source", "source", "OPA2810", 0.000554524),
            "high" => ("X6B", "hi", "highbuf", "highbuf", "OPA2810", 0.000654719),
            "low" => ("X7B", "low", "lowbuf", "lowbuf", "OPA2810", 0.000201502),
            "tia" => ("X7A", "0", sum, "tia", "OPA2810", 0.000100193),
            _ => panic!("loop {lp}"),
        };
        let old = format!("{inst} {positive} {negative} {out} vp vn {model}");
        assert!(s.contains(&old));
        s = s.replace(
            &old,
            &if ["drive", "high", "low"].contains(&lp) {
                format!("{inst} {positive} {negative} probe_f vp vn {model}")
            } else {
                format!("{inst} {positive} probe_f {out} vp vn {model}")
            },
        );
        s+=&format!("Rbridge {negative} probe_f {}\nIinj 0 {negative} DC 0 AC 1\nIinj2 0 probe_f DC 0 AC 0\n.nodeset v(probe_f)={guess}\n",c.bridge);
        (
            format!("v({negative})"),
            "v(probe_f)".into(),
            c.bridge,
            "alter Iinj ac=0\nalter Iinj2 ac=1\n".into(),
        )
    };
    if let Some((_, value)) = c.name.split_once("_local") {
        let cl: f64 = value.split('_').next().unwrap().parse().unwrap();
        s += &format!("Clocal {sum} tia {}\n", cl * 1e-12);
    }
    if let Some((_, value)) = c.name.split_once("_caplead") {
        let l: f64 = value.split('_').next().unwrap().parse().unwrap();
        s = s.replace(&format!("Clocal {sum} tia "), &format!("Clocal {sum} local_cf_out "));
        s += &format!("Llocal local_cf_out tia {}\n", l * 1e-9);
    }
    if let Some((_, value)) = c.name.split_once("_series") {
        let rs: f64 = value.split('_').next().unwrap().parse().unwrap();
        s = s
            .replace("RF low tia ", "RF low series_mid ")
            .replace("CF low tia ", "CF low series_mid ");
        s += &format!("Rseries series_mid tia {rs}\n");
    }
    if let Some((_, value)) = c.name.split_once("_damp") {
        let rc: f64 = value.split('_').next().unwrap().parse().unwrap();
        s = s.replace("CF low tia ", "CF low cf_series ");
        s += &format!("Rcf cf_series tia {rc}\n");
    }
    if let Some((_, value)) = c.name.rsplit_once("_lead") {
        let l: f64 = value.parse().unwrap();
        s = s
            .replace(&format!("RF {sum} tia "), &format!("RF {sum} rf_end "))
            .replace(&format!("CF {sum} tia "), &format!("CF {sum} rf_end "))
            .replace("Rcf cf_series tia ", "Rcf cf_series rf_end ")
            .replace("Rseries series_mid tia ", "Rseries series_mid rf_end ");
        s += &format!("Lfeedback rf_end tia {}\n", l * 1e-9);
    }
    // Rev E: isolation resistor between the TIA output pin (tia: C104, codec channel B tap, Rev D
    // board copper) and the relay common bus (tbus: relay pads, RF through the selected contact).
    if let Some((_, value)) = c.name.split_once("_rout") {
        let r: f64 = value.split('_').next().unwrap().parse().unwrap();
        s = s.replace("Lfeedback rf_end tia ", "Lfeedback rf_end tbus ");
        s += &format!("Rout tia tbus {r}\n");
    }
    let name = format!("{}_{}", c.name, lp);
    let density = if c.name.contains("fixed_r100k_coil") {
        19200
    } else if c.name.contains("coil") {
        4800
    } else {
        120
    };
    let dc = if codec(&c.name) {
        "v(x5.mid) v(x6a.mid) v(x6b.mid) v(x7a.mid) v(x7b.mid) v(excite) v(source) v(hi) v(low) v(tia) v(highbuf) v(lowbuf)"
    } else {
        "v(x5.mid) v(x6a.mid) v(x6b.mid) v(x7a.mid) v(x7b.mid) v(xa.mid) v(xb.mid) v(acin) v(source) v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aop) v(aom) v(bop) v(bom)"
    };
    s+=&format!(".control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\nwrdata {name}_dc.dat {dc}\nac dec 120 1 1G\nlet ve={ve}\nlet vf={vf}\nwrdata {name}_e.dat real(ve) imag(ve) real(vf) imag(vf)\n{second}ac dec 120 1 1G\nlet ve={ve}\nlet vf={vf}\nwrdata {name}_f.dat real(ve) imag(ve) real(vf) imag(vf)\nquit\n.endc\n.end\n");
    (
        s.replace("ac dec 120 1 1G", &format!("ac dec {density} 1 1G")),
        bridge,
    )
}
fn data(p: &str) -> Vec<Vec<f64>> {
    fs::read_to_string(p)
        .unwrap()
        .lines()
        .skip(1)
        .map(|l| {
            l.split_whitespace()
                .map(|x| {
                    let n: f64 = x.parse().unwrap();
                    assert!(n.is_finite(), "nonfinite {p}");
                    n
                })
                .collect()
        })
        .collect()
}
fn return_ratio(z11: C, z21: C, z12: C, z22: C, r: f64) -> C {
    let det = z11 * z22 - z12 * z21;
    let gd = C::n(2. / r, 0.) * det;
    (gd - z12 - z21) / (z11 + z22 - gd)
}
fn analyze(name: &str, bridge: f64, five: f64) -> String {
    let dc = data(&format!("{name}_dc.dat"));
    assert_eq!(dc.len(), 1);
    let dc = &dc[0];
    for x in &dc[1..6] {
        assert!(x.abs() < 1e-6, "OPA MID invalid {name}: {x}");
    }
    if codec(name) {
        // DC-coupled source: the difference stage rejects the DAC's 1.65 V common mode, so the
        // source, DUT and TIA sit near 0 V; the codec inputs are AC coupled.
        for x in &dc[6..13] {
            assert!(x.abs() < 0.05, "codec deck DC operating point off {name}: {x}");
        }
        return analyze_loop(name, bridge);
    }
    for x in &dc[6..8] {
        assert!((x - five / 2.).abs() < 1e-4, "FDA MID invalid {name}: {x}");
    }
    assert!(dc[8].abs() < 1e-5, "AC coupling not atDC {name}");
    for x in &dc[15..19] {
        assert!(*x > 1.9 && *x < 2.2, "FDA saturation {name}");
    }
    analyze_loop(name, bridge)
}
fn analyze_loop(name: &str, bridge: f64) -> String {
    let e = data(&format!("{name}_e.dat"));
    let f = data(&format!("{name}_f.dat"));
    assert!(e.len() >= 1081);
    assert_eq!(e.len(), f.len());
    let mut points = vec![];
    let mut prev = 0.;
    let mut first = true;
    let mut csv =
        "frequency_hz,return_real,return_imag,gain_db,unwrapped_phase_deg,return_difference_abs\n"
            .to_string();
    for (e, f) in e.iter().zip(f.iter()) {
        assert_eq!(e[0], f[0]);
        let t = return_ratio(
            C::n(e[1], e[2]),
            C::n(e[3], e[4]),
            C::n(f[1], f[2]),
            C::n(f[3], f[4]),
            bridge,
        );
        assert!(t.abs().is_finite());
        let mut phase = t.phase() * 180. / std::f64::consts::PI;
        if !first {
            while phase - prev > 180. {
                phase -= 360.;
            }
            while phase - prev < -180. {
                phase += 360.;
            }
        }
        first = false;
        prev = phase;
        let db = 20. * t.abs().log10();
        let delta = (C::n(1., 0.) + t).abs();
        points.push((e[0], db, phase, delta));
        csv += &format!(
            "{:.12e},{:.12e},{:.12e},{db:.9},{phase:.9},{delta:.12e}\n",
            e[0], t.r, t.i
        );
    }
    fs::write(format!("{name}_return.csv"), csv).unwrap();
    let mut crossings = vec![];
    for p in points.windows(2) {
        let (a, b) = (p[0], p[1]);
        if (a.1 >= 0. && b.1 < 0.) || (a.1 < 0. && b.1 >= 0.) {
            let k = a.1 / (a.1 - b.1);
            let freq = (a.0.ln() + k * (b.0 / a.0).ln()).exp();
            let phase = a.2 + k * (b.2 - a.2);
            crossings.push(format!(
                "{:.4} MHz / {:.2}° ({})",
                freq / 1e6,
                oracle::wrap180(180. + phase),
                if b.1 < a.1 { "down" } else { "up" }
            ));
        }
    }
    let min = points.iter().min_by(|a, b| a.3.total_cmp(&b.3)).unwrap();
    format!(
        "| {name} | {} | {:.5} at {:.4} MHz |\n",
        if crossings.is_empty() {
            "no unity crossing".into()
        } else {
            crossings.join("; ")
        },
        min.3,
        min.0 / 1e6
    )
}
fn main() {
    let requested = std::env::args().nth(1).unwrap_or("nominal".into());
    let reuse = std::env::args().any(|s| s == "--analyze-only");
    let final_design = requested.starts_with("final_");
    let mode = requested.strip_prefix("final_").unwrap_or(&requested);
    let mut cases = vec![];
    for (tag, r, cf) in [
        ("r100", 100., 0.),
        ("r5k", 5000., 0.),
        ("r100k", 100000., 5e-12),
    ] {
        cases.push(Case {
            name: format!("{tag}_matched"),
            r,
            cf,
            dut: format!("RDUT hi low {r}"),
            stray: 0.,
            rail: 12.,
            five: 5.,
            rtol: 0.,
            bridge: 100.,
            riso: 4.02,
        });
    }
    if mode == "comp" || mode == "invariance" {
        cases.clear();
        for cf in [0., 2.2e-12, 4.7e-12, 10e-12] {
            for stray in [0., 100e-12] {
                cases.push(Case {
                    name: format!("5k_cf{:.1}_stray{:.0}", cf * 1e12, stray * 1e12),
                    r: 5000.,
                    cf,
                    dut: "RDUT hi low 5000".into(),
                    stray,
                    rail: 12.,
                    five: 5.,
                    rtol: 0.,
                    bridge: 100.,
                    riso: 4.02,
                });
            }
        }
    }
    if mode == "invariance" {
        let base = cases.clone();
        cases.clear();
        for c in base {
            for r in [1., 10., 100., 1000.] {
                let mut c = c.clone();
                c.name += &format!("_bridge{r}");
                c.bridge = r;
                cases.push(c);
            }
        }
    }
    if mode == "grid" || mode == "corners" || mode == "lead" || mode == "leadwide" {
        cases.clear();
        for (tag, r, cf) in [
            ("r100", 100., 100e-12),
            ("r5k", 5000., 10e-12),
            ("r100k", 100000., 5e-12),
        ] {
            for (n, d) in [
                ("matched", format!("RDUT hi low {r}")),
                ("short", "RDUT hi low 0.01".into()),
                ("open", "RDUT hi low 1e12".into()),
                ("cap100n", "CDUT hi low 100n".into()),
                ("cap500n", "CDUT hi low 500n".into()),
                ("cap9u", "CDUT hi low 9u".into()),
                ("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u".into()),
            ] {
                for stray in [0., 100e-12] {
                    for corner in if mode == "corners" {
                        vec![-1., 1.]
                    } else {
                        vec![0.]
                    } {
                        cases.push(Case {
                            name: format!(
                                "rev_c_{tag}_{n}_stray{:.0}_corner{corner}",
                                stray * 1e12
                            ),
                            r,
                            cf: cf * (1. + 0.05 * corner),
                            dut: d.clone(),
                            stray,
                            rail: 12. * (1. + 0.05 * corner),
                            five: 5. * (1. + 0.05 * corner),
                            rtol: 0.001 * corner,
                            bridge: 100.,
                            riso: 4.02,
                        });
                    }
                }
            }
        }
    }
    if mode == "lead" {
        cases = cases
            .into_iter()
            .flat_map(|c| {
                [20., 50.].into_iter().map(move |l| {
                    let mut c = c.clone();
                    c.name += &format!("_lead{l}");
                    c
                })
            })
            .collect();
    }
    if mode == "leadwide" {
        cases.retain(|c| c.r > 100.);
        for c in &mut cases {
            c.name += "_lead100";
        }
    }
    if mode == "lowcomp" {
        cases.clear();
        for cf in [22e-12, 47e-12, 100e-12, 220e-12] {
            for stray in [0., 100e-12] {
                for (n, dut) in [("open", "RDUT hi low 1e12"), ("short", "RDUT hi low 0.01")] {
                    cases.push(Case {
                        name: format!("100r_cf{:.0}_stray{:.0}_{n}", cf * 1e12, stray * 1e12),
                        r: 100.,
                        cf,
                        dut: dut.into(),
                        stray,
                        rail: 12.,
                        five: 5.,
                        rtol: 0.,
                        bridge: 100.,
                        riso: 4.02,
                    });
                }
            }
        }
    }
    if mode == "fda_iso" {
        cases.clear();
        for riso in [4.02, 6.8, 10., 12., 15., 22.] {
            cases.push(Case {
                name: format!("fda_iso{riso}"),
                r: 100.,
                cf: 100e-12,
                dut: "RDUT hi low 100".into(),
                stray: 0.,
                rail: 12.,
                five: 5.,
                rtol: 0.,
                bridge: 10.,
                riso,
            });
        }
    }
    if mode == "fda_ng" || mode == "fda_invariance" {
        cases.clear();
        for (r, cap) in if mode == "fda_ng" {
            vec![
                (100., 1000.),
                (150., 1000.),
                (200., 1000.),
                (100., 2200.),
                (150., 2200.),
                (200., 2200.),
            ]
        } else {
            vec![(0., 0.)]
        } {
            for bridge in if mode == "fda_invariance" {
                vec![1., 10., 100.]
            } else {
                vec![10.]
            } {
                cases.push(Case {
                    name: if mode == "fda_ng" {
                        format!("fda_ng_{r}_{cap}_10")
                    } else {
                        format!("fda_bridge{bridge}")
                    },
                    r: 100.,
                    cf: 100e-12,
                    dut: "RDUT hi low 100".into(),
                    stray: 0.,
                    rail: 12.,
                    five: 5.,
                    rtol: 0.,
                    bridge,
                    riso: if mode == "fda_ng" { 10. } else { 4.02 },
                });
            }
        }
    }
    if mode == "fda_filter" {
        cases.clear();
        for (cap, riso) in [
            (1000., 10.),
            (470., 10.),
            (330., 10.),
            (470., 22.),
            (330., 22.),
            (1000., 22.),
            (1000., 47.),
            (470., 47.),
        ] {
            cases.push(Case {
                name: format!("fda_filter_{cap}_{riso}"),
                r: 100.,
                cf: 100e-12,
                dut: "RDUT hi low 100".into(),
                stray: 0.,
                rail: 12.,
                five: 5.,
                rtol: 0.,
                bridge: 10.,
                riso,
            });
        }
    }
    if mode == "fda_cf" {
        cases.clear();
        for cap in [5., 10., 22., 47., 100.] {
            cases.push(Case {
                name: format!("fda_cf_{cap}"),
                r: 100.,
                cf: 100e-12,
                dut: "RDUT hi low 100".into(),
                stray: 0.,
                rail: 12.,
                five: 5.,
                rtol: 0.,
                bridge: 10.,
                riso: 4.02,
            });
        }
    }
    if mode == "fda_evm" {
        cases.clear();
        for cap in [10., 22., 47., 100.] {
            cases.push(Case {
                name: format!("fda_evm_{cap}"),
                r: 100.,
                cf: 100e-12,
                dut: "RDUT hi low 100".into(),
                stray: 0.,
                rail: 12.,
                five: 5.,
                rtol: 0.,
                bridge: 10.,
                riso: 4.32,
            });
        }
    }
    if mode == "compact" {
        cases.clear();
        for (n, dut) in [
            ("open", "RDUT hi low 1e12"),
            ("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u"),
            ("matched", "RDUT hi low 100"),
            ("short", "RDUT hi low 0.01"),
        ] {
            for corner in [-1., 1.] {
                for lead in [10., 15., 20., 25.] {
                    cases.push(Case {
                        name: format!("r100_{n}_stray100_corner{corner}_lead{lead}"),
                        r: 100.,
                        cf: 100e-12 * (1. + 0.05 * corner),
                        dut: dut.into(),
                        stray: 100e-12,
                        rail: 12. * (1. + 0.05 * corner),
                        five: 5. * (1. + 0.05 * corner),
                        rtol: 0.001 * corner,
                        bridge: 100.,
                        riso: 4.32,
                    });
                }
            }
        }
    }
    if mode == "fixedinvariance" {
        cases.clear();
        for stray in [0., 100.] {
            for bridge in [1., 10., 100., 1000.] {
                cases.push(Case {
                    name: format!("fixed5k_stray{stray}_bridge{bridge}_caplead5_local100_lead100"),
                    r: 5000.,
                    cf: 0.,
                    dut: "RDUT hi low 5000".into(),
                    stray: stray * 1e-12,
                    rail: 12.,
                    five: 5.,
                    rtol: 0.,
                    bridge,
                    riso: 4.32,
                });
            }
        }
    }
    if mode == "fixedfda" || mode == "fixedlead" {
        cases.clear();
        for (range, r) in [("r100", 100.), ("r5k", 5000.), ("r100k", 100000.)] {
            let fixtures = if mode == "fixedfda" {
                vec![("matched", format!("RDUT hi low {r}"))]
            } else {
                vec![
                    ("open", "RDUT hi low 1e12".into()),
                    ("short", "RDUT hi low 0.01".into()),
                ]
            };
            for (n, dut) in fixtures {
                for stray in if mode == "fixedfda" {
                    vec![0.]
                } else {
                    vec![0., 100.]
                } {
                    for local in if mode == "fixedfda" {
                        vec![5.]
                    } else {
                        vec![0., 10.]
                    } {
                        for lead in if mode == "fixedfda" {
                            vec![100.]
                        } else {
                            vec![0., 100.]
                        } {
                            cases.push(Case {name:format!("fixedlead_{range}_{n}_stray{stray}_caplead{local}_local100_lead{lead}"),r,cf:0.,dut:dut.clone(),stray:stray*1e-12,rail:12.,five:5.,rtol:0.,bridge:100.,riso:4.32});
                        }
                    }
                }
            }
        }
    }
    if ["fixedgrid", "fixedcorners", "fixedrisogrid", "fixedrisocorners"].contains(&mode) {
        cases.clear();
        for (range, r) in [("r100", 100.), ("r5k", 5000.), ("r100k", 100000.)] {
            for (n, dut) in [
                ("matched", format!("RDUT hi low {r}")),
                ("short", "RDUT hi low 0.01".into()),
                ("open", "RDUT hi low 1e12".into()),
                ("cap100n", "CDUT hi low 100n".into()),
                ("cap500n", "CDUT hi low 500n".into()),
                ("cap9u", "CDUT hi low 9u".into()),
                ("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u".into()),
            ] {
                for stray in [0., 100.] {
                    let corners = if mode.ends_with("corners") {
                        vec![-1., 1.]
                    } else {
                        vec![0.]
                    };
                    for corner in corners {
                        let cl = 100. * (1. + 0.05 * corner);
                        cases.push(Case {name:format!("fixed_{range}_{n}_stray{stray}_corner{corner}{}_caplead5_local{cl}_lead100", if mode.starts_with("fixedriso") { "_risolo22" } else { "" }),r,cf:0.,dut:dut.clone(),stray:stray*1e-12,rail:12.*(1.+0.05*corner),five:5.*(1.+0.05*corner),rtol:0.001*corner,bridge:100.,riso:4.32});
                    }
                }
            }
        }
    }
    if mode == "localonly" {
        cases.clear();
        for (range, r) in [("r100", 100.), ("r5k", 5000.), ("r100k", 100000.)] {
            for cl in [22., 47., 100.] {
                for lead in [50., 100.] {
                    cases.push(Case {
                        name: format!("fixedcf_{range}_open_local{cl}_lead{lead}"),
                        r,
                        cf: 0.,
                        dut: "RDUT hi low 1e12".into(),
                        stray: 100e-12,
                        rail: 12.,
                        five: 5.,
                        rtol: 0.,
                        bridge: 100.,
                        riso: 4.32,
                    });
                }
            }
        }
    }
    if mode == "local" {
        cases.clear();
        for cl in [5., 10., 22., 47., 100.] {
            for lead in [50., 100.] {
                cases.push(Case {
                    name: format!("r100_open_local{cl}_lead{lead}"),
                    r: 100.,
                    cf: 100e-12,
                    dut: "RDUT hi low 1e12".into(),
                    stray: 100e-12,
                    rail: 12.,
                    five: 5.,
                    rtol: 0.,
                    bridge: 100.,
                    riso: 4.32,
                });
            }
        }
    }
    if mode == "series" {
        cases.clear();
        for rs in [2.2, 4.7, 10., 22., 47., 100.] {
            for lead in [50., 100.] {
                cases.push(Case {
                    name: format!("r100_open_series{rs}_lead{lead}"),
                    r: 100.,
                    cf: 100e-12,
                    dut: "RDUT hi low 1e12".into(),
                    stray: 100e-12,
                    rail: 12.,
                    five: 5.,
                    rtol: 0.,
                    bridge: 100.,
                    riso: 4.32,
                });
            }
        }
    }
    if mode == "cfcompact" {
        cases.clear();
        for cf in [56., 68., 82., 100., 120., 150.] {
            for lead in [20., 25., 35., 50.] {
                cases.push(Case {
                    name: format!("r100_open_cf{cf}_stray100_lead{lead}"),
                    r: 100.,
                    cf: cf * 1e-12,
                    dut: "RDUT hi low 1e12".into(),
                    stray: 100e-12,
                    rail: 12.,
                    five: 5.,
                    rtol: 0.,
                    bridge: 100.,
                    riso: 4.32,
                });
            }
        }
    }
    if mode == "cflead" {
        cases.clear();
        for cf in [22., 47., 220., 470., 1000., 2200., 4700.] {
            for lead in [50., 100.] {
                cases.push(Case {
                    name: format!("r100_open_cf{cf}_stray100_lead{lead}"),
                    r: 100.,
                    cf: cf * 1e-12,
                    dut: "RDUT hi low 1e12".into(),
                    stray: 100e-12,
                    rail: 12.,
                    five: 5.,
                    rtol: 0.,
                    bridge: 100.,
                    riso: 4.32,
                });
            }
        }
    }
    if mode == "damp" {
        cases.clear();
        for (n, dut) in [
            ("open", "RDUT hi low 1e12"),
            ("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u"),
        ] {
            for rc in [3.3, 10., 22., 47., 100.] {
                for lead in [50., 100.] {
                    cases.push(Case {
                        name: format!("r100_{n}_stray100_damp{rc}_lead{lead}"),
                        r: 100.,
                        cf: 100e-12,
                        dut: dut.into(),
                        stray: 100e-12,
                        rail: 12.,
                        five: 5.,
                        rtol: 0.,
                        bridge: 100.,
                        riso: 4.32,
                    });
                }
            }
        }
    }
    if mode == "fixedfixture" || mode == "fixedleads" || mode == "fixedrisoleads" {
        // Fixture/lead envelope beyond the 0/100 pF lumped stray of fixedgrid. Lumped stray
        // per DUT terminal up to 1 nF, plus distributed leads: the TIA crossover is 25–60 MHz,
        // where a metre of coax is a sizeable fraction of a wavelength, so leads are LC ladders.
        cases.clear();
        let duts = |r: f64, coil: bool, hi: &str, lo: &str| {
            let mut v = vec![
                ("open", format!("RDUT {hi} {lo} 1e12")),
                ("short", format!("RDUT {hi} {lo} 0.01")),
                ("matched", format!("RDUT {hi} {lo} {r}")),
            ];
            if coil {
                v.push(("coil50u", format!("RDUT {hi} coil 0.5\nLDUT coil {lo} 50u")));
            }
            v
        };
        for (range, r) in [("r100", 100.), ("r5k", 5000.), ("r100k", 100000.)] {
            if mode == "fixedfixture" {
                for (n, dut) in duts(r, range == "r100", "hi", "low") {
                    for stray in [0., 100., 220., 470., 1000.] {
                        cases.push(Case {name:format!("fixture_{range}_{n}_stray{stray}_caplead5_local100_lead100"),r,cf:0.,dut:dut.clone(),stray:stray*1e-12,rail:12.,five:5.,rtol:0.,bridge:100.,riso:4.32});
                    }
                }
                continue;
            }
            // RG-174-like coax, shield grounded at the board: 50 Ω, 101 pF/m, 252.5 nH/m,
            // lossless (less damping than real cable), 20 sections per metre.
            // Unshielded twisted pair: 0.7 µH/m loop, 50 pF/m between wires, 10 pF/m to ground.
            for (lead, metres) in [("coax0.5m", 0.5), ("coax1m", 1.), ("coax2m", 2.), ("twisted1m", 1.)] {
                let sections = (20. * metres) as usize;
                let dx = metres / sections as f64;
                let mut ladder = String::new();
                for (wire, start) in [("h", "hi"), ("l", "low")] {
                    let mut prev = start.to_string();
                    for k in 0..sections {
                        let next = if k + 1 == sections { format!("{wire}_dut") } else { format!("{wire}_n{k}") };
                        if lead.starts_with("coax") {
                            ladder += &format!("Lw{wire}{k} {prev} {next} {}\nCw{wire}{k} {next} 0 {}\n", 252.5e-9 * dx, 101e-12 * dx);
                        } else {
                            ladder += &format!("Lw{wire}{k} {prev} {next} {}\nCw{wire}{k} {next} 0 {}\n", 0.35e-6 * dx, 10e-12 * dx);
                            if wire == "l" {
                                ladder += &format!("Cpair{k} h_{} {next} {}\n", if k + 1 == sections { "dut".to_string() } else { format!("n{k}") }, 50e-12 * dx);
                            }
                        }
                        prev = next;
                    }
                }
                for (n, dut) in duts(r, range == "r100", "h_dut", "l_dut") {
                    cases.push(Case {name:format!("leads_{range}_{n}_{lead}{}_caplead5_local100_lead100", if mode == "fixedrisoleads" { "_risolo22" } else { "" }),r,cf:0.,dut:format!("{ladder}{dut}"),stray:0.,rail:12.,five:5.,rtol:0.,bridge:100.,riso:4.32});
                }
            }
        }
    }
    if mode == "fixedriso" {
        // Candidate fix: isolation resistor between J3 LO and the summing node, LOW follower
        // left on the connector side. Same fixture envelope as fixedfixture/fixedleads.
        let mut riso_cases = vec![];
        for (range, r, values) in [("r100", 100., vec![10., 22., 47.]), ("r5k", 5000., vec![22., 47.]), ("r100k", 100000., vec![22., 47.])] {
            let mut duts = vec![("open", "RDUT hi low 1e12".to_string()), ("short", "RDUT hi low 0.01".into())];
            if range == "r100" {
                duts.push(("matched", format!("RDUT hi low {r}")));
                duts.push(("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u".into()));
            }
            let strays = if range == "r100" { vec![0., 100., 220., 470., 1000.] } else { vec![0., 1000.] };
            for ri in values {
                for (n, dut) in &duts {
                    for stray in &strays {
                        riso_cases.push(Case {name:format!("riso_{range}_{n}_stray{stray}_risolo{ri}_caplead5_local100_lead100"),r,cf:0.,dut:dut.clone(),stray:stray*1e-12,rail:12.,five:5.,rtol:0.,bridge:100.,riso:4.32});
                    }
                }
            }
        }
        cases = riso_cases;
    }
    if mode == "fixedextracted" {
        // Board parasitics from ../layout-parasitics/extracted.json (high corner), with cable
        // capacitance on top as Cstray. Rev C: board C on low (summing node) and hi, HI-LO and
        // LO-TIA coupling, TIA-out to ground. R_iso variant: the summing side keeps 1.28 pF
        // (geometry_riso.json), the J3 side 3.8 pF. C104 lead 4.87 nH extracted, 10 nH stress;
        // RF lead per range from the extracted high values.
        cases.clear();
        for (range, r, rf_lead) in [("r100", 100., 21.65), ("r5k", 5000., 50.46), ("r100k", 100000., 33.14)] {
            let mut duts = vec![("open", "RDUT hi low 1e12".to_string()), ("short", "RDUT hi low 0.01".into()), ("matched", format!("RDUT hi low {r}"))];
            if range == "r100" {
                duts.push(("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u".into()));
            }
            let strays = if range == "r100" { vec![0., 100., 220., 470., 1000.] } else { vec![0., 1000.] };
            // _revd: the as-built Rev D board, extracted.json rev_d_board high corner, worst over ranges.
            for riso in ["", "_risolo22", "_revd_risolo22"] {
                let board = if riso.is_empty() {
                    "Cbsum low 0 5.62p\nCbhi hi 0 5.234p\nCbhisum hi low 0.156p\nCbsumtia low tia 0.395p\nCbsumlbuf low lowbuf 0.166p\nCbtiao tia 0 10.547p\n"
                } else if riso == "_risolo22" {
                    "Cbj3 low 0 3.8p\nCbsum sum 0 1.28p\nCbhi hi 0 5.234p\nCbhisum hi low 0.156p\nCbsumtia sum tia 0.395p\nCbtiao tia 0 10.547p\n"
                } else {
                    "Cbj3 low 0 5.666p\nCbsum sum 0 1.274p\nCbriso sum low 0.118p\nCbhi hi 0 5.232p\nCbhisum hi low 0.158p\nCbj3lbuf low lowbuf 0.15p\nCbsumtia sum tia 0.399p\nCbtiao tia 0 10.53p\n"
                };
                // EXTRACT_DROP=<element> removes one board parasitic to attribute its effect.
                let drop = std::env::var("EXTRACT_DROP").unwrap_or_default();
                let board: String = board
                    .lines()
                    .filter(|l| drop.is_empty() || !l.starts_with(&format!("{drop} ")))
                    .map(|l| format!("{l}\n"))
                    .collect();
                let riso = if drop.is_empty() { riso.to_string() } else { format!("_drop{drop}{riso}") };
                for (n, dut) in &duts {
                    for stray in &strays {
                        for caplead in [4.87, 10.] {
                            cases.push(Case {name:format!("extracted_{range}_{n}_stray{stray}{riso}_caplead{caplead}_local100_lead{rf_lead}"),r,cf:0.,dut:format!("{board}{dut}"),stray:stray*1e-12,rail:12.,five:5.,rtol:0.,bridge:100.,riso:4.32});
                        }
                    }
                }
            }
        }
    }
    if mode == "codecbase" || mode == "fixedrelay" {
        cases = relay_cases(mode == "fixedrelay", 0., 0.);
    }
    // fixedrelayrout{R}: relay bus behind R ohm; fixedrelaycng{C}: C pF from DUT_LO to ground;
    // codecbasecng{C}: the latter without relays.
    if let Some(rout) = mode.strip_prefix("fixedrelayrout") {
        cases = relay_cases(true, rout.parse().unwrap(), 0.);
    }
    if let Some(cng) = mode.strip_prefix("fixedrelaycng") {
        cases = relay_cases(true, 0., cng.parse().unwrap());
    }
    if let Some(cng) = mode.strip_prefix("codecbasecng") {
        cases = relay_cases(false, 0., cng.parse().unwrap());
    }
    // reverelaycng{C}: fixedrelaycng{C} on the extracted Rev E board (reve_extracted.rs).
    // reverelaycng{C}_r104: the same on the as-built R104 board (reve_r104_extracted.rs).
    if let Some(rest) = mode.strip_prefix("reverelaycng") {
        let (cng, r104) = match rest.strip_suffix("_r104") { Some(c) => (c, true), None => (rest, false) };
        cases = reve_relay_cases(cng.parse().unwrap(), r104);
    }
    let mut report="# Strict full-chain bilateral loop matrix\n\nAll printed cases pass internal DC bias checks. All unity crossings are reported. Angles are signed principal angular separation from -1, not a stability verdict; downward crossings with the usual negative-phase branch correspond to conventional phase margin. Upward crossings must be assessed with the complete return trajectory.\n\n| Case / loop | Unity crossings / signed angle from -1 | Minimum return difference |\n|---|---|---|\n".to_string();
    if final_design {
        for c in &mut cases {
            c.name = format!("final_{}", c.name);
            c.riso = 4.32;
            if mode == "nominal" || mode == "tia" || mode == "low" || mode == "fda" {
                c.cf = if c.r == 100. {
                    100e-12
                } else if c.r == 5000. {
                    10e-12
                } else {
                    5e-12
                };
            }
        }
    }
    // SHARD=i/n runs every n-th case starting at i (parallel processes); each shard writes its own report.
    let shard: Option<(usize, usize)> = std::env::var("SHARD").ok().map(|v| {
        let (i, n) = v.split_once('/').unwrap();
        (i.parse().unwrap(), n.parse().unwrap())
    });
    let requested = match shard {
        Some((i, n)) => format!("{requested}-shard{i}of{n}"),
        None => requested.clone(),
    };
    for (index, c) in cases.into_iter().enumerate() {
        if let Some((i, n)) = shard {
            if index % n != i {
                continue;
            }
        }
        if let Ok(filter) = std::env::var("CASE_FILTER") {
            if !c.name.contains(&filter) {
                continue;
            }
        }
        let loops = if mode == "fda_iso"
            || mode == "fda_ng"
            || mode == "fda_invariance"
            || mode == "fda_filter"
            || mode == "fda_cf"
            || mode == "fda_evm"
        {
            vec!["fda_a", "fda_b"]
        } else if mode == "fda" || mode == "fixedfda" {
            vec!["fda_a", "fda_b", "fda_a_cm", "fda_b_cm"]
        } else if (mode == "fixedfixture" && c.name.contains("_r100_") && c.name.contains("_stray1000_"))
            || (mode == "fixedleads" && c.name.contains("_r100_") && c.name.contains("_coax2m_"))
            || (mode == "fixedriso" && c.name.contains("_r100_") && c.name.contains("_stray1000_"))
        {
            // The heaviest fixture loads also load the source driver and both sense followers.
            vec!["tia", "drive", "high", "low"]
        } else if (mode.starts_with("fixedrelay") || mode.starts_with("reverelay")) && c.name.contains("_loops_") {
            vec!["drive", "high", "low"]
        } else if mode == "low" {
            vec!["low"]
        } else if mode == "nominal" {
            vec![
                "source", "drive", "high", "low", "tia", "fda_a", "fda_b", "fda_a_cm", "fda_b_cm",
            ]
        } else {
            vec!["tia"]
        };
        for lp in loops {
            let mut c = c.clone();
            if lp.starts_with("fda_") && mode != "fda_invariance" {
                c.bridge = 10.;
            } else if ["drive", "high", "low"].contains(&lp) {
                c.bridge = 0.01;
            }
            let name = format!("{}_{}", c.name, lp);
            let (mut s, bridge) = circuit(&c, lp);
            if reuse {
                let row = analyze(&name, bridge, c.five);
                print!("{row}");
                report += &row;
                fs::write(format!("matrix-{requested}.md"), &report).unwrap();
                continue;
            }
            if final_design {
                let (order, conditioned) =
                    strict_order::find_order(&name, &s, 48).expect("strict exact-network OP");
                eprintln!("{name}: exact-network declaration order {order}");
                s = conditioned;
            }
            fs::write(format!("{name}.cir"), s).unwrap();
            for suffix in ["e", "f", "dc"] {
                let _ = fs::remove_file(format!("{name}_{suffix}.dat"));
            }
            let out = Command::new(
                std::env::var("NGSPICE").unwrap_or("/opt/homebrew/bin/ngspice".into()),
            )
            .args(["-b", &format!("{name}.cir")])
            .output()
            .unwrap();
            let mut log = out.stdout;
            log.extend(out.stderr);
            fs::write(format!("{name}.log"), &log).unwrap();
            assert!(
                out.status.success()
                    && !String::from_utf8_lossy(&log).contains("Error:")
                    && !String::from_utf8_lossy(&log)
                        .to_lowercase()
                        .contains("aborted"),
                "{name}: simulator error"
            );
            let row = analyze(&name, bridge, c.five);
            print!("{row}");
            report += &row;
            fs::write(format!("matrix-{requested}.md"), &report).unwrap();
        }
    }
}

/// Rev E: Rev D extracted board (`_revd_risolo22`) on the codec front end, without relays
/// (`codecbase`), or with three TQ2SA latching DPDT relays replacing JP1-JP6 (`fixedrelay`,
/// docs/rev-e-range-switching.md section 6). Nodes: source = SOURCE_BUF, hi = DUT_HI, low = DUT_LO,
/// sum = TIA_SUM, tia = TIA_OUT.
#[derive(Clone, Copy)]
struct Relay {
    rc: f64,   // selected contact resistance, ohm (in series with RG and with RF)
    lrel: f64, // selected contact-path inductance added to the RF lead, nH
    coc: f64,  // open-contact capacitance, pF
    ccc: f64,  // contact-to-coil capacitance, pF
    cpp: f64,  // pole-to-pole capacitance, pF
    dc: f64,   // extra TIA_OUT copper for the relay pads, pF
}
const NOMINAL: Relay = Relay { rc: 0.075, lrel: 10., coc: 0.3, ccc: 1., cpp: 0.5, dc: 3. };
const STRESS: Relay = Relay { rc: 0.075, lrel: 20., coc: 2., ccc: 5., cpp: 2., dc: 10. };
const RANGES: [(&str, f64, f64); 3] = [("r100", 100., 21.65), ("r5k", 5000., 50.46), ("r100k", 100000., 33.14)];
const REVD_BOARD: &str = "Cbj3 low 0 5.666p\nCbsum sum 0 1.274p\nCbriso sum low 0.118p\nCbhi hi 0 5.232p\nCbhisum hi low 0.158p\nCbj3lbuf low lowbuf 0.15p\nCbsumtia sum tia 0.399p\nCbtiao tia 0 10.53p\n";
fn relay_netlist(selected: f64, p: Relay, bus: &str) -> String {
    let mut s = String::new();
    for (k, (_, r, _)) in RANGES.iter().enumerate().filter(|(_, (_, r, _))| *r != selected) {
        s += &format!(
            "Ru{k} sum ru{k} {r}\nCocf{k} ru{k} {bus} {coc}p\nCcf{k} ru{k} 0 {ccc}p\nRgu{k} hi rgu{k} {r}\nCocs{k} rgu{k} source {coc}p\nCcs{k} rgu{k} 0 {ccc}p\nCpp{k} source ru{k} {cpp}p\nCppx{k} rgu{k} {bus} {cpp}p\n",
            coc = p.coc,
            ccc = p.ccc,
            cpp = p.cpp
        );
    }
    s += &format!(
        "Ccsel_t {bus} 0 {ccc}p\nCcsel_s source 0 {ccc}p\nCppsel source {bus} {cpp}p\n",
        ccc = p.ccc,
        cpp = p.cpp,
    );
    // dc = 0 (reverelay modes): the relay pad copper is inside the extracted board TIA_OUT value.
    if p.dc > 0. {
        s += &format!("Cdtia {bus} 0 {}p\n", p.dc);
    }
    s
}
fn relay_case(name: String, r: f64, dut: String, stray: f64) -> Case {
    Case { name, r, cf: 0., dut, stray: stray * 1e-12, rail: 12., five: 5., rtol: 0., bridge: 100., riso: 4.32 }
}
/// `rout` > 0 adds `_rout{rout}`: the relay bus sits behind an isolation resistor (see circuit()).
/// `cng` > 0 adds `_cng{cng}`: a fixed capacitor (pF) from DUT_LO to ground, ahead of R_iso, which
/// lowers the TIA's high-frequency loop gain (noise-gain shaping, as the fixture strays already do).
fn relay_cases(relays: bool, rout: f64, cng: f64) -> Vec<Case> {
    let (bus, mut rt) = if rout > 0. { ("tbus", format!("_rout{rout}")) } else { ("tia", String::new()) };
    let board = if cng > 0. {
        rt += &format!("_cng{cng}");
        format!("Cng low 0 {cng}p\n{REVD_BOARD}")
    } else {
        REVD_BOARD.to_string()
    };
    let mut cases = vec![];
    let sets: Vec<(&str, Relay)> = if relays { vec![("nom", NOMINAL), ("str", STRESS)] } else { vec![("none", NOMINAL)] };
    // 1. Grid over the Rev D extracted combinations.
    for (set, p) in &sets {
        for (range, r, rf_lead) in RANGES {
            let mut duts = vec![("open", "RDUT hi low 1e12".to_string()), ("short", "RDUT hi low 0.01".into()), ("matched", format!("RDUT hi low {r}"))];
            if range == "r100" {
                duts.push(("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u".into()));
            }
            let strays = if range == "r100" { vec![0., 100., 220., 470., 1000.] } else { vec![0., 1000.] };
            for (n, dut) in &duts {
                for stray in &strays {
                    for caplead in [4.87, 10.] {
                        let (tag, rr, lead, extra) = if relays {
                            ("relay", r + p.rc, rf_lead + p.lrel, relay_netlist(r, *p, bus))
                        } else {
                            ("codec", r, rf_lead, String::new())
                        };
                        cases.push(relay_case(format!("{tag}_{range}_{n}_stray{stray}_revd_risolo22_{set}{rt}_caplead{caplead}_local100_lead{lead}"), rr, format!("{board}{extra}{dut}"), *stray));
                    }
                }
            }
        }
    }
    if !relays {
        return cases;
    }
    // 2. Attribution: stress value of one parameter at a time, the rest nominal.
    for (range, r, rf_lead) in RANGES {
        for param in ["coc", "ccc", "cpp", "lrel", "dc", "rc"] {
            let mut p = NOMINAL;
            match param {
                "coc" => p.coc = STRESS.coc,
                "ccc" => p.ccc = STRESS.ccc,
                "cpp" => p.cpp = STRESS.cpp,
                "lrel" => p.lrel = STRESS.lrel,
                "dc" => p.dc = STRESS.dc,
                _ => p.rc = STRESS.rc,
            }
            cases.push(relay_case(format!("relay_attr{param}_{range}_open_stray0_revd_risolo22{rt}_caplead10_local100_lead{}", rf_lead + p.lrel), r + p.rc, format!("{board}{}RDUT hi low 1e12", relay_netlist(r, p, bus)), 0.));
        }
    }
    // 3. Source driver and sense followers: stress set, heaviest fixture.
    for (range, r, rf_lead) in [RANGES[0], RANGES[2]] {
        for stray in [0., 1000.] {
            cases.push(relay_case(format!("relay_loops_{range}_open_stray{stray}_revd_risolo22_str{rt}_caplead10_local100_lead{}", rf_lead + STRESS.lrel), r + STRESS.rc, format!("{board}{}RDUT hi low 1e12", relay_netlist(r, STRESS, bus)), stray));
        }
    }
    // 4. Two relays closed (weld): second feedback and source path in parallel.
    for (a, b) in [(0, 1), (0, 2), (1, 2)] {
        let (ra, rb) = (RANGES[a], RANGES[b]);
        cases.push(relay_case(format!("relay_weld_{}_{}_open_stray0_revd_risolo22_nom{rt}_caplead10_local100_lead{}", ra.0, rb.0, ra.2 + NOMINAL.lrel), ra.1 + NOMINAL.rc, format!("{board}{}Rpar sum rfp {}\nLpar rfp {bus} 30n\nRGpar source hi {}\nRDUT hi low 1e12", relay_netlist(ra.1, NOMINAL, bus), rb.1, rb.1), 0.));
    }
    cases
}

// Rev E extracted board: per-range SPICE capacitors (REVE_BOARD_NOM/HIGH, nodes sum low tia hi
// lowbuf highbuf source ru{k} rgu{k}) and loop inductances (REVE_LEAD, REVE_CAPLEAD), generated by
// ../layout-parasitics/assemble_reve.py.
include!("reve_extracted.rs");
include!("reve_r104_extracted.rs");
/// `reverelaycng{C}`: `fixedrelaycng{C}` with the Rev E extraction in place of REVD_BOARD and the
/// Rev D RF leads. The board netlist already holds all TIA_OUT copper (relay pads included), so
/// `dc` = 0; coc/ccc/cpp/lrel/rc stay the relay-internal NOMINAL/STRESS estimates. Nominal relay
/// set runs on the nominal board corner (`_bnom`), stress set on the high corner (`_bhigh`).
fn reve_relay_cases(cng: f64, r104: bool) -> Vec<Case> {
    // r104: as-built R104 board (reve_r104_extracted.rs): driver -> C(SRC_DRV) -> 47 ohm -> SOURCE_BUF.
    let rt = if r104 { format!("_cng{cng}_r104_srciso47") } else { format!("_cng{cng}") };
    let (board_nom, board_high, leads, caplead0) = if r104 {
        (REVE_R104_BOARD_NOM, REVE_R104_BOARD_HIGH, REVE_R104_LEAD, REVE_R104_CAPLEAD)
    } else {
        (REVE_BOARD_NOM, REVE_BOARD_HIGH, REVE_LEAD, REVE_CAPLEAD)
    };
    let board = |corner: &str, k: usize| {
        format!("Cng low 0 {cng}p\n{}", if corner == "bnom" { board_nom[k] } else { board_high[k] })
    };
    let nom = Relay { dc: 0., ..NOMINAL };
    let stress = Relay { dc: 0., ..STRESS };
    let mut cases = vec![];
    // 1. Grid: same DUT / stray / caplead grid as fixedrelaycng{C}.
    for (set, p, bc) in [("nom", nom, "bnom"), ("str", stress, "bhigh")] {
        for (k, &(range, r, _)) in RANGES.iter().enumerate() {
            let mut duts = vec![("open", "RDUT hi low 1e12".to_string()), ("short", "RDUT hi low 0.01".into()), ("matched", format!("RDUT hi low {r}"))];
            if range == "r100" {
                duts.push(("coil50u", "RDUT hi coil 0.5\nLDUT coil low 50u".into()));
            }
            let strays = if range == "r100" { vec![0., 100., 220., 470., 1000.] } else { vec![0., 1000.] };
            for (n, dut) in &duts {
                for stray in &strays {
                    for caplead in [caplead0, 10.] {
                        cases.push(relay_case(format!("reverelay_{range}_{n}_stray{stray}_risolo22_{bc}_{set}{rt}_caplead{caplead}_local100_lead{:.2}", leads[k] + p.lrel), r + p.rc, format!("{}{}{dut}", board(bc, k), relay_netlist(r, p, "tia")), *stray));
                    }
                }
            }
        }
    }
    // 2. Attribution on the high board, open DUT, stray 0, caplead 10: one relay stress value at a
    //    time (rest nominal), and the Rev D RF lead in place of the Rev E extracted lead.
    for (k, &(range, r, revd_lead)) in RANGES.iter().enumerate() {
        for param in ["none", "coc", "ccc", "cpp", "lrel", "allstr", "revdlead"] {
            let mut p = nom;
            match param {
                "coc" => p.coc = STRESS.coc,
                "ccc" => p.ccc = STRESS.ccc,
                "cpp" => p.cpp = STRESS.cpp,
                "lrel" => p.lrel = STRESS.lrel,
                "allstr" => p = stress,
                _ => {}
            }
            let lead = if param == "revdlead" { revd_lead + p.lrel } else { leads[k] + p.lrel };
            cases.push(relay_case(format!("reverelay_attr{param}_{range}_open_stray0_risolo22_bhigh{rt}_caplead10_local100_lead{lead:.2}"), r + p.rc, format!("{}{}RDUT hi low 1e12", board("bhigh", k), relay_netlist(r, p, "tia")), 0.));
        }
    }
    // 3. Source driver and sense followers: stress set, high board, every range, heaviest fixture.
    for (k, &(range, r, _)) in RANGES.iter().enumerate() {
        for stray in [0., 1000.] {
            cases.push(relay_case(format!("reverelay_loops_{range}_open_stray{stray}_risolo22_bhigh_str{rt}_caplead10_local100_lead{:.2}", leads[k] + STRESS.lrel), r + STRESS.rc, format!("{}{}RDUT hi low 1e12", board("bhigh", k), relay_netlist(r, stress, "tia")), stray));
        }
    }
    // 3b. Source-driver attribution and fix candidates (r100 / r100k, open, stray 0): relay set x
    //     board corner, the high board without any capacitor touching SOURCE_BUF, and an
    //     isolation resistor between X6A and the SOURCE_BUF bus (`_srciso{R}`, see circuit()).
    for k in 0..3 {
        let (range, r, _) = RANGES[k];
        let nosrc: String = board("bhigh", k).lines().filter(|l| !l.split(' ').any(|t| t == "source")).map(|l| format!("{l}\n")).collect();
        let variants: Vec<(String, Relay, String, f64)> = vec![
            ("drvnomnom".into(), nom, board("bnom", k), 0.),
            ("drvnomhigh".into(), nom, board("bhigh", k), 0.),
            ("drvstrnom".into(), stress, board("bnom", k), 0.),
            ("drvstrhighnosrcboard".into(), stress, nosrc, 0.),
            ("drvstrhigh_srciso10".into(), stress, board("bhigh", k), 0.),
            ("drvstrhigh_srciso22".into(), stress, board("bhigh", k), 0.),
            ("drvstrhigh_srciso47".into(), stress, board("bhigh", k), 0.),
            ("drvstrhigh_srciso47".into(), stress, board("bhigh", k), 1000.),
            ("drvnomnom_srciso47".into(), nom, board("bnom", k), 0.),
        ];
        for (tag, p, b, stray) in variants {
            if r104 && tag.contains("srciso") {
                continue; // R104 is already in the board topology
            }
            cases.push(relay_case(format!("reverelay_loops_{tag}_{range}_open_stray{stray}_risolo22{rt}_caplead10_local100_lead{:.2}", leads[k] + p.lrel), r + p.rc, format!("{b}{}RDUT hi low 1e12", relay_netlist(r, p, "tia")), stray));
        }
        // TIA loop with the 47 ohm source isolation resistor: stress/high, open and short DUT.
        for (n, dut) in if r104 { vec![] } else { vec![("open", "RDUT hi low 1e12"), ("short", "RDUT hi low 0.01")] } {
            cases.push(relay_case(format!("reverelay_attrsrciso47_{range}_{n}_stray0_risolo22_bhigh_str{rt}_srciso47_caplead10_local100_lead{:.2}", leads[k] + STRESS.lrel), r + STRESS.rc, format!("{}{}{dut}", board("bhigh", k), relay_netlist(r, stress, "tia")), 0.));
        }
    }
    // 4. Two relays closed (weld), nominal set and board.
    for (a, b) in [(0, 1), (0, 2), (1, 2)] {
        let (ra, rb) = (RANGES[a], RANGES[b]);
        cases.push(relay_case(format!("reverelay_weld_{}_{}_open_stray0_risolo22_bnom_nom{rt}_caplead10_local100_lead{:.2}", ra.0, rb.0, leads[a] + NOMINAL.lrel), ra.1 + NOMINAL.rc, format!("{}{}Rpar sum rfp {}\nLpar rfp tia {}n\nRGpar source hi {}\nRDUT hi low 1e12", board("bnom", a), relay_netlist(ra.1, nom, "tia"), rb.1, leads[b] + NOMINAL.lrel, rb.1), 0.));
    }
    cases
}
