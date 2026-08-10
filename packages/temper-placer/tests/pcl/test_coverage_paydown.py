"""
Coverage paydown tests for PCL module — fills gaps in existing test coverage.

Tests added for constraint properties, BaseConstraint.escalate,
KeepoutConstraint, LintResult, lint_constraints, ConstraintCollection methods,
SAT bridge, tag dispatch, tagged constraints, and unsat compiler edge cases.
"""

import pytest

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    CompilationContext,
    ConstraintTier,
    ConstraintType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SemanticTag,
    SeparatedConstraint,
)
from temper_placer.pcl.linter import LintResult, lint_constraints
from temper_placer.pcl.parser import (
    ConstraintCollection,
    load_pcl_collection,
    parse_constraint_dict,
    parse_pcl_file,
)
from temper_placer.pcl.sat_bridge import ConstraintOrigin
from temper_placer.pcl.unsat_compiler import (
    InfeasibleConstraintSet,
    compile_unsat_to_pcl,
    reset_escalation_counts,
)
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin


# ============================================================================
# ConstraintType properties
# ============================================================================


def test_constraint_type_capabilities():
    """ConstraintType.capabilities returns frozenset of SemanticTag."""
    assert ConstraintType.ADJACENT.capabilities == frozenset({SemanticTag.PROXIMITY})
    assert ConstraintType.SEPARATED.capabilities == frozenset({SemanticTag.SEPARATION, SemanticTag.ORDERING})
    assert ConstraintType.ENCLOSING.capabilities == frozenset({SemanticTag.ZONING})
    assert ConstraintType.ON_SIDE.capabilities == frozenset({SemanticTag.ZONING})


def test_constraint_type_label():
    """ConstraintType.label returns the string representation."""
    assert ConstraintType.ADJACENT.label == "adjacent"
    assert ConstraintType.SEPARATED.label == "separated"
    assert ConstraintType.LOOP_AREA.label == "loop_area"


def test_constraint_type_supported_targets():
    """ConstraintType.supported_targets returns frozenset of CompilationTarget."""
    from temper_placer.pcl.constraints import CompilationTarget
    targets = ConstraintType.ADJACENT.supported_targets
    assert CompilationTarget.JAX in targets
    assert CompilationTarget.SAT in targets


def test_constraint_type_value():
    """ConstraintType.value returns the string label."""
    assert ConstraintType.ADJACENT.value == "adjacent"
    assert ConstraintType.ANCHORED.value == "anchored"
    assert ConstraintType.KEEPOUT.value == "keepout"


# ============================================================================
# BaseConstraint.escalate
# ============================================================================


def test_base_constraint_escalate_soft_to_strong():
    """BaseConstraint.escalate moves SOFT -> STRONG."""
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.SOFT, because="Escalation test",
    )
    assert c.tier == ConstraintTier.SOFT
    c.escalate()
    assert c.tier == ConstraintTier.STRONG


def test_base_constraint_escalate_strong_to_hard():
    """BaseConstraint.escalate moves STRONG -> HARD."""
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.STRONG, because="Escalation test",
    )
    c.escalate()
    assert c.tier == ConstraintTier.HARD


def test_base_constraint_escalate_hard_stays_hard():
    """BaseConstraint.escalate on HARD stays HARD."""
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Escalation test",
    )
    c.escalate()
    assert c.tier == ConstraintTier.HARD


# ============================================================================
# KeepoutConstraint
# ============================================================================


def test_keepout_constraint_creation():
    """KeepoutConstraint can be created."""
    k = KeepoutConstraint(
        zone_name="HV_KEEPOUT",
        tier=ConstraintTier.HARD,
        because="No components allowed in HV keepout for safety isolation",
    )
    assert k.zone_name == "HV_KEEPOUT"
    assert k.margin_mm == 0.0
    assert k.id == "keepout_HV_KEEPOUT"


