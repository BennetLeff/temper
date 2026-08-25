"""Differential test: Rust S-expression writer (temper_design_bundle_python
parse_engine.write_board_sexpr_py) round-trip parity on the corpus.

Wave 4, Phase 3 (formats/IO) -- the writer is the inverse of the
kiutils-exact tokenizer (`parse_engine.rs`); see `sexpr_writer.rs`'s module
doc for the design and its known limitations.

Acceptance criterion (D7 from the Phase 3 plan): **re-parse parity**, not
byte-identical output. The tokenizer normalizes whitespace, drops carets
outside strings, and collapses integral decimals to ints, so the written
bytes are not expected to match the input file -- but re-parsing the
written text must produce the SAME token tree as re-parsing the original.

The comparison uses `parse_engine.tokenize` on both sides: it returns the
top-level s-expression as a Python value (the same shape kiutils'
`parse_sexp` returns), so tree equality here is the Rust-tree equality
checked through the pyo3 boundary. Str and Bare both surface as `str`
across that boundary (see `atom_to_py`), so the two documented Rust-tree
limitations that only swap Str<->Bare are invisible to this test -- they are
covered by the Rust unit tests in `sexpr_writer.rs`, which compare the
`KiNode` trees directly.

A third property is asserted beyond tree equality: **write idempotence** --
writing the written text is a fixed point. The writer must be its own
normal form; anything else would mean the second write changed the tree
again.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb

_PARSE_ENGINE = _tdb.parse_engine

REPO_ROOT = Path(__file__).resolve().parents[4]
CORPUS = [
    ("temper", REPO_ROOT / "power_pcb_dataset" / "corpus" / "temper" / "temper.kicad_pcb"),
    ("minimal", REPO_ROOT / "power_pcb_dataset" / "corpus" / "minimal" / "minimal_board.kicad_pcb"),
    (
        "rp2040",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "rp2040_designguide" / "RP2040-Guide.kicad_pcb",
    ),
    (
        "bitaxe",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "bitaxe_ultra" / "bitaxeUltra.kicad_pcb",
    ),
    (
        "piantor",
        REPO_ROOT / "power_pcb_dataset" / "corpus" / "piantor_right" / "keyboard_pcb.kicad_pcb",
    ),
    ("pcb", REPO_ROOT / "pcb" / "temper.kicad_pcb"),
]


@pytest.mark.parametrize("name,path", CORPUS, ids=[c[0] for c in CORPUS])
def test_corpus_board_round_trip_parity(name: str, path):
    text = path.read_text()
    tree_original = _PARSE_ENGINE.tokenize(text)

    written = _PARSE_ENGINE.write_board_sexpr_py(text)
    tree_written = _PARSE_ENGINE.tokenize(written)

    assert tree_written == tree_original, (
        f"re-parsing the written {name} board changed the token tree "
        "(D7 re-parse parity violated)"
    )


@pytest.mark.parametrize("name,path", CORPUS, ids=[c[0] for c in CORPUS])
def test_corpus_board_write_is_idempotent(name: str, path):
    text = path.read_text()
    once = _PARSE_ENGINE.write_board_sexpr_py(text)
    twice = _PARSE_ENGINE.write_board_sexpr_py(once)
    assert twice == once, (
        f"writing the written {name} board is not a fixed point; "
        "the writer is not in normal form"
    )


@pytest.mark.parametrize(
    "fixture",
    [
        # Head atom + leading atoms on the opening line; children indented.
        '(kicad_pcb (version 20211014) (general (thickness 1.6)) (net 1 "+15V"))',
        # Integral decimals collapse to ints (5.0 -> 5) and stay ints.
        '(pad "1" thru_hole circle (at 10 20 90.0) (size 3.0 3.0) (drill 1.5))',
        # String content with an escaped quote round-trips through `\"`.
        '(descr "a \\"quoted\\" bit")',
        # Backslash sequences that are NOT escapes (KiCad's \\n) survive.
        '(text "LINE1\\nLINE2" (at 0 0))',
        # The verbatim (offset ...) drill sub-list quirk.
        '(pad "1" thru_hole circle (drill (offset 0 1)))',
        # A caret outside a string is dropped consistently (a^b -> a b).
        "(x a^b)",
        # Empty document.
        "()",
        # Float rendered in fixed notation.
        "(x 0.00001 0.035 96.95)",
    ],
    ids=[
        "header-and-indent",
        "integral-decimals",
        "escaped-quote",
        "backslash-sequence",
        "drill-offset-quirk",
        "caret-outside-string",
        "empty-document",
        "fixed-notation-floats",
    ],
)
def test_adversarial_tokens_round_trip(fixture: str):
    tree_original = _PARSE_ENGINE.tokenize(fixture)
    written = _PARSE_ENGINE.write_board_sexpr_py(fixture)
    tree_written = _PARSE_ENGINE.tokenize(written)
    assert tree_written == tree_original
    assert _PARSE_ENGINE.write_board_sexpr_py(written) == written


def test_malformed_input_fails_closed():
    # Unbalanced parens must raise (kiutils raises there too) -- never
    # return a half-written document.
    with pytest.raises(ValueError):
        _PARSE_ENGINE.write_board_sexpr_py("(kicad_pcb (version 20211014)")
    with pytest.raises(ValueError):
        _PARSE_ENGINE.write_board_sexpr_py("(a b))")


def test_embed_title_block_comment_creates_and_overwrites():
    content = "(kicad_pcb (version 20211014) (general (thickness 1.6)) (paper \"A4\"))"
    out = _PARSE_ENGINE.embed_title_block_comment_py(content, 9, "provenance: board=abc")
    assert "(title_block" in out
    assert '(comment 9 "provenance: board=abc")' in out
    # Re-parse parity after the mutation.
    assert _PARSE_ENGINE.tokenize(out) != _PARSE_ENGINE.tokenize(content)
    # Overwrite the same slot.
    out2 = _PARSE_ENGINE.embed_title_block_comment_py(out, 9, "provenance: board=def")
    assert '(comment 9 "provenance: board=def")' in out2
    assert "board=abc" not in out2
    # A different slot is preserved.
    out3 = _PARSE_ENGINE.embed_title_block_comment_py(out, 2, "keep")
    assert '(comment 9 "provenance: board=abc")' in out3
    assert '(comment 2 "keep")' in out3


def test_embed_title_block_comment_fails_closed_on_non_board():
    with pytest.raises(ValueError):
        _PARSE_ENGINE.embed_title_block_comment_py("(not_a_board (x 1))", 9, "x")
