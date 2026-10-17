//! Generate exact paired decks and run the executable production-core harness.
use std::{env, fs, path::Path, process::Command};
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 4);
    let tpl = fs::read_to_string(&a[1]).unwrap();
    let out = Path::new(&a[2]);
    fs::create_dir(out).unwrap();
    let mut cases = String::from(
        "case,mode,vrms,tank_r,branch_ohm,catch_l_uH,fault,step_us,guard_us,end_s,exit_success\n",
    );
    for (name, mode, v, r, rp, l, fault) in [
        ("nominal", "study", 120., 2., 25., 1., 0),
        ("low-loss", "study", 120., 0.02, 25., 3., 0),
        ("catch-short", "study", 140., 2., 23.75, 1., 1),
        ("bus-short", "study", 140., 2., 23.75, 3., 2),
        ("stale", "stale", 120., 2., 25., 1., 0),
        ("capture", "capture", 120., 2., 25., 1., 0),
        ("proof-open", "proof-open", 120., 2., 25., 1., 0),
        ("bypass-open", "bypass-open", 120., 2., 25., 1., 0),
        ("bad-post", "bad-post", 120., 2., 25., 1., 0),
        ("inhibited", "inhibited", 120., 2., 25., 1., 0),
    ] {
        for step in [0.625, 0.3125] {
            let id = format!("{name}-{step}us");
            let deck = out.join(format!("{id}.cir"));
            let mut text = tpl.clone();
            for (k, val) in [
                ("VRMS", v.to_string()),
                ("RT", r.to_string()),
                ("CL", format!("{l}u")),
                ("RP1", rp.to_string()),
                ("RP2", rp.to_string()),
                ("FAULT", fault.to_string()),
                ("FT", ".4".into()),
                ("STEP", format!("{step}u")),
                ("END", ".6".into()),
            ] {
                text = text.replace(&format!("@{k}@"), &val);
            }
            fs::write(&deck, text).unwrap();
            let o = Command::new(&a[3])
                .arg(&deck)
                .arg(out.join(&id))
                .args([
                    mode,
                    &r.to_string(),
                    &v.to_string(),
                    &rp.to_string(),
                    &rp.to_string(),
                    "20",
                    ".6",
                ])
                .output()
                .unwrap();
            fs::write(
                out.join(format!("{id}.process.log")),
                String::from_utf8_lossy(&o.stdout).to_string()
                    + &String::from_utf8_lossy(&o.stderr),
            )
            .unwrap();
            cases += &format!(
                "{id},{mode},{v},{r},{rp},{l},{fault},{step},20,.6,{}\n",
                o.status.success()
            );
            fs::write(out.join("cases.csv"), &cases).unwrap();
        }
    }
}
