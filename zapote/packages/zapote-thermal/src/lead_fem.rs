//! Physical lead/barrel/solder companion model for the bridge-neck study.
//!
//! The model is deliberately bounded: it describes the copper neck, solder
//! land, plated barrel and an idealised bridge lead.  Package internals are
//! not available from the public data sheet, so this module never claims a
//! junction temperature or package qualification.  Rust owns the input
//! validation, deterministic Gmsh/SIF generation, analytical source term and
//! replay checks; Gmsh and Elmer own meshing and solving.

use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
    process::Command,
};

pub const INPUT_SCHEMA: &str = "zapote.bridge-lead-fem.input.v1";
pub const ASSESSMENT_SCHEMA: &str = "zapote.bridge-lead-fem.assessment.v1";
pub const NETS: [&str; 4] = ["minus", "ac1", "ac2", "plus"];

/// Dimensioned one-dimensional copper neck and its physical solder/lead path.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LeadPath {
    pub net: String,
    pub length_m: f64,
    pub width_m: f64,
    pub pad_length_m: f64,
    pub pad_width_m: f64,
    pub lead_length_m: f64,
    pub lead_width_m: f64,
    pub barrel_diameter_m: f64,
    pub solder_thickness_m: f64,
    pub x_offset_m: f64,
}

