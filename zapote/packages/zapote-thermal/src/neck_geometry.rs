//! Native power-entry terminal-neck geometry for the Gmsh/Elmer model.
//!
//! This module is intentionally a geometry *translator*, not a PCB parser or a
//! thermal solver.  It consumes the frozen native extraction and emits a
//! deterministic Gmsh OpenCASCADE program.  The input is bound to the exact
//! board bytes and to the four reviewed `GBU2510A` pads; missing, duplicated,
//! diagonal, or differently shaped data is rejected rather than guessed.

use anyhow::{bail, ensure, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

const BRIDGE_ID: &str = "bridge";
const BRIDGE_MPN: &str = "GBU2510A";
const BRIDGE_NETS: [&str; 4] = ["minus", "ac1", "ac2", "plus"];
const TRACE_UUIDS: [&str; 4] = [
    "1a8c9e36-4bbf-486e-a8a9-34985b0b249e",
    "6be299ab-3af0-4444-8bb5-c26c3d6443f6",
    "44d2e757-cc34-46a2-88aa-5ae29db62817",
    "e7dc2c72-d7b2-4456-afa6-efe227e0f8f8",
];
const EXPECTED_LENGTH_MM: [f64; 4] = [8.5, 9.0, 6.0, 7.0];
const EXPECTED_WIDTH_MM: f64 = 2.5;
const FR4_THICKNESS_M: f64 = 1.44e-3;
const GBJ_TRACE_UUIDS: [&str; 4] = [
    "33cdb604-2e4a-49a4-bcca-80b829c3818c",
    "8e49f7cf-5c7a-4b79-9cb4-c1cbe398fc62",
    "fcbfb9cb-ae96-4261-8ec9-a57c3db7f95d",
    "c060f5f6-a3d7-4399-923b-4094c1d4c60e",
];
const GBJ_NETS: [&str; 4] = ["plus", "ac1", "ac2", "minus"];

#[derive(Debug, Clone, Deserialize)]
struct NativeInput {
    board_file_utf8: String,
    board_sha256: String,
    components: Vec<Component>,
    traces: Vec<Trace>,
}

#[derive(Debug, Clone, Deserialize)]
struct ManufacturingInput {
    board_sha256: String,
    input: ManufacturingDetail,
}

#[derive(Debug, Clone, Deserialize)]
struct ManufacturingDetail {
    pads: Vec<ManufacturingPad>,
    holes: Vec<ManufacturingHole>,
}

#[derive(Debug, Clone, Deserialize)]
struct ManufacturingPad {
    id: String,
    copper: Polygon,
    plated: bool,
}

#[derive(Debug, Clone, Deserialize)]
struct ManufacturingHole {
    id: String,
    center_mm: [f64; 2],
    diameter_mm: f64,
}

#[derive(Debug, Clone, Deserialize)]
struct Polygon {
    vertices_mm: Vec<[f64; 2]>,
}

#[derive(Debug, Clone, Deserialize)]
struct Component {
    id: String,
    mpn: String,
    footprint_pads: Vec<Pad>,
}

#[derive(Debug, Clone, Deserialize)]
struct Pad {
    pad: String,
    uuid: String,
    net: String,
    position_mm: [f64; 2],
    size_mm: [f64; 2],
    drill_mm: [f64; 2],
    orientation_deg: f64,
    shape: u8,
    layers: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct Trace {
    uuid: String,
    net: String,
    points_mm: Vec<[f64; 2]>,
    layer: String,
    width_mm: f64,
}

/// Dimensions and source binding for one extracted bridge terminal neck.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NeckGeometry {
    /// Electrical net represented by this neck.
    pub net: String,
    /// Native bridge pad number and UUID.
    pub pad_number: String,
    pub pad_uuid: String,
    /// Native trace UUID and copper layer.
    pub trace_uuid: String,
    pub trace_layer: String,
    /// Length from the pad center to the far trace endpoint, in millimetres.
    pub trace_length_mm: f64,
    /// Native trace width, in millimetres.
    pub trace_width_mm: f64,
    /// Native pad dimensions and drill, in millimetres.
    pub pad_size_mm: [f64; 2],
    pub drill_mm: f64,
    /// KiCad pad shape: 1 is the rectangular pin-1 pad, 2 is an obround.
    pub pad_shape: u8,
    /// Localized trace direction.  It is always +Y in the generated model.
    pub reversed_native_trace: bool,
}

/// Complete deterministic Gmsh model for the four bridge terminal necks.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct NeckModel {
    /// Native board digest used to bind this model.
    pub board_sha256: String,
    /// Canonical bridge identity.
    pub bridge_id: String,
    pub bridge_mpn: String,
    /// Exact reviewed neck records, ordered `minus`, `ac1`, `ac2`, `plus`.
    pub necks: Vec<NeckGeometry>,
}

/// Board stackup dimensions parsed from the native KiCad board bytes.
///
/// These values are kept separate from the neck geometry because they are
/// global board properties. A physical-model contract must use these parsed
/// dimensions instead of silently carrying an old fabrication assumption.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StackupDimensions {
    pub board_thickness_mm: f64,
    pub copper_thickness_um: f64,
}

