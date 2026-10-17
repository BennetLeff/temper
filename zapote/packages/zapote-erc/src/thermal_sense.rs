//! Standalone two-channel thermal comparator validation.
//! Sensor assemblies are off-board; their exact identity is bound by the
//! supplied sensor contract rather than invented as PCB components.
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::{CheckReport, Finding};

const PARTS: &[(&str, &str)] = &[
    ("heatsink_probe", "B2B-XH-A(LF)(SN)"),
    ("coil_probe", "B2B-XH-A(LF)(SN)"),
    ("host", "B6B-XH-A(LF)(SN)"),
    ("hs_comp", "TLV3201AIDBVR"),
    ("coil_comp", "TLV3201AIDBVR"),
    ("hs_fixed", "RC0603FR-0710KL"),
    ("hs_top", "RC0603FR-079K09L"),
    ("hs_bottom", "RC0603FR-0711K5L"),
    ("hs_hyst", "RC0603FR-0734K8L"),
    ("coil_fixed", "RC0603FR-0710KL"),
    ("coil_top", "RC0603FR-0720KL"),
    ("coil_bottom", "RC0603FR-078K06L"),
    ("coil_hyst", "RC0603FR-0742K2L"),
    ("open_top", "RC0603FR-071K21L"),
    ("open_bottom", "RC0603FR-07100KL"),
    ("hs_open_comp", "TLV9031DBVR"),
    ("coil_open_comp", "TLV9031DBVR"),
    ("hs_or", "SN74LVC1G32DBVR"),
    ("coil_or", "SN74LVC1G32DBVR"),
    ("hs_filter", "C0603C104K5RACTU"),
    ("hs_bypass", "C0603C104K5RACTU"),
    ("coil_filter", "C0603C104K5RACTU"),
    ("coil_bypass", "C0603C104K5RACTU"),
    ("hs_open_bypass", "C0603C104K5RACTU"),
    ("coil_open_bypass", "C0603C104K5RACTU"),
    ("hs_or_bypass", "C0603C104K5RACTU"),
    ("coil_or_bypass", "C0603C104K5RACTU"),
];
const TOPOLOGY: &[(&str, &[&str])] = &[
    (
        "+3V3",
        &[
            "host.1",
            "hs_comp.5",
            "coil_comp.5",
            "hs_fixed.1",
            "hs_top.1",
            "hs_bypass.1",
            "coil_fixed.1",
            "coil_top.1",
            "coil_bypass.1",
            "hs_open_comp.5",
            "hs_or.5",
            "hs_open_bypass.1",
            "hs_or_bypass.1",
            "coil_open_comp.5",
            "coil_or.5",
            "coil_open_bypass.1",
            "coil_or_bypass.1",
            "open_top.1",
        ],
    ),
    (
        "gnd",
        &[
            "host.2",
            "heatsink_probe.2",
            "coil_probe.2",
            "hs_comp.2",
            "coil_comp.2",
            "hs_bottom.2",
            "hs_filter.2",
            "hs_bypass.2",
            "coil_bottom.2",
            "coil_filter.2",
            "coil_bypass.2",
            "hs_open_comp.2",
            "hs_or.3",
            "hs_open_bypass.2",
            "hs_or_bypass.2",
            "coil_open_comp.2",
            "coil_or.3",
            "coil_open_bypass.2",
            "coil_or_bypass.2",
            "open_bottom.2",
        ],
    ),
    (
        "HS_SENSE",
        &[
            "host.5",
            "heatsink_probe.1",
            "hs_fixed.2",
            "hs_comp.4",
            "hs_filter.1",
            "hs_open_comp.3",
        ],
    ),
    (
        "HS_REF",
        &["hs_top.2", "hs_bottom.1", "hs_hyst.1", "hs_comp.3"],
    ),
    ("HS_FAULT", &["host.3", "hs_or.4"]),
    (
        "COIL_SENSE",
        &[
            "host.6",
            "coil_probe.1",
            "coil_fixed.2",
            "coil_comp.4",
            "coil_filter.1",
            "coil_open_comp.3",
        ],
    ),
    (
        "COIL_REF",
        &["coil_top.2", "coil_bottom.1", "coil_hyst.1", "coil_comp.3"],
    ),
    ("COIL_FAULT", &["host.4", "coil_or.4"]),
    ("HS_HOT", &["hs_hyst.2", "hs_comp.1", "hs_or.1"]),
    ("COIL_HOT", &["coil_hyst.2", "coil_comp.1", "coil_or.1"]),
    ("HS_OPEN", &["hs_open_comp.1", "hs_or.2"]),
    ("COIL_OPEN", &["coil_open_comp.1", "coil_or.2"]),
    (
        "OPEN_REF",
        &[
            "hs_open_comp.4",
            "coil_open_comp.4",
            "open_top.2",
            "open_bottom.1",
        ],
    ),
];
fn s<'a>(v: &'a Value, name: &str) -> Result<&'a str, String> {
    v[name]
        .as_str()
        .filter(|x| !x.is_empty())
        .ok_or_else(|| format!("missing {name}"))
}
fn text(v: &Value) -> Result<&str, String> {
    v.as_str()
        .filter(|x| !x.is_empty())
        .ok_or_else(|| "missing nonempty string".into())
}
fn arr<'a>(v: &'a Value, name: &str) -> Result<&'a [Value], String> {
    v[name]
        .as_array()
        .map(Vec::as_slice)
        .ok_or_else(|| format!("missing array {name}"))
}
fn finding(f: &mut Vec<Finding>, rule: &str, ok: bool, msg: impl Into<String>, subject: &str) {
    f.push(if ok {
        Finding::pass(rule, msg, subject)
    } else {
        Finding::fail(rule, msg, subject)
    });
}
fn add(m: &mut BTreeMap<String, String>, k: String, v: String) -> Result<(), String> {
    if m.insert(k.clone(), v).is_some() {
        Err(format!("duplicate endpoint {k}"))
    } else {
        Ok(())
    }
}
#[derive(Clone, Copy)]
struct R {
    n: f64,
    lo: f64,
    hi: f64,
}
fn resistor(attrs: &Value, id: &str) -> Result<R, String> {
    let v = s(&attrs[id], "value")?;
    let (n, t) = v
        .split_once("+/-")
        .ok_or_else(|| format!("missing tolerance {id}"))?;
    let (number, scale) = n
        .trim()
        .strip_suffix("kohm")
        .map(|x| (x, 1000.))
        .or_else(|| n.trim().strip_suffix("ohm").map(|x| (x, 1.)))
        .ok_or_else(|| format!("bad resistor unit {id}"))?;
    let n = number
        .parse::<f64>()
        .map_err(|_| format!("bad resistance {id}"))?
        * scale;
    let t = t
        .trim()
        .strip_suffix('%')
        .ok_or("bad tolerance")?
        .parse::<f64>()
        .map_err(|_| "bad tolerance")?
        / 100.;
    if !(n > 0. && (0. ..1.).contains(&t)) {
        return Err(format!("invalid resistor {id}"));
    }
    Ok(R {
        n,
        lo: n * (1. - t),
        hi: n * (1. + t),
    })
}
fn capacitor_max(attrs: &Value, id: &str) -> Result<f64, String> {
    let v = s(&attrs[id], "value")?;
    let (n, t) = v
        .split_once("+/-")
        .ok_or_else(|| format!("missing tolerance {id}"))?;
    let n = n
        .trim()
        .strip_suffix("nF")
        .ok_or_else(|| format!("bad capacitor unit {id}"))?
        .parse::<f64>()
        .map_err(|_| format!("bad capacitance {id}"))?
        * 1e-9;
    let t = t
        .trim()
        .strip_suffix('%')
        .ok_or("bad tolerance")?
        .parse::<f64>()
        .map_err(|_| "bad tolerance")?
        / 100.;
    if !(n > 0. && (0. ..1.).contains(&t)) {
        return Err(format!("invalid capacitor {id}"));
    }
    Ok(n * (1. + t))
}
fn threshold(fixed: R, top: R, bottom: R, hyst: R, beta: f64, r25: f64, output: f64) -> f64 {
    let frac = (1. / top.n + output / hyst.n) / (1. / top.n + 1. / bottom.n + 1. / hyst.n);
    let r = fixed.n * frac / (1. - frac);
    1. / (1. / 298.15 + (r / r25).ln() / beta) - 273.15
}
fn corner_range(fixed: R, top: R, bottom: R, hyst: R, output: f64) -> (f64, f64) {
    let mut min = f64::INFINITY;
    let mut max = f64::NEG_INFINITY;
    for mask in 0..64 {
        let pick = |r: R, bit: u32| if mask & (1 << bit) == 0 { r.lo } else { r.hi };
        let t = threshold(
            R {
                n: pick(fixed, 0),
                lo: 0.,
                hi: 0.,
            },
            R {
                n: pick(top, 1),
                lo: 0.,
                hi: 0.,
            },
            R {
                n: pick(bottom, 2),
                lo: 0.,
                hi: 0.,
            },
            R {
                n: pick(hyst, 3),
                lo: 0.,
                hi: 0.,
            },
            4190. * if mask & 16 == 0 { 0.985 } else { 1.015 },
            100000. * if mask & 32 == 0 { 1.02 } else { 0.98 },
            output,
        );
        min = min.min(t);
        max = max.max(t);
    }
    (min, max)
}

