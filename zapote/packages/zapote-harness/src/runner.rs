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
    inventory["units"]
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
        .collect()
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
    let hashes = inputs
        .into_iter()
        .map(|(p, b)| Ok((p, digest(&b))))
        .collect::<Result<BTreeMap<_, _>>>()?;
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

pub fn run(spec: &UnitRunSpec, out: &Path, kicad: &Path, python: &Path) -> Result<UnitRunReport> {
    let (unit_checks, native, hashes) = evaluate(spec)?;
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
    let pfc_power = if spec.unit == UnitKind::PowerEntry {
        let receipt = json(&read(&out.join("manufacturing-input.json"))?)?;
        Some(crate::pfc_power::run(&source, &native_text, text(&board)?, &receipt)?)
    } else { None };
    let mut required = required_rules(spec.unit)?;
    if pfc_power.is_some() { required.extend(crate::pfc_power::RULES.map(str::to_owned)); }
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
    parts.extend(pfc_power.iter().map(|r|&r.checks));
    parts.extend(operating_checks.iter());
    let coverage = enforce_required(&required, &combine(&parts));
    let common = combine(&[&stack, &binding, &coverage]);
    let (native_checks, native_execution) = native_run(spec, out, kicad)?;
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
    Ok(UnitRunReport{schema:"zapote.unit-run.v2",unit:spec.unit,status:all.status,input_hashes:hashes,executable_sha256,unit_checks,common_checks:common,native_checks,power_checks,pfc_power,manufacturing_checks,manufacturing_population,operating_checks,manufacturing_receipt_sha256,native_execution,required_rule_ids:required,declared_checked_rule_ids:all.checked_rules,native_population:population,population_scope:"native_population is an input census. manufacturing_population records Rust P2 evaluations separately; other unit rules do not uniformly expose evaluated counts.",qualification})
}