/// Extract the finished board and outer copper thicknesses from a retained
/// native capture. The parser is intentionally bounded to KiCad's `(general)`
/// and `(stackup)` records; missing or inconsistent records fail closed.
pub fn extract_stackup_dimensions(native_json: &[u8]) -> Result<StackupDimensions> {
    let native: NativeInput = serde_json::from_slice(native_json).context("parse native.json")?;
    ensure!(
        format!("{:x}", Sha256::digest(native.board_file_utf8.as_bytes())) == native.board_sha256,
        "stackup native board digest mismatch"
    );
    let dimensions = zapote_drc::stackup::physical_dimensions(&native.board_file_utf8)
        .map_err(anyhow::Error::msg)?;
    let front = *dimensions
        .layers_mm
        .get("F.Cu")
        .context("missing front copper")?;
    let back = *dimensions
        .layers_mm
        .get("B.Cu")
        .context("missing back copper")?;
    ensure!(
        (front - back).abs() < 1e-9,
        "outer copper layers have inconsistent thickness"
    );
    ensure!(
        dimensions
            .layers_mm
            .keys()
            .filter(|name| name.ends_with(".Cu"))
            .count()
            == 2,
        "joint model supports two copper layers"
    );
    Ok(StackupDimensions {
        board_thickness_mm: dimensions.board_thickness_mm,
        copper_thickness_um: front * 1000.0,
    })
}

/// Stable digest of the extracted bridge geometry, independent of the full
/// native JSON envelope. Contracts can bind this digest and replay can
/// recompute it from the current native/manufacturing capture.
pub fn geometry_fingerprint(model: &NeckModel) -> Result<String> {
    Ok(format!("{:x}", Sha256::digest(serde_json::to_vec(model)?)))
}

/// Mesh-integrity statistics for a generated MSH 2.2 neck case.
#[derive(Debug, Clone, PartialEq)]
pub struct MeshStats {
    /// Areas of physical surfaces 11, 12 and 13 in square metres.
    pub areas_m2: [f64; 3],
    /// Volumes of physical volumes 1 (copper) and 2 (FR4) in cubic metres.
    pub volumes_m3: [f64; 2],
    pub nodes: usize,
    pub tetrahedra: usize,
}

