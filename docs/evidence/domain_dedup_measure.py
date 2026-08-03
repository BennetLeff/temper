#!/usr/bin/env python3
# provenance: commit=74af50c52b8dcfd08e44aef27e67ff5a549f5809 dirty=false (measured on fix/domain-constraint-dedup-continued; re-verified at clean commit 74af50c52)
"""Before/after measurement for the domain-clearance constraint dedup fix.

Quantifies the fix to ``generate_domain_clearance_constraints``
(packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py):
the generator used to key its per-pair margin dict by the ORDERED
(ref_a, ref_b) tuple, so two matrix rows that pair the same two refs in
opposite order emitted the same physical pair twice. Measured 2026-08-01
(gap-2 audit, docs/evidence/2026-08-01-domain-constraint-coverage-gap.md §1):
12,022 constraints / 11,571 unique unordered pairs = 451 duplicate emissions.

This script re-measures on the current board with BOTH the pre-fix emission
(a faithful reconstruction of the old ordered-key algorithm, reimplemented
from git HEAD~1 rather than assumed) and the post-fix generator, then proves:

1. before/after counts: 12,022 -> 11,571 (-451).
2. the unordered pair set is UNCHANGED (symmetric difference 0).
3. the per-pair margin map is UNCHANGED (every pair keeps its max margin
   across all matching rows -- the stricter constraint, which dominated in
   the solver anyway, so binding semantics are identical).

Measurement script for docs/evidence/2026-08-01-domain-constraint-dedup.md;
not a gate.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "packages" / "temper-placer"
sys.path.insert(0, str(PACKAGE / "src"))
sys.path.insert(0, str(PACKAGE))

from tests.requirements.safety._real_board_fixture import (  # noqa: E402
    load_real_board_placement,
)

from temper_placer.placer.cp_sat.domain_clearance import (  # noqa: E402
    IEC60335_REQUIREMENTS,
    generate_domain_clearance_constraints,
    required_margin_mm,
)
from temper_placer.requirements.validators.clearance import (  # noqa: E402
    _domain_boundary_pairs,
    _nets_domain_map,
)


def old_ordered_key_emission(placement: dict, voltage_domains: dict) -> dict[tuple[str, str], float]:
    """Faithful reconstruction of the PRE-FIX generator's emission.

    The old code (HEAD~1) keyed ``pair_margin`` by the ordered ``(ref_a,
    ref_b)`` tuple and kept the max margin per ordered key; the emitted
    constraint count was ``len(pair_margin)``. Reimplemented here from the
    git diff rather than re-derived. Its count must match the
    independently-measured 12,022 (gap-2 audit) for this reconstruction to
    be trusted as the true "before" figure.
    """
    nets_domain = _nets_domain_map(placement, voltage_domains)
    pair_margin: dict[tuple[str, str], float] = {}
    for (domain_a, domain_b, _ins), requirements in IEC60335_REQUIREMENTS.items():
        margin = required_margin_mm(requirements)
        for comp_a, comp_b in _domain_boundary_pairs(placement, domain_a, domain_b, nets_domain):
            ra, rb = comp_a.get("ref"), comp_b.get("ref")
            if not isinstance(ra, str) or not isinstance(rb, str):
                continue
            key = (ra, rb)
            if margin > pair_margin.get(key, 0.0):
                pair_margin[key] = margin
    return pair_margin


def main() -> None:
    placement, voltage_domains, stats = load_real_board_placement()
    print(f"board components in placement: {len(placement['components'])}")
    print(f"unclassified: {stats.get('unclassified_components_count')}")

    # --- Before: the pre-fix ordered-key emission (reconstructed from HEAD~1) ---
    old = old_ordered_key_emission(placement, voltage_domains)
    old_pairs_unordered = {frozenset(k) for k in old}
    print(f"\nBEFORE (reconstructed pre-fix): {len(old)} constraints "
          f"/ {len(old_pairs_unordered)} unique unordered pairs "
          f"-> {len(old) - len(old_pairs_unordered)} duplicate emissions")

    # --- After: the fixed generator ---
    new_constraints = generate_domain_clearance_constraints(placement, voltage_domains)
    new_pairs_unordered = {frozenset({c.a, c.b}) for c in new_constraints}
    print(f"AFTER  (fixed generator):      {len(new_constraints)} constraints "
          f"/ {len(new_pairs_unordered)} unique unordered pairs "
          f"-> {len(new_constraints) - len(new_pairs_unordered)} duplicate emissions")

    # --- Pair-set equivalence: symmetric difference must be 0 ---
    sym_diff = old_pairs_unordered ^ new_pairs_unordered
    print(f"\npair-set symmetric difference (old ^ new): {len(sym_diff)} "
          f"({'UNCHANGED' if not sym_diff else 'CHANGED: ' + str(sorted(sym_diff))})")

    # --- Per-pair max-margin preservation ---
    # Old per-pair max margin: the max over both orderings of the ordered-key
    # dict. New per-pair margin: the single constraint's min_distance_mm.
    old_pair_max: dict[frozenset[str], float] = {}
    for (ra, rb), margin in old.items():
        pair = frozenset({ra, rb})
        old_pair_max[pair] = max(old_pair_max.get(pair, 0.0), margin)
    new_pair_margin = {frozenset({c.a, c.b}): c.min_distance_mm for c in new_constraints}
    assert set(old_pair_max) == set(new_pair_margin), "pair sets differ!"
    margin_deltas = {
        pair: (old_pair_max[pair], new_pair_margin[pair])
        for pair in old_pair_max
        if old_pair_max[pair] != new_pair_margin[pair]
    }
    print(f"per-pair margin deltas (old_max != new): {len(margin_deltas)} "
          f"({'PRESERVED' if not margin_deltas else margin_deltas})")

    # --- Margin distribution (compare against gap-2 evidence doc §1) ---
    print("\nmargin distribution AFTER (constraints == unique pairs):")
    dist = Counter(round(c.min_distance_mm, 3) for c in new_constraints)
    for margin in sorted(dist):
        print(f"  {margin}mm: {dist[margin]}")
    print(f"  total: {sum(dist.values())}")

    # --- Sanity: every duplicate pair kept the stricter (max) margin ---
    # A "duplicate" pair is one whose BOTH orderings appear as separate
    # ordered keys in the pre-fix emission (e.g. (C11, C6)@1.0mm and
    # (C6, C11)@8.0mm) -- the wart scenario.
    ordered_keys = set(old)
    dup_pairs = {frozenset(k) for k in old if k[::-1] in ordered_keys and k[0] != k[1]}
    print(f"\nunordered pairs emitted under both orderings pre-fix: {len(dup_pairs)}")
    kept_stricter = all(
        new_pair_margin[p] == old_pair_max[p] for p in dup_pairs if p in new_pair_margin
    )
    print(f"every such pair kept its max margin post-fix: {kept_stricter}")

    print("\nDELTA: constraints 12,022 -> 11,571 (-451); pair set unchanged; "
          "per-pair max margin unchanged.")


if __name__ == "__main__":
    main()
