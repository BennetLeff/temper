"""``gen_wasm_test_registry``'s brace counter must ignore non-code braces.

The generator finds a test module's extent by walking lines and tracking
``{``/``}`` depth.  Until 2026-08-24 it did that with
``line.count("{") - line.count("}")`` on the raw line, so any brace inside a
string literal, char literal or comment moved the depth.

That is not a hypothetical.  ``temper-orchestration``'s ``state_ser.rs``
tests the loud-error path with deliberately malformed JSON::

    let e = native_from_json("{not json").unwrap_err();

Four characters of test data.  The naive count read the ``{`` as an unclosed
block, :func:`module_body` walked to EOF without returning to depth 0, and the
gate exited ``unbalanced braces at line 814``.  Because the step exits on the
first crate that fails and ``temper-orchestration`` is 7th of 12, the five
crates after it were never checked at all -- and the two test modules #1434
added (``state_ser``, ``subprocess_stage``, 14 tests) stayed out of the
``wasm32`` corpus while the step reported only a parse error.

These tests pin the constructs that can legally hide a brace.  Every one of
them is real Rust that appears, or could appear, in the crates under gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import gen_wasm_test_registry as g  # noqa: E402


def deltas(src: str) -> list[int]:
    return g.brace_deltas(src.split("\n"))


class TestBracesThatAreNotCode:
    def test_the_regression_case(self) -> None:
        """The exact line that broke the gate contributes nothing."""
        src = 'let e = native_from_json("{not json").unwrap_err();'
        assert deltas(src) == [0]

    def test_string_with_balanced_braces(self) -> None:
        src = 'let e = native_from_json("{\\"typed\\": {\\"a\\": 1}}").unwrap_err();'
        assert deltas(src) == [0]

    def test_unbalanced_closing_brace_in_a_string(self) -> None:
        assert deltas('let s = "}";') == [0]

    def test_line_comment(self) -> None:
        assert deltas("let x = 1; // opens a block {") == [0]

    def test_doc_comment_with_a_code_sample(self) -> None:
        assert deltas("/// mod tests { fn a() {} }") == [0]

    def test_block_comment_spanning_lines(self) -> None:
        src = "/* {\n   {\n*/ fn a() {"
        assert deltas(src) == [0, 0, 1]

    def test_block_comments_nest(self) -> None:
        # Rust block comments nest; C's do not.  A single `*/` must not be
        # taken as closing an outer comment that is still open.
        src = "/* outer /* inner { */ still in a comment {\n*/ fn a() {"
        assert deltas(src) == [0, 1]

    def test_char_literal_brace(self) -> None:
        assert deltas("if c == '{' { n += 1; }") == [0]

    def test_char_literal_unicode_escape_contains_braces(self) -> None:
        assert deltas(r"let c = '\u{1F600}';") == [0]

    def test_lifetime_is_not_a_char_literal(self) -> None:
        # `'a` opens no literal.  If it were treated as one, the `{` after it
        # would be swallowed and the fn body would never open.
        assert deltas("impl<'a> Foo<'a> for Bar<'a> {") == [1]

    def test_raw_string(self) -> None:
        assert deltas(r'let s = r#"{ not json"#;') == [0]

    def test_raw_string_spanning_lines(self) -> None:
        src = 'let s = r#"{\n   {\n"#; fn a() {'
        assert deltas(src) == [0, 0, 1]

    def test_byte_string(self) -> None:
        assert deltas('let b = b"{";') == [0]

    def test_plain_string_spanning_lines(self) -> None:
        # A raw newline inside a "..." literal is legal Rust.
        src = 'let s = "{\n  {\n"; fn a() {'
        assert deltas(src) == [0, 0, 1]

    def test_escaped_quote_does_not_end_the_string(self) -> None:
        assert deltas(r'let s = "\"{"; ') == [0]

    def test_identifier_ending_in_r_is_not_a_raw_string(self) -> None:
        # `foor"..."` is not valid Rust, but `4r` style suffixes and idents
        # ending in `r` are common enough that the boundary check matters.
        assert deltas('let counter = "{";') == [0]


class TestBracesThatAreCode:
    def test_plain_block(self) -> None:
        assert deltas("mod tests {") == [1]

    def test_close(self) -> None:
        assert deltas("}") == [-1]

    def test_several_on_one_line(self) -> None:
        assert deltas("#[test] fn a() {}") == [0]
        assert deltas("fn a() { if x { y() } }") == [0]

    def test_code_and_string_on_the_same_line(self) -> None:
        assert deltas('fn a() { let s = "{"; }') == [0]
        assert deltas('fn a() { let s = "{";') == [1]


class TestModuleBody:
    def test_module_containing_malformed_json_terminates(self) -> None:
        """The end-to-end shape of the failure: ``module_body`` must return."""
        lines = [
            "#[cfg(test)]",
            "mod tests {",
            "    #[test]",
            "    fn malformed_json_is_a_loud_error() {",
            '        let e = native_from_json("{not json").unwrap_err();',
            "    }",
            "}",
            "",
            "fn after() {}",
        ]
        body = g.module_body(lines, 1)
        assert body[0] == "mod tests {"
        assert body[-1] == "}"
        assert len(body) == 6

    def test_genuinely_unbalanced_source_still_raises(self) -> None:
        """The guard must stay loud for a real unclosed module."""
        lines = ["mod tests {", "    fn a() {", "    }"]
        with pytest.raises(SystemExit, match="unbalanced braces"):
            g.module_body(lines, 0)


class TestNestedModuleIdentity:
    def test_generated_name_includes_every_inline_ancestor(self) -> None:
        """R19 names must be identical to libtest names, not just callable."""
        source = """#[cfg(test)]
