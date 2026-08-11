//! strip_copper: paren-balanced removal of committed copper s-expression
//! blocks (`(segment ...)`, `(via ...)`, `(zone ...)`) from KiCad board
//! content.
//!
//! Ported verbatim from `temper_placer/router_v6/_strip_copper.py` (the
//! crate VERIFICATION.md carries the parity proof; the differential oracle in
//! `packages/temper-placer/tests/router_v6/test_strip_copper_rust_differential.py`
//! is a verbatim copy of the pre-migration Python).  The algorithm is
//! deliberately naive -- it tracks a parenthesis depth from each block's
//! opening line rather than parsing the s-expression grammar, so parens
//! inside quoted strings are counted exactly as the reference counts them.
//! Parity with the pinned oracle, not s-expression correctness, is the
//! contract, and the differential pins the naive corners (quoted unbalanced
//! parens, negative-depth closes) on both sides.
//!
//! Pure-Rust core (`strip_blocks` / `strip_existing_copper` /
//! `strip_existing_zones`, wasm32-safe) plus a thin `#[cfg(feature =
//! "python")]` pyo3 boundary, following the `isolation`/`dsn` module shape.

use regex::Regex;

/// A CPython-`\s` whitespace class.  The `regex` crate's `\s` is Unicode
/// White_Space, which omits U+001C..=U+001F that CPython's (str) `\s`
/// includes; unioning `\x1c-\x1f` reproduces CPython's class exactly, so a
/// line whose leading whitespace is a file/group/record/unit separator (or
/// whose keyword is followed by one) behaves identically on both sides.
const PY_WS: &str = r"[\s\x1c-\x1f]";

/// Result of a strip pass: the cleaned content and how many blocks were
/// removed.
#[derive(Debug, PartialEq, Eq)]
pub struct StripResult {
    /// The content with every matched block's lines removed.
    pub content: String,
    /// How many blocks were removed (a block counts once when it opens).
    pub removed: usize,
}

/// Compile the opening-line pattern for `keywords`, reproducing CPython's
/// `re.compile(r"^\s*\((" + "|".join(re.escape(k) for k in keywords) + r")\s")`.
///
/// The pattern is a fixed skeleton around `regex::escape`d literals, so it
/// is always a valid regex and cannot fail to compile.
#[expect(clippy::expect_used, reason = "escaped literals in a fixed skeleton are always a valid regex")]
fn opening_pattern(keywords: &[&str]) -> Regex {
    let kws = keywords
        .iter()
        .map(|k| regex::escape(k))
        .collect::<Vec<_>>()
        .join("|");
    Regex::new(&format!("^{PY_WS}*\\((?:{kws}){PY_WS}"))
        .expect("escaped keywords in a fixed skeleton cannot fail to compile")
}

/// Remove every top-level `(keyword ...)` block for each *keywords* entry,
/// tracking paren depth from each block's opening line.
///
/// A block "opens" on the first line (after leading whitespace) whose
/// beginning matches `(keyword ` for some keyword.  From there every `(`
/// and `)` on subsequent lines (including the opening line itself) adjusts a
/// running depth counter; the block ends on the line where that counter
/// returns to zero (or below, defensively).  This is correct whether the
/// whole block is on one line (`(segment ...)`, `(via ...)`) or spans many
/// (`(zone ...)`).
pub fn strip_blocks(content: &str, keywords: &[&str]) -> StripResult {
    let pattern = opening_pattern(keywords);
    let mut out: Vec<&str> = Vec::new();
    let mut removed = 0usize;
    let mut depth = 0isize;
    let mut in_block = false;
    for line in content.split('\n') {
        if !in_block && pattern.is_match(line) {
            in_block = true;
            depth = 0;
            removed += 1;
        }
        if in_block {
            depth += line.matches('(').count() as isize - line.matches(')').count() as isize;
            if depth <= 0 {
                in_block = false;
            }
            continue;
        }
        out.push(line);
    }
    StripResult {
        content: out.join("\n"),
        removed,
    }
}

/// Remove every committed `(segment ...)`, `(via ...)`, and `(zone ...)`
/// top-level s-expression block from `content` -- the routing-*input* half
/// of R7: a board handed to `route_pcb` through this function no longer
/// carries its committed zones as data the router (or anything reading its
/// output) could mistake for authoritative.
pub fn strip_existing_copper(content: &str) -> StripResult {
    strip_blocks(content, &["segment", "via", "zone"])
}

/// Remove only `(zone ...)` blocks from `content`, leaving any
/// `(segment ...)`/`(via ...)` entries untouched -- the routing-*output*
/// half of R7: the written board's zones are exactly this run's regenerated
/// set, never the stale carryover from the input board.
pub fn strip_existing_zones(content: &str) -> StripResult {
    strip_blocks(content, &["zone"])
}

#[cfg(feature = "python")]
mod py_bridge {
    use super::*;
    use pyo3::prelude::*;