/// Verify the bounded ASCII Gmsh 2.2 mesh emitted by the Gmsh generator.
///
/// The check is deliberately structural: all tetrahedral exterior faces must
/// have exactly one triangle in physical group 11, 12 or 13, while any
/// triangle assigned to a physical group must be an exterior face.  This
/// catches convection accidentally applied to the copper/FR4 interface before
/// an Elmer solve is allowed to consume the mesh.
pub fn verify_mesh(mesh: &str, neck: &NeckGeometry, copper_thickness_um: f64) -> Result<MeshStats> {
    ensure!(
        mesh.starts_with("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n"),
        "expected ASCII MSH 2.2"
    );
    let top = FR4_THICKNESS_M + copper_thickness_um * 1e-6;
    let length = neck.trace_length_mm * 1e-3;
    let lines: Vec<&str> = mesh.lines().collect();
    let node_start = lines
        .iter()
        .position(|line| line.trim() == "$Nodes")
        .context("missing $Nodes")?;
    let node_count: usize = lines
        .get(node_start + 1)
        .context("missing node count")?
        .trim()
        .parse()?;
    let mut nodes = BTreeMap::new();
    for line in lines.iter().skip(node_start + 2).take(node_count) {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure!(fields.len() == 4, "malformed node row");
        nodes.insert(
            fields[0].parse::<u64>()?,
            [
                fields[1].parse::<f64>()?,
                fields[2].parse::<f64>()?,
                fields[3].parse::<f64>()?,
            ],
        );
    }
    ensure!(nodes.len() == node_count, "duplicate or missing node ids");
    ensure!(
        nodes.values().all(|p| p.iter().all(|x| x.is_finite())
            && p[0].abs() <= 0.0025 + 1e-9
            && p[1] >= -0.002 - 1e-9
            && p[1] <= length + 1e-9
            && p[2] >= -1e-9
            && p[2] <= top + 1e-9),
        "mesh nodes outside local native bounds or non-finite"
    );
    let elem_start = lines
        .iter()
        .position(|line| line.trim() == "$Elements")
        .context("missing $Elements")?;
    let elem_count: usize = lines
        .get(elem_start + 1)
        .context("missing element count")?
        .trim()
        .parse()?;
    let mut boundary = BTreeMap::<[u64; 3], usize>::new();
    let mut face_material = BTreeMap::<[u64; 3], usize>::new();
    let mut interface_faces = 0usize;
    let mut surfaces = BTreeMap::<[u64; 3], usize>::new();
    let mut surface_areas = [0.0; 3];
    let mut volumes = [0.0; 2];
    let mut tetrahedra = 0;
    for line in lines.iter().skip(elem_start + 2).take(elem_count) {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure!(fields.len() >= 3, "malformed element row");
        let kind: usize = fields[1].parse()?;
        let tags: usize = fields[2].parse()?;
        ensure!(fields.len() >= 3 + tags, "truncated element tags");
        let physical = (tags > 0)
            .then(|| fields[3].parse::<usize>().ok())
            .flatten();
        let node_fields = &fields[3 + tags..];
        if kind == 2 {
            ensure!(node_fields.len() == 3, "triangle must have three nodes");
            let mut face = [
                node_fields[0].parse()?,
                node_fields[1].parse()?,
                node_fields[2].parse()?,
            ];
            face.sort_unstable();
            let Some(tag) = physical else {
                bail!("surface triangle has no physical tag")
            };
            let index = match tag {
                11 => 0,
                12 => 1,
                13 => 2,
                _ => bail!("surface triangle has unexpected physical tag {tag}"),
            };
            ensure!(
                surfaces.insert(face, tag).is_none(),
                "duplicate physical surface triangle"
            );
            let [a, b, c] = face_coords(&nodes, face)?;
            let drill_m = neck.drill_mm * 1e-3;
            let length_m = neck.trace_length_mm * 1e-3;
            if tag == 11 {
                ensure!(
                    [a, b, c]
                        .iter()
                        .all(|p| (p[0].hypot(p[1]) - drill_m / 2.0).abs() < 1e-8
                            && p[2] >= FR4_THICKNESS_M - 1e-9),
                    "physical 11 contains a non-terminal surface"
                );
            } else if tag == 12 {
                ensure!(
                    [a, b, c]
                        .iter()
                        .all(|p| (p[1] - length_m).abs() < 1e-9 && p[2] >= FR4_THICKNESS_M - 1e-9),
                    "physical 12 contains a non-far-face surface"
                );
            } else {
                ensure!(
                    ![a, b, c]
                        .iter()
                        .all(|p| (p[0].hypot(p[1]) - drill_m / 2.0).abs() < 1e-8
                            && p[2] >= FR4_THICKNESS_M - 1e-9),
                    "terminal face incorrectly assigned to air"
                );
                ensure!(
                    ![a, b, c]
                        .iter()
                        .all(|p| (p[1] - length_m).abs() < 1e-9 && p[2] >= FR4_THICKNESS_M - 1e-9),
                    "far copper face incorrectly assigned to air"
                );
            }
            surface_areas[index] += triangle_area(a, b, c);
        } else if kind == 4 {
            ensure!(node_fields.len() == 4, "tetrahedron must have four nodes");
            tetrahedra += 1;
            let mut tetra = [
                node_fields[0].parse()?,
                node_fields[1].parse()?,
                node_fields[2].parse()?,
                node_fields[3].parse()?,
            ];
            tetra.sort_unstable();
            let Some(tag) = physical else {
                bail!("tetrahedron has no physical tag")
            };
            let index = match tag {
                1 => 0,
                2 => 1,
                _ => bail!("tetrahedron has unexpected physical tag {tag}"),
            };
            let [a, b, c, d] = tetra_coords(&nodes, tetra)?;
            let volume = tetra_volume(a, b, c, d);
            ensure!(volume.is_finite() && volume > 0.0, "degenerate tetrahedron");
            ensure!(
                [a, b, c, d].iter().all(|p| if tag == 1 {
                    p[2] >= FR4_THICKNESS_M - 1e-9
                } else {
                    p[2] <= FR4_THICKNESS_M + 1e-9
                }),
                "material assignment crosses copper/substrate interface"
            );
            volumes[index] += volume;
            for face in [
                [tetra[0], tetra[1], tetra[2]],
                [tetra[0], tetra[1], tetra[3]],
                [tetra[0], tetra[2], tetra[3]],
                [tetra[1], tetra[2], tetra[3]],
            ] {
                let mut key = face;
                key.sort_unstable();
                *boundary.entry(key).or_default() += 1;
                if let Some(previous) = face_material.insert(key, tag) {
                    if previous != tag {
                        interface_faces += 1;
                    }
                }
            }
        }
    }
    ensure!(tetrahedra > 0, "mesh contains no tetrahedra");
    ensure!(
        interface_faces > 0,
        "copper/substrate mesh has no conforming shared interface"
    );
    for (face, count) in &boundary {
        ensure!(*count <= 2, "non-manifold or duplicated tetrahedral face");
        if *count == 1 {
            ensure!(
                surfaces.contains_key(face),
                "tetrahedral exterior face lacks physical boundary triangle"
            );
        } else {
            ensure!(
                !surfaces.contains_key(face),
                "internal tetrahedral face is assigned to a boundary physical group"
            );
        }
    }
    ensure!(
        surfaces.keys().all(|face| boundary.get(face) == Some(&1)),
        "physical triangle is not a unique tetrahedral exterior face"
    );
    let tc = copper_thickness_um * 1e-6;
    ensure!(
        tc.is_finite() && tc > 0.0,
        "copper thickness must be finite and positive"
    );
    let expected_cu = copper_area_m2(neck) * tc;
    let hole_area = std::f64::consts::PI * (neck.drill_mm * 1e-3 / 2.0).powi(2);
    let expected_fr4 =
        (0.005 * ((neck.trace_length_mm + 2.0) * 1e-3) - hole_area) * FR4_THICKNESS_M;
    ensure!(
        (volumes[0] - expected_cu).abs() / expected_cu < 0.01,
        "copper volume differs from analytic native shape"
    );
    ensure!(
        (volumes[1] - expected_fr4).abs() / expected_fr4 < 0.01,
        "FR4 volume differs from analytic patch shape"
    );
    ensure!(
        surface_areas
            .iter()
            .all(|area| area.is_finite() && *area > 0.0),
        "one or more required physical surfaces is empty"
    );
    let terminal_area = std::f64::consts::PI * neck.drill_mm * 1e-3 * tc;
    ensure!(
        (surface_areas[0] / terminal_area - 1.0).abs() < 0.02,
        "terminal area differs from drilled copper wall"
    );
    ensure!(
        (surface_areas[1] / (neck.trace_width_mm * 1e-3 * tc) - 1.0).abs() < 1e-7,
        "far face area differs from trace cross-section"
    );
    Ok(MeshStats {
        areas_m2: surface_areas,
        volumes_m3: volumes,
        nodes: node_count,
        tetrahedra,
    })
}

