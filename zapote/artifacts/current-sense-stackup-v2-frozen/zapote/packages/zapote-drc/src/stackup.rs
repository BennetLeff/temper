//! Physical stackup checks over the actual KiCad document, reusable across units.
//! KiCad's total includes copper, dielectric and solder mask (not paste/silk).
//! This is a nominal CAD consistency check, not a fabricator thickness tolerance.
use crate::donor_sexpr::{parse_document, unquote, Sexpr};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use zapote_core::{CheckReport, Finding};

pub const RULE: &str = "DRC.BOARD.STACKUP";
const ROUNDING_MM: f64 = 0.000001;

fn list(node: &Sexpr) -> Result<&[Sexpr], String> {
    match node {
        Sexpr::List(items) => Ok(items),
        _ => Err("expected S-expression list".into()),
    }
}
fn atom(node: Option<&Sexpr>) -> Result<String, String> {
    match node {
        Some(Sexpr::Atom(text)) => Ok(unquote(text)),
        _ => Err("expected scalar field".into()),
    }
}
fn children<'a>(node: &'a Sexpr, key: &str) -> Result<Vec<&'a Sexpr>, String> {
    Ok(list(node)?
        .iter()
        .filter(|item| match item {
            Sexpr::List(items) => atom(items.first()).is_ok_and(|name| name == key),
            _ => false,
        })
        .collect())
}
fn one<'a>(node: &'a Sexpr, key: &str) -> Result<&'a Sexpr, String> {
    let matches = children(node, key)?;
    if matches.len() != 1 {
        return Err(format!(
            "requires exactly one {key} field; found {}",
            matches.len()
        ));
    }
    Ok(matches[0])
}
fn scalar(node: &Sexpr, key: &str) -> Result<String, String> {
    atom(list(one(node, key)?)?.get(1))
}
fn thickness(node: &Sexpr, positive: bool) -> Result<f64, String> {
    let value: f64 = scalar(node, "thickness")?
        .parse()
        .map_err(|_| "malformed thickness".to_owned())?;
    if !value.is_finite() || value < 0.0 || (positive && value == 0.0) {
        return Err(format!(
            "thickness must be finite and {}; found {value} mm",
            if positive { "positive" } else { "nonnegative" }
        ));
    }
    Ok(value)
}

fn inspect(text: &str) -> Result<String, String> {
    let board = parse_document(text, "KiCad PCB")?;
    if atom(list(&board)?.first())? != "kicad_pcb" {
        return Err("expected kicad_pcb document".into());
    }
    let total = thickness(one(&board, "general")?, true)?;
    let declarations = one(&board, "layers")?;
    let mut declared = Vec::new();
    for node in list(declarations)?.iter().skip(1) {
        let fields = list(node)?;
        let name = atom(fields.get(1))?;
        if name.ends_with(".Cu") {
            declared.push(name);
        }
    }
    if declared.len() < 2 || declared.iter().collect::<BTreeSet<_>>().len() != declared.len() {
        return Err("requires distinct declared copper layers".into());
    }
    let stackup = one(one(&board, "setup")?, "stackup")?;
    let mut names = BTreeSet::new();
    let mut copper = Vec::new();
    let mut physical = Vec::new();
    let mut sum = 0.0;
    for layer in children(stackup, "layer")? {
        let name = atom(list(layer)?.get(1))?;
        if !names.insert(name.clone()) {
            return Err(format!("duplicate stackup layer {name}"));
        }
        let kind = scalar(layer, "type")?;
        let is_copper = kind == "copper";
        let is_dielectric = matches!(kind.as_str(), "core" | "prepreg");
        let is_mask = matches!(name.as_str(), "F.Mask" | "B.Mask");
        if is_copper || is_dielectric || is_mask {
            if is_copper && !name.ends_with(".Cu")
                || is_dielectric && !name.starts_with("dielectric ")
            {
                return Err(format!("stackup layer {name} has inconsistent type {kind}"));
            }
            let t = thickness(layer, !is_mask).map_err(|error| format!("{name}: {error}"))?;
            sum += t;
            if is_copper {
                copper.push(name);
            }
            if !is_mask {
                physical.push(is_copper);
            }
        } else if !matches!(name.as_str(), "F.SilkS" | "B.SilkS" | "F.Paste" | "B.Paste") {
            return Err(format!("unsupported stackup layer {name} type {kind}"));
        }
    }
    if copper != declared {
        return Err(format!(
            "stackup copper order {copper:?} differs from declared {declared:?}"
        ));
    }
    if physical.len() != 2 * copper.len() - 1
        || physical
            .iter()
            .enumerate()
            .any(|(i, copper)| *copper != (i % 2 == 0))
    {
        return Err("each adjacent copper layer pair requires a positive dielectric layer".into());
    }
    if !sum.is_finite() || (sum - total).abs() > ROUNDING_MM {
        return Err(format!("stackup sum {sum:.6} mm differs from general thickness {total:.6} mm (rounding allowance {ROUNDING_MM} mm)"));
    }
    Ok(format!(
        "{} copper layers; copper + dielectric + mask = {sum:.6} mm, declared {total:.6} mm",
        copper.len()
    ))
}

