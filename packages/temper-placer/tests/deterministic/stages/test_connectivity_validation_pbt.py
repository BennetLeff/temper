"""Property-based + metamorphic tests for the migrated connectivity kernel.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Bit-identical parity
against the pinned oracle is asserted separately by
``test_connectivity_validation_rust_differential.py``.

Well-separated synthetic nets (anchors are integers scaled by _STRIDE so
every cluster is isolated from every other) admit an exact structural
prediction, which the properties assert:

- ``pc`` pad-bearing clusters (``pad``/``chain``/``viabridge``) and ``ic``
  copper-island clusters (``track``/``via``) form exactly ``pc + ic``
  components.  Hence:
  * ``unconnected_pad == max(0, pc - 1)`` (P1),
  * ``orphan_island == ic`` (P2),
  * ``dangling_track == tc`` where ``tc`` is the number of lone-track
    clusters (chain/viabridge tracks connect to pads/vias at both ends) (P3).

Six hypothesis properties (R1c):

- P1. Unconnected-pad count follows the pad-component model.
- P2. Orphan-island count equals the number of copper islands.
- P3. Dangling-track count equals the number of lone-track clusters.
- P4. A single ``chain`` cluster is clean (0 violations).
- P5. A single ``viabridge`` cluster is clean (0 violations).
- P6. Violation-type closure: only the three known types are ever emitted.

Three metamorphic relations (R1d):

- MR1. Translation: shifting all coordinates by ``(dx, dy)`` preserves the
  violation types and their relative geometry.
- MR2. Net renaming: the same geometry under a different net name yields
  identical (type, location) violations; only descriptions follow the name.
- MR3. Bridging reduces violations: adding a track between two isolated
  pads removes exactly one violation and adds none.
- MR4. Registration order: permuting pad/track/via insertion order leaves
  the violation-type counts and the orphan/dangling geometry unchanged (the
  unconnected-pad *identity* is root-pinned by the largest-root-primary
  rule, so only its count is order-invariant).
"""

from __future__ import annotations

import temper_drc_rs as _drc
from hypothesis import given, settings
from hypothesis import strategies as st

_STRIDE = 1000
_KIND = st.sampled_from(["pad", "chain", "track", "via", "viabridge"])
_INDEX = st.integers(min_value=0, max_value=60)
_NET = st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789")
_CLUSTERS = st.lists(
    st.tuples(_KIND, _INDEX, _INDEX),
    min_size=0,
    max_size=6,
    # Distinct anchors: overlapping clusters would couple the properties.
    unique_by=lambda c: (c[1], c[2]),
)


def _anchor(i, j):
    return (_STRIDE * i, _STRIDE * j)


def _build(clusters, net):
    """Return (pads, tracks, vias) flattened tuple lists for the kernel."""
    pads, tracks, vias = [], [], []
    for cid, (kind, i, j) in enumerate(clusters):
        x, y = _anchor(i, j)
        if kind == "pad":
            pads.append((x, y, 0, f"P{cid}", 1.0, 1.0, 0.0))
        elif kind == "chain":
            pads.append((x, y, 0, f"P{cid}a", 1.0, 1.0, 0.0))
            pads.append((x + 10, y, 0, f"P{cid}b", 1.0, 1.0, 0.0))
            tracks.append((x, y, x + 10, y, 0))
        elif kind == "track":
            tracks.append((x, y, x + 5, y, 0))
        elif kind == "via":
            vias.append((x, y))
        elif kind == "viabridge":
            pads.append((x, y, 0, f"P{cid}a", 1.0, 1.0, 0.0))
            pads.append((x + 5, y, 1, f"P{cid}b", 1.0, 1.0, 0.0))
            tracks.append((x, y, x + 5, y, 0))
            vias.append((x + 5, y))
    return pads, tracks, vias


def _run(clusters, net):
    pads, tracks, vias = _build(clusters, net)
    return list(_drc.connectivity_validate_net_py(net, pads, tracks, vias))


def _counts(vs):
    by = {}
    for v in vs:
        by[v[0]] = by.get(v[0], 0) + 1
    return by


def _pad_component_count(clusters):
    return sum(1 for c in clusters if c[0] in ("pad", "chain", "viabridge"))


def _island_cluster_count(clusters):
    return sum(1 for c in clusters if c[0] in ("track", "via"))


def _lone_track_count(clusters):
    return sum(1 for c in clusters if c[0] == "track")