fn face_coords(nodes: &BTreeMap<u64, [f64; 3]>, face: [u64; 3]) -> Result<[[f64; 3]; 3]> {
    Ok([
        *nodes
            .get(&face[0])
            .context("triangle references unknown node")?,
        *nodes
            .get(&face[1])
            .context("triangle references unknown node")?,
        *nodes
            .get(&face[2])
            .context("triangle references unknown node")?,
    ])
}

fn tetra_coords(nodes: &BTreeMap<u64, [f64; 3]>, tetra: [u64; 4]) -> Result<[[f64; 3]; 4]> {
    Ok([
        *nodes
            .get(&tetra[0])
            .context("tetrahedron references unknown node")?,
        *nodes
            .get(&tetra[1])
            .context("tetrahedron references unknown node")?,
        *nodes
            .get(&tetra[2])
            .context("tetrahedron references unknown node")?,
        *nodes
            .get(&tetra[3])
            .context("tetrahedron references unknown node")?,
    ])
}

fn triangle_area(a: [f64; 3], b: [f64; 3], c: [f64; 3]) -> f64 {
    let u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    0.5 * (u[1] * v[2] - u[2] * v[1])
        .hypot((u[2] * v[0] - u[0] * v[2]).hypot(u[0] * v[1] - u[1] * v[0]))
}

fn tetra_volume(a: [f64; 3], b: [f64; 3], c: [f64; 3], d: [f64; 3]) -> f64 {
    let u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    let w = [d[0] - a[0], d[1] - a[1], d[2] - a[2]];
    ((u[0] * (v[1] * w[2] - v[2] * w[1]) - u[1] * (v[0] * w[2] - v[2] * w[0])
        + u[2] * (v[0] * w[1] - v[1] * w[0]))
        .abs())
        / 6.0
}

fn copper_area_m2(neck: &NeckGeometry) -> f64 {
    let w = neck.pad_size_mm[0] * 1e-3;
    let h = neck.pad_size_mm[1] * 1e-3;
    let tw = neck.trace_width_mm * 1e-3;
    let length = neck.trace_length_mm * 1e-3;
    let drill = neck.drill_mm * 1e-3;
    let pad = if neck.pad_shape == 1 {
        w * h
    } else {
        w * (h - w) + std::f64::consts::PI * (w / 2.0).powi(2)
    };
    let overlap = if neck.pad_shape == 1 {
        tw * (h / 2.0)
    } else {
        // Numerically integrate the narrow trace overlap with the obround.
        let n = 4096usize;
        let dy = (h / 2.0) / n as f64;
        (0..n)
            .map(|i| {
                let y = (i as f64 + 0.5) * dy;
                let a = (h - w) / 2.0;
                let pad_width = if y <= a {
                    w
                } else {
                    2.0 * ((w / 2.0).powi(2) - (y - a).powi(2)).max(0.0).sqrt()
                };
                tw.min(pad_width) * dy
            })
            .sum()
    };
    (pad + tw * length - overlap - std::f64::consts::PI * (drill / 2.0).powi(2)).max(0.0)
}

/// Decode the exact frozen baseline geometry with its historical dimensions.
pub fn build_neck_model(native_json: &[u8], manufacturing_json: &[u8]) -> Result<NeckModel> {
    build_neck_model_impl(native_json, manufacturing_json, true)
}

/// Decode a reviewed same-package variant from native geometry. Unlike the
/// historical baseline importer, this does not bake in old widths/lengths;
/// it still requires exactly one trace terminating at each reviewed bridge
/// pad, preserving net/pad identity and manufacturing binding.
pub fn build_neck_model_variant(
    native_json: &[u8],
    manufacturing_json: &[u8],
) -> Result<NeckModel> {
    build_neck_model_impl(native_json, manufacturing_json, false)
}

