//! Bounded four-material bridge package FEM model.
//!
//! The model is intentionally small and explicit: Gmsh owns geometry and
//! Elmer owns the coupled electrical/thermal solve.  Rust owns the input
//! contract, mesh census, output interpretation, and replay verdict.  A
//! retained run can therefore never become valid merely by changing hashes.

use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

// Large immutable meshes may be stored as gzip. Hashes always cover the
// original bytes, so lossless archival does not change the evidence identity.
fn read_artifact(path: impl AsRef<Path>) -> Result<Vec<u8>> {
    use std::io::Read;
    let path = path.as_ref();
    let mut name = path.as_os_str().to_os_string();
    name.push(".gz");
    let compressed = PathBuf::from(name);
    ensure!(
        !(path.exists() && compressed.exists()),
        "ambiguous raw and compressed evidence"
    );
    const LIMIT: u64 = 64 * 1024 * 1024;
    let mut bytes = Vec::new();
    if path.exists() {
        std::fs::File::open(path)?
            .take(LIMIT + 1)
            .read_to_end(&mut bytes)?;
    } else {
        flate2::read::MultiGzDecoder::new(std::fs::File::open(&compressed)?)
            .take(LIMIT + 1)
            .read_to_end(&mut bytes)?;
    }
    ensure!(
        bytes.len() as u64 <= LIMIT,
        "evidence artifact exceeds 64 MiB limit"
    );
    Ok(bytes)
}

fn read_text(path: impl AsRef<Path>) -> Result<String> {
    Ok(String::from_utf8(read_artifact(path)?)?)
}

pub const MATERIAL_IDS: [u8; 4] = [1, 2, 3, 4];
pub const PORT_IDS: [u8; 3] = [11, 12, 14];
const FR4_K: f64 = 1.44e-3;

/// Shape of the exposed bridge pad.  `VerticalObround` is the native GBU
/// shape; its straight section is the pad length minus its width.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum PadShape {
    Rectangle,
    VerticalObround,
    Round,
}

