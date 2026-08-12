// D3 runner test: sequence the D3 deterministic clearance-grid stage
// (ClearanceGridStage) through PipelineRunner<BoardState> (Rust
// Orchestration Engine plan 2026-08-09-001, Phase D batch D3).
//
// The stage delegates its leaf compute to Python modules that the embedded
// test interpreter cannot see (no venv), so the modules the stage imports are
// registered as FAKES in sys.modules below -- the same builtins-only approach
// d1/d2_stages_runner.rs use. What this suite proves is the SEQUENCING and the
// BoardState read/write contract: the stage reads board/netlist/placements,
// constructs the (fake) ClearanceGrid, drives the pad-blocking loop, the HV
// creepage-expansion pass (appending to the fake `_grid_fence._EXPANSION_LOG`
// and invoking the fake fence), and writes `grid` back onto the state.
//
// Tests:
//   1. clearance_grid_no_board_guard      -- the guard returns the state
//      unchanged (grid untouched)
//   2. clearance_grid_single_stage_end_to_end -- board + netlist through the
//      runner: grid attached, nets registered in pin order
//   3. clearance_grid_hv_expansion_fence  -- an HV exclusion zone populates
//      the expansion log and the fence runs over it
//   4. clearance_grid_exclusion_zone_writes -- excluded nets are blocked
//      with net_id -2 inside the zone bbox
//   5. clearance_grid_zone_pipeline_chain -- zone_geometry -> clearance_grid
//      in one runner, grid written back after the zones

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};

use temper_orchestration::{BoardState, PipelineConfig, PipelineRunner, ZoneGeometryStage};

const FAKE_MODULES: &str = r#"
# Fake Python modules the D3 stage imports at runtime (registered into
# sys.modules by the test so `py.import(...)` resolves without the venv).
# The FakeGrid replicates the ClearanceGrid orchestration surface with
# tuple-indexable 2D arrays (numpy's `arr[row, col]` semantics) so the
# stage's exclusion-zone writes work against the same access pattern.
class FakeBoard:
    def __init__(self, width, height):
        self.width = width
        self.height = height

class FakeNDArray:
    def __init__(self, rows, cols):
        self.data = [[0] * cols for _ in range(rows)]
    def __getitem__(self, key):
        if isinstance(key, tuple):
            r, c = key
            return self.data[r][c]
        return self.data[key]
    def __setitem__(self, key, value):
        if isinstance(key, tuple):
            r, c = key
            self.data[r][c] = value
        else:
            self.data[key] = value

class FakeGrid:
    def __init__(self, width_mm, height_mm, cell_size_mm, layer_count=2):
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.cell_size_mm = cell_size_mm
        self.layer_count = layer_count
        self.cols = int(width_mm / cell_size_mm)
        self.rows = int(height_mm / cell_size_mm)
        self._trace_net_ids = [FakeNDArray(self.rows, self.cols) for _ in range(layer_count)]
        self._pad_net_ids = [FakeNDArray(self.rows, self.cols) for _ in range(layer_count)]
        self._net_to_id = {}
        self._id_to_net = {}
        self._next_net_id = 1
    def get_net_id(self, net_name):
        if not net_name:
            return 0
        if net_name not in self._net_to_id:
            self._net_to_id[net_name] = self._next_net_id
            self._id_to_net[self._next_net_id] = net_name
            self._next_net_id += 1
        return self._net_to_id[net_name]
    def block_circle(self, center, radius_mm, clearance_mm, layer=0, net_name=None, is_pad=True):
        if layer < 0 or layer >= self.layer_count:
            return
        total = radius_mm + clearance_mm
        cx, cy = center
        net_id = self.get_net_id(net_name) if net_name else -2
        target = self._pad_net_ids[layer] if is_pad else self._trace_net_ids[layer]
        min_col = max(0, int((cx - total) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + total) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - total) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + total) / self.cell_size_mm) + 1)
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                dx = (col * self.cell_size_mm + self.cell_size_mm / 2) - cx
                dy = (row * self.cell_size_mm + self.cell_size_mm / 2) - cy
                if (dx * dx + dy * dy) ** 0.5 <= total:
                    curr = target[row, col]
                    if curr == 0:
                        target[row, col] = net_id
                    elif curr != net_id:
                        target[row, col] = -1
    def block_rect(self, center, size, clearance_mm, layer=0, net_name=None, is_obstacle=True):
        if layer < 0 or layer >= self.layer_count:
            return
        cx, cy = center
        hw, hh = size[0] / 2.0 + clearance_mm, size[1] / 2.0 + clearance_mm
        min_col = max(0, int((cx - hw) / self.cell_size_mm))
        max_col = min(self.cols, int((cx + hw) / self.cell_size_mm) + 1)
        min_row = max(0, int((cy - hh) / self.cell_size_mm))
        max_row = min(self.rows, int((cy + hh) / self.cell_size_mm) + 1)
        net_id = -2 if is_obstacle else (self.get_net_id(net_name) if net_name else -2)
        target = self._trace_net_ids[layer]
        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                curr = target[row, col]
                if curr == 0:
                    target[row, col] = net_id
                elif curr != net_id:
                    target[row, col] = -1
    def blocked_count_on_layer(self, layer):
        if layer < 0 or layer >= self.layer_count:
            return 0
        n = 0
        for row in range(self.rows):
            for col in range(self.cols):
                if self._trace_net_ids[layer][row, col] != 0:
                    n += 1
                if self._pad_net_ids[layer][row, col] != 0:
                    n += 1
        return n
    def is_available(self, x_mm, y_mm, layer=0, net_name=None, net_id=None):
        if layer < 0 or layer >= self.layer_count:
            return False
        col = int(x_mm / self.cell_size_mm)
        row = int(y_mm / self.cell_size_mm)
        if 0 <= row < self.rows and 0 <= col < self.cols:
            if net_id is None and net_name:
                net_id = self.get_net_id(net_name)
            t = self._trace_net_ids[layer][row, col]
            if t != 0 and t != net_id:
                return False
            p = self._pad_net_ids[layer][row, col]
            return not (p != 0 and p != net_id)
        return False

