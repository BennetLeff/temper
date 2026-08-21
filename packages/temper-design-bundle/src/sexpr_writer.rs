//! S-expression writer for `.kicad_pcb` documents -- the inverse of the
//! kiutils-exact tokenizer in `parse_engine.rs`.
//!
//! Wave 4 Phase 3 (formats/IO): the parse engine builds a [`KiNode`] tree
//! that preserves the full document structure (every list, atom, string,
//! int and float token -- including kiutils' Str-vs-Bare distinction and the
//! verbatim `(offset ...)` drill sub-list quirk). A serializer over that
//! tree is therefore the inverse of the tokenizer: **parse -> write -> parse
//! is the identity on the tree by construction** (the D7 decision from the
//! Phase 3 plan -- re-parse parity is the acceptance criterion, not
//! byte-identical output).
//!
//! ## Why not write from `RawBoard`?
//!
//! `RawBoard` is a *lossy projection* of the tree (missing descr/tags/path/
//! uuid on footprints, missing FillSettings/net/priority/hatch on zones,
//! no TitleBlock at all). Writing from the tree avoids that projection
//! entirely: whatever the tokenizer preserved, the writer reproduces.
//!
//! ## Formatting conventions
//!
//! - 4 spaces per indentation level.
//! - A list's head atom and any following atoms share the opening line
//!   (`(kicad_pcb` then children; `(net 1 "+15V")` stays on one line);
//!   every subsequent item (nested list or atom) is placed on its own
//!   line; the closing paren sits on its own line at the list's indent.
//! - Strings are re-quoted with `"` escaped as `\"` (the tokenizer's only
//!   unescape direction, so the round trip is exact). Literal backslashes
//!   pass through unchanged -- the tokenizer only treats `\"` as an
//!   escape, so `\n` (backslash-n, KiCad's newline escape) stays two
//!   characters.
//! - Numbers: ints as decimal; floats ALWAYS in fixed notation rendered
//!   from the shortest round-trip digits ([`crate::parse_engine::shortest_digits`]).
//!   This deliberately diverges from CPython's `repr` outside the fixed
//!   range: a scientific token (`1e-05`, `1e+16`) is NOT a kiutils number
//!   token and would re-parse as a bare string, breaking re-parse parity.
//!   Inside `1e-4 <= |v| < 1e16` the output is byte-identical to
//!   `py_repr_f64`.
//!
//! ## Known round-trip limitations (none exercised by the corpus)
//!
//! - A `KiAtom::Str` whose content ends in a lone backslash cannot be
//!   re-emitted as a string token (kiutils' tokenizer would treat the
//!   `\"` as an escape and never find the closing quote). The corpus has
//!   zero such strings.
//! - A `KiAtom::Bare` that *looks* like a quoted string (a malformed
//!   `"..."` that failed string classification, e.g. `"R1"(`) is written
//!   verbatim, so a re-parse classifies it as a Str token with the same
//!   content. The Rust tree differs (Bare vs Str) but the Python-side
//!   `tokenize` trees are identical (Str and Bare both map to `str`).
//! - A `KiAtom::Bare` that *matches the numeric grammar* (e.g. the `5` of
//!   `5^0`, which tokenizes as Bare("5") because its next char is `^`, not
//!   space/`)`) cannot round-trip as Bare: kiutils' number-vs-string
//!   decision depends on the lookahead character, and a writer placing
//!   whitespace or `)` after the token forces number classification. The
//!   corpus contains no such token.
//! - NaN/±inf floats render as `nan`/`inf` bare tokens (not round-trip
//!   safe) -- unreachable from any parse, since the tokenizer never
//!   produces them.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::parse_engine::{
    parse_ki_document, shortest_digits, KiAtom, KiNode, Num,
};

