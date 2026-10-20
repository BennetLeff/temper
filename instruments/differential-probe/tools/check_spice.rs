//! Summarize the nominal TI OPA810 macromodel fixtures, not bench qualification.
use std::{error::Error, fs};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
fn rows(path: &str) -> Result<Vec<Vec<f64>>> {
    fs::read_to_string(path)?
        .lines()
        .skip(1)
        .map(|line| {
            line.split_whitespace()
                .map(|x| x.parse::<f64>().map_err(Into::into))
                .collect()
        })
        .collect()
}
fn interpolate(data: &[Vec<f64>], col: usize, f: f64) -> f64 {
    let pair = data
        .windows(2)
        .find(|p| p[0][0] <= f && f <= p[1][0])
        .unwrap();
    let t = (f.ln() - pair[0][0].ln()) / (pair[1][0].ln() - pair[0][0].ln());
    pair[0][col] + t * (pair[1][col] - pair[0][col])
}
fn main() -> Result<()> {
    let ac = rows("validation/spice/ac.tsv")?;
    let mut report="TI OPA2810 Rev A (U1A/U1B buffers, U3B subtractor, U3A driver) and OPA810 Rev A (U12) vendor macromodels; ngspice 45.2 PSpice compatibility.\nIdeal lumped 2000:1 compensated dividers and R12/R32 included; supplies +4.8000 / -4.8068 V; fixed switch positions; 1M scope plus lumped 120pF cable/input.\nGains are output per volt of tip differential input.\n\n".to_string();
    for (col, label, expected) in [(1, "1000:1", 9.99412e-4), (2, "200:1", 5.00510e-3)] {
        let gain = ac[0][col];
        assert!(
            (gain / expected - 1.).abs() < 0.001,
            "unexpected low-frequency gain {label}"
        );
        let target = gain / 2f64.sqrt();
        let pair = ac
            .windows(2)
            .find(|p| p[0][col] >= target && p[1][col] < target)
            .ok_or("no -3dB crossing")?;
        let bw = pair[0][0]
            + (pair[1][0] - pair[0][0]) * (pair[0][col] - target) / (pair[0][col] - pair[1][col]);
        assert!((4.8e6..6.2e6).contains(&bw), "unexpected bandwidth {label}");
        let peak = ac.iter().map(|r| r[col]).fold(0f64, f64::max) / gain;
        assert!(peak < 1.01, "unexpected AC peaking {label}");
        report+=&format!("{label}: LF gain {gain:.8e} V/V (ratio {:.3}:1); normalized -3dB bandwidth {:.4} MHz; maximum response {:.4} dB above LF (checked < 0.09 dB).\n",1./gain,bw/1e6,20.*peak.log10());
        for f in [35e3, 60e3, 5e6] {
            let relative = 20. * (interpolate(&ac, col, f) / gain).log10();
            let phase = interpolate(&ac, col + 2, f);
            report += &format!(
                "  {:.0} Hz: relative amplitude {relative:.6} dB, phase {phase:.6} deg.\n",
                f
            );
        }
    }
    let tran = rows("validation/spice/unused-fine-saturation.tsv")?;
    let settled: Vec<_> = tran.iter().filter(|r| r[0] >= 20e-6).collect();
    let difference = settled.iter().map(|r| r[4].abs()).fold(0f64, f64::max);
    let maximum = settled
        .iter()
        .map(|r| r[3])
        .fold(f64::NEG_INFINITY, f64::max);
    let minimum = settled.iter().map(|r| r[3]).fold(f64::INFINITY, f64::min);
    let wide_peak = settled.iter().map(|r| r[1].abs()).fold(0f64, f64::max);
    assert!(
        maximum > 4.5 && minimum < -4.5,
        "fixture did not overdrive fine stage"
    );
    assert!(
        difference < 0.001,
        "fine branch disturbed wide output by >=1mV"
    );
    assert!(
        (1.45..1.55).contains(&wide_peak),
        "wide signal missing or clipped"
    );
    report+=&format!("\n60kHz, 1500Vpk differential at the tips, wide range: fine-stage model spans {minimum:.6} to {maximum:.6} V.\nMax wide-output difference with fine branch connected versus disconnected (20..60us): {:.3} nV.\n",difference*1e9);
    report+="The fine-stage model clip levels extend about 0.12V outside the ideal supply rails; they are not physical clip-voltage predictions.\nThis comparison supports only nominal branch isolation within the vendor model. It excludes real supply coupling, OPA2810 inter-channel coupling (the model is one channel per instance), layout/lead parasitics, distributed divider strays, temperature/tolerances, switch transitions/bounce and clamp references.\nNo bench stability, CMRR, bandwidth, clip level or recovery rating is established.\n";
    fs::write("validation/spice/results.txt", &report)?;
    print!("{report}");
    Ok(())
}
