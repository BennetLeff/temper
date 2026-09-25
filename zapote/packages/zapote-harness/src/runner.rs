//! Execute the adopted unit truth functions against current, hash-bound files.
//! Native reports are captured in this run, never accepted by basename alone.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use zapote_core::unit::{UnitInput, UnitNativeEvidence};
use zapote_core::{CheckReport, Finding, Status};

type Result<T> = std::result::Result<T, String>;

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum UnitKind {
    Rtd,
    CurrentSense,
    VoltageSense,
    ThermalSense,
    Interlock,
    GateDrive,
    PowerEntry,
}
impl UnitKind {
    pub fn name(self) -> &'static str {
        match self {
            Self::Rtd => "rtd",
            Self::CurrentSense => "current-sense",
            Self::VoltageSense => "voltage-sense",
            Self::ThermalSense => "thermal-sense",
            Self::Interlock => "interlock",
            Self::GateDrive => "gate-drive",
            Self::PowerEntry => "power-entry",
        }
    }
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct UnitRunSpec {
    pub unit: UnitKind,
    pub source: PathBuf,
    pub native: PathBuf,
    pub board: PathBuf,
    pub schematic: PathBuf,
    pub contract: Option<PathBuf>,
    pub composite: Option<PathBuf>,
    /// Retained numerical evidence directory for the PowerEntry thermal
    /// replay. The directory is optional so older manifests remain readable.
    #[serde(default)]
    pub thermal_evidence: Option<PathBuf>,
    /// Versioned physical package model contract and retained assessment.
    /// These remain optional so the historical seven-unit manifest stays
    /// replayable until the coordinator promotes a reviewed candidate.
    #[serde(default)]
    pub physical_model: Option<PathBuf>,
    #[serde(default)]
    pub physical_model_assessment: Option<PathBuf>,
    /// Archived manufacturer bytes for byte-level loss-source verification.
    #[serde(default)]
    pub physical_model_source: Option<PathBuf>,
    /// Mandatory joint FEM replay for PowerEntry; absent evidence fails coverage.
    #[serde(default)]
    pub joint_model_evidence: Option<PathBuf>,
    #[serde(default)]
    pub shunt_model_evidence: Option<PathBuf>,
    #[serde(default)]
    pub shunt_assembly_evidence: Option<PathBuf>,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: String,
    pub units: Vec<UnitRunSpec>,
}

#[derive(Debug, Serialize)]
pub struct UnitRunReport {
    pub schema: &'static str,
    pub unit: UnitKind,
    pub status: Status,
    pub input_hashes: BTreeMap<PathBuf, String>,
    pub executable_sha256: String,
    /// Unmodified unit truth verdict; no blanket hardware waiver is applied.
    pub unit_checks: CheckReport,
    pub common_checks: CheckReport,
    pub native_checks: CheckReport,
    pub power_checks: Option<CheckReport>,
    pub pfc_power: Option<crate::pfc_power::Report>,
    pub loss_budget: Option<crate::pfc_loss_budget::Report>,
    pub candidates: Option<crate::pfc_candidates::Report>,
    pub thermal_checks: Option<CheckReport>,
    pub physical_checks: Option<CheckReport>,
    pub joint_checks: Option<CheckReport>,
    pub shunt_checks: Option<CheckReport>,
    pub loop_checks: Option<CheckReport>,
    pub manufacturing_checks: CheckReport,
    /// Rule populations emitted by the Rust manufacturing evaluator.
    pub manufacturing_population: zapote_drc::manufacturing::P2Population,
    pub operating_checks: Option<CheckReport>,
    pub manufacturing_receipt_sha256: String,
    pub native_execution: Vec<NativeCommand>,
    pub required_rule_ids: Vec<String>,
    pub declared_checked_rule_ids: Vec<String>,
    pub native_population: BTreeMap<String, usize>,
    pub population_scope: &'static str,
    pub qualification: CheckReport,
}
#[derive(Debug, Serialize, Deserialize)]
pub struct NativeCommand {
    pub argv: Vec<String>,
    pub returncode: i32,
    pub input_sha256: String,
    pub report_sha256: String,
    pub report_path: PathBuf,
    pub dependency_hashes: BTreeMap<PathBuf, String>,
    pub tool_version: String,
}
pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn read(path: &Path) -> Result<Vec<u8>> {
    fs::read(path).map_err(|e| format!("read {}: {e}", path.display()))
}
fn text(bytes: &[u8]) -> Result<&str> {
    std::str::from_utf8(bytes).map_err(|e| e.to_string())
}
fn json<T: serde::de::DeserializeOwned>(bytes: &[u8]) -> Result<T> {
    serde_json::from_slice(bytes).map_err(|e| e.to_string())
}
fn required_path<'a>(p: &'a Option<PathBuf>, label: &str) -> Result<&'a Path> {
    p.as_deref()
        .ok_or_else(|| format!("required {label} input missing"))
}
fn hash_file(path: &Path) -> Result<String> {
    Ok(digest(&read(path)?))
}
pub fn combine(parts: &[&CheckReport]) -> CheckReport {
    let mut findings = Vec::new();
    let mut rules = BTreeSet::new();
    let mut gaps = BTreeSet::new();
    for p in parts {
        findings.extend(p.findings.clone());
        rules.extend(p.checked_rules.clone());
        gaps.extend(p.coverage_gaps.clone());
    }
    CheckReport::from_findings(
        findings,
        rules.into_iter().collect(),
        gaps.into_iter().collect(),
    )
}