fn is_false(v: &bool) -> bool {
    !*v
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MaterialParams {
    pub copper_sigma_s_m: f64,
    pub copper_alpha_per_k: f64,
    pub copper_k_w_mk: f64,
    pub fr4_k_w_mk: f64,
    pub solder_sigma_s_m: f64,
    pub solder_k_w_mk: f64,
    pub lead_sigma_s_m: f64,
    pub lead_k_w_mk: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct JointInput {
    pub pad_shape: PadShape,
    pub pad_width_m: f64,
    pub pad_length_m: f64,
    pub drill_diameter_m: f64,
    pub trace_width_m: f64,
    #[serde(default, skip_serializing_if = "is_false")]
    pub trace_on_back: bool,
    pub trace_length_m: f64,
    pub copper_thickness_m: f64,
    pub barrel_plating_m: f64,
    pub board_thickness_m: f64,
    pub substrate_half_width_m: f64,
    pub substrate_back_margin_m: f64,
    pub solder_width_m: f64,
    pub solder_length_m: f64,
    pub solder_thickness_m: f64,
    pub lead_width_m: f64,
    pub lead_length_m: f64,
    pub lead_top_z_m: f64,
    pub current_a: f64,
    pub package_temperature_k: f64,
    pub board_temperature_k: f64,
    pub initial_temperature_k: f64,
    pub materials: MaterialParams,
}

impl Default for JointInput {
    fn default() -> Self {
        Self {
            pad_shape: PadShape::Rectangle,
            pad_width_m: 0.004,
            pad_length_m: 0.0025,
            drill_diameter_m: 0.0013,
            trace_width_m: 0.0025,
            trace_on_back: false,
            trace_length_m: 0.0085,
            copper_thickness_m: 0.00007,
            barrel_plating_m: 25e-6,
            board_thickness_m: FR4_K,
            substrate_half_width_m: 0.003,
            substrate_back_margin_m: 0.003,
            solder_width_m: 0.004,
            solder_length_m: 0.0025,
            solder_thickness_m: 0.00015,
            lead_width_m: 0.0008,
            lead_length_m: 0.0006,
            lead_top_z_m: 0.0012,
            current_a: 15.0,
            package_temperature_k: 333.15,
            board_temperature_k: 353.15,
            initial_temperature_k: 343.15,
            materials: MaterialParams {
                copper_sigma_s_m: 55.0e6,
                copper_alpha_per_k: 0.00393,
                copper_k_w_mk: 350.0,
                fr4_k_w_mk: 0.25,
                solder_sigma_s_m: 4.5e6,
                solder_k_w_mk: 50.0,
                lead_sigma_s_m: 10.0e6,
                lead_k_w_mk: 100.0,
            },
        }
    }
}

impl JointInput {
    pub fn validate(&self) -> Result<()> {
        for (name, value) in [
            ("pad_width_m", self.pad_width_m),
            ("pad_length_m", self.pad_length_m),
            ("drill_diameter_m", self.drill_diameter_m),
            ("trace_width_m", self.trace_width_m),
            ("trace_length_m", self.trace_length_m),
            ("copper_thickness_m", self.copper_thickness_m),
            ("barrel_plating_m", self.barrel_plating_m),
            ("board_thickness_m", self.board_thickness_m),
            ("substrate_half_width_m", self.substrate_half_width_m),
            ("substrate_back_margin_m", self.substrate_back_margin_m),
            ("solder_width_m", self.solder_width_m),
            ("solder_length_m", self.solder_length_m),
            ("solder_thickness_m", self.solder_thickness_m),
            ("lead_width_m", self.lead_width_m),
            ("lead_length_m", self.lead_length_m),
            ("lead_top_z_m", self.lead_top_z_m),
            ("package_temperature_k", self.package_temperature_k),
            ("board_temperature_k", self.board_temperature_k),
            ("initial_temperature_k", self.initial_temperature_k),
        ] {
            ensure!(
                value.is_finite() && value > 0.0,
                "{name} must be finite and positive"
            );
        }
        ensure!(
            self.current_a.is_finite() && self.current_a >= 0.0,
            "current_a must be finite and nonnegative"
        );
        ensure!(
            self.drill_diameter_m < self.pad_width_m.min(self.pad_length_m),
            "drill must fit pad"
        );
        ensure!(
            self.trace_width_m <= 2.0 * self.substrate_half_width_m,
            "trace does not fit substrate"
        );
        ensure!(
            self.lead_width_m.hypot(self.lead_length_m) < self.drill_diameter_m,
            "rectangular lead corners do not fit finished bore"
        );
        ensure!(
            self.drill_diameter_m + 2.0 * self.barrel_plating_m
                < self.pad_width_m.min(self.pad_length_m),
            "plated barrel must fit pad"
        );
        ensure!(
            self.trace_length_m > self.pad_length_m / 2.0
                && self.substrate_half_width_m > self.pad_width_m / 2.0
                && self.substrate_back_margin_m > self.pad_length_m / 2.0
                && self.lead_top_z_m > self.copper_thickness_m + self.solder_thickness_m,
            "joint solids do not fit the declared domain"
        );
        ensure!(
            self.board_thickness_m > self.copper_thickness_m,
            "board/copper overlap"
        );
        ensure!(
            (self.solder_width_m - self.pad_width_m).abs() < 1e-12
                && (self.solder_length_m - self.pad_length_m).abs() < 1e-12,
            "solder footprint must follow pad until wetting is reviewed"
        );
        if self.pad_shape == PadShape::VerticalObround {
            ensure!(
                self.pad_length_m > self.pad_width_m,
                "obround length must exceed width; round pads need a separate model"
            );
        }
        if self.pad_shape == PadShape::Round {
            ensure!(
                (self.pad_length_m - self.pad_width_m).abs() < 1e-12,
                "round pad must be square"
            );
        }
        for (name, value) in [
            ("copper_sigma_s_m", self.materials.copper_sigma_s_m),
            ("copper_alpha_per_k", self.materials.copper_alpha_per_k),
            ("copper_k_w_mk", self.materials.copper_k_w_mk),
            ("fr4_k_w_mk", self.materials.fr4_k_w_mk),
            ("solder_sigma_s_m", self.materials.solder_sigma_s_m),
            ("solder_k_w_mk", self.materials.solder_k_w_mk),
            ("lead_sigma_s_m", self.materials.lead_sigma_s_m),
            ("lead_k_w_mk", self.materials.lead_k_w_mk),
        ] {
            ensure!(
                value.is_finite() && value > 0.0,
                "{name} must be finite and positive"
            );
        }
        ensure!(
            self.materials.copper_alpha_per_k < 1.0,
            "copper alpha is unreasonable"
        );
        Ok(())
    }
    pub fn canonical_physics_hash(&self) -> String {
        let mut h = Sha256::new();
        h.update(
            serde_json::to_vec(&self.materials)
                .expect("serializing material parameters cannot fail"),
        );
        h.update(self.current_a.to_bits().to_le_bytes());
        h.update(self.package_temperature_k.to_bits().to_le_bytes());
        h.update(self.board_temperature_k.to_bits().to_le_bytes());
        format!("{:x}", h.finalize())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MeshStats {
    pub nodes: usize,
    pub tetrahedra: usize,
    pub triangles: usize,
    pub material_volumes_m3: BTreeMap<u8, f64>,
    pub interface_triangles: BTreeMap<String, usize>,
    pub port_triangles: BTreeMap<u8, usize>,
    pub port_areas_m2: BTreeMap<u8, f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SolverMeasurement {
    pub max_temperature_k: f64,
    pub min_temperature_k: f64,
    pub joule_w: f64,
    pub flux_w: [f64; 3],
    pub input_iv_w: f64,
    pub converged: bool,
}

fn f(v: f64) -> String {
    format!("{v:.12}")
}

/// Emit the reviewed conforming four-solid geometry.  Gmsh's BooleanFragments
/// keeps physical volume IDs 1=Cu, 2=FR4, 3=solder and 4=lead.
pub fn generate_geometry(input: &JointInput, mesh_size_m: f64) -> Result<String> {
    input.validate()?;
    ensure!(
        mesh_size_m.is_finite() && (0.00001..=0.001).contains(&mesh_size_m),
        "invalid mesh size"
    );
    let source = match input.pad_shape {
        PadShape::Rectangle => include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../thermal/physical-model/joint-fem/reference-rect/joint.geo"
        )),
        PadShape::VerticalObround => include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../thermal/physical-model/joint-fem/reference-oval/joint.geo"
        )),
        PadShape::Round => include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../thermal/physical-model/joint-fem/reference-round/joint.geo"
        )),
    };
    let mut text = String::new();
    for line in source.lines() {
        let replacement = if line.starts_with("w=") {
            format!(
                "w={}; L={}; tc={}; h={};",
                f(input.trace_width_m),
                f(input.trace_length_m),
                f(input.copper_thickness_m),
                f(input.board_thickness_m)
            )
        } else if line.starts_with("ri=") {
            format!(
                "ri={}; ro=ri+{}; lw={}; lt={};",
                f(input.drill_diameter_m / 2.0),
                f(input.barrel_plating_m),
                f(input.lead_width_m),
                f(input.lead_length_m)
            )
        } else if line.starts_with("pw=") {
            format!(
                "pw={}; pl={}; st={}; top={};",
                f(input.pad_width_m),
                f(input.pad_length_m),
                f(input.solder_thickness_m),
                f(input.lead_top_z_m)
            )
        } else if line.starts_with("Mesh.CharacteristicLengthMax") {
            format!("Mesh.CharacteristicLengthMax = {};", f(mesh_size_m))
        } else if line.starts_with("Mesh.CharacteristicLengthMin") {
            format!(
                "Mesh.CharacteristicLengthMin = {};",
                f(mesh_size_m.min(0.0001))
            )
        } else if line.starts_with("Box(1)=") {
            let z = if input.trace_on_back { "-h-tc" } else { "0" };
            format!("Box(1)={{-w/2,0,{z},w,L,tc}};")
        } else if line.starts_with("farCu()=") {
            if input.trace_on_back {
                format!(
                    "farCu()=Surface In BoundingBox {{-{bw}-e,L-e,-h-tc-e,{bw}+e,L+e,-h+e}};",
                    bw = f(input.substrate_half_width_m)
                )
            } else {
                line.into()
            }
        } else if line.starts_with("Box(10)=") {
            format!(
                "Box(10)={{-{bw},-{back},-h,{width},L+{back},h}};",
                bw = f(input.substrate_half_width_m),
                back = f(input.substrate_back_margin_m),
                width = f(2.0 * input.substrate_half_width_m)
            )
        } else if line.starts_with("farBoard()=") {
            format!(
                "farBoard()=Surface In BoundingBox {{-{bw}-e,L-e,-h-e,{bw}+e,L+e,e}};",
                bw = f(input.substrate_half_width_m)
            )
        } else {
            line.into()
        };
        text.push_str(&replacement);
        text.push('\n');
    }

    Ok(text)
}

