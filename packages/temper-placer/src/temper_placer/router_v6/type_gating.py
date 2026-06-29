"""
Type-Gating Policy — classify constraints as Safety, Performance, or Aesthetic.

Origin: U2 of docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md

Implements the configurable mapping from constraint kind → gating tier
with the default rule (R5.1):
  - LayerConstraint → Safety
  - DiffPairConstraint → Performance
  - CapacityConstraint on HV-adjacent channels → Safety
  - CapacityConstraint on signal-only channels → Performance
  - Aesthetic constraints → never lowered to SAT

References:
  - R3 (Safety eager), R4 (Performance lazy), R5 (Aesthetic never), R5.1
  - KD2 (Safety always eager — never lazy)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ConstraintType = Literal["safety", "performance", "aesthetic"]
ConstraintKind = Literal["capacity", "diff_pair", "layer_restriction"]


@dataclass
class Rule:
    """Classification rule: pair a constraint kind with a gating tier,
    optionally scoped to channels touching an HV net."""

    kind: ConstraintKind
    default_tier: ConstraintType
    hv_override_tier: ConstraintType | None = None


@dataclass
class TypeGating:
    """Configurable mapping from constraint kind → gating tier.

    Attributes:
        rules: Mapping from ConstraintKind to the default ConstraintType.
            Override per channel when the channel touches an HV net via
            the ``hv_override_tier`` field.
        hv_net_names: Set of net names classified as HV. Used to determine
            whether a constraint's channel is HV-adjacent.
    """

    rules: list[Rule] = field(default_factory=lambda: [
        Rule(kind="capacity", default_tier="performance", hv_override_tier="safety"),
        Rule(kind="diff_pair", default_tier="performance"),
        Rule(kind="layer_restriction", default_tier="safety"),
    ])
    hv_net_names: frozenset[str] = field(default_factory=frozenset)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_constraint(
        self,
        kind: ConstraintKind,
        channel_id: str = "",
        touches_hv: bool = False,
    ) -> ConstraintType:
        """Classify a single constraint by kind and channel context.

        Args:
            kind: The constraint kind ("capacity", "diff_pair", "layer_restriction").
            channel_id: Channel identifier (for logging only).
            touches_hv: Whether the constraint's channel is adjacent to an HV net.

        Returns:
            One of "safety", "performance", "aesthetic".
        """
        _ = channel_id  # reserved for future use
        for rule in self.rules:
            if rule.kind == kind:
                if touches_hv and rule.hv_override_tier is not None:
                    return rule.hv_override_tier
                return rule.default_tier
        return "safety"  # unknown kinds default to safety

    def classify_bundle_constraints(
        self,
        bundle_constraint_kinds: frozenset[ConstraintKind],
        touches_hv: bool = False,
    ) -> frozenset[ConstraintType]:
        """Classify all constraint kinds present in a bundle.

        Args:
            bundle_constraint_kinds: Set of constraint kinds applicable.
            touches_hv: Whether any channel touching the bundle is HV-adjacent.

        Returns:
            Frozenset of ConstraintType values for the bundle.
        """
        types: set[ConstraintType] = set()
        for kind in sorted(bundle_constraint_kinds):
            types.add(self.classify_constraint(kind, touches_hv=touches_hv))
        return frozenset(types)


# ------------------------------------------------------------------
# Module-level convenience helpers
# ------------------------------------------------------------------

DEFAULT_GATING = TypeGating()


def classify_constraint(
    kind: ConstraintKind,
    touches_hv: bool = False,
) -> ConstraintType:
    """Convenience: classify using the default gating rules."""
    return DEFAULT_GATING.classify_constraint(kind, touches_hv=touches_hv)
