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
use std::collections::BTreeSet;

use crate::parse_engine::{
    parse_ki_document, shortest_digits, KiAtom, KiNode,
};

/// Find the `(at ...)` sub-node within a list of KiNodes (footprint or pad
/// children). Returns the index and a mutable reference to the at-list.
fn find_at_node_mut(items: &mut [KiNode]) -> Option<usize> {
    for (i, item) in items.iter().enumerate() {
        if let KiNode::List(sub) = item
            && matches!(
                sub.first(),
                Some(KiNode::Atom(KiAtom::Bare(b))) if b == "at"
            )
        {
            return Some(i);
        }
    }
    None
}

/// Find the `(property "Reference" "ref")` sub-node within a footprint's
/// children. Returns the reference string.
fn find_reference(items: &[KiNode]) -> Option<String> {
    for item in items {
        let KiNode::List(sub) = item else { continue };
        let head = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) if b == "property" => b.as_str(),
            _ => continue,
        };
        let _ = head;
        // (property "Reference" "R1") — index 1 is key, index 2 is value
        if let Some(KiNode::Atom(KiAtom::Str(key))) = sub.get(1)
            && key == "Reference"
            && let Some(KiNode::Atom(KiAtom::Str(val))) = sub.get(2)
        {
            return Some(val.clone());
        }
    }
    None
}

/// Read the angle from an `(at X Y [angle])` node. Returns 0.0 if absent.
fn read_at_angle(at_items: &[KiNode]) -> f64 {
    if at_items.len() >= 4
        && let Some(KiNode::Atom(a)) = at_items.get(3)
    {
        return match a {
            KiAtom::Int(v) => *v as f64,
            KiAtom::Float(v) => *v,
            _ => 0.0,
        };
    }
    0.0
}

/// Convert an f64 to a KiAtom, using Int for integral values (matching
/// the tokenizer's integral-decimal-collapse behavior).
fn num_to_atom(v: f64) -> KiAtom {
    if v == v.trunc() && v >= i64::MIN as f64 && v < i64::MAX as f64 {
        KiAtom::Int(v as i64)
    } else {
        KiAtom::Float(v)
    }
}

fn atom_f64(atom: &KiAtom) -> Option<f64> {
    match atom {
        KiAtom::Int(v) => Some(*v as f64),
        KiAtom::Float(v) => Some(*v),
        _ => None,
    }
}

fn atom_text(atom: &KiAtom) -> Option<&str> {
    match atom {
        KiAtom::Str(v) | KiAtom::Bare(v) => Some(v),
        _ => None,
    }
}

fn list_head(items: &[KiNode]) -> Option<&str> {
    match items.first() {
        Some(KiNode::Atom(KiAtom::Bare(v))) => Some(v),
        _ => None,
    }
}

fn child_list<'a>(items: &'a [KiNode], head: &str) -> Option<&'a [KiNode]> {
    items.iter().find_map(|item| {
        let KiNode::List(sub) = item else { return None };
        (list_head(sub) == Some(head)).then_some(sub.as_slice())
    })
}

fn child_list_mut<'a>(items: &'a mut [KiNode], head: &str) -> Option<&'a mut Vec<KiNode>> {
    items.iter_mut().find_map(|item| {
        let KiNode::List(sub) = item else { return None };
        (list_head(sub) == Some(head)).then_some(sub)
    })
}

fn child_text<'a>(items: &'a [KiNode], head: &str) -> Option<&'a str> {
    let sub = child_list(items, head)?;
    let KiNode::Atom(atom) = sub.get(1)? else { return None };
    atom_text(atom)
}

fn child_number(items: &[KiNode], head: &str) -> Option<f64> {
    let sub = child_list(items, head)?;
    let KiNode::Atom(atom) = sub.get(1)? else { return None };
    atom_f64(atom)
}

fn child_point(items: &[KiNode], head: &str) -> Option<(f64, f64)> {
    let sub = child_list(items, head)?;
    let KiNode::Atom(x) = sub.get(1)? else { return None };
    let KiNode::Atom(y) = sub.get(2)? else { return None };
    Some((atom_f64(x)?, atom_f64(y)?))
}

