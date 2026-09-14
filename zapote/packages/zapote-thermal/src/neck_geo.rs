//! Conforming local copper/substrate solid, with explicit exterior groups.
use crate::neck_geometry::NeckGeometry;
use anyhow::{ensure, Result};

pub fn generate(neck: &NeckGeometry, copper_um: f64, mesh_mm: f64) -> Result<String> {
    ensure!(
        copper_um.is_finite() && (1.0..=200.0).contains(&copper_um),
        "unsupported copper thickness"
    );
    ensure!(
        mesh_mm.is_finite() && (0.02..=1.0).contains(&mesh_mm),
        "unsupported mesh size"
    );
    let w = neck.pad_size_mm[0] * 0.001;
    let h = neck.pad_size_mm[1] * 0.001;
    let tw = neck.trace_width_mm * 0.001;
    let length = neck.trace_length_mm * 0.001;
    let r = neck.drill_mm * 0.0005;
    let tc = copper_um * 1e-6;
    let core = 0.00144;
    let top = core + tc;
    let mesh = mesh_mm * 0.001;
    let pad = if neck.pad_number == "1" {
        format!(
            "Rectangle(1) = {{{}, {}, {core}, {w}, {h}}};\npad[]={{1}};",
            -w / 2.0,
            -h / 2.0
        )
    } else {
        let straight = h - w;
        ensure!(straight > 0.0, "oval must be longer than wide");
        format!("Rectangle(1) = {{{}, {}, {core}, {w}, {straight}}};\nDisk(2)={{0,{}, {core},{},{}}};\nDisk(3)={{0,{}, {core},{},{}}};\npad[]=BooleanUnion{{Surface{{1}};Delete;}}{{Surface{{2,3}};Delete;}};",-w/2.0,-straight/2.0,-straight/2.0,w/2.0,w/2.0,straight/2.0,w/2.0,w/2.0)
    };
    Ok(format!(
        r#"SetFactory("OpenCASCADE");
Geometry.OCCBooleanPreserveNumbering = 1;
Mesh.MshFileVersion = 2.2;
Mesh.ElementOrder = 1;
Mesh.CharacteristicLengthMin = {mesh};
Mesh.CharacteristicLengthMax = {mesh};
// Coordinates in metres. Native trace direction localized to +Y.
{pad}
trace=news; Rectangle(trace)={{{xmin},0,{core},{tw},{length}}};
face[]=BooleanUnion{{Surface{{pad[]}};Delete;}}{{Surface{{trace}};Delete;}};
cu[]=Extrude{{0,0,{tc}}}{{Surface{{face[]}};}};
substrate=newv; Box(substrate)={{-0.0025,-0.002,0,0.005,{patch_length},{core}}};
hole=newv; Cylinder(hole)={{0,0,-0.0001,0,0,0.002,{r}}};
solids[]=BooleanDifference{{Volume{{cu[1],substrate}};Delete;}}{{Volume{{hole}};Delete;}};
joined[]=BooleanFragments{{Volume{{solids[]}};Delete;}}{{}};
eps=1e-6;
copper[]=Volume In BoundingBox{{-0.0025-eps,-0.002-eps,{core}-eps,0.0025+eps,{length}+eps,{top}+eps}};
fr4[]=Volume In BoundingBox{{-0.0025-eps,-0.002-eps,-eps,0.0025+eps,{length}+eps,{core}+eps}};
terminal[]=Surface In BoundingBox{{-{r}-eps,-{r}-eps,{core}-eps,{r}+eps,{r}+eps,{top}+eps}};
far[]=Surface In BoundingBox{{{xmin}-eps,{length}-eps,{core}-eps,{xmax}+eps,{length}+eps,{top}+eps}};
outer[]=CombinedBoundary{{Volume{{joined[]}};}};
outer[]=Abs(outer[]);
outer[]-={{terminal[],far[]}};
Physical Volume(1)={{copper[]}};
Physical Volume(2)={{fr4[]}};
Physical Surface(11)={{terminal[]}};
Physical Surface(12)={{far[]}};
Physical Surface(13)={{outer[]}};
"#,
        xmin = -tw / 2.0,
        xmax = tw / 2.0,
        patch_length = length + 0.002
    ))
}