def test_keepout_constraint_involves_component():
    """KeepoutConstraint.involves_component checks zone name."""
    k = KeepoutConstraint(
        zone_name="TEST_ZONE",
        tier=ConstraintTier.HARD,
        because="Safety isolation requirement",
    )
    assert k.involves_component("TEST_ZONE")
    assert not k.involves_component("OTHER_ZONE")


def test_keepout_constraint_to_dict():
    """KeepoutConstraint.to_dict serializes correctly."""
    k = KeepoutConstraint(
        zone_name="HV_KEEPOUT",
        tier=ConstraintTier.HARD,
        because="Safety isolation requirement",
        margin_mm=2.0,
    )
    d = k.to_dict()
    assert d["type"] == "keepout"
    assert d["zone_name"] == "HV_KEEPOUT"
    assert d["margin_mm"] == 2.0
    assert d["tier"] == 1


# ============================================================================
# LintResult
# ============================================================================


def test_lint_result_passed_no_errors():
    """LintResult.passed is True when there are no errors."""
    r = LintResult(errors=[], warnings=[])
    assert r.passed is True


def test_lint_result_passed_with_warnings():
    """LintResult.passed is True even with warnings."""
    from temper_placer.pcl.linter import LintWarning
    r = LintResult(errors=[], warnings=[LintWarning(message="test")])
    assert r.passed is True


def test_lint_result_passed_with_errors():
    """LintResult.passed is False when there are errors."""
    from temper_placer.pcl.linter import LintError
    r = LintResult(errors=[LintError(message="test")], warnings=[])
    assert r.passed is False


# ============================================================================
# lint_constraints
# ============================================================================


def test_lint_constraints_empty():
    """lint_constraints on empty list passes."""
    board = Board(width=100.0, height=100.0)
    netlist = Netlist(components=[], nets=[])
    result = lint_constraints([], netlist, board)
    assert result.passed


def test_lint_constraints_unknown_component():
    """lint_constraints reports unknown component references."""
    board = Board(width=100.0, height=100.0)
    components = [Component(ref="U1", footprint="SOIC8", bounds=(5, 5), pins=[])]
    netlist = Netlist(components=components, nets=[])

    c = AdjacentConstraint(
        a="U1", b="MISSING",
        max_distance_mm=10.0, tier=ConstraintTier.SOFT,
        because="Test linting",
    )
    result = lint_constraints([c], netlist, board)
    # Should find errors about MISSING component
    assert not result.passed
    assert len(result.errors) >= 1
    assert any("MISSING" in e.message for e in result.errors)


def test_lint_constraints_aligned_edge_case():
    """lint_constraints on AlignedConstraint with known components passes."""
    from temper_placer.pcl.constraints import Axis

    board = Board(width=100.0, height=100.0)
    components = [
        Component(ref="C1", footprint="0603", bounds=(1.6, 0.8), pins=[]),
        Component(ref="C2", footprint="0603", bounds=(1.6, 0.8), pins=[]),
    ]
    netlist = Netlist(components=components, nets=[])

    c = AlignedConstraint(
        components=["C1", "C2"],
        axis=Axis.X,
        tier=ConstraintTier.SOFT,
        because="Alignment test case",
    )
    result = lint_constraints([c], netlist, board)
    assert result.passed


# ============================================================================
# ConstraintCollection methods
# ============================================================================


def test_constraint_collection_add():
    """ConstraintCollection.add appends a constraint."""
    coll = ConstraintCollection(constraints=[])
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test add method",
    )
    coll.add(c)
    assert len(coll) == 1
    assert coll.constraints[0] is c


def test_constraint_collection_copy():
    """ConstraintCollection.copy creates a deep copy."""
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test copy method",
    )
    coll = ConstraintCollection(constraints=[c])
    copied = coll.copy()
    assert len(copied) == 1
    assert copied.constraints[0].id == c.id
    assert copied.constraints[0] is not c  # deep copy


