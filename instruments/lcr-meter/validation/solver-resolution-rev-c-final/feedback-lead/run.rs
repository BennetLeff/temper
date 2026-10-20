#[path = "../strict_order.rs"]
mod strict_order;
use std::{
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
fn main() {
    let mut summary = String::from("case,status,load,lead_nh,corner,cf_pf,afe_v,fda_v,order\n");
    for load in ["open", "coil"] {
        for lead in [10, 20, 50] {
            for corner in [0, -1, 1] {
                let cf = 100. * (1. + 0.05 * corner as f64);
                let afe = 12. * (1. + 0.05 * corner as f64);
                let fda = 5. * (1. + 0.05 * corner as f64);
                let name = format!("{load}_lead{lead}_corner{corner}");
                let source = if load == "open" {
                    "../c100_open.cir"
                } else {
                    "../c100_coil50u.cir"
                };
                let original = fs::read_to_string(source).unwrap();
                let mut s = original.split_once(".control").unwrap().0.to_string();
                s = s
                    .replace(".include models/", ".include ../models/")
                    .replace(".include final-seed.inc", ".include ../final-seed.inc")
                    .replace("RF low tia 100", "RF low rf_end 100")
                    .replace("CF low tia 100p", &format!("CF low rf_end {cf}p"))
                    .replace("Chi hi 0 0.000000000000000000000001", "Chi hi 0 100p")
                    .replace("Clo low 0 0.000000000000000000000001", "Clo low 0 100p")
                    .replace("Vp vp 0 12", &format!("Vp vp 0 {afe}"))
                    .replace("Vn vn 0 -12", &format!("Vn vn 0 -{afe}"))
                    .replace("V5 v5 0 5", &format!("V5 v5 0 {fda}"));
                assert!(s.contains("RF low rf_end 100"));
                assert!(s.contains("Chi hi 0 100p") && s.contains("Clo low 0 100p"));
                s += &format!("Lfeedback rf_end tia {lead}n\n");
                let idut = if load == "open" {
                    "(v(hi)-v(low))/1e12"
                } else {
                    "i(LDUT)"
                };
                s+=&format!(".control\nset klu\nset filetype=ascii\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\nop\nwrite {name}_op.raw all\ntran 1n 20u 0 1n\nlet irg=(v(source)-v(hi))/100\nlet irf=(v(low)-v(rf_end))/100\nlet idut={idut}\nlet ihout=-i(v.x6b.x_h3.vh_h3)\nlet ilout=-i(v.x7b.x_h3.vh_h3)\nlet itout=-i(v.x7a.x_h3.vh_h3)\nwrdata {name}_tran.dat v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(rf_end) v(aadc_p) v(aadc_m) v(badc_p) v(badc_m) irg i(Lfeedback) irf idut ihout ilout itout\nquit\n.endc\n.end\n");
                let ordered = strict_order::find_order(&format!("init-{name}"), &s, 64);
                let (order, s) = match ordered {
                    Ok(v) => v,
                    Err(e) => {
                        summary +=
                            &format!("{name},FAIL:{e},{load},{lead},{corner},{cf},{afe},{fda},\n");
                        fs::write("run-results.csv", &summary).unwrap();
                        continue;
                    }
                };
                fs::write(format!("{name}.cir"), s).unwrap();
                for suffix in ["_op.raw", "_tran.dat"] {
                    let _ = fs::remove_file(format!("{name}{suffix}"));
                }
                let f = fs::File::create(format!("{name}.log")).unwrap();
                let mut child = Command::new(
                    std::env::var("NGSPICE").unwrap_or("/opt/homebrew/bin/ngspice".into()),
                )
                .args(["-b", &format!("{name}.cir")])
                .stdout(Stdio::from(f.try_clone().unwrap()))
                .stderr(Stdio::from(f))
                .spawn()
                .unwrap();
                let start = Instant::now();
                let mut timeout = false;
                while child.try_wait().unwrap().is_none() {
                    if start.elapsed() > Duration::from_secs(120) {
                        child.kill().unwrap();
                        child.wait().unwrap();
                        timeout = true;
                        break;
                    }
                    thread::sleep(Duration::from_millis(50));
                }
                let result = (|| -> Result<(), String> {
                    if timeout {
                        return Err("timeout".into());
                    }
                    strict_order::true_op(&format!("{name}_op.raw"))?;
                    let log = fs::read_to_string(format!("{name}.log")).unwrap();
                    if log.contains("Error") || log.contains("aborted") {
                        return Err("analysis error".into());
                    }
                    let t = fs::read_to_string(format!("{name}_tran.dat"))
                        .map_err(|e| e.to_string())?;
                    let mut count = 0;
                    let mut last = 0.;
                    for l in t.lines().skip(1) {
                        let row = l
                            .split_whitespace()
                            .map(|v| v.parse::<f64>().map_err(|e| e.to_string()))
                            .collect::<Result<Vec<_>, _>>()?;
                        if row.len() != 18 || !row.iter().all(|v| v.is_finite()) {
                            return Err("invalid row".into());
                        }
                        last = row[0];
                        count += 1;
                    }
                    if count < 20000 || (last - 20e-6).abs() > 1e-12 {
                        return Err("incomplete transient".into());
                    }
                    Ok(())
                })();
                let status = match result {
                    Ok(()) => "PASS".to_string(),
                    Err(e) => format!("FAIL:{e}"),
                };
                println!("{name} {status}");
                summary +=
                    &format!("{name},{status},{load},{lead},{corner},{cf},{afe},{fda},{order}\n");
                fs::write("run-results.csv", &summary).unwrap();
            }
        }
    }
}
