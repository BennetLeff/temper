// U-G runner test: sequence the Router V6 stages through the Rust
// `PipelineRunner<BoardState>` via the `RouterPipeline` pyclass `run()`
// driver (Rust Orchestration Engine plan 2026-08-09-001,
// orchestration-port unit U-G).
//
// What this suite proves is the U-G DRIVER wiring:
//
//   1. `canonical_stage_order_through_pyclass` — the fixed Stage 0..5 order
//      driven through the pyclass run(): the Python leaf call-backs fire in
//      exactly the oracle's order (parse -> legalize -> ledger.checkin ->
//      dense/escape -> ledger.checkout(escape_vias) -> stage2 ->
//      resource_bound -> stage3 -> stage4 -> ledger.checkout(routing_complete)),
//      the result is assembled with the threaded objects, and
//      `runtime_seconds >= 0`.
//   2. `skip_stage3_bypasses_sat_through_pyclass` — the R7 stage3_override
//      is consumed by the driver: `_run_stage3` never fires and the result
//      carries the override object (identity).
//   3. `stage_exception_propagation_through_pyclass` — a raising stage
//      halts the run and the ORIGINAL exception is re-raised (type +
//      message), with the stages before it having run.
//   4. `result_assembly_fields_through_pyclass` — the RouterV6Result
//      carries pcb / escape_vias / stage2 / stage3 / stage4 /
//      batch_results=list(last_batch_results) / manufacturing_report=None.
//
// The embedded test interpreter cannot see the venv, so the Python modules
// the driver imports (`temper_placer.router_v6._pipeline_core`,
// `temper_placer.io.kicad_parser`,
// `temper_placer.router_v6.placement_legalization`,
// `temper_placer.router_v6.dense_package_detection`,
// `temper_placer.router_v6.escape_via_generator`,
// `temper_placer.router_v6._pipeline_types`) are registered as FAKES in
// sys.modules below -- the same builtins-only approach the d1..d7 and
// ue_pipeline_runner.rs suites use.

#![allow(clippy::unwrap_used, clippy::expect_used)] // tests-only integration target

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};

use temper_orchestration::RouterPipeline;

const FAKE_SOURCE: &str = r#"
ORDER_LOG = []

class FakeNet:
    def __init__(self, name):
        self.name = name
        self.pins = [0, 1]

class FakeDR:
    def __init__(self):
        self.net_class_assignments = {}
        self.net_classes = {}
        self.default_clearance_mm = 0.3

class FakePcb:
    def __init__(self):
        self.nets = [FakeNet("GND"), FakeNet("SPI_MOSI")]
        self.components = ["U1"]
        self.design_rules = FakeDR()
        self.board = None
    def validate_placement(self):
        ORDER_LOG.append("validate")
        return []

def _net_sort_key(net):
    name = net.name if hasattr(net, "name") else str(net)
    return 0 if name.startswith("GND") else 1

def _run_stage0_setup(pcb, pcb_override=None, net_class_assignments=None,
                      net_classes=None):
    if pcb_override is not None:
        pcb = pcb_override
    pcb.nets.sort(key=_net_sort_key)
    ORDER_LOG.append("stage0_setup")
    return pcb

def parse_kicad_pcb_v6(pcb_path, *, use_declared_layer_roles=False):
    ORDER_LOG.append(("parse", use_declared_layer_roles))
    return FakePcb()

class FakeAuditor:
    def check_collisions(self):
        return []

class FakeLegalizer:
    def __init__(self, pcb):
        ORDER_LOG.append("legalizer_ctor")
        self.auditor = FakeAuditor()
    def legalize(self):
        ORDER_LOG.append("legalize")
        return True

def identify_dense_packages(pcb_components):
    ORDER_LOG.append(("dense", len(pcb_components)))
    return [FakePkg("U1")]

class FakePkg:
    def __init__(self, ref):
        self.component = FakeComp(ref)
        self._ref = ref
        self.requires_escape = True

class FakeComp:
    def __init__(self, ref):
        self.ref = ref