/// A Python nested list (as produced by ``zone_sexpr_py``,
/// ``segment_sexpr_py`` etc.) → s-expression text.
///
/// The Bare/Str distinction uses a keyword heuristic: a string matching
/// ``^[a-z_][a-z0-9_]*$`` is emitted bare (unquoted), matching every
/// keyword token (``zone``, ``net``, ``layer``, ``none``, etc.); all
/// other strings are quoted (net names, layer names, UUIDs). This mirrors
/// kiutils' own ``Sexpr`` vs bare-token convention as observed in the
/// production board corpus.
fn py_sexpr_to_text(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<String> {
    use pyo3::types::PyList;

    // Try list first (most common for nested structures)
    if obj.is_instance_of::<PyList>() {
        let parts: Vec<String> = obj.try_iter()?
            .map(|item| py_sexpr_to_text(py, &item?))
            .collect::<PyResult<_>>()?;
        Ok(format!("({})", parts.join(" ")))
    } else if let Ok(b) = obj.extract::<bool>() {
        Ok(if b { "true".to_string() } else { "false".to_string() })
    } else if let Ok(i) = obj.extract::<i64>() {
        Ok(i.to_string())
    } else if let Ok(f) = obj.extract::<f64>() {
        Ok(render_float(f))
    } else if let Ok(s) = obj.extract::<String>() {
        if is_keyword_token(&s) {
            Ok(s)
        } else {
            Ok(render_str(&s))
        }
    } else {
        Ok(obj.str()?.to_string())
    }
}

fn is_keyword_token(s: &str) -> bool {
    if s.is_empty() {
        return false;
    }
    let bytes = s.as_bytes();
    if !bytes[0].is_ascii_lowercase() && bytes[0] != b'_' {
        return false;
    }
    bytes[1..].iter().all(|&b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
}

/// Render a single atom to its source token text.
fn render_atom(atom: &KiAtom) -> String {
    match atom {
        KiAtom::Str(s) => render_str(s),
        KiAtom::Bare(s) => s.clone(),
        KiAtom::Int(v) => v.to_string(),
        KiAtom::Float(v) => render_float(*v),
        // The verbatim `(offset ...)` drill sub-list quirk: kiutils stores
        // the whole sub-list as a drill diameter/width; write it back as a
        // list. `indent` is irrelevant for rendering (callers place it).
        KiAtom::List(items) => write_list(items, 0),
    }
}

/// Re-quote a string token. `"` becomes `\"` (the tokenizer's only
/// unescape); every other character -- including `\`, `(`, `)`, `^` --
/// passes through unchanged, which is exactly the inverse of the parse
/// side's `inner.replace("\\\"", "\"")`.
fn render_str(content: &str) -> String {
    let mut out = String::with_capacity(content.len() + 2);
    out.push('"');
    for ch in content.chars() {
        if ch == '"' {
            out.push('\\');
        }
        out.push(ch);
    }
    out.push('"');
    out
}

/// Render a float in kiutils-number-safe fixed notation, from the shortest
/// round-trip digits. Placing the decimal point at `exp + 1` reproduces the
/// value exactly; integral results get a trailing `.0` (which re-parses as
/// a Float -- never an Int -- because integral decimals only collapse to
/// Int inside i64 range, and an integral Float outside that range fails the
/// i64 guard in `classify_number`).
fn render_float(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    if v.is_infinite() {
        return if v < 0.0 { "-inf".to_string() } else { "inf".to_string() };
    }
    if v == 0.0 {
        // Float(-0.0) is unreachable from any parse (the tokenizer converts
        // every integral decimal -- including -0.0 -- to Int), but render
        // it the way py_repr_f64 would for consistency.
        return if v.is_sign_negative() { "-0.0".to_string() } else { "0.0".to_string() };
    }
    let (neg, digits, exp) = match shortest_digits(v) {
        Ok(t) => t,
        // `format!("{v:e}")` cannot fail for a finite non-zero f64; this
        // arm is unreachable in practice and only keeps the type honest.
        Err(e) => return format!("<repr-error:{e}>"),
    };
    let point_pos = exp + 1;
    let mut out = String::new();
    if neg {
        out.push('-');
    }
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
    out
}

/// Render a [`KiNode`] at the given indentation level. Atoms render as
/// their token text; lists render multi-line (see the module doc).
pub(crate) fn write_ki_node(node: &KiNode, indent: usize) -> String {
    match node {
        KiNode::Atom(a) => render_atom(a),
        KiNode::List(items) => write_list(items, indent),
    }
}

fn write_list(items: &[KiNode], indent: usize) -> String {
    if items.is_empty() {
        return "()".to_string();
    }
    let mut out = String::from("(");
    out.push_str(&write_ki_node(&items[0], indent + 1));
    let mut idx = 1;
    // Leading atoms share the head line (e.g. `(net 1 "+15V")`, or the
    // `(kicad_pcb (version ...) ...)` header when those tokens are atoms).
    while idx < items.len() {
        if let KiNode::Atom(a) = &items[idx] {
            out.push(' ');
            out.push_str(&render_atom(a));
            idx += 1;
        } else {
            break;
        }
    }
    if idx < items.len() {
        for item in &items[idx..] {
            out.push('\n');
            push_indent(&mut out, indent + 1);
            out.push_str(&write_ki_node(item, indent + 1));
        }
        out.push('\n');
        push_indent(&mut out, indent);
    }
    out.push(')');
    out
}

fn push_indent(out: &mut String, indent: usize) {
    for _ in 0..indent {
        out.push_str("    ");
    }
}

/// Serialize a full parsed `.kicad_pcb` document (the `Vec<KiNode>` from
/// [`parse_ki_document`]) back to text: every top-level node rendered at
/// indent 0, joined with newlines, terminated by a trailing newline.
pub(crate) fn write_board_document(nodes: &[KiNode]) -> String {
    let mut out = String::new();
    for (i, node) in nodes.iter().enumerate() {
        if i > 0 {
            out.push('\n');
        }
        out.push_str(&write_ki_node(node, 0));
    }
    out.push('\n');
    out
}

fn is_list_with_head(node: &KiNode, head: &str) -> bool {
    match node {
        KiNode::List(items) => matches!(
            items.first(),
            Some(KiNode::Atom(KiAtom::Bare(b))) if b == head
        ),
        _ => false,
    }
}

/// Build a fresh `(title_block (comment SLOT "text"))` list.
fn make_title_block(slot: usize, text: &str) -> KiNode {
    let comment = KiNode::List(vec![
        KiNode::Atom(KiAtom::Bare("comment".to_string())),
        KiNode::Atom(KiAtom::Int(slot as i64)),
        KiNode::Atom(KiAtom::Str(text.to_string())),
    ]);
    KiNode::List(vec![
        KiNode::Atom(KiAtom::Bare("title_block".to_string())),
        comment,
    ])
}

/// Set comment `slot` to `text` inside an existing `(title_block ...)`
/// list: overwrite the `(comment SLOT ...)` entry when present, otherwise
/// append one.
fn set_title_block_comment(tb_items: &mut Vec<KiNode>, slot: usize, text: &str) {
    let new_comment = KiNode::List(vec![
        KiNode::Atom(KiAtom::Bare("comment".to_string())),
        KiNode::Atom(KiAtom::Int(slot as i64)),
        KiNode::Atom(KiAtom::Str(text.to_string())),
    ]);
    for item in tb_items.iter_mut() {
        let KiNode::List(comment_items) = item else { continue };
        let head_matches = matches!(
            comment_items.first(),
            Some(KiNode::Atom(KiAtom::Bare(b))) if b == "comment"
        );
        if head_matches
            && matches!(comment_items.get(1), Some(KiNode::Atom(KiAtom::Int(v))) if *v == slot as i64)
        {
            *item = new_comment;
            return;
        }
    }
    tb_items.push(new_comment);
}

/// Embed a numbered title-block comment into a parsed document tree:
/// overwrite `(comment SLOT ...)` when the board already has a
/// `(title_block ...)`, otherwise create the title_block and insert it
/// after `(paper ...)` if present, else after `(general ...)`, else right
/// after the root head. Returns an error (fail closed) when the document
/// has no `(kicad_pcb ...)` root list.
pub(crate) fn embed_title_block_comment(
    nodes: &mut [KiNode],
    slot: usize,
    text: &str,
) -> Result<(), String> {
    let root = nodes.first_mut().ok_or_else(|| "empty document".to_string())?;
    let KiNode::List(root_items) = root else {
        return Err("document root is not a list".to_string());
    };
    let root_is_pcb = matches!(
        root_items.first(),
        Some(KiNode::Atom(KiAtom::Bare(b))) if b == "kicad_pcb"
    );
    if !root_is_pcb {
        return Err("document root is not a (kicad_pcb ...) list".to_string());
    }
    match root_items.iter().position(|n| is_list_with_head(n, "title_block")) {
        Some(i) => {
            let KiNode::List(tb_items) = &mut root_items[i] else {
                return Err("title_block is not a list".to_string());
            };
            set_title_block_comment(tb_items, slot, text);
        }
        None => {
            let title_block = make_title_block(slot, text);
            let insert_at = root_items
                .iter()
                .position(|n| is_list_with_head(n, "paper"))
                .map(|i| i + 1)
                .or_else(|| {
                    root_items
                        .iter()
                        .position(|n| is_list_with_head(n, "general"))
                        .map(|i| i + 1)
                })
                .unwrap_or(1);
            let insert_at = insert_at.min(root_items.len());
            root_items.insert(insert_at, title_block);
        }
    }
    Ok(())
}

/// Parse raw `.kicad_pcb` text with the kiutils-exact tokenizer, serialize
/// the resulting tree back to text. Re-parsing the result yields the same
/// tree (D7 re-parse parity); the bytes need not match the input (the
/// tokenizer already normalized whitespace/carets/integral decimals).
#[pyfunction]
pub fn write_board_sexpr_py(content: &str) -> PyResult<String> {
    let nodes = parse_ki_document(content).map_err(PyValueError::new_err)?;
    Ok(write_board_document(&nodes))
}

/// Parse raw `.kicad_pcb` text, append one or more s-expression items
/// (as Python nested lists — the output of ``zone_sexpr_py``,
/// ``segment_sexpr_py`` etc.) to the root ``(kicad_pcb ...)`` list, and
/// serialize the mutated tree back to text. Each item is a Python list
/// like ``["zone", ["net", 2], ...]``. Items are appended before the
/// root's closing paren — where KiCad expects new items.
/// Fails closed (ValueError) if the board text fails to parse, or if
/// the document root is not a ``(kicad_pcb ...)`` list.
#[pyfunction]
pub fn append_items_to_board_py(
    py: Python<'_>,
    content: &str,
    item_sexprs: Vec<Py<PyAny>>,
) -> PyResult<String> {
    let mut nodes = parse_ki_document(content).map_err(PyValueError::new_err)?;
    let root = nodes.first_mut().ok_or_else(|| {
        PyValueError::new_err("empty document — no root node")
    })?;
    let KiNode::List(root_items) = root else {
        return Err(PyValueError::new_err(
            "document root is not a list",
        ));
    };
    let root_is_pcb = matches!(
        root_items.first(),
        Some(KiNode::Atom(KiAtom::Bare(b))) if b == "kicad_pcb"
    );
    if !root_is_pcb {
        return Err(PyValueError::new_err(
            "document root is not a (kicad_pcb ...) list",
        ));
    };
    for item_obj in &item_sexprs {
        let item_text = py_sexpr_to_text(py, item_obj.bind(py))?;
        let item_nodes =
            parse_ki_document(&item_text).map_err(PyValueError::new_err)?;
        for item_node in item_nodes {
            root_items.push(item_node);
        }
    }
    Ok(write_board_document(&nodes))
}

/// Parse raw `.kicad_pcb` text and extract the `{net_name: net_index}`
/// mapping from all `(net N "name")` entries in the root list.
/// Returns a Python dict. Fails closed (ValueError) if the text is not
/// parseable.
#[pyfunction]
pub fn extract_net_map_from_text_py(
    py: Python<'_>,
    content: &str,
) -> PyResult<Py<PyAny>> {
    use pyo3::types::PyDict;
    let nodes = parse_ki_document(content).map_err(PyValueError::new_err)?;
    let out = PyDict::new(py);
    for node in &nodes {
        let KiNode::List(items) = node else { continue };
        let head = match items.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) if b == "kicad_pcb" => b.as_str(),
            _ => continue,
        };
        let _ = head; // confirmed root
        for child in items {
            let KiNode::List(sub) = child else { continue };
            let first = match sub.first() {
                Some(KiNode::Atom(KiAtom::Bare(b))) if b == "net" => b.as_str(),
                _ => continue,
            };
            let _ = first;
            // (net N "name") — N is the index, "name" is the net name
            let Some(KiNode::Atom(num_atom)) = sub.get(1) else {
                continue;
            };
            let Some(KiNode::Atom(name_atom)) = sub.get(2) else {
                continue;
            };
            let num_val: i64 = match num_atom {
                KiAtom::Int(v) => *v,
                KiAtom::Float(v) => *v as i64,
                _ => continue,
            };
            let name_val: &str = match name_atom {
                KiAtom::Str(s) => s.as_str(),
                KiAtom::Bare(s) => s.as_str(),
                _ => continue,
            };
            out.set_item(name_val, num_val)?;
        }
    }
    Ok(out.into_any().unbind())
}

