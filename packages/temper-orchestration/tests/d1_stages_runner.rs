// D1 runner test: sequence the three D1 deterministic setup stages
// (ConfigAttachStage + NetOrderingStage + DrcOracleSetupStage) through
// PipelineRunner<BoardState> (Rust Orchestration Engine plan 2026-08-09-001,
// Phase D batch D1).
//
// The stages delegate their leaf compute to Python classes/glue that the
// embedded test interpreter cannot see (no venv), so the Python modules the
// stages import are registered as FAKES in sys.modules below -- the same
// builtins-only approach stages_runner.rs uses for its duck-typed fakes.
// What this suite proves is the SEQUENCING and the BoardState read/write
// contract: each stage reads the Py<PyAny> fields it needs, the runner
// threads the state through in declaration order, and the write-back lands
// on the correct fields.
//
// Tests:
//   1. three_stages_sequence_end_to_end  — all three through one runner,
//      final state has config + net_order + drc_oracle populated
//   2. net_ordering_defaults_empty_loops  — missing loops become an empty
//      LoopCollection (the order_nets call still happens)
//   3. no_netlist_skips_net_ordering      — the guard returns the state
//      unchanged (net_order untouched)
//   4. net_class_setup_mutates_in_place   — the in-place netlist mapping
//      path (NetClassSetupStage) returns the same state object

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule, PyTuple};

use temper_orchestration::{
    BoardState, ConfigAttachStage, DrcOracleSetupStage, NetClassSetupStage, NetOrderingStage,
    PipelineConfig, PipelineRunner,
};

use temper_design_bundle::Netlist;

const FAKE_MODULES: &str = r#"
# Fake Python modules the D1 stages import at runtime (registered into
# sys.modules by the test so `py.import(...)` resolves without the venv).
class FakeClearanceMatrix:
    def __init__(self):
        self.added = []
    def add_net_class_rules(self, rules):
        self.added.append(("ncr", rules))
    def set_net_class(self, net, cls):
        self.added.append(("set", net, cls))
    def add_differential_pair(self, a, b, spacing):
        self.added.append(("dp", a, b, spacing))
    @classmethod
    def parse(cls, board):
        m = cls()
        m.added.append(("parse", board))
        return m
class FakeDesignRulesParser:
    @staticmethod
    def create_default():
        return FakeClearanceMatrix()
class FakePoint:
    def __init__(self, x, y):
        self.x = x; self.y = y
class FakePad:
    def __init__(self, **kw):
        self.kw = kw
class FakeGeometry:
    def __init__(self):
        self.pads = []
        self.rebuilt = 0
    def rebuild_index(self):
        self.rebuilt += 1
class FakeDRCOracle:
    def __init__(self, rules=None):
        self.rules = rules
        self.geometry = FakeGeometry()
    def register_pad(self, pad):
        self.geometry.pads.append(pad)
def pin_world_position(pin, component):
    return (0.0, 0.0)
class FakeLoopCollection:
    def __init__(self):
        self.loops = []
def order_nets(netlist, loops, net_priority_config=None):
    return ["NET_B", "NET_A"]
class FakeNet:
    def __init__(self, name):
        self.name = name; self.net_class = "Signal"; self.pins = []
class FakeComponent:
    def __init__(self, ref):
        self.ref = ref; self.initial_position = (10.0, 10.0)
        self.initial_rotation = 0; self.initial_side = 0; self.pins = []
class FakeNetlist:
    def __init__(self):
        self.components = [FakeComponent("U1")]
        self.nets = [FakeNet("NET_A"), FakeNet("NET_B")]
        self.mapping_applied = None
    def apply_net_class_mapping(self, mapping):
        self.mapping_applied = mapping
        return 1
"#;

fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    // Build the fake `temper_placer.router_v6.constraints_*` modules from a
    // single shared namespace object so cross-module references resolve.
    let ns = PyModule::new(py, "d1_fakes")?;
    let code = std::ffi::CString::new(FAKE_MODULES).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

    // Register the package chain in sys.modules so the stages' dotted
    // `py.import(...)` calls resolve to the fakes.
    let pkg = PyModule::new(py, "temper_placer")?;
    let router = PyModule::new(py, "router_v6")?;
    let core = PyModule::new(py, "core")?;

    let cdr = PyModule::new(py, "constraints_design_rules")?;
    cdr.add("ClearanceMatrix", ns.getattr("FakeClearanceMatrix")?)?;
    cdr.add("DesignRulesParser", ns.getattr("FakeDesignRulesParser")?)?;
    router.add("constraints_design_rules", &cdr)?;

    let drc = PyModule::new(py, "constraints_drc_oracle")?;
    drc.add("DRCOracle", ns.getattr("FakeDRCOracle")?)?;
    router.add("constraints_drc_oracle", &drc)?;

    let geom = PyModule::new(py, "constraints_geometry")?;
    geom.add("Point", ns.getattr("FakePoint")?)?;
    router.add("constraints_geometry", &geom)?;

    let spatial = PyModule::new(py, "constraints_spatial_index")?;
    spatial.add("Pad", ns.getattr("FakePad")?)?;
    router.add("constraints_spatial_index", &spatial)?;

    let ordering = PyModule::new(py, "net_ordering")?;
    ordering.add("order_nets", ns.getattr("order_nets")?)?;
    router.add("net_ordering", &ordering)?;

    let loops = PyModule::new(py, "loop")?;
    loops.add("LoopCollection", ns.getattr("FakeLoopCollection")?)?;
    core.add("loop", &loops)?;

    let pin_geom = PyModule::new(py, "pin_geometry")?;
    pin_geom.add("pin_world_position", ns.getattr("pin_world_position")?)?;
    core.add("pin_geometry", &pin_geom)?;

    pkg.add("router_v6", &router)?;
    pkg.add("core", &core)?;

    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.router_v6", &router)?;
    modules.set_item("temper_placer.router_v6.constraints_design_rules", &cdr)?;
    modules.set_item("temper_placer.router_v6.constraints_drc_oracle", &drc)?;
    modules.set_item("temper_placer.router_v6.constraints_geometry", &geom)?;
    modules.set_item("temper_placer.router_v6.constraints_spatial_index", &spatial)?;
    modules.set_item("temper_placer.router_v6.net_ordering", &ordering)?;
    modules.set_item("temper_placer.core", &core)?;
    modules.set_item("temper_placer.core.loop", &loops)?;
    modules.set_item("temper_placer.core.pin_geometry", &pin_geom)?;
    Ok(ns.into_any())
}

fn fake_netlist(py: Python<'_>, ns: &Bound<'_, PyAny>) -> Py<Netlist> {
    // The fake Component/Net objects stay duck-typed (the stages read
    // `netlist.components` / `netlist.nets` and reach into them); only the
    // CONTAINER is the real design-bundle `Netlist` pyclass, because the
    // BoardState field is now `Option<Py<Netlist>>`.
    let comp = ns
        .getattr("FakeComponent")
        .expect("fake component")
        .call1(("U1",))
        .expect("construct fake component");
    let comps = PyList::new(py, [comp]).expect("component list");
    let net_a = ns
        .getattr("FakeNet")
        .expect("fake net")
        .call1(("NET_A",))
        .expect("construct fake net");
    let net_b = ns
        .getattr("FakeNet")
        .expect("fake net")
        .call1(("NET_B",))
        .expect("construct fake net");
    let nets = PyList::new(py, [net_a, net_b]).expect("net list");
    let netlist = py.get_type::<Netlist>().call0().expect("construct netlist");
    netlist
        .setattr("components", &comps)
        .expect("set components");
    netlist.setattr("nets", &nets).expect("set nets");
    netlist.extract::<Py<Netlist>>().expect("typed netlist")
}

fn string_tuple(py: Python<'_>, items: &[&str]) -> Py<PyAny> {
    PyTuple::new(py, items).expect("tuple").into_any().unbind()
}

