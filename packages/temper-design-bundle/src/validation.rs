//! Validation decision kernels — Wave 4 Phase 4 (the validation remainder).
//!
//! Python references (pinned VERBATIM in
//! `packages/temper-placer/tests/validation/_<mod>_py_oracle.py` at commit
//! `6290942be`; the differential suites
//! `tests/validation/test_<mod>_rust_differential.py` are the TDD oracles
//! for this file):
//!
//! | Rust kernel | Python origin | Home crate |
//! |---|---|---|
//! | `zones_overlap` / `preflight_zones_fit` / `preflight_unassigned` / `preflight_impossible` | `validation/preflight.py` | temper-design-bundle |
//! | `parse_design_netlist` / `reconcile` | `validation/netlist_reconciliation.py` | temper-design-bundle |
//! | `canonical_angle` / `angle_diff` / `pad_key` / `check_footprint_geometry` | `validation/placement_roundtrip.py` | temper-design-bundle |
//! | `prereg_temporal_gate` | `validation/prereg/schema.py` | temper-design-bundle |
//!
//! The `rdl_sum` RDL kernel of `validation/human_reference_extractor.py`
//! lives in `temper-drc-rs` (its trace-kernel family) — see that crate's
//! `validation.rs`.
//!
//! # The pydantic / I/O boundary (what stays Python, argued in-source)
//!
//! - **pydantic is not reimplemented.** `prereg/schema.py` keeps its models
//!   and `model_validator` call-backs (config-loader precedent, Phase 3
//!   candidate 5); the temporal-gate CONTROL FLOW — the naive-to-UTC
//!   normalization decision, the `created > battery` comparison (via
//!   Python's own `>` operator, called back across the boundary), and the
//!   ValueError construction — is Rust (`prereg_temporal_gate`).
//! - **File I/O stays Python.** `parse_design_netlist`'s file read and the
//!   placement-roundtrip's KTD4 re-parse (`parse_kicad_pcb_v6` +
//!   `KiBoard.from_file`) stay in the delegation modules; the Rust kernels
//!   operate on text / already-extracted geometry.
//! - **kiutils-tree extraction stays Python.** The placement-roundtrip
//!   kernel receives *world* pad positions computed by the shared
//!   `kicad_transform` primitives (both arms call the same Python, so the
//!   geometry is identical by construction) plus the written anchors/angles
//!   from the kiutils tree.
//! - **The `_get_footprint_reference` consumer relationship (#723) is
//!   preserved:** `placement_roundtrip.py` keeps its import and call site
//!   verbatim.
//!
//! # Numerics and formatting parity (all pinned by the differentials)
//!
//! - **CPython float modulo is not `f64::rem_euclid`.** CPython's
//!   `float_rem` maps an exact-multiple result (±0.0) to
//!   `copysign(0.0, fy)` — so `-720.0 % 360.0` is `+0.0` while
//!   `(-720.0_f64).rem_euclid(360.0)` is `-0.0` (measured; the `.hex()`
//!   comparison would catch it). `crate::host_math::py_float_mod`
//!   transcribes `float_rem` exactly (fmod + sign-correction + the
//!   `copysign` zero branch).
//! - **Fixed-point formatting** (`{:.1}`) matches CPython `:.1f`
//!   bit-for-bit on this platform (measured 21/21 incl. half-way cases
//!   like `50.125` → `50.1` and `2.35` → `2.4`; same claim as the
//!   temper-drc-rs `tht_hole_collisions` `:.3f` measurement). The
//!   zone-fit reason strings are therefore built here. The two messages
//!   that interpolate a NO-FORMAT `str(float)` (ZONE_003's suggestion,
//!   ZONE_005's message) stay Python — Rust `Display` renders `10.0` as
//!   `10`.
//! - **`!r` interpolation.** The reconciliation error strings carry
//!   `!r` reprs of strings; `py_str_repr` below transcribes CPython's
//!   `unicode_repr` quote-selection and escaping (the differential asserts
//!   the error strings byte-identically).
//! - **Iteration order.** Every `sorted(...)` below is the oracle's OWN
//!   sort (the reconcile findings iterate `sorted(design_by_path)` etc.),
//!   not a stabilisation of a set/dict fold — the one hash-randomised
//!   surface (the board-net `set` node lists) is passed as an unordered
//!   list and compared as a set on both sides, exactly as the oracle's
//!   `set != set` does.
//! - **JSON string tokens.** The design-netlist tokenizer decodes
//!   quote-leading tokens with `serde_json::from_str`, matching CPython
//!   `json.loads` on every token the netlist compiler emits (escapes are
//!   JSON-valid: `\"`, `\\`, `\n`, `\t`). For MALFORMED quoted tokens
//!   outside the compiler's domain the two json implementations raise
//!   different error classes/texts (`JSONDecodeError` vs a `PyValueError`
//!   carrying serde_json's text, which the shim re-wraps as the gate
//!   error) — both fail closed, neither is in the differential's domain;
//!   recorded in VERIFICATION.md, not chased.
//!
//! R1h: **N/A — not a physics-gated surface.** These kernels move
//! decision/string compute; none gates on a physics quantity, so the R24
//! discipline (soundness proof / BMC / post-solve audit) does not apply.
//!
//! pyo3 panic policy: every `#[pyfunction]` boundary is wrapped by pyo3's
//! default `catch_unwind` (panics surface as `pyo3_runtime.PanicException`,
//! never across the boundary as UB) — R1g. No `unwrap`/`expect` outside
//! `#[cfg(test)]`.

use std::collections::HashMap;