mod outer {
    mod tests {
        #[cfg(test)]
        mod frozen_dsn_tests {
            #[test]
            fn frozen_case() {}
        }
    }
}
"""
        rewritten, body_text, fns = g.rewrite_module(
            source, "dsn_types.rs", "frozen_dsn_tests"
        )

        assert body_text is None
        assert fns == [("frozen_case", [])]
        assert (
            '"dsn_types::outer::tests::frozen_dsn_tests::frozen_case"'
            in rewritten
        )
        assert '"dsn_types::frozen_dsn_tests::frozen_case"' not in rewritten
        assert (
            rewritten.count(
                "// --- BEGIN generated by scripts/gen_wasm_test_registry.py: "
                "frozen_dsn_tests ---"
            )
            == 1
        )
        assert (
            rewritten.count(
                "// --- END generated by scripts/gen_wasm_test_registry.py: "
                "frozen_dsn_tests ---"
            )
            == 1
        )

        rewritten_again, _, fns_again = g.rewrite_module(
            rewritten, "dsn_types.rs", "frozen_dsn_tests"
        )
        assert fns_again == fns
        assert rewritten_again == rewritten


class TestRealSource:
    def test_state_ser_module_is_brace_balanced(self) -> None:
        """The file the gate died on, parsed from disk."""
        path = _REPO_ROOT / "packages" / "temper-orchestration" / "src" / "state_ser.rs"
        if not path.exists():  # pragma: no cover - crate not checked out
            pytest.skip(f"{path} not present")
        lines = path.read_text().split("\n")
        decl = next(i for i, ln in enumerate(lines) if ln.rstrip() == "pub(crate) mod tests {")
        body = g.module_body(lines, decl)
        assert body[-1].rstrip() == "}"
        assert sum(g.brace_deltas(body)) == 0


class TestStdProcessExclusion:
    """`wasm32-unknown-unknown` has no process model, so a test module that
    reaches for one is native-only by construction.

    Found the hard way: fixing the brace counter registered
    ``subprocess_stage::tests`` for the first time, and all 7 of its tests
    trapped under Node with ``no pids on this platform``
    (``std/src/sys/process/unsupported.rs``).  The predicate keeps them out
    rather than listing them as expected failures -- that manifest is for
    divergences worth executing, and these cannot execute at all.
    """

    def _discover(self, tmp_path: Path, body: str) -> list:
        src = tmp_path / "src"
        src.mkdir()
        # `feature_gated_modules` reads lib.rs to find `#[cfg(feature = ...)]`
        # module declarations, so the crate root has to exist.
        (src / "lib.rs").write_text("pub mod thing;\n")
        (src / "thing.rs").write_text(body)
        return g.discover_eligible(src)

    def test_module_using_std_process_is_excluded(self, tmp_path: Path) -> None:
        found = self._discover(
            tmp_path,
            "#[cfg(test)]\nmod tests {\n"
            "    #[test]\n    fn a() { let _ = std::process::id(); }\n}\n",
        )
        assert [d.excluded for d in found] == ["std-process-no-wasm32"]

    def test_use_declaration_counts(self, tmp_path: Path) -> None:
        found = self._discover(
            tmp_path,
            "#[cfg(test)]\nmod tests {\n    use std::process::Command;\n"
            '    #[test]\n    fn a() { Command::new("x"); }\n}\n',
        )
        assert [d.excluded for d in found] == ["std-process-no-wasm32"]

    def test_ordinary_module_is_not_excluded(self, tmp_path: Path) -> None:
        found = self._discover(
            tmp_path,
            "#[cfg(test)]\nmod tests {\n    #[test]\n    fn a() { assert!(true); }\n}\n",
        )
        assert [d.excluded for d in found] == [None]

    def test_mention_in_a_comment_does_not_exclude(self, tmp_path: Path) -> None:
        # The predicate strips `//` before matching, same as PROPTEST_USE --
        # a module must not lose its tests because prose named the API.
        found = self._discover(
            tmp_path,
            "#[cfg(test)]\nmod tests {\n    // unlike std::process, this is pure\n"
            "    #[test]\n    fn a() { assert!(true); }\n}\n",
        )
        assert [d.excluded for d in found] == [None]

    def test_the_predicate_is_narrow(self) -> None:
        """It must exclude exactly one module across every gated crate.

        A predicate that quietly widened would shrink the wasm32 corpus with
        no failing test to say so -- the failure class this gate exists for.
        """
        excluded = []
        for name in sorted(g.CRATES):
            src = _REPO_ROOT / "packages" / name / "src"
            if not src.exists():  # pragma: no cover - layout differs
                continue
            excluded += [
                f"{name}:{d.rel}::{d.ident}"
                for d in g.discover_eligible(src)
                if d.excluded == "std-process-no-wasm32"
            ]
        assert excluded == ["temper-orchestration:subprocess_stage.rs::tests"]