/// Complete adopted registry, fixed by source, not caller-selected dispatch.
pub fn validate_manifest(m: &Manifest) -> Result<()> {
    if m.schema != "zapote.unit-run-manifest.v1" {
        return Err("unsupported runner manifest schema".into());
    }
    let got: BTreeSet<_> = m.units.iter().map(|s| s.unit.name()).collect();
    let want: BTreeSet<_> = [
        "rtd",
        "current-sense",
        "voltage-sense",
        "thermal-sense",
        "interlock",
        "gate-drive",
        "power-entry",
    ]
    .into_iter()
    .collect();
    if got != want || m.units.len() != want.len() {
        return Err("manifest must contain each of the seven maintained units exactly once".into());
    }
    Ok(())
}

/// Omitted checks fail even when every reported check was green.
pub fn enforce_required(required: &[String], report: &CheckReport) -> CheckReport {
    let missing: Vec<_> = required
        .iter()
        .filter(|id| !report.checked_rules.contains(id))
        .collect();
    let f = missing
        .iter()
        .map(|id| {
            Finding::fail(
                "RUNNER.REQUIRED_CHECKS",
                format!("required rule {id} was not executed"),
                (*id).clone(),
            )
        })
        .collect();
    CheckReport::from_findings(f, vec!["RUNNER.REQUIRED_CHECKS".into()], vec![])
}
fn required_rules(unit: UnitKind) -> Result<Vec<String>> {
    let inventory: serde_json::Value = serde_json::from_str(include_str!(
        "../../../validation/inventory-2026-09-12.json"
    ))
    .map_err(|e| e.to_string())?;
    let mut required: Vec<String> = inventory["units"]
        .as_array()
        .and_then(|us| us.iter().find(|u| u["unit"] == unit.name()))
        .and_then(|u| u["distinct_checked_rule_ids"].as_array())
        .ok_or_else(|| "unit absent from adopted registry".to_owned())?
        .iter()
        .map(|v| {
            v.as_str()
                .map(str::to_owned)
                .ok_or_else(|| "bad rule ID".to_owned())
        })
        .collect::<Result<_>>()?;
    // Coverage requirements are independent of whether the hook emitted a
    // report. Removing the thermal hook must fail closed, not shrink coverage.
    if unit == UnitKind::PowerEntry {
        required.extend(zapote_erc::pfc_interfaces::RULES.map(str::to_owned));
        required.push(zapote_erc::pfc_shunt::RULE.into());
        required.extend(zapote_erc::pfc_protection::RULES.map(str::to_owned));
        required.extend(crate::shunt_thermal::RULES.map(str::to_owned));
        required.extend(crate::pfc_loops::RULES.map(str::to_owned));
        required.extend(crate::pfc_power::RULES.map(str::to_owned));
        required.extend(crate::pfc_loss_budget::RULES.map(str::to_owned));
        required.extend(crate::model_assurance::RULES.map(str::to_owned));
        required.extend(crate::pfc_candidates::RULES.map(str::to_owned));
        required.extend(crate::bridge_thermal::RULES.map(str::to_owned));
        required.extend(crate::bridge_thermal::COOLING_RULES.map(str::to_owned));
        required.extend(crate::bridge_thermal::PHYSICAL_RULES.map(str::to_owned));
        required.extend(crate::bridge_thermal::JOINT_RULES.map(str::to_owned));
    }
    Ok(required)
}

