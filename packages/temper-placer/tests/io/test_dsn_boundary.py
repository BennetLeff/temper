import pytest

from temper_placer.io.boundary_registry import (
    BOUNDARY_NAMES,
    BoundaryDef,
    get_boundary,
    list_boundaries,
)


def test_list_boundaries_returns_thirteen_names():
    names = list_boundaries()
    assert names == [
        "semantic",
        "topological",
        "placement",
        "routing",
        "validation",
        "zone_geometry",
        "zone_assignment",
        "slot_generation",
        "component_assignment",
        "apply_placements",
        "courtyard_check",
        "apply_placements_reapply",
        "placement_validation",
    ]


def test_get_boundary_returns_valid_boundary_def():
    expected_pipeline_class = {
        "PipelineOrchestrator",
        "DeterministicPipeline",
    }
    expected_output_format = {"dsn", "json"}
    expected_serialization_fn = {
        "export_pcb",
        "serialize_boardstate_to_dsn",
        "serialize_violations_to_json",
    }
    for name in BOUNDARY_NAMES:
        bd = get_boundary(name)
        assert isinstance(bd, BoundaryDef)
        assert bd.output_format in expected_output_format
        assert bd.pipeline_class in expected_pipeline_class
        assert bd.serialization_fn in expected_serialization_fn


def test_get_boundary_placement_maps_to_geometric():
    bd = get_boundary("placement")
    assert bd.phase_name == "geometric"


def test_get_boundary_semantic_maps_to_semantic():
    bd = get_boundary("semantic")
    assert bd.phase_name == "semantic"


def test_get_boundary_validation_maps_to_output():
    bd = get_boundary("validation")
    assert bd.phase_name == "output"


def test_get_boundary_rejects_unknown_name():
    with pytest.raises(KeyError, match="Unknown boundary"):
        get_boundary("nonexistent")
