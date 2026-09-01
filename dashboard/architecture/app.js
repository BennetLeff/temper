(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const TILE_X = 42;
  const TILE_Y = 23;
  const Z_SCALE = 22;
  const ORIGIN = { x: 570, y: 90 };
  const REPO_URL = "https://github.com/BennetLeff/temper";

  const palette = {
    design: { accent: "#47767a", top: "#c9dad5", left: "#a5bbb5", right: "#b7ccc6" },
    core: { accent: "#5e7651", top: "#d5dfc9", left: "#afbea4", right: "#c2d0b7" },
    seam: { accent: "#786179", top: "#dfd2dc", left: "#bcabb9", right: "#cdbdca" },
    verify: { accent: "#a6543d", top: "#e9cabc", left: "#caa391", right: "#dab4a4" },
    runtime: { accent: "#a9792d", top: "#ead6aa", left: "#c9ad72", right: "#dbc18b" }
  };

  const flowColors = {
    design: "#47767a",
    place: "#786179",
    route: "#5e7651",
    verify: "#a6543d",
    runtime: "#a9792d"
  };

  const TRACE_DELAYS = [0, 4800, 3600, 2800, 2000, 1250];

  const districtOffsets = {
    authoring: { x: 0, y: 0 },
    control: { x: .8, y: 0 },
    compute: { x: 0, y: .9 },
    verification: { x: 1.2, y: .6 },
    device: { x: .8, y: .1 }
  };

  const districts = [
    { id: "authoring", index: "01", name: "ELECTRICAL AUTHORING", x: 0, y: 0, w: 8, d: 7 },
    { id: "control", index: "02", name: "DRIVER + CONTRACTS", x: 9, y: 0, w: 8, d: 7 },
    { id: "compute", index: "03", name: "PLACEMENT + ROUTING", x: 2, y: 8, w: 15, d: 8 },
    { id: "verification", index: "04", name: "PHYSICS + GATES", x: 18, y: 7, w: 8, d: 9 },
    { id: "device", index: "05", name: "EMBEDDED RUNTIME", x: 19, y: 0, w: 7, d: 6 }
  ].map(district => ({
    ...district,
    x: district.x + districtOffsets[district.id].x,
    y: district.y + districtOffsets[district.id].y
  }));

  const nodes = [
    {
      id: "atopile", code: "ATO", name: "Atopile model", tech: "SOURCE OF TRUTH", district: "authoring",
      x: 1, y: 1, w: 2.4, d: 1.8, h: 1.7, kind: "design", shape: "tower", flows: ["design", "runtime"],
      subtitle: "Electrical intent, parts, interfaces, and operating-envelope assertions",
      status: ["AUTHORING SSOT", "ATOPILE"], owner: "elec/", boundary: "Design intent", stack: "Atopile DSL",
      summary: "The top-level cooker assembly declares the AC input, 340 V bus, half bridge, resonant tank, sensing, MCU, and hardware safety chain. It is the human-authored electrical model from which net identity and cross-source requirements originate.",
      inputs: ["Part and footprint definitions", "Safety-domain and operating-envelope constraints"],
      outputs: ["Module graph and electrical connectivity", "Named nets, parameters, and netlist inputs"],
      sources: [
        ["elec/src/main.ato", "Top-level Temper induction cooker assembly and operating envelope"],
        ["elec/src/modules.ato", "Power, sensing, safety, and MCU module definitions"],
        ["elec/domain_manifest.yaml", "HV, isolated, and SELV domain declarations"]
      ]
    },
    {
      id: "pcl", code: "PCL", name: "Constraint language", tech: "TYPED INTENT", district: "authoring",
      x: 4.2, y: .8, w: 2.4, d: 1.8, h: 2.4, kind: "design", shape: "prism", flows: ["design", "place"],
      subtitle: "Designer constraints lowered through typed IR into solver instructions",
      status: ["RUST SSOT", "SAT LOWERING"], owner: "temper-pcl-ir", boundary: "Intent → solver", stack: "Rust + PyO3",
      summary: "Placement Constraint Language data is parsed and normalized into a shared typed IR. The constraint compiler lowers designer-level relations through a type lattice and desugaring tiers into the SAT-oriented instruction surface used by placement and routing.",
      inputs: ["Placement constraints YAML", "References, regions, and net-class relations"],
      outputs: ["Typed PCL intermediate representation", "Lowered SAT constraint ISA"],
      sources: [
        ["packages/temper-placer/src/temper_placer/pcl/parser.py", "Python-facing parser seam"],
        ["packages/temper-pcl-ir/src/lib.rs", "Shared typed PCL IR"],
        ["packages/temper-constraint-compiler/src/lib.rs", "Constraint lowering compiler"]
      ]
    },
    {
      id: "kicad", code: "PCB", name: "KiCad design", tech: "BOARD ARTIFACT", district: "authoring",
      x: 2, y: 4, w: 4.2, d: 1.7, h: .65, kind: "design", shape: "board", flows: ["design", "place", "route", "verify", "runtime"],
      subtitle: "Schematics, footprints, copper, zones, and manufacturable board state",
      status: ["BOARD SSOT", "KICAD"], owner: "pcb/", boundary: "EDA artifact", stack: ".kicad_sch + .kicad_pcb",
      summary: "The KiCad project is the concrete board representation consumed by placement, routing, and DRC. The same board carries the physical realization of the sensing, protection, power-stage, and MCU nets that firmware ultimately drives.",
      inputs: ["Electrical netlist and local component libraries", "Placed footprints, routed segments, vias, and zones"],
      outputs: ["Parseable board S-expressions", "Manufacturing and DRC input"],
      sources: [
        ["pcb/temper.kicad_sch", "Root KiCad schematic"],
        ["pcb/temper.kicad_pcb", "Production PCB layout"],
        ["components/", "Repository-local symbols and footprints"]
      ]
    },
    {
      id: "cli", code: "CLI", name: "temper driver", tech: "PROCESS OWNER", district: "control",
      x: 10, y: .8, w: 2.3, d: 1.8, h: 2.6, kind: "core", shape: "tower", flows: ["design", "place", "route", "verify"],
      subtitle: "Rust entry point for parse, place, route, DRC, and pipeline commands",
      status: ["RUST BINARY", "OPTION E DRIVER"], owner: "crates/temper-cli", boundary: "Process lifecycle", stack: "Rust / clap",
      summary: "The temper binary is the migration target for process ownership. Pure-Rust commands parse boards directly; place, route, DRC, and whole-pipeline commands currently cross explicit subprocess seams for operations still owned by Python or kicad-cli.",
      inputs: ["Command, board path, constraints path", "Environment and output paths"],
      outputs: ["Pipeline invocation", "JSON summaries and board artifacts", "Subprocess exit status"],
      sources: [
        ["crates/temper-cli/src/main.rs", "Rust CLI and subprocess-driver commands"],
        ["crates/temper-cli/Cargo.toml", "Driver dependency boundary"]
      ]
    },
    {
      id: "bundle", code: "DB", name: "Design bundle", tech: "VALIDATED BOUNDARY", district: "control",
      x: 13.2, y: .6, w: 2.5, d: 2, h: 3.4, kind: "core", shape: "tower", flows: ["design", "place", "route"],
      subtitle: "Provenance-carrying parse and validation boundary for Atopile, PCL, and KiCad",
      status: ["RUST OWNER", "PROVENANCE"], owner: "temper-design-bundle", boundary: "Untrusted text → model", stack: "Rust + serde",
      summary: "The design bundle turns source artifacts into validated, provenance-aware inputs. It owns parsers and deterministic stage kernels that must agree across the Atopile, PCL, and KiCad sides before optimization begins.",
      inputs: ["KiCad S-expressions", "Atopile/PCL configuration", "Content digests"],
      outputs: ["Validated design records", "Board summaries and hypergraph contracts", "Provenance metadata"],
      sources: [
        ["packages/temper-design-bundle/src/lib.rs", "Public Rust module surface"],
        ["packages/temper-design-bundle/src/parse_engine.rs", "KiCad parse engine"],
        ["packages/temper-design-bundle/src/config_loader.rs", "Constraint configuration loader"]
      ]
    },
    {
      id: "contracts", code: "TYPES", name: "Typed contracts", tech: "PORTABLE STATE", district: "control",
      x: 10.2, y: 4.2, w: 3, d: 1.7, h: 1.7, kind: "core", shape: "prism", flows: ["design", "place", "route", "verify"],
      subtitle: "Owned state, KiCad IO types, and the cross-stage wire format",
      status: ["PURE RUST CORE", "WASM-COMPATIBLE"], owner: "data-model + io-types", boundary: "Stage data", stack: "Rust / serde / JSON",
      summary: "Portable types keep process boundaries explicit: owned components, pins, nets, routes, writer structures, provenance records, and JSON-safe board state. These contracts are the migration seam replacing opaque Python objects with values Rust can own.",
      inputs: ["Validated design records", "Parsed footprints and netlist leaves"],
      outputs: ["NativeBoardState-compatible values", "RouteSet, trace, via, writer, and provenance types"],
      sources: [
        ["packages/temper-data-model/src/lib.rs", "Owned Component, Pin, Net, and Val types"],
        ["packages/temper-io-types/src/lib.rs", "KiCad IO and serialization type surface"],
        ["packages/temper-orchestration/src/board_state.rs", "Python-backed and native BoardState carriers"]
      ]
    },
    {
      id: "seam", code: "FFI", name: "Python seam", tech: "EXPLICIT BOUNDARY", district: "control",
      x: 14.1, y: 4.1, w: 2.2, d: 1.6, h: 2.1, kind: "seam", shape: "frame", flows: ["place", "route"],
      subtitle: "Thin PyO3 shims and subprocesses for the remaining interpreter-owned surfaces",
      status: ["TRANSITIONAL", "FAIL-LOUD"], owner: "temper-placer + PyO3 crates", boundary: "Rust ↔ Python", stack: "PyO3 / JSON / subprocess",
      summary: "This is a deliberate architecture seam, not a second implementation home. Python packages delegate migrated compute into Rust; Rust orchestration invokes Python subprocesses where OR-Tools, kiutils, or stage marshalling have not yet moved.",
      inputs: ["Owned values or JSON board state", "Python objects at legacy stage boundaries"],
      outputs: ["Typed return values", "Explicit stage status and stderr", "No silent fallback"],
      sources: [
        ["packages/temper-orchestration/src/subprocess_stage.rs", "Rust-owned subprocess stage adapter"],
        ["packages/temper-orchestration/src/state_ser.rs", "NativeBoardState JSON codec"],
        ["packages/temper-placer/src/temper_placer/", "Python CLI, shims, and remaining orchestration surfaces"]
      ]
    },
    {
      id: "orchestration", code: "PIPE", name: "Orchestration engine", tech: "D1 → D7 / STAGE 0 → 5", district: "compute",
      x: 7.3, y: 9.3, w: 3.2, d: 2.5, h: 4.2, kind: "core", shape: "tower", flows: ["design", "place", "route", "verify"],
      subtitle: "Rust-owned stage sequencing, board state, failure semantics, and feedback loops",
      status: ["RUST OWNER", "PIPELINE RUNNER"], owner: "temper-orchestration", boundary: "Pipeline control plane", stack: "Rust + optional PyO3",
      summary: "PipelineRunner threads BoardState through deterministic placement and router stages. It owns ordering, observations, stage outcomes, invariants, and failure semantics while the computation behind individual stages may be native Rust or cross an explicit seam.",
      inputs: ["Validated board state and PipelineConfig", "Stage implementations and feedback deltas"],
      outputs: ["Placement and routing state", "PipelineReport / StageReport", "Convergence and failure verdicts"],
      sources: [
        ["packages/temper-orchestration/src/pipeline.rs", "Generic PipelineRunner and report model"],
        ["packages/temper-orchestration/src/deterministic_pipeline.rs", "D1–D7 placement stage order"],
        ["packages/temper-orchestration/src/router_pipeline.rs", "Router Stage 0–5 sequencing"],
        ["packages/temper-orchestration/src/stage.rs", "Stage trait and error contract"]
      ]
    },
    {
      id: "cpsat", code: "SAT", name: "CP-SAT placement", tech: "SOLVER LOOP", district: "compute",
      x: 3.4, y: 10.1, w: 2.8, d: 2.3, h: 2.9, kind: "seam", shape: "chip", flows: ["place", "verify"],
      subtitle: "Constraint encoding, envelope solving, and DRC-informed placement refinement",
      status: ["PYTHON HOST", "RUST KERNELS"], owner: "temper-placer/placer/cp_sat", boundary: "Constraint model", stack: "Python / OR-Tools / Rust",
      summary: "The placement subsystem encodes component envelopes, orientation, zones, proximity, loop-area, isolation, and creepage constraints into CP-SAT. The solve loop returns discrete placements and can incorporate targeted DRC feedback cuts.",
      inputs: ["Typed PCL constraints", "Component envelopes and allowed slots", "DRC feedback cuts"],
      outputs: ["Reference → x/y/rotation placements", "Solver status, diagnostics, and objective metrics"],
      sources: [
        ["packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py", "Public placement encoder surface"],
        ["packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py", "Solve-loop orchestration seam"],
        ["packages/temper-placer/src/temper_placer/placer/cp_sat/feedback.py", "ConstraintDelta feedback classification"],
        ["packages/temper-placer/temper-constraints/src/lib.rs", "Rust SAT encoding primitives"]
      ]
    },
    {
      id: "geometry", code: "GEO", name: "Geometry kernels", tech: "SPATIAL SSOT", district: "compute",
      x: 11.4, y: 9.4, w: 2.6, d: 2.1, h: 2.4, kind: "core", shape: "prism", flows: ["place", "route", "verify"],
      subtitle: "KiCad-correct transforms, pad geometry, clearances, slots, vias, and channels",
      status: ["RUST SSOT", "ORACLE-GATED"], owner: "temper-geometry", boundary: "Physical geometry", stack: "Rust + PyO3",
      summary: "Geometry kernels centralize the spatial rules that placement, routing, containment, and DRC share. The sanctioned KiCad R(-theta) transform is anchored by pcbnew oracles so internally consistent but physically wrong conventions cannot pass unnoticed.",
      inputs: ["Footprint-local geometry and board poses", "Layer roles, net classes, and clearance rules"],
      outputs: ["World positions and polygons", "Distances, channel widths, slots, and via candidates"],
      sources: [
        ["packages/temper-geometry/src/lib.rs", "Geometry module registry and Python surface"],
        ["packages/temper-geometry/src/kicad_transform.rs", "Canonical KiCad coordinate transforms"],
        ["packages/temper-geometry/src/geometry_kernels.rs", "Shared geometry kernels"],
        ["scripts/check_pad_world_position_oracle.py", "pcbnew-backed transform gate"]
      ]
    },
    {
      id: "router", code: "R6", name: "Router V6", tech: "TOPOLOGY → COPPER", district: "compute",
      x: 5.4, y: 13.2, w: 3.5, d: 2.1, h: 3.2, kind: "core", shape: "chip", flows: ["route", "verify"],
      subtitle: "Channel analysis, SAT topology, A*/Theta* realization, and manufacturing checks",
      status: ["RUST CORE", "PYTHON ADAPTER"], owner: "temper-rust-router-core", boundary: "Net topology + paths", stack: "Rust / SAT / A* / PyO3",
      summary: "Routing progresses from board loading and legalization through escape vias, channel analysis, topological solving, geometric realization, and optional manufacturing DRC. The pure Rust core owns solver and graph kernels; a PyO3 package and Python stages connect them to the live board pipeline.",
      inputs: ["Placed board and ordered nets", "Channel skeletons, layer roles, clearances"],
      outputs: ["Topologies and routed paths", "Trace segments, vias, and routing metrics"],
      sources: [
        ["packages/temper-rust-router-core/src/lib.rs", "Pure Rust router core"],
        ["packages/temper-rust-router/src/lib.rs", "PyO3 router extension"],
        ["packages/temper-orchestration/src/router_pipeline.rs", "Runtime stage sequence"],
        ["packages/temper-placer/src/temper_placer/router_v6/", "Board-facing routing stages"]
      ]
    },
    {
      id: "writer", code: "IO", name: "Board writer", tech: "ARTIFACT COMMIT", district: "compute",
      x: 10.2, y: 13.5, w: 2.6, d: 1.8, h: 1.5, kind: "core", shape: "board", flows: ["route"],
      subtitle: "Deterministic KiCad serialization for placements, segments, vias, zones, and provenance",
      status: ["RUST KERNELS", "KIUTILS SEAM"], owner: "temper-io-types", boundary: "State → .kicad_pcb", stack: "Rust / S-expression / Python",
      summary: "Writer kernels produce deterministic KiCad fragments and stable identifiers, while board-object mutation remains on the kiutils-facing seam. The output is a new board path; input boards are not silently overwritten by the Rust driver.",
      inputs: ["Placement coordinates and RouteSet", "Original board text and net-index map"],
      outputs: ["Updated .kicad_pcb", "Stable trace/via ordering and provenance"],
      sources: [
        ["packages/temper-io-types/src/kicad_write_geometry.rs", "KiCad S-expression emission kernels"],
        ["packages/temper-io-types/src/write_types.rs", "Writer-facing type contracts"],
        ["packages/temper-design-bundle/src/write_board_geometry.rs", "Board geometry write orchestration"]
      ]
    },
    {
      id: "thermal", code: "THM", name: "Thermal models", tech: "PHYSICS BOUNDS", district: "verification",
      x: 19.1, y: 8.6, w: 2.3, d: 1.9, h: 2.1, kind: "verify", shape: "prism", flows: ["place", "verify", "runtime"],
      subtitle: "Parameter bounds and thermal property campaigns for layout and protection",
      status: ["RUST OWNER", "PHYSICS"], owner: "temper-thermal", boundary: "Heat and limits", stack: "Rust + PyO3",
      summary: "Thermal kernels bound device and material parameters used to assess candidate layouts and safety behavior. They feed verification and quality decisions; firmware independently consumes concrete sensor readings and thresholds at runtime.",
      inputs: ["Power dissipation, materials, geometry", "RTD and junction parameter ranges"],
      outputs: ["Thermal bounds and derived limits", "Property-campaign results"],
      sources: [
        ["packages/temper-thermal/src/lib.rs", "Thermal module and Python bindings"],
        ["packages/temper-thermal/src/parameter_bounds.rs", "Typed parameter-bound kernels"],
        ["packages/temper-thermal/src/property_campaigns.rs", "Physics property campaigns"]
      ]
    },
    {
      id: "drc", code: "DRC", name: "Design-rule engine", tech: "GEOMETRIC VERDICT", district: "verification",
      x: 22.2, y: 8.2, w: 2.5, d: 2, h: 3.3, kind: "verify", shape: "tower", flows: ["place", "route", "verify"],
      subtitle: "Fast Rust checks plus kicad-cli manufacturing truth and ratcheted ceilings",
      status: ["RUST ENGINE", "KICAD ORACLE"], owner: "temper-drc-rs", boundary: "Board → violations", stack: "Rust / rstar / kicad-cli",
      summary: "The Rust DRC engine performs indexed geometric checks and marshals structured violations. Manufacturing sign-off still asks kicad-cli through the sanctioned harness, with nondeterministic categories handled by sampled ceilings and provenance rather than a single optimistic run.",
      inputs: ["Board geometry, rules, and net classes", "Generated DRU and KiCad library environment"],
      outputs: ["Typed DRC errors and warnings", "Feedback cuts and regression counts", "Provenance-bound ceiling verdict"],
      sources: [
        ["packages/temper-drc-rs/src/lib.rs", "Rust DRC engine and PyO3 boundary"],
        ["packages/temper-placer/src/temper_placer/validation/_drc_api.py", "Sanctioned kicad-cli harness"],
        ["power_pcb_dataset/drc_ceiling.json", "Measured regression ceiling and provenance"],
        ["scripts/ci_check_drc.py", "DRC ratchet gate"]
      ]
    },
    {
      id: "quality", code: "QO", name: "Quality oracle", tech: "SIX-LAYER SCORE", district: "verification",
      x: 19.4, y: 11.7, w: 2.5, d: 2, h: 2.7, kind: "verify", shape: "cylinder", flows: ["place", "route", "verify"],
      subtitle: "Pure Rust aggregation of routing, placement, DRC, thermal, and zone quality",
      status: ["PURE RUST", "TYPED VERDICT"], owner: "temper-quality-oracle", boundary: "Metrics → pass/fail", stack: "Rust + PyO3",
      summary: "The quality oracle combines precomputed metrics into normalized scores and typed pass/fail verdicts. It is deliberately downstream of measurement: it judges placement and routing data but does not invent missing physical evidence.",
      inputs: ["Placement, routing, DRC, thermal, and zone metrics", "Derived quality configuration"],
      outputs: ["QualityMetrics", "Pass/fail verdict and violations", "Component scores"],
      sources: [
        ["packages/temper-quality-oracle/src/lib.rs", "Public oracle and binding surface"],
        ["packages/temper-quality-oracle/src/oracle.rs", "Prepared evaluation pipeline"],
        ["packages/temper-quality-oracle/src/types.rs", "QualityConfig, metrics, and verdict types"]
      ]
    },
    {
      id: "ci", code: "CI", name: "Repository gates", tech: "MERGE CONTROL", district: "verification",
      x: 22.4, y: 12, w: 2.5, d: 2.1, h: 4.5, kind: "verify", shape: "tower", flows: ["design", "place", "route", "verify", "runtime"],
      subtitle: "Cross-source consistency, Rust/Python tests, provenance, firmware proofs, and regeneration",
      status: ["GITHUB ACTIONS", "FAIL-CLOSED GATES"], owner: ".github + scripts", boundary: "Commit → evidence", stack: "Actions / Python / Rust / CMake",
      summary: "CI treats generated artifacts, extension freshness, import boundaries, physics provenance, board measurements, firmware invariants, and differential oracles as architecture contracts. Required checks are path-routed through a machine-readable manifest.",
      inputs: ["Changed paths and generated artifacts", "Tests, oracles, measurements, and provenance records"],
      outputs: ["Required-check status", "Regression and consistency verdicts", "Recorded metrics artifacts"],
      sources: [
        [".github/required-checks.json", "Path-to-required-check routing contract"],
        [".github/workflows/python-tests.yml", "Core Rust/Python and consistency gates"],
        [".github/workflows/firmware-tests.yml", "Firmware model, invariant, mutation, and host tests"],
        ["Makefile", "Regeneration and extension lifecycle entry points"]
      ]
    },
    {
      id: "firmware_manifest", code: "CFG", name: "Firmware manifests", tech: "GENERATED CONTRACT", district: "device",
      x: 20, y: .8, w: 2.2, d: 1.7, h: 1.4, kind: "runtime", shape: "prism", flows: ["runtime", "verify"],
      subtitle: "Configuration, transition table, invariants, and board-derived contracts",
      status: ["YAML SSOT", "CODEGEN"], owner: "firmware/*.yaml", boundary: "Manifest → C", stack: "YAML / Python codegen",
      summary: "Runtime thresholds and allowed state transitions are authored as manifests, then rendered into committed C headers and generated tests. CI regenerates them and rejects drift, so firmware behavior is traceable back to declarative inputs.",
      inputs: ["Control thresholds and timing constants", "Nine-state transition rules", "Board-derived GPIO and safety contracts"],
      outputs: ["config.h and transition_table.h", "Generated transition tests and invariant proofs"],
      sources: [
        ["firmware/config.yaml", "Firmware tunable-parameter source"],
        ["firmware/transition_table.yaml", "Nine-state transition source"],
        ["firmware/tools/gen_config.py", "Configuration header generator"],
        ["firmware/tools/gen_transition_table.py", "Transition-table generator"]
      ]
    },
    {
      id: "firmware", code: "ESP", name: "Control firmware", tech: "9-STATE MACHINE", district: "device",
      x: 23, y: .7, w: 2.3, d: 2, h: 3.7, kind: "runtime", shape: "chip", flows: ["runtime", "verify"],
      subtitle: "ESP32-S3 control loop, safety monitoring, PID/PLL, and fail-safe outputs",
      status: ["C / ESP-IDF", "REAL-TIME"], owner: "firmware/main", boundary: "Digital controller", stack: "C / ESP32-S3",
      summary: "The firmware state machine moves through INIT, IDLE, PAN_DET, PREHEAT, HEATING, NO_PAN, COOLDOWN, FAULT, and RUNAWAY_FAULT. It samples hardware status, computes control outputs, kicks the external watchdog, and drives shutdown-safe actuators.",
      inputs: ["RTD, bus-current, voltage, tach, buttons, and fault GPIOs", "Generated thresholds and transition table"],
      outputs: ["PWM and gate-enable intent", "Fan, discharge relay, watchdog kick", "Fault code and runtime state"],
      sources: [
        ["firmware/main/main.c", "ESP-IDF application entry and hardware seams"],
        ["firmware/main/state_machine.c", "Nine-state control implementation"],
        ["firmware/components/control/", "PID and PLL control"],
        ["firmware/components/safety/", "Safety monitoring and fault handling"]
      ]
    },
    {
      id: "physical", code: "HW", name: "Cooker plant", tech: "POWER + SENSORS", district: "device",
      x: 20.4, y: 3.8, w: 4.3, d: 1.5, h: 1.1, kind: "runtime", shape: "board", flows: ["runtime", "verify"],
      subtitle: "Mains front end, 340 V bus, half bridge, resonant tank, coil, safety, and sensing",
      status: ["PHYSICAL", "HARDWARE-LATCHED SAFETY"], owner: "elec + pcb", boundary: "Electrons and heat", stack: "ESP32-S3 / IGBT / RTD",
      summary: "The physical system converts mains power through a high-voltage bus and IGBT half bridge into the resonant induction tank. Current, temperature, fan, watchdog, and interlock circuits return observations or force shutdown independently of software.",
      inputs: ["120 V AC and user intent", "PWM/gate drive, fan, and discharge control"],
      outputs: ["Induction heating", "Analog and digital safety observations", "Hardware SHUTDOWN_N behavior"],
      sources: [
        ["elec/src/main.ato", "Top-level electrical power and control graph"],
        ["pcb/temper.kicad_pcb", "Physical board implementation"],
        ["docs/hardware/PROTECTION_CHAIN_REVIEW.md", "Protection-chain design and status"],
        ["firmware/README.md", "GPIO and runtime hardware contracts"]
      ]
    }
  ].map(node => ({
    ...node,
    x: node.x + districtOffsets[node.district].x,
    y: node.y + districtOffsets[node.district].y
  }));

  const edges = [
    ["atopile", "bundle", "design", "module graph + net identity"],
    ["pcl", "bundle", "design", "constraints + configuration"],
    ["kicad", "bundle", "design", "board S-expressions"],
    ["bundle", "contracts", "design", "validated bundle + provenance"],
    ["cli", "orchestration", "design", "command + artifact paths"],
    ["contracts", "orchestration", "place", "NativeBoardState + PipelineConfig"],
    ["pcl", "cpsat", "place", "typed IR + SAT instructions"],
    ["orchestration", "seam", "place", "stage state / subprocess request"],
    ["seam", "cpsat", "place", "Python objects + OR-Tools model"],
    ["geometry", "cpsat", "place", "envelopes + clearance geometry"],
    ["thermal", "cpsat", "place", "physics bounds + penalties"],
    ["cpsat", "orchestration", "place", "x / y / rotation placements"],
    ["orchestration", "geometry", "place", "pads + slots + net classes"],
    ["drc", "cpsat", "place", "targeted ConstraintDelta cuts"],
    ["orchestration", "router", "route", "placed board + net order"],
    ["geometry", "router", "route", "channels + via candidates"],
    ["router", "writer", "route", "RouteSet: traces + vias"],
    ["writer", "kicad", "route", "deterministic .kicad_pcb update"],
    ["kicad", "drc", "verify", "board + generated DRU"],
    ["geometry", "drc", "verify", "polygons + spacing rules"],
    ["drc", "orchestration", "verify", "typed violations + stage verdict"],
    ["cpsat", "quality", "verify", "placement metrics"],
    ["router", "quality", "verify", "routing + connectivity metrics"],
    ["drc", "quality", "verify", "error / warning metrics"],
    ["quality", "ci", "verify", "QualityVerdict + scorecard"],
    ["firmware_manifest", "firmware", "runtime", "generated C contracts"],
    ["physical", "firmware", "runtime", "RTD / current / tach / faults"],
    ["firmware", "physical", "runtime", "PWM / fan / relay / watchdog"],
    ["firmware", "ci", "verify", "host tests + invariant proofs"],
    ["kicad", "ci", "verify", "provenance + cross-source gates"]
  ].map((edge, index) => ({ id: `edge-${index}`, from: edge[0], to: edge[1], flow: edge[2], payload: edge[3] }));

  if (globalThis.TEMPER_ATLAS_VALIDATE_ONLY) {
    globalThis.TEMPER_ATLAS_DATA = { districts, nodes, edges, palette, flowColors };
    return;
  }

  const nodeById = new Map(nodes.map(node => [node.id, node]));
  const svg = document.querySelector("#system-map");
  const viewport = document.querySelector("#viewport");
  const districtLayer = document.querySelector("#district-layer");
  const edgeLayer = document.querySelector("#edge-layer");
  const nodeLayer = document.querySelector("#node-layer");
  const labelLayer = document.querySelector("#label-layer");
  const inspector = document.querySelector("#inspector-content");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const traceSpeed = document.querySelector("#trace-speed");
  const traceSpeedValue = document.querySelector("#trace-speed-value");
  const buildStatus = document.querySelector("#build-status");
  const focusName = document.querySelector("#focus-name");
  const focusDetail = document.querySelector("#focus-detail");

  let selectedNode = "orchestration";
  let selectedFlow = "all";
  let selectedTab = "details";
  let traceTimer = null;
  let traceStep = null;
  let traceIndex = -1;
  let transform = { x: -56, y: 2, scale: .86 };
  let dragState = null;
  let dragFrame = null;

  const buildInfo = globalThis.TEMPER_ATLAS_BUILD;
  if (buildInfo?.commit && buildInfo.commit !== "working-tree") {
    const shortCommit = buildInfo.commit.slice(0, 7);
    buildStatus.textContent = `${buildInfo.ref}@${shortCommit}`.toUpperCase();
    buildStatus.title = `Published from ${buildInfo.ref} at commit ${buildInfo.commit}`;
  }
  focusDetail.textContent = `${nodes.length} structures · ${edges.length} payload paths`;

  const project = (x, y, z = 0) => ({
    x: ORIGIN.x + (x - y) * TILE_X,
    y: ORIGIN.y + (x + y) * TILE_Y - z * Z_SCALE
  });

  const el = (tag, attrs = {}, parent = null) => {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (parent) parent.appendChild(node);
    return node;
  };

  const points = list => list.map(point => `${point.x},${point.y}`).join(" ");
  const nodeCenter = node => project(node.x + node.w / 2, node.y + node.d / 2, node.h + .12);

  function applyTransform() {
    viewport.setAttribute("transform", `translate(${transform.x} ${transform.y}) scale(${transform.scale})`);
  }

  function renderDistricts() {
    districts.forEach(district => {
      const corners = [
        project(district.x, district.y),
        project(district.x + district.w, district.y),
        project(district.x + district.w, district.y + district.d),
        project(district.x, district.y + district.d)
      ];
      el("polygon", { class: `district-floor district-${district.id}`, points: points(corners) }, districtLayer);

      for (let x = 1; x < district.w; x += 1) {
        const a = project(district.x + x, district.y);
        const b = project(district.x + x, district.y + district.d);
        el("line", { class: "district-grid-line", x1: a.x, y1: a.y, x2: b.x, y2: b.y }, districtLayer);
      }
      for (let y = 1; y < district.d; y += 1) {
        const a = project(district.x, district.y + y);
        const b = project(district.x + district.w, district.y + y);
        el("line", { class: "district-grid-line", x1: a.x, y1: a.y, x2: b.x, y2: b.y }, districtLayer);
      }

      const labelPos = project(district.x, district.y, .08);
      const label = el("text", { class: "district-label", x: labelPos.x - 2, y: labelPos.y - 11 }, labelLayer);
      const index = el("tspan", { class: "district-index" }, label);
      index.textContent = `${district.index}  `;
      label.appendChild(document.createTextNode(district.name));
    });
  }

  function edgeCurve(from, to, bend = 0) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const normal = Math.max(-72, Math.min(72, (dx * .05 - dy * .04) + bend));
    const c1 = { x: from.x + dx * .34 + normal, y: from.y + dy * .18 - normal * .25 };
    const c2 = { x: from.x + dx * .68 + normal, y: from.y + dy * .82 - normal * .25 };
    return `M ${from.x} ${from.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${to.x} ${to.y}`;
  }

  function renderEdges() {
    edges.forEach((edge, index) => {
      const from = nodeCenter(nodeById.get(edge.from));
      const to = nodeCenter(nodeById.get(edge.to));
      const group = el("g", {
        class: "architecture-edge",
        "data-edge": edge.id,
        "data-flow": edge.flow,
        style: `--edge-color:${flowColors[edge.flow]}`
      }, edgeLayer);
      const curve = edgeCurve(from, to, (index % 3 - 1) * 10);
      el("path", { class: "edge-underlay", d: curve }, group);
      el("path", { class: "edge-selection-halo", d: curve }, group);
      el("path", { class: "edge-path", d: curve, "marker-end": `url(#arrow-${edge.flow})` }, group);
      const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - 8 };
      const tracerPosition = reducedMotion ? { cx: mid.x, cy: mid.y + 8 } : {};
      const tracer = el("circle", { class: "edge-tracer", r: "5", "aria-hidden": "true", ...tracerPosition }, group);
      if (!reducedMotion) el("animateMotion", { path: curve, dur: "1.4s", repeatCount: "indefinite", begin: "indefinite" }, tracer);
      const length = Math.hypot(to.x - from.x, to.y - from.y) || 1;
      const labelSpread = (index % 5 - 2) * 11;
      const labelX = mid.x - ((to.y - from.y) / length) * labelSpread;
      const labelY = mid.y + ((to.x - from.x) / length) * labelSpread;
      const label = el("text", { class: "edge-label", x: labelX, y: labelY, "text-anchor": "middle" }, group);
      label.textContent = `${edge.flow.toUpperCase()} · ${edge.payload}`;
    });
  }

  function prismFaces(node, zBase = 0, height = node.h, inset = 0) {
    const x = node.x + inset;
    const y = node.y + inset;
    const w = node.w - inset * 2;
    const d = node.d - inset * 2;
    const z = zBase + height;
    const base = [project(x, y, zBase), project(x + w, y, zBase), project(x + w, y + d, zBase), project(x, y + d, zBase)];
    const top = [project(x, y, z), project(x + w, y, z), project(x + w, y + d, z), project(x, y + d, z)];
    return { base, top };
  }

  function drawPrism(node, group, zBase = 0, height = node.h, inset = 0) {
    const { base, top } = prismFaces(node, zBase, height, inset);
    el("polygon", { class: "node-face face-left", points: points([top[3], top[2], base[2], base[3]]) }, group);
    el("polygon", { class: "node-face face-right", points: points([top[1], top[2], base[2], base[1]]) }, group);
    el("polygon", { class: "node-face face-top", points: points(top) }, group);
  }

  function drawTower(node, group) {
    drawPrism(node, group);
    const floors = Math.max(2, Math.floor(node.h));
    for (let i = 1; i < floors; i += 1) {
      const z = (node.h / floors) * i;
      const a = project(node.x, node.y + node.d, z);
      const b = project(node.x + node.w, node.y + node.d, z);
      const c = project(node.x + node.w, node.y, z);
      el("line", { class: "floor-line", x1: a.x, y1: a.y, x2: b.x, y2: b.y }, group);
      el("line", { class: "floor-line", x1: b.x, y1: b.y, x2: c.x, y2: c.y }, group);
    }
  }

  function drawBoard(node, group) {
    drawPrism(node, group);
    const z = node.h + .03;
    for (let i = .45; i < node.w; i += .62) {
      const a = project(node.x + i, node.y + .25, z);
      const b = project(node.x + i, node.y + node.d - .25, z);
      el("line", { class: "floor-line", x1: a.x, y1: a.y, x2: b.x, y2: b.y }, group);
    }
    for (let i = .35; i < node.d; i += .55) {
      const a = project(node.x + .25, node.y + i, z);
      const b = project(node.x + node.w - .25, node.y + i, z);
      el("line", { class: "floor-line", x1: a.x, y1: a.y, x2: b.x, y2: b.y }, group);
    }
  }

  function drawChip(node, group) {
    drawPrism(node, group, 0, node.h, .18);
    const pins = 5;
    for (let i = 0; i < pins; i += 1) {
      const t = (i + .5) / pins;
      const leftA = project(node.x, node.y + node.d * t, .32);
      const leftB = project(node.x + .18, node.y + node.d * t, .32);
      const rightA = project(node.x + node.w - .18, node.y + node.d * t, .32);
      const rightB = project(node.x + node.w, node.y + node.d * t, .32);
      el("line", { class: "hardware-pin", x1: leftA.x, y1: leftA.y, x2: leftB.x, y2: leftB.y }, group);
      el("line", { class: "hardware-pin", x1: rightA.x, y1: rightA.y, x2: rightB.x, y2: rightB.y }, group);
    }
  }

  function drawFrame(node, group) {
    drawPrism(node, group);
    const inner = prismFaces(node, node.h + .02, .02, .42).top;
    el("polygon", { points: points(inner), fill: "#eee5d2", stroke: "var(--stroke)", "stroke-width": ".8" }, group);
  }

  function drawCylinder(node, group) {
    const centerTop = project(node.x + node.w / 2, node.y + node.d / 2, node.h);
    const centerBase = project(node.x + node.w / 2, node.y + node.d / 2, 0);
    const rx = node.w * TILE_X * .7;
    const ry = node.d * TILE_Y * .65;
    const bodyPath = `M ${centerTop.x - rx} ${centerTop.y} L ${centerBase.x - rx} ${centerBase.y} A ${rx} ${ry} 0 0 0 ${centerBase.x + rx} ${centerBase.y} L ${centerTop.x + rx} ${centerTop.y} A ${rx} ${ry} 0 0 1 ${centerTop.x - rx} ${centerTop.y}`;
    el("path", { class: "node-face face-left", d: bodyPath }, group);
    el("ellipse", { class: "node-face face-top", cx: centerTop.x, cy: centerTop.y, rx, ry }, group);
    for (let i = 1; i < 3; i += 1) {
      const z = node.h * i / 3;
      const center = project(node.x + node.w / 2, node.y + node.d / 2, z);
      el("path", { class: "floor-line", d: `M ${center.x - rx} ${center.y} A ${rx} ${ry} 0 0 0 ${center.x + rx} ${center.y}` }, group);
    }
  }

  function renderNodes() {
    nodes.forEach(node => {
      const colors = palette[node.kind];
      const group = el("g", {
        class: "architecture-node",
        tabindex: "0",
        role: "button",
        "aria-label": `${node.name}: ${node.subtitle}`,
        "data-node": node.id,
        style: `--accent:${colors.accent};--stroke:${colors.accent}88;--top:${colors.top};--left:${colors.left};--right:${colors.right}`
      }, nodeLayer);

      if (node.shape === "tower") drawTower(node, group);
      else if (node.shape === "board") drawBoard(node, group);
      else if (node.shape === "chip") drawChip(node, group);
      else if (node.shape === "frame") drawFrame(node, group);
      else if (node.shape === "cylinder") drawCylinder(node, group);
      else drawPrism(node, group);

      const codePos = project(node.x + .22, node.y + .2, node.h + .05);
      const code = el("text", { class: "node-code", x: codePos.x, y: codePos.y - 5 }, group);
      code.textContent = node.code;

      const labelPos = project(node.x + node.w / 2, node.y + node.d + .22, 0);
      const name = el("text", { class: "node-name node-label", "data-node": node.id, x: labelPos.x, y: labelPos.y + 11, "text-anchor": "middle" }, labelLayer);
      name.textContent = node.name;
      const tech = el("text", { class: "node-tech node-label", "data-node": node.id, x: labelPos.x, y: labelPos.y + 23, "text-anchor": "middle" }, labelLayer);
      tech.textContent = node.tech;

      group.addEventListener("click", event => {
        event.stopPropagation();
        stopTrace();
        selectNode(node.id);
      });
      group.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          stopTrace();
          selectNode(node.id);
        }
      });
    });
  }

  function selectNode(id, options = {}) {
    selectedNode = id;
    const node = nodeById.get(id);
    const incident = new Set(edges.filter(edge => edge.from === id || edge.to === id).map(edge => edge.id));
    const connected = new Set(edges.flatMap(edge => {
      if (edge.from === id) return [edge.to];
      if (edge.to === id) return [edge.from];
      return [];
    }));

    document.querySelectorAll(".architecture-node, .node-label").forEach(element => {
      const elementId = element.dataset.node;
      element.classList.toggle("selected", elementId === id);
      element.classList.toggle("connected", connected.has(elementId));
      element.classList.toggle("context-muted", elementId !== id && !connected.has(elementId));
    });
    document.querySelectorAll(".architecture-edge").forEach(element => {
      element.classList.toggle("active", options.highlightEdges !== false && incident.has(element.dataset.edge));
      element.classList.toggle("context-muted", !incident.has(element.dataset.edge));
    });
    focusName.textContent = `${node.name.toLowerCase()} → ${incident.size} connections`;
    focusDetail.textContent = node.subtitle;
    if (!options.keepTab) selectedTab = "details";
    updateTabs();
    renderInspector();
  }

  function setFlow(flow) {
    selectedFlow = flow;
    stopTrace();
    document.querySelectorAll(".flow-filter").forEach(button => button.classList.toggle("active", button.dataset.flow === flow));
    document.querySelectorAll(".architecture-edge").forEach(element => {
      element.classList.toggle("inactive", flow !== "all" && element.dataset.flow !== flow);
    });
    document.querySelectorAll(".architecture-node, .node-label").forEach(element => {
      const node = nodeById.get(element.dataset.node);
      element.classList.toggle("inactive", flow !== "all" && !node.flows.includes(flow));
    });
    const activeEdges = flow === "all" ? edges : edges.filter(edge => edge.flow === flow);
    focusName.textContent = flow === "all" ? "full system" : `${flow} flow`;
    focusDetail.textContent = `${activeEdges.length} payload paths · click a structure to inspect`;
  }

  function pathLink(path) {
    const safePath = path.replaceAll("#", "%23");
    const view = path.endsWith("/") ? "tree" : "blob";
    return `${REPO_URL}/${view}/main/${safePath}`;
  }

  function detailMarkup(node) {
    return `
      <p class="eyebrow" style="--accent:${palette[node.kind].accent}">${node.district} / ${node.code}</p>
      <h1>${node.name}</h1>
      <p class="inspector-subtitle">${node.subtitle}</p>
      <div class="status-row">${node.status.map(status => `<span class="status-pill">${status}</span>`).join("")}</div>
      <dl class="fact-grid">
        <div class="fact"><dt>OWNER</dt><dd>${node.owner}</dd></div>
        <div class="fact"><dt>BOUNDARY</dt><dd>${node.boundary}</dd></div>
        <div class="fact"><dt>STACK</dt><dd>${node.stack}</dd></div>
        <div class="fact"><dt>CONNECTIONS</dt><dd>${edges.filter(edge => edge.from === node.id || edge.to === node.id).length} traced paths</dd></div>
      </dl>
      <section class="inspector-section"><h2 class="section-label">WHAT IT DOES</h2><p>${node.summary}</p></section>
      <section class="inspector-section"><h2 class="section-label">WHAT MOVES IN</h2><ul class="payload-list">${node.inputs.map(value => `<li>${value}</li>`).join("")}</ul></section>
      <section class="inspector-section"><h2 class="section-label">WHAT MOVES OUT</h2><ul class="payload-list">${node.outputs.map(value => `<li>${value}</li>`).join("")}</ul></section>`;
  }

  function flowsMarkup(node) {
    const incident = edges.filter(edge => edge.from === node.id || edge.to === node.id);
    return `
      <p class="eyebrow" style="--accent:${palette[node.kind].accent}">${node.code} / LIVE DEPENDENCIES</p>
      <h1>${node.name}</h1>
      <p class="inspector-subtitle">Payloads are labeled at the boundary where ownership changes.</p>
      <ol class="flow-list">${incident.map(edge => {
        const outbound = edge.from === node.id;
        const peer = nodeById.get(outbound ? edge.to : edge.from);
        return `<li class="flow-item" style="--flow-color:${flowColors[edge.flow]}">
          <div class="flow-direction">${outbound ? "OUT TO" : "IN FROM"} · ${edge.flow.toUpperCase()}</div>
          <div class="flow-title">${peer.name}</div>
          <div class="flow-payload">${edge.payload}</div>
        </li>`;
      }).join("")}</ol>`;
  }

  function sourcesMarkup(node) {
    return `
      <p class="eyebrow" style="--accent:${palette[node.kind].accent}">${node.code} / REPOSITORY EVIDENCE</p>
      <h1>${node.name}</h1>
      <p class="inspector-subtitle">These files define, connect, or verify this structure. Links resolve from the map’s dashboard directory.</p>
      <ul class="source-list">${node.sources.map(([path, description]) => `<li><a href="${pathLink(path)}" target="_blank" rel="noreferrer"><span>${path}</span><small>${description}</small></a></li>`).join("")}</ul>`;
  }

  function renderInspector() {
    const node = nodeById.get(selectedNode);
    inspector.style.setProperty("--accent", palette[node.kind].accent);
    inspector.innerHTML = selectedTab === "details" ? detailMarkup(node) : selectedTab === "flows" ? flowsMarkup(node) : sourcesMarkup(node);
    inspector.scrollTop = 0;
  }

  function updateTabs() {
    document.querySelectorAll(".tab").forEach(button => {
      const active = button.dataset.tab === selectedTab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    inspector.setAttribute("aria-labelledby", `tab-${selectedTab}`);
  }

  function startTrace() {
    if (traceTimer) {
      stopTrace();
      return;
    }
    const traceEdges = selectedFlow === "all" ? edges : edges.filter(edge => edge.flow === selectedFlow);
    if (!traceEdges.length) return;
    const button = document.querySelector("#trace-flow");
    button.classList.add("running");
    button.querySelector(".play-icon").textContent = "■";
    traceIndex = -1;
    traceStep = () => {
      document.querySelectorAll(".trace-active").forEach(element => {
        element.querySelector("animateMotion")?.endElement();
        element.classList.remove("trace-active");
      });
      traceIndex = (traceIndex + 1) % traceEdges.length;
      const edge = traceEdges[traceIndex];
      const traceElement = document.querySelector(`[data-edge="${edge.id}"]`);
      traceElement.classList.add("trace-active");
      traceElement.querySelector("animateMotion")?.beginElement();
      selectNode(edge.to, { keepTab: true, highlightEdges: false });
      focusName.textContent = `trace ${traceIndex + 1}/${traceEdges.length} · ${nodeById.get(edge.from).name.toLowerCase()} → ${nodeById.get(edge.to).name.toLowerCase()}`;
      focusDetail.textContent = edge.payload;
    };
    traceStep();
    traceTimer = window.setInterval(traceStep, currentTraceDelay());
  }

  function stopTrace() {
    if (traceTimer) window.clearInterval(traceTimer);
    traceTimer = null;
    traceStep = null;
    traceIndex = -1;
    document.querySelectorAll(".trace-active").forEach(element => {
      element.querySelector("animateMotion")?.endElement();
      element.classList.remove("trace-active");
    });
    const button = document.querySelector("#trace-flow");
    button.classList.remove("running");
    button.querySelector(".play-icon").textContent = "▶";
  }

  function currentTraceDelay() {
    return TRACE_DELAYS[Number(traceSpeed.value)];
  }

  function updateTraceSpeed() {
    const delay = currentTraceDelay();
    const seconds = (delay / 1000).toFixed(delay % 1000 === 0 ? 0 : 1);
    traceSpeedValue.textContent = `${seconds}s / step`;
    traceSpeed.setAttribute("aria-valuetext", `${seconds} seconds per step`);
    document.querySelectorAll("animateMotion").forEach(motion => motion.setAttribute("dur", `${Math.max(.9, delay * .72 / 1000)}s`));
    if (traceTimer && traceStep) {
      window.clearInterval(traceTimer);
      traceTimer = window.setInterval(traceStep, delay);
    }
  }

  function zoomBy(factor, anchor = { x: 660, y: 430 }) {
    const oldScale = transform.scale;
    const newScale = Math.max(.52, Math.min(1.7, oldScale * factor));
    const ratio = newScale / oldScale;
    transform.x = anchor.x - (anchor.x - transform.x) * ratio;
    transform.y = anchor.y - (anchor.y - transform.y) * ratio;
    transform.scale = newScale;
    applyTransform();
  }

  function resetView() {
    transform = { x: -56, y: 2, scale: .86 };
    applyTransform();
    setFlow("all");
    selectNode("orchestration");
  }

  function clientPoint(event, inverse = svg.getScreenCTM()?.inverse()) {
    if (!inverse) return { x: event.clientX, y: event.clientY };
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(inverse);
  }

  svg.addEventListener("wheel", event => {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 1.1 : .9, clientPoint(event));
  }, { passive: false });

  svg.addEventListener("pointerdown", event => {
    if (dragState || event.target.closest(".architecture-node")) return;
    svg.setPointerCapture(event.pointerId);
    const inverse = svg.getScreenCTM()?.inverse();
    const point = clientPoint(event, inverse);
    dragState = {
      pointerId: event.pointerId,
      x: point.x,
      y: point.y,
      tx: transform.x,
      ty: transform.y,
      inverse
    };
    svg.classList.add("dragging");
  });

  svg.addEventListener("pointermove", event => {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    const point = clientPoint(event, dragState.inverse);
    transform.x = dragState.tx + point.x - dragState.x;
    transform.y = dragState.ty + point.y - dragState.y;
    if (!dragFrame) {
      dragFrame = window.requestAnimationFrame(() => {
        dragFrame = null;
        applyTransform();
      });
    }
  });

  function endDrag(event) {
    if (!dragState || event.pointerId !== dragState.pointerId) return;
    const pointerId = dragState.pointerId;
    dragState = null;
    if (dragFrame) {
      window.cancelAnimationFrame(dragFrame);
      dragFrame = null;
      applyTransform();
    }
    svg.classList.remove("dragging");
    if (event.type !== "lostpointercapture" && svg.hasPointerCapture(pointerId)) svg.releasePointerCapture(pointerId);
  }

  svg.addEventListener("pointerup", endDrag);
  svg.addEventListener("pointercancel", endDrag);
  svg.addEventListener("lostpointercapture", endDrag);

  document.querySelectorAll(".flow-filter").forEach(button => button.addEventListener("click", () => setFlow(button.dataset.flow)));
  const tabs = [...document.querySelectorAll(".tab")];
  tabs.forEach((button, index) => {
    button.addEventListener("click", () => {
      stopTrace();
      selectedTab = button.dataset.tab;
      updateTabs();
      renderInspector();
    });
    button.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[nextIndex].click();
      tabs[nextIndex].focus();
    });
  });
  document.querySelector("#zoom-in").addEventListener("click", () => zoomBy(1.14));
  document.querySelector("#zoom-out").addEventListener("click", () => zoomBy(.86));
  document.querySelector("#reset-view").addEventListener("click", resetView);
  document.querySelector("#trace-flow").addEventListener("click", startTrace);
  traceSpeed.addEventListener("input", updateTraceSpeed);

  renderDistricts();
  renderEdges();
  renderNodes();
  updateTraceSpeed();
  applyTransform();
  selectNode(selectedNode);
})();