class FakePin:
    def __init__(self, name, x, y, net="NET", shape="circle", layer="F.Cu", is_pth=False):
        self.name = name
        self.number = name
        self.position = (x, y)
        self.net = net
        self.shape = shape
        self.layer = layer
        self.is_pth = is_pth
        self.rotation = 0.0

class FakeComponent:
    def __init__(self, ref, x, y, pins, net_class="Signal"):
        self.ref = ref
        self.pins = pins
        self.initial_position = (x, y)
        self.net_class = net_class

class FakeNet:
    def __init__(self, name, net_class="Signal"):
        self.name = name
        self.net_class = net_class

class FakeNetlist:
    def __init__(self, components, nets):
        self.components = components
        self.nets = nets

class FakeZone:
    def __init__(self, name, bounds):
        self.name = name
        self.bounds = bounds

class FakeHVZone:
    def __init__(self, name, center, size, component_refdes=None, excluded_nets=()):
        self.name = name
        self.center = center
        self.size = size
        self.component_refdes = component_refdes
        self.excluded_nets = list(excluded_nets)

def pin_world_position(pin, comp):
    return (pin.position[0] + comp.initial_position[0],
            pin.position[1] + comp.initial_position[1])

_EXPANSION_LOG = []

def hv_pad_set(pads, hv_exclusion_zones, component_positions):
    hv_refs = set()
    for zone in hv_exclusion_zones:
        ref = getattr(zone, "component_refdes", None)
        if ref is not None:
            hv_refs.add(ref)
            continue
        zx, zy = zone.center
        zw, zh = zone.size
        hw, hh = zw / 2.0, zh / 2.0
        best = None
        best_d2 = None
        for r, pos in component_positions.items():
            if (zx - hw) <= pos[0] <= (zx + hw) and (zy - hh) <= pos[1] <= (zy + hh):
                d2 = (pos[0] - zx) ** 2 + (pos[1] - zy) ** 2
                if best is None or d2 < best_d2:
                    best, best_d2 = r, d2
        if best is not None:
            hv_refs.add(best)
    return {(p["ref"], p["name"]) for p in pads if p["ref"] in hv_refs}

def effective_creepage(layer, base):
    if layer in ("In1.Cu", "In2.Cu"):
        return base * 0.30
    return base

def _layer_index_to_name(layer_idx, _layer_count):
    names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    if layer_idx < len(names):
        return names[layer_idx]
    return "Layer_%d" % layer_idx

class ConfigError(ValueError):
    pass

class FenceViolation(RuntimeError):
    pass

def define_zone_layout(board_width, board_height):
    return [
        ("HV", 0, 0, board_width * 0.3, board_height),
        ("Power", board_width * 0.3, 0, board_width * 0.6, board_height),
        ("Signal", board_width * 0.6, 0, board_width * 0.9, board_height),
        ("MCU", board_width * 0.9, 0, board_width, board_height),
    ]

