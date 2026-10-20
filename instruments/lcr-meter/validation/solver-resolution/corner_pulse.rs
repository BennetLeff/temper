use std::{
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
fn rows(p: &str) -> Result<Vec<Vec<f64>>, String> {
    let t = fs::read_to_string(p).map_err(|e| e.to_string())?;
    let mut r = Vec::new();
    for l in t.lines().skip(1) {
        let v = l
            .split_whitespace()
            .map(|s| s.parse::<f64>().map_err(|e| e.to_string()))
            .collect::<Result<Vec<_>, _>>()?;
        if !v.is_empty() {
            if v.iter().any(|x| !x.is_finite()) {
                return Err("nonfinite data".into());
            }
            r.push(v)
        }
    }
    if r.is_empty() {
        return Err("empty data".into());
    }
    Ok(r)
}
fn main() {
    let base = fs::read_to_string("5k_resistor.cir")
        .unwrap()
        .split(".control")
        .next()
        .unwrap()
        .replace("SIN(0.3 0.3 50k)", "");
    let mut out=String::from("case,cf_pf,fixture_pf,afe_v,fda_v,status,mid_a,mid_b,delta_mv,overshoot_pct,last_outside_1pct_ns,adc_min_v,adc_max_v\n");
    for cf in [0, 10] {
        for fixture in [0, 25, 100] {
            for afe in [11.4, 12.0, 12.6] {
                for fda in [4.75, 5.0, 5.25] {
                    let n = format!("corner_cf{cf}_cp{fixture}_afe{afe:.1}_fda{fda:.2}");
                    let mut s = base
                        .replace("Vp vp 0 12", &format!("Vp vp 0 {afe}"))
                        .replace("Vn vn 0 -12", &format!("Vn vn 0 -{afe}"))
                        .replace("V5 v5 0 5", &format!("V5 v5 0 {fda}"));
                    s = s.replace(
                        "CF low tia 0.000000000000000000000001",
                        &format!(
                            "CF low tia {}",
                            if cf == 0 { 1e-24 } else { cf as f64 * 1e-12 }
                        ),
                    );
                    s+=&format!("Cfixture hi low {}\nItest hi low PULSE(0 1u 1u 1n 1n 5u 12u)\n.control\nset klu\nset wr_singlescale\nset wr_vecnames\nset filetype=ascii\nop\nwrite {n}_op.raw all\nwrdata {n}_op.dat v(xa.mid) v(xb.mid) v(source) v(hi) v(low) v(tia) v(aop) v(aom) v(bop) v(bom)\ntran 1n 10u 0 1n\nwrdata {n}_tran.dat v(hi) v(low) v(tia) v(highbuf) v(lowbuf) v(aadc_p) v(aadc_m) v(badc_p) v(badc_m)\nquit\n.endc\n.end\n",if fixture==0{1e-24}else{fixture as f64*1e-12});
                    fs::write(format!("{n}.cir"), s).unwrap();
                    let file = fs::File::create(format!("{n}.log")).unwrap();
                    let mut child = Command::new(std::env::var("NGSPICE").unwrap_or_else(|_| "ngspice".into()))
                        .args(["-b", &format!("{n}.cir")])
                        .stdout(Stdio::from(file.try_clone().unwrap()))
                        .stderr(Stdio::from(file))
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
                    let result = (|| -> Result<String, String> {
                        if timeout {
                            return Err("timeout".into());
                        }
                        let log = fs::read_to_string(format!("{n}.log")).unwrap();
                        if log.contains("Error") || log.contains("aborted") {
                            return Err("simulator error".into());
                        }
                        let op = rows(&format!("{n}_op.dat"))?;
                        if op.len() != 1 {
                            return Err("OP rowcount".into());
                        }
                        let expected = fda / (2. + 1e-6);
                        if (op[0][1] - expected).abs() > 1e-6 || (op[0][2] - expected).abs() > 1e-6
                        {
                            return Err(format!(
                                "false DC MID {} {} expected {expected}",
                                op[0][1], op[0][2]
                            ));
                        }
                        let tr = rows(&format!("{n}_tran.dat"))?;
                        if (tr.last().unwrap()[0] - 10e-6).abs() > 1e-12 {
                            return Err("incomplete transient".into());
                        }
                        let near = |t: f64| {
                            tr.iter()
                                .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
                                .unwrap()
                        };
                        let b = near(0.9e-6)[3];
                        let delta = near(5.9e-6)[3] - b;
                        let mut overshoot = 0f64;
                        let mut last = 1.001e-6;
                        for r in tr.iter().filter(|r| r[0] >= 1.001e-6 && r[0] < 5.9e-6) {
                            let v = (r[3] - b) / delta;
                            overshoot = overshoot.max(v - 1.);
                            if (v - 1.).abs() > 0.01 {
                                last = r[0]
                            }
                        }
                        let lo = tr
                            .iter()
                            .flat_map(|r| r[6..10].iter())
                            .copied()
                            .fold(f64::INFINITY, f64::min);
                        let hi = tr
                            .iter()
                            .flat_map(|r| r[6..10].iter())
                            .copied()
                            .fold(f64::NEG_INFINITY, f64::max);
                        if lo < 0.1 || hi > fda - 0.1 {
                            return Err("ADC headroom".into());
                        }
                        Ok(format!(
                            "PASS,{:.9},{:.9},{:.6},{:.3},{:.3},{:.6},{:.6}",
                            op[0][1],
                            op[0][2],
                            delta * 1e3,
                            overshoot * 100.,
                            (last - 1.001e-6) * 1e9,
                            lo,
                            hi
                        ))
                    })();
                    let status = match result {
                        Ok(v) => v,
                        Err(e) => format!("FAIL:{e},,,,,,,"),
                    };
                    println!("{n} {status}");
                    out += &format!("{n},{cf},{fixture},{afe},{fda},{status}\n");
                    fs::write("corner-results.csv", &out).unwrap();
                }
            }
        }
    }
}
