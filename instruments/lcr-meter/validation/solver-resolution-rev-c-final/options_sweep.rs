use std::{
    fs,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
fn main() {
    let base = fs::read_to_string("partition.cir").unwrap();
    for (name, opt) in [
        ("pivot1", "pivrel=1"),
        ("pivot01", "pivrel=0.1"),
        ("pivot006", "pivrel=1e-6"),
        ("itl", "itl1=1000"),
        ("gmin9", "gmin=1e-9"),
        ("gmin15", "gmin=1e-15"),
        ("shunt12", "rshunt=1e12"),
        ("shunt18", "rshunt=1e18"),
        ("loose", "reltol=1e-3 abstol=1e-12 vntol=1e-6"),
        ("noop", "noopiter"),
    ] {
        let deck = base
            .replace(".control", &format!(".options {opt}\n.control"))
            .replace("partition.raw", &format!("{name}.raw"));
        fs::write(format!("{name}.cir"), deck).unwrap();
        let f = fs::File::create(format!("{name}.log")).unwrap();
        let mut child = Command::new("/opt/homebrew/bin/ngspice")
            .args(["-b", &format!("{name}.cir")])
            .stdout(Stdio::from(f.try_clone().unwrap()))
            .stderr(Stdio::from(f))
            .spawn()
            .unwrap();
        let start = Instant::now();
        while child.try_wait().unwrap().is_none() {
            if start.elapsed() > Duration::from_secs(8) {
                child.kill().unwrap();
                child.wait().unwrap();
                break;
            }
            thread::sleep(Duration::from_millis(100));
        }
        let guard = Command::new("./op_guard")
            .arg(format!("{name}.raw"))
            .output()
            .unwrap();
        println!(
            "{name}: {} {}",
            guard.status,
            String::from_utf8_lossy(&guard.stdout)
        );
    }
}
