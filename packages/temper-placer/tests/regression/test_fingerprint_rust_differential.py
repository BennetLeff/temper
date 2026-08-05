"""Differential test: fingerprint compute kernels in Rust
(``temper_design_bundle_python.input_fingerprint`` / ``source_fingerprint``
/ ``should_skip``) vs the pinned Python oracle (Wave 4, Phase 4 — regression
slice).

``temper_placer/regression/fingerprint.py`` moves its hashing/decision
compute — the SHA-256 update-sequence for input fingerprints (existing file
bytes vs. missing-path strings, then the seed/epochs suffixes), the
``"\\n"``-join + SHA-256 for source fingerprints, and the cache-skip
decision — into ``temper-design-bundle``. The pre-migration module is pinned
verbatim as the oracle (``_fingerprint_py_oracle.py``, commit ``0a29f15e3``).

Design boundaries, argued in the migrated module and
``packages/temper-design-bundle/VERIFICATION.md``:

- File I/O stays Python-side: the delegation module reads the input files,
  walks ``SOURCE_FINGERPRINT_DIRS`` for ``*.py``, and computes the per-file
  hash with the crate's own ``sha256_hex``; the kernels operate on the
  marshalled byte/string parts and the pre-joined entry lines.
- The input-parts order is the oracle's ``sorted([pcb, constraints,
  baseline])`` path sort (Python Path sort), performed in the delegation
  module and preserved by the kernel.
- SHA-256 is standardized — ``hashlib.sha256`` and the crate's ``sha2``
  digest agree by construction (pinned anyway by the differential).
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb

import tests.regression._fingerprint_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
INPUT_FINGERPRINT = _tdb.input_fingerprint
SOURCE_FINGERPRINT = _tdb.source_fingerprint
SHOULD_SKIP = _tdb.should_skip

from temper_placer.regression.fingerprint import (  # noqa: E402
    compute_input_fingerprint as ShimInputFp,
    compute_source_fingerprint as ShimSourceFp,
    should_skip as ShimShouldSkip,
)


# ---------------------------------------------------------------------------
# R1a — differential
# ---------------------------------------------------------------------------


def test_differential_input_fingerprint_direct():
    """Drive the kernel directly: parts are (Some(bytes) | None, path-str)
    in the oracle's sorted-path order."""
    rng = random.Random(0xF1A5)
    for _ in range(200):
        n = rng.randint(0, 4)
        parts = []
        ref = hashlib.sha256()
        for i in range(n):
            exists = rng.random() < 0.6
            path_str = f"/tmp/pcb_{i}.kicad_pcb"
            if exists:
                data = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 64)))
                parts.append((data, path_str))
                ref.update(data)
            else:
                parts.append((None, path_str))
                ref.update(path_str.encode())
        seed = rng.randint(0, 10**6)
        epochs = rng.randint(0, 10**6)
        ref.update(f"seed:{seed}".encode())
        ref.update(f"epochs:{epochs}".encode())
        assert INPUT_FINGERPRINT(parts, seed, epochs) == ref.hexdigest()


def test_differential_input_fingerprint_end_to_end(tmp_path):
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_bytes(b"board")
    constraints = tmp_path / "constraints.yaml"
    constraints.write_bytes(b"constraints")
    missing = tmp_path / "baseline.json"  # does not exist
    for seed, epochs in [(42, 5), (0, 0), (7, 100)]:
        o = _oracle.compute_input_fingerprint(pcb, constraints, missing, seed, epochs)
        s = ShimInputFp(pcb, constraints, missing, seed, epochs)
        assert s == o
        # oracle reference: the verbatim algorithm
        ref = hashlib.sha256()
        for path in sorted([pcb, constraints, missing]):
            if path.exists():
                ref.update(path.read_bytes())
            else:
                ref.update(str(path).encode())
        ref.update(f"seed:{seed}".encode())
        ref.update(f"epochs:{epochs}".encode())
        assert s == ref.hexdigest()