/// Emit the coupled StatCurrent + Heat Equation deck.  The current source is
/// applied once on lead port 11; heat is generated by the electrical solve.
pub fn generate_sif(input: &JointInput, mesh: &MeshStats) -> Result<String> {
    input.validate()?;
    let area = *mesh
        .port_areas_m2
        .get(&11)
        .context("lead port 11 area missing")?;
    ensure!(area > 0.0, "lead port area is empty");
    let jd = input.current_a / area;
    Ok(format!(
        r#"Header
 CHECK KEYWORDS Warn
 Mesh DB "." "mesh"
End
Simulation
 Coordinate System = Cartesian 3D
 Simulation Type = Steady State
 Steady State Max Iterations = 30
 Output File = result.dat
End
Initial Condition 1
 Temperature = {init:.12}
End
Body 1
 Target Bodies(1) = 1
 Equation = 1
 Material = 1
 Body Force = 1
 Initial Condition = 1
End
Body 2
 Target Bodies(1) = 2
 Equation = 2
 Material = 2
 Initial Condition = 1
End
Body 3
 Target Bodies(1) = 3
 Equation = 1
 Material = 3
 Body Force = 1
 Initial Condition = 1
End
Body 4
 Target Bodies(1) = 4
 Equation = 1
 Material = 4
 Body Force = 1
 Initial Condition = 1
End
Equation 1
 Active Solvers(2) = 1 2
End
Equation 2
 Active Solvers(1) = 2
End
Solver 1
 Equation = Stat Current
 Procedure = "StatCurrentSolve" "StatCurrentSolver"
 Variable = Potential
 Variable DOFs = 1
 Calculate Volume Current = True
 Calculate Joule Heating = True
 Linear System Solver = Direct
 Linear System Direct Method = umfpack
 Nonlinear System Max Iterations = 1
 Steady State Convergence Tolerance = 1e-8
End
Solver 2
 Equation = Heat Equation
 Procedure = "HeatSolve" "HeatSolver"
 Variable = Temperature
 Linear System Solver = Direct
 Linear System Direct Method = umfpack
 Nonlinear System Max Iterations = 1
 Steady State Convergence Tolerance = 1e-8
 Calculate Loads = True
 Calculate Boundary Fluxes = True
End
Solver 3
 Exec Solver = After All
 Equation = SaveScalars
 Procedure = "SaveData" "SaveScalars"
 Variable 1 = Temperature
 Operator 1 = max
 Variable 2 = Temperature
 Operator 2 = min
 Variable 3 = Potential
 Operator 3 = boundary int
 Variable 4 = Potential
 Operator 4 = area
 Filename = scalars.dat
End
Material 1
 Electric Conductivity = Variable Temperature
  Real MATC "{sigma:.12}/(1+{alpha:.12}*(tx-293.15))"
 Heat Conductivity = {cuk:.12}
 Density = 8960
 Heat Capacity = 385
End
Material 2
 Heat Conductivity = {fr4k:.12}
 Density = 1900
 Heat Capacity = 1000
End
Material 3
 Electric Conductivity = {ss:.12}
 Heat Conductivity = {sk:.12}
 Density = 7400
 Heat Capacity = 230
End
Material 4
 Electric Conductivity = {ls:.12}
 Heat Conductivity = {lk:.12}
 Density = 8900
 Heat Capacity = 385
End
Body Force 1
 Joule Heat = True
End
Boundary Condition 1
 Target Boundaries(1) = 11
 Current Density BC = True
 Current Density = {jd:.12}
 Temperature = {pkg:.12}
 Save Scalars = True
End
Boundary Condition 2
 Target Boundaries(1) = 12
 Temperature = {board:.12}
 Save Scalars = True
End
Boundary Condition 3
 Target Boundaries(1) = 14
 Potential = 0
 Temperature = {board:.12}
 Save Scalars = True
End
"#,
        init = input.initial_temperature_k,
        sigma = input.materials.copper_sigma_s_m,
        alpha = input.materials.copper_alpha_per_k,
        cuk = input.materials.copper_k_w_mk,
        fr4k = input.materials.fr4_k_w_mk,
        ss = input.materials.solder_sigma_s_m,
        sk = input.materials.solder_k_w_mk,
        ls = input.materials.lead_sigma_s_m,
        lk = input.materials.lead_k_w_mk,
        jd = jd,
        pkg = input.package_temperature_k,
        board = input.board_temperature_k
    ))
}

