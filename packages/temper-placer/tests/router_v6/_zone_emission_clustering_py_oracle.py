"""Pinned Python (scipy) oracle for the `_cluster_positions` Ward-linkage
clustering migration (R19).

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
``_cluster_positions`` below is a **verbatim** ``git show`` extraction from
commit ``c10523bb`` (this migration's base commit) of
``temper_placer/router_v6/zone_emission.py``. Nothing has been cleaned up,
refactored, or fixed by this file.
``test_zone_emission_clustering_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts the function from the pinned commit and compares the source text
character for character.

Why this function specifically
-------------------------------
This is the one piece of ``zone_emission.py`` this migration replaces: the
Ward-linkage clustering step (``scipy.cluster.hierarchy.linkage``/
``fcluster``/``scipy.spatial.distance.pdist``), now
``temper_geometry.ward_cluster_labels_py`` (`kodama` crate) in the live
module. The NN-distance-gap threshold heuristic inside this same function
was NEVER scipy (plain Python arithmetic) and is unchanged in the live
module -- pinned here anyway because it is inseparable from the function
body being pinned, not because it is itself part of the migration.

See docs/evidence/2026-08-07-zone-emission-clustering-kodama-port.md for the
full differential (consumer-contract verification, `kodama` evaluation,
real-board + synthetic differential results, and the port decision).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# From zone_emission.py @ c10523bb (this migration's base commit)
# ---------------------------------------------------------------------------


def _cluster_positions(
    positions: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    """Group positions into spatial clusters using data-informed hierarchical
    clustering (scipy).  The cut threshold is derived from the largest gap in
    sorted nearest-neighbour distances — separating within-component adjacency
    (~0.6-2.5 mm) from inter-component separation (70-111 mm median on the
    production board).

    Falls back to a single cluster for nets with ≤2 pads or when no natural
    gap is detectable.
    """
    if len(positions) <= 2:
        return [list(positions)]

    # Nearest-neighbour distance for every pad
    nn_dists: list[float] = []
    for i, (xi, yi) in enumerate(positions):
        best = float("inf")
        for j, (xj, yj) in enumerate(positions):
            if j == i:
                continue
            d2 = (xj - xi) ** 2 + (yj - yi) ** 2
            if d2 < best:
                best = d2
        nn_dists.append(best**0.5 if best < float("inf") else 0.0)

    nn_dists.sort()

    # Largest relative gap in sorted NN distances -> natural cut threshold.
    # Only gaps significantly wider than the local neighbourhood are
    # considered natural separation points — this prevents splitting a
    # single component's pads (where NN distances are all similar in
    # magnitude) into multiple clusters.
    max_gap_ratio = 0.0
    threshold = nn_dists[-1] if nn_dists else 0.0
    for i in range(len(nn_dists) - 1):
        if nn_dists[i] > 0:
            gap = nn_dists[i + 1] - nn_dists[i]
            ratio = gap / nn_dists[i]
            if ratio > max_gap_ratio:
                max_gap_ratio = ratio
                threshold = (nn_dists[i] + nn_dists[i + 1]) / 2.0

    # If no natural gap (all NN distances are in the same order of
    # magnitude — the component-adjacent case), use the 95th percentile
    # NN distance, resulting in one large cluster.
    if max_gap_ratio < 1.0 or threshold < 0.5:
        idx = min(len(nn_dists) - 1, int(len(nn_dists) * 0.95))
        threshold = max(10.0, nn_dists[idx]) if nn_dists else 10.0

    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    Z = linkage(pdist(positions), method="ward")
    labels = fcluster(Z, t=threshold, criterion="distance")  # type: ignore[attr-defined]

    clusters: dict[int, list[tuple[float, float]]] = {}
    for i, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(positions[i])  # type: ignore[arg-type]

    return list(clusters.values())
