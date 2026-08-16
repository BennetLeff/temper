//! Wave 4 Phase 3 candidate 3: the KiCad parse engine.
//!
//! Port of the kiutils-based parse path under
//! `temper_placer/io/{kicad_parser,_parse_board,_parse_modules,_parse_nets,
//! _parse_tracks,_parse_zones,_kicad_types,kicad_metadata}.py` to Rust. The
//! engine parses the raw `.kicad_pcb` s-expression text itself, so kiutils
//! leaves the product boundary (parent plan R4); the Python modules become
//! delegation shims and the differential pins bit-identical output against a
//! verbatim kiutils oracle (see `tests/io/test_parse_engine_rust_differential.py`).
//!
//! ## The tokenizer is kiutils' tokenizer
//!
//! kiutils 1.4.8 tokenizes with a hand-written regex
//! (`kiutils/utils/sexpr.py`). Its grammar is *not* "any number is a number":
//!
//! - a decimal token (`[+-]?\d+\.\d+`) is numeric **only when followed by a
//!   space or `)`**, and parses via `float()`; if the float is integral it is
//!   converted to an **int** (`5.0` -> `5`);
//! - an integer token (`-?\d+`) is numeric **only when followed by a space or
//!   `)`** and stays an **int** (a leading `+` is numeric only in the decimal
//!   form: `+5` is a bare string, `+5.0` is the int 5);
//! - a quoted string is a string token **only when followed by `)` or
//!   whitespace** (`(?:(?=\))|(?=\s))` after the closing quote); otherwise —
//!   including unterminated strings — the whole run (quotes included) is a
//!   bare token (`"R1"(` tokenizes as the bare `"R1"`);
//! - `^` is excluded from bare tokens (`[^(^)\s]`) and is skipped entirely:
//!   `5^0` tokenizes as `5`, `0`;
//! - anything else (scientific notation, `.5`, `0x...`) is a string.
//!
//! The int-vs-float distinction is load-bearing: the extraction's outputs
//! (e.g. `Board.origin`, `Component._rotation_deg`, net ids) keep the token
//! type, and the differential carries the concrete type in every comparison
//! key. The corpus contains no scientific-notation numeric tokens (verified:
//! 39,753 distinct numeric tokens, all plain decimals/ints), so Rust
//! `str::parse::<f64>()` reproduces Python `float()` bit-for-bit (both are
//! IEEE round-to-nearest; the plan's Q1 float-parse-parity assumption,
//! verified on the corpus before the engine was claimed).
//!
//! ## Known quirks reproduced faithfully
//!
//! - A pad whose `(drill ...)` token has no diameter (only `(offset ...)`)
//!   gets the raw `['offset', x, y]` list stored as `DrillDefinition.diameter`
//!   (kiutils 1.4.8 puts `exp[1]` there verbatim). Seen on the piantor corpus.
//! - `DrillDefinition` objects (not floats) flow into `Pin.drill` /
//!   `PadData.drill` for pads with a drill token.
//! - Board-level `arc` items count as traces (they have `start`/`end`).
//! - The footprint `properties` dict is keyed by property name; `entryName`
//!   is derived from `libId` by splitting at the FIRST colon.
//! - Board geometry min/max keeps the operand type: an all-integer
//!   Edge.Cuts outline yields an integer `Board.origin` / `width` / `height`.
//!
//! ## Fail-closed family (kiutils raises -> the engine raises)
//!
//! kiutils' `from_sexpr` raises on several malformed tokens that the walkers
//! would otherwise silently default: a nameless `(net N)` on a pad or at
//! board level (`Net.from_sexpr` does `exp[2]`), a position list shorter
//! than 3 items (`Position.from_sexpr`), an oval drill without its width
//! (`exp[3]`), and a footprint whose libId token is not an atom (kiutils
//! stores the raw list as entryName and the oracle raises AttributeError on
//! it). `raw_board_from_tree` records these into an error vec and
//! `parse_kicad_document` fails the whole parse — a malformed token can
//! never degrade to a default value (fail-open). Segment/via/arc `(net N)`
//! tokens are NOT in this family: kiutils keeps the raw int there
//! (`object.net = item[1]`), so truthiness semantics match as-is.
//!
//! ## GEOS boundary (kicad_metadata courtyards)
//!
//! The courtyard polygons are computed by shapely/GEOS
//! (`buffer`/`convex_hull`/`unary_union`) which is not reimplementable in
//! Rust bit-exactly (see MIGRATION_PHASE_GUIDE "Numerical traps"). The engine
//! therefore produces the raw courtyard inputs (fp_poly coords, fp_circle
//! center+end, fp_rect corners, fp_line/fp_arc points) and the Python shim
//! runs the *same* shapely code on them; the differential proves the raw
//! inputs are bit-identical, so the GEOS outputs are equal by construction.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3::IntoPyObjectExt;

use crate::board_contracts::Board;
use crate::netlist_contracts::{dataclass_eq, dataclass_repr, repr_of, unhashable, Netlist};

// ===========================================================================
// 1. Tokenizer (kiutils-exact grammar)
// ===========================================================================

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum KiAtom {
    Str(String),
    Int(i64),
    Float(f64),
    Bare(String),
    /// An opaque sub-list stored verbatim (kiutils stores the `(offset ...)`
    /// sub-list into `DrillDefinition.diameter` when a drill carries no
    /// diameter -- reproduced here so the object reprs identically).
    List(Vec<KiNode>),
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum KiNode {
    Atom(KiAtom),
    List(Vec<KiNode>),
}

/// Is `word` a kiutils-numeric token, i.e. does the regex
/// `[+-]?\d+\.\d+|\-?\d+` match the whole word with `next` (space or `)`)
/// satisfying the lookahead?
fn classify_number(word: &str, next_is_space_or_paren: bool) -> Option<KiAtom> {
    if !next_is_space_or_paren {
        return None;
    }
    let bytes = word.as_bytes();
    let n = bytes.len();
    if n == 0 {
        return None;
    }
    let mut i = 0usize;
    let mut plus = false;
    if bytes[i] == b'+' {
        plus = true;
        i += 1;
    } else if bytes[i] == b'-' {
        i += 1;
    }
    let mut digits_before = 0usize;
    while i < n && bytes[i].is_ascii_digit() {
        i += 1;
        digits_before += 1;
    }
    if digits_before == 0 {
        return None;
    }
    let mut is_decimal = false;
    if i < n && bytes[i] == b'.' {
        is_decimal = true;
        i += 1;
        let mut digits_after = 0usize;
        while i < n && bytes[i].is_ascii_digit() {
            i += 1;
            digits_after += 1;
        }
        if digits_after == 0 {
            return None;
        }
    }
    if i != n {
        return None; // trailing junk -> bare string (matches kiutils `s`)
    }
    if !is_decimal && plus {
        // kiutils' integer form is `\-?\d+` -- a leading `+` is numeric
        // only in the decimal form (`+5` is a bare string, `+5.0` is a
        // number that then becomes int 5).
        return None;
    }
    if is_decimal {
        // `float(word)` then `if v.is_integer(): int(v)` -- the kiutils num
        // branch. A decimal token whose float value is integral becomes an
        // int (`5.0` -> `5`, `-0.0` -> `0`).
        let v: f64 = word.parse().ok()?;
        if v.fract() == 0.0 {
            // Python int() of an integral float is exact for |v| < 2^53; the
            // corpus max is ~1e10. Out-of-i64-range integral floats stay
            // floats (documented deviation, not exercised by the corpus).
            // NOTE: i64::MIN/MAX as f64 -- never `2i64.pow(63)` (that
            // overflows and wraps to i64::MIN in release, silently making
            // this check always-false).
            if v >= i64::MIN as f64 && v < i64::MAX as f64 {
                return Some(KiAtom::Int(v as i64));
            }
            return Some(KiAtom::Float(v));
        }
        return Some(KiAtom::Float(v));
    }
    let v: i64 = word.parse().ok()?;
    Some(KiAtom::Int(v))
}

/// Tokenize `input` with kiutils' exact token grammar, then build the tree.
/// Returns `Err` on unbalanced parentheses (kiutils raises `AssertionError` /
/// `IndexError` there; we raise a typed error instead -- both sides raise on
/// malformed input, which is all the differential requires).
fn parse_ki_document(input: &str) -> Result<Vec<KiNode>, String> {
    let bytes = input.as_bytes();
    let mut i = 0usize;
    let mut stack: Vec<Vec<KiNode>> = vec![Vec::new()];
    let n = bytes.len();
    while i < n {
        let c = bytes[i] as char;
        if c.is_whitespace() {
            i += 1;
            continue;
        }
        if c == '^' {
            // kiutils' bare-token regex `(?P<s>[^(^)\s]+)` EXCLUDES `^`,
            // so re.finditer skips the char entirely -- it is part of no
            // token. `5^0` tokenizes as `5`, `0` with the caret dropped.
            i += 1;
            continue;
        }
        if c == '(' {
            stack.push(Vec::new());
            i += 1;
            continue;
        }
        if c == ')' {
            if stack.len() == 1 {
                return Err("Trouble with nesting of brackets".to_string());
            }
            let done = stack.pop().ok_or_else(|| "Trouble with nesting of brackets".to_string())?;
            stack
                .last_mut()
                .ok_or_else(|| "Trouble with nesting of brackets".to_string())?
                .push(KiNode::List(done));
            i += 1;
            continue;
        }
        if c == '"' {
            // kiutils' `sq` branch:
            //   `"(?:[^"]|(?<=\\)")*"(?:(?=\))|(?=\s)))`
            // A quoted string is a STRING token only when a closing quote is
            // found AND the next char is `)` or whitespace. Otherwise the
            // whole run (quotes included) falls through to the bare-token
            // branch below -- kiutils' `s` class `[^(^)\s]+` accepts `"` and
            // `\` as ordinary characters, so `"R1"(` tokenizes as the bare
            // token `"R1"` (quotes preserved). Unterminated strings are bare
            // tokens too (the `sq` alternative never matches).
            let mut scan = i + 1;
            let mut closed_at: Option<usize> = None;
            while scan < n {
                let cur = bytes[scan] as char;
                if cur == '\\' && scan + 1 < n && bytes[scan + 1] as char == '"' {
                    scan += 2;
                    continue;
                }
                if cur == '"' {
                    closed_at = Some(scan);
                    break;
                }
                scan += 1;
            }
            if let Some(close) = closed_at {
                let after = if close + 1 < n { Some(bytes[close + 1] as char) } else { None };
                // Python `\s` = [ \t\n\r\f\v] -- the same set the bare scan
                // and whitespace skip use via char::is_whitespace (U+0009..D
                // + U+0020), spelled out here so the lookahead cannot drift.
                let is_string = matches!(
                    after,
                    Some(')') | Some(' ') | Some('\t') | Some('\n') | Some('\r') | Some('\x0c') | Some('\x0b')
                );
                if is_string {
                    let raw = &input[i..=close];
                    let inner = &raw[1..raw.len() - 1];
                    // Only `\"` is unescaped -- a literal backslash is NOT
                    // (`\\` stays `\\`).
                    let unescaped = inner.replace("\\\"", "\"");
                    stack
                        .last_mut()
                        .ok_or_else(|| "Trouble with nesting of brackets".to_string())?
                        .push(KiNode::Atom(KiAtom::Str(unescaped)));
                    i = close + 1;
                    continue;
                }
            }
            // fall through: the `"` starts a bare token (quotes preserved)
        }
        // bare token: consume until whitespace / paren / `^`. The delimiter
        // decides whether the word can be numeric (kiutils' num lookahead
        // `[\ \)]`).
        let start = i;
        while i < n {
            let cur = bytes[i] as char;
            if cur.is_whitespace() || cur == '(' || cur == ')' || cur == '^' {
                break;
            }
            i += 1;
        }
        let word = &input[start..i];
        let next = if i < n { bytes[i] as char } else { '\0' };
        let next_is_ok = i < n && (next == ' ' || next == ')');
        let top = stack.last_mut().ok_or_else(|| "Trouble with nesting of brackets".to_string())?;
        if let Some(atom) = classify_number(word, next_is_ok) {
            top.push(KiNode::Atom(atom));
        } else {
            top.push(KiNode::Atom(KiAtom::Bare(word.to_string())));
        }
    }
    if stack.len() != 1 {
        return Err("Trouble with nesting of brackets".to_string());
    }
    stack.pop().ok_or_else(|| "Trouble with nesting of brackets".to_string())
}

// ===========================================================================
// 2. Python-numeric-tower fidelity (int vs float must not hide)
// ===========================================================================

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) enum Num {
    I(i64),
    F(f64),
}

impl Num {
    fn as_f64(&self) -> f64 {
        match self {
            Num::I(v) => *v as f64,
            Num::F(v) => *v,
        }
    }

    fn is_truthy(&self) -> bool {
        match self {
            Num::I(v) => *v != 0,
            Num::F(v) => *v != 0.0,
        }
    }

    /// `a + b` with Python's int+int stays int (exact); any float operand
    /// widens to float. i64 overflow falls back to float (Python ints are
    /// unbounded; the corpus never approaches i64 range).
    fn add(&self, o: &Num) -> Num {
        match (self, o) {
            (Num::I(a), Num::I(b)) => match a.checked_add(*b) {
                Some(v) => Num::I(v),
                None => Num::F(*a as f64 + *b as f64),
            },
            (Num::I(a), Num::F(b)) => Num::F(*a as f64 + *b),
            (Num::F(a), Num::I(b)) => Num::F(*a + *b as f64),
            (Num::F(a), Num::F(b)) => Num::F(*a + *b),
        }
    }

    fn sub(&self, o: &Num) -> Num {
        match (self, o) {
            (Num::I(a), Num::I(b)) => match a.checked_sub(*b) {
                Some(v) => Num::I(v),
                None => Num::F(*a as f64 - *b as f64),
            },
            (Num::I(a), Num::F(b)) => Num::F(*a as f64 - *b),
            (Num::F(a), Num::I(b)) => Num::F(*a - *b as f64),
            (Num::F(a), Num::F(b)) => Num::F(*a - *b),
        }
    }

    /// `min(a, b)` -- Python's `min` returns the FIRST operand on equality
    /// and preserves the operand type (int stays int).
    fn py_min(a: Num, b: Num) -> Num {
        if b.as_f64() < a.as_f64() {
            b
        } else {
            a
        }
    }

    fn py_max(a: Num, b: Num) -> Num {
        if b.as_f64() > a.as_f64() {
            b
        } else {
            a
        }
    }

    fn is_finite(&self) -> bool {
        self.as_f64().is_finite()
    }

    /// `float(x)`.
    fn to_f64(self) -> f64 {
        self.as_f64()
    }
}

/// `str(x)` as CPython renders it: ints as decimal, floats via the shortest
/// round-trip repr with Python's fixed-vs-scientific thresholds.
fn num_to_string(v: Num) -> String {
    match v {
        Num::I(i) => i.to_string(),
        Num::F(f) => py_repr_f64(f).unwrap_or_else(|e| format!("<repr-error:{e}>")),
    }
}

/// CPython's `repr()`/`str()` of a float: shortest round-trip digits, fixed
/// notation for `1e-4 <= |v| < 1e16` (with a mandatory `.0` on integral
/// values), scientific otherwise (`1e-05`, `1e+16`), exponent zero-padded to
/// 2 digits.
fn py_repr_f64(v: f64) -> Result<String, String> {
    if v.is_nan() {
        return Ok("nan".to_string());
    }
    if v.is_infinite() {
        return Ok(if v < 0.0 { "-inf".to_string() } else { "inf".to_string() });
    }
    if v == 0.0 {
        return Ok(if v.is_sign_negative() { "-0.0".to_string() } else { "0.0".to_string() });
    }
    let s = format!("{v:e}");
    let (mant, exp) = s
        .split_once('e')
        .ok_or_else(|| format!("format e produced no exponent for {v}"))?;
    let exp: i32 = exp.parse().map_err(|_| format!("format e produced a non-numeric exponent for {v}"))?;
    let (neg, mant) = match mant.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, mant),
    };
    let digits: String = mant.chars().filter(|c| *c != '.').collect();
    let mut out = String::new();
    if neg {
        out.push('-');
    }
    if (-4..16).contains(&exp) {
        let point_pos = exp + 1;
        if point_pos <= 0 {
            out.push_str("0.");
            for _ in 0..(-point_pos) {
                out.push('0');
            }
            out.push_str(&digits);
        } else if point_pos as usize >= digits.len() {
            out.push_str(&digits);
            for _ in 0..(point_pos as usize - digits.len()) {
                out.push('0');
            }
            out.push_str(".0");
        } else {
            let (a, b) = digits.split_at(point_pos as usize);
            out.push_str(a);
            out.push('.');
            out.push_str(b);
        }
    } else {
        let (d0, rest) = digits.split_at(1);
        out.push_str(d0);
        if !rest.is_empty() {
            out.push('.');
            out.push_str(rest);
        }
        out.push('e');
        if exp >= 0 {
            out.push('+');
        } else {
            out.push('-');
        }
        out.push_str(&format!("{:02}", exp.abs()));
    }
    Ok(out)
}

/// Python's `round(x)` -- half-to-EVEN, unlike `f64::round` (half-away).
/// `round(2.5) == 2`, `round(-0.5) == 0`, `round(-1.5) == -2`.
fn py_round(x: f64) -> f64 {
    let f = x.fract();
    if f.abs() == 0.5 {
        let t = x.trunc();
        let lower_even = (t as i64).rem_euclid(2) == 0;
        if lower_even {
            t
        } else {
            t + x.signum()
        }
    } else {
        x.round()
    }
}

// ===========================================================================
// 3. Raw board model (faithful kiutils projection)
// ===========================================================================

#[derive(Clone, Debug)]
pub(crate) struct RawPos {
    pub x: Num,
    pub y: Num,
    pub angle: Option<Num>,
    /// kiutils' `Position` carries an `unlocked` flag (any `unlocked` token
    /// anywhere in the list sets it; the angle is then None). Only the drill
    /// offset path surfaces it (a `Position` pyclass); the rest of the model
    /// reads x/y/angle only.
    pub unlocked: bool,
}

