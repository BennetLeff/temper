//! Generate exact paired decks and run the executable production-core harness.
use std::{env, fs, path::Path, process::Command, thread};
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 4);
    let tpl = fs::read_to_string(&a[1]).unwrap();
    let out = Path::new(&a[2]);
    fs::create_dir(out).unwrap();
    let mut cases = String::from(
        "case,mode,vrms,tank_r,branch_ohm,catch_l_uH,fault,step_us,guard_us,end_s,exit_success\n",
    );
    let mut jobs = Vec::new();
    for (name, mode, v, r, rp, l, fault) in [
        ("nominal", "study", 120., 2., 25., 1., 0),
        ("low-loss", "study", 120., 0.02, 25., 3., 0),
        ("demand-pause", "demand-pause", 120., 2., 25., 1., 0),
        ("no-demand", "no-demand", 120., 2., 25., 1., 0),
        ("catch-short", "study", 140., 2., 23.75, 1., 1),
        ("bus-short", "study", 140., 2., 23.75, 3., 2),
        ("stale", "stale", 120., 2., 25., 1., 0),
        ("readback", "readback", 120., 2., 25., 1., 0),
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
                ("FT", "1.0".into()),
                ("STEP", format!("{step}u")),
                ("END", "1.3".into()),
            ] {
                text = text.replace(&format!("@{k}@"), &val);
            }
            fs::write(&deck, text).unwrap();
            jobs.push((
                id,
                deck,
                vec![
                    mode.to_owned(),
                    r.to_string(),
                    v.to_string(),
                    rp.to_string(),
                    rp.to_string(),
                    "20".into(),
                    "1.3".into(),
                ],
                format!("{mode},{v},{r},{rp},{l},{fault},{step},20,1.3"),
            ));
        }
    }
    // Independent ngspice processes, two at a time. Their global C runtime
    // must never share a process; output ordering remains the case order.
    let binary = &a[3];
    for batch in jobs.chunks(2) {
        let results = thread::scope(|scope| {
            let handles: Vec<_> = batch
                .iter()
                .map(|(id, deck, args, row)| {
                    scope.spawn(move || {
                        let o = Command::new(binary)
                            .arg(deck)
                            .arg(out.join(id))
                            .args(args)
                            .output()
                            .unwrap();
                        fs::write(
                            out.join(format!("{id}.process.log")),
                            String::from_utf8_lossy(&o.stdout).to_string()
                                + &String::from_utf8_lossy(&o.stderr),
                        )
                        .unwrap();
                        format!("{id},{row},{}\n", o.status.success())
                    })
                })
                .collect();
            handles
                .into_iter()
                .map(|h| h.join().unwrap())
                .collect::<Vec<_>>()
        });
        for result in results {
            cases += &result;
        }
        fs::write(out.join("cases.csv"), &cases).unwrap();
    }
}
