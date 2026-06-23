import pytest
from temper_placer.io.boundary_registry import (
    BoundaryRegistry,
    BoundaryDef,
    BOUNDARY_NAMES,
)


def test_list_boundaries_returns_five_names():
    names = BoundaryRegistry.list_boundaries()
    assert names == ["semantic", "topological", "placement", "routing", "validation"]


def test_get_boundary_returns_valid_boundary_def():
    for name in BOUNDARY_NAMES:
        bd = BoundaryRegistry.get_boundary(name)
        assert isinstance(bd, BoundaryDef)
        assert bd.output_format == "dsn"
        assert bd.pipeline_class == "PipelineOrchestrator"
        assert bd.serialization_fn == "export_pcb"


def test_get_boundary_placement_maps_to_geometric():
    bd = BoundaryRegistry.get_boundary("placement")
    assert bd.phase_name == "geometric"


def test_get_boundary_semantic_maps_to_semantic():
    bd = BoundaryRegistry.get_boundary("semantic")
    assert bd.phase_name == "semantic"


def test_get_boundary_validation_maps_to_output():
    bd = BoundaryRegistry.get_boundary("validation")
    assert bd.phase_name == "output"


def test_get_boundary_rejects_unknown_name():
    with pytest.raises(KeyError, match="Unknown boundary"):
        BoundaryRegistry.get_boundary("nonexistent")
