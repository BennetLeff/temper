//! Source-bound thermal screening for the PFC current shunt.
//!
//! This is deliberately a copper/terminal model.  The resistor body is not
//! assigned a guessed conductivity or an unverified terminal-to-body theta;
//! therefore the result is a screening result and remains IND for package
//! temperature until that manufacturer datum is supplied.
use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

pub const QUALIFIED_MPN: &str = "HCSM2818FT10L0";
pub const RESISTANCE_OHM: f64 = 0.010;
pub const RESISTANCE_TOLERANCE: f64 = 0.01;
pub const TCR_PPM_PER_K: f64 = 75.0;
pub const RATED_POWER_W: f64 = 5.0;
pub const MIN_PAD_TRACE_AREA_MM2: f64 = 500.0;
pub const CROP_HALF_WIDTH_MM: f64 = 15.0;

#[derive(Debug, Clone, Deserialize)]
struct Native { board_file_utf8: String, board_sha256: String, components: Vec<Component>, traces: Vec<Trace> }
#[derive(Debug, Clone, Deserialize)]
struct Component { id: String, mpn: String, position_mm: [f64; 2], footprint_pads: Vec<Pad> }
#[derive(Debug, Clone, Deserialize)]
struct Pad { pad: String, uuid: String, net: String, position_mm: [f64; 2], size_mm: [f64; 2], orientation_deg: f64, layers: Vec<String> }
#[derive(Debug, Clone, Deserialize)]
struct Trace { uuid: String, net: String, points_mm: Vec<[f64; 2]>, layer: String, width_mm: f64 }

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ShuntGeometry {
    pub board_sha256: String,
    pub component_id: String,
    pub mpn: String,
    pub position_mm: [f64; 2],
    pub pads: Vec<PadGeometry>,
    pub attached_traces: Vec<TraceGeometry>,
    pub crop_bounds_mm: [f64; 4],
}
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PadGeometry { pub number: String, pub uuid: String, pub net: String, pub position_mm: [f64; 2], pub size_mm: [f64; 2], pub orientation_deg: f64, pub layers: Vec<String> }
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TraceGeometry { pub uuid: String, pub net: String, pub layer: String, pub width_mm: f64, pub length_mm: f64, pub points_mm: Vec<[f64; 2]> }

