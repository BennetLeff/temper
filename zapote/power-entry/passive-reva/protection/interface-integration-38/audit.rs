//! Exact-pin audit of the partial Rev38 isolation fixture.
//! This does not audit the eventual joined protection circuit or electrical limits.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;

#[derive(Debug)]
enum Sexp {
    Atom(String),
    List(Vec<Sexp>),
}

fn parse(input: &str) -> Result<Sexp, String> {
    fn one(bytes: &[u8], cursor: &mut usize) -> Result<Sexp, String> {
        while bytes.get(*cursor).is_some_and(u8::is_ascii_whitespace) {
            *cursor += 1;
        }
        match bytes.get(*cursor) {
            Some(b'(') => {
                *cursor += 1;
                let mut items = Vec::new();
                loop {
                    while bytes.get(*cursor).is_some_and(u8::is_ascii_whitespace) {
                        *cursor += 1;
                    }
                    match bytes.get(*cursor) {
                        Some(b')') => {
                            *cursor += 1;
                            return Ok(Sexp::List(items));
                        }
                        None => return Err("unclosed list".into()),
                        _ => items.push(one(bytes, cursor)?),
                    }
                }
            }
            Some(b'"') => {
                *cursor += 1;
                let mut value = Vec::new();
                loop {
                    match bytes.get(*cursor) {
                        Some(b'"') => {
                            *cursor += 1;
                            return String::from_utf8(value).map(Sexp::Atom).map_err(|e| e.to_string());
                        }
                        Some(b'\\') => {
                            *cursor += 1;
                            value.push(*bytes.get(*cursor).ok_or("trailing escape")?);
                            *cursor += 1;
                        }
                        Some(c) => {
                            *cursor += 1;
                            value.push(*c);
                        }
                        None => return Err("unclosed string".into()),
                    }
                }
            }
            Some(b')') => Err("unexpected close".into()),
            Some(_) => {
                let start = *cursor;
                while bytes.get(*cursor).is_some_and(|c| !c.is_ascii_whitespace() && *c != b'(' && *c != b')') {
                    *cursor += 1;
                }
                String::from_utf8(bytes[start..*cursor].to_vec())
                    .map(Sexp::Atom).map_err(|e| e.to_string())
            }
            None => Err("unexpected end".into()),
        }
    }
    let mut cursor = 0;
    let root = one(input.as_bytes(), &mut cursor)?;
    if input.as_bytes()[cursor..].iter().any(|c| !c.is_ascii_whitespace()) {
        return Err("trailing data".into());
    }
    Ok(root)
}

fn children<'a>(node: &'a Sexp, key: &'a str) -> impl Iterator<Item = &'a Sexp> {
    let items = match node {
        Sexp::List(items) => items.as_slice(),
        Sexp::Atom(_) => &[],
    };
    items.iter().filter(move |item| {
        matches!(item, Sexp::List(parts) if matches!(parts.first(), Some(Sexp::Atom(head)) if head == key))
    })
}

fn field(node: &Sexp, key: &str) -> Result<String, String> {
    match children(node, key).next() {
        Some(Sexp::List(parts)) => match parts.get(1) {
            Some(Sexp::Atom(value)) => Ok(value.clone()),
            _ => Err(format!("non-atom {key}")),
        },
        _ => Err(format!("missing {key}")),
    }
}

#[derive(Clone)]
struct Graph {
    parts: BTreeMap<String, String>,
    pins: BTreeMap<(String, String), String>,
}

