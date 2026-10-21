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
fn circuit(c: &Case, lp: &str) -> (String, f64) {
    let final_design = c.name.starts_with("final_");
    let mut s = fs::read_to_string(if final_design {
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
    let name = format!("{}_{}", c.name, lp);
    let density = if c.name.contains("fixed_r100k_coil") {
        19200
    } else if c.name.contains("coil") {
        4800
    } else {
        120
    };
    s+=&format!(".control\nset klu\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\nwrdata {name}_dc.dat v(x5.mid) v(x6a.mid) v(x6b.mid) v(x7a.mid) v(x7b.mid) v(xa.mid) v(xb.mid) v(acin) v(source) v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aop) v(aom) v(bop) v(bom)\nac dec 120 1 1G\nlet ve={ve}\nlet vf={vf}\nwrdata {name}_e.dat real(ve) imag(ve) real(vf) imag(vf)\n{second}ac dec 120 1 1G\nlet ve={ve}\nlet vf={vf}\nwrdata {name}_f.dat real(ve) imag(ve) real(vf) imag(vf)\nquit\n.endc\n.end\n");
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
    for x in &dc[6..8] {
        assert!((x - five / 2.).abs() < 1e-4, "FDA MID invalid {name}: {x}");
    }
    assert!(dc[8].abs() < 1e-5, "AC coupling not atDC {name}");
    for x in &dc[15..19] {
        assert!(*x > 1.9 && *x < 2.2, "FDA saturation {name}");
    }
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
    for c in cases {
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