@given(_CLUSTERS)
@settings(max_examples=100, deadline=None)
def test_p1_unconnected_pad_model(clusters):
    vs = _run(clusters, "N")
    pc = _pad_component_count(clusters)
    assert _counts(vs).get("unconnected_pad", 0) == max(0, pc - 1)


@given(_CLUSTERS)
@settings(max_examples=100, deadline=None)
def test_p2_orphan_island_model(clusters):
    vs = _run(clusters, "N")
    ic = _island_cluster_count(clusters)
    assert _counts(vs).get("orphan_island", 0) == ic


@given(_CLUSTERS)
@settings(max_examples=100, deadline=None)
def test_p3_dangling_track_model(clusters):
    vs = _run(clusters, "N")
    tc = _lone_track_count(clusters)
    assert _counts(vs).get("dangling_track", 0) == tc


@given(_INDEX, _INDEX)
@settings(max_examples=100, deadline=None)
def test_p4_single_chain_is_clean(i, j):
    vs = _run([("chain", i, j)], "N")
    assert vs == []


@given(_INDEX, _INDEX)
@settings(max_examples=100, deadline=None)
def test_p5_single_viabridge_is_clean(i, j):
    vs = _run([("viabridge", i, j)], "N")
    assert vs == []


@given(_CLUSTERS)
@settings(max_examples=100, deadline=None)
def test_p6_type_closure(clusters):
    vs = _run(clusters, "N")
    assert all(v[0] in ("orphan_island", "unconnected_pad", "dangling_track") for v in vs)


@given(_CLUSTERS, st.integers(min_value=1, max_value=100), st.integers(min_value=1, max_value=100))
@settings(max_examples=100, deadline=None)
def test_mr1_translation(clusters, dx, dy):
    vs = _run(clusters, "N")
    shifted = [(v[0], v[1] + _STRIDE * dx, v[2] + _STRIDE * dy, v[3]) for v in vs]
    pads, tracks, vias = _build(clusters, "N")
    pads2 = [(x + _STRIDE * dx, y + _STRIDE * dy, l, i, w, h, r) for x, y, l, i, w, h, r in pads]
    tracks2 = [(sx + _STRIDE * dx, sy + _STRIDE * dy, ex + _STRIDE * dx, ey + _STRIDE * dy, l) for sx, sy, ex, ey, l in tracks]
    vias2 = [(x + _STRIDE * dx, y + _STRIDE * dy) for x, y in vias]
    vs2 = list(_drc.connectivity_validate_net_py("N", pads2, tracks2, vias2))
    assert vs2 == shifted


@given(_CLUSTERS, _NET)
@settings(max_examples=100, deadline=None)
def test_mr2_net_rename(clusters, net2):
    if not net2 or net2 == "N":
        return
    a = _run(clusters, "N")
    b = _run(clusters, net2)
    assert [(v[0], v[1], v[2]) for v in a] == [(v[0], v[1], v[2]) for v in b]
    for va, vb in zip(a, b):
        assert va[3].replace("N", net2) == vb[3]


@given(_INDEX, _INDEX)
@settings(max_examples=100, deadline=None)
def test_mr3_bridging_reduces_violations(i, j):
    x, y = _anchor(i, j)
    a = _counts(_run([("pad", i, j), ("pad", i + 1, j)], "N"))
    assert a == {"unconnected_pad": 1}
    pads = [(x, y, 0, "P0", 1.0, 1.0, 0.0), (x + _STRIDE, y, 0, "P1", 1.0, 1.0, 0.0)]
    tracks = [(x, y, x + _STRIDE, y, 0)]
    b = _counts(list(_drc.connectivity_validate_net_py("N", pads, tracks, [])))
    assert b == {}


@given(_CLUSTERS)
@settings(max_examples=100, deadline=None)
def test_mr4_order_permutation(clusters):
    a = _run(clusters, "N")
    pads, tracks, vias = _build(clusters, "N")
    b = list(_drc.connectivity_validate_net_py(
        "N", list(reversed(pads)), list(reversed(tracks)), list(reversed(vias))
    ))
    assert _counts(a) == _counts(b)
    a_geo = {(v[0], v[1], v[2]) for v in a if v[0] != "unconnected_pad"}
    b_geo = {(v[0], v[1], v[2]) for v in b if v[0] != "unconnected_pad"}
    assert a_geo == b_geo