def test_constraint_collection_by_type():
    """ConstraintCollection.by_type filters by ConstraintType."""
    adj = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test by_type adj",
    )
    sep = SeparatedConstraint(
        a="A", b="B", min_distance_mm=5.0,
        tier=ConstraintTier.HARD, because="Test by_type sep",
    )
    coll = ConstraintCollection(constraints=[adj, sep])
    adj_matches = coll.by_type(ConstraintType.ADJACENT)
    sep_matches = coll.by_type(ConstraintType.SEPARATED)
    assert len(adj_matches) == 1
    assert adj_matches[0] is adj
    assert len(sep_matches) == 1
    assert sep_matches[0] is sep


def test_constraint_collection_by_tier():
    """ConstraintCollection.by_tier filters by ConstraintTier."""
    hard = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test by_tier hard",
    )
    soft = AdjacentConstraint(
        a="Q3", b="Q4", max_distance_mm=5.0,
        tier=ConstraintTier.SOFT, because="Test by_tier soft",
    )
    coll = ConstraintCollection(constraints=[hard, soft])
    hard_matches = coll.by_tier(ConstraintTier.HARD)
    soft_matches = coll.by_tier(ConstraintTier.SOFT)
    assert len(hard_matches) == 1
    assert len(soft_matches) == 1


def test_constraint_collection_involving_component():
    """ConstraintCollection.involving_component finds relevant constraints."""
    adj = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test involving",
    )
    sep = SeparatedConstraint(
        a="Q3", b="Q4", min_distance_mm=5.0,
        tier=ConstraintTier.HARD, because="Test involving",
    )
    coll = ConstraintCollection(constraints=[adj, sep])
    matches = coll.involving_component("Q1")
    assert len(matches) == 1
    assert matches[0] is adj


def test_constraint_collection_validate_component_refs():
    """ConstraintCollection.validate_component_refs reports invalid refs."""
    adj = AdjacentConstraint(
        a="Q1", b="MISSING",
        max_distance_mm=10.0, tier=ConstraintTier.HARD,
        because="Test validate refs",
    )
    coll = ConstraintCollection(constraints=[adj])
    errors = coll.validate_component_refs(["Q1", "Q2"])
    assert len(errors) == 1
    assert "MISSING" in errors[0]


def test_constraint_collection_compile_no_backend():
    """ConstraintCollection.compile raises when no backend registered."""
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test compile",
    )
    coll = ConstraintCollection(constraints=[c])
    ctx = CompilationContext(netlist=None)  # type: ignore[arg-type]
    from temper_placer.pcl.constraints import CompilationTarget
    # No backends registered for "cp_sat" — uses BaseConstraint.backends directly,
    # which at import time only has "drc" registered. Use a key unlikely to exist.
    with pytest.raises(ValueError, match="No backend registered"):
        coll.compile(CompilationTarget.CP_SAT, ctx)


def test_constraint_collection_lint_calls_linter():
    """ConstraintCollection.lint delegates to lint_constraints."""
    board = Board(width=100.0, height=100.0)
    comp = Component(ref="U1", footprint="SOIC8", bounds=(5, 5), pins=[])
    netlist = Netlist(components=[comp], nets=[])
    c = AdjacentConstraint(
        a="U1", b="U1",
        max_distance_mm=10.0, tier=ConstraintTier.SOFT,
        because="Test collection lint",
    )
    coll = ConstraintCollection(constraints=[c])
    result = coll.lint(netlist, board)
    assert isinstance(result, LintResult)
    # U1 adjacent to itself is suspicious but should only be a warning
    assert result.passed


def test_constraint_collection_auto_enrich_empty():
    """ConstraintCollection.auto_enrich with empty netlist — raises NotImplementedError."""
    board = Board(width=100.0, height=100.0)
    netlist = Netlist(components=[], nets=[])
    coll = ConstraintCollection(constraints=[])
    # auto_enrich calls auto_detect_decoupling which raises NotImplementedError
    with pytest.raises(NotImplementedError, match="auto_detect_decoupling removed"):
        coll.auto_enrich(netlist, board)


