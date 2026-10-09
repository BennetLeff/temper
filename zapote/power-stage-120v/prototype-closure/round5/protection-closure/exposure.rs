//! Prescribed voltage-exposure sensitivity, NOT the joined source/rectifier plant.
use std::{env,fs,path::Path,process::Command};
fn metric(log: &str,key: &str)->f64 {
    log.lines().find_map(|l| {
        let (left,right)=l.split_once('=')?;
        (left.trim()==key).then(||right.split_whitespace().next().unwrap().parse::<f64>().unwrap())
    }).unwrap_or_else(||panic!("missing {key}"))
}
fn main() {
    let args:Vec<String>=env::args().collect();
    let out=Path::new(args.get(1).expect("output directory required"));
    fs::create_dir_all(out).unwrap();
    let r:f64=23.75; let volts=(36612.0*r).sqrt(); let hold:f64=8e-3;
    let mut csv=String::from("open_gaps,c_gap_f,rise_s,max_step_s,peak_w,analytic_peak_w,energy_j,analytic_energy_j,peak_relative_error,energy_relative_error,peak_above_4000w\n");
    for gaps in 0..=2 {
        for cap in [1e-11,1e-10,1e-9] {
            for rise in [1e-8,1e-7,1e-6] {
                for step in [1e-6,5e-7] {
                    let name=format!("g{gaps}-c{cap:e}-r{rise:e}-s{step:e}");
                    let mut deck=format!("* Conditional voltage exposure; no arc/fuse qualification\nV1 src 0 PWL(0 0 1u 0 {} {volts} {} {volts} {} 0)\n",1e-6+rise,1e-6+rise+hold,1e-6+2.0*rise+hold);
                    if gaps==0 { deck.push_str("Vlink src load 0\n"); }
                    else {
                        // Two identical series gap caps have Ceq=Cgap/2. Individual
                        // voltage sharing is NOT claimed: capacitance mismatch is unbounded.
                        deck.push_str(&format!("Cgap src load {}\n",cap/f64::from(gaps)));
                    }
                    deck.push_str(&format!("R1 load 0 {r}\nR2 load 0 {r}\n.options reltol=1e-8 abstol=1e-14 vntol=1e-10 trtol=1\n.tran {step} {} 0 {step}\n.meas tran peak MAX par('v(load)*v(load)/{r}')\n.meas tran energy INTEG par('v(load)*v(load)/{r}')\n.end\n",hold+2.0*rise+2e-5));
                    let path=out.join(format!("{name}.cir"));fs::write(&path,deck).unwrap();
                    let result=Command::new("ngspice").args(["-n","-b"]).arg(&path).output().unwrap();
                    let log=String::from_utf8(result.stdout).unwrap()+&String::from_utf8(result.stderr).unwrap();
                    fs::write(out.join(format!("{name}.log")),&log).unwrap();
                    assert!(result.status.success()&&!log.contains("aborted")&&!log.contains("failed"),"ngspice {name}: {log}");
                    let peak=metric(&log,"peak");let energy=metric(&log,"energy");
                    let (ap,ae)=if gaps==0 {(volts*volts/r,volts*volts/r*(hold+2.0*rise/3.0))} else {
                        let tau=r/2.0*cap/f64::from(gaps);
                        let factor=-(-rise/tau).exp_m1();
                        ((volts*tau/rise*factor).powi(2)/r,
                         2.0*volts*volts*tau*tau/(rise*rise*r)*(rise-tau*factor))
                    };
                    let pe=(peak/ap-1.0).abs();let ee=(energy/ae-1.0).abs();
                    assert!(pe<0.01&&ee<0.01,"oracle error {name}: peak{pe},energy{ee}");
                    csv.push_str(&format!("{gaps},{cap:e},{rise:e},{step:e},{peak:.9e},{ap:.9e},{energy:.9e},{ae:.9e},{pe:.9e},{ee:.9e},{}\n",peak>4000.0));
                }
            }
        }
    }
    fs::write(out.join("exposure.csv"),csv).unwrap();
    println!("PASS 54 prescribed-exposure cases; analytic RC oracle within1%; amplitude={volts} V,hold={hold}s; not full-plant or contact rating evidence");
}
