use crate::error::{DesignBundleError, diagnostic};
use crate::model::{Component, Constraint, ConstraintOrigin, Net, NetClass, SafetyDomain, Stackup};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use temper_pcl_ir::{ConstraintTier, PclConstraintKind};

/// Compiler version this strict bridge accepts. A different Atopile may
/// change attribute shapes or assertion semantics; accepting it silently
/// would launder an unqualified input into a candidate board.
pub const PINNED_ATOPILE_VERSION: &str = "0.2.69";
/// Schema tag of the resolved-export document produced by
/// `harness-lab/circuit_export.py`.
pub const CIRCUIT_EXPORT_SCHEMA: &str = "temper.circuit-export.v1";

/// Parsed atopile export — the primary input format for bundle assembly.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtopileExport {
    pub schema_version: u32,
    pub board: crate::model::BoardSpec,
    pub components: Vec<Component>,
    pub nets: Vec<Net>,
    #[serde(default)]
    pub net_classes: Vec<NetClass>,
    #[serde(default)]
    pub safety_domains: Vec<SafetyDomain>,
    #[serde(default)]
    pub stackup: Option<Stackup>,
    #[serde(default)]
    pub zones: Vec<String>,
    #[serde(default)]
    pub loops: Vec<String>,
    #[serde(default)]
    pub safety: Vec<SafetyRule>,
}
/// A single net in the atopile export.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtopileNet {
    pub signal: String,
    pub canonical_name: String,
}
/// A single component in the atopile export.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtopileComponent {
    pub id: String,
}
/// A safety constraint rule from the atopile export (creepage, clearance).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyRule {
    pub id: String,
    pub subject: String,
    pub metric: String,
    pub value_mm: f64,
    #[serde(default)]
    pub because: Option<String>,
}
/// A single mapping entry: atopile signal name → KiCad net name.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MappingEntry {
    pub atopile_signal: String,
    pub kicad_net: String,
    #[serde(default)]
    pub aliases: Vec<String>,
}
/// The full net mapping: atopile signals → KiCad nets.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetMapping {
    pub schema_version: u32,
    pub entries: Vec<MappingEntry>,
}
impl AtopileExport {
    pub fn derived_constraints(&self) -> Vec<Constraint> {
        self.safety
            .iter()
            .map(|r| Constraint {
                schema_version: 1,
                id: r.id.clone(),
                tier: ConstraintTier::Hard,
                because: r.because.clone(),
                origin: ConstraintOrigin::AtopileDerived,
                references: vec![r.subject.clone()],
                kind: PclConstraintKind::Separated {
                    a: r.subject.clone(),
                    b: r.subject.clone(),
                    min_distance_mm: r.value_mm,
                    metric: r.metric.clone(),
                },
            })
            .collect()
    }
}

// ---------------------------------------------------------------------------
// Strict resolved-export-to-bundle bridge (P1 U2, MCU candidate profile).
//
// `temper.circuit-export.v1` (resolved attributes per instance) and
// `DesignBundle` are distinct schemas: this conversion is explicit, preserves
// each field's origin, and fails closed on missing required fields,
// conflicting joins, or unmatched instances. It never fabricates source
// floors (no default MPNs, values, or footprints) to satisfy validation.
// Candidate bundles keep a non-production role; production-identity guards
// in `identity.rs` are untouched by this path.
// ---------------------------------------------------------------------------

/// One resolved component from a `temper.circuit-export.v1` document.
/// `address` is the full Atopile instance address
/// (`<abs path>:<Entry>::<instance.path>`); `attributes` is the verbatim
/// resolved data dict (MPNs/values/footprints live here, never in the
/// netlist's aliased `libsource`/`value` fields).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitResolvedComponent {
    pub address: String,
    pub attributes: HashMap<String, serde_json::Value>,
}

