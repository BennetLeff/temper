"""Tests for Stage invariants property (U1)."""


from temper_placer.validation.drc_fence import InvariantSpec

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState


class NoInvariantsStage(Stage):
    """Stage that does not override invariants."""

    @property
    def name(self) -> str:
        return "no_invariants"

    def run(self, state: BoardState) -> BoardState:
        return state


class WithInvariantsStage(Stage):
    """Stage that declares invariants."""

    @property
    def name(self) -> str:
        return "with_invariants"

    @property
    def invariants(self) -> tuple[InvariantSpec, ...]:
        return (
            InvariantSpec(
                check_name="drc_component_overlap",
                guarantees="No component overlaps after placement",
            ),
        )

    def run(self, state: BoardState) -> BoardState:
        return state


class TestStageInvariants:
    """Test Stage.invariants property."""

    def test_default_invariants_empty(self):
        """Stage with no invariants override returns empty tuple."""
        stage = NoInvariantsStage()
        assert stage.invariants == ()

    def test_custom_invariants(self):
        """Stage with invariants override returns the declared specs."""
        stage = WithInvariantsStage()
        assert len(stage.invariants) == 1
        assert stage.invariants[0].check_name == "drc_component_overlap"
        assert "No component overlaps" in stage.invariants[0].guarantees

    def test_invariants_is_tuple_of_invariant_spec(self):
        """Type: return is tuple[InvariantSpec, ...]."""
        stage = WithInvariantsStage()
        for inv in stage.invariants:
            assert isinstance(inv, InvariantSpec)

    def test_last_modified_regions_default_none(self):
        """Stage.last_modified_regions defaults to None."""
        stage = NoInvariantsStage()
        assert stage.last_modified_regions is None