fn child_texts(items: &[KiNode], head: &str) -> Option<Vec<String>> {
    child_list(items, head)?
        .iter()
        .skip(1)
        .map(|node| {
            let KiNode::Atom(atom) = node else { return None };
            atom_text(atom).map(str::to_string)
        })
        .collect()
}

type FootprintPadAnchor = ((f64, f64), Vec<String>, i64);

fn footprint_pad_anchor(
    footprint: &[KiNode],
    pad_number: &str,
) -> Result<FootprintPadAnchor, String> {
    let origin = child_point(footprint, "at")
        .ok_or_else(|| "moving footprint has no numeric at".to_string())?;
    let angle = child_list(footprint, "at").map(read_at_angle).unwrap_or(0.0);
    let mut matches = Vec::new();
    for item in footprint {
        let KiNode::List(pad) = item else { continue };
        if list_head(pad) != Some("pad") {
            continue;
        }
        let number = pad.get(1).and_then(|node| {
            let KiNode::Atom(atom) = node else { return None };
            atom_text(atom)
        });
        if number != Some(pad_number) {
            continue;
        }
        let local = child_point(pad, "at")
            .ok_or_else(|| format!("moving pad {pad_number} has no numeric at"))?;
        let layers = child_texts(pad, "layers")
            .ok_or_else(|| format!("moving pad {pad_number} has no layers"))?;
        let net = child_number(pad, "net")
            .ok_or_else(|| format!("moving pad {pad_number} has no numeric net"))?;
        if net.fract() != 0.0 {
            return Err(format!("moving pad {pad_number} net is not integral"));
        }
        let rotated = temper_geometry::kicad_transform::rotate_local_to_world_deg(
            local.0, local.1, angle,
        );
        matches.push((
            (origin.0 + rotated.0, origin.1 + rotated.1),
            layers,
            net as i64,
        ));
    }
    match matches.as_slice() {
        [one] => Ok(one.clone()),
        rows => Err(format!("expected one moving pad {pad_number}, found {}", rows.len())),
    }
}

fn approx_point(a: (f64, f64), b: (f64, f64)) -> bool {
    (a.0 - b.0).abs() <= 1e-9 && (a.1 - b.1).abs() <= 1e-9
}

fn block_span(text: &str, start: usize) -> Result<(usize, usize), String> {
    let bytes = text.as_bytes();
    let mut depth = 0usize;
    let mut quoted = false;
    let mut escaped = false;
    for (offset, byte) in bytes[start..].iter().enumerate() {
        if quoted {
            if escaped {
                escaped = false;
            } else if *byte == b'\\' {
                escaped = true;
            } else if *byte == b'"' {
                quoted = false;
            }
            continue;
        }
        match *byte {
            b'"' => quoted = true,
            b'(' => depth += 1,
            b')' => {
                if depth == 0 {
                    return Err("closing parenthesis precedes block start".into());
                }
                depth -= 1;
                if depth == 0 {
                    return Ok((start, start + offset + 1));
                }
            }
            _ => {}
        }
    }
    Err(format!("unbalanced s-expression block at byte {start}"))
}

fn span_for_marker(text: &str, head: &str, marker: &str) -> Result<(usize, usize), String> {
    let marker_at = text
        .find(marker)
        .ok_or_else(|| format!("declared identity not found: {marker}"))?;
    if text[marker_at + marker.len()..].contains(marker) {
        return Err(format!("declared identity is duplicated: {marker}"));
    }
    let needle = format!("({head}");
    let start = text[..marker_at]
        .rfind(&needle)
        .ok_or_else(|| format!("{head} block start not found for {marker}"))?;
    block_span(text, start)
}

/// Replace one embedded footprint block while preserving every unrelated byte.
pub fn replace_footprint_block_by_reference(
    content: &str,
    reference: &str,
    replacement_block: &str,
) -> Result<String, String> {
    let replacement_nodes = parse_ki_document(replacement_block)?;
    let [KiNode::List(replacement)] = replacement_nodes.as_slice() else {
        return Err("replacement must contain exactly one footprint block".into());
    };
    if list_head(replacement) != Some("footprint") {
        return Err("replacement root is not a footprint".into());
    }
    if find_reference(replacement).as_deref() != Some(reference) {
        return Err(format!("replacement footprint is not {reference}"));
    }
    let marker = format!("(property \"Reference\" \"{reference}\")");
    let (start, end) = span_for_marker(content, "footprint", &marker)?;
    let mut output = content.to_string();
    output.replace_range(start..end, replacement_block);
    parse_ki_document(&output)?;
    Ok(output)
}