def test_differential_input_fingerprint_all_missing(tmp_path):
    a = tmp_path / "a.kicad_pcb"
    b = tmp_path / "b.yaml"
    c = tmp_path / "c.json"
    o = _oracle.compute_input_fingerprint(a, b, c, 1, 1)
    s = ShimInputFp(a, b, c, 1, 1)
    assert s == o
    assert s != _oracle.compute_input_fingerprint(b, a, c, 1, 1)  # order matters


def test_differential_source_fingerprint():
    entries = [
        "packages/temper-placer/src/temper_placer/regression/a.py:abc123",
        "packages/temper-placer/src/temper_placer/regression/b.py:def456",
        "",
    ]
    # kernel vs oracle-ref (the oracle's compute_source_fingerprint needs a
    # real repo root, so the join+hash ref is transcribed here)
    joined = "\n".join(entries)
    assert SOURCE_FINGERPRINT(entries) == hashlib.sha256(joined.encode()).hexdigest()
    assert SOURCE_FINGERPRINT([]) == hashlib.sha256(b"").hexdigest()


def test_differential_source_fingerprint_end_to_end(tmp_path, monkeypatch):
    """Build a fake src tree and compare the full compute against the oracle."""
    from temper_placer.regression.fingerprint import SOURCE_FINGERPRINT_DIRS

    for rel in SOURCE_FINGERPRINT_DIRS:
        d = tmp_path / rel
        d.mkdir(parents=True, exist_ok=True)
    (tmp_path / SOURCE_FINGERPRINT_DIRS[0] / "z.py").write_text("z")
    (tmp_path / SOURCE_FINGERPRINT_DIRS[0] / "a.py").write_text("a")
    (tmp_path / SOURCE_FINGERPRINT_DIRS[1] / "b.py").write_text("b")
    o = _oracle.compute_source_fingerprint(tmp_path)
    s = ShimSourceFp(tmp_path)
    assert s == o
    # a content change must change the fingerprint
    (tmp_path / SOURCE_FINGERPRINT_DIRS[0] / "a.py").write_text("a2")
    assert ShimSourceFp(tmp_path) != s


def test_differential_source_fingerprint_missing_dir(tmp_path):
    o = _oracle.compute_source_fingerprint(tmp_path)  # no dirs exist
    s = ShimSourceFp(tmp_path)
    assert s == o
    assert s == hashlib.sha256(b"").hexdigest()


def test_differential_should_skip():
    cache = {
        "version": 1,
        "boards": {
            "b1": {"input_fingerprint": "in1", "source_fingerprint": "src1"},
        },
    }
    assert _oracle.should_skip("b1", "in1", "src1", cache) is True
    assert _oracle.should_skip("b1", "in2", "src1", cache) is False
    assert _oracle.should_skip("b1", "in1", "src2", cache) is False
    assert _oracle.should_skip("missing", "in1", "src1", cache) is False
    assert _oracle.should_skip("b1", "in1", "src1", {}) is False
    # empty board entry (falsy) -> no skip
    cache["boards"]["b1"] = {}
    assert _oracle.should_skip("b1", "in1", "src1", cache) is False
    # missing fingerprint keys -> no skip
    cache["boards"]["b1"] = {"last_pass_commit": "abc"}
    assert _oracle.should_skip("b1", "in1", "src1", cache) is False


def test_differential_should_skip_shim():
    """The shim's should_skip must agree with the oracle on the same cache."""
    cases = [
        ({"boards": {"b1": {"input_fingerprint": "i", "source_fingerprint": "s"}}}, True),
        ({"boards": {"b1": {"input_fingerprint": "x", "source_fingerprint": "s"}}}, False),
        ({"boards": {"b1": {}}}, False),
        ({"boards": {}}, False),
        ({}, False),
    ]
    for cache, expected in cases:
        o = _oracle.should_skip("b1", "i", "s", cache)
        s = ShimShouldSkip("b1", "i", "s", cache)
        assert o == expected
        assert s == o