/// Import the reviewed GBJ2510-F capture.  Pin order follows the native
/// package (1=plus, 2=ac1, 3=ac2, 4=minus), while all identity, geometry and
/// manufacturing records are bound to their captured UUIDs.
pub fn build_gbj_neck_model(native_json: &[u8], manufacturing_json: &[u8]) -> Result<NeckModel> {
    ensure!(
        zapote_drc::native_binding::validate(std::str::from_utf8(native_json)?).status
            == zapote_core::Status::Pass,
        "GBJ native geometry differs from saved board bytes"
    );
    let native: NativeInput = serde_json::from_slice(native_json).context("parse native.json")?;
    let manufacturing: ManufacturingInput =
        serde_json::from_slice(manufacturing_json).context("parse manufacturing.json")?;
    ensure!(
        native.board_sha256 == manufacturing.board_sha256,
        "native/manufacturing board hashes disagree"
    );
    ensure!(
        format!("{:x}", Sha256::digest(native.board_file_utf8.as_bytes())) == native.board_sha256,
        "native board_sha256 does not match embedded board_file_utf8"
    );
    let bridges: Vec<&Component> = native
        .components
        .iter()
        .filter(|c| c.id == BRIDGE_ID || c.mpn == "GBJ2510-F")
        .collect();
    ensure!(
        bridges.len() == 1,
        "expected exactly one GBJ bridge component"
    );
    let bridge = bridges[0];
    ensure!(
        bridge.id == BRIDGE_ID && bridge.mpn == "GBJ2510-F",
        "bridge identity is not GBJ2510-F"
    );
    let mut necks = Vec::with_capacity(4);
    for (idx, (&net, &trace_uuid)) in GBJ_NETS.iter().zip(GBJ_TRACE_UUIDS.iter()).enumerate() {
        let pad_no = (idx + 1).to_string();
        let matching: Vec<&Pad> = bridge
            .footprint_pads
            .iter()
            .filter(|p| p.pad == pad_no && p.net == net)
            .collect();
        ensure!(
            matching.len() == 1,
            "expected GBJ pad {pad_no} on net {net}"
        );
        let pad = matching[0];
        ensure!(pad.size_mm == [4.0, 4.0], "GBJ pad {pad_no} must be 4x4 mm");
        ensure!(
            (pad.drill_mm[0] - 1.6).abs() < 1e-9 && (pad.drill_mm[1] - 1.6).abs() < 1e-9,
            "GBJ pad {pad_no} drill must be 1.6 mm"
        );
        ensure!(
            pad.shape == if idx == 0 { 1 } else { 2 },
            "GBJ pad {pad_no} has unexpected KiCad shape"
        );
        ensure!(
            pad.orientation_deg.rem_euclid(90.0).abs() < 1e-9,
            "GBJ pad orientation must be orthogonal"
        );
        verify_manufacturing_pad(&manufacturing.input, pad)?;
        let traces: Vec<&Trace> = native
            .traces
            .iter()
            .filter(|t| t.uuid == trace_uuid)
            .collect();
        ensure!(traces.len() == 1, "expected one GBJ trace {trace_uuid}");
        let trace = traces[0];
        ensure!(
            trace.net == net && trace.points_mm.len() == 2,
            "GBJ trace identity/shape mismatch"
        );
        ensure!(
            trace.width_mm > pad.size_mm[0] && trace.width_mm <= 2.0 * pad.size_mm[0],
            "GBJ trace width must exceed pad and fit bounded substrate"
        );
        ensure!(
            trace.layer == "F.Cu" || trace.layer == "B.Cu",
            "GBJ trace layer unsupported"
        );
        let d0 = distance_mm(trace.points_mm[0], pad.position_mm);
        let d1 = distance_mm(trace.points_mm[1], pad.position_mm);
        let (length, reversed) = if d0 < 1e-7 {
            (d1, false)
        } else if d1 < 1e-7 {
            (d0, true)
        } else {
            bail!("GBJ trace {trace_uuid} does not terminate at pad center")
        };
        ensure!(length > 0.0, "GBJ trace has zero length");
        let far = if reversed {
            trace.points_mm[0]
        } else {
            trace.points_mm[1]
        };
        ensure!(
            (far[0] - pad.position_mm[0]).abs() < 1e-7 && (far[1] - pad.position_mm[1]).abs() > 0.0,
            "GBJ trace must be centered vertical"
        );
        necks.push(NeckGeometry {
            net: net.into(),
            pad_number: pad.pad.clone(),
            pad_uuid: pad.uuid.clone(),
            trace_uuid: trace.uuid.clone(),
            trace_layer: trace.layer.clone(),
            trace_length_mm: length,
            trace_width_mm: trace.width_mm,
            pad_size_mm: pad.size_mm,
            drill_mm: pad.drill_mm[0],
            pad_shape: pad.shape,
            reversed_native_trace: reversed,
        });
    }
    Ok(NeckModel {
        board_sha256: native.board_sha256,
        bridge_id: BRIDGE_ID.into(),
        bridge_mpn: "GBJ2510-F".into(),
        necks,
    })
}

