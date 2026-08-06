//! Port of `temper_placer.core.net_classification`.
//!
//! # The measured trap: Python `$` is not Rust `$`
//!
//! The reference matches with `re.search(rf"(?:^|_){escaped}(?:$|[\d_])", upper)`.
//! In Python, `$` (without `re.MULTILINE`) matches at the end of the
//! string **or immediately before a trailing newline**. Rust's `regex`
//! crate matches `$` at end-of-haystack only. Measured on the live
//! reference:
//!
//! ```text
//! _matches_any("GND",    GROUND_NET_PATTERNS) -> True
//! _matches_any("GND\n",  GROUND_NET_PATTERNS) -> True   <-- the trap
//! _matches_any("GND\nX", GROUND_NET_PATTERNS) -> False
//! ```
//!
//! A naive port returns `False` for `"GND\n"` — a net whose name picked
//! up a stray newline would be silently reclassified from ground to
//! signal. The trailing-boundary alternation below is therefore
//! `(?:\z|(?=\n\z)|[\d_])`, not `(?:$|[\d_])`.
//!
//! # `^` needs no such treatment
//!
//! Python's `^` without `re.MULTILINE` matches only at position 0, which
//! is exactly Rust's `\A`. `"\nGND"` is `False` in both.
//!
//! # Iteration order is irrelevant here, and that is proven, not assumed
//!
//! `_matches_any` iterates a `frozenset`, whose order is
//! `PYTHONHASHSEED`-dependent for `str` elements. The function is a pure
//! disjunction (`return True` on the first hit, `False` after all), so
//! the result is order-invariant — but the program brief is explicit
//! that order-invariance must be *proven* rather than sorted away. The
//! Rust port keeps the patterns in a fixed array and the R1d metamorphic
//! suite runs the reference under several `PYTHONHASHSEED` values to
//! confirm the reference agrees with itself and with Rust.
//!
//! # `str.upper()`
//!
//! Both CPython's `str.upper()` and Rust's `str::to_uppercase()`
//! implement the full (not simple) Unicode uppercase mapping, including
//! the length-changing ones: `'ß' -> "SS"` and `'ı' -> "I"` were
//! measured to agree. The differential includes a Unicode corpus.

use regex::Regex;
use std::sync::OnceLock;

pub const GROUND_NET_PATTERNS: [&str; 6] = ["GND", "PGND", "CGND", "AGND", "DGND", "VSS"];
pub const POWER_NET_PATTERNS: [&str; 7] = ["+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"];
pub const HV_NET_PATTERNS: [&str; 6] = ["AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"];

pub const GROUND_PIN_PATTERNS: [&str; 6] = ["GND", "VSS", "AGND", "DGND", "PGND", "CGND"];
pub const POWER_PIN_PATTERNS: [&str; 7] = ["VCC", "VDD", "VIN", "VOUT", "PVCC", "VBUS", "PWR"];
pub const HV_PIN_PATTERNS: [&str; 6] = ["AC_L", "AC_N", "PE", "HV", "MAINS", "RECT"];
pub const CLOCK_PIN_PATTERNS: [&str; 6] = ["CLK", "CLOCK", "XTAL1", "XTAL2", "OSC_IN", "OSC_OUT"];

/// Which pattern set a query is being matched against.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PatternSet {
    GroundNet,
    PowerNet,
    HvNet,
    GroundPin,
    PowerPin,
    HvPin,
    ClockPin,
}

impl PatternSet {
    fn patterns(self) -> &'static [&'static str] {
        match self {
            PatternSet::GroundNet => &GROUND_NET_PATTERNS,
            PatternSet::PowerNet => &POWER_NET_PATTERNS,
            PatternSet::HvNet => &HV_NET_PATTERNS,
            PatternSet::GroundPin => &GROUND_PIN_PATTERNS,
            PatternSet::PowerPin => &POWER_PIN_PATTERNS,
            PatternSet::HvPin => &HV_PIN_PATTERNS,
            PatternSet::ClockPin => &CLOCK_PIN_PATTERNS,
        }
    }

    fn compiled(self) -> &'static Vec<Regex> {
        macro_rules! cell {
            ($name:ident) => {{
                static $name: OnceLock<Vec<Regex>> = OnceLock::new();
                $name.get_or_init(|| compile_set(self.patterns()))
            }};
        }
        match self {
            PatternSet::GroundNet => cell!(GROUND_NET),
            PatternSet::PowerNet => cell!(POWER_NET),
            PatternSet::HvNet => cell!(HV_NET),
            PatternSet::GroundPin => cell!(GROUND_PIN),
            PatternSet::PowerPin => cell!(POWER_PIN),
            PatternSet::HvPin => cell!(HV_PIN),
            PatternSet::ClockPin => cell!(CLOCK_PIN),
        }
    }
}

