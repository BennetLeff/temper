//! Routing policy consumes KiCad's native connectivity clusters, never net labels alone.
use anyhow::{ensure, Context, Result};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
pub struct Track {
    uuid: String,
    kind: String,
    net: String,
    layer: String,
    width_mm: f64,
    start_mm: [f64; 2],
    end_mm: [f64; 2],
    bounds_mm: [f64; 4],
}

#[derive(Deserialize)]
pub struct Cluster {
    pad: String,
    pads: Vec<String>,
    tracks: Vec<String>,
}

#[derive(Deserialize)]
pub struct Measurement {
    tracks: Vec<Track>,
    connectivity: Vec<Cluster>,
}

pub fn evaluate(m: &Measurement, outline: [f64; 4], findings: &mut Vec<Value>) -> Result<()> {
    let expected_pads: BTreeSet<&str> = [
        "C9.1", "C9.2", "U3.1", "U3.2", "U3.3", "U3.4", "U3.5", "U3.6",
    ]
    .into();
    let clusters: BTreeMap<&str, &Cluster> =
        m.connectivity.iter().map(|c| (c.pad.as_str(), c)).collect();
    ensure!(
        clusters.len() == m.connectivity.len()
            && clusters.keys().copied().collect::<BTreeSet<_>>() == expected_pads,
        "incomplete or duplicate connectivity census"
    );
    let tracks: BTreeMap<&str, &Track> = m.tracks.iter().map(|t| (t.uuid.as_str(), t)).collect();
    ensure!(
        tracks.len() == m.tracks.len() && !tracks.contains_key(""),
        "invalid track identities"
    );
    for cluster in clusters.values() {
        let pads: BTreeSet<&str> = cluster.pads.iter().map(String::as_str).collect();
        let ids: BTreeSet<&str> = cluster.tracks.iter().map(String::as_str).collect();
        ensure!(
            pads.len() == cluster.pads.len()
                && pads.contains(cluster.pad.as_str())
                && pads.is_subset(&expected_pads),
            "invalid connected-pad evidence"
        );
        ensure!(
            ids.len() == cluster.tracks.len() && ids.iter().all(|id| tracks.contains_key(id)),
            "invalid connected-track evidence"
        );
        for pad in &pads {
            let other = clusters
                .get(pad)
                .context("missing reciprocal connectivity")?;
            ensure!(
                other
                    .pads
                    .iter()
                    .map(String::as_str)
                    .collect::<BTreeSet<_>>()
                    == pads
                    && other
                        .tracks
                        .iter()
                        .map(String::as_str)
                        .collect::<BTreeSet<_>>()
                        == ids,
                "inconsistent native clusters"
            );
        }
        let partner = match cluster.pad.as_str() {
            "C9.1" => Some("U3.3"),
            "U3.3" => Some("C9.1"),
            "C9.2" => Some("U3.1"),
            "U3.1" => Some("C9.2"),
            _ => None,
        };
        if let Some(partner) = partner {
            if !pads.contains(partner) || ids.is_empty() {
                findings.push(json!({"id": format!("unrouted:{}:{partner}", cluster.pad)}));
            }
        }
        if pads
            .iter()
            .any(|p| *p != cluster.pad && Some(*p) != partner)
            || (partner.is_none() && !ids.is_empty())
        {
            findings.push(json!({"id": format!("unintended_connection:{}", cluster.pad)}));
        }
    }
    if tracks.len() > 22 {
        findings.push(json!({"id": "too_many_tracks"}));
    }
    for track in tracks.values() {
        ensure!(
            track
                .start_mm
                .iter()
                .chain(track.end_mm.iter())
                .chain(track.bounds_mm.iter())
                .chain([&track.width_mm])
                .all(|v| v.is_finite())
                && track.width_mm > 0.0
                && track.bounds_mm[0] < track.bounds_mm[2]
                && track.bounds_mm[1] < track.bounds_mm[3],
            "invalid track geometry"
        );
        if track.kind != "segment"
            || track.layer != "F.Cu"
            || (track.width_mm - 0.25).abs() > 1e-9
            || !["+15V", "gnd"].contains(&track.net.as_str())
            || track.start_mm == track.end_mm
        {
            findings.push(json!({"id": format!("unsupported_track:{}", track.uuid)}));
        }
        let [left, top, right, bottom] = track.bounds_mm;
        if left < outline[0] || top < outline[1] || right > outline[2] || bottom > outline[3] {
            findings.push(json!({"id": format!("copper_outside_outline:{}", track.uuid)}));
        }
        let anchor = if track.net == "+15V" { "C9.1" } else { "C9.2" };
        if !clusters[anchor].tracks.contains(&track.uuid) {
            findings.push(json!({"id": format!("extraneous_copper:{}", track.uuid)}));
        }
    }
    Ok(())
}