def generate_escape_vias(pkg, design_rules, strategy="dog-bone"):
    ORDER_LOG.append(("escape", strategy))
    return [1]

class Stage3Output:
    def __init__(self, constraint_model=None, solution=None, topology_graph=None):
        self.constraint_model = constraint_model
        self.solution = solution
        self.topology_graph = topology_graph

class RouterV6Result:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class ManufacturingDRCViolationError(Exception):
    pass

class FakeStage2:
    pass

class FakeStage3:
    topology_graph = object()

class FakeRR:
    def __init__(self):
        self.success_count = 3
        self.failure_count = 1

class FakeStage4:
    def __init__(self):
        self.routing_results = FakeRR()

class FakeReport:
    critical_violations = 0
    total_violations = 0

class FakeLedger:
    def __init__(self):
        self.log = ORDER_LOG
    def checkin(self, state_or_pcb):
        ORDER_LOG.append("ledger.checkin")
    def checkout(self, stage_name, state_or_pcb):
        ORDER_LOG.append(("ledger.checkout", stage_name))

class FakePipeline:
    def __init__(self, skip_stage3=False, enable_legalization=True,
                 enable_manufacturing_drc=False, dfm_fail_on="critical",
                 raise_stage=None):
        self.verbose = False
        self.skip_stage3 = skip_stage3
        self.enable_legalization = enable_legalization
        self.enable_manufacturing_drc = enable_manufacturing_drc
        self.dfm_fail_on = dfm_fail_on
        self.fence = None
        self.enable_erc_check = False
        self.last_batch_results = [{"net": "N1"}]
        self.ledger = FakeLedger()
        self._raise_stage = raise_stage
    def _run_stage2(self, pcb, escape_vias):
        ORDER_LOG.append("stage2")
        if self._raise_stage == "stage2":
            raise RuntimeError("boom-stage2")
        return FakeStage2()
    def _compute_resource_bound(self, pcb, stage2):
        ORDER_LOG.append("resource_bound")
    def _run_stage3(self, pcb, stage2):
        ORDER_LOG.append("stage3")
        if self._raise_stage == "stage3":
            raise RuntimeError("boom-stage3")
        return FakeStage3()
    def _run_stage4(self, pcb, stage2, stage3, escape_vias):
        ORDER_LOG.append("stage4")
        if self._raise_stage == "stage4":
            raise RuntimeError("boom-stage4")
        return FakeStage4()
    def _run_manufacturing_drc(self, pcb, routing_results):
        ORDER_LOG.append("manufacturing")
        return FakeReport()
    def _run_fence(self, **kwargs):
        ORDER_LOG.append(("fence", kwargs["stage_name"]))
"#;

