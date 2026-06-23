from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
import pytest

from temper_placer.deterministic.stages.clearance_grid import (
    ConfigError,
    _layer_index_to_name,
    effective_creepage,
    hv_pad_set,
)


def test_empty_grid_all_available():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
    assert grid.is_available(25, 25) == True
    assert grid.blocked_count == 0

def test_block_pad_with_clearance():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)

    # Block a 1mm pad at (25, 25) with 0.3mm clearance
    grid.block_circle(center=(25, 25), radius_mm=0.5, clearance_mm=0.3)

    # Center should be blocked
    assert grid.is_available(25, 25) == False

    # 0.5mm away (within pad) should be blocked
    assert grid.is_available(25.4, 25) == False

    # 0.9mm away (within clearance) should be blocked
    assert grid.is_available(25.7, 25) == False

    # 1.0mm away (outside clearance) should be available
    assert grid.is_available(26.0, 25) == True

def test_grid_is_deterministic():
    '''Same input produces same blocked cells.'''
    def build_grid():
        grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)
        grid.block_circle(center=(25, 25), radius_mm=0.5, clearance_mm=0.3)
        return grid.blocked_cells

    result1 = build_grid()
    result2 = build_grid()
    assert result1 == result2

def test_block_trace():
    grid = ClearanceGrid(width_mm=50, height_mm=50, cell_size_mm=0.5)

    # Block a horizontal trace from (20, 25) to (30, 25)
    # Width 1mm, Clearance 0mm (to keep it simple)
    path = [(20.0, 25.0), (30.0, 25.0)]
    grid.block_trace(path, width_mm=1.0, clearance_mm=0.0)

    # Points along the line should be blocked
    assert grid.is_available(20, 25) == False
    assert grid.is_available(25, 25) == False
    assert grid.is_available(30, 25) == False

    # Points just outside width should be available
    assert grid.is_available(25, 25.6) == True
    assert grid.is_available(25, 24.4) == True

    # Points at ends should be blocked within radius
    assert grid.is_available(19.6, 25) == False
    assert grid.is_available(19.4, 25) == True


# =============================================================================
# U1 tests: Per-Layer Creepage Helper and HV-Pad Set Resolution
# =============================================================================


class _StubZone:
    """Minimal duck-typed HV exclusion zone for unit tests."""

    def __init__(
        self,
        name="z",
        center=(0.0, 0.0),
        size=(10.0, 10.0),
        component_refdes=None,
    ):
        self.name = name
        self.center = center
        self.size = size
        self.component_refdes = component_refdes
        self.excluded_nets = []
        self.clearance_mm = 6.0


def test_effective_creepage_outer():
    assert effective_creepage("F.Cu", 6.0) == 6.0


def test_effective_creepage_back_copper():
    assert effective_creepage("B.Cu", 6.0) == 6.0


def test_effective_creepage_inner():
    # 0.3 factor per drc_oracle.py
    assert effective_creepage("In1.Cu", 6.0) == pytest.approx(1.8)
    assert effective_creepage("In2.Cu", 6.0) == pytest.approx(1.8)


def test_layer_index_to_name():
    assert _layer_index_to_name(0, 4) == "F.Cu"
    assert _layer_index_to_name(1, 4) == "In1.Cu"
    assert _layer_index_to_name(2, 4) == "In2.Cu"
    assert _layer_index_to_name(3, 4) == "B.Cu"


def test_hv_pad_set_includes_all_pins_of_hv_component():
    pads = [
        {"ref": "Q1", "name": "G"},
        {"ref": "Q1", "name": "D"},
        {"ref": "Q1", "name": "S"},
        {"ref": "D1", "name": "A"},
        {"ref": "D1", "name": "K"},
        {"ref": "R1", "name": "1"},
        {"ref": "R1", "name": "2"},
    ]
    zones = [
        _StubZone(name="q1", center=(10.0, 10.0), size=(5.0, 5.0), component_refdes="Q1"),
        _StubZone(name="d1", center=(20.0, 20.0), size=(5.0, 5.0), component_refdes="D1"),
    ]
    positions = {"Q1": (10.0, 10.0), "D1": (20.0, 20.0), "R1": (30.0, 30.0)}

    result = hv_pad_set(pads, zones, positions)

    assert ("Q1", "G") in result
    assert ("Q1", "D") in result
    assert ("Q1", "S") in result
    assert ("D1", "A") in result
    assert ("D1", "K") in result
    assert ("R1", "1") not in result
    assert ("R1", "2") not in result
    assert len(result) == 5


def test_hv_pad_set_unknown_refdes_raises():
    pads = [{"ref": "Q1", "name": "G"}]
    zones = [_StubZone(component_refdes="Q99")]
    positions = {"Q1": (10.0, 10.0)}

    with pytest.raises(ConfigError) as exc:
        hv_pad_set(pads, zones, positions)
    assert "Q99" in str(exc.value)


def test_hv_pad_set_uses_spatial_fallback_when_refdes_unset():
    """When a zone omits component_refdes, the closest component within
    the zone bounds is used. This preserves R6 (no required config change)
    while keeping R1 satisfiable (explicit refdes takes precedence)."""
    pads = [
        {"ref": "Q1", "name": "G"},
        {"ref": "Q1", "name": "D"},
        {"ref": "Q1", "name": "S"},
        {"ref": "R1", "name": "1"},
    ]
    zones = [_StubZone(name="q1_zone", center=(10.0, 10.0), size=(5.0, 5.0))]
    positions = {"Q1": (10.0, 10.0), "R1": (50.0, 50.0)}

    result = hv_pad_set(pads, zones, positions)

    assert ("Q1", "G") in result
    assert ("Q1", "D") in result
    assert ("Q1", "S") in result
    assert ("R1", "1") not in result


def test_hv_pad_set_spatial_fallback_no_component_raises():
    pads = [{"ref": "Q1", "name": "G"}]
    zones = [_StubZone(name="orphan", center=(100.0, 100.0), size=(5.0, 5.0))]
    positions = {"Q1": (10.0, 10.0)}

    with pytest.raises(ConfigError) as exc:
        hv_pad_set(pads, zones, positions)
    assert "orphan" in str(exc.value)


def test_hv_pad_set_empty_zones_returns_empty_set():
    pads = [{"ref": "Q1", "name": "G"}]
    result = hv_pad_set(pads, [], {"Q1": (0.0, 0.0)})
    assert result == set()


def test_helpers_do_not_mutate_grid():
    """The pure helpers must not mutate any grid state (R6)."""
    grid = ClearanceGrid(width_mm=20, height_mm=20, cell_size_mm=0.5)
    snapshot = grid.blocked_cells

    effective_creepage("F.Cu", 6.0)
    effective_creepage("In1.Cu", 6.0)
    _layer_index_to_name(0, 2)

    assert grid.blocked_cells == snapshot

