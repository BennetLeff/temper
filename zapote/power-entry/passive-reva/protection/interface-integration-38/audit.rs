//! Exact-pin audit of the Rev38 cooker-controller port, receiver, driver, watchdog,
//! rail supervisors, and VD/VB detector. Electrical limits remain open.

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
    references: BTreeMap<String, String>,
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
    let mut net_names = BTreeSet::new();
    let mut net_codes = BTreeSet::new();
    for net in children(section, "net") {
        let name = field(net, "name")?;
        let code = field(net, "code")?;
        if !net_names.insert(name.clone()) || !net_codes.insert(code) {
            return Err(format!("duplicate net name or code: {name}"));
        }
        for node in children(net, "node") {
            let reference = field(node, "ref")?;
            let identity = refs.get(&reference).ok_or_else(|| format!("unknown reference {reference}"))?;
            let pin = (identity.clone(), field(node, "pin")?);
            if pins.insert(pin.clone(), name.clone()).is_some() {
                return Err(format!("duplicate pin {pin:?}"));
            }
        }
    }
    Ok(Graph { parts, pins, references: refs })
}

// Atopile can reuse one netlist libsource identity for distinct MPNs that
// share a footprint. The generated BOM retains the per-reference MPN;
// connectivity comes from the netlist and part identity comes from the BOM.
fn with_bom_parts(mut g: Graph, csv_path: &str) -> Result<Graph, String> {
    let csv = fs::read_to_string(csv_path).map_err(|e| e.to_string())?;
    let mut seen = BTreeSet::new();
    for row in csv.lines().skip(1) {
        let (mpn, tail) = row.split_once(',').ok_or("BOM row missing MPN")?;
        let refs = if let Some(quoted) = tail.strip_prefix('"') {
            quoted.split_once('"').ok_or("unterminated BOM designators")?.0
        } else {
            tail.split_once(',').ok_or("BOM row missing designator")?.0
        };
        for reference in refs.split(',') {
            if let Some(id) = g.references.get(reference) {
                if !seen.insert(id.clone()) { return Err(format!("duplicate BOM identity for {id}")); }
                g.parts.insert(id.clone(), mpn.to_owned());
            }
        }
    }
    for id in g.references.values() {
        if !seen.contains(id) { return Err(format!("BOM missing {id}")); }
    }
    Ok(g)
}

fn joined_bom_graph() -> Result<Graph, String> {
    load_stage("integrated")
}

fn load_stage(name: &str) -> Result<Graph, String> {
    let netlist = fs::read_to_string(format!("build/{name}.net")).map_err(|e| e.to_string())?;
    with_bom_parts(graph(&netlist)?, &format!("build/{name}.csv"))
}

fn members(g: &Graph, net: &str) -> BTreeSet<(String, String)> {
    g.pins.iter().filter(|(_, name)| name.as_str() == net)
        .map(|(pin, _)| pin.clone()).collect()
}

fn check_cooker_mate(g: &Graph) -> Result<(), String> {
    for (id, part) in [
        ("rev38_mate", "43045-1612"),
        ("cooker.mcu.mcu", "ESP32-S3-WROOM-1-N8R8"),
        ("cooker.mcu.r_sda_pullup", "RC0603FR-074K7L"),
        ("cooker.mcu.r_scl_pullup", "RC0603FR-074K7L"),
        ("cooker.aux_supply.psu", "IRM-10-15"),
        ("cooker.power_mgmt.buck_3v3.buck", "LMR51430XDDCR"),
        ("cooker.power_mgmt.buck_3v3.l_out", "SRP1265A-5R6M"),
        ("supervisor", "TPS389001DSER"),
        ("reset_buffer", "SN74LVC1G17DBVR"),
        ("fault_inverter", "SN74LVC1G04DBVR"),
        ("reset_and", "SN74LVC1G08DBVR"),
        ("interlock_and", "SN74LVC1G08DBVR"),
        ("rail_top", "RC0603FR-0716KL"),
        ("rail_bottom", "RC0603FR-0710KL"),
        ("reset_pullup", "RC0603FR-0710KL"),
        ("runaway_pulldown", "RC0603FR-0710KL"),
        ("reset_delay", "GRM188R71H104KA93D"),
        ("supervisor_bypass", "GRM188R71H104KA93D"),
        ("reset_buffer_bypass", "GRM188R71H104KA93D"),
        ("fault_inverter_bypass", "GRM188R71H104KA93D"),
        ("reset_and_bypass", "GRM188R71H104KA93D"),
        ("interlock_and_bypass", "GRM188R71H104KA93D"),
    ] {
        if g.parts.get(id).map(String::as_str) != Some(part) {
            return Err(format!("cooker mate part identity differs at {id}"));
        }
    }
    for part in ["43045-1612", "ESP32-S3-WROOM-1-N8R8"] {
        if g.parts.values().filter(|candidate| candidate.as_str() == part).count() != 1 {
            return Err(format!("cooker mate expected exactly one {part}"));
        }
    }

    let groups: &[(&str, &[(&str, &str)])] = &[
        ("SELV 3.3 V", &[("rev38_mate", "1"), ("rev38_mate", "9"), ("cooker.mcu.mcu", "2"), ("cooker.mcu.r_sda_pullup", "1"), ("cooker.mcu.r_scl_pullup", "1"), ("cooker.power_mgmt.buck_3v3.l_out", "2"), ("supervisor", "4"), ("reset_buffer", "5"), ("fault_inverter", "5"), ("reset_and", "5"), ("interlock_and", "5"), ("rail_top", "1"), ("reset_pullup", "1"), ("supervisor_bypass", "1"), ("reset_buffer_bypass", "1"), ("fault_inverter_bypass", "1"), ("reset_and_bypass", "1"), ("interlock_and_bypass", "1")]),
        ("SELV ground", &[("rev38_mate", "8"), ("rev38_mate", "13"), ("rev38_mate", "16"), ("cooker.mcu.mcu", "1"), ("cooker.mcu.mcu", "40"), ("cooker.mcu.mcu", "41"), ("cooker.aux_supply.psu", "4"), ("cooker.power_mgmt.buck_3v3.buck", "1"), ("supervisor", "2"), ("reset_buffer", "3"), ("fault_inverter", "3"), ("reset_and", "3"), ("interlock_and", "3"), ("rail_bottom", "2"), ("runaway_pulldown", "2"), ("reset_delay", "2"), ("supervisor_bypass", "2"), ("reset_buffer_bypass", "2"), ("fault_inverter_bypass", "2"), ("reset_and_bypass", "2"), ("interlock_and_bypass", "2")]),
        ("SELV 15 V source", &[("cooker.aux_supply.psu", "3"), ("cooker.power_mgmt.buck_3v3.buck", "3"), ("cooker.power_mgmt.buck_3v3.buck", "5")]),
        ("SOURCE_STOP_N", &[("rev38_mate", "2"), ("cooker.mcu.mcu", "21")]),
        ("SOURCE_VALIDATED_HEARTBEAT", &[("rev38_mate", "3"), ("cooker.mcu.mcu", "23")]),
        ("SOURCE_PERMIT_SET_REQUEST", &[("rev38_mate", "4"), ("cooker.mcu.mcu", "25")]),
        ("SOURCE_PREWATCHDOG_OK", &[("rev38_mate", "5"), ("cooker.mcu.mcu", "11")]),
        ("SOURCE_COMMAND_TX", &[("rev38_mate", "6"), ("cooker.mcu.mcu", "33")]),
        ("SOURCE_RESPONSE_RX", &[("rev38_mate", "7"), ("cooker.mcu.mcu", "34")]),
        ("SOURCE_START_N", &[("rev38_mate", "10"), ("cooker.mcu.mcu", "35")]),
        ("I2C_SDA", &[("rev38_mate", "11"), ("cooker.mcu.mcu", "31"), ("cooker.mcu.r_sda_pullup", "2")]),
        ("I2C_SCL", &[("rev38_mate", "12"), ("cooker.mcu.mcu", "32"), ("cooker.mcu.r_scl_pullup", "2")]),
        ("SOURCE_RESET_GOOD", &[("rev38_mate", "14"), ("reset_buffer", "4"), ("reset_and", "1")]),
        ("SOURCE_INTERLOCK_N", &[("rev38_mate", "15"), ("interlock_and", "4")]),
    ];
    let mut distinct = BTreeSet::new();
    for (label, pins) in groups {
        let (first_id, first_pin) = pins[0];
        let net = g.pins.get(&(first_id.into(), first_pin.into()))
            .ok_or_else(|| format!("cooker mate missing {label}: {first_id}.{first_pin}"))?;
        if !distinct.insert(net) {
            return Err(format!("cooker mate {label} is shorted to another port function"));
        }
        for (id, pin) in *pins {
            if g.pins.get(&((*id).into(), (*pin).into())) != Some(net) {
                return Err(format!("cooker mate {label} missing {id}.{pin}"));
            }
        }
        if !matches!(*label, "SELV 3.3 V" | "SELV ground" | "SELV 15 V source") {
            let expected: BTreeSet<(String, String)> = pins.iter()
                .map(|(id, pin)| ((*id).into(), (*pin).into())).collect();
            if members(g, net) != expected {
                return Err(format!("cooker mate {label} has an unexpected load or driver"));
            }
        }
    }
    let internal: &[(&str, &[(&str, &str)])] = &[
        ("reset request", &[("cooker.mcu.mcu", "22"), ("cooker.safety.fault_any_or", "4"), ("supervisor", "6"), ("reset_pullup", "2"), ("reset_buffer", "2"), ("reset_and", "2")]),
        ("rail sense", &[("rail_top", "2"), ("rail_bottom", "1"), ("supervisor", "1")]),
        ("reset delay", &[("reset_delay", "1"), ("supervisor", "5")]),
        ("fault inverted", &[("fault_inverter", "4"), ("interlock_and", "2")]),
        ("reset and", &[("reset_and", "4"), ("interlock_and", "1")]),
        ("ESP EN", &[("supervisor", "3"), ("cooker.mcu.mcu", "3"), ("cooker.mcu.r_en", "2"), ("cooker.mcu.c_en", "1"), ("cooker.mcu.btn_reset", "1")]),
        ("latched shutdown", &[("cooker.safety.latch", "6"), ("cooker.safety.latch", "10"), ("cooker.hb.gate_hs.driver", "5"), ("cooker.mcu.mcu", "10"), ("cooker.safety.tp_shutdown", "1"), ("cooker.safety.tp_fault", "1"), ("fault_inverter", "2")]),
        ("runaway cut", &[("cooker.mcu.mcu", "8"), ("cooker.safety.fault_or", "5"), ("runaway_pulldown", "1")]),
    ];
    for (label, pins) in internal {
        let net = g.pins.get(&(pins[0].0.into(), pins[0].1.into()))
            .ok_or_else(|| format!("cooker mate missing {label}"))?;
        let wanted: BTreeSet<(String, String)> = pins.iter().map(|(id, pin)| ((*id).into(), (*pin).into())).collect();
        if members(g, net) != wanted || !distinct.insert(net) {
            return Err(format!("cooker mate {label} differs or is shorted"));
        }
    }
    let reset_request = g.pins.get(&("supervisor".into(), "6".into())).unwrap();
    let rail = g.pins.get(&("rev38_mate".into(), "1".into())).unwrap();
    let ground = g.pins.get(&("rev38_mate".into(), "8".into())).unwrap();
    for (label, net) in [("reset request", reset_request), ("rail", rail), ("ground", ground)] {
        if net == g.pins.get(&("rev38_mate".into(), "14".into())).unwrap() ||
           net == g.pins.get(&("rev38_mate".into(), "15".into())).unwrap() {
            return Err(format!("cooker mate {label} shorted to authorization output"));
        }
    }
    Ok(())
}

