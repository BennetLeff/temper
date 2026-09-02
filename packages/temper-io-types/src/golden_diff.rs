//! golden_diff: tolerance-aware golden-output comparison for DSN/SES/JSON.
//!
//! Ported verbatim from `temper_placer/testing/golden_diff.py` (the crate
//! VERIFICATION.md carries the parity proof; the differential oracle in
//! `packages/temper-placer/tests/testing/test_golden_diff_rust_differential.py`
//! is a verbatim copy of the pre-migration Python).  The module was the last
//! sizeable Python piece with real parsing/diffing logic: DSN place/net
//! extraction, SES `(wire ... (path ...))` extraction, and a
//! tolerance-aware recursive JSON diff, all producing a structured report
//! of BINARY / WITHIN_TOLERANCE / BEYOND_TOLERANCE entries.
//!
//! What migrated from Python:
//!   - `parse_dsn_places` / `parse_dsn_nets` / `parse_ses_wires` -- the
//!     regex kernels (pure Rust, wasm32-safe).  The existing `dsn`/`dsn_types`
//!     modules were checked and NOT reused: they are a DSN *formatter*
//!     (`format_dsn_arg`, `dsn_expression_to_string`) and text normaliser,
//!     not a place/net structural parser -- see VERIFICATION.md.
//!   - `diff_dsn` / `diff_ses` / `diff_json` (+ `json_diff_recursive`) -- the
//!     comparison kernels, including the CPython-`str(float)` replica
//!     (`py_str_float`) and CPython-`round(x, 6)` (`py_round_6`).
//!   - the former `diff_golden` dispatch, `DiffEntry`/`DiffReport` dataclasses
//!     and `to_json` presentation were binding-only and were retired with the
//!     Python shim.
//!
//! The former Python bridge returned `(entries, passed, summary)` from these
//! kernels.  That bridge had no production callers and is intentionally kept
//! out of the extension surface; the kernels remain available to Rust tests
//! and native consumers.

use regex::Regex;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::sync::LazyLock;

/// Compiles a regex from a source literal. Infallible: every pattern passed
/// here is a compile-time constant in this file, so `Regex::new` cannot fail.
#[expect(clippy::expect_used, reason = "literal patterns compiled from source cannot fail")]
fn static_regex(pattern: &'static str) -> Regex {
    Regex::new(pattern).expect("invalid static regex literal")
}

// ---------------------------------------------------------------------------
// CPython float-string replica
// ---------------------------------------------------------------------------

/// CPython `str(float)` (== `repr(float)`, shortest round-trip with
/// CPython's formatting rules), which the reference renders every
/// `golden_value`/`candidate_value` through.
///
/// Rules reproduced:
///   - `nan` / `inf` / `-inf` (lowercase, NaN sign dropped),
///   - `-0.0` for negative zero,
///   - fixed-point when `-3 <= decpt <= 16`, scientific otherwise (decpt =
///     digits-before-decimal-point, from the shortest digit string), with
///     `e+NN`/`e-NN` (sign always present, exponent zero-padded to >= 2),
///   - integral fixed-point values get a trailing `.0` (Py_DTSF_ADD_DOT_0).
///
/// The shortest digit string comes from Rust's `{:e}` (Grisu3 + Dragon4).
/// Empirically verified byte-identical to CPython over 320k random values
/// (boundary thresholds, subnormals, 1e-320..1e279, |x|<=1e9 sweeps -- 0
/// mismatches); the only known divergence class is shortest-repr tie
/// breaking at magnitude >= ~1e14, outside the golden-diff input domain
/// (see VERIFICATION.md "Documented bounds").
pub fn py_str_float(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x < 0.0 { "-inf" } else { "inf" }.to_string();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0" } else { "0.0" }.to_string();
    }
    let sign = if x < 0.0 { "-" } else { "" };
    let mantissa = format!("{:e}", x.abs());
    let (digits_part, exp_part) = match mantissa.split_once('e') {
        Some(pair) => pair,
        // Unreachable: `{:e}` on a finite nonzero f64 always emits 'e'.
        None => return mantissa,
    };
    let digits: String = digits_part.chars().filter(|c| *c != '.').collect();
    let exp: i32 = match exp_part.parse() {
        Ok(e) => e,
        // Unreachable: the exponent is a signed integer literal.
        Err(_) => return mantissa,
    };
    let decpt = exp + 1;
    if decpt <= -4 || decpt >= 17 {
        let (head, tail) = digits.split_at(1);
        let mantissa_out = if tail.is_empty() {
            head.to_string()
        } else {
            format!("{}.{}", head, tail)
        };
        let exp_sign = if exp < 0 { "-" } else { "+" };
        format!("{}{}e{}{:02}", sign, mantissa_out, exp_sign, exp.abs())
    } else {
        let body = if decpt <= 0 {
            format!("0.{}{}", "0".repeat((-decpt) as usize), digits)
        } else if (decpt as usize) < digits.len() {
            let (h, t) = digits.split_at(decpt as usize);
            format!("{}.{}", h, t)
        } else {
            format!("{}{}", digits, "0".repeat((decpt as usize) - digits.len()))
        };
        let body = if body.contains('.') { body } else { format!("{}.0", body) };
        format!("{}{}", sign, body)
    }
}