    fn to_pair(result: StripResult) -> (String, usize) {
        (result.content, result.removed)
    }

    #[pyfunction(name = "strip_existing_copper")]
    fn strip_existing_copper_py(content: &str) -> PyResult<(String, usize)> {
        temper_py_bridge::catch_panic(|| Ok(to_pair(super::strip_existing_copper(content))))
    }

    #[pyfunction(name = "strip_existing_zones")]
    fn strip_existing_zones_py(content: &str) -> PyResult<(String, usize)> {
        temper_py_bridge::catch_panic(|| Ok(to_pair(super::strip_existing_zones(content))))
    }

    pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(strip_existing_copper_py, m)?)?;
        m.add_function(wrap_pyfunction!(strip_existing_zones_py, m)?)?;
        Ok(())
    }
}

#[cfg(feature = "python")]
pub use py_bridge::register;

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn single_line_segment_is_stripped() {
        let r = strip_existing_copper(
            "  (segment (start 0 0) (end 1 1) (width 0.2) (layer \"F.Cu\") (net 1))\n",
        );
        assert_eq!(r.removed, 1);
        assert_eq!(r.content, "");
    }

    #[cfg_attr(test, test)]
    fn multiline_zone_block_is_stripped() {
        let zone = "  (zone (net 4) (net_name \"+3V3\") (layer \"F.Cu\") (hatch full 0.5)\n\
                    \t(priority 50)\n\
                    \t(polygon\n\
                    \t  (pts\n\
                    \t    (xy 122.5485 147.3413)\n\
                    \t    (xy 122.601 147.3926)\n\
                    \t  )\n\
                    \t)\n\
                    \t)\n";
        let r = strip_existing_zones(zone);
        assert_eq!(r.removed, 1);
        assert_eq!(r.content, "");
    }

    #[cfg_attr(test, test)]
    fn copper_strips_zones_segments_and_vias() {
        let board = "(kicad_pcb\n\
            \x20 (segment (start 0 0) (end 1 1) (width 0.2) (layer \"F.Cu\") (net 1))\n\
            \x20 (via (at 1 1) (size 0.8) (drill 0.4) (layers \"F.Cu\" \"B.Cu\") (net 1))\n\
            \x20 (zone (net 1) (net_name \"GND\") (layer \"F.Cu\") (hatch full 0.5)\n\
            \x20\x20 (polygon (pts (xy 0 0) (xy 1 0)))\n\
            \x20 )\n\
            )\n";
        let r = strip_existing_copper(board);
        assert_eq!(r.removed, 3);
        assert_eq!(r.content, "(kicad_pcb\n)\n");
    }

    #[cfg_attr(test, test)]
    fn zones_strip_leaves_segments_and_vias() {
        let board = "(kicad_pcb\n\
            \x20 (zone (net 1) (net_name \"GND\") (layer \"F.Cu\")\n\
            \x20\x20 (polygon (pts (xy 0 0)))\n\
            \x20 )\n\
            \x20 (segment (start 0 0) (end 1 1) (width 0.2) (layer \"F.Cu\") (net 1))\n\
            )\n";
        let r = strip_existing_zones(board);
        assert_eq!(r.removed, 1);
        assert!(r.content.contains("(segment (start 0 0)"));
    }

    #[cfg_attr(test, test)]
    fn no_keyword_blocks_is_a_no_op() {
        let content = "(kicad_pcb\n  (net 1 \"GND\")\n)\n";
        let r = strip_existing_copper(content);
        assert_eq!(r.removed, 0);
        assert_eq!(r.content, content);
    }

    #[cfg_attr(test, test)]
    fn keyword_needs_trailing_whitespace() {
        // `(zone)`, `(zonex ...)` do NOT open a block; `(zone 1 ...)` does.
        let content = "(kicad_pcb\n  (zone)\n  (zonex (net 1))\n  (zone 1 (net 1))\n)\n";
        let r = strip_existing_zones(content);
        assert_eq!(r.removed, 1);
        assert!(r.content.contains("  (zone)\n"));
        assert!(r.content.contains("  (zonex (net 1))"));
        assert!(!r.content.contains("(zone 1"));
    }

    #[cfg_attr(test, test)]
    fn negative_depth_closes_block_one_line_early() {
        // Opening line is net -1: the block closes on its own opening line.
        let r = strip_existing_zones("  (zone ))\n  (net 1 \"GND\")\n");
        assert_eq!(r.removed, 1);
        assert_eq!(r.content, "  (net 1 \"GND\")\n");
        // A net-0 opening line (`(zone )` -- one open, one close) closes on
        // the same line too, defensively.
        let balanced = strip_existing_zones("  (zone ) extra\n  (net 1 \"GND\")\n");
        assert_eq!(balanced.removed, 1);
        assert_eq!(balanced.content, "  (net 1 \"GND\")\n");
    }

    #[cfg_attr(test, test)]
    fn unbalanced_depth_swallows_following_lines() {
        // Opening line is net +3, so the block does not close at the zone's
        // natural end: the `))` line drops depth to zero and the block
        // swallows lines 1-3, leaving the rest.
        let content = "(kicad_pcb\n\
            \x20 (zone (net 1 (net_name \"GND\"\n\
            \x20\x20 (polygon (pts (xy 0 0)))\n\
            \x20 )))\n\
            \x20 (net 2 \"X\")\n\
            )\n";
        let r = strip_existing_zones(content);
        assert_eq!(r.removed, 1);
        assert_eq!(r.content, "(kicad_pcb\n  (net 2 \"X\")\n)\n");
    }

    #[cfg_attr(test, test)]
    fn crlf_lines_keep_carriage_returns() {
        let content = "(kicad_pcb\r\n\
            \x20 (zone (net 1) (net_name \"GND\") (layer \"F.Cu\")\r\n\
            \x20\x20 (polygon (pts (xy 0 0)))\r\n\
            \x20 )\r\n\
            \x20 (segment (start 1 1) (end 2 2) (width 0.2) (layer \"F.Cu\") (net 1))\r\n\
            )\r\n";
        let r = strip_existing_zones(content);
        assert_eq!(r.removed, 1);
        assert!(r.content.contains("(segment (start 1 1) (end 2 2) (width 0.2) (layer \"F.Cu\") (net 1))\r\n"));
    }

    #[cfg_attr(test, test)]
    fn parens_inside_quoted_strings_count_toward_depth() {
        // A net-negative quoted string (`"(GND("`) adds a structural open to
        // the running depth, exactly as the Python reference does: the zone's
        // own close leaves depth at 1, so the block swallows the following
        // `(net 2 ...)` line and closes on the document's final `)`.
        // Parity, not correctness, is the contract.
        let content = "(kicad_pcb\n  (zone (net 1) (net_name \"GND(\") (layer \"F.Cu\")\n  )\n  (net 2 \"X\")\n)\n";
        let r = strip_existing_zones(content);
        assert_eq!(r.removed, 1);
        assert_eq!(r.content, "(kicad_pcb\n");
    }

    #[cfg_attr(test, test)]
    fn empty_and_no_trailing_newline() {
        let empty = strip_existing_copper("");
        assert_eq!(empty.removed, 0);
        assert_eq!(empty.content, "");

        let single = strip_existing_zones("(zone (net 1))");
        assert_eq!(single.removed, 1);
        assert_eq!(single.content, "");
    }

    #[cfg_attr(test, test)]
    fn block_span_consumes_nested_segment() {
        // A `(segment ...)` inside a zone's span is removed with the zone
        // (removed == 1), not counted independently.
        let content = "(kicad_pcb\n\
            \x20 (zone (net 1) (net_name \"GND\") (layer \"F.Cu\") (hatch full 0.5)\n\
            \x20\x20 (segment (start 1 1) (end 2 2) (width 0.2) (layer \"F.Cu\") (net 1))\n\
            \x20\x20 (polygon (pts (xy 0 0)))\n\
            \x20 )\n\
            \x20 (segment (start 5 5) (end 6 6) (width 0.2) (layer \"F.Cu\") (net 1))\n\
            )\n";
        let r = strip_existing_copper(content);
        assert_eq!(r.removed, 2, "zone + top-level segment, not the nested one");
        assert_eq!(r.content, "(kicad_pcb\n)\n");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("strip_copper::tests::single_line_segment_is_stripped", single_line_segment_is_stripped),
        ("strip_copper::tests::multiline_zone_block_is_stripped", multiline_zone_block_is_stripped),
        ("strip_copper::tests::copper_strips_zones_segments_and_vias", copper_strips_zones_segments_and_vias),
        ("strip_copper::tests::zones_strip_leaves_segments_and_vias", zones_strip_leaves_segments_and_vias),
        ("strip_copper::tests::no_keyword_blocks_is_a_no_op", no_keyword_blocks_is_a_no_op),
        ("strip_copper::tests::keyword_needs_trailing_whitespace", keyword_needs_trailing_whitespace),
        ("strip_copper::tests::negative_depth_closes_block_one_line_early", negative_depth_closes_block_one_line_early),
        ("strip_copper::tests::unbalanced_depth_swallows_following_lines", unbalanced_depth_swallows_following_lines),
        ("strip_copper::tests::crlf_lines_keep_carriage_returns", crlf_lines_keep_carriage_returns),
        ("strip_copper::tests::parens_inside_quoted_strings_count_toward_depth", parens_inside_quoted_strings_count_toward_depth),
        ("strip_copper::tests::empty_and_no_trailing_newline", empty_and_no_trailing_newline),
        ("strip_copper::tests::block_span_consumes_nested_segment", block_span_consumes_nested_segment),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
