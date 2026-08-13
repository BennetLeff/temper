// D4 runner test: sequence the D4 deterministic assignment stage
// (ComponentAssignmentStage) through PipelineRunner<BoardState>, and drive
// the D4 validator kernel (phased_validator_hv) directly on a Rust
// BoardState (Rust Orchestration Engine plan 2026-08-09-001, Phase D batch
// D4).
//
// The stage delegates its greedy compute to the temper-design-bundle kernel
// (`assign_components_to_slots`) that the embedded test interpreter cannot
// see (no venv), so the modules the stage imports are registered as FAKES in
// sys.modules below -- the same builtins-only approach d1/d2/d3_stages_runner.rs
// use. What this suite proves is the SEQUENCING and the BoardState read/write
// contract: the stage reads netlist/component_zone_map/zone_slots (+ the
// optional domain map and fixed placements), resolves fixed placements,
// delegates the greedy assignment to the (fake) kernel, wraps the result in
// `frozenset(placements.items())` and writes `placements` back onto the
// state. The validator-kernel test drives `phased_validator_hv` against
// fake netlist/design-rules objects + fake slot-grid kernels and asserts the
// `(field, value, reason)` triple list comes back.
//
// Tests:
//   1. component_assignment_no_netlist_guard     -- the guard returns the
//      state unchanged (placements untouched)
//   2. component_assignment_single_stage_end_to_end -- netlist + zone map +
//      slot grid through the runner: placements attached
//   3. component_assignment_fixed_placements     -- fixed placements are
//      resolved ref-first and lead the kernel input
//   4. component_assignment_domain_filter        -- a per-ref domain map
//      confines the kernel input's domain_ok
//   5. phased_validator_hv_kernel                -- the coverage / over-claim
//      kernel returns (field, value, reason) triples

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule, PyString, PyTuple};

use temper_orchestration::{
    BoardState, ComponentAssignmentStage, PipelineConfig, PipelineRunner, SlotId,
};

const FAKE_MODULES: &str = r#"
# Fake Python modules the D4 stage / validator kernel import at runtime
# (registered into sys.modules by the test so `py.import(...)` resolves
# without the venv).

class FakePin:
    def __init__(self, name, x, y, net="NET"):
        self.name = name
        self.number = name
        self.position = (x, y)
        self.net = net

class FakeComponent:
    def __init__(self, ref, bounds, pins=(), sheetpath=None):
        self.ref = ref
        self.bounds = bounds
        self.pins = list(pins)
        self.sheetpath = sheetpath

class FakeNetlist:
    def __init__(self, components, nets=()):
        self.components = list(components)
        self.nets = list(nets)

class FakeNetClassRules:
    def __init__(self, creepage_mm, safety_category):
        self.creepage_mm = creepage_mm
        self.safety_category = safety_category

class FakeDesignRules:
    def __init__(self, net_classes, net_class_assignments):
        self.net_classes = net_classes
        self.net_class_assignments = net_class_assignments

class FakePhasedComponentAssignmentStage:
    def __new__(cls):
        return object.__new__(cls)
    def _get_footprint_radius(self, comp):
        return 2.0
    def _effective_ghost_pad_radius(self, ref, pin_name, base_radius, cur, other):
        return base_radius

class FakePoint:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class FakeRegion:
    def __init__(self, x0, y0, x1, y1):
        self._b = (x0, y0, x1, y1)
    @property
    def is_empty(self):
        return False
    def covers(self, p):
        return self._b[0] <= p.x <= self._b[2] and self._b[1] <= p.y <= self._b[3]

def assign_components_to_slots(netlist, component_zone_map, zone_slots, fixed, domain_ok, slot_spacing):
    """Fake greedy kernel: fixed placements first, then the first allowed
    slot of each component's zone (the real kernel's shape, not its
    compute; the domain filter mirrors `available_slots.retain(allowed)`)."""
    out = {}
    for ref, pos in fixed.items():
        out[ref] = pos
    zones = dict(zone_slots)
    for comp in netlist.components:
        if comp.ref in out:
            continue
        zone = component_zone_map.get(comp.ref, "Signal")
        slots = zones.get(zone, ())
        allowed = domain_ok.get(comp.ref) if domain_ok else None
        for s in slots:
            if allowed is not None and s not in allowed:
                continue
            if s not in out.values():
                out[comp.ref] = s
                break
    return out

