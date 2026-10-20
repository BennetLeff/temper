mod strict_order;
use std::{fs, process::Command};
fn main() {
    for (n, src, cf) in [
        ("cm100r", "revc_100r_cap100n", false),
        ("cm5k_cf10", "newton-5k-selected", true),
        ("cm100k", "newton-100k-selected", false),
    ] {
        let mut s = fs::read_to_string(format!("{src}.cir"))
            .unwrap()
            .split(".control")
            .next()
            .unwrap()
            .replace("SIN(0.3 0.3 50k)", "")
            .replace(
                "Vcm cm 0 2.048",
                "Vcm cm 0 DC 2.048 PULSE(2.048 2.058 1u 10n 10n 5u 12u)",
            );
        if cf {
            s = s.replace("CF low tia 0.000000000000000000000001", "CF low tia 10p")
        }
        s+=&format!(".control\nset klu\nset wr_singlescale\nset wr_vecnames\nset filetype=ascii\nop\nwrite {n}_op.raw all\ntran 1n 10u 0 1n\nlet acm=(v(aadc_p)+v(aadc_m))/2\nlet bcm=(v(badc_p)+v(badc_m))/2\nlet adiff=v(aadc_p)-v(aadc_m)\nlet bdiff=v(badc_p)-v(badc_m)\nwrdata {n}_tran.dat v(cm) acm bcm adiff bdiff v(highbuf) v(lowbuf) v(tia)\nquit\n.endc\n.end\n");
        let (_, s) = strict_order::find_order(&format!("init-{n}"), &s, 48).unwrap();
        fs::write(format!("{n}.cir"), s).unwrap();
        let o = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
            .args(["-b", &format!("{n}.cir")])
            .output()
            .unwrap();
        let mut log = o.stdout;
        log.extend(o.stderr);
        fs::write(format!("{n}.log"), &log).unwrap();
        let t = String::from_utf8_lossy(&log);
        assert!(!t.contains("Error") && !t.contains("aborted"), "{n} failed");
        let status = Command::new("./op_guard")
            .arg(format!("{n}_op.raw"))
            .status()
            .unwrap();
        assert!(status.success());
        println!("{n} complete");
    }
}
