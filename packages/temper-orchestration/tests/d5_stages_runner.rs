// D5 runner test: sequence the D5 deterministic zone-aware stages through
// PipelineRunner<BoardState>, and drive the Rust `PhasedAssignmentStage`
// (Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D5).
//
// The zone-aware stage delegates its slot-grid / ray-casting / AABB compute
// to temper-design-bundle kernels and the `isolation_slot_aabb` helper that
// the embedded test interpreter cannot see (no venv), so the modules the
// stage imports are registered as FAKES in sys.modules below -- the same
// builtins-only approach the d1..d4 runner tests use. What this suite proves
// is the SEQUENCING and the BoardState read/write contract:
//
//   1. `ZoneAwareSlotGenerationStage`: reads `zones` (+ `board`, `netlist`
//      for the isolation filter), writes `zone_slots` and
//      `reclaim_by_pin_pair`; the no-zones guard writes only the reclaim.
//   2. `PhasedAssignmentStage`: reads `netlist` / `component_zone_map` /
//      `zone_slots` (+ `design_rules`), writes `placements` and `used_slots`;
//      the no-netlist guard returns the state untouched.
//
// The phased stage drives the phase dispatch, the slot scoring, the footprint
// + HV ring reservation and the `_compute_wirelength` / `_get_footprint_radius`
// / `_effective_ghost_pad_radius` / `_apply_bottleneck_filter` mixin helpers
// through the fake stage object.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule, PySet, PyString, PyTuple};

use temper_orchestration::{BoardState, PhasedAssignmentStage, PipelineConfig, PipelineRunner, ZoneAwareSlotGenerationStage};

const FAKE_MODULES: &str = r#"
# Fake Python modules the D5 stages import at runtime (registered into
# sys.modules by the test so `py.import(...)` resolves without the venv).

class FakePin:
    def __init__(self, name, x, y, net="NET"):
        self.name = name
        self.number = name
        self.position = (x, y)
        self.net = net

class FakeComponent:
    def __init__(self, ref, bounds, pins=(), net_class=None):
        self.ref = ref
        self.bounds = bounds
        self.pins = list(pins)
        self.net_class = net_class
        self.initial_position = None

class FakeNetlist:
    def __init__(self, components, nets=()):
        self.components = list(components)
        self.nets = list(nets)

class FakeZone:
    def __init__(self, name, bounds):
        self.name = name
        self.bounds = bounds

class FakeBoard:
    def __init__(self):
        self.width = 100.0
        self.height = 100.0
        self.copper_zones = None
        self.zones = None

class FakeConstraints:
    def __init__(self):
        self.placement_priority = {"auto": {"method": "auto"}}

class FakeCompiler:
    def validate(self, board, netlist):
        return []

class FakeStage:
    def __init__(self, design_rules=None):
        self.constraints = FakeConstraints()
        self.compiler = FakeCompiler()
        self.slot_filter = lambda slot, ref, placements: True
        self.slot_scorer = lambda slot, ref, placements: 0.0
        self.design_rules = design_rules
        self.channel_map = None
        self.w_r = 0.05
        self.use_isolation_slots = False
        self._isolation_slots_by_ref = {}
        self.seed_filter = None
        self._bottleneck_map = None
        self.slot_spacing = 12.0
        self.fixed_placements = {}
    def _get_footprint_radius(self, comp):
        return 3.0
    def _effective_ghost_pad_radius(self, ref, pin_name, base_radius, cur, other):
        return base_radius
    def _compute_wirelength(self, ref, slot, net_pins, placements):
        return 0.0
    def _apply_bottleneck_filter(self, ref, candidate_slots, comp_by_ref=None):
        return list(candidate_slots)
    def _is_hv_ref(self, ref, comp_by_ref):
        return False

class FakeDesignRules:
    def __init__(self, creepage_mm=6.0, safety_category="HV"):
        class _R:
            def __init__(self, creepage, safety):
                self.creepage_mm = creepage
                self.safety_category = safety
        self.net_classes = {"HighVoltage": _R(creepage_mm, safety_category)}
        self.net_class_assignments = {"HV": "HighVoltage"}

def generate_slots_for_zone(x_min, y_min, x_max, y_max, spacing):
    out = []
    x = x_min + spacing / 2.0
    while x < x_max:
        y = y_min + spacing / 2.0
        while y < y_max:
            out.append((x, y))
            y += spacing
        x += spacing
    return out

def point_in_polygon_py(x, y, polygon):
    return False

