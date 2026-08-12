"""Wave-4 tail-tooling migration: behavioural A/B of the regression
golden-manifest compute (temper-io-types ``manifest`` module) against the
pinned pre-migration oracle.

The pre-migration ``temper_placer/regression/manifest.py`` is pinned
VERBATIM as ``tests/regression/_manifest_py_oracle.py`` (content-hash
registered in ``scripts/oracle_hashes.json`` AND in this file's body
digests). Both arms are driven with IDENTICAL inputs; every assertion is
bit-exact:

- ``temper_io_types.resolve_board_path_py`` vs oracle ``GoldenBoard.resolve_path``
  (``repo_root / board.path``);
- ``temper_io_types.baseline_yaml_path_py``  vs oracle ``GoldenBoard.baseline_yaml_path``
  (``power_pcb_dataset/baselines/{id}_baseline.yaml``);
- ``temper_io_types.baseline_pcb_path_py``   vs oracle ``GoldenBoard.baseline_pcb_path``
  (``power_pcb_dataset/baselines/{id}.kicad_pcb``);
- ``temper_io_types.validate_board_paths``   vs oracle ``GoldenManifest.validate``
  (the per-board missing-PCB error strings — the shim keeps the ``mkdir``
  side effect so the two arms' filesystem effects match too).

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations``
asserts the shim methods bind to the ``temper_io_types`` pyfunctions and
the oracle still holds the Python compute; ``test_shim_delegates_*`` prove
the shim methods really route through the pyo3 boundary (recording stubs).

What stays Python (documented boundary): the YAML ingestion
(``GoldenManifest.load`` — ``yaml.safe_load``), the ``validate`` ``mkdir``
side effect and the ``get_board`` linear lookup. The differential still pins
them (``test_load_matches_oracle`` / ``test_get_board_matches_oracle``)
because the shim keeps the SAME code the oracle had — the only divergence
under test is the migrated path-set compute feeding it. See the module
header in ``packages/temper-io-types/src/manifest.rs`` and its
VERIFICATION.md for the split argument.
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path
from tempfile import mkdtemp

import temper_io_types as _tio
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.regression import manifest as shim_mod
from temper_placer.regression.manifest import GoldenBoard, GoldenManifest
from tests.regression import _manifest_py_oracle as _oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_manifest_py_oracle.py")

# Body digests of the four ported kernels, extracted from the oracle file
# (AST ranges of the class methods, dedented) — pinned here so a body edit
# in the oracle fails this test rather than silently re-pinning the
# differential.
_BODY_DIGESTS = {
    "GoldenBoard.resolve_path": "77befb9e807d50f25efefaa2fadaf05a0c927f882b48f22d0000ff5901e5873d",
    "GoldenBoard.baseline_yaml_path": "62a8a44d0f95337fb40338a7f3ca5fa572cc492c26927a31cf190957f8f15d9a",
    "GoldenBoard.baseline_pcb_path": "d509bb3e036fa575f513ad9e00230343058138a5dad10699d27461dc1784c982",
    "GoldenManifest.validate": "b16bd53112db888771d04ad92e1f9b68a8e5f1300ae560d07a1b06c5535a4639",
}


def _oracle_body_digests(path: Path) -> dict[str, str]:
    import ast

    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    out: dict[str, str] = {}

    def walk(node, prefix=""):
        for child in node.body:
            if isinstance(child, ast.ClassDef):
                walk(child, child.name + ".")
            elif isinstance(child, ast.FunctionDef):
                body = "".join(lines[child.lineno - 1 : child.end_lineno])
                out[prefix + child.name] = hashlib.sha256(textwrap.dedent(body).encode()).hexdigest()

    walk(ast.parse(src))
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
    """Anti-vacuity: the shim methods must bind to temper_io_types
    pyfunctions, not resolve back onto the oracle or keep the compute
    inline."""
    assert _tio.resolve_board_path_py.__module__ == "temper_io_types.temper_io_types"
    assert _tio.baseline_yaml_path_py.__module__ == "temper_io_types.temper_io_types"
    assert _tio.baseline_pcb_path_py.__module__ == "temper_io_types.temper_io_types"
    assert _tio.validate_board_paths.__module__ == "temper_io_types.temper_io_types"
    # The oracle's compute must not have been collapsed onto the shims.
    import inspect

    src = inspect.getsource(shim_mod)
    assert "repo_root / self.path" not in src
    assert "import temper_io_types" in src
    assert "validate_board_paths" in src
    assert "resolve_board_path_py" in src


def test_shim_delegates_resolve_path(monkeypatch, tmp_path) -> None:
    """Anti-vacuity: GoldenBoard.resolve_path routes through the Rust
    kernel."""
    calls: list[tuple] = []
    real = _tio.resolve_board_path_py

    def recording(root, path):
        calls.append((root, path))
        return real(root, path)

    monkeypatch.setattr(_tio, "resolve_board_path_py", recording)
    board = GoldenBoard(id="b1", path="pcb/b1.kicad_pcb", component_count=1, net_count=1, baseline_git_hash="x")
    got = board.resolve_path(tmp_path)
    assert got == tmp_path / "pcb" / "b1.kicad_pcb"
    assert calls == [(str(tmp_path), "pcb/b1.kicad_pcb")]


def test_shim_delegates_baseline_paths(monkeypatch, tmp_path) -> None:
    calls_yaml: list[tuple] = []
    calls_pcb: list[tuple] = []
    real_yaml = _tio.baseline_yaml_path_py
    real_pcb = _tio.baseline_pcb_path_py

    def recording_yaml(root, bid):
        calls_yaml.append((root, bid))
        return real_yaml(root, bid)

    def recording_pcb(root, bid):
        calls_pcb.append((root, bid))
        return real_pcb(root, bid)

    monkeypatch.setattr(_tio, "baseline_yaml_path_py", recording_yaml)
    monkeypatch.setattr(_tio, "baseline_pcb_path_py", recording_pcb)
    board = GoldenBoard(id="temper", path="pcb/t.kicad_pcb", component_count=1, net_count=1, baseline_git_hash="x")
    assert board.baseline_yaml_path(tmp_path) == tmp_path / "power_pcb_dataset" / "baselines" / "temper_baseline.yaml"
    assert board.baseline_pcb_path(tmp_path) == tmp_path / "power_pcb_dataset" / "baselines" / "temper.kicad_pcb"
    assert calls_yaml == [(str(tmp_path), "temper")]
    assert calls_pcb == [(str(tmp_path), "temper")]


def test_shim_delegates_validate(monkeypatch, tmp_path) -> None:
    """Anti-vacuity: GoldenManifest.validate routes through the Rust
    kernel."""
    calls: list[tuple] = []
    real = _tio.validate_board_paths

    def recording(root, boards):
        calls.append((root, boards))
        return real(root, boards)

    monkeypatch.setattr(_tio, "validate_board_paths", recording)
    manifest = GoldenManifest(
        version=1,
        boards=[GoldenBoard(id="b1", path="pcb/b1.kicad_pcb", component_count=1, net_count=1, baseline_git_hash="x")],
    )
    manifest.validate(tmp_path)
    assert len(calls) == 1
    assert calls[0][0] == str(tmp_path)
    assert calls[0][1] == [("b1", "pcb/b1.kicad_pcb")]


# ---------------------------------------------------------------------------
# Path-set differentials
# ---------------------------------------------------------------------------

_CASE_BOARDS = [
    ("temper", "pcb/temper.kicad_pcb"),
    ("tiny", "power_pcb_dataset/boards/tiny.kicad_pcb"),
    ("deep", "a/b/c/deep.kicad_pcb"),
    ("spaced", "pcb/with space.kicad_pcb"),
]


def _board_for(board_id, path):
    return GoldenBoard(
        id=board_id, path=path, component_count=1, net_count=1, baseline_git_hash="x"
    )


def test_resolve_path_matches_oracle() -> None:
    for root in ("/repo", "/tmp/with space", "/"):
        for board_id, board_path in _CASE_BOARDS:
            got = _board_for(board_id, board_path).resolve_path(Path(root))
            want = _oracle.GoldenBoard(
                id=board_id, path=board_path, component_count=1, net_count=1, baseline_git_hash="x"
            ).resolve_path(Path(root))
            assert got == want
            assert str(got) == str(want)


def test_baseline_paths_match_oracle() -> None:
    for root in ("/repo", "/tmp/x"):
        for board_id, _board_path in _CASE_BOARDS:
            board = _board_for(board_id, "irrelevant")
            oracle_board = _oracle.GoldenBoard(
                id=board_id, path="irrelevant", component_count=1, net_count=1, baseline_git_hash="x"
            )
            assert board.baseline_yaml_path(Path(root)) == oracle_board.baseline_yaml_path(Path(root))
            assert board.baseline_pcb_path(Path(root)) == oracle_board.baseline_pcb_path(Path(root))


def test_validate_matches_oracle(tmp_path) -> None:
    """Existing PCB files produce no error; missing ones produce the
    oracle-identical message (the shim performs the same mkdir side effect
    first, so the filesystem state matches too)."""
    (tmp_path / "pcb").mkdir()
    (tmp_path / "pcb" / "b1.kicad_pcb").write_text("(kicad_pcb)\n")
    boards = [
        ("b1", "pcb/b1.kicad_pcb"),
        ("b2", "pcb/b2.kicad_pcb"),
    ]
    shim = GoldenManifest(version=1, boards=[_board_for(*b) for b in boards])
    oracle = _oracle.GoldenManifest(
        version=1,
        boards=[
            _oracle.GoldenBoard(id=i, path=p, component_count=1, net_count=1, baseline_git_hash="x")
            for i, p in boards
        ],
    )
    assert shim.validate(tmp_path) == oracle.validate(tmp_path)
    assert shim.validate(tmp_path) == ["Board 'b2': PCB file not found at " + str(tmp_path / "pcb" / "b2.kicad_pcb")]


def test_validate_empty_manifest(tmp_path) -> None:
    assert GoldenManifest().validate(tmp_path) == []
    assert _oracle.GoldenManifest().validate(tmp_path) == []


def test_absolute_board_path_replacement_semantics_match_oracle() -> None:
    """pathlib and PathBuf both REPLACE the repo root when the joined path
    is absolute — the differential pins both arms agreeing on that corner
    (a board manifest would never carry an absolute path, but the join
    semantics must not diverge either)."""
    root = Path("/repo")
    for abs_path in ("/etc", "/", "/x/y.kicad_pcb"):
        got = _board_for("b", abs_path).resolve_path(root)
        want = _oracle.GoldenBoard(
            id="b", path=abs_path, component_count=1, net_count=1, baseline_git_hash="x"
        ).resolve_path(root)
        assert str(got) == str(want) == abs_path


def test_trailing_separator_divergence_is_documented_bound(tmp_path) -> None:
    """pathlib and PathBuf disagree on a trailing separator in a board path
    ('pcb/x/'): the shim's ``Path(...)`` wrapper normalizes it away, so the
    ``resolve_path`` public API matches the oracle exactly; but the Rust
    ``validate_board_paths`` error-message formatting preserves it while
    pathlib's ``str(Path)`` strips it. This is a DOCUMENTED BOUND (real
    manifest paths never carry trailing separators; the PBT domain is
    constrained accordingly), recorded here so the divergence is a pinned
    fact rather than a surprise."""
    root = tmp_path
    trailing = "pcb/x/"
    # resolve_path: the shim's Path() wrapper normalizes — public API parity.
    got = str(_board_for("b", trailing).resolve_path(root))
    want = str(
        _oracle.GoldenBoard(
            id="b", path=trailing, component_count=1, net_count=1, baseline_git_hash="x"
        ).resolve_path(root)
    )
    assert got == want == str(root / "pcb" / "x")
    # validate: the Rust message keeps the trailing separator; pathlib strips it.
    rust_msgs = _tio.validate_board_paths(str(root), [("b", "pcb/x/")])
    assert rust_msgs == [f"Board 'b': PCB file not found at {root}/pcb/x/"]
    oracle_msgs = _oracle.GoldenManifest(
        boards=[
            _oracle.GoldenBoard(id="b", path="pcb/x/", component_count=1, net_count=1, baseline_git_hash="x")
        ]
    ).validate(root)
    assert oracle_msgs == [f"Board 'b': PCB file not found at {root}/pcb/x"]


def test_redundant_separator_divergence_is_documented_bound(tmp_path) -> None:
    """pathlib collapses empty and '.' components on join (``'0//0'`` →
    ``'0/0'``, ``'a/./b'`` → ``'a/b'``) while PathBuf preserves them
    literally. As with trailing separators, the shim's ``Path(...)`` wrapper
    gives ``resolve_path`` full public-API parity, but ``validate_board_paths``
    messages diverge for such paths. Documented bound: real manifest paths
    never carry redundant separators (the PBT domain is constrained to clean
    components); pinned here so the divergence is a known fact."""
    root = tmp_path
    rust_msgs = _tio.validate_board_paths(str(root), [("b", "0//0")])
    assert rust_msgs == [f"Board 'b': PCB file not found at {root}/0//0"]
    oracle_msgs = _oracle.GoldenManifest(
        boards=[
            _oracle.GoldenBoard(id="b", path="0//0", component_count=1, net_count=1, baseline_git_hash="x")
        ]
    ).validate(root)
    assert oracle_msgs == [f"Board 'b': PCB file not found at {root}/0/0"]


# ---------------------------------------------------------------------------
# Unmigrated surfaces still pinned (load / get_board share the same code)
# ---------------------------------------------------------------------------


def test_load_matches_oracle(tmp_path) -> None:
    manifest_path = tmp_path / "golden_manifest.yaml"
    manifest_path.write_text(
        "version: 1\nboards:\n  - id: b1\n    path: pcb/b1.kicad_pcb\n"
        "    component_count: 5\n    net_count: 3\n    baseline_git_hash: abc123\n"
        "    description: 'Test board'\n"
    )
    got = GoldenManifest.load(manifest_path)
    want = _oracle.GoldenManifest.load(manifest_path)
    assert got.version == want.version
    assert len(got.boards) == len(want.boards)
    for g, w in zip(got.boards, want.boards):
        assert (g.id, g.path, g.component_count, g.net_count, g.baseline_git_hash, g.description) == (
            w.id, w.path, w.component_count, w.net_count, w.baseline_git_hash, w.description,
        )


def test_get_board_matches_oracle() -> None:
    shim = GoldenManifest(version=1, boards=[_board_for("b1", "pcb/b1.kicad_pcb")])
    oracle = _oracle.GoldenManifest(
        version=1,
        boards=[
            _oracle.GoldenBoard(id="b1", path="pcb/b1.kicad_pcb", component_count=1, net_count=1, baseline_git_hash="x")
        ],
    )
    assert shim.get_board("b1") is not None
    assert oracle.get_board("b1") is not None
    assert shim.get_board("nope") is None
    assert oracle.get_board("nope") is None


# ---------------------------------------------------------------------------
# PBT (Hypothesis): differential + invariants
# ---------------------------------------------------------------------------

_root = st.text(
    alphabet=st.sampled_from("/abcdefghijklmnopqrstuvwxyz- _0123456789"),
    min_size=1,
    max_size=40,
)
_id = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_/- "),
    min_size=1,
    max_size=20,
)
# Clean relative manifest paths — the real golden_manifest.yaml domain. The
# differential pins bit-exact parity for paths whose components are ordinary
# names; pathlib-vs-PathBuf diverge on empty (``//``), ``.`` and trailing
# separators (pathlib collapses them, PathBuf preserves them literally), which
# real manifest entries never carry — recorded as documented bounds below and
# pinned by test_trailing_separator_divergence_is_documented_bound /
# test_redundant_separator_divergence_is_documented_bound.
_component = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_-."),
    min_size=1,
    max_size=12,
).filter(lambda c: c not in (".", ".."))
_path = st.lists(_component, min_size=1, max_size=4).map("/".join)


@settings(deadline=None)
@given(root=_root, board_path=_path)
def test_pbt_resolve_path_matches_oracle(root, board_path):
    """Differential: resolve_path is str-identical to the oracle's
    repo_root / path join."""
    got = _board_for("b", board_path).resolve_path(Path(root))
    want = _oracle.GoldenBoard(
        id="b", path=board_path, component_count=1, net_count=1, baseline_git_hash="x"
    ).resolve_path(Path(root))
    assert got == want
    assert str(got) == str(want)


@settings(deadline=None)
@given(root=_root, board_id=_id)
def test_pbt_baseline_yaml_path_matches_oracle(root, board_id):
    got = _board_for(board_id, "x").baseline_yaml_path(Path(root))
    want = _oracle.GoldenBoard(
        id=board_id, path="x", component_count=1, net_count=1, baseline_git_hash="x"
    ).baseline_yaml_path(Path(root))
    assert str(got) == str(want)


@settings(deadline=None)
@given(root=_root, board_id=_id)
def test_pbt_baseline_pcb_path_matches_oracle(root, board_id):
    got = _board_for(board_id, "x").baseline_pcb_path(Path(root))
    want = _oracle.GoldenBoard(
        id=board_id, path="x", component_count=1, net_count=1, baseline_git_hash="x"
    ).baseline_pcb_path(Path(root))
    assert str(got) == str(want)


@settings(deadline=None)
@given(boards=st.lists(st.tuples(_id, _path), min_size=0, max_size=6))
def test_pbt_validate_matches_oracle(boards):
    """Differential: validate error lists are identical to the oracle's for
    arbitrary (id, path) sets against a real empty temp repo."""
    d = Path(mkdtemp(prefix="manifestpbt_"))
    shim = GoldenManifest(version=1, boards=[_board_for(i, p) for i, p in boards])
    oracle = _oracle.GoldenManifest(
        version=1,
        boards=[
            _oracle.GoldenBoard(id=i, path=p, component_count=1, net_count=1, baseline_git_hash="x")
            for i, p in boards
        ],
    )
    assert shim.validate(d) == oracle.validate(d)


@settings(deadline=None)
@given(root=_root, board_path=_path)
def test_pbt_resolve_path_prefix_invariant(root, board_path):
    """Invariant: the resolved path always starts with the repo root (the
    join never discards or reorders its first operand)."""
    got = _board_for("b", board_path).resolve_path(Path(root))
    assert str(got).startswith(root)


# ---------------------------------------------------------------------------
# Metamorphic relations (deterministic samples)
# ---------------------------------------------------------------------------


def test_meta_validate_reports_exactly_the_missing_boards(tmp_path) -> None:
    """Validation reports exactly one error per missing PCB, in manifest
    order, and no error for existing PCBs."""
    (tmp_path / "pcb").mkdir()
    (tmp_path / "pcb" / "a.kicad_pcb").write_text("(kicad_pcb)\n")
    boards = [("a", "pcb/a.kicad_pcb"), ("b", "pcb/b.kicad_pcb"), ("c", "pcb/c.kicad_pcb")]
    errs = GoldenManifest(version=1, boards=[_board_for(*b) for b in boards]).validate(tmp_path)
    assert len(errs) == 2
    assert errs[0].endswith("pcb/b.kicad_pcb")
    assert errs[1].endswith("pcb/c.kicad_pcb")
    assert all("Board 'a'" not in e for e in errs)


def test_meta_baseline_path_embeds_the_id(tmp_path) -> None:
    """Each baseline path embeds its board id verbatim in the fixed
    power_pcb_dataset/baselines layout — the id is the only free variable."""
    base = Path("/repo")
    yaml_a = _board_for("alpha", "x").baseline_yaml_path(base)
    yaml_b = _board_for("beta", "x").baseline_yaml_path(base)
    assert str(yaml_a).endswith("alpha_baseline.yaml")
    assert str(yaml_b).endswith("beta_baseline.yaml")
    assert yaml_a.parent == yaml_b.parent == base / "power_pcb_dataset" / "baselines"
    pcb_a = _board_for("alpha", "x").baseline_pcb_path(base)
    pcb_b = _board_for("beta", "x").baseline_pcb_path(base)
    assert str(pcb_a).endswith("alpha.kicad_pcb")
    assert str(pcb_b).endswith("beta.kicad_pcb")


def test_meta_validate_is_idempotent_across_calls(tmp_path) -> None:
    """validate is a pure function of (manifest, repo state): calling it
    twice yields the same errors (the mkdir side effect is a no-op on the
    second call)."""
    boards = [("b1", "pcb/b1.kicad_pcb")]
    manifest = GoldenManifest(version=1, boards=[_board_for(*b) for b in boards])
    first = manifest.validate(tmp_path)
    second = manifest.validate(tmp_path)
    assert first == second
    assert (tmp_path / "power_pcb_dataset" / "baselines").is_dir()


def test_meta_resolve_path_is_stable_under_root_trailing_slash(tmp_path) -> None:
    """A trailing slash on the repo root is preserved by pathlib; the Rust
    join produces the same display string (Path::join keeps it)."""
    base = Path("/repo/")
    board = _board_for("b1", "pcb/b1.kicad_pcb")
    oracle = _oracle.GoldenBoard(id="b1", path="pcb/b1.kicad_pcb", component_count=1, net_count=1, baseline_git_hash="x")
    assert board.resolve_path(base) == oracle.resolve_path(base)
    assert str(board.resolve_path(base)) == str(oracle.resolve_path(base))