fn graph(input: &str) -> Result<Graph, String> {
    let root = parse(input)?;
    let section = children(&root, "components").next().ok_or("missing components")?;
    let mut refs = BTreeMap::new();
    let mut parts = BTreeMap::new();
    for comp in children(section, "comp") {
        let reference = field(comp, "ref")?;
        let sheetpath = children(comp, "sheetpath").next().ok_or("missing sheetpath")?;
        let identity = field(sheetpath, "names")?.rsplit("::").next().ok_or("empty identity")?.to_owned();
        let libsource = children(comp, "libsource").next().ok_or("missing libsource")?;
        let part = field(libsource, "part")?;
        if refs.insert(reference, identity.clone()).is_some() || parts.insert(identity, part).is_some() {
            return Err("duplicate reference or identity".into());
        }
    }
    let section = children(&root, "nets").next().ok_or("missing nets")?;
    let mut pins = BTreeMap::new();
    for net in children(section, "net") {
        let name = field(net, "name")?;
        for node in children(net, "node") {
            let reference = field(node, "ref")?;
            let identity = refs.get(&reference).ok_or_else(|| format!("unknown reference {reference}"))?;
            let pin = (identity.clone(), field(node, "pin")?);
            if pins.insert(pin.clone(), name.clone()).is_some() {
                return Err(format!("duplicate pin {pin:?}"));
            }
        }
    }
    Ok(Graph { parts, pins })
}

fn members(g: &Graph, net: &str) -> BTreeSet<(String, String)> {
    g.pins.iter().filter(|(_, name)| name.as_str() == net)
        .map(|(pin, _)| pin.clone()).collect()
}

fn domain(id: &str, pin: &str) -> &'static str {
    match id {
        "iso_protocol" | "iso_feedback" if pin.parse::<u8>().is_ok_and(|n| n <= 8) => "SELV",
        "iso_protocol" | "iso_feedback" => "HOT",
        "c_iso1_selv" | "c_iso2_selv" | "source_permit_fb_pd" | "source_session_fb_pd" => "SELV",
        _ => "HOT",
    }
}