#[pyfunction]
pub fn replace_footprint_block_by_reference_py(
    content: &str,
    reference: &str,
    replacement_block: &str,
) -> PyResult<String> {
    replace_footprint_block_by_reference(content, reference, replacement_block)
        .map_err(PyValueError::new_err)
}

fn mutate_point_with_shear(
    items: &mut [KiNode],
    head: &str,
    fixed_endpoint: (f64, f64),
    moving_endpoint: (f64, f64),
    east_shift_mm: f64,
) -> Result<(), String> {
    let point = child_list_mut(items, head)
        .ok_or_else(|| format!("route item has no ({head} ...) point"))?;
    let KiNode::Atom(x_atom) = point.get(1).ok_or_else(|| format!("{head} has no x"))? else {
        return Err(format!("{head} x is not numeric"));
    };
    let KiNode::Atom(y_atom) = point.get(2).ok_or_else(|| format!("{head} has no y"))? else {
        return Err(format!("{head} y is not numeric"));
    };
    let x = atom_f64(x_atom).ok_or_else(|| format!("{head} x is not numeric"))?;
    let y = atom_f64(y_atom).ok_or_else(|| format!("{head} y is not numeric"))?;
    let dy = moving_endpoint.1 - fixed_endpoint.1;
    if dy.abs() <= 1e-9 {
        return Err("fixed and moving endpoints must have different y coordinates".into());
    }
    let factor = (y - fixed_endpoint.1) / dy;
    if !(-1e-9..=1.0 + 1e-9).contains(&factor) {
        return Err(format!("{head} point lies outside the declared route span"));
    }
    point[1] = KiNode::Atom(num_to_atom(x + east_shift_mm * factor.clamp(0.0, 1.0)));
    Ok(())
}