/// The reference's `p and not p[-1].isalnum()` test.
///
/// Python's `str.isalnum()` is Unicode-aware, but every pattern in this
/// module is ASCII, so `is_alphanumeric()` on the final `char` is
/// equivalent over the actual domain. (The patterns are compile-time
/// constants; a new non-ASCII pattern would need this revisited, which
/// the `patterns_are_ascii` test below enforces.)
fn has_trailing_boundary(pattern: &str) -> bool {
    match pattern.chars().next_back() {
        None => false,
        Some(last) => last.is_alphanumeric(),
    }
}

fn compile_set(patterns: &[&str]) -> Vec<Regex> {
    patterns
        .iter()
        .filter_map(|p| Regex::new(&pattern_source(p)).ok())
        .collect()
}

/// Build the regex source for one pattern, mirroring `_matches_any`.
pub fn pattern_source(pattern: &str) -> String {
    let escaped = regex::escape(pattern);
    // The reference's guard is `if p and not p[-1].isalnum()`, so an
    // *empty* pattern falls through to the `elif` branch, not the
    // leading-anchor one. The two branches are NOT equivalent on the
    // empty pattern (`(?:^|_)` matches "ABC"; `(?:^|_)(?:$|[\d_])` does
    // not), so the emptiness test has to sit on this side of the `&&`
    // even though no set currently contains an empty pattern.
    if !pattern.is_empty() && !has_trailing_boundary(pattern) {
        // Leading anchor only — a pattern ending in a non-alphanumeric
        // character ("DC_BUS+", "DC_BUS-") has no trailing boundary to
        // anchor on.
        format!(r"(?:\A|_){escaped}")
    } else {
        // `(?:$|[\d_])` in Python == end-of-text, or immediately before a
        // single trailing newline, or a digit/underscore. The `regex`
        // crate has no look-around, so the "before a trailing newline"
        // half is handled by [`strip_one_trailing_newline`] on the
        // haystack instead of by the pattern; see its docs for why the
        // two are equivalent.
        format!(r"(?:\A|_){escaped}(?:\z|[\d_])")
    }
}

/// Remove at most one trailing `\n`, turning Python's `$` into `\z`.
///
/// Python's `$` (no `re.MULTILINE`) matches at end-of-string **or** at
/// the one position immediately before a single trailing newline.
/// Deleting that newline moves the second position onto the first, so
/// `\z` alone then covers both. The rewrite is safe for the rest of the
/// pattern because:
///
/// * only the tail changes, so `\A` and the `_` alternative are untouched;
/// * `\n` is not in `[\d_]`, so no `[\d_]` match can be destroyed by
///   removing it;
/// * no pattern in any set contains `\n`, so none can lose a literal
///   character.
///
/// Verified against the reference on `"GND"`, `"GND\n"`, `"GND\n\n"`,
/// `"GND\nX"`, `"\nGND"` and `"GND_\n"`.
fn strip_one_trailing_newline(s: &str) -> &str {
    s.strip_suffix('\n').unwrap_or(s)
}

/// `_matches_any(name, patterns)`.
pub fn matches_any(name: &str, set: PatternSet) -> bool {
    let upper = name.to_uppercase();
    let haystack = strip_one_trailing_newline(&upper);
    set.compiled().iter().any(|re| re.is_match(haystack))
}

pub fn is_ground_net(name: &str) -> bool {
    matches_any(name, PatternSet::GroundNet)
}

pub fn is_power_net(name: &str) -> bool {
    matches_any(name, PatternSet::PowerNet)
}

