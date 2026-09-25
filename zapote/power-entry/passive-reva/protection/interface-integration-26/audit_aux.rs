//! Compare the compiled AUX insertion with Rev11 and the verified Rev19 pin graph.
//!
//! This checks exported connectivity, not source behavior, part ratings, or ERC.

use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;

type Pin = (String, String);
type PinSet = BTreeSet<Pin>;

#[derive(Debug)]
enum Sexpr {
    Atom(String),
    List(Vec<Sexpr>),
}

fn parse_sexpr(input: &str) -> Result<Sexpr, String> {
    fn parse_one(chars: &[char], at: &mut usize) -> Result<Sexpr, String> {
        while chars.get(*at).is_some_and(|c| c.is_whitespace()) {
            *at += 1;
        }
        match chars.get(*at) {
            Some('(') => {
                *at += 1;
                let mut children = Vec::new();
                loop {
                    while chars.get(*at).is_some_and(|c| c.is_whitespace()) {
                        *at += 1;
                    }
                    match chars.get(*at) {
                        Some(')') => {
                            *at += 1;
                            return Ok(Sexpr::List(children));
                        }
                        None => return Err("unclosed list".into()),
                        _ => children.push(parse_one(chars, at)?),
                    }
                }
            }
            Some(')') => Err("unexpected closing parenthesis".into()),
            Some('"') => {
                *at += 1;
                let mut value = String::new();
                loop {
                    match chars.get(*at) {
                        Some('"') => {
                            *at += 1;
                            return Ok(Sexpr::Atom(value));
                        }
                        Some('\\') => {
                            *at += 1;
                            let escaped = chars.get(*at).ok_or("trailing escape")?;
                            value.push(*escaped);
                            *at += 1;
                        }
                        Some(c) => {
                            value.push(*c);
                            *at += 1;
                        }
                        None => return Err("unclosed quoted string".into()),
                    }
                }
            }
            Some(_) => {
                let start = *at;
                while chars
                    .get(*at)
                    .is_some_and(|c| !c.is_whitespace() && *c != '(' && *c != ')')
                {
                    *at += 1;
                }
                Ok(Sexpr::Atom(chars[start..*at].iter().collect()))
            }
            None => Err("unexpected end of file".into()),
        }
    }

    let chars: Vec<char> = input.chars().collect();
    let mut at = 0;
    let root = parse_one(&chars, &mut at)?;
    if chars[at..].iter().any(|c| !c.is_whitespace()) {
        return Err("trailing data".into());
    }
    Ok(root)
}

fn children<'a>(expr: &'a Sexpr, name: &'a str) -> impl Iterator<Item = &'a Sexpr> {
    let list = match expr {
        Sexpr::List(list) => list.as_slice(),
        Sexpr::Atom(_) => &[],
    };
    list.iter().filter(move |item| {
        matches!(item, Sexpr::List(parts) if matches!(parts.first(), Some(Sexpr::Atom(head)) if head == name))
    })
}

fn atom_field(expr: &Sexpr, name: &str) -> Result<String, String> {
    let field = children(expr, name)
        .next()
        .ok_or_else(|| format!("missing {name}"))?;
    match field {
        Sexpr::List(parts) => match parts.get(1) {
            Some(Sexpr::Atom(value)) => Ok(value.clone()),
            _ => Err(format!("{name} is not an atom")),
        },
        Sexpr::Atom(_) => Err(format!("{name} is not a list")),
    }
}

struct Graph {
    components: BTreeSet<String>,
    pins: BTreeMap<Pin, String>,
}

fn graph(text: &str) -> Result<Graph, String> {
    let root = parse_sexpr(text)?;
    let components = children(&root, "components")
        .next()
        .ok_or("missing components section")?;
    let mut refs = BTreeMap::new();
    let mut ids = BTreeSet::new();
    for comp in children(components, "comp") {
        let reference = atom_field(comp, "ref")?;
        let path = children(comp, "sheetpath")
            .next()
            .ok_or("missing sheetpath")?;
        let id = atom_field(path, "names")?
            .split("::")
            .last()
            .ok_or("empty sheetpath")?
            .to_string();
        if refs.insert(reference, id.clone()).is_some() || !ids.insert(id) {
            return Err("duplicate component reference or identity".into());
        }
    }
    let nets = children(&root, "nets")
        .next()
        .ok_or("missing nets section")?;
    let mut pins = BTreeMap::new();
    for net in children(nets, "net") {
        let name = atom_field(net, "name")?;
        for node in children(net, "node") {
            let reference = atom_field(node, "ref")?;
            let id = refs
                .get(&reference)
                .ok_or_else(|| format!("unknown component {reference}"))?;
            let pin = (id.clone(), atom_field(node, "pin")?);
            if pins.insert(pin.clone(), name.clone()).is_some() {
                return Err(format!("duplicate exported pin {pin:?}"));
            }
        }
    }
    Ok(Graph {
        components: ids,
        pins,
    })
}

fn pin_group(graph: &Graph, name: &str) -> PinSet {
    graph
        .pins
        .iter()
        .filter(|(_, net)| net.as_str() == name)
        .map(|(pin, _)| pin.clone())
        .collect()
}

fn partition(pins: &BTreeMap<Pin, String>) -> BTreeSet<PinSet> {
    let mut groups: BTreeMap<&str, PinSet> = BTreeMap::new();
    for (pin, net) in pins {
        groups.entry(net).or_default().insert(pin.clone());
    }
    groups.into_values().collect()
}

