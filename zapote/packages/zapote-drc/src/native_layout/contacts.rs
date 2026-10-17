//! Apply the existing pad-entry kernel to native track/pad contacts and filled
//! pad copper. Native connectivity supplies candidates; Rust measures witnesses.
use super::{require, Measurement, NativeReport, Result, Snapshot};
use crate::{layout_quality::report::Family, manufacturing::Polygon, power_contact};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PadEntry {
    pub track_uuid: String,
    pub pad_uuid: String,
    pub reference: String,
    pub pin: String,
    pub net: String,
    pub layer: String,
    pub entry: power_contact::Entry,
}

pub(super) fn measure(snapshot: &Snapshot, report: &mut NativeReport) -> Result<()> {
    let pads: BTreeMap<_, _> = snapshot.pads.iter().map(|p| (p.uuid.as_str(), p)).collect();
    let copper: BTreeMap<_, _> = snapshot
        .copper
        .iter()
        .map(|c| ((c.uuid.as_str(), c.layer.as_str()), c))
        .collect();
    let mut full_width = 0;
    let mut no_witness = 0;
    for track in &snapshot.tracks {
        for id in &track.pad_contacts {
            let pad = pads.get(id.as_str()).ok_or("native contact pad absent")?;
            require(
                pad.net == track.net && pad.layers.contains(&track.layer),
                "native contact crosses net labels or flashed layers",
            )?;
            let shape = copper
                .get(&(id.as_str(), track.layer.as_str()))
                .ok_or("native contact pad copper absent")?;
            require(
                shape.kind == "pad" && shape.net == pad.net,
                "native contact copper identity mismatch",
            )?;
            let regions = shape
                .polygons
                .iter()
                .map(|p| power_contact::Region {
                    shell: Polygon {
                        vertices_mm: p.shell.clone(),
                    },
                    holes: p
                        .holes
                        .iter()
                        .map(|h| Polygon {
                            vertices_mm: h.clone(),
                        })
                        .collect(),
                })
                .collect::<Vec<_>>();
            let entry = power_contact::entry_regions(
                &regions,
                track.start_mm,
                track.end_mm,
                track.width_mm,
            )?;
            full_width += usize::from(entry.full_width_chord_observed);
            no_witness += usize::from(entry.witness_centerline_mm.is_none());
            report.metric(Measurement {
                id: format!("pad-entry/{}/{id}", track.uuid),
                family: Family::CopperDistribution,
                objects: vec![track.uuid.clone(), id.clone()],
                location_mm: entry.witness_centerline_mm.unwrap_or(pad.position_mm),
                metric: "entry_chord_mm".into(),
                value: entry.certified_chord_mm,
                interpretation: "Largest sampled contiguous chord through filled pad and straight trace body; excludes end caps. Zero means no witness, not an open. Not minimum-cut width or ampacity.".into(),
            })?;
            report.pad_entries.push(PadEntry {
                track_uuid: track.uuid.clone(),
                pad_uuid: id.clone(),
                reference: pad.reference.clone(),
                pin: pad.number.clone(),
                net: pad.net.clone(),
                layer: track.layer.clone(),
                entry,
            });
        }
    }
    report
        .pad_entries
        .sort_by(|a, b| (&a.track_uuid, &a.pad_uuid).cmp(&(&b.track_uuid, &b.pad_uuid)));
    report.population.insert(
        "pad_track_contacts_evaluated".into(),
        report.pad_entries.len(),
    );
    report
        .population
        .insert("pad_entries_full_width_witness".into(), full_width);
    report
        .population
        .insert("pad_entries_no_straight_witness".into(), no_witness);
    Ok(())
}