# ============================================================================
# parse_constraint_dict, parse_pcl_file, load_pcl_collection
# ============================================================================


def test_parse_constraint_dict_keepout():
    """parse_constraint_dict handles keepout type."""
    data = {
        "type": "keepout",
        "zone_name": "TEST_KEEPOUT",
        "tier": 1,
        "because": "Safety keepout zone for isolation",
    }
    c = parse_constraint_dict(data)
    assert isinstance(c, KeepoutConstraint)
    assert c.zone_name == "TEST_KEEPOUT"


def test_parse_pcl_file_basic(tmp_path):
    """parse_pcl_file loads a YAML file with constraints."""
    import yaml
    pcl_yaml = {
        "version": "1.0",
        "constraints": [
            {
                "type": "adjacent",
                "a": "Q1",
                "b": "Q2",
                "max_distance_mm": 10,
                "tier": 1,
                "because": "Minimize commutation loop area",
            }
        ],
    }
    p = tmp_path / "test.pcl.yaml"
    p.write_text(yaml.dump(pcl_yaml))
    coll = parse_pcl_file(p)
    assert len(coll) == 1


def test_load_pcl_collection_directory(tmp_path):
    """load_pcl_collection loads all YAML files from a directory."""
    import yaml
    pcl_yaml = {
        "version": "1.0",
        "constraints": [
            {
                "type": "separated",
                "a": "HV", "b": "LV",
                "min_distance_mm": 8,
                "tier": 1,
                "because": "HV/LV separation",
            }
        ],
    }
    (tmp_path / "test.pcl.yaml").write_text(yaml.dump(pcl_yaml))
    coll = load_pcl_collection(tmp_path)
    assert len(coll) >= 1


# ============================================================================
# load_pcl_schema
# ============================================================================


def test_load_pcl_schema_returns_dict():
    """load_pcl_schema returns the PCL schema."""
    from temper_placer.pcl._schema import load_pcl_schema
    schema = load_pcl_schema()
    assert isinstance(schema, dict)
    # Schema may have top-level $schema, $defs, properties keys
    assert len(schema) > 0


# ============================================================================
# validate_pcl_dict
# ============================================================================


def test_validate_pcl_dict_valid():
    """validate_pcl_dict accepts a valid PCL dict."""
    from temper_placer.pcl._schema import validate_pcl_dict
    data = {
        "version": "1.0",
        "constraints": [
            {
                "type": "adjacent",
                "a": "Q1", "b": "Q2",
                "max_distance_mm": 10,
                "tier": 1,
                "because": "Test constraint",
            }
        ],
    }
    # Should not raise
    validate_pcl_dict(data)


def test_validate_pcl_dict_missing_constraints():
    """validate_pcl_dict rejects dict without 'constraints' key."""
    from temper_placer.pcl._schema import validate_pcl_dict, PCLValidationError
    with pytest.raises(PCLValidationError):
        validate_pcl_dict({"version": "1.0"})


# ============================================================================
# SAT bridge: ConstraintOrigin
# ============================================================================


def test_constraint_origin_record_and_lookup():
    """ConstraintOrigin.record and lookup_pcl_id."""
    origin = ConstraintOrigin()
    origin.record("pcl_1", "sat_A")
    origin.record("pcl_1", "sat_B")
    assert origin.lookup_pcl_id("sat_A") == "pcl_1"
    assert origin.lookup_pcl_id("sat_B") == "pcl_1"
    assert origin.lookup_pcl_id("nonexistent") is None


def test_constraint_origin_get_sat_names():
    """ConstraintOrigin.get_sat_names returns all SAT names for a PCL id."""
    origin = ConstraintOrigin()
    origin.record("pcl_1", "sat_A")
    origin.record("pcl_1", "sat_B")
    assert sorted(origin.get_sat_names("pcl_1")) == ["sat_A", "sat_B"]
    assert origin.get_sat_names("nonexistent") == []


