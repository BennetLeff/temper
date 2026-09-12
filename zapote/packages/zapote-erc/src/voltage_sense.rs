//! Fixed VoltageSenseUnit intent checked against compiled and native evidence.
//! Electrical limits are conditional; omitted device behavior stays indeterminate.
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::{CheckReport, Finding};

const TOPOLOGY: &[(&str, &[&str])] = &[
    ("BUS_PLUS", &["input.1", "r_ovp_top1.1", "r_adc_top1.1"]),
    (
        "BUS_RETURN",
        &[
            "input.2",
            "host.2",
            "r_ovp_bottom.2",
            "r_adc_bottom.2",
            "comp.2",
            "reference.2",
            "c_adc.2",
            "c_comp.2",
            "c_ref_in.2",
            "c_ref_out.2",
        ],
    ),
    (
        "+3V3",
        &[
            "host.1",
            "comp.5",
            "reference.3",
            "reference.4",
            "c_comp.1",
            "c_ref_in.1",
        ],
    ),
    ("OVP_MID1", &["r_ovp_top1.2", "r_ovp_top2.1"]),
    ("OVP_MID2", &["r_ovp_top2.2", "r_ovp_top3.1"]),
    (
        "OVP_SENSE",
        &["r_ovp_top3.2", "r_ovp_bottom.1", "r_hyst.1", "comp.3"],
    ),
    ("OVP_FAULT", &["r_hyst.2", "comp.1", "host.3"]),
    ("VREF_2V5", &["reference.5", "comp.4", "c_ref_out.1"]),
    (
        "BUS_MON",
        &["r_adc_top3.2", "r_adc_bottom.1", "c_adc.1", "host.4"],
    ),
    ("ADC_MID1", &["r_adc_top1.2", "r_adc_top2.1"]),
    ("ADC_MID2", &["r_adc_top2.2", "r_adc_top3.1"]),
    ("vbias", &["reference.1"]),
];
const PARTS: &[(&str, &str)] = &[
    ("input", "691253500002"),
    ("host", "B4B-XH-A(LF)(SN)"),
    ("comp", "TLV3201AIDBVR"),
    ("reference", "REF2025AIDDCR"),
    ("r_ovp_top1", "RC1206FR-07430KL"),
    ("r_ovp_top2", "RC1206FR-07430KL"),
    ("r_ovp_top3", "RC1206FR-07430KL"),
    ("r_ovp_bottom", "RT0603BRD0716K9L"),
    ("r_hyst", "RT0603BRD07487KL"),
    ("r_adc_top1", "RC1206FR-07300KL"),
    ("r_adc_top2", "RC1206FR-07300KL"),
    ("r_adc_top3", "RC1206FR-07300KL"),
    ("r_adc_bottom", "RC0603FR-0710KL"),
    ("c_adc", "C0603C104K5RACTU"),
    ("c_comp", "C0603C104K5RACTU"),
    ("c_ref_in", "C0603C104K5RACTU"),
    ("c_ref_out", "C0603C104K5RACTU"),
];
fn text(v: &Value) -> Result<&str, String> {
    v.as_str()
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "missing nonempty string".into())
}
fn array(v: &Value) -> Result<&[Value], String> {
    v.as_array()
        .map(Vec::as_slice)
        .ok_or_else(|| "missing array".into())
}
fn check(f: &mut Vec<Finding>, rule: &str, ok: bool, message: impl Into<String>) {
    f.push(if ok {
        Finding::pass(rule, message, "VoltageSenseUnit")
    } else {
        Finding::fail(rule, message, "VoltageSenseUnit")
    });
}
fn insert(map: &mut BTreeMap<String, String>, pin: String, net: String) -> Result<(), String> {
    if map.insert(pin.clone(), net).is_some() {
        return Err(format!("duplicate pin {pin}"));
    }
    Ok(())
}
#[derive(Clone, Copy)]
struct R {
    nominal: f64,
    min: f64,
    max: f64,
}
fn resistor(attrs: &Value, id: &str) -> Result<R, String> {
    let value = text(&attrs[id]["value"])?;
    let (nominal, tol) = value
        .split_once("+/-")
        .ok_or_else(|| format!("missing tolerance: {id}"))?;
    let nominal = nominal.trim();
    let (number, scale) = if let Some(n) = nominal.strip_suffix("kohm") {
        (n, 1000.)
    } else if let Some(n) = nominal.strip_suffix("ohm") {
        (n, 1.)
    } else {
        return Err(format!("unsupported resistor unit: {id}"));
    };
    let nominal: f64 = number
        .trim()
        .parse::<f64>()
        .map_err(|_| format!("invalid resistance: {id}"))?
        * scale;
    let tol: f64 = tol
        .trim()
        .strip_suffix('%')
        .ok_or("missing percent")?
        .trim()
        .parse::<f64>()
        .map_err(|_| "invalid tolerance")?
        / 100.;
    if !nominal.is_finite() || nominal <= 0. || !tol.is_finite() || !(0. ..1.).contains(&tol) {
        return Err(format!("invalid resistor bounds: {id}"));
    }
    // Part-family ceilings at |T-25 C| <=60 C; do not infer tempco from numeric value.
    let tc = if id == "r_hyst" || id == "r_ovp_bottom" {
        25e-6
    } else {
        100e-6
    };
    Ok(R {
        nominal,
        min: nominal * (1. - tol) * (1. - 60. * tc),
        max: nominal * (1. + tol) * (1. + 60. * tc),
    })
}
fn sum(rs: &[R]) -> R {
    R {
        nominal: rs.iter().map(|r| r.nominal).sum(),
        min: rs.iter().map(|r| r.min).sum(),
        max: rs.iter().map(|r| r.max).sum(),
    }
}
fn inspect(source: &Value, native: &Value) -> Result<Vec<Finding>, String> {
    let mut f = Vec::new();
    if text(&source["entry"])? != "elec/src/voltage_sense_unit.ato:VoltageSenseUnit" {
        return Err("wrong standalone source entry".into());
    }
    let attrs = &source["source_attributes"];
    let components = array(&source["components"])?;
    let actual = array(&native["components"])?;
    let mut refs = BTreeMap::new();
    let mut source_ids = BTreeSet::new();
    let mut native_ids = BTreeSet::new();
    for c in components {
        let id = text(&c["instance_path"])?;
        if !source_ids.insert(id) || refs.insert(text(&c["reference"])?, id).is_some() {
            return Err("duplicate source component/reference".into());
        }
        check(
            &mut f,
            "ERC.VOLTAGE.SOURCE",
            c["mpn"] == attrs[id]["mpn"] && c["value"] == attrs[id]["value"],
            format!("compiled component/attribute binding {id}"),
        );
    }
    let expected_ids: BTreeSet<_> = PARTS.iter().map(|(id, _)| *id).collect();
    check(
        &mut f,
        "ERC.VOLTAGE.SOURCE",
        source_ids == expected_ids,
        "exact 17-component source census",
    );
    let mut pads = BTreeMap::new();
    for c in actual {
        let id = text(&c["id"])?;
        if !native_ids.insert(id) {
            return Err("duplicate native component".into());
        }
        for p in array(&c["footprint_pads"])? {
            insert(
                &mut pads,
                format!("{id}.{}", text(&p["pad"])?),
                text(&p["net"])?.into(),
            )?;
        }
    }
    check(
        &mut f,
        "ERC.VOLTAGE.SOURCE",
        native_ids == expected_ids,
        "exact 17-component native census",
    );
    for (id, mpn) in PARTS {
        check(
            &mut f,
            "ERC.VOLTAGE.PARTS",
            text(&attrs[*id]["mpn"])? == *mpn
                && actual.iter().any(|c| c["id"] == *id && c["mpn"] == *mpn),
            format!("qualified part identity {id}: {mpn}"),
        );
    }
    for (id, expected) in [
        ("r_ovp_top1", "430kohm +/- 1%"),
        ("r_ovp_top2", "430kohm +/- 1%"),
        ("r_ovp_top3", "430kohm +/- 1%"),
        ("r_ovp_bottom", "16.9kohm +/- 0.1%"),
        ("r_hyst", "487kohm +/- 0.1%"),
        ("r_adc_top1", "300kohm +/- 1%"),
        ("r_adc_top2", "300kohm +/- 1%"),
        ("r_adc_top3", "300kohm +/- 1%"),
        ("r_adc_bottom", "10kohm +/- 1%"),
    ] {
        check(
            &mut f,
            "ERC.VOLTAGE.PARTS",
            attrs[id]["value"] == expected,
            format!("value/tolerance matches exact MPN for {id}"),
        );
    }
    let mut intent = BTreeMap::new();
    for (net, nodes) in TOPOLOGY {
        for node in *nodes {
            insert(&mut intent, (*node).into(), (*net).into())?;
        }
    }
    let mut compiled = BTreeMap::new();
    for net in array(&source["bridge"]["nets"])? {
        for pair in array(&net["nodes"])? {
            let pair = array(pair)?;
            if pair.len() != 2 {
                return Err("malformed source endpoint".into());
            }
            let id = refs
                .get(text(&pair[0])?)
                .ok_or("unknown source reference")?;
            insert(
                &mut compiled,
                format!("{id}.{}", text(&pair[1])?),
                text(&net["name"])?.into(),
            )?;
        }
    }
    let mut connected = BTreeMap::new();
    for c in array(&native["connections"])? {
        insert(
            &mut connected,
            format!("{}.{}", text(&c["component"])?, text(&c["pin"])?),
            text(&c["net"])?.into(),
        )?;
    }
    check(
        &mut f,
        "ERC.VOLTAGE.TOPOLOGY",
        compiled == intent,
        "compiled source equals complete independent pin/net intent",
    );
    check(
        &mut f,
        "ERC.VOLTAGE.TOPOLOGY",
        connected == intent && pads == intent,
        "native pad and connection census equals complete pin/net intent",
    );
    let mut strict = BTreeSet::new();
    for p in array(&source["strict_pin_map"])? {
        let id = text(&p["instance_path"])?;
        let pad = text(&p["pad"])?;
        if text(&p["pin"])? != pad
            || refs.get(text(&p["reference"])?).copied() != Some(id)
            || !strict.insert(format!("{id}.{pad}"))
        {
            return Err("invalid or duplicate strict pin map".into());
        }
    }
    check(
        &mut f,
        "ERC.VOLTAGE.SOURCE",
        strict == intent.keys().cloned().collect(),
        "strict source map covers every physical pin exactly once",
    );
    let clusters = array(&native["connectivity_clusters"])?;
    for (net, nodes) in TOPOLOGY {
        let groups: Vec<_> = clusters.iter().filter(|c| c["net"] == *net).collect();
        let complete = groups.len() == 1
            && array(&groups[0]["nodes"]).is_ok_and(|values| {
                let actual: BTreeSet<_> = values.iter().filter_map(Value::as_str).collect();
                actual.len() == values.len() && actual == nodes.iter().copied().collect()
            });
        check(
            &mut f,
            "ERC.VOLTAGE.CONNECTIVITY",
            complete,
            format!("all {net} endpoints in exactly one native copper cluster"),
        );
    }
    check(
        &mut f,
        "ERC.VOLTAGE.CONNECTIVITY",
        clusters.len() == TOPOLOGY.len(),
        "no extra or fragmented native connectivity clusters",
    );
    check(
        &mut f,
        "ERC.VOLTAGE.CONNECTIVITY",
        !array(&native["traces"])?.is_empty(),
        "native routed copper exists",
    );
    electrical(attrs, &mut f)?;
    for gap in ["TLV3201 internal hysteresis has no guaranteed maximum; 3.3V/common-mode output and offset applicability require qualification", "nonisolated BUS_RETURN/host return must be reconciled with cooker PE and doubler midpoint before integration", "receiver loading/acquisition and effective filter capacitance", "power-off, bottom-resistor-open, brownout, surge/clamp behavior and assembled insulation", "physical accuracy and end-to-end shutdown timing: NOT RUN"] {
        f.push(Finding::indeterminate("ERC.VOLTAGE.QUALIFICATION",gap,"VoltageSenseUnit"));
    }
    Ok(f)
}
fn electrical(attrs: &Value, f: &mut Vec<Finding>) -> Result<(), String> {
    let ovp = [
        resistor(attrs, "r_ovp_top1")?,
        resistor(attrs, "r_ovp_top2")?,
        resistor(attrs, "r_ovp_top3")?,
    ];
    let adc = [
        resistor(attrs, "r_adc_top1")?,
        resistor(attrs, "r_adc_top2")?,
        resistor(attrs, "r_adc_top3")?,
    ];
    let rt = sum(&ovp);
    let ra = sum(&adc);
    let rb = resistor(attrs, "r_ovp_bottom")?;
    let rh = resistor(attrs, "r_hyst")?;
    let bottom = resistor(attrs, "r_adc_bottom")?;
    let adc_max = 250. * bottom.max / (ra.min + bottom.max);
    let adc_min = 250. * bottom.min / (ra.max + bottom.min);
    check(
        f,
        "ERC.VOLTAGE.ADC_RANGE",
        adc_max <= 3.1,
        format!(
            "ADC monitor at 250V, tolerance/tempco bounds [{adc_min:.6},{adc_max:.6}] V <=3.1V"
        ),
    );
    let vr = [
        2.5 * (1. - 0.0005) * (1. - 60. * 8e-6),
        2.5 * (1. + 0.0005) * (1. + 60. * 8e-6),
    ];
    let trip = |r: f64, b: f64, h: f64, v: f64, out: f64| v * (1. + r / b + r / h) - out * r / h;
    let ideal = [
        trip(rt.min, rb.max, rh.max, vr[0], 0.),
        trip(rt.max, rb.min, rh.min, vr[1], 0.),
    ];
    check(f,"ERC.VOLTAGE.OVP_MODEL",ideal[0]>=195. && ideal[1]<=205.,format!("ideal comparator rising trip, resistor/reference bounds [{:.6},{:.6}] V within195..205V",ideal[0],ideal[1]));
    // Same-device hysteresis cancels Vref/offset; never subtract thresholds
    // from different resistor/offset corners to claim hysteresis bounds.
    let hyst = [3.3 * 0.95 * rt.min / rh.max, 3.3 * 1.05 * rt.max / rh.min];
    check(
        f,
        "ERC.VOLTAGE.OVP_MODEL",
        hyst[0] >= 5. && hyst[1] <= 10.,
        format!(
            "ideal comparator external hysteresis [{:.6},{:.6}] V within5..10V",
            hyst[0], hyst[1]
        ),
    );
    let nonideal = [
        trip(rt.min, rb.max, rh.max, vr[0] - 0.005, 0.4),
        trip(rt.max, rb.min, rh.min, vr[1] + 0.005, 0.),
    ];
    f.push(Finding::indeterminate("ERC.VOLTAGE.OVP_APPLICABILITY",format!("sensitivity scenario +/-5mV effective offset, VOL0..0.4V: rising [{:.6},{:.6}] V; excludes unbounded internal hysteresis and is not a guaranteed device certificate",nonideal[0],nonideal[1]),"comp"));
    for (prefix, chain) in [("r_ovp_top", ovp), ("r_adc_top", adc)] {
        for short in [None, Some(0), Some(1), Some(2)] {
            let min_total: f64 = chain
                .iter()
                .enumerate()
                .filter(|(i, _)| Some(*i) != short)
                .map(|(_, r)| r.min)
                .sum();
            for (i, r) in chain.iter().enumerate().filter(|(i, _)| Some(*i) != short) {
                let id = format!("{prefix}{}", i + 1);
                if attrs[&id]["power_rating"] != "0.25W" || attrs[&id]["voltage_rating"] != "200V" {
                    return Err(format!("unqualified resistor rating: {id}"));
                }
                // Ignore the positive bottom resistance: conservative upper bound.
                let amps = 250. / min_total;
                let volts = 250. * r.max / (r.max + min_total - r.min);
                let watts = amps * amps * r.max;
                check(f,"ERC.VOLTAGE.STRESS",volts<=200. && watts<=0.125,format!("{id} short={short:?}: conservative {volts:.3}V/{watts:.6}W <=200V/50% of0.25W"));
            }
        }
    }
    for id in ["c_adc", "c_comp", "c_ref_in", "c_ref_out"] {
        check(
            f,
            "ERC.VOLTAGE.PARTS",
            attrs[id]["value"] == "100nF +/- 10%" && attrs[id]["voltage_rating"] == "50V",
            format!("capacitor source rating/value {id}"),
        );
    }
    Ok(())
}
pub fn validate(source_utf8: &str, native_utf8: &str) -> CheckReport {
    let result = serde_json::from_str(source_utf8)
        .map_err(|e| format!("source JSON: {e}"))
        .and_then(|s| {
            serde_json::from_str(native_utf8)
                .map_err(|e| format!("native JSON: {e}"))
                .and_then(|n| inspect(&s, &n))
        });
    let findings = result.unwrap_or_else(|message| {
        vec![Finding::fail(
            "ERC.VOLTAGE.INPUT",
            message,
            "VoltageSenseUnit",
        )]
    });
    let checked = findings
        .iter()
        .map(|f| f.rule.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    CheckReport::from_findings(findings, checked, vec![])
}