impl RawPos {
    /// The zero position (`(0, 0)`, no angle, not unlocked) -- the default
    /// every walker keeps when a position token is absent or unparseable.
    fn origin() -> RawPos {
        RawPos { x: Num::I(0), y: Num::I(0), angle: None, unlocked: false }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct RawDrill {
    pub oval: bool,
    /// The token at `exp[1]` (or `exp[2]` for oval) -- a number, or the raw
    /// offset list when a drill carries only `(offset ...)` (kiutils quirk).
    pub diameter: Option<KiAtom>,
    pub width: Option<KiAtom>,
    pub offset: Option<RawPos>,
}

#[derive(Clone, Debug)]
pub(crate) struct RawPad {
    pub number: String,
    pub shape: String,
    pub position: RawPos,
    pub size: RawPos,
    pub drill: Option<RawDrill>,
    pub layers: Vec<String>,
    pub roundrect_ratio: Option<Num>,
    pub net: Option<(Num, String)>,
}

#[derive(Clone, Debug)]
pub(crate) enum RawFpItem {
    Text { text: String, layer: String },
    Line { start: RawPos, end: RawPos, layer: String },
    Rect { start: RawPos, end: RawPos, layer: String },
    Circle { center: RawPos, end: RawPos, layer: String },
    Arc { start: RawPos, mid: RawPos, end: RawPos, layer: String },
    Poly { coords: Vec<RawPos>, layer: String },
    TextBox { start: RawPos, end: RawPos, layer: String },
    #[allow(dead_code)]
    Curve { coords: Vec<RawPos>, layer: String },
}

impl RawFpItem {
    fn layer(&self) -> &str {
        match self {
            RawFpItem::Text { layer, .. }
            | RawFpItem::Line { layer, .. }
            | RawFpItem::Rect { layer, .. }
            | RawFpItem::Circle { layer, .. }
            | RawFpItem::Arc { layer, .. }
            | RawFpItem::Poly { layer, .. }
            | RawFpItem::TextBox { layer, .. }
            | RawFpItem::Curve { layer, .. } => layer,
        }
    }
}

#[derive(Clone, Debug)]
pub(crate) struct RawFootprint {
    pub position: RawPos,
    pub layer: String,
    pub locked: bool,
    pub lib_id: String,
    pub entry_name: String,
    pub properties: Vec<(String, String)>,
    pub pads: Vec<RawPad>,
    pub graphic_items: Vec<RawFpItem>,
}

#[derive(Clone, Debug)]
pub(crate) enum RawGrItem {
    Line { start: RawPos, end: RawPos, layer: String },
    Rect { start: RawPos, end: RawPos, layer: String },
    Circle { center: RawPos, end: RawPos, layer: String },
    Arc { start: RawPos, mid: RawPos, end: RawPos, layer: String },
    Poly { coords: Vec<RawPos>, layer: String },
    Text {
        // `text` is part of the faithful kiutils model; the extraction only
        // reads it via hasattr(item, "text") on FOOTPRINT items, and board
        // gr_text contributes nothing to bounds/dimensions.
        #[allow(dead_code)]
        text: String,
        layer: String,
    },
    TextBox { start: RawPos, end: RawPos, layer: String },
    #[allow(dead_code)]
    Curve {
        // fp_curve coordinates are part of the faithful kiutils model; the
        // bounds extraction only reads start/end-bearing items (FpCurve has
        // no `start` attribute), so the coords are never consumed.
        coords: Vec<RawPos>,
        layer: String,
    },
}

#[derive(Clone, Debug)]
pub(crate) struct RawZone {
    pub name: Option<String>,
    pub net_name: Option<String>,
    pub layers: Vec<String>,
    pub polygons: Vec<Vec<RawPos>>,
}

#[derive(Clone, Debug)]
pub(crate) struct RawNet {
    pub number: Num,
    pub name: String,
}

#[derive(Clone, Debug)]
pub(crate) enum RawTraceItem {
    Segment { start: RawPos, end: RawPos, width: Num, layer: String, net: Num },
    Via { position: RawPos, size: Num, drill: Num, layers: Vec<String>, net: Num },
    // `mid` is faithful to kiutils' Arc; the trace extraction reads only
    // start/end (hasattr checks), so mid is never consumed here.
    #[allow(dead_code)]
    Arc { start: RawPos, mid: RawPos, end: RawPos, width: Num, layer: String, net: Num },
    // kiutils parses `(target ...)` into traceItems and the via extraction's
    // `hasattr(track, "position") and not hasattr(track, "start")` accepts it;
    // no corpus file contains targets, so this variant is never constructed.
    #[allow(dead_code)]
    Target { position: RawPos, size: Num, drill: Num, layers: Vec<String>, net: Num },
}

#[derive(Clone, Debug)]
pub(crate) struct RawStackupLayer {
    pub name: String,
    pub layer_type: String,
    pub thickness: Option<Num>,
    pub material: Option<String>,
    pub epsilon_r: Option<Num>,
    pub loss_tangent: Option<Num>,
}

#[derive(Clone, Debug)]
pub(crate) struct RawBoard {
    pub graphic_items: Vec<RawGrItem>,
    pub footprints: Vec<RawFootprint>,
    pub zones: Vec<RawZone>,
    pub nets: Vec<RawNet>,
    pub trace_items: Vec<RawTraceItem>,
    pub stackup_layers: Vec<RawStackupLayer>,
    pub layers: Vec<String>,
    // Parallel array to `layers` (same length, same order, index-aligned):
    // the role token (`(0 "F.Cu" signal)`'s `signal`) declared for that
    // layer in the board's own `(layers ...)` block, or `""` if the entry
    // has no third token. Added 2026-08-14 alongside
    // `temper-geometry/src/layer_identity.rs` -- ADDITIVE ONLY. Before this
    // field existed, `raw_board_from_tree` read a layer's NAME (index 1)
    // and silently discarded its ROLE token (index 2) entirely, which is
    // why every consumer downstream of this parser (`_extract_stackup`'s
    // positional/zone-content heuristic, `core/board.py`'s closed
    // `LayerIndex`/`STANDARD_LAYER_ORDER` enum) had no structural way to
    // read the board's own declared role and fell back to inference --
    // "coincidentally correct" only because the production board has
    // stayed 4-layer with plane zones on structurally first/last layers.
    // See `docs/evidence/2026-07-27-phantom-layer-stackup.md` for the
    // incident this already produced once, and
    // `temper-geometry/src/layer_identity.rs`'s module doc for the
    // parallel bug this parser gap was verified (2026-08-14 SSOT dataflow
    // audit) to be the root cause of. This field is additive and read by
    // nothing yet in this crate -- it exists so a consumer CAN start
    // reading the real declared role instead of inferring one; wiring
    // `_extract_stackup` (or any of its nine verified consumers) onto it
    // is deliberately NOT done here (`_extract_stackup`'s own
    // `use_declared_layer_roles` opt-in flag is documented as unsafe to
    // default on before pours become derived output -- see that
    // function's docstring) and is out of scope for this change.
    pub layer_roles: Vec<String>,
    pub general_thickness: Option<Num>,
}

/// Clone an owned handle to the same underlying Python object (NOT a copy).
fn same(py: Python<'_>, obj: &Py<PyAny>) -> Py<PyAny> {
    obj.clone_ref(py)
}

fn atom_to_string(atom: &KiAtom) -> String {
    match atom {
        KiAtom::Str(s) | KiAtom::Bare(s) => s.clone(),
        KiAtom::Int(v) => v.to_string(),
        KiAtom::Float(v) => py_repr_f64(*v).unwrap_or_else(|e| format!("<repr-error:{e}>")),
        KiAtom::List(_) => String::new(),
    }
}

/// The kiutils `Position` from `(at X Y [angle])` / `(size X Y)` /
/// `(offset ...)`: `exp[1]` and `exp[2]` verbatim (int or float), `exp[3]`
/// is the angle unless it is the `unlocked` marker. Mirrors kiutils'
/// `Position.from_sexpr`: a list shorter than 3 items raises there, so the
/// engine records a parse error and the document parse fails closed. A
/// non-numeric x/y keeps returning `None` without an error (kiutils stores
/// the raw token and only fails later in a float() conversion -- a
/// documented deviation, see VERIFICATION.md).
fn parse_pos(items: &[KiNode], errors: &mut Vec<String>) -> Option<RawPos> {
    let get = |idx: usize| -> Option<Num> {
        let atom = items.get(idx)?;
        match atom {
            KiNode::Atom(KiAtom::Int(v)) => Some(Num::I(*v)),
            KiNode::Atom(KiAtom::Float(v)) => Some(Num::F(*v)),
            _ => None,
        }
    };
    if items.len() < 3 {
        errors.push("Expression does not have the correct type".to_string());
        return None;
    }
    let x = get(1)?;
    let y = get(2)?;
    let mut angle = get(3);
    if let Some(KiNode::Atom(KiAtom::Bare(b))) = items.get(3)
        && b == "unlocked" {
            angle = None;
        }
    // kiutils scans the WHOLE list for the `unlocked` marker, not just
    // index 3 (`for item in exp: if item == 'unlocked'`).
    let mut unlocked = false;
    for item in items.iter().skip(1) {
        if let KiNode::Atom(KiAtom::Bare(b)) = item
            && b == "unlocked" {
                unlocked = true;
            }
    }
    Some(RawPos { x, y, angle, unlocked })
}

fn parse_drill(items: &[KiNode], errors: &mut Vec<String>) -> Option<RawDrill> {
    let get = |idx: usize| -> Option<KiAtom> {
        match items.get(idx)? {
            KiNode::Atom(a) => Some(a.clone()),
            KiNode::List(sub) => {
                // The offset-list quirk: kiutils stores the whole sub-list
                // verbatim into diameter/width. Reproduce the list as an
                // opaque "list" atom carrying the token values.
                Some(KiAtom::List(sub.clone()))
            }
        }
    };
    let mut oval = false;
    if let Some(KiNode::Atom(KiAtom::Bare(b))) = items.get(1)
        && b == "oval" {
            oval = true;
        }
    let (diameter, width) = if oval {
        // kiutils: `object.diameter = exp[2]; object.width = exp[3]` --
        // both are unconditional, so an oval drill missing its width
        // raises IndexError there; the engine fails closed the same way.
        if items.len() < 4 {
            errors.push("Expression does not have the correct type".to_string());
        }
        (get(2), get(3))
    } else {
        let d = get(1);
        let w = if items.len() > 2 { get(2) } else { None };
        (d, w)
    };
    let mut offset = None;
    for item in items {
        if let KiNode::List(sub) = item
            && let Some(KiNode::Atom(KiAtom::Bare(b))) = sub.first()
                && b == "offset" {
                    // kiutils: `Position().from_sexpr(item)` -- the angle
                    // and the unlocked marker are kept.
                    offset = parse_pos(sub, errors);
                }
    }
    Some(RawDrill { oval, diameter, width, offset })
}

fn parse_pad(items: &[KiNode], errors: &mut Vec<String>) -> Option<RawPad> {
    let num_str = match items.get(1)? {
        KiNode::Atom(a) => atom_to_string(a),
        _ => String::new(),
    };
    let shape = match items.get(3)? {
        KiNode::Atom(a) => atom_to_string(a),
        _ => String::new(),
    };
    let mut position = RawPos::origin();
    let mut size = RawPos::origin();
    let mut drill = None;
    let mut layers: Vec<String> = Vec::new();
    let mut roundrect_ratio = None;
    let mut net = None;
    for item in &items[3..] {
        let KiNode::List(sub) = item else { continue };
        let head = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
            Some(KiNode::Atom(KiAtom::Str(s))) => s.as_str(),
            _ => continue,
        };
        match head {
            "at" => position = parse_pos(sub, errors).unwrap_or(position),
            "size" => size = parse_pos(sub, errors).unwrap_or(size),
            "drill" => drill = parse_drill(sub, errors),
            "layers" => {
                for layer in sub.iter().skip(1) {
                    if let KiNode::Atom(a) = layer {
                        layers.push(atom_to_string(a));
                    }
                }
            }
            "roundrect_rratio" => {
                if let Some(KiNode::Atom(KiAtom::Int(v))) = sub.get(1) {
                    roundrect_ratio = Some(Num::I(*v));
                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = sub.get(1) {
                    roundrect_ratio = Some(Num::F(*v));
                }
            }
            "net" => {
                // kiutils: `Net().from_sexpr(item)` does `object.number =
                // exp[1]; object.name = exp[2]` -- both unconditional, so a
                // nameless `(net 1)` (or `(net)`) raises IndexError there.
                // The engine fails closed the same way (parity contract:
                // a nameless pad-net token must not silently become
                // pin.net="" and then get dropped as unconnected).
                if sub.len() < 3 {
                    errors.push("Expression does not have the correct type".to_string());
                    continue;
                }
                let number = match sub.get(1) {
                    Some(KiNode::Atom(KiAtom::Int(v))) => Some(Num::I(*v)),
                    Some(KiNode::Atom(KiAtom::Float(v))) => Some(Num::F(*v)),
                    _ => None,
                };
                let name = match sub.get(2) {
                    Some(KiNode::Atom(a)) => atom_to_string(a),
                    _ => String::new(),
                };
                if let Some(number) = number {
                    net = Some((number, name));
                }
            }
            _ => {}
        }
    }
    Some(RawPad { number: num_str, shape, position, size, drill, layers, roundrect_ratio, net })
}

fn parse_fp_item(items: &[KiNode], errors: &mut Vec<String>) -> Option<RawFpItem> {
    let head = match items.first() {
        Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
        _ => return None,
    };
    let mut layer = String::new();
    let mut start = RawPos::origin();
    let mut end = RawPos::origin();
    let mut mid = RawPos::origin();
    let mut center = RawPos::origin();
    let mut coords: Vec<RawPos> = Vec::new();
    let mut text = String::new();
    for item in &items[1..] {
        let KiNode::List(sub) = item else { continue };
        let subhead = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
            _ => continue,
        };
        match subhead {
            "layer" => {
                if let Some(KiNode::Atom(a)) = sub.get(1) {
                    layer = atom_to_string(a);
                }
            }
            "start" => start = parse_pos(sub, errors).unwrap_or(start),
            "end" => end = parse_pos(sub, errors).unwrap_or(end),
            "mid" => mid = parse_pos(sub, errors).unwrap_or(mid),
            "center" => center = parse_pos(sub, errors).unwrap_or(center),
            "pts" | "coordinates" => {
                // kiutils: every `(xy X Y)` child of the pts list becomes a
                // Position via Position().from_sexpr (X, Y at exp[1], exp[2]).
                for pt in sub.iter().skip(1) {
                    if let KiNode::List(ptsub) = pt
                        && let Some(p) = parse_pos(ptsub, errors) {
                            coords.push(p);
                        }
                }
            }
            _ => {}
        }
    }
    // FpText: `type = exp[1]`, `text = exp[2]` (the quoted string).
    if head == "fp_text"
        && let Some(KiNode::Atom(a)) = items.get(2) {
            text = atom_to_string(a);
        }
    match head {
        "fp_text" => Some(RawFpItem::Text { text, layer }),
        "fp_line" => Some(RawFpItem::Line { start, end, layer }),
        "fp_rect" => Some(RawFpItem::Rect { start, end, layer }),
        "fp_circle" => Some(RawFpItem::Circle { center, end, layer }),
        "fp_arc" => Some(RawFpItem::Arc { start, mid, end, layer }),
        "fp_poly" => Some(RawFpItem::Poly { coords, layer }),
        "fp_text_box" => Some(RawFpItem::TextBox { start, end, layer }),
        "fp_curve" => Some(RawFpItem::Curve { coords, layer }),
        _ => None,
    }
}

fn parse_footprint(items: &[KiNode], errors: &mut Vec<String>) -> Option<RawFootprint> {
    let lib_id = match items.get(1) {
        Some(KiNode::Atom(a)) => atom_to_string(a),
        // kiutils does `object.libId = exp[1]` unconditionally; for a
        // non-atom token (no libId, e.g. `(footprint (layer ...) ...)`) the
        // libId setter's else branch stores the RAW LIST as entryName, and
        // the oracle's `_get_footprint_reference` then raises AttributeError
        // on `ename.startswith`. Fail closed the same way (a footprint
        // without a string libId is not a parseable footprint).
        _ => {
            errors.push("Expression does not have the correct type".to_string());
            String::new()
        }
    };
    // kiutils' libId setter splits at the FIRST colon.
    let (entry_name, _nickname) = match lib_id.split_once(':') {
        Some((nick, entry)) => (entry.to_string(), Some(nick.to_string())),
        None => (lib_id.clone(), None),
    };
    let mut position = RawPos::origin();
    let mut layer = String::new();
    let mut locked = false;
    let mut properties: Vec<(String, String)> = Vec::new();
    let mut pads: Vec<RawPad> = Vec::new();
    let mut graphic_items: Vec<RawFpItem> = Vec::new();
    for item in &items[2..] {
        let KiNode::List(sub) = item else {
            if let KiNode::Atom(KiAtom::Bare(b)) = item
                && b == "locked" {
                    locked = true;
                }
            continue;
        };
        let head = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
            _ => continue,
        };
        match head {
            "layer" => {
                if let Some(KiNode::Atom(a)) = sub.get(1) {
                    layer = atom_to_string(a);
                }
            }
            "at" => position = parse_pos(sub, errors).unwrap_or(position),
            "property" => {
                let name = match sub.get(1) {
                    Some(KiNode::Atom(a)) => atom_to_string(a),
                    _ => String::new(),
                };
                let value = match sub.get(2) {
                    Some(KiNode::Atom(a)) => atom_to_string(a),
                    _ => String::new(),
                };
                // kiutils: object.properties.update({item[1]: item[2]}) --
                // later duplicates overwrite earlier ones, key order is first
                // insertion.
                properties.retain(|(k, _)| k != &name);
                properties.push((name, value));
            }
            "pad" => {
                if let Some(pad) = parse_pad(sub, errors) {
                    pads.push(pad);
                }
            }
            "fp_text" | "fp_line" | "fp_rect" | "fp_circle" | "fp_arc" | "fp_poly"
            | "fp_text_box" | "fp_curve" => {
                if let Some(item) = parse_fp_item(sub, errors) {
                    graphic_items.push(item);
                }
            }
            _ => {}
        }
    }
    Some(RawFootprint {
        position,
        layer,
        locked,
        lib_id,
        entry_name,
        properties,
        pads,
        graphic_items,
    })
}

