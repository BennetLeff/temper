use std::{f64::consts::PI, fs};
fn data(p: &str) -> Vec<Vec<f64>> {
    let text = fs::read_to_string(p).unwrap();
    let rows: Vec<Vec<f64>> = text
        .lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_whitespace()
                .map(|v| {
                    let x: f64 = v.parse().unwrap();
                    assert!(x.is_finite(), "nonfinite {p}");
                    x
                })
                .collect()
        })
        .collect();
    assert!(!rows.is_empty(), "empty {p}");
    rows
}
fn near(d: &[Vec<f64>], f: f64) -> &Vec<f64> {
    d.iter()
        .min_by(|a, b| (a[0] - f).abs().partial_cmp(&(b[0] - f).abs()).unwrap())
        .unwrap()
}
fn main() {
    let mut out=String::from("# Exact coupled circuit: solver and transient checks\n\nGenerated data checks; official vendor models unchanged. DC/AC/transient all required, every numeric field finite.\n\n| Case | I HIGH buffer mA | I LOW buffer mA | I TIA mA | max DC output KCL residual pA | AC rows | transient rows | ADC pin min/max V |\n|---|---:|---:|---:|---:|---:|---:|---|\n");
    for n in [
        "100r_cap100n",
        "100r_cap500n",
        "100r_cap9u",
        "100r_coil50u",
        "5k_resistor",
        "100k_resistor",
    ] {
        let log = fs::read_to_string(format!("{n}.log")).unwrap();
        assert!(!log.contains("Error") && !log.contains("aborted"));
        let dc = data(&format!("{n}_dc.dat"));
        assert_eq!(dc.len(), 1);
        let ac = data(&format!("{n}_ac.dat"));
        assert_eq!(ac.len(), 561);
        let tr = data(&format!("{n}_tran.dat"));
        assert!(tr.len() > 12000);
        assert!((tr.last().unwrap()[0] - 120e-6).abs() < 1e-12);
        let d = &dc[0];
        let k = d[18..21].iter().map(|x| x.abs()).fold(0., f64::max);
        assert!(k < 2e-12);
        let lo = tr
            .iter()
            .flat_map(|r| r[8..12].iter())
            .copied()
            .fold(f64::INFINITY, f64::min);
        let hi = tr
            .iter()
            .flat_map(|r| r[8..12].iter())
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        assert!(lo > 0.1 && hi < 4.9);
        out += &format!(
            "| {n} | {:.7} | {:.7} | {:.7} | {:.5} | {} | {} | {:.6} / {:.6} |\n",
            d[15] * 1000.,
            d[16] * 1000.,
            d[17] * 1000.,
            k * 1e12,
            ac.len(),
            tr.len(),
            lo,
            hi
        );
    }
    out+="\nDC output current is taken from the existing manufacturer model output-current sensor, with negative sign for current delivered externally. Residuals include omitted follower input bias and ESD off leakage (~pA), not an unconstrained op-amp output. Negative currents are real FDA common-mode sink loading.\n\n## Five-kilohm fast-disturbance transient\n\n1µA current pulse from DUT_HI to DUT_LO;1ns edge; both RG/RF=5kΩ and DUT=5kΩ. This is a diagnostic disturbance, not the normal DDS waveform. FDA CM/load retained. Nominal27°C.\n\n| Case | TIA increment mV | TIA overshoot % | last outside1% ns afteredge |\n|---|---:|---:|---:|\n";
    for n in [
        "pulse5k_cf0",
        "pulse5k_cf2p2",
        "pulse5k_cf4p7",
        "pulse5k_cf10",
        "pulse5k_cf0_fixture100",
        "pulse5k_cf2p2_fixture100",
        "pulse5k_cf4p7_fixture100",
        "pulse5k_cf10_fixture100",
    ] {
        let d = data(&format!("{n}.dat"));
        assert!((d.last().unwrap()[0] - 8e-6).abs() < 1e-12);
        let base = near(&d, 0.9e-6)[3];
        let steady = near(&d, 3.9e-6)[3];
        let delta = steady - base;
        let mut overshoot = 0f64;
        let mut last = 1.001e-6;
        for row in d.iter().filter(|r| r[0] > 1.001e-6 && r[0] < 3.9e-6) {
            let norm = (row[3] - base) / delta;
            overshoot = overshoot.max(norm - 1.);
            if (norm - 1.).abs() > 0.01 {
                last = row[0]
            }
        }
        out += &format!(
            "| {n} | {:.6} | {:.3} | {:.2} |\n",
            delta * 1000.,
            overshoot * 100.,
            (last - 1.001e-6) * 1e9
        );
    }
    out+="\nStructural-shunt sensitivity is recorded separately; do not infer robustness from one converged circuit.\n";
    fs::write("verified-results.md", out).unwrap();
    // Plot first500ns after pulse edge, actual samples, native SVG.
    let mut svg=String::from("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"960\" height=\"480\"><rect width=\"960\" height=\"480\" fill=\"white\"/><g font-family=\"sans-serif\" fill=\"#172b4d\"><text x=\"60\" y=\"30\" font-size=\"20\">5kΩ range: nominal TIA response to1µA DUT disturbance</text><text x=\"60\" y=\"52\" font-size=\"13\">Full coupled TI models;1ns current edge;100pF across5kΩ DUT; no hardware claim</text>");
    for (n, color, label) in [
        ("pulse5k_cf0_fixture100", "#bd3030", "No added CF"),
        ("pulse5k_cf10_fixture100", "#007f87", "10pF CF candidate"),
    ] {
        let d = data(&format!("{n}.dat"));
        let base = near(&d, 0.9e-6)[3];
        let points = d
            .iter()
            .filter(|r| r[0] >= 0.99e-6 && r[0] <= 1.5e-6)
            .map(|r| {
                format!(
                    "{:.2},{:.2}",
                    60. + (r[0] - 1e-6) / 500e-9 * 840.,
                    90. + (-(r[3] - base) / 0.006) * 270.
                )
            })
            .collect::<Vec<_>>()
            .join(" ");
        svg+=&format!("<polyline points=\"{points}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"2\"/><text x=\"{}\" y=\"445\" fill=\"{color}\">{label}</text>",if color=="#bd3030"{60}else{430});
    }
    for t in [0, 100, 200, 300, 400, 500] {
        let x = 60. + t as f64 / 500. * 840.;
        svg+=&format!("<path d=\"M{x} 85 V365\" stroke=\"#ddd\"/><text x=\"{}\" y=\"390\" font-size=\"12\">{t}ns</text>",x-12.);
    }
    for mv in [0, 2, 4, 6] {
        let y = 90. + mv as f64 / 6. * 270.;
        svg+=&format!("<path d=\"M60 {y} H900\" stroke=\"#ddd\"/><text x=\"8\" y=\"{}\" font-size=\"12\">−{mv}mV</text>",y+4.);
    }
    svg += "</g></svg>";
    fs::write("5k-ringing.svg", svg).unwrap();
    let _ = PI;
}
