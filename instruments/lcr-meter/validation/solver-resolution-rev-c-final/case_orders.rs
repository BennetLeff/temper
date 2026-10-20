use std::{
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
fn main() {
    for target in [
        "revc_100r_coil50u",
        "revc_5k_resistor",
        "revc_100k_resistor",
    ] {
        let base = fs::read_to_string(format!("{target}.cir")).unwrap();
        let (head, ctl) = base.split_once(".control").unwrap();
        let mut comps = Vec::new();
        let mut directives = String::new();
        for (i, l) in head.lines().enumerate() {
            if i == 0 || l.starts_with(['.', '*']) {
                directives += l;
                directives.push('\n')
            } else {
                comps.push(l.to_string());
            }
        }
        for n in 0..24 {
            let mut c = comps.clone();
            if n == 0 {
                c.reverse()
            } else {
                c.sort_by_key(|l| {
                    let mut h = 14695981039346656037u64 ^ n;
                    for b in l.bytes() {
                        h = (h ^ b as u64).wrapping_mul(1099511628211);
                    }
                    h
                });
            }
            let name = format!("{target}-order{n}");
            let circuit = format!("{directives}{}\n", c.join("\n"));
            let d=format!("{circuit}.control\nset klu\nset filetype=ascii\nop\nwrite {name}.raw all\nquit\n.endc\n.end\n");
            fs::write(format!("{name}.cir"), d).unwrap();
            let f = fs::File::create(format!("{name}.log")).unwrap();
            let mut child = Command::new("/opt/homebrew/bin/ngspice")
                .args(["-b", &format!("{name}.cir")])
                .stdout(Stdio::from(f.try_clone().unwrap()))
                .stderr(Stdio::from(f))
                .spawn()
                .unwrap();
            let start = Instant::now();
            while child.try_wait().unwrap().is_none() {
                if start.elapsed() > Duration::from_secs(3) {
                    child.kill().unwrap();
                    child.wait().unwrap();
                    break;
                }
                thread::sleep(Duration::from_millis(50));
            }
            let g = Command::new("./op_guard")
                .arg(format!("{name}.raw"))
                .output()
                .unwrap();
            println!(
                "{name}: {} {}",
                g.status,
                String::from_utf8_lossy(&g.stdout)
            );
            if g.status.success() {
                fs::write(
                    format!("{target}-selected.cir"),
                    format!(
                        "{circuit}.control{}",
                        ctl.replace(target, &format!("{target}-selected"))
                    ),
                )
                .unwrap();
                break;
            }
        }
    }
}
