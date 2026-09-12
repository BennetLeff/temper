//! Package-pin-grounded checks for the standalone interlock.
//! Connectivity parity and Boolean device propagation are separate checks.
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::{CheckReport, Finding};

type Nets = BTreeMap<String, String>;
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct InterlockState {
    pub permit: bool,
    pub latched_fault: bool,
}
#[derive(Debug, Clone, Copy)]
pub struct InterlockInputs {
    pub faults: u8,
    pub sensor_live: bool,
    pub watchdog_reset_n: bool,
    pub prior: InterlockState,
    pub reset_falling_edge: bool,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GraphState {
    pub permit: bool,
    pub latched_fault: bool,
    pub reset_edge: bool,
}
/// Independent requirement oracle. Q is the sole stored state; QBAR is derived.
pub fn evaluate(i: InterlockInputs) -> InterlockState {
    let good = i.faults == 0 && i.sensor_live && i.watchdog_reset_n;
    let q = good && (i.reset_falling_edge || i.prior.permit);
    InterlockState {
        permit: q,
        latched_fault: !q,
    }
}
fn s<'a>(v: &'a Value, k: &str) -> Result<&'a str, String> {
    v[k].as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| format!("missing {k}"))
}
fn arr<'a>(v: &'a Value, k: &str) -> Result<&'a [Value], String> {
    v[k].as_array()
        .map(Vec::as_slice)
        .ok_or_else(|| format!("missing array {k}"))
}
fn add(m: &mut Nets, k: String, v: String) -> Result<(), String> {
    if m.insert(k.clone(), v).is_some() {
        Err(format!("duplicate endpoint {k}"))
    } else {
        Ok(())
    }
}
fn compiled(source: &Value) -> Result<Nets, String> {
    let mut refs = BTreeMap::new();
    for c in arr(source, "components")? {
        if refs
            .insert(s(c, "reference")?, s(c, "instance_path")?)
            .is_some()
        {
            return Err("duplicate reference".into());
        }
    }
    let mut nets = Nets::new();
    for n in arr(&source["bridge"], "nets")? {
        for p in arr(n, "nodes")? {
            let pair = p
                .as_array()
                .filter(|p| p.len() == 2)
                .ok_or("bad source endpoint")?;
            let reference = pair[0].as_str().ok_or("bad reference")?;
            let id = refs.get(reference).ok_or("unknown reference")?;
            let pin = pair[1].as_str().ok_or("bad pin")?;
            add(&mut nets, format!("{id}.{pin}"), s(n, "name")?.into())?;
        }
    }
    Ok(nets)
}
fn net<'a>(n: &'a Nets, p: &str) -> Result<&'a str, String> {
    n.get(p)
        .map(String::as_str)
        .ok_or_else(|| format!("missing pin {p}"))
}
fn read(v: &BTreeMap<String, bool>, n: &Nets, p: &str) -> Result<bool, String> {
    v.get(net(n, p)?)
        .copied()
        .ok_or_else(|| format!("unresolved input {p}"))
}
fn drive(v: &mut BTreeMap<String, bool>, n: &Nets, p: &str, b: bool) -> Result<(), String> {
    let key = net(n, p)?;
    if v.get(key).is_some_and(|old| *old != b) {
        return Err(format!("conflicting drivers on {key}"));
    }
    v.insert(key.into(), b);
    Ok(())
}
/// Each tuple is a physical package output and its inputs, from TI pin tables.
fn gates() -> Vec<(String, Vec<String>, bool)> {
    let mut g = Vec::new();
    for id in ["fault_inv", "control_inv"] {
        for (a, y) in [(1, 2), (3, 4), (5, 6), (9, 8), (11, 10), (13, 12)] {
            g.push((format!("{id}.{y}"), vec![format!("{id}.{a}")], true));
        }
    }
    g.push((
        "common.4".into(),
        vec!["common.1".into(), "common.2".into()],
        false,
    ));
    g.push((
        "aggregate.8".into(),
        [1, 2, 3, 4, 5, 6, 11, 12]
            .map(|p| format!("aggregate.{p}"))
            .into(),
        true,
    ));
    g
}
fn frame(n: &Nets, i: InterlockInputs, reset_n: bool) -> Result<BTreeMap<String, bool>, String> {
    let mut v = BTreeMap::new();
    drive(&mut v, n, "host.1", true)?;
    drive(&mut v, n, "host.2", false)?;
    for k in 0..7 {
        drive(
            &mut v,
            n,
            &format!("faults.{}", k + 2),
            i.faults & (1 << k) != 0,
        )?;
    }
    drive(&mut v, n, "host.4", reset_n)?;
    drive(&mut v, n, "host.5", i.sensor_live)?;
    // A supervisor RESET waveform is the boundary of the static digital model.
    drive(&mut v, n, "watchdog.1", i.watchdog_reset_n)?;
    for (power, ground) in [
        ("fault_inv.14", "fault_inv.7"),
        ("control_inv.14", "control_inv.7"),
        ("aggregate.14", "aggregate.7"),
        ("latch.8", "latch.4"),
        ("watchdog.5", "watchdog.2"),
        ("common.5", "common.3"),
    ] {
        if !read(&v, n, power)? || read(&v, n, ground)? {
            return Err(format!("invalid supply at {power}/{ground}"));
        }
    }
    let gs = gates();
    // Reject shared output nets even where two drivers happen to agree in this vector.
    let mut drivers = BTreeSet::new();
    for (out, _, _) in &gs {
        if !drivers.insert(net(n, out)?) {
            return Err("multiple gate outputs on one net".into());
        }
    }
    for _ in 0..gs.len() {
        let before = v.len();
        for (out, ins, invert) in &gs {
            let inputs = ins
                .iter()
                .map(|p| read(&v, n, p))
                .collect::<Result<Vec<_>, _>>();
            if let Ok(inputs) = inputs {
                let b = inputs.into_iter().all(|b| b);
                drive(&mut v, n, out, b ^ invert)?;
            }
        }
        if before == v.len() {
            break;
        }
    }
    for (out, _, _) in &gs {
        read(&v, n, out)?;
    }
    Ok(v)
}
/// Simulate actual physical pin nets, including the clock before and after reset.
pub fn evaluate_graph(
    source_json: &str,
    i: InterlockInputs,
    old_reset: bool,
    new_reset: bool,
) -> Result<GraphState, String> {
    let source: Value = serde_json::from_str(source_json).map_err(|e| e.to_string())?;
    evaluate_nets(&compiled(&source)?, i, old_reset, new_reset)
}
fn evaluate_nets(
    n: &Nets,
    i: InterlockInputs,
    old_reset: bool,
    new_reset: bool,
) -> Result<GraphState, String> {
    let old = frame(n, i, old_reset)?;
    let mut now = frame(n, i, new_reset)?;
    let clr = read(&now, n, "latch.6")?;
    let pre = read(&now, n, "latch.7")?;
    if !clr && !pre {
        return Err("simultaneous asynchronous set/clear".into());
    }
    let edge = !read(&old, n, "latch.1")? && read(&now, n, "latch.1")?;
    let q = if !clr {
        false
    } else if !pre {
        true
    } else if edge {
        read(&now, n, "latch.2")?
    } else {
        i.prior.permit
    };
    drive(&mut now, n, "latch.5", q)?;
    drive(&mut now, n, "latch.3", !q)?;
    Ok(GraphState {
        permit: read(&now, n, "host.6")?,
        latched_fault: read(&now, n, "host.7")?,
        reset_edge: edge,
    })
}
fn finding(f: &mut Vec<Finding>, rule: &str, ok: bool, msg: impl Into<String>, subject: &str) {
    f.push(if ok {
        Finding::pass(rule, msg, subject)
    } else {
        Finding::fail(rule, msg, subject)
    });
}
fn resistor_max(v: &Value) -> Result<f64, String> {
    let raw = s(v, "value")?;
    let (value, tol) = raw.split_once("+/-").ok_or("missing resistor tolerance")?;
    let (n, scale) = value
        .trim()
        .strip_suffix("kohm")
        .map(|n| (n, 1000.))
        .or_else(|| value.trim().strip_suffix("ohm").map(|n| (n, 1.)))
        .ok_or("bad resistor unit")?;
    let n = n.trim().parse::<f64>().map_err(|_| "bad resistance")? * scale;
    let t = tol
        .trim()
        .strip_suffix('%')
        .ok_or("bad tolerance")?
        .trim()
        .parse::<f64>()
        .map_err(|_| "bad tolerance")?
        / 100.;
    if !n.is_finite() || !t.is_finite() || n <= 0. || !(0. ..1.).contains(&t) {
        return Err("invalid resistor range".into());
    }
    Ok(n * (1. + t))
}

