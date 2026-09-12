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
    ("coil_fixed", "RC0603FR-073K32L"),
    ("coil_top", "RC0603FR-073K16L"),
    ("coil_bottom", "RC0603FR-074K42L"),
    ("coil_hyst", "RC0603FR-0711K5L"),
    ("hs_filter", "C0603C104K5RACTU"),
    ("hs_bypass", "C0603C104K5RACTU"),
    ("coil_filter", "C0603C104K5RACTU"),
    ("coil_bypass", "C0603C104K5RACTU"),
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
        ],
    ),
    (
        "HS_REF",
        &["hs_top.2", "hs_bottom.1", "hs_hyst.1", "hs_comp.3"],
    ),
    ("HS_FAULT", &["host.3", "hs_hyst.2", "hs_comp.1"]),
    (
        "COIL_SENSE",
        &[
            "host.6",
            "coil_probe.1",
            "coil_fixed.2",
            "coil_comp.4",
            "coil_filter.1",
        ],
    ),
    (
        "COIL_REF",
        &["coil_top.2", "coil_bottom.1", "coil_hyst.1", "coil_comp.3"],
    ),
    ("COIL_FAULT", &["host.4", "coil_hyst.2", "coil_comp.1"]),
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
fn inspect(source: &Value, native: &Value, contract: &Value) -> Result<Vec<Finding>, String> {
    let mut f = Vec::new();
    if s(source, "entry")? != "elec/src/thermal_sense_unit.ato:ThermalSenseUnit" {
        return Err("wrong standalone source entry".into());
    }
    if s(contract, "schema")? != "zapote.thermal.sensor-contract.v1"
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
        "exact 17-component source census",
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
        "exact 17-component native census",
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
        ("coil_fixed", "3.32kohm +/- 1%"),
        ("coil_top", "3.16kohm +/- 1%"),
        ("coil_bottom", "4.42kohm +/- 1%"),
        ("coil_hyst", "11.5kohm +/- 1%"),
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
    for msg in ["TLV3201 common-mode, output swing, offset and internal hysteresis applicability across the 3.135–3.465 V monitor rail", "beta extrapolation to coil 120°C and 3.3V TLV hysteresis", "external connector 85°C limit, mounting, thermal coupling, and self-heating", "sensor open reads cold/healthy and sensor short reads hot; this is an integration gap, not a fault-safe claim", "raw analog monitors approach VCC at cold/open sensor; receiver acquisition, loading and full rail range remain unqualified", "power-off behavior and system integration"] { f.push(Finding::indeterminate("ERC.THERMAL.QUALIFICATION",msg,"ThermalSenseUnit")); }
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
                [3320., 3160., 4420., 11500.],
                [119.96, 100.08, 116.33, 123.77, 97.07, 103.22],
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
}
