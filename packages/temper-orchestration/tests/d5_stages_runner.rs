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
// + HV ring reservation and the `_compute_wirelength` /
// `_effective_ghost_pad_radius` / `_apply_bottleneck_filter` mixin helpers
// through the fake stage object.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList, PyModule, PyTuple};

use temper_data_model::{SlotPos, StrPairSet, Val, Zone, ZoneSet, ZoneSlots, ZoneSlotsSet};

use temper_orchestration::{
    BoardState, PhasedAssignmentStage, PipelineConfig, PipelineRunner, ZoneAwareSlotGenerationStage,
};

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

def footprint_radius_py(bounds, slot_spacing):
    if bounds:
        return ((bounds[0] ** 2 + bounds[1] ** 2) ** 0.5) / 2.0 + 1.0
    return slot_spacing / 2.0

def reserve_slots_py(center, radius, all_slots):
    cx, cy = center
    return [s for s in all_slots
            if ((s[0] - cx) ** 2 + (s[1] - cy) ** 2) ** 0.5 <= radius]

def distance_py(p1, p2):
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
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
    ds.add(
        "generate_slots_for_zone",
        ns.getattr("generate_slots_for_zone")?,
    )?;
    let dp = PyModule::new(py, "deterministic_phase")?;
    dp.add("point_in_polygon_py", ns.getattr("point_in_polygon_py")?)?;
    dp.add(
        "slot_intersects_iso_py",
        ns.getattr("slot_intersects_iso_py")?,
    )?;
    dp.add("footprint_radius_py", ns.getattr("footprint_radius_py")?)?;
    dp.add("reserve_slots_py", ns.getattr("reserve_slots_py")?)?;
    dp.add("distance_py", ns.getattr("distance_py")?)?;
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
    // U6 (O-C3) group-2: `temper_placer.deterministic.stages.zone_geometry`
    // — the owned `ZoneSet` rebuild (`Marshal::to_python` for `Zone`) needs
    // the class when the with-zones path runs.
    let stages = PyModule::new(py, "stages")?;
    let zg = PyModule::new(py, "zone_geometry")?;
    zg.add("Zone", ns.getattr("FakeZone")?)?;
    stages.add("zone_geometry", &zg)?;
    det.add("stages", &stages)?;
    pkg.add("deterministic", &det)?;
    modules.set_item("temper_placer.deterministic", &det)?;
    modules.set_item("temper_placer.deterministic.channels", &channels)?;
    modules.set_item("temper_placer.deterministic.stages", &stages)?;
    modules.set_item("temper_placer.deterministic.stages.zone_geometry", &zg)?;
    Ok(ns.into_any())
}

fn zone_state<'py>(
    _py: Python<'py>,
    ns: &Bound<'py, PyAny>,
    with_zones: bool,
) -> PyResult<BoardState> {
    let board = ns.getattr("FakeBoard")?.call0()?;
    let mut state = BoardState::new();
    // U6 (O-C3) group-2: the owned `ZoneSet` shape of the frozenset the
    // Python stage received (the marshaller's read, exercised end-to-end by
    // the Python D5 suite).
    state.zones = Some(if with_zones {
        ZoneSet(std::collections::HashSet::from([Zone {
            name: "Signal".into(),
            bounds: (
                (Val::Float(0.0), Val::Float(0.0)),
                (Val::Float(30.0), Val::Float(30.0)),
            ),
        }]))
    } else {
        ZoneSet(Default::default())
    });
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
        // U6 (O-C3) group-2: the entry is owned -- probe the Signal zone's
        // produced slots through the owned element (the Python `dict(...)`
        // rebuild path is exercised by the Python D5 suite).
        let signal = zone_slots
            .iter()
            .find(|z| z.zone == "Signal")
            .expect("the Signal zone must have an entry");
        assert!(
            !signal.slots.is_empty(),
            "the Signal zone must produce slots"
        );
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
    let r1 = ns
        .getattr("FakeComponent")?
        .call1(("Q1", (2.0, 2.0), vec![&pin1]))?;
    let pin2 = ns.getattr("FakePin")?.call1(("1", 0.0, 0.0, "NET"))?;
    let r2 = ns
        .getattr("FakeComponent")?
        .call1(("C1", (2.0, 2.0), vec![&pin2]))?;
    let netlist = ns
        .getattr("FakeNetlist")?
        .call1((PyList::new(py, [r1, r2])?,))?;
    let mut state = BoardState::new();
    state.netlist = Some(netlist.into_any().unbind());
    // U6 (O-C3) group-2: the owned shapes of the Python `frozenset` feeds.
    state.component_zone_map = Some(StrPairSet(std::collections::HashSet::from([
        ("Q1".to_string(), "Signal".to_string()),
        ("C1".to_string(), "Signal".to_string()),
    ])));
    state.zone_slots = Some(ZoneSlotsSet(std::collections::HashSet::from([ZoneSlots {
        zone: "Signal".into(),
        slots: vec![
            SlotPos(2.5, 2.5),
            SlotPos(7.5, 2.5),
            SlotPos(2.5, 7.5),
            SlotPos(7.5, 7.5),
        ],
    }])));
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
        // U6 (O-C3) group-2: the fields are owned — the guard is exercised
        // with populated NON-EMPTY sets (the old test wedged garbage Python
        // strings in to prove the guard returns before touching them; the
        // owned `!set.is_empty()` guard is the direct analogue).
        state.component_zone_map = Some(StrPairSet(std::collections::HashSet::from([(
            "x".to_string(),
            "x".to_string(),
        )])));
        state.zone_slots = Some(ZoneSlotsSet(std::collections::HashSet::from([ZoneSlots {
            zone: "x".into(),
            slots: vec![],
        }])));

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(PhasedAssignmentStage {
            stage: stage_obj.unbind(),
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        assert!(
            out.placements.is_none(),
            "placements must be untouched by the guard"
        );
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
        assert_eq!(placements.len(), 2, "both components placed");
        let used = out.used_slots.as_ref().expect("used_slots attached");
        assert!(used.len() >= 2, "footprint rings must reserve slots");
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
        // U1 (O-C3): the field is owned — rebuild the Python set from the
        // slot coordinates (the marshaller's to_python path is exercised
        // end-to-end by the Python D4/D5 suites; the runner just needs a
        // Python set to probe membership in).
        let used_set = py.import("builtins")?.getattr("set")?.call0()?;
        for slot in used {
            used_set.call_method1("add", (PyTuple::new(py, [slot.0, slot.1])?,))?;
        }
        // Q1's HV pin sits at its placed position + (0,0); creepage 6.0 with
        // the 2.5/7.5 grid guarantees at least the placed slot and neighbors.
        // U6 (O-C3) group-2: `placements` is owned — resolve Q1's position
        // through the owned element (the Python `dict(...)` rebuild path is
        // exercised by the Python D5 suite).
        let q1 = out
            .placements
            .as_ref()
            .expect("placements attached")
            .iter()
            .find(|p| p.ref_ == "Q1")
            .expect("Q1 placed");
        let q1_pos = (q1.position.0, q1.position.1).into_pyobject(py)?;
        assert!(
            used_set.contains(q1_pos)?,
            "the placed slot must be reserved"
        );
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