impl ShuntGeometry {
    pub fn from_native(bytes: &[u8]) -> Result<Self> {
        let n: Native = serde_json::from_slice(bytes).context("parse native capture")?;
        ensure!(!n.board_sha256.is_empty(), "native capture is missing board digest");
        ensure!(format!("{:x}", Sha256::digest(n.board_file_utf8.as_bytes())) == n.board_sha256,
            "native board bytes do not match board_sha256");
        let c = n.components.iter().find(|c| c.id.eq_ignore_ascii_case("shunt"))
            .context("native capture has no shunt component")?;
        ensure!(c.mpn == QUALIFIED_MPN,
            "shunt MPN {} is not qualified; expected {} (rejecting legacy fictional part)", c.mpn, QUALIFIED_MPN);
        ensure!(c.footprint_pads.len() == 2, "qualified two-terminal shunt requires exactly two pads");
        let mut pads = c.footprint_pads.iter().map(|p| PadGeometry { number:p.pad.clone(), uuid:p.uuid.clone(), net:p.net.clone(), position_mm:p.position_mm, size_mm:p.size_mm, orientation_deg:p.orientation_deg, layers:p.layers.clone() }).collect::<Vec<_>>();
        pads.sort_by(|a,b| a.number.cmp(&b.number));
        ensure!(pads[0].number != pads[1].number && pads.iter().all(|p| p.layers.iter().any(|l| l == "F.Cu" || l == "B.Cu")), "invalid shunt pad identity/layers");
        let nets: Vec<String> = pads.iter().map(|p| p.net.clone()).collect();
        let mut attached = Vec::new();
        let crop = [c.position_mm[0]-CROP_HALF_WIDTH_MM, c.position_mm[0]+CROP_HALF_WIDTH_MM,
            c.position_mm[1]-CROP_HALF_WIDTH_MM, c.position_mm[1]+CROP_HALF_WIDTH_MM];
        for t in n.traces.iter().filter(|t| nets.contains(&t.net)) {
            ensure!(t.points_mm.len() >= 2 && t.width_mm.is_finite() && t.width_mm > 0.0, "invalid shunt trace {}", t.uuid);
            let intersects = t.points_mm.iter().any(|q| q[0] >= crop[0] && q[0] <= crop[1] && q[1] >= crop[2] && q[1] <= crop[3]);
            if !intersects { continue; }
            let length_mm = t.points_mm.windows(2).map(|w| ((w[1][0]-w[0][0]).powi(2)+(w[1][1]-w[0][1]).powi(2)).sqrt()).sum();
            attached.push(TraceGeometry { uuid:t.uuid.clone(), net:t.net.clone(), layer:t.layer.clone(), width_mm:t.width_mm, length_mm, points_mm:t.points_mm.clone() });
        }
        ensure!(!attached.is_empty(), "no native copper attached to shunt nets");
        Ok(Self { board_sha256:n.board_sha256, component_id:c.id.clone(), mpn:c.mpn.clone(), position_mm:c.position_mm, pads, attached_traces:attached, crop_bounds_mm:crop })
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ThermalCase { pub name: String, pub current_rms_a: f64, pub heat_split: [f64;2], pub resistance_ohm: f64, pub power_w: f64, pub terminal_temp_limit_c: f64, pub status: String, pub internal_theta_max_c_per_w: Option<f64> }

pub fn cases(current_rms_a: f64) -> Result<Vec<ThermalCase>> {
    ensure!(current_rms_a.is_finite() && current_rms_a >= 0.0, "current must be finite and non-negative");
    let r = RESISTANCE_OHM * (1.0 + RESISTANCE_TOLERANCE);
    let p = current_rms_a * current_rms_a * r;
    Ok([("nominal-50-50",[0.5,0.5]),("pad1-hot",[1.0,0.0]),("pad2-hot",[0.0,1.0])].into_iter().map(|(name,split)| ThermalCase { name:name.into(), current_rms_a, heat_split:split, resistance_ohm:r, power_w:p, terminal_temp_limit_c:100.0, status:"INDETERMINATE_BODY_THERMAL_DATA".into(), internal_theta_max_c_per_w:None }).collect())
}

/// Emit a conservative copper-only Gmsh plate.  No resistor-body material is
/// invented; terminal heat is applied as a pair of boundary fluxes by the
/// caller's Elmer case.
pub fn gmsh_geometry(g: &ShuntGeometry, path: &Path) -> Result<()> {
    let [minx,maxx,miny,maxy] = g.crop_bounds_mm;
    ensure!([minx,maxx,miny,maxy].iter().all(|v| v.is_finite()) && maxx>minx && maxy>miny, "invalid shunt crop");
    let mut s = String::from("SetFactory(\"OpenCASCADE\");\n");
    let mut id = 1usize;
    for p in &g.pads {
        let z = if p.layers.iter().any(|l| l == "F.Cu") { 0.0 } else { -0.00007 };
        s.push_str(&format!("Box({id}) = {{{}, {}, {}, {}, {}, 0.00007}};\n", (p.position_mm[0]-p.size_mm[0]/2.0)/1000.0, (p.position_mm[1]-p.size_mm[1]/2.0)/1000.0, z, p.size_mm[0]/1000.0, p.size_mm[1]/1000.0));
        id += 1;
    }
    // Each attached trace is represented by its measured length and width as
    // an axis-aligned segment.  The segment is a conservative copper volume;
    // no material is added where native copper was not observed.
    for t in &g.attached_traces {
        let p = g.pads.iter().find(|p| p.net == t.net).context("trace net has no shunt pad")?;
        let z = if p.layers.iter().any(|l| l == "F.Cu") { 0.0 } else { -0.00007 };
        let (lo_x, hi_x) = t.points_mm.iter().map(|q| q[0]).fold((f64::INFINITY, f64::NEG_INFINITY), |(lo,hi),x|(lo.min(x),hi.max(x)));
        let (lo_y, hi_y) = t.points_mm.iter().map(|q| q[1]).fold((f64::INFINITY, f64::NEG_INFINITY), |(lo,hi),y|(lo.min(y),hi.max(y)));
        ensure!(hi_x >= lo_x && hi_y >= lo_y, "trace {} has invalid envelope", t.uuid);
        s.push_str(&format!("Box({id}) = {{{}, {}, {}, {}, {}, 0.00007}};\n", (lo_x-t.width_mm/2.0)/1000.0, (lo_y-t.width_mm/2.0)/1000.0, z, ((hi_x-lo_x)+t.width_mm)/1000.0, ((hi_y-lo_y)+t.width_mm)/1000.0));
        id += 1;
    }
    s.push_str(&format!("Physical Volume(\"COPPER\") = {{{}}};\n", (1..id).map(|i| i.to_string()).collect::<Vec<_>>().join(",")));
    fs::write(path, s).with_context(|| format!("write {}", path.display()))?;
    Ok(())
}