def scale_zone_bounds(name, r0, r1, r2, r3, board_width, board_height):
    return (r0 * board_width, r1 * board_height, r2 * board_width, r3 * board_height)

def check_clearance_grid_conservatism(grid, expansion_log=None, sample_count_circle=16):
    log = expansion_log if expansion_log is not None else _EXPANSION_LOG
    violations = []
    for entry in log:
        (ref, pin_name, layer_idx, pos, shape, pad_radius, pad_size, eff_creep, _cells) = entry
        if layer_idx < 0 or layer_idx >= grid.layer_count:
            continue
        cell = grid.cell_size_mm
        inset = cell / 2.0
        if shape in ("rect", "roundrect", "oval") and pad_size[0] > 0 and pad_size[1] > 0:
            cx, cy = pos
            w, h = pad_size
            eff = eff_creep - inset
            samples = [(cx - w / 2 - eff, cy - h / 2 - eff), (cx + w / 2 + eff, cy - h / 2 - eff),
                       (cx - w / 2 - eff, cy + h / 2 + eff), (cx + w / 2 + eff, cy + h / 2 + eff),
                       (cx, cy - h / 2 - eff), (cx, cy + h / 2 + eff),
                       (cx - w / 2 - eff, cy), (cx + w / 2 + eff, cy)]
        else:
            samples = [(pos[0], pos[1])]
        for x, y in samples:
            if grid.is_available(x, y, layer=layer_idx):
                violations.append({"ref": ref, "pin_name": pin_name, "layer": layer_idx,
                                   "xy": (x, y), "reason": "fake"})
    return violations

def check_clearance_grid_perf_budget(fence_elapsed_ms, stage_elapsed_ms, budget_pct=20.0, floor_ms=50.0):
    return (False, None)
"#;

fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "d3_fakes")?;
    let code = std::ffi::CString::new(FAKE_MODULES).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

    // temper_placer.deterministic.stages._grid_core
    let pkg = PyModule::new(py, "temper_placer")?;
    let det = PyModule::new(py, "deterministic")?;
    let stages = PyModule::new(py, "stages")?;
    let grid_core = PyModule::new(py, "_grid_core")?;
    grid_core.add("ClearanceGrid", ns.getattr("FakeGrid")?)?;
    let grid_hv = PyModule::new(py, "_grid_hv")?;
    grid_hv.add("hv_pad_set", ns.getattr("hv_pad_set")?)?;
    grid_hv.add("effective_creepage", ns.getattr("effective_creepage")?)?;
    grid_hv.add("_layer_index_to_name", ns.getattr("_layer_index_to_name")?)?;
    grid_hv.add("ConfigError", ns.getattr("ConfigError")?)?;
    let grid_fence = PyModule::new(py, "_grid_fence")?;
    grid_fence.add("_EXPANSION_LOG", ns.getattr("_EXPANSION_LOG")?)?;
    grid_fence.add("check_clearance_grid_conservatism", ns.getattr("check_clearance_grid_conservatism")?)?;
    grid_fence.add("check_clearance_grid_perf_budget", ns.getattr("check_clearance_grid_perf_budget")?)?;
    grid_fence.add("FenceViolation", ns.getattr("FenceViolation")?)?;
    stages.add("_grid_core", &grid_core)?;
    stages.add("_grid_hv", &grid_hv)?;
    stages.add("_grid_fence", &grid_fence)?;
    det.add("stages", &stages)?;
    pkg.add("deterministic", &det)?;

    // temper_placer.core.pin_geometry
    let core = PyModule::new(py, "core")?;
    let pin_geometry = PyModule::new(py, "pin_geometry")?;
    pin_geometry.add("pin_world_position", ns.getattr("pin_world_position")?)?;
    core.add("pin_geometry", &pin_geometry)?;
    pkg.add("core", &core)?;

    // temper_placer.deterministic.stages.zone_geometry (for the chain test)
    let zg = PyModule::new(py, "zone_geometry")?;
    zg.add("Zone", ns.getattr("FakeZone")?)?;
    stages.add("zone_geometry", &zg)?;

    // temper_design_bundle_python.deterministic_stages (for ZoneGeometryStage)
    let tdb = PyModule::new(py, "temper_design_bundle_python")?;
    let ds = PyModule::new(py, "deterministic_stages")?;
    ds.add("define_zone_layout", ns.getattr("define_zone_layout")?)?;
    ds.add("scale_zone_bounds", ns.getattr("scale_zone_bounds")?)?;
    tdb.add("deterministic_stages", &ds)?;

    modules.set_item("temper_design_bundle_python", &tdb)?;
    modules.set_item("temper_design_bundle_python.deterministic_stages", &ds)?;

    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.deterministic", &det)?;
    modules.set_item("temper_placer.deterministic.stages", &stages)?;
    modules.set_item("temper_placer.deterministic.stages._grid_core", &grid_core)?;
    modules.set_item("temper_placer.deterministic.stages._grid_hv", &grid_hv)?;
    modules.set_item("temper_placer.deterministic.stages._grid_fence", &grid_fence)?;
    modules.set_item("temper_placer.core", &core)?;
    modules.set_item("temper_placer.core.pin_geometry", &pin_geometry)?;
    modules.set_item("temper_placer.deterministic.stages.zone_geometry", &zg)?;
    Ok(ns.into_any())
}