fn ntc_ohm(temp_c: f64, beta: f64, r25: f64) -> f64 {
    r25 * ((beta * (1. / (temp_c + 273.15) - 1. / 298.15)).exp())
}

fn divider_voltage(vcc: f64, source: R, load: f64) -> f64 {
    vcc * load / (source.n + load)
}

fn fault_or(hot: bool, open: bool) -> bool {
    hot || open
}

fn sensor_voltage(vcc: f64, fixed: R, sensor: f64) -> f64 {
    if sensor.is_infinite() {
        vcc
    } else {
        divider_voltage(vcc, fixed, sensor)
    }
}

struct ChannelModel {
    fixed: R,
    top: R,
    bottom: R,
    hyst: R,
}

fn analog_fault_cases(channel: ChannelModel, open_top: R, open_bottom: R, hot_c: f64) -> bool {
    let ChannelModel {
        fixed,
        top,
        bottom,
        hyst,
    } = channel;
    let vcc = 3.3;
    let open_ref = vcc * open_bottom.n / (open_top.n + open_bottom.n);
    // Evaluate both prior hot-output states: a healthy reconnect must clear,
    // while a hot/open/short input must assert regardless of prior state.
    let cases = [
        (ntc_ohm(0., 4190., 100000.), false),
        (100000., false),
        (ntc_ohm(hot_c, 4190., 100000.), true),
        (f64::INFINITY, true), // sense lead open
        (f64::INFINITY, true), // return lead open
        (0., true),            // short to ground
        (f64::INFINITY, true), // short to supply has the same rail voltage
    ];
    cases.iter().all(|(resistance, expected)| {
        let sense = sensor_voltage(vcc, fixed, *resistance);
        let open = sense > open_ref;
        [0., vcc].iter().all(|output| {
            let hot_ref =
                (vcc / top.n + output / hyst.n) / (1. / top.n + 1. / bottom.n + 1. / hyst.n);
            fault_or(hot_ref > sense, open) == *expected
        })
    })
}