fn parse_gr_item(items: &[KiNode], errors: &mut Vec<String>) -> Option<RawGrItem> {
    let head = match items.first() {
        Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
        _ => return None,
    };
    let mut layer = String::new();
    let mut start = RawPos::origin();
    let mut end = RawPos::origin();
    let mut mid = RawPos::origin();
    let mut center = RawPos::origin();
    let mut coords: Vec<RawPos> = Vec::new();
    let mut text = String::new();
    for item in &items[1..] {
        let KiNode::List(sub) = item else { continue };
        let subhead = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
            _ => continue,
        };
        match subhead {
            "layer" => {
                if let Some(KiNode::Atom(a)) = sub.get(1) {
                    layer = atom_to_string(a);
                }
            }
            "start" => start = parse_pos(sub, errors).unwrap_or(start),
            "end" => end = parse_pos(sub, errors).unwrap_or(end),
            "mid" => mid = parse_pos(sub, errors).unwrap_or(mid),
            "center" => center = parse_pos(sub, errors).unwrap_or(center),
            // gr_poly writes `(pts (xy x y) (xy x y) ...)`
            "pts" => {
                for pt in sub.iter().skip(1) {
                    let KiNode::List(xy) = pt else { continue };
                    if let Some(p) = parse_pos(xy, errors) {
                        coords.push(p);
                    }
                }
            }
            _ => {}
        }
    }
    // gr_text: text is the first atom after the head token.
    if head == "gr_text"
        && let KiNode::Atom(a) = items.get(1).cloned().unwrap_or(KiNode::Atom(KiAtom::Str(String::new())))
            && matches!(a, KiAtom::Str(_) | KiAtom::Bare(_)) {
                text = atom_to_string(&a);
            }
    match head {
        "gr_line" => Some(RawGrItem::Line { start, end, layer }),
        "gr_rect" => Some(RawGrItem::Rect { start, end, layer }),
        "gr_circle" => Some(RawGrItem::Circle { center, end, layer }),
        "gr_arc" => Some(RawGrItem::Arc { start, mid, end, layer }),
        "gr_poly" => Some(RawGrItem::Poly { coords, layer }),
        "gr_text" => Some(RawGrItem::Text { text, layer }),
        "gr_text_box" => Some(RawGrItem::TextBox { start, end, layer }),
        "gr_curve" => Some(RawGrItem::Curve { coords, layer }),
        _ => None,
    }
}

fn parse_zone(items: &[KiNode], errors: &mut Vec<String>) -> Option<RawZone> {
    let mut name = None;
    let mut net_name = None;
    let mut layers: Vec<String> = Vec::new();
    let mut polygons: Vec<Vec<RawPos>> = Vec::new();
    for item in &items[1..] {
        let KiNode::List(sub) = item else { continue };
        let head = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
            _ => continue,
        };
        match head {
            "name" => {
                if let Some(KiNode::Atom(a)) = sub.get(1) {
                    name = Some(atom_to_string(a));
                }
            }
            "net_name" => {
                if let Some(KiNode::Atom(a)) = sub.get(1) {
                    net_name = Some(atom_to_string(a));
                }
            }
            // kiutils accepts both `(layers ...)` (plural) and `(layer ...)`
            // (singular) zone tokens -- the rp2040 corpus uses both.
            "layers" | "layer" => {
                for layer in sub.iter().skip(1) {
                    if let KiNode::Atom(a) = layer {
                        layers.push(atom_to_string(a));
                    }
                }
            }
            "polygon" => {
                let mut coords: Vec<RawPos> = Vec::new();
                for child in sub.iter().skip(1) {
                    if let KiNode::List(ptsub) = child
                        && let Some(KiNode::Atom(KiAtom::Bare(b))) = ptsub.first()
                            && b == "pts" {
                                for pt in ptsub.iter().skip(1) {
                                    if let KiNode::List(xy) = pt
                                        && let Some(p) = parse_pos(xy, errors) {
                                            coords.push(p);
                                        }
                                }
                            }
                }
                polygons.push(coords);
            }
            _ => {}
        }
    }
    Some(RawZone { name, net_name, layers, polygons })
}

fn parse_stackup_layer(items: &[KiNode]) -> Option<RawStackupLayer> {
    let name = match items.get(1) {
        Some(KiNode::Atom(a)) => atom_to_string(a),
        _ => String::new(),
    };
    let mut layer_type = String::new();
    let mut thickness = None;
    let mut material = None;
    let mut epsilon_r = None;
    let mut loss_tangent = None;
    for item in &items[2..] {
        let KiNode::List(sub) = item else { continue };
        let head = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
            _ => continue,
        };
        let num = |idx: usize| -> Option<Num> {
            match sub.get(idx) {
                Some(KiNode::Atom(KiAtom::Int(v))) => Some(Num::I(*v)),
                Some(KiNode::Atom(KiAtom::Float(v))) => Some(Num::F(*v)),
                _ => None,
            }
        };
        match head {
            "type" => {
                if let Some(KiNode::Atom(a)) = sub.get(1) {
                    layer_type = atom_to_string(a);
                }
            }
            "thickness" => thickness = num(1),
            "material" => {
                if let Some(KiNode::Atom(a)) = sub.get(1) {
                    material = Some(atom_to_string(a));
                }
            }
            "epsilon_r" => epsilon_r = num(1),
            "loss_tangent" => loss_tangent = num(1),
            _ => {}
        }
    }
    Some(RawStackupLayer { name, layer_type, thickness, material, epsilon_r, loss_tangent })
}

