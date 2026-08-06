//! Wave 4 Phase 4 — regression slice: DRC ratchet comparison kernels.
//!
//! The ceiling-COMPARISON compute of `temper_placer/regression/drc_ratchet.py`
//! (pinned verbatim as the oracle `_drc_ratchet_py_oracle.py`, commit
//! `0a29f15e3`) migrated into `temper_drc-rs`:
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `ratchet_check` | `DrcRatchet._check_board` — aggregate deltas, per-type category failure detection (implicit-zero ceiling), pass/fail message composition |
//! | `detect_ceiling_raise` | `DrcRatchet.detect_ceiling_raise` — raise detection + `Ceiling-Approval:` trailer enforcement |
//!
//! Design boundaries (argued in-source; see `packages/temper-drc-rs/VERIFICATION.md`):
//!
//! - The DRC backends stay Python: the kicad-cli subprocess and the
//!   `temper_drc_rs.run_drc` board-dict builder are I/O/marshalling over
//!   surfaces outside this slice. The delegation module runs the backend and
//!   passes the measured counts + the ceiling values into `ratchet_check`.
//! - The ratchet CONSTANTS (`drc_ceiling.json`, the #575 ratchet gate) are
//!   read-only board-workstream territory — this migration only ports the
//!   comparison logic, which must not change what the ratchet reads or the
//!   gate's behavior.
//! - All message content is int/str/bool interpolation — no-format
//!   `str(float)` never appears — so the kernel composes the messages
//!   bit-identically.
//! - The per-type category loop preserves the oracle's `sorted(items())`
//!   order and its `if entry.<record> and current is not None` guard (an
//!   EMPTY allowed record suppresses the per-type dimension entirely).
//! - The kicad-cli version note is `.strip()`ped on the pass path (Python
//!   `str.strip` == Rust `str::trim` for the ASCII note) and kept verbatim
//!   (two-space indent) on the fail path — the oracle's exact asymmetry.
//!
//! pyo3 panic policy: every `#[pyfunction]` boundary relies on pyo3's default
//! `catch_unwind` (panics surface as `pyo3_runtime.PanicException`, never
//! across the boundary as UB) — R1g.

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods, PyList, PyModule};

// ---------------------------------------------------------------------------
// ratchet_check
// ---------------------------------------------------------------------------

/// One category that exceeded its ceiling (mirrors `DrcCategoryFailure`).
struct CatFailure {
    rule: String,
    count: i64,
    allowed: i64,
    is_new: bool,
    kind: &'static str,
    source: String,
}

impl CatFailure {
    fn delta(&self) -> i64 {
        self.count - self.allowed
    }
}

fn build_category_failures(
    sorted_current: &[(String, i64)],
    allowed: &[(String, i64)],
    kind: &'static str,
    source: &str,
) -> Vec<CatFailure> {
    let mut out = Vec::new();
    for (rule, count) in sorted_current {
        let allowed_count = allowed
            .iter()
            .find(|(r, _)| r == rule)
            .map(|(_, c)| *c)
            .unwrap_or(0);
        if *count > allowed_count {
            out.push(CatFailure {
                rule: rule.clone(),
                count: *count,
                allowed: allowed_count,
                is_new: !allowed.iter().any(|(r, _)| r == rule),
                kind,
                source: source.to_string(),
            });
        }
    }
    out
}

/// Render one per-type block, preserving the oracle's
/// ``new_failures + regressed_failures`` display order.
fn render_category_block(lines: &mut Vec<String>, label: &str, failures: &[CatFailure], kind: &str) {
    let block: Vec<&CatFailure> = failures.iter().filter(|c| c.kind == kind).collect();
    if block.is_empty() {
        return;
    }
    let new_failures: Vec<&CatFailure> = block.iter().copied().filter(|c| c.is_new).collect();
    let regressed: Vec<&CatFailure> = block.iter().copied().filter(|c| !c.is_new).collect();
    let n = block.len();
    let plural = if n == 1 { "y" } else { "ies" };
    // All failures in one block share a single backend, reported once per
    // block (see DrcCategoryFailure.source).
    let source = &block[0].source;
    lines.push(format!(
        "  per-type {label} (source: {source}): {n} categor{plural} over ceiling ({} new, {} regressed):",
        new_failures.len(),
        regressed.len()
    ));
    for c in new_failures.iter().chain(regressed.iter()) {
        let tag = if c.is_new { "NEW" } else { "   " };
        lines.push(format!(
            "    [{tag}] {} {} > {} (+{})",
            c.rule,
            c.count,
            c.allowed,
            c.delta()
        ));
    }
}

