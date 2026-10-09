//! The fab pass: vendor limits that KiCad's own DRC measures (copper
//! clearance, hole to copper per hole type, silkscreen text size).
//!
//! KiCad runs on a copy of the board, with its `.kicad_pro` (so the
//! designer's severities and exclusions still apply) and a `.kicad_dru`
//! holding only the profile's `zapote fab` rules. When several custom rules
//! match, KiCad applies the last even if it is looser (measured on 10.0.4),
//! so vendor rules are never mixed into the board's own rules; the input
//! board and its rules are untouched and stay with the native pass.
//!
//! KiCad also ignores a malformed `.kicad_dru` without an error. The same
//! rules therefore run first on a committed self-test board that breaks every
//! one of them by a wide margin; a rule that does not fire there is reported
//! as a coverage gap instead of as a pass.
use crate::native_reports::{self, DrcReport};
use crate::runner::digest;
use std::{collections::BTreeSet, fs, path::Path, process::Command};
use zapote_core::{CheckReport, Finding};
use zapote_drc::{fab_rules::kicad_rules, manufacturing::FabricationLimits};

type Result<T> = std::result::Result<T, String>;

/// Built by `zapote/tools/make_fab_selftest_board.py`.
const SELFTEST_BOARD: &str = include_str!("../fixtures/fab_selftest.kicad_pcb");

/// One emitted rule: its name and the KiCad constraint (and violation type) it sets.
#[derive(Clone, Debug)]
pub struct FabRule {
    pub name: String,
    pub constraint: String,
}

/// The rules in a `.kicad_dru` written by [`kicad_rules`].
pub fn rule_set(rules: &str) -> Vec<FabRule> {
    rules
        .lines()
        .filter_map(|line| {
            let name = line.strip_prefix("(rule \"")?.split('"').next()?;
            let constraint = line.split("(constraint ").nth(1)?.split_whitespace().next()?;
            Some(FabRule { name: name.into(), constraint: constraint.into() })
        })
        .collect()
}

/// The rule KiCad attributes a violation to: `(rule '<name>' ...)`.
fn attributed<'a>(description: &str, rules: &'a [FabRule]) -> Option<&'a FabRule> {
    let name = description.split("(rule '").nth(1)?.split('\'').next()?;
    rules.iter().find(|r| r.name == name)
}

