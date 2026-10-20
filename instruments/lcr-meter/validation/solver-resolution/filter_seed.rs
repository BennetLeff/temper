use std::{
    collections::{HashMap, HashSet},
    env, fs,
};
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(
        a.len(),
        4,
        "usage: filter_seed full-op.raw circuit.cir seed.inc"
    );
    let circuit = fs::read_to_string(&a[2]).unwrap();
    let mut model_nodes: HashMap<String, HashSet<String>> = HashMap::new();
    for line in circuit.lines() {
        let p: Vec<_> = line.split_whitespace().collect();
        if p.first()
            .is_some_and(|v| v.eq_ignore_ascii_case(".include"))
            && p[1].ends_with(".lib")
        {
            let lib = fs::read_to_string(p[1]).unwrap();
            let mut model = String::new();
            for line in lib.lines() {
                let p: Vec<_> = line.split_whitespace().collect();
                if p.is_empty() {
                    continue;
                }
                if p[0].eq_ignore_ascii_case(".subckt") {
                    model = p[1].to_lowercase();
                } else if p[0].eq_ignore_ascii_case(".ends") {
                    model.clear();
                } else if !model.is_empty() && p[0].starts_with(['R', 'r']) {
                    model_nodes
                        .entry(model.clone())
                        .or_default()
                        .extend([p[1].to_lowercase(), p[2].to_lowercase()]);
                }
            }
        }
    }
    let mut allowed = HashSet::new();
    for line in circuit.lines() {
        let p: Vec<_> = line.split_whitespace().collect();
        if p.is_empty() {
            continue;
        }
        if p[0].starts_with(['R', 'r']) {
            allowed.insert(format!("v({})", p[1].to_lowercase()));
            allowed.insert(format!("v({})", p[2].to_lowercase()));
        }
        if p[0].starts_with(['X', 'x']) {
            if let Some(nodes) = model_nodes.get(&p.last().unwrap().to_lowercase()) {
                for node in nodes {
                    allowed.insert(format!("v({}.{})", p[0].to_lowercase(), node));
                }
            }
        }
    }
    let raw = fs::read_to_string(&a[1]).unwrap();
    let (head, vals) = raw.split_once("Values:\n").unwrap();
    assert!(head.contains("No. Points: 1"), "requires exactly one OP");
    let var = head.split_once("Variables:\n").unwrap().1;
    let names: Vec<_> = var
        .lines()
        .map(|l| {
            let f: Vec<_> = l.split_whitespace().collect();
            (f[1], f[2])
        })
        .collect();
    let values: Vec<f64> = vals
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| l.split_whitespace().last().unwrap().parse().unwrap())
        .collect();
    assert_eq!(names.len(), values.len());
    let mut out=String::from("* Generated initial guesses from a converged OP; released after initial iteration.\n* Only top-level and vendor-subcircuit resistor endpoints: KLU cannot add absent diagonal entries.\n* No vendor model edits, forced ICs, supplies, or circuit alterations.\n");
    let mut count = 0;
    for ((name, kind), value) in names.iter().zip(values) {
        assert!(value.is_finite());
        if *kind == "voltage" && allowed.contains(*name) {
            out += &format!(".nodeset {name}={value:.15e}\n");
            count += 1;
        }
    }
    assert!(count > 0);
    fs::write(&a[3], out).unwrap();
    println!("wrote {count} initial voltage guesses");
}
