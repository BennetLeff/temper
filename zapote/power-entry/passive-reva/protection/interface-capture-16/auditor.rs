//! Small, dependency-free auditor for the revision-16 KiCad export fixtures.
//!
//! This is deliberately independent of the schematic generator: it reads the
//! exported netlist and the pin/net contract TSV, then checks the graph that
//! KiCad actually exported.  It is a review fixture, not a production ERC.

use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct Pin {
    reference: String,
    pin: String,
}

fn norm(s: &str) -> String {
    let mut v = s.trim().trim_matches('"').to_string();
    while v.starts_with('/') {
        v.remove(0);
    }
    v
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Sexp {
    Atom(String),
    List(Vec<Sexp>),
}

fn parse_sexp(text: &str) -> Result<Sexp, String> {
    let c: Vec<char> = text.chars().collect();
    let mut i = 0usize;
    fn one(c: &[char], i: &mut usize) -> Result<Sexp, String> {
        while *i < c.len() && c[*i].is_whitespace() {
            *i += 1;
        }
        if *i >= c.len() {
            return Err("unexpected end of S-expression".into());
        }
        if c[*i] == '(' {
            *i += 1;
            let mut xs = Vec::new();
            loop {
                while *i < c.len() && c[*i].is_whitespace() {
                    *i += 1;
                }
                if *i >= c.len() {
                    return Err("missing closing parenthesis".into());
                }
                if c[*i] == ')' {
                    *i += 1;
                    return Ok(Sexp::List(xs));
                }
                xs.push(one(c, i)?);
            }
        }
        if c[*i] == ')' {
            return Err("unexpected closing parenthesis".into());
        }
        if c[*i] == '"' {
            *i += 1;
            let mut s = String::new();
            while *i < c.len() {
                match c[*i] {
                    '"' => {
                        *i += 1;
                        return Ok(Sexp::Atom(s));
                    }
                    '\\' => {
                        *i += 1;
                        if *i >= c.len() {
                            return Err("unterminated escape".into());
                        }
                        s.push(c[*i]);
                        *i += 1;
                    }
                    ch => {
                        s.push(ch);
                        *i += 1;
                    }
                }
            }
            return Err("unterminated quoted atom".into());
        }
        let start = *i;
        while *i < c.len() && !c[*i].is_whitespace() && c[*i] != ')' && c[*i] != '(' {
            *i += 1;
        }
        Ok(Sexp::Atom(c[start..*i].iter().collect()))
    }
    let root = one(&c, &mut i)?;
    while i < c.len() && c[i].is_whitespace() {
        i += 1;
    }
    if i != c.len() {
        return Err("trailing data after S-expression root".into());
    }
    Ok(root)
}

fn head(x: &Sexp, h: &str) -> bool {
    matches!(x, Sexp::List(v) if matches!(v.first(), Some(Sexp::Atom(a)) if a == h))
}
fn n_field(x: &Sexp, h: &str) -> Option<String> {
    if let Sexp::List(v) = x {
        for y in v {
            if let Sexp::List(w) = y {
                if w.len() >= 2 && matches!(&w[0], Sexp::Atom(a) if a == h) {
                    if let Sexp::Atom(a) = &w[1] {
                        return Some(a.clone());
                    }
                }
            }
        }
    }
    None
}

fn parse_nets(text: &str) -> Result<BTreeMap<Pin, String>, String> {
    let root = parse_sexp(text)?;
    let top = match root {
        Sexp::List(v) => v,
        _ => return Err("root is not a list".into()),
    };
    let nets = top
        .iter()
        .find(|x| head(x, "nets"))
        .ok_or("missing (nets ...) section")?;
    let mut out = BTreeMap::new();
    if let Sexp::List(ns) = nets {
        for n in ns.iter().filter(|x| head(x, "net")) {
            let name = n_field(n, "name").ok_or("net missing name")?;
            if let Sexp::List(parts) = n {
                let mut node_count = 0usize;
                for node in parts.iter().filter(|x| head(x, "node")) {
                    node_count += 1;
                    let r = n_field(node, "ref").ok_or("node missing ref")?;
                    let p = n_field(node, "pin").ok_or("node missing pin")?;
                    let pin = Pin {
                        reference: r,
                        pin: p,
                    };
                    if out.insert(pin.clone(), norm(&name)).is_some() {
                        return Err(format!(
                            "duplicate exported pin {}.{}",
                            pin.reference, pin.pin
                        ));
                    }
                }
                if norm(&name).starts_with("unconnected-") && node_count != 1 {
                    return Err(format!(
                        "unconnected net {name} has {node_count} nodes (expected singleton)"
                    ));
                }
            }
        }
    }
    Ok(out)
}

fn component_refs(text: &str) -> BTreeSet<String> {
    let mut refs = BTreeSet::new();
    let Ok(Sexp::List(top)) = parse_sexp(text) else {
        return refs;
    };
    if let Some(Sexp::List(cs)) = top.iter().find(|x| head(x, "components")) {
        for comp in cs.iter().filter(|x| head(x, "comp")) {
            if let Some(r) = n_field(comp, "ref") {
                refs.insert(r);
            }
        }
    }
    refs
}

// Manufacturer pin-function tables, separately transcribed from the drawing
// generator. KiCad10 appends _<pin number> to custom-symbol pinfunction fields.
fn audit_functions(name: &str, text: &str) -> Result<(), String> {
    let and = ["A", "B", "GND", "Y", "VCC"];
    let latch = [
        "/CLR1", "D1", "CLK1", "/PRE1", "Q1", "/Q1", "GND", "/Q2", "Q2", "/PRE2", "CLK2", "D2",
        "/CLR2", "VCC",
    ];
    let tables: Vec<(&str, &[&str])> = if name == "clamp" {
        vec![
            (
                "U1",
                &[
                    "FB", "OUT", "SNS", "GATE", "VCC", "/SHDN", "GND", "UV", "GND", "/FLT",
                    "ENOUT", "TMR",
                ],
            ),
            ("Q1", &["G", "D", "S"]),
            ("D1", &["K", "A"]),
        ]
    } else {
        vec![
            ("U1", &and),
            ("U2", &and),
            ("U3", &latch),
            (
                "U4",
                &[
                    "VCC1", "GND1", "INA", "INB", "INC", "OUTD", "EN1", "GND1", "GND2", "EN2",
                    "IND", "OUTC", "OUTB", "OUTA", "GND2", "VCC2",
                ],
            ),
            ("U5", &and),
            ("U6", &latch),
            ("U7", &and),
        ]
    };
    let mut want = BTreeMap::new();
    for (r, names) in tables {
        for (i, n) in names.iter().enumerate() {
            want.insert(
                Pin {
                    reference: r.into(),
                    pin: (i + 1).to_string(),
                },
                n.to_string(),
            );
        }
    }
    fn visit(x: &Sexp, want: &mut BTreeMap<Pin, String>) -> Result<(), String> {
        if head(x, "node") {
            let p = Pin {
                reference: n_field(x, "ref").ok_or("missing ref")?,
                pin: n_field(x, "pin").ok_or("missing pin")?,
            };
            if let Some(expected) = want.remove(&p) {
                let actual = n_field(x, "pinfunction").ok_or("missing pinfunction")?;
                let plain = actual
                    .strip_suffix(&format!("_{}", p.pin))
                    .unwrap_or(&actual);
                if plain != expected {
                    return Err(format!(
                        "pin function {}.{} expected {expected}, found {actual}",
                        p.reference, p.pin
                    ));
                }
            }
        }
        if let Sexp::List(v) = x {
            for c in v {
                visit(c, want)?;
            }
        }
        Ok(())
    }
    visit(&parse_sexp(text)?, &mut want)?;
    if !want.is_empty() {
        return Err("missing manufacturer pin functions".into());
    }
    Ok(())
}

fn expected(path: &Path) -> Result<BTreeMap<Pin, String>, String> {
    let mut out = BTreeMap::new();
    for (n, line) in fs::read_to_string(path)
        .map_err(|e| e.to_string())?
        .lines()
        .enumerate()
    {
        let p: Vec<_> = line.split('\t').collect();
        if p.len() != 3 {
            return Err(format!("{}:{} malformed TSV", path.display(), n + 1));
        }
        let pin = Pin {
            reference: p[0].into(),
            pin: p[1].into(),
        };
        if out.insert(pin.clone(), norm(p[2])).is_some() {
            return Err(format!("duplicate expected {}.{}", pin.reference, pin.pin));
        }
    }
    Ok(out)
}

fn assert_contracts(name: &str, g: &BTreeMap<Pin, String>) -> Result<(), String> {
    let get = |r: &str, p: &str| {
        g.get(&Pin {
            reference: r.into(),
            pin: p.into(),
        })
        .cloned()
        .ok_or_else(|| format!("missing contract pin {}.{}", r, p))
    };
    let same = |pairs: &[(&str, &str)]| -> Result<(), String> {
        let first = get(pairs[0].0, pairs[0].1)?;
        for &(r, p) in &pairs[1..] {
            if get(r, p)? != first {
                return Err(format!("contract mismatch at {}.{}", r, p));
            }
        }
        Ok(())
    };
    let expect = |r: &str, p: &str, net: &str| -> Result<(), String> {
        if get(r, p)? != net {
            return Err(format!("{}.{p} is not on {net}", r));
        }
        Ok(())
    };
    if name == "clamp" {
        for (pin, net) in [
            ("1", "FB"),
            ("2", "AUX_PROTECTED"),
            ("3", "SNS"),
            ("4", "GATE_DRV"),
            ("5", "AUX_RAW"),
            ("6", "SERVICE_RESET_N"),
            ("7", "HOT_GND"),
            ("8", "UV"),
            ("9", "HOT_GND"),
            ("10", "FLT_TP"),
            ("11", "ENOUT_TP"),
            ("12", "TMR"),
        ] {
            expect("U1", pin, net)?;
        }
        expect("Q1", "2", "AUX_RAW")?;
        expect("Q1", "1", "Q_GATE")?;
        expect("C3", "1", "CG")?;
        same(&[("Q1", "3"), ("R1", "1"), ("U1", "3")])?;
        same(&[("Q1", "1"), ("R6", "2"), ("R7", "1"), ("D1", "2")])?;
        same(&[("R7", "2"), ("D1", "1"), ("C3", "1")])?;
        if get("R1", "2")? != get("U1", "2")? {
            return Err("protected output is not common to R1.2/U1.2".into());
        }
        expect("R2", "1", "AUX_PROTECTED")?;
        expect("C4", "1", "AUX_PROTECTED")?;
    } else if name == "reset" {
        // The source latch D input is the fixed 3V3 state; the HOT latch D
        // input is the independently-produced authorization state. A
        // fixed-high HOT D input would defeat the permission contract.
        if get("U3", "2")? != "SELV3V3" {
            return Err("source latch D1 is not tied to SELV3V3".into());
        }
        if get("U6", "2")? == "HOT_LOGIC5" {
            return Err("HOT latch D1 is fixed high".into());
        }
        // ISO7741 channels: A/B/C go source->hot, D returns hot->source.
        for (a, b) in [("3", "14"), ("4", "13"), ("5", "12"), ("11", "6")] {
            if get("U4", a)? == get("U4", b)? {
                return Err(format!(
                    "ISO7741 channel {}-{} is electrically shorted",
                    a, b
                ));
            }
        }
        expect("U4", "3", "COMMAND_TX")?;
        expect("U4", "4", "PERMIT_TX")?;
        expect("U4", "5", "RELAY_CMD")?;
        expect("U4", "11", "HOT_RESPONSE_TX")?;
        for (pin, net) in [
            ("1", "SELV3V3"),
            ("2", "SELV_GND"),
            ("6", "SELV_RESPONSE_RX"),
            ("7", "SELV3V3"),
            ("8", "SELV_GND"),
            ("9", "HOT_GND"),
            ("10", "HOT_LOGIC5"),
            ("12", "HOT_RELAY_CMD"),
            ("13", "HOT_PERMIT_RX"),
            ("14", "HOT_COMMAND_RX"),
            ("15", "HOT_GND"),
            ("16", "HOT_LOGIC5"),
        ] {
            expect("U4", pin, net)?;
        }
        // HOT clear gates both latches and the enable AND.
        same(&[("U5", "4"), ("U6", "1"), ("U6", "13"), ("U7", "2")])?;
        if get("U6", "2")? != get("U6", "9")? {
            return Err("dual HOT authorization latches disagree".into());
        }
        if get("U3", "1")? != get("U2", "4")? {
            return Err("source health does not reach reset AND".into());
        }
        if get("U4", "2")? == get("U4", "9")? {
            return Err("SELV and HOT grounds are merged through ISO7741".into());
        }
    }
    Ok(())
}

fn audit_one(dir: &Path, name: &str, expected_count: usize) -> Result<(), String> {
    let text = fs::read_to_string(dir.join(format!("{name}.net"))).map_err(|e| e.to_string())?;
    let actual = parse_nets(&text)?;
    audit_functions(name, &text)?;
    let want = expected(&dir.join(format!("{name}-expected.tsv")))?;
    if component_refs(&text).len() != expected_count {
        return Err(format!(
            "{name}: component count {} != {expected_count}",
            component_refs(&text).len()
        ));
    }
    for (pin, net) in &want {
        match actual.get(pin) {
            Some(found) if net == "NC" && found.starts_with("unconnected-") => {}
            Some(found) if found == net => {}
            Some(found) => {
                return Err(format!(
                    "{name}: {}.{} expected {net}, exported {found}",
                    pin.reference, pin.pin
                ))
            }
            None => {
                return Err(format!(
                    "{name}: exported netlist omits {}.{}",
                    pin.reference, pin.pin
                ))
            }
        }
    }
    for (pin, net) in &actual {
        if !want.contains_key(pin) {
            return Err(format!(
                "{name}: unexpected exported pin {}.{} on {net}",
                pin.reference, pin.pin
            ));
        }
    }
    assert_contracts(name, &actual)?;
    println!(
        "PASS {name}: {} pins, {expected_count} components",
        want.len()
    );
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let dir = args
        .iter()
        .find(|a| a.as_str() != "--self-test")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    if args.iter().any(|a| a == "--self-test") {
        self_tests();
        audit_one(&dir, "clamp", 14).expect("baseline clamp must pass before mutation");
        audit_one(&dir, "reset", 28).expect("baseline reset must pass before mutation");
        let clamp_text = fs::read_to_string(dir.join("clamp.net")).unwrap();
        assert!(audit_functions("clamp", &clamp_text.replace("VCC_5", "WRONG_5")).is_err());
        if dir.join("clamp.net").exists() {
            let clamp = parse_nets(&fs::read_to_string(dir.join("clamp.net")).unwrap()).unwrap();
            assert_contracts("clamp", &clamp).unwrap();
            let mut diode = clamp.clone();
            diode.insert(
                Pin {
                    reference: "D1".into(),
                    pin: "1".into(),
                },
                "Q_GATE".into(),
            );
            assert!(
                assert_contracts("clamp", &diode).is_err(),
                "clamp D1.1 -> Q_GATE mutation must fail"
            );
            let reset = parse_nets(&fs::read_to_string(dir.join("reset.net")).unwrap()).unwrap();
            assert_contracts("reset", &reset).unwrap();
            let mut fixed = reset.clone();
            fixed.insert(
                Pin {
                    reference: "U6".into(),
                    pin: "2".into(),
                },
                "HOT_LOGIC5".into(),
            );
            assert!(
                assert_contracts("reset", &fixed).is_err(),
                "HOT U6.2 fixed-high mutation must fail"
            );
            println!(
                "PASS live mutation tests: clamp diode endpoint and HOT D1 fixed-high rejected"
            );
        }
        return;
    }
    if let Err(e) = audit_one(&dir, "clamp", 14).and_then(|_| audit_one(&dir, "reset", 28)) {
        eprintln!("AUDIT FAILED: {e}");
        std::process::exit(1);
    }
}

fn self_tests() {
    let good = "(export\n (nets\n  (net\n   (name \"/SNS\")\n   (node\n    (ref \"Q1\")\n    (pin \"3\")\n   )\n   (node\n    (ref \"R1\")\n    (pin \"1\")\n   )\n   (node\n    (ref \"U1\")\n    (pin \"3\")\n   )\n  )\n )\n)";
    let parsed = parse_nets(good).expect("synthetic netlist parses");
    assert_eq!(
        parsed.get(&Pin {
            reference: "Q1".into(),
            pin: "3".into()
        }),
        Some(&"SNS".into())
    );
    let bad = good.replace("(pin \"3\")", "(pin \"2\")");
    let p = parse_nets(&bad).expect("mutation still parses");
    assert!(!p.contains_key(&Pin {
        reference: "Q1".into(),
        pin: "3".into()
    }));
    for invalid in ["(", ")", "(a))", "(a)(b)", "(a \"unterminated)"] {
        assert!(parse_sexp(invalid).is_err());
    }
    assert_eq!(
        parse_sexp(r#"("escaped\"quote")"#).unwrap(),
        Sexp::List(vec![Sexp::Atom("escaped\"quote".into())])
    );
    assert!(parse_nets(&good.replace("/SNS", "unconnected-probe")).is_err());
    assert!(parse_nets(
        &good
            .replace("R1", "Q1")
            .replace("(pin \"1\")", "(pin \"3\")")
    )
    .is_err());
    println!("PASS parser checks: escaped quote, malformed inputs, NC singleton and duplicate pin rejection");
}
