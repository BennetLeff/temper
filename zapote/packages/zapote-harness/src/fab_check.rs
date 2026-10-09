//! The fab pass: vendor limits that KiCad's own DRC measures (copper
//! clearance, hole to copper per hole type, silkscreen text size).
//!
//! KiCad runs on a copy of the board, with its `.kicad_pro` (so the
//! designer's severities and exclusions still apply) and a `.kicad_dru`
//! holding only the profile's `zapote fab` rules. When several custom rules
//! match, KiCad applies the last even if it is looser (measured on 10.0.4),
//! so vendor rules are never mixed into the board's own rules; the input
//! board and its rules are untouched and stay with the native pass. A pad or
//! footprint local clearance also beats every custom rule, so the copy is
//! written without them (`tools/fab_board_copy.py`).
//!
//! KiCad ignores a malformed `.kicad_dru` without an error. The same rules
//! therefore run first on a committed self-test board that breaks every one
//! of them by a wide margin; a rule that does not fire there is reported as a
//! coverage gap instead of as a pass.
use crate::native_reports::{self, DrcReport, NativeViolation};
use crate::runner::digest;
use std::{collections::BTreeSet, fs, path::Path, process::Command};
use zapote_core::{CheckReport, Finding};
use zapote_drc::fab_rules::{kicad_rules, rules, KicadRule};
use zapote_drc::manufacturing::FabricationLimits;

type Result<T> = std::result::Result<T, String>;

/// Built by `zapote/tools/make_fab_selftest_board.py`.
const SELFTEST_BOARD: &str = include_str!("../fixtures/fab_selftest.kicad_pcb");
const BOARD_COPY_SCRIPT: &str = include_str!("../../../tools/fab_board_copy.py");
const CONTRACT: &str = "FAB.REPORT_CONTRACT";

/// What KiCad's custom rules cannot express; listed in the evidence.
const NOT_COVERED: [&str; 1] =
    ["silkscreen graphic line width (JLC scopes its legend line width to characters, which are checked)"];

/// The fab rule a violation is attributed to. KiCad states a custom rule in
/// the first parenthesised clause, `(rule '<name>' ...)`; anything later (net
/// or netclass names) cannot claim a fab rule. A violation naming no rule
/// belongs to a board-setup fab rule (empty text) of the same type, which the
/// fab copy set itself; other board-setup findings stay with the native pass.
fn attributed<'a>(v: &NativeViolation, rules: &'a [KicadRule]) -> Option<&'a KicadRule> {
    let named = v
        .description
        .find('(')
        .and_then(|open| v.description[open + 1..].strip_prefix("rule '"))
        .and_then(|rest| rest.split('\'').next());
    match named {
        Some(name) => rules.iter().find(|r| r.name == name),
        None => rules.iter().find(|r| r.text.is_empty() && r.violation == v.kind),
    }
}

/// Judge the board's report. Only violations KiCad attributes to a fab rule
/// count; board-setup and netclass findings belong to the native pass.
pub fn evaluate(rules: &[KicadRule], selftest: &DrcReport, board: &DrcReport) -> CheckReport {
    let fired: BTreeSet<&str> = selftest
        .violations
        .iter()
        .filter_map(|v| attributed(v, rules))
        .map(|r| r.name.as_str())
        .collect();
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let mut checked: BTreeSet<String> = [CONTRACT.to_string()].into();
    for rule in rules {
        let id = format!("FAB.{}", rule.violation);
        checked.insert(id.clone());
        let mut hits = 0;
        for v in board.violations.iter().filter(|v| attributed(v, rules) == Some(rule)) {
            hits += 1;
            if v.kind == rule.violation {
                findings.push(native_reports::finding(v, &id));
            } else {
                findings.push(Finding::fail(
                    CONTRACT,
                    format!(
                        "KiCad reported a {} violation for {} rule '{}'",
                        v.kind, rule.violation, rule.name
                    ),
                    native_reports::finding(v, &id).object,
                ));
            }
        }
        if hits > 0 {
            continue;
        }
        if !fired.contains(rule.name.as_str()) {
            gaps.push(format!(
                "rule '{}' did not fire on the self-test board: KiCad did not apply it, or the limit \
                 is at or below the self-test board's geometry; no result on this board counts",
                rule.name
            ));
        } else if board.ignored_checks.contains(&rule.violation) {
            gaps.push(format!(
                "the board's project ignores {} checks, so rule '{}' cannot report",
                rule.violation, rule.name
            ));
        } else {
            findings.push(Finding::pass(&id, format!("0 violations of '{}'", rule.name), "board"));
        }
    }
    CheckReport::from_findings(findings, checked.into_iter().collect(), gaps)
}

