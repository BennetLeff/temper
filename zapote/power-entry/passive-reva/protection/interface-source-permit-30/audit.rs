use std::{collections::{BTreeMap, BTreeSet}, fs};

fn main() {
    let netlist = fs::read_to_string("build/default.net").expect("compiled Atopile netlist");
    for part in ["SN74LVC1G08DBVR", "TPS389001DSER", "SN74HCS74PWR", "ISO7741FDWR"] {
        assert!(netlist.contains(&format!("(part \"{part}\")")), "missing compiled part {part}");
    }

    let mut nets: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut current: Option<String> = None;
    for line in netlist.lines() {
        let line = line.trim();
        if line.starts_with("(net ") {
            current = line.split_once("(name \"").and_then(|(_, tail)| tail.split_once('\"'))
                .map(|(name, _)| name.to_string());
            if let Some(name) = &current { nets.entry(name.clone()).or_default(); }
        } else if let Some(net) = &current {
            if line.starts_with("(node ") {
                let refdes = field(line, "ref");
                let pin = field(line, "pin");
                nets.get_mut(net).unwrap().insert(format!("{refdes}.{pin}"));
            }
            if line.ends_with(")))") { current = None; }
        }
    }

    let expected = fs::read_to_string("netlist.tsv").expect("compiled-netlist contract");
    let mut checked = 0;
    for line in expected.lines().map(str::trim).filter(|l| !l.is_empty() && !l.starts_with('#')) {
        let (net, nodes) = line.split_once(" | ").expect("contract row");
        let actual = nets.get(net).unwrap_or_else(|| panic!("compiled net absent: {net}"));
        let wanted: BTreeSet<_> = nodes.split(',').map(str::to_string).collect();
        assert_eq!(actual, &wanted, "compiled connectivity differs on net {net}");
        checked += wanted.len();
    }
    assert!(checked >= 40);
    println!("PASS: {checked} compiled pin/net assignments and all four MPN identities verified");
}

fn field(line: &str, key: &str) -> String {
    let marker = format!("({key} \"");
    line.split_once(&marker).and_then(|(_, tail)| tail.split_once('\"'))
        .map(|(value, _)| value.to_string()).unwrap_or_else(|| panic!("missing {key} in {line}"))
}
