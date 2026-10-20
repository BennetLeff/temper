use std::{
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
fn main() {
    let base = fs::read_to_string("partition.cir").unwrap();
    let (head, ctl) = base.split_once(".control").unwrap();
    let mut comps = Vec::new();
    let mut directives = String::new();
    for (i, l) in head.lines().enumerate() {
        if i == 0 || l.starts_with(['.', '*']) {
            directives += l;
            directives.push(10 as char);
        } else {
            comps.push(l.to_string());
        }
    }
    for n in 0..10 {
        let mut c = comps.clone();
        if n == 0 {
            c.reverse();
        } else {
            c.sort_by_key(|l| {
                let mut h = 14695981039346656037u64 ^ n;
                for b in l.bytes() {
                    h = (h ^ b as u64).wrapping_mul(1099511628211);
                }
                h
            });
        }
        let name = format!("order{n}");
        let d = format!(
            "{directives}{}\n.control{}",
            c.join("\n"),
            ctl.replace("partition.raw", &format!("{name}.raw"))
        );
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
            if start.elapsed() > Duration::from_secs(5) {
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
            break;
        }
    }
}
