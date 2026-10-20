use std::{collections::HashMap, fs};
fn main() {
    let text = fs::read_to_string("old-offset-nodeset.inc").unwrap();
    let mut nodes: HashMap<String, f64> = text
        .lines()
        .filter_map(|l| {
            l.strip_prefix(".nodeset ")
                .and_then(|l| l.split_once('='))
                .map(|(a, b)| (a.to_string(), b.parse().unwrap()))
        })
        .collect();
    for (tag, ri) in [("adc-only", 3.3), ("dc22", 22.)] {
        let mut m = nodes.clone();
        for (p, high, low) in [("a", "highbuf", "lowbuf"), ("b", "lowbuf", "tia")] {
            let get = |n: &str| nodes[&format!("v({n})")];
            let op = get(&format!("{p}op"));
            let om = get(&format!("{p}om"));
            let vh = get(high);
            let vl = get(low);
            let fm = om - ri * (om - vh) / (2000. + ri);
            let fp = op - ri * (op - vl) / (2000. + ri);
            let inp = (vh * (1000. + ri) + om * 1000.) / (2000. + ri);
            let inn = (vl * (1000. + ri) + op * 1000.) / (2000. + ri);
            for (n, v) in [
                (format!("{p}fbm"), fm),
                (format!("{p}fbp"), fp),
                (format!("{p}adc_m"), fm),
                (format!("{p}adc_p"), fp),
            ] {
                m.insert(format!("v({n})"), v);
            }
            if ri != 3.3 {
                for (n, v) in [(format!("{p}ip"), inp), (format!("{p}im"), inn)] {
                    m.insert(format!("v({n})"), v);
                }
                let shift = ((inp + inn) - (get(&format!("{p}ip")) + get(&format!("{p}im")))) / 2.;
                for (n, v) in nodes.iter() {
                    if n.starts_with(&format!("v(x{p}.")) && *v > 0.9 && *v < 1.2 {
                        m.insert(n.clone(), v + shift);
                    }
                }
            }
        }
        let mut names: Vec<_> = m.keys().collect();
        names.sort();
        let mut s =
            String::from("* Analytic DC resistor-network seed adjustment; initial guesses only.\n");
        for n in names {
            s += &format!(".nodeset {n}={:.15e}\n", m[n]);
        }
        fs::write(format!("{tag}-seed.inc"), s).unwrap();
        let base = if ri == 3.3 { "stage-3p3" } else { "final-cap" };
        let deck = fs::read_to_string(format!("{base}.cir"))
            .unwrap()
            .replace("old-offset-nodeset.inc", &format!("{tag}-seed.inc"))
            .replace(&format!("write {base}.raw"), &format!("write {tag}.raw"));
        fs::write(format!("{tag}.cir"), deck).unwrap();
    }
    nodes.clear();
}
