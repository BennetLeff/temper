use std::{fs, process::Command};
fn data(p: &str) -> Vec<Vec<f64>> {
    fs::read_to_string(p)
        .unwrap()
        .lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_whitespace()
                .map(|v| {
                    let x: f64 = v.parse().unwrap();
                    assert!(x.is_finite());
                    x
                })
                .collect()
        })
        .collect()
}
fn main() {
    let mut cases = vec![
        (
            "c100_cap100n".to_string(),
            100,
            "CDUT hi low 100n".to_string(),
            0,
            0,
        ),
        ("c100_cap500n".into(), 100, "CDUT hi low 500n".into(), 0, 0),
        ("c100_cap9u".into(), 100, "CDUT hi low 9u".into(), 0, 0),
        (
            "c100_coil50u".into(),
            100,
            "RDUT hi coil 0.5\nLDUT coil low 50u".into(),
            0,
            0,
        ),
        ("c100_open".into(), 100, "RDUT hi low 1T".into(), 0, 0),
        ("c100_short10m".into(), 100, "RDUT hi low 10m".into(), 0, 0),
    ];
    for hi in [0, 100] {
        for lo in [0, 100] {
            cases.push((
                format!("c100k_coil_hi{hi}_lo{lo}"),
                100000,
                "RDUT hi coil 0.5\nLDUT coil low 50u".into(),
                hi,
                lo,
            ));
        }
    }
    let mut report=String::from("# Rev C bounded fast-disturbance transients\n\nOfficial unmodified 2021 GWL THS4551 model; Riso=4.02Ω; real FDA bias/loading. 1µA DUT HI→LO current pulse,1ns edges,10µs width;20µs total,1ns maximum step. DDS at0.3V DC with source AC coupling retained. Open means1TΩ and short means10mΩ. These are bounded finite waveform checks, not proof of all loop margins or long-time settling.\n\n| Case | HI/LO to ground pF | Peak TIA change mV | Peak HIGH buffer change mV | Peak LOW buffer change mV | Final TIA offset µV | ADC min/max V |\n|---|---|---:|---:|---:|---:|---|\n");
    for (name, r, dut, ch, cl) in cases {
        let old = if r == 100 {
            "revc_100r_cap100n"
        } else {
            "revc_100k_resistor"
        };
        let base = fs::read_to_string(format!("{old}.cir")).unwrap();
        let mut s = base
            .split(".control")
            .next()
            .unwrap()
            .replace("SIN(0.3 0.3 50k)", "")
            .replace(
                if r == 100 {
                    "CDUT hi low 100n"
                } else {
                    "RDUT hi low 100000"
                },
                &dut,
            );
        s+=&format!("Chi hi 0 {}\nClo low 0 {}\nItest hi low PULSE(0 1u 1u 1n 1n 10u 30u)\n.control\nset klu\nset wr_singlescale\nset wr_vecnames\nset filetype=ascii\nop\nwrite {name}_op.raw all\ntran 1n 20u 0 1n\nwrdata {name}_tran.dat v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aadc_p) v(aadc_m) v(badc_p) v(badc_m)\nquit\n.endc\n.end\n",if ch==0{1e-24}else{ch as f64*1e-12},if cl==0{1e-24}else{cl as f64*1e-12});
        fs::write(format!("{name}.cir"), s).unwrap();
        let o = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{name}.cir")])
            .output()
            .unwrap();
        let mut log = o.stdout;
        log.extend(o.stderr);
        fs::write(format!("{name}.log"), &log).unwrap();
        let t = String::from_utf8_lossy(&log);
        assert!(!t.contains("Error") && !t.contains("aborted"));
        let guard = Command::new("./op_guard")
            .arg(format!("{name}_op.raw"))
            .output()
            .unwrap();
        assert!(
            guard.status.success(),
            "{name}: {}",
            String::from_utf8_lossy(&guard.stderr)
        );
        let d = data(&format!("{name}_tran.dat"));
        assert!(d.len() > 20000);
        assert!((d.last().unwrap()[0] - 20e-6).abs() < 1e-12);
        let baseline = d
            .iter()
            .min_by(|a, b| (a[0] - 0.9e-6).abs().total_cmp(&(b[0] - 0.9e-6).abs()))
            .unwrap();
        let peak = |col: usize| {
            d.iter()
                .map(|v| (v[col] - baseline[col]).abs())
                .fold(0., f64::max)
                * 1e3
        };
        let lo = d
            .iter()
            .flat_map(|v| v[6..10].iter())
            .copied()
            .fold(f64::INFINITY, f64::min);
        let hi = d
            .iter()
            .flat_map(|v| v[6..10].iter())
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        assert!(lo > 0.1 && hi < 4.9);
        assert!(d.iter().all(|v| v[1..6].iter().all(|x| x.abs() < 10.)));
        report += &format!(
            "| {name} | {ch}/{cl} | {:.6} | {:.6} | {:.6} | {:.6} | {lo:.6}/{hi:.6} |\n",
            peak(3),
            peak(4),
            peak(5),
            (d.last().unwrap()[3] - baseline[3]) * 1e6
        );
        fs::write("extended-pulse.md", &report).unwrap();
        println!("{name} PASS");
    }
}