/// Validate a complete native board document; absence or ambiguity fails closed.
pub fn validate_board(text: &str) -> CheckReport {
    report(inspect(text))
}

/// Require byte-bound board evidence in the native export before inspecting it.
pub fn validate_native_export(export: &str, expected_board_sha256: &str) -> CheckReport {
    let result = (|| {
        let value: serde_json::Value = serde_json::from_str(export).map_err(|e| e.to_string())?;
        let text = value["board_file_utf8"]
            .as_str()
            .ok_or("native export requires board_file_utf8 for physical stackup validation")?;
        let actual = format!("{:x}", Sha256::digest(text.as_bytes()));
        if actual != expected_board_sha256
            || value["board_sha256"].as_str() != Some(actual.as_str())
        {
            return Err("stackup board bytes do not match the native board SHA256".into());
        }
        inspect(text)
    })();
    report(result)
}
fn report(result: Result<String, String>) -> CheckReport {
    let finding = match result {
        Ok(message) => Finding::pass(RULE, message, "board.setup.stackup"),
        Err(message) => Finding::fail(RULE, message, "board.setup.stackup"),
    };
    CheckReport::from_findings(vec![finding], vec![RULE.into()], vec![])
}

#[cfg(test)]
mod tests {
    use super::*;
    const BEFORE: &str =
        include_str!("../../../current-sense/evidence/stackup-fix/before.kicad_pcb");
    fn fixed() -> String {
        BEFORE.replacen("(thickness 0)", "(thickness 1.44)", 1)
    }
    fn passes(text: &str) -> bool {
        validate_board(text).status == zapote_core::Status::Pass
    }
    #[test]
    fn native_zero_core_is_rejected() {
        assert!(!passes(BEFORE));
    }
    #[test]
    fn physical_total_includes_mask() {
        assert!(passes(&fixed()));
    }
    #[test]
    fn missing_and_invalid_thicknesses_fail_closed() {
        for value in ["0", "-1", "NaN", "inf", "1.46", "bogus"] {
            assert!(
                !passes(&fixed().replacen("(thickness 1.44)", &format!("(thickness {value})"), 1)),
                "{value}"
            );
        }
        assert!(!passes(&fixed().replacen("(thickness 1.44)", "", 1)));
        assert!(!passes(&fixed().replacen(
            "(thickness 1.6)",
            "(thickness 0)",
            1
        )));
    }
    #[test]
    fn missing_stackup_or_copper_cannot_pass() {
        assert!(!passes(&fixed().replacen(
            "(stackup",
            "(ignored_stackup",
            1
        )));
        assert!(!passes(&fixed().replacen(
            "(layer \"B.Cu\"",
            "(layer \"In1.Cu\"",
            1
        )));
        assert!(!passes(&fixed().replacen(
            "(type \"core\")",
            "(type \"unknown\")",
            1
        )));
    }
    #[test]
    fn duplicate_fields_and_trailing_documents_are_rejected() {
        assert!(!passes(&fixed().replacen(
            "(thickness 1.44)",
            "(thickness 1.44) (thickness 1.44)",
            1
        )));
        assert!(!passes(&(fixed() + "(kicad_pcb)")));
    }
    #[test]
    fn string_contents_cannot_spoof_structural_fields() {
        assert!(passes(&fixed().replacen(
            "(paper \"A4\")",
            "(paper \"fake (stackup (thickness 0)) \\\"quoted\\\"\")",
            1
        )));
        assert!(!passes("(kicad_pcb (paper \"unterminated\\\""));
    }
    #[test]
    fn four_layer_stackup_checks_each_dielectric_and_copper_order() {
        let board = r#"(kicad_pcb (general (thickness 1.6))
            (layers (0 "F.Cu" signal) (4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal))
            (setup (stackup
              (layer "F.Cu" (type "copper") (thickness 0.07))
              (layer "dielectric 1" (type "prepreg") (thickness 0.2))
              (layer "In1.Cu" (type "copper") (thickness 0.035))
              (layer "dielectric 2" (type "core") (thickness 0.99))
              (layer "In2.Cu" (type "copper") (thickness 0.035))
              (layer "dielectric 3" (type "prepreg") (thickness 0.2))
              (layer "B.Cu" (type "copper") (thickness 0.07)))))"#;
        assert!(passes(board));
        assert!(!passes(&board.replacen(
            "(thickness 0.2)",
            "(thickness 0)",
            1
        )));
        assert!(!passes(&board.replacen(
            "(thickness 0.035)",
            "(thickness -0.035)",
            1
        )));
        assert!(!passes(&board.replacen(
            "(layer \"In1.Cu\"",
            "(layer \"In2.Cu\"",
            1
        )));
    }
    #[test]
    fn excessive_nesting_and_unicode_are_handled_without_panics() {
        assert!(!passes(&("(".repeat(140) + &")".repeat(140))));
        assert!(passes(&fixed().replacen(
            "(paper \"A4\")",
            "(paper \"µm — FR4\")",
            1
        )));
    }
}
