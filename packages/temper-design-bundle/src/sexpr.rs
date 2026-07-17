//! Minimal shared S-expression tokenizer/parser used by both the
//! `.kicad_pcb` reader (`kicad_pcb.rs`) and the KiCad netlist-export reader
//! (`netlist.rs`). Both formats are the same S-expression syntax; only the
//! top-level structure being walked differs, so the tokenizer/parser is
//! shared here rather than duplicated a second time in this crate.

use crate::error::DesignBundleError;

#[derive(Debug, Clone, PartialEq)]
pub(crate) enum Sexpr {
    Atom(String),
    List(Vec<Sexpr>),
}

fn tokenize(input: &str, format_name: &str) -> Result<Vec<String>, DesignBundleError> {
    let mut tokens = Vec::new();
    let bytes = input.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        let c = bytes[i] as char;
        if c.is_whitespace() {
            i += 1;
            continue;
        }
        if c == '(' || c == ')' {
            tokens.push(c.to_string());
            i += 1;
            continue;
        }
        if c == '"' {
            let start = i;
            i += 1;
            while i < bytes.len() {
                let cur = bytes[i] as char;
                if cur == '\\' && i + 1 < bytes.len() {
                    i += 2;
                    continue;
                }
                if cur == '"' {
                    i += 1;
                    break;
                }
                i += 1;
            }
            if i > bytes.len() || bytes[i - 1] as char != '"' {
                return Err(DesignBundleError::Document(format!(
                    "unterminated string literal in {format_name}"
                )));
            }
            tokens.push(input[start..i].to_string());
            continue;
        }
        let start = i;
        while i < bytes.len() {
            let cur = bytes[i] as char;
            if cur.is_whitespace() || cur == '(' || cur == ')' {
                break;
            }
            i += 1;
        }
        tokens.push(input[start..i].to_string());
    }
    Ok(tokens)
}

fn parse_expr(
    tokens: &[String],
    pos: &mut usize,
    format_name: &str,
) -> Result<Sexpr, DesignBundleError> {
    if *pos >= tokens.len() {
        return Err(DesignBundleError::Document(format!(
            "unexpected end of {format_name} input"
        )));
    }
    let tok = &tokens[*pos];
    if tok == "(" {
        *pos += 1;
        let mut items = Vec::new();
        loop {
            if *pos >= tokens.len() {
                return Err(DesignBundleError::Document(format!(
                    "unbalanced parentheses in {format_name}"
                )));
            }
            if tokens[*pos] == ")" {
                *pos += 1;
                break;
            }
            items.push(parse_expr(tokens, pos, format_name)?);
        }
        Ok(Sexpr::List(items))
    } else if tok == ")" {
        Err(DesignBundleError::Document(format!(
            "unexpected ')' in {format_name}"
        )))
    } else {
        *pos += 1;
        Ok(Sexpr::Atom(tok.clone()))
    }
}

pub(crate) fn unquote(atom: &str) -> String {
    if atom.len() >= 2 && atom.starts_with('"') && atom.ends_with('"') {
        atom[1..atom.len() - 1]
            .replace("\\\"", "\"")
            .replace("\\\\", "\\")
    } else {
        atom.to_string()
    }
}

/// Parses `text` as a single top-level S-expression document. `format_name`
/// is used only to make error messages name the right file format (e.g.
/// `.kicad_pcb` vs. netlist export).
pub(crate) fn parse_document(text: &str, format_name: &str) -> Result<Sexpr, DesignBundleError> {
    let tokens = tokenize(text, format_name)?;
    if tokens.is_empty() {
        return Err(DesignBundleError::Document(format!(
            "empty {format_name} document"
        )));
    }
    let mut pos = 0usize;
    parse_expr(&tokens, &mut pos, format_name)
}