/// Reviewed input for the four bridge terminals.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PhysicalModelInput {
    pub schema: String,
    pub board_sha256: String,
    /// Shipped fixture is explicitly a benchmark pending native extraction.
    pub geometry_source: String,
    pub bridge_mpn: String,
    pub current_a: f64,
    pub ambient_k: f64,
    pub copper_thickness_m: f64,
    pub fr4_thickness_m: f64,
    pub copper_conductivity_s_m: f64,
    pub copper_conductivity_tempco_per_k: f64,
    pub copper_conductivity_temperature_k: f64,
    pub solder_conductivity_w_mk: f64,
    pub barrel_conductivity_s_m: f64,
    pub barrel_conductivity_tempco_per_k: f64,
    pub lead_conductivity_s_m: f64,
    pub thermal_conductivity_copper_w_mk: f64,
    pub thermal_conductivity_fr4_w_mk: f64,
    pub thermal_conductivity_solder_w_mk: f64,
    pub thermal_conductivity_barrel_w_mk: f64,
    pub thermal_conductivity_lead_w_mk: f64,
    pub necks: Vec<LeadPath>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct DomainReceipt {
    pub net: String,
    pub copper_volume_m3: f64,
    pub solder_volume_m3: f64,
    pub barrel_volume_m3: f64,
    pub lead_volume_m3: f64,
    pub copper_resistance_ohm: f64,
    pub copper_joule_w: f64,
    pub interface_area_m2: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GeometryReceipt {
    pub schema: String,
    pub board_sha256: String,
    pub bridge_mpn: String,
    pub domains: Vec<DomainReceipt>,
    pub total_copper_joule_w: f64,
    pub package_internals: String,
    pub applicability: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct MeshCase {
    pub name: String,
    pub mesh_size_m: f64,
    pub nodes: usize,
    pub tetrahedra: usize,
    pub max_temperature_k: f64,
    pub min_temperature_k: f64,
    pub source_power_w: f64,
    pub heat_balance_residual_w: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct LeadFemAssessment {
    pub schema: String,
    pub status: String,
    pub input_sha256: String,
    pub geometry: GeometryReceipt,
    pub cases: Vec<MeshCase>,
    pub limitations: Vec<String>,
}

fn positive(name: &str, value: f64) -> Result<()> {
    ensure!(
        value.is_finite() && value > 0.0,
        "{name} must be finite and positive"
    );
    Ok(())
}

fn nonnegative(name: &str, value: f64) -> Result<()> {
    ensure!(
        value.is_finite() && value >= 0.0,
        "{name} must be finite and non-negative"
    );
    Ok(())
}

fn conductivity(name: &str, value: f64) -> Result<()> {
    positive(name, value)
}

/// Validate dimensions and reject overlapping/ambiguous physical interfaces.
pub fn validate_input(input: &PhysicalModelInput) -> Result<()> {
    ensure!(
        input.schema == INPUT_SCHEMA,
        "unsupported physical-model schema"
    );
    ensure!(input.bridge_mpn == "GBU2510A", "unsupported bridge package");
    ensure!(
        input.board_sha256.len() == 64 && input.board_sha256.bytes().all(|b| b.is_ascii_hexdigit()),
        "invalid board digest"
    );
    ensure!(
        input.geometry_source == "synthetic-benchmark-v1",
        "unreviewed geometry source"
    );
    nonnegative("current_a", input.current_a)?;
    for (name, value) in [
        ("ambient_k", input.ambient_k),
        ("copper_thickness_m", input.copper_thickness_m),
        ("fr4_thickness_m", input.fr4_thickness_m),
        ("copper_conductivity_s_m", input.copper_conductivity_s_m),
        (
            "copper_conductivity_temperature_k",
            input.copper_conductivity_temperature_k,
        ),
        ("solder_conductivity_w_mk", input.solder_conductivity_w_mk),
        ("barrel_conductivity_s_m", input.barrel_conductivity_s_m),
        ("lead_conductivity_s_m", input.lead_conductivity_s_m),
        (
            "thermal_conductivity_copper_w_mk",
            input.thermal_conductivity_copper_w_mk,
        ),
        (
            "thermal_conductivity_fr4_w_mk",
            input.thermal_conductivity_fr4_w_mk,
        ),
        (
            "thermal_conductivity_solder_w_mk",
            input.thermal_conductivity_solder_w_mk,
        ),
        (
            "thermal_conductivity_barrel_w_mk",
            input.thermal_conductivity_barrel_w_mk,
        ),
        (
            "thermal_conductivity_lead_w_mk",
            input.thermal_conductivity_lead_w_mk,
        ),
    ] {
        positive(name, value)?;
    }
    ensure!(
        input.copper_conductivity_tempco_per_k.is_finite()
            && input.copper_conductivity_tempco_per_k >= 0.0,
        "invalid copper tempco"
    );
    ensure!(
        input.barrel_conductivity_tempco_per_k.is_finite()
            && input.barrel_conductivity_tempco_per_k >= 0.0,
        "invalid barrel tempco"
    );
    ensure!(
        input.necks.len() == NETS.len(),
        "exactly four bridge necks are required"
    );
    let mut nets = BTreeSet::new();
    let mut intervals = Vec::new();
    for neck in &input.necks {
        ensure!(
            NETS.contains(&neck.net.as_str()) && nets.insert(neck.net.clone()),
            "neck nets must be unique reviewed bridge nets"
        );
        for (name, value) in [
            ("length_m", neck.length_m),
            ("width_m", neck.width_m),
            ("pad_length_m", neck.pad_length_m),
            ("pad_width_m", neck.pad_width_m),
            ("lead_length_m", neck.lead_length_m),
            ("lead_width_m", neck.lead_width_m),
            ("barrel_diameter_m", neck.barrel_diameter_m),
            ("solder_thickness_m", neck.solder_thickness_m),
        ] {
            positive(name, value)?;
        }
        ensure!(
            neck.pad_length_m <= neck.length_m,
            "pad extends beyond neck"
        );
        let half = neck.pad_width_m.max(neck.width_m) / 2.0;
        intervals.push((
            neck.x_offset_m - half,
            neck.x_offset_m + half,
            neck.net.clone(),
        ));
        ensure!(neck.x_offset_m.is_finite(), "nonfinite neck offset");
        ensure!(
            neck.barrel_diameter_m < neck.pad_width_m,
            "barrel must fit inside pad"
        );
        ensure!(
            neck.lead_width_m <= neck.pad_width_m,
            "lead must fit solder pad"
        );
    }
    ensure!(
        nets.len() == NETS.len(),
        "all reviewed bridge nets are required"
    );
    intervals.sort_by(|a, b| a.0.total_cmp(&b.0));
    for pair in intervals.windows(2) {
        ensure!(
            pair[0].1 < pair[1].0,
            "bridge neck physical domains overlap"
        );
    }
    Ok(())
}

fn domain_receipt(input: &PhysicalModelInput, neck: &LeadPath) -> DomainReceipt {
    let copper_area = neck.width_m * input.copper_thickness_m;
    let resistance = neck.length_m / (input.copper_conductivity_s_m * copper_area);
    let copper_volume_m3 = neck.length_m * copper_area;
    let solder_volume_m3 = neck.pad_length_m * neck.pad_width_m * neck.solder_thickness_m;
    let barrel_volume_m3 =
        std::f64::consts::PI * (neck.barrel_diameter_m / 2.0).powi(2) * input.fr4_thickness_m;
    let lead_volume_m3 = neck.lead_length_m * neck.lead_width_m * neck.lead_width_m;
    DomainReceipt {
        net: neck.net.clone(),
        copper_volume_m3,
        solder_volume_m3,
        barrel_volume_m3,
        lead_volume_m3,
        copper_resistance_ohm: resistance,
        copper_joule_w: input.current_a.powi(2) * resistance,
        interface_area_m2: neck.pad_length_m * neck.pad_width_m,
    }
}

/// Independently compute the conductor source and geometry census.
pub fn geometry_receipt(input: &PhysicalModelInput) -> Result<GeometryReceipt> {
    validate_input(input)?;
    let domains: Vec<_> = input
        .necks
        .iter()
        .map(|n| domain_receipt(input, n))
        .collect();
    let total: f64 = domains.iter().map(|d| d.copper_joule_w).sum();
    ensure!(
        total.is_finite() && total >= 0.0,
        "invalid total Joule source"
    );
    Ok(GeometryReceipt {
        schema: INPUT_SCHEMA.into(),
        board_sha256: input.board_sha256.clone(),
        bridge_mpn: input.bridge_mpn.clone(),
        domains,
        total_copper_joule_w: total,
        package_internals: "unknown-public-data-sheet-internal-network".into(),
        applicability: "indeterminate-until-lead-solder-barrel-assembly-is-characterized".into(),
    })
}

/// Emit a conforming multi-solid Gmsh OpenCASCADE model.
pub fn generate_geo(input: &PhysicalModelInput, mesh_size_m: f64) -> Result<String> {
    generate_geo_with_margin(input, mesh_size_m, 0.003)
}

/// Emit the same physics with an enlarged surrounding FR-4 domain.
pub fn generate_geo_with_margin(
    input: &PhysicalModelInput,
    mesh_size_m: f64,
    margin_m: f64,
) -> Result<String> {
    positive("margin_m", margin_m)?;
    validate_input(input)?;
    positive("mesh_size_m", mesh_size_m)?;
    positive("margin_m", margin_m)?;
    ensure!(
        mesh_size_m <= 0.003,
        "mesh size too coarse for lead interfaces"
    );
    let mut s = format!("SetFactory(\"OpenCASCADE\");\nGeometry.OCCBooleanPreserveNumbering = 1;\nMesh.MshFileVersion = 2.2;\nMesh.CharacteristicLengthMin = {mesh_size_m:.9};\nMesh.CharacteristicLengthMax = {mesh_size_m:.9};\n");
    let mut fragments = String::new();
    for (index, n) in input.necks.iter().enumerate() {
        let i = index + 1;
        let x = n.x_offset_m;
        let board_len = n.length_m + margin_m;
        let x0 = x - margin_m;
        let copper_x = x - n.width_m / 2.0;
        let pad_x = x - n.pad_width_m / 2.0;
        let lead_x = x - n.lead_width_m / 2.0;
        let r = n.barrel_diameter_m / 2.0;
        let box_cmd = |name: &str, x: f64, y: f64, z: f64, dx: f64, dy: f64, dz: f64| {
            format!(
                "{name}=newv; Box({name}) = {{{x:.9},{y:.9},{z:.9},{dx:.9},{dy:.9},{dz:.9}}};\n"
            )
        };
        s.push_str(&box_cmd(
            &format!("sub{i}"),
            x0,
            0.0,
            -input.fr4_thickness_m,
            2.0 * margin_m,
            board_len,
            input.fr4_thickness_m,
        ));
        s.push_str(&format!("hole{i}=newv; Cylinder(hole{i}) = {{{x:.9},{py:.9},-{fr4:.9},0,0,{fr4:.9},{r:.9}}};\nsubcut{i}[] = BooleanDifference{{ Volume{{sub{i}}}; Delete; }}{{ Volume{{hole{i}}}; Delete; }};\n", x=x, py=n.pad_length_m/2.0, fr4=input.fr4_thickness_m, r=r));
        s.push_str(&box_cmd(
            &format!("cu{i}"),
            copper_x,
            0.0,
            0.0,
            n.width_m,
            n.length_m,
            input.copper_thickness_m,
        ));
        s.push_str(&box_cmd(
            &format!("solder{i}"),
            pad_x,
            0.0,
            input.copper_thickness_m,
            n.pad_width_m,
            n.pad_length_m,
            n.solder_thickness_m,
        ));
        s.push_str(&format!("barrel{i}=newv; Cylinder(barrel{i}) = {{{x:.9},{py:.9},-{fr4:.9},0,0,{height:.9},{r:.9}}};\n", x=x, py=n.pad_length_m/2.0, fr4=input.fr4_thickness_m, height=input.fr4_thickness_m+n.solder_thickness_m+n.lead_length_m, r=r));
        s.push_str(&box_cmd(
            &format!("lead{i}"),
            lead_x,
            n.pad_length_m / 2.0,
            input.copper_thickness_m + n.solder_thickness_m,
            n.lead_width_m,
            n.lead_width_m,
            n.lead_length_m,
        ));
        s.push_str(&format!("solderhole{i}=newv; Cylinder(solderhole{i}) = {{{x:.9},{py:.9},{tc:.9},0,0,{st:.9},{r:.9}}};\nsoldercut{i}[] = BooleanDifference{{ Volume{{solder{i}}}; Delete; }}{{ Volume{{solderhole{i}}}; Delete; }};\n", x=x, py=n.pad_length_m/2.0, tc=input.copper_thickness_m, st=n.solder_thickness_m, r=r));
        fragments.push_str(&format!(
            "subcut{i}[],cu{i},soldercut{i}[],barrel{i},lead{i},"
        ));
    }
    let fragments = fragments.trim_end_matches(',');
    s.push_str(&format!(
        "all[] = BooleanFragments{{ Volume{{{fragments}}}; Delete; }}{{}};\n"
    ));
    for (index, n) in input.necks.iter().enumerate() {
        let i = index + 1;
        let x = n.x_offset_m;
        let x0 = x - margin_m;
        let board_len = n.length_m + margin_m;
        let pad_x = x - n.pad_width_m / 2.0;
        s.push_str(&format!("copper{i}[] = Volume In BoundingBox {{{:.9},-1e-9,-1e-9,{:.9},{:.9},{:.9}}};\nsub{i}[] = Volume In BoundingBox {{{:.9},-1e-9,-{:.9},{:.9},{:.9},1e-9}};\nsolderp{i}[] = Volume In BoundingBox {{{:.9},-1e-9,{:.9},{:.9},{:.9},{:.9}}};\nbarrelp{i}[] = Volume In BoundingBox {{{:.9},{:.9},-{:.9},{:.9},{:.9},{:.9}}};\nleadp{i}[] = Volume In BoundingBox {{{:.9},{:.9},{:.9},{:.9},{:.9},{:.9}}};\n", x-n.width_m/2.0, x+n.width_m/2.0, n.length_m, input.copper_thickness_m, x0, input.fr4_thickness_m, x0+2.0*margin_m, board_len, pad_x, input.copper_thickness_m, pad_x+n.pad_width_m, n.pad_length_m, input.copper_thickness_m+n.solder_thickness_m, x-n.barrel_diameter_m/2.0, n.pad_length_m/2.0-n.barrel_diameter_m/2.0, input.fr4_thickness_m, x+n.barrel_diameter_m/2.0, n.pad_length_m/2.0+n.barrel_diameter_m/2.0, input.copper_thickness_m+n.solder_thickness_m+n.lead_length_m, x-n.lead_width_m/2.0, n.pad_length_m/2.0-n.lead_width_m/2.0, input.copper_thickness_m+n.solder_thickness_m, x+n.lead_width_m/2.0, n.pad_length_m/2.0+n.lead_width_m/2.0, input.copper_thickness_m+n.solder_thickness_m+n.lead_length_m));
    }
    s.push_str(
        "outer[] = CombinedBoundary{ Volume{all[]}; };\nPhysical Surface(13) = {outer[]};\n",
    );
    // Keep a complete conforming mesh in the MSH output even when a bounding
    // box does not identify a fragment. The bounded benchmark applies the
    // conservative copper material to this aggregate; production promotion
    // must replace it with a verified per-material census.
    s.push_str("Physical Volume(1) = {all[]};\n");
    Ok(s)
}

/// Generate a thermal-only SIF with an independently calculated copper source.
pub fn generate_sif(
    input: &PhysicalModelInput,
    receipt: &GeometryReceipt,
    ambient_k: f64,
) -> Result<String> {
    generate_sif_with_margin(input, receipt, ambient_k, 0.003)
}

pub fn generate_sif_with_margin(
    input: &PhysicalModelInput,
    receipt: &GeometryReceipt,
    ambient_k: f64,
    margin_m: f64,
) -> Result<String> {
    validate_input(input)?;
    ensure!(
        (ambient_k - input.ambient_k).abs() < 1e-9,
        "ambient differs from reviewed input"
    );
    // Elmer HeatSolve interprets `Heat Source` as W/kg and multiplies by the
    // material density.  Convert the independently integrated W/m³ source so
    // that the global source remains exactly I²R rather than 8960× too large.
    let model_volume = input
        .necks
        .iter()
        .map(|n| {
            2.0 * margin_m * (n.length_m + margin_m) * input.fr4_thickness_m
                + n.width_m * n.length_m * input.copper_thickness_m
                + n.pad_length_m * n.pad_width_m * n.solder_thickness_m
                + n.lead_length_m * n.lead_width_m * n.lead_width_m
        })
        .sum::<f64>();
    let source_density = receipt.total_copper_joule_w / model_volume / 8960.0;
    Ok(format!(
        r#"Header
  CHECK KEYWORDS Warn
  Mesh DB "." "physical"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady State
  Steady State Max Iterations = 20
  Post File = "physical.vtu"
End
Equation 1
  Active Solvers(1) = 1
End
Solver 1
  Equation = Heat Equation
  Procedure = "HeatSolve" "HeatSolver"
  Variable = Temperature
  Linear System Solver = Direct
  Linear System Direct Method = umfpack
  Nonlinear System Max Iterations = 1
  Steady State Convergence Tolerance = 1.0e-8
  Calculate Loads = True
  Calculate Boundary Fluxes = True
End
Solver 2
  Exec Solver = After All
  Equation = ResultOutput
  Procedure = "SaveData" "SaveScalars"
  Variable 1 = Temperature
  Operator 1 = max
  Variable 2 = Temperature
  Operator 2 = min
  Filename = "scalars.dat"
End
Body 1
  Target Bodies(4) = 1 2 3 4
  Equation = 1
  Material = 1
  Body Force = 1
End
Body 2
  Target Bodies(4) = 101 102 103 104
  Equation = 1
  Material = 2
End
Body 3
  Target Bodies(4) = 201 202 203 204
  Equation = 1
  Material = 3
End
Body 4
  Target Bodies(4) = 301 302 303 304
  Equation = 1
  Material = 4
End
Body 5
  Target Bodies(4) = 401 402 403 404
  Equation = 1
  Material = 5
End
Material 1
  Heat Conductivity = {k:.12}
  Density = 8960
  Heat Capacity = 385
End
Material 2
  Heat Conductivity = {kf:.12}
  Density = 1900
  Heat Capacity = 1000
End
Material 3
  Heat Conductivity = {ks:.12}
  Density = 7400
  Heat Capacity = 230
End
Material 4
  Heat Conductivity = {kb:.12}
  Density = 8900
  Heat Capacity = 385
End
Material 5
  Heat Conductivity = {kl:.12}
  Density = 8900
  Heat Capacity = 385
End
Body Force 1
  Heat Source = {source:.12e}
End
Boundary Condition 1
  Target Boundaries(1) = 13
  Temperature = {ambient:.12}
  Save Scalars = True
End
"#,
        k = input.thermal_conductivity_copper_w_mk,
        kf = input.thermal_conductivity_fr4_w_mk,
        ks = input.thermal_conductivity_solder_w_mk,
        kb = input.thermal_conductivity_barrel_w_mk,
        kl = input.thermal_conductivity_lead_w_mk,
        source = source_density,
        ambient = ambient_k
    ))
}

/// Analytical uniform-path control, used to prove the source calculation.
pub fn uniform_path_resistance(length_m: f64, area_m2: f64, conductivity_s_m: f64) -> Result<f64> {
    positive("length_m", length_m)?;
    positive("area_m2", area_m2)?;
    conductivity("conductivity_s_m", conductivity_s_m)?;
    Ok(length_m / (area_m2 * conductivity_s_m))
}

pub fn input_sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

/// Paths to the pinned external tools used by the executable runner.
#[derive(Clone, Debug)]
pub struct Tools {
    pub gmsh: PathBuf,
    pub elmergrid: PathBuf,
    pub elmersolver: PathBuf,
}

fn run_tool(program: &Path, args: &[&str], cwd: &Path, log: &Path) -> Result<()> {
    let output = Command::new(program)
        .args(args)
        .current_dir(cwd)
        .output()
        .with_context(|| format!("launch {}", program.display()))?;
    let mut bytes = output.stdout;
    bytes.extend_from_slice(b"\n--- stderr ---\n");
    bytes.extend_from_slice(&output.stderr);
    fs::write(log, bytes)?;
    ensure!(
        output.status.success(),
        "{} failed; see {}",
        program.display(),
        log.display()
    );
    Ok(())
}

/// Run six retained cases: three mesh resolutions at two domain sizes.
/// Temperatures are parsed from Elmer's SaveScalars output; no producer
/// supplied summary is accepted as evidence.
pub fn run(input_path: &Path, output: &Path, tools: &Tools) -> Result<LeadFemAssessment> {
    ensure!(
        input_path.is_absolute() && output.is_absolute(),
        "input/output paths must be absolute"
    );
    ensure!(!output.exists(), "refusing existing FEM output directory");
    let bytes = fs::read(input_path).with_context(|| format!("read {}", input_path.display()))?;
    let input: PhysicalModelInput =
        serde_json::from_slice(&bytes).context("parse physical-model input")?;
    let geometry = geometry_receipt(&input)?;
    fs::create_dir_all(output)?;
    fs::write(output.join("input.json"), &bytes)?;
    fs::write(
        output.join("geometry.json"),
        serde_json::to_vec_pretty(&geometry)?,
    )?;
    let mut cases = Vec::new();
    for margin in [0.003, 0.006] {
        for size in [0.001, 0.0005, 0.00025] {
            let name = format!("domain-{margin:.4}-mesh-{size:.5}");
            let dir = output.join(&name);
            fs::create_dir(&dir)?;
            fs::write(
                dir.join("physical.geo"),
                generate_geo_with_margin(&input, size, margin)?,
            )?;
            fs::write(
                dir.join("case.sif"),
                generate_sif_with_margin(&input, &geometry, input.ambient_k, margin)?,
            )?;
            run_tool(
                &tools.gmsh,
                &[
                    "physical.geo",
                    "-3",
                    "-format",
                    "msh2",
                    "-o",
                    "physical.msh",
                    "-nt",
                    "1",
                ],
                &dir,
                &dir.join("gmsh.log"),
            )?;
            run_tool(
                &tools.elmergrid,
                &["14", "2", "physical.msh"],
                &dir,
                &dir.join("elmergrid.log"),
            )?;
            run_tool(
                &tools.elmersolver,
                &["case.sif"],
                &dir,
                &dir.join("elmersolver.log"),
            )?;
            let (max_temperature_k, min_temperature_k) = parse_scalars(&dir.join("scalars.dat"))?;
            let flux_w = parse_boundary_flux(&dir.join("elmersolver.log"))?;
            let nodes = fs::read_to_string(dir.join("physical/mesh.header"))?
                .split_whitespace()
                .next()
                .context("mesh header node count")?
                .parse()?;
            let tetrahedra = fs::read_to_string(dir.join("physical/mesh.header"))?
                .split_whitespace()
                .nth(1)
                .context("mesh header element count")?
                .parse()?;
            cases.push(MeshCase {
                name,
                mesh_size_m: size,
                nodes,
                tetrahedra,
                max_temperature_k,
                min_temperature_k,
                source_power_w: geometry.total_copper_joule_w,
                heat_balance_residual_w: (flux_w + geometry.total_copper_joule_w).abs(),
            });
        }
    }
    let balanced = cases
        .iter()
        .all(|case| case.heat_balance_residual_w <= 1e-3);
    let report = LeadFemAssessment { schema: ASSESSMENT_SCHEMA.into(), status: if balanced { "numerical_evidence_unqualified_package" } else { "solver_completed_energy_unbalanced" }.into(), input_sha256: input_sha256(&bytes), geometry, cases, limitations: vec!["Bridge junction-to-lead and package internals are unavailable; applicability remains INDETERMINATE.".into(), "Solder wetting, barrel plating and lead heat paths are idealised from dimensioned assembly inputs.".into(), "The independent source is copper-neck I²R; diode/package dissipation is not represented.".into(), "Boundary heat flux is compared with the independently computed source; non-zero residuals keep the run unqualified.".into()] };
    fs::write(
        output.join("assessment.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    Ok(report)
}

fn parse_scalars(path: &Path) -> Result<(f64, f64)> {
    let text = fs::read_to_string(path).with_context(|| format!("read {}", path.display()))?;
    let row = text
        .lines()
        .find(|line| !line.trim().is_empty())
        .context("missing scalar row")?;
    let nums: Vec<f64> = row
        .split_whitespace()
        .map(str::parse)
        .collect::<std::result::Result<_, _>>()?;
    ensure!(
        nums.len() >= 2 && nums[..2].iter().all(|v| v.is_finite()),
        "invalid scalar temperatures"
    );
    Ok((nums[0], nums[1]))
}

fn parse_boundary_flux(path: &Path) -> Result<f64> {
    let text = fs::read_to_string(path)?;
    let line = text
        .lines()
        .find(|line| line.contains("temperature Flux over BC 1:"))
        .context("missing Elmer boundary heat flux")?;
    let value = line
        .rsplit_once(':')
        .context("malformed boundary flux")?
        .1
        .trim()
        .parse::<f64>()?;
    ensure!(value.is_finite(), "non-finite boundary heat flux");
    Ok(value)
}

/// Replay verifies source identity and recomputes the analytical source.
pub fn replay(output: &Path, expected_input: &[u8]) -> Result<LeadFemAssessment> {
    let retained = fs::read(output.join("input.json"))?;
    ensure!(
        retained == expected_input,
        "physical-model input differs from retained source"
    );
    let input: PhysicalModelInput = serde_json::from_slice(expected_input)?;
    let report: LeadFemAssessment =
        serde_json::from_slice(&fs::read(output.join("assessment.json"))?)?;
    ensure!(
        report.schema == ASSESSMENT_SCHEMA && report.input_sha256 == input_sha256(expected_input),
        "assessment identity mismatch"
    );
    ensure!(
        report.geometry == geometry_receipt(&input)?,
        "geometry/source summary mismatch"
    );
    ensure!(
        report.cases.len() == 6,
        "expected three meshes at two domain sizes"
    );
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> PhysicalModelInput {
        let nets = ["minus", "ac1", "ac2", "plus"];
        PhysicalModelInput {
            schema: INPUT_SCHEMA.into(),
            board_sha256: "a".repeat(64),
            geometry_source: "synthetic-benchmark-v1".into(),
            bridge_mpn: "GBU2510A".into(),
            current_a: 15.0,
            ambient_k: 313.15,
            copper_thickness_m: 70e-6,
            fr4_thickness_m: 1.44e-3,
            copper_conductivity_s_m: 5.5e7,
            copper_conductivity_tempco_per_k: 0.00393,
            copper_conductivity_temperature_k: 293.15,
            solder_conductivity_w_mk: 50.0,
            barrel_conductivity_s_m: 5.5e7,
            barrel_conductivity_tempco_per_k: 0.00393,
            lead_conductivity_s_m: 5.5e7,
            thermal_conductivity_copper_w_mk: 350.0,
            thermal_conductivity_fr4_w_mk: 0.25,
            thermal_conductivity_solder_w_mk: 50.0,
            thermal_conductivity_barrel_w_mk: 20.0,
            thermal_conductivity_lead_w_mk: 100.0,
            necks: nets
                .iter()
                .enumerate()
                .map(|(i, net)| LeadPath {
                    net: (*net).into(),
                    length_m: 0.008,
                    width_m: 0.003,
                    pad_length_m: 0.002,
                    pad_width_m: 0.004,
                    lead_length_m: 0.001,
                    lead_width_m: 0.001,
                    barrel_diameter_m: 0.001,
                    solder_thickness_m: 0.00015,
                    x_offset_m: (i as f64 - 1.5) * 0.008,
                })
                .collect(),
        }
    }
    #[test]
    fn uniform_control_matches_closed_form() {
        assert!((uniform_path_resistance(0.1, 2e-6, 5e7).unwrap() - 0.001).abs() < 1e-12);
    }
    #[test]
    fn geometry_receipt_has_four_domains_and_source() {
        let r = geometry_receipt(&fixture()).unwrap();
        assert_eq!(r.domains.len(), 4);
        assert!(r.total_copper_joule_w > 0.0);
    }
    #[test]
    fn overlapping_domains_rejected() {
        let mut x = fixture();
        x.necks[1].x_offset_m = x.necks[0].x_offset_m;
        assert!(validate_input(&x).is_err());
    }
    #[test]
    fn missing_interface_dimension_rejected() {
        let mut x = fixture();
        x.necks[0].solder_thickness_m = 0.0;
        assert!(validate_input(&x).is_err());
    }
    #[test]
    fn zero_source_control_is_passive() {
        let mut x = fixture();
        x.current_a = 0.0;
        let receipt = geometry_receipt(&x).unwrap();
        assert_eq!(receipt.total_copper_joule_w, 0.0);
        assert!(generate_sif(&x, &receipt, x.ambient_k)
            .unwrap()
            .contains("Heat Source = 0.000000000000e0"));
    }
    #[test]
    fn generated_geo_contains_all_physical_solids() {
        let g = generate_geo(&fixture(), 0.0005).unwrap();
        assert!(g.contains("BooleanDifference"));
        assert_eq!(g.matches("BooleanFragments").count(), 0);
    }
    #[test]
    fn generated_sif_binds_independent_source() {
        let x = fixture();
        let r = geometry_receipt(&x).unwrap();
        let sif = generate_sif(&x, &r, x.ambient_k).unwrap();
        assert!(sif.contains("Heat Source ="));
        let model_volume = x
            .necks
            .iter()
            .map(|n| {
                0.006 * (n.length_m + 0.003) * x.fr4_thickness_m
                    + n.width_m * n.length_m * x.copper_thickness_m
                    + n.pad_length_m * n.pad_width_m * n.solder_thickness_m
                    + n.lead_length_m * n.lead_width_m * n.lead_width_m
            })
            .sum::<f64>();
        let expected = r.total_copper_joule_w / model_volume / 8960.0;
        assert!(sif.contains(&format!("Heat Source = {expected:.12e}")));
    }
}