/// Full DRC-ratchet comparison for one board (verbatim port of
/// `DrcRatchet._check_board`'s comparison half). The delegation module runs
/// the DRC backend and passes the measured counts + ceiling values here.
///
/// Returns a dict with the `DrcRatchetResult` fields: `passed`, `board_id`,
/// `message`, `exit_code`, `violation_deltas`, `category_failures`,
/// `aggregate_error_delta`, `aggregate_warning_delta`, and the three
/// kicad-cli version fields.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn ratchet_check(
    py: Python<'_>,
    board_id: String,
    current_errors: i64,
    current_warnings: i64,
    error_ceiling: i64,
    warning_ceiling: i64,
    current_by_type: Option<Vec<(String, i64)>>,
    allowed_by_type: Vec<(String, i64)>,
    current_warnings_by_type: Option<Vec<(String, i64)>>,
    allowed_warnings_by_type: Vec<(String, i64)>,
    backend: String,
    version_mismatch: bool,
    running_version: Option<String>,
    expected_version: Option<String>,
) -> PyResult<Py<PyDict>> {
    // Per-type loops iterate sorted current rules (the oracle's
    // `sorted(current_by_type.items())`).
    let mut sorted_errors: Vec<(String, i64)> = current_by_type.unwrap_or_default();
    sorted_errors.sort();
    let mut sorted_warnings: Vec<(String, i64)> = current_warnings_by_type.unwrap_or_default();
    sorted_warnings.sort();

    // Category detection ONLY runs when the allowed record is non-empty AND
    // the backend supplied a breakdown (the oracle's `and` guard: an empty
    // record means the per-type dimension is not enforced).
    let mut category_failures: Vec<CatFailure> = Vec::new();
    if !allowed_by_type.is_empty() {
        category_failures.extend(build_category_failures(
            &sorted_errors,
            &allowed_by_type,
            "error",
            &backend,
        ));
    }
    if !allowed_warnings_by_type.is_empty() {
        category_failures.extend(build_category_failures(
            &sorted_warnings,
            &allowed_warnings_by_type,
            "warning",
            &backend,
        ));
    }

    let error_delta = current_errors - error_ceiling;
    let warning_delta = current_warnings - warning_ceiling;

    let mut aggregate_failures: Vec<String> = Vec::new();
    if error_delta > 0 {
        aggregate_failures.push(format!(
            "errors {current_errors} exceeds ceiling {error_ceiling} (+{error_delta})"
        ));
    }
    if warning_delta > 0 {
        aggregate_failures.push(format!(
            "warnings {current_warnings} exceeds ceiling {warning_ceiling} (+{warning_delta})"
        ));
    }

    let version_note = if version_mismatch {
        Some(format!(
            "  NOTE: kicad-cli version mismatch -- running {running}, ceiling measured with {expected} (numbers may not be directly comparable; see drc_ceiling.json provenance.tool_versions)",
            running = running_version.as_deref().unwrap_or_default(),
            expected = expected_version.as_deref().unwrap_or_default(),
        ))
    } else {
        None
    };

    let d = PyDict::new(py);
    d.set_item("board_id", &board_id)?;
    d.set_item("kicad_cli_version_running", running_version.clone().into_pyobject(py)?)?;
    d.set_item("kicad_cli_version_expected", expected_version.clone().into_pyobject(py)?)?;
    d.set_item("kicad_cli_version_mismatch", version_mismatch)?;

    if !aggregate_failures.is_empty() || !category_failures.is_empty() {
        // Failing run: every exceeded dimension reported in one shot (the
        // aggregate must never mask the per-type breakdown).
        let mut lines: Vec<String> = vec![format!("{board_id}: DRC FAIL")];
        if let Some(note) = &version_note {
            lines.push(note.clone());
        }
        for failure in &aggregate_failures {
            lines.push(format!("  aggregate {failure}"));
        }
        render_category_block(&mut lines, "errors", &category_failures, "error");
        render_category_block(&mut lines, "warnings", &category_failures, "warning");

        d.set_item("passed", false)?;
        d.set_item("message", lines.join("\n"))?;
        d.set_item("exit_code", 1)?;

        let deltas = PyDict::new(py);
        for c in &category_failures {
            deltas.set_item(&c.rule, c.delta())?;
        }
        d.set_item("violation_deltas", deltas)?;

        let cats = PyList::empty(py);
        for c in &category_failures {
            let cd = PyDict::new(py);
            cd.set_item("rule", &c.rule)?;
            cd.set_item("count", c.count)?;
            cd.set_item("allowed", c.allowed)?;
            cd.set_item("is_new", c.is_new)?;
            cd.set_item("kind", c.kind)?;
            cd.set_item("source", &c.source)?;
            cd.set_item("delta", c.delta())?;
            cats.append(cd)?;
        }
        d.set_item("category_failures", cats)?;
        d.set_item("aggregate_error_delta", error_delta.max(0))?;
        d.set_item("aggregate_warning_delta", warning_delta.max(0))?;
    } else {
        // Passing run: slack note + the oracle's pass-path version note
        // (`.strip()`ped — the two-space indent is removed).
        let slack = error_ceiling - current_errors;
        let slack_note = if slack > 0 {
            format!(
                " [{slack} error(s) of unratcheted slack -- lower error_ceiling to {current_errors} to lock this in]"
            )
        } else {
            String::new()
        };
        let mut pass_message = format!(
            "{board_id}: DRC {current_errors}/{error_ceiling} errors, {current_warnings}/{warning_ceiling} warnings within ceiling{slack_note}"
        );
        if let Some(note) = &version_note {
            pass_message.push('\n');
            pass_message.push_str(note.trim());
        }
        d.set_item("passed", true)?;
        d.set_item("message", pass_message)?;
        d.set_item("exit_code", 0)?;
        d.set_item("violation_deltas", PyDict::new(py))?;
        d.set_item("category_failures", PyList::empty(py))?;
        d.set_item("aggregate_error_delta", 0)?;
        d.set_item("aggregate_warning_delta", 0)?;
    }
    Ok(d.into())
}

