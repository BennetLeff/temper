from temper_placer.deterministic.stages.clearance_grid import (
    ClearanceGrid,
    ClearanceGridStage,
    ConfigError,
    _EXPANSION_LOG,
    _layer_index_to_name,
    effective_creepage,
    hv_pad_set,
)
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import HVExclusionZone
import pytest


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


# =============================================================================
# U2 tests: Pre-Route Creepage Expansion Pass
# =============================================================================


def _make_board_state(
    board_width: float = 50.0,
    board_height: float = 50.0,
    components=None,
    nets=None,
    placements=None,
) -> BoardState:
    """Build a BoardState populated with the given netlist + placements.

    Helper for U2/U3 tests so we can drive `ClearanceGridStage.run` directly
    without going through the full pipeline.
    """
    board = Board(width=board_width, height=board_height)
    if components is None or nets is None:
        netlist = Netlist(components=[], nets=[])
    else:
        netlist = Netlist(components=components, nets=nets)
    return BoardState(
        board=board,
        netlist=netlist,
        placements=placements or frozenset(),
    )


def _make_pad_size(width: float, height: float, shape: str = "circle"):
    """Build a pad_sizes entry compatible with the stage's `real_pad.size.X`
    and `real_pad.shape` access pattern."""
    class _Size:
        def __init__(self, w, h):
            self.X = w
            self.Y = h

    class _Pad:
        def __init__(self, w, h, shape):
            self.size = _Size(w, h)
            self.shape = shape
            self.rotation = 0.0

    return _Pad(width, height, shape)


def _run_grid_stage(
    state,
    hv_exclusion_zones=None,
    layer_count=2,
    cell_size_mm=0.5,
    pad_sizes=None,
    net_class_clearances=None,
):
    """Run a minimal ClearanceGridStage.

    Defaults: max_clearance_mm=0.2, Signal clearance 0.2, small HV clearance
    so the standard blocking does not dominate the expansion. Tests can
    override via the keyword args.
    """
    if net_class_clearances is None:
        net_class_clearances = {"Signal": 0.2, "HighVoltage": 0.2}
    stage = ClearanceGridStage(
        cell_size_mm=cell_size_mm,
        layer_count=layer_count,
        max_clearance_mm=0.2,
        net_class_clearances=net_class_clearances,
        net_classes={},
        pth_mask_expansion_mm=0.0,  # zero so the math is predictable
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        hv_exclusion_zones=hv_exclusion_zones or [],
        default_trace_width_mm=0.0,  # zero so the math is predictable
        pad_sizes=pad_sizes or {},
    )
    return stage.run(state)


def test_expansion_circular_pad_grows_radius():
    """A circular HV pad on F.Cu is blocked at radius r + 6.0 - 0.5*cell,
    but not at r + 6.0 + 0.5*cell. Validates the boundary is exact to
    within one cell, not conservatively over-blocked."""
    cell = 0.5
    pos = (25.0, 25.0)
    eff = 6.0
    pad_w = 2.0  # -> pad_radius = 1.0

    pin = Pin(name="1", number="1", position=(0.0, 0.0), net="HV",
              shape="circle", layer="F.Cu", width=pad_w, height=pad_w)
    comp = Component(ref="Q1", footprint="TO-247", bounds=(10.0, 10.0),
                     pins=[pin], net_class="HighVoltage", initial_position=pos)
    net = Net(name="HV", pins=[("Q1", "1")], net_class="HighVoltage")
    netlist = Netlist(components=[comp], nets=[net])

    state = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=netlist,
    )

    pad_sizes = {("Q1", "1"): _make_pad_size(pad_w, pad_w, "circle")}

    zone = HVExclusionZone(
        name="q1_zone", center=pos, size=(10.0, 10.0),
        clearance_mm=6.0, component_refdes="Q1",
    )

    result = _run_grid_stage(
        state, hv_exclusion_zones=[zone], layer_count=2,
        cell_size_mm=cell, pad_sizes=pad_sizes,
    )
    grid = result.grid
    assert grid is not None

    # Pad at (25, 25) with pad_radius=1.0, eff=6.0: threshold = 7.0.
    # cell at col=63, row=50: center (31.75, 25.25), dist = 6.755 < 7.0
    # cell at col=64, row=50: center (32.25, 25.25), dist = 7.254 > 7.0
    in_x = 63 * cell + cell / 2
    out_x = 64 * cell + cell / 2
    sample_y = 50 * cell + cell / 2

    assert grid.is_available(in_x, sample_y, layer=0) is False
    assert grid.is_available(out_x, sample_y, layer=0) is True


