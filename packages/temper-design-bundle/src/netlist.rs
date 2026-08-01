//! Minimal KiCad netlist-export (`.net`) reader.
//!
//! Like `kicad_pcb.rs`, this extracts exactly one thing -- the set of
//! component reference designators -- from `(components (comp (ref "...")
//! ...) ...)` blocks. It exists because the versioned `AtopileExport` JSON
//! (`elec/exports/temper.design-input.v1.json`) is a hand-authored,
//! long-stale sample fixture (3 components), not a live artifact regenerated
//! from the real ~100-component design -- so it cannot be the netlist source
//! of truth for a real identity gate. Reading `elec/build/default.net`
//! natively keeps the gate's correctness independent of that unfinished
//! pipeline, consistent with the same choice made for `.kicad_pcb` reading.

use std::collections::HashSet;

use crate::error::DesignBundleError;
use crate::sexpr::{Sexpr, parse_document, unquote};

/// Returns true if `list` is a `(comp ...)` node.
fn is_comp_node(items: &[Sexpr]) -> bool {
    matches!(items.first(), Some(Sexpr::Atom(head)) if head == "comp")
}

/// Finds the `(ref "VALUE")` child of a `(comp ...)` node and returns its
/// unquoted value.
fn comp_reference(items: &[Sexpr]) -> Option<String> {
    for item in items {
        if let Sexpr::List(children) = item
            && children.len() >= 2
            && matches!(&children[0], Sexpr::Atom(head) if head == "ref")
            && let Sexpr::Atom(value) = &children[1]
        {
            return Some(unquote(value));
        }
    }
    None
}

fn collect_comp_refs(node: &Sexpr, refs: &mut HashSet<String>) {
    if let Sexpr::List(items) = node {
        if is_comp_node(items)
            && let Some(reference) = comp_reference(items)
        {
            refs.insert(reference);
        }
        for item in items {
            collect_comp_refs(item, refs);
        }
    }
}

/// Extracts the set of component reference designators from a KiCad netlist
/// export's (`.net`) raw text.
pub fn extract_component_references(
    netlist_text: &str,
) -> Result<HashSet<String>, DesignBundleError> {
    let root = parse_document(netlist_text, "netlist export")?;
    let mut refs = HashSet::new();
    collect_comp_refs(&root, &mut refs);
    Ok(refs)
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn extracts_refs_from_comp_blocks() {
        let doc = r#"
        (export (version "E")
          (components
            (comp (ref "U1")
              (value "?")
              (footprint "Fuse:Fuse_Holder_5x20mm"))
            (comp (ref "U2")
              (value "10k")
              (footprint "Resistor_SMD:R_0603_1608Metric")))
          (nets))
        "#;
        let refs = extract_component_references(doc).unwrap();
        assert_eq!(refs, HashSet::from(["U1".to_string(), "U2".to_string()]));
    }

    #[test]
    fn empty_document_is_an_error() {
        assert!(extract_component_references("").is_err());
    }

    #[test]
    fn netlist_with_no_components_returns_empty_set() {
        let doc = r#"(export (version "E") (components) (nets))"#;
        let refs = extract_component_references(doc).unwrap();
        assert!(refs.is_empty());
    }

    #[test]
    fn ignores_ref_like_fields_outside_comp_nodes() {
        let doc = r#"
        (export (version "E")
          (design (source "unknown"))
          (components
            (comp (ref "U1") (value "?"))))
        "#;
        let refs = extract_component_references(doc).unwrap();
        assert_eq!(refs, HashSet::from(["U1".to_string()]));
    }
}