/// Result of [`fab_check`].
pub struct FabCheck {
    pub report: CheckReport,
    /// Rules hash, KiCad version, project, cleared overrides and command receipts.
    pub evidence: serde_json::Value,
}

/// Inputs of [`fab_check`]. `board_bytes` are the bytes the caller hashed.
pub struct FabInputs<'a> {
    pub board: &'a Path,
    pub board_bytes: &'a [u8],
    /// Must not exist yet.
    pub out: &'a Path,
    pub kicad: &'a Path,
    /// A Python with KiCad's `pcbnew`, for the board copy.
    pub python: &'a Path,
}

/// Run the fab pass. `None` when the profile sets no limit this pass applies:
/// the check is then absent, not passed. Tool and report failures become a
/// failing `FAB.REPORT_CONTRACT` finding; only I/O errors are `Err`.
pub fn fab_check(i: &FabInputs, limits: &FabricationLimits) -> Result<Option<FabCheck>> {
    let set = rules(limits);
    if set.is_empty() {
        return Ok(None);
    }
    let text = kicad_rules(limits).unwrap_or_else(|| "(version 1)\n".into());
    fs::create_dir(i.out).map_err(|e| format!("fab output {} must be new: {e}", i.out.display()))?;
    let mut evidence = serde_json::json!({
        "rules_sha256": digest(text.as_bytes()),
        "rules": set.iter().map(|r| &r.name).collect::<Vec<_>>(),
        "board_sha256": digest(i.board_bytes),
        "not_covered": NOT_COVERED,
    });
    let report = match run(i, &text, limits.minimum_solder_mask_web_mm, &mut evidence) {
        Ok((selftest, board)) => evaluate(&set, &selftest, &board),
        Err(Failure::Io(e)) => return Err(e),
        Err(Failure::Contract(e)) => {
            evidence["error"] = e.clone().into();
            let finding = Finding::fail(CONTRACT, e, "fab pass");
            CheckReport::from_findings(vec![finding], vec![CONTRACT.into()], vec![])
        }
    };
    Ok(Some(FabCheck { report, evidence }))
}

/// The fab pass must judge the `.kicad_pro` the native DRC hashed: the
/// project beside `board` per the native DRC command's dependency census.
pub fn check_project_matches_native(
    fab: &FabCheck,
    board: &Path,
    native: &[crate::runner::NativeCommand],
) -> Result<()> {
    let project = board.canonicalize().map_err(|e| e.to_string())?.with_extension("kicad_pro");
    let native_project = native
        .iter()
        .find(|n| n.argv.get(2).map(String::as_str) == Some("drc"))
        .and_then(|n| n.dependency_hashes.get(&project));
    let fab_project = fab.evidence.get("project_sha256");
    if fab_project.is_some_and(|h| h.as_str() != native_project.map(String::as_str)) {
        return Err("board project changed between the native and fab passes".into());
    }
    Ok(())
}

enum Failure {
    Io(String),
    Contract(String),
}

fn io<E: std::fmt::Display>(e: E) -> Failure {
    Failure::Io(e.to_string())
}

type Outcome<T> = std::result::Result<T, Failure>;

fn run(
    i: &FabInputs,
    rules: &str,
    mask_web_mm: Option<f64>,
    evidence: &mut serde_json::Value,
) -> Outcome<(DrcReport, DrcReport)> {
    let version = Command::new(i.kicad).arg("--version").output().map_err(io)?;
    if !version.status.success() {
        return Err(Failure::Contract("kicad-cli version probe failed".into()));
    }
    evidence["kicad_version"] = String::from_utf8_lossy(&version.stdout).trim().into();
    let script = i.out.join("fab_board_copy.py");
    fs::write(&script, BOARD_COPY_SCRIPT).map_err(io)?;
    evidence["board_copy_script_sha256"] = digest(BOARD_COPY_SCRIPT.as_bytes()).into();

    // Self-test board, through the same copy step, with no project: KiCad's
    // default severities.
    let selftest_dir = i.out.join("self-test");
    fs::create_dir(&selftest_dir).map_err(io)?;
    let selftest_board = selftest_dir.join("fab_selftest.kicad_pcb");
    copy_board(i, &script, SELFTEST_BOARD.as_bytes(), &selftest_board, mask_web_mm, evidence, "self_test_copy")?;
    fs::write(selftest_board.with_extension("kicad_dru"), rules).map_err(io)?;
    let selftest = drc(i.kicad, &selftest_board, evidence, "self_test")?;

    // The board copy, beside the board's own project file.
    let board_dir = i.out.join("board");
    fs::create_dir(&board_dir).map_err(io)?;
    let name = i.board.file_name().ok_or_else(|| Failure::Io("board path has no file name".into()))?;
    let copy = board_dir.join(name);
    let receipt = copy_board(i, &script, i.board_bytes, &copy, mask_web_mm, evidence, "board_copy")?;
    evidence["cleared_overrides"] = receipt["cleared"].clone();
    let project = i.board.with_extension("kicad_pro");
    evidence["project_sha256"] = if project.is_file() {
        let p = fs::read(&project).map_err(io)?;
        fs::write(copy.with_extension("kicad_pro"), &p).map_err(io)?;
        digest(&p).into()
    } else {
        serde_json::Value::Null
    };
    evidence["project"] =
        if project.is_file() { "copied beside the board" } else { "none: KiCad default severities" }.into();
    evidence["board_copy_sha256"] = digest(&fs::read(&copy).map_err(io)?).into();
    fs::write(copy.with_extension("kicad_dru"), rules).map_err(io)?;
    let board = drc(i.kicad, &copy, evidence, "board_run")?;
    Ok((selftest, board))
}