/// Atomically move one footprint and its complete declared route chain.
///
/// Validation happens on the full parsed board before any output is
/// returned. Only the footprint and route blocks named by identity are
/// reserialized; every byte outside those blocks is copied verbatim.
#[allow(clippy::too_many_arguments)]
pub fn replace_declared_route_and_move_footprint(
    content: &str,
    footprint_ref: &str,
    route_net: i64,
    route_layer: &str,
    route_width_mm: f64,
    fixed_endpoint: (f64, f64),
    moving_via_tstamp: &str,
    moving_pad_number: &str,
    moving_via_size_mm: f64,
    moving_via_drill_mm: f64,
    segment_tstamps: &[String],
    east_shift_mm: f64,
) -> Result<String, String> {
    if !route_width_mm.is_finite() || route_width_mm <= 0.0 {
        return Err("route width must be finite and positive".into());
    }
    if !east_shift_mm.is_finite() || east_shift_mm <= 0.0 {
        return Err("east shift must be finite and positive".into());
    }
    if !moving_via_size_mm.is_finite() || moving_via_size_mm <= 0.0
        || !moving_via_drill_mm.is_finite() || moving_via_drill_mm <= 0.0
        || moving_via_drill_mm >= moving_via_size_mm
    {
        return Err("moving via size/drill declaration is invalid".into());
    }
    let declared: BTreeSet<_> = segment_tstamps.iter().cloned().collect();
    if declared.len() != segment_tstamps.len() || declared.is_empty() {
        return Err("segment tstamp declaration must be non-empty and unique".into());
    }

    let nodes = parse_ki_document(content)?;
    let root_items = nodes
        .iter()
        .find_map(|node| {
            let KiNode::List(items) = node else { return None };
            (list_head(items) == Some("kicad_pcb")).then_some(items.as_slice())
        })
        .ok_or_else(|| "document root is not a (kicad_pcb ...) list".to_string())?;

    let mut footprint_count = 0usize;
    let mut actual_segments = BTreeSet::new();
    let mut route_edges = Vec::new();
    let mut moving_endpoint = None;
    let mut moving_via_layers = None;
    let mut moving_pad = None;
    let mut fixed_seen = false;

    for item in root_items {
        let KiNode::List(items) = item else { continue };
        match list_head(items) {
            Some("footprint") if find_reference(items).as_deref() == Some(footprint_ref) => {
                footprint_count += 1;
                moving_pad = Some(footprint_pad_anchor(items, moving_pad_number)?);
            }
            Some("segment") if child_number(items, "net") == Some(route_net as f64) => {
                if child_text(items, "layer") != Some(route_layer) {
                    continue;
                }
                let width = child_number(items, "width")
                    .ok_or_else(|| "declared route segment has no numeric width".to_string())?;
                if (width - route_width_mm).abs() > 1e-9 {
                    return Err(format!(
                        "declared route segment width {width} does not match {route_width_mm}"
                    ));
                }
                let stamp = child_text(items, "tstamp")
                    .ok_or_else(|| "declared route segment has no tstamp".to_string())?
                    .to_string();
                if !declared.contains(&stamp) {
                    return Err(format!(
                        "undeclared segment on net {route_net}/{route_layer}: {stamp}"
                    ));
                }
                if !actual_segments.insert(stamp.clone()) {
                    return Err(format!("duplicate segment identity: {stamp}"));
                }
                let start = child_point(items, "start")
                    .ok_or_else(|| format!("segment {stamp} has no start"))?;
                let end = child_point(items, "end")
                    .ok_or_else(|| format!("segment {stamp} has no end"))?;
                fixed_seen |= approx_point(start, fixed_endpoint) || approx_point(end, fixed_endpoint);
                route_edges.push((stamp, start, end));
            }
            Some("via")
                if child_number(items, "net") == Some(route_net as f64)
                    && child_text(items, "tstamp") == Some(moving_via_tstamp) =>
            {
                if moving_endpoint.is_some() {
                    return Err(format!("duplicate moving via identity: {moving_via_tstamp}"));
                }
                moving_endpoint = child_point(items, "at");
                let size = child_number(items, "size")
                    .ok_or_else(|| "moving via has no numeric size".to_string())?;
                let drill = child_number(items, "drill")
                    .ok_or_else(|| "moving via has no numeric drill".to_string())?;
                if (size - moving_via_size_mm).abs() > 1e-9
                    || (drill - moving_via_drill_mm).abs() > 1e-9
                {
                    return Err(format!(
                        "moving via size/drill {size}/{drill} does not match {moving_via_size_mm}/{moving_via_drill_mm}"
                    ));
                }
                moving_via_layers = child_texts(items, "layers");
            }
            _ => {}
        }
    }
    if footprint_count != 1 {
        return Err(format!("expected one footprint {footprint_ref}, found {footprint_count}"));
    }
    if actual_segments != declared {
        let missing: Vec<_> = declared.difference(&actual_segments).cloned().collect();
        return Err(format!("declared segment identity missing from route: {missing:?}"));
    }
    let moving_endpoint = moving_endpoint
        .ok_or_else(|| format!("moving via identity not found: {moving_via_tstamp}"))?;
    let via_layers = moving_via_layers
        .ok_or_else(|| "moving via has no layer span".to_string())?;
    let (pad_anchor, pad_layers, pad_net) = moving_pad
        .ok_or_else(|| format!("moving pad {footprint_ref}.{moving_pad_number} not found"))?;
    if pad_net != route_net {
        return Err(format!("moving pad net {pad_net} does not match route net {route_net}"));
    }
    if !approx_point(pad_anchor, moving_endpoint) {
        return Err(format!(
            "moving via is not co-located with pad {footprint_ref}.{moving_pad_number}"
        ));
    }
    if !via_layers.iter().any(|layer| layer == route_layer) {
        return Err(format!("moving via layer span omits route layer {route_layer}"));
    }
    let pad_copper_layers: Vec<_> = pad_layers
        .iter()
        .filter(|layer| layer.as_str() == "*.Cu" || layer.ends_with(".Cu"))
        .collect();
    if pad_copper_layers.is_empty()
        || (!pad_copper_layers.iter().any(|layer| layer.as_str() == "*.Cu")
            && !pad_copper_layers
                .iter()
                .any(|layer| via_layers.iter().any(|via| via == *layer)))
    {
        return Err(format!(
            "moving via layer span does not reach pad {footprint_ref}.{moving_pad_number} copper"
        ));
    }

    let mut reachable = vec![fixed_endpoint];
    let mut connected = vec![false; route_edges.len()];
    loop {
        let mut progress = false;
        for (index, (_, start, end)) in route_edges.iter().enumerate() {
            if connected[index] {
                continue;
            }
            if reachable
                .iter()
                .any(|point| approx_point(*point, *start) || approx_point(*point, *end))
            {
                connected[index] = true;
                reachable.extend([*start, *end]);
                progress = true;
            }
        }
        if !progress {
            break;
        }
    }
    let disconnected: Vec<_> = route_edges
        .iter()
        .zip(&connected)
        .filter_map(|((stamp, _, _), is_connected)| (!is_connected).then_some(stamp.clone()))
        .collect();
    if !disconnected.is_empty() {
        return Err(format!(
            "declared route is not one continuous graph from the fixed endpoint: {disconnected:?}"
        ));
    }
    let moving_seen = reachable.iter().any(|point| approx_point(*point, moving_endpoint));
    if !fixed_seen || !moving_seen {
        return Err("declared chain does not connect both fixed endpoint and moving via".into());
    }

    let mut replacements: Vec<(usize, usize, String)> = Vec::new();
    let fp_marker = format!("(property \"Reference\" \"{footprint_ref}\")");
    let (start, end) = span_for_marker(content, "footprint", &fp_marker)?;
    let mut fp_nodes = parse_ki_document(&content[start..end])?;
    let KiNode::List(fp_items) = fp_nodes
        .first_mut()
        .ok_or_else(|| "empty footprint block".to_string())?
    else {
        return Err("footprint block is not a list".into());
    };
    let at = child_list_mut(fp_items, "at")
        .ok_or_else(|| format!("footprint {footprint_ref} has no at"))?;
    let KiNode::Atom(x_atom) = at.get(1).ok_or_else(|| "footprint at has no x".to_string())? else {
        return Err("footprint x is not numeric".into());
    };
    let x = atom_f64(x_atom).ok_or_else(|| "footprint x is not numeric".to_string())?;
    at[1] = KiNode::Atom(num_to_atom(x + east_shift_mm));
    replacements.push((start, end, write_ki_node(&fp_nodes[0], 0)));

    for stamp in segment_tstamps {
        let marker = format!("(tstamp {stamp})");
        let (start, end) = span_for_marker(content, "segment", &marker)?;
        let mut segment_nodes = parse_ki_document(&content[start..end])?;
        let KiNode::List(items) = segment_nodes
            .first_mut()
            .ok_or_else(|| "empty segment block".to_string())?
        else {
            return Err("segment block is not a list".into());
        };
        mutate_point_with_shear(items, "start", fixed_endpoint, moving_endpoint, east_shift_mm)?;
        mutate_point_with_shear(items, "end", fixed_endpoint, moving_endpoint, east_shift_mm)?;
        replacements.push((start, end, write_ki_node(&segment_nodes[0], 0)));
    }

    let via_marker = format!("(tstamp {moving_via_tstamp})");
    let (start, end) = span_for_marker(content, "via", &via_marker)?;
    let mut via_nodes = parse_ki_document(&content[start..end])?;
    let KiNode::List(items) = via_nodes
        .first_mut()
        .ok_or_else(|| "empty via block".to_string())?
    else {
        return Err("via block is not a list".into());
    };
    let at = child_list_mut(items, "at").ok_or_else(|| "moving via has no at".to_string())?;
    let KiNode::Atom(x_atom) = at.get(1).ok_or_else(|| "via at has no x".to_string())? else {
        return Err("via x is not numeric".into());
    };
    let x = atom_f64(x_atom).ok_or_else(|| "via x is not numeric".to_string())?;
    at[1] = KiNode::Atom(num_to_atom(x + east_shift_mm));
    replacements.push((start, end, write_ki_node(&via_nodes[0], 0)));

    replacements.sort_by_key(|(start, _, _)| *start);
    for pair in replacements.windows(2) {
        if pair[0].1 > pair[1].0 {
            return Err("declared mutation blocks overlap".into());
        }
    }
    let mut output = content.to_string();
    for (start, end, replacement) in replacements.into_iter().rev() {
        output.replace_range(start..end, &replacement);
    }
    parse_ki_document(&output)?;
    Ok(output)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn replace_declared_route_and_move_footprint_py(
    content: &str,
    footprint_ref: &str,
    route_net: i64,
    route_layer: &str,
    route_width_mm: f64,
    fixed_endpoint: (f64, f64),
    moving_via_tstamp: &str,
    moving_pad_number: &str,
    moving_via_size_mm: f64,
    moving_via_drill_mm: f64,
    segment_tstamps: Vec<String>,
    east_shift_mm: f64,
) -> PyResult<String> {
    replace_declared_route_and_move_footprint(
        content,
        footprint_ref,
        route_net,
        route_layer,
        route_width_mm,
        fixed_endpoint,
        moving_via_tstamp,
        moving_pad_number,
        moving_via_size_mm,
        moving_via_drill_mm,
        &segment_tstamps,
        east_shift_mm,
    )
    .map_err(PyValueError::new_err)
}

/// Update an `(at X Y [angle])` node's X, Y, and angle values.
fn update_at_node(at_items: &mut Vec<KiNode>, x: f64, y: f64, angle: f64) {
    // Set X (index 1) and Y (index 2)
    if at_items.len() >= 3 {
        at_items[1] = KiNode::Atom(num_to_atom(x));
        at_items[2] = KiNode::Atom(num_to_atom(y));
    }
    // Set angle (index 3): update if present, append if not
    if at_items.len() >= 4 {
        at_items[3] = KiNode::Atom(num_to_atom(angle));
    } else {
        at_items.push(KiNode::Atom(num_to_atom(angle)));
    }
}

/// Update a pad's angle within its `(at lx ly [angle])` sub-node.
fn update_pad_angle(pad_items: &mut [KiNode], new_angle: f64) {
    // Find the (at ...) sub-node within the pad
    if let Some(idx) = find_at_node_mut(pad_items) {
        let KiNode::List(at_items) = &mut pad_items[idx] else {
            return;
        };
        // If angle is present (index 3), update it; else append
        if at_items.len() >= 4 {
            at_items[3] = KiNode::Atom(num_to_atom(new_angle));
        } else {
            at_items.push(KiNode::Atom(num_to_atom(new_angle)));
        }
    }
}

/// Read a pad's angle from its `(at lx ly [angle])` sub-node.
fn read_pad_angle(pad_items: &[KiNode]) -> f64 {
    for item in pad_items {
        let KiNode::List(sub) = item else { continue };
        let head = match sub.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) if b == "at" => b.as_str(),
            _ => continue,
        };
        let _ = head;
        return read_at_angle(sub);
    }
    0.0
}