fn build_neck_model_impl(
    native_json: &[u8],
    manufacturing_json: &[u8],
    strict_baseline: bool,
) -> Result<NeckModel> {
    let native: NativeInput = serde_json::from_slice(native_json).context("parse native.json")?;
    let manufacturing: ManufacturingInput =
        serde_json::from_slice(manufacturing_json).context("parse manufacturing.json")?;
    ensure!(
        native.board_sha256 == manufacturing.board_sha256,
        "native/manufacturing board hashes disagree"
    );
    let calculated = format!("{:x}", Sha256::digest(native.board_file_utf8.as_bytes()));
    ensure!(
        calculated == native.board_sha256,
        "native board_sha256 does not match embedded board_file_utf8"
    );
    ensure!(
        native.board_sha256.len() == 64
            && native.board_sha256.bytes().all(|b| b.is_ascii_hexdigit()),
        "board_sha256 must be a 64-character hexadecimal digest"
    );

    let bridge: Vec<&Component> = native
        .components
        .iter()
        .filter(|component| component.id == BRIDGE_ID || component.mpn == BRIDGE_MPN)
        .collect();
    ensure!(bridge.len() == 1, "expected exactly one bridge component");
    let bridge = bridge[0];
    ensure!(
        bridge.id == BRIDGE_ID && bridge.mpn == BRIDGE_MPN,
        "bridge identity is not the reviewed id/mpn pair"
    );

    let mut pads = Vec::with_capacity(BRIDGE_NETS.len());
    for (index, net) in BRIDGE_NETS.iter().enumerate() {
        let expected_pad = (index + 1).to_string();
        let matching: Vec<&Pad> = bridge
            .footprint_pads
            .iter()
            .filter(|pad| pad.pad == expected_pad && pad.net == *net)
            .collect();
        ensure!(
            matching.len() == 1,
            "expected bridge pad {expected_pad} on net {net}"
        );
        let pad = matching[0];
        ensure!(
            pad.layers
                .iter()
                .any(|layer| layer == "F.Cu" || layer == "B.Cu"),
            "bridge pad {} has no copper layer",
            pad.pad
        );
        ensure!(
            pad.size_mm[0] > 0.0 && pad.size_mm[1] > 0.0,
            "bridge pad {} has invalid dimensions",
            pad.pad
        );
        ensure!(
            (pad.drill_mm[0] - 1.6).abs() < 1e-9 && (pad.drill_mm[1] - 1.6).abs() < 1e-9,
            "bridge pad {} does not have the reviewed 1.6 mm round drill",
            pad.pad
        );
        let expected_shape = if index == 0 { 1 } else { 2 };
        ensure!(
            pad.shape == expected_shape,
            "bridge pad {} has shape {}, expected reviewed shape {}",
            pad.pad,
            pad.shape,
            expected_shape
        );
        ensure!(
            pad.orientation_deg.rem_euclid(90.0).abs() < 1e-9,
            "bridge pad {} has unsupported non-orthogonal orientation",
            pad.pad
        );
        verify_manufacturing_pad(&manufacturing.input, pad)?;
        pads.push(pad);
    }

    let mut necks = Vec::with_capacity(BRIDGE_NETS.len());
    for (index, (&net, &trace_uuid)) in BRIDGE_NETS.iter().zip(TRACE_UUIDS.iter()).enumerate() {
        let pad = pads[index];
        let matching: Vec<&Trace> = native
            .traces
            .iter()
            .filter(|trace| {
                if strict_baseline {
                    trace.uuid == trace_uuid
                } else {
                    trace.net == net
                        && trace.points_mm.len() == 2
                        && trace
                            .points_mm
                            .iter()
                            .any(|point| distance_mm(*point, pad.position_mm) < 1e-7)
                }
            })
            .collect();
        ensure!(
            matching.len() == 1,
            "expected one reviewed trace terminating at bridge net {net}"
        );
        let trace = matching[0];
        ensure!(
            trace.net == net,
            "trace {trace_uuid} net does not match bridge pad"
        );
        ensure!(
            trace.points_mm.len() == 2,
            "trace {trace_uuid} must be a two-point neck"
        );
        if strict_baseline {
            ensure!(
                (trace.width_mm - EXPECTED_WIDTH_MM).abs() < 1e-9,
                "trace {trace_uuid} width differs from reviewed 2.5 mm"
            );
        }
        ensure!(
            trace.layer == "F.Cu" || trace.layer == "B.Cu",
            "trace {trace_uuid} is on unsupported layer {}",
            trace.layer
        );
        let d0 = distance_mm(trace.points_mm[0], pad.position_mm);
        let d1 = distance_mm(trace.points_mm[1], pad.position_mm);
        let (length_mm, reversed) = if d0 < 1e-7 {
            (d1, false)
        } else if d1 < 1e-7 {
            (d0, true)
        } else {
            bail!("trace {trace_uuid} does not terminate at its native pad center")
        };
        if strict_baseline {
            ensure!(
                (length_mm - EXPECTED_LENGTH_MM[index]).abs() < 1e-6,
                "trace {trace_uuid} length {length_mm} mm differs from reviewed {} mm",
                EXPECTED_LENGTH_MM[index]
            );
        }
        let far = if reversed {
            trace.points_mm[0]
        } else {
            trace.points_mm[1]
        };
        let pad_center = pad.position_mm;
        let vector = [far[0] - pad_center[0], far[1] - pad_center[1]];
        ensure!(
            vector[0].abs() < 1e-7 && vector[1].abs() > 0.0,
            "trace {trace_uuid} is diagonal or zero-length after pad binding"
        );
        necks.push(NeckGeometry {
            net: net.to_string(),
            pad_number: pad.pad.clone(),
            pad_uuid: pad.uuid.clone(),
            trace_uuid: trace.uuid.clone(),
            trace_layer: trace.layer.clone(),
            trace_length_mm: length_mm,
            trace_width_mm: trace.width_mm,
            pad_size_mm: pad.size_mm,
            drill_mm: pad.drill_mm[0],
            pad_shape: pad.shape,
            reversed_native_trace: reversed,
        });
    }
    ensure!(
        unique(necks.iter().map(|neck| neck.pad_uuid.as_str())),
        "duplicate bridge pad UUID"
    );
    ensure!(
        unique(necks.iter().map(|neck| neck.trace_uuid.as_str())),
        "duplicate bridge trace UUID"
    );

    Ok(NeckModel {
        board_sha256: native.board_sha256,
        bridge_id: BRIDGE_ID.to_string(),
        bridge_mpn: BRIDGE_MPN.to_string(),
        necks,
    })
}

