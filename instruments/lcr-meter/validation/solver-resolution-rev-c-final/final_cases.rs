// Historical initial ordering experiment, including retained failures.
// Use rerun.sh and accepted-cases.txt for the accepted complete matrix.
use std::{
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
fn transform(s: &str) -> String {
    let (h, c) = s.split_once(".control").unwrap();
    let mut h = h
        .replace("offset-nodeset.inc", "final-seed.inc")
        .replace("Raint1 aom afbm 3.3", "Raint1 aom afbm 22")
        .replace("Raint2 aop afbp 3.3", "Raint2 aop afbp 22")
        .replace("Rbint1 bom bfbm 3.3", "Rbint1 bom bfbm 22")
        .replace("Rbint2 bop bfbp 3.3", "Rbint2 bop bfbp 22")
        .replace("Raiso1 aop aadc_p 4.02", "Raiso1 afbp aadc_p 4.32")
        .replace("Raiso2 aom aadc_m 4.02", "Raiso2 afbm aadc_m 4.32")
        .replace("Rbiso1 bop badc_p 4.02", "Rbiso1 bfbp badc_p 4.32")
        .replace("Rbiso2 bom badc_m 4.02", "Rbiso2 bfbm badc_m 4.32");
    h += "Cfba1 afbm aip 100p\nCfba2 afbp aim 100p\nCfbb1 bfbm bip 100p\nCfbb2 bfbp bim 100p\n";
    let mut dir = String::new();
    let mut comp = Vec::new();
    for (i, l) in h.lines().enumerate() {
        if i == 0 || l.starts_with(['.', '*']) {
            dir += l;
            dir += '\n'.to_string().as_str();
        } else {
            comp.push(l);
        }
    }
    comp.reverse();
    format!("{dir}{}\n.control{c}", comp.join("\n"))
}
fn rows(p: &str) -> Vec<Vec<f64>> {
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
    fs::create_dir_all("nominal-inputs").unwrap();
    let mut report =
        String::from("case,status,dc_kcl_pa,ac_rows,transient_rows,adc_min_v,adc_max_v\n");
    for n in [
        "revc_100r_cap100n",
        "revc_100r_cap500n",
        "revc_100r_cap9u",
        "revc_100r_coil50u",
        "revc_5k_resistor",
        "revc_100k_resistor",
    ] {
        let source = format!("nominal-inputs/{n}.cir");
        assert!(
            std::path::Path::new(&source).exists(),
            "bundled nominal input missing"
        );
        let s = transform(&fs::read_to_string(source).unwrap());
        fs::write(format!("{n}.cir"), s).unwrap();
        let f = fs::File::create(format!("{n}.log")).unwrap();
        let mut child = Command::new("/opt/homebrew/bin/ngspice")
            .args(["-b", &format!("{n}.cir")])
            .stdout(Stdio::from(f.try_clone().unwrap()))
            .stderr(Stdio::from(f))
            .spawn()
            .unwrap();
        let st = Instant::now();
        while child.try_wait().unwrap().is_none() {
            if st.elapsed() > Duration::from_secs(30) {
                child.kill().unwrap();
                child.wait().unwrap();
                break;
            }
            thread::sleep(Duration::from_millis(100));
        }
        let g = Command::new("./op_guard")
            .arg(format!("{n}_op.raw"))
            .output()
            .unwrap();
        let log = fs::read_to_string(format!("{n}.log")).unwrap();
        if !g.status.success() || log.contains("Error") || log.contains("aborted") {
            println!("{n} FAIL");
            report += &format!("{n},FAIL,,,,,\n");
        } else {
            let dc = rows(&format!("{n}_dc.dat"));
            let k = dc[0][18..21].iter().map(|x| x.abs()).fold(0., f64::max);
            let ac = rows(&format!("{n}_ac.dat"));
            let tr = rows(&format!("{n}_tran.dat"));
            assert_eq!(ac.len(), 561);
            assert!((tr.last().unwrap()[0] - 120e-6).abs() < 1e-12);
            assert!(k < 2e-12);
            let lo = tr
                .iter()
                .flat_map(|v| v[8..12].iter())
                .copied()
                .fold(f64::INFINITY, f64::min);
            let hi = tr
                .iter()
                .flat_map(|v| v[8..12].iter())
                .copied()
                .fold(f64::NEG_INFINITY, f64::max);
            assert!(lo > 0.1 && hi < 4.9);
            report += &format!(
                "{n},PASS,{},{},{},{lo},{hi}\n",
                k * 1e12,
                ac.len(),
                tr.len()
            );
            println!("{n} PASS");
        }
        fs::write("nominal-results.csv", &report).unwrap();
    }
}