def infer_slot_spacing_py(slots):
    return 5.0

def build_slot_index_py(slots, spacing):
    idx = {}
    for s in slots:
        i = int(round(s[0] / spacing))
        j = int(round(s[1] / spacing))
        idx.setdefault((i, j), []).append(s)
    return idx

def slots_within_radius_py(center, radius, index, spacing):
    out = []
    cx, cy = center
    for cell_slots in index.values():
        for s in cell_slots:
            if ((s[0] - cx) ** 2 + (s[1] - cy) ** 2) ** 0.5 <= radius:
                out.append(s)
    return out
"#;

fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "d4_fakes")?;
    let code = std::ffi::CString::new(FAKE_MODULES).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

    // temper_design_bundle_python.deterministic_leaves
    let tdb = PyModule::new(py, "temper_design_bundle_python")?;
    let dl = PyModule::new(py, "deterministic_leaves")?;
    dl.add("assign_components_to_slots", ns.getattr("assign_components_to_slots")?)?;
    dl.add("infer_slot_spacing_py", ns.getattr("infer_slot_spacing_py")?)?;
    dl.add("build_slot_index_py", ns.getattr("build_slot_index_py")?)?;
    dl.add("slots_within_radius_py", ns.getattr("slots_within_radius_py")?)?;
    tdb.add("deterministic_leaves", &dl)?;
    modules.set_item("temper_design_bundle_python", &tdb)?;
    modules.set_item("temper_design_bundle_python.deterministic_leaves", &dl)?;

    // shapely.geometry (the domain-filter predicate)
    let shapely_pkg = PyModule::new(py, "shapely")?;
    let geometry = PyModule::new(py, "geometry")?;
    geometry.add("Point", ns.getattr("FakePoint")?)?;
    geometry.add("Region", ns.getattr("FakeRegion")?)?;
    shapely_pkg.add("geometry", &geometry)?;
    modules.set_item("shapely", &shapely_pkg)?;
    modules.set_item("shapely.geometry", &geometry)?;

    // temper_placer.deterministic.stages.phased_component_assignment
    let pkg = PyModule::new(py, "temper_placer")?;
    let det = PyModule::new(py, "deterministic")?;
    let stages = PyModule::new(py, "stages")?;
    let pca = PyModule::new(py, "phased_component_assignment")?;
    pca.add("PhasedComponentAssignmentStage", ns.getattr("FakePhasedComponentAssignmentStage")?)?;
    stages.add("phased_component_assignment", &pca)?;
    det.add("stages", &stages)?;
    pkg.add("deterministic", &det)?;
    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.deterministic", &det)?;
    modules.set_item("temper_placer.deterministic.stages", &stages)?;
    modules.set_item("temper_placer.deterministic.stages.phased_component_assignment", &pca)?;
    Ok(ns.into_any())
}

/// A Python tuple of `Bound<PyAny>` items (homogeneous).
fn py_tuple<'py>(py: Python<'py>, items: Vec<Bound<'py, PyAny>>) -> PyResult<Bound<'py, PyAny>> {
    Ok(PyTuple::new(py, items)?.into_any())
}

fn py_list<'py>(py: Python<'py>, items: Vec<Bound<'py, PyAny>>) -> PyResult<Bound<'py, PyAny>> {
    let list = PyList::empty(py);
    for item in items {
        list.append(item)?;
    }
    Ok(list.into_any())
}

fn py_frozenset<'py>(py: Python<'py>, items: Vec<Bound<'py, PyAny>>) -> PyResult<Bound<'py, PyAny>> {
    let builtins = py.import("builtins")?;
    let list = py_list(py, items)?;
    builtins.getattr("frozenset")?.call1((list,))
}