# ---------------------------------------------------------------------------
# R1d — metamorphic relations (>=3, honestly bounded)
# ---------------------------------------------------------------------------


def test_mr1_fingerprint_changes_with_any_input_byte():
    """Flipping one byte in any existing input part changes the digest."""
    rng = random.Random(99)
    parts = []
    for i in range(3):
        parts.append((bytes(rng.getrandbits(8) for _ in range(16)), f"/p/{i}.bin"))
    base = INPUT_FINGERPRINT(parts, 1, 2)
    for i in range(3):
        mutated = list(parts)
        data = bytearray(parts[i][0])
        data[0] ^= 0xFF
        mutated[i] = (bytes(data), parts[i][1])
        assert INPUT_FINGERPRINT(mutated, 1, 2) != base


def test_mr2_missing_path_string_is_sensitive():
    """The path string is hashed for a missing file: changing it changes the
    digest (proving the kernel hashes the path, not nothing)."""
    a = INPUT_FINGERPRINT([(None, "/tmp/x.pcb")], 1, 1)
    b = INPUT_FINGERPRINT([(None, "/tmp/y.pcb")], 1, 1)
    assert a != b
    # and an existing file's content, not its path
    c = INPUT_FINGERPRINT([(b"data", "/tmp/z.pcb")], 1, 1)
    d = INPUT_FINGERPRINT([(b"data", "/tmp/other.pcb")], 1, 1)
    assert c == d


def test_mr3_seed_epochs_sensitive():
    a = INPUT_FINGERPRINT([], 1, 1)
    assert a != INPUT_FINGERPRINT([], 2, 1)
    assert a != INPUT_FINGERPRINT([], 1, 2)


def test_mr4_should_skip_requires_both_matches():
    """Flipping either fingerprint individually makes should_skip False."""
    cache = {"boards": {"b": {"input_fingerprint": "i", "source_fingerprint": "s"}}}
    assert SHOULD_SKIP("b", "i", "s", cache) is True
    assert SHOULD_SKIP("b", "i2", "s", cache) is False
    assert SHOULD_SKIP("b", "i", "s2", cache) is False


# ---------------------------------------------------------------------------
# R1c — non-vacuous properties (>=5)
# ---------------------------------------------------------------------------


def test_prop1_digest_is_64_hex_chars():
    for args in [([], 0, 0), ([(b"x", "/p")], 1, 2)]:
        d = INPUT_FINGERPRINT(*args)
        assert len(d) == 64
        int(d, 16)  # hex


def test_prop2_deterministic():
    parts = [(b"abc", "/p"), (None, "/q")]
    assert INPUT_FINGERPRINT(parts, 5, 5) == INPUT_FINGERPRINT(parts, 5, 5)


def test_prop3_empty_parts_matches_pure_suffixes():
    ref = hashlib.sha256()
    ref.update(b"seed:7")
    ref.update(b"epochs:3")
    assert INPUT_FINGERPRINT([], 7, 3) == ref.hexdigest()


def test_prop4_source_fingerprint_join_is_nl_separated():
    ref = hashlib.sha256(b"a\nb").hexdigest()
    assert SOURCE_FINGERPRINT(["a", "b"]) == ref
    # a joined-with-comma would give a different digest
    assert SOURCE_FINGERPRINT(["a", "b"]) != hashlib.sha256(b"a,b").hexdigest()


def test_prop5_empty_source_fingerprint_is_empty_sha256():
    assert SOURCE_FINGERPRINT([]) == hashlib.sha256(b"").hexdigest()


def test_prop6_should_skip_missing_board_is_false():
    assert SHOULD_SKIP("nope", "i", "s", {"boards": {"b": {}}}) is False
    assert SHOULD_SKIP("nope", "i", "s", None) is False
