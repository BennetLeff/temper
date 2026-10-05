//! Conditional vendor-device references. Each local 4x4 is used separately.
use std::{env, fs, path::Path, process::Command};
fn matrix(p: &Path) -> [[f64; 4]; 4] {
    let s = fs::read_to_string(p).unwrap();
    let v = s
        .split("\"L_nH\":")
        .nth(1)
        .unwrap()
        .split("\"tets\"")
        .next()
        .unwrap();
    let n: Vec<f64> = v
        .split(|c: char| !(c.is_ascii_digit() || ".-+eE".contains(c)))
        .filter_map(|t| t.parse().ok())
        .collect();
    assert_eq!(n.len(), 16);
    let mut a = [[0.; 4]; 4];
    for i in 0..4 {
        for j in 0..4 {
            a[i][j] = n[4 * i + j];
        }
    }
    let mut l = [[0.; 4]; 4];
    for i in 0..4 {
        for j in 0..=i {
            assert!((a[i][j] - a[j][i]).abs() < 1e-8);
            let z = a[i][j] - (0..j).map(|k| l[i][k] * l[j][k]).sum::<f64>();
            l[i][j] = if i == j {
                assert!(z > 0.);
                z.sqrt()
            } else {
                z / l[j][j]
            };
        }
    }
    a
}
fn main() {
    let args: Vec<_> = env::args().collect();
    assert_eq!(args.len(), 4, "runner ROOT OUT VENDOR");
    let root = Path::new(&args[1]);
    let out = Path::new(&args[2]);
    fs::create_dir(out).unwrap();
    let base = root.join("zapote/power-stage-120v/prototype-closure");
    let tpl = fs::read_to_string(base.join("round5/model/device.cir")).unwrap();
    let mut csv=String::from("case,leg,step_ns,bus_v,current_a,dt_ns,direction,complete,vds_ls_die_pk,vds_hs_die_pk,vgs_ls_die_max,vgs_hs_die_max,vgs_ls_at_partner,vgs_hs_at_partner\n");
    for (leg, file) in [
        ("A", "A-e4-h1-matrix.json"),
        ("B", "B-e4-f4-h1-matrix.json"),
    ] {
        let a = matrix(&base.join("round4/fields/evidence").join(file));
        for step in [0.4, 0.2] {
            for dir in [0, 1] {
                for dt in [396.6, 488.0] {
                    let name = format!("{leg}-h{step}-d{dir}-dt{dt}");
                    let folder = out.join(&name);
                    fs::create_dir(&folder).unwrap();
                    let mut pars =
                        format!(".param VBUS=198 IL=37 DIR={dir} DT={dt}n TRMAX={step}n\n");
                    for i in 0..4 {
                        pars += &format!(".param LP{}={}n\n", i + 1, a[i][i]);
                        for j in i + 1..4 {
                            pars += &format!(
                                ".param K{}{}={}\n",
                                i + 1,
                                j + 1,
                                a[i][j] / (a[i][i] * a[j][j]).sqrt()
                            );
                        }
                    }
                    let deck = tpl.replace("@VENDOR@", &args[3]).replace("@PARAMS@", &pars);
                    fs::write(folder.join("input.cir"), deck).unwrap();
                    fs::write(folder.join(".spiceinit"), "set ngbehavior=psa\n").unwrap();
                    let result = Command::new("/opt/homebrew/bin/ngspice")
                        .args(["-b", "input.cir"])
                        .current_dir(&folder)
                        .output()
                        .unwrap();
                    let log = String::from_utf8_lossy(&result.stdout).to_string()
                        + &String::from_utf8_lossy(&result.stderr);
                    fs::write(folder.join("run.log"), &log).unwrap();
                    let fields = [
                        "vds_ls_die_pk",
                        "vds_hs_die_pk",
                        "vgs_ls_die_max",
                        "vgs_hs_die_max",
                        "vgs_ls_at_partner",
                        "vgs_hs_at_partner",
                    ];
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
                    let complete = result.status.success()
                        && !log.contains("Timestep too small")
                        && !vals.contains(&"NaN");
                    csv += &format!(
                        "{name},{leg},{step},198,37,{dt},{dir},{complete},{}\n",
                        vals.join(",")
                    );
                    fs::write(out.join("results.csv"), &csv).unwrap();
                    assert!(complete, "failed {name}");
                }
            }
        }
    }
}
