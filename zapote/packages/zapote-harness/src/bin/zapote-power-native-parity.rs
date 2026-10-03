//! Source-to-saved-board pad parity for the standalone 120 V power stage.
//! The KiCad Python adapter supplies pad facts; this gate owns source mapping.
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::{env, fs, path::Path, process::ExitCode};

fn field<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value[key]
        .as_str()
        .with_context(|| format!("missing string field {key}"))
}

fn array<'a>(value: &'a Value, key: &str) -> Result<&'a [Value]> {
    value[key]
        .as_array()
        .map(Vec::as_slice)
        .with_context(|| format!("missing array field {key}"))
}

fn sha256(path: &Path) -> Result<String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(fs::read(path).with_context(|| format!("read {}", path.display()))?)
    ))
}

fn check_source_hashes(manifest: &Value, hashes: &[(&str, String); 3]) -> Result<()> {
    for (name, actual) in hashes {
        ensure!(
            field(&manifest["input_hashes"], name)? == actual,
            "frozen {name} hash differs from source manifest"
        );
    }
    Ok(())
}

#[derive(Debug, PartialEq)]
struct Census {
    components: usize,
    source_pins: usize,
    copper_pads: usize,
    duplicate_copper_pads: usize,
}

fn check(manifest: &Value, native: &Value) -> Result<Census> {
    ensure!(
        field(manifest, "schema")? == "zapote.power-stage-120v.native-source-manifest.v1",
        "unsupported source manifest schema"
    );
    ensure!(
        field(native, "schema")? == "zapote.power-stage-120v.native-pad-extract.v1",
        "unsupported native pad extract schema"
    );

    // The bridge uses reference and source pin; strict_pin_map supplies the
    // corresponding footprint pad. Reject duplicate claims on either side.
    let mut net_by_source_pin = BTreeMap::<(String, String), String>::new();
    let mut names = BTreeSet::new();
    for net in array(&manifest["bridge"], "nets")? {
        let name = field(net, "name")?;
        ensure!(
            !name.is_empty() && names.insert(name),
            "duplicate or empty bridge net {name}"
        );
        for node in array(net, "nodes")? {
            let pair = node.as_array().context("bridge node must be a pair")?;
            ensure!(pair.len() == 2, "bridge node must be a pair");
            let reference = pair[0].as_str().context("bridge node reference missing")?;
            let pin = pair[1].as_str().context("bridge node pin missing")?;
            ensure!(
                !reference.is_empty() && !pin.is_empty(),
                "empty bridge node"
            );
            ensure!(
                net_by_source_pin
                    .insert((reference.into(), pin.into()), name.into())
                    .is_none(),
                "source pin {reference}.{pin} belongs to multiple nets"
            );
        }
    }

    let mut expected_components = BTreeMap::<String, (String, String, String)>::new();
    let mut instances = BTreeSet::new();
    for component in array(manifest, "components")? {
        let reference = field(component, "reference")?;
        let instance = field(component, "instance_path")?;
        let mpn = field(component, "mpn")?;
        let footprint = field(component, "footprint")?;
        ensure!(
            !reference.is_empty()
                && !instance.is_empty()
                && !mpn.is_empty()
                && !footprint.is_empty(),
            "incomplete source component {reference}"
        );
        ensure!(
            instances.insert(instance),
            "duplicate source instance {instance}"
        );
        let attr = &manifest["source_attributes"][instance];
        ensure!(
            field(attr, "mpn")? == mpn && field(attr, "footprint")? == footprint,
            "source attributes differ from component {reference}"
        );
        ensure!(
            expected_components
                .insert(
                    reference.into(),
                    (instance.into(), mpn.into(), footprint.into())
                )
                .is_none(),
            "duplicate source reference {reference}"
        );
    }
    ensure!(
        manifest["source_attributes"]
            .as_object()
            .context("source_attributes missing")?
            .len()
            == expected_components.len(),
        "source attribute census differs from components"
    );

    let mut expected_pad_nets = BTreeMap::<(String, String), String>::new();
    let mut mapped_source_pins = BTreeSet::new();
    for entry in array(manifest, "strict_pin_map")? {
        let reference = field(entry, "reference")?;
        let instance = field(entry, "instance_path")?;
        let pin = field(entry, "pin")?;
        let pad = field(entry, "pad")?;
        ensure!(!pad.is_empty(), "empty source pad on {reference}.{pin}");
        let expected = expected_components
            .get(reference)
            .with_context(|| format!("pin map has unknown component {reference}"))?;
        ensure!(
            expected.0 == instance,
            "pin map source instance mismatch at {reference}.{pin}"
        );
        let source_key = (reference.into(), pin.into());
        ensure!(
            mapped_source_pins.insert(source_key.clone()),
            "duplicate strict mapping for {reference}.{pin}"
        );
        let net = net_by_source_pin
            .get(&source_key)
            .with_context(|| format!("{reference}.{pin} lacks bridge net"))?;
        ensure!(
            expected_pad_nets
                .insert((reference.into(), pad.into()), net.clone())
                .is_none(),
            "multiple source pins claim {reference}.{pad}"
        );
    }
    ensure!(
        mapped_source_pins.len() == net_by_source_pin.len(),
        "bridge node census differs from strict pin map"
    );

    let mut allowed_unconnected = BTreeSet::new();
    for pair in array(manifest, "unconnected_pads")? {
        let parts = pair
            .as_array()
            .context("unconnected_pads entry must be [reference,pad]")?;
        ensure!(
            parts.len() == 2,
            "unconnected_pads entry must be [reference,pad]"
        );
        let reference = parts[0].as_str().context("unconnected reference missing")?;
        let pad = parts[1].as_str().context("unconnected pad missing")?;
        ensure!(
            expected_components.contains_key(reference),
            "unconnected pad has unknown component {reference}"
        );
        ensure!(!pad.is_empty(), "unconnected pad number missing");
        ensure!(
            allowed_unconnected.insert((reference.to_owned(), pad.to_owned())),
            "duplicate unconnected pad {reference}.{pad}"
        );
    }

    let mut observed_components = BTreeSet::new();
    let mut observed_pads = BTreeSet::new();
    let mut pad_uuids = BTreeSet::new();
    let mut copper_pads = 0;
    for component in array(native, "components")? {
        let reference = field(component, "reference")?;
        let instance = field(component, "instance_path")?;
        let mpn = field(component, "mpn")?;
        let footprint = field(component, "footprint")?;
        let value = field(component, "value")?;
        ensure!(
            observed_components.insert(reference),
            "duplicate native reference {reference}"
        );
        let expected = expected_components
            .get(reference)
            .with_context(|| format!("unexpected native component {reference}"))?;
        ensure!(
            expected.0 == instance,
            "{reference} SourceInstance differs: {instance}"
        );
        ensure!(
            expected.1 == mpn && expected.1 == value,
            "{reference} MPN or Value differs from source"
        );
        ensure!(
            expected.2 == footprint,
            "{reference} footprint differs from source: {footprint}"
        );
        for pad in array(component, "pads")? {
            let number = field(pad, "number")?;
            let net = field(pad, "net")?;
            let uuid = field(pad, "uuid")?;
            ensure!(
                !number.is_empty() && !uuid.is_empty(),
                "numberless or UUID-less copper pad on {reference}"
            );
            ensure!(
                pad_uuids.insert(uuid),
                "duplicate native copper pad UUID {uuid}"
            );
            let key = (reference.to_owned(), number.to_owned());
            if let Some(expected_net) = expected_pad_nets.get(&key) {
                ensure!(
                    net == expected_net,
                    "{reference}.{number}: native net {net:?}, source net {expected_net:?}"
                );
            } else {
                ensure!(
                    allowed_unconnected.contains(&key) && net.is_empty(),
                    "unexpected copper pad {reference}.{number} net {net:?}"
                );
            }
            observed_pads.insert(key);
            copper_pads += 1;
        }
    }
    ensure!(
        observed_components.len() == expected_components.len(),
        "missing native components: {:?}",
        expected_components
            .keys()
            .filter(|r| !observed_components.contains(r.as_str()))
            .collect::<Vec<_>>()
    );
    for key in expected_pad_nets.keys().chain(allowed_unconnected.iter()) {
        ensure!(
            observed_pads.contains(key),
            "missing physical copper pad {}.{}",
            key.0,
            key.1
        );
    }
    Ok(Census {
        components: observed_components.len(),
        source_pins: mapped_source_pins.len(),
        copper_pads,
        duplicate_copper_pads: copper_pads - observed_pads.len(),
    })
}