pub fn is_hv_net(name: &str) -> bool {
    matches_any(name, PatternSet::HvNet)
}

pub fn is_signal_net(name: &str) -> bool {
    !(is_ground_net(name) || is_power_net(name) || is_hv_net(name))
}

/// Precedence: ground > power > hv > signal.
pub fn classify_net_type(name: &str) -> &'static str {
    if is_ground_net(name) {
        "ground"
    } else if is_power_net(name) {
        "power"
    } else if is_hv_net(name) {
        "hv"
    } else {
        "signal"
    }
}

pub fn is_ground_pin(pin_name: &str) -> bool {
    matches_any(pin_name, PatternSet::GroundPin)
}

pub fn is_power_pin(pin_name: &str) -> bool {
    matches_any(pin_name, PatternSet::PowerPin)
}

pub fn is_hv_pin(pin_name: &str) -> bool {
    matches_any(pin_name, PatternSet::HvPin)
}

pub fn is_clock_pin(pin_name: &str) -> bool {
    matches_any(pin_name, PatternSet::ClockPin)
}

pub const ALL_SETS: [PatternSet; 7] = [
    PatternSet::GroundNet,
    PatternSet::PowerNet,
    PatternSet::HvNet,
    PatternSet::GroundPin,
    PatternSet::PowerPin,
    PatternSet::HvPin,
    PatternSet::ClockPin,
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn patterns_are_ascii_and_non_empty() {
        for set in ALL_SETS {
            for p in set.patterns() {
                assert!(!p.is_empty(), "empty pattern in {set:?}");
                assert!(p.is_ascii(), "non-ASCII pattern {p:?} in {set:?}");
            }
        }
    }

    #[test]
    fn every_pattern_compiles() {
        for set in ALL_SETS {
            assert_eq!(
                set.compiled().len(),
                set.patterns().len(),
                "a pattern in {set:?} failed to compile"
            );
        }
    }

    #[test]
    fn trailing_newline_trap() {
        assert!(is_ground_net("GND"));
        assert!(is_ground_net("GND\n"));
        assert!(!is_ground_net("GND\nX"));
        assert!(!is_ground_net("\nGND"));
        assert!(is_ground_net("AGND\n"));
        assert!(is_ground_net("gnd\n"));
        // Only ONE trailing newline counts, in Python and here.
        assert!(!is_ground_net("GND\n\n"));
        assert!(is_ground_net("GND_\n"));
    }

    #[test]
    fn pe_is_word_bounded_not_substring() {
        // The bug this module's docstring records: "PE" as a plain
        // substring matches "SPEED".
        assert!(is_hv_net("PE"));
        assert!(!is_hv_net("SPEED"));
        assert!(is_hv_net("TYPE_PE"));
    }

    #[test]
    fn non_alnum_tail_is_leading_anchor_only() {
        assert!(is_hv_net("DC_BUS+"));
        assert!(is_hv_net("X_DC_BUS+FOO"));
        assert!(is_hv_net("DC_BUS+123"));
        assert!(is_hv_net("DC_BUS-"));
    }

    #[test]
    fn precedence_is_ground_power_hv_signal() {
        assert_eq!(classify_net_type("GND"), "ground");
        assert_eq!(classify_net_type("VCC"), "power");
        assert_eq!(classify_net_type("AC_L"), "hv");
        assert_eq!(classify_net_type("SDA"), "signal");
        // A name matching both ground and hv resolves to ground.
        assert_eq!(classify_net_type("GND_PE"), "ground");
    }

    #[test]
    fn signal_is_the_complement() {
        for name in ["GND", "VCC", "AC_L", "SDA", "", "PE", "DC_BUS+"] {
            assert_eq!(
                is_signal_net(name),
                classify_net_type(name) == "signal",
                "disagreement on {name:?}"
            );
        }
    }

    #[test]
    fn unicode_case_folding() {
        assert!(is_ground_net("ß_gnd")); // 'ß'.upper() == "SS"
        assert!(is_ground_net("ı_gnd")); // 'ı'.upper() == "I"
        assert!(!is_ground_net("gndı"));
    }
}