/// CPython `round(x, 6)` -- round-half-**even** at 6 decimal places, computed
/// EXACTLY the way CPython's `double_round` does (no intermediate
/// `x * 10^6` rounding, which diverges at exact ties -- e.g.
/// `round(9836.58905/100, 6)` must be 98.365891, not 98.36589).
///
/// CPython round-trips `_Py_dg_dtoa(x, mode=3, ndigits=6)` (the exact decimal
/// digits of x rounded to 6 places, half-even) back through correctly-rounded
/// `_Py_dg_strtod`.  Reproduced here with exact integer arithmetic:
///
///   x = m_int * 2^e_int   (m_int < 2^53, from the bit pattern)
///   x * 10^6 = q * 2^e_int, q = m_int * 10^6 < 2^73
///   k = round-half-even of the exact rational q / 2^(-e_int)  (i128, exact)
///   result = k * 10^-6 rounded to the nearest double, k < 2^53 -> single
///   correctly-rounded division (identical to strtod); k >= 2^53 -> the exact
///   decimal "k" + "e-6" through `str::parse` (correctly rounded).
///
/// x >= 2^53 is an integer, so round(x, 6) == x (CPython returns x).  For
/// x < 2^53 the e_int >= 0 branch is unreachable (e_int <= -24); the s >= 74
/// branch covers values below half the 1e-6 grid (k = 0 exactly -- q is never
/// a power of two, so the < 0.5 bound is strict).
///
/// Verified bit-identical to CPython over a 449k-value corpus (full-range
/// random doubles, DSN-style x/100, 6-dp grid ties with ULP-scale
/// perturbations, 1e-300..1e299 magnitudes): 0 mismatches.
fn py_round_6(x: f64) -> f64 {
    if !x.is_finite() || x == 0.0 {
        return x;
    }
    let y = x.abs();
    if y >= 9_007_199_254_740_992.0 {
        return x;
    }
    let bits = y.to_bits();
    let exp_bits = ((bits >> 52) & 0x7ff) as i64;
    let mant = bits & ((1u64 << 52) - 1);
    let (m_int, e_int): (i128, i128) = if exp_bits == 0 {
        (mant as i128, -1074i128)
    } else {
        ((mant as i128) + (1i128 << 52), exp_bits as i128 - 1023 - 52)
    };
    let q = m_int * 1_000_000;
    let k: i128 = if e_int >= 0 {
        q << e_int
    } else {
        let s: i128 = -e_int;
        if s >= 74 {
            0
        } else {
            let s = s as u32;
            let div = 1i128 << s;
            let floor = q / div;
            let rem = q % div;
            let twice = 2 * rem;
            if twice < div {
                floor
            } else if twice > div {
                floor + 1
            } else if floor % 2 == 0 {
                floor
            } else {
                floor + 1
            }
        }
    };
    let result = if k < (1i128 << 52) {
        k as f64 / 1_000_000.0
    } else {
        format!("{}e-6", k)
            .parse::<f64>()
            .unwrap_or_else(|_| k as f64 / 1_000_000.0)
    };
    if x < 0.0 {
        -result
    } else {
        result
    }
}

/// The three-way category the reference derives from `delta <= tolerance`.
fn category(delta: f64, tolerance: f64) -> &'static str {
    if delta <= tolerance {
        "WITHIN_TOLERANCE"
    } else {
        "BEYOND_TOLERANCE"
    }
}

/// Fold a finished entry list into a report, computing `passed` and the
/// reference's exact summary line
/// (`"{board}/{stage}: {PASS|FAIL} — {n} issues"`, em-dash included).
fn finish_report(board: &str, stage: &str, entries: Vec<DiffEntryData>) -> DiffReportData {
    let failures = entries
        .iter()
        .filter(|e| e.category == "BINARY" || e.category == "BEYOND_TOLERANCE")
        .count();
    let passed = failures == 0;
    let summary = format!(
        "{}/{}: {} — {} issues",
        board,
        stage,
        if passed { "PASS" } else { "FAIL" },
        failures
    );
    DiffReportData {
        board: board.into(),
        stage: stage.into(),
        passed,
        entries,
        summary,
    }
}

// ---------------------------------------------------------------------------
// Report data model (pure core)
// ---------------------------------------------------------------------------

/// One structured diff finding, mirroring the `DiffEntry` dataclass fields.
pub struct DiffEntryData {
    pub board: String,
    pub stage: String,
    pub category: String,
    pub entity: String,
    pub field: String,
    pub golden_value: String,
    pub candidate_value: String,
    pub delta: Option<f64>,
    pub tolerance: Option<f64>,
}