/// Walk the top-level `.kicad_pcb` document into the raw model. Malformed
/// tokens that kiutils' `from_sexpr` raises on (nameless board-level nets,
/// truncated positions, oval drills missing their width, footprints without
/// a libId) are recorded into `errors`; `parse_kicad_document` fails closed
/// on any of them.
fn raw_board_from_tree(root: &[KiNode], errors: &mut Vec<String>) -> RawBoard {
    let mut board = RawBoard {
        graphic_items: Vec::new(),
        footprints: Vec::new(),
        zones: Vec::new(),
        nets: Vec::new(),
        trace_items: Vec::new(),
        stackup_layers: Vec::new(),
        layers: Vec::new(),
        layer_roles: Vec::new(),
        general_thickness: None,
    };
    // The document is a single top-level `(kicad_pcb ...)` list; walk its
    // children.
    let items: &[KiNode] = match root {
        [KiNode::List(inner)] => inner.as_slice(),
        other => other,
    };
    for node in items {
        let KiNode::List(items) = node else { continue };
        let head = match items.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
            _ => continue,
        };
        match head {
            "general" => {
                for sub in items.iter().skip(1) {
                    if let KiNode::List(s) = sub
                        && let Some(KiNode::Atom(KiAtom::Bare(b))) = s.first()
                            && b == "thickness" {
                                board.general_thickness = match s.get(1) {
                                    Some(KiNode::Atom(KiAtom::Int(v))) => Some(Num::I(*v)),
                                    Some(KiNode::Atom(KiAtom::Float(v))) => Some(Num::F(*v)),
                                    _ => None,
                                };
                            }
                }
            }
            "layers" => {
                // `(0 "F.Cu" signal)` -- the NAME is the quoted token at
                // index 1; index 2 is the declared ROLE token (`signal` /
                // `power` / `mixed` / `jumper` / `user`). Both are captured
                // now, index-aligned across `board.layers` /
                // `board.layer_roles` -- see `RawBoard::layer_roles`'s doc
                // comment for why the role token was previously discarded
                // and what reads it.
                for sub in items.iter().skip(1) {
                    if let KiNode::List(s) = sub
                        && let Some(KiNode::Atom(a)) = s.get(1) {
                            board.layers.push(atom_to_string(a));
                            let role = match s.get(2) {
                                Some(KiNode::Atom(role_atom)) => atom_to_string(role_atom),
                                _ => String::new(),
                            };
                            board.layer_roles.push(role);
                        }
                }
            }
            "setup" => {
                for sub in items.iter().skip(1) {
                    let KiNode::List(s) = sub else { continue };
                    let is_stackup = matches!(
                        s.first(),
                        Some(KiNode::Atom(KiAtom::Bare(b))) if b == "stackup"
                    );
                    if is_stackup {
                        // The `(layer ...)` entries are direct children of
                        // the `(stackup ...)` list.
                        for inner in s.iter().skip(1) {
                            let KiNode::List(l) = inner else { continue };
                            if matches!(
                                l.first(),
                                Some(KiNode::Atom(KiAtom::Bare(b))) if b == "layer"
                            ) && let Some(layer) = parse_stackup_layer(l)
                            {
                                board.stackup_layers.push(layer);
                            }
                        }
                    }
                }
            }
            "net" => {
                // kiutils: `Net().from_sexpr(item)` does `object.name =
                // exp[2]` unconditionally -- a nameless board-level
                // `(net 1)` raises IndexError there; fail closed the same
                // way (R1 parity contract).
                if items.len() < 3 {
                    errors.push("Expression does not have the correct type".to_string());
                    continue;
                }
                let number = match items.get(1) {
                    Some(KiNode::Atom(KiAtom::Int(v))) => Some(Num::I(*v)),
                    Some(KiNode::Atom(KiAtom::Float(v))) => Some(Num::F(*v)),
                    _ => None,
                };
                let name = match items.get(2) {
                    Some(KiNode::Atom(a)) => atom_to_string(a),
                    _ => String::new(),
                };
                if let Some(number) = number {
                    board.nets.push(RawNet { number, name });
                }
            }
            "footprint" => {
                if let Some(fp) = parse_footprint(items, errors) {
                    board.footprints.push(fp);
                }
            }
            "gr_line" | "gr_rect" | "gr_circle" | "gr_arc" | "gr_poly" | "gr_text"
            | "gr_text_box" | "gr_curve" => {
                if let Some(item) = parse_gr_item(items, errors) {
                    board.graphic_items.push(item);
                }
            }
            "segment" => {
                let mut start = RawPos::origin();
                let mut end = RawPos::origin();
                let mut width = Num::I(0);
                let mut layer = String::new();
                let mut net = Num::I(0);
                for sub in items.iter().skip(1) {
                    if let KiNode::List(s) = sub {
                        let h = match s.first() {
                            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
                            _ => continue,
                        };
                        match h {
                            "start" => start = parse_pos(s, errors).unwrap_or(start),
                            "end" => end = parse_pos(s, errors).unwrap_or(end),
                            "width" => {
                                if let Some(KiNode::Atom(KiAtom::Int(v))) = s.get(1) {
                                    width = Num::I(*v);
                                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = s.get(1) {
                                    width = Num::F(*v);
                                }
                            }
                            "layer" => {
                                if let Some(KiNode::Atom(a)) = s.get(1) {
                                    layer = atom_to_string(a);
                                }
                            }
                            "net" => {
                                if let Some(KiNode::Atom(KiAtom::Int(v))) = s.get(1) {
                                    net = Num::I(*v);
                                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = s.get(1) {
                                    net = Num::F(*v);
                                }
                            }
                            _ => {}
                        }
                    }
                }
                board.trace_items.push(RawTraceItem::Segment { start, end, width, layer, net });
            }
            "arc" => {
                let mut start = RawPos::origin();
                let mut end = RawPos::origin();
                let mut mid = RawPos::origin();
                let mut width = Num::I(0);
                let mut layer = String::new();
                let mut net = Num::I(0);
                for sub in items.iter().skip(1) {
                    if let KiNode::List(s) = sub {
                        let h = match s.first() {
                            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
                            _ => continue,
                        };
                        match h {
                            "start" => start = parse_pos(s, errors).unwrap_or(start),
                            "end" => end = parse_pos(s, errors).unwrap_or(end),
                            "mid" => mid = parse_pos(s, errors).unwrap_or(mid),
                            "width" => {
                                if let Some(KiNode::Atom(KiAtom::Int(v))) = s.get(1) {
                                    width = Num::I(*v);
                                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = s.get(1) {
                                    width = Num::F(*v);
                                }
                            }
                            "layer" => {
                                if let Some(KiNode::Atom(a)) = s.get(1) {
                                    layer = atom_to_string(a);
                                }
                            }
                            "net" => {
                                if let Some(KiNode::Atom(KiAtom::Int(v))) = s.get(1) {
                                    net = Num::I(*v);
                                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = s.get(1) {
                                    net = Num::F(*v);
                                }
                            }
                            _ => {}
                        }
                    }
                }
                board.trace_items.push(RawTraceItem::Arc { start, mid, end, width, layer, net });
            }
            "via" => {
                let mut position = RawPos::origin();
                let mut size = Num::I(0);
                let mut drill = Num::I(0);
                let mut layers: Vec<String> = Vec::new();
                let mut net = Num::I(0);
                for sub in items.iter().skip(1) {
                    if let KiNode::List(s) = sub {
                        let h = match s.first() {
                            Some(KiNode::Atom(KiAtom::Bare(b))) => b.as_str(),
                            _ => continue,
                        };
                        match h {
                            "at" => position = parse_pos(s, errors).unwrap_or(position),
                            "size" => {
                                if let Some(KiNode::Atom(KiAtom::Int(v))) = s.get(1) {
                                    size = Num::I(*v);
                                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = s.get(1) {
                                    size = Num::F(*v);
                                }
                            }
                            "drill" => {
                                if let Some(KiNode::Atom(KiAtom::Int(v))) = s.get(1) {
                                    drill = Num::I(*v);
                                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = s.get(1) {
                                    drill = Num::F(*v);
                                }
                            }
                            "layers" => {
                                for layer in s.iter().skip(1) {
                                    if let KiNode::Atom(a) = layer {
                                        layers.push(atom_to_string(a));
                                    }
                                }
                            }
                            "net" => {
                                if let Some(KiNode::Atom(KiAtom::Int(v))) = s.get(1) {
                                    net = Num::I(*v);
                                } else if let Some(KiNode::Atom(KiAtom::Float(v))) = s.get(1) {
                                    net = Num::F(*v);
                                }
                            }
                            _ => {}
                        }
                    }
                }
                board.trace_items.push(RawTraceItem::Via { position, size, drill, layers, net });
            }
            "zone" => {
                if let Some(zone) = parse_zone(items, errors) {
                    board.zones.push(zone);
                }
            }
            _ => {}
        }
    }
    board
}


/// Parse `content` and validate that it is a single `(kicad_pcb ...)` document
/// (mirrors kiutils' `from_sexpr` rejecting any other root: empty input,
/// bare atoms, or a different top-level keyword all raise).
fn parse_kicad_document(content: &str) -> Result<RawBoard, String> {
    let tree = parse_ki_document(content)?;
    let items: &[KiNode] = match tree.as_slice() {
        [KiNode::List(inner)] => inner.as_slice(),
        _ => return Err("Expression does not have the correct type".to_string()),
    };
    let is_kicad_pcb = matches!(
        items.first(),
        Some(KiNode::Atom(KiAtom::Bare(b))) if b == "kicad_pcb"
    );
    if !is_kicad_pcb {
        return Err("Expression does not have the correct type".to_string());
    }
    let mut errors: Vec<String> = Vec::new();
    let raw = raw_board_from_tree(&tree, &mut errors);
    if let Some(err) = errors.first() {
        // kiutils' `from_sexpr` raises on the malformed token (nameless net,
        // truncated position, oval drill without width, footprint without a
        // libId); the engine fails closed the same way so a broken token can
        // never silently degrade to a default value.
        return Err(err.clone());
    }
    Ok(raw)
}

// ===========================================================================
// 4. Extraction (ports of the _parse_* logic)
// ===========================================================================

fn extract_board_geometry_pure(raw: &RawBoard) -> (Option<Num>, Option<Num>, Option<(Num, Num)>) {
    // returns (width, height, origin) as Option -- None when falling back to
    // Board.temper_default()
    let mut edge_cuts: Vec<&RawGrItem> = Vec::new();
    for g in &raw.graphic_items {
        if g_layer(g) == "Edge.Cuts" {
            edge_cuts.push(g);
        }
    }
    if edge_cuts.is_empty() {
        return (None, None, None);
    }
    let inf = Num::F(f64::INFINITY);
    let neg_inf = Num::F(f64::NEG_INFINITY);
    let mut x_min = inf;
    let mut y_min = inf;
    let mut x_max = neg_inf;
    let mut y_max = neg_inf;
    for item in &edge_cuts {
        match item {
            RawGrItem::Line { start, end, .. }
            | RawGrItem::Rect { start, end, .. }
            | RawGrItem::TextBox { start, end, .. } => {
                for pt in [start, end] {
                    x_min = Num::py_min(x_min, pt.x);
                    y_min = Num::py_min(y_min, pt.y);
                    x_max = Num::py_max(x_max, pt.x);
                    y_max = Num::py_max(y_max, pt.y);
                }
            }
            RawGrItem::Arc { start, mid, end, .. } => {
                for pt in [start, end] {
                    x_min = Num::py_min(x_min, pt.x);
                    y_min = Num::py_min(y_min, pt.y);
                    x_max = Num::py_max(x_max, pt.x);
                    y_max = Num::py_max(y_max, pt.y);
                }
                if mid.x.is_finite() || mid.y.is_finite() {
                    x_min = Num::py_min(x_min, mid.x);
                    y_min = Num::py_min(y_min, mid.y);
                    x_max = Num::py_max(x_max, mid.x);
                    y_max = Num::py_max(y_max, mid.y);
                }
            }
            RawGrItem::Poly { coords, .. } | RawGrItem::Curve { coords, .. } => {
                for pt in coords {
                    x_min = Num::py_min(x_min, pt.x);
                    y_min = Num::py_min(y_min, pt.y);
                    x_max = Num::py_max(x_max, pt.x);
                    y_max = Num::py_max(y_max, pt.y);
                }
            }
            RawGrItem::Circle { .. } | RawGrItem::Text { .. } => {}
        }
    }
    if !(x_min.is_finite() && x_max.is_finite() && y_min.is_finite() && y_max.is_finite()) {
        return (None, None, None);
    }
    let width = x_max.sub(&x_min);
    let height = y_max.sub(&y_min);
    (Some(width), Some(height), Some((x_min, y_min)))
}

fn g_layer(item: &RawGrItem) -> &str {
    match item {
        RawGrItem::Line { layer, .. }
        | RawGrItem::Rect { layer, .. }
        | RawGrItem::Circle { layer, .. }
        | RawGrItem::Arc { layer, .. }
        | RawGrItem::Poly { layer, .. }
        | RawGrItem::Text { layer, .. }
        | RawGrItem::TextBox { layer, .. }
        | RawGrItem::Curve { layer, .. } => layer,
    }
}

/// Port of `_calculate_footprint_bounds` from `_parse_modules.py`.
fn calculate_footprint_bounds(fp: &RawFootprint, center_offset_x: f64, center_offset_y: f64) -> (f64, f64) {
    let layers_priority = ["F.CrtYd", "B.CrtYd", "F.Fab", "B.Fab"];
    let mut items_to_use: Vec<&RawFpItem> = Vec::new();
    for g in &fp.graphic_items {
        if layers_priority.contains(&g.layer()) {
            items_to_use.push(g);
        }
    }
    if items_to_use.is_empty() {
        for g in &fp.graphic_items {
            if !g.layer().contains("Silk") {
                items_to_use.push(g);
            }
        }
    }
    let gfx_bounds: Option<(Num, Num, Num, Num)> = if !items_to_use.is_empty() {
        let inf = Num::F(f64::INFINITY);
        let neg_inf = Num::F(f64::NEG_INFINITY);
        let mut x_min = inf;
        let mut y_min = inf;
        let mut x_max = neg_inf;
        let mut y_max = neg_inf;
        let mut has_valid = false;
        for item in &items_to_use {
            match item {
                RawFpItem::Line { start, end, .. }
                | RawFpItem::Rect { start, end, .. }
                | RawFpItem::Arc { start, end, .. }
                | RawFpItem::TextBox { start, end, .. } => {
                    for pt in [start, end] {
                        x_min = Num::py_min(x_min, pt.x);
                        y_min = Num::py_min(y_min, pt.y);
                        x_max = Num::py_max(x_max, pt.x);
                        y_max = Num::py_max(y_max, pt.y);
                    }
                    has_valid = true;
                }
                // Oracle: `if hasattr(item, "center") and hasattr(item,
                // "radius")` -- a circle contributes a square bounding box
                // of side `2*radius` centred on `center`. kiutils' `FpCircle`
                // stores `center`+`end` (a point on the circumference), not
                // a precomputed `radius`, so the radius is the centre-to-end
                // Euclidean distance.
                RawFpItem::Circle { center, end, .. } => {
                    let dx = end.x.to_f64() - center.x.to_f64();
                    let dy = end.y.to_f64() - center.y.to_f64();
                    let r = (dx * dx + dy * dy).sqrt();
                    let cx = center.x.to_f64();
                    let cy = center.y.to_f64();
                    x_min = Num::py_min(x_min, Num::F(cx - r));
                    y_min = Num::py_min(y_min, Num::F(cy - r));
                    x_max = Num::py_max(x_max, Num::F(cx + r));
                    y_max = Num::py_max(y_max, Num::F(cy + r));
                    has_valid = true;
                }
                // Not in the pre-migration oracle (kiutils' `FpPoly` was
                // never matched by its `start`/`end` or `center`/`radius`
                // checks either), but a polygon's vertices are exactly as
                // real a courtyard/fab extent as a line's endpoints -- drop
                // it here and a polygonal courtyard silently vanishes from
                // every downstream spacing/keepout/congestion consumer the
                // same way the circle did.
                RawFpItem::Poly { coords, .. } if !coords.is_empty() => {
                    for pt in coords {
                        x_min = Num::py_min(x_min, pt.x);
                        y_min = Num::py_min(y_min, pt.y);
                        x_max = Num::py_max(x_max, pt.x);
                        y_max = Num::py_max(y_max, pt.y);
                    }
                    has_valid = true;
                }
                _ => {}
            }
        }
        if has_valid {
            Some((x_min, y_min, x_max, y_max))
        } else {
            None
        }
    } else {
        None
    };

    let inf = Num::F(f64::INFINITY);
    let neg_inf = Num::F(f64::NEG_INFINITY);
    let mut pad_x_min = inf;
    let mut pad_y_min = inf;
    let mut pad_x_max = neg_inf;
    let mut pad_y_max = neg_inf;
    for pad in &fp.pads {
        let px = pad.position.x;
        let py = pad.position.y;
        let pw = pad.size.x.to_f64();
        let ph = pad.size.y.to_f64();
        let half_w = Num::F(pw / 2.0);
        let half_h = Num::F(ph / 2.0);
        pad_x_min = Num::py_min(pad_x_min, px.sub(&half_w));
        pad_y_min = Num::py_min(pad_y_min, py.sub(&half_h));
        pad_x_max = Num::py_max(pad_x_max, px.add(&half_w));
        pad_y_max = Num::py_max(pad_y_max, py.add(&half_h));
    }

    let has_pads = pad_x_min.as_f64() != f64::INFINITY;
    if let Some((bx0, by0, bx1, by1)) = gfx_bounds {
        if has_pads {
            let x_min = Num::py_min(bx0, pad_x_min);
            let y_min = Num::py_min(by0, pad_y_min);
            let x_max = Num::py_max(bx1, pad_x_max);
            let y_max = Num::py_max(by1, pad_y_max);
            let hw = (x_min.to_f64() - center_offset_x).abs().max((x_max.to_f64() - center_offset_x).abs());
            let hh = (y_min.to_f64() - center_offset_y).abs().max((y_max.to_f64() - center_offset_y).abs());
            return (0.5_f64.max(2.0 * hw), 0.5_f64.max(2.0 * hh));
        }
        let hw = (bx0.to_f64() - center_offset_x).abs().max((bx1.to_f64() - center_offset_x).abs());
        let hh = (by0.to_f64() - center_offset_y).abs().max((by1.to_f64() - center_offset_y).abs());
        return (0.5_f64.max(2.0 * hw), 0.5_f64.max(2.0 * hh));
    }
    if has_pads {
        let hw = (pad_x_min.to_f64() - center_offset_x).abs().max((pad_x_max.to_f64() - center_offset_x).abs());
        let hh = (pad_y_min.to_f64() - center_offset_y).abs().max((pad_y_max.to_f64() - center_offset_y).abs());
        return (0.5_f64.max(2.0 * hw), 0.5_f64.max(2.0 * hh));
    }
    (2.0, 2.0)
}

/// Port of `_get_footprint_reference` from `_parse_modules.py`.
fn get_footprint_reference(fp: &RawFootprint) -> Option<String> {
    let props = &fp.properties;
    let mut ref_from_props: Option<String> = None;
    let mut is_dict = false;
    // kiutils always produces a dict keyed by property name.
    for (k, v) in props {
        if k == "Reference" {
            ref_from_props = Some(v.clone());
        }
        is_dict = true;
    }
    if is_dict
        && let Some(r) = ref_from_props {
            return Some(r);
        }
    let silk_layers = ["F.SilkS", "B.SilkS", "F.Fab", "B.Fab"];
    for item in &fp.graphic_items {
        if let RawFpItem::Text { text, layer } = item
            && silk_layers.contains(&layer.as_str()) {
                let candidate = text.trim();
                if !candidate.is_empty() && !candidate.starts_with("REF**") {
                    return Some(candidate.to_string());
                }
            }
    }
    let ename = &fp.entry_name;
    // kiutils: `if ename and not ename.startswith("REF**") and ":" not in
    // ename and len(ename) < 10` -- the leading truthiness guard means an
    // empty entryName falls through to None (the footprint is dropped).
    if !ename.is_empty() && !ename.starts_with("REF**") && !ename.contains(':') && ename.len() < 10 {
        return Some(ename.clone());
    }
    None
}

/// Port of `_extract_components_from_pcb` from `_parse_modules.py`.
fn extract_components_pure(raw: &RawBoard, board_origin: (f64, f64)) -> Vec<CompOut> {
    let (ox, oy) = board_origin;
    let mut components: Vec<CompOut> = Vec::new();
    for fp in &raw.footprints {
        let Some(ref_str) = get_footprint_reference(fp) else { continue };
        // Oracle: `if not ref or ref.startswith("REF**"): continue` -- the
        // falsy check drops an empty-string Reference property (e.g.
        // `(property "Reference" "")`), exactly like the REF** placeholder.
        if ref_str.is_empty() || ref_str.starts_with("REF**") {
            continue;
        }
        let rot_deg: Num = match fp.position.angle {
            Some(a) if a.is_truthy() => a,
            _ => Num::F(0.0),
        };
        let rot_idx = (py_round(rot_deg.to_f64() / 90.0) as i64).rem_euclid(4);
        let (center_offset_x, center_offset_y) = if !fp.pads.is_empty() {
            let xs: Vec<Num> = fp.pads.iter().map(|p| p.position.x).collect();
            let ys: Vec<Num> = fp.pads.iter().map(|p| p.position.y).collect();
            let mut x_min = xs[0];
            let mut x_max = xs[0];
            for &v in &xs[1..] {
                x_min = Num::py_min(x_min, v);
                x_max = Num::py_max(x_max, v);
            }
            let mut y_min = ys[0];
            let mut y_max = ys[0];
            for &v in &ys[1..] {
                y_min = Num::py_min(y_min, v);
                y_max = Num::py_max(y_max, v);
            }
            ((x_min.add(&x_max)).to_f64() / 2.0, (y_min.add(&y_max)).to_f64() / 2.0)
        } else {
            (0.0, 0.0)
        };
        let (width, height) = calculate_footprint_bounds(fp, center_offset_x, center_offset_y);
        let side: i64 = if fp.layer == "B.Cu" || fp.layer == "Back" || fp.layer == "Bottom" { 1 } else { 0 };
        let mut raw_pins: Vec<RawPinOut> = Vec::new();
        for pad in &fp.pads {
            let local_x = pad.position.x;
            let local_y = pad.position.y;
            let pad_layers = if pad.layers.is_empty() { vec!["F.Cu".to_string()] } else { pad.layers.clone() };
            let is_through_hole = pad_layers.iter().any(|l| l.contains("*.Cu") || l == "*.Cu");
            let layer = if is_through_hole {
                "all".to_string()
            } else {
                let copper: Vec<&String> = pad_layers.iter().filter(|l| l.contains(".Cu") && !l.contains('*')).collect();
                copper.first().map(|s| (*s).clone()).unwrap_or_else(|| "F.Cu".to_string())
            };
            let pad_width = pad.size.x;
            let pad_height = pad.size.y;
            let pad_drill: NumOrDrill = match &pad.drill {
                Some(drill) => NumOrDrill::Drill(drill.clone()),
                None => NumOrDrill::Num(Num::F(0.0)),
            };
            let pad_shape = if pad.shape.is_empty() {
                "rect".to_string()
            } else if is_through_hole && pad.shape == "circle" {
                "thru_hole".to_string()
            } else {
                pad.shape.clone()
            };
            let pad_roundrect_ratio = pad.roundrect_ratio.unwrap_or(Num::F(0.25));
            let pad_abs_rotation_deg: Num = match pad.position.angle {
                Some(a) if a.is_truthy() => a,
                _ => Num::F(0.0),
            };
            let pad_rotation_deg = (pad_abs_rotation_deg.sub(&rot_deg)).to_f64().rem_euclid(360.0);
            let net_name = pad.net.as_ref().map(|(_n, name)| name.clone());
            raw_pins.push(RawPinOut {
                name: pad.number.clone(),
                number: pad.number.clone(),
                // `p["position"][0] - center_offset_x` -- the oracle subtracts
                // the (float) pad-centroid offset, so the result is always a
                // float even when the pad coordinate was an int token.
                position: (
                    Num::F(local_x.to_f64() - center_offset_x),
                    Num::F(local_y.to_f64() - center_offset_y),
                ),
                net: net_name,
                width: pad_width,
                height: pad_height,
                shape: pad_shape,
                layer,
                drill: pad_drill,
                is_pth: is_through_hole,
                roundrect_ratio: pad_roundrect_ratio,
                pad_rotation_deg,
            });
        }
        let cx_to_rotate = if side == 1 { -center_offset_x } else { center_offset_x };
        let rot_rad = rot_deg.to_f64().to_radians();
        // rotate_local_to_world: R(-theta) -- (x*c + y*s, -x*s + y*c)
        let c = rot_rad.cos();
        let s = rot_rad.sin();
        let rotated_cx = cx_to_rotate * c + center_offset_y * s;
        let rotated_cy = -cx_to_rotate * s + center_offset_y * c;
        let initial_position = (
            fp.position.x.to_f64() - ox + rotated_cx,
            fp.position.y.to_f64() - oy + rotated_cy,
        );
        let attributes: Vec<(String, String)> = vec![
            ("_center_offset_x".to_string(), num_to_string(Num::F(center_offset_x))),
            ("_center_offset_y".to_string(), num_to_string(Num::F(center_offset_y))),
            ("_rotation_deg".to_string(), num_to_string(rot_deg)),
        ];
        let sheetpath: Option<String> = fp.properties.iter().find(|(k, _)| k == "Sheetpath").map(|(_, v)| v.clone());
        components.push(CompOut {
            r#ref: ref_str,
            footprint: fp.lib_id.clone(),
            bounds: (width, height),
            pins: raw_pins,
            initial_position,
            fixed: fp.locked,
            initial_rotation_quadrant: rot_idx,
            initial_side: side,
            attributes,
            sheetpath,
        });
    }
    components
}

#[derive(Clone, Debug)]
enum NumOrDrill {
    Num(Num),
    Drill(RawDrill),
}

#[derive(Clone, Debug)]
struct RawPinOut {
    name: String,
    number: String,
    position: (Num, Num),
    net: Option<String>,
    width: Num,
    height: Num,
    shape: String,
    layer: String,
    drill: NumOrDrill,
    is_pth: bool,
    roundrect_ratio: Num,
    pad_rotation_deg: f64,
}

#[derive(Clone, Debug)]
struct CompOut {
    r#ref: String,
    footprint: String,
    bounds: (f64, f64),
    pins: Vec<RawPinOut>,
    initial_position: (f64, f64),
    fixed: bool,
    initial_rotation_quadrant: i64,
    initial_side: i64,
    attributes: Vec<(String, String)>,
    sheetpath: Option<String>,
}

/// Port of `_extract_pads_from_pcb` from `_parse_modules.py`.
fn extract_pads_pure(raw: &RawBoard) -> Vec<PadOut> {
    let mut pads: Vec<PadOut> = Vec::new();
    for fp in &raw.footprints {
        let ref_str = get_footprint_reference(fp);
        let fp_x = fp.position.x.to_f64();
        let fp_y = fp.position.y.to_f64();
        for pad in &fp.pads {
            let abs_x = fp_x + pad.position.x.to_f64();
            let abs_y = fp_y + pad.position.y.to_f64();
            let drill: NumOrDrill = match &pad.drill {
                Some(d) => NumOrDrill::Drill(d.clone()),
                None => NumOrDrill::Num(Num::F(0.0)),
            };
            let rotation: Num = match pad.position.angle {
                Some(a) if a.is_truthy() => a,
                _ => Num::F(0.0),
            };
            let layer = pad.layers.first().cloned().unwrap_or_else(|| "F.Cu".to_string());
            let net_name = pad.net.as_ref().map(|(_n, name)| name.clone());
            pads.push(PadOut {
                position: (abs_x, abs_y),
                size: (pad.size.x, pad.size.y),
                shape: if pad.shape.is_empty() { "rect".to_string() } else { pad.shape.clone() },
                drill,
                rotation,
                layer,
                number: pad.number.clone(),
                net: net_name,
                component_ref: ref_str.clone(),
            });
        }
    }
    pads
}

#[derive(Clone, Debug)]
struct PadOut {
    position: (f64, f64),
    size: (Num, Num),
    shape: String,
    drill: NumOrDrill,
    rotation: Num,
    layer: String,
    number: String,
    net: Option<String>,
    // The oracle's `_extract_pads_from_pcb` passes `_get_footprint_reference`
    // through unchanged: None for a ref-less footprint, "" for an empty
    // Reference property -- both must survive into PadData.component_ref.
    component_ref: Option<String>,
}

/// Port of `_extract_nets_from_pcb` from `_parse_nets.py`.
///
/// DIVERGENCE (2026-08-15, deliberate, in lockstep with the pinned oracle
/// `tests/io/_parse_engine_py_oracle/_parse_nets.py`): the pre-migration
/// Python dropped nets with fewer than 2 pins (`if len(n.pins) >= 2`).
/// Single-pad nets are real electrical entities -- they still carry a net
/// class assignment (DRC, DRU emission, safety classification) and must
/// stay in the netlist registry so `Netlist.apply_net_class_mapping_strict`
/// can resolve every key of `temper_constraints.yaml`'s `net_classes:`
/// (the ZCD orphan-footprint removal leaves `ac_l` as a single-pad net --
/// PR #1178 lineage; without this, the strict net-class mapping raises
/// `ValueError` naming `ac_l` as an unresolved key). Routing already
/// excludes them (`router_v6.routing_space._routable_net_names` requires
/// at least 2 pins); the registry just no longer forgets they exist. Kept in
/// lockstep with the oracle so the R1a differential stays a parity check
/// rather than asserting the pre-migration drop.
fn extract_nets_pure(components: &[CompOut]) -> Vec<(String, Vec<(String, String)>)> {
    // (net_name, [(comp_ref, pin_name)]) in first-encounter order.
    let mut order: Vec<String> = Vec::new();
    let mut nets: HashMap<String, Vec<(String, String)>> = HashMap::new();
    for comp in components {
        for pin in &comp.pins {
            let Some(net) = &pin.net else { continue };
            // Python `if not pin.net: continue` -- empty-string nets are
            // falsy and skipped, exactly like None.
            if net.is_empty() {
                continue;
            }
            if !nets.contains_key(net) {
                order.push(net.clone());
                nets.insert(net.clone(), Vec::new());
            }
            let entry = nets.entry(net.clone()).or_default();
            entry.push((comp.r#ref.clone(), pin.name.clone()));
        }
    }
    // Every name in `order` was inserted with at least one pin, so no
    // filtering is needed -- single-pad nets are retained (see the function
    // docstring for why).
    order
        .into_iter()
        .map(|name| {
            let pins = nets.get(&name).cloned().unwrap_or_default();
            (name, pins)
        })
        .collect()
}

/// Port of `_extract_traces_from_pcb` / `_extract_vias_from_pcb`.
fn extract_traces_pure(raw: &RawBoard, net_map: &HashMap<String, String>) -> (Vec<TraceOut>, Vec<ViaOut>) {
    let mut traces: Vec<TraceOut> = Vec::new();
    let mut vias: Vec<ViaOut> = Vec::new();
    for track in &raw.trace_items {
        match track {
            RawTraceItem::Segment { start, end, width, layer, net } | RawTraceItem::Arc { start, end, width, layer, net, .. } => {
                let net_name = if net.is_truthy() {
                    let net_id = num_to_string(*net);
                    Some(net_map.get(&net_id).cloned().unwrap_or(net_id))
                } else {
                    None
                };
                traces.push(TraceOut {
                    start: (start.x, start.y),
                    end: (end.x, end.y),
                    width: *width,
                    layer: layer.clone(),
                    net: net_name,
                });
            }
            RawTraceItem::Via { position, size, drill, layers, net } | RawTraceItem::Target { position, size, drill, layers, net } => {
                let net_name = if net.is_truthy() {
                    let net_id = num_to_string(*net);
                    Some(net_map.get(&net_id).cloned().unwrap_or(net_id))
                } else {
                    None
                };
                let drill_val = if drill.is_truthy() { *drill } else { Num::F(0.4) };
                // kiutils' Via ALWAYS has a `layers` list (defaults to []),
                // so the oracle's `tuple(track.layers) if hasattr(...)` live
                // branch yields `()` for a layers-less via; the
                // `("F.Cu", "B.Cu")` else-branch is dead code there. Empty
                // stays empty.
                let layers_vec = layers.clone();
                vias.push(ViaOut {
                    position: (position.x, position.y),
                    diameter: *size,
                    drill: drill_val,
                    net: net_name,
                    layers: layers_vec,
                });
            }
        }
    }
    (traces, vias)
}

#[derive(Clone, Debug)]
struct TraceOut {
    start: (Num, Num),
    end: (Num, Num),
    width: Num,
    layer: String,
    net: Option<String>,
}

#[derive(Clone, Debug)]
struct ViaOut {
    position: (Num, Num),
    diameter: Num,
    drill: Num,
    net: Option<String>,
    layers: Vec<String>,
}

/// Port of `_extract_zones_from_pcb` from `_parse_zones.py`. Returns the
/// zones and appends any non-rectangular warnings (in encounter order).
fn extract_zones_pure(raw: &RawBoard, x_min: Num, y_min: Num) -> (Vec<ZoneOut>, Vec<String>) {
    let mut zones: Vec<ZoneOut> = Vec::new();
    let mut warnings: Vec<String> = Vec::new();
    for ki_zone in &raw.zones {
        if let Some(poly) = ki_zone.polygons.first() {
            // Python: `p.X - x_min` with x_min the board origin (int-typed on
            // integer boards) -- int - int stays int.
            let x_pts: Vec<Num> = poly.iter().map(|p| p.x.sub(&x_min)).collect();
            let y_pts: Vec<Num> = poly.iter().map(|p| p.y.sub(&y_min)).collect();
            if !x_pts.is_empty() && !y_pts.is_empty() {
                let mut b0 = x_pts[0];
                let mut b1 = x_pts[0];
                for &v in &x_pts[1..] {
                    b0 = Num::py_min(b0, v);
                    b1 = Num::py_max(b1, v);
                }
                let mut b2 = y_pts[0];
                let mut b3 = y_pts[0];
                for &v in &y_pts[1..] {
                    b2 = Num::py_min(b2, v);
                    b3 = Num::py_max(b3, v);
                }
                let bounds = (b0, b2, b1, b3);
                let polygon: Vec<(Num, Num)> = x_pts.iter().cloned().zip(y_pts.iter().cloned()).collect();
                let bbox_area = bounds.2.sub(&bounds.0).to_f64() * bounds.3.sub(&bounds.1).to_f64();
                let mut poly_area = 0.0_f64;
                if polygon.len() > 2 {
                    for i in 0..polygon.len() {
                        let j = (i + 1) % polygon.len();
                        poly_area += polygon[i].0.to_f64() * polygon[j].1.to_f64();
                        poly_area -= polygon[j].0.to_f64() * polygon[i].1.to_f64();
                    }
                    poly_area = poly_area.abs() / 2.0;
                }
                if bbox_area > 0.0 && (bbox_area - poly_area).abs() / bbox_area > 0.05 {
                    let zone_name = ki_zone
                        .name
                        .clone()
                        .filter(|n| !n.is_empty())
                        .unwrap_or_else(|| "Unnamed".to_string());
                    warnings.push(format!(
                        "Zone '{}' is non-rectangular. Approximating polygon (area={:.1}) with bounding box (area={:.1}).",
                        zone_name, poly_area, bbox_area
                    ));
                }
                let name = ki_zone
                    .name
                    .clone()
                    .filter(|n| !n.is_empty())
                    .unwrap_or_else(|| format!("Zone_{}", zones.len()));
                let net_classes = match &ki_zone.net_name {
                    Some(n) if !n.is_empty() => vec![n.clone()],
                    _ => vec!["Signal".to_string()],
                };
                let layers = if ki_zone.layers.is_empty() { vec!["F.Cu".to_string()] } else { ki_zone.layers.clone() };
                zones.push(ZoneOut { name, bounds, net_classes, polygon, layers });
            }
        }
    }
    (zones, warnings)
}

#[derive(Clone, Debug)]
struct ZoneOut {
    name: String,
    bounds: (Num, Num, Num, Num),
    net_classes: Vec<String>,
    polygon: Vec<(Num, Num)>,
    layers: Vec<String>,
}

// ===========================================================================
// 5. Text-regex surfaces (extract_footprint_positions, extract_net_classes)
// ===========================================================================

/// Port of `extract_footprint_positions` from `kicad_parser.py` (pure-text).
/// Compiled once; the pattern is a literal constant so compilation cannot
/// fail (same pattern as temper-io-types' footprint parser).
fn re_footprint_start() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    #[expect(clippy::unwrap_used, reason = "literal constant pattern cannot fail to compile")]
    RE.get_or_init(|| regex::Regex::new(r#"\(footprint\s+"[^"]+"\s+\(layer"#).unwrap())
}

fn re_fp_at() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    #[expect(clippy::unwrap_used, reason = "literal constant pattern cannot fail to compile")]
    RE.get_or_init(|| regex::Regex::new(r"\(at\s+([\d.-]+)\s+([\d.-]+)(?:\s+([\d.-]+))?\)").unwrap())
}

fn re_fp_ref() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    #[expect(clippy::unwrap_used, reason = "literal constant pattern cannot fail to compile")]
    RE.get_or_init(|| regex::Regex::new(r#"\(property\s+"Reference"\s+"([^"]+)""#).unwrap())
}

fn re_net_class_start() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    #[expect(clippy::unwrap_used, reason = "literal constant pattern cannot fail to compile")]
    RE.get_or_init(|| regex::Regex::new(r"\(net_class\b").unwrap())
}

fn re_net_class_name() -> &'static regex::Regex {
    static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    #[expect(clippy::unwrap_used, reason = "literal constant pattern cannot fail to compile")]
    RE.get_or_init(|| regex::Regex::new(r#"^\(net_class\s+"([^"]+)""#).unwrap())
}

// Per-pattern statics: a single `fn re_field(pattern)` would share one
// OnceLock across call sites (the first pattern wins for every field). Each
// field therefore gets its own function + static. The patterns are literal
// constants, so `Regex::new` cannot fail; clippy's unwrap_used does not fire
// inside macro bodies, hence no #[expect] here.
macro_rules! re_const {
    ($name:ident, $pattern:expr) => {
        fn $name() -> &'static regex::Regex {
            static RE: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
            RE.get_or_init(|| regex::Regex::new($pattern).unwrap())
        }
    };
}

re_const!(re_clearance, r"\(clearance\s+([\d.]+)\)");
re_const!(re_track_width, r"\(track_width\s+([\d.]+)\)");
re_const!(re_trace_width, r"\(trace_width\s+([\d.]+)\)");
re_const!(re_via_dia, r"\(via_dia\s+([\d.]+)\)");
re_const!(re_via_drill, r"\(via_drill\s+([\d.]+)\)");
re_const!(re_diff_pair_gap, r"\(diff_pair_gap\s+([\d.]+)\)");
re_const!(re_diff_pair_width, r"\(diff_pair_width\s+([\d.]+)\)");
re_const!(re_add_net, r#"\(add_net\s+"([^"]+)"\)"#);

fn extract_footprint_positions_pure(content: &str) -> Vec<(String, f64, f64, f64)> {
    let footprint_re = re_footprint_start();
    let at_re = re_fp_at();
    let ref_re = re_fp_ref();
    let starts: Vec<usize> = footprint_re.find_iter(content).map(|m| m.start()).collect();
    let mut out: Vec<(String, f64, f64, f64)> = Vec::new();
    for (i, start) in starts.iter().enumerate() {
        let end = starts.get(i + 1).copied().unwrap_or(content.len());
        let block = &content[*start..end];
        let Some(at_match) = at_re.find(block) else { continue };
        let at_str = &block[at_match.start()..at_match.end()];
        let Some(caps) = at_re.captures(at_str) else { continue };
        let x = caps.get(1).and_then(|g| g.as_str().parse::<f64>().ok()).unwrap_or(0.0);
        let y = caps.get(2).and_then(|g| g.as_str().parse::<f64>().ok()).unwrap_or(0.0);
        let rotation = match caps.get(3) {
            Some(g) => g.as_str().parse::<f64>().unwrap_or(0.0),
            None => 0.0,
        };
        let Some(ref_match) = ref_re.find(block) else { continue };
        let Some(ref_caps) = ref_re.captures(&block[ref_match.start()..ref_match.end()]) else { continue };
        let Some(ref_g) = ref_caps.get(1) else { continue };
        out.push((ref_g.as_str().to_string(), x, y, rotation));
    }
    out
}


/// Port of `extract_net_classes` from `_parse_nets.py` (pure-text).
fn extract_net_classes_pure(content: &str) -> Vec<(String, NetClassRaw)> {
    let start_re = re_net_class_start();
    let name_re = re_net_class_name();
    let clearance_re = re_clearance();
    let track_width_re = re_track_width();
    let trace_width_re = re_trace_width();
    let via_dia_re = re_via_dia();
    let via_drill_re = re_via_drill();
    let gap_re = re_diff_pair_gap();
    let dpw_re = re_diff_pair_width();
    let add_net_re = re_add_net();
    let starts: Vec<usize> = start_re.find_iter(content).map(|m| m.start()).collect();
    let mut out: Vec<(String, NetClassRaw)> = Vec::new();
    for start in starts {
        let mut balance = 0i64;
        let mut end = start;
        let mut found_start = false;
        let bytes = content.as_bytes();
        let mut i = start;
        while i < bytes.len() {
            let c = bytes[i] as char;
            if c == '(' {
                balance += 1;
                found_start = true;
            } else if c == ')' {
                balance -= 1;
            }
            if found_start && balance == 0 {
                end = i + 1;
                break;
            }
            i += 1;
        }
        let block = &content[start..end];
        let Some(name_match) = name_re.find(block) else { continue };
        let Some(name_caps) = name_re.captures(&block[name_match.start()..name_match.end()]) else { continue };
        let Some(name_g) = name_caps.get(1) else { continue };
        let name = name_g.as_str().to_string();
        let get_float = |re: &regex::Regex, block: &str| -> Option<f64> {
            re.captures(block).and_then(|c| c.get(1)).and_then(|g| g.as_str().parse::<f64>().ok())
        };
        let clearance = get_float(clearance_re, block);
        let track_width = get_float(track_width_re, block);
        let trace_width = get_float(trace_width_re, block);
        // Oracle: `get_float(r"\(track_width ...\)") or get_float(...)` --
        // a parsed `(track_width 0)` is FALSY there, so it falls through to
        // the trace_width lookup and then to None (-> the 0.25 default
        // downstream). `Some(0.0).or(...)` would keep 0.0 and diverge.
        let trace_width = match track_width {
            Some(v) if v != 0.0 => Some(v),
            _ => trace_width,
        };
        let via_dia = get_float(via_dia_re, block);
        let via_drill = get_float(via_drill_re, block);
        let gap = get_float(gap_re, block);
        let dpw = get_float(dpw_re, block);
        let nets: Vec<String> = add_net_re
            .captures_iter(block)
            .filter_map(|c| c.get(1))
            .map(|g| g.as_str().to_string())
            .collect();
        out.push((
            name,
            NetClassRaw {
                clearance,
                trace_width,
                via_dia,
                via_drill,
                gap,
                dpw,
                nets,
            },
        ));
    }
    out
}


#[derive(Clone, Debug)]
struct NetClassRaw {
    clearance: Option<f64>,
    trace_width: Option<f64>,
    via_dia: Option<f64>,
    via_drill: Option<f64>,
    gap: Option<f64>,
    dpw: Option<f64>,
    nets: Vec<String>,
}

// ===========================================================================
// 6. pyo3: dataclass pyclasses for the parse output (_kicad_types.py)
// ===========================================================================

#[pyclass(dict, module = "temper_design_bundle_python.parse_engine")]
#[derive(Debug)]
pub struct TraceData {
    #[pyo3(get, set)]
    pub start: Py<PyAny>,
    #[pyo3(get, set)]
    pub end: Py<PyAny>,
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub net: Py<PyAny>,
}

impl TraceData {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.start),
            same(py, &self.end),
            same(py, &self.width),
            same(py, &self.layer),
            same(py, &self.net),
        ]
    }
}

#[pymethods]
impl TraceData {
    #[new]
    #[pyo3(signature = (start, end, width, layer, net=None))]
    fn new(
        py: Python<'_>,
        start: &Bound<'_, PyAny>,
        end: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        layer: &Bound<'_, PyAny>,
        net: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            start: start.clone().unbind(),
            end: end.clone().unbind(),
            width: width.clone().unbind(),
            layer: layer.clone().unbind(),
            net: match net {
                Some(v) => v.clone().unbind(),
                None => py.None(),
            },
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "TraceData",
            &[
                ("start", repr_of(&self.start, py)?),
                ("end", repr_of(&self.end, py)?),
                ("width", repr_of(&self.width, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("net", repr_of(&self.net, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("TraceData"))
    }
}

#[pyclass(dict, module = "temper_design_bundle_python.parse_engine")]
#[derive(Debug)]
pub struct PadData {
    #[pyo3(get, set)]
    pub position: Py<PyAny>,
    #[pyo3(get, set)]
    pub size: Py<PyAny>,
    #[pyo3(get, set)]
    pub shape: Py<PyAny>,
    #[pyo3(get, set)]
    pub drill: Py<PyAny>,
    #[pyo3(get, set)]
    pub rotation: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub number: Py<PyAny>,
    #[pyo3(get, set)]
    pub net: Py<PyAny>,
    #[pyo3(get, set)]
    pub component_ref: Py<PyAny>,
}

impl PadData {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.position),
            same(py, &self.size),
            same(py, &self.shape),
            same(py, &self.drill),
            same(py, &self.rotation),
            same(py, &self.layer),
            same(py, &self.number),
            same(py, &self.net),
            same(py, &self.component_ref),
        ]
    }
}

#[pymethods]
impl PadData {
    #[new]
    #[pyo3(signature = (position, size, shape, drill=None, rotation=None, layer=None, number=None, net=None, component_ref=None))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        position: &Bound<'_, PyAny>,
        size: &Bound<'_, PyAny>,
        shape: &Bound<'_, PyAny>,
        drill: Option<&Bound<'_, PyAny>>,
        rotation: Option<&Bound<'_, PyAny>>,
        layer: Option<&Bound<'_, PyAny>>,
        number: Option<&Bound<'_, PyAny>>,
        net: Option<&Bound<'_, PyAny>>,
        component_ref: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let f = |py: Python<'_>, v: Option<&Bound<'_, PyAny>>, d: f64| -> PyResult<Py<PyAny>> {
            match v {
                Some(v) => Ok(v.clone().unbind()),
                None => d.into_py_any(py),
            }
        };
        let s = |py: Python<'_>, v: Option<&Bound<'_, PyAny>>, d: &str| -> PyResult<Py<PyAny>> {
            match v {
                Some(v) => Ok(v.clone().unbind()),
                None => d.into_py_any(py),
            }
        };
        Ok(Self {
            position: position.clone().unbind(),
            size: size.clone().unbind(),
            shape: shape.clone().unbind(),
            drill: f(py, drill, 0.0)?,
            rotation: f(py, rotation, 0.0)?,
            layer: s(py, layer, "F.Cu")?,
            number: s(py, number, "")?,
            net: match net {
                Some(v) => v.clone().unbind(),
                None => py.None(),
            },
            component_ref: match component_ref {
                Some(v) => v.clone().unbind(),
                None => py.None(),
            },
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "PadData",
            &[
                ("position", repr_of(&self.position, py)?),
                ("size", repr_of(&self.size, py)?),
                ("shape", repr_of(&self.shape, py)?),
                ("drill", repr_of(&self.drill, py)?),
                ("rotation", repr_of(&self.rotation, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("number", repr_of(&self.number, py)?),
                ("net", repr_of(&self.net, py)?),
                ("component_ref", repr_of(&self.component_ref, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("PadData"))
    }
}

#[pyclass(dict, module = "temper_design_bundle_python.parse_engine")]
#[derive(Debug)]
pub struct ViaData {
    #[pyo3(get, set)]
    pub position: Py<PyAny>,
    #[pyo3(get, set)]
    pub diameter: Py<PyAny>,
    #[pyo3(get, set)]
    pub drill: Py<PyAny>,
    #[pyo3(get, set)]
    pub net: Py<PyAny>,
    #[pyo3(get, set)]
    pub layers: Py<PyAny>,
}

impl ViaData {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.position),
            same(py, &self.diameter),
            same(py, &self.drill),
            same(py, &self.net),
            same(py, &self.layers),
        ]
    }
}

#[pymethods]
impl ViaData {
    #[new]
    #[pyo3(signature = (position, diameter, drill, net=None, layers=None))]
    fn new(
        py: Python<'_>,
        position: &Bound<'_, PyAny>,
        diameter: &Bound<'_, PyAny>,
        drill: &Bound<'_, PyAny>,
        net: Option<&Bound<'_, PyAny>>,
        layers: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            position: position.clone().unbind(),
            diameter: diameter.clone().unbind(),
            drill: drill.clone().unbind(),
            net: match net {
                Some(v) => v.clone().unbind(),
                None => py.None(),
            },
            layers: match layers {
                Some(v) => v.clone().unbind(),
                None => PyTuple::new(py, ["F.Cu", "B.Cu"])?.into_any().unbind(),
            },
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ViaData",
            &[
                ("position", repr_of(&self.position, py)?),
                ("diameter", repr_of(&self.diameter, py)?),
                ("drill", repr_of(&self.drill, py)?),
                ("net", repr_of(&self.net, py)?),
                ("layers", repr_of(&self.layers, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ViaData"))
    }
}

/// kiutils' `DrillDefinition` dataclass, reproduced as a pyclass so pads with
/// a `(drill ...)` token carry the same object shape (and repr) into
/// `Pin.drill` / `PadData.drill`.
#[pyclass(dict, module = "temper_design_bundle_python.parse_engine")]
#[derive(Debug)]
pub struct DrillDefinition {
    #[pyo3(get, set)]
    pub oval: Py<PyAny>,
    #[pyo3(get, set)]
    pub diameter: Py<PyAny>,
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub offset: Py<PyAny>,
}

impl DrillDefinition {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.oval),
            same(py, &self.diameter),
            same(py, &self.width),
            same(py, &self.offset),
        ]
    }
}

#[pymethods]
impl DrillDefinition {
    #[new]
    #[pyo3(signature = (oval=None, diameter=None, width=None, offset=None))]
    fn new(
        py: Python<'_>,
        oval: Option<&Bound<'_, PyAny>>,
        diameter: Option<&Bound<'_, PyAny>>,
        width: Option<&Bound<'_, PyAny>>,
        offset: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            oval: match oval {
                Some(v) => v.clone().unbind(),
                None => false.into_py_any(py)?,
            },
            diameter: match diameter {
                Some(v) => v.clone().unbind(),
                None => 0.0_f64.into_py_any(py)?,
            },
            width: match width {
                Some(v) => v.clone().unbind(),
                None => py.None(),
            },
            offset: match offset {
                Some(v) => v.clone().unbind(),
                None => py.None(),
            },
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "DrillDefinition",
            &[
                ("oval", repr_of(&self.oval, py)?),
                ("diameter", repr_of(&self.diameter, py)?),
                ("width", repr_of(&self.width, py)?),
                ("offset", repr_of(&self.offset, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("DrillDefinition"))
    }
}

/// kiutils' `Position` dataclass, reproduced so `DrillDefinition.offset`
/// reprs identically (`Position(X=..., Y=..., angle=None, unlocked=False)`).
#[pyclass(dict, module = "temper_design_bundle_python.parse_engine")]
#[derive(Debug)]
pub struct Position {
    // Field names X/Y match kiutils' Position dataclass (repr parity).
    #[pyo3(get, set, name = "X")]
    pub x: Py<PyAny>,
    #[pyo3(get, set, name = "Y")]
    pub y: Py<PyAny>,
    #[pyo3(get, set)]
    pub angle: Py<PyAny>,
    #[pyo3(get, set)]
    pub unlocked: Py<PyAny>,
}

impl Position {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.x),
            same(py, &self.y),
            same(py, &self.angle),
            same(py, &self.unlocked),
        ]
    }
}

#[pymethods]
impl Position {
    #[new]
    #[pyo3(signature = (x=None, y=None, angle=None, unlocked=None))]
    fn new(
        py: Python<'_>,
        x: Option<&Bound<'_, PyAny>>,
        y: Option<&Bound<'_, PyAny>>,
        angle: Option<&Bound<'_, PyAny>>,
        unlocked: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let f = |py: Python<'_>, v: Option<&Bound<'_, PyAny>>, d: f64| -> PyResult<Py<PyAny>> {
            match v {
                Some(v) => Ok(v.clone().unbind()),
                None => d.into_py_any(py),
            }
        };
        Ok(Self {
            x: f(py, x, 0.0)?,
            y: f(py, y, 0.0)?,
            angle: match angle {
                Some(v) => v.clone().unbind(),
                None => py.None(),
            },
            unlocked: match unlocked {
                Some(v) => v.clone().unbind(),
                None => false.into_py_any(py)?,
            },
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Position",
            &[
                ("X", repr_of(&self.x, py)?),
                ("Y", repr_of(&self.y, py)?),
                ("angle", repr_of(&self.angle, py)?),
                ("unlocked", repr_of(&self.unlocked, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Position"))
    }
}

#[pyclass(dict, module = "temper_design_bundle_python.parse_engine")]
#[derive(Debug)]
pub struct ParseResult {
    // Wave-4 "PyAny removal" tightening (2026-08-04): `netlist`/`board` are
    // always constructed as the `Netlist`/`Board` pyclasses (build_netlist /
    // build_board / reference_loader.py), so the opaque `Py<PyAny>` handle
    // is replaced by the typed reference. Behavior is unchanged: the wrapped
    // value IS the pyclass and identity is preserved by the typed handle.
    // The remaining four fields stay `Py<PyAny>` (Python list containers;
    // identity-mutable, no-coercion — STILL-NEEDED per the PyAny surface
    // audit, docs/evidence/2026-08-05-pyany-surface-audit.md).
    #[pyo3(get, set)]
    pub netlist: Py<Netlist>,
    #[pyo3(get, set)]
    pub board: Py<Board>,
    #[pyo3(get, set)]
    pub warnings: Py<PyAny>,
    #[pyo3(get, set)]
    pub traces: Py<PyAny>,
    #[pyo3(get, set)]
    pub vias: Py<PyAny>,
    #[pyo3(get, set)]
    pub pads: Py<PyAny>,
}

impl ParseResult {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.netlist.clone_ref(py).into_any(),
            self.board.clone_ref(py).into_any(),
            same(py, &self.warnings),
            same(py, &self.traces),
            same(py, &self.vias),
            same(py, &self.pads),
        ]
    }
}

#[pymethods]
impl ParseResult {
    #[new]
    #[pyo3(signature = (netlist, board, warnings, traces=None, vias=None, pads=None))]
    fn new(
        py: Python<'_>,
        netlist: &Bound<'_, Netlist>,
        board: &Bound<'_, Board>,
        warnings: &Bound<'_, PyAny>,
        traces: Option<&Bound<'_, PyAny>>,
        vias: Option<&Bound<'_, PyAny>>,
        pads: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let empty = || PyList::empty(py).into_any().unbind();
        Ok(Self {
            netlist: netlist.clone().unbind(),
            board: board.clone().unbind(),
            warnings: warnings.clone().unbind(),
            traces: match traces {
                Some(v) => v.clone().unbind(),
                None => empty(),
            },
            vias: match vias {
                Some(v) => v.clone().unbind(),
                None => empty(),
            },
            pads: match pads {
                Some(v) => v.clone().unbind(),
                None => empty(),
            },
        })
    }

    #[getter]
    fn has_warnings(&self, py: Python<'_>) -> PyResult<bool> {
        Ok(self.warnings.bind(py).len()? > 0)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let netlist = self.netlist.clone_ref(py).into_any();
        let board = self.board.clone_ref(py).into_any();
        Ok(dataclass_repr(
            "ParseResult",
            &[
                ("netlist", repr_of(&netlist, py)?),
                ("board", repr_of(&board, py)?),
                ("warnings", repr_of(&self.warnings, py)?),
                ("traces", repr_of(&self.traces, py)?),
                ("vias", repr_of(&self.vias, py)?),
                ("pads", repr_of(&self.pads, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ParseResult"))
    }
}

// ===========================================================================
// 7. pyfunctions
// ===========================================================================

fn num_to_py(py: Python<'_>, v: Num) -> PyResult<Py<PyAny>> {
    match v {
        Num::I(i) => i.into_py_any(py),
        Num::F(f) => f.into_py_any(py),
    }
}

fn atom_to_py(py: Python<'_>, atom: &KiAtom) -> PyResult<Py<PyAny>> {
    match atom {
        KiAtom::Str(s) | KiAtom::Bare(s) => s.clone().into_py_any(py),
        KiAtom::Int(v) => (*v).into_py_any(py),
        KiAtom::Float(v) => (*v).into_py_any(py),
        KiAtom::List(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(node_to_py(py, item)?.bind(py))?;
            }
            list.into_any().unbind().into_py_any(py)
        }
    }
}

fn node_to_py(py: Python<'_>, node: &KiNode) -> PyResult<Py<PyAny>> {
    match node {
        KiNode::Atom(a) => atom_to_py(py, a),
        KiNode::List(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(node_to_py(py, item)?.bind(py))?;
            }
            list.into_any().unbind().into_py_any(py)
        }
    }
}

fn build_drill_definition(py: Python<'_>, drill: &RawDrill) -> PyResult<Py<PyAny>> {
    let cls = py.get_type::<DrillDefinition>();
    let oval: Py<PyAny> = drill.oval.into_py_any(py)?;
    let diameter: Py<PyAny> = match &drill.diameter {
        Some(a) => atom_to_py(py, a)?,
        None => 0.0_f64.into_py_any(py)?,
    };
    let width: Py<PyAny> = match &drill.width {
        Some(a) => atom_to_py(py, a)?,
        None => py.None(),
    };
    let offset: Py<PyAny> = match &drill.offset {
        Some(pos) => {
            let pos_cls = py.get_type::<Position>();
            let xo = num_to_py(py, pos.x)?;
            let yo = num_to_py(py, pos.y)?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("x", xo.bind(py))?;
            kwargs.set_item("y", yo.bind(py))?;
            // kiutils' Position keeps `angle` (exp[3] unless it is the
            // `unlocked` marker) and scans the whole list for `unlocked` --
            // both must survive into the Position pyclass.
            match pos.angle {
                Some(a) => kwargs.set_item("angle", num_to_py(py, a)?.bind(py))?,
                None => kwargs.set_item("angle", py.None())?,
            }
            kwargs.set_item("unlocked", pos.unlocked)?;
            pos_cls.call((), Some(&kwargs))?.unbind()
        }
        None => py.None(),
    };
    cls.call((oval, diameter, width, offset), None)?.unbind().into_py_any(py)
}

/// Construct a `Board` pyclass from the pure extraction result.
fn build_board(
    py: Python<'_>,
    raw: &RawBoard,
    zone_warnings: &mut Vec<String>,
) -> PyResult<Py<Board>> {
    let board_cls = py.get_type::<crate::board_contracts::Board>();
    let mount_cls = py.get_type::<crate::board_contracts::MountingHole>();
    let zone_cls = py.get_type::<crate::board_contracts::Zone>();
    let (width, height, origin) = extract_board_geometry_pure(raw);
    if width.is_none() {
        // No Edge.Cuts (or unparseable): fall back to Board.temper_default().
        let message = if raw.graphic_items.iter().any(|g| g_layer(g) == "Edge.Cuts") {
            "Edge.Cuts geometry present but has no parseable coordinate data. Falling back to Board.temper_default()."
        } else {
            "No Edge.Cuts found in PCB. Using default 100x150mm."
        };
        zone_warnings.push(message.to_string());
        return Ok(board_cls
            .call_method("temper_default", (), None)?
            .extract::<Py<Board>>()?);
    }
    let width = width.ok_or_else(|| PyValueError::new_err("edge cuts width missing"))?;
    let height = height.ok_or_else(|| PyValueError::new_err("edge cuts height missing"))?;
    let (ox, oy) = origin.ok_or_else(|| PyValueError::new_err("edge cuts origin missing"))?;
    // mounting holes
    let mut holes: Vec<Py<PyAny>> = Vec::new();
    for fp in &raw.footprints {
        let mut is_mounting_hole = false;
        if fp.entry_name.contains("MountingHole") {
            is_mounting_hole = true;
        }
        if !is_mounting_hole {
            for item in &fp.graphic_items {
                if let RawFpItem::Text { text, .. } = item
                    && text.contains("MountingHole") {
                        is_mounting_hole = true;
                        break;
                    }
            }
        }
        if is_mounting_hole {
            let px = fp.position.x.sub(&ox);
            let py_val = fp.position.y.sub(&oy);
            let pos = PyTuple::new(py, [num_to_py(py, px)?, num_to_py(py, py_val)?])?;
            holes.push(mount_cls.call((pos, 3.2_f64), None)?.unbind());
        }
    }
    // zones
    let (zone_outs, zwarns) = extract_zones_pure(raw, ox, oy);
    zone_warnings.extend(zwarns);
    let mut zone_objs: Vec<Py<PyAny>> = Vec::new();
    for z in &zone_outs {
        let bounds = PyTuple::new(
            py,
            [
                num_to_py(py, z.bounds.0)?,
                num_to_py(py, z.bounds.1)?,
                num_to_py(py, z.bounds.2)?,
                num_to_py(py, z.bounds.3)?,
            ],
        )?;
        let net_classes = PyList::new(py, z.net_classes.iter().map(|s| s.as_str()))?;
        let poly = PyList::empty(py);
        for (x, y) in &z.polygon {
            poly.append(PyTuple::new(py, [num_to_py(py, *x)?, num_to_py(py, *y)?])?)?;
        }
        let layers = PyList::new(py, z.layers.iter().map(|s| s.as_str()))?;
        zone_objs.push(zone_cls.call((z.name.clone(), bounds, net_classes, py.None(), py.None(), poly, layers), None)?.unbind());
    }
    let holes_list = PyList::new(py, holes.iter().map(|h| h.bind(py)))?;
    let zones_list = PyList::new(py, zone_objs.iter().map(|z| z.bind(py)))?;
    let width_py = num_to_py(py, width)?;
    let height_py = num_to_py(py, height)?;
    let origin_py = PyTuple::new(py, [num_to_py(py, ox)?, num_to_py(py, oy)?])?;
    Ok(board_cls
        .call(
            (width_py.bind(py), height_py.bind(py), origin_py, zones_list, holes_list),
            None,
        )?
        .extract::<Py<Board>>()?)
}

/// Construct the contract pyclasses (Component/Pin/Net/Netlist) from the
/// pure extraction outputs.
fn build_netlist(
    py: Python<'_>,
    components: &[CompOut],
    net_names: &[(String, Vec<(String, String)>)],
) -> PyResult<Py<Netlist>> {
    let pin_cls = py.get_type::<crate::netlist_contracts::Pin>();
    let comp_cls = py.get_type::<crate::netlist_contracts::Component>();
    let net_cls = py.get_type::<crate::netlist_contracts::Net>();
    let netlist_cls = py.get_type::<crate::netlist_contracts::Netlist>();
    let mut comp_objs: Vec<Py<PyAny>> = Vec::new();
    for c in components {
        let mut pin_objs: Vec<Py<PyAny>> = Vec::new();
        for p in &c.pins {
            let pos = PyTuple::new(py, [num_to_py(py, p.position.0)?, num_to_py(py, p.position.1)?])?;
            let net_py: Py<PyAny> = match &p.net {
                Some(n) => n.clone().into_py_any(py)?,
                None => py.None(),
            };
            let drill_py: Py<PyAny> = match &p.drill {
                NumOrDrill::Num(v) => num_to_py(py, *v)?,
                NumOrDrill::Drill(d) => build_drill_definition(py, d)?,
            };
            let width_py = num_to_py(py, p.width)?;
            let height_py = num_to_py(py, p.height)?;
            let ratio_py = num_to_py(py, p.roundrect_ratio)?;
            pin_objs.push(
                pin_cls.call(
                    (
                        p.name.clone(),
                        p.number.clone(),
                        pos,
                        net_py,
                        width_py,
                        height_py,
                        p.shape.clone(),
                        p.layer.clone(),
                        drill_py,
                        p.is_pth,
                        ratio_py,
                        p.pad_rotation_deg,
                    ),
                    None,
                )?
                .unbind(),
            );
        }
        let bounds = PyTuple::new(py, [c.bounds.0, c.bounds.1])?;
        let pins_list = PyList::new(py, pin_objs.iter().map(|p| p.bind(py)))?;
        let attrs = PyDict::new(py);
        for (k, v) in &c.attributes {
            attrs.set_item(k, v)?;
        }
        let sheetpath: Py<PyAny> = match &c.sheetpath {
            Some(s) => s.clone().into_py_any(py)?,
            None => py.None(),
        };
        let ref_py = c.r#ref.clone().into_py_any(py)?;
        let fp_py = c.footprint.clone().into_py_any(py)?;
        let fixed_py = c.fixed.into_py_any(py)?;
        let rot_py = c.initial_rotation_quadrant.into_py_any(py)?;
        let side_py = c.initial_side.into_py_any(py)?;
        let pos_py: Py<PyAny> = PyTuple::new(py, [c.initial_position.0, c.initial_position.1])?.into_any().unbind();
        let bounds_py = bounds.into_any().unbind();
        let pins_py = pins_list.into_any().unbind();
        let attrs_py = attrs.into_any().unbind();
        let args = PyTuple::new(
            py,
            [
                ref_py,
                fp_py,
                bounds_py,
                pins_py,
                py.None(),
                py.None(),
                fixed_py,
                pos_py,
                rot_py,
                side_py,
                attrs_py,
                py.None(),
                sheetpath,
            ],
        )?;
        comp_objs.push(comp_cls.call(args, None)?.unbind());
    }
    let mut net_objs: Vec<Py<PyAny>> = Vec::new();
    for (name, pins) in net_names {
        let pins_list = PyList::empty(py);
        for (ref_str, pin_name) in pins {
            pins_list.append(PyTuple::new(py, [ref_str, pin_name])?)?;
        }
        net_objs.push(net_cls.call((name, pins_list), None)?.unbind());
    }
    let comps_list = PyList::new(py, comp_objs.iter().map(|c| c.bind(py)))?;
    let nets_list = PyList::new(py, net_objs.iter().map(|n| n.bind(py)))?;
    Ok(netlist_cls
        .call((comps_list, nets_list), None)?
        .extract::<Py<Netlist>>()?)
}

fn build_trace_data(py: Python<'_>, t: &TraceOut) -> PyResult<Py<PyAny>> {
    let cls = py.get_type::<TraceData>();
    let start = PyTuple::new(py, [num_to_py(py, t.start.0)?, num_to_py(py, t.start.1)?])?;
    let end = PyTuple::new(py, [num_to_py(py, t.end.0)?, num_to_py(py, t.end.1)?])?;
    let width = num_to_py(py, t.width)?;
    let net: Py<PyAny> = match &t.net {
        Some(n) => n.clone().into_py_any(py)?,
        None => py.None(),
    };
    cls.call((start, end, width, t.layer.clone(), net), None)?.unbind().into_py_any(py)
}

fn build_via_data(py: Python<'_>, v: &ViaOut) -> PyResult<Py<PyAny>> {
    let cls = py.get_type::<ViaData>();
    let pos = PyTuple::new(py, [num_to_py(py, v.position.0)?, num_to_py(py, v.position.1)?])?;
    let diameter = num_to_py(py, v.diameter)?;
    let drill = num_to_py(py, v.drill)?;
    let net: Py<PyAny> = match &v.net {
        Some(n) => n.clone().into_py_any(py)?,
        None => py.None(),
    };
    let layers = PyTuple::new(py, v.layers.iter().map(|s| s.as_str()))?;
    cls.call((pos, diameter, drill, net, layers), None)?.unbind().into_py_any(py)
}

fn build_pad_data(py: Python<'_>, p: &PadOut) -> PyResult<Py<PyAny>> {
    let cls = py.get_type::<PadData>();
    let pos = PyTuple::new(py, [p.position.0, p.position.1])?;
    let size = PyTuple::new(py, [num_to_py(py, p.size.0)?, num_to_py(py, p.size.1)?])?;
    let drill: Py<PyAny> = match &p.drill {
        NumOrDrill::Num(v) => num_to_py(py, *v)?,
        NumOrDrill::Drill(d) => build_drill_definition(py, d)?,
    };
    let rotation = num_to_py(py, p.rotation)?;
    let net: Py<PyAny> = match &p.net {
        Some(n) => n.clone().into_py_any(py)?,
        None => py.None(),
    };
    let comp_ref: Py<PyAny> = match &p.component_ref {
        Some(s) => s.clone().into_py_any(py)?,
        None => py.None(),
    };
    cls.call(
        (pos, size, p.shape.clone(), drill, rotation, p.layer.clone(), p.number.clone(), net, comp_ref),
        None,
    )?
    .unbind()
    .into_py_any(py)
}

/// The full `parse_kicad_pcb` engine: text in, ParseResult pyclass out.
///
/// `net_class_mapping`, when given, is a `net_name -> net_class` Python dict
/// (or any mapping-like object `Netlist.apply_net_class_mapping` accepts)
/// applied to the freshly built netlist before it is returned -- this is
/// what makes the parser assign real per-net classes at parse time instead
/// of leaving every net at `Net::new`'s `"Signal"` default (see
/// `netlist_contracts.rs`'s `Net::new`). The caller (the Python
/// `kicad_parser.parse_kicad_pcb` shim) passes the project's own
/// `TEMPER_NET_ASSIGNMENTS` SSOT here by default -- the table itself is
/// never transcribed into Rust, only threaded through once per call, so
/// there is no second hand-maintained copy to drift from the first (see
/// the docs/evidence 2026-08-11 correspondence-gate family this mirrors).
/// Uses the existing, already-tested `apply_net_class_mapping` (silent
/// skip-on-miss -- matches this table's own documented historical-alias
/// convention: some keys intentionally name nets absent from the current
/// board), not the `_strict` variant, which would hard-error on those.
fn parse_kicad_pcb_impl(
    py: Python<'_>,
    pcb_content: &str,
    normalize: bool,
    net_class_mapping: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyAny>> {
    let raw = parse_kicad_document(pcb_content).map_err(PyValueError::new_err)?;
    let mut warnings: Vec<String> = Vec::new();

    // net_map: str(net.number) -> net.name
    let mut net_map: HashMap<String, String> = HashMap::new();
    for n in &raw.nets {
        net_map.insert(num_to_string(n.number), n.name.clone());
    }

    let board = build_board(py, &raw, &mut warnings)?;

    if raw.footprints.is_empty() {
        warnings.insert(0, "No footprints found in PCB.".to_string());
        let netlist = build_netlist(py, &[], &[])?;
        return build_parse_result(py, netlist, board, warnings, Vec::new(), Vec::new(), Vec::new());
    }

    let origin_to_use = if normalize {
        let ox = board.bind(py).getattr("origin")?.get_item(0)?.extract::<f64>()?;
        let oy = board.bind(py).getattr("origin")?.get_item(1)?.extract::<f64>()?;
        (ox, oy)
    } else {
        (0.0, 0.0)
    };

    let components = extract_components_pure(&raw, origin_to_use);
    let nets = extract_nets_pure(&components);
    let (traces, vias) = extract_traces_pure(&raw, &net_map);
    let pads = extract_pads_pure(&raw);

    let netlist = build_netlist(py, &components, &nets)?;

    if let Some(mapping) = net_class_mapping {
        netlist
            .bind(py)
            .call_method1("apply_net_class_mapping", (mapping,))?;
    }

    let trace_objs: Vec<Py<PyAny>> = traces.iter().map(|t| build_trace_data(py, t)).collect::<PyResult<_>>()?;
    let via_objs: Vec<Py<PyAny>> = vias.iter().map(|v| build_via_data(py, v)).collect::<PyResult<_>>()?;
    let pad_objs: Vec<Py<PyAny>> = pads.iter().map(|p| build_pad_data(py, p)).collect::<PyResult<_>>()?;

    build_parse_result(py, netlist, board, warnings, trace_objs, via_objs, pad_objs)
}

fn build_parse_result(
    py: Python<'_>,
    netlist: Py<Netlist>,
    board: Py<Board>,
    warnings: Vec<String>,
    traces: Vec<Py<PyAny>>,
    vias: Vec<Py<PyAny>>,
    pads: Vec<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let cls = py.get_type::<ParseResult>();
    let warnings_list = PyList::new(py, warnings.iter().map(|s| s.as_str()))?;
    let traces_list = PyList::new(py, traces.iter().map(|t| t.bind(py)))?;
    let vias_list = PyList::new(py, vias.iter().map(|v| v.bind(py)))?;
    let pads_list = PyList::new(py, pads.iter().map(|p| p.bind(py)))?;
    cls.call((netlist, board, warnings_list, traces_list, vias_list, pads_list), None)?
        .unbind()
        .into_py_any(py)
}

#[pyfunction(signature = (pcb_content, normalize=true, net_class_mapping=None))]
fn parse_kicad_pcb(
    py: Python<'_>,
    pcb_content: &str,
    normalize: bool,
    net_class_mapping: Option<&Bound<'_, PyAny>>,
) -> PyResult<Py<PyAny>> {
    parse_kicad_pcb_impl(py, pcb_content, normalize, net_class_mapping)
}

/// Extract component positions from raw KiCad PCB content without kiutils.
///
/// Args:
///     content: Raw KiCad PCB file content as string.
///
/// Returns:
///     Dict mapping component reference to position info:
///     ``{"U1": {"x": 50.5, "y": 75.25, "rotation": 90.0}, ...}``
#[pyfunction]
fn extract_footprint_positions(py: Python<'_>, content: &str) -> PyResult<Py<PyAny>> {
    let positions = extract_footprint_positions_pure(content);
    let out = PyDict::new(py);
    for (ref_str, x, y, rotation) in positions {
        let inner = PyDict::new(py);
        inner.set_item("x", x)?;
        inner.set_item("y", y)?;
        inner.set_item("rotation", rotation)?;
        out.set_item(ref_str, inner)?;
    }
    out.into_any().unbind().into_py_any(py)
}

/// Test/conformance surface: tokenize `content` with the kiutils-exact
/// tokenizer and return the top-level s-expression as a Python value (the
/// same shape kiutils' ``parse_sexp`` returns -- ``out[0]``). Drives the
/// tokenizer-conformance test against ``kiutils.utils.sexpr.parse_sexp`` on
/// adversarial token strings (caret, adjacent quotes, backslash-quote runs,
/// ``+5``, CRLF) so the "kiutils-exact" claim is asserted as written, not
/// just on the corpus.
#[pyfunction]
fn tokenize(py: Python<'_>, content: &str) -> PyResult<Py<PyAny>> {
    let tree = parse_ki_document(content).map_err(PyValueError::new_err)?;
    let Some(first) = tree.first() else {
        // kiutils' parse_sexp does `return out[0]` -- an empty input raises
        // IndexError there; fail closed the same way.
        return Err(PyValueError::new_err("cannot index empty token stream"));
    };
    node_to_py(py, first)
}

#[pyfunction]
fn extract_net_classes(py: Python<'_>, content: &str) -> PyResult<Py<PyAny>> {
    let classes = extract_net_classes_pure(content);
    let out = PyDict::new(py);
    for (name, rules) in classes {
        let inner = PyDict::new(py);
        inner.set_item("clearance", rules.clearance)?;
        inner.set_item("trace_width", rules.trace_width)?;
        inner.set_item("via_dia", rules.via_dia)?;
        inner.set_item("via_drill", rules.via_drill)?;
        inner.set_item("diff_pair_gap", rules.gap)?;
        inner.set_item("diff_pair_width", rules.dpw)?;
        let nets = PyList::new(py, rules.nets.iter().map(|s| s.as_str()))?;
        inner.set_item("nets", nets)?;
        out.set_item(name, inner)?;
    }
    out.into_any().unbind().into_py_any(py)
}

/// Raw stackup + plane-relevant zone data for the v6 stackup assembly (the
/// assembly itself stays Python: it targets router_v6.stage0_data dataclasses
/// and reads the netclass SSOT via `_is_plane_required_net`).
#[pyfunction]
fn extract_stackup_raw(py: Python<'_>, content: &str) -> PyResult<Py<PyAny>> {
    let raw = parse_kicad_document(content).map_err(PyValueError::new_err)?;
    let out = PyDict::new(py);
    let layers = PyList::empty(py);
    for l in &raw.stackup_layers {
        let entry = PyDict::new(py);
        entry.set_item("name", l.name.clone())?;
        entry.set_item("type", l.layer_type.clone())?;
        entry.set_item("thickness", match l.thickness {
            Some(t) => num_to_py(py, t)?,
            None => py.None(),
        })?;
        entry.set_item("material", match &l.material {
            Some(m) => m.clone().into_py_any(py)?,
            None => py.None(),
        })?;
        entry.set_item("epsilon_r", match l.epsilon_r {
            Some(t) => num_to_py(py, t)?,
            None => py.None(),
        })?;
        entry.set_item("loss_tangent", match l.loss_tangent {
            Some(t) => num_to_py(py, t)?,
            None => py.None(),
        })?;
        layers.append(entry)?;
    }
    out.set_item("stackup_layers", layers)?;
    let zones = PyList::empty(py);
    for z in &raw.zones {
        let entry = PyDict::new(py);
        entry.set_item("net_name", match &z.net_name {
            Some(n) => n.clone().into_py_any(py)?,
            None => py.None(),
        })?;
        let zone_layers = PyList::new(py, z.layers.iter().map(|s| s.as_str()))?;
        entry.set_item("layers", zone_layers)?;
        zones.append(entry)?;
    }
    out.set_item("zones", zones)?;
    let board_layers = PyList::new(py, raw.layers.iter().map(|s| s.as_str()))?;
    out.set_item("layers", board_layers)?;
    // Additive (2026-08-14): index-aligned with `"layers"` above -- the
    // declared role token (`signal`/`power`/`mixed`/`jumper`/`user`) for
    // each entry, or `""` if the board declared no third token for it. See
    // `RawBoard::layer_roles`'s doc comment. Not yet read by
    // `_extract_stackup` in `_parse_board.py` -- see that function's
    // `use_declared_layer_roles` docstring for why wiring it in is a
    // separate, deliberately out-of-scope change.
    let board_layer_roles = PyList::new(py, raw.layer_roles.iter().map(|s| s.as_str()))?;
    out.set_item("layer_roles", board_layer_roles)?;
    out.set_item("general_thickness", match raw.general_thickness {
        Some(t) => num_to_py(py, t)?,
        None => py.None(),
    })?;
    out.into_any().unbind().into_py_any(py)
}

/// Board dimensions + pad sizes + raw courtyard inputs for kicad_metadata.
/// The courtyard POLYGONS are computed by the Python shim's shapely step
/// (GEOS is not reimplementable bit-exactly in Rust; see module docs).
#[pyfunction]
fn extract_metadata_raw(py: Python<'_>, content: &str) -> PyResult<Py<PyAny>> {
    let raw = parse_kicad_document(content).map_err(PyValueError::new_err)?;
    let out = PyDict::new(py);

    // board dimensions from Edge.Cuts (fail-closed like the oracle: raises
    // when no outline or zero area).
    let mut min_x = Num::F(f64::INFINITY);
    let mut min_y = Num::F(f64::INFINITY);
    let mut max_x = Num::F(f64::NEG_INFINITY);
    let mut max_y = Num::F(f64::NEG_INFINITY);
    let mut found = false;
    for g in &raw.graphic_items {
        if g_layer(g) != "Edge.Cuts" {
            continue;
        }
        match g {
            RawGrItem::Poly { coords, .. } | RawGrItem::Curve { coords, .. } => {
                for p in coords {
                    min_x = Num::py_min(min_x, p.x);
                    max_x = Num::py_max(max_x, p.x);
                    min_y = Num::py_min(min_y, p.y);
                    max_y = Num::py_max(max_y, p.y);
                }
                if !coords.is_empty() {
                    found = true;
                }
            }
            RawGrItem::Rect { start, end, .. } | RawGrItem::TextBox { start, end, .. } => {
                for p in [start, end] {
                    min_x = Num::py_min(min_x, p.x);
                    max_x = Num::py_max(max_x, p.x);
                    min_y = Num::py_min(min_y, p.y);
                    max_y = Num::py_max(max_y, p.y);
                }
                found = true;
            }
            RawGrItem::Line { start, end, .. } => {
                min_x = Num::py_min(min_x, start.x);
                max_x = Num::py_max(max_x, start.x);
                min_x = Num::py_min(min_x, end.x);
                max_x = Num::py_max(max_x, end.x);
                min_y = Num::py_min(min_y, start.y);
                max_y = Num::py_max(max_y, start.y);
                min_y = Num::py_min(min_y, end.y);
                max_y = Num::py_max(max_y, end.y);
                found = true;
            }
            RawGrItem::Circle { center, end, .. } => {
                let cx = center.x.to_f64();
                let cy = center.y.to_f64();
                let ex = end.x.to_f64();
                let ey = end.y.to_f64();
                let r = ((ex - cx) * (ex - cx) + (ey - cy) * (ey - cy)).sqrt();
                min_x = Num::py_min(min_x, Num::F(cx - r));
                max_x = Num::py_max(max_x, Num::F(cx + r));
                min_y = Num::py_min(min_y, Num::F(cy - r));
                max_y = Num::py_max(max_y, Num::F(cy + r));
                found = true;
            }
            RawGrItem::Arc { start, mid, end, .. } => {
                for p in [start, mid, end] {
                    min_x = Num::py_min(min_x, p.x);
                    max_x = Num::py_max(max_x, p.x);
                    min_y = Num::py_min(min_y, p.y);
                    max_y = Num::py_max(max_y, p.y);
                }
                found = true;
            }
            RawGrItem::Text { .. } => {}
        }
    }
    if !found {
        return Err(PyValueError::new_err(
            "No Edge.Cuts geometry found in the board. Board dimensions cannot be determined — a valid PCB must have a board outline on the Edge.Cuts layer.",
        ));
    }
    let width = max_x.sub(&min_x);
    let height = max_y.sub(&min_y);
    if width.to_f64() <= 0.0 || height.to_f64() <= 0.0 {
        return Err(PyValueError::new_err(format!(
            "Edge.Cuts geometry degenerates to zero area (width={}, height={}). Board outline must define a non-zero rectangle.",
            num_to_string(width),
            num_to_string(height)
        )));
    }
    out.set_item("board_width", num_to_py(py, width)?)?;
    out.set_item("board_height", num_to_py(py, height)?)?;

    // pad sizes: {("ref", "num"): [w, h, shape]} -- matches the oracle's
    // `_extract_pad_sizes`, which SKIPS pads with an empty number.
    let pad_sizes = PyDict::new(py);
    for fp in &raw.footprints {
        let r#ref = fp.properties.iter().find(|(k, _)| k == "Reference").map(|(_, v)| v.clone()).unwrap_or_default();
        if r#ref.is_empty() {
            continue;
        }
        for pad in &fp.pads {
            let pad_num = pad.number.clone();
            if pad_num.is_empty() {
                continue;
            }
            let key = PyTuple::new(py, [r#ref.clone(), pad_num.clone()])?;
            // [pos_x, pos_y, w, h, shape] -- the pad POSITION is included so
            // the shim's courtyard fallback (pad bbox + margin) can reproduce
            // the oracle's Strategy-2 geometry exactly.
            let entry = PyList::empty(py);
            entry.append(num_to_py(py, pad.position.x)?)?;
            entry.append(num_to_py(py, pad.position.y)?)?;
            entry.append(num_to_py(py, pad.size.x)?)?;
            entry.append(num_to_py(py, pad.size.y)?)?;
            entry.append(if pad.shape.is_empty() { "rect" } else { pad.shape.as_str() })?;
            pad_sizes.set_item(key, entry)?;
        }
    }
    out.set_item("pad_sizes", pad_sizes)?;

    // Pad bbox inputs: {ref: [[x, y, w, h], ...]} over ALL pads (numbered
    // AND unnumbered). The oracle's courtyard Strategy-2 fallback iterates
    // `for pad in fp.pads:` with no number filter, so unnumbered pads must
    // reach the shim's pad-bbox fallback even though `pad_sizes` above
    // deliberately excludes them (the oracle's `_extract_pad_sizes` skips
    // empty pad numbers).
    let pad_bbox = PyDict::new(py);
    for fp in &raw.footprints {
        let r#ref = fp.properties.iter().find(|(k, _)| k == "Reference").map(|(_, v)| v.clone()).unwrap_or_default();
        if r#ref.is_empty() {
            continue;
        }
        let entries = PyList::empty(py);
        for pad in &fp.pads {
            let entry = PyList::empty(py);
            entry.append(num_to_py(py, pad.position.x)?)?;
            entry.append(num_to_py(py, pad.position.y)?)?;
            entry.append(num_to_py(py, pad.size.x)?)?;
            entry.append(num_to_py(py, pad.size.y)?)?;
            entries.append(entry)?;
        }
        pad_bbox.set_item(r#ref, entries)?;
    }
    out.set_item("pad_bbox_inputs", pad_bbox)?;

    // raw courtyard inputs: {ref: [{"kind": ..., ...}]}
    let courtyards = PyDict::new(py);
    for fp in &raw.footprints {
        let r#ref = fp.properties.iter().find(|(k, _)| k == "Reference").map(|(_, v)| v.clone()).unwrap_or_default();
        if r#ref.is_empty() {
            continue;
        }
        let mut shapes: Vec<Py<PyAny>> = Vec::new();
        for item in &fp.graphic_items {
            let layer = item.layer();
            if layer != "F.CrtYd" && layer != "B.CrtYd" {
                continue;
            }
            let shape = PyDict::new(py);
            match item {
                RawFpItem::Poly { coords, .. } => {
                    shape.set_item("kind", "poly")?;
                    let pts = PyList::empty(py);
                    for p in coords {
                        pts.append(PyTuple::new(py, [num_to_py(py, p.x)?, num_to_py(py, p.y)?])?)?;
                    }
                    shape.set_item("coords", pts)?;
                }
                RawFpItem::Circle { center, end, .. } => {
                    shape.set_item("kind", "circle")?;
                    shape.set_item("center", PyTuple::new(py, [num_to_py(py, center.x)?, num_to_py(py, center.y)?])?)?;
                    shape.set_item("end", PyTuple::new(py, [num_to_py(py, end.x)?, num_to_py(py, end.y)?])?)?;
                }
                RawFpItem::Rect { start, end, .. } => {
                    shape.set_item("kind", "rect")?;
                    shape.set_item("start", PyTuple::new(py, [num_to_py(py, start.x)?, num_to_py(py, start.y)?])?)?;
                    shape.set_item("end", PyTuple::new(py, [num_to_py(py, end.x)?, num_to_py(py, end.y)?])?)?;
                }
                RawFpItem::Line { start, end, .. } => {
                    shape.set_item("kind", "line")?;
                    shape.set_item("start", PyTuple::new(py, [num_to_py(py, start.x)?, num_to_py(py, start.y)?])?)?;
                    shape.set_item("end", PyTuple::new(py, [num_to_py(py, end.x)?, num_to_py(py, end.y)?])?)?;
                }
                RawFpItem::Arc { start, mid, end, .. } => {
                    shape.set_item("kind", "arc")?;
                    shape.set_item("start", PyTuple::new(py, [num_to_py(py, start.x)?, num_to_py(py, start.y)?])?)?;
                    shape.set_item("mid", PyTuple::new(py, [num_to_py(py, mid.x)?, num_to_py(py, mid.y)?])?)?;
                    shape.set_item("end", PyTuple::new(py, [num_to_py(py, end.x)?, num_to_py(py, end.y)?])?)?;
                }
                RawFpItem::Text { .. } | RawFpItem::TextBox { .. } | RawFpItem::Curve { .. } => {}
            }
            shapes.push(shape.into_any().unbind());
        }
        courtyards.set_item(r#ref, PyList::new(py, shapes.iter().map(|s| s.bind(py)))?)?;
    }
    out.set_item("courtyard_inputs", courtyards)?;
    out.into_any().unbind().into_py_any(py)
}

// ===========================================================================
// 8. registration
// ===========================================================================

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let sub = PyModule::new(module.py(), "parse_engine")?;
    sub.add_class::<TraceData>()?;
    sub.add_class::<PadData>()?;
    sub.add_class::<ViaData>()?;
    sub.add_class::<ParseResult>()?;
    sub.add_class::<DrillDefinition>()?;
    sub.add_class::<Position>()?;
    sub.add_function(wrap_pyfunction!(parse_kicad_pcb, &sub)?)?;
    sub.add_function(wrap_pyfunction!(extract_footprint_positions, &sub)?)?;
    sub.add_function(wrap_pyfunction!(extract_net_classes, &sub)?)?;
    sub.add_function(wrap_pyfunction!(extract_stackup_raw, &sub)?)?;
    sub.add_function(wrap_pyfunction!(extract_metadata_raw, &sub)?)?;
    sub.add_function(wrap_pyfunction!(tokenize, &sub)?)?;
    module.add_submodule(&sub)?;
    Ok(())
}


#[cfg(test)]
#[allow(clippy::expect_used)]
mod tests {
    use super::*;

    /// kiutils' num grammar: a decimal token whose float value is integral
    /// becomes an INT (`3.0` -> `3`) -- and the i64 range guard must not
    /// silently flip the branch (regression for `2i64.pow(63)` overflowing
    /// to i64::MIN in release, which turned every integral decimal into a
    /// float).
    #[test]
    fn decimal_integral_token_is_int() {
        let tree = parse_ki_document(
            r#"(pad "1" thru_hole circle (at 10 20 90.0) (size 3.0 3.0) (drill 1.5))"#,
        )
        .expect("this fixture is tokenizer-conformant; a parse failure must be loud, not a vacuous pass");
        let KiNode::List(items) = &tree[0] else {
            return;
        };
        let mut size_seen = false;
        let mut angle_seen = false;
        for item in items {
            let KiNode::List(sub) = item else { continue };
            let Some(KiNode::Atom(KiAtom::Bare(b))) = sub.first() else { continue };
            match b.as_str() {
                "size" => {
                    assert!(matches!(sub.get(1), Some(KiNode::Atom(KiAtom::Int(3)))));
                    assert!(matches!(sub.get(2), Some(KiNode::Atom(KiAtom::Int(3)))));
                    size_seen = true;
                }
                "drill" => {
                    assert!(matches!(sub.get(1), Some(KiNode::Atom(KiAtom::Float(v))) if *v == 1.5));
                }
                "at" => {
                    // `90.0` is an integral decimal -> int 90
                    assert!(matches!(sub.get(3), Some(KiNode::Atom(KiAtom::Int(90)))));
                    angle_seen = true;
                }
                _ => {}
            }
        }
        assert!(size_seen && angle_seen);
    }


    /// Single-pad nets must stay in the netlist registry (deliberate
    /// 2026-08-15 divergence from the pre-migration `len(pins) >= 2` drop --
    /// see `extract_nets_pure`'s docstring). A net with one pad still needs
    /// its net class assignment (DRC/DRU/safety) and must resolve in
    /// `Netlist.apply_net_class_mapping_strict`; routing excludes it via
    /// `_routable_net_names`, not by erasing it from the registry.
    #[test]
    fn extract_nets_pure_keeps_single_pad_nets() {
        fn pin(name: &str, net: &str) -> RawPinOut {
            RawPinOut {
                name: name.to_string(),
                number: name.to_string(),
                position: (Num::F(0.0), Num::F(0.0)),
                net: Some(net.to_string()),
                width: Num::F(1.0),
                height: Num::F(1.0),
                shape: "rect".to_string(),
                layer: "F.Cu".to_string(),
                drill: NumOrDrill::Num(Num::F(0.0)),
                is_pth: false,
                roundrect_ratio: Num::F(0.0),
                pad_rotation_deg: 0.0,
            }
        }
        fn comp(r#ref: &str, pins: Vec<RawPinOut>) -> CompOut {
            CompOut {
                r#ref: r#ref.to_string(),
                footprint: "R:R_0603".to_string(),
                bounds: (0.0, 0.0),
                pins,
                initial_position: (0.0, 0.0),
                fixed: false,
                initial_rotation_quadrant: 0,
                initial_side: 0,
                attributes: Vec::new(),
                sheetpath: None,
            }
        }
        let components = vec![
            comp("F1", vec![pin("1", "ac_l")]),
            comp("U1", vec![pin("1", "gnd"), pin("2", "gnd")]),
        ];
        let nets = extract_nets_pure(&components);
        let names: Vec<&str> = nets.iter().map(|(n, _)| n.as_str()).collect();
        assert_eq!(names, vec!["ac_l", "gnd"], "single-pad net must be retained");
        assert_eq!(nets[0].1, vec![("F1".to_string(), "1".to_string())]);
    }


    fn pos(x: f64, y: f64) -> RawPos {
        RawPos { x: Num::F(x), y: Num::F(y), angle: None, unlocked: false }
    }

    /// Regression for the bug this module was built to fix: a footprint
    /// whose ONLY graphic item is an `fp_circle` must produce bounds that
    /// cover that circle, not the `(2.0, 2.0)` empty-footprint fallback.
    /// Before the fix, `Circle` fell into `calculate_footprint_bounds`'s
    /// catch-all `_ => {}` arm exactly like `Line`/`Rect`/`Arc`/`TextBox`
    /// do NOT -- `has_valid` was never set, `gfx_bounds` came back `None`,
    /// and (with no pads either) the function returned the bare (2.0, 2.0)
    /// fallback instead of a box covering the circle.
    #[test]
    fn circle_only_courtyard_produces_circle_bounds() {
        let fp = RawFootprint {
            position: RawPos::origin(),
            layer: "F.Cu".to_string(),
            locked: false,
            lib_id: "Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn".to_string(),
            entry_name: "CP_Radial_D35.0mm_P10.00mm_SnapIn".to_string(),
            properties: vec![],
            pads: vec![],
            graphic_items: vec![RawFpItem::Circle {
                center: pos(5.0, 0.0),
                end: pos(22.75, 0.0),
                layer: "F.CrtYd".to_string(),
            }],
        };
        let (width, height) = calculate_footprint_bounds(&fp, 0.0, 0.0);
        // radius = |22.75 - 5| = 17.75 -> diameter (and the symmetric box
        // side, since center_offset is 0 and the circle is centred off-
        // origin at x=5) = 2 * max(|5-17.75|, |5+17.75|) = 2*22.75 = 45.5
        // in x; y is symmetric about 0 so 2*17.75 = 35.5.
        assert!((width - 45.5).abs() < 1e-9, "width={width}, expected 45.5");
        assert!((height - 35.5).abs() < 1e-9, "height={height}, expected 35.5");
    }

    /// The real `CP_Radial_D35.0mm_P10.00mm_SnapIn` footprint geometry used
    /// by C2/C3/C4/C5 on `pcb/temper.kicad_pcb`: an F.CrtYd circle (center
    /// 5,0 / end 22.75,0 -> radius 17.75, a 35.5mm-diameter courtyard), an
    /// F.Fab circle (center 5,0 / end 22.5,0), two short F.Fab line
    /// segments (a polarity mark), and two through-hole pads at (0,0) and
    /// (10,0) (4x4mm each). `center_offset` is threaded as the real pad
    /// centroid ((0+10)/2, (0+0)/2) = (5, 0) -- the same point
    /// `_extract_components_from_pcb`/`extract_components_pure` compute and
    /// pass, and coincidentally the same point the courtyard circles are
    /// centred on. With the circle dropped (pre-fix), bounds fell back to
    /// the tiny F.Fab polarity-mark line segments plus the two pads --
    /// on the order of 30mm x 19mm, NOT the 35.5mm the part actually
    /// occupies. This is the C2xC3 collision root cause quoted directly
    /// from the real board.
    #[test]
    fn real_cp_radial_d35_courtyard_matches_kicad_diameter() {
        let fp = RawFootprint {
            position: RawPos::origin(),
            layer: "F.Cu".to_string(),
            locked: false,
            lib_id: "Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn".to_string(),
            entry_name: "CP_Radial_D35.0mm_P10.00mm_SnapIn".to_string(),
            properties: vec![],
            pads: vec![
                RawPad {
                    number: "1".to_string(),
                    shape: "roundrect".to_string(),
                    position: pos(0.0, 0.0),
                    size: pos(4.0, 4.0),
                    drill: None,
                    layers: vec!["*.Cu".to_string()],
                    roundrect_ratio: None,
                    net: None,
                },
                RawPad {
                    number: "2".to_string(),
                    shape: "circle".to_string(),
                    position: pos(10.0, 0.0),
                    size: pos(4.0, 4.0),
                    drill: None,
                    layers: vec!["*.Cu".to_string()],
                    roundrect_ratio: None,
                    net: None,
                },
            ],
            graphic_items: vec![
                RawFpItem::Line {
                    start: pos(-10.065141, -7.6875),
                    end: pos(-6.565141, -7.6875),
                    layer: "F.Fab".to_string(),
                },
                RawFpItem::Line {
                    start: pos(-8.315141, -9.4375),
                    end: pos(-8.315141, -5.9375),
                    layer: "F.Fab".to_string(),
                },
                RawFpItem::Circle {
                    center: pos(5.0, 0.0),
                    end: pos(22.5, 0.0),
                    layer: "F.Fab".to_string(),
                },
                RawFpItem::Circle {
                    center: pos(5.0, 0.0),
                    end: pos(22.75, 0.0),
                    layer: "F.CrtYd".to_string(),
                },
            ],
        };
        // Pad centroid offset, exactly as `extract_components_pure` computes it.
        let (width, height) = calculate_footprint_bounds(&fp, 5.0, 0.0);
        assert!((width - 35.5).abs() < 1e-9, "width={width}, expected 35.5 (the part's real diameter)");
        assert!((height - 35.5).abs() < 1e-9, "height={height}, expected 35.5 (the part's real diameter)");
    }

    /// Same defect class, different shape: a footprint whose only
    /// courtyard/fab geometry is an `fp_poly` must have its vertices
    /// included in bounds. `Poly` fell into the same `_ => {}` catch-all
    /// as `Circle` (dropped silently, `has_valid` never set).
    #[test]
    fn poly_only_fab_outline_produces_poly_bounds() {
        let fp = RawFootprint {
            position: RawPos::origin(),
            layer: "F.Cu".to_string(),
            locked: false,
            lib_id: "Package_TO_SOT_SMD:SOT-23".to_string(),
            entry_name: "SOT-23".to_string(),
            properties: vec![],
            pads: vec![],
            graphic_items: vec![RawFpItem::Poly {
                coords: vec![pos(-1.4, -0.75), pos(1.4, -0.75), pos(1.4, 0.75), pos(-1.4, 0.75)],
                layer: "F.Fab".to_string(),
            }],
        };
        let (width, height) = calculate_footprint_bounds(&fp, 0.0, 0.0);
        assert!((width - 2.8).abs() < 1e-9, "width={width}, expected 2.8");
        assert!((height - 1.5).abs() < 1e-9, "height={height}, expected 1.5");
    }

    /// An empty `fp_poly` (zero vertices -- degenerate but not impossible
    /// from a hand-edited footprint) must not be treated as a valid bounds
    /// contributor; with no other geometry and no pads this falls through
    /// to the `(2.0, 2.0)` empty-footprint default, same as it would if the
    /// item were absent entirely.
    #[test]
    fn empty_poly_does_not_fake_valid_bounds() {
        let fp = RawFootprint {
            position: RawPos::origin(),
            layer: "F.Cu".to_string(),
            locked: false,
            lib_id: "Test:Empty".to_string(),
            entry_name: "Empty".to_string(),
            properties: vec![],
            pads: vec![],
            graphic_items: vec![RawFpItem::Poly { coords: vec![], layer: "F.Fab".to_string() }],
        };
        let (width, height) = calculate_footprint_bounds(&fp, 0.0, 0.0);
        assert!((width - 2.0).abs() < 1e-9, "width={width}, expected 2.0 fallback");
        assert!((height - 2.0).abs() < 1e-9, "height={height}, expected 2.0 fallback");
    }
}
