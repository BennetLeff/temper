//! Native shunt-to-board heat paths. Unpublished resistor internals and
//! enclosure cooling remain applicability gaps, even when the solve converges.
use crate::{neck_run::Tools, shunt_local};
use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::io::Read;
use std::{collections::BTreeMap, fs, path::Path, time::Duration};

pub const MESHES: [f64; 3] = [0.0001, 0.00005, 0.00004];
fn scenario_meshes(p: &Scenario) -> [f64; 3] {
    // The hotter terminal needs one further refinement; the 40 um result
    // failed the unchanged 0.5 K estimated-remaining-error requirement.
    if p.name == "pad2-hot" {
        [MESHES[0], MESHES[1], 0.000035]
    } else {
        MESHES
    }
}
const APPLICABILITY: &str = "INDETERMINATE: heat imposed at solder contacts; internal resistor thermal resistance, full-board/enclosure cooling, other heat sources and transient/pulse behavior are not modeled";
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Track {
    pub ends: [[f64; 2]; 2],
    pub width: f64,
    pub front: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Via {
    pub centre: [f64; 2],
    pub diameter: f64,
    pub drill: f64,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Geometry {
    pub local: shunt_local::Geometry,
    /// Copper plus dielectric only; adiabatic solder-mask skins are omitted.
    pub board_mm: f64,
    pub finished_board_mm: f64,
    pub tracks: Vec<Track>,
    pub vias: Vec<Via>,
    pub zones: Vec<Vec<[f64; 2]>>,
    pub zone_bounds: Vec<[f64; 4]>,
    /// x minimum, x maximum, y minimum, y maximum, native world millimetres.
    pub crop: [f64; 4],
}
fn pair(v: &Value) -> Result<[f64; 2]> {
    let p: [f64; 2] = serde_json::from_value(v.clone())?;
    ensure!(p.iter().all(|v| v.is_finite()), "nonfinite position");
    Ok(p)
}
fn overlaps(bounds: [f64; 4], crop: [f64; 4]) -> bool {
    bounds[1] > crop[0] && bounds[0] < crop[1] && bounds[3] > crop[2] && bounds[2] < crop[3]
}
pub(crate) fn in_poly(p: [f64; 2], poly: &[[f64; 2]]) -> bool {
    let mut yes = false;
    for (a, b) in poly
        .iter()
        .zip(poly.iter().cycle().skip(1))
        .take(poly.len())
    {
        if (a[1] > p[1]) != (b[1] > p[1])
            && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            yes = !yes;
        }
    }
    yes
}
fn segment_hits(a: [f64; 2], b: [f64; 2], c: [f64; 4]) -> bool {
    let mut lo: f64 = 0.;
    let mut hi: f64 = 1.;
    for (axis, min, max) in [(0, c[0], c[1]), (1, c[2], c[3])] {
        let d = b[axis] - a[axis];
        if d.abs() < 1e-12 {
            if a[axis] < min || a[axis] > max {
                return false;
            }
        } else {
            let u = (min - a[axis]) / d;
            let v = (max - a[axis]) / d;
            lo = lo.max(u.min(v));
            hi = hi.min(u.max(v));
        }
    }
    lo <= hi
}
pub fn geometry(native: &[u8], widen: bool) -> Result<Geometry> {
    let local = shunt_local::geometry(native)?;
    let n: Value = serde_json::from_slice(native)?;
    // The crop assumes the reviewed continuous substrate and absence of
    // cutouts. A different board requires an explicit applicability review,
    // even if its two shunt pads happen to retain the same coordinates.
    ensure!(
        local.board_sha256 == "b1e06afbf0e9a8b41a3bbbbd046abeb5495e9b42f3fc07e1b312095bc7e97583",
        "unreviewed assembly board outline/cutouts"
    );
    ensure!(
        zapote_drc::native_binding::validate(std::str::from_utf8(native)?).status
            == zapote_core::Status::Pass,
        "native geometry does not bind saved board"
    );
    let crop = if widen {
        [67., 88., 128., 136.]
    } else {
        [68., 87., 128., 136.]
    };
    // This is a bounded physical fixture, not an arbitrary-board geometry engine.
    ensure!(
        local.pad_centres_mm == [[80.05, 132.], [75.95, 132.]],
        "unsupported shunt position"
    );
    for c in n["components"].as_array().context("components")? {
        for p in c["footprint_pads"].as_array().context("pads")? {
            let [x, y] = pair(&p["position_mm"])?;
            let [w, h] = pair(&p["size_mm"])?;
            // Circumscribed circle also catches rotated non-shunt pads.
            let angle = p["orientation_deg"]
                .as_f64()
                .context("pad orientation")?
                .rem_euclid(180.);
            let [rx, ry] = if angle == 0. {
                [w / 2., h / 2.]
            } else if angle == 90. {
                [h / 2., w / 2.]
            } else {
                [w.hypot(h) / 2.; 2]
            };
            ensure!(
                c["id"] == "shunt" || !overlaps([x - rx, x + rx, y - ry, y + ry], crop),
                "another component enters crop: {}",
                c["id"]
            );
        }
    }
    let mut zones = Vec::new();
    for z in n["zones"].as_array().context("zones")? {
        for p in z["filled_polygons"].as_array().context("zone polygons")? {
            let ps = p["outer_mm"]
                .as_array()
                .context("zone outer")?
                .iter()
                .map(pair)
                .collect::<Result<Vec<_>>>()?;
            ensure!(ps.len() >= 3, "invalid zone polygon");
            let corners = [
                [crop[0], crop[2]],
                [crop[1], crop[2]],
                [crop[0], crop[3]],
                [crop[1], crop[3]],
            ];
            if corners.iter().any(|p| in_poly(*p, &ps))
                || ps
                    .iter()
                    .zip(ps.iter().cycle().skip(1))
                    .take(ps.len())
                    .any(|(a, b)| segment_hits(*a, *b, crop))
            {
                ensure!(
                    z["layer"] == "B.Cu" && p["holes_mm"].as_array().is_some_and(Vec::is_empty),
                    "unsupported zone layer/holes"
                );
                zones.push(ps);
            }
        }
    }
    let mut tracks = Vec::new();
    for t in n["traces"].as_array().context("traces")? {
        let ps = t["points_mm"].as_array().context("trace points")?;
        ensure!(ps.len() >= 2, "empty trace");
        let width = t["width_mm"].as_f64().context("width")?;
        ensure!(width.is_finite() && width > 0., "invalid trace width");
        for ab in ps.windows(2) {
            let a = pair(&ab[0])?;
            let b = pair(&ab[1])?;
            let r = width / 2.;
            if overlaps(
                [
                    a[0].min(b[0]) - r,
                    a[0].max(b[0]) + r,
                    a[1].min(b[1]) - r,
                    a[1].max(b[1]) + r,
                ],
                crop,
            ) {
                ensure!(
                    t["layer"] == "F.Cu" || t["layer"] == "B.Cu",
                    "unsupported layer"
                );
                ensure!((a[0] - b[0]).hypot(a[1] - b[1]) > 1e-6, "zero-length trace");
                tracks.push(Track {
                    ends: [a, b],
                    width,
                    front: t["layer"] == "F.Cu",
                });
            }
        }
    }
    let mut vias = Vec::new();
    for v in n["vias"].as_array().context("vias")? {
        let centre = pair(&v["position_mm"])?;
        let diameter = v["diameter_mm"].as_f64().context("via diameter")?;
        let drill = v["drill_mm"].as_f64().context("via drill")?;
        let [x, y] = centre;
        let r = diameter / 2.;
        if overlaps([x - r, x + r, y - r, y + r], crop) {
            ensure!(
                x - r > crop[0] && x + r < crop[1] && y - r > crop[2] && y + r < crop[3],
                "via crosses crop"
            );
            ensure!(
                diameter == 1.4
                    && drill == 0.8
                    && v["from_layer"] == "F.Cu"
                    && v["to_layer"] == "B.Cu",
                "unsupported via"
            );
            vias.push(Via {
                centre,
                diameter,
                drill,
            });
        }
    }
    ensure!(vias.len() == 12, "expected twelve native thermal vias");
    let zone_bounds = zones
        .iter()
        .map(|ps| {
            ps.iter().fold(
                [
                    f64::INFINITY,
                    f64::NEG_INFINITY,
                    f64::INFINITY,
                    f64::NEG_INFINITY,
                ],
                |[x0, x1, y0, y1], [x, y]| [x0.min(*x), x1.max(*x), y0.min(*y), y1.max(*y)],
            )
        })
        .collect();
    let stack = zapote_drc::stackup::physical_dimensions(
        n["board_file_utf8"].as_str().context("board bytes")?,
    )
    .map_err(anyhow::Error::msg)?;
    let board_mm = stack
        .layers_mm
        .iter()
        .filter(|(name, _)| name.ends_with(".Cu") || name.starts_with("dielectric "))
        .map(|(_, mm)| *mm)
        .sum();
    Ok(Geometry {
        local,
        board_mm,
        finished_board_mm: stack.board_thickness_mm,
        tracks,
        vias,
        zones,
        zone_bounds,
        crop,
    })
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Scenario {
    pub name: String,
    pub split: [f64; 2],
    pub cut_c: f64,
    pub plating_mm: f64,
    pub solder_mm: f64,
    pub solder_k: f64,
    pub fr4_k: f64,
    pub widen: bool,
    pub direct: bool,
}
pub fn scenarios() -> Vec<Scenario> {
    let base = Scenario {
        name: "nominal".into(),
        split: [0.5, 0.5],
        cut_c: 60.,
        plating_mm: 0.025,
        solder_mm: 0.15,
        solder_k: 50.,
        fr4_k: 0.25,
        widen: false,
        direct: false,
    };
    vec![
        base.clone(),
        Scenario {
            name: "hot-board".into(),
            cut_c: 80.,
            ..base.clone()
        },
        Scenario {
            name: "pad1-hot".into(),
            split: [1., 0.],
            ..base.clone()
        },
        Scenario {
            name: "pad2-hot".into(),
            split: [0., 1.],
            ..base.clone()
        },
        Scenario {
            name: "weak-joints".into(),
            plating_mm: 0.015,
            solder_mm: 0.25,
            solder_k: 25.,
            fr4_k: 0.18,
            ..base.clone()
        },
        Scenario {
            name: "wider-domain".into(),
            widen: true,
            ..base
        },
    ]
}
// All distances above are mm; the solver geometry uses metres exclusively.
struct Geo {
    text: String,
    next: usize,
}
impl Geo {
    fn id(&mut self) -> usize {
        let i = self.next;
        self.next += 1;
        i
    }
    fn box_(&mut self, p: [f64; 3], d: [f64; 3]) -> usize {
        let i = self.id();
        self.text += &format!(
            "Box({i})={{{},{},{},{},{},{}}};\n",
            p[0] * 1e-3,
            p[1] * 1e-3,
            p[2] * 1e-3,
            d[0] * 1e-3,
            d[1] * 1e-3,
            d[2] * 1e-3
        );
        i
    }
    fn cylinder(&mut self, p: [f64; 2], z: f64, h: f64, r: f64) -> usize {
        let i = self.id();
        self.text += &format!(
            "Cylinder({i})={{{},{},{},0,0,{},{}}};\n",
            p[0] * 1e-3,
            p[1] * 1e-3,
            z * 1e-3,
            h * 1e-3,
            r * 1e-3
        );
        i
    }
}
fn ids(v: &[usize]) -> String {
    v.iter().map(usize::to_string).collect::<Vec<_>>().join(",")
}
// Clip only for CAD construction. Membership/volume checks use the untouched
// native polygon; removing sub-micron edges avoids OpenCASCADE's tolerance floor.
fn clipped_zone(poly: &[[f64; 2]], crop: [f64; 4]) -> Vec<[f64; 2]> {
    let mut out = poly.to_vec();
    for (axis, limit, sign) in [
        (0, crop[0], 1.),
        (0, crop[1], -1.),
        (1, crop[2], 1.),
        (1, crop[3], -1.),
    ] {
        let old = out;
        out = Vec::new();
        for (a, b) in old.iter().zip(old.iter().cycle().skip(1)).take(old.len()) {
            let ai = (a[axis] - limit) * sign >= 0.;
            let bi = (b[axis] - limit) * sign >= 0.;
            if ai {
                out.push(*a);
            }
            if ai != bi {
                let t = (limit - a[axis]) / (b[axis] - a[axis]);
                let mut p = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
                p[axis] = limit;
                out.push(p);
            }
        }
    }
    let mut clean: Vec<[f64; 2]> = Vec::new();
    for p in out {
        if clean
            .last()
            .is_none_or(|a| (a[0] - p[0]).hypot(a[1] - p[1]) > 0.001)
        {
            clean.push(p);
        }
    }
    if clean.len() > 1
        && (clean[0][0] - clean[clean.len() - 1][0]).hypot(clean[0][1] - clean[clean.len() - 1][1])
            < 0.001
    {
        clean.pop();
    }
    clean
}
pub fn geo(g: &Geometry, p: &Scenario, mesh: f64) -> String {
    let mut b=Geo{text:format!("SetFactory(\"OpenCASCADE\");\nMesh.MshFileVersion=2.2;\nMesh.ElementOrder=1;\nMesh.CharacteristicLengthMin={};\nMesh.CharacteristicLengthMax={};\nMesh.MeshSizeFromCurvature=32;\nMesh.MinimumCirclePoints=32;\n",mesh/10.,mesh*4.),next:100};
    let tc = g.local.copper_mm;
    let h = g.board_mm;
    let [x0, x1, y0, y1] = g.crop;
    for (li, z) in [(0, h - tc), (1, 0.)] {
        let mut v = Vec::new();
        if li == 0 {
            for c in g.local.pad_centres_mm {
                v.push(b.box_([c[0] - 1.75, c[1] - 2.65, z], [3.5, 5.3, tc]));
            }
        }
        for t in g.tracks.iter().filter(|t| t.front == (li == 0)) {
            let [a, c] = t.ends;
            let length = (c[0] - a[0]).hypot(c[1] - a[1]);
            let id = b.box_([a[0], a[1] - t.width / 2., z], [length, t.width, tc]);
            b.text += &format!(
                "Rotate {{{{0,0,1}},{{{},{},0}},{}}} {{Volume{{{id}}};}}\n",
                a[0] * 1e-3,
                a[1] * 1e-3,
                (c[1] - a[1]).atan2(c[0] - a[0])
            );
            v.extend([
                id,
                b.cylinder(a, z, tc, t.width / 2.),
                b.cylinder(c, z, tc, t.width / 2.),
            ]);
        }
        for via in &g.vias {
            v.push(b.cylinder(via.centre, z, tc, via.diameter / 2.));
        }
        let mut zone_volumes = String::new();
        if li == 1 {
            for (j, poly) in g.zones.iter().enumerate() {
                let poly = clipped_zone(poly, g.crop);
                let first = 100000 + j * 10000;
                for (k, [x, y]) in poly.iter().enumerate() {
                    b.text += &format!(
                        "Point({})={{{},{},{}}};\n",
                        first + k,
                        x * 1e-3,
                        y * 1e-3,
                        z * 1e-3
                    );
                }
                for k in 0..poly.len() {
                    b.text += &format!(
                        "Line({})={{{},{}}};\n",
                        first + k,
                        first + k,
                        first + (k + 1) % poly.len()
                    );
                }
                let lines = (first..first + poly.len()).collect::<Vec<_>>();
                b.text+=&format!("Curve Loop({first})={{{}}};Plane Surface({first})={{{first}}};\nzz{j}[]=Extrude {{0,0,{}}} {{Surface{{{first}}};}};\n",ids(&lines),tc*1e-3);
                zone_volumes += &format!(",zz{j}[1]");
                b.next += 10000;
            }
        }
        b.text+=&format!("cu{li}[]=BooleanUnion{{Volume{{{}}};Delete;}}{{Volume{{{}{zone_volumes}}};Delete;}};\n",v[0],ids(&v[1..]));
        let crop = b.box_([x0, y0, z], [x1 - x0, y1 - y0, tc]);
        b.text+=&format!("cu{li}[]=BooleanIntersection{{Volume{{cu{li}[]}};Delete;}}{{Volume{{{crop}}};Delete;}};\n");
        let drills: Vec<_> = g
            .vias
            .iter()
            .map(|v| b.cylinder(v.centre, z, tc, v.drill / 2.))
            .collect();
        b.text += &format!(
            "cu{li}[]=BooleanDifference{{Volume{{cu{li}[]}};Delete;}}{{Volume{{{}}};Delete;}};\n",
            ids(&drills)
        );
    }
    let substrate = b.box_([x0, y0, tc], [x1 - x0, y1 - y0, h - 2. * tc]);
    let holes: Vec<_> = g
        .vias
        .iter()
        .map(|v| b.cylinder(v.centre, tc, h - 2. * tc, v.drill / 2. + p.plating_mm))
        .collect();
    b.text += &format!(
        "fr4[]=BooleanDifference{{Volume{{{substrate}}};Delete;}}{{Volume{{{}}};Delete;}};\n",
        ids(&holes)
    );
    let mut barrels = Vec::new();
    for (j, v) in g.vias.iter().enumerate() {
        let out = b.cylinder(v.centre, tc, h - 2. * tc, v.drill / 2. + p.plating_mm);
        let inn = b.cylinder(v.centre, tc, h - 2. * tc, v.drill / 2.);
        b.text += &format!(
            "bar{j}[]=BooleanDifference{{Volume{{{out}}};Delete;}}{{Volume{{{inn}}};Delete;}};\n"
        );
        barrels.push(format!("bar{j}[]"));
    }
    let mut sold = Vec::new();
    for cx in [80.125, 75.875] {
        sold.push(b.box_([cx - 1.45, 132. - 2.475, h], [2.9, 4.95, p.solder_mm]));
    }
    b.text += &format!(
        "all[]=BooleanFragments{{Volume{{cu0[],cu1[],fr4[],{},{}}};Delete;}}{{}};\ne=1e-6;\n",
        barrels.join(","),
        ids(&sold)
    );
    b.text+=&format!("front[]=Volume In BoundingBox{{-1,-1,{}-e,1,1,{}+e}};\nback[]=Volume In BoundingBox{{-1,-1,-e,1,1,{}+e}};\nPhysical Volume(1)={{front[],back[]}};\n",(h-tc)*1e-3,h*1e-3,tc*1e-3);
    b.text += "barrels[]={};\n";
    for v in &g.vias {
        let [x, y] = v.centre;
        let r = v.drill / 2. + p.plating_mm;
        b.text += &format!(
            "bb[]=Volume In BoundingBox{{{}-e,{}-e,{}-e,{}+e,{}+e,{}+e}};barrels[]+={{bb[]}};\n",
            (x - r) * 1e-3,
            (y - r) * 1e-3,
            tc * 1e-3,
            (x + r) * 1e-3,
            (y + r) * 1e-3,
            (h - tc) * 1e-3
        );
    }
    b.text += "Physical Volume(2)={barrels[]};\n";
    for (i, cx) in [80.125, 75.875].into_iter().enumerate() {
        b.text+=&format!("s{i}[]=Volume In BoundingBox{{{}-e,{}-e,{}-e,{}+e,{}+e,{}+e}};Physical Volume({})={{s{i}[]}};\n",(cx-1.45)*1e-3,129.525e-3,h*1e-3,(cx+1.45)*1e-3,134.475e-3,(h+p.solder_mm)*1e-3,i+4);
    }
    b.text+="substrate[]=all[];substrate[]-={front[],back[],barrels[],s0[],s1[]};Physical Volume(3)={substrate[]};\n";
    let bounds = [(0, x0), (0, x1), (1, y0), (1, y1)];
    b.text += "cuts[]={};\n";
    for (axis, v) in bounds {
        let mut lo = [x0 * 1e-3, y0 * 1e-3, 0.];
        let mut hi = [x1 * 1e-3, y1 * 1e-3, h * 1e-3];
        lo[axis] = v * 1e-3;
        hi[axis] = v * 1e-3;
        b.text += &format!(
            "cc[]=Surface In BoundingBox{{{}-e,{}-e,{}-e,{}+e,{}+e,{}+e}};cuts[]+={{cc[]}};\n",
            lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]
        );
    }
    b.text += "Physical Surface(13)={cuts[]};\n";
    for (i, cx) in [80.125, 75.875].into_iter().enumerate() {
        b.text+=&format!("heat{i}[]=Surface In BoundingBox{{{}-e,{}-e,{}-e,{}+e,{}+e,{}+e}};Physical Surface({})={{heat{i}[]}};\n",(cx-1.45)*1e-3,129.525e-3,(h+p.solder_mm)*1e-3,(cx+1.45)*1e-3,134.475e-3,(h+p.solder_mm)*1e-3,i+14);
    }
    b.text+=&format!("Field[1]=Box;Field[1].VIn={mesh};Field[1].VOut={};Field[1].XMin=0.074;Field[1].XMax=0.082;Field[1].YMin=0.129;Field[1].YMax=0.135;Field[1].ZMin={};Field[1].ZMax={};Field[1].Thickness=0.0003;Background Field=1;\n",mesh*4.,(h-tc)*1e-3-0.0001,(h+p.solder_mm)*1e-3);
    b.text
}
fn sif(p: &Scenario) -> String {
    let mut s=String::from("Header\n CHECK KEYWORDS Warn\n Mesh DB \".\" \"mesh\"\nEnd\nSimulation\n Coordinate System = Cartesian 3D\n Simulation Type = Steady State\n Steady State Max Iterations = 8\nEnd\nEquation 1\n Active Solvers(1) = 1\nEnd\n");
    for (i, k) in [350., 350., p.fr4_k, p.solder_k, p.solder_k]
        .into_iter()
        .enumerate()
    {
        let id = i + 1;
        s+=&format!("Material {id}\n Heat Conductivity = {k}\n Density = 1\n Heat Capacity = 1\nEnd\nBody {id}\n Target Bodies(1) = {id}\n Equation = 1\n Material = {id}\n");
        s += "End\n";
    }
    s += &format!(
        r#"Solver 1
 Equation = Heat Equation
 Procedure = "HeatSolve" "HeatSolver"
 Variable = Temperature
 {linear_solver}
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
        p.cut_c + 273.15,
        linear_solver = if p.direct {
            "Linear System Solver = Direct\n Linear System Direct Method = umfpack"
        } else if p.name == "weak-joints" {
            "Linear System Solver = Iterative\n Linear System Iterative Method = BiCGStab\n Linear System Preconditioning = ILU2\n Linear System Max Iterations = 10000\n Linear System Convergence Tolerance = 1e-12\n Linear System Abort Not Converged = True"
        } else {
            "Linear System Solver = Iterative\n Linear System Iterative Method = BiCGStab\n Linear System Preconditioning = ILU1\n Linear System Max Iterations = 10000\n Linear System Convergence Tolerance = 1e-12\n Linear System Abort Not Converged = True"
        }
    );
    for (i, split) in p.split.into_iter().enumerate() {
        s += &format!(
            "Boundary Condition {}\n Target Boundaries(1) = {}\n Heat Flux = {:.14}\nEnd\n",
            i + 2,
            i + 14,
            shunt_local::HEAT_W * split / (2.9 * 4.95 * 1e-6)
        );
    }
    s
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Case {
    pub scenario: Scenario,
    pub mesh_m: f64,
    pub nodes: usize,
    pub measurement: shunt_local::Measurement,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Report {
    pub schema: String,
    pub applicability: String,
    pub geometry: Geometry,
    pub heat_w: f64,
    pub cases: Vec<Case>,
    pub artifacts: BTreeMap<String, String>,
}
fn case_dir(c: &Case) -> String {
    format!("{}-{}", c.scenario.name, (c.mesh_m * 1e6).round() as u32)
}
fn measure(dir: &Path, p: &Scenario) -> Result<shunt_local::Measurement> {
    let log = fs::read_to_string(dir.join("solver.log"))?;
    let header = read_text(&dir.join("mesh/mesh.header"))?;
    let counts: Vec<usize> = header
        .lines()
        .next()
        .context("mesh header")?
        .split_whitespace()
        .map(str::parse)
        .collect::<std::result::Result<_, _>>()?;
    ensure!(counts.len() == 3, "mesh census");
    for (label, count) in [
        "Number of nodes in mesh:",
        "Number of bulk elements in mesh:",
        "Number of boundary elements in mesh:",
    ]
    .into_iter()
    .zip(counts)
    {
        let actual: Vec<_> = log
            .lines()
            .filter_map(|l| l.strip_prefix(&format!("InitializeMesh: {label}")))
            .collect();
        ensure!(
            actual.len() == 1 && actual[0].trim().parse::<usize>()? == count,
            "solver log mesh census differs"
        );
    }
    shunt_local::measurements_with_sources(dir, p.cut_c, &p.split.map(|x| x * shunt_local::HEAT_W))
}
/// Lossless mesh archival retains original-byte hashes; two representations
/// at once are ambiguous and therefore rejected.
pub(crate) fn read_bytes(path: &Path) -> Result<Vec<u8>> {
    let mut compressed = path.as_os_str().to_os_string();
    compressed.push(".gz");
    let compressed = std::path::PathBuf::from(compressed);
    ensure!(
        !(path.exists() && compressed.exists()),
        "ambiguous raw/compressed artifact"
    );
    let mut bytes = Vec::new();
    const LIMIT: u64 = 256 * 1024 * 1024;
    if path.exists() {
        fs::File::open(path)?
            .take(LIMIT + 1)
            .read_to_end(&mut bytes)?;
    } else {
        flate2::read::MultiGzDecoder::new(fs::File::open(compressed)?)
            .take(LIMIT + 1)
            .read_to_end(&mut bytes)?;
    }
    ensure!(
        bytes.len() as u64 <= LIMIT,
        "assembly artifact exceeds 256 MiB"
    );
    Ok(bytes)
}
pub(crate) fn read_text(path: &Path) -> Result<String> {
    Ok(String::from_utf8(read_bytes(path)?)?)
}
fn hashes(root: &Path, cases: &[Case]) -> Result<BTreeMap<String, String>> {
    let mut paths = vec![
        "native.json".into(),
        "backend.json".into(),
        "reuse.json".into(),
    ];
    for c in cases {
        for f in [
            "local.geo",
            "local.msh",
            "case.sif",
            "scalars.dat",
            "scalars.dat.names",
            "gmsh.log",
            "grid.log",
            "solver.log",
            "gmsh.command.json",
            "grid.command.json",
            "solver.command.json",
            "solver-inputs.json",
            "mesh/mesh.nodes",
            "mesh/mesh.elements",
            "mesh/mesh.boundary",
            "mesh/mesh.header",
        ] {
            paths.push(format!("{}/{f}", case_dir(c)));
        }
    }
    paths
        .into_iter()
        .map(|p| {
            Ok((
                p.clone(),
                format!("{:x}", Sha256::digest(read_bytes(&root.join(p))?)),
            ))
        })
        .collect()
}
fn profile() -> Vec<(Scenario, f64)> {
    let mut cases: Vec<_> = scenarios()
        .into_iter()
        .flat_map(|p| scenario_meshes(&p).into_iter().map(move |m| (p.clone(), m)))
        .collect();
    let mut direct = scenarios().remove(0);
    direct.name = "direct-control".into();
    direct.direct = true;
    cases.push((direct, MESHES[0]));
    cases
}
fn validate_profile(cases: &[Case]) -> Result<()> {
    ensure!(
        cases.len() == profile().len(),
        "incomplete assembly profile"
    );
    for (case, (p, m)) in cases.iter().zip(profile()) {
        ensure!(
            case.scenario == p && case.mesh_m == m,
            "assembly profile changed"
        );
    }
    ensure!(
        (cases.last().context("direct control")?.measurement.max_c - cases[0].measurement.max_c)
            .abs()
            < 1e-5,
        "iterative/direct solver disagreement"
    );
    for (cs, p) in cases[..cases.len() - 1].chunks_exact(3).zip(scenarios()) {
        for (c, m) in cs.iter().zip(scenario_meshes(&p)) {
            ensure!(c.scenario == p && c.mesh_m == m, "assembly profile changed");
        }
        for (j, ab) in cs.windows(2).enumerate() {
            ensure!(ab[1].nodes > ab[0].nodes, "mesh did not refine");
            ensure!(
                // First-order remaining-error estimate: for halving this is
                // the raw difference; smaller refinement ratios must satisfy
                // a proportionally tighter difference, not get a free pass.
                (ab[1].measurement.max_c - ab[0].measurement.max_c).abs() * ab[1].mesh_m
                    / (ab[0].mesh_m - ab[1].mesh_m)
                    < [1., 0.5][j],
                "assembly mesh not converged"
            );
        }
    }
    for j in 0..3 {
        ensure!(
            (cases[3 + j].measurement.max_c - cases[j].measurement.max_c - 20.).abs() < 1e-5,
            "uniform boundary shift oracle failed"
        );
    }
    Ok(())
}
fn copy_tree(source: &Path, destination: &Path) -> Result<()> {
    fs::create_dir(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        let dest = destination.join(entry.file_name());
        ensure!(!ty.is_symlink(), "seed evidence symlink rejected");
        if ty.is_dir() {
            copy_tree(&entry.path(), &dest)?;
        } else {
            fs::copy(entry.path(), dest)?;
        }
    }
    Ok(())
}
fn verify_case(g: &Geometry, p: &Scenario, mesh: f64, dir: &Path) -> Result<Case> {
    validate_commands(dir)?;
    ensure!(
        fs::read_to_string(dir.join("local.geo"))? == geo(g, p, mesh)
            && fs::read_to_string(dir.join("case.sif"))? == sif(p),
        "seed case deck differs from current model"
    );
    let nodes = crate::shunt_assembly_mesh::validate(&read_text(&dir.join("local.msh"))?, g, p)?;
    crate::shunt_assembly_mesh::validate_elmer(&dir.join("mesh"), g, p)?;
    validate_solver_inputs(dir)?;
    Ok(Case {
        scenario: p.clone(),
        mesh_m: mesh,
        nodes,
        measurement: measure(dir, p)?,
    })
}
fn solver_inputs(dir: &Path) -> Result<BTreeMap<String, String>> {
    [
        "local.geo",
        "local.msh",
        "case.sif",
        "mesh/mesh.nodes",
        "mesh/mesh.elements",
        "mesh/mesh.boundary",
        "mesh/mesh.header",
    ]
    .into_iter()
    .map(|f| {
        Ok((
            f.into(),
            format!("{:x}", Sha256::digest(read_bytes(&dir.join(f))?)),
        ))
    })
    .collect()
}
fn validate_solver_inputs(dir: &Path) -> Result<()> {
    let receipt: BTreeMap<String, String> =
        serde_json::from_slice(&fs::read(dir.join("solver-inputs.json"))?)?;
    ensure!(
        receipt == solver_inputs(dir)?,
        "solver inputs differ from pre-execution receipt"
    );
    Ok(())
}
fn validate_commands(dir: &Path) -> Result<()> {
    shunt_local::validate_commands(dir, 240000)
}
pub fn run(native: &[u8], out: &Path, tools: &Tools) -> Result<Report> {
    run_from(native, out, tools, None)
}
fn validate_seed_identity(native: &[u8], backend: &[u8], seed: &Path) -> Result<()> {
    ensure!(
        fs::read(seed.join("native.json"))? == native,
        "seed native input mismatch"
    );
    ensure!(
        fs::read(seed.join("backend.json"))? == backend,
        "seed backend differs from installed solver"
    );
    Ok(())
}
/// Reuse only complete cases whose native input, installed backends, generated
/// decks, both meshes and raw measurements pass the current validators.
pub fn run_from(native: &[u8], out: &Path, tools: &Tools, seed: Option<&Path>) -> Result<Report> {
    ensure!(
        [&tools.gmsh, &tools.grid, &tools.solver]
            .iter()
            .all(|p| p.is_absolute()),
        "assembly tool paths must be absolute"
    );
    let g = geometry(native, false)?;
    geometry(native, true)?;
    ensure!(!out.exists(), "refusing to overwrite evidence");
    fs::create_dir_all(out)?;
    fs::write(out.join("native.json"), native)?;
    shunt_local::write_backend(out, tools)?;
    if let Some(seed) = seed {
        validate_seed_identity(native, &fs::read(out.join("backend.json"))?, seed)?;
    }
    let mut reused = BTreeMap::<String, String>::new();
    let mut cases = Vec::new();
    for (p, mesh) in profile() {
        let cg = geometry(native, p.widen)?;
        let dir = out.join(format!("{}-{}", p.name, (mesh * 1e6).round() as u32));
        if let Some(seed) = seed {
            let previous = seed.join(dir.file_name().context("case name")?);
            if previous.exists() {
                verify_case(&cg, &p, mesh, &previous)?;
                copy_tree(&previous, &dir)?;
                let c = verify_case(&cg, &p, mesh, &dir)?;
                reused.insert(
                    dir.file_name()
                        .context("case name")?
                        .to_string_lossy()
                        .into_owned(),
                    format!(
                        "{:x}",
                        Sha256::digest(fs::read(previous.join("solver.log"))?)
                    ),
                );
                cases.push(c);
                continue;
            }
        }
        fs::create_dir(&dir)?;
        fs::write(dir.join("local.geo"), geo(&cg, &p, mesh))?;
        fs::write(dir.join("case.sif"), sif(&p))?;
        let mut nodes = None;
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
                &dir,
                &dir.join(format!("{name}.log")),
                Duration::from_secs(240),
            )?;
            if name == "gmsh" {
                nodes = Some(crate::shunt_assembly_mesh::validate(
                    &read_text(&dir.join("local.msh"))?,
                    &cg,
                    &p,
                )?);
            }
            if name == "grid" {
                crate::shunt_assembly_mesh::validate_elmer(&dir.join("mesh"), &cg, &p)?;
                fs::write(
                    dir.join("solver-inputs.json"),
                    serde_json::to_vec_pretty(&solver_inputs(&dir)?)?,
                )?;
            }
        }
        validate_solver_inputs(&dir)?;
        cases.push(Case {
            scenario: p.clone(),
            mesh_m: mesh,
            nodes: nodes.context("Gmsh validation missing")?,
            measurement: measure(&dir, &p)?,
        });
    }
    fs::write(
        out.join("reuse.json"),
        serde_json::to_vec_pretty(
            &serde_json::json!({"seed":seed,"reused_solver_log_sha256":reused}),
        )?,
    )?;
    validate_profile(&cases)?;
    let r = Report {
        schema: "zapote.shunt-assembly.v1".into(),
        applicability: APPLICABILITY.into(),
        geometry: g,
        heat_w: shunt_local::HEAT_W,
        artifacts: hashes(out, &cases)?,
        cases,
    };
    fs::write(out.join("report.json"), serde_json::to_vec_pretty(&r)?)?;
    Ok(r)
}
pub fn replay(native: &[u8], out: &Path) -> Result<Report> {
    let r: Report = serde_json::from_slice(&fs::read(out.join("report.json"))?)?;
    ensure!(
        r.schema == "zapote.shunt-assembly.v1"
            && r.applicability == APPLICABILITY
            && r.geometry == geometry(native, false)?
            && r.heat_w == shunt_local::HEAT_W,
        "assembly model/native input changed"
    );
    ensure!(
        fs::read(out.join("native.json"))? == native,
        "retained native capture changed"
    );
    shunt_local::validate_backend(out)?;
    validate_profile(&r.cases)?;
    ensure!(
        r.artifacts == hashes(out, &r.cases)?,
        "assembly artifacts changed"
    );
    for c in &r.cases {
        let g = geometry(native, c.scenario.widen)?;
        let d = out.join(case_dir(c));
        validate_commands(&d)?;
        validate_solver_inputs(&d)?;
        ensure!(
            fs::read_to_string(d.join("local.geo"))? == geo(&g, &c.scenario, c.mesh_m)
                && fs::read_to_string(d.join("case.sif"))? == sif(&c.scenario),
            "assembly deck changed"
        );
        ensure!(
            measure(&d, &c.scenario)? == c.measurement,
            "summary differs from raw logs"
        );
        ensure!(
            crate::shunt_assembly_mesh::validate(
                &read_text(&d.join("local.msh"))?,
                &g,
                &c.scenario
            )? == c.nodes,
            "mesh census changed"
        );
        crate::shunt_assembly_mesh::validate_elmer(&d.join("mesh"), &g, &c.scenario)?;
    }
    Ok(r)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> std::path::PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../power-entry/shunt-assembly/run-09/nominal-100")
    }
    fn scratch() -> std::path::PathBuf {
        static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let p = std::env::temp_dir().join(format!(
            "shunt-assembly-test-{}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        fs::create_dir(&p).unwrap();
        p
    }
    fn native() -> Vec<u8> {
        fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../power-entry/shunt-repair/evidence/native-04.json"),
        )
        .unwrap()
    }
    #[test]
    fn native_heat_path_includes_zone_twelve_vias_and_both_layers() {
        let n = native();
        let g = geometry(&n, false).unwrap();
        assert_eq!(g.vias.len(), 12);
        assert_eq!(g.zones.len(), 1);
        assert!(g.tracks.iter().any(|t| t.front));
        assert!(g.tracks.iter().any(|t| !t.front));
        assert!((g.board_mm - 1.58).abs() < 1e-12);
        assert_eq!(g.finished_board_mm, 1.6);
        assert!((g.board_mm - 2. * g.local.copper_mm - 1.44).abs() < 1e-12);
        let wide = geometry(&n, true).unwrap();
        assert!(wide.crop[0] < g.crop[0] && wide.crop[1] > g.crop[1]);
    }
    #[test]
    fn altered_native_via_cannot_silently_change_geometry() {
        let mut n: Value = serde_json::from_slice(&native()).unwrap();
        n["vias"][0]["drill_mm"] = serde_json::json!(0.1);
        assert!(geometry(&serde_json::to_vec(&n).unwrap(), false).is_err());
    }
    #[test]
    fn clipping_preserves_zone_interior_and_excludes_outside_region() {
        let g = geometry(&native(), false).unwrap();
        let p = clipped_zone(&g.zones[0], g.crop);
        assert!(p.len() >= 3);
        for x in [82.9, 83.2, 84., 86.9] {
            for y in [128.1, 134.4, 134.8, 135.9] {
                assert_eq!(in_poly([x, y], &p), in_poly([x, y], &g.zones[0]));
            }
        }
        assert!(!in_poly([90., 150.], &p));
    }
    #[test]
    fn partial_profile_and_false_boundary_shift_are_rejected() {
        assert!(validate_profile(&[]).is_err());
        let cases: Vec<_> = profile()
            .into_iter()
            .enumerate()
            .map(|(j, (p, m))| Case {
                scenario: p,
                mesh_m: m,
                nodes: 100 * (j % 3 + 1),
                measurement: shunt_local::Measurement {
                    max_c: 90.,
                    min_c: 60.,
                    heat_out_w: shunt_local::HEAT_W,
                },
            })
            .collect();
        assert!(validate_profile(&cases)
            .unwrap_err()
            .to_string()
            .contains("shift"));
    }
    #[test]
    fn small_refinement_step_cannot_evade_error_estimate() {
        let mut cases: Vec<_> = profile()
            .into_iter()
            .enumerate()
            .map(|(j, (p, m))| {
                let offset = if p.name == "hot-board" { 20. } else { 0. };
                Case {
                    scenario: p,
                    mesh_m: m,
                    nodes: 100 * (j % 3 + 1),
                    measurement: shunt_local::Measurement {
                        max_c: 90. + offset,
                        min_c: 60. + offset,
                        heat_out_w: shunt_local::HEAT_W,
                    },
                }
            })
            .collect();
        validate_profile(&cases).unwrap();
        // 0.2 K is below the old raw-delta threshold but estimates 0.8 K
        // remaining when refinement is only 50 -> 40 micrometres.
        cases[2].measurement.max_c += 0.2;
        assert!(validate_profile(&cases)
            .unwrap_err()
            .to_string()
            .contains("converged"));
    }
    #[test]
    fn command_contract_rejects_changed_environment_arguments_and_case() {
        let root = scratch();
        let dest = root.join("nominal-100");
        fs::create_dir(&dest).unwrap();
        for name in ["gmsh", "grid", "solver"] {
            fs::copy(
                fixture().join(format!("{name}.command.json")),
                dest.join(format!("{name}.command.json")),
            )
            .unwrap();
        }
        validate_commands(&dest).unwrap();
        let file = dest.join("solver.command.json");
        let original = fs::read(&file).unwrap();
        for (key, val) in [
            ("cwd", serde_json::json!("/different/case")),
            ("program", serde_json::json!("/bin/other")),
            ("args", serde_json::json!(["other.sif"])),
            ("environment", serde_json::json!({"OMP_NUM_THREADS":"8"})),
        ] {
            let mut v: Value = serde_json::from_slice(&original).unwrap();
            v[key] = val;
            fs::write(&file, serde_json::to_vec(&v).unwrap()).unwrap();
            assert!(validate_commands(&dest).is_err());
        }
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn seed_identity_and_deck_changes_are_rejected_before_solver_work() {
        let root = scratch();
        fs::write(root.join("native.json"), b"native").unwrap();
        fs::write(root.join("backend.json"), b"backend").unwrap();
        validate_seed_identity(b"native", b"backend", &root).unwrap();
        assert!(validate_seed_identity(b"changed", b"backend", &root).is_err());
        assert!(validate_seed_identity(b"native", b"changed", &root).is_err());
        let dest = root.join("nominal-100");
        fs::create_dir(&dest).unwrap();
        for name in ["gmsh", "grid", "solver"] {
            fs::copy(
                fixture().join(format!("{name}.command.json")),
                dest.join(format!("{name}.command.json")),
            )
            .unwrap();
        }
        let g = geometry(&native(), false).unwrap();
        let p = scenarios().remove(0);
        fs::write(dest.join("local.geo"), geo(&g, &p, MESHES[0])).unwrap();
        fs::write(dest.join("case.sif"), "changed source flux").unwrap();
        assert!(verify_case(&g, &p, MESHES[0], &dest)
            .unwrap_err()
            .to_string()
            .contains("deck"));
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn compressed_artifact_preserves_bytes_and_rejects_ambiguity() {
        use std::io::Write;
        let root = scratch();
        let path = root.join("sample");
        let original = b"retained original bytes";
        let mut gz = flate2::write::GzEncoder::new(
            fs::File::create(root.join("sample.gz")).unwrap(),
            flate2::Compression::default(),
        );
        gz.write_all(original).unwrap();
        gz.finish().unwrap();
        assert_eq!(read_bytes(&path).unwrap(), original);
        fs::write(&path, original).unwrap();
        assert!(read_bytes(&path).is_err());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn relative_tool_paths_fail_before_creating_evidence() {
        let root = scratch();
        let out = root.join("attempt");
        let tools = Tools {
            gmsh: "gmsh".into(),
            grid: "ElmerGrid".into(),
            solver: "ElmerSolver".into(),
        };
        assert!(run(b"{}", &out, &tools)
            .unwrap_err()
            .to_string()
            .contains("absolute"));
        assert!(!out.exists());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn solver_results_from_a_different_mesh_or_heat_split_are_rejected() {
        let root = scratch();
        fs::create_dir(root.join("mesh")).unwrap();
        for f in [
            "solver.log",
            "scalars.dat",
            "scalars.dat.names",
            "mesh/mesh.header",
        ] {
            fs::copy(fixture().join(f), root.join(f)).unwrap();
        }
        let p = scenarios().remove(0);
        measure(&root, &p).unwrap();
        let log = fs::read_to_string(root.join("solver.log")).unwrap();
        fs::write(
            root.join("solver.log"),
            log.replace("Number of nodes in mesh:", "Number of nodes in mesh: 0"),
        )
        .unwrap();
        assert!(measure(&root, &p).is_err());
        fs::write(root.join("solver.log"), log).unwrap();
        let mut p = p;
        p.split = [1., 0.];
        assert!(measure(&root, &p).is_err());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn changed_solver_input_invalidates_pre_execution_receipt() {
        let root = scratch();
        fs::create_dir(root.join("mesh")).unwrap();
        for p in [
            "local.geo",
            "local.msh",
            "case.sif",
            "mesh/mesh.nodes",
            "mesh/mesh.elements",
            "mesh/mesh.boundary",
            "mesh/mesh.header",
        ] {
            fs::write(root.join(p), p).unwrap();
        }
        fs::write(
            root.join("solver-inputs.json"),
            serde_json::to_vec(&solver_inputs(&root).unwrap()).unwrap(),
        )
        .unwrap();
        validate_solver_inputs(&root).unwrap();
        fs::write(root.join("mesh/mesh.nodes"), "another refinement").unwrap();
        assert!(validate_solver_inputs(&root)
            .unwrap_err()
            .to_string()
            .contains("pre-execution"));
        fs::remove_dir_all(root).unwrap();
    }
}