/// Register the fake `temper_placer` submodules the driver imports at
/// runtime into sys.modules.
fn install_fakes<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyModule>> {
    let sys = py.import("sys")?;
    let modules: Bound<PyDict> = sys.getattr("modules")?.cast_into()?;

    let ns = PyModule::new(py, "ug_fakes")?;
    let code = std::ffi::CString::new(FAKE_SOURCE).expect("fake source has no NUL");
    py.run(code.as_c_str(), Some(&ns.dict()), Some(&ns.dict()))?;

    let pkg = PyModule::new(py, "temper_placer")?;
    let io = PyModule::new(py, "io")?;
    let kicad_parser = PyModule::new(py, "kicad_parser")?;
    kicad_parser.add("parse_kicad_pcb_v6", ns.getattr("parse_kicad_pcb_v6")?)?;
    io.add("kicad_parser", &kicad_parser)?;
    pkg.add("io", &io)?;

    let router_v6 = PyModule::new(py, "router_v6")?;
    let pipeline_core = PyModule::new(py, "_pipeline_core")?;
    pipeline_core.add("_run_stage0_setup", ns.getattr("_run_stage0_setup")?)?;
    pipeline_core.add("_net_sort_key", ns.getattr("_net_sort_key")?)?;
    router_v6.add("_pipeline_core", &pipeline_core)?;

    let placement_legalization = PyModule::new(py, "placement_legalization")?;
    placement_legalization.add("Legalizer", ns.getattr("FakeLegalizer")?)?;
    router_v6.add("placement_legalization", &placement_legalization)?;

    let dense_package_detection = PyModule::new(py, "dense_package_detection")?;
    dense_package_detection.add(
        "identify_dense_packages",
        ns.getattr("identify_dense_packages")?,
    )?;
    router_v6.add("dense_package_detection", &dense_package_detection)?;

    let escape_via_generator = PyModule::new(py, "escape_via_generator")?;
    escape_via_generator.add("generate_escape_vias", ns.getattr("generate_escape_vias")?)?;
    router_v6.add("escape_via_generator", &escape_via_generator)?;

    let pipeline_types = PyModule::new(py, "_pipeline_types")?;
    pipeline_types.add("Stage3Output", ns.getattr("Stage3Output")?)?;
    pipeline_types.add("RouterV6Result", ns.getattr("RouterV6Result")?)?;
    pipeline_types.add(
        "ManufacturingDRCViolationError",
        ns.getattr("ManufacturingDRCViolationError")?,
    )?;
    router_v6.add("_pipeline_types", &pipeline_types)?;

    pkg.add("router_v6", &router_v6)?;

    modules.set_item("temper_placer", &pkg)?;
    modules.set_item("temper_placer.io", &io)?;
    modules.set_item("temper_placer.io.kicad_parser", &kicad_parser)?;
    modules.set_item("temper_placer.router_v6", &router_v6)?;
    modules.set_item("temper_placer.router_v6._pipeline_core", &pipeline_core)?;
    modules.set_item(
        "temper_placer.router_v6.placement_legalization",
        &placement_legalization,
    )?;
    modules.set_item(
        "temper_placer.router_v6.dense_package_detection",
        &dense_package_detection,
    )?;
    modules.set_item(
        "temper_placer.router_v6.escape_via_generator",
        &escape_via_generator,
    )?;
    modules.set_item("temper_placer.router_v6._pipeline_types", &pipeline_types)?;
    Ok(ns)
}

fn clear_log(ns: &Bound<'_, PyModule>) -> PyResult<()> {
    ns.getattr("ORDER_LOG")?.call_method0("clear")?;
    Ok(())
}

fn read_log(ns: &Bound<'_, PyModule>) -> PyResult<Vec<String>> {
    let log = ns.getattr("ORDER_LOG")?;
    log.try_iter()?
        .map(|item| item.and_then(|v| v.str().map(|s| s.to_string())))
        .collect()
}

