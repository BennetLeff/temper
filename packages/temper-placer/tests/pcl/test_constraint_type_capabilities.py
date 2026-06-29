"""TS4: ConstraintType capabilities and supported targets tests."""


from temper_placer.pcl.constraints import (
    CompilationTarget,
    ConstraintType,
    SemanticTag,
)


class TestConstraintTypeCapabilities:
    """Verify each ConstraintType has correct capabilities and supported_targets."""

    def test_adjacent_capabilities(self):
        ct = ConstraintType.ADJACENT
        assert ct.capabilities == frozenset({SemanticTag.PROXIMITY})
        assert ct.supported_targets == frozenset({
            CompilationTarget.JAX, CompilationTarget.SAT, CompilationTarget.DRC,
        })

    def test_separated_capabilities(self):
        ct = ConstraintType.SEPARATED
        assert ct.capabilities == frozenset({SemanticTag.SEPARATION, SemanticTag.ORDERING})
        assert CompilationTarget.SAT in ct.supported_targets

    def test_enclosing_capabilities(self):
        ct = ConstraintType.ENCLOSING
        assert ct.capabilities == frozenset({SemanticTag.ZONING})
        assert CompilationTarget.DRC in ct.supported_targets

    def test_aligned_capabilities(self):
        ct = ConstraintType.ALIGNED
        assert ct.capabilities == frozenset({SemanticTag.ALIGNMENT})
        # ALIGNED has no SAT grounding
        assert CompilationTarget.SAT not in ct.supported_targets
        assert CompilationTarget.JAX in ct.supported_targets
        assert CompilationTarget.DRC in ct.supported_targets

    def test_on_side_capabilities(self):
        ct = ConstraintType.ON_SIDE
        assert ct.capabilities == frozenset({SemanticTag.ZONING})

    def test_anchored_capabilities(self):
        ct = ConstraintType.ANCHORED
        assert ct.capabilities == frozenset({SemanticTag.ZONING})

    def test_loop_area_capabilities(self):
        ct = ConstraintType.LOOP_AREA
        assert ct.capabilities == frozenset({SemanticTag.PROXIMITY, SemanticTag.ORDERING})
        assert CompilationTarget.SAT in ct.supported_targets

    def test_value_preserved_for_serialization(self):
        """ConstraintType.value still returns the string form."""
        assert ConstraintType.SEPARATED.value == "separated"
        assert ConstraintType.ADJACENT.value == "adjacent"
        assert ConstraintType.ENCLOSING.value == "enclosing"

    def test_label_property(self):
        """ConstraintType.label returns the string form (backward compat)."""
        assert ConstraintType.LOOP_AREA.label == "loop_area"

    def test_all_types_have_capabilities(self):
        """Every ConstraintType member has a non-empty capabilities set."""
        for ct in ConstraintType:
            assert len(ct.capabilities) > 0, f"{ct} has empty capabilities"

    def test_all_types_have_supported_targets(self):
        """Every ConstraintType member has a non-empty supported_targets set."""
        for ct in ConstraintType:
            assert len(ct.supported_targets) > 0, f"{ct} has empty supported_targets"
            assert CompilationTarget.JAX in ct.supported_targets, (
                f"{ct} must support JAX target"
            )