/// Reorient pad angles: new_pad_angle = old_pad_angle + delta.
/// Uses the same logic as `reorient_pad_angles_py`.
fn reorient_pad_angle(old_angle: f64, delta: f64) -> f64 {
    let new_angle = old_angle + delta;
    // Normalize to [0, 360)
    let normalized = new_angle.rem_euclid(360.0);
    // If the result is a whole number, render as int (matches the Rust
    // writer's integral-decimal collapse)
    // Whole-number and fractional results render identically here; the
    // branch the original port carried was dead and is collapsed.
    normalized
}

/// Parse raw `.kicad_pcb` text, update footprint positions and pad angles
/// for the given placements, and serialize the mutated tree back to text.
///
/// Each placement is a tuple ``(ref, x, y, new_angle)``. For each footprint
/// matching `ref`, the `(at X Y angle)` node is updated, and every pad's
/// angle is reoriented by `new_angle - old_angle` (preserving each pad's
/// intrinsic orientation relative to its parent). Fails closed if the
/// document is not a valid `(kicad_pcb ...)` list.
#[pyfunction]
pub fn update_footprint_positions_py(
    content: &str,
    placements: Vec<(String, f64, f64, f64)>,
) -> PyResult<String> {
    let mut nodes = parse_ki_document(content).map_err(PyValueError::new_err)?;
    let root = nodes.first_mut().ok_or_else(|| {
        PyValueError::new_err("empty document — no root node")
    })?;
    let KiNode::List(root_items) = root else {
        return Err(PyValueError::new_err("document root is not a list"));
    };

    for item in root_items.iter_mut() {
        let KiNode::List(fp_items) = item else { continue };
        let head = match fp_items.first() {
            Some(KiNode::Atom(KiAtom::Bare(b))) if b == "footprint" => b.as_str(),
            _ => continue,
        };
        let _ = head;

        // Find the reference for this footprint
        let ref_str = match find_reference(fp_items) {
            Some(r) => r,
            None => continue,
        };

        // Check if this footprint has a placement
        let placement = placements.iter().find(|(r, _, _, _)| *r == ref_str);
        let Some((_, new_x, new_y, new_angle)) = placement else {
            continue;
        };
        let new_x = *new_x;
        let new_y = *new_y;
        let new_angle = *new_angle;

        // Find and update the (at ...) node, reading the old angle
        let at_idx = match find_at_node_mut(fp_items) {
            Some(i) => i,
            None => continue,
        };

        // Read old angle before mutating
        let old_angle = {
            let KiNode::List(at_items) = &fp_items[at_idx] else { continue };
            read_at_angle(at_items)
        };

        let delta = new_angle - old_angle;

        // Update the at node
        if let KiNode::List(at_items) = &mut fp_items[at_idx] {
            update_at_node(at_items, new_x, new_y, new_angle);
        }

        // Reorient pad angles if delta is not a multiple of 360
        if delta.rem_euclid(360.0) != 0.0 {
            for fp_item in fp_items.iter_mut() {
                let KiNode::List(pad_items) = fp_item else { continue };
                let is_pad = matches!(
                    pad_items.first(),
                    Some(KiNode::Atom(KiAtom::Bare(b))) if b == "pad"
                );
                if !is_pad {
                    continue;
                }
                let old_pad_angle = read_pad_angle(pad_items);
                let new_pad_angle = reorient_pad_angle(old_pad_angle, delta);
                update_pad_angle(pad_items, new_pad_angle);
            }
        }
    }

    Ok(write_board_document(&nodes))
}