fn open_margin(fixed: R, top: R, bottom: R, contract: &Value) -> (f64, f64) {
    let sense_leak = contract["open_detection"]["sense_leakage_a"]
        .as_f64()
        .unwrap_or(0.);
    let ref_leak = contract["open_detection"]["reference_leakage_a"]
        .as_f64()
        .unwrap_or(0.);
    let comparator_error = contract["open_detection"]["comparator_error_v"]
        .as_f64()
        .unwrap_or(0.);
    let vccs = [3.135, 3.465];
    let minimum_c = contract["open_detection"]["minimum_valid_temperature_c"]
        .as_f64()
        .unwrap_or(0.);
    let mut cold = f64::INFINITY;
    let mut open = f64::INFINITY;
    for mask in 0..8 {
        let pick = |r: R, bit: u32| R {
            n: if mask & (1 << bit) == 0 { r.lo } else { r.hi },
            lo: 0.,
            hi: 0.,
        };
        let fixed = pick(fixed, 0);
        let top = pick(top, 1);
        let bottom = pick(bottom, 2);
        for vcc in vccs {
            for beta in [4190. * 0.985, 4190. * 1.015] {
                for r25 in [100000. * 0.98, 100000. * 1.02] {
                    let sensor = ntc_ohm(minimum_c, beta, r25);
                    let sense = divider_voltage(vcc, fixed, sensor);
                    let refv = vcc * bottom.n / (top.n + bottom.n);
                    let rth = top.n * bottom.n / (top.n + bottom.n);
                    // A valid cold sensor is below OPEN_REF; a disconnected sensor rises above it.
                    let sense_rth = fixed.n * sensor / (fixed.n + sensor);
                    let cold_margin = (refv - ref_leak * rth)
                        - (sense + sense_leak * sense_rth)
                        - comparator_error;
                    let open_margin =
                        vcc - sense_leak * fixed.n - (refv + ref_leak * rth) - comparator_error;
                    cold = cold.min(cold_margin);
                    open = open.min(open_margin);
                }
            }
        }
    }
    (cold, open)
}