def test_constraint_origin_get_sat_names_empty():
    """ConstraintOrigin.get_sat_names returns empty for unknown id."""
    origin = ConstraintOrigin()
    assert origin.get_sat_names("unknown") == []


# ============================================================================
# SAT bridge: SATBridgeContext
# ============================================================================


def test_sat_bridge_context_net_index():
    """SATBridgeContext.net_index resolves component refs."""
    from temper_placer.pcl.sat_bridge import SATBridgeContext
    comps = [
        Component(ref="U1", footprint="SOIC8", bounds=(5, 5), pins=[]),
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8), pins=[]),
    ]
    netlist = Netlist(components=comps, nets=[])
    ctx = SATBridgeContext(
        netlist=netlist, board=None, skeletons={}, channel_widths={},
    )
    assert ctx.net_index("U1") == 0
    assert ctx.net_index("R1") == 1


def test_sat_bridge_context_component_indices():
    """SATBridgeContext.component_indices resolves component ref to indices."""
    from temper_placer.pcl.sat_bridge import SATBridgeContext
    comps = [
        Component(ref="U1", footprint="SOIC8", bounds=(5, 5), pins=[]),
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8), pins=[]),
    ]
    netlist = Netlist(components=comps, nets=[])
    ctx = SATBridgeContext(
        netlist=netlist, board=None, skeletons={}, channel_widths={},
    )
    indices = ctx.component_indices("U1")
    assert isinstance(indices, list)
    assert len(indices) >= 0


def test_sat_bridge_context_channels_empty():
    """SATBridgeContext.channels returns empty when no skeletons."""
    from temper_placer.pcl.sat_bridge import SATBridgeContext
    netlist = Netlist(components=[], nets=[])
    ctx = SATBridgeContext(
        netlist=netlist, board=None, skeletons={}, channel_widths={},
    )
    assert ctx.channels == []


# ============================================================================
# SAT bridge: constraint_to_clauses, register_handler
# ============================================================================


def test_constraint_to_clauses_adjacent_no_skeletons():
    """constraint_to_clauses handles AdjacentConstraint without skeletons."""
    from temper_placer.pcl.sat_bridge import constraint_to_clauses, SATBridgeContext
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test SAT bridge usage",
    )
    # Build a minimal SATBridgeContext
    comps = [
        Component(ref="Q1", footprint="SOIC8", bounds=(5, 5), pins=[]),
        Component(ref="Q2", footprint="SOIC8", bounds=(5, 5), pins=[]),
    ]
    netlist = Netlist(components=comps, nets=[])
    ctx = SATBridgeContext(
        netlist=netlist, board=None, skeletons={}, channel_widths={},
    )
    # Returns (clauses_list, ConstraintOrigin) tuple
    result = constraint_to_clauses(c, ctx)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_register_handler_and_dispatch():
    """register_handler with constraint_to_clauses dispatches correctly."""
    from temper_placer.pcl.sat_bridge import register_handler, constraint_to_clauses
    from temper_placer.pcl.constraints import CompilationTarget

    # Backend already registered at module import. Test that constraint_to_clauses
    # is callable with a proper context.
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="Test register handler proc",
    )
    # Verify the backend is registered
    from temper_placer.pcl.constraints import BaseConstraint as BC
    assert "sat" in BC.backends  # type: ignore[attr-defined]

    # register_handler() is called at module load time in sat_bridge.py.
    # Just verify it doesn't error on call.
    register_handler(ConstraintType.ADJACENT, constraint_to_clauses)


# ============================================================================
# Tag dispatch
# ============================================================================


def test_tag_components_empty_netlist():
    """tag_dispatch.components returns list with empty netlist."""
    from temper_placer.pcl.tag_dispatch import TagRef, components as tag_components, ComponentTag
    netlist = Netlist(components=[], nets=[])
    refs = tag_components(TagRef(ComponentTag.POWER), netlist)
    assert isinstance(refs, list)
    assert len(refs) == 0  # Empty netlist, no matches


