use std::{fs, process::Command};
fn main() {
    let base = fs::read_to_string("final-cap.cir").unwrap();
    let afe = fs::read_to_string("old-offset-nodeset.inc").unwrap();
    let mut seed = afe
        .lines()
        .filter(|l| {
            !l.contains("(xa.")
                && !l.contains("(xb.")
                && !l.starts_with(".nodeset v(a")
                && !l.starts_with(".nodeset v(b")
        })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n";
    for (tag, high, low) in [
        ("a", 0.000654718577, 0.000201501531),
        ("b", 0.000201501531, 0.000100193),
    ] {
        let from = if tag == "a" { "Rai1" } else { "Rbi1" };
        let until = if tag == "a" { "Rbi1" } else { "Cfba1" };
        let mut block = base
            .split_once(from)
            .unwrap()
            .1
            .split_once(until)
            .unwrap()
            .0
            .to_string();
        block = format!("{from}{block}");
        for l in base.lines().filter(|l| l.starts_with(&format!("Cfb{tag}"))) {
            block += l;
            block += "\n";
        }
        let head=format!("Isolated FDA actual final topology to initialize coupled full circuit\n.include models/ths4551.lib\n.options reltol=1e-5 abstol=1e-12 vntol=1e-7 method=gear\nV5 v5 0 5\nVcm cm 0 2.048\nVhigh highbuf 0 {high}\nVlow lowbuf 0 {low}\nVtia tia 0 {low}\n");
        let deck=format!("{head}{block}.control\nset klu\nset filetype=ascii\nop\nwrite standalone-{tag}.raw all\nprint v(x{tag}.mid)\nquit\n.endc\n.end\n");
        fs::write(format!("standalone-{tag}.cir"), deck).unwrap();
        let r = Command::new("/opt/homebrew/bin/ngspice")
            .args(["-b", &format!("standalone-{tag}.cir")])
            .output()
            .unwrap();
        fs::write(
            format!("standalone-{tag}.log"),
            [r.stdout, r.stderr].concat(),
        )
        .unwrap();
        let status = Command::new("./filter_seed")
            .args([
                &format!("standalone-{tag}.raw"),
                &format!("standalone-{tag}.cir"),
                &format!("standalone-{tag}.inc"),
            ])
            .status()
            .unwrap();
        assert!(status.success());
        seed += &fs::read_to_string(format!("standalone-{tag}.inc")).unwrap();
    }
    fs::write("composite-seed.inc", seed).unwrap();
    let deck = base
        .replace("old-offset-nodeset.inc", "composite-seed.inc")
        .replace("final-cap.raw", "composite.raw");
    fs::write("composite.cir", deck).unwrap();
}