#[test]
fn three_stages_sequence_end_to_end() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let netlist = fake_netlist(py, &ns);
        let config = PyDict::new(py);
        config.set_item("zones", PyList::empty(py)).unwrap();

        let mut state = BoardState::new();
        state.netlist = Some(netlist);

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ConfigAttachStage {
            config: Some(config.into_any().unbind()),
        }));
        runner.add_stage(Box::new(NetOrderingStage {
            net_priority: Some(PyDict::new(py).into_any().unbind()),
        }));
        runner.add_stage(Box::new(DrcOracleSetupStage {
            design_rules: None,
            parsed_pads: None,
        }));
        let (out, report) = runner.run(state);

        assert!(!report.halted_early, "halted: {:?}", report.stage_reports);
        let names: Vec<String> = report
            .stage_reports
            .iter()
            .map(|r| r.name.to_string())
            .collect();
        assert_eq!(
            names,
            vec!["config_attach", "net_ordering", "drc_oracle_setup"]
        );
        for r in &report.stage_reports {
            assert!(
                matches!(r.outcome, temper_orchestration::StageOutcome::Completed),
                "stage {:?} did not complete: {:?}",
                r.name,
                r.outcome
            );
        }

        // config attached
        let config = out.config.as_ref().expect("config attached");
        assert_eq!(
            config.bind(py).get_item("zones").unwrap().len().unwrap(),
            0
        );
        // net_order written from the fake order_nets
        assert_eq!(out.net_order, vec!["NET_B", "NET_A"]);
        // drc_oracle written with the fake DRCOracle
        let oracle = out.drc_oracle.as_ref().expect("drc_oracle attached");
        let geometry = oracle.bind(py).getattr("geometry").unwrap();
        let pads: Vec<Bound<'_, PyAny>> = geometry.getattr("pads").unwrap().try_iter().unwrap().collect::<Result<_, _>>().unwrap();
        assert!(pads.is_empty());
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn net_ordering_defaults_empty_loops() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let netlist = fake_netlist(py, &ns);

        let mut state = BoardState::new();
        state.netlist = Some(netlist);
        // state.loops left None -> stage must build an empty LoopCollection.

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(NetOrderingStage {
            net_priority: None,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        assert_eq!(out.net_order, vec!["NET_B", "NET_A"]);
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn no_netlist_skips_net_ordering() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let mut state = BoardState::new();
        state.net_order = vec!["PRESERVED".into()];

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(NetOrderingStage {
            net_priority: None,
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        // The stage returned the state unchanged.
        assert_eq!(out.net_order, vec!["PRESERVED"]);
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn net_class_setup_mutates_in_place_and_returns_state() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py).unwrap();
        let netlist = fake_netlist(py, &ns);

        let mut state = BoardState::new();
        state.netlist = Some(netlist.clone_ref(py));
        let mapping = PyDict::new(py);
        mapping.set_item("NET_A", "Power").unwrap();

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(NetClassSetupStage {
            net_classes: Some(mapping.into_any().unbind()),
        }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        // Netlist mutated in place; the state object is returned unchanged
        // (same Py reference). The real Netlist's `apply_net_class_mapping`
        // rewrites NET_A's net_class (the fake `mapping_applied` bookkeeping
        // is gone with the fake container).
        let nets = out
            .netlist
            .as_ref()
            .unwrap()
            .bind(py)
            .getattr("nets")
            .unwrap();
        let first = nets.get_item(0).unwrap();
        assert_eq!(first.getattr("name").unwrap().extract::<String>().unwrap(), "NET_A");
        assert_eq!(
            first.getattr("net_class").unwrap().extract::<String>().unwrap(),
            "Power"
        );
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn config_attach_identity_preserved_when_nothing_to_do() {
    Python::initialize();
    Python::attach(|py| {
        install_fakes(py).unwrap();
        let mut state = BoardState::new();
        state.config = Some(string_tuple(py, &["already", "set"]));

        let mut runner = PipelineRunner::new(PipelineConfig::default());
        runner.add_stage(Box::new(ConfigAttachStage { config: None }));
        let (out, report) = runner.run(state);
        assert!(!report.halted_early);
        // config untouched (None stage config -> no write-back)
        assert_eq!(
            out.config.as_ref().unwrap().bind(py).len().unwrap(),
            2,
            "config must be preserved"
        );
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
