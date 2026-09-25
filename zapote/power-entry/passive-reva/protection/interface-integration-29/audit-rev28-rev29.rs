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

#[test]
fn compiled_rev29_adds_watchdog_and_supervisor_qualified_latch_clear() {
    let old_path = env::var("REV28_NET").expect("set REV28_NET");
    let new_path = env::var("REV29_NET").expect("set REV29_NET");
    let old = graph(&fs::read_to_string(old_path).expect("Rev28 netlist")).expect("parse Rev28");
    let new = graph(&fs::read_to_string(new_path).expect("Rev29 netlist")).expect("parse Rev29");

    let added: BTreeSet<String> = [
        "protection.hot_watchdog",
        "protection.hot_watchdog_cwd",
        "protection.hot_watchdog_bypass",
        "protection.receiver_session_active_pd",
        "protection.heartbeat_pd",
        "protection.watchdog_fault_pullup",
        "protection.session_qualified_pulse_pd",
        "protection.watchdog_clear_and",
        "protection.watchdog_clear_bypass",
        "protection.watchdog_clear_pd",
    ]
    .into_iter()
    .map(str::to_string)
    .collect();
    assert_eq!(new.components, old.components.union(&added).cloned().collect());

    let mut expected = old.pins.clone();
    for (pin, net) in [
        (("protection.latch".to_string(), "12".to_string()), "logic5"),
        (("protection.latch".to_string(), "11".to_string()), "SESSION_QUALIFIED_PULSE_5V"),
        (("protection.latch".to_string(), "13".to_string()), "watchdog_clear_qualified"),
        (("protection.latch".to_string(), "9".to_string()), "HOT_LINK_GOOD_QUALIFIED"),
        (("protection.link_good_input_pd".to_string(), "1".to_string()), "HOT_LINK_GOOD_QUALIFIED"),
        (("protection.link_clear_and".to_string(), "2".to_string()), "HOT_LINK_GOOD_QUALIFIED"),
    ] {
        expected.insert(pin, net.to_string());
    }
    for (id, pin, net) in [
        ("protection.hot_watchdog", "1", "logic5"),
        ("protection.hot_watchdog", "2", "cwd"),
        ("protection.hot_watchdog", "3", "RECEIVER_SESSION_ACTIVE"),
        ("protection.hot_watchdog", "4", "PFC_BUS_MINUS"),
        ("protection.hot_watchdog", "5", "logic5"),
        ("protection.hot_watchdog", "6", "VALIDATED_HEARTBEAT_5V"),
        ("protection.hot_watchdog", "7", "watchdog_ok_n"),
        ("protection.hot_watchdog", "8", "watchdog_ok_n"),
        ("protection.hot_watchdog", "9", "PFC_BUS_MINUS"),
        ("protection.hot_watchdog_cwd", "1", "cwd"),
        ("protection.hot_watchdog_cwd", "2", "PFC_BUS_MINUS"),
        ("protection.hot_watchdog_bypass", "1", "logic5"),
        ("protection.hot_watchdog_bypass", "2", "PFC_BUS_MINUS"),
        ("protection.receiver_session_active_pd", "1", "RECEIVER_SESSION_ACTIVE"),
        ("protection.receiver_session_active_pd", "2", "PFC_BUS_MINUS"),
        ("protection.heartbeat_pd", "1", "VALIDATED_HEARTBEAT_5V"),
        ("protection.heartbeat_pd", "2", "PFC_BUS_MINUS"),
        ("protection.watchdog_fault_pullup", "1", "logic5"),
        ("protection.watchdog_fault_pullup", "2", "watchdog_ok_n"),
        ("protection.watchdog_clear_and", "1", "rails_ok"),
        ("protection.watchdog_clear_and", "2", "watchdog_ok_n"),
        ("protection.watchdog_clear_and", "3", "PFC_BUS_MINUS"),
        ("protection.watchdog_clear_and", "4", "watchdog_clear_qualified"),
        ("protection.watchdog_clear_and", "5", "logic5"),
        ("protection.watchdog_clear_pd", "1", "watchdog_clear_qualified"),
        ("protection.watchdog_clear_pd", "2", "PFC_BUS_MINUS"),
        ("protection.watchdog_clear_bypass", "1", "logic5"),
        ("protection.watchdog_clear_bypass", "2", "PFC_BUS_MINUS"),
        ("protection.session_qualified_pulse_pd", "1", "SESSION_QUALIFIED_PULSE_5V"),
        ("protection.session_qualified_pulse_pd", "2", "PFC_BUS_MINUS"),
    ] {
        expected.insert((id.to_string(), pin.to_string()), net.to_string());
    }
    for (pin, wanted_net) in &expected {
        assert_eq!(new.pins.get(pin), Some(wanted_net), "pin {pin:?}");
    }
    for pin in new.pins.keys() {
        assert!(expected.contains_key(pin), "unexpected pin {pin:?}");
    }

    assert_eq!(
        pin_group(&new, "watchdog_ok_n"),
        [
            ("protection.hot_watchdog".into(), "7".into()),
            ("protection.hot_watchdog".into(), "8".into()),
            ("protection.watchdog_fault_pullup".into(), "2".into()),
            ("protection.watchdog_clear_and".into(), "2".into()),
        ].into_iter().collect()
    );
    assert_eq!(
        pin_group(&new, "watchdog_clear_qualified"),
        [
            ("protection.latch".into(), "13".into()),
            ("protection.watchdog_clear_and".into(), "4".into()),
            ("protection.watchdog_clear_pd".into(), "1".into()),
        ].into_iter().collect()
    );
    assert_eq!(
        pin_group(&new, "HOT_LINK_GOOD_QUALIFIED"),
        [
            ("protection.latch".into(), "9".into()),
            ("protection.link_good_input_pd".into(), "1".into()),
            ("protection.link_clear_and".into(), "2".into()),
        ].into_iter().collect()
    );
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
