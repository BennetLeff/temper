use std::{collections::{BTreeMap, BTreeSet}, fs};

fn field(line: &str, key: &str) -> String {
    let marker = format!("({key} \"");
    line.split_once(&marker).and_then(|(_, tail)| tail.split_once('"'))
        .map(|(value, _)| value.to_string())
        .unwrap_or_else(|| panic!("missing {key} in {line}"))
}

fn main() {
    let text = fs::read_to_string("build/default.net").expect("compiled Atopile netlist");
    for part in ["SN74LVC1G08DBVR", "TPS389001DSER", "SN74HCS74PWR",
                 "ISO7741FDWR", "TPS3431SDRBR", "SN74LVC1G17DBVR"] {
        assert!(text.contains(&format!("(part \"{part}\")")), "missing compiled MPN {part}");
    }
    let mut nets: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut current: Option<String> = None;
    for line in text.lines().map(str::trim) {
        if line.starts_with("(net ") {
            current = line.split_once("(name \"").and_then(|(_, tail)| tail.split_once('"'))
                .map(|(name, _)| name.to_string());
            if let Some(name) = &current { nets.entry(name.clone()).or_default(); }
        } else if let Some(name) = &current {
            if line.starts_with("(node ") {
                let node = format!("{}.{}", field(line, "ref"), field(line, "pin"));
                nets.get_mut(name).unwrap().insert(node);
            }
            if line.ends_with(")))") { current = None; }
        }
    }
    let has = |n: &str, expected: &[&str]| {
        let actual = nets.get(n).unwrap_or_else(|| panic!("net missing: {n}"));
        let wanted: BTreeSet<_> = expected.iter().map(|s| s.to_string()).collect();
        assert_eq!(actual, &wanted, "unexpected pin membership on {n}");
    };
    let contains = |n: &str, expected: &[&str]| {
        let actual = nets.get(n).unwrap_or_else(|| panic!("net missing: {n}"));
        for node in expected { assert!(actual.contains(*node), "{n} missing node {node}"); }
    };
    contains("selv3v3", &["U25.1", "U25.3", "U25.5", "U26.5", "U30.1"]);
    contains("selv_gnd", &["U25.4", "U25.9", "U26.3"]);
    has("source_validated_heartbeat", &["U26.2", "U31.1"]);
    has("wd_wdi", &["U25.6", "U26.4", "U32.1"]);
    has("wd_cwd", &["U25.2", "U27.1"]);
    has("source_watchdog_good", &["U1.2", "U25.7", "U25.8", "U30.2"]);
    has("source_reset_good", &["U1.1", "U7.1"]);
    has("source_health", &["U2.4", "U4.1"]);
    has("source_clear_n", &["U4.4", "U5.1", "U10.1"]);
    has("permit_tx", &["U5.5", "U6.4", "U14.1"]);
    has("hot_permit_rx", &["U6.13", "U15.1"]);
    println!("PASS: compiled watchdog producer joins source latch; exact critical nets and single pull-up verified");
}
