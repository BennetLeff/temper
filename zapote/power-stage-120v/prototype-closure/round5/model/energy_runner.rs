//! Finite stored-energy catch/fault convergence; no incoming AC or fuse arc model.
use std::{env, fs, path::Path, process::Command};
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 3);
    let tpl = fs::read_to_string(&a[1]).unwrap();
    let out = Path::new(&a[2]);
    fs::create_dir(out).unwrap();
    let fields = [
        "vbus_pk",
        "catch_pk",
        "catch_current_pk",
        "catch_i2t",
        "current_pk",
        "vcap_pk",
        "energy_residual",
    ];
    let mut csv = format!(
        "case,step_ns,delay_us,catch_l_uh,tank_r,initial_ct_v,short,complete,{}\n",
        fields.join(",")
    );
    for step in [50., 25.] {
        for delay in [2., 20.] {
            for cl in [1., 3.] {
                for r in [0.02, 2.] {
                    for vc in [-640., 640.] {
                        for short in [0, 1] {
                            let name = format!("s{step}-d{delay}-l{cl}-r{r}-v{vc}-f{short}");
                            let folder = out.join(&name);
                            fs::create_dir(&folder).unwrap();
                            let mut d = tpl.clone();
                            for (k, v) in [
                                ("VB", "198".into()),
                                ("IL", "85.551".into()),
                                ("VC", vc.to_string()),
                                ("L", "140u".into()),
                                ("R", r.to_string()),
                                ("TD", format!("{delay}u")),
                                ("STEP", format!("{step}n")),
                                ("CL", format!("{cl}u")),
                                ("SHORT", short.to_string()),
                            ] {
                                d = d.replace(&format!("@{k}@"), &v);
                            }
                            fs::write(folder.join("input.cir"), d).unwrap();
                            let p = Command::new("/opt/homebrew/bin/ngspice")
                                .args(["-b", "input.cir"])
                                .current_dir(&folder)
                                .output()
                                .unwrap();
                            let log = String::from_utf8_lossy(&p.stdout).to_string()
                                + &String::from_utf8_lossy(&p.stderr);
                            fs::write(folder.join("run.log"), &log).unwrap();
                            let vals: Vec<_> = fields
                                .iter()
                                .map(|f| {
                                    log.lines()
                                        .find(|l| l.starts_with(f))
                                        .and_then(|l| l.split('=').nth(1))
                                        .and_then(|v| v.split_whitespace().next())
                                        .unwrap_or("NaN")
                                })
                                .collect();
                            let ok = p.status.success()
                                && !log.to_lowercase().contains("timestep too small")
                                && !vals.contains(&"NaN");
                            csv += &format!(
                                "{name},{step},{delay},{cl},{r},{vc},{short},{ok},{}\n",
                                vals.join(",")
                            );
                            fs::write(out.join("results.csv"), &csv).unwrap();
                        }
                    }
                }
            }
        }
    }
}
