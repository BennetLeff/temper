"""Shared Hypothesis strategies for the topological placement suites.

Composed bottom-up per the repo's invariant-suite pattern
(docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md):
refs -> edge specs -> whole graph specs -> positions/sizes/zones. Generation
logic lives here once; the PBT and metamorphic files draw from it.

Distances are drawn from a finite, non-NaN band because the production callers
(``heuristics/topological_init.py``, the PCL adjacency/separation constraints)
only ever supply positive finite millimetre distances. NaN and infinity are
covered by explicit fixtures in the differential file instead, where the
oracle pins the exact behaviour rather than a property having to describe it.
"""

from __future__ import annotations

from hypothesis import strategies as st

from temper_placer.core.board import Zone

# Multi-character, non-numeric refs: single characters would make the
# node-relabelling metamorphic relation trivially collision-prone.
refs = st.text(alphabet="ABCDEFGH", min_size=1, max_size=3).map(lambda s: f"U{s}")

distances = st.floats(min_value=0.001, max_value=1000.0, allow_nan=False, allow_infinity=False)
coords = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False)
sizes = st.floats(min_value=0.1, max_value=8.0, allow_nan=False, allow_infinity=False)


@st.composite
def component_lists(draw: st.DrawFn, min_size: int = 1, max_size: int = 7) -> list[str]:
    """A deduplicated, order-preserving list of component refs."""
    raw = draw(st.lists(refs, min_size=min_size, max_size=max_size))
    seen: list[str] = []
    for r in raw:
        if r not in seen:
            seen.append(r)
    if not seen:
        seen = ["UA"]
    return seen


@st.composite
def graph_specs(draw: st.DrawFn, min_components: int = 1, max_components: int = 7):
    """Return ``(components, adjacencies, separations)``.

    Each edge is ``(a, b, distance, constraint_id)``. Self-loops are excluded
    because ``add_adjacency(a, a, ...)`` would create a self-edge the
    production constraint parser cannot emit.
    """
    comps = draw(component_lists(min_size=min_components, max_size=max_components))

    def edges(tag: str):
        n = draw(st.integers(min_value=0, max_value=min(6, len(comps) * 2)))
        out = []
        for k in range(n):
            a = draw(st.sampled_from(comps))
            b = draw(st.sampled_from(comps))
            if a == b:
                continue
            out.append((a, b, draw(distances), f"{tag}{k}"))
        return out

    return comps, edges("adj"), edges("sep")


@st.composite
def position_maps(draw: st.DrawFn, components: list[str]) -> dict[str, tuple[float, float]]:
    return {ref: (draw(coords), draw(coords)) for ref in components}


@st.composite
def size_maps(draw: st.DrawFn, components: list[str]) -> dict[str, tuple[float, float]]:
    return {ref: (draw(sizes), draw(sizes)) for ref in components}


@st.composite
def zones(draw: st.DrawFn, name: str = "Z") -> Zone:
    x0 = draw(coords)
    y0 = draw(coords)
    w = draw(st.floats(min_value=20.0, max_value=400.0, allow_nan=False))
    h = draw(st.floats(min_value=20.0, max_value=400.0, allow_nan=False))
    return Zone(name=name, bounds=(x0, y0, x0 + w, y0 + h))


def build_graph(cls, components, adjacencies, separations):
    """Build a graph of the given class from a spec tuple."""
    g = cls()
    for ref in components:
        g.add_component(ref)
    for a, b, d, cid in adjacencies:
        g.add_adjacency(a, b, d, cid)
    for a, b, d, cid in separations:
        g.add_separation(a, b, d, cid)
    return g