fn pair<'py>(py: Python<'py>, a: &str, b: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let a = PyString::new(py, a).into_any();
    py_tuple(py, vec![a, b])
}

/// A Python `(x, y)` slot tuple.
fn xy<'py>(py: Python<'py>, x: f64, y: f64) -> PyResult<Bound<'py, PyAny>> {
    Ok((x, y).into_pyobject(py)?.into_any())
}

/// A Python string as a `Bound<PyAny>`.
fn str_any<'py>(py: Python<'py>, s: &str) -> Bound<'py, PyAny> {
    PyString::new(py, s).into_any()
}

fn assignment_state<'py>(
    py: Python<'py>,
    ns: &Bound<'py, PyAny>,
    components: Vec<Bound<'py, PyAny>>,
) -> PyResult<BoardState> {
    let netlist = ns
        .getattr("FakeNetlist")?
        .call1((py_list(py, components.clone())?,))?;
    let czm = py_frozenset(
        py,
        components
            .iter()
            .map(|c| pair(py, &c.getattr("ref")?.extract::<String>()?, str_any(py, "Signal")))
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let slots = py_tuple(py, vec![xy(py, 0.0, 0.0)?, xy(py, 5.0, 5.0)?])?;
    let zone_slots = py_frozenset(py, vec![pair(py, "Signal", slots.clone())?])?;

    let mut state = BoardState::new();
    state.netlist = Some(netlist.into_any().unbind());
    state.component_zone_map = Some(czm.into_any().unbind());
    state.zone_slots = Some(zone_slots.into_any().unbind());
    Ok(state)
}

fn stage() -> ComponentAssignmentStage {
    ComponentAssignmentStage {
        slot_spacing: 12.0,
        fixed_placements: None,
    }
}

#[test]
fn component_assignment_no_netlist_guard() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let state = BoardState::new();

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(stage()));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert!(out.placements.is_none(), "placements must be untouched by the guard");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn component_assignment_single_stage_end_to_end() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let r1 = ns.getattr("FakeComponent")?.call1(("R1", (4.0, 2.0)))?;
        let r2 = ns.getattr("FakeComponent")?.call1(("R2", (4.0, 2.0)))?;
        let state = assignment_state(py, &ns, vec![r1, r2])?;

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(stage()));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert_eq!(report.stage_reports.len(), 1);
        let placements = out.placements.as_ref().expect("placements attached");
        assert_eq!(placements.bind(py).len()?, 2, "both components placed");
        let as_dict = py.import("builtins")?.getattr("dict")?.call1((placements,))?;
        assert_eq!(as_dict.get_item("R1")?.extract::<(f64, f64)>()?, (0.0, 0.0));
        assert_eq!(as_dict.get_item("R2")?.extract::<(f64, f64)>()?, (5.0, 5.0));
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn component_assignment_fixed_placements() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let r1 = ns.getattr("FakeComponent")?.call1(("R1", (4.0, 2.0)))?;
        let r2 = ns.getattr("FakeComponent")?.call1(("R2", (4.0, 2.0)))?;
        let state = assignment_state(py, &ns, vec![r1, r2])?;

        let fixed = PyDict::new(py);
        fixed.set_item("R1", (3.0_f64, 3.0_f64))?;

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ComponentAssignmentStage {
            slot_spacing: 12.0,
            fixed_placements: Some(fixed.into_any().unbind()),
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let placements = out.placements.as_ref().expect("placements attached");
        let as_dict = py.import("builtins")?.getattr("dict")?.call1((placements,))?;
        // The fixed placement wins the exact position; R2 gets the first
        // free grid slot (the fake kernel's fallback).
        assert_eq!(as_dict.get_item("R1")?.extract::<(f64, f64)>()?, (3.0, 3.0));
        assert_eq!(as_dict.get_item("R2")?.extract::<(f64, f64)>()?, (0.0, 0.0));
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn component_assignment_domain_filter() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let r1 = ns.getattr("FakeComponent")?.call1(("R1", (4.0, 2.0)))?;
        let mut state = assignment_state(py, &ns, vec![r1])?;

        // Confine R1 to x >= 3 via a right-hand corridor region.
        let geometry = py.import("shapely.geometry")?;
        let region = geometry.getattr("Region")?.call1((3.0, 0.0, 100.0, 100.0))?;
        let dom = py_frozenset(py, vec![pair(py, "R1", str_any(py, "LV_interior"))?])?;
        let regions = PyTuple::new(py, [region])?;
        state.component_domain_map = Some(dom.into_any().unbind());
        state.domain_regions = Some(regions.into_any().unbind());

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(stage()));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let placements = out.placements.as_ref().expect("placements attached");
        let as_dict = py.import("builtins")?.getattr("dict")?.call1((placements,))?;
        // The domain filter drops slot (0,0); the only covered slot (5,5)
        // wins.
        assert_eq!(as_dict.get_item("R1")?.extract::<(f64, f64)>()?, (5.0, 5.0));
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn phased_validator_hv_kernel() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        // Q1 (HV, placed at (0,0) with pin Q1.1 at absolute (0,0)) and an LV
        // chip at (20,20). Creepage 6.0; used_slots recorded by the placer.
        let pin = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0, "HV"))?;
        let comp = ns.getattr("FakeComponent")?.call1(("Q1", (10.0, 10.0), vec![&pin]))?;
        let pin2 = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0, "VCC"))?;
        let comp2 = ns.getattr("FakeComponent")?.call1(("C1", (2.0, 2.0), vec![&pin2]))?;
        let netlist = ns.getattr("FakeNetlist")?.call1((py_list(py, vec![comp, comp2])?,))?;
        let rules = ns.getattr("FakeDesignRules")?.call1((PyDict::new(py), PyDict::new(py)))?;
        let hv_cls = ns.getattr("FakeNetClassRules")?.call1((6.0_f64, "HV"))?;
        rules.getattr("net_classes")?.call_method1("__setitem__", ("HighVoltage", &hv_cls))?;
        rules
            .getattr("net_class_assignments")?
            .call_method1("__setitem__", ("HV", "HighVoltage"))?;

        let slots = py_tuple(
            py,
            vec![
                xy(py, 0.0, 0.0)?,
                xy(py, 0.0, 5.0)?,
                xy(py, 5.0, 0.0)?,
                xy(py, 5.0, 5.0)?,
            ],
        )?;
        let zone_slots = py_frozenset(py, vec![pair(py, "Signal", slots)?])?;
        let placements = py_frozenset(
            py,
            vec![
                pair(py, "Q1", xy(py, 0.0, 0.0)?)?,
                pair(py, "C1", xy(py, 20.0, 20.0)?)?,
            ],
        )?;
        // used_slots recorded by the placer WITHOUT the (0,5) HV-ring slot.
        // U1 (O-C3): the field is owned now — construct the `HashSet<SlotId>`
        // directly (the same shape the marshaller produces from the
        // frozenset, exercised end-to-end by the Python D4 differential).
        let mut used_owned = std::collections::HashSet::new();
        used_owned.insert(SlotId(0.0, 0.0));
        used_owned.insert(SlotId(5.0, 0.0));

        let mut state = BoardState::new();
        state.netlist = Some(netlist.into_any().unbind());
        state.design_rules = Some(rules.into_any().unbind());
        state.zone_slots = Some(zone_slots.into_any().unbind());
        state.placements = Some(placements.into_any().unbind());
        state.used_slots = Some(used_owned);

        let failures = temper_orchestration::phased_validator_hv(py, state);
        let failures = failures.unwrap();
        let n: usize = failures.bind(py).len()?;
        assert!(n >= 1, "the missing (0,5) ring slot must be reported");
        let first = failures.bind(py).get_item(0)?;
        let field: String = first.get_item(0)?.extract()?;
        assert!(field.starts_with("hv_creepage_unblocked.Q1."), "field: {field}");
        let reason: String = first.get_item(2)?.extract()?;
        assert!(reason.contains("(0.0, 5.0)"), "reason: {reason}");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
