//! Measurements from retained ngspice ASCII rawfiles. No submitted scores are trusted.
use anyhow::{bail, ensure, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

const REQUIRED: [&str; 3] = ["startup", "input_variation", "load_variation"];
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn digest(v: &Value) -> bool {
    v.as_str()
        .is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
}
fn number(v: &Value, key: &str) -> Result<f64> {
    let n = v[key]
        .as_f64()
        .with_context(|| format!("missing numeric {key}"))?;
    ensure!(n.is_finite(), "nonfinite {key}");
    Ok(n)
}

struct Waveform {
    time: Vec<f64>,
    signals: BTreeMap<String, Vec<f64>>,
}
fn parse_raw(text: &str) -> Result<Waveform> {
    ensure!(text.len() <= 32 * 1024 * 1024, "rawfile exceeds limit");
    let (header, body) = text
        .split_once("Values:\n")
        .context("ASCII Values section missing")?;
    ensure!(
        header.lines().any(|l| l.trim() == "Flags: real"),
        "only real rawfiles supported"
    );
    let count = |key: &str| -> Result<usize> {
        header
            .lines()
            .find_map(|l| l.strip_prefix(key))
            .context("rawfile header count missing")?
            .trim()
            .parse()
            .context("invalid rawfile count")
    };
    let nv = count("No. Variables:")?;
    let np = count("No. Points:")?;
    ensure!(
        (4..=64).contains(&nv) && (3..=1_000_000).contains(&np),
        "unsupported waveform dimensions"
    );
    let variables = header
        .split_once("Variables:\n")
        .context("Variables section missing")?
        .1;
    let mut names = Vec::new();
    for (index, line) in variables
        .lines()
        .filter(|l| !l.trim().is_empty())
        .enumerate()
    {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure!(
            fields.len() == 3 && fields[0].parse::<usize>()? == index,
            "malformed variable index"
        );
        let name = fields[1].to_ascii_lowercase();
        let unit = match name.as_str() {
            "time" => "time",
            n if n.starts_with("v(") => "voltage",
            n if n.starts_with("i(") => "current",
            _ => bail!("unsupported variable name"),
        };
        ensure!(
            fields[2] == unit && !names.contains(&name),
            "wrong units or duplicate signal"
        );
        names.push(name);
    }
    ensure!(
        names.len() == nv && names[0] == "time",
        "variable census mismatch"
    );
    let tokens: Vec<_> = body.split_whitespace().collect();
    ensure!(
        tokens.len() == np * (nv + 1),
        "truncated or extra waveform data"
    );
    let mut columns = vec![Vec::with_capacity(np); nv];
    for (index, row) in tokens.chunks_exact(nv + 1).enumerate() {
        ensure!(row[0].parse::<usize>()? == index, "wrong sample index");
        for (col, token) in columns.iter_mut().zip(&row[1..]) {
            let value: f64 = token.parse()?;
            ensure!(value.is_finite(), "nonfinite waveform");
            col.push(value);
        }
    }
    let time = columns[0].clone();
    ensure!(
        time[0] >= 0.0 && time.windows(2).all(|w| w[1] > w[0]),
        "invalid timebase"
    );
    let signals = names.into_iter().zip(columns).collect::<BTreeMap<_, _>>();
    for name in ["v(out)", "v(in)", "i(vin)"] {
        ensure!(signals.contains_key(name), "missing signal {name}");
    }
    Ok(Waveform { time, signals })
}

fn measure(scenario: &Value) -> Result<Value> {
    let text = scenario["raw_waveform"]
        .as_str()
        .context("raw waveform missing")?;
    ensure!(
        scenario["artifact_sha256"] == hash(text.as_bytes()),
        "waveform hash mismatch"
    );
    let wave = parse_raw(text)?;
    let spec = &scenario["spec"];
    let start = number(spec, "window_start_s")?;
    let end = number(spec, "window_end_s")?;
    let step = number(spec, "max_step_s")?;
    let target = number(spec, "target_v")?;
    let band = number(spec, "settling_band_v")?;
    let event = number(spec, "event_s")?;
    ensure!(
        start >= 0.0
            && end > start
            && step > 0.0
            && target > 0.0
            && band > 0.0
            && event >= 0.0
            && event < end,
        "invalid scenario settings"
    );
    ensure!(
        wave.time[0] <= event && wave.time[0] <= start && *wave.time.last().unwrap() >= end,
        "truncated time coverage"
    );
    ensure!(
        wave.time
            .windows(2)
            .all(|w| w[1] - w[0] <= step * (1.0 + 1e-9)),
        "under-resolved waveform"
    );
    let times = &wave.time;
    let output = &wave.signals["v(out)"];
    let indexes: Vec<_> = times
        .iter()
        .enumerate()
        .filter_map(|(i, t)| (*t >= start && *t <= end).then_some(i))
        .collect();
    ensure!(indexes.len() >= 3, "too few window samples");
    let extrema = |signal: &[f64]| -> (f64, f64) {
        indexes
            .iter()
            .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), i| {
                (lo.min(signal[*i]), hi.max(signal[*i]))
            })
    };
    let average = |signal: &[f64]| -> f64 {
        let mut area = 0.0;
        for i in 1..times.len() {
            let left = times[i - 1].max(start);
            let right = times[i].min(end);
            if right <= left {
                continue;
            }
            let slope = (signal[i] - signal[i - 1]) / (times[i] - times[i - 1]);
            let a = signal[i - 1] + slope * (left - times[i - 1]);
            let b = signal[i - 1] + slope * (right - times[i - 1]);
            area += (a + b) * 0.5 * (right - left);
        }
        area / (end - start)
    };
    let (lo, hi) = extrema(output);
    let last_outside = times
        .iter()
        .enumerate()
        .filter(|(i, t)| **t >= event && **t <= end && (output[*i] - target).abs() > band)
        .map(|(i, _)| i)
        .next_back();
    let settling = match last_outside {
        None => 0.0,
        Some(i) => {
            *times
                .get(i + 1)
                .filter(|t| **t <= end)
                .context("output never settled")?
                - event
        }
    };
    let (vin_lo, vin_hi) = extrema(&wave.signals["v(in)"]);
    let mut measured = json!({"vout_avg":average(output),"vout_min":lo,"vout_max":hi,"vout_pp":hi-lo,
        "vin_avg":average(&wave.signals["v(in)"]),"iin_avg":average(&wave.signals["i(vin)"]),
        "vin_span":vin_hi-vin_lo,"overshoot_v":(hi-target).max(0.0),"undershoot_v":(target-lo).max(0.0),
        "settling_s":settling,"duration_s":end-start});
    if let Some(load) = wave.signals.get("i(load)") {
        let (a, b) = extrema(load);
        measured["load_span"] = json!(b - a);
    }
    let limits = spec["limits"]
        .as_object()
        .context("frozen limits missing")?;
    for key in ["vout_avg", "vout_pp", "overshoot_v", "settling_s"] {
        ensure!(limits.contains_key(key), "mandatory limit {key} missing");
    }
    let name = scenario["name"].as_str().context("scenario name missing")?;
    if name == "input_variation" {
        ensure!(
            limits
                .get("vin_span")
                .and_then(|v| v["min"].as_f64())
                .is_some_and(|v| v > 0.0),
            "input excitation limit missing"
        );
    }
    if name == "load_variation" {
        ensure!(
            limits
                .get("load_span")
                .and_then(|v| v["min"].as_f64())
                .is_some_and(|v| v > 0.0),
            "load excitation limit missing"
        );
    }
    let mut violations = Vec::new();
    for (key, limit) in limits {
        let value = measured[key]
            .as_f64()
            .with_context(|| format!("unsupported measurement {key}"))?;
        let min = number(limit, "min")?;
        let max = number(limit, "max")?;
        ensure!(min <= max, "reversed measurement limits");
        if value < min || value > max {
            violations.push(json!({"id":"measurement_out_of_limit","measurement":key,"actual":value,"min":min,"max":max}));
        }
    }
    Ok(
        json!({"name":name,"status":if violations.is_empty(){"pass"}else{"fail"},"measurements":measured,"findings":violations}),
    )
}