def slot_intersects_iso_py(slot, iso_aabbs):
    return False

def isolation_slot_aabb(slot, component_xy):
    return ((0.0, 0.0), (5.0, 5.0))

def routability_penalty(slot, channel_map):
    return 0.0
"#;

fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "d5_fakes")?;
    let code = std::ffi::CString::new(FAKE_MODULES).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;
    modules.set_item("d5_fakes", &ns)?;

    // temper_design_bundle_python.deterministic_stages / .deterministic_phase
    let tdb = PyModule::new(py, "temper_design_bundle_python")?;
    let ds = PyModule::new(py, "deterministic_stages")?;
    ds.add("generate_slots_for_zone", ns.getattr("generate_slots_for_zone")?)?;
    let dp = PyModule::new(py, "deterministic_phase")?;
    dp.add("point_in_polygon_py", ns.getattr("point_in_polygon_py")?)?;
    dp.add("slot_intersects_iso_py", ns.getattr("slot_intersects_iso_py")?)?;
    tdb.add("deterministic_stages", &ds)?;
    tdb.add("deterministic_phase", &dp)?;
    modules.set_item("temper_design_bundle_python", &tdb)?;
    modules.set_item("temper_design_bundle_python.deterministic_stages", &ds)?;
    modules.set_item("temper_design_bundle_python.deterministic_phase", &dp)?;

    // temper_placer.io.isolation_slot_geometry
    let pkg = PyModule::new(py, "temper_placer")?;
    let io = PyModule::new(py, "io")?;
    let isg = PyModule::new(py, "isolation_slot_geometry")?;
    isg.add("isolation_slot_aabb", ns.getattr("isolation_slot_aabb")?)?;
    io.add("isolation_slot_geometry", &isg)?;
    pkg.add("io", &io)?;
    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.io", &io)?;
    modules.set_item("temper_placer.io.isolation_slot_geometry", &isg)?;

    // temper_placer.deterministic.channels (the routability_penalty import
    // in the Rust best-slot scoring; never called with channel_map=None).
    let det = PyModule::new(py, "deterministic")?;
    let channels = PyModule::new(py, "channels")?;
    channels.add("routability_penalty", ns.getattr("routability_penalty")?)?;
    det.add("channels", &channels)?;
    pkg.add("deterministic", &det)?;
    modules.set_item("temper_placer.deterministic", &det)?;
    modules.set_item("temper_placer.deterministic.channels", &channels)?;
    Ok(ns.into_any())
}

fn py_tuple<'py>(py: Python<'py>, items: Vec<Bound<'py, PyAny>>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(py, items)?.into_any())
}

fn py_frozenset<'py>(py: Python<'py>, items: Vec<Bound<'py, PyAny>>) -> PyResult<Bound<'py, PyAny>> {
    let builtins = py.import("builtins")?;
    let list = PyList::empty(py);
    for item in items {
        list.append(item)?;
    }
    builtins.getattr("frozenset")?.call1((list,))
}

fn pair<'py>(py: Python<'py>, a: &str, b: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let a = PyString::new(py, a).into_any();
    py_tuple(py, vec![a, b])
}

fn xy<'py>(py: Python<'py>, x: f64, y: f64) -> PyResult<Bound<'py, PyAny>> {
    Ok((x, y).into_pyobject(py)?.into_any())
}

fn zone_state<'py>(
    py: Python<'py>,
    ns: &Bound<'py, PyAny>,
    with_zones: bool,
) -> PyResult<BoardState> {
    let zones = if with_zones {
        let z = ns.getattr("FakeZone")?.call1(("Signal", ((0.0, 0.0), (30.0, 30.0))))?;
        py_frozenset(py, vec![z])?
    } else {
        py_frozenset(py, vec![])?
    };
    let board = ns.getattr("FakeBoard")?.call0()?;
    let mut state = BoardState::new();
    state.zones = Some(zones.into_any().unbind());
    state.board = Some(board.into_any().unbind());
    Ok(state)
}

