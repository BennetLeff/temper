"""TS4: CI gate — bridge registration completeness."""


from temper_placer.pcl.constraints import (
    BaseConstraint,
    CompilationTarget,
    ConstraintType,
)
from temper_placer.pcl.drc_bridge import TYPE_HANDLERS as DRC_TYPE_HANDLERS
from temper_placer.pcl.sat_bridge import TYPE_HANDLERS as SAT_TYPE_HANDLERS


class TestBridgeRegistrationCompleteness:
    """Every ConstraintType with SAT/DRC in supported_targets has a handler."""

    def test_all_sat_targets_have_handler(self):
        """Each type with SAT in supported_targets has a SAT handler."""
        missing = []
        for ct in ConstraintType:
            if CompilationTarget.SAT in ct.supported_targets and ct not in SAT_TYPE_HANDLERS:
                missing.append(ct)
        assert not missing, (
            f"ConstraintType(s) with SAT support but no handler: {missing}"
        )

    def test_all_drc_targets_have_handler(self):
        """Each type with DRC in supported_targets has a DRC handler."""
        missing = []
        for ct in ConstraintType:
            if CompilationTarget.DRC in ct.supported_targets and ct not in DRC_TYPE_HANDLERS:
                missing.append(ct)
        assert not missing, (
            f"ConstraintType(s) with DRC support but no handler: {missing}"
        )

    def test_backends_registry_has_all_targets(self):
        """BaseConstraint.backends contains entries for jax, sat, drc."""
        assert "jax" in BaseConstraint.backends, "jax backend missing"
        assert "sat" in BaseConstraint.backends, "sat backend missing"
        assert "drc" in BaseConstraint.backends, "drc backend missing"

    def test_sat_backend_is_callable(self):
        """The SAT backend is a callable."""
        assert callable(BaseConstraint.backends.get("sat"))

    def test_drc_backend_is_callable(self):
        """The DRC backend is a callable."""
        assert callable(BaseConstraint.backends.get("drc"))

    def test_no_handler_for_non_sat_type(self):
        """ALIGNED has no SAT grounding — handler returns []."""
        assert CompilationTarget.SAT not in ConstraintType.ALIGNED.supported_targets