use pyo3::exceptions::{PyIndexError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

// ---------------------------------------------------------------------------
// Type aliases (keeps the pyfunction signatures under clippy's
// type_complexity threshold)
// ---------------------------------------------------------------------------

/// A zone's `(x_min, y_min, x_max, y_max)` bounds (and a component's
/// `(width, height)` where arity matches).
type Bounds = (f64, f64, f64, f64);

/// A design-netlist parse result: `(components, nets, duplicate_refs)`.
type ParsedDesignNetlist = (
    Vec<(String, String)>,
    Vec<(String, Vec<(String, String)>)>,
    Vec<(String, String, String)>,
);

/// A reconcile result: `(findings, design_components, board_components,
/// matched_paths, design_nets_nonempty, board_nets)`.
type ReconcileResult = (Vec<Py<PyDict>>, usize, usize, usize, usize, usize);

/// One written-pad geometry record `(key, x, y, angle)` — `None` entries
/// mean the pad has no `(at ...)` position.
type WrittenPad = (String, Option<f64>, Option<f64>, Option<f64>);

// ---------------------------------------------------------------------------
// CPython-semantics helpers
// ---------------------------------------------------------------------------

// `py_float_mod` moved to `crate::host_math` (2026-08-07, Wave 4 Phase 3
// `write_board_geometry.rs`) — it needed the exact same CPython `float %`
// zero-sign transcription this module already carried, and a second private
// copy would have been the third independently-typed instance of this
// formula in the crate. See `host_math.rs`'s doc comment on `py_float_mod`.
use crate::host_math::py_float_mod;

/// CPython's `repr()` of a str — the `!r` interpolation used by the
/// reconciliation error strings. Quote rule (CPython `unicode_repr`):
/// single quotes by default, double quotes when the string contains `'`
/// but not `"`. Escapes: the chosen quote, backslash, `\n`/`\t`/`\r`, and
/// `\xNN` (lowercase hex) for other control chars < 0x20 plus 0x7f.
/// Non-ASCII printable chars are emitted literally (the netlist domain is
/// ASCII; the oracle's repr does the same).
fn py_str_repr(s: &str) -> String {
    let use_double = s.contains('\'') && !s.contains('"');
    let quote = if use_double { '"' } else { '\'' };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            c if c == quote => {
                out.push('\\');
                out.push(quote);
            }
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            '\r' => out.push_str("\\r"),
            c if (c as u32) < 0x20 || (c as u32) == 0x7f => {
                out.push_str(&format!("\\x{:02x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// A float leaf as a Python float (`Py<PyAny>`).
fn py_float(py: Python<'_>, v: f64) -> PyResult<Py<PyAny>> {
    Ok(v.into_pyobject(py)?.unbind().into_any())
}

/// A 2-float pair as a Python tuple (`Py<PyAny>`).
fn py_tuple2(py: Python<'_>, a: f64, b: f64) -> PyResult<Py<PyAny>> {
    Ok(PyTuple::new(py, [a, b])?.unbind().into_any())
}

// ---------------------------------------------------------------------------
// preflight._zones_overlap
// ---------------------------------------------------------------------------

/// AABB zone-overlap predicate (verbatim port of
/// `preflight._zones_overlap`): no overlap iff one is fully left/right of
/// the other or fully above/below (edge-touch is NOT overlap).
#[pyfunction]
fn zones_overlap(a: Bounds, b: Bounds) -> bool {
    let (x1_min, y1_min, x1_max, y1_max) = a;
    let (x2_min, y2_min, x2_max, y2_max) = b;
    if x1_max <= x2_min || x2_max <= x1_min {
        return false;
    }
    !(y1_max <= y2_min || y2_max <= y1_min)
}

// ---------------------------------------------------------------------------
// preflight.check_zones_fit_on_board — the decision kernel
// ---------------------------------------------------------------------------

/// The zone-fit decision compute of `preflight.check_zones_fit_on_board`:
/// the four outside-reason checks (reason strings with `:.1f` formatting)
/// and the ordered-pair overlap enumeration. Returns `(passed, outside,
/// overlaps)` where `outside` is `(zone_name, reasons)` in zone order and
/// `overlaps` is `(zone_a, zone_b)` in the oracle's `enumerate`-pair order.
///
/// The shim assembles ZONE_003 (its suggestion interpolates no-format
/// floats) and ZONE_005 (no-format floats) messages Python-side; the
/// ZONE_004 message/suggestion are static text built Python-side from the
/// returned pair names.
/// A zone-fit result: `(passed, outside, overlaps)` where `outside` is
/// `(zone_name, reasons)` in zone order and `overlaps` is `(zone_a,
/// zone_b)` in the oracle's `enumerate`-pair order.
type ZonesFitResult = (bool, Vec<(String, Vec<String>)>, Vec<(String, String)>);

#[pyfunction]
fn preflight_zones_fit(
    zones: Vec<(String, Bounds)>,
    board_w: f64,
    board_h: f64,
) -> ZonesFitResult {
    let mut outside: Vec<(String, Vec<String>)> = Vec::new();
    for (name, (x_min, y_min, x_max, y_max)) in &zones {
        let mut reasons = Vec::new();
        if *x_min < 0.0 {
            reasons.push(format!("x_min={x_min:.1} < 0"));
        }
        if *y_min < 0.0 {
            reasons.push(format!("y_min={y_min:.1} < 0"));
        }
        if *x_max > board_w {
            reasons.push(format!("x_max={x_max:.1} > board_width={board_w:.1}"));
        }
        if *y_max > board_h {
            reasons.push(format!("y_max={y_max:.1} > board_height={board_h:.1}"));
        }
        if !reasons.is_empty() {
            outside.push((name.clone(), reasons));
        }
    }
    if !outside.is_empty() {
        // The oracle returns immediately with only the ZONE_003 issues —
        // the overlap pass is skipped entirely.
        return (false, outside, Vec::new());
    }
    let mut overlaps = Vec::new();
    for i in 0..zones.len() {
        let (name_a, bounds_a) = &zones[i];
        for (name_b, bounds_b) in &zones[i + 1..] {
            if zones_overlap(*bounds_a, *bounds_b) {
                overlaps.push((name_a.clone(), name_b.clone()));
            }
        }
    }
    (true, outside, overlaps)
}

// ---------------------------------------------------------------------------
// preflight.check_components_have_zones — the set-arithmetic kernel
// ---------------------------------------------------------------------------

/// The have-zones set arithmetic of `preflight.check_components_have_zones`:
/// `unassigned = netlist - assigned - fixed`, the sort/truncate suggestion
/// construction, and the severity/`passed` decision. Returns `(passed,
/// issues)` where each issue is a dict `{severity, code, message,
/// suggestion, components, details}` (all text is Rust-built — no
/// no-format float interpolation in this kernel).
#[pyfunction]
#[pyo3(signature = (netlist_refs, assigned_refs, fixed_refs, require_all=false))]
fn preflight_unassigned(
    py: Python<'_>,
    netlist_refs: Vec<String>,
    assigned_refs: Vec<String>,
    fixed_refs: Vec<String>,
    require_all: bool,
) -> PyResult<(bool, Vec<Py<PyDict>>)> {
    let netlist_set: std::collections::HashSet<&str> =
        netlist_refs.iter().map(String::as_str).collect();
    let assigned_set: std::collections::HashSet<&str> =
        assigned_refs.iter().map(String::as_str).collect();
    let fixed_set: std::collections::HashSet<&str> =
        fixed_refs.iter().map(String::as_str).collect();

    let mut unassigned: Vec<&str> = netlist_set
        .iter()
        .copied()
        .filter(|r| !assigned_set.contains(r) && !fixed_set.contains(r))
        .collect();
    unassigned.sort_unstable();

    let (issues, passed) = if unassigned.is_empty() {
        let issues = vec![issue_dict(
            py,
            "INFO",
            "ZONE_002",
            // The oracle's message interpolates ``len(netlist_refs)`` where
            // netlist_refs is the SET ``{c.ref for c in netlist.components}``
            // — duplicates collapse, so it is the unique-ref count.
            &format!(
                "All {} components have zone assignments",
                netlist_set.len()
            ),
            "",
            Vec::new(),
            PyDict::new(py),
        )?];
        (issues, true)
    } else {
        let severity = if require_all { "ERROR" } else { "WARNING" };
        let head: Vec<&str> = unassigned.iter().take(10).copied().collect();
        let mut suggestion = format!(
            "Add zone assignments in constraints.yaml under 'zone_assignments' \
             or add components to zone 'components' list. Unassigned: {}",
            head.join(", ")
        );
        if unassigned.len() > 10 {
            suggestion.push_str(&format!(" and {} more...", unassigned.len() - 10));
        }
        let details = PyDict::new(py);
        details.set_item("unassigned_count", unassigned.len())?;
        let issues = vec![issue_dict(
            py,
            severity,
            "ZONE_001",
            &format!("{} components have no zone assignment", unassigned.len()),
            &suggestion,
            unassigned.iter().map(|s| (*s).to_string()).collect(),
            details,
        )?];
        // passed = not require_all if unassigned else True
        (issues, !require_all)
    };
    Ok((passed, issues))
}

// ---------------------------------------------------------------------------
// preflight.check_impossible_constraints — the bounds/set kernel
// ---------------------------------------------------------------------------

/// The impossible-constraints decision compute of
/// `preflight.check_impossible_constraints`: the zone-fit (both
/// orientations), missing-component, and missing-zone checks, in the
/// oracle's exact finding order (001s, then 002s, then 003s, 004s, 005s,
/// then 006 iff no ERROR). Returns `(passed, issues)` with dict-shaped
/// issues as in `preflight_unassigned`.
#[pyfunction]
fn preflight_impossible(
    py: Python<'_>,
    components: Vec<(String, f64, f64)>,
    zones: Vec<(String, Bounds)>,
    assignments: Vec<(String, String)>,
    groups: Vec<(String, String, Vec<String>)>,
    thermals: Vec<Vec<String>>,
) -> PyResult<(bool, Vec<Py<PyDict>>)> {
    // {c.ref: c.bounds for c in netlist.components} — last duplicate wins.
    let mut comp_bounds: HashMap<&str, (f64, f64)> = HashMap::new();
    for (ref_, w, h) in &components {
        comp_bounds.insert(ref_.as_str(), (*w, *h));
    }
    let mut zone_bounds: HashMap<&str, Bounds> = HashMap::new();
    for (name, bounds) in &zones {
        zone_bounds.insert(name.as_str(), *bounds);
    }

    let mut issues: Vec<Py<PyDict>> = Vec::new();
    #[allow(clippy::type_complexity)]
    let mut too_large: Vec<(String, String, (f64, f64), (f64, f64))> = Vec::new();

    for (ref_, zone_name) in &assignments {
        let Some(&(comp_w, comp_h)) = comp_bounds.get(ref_.as_str()) else {
            continue; // component not in netlist, skip
        };
        let Some(&(z_x_min, z_y_min, z_x_max, z_y_max)) = zone_bounds.get(zone_name.as_str())
        else {
            issues.push(issue_dict(
                py,
                "ERROR",
                "CONSTRAINT_001",
                &format!("Component '{ref_}' assigned to non-existent zone '{zone_name}'"),
                &format!("Either create zone '{zone_name}' or assign '{ref_}' to an existing zone."),
                vec![ref_.clone()],
                PyDict::new(py),
            )?);
            continue;
        };
        let zone_w = z_x_max - z_x_min;
        let zone_h = z_y_max - z_y_min;
        let fits_normal = comp_w <= zone_w && comp_h <= zone_h;
        let fits_rotated = comp_h <= zone_w && comp_w <= zone_h;
        if !(fits_normal || fits_rotated) {
            too_large.push((ref_.clone(), zone_name.clone(), (comp_w, comp_h), (zone_w, zone_h)));
        }
    }

    for (ref_, zone_name, (cw, ch), (zw, zh)) in &too_large {
        let details = PyDict::new(py);
        details.set_item("component_size", PyTuple::new(py, [*cw, *ch])?)?;
        details.set_item("zone_size", PyTuple::new(py, [*zw, *zh])?)?;
        issues.push(issue_dict(
            py,
            "ERROR",
            "CONSTRAINT_002",
            &format!(
                "Component '{ref_}' ({cw:.1}x{ch:.1}mm) won't fit in zone '{zone_name}' ({zw:.1}x{zh:.1}mm)"
            ),
            &format!("Increase zone '{zone_name}' size or reassign '{ref_}' to a larger zone."),
            vec![ref_.clone()],
            details,
        )?);
    }

    for (group_name, _zone, group_comps) in &groups {
        let missing: Vec<String> = group_comps
            .iter()
            .filter(|c| !comp_bounds.contains_key(c.as_str()))
            .cloned()
            .collect();
        if !missing.is_empty() {
            let details = PyDict::new(py);
            details.set_item("group_name", group_name.as_str())?;
            details.set_item("missing_count", missing.len())?;
            let joined = missing.iter().take(5).cloned().collect::<Vec<_>>().join(", ");
            issues.push(issue_dict(
                py,
                "WARNING",
                "CONSTRAINT_003",
                &format!(
                    "Group '{group_name}' references {} components not in netlist",
                    missing.len()
                ),
                &format!("Update group or netlist. Missing: {joined}"),
                missing,
                details,
            )?);
        }
    }

    for (group_name, zone, group_comps) in &groups {
        if !zone.is_empty() && !zone_bounds.contains_key(zone.as_str()) {
            issues.push(issue_dict(
                py,
                "ERROR",
                "CONSTRAINT_004",
                &format!("Group '{group_name}' requires non-existent zone '{zone}'"),
                &format!("Create zone '{zone}' or change group's zone assignment."),
                group_comps.clone(),
                PyDict::new(py),
            )?);
        }
    }

    for thermal in &thermals {
        let missing: Vec<String> = thermal
            .iter()
            .filter(|c| !comp_bounds.contains_key(c.as_str()))
            .cloned()
            .collect();
        if !missing.is_empty() {
            let joined = missing.iter().take(5).cloned().collect::<Vec<_>>().join(", ");
            issues.push(issue_dict(
                py,
                "WARNING",
                "CONSTRAINT_005",
                &format!(
                    "Thermal constraint references {} components not in netlist",
                    missing.len()
                ),
                &format!("Update thermal constraints. Missing: {joined}"),
                missing,
                PyDict::new(py),
            )?);
        }
    }

    let error_count = issues
        .iter()
        .filter(|d| {
            d.bind(py)
                .get_item("severity")
                .ok()
                .flatten()
                .and_then(|s| s.extract::<String>().ok())
                .is_some_and(|s| s == "ERROR")
        })
        .count();
    if error_count == 0 {
        issues.push(issue_dict(
            py,
            "INFO",
            "CONSTRAINT_006",
            "All constraints are feasible",
            "",
            Vec::new(),
            PyDict::new(py),
        )?);
    }

    Ok((error_count == 0, issues))
}

/// Build one `{severity, code, message, suggestion, components, details}`
/// issue dict, the shape the delegation shims wrap into `PreflightIssue`.
fn issue_dict(
    py: Python<'_>,
    severity: &str,
    code: &str,
    message: &str,
    suggestion: &str,
    components: Vec<String>,
    details: Bound<'_, PyDict>,
) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("severity", severity)?;
    d.set_item("code", code)?;
    d.set_item("message", message)?;
    d.set_item("suggestion", suggestion)?;
    d.set_item("components", components)?;
    d.set_item("details", details)?;
    Ok(d.unbind())
}

// ---------------------------------------------------------------------------
// netlist_reconciliation — the design-netlist s-expression parser
// ---------------------------------------------------------------------------

/// A parsed node: an atom (string token) or a list of nodes.
#[derive(Debug, Clone)]
enum Value {
    Atom(String),
    List(Vec<Value>),
}

/// Tokenizer faithful to the oracle's
/// `_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()]+))', re.S)`.
/// The regex prefers the quoted-string alternative; a quote that never
/// closes falls through to the bare-token alternative (which may start at
/// the quote). Returns the RAW token spans — the decode step
/// (json.loads for quote-leading tokens) is separate, exactly as in the
/// oracle's `_sexp`. The "invalid netlist syntax at byte {pos}" branch is
/// unreachable (after `\s*`, the next char is always `(`, `)` or
/// `[^\s()]+`) and is not transcribed.
fn tokenize(text: &str) -> Vec<&str> {
    let bytes = text.as_bytes();
    let mut tokens = Vec::new();
    let mut pos = 0usize;
    while pos < bytes.len() {
        // \s* — Python's str `\s` set, Unicode-aware (see is_py_whitespace).
        while pos < bytes.len() {
            let c = next_char(text, pos);
            if !is_py_whitespace(c) {
                break;
            }
            pos += c.len_utf8();
        }
        if pos >= bytes.len() {
            break;
        }
        match bytes[pos] {
            b'(' => {
                tokens.push(&text[pos..pos + 1]);
                pos += 1;
            }
            b')' => {
                tokens.push(&text[pos..pos + 1]);
                pos += 1;
            }
            b'"' => {
                // Try the quoted-string alternative: scan for the closing
                // quote, skipping `\x` escape pairs (backslash + any char).
                // A `\` before the closing quote consumes it as an escape,
                // exactly as the regex's `\\.` alternative does.
                let mut i = pos + 1;
                let mut closed = false;
                while i < bytes.len() {
                    if bytes[i] == b'"' {
                        closed = true;
                        break;
                    }
                    if bytes[i] == b'\\' {
                        i += 2;
                    } else {
                        i += 1;
                    }
                }
                if closed {
                    tokens.push(&text[pos..=i]);
                    pos = i + 1;
                } else {
                    // fall through: [^\s()]+ starting at the quote
                    let mut j = pos;
                    while j < bytes.len() {
                        let c = next_char(text, j);
                        if is_ws_or_paren(c) {
                            break;
                        }
                        j += c.len_utf8();
                    }
                    tokens.push(&text[pos..j]);
                    pos = j;
                }
            }
            _ => {
                // [^\s()]+
                let mut j = pos;
                while j < bytes.len() {
                    let c = next_char(text, j);
                    if is_ws_or_paren(c) {
                        break;
                    }
                    j += c.len_utf8();
                }
                tokens.push(&text[pos..j]);
                pos = j;
            }
        }
    }
    tokens
}

/// Decode the char at byte offset `pos` (callers guarantee
/// `pos < text.len()`). `text` is a `String` from the Python boundary, so
/// it is valid UTF-8; `chars()` yields U+FFFD for a lone surrogate, which
/// cannot appear in a `String` from CPython (surrogates stay inside the
/// pyo3 boundary, never in the kernel's `&str`).
fn next_char(text: &str, pos: usize) -> char {
    match text[pos..].chars().next() {
        Some(c) => c,
        None => unreachable!("pos < len, valid UTF-8"),
    }
}

/// Python's `\s` set for `str` (as matched by the oracle's
/// `_TOKEN = re.compile(r'\s*...', re.S)`): the ASCII
/// `[ \t\n\r\f\v]` plus the Unicode whitespace code points U+001C–U+001F
/// (file/group/record/unit separators), U+0085 (NEL), U+00A0 (NBSP),
/// U+1680 (Ogham space mark), U+2000–U+200A (the en-space family),
/// U+2028/U+2029 (line/paragraph separators), U+202F (narrow NBSP),
/// U+205F (medium mathematical space), U+3000 (ideographic space).
/// Measured against CPython 3.12 (2026-08-05): these are exactly the code
/// points `re.match(r'\s', ch)` accepts.
///
/// NOTE this is deliberately NOT Rust's `char::is_whitespace` (Unicode
/// White_Space): that set MISSES U+001C–U+001F and U+0085, which Python
/// `\s` matches — the same classification gap already recorded for
/// `str.strip` in the reference-loader section (VERIFICATION.md §M4).
fn is_py_whitespace(c: char) -> bool {
    matches!(
        c,
        ' ' | '\t' | '\n' | '\r' | '\x0b' | '\x0c'
            | '\u{1c}' | '\u{1d}' | '\u{1e}' | '\u{1f}'
            | '\u{85}' | '\u{a0}' | '\u{1680}'
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}' | '\u{2029}' | '\u{202f}'
            | '\u{205f}' | '\u{3000}'
    )
}

fn is_ws_or_paren(c: char) -> bool {
    is_py_whitespace(c) || c == '(' || c == ')'
}

/// Decode one token into an atom: `json.loads(token)` for quote-leading
/// tokens, identity otherwise (the oracle's `_sexp` line).
fn decode_atom(token: &str) -> Result<String, String> {
    if token.starts_with('"') {
        // serde_json and CPython json agree on every valid JSON string;
        // malformed quoted tokens are outside the compiler's domain (see
        // the module docstring — the error text differs, recorded).
        serde_json::from_str::<String>(token).map_err(|e| e.to_string())
    } else {
        Ok(token.to_string())
    }
}

/// Parse the token stream into nested `Value`s (the oracle's `_sexp`
/// stack machine). Errors are the oracle's byte-identical strings (as
/// `PyValueError`; the shim re-wraps into `ReconciliationGateError`).
fn sexp(text: &str) -> Result<Vec<Value>, String> {
    let tokens = tokenize(text);
    let mut stack: Vec<Vec<Value>> = vec![Vec::new()]; // stack[0] is the root
    for token in tokens {
        match token {
            "(" => stack.push(Vec::new()),
            ")" => {
                if stack.len() == 1 {
                    return Err("unbalanced netlist: unmatched ')'".to_string());
                }
                // len >= 2, so pop() is Some and the new top exists.
                if let Some(closed) = stack.pop() {
                    let last_idx = stack.len() - 1;
                    stack[last_idx].push(Value::List(closed));
                }
            }
            _ => {
                let atom = decode_atom(token)?;
                let last_idx = stack.len() - 1;
                stack[last_idx].push(Value::Atom(atom));
            }
        }
    }
    if stack.len() != 1 {
        return Err("unbalanced netlist: unmatched '('".to_string());
    }
    match stack.pop() {
        Some(root) => Ok(root),
        None => unreachable!("stack had exactly one element"),
    }
}

/// `_children(node, name)` — child lists whose first element == name.
fn children<'a>(node: &'a [Value], name: &str) -> Vec<&'a [Value]> {
    node.iter()
        .filter_map(|v| match v {
            Value::List(items) if !items.is_empty() => match &items[0] {
                Value::Atom(head) if head == name => Some(items.as_slice()),
                _ => None,
            },
            _ => None,
        })
        .collect()
}

/// Python `repr` of a `Value` — `node[0]!r` in the error strings.
fn value_repr(v: &Value) -> String {
    match v {
        Value::Atom(s) => py_str_repr(s),
        Value::List(items) => {
            let inner: Vec<String> = items.iter().map(value_repr).collect();
            format!("[{}]", inner.join(", "))
        }
    }
}

/// `_field(node, name)` — the strict fail-closed single-field reader with
/// the oracle's byte-identical error strings.
///
/// The error is either a gate-error string (raised as `PyValueError` by
/// the caller) or the oracle's raw `node[0]` `IndexError` for an EMPTY
/// node. Through the netlist grammar the empty node is unreachable —
/// `children()` requires a non-empty list whose first element is the name
/// atom, and the s-expression parser always stores the head — but the
/// oracle's expression is `{node[0]!r}`, which would raise
/// `IndexError('list index out of range')` if it ever were empty; the
/// kernel mirrors that expression so the escaping class cannot diverge
/// (parity of the code, not only of reachable states).
#[derive(Debug, PartialEq)]
enum FieldErr {
    Gate(String),
    Index,
}

fn field(node: &[Value], name: &str, required: bool) -> Result<String, FieldErr> {
    let fields = children(node, name);
    if fields.len() > 1 || (required && fields.is_empty()) {
        let head = match node.first() {
            Some(first) => value_repr(first),
            None => return Err(FieldErr::Index),
        };
        return Err(FieldErr::Gate(format!(
            "invalid {} field in {}",
            py_str_repr(name),
            head
        )));
    }
    if fields.is_empty() {
        return Ok(String::new());
    }
    let f = fields[0];
    if f.len() != 2 {
        // `fields` non-empty implies `node` non-empty (the field list is a
        // child of `node`), so the oracle's `node[0]` here cannot
        // IndexError — rendered identically.
        return Err(FieldErr::Gate(format!(
            "malformed {} field in {}",
            py_str_repr(name),
            value_repr(&node[0])
        )));
    }
    match &f[1] {
        Value::Atom(s) => Ok(s.clone()),
        _ => Err(FieldErr::Gate(format!(
            "malformed {} field in {}",
            py_str_repr(name),
            value_repr(&node[0])
        ))),
    }
}

fn field_err(e: FieldErr) -> PyErr {
    match e {
        FieldErr::Gate(msg) => PyValueError::new_err(msg),
        FieldErr::Index => PyIndexError::new_err("list index out of range"),
    }
}

/// `_instance_path_from_sheetpath` — the dotted atopile path after the
/// first `::`, or "".
fn instance_path_from_sheetpath(sheetpath_node: &[Value]) -> String {
    for child in children(sheetpath_node, "names") {
        let names = match child.get(1) {
            Some(Value::Atom(s)) => s.clone(),
            _ => String::new(),
        };
        if let Some((_, after)) = names.split_once("::") {
            return after.to_string();
        }
    }
    String::new()
}

/// `parse_design_netlist` compute — parses the compiled design-netlist
/// text into `(components, nets, duplicate_refs)`. The file read and the
/// "not found"/"empty" checks stay in the delegation module; every other
/// fail-closed error is raised here with the oracle's byte-identical
/// message (including the `!r` reprs and the netlist path).
#[pyfunction]
#[pyo3(signature = (netlist_path, text))]
fn parse_design_netlist(netlist_path: String, text: String) -> PyResult<ParsedDesignNetlist> {
    let parsed = sexp(&text).map_err(PyValueError::new_err)?;

    let export = parsed.iter().find(|item| match item {
        Value::List(items) if !items.is_empty() => {
            matches!(&items[0], Value::Atom(h) if h == "export")
        }
        _ => false,
    });
    let Some(Value::List(export_items)) = export else {
        return Err(PyValueError::new_err(format!(
            "netlist has no 'export' block: {netlist_path}"
        )));
    };

    let components_blocks = children(export_items, "components");
    if components_blocks.len() != 1 {
        return Err(PyValueError::new_err(
            "netlist must contain exactly one 'components' block",
        ));
    }

    let mut components: Vec<(String, String)> = Vec::new();
    let mut duplicate_refs: Vec<(String, String, String)> = Vec::new();
    let mut seen_paths: HashMap<String, String> = HashMap::new();
    let mut ref_paths: HashMap<String, String> = HashMap::new();

    for node in children(components_blocks[0], "comp") {
        let ref_ = field(node, "ref", true).map_err(field_err)?;
        let sheetpath_nodes = children(node, "sheetpath");
        let instance_path = match sheetpath_nodes.first() {
            Some(sp) => instance_path_from_sheetpath(sp),
            None => String::new(),
        };
        if instance_path.is_empty() {
            return Err(PyValueError::new_err(format!(
                "design component {} has no usable 'sheetpath' field -- \
                 cannot establish a designator-renumbering-safe identity for it",
                py_str_repr(&ref_)
            )));
        }
        if let Some(prev_ref) = seen_paths.get(&instance_path) {
            return Err(PyValueError::new_err(format!(
                "design netlist has two components sharing instance path {} ({} and {}) \
                 -- identity is ambiguous, refusing to guess",
                py_str_repr(&instance_path),
                py_str_repr(prev_ref),
                py_str_repr(&ref_)
            )));
        }
        seen_paths.insert(instance_path.clone(), ref_.clone());
        // The oracle's `if ref in ref_paths: append(...) else: ref_paths[ref]
        // = path` anchors every duplicate pair at the FIRST-seen path
        // (never updated); `insert`'s replace-and-return would chain pairs
        // instead. First occurrence only.
        if let Some(first_path) = ref_paths.get(&ref_) {
            duplicate_refs.push((ref_.clone(), first_path.clone(), instance_path.clone()));
        } else {
            ref_paths.insert(ref_.clone(), instance_path.clone());
        }
        components.push((ref_, instance_path));
    }

    if components.is_empty() {
        return Err(PyValueError::new_err(format!(
            "netlist contains zero components: {netlist_path}"
        )));
    }

    let nets_blocks = children(export_items, "nets");
    if nets_blocks.len() != 1 {
        return Err(PyValueError::new_err(
            "netlist must contain exactly one 'nets' block",
        ));
    }

    let mut nets: Vec<(String, Vec<(String, String)>)> = Vec::new();
    let mut pin_owner: HashMap<(String, String), String> = HashMap::new();
    for node in children(nets_blocks[0], "net") {
        let name = field(node, "name", true).map_err(field_err)?;
        if nets.iter().any(|(n, _)| *n == name) {
            return Err(PyValueError::new_err(format!(
                "duplicate net name in netlist: {}",
                py_str_repr(&name)
            )));
        }
        let mut nodelist: Vec<(String, String)> = Vec::new();
        for nn in children(node, "node") {
            let ref_ = field(nn, "ref", true).map_err(field_err)?;
            let pin = field(nn, "pin", true).map_err(field_err)?;
            if let Some(owner) = pin_owner.get(&(ref_.clone(), pin.clone())) {
                return Err(PyValueError::new_err(format!(
                    "pin {}.{} appears in more than one net ({} and {}) -- malformed netlist",
                    ref_,
                    pin,
                    py_str_repr(owner),
                    py_str_repr(&name)
                )));
            }
            pin_owner.insert((ref_.clone(), pin.clone()), name.clone());
            nodelist.push((ref_, pin));
        }
        nets.push((name, nodelist));
    }

    if nets.is_empty() {
        return Err(PyValueError::new_err(format!(
            "netlist contains zero nets: {netlist_path}"
        )));
    }

    Ok((components, nets, duplicate_refs))
}

// ---------------------------------------------------------------------------
// netlist_reconciliation.reconcile — the comparison kernel
// ---------------------------------------------------------------------------

/// `design.ref_to_paths` — ref -> instance paths, component order (used by
/// the net-path resolution; a ref with multiple paths contributes all).
fn design_ref_to_paths(design_components: &[(String, String)]) -> HashMap<&str, Vec<&str>> {
    let mut out: HashMap<&str, Vec<&str>> = HashMap::new();
    for (ref_, path) in design_components {
        out.entry(ref_.as_str()).or_default().push(path.as_str());
    }
    out
}

/// `_net_membership_detail` — the byte-identical NET-MEMBERSHIP detail.
fn net_membership_detail(
    name: &str,
    design_paths: &std::collections::HashSet<&str>,
    board_paths: &std::collections::HashSet<&str>,
) -> String {
    let mut only_design: Vec<&str> = design_paths
        .iter()
        .copied()
        .filter(|p| !board_paths.contains(p))
        .collect();
    only_design.sort_unstable();
    let mut only_board: Vec<&str> = board_paths
        .iter()
        .copied()
        .filter(|p| !design_paths.contains(p))
        .collect();
    only_board.sort_unstable();
    let mut parts = vec![format!(
        "net {} has different component membership between the two sides",
        py_str_repr(name)
    )];
    if !only_design.is_empty() {
        parts.push(format!("design-only: {}", only_design.join(", ")));
    }
    if !only_board.is_empty() {
        parts.push(format!("board-only: {}", only_board.join(", ")));
    }
    parts.join(" -- ")
}

/// Build one `{kind, severity, detail, refs, paths}` finding dict.
fn finding_dict(
    py: Python<'_>,
    kind: &str,
    severity: &str,
    detail: &str,
    refs: Vec<String>,
    paths: Vec<String>,
) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("kind", kind)?;
    d.set_item("severity", severity)?;
    d.set_item("detail", detail)?;
    d.set_item("refs", refs)?;
    d.set_item("paths", paths)?;
    Ok(d.unbind())
}