pub fn parse_msh2(mesh: &str, input: &JointInput) -> Result<MeshStats> {
    crate::joint_mesh::parse(mesh, input)
}
pub fn validate_outputs(
    log: &str,
    scalars: &str,
    names: &str,
    input: &JointInput,
    mesh: &MeshStats,
) -> Result<SolverMeasurement> {
    crate::joint_physics::validate(log, scalars, names, input, mesh)
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunReport {
    pub status: String,
    pub input: JointInput,
    pub input_hash: String,
    pub physics_hash: String,
    pub cases: Vec<CaseReport>,
    pub artifacts: BTreeMap<String, String>,
    pub tool_versions: BTreeMap<String, String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaseReport {
    pub mesh_size_m: f64,
    pub mesh: MeshStats,
    pub measurement: SolverMeasurement,
}
#[derive(Debug, Clone)]
pub struct RunConfig {
    pub input: JointInput,
    pub output_dir: PathBuf,
    pub gmsh: PathBuf,
    pub elmergrid: PathBuf,
    pub elmersolver: PathBuf,
    pub timeout: Duration,
}

fn hash_bytes(v: &[u8]) -> String {
    format!("{:x}", Sha256::digest(v))
}
fn run_cmd(program: &Path, args: &[&str], cwd: &Path, timeout: Duration, name: &str) -> Result<()> {
    crate::run_process(
        program,
        args,
        cwd,
        &cwd.join(format!("{name}.log")),
        timeout,
    )?;
    Ok(())
}

pub fn run(config: &RunConfig) -> Result<RunReport> {
    run_with_meshes(config, &[0.0006, 0.0003, 0.00015])
}

fn evidence_hashes(root: &Path, count: usize) -> Result<BTreeMap<String, String>> {
    let mut paths = vec!["input.json".to_string(), "backend.json".to_string()];
    for i in 0..count {
        for name in [
            "joint.geo",
            "joint.msh",
            "case.sif",
            "scalars.dat",
            "scalars.dat.names",
            "gmsh.log",
            "grid.log",
            "elmersolver.log",
            "gmsh.command.json",
            "grid.command.json",
            "elmersolver.command.json",
            "mesh/mesh.nodes",
            "mesh/mesh.elements",
            "mesh/mesh.boundary",
            "mesh/mesh.header",
        ] {
            paths.push(format!("mesh-{i}/{name}"));
        }
    }
    paths
        .into_iter()
        .map(|p| Ok((p.clone(), hash_bytes(&read_artifact(root.join(p))?))))
        .collect()
}

fn validate_cases(cases: &[CaseReport]) -> Result<&'static str> {
    ensure!(
        [1, 3].contains(&cases.len()),
        "one or three mesh levels required"
    );
    if cases.len() == 1 {
        return Ok("numerical_only");
    }
    ensure!(
        cases
            .iter()
            .map(|c| c.mesh_size_m)
            .eq([0.0006, 0.0003, 0.00015]),
        "three distinct reviewed resolutions required"
    );
    for (n, pair) in cases.windows(2).enumerate() {
        ensure!(
            pair[1].mesh.nodes > pair[0].mesh.nodes,
            "mesh refinement did not add nodes"
        );
        ensure!(
            (pair[1].measurement.max_temperature_k - pair[0].measurement.max_temperature_k).abs()
                <= if n == 0 { 1.0 } else { 0.5 },
            "local temperature did not converge under refinement"
        );
        let a = pair[0].measurement.joule_w;
        let b = pair[1].measurement.joule_w;
        ensure!(
            (a - b).abs() <= 1e-9 + 0.02 * b.abs(),
            "electrical loss did not converge under refinement"
        );
    }
    Ok("numerical_mesh_converged")
}

fn run_with_meshes(config: &RunConfig, meshes: &[f64]) -> Result<RunReport> {
    config.input.validate()?;
    ensure!(
        config.output_dir.is_absolute(),
        "output directory must be absolute"
    );
    ensure!(
        !config.output_dir.exists(),
        "refusing existing output directory"
    );
    fs::create_dir_all(&config.output_dir)?;
    let mut backend = BTreeMap::new();
    for (name, path) in [
        ("gmsh", &config.gmsh),
        ("grid", &config.elmergrid),
        ("solver", &config.elmersolver),
    ] {
        backend.insert(
            format!("{name}_executable_sha256"),
            crate::sha256_file(path)?,
        );
    }
    fs::write(
        config.output_dir.join("backend.json"),
        serde_json::to_vec_pretty(&backend)?,
    )?;
    let input_bytes = serde_json::to_vec_pretty(&config.input)?;
    fs::write(config.output_dir.join("input.json"), &input_bytes)?;
    let mut cases = Vec::new();
    for (idx, ms) in meshes.iter().copied().enumerate() {
        let d = config.output_dir.join(format!("mesh-{idx}"));
        fs::create_dir(&d)?;
        let geo = generate_geometry(&config.input, ms)?;
        fs::write(d.join("joint.geo"), &geo)?;
        run_cmd(
            &config.gmsh,
            &[
                "joint.geo",
                "-3",
                "-format",
                "msh2",
                "-o",
                "joint.msh",
                "-nt",
                "1",
            ],
            &d,
            config.timeout,
            "gmsh",
        )?;
        run_cmd(
            &config.elmergrid,
            &["14", "2", "joint.msh", "-out", "mesh"],
            &d,
            config.timeout,
            "grid",
        )?;
        let msh = read_text(d.join("joint.msh"))?;
        let mesh = parse_msh2(&msh, &config.input)?;
        let sif = generate_sif(&config.input, &mesh)?;
        fs::write(d.join("case.sif"), &sif)?;
        run_cmd(
            &config.elmersolver,
            &["case.sif"],
            &d,
            config.timeout,
            "elmersolver",
        )?;
        let log = read_text(d.join("elmersolver.log"))?;
        let scalars = read_text(d.join("scalars.dat"))?;
        let names = read_text(d.join("scalars.dat.names"))?;
        let measurement = validate_outputs(&log, &scalars, &names, &config.input, &mesh)?;
        cases.push(CaseReport {
            mesh_size_m: ms,
            mesh,
            measurement,
        });
    }
    let artifacts = evidence_hashes(&config.output_dir, cases.len())?;
    let mut versions = BTreeMap::new();
    for (name, marker) in [
        ("gmsh", "[Gmsh"),
        ("grid", "Version:"),
        ("elmersolver", "MAIN: Version:"),
    ] {
        let log = read_text(config.output_dir.join(format!("mesh-0/{name}.log")))?;
        versions.insert(
            name.into(),
            log.lines()
                .find(|s| s.contains(marker))
                .context("missing runtime version")?
                .into(),
        );
    }
    let report = RunReport {
        status: validate_cases(&cases)?.into(),
        input: config.input.clone(),
        input_hash: hash_bytes(&input_bytes),
        physics_hash: config.input.canonical_physics_hash(),
        cases,
        artifacts,
        tool_versions: versions,
    };
    fs::write(
        config.output_dir.join("report.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(report)
}

/// Replay retained raw mesh/log/scalars.  Inputs and generated SIF/geometry
/// are regenerated, and source physics is checked against the immutable
/// reviewed contract hash before any producer-controlled hash is trusted.
pub fn replay(root: &Path) -> Result<RunReport> {
    let report: RunReport = serde_json::from_slice(&read_artifact(root.join("report.json"))?)?;
    report.input.validate()?;
    ensure!(
        report.status == validate_cases(&report.cases)?,
        "incorrect numerical scope/status"
    );
    ensure!(
        report.artifacts == evidence_hashes(root, report.cases.len())?,
        "retained raw evidence hash changed"
    );
    for (name, marker) in [
        ("gmsh", "[Gmsh"),
        ("grid", "Version:"),
        ("elmersolver", "MAIN: Version:"),
    ] {
        let log = read_text(root.join(format!("mesh-0/{name}.log")))?;
        ensure!(
            report.tool_versions.get(name).map(String::as_str)
                == log.lines().find(|s| s.contains(marker)),
            "runtime version record differs from raw log"
        );
    }
    ensure!(
        report.input.canonical_physics_hash() == report.physics_hash,
        "source physics changed"
    );
    let input_bytes = serde_json::to_vec_pretty(&report.input)?;
    ensure!(
        read_artifact(root.join("input.json"))? == input_bytes,
        "retained input differs from report"
    );
    ensure!(
        hash_bytes(&input_bytes) == report.input_hash,
        "input hash mismatch"
    );
    ensure!(
        [1usize, 3usize].contains(&report.cases.len()),
        "one or three mesh levels required"
    );
    for (idx, c) in report.cases.iter().enumerate() {
        let d = root.join(format!("mesh-{idx}"));
        let mesh = read_text(d.join("joint.msh"))?;
        let stats = parse_msh2(&mesh, &report.input)?;
        ensure!(stats == c.mesh, "mesh census changed");
        let geo = generate_geometry(&report.input, c.mesh_size_m)?;
        ensure!(
            read_artifact(d.join("joint.geo"))? == geo.as_bytes(),
            "geometry changed"
        );
        let sif = generate_sif(&report.input, &stats)?;
        ensure!(
            read_artifact(d.join("case.sif"))? == sif.as_bytes(),
            "solver physics changed"
        );
        let m = validate_outputs(
            &read_text(d.join("elmersolver.log"))?,
            &read_text(d.join("scalars.dat"))?,
            &read_text(d.join("scalars.dat.names"))?,
            &report.input,
            &stats,
        )?;
        ensure!(m == c.measurement, "solver scalars changed");
    }
    Ok(report)
}

/// Execute the FEM for one selected resolution.  The report is marked
/// `numerical_only` because a single mesh cannot establish convergence.
/// Callers evaluating a coupled package should invoke this once per level and
/// compare the returned raw measurements themselves.
pub fn run_at_mesh(config: &RunConfig, mesh_size_m: f64) -> Result<RunReport> {
    ensure!(
        mesh_size_m.is_finite() && mesh_size_m > 0.0,
        "invalid mesh size"
    );
    run_with_meshes(config, &[mesh_size_m])
}