impl DiffEntryData {
    /// 9-argument constructor mirroring the 9-field `DiffEntry` dataclass
    /// the shim reconstructs via `DiffEntry(**e)`; the arity is fixed by the
    /// parity contract (VERIFICATION.md), not a design choice.
    #[expect(
        clippy::too_many_arguments,
        reason = "mirrors the 9-field DiffEntry dataclass; a builder would obscure the field-for-field parity"
    )]
    fn new(
        board: &str,
        stage: &str,
        category: &str,
        entity: String,
        field: String,
        golden_value: String,
        candidate_value: String,
        delta: Option<f64>,
        tolerance: Option<f64>,
    ) -> Self {
        DiffEntryData {
            board: board.into(),
            stage: stage.into(),
            category: category.into(),
            entity,
            field,
            golden_value,
            candidate_value,
            delta,
            tolerance,
        }
    }

    fn presence(
        board: &str,
        stage: &str,
        entity: String,
        golden_value: &str,
        candidate_value: &str,
    ) -> Self {
        Self::new(
            board,
            stage,
            "BINARY",
            entity,
            "presence".into(),
            golden_value.into(),
            candidate_value.into(),
            None,
            None,
        )
    }
}

/// A full comparison report, mirroring the `DiffReport` dataclass fields.
pub struct DiffReportData {
    pub board: String,
    pub stage: String,
    pub passed: bool,
    pub entries: Vec<DiffEntryData>,
    pub summary: String,
}

// ---------------------------------------------------------------------------
// DSN parsing + diff
// ---------------------------------------------------------------------------

static PLACES_RE: LazyLock<Regex> =
    LazyLock::new(|| static_regex(r"\(\s*place\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+\S+\s+([\d.]+)"));
static NETS_RE: LazyLock<Regex> =
    LazyLock::new(|| static_regex(r"\(\s*net\s+(\S+)\s+\(\s*pins\s+(.*?)\)"));

/// Extract `(place <ref> <x> <y> <side> <rot>)` lines into
/// `ref -> (x_mm, y_mm, rot)` with DSN units divided by 100 and rounded to
/// 6 dp (CPython `round(x/100, 6)`).
///
/// Returns `None` exactly when the reference's `try/except` would: any
/// capture group that fails `float()` (the `[\\d.]+` class admits strings
/// like `..` that `float` rejects) makes the whole parse fail. Note the
/// `[\\d.]+` class has no `-`, so negative coordinates are silently
/// skipped -- shared naive behaviour with the reference, pinned by a
/// fixture, not fixed here.
pub fn parse_dsn_places(dsn_text: &str) -> Option<BTreeMap<String, (f64, f64, f64)>> {
    let mut places = BTreeMap::new();
    for m in PLACES_RE.captures_iter(dsn_text) {
        let ref_ = m.get(1)?.as_str();
        let x = py_round_6(m.get(2)?.as_str().parse::<f64>().ok()? / 100.0);
        let y = py_round_6(m.get(3)?.as_str().parse::<f64>().ok()? / 100.0);
        let rot = py_round_6(m.get(4)?.as_str().parse::<f64>().ok()?);
        places.insert(ref_.to_string(), (x, y, rot));
    }
    Some(places)
}

/// Extract `(net <name> (pins ...))` lines into `name -> pin_count`
/// (Python `str.split()` = `split_whitespace`).  Unlike the places parse
/// this one has no failure mode in the reference (no `float()`), so it
/// always succeeds.
pub fn parse_dsn_nets(dsn_text: &str) -> BTreeMap<String, usize> {
    let mut nets = BTreeMap::new();
    for m in NETS_RE.captures_iter(dsn_text) {
        if let (Some(name), Some(pins)) = (m.get(1), m.get(2)) {
            nets.insert(name.as_str().to_string(), pins.as_str().split_whitespace().count());
        }
    }
    nets
}