// Reviewed Rev A identities and topology. Changes require explicit model review.
const PARTS: &[(&str, &str, &str)] = &[
    ("fault_inv_bypass", "C0603C104K5RACTU", "100nF +/- 10%"),
    ("control_inv_bypass", "C0603C104K5RACTU", "100nF +/- 10%"),
    ("aggregate_bypass", "C0603C104K5RACTU", "100nF +/- 10%"),
    ("latch_bypass", "C0603C104K5RACTU", "100nF +/- 10%"),
    ("watchdog_bypass", "C0603C104K5RACTU", "100nF +/- 10%"),
    ("common_bypass", "C0603C104K5RACTU", "100nF +/- 10%"),
    ("faults", "B8B-XH-A(LF)(SN)", ""),
    ("host", "B8B-XH-A(LF)(SN)", ""),
    ("ocp_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("live_pulldown", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("permit_pulldown", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("ovp_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("hs_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("coil_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("rtd_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("runaway_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("aux_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("reset_pullup", "RC0603FR-0710KL", "10kohm +/- 1%"),
    ("wdi_pulldown", "RC0603FR-071KL", "1kohm +/- 1%"),
    ("fault_inv", "SN74LVC14ADR", ""),
    ("control_inv", "SN74LVC14ADR", ""),
    ("aggregate", "CD74HC30PWR", ""),
    ("latch", "SN74LVC1G74DCUR", ""),
    ("watchdog", "TPS3823-33DBVR", ""),
    ("common", "SN74LVC1G08DBVR", ""),
];
const TOPOLOGY: &[(&str, &[&str])] = &[
    (
        "vcc",
        &[
            "reset_pullup.1",
            "watchdog.3",
            "latch.7",
            "latch.2",
            "aux_pullup.1",
            "runaway_pullup.1",
            "rtd_pullup.1",
            "coil_pullup.1",
            "hs_pullup.1",
            "ovp_pullup.1",
            "ocp_pullup.1",
            "common.5",
            "common_bypass.1",
            "watchdog.5",
            "watchdog_bypass.1",
            "latch.8",
            "latch_bypass.1",
            "aggregate.14",
            "aggregate_bypass.1",
            "control_inv.14",
            "control_inv_bypass.1",
            "fault_inv.14",
            "fault_inv_bypass.1",
            "host.1",
        ],
    ),
    (
        "gnd",
        &[
            "control_inv.13",
            "permit_pulldown.2",
            "live_pulldown.2",
            "wdi_pulldown.2",
            "common.3",
            "common_bypass.2",
            "watchdog.2",
            "watchdog_bypass.2",
            "latch.4",
            "latch_bypass.2",
            "aggregate.7",
            "aggregate_bypass.2",
            "control_inv.7",
            "control_inv_bypass.2",
            "fault_inv.7",
            "fault_inv_bypass.2",
            "faults.1",
            "host.2",
        ],
    ),
    ("ocp_fault", &["ocp_pullup.2", "fault_inv.1", "faults.2"]),
    ("ocp_healthy", &["aggregate.1", "fault_inv.2"]),
    ("ovp_fault", &["ovp_pullup.2", "fault_inv.3", "faults.3"]),
    ("ovp_healthy", &["aggregate.2", "fault_inv.4"]),
    ("hs_fault", &["hs_pullup.2", "fault_inv.5", "faults.4"]),
    ("hs_healthy", &["aggregate.3", "fault_inv.6"]),
    ("coil_fault", &["coil_pullup.2", "fault_inv.9", "faults.5"]),
    ("coil_healthy", &["aggregate.4", "fault_inv.8"]),
    ("rtd_fault", &["rtd_pullup.2", "fault_inv.11", "faults.6"]),
    ("rtd_healthy", &["aggregate.5", "fault_inv.10"]),
    (
        "runaway_fault",
        &["runaway_pullup.2", "fault_inv.13", "faults.7"],
    ),
    ("runaway_healthy", &["aggregate.6", "fault_inv.12"]),
    ("aux_fault", &["aux_pullup.2", "control_inv.1", "faults.8"]),
    ("aux_healthy", &["aggregate.11", "control_inv.2"]),
    ("reset_n", &["control_inv.5", "reset_pullup.2", "host.4"]),
    ("reset_clock", &["latch.1", "control_inv.6"]),
    (
        "sensor_live",
        &["control_inv.9", "live_pulldown.1", "host.5"],
    ),
    ("live_n", &["control_inv.11", "control_inv.8"]),
    ("live_buf", &["common.2", "control_inv.10"]),
    ("wdt_good", &["common.1", "watchdog.1", "host.8"]),
    ("wdi", &["wdi_pulldown.1", "watchdog.4", "host.3"]),
    ("common_good", &["aggregate.12", "common.4"]),
    ("any_fault", &["control_inv.3", "aggregate.8"]),
    ("all_good", &["latch.6", "control_inv.4"]),
    ("permit", &["permit_pulldown.1", "latch.5", "host.6"]),
    ("latched_fault", &["latch.3", "host.7"]),
    ("y6", &["control_inv.12"]),
    ("nc9", &["aggregate.9"]),
    ("nc10", &["aggregate.10"]),
    ("nc13", &["aggregate.13"]),
];
fn inspect(source: &Value, native: &Value) -> Result<Vec<Finding>, String> {
    let mut f = Vec::new();
    if s(source, "entry")? != "elec/src/interlock_unit.ato:InterlockUnit" {
        return Err("wrong source entry".into());
    }
    let attrs = &source["source_attributes"];
    let source_components = arr(source, "components")?;
    let native_components = arr(native, "components")?;
    let mut refs = BTreeMap::new();
    let mut ids = BTreeSet::new();
    for c in source_components {
        let id = s(c, "instance_path")?;
        if !ids.insert(id) || refs.insert(s(c, "reference")?, id).is_some() {
            return Err("duplicate source component/reference".into());
        };
        finding(
            &mut f,
            "ERC.INTERLOCK.SOURCE",
            c["mpn"] == attrs[id]["mpn"] && c["value"] == attrs[id]["value"],
            format!("source attribute binding {id}"),
            id,
        );
    }
    let expected: BTreeSet<_> = PARTS.iter().map(|x| x.0).collect();
    finding(
        &mut f,
        "ERC.INTERLOCK.SOURCE",
        ids == expected,
        "exact 25-component source census",
        "InterlockUnit",
    );
    let mut native_ids = BTreeSet::new();
    let mut pads = BTreeMap::new();
    for c in native_components {
        let id = s(c, "id")?;
        if !native_ids.insert(id) {
            return Err("duplicate native component".into());
        };
        for p in arr(c, "footprint_pads")? {
            add(
                &mut pads,
                format!("{id}.{}", s(p, "pad")?),
                s(p, "net")?.into(),
            )?;
        }
    }
    finding(
        &mut f,
        "ERC.INTERLOCK.NATIVE_COMPONENTS",
        native_ids == expected,
        "exact 25-component native census",
        "native",
    );
    for (id, mpn, value) in PARTS {
        finding(
            &mut f,
            "ERC.INTERLOCK.PARTS",
            attrs[*id]["mpn"] == *mpn
                && (attrs[*id]["value"].as_str().unwrap_or("") == *value)
                && native_components
                    .iter()
                    .any(|c| c["id"] == *id && c["mpn"] == *mpn),
            format!("exact MPN {id}: {mpn}"),
            id,
        );
    }
    let mut intent = BTreeMap::new();
    for (net, nodes) in TOPOLOGY {
        for node in *nodes {
            add(&mut intent, (*node).into(), (*net).into())?;
        }
    }
    let mut compiled = BTreeMap::new();
    for net in arr(&source["bridge"], "nets")? {
        for pair in arr(net, "nodes")? {
            let p = pair.as_array().ok_or("bad source endpoint")?;
            if p.len() != 2 {
                return Err("bad source endpoint".into());
            };
            let id = refs
                .get(p[0].as_str().ok_or("bad reference")?)
                .ok_or("unknown source reference")?;
            add(
                &mut compiled,
                format!("{id}.{}", p[1].as_str().ok_or("bad pin")?),
                s(net, "name")?.into(),
            )?;
        }
    }
    let mut connected = BTreeMap::new();
    for c in arr(native, "connections")? {
        add(
            &mut connected,
            format!("{}.{}", s(c, "component")?, s(c, "pin")?),
            s(c, "net")?.into(),
        )?;
    }
    finding(
        &mut f,
        "ERC.INTERLOCK.TOPOLOGY",
        compiled == intent,
        "compiled source equals complete pin/net intent",
        "InterlockUnit",
    );
    finding(
        &mut f,
        "ERC.INTERLOCK.TOPOLOGY",
        connected == intent && pads == intent,
        "native pads and connections equal complete pin/net intent",
        "native",
    );
    let mut strict = BTreeSet::new();
    let mut strict_ok = true;
    for p in arr(source, "strict_pin_map")? {
        let id = p["instance_path"].as_str();
        let pad = p["pad"].as_str();
        let pin = p["pin"].as_str();
        let reference = p["reference"].as_str();
        let valid = match (id, pad, pin, reference) {
            (Some(id), Some(pad), Some(pin), Some(reference)) => {
                refs.get(reference) == Some(&id)
                    && pad == pin
                    && strict.insert(format!("{id}.{pad}"))
            }
            _ => false,
        };
        strict_ok &= valid;
    }
    finding(&mut f,"ERC.INTERLOCK.STRICT_PIN_MAP",strict_ok&&strict==intent.keys().cloned().collect(),"strict source pin map validates reference, pin/pad identity, uniqueness, and complete coverage","source");
    let mut by_net: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut cluster_ok = true;
    for c in arr(native, "connectivity_clusters")? {
        if c["source"] != "native" {
            continue;
        }
        let net = match c["net"].as_str() {
            Some(v) => v.to_string(),
            None => {
                cluster_ok = false;
                continue;
            }
        };
        let nodes = match c["nodes"].as_array() {
            Some(v) => {
                let mut nodes = BTreeSet::new();
                for node in v {
                    match node.as_str() {
                        Some(node) if !node.is_empty() => {
                            cluster_ok &= nodes.insert(node.to_owned())
                        }
                        _ => cluster_ok = false,
                    }
                }
                nodes
            }
            None => {
                cluster_ok = false;
                continue;
            }
        };
        if by_net.insert(net, nodes).is_some() {
            cluster_ok = false;
        }
    }
    let mut expected_by_net: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (node, net) in &intent {
        expected_by_net
            .entry(net.clone())
            .or_default()
            .insert(node.clone());
    }
    finding(
        &mut f,
        "ERC.INTERLOCK.CONNECTIVITY",
        cluster_ok && by_net == expected_by_net,
        "one native connectivity cluster per authored net with exact node sets",
        "native",
    );
    finding(
        &mut f,
        "ERC.INTERLOCK.CONNECTIVITY",
        !arr(native, "traces")?.is_empty(),
        "native routed copper exists",
        "native",
    );

    for id in [
        "ocp_pullup",
        "ovp_pullup",
        "hs_pullup",
        "coil_pullup",
        "rtd_pullup",
        "runaway_pullup",
        "aux_pullup",
    ] {
        let high = 3.135 - resistor_max(&attrs[id])? * 20e-6;
        finding(
            &mut f,
            "ERC.INTERLOCK.OPEN_MARGIN",
            high > 2.,
            format!("{id}: open input minimum {high:.6} V, Schmitt rising maximum 2.0 V"),
            id,
        );
    }
    let nets = crate::interlock::compiled(source)?;
    let mut count = 0;
    'vectors: for faults in 0..128 {
        for live in [false, true] {
            for wdt in [false, true] {
                for q in [false, true] {
                    for old in [false, true] {
                        for new in [false, true] {
                            let i = InterlockInputs {
                                faults,
                                sensor_live: live,
                                watchdog_reset_n: wdt,
                                prior: InterlockState {
                                    permit: q,
                                    latched_fault: !q,
                                },
                                reset_falling_edge: old && !new,
                            };
                            let expected = evaluate(i);
                            match evaluate_nets(&nets, i, old, new) {
                                Ok(actual)
                                    if actual.permit == expected.permit
                                        && actual.latched_fault == expected.latched_fault
                                        && actual.reset_edge == (old && !new) =>
                                {
                                    count += 1;
                                }
                                other => {
                                    finding(&mut f,"ERC.INTERLOCK.DIGITAL_MODEL",false,format!("faults={faults} live={live} watchdog={wdt} priorQ={q} RESET_N={old}->{new}: {other:?}; expected {expected:?}"),"graph");
                                    break 'vectors;
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    finding(
        &mut f,
        "ERC.INTERLOCK.DIGITAL_MODEL",
        count == 4096,
        format!("{count}/4096 compiled gate/state/clock vectors agree with requirement oracle"),
        "graph",
    );
    for gap in [
        "SENSOR_LIVE producer and remote power-off injection",
        "AUX producer and downstream active-high PERMIT receiver",
        "actual watchdog timing, power ramps, propagation and clock/clear recovery/removal",
        "HC30 threshold applicability at actual rail, harness transients and component failures",
        "physical fault tests NOT RUN",
    ] {
        f.push(Finding::indeterminate(
            "ERC.INTERLOCK.QUALIFICATION",
            gap,
            "InterlockUnit",
        ));
    }
    Ok(f)
}
pub fn validate(source: &str, native: &str) -> CheckReport {
    // The replay alias file is not an acceptance authority. The reviewed pin
    // topology and compiled device behavior above are authoritative here.
    let result = serde_json::from_str(source)
        .and_then(|s| serde_json::from_str(native).map(|n| (s, n)))
        .map_err(|e| e.to_string())
        .and_then(|(s, n)| inspect(&s, &n));
    let findings =
        result.unwrap_or_else(|e| vec![Finding::fail("ERC.INTERLOCK.INPUT", e, "InterlockUnit")]);
    let rules = findings
        .iter()
        .map(|f| f.rule.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    CheckReport::from_findings(findings, rules, vec![])
}