/// Bind composite inputs to independently supplied source and native bytes.
pub fn evaluate(
    spec: &UnitRunSpec,
) -> Result<(CheckReport, UnitNativeEvidence, BTreeMap<PathBuf, String>)> {
    let mut inputs = BTreeMap::new();
    for p in [&spec.source, &spec.native, &spec.board, &spec.schematic]
        .into_iter()
        .chain(spec.contract.iter())
        .chain(spec.composite.iter())
        .chain(spec.physical_model.iter())
        .chain(spec.physical_model_assessment.iter())
        .chain(spec.physical_model_source.iter())
    {
        inputs.insert(p.clone(), read(p)?);
    }
    let source = &inputs[&spec.source];
    let native = &inputs[&spec.native];
    let board = &inputs[&spec.board];
    let n: UnitNativeEvidence = json(native)?;
    let raw: serde_json::Value = json(native)?;
    if n.board_sha256 != digest(board)
        || raw
            .get("board_file_utf8")
            .is_some_and(|v| v.as_str().map(str::as_bytes) != Some(board.as_slice()))
    {
        return Err("native export differs from supplied saved PCB bytes".into());
    }
    if n.components.is_empty() || n.connections.is_empty() || n.connectivity_clusters.is_empty() {
        return Err("required native component/pin/connectivity population is empty".into());
    }
    let source_text = text(source)?;
    let native_text = text(native)?;
    let report = match spec.unit {
        UnitKind::Rtd => {
            let p = required_path(&spec.composite, "RTD composite")?;
            let i: UnitInput = json(&inputs[p])?;
            if i.identity.source_manifest_sha256 != digest(source)
                || i.identity.native_export_sha256 != digest(native)
                || i.identity.board_sha256 != digest(board)
                || serde_json::to_value(&i.native).map_err(|e| e.to_string())?
                    != serde_json::to_value(&n).map_err(|e| e.to_string())?
            {
                return Err("RTD composite source/native/board binding differs".into());
            }
            crate::run_unit(&i)
        }
        UnitKind::CurrentSense => {
            let p = required_path(&spec.composite, "current-sense composite")?;
            let i = crate::parse_current_sense_input(&inputs[p]).map_err(|e| e.to_string())?;
            if i.source_manifest_utf8.as_bytes() != source
                || i.native_export_utf8.as_bytes() != native
                || i.identity.board_sha256 != digest(board)
            {
                return Err("current-sense composite source/native/board binding differs".into());
            }
            crate::run_current_sense(&i)
        }
        UnitKind::VoltageSense => crate::voltage_sense::parse_and_run(source, native)?,
        UnitKind::ThermalSense => crate::thermal_sense::parse_and_run(
            source,
            native,
            &inputs[required_path(&spec.contract, "thermal contract")?],
        )?,
        UnitKind::Interlock => crate::interlock::parse_and_run(
            source,
            native,
            &inputs[required_path(&spec.contract, "interlock contract")?],
        )?,
        UnitKind::GateDrive => crate::gate_drive::run(source_text, native_text, board),
        UnitKind::PowerEntry => crate::power_entry::run(source_text, native_text, board),
    };
    // Re-read before acceptance: a file changed while evaluating must not pass.
    let mut hashes = inputs
        .into_iter()
        .map(|(p, b)| Ok((p, digest(&b))))
        .collect::<Result<BTreeMap<_, _>>>()?;
    for root in [
        &spec.thermal_evidence,
        &spec.joint_model_evidence,
        &spec.shunt_model_evidence,
        &spec.shunt_assembly_evidence,
    ]
    .into_iter()
    .flatten()
    {
        hash_evidence_tree(root, &mut hashes)?;
    }
    verify_hashes(&hashes)?;
    Ok((report, n, hashes))
}
fn verify_hashes(hashes: &BTreeMap<PathBuf, String>) -> Result<()> {
    for (p, h) in hashes {
        if &hash_file(p)? != h {
            return Err(format!("input changed during run: {}", p.display()));
        }
    }
    Ok(())
}
fn hash_evidence_tree(root: &Path, hashes: &mut BTreeMap<PathBuf, String>) -> Result<()> {
    if !root.exists() {
        return Ok(());
    }
    let metadata = fs::symlink_metadata(root).map_err(|e| e.to_string())?;
    if metadata.file_type().is_symlink() {
        hashes.insert(root.to_owned(), hash_file(root)?);
    } else if metadata.is_dir() {
        for entry in fs::read_dir(root).map_err(|e| e.to_string())? {
            let path = entry.map_err(|e| e.to_string())?.path();
            hash_evidence_tree(&path, hashes)?;
        }
    } else {
        hashes.insert(root.to_owned(), hash_file(root)?);
    }
    Ok(())
}
fn evidence_hashes(spec: &UnitRunSpec) -> Result<BTreeMap<PathBuf, String>> {
    let mut hashes = BTreeMap::new();
    for root in [
        &spec.thermal_evidence,
        &spec.joint_model_evidence,
        &spec.shunt_model_evidence,
        &spec.shunt_assembly_evidence,
    ]
    .into_iter()
    .flatten()
    {
        hash_evidence_tree(root, &mut hashes)?;
    }
    Ok(hashes)
}
fn dependencies(dir: &Path, hashes: &mut BTreeMap<PathBuf, String>) -> Result<()> {
    for item in fs::read_dir(dir).map_err(|e| e.to_string())? {
        let p = item.map_err(|e| e.to_string())?.path();
        if p.is_dir() {
            dependencies(&p, hashes)?;
        } else {
            let ext = p.extension().and_then(|s| s.to_str()).unwrap_or("");
            let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("");
            if [
                "kicad_pcb",
                "kicad_sch",
                "kicad_pro",
                "kicad_dru",
                "kicad_mod",
                "kicad_sym",
            ]
            .contains(&ext)
                || ["fp-lib-table", "sym-lib-table"].contains(&name)
            {
                hashes.insert(p.clone(), hash_file(&p)?);
            }
        }
    }
    Ok(())
}
/// Verify a captured command against current inputs and exact report bytes.
pub fn verify_native_binding(c: &NativeCommand, source: &Path, report: &[u8]) -> Result<()> {
    if c.input_sha256 != hash_file(source)? || c.report_sha256 != digest(report) {
        return Err("native command input/report hash mismatch".into());
    }
    if c.dependency_hashes.is_empty() || !c.dependency_hashes.contains_key(source) {
        return Err("native command lacks required dependency census".into());
    }
    verify_hashes(&c.dependency_hashes)
}
fn native_run(
    spec: &UnitRunSpec,
    out: &Path,
    kicad: &Path,
) -> Result<(CheckReport, Vec<NativeCommand>)> {
    fs::create_dir_all(out).map_err(|e| e.to_string())?;
    let version = Command::new(kicad)
        .arg("--version")
        .output()
        .map_err(|e| e.to_string())?;
    if !version.status.success() {
        return Err("kicad-cli version probe failed".into());
    }
    let version = String::from_utf8_lossy(&version.stdout).trim().to_owned();
    let mut captures = Vec::new();
    let mut reports = Vec::new();
    let mut commands = Vec::new();
    for (kind, domain, path) in [("erc", "sch", &spec.schematic), ("drc", "pcb", &spec.board)] {
        let source = path.canonicalize().map_err(|e| e.to_string())?;
        let mut deps = BTreeMap::new();
        dependencies(source.parent().ok_or("source parent missing")?, &mut deps)?;
        let report_path = out.join(format!("{kind}.json"));
        if report_path.exists() {
            return Err(format!(
                "refusing to overwrite existing native evidence: {}",
                report_path.display()
            ));
        }
        let mut argv = vec![
            kicad.to_string_lossy().into_owned(),
            domain.into(),
            kind.into(),
            "--severity-all".into(),
        ];
        if kind == "drc" {
            argv.extend(["--all-track-errors".into(), "--schematic-parity".into()]);
        }
        argv.extend([
            "--format".into(),
            "json".into(),
            "--output".into(),
            report_path.to_string_lossy().into_owned(),
            source.to_string_lossy().into_owned(),
        ]);
        let child = Command::new(kicad)
            .args(&argv[1..])
            .output()
            .map_err(|e| e.to_string())?;
        fs::write(out.join(format!("{kind}.stdout")), &child.stdout).map_err(|e| e.to_string())?;
        fs::write(out.join(format!("{kind}.stderr")), &child.stderr).map_err(|e| e.to_string())?;
        let report = read(&report_path)?;
        let c = NativeCommand {
            argv,
            returncode: child.status.code().unwrap_or(-1),
            input_sha256: deps.get(&source).ok_or("source hash missing")?.clone(),
            report_sha256: digest(&report),
            report_path,
            dependency_hashes: deps,
            tool_version: version.clone(),
        };
        verify_native_binding(&c, &source, &report)?;
        let command = serde_json::to_string_pretty(&c).map_err(|e| e.to_string())?;
        fs::write(out.join(format!("{kind}-command.json")), &command).map_err(|e| e.to_string())?;
        reports.push(String::from_utf8(report).map_err(|e| e.to_string())?);
        commands.push(command);
        captures.push(c);
    }
    Ok((
        crate::native_reports::validate(&reports[0], &reports[1], &commands[0], &commands[1]),
        captures,
    ))
}
fn manufacturing_run(
    spec: &UnitRunSpec,
    out: &Path,
    python: &Path,
    native: &UnitNativeEvidence,
) -> Result<(CheckReport, String, zapote_drc::manufacturing::P2Population)> {
    fs::create_dir_all(out).map_err(|e| e.to_string())?;
    let extractor = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../validation/p2/extract.py");
    let extractor_hash = hash_file(&extractor)?;
    let receipt_path = out.join("manufacturing-input.json");
    let argv = vec![
        extractor.to_string_lossy().into_owned(),
        spec.board.to_string_lossy().into_owned(),
        receipt_path.to_string_lossy().into_owned(),
    ];
    let child = Command::new(python)
        .args(&argv)
        .output()
        .map_err(|e| e.to_string())?;
    fs::write(out.join("manufacturing.stdout"), &child.stdout).map_err(|e| e.to_string())?;
    fs::write(out.join("manufacturing.stderr"), &child.stderr).map_err(|e| e.to_string())?;
    fs::write(out.join("manufacturing-command.json"), serde_json::to_vec_pretty(&serde_json::json!({"python":python,"argv":argv,"returncode":child.status.code(),"extractor_sha256":extractor_hash})).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    if !child.status.success() {
        return Err("manufacturing native extraction failed; see captured stderr".into());
    }
    let bytes = read(&receipt_path)?;
    let receipt: serde_json::Value = json(&bytes)?;
    if receipt["schema"] != "zapote.manufacturing-native.v1"
        || receipt["board_sha256"] != hash_file(&spec.board)?
        || receipt["extractor_sha256"] != extractor_hash
        || hash_file(&extractor)? != extractor_hash
    {
        return Err("manufacturing board/extractor identity mismatch".into());
    }
    for (key, expected) in [
        ("footprints", native.components.len()),
        (
            "pads",
            native
                .components
                .iter()
                .map(|c| c.footprint_pads.len())
                .sum(),
        ),
        ("tracks", native.traces.len()),
        ("vias", native.vias.len()),
    ] {
        if receipt["native_census"][key].as_u64() != Some(expected as u64) {
            return Err(format!(
                "manufacturing {key} census differs from native unit export"
            ));
        }
    }
    let input = serde_json::from_value(receipt["input"].clone()).map_err(|e| e.to_string())?;
    let (report, population) = zapote_drc::manufacturing::validate_with_population(&input);
    Ok((report, digest(&bytes), population))
}

fn bound_manufacturing_bytes(path: &Path, expected_hash: &str) -> Result<Vec<u8>> {
    let bytes = read(path)?;
    if digest(&bytes) != expected_hash {
        return Err("manufacturing receipt changed after native extraction validation".into());
    }
    Ok(bytes)
}

fn active_model_gap(rules: impl IntoIterator<Item = &'static str>, incompatible_evidence: bool) -> CheckReport {
    let rules: Vec<_> = rules.into_iter().collect();
    let message = "active rectifier has no board-bound loss/thermal model in this runner; passive GBU/GBJ evidence cannot qualify four IPW60R017C7 devices or the TEA2209T";
    CheckReport::from_findings(
        rules.iter().map(|rule| if incompatible_evidence {
            Finding::fail(rule, format!("inapplicable model supplied: {message}"), "active-rectifier")
        } else { Finding::indeterminate(rule, message, "active-rectifier") }).collect(),
        rules.iter().map(|r| (*r).into()).collect(),
        vec![message.into()],
    )
}

fn passive_gbu_loss_gap() -> CheckReport {
    let rules = crate::pfc_loss_budget::RULES.into_iter()
        .chain(crate::model_assurance::RULES)
        .chain(crate::pfc_candidates::RULES);
    let message = "GBU2510A board has no matching diode loss/candidate model in this runner; GBJ2510-F source data cannot qualify its bridge";
    CheckReport::from_findings(
        rules.clone().map(|rule| Finding::indeterminate(rule, message, "GBU2510A")).collect(),
        rules.map(str::to_owned).collect(),
        vec![message.into()],
    )
}

fn has_gbj_loss_model(bridge_mpn: &str) -> Result<bool> {
    match bridge_mpn {
        "GBJ2510-F" => Ok(true),
        "GBU2510A" => Ok(false),
        _ => Err(format!("no reviewed passive bridge identity for {bridge_mpn}")),
    }
}

pub fn run(spec: &UnitRunSpec, out: &Path, kicad: &Path, python: &Path) -> Result<UnitRunReport> {
    let evidence_before = evidence_hashes(spec)?;
    let (mut unit_checks, native, hashes) = evaluate(spec)?;
    let native_text = String::from_utf8(read(&spec.native)?).map_err(|e| e.to_string())?;
    let source = String::from_utf8(read(&spec.source)?).map_err(|e| e.to_string())?;
    let board = read(&spec.board)?;
    let stack = zapote_drc::stackup::validate_board(text(&board)?);
    let mut bound_native: serde_json::Value =
        serde_json::from_str(&native_text).map_err(|e| e.to_string())?;
    // Legacy RTD receipts identify the saved board by hash; evaluate verified it above.
    bound_native["board_file_utf8"] = text(&board)?.into();
    let binding = zapote_drc::native_binding::validate(&bound_native.to_string());
    let power_checks = match spec.unit {
        UnitKind::GateDrive => Some(crate::p1::run(
            &source,
            &native_text,
            &board,
            crate::p1::P1Unit::GateDrive,
        )),
        UnitKind::PowerEntry => Some(crate::p1::run(
            &source,
            &native_text,
            &board,
            crate::p1::P1Unit::Pfc,
        )),
        _ => None,
    };
    let operating_checks = match spec.unit {
        UnitKind::GateDrive
        | UnitKind::PowerEntry
        | UnitKind::CurrentSense
        | UnitKind::Interlock => Some(crate::p3::run(
            spec.unit.name(),
            &source,
            &native_text,
            &board,
        )),
        _ => None,
    };
    let (manufacturing_checks, manufacturing_receipt_sha256, manufacturing_population) =
        manufacturing_run(spec, out, python, &native)?;
    let manufacturing_bytes = bound_manufacturing_bytes(
        &out.join("manufacturing-input.json"),
        &manufacturing_receipt_sha256,
    )?;
    let pfc_power = if spec.unit == UnitKind::PowerEntry {
        let receipt = json(&manufacturing_bytes)?;
        Some(crate::pfc_power::run(
            &source,
            &native_text,
            text(&board)?,
            &receipt,
        )?)
    } else {
        None
    };
    let active_rectifier = spec.unit == UnitKind::PowerEntry
        && zapote_erc::power_entry::entry(&source)? == zapote_erc::power_entry::ACTIVE_ENTRY;
    let gbj_loss_model = if spec.unit == UnitKind::PowerEntry && !active_rectifier {
        let circuit = zapote_erc::source_circuit::Circuit::parse(
            &source, zapote_erc::power_entry::ENTRY)?;
        let bridge = circuit.components.get("bridge")
            .ok_or_else(|| "power-entry source has no bridge".to_owned())?;
        has_gbj_loss_model(&bridge.mpn)?
    } else {
        false
    };
    if active_rectifier {
        unit_checks = combine(&[&unit_checks, &active_model_gap(
            crate::pfc_loss_budget::RULES.into_iter()
                .chain(crate::model_assurance::RULES)
                .chain(crate::pfc_candidates::RULES), false)]);
    } else if spec.unit == UnitKind::PowerEntry && !gbj_loss_model {
        unit_checks = combine(&[&unit_checks, &passive_gbu_loss_gap()]);
    }
    let loss_budget = if gbj_loss_model {
        Some(crate::pfc_loss_budget::run(&source)?)
    } else { None };
    let candidates = if gbj_loss_model {
        Some(crate::pfc_candidates::run(&source)?)
    } else { None };
    let loop_checks = if spec.unit == UnitKind::PowerEntry {
        Some(crate::pfc_loops::run(
            &source,
            &native_text,
            &json(&manufacturing_bytes)?,
        ))
    } else {
        None
    };
    let cooling_contract = spec.contract.as_ref().map(|p| read(p)).transpose()?;
    let manufacturing_geometry = Some(manufacturing_bytes);
    let gbj_reports = (spec.unit == UnitKind::PowerEntry
        && native
            .components
            .iter()
            .any(|c| c.id == "bridge" && c.mpn == "GBJ2510-F"))
    .then(|| {
        crate::bridge_thermal::run_gbj_model(
            spec.joint_model_evidence.as_deref(),
            native_text.as_bytes(),
            manufacturing_geometry.as_deref(),
            pfc_power.as_ref(),
        )
    });
    let shunt_checks = (spec.unit == UnitKind::PowerEntry).then(|| {
        crate::shunt_thermal::run(
            spec.shunt_model_evidence.as_deref(),
            spec.shunt_assembly_evidence.as_deref(),
            native_text.as_bytes(),
            pfc_power.as_ref(),
        )
    });
    let thermal_checks = (spec.unit == UnitKind::PowerEntry).then(|| {
        if active_rectifier {
            return active_model_gap(crate::bridge_thermal::RULES.into_iter().chain(crate::bridge_thermal::COOLING_RULES), spec.thermal_evidence.is_some() || spec.contract.is_some());
        }
        if let Some(reports) = &gbj_reports {
            return reports.thermal.clone();
        }
        crate::bridge_thermal::run_with_contract(
            spec.thermal_evidence.as_deref(),
            &board,
            pfc_power.as_ref(),
            cooling_contract.as_deref(),
        )
    });
    if (spec.physical_model.is_some() || spec.physical_model_assessment.is_some())
        && (spec.physical_model.is_none() || spec.physical_model_assessment.is_none())
    {
        return Err("physical-model contract and assessment must be supplied together".into());
    }
    let physical_contract = spec.physical_model.as_ref().map(|p| read(p)).transpose()?;
    let physical_assessment = spec
        .physical_model_assessment
        .as_ref()
        .map(|p| read(p))
        .transpose()?;
    let physical_source = spec
        .physical_model_source
        .as_ref()
        .map(|p| read(p))
        .transpose()?;
    let physical_checks = (spec.unit == UnitKind::PowerEntry).then(|| {
        if active_rectifier {
            return active_model_gap(crate::bridge_thermal::PHYSICAL_RULES, spec.physical_model.is_some() || spec.physical_model_source.is_some());
        }
        if let Some(reports) = &gbj_reports {
            return reports.physical.clone();
        }
        crate::bridge_thermal::run_with_physical_model(
            spec.thermal_evidence.as_deref(),
            &board,
            pfc_power.as_ref(),
            physical_contract.as_deref(),
            physical_assessment.as_deref(),
            physical_source.as_deref(),
            Some(native_text.as_bytes()),
            manufacturing_geometry.as_deref(),
        )
    });
    let joint_checks = (spec.unit == UnitKind::PowerEntry).then(|| {
        if active_rectifier {
            return active_model_gap(crate::bridge_thermal::JOINT_RULES, spec.joint_model_evidence.is_some());
        }
        if let Some(reports) = &gbj_reports {
            return reports.joint.clone();
        }
        crate::bridge_thermal::run_joint_model(
            spec.joint_model_evidence.as_deref(),
            native_text.as_bytes(),
            manufacturing_geometry.as_deref(),
            pfc_power.as_ref(),
        )
    });
    let mut required = required_rules(spec.unit)?;
    if physical_checks.is_some() {
        required.extend(crate::bridge_thermal::PHYSICAL_RULES.map(str::to_owned));
    }
    required.extend(
        [
            "DRC.P2.BODY_COLLISION",
            "DRC.P2.ANNULAR_RING",
            "DRC.P2.DRILL_CONFLICT",
            "DRC.P2.COPPER_OUTLINE",
            "DRC.P2.SUPPORTED_ANGLE",
        ]
        .map(str::to_owned),
    );
    if power_checks.is_some() {
        required.extend(
            [
                "ERC.POWER.P1_SOURCE_NATIVE_BINDING",
                "DRC.POWER.P1_SAVED_BOARD_IDENTITY",
                "ERC.POWER.DOMAIN_PIN_CONTRACT",
                "DRC.POWER.PATH_AMPACITY",
                "DRC.POWER.ISOLATION_POPULATION",
            ]
            .map(str::to_owned),
        );
    }
    if operating_checks.is_some() {
        required.extend(
            [
                "ERC.P3.THERMAL_OPERATING_LIMIT",
                "ERC.P3.SHUTDOWN_TIMING_BOUND",
            ]
            .map(str::to_owned),
        );
    }
    if matches!(spec.unit, UnitKind::GateDrive | UnitKind::PowerEntry) {
        required.extend(
            [
                "DRC.P3.SWITCHING_LOOP_AREA",
                "DRC.P3.RETURN_PATH_CONTINUITY",
                "DRC.P3.AGGRESSOR_VICTIM_SPACING",
            ]
            .map(str::to_owned),
        );
    } else if operating_checks.is_some() {
        required.push("DRC.P3.APPLICABILITY".into());
    }
    let mut parts = vec![&unit_checks, &manufacturing_checks];
    parts.extend(power_checks.iter());
    parts.extend(pfc_power.iter().map(|r| &r.checks));
    parts.extend(loss_budget.iter().map(|r| &r.checks));
    parts.extend(candidates.iter().map(|r| &r.checks));
    parts.extend(thermal_checks.iter());
    parts.extend(physical_checks.iter());
    parts.extend(joint_checks.iter());
    parts.extend(shunt_checks.iter());
    parts.extend(loop_checks.iter());
    parts.extend(operating_checks.iter());
    let coverage = enforce_required(&required, &combine(&parts));
    let common = combine(&[&stack, &binding, &coverage]);
    let (native_checks, native_execution) = native_run(spec, out, kicad)?;
    if evidence_before != evidence_hashes(spec)? {
        return Err("thermal or joint FEM evidence changed during run".into());
    }
    verify_hashes(&hashes)?;
    let qualification=CheckReport::from_findings(vec![Finding::indeterminate("QUALIFICATION.HARDWARE","powered hardware qualification has not been performed; other model, implementation and input gaps are preserved separately","unit")],vec!["QUALIFICATION.HARDWARE".into()],vec!["hardware not run".into()]);
    parts.extend([&common, &native_checks, &qualification]);
    let all = combine(&parts);
    let population = BTreeMap::from([
        ("components".into(), native.components.len()),
        ("connections".into(), native.connections.len()),
        (
            "connectivity_clusters".into(),
            native.connectivity_clusters.len(),
        ),
        ("traces".into(), native.traces.len()),
        ("vias".into(), native.vias.len()),
        ("zones".into(), native.zones.len()),
    ]);
    let executable_sha256 = hash_file(&std::env::current_exe().map_err(|e| e.to_string())?)?;
    Ok(UnitRunReport{schema:"zapote.unit-run.v2",unit:spec.unit,status:all.status,input_hashes:hashes,executable_sha256,unit_checks,common_checks:common,native_checks,power_checks,pfc_power,loss_budget,candidates,thermal_checks,physical_checks,joint_checks,shunt_checks,loop_checks,manufacturing_checks,manufacturing_population,operating_checks,manufacturing_receipt_sha256,native_execution,required_rule_ids:required,declared_checked_rule_ids:all.checked_rules,native_population:population,population_scope:"native_population is an input census. manufacturing_population records Rust P2 evaluations separately; other unit rules do not uniformly expose evaluated counts.",qualification})
}

#[cfg(test)]
mod cooling_coverage_tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn active_model_gaps_keep_every_obligation_and_reject_passive_evidence() {
        let rules: Vec<_> = crate::pfc_loss_budget::RULES.into_iter()
            .chain(crate::model_assurance::RULES).chain(crate::pfc_candidates::RULES)
            .chain(crate::bridge_thermal::RULES).chain(crate::bridge_thermal::COOLING_RULES)
            .chain(crate::bridge_thermal::PHYSICAL_RULES).chain(crate::bridge_thermal::JOINT_RULES).collect();
        let report = active_model_gap(rules.iter().copied(), false);
        assert_eq!(report.status, zapote_core::Status::Indeterminate);
        for rule in &rules {
            assert!(report.checked_rules.iter().any(|r| r == rule));
            assert!(report.findings.iter().any(|f| f.rule == *rule && f.status == zapote_core::Status::Indeterminate));
        }
        let reuse = active_model_gap(crate::bridge_thermal::JOINT_RULES, true);
        assert_eq!(reuse.status, zapote_core::Status::Fail);
        assert!(reuse.findings.iter().all(|f| f.message.contains("inapplicable model supplied")));
    }

    #[test]
    fn gbu_bridge_keeps_loss_obligations_indeterminate() {
        assert!(!has_gbj_loss_model("GBU2510A").unwrap());
        let report = passive_gbu_loss_gap();
        assert_eq!(report.status, zapote_core::Status::Indeterminate);
        for rule in crate::pfc_loss_budget::RULES.into_iter()
            .chain(crate::model_assurance::RULES)
            .chain(crate::pfc_candidates::RULES)
        {
            assert!(report.findings.iter().any(|f| f.rule == rule &&
                f.status == zapote_core::Status::Indeterminate));
        }
    }

    #[test]
    fn gbj_bridge_keeps_its_bound_loss_screen() {
        assert!(has_gbj_loss_model("GBJ2510-F").unwrap());
    }

    #[test]
    fn unreviewed_passive_bridge_still_fails_closed() {
        assert!(has_gbj_loss_model("GBU2510").is_err());
    }

    #[test]
    fn edited_geometry_with_unchanged_board_identity_cannot_reach_downstream_checks() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("zapote-receipt-{suffix}.json"));
        let original = br#"{"board_sha256":"same-board","inner_copper_polygons":[[0,0],[1,1]]}"#;
        fs::write(&path, original).unwrap();
        let expected = digest(original);
        assert_eq!(
            bound_manufacturing_bytes(&path, &expected).unwrap(),
            original
        );
        fs::write(
            &path,
            br#"{"board_sha256":"same-board","inner_copper_polygons":[[0,0],[100,100]]}"#,
        )
        .unwrap();
        let result = bound_manufacturing_bytes(&path, &expected);
        fs::remove_file(path).unwrap();
        assert!(result.unwrap_err().contains("receipt changed"));
    }

    #[test]
    fn power_entry_requires_electrical_rules_even_if_hooks_are_removed() {
        let required = required_rules(UnitKind::PowerEntry).unwrap();
        for rule in zapote_erc::pfc_interfaces::RULES
            .into_iter()
            .chain(crate::pfc_power::RULES)
            .chain(crate::model_assurance::RULES)
        {
            assert!(required.iter().any(|id| id == rule));
            let missing_one = CheckReport::from_findings(
                vec![],
                required.iter().filter(|id| *id != rule).cloned().collect(),
                vec![],
            );
            let coverage = enforce_required(&required, &missing_one);
            assert_eq!(coverage.status, Status::Fail);
            assert!(coverage.findings.iter().any(|f| f.message.contains(rule)));
        }
    }

    #[test]
    fn power_entry_requires_cooling_even_when_the_hook_emits_no_report() {
        let required = required_rules(UnitKind::PowerEntry).unwrap();
        for rule in crate::bridge_thermal::RULES
            .into_iter()
            .chain(crate::bridge_thermal::COOLING_RULES)
        {
            assert!(required.iter().any(|id| id == rule));
        }
        let without_cooling = CheckReport::from_findings(
            vec![],
            required
                .iter()
                .filter(|id| !id.starts_with("THERMAL.POWER_ENTRY."))
                .cloned()
                .collect(),
            vec![],
        );
        let coverage = enforce_required(&required, &without_cooling);
        assert_eq!(coverage.status, Status::Fail);
        assert_eq!(coverage.findings.len(), 10);
        for rule in crate::bridge_thermal::PHYSICAL_RULES {
            assert!(coverage.findings.iter().any(|f| f.message.contains(rule)));
        }
    }

    #[test]
    fn joint_model_evidence_is_hashed_and_mutation_is_rejected() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock before epoch")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("zapote-joint-evidence-{suffix}"));
        fs::create_dir_all(root.join("mesh-0")).unwrap();
        let evidence = root.join("mesh-0/result.dat");
        fs::write(&evidence, b"raw solver result").unwrap();
        let spec = UnitRunSpec {
            unit: UnitKind::PowerEntry,
            source: PathBuf::from("source"),
            native: PathBuf::from("native"),
            board: PathBuf::from("board"),
            schematic: PathBuf::from("schematic"),
            contract: None,
            composite: None,
            thermal_evidence: None,
            physical_model: None,
            physical_model_assessment: None,
            physical_model_source: None,
            joint_model_evidence: Some(root.clone()),
            shunt_model_evidence: None,
            shunt_assembly_evidence: None,
        };
        let hashes = evidence_hashes(&spec).unwrap();
        assert_eq!(hashes.get(&evidence), Some(&digest(b"raw solver result")));
        fs::write(&evidence, b"edited solver result").unwrap();
        assert!(verify_hashes(&hashes).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