/// Parse raw `.kicad_pcb` text, set title-block comment `slot` to `text`
/// (creating the title_block when absent), and serialize the mutated tree
/// back to text. The provenance-embedding kernel behind
/// `temper_placer.io.provenance.embed_provenance`.
#[pyfunction]
pub fn embed_title_block_comment_py(content: &str, slot: usize, text: &str) -> PyResult<String> {
    let mut nodes = parse_ki_document(content).map_err(PyValueError::new_err)?;
    embed_title_block_comment(&mut nodes, slot, text).map_err(PyValueError::new_err)?;
    Ok(write_board_document(&nodes))
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use std::path::Path;

    use super::*;

    fn round_trips(input: &str) -> (Vec<KiNode>, Vec<KiNode>, String) {
        let tree = parse_ki_document(input).expect("fixture must parse");
        let out = write_board_document(&tree);
        let tree2 = parse_ki_document(&out).expect("written text must re-parse");
        (tree, tree2, out)
    }

    fn assert_round_trip(input: &str) -> String {
        let (tree, tree2, out) = round_trips(input);
        assert_eq!(tree, tree2, "round trip changed the tree");
        // Idempotence: writing the written text is a fixed point.
        let out2 = write_board_document(&tree2);
        assert_eq!(out, out2, "writer is not idempotent");
        out
    }

    #[test]
    fn simple_board_round_trips() {
        let out = assert_round_trip(
            "(kicad_pcb (version 20211014) (generator kiutils)\n\
             \x20 (general (thickness 1.6))\n\
             \x20 (net 1 \"+15V\")\n\
             \x20 (segment (start 96.95 252.45) (end 96.9875 252.54) (width 0.2) (layer \"In3.Cu\") (net 92))\n\
             )",
        );
        // The writer's own format: head line then children, 4-space indent.
        assert!(out.starts_with("(kicad_pcb\n    (version 20211014)"));
        assert!(out.contains("\n    (net 1 \"+15V\")\n"));
        assert!(out.trim_end().ends_with(')'));
    }

    #[test]
    fn integral_decimal_collapses_to_int_and_round_trips() {
        // `5.0` and `90.0` tokenize to Int; the writer emits `5` / `90`;
        // re-parsing gives the same Int tokens (tree equality, not bytes).
        let out = assert_round_trip(
            r#"(pad "1" thru_hole circle (at 10 20 90.0) (size 3.0 3.0) (drill 1.5))"#,
        );
        assert!(out.contains("(at 10 20 90)"));
        assert!(out.contains("(size 3 3)"));
        assert!(out.contains("(drill 1.5)"));
    }

    #[test]
    fn float_fixed_range_matches_py_repr() {
        assert_eq!(render_float(96.95), "96.95");
        assert_eq!(render_float(0.2), "0.2");
        assert_eq!(render_float(4.5), "4.5");
        assert_eq!(render_float(0.035), "0.035");
        assert_eq!(render_float(1e-4), "0.0001");
        assert_eq!(render_float(999999.99), "999999.99");
    }

    #[test]
    fn float_scientific_range_stays_number_tokens() {
        // Outside CPython's fixed range the writer must still emit a token
        // that re-classifies as a number (a scientific token would re-parse
        // as a Bare string).
        assert_eq!(render_float(1e-5), "0.00001");
        assert_eq!(render_float(-1.5e20), "-150000000000000000000.0");
        assert_eq!(render_float(1.5e-8), "0.000000015");
        let out = assert_round_trip("(x 0.00001 1.0000000000000002e16)");
        // `1.0000000000000002e16` is NOT a kiutils number token, so it
        // parsed as a Bare string and must come back verbatim as Bare;
        // `0.00001` parsed as Float(1e-5) and is re-rendered fixed.
        assert!(out.contains("0.00001"), "float token re-rendered fixed");
    }

    #[test]
    fn string_quote_escaping_round_trips() {
        let out = assert_round_trip(r#"(descr "a \"quoted\" bit")"#);
        assert!(out.contains(r#"(descr "a \"quoted\" bit")"#));
    }

    #[test]
    fn string_backslash_sequences_round_trips() {
        // `\n` (backslash-n) is NOT an escape the tokenizer processes; it
        // must survive verbatim. Trailing-backslash content is the one
        // documented non-round-trippable case -- not tested here (absent
        // from the corpus).
        let out = assert_round_trip(r#"(text "LINE1\nLINE2" (at 0 0))"#);
        assert!(out.contains(r#""LINE1\nLINE2""#));
        let out = assert_round_trip(r#"(text "back\\slash" (at 0 0))"#);
        assert!(out.contains(r#""back\\slash""#));
    }

    #[test]
    fn caret_outside_string_is_dropped_consistently() {
        // `a^b` tokenizes as Bare("a"), Bare("b") (the caret is skipped);
        // the writer emits `a b`, which re-parses to the same two Bare
        // tokens. NOTE: a caret-split NUMERIC token (`5^0` -> Bare("5"),
        // Int(0)) is deliberately NOT used here -- Bare("5") re-classifies
        // as Int(5) when written followed by a space (kiutils' number
        // classification depends on the next char, which the writer cannot
        // control). That corner is a documented round-trip limitation; the
        // corpus contains no such token.
        let out = assert_round_trip("(x a^b)");
        assert!(out.contains("(x a b)"));
    }

    #[test]
    fn drill_offset_quirk_sub_list_round_trips() {
        // A drill carrying only `(offset ...)` stores the sub-list verbatim
        // in the RawBoard projection's diameter; in the KiNode tree it is
        // simply a nested list, which the writer emits back as a list (on
        // its own indented line, like every nested child).
        let out = assert_round_trip("(pad \"1\" thru_hole circle (drill (offset 0 1)))");
        assert!(out.contains("(drill\n        (offset 0 1)\n    )"));
    }

    #[test]
    fn empty_and_atom_only_documents() {
        let out = assert_round_trip("()");
        assert_eq!(out, "()\n");
        // A bare-atom document is not a real board but must still round-trip.
        let out = assert_round_trip("hello");
        assert_eq!(out, "hello\n");
    }

    #[test]
    fn embed_comment_creates_title_block() {
        let mut nodes = parse_ki_document(
            "(kicad_pcb (version 20211014) (general (thickness 1.6)) (paper \"A4\"))",
        )
        .unwrap();
        embed_title_block_comment(&mut nodes, 9, "provenance: board=abc").unwrap();
        let out = write_board_document(&nodes);
        assert!(out.contains("(title_block\n        (comment 9 \"provenance: board=abc\")\n    )"));
        // The inserted title_block must sit right after (paper ...).
        let paper_pos = out.find("(paper \"A4\")").unwrap();
        let tb_pos = out.find("title_block").unwrap();
        assert!(tb_pos > paper_pos);
        // Re-parse parity holds after the mutation.
        let tree2 = parse_ki_document(&out).unwrap();
        assert_eq!(nodes, tree2);
    }

    #[test]
    fn embed_comment_overwrites_existing_slot() {
        let mut nodes = parse_ki_document(
            "(kicad_pcb (title_block (title \"T\")\n (comment 9 \"old\") (comment 2 \"keep\")))",
        )
        .unwrap();
        embed_title_block_comment(&mut nodes, 9, "new").unwrap();
        let out = write_board_document(&nodes);
        assert!(!out.contains("\"old\""));
        assert!(out.contains("(comment 9 \"new\")"));
        assert!(out.contains("(comment 2 \"keep\")"));
        assert!(out.contains("(title \"T\")"));
        let tree2 = parse_ki_document(&out).unwrap();
        assert_eq!(nodes, tree2);
    }

    #[test]
    fn embed_comment_fails_closed_on_non_pcb_document() {
        let mut nodes = parse_ki_document("(not_a_board (x 1))").unwrap();
        assert!(embed_title_block_comment(&mut nodes, 9, "x").is_err());
    }

    /// The acceptance fixture: the production board. Parse -> write ->
    /// parse must be the identity on the tree, and write must be a fixed
    /// point.
    #[test]
    fn production_board_round_trips() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../pcb/temper.kicad_pcb");
        let text = std::fs::read_to_string(&path)
            .expect("pcb/temper.kicad_pcb must be present for the round-trip test");
        let (tree, tree2, out) = round_trips(&text);
        assert_eq!(tree, tree2, "production board round trip changed the tree");
        let out2 = write_board_document(&tree2);
        assert_eq!(out, out2, "production board write is not a fixed point");
    }
}