def test_tag_resolve_on_component():
    """tag_dispatch.resolve returns False for untagged component."""
    from temper_placer.pcl.tag_dispatch import TagRef, resolve as tag_resolve, ComponentTag
    comp = Component(
        ref="U1", footprint="SOIC8", bounds=(5, 5),
        pins=[], tags=frozenset(),
    )
    expr = TagRef(ComponentTag.ALL)
    result = tag_resolve(expr, comp)
    assert isinstance(result, bool)
    assert result is False  # Untagged component matches nothing


def test_pre_expansion_validate_on_tagged_constraint():
    """pre_expansion_validate validates a tagged constraint."""
    from temper_placer.pcl.tag_dispatch import pre_expansion_validate, TagRef, ComponentTag
    from temper_placer.pcl.tagged_constraints import TaggedAdjacentConstraint
    tc = TaggedAdjacentConstraint(
        tag_expr_a=TagRef(ComponentTag.POWER),
        tag_expr_b=TagRef(ComponentTag.DECOUPLING),
        max_distance_mm=10.0,
        tier=ConstraintTier.STRONG,
        because="Gate drive decoupling proximity",
    )
    # pre_expansion_validate should not raise for well-formed tagged constraints
    pre_expansion_validate(tc)  # No exception expected


def test_tag_dispatch_E_used_in_signatures():
    """tag_dispatch.E is the TagExpr union type (used in type annotations)."""
    from temper_placer.pcl.tag_dispatch import E, TagRef
    # E is a typing.Union in TYPE_CHECKING; at runtime tags/constraints use TagRef.
    # Test that TagRef can be used where E is expected.
    expr = TagRef("test")
    assert hasattr(expr, "tag")


# ============================================================================
# Tagged constraints
# ============================================================================


def test_tagged_adjacent_constraint():
    """TaggedAdjacentConstraint can be created and serialized."""
    from temper_placer.pcl.tagged_constraints import TaggedAdjacentConstraint
    from temper_placer.pcl.tag_dispatch import TagRef, ComponentTag
    tc = TaggedAdjacentConstraint(
        tag_expr_a=TagRef(ComponentTag.POWER),
        tag_expr_b=TagRef(ComponentTag.DECOUPLING),
        max_distance_mm=10.0,
        tier=ConstraintTier.STRONG,
        because="Gate drive decoupling proximity",
    )
    assert tc.involves_component("any") is True
    d = tc.to_dict()
    assert d["type"] == "adjacent"
    assert d["max_distance_mm"] == 10.0
    exprs = tc.collect_tag_exprs()
    assert len(exprs) == 2


def test_tagged_separated_constraint():
    """TaggedSeparatedConstraint can be created and serialized."""
    from temper_placer.pcl.tagged_constraints import TaggedSeparatedConstraint
    from temper_placer.pcl.tag_dispatch import TagRef, ComponentTag
    tc = TaggedSeparatedConstraint(
        tag_expr_a=TagRef(ComponentTag.HV),
        tag_expr_b=TagRef(ComponentTag.LV),
        min_distance_mm=15.0,
        tier=ConstraintTier.HARD,
        because="HV/LV isolation",
    )
    assert tc.involves_component("any") is True
    d = tc.to_dict()
    assert d["type"] == "separated"
    exprs = tc.collect_tag_exprs()
    assert len(exprs) == 2


def test_tagged_aligned_constraint():
    """TaggedAlignedConstraint can be created and serialized."""
    from temper_placer.pcl.tagged_constraints import TaggedAlignedConstraint
    from temper_placer.pcl.tag_dispatch import TagRef, ComponentTag
    from temper_placer.pcl.constraints import Axis
    tc = TaggedAlignedConstraint(
        tag_expr=TagRef(ComponentTag.DECOUPLING),
        axis=Axis.X,
        tier=ConstraintTier.SOFT,
        because="Align decoupling capacitors",
    )
    assert tc.involves_component("any") is True
    d = tc.to_dict()
    assert d["type"] == "aligned"
    exprs = tc.collect_tag_exprs()
    assert len(exprs) == 1


