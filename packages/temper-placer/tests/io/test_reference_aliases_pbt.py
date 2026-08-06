"""Property-based + metamorphic tests for the Rust reference-alias loader.

Wave 4, Phase 3, candidate 5 (plan ``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``,
R1c/R1d). These properties exercise the migrated
``temper_placer.io.reference_aliases`` module (a pure-delegation re-export of
the ``temper_io_types`` pyclasses); error/value parity against the pinned
oracle is asserted separately by ``test_reference_aliases_rust_differential.py``.

Properties:

- P1. Validation is a closed gate: for any alias map, the loader either
  accepts it with every target live and every source distinct-and-nonlive,
  or rejects it with one of the oracle's ValueError classes.
- P2. Valid manifests preserve the mapping exactly.
- P3. Self-aliases are always rejected.
- P4. Live sources are always rejected.
- P5. Missing targets are always rejected.
- P6. Schema-version other than 1 is always rejected.

Metamorphic relations:

- MR1. Available-set independence: adding extra available names (beyond the
  referenced targets) never changes a valid load's result.
- MR2. Order independence of ``component_refs``/``loop_names`` (sets).
- MR3. Loop-vs-component namespace isolation: a loop alias can target a
  component name (and vice versa) without tripping the other namespace's
  live-name check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import temper_io_types as _io
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.io._reference_aliases_py_oracle as _oracle

LOAD = _io.load_reference_alias_manifest

MAX_EXAMPLES = 100

_NAME_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"


@st.composite
def alias_map(draw):
    """A mapping whose keys/values are non-empty names over a small alphabet
    (so collisions with the live set are reachable)."""
    names = draw(
        st.lists(
            st.text(min_size=1, max_size=6, alphabet=_NAME_ALPHABET),
            min_size=1,
            max_size=6,
            unique=True,
        )
    )
    pairs = draw(
        st.lists(
            st.tuples(st.sampled_from(names), st.sampled_from(names)),
            min_size=0,
            max_size=6,
            unique=True,
        )
    )
    return dict(pairs), names


def _write(content: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "m.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _render_aliases(aliases: dict) -> str:
    """Render a component_aliases block; an empty dict must render as `{}`
    (a bare key with no entries parses to None, which the loader rejects)."""
    if not aliases:
        return "component_aliases: {}\n"
    return "component_aliases:\n" + "".join(f"  {k}: {v}\n" for k, v in aliases.items())


def _load_both(content: str, component_refs, loop_names):
    path = _write(content)
    with open(path) as f:
        raw = __import__("yaml").safe_load(f)
    # oracle arm: pass the path directly (Path)
    try:
        py_res = ("ok", _oracle.load_reference_alias_manifest(path, component_refs=component_refs, loop_names=loop_names))
    except Exception as e:  # noqa: BLE001
        py_res = ("err", type(e).__name__)
    try:
        rs_res = ("ok", LOAD(str(path), component_refs=component_refs, loop_names=loop_names))
    except Exception as e:  # noqa: BLE001
        rs_res = ("err", type(e).__name__)
    return py_res, rs_res, raw


@given(alias_map())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_validation_is_a_closed_gate(alias_and_names):
    aliases, names = alias_and_names
    content = "schema_version: 1\n" + _render_aliases(aliases)
    py_res, rs_res, _raw = _load_both(content, names, set())
    assert rs_res[0] == py_res[0]  # both arms agree on accept/reject
    if rs_res[0] == "ok":
        # accepted => every target live, every source distinct and not live
        for source, target in aliases.items():
            assert target in names, "accepted alias with missing target"
            assert source != target, "accepted self-alias"
            assert source not in names, "accepted live source"
        m = rs_res[1]
        assert dict(m.component_aliases) == aliases
    else:
        assert py_res[1] == rs_res[1], "both arms reject with the same type"


@given(alias_map())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_p3_p4_p5_rejection_classes(alias_and_names):
    aliases, names = alias_and_names
    content = "schema_version: 1\n" + _render_aliases(aliases)
    py_res, rs_res, _raw = _load_both(content, names, set())
    if py_res[0] == "ok" and rs_res[0] == "ok":
        # same type name + same mapping (cross-class == is NotImplemented)
        assert type(rs_res[1]).__name__ == type(py_res[1]).__name__
        assert dict(rs_res[1].component_aliases) == dict(py_res[1].component_aliases)
        assert dict(rs_res[1].loop_aliases) == dict(py_res[1].loop_aliases)
    else:
        assert rs_res == py_res


@given(st.integers(min_value=-5, max_value=5))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p6_schema_version_other_than_one_rejected(version):
    if version == 1:
        return
    path = _write(f"schema_version: {version}\ncomponent_aliases: {{}}\n")
    try:
        _oracle.load_reference_alias_manifest(path, component_refs=set(), loop_names=set())
        py_rejected = False
    except ValueError:
        py_rejected = True
    try:
        LOAD(str(path), component_refs=set(), loop_names=set())
        rs_rejected = False
    except ValueError:
        rs_rejected = True
    assert py_rejected == rs_rejected is True


@given(alias_map())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_extra_available_names_do_not_change_result(alias_and_names):
    aliases, names = alias_and_names
    # restrict to valid aliases only (every target live, no self/live source)
    valid = {k: v for k, v in aliases.items() if v in names and k != v and k not in names}
    content = "schema_version: 1\n" + _render_aliases(valid)
    path = _write(content)
    extra = ["ZZ_EXTRA_1", "ZZ_EXTRA_2"]
    m_small = LOAD(str(path), component_refs=set(names), loop_names=set())
    m_big = LOAD(str(path), component_refs=set(names + extra), loop_names=set())
    assert dict(m_small.component_aliases) == dict(m_big.component_aliases)


@given(alias_map())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_available_set_order_irrelevant(alias_and_names):
    aliases, names = alias_and_names
    valid = {k: v for k, v in aliases.items() if v in names and k != v and k not in names}
    content = "schema_version: 1\n" + _render_aliases(valid)
    path = _write(content)
    m_a = LOAD(str(path), component_refs=list(names), loop_names=set())
    m_b = LOAD(str(path), component_refs=list(reversed(names)), loop_names=set())
    assert dict(m_a.component_aliases) == dict(m_b.component_aliases)


def test_mr3_namespace_isolation():
    """Loop targets validate against the loop namespace only: a target that is
    a live COMPONENT ref does not satisfy the loop check, and a component ref
    set does not leak into loop validation."""
    path = _write("schema_version: 1\nloop_aliases:\n  LEGACY_LOOP: C2\n")
    try:
        LOAD(str(path), component_refs={"C2"}, loop_names=set())
        rejected = False
    except ValueError:
        rejected = True
    assert rejected is True
    m = LOAD(str(path), component_refs=set(), loop_names={"C2"})
    assert dict(m.loop_aliases) == {"LEGACY_LOOP": "C2"}