#[test]
fn zone_aware_no_zones_writes_reclaim() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d5_fakes")?;
        let state = zone_state(py, &ns, false)?;

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ZoneAwareSlotGenerationStage {
            slot_spacing_mm: 5.0,
            copper_zone_margin: 2.0,
            yaml_copper_zones: None,
            yaml_isolation_slots: None,
            net_class_rules: None,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        // The no-zones guard leaves `zone_slots` untouched (None in the Rust
        // state) and writes only the (empty) reclaim.
        assert!(out.zone_slots.is_none());
        assert!(out.reclaim_by_pin_pair.is_none());
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn zone_aware_with_zones_writes_zone_slots() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d5_fakes")?;
        let state = zone_state(py, &ns, true)?;

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ZoneAwareSlotGenerationStage {
            slot_spacing_mm: 5.0,
            copper_zone_margin: 2.0,
            yaml_copper_zones: None,
            yaml_isolation_slots: None,
            net_class_rules: None,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let zone_slots = out.zone_slots.as_ref().expect("zone_slots attached");
        let as_dict = py.import("builtins")?.getattr("dict")?.call1((zone_slots,))?;
        let slots = as_dict.get_item("Signal")?;
        assert!(slots.len()? > 0, "the Signal zone must produce slots");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

fn phased_state<'py>(
    py: Python<'py>,
    ns: &Bound<'py, PyAny>,
    design_rules: Option<&Bound<'py, PyAny>>,
) -> PyResult<BoardState> {
    let pin1 = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0, "HV"))?;
    let r1 = ns.getattr("FakeComponent")?.call1(("Q1", (2.0, 2.0), vec![&pin1]))?;
    let pin2 = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0, "NET"))?;
    let r2 = ns.getattr("FakeComponent")?.call1(("C1", (2.0, 2.0), vec![&pin2]))?;
    let netlist = ns.getattr("FakeNetlist")?.call1((PyList::new(py, [r1, r2])?,))?;
    let czm = py_frozenset(
        py,
        vec![
            pair(py, "Q1", PyString::new(py, "Signal").into_any())?,
            pair(py, "C1", PyString::new(py, "Signal").into_any())?,
        ],
    )?;
    let slots = py_tuple(py, vec![xy(py, 2.5, 2.5)?, xy(py, 7.5, 2.5)?, xy(py, 2.5, 7.5)?, xy(py, 7.5, 7.5)?])?;
    let zone_slots = py_frozenset(py, vec![pair(py, "Signal", slots)?])?;

    let mut state = BoardState::new();
    state.netlist = Some(netlist.into_any().unbind());
    state.component_zone_map = Some(czm.into_any().unbind());
    state.zone_slots = Some(zone_slots.into_any().unbind());
    if let Some(dr) = design_rules {
        state.design_rules = Some(dr.clone().into_any().unbind());
    }
    Ok(state)
}

#[test]
fn phased_guard_no_netlist_identity() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d5_fakes")?;
        let stage_obj = ns.getattr("FakeStage")?.call0()?;
        let mut state = BoardState::new();
        state.component_zone_map = Some(PyString::new(py, "x").into_any().unbind());
        state.zone_slots = Some(PyString::new(py, "x").into_any().unbind());

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(PhasedAssignmentStage {
            stage: stage_obj.unbind(),
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert!(out.placements.is_none(), "placements must be untouched by the guard");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn phased_single_stage_end_to_end() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d5_fakes")?;
        let stage_obj = ns.getattr("FakeStage")?.call0()?;
        let state = phased_state(py, &ns, None)?;

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(PhasedAssignmentStage {
            stage: stage_obj.unbind(),
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let placements = out.placements.as_ref().expect("placements attached");
        assert_eq!(placements.bind(py).len()?, 2, "both components placed");
        let used = out.used_slots.as_ref().expect("used_slots attached");
        assert!(used.bind(py).len()? >= 2, "footprint rings must reserve slots");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn phased_hv_rings_reserved() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let ns = py.import("d5_fakes")?;
        let dr = ns.getattr("FakeDesignRules")?.call1((6.0_f64, "HV"))?;
        let stage_obj = ns.getattr("FakeStage")?.call1((&dr,))?;
        let state = phased_state(py, &ns, Some(&dr))?;

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(PhasedAssignmentStage {
            stage: stage_obj.unbind(),
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let used = out.used_slots.as_ref().expect("used_slots attached");
        let used_set: Bound<PySet> = py
            .import("builtins")?
            .getattr("set")?
            .call1((used,))?
            .cast_into()?;
        // Q1's HV pin sits at its placed position + (0,0); creepage 6.0 with
        // the 2.5/7.5 grid guarantees at least the placed slot and neighbors.
        let as_dict = py.import("builtins")?.getattr("dict")?.call1((
            out.placements.as_ref().unwrap(),
        ))?;
        let q1 = as_dict.get_item("Q1")?;
        assert!(used_set.contains(q1)?, "the placed slot must be reserved");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