/// The DSN kernel: component-place comparison (X/Y abs delta, rotation
/// delta wrapped modulo 360) + net pin-count comparison.
pub fn diff_dsn(
    board: &str,
    stage: &str,
    golden: &str,
    candidate: &str,
    tolerance: f64,
) -> DiffReportData {
    let golden_places = parse_dsn_places(golden);
    let candidate_places = parse_dsn_places(candidate);

    let (golden_places, candidate_places) = match (golden_places, candidate_places) {
        (Some(g), Some(c)) => (g, c),
        (g, c) => {
            let entries = vec![DiffEntryData::new(
                board,
                stage,
                "BINARY",
                "dsn".into(),
                "parse".into(),
                if g.is_some() { "parse_ok" } else { "parse_fail" }.into(),
                if c.is_some() { "parse_ok" } else { "parse_fail" }.into(),
                None,
                None,
            )];
            return DiffReportData {
                board: board.into(),
                stage: stage.into(),
                passed: false,
                entries,
                summary: "DSN parse failure".into(),
            };
        }
    };

    let mut entries: Vec<DiffEntryData> = Vec::new();

    let mut all_refs: BTreeSet<&str> = golden_places.keys().map(String::as_str).collect();
    all_refs.extend(candidate_places.keys().map(String::as_str));
    for ref_ in all_refs {
        match (golden_places.get(ref_), candidate_places.get(ref_)) {
            (None, Some(_)) => {
                entries.push(DiffEntryData::presence(
                    board,
                    stage,
                    format!("component {}", ref_),
                    "missing",
                    "present",
                ));
            }
            (Some(_), None) => {
                entries.push(DiffEntryData::presence(
                    board,
                    stage,
                    format!("component {}", ref_),
                    "present",
                    "missing",
                ));
            }
            (Some(g), Some(c)) => {
                for (axis, gv, cv) in [("X", g.0, c.0), ("Y", g.1, c.1), ("rotation", g.2, c.2)] {
                    let delta = if axis == "rotation" {
                        let d = (gv - cv).abs() % 360.0;
                        d.min(360.0 - d)
                    } else {
                        (gv - cv).abs()
                    };
                    let cat = category(delta, tolerance);
                    entries.push(DiffEntryData::new(
                        board,
                        stage,
                        cat,
                        format!("component {}", ref_),
                        format!("{} coordinate", axis),
                        py_str_float(gv),
                        py_str_float(cv),
                        Some(delta),
                        Some(tolerance),
                    ));
                }
            }
            (None, None) => {}
        }
    }

    let golden_nets = parse_dsn_nets(golden);
    let candidate_nets = parse_dsn_nets(candidate);
    let mut all_nets: BTreeSet<&str> = golden_nets.keys().map(String::as_str).collect();
    all_nets.extend(candidate_nets.keys().map(String::as_str));
    for net in all_nets {
        match (golden_nets.get(net), candidate_nets.get(net)) {
            (None, Some(_)) => {
                entries.push(DiffEntryData::presence(
                    board,
                    stage,
                    format!("net '{}'", net),
                    "missing",
                    "present",
                ));
            }
            (Some(_), None) => {
                entries.push(DiffEntryData::presence(
                    board,
                    stage,
                    format!("net '{}'", net),
                    "present",
                    "missing",
                ));
            }
            (Some(g), Some(c)) => {
                if g != c {
                    entries.push(DiffEntryData::new(
                        board,
                        stage,
                        "BINARY",
                        format!("net '{}'", net),
                        "pin_count".into(),
                        g.to_string(),
                        c.to_string(),
                        None,
                        None,
                    ));
                }
            }
            (None, None) => {}
        }
    }

    finish_report(board, stage, entries)
}

// ---------------------------------------------------------------------------
// SES parsing + diff
// ---------------------------------------------------------------------------

static WIRES_RE: LazyLock<Regex> = LazyLock::new(|| {
    static_regex(r"\(\s*wire\s+(\S+)\s+\(\s*path\s+\S+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)")
});

/// Extract `(wire <net> (path <layer> <width> <x1> <y1> <x2> <y2>))` lines
/// into `{net}_{enumerate-index} -> [(x1, y1), (x2, y2)]`, matching the
/// reference's `f"{net}_{idx}"` keying (idx counts ALL wires in document
/// order).  Returns `None` on any `float()` failure, like the reference's
/// `try/except`.
pub fn parse_ses_wires(ses_text: &str) -> Option<BTreeMap<String, Vec<(f64, f64)>>> {
    let mut wires = BTreeMap::new();
    for (idx, m) in WIRES_RE.captures_iter(ses_text).enumerate() {
        let net = m.get(1)?.as_str();
        let x1 = m.get(2)?.as_str().parse::<f64>().ok()?;
        let y1 = m.get(3)?.as_str().parse::<f64>().ok()?;
        let x2 = m.get(4)?.as_str().parse::<f64>().ok()?;
        let y2 = m.get(5)?.as_str().parse::<f64>().ok()?;
        wires.insert(format!("{}_{}", net, idx), vec![(x1, y1), (x2, y2)]);
    }
    Some(wires)
}