fn expected_clamp(text: &str) -> Result<BTreeMap<Pin, String>, String> {
    let mut out = BTreeMap::new();
    for line in text.lines() {
        let mut parts = line.split('\t');
        let reference = parts.next().ok_or("missing reference")?;
        let pin = parts.next().ok_or("missing pin")?;
        let net = parts.next().ok_or("missing net")?;
        if parts.next().is_some() {
            return Err(format!("extra TSV column: {line}"));
        }
        let key = (
            format!("clamp.{}", reference.to_lowercase()),
            pin.to_string(),
        );
        if out.insert(key, net.to_string()).is_some() {
            return Err(format!("duplicate TSV pin: {line}"));
        }
    }
    Ok(out)
}

fn verify(
    baseline: &Graph,
    candidate: &Graph,
    expected: &BTreeMap<Pin, String>,
) -> Result<(), String> {
    let clamp_ids: BTreeSet<String> = expected.keys().map(|(id, _)| id.clone()).collect();
    if baseline.components.len() != 136 || clamp_ids.len() != 14 {
        return Err("unexpected baseline or clamp component count".into());
    }
    let union: BTreeSet<String> = baseline.components.union(&clamp_ids).cloned().collect();
    if candidate.components != union {
        return Err("candidate component identities differ from Rev11 + Rev19".into());
    }

    let clamp_pins: BTreeMap<Pin, String> = candidate
        .pins
        .iter()
        .filter(|(pin, _)| clamp_ids.contains(&pin.0))
        .map(|(pin, net)| (pin.clone(), net.clone()))
        .collect();
    if clamp_pins.len() != 39 || clamp_pins.keys().ne(expected.keys()) {
        return Err("clamp pin identity/count differs from Rev19".into());
    }
    if partition(&clamp_pins) != partition(expected) {
        return Err("clamp pin connectivity partition differs from Rev19".into());
    }

    let header = ("aux".to_string(), "1".to_string());
    let baseline_old: BTreeMap<Pin, String> = baseline
        .pins
        .iter()
        .filter(|(pin, _)| *pin != &header)
        .map(|(pin, net)| (pin.clone(), net.clone()))
        .collect();
    let candidate_old: BTreeMap<Pin, String> = candidate
        .pins
        .iter()
        .filter(|(pin, _)| baseline.components.contains(&pin.0) && *pin != &header)
        .map(|(pin, net)| (pin.clone(), net.clone()))
        .collect();
    if baseline_old.keys().ne(candidate_old.keys())
        || partition(&baseline_old) != partition(&candidate_old)
    {
        return Err("Rev11 pin connectivity changed beyond AUX header insertion".into());
    }

    let raw: PinSet = [
        ("aux", "1"),
        ("clamp.u1", "5"),
        ("clamp.q1", "2"),
        ("clamp.r4", "1"),
        ("clamp.c1", "1"),
    ]
    .into_iter()
    .map(|(id, pin)| (id.to_string(), pin.to_string()))
    .collect();
    if pin_group(candidate, "AUX_RAW") != raw {
        return Err("AUX_RAW is not confined to source header and clamp input".into());
    }
    let mut protected = pin_group(baseline, "AUX_15V_IN");
    if !protected.remove(&header) {
        return Err("Rev11 AUX header pin not found".into());
    }
    protected.extend(
        [
            ("clamp.u1", "2"),
            ("clamp.r1", "2"),
            ("clamp.r2", "1"),
            ("clamp.c4", "1"),
        ]
        .into_iter()
        .map(|(id, pin)| (id.to_string(), pin.to_string())),
    );
    if pin_group(candidate, "AUX_PROTECTED") != protected {
        return Err("not every Rev11 AUX consumer is on the protected rail".into());
    }
    let mut hot_return = pin_group(baseline, "PFC_BUS_MINUS");
    hot_return.extend(
        expected
            .iter()
            .filter(|(_, net)| net.as_str() == "HOT_GND")
            .map(|(pin, _)| pin.clone()),
    );
    if pin_group(candidate, "PFC_BUS_MINUS") != hot_return {
        return Err("clamp return is not the established Rev11 HOT return".into());
    }
    for (net, pin) in [
        ("SERVICE_RESET_N_OPEN", ("clamp.u1", "6")),
        ("CLAMP_FLT_OBSERVE_OPEN", ("clamp.u1", "10")),
        ("CLAMP_ENOUT_OBSERVE_OPEN", ("clamp.u1", "11")),
    ] {
        let singleton: PinSet = [(pin.0.to_string(), pin.1.to_string())].into();
        if pin_group(candidate, net) != singleton {
            return Err(format!("{net} is not the intended open boundary"));
        }
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 {
        return Err("usage: audit_aux BASELINE.net CANDIDATE.net REV19.tsv".into());
    }
    let baseline = graph(&fs::read_to_string(&args[1]).map_err(|e| e.to_string())?)?;
    let candidate = graph(&fs::read_to_string(&args[2]).map_err(|e| e.to_string())?)?;
    let expected = expected_clamp(&fs::read_to_string(&args[3]).map_err(|e| e.to_string())?)?;
    verify(&baseline, &candidate, &expected)?;
    println!("PASS: 136 preserved Rev11 components + 14 Rev19 clamp components; 39 clamp pins and AUX insertion verified");
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("FAIL: {error}");
        std::process::exit(1);
    }
}