fn worst_open_settling(fixed: R, top: R, bottom: R, c: f64, contract: &Value) -> f64 {
    let sense_leak = contract["open_detection"]["sense_leakage_a"]
        .as_f64()
        .unwrap_or(0.);
    let ref_leak = contract["open_detection"]["reference_leakage_a"]
        .as_f64()
        .unwrap_or(0.);
    let error = contract["open_detection"]["comparator_error_v"]
        .as_f64()
        .unwrap_or(0.);
    let mut worst: f64 = 0.;
    for mask in 0..8 {
        let pick = |r: R, bit: u32| if mask & (1 << bit) == 0 { r.lo } else { r.hi };
        let rf = pick(fixed, 0);
        let rt = pick(top, 1);
        let rb = pick(bottom, 2);
        let rth = rt * rb / (rt + rb);
        for vcc in [3.135, 3.465] {
            let threshold = vcc * rb / (rt + rb) + ref_leak * rth + error;
            let asymptote = vcc - sense_leak * rf;
            let tau = rf * c;
            let t = if threshold > 0. && threshold < asymptote {
                -tau * (1. - threshold / asymptote).ln()
            } else {
                f64::INFINITY
            };
            worst = worst.max(t);
        }
    }
    worst
}
fn inspect(source: &Value, native: &Value, contract: &Value) -> Result<Vec<Finding>, String> {
    let mut f = Vec::new();
    if s(source, "entry")? != "elec/src/thermal_sense_unit.ato:ThermalSenseUnit" {
        return Err("wrong standalone source entry".into());
    }
    if s(contract, "schema")? != "zapote.thermal.sensor-contract.v2"
        || s(contract, "mpn")? != "NTCALUG01A104GA"
        || contract["off_board"] != true
    {
        finding(
            &mut f,
            "ERC.THERMAL.SENSOR_CONTRACT",
            false,
            "sensor contract identity/off-board declaration is wrong",
            "sensor-contract",
        );
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
            "ERC.THERMAL.SOURCE",
            c["mpn"] == attrs[id]["mpn"] && c["value"] == attrs[id]["value"],
            format!("source attribute binding {id}"),
            id,
        );
    }
    let expected: BTreeSet<_> = PARTS.iter().map(|x| x.0).collect();
    finding(
        &mut f,
        "ERC.THERMAL.SOURCE",
        ids == expected,
        "exact 27-component source census",
        "ThermalSenseUnit",
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
        "ERC.THERMAL.NATIVE_COMPONENTS",
        native_ids == expected,
        "exact 27-component native census",
        "native",
    );
    for (id, mpn) in PARTS {
        finding(
            &mut f,
            "ERC.THERMAL.PARTS",
            attrs[*id]["mpn"] == *mpn
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
            let id = refs.get(text(&p[0])?).ok_or("unknown source reference")?;
            add(
                &mut compiled,
                format!("{id}.{}", text(&p[1])?),
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
        "ERC.THERMAL.TOPOLOGY",
        compiled == intent,
        "compiled source equals complete pin/net intent",
        "ThermalSenseUnit",
    );
    finding(
        &mut f,
        "ERC.THERMAL.TOPOLOGY",
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
    finding(&mut f,"ERC.THERMAL.STRICT_PIN_MAP",strict_ok&&strict==intent.keys().cloned().collect(),"strict source pin map validates reference, pin/pad identity, uniqueness, and complete coverage","source");
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
        "ERC.THERMAL.CONNECTIVITY",
        cluster_ok && by_net == expected_by_net,
        "one native connectivity cluster per authored net with exact node sets",
        "native",
    );
    finding(
        &mut f,
        "ERC.THERMAL.CONNECTIVITY",
        !arr(native, "traces")?.is_empty(),
        "native routed copper exists",
        "native",
    );
    let sensor_ok = s(contract, "mpn")? == "NTCALUG01A104GA"
        && contract["r25_ohm"].as_f64() == Some(100000.)
        && contract["r25_tolerance"].as_f64() == Some(0.02)
        && contract["beta_k"].as_f64() == Some(4190.)
        && contract["beta_tolerance"].as_f64() == Some(0.015)
        && contract["beta_interval_c"] == serde_json::json!([25., 85.])
        && contract["temperature_rating_c"] == serde_json::json!([-55., 150.])
        && contract["temperature_rating_scope"] == "sensor assembly without connector"
        && contract["supply_v"] == serde_json::json!([3.135, 3.465])
        && contract["qualification"] == "indeterminate"
        && contract["channels"]["hs"]
            == serde_json::json!({"nominal_trip_c":85.0,"nominal_release_c":70.0})
        && contract["channels"]["coil"]
            == serde_json::json!({"nominal_trip_c":120.0,"nominal_release_c":100.0});
    finding(&mut f,"ERC.THERMAL.SENSOR_CONTRACT",sensor_ok,"exact sensor identity, rating scope, supply range, channel targets, and qualification contract","sensor-contract");
    for id in ["hs_filter", "hs_bypass", "coil_filter", "coil_bypass"] {
        finding(
            &mut f,
            "ERC.THERMAL.PARTS",
            attrs[id]["value"] == "100nF +/- 10%" && attrs[id]["voltage_rating"] == "50V",
            format!("{id} capacitor value and 50V rating"),
            id,
        );
    }
    for (id, value) in [
        ("hs_fixed", "10kohm +/- 1%"),
        ("hs_top", "9.09kohm +/- 1%"),
        ("hs_bottom", "11.5kohm +/- 1%"),
        ("hs_hyst", "34.8kohm +/- 1%"),
        ("coil_fixed", "10kohm +/- 1%"),
        ("coil_top", "20kohm +/- 1%"),
        ("coil_bottom", "8.06kohm +/- 1%"),
        ("coil_hyst", "42.2kohm +/- 1%"),
        ("open_top", "1.21kohm +/- 1%"),
        ("open_bottom", "100kohm +/- 1%"),
    ] {
        finding(
            &mut f,
            "ERC.THERMAL.PARTS",
            attrs[id]["value"] == value,
            format!("{id} exact MPN/value/tolerance binding"),
            id,
        );
    }
    for (prefix, nominal_trip, nominal_release) in [("hs", 85., 70.), ("coil", 120., 100.)] {
        let fixed = resistor(attrs, &format!("{prefix}_fixed"))?;
        let top = resistor(attrs, &format!("{prefix}_top"))?;
        let bottom = resistor(attrs, &format!("{prefix}_bottom"))?;
        let hyst = resistor(attrs, &format!("{prefix}_hyst"))?;
        let beta = 4190.;
        let trip = threshold(fixed, top, bottom, hyst, beta, 100000., 0.);
        let rel = threshold(fixed, top, bottom, hyst, beta, 100000., 1.);
        let (tl, th) = corner_range(fixed, top, bottom, hyst, 0.);
        let (rl, rh) = corner_range(fixed, top, bottom, hyst, 1.);
        finding(&mut f,"ERC.THERMAL.THRESHOLDS",(trip-nominal_trip).abs()<1.0&& (rel-nominal_release).abs()<1.0,format!("{prefix} nominal thresholds trip {trip:.2}°C/release {rel:.2}°C; expected {nominal_trip}/{nominal_release}"),prefix);
        finding(&mut f,"ERC.THERMAL.THRESHOLD_CORNERS",tl.is_finite()&&th.is_finite()&&rl.is_finite()&&rh.is_finite()&&tl<=trip&&trip<=th&&rl<=rel&&rel<=rh&&rh<tl,format!("{prefix} exhaustive 64-corner trip {tl:.2}..{th:.2}°C, release {rl:.2}..{rh:.2}°C; conditional model only"),prefix);
    }
    let open_contract = contract["open_detection"]["minimum_valid_temperature_c"] == 0.0
        && contract["open_detection"]["comparator_error_v"] == 0.014
        && contract["open_detection"]["sense_leakage_a"] == 0.000001
        && contract["open_detection"]["reference_leakage_a"] == 0.000002
        && contract["open_detection"]["max_settling_s"] == 0.01
        && contract["open_detection"]["hot_or_open_asserts_fault"] == true
        && contract["open_detection"]["reset_owned_by"] == "external-interlock";
    finding(
        &mut f,
        "ERC.THERMAL.OPEN_CONTRACT",
        open_contract,
        "open detection uses the v2 bounded engineering allowances and external reset ownership",
        "open_detection",
    );
    let (hs_cold, hs_open) = open_margin(
        resistor(attrs, "hs_fixed")?,
        resistor(attrs, "open_top")?,
        resistor(attrs, "open_bottom")?,
        contract,
    );
    let (coil_cold, coil_open) = open_margin(
        resistor(attrs, "coil_fixed")?,
        resistor(attrs, "open_top")?,
        resistor(attrs, "open_bottom")?,
        contract,
    );
    finding(&mut f, "ERC.THERMAL.OPEN_MARGIN", hs_cold > 0. && hs_open > 0.,
        format!("heatsink 0°C/open worst-case comparator margins {hs_cold:.4}/{hs_open:.4} V; IN+ sense > IN- OPEN_REF"), "hs_open_comp");
    finding(&mut f, "ERC.THERMAL.OPEN_MARGIN", coil_cold > 0. && coil_open > 0.,
        format!("coil 0°C/open worst-case comparator margins {coil_cold:.4}/{coil_open:.4} V; IN+ sense > IN- OPEN_REF"), "coil_open_comp");
    let hs_settling = worst_open_settling(
        resistor(attrs, "hs_fixed")?,
        resistor(attrs, "open_top")?,
        resistor(attrs, "open_bottom")?,
        capacitor_max(attrs, "hs_filter")?,
        contract,
    );
    let coil_settling = worst_open_settling(
        resistor(attrs, "coil_fixed")?,
        resistor(attrs, "open_top")?,
        resistor(attrs, "open_bottom")?,
        capacitor_max(attrs, "coil_filter")?,
        contract,
    );
    let max_settling = contract["open_detection"]["max_settling_s"]
        .as_f64()
        .unwrap_or(0.);
    finding(
        &mut f,
        "ERC.THERMAL.OPEN_SETTLING",
        hs_settling.is_finite() && coil_settling.is_finite() && hs_settling <= max_settling && coil_settling <= max_settling,
        format!("worst-case zero-charge threshold crossing hs={hs_settling:.6}s coil={coil_settling:.6}s <= {max_settling:.6}s"),
        "open_detection",
    );
    let gate_map = [
        ("hs_open_comp.1", "HS_OPEN"),
        ("hs_open_comp.2", "gnd"),
        ("hs_open_comp.3", "HS_SENSE"),
        ("hs_open_comp.4", "OPEN_REF"),
        ("hs_open_comp.5", "+3V3"),
        ("coil_open_comp.1", "COIL_OPEN"),
        ("coil_open_comp.2", "gnd"),
        ("coil_open_comp.3", "COIL_SENSE"),
        ("coil_open_comp.4", "OPEN_REF"),
        ("coil_open_comp.5", "+3V3"),
        ("hs_or.1", "HS_HOT"),
        ("hs_or.2", "HS_OPEN"),
        ("hs_or.3", "gnd"),
        ("hs_or.4", "HS_FAULT"),
        ("hs_or.5", "+3V3"),
        ("coil_or.1", "COIL_HOT"),
        ("coil_or.2", "COIL_OPEN"),
        ("coil_or.3", "gnd"),
        ("coil_or.4", "COIL_FAULT"),
        ("coil_or.5", "+3V3"),
    ];
    let gate_ok = gate_map
        .iter()
        .all(|(pin, net)| compiled.get(*pin).is_some_and(|actual| actual == net));
    finding(&mut f, "ERC.THERMAL.GATE_PIN_MAP", gate_ok,
        "independent TLV9031 and SN74LVC1G32 pin map preserves sense polarity and HOT/OPEN OR inputs", "open_detection");
    finding(&mut f, "ERC.THERMAL.FAULT_LOGIC", intent.get("hs_or.1") == Some(&"HS_HOT".into())
        && intent.get("hs_or.2") == Some(&"HS_OPEN".into())
        && intent.get("coil_or.1") == Some(&"COIL_HOT".into())
        && intent.get("coil_or.2") == Some(&"COIL_OPEN".into())
        && intent.get("hs_or.4") == Some(&"HS_FAULT".into())
        && intent.get("coil_or.4") == Some(&"COIL_FAULT".into()),
        "each channel fault is the logical OR of independently wired HOT and OPEN comparator outputs", "fault_logic");
    let truth = [
        (false, false, false),
        (true, false, true),
        (false, true, true),
        (true, true, true),
    ];
    finding(
        &mut f,
        "ERC.THERMAL.FAULT_CASES",
        truth
            .iter()
            .all(|(hot, open, expected)| fault_or(*hot, *open) == *expected),
        "SN74LVC1G32 truth table: each asserted input and both asserted inputs produce HIGH",
        "fault_logic",
    );
    let hs_analog = analog_fault_cases(
        ChannelModel {
            fixed: resistor(attrs, "hs_fixed")?,
            top: resistor(attrs, "hs_top")?,
            bottom: resistor(attrs, "hs_bottom")?,
            hyst: resistor(attrs, "hs_hyst")?,
        },
        resistor(attrs, "open_top")?,
        resistor(attrs, "open_bottom")?,
        85.1,
    );
    let coil_analog = analog_fault_cases(
        ChannelModel {
            fixed: resistor(attrs, "coil_fixed")?,
            top: resistor(attrs, "coil_top")?,
            bottom: resistor(attrs, "coil_bottom")?,
            hyst: resistor(attrs, "coil_hyst")?,
        },
        resistor(attrs, "open_top")?,
        resistor(attrs, "open_bottom")?,
        120.1,
    );
    finding(&mut f, "ERC.THERMAL.ANALOG_FAULT_CASES", hs_analog && coil_analog,
        "analog sense/reference evaluation faults at hot, open, and both short conditions while remaining clear at 0°C and reconnect", "fault_logic");
    for msg in ["TLV3201 common-mode, output swing, offset and internal hysteresis applicability across the 3.135–3.465 V monitor rail", "TLV9031 input common-mode, output swing, offset and leakage applicability across the 3.135–3.465 V monitor rail", "SN74LVC1G32 input/output thresholds and rail applicability across the 3.135–3.465 V monitor rail", "beta extrapolation to coil 120°C and comparator hysteresis", "external connector 85°C limit, mounting, thermal coupling, and self-heating", "sensor harness open/short behavior and downstream latch integration", "power-off behavior and system integration"] { f.push(Finding::indeterminate("ERC.THERMAL.QUALIFICATION",msg,"ThermalSenseUnit")); }
    Ok(f)
}
pub fn validate(source: &str, native: &str, contract: &str) -> CheckReport {
    let r = serde_json::from_str(source)
        .and_then(|s| serde_json::from_str(native).map(|n| (s, n)))
        .and_then(|(s, n)| serde_json::from_str(contract).map(|c| (s, n, c)))
        .map_err(|e| e.to_string())
        .and_then(|(s, n, c)| inspect(&s, &n, &c));
    let findings =
        r.unwrap_or_else(|e| vec![Finding::fail("ERC.THERMAL.INPUT", e, "ThermalSenseUnit")]);
    let rules = findings
        .iter()
        .map(|x| x.rule.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    CheckReport::from_findings(findings, rules, vec![])
}

#[cfg(test)]
mod tests {
    use super::*;
    fn r(n: f64) -> R {
        R {
            n,
            lo: n * 0.99,
            hi: n * 1.01,
        }
    }

    #[test]
    fn thermal_math_matches_independent_loaded_network_audit() {
        // Independent KCL/beta audit retained in thermal-sense/MODEL.md.
        // 0.015 C allows only rounding of the independently supplied 0.01 C values.
        for (values, expected) in [
            (
                [10000., 9090., 11500., 34800.],
                [84.96, 69.79, 82.40, 87.62, 67.65, 72.01],
            ),
            (
                [10000., 20000., 8060., 42200.],
                [119.6452, 99.9624, 116.0168, 123.4442, 96.9587, 103.0987],
            ),
        ] {
            let [fixed, top, bottom, hyst] = values.map(r);
            let (tl, th) = corner_range(fixed, top, bottom, hyst, 0.);
            let (rl, rh) = corner_range(fixed, top, bottom, hyst, 1.);
            let actual = [
                threshold(fixed, top, bottom, hyst, 4190., 100000., 0.),
                threshold(fixed, top, bottom, hyst, 4190., 100000., 1.),
                tl,
                th,
                rl,
                rh,
            ];
            for (actual, expected) in actual.into_iter().zip(expected) {
                assert!((actual - expected).abs() < 0.015, "{actual} != {expected}");
            }
        }
    }

    #[test]
    fn open_detection_numeric_corner_reference_is_independent() {
        let contract = serde_json::json!({"open_detection":{"sense_leakage_a":1e-6,"reference_leakage_a":2e-6,"comparator_error_v":0.014}});
        let margin = open_margin(r(10000.), r(1210.), r(100000.), &contract);
        let settling = worst_open_settling(r(10000.), r(1210.), r(100000.), 110e-9, &contract);
        assert!((margin.0 - 0.0161).abs() < 0.001, "cold margin {margin:?}");
        assert!((margin.1 - 0.0103).abs() < 0.001, "open margin {margin:?}");
        assert!((settling - 0.00635).abs() < 0.0002, "settling {settling}");
    }
}