/// The SES kernel: per-wire point comparison by Euclidean distance.
///
/// The distance uses `powf(2.0)` (libm `pow`) exactly where the reference
/// writes `(gpt[0] - cpt[0]) ** 2`: Python's float `**` is libm `pow`, and
/// `pow(x, 2.0)` is *not* guaranteed bit-identical to `x * x` -- using
/// multiplication here would inject a last-ULP divergence the differential
/// would catch.
pub fn diff_ses(
    board: &str,
    stage: &str,
    golden: &str,
    candidate: &str,
    tolerance: f64,
) -> DiffReportData {
    let golden_wires = parse_ses_wires(golden);
    let candidate_wires = parse_ses_wires(candidate);

    let (golden_wires, candidate_wires) = match (golden_wires, candidate_wires) {
        (Some(g), Some(c)) => (g, c),
        (g, c) => {
            let entries = vec![DiffEntryData::new(
                board,
                stage,
                "BINARY",
                "ses".into(),
                "parse".into(),
                if g.is_some() { "parse_ok" } else { "parse_fail" }.into(),
                if c.is_some() { "parse_ok" } else { "parse_fail" }.into(),
                None,
                None,
            )];
            return DiffReportData {
                board: board.into(),
                stage: stage.into(),
                passed: false,
                entries,
                summary: "SES parse failure".into(),
            };
        }
    };

    let mut entries: Vec<DiffEntryData> = Vec::new();

    let mut all_keys: BTreeSet<&str> = golden_wires.keys().map(String::as_str).collect();
    all_keys.extend(candidate_wires.keys().map(String::as_str));
    for key in all_keys {
        match (golden_wires.get(key), candidate_wires.get(key)) {
            (None, Some(_)) => {
                entries.push(DiffEntryData::presence(
                    board,
                    stage,
                    format!("wire_{}", key),
                    "missing",
                    "present",
                ));
            }
            (Some(_), None) => {
                entries.push(DiffEntryData::presence(
                    board,
                    stage,
                    format!("wire_{}", key),
                    "present",
                    "missing",
                ));
            }
            (Some(g), Some(c)) => {
                for (i, (gpt, cpt)) in g.iter().zip(c.iter()).enumerate() {
                    let delta = ((gpt.0 - cpt.0).powf(2.0) + (gpt.1 - cpt.1).powf(2.0)).sqrt();
                    let cat = category(delta, tolerance);
                    entries.push(DiffEntryData::new(
                        board,
                        stage,
                        cat,
                        format!("wire_{}", key),
                        format!("point_{}", i),
                        format!("({}, {})", py_str_float(gpt.0), py_str_float(gpt.1)),
                        format!("({}, {})", py_str_float(cpt.0), py_str_float(cpt.1)),
                        Some(delta),
                        Some(tolerance),
                    ));
                }
            }
            (None, None) => {}
        }
    }

    finish_report(board, stage, entries)
}

// ---------------------------------------------------------------------------
// JSON diff
// ---------------------------------------------------------------------------