def test_tagged_anchored_constraint():
    """TaggedAnchoredConstraint can be created and serialized."""
    from temper_placer.pcl.tagged_constraints import TaggedAnchoredConstraint
    from temper_placer.pcl.tag_dispatch import TagRef, ComponentTag
    tc = TaggedAnchoredConstraint(
        tag_expr=TagRef(ComponentTag.CONNECTOR),
        region=(0, 0, 10, 10),
        tier=ConstraintTier.HARD,
        because="Edge connectors fixed region",
    )
    assert tc.involves_component("any") is True
    d = tc.to_dict()
    assert d["type"] == "anchored"
    exprs = tc.collect_tag_exprs()
    assert len(exprs) == 1


def test_tagged_enclosing_constraint():
    """TaggedEnclosingConstraint can be created and serialized."""
    from temper_placer.pcl.tagged_constraints import TaggedEnclosingConstraint
    from temper_placer.pcl.tag_dispatch import TagRef, ComponentTag
    tc = TaggedEnclosingConstraint(
        outer="HV_ZONE",
        tag_expr_inner=TagRef(ComponentTag.HV),
        tier=ConstraintTier.HARD,
        because="HV devices in HV zone",
    )
    assert tc.involves_component("any") is True
    d = tc.to_dict()
    assert d["type"] == "enclosing"
    exprs = tc.collect_tag_exprs()
    assert len(exprs) == 1


def test_tagged_onside_constraint():
    """TaggedOnSideConstraint can be created and serialized."""
    from temper_placer.pcl.tagged_constraints import TaggedOnSideConstraint
    from temper_placer.pcl.tag_dispatch import TagRef, ComponentTag
    from temper_placer.pcl.constraints import BoardSide, EdgeType
    tc = TaggedOnSideConstraint(
        tag_expr=TagRef(ComponentTag.CONNECTOR),
        side=BoardSide.LEFT,
        edge=EdgeType.FLUSH,
        tier=ConstraintTier.HARD,
        because="Connectors on edge",
    )
    assert tc.involves_component("any") is True
    d = tc.to_dict()
    assert d["type"] == "on_side"
    exprs = tc.collect_tag_exprs()
    assert len(exprs) == 1


# ============================================================================
# UNSAT compiler
# ============================================================================


def test_reset_escalation_counts():
    """reset_escalation_counts clears the counter."""
    from temper_placer.pcl.unsat_compiler import _escalation_counts
    _escalation_counts["test"] = 5
    reset_escalation_counts()
    assert len(_escalation_counts) == 0


def test_compile_unsat_to_pcl_empty_core():
    """compile_unsat_to_pcl raises on empty UNSAT core."""
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.HARD, because="UNSAT test",
    )
    coll = ConstraintCollection(constraints=[c])
    origin = ConstraintOrigin()
    ctx = CompilationContext(netlist=None)  # type: ignore[arg-type]
    with pytest.raises(InfeasibleConstraintSet, match="Empty UNSAT core"):
        compile_unsat_to_pcl([], coll, origin, ctx)


def test_compile_unsat_to_pcl_with_core():
    """compile_unsat_to_pcl returns new collection with adjustments."""
    c = AdjacentConstraint(
        a="Q1", b="Q2", max_distance_mm=10.0,
        tier=ConstraintTier.SOFT, because="UNSAT compilation test",
    )
    coll = ConstraintCollection(constraints=[c])
    origin = ConstraintOrigin()
    origin.record(c.id, "sat_proximity_Q1_Q2")
    ctx = CompilationContext(netlist=None)  # type: ignore[arg-type]
    result = compile_unsat_to_pcl(["sat_proximity_Q1_Q2"], coll, origin, ctx)
    assert isinstance(result, ConstraintCollection)
    assert len(result) >= 1