fn distance_mm(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}

fn verify_manufacturing_pad(input: &ManufacturingDetail, pad: &Pad) -> Result<()> {
    let uuid_marker = format!(":{}@", pad.uuid);
    let copper: Vec<&ManufacturingPad> = input
        .pads
        .iter()
        .filter(|entry| entry.id.contains(&uuid_marker))
        .collect();
    ensure!(
        copper.len() == 2,
        "manufacturing capture must contain F.Cu and B.Cu polygons for pad {}",
        pad.uuid
    );
    ensure!(
        copper.iter().all(|entry| entry.plated),
        "manufacturing pad {} is not plated",
        pad.uuid
    );
    let (mut min_x, mut min_y) = (f64::INFINITY, f64::INFINITY);
    let (mut max_x, mut max_y) = (f64::NEG_INFINITY, f64::NEG_INFINITY);
    for vertex in copper
        .iter()
        .flat_map(|entry| entry.copper.vertices_mm.iter())
    {
        min_x = min_x.min(vertex[0]);
        min_y = min_y.min(vertex[1]);
        max_x = max_x.max(vertex[0]);
        max_y = max_y.max(vertex[1]);
    }
    ensure!(
        (max_x - min_x - pad.size_mm[0]).abs() < 0.02
            && (max_y - min_y - pad.size_mm[1]).abs() < 0.02,
        "manufacturing pad {} bounds disagree with native dimensions",
        pad.uuid
    );
    let holes: Vec<&ManufacturingHole> = input
        .holes
        .iter()
        .filter(|hole| hole.id.contains(&pad.uuid))
        .collect();
    ensure!(
        holes.len() == 1,
        "manufacturing capture must contain one hole for pad {}",
        pad.uuid
    );
    let hole = holes[0];
    ensure!(
        distance_mm(hole.center_mm, pad.position_mm) < 1e-5
            && (hole.diameter_mm - pad.drill_mm[0]).abs() < 1e-6,
        "manufacturing hole disagrees with native pad {}",
        pad.uuid
    );
    Ok(())
}