def test_expansion_rect_pad_grows_each_side():
    """A rect HV pad on F.Cu is blocked at corners offset by (eff, eff) from
    the rect bbox, not blocked just outside."""
    cell = 0.5
    eff = 6.0
    pos = (25.0, 25.0)
    pad_w, pad_h = 2.0, 1.0

    pin = Pin(name="1", number="1", position=(0.0, 0.0), net="HV",
              shape="rect", layer="F.Cu", width=pad_w, height=pad_h)
    comp = Component(ref="U1", footprint="SOIC-8", bounds=(5.0, 4.0),
                     pins=[pin], net_class="HighVoltage", initial_position=pos)
    net = Net(name="HV", pins=[("U1", "1")], net_class="HighVoltage")
    netlist = Netlist(components=[comp], nets=[net])

    state = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=netlist,
    )

    pad_sizes = {("U1", "1"): _make_pad_size(pad_w, pad_h, "rect")}

    zone = HVExclusionZone(
        name="u1_zone", center=pos, size=(10.0, 10.0),
        clearance_mm=6.0, component_refdes="U1",
    )

    result = _run_grid_stage(
        state, hv_exclusion_zones=[zone], pad_sizes=pad_sizes,
    )
    grid = result.grid

    # Expansion: rect is grown to (pad_w + 2*eff, pad_h + 2*eff) = (14, 13).
    # Centered at (25, 25), the expanded rect spans (18, 18.5) to (32, 31.5).
    # Cell col=63 (x=31.75), row=63 (y=31.75) is just inside the corner.
    # Cell col=64 (x=32.25) is just outside the corner.
    inside_x = 63 * cell + cell / 2
    outside_x = 64 * cell + cell / 2
    inside_y = 63 * cell + cell / 2
    outside_y = 64 * cell + cell / 2

    assert grid.is_available(inside_x, inside_y, layer=0) is False
    assert grid.is_available(outside_x, outside_y, layer=0) is True


def test_expansion_inner_layer_uses_reduced_factor():
    """On In1.Cu, the blocked radius is pad_r + 1.8, not pad_r + 6.0."""
    cell = 0.5
    pad_r = 1.0
    pos = (25.0, 25.0)
    eff_inner = 6.0 * 0.30  # 1.8

    pin = Pin(name="1", number="1", position=(0.0, 0.0), net="HV",
              shape="circle", layer="In1.Cu", width=2.0, height=2.0)
    comp = Component(ref="Q1", footprint="TO-247", bounds=(10.0, 10.0),
                     pins=[pin], net_class="HighVoltage", initial_position=pos)
    net = Net(name="HV", pins=[("Q1", "1")], net_class="HighVoltage")
    netlist = Netlist(components=[comp], nets=[net])

    state = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=netlist,
    )

    pad_sizes = {("Q1", "1"): _make_pad_size(2.0, 2.0, "circle")}

    zone = HVExclusionZone(
        name="q1_zone", center=pos, size=(10.0, 10.0),
        clearance_mm=6.0, component_refdes="Q1",
    )

    # Need 4 layers so layer 1 = In1.Cu
    result = _run_grid_stage(
        state, hv_exclusion_zones=[zone], layer_count=4,
        pad_sizes=pad_sizes,
    )
    grid = result.grid

    # F.Cu (layer 0) has no expansion since the pin is on In1.Cu only.
    sample_y = 50 * cell + cell / 2
    assert grid.is_available(50 * cell + cell / 2, sample_y, layer=0) is True

    # In1.Cu (layer 1) has the inner-layer expansion.
    # Threshold 1.0 + 1.8 = 2.8.
    # cell at col=55, row=50: center (27.75, 25.25), dist = 2.761 < 2.8 -> blocked
    # cell at col=56, row=50: center (28.25, 25.25), dist = 3.260 > 2.8 -> unblocked
    in_x = 55 * cell + cell / 2
    out_x = 56 * cell + cell / 2
    assert grid.is_available(in_x, sample_y, layer=1) is False
    assert grid.is_available(out_x, sample_y, layer=1) is True