/// `reconcile` compute — component-level (UNKEYABLE / REUSE / MISSING /
/// RENUMBERED / EXTRA) and net-level (NET-MISSING / NET-EXTRA /
/// NET-MEMBERSHIP) findings plus the report counters, in the oracle's
/// exact finding order. Returns `(findings, design_components,
/// board_components, matched_paths, design_nets_nonempty, board_nets)`;
/// each finding is `{kind, severity, detail, refs, paths}`.
#[pyfunction]
fn reconcile(
    py: Python<'_>,
    board_components: Vec<(String, String)>,
    board_nets: Vec<(String, Vec<String>)>,
    design_components: Vec<(String, String)>,
    design_nets: Vec<(String, Vec<(String, String)>)>,
    duplicate_refs: Vec<(String, String, String)>,
) -> PyResult<ReconcileResult> {
    let mut findings: Vec<Py<PyDict>> = Vec::new();

    // UNKEYABLE — board.components order.
    for (ref_, sheetpath) in &board_components {
        if sheetpath.is_empty() {
            findings.push(finding_dict(
                py,
                "UNKEYABLE",
                "ERROR",
                &format!(
                    "{ref_}: board footprint has no 'Sheetpath' property -- \
                     cannot be identity-matched against the netlist at all"
                ),
                vec![ref_.clone()],
                Vec::new(),
            )?);
        }
    }

    let design_by_path: HashMap<&str, &str> = design_components
        .iter()
        .map(|(r, p)| (p.as_str(), r.as_str()))
        .collect();
    let board_by_path: HashMap<&str, &str> = board_components
        .iter()
        .map(|(r, p)| (p.as_str(), r.as_str()))
        .collect();

    // Board-side REUSE — grouped by ref in component order, refs sorted.
    let mut board_ref_paths: Vec<(String, Vec<String>)> = Vec::new();
    for (ref_, sheetpath) in &board_components {
        match board_ref_paths.iter_mut().find(|(r, _)| r == ref_) {
            Some((_, paths)) => paths.push(sheetpath.clone()),
            None => board_ref_paths.push((ref_.clone(), vec![sheetpath.clone()])),
        }
    }
    board_ref_paths.sort_by(|a, b| a.0.cmp(&b.0));
    for (ref_, paths) in &board_ref_paths {
        if paths.len() > 1 {
            let joined = paths
                .iter()
                .map(|p| if p.is_empty() { "<no sheetpath>".to_string() } else { p.clone() })
                .collect::<Vec<_>>()
                .join(", ");
            findings.push(finding_dict(
                py,
                "REUSE",
                "ERROR",
                &format!(
                    "ref {} names {} board components ({joined}) -- one ref, multiple components",
                    py_str_repr(ref_),
                    paths.len(),
                ),
                vec![ref_.clone()],
                paths.clone(),
            )?);
        }
    }

    // Design-side REUSE — duplicate_refs order.
    for (ref_, path_a, path_b) in &duplicate_refs {
        findings.push(finding_dict(
            py,
            "REUSE",
            "ERROR",
            &format!(
                "ref {} names two design components ({} and {}) -- \
                 one ref, multiple components",
                py_str_repr(ref_),
                py_str_repr(path_a),
                py_str_repr(path_b),
            ),
            vec![ref_.clone()],
            vec![path_a.clone(), path_b.clone()],
        )?);
    }

    // MISSING / RENUMBERED — sorted design paths.
    let mut design_paths_sorted: Vec<&str> = design_by_path.keys().copied().collect();
    design_paths_sorted.sort_unstable();
    for path in design_paths_sorted {
        let design_ref = design_by_path[path];
        match board_by_path.get(path) {
            None => findings.push(finding_dict(
                py,
                "MISSING",
                "ERROR",
                &format!(
                    "design component {} (path {}) has no board footprint carrying this \
                     sheetpath -- the board has never been resynced to include this \
                     component (the tank-capacitor class)",
                    py_str_repr(design_ref),
                    py_str_repr(path),
                ),
                vec![design_ref.to_string()],
                vec![path.to_string()],
            )?),
            Some(board_ref) if *board_ref != design_ref => findings.push(finding_dict(
                py,
                "RENUMBERED",
                "ERROR",
                &format!(
                    "path {} carries different refs: design {} vs board {} -- a designator \
                     renumber (refdes overlap is blind to this class)",
                    py_str_repr(path),
                    py_str_repr(design_ref),
                    py_str_repr(board_ref),
                ),
                vec![design_ref.to_string(), (*board_ref).to_string()],
                vec![path.to_string()],
            )?),
            _ => {}
        }
    }

    // EXTRA — sorted board paths.
    let mut board_paths_sorted: Vec<&str> = board_by_path.keys().copied().collect();
    board_paths_sorted.sort_unstable();
    for path in board_paths_sorted {
        if !design_by_path.contains_key(path) {
            let board_ref = board_by_path[path];
            findings.push(finding_dict(
                py,
                "EXTRA",
                "ERROR",
                &format!(
                    "board footprint {} (path {}) has no matching component in the \
                     compiled netlist -- stale board, or a corrupted Sheetpath property",
                    py_str_repr(board_ref),
                    py_str_repr(path),
                ),
                vec![board_ref.to_string()],
                vec![path.to_string()],
            )?);
        }
    }

    // Net-level: resolve design net -> path sets (keeping empty sets!),
    // then the sorted NET-MISSING / NET-MEMBERSHIP / NET-EXTRA findings.
    let design_ref_to_paths = design_ref_to_paths(&design_components);
    let mut design_net_paths: HashMap<&str, std::collections::HashSet<&str>> = HashMap::new();
    for (name, nodes) in &design_nets {
        let mut paths: std::collections::HashSet<&str> = std::collections::HashSet::new();
        for (ref_, _pin) in nodes {
            if let Some(ps) = design_ref_to_paths.get(ref_.as_str()) {
                paths.extend(ps.iter().copied());
            }
        }
        design_net_paths.insert(name.as_str(), paths);
    }

    let board_nets_map: HashMap<&str, std::collections::HashSet<&str>> = board_nets
        .iter()
        .map(|(name, paths)| (name.as_str(), paths.iter().map(String::as_str).collect()))
        .collect();

    let mut design_net_sorted: Vec<&str> = design_net_paths.keys().copied().collect();
    design_net_sorted.sort_unstable();
    for name in design_net_sorted {
        let paths = &design_net_paths[name];
        let board_paths = board_nets_map.get(name);
        if paths.is_empty() {
            // Declared-but-empty design net: no board counterpart -> nothing;
            // board counterpart -> the dropped-net signature.
            if let Some(bp) = board_paths.filter(|bp| !bp.is_empty()) {
                let mut sorted_bp: Vec<&str> = bp.iter().copied().collect();
                sorted_bp.sort_unstable();
                findings.push(finding_dict(
                    py,
                    "NET-MEMBERSHIP",
                    "ERROR",
                    &format!(
                        "net {} connects board component(s) {} but has zero nodes in the \
                         compiled netlist -- the net's membership was dropped on the \
                         design side (dropped-net class)",
                        py_str_repr(name),
                        sorted_bp.join(", "),
                    ),
                    Vec::new(),
                    sorted_bp.iter().map(|s| (*s).to_string()).collect(),
                )?);
            }
            continue;
        }
        match board_paths {
            None => {
                let mut sorted_p: Vec<&str> = paths.iter().copied().collect();
                sorted_p.sort_unstable();
                findings.push(finding_dict(
                    py,
                    "NET-MISSING",
                    "ERROR",
                    &format!(
                        "net {} connects design component(s) {} but has no counterpart on \
                         the board -- a design net with zero placed components",
                        py_str_repr(name),
                        sorted_p.join(", "),
                    ),
                    Vec::new(),
                    sorted_p.iter().map(|s| (*s).to_string()).collect(),
                )?);
            }
            Some(bp) if bp != paths => {
                let detail = net_membership_detail(name, paths, bp);
                let mut sym_diff: Vec<&str> = paths
                    .iter()
                    .copied()
                    .filter(|p| !bp.contains(p))
                    .chain(bp.iter().copied().filter(|p| !paths.contains(p)))
                    .collect();
                sym_diff.sort_unstable();
                findings.push(finding_dict(
                    py,
                    "NET-MEMBERSHIP",
                    "ERROR",
                    &detail,
                    Vec::new(),
                    sym_diff.iter().map(|s| (*s).to_string()).collect(),
                )?);
            }
            _ => {}
        }
    }

    let mut board_net_sorted: Vec<&str> = board_nets_map.keys().copied().collect();
    board_net_sorted.sort_unstable();
    for name in board_net_sorted {
        if !design_net_paths.contains_key(name) {
            let bp = &board_nets_map[name];
            let mut sorted_bp: Vec<&str> = bp.iter().copied().collect();
            sorted_bp.sort_unstable();
            findings.push(finding_dict(
                py,
                "NET-EXTRA",
                "ERROR",
                &format!(
                    "net {} connects board component(s) {} but does not exist in the \
                     compiled netlist -- stale board or orphaned assignment",
                    py_str_repr(name),
                    sorted_bp.join(", "),
                ),
                Vec::new(),
                sorted_bp.iter().map(|s| (*s).to_string()).collect(),
            )?);
        }
    }

    let matched_paths = {
        let design_paths: std::collections::HashSet<&str> =
            design_components.iter().map(|(_, p)| p.as_str()).collect();
        let board_paths: std::collections::HashSet<&str> =
            board_components.iter().map(|(_, p)| p.as_str()).collect();
        design_paths.intersection(&board_paths).count()
    };
    let design_nets_nonempty = design_net_paths.values().filter(|p| !p.is_empty()).count();
    let board_nets_count = board_nets.len();

    Ok((
        findings,
        design_components.len(),
        board_components.len(),
        matched_paths,
        design_nets_nonempty,
        board_nets_count,
    ))
}

