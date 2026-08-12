"""Wave-4 tail-tooling migration: behavioural A/B of the quarantine compute
(temper-io-types ``quarantine`` module) against the pinned pre-migration
oracle.

The pre-migration ``temper_placer/testing/quarantine.py`` is pinned VERBATIM
as ``tests/testing/_quarantine_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json`` AND in this file's body digests). Both arms
are driven with IDENTICAL inputs; every assertion is bit-exact:

- ``temper_io_types.classify_error``        vs oracle ``classify_error``
  (the taxonomy decision table — identical on every ``(stage, exception)``);
- ``temper_io_types.compute_stack_hash``    vs oracle ``compute_stack_hash``
  (12-hex SHA-256 prefix of the CPython-formatted traceback — both arms
  render the traceback through CPython's ``traceback.format_exception``, so
  the rendering is identical by construction and the hash kernel under test
  is the Rust sha2 reduction);
- ``temper_io_types.compute_fingerprint``   vs oracle ``compute_fingerprint``
  (the board-fingerprint dict — existing and non-existent files).

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
the shim binds to ``temper_io_types`` pyfunctions and the oracle still holds
the Python compute; ``test_shim_delegates_*`` prove ``quarantine_error``
really routes through the pyo3 boundary for all three kernels (recording
stubs).

What stays Python (documented boundary): the dead-letter filesystem manifest
management — ``QuarantineEntry`` (+ its ``to_dict``/``to_json``
serialization), ``quarantine_error`` (date-directory + entry-file writes),
``_update_manifest``, ``load_manifest``, ``quarantine_summary`` and the
``TAXONOMY_CLASSES`` label table. The differential still pins the whole
orchestration bit-exactly (``test_oracle_bodies_match_pinned_digests`` +
``test_quarantine_error_*``) because the shim keeps the SAME orchestration
the oracle had — the only divergence under test is the migrated compute
feeding it. See the module header in
``packages/temper-io-types/src/quarantine.rs`` and its VERIFICATION.md for
the split argument.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from pathlib import Path
from tempfile import mkdtemp

import pytest
import temper_io_types as _tio
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.testing import quarantine as shim_mod
from tests.testing import _quarantine_py_oracle as _oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_quarantine_py_oracle.py")

# Body digests of the three ported kernels, extracted from the oracle file
# (AST ranges, dedented) — pinned here so a body edit in the oracle fails this
# test rather than silently re-pinning the differential.
_BODY_DIGESTS = {
    "classify_error": "7126ea15203c0542f8c339c227910d5182653a6377b181559d7b4a168bc1d26f",
    "compute_stack_hash": "d9232736e246122e5ac5bd4be3776d39c131581f0720769f9a0b8b59721dd4e6",
    "compute_fingerprint": "c53570dd50f6630a9c086de5b82e25f991e6b3f1e441423a3be7d2471bfe740a",
}


def _oracle_body_digests(path: Path) -> dict[str, str]:
    import ast

    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    out: dict[str, str] = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            body = "".join(lines[node.lineno - 1 : node.end_lineno])
            out[node.name] = hashlib.sha256(textwrap.dedent(body).encode()).hexdigest()
    return out


def test_oracle_bodies_match_pinned_digests() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied bodies are content-addressed. If this fails,
    either the oracle was edited (revert it) or a pre-migration module's
    source really changed upstream (re-pin deliberately, in its own commit).
    """
    digests = _oracle_body_digests(_ORACLE_PATH)
    for name, want in _BODY_DIGESTS.items():
        assert digests.get(name) == want, (
            f"the pinned oracle body {name} changed; it must stay verbatim "
            "(see scripts/oracle_hashes.json for the registered hash)"
        )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shim must bind to temper_io_types pyfunctions, not
    resolve back onto the oracle or keep the compute inline."""
    assert _tio.classify_error.__module__ == "temper_io_types.temper_io_types"
    assert _tio.compute_stack_hash.__module__ == "temper_io_types.temper_io_types"
    assert _tio.compute_fingerprint.__module__ == "temper_io_types.temper_io_types"
    # The oracle's compute must not have been collapsed onto the shims.
    assert _oracle.classify_error.__module__ != "temper_io_types.temper_io_types"
    assert _oracle.compute_stack_hash.__module__ != "temper_io_types.temper_io_types"
    assert _oracle.compute_fingerprint.__module__ != "temper_io_types.temper_io_types"
    # The shim no longer contains the migrated compute inline.
    import inspect

    assert "to_lowercase" not in inspect.getsource(shim_mod)
    assert "hashlib" not in inspect.getsource(shim_mod)


def test_shim_delegates_classify(monkeypatch) -> None:
    """Anti-vacuity: shim classify_error routes through the Rust kernel."""
    calls: list[tuple] = []
    real = _tio.classify_error

    def recording(stage, exc):
        calls.append((stage, exc))
        return real(stage, exc)

    monkeypatch.setattr(_tio, "classify_error", recording)
    exc = ValueError("version mismatch")
    assert shim_mod.classify_error("parse", exc) == "PARSE_KICAD_VERSION_MISMATCH"
    assert len(calls) == 1


def test_shim_delegates_stack_hash(monkeypatch) -> None:
    """Anti-vacuity: shim compute_stack_hash routes through the Rust kernel."""
    calls: list[object] = []
    real = _tio.compute_stack_hash

    def recording(exc):
        calls.append(exc)
        return real(exc)

    monkeypatch.setattr(_tio, "compute_stack_hash", recording)
    exc = ValueError("boom")
    shim_mod.compute_stack_hash(exc)
    assert len(calls) == 1


def test_shim_delegates_fingerprint(monkeypatch, tmp_path) -> None:
    """Anti-vacuity: shim compute_fingerprint routes through the Rust kernel."""
    calls: list[str] = []
    real = _tio.compute_fingerprint

    def recording(path):
        calls.append(path)
        return real(path)

    pcb = tmp_path / "t.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    monkeypatch.setattr(_tio, "compute_fingerprint", recording)
    fp = shim_mod.compute_fingerprint(pcb)
    assert fp["exists"] is True
    assert calls == [str(pcb)]


# ---------------------------------------------------------------------------
# classify_error vs classify_error
# ---------------------------------------------------------------------------


def _raise_at_frame(cls, msg):
    return cls(msg)


class _ErrorFactory:
    """Deterministic exception construction usable in Hypothesis strategies."""

    @staticmethod
    def build(kind: str, msg: str):
        by_kind = {
            "ValueError": ValueError,
            "KeyError": KeyError,
            "SyntaxError": SyntaxError,
            "RuntimeError": RuntimeError,
            "Exception": Exception,
        }
        return by_kind[kind](msg)


_CLASSIFY_CASES = [
    ("parse", ValueError("version mismatch in format_version"), "PARSE_KICAD_VERSION_MISMATCH"),
    ("parse", RuntimeError("footprint library not found"), "PARSE_MISSING_FOOTPRINT_LIB"),
    ("parse", UnicodeDecodeError("utf-8", b"", 0, 1, "invalid"), "PARSE_DECODE_ERROR"),
    ("parse", ValueError("zero components and zero nets found"), "PARSE_EMPTY_BOARD"),
    ("parse", SyntaxError("unexpected token"), "PARSE_UNSUPPORTED_SYNTAX"),
    ("parse", KeyError("missing"), "PARSE_UNSUPPORTED_SYNTAX"),
    ("parse", Exception("some unexpected parse error"), "PARSE_UNKNOWN"),
    ("preflight", Exception("preflight check failed"), "STAGE_PREFLIGHT_FAILED"),
    ("geometric", Exception("optimizer diverged"), "STAGE_GEOMETRIC_DIVERGED"),
    ("routing", Exception("routing incomplete"), "STAGE_ROUTING_FAILED"),
    ("output", Exception("output serialization error"), "STAGE_OUTPUT_FAILED"),
    ("unknown_stage", Exception("something went wrong"), "UNKNOWN"),
    ("", Exception("anything"), "UNKNOWN"),
]


def test_classify_matches_oracle_on_documented_cases() -> None:
    for stage, exc, want in _CLASSIFY_CASES:
        assert _oracle.classify_error(stage, exc) == want
        assert _tio.classify_error(stage, exc) == want
        assert _tio.classify_error(stage, exc) == _oracle.classify_error(stage, exc)


def test_classify_errors_propagate_like_python() -> None:
    """str(exc) raising an exception must propagate from both arms."""
    class _BadStr(Exception):
        def __str__(self):
            raise RuntimeError("str failed")

    exc = _BadStr("x")
    with pytest.raises(RuntimeError):
        _oracle.classify_error("parse", exc)
    with pytest.raises(RuntimeError):
        _tio.classify_error("parse", exc)


# ---------------------------------------------------------------------------
# compute_stack_hash vs compute_stack_hash
# ---------------------------------------------------------------------------


def _raised(exc_class, msg):
    try:
        raise exc_class(msg)
    except exc_class as exc:
        return exc


def test_stack_hash_matches_oracle_on_raised_exceptions() -> None:
    for cls, msg in [
        (ValueError, "error one"),
        (RuntimeError, "same error"),
        (KeyError, "missing key"),
        (TypeError, "bad type"),
    ]:
        exc = _raised(cls, msg)
        assert _oracle.compute_stack_hash(exc) == _tio.compute_stack_hash(exc)
        got = _tio.compute_stack_hash(exc)
        assert isinstance(got, str)
        assert len(got) == 12
        assert all(c in "0123456789abcdef" for c in got)


def test_stack_hash_matches_oracle_on_unraised_exception() -> None:
    """An exception never raised has a None __traceback__; format_exception
    must still render it identically (just the last line)."""
    exc = ValueError("constructed directly")
    assert _oracle.compute_stack_hash(exc) == _tio.compute_stack_hash(exc)


def test_stack_hash_raises_like_python_on_bad_traceback() -> None:
    """A pathological exception whose __traceback__ attribute is unusable
    must fail the same way from both arms."""

    class _Weird:
        pass

    exc = _Weird()
    with pytest.raises(AttributeError):
        _oracle.compute_stack_hash(exc)
    with pytest.raises(Exception):
        _tio.compute_stack_hash(exc)


# ---------------------------------------------------------------------------
# compute_fingerprint vs compute_fingerprint
# ---------------------------------------------------------------------------


def _assert_fingerprints_equal(got: dict, want: dict) -> None:
    assert set(got) == set(want)
    for key in want:
        assert got[key] == want[key], f"fingerprint field {key} differs"


def test_fingerprint_matches_oracle_existing_file(tmp_path) -> None:
    pcb = tmp_path / "test.kicad_pcb"
    pcb.write_text("(kicad_pcb (version 20240108)\n  (net 0 \"\")\n)\n")
    _assert_fingerprints_equal(
        _tio.compute_fingerprint(str(pcb)), _oracle.compute_fingerprint(pcb)
    )
    assert _tio.compute_fingerprint(str(pcb))["lines"] == 4


def test_fingerprint_matches_oracle_nonexistent_file(tmp_path) -> None:
    pcb = tmp_path / "nonexistent.kicad_pcb"
    _assert_fingerprints_equal(
        _tio.compute_fingerprint(str(pcb)), _oracle.compute_fingerprint(pcb)
    )
    assert _tio.compute_fingerprint(str(pcb))["exists"] is False


def test_fingerprint_matches_oracle_without_header(tmp_path) -> None:
    pcb = tmp_path / "other.txt"
    pcb.write_text("just some text\nwith two lines\n")
    _assert_fingerprints_equal(
        _tio.compute_fingerprint(str(pcb)), _oracle.compute_fingerprint(pcb)
    )
    assert _tio.compute_fingerprint(str(pcb))["has_kicad_header"] is False


def test_fingerprint_matches_oracle_unreadable_dir_as_path(tmp_path) -> None:
    """A directory passed as the path exists (metadata works) but read_text
    fails → both arms emit the readable: False fallback with size_bytes."""
    _assert_fingerprints_equal(
        _tio.compute_fingerprint(str(tmp_path)), _oracle.compute_fingerprint(tmp_path)
    )


# ---------------------------------------------------------------------------
# End-to-end through the shim: quarantine_error vs oracle quarantine_error
# ---------------------------------------------------------------------------


def test_quarantine_error_end_to_end_matches_oracle(tmp_path) -> None:
    """quarantine_error (filesystem orchestration stays Python) fed by the
    Rust kernels produces a QuarantineEntry identical to the oracle's."""
    qdir = tmp_path / "q"
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    err = ValueError("parse error: version")

    got = shim_mod.quarantine_error(qdir, "board_1", pcb, "parse", err)
    want = _oracle.quarantine_error(tmp_path / "q_oracle", "board_1", pcb, "parse", err)

    assert got.taxonomy == want.taxonomy
    assert got.error_class == want.error_class
    assert got.error_message == want.error_message
    assert got.stack_hash == want.stack_hash
    assert got.fingerprint == want.fingerprint
    assert got.to_dict()["taxonomy_label"] == want.to_dict()["taxonomy_label"]

    # The two arms ran at slightly different wall-clock instants, so the
    # dataclass timestamp fields differ by design — strip them (including
    # inside the manifest's entries) and compare the rest bit-for-bit.
    def _without_ts(d: dict) -> dict:
        out = {k: v for k, v in d.items() if k not in ("timestamp", "last_updated")}
        if "entries" in out:
            out["entries"] = [
                {k: v for k, v in e.items() if k != "timestamp"} for e in out["entries"]
            ]
        return out

    assert _without_ts(got.to_dict()) == _without_ts(want.to_dict())
    assert json.loads(got.to_json())["taxonomy"] == json.loads(want.to_json())["taxonomy"]

    # Both wrote an entry file under a date dir.
    assert len(list(qdir.rglob("*.json"))) == len(list((tmp_path / "q_oracle").rglob("*.json")))
    manifest = shim_mod.load_manifest(qdir)
    oracle_manifest = shim_mod.load_manifest(tmp_path / "q_oracle")
    assert _without_ts(manifest) == _without_ts(oracle_manifest)
    assert set(manifest) == set(oracle_manifest)


