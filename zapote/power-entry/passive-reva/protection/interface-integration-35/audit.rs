//! Audit the compiled Rev35 source-to-HOT-to-protection join.
//! This checks exported connectivity, not behavior, analog ratings, or ERC.

use std::collections::{BTreeMap, BTreeSet};
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

#[derive(Clone)]
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
    graph.pins.iter().filter(|(_, net)| net.as_str() == name)
        .map(|(pin, _)| pin.clone()).collect()
}

fn validate(g: &Graph, text: &str) -> Result<(), String> {
    if g.components.len() != 226 {
        return Err(format!("expected 226 component instances, got {}", g.components.len()));
    }
    if text.matches("(libsource (lib \"lib\") (part \"ISO7741FDWR\")").count() != 1
        || !g.components.contains("receiver.iso")
        || g.components.iter().filter(|id| id.as_str() == "receiver.iso" || id.as_str() == "source.isolator").count() != 1
    {
        return Err("integration must contain exactly one ISO7741F".into());
    }
    for duplicate in ["receiver.session_load_pd", "receiver.heartbeat_load_pd",
                      "receiver.session_pulse_load_pd", "receiver.arm_load_pd",
                      "source.permit_rx_pd", "source.unused_a_pd", "source.unused_c_pd"] {
        if g.components.contains(duplicate) { return Err(format!("duplicate fixture load: {duplicate}")); }
    }
    for (id, pin, net) in [
        ("source.source_latch", "5", "source_permit"),
        ("receiver.iso", "4", "source_permit"),
        ("receiver.iso", "13", "HOT_PERMIT_ISOLATED"),
        ("pfc.protection.permit_buf", "2", "HOT_PERMIT_ISOLATED"),
        ("receiver.session_buf", "4", "RECEIVER_SESSION_ACTIVE"),
        ("pfc.protection.hot_watchdog", "3", "RECEIVER_SESSION_ACTIVE"),
        ("receiver.heartbeat_buf", "4", "VALIDATED_HEARTBEAT_5V"),
        ("pfc.protection.hot_watchdog", "6", "VALIDATED_HEARTBEAT_5V"),
        ("receiver.session_pulse_buf", "4", "SESSION_QUALIFIED_PULSE_5V"),
        ("pfc.protection.latch", "11", "SESSION_QUALIFIED_PULSE_5V"),
        ("receiver.arm_buf", "4", "hot_arm"),
        ("pfc.protection.arm_buf", "2", "hot_arm"),
        ("pfc.protection.latch", "9", "HOT_LINK_GOOD_QUALIFIED"),
        ("receiver.rx", "27", "HOT_LINK_GOOD_QUALIFIED"),
        ("pfc.protection.sup_logic", "6", "hot_rails_ok"),
        ("receiver.reset_supervisor", "3", "hot_rails_ok"),
        ("source.watchdog", "7", "source_watchdog_good"),
        ("source.watchdog", "8", "source_watchdog_good"),
        ("source.source_latch", "1", "source_clear_n"),
    ] {
        if g.pins.get(&(id.into(), pin.into())).is_none_or(|actual| actual != net) {
            return Err(format!("{id}.{pin} must join {net}"));
        }
    }
    let watchdog_good: PinSet = [
        ("source.watchdog", "7"), ("source.watchdog", "8"),
        ("source.watchdog_good_pullup", "2"), ("source.and_reset_wd", "2"),
    ].into_iter().map(|(id, pin)| (id.into(), pin.into())).collect();
    if pin_group(g, "source_watchdog_good") != watchdog_good {
        return Err("source watchdog-good must have one pullup and no pulldown".into());
    }
    let permit_driver: PinSet = [
        ("receiver.iso", "13"), ("pfc.protection.permit_buf", "2"),
        ("pfc.protection.permit_input_pd", "1"), ("receiver.rx", "32"),
    ].into_iter().map(|(id, pin)| (id.into(), pin.into())).collect();
    if pin_group(g, "HOT_PERMIT_ISOLATED") != permit_driver {
        return Err("HOT permit must have one isolated driver and only the expected local loads".into());
    }
    let source_permit: PinSet = [
        ("source.source_latch", "5"), ("receiver.iso", "4"),
        ("source.permit_tx_pd", "1"),
    ].into_iter().map(|(id, pin)| (id.into(), pin.into())).collect();
    if pin_group(g, "source_permit") != source_permit {
        return Err("source permit must have only the latch, isolated receiver, and pulldown".into());
    }
    if g.pins.get(&(String::from("receiver.iso"), String::from("1")))
        == g.pins.get(&(String::from("receiver.iso"), String::from("16")))
        || g.pins.get(&(String::from("receiver.iso"), String::from("2")))
        == g.pins.get(&(String::from("receiver.iso"), String::from("9")))
    {
        return Err("SELV and HOT isolator supplies or grounds are shorted".into());
    }
    Ok(())
}

fn main() {
    let text = fs::read_to_string("build/default.net").expect("integrated netlist");
    let g = graph(&text).expect("parse compiled netlist");
    validate(&g, &text).expect("integrated pin graph");
    let mut wrong_net = g.clone();
    wrong_net.pins.insert(("receiver.iso".into(), "4".into()), "selv_gnd".into());
    assert!(validate(&wrong_net, &text).is_err(), "miswired permit mutation was accepted");
    let mut extra_iso = g.clone();
    extra_iso.components.insert("source.isolator".into());
    assert!(validate(&extra_iso, &text).is_err(), "duplicate isolator mutation was accepted");
    let mut bypass_pin = g.clone();
    bypass_pin.pins.insert(("pfc.control".into(), "1".into()), "HOT_PERMIT_ISOLATED".into());
    assert!(validate(&bypass_pin, &text).is_err(), "external permit bypass mutation was accepted");
    println!("PASS: {} components, {} nets; one isolator, source/HOT/PFC joins, three rejected faults",
        g.components.len(), g.pins.values().collect::<BTreeSet<_>>().len());
}