// ---------------------------------------------------------------------------
// placement_roundtrip — the pure kernels
// ---------------------------------------------------------------------------

/// `canonical_angle` — mod-360 normalization into `[0, 360)` with CPython
/// `float %` semantics (py_float_mod, so `-720.0` → `+0.0`, not `-0.0`).
#[pyfunction]
fn canonical_angle(angle: f64) -> f64 {
    py_float_mod(angle, 360.0)
}

/// `_angle_diff` — the shortest signed-magnitude difference in degrees.
#[pyfunction]
fn angle_diff(a: f64, b: f64) -> f64 {
    let diff = (canonical_angle(a) - canonical_angle(b)).abs();
    let diff = py_float_mod(diff, 360.0);
    diff.min(360.0 - diff)
}

/// `_pad_key` — a pad's number when it has one, else `__pad_{index}`.
#[pyfunction]
#[pyo3(signature = (number, index))]
fn pad_key(number: Option<String>, index: usize) -> String {
    match number {
        Some(n) if !n.is_empty() => n,
        _ => format!("__pad_{index}"),
    }
}

/// Build one `{kind, pad, expected, actual, detail}` mismatch dict.
fn mismatch_dict(
    py: Python<'_>,
    kind: &str,
    pad: Option<String>,
    expected: Option<Py<PyAny>>,
    actual: Option<Py<PyAny>>,
    detail: &str,
) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("kind", kind)?;
    d.set_item("pad", pad)?;
    d.set_item("expected", expected)?;
    d.set_item("actual", actual)?;
    d.set_item("detail", detail)?;
    Ok(d.unbind())
}