/// The reference's `type(v).__name__` for the JSON value domain.
fn json_type_name(v: &Value) -> &'static str {
    match v {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => {
            if n.is_i64() || n.is_u64() {
                "int"
            } else {
                "float"
            }
        }
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// CPython `str(int)` for the integer-arm of the numeric branch.
fn number_int_str(n: &serde_json::Number) -> String {
    if let Some(i) = n.as_i64() {
        i.to_string()
    } else if let Some(u) = n.as_u64() {
        u.to_string()
    } else {
        // Unreachable when both numbers type-name as "int".
        n.to_string()
    }
}

/// The tolerance-aware recursive JSON diff (`_json_diff_recursive`).
///
/// Branch order and semantics match the reference exactly: strict type-name
/// equality first (`dict`/`list`/`int`/`float`/`bool`/`str`/`NoneType`),
/// then dict key-union in sorted order, list length then index recursion,
/// float-vs-float tolerance categories (`delta <= tolerance` is WITHIN),
/// and everything else compared by `str()` rendering.
fn json_diff_recursive(
    golden_val: &Value,
    candidate_val: &Value,
    tolerance: f64,
    board: &str,
    stage: &str,
    path: &str,
    entries: &mut Vec<DiffEntryData>,
) {
    if json_type_name(golden_val) != json_type_name(candidate_val) {
        entries.push(DiffEntryData::new(
            board,
            stage,
            "BINARY",
            if path.is_empty() { "root".into() } else { path.into() },
            "type".into(),
            json_type_name(golden_val).into(),
            json_type_name(candidate_val).into(),
            None,
            None,
        ));
        return;
    }

    let entity = || {
        if path.is_empty() {
            "root".to_string()
        } else {
            path.to_string()
        }
    };

    match golden_val {
        Value::Object(g) => {
            let c = match candidate_val {
                Value::Object(c) => c,
                _ => return,
            };
            let mut all_keys: BTreeSet<&str> = g.keys().map(String::as_str).collect();
            all_keys.extend(c.keys().map(String::as_str));
            for k in all_keys {
                let new_path = if path.is_empty() {
                    k.to_string()
                } else {
                    format!("{}.{}", path, k)
                };
                match (g.get(k), c.get(k)) {
                    (None, Some(_)) => {
                        entries.push(DiffEntryData::presence(
                            board,
                            stage,
                            new_path,
                            "missing",
                            "present",
                        ));
                    }
                    (Some(_), None) => {
                        entries.push(DiffEntryData::presence(
                            board,
                            stage,
                            new_path,
                            "present",
                            "missing",
                        ));
                    }
                    (Some(gv), Some(cv)) => {
                        json_diff_recursive(gv, cv, tolerance, board, stage, &new_path, entries);
                    }
                    (None, None) => {}
                }
            }
        }
        Value::Array(g) => {
            let c = match candidate_val {
                Value::Array(c) => c,
                _ => return,
            };
            if g.len() != c.len() {
                entries.push(DiffEntryData::new(
                    board,
                    stage,
                    "BINARY",
                    entity(),
                    "length".into(),
                    g.len().to_string(),
                    c.len().to_string(),
                    None,
                    None,
                ));
            } else {
                for (i, (gv, cv)) in g.iter().zip(c.iter()).enumerate() {
                    json_diff_recursive(
                        gv,
                        cv,
                        tolerance,
                        board,
                        stage,
                        &format!("{}[{}]", path, i),
                        entries,
                    );
                }
            }
        }
        Value::Number(g) => {
            let c = match candidate_val {
                Value::Number(c) => c,
                _ => return,
            };
            if g.is_f64() && c.is_f64() {
                let gv = match g.as_f64() {
                    Some(v) => v,
                    None => return,
                };
                let cv = match c.as_f64() {
                    Some(v) => v,
                    None => return,
                };
                let delta = (gv - cv).abs();
                let cat = category(delta, tolerance);
                entries.push(DiffEntryData::new(
                    board,
                    stage,
                    cat,
                    entity(),
                    "value".into(),
                    py_str_float(gv),
                    py_str_float(cv),
                    Some(delta),
                    Some(tolerance),
                ));
            } else {
                let gs = number_int_str(g);
                let cs = number_int_str(c);
                if gs != cs {
                    entries.push(DiffEntryData::new(
                        board,
                        stage,
                        "BINARY",
                        entity(),
                        "value".into(),
                        gs,
                        cs,
                        None,
                        None,
                    ));
                }
            }
        }
        Value::Bool(g) => {
            // CPython's `bool` is an `int` subclass, so `isinstance(True,
            // (int, float))` is True and bools land in the numeric branch,
            // compared by `!=` and rendered with `str()` ("True"/"False").
            let c = match candidate_val {
                Value::Bool(c) => c,
                _ => return,
            };
            if g != c {
                entries.push(DiffEntryData::new(
                    board,
                    stage,
                    "BINARY",
                    entity(),
                    "value".into(),
                    if *g { "True" } else { "False" }.into(),
                    if *c { "True" } else { "False" }.into(),
                    None,
                    None,
                ));
            }
        }
        Value::Null => {
            // The reference's else-branch: `str(None)` == "None" on both
            // sides, so two Nulls never produce an entry.
        }
        Value::String(g) => {
            let c = match candidate_val {
                Value::String(c) => c,
                _ => return,
            };
            if g != c {
                entries.push(DiffEntryData::new(
                    board,
                    stage,
                    "BINARY",
                    entity(),
                    "value".into(),
                    g.clone(),
                    c.clone(),
                    None,
                    None,
                ));
            }
        }
    }
}

/// The JSON kernel: parse both documents (`serde_json::from_str`), then the
/// recursive tolerance diff.  Parse failures produce the reference's exact
/// golden/candidate distinction and summary strings.
pub fn diff_json(
    board: &str,
    stage: &str,
    golden: &str,
    candidate: &str,
    tolerance: f64,
) -> DiffReportData {
    let gj = match serde_json::from_str::<Value>(golden) {
        Ok(v) => v,
        Err(_) => {
            let entries = vec![DiffEntryData::new(
                board,
                stage,
                "BINARY",
                "json".into(),
                "parse".into(),
                "parse_fail".into(),
                "parse_ok".into(),
                None,
                None,
            )];
            return DiffReportData {
                board: board.into(),
                stage: stage.into(),
                passed: false,
                entries,
                summary: "Golden JSON parse failure".into(),
            };
        }
    };
    let cj = match serde_json::from_str::<Value>(candidate) {
        Ok(v) => v,
        Err(_) => {
            let entries = vec![DiffEntryData::new(
                board,
                stage,
                "BINARY",
                "json".into(),
                "parse".into(),
                "parse_ok".into(),
                "parse_fail".into(),
                None,
                None,
            )];
            return DiffReportData {
                board: board.into(),
                stage: stage.into(),
                passed: false,
                entries,
                summary: "Candidate JSON parse failure".into(),
            };
        }
    };

    let mut entries: Vec<DiffEntryData> = Vec::new();
    json_diff_recursive(&gj, &cj, tolerance, board, stage, "", &mut entries);
    finish_report(board, stage, entries)
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod py_bridge {
    use pyo3::prelude::*;

    /// This module has no Python exports.  Keep an empty registration hook so
    /// the crate's module assembly remains stable while the Rust kernels stay
    /// usable by native and wasm tests.
    pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
        Ok(())
    }
}

#[cfg(feature = "python")]
pub use py_bridge::register;

// ---------------------------------------------------------------------------
// Rust unit tests (native + wasm tier)
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn py_str_float_known_values() {
        for (x, expect) in [
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (50.0, "50.0"),
            (2.0, "2.0"),
            (0.05, "0.05"),
            (52.123456, "52.123456"),
            (0.1, "0.1"),
            (1.0005, "1.0005"),
            (1e15, "1000000000000000.0"),
            (1e16, "1e+16"),
            (1e17, "1e+17"),
            (1e-4, "0.0001"),
            (1e-5, "1e-05"),
            (1e-7, "1e-07"),
            (f64::NAN, "nan"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
            (2.0f64.powi(53), "9007199254740992.0"),
            (1.7976931348623157e308, "1.7976931348623157e+308"),
            (5e-324, "5e-324"),
            (123456789.123, "123456789.123"),
            (-0.05, "-0.05"),
            (-1e-5, "-1e-05"),
            (0.0005, "0.0005"),
        ] {
            assert_eq!(py_str_float(x), expect, "py_str_float({x:?})");
        }
    }

    #[cfg_attr(test, test)]
    fn py_round_6_matches_cpython() {
        assert_eq!(py_round_6(5000.0 / 100.0), 50.0);
        assert_eq!(py_round_6(0.05 / 100.0), 0.0005);
        assert_eq!(py_round_6(50.01), 50.01);
        // round-half-even at the 6th decimal (CPython-verified pins):
        assert_eq!(py_round_6(2.675), 2.675);
        assert_eq!(py_round_6(0.0000005), 0.0);
        assert_eq!(py_round_6(1.5e-6), 2e-6);
        assert_eq!(py_round_6(0.5e-6), 0.0);
        // The exact-tie regression: the naive `x*1e6` path rounds the
        // product to 98365890.5 (a tie) and picks the even neighbour 98365890,
        // while CPython rounds the EXACT value (98.365890500000006...) up to
        // 98.365891. This is the zone_geometry.dsn coordinate that exposed it.
        assert_eq!(py_round_6(9836.58905 / 100.0), 98.365891);
        // Above 2^53 x is an integer: round(x, 6) == x.
        assert_eq!(py_round_6(1e209), 1e209);
    }

    #[cfg_attr(test, test)]
    fn parse_dsn_places_basic() {
        let dsn = "(pcb t (placement (place U1 5000 5000 front 0) (place U2 2500 4000 front 90)))";
        let p = parse_dsn_places(dsn).unwrap();
        assert_eq!(p.get("U1"), Some(&(50.0, 50.0, 0.0)));
        assert_eq!(p.get("U2"), Some(&(25.0, 40.0, 90.0)));
    }

    #[cfg_attr(test, test)]
    fn parse_dsn_places_fails_on_bad_float() {
        assert!(parse_dsn_places("(place U1 .. 5000 front 0)").is_none());
        assert!(parse_dsn_places("").is_some());
    }

    #[cfg_attr(test, test)]
    fn parse_dsn_nets_counts_pins() {
        let dsn = "(network (net N1 (pins A-1 B-2)) (net N2 (pins )))";
        let n = parse_dsn_nets(dsn);
        assert_eq!(n.get("N1"), Some(&2));
        assert_eq!(n.get("N2"), Some(&0));
        // `(pins))` with no whitespace after `pins` does not match the
        // pattern (pins\s+) on either side -- shared naive behaviour.
        assert!(!parse_dsn_nets("(network (net N3 (pins)))").contains_key("N3"));
    }

    #[cfg_attr(test, test)]
    fn parse_ses_wires_keying() {
        let ses = "(session (wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000)) (wire NET2 (path 1 0.200000 1.000000 2.000000 3.000000 4.000000)))";
        let w = parse_ses_wires(ses).unwrap();
        assert_eq!(w.get("NET1_0"), Some(&vec![(0.0, 0.0), (10.0, 10.0)]));
        assert_eq!(w.get("NET2_1"), Some(&vec![(1.0, 2.0), (3.0, 4.0)]));
    }

    #[cfg_attr(test, test)]
    fn rotation_delta_wraps_mod_360() {
        let g = "(pcb (placement (place U1 0 0 front 10)))";
        let c = "(pcb (placement (place U1 0 0 front 370)))";
        let r = diff_dsn("b", "s", g, c, 0.001);
        assert!(r.passed);
        for e in &r.entries {
            if e.field == "rotation coordinate" {
                assert_eq!(e.delta, Some(0.0));
            }
        }
    }

    #[cfg_attr(test, test)]
    fn json_diff_tolerance_boundary() {
        let g = r#"{"v": 1.0}"#;
        let c = r#"{"v": 1.25}"#;
        let r = diff_json("b", "s", g, c, 0.25);
        assert!(r.passed);
        assert_eq!(r.entries[0].category, "WITHIN_TOLERANCE");
        let c2 = r#"{"v": 1.250001}"#;
        let r2 = diff_json("b", "s", g, c2, 0.25);
        assert!(!r2.passed);
        assert_eq!(r2.entries[0].category, "BEYOND_TOLERANCE");
    }

    #[cfg_attr(test, test)]
    fn json_diff_type_names() {
        // bool vs int: type() differs (bool vs int) -- CPython bool is an
        // int subclass but type() is strict.
        let r = diff_json("b", "s", r#"{"x": true}"#, r#"{"x": 1}"#, 1.0);
        assert!(!r.passed);
        assert_eq!(r.entries[0].golden_value, "bool");
        assert_eq!(r.entries[0].candidate_value, "int");
        // null vs string: NoneType vs str
        let r = diff_json("b", "s", r#"{"x": null}"#, r#"{"x": "a"}"#, 1.0);
        assert_eq!(r.entries[0].golden_value, "NoneType");
        assert_eq!(r.entries[0].candidate_value, "str");
    }

    #[cfg_attr(test, test)]
    fn json_diff_bool_rendering() {
        // bool vs bool uses str(): "True"/"False".
        let r = diff_json("b", "s", r#"{"x": true}"#, r#"{"x": false}"#, 1.0);
        assert!(!r.passed);
        assert_eq!(r.entries[0].golden_value, "True");
        assert_eq!(r.entries[0].candidate_value, "False");
    }

    #[cfg_attr(test, test)]
    fn json_diff_nested_paths() {
        let g = r#"{"a": {"b": [1, 2.0, {"c": "x"}]}}"#;
        let c = r#"{"a": {"b": [1, 3.0, {"c": "y"}]}}"#;
        let r = diff_json("b", "s", g, c, 0.5);
        assert!(!r.passed);
        let entities: Vec<&str> = r.entries.iter().map(|e| e.entity.as_str()).collect();
        assert!(entities.contains(&"a.b[1]"), "entries: {entities:?}");
        assert!(entities.contains(&"a.b[2].c"), "entries: {entities:?}");
    }

    #[cfg_attr(test, test)]
    fn empty_inputs_pass_or_fail_per_format() {
        let d = diff_dsn("b", "s", "", "", 0.001);
        assert!(d.passed && d.entries.is_empty());
        let s = diff_ses("b", "s", "", "", 0.001);
        assert!(s.passed && s.entries.is_empty());
        let j = diff_json("b", "s", "", "", 0.001);
        assert!(!j.passed);
        assert_eq!(j.summary, "Golden JSON parse failure");
    }

    #[cfg_attr(test, test)]
    fn summary_uses_python_fstring() {
        let g = "(pcb (placement (place U1 0 0 front 0)))";
        let c = "(pcb (placement (place U1 100 0 front 0)))";
        let r = diff_dsn("temper", "apply_placements", g, c, 0.001);
        assert_eq!(r.summary, "temper/apply_placements: FAIL — 1 issues");
        assert!(!r.passed);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("golden_diff::tests::py_str_float_known_values", py_str_float_known_values),
        ("golden_diff::tests::py_round_6_matches_cpython", py_round_6_matches_cpython),
        ("golden_diff::tests::parse_dsn_places_basic", parse_dsn_places_basic),
        ("golden_diff::tests::parse_dsn_places_fails_on_bad_float", parse_dsn_places_fails_on_bad_float),
        ("golden_diff::tests::parse_dsn_nets_counts_pins", parse_dsn_nets_counts_pins),
        ("golden_diff::tests::parse_ses_wires_keying", parse_ses_wires_keying),
        ("golden_diff::tests::rotation_delta_wraps_mod_360", rotation_delta_wraps_mod_360),
        ("golden_diff::tests::json_diff_tolerance_boundary", json_diff_tolerance_boundary),
        ("golden_diff::tests::json_diff_type_names", json_diff_type_names),
        ("golden_diff::tests::json_diff_bool_rendering", json_diff_bool_rendering),
        ("golden_diff::tests::json_diff_nested_paths", json_diff_nested_paths),
        ("golden_diff::tests::empty_inputs_pass_or_fail_per_format", empty_inputs_pass_or_fail_per_format),
        ("golden_diff::tests::summary_uses_python_fstring", summary_uses_python_fstring),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(all(test, not(feature = "wasm-test-registry")))]
mod proptests {
    use super::*;

    #[test]
    fn py_str_float_round_trips() {
        use proptest::prelude::*;
        proptest!(|(x in -1e9f64..1e9f64)| {
            let s = py_str_float(x);
            let back: f64 = s.parse().unwrap_or_else(|_| panic!("py_str_float produced unparseable '{}'", s));
            prop_assert_eq!(back, x, "py_str_float({}) -> '{}' does not round-trip", x, s);
        });
    }

    #[test]
    fn py_str_float_has_no_leading_plus() {
        use proptest::prelude::*;
        proptest!(|(x in -1e6f64..1e6f64)| {
            let s = py_str_float(x);
            prop_assert!(!s.starts_with('+'), "py_str_float({x}) -> '{s}' has leading plus");
        });
    }

    #[test]
    fn diff_dsn_identical_is_passed() {
        use proptest::prelude::*;
        proptest!(|(x in 0u32..10000u32, y in 0u32..10000u32, rot in 0u32..720u32)| {
            let doc = format!("(pcb (placement (place U1 {} {} front {})))", x, y, rot);
            let r = diff_dsn("b", "s", &doc, &doc, 0.001);
            prop_assert!(r.passed, "identical DSN not passed: {}", r.summary);
            prop_assert!(r.entries.iter().all(|e| e.category == "WITHIN_TOLERANCE"));
        });
    }

    #[test]
    fn diff_json_identity_is_passed() {
        use proptest::prelude::*;
        proptest!(|(i in 0i64..10000i64, f in -1000.0f64..1000.0f64)| {
            let doc = format!(r#"{{"i": {}, "f": {}}}"#, i, f);
            let r = diff_json("b", "s", &doc, &doc, 0.001);
            prop_assert!(r.passed, "identical JSON not passed: {}", r.summary);
        });
    }
}
