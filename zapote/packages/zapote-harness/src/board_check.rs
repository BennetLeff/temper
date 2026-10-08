//! `zapote-check`: the board-generic checks on any saved KiCad board.
//!
//! Runs the physical stackup gate, KiCad ERC/DRC (one finding per
//! violation) and the P2 manufacturing rules under a vendor fab profile,
//! keeps every input, report and receipt in a new output directory, and
//! writes `report.json`. Unit electrical checks are not included.
use crate::runner::{self, NativeCommand};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
};
use zapote_core::{CheckReport, Status};

pub struct BoardCheck {
    pub board: PathBuf,
    /// Defaults to the board's sibling `.kicad_sch`.
    pub schematic: Option<PathBuf>,
    pub profile: PathBuf,
    /// The assembly process the board is built for (e.g. "reflow"). Without
    /// it the manufacturing report keeps an assembly gap, so the best
    /// possible result is indeterminate (exit 2).
    pub assembly: Option<String>,
    pub kicad_cli: PathBuf,
    pub python: PathBuf,
    /// Must not exist yet: evidence is never overwritten.
    pub output: PathBuf,
}

#[derive(Serialize)]
pub struct NamedCheck {
    pub name: String,
    pub report: CheckReport,
}

#[derive(Serialize)]
pub struct BoardCheckReport {
    pub schema: &'static str,
    pub board: PathBuf,
    pub board_sha256: String,
    pub schematic: PathBuf,
    pub profile: serde_json::Value,
    pub status: Status,
    pub checks: Vec<NamedCheck>,
    pub native_commands: Vec<NativeCommand>,
    pub scope: &'static str,
}

impl BoardCheckReport {
    pub fn new(
        board: PathBuf,
        board_sha256: String,
        schematic: PathBuf,
        profile: serde_json::Value,
        checks: Vec<NamedCheck>,
    ) -> Self {
        let status = if checks.iter().any(|c| c.report.status == Status::Fail) {
            Status::Fail
        } else if checks.iter().any(|c| c.report.status == Status::Indeterminate) {
            Status::Indeterminate
        } else {
            Status::Pass
        };
        Self {
            schema: "zapote.board-check.v1",
            board,
            board_sha256,
            schematic,
            profile,
            status,
            checks,
            native_commands: vec![],
            scope: "stackup, KiCad ERC/DRC and P2 manufacturing under the named fab profile; unit electrical, current, thermal and assembly checks are not included",
        }
    }
}

/// 0 pass, 1 any failure, 2 nothing failed but something was indeterminate or missing.
pub fn exit_code(r: &BoardCheckReport) -> u8 {
    match r.status {
        Status::Pass => 0,
        Status::Fail => 1,
        Status::Indeterminate => 2,
    }
}

pub fn run(c: &BoardCheck) -> Result<BoardCheckReport, String> {
    fs::create_dir(&c.output)
        .map_err(|e| format!("output directory {} must be new: {e}", c.output.display()))?;
    let board = c.board.canonicalize().map_err(|e| format!("{}: {e}", c.board.display()))?;
    let schematic = match &c.schematic {
        Some(s) => s.clone(),
        None => board.with_extension("kicad_sch"),
    };
    let schematic = schematic
        .canonicalize()
        .map_err(|e| format!("schematic {}: {e} (pass --schematic)", schematic.display()))?;
    let bytes = fs::read(&board).map_err(|e| e.to_string())?;
    let text = std::str::from_utf8(&bytes).map_err(|_| "KiCad board must be UTF-8".to_string())?;
    let stackup = zapote_drc::stackup::validate_board(text);
    let (native, commands) = runner::native_check(&schematic, &board, &c.output.join("native"), &c.kicad_cli)?;
    let dfm = runner::dfm_check(
        &board,
        &c.output.join("manufacturing"),
        &c.python,
        Some(&c.profile),
        c.assembly.as_deref(),
    )?;
    if runner::digest(&fs::read(&board).map_err(|e| e.to_string())?) != runner::digest(&bytes) {
        return Err("board changed while it was being checked".into());
    }
    let mut report = BoardCheckReport::new(
        board,
        runner::digest(&bytes),
        schematic,
        dfm.profile.clone().unwrap_or(serde_json::Value::Null),
        vec![
            NamedCheck { name: "stackup".into(), report: stackup },
            NamedCheck { name: "native".into(), report: native },
            NamedCheck { name: "manufacturing".into(), report: dfm.report },
        ],
    );
    report.native_commands = commands;
    fs::write(
        c.output.join("report.json"),
        serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    fs::write(c.output.join("summary.txt"), summary(&report)).map_err(|e| e.to_string())?;
    Ok(report)
}

/// Human-readable result: failing findings grouped by rule, with object and
/// actual/required values, then indeterminate counts and coverage gaps.
pub fn summary(r: &BoardCheckReport) -> String {
    let mut out = format!(
        "{} {} (profile {})\n",
        status_word(r.status),
        r.board.display(),
        r.profile["name"].as_str().unwrap_or("none")
    );
    for check in &r.checks {
        let rep = &check.report;
        out += &format!("\n[{}] {}\n", check.name, status_word(rep.status));
        let mut failing: BTreeMap<&str, Vec<&zapote_core::Finding>> = BTreeMap::new();
        for f in rep.findings.iter().filter(|f| f.status == Status::Fail) {
            failing.entry(&f.rule).or_default().push(f);
        }
        for (rule, findings) in failing {
            out += &format!("  {rule} ({})\n", findings.len());
            for f in findings {
                let values = match (&f.actual, &f.required) {
                    (Some(a), Some(q)) => format!(" [actual {a}, required {q}]"),
                    (Some(a), None) => format!(" [actual {a}]"),
                    _ => String::new(),
                };
                out += &format!("    {}: {}{values}\n", f.object, f.message);
            }
        }
        let undecided = rep.findings.iter().filter(|f| f.status == Status::Indeterminate).count();
        if undecided > 0 {
            out += &format!("  indeterminate: {undecided}\n");
        }
        for gap in &rep.coverage_gaps {
            out += &format!("  gap: {gap}\n");
        }
    }
    out
}

fn status_word(s: Status) -> &'static str {
    match s {
        Status::Pass => "PASS",
        Status::Fail => "FAIL",
        Status::Indeterminate => "INDETERMINATE",
    }
}