/// The `_check_footprint` comparison logic of
/// `placement_roundtrip.check_placement_roundtrip`: the footprint-anchor,
/// footprint-angle, pad-presence, pad-position and pad-angle checks and
/// mismatch-record construction. The shim supplies WORLD geometry
/// (computed by the shared kicad_transform primitives) and the written
/// anchors/angles from the kiutils tree; this kernel is the comparison
/// itself.
///
/// `rot_center` is the R(-theta)-rotated center offset; the expected
/// anchor is `pos - rot_center`. Template pads are
/// `(key, exp_x, exp_y, intrinsic_deg)` — the expected world position and
/// the template pad's intrinsic angle (`pad_rotation_deg`); the expected
/// world pad angle is `canonical_angle(theta + intrinsic_deg)`. Written
/// pads are `(key, x, y, angle)` with `None` position entries for a pad
/// with no `(at ...)` token.
///
/// Returns `(mismatches, checked_pads)` where each mismatch is
/// `{kind, pad, expected, actual, detail}`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn check_footprint_geometry(
    py: Python<'_>,
    _ref: String,
    pos: (f64, f64),
    rot_center: (f64, f64),
    written_anchor: (f64, f64),
    theta: f64,
    written_angle: f64,
    epsilon: f64,
    template_pads: Vec<(String, f64, f64, f64)>,
    written_pads: Vec<WrittenPad>,
) -> PyResult<(Vec<Py<PyDict>>, usize)> {
    let mut mismatches: Vec<Py<PyDict>> = Vec::new();

    let exp_anchor_x = pos.0 - rot_center.0;
    let exp_anchor_y = pos.1 - rot_center.1;
    let wx = written_anchor.0;
    let wy = written_anchor.1;
    if (wx - exp_anchor_x).abs() > epsilon || (wy - exp_anchor_y).abs() > epsilon {
        mismatches.push(mismatch_dict(
            py,
            "footprint_anchor",
            None,
            Some(py_tuple2(py, exp_anchor_x, exp_anchor_y)?),
            Some(py_tuple2(py, wx, wy)?),
            "",
        )?);
    }

    let wa = written_angle;
    if angle_diff(theta, wa) > epsilon {
        mismatches.push(mismatch_dict(
            py,
            "footprint_angle",
            None,
            Some(py_float(py, canonical_angle(theta))?),
            Some(py_float(py, canonical_angle(wa))?),
            "",
        )?);
    }

    let mut written_by_key: HashMap<&str, &WrittenPad> = HashMap::new();
    for wp in &written_pads {
        written_by_key.insert(wp.0.as_str(), wp);
    }

    let mut checked = 0usize;
    for (key, exp_x, exp_y, intrinsic) in &template_pads {
        let Some(wpad) = written_by_key.get(key.as_str()) else {
            mismatches.push(mismatch_dict(
                py,
                "pad_missing",
                Some(key.clone()),
                None,
                None,
                "template pad not present in the written footprint",
            )?);
            continue;
        };
        let (Some(x), Some(y), Some(angle)) = (wpad.1, wpad.2, wpad.3) else {
            mismatches.push(mismatch_dict(
                py,
                "pad_missing",
                Some(key.clone()),
                None,
                None,
                "written pad has no (at ...) position",
            )?);
            continue;
        };
        if (exp_x - x).abs() > epsilon || (exp_y - y).abs() > epsilon {
            mismatches.push(mismatch_dict(
                py,
                "pad_position",
                Some(key.clone()),
                Some(py_tuple2(py, *exp_x, *exp_y)?),
                Some(py_tuple2(py, x, y)?),
                "",
            )?);
        }
        let exp_ang = canonical_angle(theta + intrinsic);
        let act_ang = canonical_angle(angle);
        if angle_diff(exp_ang, act_ang) > epsilon {
            mismatches.push(mismatch_dict(
                py,
                "pad_angle",
                Some(key.clone()),
                Some(py_float(py, exp_ang)?),
                Some(py_float(py, act_ang)?),
                "",
            )?);
        }
        checked += 1;
    }

    Ok((mismatches, checked))
}

