use std::{collections::HashMap, fs, process::Command};
fn raw(p: &str) -> HashMap<String, f64> {
    let t = fs::read_to_string(p).unwrap();
    let (h, v) = t.split_once("Values:\n").unwrap();
    let n: Vec<_> = h
        .split_once("Variables:\n")
        .unwrap()
        .1
        .lines()
        .map(|l| l.split_whitespace().nth(1).unwrap().to_string())
        .collect();
    let v: Vec<f64> = v
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.split_whitespace().last().unwrap().parse().unwrap())
        .collect();
    n.into_iter().zip(v).collect()
}
fn main() {
    let base = fs::read_to_string("final-cap.cir").unwrap();
    let a = raw("standalone-a.raw");
    let b = raw("standalone-b.raw");
    let mut afe = base.split_once("Rai1").unwrap().0.to_string();
    afe+=&format!("Vaip aip 0 {}\nVaim aim 0 {}\nVbip bip 0 {}\nVbim bim 0 {}\nRai1 highbuf aip 1k\nRai2 lowbuf aim 1k\nRbi1 lowbuf bip 1k\nRbi2 tia bim 1k\n",a["v(aip)"],a["v(aim)"],b["v(bip)"],b["v(bim)"]);
    afe = afe.replace(".include old-offset-nodeset.inc\n", "");
    afe +=
        ".control\nset klu\nset filetype=ascii\nop\nwrite afe-loaded.raw all\nquit\n.endc\n.end\n";
    fs::write("afe-loaded.cir", afe).unwrap();
    let r = Command::new("/opt/homebrew/bin/ngspice")
        .args(["-b", "afe-loaded.cir"])
        .output()
        .unwrap();
    fs::write("afe-loaded.log", [r.stdout, r.stderr].concat()).unwrap();
    assert!(Command::new("./filter_seed")
        .args(["afe-loaded.raw", "afe-loaded.cir", "afe-loaded.inc"])
        .status()
        .unwrap()
        .success());
    let mut seed = fs::read_to_string("afe-loaded.inc").unwrap();
    for tag in ["a", "b"] {
        for l in fs::read_to_string(format!("standalone-{tag}.inc"))
            .unwrap()
            .lines()
        {
            if l.contains(&format!("v(x{tag}.")) || l.contains(&format!("v({tag}")) {
                seed += l;
                seed += "\n";
            }
        }
    }
    fs::write("partition-seed.inc", seed).unwrap();
    fs::write(
        "partition.cir",
        base.replace("old-offset-nodeset.inc", "partition-seed.inc")
            .replace("final-cap.raw", "partition.raw"),
    )
    .unwrap();
}