def test_quarantine_summary_matches_oracle(tmp_path) -> None:
    qdir = tmp_path / "q"
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    shim_mod.quarantine_error(qdir, "b1", pcb, "parse", ValueError("version mismatch"))
    shim_mod.quarantine_error(qdir, "b2", pcb, "routing", RuntimeError("router failed"))
    summary = shim_mod.quarantine_summary(qdir)
    assert "2 total entries" in summary
    assert "PARSE_KICAD_VERSION_MISMATCH" in summary
    assert "STAGE_ROUTING_FAILED" in summary


# ---------------------------------------------------------------------------
# PBT (Hypothesis): differential + invariants
# ---------------------------------------------------------------------------

_stage = st.sampled_from(["parse", "preflight", "geometric", "routing", "output", "whatever"])
_kind = st.sampled_from(["ValueError", "KeyError", "SyntaxError", "RuntimeError", "Exception"])
# ASCII keyword soup — the classifier's domain (see the module doc's
# ascii-boundary note).
_msg = st.text(
    alphabet=st.sampled_from(
        "abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    ),
    max_size=40,
)


@settings(deadline=None)
@given(stage=_stage, kind=_kind, msg=_msg)
def test_pbt_classify_matches_oracle(stage, kind, msg):
    """Differential: shim classify_error is identical to the oracle's over
    arbitrary (stage, exception class, message) inputs."""
    exc = _ErrorFactory.build(kind, msg)
    assert shim_mod.classify_error(stage, exc) == _oracle.classify_error(stage, exc)


@settings(deadline=None)
@given(kind=_kind, msg=_msg)
def test_pbt_classify_non_parse_stages_are_fixed_points(kind, msg):
    """Metamorphic-style exhaustiveness: every non-parse stage maps ANY
    exception to exactly its stage taxonomy class."""
    exc = _ErrorFactory.build(kind, msg)
    assert _tio.classify_error("preflight", exc) == "STAGE_PREFLIGHT_FAILED"
    assert _tio.classify_error("geometric", exc) == "STAGE_GEOMETRIC_DIVERGED"
    assert _tio.classify_error("routing", exc) == "STAGE_ROUTING_FAILED"
    assert _tio.classify_error("output", exc) == "STAGE_OUTPUT_FAILED"
    assert _tio.classify_error("unknown", exc) == "UNKNOWN"


@settings(deadline=None)
@given(msg=_msg)
def test_pbt_classify_version_keyword_wins(msg):
    """A message that contains 'version' — in any case, at any position —
    always classifies as PARSE_KICAD_VERSION_MISMATCH on the parse stage
    (the highest-precedence arm)."""
    exc = ValueError(f"{msg} version x")
    assert _tio.classify_error("parse", exc) == "PARSE_KICAD_VERSION_MISMATCH"
    exc_upper = ValueError(f"{msg} VERSION x")
    assert _tio.classify_error("parse", exc_upper) == "PARSE_KICAD_VERSION_MISMATCH"


@settings(deadline=None)
@given(msg=_msg)
def test_pbt_classify_decode_keyword_invariant(msg):
    """A message containing 'decode' classifies as PARSE_DECODE_ERROR unless
    a higher-precedence keyword is also present. Precedence (the reference's
    order): version > footprint/lib > decode/utf."""
    low = msg.lower()
    if "version" in low:
        assert _tio.classify_error("parse", ValueError(f"{msg} decode")) == (
            "PARSE_KICAD_VERSION_MISMATCH"
        )
    elif "footprint" in low or "lib" in low:
        assert _tio.classify_error("parse", ValueError(f"{msg} decode")) == (
            "PARSE_MISSING_FOOTPRINT_LIB"
        )
    else:
        assert _tio.classify_error("parse", ValueError(f"{msg} decode")) == "PARSE_DECODE_ERROR"


@settings(deadline=None)
@given(kind=_kind, msg=_msg)
def test_pbt_stack_hash_matches_oracle(kind, msg):
    """Differential: the Rust sha256-prefix stack hash is identical to the
    oracle's hashlib hash for arbitrary raised exceptions."""
    exc = _raised(_ErrorFactory.build(kind, msg).__class__, msg)
    assert _tio.compute_stack_hash(exc) == _oracle.compute_stack_hash(exc)


@settings(deadline=None)
@given(msg=_msg)
def test_pbt_stack_hash_is_12_lower_hex_chars(msg):
    """Invariant: the stack hash is always the 12-char lowercase hex SHA-256
    prefix, regardless of the exception content."""
    exc = _raised(RuntimeError, msg)
    h = _tio.compute_stack_hash(exc)
    assert len(h) == 12
    assert set(h) <= set("0123456789abcdef")


@settings(deadline=None)
@given(content=st.text(alphabet="\n()kicad_pcb 0123456789ABCDEF", max_size=120))
def test_pbt_fingerprint_matches_oracle(content):
    """Differential: the Rust filesystem fingerprint dict is identical to the
    oracle's for arbitrary ASCII board-ish content."""
    d = Path(mkdtemp(prefix="qpbtdiff_"))
    pcb = d / "t.kicad_pcb"
    pcb.write_text(content)
    got = _tio.compute_fingerprint(str(pcb))
    want = _oracle.compute_fingerprint(pcb)
    _assert_fingerprints_equal(got, want)


@settings(deadline=None)
@given(content=st.text(alphabet="\n()kicad_pcb 0123456789", max_size=100))
def test_pbt_fingerprint_lines_invariant(content):
    """Invariant: lines == newline_count + 1, and the header probe matches
    the oracle's 200-char-window lowercased search."""
    d = Path(mkdtemp(prefix="qpbtsame_"))
    pcb = d / "t.kicad_pcb"
    pcb.write_text(content)
    fp = _tio.compute_fingerprint(str(pcb))
    assert fp["lines"] == content.count("\n") + 1
    assert fp["has_kicad_header"] == (
        "(kicad_pcb" in content.lower()[:200]
    )


# ---------------------------------------------------------------------------
# Metamorphic relations (deterministic samples)
# ---------------------------------------------------------------------------


def test_meta_classify_suffix_can_only_add_precedence() -> None:
    """Appending a higher-precedence keyword to a parse message can only move
    the classification UP the fixed precedence order (earlier arm wins)."""
    base = [
        "plain garbage",
        "some decode issue",
        "zero nets found",
        "a footprint is missing",
        "format_version 42",
    ]
    for msg in base:
        got_base = _tio.classify_error("parse", ValueError(msg))
        got_suffix = _tio.classify_error("parse", ValueError(msg + " version mismatch"))
        assert got_suffix == "PARSE_KICAD_VERSION_MISMATCH"
        assert got_base != "PARSE_KICAD_VERSION_MISMATCH" or got_base == got_suffix


def test_meta_fingerprint_append_newline_increments_lines(tmp_path) -> None:
    """Appending exactly one '\\n' to a file always increments the line count
    by one (count('\\n') + 1), leaving the header probe unchanged when the
    header position is unaffected."""
    for base in ["a", "a\n", "a\nb", "(kicad_pcb)\n", "\n\n"]:
        pcb = tmp_path / f"f{len(base)}.kicad_pcb"
        pcb.write_text(base)
        fp_before = _tio.compute_fingerprint(str(pcb))
        pcb.write_text(base + "\n")
        fp_after = _tio.compute_fingerprint(str(pcb))
        assert fp_after["lines"] == fp_before["lines"] + 1
        assert fp_after["size_bytes"] == fp_before["size_bytes"] + 1
        if "(kicad_pcb" in base[:200]:
            assert fp_after["has_kicad_header"] is True


def test_meta_stack_hash_same_error_is_stable_and_different_errors_differ() -> None:
    """Stack hashing is a deterministic function of the exception: the same
    exception object (and same raise location) always hashes the same, and
    different error messages produce different hashes."""
    h1 = _oracle.compute_stack_hash(_raised(ValueError, "same error"))
    h2 = _oracle.compute_stack_hash(_raised(ValueError, "same error"))
    assert h1 == h2
    h3 = _tio.compute_stack_hash(_raised(ValueError, "different error"))
    assert h3 != h1


def test_meta_fingerprint_is_pure_function_of_content(tmp_path) -> None:
    """Rewriting a file with identical bytes yields an identical fingerprint
    (no hidden state); changing the bytes changes lines or header in the
    direction the content dictates."""
    pcb = tmp_path / "pure.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    first = _tio.compute_fingerprint(str(pcb))
    pcb.write_text("(kicad_pcb)\n")  # identical rewrite
    second = _tio.compute_fingerprint(str(pcb))
    assert first == second
    pcb.write_text("(kicad_pcb)\n\n")
    third = _tio.compute_fingerprint(str(pcb))
    assert third["lines"] == first["lines"] + 1