// ---------------------------------------------------------------------------
// prereg/schema — the temporal gate
// ---------------------------------------------------------------------------

/// The temporal-gate control flow of `PreregistrationManifest.load`: the
/// `created > battery` decision (via Python's own `>` — the two datetimes
/// are opaque here and compared by calling back into CPython) and the
/// byte-identical ValueError construction. The naive-to-UTC normalization
/// and `_parse_iso_to_utc` stay in the shim (Python datetime semantics);
/// this kernel decides and raises.
#[pyfunction]
fn prereg_temporal_gate(
    created_dt: Bound<'_, PyAny>,
    created_raw: String,
    battery_dt: Bound<'_, PyAny>,
    battery_iso: String,
) -> PyResult<()> {
    let after = created_dt
        .rich_compare(&battery_dt, pyo3::basic::CompareOp::Gt)?
        .is_truthy()?;
    if after {
        return Err(PyValueError::new_err(format!(
            "pre-registration created_at ({created_raw}) post-dates battery-run timestamp \
             ({battery_iso}); pre-registration must demonstrably predate results"
        )));
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Register the validation kernels as the `validation` submodule of
/// `temper_design_bundle_python`.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let sub = PyModule::new(module.py(), "validation")?;
    sub.add_function(wrap_pyfunction!(zones_overlap, &sub)?)?;
    sub.add_function(wrap_pyfunction!(preflight_zones_fit, &sub)?)?;
    sub.add_function(wrap_pyfunction!(preflight_unassigned, &sub)?)?;
    sub.add_function(wrap_pyfunction!(preflight_impossible, &sub)?)?;
    sub.add_function(wrap_pyfunction!(parse_design_netlist, &sub)?)?;
    sub.add_function(wrap_pyfunction!(reconcile, &sub)?)?;
    sub.add_function(wrap_pyfunction!(canonical_angle, &sub)?)?;
    sub.add_function(wrap_pyfunction!(angle_diff, &sub)?)?;
    sub.add_function(wrap_pyfunction!(pad_key, &sub)?)?;
    sub.add_function(wrap_pyfunction!(check_footprint_geometry, &sub)?)?;
    sub.add_function(wrap_pyfunction!(prereg_temporal_gate, &sub)?)?;
    module.add_submodule(&sub)?;
    Ok(())
}

#[cfg(test)]
mod validation_parity_tests {
    use super::*;

    #[test]
    fn field_on_empty_node_is_the_oracles_index_error_not_a_fabricated_head() {
        // The oracle's error path is `f"invalid {name!r} field in {node[0]!r}"`:
        // an empty node would raise `IndexError('list index out of range')` —
        // never a gate error with a fabricated `'None'` head. Unreachable
        // through the netlist grammar (children() requires a head), pinned
        // here so the escaping class cannot diverge if the grammar grows a
        // headless node form.
        match field(&[], "ref", true) {
            Err(FieldErr::Index) => {}
            other => panic!("expected FieldErr::Index, got {other:?}"),
        }
        // required=false on an empty node short-circuits before the head is
        // evaluated, exactly as the oracle's `if not fields: return ""`.
        assert_eq!(field(&[], "ref", false), Ok(String::new()));
    }

    #[test]
    fn is_py_whitespace_matches_cpythons_unicode_set() {
        // ASCII [ \t\n\r\f\v]
        for c in [' ', '\t', '\n', '\r', '\x0b', '\x0c'] {
            assert!(is_py_whitespace(c), "0x{:x}", c as u32);
        }
        // The Unicode code points Python `\s` matches but
        // char::is_whitespace does NOT (the classification gap this
        // function exists to close; measured against CPython 3.12).
        for cp in [
            0x1c, 0x1d, 0x1e, 0x1f, 0x85, 0xa0, 0x1680, 0x2000, 0x200a,
            0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
        ] {
            let c = char::from_u32(cp).unwrap_or_else(|| unreachable!("valid code point"));
            assert!(is_py_whitespace(c), "U+{:04X}", cp);
        }
        // And the whole \u2000-\u200a range.
        for cp in 0x2000..=0x200a {
            let c = char::from_u32(cp).unwrap_or_else(|| unreachable!("valid code point"));
            assert!(is_py_whitespace(c));
        }
        // A non-whitespace non-ASCII char is NOT whitespace.
        assert!(!is_py_whitespace('\u{e9}'));
    }

    #[test]
    fn tokenize_splits_on_unicode_whitespace_like_the_oracle_regex() {
        // \xa0 separates tokens exactly like the oracle's `\s*`/`[^\s()]`
        // (the byte-level old tokenizer glued "comp\xa0" into one token).
        let text = "(comp\u{a0}\u{a0}(ref \"R1\"))\n";
        let tokens = tokenize(text);
        assert_eq!(
            tokens,
            vec!["(", "comp", "(", "ref", "\"R1\"", ")", ")"]
        );
        // \u2028 (line separator) and \u3000 (ideographic space) too.
        let text2 = "(a\u{2028}b\u{3000}c)";
        assert_eq!(tokenize(text2), vec!["(", "a", "b", "c", ")"]);
    }
}
