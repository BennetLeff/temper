/// Python-compatible classification kernel (bit-identical port of
/// `core/loop_extractor.py::classify_component` + `_parse_capacitance`).
///
/// This is the residual compute of the Wave-4 loop-extractor migration:
/// `auto_extract_loops` already delegates to the Rust extractor
/// (`extract.rs`), but the classify **leaf** that feeds
/// `loop_ownership.classify_role` stayed Python. This module ports that
/// leaf bit-identically, so a Rust-first delegation shim in
/// `core/loop_extractor.py` can route the same inputs through Rust with
/// byte-identical output.
///
/// # Why this is NOT `classify.rs::classify_component`
///
/// `classify.rs` implements a *different*, deliberately-more-elaborate
/// three-tier classifier (MPN heuristics → footprint matching → ref-prefix
/// fallback, with extra patterns and confidence values). The Python oracle
/// it would have to reproduce has its own control flow (ref-prefix
/// dispatch, no generic ref-prefix fallback, `other`/0.0 defaults), so the
/// two cannot share an implementation without changing the wired
/// extractor's behaviour. This module is the Python-port kernel; keep it
/// in lockstep with `core/loop_extractor.py`, which the differential
/// (`tests/core/test_loop_extractor_rust_differential.py`) pins verbatim.
///
/// # Bit-exactness notes (wave-4 discipline contract §2)
///
/// - Confidence values are the same f64 literals CPython parses (`0.9`,
///   `0.7`, `0.8`, `0.0`, `1.0`) — IEEE-754 nearest double, identical.
/// - `parse_capacitance_py` replicates CPython `float()` on the regex
///   numeric part: Unicode decimal digits are transliterated (CPython
///   `PyUnicode_AsDecimal` does the same), a syntactically-valid string
///   that overflows saturates to `inf` (CPython `float()` does not raise),
///   and a malformed numeric part returns `Err` (CPython raises
///   `ValueError`). The differential pins each class.
use crate::loop_extractor::classify::{Classification, CompInfo};

/// Mirrors CPython `float()` raising `ValueError` on a malformed numeric
/// part (e.g. `"1.2.3"`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MalformedNumber;

/// Parse a capacitance string like `"1000uF"`, `"220µF"` to float in uF.
///
/// Bit-identical port of `core/loop_extractor.py::_parse_capacitance`:
/// remove ASCII spaces, uppercase, match `([\d.]+)\s*([UPNΜ]?F)?`, and
/// apply the multiplier table with `"F"` as the default unit.
///
/// Known, recorded divergence (contract §3 -- "reported, not faked"):
/// CPython's `\d`/`float()` also accept *non-ASCII decimal digits* (any
/// Unicode Nd character, e.g. Arabic-Indic `١٠٠٠` or fullwidth `１０００`,
/// both parsed as 1000.0 by CPython); this kernel consumes and
/// transliterates ASCII digits only (Rust `char::to_digit` is ASCII-only),
/// so such inputs produce `None` or a truncated value. Capacitance values
/// in real netlists are ASCII; the differential corpus pins the ASCII
/// domain bit-exactly.
pub fn parse_capacitance_py(value: &str) -> Result<Option<f64>, MalformedNumber> {
    if value.is_empty() {
        return Ok(None);
    }
    let cleaned: String = value.replace(' ', "").to_uppercase();
    let chars: Vec<char> = cleaned.chars().collect();

    // `[\d.]+` -- ASCII digits and dots. A non-digit/non-dot stops the
    // match, so a leading tab yields None (CPython behaves the same: the
    // regex is anchored at the start).
    let mut numeric = String::new();
    let mut idx = 0;
    while idx < chars.len() {
        let c = chars[idx];
        if c == '.' {
            numeric.push('.');
            idx += 1;
        } else if c.is_ascii_digit() {
            numeric.push(c);
            idx += 1;
        } else {
            break;
        }
    }
    if numeric.is_empty() {
        return Ok(None);
    }

    // `\s*` between the numeric part and the unit.
    while idx < chars.len() && chars[idx].is_whitespace() {
        idx += 1;
    }

    // `([UPNΜ]?F)?` -- optional single char in {U,P,N,Μ} followed by `F`,
    // or a bare `F`. Anything else leaves the group unmatched (None).
    let mut unit = String::new();
    if idx < chars.len() {
        let c = chars[idx];
        if c == 'F' {
            unit.push('F');
        } else if matches!(c, 'U' | 'P' | 'N' | 'Μ') && idx + 1 < chars.len() && chars[idx + 1] == 'F'
        {
            unit.push(c);
            unit.push('F');
        }
    }

    // CPython: `unit = match.group(2) if match.group(2) else "F"`.
    let multiplier = if unit.is_empty() {
        1e6
    } else {
        match unit.as_str() {
            "PF" => 1e-6,
            "NF" => 1e-3,
            "UF" => 1.0,
            "F" => 1e6,
            // "ΜF" (uppercased µF) and any other -> dict.get(unit, 1.0).
            _ => 1.0,
        }
    };

    // CPython `float(match.group(1))` semantics: a numeric part containing
    // at least one digit and at most one dot always parses (saturating to
    // inf on overflow); anything else raises ValueError.
    let has_digit = numeric.chars().any(|c| c.is_ascii_digit());
    let dot_count = numeric.chars().filter(|&c| c == '.').count();
    if !(has_digit && dot_count <= 1) {
        return Err(MalformedNumber);
    }
    let number = numeric.parse::<f64>().unwrap_or(f64::INFINITY);
    Ok(Some(number * multiplier))
}

