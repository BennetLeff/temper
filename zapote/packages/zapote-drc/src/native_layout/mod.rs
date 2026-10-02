//! Native-board layout analysis. Geometry is read by pcbnew, policy and metrics
//! live here. A geometry screen never supplies a missing physical model.
mod contacts;
mod geometry;
mod paths;
mod report;
#[cfg(test)]
mod tests;
pub use contacts::PadEntry;
pub use paths::Route;
pub use report::{compare, evaluate, Delta, Measurement, NativeReport};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Polygon {
    pub shell: Vec<[f64; 2]>,
    pub holes: Vec<Vec<[f64; 2]>>,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Courtyard {
    pub side: String,
    pub polygons: Vec<Polygon>,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Component {
    pub reference: String,
    pub uuid: String,
    pub position_mm: [f64; 2],
    pub courtyards: Vec<Courtyard>,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Pad {
    pub uuid: String,
    pub reference: String,
    pub number: String,
    pub net: String,
    pub position_mm: [f64; 2],
    pub layers: Vec<String>,
    pub plated_through: bool,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Track {
    pub uuid: String,
    pub net: String,
    pub layer: String,
    pub start_mm: [f64; 2],
    pub end_mm: [f64; 2],
    pub width_mm: f64,
    pub length_mm: f64,
    pub pad_contacts: Vec<String>,
    pub start_contacts: Vec<String>,
    pub end_contacts: Vec<String>,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Via {
    pub uuid: String,
    pub net: String,
    pub position_mm: [f64; 2],
    pub layers: Vec<String>,
}
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Copper {
    pub uuid: String,
    pub kind: String,
    pub net: String,
    pub layer: String,
    pub polygons: Vec<Polygon>,
}
/// Captured facts, not a user-authored engineering model. The production caller
/// invokes the pinned extractor on saved bytes and verifies its script hash.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    pub schema: String,
    pub board_sha256: String,
    pub extractor_sha256: String,
    pub tool_version: String,
    pub polygon_error_mm: f64,
    pub layers: Vec<String>,
    pub components: Vec<Component>,
    pub pads: Vec<Pad>,
    pub tracks: Vec<Track>,
    pub vias: Vec<Via>,
    pub copper: Vec<Copper>,
    pub zone_count: usize,
    pub gaps: Vec<String>,
}
pub(crate) type Result<T> = std::result::Result<T, String>;
pub(crate) fn require(valid: bool, message: impl Into<String>) -> Result<()> {
    if valid {
        Ok(())
    } else {
        Err(message.into())
    }
}
pub(crate) fn finite(value: f64) -> Result<f64> {
    require(value.is_finite(), "non-finite native metric")?;
    Ok(value)
}
pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
impl Snapshot {
    pub fn validate(&self, board: &[u8]) -> Result<()> {
        require(
            self.schema == "zapote.layout-native.v2",
            "unsupported native layout schema",
        )?;
        require(
            self.board_sha256 == digest(board),
            "snapshot board hash differs from saved bytes",
        )?;
        require(!self.tool_version.is_empty(), "missing native tool version")?;
        require(
            !self.layers.is_empty()
                && self.layers.iter().collect::<BTreeSet<_>>().len() == self.layers.len(),
            "empty or duplicate copper layers",
        )?;
        require(
            self.polygon_error_mm > 0.0 && self.polygon_error_mm <= 0.001,
            "unsupported polygon approximation",
        )?;
        require(
            !self.components.is_empty() && !self.pads.is_empty() && !self.copper.is_empty(),
            "empty native object population",
        )?;
        let mut ids = BTreeSet::new();
        for id in self
            .components
            .iter()
            .map(|v| &v.uuid)
            .chain(self.pads.iter().map(|v| &v.uuid))
            .chain(self.tracks.iter().map(|v| &v.uuid))
            .chain(self.vias.iter().map(|v| &v.uuid))
        {
            require(
                !id.is_empty() && ids.insert(id),
                "empty or duplicate native UUID",
            )?;
        }
        let refs: BTreeSet<_> = self.components.iter().map(|v| &v.reference).collect();
        require(
            refs.len() == self.components.len(),
            "duplicate component reference",
        )?;
        let mut logical_pins = BTreeMap::new();
        for p in &self.pads {
            if let Some(net) = logical_pins.insert((&p.reference, &p.number), &p.net) {
                require(
                    net == &p.net,
                    "physical pads on a logical pin disagree on net",
                )?;
            }
            require(refs.contains(&p.reference), "pad parent is absent")?;
            require(
                p.layers.iter().all(|l| self.layers.contains(l))
                    && p.layers.iter().collect::<BTreeSet<_>>().len() == p.layers.len(),
                "invalid pad layer set",
            )?;
            for v in p.position_mm {
                finite(v)?;
            }
        }
        for c in &self.components {
            for v in c.position_mm {
                finite(v)?;
            }
        }
        let mut shapes = BTreeSet::new();
        for c in &self.copper {
            require(
                shapes.insert((&c.uuid, &c.layer)),
                "duplicate native copper object/layer",
            )?;
            require(self.layers.contains(&c.layer), "copper on undeclared layer")?;
            geometry::shape(&c.polygons)?;
        }
        for t in &self.tracks {
            for v in t.start_mm.into_iter().chain(t.end_mm) {
                finite(v)?;
            }
            require(
                t.width_mm.is_finite()
                    && t.width_mm > 0.0
                    && t.length_mm.is_finite()
                    && t.length_mm > 0.0,
                "invalid native track dimensions",
            )?;
            require(self.layers.contains(&t.layer), "track on undeclared layer")?;
            let contacts: BTreeSet<_> = t.pad_contacts.iter().collect();
            require(
                contacts.len() == t.pad_contacts.len()
                    && t.start_contacts
                        .iter()
                        .chain(&t.end_contacts)
                        .all(|id| contacts.contains(id)),
                "inconsistent native track pad contacts",
            )?;
            require(
                (geometry::distance(t.start_mm, t.end_mm) - t.length_mm).abs() <= 0.000002,
                "straight track length differs from native endpoints",
            )?;
        }
        for v in &self.vias {
            require(
                v.layers.len() >= 2
                    && v.layers.iter().all(|l| self.layers.contains(l))
                    && v.layers.iter().collect::<BTreeSet<_>>().len() == v.layers.len(),
                "invalid via layer span",
            )?;
            for x in v.position_mm {
                finite(x)?;
            }
        }
        Ok(())
    }
}