fn check(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 42 { return Err(format!("expected 42 parts, found {}", g.parts.len())); }
    for (id, part) in [
        ("rx", "AVR64DA32-E/PT"),
        ("iso_protocol", "ISO7741FDWR"),
        ("iso_feedback", "ISO7742FDWR"),
        ("reset_pulses", "SN74LV221AQPWRQ1"),
        ("prep_abort_memory", "SN74HCS74PWR"),
        ("c_prep_abort_memory", "GRM188R71H104KA93D"),
        ("prep_trip_ok_pd", "RC0603FR-0710KL"),
        ("prep_abort_ok_pd", "RC0603FR-0710KL"),
        ("c_prep_timing", "GRM188R71H103KA01D"),
        ("c_history_timing", "GRM188R71H103KA01D"),
        ("r_prep_timing", "RC0603FR-0710KL"),
        ("r_history_timing", "RC0603FR-0710KL"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != part) {
            return Err(format!("wrong part identity for {id}"));
        }
    }
    // Every audited signal has exact membership, so an extra bypass or a
    // short between two named signals also fails.
    for (net, expected) in [
        ("selv3v3", "iso_protocol:1 iso_protocol:7 iso_feedback:1 iso_feedback:7 c_iso1_selv:1 c_iso2_selv:1"),
        ("selv_gnd", "iso_protocol:2 iso_protocol:8 iso_feedback:2 iso_feedback:8 c_iso1_selv:2 c_iso2_selv:2 source_permit_fb_pd:2 source_session_fb_pd:2"),
        ("hot_logic5", "rx:18 rx:28 iso_protocol:10 iso_protocol:16 iso_feedback:10 iso_feedback:16 reset_pulses:3 reset_pulses:11 reset_pulses:16 prep_abort_memory:1 prep_abort_memory:10 prep_abort_memory:14 c_prep_abort_memory:1 r_prep_timing:1 r_history_timing:1 c_reset_pulses:1 c_rx:1 c_iso1_hot:1 c_iso2_hot:1 reset_pullup:1 prep_abort_pu:1 permit_seen_pu:1"),
        ("hot_prep_abort_q", "rx:7 prep_abort_memory:5 prep_abort_pu:2"),
        ("hot_prep_abort_ok", "prep_abort_memory:6 prep_abort_ok_pd:1"),
        ("hot_prep_trip_ok", "prep_abort_memory:4 prep_trip_ok_pd:1"),
        ("q1", "reset_pulses:13 prep_abort_memory:3"),
        ("source_command_tx", "iso_protocol:3"),
        ("source_permit_q", "iso_protocol:4"),
        ("source_relay_request", "iso_protocol:5"),
        ("source_response_rx", "iso_protocol:6"),
        ("source_health_q", "iso_feedback:3"),
        ("source_stop_n", "iso_feedback:4"),
        ("source_hot_permit_fb", "iso_feedback:5 source_permit_fb_pd:1"),
        ("source_hot_session_fb", "iso_feedback:6 source_session_fb_pd:1"),
        ("hot_permit", "rx:10 iso_protocol:13 iso_feedback:12 permit_pd:1"),
        ("hot_relay_request", "rx:3 iso_protocol:12 relay_request_pd:1"),
        ("hot_relay_driver", "rx:32 relay_driver_pd:1"),
        ("hot_source_health", "iso_feedback:14 source_health_pd:1"),
        ("hot_source_stop_n", "iso_feedback:13 source_stop_pd:1"),
        ("hot_session_q", "rx:11 iso_feedback:11 session_pd:1"),
        ("hot_session_clear_n", "rx:20 session_clear_pd:1"),
        ("hot_prep_reset_request", "rx:2 reset_pulses:2 prep_reset_pd:1"),
        ("hot_history_reset_request", "rx:9 reset_pulses:10 history_reset_pd:1"),
        ("hot_prep_reset_raw_n", "reset_pulses:4 prep_reset_raw_pd:1"),
        ("hot_history_reset_raw_n", "reset_pulses:12 history_reset_raw_pd:1"),
        ("cext1", "reset_pulses:14 c_prep_timing:2"),
        ("rext_cext1", "reset_pulses:15 r_prep_timing:2 c_prep_timing:1"),
        ("cext2", "reset_pulses:6 c_history_timing:2"),
        ("rext_cext2", "reset_pulses:7 r_history_timing:2 c_history_timing:1"),
        ("ind", "rx:30 iso_protocol:11"),
        ("outa", "rx:31 iso_protocol:14"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong membership on {net}")); }
    }
    for (id, pin, net) in [
        ("rx", "1", "hot_permit_seen_q"), ("rx", "2", "hot_prep_reset_request"),
        ("rx", "6", "hot_disarm_q"), ("rx", "7", "hot_prep_abort_q"),
        ("rx", "8", "hot_fault_n"), ("rx", "9", "hot_history_reset_request"),
        ("rx", "12", "hot_run_q"), ("rx", "13", "hot_receiver_abort_n"),
        ("rx", "14", "hot_revalidate_request"), ("rx", "15", "hot_run_set_request"),
        ("rx", "16", "hot_wdi"), ("rx", "17", "hot_rails_ok"),
        ("rx", "19", "hot0"), ("rx", "29", "hot0"),
        ("reset_pulses", "1", "hot0"), ("reset_pulses", "9", "hot0"),
        ("reset_pulses", "8", "hot0"),
        ("prep_abort_memory", "2", "hot0"),
        ("prep_abort_memory", "7", "hot0"),
        ("prep_abort_memory", "11", "hot0"),
        ("prep_abort_memory", "12", "hot0"),
        ("prep_abort_memory", "13", "hot0"),
        ("c_prep_abort_memory", "2", "hot0"),
        ("prep_trip_ok_pd", "2", "hot0"),
        ("prep_abort_ok_pd", "2", "hot0"),
        ("rx", "26", "hot_reset_n"), ("rx", "27", "hot_updi"),
    ] {
        if g.pins.get(&(id.into(), pin.into())).is_none_or(|found| found != net) {
            return Err(format!("{id}.{pin} must be on {net}"));
        }
    }
    for net in ["hot_permit", "hot_relay_request", "hot_relay_driver", "hot_source_health",
                "hot_source_stop_n", "hot_session_q", "hot_receiver_abort_n",
                "hot_session_clear_n", "hot_prep_reset_raw_n",
                "hot_history_reset_raw_n"] {
        let id = match net {
            "hot_permit" => "permit_pd", "hot_relay_request" => "relay_request_pd",
            "hot_relay_driver" => "relay_driver_pd", "hot_source_health" => "source_health_pd",
            "hot_source_stop_n" => "source_stop_pd", "hot_session_q" => "session_pd",
            "hot_session_clear_n" => "session_clear_pd",
            "hot_prep_reset_raw_n" => "prep_reset_raw_pd",
            "hot_history_reset_raw_n" => "history_reset_raw_pd",
            _ => "abort_pd",
        };
        if g.pins.get(&(id.into(), "1".into())).is_none_or(|found| found != net)
            || g.pins.get(&(id.into(), "2".into())).is_none_or(|found| found != "hot0") {
            return Err(format!("missing local low default on {net}"));
        }
    }
    // Check every net, including currently unnamed or newly added conductors.
    let mut net_domains: BTreeMap<&str, &str> = BTreeMap::new();
    for ((id, pin), net) in &g.pins {
        let side = domain(id, pin);
        if net_domains.insert(net, side).is_some_and(|old| old != side) {
            return Err(format!("{net} crosses SELV/HOT boundary"));
        }
    }
    Ok(())
}

fn main() {
    let input = fs::read_to_string("build/isolation.net").expect("Atopile netlist");
    check(&graph(&input).expect("netlist parse")).expect("isolation pin audit");
    println!("partial Rev38 isolation pin audit PASS");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Graph {
        graph(&fs::read_to_string("build/isolation.net").unwrap()).unwrap()
    }

    #[test]
    fn compiled_fixture_passes() { check(&fixture()).unwrap(); }

    #[test]
    fn feedback_swap_fails() {
        let mut g = fixture();
        g.pins.insert(("iso_feedback".into(), "5".into()), "source_hot_session_fb".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn missing_abort_default_fails() {
        let mut g = fixture();
        g.pins.remove(&("abort_pd".into(), "2".into()));
        assert!(check(&g).is_err());
    }

    #[test]
    fn missing_clear_readback_default_fails() {
        let mut g = fixture();
        g.pins.remove(&("session_clear_pd".into(), "2".into()));
        assert!(check(&g).is_err());
    }

    #[test]
    fn relay_driver_short_fails() {
        let mut g = fixture();
        g.pins.insert(("rx".into(), "32".into()), "hot_relay_request".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn wrong_feedback_part_fails() {
        let mut g = fixture();
        g.parts.insert("iso_feedback".into(), "ISO7741FDWR".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn new_copper_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("source_permit_fb_pd".into(), "2".into()), "hot0".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn reset_channels_swapped_fail() {
        let mut g = fixture();
        g.pins.insert(("reset_pulses".into(), "12".into()), "hot_prep_reset_raw_n".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn missing_timing_cap_fails() {
        let mut g = fixture();
        g.pins.remove(&("c_history_timing".into(), "1".into()));
        assert!(check(&g).is_err());
    }

    #[test]
    fn trip_preset_miswire_fails() {
        let mut g = fixture();
        g.pins.insert(("prep_abort_memory".into(), "4".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn reset_clock_miswire_fails() {
        let mut g = fixture();
        g.pins.insert(("prep_abort_memory".into(), "3".into()), "hot_prep_reset_raw_n".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn missing_trip_default_fails() {
        let mut g = fixture();
        g.pins.remove(&("prep_trip_ok_pd".into(), "2".into()));
        assert!(check(&g).is_err());
    }
}