/// Write `copy` from `bytes` with pcbnew (`tools/fab_board_copy.py`): no local
/// clearance overrides, and the vendor's solder-mask web when the profile sets
/// one. pcbnew's default project files beside the copy are removed.
fn copy_board(
    i: &FabInputs,
    script: &Path,
    bytes: &[u8],
    copy: &Path,
    mask_web_mm: Option<f64>,
    evidence: &mut serde_json::Value,
    key: &str,
) -> Outcome<serde_json::Value> {
    let dir = copy.parent().ok_or_else(|| Failure::Io("copy has no directory".into()))?;
    let source = dir.join("source.kicad_pcb");
    fs::write(&source, bytes).map_err(io)?;
    let mut command = Command::new(i.python);
    command.arg(script).arg(&source).arg(copy);
    if let Some(web) = mask_web_mm {
        command.arg(web.to_string());
    }
    let child = command.output().map_err(io)?;
    fs::write(dir.join("board-copy.stderr"), &child.stderr).map_err(io)?;
    evidence[key] = serde_json::json!({"python": i.python, "returncode": child.status.code()});
    if !child.status.success() {
        let stderr = String::from_utf8_lossy(&child.stderr);
        return Err(Failure::Contract(format!("board copy failed: {stderr}")));
    }
    let receipt: serde_json::Value = serde_json::from_slice(&child.stdout)
        .map_err(|e| Failure::Contract(format!("board copy output: {e}")))?;
    evidence[key]["solder_mask_min_web_mm"] = receipt["solder_mask_min_web_mm"].clone();
    fs::remove_file(&source).map_err(io)?;
    for suffix in ["kicad_pro", "kicad_prl"] {
        let path = copy.with_extension(suffix);
        if path.exists() {
            fs::remove_file(path).map_err(io)?;
        }
    }
    Ok(receipt)
}

/// `kicad-cli pcb drc` on `board`, keeping the report and output beside it.
fn drc(kicad: &Path, board: &Path, evidence: &mut serde_json::Value, key: &str) -> Outcome<DrcReport> {
    let dir = board.parent().ok_or_else(|| Failure::Io("board copy has no directory".into()))?;
    let report_path = dir.join("drc.json");
    let flags = ["--severity-all", "--all-track-errors", "--format", "json", "--output"];
    let argv: Vec<String> = ["pcb", "drc"]
        .into_iter()
        .chain(flags)
        .map(String::from)
        .chain([report_path.to_string_lossy().into_owned(), board.to_string_lossy().into_owned()])
        .collect();
    let child = Command::new(kicad).args(&argv).output().map_err(io)?;
    fs::write(dir.join("drc.stdout"), &child.stdout).map_err(io)?;
    fs::write(dir.join("drc.stderr"), &child.stderr).map_err(io)?;
    evidence[key] = serde_json::json!({"argv": argv, "returncode": child.status.code()});
    if !child.status.success() {
        let stderr = String::from_utf8_lossy(&child.stderr);
        return Err(Failure::Contract(format!("fab DRC failed on {}: {stderr}", board.display())));
    }
    let bytes = fs::read(&report_path).map_err(io)?;
    evidence[key]["report_sha256"] = digest(&bytes).into();
    let text = std::str::from_utf8(&bytes).map_err(|e| Failure::Contract(e.to_string()))?;
    let report = native_reports::drc_report(text).map_err(Failure::Contract)?;
    if Path::new(&report.source).file_name() != board.file_name() {
        let wanted = board.display();
        return Err(Failure::Contract(format!("fab DRC report is for {}, not {wanted}", report.source)));
    }
    Ok(report)
}
