//! Rust-owned interpretation of compiled Atopile circuit evidence.
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs,
};

#[derive(Clone, Debug, PartialEq)]
enum Node {
    Atom(String),
    List(Vec<Node>),
}

fn parse_sexp(text: &str) -> Result<Node> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut quoted = false;
    for c in text.chars() {
        if quoted {
            if c == '"' {
                quoted = false;
                tokens.push(current.clone());
                current.clear();
            } else {
                current.push(c);
            }
        } else if c == '"' {
            quoted = true;
        } else if matches!(c, '(' | ')') {
            if !current.is_empty() {
                tokens.push(current.clone());
                current.clear();
            }
            tokens.push(c.to_string());
        } else if c.is_whitespace() {
            if !current.is_empty() {
                tokens.push(current.clone());
                current.clear();
            }
        } else {
            current.push(c);
        }
    }
    ensure!(!quoted && current.is_empty(), "malformed netlist tokens");
    fn one(t: &[String], i: &mut usize) -> Result<Node> {
        ensure!(*i < t.len(), "unexpected netlist end");
        if t[*i] != "(" {
            let a = Node::Atom(t[*i].clone());
            *i += 1;
            return Ok(a);
        }
        *i += 1;
        let mut xs = Vec::new();
        while *i < t.len() && t[*i] != ")" {
            xs.push(one(t, i)?);
        }
        ensure!(*i < t.len(), "unclosed netlist list");
        *i += 1;
        Ok(Node::List(xs))
    }
    let mut i = 0;
    let mut roots = Vec::new();
    while i < tokens.len() {
        roots.push(one(&tokens, &mut i)?);
    }
    Ok(Node::List(roots))
}
fn as_list<'a>(n: &'a Node, name: &str) -> Option<&'a [Node]> {
    match n {
        Node::List(xs) if xs.first() == Some(&Node::Atom(name.into())) => Some(xs),
        _ => None,
    }
}
fn field(n: &Node, name: &str) -> Option<String> {
    as_list(n, name)
        .and_then(|x| x.get(1))
        .and_then(|v| match v {
            Node::Atom(a) => Some(a.clone()),
            _ => None,
        })
}
fn child_field(n: &Node, name: &str) -> Option<String> {
    children(n, name).first().and_then(|v| field(v, name))
}
fn children<'a>(n: &'a Node, name: &str) -> Vec<&'a Node> {
    match n {
        Node::List(xs) => xs.iter().filter(|x| as_list(x, name).is_some()).collect(),
        _ => Vec::new(),
    }
}
fn finding(id: &str, message: impl Into<String>) -> Value {
    json!({"id":id,"message":message.into()})
}
fn digest(path: &str) -> Result<String> {
    let mut h = Sha256::new();
    h.update(fs::read(path).with_context(|| format!("read {path}"))?);
    Ok(format!("{:x}", h.finalize()))
}
type CompiledParts = HashMap<String, (String, String, String)>;
type CompiledPins = HashMap<(String, String), String>;
fn netlist(text: &str) -> Result<(CompiledParts, CompiledPins)> {
    let root = match parse_sexp(text)? {
        Node::List(roots) => roots.into_iter().find(|n| as_list(n, "export").is_some()),
        _ => None,
    }
    .context("netlist has no export")?;
    let comps = children(&root, "components");
    ensure!(comps.len() == 1, "components block missing or duplicated");
    let mut parts = HashMap::new();
    for c in children(comps[0], "comp") {
        let r = child_field(c, "ref").context("component ref missing")?;
        ensure!(!parts.contains_key(&r), "duplicate component {r}");
        let source = children(c, "sheetpath")
            .first()
            .and_then(|x| child_field(x, "names"))
            .unwrap_or_default();
        let mpn = children(c, "libsource")
            .first()
            .and_then(|x| child_field(x, "part"))
            .unwrap_or_default();
        let value = child_field(c, "value").unwrap_or_default();
        parts.insert(r, (mpn, value, source));
    }
    let nets = children(&root, "nets");
    ensure!(nets.len() == 1, "nets block missing or duplicated");
    let mut pins = HashMap::new();
    for n in children(nets[0], "net") {
        let name = child_field(n, "name").context("net name missing")?;
        for p in children(n, "node") {
            let r = child_field(p, "ref").context("net node ref missing")?;
            let pin = child_field(p, "pin").context("net node pin missing")?;
            ensure!(
                pins.insert((r.clone(), pin.clone()), name.clone())
                    .is_none(),
                "duplicate pin membership {r}.{pin}"
            );
        }
    }
    ensure!(
        !parts.is_empty() && !pins.is_empty(),
        "compiled netlist is empty"
    );
    Ok((parts, pins))
}
fn csv(text: &str) -> Result<HashMap<String, String>> {
    let mut lines = text.lines();
    let header = lines.next().context("BOM header missing")?;
    let headers: Vec<_> = header.split(',').map(str::trim).collect();
    let mpn_i = headers
        .iter()
        .position(|h| *h == "Comment")
        .context("BOM Comment column missing")?;
    let ref_i = headers
        .iter()
        .position(|h| *h == "Designator")
        .context("BOM Designator column missing")?;
    let mut result = HashMap::new();
    for (line_no, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let mut cols = Vec::new();
        let mut cur = String::new();
        let mut quoted = false;
        for c in line.chars() {
            if c == '"' {
                quoted = !quoted;
            } else if c == ',' && !quoted {
                cols.push(cur.clone());
                cur.clear();
            } else {
                cur.push(c);
            }
        }
        cols.push(cur);
        ensure!(
            cols.len() > mpn_i && cols.len() > ref_i,
            "malformed BOM row {}",
            line_no + 2
        );
        let mpn = cols[mpn_i].trim().to_string();
        for r in cols[ref_i]
            .split(',')
            .map(str::trim)
            .filter(|r| !r.is_empty())
        {
            ensure!(
                result.insert(r.to_string(), mpn.clone()).is_none(),
                "duplicate BOM designator {r}"
            );
        }
    }
    Ok(result)
}

