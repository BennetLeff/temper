//! `router_v6.net_classification.is_ground_net`, the one classifier whose
//! result reaches `_classify_vias`'s return value.
//!
//! `is_signal_net` is deliberately absent: its call site in `_classify_vias`
//! feeds an accumulator that is unconditionally overwritten two lines later by
//! `signal = total - thermal - stitching` (defect 1 in the oracle header). The
//! call has no observable effect, so porting it would add a dependency the
//! kernel's output does not have.
//!
//! `_SINGLE_LAYER_MODE` is a module-global read at call time, i.e. a hidden
//! input. It is sampled from the live Python module by the bindings and passed
//! in rather than baked in here.

/// `GROUND_NET_PATTERNS`. The frozenset is iterated in hash order in Python,
/// but the loop short-circuits on the first match and the result is a bare
/// `bool`, so the order is not observable.
const GROUND_NET_PATTERNS: [&str; 6] = ["GND", "PGND", "CGND", "AGND", "DGND", "VSS"];

/// The `(?:$|[\d_])` trailing boundary. Python's `\d` is Unicode `Nd`;
/// `char::is_numeric` is `Nd | Nl | No`, a superset that differs only for
/// characters (Roman numerals, vulgar fractions) that cannot appear in a
/// KiCad net name.
#[inline]
fn is_trailing_boundary(c: char) -> bool {
    c == '_' || c.is_numeric()
}

/// `_matches_any(name, GROUND_NET_PATTERNS)` for the all-alphanumeric ground
/// patterns: a word-boundary match delimited by `_` or the string ends.
fn matches_ground_pattern(upper: &str) -> bool {
    let chars: Vec<char> = upper.chars().collect();
    for pattern in GROUND_NET_PATTERNS {
        let pat: Vec<char> = pattern.chars().collect();
        if pat.len() > chars.len() {
            continue;
        }
        for start in 0..=(chars.len() - pat.len()) {
            if chars[start..start + pat.len()] != pat[..] {
                continue;
            }
            let leading_ok = start == 0 || chars[start - 1] == '_';
            let after = start + pat.len();
            let trailing_ok = after == chars.len() || is_trailing_boundary(chars[after]);
            if leading_ok && trailing_ok {
                return true;
            }
        }
    }
    false
}

/// `is_ground_net(name)`.
pub fn is_ground_net(name: &str, single_layer_mode: bool) -> bool {
    if single_layer_mode {
        return false;
    }
    matches_ground_pattern(&name.to_uppercase())
}

#[cfg(test)]
mod tests {
    use super::is_ground_net;

    #[test]
    fn ground_patterns_are_word_bounded() {
        assert!(is_ground_net("GND", false));
        assert!(is_ground_net("gnd", false));
        assert!(is_ground_net("GND1", false));
        assert!(is_ground_net("A_GND_B", false));
        assert!(is_ground_net("PGND", false));
        // Not word-bounded: a bare substring must not match.
        assert!(!is_ground_net("XGND", false));
        assert!(!is_ground_net("GNDX", false));
        assert!(!is_ground_net("", false));
        assert!(!is_ground_net("DC_BUS+", false));
        // Single-layer mode is a hidden input that suppresses every match.
        assert!(!is_ground_net("GND", true));
    }
}