fn check_cooker_rev38_harness(rev38: &Graph, cooker: &Graph) -> Result<(), String> {
    check_cooker_mate(cooker)?;
    for (id, mpn) in [
        ("source_mcu.controller_port", "43045-1612"),
        ("source_mcu.expander", "TCA6408AQPWRQ1"),
        ("receiver.iso_protocol", "ISO7741FQDWWRQ1"),
        ("source_mcu.start", "EVQ-P7A01P"),
        ("source.stop_pd", "RC0603FR-0710KL"),
        ("source.heartbeat_pd", "RC0603FR-0710KL"),
        ("source.permit_set_pd", "RC0603FR-0710KL"),
        ("source.prewatchdog_pd", "RC0603FR-0710KL"),
        ("source.reset_good_pd", "RC0603FR-0710KL"),
        ("source.interlock_pd", "RC0603FR-0710KL"),
    ] {
        if rev38.parts.get(id).map(String::as_str) != Some(mpn) {
            return Err(format!("Rev38 {id} identity differs from {mpn}"));
        }
    }
    if rev38.parts.values().filter(|part| part.as_str() == "ESP32-S3-WROOM-1-N8R8").count() != 0 ||
       rev38.parts.values().filter(|part| part.as_str() == "43045-1612").count() != 1 {
        return Err("Rev38 board must have one port and no second cooker ESP".into());
    }
    let mut nets = [Vec::new(), Vec::new()];
    for (side, (g, id)) in [(rev38, "source_mcu.controller_port"), (cooker, "rev38_mate")]
        .into_iter().enumerate() {
        for pad in 1..=16 {
            let net = g.pins.get(&(id.into(), pad.to_string()))
                .ok_or_else(|| format!("missing {id} pad {pad}"))?;
            nets[side].push(net.as_str());
        }
        for left in 1..=16 {
            for right in left + 1..=16 {
                let group = |pad| match pad { 9 => 1, 13 | 16 => 8, _ => pad };
                if (nets[side][left - 1] == nets[side][right - 1]) !=
                   (group(left) == group(right)) {
                    return Err(format!("{id} pads {left}/{right} split or shorted"));
                }
            }
        }
    }
    // The two PCB sources have distinct net names. Each numbered contact is
    // one proposed straight-through conductor, with only the declared supply
    // and return contacts sharing a net on either board.
    for (pad, id, pin) in [
        (1, "source_mcu.expander", "1"),
        (2, "source.stop_pd", "1"),
        (3, "source.heartbeat_pd", "1"),
        (4, "source.permit_set_pd", "1"),
        (5, "source.prewatchdog_pd", "1"),
        (6, "receiver.iso_protocol", "3"),
        (7, "receiver.iso_protocol", "6"),
        (8, "source_mcu.expander", "2"),
        (9, "source_mcu.expander", "16"),
        (10, "source_mcu.start", "1"),
        (11, "source_mcu.expander", "15"),
        (12, "source_mcu.expander", "14"),
        (13, "source_mcu.expander", "8"),
        (14, "source.reset_good_pd", "1"),
        (15, "source.interlock_pd", "1"),
        (16, "receiver.c_iso1_selv", "2"),
    ] {
        if rev38.pins.get(&(id.into(), pin.into())).map(String::as_str) !=
           Some(nets[0][pad - 1]) {
            return Err(format!("Rev38 port pad {pad} lost {id}.{pin}"));
        }
    }
    // A required endpoint alone is insufficient: another driver could be
    // silently joined to STOP or an authorization input. Pin all signal-net
    // members. The shared supply/return nets are handled by the full Rev38
    // source audit and the frozen-source receipt.
    for (pad, expected) in [
        (2, &[("receiver.iso_feedback", "4"), ("source.permit_clear", "2"), ("source.stop_pd", "1"), ("source_mcu.controller_port", "2")][..]),
        (3, &[("source.heartbeat_pd", "1"), ("source.seen_reset_pulse", "10"), ("source_mcu.controller_port", "3")][..]),
        (4, &[("source.inv", "5"), ("source.permit", "3"), ("source.permit_set_pd", "1"), ("source_mcu.controller_port", "4")][..]),
        (5, &[("source.health", "8"), ("source.prewatchdog_pd", "1"), ("source_mcu.controller_port", "5")][..]),
        (6, &[("receiver.iso_protocol", "3"), ("source_mcu.controller_port", "6")][..]),
        (7, &[("receiver.iso_protocol", "6"), ("source_mcu.controller_port", "7")][..]),
        (10, &[("source_mcu.controller_port", "10"), ("source_mcu.start", "1"), ("source_mcu.start_pu", "2")][..]),
        (11, &[("source_mcu.controller_port", "11"), ("source_mcu.expander", "15")][..]),
        (12, &[("source_mcu.controller_port", "12"), ("source_mcu.expander", "14")][..]),
        (14, &[("source.health", "1"), ("source.health", "9"), ("source.reset_good_pd", "1"), ("source_mcu.controller_port", "14")][..]),
        (15, &[("source.health", "10"), ("source.health", "4"), ("source.interlock_pd", "1"), ("source_mcu.controller_port", "15")][..]),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.iter()
            .map(|(id, pin)| ((*id).into(), (*pin).into())).collect();
        if members(rev38, nets[0][pad - 1]) != wanted {
            return Err(format!("Rev38 port pad {pad} has an extra or missing endpoint"));
        }
    }
    Ok(())
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
    if g.parts.len() != 71 { return Err(format!("expected 71 parts, found {}", g.parts.len())); }
    for (id, part) in [
        ("rx", "AVR64DA32-E/PT"),
        ("iso_protocol", "ISO7741FQDWWRQ1"),
        ("iso_feedback", "ISO6742FQDWWRQ1"),
        ("reset_pulses", "SN74LV221AQPWRQ1"),
        ("prep_abort_memory", "SN74HCS74PWR"),
        ("permit_seen_memory", "SN74HCS74PWR"),
        ("disarm_memory", "SN74HCS74PWR"),
        ("c_disarm_memory", "GRM188R71H104KA93D"),
        ("disarm_sample_pd", "RC0603FR-0710KL"),
        ("permit_inverter", "SN74HCS04PWR"),
        ("c_permit_inverter", "GRM188R71H104KA93D"),
        ("c_permit_seen_memory", "GRM188R71H104KA93D"),
        ("permit_preset_pd", "RC0603FR-0710KL"),
        ("prep_trip_and", "SN74HCS21PWR"),
        ("history_reset_and", "SN74HCS21PWR"),
        ("c_history_reset_and", "GRM188R71H104KA93D"),
        ("history_reset_allowed_pd", "RC0603FR-0710KL"),
        ("history_reset_d_pu", "RC0603FR-0710KL"),
        ("c_prep_trip_and", "GRM188R71H104KA93D"),
        ("watchdog_ok_pd", "RC0603FR-07100KL"),
        ("rails_pd", "RC0603FR-07100KL"),
        ("c_prep_abort_memory", "GRM188R71H104KA93D"),
        ("permit_loss_nand", "SN74HCS00PWR"),
        ("c_permit_loss_nand", "GRM188R71H104KA93D"),
        ("permit_loss_ok_pd", "RC0603FR-0710KL"),
        ("session_and", "SN74HCS21PWR"),
        ("c_session_and", "GRM188R71H104KA93D"),
        ("revalidate_d_pd", "RC0603FR-0710KL"),
        ("session_memory", "SN74HCS74PWR"),
        ("c_session_memory", "GRM188R71H104KA93D"),
        ("run_and", "SN74HCS21PWR"),
        ("c_run_and", "GRM188R71H104KA93D"),
        ("run_clear_pd", "RC0603FR-0710KL"),
        ("run_memory", "SN74HCS74PWR"),
        ("c_run_memory", "GRM188R71H104KA93D"),
        ("prep_trip_ok_pd", "RC0603FR-0710KL"),
        ("prep_abort_ok_pd", "RC0603FR-0710KL"),
        ("attempt_valid_pd", "RC0603FR-0710KL"),
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
        ("hot_logic5", "rx:18 rx:28 iso_protocol:10 iso_protocol:16 iso_feedback:10 iso_feedback:16 reset_pulses:3 reset_pulses:11 reset_pulses:16 prep_abort_memory:1 prep_abort_memory:10 prep_abort_memory:14 permit_seen_memory:1 permit_seen_memory:10 permit_seen_memory:14 disarm_memory:4 disarm_memory:10 disarm_memory:14 c_disarm_memory:1 permit_inverter:14 c_permit_inverter:1 c_permit_seen_memory:1 prep_trip_and:13 prep_trip_and:14 history_reset_and:13 history_reset_and:14 c_history_reset_and:1 history_reset_d_pu:1 permit_loss_nand:14 c_permit_loss_nand:1 session_and:14 c_session_and:1 session_memory:4 session_memory:10 session_memory:14 c_session_memory:1 run_and:5 run_and:12 run_and:13 run_and:14 c_run_and:1 run_memory:4 run_memory:10 run_memory:14 c_run_memory:1 c_prep_trip_and:1 c_prep_abort_memory:1 r_prep_timing:1 r_history_timing:1 c_reset_pulses:1 c_rx:1 c_iso1_hot:1 c_iso2_hot:1 reset_pullup:1 prep_abort_pu:1 permit_seen_pu:1"),
        ("hot_prep_abort_q", "rx:7 prep_abort_memory:5 prep_abort_pu:2"),
        ("hot_prep_abort_ok", "prep_abort_memory:6 history_reset_and:5 session_and:2 prep_abort_ok_pd:1"),
        ("hot_prep_trip_ok", "prep_abort_memory:4 disarm_memory:1 prep_trip_and:8 history_reset_and:10 session_and:1 prep_trip_ok_pd:1"),
        ("hot_attempt_valid", "rx:4 prep_trip_and:1 attempt_valid_pd:1"),
        ("hot_watchdog_ok", "prep_trip_and:12 watchdog_ok_pd:1"),
        ("prep_trip_and-y1", "prep_trip_and:6 prep_trip_and:9"),
        ("q1", "reset_pulses:13 prep_abort_memory:3"),
        ("source_command_tx", "iso_protocol:3"),
        ("source_permit_q", "iso_protocol:4"),
        ("source_relay_request", "iso_protocol:5"),
        ("source_response_rx", "iso_protocol:6"),
        ("source_health_q", "iso_feedback:3"),
        ("source_stop_n", "iso_feedback:4"),
        ("source_hot_permit_fb", "iso_feedback:5 source_permit_fb_pd:1"),
        ("source_hot_session_fb", "iso_feedback:6 source_session_fb_pd:1"),
        ("hot_permit", "rx:10 iso_protocol:13 iso_feedback:12 permit_inverter:1 run_and:2 permit_pd:1"),
        ("hot_permit_seen_q", "rx:1 permit_seen_memory:5 permit_loss_nand:1 permit_seen_pu:2"),
        ("hot_permit_preset_n", "permit_inverter:2 permit_seen_memory:4 disarm_memory:2 history_reset_and:4 permit_loss_nand:2 session_and:12 permit_preset_pd:1"),
        ("hot_disarm_q", "rx:6 disarm_memory:5 history_reset_and:1 session_and:10 disarm_pd:1"),
        ("hot_disarm_sample_request", "rx:21 disarm_memory:3 disarm_sample_pd:1"),
        ("hot_run_low", "permit_inverter:4 history_reset_and:2 session_and:13"),
        ("hot_abort_asserted", "permit_inverter:6 history_reset_and:12"),
        ("hot_history_reset_allowed", "history_reset_and:8 permit_inverter:9 history_reset_allowed_pd:1"),
        ("hot_history_reset_d", "permit_inverter:8 permit_seen_memory:2 history_reset_d_pu:2"),
        ("history_reset_and-y1", "history_reset_and:6 history_reset_and:9"),
        ("reset_pulses-q2", "reset_pulses:5 permit_seen_memory:3"),
        ("hot_relay_request", "rx:3 iso_protocol:12 relay_request_pd:1"),
        ("hot_relay_driver", "rx:32 relay_driver_pd:1 run_and:10"),
        ("hot_relay_enable", "run_and:8"),
        ("hot_source_health", "iso_feedback:14 prep_trip_and:2 source_health_pd:1"),
        ("hot_source_stop_n", "iso_feedback:13 prep_trip_and:4 source_stop_pd:1"),
        ("hot_fault_n", "rx:8 prep_trip_and:10 fault_n_pd:1"),
        ("hot_rails_ok", "rx:17 prep_trip_and:5 rails_pd:1"),
        ("hot_permit_loss_ok", "permit_loss_nand:3 permit_loss_ok_pd:1 session_and:5"),
        ("hot_session_revalidate_d", "session_and:8 revalidate_d_pd:1 session_memory:2"),
        ("hot_run_clear_n", "run_and:6 run_clear_pd:1 run_memory:1 run_memory:2"),
        ("hot_session_q", "rx:11 iso_feedback:11 session_memory:5 run_and:1 session_pd:1"),
        ("hot_run_q", "rx:12 permit_inverter:3 run_memory:5 run_and:9 run_pd:1"),
        ("hot_receiver_abort_n", "rx:13 permit_inverter:5 session_and:4 abort_pd:1"),
        ("hot_session_clear_n", "rx:20 session_and:6 session_and:9 session_memory:1 run_and:4 session_clear_pd:1"),
        ("hot_revalidate_request", "rx:14 session_memory:3 revalidate_pd:1"),
        ("hot_run_set_request", "rx:15 run_memory:3 run_set_pd:1"),
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
        ("attempt_valid_pd", "2", "hot0"),
        ("prep_trip_and", "7", "hot0"),
        ("history_reset_and", "7", "hot0"),
        ("c_history_reset_and", "2", "hot0"),
        ("history_reset_allowed_pd", "2", "hot0"),
        ("c_prep_trip_and", "2", "hot0"),
        ("watchdog_ok_pd", "2", "hot0"),
        ("permit_inverter", "7", "hot0"),
        ("permit_inverter", "11", "hot0"),
        ("permit_inverter", "13", "hot0"),
        ("permit_seen_memory", "7", "hot0"),
        ("permit_seen_memory", "11", "hot0"),
        ("permit_seen_memory", "12", "hot0"),
        ("permit_seen_memory", "13", "hot0"),
        ("c_permit_inverter", "2", "hot0"),
        ("c_permit_seen_memory", "2", "hot0"),
        ("permit_preset_pd", "2", "hot0"),
        ("disarm_memory", "7", "hot0"),
        ("disarm_memory", "11", "hot0"),
        ("disarm_memory", "12", "hot0"),
        ("disarm_memory", "13", "hot0"),
        ("c_disarm_memory", "2", "hot0"),
        ("disarm_sample_pd", "2", "hot0"),
        ("permit_loss_nand", "7", "hot0"),
        ("permit_loss_nand", "4", "hot0"), ("permit_loss_nand", "5", "hot0"),
        ("permit_loss_nand", "9", "hot0"), ("permit_loss_nand", "10", "hot0"),
        ("permit_loss_nand", "12", "hot0"), ("permit_loss_nand", "13", "hot0"),
        ("c_permit_loss_nand", "2", "hot0"), ("permit_loss_ok_pd", "2", "hot0"),
        ("session_and", "7", "hot0"), ("c_session_and", "2", "hot0"),
        ("revalidate_d_pd", "2", "hot0"),
        ("session_memory", "7", "hot0"), ("session_memory", "11", "hot0"),
        ("session_memory", "12", "hot0"), ("session_memory", "13", "hot0"),
        ("c_session_memory", "2", "hot0"),
        ("run_and", "7", "hot0"), ("c_run_and", "2", "hot0"),
        ("run_clear_pd", "2", "hot0"),
        ("run_memory", "7", "hot0"), ("run_memory", "11", "hot0"),
        ("run_memory", "12", "hot0"), ("run_memory", "13", "hot0"),
        ("c_run_memory", "2", "hot0"),
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

fn check_source(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 48 { return Err(format!("expected 48 source parts, found {}", g.parts.len())); }
    for (id, part) in [
        ("watchdog", "TPS3431SDRBR"),
        ("cwd", "GRM1885C1H102JA01D"),
        ("rail", "TPS389001DSER"),
        ("rail_top", "RC0603FR-0716KL"),
        ("heartbeat_pd", "RC0603FR-0710KL"),
        ("wdi_pu", "RC0603FR-07100KL"),
        ("health", "SN74HCS21PWR"),
        ("prewatchdog_pd", "RC0603FR-0710KL"),
        ("inv", "SN74HCS04PWR"),
        ("seen_reset_pulse", "SN74LV221AQPWRQ1"),
        ("seen", "SN74HCS74PWR"),
        ("loss", "SN74HCS00PWR"),
        ("reset_check", "SN74HCS21PWR"),
        ("permit_clear", "SN74HCS21PWR"),
        ("permit", "SN74HCS74PWR"),
        ("reset_c", "GRM188R71H103KA01D"),
        ("wdi_pulse_c", "GRM188R71H103KA01D"),
        ("wdi_pulse_r", "RC0603FR-0710KL"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != part) {
            return Err(format!("wrong source part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("source_validated_heartbeat", "seen_reset_pulse:10 heartbeat_pd:1"),
        ("source_reset_good", "health:1 health:9 reset_good_pd:1"),
        ("source_interlock_n", "health:4 health:10 interlock_pd:1"),
        ("source_stop_n", "permit_clear:2 stop_pd:1"),
        ("source_hot_permit_fb", "inv:1 permit_fb_pd:1"),
        ("source_hot_session_fb", "permit_clear:4 session_fb_pd:1"),
        ("source_permit_set_request", "inv:5 permit:3 permit_set_pd:1"),
        ("source_seen_reset_request", "seen_reset_pulse:2 seen_reset_pd:1"),
        ("source_challenge_active", "reset_check:10 challenge_pd:1"),
        ("source_health_q", "health:6 reset_check:5 permit_clear:1 health_pd:1"),
        ("source_prewatchdog_ok", "health:8 prewatchdog_pd:1"),
        ("source_permit_q", "inv:3 permit:5 permit_q_pd:1"),
        ("source_permit_seen_q", "seen:5 seen_pu:2 loss:1"),
        ("source_permit_loss_ok", "loss:3 permit_clear:5 loss_pd:1"),
        ("source_clear_n", "permit_clear:6 permit:1 permit:2 clear_pd:1"),
        ("source_rail_reset_n", "rail:6 rail_reset_pu:2 health:5 health:12"),
        ("source_watchdog_good", "watchdog:7 watchdog:8 wdo_pu:2 health:2"),
        ("source_wdi", "watchdog:6 seen_reset_pulse:12 wdi_pu:2"),
        ("source_wdi_cext", "seen_reset_pulse:6 wdi_pulse_c:2"),
        ("source_wdi_rext_cext", "seen_reset_pulse:7 wdi_pulse_r:2 wdi_pulse_c:1"),
        ("source_wd_cwd", "watchdog:2 cwd:1"),
        ("source_rail_sense", "rail:1 rail_top:2 rail_bottom:1"),
        ("source_rail_ct", "rail:5 rail_ct:1"),
        ("source_permit_low", "inv:4 reset_check:1"),
        ("source_set_low", "inv:6 reset_check:4"),
        ("source_seen_preset_n", "inv:2 seen:4 loss:2 reset_check:2 seen_preset_pd:1"),
        ("source_seen_reset_allowed", "inv:9 reset_check:8"),
        ("source_seen_reset_d", "inv:8 seen:2 reset_d_pu:2"),
        ("q1", "seen_reset_pulse:13 seen:3"),
        ("cext1", "seen_reset_pulse:14 reset_c:2"),
        ("rext_cext1", "seen_reset_pulse:15 reset_r:2 reset_c:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static source pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong source membership on {net}")); }
    }
    for (id, pin, net) in [
        ("watchdog", "1", "selv3v3"), ("watchdog", "3", "selv3v3"),
        ("watchdog", "5", "selv3v3"), ("watchdog", "4", "selv_gnd"),
        ("watchdog", "9", "selv_gnd"), ("cwd", "2", "selv_gnd"),
        ("rail", "4", "selv3v3"), ("rail", "2", "selv_gnd"),
        ("seen", "1", "selv3v3"), ("permit", "4", "selv3v3"),
        ("seen_reset_pulse", "3", "selv3v3"),
        ("seen_reset_pulse", "9", "selv_gnd"),
        ("seen_reset_pulse", "11", "selv3v3"),
        ("wdi_pu", "1", "selv3v3"),
        ("wdi_pulse_r", "1", "selv3v3"),
        ("permit_q_pd", "2", "selv_gnd"),
        ("clear_pd", "2", "selv_gnd"),
        ("loss_pd", "2", "selv_gnd"),
        ("session_fb_pd", "2", "selv_gnd"),
        ("permit_fb_pd", "2", "selv_gnd"),
        ("prewatchdog_pd", "2", "selv_gnd"),
        ("health", "13", "selv3v3"),
    ] {
        if g.pins.get(&(id.into(), pin.into())).is_none_or(|found| found != net) {
            return Err(format!("source {id}.{pin} must be on {net}"));
        }
    }
    Ok(())
}

fn check_driver(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 17 { return Err(format!("expected 17 driver parts, found {}", g.parts.len())); }
    for (id, part) in [
        ("qualify", "SN74HCS21PWR"),
        ("release", "SN74LVC1G06DBVR"),
        ("shunt", "PMBT3904"),
        ("base_bias", "RC2512JK-073K3L"),
        ("base_pd", "RC0603FR-0747KL"),
        ("ena_pu", "RC1206FR-0710KL"),
        ("ena_pd", "RC0603FR-07100KL"),
        ("driver", "UCC27624DDAR"),
        ("c_driver_bulk", "GCM31CC71H475KA03L"),
        ("gate_r", "RC1206FR-0710RL"),
        ("stw", "STW65N65DM2AG"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != part) {
            return Err(format!("wrong driver part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("hot_logic5", "qualify:14 c_qualify:1 release:5 c_release:1"),
        ("aux_protected", "base_bias:1 ena_pu:1 driver:6 c_driver_hf:1 c_driver_bulk:1"),
        ("pfc_pwm", "driver:2 pwm_pd:1"),
        ("hot_run_q", "qualify:1"),
        ("hot_session_q", "qualify:2"),
        ("hot_permit", "qualify:4"),
        ("hot_prep_trip_ok", "qualify:5"),
        ("hot_receiver_abort_n", "qualify:10"),
        ("hot_prep_abort_ok", "qualify:12"),
        ("hot_source_stop_n", "qualify:13"),
        ("driver_first_and", "qualify:6 qualify:9"),
        ("driver_permission", "qualify:8 permission_pd:1 release:2"),
        ("en_shunt_base", "release:4 shunt:1 base_bias:2 base_pd:1"),
        ("ena_node", "shunt:3 ena_pu:2 ena_pd:1 driver:1"),
        ("outa", "driver:7 gate_r:1"),
        ("stw_gate", "gate_r:2 gate_pd:1 stw:1"),
        ("outb", "driver:5"),
        ("stw_drain", "stw:2"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong driver membership on {net}")); }
    }
    for (id, pin) in [
        ("qualify", "7"), ("permission_pd", "2"), ("c_qualify", "2"),
        ("release", "3"), ("c_release", "2"), ("shunt", "2"),
        ("base_pd", "2"), ("ena_pd", "2"), ("driver", "3"),
        ("driver", "9"), ("driver", "4"), ("driver", "8"),
        ("pwm_pd", "2"), ("c_driver_hf", "2"),
        ("c_driver_bulk", "2"), ("gate_pd", "2"), ("stw", "3"),
    ] {
        if g.pins.get(&(id.into(), pin.into())).is_none_or(|net| net != "hot0") {
            return Err(format!("driver {id}.{pin} must be HOT0"));
        }
    }
    Ok(())
}

fn check_hot_watchdog(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 4 { return Err(format!("expected 4 HOT watchdog parts, found {}", g.parts.len())); }
    for (id, part) in [
        ("watchdog", "TPS3431SDRBR"),
        ("cwd", "GRM1885C1H102JA01D"),
        ("wdo_pu", "RC0603FR-0710KL"),
        ("c_watchdog", "GRM188R71H104KA93D"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != part) {
            return Err(format!("wrong HOT watchdog part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("hot_logic5", "watchdog:1 watchdog:3 watchdog:5 wdo_pu:1 c_watchdog:1"),
        ("hot0", "watchdog:4 watchdog:9 cwd:2 c_watchdog:2"),
        ("hot_wdi", "watchdog:6"),
        ("hot_watchdog_ok", "watchdog:7 watchdog:8 wdo_pu:2"),
        ("hot_wd_cwd", "watchdog:2 cwd:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong HOT watchdog membership on {net}")); }
    }
    Ok(())
}

fn check_hot_rails(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 13 { return Err(format!("expected 13 HOT rail parts, found {}", g.parts.len())); }
    for (id, part) in [
        ("sup_logic", "TPS389001DSER"), ("sup_aux", "TPS389001DSER"),
        ("reset_pu", "RC0603FR-0710KL"),
        ("logic_top", "RC0603FR-07294KL"),
        ("aux_top", "RC0603FR-071M02L"),
        ("logic_bottom", "RC0603FR-07100KL"),
        ("aux_bottom", "RC0603FR-07100KL"),
        ("logic_iso", "RC0603FR-0747KL"),
        ("aux_iso", "RC0603FR-0747KL"),
        ("logic_ct", "GRM1885C1H101JA01D"),
        ("aux_ct", "GRM1885C1H101JA01D"),
        ("c_logic", "GRM188R71H104KA93D"),
        ("c_aux", "GRM188R71H104KA93D"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != part) {
            return Err(format!("wrong HOT rail part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("hot_logic5", "sup_logic:4 sup_aux:4 sup_logic:3 sup_aux:3 reset_pu:1 c_logic:1 c_aux:1 logic_top:1"),
        ("hot0", "sup_logic:2 sup_aux:2 c_logic:2 c_aux:2 logic_bottom:2 logic_ct:2 aux_bottom:2 aux_ct:2"),
        ("aux_protected", "aux_top:1"),
        ("hot_rails_ok", "sup_logic:6 sup_aux:6 reset_pu:2"),
        ("hot_logic_div", "logic_top:2 logic_bottom:1 logic_iso:1"),
        ("hot_logic_sense", "sup_logic:1 logic_iso:2"),
        ("hot_logic_ct", "sup_logic:5 logic_ct:1"),
        ("hot_aux_div", "aux_top:2 aux_bottom:1 aux_iso:1"),
        ("hot_aux_sense", "sup_aux:1 aux_iso:2"),
        ("hot_aux_ct", "sup_aux:5 aux_ct:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong HOT rail membership on {net}")); }
    }
    Ok(())
}

fn check_f2_detector(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 34 { return Err(format!("expected 34 F2 detector parts, found {}", g.parts.len())); }
    let mut expected_parts = BTreeMap::new();
    for side in ["vd", "vb"] {
        for index in 1..=4 { expected_parts.insert(format!("{side}_div.r{index}"), "TNPW1206200KBEEA"); }
        for (suffix, mpn) in [
            ("r5", "TNPW1206187KBEEA"), ("step", "TNPW1206200RBEEA"),
            ("bottom", "TNPW12065K62BEEA"), ("filter", "GRM1885C1H470JA01D"),
        ] { expected_parts.insert(format!("{side}_div.{suffix}"), mpn); }
    }
    for (id, mpn) in [
        ("reference", "LM4040A25IDBZR"), ("ref_bias", "RC0603FR-0710KL"),
        ("ref_bypass", "GRM188R71H104KA93D"),
        ("cmp_vd", "TLV3202IDR"), ("cmp_vb", "TLV3202IDR"),
        ("c_vd", "GRM188R71H104KA93D"), ("c_vb", "GRM188R71H104KA93D"),
        ("vd_ov_ref", "RC0603FR-0722KL"), ("vd_ov", "RC0603FR-0722KL"),
        ("vd_mismatch_p", "RC0603FR-0722KL"), ("vb_mismatch_n", "RC0603FR-0722KL"),
        ("vb_ov_ref", "RC0603FR-0722KL"), ("vb_ov", "RC0603FR-0722KL"),
        ("vb_mismatch_p", "RC0603FR-0722KL"), ("vd_mismatch_n", "RC0603FR-0722KL"),
        ("health", "SN74HCS21PWR"), ("c_health", "GRM188R71H104KA93D"),
        ("aux_window_pd", "RC0603FR-0710KL"),
    ] { expected_parts.insert(id.into(), mpn); }
    for (id, mpn) in expected_parts {
        if g.parts.get(&id).is_none_or(|found| found != mpn) {
            return Err(format!("wrong F2 detector part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("vd_local", "vd_div.r1:1"), ("vb_bank", "vb_div.r1:1"),
        ("hot_logic5", "ref_bias:1 cmp_vd:8 cmp_vb:8 c_vd:1 c_vb:1 health:14 health:12 health:13 c_health:1"),
        ("hot0", "vd_div.bottom:2 vd_div.filter:2 vb_div.bottom:2 vb_div.filter:2 reference:2 ref_bypass:2 cmp_vd:4 cmp_vb:4 c_vd:2 c_vb:2 health:7 c_health:2 aux_window_pd:2"),
        ("hot_fault_n", "health:8"),
        ("aux_window_ok", "health:10 aux_window_pd:1"),
        ("vdvb_health", "health:6 health:9"),
        ("ref25", "reference:1 ref_bias:2 ref_bypass:1 vd_ov_ref:1 vb_ov_ref:1"),
        ("vd_div-high", "vd_div.r5:2 vd_div.step:1 vd_div.filter:1 vd_ov:1 vd_mismatch_p:1"),
        ("vb_div-high", "vb_div.r5:2 vb_div.step:1 vb_div.filter:1 vb_ov:1 vb_mismatch_p:1"),
        ("vd_div-low", "vd_div.step:2 vd_div.bottom:1 vd_mismatch_n:1"),
        ("vb_div-low", "vb_div.step:2 vb_div.bottom:1 vb_mismatch_n:1"),
        ("cmp_vd-out1", "cmp_vd:1 health:1"),
        ("cmp_vd-out2", "cmp_vd:7 health:2"),
        ("cmp_vb-out1", "cmp_vb:1 health:4"),
        ("cmp_vb-out2", "cmp_vb:7 health:5"),
        ("cmp_vd-in1_n", "cmp_vd:2 vd_ov:2"),
        ("cmp_vd-in1_p", "cmp_vd:3 vd_ov_ref:2"),
        ("cmp_vd-in2_p", "cmp_vd:5 vd_mismatch_p:2"),
        ("cmp_vd-in2_n", "cmp_vd:6 vb_mismatch_n:2"),
        ("cmp_vb-in1_n", "cmp_vb:2 vb_ov:2"),
        ("cmp_vb-in1_p", "cmp_vb:3 vb_ov_ref:2"),
        ("cmp_vb-in2_p", "cmp_vb:5 vb_mismatch_p:2"),
        ("cmp_vb-in2_n", "cmp_vb:6 vd_mismatch_n:2"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong F2 detector membership on {net}")); }
    }
    for side in ["vd", "vb"] {
        for index in 1..=4 {
            let net = format!("{side}_div.r{index}-p2");
            let next = index + 1;
            let wanted = BTreeSet::from([
                (format!("{side}_div.r{index}"), "2".into()),
                (format!("{side}_div.r{next}"), "1".into()),
            ]);
            if members(g, &net) != wanted { return Err(format!("broken F2 {side} divider segment {index}")); }
        }
    }
    Ok(())
}

fn check_aux_window(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 11 { return Err(format!("expected 11 AUX window parts, found {}", g.parts.len())); }
    for (id, mpn) in [
        ("fast_top", "RC0603FR-07430KL"), ("fast_bottom", "RC0603FR-07100KL"),
        ("fast_iso", "RC0603FR-0722KL"), ("ov_top", "RC0603FR-07560KL"),
        ("ov_bottom", "RC0603FR-07100KL"), ("ov_iso", "RC0603FR-0722KL"),
        ("ov_ref", "RC0603FR-0722KL"), ("comparator", "TLV3202IDR"),
        ("c_comparator", "GRM188R71H104KA93D"),
        ("window", "SN74LVC1G08DBVR"), ("c_window", "GRM188R71H104KA93D"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != mpn) {
            return Err(format!("wrong AUX window part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("aux_protected", "fast_top:1 ov_top:1"),
        ("hot_logic5", "comparator:8 c_comparator:1 window:5 c_window:1"),
        ("hot0", "fast_bottom:2 ov_bottom:2 comparator:4 c_comparator:2 window:3 c_window:2"),
        ("ref25", "ov_ref:1 comparator:2"),
        ("aux_window_ok", "window:4"),
        ("aux_fast_div", "fast_top:2 fast_bottom:1 fast_iso:1"),
        ("aux_ov_div", "ov_top:2 ov_bottom:1 ov_iso:1"),
        ("in1_p", "fast_iso:2 comparator:3"),
        ("in2_n", "ov_iso:2 comparator:6"),
        ("in2_p", "ov_ref:2 comparator:5"),
        ("out1", "comparator:1 window:1"),
        ("out2", "comparator:7 window:2"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong AUX window membership on {net}")); }
    }
    Ok(())
}

fn check_pfc_control(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 24 { return Err(format!("expected 24 PFC control parts, found {}", g.parts.len())); }
    let mut expected_parts = BTreeMap::new();
    for index in 1..=5 { expected_parts.insert(format!("r_vtop{index}"), "CRCW2512200KFKEG"); }
    for (id, mpn) in [
        ("pfc", "UCC28180D"), ("shunt", "HCSM2818FT10L0"),
        ("r_isense", "RC1206FR-07220RL"), ("c_isense", "C0805C102J5GACTU"),
        ("isense_clamp", "BAV23C-E3-08"), ("r_freq", "RC1206FR-0716K2L"),
        ("c_icomp", "C0805C272J5GACTU"), ("r_vcomp", "RC1206FR-0740K2L"),
        ("c_vcomp", "GRM32ER71H475KA88L"), ("c_vcomp_p", "C0805C224K5RACTU"),
        ("c_vcc", "C0805C105K5RACTU"), ("r_vbottom", "RC1206FR-0713KL"),
        ("c_vfeed", "C0805C681J5GACTU"), ("q_inhibit", "AO3400A"),
        ("inhibit_pu", "RC1206FR-07100KL"), ("inhibit_pd", "RC1206FR-07100KL"),
        ("q_permit", "AO3400A"), ("permit_r", "RC1206FR-071KL"),
        ("permit_pd", "RC1206FR-07100KL"),
    ] { expected_parts.insert(id.into(), mpn); }
    for (id, mpn) in expected_parts {
        if g.parts.get(&id).is_none_or(|found| found != mpn) {
            return Err(format!("wrong PFC control part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("hot0", "pfc:1 shunt:1 c_isense:2 isense_clamp:1 r_freq:2 c_icomp:2 c_vcomp:2 c_vcomp_p:2 c_vcc:2 r_vbottom:2 c_vfeed:2 q_inhibit:2 inhibit_pd:2 q_permit:2 permit_pd:2"),
        ("aux_protected", "pfc:7 c_vcc:1 inhibit_pu:1"),
        ("vd_local", "r_vtop1:1"),
        ("rect_minus", "shunt:2 r_isense:1"),
        ("driver_permission", "permit_r:1"),
        ("pfc_pwm", "pfc:8"),
        ("vsense_node", "r_vtop5:2 pfc:6 r_vbottom:1 c_vfeed:1 q_inhibit:3"),
        ("inhibit_gate", "q_inhibit:1 inhibit_pu:2 inhibit_pd:1 q_permit:3"),
        ("permit_gate", "q_permit:1 permit_r:2 permit_pd:1"),
        ("icomp", "pfc:2 c_icomp:1"),
        ("isense", "pfc:3 r_isense:2 c_isense:1 isense_clamp:3"),
        ("freq", "pfc:4 r_freq:1"),
        ("vcomp", "pfc:5 r_vcomp:1 c_vcomp_p:1"),
        ("r_vcomp-p2", "r_vcomp:2 c_vcomp:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong PFC control membership on {net}")); }
    }
    for index in 1..=4 {
        let net = format!("r_vtop{index}-p2");
        let wanted = BTreeSet::from([
            (format!("r_vtop{index}"), "2".into()),
            (format!("r_vtop{}", index + 1), "1".into()),
        ]);
        if members(g, &net) != wanted { return Err(format!("broken PFC VSENSE ladder segment {index}")); }
    }
    Ok(())
}

fn check_pfc_power(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 15 { return Err(format!("expected 15 PFC power parts, found {}", g.parts.len())); }
    for (id, mpn) in [
        ("bridge", "GBJ2510-F"), ("l_boost", "760800301"),
        ("d_boost", "C3D20065D"), ("f2", "A70QS50-14F"),
        ("f2_vd_stud", "74651173R"), ("f2_vb_stud", "74651173R"),
        ("local_c", "B32776P6226K000"), ("hf_c", "B32672P6474K000"),
        ("bulk1", "LGX2W561MELC50"), ("bulk2", "LGX2W561MELC50"),
        ("bulk3", "LGX2W561MELC50"), ("bulk4", "LGX2W561MELC50"),
        ("bleed1", "RC2512FR-07150KL"), ("bleed2", "RC2512FR-07150KL"),
        ("bleed3", "RC2512FR-07150KL"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != mpn) {
            return Err(format!("wrong PFC power part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("ac_rect_l", "bridge:2"), ("ac_rect_n", "bridge:3"),
        ("hot0", "local_c:2 local_c:3 hf_c:2 bulk1:2 bulk2:2 bulk3:2 bulk4:2 bleed3:2"),
        ("rect_minus", "bridge:4"),
        ("boost_switch", "l_boost:2 d_boost:1 d_boost:3"),
        ("vd_local", "d_boost:2 f2:1 f2_vd_stud:1 local_c:1 local_c:4 hf_c:1"),
        ("vb_bank", "f2:2 f2_vb_stud:1 bulk1:1 bulk2:1 bulk3:1 bulk4:1 bleed1:1"),
        ("bleed1", "bleed1:2 bleed2:1"),
        ("bleed2", "bleed2:2 bleed3:1"),
        ("plus", "bridge:1 l_boost:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong PFC power membership on {net}")); }
    }
    Ok(())
}

fn check_ac_input(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 14 { return Err(format!("expected 14 AC input parts, found {}", g.parts.len())); }
    for (id, mpn) in [
        ("board_input", "1714984"),
        ("aux_branch", "1714971"),
        ("raw_aux", "IRM-20-24"),
        ("cmc", "B82726S2163N030"), ("ntc", "SL32 10015"),
        ("bypass", "RT33K012"), ("x2", "B32922C3224M289"),
        ("mov", "V150LA10AP"), ("y1", "VY1102M31Y5UQ63V0"),
        ("relay_gate_r", "RC1206FR-071KL"),
        ("relay_gate_pd", "RC1206FR-07100KL"),
        ("relay_fet", "AO3400A"), ("coil_drop", "RC2512FK-0791RL"),
        ("flyback", "SS14"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != mpn) {
            return Err(format!("wrong AC input part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("ac_n", "board_input:2 cmc:2 x2:2 mov:2"),
        ("pe", "board_input:3 y1:2"),
        ("hot0", "y1:1 relay_gate_pd:2 relay_fet:2 raw_aux:3"),
        ("aux_protected", "coil_drop:1"),
        ("hot_relay_enable", "relay_gate_r:1"),
        ("ac_rect_l", "ntc:2 bypass:3"),
        ("ac_rect_n", "cmc:3 raw_aux:2"),
        ("fused_l", "board_input:1 cmc:1 x2:1 mov:1"),
        ("cmc_l_out", "cmc:4 ntc:1 bypass:4 aux_branch:1"),
        ("aux_fused_l", "aux_branch:2 raw_aux:1"),
        ("raw_aux24", "raw_aux:4"),
        ("relay_coil_hi", "coil_drop:2 bypass:1 flyback:1"),
        ("relay_coil_lo", "relay_fet:3 bypass:2 flyback:2"),
        ("relay_gate", "relay_gate_r:2 relay_gate_pd:1 relay_fet:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong AC input membership on {net}")); }
    }
    Ok(())
}

fn check_hot15_converter(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 12 { return Err(format!("expected 12 HOT 15 V converter parts, found {}", g.parts.len())); }
    for (id, mpn) in [
        ("buck", "LMR36015BRNXT"),
        ("cin_a", "C3225X7R2A106K250AC"), ("cin_b", "C3225X7R2A106K250AC"),
        ("vin_hf_a", "C3216X7R2A224K115AA"), ("vin_hf_b", "C3216X7R2A224K115AA"),
        ("boot_c", "GRM188R71H104KA93D"), ("vcc_c", "C2012X7R1C105K125AA"),
        ("inductor", "XGL6060-183MEC"),
        ("cout_a", "C5750X7R1H226M250KB"), ("cout_b", "C5750X7R1H226M250KB"),
        ("fb_top", "ERA3AEB104V"), ("fb_bottom", "ERA3AEB7151V"),
    ] {
        if g.parts.get(id).is_none_or(|found| found != mpn) {
            return Err(format!("wrong HOT 15 V part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("raw_aux24", "buck:2 buck:10 buck:9 cin_a:1 cin_b:1 vin_hf_a:1 vin_hf_b:1"),
        ("hot0", "buck:1 buck:11 buck:6 buck:8 cin_a:2 cin_b:2 vin_hf_a:2 vin_hf_b:2 vcc_c:2 cout_a:2 cout_b:2 fb_bottom:2"),
        ("aux15_precut", "inductor:2 cout_a:1 cout_b:1 fb_top:1"),
        ("buck_sw", "buck:3 buck:12 boot_c:2 inductor:1"),
        ("buck_boot", "buck:4 boot_c:1"),
        ("buck_vcc", "buck:5 vcc_c:1"),
        ("buck_fb", "buck:7 fb_top:2 fb_bottom:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static HOT 15 V pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong HOT 15 V membership on {net}")); }
    }
    Ok(())
}

fn check_aux_cutoff(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 10 { return Err(format!("expected 10 AUX cutoff parts, found {}", g.parts.len())); }
    for (id, mpn) in [
        ("cutoff", "LTC4368HMS-2#PBF"), ("fets", "FDS3992"),
        ("sense", "WSL2512R0500FTA"),
        ("uv_top", "TNPU060320K0AWEN00"), ("uv_bottom", "TNPU0603806RAZEN00"),
        ("ov_top", "TNPU060320K0AWEN00"), ("ov_bottom", "TNPU0603590RAZEN00"),
        ("r_gate", "RC0603FR-0722KL"), ("c_gate", "GRM188R72A103KA01D"),
        ("c_out", "GCM31CC71H475KA03L"),
    ] {
        if g.parts.get(id).map(String::as_str) != Some(mpn) {
            return Err(format!("wrong AUX cutoff part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("aux15_precut", "cutoff:1 cutoff:6 fets:7 fets:8 uv_top:1 ov_top:1"),
        ("hot0", "cutoff:4 cutoff:5 uv_bottom:2 ov_bottom:2 c_gate:2 c_out:2"),
        ("aux_protected", "cutoff:8 sense:2 c_out:1"),
        ("uv_node", "cutoff:2 uv_top:2 uv_bottom:1"),
        ("ov_node", "cutoff:3 ov_top:2 ov_bottom:1"),
        ("fet_source", "fets:2 fets:4"),
        ("fet_gate", "cutoff:10 fets:1 fets:3 r_gate:1"),
        ("gate_cap_top", "r_gate:2 c_gate:1"),
        ("sense_upstream", "cutoff:9 fets:5 fets:6 sense:1"),
        ("fault", "cutoff:7"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static AUX cutoff pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong AUX cutoff membership on {net}")); }
    }
    Ok(())
}

fn check_hot_logic5_converter(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 13 { return Err(format!("expected 13 HOT logic5 parts, found {}", g.parts.len())); }
    for (id, mpn) in [
        ("buck", "TPS54202DDCR"),
        ("cin_a", "C3225X7R1H106K250AC"), ("cin_b", "C3225X7R1H106K250AC"),
        ("cin_hf", "GRM188R71H104KA93D"),
        ("en_top", "CRCW0603510KJNEA"), ("en_bottom", "CRCW0603105KFKEA"),
        ("boot_c", "GRM188R71H104KA93D"), ("inductor", "XGL6060-153MEC"),
        ("cout_a", "C3225X7R1E226M250AB"), ("cout_b", "C3225X7R1E226M250AB"),
        ("fb_top", "ERA3AEB104V"), ("fb_bottom", "ERA3AEB1332V"),
        ("fb_ff", "GRM1885C1H750JA01D"),
    ] {
        if g.parts.get(id).map(String::as_str) != Some(mpn) {
            return Err(format!("wrong HOT logic5 part identity for {id}"));
        }
    }
    for (net, expected) in [
        ("aux_protected", "buck:3 cin_a:1 cin_b:1 cin_hf:1 en_top:1"),
        ("hot0", "buck:1 cin_a:2 cin_b:2 cin_hf:2 en_bottom:2 cout_a:2 cout_b:2 fb_bottom:2"),
        ("hot_logic5", "inductor:2 cout_a:1 cout_b:1 fb_top:1 fb_ff:1"),
        ("buck_sw", "buck:2 boot_c:2 inductor:1"),
        ("buck_boot", "buck:6 boot_c:1"),
        ("buck_fb", "buck:4 fb_top:2 fb_bottom:1 fb_ff:2"),
        ("buck_en", "buck:5 en_top:2 en_bottom:1"),
    ] {
        let wanted: BTreeSet<(String, String)> = expected.split_whitespace().map(|pin| {
            let (id, number) = pin.split_once(':').expect("static HOT logic5 pin mapping");
            (id.to_owned(), number.to_owned())
        }).collect();
        if members(g, net) != wanted { return Err(format!("wrong HOT logic5 membership on {net}")); }
    }
    Ok(())
}

fn preserved_joined_nets(g: &Graph, standalone: &Graph, prefix: &str) -> Result<(), String> {
    let mut joined_nets: BTreeMap<&str, &str> = BTreeMap::new();
    for net in standalone.pins.values().collect::<BTreeSet<_>>() {
        let group: Vec<_> = standalone.pins.iter().filter(|(_, candidate)| candidate == &net)
            .map(|((id, pin), _)| (format!("{prefix}.{id}"), pin.clone())).collect();
        if let Some(first) = group.first().and_then(|pin| g.pins.get(pin)) {
            if group.iter().any(|pin| g.pins.get(pin) != Some(first)) {
                return Err(format!("joined {prefix} net split at {net}"));
            }
            if let Some(other) = joined_nets.insert(first, net) {
                return Err(format!("joined {prefix} nets {other} and {net} shorted"));
            }
        } else {
            return Err(format!("missing joined {prefix} net {net}"));
        }
    }
    Ok(())
}

fn check_source_mcu(g: &Graph) -> Result<(), String> {
    if g.parts.len() != 10 { return Err(format!("expected 10 source-port parts, found {}", g.parts.len())); }
    for (id, part) in [("controller_port", "43045-1612"), ("expander", "TCA6408AQPWRQ1"), ("start", "EVQ-P7A01P")] {
        if g.parts.get(id).map(String::as_str) != Some(part) { return Err(format!("wrong source MCU part {id}")); }
    }
    for (a, ap, b, bp) in [
        ("controller_port", "11", "expander", "15"),
        ("controller_port", "12", "expander", "14"),
        ("controller_port", "10", "start", "1"),
        ("controller_port", "10", "start_pu", "2"),
        ("expander", "3", "exp_reset_pu", "2"),
        ("expander", "4", "challenge_pd", "1"),
        ("expander", "5", "seen_request_pd", "1"),
        ("expander", "6", "relay_request_pd", "1"),
        ("expander", "2", "expander", "8"),
        ("controller_port", "1", "controller_port", "9"),
        ("controller_port", "8", "controller_port", "13"),
        ("controller_port", "8", "controller_port", "16"),
        ("controller_port", "1", "expander", "1"),
        ("controller_port", "9", "expander", "16"),
    ] {
        let left = g.pins.get(&(a.into(), ap.into()));
        let right = g.pins.get(&(b.into(), bp.into()));
        if left.is_none() || left != right { return Err(format!("missing source MCU pad join {a}.{ap} to {b}.{bp}")); }
    }
    Ok(())
}

fn check_integrated_with_mcu(g: &Graph, hot: &Graph, source: &Graph, source_mcu: &Graph, driver: &Graph, hot_wd: &Graph, rails: &Graph, f2: &Graph, aux: &Graph, pfc: &Graph, power: &Graph, ac: &Graph) -> Result<(), String> {
    let hot15 = load_stage("hot15_converter")?;
    check_hot15_converter(&hot15)?;
    let cutoff = load_stage("aux_cutoff")?;
    let logic5 = load_stage("hot_logic5_converter")?;
    check_aux_cutoff(&cutoff)?;
    check_hot_logic5_converter(&logic5)?;
    if g.parts.len() != hot.parts.len() + source.parts.len() + source_mcu.parts.len() + driver.parts.len() + hot_wd.parts.len() + rails.parts.len() + f2.parts.len() + aux.parts.len() + pfc.parts.len() + power.parts.len() + ac.parts.len() + hot15.parts.len() + cutoff.parts.len() + logic5.parts.len() {
        return Err("joined part count differs from the standalone fixtures".into());
    }
    for (prefix, standalone) in [("receiver", hot), ("source", source), ("source_mcu", source_mcu), ("driver", driver), ("hot_watchdog", hot_wd), ("hot_rails", rails), ("f2_detector", f2), ("aux_window", aux), ("pfc_control", pfc), ("pfc_power", power), ("ac_input", ac), ("hot15_converter", &hot15), ("aux_cutoff", &cutoff), ("hot_logic5_converter", &logic5)] {
        for (id, part) in &standalone.parts {
            if g.parts.get(&format!("{prefix}.{id}")) != Some(part) {
                return Err(format!("joined part identity differs at {prefix}.{id}"));
            }
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("source.permit", "5", "receiver.iso_protocol", "4"),
        ("source.health", "6", "receiver.iso_feedback", "3"),
        ("source.stop_pd", "1", "receiver.iso_feedback", "4"),
        ("source.permit_fb_pd", "1", "receiver.iso_feedback", "5"),
        ("source.session_fb_pd", "1", "receiver.iso_feedback", "6"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing source/receiver join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("source_mcu.controller_port", "2", "source.stop_pd", "1"),
        ("source_mcu.controller_port", "3", "source.heartbeat_pd", "1"),
        ("source_mcu.controller_port", "4", "source.permit_set_pd", "1"),
        ("source_mcu.controller_port", "5", "source.prewatchdog_pd", "1"),
        ("source_mcu.controller_port", "6", "receiver.iso_protocol", "3"),
        ("source_mcu.controller_port", "7", "receiver.iso_protocol", "6"),
        ("source_mcu.controller_port", "14", "source.reset_good_pd", "1"),
        ("source_mcu.controller_port", "15", "source.interlock_pd", "1"),
        ("source_mcu.expander", "4", "source.challenge_pd", "1"),
        ("source_mcu.expander", "5", "source.seen_reset_pd", "1"),
        ("source_mcu.expander", "6", "receiver.iso_protocol", "5"),
        ("source_mcu.expander", "7", "source.rail", "6"),
        ("source_mcu.expander", "9", "source.permit", "5"),
        ("source_mcu.expander", "10", "receiver.iso_feedback", "5"),
        ("source_mcu.expander", "11", "receiver.iso_feedback", "6"),
        ("source_mcu.expander", "12", "source.seen", "5"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing source MCU join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("driver.qualify", "1", "receiver.run_memory", "5"),
        ("driver.qualify", "2", "receiver.session_memory", "5"),
        ("driver.qualify", "4", "receiver.iso_protocol", "13"),
        ("driver.qualify", "5", "receiver.prep_trip_and", "8"),
        ("driver.qualify", "10", "receiver.rx", "13"),
        ("driver.qualify", "12", "receiver.prep_abort_memory", "6"),
        ("driver.qualify", "13", "receiver.iso_feedback", "13"),
        ("driver.release", "5", "receiver.rx", "28"),
        ("driver.shunt", "2", "receiver.rx", "19"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing receiver/driver join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("hot_watchdog.watchdog", "1", "receiver.rx", "28"),
        ("hot_watchdog.watchdog", "4", "receiver.rx", "19"),
        ("hot_watchdog.watchdog", "6", "receiver.rx", "16"),
        ("hot_watchdog.watchdog", "7", "receiver.prep_trip_and", "12"),
        ("hot_watchdog.watchdog", "8", "receiver.watchdog_ok_pd", "1"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing HOT watchdog join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("hot_rails.sup_logic", "4", "receiver.rx", "28"),
        ("hot_rails.sup_logic", "2", "receiver.rx", "19"),
        ("hot_rails.sup_logic", "6", "receiver.prep_trip_and", "5"),
        ("hot_rails.sup_aux", "6", "receiver.rails_pd", "1"),
        ("hot_rails.aux_top", "1", "driver.driver", "6"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing HOT rail join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("f2_detector.cmp_vd", "8", "receiver.rx", "28"),
        ("f2_detector.cmp_vd", "4", "receiver.rx", "19"),
        ("f2_detector.health", "8", "receiver.prep_trip_and", "10"),
        ("f2_detector.health", "8", "receiver.fault_n_pd", "1"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing F2 detector join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("aux_window.fast_top", "1", "driver.driver", "6"),
        ("aux_window.comparator", "8", "receiver.rx", "28"),
        ("aux_window.comparator", "4", "receiver.rx", "19"),
        ("aux_window.comparator", "2", "f2_detector.reference", "1"),
        ("aux_window.window", "4", "f2_detector.health", "10"),
        ("aux_window.window", "4", "f2_detector.aux_window_pd", "1"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing AUX window join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("pfc_control.pfc", "1", "receiver.rx", "19"),
        ("pfc_control.pfc", "7", "driver.driver", "6"),
        ("pfc_control.r_vtop1", "1", "f2_detector.vd_div.r1", "1"),
        ("pfc_control.permit_r", "1", "driver.qualify", "8"),
        ("pfc_control.pfc", "8", "driver.driver", "2"),
        ("driver.stw", "3", "receiver.rx", "19"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing PFC control join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("pfc_power.bridge", "4", "pfc_control.shunt", "2"),
        ("pfc_power.d_boost", "1", "driver.stw", "2"),
        ("pfc_power.d_boost", "3", "driver.stw", "2"),
        ("pfc_power.d_boost", "2", "f2_detector.vd_div.r1", "1"),
        ("pfc_power.f2", "2", "f2_detector.vb_div.r1", "1"),
        ("pfc_power.local_c", "2", "receiver.rx", "19"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing PFC power join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("ac_input.ntc", "2", "pfc_power.bridge", "2"),
        ("ac_input.cmc", "3", "pfc_power.bridge", "3"),
        ("ac_input.y1", "1", "receiver.rx", "19"),
        ("ac_input.coil_drop", "1", "driver.driver", "6"),
        ("ac_input.relay_gate_r", "1", "receiver.run_and", "8"),
        ("ac_input.raw_aux", "4", "hot15_converter.buck", "2"),
        ("ac_input.raw_aux", "3", "hot15_converter.buck", "1"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing AC input join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    for (left_id, left_pin, right_id, right_pin) in [
        ("hot15_converter.inductor", "2", "aux_cutoff.cutoff", "1"),
        ("aux_cutoff.cutoff", "8", "driver.driver", "6"),
        ("aux_cutoff.cutoff", "8", "hot_logic5_converter.buck", "3"),
        ("hot_logic5_converter.inductor", "2", "receiver.rx", "28"),
        ("aux_cutoff.cutoff", "5", "receiver.rx", "19"),
        ("hot_logic5_converter.buck", "1", "receiver.rx", "19"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing AUX/logic5 join {left_id}.{left_pin} to {right_id}.{right_pin}"));
        }
    }
    let precut = g.pins.get(&("aux_cutoff.cutoff".into(), "1".into()));
    let protected = g.pins.get(&("aux_cutoff.cutoff".into(), "8".into()));
    let logic5_out = g.pins.get(&("hot_logic5_converter.inductor".into(), "2".into()));
    if precut.is_none() || precut == protected || protected == logic5_out || precut == logic5_out {
        return Err("AUX cutoff or 5 V conversion bypassed".into());
    }
    // Net names change at module boundaries. Internal conductors must stay
    // intact and two previously distinct conductors must not become one.
    preserved_joined_nets(g, source, "source")?;
    preserved_joined_nets(g, source_mcu, "source_mcu")?;
    preserved_joined_nets(g, driver, "driver")?;
    preserved_joined_nets(g, hot_wd, "hot_watchdog")?;
    preserved_joined_nets(g, rails, "hot_rails")?;
    preserved_joined_nets(g, f2, "f2_detector")?;
    preserved_joined_nets(g, aux, "aux_window")?;
    preserved_joined_nets(g, pfc, "pfc_control")?;
    preserved_joined_nets(g, power, "pfc_power")?;
    preserved_joined_nets(g, ac, "ac_input")?;
    preserved_joined_nets(g, &hot15, "hot15_converter")?;
    preserved_joined_nets(g, &cutoff, "aux_cutoff")?;
    preserved_joined_nets(g, &logic5, "hot_logic5_converter")?;
    for (left_id, left_pin, right_id, right_pin) in [
        ("receiver.iso_protocol", "13", "receiver.rx", "10"),
        ("receiver.iso_feedback", "12", "receiver.iso_protocol", "13"),
        ("receiver.iso_feedback", "11", "receiver.session_memory", "5"),
    ] {
        let left = g.pins.get(&(left_id.into(), left_pin.into()));
        let right = g.pins.get(&(right_id.into(), right_pin.into()));
        if left.is_none() || left != right {
            return Err(format!("missing HOT physical feedback join {left_id}.{left_pin}"));
        }
    }
    let mut net_domains: BTreeMap<&str, &str> = BTreeMap::new();
    for ((id, pin), net) in &g.pins {
        let side = if id.starts_with("source.") || id.starts_with("source_mcu.")
            || matches!(id.as_str(), "receiver.c_iso1_selv" | "receiver.c_iso2_selv"
                | "receiver.source_permit_fb_pd" | "receiver.source_session_fb_pd")
            || matches!(id.as_str(), "receiver.iso_protocol" | "receiver.iso_feedback")
                && pin.parse::<u8>().is_ok_and(|n| n <= 8)
        { "SELV" } else { "HOT" };
        if net_domains.insert(net, side).is_some_and(|old| old != side) {
            return Err(format!("{net} crosses the joined SELV/HOT boundary"));
        }
    }
    Ok(())
}

#[cfg(test)]
fn check_integrated(g: &Graph, hot: &Graph, source: &Graph, driver: &Graph, hot_wd: &Graph, rails: &Graph, f2: &Graph, aux: &Graph, pfc: &Graph, power: &Graph, ac: &Graph) -> Result<(), String> {
    let source_mcu = load_stage("source_mcu")?;
    check_integrated_with_mcu(g, hot, source, &source_mcu, driver, hot_wd, rails, f2, aux, pfc, power, ac)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() > 1 {
        if args.len() == 6 && args[1] == "--assembly-harness" {
            let rev38 = with_bom_parts(
                graph(&fs::read_to_string(&args[2]).expect("Rev38 netlist")).expect("Rev38 graph"),
                &args[3],
            ).expect("Rev38 BOM identity");
            let cooker = with_bom_parts(
                graph(&fs::read_to_string(&args[4]).expect("cooker mate netlist")).expect("cooker mate graph"),
                &args[5],
            ).expect("cooker mate BOM identity");
            check_cooker_rev38_harness(&rev38, &cooker).expect("16-contact assembly harness audit");
            println!("two-source 16-contact straight-through harness contract PASS; physical harness NOT RUN");
            return;
        }
        if args.len() != 4 || args[1] != "--cooker-mate" {
            panic!("usage: audit [--cooker-mate NETLIST BOM | --assembly-harness REV38_NET REV38_BOM COOKER_NET COOKER_BOM]");
        }
        let netlist = fs::read_to_string(&args[2]).expect("cooker mate netlist");
        let cooker = with_bom_parts(graph(&netlist).expect("cooker mate netlist graph"), &args[3])
            .expect("cooker mate BOM identity");
        check_cooker_mate(&cooker).expect("cooker mate exact-pin audit");
        println!("cooker mate compiled exact-pin audit PASS; reset/interlock producers joined");
        return;
    }
    let hot = load_stage("isolation").expect("isolation netlist/BOM");
    let source = load_stage("source").expect("source netlist/BOM");
    let source_mcu = load_stage("source_mcu").expect("source MCU netlist/BOM");
    let driver = load_stage("driver").expect("driver netlist/BOM");
    let hot_wd = load_stage("hot_watchdog").expect("HOT watchdog netlist/BOM");
    let rails = load_stage("hot_rails").expect("HOT rail netlist/BOM");
    let f2 = load_stage("f2_detector").expect("F2 detector netlist/BOM");
    let aux = load_stage("aux_window").expect("AUX window netlist/BOM");
    let pfc = load_stage("pfc_control").expect("PFC control netlist/BOM");
    let power = load_stage("pfc_power").expect("PFC power netlist/BOM");
    let ac = load_stage("ac_input").expect("AC input netlist/BOM");
    let hot15 = load_stage("hot15_converter").expect("HOT 15 V netlist/BOM");
    let cutoff = load_stage("aux_cutoff").expect("AUX cutoff netlist/BOM");
    let logic5 = load_stage("hot_logic5_converter").expect("HOT logic5 netlist/BOM");
    let integrated = joined_bom_graph().expect("joined BOM identity");
    check(&hot).expect("isolation pin audit");
    check_source(&source).expect("source pin audit");
    check_source_mcu(&source_mcu).expect("source MCU pin audit");
    check_driver(&driver).expect("driver pin audit");
    check_hot_watchdog(&hot_wd).expect("HOT watchdog pin audit");
    check_hot_rails(&rails).expect("HOT rail pin audit");
    check_f2_detector(&f2).expect("F2 detector pin audit");
    check_aux_window(&aux).expect("AUX window pin audit");
    check_pfc_control(&pfc).expect("PFC control pin audit");
    check_pfc_power(&power).expect("PFC power pin audit");
    check_ac_input(&ac).expect("AC input pin audit");
    check_hot15_converter(&hot15).expect("HOT 15 V pin audit");
    check_aux_cutoff(&cutoff).expect("AUX cutoff pin audit");
    check_hot_logic5_converter(&logic5).expect("HOT logic5 pin audit");
    check_integrated_with_mcu(&integrated, &hot, &source, &source_mcu, &driver, &hot_wd, &rails, &f2, &aux, &pfc, &power, &ac).expect("Rev38 join audit");
    println!("partial Rev38 joined source/receiver/AC/PFC/driver/AUX/logic5 pin audit PASS");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cooker_mate_fixture() -> Graph {
        let mut g = Graph { parts: BTreeMap::new(), pins: BTreeMap::new(), references: BTreeMap::new() };
        g.parts.insert("rev38_mate".into(), "43045-1612".into());
        g.parts.insert("cooker.mcu.mcu".into(), "ESP32-S3-WROOM-1-N8R8".into());
        g.parts.insert("cooker.mcu.r_sda_pullup".into(), "RC0603FR-074K7L".into());
        g.parts.insert("cooker.mcu.r_scl_pullup".into(), "RC0603FR-074K7L".into());
        g.parts.insert("cooker.aux_supply.psu".into(), "IRM-10-15".into());
        g.parts.insert("cooker.power_mgmt.buck_3v3.buck".into(), "LMR51430XDDCR".into());
        g.parts.insert("cooker.power_mgmt.buck_3v3.l_out".into(), "SRP1265A-5R6M".into());
        for (id, mpn) in [
            ("supervisor", "TPS389001DSER"),
            ("reset_buffer", "SN74LVC1G17DBVR"),
            ("fault_inverter", "SN74LVC1G04DBVR"),
            ("reset_and", "SN74LVC1G08DBVR"),
            ("interlock_and", "SN74LVC1G08DBVR"),
            ("rail_top", "RC0603FR-0716KL"),
            ("rail_bottom", "RC0603FR-0710KL"),
            ("reset_pullup", "RC0603FR-0710KL"),
            ("runaway_pulldown", "RC0603FR-0710KL"),
            ("reset_delay", "GRM188R71H104KA93D"),
            ("supervisor_bypass", "GRM188R71H104KA93D"),
            ("reset_buffer_bypass", "GRM188R71H104KA93D"),
            ("fault_inverter_bypass", "GRM188R71H104KA93D"),
            ("reset_and_bypass", "GRM188R71H104KA93D"),
            ("interlock_and_bypass", "GRM188R71H104KA93D"),
        ] { g.parts.insert(id.into(), mpn.into()); }
        let groups: &[(&str, &[(&str, &str)])] = &[
            ("vcc", &[("rev38_mate", "1"), ("rev38_mate", "9"), ("cooker.mcu.mcu", "2"), ("cooker.mcu.r_sda_pullup", "1"), ("cooker.mcu.r_scl_pullup", "1"), ("cooker.power_mgmt.buck_3v3.l_out", "2"), ("supervisor", "4"), ("reset_buffer", "5"), ("fault_inverter", "5"), ("reset_and", "5"), ("interlock_and", "5"), ("rail_top", "1"), ("reset_pullup", "1"), ("supervisor_bypass", "1"), ("reset_buffer_bypass", "1"), ("fault_inverter_bypass", "1"), ("reset_and_bypass", "1"), ("interlock_and_bypass", "1")]),
            ("gnd", &[("rev38_mate", "8"), ("rev38_mate", "13"), ("rev38_mate", "16"), ("cooker.mcu.mcu", "1"), ("cooker.mcu.mcu", "40"), ("cooker.mcu.mcu", "41"), ("cooker.aux_supply.psu", "4"), ("cooker.power_mgmt.buck_3v3.buck", "1"), ("supervisor", "2"), ("reset_buffer", "3"), ("fault_inverter", "3"), ("reset_and", "3"), ("interlock_and", "3"), ("rail_bottom", "2"), ("runaway_pulldown", "2"), ("reset_delay", "2"), ("supervisor_bypass", "2"), ("reset_buffer_bypass", "2"), ("fault_inverter_bypass", "2"), ("reset_and_bypass", "2"), ("interlock_and_bypass", "2")]),
            ("selv15", &[("cooker.aux_supply.psu", "3"), ("cooker.power_mgmt.buck_3v3.buck", "3"), ("cooker.power_mgmt.buck_3v3.buck", "5")]),
            ("stop", &[("rev38_mate", "2"), ("cooker.mcu.mcu", "21")]),
            ("heartbeat", &[("rev38_mate", "3"), ("cooker.mcu.mcu", "23")]),
            ("permit", &[("rev38_mate", "4"), ("cooker.mcu.mcu", "25")]),
            ("prewatchdog", &[("rev38_mate", "5"), ("cooker.mcu.mcu", "11")]),
            ("command", &[("rev38_mate", "6"), ("cooker.mcu.mcu", "33")]),
            ("response", &[("rev38_mate", "7"), ("cooker.mcu.mcu", "34")]),
            ("start", &[("rev38_mate", "10"), ("cooker.mcu.mcu", "35")]),
            ("sda", &[("rev38_mate", "11"), ("cooker.mcu.mcu", "31"), ("cooker.mcu.r_sda_pullup", "2")]),
            ("scl", &[("rev38_mate", "12"), ("cooker.mcu.mcu", "32"), ("cooker.mcu.r_scl_pullup", "2")]),
            ("reset_good", &[("rev38_mate", "14"), ("reset_buffer", "4"), ("reset_and", "1")]),
            ("interlock_n", &[("rev38_mate", "15"), ("interlock_and", "4")]),
            ("reset_request", &[("cooker.mcu.mcu", "22"), ("cooker.safety.fault_any_or", "4"), ("supervisor", "6"), ("reset_pullup", "2"), ("reset_buffer", "2"), ("reset_and", "2")]),
            ("sense", &[("rail_top", "2"), ("rail_bottom", "1"), ("supervisor", "1")]),
            ("delay", &[("reset_delay", "1"), ("supervisor", "5")]),
            ("inverted", &[("fault_inverter", "4"), ("interlock_and", "2")]),
            ("reset_and_out", &[("reset_and", "4"), ("interlock_and", "1")]),
            ("en", &[("supervisor", "3"), ("cooker.mcu.mcu", "3"), ("cooker.mcu.r_en", "2"), ("cooker.mcu.c_en", "1"), ("cooker.mcu.btn_reset", "1")]),
            ("shutdown", &[("fault_inverter", "2"), ("cooker.safety.latch", "6"), ("cooker.safety.latch", "10"), ("cooker.hb.gate_hs.driver", "5"), ("cooker.mcu.mcu", "10"), ("cooker.safety.tp_shutdown", "1"), ("cooker.safety.tp_fault", "1")]),
            ("runaway", &[("runaway_pulldown", "1"), ("cooker.mcu.mcu", "8"), ("cooker.safety.fault_or", "5")]),
        ];
        for (net, pins) in groups {
            for (id, pin) in *pins {
                g.pins.insert(((*id).into(), (*pin).into()), (*net).into());
            }
        }
        g
    }

    #[test]
    fn cooker_mate_exact_pin_contract_passes() {
        check_cooker_mate(&cooker_mate_fixture()).unwrap();
    }

    #[test]
    fn cooker_mate_rejects_stop_and_start_swap() {
        let mut g = cooker_mate_fixture();
        let stop = g.pins[&("cooker.mcu.mcu".into(), "21".into())].clone();
        let start = g.pins[&("cooker.mcu.mcu".into(), "35".into())].clone();
        g.pins.insert(("cooker.mcu.mcu".into(), "21".into()), start);
        g.pins.insert(("cooker.mcu.mcu".into(), "35".into()), stop);
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_extra_interlock_driver() {
        let mut g = cooker_mate_fixture();
        let net = g.pins[&("rev38_mate".into(), "15".into())].clone();
        g.pins.insert(("cooker.mcu.mcu".into(), "39".into()), net);
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_reset_supervisor_disconnected_from_latch() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("supervisor".into(), "6".into()), "orphan".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_reset_request_bypassing_interlock() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("reset_and".into(), "2".into()), "vcc".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_wrong_latch_polarity_source() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("fault_inverter".into(), "2".into()), "orphan".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_en_monitor_bypass() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("supervisor".into(), "3".into()), "vcc".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_missing_runaway_default() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("runaway_pulldown".into(), "1".into()), "orphan".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_added_stop_pullup() {
        let mut g = cooker_mate_fixture();
        let net = g.pins[&("rev38_mate".into(), "2".into())].clone();
        g.pins.insert(("cooker.mcu.r_en".into(), "2".into()), net);
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_orphaned_cooker_rail_producer() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("cooker.power_mgmt.buck_3v3.l_out".into(), "2".into()), "orphan".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_orphaned_cooker_rail_return() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("cooker.aux_supply.psu".into(), "4".into()), "orphan".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn cooker_mate_rejects_orphaned_15v_source() {
        let mut g = cooker_mate_fixture();
        g.pins.insert(("cooker.aux_supply.psu".into(), "3".into()), "orphan".into());
        assert!(check_cooker_mate(&g).is_err());
    }

    #[test]
    fn netlist_rejects_duplicate_name_for_disconnected_nets() {
        let input = r#"(export
          (components
            (comp (ref "U1") (sheetpath (names "Top::esp")) (libsource (part "ESP")))
            (comp (ref "J1") (sheetpath (names "Top::port")) (libsource (part "PORT"))))
          (nets
            (net (code "1") (name "stop_n") (node (ref "U1") (pin "21")))
            (net (code "2") (name "stop_n") (node (ref "J1") (pin "2")))))"#;
        assert!(graph(input).is_err());
    }

    fn fixture() -> Graph {
        load_stage("isolation").unwrap()
    }

    fn source_fixture() -> Graph {
        load_stage("source").unwrap()
    }

    fn source_mcu_fixture() -> Graph {
        load_stage("source_mcu").unwrap()
    }

    fn driver_fixture() -> Graph {
        load_stage("driver").unwrap()
    }

    fn hot_watchdog_fixture() -> Graph {
        load_stage("hot_watchdog").unwrap()
    }

    fn hot_rails_fixture() -> Graph {
        load_stage("hot_rails").unwrap()
    }

    fn f2_fixture() -> Graph {
        load_stage("f2_detector").unwrap()
    }

    fn aux_fixture() -> Graph {
        load_stage("aux_window").unwrap()
    }

    fn pfc_fixture() -> Graph {
        load_stage("pfc_control").unwrap()
    }

    fn power_fixture() -> Graph {
        load_stage("pfc_power").unwrap()
    }

    fn ac_fixture() -> Graph {
        load_stage("ac_input").unwrap()
    }

    fn integrated_fixture() -> Graph {
        joined_bom_graph().unwrap()
    }

    #[test]
    fn joined_part_identity_comes_from_bom() {
        let mut netlist = graph(&fs::read_to_string("build/integrated.net").unwrap()).unwrap();
        netlist.parts.insert("source.reset_good_pd".into(), "WRONG_ALIAS".into());
        let joined = with_bom_parts(netlist, "build/integrated.csv").unwrap();
        assert_eq!(joined.parts.get("source.reset_good_pd").map(String::as_str),
                   Some("RC0603FR-0710KL"));
    }

    fn hot15_fixture() -> Graph {
        load_stage("hot15_converter").unwrap()
    }

    fn cutoff_fixture() -> Graph {
        load_stage("aux_cutoff").unwrap()
    }

    fn logic5_fixture() -> Graph {
        load_stage("hot_logic5_converter").unwrap()
    }

    #[test]
    fn compiled_source_receiver_join_passes() {
        check_integrated(&integrated_fixture(), &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).unwrap();
    }

    #[test]
    fn compiled_aux_cutoff_and_logic5_pins_pass() {
        check_aux_cutoff(&cutoff_fixture()).unwrap();
        check_hot_logic5_converter(&logic5_fixture()).unwrap();
    }

    #[test]
    fn cutoff_pre_and_post_short_is_rejected() {
        let mut g = integrated_fixture();
        let precut = g.pins[&("aux_cutoff.cutoff".into(), "1".into())].clone();
        g.pins.insert(("aux_cutoff.cutoff".into(), "8".into()), precut);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(),
            &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(),
            &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn cutoff_sense_bypass_is_rejected() {
        let mut g = cutoff_fixture();
        let output = g.pins[&("sense".into(), "2".into())].clone();
        g.pins.insert(("sense".into(), "1".into()), output);
        assert!(check_aux_cutoff(&g).is_err());
    }

    #[test]
    fn cutoff_gate_disconnect_is_rejected() {
        let mut g = cutoff_fixture();
        g.pins.insert(("fets".into(), "3".into()), "open_gate".into());
        assert!(check_aux_cutoff(&g).is_err());
    }

    #[test]
    fn cutoff_uv_ov_swap_is_rejected() {
        let mut g = cutoff_fixture();
        let ov = g.pins[&("cutoff".into(), "3".into())].clone();
        g.pins.insert(("cutoff".into(), "2".into()), ov);
        assert!(check_aux_cutoff(&g).is_err());
    }

    #[test]
    fn logic5_switch_output_short_is_rejected() {
        let mut g = logic5_fixture();
        let output = g.pins[&("inductor".into(), "2".into())].clone();
        g.pins.insert(("buck".into(), "2".into()), output);
        assert!(check_hot_logic5_converter(&g).is_err());
    }

    #[test]
    fn logic5_input_pre_cutoff_bypass_is_rejected() {
        let mut g = integrated_fixture();
        let precut = g.pins[&("aux_cutoff.cutoff".into(), "1".into())].clone();
        g.pins.insert(("hot_logic5_converter.buck".into(), "3".into()), precut);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(),
            &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(),
            &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn hot15_switch_to_output_inductor_bypass_is_rejected() {
        let mut g = hot15_fixture();
        g.pins.insert(("inductor".into(), "2".into()), "buck_sw".into());
        assert!(check_hot15_converter(&g).is_err());
    }

    #[test]
    fn hot15_feedback_ground_swap_is_rejected() {
        let mut g = hot15_fixture();
        g.pins.insert(("fb_top".into(), "2".into()), "hot0".into());
        assert!(check_hot15_converter(&g).is_err());
    }

    #[test]
    fn hot15_nc_to_switch_open_is_rejected() {
        let mut g = hot15_fixture();
        g.pins.insert(("buck".into(), "3".into()), "open_nc".into());
        assert!(check_hot15_converter(&g).is_err());
    }

    #[test]
    fn hot15_part_substitution_is_rejected() {
        let mut g = hot15_fixture();
        g.parts.insert("buck".into(), "LMR36015FBRNXT".into());
        assert!(check_hot15_converter(&g).is_err());
    }

    #[test]
    fn joined_hot15_raw_feed_bypass_is_rejected() {
        let mut g = integrated_fixture();
        let precut = g.pins[&("hot15_converter.inductor".into(), "2".into())].clone();
        g.pins.insert(("hot15_converter.buck".into(), "2".into()), precut);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(),
            &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(),
            &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn compiled_source_mcu_pin_fixture_passes() {
        let g = source_mcu_fixture();
        check_source_mcu(&g).unwrap();
        assert!(!g.parts.values().any(|mpn| mpn.starts_with("ESP32-S3-WROOM")));
    }

    #[test]
    fn source_mcu_uart_pad_swap_is_rejected() {
        let mut g = integrated_fixture();
        let tx = g.pins.get(&(String::from("source_mcu.controller_port"), String::from("6"))).unwrap().clone();
        let rx = g.pins.get(&(String::from("source_mcu.controller_port"), String::from("7"))).unwrap().clone();
        g.pins.insert(("source_mcu.controller_port".into(), "6".into()), rx);
        g.pins.insert(("source_mcu.controller_port".into(), "7".into()), tx);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn source_controller_reset_and_interlock_swap_is_rejected() {
        let mut g = integrated_fixture();
        let reset = g.pins[&("source_mcu.controller_port".into(), "14".into())].clone();
        let interlock = g.pins[&("source_mcu.controller_port".into(), "15".into())].clone();
        g.pins.insert(("source_mcu.controller_port".into(), "14".into()), interlock);
        g.pins.insert(("source_mcu.controller_port".into(), "15".into()), reset);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(),
            &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(),
            &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn source_controller_power_return_short_is_rejected() {
        let mut g = source_mcu_fixture();
        let supply = g.pins[&("controller_port".into(), "1".into())].clone();
        g.pins.insert(("controller_port".into(), "8".into()), supply);
        assert!(check_source_mcu(&g).is_err());
    }

    #[test]
    fn compiled_driver_passes() { check_driver(&driver_fixture()).unwrap(); }

    #[test]
    fn compiled_hot_watchdog_passes() { check_hot_watchdog(&hot_watchdog_fixture()).unwrap(); }

    #[test]
    fn compiled_hot_rails_passes() { check_hot_rails(&hot_rails_fixture()).unwrap(); }

    #[test]
    fn compiled_f2_detector_passes() { check_f2_detector(&f2_fixture()).unwrap(); }

    #[test]
    fn compiled_aux_window_passes() { check_aux_window(&aux_fixture()).unwrap(); }

    #[test]
    fn compiled_pfc_control_passes() { check_pfc_control(&pfc_fixture()).unwrap(); }

    #[test]
    fn compiled_pfc_power_passes() { check_pfc_power(&power_fixture()).unwrap(); }

    #[test]
    fn compiled_ac_input_passes() { check_ac_input(&ac_fixture()).unwrap(); }

    #[test]
    fn ac_fused_board_terminal_disconnect_fails() {
        let mut g = ac_fixture();
        g.pins.insert(("board_input".into(), "1".into()), "unfused_l".into());
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_aux_branch_fuse_bypass_fails() {
        let mut g = ac_fixture();
        let send = g.pins[&("aux_branch".into(), "1".into())].clone();
        g.pins.insert(("aux_branch".into(), "2".into()), send);
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_aux_branch_return_disconnect_fails() {
        let mut g = ac_fixture();
        g.pins.remove(&("aux_branch".into(), "2".into()));
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_raw_aux_input_bypass_fails() {
        let mut g = ac_fixture();
        let send = g.pins[&("aux_branch".into(), "1".into())].clone();
        g.pins.insert(("raw_aux".into(), "1".into()), send);
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_raw_aux_hot_return_disconnect_fails() {
        let mut g = ac_fixture();
        g.pins.insert(("raw_aux".into(), "3".into()), "raw_aux_return_cut".into());
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_raw_aux_polarity_swap_fails() {
        let mut g = ac_fixture();
        let positive = g.pins[&("raw_aux".into(), "4".into())].clone();
        let negative = g.pins[&("raw_aux".into(), "3".into())].clone();
        g.pins.insert(("raw_aux".into(), "3".into()), positive);
        g.pins.insert(("raw_aux".into(), "4".into()), negative);
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_ntc_precharge_bypass_fails() {
        let mut g = ac_fixture();
        g.pins.insert(("ntc".into(), "1".into()), "ac_rect_l".into());
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_relay_contact_open_fails() {
        let mut g = ac_fixture();
        g.pins.remove(&("bypass".into(), "3".into()));
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_y1_pe_disconnect_fails() {
        let mut g = ac_fixture();
        g.pins.insert(("y1".into(), "2".into()), "hot0".into());
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn ac_flyback_reverse_fails() {
        let mut g = ac_fixture();
        g.pins.insert(("flyback".into(), "1".into()), "relay_coil_lo".into());
        assert!(check_ac_input(&g).is_err());
    }

    #[test]
    fn joined_ac_bridge_live_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("pfc_power.bridge".into(), "2".into()), "ac_live_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_ac_bridge_neutral_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("pfc_power.bridge".into(), "3".into()), "ac_neutral_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_relay_control_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("ac_input.relay_gate_r".into(), "1".into()), "relay_control_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_relay_control_cannot_bypass_run_gate() {
        let mut g = integrated_fixture();
        let direct = g.pins.get(&("receiver.rx".into(), "32".into())).unwrap().to_string();
        g.pins.insert(("ac_input.relay_gate_r".into(), "1".into()), direct);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn pfc_power_f2_bypass_fails() {
        let mut g = power_fixture();
        g.pins.insert(("f2".into(), "2".into()), "vd_local".into());
        assert!(check_pfc_power(&g).is_err());
    }

    #[test]
    fn pfc_power_f2_vd_stud_missing_pin_fails() {
        let mut g = power_fixture();
        check_pfc_power(&g).unwrap();
        g.pins.remove(&("f2_vd_stud".into(), "1".into()));
        assert!(check_pfc_power(&g).is_err());
    }

    #[test]
    fn pfc_power_f2_vb_stud_missing_part_fails() {
        let mut g = power_fixture();
        check_pfc_power(&g).unwrap();
        g.parts.remove("f2_vb_stud");
        assert!(check_pfc_power(&g).is_err());
    }

    #[test]
    fn pfc_power_f2_studs_cross_potential_fails() {
        let mut g = power_fixture();
        check_pfc_power(&g).unwrap();
        g.pins.insert(("f2_vd_stud".into(), "1".into()), "vb_bank".into());
        g.pins.insert(("f2_vb_stud".into(), "1".into()), "vd_local".into());
        assert!(check_pfc_power(&g).is_err());
    }

    #[test]
    fn pfc_power_local_cap_after_f2_fails() {
        let mut g = power_fixture();
        g.pins.insert(("local_c".into(), "1".into()), "vb_bank".into());
        assert!(check_pfc_power(&g).is_err());
    }

    #[test]
    fn pfc_power_diode_anode_missing_fails() {
        let mut g = power_fixture();
        g.pins.remove(&("d_boost".into(), "3".into()));
        assert!(check_pfc_power(&g).is_err());
    }

    #[test]
    fn joined_pfc_power_f2_sense_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("pfc_power.f2".into(), "2".into()), "bank_sense_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_pfc_power_switch_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("pfc_power.d_boost".into(), "1".into()), "boost_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn pfc_vsense_ladder_open_fails() {
        let mut g = pfc_fixture();
        g.pins.remove(&("r_vtop3".into(), "2".into()));
        assert!(check_pfc_control(&g).is_err());
    }

    #[test]
    fn pfc_inhibit_fet_missing_fails() {
        let mut g = pfc_fixture();
        g.pins.remove(&("q_inhibit".into(), "3".into()));
        assert!(check_pfc_control(&g).is_err());
    }

    #[test]
    fn pfc_isense_clamp_reversed_fails() {
        let mut g = pfc_fixture();
        g.pins.insert(("isense_clamp".into(), "3".into()), "hot0".into());
        assert!(check_pfc_control(&g).is_err());
    }

    #[test]
    fn joined_pfc_pwm_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("pfc_control.pfc".into(), "8".into()), "pwm_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_pfc_permission_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("pfc_control.permit_r".into(), "1".into()), "permit_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn aux_fast_divider_open_fails() {
        let mut g = aux_fixture();
        g.pins.remove(&("fast_bottom".into(), "1".into()));
        assert!(check_aux_window(&g).is_err());
    }

    #[test]
    fn aux_ov_comparator_input_swap_fails() {
        let mut g = aux_fixture();
        g.pins.insert(("comparator".into(), "6".into()), "ref25".into());
        assert!(check_aux_window(&g).is_err());
    }

    #[test]
    fn aux_window_output_missing_fails() {
        let mut g = aux_fixture();
        g.pins.remove(&("window".into(), "4".into()));
        assert!(check_aux_window(&g).is_err());
    }

    #[test]
    fn joined_aux_window_fault_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("aux_window.window".into(), "4".into()), "aux_window_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_aux_window_reference_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("aux_window.comparator".into(), "2".into()), "aux_ref_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn f2_divider_open_fails() {
        let mut g = f2_fixture();
        g.pins.remove(&("vd_div.r3".into(), "2".into()));
        assert!(check_f2_detector(&g).is_err());
    }

    #[test]
    fn f2_absolute_ov_swap_fails() {
        let mut g = f2_fixture();
        g.pins.insert(("cmp_vd".into(), "3".into()), "vd_div-high".into());
        assert!(check_f2_detector(&g).is_err());
    }

    #[test]
    fn f2_mismatch_cross_sense_missing_fails() {
        let mut g = f2_fixture();
        g.pins.insert(("vb_mismatch_n".into(), "1".into()), "vd_div-low".into());
        assert!(check_f2_detector(&g).is_err());
    }

    #[test]
    fn f2_health_output_missing_fails() {
        let mut g = f2_fixture();
        g.pins.remove(&("health".into(), "8".into()));
        assert!(check_f2_detector(&g).is_err());
    }

    #[test]
    fn joined_f2_fault_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("f2_detector.health".into(), "8".into()), "f2_fault_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_f2_rail_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("f2_detector.cmp_vd".into(), "8".into()), "f2_rail_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn hot_rails_missing_logic_sense_series_fails() {
        let mut g = hot_rails_fixture();
        g.pins.remove(&("logic_iso".into(), "2".into()));
        assert!(check_hot_rails(&g).is_err());
    }

    #[test]
    fn hot_rails_aux_sense_grounded_fails() {
        let mut g = hot_rails_fixture();
        g.pins.insert(("sup_aux".into(), "1".into()), "hot0".into());
        assert!(check_hot_rails(&g).is_err());
    }

    #[test]
    fn hot_rails_missing_shared_reset_fails() {
        let mut g = hot_rails_fixture();
        g.pins.insert(("sup_aux".into(), "6".into()), "aux_reset_cut".into());
        assert!(check_hot_rails(&g).is_err());
    }

    #[test]
    fn hot_rails_aux_short_to_logic_fails() {
        let mut g = hot_rails_fixture();
        g.pins.insert(("aux_top".into(), "1".into()), "hot_logic5".into());
        assert!(check_hot_rails(&g).is_err());
    }

    #[test]
    fn joined_hot_rails_reset_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("hot_rails.sup_aux".into(), "6".into()), "rail_reset_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_hot_rails_aux_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("hot_rails.aux_top".into(), "1".into()), "rail_aux_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn hot_watchdog_missing_cwd_fails() {
        let mut g = hot_watchdog_fixture();
        g.pins.remove(&("cwd".into(), "1".into()));
        assert!(check_hot_watchdog(&g).is_err());
    }

    #[test]
    fn hot_watchdog_missing_output_pullup_fails() {
        let mut g = hot_watchdog_fixture();
        g.pins.remove(&("wdo_pu".into(), "2".into()));
        assert!(check_hot_watchdog(&g).is_err());
    }

    #[test]
    fn hot_watchdog_enable_grounded_fails() {
        let mut g = hot_watchdog_fixture();
        g.pins.insert(("watchdog".into(), "3".into()), "hot0".into());
        assert!(check_hot_watchdog(&g).is_err());
    }

    #[test]
    fn joined_hot_watchdog_wdi_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("hot_watchdog.watchdog".into(), "6".into()), "hot_wdi_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_hot_watchdog_trip_output_disconnect_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("hot_watchdog.watchdog".into(), "7".into()), "hot_trip_cut".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn driver_enable_left_floating_fails() {
        let mut g = driver_fixture();
        g.pins.remove(&("shunt".into(), "3".into()));
        assert!(check_driver(&g).is_err());
    }

    #[test]
    fn driver_shunt_base_bias_missing_fails() {
        let mut g = driver_fixture();
        g.pins.remove(&("base_bias".into(), "2".into()));
        assert!(check_driver(&g).is_err());
    }

    #[test]
    fn driver_logic_power_backfeed_fails() {
        let mut g = driver_fixture();
        g.pins.insert(("release".into(), "5".into()), "aux_protected".into());
        assert!(check_driver(&g).is_err());
    }

    #[test]
    fn driver_abort_bypass_fails() {
        let mut g = driver_fixture();
        g.pins.insert(("qualify".into(), "10".into()), "hot_logic5".into());
        assert!(check_driver(&g).is_err());
    }

    #[test]
    fn driver_power_pad_floating_fails() {
        let mut g = driver_fixture();
        g.pins.remove(&("driver".into(), "9".into()));
        assert!(check_driver(&g).is_err());
    }

    #[test]
    fn joined_driver_run_producer_missing_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("driver.qualify".into(), "1".into()), "aux_protected".into());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_driver_gate_short_to_aux_fails() {
        let mut g = integrated_fixture();
        let aux = g.pins.get(&("driver.driver".into(), "6".into())).unwrap().clone();
        g.pins.insert(("driver.stw".into(), "1".into()), aux);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_driver_whole_enable_net_short_to_aux_fails() {
        let mut g = integrated_fixture();
        let aux = g.pins.get(&("driver.driver".into(), "6".into())).unwrap().clone();
        let ena = g.pins.get(&("driver.driver".into(), "1".into())).unwrap().clone();
        for net in g.pins.values_mut() {
            if *net == ena { *net = aux.clone(); }
        }
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn compiled_source_passes() { check_source(&source_fixture()).unwrap(); }

    #[test]
    fn source_weak_heartbeat_pull_down_fails() {
        let mut g = source_fixture();
        g.parts.insert("heartbeat_pd".into(), "RC0603FR-07100KL".into());
        assert!(check_source(&g).is_err());
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
    fn relay_run_qualification_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("run_and".into(), "9".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn wrong_feedback_part_fails() {
        let mut g = fixture();
        g.parts.insert("iso_feedback".into(), "ISO7741FQDWWRQ1".into());
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

    #[test]
    fn missing_attempt_default_fails() {
        let mut g = fixture();
        g.pins.remove(&("attempt_valid_pd".into(), "2".into()));
        assert!(check(&g).is_err());
    }

    #[test]
    fn missing_trip_fan_in_fails() {
        let mut g = fixture();
        g.pins.insert(("prep_trip_and".into(), "10".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn missing_watchdog_default_fails() {
        let mut g = fixture();
        g.pins.remove(&("watchdog_ok_pd".into(), "2".into()));
        assert!(check(&g).is_err());
    }

    #[test]
    fn permit_preset_miswire_fails() {
        let mut g = fixture();
        g.pins.insert(("permit_seen_memory".into(), "4".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn history_reset_clock_miswire_fails() {
        let mut g = fixture();
        g.pins.insert(("permit_seen_memory".into(), "3".into()), "q1".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn disarm_clear_miswire_fails() {
        let mut g = fixture();
        g.pins.insert(("disarm_memory".into(), "1".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn disarm_clock_miswire_fails() {
        let mut g = fixture();
        g.pins.insert(("disarm_memory".into(), "3".into()), "q1".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn history_d_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("permit_seen_memory".into(), "2".into()), "hot0".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn history_disarm_qualification_missing_fails() {
        let mut g = fixture();
        g.pins.insert(("history_reset_and".into(), "1".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn history_abort_qualification_missing_fails() {
        let mut g = fixture();
        g.pins.insert(("history_reset_and".into(), "12".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn permit_loss_history_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("permit_loss_nand".into(), "1".into()), "hot0".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn session_clear_abort_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("session_and".into(), "4".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn session_raw_clock_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("session_memory".into(), "3".into()), "hot_session_revalidate_d".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn run_clear_permit_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("run_and".into(), "2".into()), "hot_logic5".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn run_raw_clock_bypass_fails() {
        let mut g = fixture();
        g.pins.insert(("run_memory".into(), "3".into()), "hot_run_clear_n".into());
        assert!(check(&g).is_err());
    }

    #[test]
    fn source_watchdog_clear_bypass_fails() {
        let mut g = source_fixture();
        g.pins.insert(("health".into(), "2".into()), "selv3v3".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn source_reset_input_fall_cannot_be_wdi_trigger() {
        let mut g = source_fixture();
        g.pins.insert(("seen_reset_pulse".into(), "10".into()),
                      "selv_gnd".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn source_wdi_must_use_active_low_one_shot_output() {
        let mut g = source_fixture();
        g.pins.insert(("watchdog".into(), "6".into()),
                      "source_validated_heartbeat".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn source_prewatchdog_must_exclude_wdo_and_include_interlock() {
        let mut g = source_fixture();
        g.pins.insert(("health".into(), "10".into()),
                      "source_watchdog_good".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn source_retained_feedback_bypass_fails() {
        let mut g = source_fixture();
        g.pins.insert(("permit_clear".into(), "4".into()), "selv3v3".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn source_permit_readback_loss_bypass_fails() {
        let mut g = source_fixture();
        g.pins.insert(("loss".into(), "1".into()), "selv_gnd".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn source_seen_reset_clock_swap_fails() {
        let mut g = source_fixture();
        g.pins.insert(("seen".into(), "3".into()), "source_seen_reset_raw_n".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn source_set_clock_gating_fails() {
        let mut g = source_fixture();
        g.pins.insert(("permit".into(), "3".into()), "source_clear_n".into());
        assert!(check_source(&g).is_err());
    }

    #[test]
    fn joined_reverse_feedback_swap_fails() {
        let mut g = integrated_fixture();
        let other = g.pins.get(&("receiver.iso_feedback".into(), "6".into())).unwrap().clone();
        g.pins.insert(("receiver.iso_feedback".into(), "5".into()), other);
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_health_producer_missing_fails() {
        let mut g = integrated_fixture();
        g.pins.remove(&("source.health".into(), "6".into()));
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_prewatchdog_short_to_wdo_fails() {
        let mut g = integrated_fixture();
        let wdo_net = g.pins.get(&("source.watchdog".into(), "7".into())).unwrap().clone();
        for pin in [("source.health", "8"), ("source.prewatchdog_pd", "1")] {
            g.pins.insert((pin.0.into(), pin.1.into()), wdo_net.clone());
        }
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    #[test]
    fn joined_isolation_bypass_fails() {
        let mut g = integrated_fixture();
        g.pins.insert(("receiver.rx".into(), "19".into()),
                      g.pins.get(&("source.watchdog".into(), "4".into())).unwrap().clone());
        assert!(check_integrated(&g, &fixture(), &source_fixture(), &driver_fixture(), &hot_watchdog_fixture(), &hot_rails_fixture(), &f2_fixture(), &aux_fixture(), &pfc_fixture(), &power_fixture(), &ac_fixture()).is_err());
    }

    fn frozen_assembly() -> (Graph, Graph) {
        let rev38 = graph(&fs::read_to_string("source-build-05/build/default.net").unwrap()).unwrap();
        let cooker = graph(&fs::read_to_string("cooker-source-02/build/default.net").unwrap()).unwrap();
        (
            with_bom_parts(rev38, "source-build-05/build/default.csv").unwrap(),
            with_bom_parts(cooker, "cooker-source-02/build/default.csv").unwrap(),
        )
    }

    #[test]
    fn frozen_cooker_rev38_harness_contract_passes() {
        let (rev38, cooker) = frozen_assembly();
        assert!(check_cooker_rev38_harness(&rev38, &cooker).is_ok());
    }

    #[test]
    fn cooker_rev38_harness_rejects_extra_stop_driver() {
        let (mut rev38, cooker) = frozen_assembly();
        let stop = rev38.pins[&("source_mcu.controller_port".into(), "2".into())].clone();
        rev38.pins.insert(("source_mcu.expander".into(), "4".into()), stop);
        assert!(check_cooker_rev38_harness(&rev38, &cooker).is_err());
    }

    #[test]
    fn cooker_rev38_harness_rejects_wrong_protocol_part() {
        let (mut rev38, cooker) = frozen_assembly();
        rev38.parts.insert("receiver.iso_protocol".into(), "ISO6742FQDWWRQ1".into());
        assert!(check_cooker_rev38_harness(&rev38, &cooker).is_err());
    }

    #[test]
    fn cooker_rev38_harness_rejects_swapped_uart_contacts() {
        let (mut rev38, cooker) = frozen_assembly();
        let tx = rev38.pins[&("source_mcu.controller_port".into(), "6".into())].clone();
        let rx = rev38.pins[&("source_mcu.controller_port".into(), "7".into())].clone();
        rev38.pins.insert(("source_mcu.controller_port".into(), "6".into()), rx);
        rev38.pins.insert(("source_mcu.controller_port".into(), "7".into()), tx);
        assert!(check_cooker_rev38_harness(&rev38, &cooker).is_err());
    }

    #[test]
    fn cooker_rev38_harness_rejects_open_return_contact() {
        let (rev38, mut cooker) = frozen_assembly();
        cooker.pins.remove(&("rev38_mate".into(), "16".into()));
        assert!(check_cooker_rev38_harness(&rev38, &cooker).is_err());
    }

    #[test]
    fn cooker_rev38_harness_rejects_open_esp_ground_pad() {
        let (rev38, mut cooker) = frozen_assembly();
        cooker.pins.remove(&("cooker.mcu.mcu".into(), "41".into()));
        assert!(check_cooker_rev38_harness(&rev38, &cooker).is_err());
    }

    #[test]
    fn cooker_rev38_harness_rejects_second_esp() {
        let (mut rev38, cooker) = frozen_assembly();
        rev38.parts.insert("unexpected_mcu".into(), "ESP32-S3-WROOM-1-N8R8".into());
        assert!(check_cooker_rev38_harness(&rev38, &cooker).is_err());
    }
}