fn run() -> Result<()> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    ensure!(
        args.len() == 6,
        "usage: zapote-power-native-parity <source-manifest.json> <board.kicad_pcb> <frozen/default.net> <frozen/default.csv> <frozen/resolved-components.json> <pcbnew-extract.json>"
    );
    let manifest_path = Path::new(&args[0]);
    let board_path = Path::new(&args[1]);
    let netlist_path = Path::new(&args[2]);
    let bom_path = Path::new(&args[3]);
    let resolved_path = Path::new(&args[4]);
    let native_path = Path::new(&args[5]);
    let manifest: Value = serde_json::from_slice(&fs::read(manifest_path)?)?;
    let native: Value = serde_json::from_slice(&fs::read(native_path)?)?;
    let board_sha256 = sha256(board_path)?;
    let manifest_sha256 = sha256(manifest_path)?;
    let netlist_sha256 = sha256(netlist_path)?;
    let bom_sha256 = sha256(bom_path)?;
    let resolved_sha256 = sha256(resolved_path)?;
    ensure!(
        field(&native, "board_sha256")? == board_sha256,
        "pcbnew extract was made from different board bytes"
    );
    check_source_hashes(
        &manifest,
        &[
            ("default.net", netlist_sha256.clone()),
            ("default.csv", bom_sha256.clone()),
            ("resolved-components.json", resolved_sha256.clone()),
        ],
    )?;
    let census = check(&manifest, &native)?;
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "status": "PASS",
            "components": census.components,
            "source_pins": census.source_pins,
            "copper_pads": census.copper_pads,
            "duplicate_copper_pads": census.duplicate_copper_pads,
            "board_sha256": board_sha256,
            "manifest_sha256": manifest_sha256,
            "netlist_sha256": netlist_sha256,
            "bom_sha256": bom_sha256,
            "resolved_components_sha256": resolved_sha256,
        }))?
    );
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("FAIL: {error:#}");
            ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{check, check_source_hashes};
    use serde_json::json;

    fn manifest() -> serde_json::Value {
        json!({
            "schema":"zapote.power-stage-120v.native-source-manifest.v1",
            "components":[{"reference":"J1","instance_path":"jack","mpn":"P","footprint":"lib:fp"}],
            "source_attributes":{"jack":{"mpn":"P","footprint":"lib:fp"}},
            "bridge":{"nets":[{"name":"A","nodes":[["J1","1"]]},{"name":"B","nodes":[["J1","2"]]}]},
            "strict_pin_map":[
                {"reference":"J1","instance_path":"jack","pin":"1","pad":"1"},
                {"reference":"J1","instance_path":"jack","pin":"2","pad":"2"}
            ],
            "unconnected_pads":[]
        })
    }

    fn native() -> serde_json::Value {
        json!({
            "schema":"zapote.power-stage-120v.native-pad-extract.v1",
            "components":[{"reference":"J1","instance_path":"jack","mpn":"P","value":"P","footprint":"lib:fp","pads":[
                {"number":"1","net":"A","uuid":"one"},
                {"number":"1","net":"A","uuid":"one-more"},
                {"number":"2","net":"B","uuid":"two"}
            ]}]
        })
    }

    #[test]
    fn duplicate_physical_pads_have_distinct_uuids_and_same_source_net() {
        let census = check(&manifest(), &native()).unwrap();
        assert_eq!(census.source_pins, 2);
        assert_eq!(census.copper_pads, 3);
        assert_eq!(census.duplicate_copper_pads, 1);
    }

    #[test]
    fn net_swap_fails() {
        let mut board = native();
        board["components"][0]["pads"][0]["net"] = json!("B");
        assert!(check(&manifest(), &board)
            .unwrap_err()
            .to_string()
            .contains("native net"));
    }

    #[test]
    fn extra_netless_copper_pad_fails() {
        let mut board = native();
        board["components"][0]["pads"]
            .as_array_mut()
            .unwrap()
            .push(json!({"number":"3","net":"","uuid":"three"}));
        assert!(check(&manifest(), &board)
            .unwrap_err()
            .to_string()
            .contains("unexpected copper pad"));
    }

    #[test]
    fn missing_source_pin_and_wrong_mpn_fail() {
        let mut board = native();
        board["components"][0]["pads"].as_array_mut().unwrap().pop();
        assert!(check(&manifest(), &board)
            .unwrap_err()
            .to_string()
            .contains("missing physical copper pad"));
        board = native();
        board["components"][0]["mpn"] = json!("P-WRONG");
        assert!(check(&manifest(), &board)
            .unwrap_err()
            .to_string()
            .contains("MPN or Value"));
    }

    #[test]
    fn each_frozen_source_identity_is_required() {
        let mut source = manifest();
        source["input_hashes"] = json!({
            "default.net": "net", "default.csv": "bom", "resolved-components.json": "resolved"
        });
        let hashes = [
            ("default.net", "net".to_owned()),
            ("default.csv", "bom".to_owned()),
            ("resolved-components.json", "resolved".to_owned()),
        ];
        check_source_hashes(&source, &hashes).unwrap();
        for name in ["default.net", "default.csv", "resolved-components.json"] {
            source["input_hashes"][name] = json!("stale");
            assert!(check_source_hashes(&source, &hashes)
                .unwrap_err()
                .to_string()
                .contains(name));
            source["input_hashes"][name] =
                json!(hashes.iter().find(|(n, _)| *n == name).unwrap().1);
        }
    }
}