/// The resolved-export document envelope consumed by this bridge.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitExportV1 {
    pub schema: String,
    pub atopile_version: String,
    pub entry: String,
    pub components: Vec<CircuitResolvedComponent>,
    #[serde(default)]
    pub source_sha256: HashMap<String, String>,
    #[serde(default)]
    pub build_sha256: HashMap<String, String>,
}

/// One compiled-netlist component: the path-to-refdes projection. The
/// netlist is canonical for `(reference, instance_path, footprint-nickname)`
/// only; part identity comes from resolved attributes corroborated by CSV.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeNetlistComponent {
    pub reference: String,
    pub instance_path: String,
    pub footprint: String,
    pub tstamp: String,
}

/// One compiled net: canonical connectivity partition source.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeNetlistNet {
    pub name: String,
    pub nodes: Vec<(String, String)>,
}

/// The compiled-netlist side of the bridge input.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeNetlist {
    pub components: Vec<BridgeNetlistComponent>,
    pub nets: Vec<BridgeNetlistNet>,
}

/// One converted component: exact part identity with per-field origins.
/// `origins` maps field name (`footprint`/`mpn`/`value`/`reference`) to the
/// input that supplied it (`resolved-attr`, `csv`, `netlist`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConvertedComponent {
    pub instance_path: String,
    pub reference: String,
    pub footprint: String,
    pub mpn: String,
    pub value: Option<String>,
    pub origins: HashMap<String, String>,
}

/// Bridge output: bundle-shaped components plus the canonical net
/// partitions. `empty_reference_nets` (unconnected interface members such as
/// `mcu-reference*`) are reported so the admission check can prove they never
/// become copper.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConvertedCandidate {
    pub entry: String,
    pub components: Vec<ConvertedComponent>,
    pub nets: Vec<BridgeNetlistNet>,
    pub empty_reference_nets: Vec<String>,
}

/// Render a resolved `value` attribute as display text. Plain strings pass
/// through; `{magnitude, units}` quantities render numerically; anything else
/// is `None` (absent, e.g. buttons) rather than a fabricated string.
fn display_value(value: Option<&serde_json::Value>) -> Option<String> {
    match value {
        None => None,
        Some(serde_json::Value::String(s)) => Some(s.clone()),
        Some(serde_json::Value::Object(map)) => {
            let magnitude = map.get("magnitude")?.as_f64()?;
            let units = map.get("units")?.as_str()?;
            Some(format!("{magnitude} {units}"))
        }
        Some(other) => Some(other.to_string()),
    }
}

fn attr_string(
    attrs: &HashMap<String, serde_json::Value>,
    key: &str,
    instance_path: &str,
) -> Result<String, DesignBundleError> {
    match attrs.get(key) {
        Some(serde_json::Value::String(s)) if !s.is_empty() => Ok(s.clone()),
        _ => Err(diagnostic(
            "missing_field",
            format!("resolved instance '{instance_path}' has no usable '{key}' attribute"),
            vec![instance_path.to_string(), key.to_string()],
        )),
    }
}

