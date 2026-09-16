//! Native shunt-pad/local-track heat spreading. This does not resolve the
//! resistor body, solder, vias or whole-board cooling. Cut temperatures are
//! imposed assumptions; numerical convergence never qualifies the assembly.
use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path, time::Duration};

const TRACKS: [&str; 2] = [
    "8211911f-cc39-4eea-97a9-14ae9c9da5db",
    "e45ca754-66c7-4204-987e-e69d5ed1af44",
];
const MESHES: [f64; 3] = [0.0008, 0.0004, 0.0002];
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Geometry {
    pub board_sha256: String,
    pub pad_centres_mm: [[f64; 2]; 2],
    pub pad_size_mm: [f64; 2],
    pub tracks_mm: [[[f64; 2]; 2]; 2],
    pub widths_mm: [f64; 2],
    pub copper_mm: f64,
}
fn pair(v: &Value) -> Result<[f64; 2]> {
    let a = v.as_array().context("missing coordinate")?;
    ensure!(a.len() == 2, "coordinate dimension");
    let p = [a[0].as_f64().context("x")?, a[1].as_f64().context("y")?];
    ensure!(p.iter().all(|x| x.is_finite()), "nonfinite coordinate");
    Ok(p)
}
pub fn geometry(native: &[u8]) -> Result<Geometry> {
    ensure!(
        zapote_drc::native_binding::validate(std::str::from_utf8(native)?).status
            == zapote_core::Status::Pass,
        "native geometry is not bound to saved board"
    );
    let n: Value = serde_json::from_slice(native)?;
    let cs = n["components"].as_array().context("components")?;
    let shunts: Vec<_> = cs.iter().filter(|c| c["id"] == "shunt").collect();
    ensure!(shunts.len() == 1, "one shunt required");
    let s = shunts[0];
    ensure!(s["mpn"] == "HCSM2818FT10L0", "unsupported shunt package");
    let ps = s["footprint_pads"].as_array().context("pads")?;
    ensure!(ps.len() == 2, "two pads required");
    let mut centres = [[0.; 2]; 2];
    for (i, num) in ["1", "2"].iter().enumerate() {
        let p = ps
            .iter()
            .find(|p| p["pad"] == *num)
            .context("pin missing")?;
        ensure!(
            pair(&p["size_mm"])? == [3.5, 5.3]
                && pair(&p["drill_mm"])? == [0., 0.]
                && p["shape"] == 1
                && p["orientation_deg"] == 180.0,
            "reviewed rectangular native land pattern required"
        );
        ensure!(
            p["net"] == ["PFC_BUS_MINUS", "minus"][i]
                && p["layers"]
                    .as_array()
                    .context("pad layers")?
                    .iter()
                    .any(|l| l == "F.Cu")
                && !p["layers"].as_array().unwrap().iter().any(|l| l == "B.Cu"),
            "shunt net/layer differs"
        );
        centres[i] = pair(&p["position_mm"])?;
    }
    ensure!(
        (centres[0][0] - centres[1][0] - 4.1).abs() < 1e-6 && centres[0][1] == centres[1][1],
        "shunt land-pattern gap differs"
    );
    let mut tracks = [[[0.; 2]; 2]; 2];
    let mut widths = [0.; 2];
    let ts = n["traces"].as_array().context("traces")?;
    for (i, id) in TRACKS.iter().enumerate() {
        let t = ts
            .iter()
            .find(|t| t["uuid"] == *id)
            .context("local power trace missing")?;
        ensure!(
            t["layer"] == "F.Cu" && t["net"] == ["PFC_BUS_MINUS", "minus"][i],
            "local trace layer/net differs"
        );
        let p = t["points_mm"].as_array().context("trace points")?;
        ensure!(p.len() == 2, "straight trace required");
        tracks[i] = [pair(&p[0])?, pair(&p[1])?];
        widths[i] = t["width_mm"].as_f64().context("width")?;
        ensure!(
            widths[i] > 0.
                && widths[i].is_finite()
                && tracks[i][0][1] == centres[i][1]
                && tracks[i][1][1] == centres[i][1],
            "horizontal pad-centred trace required"
        );
    }
    // The cut is the existing outer trace endpoint; the inner endpoint must lie in the pad.
    for i in 0..2 {
        let [a, b] = tracks[i];
        ensure!(
            a[0] < centres[i][0] - 1.75 || a[0] > centres[i][0] + 1.75,
            "outer cut intersects pad"
        );
        ensure!(
            (b[0] - centres[i][0]).abs() < 1.75,
            "trace does not enter pad"
        );
    }
    let stack = crate::neck_geometry::extract_stackup_dimensions(native)?;
    ensure!(
        (stack.copper_thickness_um - 70.).abs() < 1e-9,
        "reviewed 70 um front copper required"
    );
    Ok(Geometry {
        board_sha256: n["board_sha256"].as_str().context("board digest")?.into(),
        pad_centres_mm: centres,
        pad_size_mm: [3.5, 5.3],
        tracks_mm: tracks,
        widths_mm: widths,
        copper_mm: 0.07,
    })
}
/// Independent construction from actual native rectangles and capsule track
/// ends, cropped at their original outer centreline endpoints.
pub fn geo(g: &Geometry, mesh: f64) -> String {
    let tc = g.copper_mm / 1000.;
    let mut s=format!("SetFactory(\"OpenCASCADE\");\nMesh.MshFileVersion=2.2;\nMesh.CharacteristicLengthMin={mesh};\nMesh.CharacteristicLengthMax={mesh};\nMesh.ElementOrder=1;\n");
    for i in 0..2 {
        let c = g.pad_centres_mm[i];
        let a = g.tracks_mm[i][0][0] / 1000.;
        let b = g.tracks_mm[i][1][0] / 1000.;
        let y = c[1] / 1000.;
        let w = g.widths_mm[i] / 1000.;
        let p = i + 1;
        let t = i + 3;
        let cap = i + 5;
        s+=&format!("Box({p})={{{},{},0,0.0035,0.0053,{tc}}};\nBox({t})={{{},{},0,{},{w},{tc}}};\nCylinder({cap})={{{b},{y},0,0,0,{tc},{}}};\n",c[0]/1000.-0.00175,y-0.00265,a.min(b),y-w/2.,(a-b).abs(),w/2.);
    }
    s += "all[]=BooleanFragments{Volume{1,2,3,4,5,6};Delete;}{};\ne=1e-6;\n";
    for i in 0..2 {
        let c = g.pad_centres_mm[i];
        let x = c[0] / 1000.;
        let y = c[1] / 1000.;
        s+=&format!("p{i}[]=Volume In BoundingBox{{{}-e,{}-e,-e,{}+e,{}+e,{tc}+e}};\nPhysical Volume({})={{p{i}[]}};\n",x-0.00175,y-0.00265,x+0.00175,y+0.00265,i+1);
    }
    s += "other[]=all[]; other[]-={p0[],p1[]}; Physical Volume(3)={other[]};\n";
    for i in 0..2 {
        let x = g.tracks_mm[i][0][0] / 1000.;
        let y = g.pad_centres_mm[i][1] / 1000.;
        let r = g.widths_mm[i] / 2000.;
        s += &format!(
            "cut{i}[]=Surface In BoundingBox{{{x}-e,{}-e,-e,{x}+e,{}+e,{tc}+e}};\n",
            y - r,
            y + r
        );
    }
    s += "Physical Surface(13)={cut0[],cut1[]};\n";
    s
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Scenario {
    pub name: String,
    pub split: [f64; 2],
    pub cut_c: f64,
    pub conductivity: f64,
}
pub fn scenarios() -> Vec<Scenario> {
    [
        ("nominal", [0.5, 0.5], 80., 350.),
        ("pad1-hot", [1., 0.], 80., 350.),
        ("pad2-hot", [0., 1.], 80., 350.),
        ("hot-cut", [0.5, 0.5], 100., 350.),
        ("weak-copper", [0.5, 0.5], 80., 250.),
    ]
    .into_iter()
    .map(|(n, split, cut_c, conductivity)| Scenario {
        name: n.into(),
        split,
        cut_c,
        conductivity,
    })
    .collect()
}
// Conditional heat input at 100 C, +1% and +75 ppm/K. Higher modeled copper
// temperatures do not qualify or predict the unmodeled resistor body.
pub const HEAT_W: f64 = 15. * 15. * 0.01 * 1.01 * (1. + 75e-6 * 75.);
fn sif(g: &Geometry, p: &Scenario) -> String {
    let vol = g.pad_size_mm[0] * g.pad_size_mm[1] * g.copper_mm * 1e-9;
    let mut s=format!("Header\n CHECK KEYWORDS Warn\n Mesh DB \".\" \"mesh\"\nEnd\nSimulation\n Coordinate System = Cartesian 3D\n Simulation Type = Steady State\n Steady State Max Iterations = 8\nEnd\nEquation 1\n Active Solvers(1) = 1\nEnd\nMaterial 1\n Heat Conductivity = {}\n Density = 1\n Heat Capacity = 1\nEnd\n",p.conductivity);
    for i in 1..=3 {
        s += &format!("Body {i}\n Target Bodies(1) = {i}\n Equation = 1\n Material = 1\n");
        if i < 3 {
            s += &format!(" Body Force = {i}\n");
        }
        s += "End\n";
    }
    for i in 0..2 {
        s += &format!(
            "Body Force {}\n Heat Source = {:.14}\nEnd\n",
            i + 1,
            HEAT_W * p.split[i] / vol
        );
    }
    s += &format!(
        r#"Solver 1
 Equation = Heat Equation
 Procedure = "HeatSolve" "HeatSolver"
 Variable = Temperature
 Linear System Solver = Direct
 Linear System Direct Method = umfpack
 Nonlinear System Max Iterations = 1
 Steady State Convergence Tolerance = 1e-9
 Calculate Loads = True
 Calculate Boundary Fluxes = True
End
Solver 2
 Exec Solver = After All
 Equation = SaveScalars
 Procedure = "SaveData" "SaveScalars"
 Variable 1 = Temperature
 Operator 1 = max
 Variable 2 = Temperature
 Operator 2 = min
 Filename = scalars.dat
End
Boundary Condition 1
 Target Boundaries(1) = 13
 Temperature = {}
 Save Scalars = True
End
"#,
        p.cut_c + 273.15
    );
    s
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Measurement {
    pub max_c: f64,
    pub min_c: f64,
    pub heat_out_w: f64,
}
fn measurements(d: &Path, p: &Scenario) -> Result<Measurement> {
    let log = fs::read_to_string(d.join("solver.log"))?;
    ensure!(
        log.contains("MAIN: *** Elmer Solver: ALL DONE ***")
            && !["ERROR::", "FATAL", "DIVERGED", "NOT CONVERGED"]
                .iter()
                .any(|x| log.contains(x)),
        "solver did not complete"
    );
    let changes = log
        .lines()
        .filter_map(|l| {
            l.split_once("Relative Change :")
                .map(|(_, v)| v.trim().parse::<f64>())
        })
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let iterations = log
        .lines()
        .filter(|l| l.contains("Steady state iteration:"))
        .count();
    ensure!(
        (2..8).contains(&iterations) && changes.last().is_some_and(|v| v.is_finite() && *v <= 1e-9),
        "steady-state convergence not established"
    );
    let names = fs::read_to_string(d.join("scalars.dat.names"))?;
    let cols = names
        .split_once("Variables in columns of matrix:")
        .context("missing scalar names")?
        .1
        .lines()
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_once(':')
                .map(|(_, n)| n.trim())
                .context("scalar name")
        })
        .collect::<Result<Vec<_>>>()?;
    ensure!(
        cols == [
            "max: temperature",
            "min: temperature",
            "res: temperature flux over bc 1"
        ],
        "unexpected scalar columns: {:?}",
        cols
    );
    let data = fs::read_to_string(d.join("scalars.dat"))?;
    ensure!(
        data.lines().filter(|l| !l.trim().is_empty()).count() == 1,
        "exactly one scalar row required"
    );
    let n = data
        .split_whitespace()
        .map(str::parse)
        .collect::<std::result::Result<Vec<f64>, _>>()?;
    ensure!(
        n.len() == 3 && n.iter().all(|n| n.is_finite()),
        "three finite scalars required"
    );
    ensure!(
        n[0] >= n[1] && (n[1] - 273.15 - p.cut_c).abs() < 1e-5,
        "temperature boundary inconsistency"
    );
    ensure!(
        (-n[2] - HEAT_W).abs() < 1e-7,
        "energy balance: {} versus {}",
        -n[2],
        HEAT_W
    );
    Ok(Measurement {
        max_c: n[0] - 273.15,
        min_c: n[1] - 273.15,
        heat_out_w: -n[2],
    })
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Case {
    pub scenario: Scenario,
    pub mesh_m: f64,
    pub node_count: usize,
    pub measurement: Measurement,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Report {
    pub schema: String,
    pub geometry: Geometry,
    pub heat_w: f64,
    pub cases: Vec<Case>,
    pub artifacts: BTreeMap<String, String>,
    pub applicability: String,
}
fn hash(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn validate_backend(out: &Path) -> Result<()> {
    let b: BTreeMap<String, String> = serde_json::from_slice(&fs::read(out.join("backend.json"))?)?;
    ensure!(
        b.keys().map(String::as_str).collect::<Vec<_>>()
            == ["HeatSolve", "SaveData", "gmsh", "grid", "solver"],
        "backend census differs"
    );
    ensure!(
        b.values()
            .all(|s| s.len() == 64 && s.bytes().all(|c| c.is_ascii_hexdigit())),
        "invalid backend digest"
    );
    Ok(())
}
fn required_hashes(out: &Path, cases: &[Case]) -> Result<BTreeMap<String, String>> {
    let mut paths = vec!["native.json".into(), "backend.json".into()];
    for c in cases {
        let name = format!("{}-{}", c.scenario.name, (c.mesh_m * 1e6).round() as u32);
        for f in [
            "local.geo",
            "local.msh",
            "case.sif",
            "scalars.dat",
            "scalars.dat.names",
            "gmsh.log",
            "grid.log",
            "solver.log",
            "mesh/mesh.nodes",
            "mesh/mesh.elements",
            "mesh/mesh.boundary",
            "mesh/mesh.header",
        ] {
            paths.push(format!("{name}/{f}"));
        }
    }
    paths
        .into_iter()
        .map(|p| Ok((p.clone(), hash(&fs::read(out.join(p))?))))
        .collect()
}
fn profile_validate(cases: &[Case]) -> Result<()> {
    let ps = scenarios();
    ensure!(cases.len() == ps.len() * 3, "incomplete profile");
    for (p, cs) in ps.iter().zip(cases.chunks_exact(3)) {
        for (c, m) in cs.iter().zip(MESHES) {
            ensure!(
                c.scenario == *p && c.mesh_m == m,
                "scenario profile changed"
            );
        }
        for (i, ab) in cs.windows(2).enumerate() {
            ensure!(ab[1].node_count > ab[0].node_count, "mesh did not refine");
            ensure!(
                (ab[1].measurement.max_c - ab[0].measurement.max_c).abs() < [1., 0.5][i],
                "mesh not converged"
            );
        }
    }
    Ok(())
}
pub fn run(native: &[u8], out: &Path, tools: &crate::neck_run::Tools) -> Result<Report> {
    let g = geometry(native)?;
    ensure!(!out.exists(), "refusing to overwrite evidence");
    fs::create_dir_all(out)?;
    fs::write(out.join("native.json"), native)?;
    let mut backend = BTreeMap::new();
    for (name, p) in [
        ("gmsh", &tools.gmsh),
        ("grid", &tools.grid),
        ("solver", &tools.solver),
    ] {
        backend.insert(name.to_owned(), crate::sha256_file(p)?);
    }
    let prefix = tools
        .solver
        .parent()
        .and_then(Path::parent)
        .context("Elmer installation prefix")?;
    for name in ["HeatSolve", "SaveData"] {
        let stem = prefix.join("share/elmersolver/lib").join(name);
        let path = ["dylib", "so"]
            .into_iter()
            .map(|ext| stem.with_extension(ext))
            .find(|p| p.is_file())
            .context("required solver module unavailable")?;
        backend.insert(name.to_owned(), crate::sha256_file(&path)?);
    }
    fs::write(
        out.join("backend.json"),
        serde_json::to_vec_pretty(&backend)?,
    )?;
    validate_backend(out)?;
    let mut cases = Vec::new();
    for p in scenarios() {
        for m in MESHES {
            let d = out.join(format!("{}-{}", p.name, (m * 1e6).round() as u32));
            fs::create_dir(&d)?;
            fs::write(d.join("local.geo"), geo(&g, m))?;
            fs::write(d.join("case.sif"), sif(&g, &p))?;
            for (exe, args, name) in [
                (
                    &tools.gmsh,
                    vec![
                        "-3",
                        "local.geo",
                        "-format",
                        "msh2",
                        "-o",
                        "local.msh",
                        "-nt",
                        "1",
                    ],
                    "gmsh",
                ),
                (
                    &tools.grid,
                    vec!["14", "2", "local.msh", "-out", "mesh"],
                    "grid",
                ),
                (&tools.solver, vec!["case.sif"], "solver"),
            ] {
                crate::run_process(
                    exe,
                    &args,
                    &d,
                    &d.join(format!("{name}.log")),
                    Duration::from_secs(180),
                )?;
                if name == "gmsh" {
                    crate::shunt_mesh::validate(&fs::read_to_string(d.join("local.msh"))?, &g)?;
                }
            }
            crate::shunt_mesh::validate_elmer(&d.join("mesh"), &g)?;
            let measurement = measurements(&d, &p)?;
            cases.push(Case {
                scenario: p.clone(),
                mesh_m: m,
                node_count: crate::shunt_mesh::validate(
                    &fs::read_to_string(d.join("local.msh"))?,
                    &g,
                )?,
                measurement,
            });
        }
    }
    profile_validate(&cases)?;
    let artifacts = required_hashes(out, &cases)?;
    let r=Report{schema:"zapote.shunt-local.v2".into(),geometry:g,heat_w:HEAT_W,cases,artifacts,applicability:"INDETERMINATE: imposed copper cut temperatures; body/solder/vias/whole-board spreading and copper Joule heat omitted".into()};
    fs::write(out.join("report.json"), serde_json::to_vec_pretty(&r)?)?;
    Ok(r)
}
pub fn replay(native: &[u8], out: &Path) -> Result<Report> {
    let r: Report = serde_json::from_slice(&fs::read(out.join("report.json"))?)?;
    ensure!(
        r.schema == "zapote.shunt-local.v2"
            && r.geometry == geometry(native)?
            && r.heat_w == HEAT_W,
        "thermal evidence input/model changed"
    );
    validate_backend(out)?;
    profile_validate(&r.cases)?;
    ensure!(
        r.artifacts == required_hashes(out, &r.cases)?,
        "thermal artifacts changed"
    );
    ensure!(
        geometry(&fs::read(out.join("native.json"))?)? == r.geometry,
        "retained geometry differs"
    );
    for c in &r.cases {
        let d = out.join(format!(
            "{}-{}",
            c.scenario.name,
            (c.mesh_m * 1e6).round() as u32
        ));
        ensure!(
            fs::read_to_string(d.join("local.geo"))? == geo(&r.geometry, c.mesh_m)
                && fs::read_to_string(d.join("case.sif"))? == sif(&r.geometry, &c.scenario),
            "thermal deck differs from current model"
        );
        crate::shunt_mesh::validate_elmer(&d.join("mesh"), &r.geometry)?;
        ensure!(
            measurements(&d, &c.scenario)? == c.measurement
                && crate::shunt_mesh::validate(
                    &fs::read_to_string(d.join("local.msh"))?,
                    &r.geometry
                )? == c.node_count,
            "thermal summary differs from raw data"
        );
    }
    Ok(r)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        path::PathBuf,
        sync::atomic::{AtomicUsize, Ordering},
    };
    fn root() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../power-entry/shunt-repair")
    }
    fn native() -> Vec<u8> {
        fs::read(root().join("evidence/native-04.json")).unwrap()
    }
    struct Scratch(PathBuf);
    impl Scratch {
        fn new() -> Self {
            static NEXT: AtomicUsize = AtomicUsize::new(0);
            let p = std::env::temp_dir().join(format!(
                "zapote-shunt-test-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&p).unwrap();
            Self(p)
        }
        fn retained() -> Self {
            let s = Self::new();
            let source = root().join("thermal-04");
            let r: Report =
                serde_json::from_slice(&fs::read(source.join("report.json")).unwrap()).unwrap();
            for p in r
                .artifacts
                .keys()
                .map(String::as_str)
                .chain(["report.json"])
            {
                let out = s.0.join(p);
                fs::create_dir_all(out.parent().unwrap()).unwrap();
                fs::copy(source.join(p), out).unwrap();
            }
            s
        }
    }
    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    #[test]
    fn retained_fem_replays_and_obeys_linear_heat_equation_symmetries() {
        let r = replay(&native(), &root().join("thermal-04")).unwrap();
        assert_eq!(r.cases.len(), 15);
        let fine = |name: &str| {
            r.cases
                .iter()
                .find(|c| c.scenario.name == name && c.mesh_m == 0.0002)
                .unwrap()
                .measurement
                .max_c
        };
        assert!((fine("hot-cut") - fine("nominal") - 20.).abs() < 1e-5);
        assert!(((fine("weak-copper") - 80.) / (fine("nominal") - 80.) - 350. / 250.).abs() < 1e-5);
        assert!(fine("nominal") > 100.); // conditional local result, not body qualification
    }
    #[test]
    fn board_or_native_pad_changes_invalidate_geometry() {
        let bytes = native();
        let g = geometry(&bytes).unwrap();
        assert_eq!(g.pad_size_mm, [3.5, 5.3]);
        for field in ["mpn", "orientation_deg", "size_mm"] {
            let mut n: Value = serde_json::from_slice(&bytes).unwrap();
            let s = n["components"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|c| c["id"] == "shunt")
                .unwrap();
            match field {
                "mpn" => s[field] = "WSL2726R0100FEA".into(),
                "orientation_deg" => s["footprint_pads"][0][field] = 90.into(),
                _ => s["footprint_pads"][0][field] = serde_json::json!([2., 4.2]),
            }
            assert!(
                geometry(&serde_json::to_vec(&n).unwrap()).is_err(),
                "{field}"
            );
        }
    }
    #[test]
    fn independent_mesh_check_rejects_missing_heat_material_and_wrong_cut() {
        let g = geometry(&native()).unwrap();
        let p = root().join("thermal-04/nominal-200/local.msh");
        let good = fs::read_to_string(p).unwrap();
        assert!(crate::shunt_mesh::validate(&good, &g).is_ok());
        for (from, to) in [(" 4 2 1 ", " 4 2 3 "), (" 2 2 13 ", " 2 2 12 ")] {
            let bad = good.replace(from, to);
            assert_ne!(bad, good);
            assert!(crate::shunt_mesh::validate(&bad, &g).is_err());
        }
    }
    #[test]
    fn edited_summary_deck_and_raw_results_cannot_replay() {
        let s = Scratch::retained();
        let n = native();
        let p = s.0.join("report.json");
        let original = fs::read(&p).unwrap();
        let mut r: Report = serde_json::from_slice(&original).unwrap();
        r.cases[2].measurement.max_c += 0.01;
        fs::write(&p, serde_json::to_vec(&r).unwrap()).unwrap();
        assert!(replay(&n, &s.0).is_err());
        fs::write(&p, &original).unwrap();
        let deck = s.0.join("nominal-200/case.sif");
        fs::write(&deck, "forged deck").unwrap();
        // Even updating the checksum cannot make a changed model its own oracle.
        let mut r: Report = serde_json::from_slice(&original).unwrap();
        r.artifacts = required_hashes(&s.0, &r.cases).unwrap();
        fs::write(&p, serde_json::to_vec(&r).unwrap()).unwrap();
        assert!(replay(&n, &s.0).is_err());
    }
    #[test]
    fn energy_and_solver_convergence_are_required_independently() {
        let s = Scratch::new();
        let src = root().join("thermal-04/nominal-200");
        for name in ["solver.log", "scalars.dat", "scalars.dat.names"] {
            fs::copy(src.join(name), s.0.join(name)).unwrap();
        }
        let p = scenarios().remove(0);
        assert!(measurements(&s.0, &p).is_ok());
        let log = fs::read_to_string(s.0.join("solver.log")).unwrap();
        fs::write(
            s.0.join("solver.log"),
            log.replace("Relative Change :", "untrusted :"),
        )
        .unwrap();
        assert!(measurements(&s.0, &p).is_err());
        fs::write(s.0.join("solver.log"), log).unwrap();
        fs::write(s.0.join("scalars.dat"), "394.5 353.15 -1.0\n").unwrap();
        assert!(measurements(&s.0, &p).is_err());
    }
    #[test]
    fn unconverged_and_incomplete_profiles_are_rejected() {
        let mut r: Report =
            serde_json::from_slice(&fs::read(root().join("thermal-04/report.json")).unwrap())
                .unwrap();
        r.cases[2].measurement.max_c += 2.;
        assert!(profile_validate(&r.cases).is_err());
        r.cases.pop();
        assert!(profile_validate(&r.cases).is_err());
    }
}
