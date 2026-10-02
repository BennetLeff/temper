//! Fast broadside coupling screen for disjoint rectangular copper patches.
//!
//! C = ε₀ εᵣ A/d assumes a homogeneous dielectric and parallel plates. Edge
//! fringing, shielding, same-layer coupling and dielectric interfaces are absent.
//! This is neither an upper bound nor a complete capacitance extraction. Native
//! polygons must be decomposed without overlaps/holes being filled in by a box.
use super::{ensure, finite, identities, positive, Error};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

/// An axis-aligned, filled rectangular patch in board coordinates.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Patch {
    /// Native copper object plus unique subdivision identifier.
    pub object: String,
    /// [min x, min y, max x, max y], mm; not a polygon bounding-box substitute.
    pub rect_mm: [f64; 4],
    /// Physical copper surface elevation, mm.
    pub z_mm: f64,
}

/// One overlapping aggressor/victim patch pair.
#[derive(Debug, Clone, Serialize)]
pub struct Pair {
    /// Aggressor identity.
    pub aggressor: String,
    /// Victim identity.
    pub victim: String,
    /// Exact rectangle overlap area, mm².
    pub overlap_mm2: f64,
    /// Physical separation of the two surfaces, mm.
    pub separation_mm: f64,
    /// Parallel-plate estimate, pF.
    pub capacitance_pf: f64,
}

fn overlap(a: &Patch, b: &Patch) -> Result<f64, Error> {
    let min_x = a.rect_mm[0].max(b.rect_mm[0]);
    let min_y = a.rect_mm[1].max(b.rect_mm[1]);
    let max_x = a.rect_mm[2].min(b.rect_mm[2]);
    let max_y = a.rect_mm[3].min(b.rect_mm[3]);
    if min_x >= max_x || min_y >= max_y {
        return Ok(0.0);
    }
    // Distinguish geometric non-overlap from an unrepresentable positive area.
    positive((max_x - min_x) * (max_y - min_y), "overlap area")
}

fn validate(patches: &[Patch]) -> Result<(), Error> {
    ensure(!patches.is_empty(), "copper patch population is empty")?;
    identities(patches.iter().map(|p| p.object.as_str()))?;
    let mut order: Vec<_> = (0..patches.len()).collect();
    for p in patches {
        for x in p.rect_mm {
            finite(x, "patch coordinate")?;
        }
        finite(p.z_mm, "patch z")?;
        ensure(
            p.rect_mm[0] < p.rect_mm[2] && p.rect_mm[1] < p.rect_mm[3],
            "patch must have positive area",
        )?;
    }
    order.sort_by(|&a, &b| patches[a].rect_mm[0].total_cmp(&patches[b].rect_mm[0]));
    let mut active: Vec<usize> = Vec::new();
    for i in order {
        active.retain(|&j| patches[j].rect_mm[2] > patches[i].rect_mm[0]);
        for &j in &active {
            ensure(
                !(patches[i].z_mm == patches[j].z_mm && overlap(&patches[i], &patches[j])? > 0.0),
                "coplanar patches within one population overlap (double counting)",
            )?;
        }
        active.push(i);
    }
    Ok(())
}

/// Sweep x intervals, then test y overlap. Cost O(n log n + x-overlap pairs),
/// worst-case O(n²). Results are sorted by descending C, then object identity.
/// Known zero projected overlap yields an empty list, not zero real coupling.
///
/// # Errors
/// Rejects invalid/overlapping subdivisions, duplicate identities, overlapping
/// coplanar aggressor/victim patches, nonpositive εᵣ and arithmetic overflow.
pub fn broadside(
    aggressors: &[Patch],
    victims: &[Patch],
    relative_permittivity: f64,
) -> Result<Vec<Pair>, Error> {
    positive(relative_permittivity, "relative_permittivity")?;
    validate(aggressors)?;
    validate(victims)?;
    identities(aggressors.iter().chain(victims).map(|p| p.object.as_str()))?;
    // End events precede starts at identical x, so edge contact has zero area.
    let mut events = Vec::with_capacity((aggressors.len() + victims.len()) * 2);
    for (side, patches) in [aggressors, victims].into_iter().enumerate() {
        for (i, p) in patches.iter().enumerate() {
            events.push((p.rect_mm[0], true, side, i));
            events.push((p.rect_mm[2], false, side, i));
        }
    }
    events.sort_by(|a, b| {
        a.0.total_cmp(&b.0)
            .then(a.1.cmp(&b.1))
            .then(a.2.cmp(&b.2))
            .then(a.3.cmp(&b.3))
    });
    let mut active = [BTreeSet::new(), BTreeSet::new()];
    let mut pairs = Vec::new();
    for (_, start, side, i) in events {
        if !start {
            active[side].remove(&i);
            continue;
        }
        for &j in &active[1 - side] {
            let (a, b) = if side == 0 {
                (&aggressors[i], &victims[j])
            } else {
                (&aggressors[j], &victims[i])
            };
            let area = overlap(a, b)?;
            if area == 0.0 {
                continue;
            }
            let separation = positive((a.z_mm - b.z_mm).abs(), "broadside separation")?;
            let c = parallel_plate_pf(area, separation, relative_permittivity)?;
            pairs.push(Pair {
                aggressor: a.object.clone(),
                victim: b.object.clone(),
                overlap_mm2: area,
                separation_mm: separation,
                capacitance_pf: c,
            });
        }
        active[side].insert(i);
    }
    pairs.sort_by(|a, b| {
        b.capacitance_pf
            .total_cmp(&a.capacitance_pf)
            .then(a.aggressor.cmp(&b.aggressor))
            .then(a.victim.cmp(&b.victim))
    });
    Ok(pairs)
}

/// Parallel-plate estimate from a positive, independently measured overlap area.
/// Units are mm², mm, and dimensionless relative permittivity; output is pF.
/// No fringing or shielding is represented.
///
/// # Errors
/// Rejects nonpositive/nonfinite geometry and an unrepresentable result.
pub fn parallel_plate_pf(
    area_mm2: f64,
    separation_mm: f64,
    relative_permittivity: f64,
) -> Result<f64, Error> {
    positive(
        0.008_854_187_812_8
            * positive(relative_permittivity, "relative_permittivity")?
            * positive(area_mm2, "overlap area")?
            / positive(separation_mm, "separation")?,
        "capacitance estimate",
    )
}