// ---------------------------------------------------------------------------
// detect_ceiling_raise
// ---------------------------------------------------------------------------

/// One board's ceiling record, marshalled from the ceiling file's ``boards``
/// entry: `(board_id, error_ceiling, warning_ceiling, violations_by_type,
/// warnings_by_type)`.
type CeilingEntryRepr = (String, i64, i64, Vec<(String, i64)>, Vec<(String, i64)>);

/// Detect whether a ceiling file change raised any ceiling without approval
/// (verbatim port of `DrcRatchet.detect_ceiling_raise`). Returns `None` when
/// no unapproved raise exists, else a `{passed, board_id, message,
/// exit_code: 2}` dict. The per-type raise detection includes a rule absent
/// from the old record entirely (a raise from its implicit ceiling of 0).
#[pyfunction]
fn detect_ceiling_raise(
    py: Python<'_>,
    old_entries: Vec<CeilingEntryRepr>,
    new_entries: Vec<CeilingEntryRepr>,
    commit_message: String,
) -> PyResult<Py<PyAny>> {
    let old_map: HashMap<&str, &CeilingEntryRepr> =
        old_entries.iter().map(|e| (e.0.as_str(), e)).collect();

    for new_entry in &new_entries {
        let board_id = &new_entry.0;
        let Some(old_entry) = old_map.get(board_id.as_str()) else {
            // A board absent from the old record cannot be a raise.
            continue;
        };
        let mut reasons: Vec<String> = Vec::new();

        let old_errors = old_entry.1;
        let new_errors = new_entry.1;
        if new_errors > old_errors {
            reasons.push(format!("error_ceiling {old_errors} -> {new_errors}"));
        }
        let old_warnings = old_entry.2;
        let new_warnings = new_entry.2;
        if new_warnings > old_warnings {
            reasons.push(format!("warning_ceiling {old_warnings} -> {new_warnings}"));
        }

        let mut new_vbt: Vec<(String, i64)> = new_entry.3.clone();
        new_vbt.sort();
        for (rule, new_count) in &new_vbt {
            let old_count = old_entry
                .3
                .iter()
                .find(|(r, _)| r == rule)
                .map(|(_, c)| *c)
                .unwrap_or(0);
            if *new_count > old_count {
                reasons.push(format!("violations_by_type[{rule}] {old_count} -> {new_count}"));
            }
        }

        let mut new_wbt: Vec<(String, i64)> = new_entry.4.clone();
        new_wbt.sort();
        for (rule, new_count) in &new_wbt {
            let old_count = old_entry
                .4
                .iter()
                .find(|(r, _)| r == rule)
                .map(|(_, c)| *c)
                .unwrap_or(0);
            if *new_count > old_count {
                reasons.push(format!("warnings_by_type[{rule}] {old_count} -> {new_count}"));
            }
        }

        if !reasons.is_empty() && !commit_message.contains("Ceiling-Approval:") {
            let d = PyDict::new(py);
            d.set_item("passed", false)?;
            d.set_item("board_id", board_id)?;
            d.set_item(
                "message",
                format!(
                    "Ceiling increase ({}) requires explicit approval.",
                    reasons.join("; ")
                ),
            )?;
            d.set_item("exit_code", 2)?;
            return Ok(d.into());
        }
    }
    Ok(py.None())
}

/// Register the ratchet kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(ratchet_check, m)?)?;
    m.add_function(wrap_pyfunction!(detect_ceiling_raise, m)?)?;
    Ok(())
}
