//! Minimal `.kicad_pcb` reader.
//!
//! This is deliberately not a general KiCad S-expression parser: it extracts
//! exactly one thing -- the set of footprint reference designators present
//! on a board -- because that is all `identity::validate_board_identity`
//! needs to compare against the netlist's component refs. Parsing natively in
//! Rust (rather than depending on a Python-generated DTO crossing the PyO3
//! boundary) keeps the identity gate self-contained: its correctness never
//! depends on a second language's extraction step being correct or present.

use std::collections::HashSet;

use crate::error::DesignBundleError;
use crate::sexpr::{Sexpr, parse_document, unquote};

/// Returns true if `list` is a `(footprint ...)` node.
fn is_footprint_node(items: &[Sexpr]) -> bool {
    matches!(items.first(), Some(Sexpr::Atom(head)) if head == "footprint")
}

/// Finds the `(property "Reference" "VALUE")` child of a footprint node and
/// returns its unquoted value.
fn footprint_reference(items: &[Sexpr]) -> Option<String> {
    for item in items {
        if let Sexpr::List(children) = item
            && children.len() >= 3
            && matches!(&children[0], Sexpr::Atom(head) if head == "property")
            && let Sexpr::Atom(name) = &children[1]
            && unquote(name) == "Reference"
            && let Sexpr::Atom(value) = &children[2]
        {
            return Some(unquote(value));
        }
    }
    None
}

fn collect_footprint_refs(node: &Sexpr, refs: &mut HashSet<String>) {
    if let Sexpr::List(items) = node {
        if is_footprint_node(items)
            && let Some(reference) = footprint_reference(items)
        {
            refs.insert(reference);
        }
        for item in items {
            collect_footprint_refs(item, refs);
        }
    }
}

/// Extracts the set of footprint reference designators from a `.kicad_pcb`
/// document's raw text.
pub fn extract_footprint_references(pcb_text: &str) -> Result<HashSet<String>, DesignBundleError> {
    let root = parse_document(pcb_text, ".kicad_pcb")?;
    let mut refs = HashSet::new();
    collect_footprint_refs(&root, &mut refs);
    Ok(refs)
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn extracts_references_from_footprint_blocks() {
        let doc = r#"
        (kicad_pcb (version 1)
          (footprint "Resistor_SMD:R_0603" (layer "F.Cu")
            (property "Reference" "U1")
            (property "Value" "10k")
          )
          (footprint "Capacitor_SMD:C_0603" (layer "F.Cu")
            (property "Reference" "U2")
          )
        )
        "#;
        let refs = extract_footprint_references(doc).unwrap();
        assert_eq!(refs.len(), 2);
        assert!(refs.contains("U1"));
        assert!(refs.contains("U2"));
    }

    #[test]
    fn ignores_non_footprint_nodes_with_similarly_shaped_properties() {
        let doc = r#"
        (kicad_pcb (version 1)
          (setup (property "Reference" "not_a_footprint"))
          (footprint "Fuse:Fuse_Holder" (layer "F.Cu")
            (property "Reference" "U1")
          )
        )
        "#;
        let refs = extract_footprint_references(doc).unwrap();
        assert_eq!(refs, HashSet::from(["U1".to_string()]));
    }

    #[test]
    fn empty_document_is_an_error() {
        assert!(extract_footprint_references("").is_err());
    }

    #[test]
    fn unbalanced_parens_is_an_error() {
        assert!(extract_footprint_references("(kicad_pcb (footprint").is_err());
    }

    #[test]
    fn escaped_quotes_in_string_atoms_are_handled() {
        let doc = r#"(kicad_pcb (footprint "lib:name" (property "Reference" "U1") (descr "a \"quoted\" thing")))"#;
        let refs = extract_footprint_references(doc).unwrap();
        assert_eq!(refs, HashSet::from(["U1".to_string()]));
    }

    #[test]
    fn board_with_no_footprints_returns_empty_set() {
        let doc = "(kicad_pcb (version 1) (general (thickness 1.6)))";
        let refs = extract_footprint_references(doc).unwrap();
        assert!(refs.is_empty());
    }
}