/// A Python nested list (as produced by ``zone_sexpr_py``,
/// ``segment_sexpr_py`` etc.) → s-expression text.
///
/// The Bare/Str distinction uses a keyword heuristic: a string matching
/// ``^[a-z_][a-z0-9_]*$`` is emitted bare (unquoted), matching every
/// keyword token (``zone``, ``net``, ``layer``, ``none``, etc.); all
/// other strings are quoted (net names, layer names, UUIDs). This mirrors
/// kiutils' own ``Sexpr`` vs bare-token convention as observed in the
/// production board corpus.
fn py_sexpr_to_text(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<String> {
    use pyo3::types::PyList;

    // Try list first (most common for nested structures)
    if obj.is_instance_of::<PyList>() {
        let parts: Vec<String> = obj.try_iter()?
            .map(|item| py_sexpr_to_text(_py, &item?))
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

    const ROUTE_FIXTURE: &str = r#"(kicad_pcb
  (net 41 "discharge.r_snub1-p2")
  (footprint "R" (layer "F.Cu")
    (at 118.64 249.56 270)
    (property "Reference" "R14")
    (pad "2" smd circle (at 2.9625 0) (size 2 2) (layers "F.Cu" "F.Mask") (net 41 "discharge.r_snub1-p2")))
  (gr_text "KEEP EXACT" (at 1 2) (layer "F.SilkS"))
  (segment (start 112 218) (end 114 235) (width 5) (layer "In3.Cu") (net 41) (tstamp 11111111-1111-1111-1111-111111111111))
  (segment (start 114 235) (end 118.64 252.5225) (width 5) (layer "In3.Cu") (net 41) (tstamp 22222222-2222-2222-2222-222222222222))
  (via (at 118.64 252.5225) (size 2) (drill 1) (layers "In3.Cu" "F.Cu") (net 41) (tstamp 33333333-3333-3333-3333-333333333333))
)"#;

    #[test]
    fn declared_route_move_is_atomic_and_preserves_unrelated_bytes() {
        let output = replace_declared_route_and_move_footprint(
            ROUTE_FIXTURE,
            "R14",
            41,
            "In3.Cu",
            5.0,
            (112.0, 218.0),
            "33333333-3333-3333-3333-333333333333",
            "2", 2.0, 1.0,
            &[
                "11111111-1111-1111-1111-111111111111".into(),
                "22222222-2222-2222-2222-222222222222".into(),
            ],
            4.0,
        )
        .expect("declared chain is valid");
        assert!(output.contains("(at 122.64 249.56 270)"));
        assert!(output.contains("(at 122.64 252.5225)"));
        assert!(output.contains("(start 112 218)"));
        assert!(output.contains("  (gr_text \"KEEP EXACT\" (at 1 2) (layer \"F.SilkS\"))\n"));
    }

    #[test]
    fn declared_route_move_rejects_stale_or_partial_identity() {
        let err = replace_declared_route_and_move_footprint(
            ROUTE_FIXTURE,
            "R14",
            41,
            "In3.Cu",
            5.0,
            (112.0, 218.0),
            "33333333-3333-3333-3333-333333333333",
            "2", 2.0, 1.0,
            &["11111111-1111-1111-1111-111111111111".into()],
            4.0,
        )
        .expect_err("omitting a chain segment must fail closed");
        assert!(err.contains("undeclared segment"));
    }

    #[test]
    fn declared_route_move_rejects_disconnected_declared_segment() {
        let fixture = ROUTE_FIXTURE.replace(
            "  (via (at 118.64 252.5225)",
            "  (segment (start 10 10) (end 11 11) (width 5) (layer \"In3.Cu\") (net 41) (tstamp 44444444-4444-4444-4444-444444444444))\n  (via (at 118.64 252.5225)",
        );
        let err = replace_declared_route_and_move_footprint(
            &fixture,
            "R14",
            41,
            "In3.Cu",
            5.0,
            (112.0, 218.0),
            "33333333-3333-3333-3333-333333333333",
            "2", 2.0, 1.0,
            &[
                "11111111-1111-1111-1111-111111111111".into(),
                "22222222-2222-2222-2222-222222222222".into(),
                "44444444-4444-4444-4444-444444444444".into(),
            ],
            4.0,
        )
        .expect_err("a disconnected declared segment must fail closed");
        assert!(err.contains("not one continuous graph"));
    }

    #[test]
    fn declared_route_move_rejects_via_disconnected_from_named_pad() {
        let fixture = ROUTE_FIXTURE.replace("(at 118.64 249.56 270)", "(at 119.64 249.56 270)");
        let err = replace_declared_route_and_move_footprint(
            &fixture, "R14", 41, "In3.Cu", 5.0, (112.0, 218.0),
            "33333333-3333-3333-3333-333333333333", "2", 2.0, 1.0,
            &["11111111-1111-1111-1111-111111111111".into(),
              "22222222-2222-2222-2222-222222222222".into()], 4.0,
        ).expect_err("the selected via must terminate at the named pad");
        assert!(err.contains("not co-located with pad R14.2"));
    }

    #[test]
    fn declared_route_move_rejects_wrong_via_layer_span() {
        let fixture = ROUTE_FIXTURE.replace(
            "(layers \"In3.Cu\" \"F.Cu\")", "(layers \"In3.Cu\" \"In4.Cu\")",
        );
        let err = replace_declared_route_and_move_footprint(
            &fixture, "R14", 41, "In3.Cu", 5.0, (112.0, 218.0),
            "33333333-3333-3333-3333-333333333333", "2", 2.0, 1.0,
            &["11111111-1111-1111-1111-111111111111".into(),
              "22222222-2222-2222-2222-222222222222".into()], 4.0,
        ).expect_err("the via must reach the selected pad copper layer");
        assert!(err.contains("does not reach pad R14.2 copper"));
    }
}