/// Judge the board's report. Only violations KiCad attributes to a fab rule
/// count; board-setup and netclass findings belong to the native pass.
pub fn evaluate(rules: &[FabRule], selftest: &DrcReport, board: &DrcReport) -> CheckReport {
    let fired: BTreeSet<&str> = selftest
        .violations
        .iter()
        .filter_map(|v| attributed(&v.description, rules))
        .map(|r| r.name.as_str())
        .collect();
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let mut checked = BTreeSet::new();
    for rule in rules {
        let id = format!("FAB.{}", rule.constraint);
        checked.insert(id.clone());
        let hits: Vec<_> = board
            .violations
            .iter()
            .filter(|v| attributed(&v.description, rules).is_some_and(|r| r.name == rule.name))
            .collect();
        if !hits.is_empty() {
            findings.extend(hits.iter().map(|v| native_reports::finding(v, &format!("FAB.{}", v.kind))));
        } else if !fired.contains(rule.name.as_str()) {
            gaps.push(format!(
                "KiCad did not apply rule '{}' on the self-test board, so no result on this board counts",
                rule.name
            ));
        } else if board.ignored_checks.iter().any(|k| *k == rule.constraint) {
            gaps.push(format!(
                "the board's project ignores {} checks, so rule '{}' cannot report",
                rule.constraint, rule.name
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
    /// Rules hash, KiCad version, project and per-run command receipts.
    pub evidence: serde_json::Value,
}

/// Run the fab pass into `out` (which must not exist). `None` when the
/// profile sets no limit this pass applies: the check is then absent, not passed.
pub fn fab_check(
    board: &Path,
    out: &Path,
    kicad: &Path,
    limits: &FabricationLimits,
) -> Result<Option<FabCheck>> {
    let Some(rules) = kicad_rules(limits) else {
        return Ok(None);
    };
    let set = rule_set(&rules);
    fs::create_dir(out).map_err(|e| format!("fab output {} must be new: {e}", out.display()))?;
    let version = Command::new(kicad).arg("--version").output().map_err(|e| e.to_string())?;
    if !version.status.success() {
        return Err("kicad-cli version probe failed".into());
    }
    let version = String::from_utf8_lossy(&version.stdout).trim().to_owned();

    // Self-test board, with no project: KiCad's default severities.
    let selftest_dir = out.join("self-test");
    fs::create_dir(&selftest_dir).map_err(|e| e.to_string())?;
    let selftest_board = selftest_dir.join("fab_selftest.kicad_pcb");
    fs::write(&selftest_board, SELFTEST_BOARD).map_err(|e| e.to_string())?;
    fs::write(selftest_board.with_extension("kicad_dru"), &rules).map_err(|e| e.to_string())?;
    let selftest = drc(kicad, &selftest_board)?;

    let board_dir = out.join("board");
    fs::create_dir(&board_dir).map_err(|e| e.to_string())?;
    let copy = board_dir.join(board.file_name().ok_or("board path has no file name")?);
    let bytes = fs::read(board).map_err(|e| format!("{}: {e}", board.display()))?;
    fs::write(&copy, &bytes).map_err(|e| e.to_string())?;
    let project = board.with_extension("kicad_pro");
    let project_sha256 = if project.is_file() {
        let p = fs::read(&project).map_err(|e| e.to_string())?;
        fs::write(copy.with_extension("kicad_pro"), &p).map_err(|e| e.to_string())?;
        Some(digest(&p))
    } else {
        None
    };
    fs::write(copy.with_extension("kicad_dru"), &rules).map_err(|e| e.to_string())?;
    let result = drc(kicad, &copy)?;

    Ok(Some(FabCheck {
        report: evaluate(&set, &selftest.report, &result.report),
        evidence: serde_json::json!({
            "rules_sha256": digest(rules.as_bytes()),
            "rules": set.iter().map(|r| &r.name).collect::<Vec<_>>(),
            "kicad_version": version,
            "board_sha256": digest(&bytes),
            "project_sha256": project_sha256,
            "project": if project_sha256.is_some() { "copied beside the board" } else { "none: KiCad default severities" },
            "self_test": selftest.receipt,
            "board_run": result.receipt,
        }),
    }))
}

struct DrcRun {
    report: DrcReport,
    receipt: serde_json::Value,
}

/// `kicad-cli pcb drc` on `board`, keeping the report and output beside it.
fn drc(kicad: &Path, board: &Path) -> Result<DrcRun> {
    let dir = board.parent().ok_or("board copy has no directory")?;
    let report_path = dir.join("drc.json");
    let argv: Vec<String> = [
        "pcb",
        "drc",
        "--severity-all",
        "--all-track-errors",
        "--format",
        "json",
        "--output",
    ]
    .into_iter()
    .map(String::from)
    .chain([report_path.to_string_lossy().into_owned(), board.to_string_lossy().into_owned()])
    .collect();
    let child = Command::new(kicad).args(&argv).output().map_err(|e| e.to_string())?;
    fs::write(dir.join("drc.stdout"), &child.stdout).map_err(|e| e.to_string())?;
    fs::write(dir.join("drc.stderr"), &child.stderr).map_err(|e| e.to_string())?;
    if !child.status.success() {
        return Err(format!("fab DRC failed on {}: {}", board.display(), String::from_utf8_lossy(&child.stderr)));
    }
    let bytes = fs::read(&report_path).map_err(|e| format!("{}: {e}", report_path.display()))?;
    let report = native_reports::drc_report(std::str::from_utf8(&bytes).map_err(|e| e.to_string())?)?;
    if Path::new(&report.source).file_name() != board.file_name() {
        return Err(format!("fab DRC report is for {}, not {}", report.source, board.display()));
    }
    Ok(DrcRun {
        report,
        receipt: serde_json::json!({
            "argv": argv,
            "returncode": child.status.code(),
            "report_sha256": digest(&bytes),
        }),
    })
}