/// Reconcile native exports against the frozen fixture contract.
pub fn evaluate(input: Value) -> Result<Value> {
    ensure!(
        input["profile"] == "engineering-circuit",
        "wrong circuit profile"
    );
    if input["atopile"]["build"]["status"] != "pass" {
        return Ok(
            json!({"stage":"circuit","status":"blocked","findings":[finding("build_unavailable","Atopile did not produce both compiled artifacts")]}),
        );
    }
    let mut findings = Vec::new();
    let c: Value = serde_json::from_str(include_str!("../engineering/circuit-contract.json"))?;
    let expected = c["components"].as_object().context("contract components")?;
    let artifacts = &input["atopile"]["build"]["artifacts"];
    let np = artifacts["default.net"]
        .as_str()
        .context("netlist missing")?;
    let bp = artifacts["default.csv"].as_str().context("BOM missing")?;
    let (parts, pins) = netlist(&fs::read_to_string(np)?)?;
    let bom = csv(&fs::read_to_string(bp)?)?;
    let export = &input["resolved_export"];
    for (name, path) in [("default.net", np), ("default.csv", bp)] {
        let actual = digest(path)?;
        if input["atopile"]["build"]["artifact_hashes"][name] != actual
            || export["build_sha256"][format!("build/{name}")] != actual
        {
            findings.push(finding(
                "artifact_hash_mismatch",
                format!("{name} differs from compiled export identity"),
            ));
        }
    }
    if input["source_unchanged"] != true {
        findings.push(finding(
            "source_changed",
            "source changed during collection",
        ));
    }
    let source = input["source"]
        .as_object()
        .context("source inventory missing")?;
    for (name, hash) in source {
        if name.ends_with("ato.yaml") {
            continue;
        }
        let key = if name.ends_with("engineering/buck.ato") {
            "buck.ato"
        } else {
            name.as_str()
        };
        if export["source_sha256"][key] != *hash {
            findings.push(finding("source_hash_mismatch", name));
        }
    }
    let entries = export["components"]
        .as_array()
        .context("resolved components missing")?;
    if parts.len() != expected.len()
        || entries.len() != expected.len()
        || bom.len() != expected.len()
    {
        findings.push(finding(
            "component_census_mismatch",
            "all nine and only nine functional components are required",
        ));
    }
    let mut groups: HashMap<String, HashSet<String>> = HashMap::new();
    let fps = input["candidate"]["footprints"]
        .as_array()
        .context("native candidate missing")?;
    for (name, spec) in expected {
        let suffix = format!(":BuckCircuitCandidate::buck.{name}");
        let matches: Vec<_> = parts
            .iter()
            .filter(|(_, (_, _, path))| path.ends_with(&suffix))
            .collect();
        let native: Vec<_> = entries
            .iter()
            .filter(|e| e["address"].as_str().is_some_and(|p| p.ends_with(&suffix)))
            .collect();
        if matches.len() != 1 || native.len() != 1 {
            findings.push(finding("module_identity", name));
            continue;
        }
        let (reference, (_, _, _)) = matches[0];
        let attrs = &native[0]["attributes"];
        if bom.get(reference).map(String::as_str) != spec["mpn"].as_str()
            || attrs["mpn"] != spec["mpn"]
        {
            findings.push(finding("bom_identity_mismatch", name));
        }
        if name != "buck" && attrs["value"] != spec["value"] {
            findings.push(finding(
                "resolved_value_mismatch",
                format!("{name}: {} differs from {}", attrs["value"], spec["value"]),
            ));
        }
        for (key, minimum) in spec["rating"].as_object().context("rating contract")? {
            let (attr, unit) = match key.as_str() {
                "voltage_v" => ("voltage_rating", "V"),
                "current_a" => ("current_rating", "A"),
                "i_out_max_a" => ("i_out_max", "A"),
                "v_in_max_v" => ("v_in_max", "V"),
                "tolerance_percent" => continue,
                _ => anyhow::bail!("unknown rating"),
            };
            let actual = attrs[attr]
                .as_str()
                .and_then(|s| s.strip_suffix(unit))
                .and_then(|s| s.parse::<f64>().ok());
            if !actual
                .is_some_and(|v| v.is_finite() && v >= minimum.as_f64().unwrap_or(f64::INFINITY))
            {
                findings.push(finding("rating_insufficient", format!("{name}.{attr}")));
            }
        }
        let candidate: Vec<_> = fps
            .iter()
            .filter(|f| f["reference"] == spec["pcb_reference"])
            .collect();
        if candidate.len() != 1 {
            findings.push(finding("candidate_census_mismatch", name));
            continue;
        }
        let pads = candidate[0]["pads"]
            .as_array()
            .context("candidate pads missing")?;
        let pin_spec = spec["pins"].as_object().context("pin contract")?;
        if pads.len() != pin_spec.len() {
            findings.push(finding("candidate_pad_census_mismatch", name));
        }
        for (pin, net) in pin_spec {
            groups
                .entry(net.as_str().context("netname")?.into())
                .or_default()
                .insert(format!("{reference}.{pin}"));
            let matches: Vec<_> = pads
                .iter()
                .filter(|p| p["number"].as_str() == Some(pin))
                .collect();
            if matches.len() != 1 || matches[0]["net"] != *net {
                findings.push(finding("candidate_net_mismatch", format!("{name}.{pin}")));
            }
        }
    }
    let mut actual: HashMap<String, HashSet<String>> = HashMap::new();
    for ((r, p), net) in pins {
        actual.entry(net).or_default().insert(format!("{r}.{p}"));
    }
    let partition = |groups: HashMap<String, HashSet<String>>| -> HashSet<Vec<String>> {
        groups
            .into_values()
            .map(|g| {
                let mut v: Vec<_> = g.into_iter().collect();
                v.sort();
                v
            })
            .collect()
    };
    if partition(actual) != partition(groups) {
        findings.push(finding(
            "net_partition_mismatch",
            "compiled pin groups differ from circuit contract",
        ));
    }
    let integrity = if findings.is_empty() { "pass" } else { "fail" };
    let q = &input["component_qualification"];
    let qualified = crate::qualification::approved("component", q)
        && q["verified_artifact"] == true
        && q["reviewed_by"].as_str().is_some_and(|s| !s.is_empty())
        && q["source"].as_str().is_some_and(|s| !s.is_empty())
        && q["source_sha256"] == input["circuit_source_sha256"];
    let mut qualification_valid = qualified;
    for name in ["c_in", "c_boot", "c_out1", "c_out2", "c_out_hf"] {
        let item = &q["capacitors"][name];
        let effective = item["effective_min_uf"].as_f64();
        let required = item["required_min_uf"].as_f64();
        if !effective
            .zip(required)
            .is_some_and(|(a, b)| a.is_finite() && b > 0.0 && a >= b)
        {
            qualification_valid = false;
        }
    }
    if !q["inductor_saturation_a"]
        .as_f64()
        .zip(q["required_peak_a"].as_f64())
        .is_some_and(|(a, b)| a.is_finite() && b > 0.0 && a >= b)
    {
        qualification_valid = false;
    }
    if !qualification_valid {
        findings.push(finding(
            "component_qualification_missing",
            "reviewed capacitor DC-bias derating and inductor saturation evidence is required",
        ));
    }
    Ok(
        json!({"stage":"circuit","status":if integrity=="fail"{"fail"}else if qualification_valid{"pass"}else{"blocked"},"integrity":{"status":integrity},"findings":findings,"component_count":parts.len(),"hardware_validated":false}),
    )
}