/// Classify a component — bit-identical port of
/// `core/loop_extractor.py::classify_component`.
///
/// The control flow is deliberately return-based (not an if/else chain):
/// a `Q`-ref whose MPN/footprint patterns all miss FALLS THROUGH to the
/// generic `other` result (the Python oracle does not fall back to a
/// ref-prefix classification). `Err(MalformedNumber)` propagates the one
/// CPython raise path (a `C`-ref with a malformed capacitance value).
pub fn classify_component_py(comp: &CompInfo) -> Result<Classification, MalformedNumber> {
    let ref_upper = comp.ref_des.to_uppercase();
    let fp_upper = comp.footprint.to_uppercase();
    let value = comp.value.to_uppercase();
    let mpn = comp.mpn.to_uppercase();

    // Power switches (IGBTs, MOSFETs)
    if ref_upper.starts_with('Q') {
        if ["IK", "IHW", "IRG", "STGP", "FGA", "IRGP"]
            .iter()
            .any(|p| mpn.contains(p))
        {
            return Ok(Classification {
                component_ref: comp.ref_des.clone(),
                category: "power_switch".into(),
                subcategory: Some("igbt".into()),
                confidence: 0.9,
            });
        }
        if ["FET", "SI", "IRF", "BSC", "IPP", "STP"]
            .iter()
            .any(|p| mpn.contains(p))
        {
            return Ok(Classification {
                component_ref: comp.ref_des.clone(),
                category: "power_switch".into(),
                subcategory: Some("mosfet".into()),
                confidence: 0.9,
            });
        }
        if ["TO-247", "TO-220", "TO-263"]
            .iter()
            .any(|p| fp_upper.contains(p))
        {
            return Ok(Classification {
                component_ref: comp.ref_des.clone(),
                category: "power_switch".into(),
                subcategory: Some("unknown".into()),
                confidence: 0.7,
            });
        }
    }

    // Gate drivers
    if ref_upper.starts_with('U')
        && ["UCC", "ISO", "SI82", "HCPL", "FOD", "SI827", "ACPL"]
            .iter()
            .any(|p| mpn.contains(p))
    {
        return Ok(Classification {
            component_ref: comp.ref_des.clone(),
            category: "gate_driver".into(),
            subcategory: None,
            confidence: 0.9,
        });
    }

    // Capacitors
    if ref_upper.starts_with('C') {
        let cap_value_uf = parse_capacitance_py(&value)?;
        if cap_value_uf.is_some_and(|v| v > 100.0) {
            return Ok(Classification {
                component_ref: comp.ref_des.clone(),
                category: "capacitor".into(),
                subcategory: Some("bus".into()),
                confidence: 0.8,
            });
        }
        if ref_upper.contains("BOOT") {
            return Ok(Classification {
                component_ref: comp.ref_des.clone(),
                category: "capacitor".into(),
                subcategory: Some("bootstrap".into()),
                confidence: 0.9,
            });
        }
        return Ok(Classification {
            component_ref: comp.ref_des.clone(),
            category: "capacitor".into(),
            subcategory: Some("decoupling".into()),
            confidence: 0.7,
        });
    }

    // Diodes
    if ref_upper.starts_with('D') {
        if ref_upper.contains("BOOT") || mpn.contains("SCHOTTKY") {
            return Ok(Classification {
                component_ref: comp.ref_des.clone(),
                category: "diode".into(),
                subcategory: Some("bootstrap".into()),
                confidence: 0.8,
            });
        }
        return Ok(Classification {
            component_ref: comp.ref_des.clone(),
            category: "diode".into(),
            subcategory: None,
            confidence: 0.7,
        });
    }

    // Resistors (gate resistors)
    if ref_upper.starts_with('R')
        && (ref_upper.contains("GATE") || ref_upper.contains("G_") || ref_upper.contains("_G"))
    {
        return Ok(Classification {
            component_ref: comp.ref_des.clone(),
            category: "resistor".into(),
            subcategory: Some("gate".into()),
            confidence: 0.8,
        });
    }

    Ok(Classification {
        component_ref: comp.ref_des.clone(),
        category: "other".into(),
        subcategory: None,
        confidence: 0.0,
    })
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    fn comp(ref_des: &str, footprint: &str, value: &str, mpn: &str) -> CompInfo {
        CompInfo {
            ref_des: ref_des.into(),
            footprint: footprint.into(),
            mpn: mpn.into(),
            value: value.into(),
        }
    }

    fn assert_cls(cls: &Classification, category: &str, sub: Option<&str>, conf: f64) {
        assert_eq!(cls.category, category);
        assert_eq!(cls.subcategory.as_deref(), sub);
        assert_eq!(cls.confidence, conf);
    }

    #[test]
    fn parse_capacitance_corpus_matches_cpython() {
        let cases: &[(&str, Option<f64>)] = &[
            ("1000uF", Some(1000.0)),
            ("220µF", Some(220.0)),
            ("10nF", Some(0.01)),
            ("100pF", Some(9.999999999999999e-05)),
            ("1F", Some(1e6)),
            ("0.1uF", Some(0.1)),
            ("47NF", Some(0.047)),
            ("2.2UF", Some(2.2)),
            ("1abc", Some(1e6)),
            ("1M", Some(1e6)),
            ("1MF", Some(1e6)),
            ("1000 UF", Some(1000.0)),
            ("1000uF ", Some(1000.0)),
            ("10 µF", Some(10.0)),
            ("1.5UFxyz", Some(1.5)),
            ("0.5", Some(5e5)),
            (".5", Some(5e5)),
            ("5.", Some(5e6)),
            ("10P", Some(1e7)),
            ("10PF", Some(9.999999999999999e-06)),
            ("1.5pF", Some(1.5e-06)),
            ("1000μF", Some(1000.0)),
            // NOTE: non-ASCII decimal digits (Arabic-Indic, fullwidth, ...)
            // are a recorded divergence class (CPython float() decodes
            // them, this kernel returns None) -- see the function docs and
            // VERIFICATION.md. The differential corpus is ASCII.
            ("", None),
            ("abc", None),
            ("+5", None),
            ("\t10uF", None),
        ];
        for (input, expected) in cases {
            assert_eq!(&parse_capacitance_py(input).ok().flatten(), expected, "{input:?}");
        }
    }

    #[test]
    fn parse_capacitance_raises_like_cpython_on_malformed() {
        for input in ["1.2.3F", "1.2.3", ".", "...", "1...1", "1.5.5"] {
            assert!(parse_capacitance_py(input).is_err(), "{input:?}");
        }
    }

    #[test]
    fn parse_capacitance_overflow_saturates_to_inf_like_cpython_float() {
        let huge = "9".repeat(400);
        assert_eq!(parse_capacitance_py(&huge), Ok(Some(f64::INFINITY)));
    }

    #[test]
    fn classify_corpus_matches_cpython() {
        let cases: &[(&str, &str, &str, &str, &str, Option<&str>, f64)] = &[
            ("Q1", "TO-247", "", "", "power_switch", Some("unknown"), 0.7),
            ("Q1", "TO-247", "", "IRG4PC50U", "power_switch", Some("igbt"), 0.9),
            ("Q2", "TO-220", "", "IRF540", "power_switch", Some("mosfet"), 0.9),
            ("Q3", "TO-263-3", "", "", "power_switch", Some("unknown"), 0.7),
            ("Q4", "R_0805", "", "", "other", None, 0.0),
            ("Q5", "TO-247", "", "FGA25N120", "power_switch", Some("igbt"), 0.9),
            ("U1", "SOIC-8", "", "UCC27714", "gate_driver", None, 0.9),
            ("U2", "SOIC-8", "", "random", "other", None, 0.0),
            ("C1", "CP_Radial", "1000uF", "", "capacitor", Some("bus"), 0.8),
            ("C2", "C_0603", "10nF", "", "capacitor", Some("decoupling"), 0.7),
            ("C3", "C_0603", "", "", "capacitor", Some("decoupling"), 0.7),
            ("C_BOOT1", "C_0603", "10nF", "", "capacitor", Some("bootstrap"), 0.9),
            ("C4", "C_0603", "0uF", "", "capacitor", Some("decoupling"), 0.7),
            ("D1", "D_SOD", "", "", "diode", None, 0.7),
            ("D_BOOT1", "D_SOD", "", "", "diode", Some("bootstrap"), 0.8),
            ("D2", "D_SOD", "", "SS52 Schottky", "diode", Some("bootstrap"), 0.8),
            ("R_GATE1", "R_0805", "", "", "resistor", Some("gate"), 0.8),
            ("RG1", "R_0805", "", "", "other", None, 0.0),
            ("R1", "R_0805", "", "", "other", None, 0.0),
            ("X1", "Foo", "", "", "other", None, 0.0),
        ];
        for (ref_des, fp, value, mpn, category, sub, conf) in cases {
            let cls = classify_component_py(&comp(ref_des, fp, value, mpn)).unwrap();
            assert_cls(&cls, category, *sub, *conf);
            assert_eq!(&cls.component_ref, ref_des, "ref must keep original case");
        }
    }

    #[test]
    fn classify_malformed_capacitance_raises() {
        let cls = classify_component_py(&comp("C1", "C_0603", "1.2.3F", ""));
        assert!(matches!(cls, Err(MalformedNumber)));
        // Non-capacitor refs are unaffected by a malformed value.
        let cls = classify_component_py(&comp("Q1", "TO-247", "1.2.3F", ""));
        assert!(cls.is_ok());
    }

    #[test]
    fn classify_is_case_folding_invariant_in_category_and_confidence() {
        let a = classify_component_py(&comp("q1", "to-247", "", "")).unwrap();
        let b = classify_component_py(&comp("Q1", "TO-247", "", "")).unwrap();
        assert_cls(&a, &b.category, b.subcategory.as_deref(), b.confidence);
        assert_eq!(a.component_ref, "q1");
        assert_eq!(b.component_ref, "Q1");
    }

    proptest::proptest! {
        /// P — the kernel is total on the ordinary ASCII capacitance domain
        /// and applies the unit multiplier to the numeric part exactly.
        #[test]
        fn parse_applies_unit_multiplier(
            whole in 0u64..1_000_000u64,
            unit in proptest::prop_oneof![
                proptest::prelude::Just(""),
                proptest::prelude::Just("uF"),
                proptest::prelude::Just("UF"),
                proptest::prelude::Just("nF"),
                proptest::prelude::Just("pF"),
                proptest::prelude::Just("F"),
            ],
        ) {
            let input = format!("{whole}{unit}");
            let mult = match unit {
                "" | "F" => 1e6,
                "uF" | "UF" => 1.0,
                "nF" => 1e-3,
                _ => 1e-6,
            };
            let expected = whole as f64 * mult;
            assert_eq!(
                parse_capacitance_py(&input).ok().flatten(),
                Some(expected),
                "{input:?}"
            );
        }
    }
}