def test_expansion_skips_non_hv_pads():
    """Non-HV pads are not expanded; their blocking matches the pre-pass
    snapshot (no creepage inflation)."""
    pos_hv = (15.0, 25.0)
    pos_lv = (35.0, 25.0)

    hv_pin = Pin(name="1", number="1", position=(0.0, 0.0), net="HV",
                 shape="circle", layer="F.Cu", width=2.0, height=2.0)
    lv_pin = Pin(name="1", number="1", position=(0.0, 0.0), net="LV",
                 shape="circle", layer="F.Cu", width=2.0, height=2.0)
    comp_hv = Component(ref="Q1", footprint="TO-247", bounds=(5.0, 5.0),
                        pins=[hv_pin], net_class="HighVoltage", initial_position=pos_hv)
    comp_lv = Component(ref="R1", footprint="0805", bounds=(2.0, 1.0),
                        pins=[lv_pin], net_class="Signal", initial_position=pos_lv)
    net_hv = Net(name="HV", pins=[("Q1", "1")], net_class="HighVoltage")
    net_lv = Net(name="LV", pins=[("R1", "1")], net_class="Signal")
    netlist = Netlist(components=[comp_hv, comp_lv], nets=[net_hv, net_lv])

    pad_sizes = {
        ("Q1", "1"): _make_pad_size(2.0, 2.0, "circle"),
        ("R1", "1"): _make_pad_size(1.0, 1.0, "circle"),
    }

    # Snapshot grid with no HV zones (only standard per-net blocking)
    state_no_hv = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=netlist,
    )
    pre = _run_grid_stage(
        state_no_hv, hv_exclusion_zones=[], pad_sizes=pad_sizes,
    ).grid

    state_with_hv = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=netlist,
    )
    zone = HVExclusionZone(
        name="q1_zone", center=pos_hv, size=(10.0, 10.0),
        clearance_mm=6.0, component_refdes="Q1",
    )
    post = _run_grid_stage(
        state_with_hv, hv_exclusion_zones=[zone], pad_sizes=pad_sizes,
    ).grid

    # Far from both pads: cell at (2.75, 2.75) is unblocked in both.
    cell = 0.5
    far_x = 5 * cell + cell / 2
    far_y = 5 * cell + cell / 2
    assert pre.is_available(far_x, far_y, layer=0) is True
    assert post.is_available(far_x, far_y, layer=0) is True

    # Near the LV pad: blocking is the same (no expansion applies).
    # LV pad at (35, 25), pad_r=0.5. Cell at (35.5, 25) is just outside.
    lv_test_x = 35.5
    assert pre.is_available(lv_test_x, pos_lv[1], layer=0) == \
        post.is_available(lv_test_x, pos_lv[1], layer=0)

    # Near the HV pad: cell at HV + 4mm.
    # HV at (15, 25), pad_r=1.0, eff=6.0: threshold 7.0.
    # cell at (19, 25) -> col=37, row=50, center (18.75, 25.25)
    #   dist = sqrt(3.75^2 + 0.25^2) = 3.758
    #   < 7.0 -> blocked (by expansion)
    #   > 1.5 (pad_r + 0.2 clearance) -> unblocked pre-expansion
    hv_in_x = 19.0
    assert pre.is_available(hv_in_x, pos_hv[1], layer=0) is True
    assert post.is_available(hv_in_x, pos_hv[1], layer=0) is False


def test_expansion_runs_once_per_stage():
    """Running the stage twice in a row on the same input does not double
    the expansion log (the log is rebuilt each run, not appended)."""
    pos = (25.0, 25.0)
    pin = Pin(name="1", number="1", position=(0.0, 0.0), net="HV",
              shape="circle", layer="F.Cu", width=2.0, height=2.0)
    comp = Component(ref="Q1", footprint="TO-247", bounds=(10.0, 10.0),
                     pins=[pin], net_class="HighVoltage", initial_position=pos)
    net = Net(name="HV", pins=[("Q1", "1")], net_class="HighVoltage")
    netlist = Netlist(components=[comp], nets=[net])
    state = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=netlist,
    )
    pad_sizes = {("Q1", "1"): _make_pad_size(2.0, 2.0, "circle")}
    zone = HVExclusionZone(
        name="q1_zone", center=pos, size=(10.0, 10.0),
        clearance_mm=6.0, component_refdes="Q1",
    )

    _run_grid_stage(state, hv_exclusion_zones=[zone], pad_sizes=pad_sizes)
    first_log = list(_EXPANSION_LOG)
    _run_grid_stage(state, hv_exclusion_zones=[zone], pad_sizes=pad_sizes)
    second_log = list(_EXPANSION_LOG)

    # Log is per-pad, not per-run: second run produces same length, not
    # 2x. (Both are the same state, but the log is cleared and rebuilt.)
    assert len(first_log) == len(second_log)
    # Pad is on F.Cu (layer 0) only, so 1 entry.
    assert len(first_log) == 1
    assert first_log[0][0] == "Q1"
    assert first_log[0][1] == "1"
    assert first_log[0][2] == 0

