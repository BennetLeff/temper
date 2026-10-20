use std::{
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
fn run(name: &str, s: String) -> bool {
    fs::write(format!("{name}.cir"), s).unwrap();
    let log = fs::File::create(format!("{name}.log")).unwrap();
    let mut child = Command::new("ngspice")
        .args(["-b", &format!("{name}.cir")])
        .stdout(Stdio::from(log.try_clone().unwrap()))
        .stderr(Stdio::from(log))
        .spawn()
        .unwrap();
    let start = Instant::now();
    let mut timeout = false;
    while child.try_wait().unwrap().is_none() {
        if start.elapsed() > Duration::from_secs(30) {
            child.kill().unwrap();
            child.wait().unwrap();
            timeout = true;
            break;
        }
        thread::sleep(Duration::from_millis(50))
    }
    if timeout {
        println!("{name} TIMEOUT");
        return false;
    }
    let log = fs::read_to_string(format!("{name}.log")).unwrap();
    if log.contains("Error") || log.contains("aborted") {
        println!("{name} FAIL");
        return false;
    }
    let op = Command::new("./op_guard")
        .arg(format!("{name}.raw"))
        .output()
        .unwrap();
    println!(
        "{name} {} {}",
        if op.status.success() {
            "TRUE_DC"
        } else {
            "INVALID"
        },
        String::from_utf8_lossy(&op.stdout)
    );
    op.status.success()
}
fn main() {
    let original = fs::read_to_string("nominal-inputs/revc_100r_cap100n.cir").unwrap();
    let base = original
        .split(".control")
        .next()
        .unwrap()
        .replace("offset-nodeset.inc", "old-offset-nodeset.inc")
        .replace("SIN(0.3 0.3 50k)", "");
    for (name, ri, resistive) in [
        ("final-cap", 22., false),
        ("final-resistor", 22., true),
        ("stage-3p3", 3.3, false),
    ] {
        let mut s = base.clone();
        for (out, tap, adc, rint, riso) in [
            ("aop", "afbp", "aadc_p", "Raint2", "Raiso1"),
            ("aom", "afbm", "aadc_m", "Raint1", "Raiso2"),
            ("bop", "bfbp", "badc_p", "Rbint2", "Rbiso1"),
            ("bom", "bfbm", "badc_m", "Rbint1", "Rbiso2"),
        ] {
            s = s
                .replace(
                    &format!("{rint} {out} {tap} 3.3"),
                    &format!("{rint} {out} {tap} {ri}"),
                )
                .replace(
                    &format!("{riso} {out} {adc} 4.02"),
                    &format!("{riso} {tap} {adc} 4.32"),
                );
        }
        if resistive {
            s = s.replace("CDUT hi low 100n", "RDUT hi low 100");
        }
        s += "Cfba1 afbm aip 100p\nCfba2 afbp aim 100p\nCfbb1 bfbm bip 100p\nCfbb2 bfbp bim 100p\n";
        s+=&format!(".control\nset klu\nset filetype=ascii\nset numdgt=17\nop\nwrite {name}.raw all\nprint v(xa.mid) v(xb.mid) v(aop) v(aom) v(bop) v(bom) v(afbp) v(afbm) v(bfbp) v(bfbm) v(acin)\nquit\n.endc\n.end\n");
        if run(name, s) {
            println!("Verified seed available: {name}.raw");
        }
    }
}