#[test]
fn canonical_stage_order_through_pyclass() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        clear_log(&ns)?;

        let pipeline = ns.getattr("FakePipeline")?.call1((false, true))?;
        let cls = py.get_type::<RouterPipeline>();
        let inst = cls.call0()?;
        let result = inst.call_method1(
            "run",
            (
                pipeline,
                "/fake/pcb.kicad_pcb",
                py.None(),
                py.None(),
                py.None(),
                py.None(),
            ),
        )?;

        let log = read_log(&ns)?;
        let expected: Vec<String> = [
            "('parse', True)",
            "stage0_setup",
            "legalizer_ctor",
            "legalize",
            "validate",
            "ledger.checkin",
            "('dense', 1)",
            "('escape', 'dog-bone')",
            "('ledger.checkout', 'escape_vias')",
            "stage2",
            "resource_bound",
            "stage3",
            "stage4",
            "('ledger.checkout', 'routing_complete')",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
        assert_eq!(log, expected, "driver call order diverged");

        // Result assembly: threaded objects + batch_results + runtime.
        assert_eq!(result.getattr("stage2")?.get_type().name()?, "FakeStage2");
        assert_eq!(result.getattr("stage3")?.get_type().name()?, "FakeStage3");
        assert_eq!(result.getattr("stage4")?.get_type().name()?, "FakeStage4");
        assert_eq!(result.getattr("escape_vias")?.len()?, 1);
        let batch = result.getattr("batch_results")?;
        assert_eq!(
            batch.get_item(0)?.get_item("net")?.extract::<String>()?,
            "N1"
        );
        assert!(result.getattr("runtime_seconds")?.extract::<f64>()? >= 0.0);
        assert!(result.getattr("manufacturing_report")?.is_none());
        // the parse carried the plane-condemnation flag
        assert_eq!(log[0], "('parse', True)");

        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn skip_stage3_bypasses_sat_through_pyclass() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        clear_log(&ns)?;

        // The shim-resolved R7 empty Stage3Output (topology_graph=None).
        let empty = ns
            .getattr("Stage3Output")?
            .call1((py.None(), py.None(), py.None()))?;
        let pipeline = ns.getattr("FakePipeline")?.call1((true, false))?;
        let cls = py.get_type::<RouterPipeline>();
        let inst = cls.call0()?;
        let result = inst.call_method1(
            "run",
            (
                pipeline,
                "/fake/pcb.kicad_pcb",
                py.None(),
                py.None(),
                py.None(),
                &empty,
            ),
        )?;

        let log = read_log(&ns)?;
        assert!(
            !log.iter().any(|e| e == "stage3"),
            "skip_stage3 must bypass _run_stage3: {log:?}"
        );
        // the override object was threaded into the result (identity)
        assert!(
            result.getattr("stage3")?.is(&empty),
            "the stage3_override object must be the result's stage3"
        );
        assert!(
            result
                .getattr("stage3")?
                .getattr("topology_graph")?
                .is_none()
        );
        // stage4 still ran on the empty topology
        assert!(log.iter().any(|e| e == "stage4"));
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn stage_exception_propagation_through_pyclass() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        clear_log(&ns)?;

        let pipeline = ns
            .getattr("FakePipeline")?
            .call1((false, true, false, "critical", "stage3"))?;
        let cls = py.get_type::<RouterPipeline>();
        let inst = cls.call0()?;
        let err = inst
            .call_method1(
                "run",
                (
                    pipeline,
                    "/fake/pcb.kicad_pcb",
                    py.None(),
                    py.None(),
                    py.None(),
                    py.None(),
                ),
            )
            .expect_err("the stage3 raise must propagate out of the pyclass");
        let value = err.value(py);
        assert_eq!(value.get_type().name()?, "RuntimeError");
        assert!(value.str()?.to_string().contains("boom-stage3"));

        // stages before the raise ran; the trailing stages did not.
        let log = read_log(&ns)?;
        assert!(log.iter().any(|e| e == "stage2"));
        assert!(!log.iter().any(|e| e == "stage4"));
        assert!(
            !log.iter()
                .any(|e| e == "('ledger.checkout', 'routing_complete')")
        );
        Ok::<(), PyErr>(())
    })
    .unwrap();
}

#[test]
fn result_assembly_fields_through_pyclass() {
    Python::initialize();
    Python::attach(|py| {
        let ns = install_fakes(py)?;
        clear_log(&ns)?;

        // DFM on, fail_on "none": the manufacturing report is threaded.
        let pipeline = ns
            .getattr("FakePipeline")?
            .call1((false, false, true, "none"))?;
        let cls = py.get_type::<RouterPipeline>();
        let inst = cls.call0()?;
        let result = inst.call_method1(
            "run",
            (
                pipeline,
                "/fake/pcb.kicad_pcb",
                py.None(),
                py.None(),
                py.None(),
                py.None(),
            ),
        )?;

        let log = read_log(&ns)?;
        assert!(log.iter().any(|e| e == "manufacturing"));
        assert_eq!(
            result.getattr("manufacturing_report")?.get_type().name()?,
            "FakeReport"
        );
        // pcb is the object the stage0_setup call-back returned (sorted)
        let pcb = result.getattr("pcb")?;
        let net0 = pcb.getattr("nets")?.get_item(0)?;
        assert_eq!(net0.getattr("name")?.extract::<String>()?, "GND");
        Ok::<(), PyErr>(())
    })
    .unwrap();
}
