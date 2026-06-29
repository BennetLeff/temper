"""Tests for TypeGating — constraint classification into safety/performance/aesthetic.

Test scenarios: T-U2-1 through T-U2-7 from
docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md
"""

from __future__ import annotations

from temper_placer.router_v6.type_gating import (
    ConstraintKind,
    Rule,
    TypeGating,
    classify_constraint,
)

# ---------------------------------------------------------------------------
# T-U2-1: LayerConstraint → safety (default)
# ---------------------------------------------------------------------------


def test_layer_restriction_safety():
    """LayerConstraint is always Safety."""
    result = classify_constraint("layer_restriction", touches_hv=False)
    assert result == "safety"


# ---------------------------------------------------------------------------
# T-U2-2: DiffPairConstraint → performance
# ---------------------------------------------------------------------------


def test_diff_pair_performance():
    """DiffPairConstraint is Performance."""
    result = classify_constraint("diff_pair", touches_hv=False)
    assert result == "performance"


# ---------------------------------------------------------------------------
# T-U2-3: CapacityConstraint on HV-adjacent channel → safety
# ---------------------------------------------------------------------------


def test_hv_capacity_safety():
    """CapacityConstraint touching HV net → Safety."""
    result = classify_constraint("capacity", touches_hv=True)
    assert result == "safety"


# ---------------------------------------------------------------------------
# T-U2-4: CapacityConstraint on signal-only channel → performance
# ---------------------------------------------------------------------------


def test_signal_capacity_performance():
    """CapacityConstraint on signal-only channel → Performance."""
    result = classify_constraint("capacity", touches_hv=False)
    assert result == "performance"


# ---------------------------------------------------------------------------
# T-U2-5: Configurable mapping injection
# ---------------------------------------------------------------------------


def test_configurable_mapping():
    """TypeGating accepts alternative rules — capacity → aesthetic."""
    gating = TypeGating(rules=[
        Rule(kind="capacity", default_tier="aesthetic"),
        Rule(kind="diff_pair", default_tier="performance"),
        Rule(kind="layer_restriction", default_tier="safety"),
    ])
    result = gating.classify_constraint("capacity")
    assert result == "aesthetic"

    # Other kinds unchanged
    assert gating.classify_constraint("layer_restriction") == "safety"
    assert gating.classify_constraint("diff_pair") == "performance"


# ---------------------------------------------------------------------------
# T-U2-6: Bundle classification
# ---------------------------------------------------------------------------


def test_bundle_classification_diff_pair():
    """Diff-pair bundle → safety (layer) + performance (diff pair)."""
    gating = TypeGating()
    kinds: frozenset[ConstraintKind] = frozenset(["layer_restriction", "diff_pair"])
    types = gating.classify_bundle_constraints(kinds)
    assert "safety" in types
    assert "performance" in types


def test_bundle_classification_signal_only():
    """Plain signal bundle → performance only (capacity on signal channels)."""
    gating = TypeGating()
    kinds: frozenset[ConstraintKind] = frozenset(["capacity"])
    types = gating.classify_bundle_constraints(kinds, touches_hv=False)
    assert "performance" in types
    assert "safety" not in types


def test_bundle_classification_hv_signal():
    """Bundle with HV-adjacent capacity + layer → safety."""
    gating = TypeGating()
    kinds: frozenset[ConstraintKind] = frozenset(["capacity", "layer_restriction"])
    types = gating.classify_bundle_constraints(kinds, touches_hv=True)
    assert "safety" in types
    # capacity is safety (hv), layer is safety → only safety
    assert types == frozenset(["safety"])


# ---------------------------------------------------------------------------
# T-U2-7: Empty bundle
# ---------------------------------------------------------------------------


def test_empty_bundle():
    """No constraints → empty constraint_types set."""
    gating = TypeGating()
    types = gating.classify_bundle_constraints(frozenset())
    assert types == frozenset()


# ---------------------------------------------------------------------------
# SC3: No safety constraint is ever classified as Performance or Aesthetic
# ---------------------------------------------------------------------------


def test_safety_never_downgraded():
    """Safety constraints (layer) are never performance or aesthetic."""
    gating = TypeGating()
    # Test all default rules — layer_restriction is always safety
    for touches_hv in (True, False):
        t = gating.classify_constraint("layer_restriction", touches_hv=touches_hv)
        assert t == "safety", f"layer_restriction with touches_hv={touches_hv} was {t}"

    # HV capacity is safety
    t = gating.classify_constraint("capacity", touches_hv=True)
    assert t == "safety"


# ---------------------------------------------------------------------------
# hv_net_names integration
# ---------------------------------------------------------------------------


def test_hv_net_names_attribute():
    """TypeGating stores hv_net_names for downstream use."""
    gating = TypeGating(hv_net_names=frozenset(["AC_L", "AC_N"]))
    assert "AC_L" in gating.hv_net_names
    assert "SIG_A" not in gating.hv_net_names


def test_unknown_kind_defaults_to_safety():
    """Unknown constraint kinds default to safety (safe default)."""
    gating = TypeGating()
    result = gating.classify_constraint(None)  # type: ignore[arg-type]
    assert result == "safety"