fn unique<'a>(mut values: impl Iterator<Item = &'a str>) -> bool {
    let mut set = BTreeSet::new();
    values.all(|value| set.insert(value))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn captures() -> (Vec<u8>, Vec<u8>) {
        let board = "canonical-board";
        let digest = format!("{:x}", Sha256::digest(board.as_bytes()));
        let mut components = Vec::new();
        let nets = ["minus", "ac1", "ac2", "plus"];
        for (i, net) in nets.iter().enumerate() {
            components.push(json!({
                "pad": (i + 1).to_string(), "uuid": format!("pad-{i}"), "net": net,
                "position_mm": [30.0 + i as f64 * 5.08, 115.0], "size_mm": [3.0, 3.2],
                "drill_mm": [1.6, 1.6], "orientation_deg": 0.0, "shape": if i == 0 {1} else {2},
                "layers": ["F.Cu", "B.Cu"]
            }));
        }
        let mut traces = Vec::new();
        for (i, ((uuid, net), length)) in TRACE_UUIDS
            .iter()
            .zip(nets)
            .zip(EXPECTED_LENGTH_MM)
            .enumerate()
        {
            let x = 30.0 + i as f64 * 5.08;
            let points = if i < 2 {
                vec![[x, 115.0], [x, 115.0 + length]]
            } else {
                vec![[x, 115.0 - length], [x, 115.0]]
            };
            traces.push(json!({"uuid":uuid,"net":net,"points_mm":points,"layer":if i%2==0{"B.Cu"}else{"F.Cu"},"width_mm":2.5}));
        }
        let native = json!({"board_file_utf8":board,"board_sha256":digest,"components":[{"id":"bridge","mpn":"GBU2510A","footprint_pads":components}],"traces":traces});
        let mut manufacturing_pads = Vec::new();
        let mut manufacturing_holes = Vec::new();
        for (i, net) in nets.iter().enumerate() {
            let x = 30.0 + i as f64 * 5.08;
            let uuid = format!("pad-{i}");
            let copper = vec![
                [x - 1.5, 113.4],
                [x + 1.5, 113.4],
                [x + 1.5, 116.6],
                [x - 1.5, 116.6],
            ];
            for layer in ["F.Cu", "B.Cu"] {
                manufacturing_pads.push(json!({"id":format!("U1.{}:{}@{}:0", i+1, uuid, layer),"copper":{"vertices_mm":copper},"plated":true}));
            }
            manufacturing_holes.push(json!({"id":format!("U1.{}:{}", i+1, uuid),"center_mm":[x,115.0],"diameter_mm":1.6}));
            let _ = net;
        }
        let manufacturing = json!({"board_sha256":digest,"input":{"pads":manufacturing_pads,"holes":manufacturing_holes}});
        (
            serde_json::to_vec(&native).unwrap(),
            serde_json::to_vec(&manufacturing).unwrap(),
        )
    }

    #[test]
    fn exact_capture_generates_four_bound_necks() {
        let (native, manufacturing) = captures();
        let model = build_neck_model(&native, &manufacturing).unwrap();
        assert_eq!(model.necks.len(), 4);
        assert!(model.necks[2].reversed_native_trace);
    }

    #[test]
    fn stackup_dimensions_are_read_from_embedded_board_bytes() {
        let (native, _) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        let board = include_str!("../../../power-entry/candidate/section.kicad_pcb");
        value["board_file_utf8"] = serde_json::Value::String(board.into());
        value["board_sha256"] = serde_json::Value::String(format!("{:x}", Sha256::digest(board)));
        let dimensions = extract_stackup_dimensions(&serde_json::to_vec(&value).unwrap()).unwrap();
        assert_eq!(dimensions.board_thickness_mm, 1.6);
        assert_eq!(dimensions.copper_thickness_um, 70.0);
    }

    #[test]
    fn stackup_dimensions_reject_missing_outer_copper() {
        let (native, _) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        let board = "(kicad_pcb\n (general\n  (thickness 1.6)\n )\n (setup\n  (stackup\n   (layer \"F.Cu\"\n    (type \"copper\")\n    (thickness 0.07)\n   )\n  )\n )\n)";
        value["board_file_utf8"] = serde_json::Value::String(board.into());
        value["board_sha256"] = serde_json::Value::String(format!("{:x}", Sha256::digest(board)));
        assert!(extract_stackup_dimensions(&serde_json::to_vec(&value).unwrap()).is_err());
    }

    #[test]
    fn stackup_cannot_borrow_a_thickness_from_another_sexpression() {
        let (native, _) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        let board = include_str!("../../../power-entry/candidate/section.kicad_pcb").replacen(
            "(thickness 1.6)",
            "",
            1,
        );
        value["board_sha256"] = json!(format!("{:x}", Sha256::digest(&board)));
        value["board_file_utf8"] = json!(board);
        assert!(extract_stackup_dimensions(&serde_json::to_vec(&value).unwrap()).is_err());
    }

    #[test]
    fn reviewed_variant_imports_native_width_and_length_without_baseline_constants() {
        let (native, manufacturing) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        value["traces"][0]["width_mm"] = json!(3.0);
        value["traces"][0]["points_mm"][1][1] = json!(125.0);
        let variant =
            build_neck_model_variant(&serde_json::to_vec(&value).unwrap(), &manufacturing).unwrap();
        assert_eq!(variant.necks[0].trace_width_mm, 3.0);
        assert_eq!(variant.necks[0].trace_length_mm, 10.0);
        assert!(build_neck_model(&serde_json::to_vec(&value).unwrap(), &manufacturing).is_err());
    }

    #[test]
    fn stale_embedded_board_bytes_are_rejected() {
        let (mut native, manufacturing) = captures();
        let index = native.iter().position(|byte| *byte == b'c').unwrap();
        native[index] = b'x';
        let error = build_neck_model(&native, &manufacturing)
            .unwrap_err()
            .to_string();
        assert!(error.contains("native board_sha256"));
    }

    #[test]
    fn duplicate_reviewed_trace_is_rejected() {
        let (native, manufacturing) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        let trace = value["traces"][0].clone();
        value["traces"].as_array_mut().unwrap().push(trace);
        let error = build_neck_model(&serde_json::to_vec(&value).unwrap(), &manufacturing)
            .unwrap_err()
            .to_string();
        assert!(error.contains("expected one reviewed trace"));
    }

    #[test]
    fn wrong_drill_is_rejected() {
        let (native, manufacturing) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        value["components"][0]["footprint_pads"][0]["drill_mm"] = json!([1.5, 1.5]);
        let error = build_neck_model(&serde_json::to_vec(&value).unwrap(), &manufacturing)
            .unwrap_err()
            .to_string();
        assert!(error.contains("1.6 mm round drill"));
    }

    #[test]
    fn reviewed_pin_net_mapping_is_not_net_only() {
        let (native, manufacturing) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        value["components"][0]["footprint_pads"][0]["net"] = json!("ac1");
        value["components"][0]["footprint_pads"][1]["net"] = json!("minus");
        let error = build_neck_model_variant(&serde_json::to_vec(&value).unwrap(), &manufacturing)
            .unwrap_err()
            .to_string();
        assert!(error.contains("expected bridge pad 1 on net minus"));
    }

    #[test]
    fn reviewed_pin_shape_is_bound_even_when_bounds_match() {
        let (native, manufacturing) = captures();
        let mut value: serde_json::Value = serde_json::from_slice(&native).unwrap();
        value["components"][0]["footprint_pads"][0]["shape"] = json!(2);
        let error = build_neck_model_variant(&serde_json::to_vec(&value).unwrap(), &manufacturing)
            .unwrap_err()
            .to_string();
        assert!(error.contains("expected reviewed shape 1"));
    }
}