pub fn evaluate(input: Value) -> Result<Value> {
    ensure!(
        input["profile"] == "engineering-simulation",
        "unexpected simulation profile"
    );
    let mut findings = Vec::new();
    let mut block = |id: &str, message: &str| findings.push(json!({"id":id,"message":message}));
    let model = &input["model"];
    if model["mpn"] != "LMR51430XDDCR"
        || model["reference_voltage"] != json!(0.6)
        || model["frequency_hz"] != json!(500000)
        || model["mode"] != "PFM"
    {
        block(
            "exact_model_missing",
            "exact LMR51430XDDCR 500 kHz PFM, 0.6 V model identity is required",
        );
    }
    if model["legacy_negative_control"] == true || model["reference_voltage"] == json!(0.8) {
        block(
            "legacy_model_rejected",
            "legacy averaged 0.8 V model is inadmissible",
        );
    }
    let q = &model["qualification"];
    if !crate::qualification::approved("model", q) {
        block(
            "qualification_not_approved",
            "exact model receipt is absent from the trusted approval registry",
        );
    }
    if !digest(&model["sha256"])
        || q["model_sha256"] != model["sha256"]
        || !digest(&q["evidence_sha256"])
        || q["source"].as_str().is_none_or(str::is_empty)
        || q["license"].as_str().is_none_or(str::is_empty)
        || q["reviewed_by"].as_str().is_none_or(str::is_empty)
        || q["status"] != "pass"
        || input["qualification_verified"] != true
    {
        block(
            "model_not_qualified",
            "reviewed independent qualification evidence bound to the exact model is required",
        );
    }
    for behavior in REQUIRED {
        if !q["coverage"]
            .as_array()
            .is_some_and(|a| a.iter().any(|v| v == behavior))
        {
            block("unsupported_coverage", behavior);
        }
    }
    if input["synthetic"] == true || model["synthetic"] == true {
        block(
            "synthetic_evidence",
            "synthetic controls cannot qualify a live circuit",
        );
    }
    for key in ["circuit_sha256", "requirements_sha256", "settings_sha256"] {
        if !digest(&input[key]) {
            block("identity_missing", key);
        }
    }
    if input["reuse"]["requested"] == true {
        let prior = &input["reuse"]["prior_identity"];
        let current = &input["reuse"]["current_identity"];
        for key in [
            "circuit_sha256",
            "requirements_sha256",
            "settings_sha256",
            "model_sha256",
        ] {
            if !digest(&current[key]) || current[key] != prior[key] {
                block("stale_reuse", key);
            }
        }
        if input["reuse"]["parasitic"] == true
            && (!digest(&current["board_sha256"])
                || current["board_sha256"] != prior["board_sha256"])
        {
            block("stale_parasitics", "board changed since extraction");
        }
    }
    let scenarios = input["scenarios"].as_array().cloned().unwrap_or_default();
    if !scenarios.is_empty() {
        let specs: Vec<_> = scenarios.iter().map(|s| s["spec"].clone()).collect();
        if input["settings_sha256"] != hash(&serde_json::to_vec(&specs)?) {
            findings.push(json!({"id":"settings_identity_mismatch","message":"scenario settings differ from their frozen identity"}));
        }
    }
    let mut seen = BTreeSet::new();
    let mut results = Vec::new();
    for scenario in scenarios {
        let name = scenario["name"].as_str().unwrap_or("").to_owned();
        if !REQUIRED.contains(&name.as_str()) || !seen.insert(name.clone()) {
            findings.push(json!({"id":"scenario_identity_invalid","message":name}));
            continue;
        }
        if scenario["status"] != "pass"
            || scenario["synthetic"] == true
            || !digest(&scenario["deck_sha256"])
        {
            findings.push(json!({"id":"scenario_unavailable","message":format!("{name}: {}",scenario["status"])}));
            continue;
        }
        match measure(&scenario) {
            Ok(result) => results.push(result),
            Err(error) => findings
                .push(json!({"id":"waveform_invalid","message":format!("{name}: {error:#}")})),
        }
    }
    for required in REQUIRED {
        if !seen.contains(required) {
            findings.push(json!({"id":"mandatory_scenario_missing","message":required}));
        }
    }
    let status = if !findings.is_empty() {
        "blocked"
    } else if results.iter().any(|r| r["status"] != "pass") {
        "fail"
    } else {
        "pass"
    };
    Ok(
        json!({"stage":"simulation","status":status,"findings":findings,"scenarios":results,"layout_sensitive":false,"hardware_validated":false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_ngspice_rc_control_matches_analytic_response() {
        let w = parse_raw(include_str!(
            "../engineering/scenarios/controls/run/rc_control.raw"
        ))
        .unwrap();
        assert_eq!(w.time.len(), 69);
        let expected = 1.0 - (1.0 - (-1.0_f64).exp()) * (-2.0_f64).exp();
        assert!((w.signals["v(out)"].last().unwrap() - expected).abs() < 0.0001);
    }
    fn scenario() -> Value {
        let mut raw=String::from("Title: software control only\nFlags: real\nNo. Variables: 5\nNo. Points: 5\nVariables:\n0 time time\n1 v(out) voltage\n2 v(in) voltage\n3 i(vin) current\n4 i(load) current\nValues:\n");
        for i in 0..5 {
            raw.push_str(&format!(
                "{i} {}\n3.3\n{}\n-0.2\n{}\n",
                i as f64 * 0.001,
                14.0 + i as f64,
                0.2 + i as f64 * 0.1
            ));
        }
        json!({"name":"startup","status":"pass","raw_waveform":raw,"artifact_sha256":hash(raw.as_bytes()),"deck_sha256":"a".repeat(64),"spec":{
            "window_start_s":0.0,"window_end_s":0.004,"max_step_s":0.0011,"target_v":3.3,"settling_band_v":0.1,"event_s":0.0,
            "limits":{"vout_avg":{"min":3.2,"max":3.4},"vout_pp":{"min":0.0,"max":0.1},"overshoot_v":{"min":0.0,"max":0.1},"settling_s":{"min":0.0,"max":0.002},"vin_span":{"min":1.0,"max":5.0},"load_span":{"min":0.1,"max":1.0}}}})
    }
    #[test]
    fn raw_measurements_pass_and_defect_fails() {
        let mut s = scenario();
        assert_eq!(measure(&s).unwrap()["status"], "pass");
        s["spec"]["limits"]["vout_avg"]["max"] = json!(3.25);
        assert_eq!(measure(&s).unwrap()["status"], "fail");
    }
    #[test]
    fn bad_raw_and_missing_limits_are_rejected() {
        for mutation in ["hash", "units", "time", "resolution", "limits"] {
            let mut s = scenario();
            match mutation {
                "hash" => s["artifact_sha256"] = json!("0".repeat(64)),
                "units" | "time" => {
                    let raw = s["raw_waveform"].as_str().unwrap().replace(
                        if mutation == "units" {
                            "v(out) voltage"
                        } else {
                            "1 0.001"
                        },
                        if mutation == "units" {
                            "v(out) current"
                        } else {
                            "1 0"
                        },
                    );
                    s["artifact_sha256"] = json!(hash(raw.as_bytes()));
                    s["raw_waveform"] = json!(raw);
                }
                "resolution" => s["spec"]["max_step_s"] = json!(0.0001),
                _ => s["spec"]["limits"] = json!({}),
            }
            assert!(measure(&s).is_err(), "{mutation}");
        }
    }
    #[test]
    fn complete_software_chain_and_independent_negative_controls() {
        let d = "a".repeat(64);
        let scenarios: Vec<_> = REQUIRED
            .iter()
            .map(|name| {
                let mut s = scenario();
                s["name"] = json!(name);
                s
            })
            .collect();
        let settings: Vec<_> = scenarios.iter().map(|s| s["spec"].clone()).collect();
        let input = json!({"profile":"engineering-simulation","model":{
            "mpn":"LMR51430XDDCR","reference_voltage":0.6,"frequency_hz":500000,"mode":"PFM","sha256":d,
            "qualification":{"model_sha256":d,"evidence_sha256":d,"source":"software control only","license":"test","reviewed_by":"test","status":"pass","coverage":REQUIRED}},
            "qualification_verified":true,"circuit_sha256":d,"requirements_sha256":d,"settings_sha256":hash(&serde_json::to_vec(&settings).unwrap()),"scenarios":scenarios});
        assert_eq!(evaluate(input.clone()).unwrap()["status"], "blocked");
        for defect in [
            "synthetic",
            "qualification",
            "coverage",
            "settings",
            "raw",
            "duplicate",
        ] {
            let mut bad = input.clone();
            match defect {
                "synthetic" => bad["synthetic"] = json!(true),
                "qualification" => bad["qualification_verified"] = json!(false),
                "coverage" => bad["model"]["qualification"]["coverage"] = json!([]),
                "settings" => bad["scenarios"][0]["spec"]["target_v"] = json!(5.0),
                "raw" => bad["scenarios"][0]["raw_waveform"] = json!(""),
                _ => bad["scenarios"][1]["name"] = json!("startup"),
            }
            assert_ne!(evaluate(bad).unwrap()["status"], "pass", "{defect}");
        }
    }
}