/// Explicit resolved-export-to-bundle conversion. `bom_mpn` is the CSV BOM
/// projection (`reference -> Comment/MPN`); it corroborates, never overrides:
/// a CSV/resolved conflict fails rather than picking a winner.
pub fn convert_circuit_export(
    export_json: &str,
    netlist_json: &str,
    bom_json: &str,
    expected_entry: &str,
) -> Result<ConvertedCandidate, DesignBundleError> {
    let export: CircuitExportV1 = serde_json::from_str(export_json)
        .map_err(|e| DesignBundleError::Document(format!("circuit export: {e}")))?;
    let netlist: BridgeNetlist = serde_json::from_str(netlist_json)
        .map_err(|e| DesignBundleError::Document(format!("bridge netlist: {e}")))?;
    let bom_mpn: HashMap<String, String> = serde_json::from_str(bom_json)
        .map_err(|e| DesignBundleError::Document(format!("BOM map: {e}")))?;

    if export.schema != CIRCUIT_EXPORT_SCHEMA {
        return Err(diagnostic(
            "unknown_schema",
            format!(
                "circuit export schema '{}' is not '{CIRCUIT_EXPORT_SCHEMA}'",
                export.schema
            ),
            vec![export.schema.clone()],
        ));
    }
    if export.atopile_version != PINNED_ATOPILE_VERSION {
        return Err(diagnostic(
            "tool_mismatch",
            format!(
                "circuit export built with Atopile {} (pinned {PINNED_ATOPILE_VERSION})",
                export.atopile_version
            ),
            vec![export.atopile_version.clone()],
        ));
    }
    let entry_module = export.entry.rsplit(':').next().unwrap_or("");
    if entry_module != expected_entry {
        return Err(diagnostic(
            "entry_mismatch",
            format!("circuit export entry '{entry_module}' is not the expected '{expected_entry}'"),
            vec![export.entry.clone()],
        ));
    }
    // Join key: the instance path trailing `<Entry>::` in the resolved
    // address must equal the netlist sheetpath trailing `<Entry>::`.
    let tail = format!("{expected_entry}::");
    let mut resolved_by_path: HashMap<&str, &CircuitResolvedComponent> = HashMap::new();
    for component in &export.components {
        let path = component.address.rsplit(&tail).next().unwrap_or("");
        if path.is_empty() || path == component.address {
            return Err(diagnostic(
                "unmatched_instance",
                format!(
                    "resolved address '{}' does not carry the '{expected_entry}::' entry tail",
                    component.address
                ),
                vec![component.address.clone()],
            ));
        }
        if resolved_by_path.contains_key(path) {
            return Err(diagnostic(
                "ambiguous_instance",
                format!("resolved export carries '{path}' twice; identity is ambiguous"),
                vec![path.to_string()],
            ));
        }
        resolved_by_path.insert(path, component);
    }

    let mut seen_refs: HashSet<&str> = HashSet::new();
    let mut seen_paths: HashSet<&str> = HashSet::new();
    let mut converted: Vec<ConvertedComponent> = Vec::new();
    for component in &netlist.components {
        if !seen_refs.insert(component.reference.as_str()) {
            return Err(diagnostic(
                "duplicate_component",
                format!("duplicate reference '{}'", component.reference),
                vec![component.reference.clone()],
            ));
        }
        if !seen_paths.insert(component.instance_path.as_str()) {
            return Err(diagnostic(
                "duplicate_instance",
                format!("duplicate instance path '{}'", component.instance_path),
                vec![component.instance_path.clone()],
            ));
        }
        let resolved = resolved_by_path
            .get(component.instance_path.as_str())
            .ok_or_else(|| {
                diagnostic(
                    "unmatched_instance",
                    format!(
                        "netlist instance '{}' ({}) has no resolved export entry",
                        component.instance_path, component.reference
                    ),
                    vec![component.instance_path.clone(), component.reference.clone()],
                )
            })?;
        let footprint = attr_string(&resolved.attributes, "footprint", &component.instance_path)?;
        let mpn = attr_string(&resolved.attributes, "mpn", &component.instance_path)?;
        match bom_mpn.get(&component.reference) {
            None => {
                return Err(diagnostic(
                    "bom_gap",
                    format!(
                        "reference '{}' has no CSV BOM entry; part identity is unknown",
                        component.reference
                    ),
                    vec![component.reference.clone()],
                ));
            }
            Some(csv_mpn) if csv_mpn != &mpn => {
                return Err(diagnostic(
                    "bom_conflict",
                    format!(
                        "reference '{}': resolved MPN '{mpn}' != CSV MPN '{csv_mpn}'",
                        component.reference
                    ),
                    vec![component.reference.clone()],
                ));
            }
            _ => {}
        }
        let mut origins = HashMap::new();
        origins.insert("footprint".to_string(), "resolved-attr".to_string());
        origins.insert("mpn".to_string(), "resolved-attr+csv".to_string());
        origins.insert("reference".to_string(), "netlist".to_string());
        let value = display_value(resolved.attributes.get("value"));
        if value.is_some() {
            origins.insert("value".to_string(), "resolved-attr".to_string());
        }
        converted.push(ConvertedComponent {
            instance_path: component.instance_path.clone(),
            reference: component.reference.clone(),
            footprint,
            mpn,
            value,
            origins,
        });
    }
    // Both-directions strictness, mirroring `apply_bom_values`: a CSV row
    // absent from the netlist means the two are out of sync.
    let mut extra: Vec<&String> = bom_mpn
        .keys()
        .filter(|reference| !seen_refs.contains(reference.as_str()))
        .collect();
    extra.sort();
    if !extra.is_empty() {
        return Err(diagnostic(
            "bom_extra",
            format!(
                "CSV BOM designators absent from the compiled netlist: {}",
                extra
                    .iter()
                    .map(|s| s.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            extra.iter().map(|s| (*s).clone()).collect(),
        ));
    }
    // A resolved instance with no netlist counterpart is an unmatched
    // component, never silent spare copper.
    let mut orphan: Vec<String> = resolved_by_path
        .keys()
        .filter(|path| !seen_paths.contains(**path))
        .map(|path| (*path).to_string())
        .collect();
    orphan.sort();
    if !orphan.is_empty() {
        return Err(diagnostic(
            "extra_component",
            format!(
                "resolved instances absent from the compiled netlist: {}",
                orphan.join(", ")
            ),
            orphan,
        ));
    }

    converted.sort_by(|a, b| a.reference.cmp(&b.reference));
    let mut empty_reference_nets: Vec<String> = netlist
        .nets
        .iter()
        .filter(|net| net.nodes.is_empty())
        .map(|net| net.name.clone())
        .collect();
    empty_reference_nets.sort();
    Ok(ConvertedCandidate {
        entry: export.entry.clone(),
        components: converted,
        nets: netlist.nets.clone(),
        empty_reference_nets,
    })
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod bridge_tests {
    use super::*;

    fn export_doc(version: &str, entry: &str, addresses: &[&str]) -> String {
        let components: Vec<serde_json::Value> = addresses
            .iter()
            .map(|address| {
                serde_json::json!({
                    "address": address,
                    "attributes": {
                        "mpn": "TEST-MPN",
                        "footprint": "Test:Foo",
                        "value": "10kohm",
                    },
                })
            })
            .collect();
        serde_json::json!({
            "schema": CIRCUIT_EXPORT_SCHEMA,
            "atopile_version": version,
            "entry": entry,
            "components": components,
        })
        .to_string()
    }

    fn netlist_doc(refs: &[(&str, &str)]) -> String {
        let components: Vec<serde_json::Value> = refs
            .iter()
            .map(|(reference, path)| {
                serde_json::json!({
                    "reference": reference,
                    "instance_path": path,
                    "footprint": "Test:Foo",
                    "tstamp": "t",
                })
            })
            .collect();
        serde_json::json!({
            "components": components,
            "nets": [{"name": "vcc", "nodes": [["U1", "2"]]}],
        })
        .to_string()
    }

    fn code(err: &DesignBundleError) -> String {
        match err {
            DesignBundleError::Validation(diags) => diags[0].code.clone(),
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    #[cfg_attr(test, test)]
    fn clean_join_preserves_origins() {
        let export = export_doc(
            PINNED_ATOPILE_VERSION,
            "/w/mcu.ato:McuCandidate",
            &["/w/mcu.ato:McuCandidate::mcu.mcu"],
        );
        let netlist = netlist_doc(&[("U1", "mcu.mcu")]);
        let out = convert_circuit_export(&export, &netlist, r#"{"U1":"TEST-MPN"}"#, "McuCandidate")
            .expect("clean join passes");
        assert_eq!(out.components.len(), 1);
        assert_eq!(out.components[0].origins["mpn"], "resolved-attr+csv");
        assert_eq!(out.components[0].origins["reference"], "netlist");
    }

    #[cfg_attr(test, test)]
    fn wrong_tool_version_fails_closed() {
        let export = export_doc(
            "0.2.70",
            "/w/mcu.ato:McuCandidate",
            &["/w/mcu.ato:McuCandidate::mcu.mcu"],
        );
        let netlist = netlist_doc(&[("U1", "mcu.mcu")]);
        let err = convert_circuit_export(&export, &netlist, r#"{"U1":"TEST-MPN"}"#, "McuCandidate")
            .unwrap_err();
        assert_eq!(code(&err), "tool_mismatch");
    }

    #[cfg_attr(test, test)]
    fn csv_conflict_fails_rather_than_picking_a_winner() {
        let export = export_doc(
            PINNED_ATOPILE_VERSION,
            "/w/mcu.ato:McuCandidate",
            &["/w/mcu.ato:McuCandidate::mcu.mcu"],
        );
        let netlist = netlist_doc(&[("U1", "mcu.mcu")]);
        let err =
            convert_circuit_export(&export, &netlist, r#"{"U1":"OTHER-MPN"}"#, "McuCandidate")
                .unwrap_err();
        assert_eq!(code(&err), "bom_conflict");
    }

    #[cfg_attr(test, test)]
    fn unmatched_and_extra_instances_fail() {
        let export = export_doc(
            PINNED_ATOPILE_VERSION,
            "/w/mcu.ato:McuCandidate",
            &["/w/mcu.ato:McuCandidate::mcu.mcu"],
        );
        let netlist = netlist_doc(&[("U1", "mcu.missing")]);
        let err = convert_circuit_export(&export, &netlist, r#"{"U1":"TEST-MPN"}"#, "McuCandidate")
            .unwrap_err();
        assert_eq!(code(&err), "unmatched_instance");

        let netlist = netlist_doc(&[("U1", "mcu.mcu")]);
        let err = convert_circuit_export(
            &export,
            &netlist,
            r#"{"U1":"TEST-MPN","U9":"TEST-MPN"}"#,
            "McuCandidate",
        )
        .unwrap_err();
        assert_eq!(code(&err), "bom_extra");
    }

    #[cfg_attr(test, test)]
    fn empty_nets_are_reported_not_admitted() {
        let export = export_doc(
            PINNED_ATOPILE_VERSION,
            "/w/mcu.ato:McuCandidate",
            &["/w/mcu.ato:McuCandidate::mcu.mcu"],
        );
        let netlist = serde_json::json!({
            "components": [{"reference": "U1", "instance_path": "mcu.mcu",
                            "footprint": "Test:Foo", "tstamp": "t"}],
            "nets": [{"name": "vcc", "nodes": [["U1", "2"]]},
                     {"name": "mcu-reference", "nodes": []}],
        })
        .to_string();
        let out = convert_circuit_export(&export, &netlist, r#"{"U1":"TEST-MPN"}"#, "McuCandidate")
            .expect("passes with empties reported");
        assert_eq!(out.empty_reference_nets, vec!["mcu-reference".to_string()]);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: bridge_tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("atopile::bridge_tests::clean_join_preserves_origins", clean_join_preserves_origins),
        ("atopile::bridge_tests::wrong_tool_version_fails_closed", wrong_tool_version_fails_closed),
        ("atopile::bridge_tests::csv_conflict_fails_rather_than_picking_a_winner", csv_conflict_fails_rather_than_picking_a_winner),
        ("atopile::bridge_tests::unmatched_and_extra_instances_fail", unmatched_and_extra_instances_fail),
        ("atopile::bridge_tests::empty_nets_are_reported_not_admitted", empty_nets_are_reported_not_admitted),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: bridge_tests ---
}