fn py_list<'py>(py: Python<'py>, items: Vec<&Bound<'py, PyAny>>) -> PyResult<Bound<'py, PyAny>> {
    use pyo3::types::PyList;
    let list = PyList::empty(py);
    for item in items {
        list.append(item)?;
    }
    Ok(list.into_any())
}

#[test]
fn clearance_grid_no_board_guard() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let state = BoardState::new();

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(temper_orchestration::ClearanceGridStage {
            cell_size_mm: 0.5,
            layer_count: 2,
            pad_sizes: None,
            max_clearance_mm: 0.2,
            net_class_clearances: None,
            net_classes: None,
            pth_mask_expansion_mm: 0.0,
            smd_mask_expansion_mm: 0.0,
            inner_layer_clearance_mm: 0.2,
            hv_exclusion_zones: None,
            default_trace_width_mm: 0.0,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert!(out.grid.is_none(), "grid must be untouched by the guard");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn clearance_grid_single_stage_end_to_end() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let board = ns.getattr("FakeBoard")?.call1((50.0, 50.0))?;
        let pin = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0))?;
        let comp = ns
            .getattr("FakeComponent")?
            .call1(("Q1", 25.0, 25.0, py_list(py, vec![&pin])?))?;
        let net = ns.getattr("FakeNet")?.call1(("NET_A",))?;
        let netlist = ns
            .getattr("FakeNetlist")?
            .call1((py_list(py, vec![&comp])?, py_list(py, vec![&net])?))?;

        let mut state = BoardState::new();
        state.board = Some(board.into_any().unbind());
        state.netlist = Some(netlist.into_any().unbind());

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(temper_orchestration::ClearanceGridStage {
            cell_size_mm: 0.5,
            layer_count: 2,
            pad_sizes: None,
            max_clearance_mm: 0.2,
            net_class_clearances: None,
            net_classes: None,
            pth_mask_expansion_mm: 0.0,
            smd_mask_expansion_mm: 0.0,
            inner_layer_clearance_mm: 0.2,
            hv_exclusion_zones: None,
            default_trace_width_mm: 0.0,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert_eq!(report.stage_reports.len(), 1);
        assert!(
            matches!(
                report.stage_reports[0].outcome,
                temper_orchestration::StageOutcome::Completed
            ),
            "stage did not complete: {:?}",
            report.stage_reports[0].outcome
        );
        let grid = out.grid.as_ref().expect("grid attached");
        let net_ids = grid.bind(py).getattr("_net_to_id")?;
        assert_eq!(net_ids.len()?, 1, "one net registered");
        let blocked = grid.bind(py).call_method1("blocked_count_on_layer", (0,))?;
        let blocked: i64 = blocked.extract()?;
        assert!(blocked > 0, "pad must block some cells");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn clearance_grid_hv_expansion_fence() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let board = ns.getattr("FakeBoard")?.call1((50.0, 50.0))?;
        let pin = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0))?;
        let comp = ns
            .getattr("FakeComponent")?
            .call1(("Q1", 25.0, 25.0, py_list(py, vec![&pin])?))?;
        let net = ns.getattr("FakeNet")?.call1(("HV", "HighVoltage"))?;
        let netlist = ns
            .getattr("FakeNetlist")?
            .call1((py_list(py, vec![&comp])?, py_list(py, vec![&net])?))?;
        let zone = ns
            .getattr("FakeHVZone")?
            .call1(("q1_zone", (25.0, 25.0), (10.0, 10.0), "Q1"))?;
        let zones = py_list(py, vec![&zone])?;

        let mut state = BoardState::new();
        state.board = Some(board.into_any().unbind());
        state.netlist = Some(netlist.into_any().unbind());

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(temper_orchestration::ClearanceGridStage {
            cell_size_mm: 0.5,
            layer_count: 2,
            pad_sizes: None,
            max_clearance_mm: 0.2,
            net_class_clearances: None,
            net_classes: None,
            pth_mask_expansion_mm: 0.0,
            smd_mask_expansion_mm: 0.0,
            inner_layer_clearance_mm: 0.2,
            hv_exclusion_zones: Some(zones.unbind()),
            default_trace_width_mm: 0.0,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let grid = out.grid.as_ref().expect("grid attached");
        let log = ns.getattr("_EXPANSION_LOG")?;
        let log_len = log.len()?;
        assert_eq!(log_len, 1, "HV expansion appends one log entry");
        let entry = log.get_item(0)?;
        let first: String = entry.get_item(0)?.extract()?;
        assert_eq!(first, "Q1");
        let _ = grid;
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn clearance_grid_exclusion_zone_writes() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let board = ns.getattr("FakeBoard")?.call1((50.0, 50.0))?;
        let pin = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0))?;
        let comp = ns
            .getattr("FakeComponent")?
            .call1(("Q1", 25.0, 25.0, py_list(py, vec![&pin])?))?;
        let net = ns.getattr("FakeNet")?.call1(("NET_A",))?;
        let netlist = ns
            .getattr("FakeNetlist")?
            .call1((py_list(py, vec![&comp])?, py_list(py, vec![&net])?))?;
        // A zone with an excluded net -- the stage blocks the zone bbox with
        // net_id -2, which the tuple-indexed fake grid records.
        let zone = ns.getattr("FakeHVZone")?.call(
            ("hv_z", (10.0, 10.0), (8.0, 6.0), Option::<String>::None),
            None,
        )?;
        zone.getattr("excluded_nets")?.call_method1("append", ("GATE_H",))?;
        let zones = py_list(py, vec![&zone])?;

        let mut state = BoardState::new();
        state.board = Some(board.into_any().unbind());
        state.netlist = Some(netlist.into_any().unbind());

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(temper_orchestration::ClearanceGridStage {
            cell_size_mm: 0.5,
            layer_count: 2,
            pad_sizes: None,
            max_clearance_mm: 0.2,
            net_class_clearances: None,
            net_classes: None,
            pth_mask_expansion_mm: 0.0,
            smd_mask_expansion_mm: 0.0,
            inner_layer_clearance_mm: 0.2,
            hv_exclusion_zones: Some(zones.unbind()),
            default_trace_width_mm: 0.0,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let grid = out.grid.as_ref().expect("grid attached");
        let net_ids = grid.bind(py).getattr("_net_to_id")?;
        assert_eq!(net_ids.len()?, 2, "NET_A + GATE_H registered");
        let center_cell = grid.bind(py).call_method1("is_available", (10.0, 10.0, 0))?;
        let center_cell: bool = center_cell.extract()?;
        assert!(!center_cell, "zone center must be blocked");
        let far = grid.bind(py).call_method1("is_available", (40.0, 40.0, 0))?;
        let far: bool = far.extract()?;
        assert!(far, "far cell must stay free");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn clearance_grid_zone_pipeline_chain() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let board = ns.getattr("FakeBoard")?.call1((100.0, 50.0))?;

        let mut state = BoardState::new();
        state.board = Some(board.into_any().unbind());

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ZoneGeometryStage { zone_config: None }));
        runner.add_stage(Box::new(temper_orchestration::ClearanceGridStage {
            cell_size_mm: 0.5,
            layer_count: 2,
            pad_sizes: None,
            max_clearance_mm: 0.2,
            net_class_clearances: None,
            net_classes: None,
            pth_mask_expansion_mm: 0.0,
            smd_mask_expansion_mm: 0.0,
            inner_layer_clearance_mm: 0.2,
            hv_exclusion_zones: None,
            default_trace_width_mm: 0.0,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let names: Vec<String> = report
            .stage_reports
            .iter()
            .map(|r| r.name.to_string())
            .collect();
        assert_eq!(names, vec!["zone_geometry", "clearance_grid"]);
        let zones = out.zones.as_ref().expect("zones attached from zone_geometry");
        assert_eq!(zones.bind(py).len().unwrap(), 4);
        let grid = out.grid.as_ref().expect("grid attached from clearance_grid");
        assert_eq!(grid.bind(py).getattr("cols")?.extract::<i64>()?, 200);
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
